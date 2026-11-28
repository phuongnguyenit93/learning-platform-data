# Vault access policy

**Vault access policy** là tập quy tắc xác định một danh tính được thực hiện thao tác nào trên đối tượng nào trong vault, dưới những điều kiện nào. Trong Privileged Access Management (PAM), policy bảo vệ credential của tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm, đồng thời kiểm soát các khả năng cấp phát, sử dụng, thay đổi và quản lý credential đó.

Bài học thuộc chương **Vault**, kết hợp kiểm kê quyền, least privilege, truy cập đúng lúc (JIT), giới hạn thao tác, luân chuyển credential, giám sát phiên và lưu bằng chứng phục vụ kiểm toán, ứng phó sự cố. Trọng tâm là thiết kế quyền có thể giải thích và kiểm chứng, phù hợp với cả người quản trị lẫn workload.

Một policy chỉ cho phép đọc một secret vẫn có thể dẫn tới quyền quản trị rất lớn nếu secret đó đăng nhập được bằng tài khoản toàn quyền. Vì vậy, thiết kế phải xét cả quyền ở vault và đặc quyền thực tế mà credential mở ra tại hệ thống đích.

Sau bài học, bạn có thể:

- Phân biệt xác thực, phân quyền ở vault và phân quyền tại tài nguyên đích.
- Mô hình hóa policy theo chủ thể, tài nguyên, thao tác và điều kiện.
- Tách quyền đọc, dùng, cấp phát, luân chuyển và quản trị policy.
- Nhận diện quyền hiệu lực, quyền gián tiếp và giới hạn của việc thu hồi.
- Xây dựng ví dụ chính sách cùng các tình huống kiểm chứng và bằng chứng cần lưu.

## 1. Policy nằm ở đâu trong luồng truy cập?

Một luồng truy cập credential có thể được mô tả như sau:

```text
Danh tính → Xác thực → Ngữ cảnh yêu cầu → Đánh giá policy
                                            ↓
                                   Cho phép hoặc từ chối
                                            ↓
                              Đọc, dùng hoặc cấp credential
                                            ↓
                               Xác thực và phân quyền ở đích
```

Ba quyết định cần phân biệt:

| Quyết định | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Xác thực | Ai hoặc workload nào đang gửi yêu cầu? | Người dùng qua IdP; workload có bằng chứng danh tính hợp lệ |
| Phân quyền vault | Danh tính đó được làm gì với đối tượng vault? | Chỉ cấp credential của một ứng dụng production |
| Phân quyền ở đích | Credential hoặc danh tính được cấp thực sự làm được gì? | Chỉ đọc một tập dữ liệu, không quản trị toàn cơ sở dữ liệu |

MFA giúp tăng độ tin cậy khi xác thực người dùng nhưng không tự thu hẹp phạm vi secret mà người đó được đọc. Ngược lại, policy vault rất hẹp cũng không sửa được tài khoản đích đang có quá nhiều quyền.

Session proxy có thể giúp sử dụng credential mà người dùng không cần nhận giá trị trực tiếp, nếu giải pháp hỗ trợ. Khả năng đó vẫn cần policy cho việc mở phiên, quyền ở đích và cơ chế ghi nhận hoạt động; không phải cứ đặt secret trong vault là mọi phiên dùng secret đều được giám sát.

## 2. Bốn thành phần của một quy tắc truy cập

Một mô hình tư duy hữu ích là:

```text
Chủ thể + Tài nguyên + Thao tác + Điều kiện → Quyết định
```

### 2.1 Chủ thể: danh tính nào được xét?

Chủ thể có thể là người dùng, nhóm, workload, session broker hoặc worker luân chuyển. Cần dùng danh tính đã được xác thực và ánh xạ đáng tin cậy, thay vì một tên người dùng do client tự gửi.

Những thuộc tính thường được xem xét gồm định danh ổn định, nhóm, loại danh tính, môi trường workload và nguồn xác thực. Một claim hoặc nhãn chỉ có giá trị cho phân quyền khi hệ thống biết ai có thể phát hành hoặc thay đổi nó.

Ví dụ, policy cho phép mọi workload có nhãn `environment=production` là nguy hiểm nếu chính workload có thể tự đặt nhãn đó. Nguồn thuộc tính và quyền sửa thuộc tính phải nằm trong mô hình tin cậy.

### 2.2 Tài nguyên: đối tượng nào được bảo vệ?

Tài nguyên có thể là một secret, phiên bản, metadata, role cấp credential động, folder, namespace, cấu hình xác thực hoặc bản policy.

Một tham chiếu cần đủ ngữ cảnh để tránh nhầm môi trường:

```text
Vault: primary-pam
Namespace: prod-payments
Đối tượng: databases/orders/application-runtime
```

Tên trên chỉ minh họa cấu trúc, không phải cú pháp bắt buộc. Nếu sản phẩm có ID ổn định, cần hiểu cách ID và đường dẫn được dùng khi đổi tên hoặc di chuyển đối tượng.

### 2.3 Thao tác: quyền gì được cấp?

Không nên gộp tất cả thành một quyền “access”. Đọc metadata, lấy giá trị secret, cấp credential động, sử dụng qua broker và thay policy có hậu quả khác nhau.

### 2.4 Điều kiện: quyền có hiệu lực khi nào?

Điều kiện có thể liên quan đến thời gian, phê duyệt, MFA, tài nguyên đích hoặc ngữ cảnh workload. Chỉ sử dụng điều kiện mà hệ thống có thể thu thập, kiểm chứng và thực thi.

Địa chỉ nguồn hoặc vùng mạng có thể hỗ trợ hạn chế nhưng không thay thế danh tính. Nhiều chủ thể có thể dùng chung một địa chỉ NAT; địa chỉ không chứng minh yêu cầu đến từ đúng ứng dụng.

## 3. Tách các nhóm thao tác có rủi ro khác nhau

| Nhóm thao tác | Ý nghĩa | Điểm cần kiểm soát |
|---|---|---|
| Liệt kê, tìm kiếm, đọc metadata | Khám phá đối tượng và thông tin mô tả | Có thể làm lộ tên tài khoản, endpoint và cấu trúc hạ tầng |
| Đọc giá trị hiện tại | Nhận credential hoặc secret | Giá trị có thể bị sao chép và sử dụng ngoài vault |
| Đọc phiên bản cũ | Lấy dữ liệu trong lịch sử | Credential cũ hoặc thông tin nhạy cảm có thể vẫn có giá trị |
| Dùng qua broker | Cho phép một dịch vụ dùng credential thay người yêu cầu | Chỉ có ý nghĩa tách khỏi đọc nếu mọi đường lấy giá trị đều được kiểm soát |
| Cấp credential động | Tạo danh tính, token hoặc credential theo role | Role cấp phát phải giới hạn quyền, tài nguyên và vòng đời |
| Tạo hoặc cập nhật đối tượng | Thêm hoặc đổi dữ liệu, metadata | Có thể thay tham chiếu tài nguyên hoặc đánh lừa bên sử dụng nếu không giới hạn |
| Luân chuyển | Thay credential tại đích và cập nhật trạng thái quản lý | Cần quyền đúng trên cả vault, workflow và tài nguyên đích |
| Xóa, khôi phục, hủy phiên bản | Tác động tới dữ liệu và khả năng phục hồi | Có thể gây mất khả năng truy cập hoặc làm credential cũ xuất hiện lại |
| Quản lý policy và danh tính | Thay đổi người được truy cập | Có thể dẫn tới tự cấp quyền và truy cập secret gián tiếp |
| Export, backup, restore | Đưa dữ liệu ra hoặc khôi phục dữ liệu | Phải xét phạm vi toàn bộ dữ liệu và vật liệu giải mã liên quan |

Tên quyền và cách tách thao tác phụ thuộc sản phẩm. Bảng này là mô hình phân tích; không thể đưa nguyên các tên nhóm vào một engine bất kỳ rồi coi là policy đã được thực thi.

Một workload biết chính xác secret cần lấy thường không cần quyền tìm kiếm toàn bộ namespace. Tuy nhiên, nếu giao diện hoặc API yêu cầu thêm thao tác metadata, cần xác định đúng thao tác đó thay vì mở rộng thành quyền đọc toàn cây.

## 4. Least privilege và quyền hiệu lực

### 4.1 Bắt đầu từ công việc cần hoàn thành

Với mỗi chủ thể, xác định công việc, đối tượng, thao tác, thời hạn và bên chịu trách nhiệm. Ví dụ:

```text
Chủ thể: workload xử lý đơn hàng production
Công việc: kết nối cơ sở dữ liệu đơn hàng
Đối tượng: role cấp credential runtime của chính ứng dụng
Thao tác: nhận credential theo role đã định nghĩa
Thời hạn: theo vòng đời được nền tảng và ứng dụng hỗ trợ
Không cần: quản lý policy, liệt kê các secret khác, chọn role quản trị
```

“Không cần” ở đây là yêu cầu thiết kế để chuyển thành policy và kiểm chứng; nó không tự tạo một quy tắc từ chối trong sản phẩm.

### 4.2 Xét mọi nguồn cấp quyền

Một danh tính có thể nhận quyền qua nhiều nhóm, role, policy trực tiếp, kế thừa folder, namespace cha hoặc quyền quản trị toàn hệ thống. Quyền hiệu lực phải được đánh giá trên tổng thể các nguồn đó.

Cần xác minh mô hình kết hợp của engine:

- Các quyền cho phép được cộng dồn hay bị giới hạn bởi một lớp khác?
- Quy tắc từ chối rõ ràng được xử lý thế nào, nếu sản phẩm hỗ trợ?
- Quyền ở cha có được kế thừa xuống con không?
- Có quyền đặc biệt nào bỏ qua một phần đánh giá thông thường không?
- Nếu thiếu ngữ cảnh hoặc không đọc được policy, yêu cầu được xử lý ra sao?

Không mặc định “deny luôn thắng” hoặc “policy cụ thể nhất luôn thắng” cho mọi giải pháp. Mục tiêu là mặc định từ chối khi không có căn cứ cho phép, sau đó diễn đạt mục tiêu đó bằng cơ chế thật của hệ thống.

### 4.3 Wildcard và quyền cho tài nguyên tương lai

Một policy cho phép toàn bộ cây có thể bao phủ cả secret được tạo sau này. Rủi ro không chỉ là những gì đang có trong folder hôm nay.

Cần biết mẫu khớp dựa trên đoạn đường dẫn, tiền tố hay quy tắc khác. Quyền cho `payments` không nên vô tình bao phủ `payments-archive` do cách so khớp quá đơn giản. Các đường dữ liệu, metadata, phiên bản và thao tác quản trị cũng có thể dùng phạm vi API khác nhau.

Với ABAC, kiểm tra người được sửa nhãn hoặc chủ sở hữu tài nguyên. Nếu họ có thể tự thay thuộc tính để đối tượng khớp một policy rộng, việc dùng nhãn không còn tạo được ranh giới như dự định.

## 5. Quyền gián tiếp và phân tách nhiệm vụ

Người không có quyền đọc secret trực tiếp vẫn có thể tiếp cận secret hoặc đặc quyền qua các khả năng khác:

- Tự sửa policy hoặc membership để cấp thêm quyền.
- Tạo token, role hoặc phương thức xác thực có quyền cao hơn.
- Thay cấu hình broker, plugin hoặc connector để xử lý dữ liệu ngoài thiết kế.
- Sửa metadata đích khiến một dịch vụ gửi credential tới tài nguyên không đúng.
- Export hoặc restore dữ liệu bằng quyền quản trị nền tảng.
- Lấy khóa hoặc can thiệp thành phần có quyền giải mã dữ liệu.
- Tắt audit để giảm khả năng bị phát hiện.

Ví dụ, nếu một worker luân chuyển tin hoàn toàn vào trường endpoint do người dùng sửa được, nó có thể kết nối sai đích khi sử dụng credential nhạy cảm. Vì vậy, quyền sửa metadata tài nguyên, danh tính máy đích và cơ chế xác minh đích cũng cần được bảo vệ.

### Phân chia trách nhiệm tham chiếu

| Vai trò | Trách nhiệm | Điểm phân tách cần kiểm chứng |
|---|---|---|
| Chủ tài nguyên | Xác định nhu cầu và người sử dụng hợp lệ | Không tự biến yêu cầu nghiệp vụ thành quyền quản trị toàn vault |
| Người thiết kế policy | Soạn quy tắc và phạm vi | Thay đổi quyền nhạy cảm có quy trình kiểm soát |
| Người phê duyệt hoặc xuất bản | Kiểm tra và đưa policy vào hiệu lực | Tránh một người tự yêu cầu, tự mở quyền và tự xóa dấu vết |
| Người vận hành phiên | Thực hiện công việc được duyệt | Không mặc nhiên đọc credential hoặc sửa policy |
| Worker luân chuyển | Thay credential theo workflow | Không quản lý mọi đối tượng hoặc mọi danh tính |
| Người kiểm toán | Đọc bằng chứng theo trách nhiệm | Không cần đọc giá trị secret chỉ để xác nhận truy cập đã xảy ra |

Phân tách bằng tên role chưa đủ. Nếu một vai trò vẫn có thể tự nâng quyền qua cơ chế khác, cần coi đó là quyền quản trị có ảnh hưởng lớn. Quyền nền tảng hoặc quyền khẩn cấp còn tồn tại phải được ghi nhận, bảo vệ và audit rõ ràng.

## 6. Policy cho người dùng, broker và workload

### 6.1 Người quản trị

Người dùng nên được nhận diện bằng danh tính cá nhân, ánh xạ qua nhóm hoặc vai trò phù hợp. Các yêu cầu rủi ro cao có thể cần MFA, lý do, mã thay đổi và phê duyệt trước khi được cấp quyền có thời hạn.

Nếu công việc có thể đi qua session broker, ưu tiên cấp khả năng sử dụng cho đúng tài khoản đích thay vì luôn cho xem mật khẩu. Tuy nhiên, với quyền quản trị rất cao ở đích, người dùng có thể tiếp cận dữ liệu hoặc thành phần khác trong phiên; không nên hứa rằng broker loại bỏ mọi khả năng lộ credential.

### 6.2 Session broker hoặc proxy

Danh tính dịch vụ của broker chỉ cần truy cập tập credential mà nó phục vụ. Yêu cầu lấy hoặc dùng credential cần được ràng buộc với người dùng, tài nguyên, quyền đã duyệt và mã phiên.

Policy phải hạn chế việc người dùng gửi tùy ý một tham chiếu secret khác vào broker. Một dịch vụ có quyền đọc rộng nhưng tin mọi tham số từ client có thể trở thành đường truy cập thay mặt người không có quyền.

### 6.3 Workload

Workload cần danh tính máy có thể xác minh, tách theo dịch vụ và môi trường. Không dùng một token vault toàn quyền cho mọi ứng dụng chỉ vì các ứng dụng cùng chạy trong một cụm.

Khi dùng federation hoặc bằng chứng danh tính từ nền tảng, ràng buộc nguồn phát hành, subject, đối tượng nhận và các điều kiện mà cơ chế thực tế hỗ trợ. Xác định ai có thể thay đổi cấu hình hoặc mã chạy của workload, vì người đó có thể sử dụng khả năng của danh tính workload.

Credential khởi tạo để truy cập vault cũng có vòng đời riêng. Nếu phải dùng token hoặc secret cố định, cần bảo vệ, giới hạn quyền và xử lý luân chuyển; không đưa nó vào source code hoặc ảnh máy để đơn giản hóa triển khai.

### 6.4 Worker luân chuyển

Worker cần quyền thực hiện quy trình đã định nghĩa trên những tài khoản cụ thể. Quyền sửa giá trị secret trong vault không tự cho phép worker thay mật khẩu ở đích; ngược lại, worker có thể thay ở đích nhưng thất bại khi ghi trạng thái mới về vault.

Cần bảo vệ danh tính worker, giới hạn tài khoản được quản lý và theo dõi công việc chưa chắc chắn kết quả. Không cấp quyền sửa toàn bộ policy hoặc truy cập mọi namespace chỉ để tránh cấu hình phạm vi.

## 7. JIT, thời hạn và thu hồi

### 7.1 Các thời hạn khác nhau

| Thời hạn | Điều được giới hạn |
|---|---|
| Thời hạn yêu cầu hoặc phê duyệt | Khi nào người dùng được phép thực hiện công việc |
| Thời hạn token truy cập vault | Khi nào token có thể gửi yêu cầu được chấp nhận |
| Thời hạn grant hoặc membership | Khi nào một danh tính được cấp khả năng truy cập |
| TTL hoặc lease credential được cấp | Vòng đời credential hoặc quyền ở hệ thống đích theo cơ chế thực tế |
| Thời lượng phiên quản trị | Bao lâu một phiên đã thiết lập được tiếp tục |

Những thời hạn này cần phối hợp. Nếu yêu cầu hết hạn sau 30 phút nhưng người dùng có thể nhận credential mới với hiệu lực dài hơn ở phút cuối, quyền thực tế có thể vượt cửa sổ được duyệt.

Gia hạn token hoặc lease cũng là một thao tác cần chính sách. Không tự cho gia hạn vô hạn chỉ vì danh tính đã được xác thực trước đó.

### 7.2 Thu hồi ở vault chưa hoàn tất mọi lớp

Cần phân biệt:

1. Ngăn yêu cầu mới tới vault.
2. Ngăn việc cấp hoặc gia hạn credential mới.
3. Vô hiệu credential đã phát ra tại đích.
4. Chấm dứt phiên hoặc xử lý tác vụ đã bắt đầu.

Thu hồi token vault không khiến một mật khẩu đã sao chép tự mất hiệu lực. Với credential động, việc thu hồi lease chỉ làm credential mất hiệu lực ở đích nếu cơ chế tích hợp thực hiện thành công; cần kiểm tra kết quả.

Thay mật khẩu hoặc làm credential hết hạn cũng không mặc nhiên đóng mọi kết nối đã xác thực. Những tiến trình, phiên cơ sở dữ liệu hoặc tác vụ nền có thể cần hành động riêng theo khả năng của tài nguyên đích.

### 7.3 Độ trễ danh tính và policy

Xóa người khỏi nhóm ở nguồn danh tính có thể chưa có tác dụng ngay với token, phiên hoặc cache đang tồn tại. Cần hiểu hệ thống đánh giá membership lúc đăng nhập hay mỗi lần yêu cầu, cách cache được cập nhật và khả năng thu hồi khẩn cấp.

Không gán một thời gian thu hồi bảo đảm chỉ từ cấu hình TTL trên một lớp. Phải kiểm chứng đường đi thực tế từ thay đổi quyền tới yêu cầu mới và phiên đang chạy.

## 8. Ví dụ policy cho dịch vụ thanh toán

Giả sử có ba bên:

- Workload `orders-runtime-prod` cần credential giới hạn cho cơ sở dữ liệu đơn hàng.
- Nhóm `payments-operators` cần mở phiên bảo trì vào máy ứng dụng trong thời gian được duyệt.
- Worker `payments-rotator` quản lý credential của một tài khoản đã định trước.

### 8.1 Ý định phân quyền

| Chủ thể | Tài nguyên | Khả năng được cấp |
|---|---|---|
| Workload runtime | Role cấp credential runtime của ứng dụng | Nhận credential theo profile đã giới hạn, không tự chọn profile quản trị |
| Nhóm vận hành | Tài khoản bảo trì của máy ứng dụng | Dùng qua broker khi đủ điều kiện và còn thời hạn |
| Worker luân chuyển | Đối tượng credential được quản lý | Thực hiện workflow thay credential và đối soát |
| Nhóm kiểm toán | Audit liên quan đến phạm vi thanh toán | Đọc bằng chứng cần thiết, không tự đọc giá trị secret |

### 8.2 Mô hình cấu hình minh họa

Đây là cách biểu diễn ý định, không phải ngôn ngữ policy của một sản phẩm vault:

```yaml
access_policy_model:
  namespace: prod-payments
  default_decision: deny
  grants:
    - subject_reference: orders-runtime-prod
      resource_reference: dynamic-credentials/orders/runtime-profile
      operations:
        - request_dynamic_credential
      constraints:
        credential_profile_fixed: true
        lifetime_bounded_by_profile: true
    - subject_reference: payments-operators
      resource_reference: servers/payment-api-01/maintenance-account
      operations:
        - use_via_session_broker
      conditions:
        approval_required: true
        mfa_required: true
        justification_required: true
        maximum_access_minutes: 30
    - subject_reference: payments-rotator
      resource_reference: databases/orders/managed-service-account
      operations:
        - execute_managed_rotation
    - subject_reference: payments-auditors
      resource_reference: audit/payments-access
      operations:
        - read_audit_evidence
```

Các trường và thao tác trên phải được dịch sang cơ chế thực tế. Sản phẩm có thể không hỗ trợ cùng cách gắn điều kiện hoặc tách quyền. Cần chỉ rõ thành phần nào kiểm tra phê duyệt, thành phần nào thực thi thời hạn và thành phần nào cấp hoặc thu hồi credential.

### 8.3 Giới hạn tại tài nguyên đích

Profile runtime chỉ nên cấp quyền ứng dụng cần trên cơ sở dữ liệu. Một profile cấp tài khoản quản trị toàn bộ cơ sở dữ liệu vẫn tạo rủi ro lớn dù workload không được đọc secret nào khác.

Tài khoản bảo trì cũng cần quyền tối thiểu và cơ chế giới hạn hành động khi phù hợp. JEA hoặc một endpoint quản trị giới hạn ở đích không tự xuất hiện từ thao tác `use_via_session_broker` trong ví dụ.

Worker cần quyền ở đích để đổi credential, nhưng không nên có quyền quản trị những tài khoản ngoài tập được giao. Nếu kỹ thuật buộc dùng một danh tính nền có quyền rộng hơn, cần ghi nhận rủi ro và tăng bảo vệ cho đường sử dụng đó.

## 9. Vòng đời của policy

### Bước 1: Thu thập nhu cầu và kiểm kê quyền hiện tại

Xác định chủ thể, công việc, tài nguyên, quyền hiệu lực đang tồn tại và bên chịu trách nhiệm. Ghi nhận cả credential được dùng ngoài vault hoặc ngoại lệ có thể làm vô hiệu kiểm soát dự kiến.

### Bước 2: Soạn quy tắc hẹp nhất đáp ứng công việc

Chọn thao tác và phạm vi cụ thể; xác định thời hạn, điều kiện và hành vi khi thiếu ngữ cảnh. Bảo vệ các thuộc tính mà policy tin cậy, bao gồm owner, nhãn và tham chiếu tài nguyên.

### Bước 3: Xem xét tác động và quyền gián tiếp

Kiểm tra wildcard, quyền kế thừa, khả năng tạo token, sửa policy, export và quản trị danh tính. Xác định policy sẽ bao phủ thêm đối tượng nào khi cây tài nguyên thay đổi.

### Bước 4: Kiểm chứng trước khi áp dụng rộng

Dùng các danh tính đại diện và đối tượng thử nghiệm để kiểm tra thao tác hợp lệ, thao tác phải từ chối và trường hợp thiếu hoặc sai điều kiện. Kiểm tra cả API và các đường chức năng liên quan, không chỉ giao diện chính.

### Bước 5: Xuất bản có kiểm soát

Gắn phiên bản, người thực hiện, lý do và tham chiếu phê duyệt theo quy trình. Áp dụng từng phạm vi phù hợp, theo dõi lỗi truy cập và khả năng duy trì công việc cần thiết.

### Bước 6: Rà soát và thu hồi

Đối chiếu với chủ tài nguyên, thay đổi nhân sự, vòng đời workload và các sự kiện sử dụng. Quyền không dùng có thể là dư thừa hoặc dành cho tác vụ định kỳ; cần xác minh trước khi xử lý.

Rollback policy cũng cần xem xét bảo mật. Khôi phục một phiên bản cũ có thể khôi phục quyền quá rộng hoặc quyền đã bị thu hồi vì sự cố; không nên tự động quay lại mọi cấu hình cũ chỉ để làm yêu cầu hết lỗi.

## 10. Kiểm chứng quyền cho phép và quyền phải từ chối

Trong môi trường được phép thử nghiệm, nên lập ma trận gồm danh tính, ngữ cảnh, tài nguyên, thao tác và kết quả mong đợi. Các tình huống dưới đây là hướng dẫn thực hành, không phải kết quả kiểm thử của một hệ thống cụ thể.

| Tình huống | Điều cần xác nhận |
|---|---|
| Workload nhận credential đúng profile | Thành công với quyền và thời hạn đúng thiết kế |
| Workload chọn profile quản trị khác | Không thể mở rộng quyền bằng tham số yêu cầu |
| Danh tính non-production dùng tài nguyên production | Bị từ chối theo cơ chế phân quyền |
| Người vận hành thiếu phê duyệt hoặc MFA bắt buộc | Không được dùng credential hoặc mở phiên tương ứng |
| Người dùng được dùng qua broker gọi chức năng đọc/export | Không lấy được giá trị qua đường ngoài thiết kế |
| Đọc metadata, lịch sử hoặc phiên bản cũ | Quyền khớp phạm vi đã được quyết định riêng |
| Tên tài nguyên gần giống hoặc chuyển namespace | Không vô tình khớp policy của tài nguyên được cấp |
| Thêm đối tượng con mới | Quyền kế thừa và wildcard không mở rộng ngoài dự kiến |
| Sửa nhãn hoặc metadata ảnh hưởng policy | Chỉ chủ thể được phép mới thay đổi được thuộc tính tin cậy |
| Người bị xóa khỏi nhóm dùng token cũ | Hành vi thu hồi khớp với cơ chế và giới hạn đã công bố |
| Token hoặc lease hết hạn | Yêu cầu mới, gia hạn và hoạt động tại đích được xử lý đúng từng lớp |
| Worker yêu cầu luân chuyển tài khoản ngoài phạm vi | Bị từ chối và có sự kiện đủ để điều tra |
| Quản trị viên policy tự cấp thêm quyền | Bị ngăn hoặc đi qua kiểm soát nhạy cảm được thiết kế và audit |

Kiểm tra phải từ chối cần xác minh không có tác động ở đích ngoài dự kiến. Một thông báo lỗi trên client chưa đủ nếu tác vụ nền đã tạo tài khoản hoặc thay quyền trước khi lỗi trả về.

Các phép thử nên dùng dữ liệu giả và tác động nhỏ. Không cần phá hủy đối tượng thật để chứng minh rằng một quyền hủy dữ liệu đã được giới hạn.

## 11. Audit và giám sát policy

### 11.1 Dữ liệu để giải thích một quyết định

Một sự kiện truy cập hữu ích có thể bao gồm:

- Danh tính người dùng hoặc workload và nguồn xác thực.
- Namespace, ID hoặc tham chiếu đối tượng, loại thao tác.
- Thời điểm, mã yêu cầu và mã phiên hoặc lease nếu có.
- Quyết định cho phép/từ chối, kết quả thực thi và lý do theo phạm vi được phép ghi.
- Tham chiếu policy hoặc phiên bản policy khi hệ thống cung cấp.
- Yêu cầu phê duyệt, phiên broker hoặc workflow luân chuyển liên quan.

Không phải engine nào cũng trả về cùng mức giải thích. Cần biết bằng chứng có thể chứng minh phần nào, bổ sung đối chiếu ở lớp điều khiển hoặc tài nguyên đích khi cần.

Không ghi giá trị secret, token, private key hoặc nội dung phản hồi nhạy cảm vào log. Metadata và đường dẫn cũng cần được bảo vệ theo mức nhạy cảm.

### 11.2 Những thay đổi cần chú ý

Các cảnh báo hữu ích gồm mở rộng wildcard, thêm nhóm có quyền cao, tạo phương thức xác thực mới, tạo token rộng quyền, tăng thời hạn, sửa trust của workload, tắt audit và nhiều yêu cầu bị từ chối bất thường.

Cần theo dõi cả các quyền đã cấp nhưng không còn chủ sở hữu, quyền JIT thu hồi quá hạn và công việc luân chuyển chưa hoàn tất. Một dashboard chỉ đếm số yêu cầu được cho phép không phản ánh mức độ đúng đắn của policy.

### 11.3 Bảo vệ bằng chứng khỏi chủ thể bị giám sát

Phân quyền xem log, sửa cấu hình audit và xóa dữ liệu bằng chứng cần được xem xét riêng. Nếu cùng một chủ thể có thể tự mở quyền rồi xóa mọi sự kiện, khả năng quy trách nhiệm bị suy yếu.

Sử dụng nơi lưu và cơ chế bảo vệ tính toàn vẹn phù hợp, đồng thời kiểm tra khả năng đọc lại bằng chứng. Backup và restore policy cũng phải được ghi nhận vì có thể đưa quyền cũ trở lại hiệu lực.

## 12. Xử lý sự cố và phụ thuộc không khả dụng

### 12.1 Khi nghi ngờ danh tính đã bị chiếm quyền

Một luồng ứng phó tham chiếu gồm:

1. Xác định danh tính, token, đối tượng và thời gian bị ảnh hưởng từ các sự kiện có sẵn.
2. Ngăn cấp thêm quyền hoặc credential, thu hồi token và grant liên quan theo khả năng hệ thống.
3. Xác định credential nào đã phát ra hoặc có thể đã bị đọc; luân chuyển hoặc thu hồi tại đích khi cần.
4. Kiểm tra phiên, lease, tiến trình và tác vụ còn hoạt động, không chỉ yêu cầu mới ở vault.
5. Bảo toàn bằng chứng và điều tra các thay đổi policy, danh tính, metadata hoặc cấu hình audit.
6. Khôi phục bằng danh tính và quyền đã được xác minh, rồi kiểm chứng lại phạm vi truy cập.

Phạm vi phản ứng phụ thuộc khả năng thật và bằng chứng. Không nên coi việc vô hiệu tài khoản ở IdP là đủ nếu token vault, credential đích hoặc phiên vẫn còn sử dụng được.

### 12.2 Khi IdP, policy engine hoặc vault lỗi

Nếu không có căn cứ hợp lệ để cho phép một yêu cầu mới, không tự bỏ điều kiện bắt buộc để duy trì phản hồi. Phải định nghĩa riêng hành vi cho yêu cầu mới, phiên đã mở, credential đang có hiệu lực và công việc thu hồi.

Nếu hệ thống cho phép dùng quyết định hoặc credential đã cache, cần giới hạn phạm vi và thời gian, bảo vệ dữ liệu, nêu rõ độ trễ thu hồi có thể xảy ra và điều kiện dừng. Không tự gia hạn quyền khi không còn liên lạc được với nơi có thẩm quyền.

### 12.3 Truy cập khẩn cấp

Break-glass cần danh tính, mục đích, phạm vi, điều kiện kích hoạt và bằng chứng sử dụng rõ ràng. Nếu dùng để phục hồi vault, đường đó phải hoạt động trong những sự cố được thiết kế, tránh phụ thuộc vòng vào chính thành phần đang lỗi.

Sau sử dụng, đối soát hành động, thu hồi quyền và luân chuyển credential theo quy trình. Quyền khẩn cấp có ảnh hưởng lớn vẫn là một phần của kiểm kê quyền, không phải ngoại lệ vĩnh viễn ngoài giám sát.

## 13. Điều kiện bàn giao và duy trì

Một bộ policy sẵn sàng vận hành khi có thể giải thích và kiểm chứng:

- Mỗi grant phục vụ công việc nào, thuộc chủ sở hữu nào và có phạm vi ra sao.
- Danh tính, thuộc tính và ngữ cảnh mà engine tin cậy được bảo vệ thế nào.
- Những thao tác đọc, dùng, cấp phát, luân chuyển và quản trị đã được phân biệt đúng khả năng sản phẩm.
- Quyền hiệu lực qua mọi nhóm, kế thừa và đường quản trị gián tiếp đã được đánh giá.
- Thời hạn, gia hạn và thu hồi được xử lý ở vault, credential đích và phiên tương ứng.
- Quyền hợp lệ và quyền phải từ chối đã có bằng chứng kiểm chứng phù hợp.
- Audit, xử lý lỗi, rollback và break-glass có trách nhiệm vận hành rõ ràng.

Policy cần được rà soát khi tài nguyên, workload, nhóm người dùng hoặc mô hình trust thay đổi. Mục tiêu vận hành là duy trì khả năng cấp đúng quyền cho công việc, giới hạn hậu quả khi một danh tính bị xâm nhập và truy vết được việc sử dụng đặc quyền từ vault tới hệ thống đích.
