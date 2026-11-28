# Onboard API credential vào PAM

Onboard API credential là quá trình đưa thông tin xác thực dùng để gọi API vào một vòng đời quản lý có chủ sở hữu, giới hạn quyền, kiểm soát cấp phát, luân chuyển, thu hồi và bằng chứng kiểm toán. Trong Privileged Access Management (PAM), mục tiêu là kiểm soát khả năng thực hiện hành động nhạy cảm qua API, không chỉ cất một chuỗi bí mật vào vault.

Một API credential có thể cho phép tạo người dùng, thay đổi cấu hình hạ tầng, truy cập dữ liệu sản xuất hoặc cấp thêm quyền. Nếu chỉ di chuyển giá trị từ file cấu hình sang vault mà workload vẫn được đọc mọi secret, quyền ở API vẫn quá rộng và credential cũ vẫn hoạt động, việc onboarding chưa giải quyết được rủi ro chính.

Trong chương Onboarding, bài này tập trung vào credential phục vụ truy cập API của dịch vụ, công cụ vận hành và pipeline tự động. Các bước được trình bày độc lập với sản phẩm PAM hoặc nhà cung cấp API cụ thể; khả năng tạo, đổi, giới hạn và thu hồi credential phải được xác minh với hệ thống đích.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Phân loại API credential và xác định phần nào thực sự là secret cần bảo vệ.
- Lập hồ sơ owner, phạm vi quyền, môi trường và các workload đang tiêu thụ credential.
- Thiết kế cách workload lấy credential hoặc nhận quyền ngắn hạn mà không chia sẻ tài khoản cá nhân.
- Xây dựng quy trình chuyển đổi, luân chuyển và thu hồi theo khả năng của nhà cung cấp.
- Kiểm tra quyền thực tế, hạn chế lộ secret và nối bằng chứng giữa PAM với API đích.

Onboarding hoàn tất khi có thể trả lời bằng bằng chứng: credential thuộc danh tính nào, dùng cho API nào, ai hoặc workload nào được nhận, nó có thể làm gì, sẽ hết hiệu lực hoặc bị thu hồi ra sao và phần nào còn phụ thuộc vào quy trình thủ công.

## 2. Phân biệt các loại credential

| Loại | Thành phần cần quản lý | Điểm cần chú ý khi onboarding |
| --- | --- | --- |
| API key tĩnh | Giá trị bí mật và key ID nếu có | Có thể tồn tại lâu; khả năng giới hạn scope và tạo nhiều key phụ thuộc nhà cung cấp |
| Personal access token | Token gắn với một tài khoản người dùng | Có thể phụ thuộc vòng đời nhân sự và mang quyền của người đó; cần đánh giá việc chuyển sang danh tính dịch vụ |
| OAuth client credential | Client secret hoặc private key của client; client ID thường là định danh | Credential dùng để xin token, không đồng nhất với access token được cấp sau đó |
| Access token | Token được trình cho API | Cần xét audience, scope, thời hạn, cách xác minh và khả năng thu hồi |
| Refresh token | Vật liệu dùng để xin token mới trong luồng có hỗ trợ | Không phải luồng nào cũng cấp; có vòng đời và rủi ro riêng |
| Chứng chỉ client và private key | Private key, chứng chỉ, chuỗi tin cậy, thời hạn | Dùng trong mTLS hoặc cơ chế xác thực khác; cần quản lý cả việc gia hạn và chấp nhận tại đích |
| Khóa ký yêu cầu API | Private key hoặc shared secret, key ID, cấu hình ký | Phải bảo vệ khả năng ký; đồng thời quản lý tin cậy, thời gian và cơ chế chống phát lại ở API |
| Workload identity hoặc federation | Quan hệ tin cậy và quyền đổi danh tính lấy token | Có thể giảm secret dài hạn, nhưng cấu hình issuer, subject, audience và quyền đích vẫn cần quản lý |

Không gọi mọi chuỗi là API key. Sai phân loại sẽ dẫn tới sai kế hoạch thu hồi: vô hiệu hóa client secret có thể chặn lần xin token tiếp theo nhưng không tự làm mọi access token đã cấp mất hiệu lực.

Không phải API credential nào cũng là đặc quyền cao. Phân loại dựa trên hành động và phạm vi thực tế: đọc một chỉ số công khai khác với tạo khóa mới hoặc thay đổi chính sách quản trị. Dành kiểm soát PAM phù hợp cho credential có thể tác động tới tài khoản quản trị, dịch vụ hoặc hạ tầng nhạy cảm.

### Danh tính, credential và quyền là ba lớp khác nhau

- **Danh tính:** service account, ứng dụng đăng ký, workload hoặc tài khoản con người.
- **Credential:** vật liệu để chứng minh danh tính hoặc thực hiện cơ chế xác thực.
- **Quyền:** các hành động và tài nguyên mà hệ thống đích cho phép sau xác thực.

Cất credential vào vault không tự giảm quyền của danh tính tại API. Luân chuyển một khóa cũng không tự tách hai ứng dụng đang cùng dùng một service account. Cần xem xét cả ba lớp khi thiết kế.

## 3. Kiểm kê trước khi đưa vào quản lý

### 3.1. Hồ sơ tối thiểu

| Nhóm thông tin | Nội dung cần xác định |
| --- | --- |
| Owner | Nhóm chịu trách nhiệm dịch vụ, người chấp nhận thay đổi, đầu mối sự cố |
| Hệ thống đích | API, endpoint tin cậy, tenant hoặc tài khoản nền tảng, môi trường |
| Danh tính | Principal ID ổn định, kiểu danh tính, thuộc tính liên quan tới vòng đời |
| Loại credential | API key, client secret, khóa ký, chứng chỉ hoặc loại khác |
| Định danh không bí mật | Key ID, client ID, certificate serial hoặc tham chiếu do nhà cung cấp cấp nếu phù hợp |
| Quyền | Vai trò, scope, giới hạn tài nguyên, quyền có thể cấp tiếp cho người khác |
| Consumer | Workload, pipeline, tác vụ định kỳ, môi trường chạy, cách nhận và cache credential |
| Vòng đời | Thời hạn, cơ chế tạo mới, số credential được phép cùng hoạt động, cách thu hồi |
| Phụ thuộc | Nơi tiêu thụ, chu kỳ chạy, restart hoặc reload, nhà cung cấp quản lý cập nhật |
| Kiểm soát | Chính sách đọc secret, phê duyệt, luân chuyển, cảnh báo, bằng chứng cần giữ |
| Thay đổi | Cửa sổ thực hiện, điều kiện dừng, cách quay lui và người xác nhận |

Không đưa giá trị secret vào bảng kiểm kê, ticket hoặc tài liệu bàn giao. Giá trị chỉ đi qua kênh tiếp nhận được bảo vệ phù hợp; hồ sơ dùng tham chiếu và định danh không bí mật khi có.

### 3.2. Tìm đủ nơi sử dụng

Một credential có thể đang nằm trong nhiều nơi: secret store của CI/CD, cấu hình ứng dụng, biến môi trường, tác vụ định kỳ, container, máy chủ vận hành và công cụ phát triển. Cần xác định nơi nào là nguồn chính thức và nơi nào là bản sao cần loại bỏ sau chuyển đổi.

Hỏi rõ workload nhận giá trị ở thời điểm khởi động hay trong từng lần gọi; có giữ cache trong bộ nhớ không; có nhiều replica hoặc worker chạy lâu không; lần chạy tiếp theo của tác vụ định kỳ là khi nào. Đổi secret trong vault không có nghĩa là mọi tiến trình đã sử dụng phiên bản mới.

Với token của nhân viên đang được dùng cho automation, cần xác định phương án chuyển sang danh tính dịch vụ hoặc workload phù hợp. Không duy trì phụ thuộc không rõ ràng vào tài khoản cá nhân chỉ vì token hiện vẫn hoạt động.

### 3.3. Xác định phạm vi quyền thực tế

Đối chiếu nhu cầu nghiệp vụ với quyền tại nhà cung cấp API. Kiểm tra cả quyền trực tiếp, vai trò được kế thừa, giới hạn tài nguyên và khả năng tạo credential khác hoặc cấp thêm quyền.

Ví dụ, một pipeline chỉ cần triển khai vào một môi trường không nên mặc nhiên dùng credential quản trị toàn bộ tổ chức. Tách production khỏi môi trường thử nghiệm, tách ứng dụng khi cần quy trách nhiệm và giới hạn phạm vi ảnh hưởng.

Scope được yêu cầu không nhất thiết là toàn bộ quyền hiệu lực. Kết quả còn phụ thuộc cách API xử lý scope, vai trò và chính sách tài nguyên. Phải kiểm tra kết quả cấp quyền và hành vi ở API đích, không chỉ đọc tên scope trong cấu hình client.

## 4. Chọn mô hình cấp phát

### 4.1. Ưu tiên giảm secret dài hạn khi có thể

Trước khi nhập một secret tĩnh, đánh giá xem hệ thống có hỗ trợ workload identity, federation, danh tính được quản lý hoặc token ngắn hạn phù hợp hay không. Nếu có, có thể quản lý quan hệ tin cậy và cơ chế cấp quyền thay cho phân phối một secret dài hạn.

Quyền ngắn hạn giảm thời gian sử dụng của một token bị lộ, nhưng không tự bảo đảm least privilege. Quan hệ federation có subject quá rộng hoặc vai trò đích quá mạnh vẫn có thể cấp quyền cho workload không mong muốn.

| Mô hình | Cách hoạt động | Điều cần kiểm soát |
| --- | --- | --- |
| Workload đọc secret từ vault | Workload xác thực với PAM và nhận credential được phép | Danh tính workload, policy đọc đúng đối tượng, cache, không ghi log secret |
| Broker xin token thay workload | Broker dùng credential được bảo vệ để lấy token phù hợp | Quyền gọi broker, audience và scope cho phép, không trở thành đường xin token tùy ý |
| Federation hoặc danh tính được quản lý | Workload dùng danh tính nền tảng để lấy quyền ngắn hạn | Issuer, subject, audience, tenant, ràng buộc môi trường và quyền tại đích |
| Proxy gọi API | Proxy giữ credential và chuyển tiếp yêu cầu được cho phép | Ràng buộc đích, đường dẫn, phương thức, tài nguyên và nguy cơ sử dụng proxy vượt phạm vi |
| Cấp phát cho người vận hành | Người được phép nhận credential theo quy trình | Thời hạn, lý do, phạm vi, xử lý sau khi secret đã được tiết lộ |

Chọn mô hình theo khả năng thật của nền tảng và yêu cầu vận hành. Không mô tả một hệ thống là giữ secret hoàn toàn phía máy chủ nếu workload vẫn nhận được giá trị secret.

### 4.2. Giải quyết danh tính khởi tạo

Workload cần chứng minh mình là ai trước khi được đọc secret hoặc xin token. Nếu mọi ứng dụng dùng chung một credential cố định để truy cập toàn bộ vault, hệ thống chỉ tạo ra một secret mạnh hơn cần bảo vệ.

Ưu tiên cơ chế danh tính gắn với môi trường chạy khi được hỗ trợ. Nếu vẫn cần bootstrap credential, giới hạn phạm vi, thời hạn, nơi lưu, khả năng sao chép và quy trình thay thế của chính credential đó.

Không tin một workload chỉ vì nó tự gửi tên ứng dụng trong một trường request. PAM hoặc broker phải kiểm tra một bằng chứng xác thực phù hợp và ánh xạ tới chính sách được quản lý.

## 5. Chuẩn bị tích hợp và đưa credential vào vault

### 5.1. Kiểm tra đích và kênh truyền

Xác định riêng endpoint dùng để lấy token, endpoint API nghiệp vụ và endpoint quản trị credential nếu có. Kiểm tra TLS và danh tính máy chủ theo mô hình tin cậy được chọn, đúng tenant hoặc tài khoản nền tảng và các kết nối mạng cần thiết.

Không cho consumer tùy ý chỉ định một URL rồi yêu cầu broker gửi credential tới đó. Nếu cần hỗ trợ nhiều đích, dùng ánh xạ và danh sách cho phép có kiểm soát. Xét cả chuyển hướng HTTP và retry để tránh chuyển secret hoặc bearer token sang đích ngoài phạm vi.

Không đặt secret trong query string hoặc URL. URL dễ đi vào access log, lịch sử, tracing và hệ thống giám sát. Cách trình credential phải theo giao thức được API hỗ trợ, đồng thời kiểm soát các lớp ghi log liên quan.

### 5.2. Nhập hoặc tạo mới

Có hai đường chính:

1. **Nhập credential hiện có:** phù hợp cho giai đoạn chuyển tiếp khi đã xác định nguồn gốc, owner và phạm vi; không chứng minh rằng các bản sao cũ đã biến mất.
2. **Tạo credential mới có kiểm soát:** dùng cho chuyển đổi khi nhà cung cấp hỗ trợ; có thể giúp tách consumer và loại bỏ phụ thuộc vào credential cũ.

Nếu hệ thống chỉ hiển thị secret một lần khi tạo, cần chuẩn bị sẵn kênh tiếp nhận và xác minh lưu thành công. Không lưu tạm vào file, chat hoặc clipboard dùng chung để thuận tiện chuyển tay.

Nhập thành công cần có phiên bản hoặc tham chiếu ổn định trong vault, policy cấp phát và metadata quản trị. Không lấy việc giao diện hiển thị dấu che secret làm bằng chứng rằng giá trị đã đúng hoặc quyền đã phù hợp.

### 5.3. Phân quyền cho người và workload

Tách quyền quản trị metadata, sử dụng credential, đọc giá trị secret, tạo phiên bản mới và thu hồi credential khi hệ thống hỗ trợ. Workload chỉ nên đọc đúng đối tượng và môi trường cần thiết.

Người có quyền sửa policy cấp phát có thể tự mở rộng quyền đọc secret nếu không có kiểm soát bổ sung. Do đó cần xét cả quyền quản trị PAM, quản lý khóa, tài khoản nhà cung cấp API và cấu hình workload.

Việc tách nhiệm vụ không có nghĩa là bắt mọi thao tác tự động chờ phê duyệt thủ công. Có thể phê duyệt policy và quy trình trước, rồi cho automation hoạt động trong giới hạn đã chấp nhận, kèm bằng chứng và cảnh báo.

## 6. Một hồ sơ onboarding minh họa

Ví dụ dưới đây là mô hình dữ liệu học tập, không phải schema cấu hình của một sản phẩm:

```yaml
api_credential:
  credential_id: cred-orders-deployer-prod
  owner_group: platform-orders
  environment: production
  provider:
    api_profile_ref: approved-orders-management-api
    tenant_ref: tenant-production
    principal_ref: app-orders-deployer
  authentication:
    kind: oauth_client_secret
    client_id_ref: provider-client-id-orders-deployer
    secret_ref: vault-ref-orders-deployer-client-secret
  authorization:
    required_capabilities:
      - deploy_orders_service
    resource_boundary_ref: orders-production-only
  delivery:
    mode: token_broker
    allowed_workload_ref: ci-orders-production
    token_profile_ref: approved-orders-deployment-token
  lifecycle:
    rotation_runbook_ref: rotate-orders-deployer-client-secret
    revocation_runbook_ref: revoke-orders-deployer-access
    readiness: pilot
  evidence:
    change_ref: CHG-API-008
    audit_profile_ref: privileged-api-access
```

Không có giá trị secret trong hồ sơ. `secret_ref` chỉ định nơi lưu; `token_profile_ref` phải được ánh xạ tới audience, scope và thời hạn thực tế mà nhà cung cấp hỗ trợ. `resource_boundary_ref` mô tả ranh giới mong muốn, cần có chính sách thực thi ở đích hoặc lớp kiểm soát phù hợp.

Trạng thái pilot thể hiện chưa mở cấp phát rộng. Việc khai báo hồ sơ không tự chứng minh rằng provider đã cấp đúng quyền, broker thực thi đúng giới hạn hoặc workload đã dùng thành công.

## 7. Kiểm thử trước khi chuyển consumer

### 7.1. Xác minh credential và quyền

Chọn một thao tác kiểm tra được nhà cung cấp hỗ trợ, có tác động tối thiểu và nằm trong phạm vi đã được chấp thuận. Không dùng thao tác xóa, đổi quyền hoặc tạo tài nguyên production chỉ để chứng minh xác thực thành công.

Kiểm thử cần tách ba kết quả:

1. Credential có thể xác thực hoặc xin token theo cơ chế dự kiến.
2. Danh tính sau xác thực thuộc đúng tenant, môi trường và phạm vi cần thiết.
3. API thực thi đúng quyền: hành động được phép thành công, hành động ngoài phạm vi bị từ chối.

Một phản hồi thành công từ endpoint lấy token chưa chứng minh API nghiệp vụ sẽ chấp nhận token hoặc giới hạn quyền như mong muốn. Ngược lại, một lỗi gọi API có thể đến từ sai audience, sai endpoint, mạng hoặc cấu hình quyền chứ không chỉ do secret sai.

Với JWT, đọc payload không tương đương xác minh chữ ký hoặc kiểm tra quyền. Với token opaque, consumer không nên giả định có thể giải mã để tự kết luận quyền. Cách xác minh token phải phù hợp giao thức và nhà cung cấp; quyết định cho phép hành động cuối cùng nằm ở API hoặc lớp thực thi quyền được thiết kế.

### 7.2. Kiểm tra cấp phát cho đúng workload

Thử workload được phép và một workload không nằm trong phạm vi. Xác minh rằng workload không thể đổi secret path, môi trường, audience, scope hoặc endpoint để nhận quyền rộng hơn.

Mã giả dưới đây mô tả các ràng buộc của một broker; không phải mã triển khai hoàn chỉnh:

```text
workload = authenticate_workload(request)
profile = authorize_fixed_profile(workload, requested_profile_id)
destination = resolve_approved_destination(profile)
credential_handle = obtain_approved_credential(profile)
token_handle = request_token(destination, credential_handle, profile)
check_token_response_against_profile(token_handle, profile)
record_issuance_metadata(workload, profile, outcome)
deliver_using_approved_channel(token_handle, workload)
```

Các hàm trên phải có hành vi bảo mật cụ thể khi triển khai. Chẳng hạn, `authorize_fixed_profile` không cho workload tự gửi scope tùy ý; `resolve_approved_destination` không tin URL từ request; kiểm tra token response phải xử lý đúng loại token và khả năng của provider.

Audit chỉ ghi metadata cần thiết, không ghi `credential_handle`, giá trị token hoặc response body chứa secret. Các nhánh lỗi, retry, debug và tracing cũng phải tuân thủ quy tắc này.

### 7.3. Kiểm tra cách consumer nhận thay đổi

Xác định khi nào consumer lấy lại credential hoặc token. Nếu cache tồn tại lâu hơn chu kỳ thay đổi, cần có cơ chế làm mới hoặc reload phù hợp. Với token ngắn hạn, làm mới trước khi hết hạn theo thiết kế và xử lý độ lệch thời gian được chấp nhận.

Không để mọi replica đồng thời xin token hoặc đọc vault khi một giá trị hết hạn. Có thể cần cache có giới hạn, làm mới phân tán hoặc cơ chế chống dồn tải. Các lựa chọn này phải giữ được ràng buộc danh tính và phạm vi; không chia một token production cho mọi môi trường chỉ để giảm số request.

## 8. Chuyển đổi và luân chuyển credential

### 8.1. Mô hình hai credential cùng hoạt động

Nếu nhà cung cấp hỗ trợ hai credential hợp lệ cho cùng một danh tính, có thể chuyển đổi theo giai đoạn:

```mermaid
flowchart LR
    A[Credential A đang hoạt động] --> B[Tạo B tại provider]
    B --> C[Lưu B và xác minh có kiểm soát]
    C --> D[Consumer pilot dùng B]
    D --> E[Chuyển các consumer còn lại]
    E --> F[Xác nhận không còn phụ thuộc A]
    F --> G[Thu hồi A tại provider]
    G --> H[Kiểm tra trạng thái và đóng thay đổi]
```

Mỗi bước cần có kết quả và điều kiện tiếp tục:

| Bước | Điều cần xác nhận |
| --- | --- |
| Tạo B | Đúng principal, đúng phạm vi; không tạo nhầm key cho tenant khác |
| Lưu B | Đã lưu nguyên vẹn, có tham chiếu phiên bản; giới hạn quyền đọc |
| Pilot | Workload mẫu lấy đúng phiên bản hoặc profile và gọi được hành động cần thiết |
| Mở rộng | Các replica, tác vụ định kỳ và consumer liên quan đã chuyển hoặc có kế hoạch xác nhận |
| Bỏ phụ thuộc A | Đã xét cache, tiến trình chạy lâu và lịch chạy không thường xuyên |
| Thu hồi A | Provider xác nhận vô hiệu hóa hoặc xóa theo cơ chế hỗ trợ |
| Đóng thay đổi | Trạng thái cuối rõ ràng; còn token đã cấp hay bản sao nào cần xử lý |

Thời gian chạy không lỗi ngắn chưa chứng minh một tác vụ chạy hằng tuần đã chuyển thành công. Kế hoạch xác nhận cần phản ánh chu kỳ của từng consumer hoặc có kiểm thử chủ động được chấp thuận.

Nếu dùng phiên bản `current` trong vault, thay con trỏ không có nghĩa các tiến trình đã bỏ phiên bản cũ. Cần quan sát hành vi cập nhật của consumer và giữ bằng chứng theo phạm vi phù hợp.

### 8.2. Khi chỉ có một credential hợp lệ

Nếu provider chỉ cho một key hoặc đổi secret sẽ vô hiệu hóa giá trị cũ ngay, không hứa hẹn chuyển đổi không gián đoạn. Có thể cần cửa sổ bảo trì, thứ tự cập nhật được điều phối hoặc thay đổi kiến trúc danh tính.

Lập kế hoạch cho khoảng thời gian provider và consumer có thể không đồng bộ. Xác định thao tác nào được tạm dừng, retry nào an toàn và điều kiện phục hồi. Không cho retry vô hạn với credential cũ vì có thể gây khóa, vượt giới hạn tốc độ hoặc che giấu sự cố.

Nếu connector không hỗ trợ tạo hoặc thu hồi credential của provider, vẫn có thể quản lý lưu trữ và cấp phát, nhưng phần vòng đời thủ công phải có owner và quy trình rõ. Không mô tả đó là luân chuyển tự động hoàn chỉnh.

### 8.3. Điều phối và xử lý trạng thái chưa rõ

Không để hai tiến trình cùng luân chuyển một credential mà không có kiểm soát đồng thời. Dùng cơ chế điều phối phù hợp, theo dõi phiên bản và xác định công việc đang thực hiện.

Nếu tạo key thành công ở provider nhưng mất phản hồi, trạng thái có thể chưa rõ. Trước khi thử tạo tiếp, đối soát bằng định danh thao tác hoặc danh sách key nếu provider hỗ trợ. Tương tự, khi thu hồi bị timeout, không kết luận credential đã bị vô hiệu hóa chỉ vì lệnh đã được gửi.

Một kết quả hợp lệ có thể là `pending_reconciliation`, kèm owner và cảnh báo. Ghi nhận trung thực trạng thái chưa rõ tốt hơn việc đánh dấu thành công khi chưa có bằng chứng.

## 9. Thu hồi: phải xử lý tại nơi chấp nhận credential

### 9.1. Vô hiệu hóa ở vault và vô hiệu hóa tại API

Xóa secret khỏi vault hoặc cấm đọc mới chỉ chặn đường cấp phát đó. Những bản sao đã được lấy ra vẫn có thể hoạt động nếu provider còn chấp nhận. Với API key tĩnh, thường cần hành động thu hồi, vô hiệu hóa hoặc thay thế ở nhà cung cấp theo cơ chế được hỗ trợ.

Với OAuth hoặc mô hình cấp token tương tự, cần phân biệt:

- Credential mà client dùng để xin token mới.
- Access token đã được cấp và chưa hết hạn.
- Refresh token hoặc grant liên quan nếu luồng thực tế có sử dụng.
- Quyền hoặc trạng thái của danh tính tại provider.

Đổi client secret có thể ngăn lần xin token mới bằng secret cũ, nhưng access token hiện có có thể còn hiệu lực. Khả năng chặn ngay phụ thuộc cơ chế API kiểm tra token, hỗ trợ thu hồi, chính sách của provider và cách xử lý cache. Không giả định có một nút thu hồi tức thời cho mọi loại token.

Nếu không thể vô hiệu hóa ngay token đã cấp, cần nêu rõ khoảng hiệu lực còn lại và biện pháp ứng phó phù hợp với sự cố. Dùng token ngắn hạn giúp giới hạn khoảng này nhưng không thay thế kiểm soát phạm vi.

### 9.2. Trường hợp credential nghi đã bị lộ

Đây là tình huống ứng phó sự cố, không chỉ là luân chuyển theo lịch. Cần phối hợp với owner và đội xử lý sự cố để hạn chế cấp phát, thu hồi tại provider, đánh giá token đã cấp và rà soát hoạt động bất thường.

Không quay lui sang một credential đã bị nghi lộ để khôi phục dịch vụ. Cần một phương án mới có kiểm soát, đồng thời giữ bằng chứng về thời điểm, phạm vi và hành động đã thực hiện.

Nếu secret xuất hiện trong kho mã, log hoặc artifact, đổi credential là bước quan trọng nhưng chưa xử lý mọi bản sao và quyền truy cập dữ liệu đã phát sinh. Việc dọn bản sao phải đi cùng bảo toàn bằng chứng phù hợp và xác nhận credential cũ không còn sử dụng được theo cơ chế của provider.

### 9.3. Offboarding

Khi ứng dụng ngừng hoạt động hoặc chuyển sang danh tính khác, cần chặn cấp phát mới, thu hồi credential tại provider, xử lý token hoặc grant liên quan khi áp dụng, gỡ quyền workload và dọn bản sao theo quy trình.

Chỉ xóa hồ sơ PAM sau khi đã xác nhận các hành động cần thiết hoặc giữ hồ sơ ở trạng thái kết thúc theo chính sách lưu giữ. Hồ sơ kiểm toán phải tiếp tục cho biết credential từng thuộc owner nào và đã được xử lý ra sao.

## 10. Audit cho truy cập API

Không phải mọi lần dùng API đều mở một phiên có video như SSH hoặc RDP. Bằng chứng thường được ghép từ PAM, broker, nền tảng danh tính, consumer và log của API đích.

| Lớp | Sự kiện hoặc dữ liệu cần có |
| --- | --- |
| PAM hoặc vault | Tạo đối tượng, sửa policy, ai hoặc workload nào lấy secret, phiên bản tham chiếu |
| Broker hoặc dịch vụ cấp token | Danh tính workload, profile cấp quyền, thời điểm, kết quả, định danh thao tác |
| Provider danh tính | Cấp token hoặc lỗi xác thực, principal, client, scope hoặc quyền được biểu diễn phù hợp |
| API đích | Danh tính hiệu lực, tài nguyên, hành động, kết quả, mã request do provider cấp |
| Luân chuyển và thu hồi | Credential ID, phiên bản hoặc key ID, từng bước, kết quả cuối, người hoặc tiến trình thực hiện |
| Quản trị bằng chứng | Người xem, xuất hoặc thay đổi cơ chế thu thập dữ liệu nhạy cảm |

Một lần đọc secret từ vault chứng minh việc cấp phát đã xảy ra, không chứng minh secret được dùng đúng một lần hoặc chỉ gọi đúng một API. Nếu cùng một credential được dùng bởi nhiều consumer, log ở đích có thể chỉ thấy cùng một principal; đây là giới hạn quy trách nhiệm cần nhận diện.

Các trường hữu ích gồm owner, environment, workload ID, principal ID, credential reference, key ID không bí mật khi có, action, target resource, correlation ID, provider request ID, thời gian và kết quả. Liên kết định danh theo cơ chế mà provider thực sự hỗ trợ; không giả định header tùy ý từ client sẽ được API lưu lại.

Không ghi Authorization header, access token, refresh token, client secret, private key hoặc response body có chứa secret. Cẩn trọng với URL, payload nghiệp vụ và thông báo lỗi. Tránh dùng hash trực tiếp của secret làm định danh mặc định; ưu tiên ID do provider hoặc vault cấp.

Giới hạn quyền xem audit vì ngay cả metadata cũng có thể tiết lộ cấu trúc tài nguyên và hoạt động nhạy cảm. Bảo vệ tính toàn vẹn, đồng bộ thời gian phù hợp và theo dõi nguồn audit ngừng gửi để kết quả truy vấn không gây hiểu nhầm.

## 11. Ma trận kiểm thử chấp nhận

Chỉ kiểm thử trong phạm vi và môi trường được chấp thuận. Những trường hợp gây gián đoạn cần có kế hoạch phù hợp; bài học này không yêu cầu thực hiện trên một API thật.

| Nhóm | Kiểm thử | Điều kiện đạt |
| --- | --- | --- |
| Định danh | Đối chiếu API, tenant, môi trường, principal và owner | Không nhầm hệ thống hoặc danh tính |
| Cấp phát hợp lệ | Workload được phép yêu cầu đúng secret hoặc profile | Nhận được khả năng truy cập theo chính sách |
| Từ chối | Workload khác yêu cầu credential production | Bị từ chối và có audit phù hợp |
| Ranh giới | Yêu cầu scope, audience, tài nguyên hoặc đích ngoài phạm vi | Không được nâng quyền ngoài profile đã duyệt |
| Quyền nghiệp vụ | Gọi thao tác cần thiết và một thao tác ngoài quyền trong phạm vi thử | Được phép hoặc bị từ chối đúng thiết kế |
| Kênh và log | Kiểm tra đường truyền, lỗi, debug, tracing và artifact | Không lộ secret; không gửi tới đích ngoài phạm vi |
| Chuyển phiên bản | Đưa consumer pilot rồi các consumer còn lại sang credential mới | Đủ bằng chứng về việc chuyển và xử lý cache |
| Thu hồi | Thu hồi credential cũ bằng cơ chế provider hỗ trợ | Xác nhận trạng thái ở provider; kiểm tra an toàn khi phù hợp |
| Token đã cấp | Đánh giá token còn hiệu lực sau đổi hoặc thu hồi client credential | Giới hạn được ghi rõ và có phương án xử lý |
| Sự cố | Vault, broker hoặc provider tạm không sẵn sàng | Retry, cache và trạng thái lỗi theo thiết kế; không tự mở quyền |
| Bằng chứng | Nối sự kiện từ cấp phát đến hành động API | Chỉ ra được điều đã chứng minh và khoảng trống còn tồn tại |

Không dùng secret cũ để thử một thao tác phá hủy nhằm chứng minh thu hồi. Chọn phương pháp xác nhận an toàn được provider hỗ trợ và ghi rõ phần nào chỉ là trạng thái báo cáo, phần nào đã được kiểm chứng hành vi.

Trước bàn giao, cần xác nhận các tiêu chí áp dụng đều đạt; phần thủ công hoặc hạn chế phải có owner chấp nhận. Một dòng trạng thái trong vault không thay thế ma trận này.

## 12. Tình huống: pipeline triển khai dịch vụ Orders

Pipeline Orders đang dùng một token cá nhân có quyền rộng để gọi API triển khai production. Token được sao chép trong hai hệ thống CI và một máy chạy tác vụ định kỳ. Mục tiêu là chuyển sang danh tính ứng dụng có quyền giới hạn và đưa vật liệu xác thực vào quản lý PAM.

### Bước 1: Lập phạm vi và phụ thuộc

Owner xác định ba consumer, lịch chạy, cách cache và các thao tác API cần thiết. Nhóm tách môi trường production khỏi staging, tạo danh tính ứng dụng phù hợp và gắn quyền chỉ cho tài nguyên Orders theo khả năng provider.

Token cá nhân cũ vẫn được coi là một credential cần thu hồi, không tự biến mất sau khi danh tính mới được tạo.

### Bước 2: Chọn cách cấp phát

Nếu cả môi trường CI và provider hỗ trợ federation phù hợp, nhóm có thể chọn cấp quyền ngắn hạn theo danh tính workload. Nếu chưa hỗ trợ, một phương án là broker dùng client credential được bảo vệ để xin token có profile cố định.

Trong phương án broker, pipeline không được tự đổi tenant, audience hoặc scope. Máy chạy tác vụ định kỳ cũng phải có danh tính riêng phù hợp, không dùng chung credential bootstrap không giới hạn.

### Bước 3: Pilot và mở rộng

Một pipeline thử lấy quyền qua luồng mới và thực hiện thao tác triển khai trong phạm vi chấp thuận. Pipeline không được phép quản trị tài khoản hoặc triển khai dịch vụ khác.

Nhóm chuyển consumer thứ hai và tác vụ định kỳ, xác nhận thời điểm nhận cấu hình mới và xử lý cache. Việc pipeline đầu tiên chạy thành công chưa đủ để thu hồi token cũ.

### Bước 4: Thu hồi và xác nhận

Sau khi các consumer chuyển xong, owner thu hồi token cá nhân ở provider, dọn các bản sao được xác định và kiểm tra bằng phương pháp an toàn. Nếu còn access token hoặc phiên xác thực phát sinh từ cơ chế cũ, nhóm đánh giá vòng đời của chúng theo provider.

Bằng chứng bàn giao gồm danh tính ứng dụng, phạm vi quyền, ba consumer, kết quả kiểm thử, tham chiếu cấp phát và kết quả thu hồi. Hồ sơ không chứa token cũ hoặc secret mới.

## 13. Lỗi thường gặp và tiêu chí vận hành

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đưa secret vào vault nhưng giữ quyền API quá rộng | Phạm vi ảnh hưởng không giảm | Rà soát quyền ở provider và kiểm thử ranh giới |
| Nhiều ứng dụng dùng chung credential | Khó quy trách nhiệm và thu hồi riêng | Tách danh tính hoặc credential khi phù hợp |
| Xóa secret ở PAM rồi coi là đã thu hồi | Bản sao bên ngoài vẫn có thể dùng | Xử lý tại provider và đánh giá token đã cấp |
| Đổi client secret rồi coi mọi token cũ hết hiệu lực | Bỏ sót quyền truy cập còn tồn tại | Xác định riêng vòng đời token và cơ chế thu hồi |
| Chỉ theo dõi consumer đang chạy thường xuyên | Tác vụ thưa kỳ lỗi sau cutover | Kiểm kê lịch chạy và xác nhận từng consumer |
| Cho broker nhận URL hoặc scope tùy ý | Có thể tiết lộ credential hoặc cấp quyền vượt dự kiến | Dùng profile và đích được kiểm soát |
| Ghi đầy đủ request và response để debug | Secret lọt vào log, trace hoặc artifact | Che dữ liệu tại nguồn và kiểm tra nhánh lỗi |
| Cho mọi ứng dụng đọc cùng vùng vault | Một workload bị xâm nhập kéo theo nhiều credential | Cấp quyền theo danh tính, đối tượng và môi trường |

Sau onboarding, theo dõi credential thiếu owner, sắp hết hạn, luân chuyển thất bại, consumer dùng phiên bản cũ, lần đọc bất thường, scope hoặc quyền thay đổi và credential đã ngừng sử dụng nhưng chưa thu hồi.

Khi đổi owner, thay API, chuyển tenant, thay môi trường CI hoặc nâng quyền ứng dụng, cần đánh giá lại hồ sơ. Credential vẫn còn hiệu lực không chứng minh cấu hình hiện tại còn phù hợp với mục đích ban đầu.

## 14. Bài thực hành thiết kế

Chọn hai trường hợp: một API key tĩnh chỉ hỗ trợ một key hoạt động và một ứng dụng dùng client credential để xin access token.

1. Lập hồ sơ owner, principal, quyền, consumer và phụ thuộc cho từng trường hợp.
2. Chọn mô hình cấp phát; xác định cách workload chứng minh danh tính mà không dùng tài khoản cá nhân chung.
3. Mô tả ranh giới đích, scope và tài nguyên được phép; viết một tình huống phải bị từ chối.
4. Vẽ trình tự tạo hoặc nhập, pilot, chuyển consumer, thu hồi và xác nhận.
5. Chỉ ra điều gì xảy ra với access token đã cấp khi client secret thay đổi.
6. Xây dựng điều kiện dừng và phương án phục hồi khi provider đổi credential thành công nhưng PAM mất phản hồi.
7. Liệt kê bằng chứng cần lưu, dữ liệu phải che và giới hạn quy trách nhiệm còn tồn tại.

Bản thiết kế đạt yêu cầu khi phân biệt được quản lý secret trong PAM với việc thực thi quyền và thu hồi tại API. Mỗi kết luận hoàn tất phải gắn với một trạng thái đã xác minh hoặc một giới hạn đã được owner chấp nhận.
