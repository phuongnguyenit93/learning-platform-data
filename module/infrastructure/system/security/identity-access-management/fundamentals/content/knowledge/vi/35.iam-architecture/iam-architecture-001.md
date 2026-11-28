# Centralized IAM

## 1. IAM tập trung là gì?

**Centralized IAM** là kiến trúc trong đó một tập năng lực quản lý danh tính và truy cập được tổ chức quanh các cơ quan có thẩm quyền chung: kho danh tính, dịch vụ xác thực, chính sách cấp quyền, quy trình vòng đời hoặc công cụ quản trị. Các ứng dụng sử dụng những năng lực này thay vì mỗi ứng dụng tự duy trì toàn bộ tài khoản, mật khẩu, MFA và quy trình cấp quyền riêng.

Ví dụ, một tổ chức có cổng học, hệ thống tài liệu và công cụ hỗ trợ. Với IAM rời rạc, mỗi nơi có tài khoản và cơ chế khôi phục khác nhau; nhân viên nghỉ việc phải được xử lý ở nhiều nơi. Với IAM tập trung, các ứng dụng có thể dùng chung nguồn danh tính và dịch vụ đăng nhập, còn việc cấp phát, thu hồi và kiểm toán được điều phối theo quy trình thống nhất.

Tập trung ở đây nói về **thẩm quyền, chính sách và trách nhiệm quản trị**, không nhất thiết nói về một máy chủ hoặc một database duy nhất. Một nền tảng IAM có thể có nhiều instance, nhiều vùng triển khai, các điểm xác minh cục bộ và cơ chế dự phòng nhưng vẫn được quản trị tập trung.

Cũng không nên hiểu centralized IAM là “mọi yêu cầu đều phải gọi một máy chủ trung tâm” hoặc “IdP quyết định được mọi quyền của mọi tài nguyên”. Hai quyết định kiến trúc cần tách riêng là:

- Ai quản trị và phát hành thông tin danh tính, chính sách, quyền?
- Quyết định và thực thi kiểm soát truy cập diễn ra ở đâu, vào lúc nào?

## 2. Có thể tập trung những năng lực nào?

| Năng lực | Phần có thể tập trung | Trách nhiệm vẫn cần ở hệ thống sử dụng |
| --- | --- | --- |
| Kho danh tính | Định danh ổn định, thuộc tính, liên kết nguồn | Mapping đúng tài khoản, namespace và tenant |
| Xác thực | Đăng nhập, MFA, khôi phục, mức bảo đảm | Xác minh kết quả và bảo vệ phiên ứng dụng |
| SSO/federation | Trust, client registration, chính sách phát hành claims | Kiểm tra issuer, bên nhận và ràng buộc giao dịch phù hợp |
| Cấp phát tài khoản | Quy trình tạo, cập nhật, vô hiệu hóa downstream | Áp dụng thay đổi và cung cấp kết quả xác minh |
| Quản lý quyền | Role, entitlement, phê duyệt, access review | Quyền trên đối tượng và điều kiện nghiệp vụ của tài nguyên |
| Chính sách | Quy tắc chung, phiên bản, phát hành và kiểm soát thay đổi | Thực thi đầy đủ tại đường truy cập cần bảo vệ |
| Audit | Tập hợp sự kiện và điều tra thay đổi quyền | Phát sự kiện có ngữ nghĩa chính xác, bảo vệ dữ liệu nhạy cảm |
| Danh tính workload | Cấp và quản lý vòng đời danh tính máy/dịch vụ | Xác minh caller, audience và quyền truy cập downstream |

Không bắt buộc mọi năng lực nằm trong một sản phẩm. Hệ thống nhân sự có thể là nguồn có thẩm quyền về tình trạng nhân viên, IdP quản lý xác thực và một hệ thống governance điều phối phê duyệt quyền. Kiến trúc vẫn có thể tập trung nếu quyền sở hữu dữ liệu, luồng đồng bộ và các ranh giới được xác định rõ.

### 2.1. Phân biệt các mô hình thường bị gọi chung

| Mô hình | Đã tập trung | Chưa thể suy ra |
| --- | --- | --- |
| Dùng chung thư mục | Một phần dữ liệu tài khoản | MFA, session và quyền ứng dụng đã thống nhất |
| Xác thực tập trung/SSO | Đăng nhập và trust với IdP | Quyền đối tượng đã được kiểm tra đúng |
| Quản trị quyền tập trung | Cấp quyền, phê duyệt và rà soát | Mọi quyết định runtime đều phải gọi PDP từ xa |
| Quyết định quyền tập trung | Một dịch vụ quyết định chính sách chung | Điểm thực thi tại ứng dụng có thể được bỏ qua |
| Vòng đời tập trung | Điều phối joiner, mover, leaver | Tất cả phiên và token cũ bị thu hồi tức thời |

Một hệ thống có SSO nhưng quyền quản trị bị gán thủ công và không được thu hồi ở ứng dụng vẫn chưa có vòng đời truy cập được quản lý đầy đủ.

## 3. Các thành phần trong kiến trúc tham chiếu

### 3.1. Nguồn danh tính và kho định danh

Nguồn có thẩm quyền cung cấp những thông tin thuộc phạm vi của mình: hệ thống nhân sự về quan hệ lao động, đối tác về một tập danh tính liên kết, nền tảng vận hành về workload. Kho danh tính chuẩn hóa định danh và liên kết các nguồn theo quy tắc đã thiết kế.

Không gộp hai tài khoản chỉ vì có cùng email hoặc tên. Mapping cần có bằng chứng, namespace và quy tắc xử lý xung đột. Một lỗi liên kết ở kho tập trung có thể lan sang nhiều ứng dụng.

### 3.2. Identity Provider và dịch vụ xác thực

IdP thực hiện hoặc điều phối xác thực, áp dụng MFA/step-up theo chính sách và cung cấp kết quả cho ứng dụng. Các chức năng enrollment credential, khôi phục và quản trị phương thức xác thực cũng là phần quan trọng của miền bảo mật này.

Tập trung xác thực giúp ứng dụng không phải nhận mật khẩu của người dùng để tự xác minh, nhưng tạo ra một vùng có độ nhạy cảm cao. Nếu quy trình khôi phục tại IdP yếu, MFA ở luồng đăng nhập chính có thể bị vượt qua bằng một đường khác.

### 3.3. Quản lý entitlement và chính sách

Entitlement mô tả khả năng truy cập được cấp; RBAC và ABAC là những cách biểu diễn hoặc đánh giá quyền. Một nền tảng tập trung có thể quản lý role chung, quan hệ membership, quy trình phê duyệt và policy dành cho các miền tài nguyên.

Phải phân biệt role theo ứng dụng, tenant và phạm vi. Chuỗi `admin` không nên có nghĩa là quản trị mọi hệ thống chỉ vì được phát hành từ một IdP chung. Nguồn phát hành đáng tin cậy không thay thế việc kiểm tra ý nghĩa và phạm vi của quyền.

### 3.4. Điểm quyết định và điểm thực thi

**Policy Decision Point — PDP** đưa ra quyết định dựa trên chủ thể, hành động, tài nguyên, ngữ cảnh và chính sách. **Policy Enforcement Point — PEP** thực thi quyết định tại gateway, service, phương thức hoặc lớp truy cập dữ liệu phù hợp.

PDP có thể nằm tại dịch vụ trung tâm hoặc được triển khai cục bộ với chính sách do trung tâm phát hành. PEP phải hiện diện ở đường truy cập thực sự tới tài nguyên; một quyết định đúng nhưng không được thực thi vẫn không bảo vệ được hệ thống.

### 3.5. Provisioning, governance và audit

Provisioning tạo và đồng bộ tài khoản/membership với hệ thống đích. Governance xác định ai được yêu cầu, ai phê duyệt và khi nào cần rà soát quyền. Audit ghi nhận thay đổi và quyết định để giải thích việc truy cập.

Ba chức năng liên quan nhưng không thay thế nhau. Một sự kiện “đã gửi yêu cầu vô hiệu hóa” trong audit chưa chứng minh connector đã vô hiệu hóa tài khoản tại ứng dụng đích.

## 4. Tách đường quản trị khỏi đường phục vụ truy cập

Một cách nhìn hữu ích là tách hai nhóm hoạt động:

| Nhóm hoạt động | Ví dụ | Yêu cầu thiết kế nổi bật |
| --- | --- | --- |
| Quản trị và phân phối trạng thái | Tạo tài khoản, phê duyệt role, phát hành policy, thay trust, luân chuyển khóa | Thẩm quyền chặt, kiểm soát thay đổi, audit và tính nhất quán |
| Phục vụ giao dịch truy cập | Đăng nhập, cấp token, xác minh token, quyết định quyền, thực thi quyền | Độ trễ, sẵn sàng, giới hạn tải, độ mới và xử lý sự cố |

Các hệ thống có thể dùng tên control plane/data plane khác nhau cho từng thành phần. Điều quan trọng là xác định thao tác nào phụ thuộc đồng bộ vào đâu và thao tác quản trị nào có thể thay đổi hiệu lực truy cập.

Ví dụ, ứng dụng đang xác minh token bằng tập khóa đã được tin cậy có thể tiếp tục xử lý một số request khi giao diện quản trị IAM ngừng hoạt động. Tuy nhiên, khả năng đăng nhập mới, refresh token hoặc cập nhật quyền có thể vẫn phụ thuộc vào dịch vụ trung tâm.

Tách triển khai và quyền quản trị của các đường này giúp giảm việc một sự cố giao diện quản trị làm dừng toàn bộ runtime, đồng thời hạn chế việc một ứng dụng nghiệp vụ có quyền sửa cấu hình IAM trung tâm.

## 5. Luồng đăng nhập và truy cập API

### 5.1. Luồng đăng nhập tập trung

Ví dụ một ứng dụng dùng OIDC theo flow phù hợp:

```text
Người dùng → ứng dụng → IdP
                         │
                         ├─ xác thực và MFA theo chính sách
                         └─ trả kết quả theo giao thức

Ứng dụng xác minh kết quả → gắn đúng tài khoản → tạo phiên cục bộ
```

Ứng dụng phải dùng thư viện/giao thức đúng, kiểm tra nguồn phát hành, đối tượng nhận, thời hạn và các ràng buộc giao dịch tương ứng. Không chỉ giải mã một JWT rồi tin các trường trong payload.

OIDC cung cấp lớp danh tính trên nền OAuth 2.0; OAuth 2.0 tự nó không phải giao thức đăng nhập danh tính. SAML có thể phục vụ đăng nhập liên kết theo mô hình khác. Việc chọn một giao thức không tự giải quyết cấp phát tài khoản hoặc quyền đối tượng bên trong ứng dụng.

### 5.2. Luồng gọi API

Ở mức khái niệm:

```text
Caller trình credential dành cho API
  → API/gateway xác minh credential và ngữ cảnh
  → service xác định tài nguyên, hành động và tenant thực tế
  → áp dụng quyết định quyền
  → chỉ thực hiện thao tác được phép
  → phát sự kiện quan sát cần thiết
```

API cần loại credential phù hợp cho bên nhận; không dùng ID token của một ứng dụng như access token dùng chung cho mọi API. Nếu một service gọi service khác, phải phân biệt danh tính workload đang gọi với người dùng mà nó đang đại diện, nếu có.

Chuyển nguyên token qua nhiều service không phải một thiết kế ủy quyền mặc định. Cần xác định audience, phạm vi delegation và quyền của từng chặng. Một workload hợp lệ cũng không tự có quyền đọc mọi tài nguyên trong mạng nội bộ.

### 5.3. Gateway không thay thế quyền đối tượng

Gateway có thể xác minh token và chặn route không được phép, nhưng thường không biết đầy đủ ai sở hữu một bản ghi hoặc bản ghi thuộc tenant nào. Service cần kiểm tra quyền trên tài nguyên thực tế, kể cả khi request đã qua gateway.

Không tin một header như `X-User-Id` chỉ vì tên header có vẻ nội bộ. Nếu kiến trúc dùng header danh tính từ proxy, phải loại bỏ dữ liệu giả mạo từ bên ngoài, xác thực đường truyền/caller, giới hạn đường đi vòng và bảo vệ ngữ nghĩa của header. Các endpoint nội bộ, batch và consumer cũng cần ranh giới thực thi phù hợp.

## 6. Chọn vị trí ra quyết định quyền

### 6.1. IdP phát hành claims, ứng dụng quyết định

IdP hoặc dịch vụ token phát hành một tập claims được giới hạn. Ứng dụng xác minh token và áp dụng policy cục bộ dựa trên claims cùng dữ liệu tài nguyên.

Ưu điểm là request không nhất thiết phải gọi IAM trung tâm mỗi lần, độ trễ dễ kiểm soát và ứng dụng có thể dùng dữ liệu nghiệp vụ sẵn có. Đánh đổi là quyền trong token có thể cũ và logic ở nhiều ứng dụng cần được giữ nhất quán. Không phát hành toàn bộ group hay hồ sơ chỉ để mọi service tự suy luận.

### 6.2. PEP gọi PDP trung tâm

Ứng dụng gửi yêu cầu quyết định đến PDP với dữ liệu cần thiết đã được xác minh. PDP dùng policy và nguồn thuộc tính phù hợp rồi trả quyết định, nghĩa vụ thực thi và metadata cần thiết.

Ưu điểm là quản lý policy và quan sát quyết định tập trung hơn, có thể sử dụng trạng thái mới. Đánh đổi là mỗi request phụ thuộc vào độ trễ, khả năng sẵn sàng và năng lực của PDP cùng các nguồn thuộc tính. PDP trung tâm vẫn không biết đúng tài nguyên nếu PEP gửi dữ liệu thiếu hoặc không đáng tin cậy.

### 6.3. Policy quản trị tập trung, đánh giá cục bộ

Trung tâm phát hành policy/thuộc tính theo phiên bản tới một engine cục bộ, thư viện hoặc thành phần cạnh ứng dụng. Quyết định diễn ra gần tài nguyên, còn quy trình thay đổi và quản trị vẫn tập trung.

Ưu điểm là giảm số phụ thuộc mạng trên đường request. Đánh đổi là phải kiểm soát nguồn gói policy, phiên bản, độ mới, tính toàn vẹn và tình trạng phân phối. Một instance nhận policy muộn có thể cho kết quả khác instance đã cập nhật.

| Lựa chọn | Phụ thuộc trung tâm trên mỗi request | Thách thức nổi bật |
| --- | --- | --- |
| Claims và policy ứng dụng | Có thể thấp | Claims cũ, logic phân quyền phân tán |
| PDP từ xa | Cao hơn | Độ trễ, tải, lỗi phụ thuộc, độ đầy đủ của đầu vào |
| Engine cục bộ với policy được phân phối | Có thể thấp | Đồng bộ phiên bản, dữ liệu thuộc tính và invalidation |

Một tổ chức có thể kết hợp các lựa chọn theo rủi ro. Chẳng hạn, thao tác đọc ít nhạy cảm sử dụng trạng thái có thời hạn đã được xác minh, còn thay đổi đặc quyền cần quyết định với dữ liệu mới hơn. Điều kiện cụ thể phải được thiết kế rõ; không chuyển sang một đường cho phép rộng hơn khi đường chính gặp lỗi.

## 7. Vòng đời truy cập khi quản lý tập trung

### 7.1. Joiner: cấp quyền cho người mới

Nguồn có thẩm quyền ghi nhận danh tính mới; IAM liên kết đúng subject, tạo tài khoản hoặc membership và cấp quyền theo quy trình. Các ứng dụng nhận dữ liệu cần thiết, không mặc định sao chép toàn bộ hồ sơ nguồn.

Role khởi đầu phải dựa trên chính sách và phê duyệt phù hợp. Tạo được tài khoản không có nghĩa đã có đủ quyền; cũng không nên cấp role rộng để tránh lỗi provisioning trong giai đoạn đầu.

### 7.2. Mover: thay đổi vai trò hoặc đơn vị

Khi một người chuyển nhóm, hệ thống cần xem cả quyền mới phải cấp và quyền cũ phải thu hồi. Chỉ bổ sung role mới mà không gỡ quyền cũ sẽ tạo tích lũy đặc quyền dù danh tính được quản lý tập trung.

Quyền trực tiếp tại ứng dụng, quyền sở hữu tài nguyên và các ngoại lệ phải được đưa vào quy trình rà soát. Nếu IAM chỉ quản lý role cấp qua một connector, cần biết những đường cấp quyền khác còn nằm ngoài khả năng quan sát của nó.

### 7.3. Leaver: chấm dứt truy cập

Quy trình chấm dứt phải xử lý tài khoản, session, grant, credential cá nhân, membership và quyền downstream trong phạm vi quản lý. Trạng thái “disabled” ở thư mục không tự làm token tự chứa hoặc session ứng dụng cũ mất hiệu lực ngay.

Cần có mục tiêu về độ trễ thu hồi và bằng chứng tại từng đích. Event phát đi, queue đã nhận và connector đã gọi API là các mốc khác nhau với “ứng dụng đã từ chối truy cập”. Job phải phản ánh các đích còn chờ hoặc thất bại.

## 8. Tính nhất quán, cache và thu hồi quyền

### 8.1. Có nhiều đồng hồ hiệu lực

Một thay đổi quyền có thể đi qua nguồn danh tính, governance, kho IAM, quá trình phát token, cache PDP và cache/session ứng dụng. Độ mới nhìn thấy tại điểm thực thi phụ thuộc vào toàn bộ đường đi thực sự được sử dụng.

Ví dụ minh họa:

```text
09:00:00  Quyền được thu hồi tại hệ thống quản lý
09:00:10  Connector cập nhật membership ở ứng dụng
09:01:00  Một cache quyết định hết hạn
09:05:00  Access token cũ hết hiệu lực nếu không có kiểm tra thu hồi khác
```

Các mốc là ví dụ, không phải thời hạn khuyến nghị. Nếu API chỉ dựa vào token cũ, việc connector cập nhật lúc 09:00:10 không tự làm API nhận biết thay đổi ngay ở thời điểm đó.

### 8.2. Cache cần có hợp đồng

Cache quyết định phải gắn với các dữ liệu làm thay đổi ý nghĩa của quyết định: subject, hành động, tài nguyên, tenant, ngữ cảnh liên quan và phiên bản policy/thuộc tính theo thiết kế. Một cache key chỉ chứa user ID có thể tái sử dụng `allow` cho sai tài nguyên.

Cần xác định thời hạn, invalidation, độ mới tối đa và cách xử lý khi không thể refresh. Không giữ một quyết định cho phép vô thời hạn vì PDP đang lỗi. Nếu dùng policy đã biết an toàn gần nhất, phải xác định nguồn tin cậy, phạm vi thao tác và thời gian cho phép sử dụng.

### 8.3. Thu hồi không chỉ là token expiry

Token ngắn hạn có thể giảm cửa sổ thông tin cũ, nhưng không tự xử lý mọi session, refresh token, API key và cache. Cơ chế thu hồi có thể gồm tra cứu trạng thái, introspection khi phù hợp với loại token, phiên bản session/quyền hoặc các cơ chế được hệ thống hỗ trợ.

Phải đo được thời điểm thay đổi có hiệu lực tại điểm thực thi. Không tuyên bố thu hồi tức thời chỉ vì API quản trị trung tâm đã trả thành công.

## 9. Độ sẵn sàng và phạm vi ảnh hưởng

### 9.1. Tập trung thẩm quyền làm tăng tầm quan trọng của nền tảng

Nếu nhiều ứng dụng phụ thuộc cùng IdP, sự cố IdP có thể làm đăng nhập mới thất bại trên diện rộng. Một cấu hình policy sai hoặc một tài khoản quản trị trung tâm bị chiếm quyền cũng có thể ảnh hưởng nhiều tài nguyên.

Cần xem không chỉ tiến trình IAM mà cả database, cache, DNS, đồng bộ thời gian, khóa/chứng thư, mạng và các nguồn thuộc tính. Nhiều instance ứng dụng IAM cùng dùng một phụ thuộc duy nhất vẫn có thể có điểm lỗi chung.

### 9.2. Xác định hành vi khi từng thành phần lỗi

| Sự cố | Hành vi cần xác định trước |
| --- | --- |
| IdP không đáp ứng | Luồng đăng nhập/refresh nào thất bại; phiên hiện có tiếp tục theo điều kiện nào |
| PDP từ xa timeout | Từ chối hay dùng policy/cache còn hợp lệ trong phạm vi đã thiết kế |
| Không tải được khóa mới | Dùng tập khóa tin cậy hiện có theo vòng đời đã định; xử lý khóa chưa biết an toàn |
| Provisioning ngừng đồng bộ | Theo dõi backlog, giới hạn tác động và trạng thái thu hồi chưa hoàn tất |
| Kho thuộc tính không sẵn sàng | Xử lý thuộc tính bắt buộc không xác định, không tự coi là thỏa điều kiện |
| Pipeline audit lỗi | Cơ chế đệm, báo động và hành vi của thao tác cần bằng chứng bắt buộc |

Không có một lựa chọn fallback duy nhất cho mọi hành động. Tuy nhiên, lỗi phụ thuộc không được tự biến thành bằng chứng được phép. Nếu có chế độ suy giảm, nó phải được giới hạn theo loại hành động, độ mới và rủi ro đã được chấp nhận.

### 9.3. Phục hồi và truy cập khẩn cấp

Kiến trúc cần kiểm thử failover, khôi phục dữ liệu, khôi phục khóa và kiểm tra các quyền đã thu hồi không bị sống lại từ snapshot cũ. Chính sách và danh tính được phục hồi phải đạt trạng thái đủ mới trước khi mở lại đường truy cập liên quan.

Cơ chế break-glass, nếu cần, phải được bảo vệ riêng, giới hạn quyền và thời gian, có kiểm soát sử dụng và audit. Không tạo một tài khoản quản trị dùng chung không được giám sát chỉ vì muốn có đường dự phòng khi IdP ngừng hoạt động.

## 10. Bảo vệ miền quản trị và ranh giới tin cậy

Quyền sửa trust, cấp role, đặt lại MFA hoặc phát hành credential có thể làm thay đổi ai được vào nhiều hệ thống. Chúng phải được quản lý như đặc quyền, với xác thực mạnh, quyền tối thiểu, phân tách nhiệm vụ và kiểm soát thay đổi phù hợp.

Một ứng dụng cần xác minh token không vì thế mà cần quyền đọc password hash, sửa người dùng hoặc lấy khóa ký. Connector chỉ nên có quyền trên đối tượng và thao tác mà nó quản lý. API quản trị cần được tách khỏi đường truy cập nghiệp vụ và có bằng chứng về người thực hiện.

Trust giữa ứng dụng và IAM phải được cấu hình và xác minh rõ. Không tự tin một issuer tùy ý do request cung cấp; không chấp nhận mọi khóa công khai chỉ vì tải được qua mạng. Luân chuyển khóa, secret và metadata cần có quy trình tránh khoảng trống xác minh hoặc tiếp tục tin vật liệu đã bị thu hồi.

Trong hệ thống đa tenant, kiểm tra phạm vi phải tồn tại ở cả quản trị lẫn runtime. Quản trị viên của một tenant không được tự mở rộng quyền sang tenant khác bằng cách gửi một tenant ID khác trong request.

Với workload, dùng danh tính riêng cho dịch vụ hoặc tác vụ thay vì dùng tài khoản cá nhân của lập trình viên. Xác định nguồn cấp, thời hạn, quyền và chủ sở hữu; không dùng một secret toàn năng chung cho mọi service chỉ để giảm số lượng danh tính cần quản lý.

## 11. Riêng tư và quan sát trong một nền tảng tập trung

### 11.1. Tập trung không có nghĩa chia sẻ toàn bộ dữ liệu

IAM trung tâm có thể nhìn thấy quan hệ danh tính và hoạt động ở nhiều ứng dụng. Cần giới hạn phát hành claims theo bên nhận, tách định danh theo phạm vi khi phù hợp và không biến token thành bản sao hồ sơ.

Log tập trung nên giữ bằng chứng cần thiết cho sự kiện xác thực, thay đổi quyền và quyết định truy cập, tránh raw token, cookie, secret hoặc toàn bộ thuộc tính cá nhân. Định danh giả danh trong audit vẫn cần bảo vệ vì có thể liên kết hành vi qua thời gian.

### 11.2. Quan sát kết quả, không chỉ quan sát tiến trình

Những tín hiệu hữu ích gồm tỷ lệ đăng nhập hoàn tất, lỗi federation theo kết nối, độ trễ cấp token, lỗi đánh giá quyền, độ mới policy, độ trễ provisioning và thời gian từ yêu cầu thu hồi đến lúc bị từ chối tại ứng dụng.

Tách lỗi xác thực, deny đúng chính sách và lỗi phụ thuộc. Tỷ lệ deny tăng không tự động là sự cố; tỷ lệ deny giảm cũng không tự chứng minh policy tốt hơn, vì một thay đổi cấp quyền quá rộng có thể làm số lần từ chối giảm.

Liên kết sự kiện giữa nguồn thay đổi, IAM, connector và ứng dụng bằng tham chiếu nội bộ thích hợp. Metric cần nhãn hữu hạn như dịch vụ, môi trường và kết quả; user ID, email hoặc token không phù hợp làm nhãn tổng hợp.

## 12. Tình huống kiến trúc: ba ứng dụng nội bộ

Một tổ chức triển khai cổng học, kho tài liệu và công cụ hỗ trợ. Cả ba dùng chung IdP để xác thực và áp dụng chính sách MFA. Nguồn nhân sự cập nhật tình trạng nhân viên vào hệ thống vòng đời; governance điều phối quyền ứng dụng và connector đồng bộ membership.

Cổng học tự kiểm tra quyền trên khóa học bằng dữ liệu tenant và entitlement được giới hạn. Kho tài liệu dùng engine đánh giá cục bộ với policy do trung tâm phát hành. Công cụ hỗ trợ gọi PDP cho thao tác thay đổi đặc quyền có yêu cầu dữ liệu mới hơn. Đây vẫn là kiến trúc IAM có quản trị tập trung dù cách đánh giá runtime khác nhau.

Một nhân viên chuyển bộ phận. Quy trình xác định role mới và thu hồi role cũ, phát hành thay đổi, theo dõi connector và kiểm tra các điểm thực thi. Quyền gán trực tiếp ngoại lệ được rà soát riêng để tránh tích lũy đặc quyền.

Sau đó PDP của công cụ hỗ trợ gặp lỗi. Thao tác cần quyết định mới không được tự động cho phép; giao diện có thể báo lỗi phù hợp. Các luồng khác chỉ tiếp tục nếu vẫn đáp ứng điều kiện xác minh và độ mới đã thiết kế. Khả năng tiếp tục của một ứng dụng không được suy diễn thành việc mọi loại truy cập đều an toàn.

Khi IdP bị gián đoạn, hệ thống theo dõi riêng đăng nhập mới, refresh và session hiện có. Kịch bản này được kiểm thử để đội vận hành biết ứng dụng nào còn phục vụ được chức năng nào, thay vì mặc định mọi nơi cùng dừng hoặc cùng tiếp tục.

## 13. Đưa kiến trúc tập trung vào hệ thống hiện hữu

Một quá trình chuyển đổi có thể đi theo các bước sau:

1. Kiểm kê ứng dụng, nguồn tài khoản, credential, quyền và người chịu trách nhiệm.
2. Thiết kế namespace và mapping danh tính; xử lý trùng và liên kết tài khoản có bằng chứng.
3. Tích hợp đăng nhập cho một phạm vi thử nghiệm, kiểm tra phiên và ràng buộc giao thức.
4. Xác định quyền vẫn nằm ở ứng dụng, quyền được quản trị tập trung và đường thực thi tương ứng.
5. Đồng bộ vòng đời, gồm cả thu hồi và xử lý lỗi connector, không chỉ tạo tài khoản.
6. Kiểm thử độ mới, cache, failover, khôi phục và quyền quản trị khẩn cấp.
7. Chuyển đổi theo từng nhóm, theo dõi quyền hiệu lực và xử lý tài khoản/đường đăng nhập cũ theo kế hoạch.

Không nhập hàng loạt tài khoản rồi ghép theo email mà không xem xét xung đột và namespace. Không giữ đường đăng nhập cũ có mật khẩu yếu hoạt động vô thời hạn bên cạnh MFA mới; nếu còn đường tương thích, cần xác định phạm vi, thời hạn và mức bảo vệ của nó.

Các tích hợp có thể dùng giao thức như OIDC/SAML cho federation hoặc cơ chế provisioning như SCIM khi hệ thống hỗ trợ. Mỗi cơ chế phục vụ một phần bài toán; việc tích hợp một giao thức không chứng minh toàn bộ vòng đời IAM đã hoàn tất.

## 14. Các câu hỏi cần trả lời khi đánh giá thiết kế

| Câu hỏi | Vì sao cần trả lời |
| --- | --- |
| Nguồn có thẩm quyền cho từng thuộc tính là gì? | Tránh dữ liệu xung đột và cấp quyền từ nguồn không đáng tin |
| Điều gì được tập trung, điều gì vẫn do miền ứng dụng sở hữu? | Tránh khoảng trống trách nhiệm hoặc ôm quá nhiều quyền vào một nơi |
| PEP nằm ở những đường truy cập nào? | Tránh API nội bộ, batch hoặc đường dữ liệu đi vòng kiểm soát |
| Token/claim/policy có thể cũ tối đa bao lâu? | Đánh giá cửa sổ thu hồi và rủi ro cache |
| Khi IdP/PDP/nguồn thuộc tính lỗi, từng thao tác sẽ ra sao? | Bảo đảm chế độ suy giảm có điều kiện rõ ràng |
| Ai có thể sửa trust hoặc cấp đặc quyền? | Kiểm soát phạm vi ảnh hưởng của tài khoản quản trị |
| Bằng chứng thu hồi tại ứng dụng là gì? | Phân biệt thay đổi đã gửi với quyền đã mất hiệu lực |
| Phục hồi có làm sống lại tài khoản hoặc quyền cũ không? | Kiểm tra tính đúng của trạng thái sau sự cố |
| Mỗi ứng dụng thật sự cần nhận thuộc tính nào? | Hạn chế dữ liệu danh tính lan rộng |

Centralized IAM mang lại khả năng quản trị danh tính và vòng đời truy cập nhất quán khi trách nhiệm và ranh giới được thiết kế rõ. Hiệu quả của kiến trúc nằm ở việc mỗi ứng dụng tin đúng nguồn, thực thi đúng quyền và phản ánh đúng thay đổi vòng đời, đồng thời nền tảng trung tâm được bảo vệ và vận hành tương xứng với phạm vi ảnh hưởng của nó.
