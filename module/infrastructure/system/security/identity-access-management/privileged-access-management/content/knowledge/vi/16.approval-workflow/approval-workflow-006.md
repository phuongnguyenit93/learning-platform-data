# Security approval trong quy trình phê duyệt PAM

## 1. Security approval là gì?

**Security approval** là quyết định của chủ thể có thẩm quyền bảo mật về một yêu cầu truy cập hoặc rủi ro liên quan, dựa trên phạm vi công việc, mức đặc quyền, điều kiện kiểm soát và chính sách áp dụng.

Trong quản lý truy cập đặc quyền, quyết định này có thể là một bước của approval workflow trước khi hệ thống cấp quyền tạm thời, phát credential hoặc mở phiên tới hạ tầng nhạy cảm.

Ví dụ, một nhà cung cấp cần chẩn đoán sự cố trên máy chủ production. Owner dịch vụ xác nhận công việc có nhu cầu thực tế. Người phê duyệt bảo mật xem xét đường truy cập, danh tính, quyền hiệu lực, cách bảo vệ credential, giám sát phiên và khả năng thu hồi. Nếu quy trình yêu cầu cả hai bên, một chữ ký bảo mật không thay chữ ký của owner dịch vụ.

Mục tiêu của bước này là tạo một quyết định có căn cứ và có thể thực thi. Việc thêm một người bấm nút vào mọi yêu cầu không tự làm truy cập an toàn hơn.

Sau bài học, người học cần có khả năng:

- Phân biệt security approval với xác thực, ủy quyền và phê duyệt nghiệp vụ.
- Xác định khi nào cần người có thẩm quyền bảo mật tham gia.
- Đánh giá một yêu cầu bằng dữ liệu đủ để quyết định.
- Gắn phê duyệt với target, quyền, thời gian và điều kiện cụ thể.
- Kiểm tra việc cấp quyền có thực thi đúng quyết định hay không.
- Giữ bằng chứng cho phê duyệt, từ chối, thay đổi và thu hồi.

## 2. Vị trí của phê duyệt bảo mật trong chuỗi kiểm soát

~~~mermaid
flowchart TD
    R["Yêu cầu truy cập có phạm vi"] --> V["Kiểm tra dữ liệu và policy"]
    V --> O["Phê duyệt nhu cầu bởi owner nếu bắt buộc"]
    O --> S["Phê duyệt bảo mật nếu policy yêu cầu"]
    S --> C["Kiểm tra các điều kiện trước khi cấp"]
    C --> G["Cấp quyền hoặc mở phiên"]
    G --> M["Giám sát và thu hồi theo vòng đời"]
    V --> A["Bằng chứng"]
    O --> A
    S --> A
    C --> A
    G --> A
    M --> A
~~~

Sơ đồ minh họa một workflow tuần tự. Quy trình thực tế có thể chạy một số bước song song, miễn là điều kiện hoàn thành và thẩm quyền được xác định rõ.

Các quyết định sau có quan hệ nhưng không tương đương:

| Quyết định | Câu hỏi chính |
|---|---|
| Xác thực | Người yêu cầu hoặc người phê duyệt là ai? |
| Phê duyệt nhu cầu | Công việc có cần thiết và phù hợp phạm vi dịch vụ không? |
| Phê duyệt thay đổi | Thay đổi có được thực hiện trong điều kiện vận hành này không? |
| Phê duyệt bảo mật | Yêu cầu đáp ứng điều kiện bảo mật hoặc có ngoại lệ hợp lệ trong thẩm quyền không? |
| Ủy quyền tại thời điểm cấp | Với dữ liệu hiện tại, hệ thống có được cấp quyền cụ thể này không? |
| Thực thi tại đích | Tài khoản thực sự làm được những gì? |

Một tài khoản đã xác thực qua MFA chưa mặc nhiên có quyền phê duyệt. Một yêu cầu đã được phê duyệt chưa mặc nhiên có phiên hoạt động. Một phiên đã mở cũng không chứng minh mọi điều kiện ghi trong quyết định đang được thực thi.

## 3. Khi nào cần security approval?

### 3.1. Dựa vào rủi ro và chính sách

Không phải mọi yêu cầu đều cần chuyên viên bảo mật duyệt thủ công. Một tổ chức có thể dùng policy đã được phê chuẩn để xử lý tự động các yêu cầu thường lệ, phạm vi hẹp và có điều kiện kiểm soát được kiểm chứng.

Những yếu tố thường làm phát sinh nhu cầu đánh giá bổ sung gồm:

- Quyền có khả năng thay đổi diện rộng hoặc ảnh hưởng thành phần tin cậy.
- Truy cập production, tài nguyên nhạy cảm hoặc hệ thống có phạm vi ảnh hưởng lớn.
- Truy cập của nhà cung cấp, đối tác hoặc chủ thể ngoài quy trình thông thường.
- Xuất credential, dùng tài khoản chia sẻ hoặc đường truy cập chưa được quản lý đầy đủ.
- Yêu cầu ngoài cửa sổ, thời lượng hoặc nhóm target đã định.
- Thiếu một biện pháp bắt buộc và đề nghị dùng biện pháp bù trừ.
- Tác vụ làm thay đổi cấu hình PAM, vault, nguồn danh tính hoặc cơ chế lưu bằng chứng.
- Dữ liệu cho thấy yêu cầu khác đáng kể với hồ sơ rủi ro thông thường.

Đây là các yếu tố thiết kế, không phải danh sách quy định chung cho mọi tổ chức. Ngưỡng, tuyến phê duyệt và thẩm quyền phải do policy của môi trường xác định.

### 3.2. Không chỉ nhìn tên role

Tên “read-only” hoặc “diagnostics” chưa đủ để kết luận rủi ro thấp. Role có thể đọc secret, tải dữ liệu, mở shell, sử dụng công cụ mở rộng hoặc tác động gián tiếp tới tài nguyên khác.

Người đánh giá cần hiểu quyền hiệu lực và giới hạn đã kiểm chứng tại đích. Nếu chưa xác minh role, phải giữ rõ phần chưa biết thay vì suy từ tên hiển thị trong PAM.

### 3.3. Phân biệt rủi ro với tính khẩn cấp

Sự cố đang xảy ra có thể làm nhu cầu truy cập cấp bách hơn, nhưng không tự làm quyền rộng trở nên ít rủi ro hơn.

Workflow khẩn cấp cần tuyến quyết định, phạm vi tối thiểu, thời hạn và bằng chứng phù hợp. Nếu policy cho phép break-glass không chờ phê duyệt trước, phải ghi nhận đúng đây là đường khẩn cấp có điều kiện và hậu kiểm; không ghi ngược rằng yêu cầu đã được duyệt trước khi sử dụng.

## 4. Ai có quyền phê duyệt bảo mật?

### 4.1. Thẩm quyền phải gắn với phạm vi

Người phê duyệt có thể là chuyên viên bảo mật, người trực được ủy quyền hoặc một vai trò khác được policy chỉ định. Chức danh hoặc việc thuộc một nhóm chat không tự tạo thẩm quyền cho mọi target và mọi mức rủi ro.

Cần xác định:

- Phạm vi tài nguyên và loại quyết định được duyệt.
- Mức rủi ro hoặc loại ngoại lệ trong thẩm quyền.
- Thời gian hiệu lực của ủy quyền.
- Điều kiện xác thực và sử dụng tài khoản phê duyệt.
- Cách xử lý khi người duyệt vắng mặt hoặc mất quyền.
- Ai có thể nhận rủi ro tồn dư nếu vượt giới hạn thẩm quyền hiện tại.

Việc chuyển tuyến cần đưa yêu cầu tới người có thẩm quyền phù hợp. Không tự coi im lặng, hết SLA hoặc người trực chưa trả lời là đồng ý.

### 4.2. Phân tách nhiệm vụ

Một số yêu cầu cần tách người yêu cầu, owner, người duyệt bảo mật và người thực hiện. Các ràng buộc này phải được áp dụng theo danh tính thực tế, không chỉ theo tên tài khoản.

Một người dùng hai tài khoản để yêu cầu và phê duyệt vẫn có thể vi phạm phân tách nhiệm vụ. Nếu policy yêu cầu hai người độc lập, hai lần bấm duyệt của cùng một người không đáp ứng yêu cầu đó.

Với phê duyệt nhiều người, cần xác định cách xử lý thành viên thuộc nhiều nhóm. Một người có được tính cho hai bước hay không phải là quy tắc rõ ràng, không phải hệ quả tình cờ của membership.

### 4.3. Ủy quyền và thay người

Ủy quyền phải có người giao, người nhận, phạm vi, thời hạn và bằng chứng. Người nhận không nên có khả năng tự mở rộng phạm vi bằng cách đổi nhóm hoặc sửa workflow.

Tại thời điểm chấp nhận quyết định, hệ thống cần kiểm tra thẩm quyền theo policy. Nếu thẩm quyền thay đổi sau khi phê duyệt, việc giữ hay vô hiệu quyết định cũ cần quy tắc cụ thể. Không mặc định mọi thay đổi nhân sự đều giữ nguyên hoặc hủy mọi phê duyệt.

## 5. Hồ sơ yêu cầu cần có gì?

Một hồ sơ tốt giúp người duyệt trả lời được “ai cần làm gì, ở đâu, bằng cách nào, trong bao lâu và bằng chứng nào sẽ tồn tại”.

| Nhóm thông tin | Nội dung cần làm rõ |
|---|---|
| Chủ thể | Danh tính cá nhân hoặc workload, đơn vị và người bảo trợ nếu có |
| Nhu cầu | Mục tiêu công việc, ticket và ảnh hưởng nếu không thực hiện |
| Target | Định danh ổn định, môi trường, owner và tập tài nguyên cụ thể |
| Quyền | Role, tác vụ dự kiến, mức đặc quyền và khả năng mở rộng quyền |
| Thời gian | Cửa sổ được phép, thời lượng tối đa và hạn dùng quyết định |
| Đường truy cập | Client, gateway, giao thức và đường trực tiếp liên quan |
| Credential | Nguồn credential, có xuất secret hay không và vòng đời |
| Phiên | Cách giám sát, ghi nhận, can thiệp và kết thúc |
| Dữ liệu | Khả năng xem, tải, chuyển hoặc ghi dữ liệu nhạy cảm |
| Thu hồi | Ai thu hồi, ở lớp nào và cách xác nhận kết quả |
| Ngoại lệ | Điều kiện thiếu, biện pháp bù trừ, thẩm quyền và thời hạn |

Thông tin không cần dài nhưng phải đủ để quyết định. “Cần quyền admin để sửa lỗi” chưa cho biết target, tác vụ, phạm vi hay lý do không thể dùng quyền hẹp hơn.

Người duyệt cần có nguồn kiểm chứng phù hợp. Một liên kết ticket giúp bổ sung bối cảnh, nhưng nội dung ticket có thể thay đổi; các dữ kiện quyết định phải được lưu hoặc tham chiếu theo phiên bản có thể đối chiếu.

Không đưa mật khẩu, private key hoặc token vào hồ sơ phê duyệt. Người duyệt cần biết cơ chế và phạm vi credential, không cần sở hữu secret để đánh giá.

## 6. Đánh giá bảo mật một yêu cầu PAM

### 6.1. Xác minh chủ thể và trách nhiệm

Cần biết ai sẽ sử dụng quyền và ai chịu trách nhiệm. Với nhà cung cấp, xác định người dùng riêng, người bảo trợ và thời hạn quan hệ hỗ trợ.

Với workload, đánh giá danh tính máy, nguồn thực thi và vòng đời credential tương ứng. Không mặc định một luồng phê duyệt dành cho người dùng tương tác phù hợp với mọi tác vụ tự động.

Nếu người yêu cầu thay mặt người khác, hồ sơ phải phân biệt người lập yêu cầu và chủ thể nhận quyền.

### 6.2. Kiểm tra least privilege và JEA

Các câu hỏi cần trả lời gồm:

- Tác vụ có cần quyền quản trị đầy đủ không?
- Có role hẹp hơn hoặc endpoint thực thi tác vụ cụ thể không?
- Quyền tại đích có tương ứng với role được chọn trong PAM không?
- Có khả năng tạo tài khoản, sửa policy hoặc lấy credential khác không?
- Có đường sang tài nguyên khác từ target được cấp không?

Một quyết định “chỉ được chẩn đoán” không tạo JEA nếu tài khoản đích vẫn có toàn quyền và không có lớp thực thi giới hạn tác vụ.

### 6.3. Kiểm tra JIT và thời gian

Cần tách:

1. Khoảng thời gian quyết định phê duyệt còn dùng được.
2. Cửa sổ mà phiên hoặc quyền có thể được cấp.
3. Thời gian tối đa của mỗi phiên hoặc grant.
4. Số lần dùng quyết định nếu có giới hạn.

Phê duyệt có thể hết hạn trước khi người dùng mở phiên. Một phiên khởi tạo muộn không nên tự được kéo dài qua giới hạn tuyệt đối nếu policy không cho phép.

Gia hạn cần đánh giá theo workflow đã định. Không sửa thời điểm kết thúc của quyết định cũ mà làm mất dấu phạm vi đã được duyệt ban đầu.

### 6.4. Kiểm tra đường truy cập và credential

Cần hiểu người dùng có đi qua gateway được quản lý không, target có nhận truy cập trực tiếp không, credential có thể dùng lại ngoài PAM không và tài khoản nào có hiệu lực tại đích.

Vault có thể giảm phơi lộ secret, nhưng “secret nằm trong vault” không tự chứng minh:

- Người dùng không có bản sao từ nguồn khác.
- Gateway chỉ có quyền tới đúng target.
- Credential hết hiệu lực khi phiên kết thúc.
- Mọi cách sử dụng tài khoản đích đều được ghi nhận.

Nếu cần rotation hoặc credential tạm thời, phải xác định phạm vi và dependency. Quyết định bảo mật không được bỏ qua tác động tới dịch vụ đang sử dụng credential.

### 6.5. Kiểm tra bằng chứng và khả năng can thiệp

Recording, log PAM và log tại đích có khả năng quan sát khác nhau. Cần biết giao thức, kênh phụ và tác vụ nào được hỗ trợ, nguồn nào ghi nhận hành động và giới hạn còn lại.

Nếu policy bắt buộc ghi nhận một loại hoạt động, cần kiểm tra khả năng đó trước khi cấp. Một ghi chú “bắt buộc recording” chỉ có giá trị thực thi khi hệ thống có thể kiểm tra và áp dụng điều kiện tương ứng.

Kết thúc phiên tại gateway có thể chặn tương tác nhưng không đảo ngược thay đổi hoặc tự hủy mọi tác vụ nền tại đích. Kế hoạch thu hồi phải nêu rõ kết quả cần đạt ở từng lớp.

## 7. Kết quả quyết định và ý nghĩa

| Kết quả logic | Ý nghĩa | Hệ quả đối với cấp quyền |
|---|---|---|
| Yêu cầu bổ sung | Chưa đủ dữ liệu để kết luận | Chưa đáp ứng điều kiện phê duyệt |
| Từ chối | Yêu cầu không được chấp nhận trong phạm vi đánh giá | Không cấp từ yêu cầu này |
| Chấp thuận | Phạm vi đã nêu được chấp nhận theo policy | Vẫn phải qua kiểm tra trước khi cấp |
| Chấp thuận có điều kiện | Chỉ chấp nhận khi các điều kiện xác định đạt | Chưa cấp nếu điều kiện còn thiếu |
| Chuyển tuyến | Vượt thẩm quyền hoặc cần vai trò khác | Chưa coi là phê duyệt hoàn tất |

Tên trạng thái cụ thể phụ thuộc hệ thống. Điều cần giữ là ý nghĩa nghiệp vụ và điều kiện thực thi.

“Không phản đối” trong một cuộc trao đổi không nhất thiết là một quyết định hợp lệ. Workflow cần xác định dạng bằng chứng và kênh nào được chấp nhận.

Một quyết định từ chối cần có lý do đủ để xử lý tiếp, nhưng không cần tiết lộ dữ liệu nhạy cảm không liên quan. Yêu cầu sửa đổi có thể được tạo phiên bản mới; không xóa quyết định cũ để khiến lịch sử chỉ còn kết quả chấp thuận.

## 8. Phê duyệt có điều kiện phải có cách thực thi

Ví dụ một người duyệt ghi:

> Chấp thuận nếu chỉ dùng role chẩn đoán, không xuất credential, không truyền tệp và phiên được ghi nhận theo policy.

Bốn điều kiện cần được chuyển thành các kiểm tra hoặc cấu hình cụ thể:

| Điều kiện | Lớp thực thi hoặc bằng chứng phù hợp |
|---|---|
| Role chẩn đoán | Mapping role và quyền hiệu lực tại đích đã kiểm chứng |
| Không xuất credential | Luồng broker/vault và quyền truy xuất secret |
| Không truyền tệp | Khả năng hạn chế kênh truyền của gateway, giao thức và target |
| Ghi nhận phiên | Trạng thái cơ chế ghi nhận và liên kết session theo phạm vi hỗ trợ |

Nếu một điều kiện không thể thực thi trong kiến trúc hiện tại, không được tự đánh dấu đã đạt chỉ vì người dùng đồng ý tuân thủ.

Có thể cần thay cách thực hiện, thu hẹp quyền, chọn công cụ khác hoặc xử lý ngoại lệ đúng thẩm quyền. Biện pháp tổ chức có thể có vai trò theo policy, nhưng phải ghi đúng giới hạn của nó.

Các điều kiện sau khi cấp cũng cần owner. Chẳng hạn, yêu cầu rà soát sau phiên là nghĩa vụ hậu kiểm; nó không thay một điều kiện bắt buộc phải đạt trước khi mở phiên.

## 9. Gắn quyết định với đúng phạm vi

### 9.1. Dùng một bản yêu cầu có phiên bản

Quyết định cần liên kết với các trường đã được duyệt, chẳng hạn:

~~~text
Request ID và phiên bản
Chủ thể nhận quyền
Target hoặc tập target đã xác định
Role và tác vụ
Phương thức truy cập
Cửa sổ và thời lượng
Điều kiện bắt buộc
Policy áp dụng
Quyết định, người duyệt và thẩm quyền
~~~

Một ID ticket duy nhất không đủ nếu nội dung có thể được đổi từ “chẩn đoán A” sang “quản trị toàn bộ cụm” mà vẫn dùng chữ ký cũ.

Nếu target là nhóm động, cần xác định semantics: duyệt tập thành viên tại thời điểm nào hay cho phép membership biến đổi trong giới hạn policy nào. Không ngầm để thay đổi nhóm mở rộng phạm vi đã duyệt.

### 9.2. Xác định thay đổi nào làm mất hiệu lực

Những thay đổi thường cần đánh giá lại gồm:

- Đổi chủ thể nhận quyền.
- Thêm target hoặc chuyển môi trường.
- Tăng mức đặc quyền hay mở thêm tác vụ.
- Gia hạn cửa sổ, thời lượng hoặc số lần sử dụng.
- Cho xuất credential hoặc mở kênh truyền dữ liệu mới.
- Thay đường truy cập hoặc làm mất điều kiện giám sát.
- Thay ngoại lệ hoặc biện pháp bù trừ.

Chính sách có thể cho phép một số sửa đổi hành chính không ảnh hưởng quyết định. Ranh giới phải rõ, có lịch sử và không do người yêu cầu tùy ý xác định.

### 9.3. Kiểm tra lại tại thời điểm cấp

Ngay trước khi cấp, hệ thống cần xác minh các điều kiện hiện tại theo policy: yêu cầu còn hiệu lực, các phê duyệt bắt buộc còn dùng được, chủ thể chưa mất quyền và các kiểm soát cần thiết đang đáp ứng.

Không chỉ tin một cờ “approved” được lưu từ trước.

Việc kiểm tra và cấp cần có cơ chế xử lý thay đổi đồng thời phù hợp, ví dụ phiên bản yêu cầu, cập nhật có điều kiện hoặc giao dịch ở nơi hệ thống hỗ trợ. Một sơ đồ workflow không tự loại bỏ khoảng thời gian giữa kiểm tra và thực thi.

## 10. Trạng thái workflow và cạnh tranh quyết định

Một mô hình logic có thể là:

~~~text
DRAFT
  → SUBMITTED
  → IN_REVIEW
  → NEEDS_INFORMATION → SUBMITTED với phiên bản phù hợp
  → REJECTED
  → APPROVED_PENDING_CONTROLS
  → READY_TO_GRANT
  → GRANTED
  → CLOSED

Các nhánh vòng đời khác:
  CANCELLED / EXPIRED / REVOKED
~~~

Đây là mô hình minh họa, không yêu cầu mọi sản phẩm có đúng các trạng thái này.

Cần tách trạng thái phê duyệt khỏi trạng thái quyền và phiên. Một yêu cầu có thể đã duyệt nhưng chưa cấp; một grant đã bị thu hồi có thể còn hành động kết thúc tại đích đang chờ xác nhận.

Với nhiều người duyệt, workflow phải định nghĩa:

- Cần tất cả vai trò hay chỉ một số lượng quyết định hợp lệ.
- Người duyệt có được trùng nhau không.
- Quyết định từ chối có chặn quy trình hay chuyển tuyến.
- Quyết định đến muộn được xử lý thế nào.
- Phiên bản yêu cầu nào là đối tượng của mỗi quyết định.
- Điều gì xảy ra nếu người yêu cầu hủy ngay khi bước cấp bắt đầu.

Ví dụ, trong một policy yêu cầu cả owner và security cùng chấp thuận, một quyết định từ chối hợp lệ phải ngăn yêu cầu đạt trạng thái sẵn sàng cấp. Không áp dụng quy tắc “lần cập nhật cuối thắng” nếu nó cho một lượt chấp thuận ghi đè từ chối trái workflow.

Retry cũng cần được xử lý. Nhận cùng một thông điệp phê duyệt hai lần không được tính thành hai người duyệt hoặc tạo hai grant ngoài ý muốn.

## 11. Ví dụ xuyên suốt: hỗ trợ chẩn đoán production

### 11.1. Yêu cầu ban đầu

Nhà cung cấp cần hỗ trợ sự cố trên app-prod-a. Người bảo trợ lập yêu cầu:

- Chủ thể: kỹ sư đối tác có danh tính riêng.
- Mục tiêu: xem trạng thái dịch vụ và thu thập thông tin chẩn đoán.
- Target: chỉ app-prod-a.
- Role: đề nghị quyền quản trị đầy đủ trong 90 phút.
- Đường truy cập: qua PAM gateway.
- Credential: không có nhu cầu xuất secret.
- Dữ liệu: có thể cần lấy một phần log ra khỏi máy chủ.

Owner dịch vụ xác nhận nhu cầu, nhưng điều đó chưa giải quyết phạm vi đặc quyền và luồng dữ liệu.

### 11.2. Đánh giá bảo mật

Người duyệt xác định:

1. Tác vụ đã mô tả có thể dùng role chẩn đoán hẹp hơn nếu khả năng đó được xác minh.
2. Thời lượng cần khớp kế hoạch hỗ trợ, không tự dùng mức tối đa theo thói quen.
3. Việc lấy log ra ngoài cần xác định nội dung, nơi nhận và đường chuyển phù hợp.
4. Không cần xuất credential cho kỹ sư.
5. Phiên cần có liên kết với người dùng, target và bằng chứng theo policy.
6. Quyền đối tác phải có thời hạn và người bảo trợ chịu trách nhiệm.

Người duyệt yêu cầu sửa phạm vi, không tự sửa yêu cầu rồi coi người yêu cầu đã chấp nhận mọi thay đổi.

### 11.3. Phiên bản được chấp thuận

Yêu cầu phiên bản mới chỉ cho role chẩn đoán, cửa sổ và thời lượng đã thống nhất. Log cần lấy được xử lý qua một đường đã duyệt với phạm vi dữ liệu cụ thể. Quyền truyền tệp tùy ý không được mở trong phiên này.

Ví dụ hồ sơ quyết định:

~~~yaml
# Mã giả minh họa dữ liệu; không phải cấu hình sản phẩm.
request_id: PAM-EXAMPLE-042
request_version: 3
beneficiary: vendor-engineer-17
target_id: app-prod-a
role_id: diagnostics-verified

security_decision:
  result: approve_with_conditions
  reviewer: security-reviewer-09
  authority_scope: production-vendor-diagnostics
  policy_version: pam-policy-example-v5
  reason: "Phạm vi chẩn đoán đã thu hẹp theo công việc."
  conditions:
    - verified_diagnostics_role
    - no_credential_export
    - approved_session_observability
    - no_unapproved_data_transfer

validity:
  approved_window: agreed_support_window
  max_session_minutes: 30
  permitted_uses: 1
  reapproval_on_scope_change: true
~~~

Giá trị cửa sổ dạng tên trong ví dụ phải được thay bằng giới hạn thời gian rõ trong triển khai. Mô hình này chỉ minh họa những thông tin cần ràng buộc.

### 11.4. Trước và trong khi cấp

Hệ thống kiểm tra phiên bản yêu cầu, quyết định của owner, quyết định bảo mật và các điều kiện bắt buộc. Nếu role hoặc cơ chế giám sát chưa xác minh được, yêu cầu chưa đủ điều kiện cấp dù đã có quyết định chấp thuận có điều kiện.

Khi phiên mở, lưu liên kết tới grant, account tại đích và session. Nếu phát sinh nhu cầu sửa cấu hình hoặc dùng target khác, phải xử lý thay đổi phạm vi theo workflow, không dựa vào chữ ký cho công việc chẩn đoán.

### 11.5. Kết thúc

Khi công việc hết hạn, kết thúc quyền và phiên theo thiết kế; ghi riêng những phần còn cần xác nhận tại đích. Xử lý credential hoặc grant theo vòng đời đã định, rồi lưu kết quả hậu kiểm.

Đóng ticket hỗ trợ không tự chứng minh mọi quyền và session đã được thu hồi. Hồ sơ cần cho thấy kết quả tương ứng hoặc trạng thái còn chờ xử lý.

## 12. Ngoại lệ, chấp nhận rủi ro và break-glass

### 12.1. Ngoại lệ không đồng nghĩa bỏ mọi điều kiện

Giả sử hệ thống chưa hỗ trợ một yêu cầu giám sát bắt buộc. Người duyệt không nên ghi “đã đạt” để giúp công việc tiếp tục.

Một ngoại lệ hợp lệ cần làm rõ:

- Yêu cầu kiểm soát nào chưa đáp ứng.
- Vì sao cần ngoại lệ và trong phạm vi nào.
- Rủi ro còn lại.
- Biện pháp bù trừ có thể thực thi.
- Người có thẩm quyền chấp nhận.
- Thời hạn và điều kiện kết thúc.
- Owner xử lý phần thiếu và bằng chứng cần lưu.

Một người được quyền duyệt truy cập thông thường chưa chắc được quyền chấp nhận loại ngoại lệ này. Có trường hợp phải chuyển tới owner rủi ro hoặc cấp thẩm quyền khác theo policy.

### 12.2. Không sửa lịch sử để hợp thức hóa

Nếu truy cập đã diễn ra trước khi có phê duyệt bắt buộc, hồ sơ phải phản ánh đúng thời điểm và quy trình thực tế.

Hậu kiểm có thể kết luận về việc sử dụng quyền hoặc xử lý vi phạm quy trình. Nó không biến một quyết định sau sự kiện thành phê duyệt trước sự kiện.

### 12.3. Tách lỗi workflow khỏi đường khẩn cấp

Sự cố hệ thống phê duyệt cần có hành vi được thiết kế: không cấp mới theo luồng thường nếu điều kiện bắt buộc chưa đạt, hoặc sử dụng đường khẩn cấp đã được ủy quyền riêng khi đủ điều kiện.

Đường khẩn cấp cần phạm vi, bằng chứng và xử lý sau sử dụng. Không dùng việc hệ thống duyệt bị lỗi làm lý do mặc định cấp quyền rộng không thời hạn.

## 13. Bảo vệ bản thân cơ chế phê duyệt

Workflow phê duyệt là một phần của hệ thống đặc quyền. Cần xem xét:

- Danh tính và quyền của người duyệt.
- Quyền sửa policy, workflow, nhóm approver và mapping target.
- Tài khoản dịch vụ thực hiện bước cấp quyền.
- Kênh nhận thông báo và nơi thực hiện quyết định.
- Cơ chế bảo vệ tính toàn vẹn của bản yêu cầu.
- Lịch sử thay đổi và quyền truy cập bằng chứng.

Thông báo email hoặc chat có thể giúp người duyệt biết có yêu cầu mới. Tuy nhiên, việc nhận được thông báo không chứng minh người đó có quyền quyết định.

Nếu hỗ trợ phê duyệt từ một kênh tích hợp, cần xác thực người thực hiện, kiểm tra thẩm quyền và ràng buộc hành động với đúng request/version. Một URL không hết hạn hoặc một phản hồi không gắn danh tính có thể làm suy giảm cơ chế.

Người yêu cầu không được tự thay approver hoặc sửa policy để bỏ bước bắt buộc. Các quyền quản trị workflow cũng cần được quản lý bằng least privilege và có quy trách nhiệm.

## 14. Bằng chứng để kiểm toán và ứng phó sự cố

Một hồ sơ có thể đối chiếu nên liên kết các chuỗi sau:

~~~text
Yêu cầu và phiên bản
  → policy áp dụng
  → các quyết định và thẩm quyền
  → điều kiện đã kiểm tra
  → grant hoặc credential được cấp
  → session và tài khoản tại đích
  → hoạt động quan sát được
  → hết hạn, thu hồi và kết quả tại đích
~~~

Bằng chứng cần trả lời được:

- Ai yêu cầu và ai thực sự nhận quyền?
- Ai duyệt, với thẩm quyền nào, vào thời điểm nào?
- Phạm vi nào đã được duyệt?
- Các điều kiện nào được kiểm tra trước khi cấp?
- Quyền thực tế có khớp phạm vi đó không?
- Có thay đổi, gia hạn, hủy hoặc ngoại lệ nào?
- Thu hồi đạt kết quả ở lớp nào và còn phần nào chưa xác minh?

Log cần được bảo vệ theo mô hình tin cậy và vòng đời dữ liệu của tổ chức. Người có quyền duyệt không nên mặc nhiên có khả năng sửa dấu vết quyết định của mình.

Không cần ghi secret hoặc toàn bộ dữ liệu phiên vào bản quyết định. Hồ sơ có thể dùng tham chiếu tới kho bằng chứng được kiểm soát, miễn là còn truy xuất được trong thời hạn cần thiết và giữ được liên kết.

Trong điều tra, chữ ký chấp thuận chỉ chứng minh một quyết định trong phạm vi đã ghi. Muốn biết người dùng thực hiện điều gì vẫn cần bằng chứng từ phiên, target và các nguồn liên quan.

## 15. Kiểm chứng workflow theo tình huống

Khi triển khai một workflow thực tế, những tình huống sau giúp xác định thiết kế có thực thi đúng ý định hay không:

| Tình huống | Kết quả cần có theo policy |
|---|---|
| Chủ thể không có thẩm quyền thử duyệt | Quyết định không được chấp nhận |
| Người yêu cầu tự duyệt bằng tài khoản khác | Không vượt ràng buộc phân tách nhiệm vụ |
| Thay target sau khi được duyệt | Quyết định cũ không cấp cho phạm vi mới trái policy |
| Role tăng quyền sau phê duyệt | Có đánh giá lại hoặc kiểm soát phiên bản phù hợp |
| Thiếu một vai trò phê duyệt bắt buộc | Chưa chuyển sang sẵn sàng cấp |
| Một approver từ chối trong workflow yêu cầu tất cả chấp thuận | Không cấp từ các chữ ký còn lại |
| Cùng quyết định được gửi lại | Không đếm thêm người duyệt hoặc cấp trùng |
| Điều kiện recording bắt buộc chưa đạt | Không coi là đủ điều kiện mở phiên |
| Phê duyệt hết hạn trước khi sử dụng | Không cấp từ quyết định đã hết hiệu lực |
| Người nhận quyền mất entitlement trước khi cấp | Kiểm tra lại và xử lý theo policy hiện hành |
| Hủy yêu cầu đồng thời với bước cấp | Có kết quả nhất quán và bằng chứng, xử lý grant nếu đã tạo |
| Người duyệt mất thẩm quyền trong lúc xử lý | Áp dụng quy tắc hiệu lực đã xác định |
| Gia hạn ngoài cửa sổ đã duyệt | Qua quy trình thay đổi hoặc phê duyệt mới cần thiết |
| Thu hồi khi phiên đang hoạt động | Có kết quả ở từng lớp, không chỉ thay cờ trạng thái |
| Dùng break-glass | Ghi đúng đường khẩn cấp và yêu cầu hậu kiểm |

Các phép kiểm chứng cần dùng dữ liệu và tài nguyên thuộc phạm vi cho phép. Không cần cấp quyền production nguy hiểm chỉ để chứng minh một nhánh workflow.

## 16. Chất lượng vận hành của bước phê duyệt

### 16.1. Giảm duyệt hình thức

Nếu approver nhận quá nhiều yêu cầu giống nhau mà thiếu dữ liệu, việc duyệt có thể trở thành thao tác theo thói quen.

Có thể cải thiện bằng cách:

- Chuẩn hóa dữ liệu tối thiểu của yêu cầu.
- Hiển thị target, quyền, thời hạn và điểm khác biệt so với luồng chuẩn.
- Dùng policy cho trường hợp thường lệ đã được kiểm chứng.
- Chuyển các trường hợp có rủi ro hoặc ngoại lệ tới đúng người.
- Yêu cầu lý do cụ thể cho quyết định vượt phạm vi thông thường.

Tự động hóa cần thể hiện đúng đây là quyết định dựa trên policy nào. Không gắn tên một người làm approver nếu người đó không thực hiện quyết định hoặc không có cơ chế ủy quyền tương ứng.

### 16.2. Dùng chỉ số có ngữ cảnh

Những chỉ số có thể hữu ích:

- Thời gian chờ theo loại yêu cầu và tuyến phê duyệt.
- Tỷ lệ yêu cầu cần bổ sung vì thiếu phạm vi.
- Số quyết định hết hạn trước khi được sử dụng.
- Số yêu cầu thay đổi phạm vi sau khi duyệt.
- Số grant không liên kết được với quyết định hợp lệ.
- Số ngoại lệ quá hạn hoặc chưa đóng.
- Tỷ lệ điều kiện bắt buộc có bằng chứng thực thi.
- Số lần cấp trùng hoặc xử lý cạnh tranh không nhất quán.

Thời gian duyệt ngắn không tự chứng minh quyết định tốt; tỷ lệ từ chối cao cũng không tự chứng minh kiểm soát hiệu quả. Cần xem chất lượng hồ sơ và kết quả cấp quyền thực tế.

## 17. Những sai lầm cần tránh

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Có chữ ký security là đủ mọi bước | Bỏ qua owner hoặc phê duyệt thay đổi bắt buộc | Xác định rõ các quyết định cần thiết |
| Duyệt “quyền admin” không nêu target | Phạm vi sử dụng không rõ | Ràng buộc chủ thể, target, role và thời gian |
| Approver chỉ xem tên role | Bỏ sót quyền hiệu lực và đường mở rộng | Dùng dữ liệu role đã kiểm chứng |
| Điều kiện chỉ tồn tại trong ghi chú | Có thể cấp quyền dù chưa đáp ứng | Gắn điều kiện với kiểm tra và lớp thực thi |
| Sửa yêu cầu nhưng giữ chữ ký cũ | Quyết định không còn đúng đối tượng | Phiên bản hóa và đánh giá lại theo policy |
| Đếm hai tài khoản thành hai người | Vượt phân tách nhiệm vụ | Ràng buộc theo danh tính và vai trò |
| Hết thời gian chờ là tự đồng ý | Cấp quyền khi chưa có quyết định bắt buộc | Chuyển tuyến hoặc xử lý hết hạn rõ ràng |
| Chấp thuận là coi grant đã tồn tại | Sai trạng thái và khó thu hồi | Tách quyết định khỏi bước cấp |
| Xóa grant là coi mọi phiên đã dừng | Hoạt động tại đích có thể còn | Xác nhận thu hồi theo từng lớp |
| Ngoại lệ không có thời hạn | Rủi ro tồn dư kéo dài | Gắn owner, hạn và điều kiện đóng |
| Hậu kiểm được ghi thành phê duyệt trước | Mất tính trung thực của lịch sử | Lưu đúng thời điểm và loại quyết định |
| Chỉ đo tốc độ duyệt | Khuyến khích duyệt vội hoặc hình thức | Đo thêm chất lượng và kết quả thực thi |

## 18. Tự thực hành trên một yêu cầu

Chọn một tác vụ quản trị giả định trong phạm vi PAM, chẳng hạn đối tác chẩn đoán một dịch vụ production. Viết một hồ sơ ngắn trả lời:

1. Chủ thể nào nhận quyền, target nào và nhu cầu gì?
2. Quyền hẹp nhất đủ cho tác vụ là gì, đã kiểm chứng bằng cách nào?
3. Vì sao yêu cầu cần hoặc không cần security approval theo policy giả định?
4. Ai có thẩm quyền, ai phải độc lập và ai nhận rủi ro nếu có ngoại lệ?
5. Quyết định có hiệu lực trong khoảng nào và cho bao nhiêu lần sử dụng?
6. Điều kiện nào phải đạt trước khi cấp và thành phần nào thực thi?
7. Thay đổi nào làm yêu cầu phải được duyệt lại?
8. Bằng chứng nào liên kết quyết định với grant, phiên và kết quả thu hồi?

Một hồ sơ đạt mục tiêu khi người vận hành có thể cấp đúng phạm vi mà không phải tự đoán ý người duyệt, còn người kiểm tra có thể đối chiếu quyết định với những gì hệ thống thực sự đã làm.
