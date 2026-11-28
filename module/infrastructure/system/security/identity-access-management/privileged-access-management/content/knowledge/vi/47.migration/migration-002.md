# Migrate shared account: chuyển tài khoản dùng chung vào PAM

## 1. Mục tiêu và phạm vi

Một tài khoản dùng chung (shared account) là tài khoản được nhiều người hoặc nhiều thành phần sử dụng dưới cùng một định danh ở hệ thống đích. Ví dụ thường gặp là tài khoản quản trị cục bộ của máy chủ, tài khoản quản trị thiết bị mạng, tài khoản hỗ trợ trên ứng dụng hoặc một tài khoản quản trị cơ sở dữ liệu đã được nhiều nhóm cùng biết mật khẩu.

Chuyển tài khoản đó vào Privileged Access Management (PAM) không chỉ là tạo một bản ghi trong vault. Mục tiêu là chuyển quyền kiểm soát credential, cách cấp quyền sử dụng, đường truy cập và bằng chứng hoạt động sang một quy trình có chủ sở hữu, kiểm soát và kiểm chứng được.

Sau bài này, người học có thể:

- Xác định một tài khoản dùng chung phục vụ thao tác của con người, workload hay cả hai.
- Lập bản đồ người dùng, credential, hệ thống đích và các dependency trước khi thay đổi mật khẩu.
- Chọn giữa loại bỏ tài khoản dùng chung, giữ nó làm tài khoản đích phía sau PAM hoặc cô lập tạm theo ngoại lệ.
- Lập kế hoạch pilot, cutover, rotation đầu tiên, kiểm thử và khôi phục truy cập.
- Xác định bằng chứng cần có để tuyên bố một tài khoản đã migrate hoàn tất.

Bài tập trung vào tài khoản dùng chung có đặc quyền trong phạm vi quản trị hệ thống, ứng dụng và hạ tầng nhạy cảm. Mẫu cấu hình và runbook trong bài là ví dụ thiết kế trung lập với nhà cung cấp, không phải cú pháp import trực tiếp của một sản phẩm PAM.

## 2. Điều gì phải thay đổi sau migration?

### 2.1. Phân biệt ba lớp định danh

Một phiên quản trị qua PAM có thể có ba định danh khác nhau:

| Lớp | Ví dụ | Câu hỏi phải trả lời |
|---|---|---|
| Người yêu cầu | Người dùng cá nhân `ops.an` | Ai được xác thực và yêu cầu quyền? |
| Phiên hoặc yêu cầu PAM | `REQ-4821`, `SESSION-771` | Quyền được cấp theo chính sách nào, trong khoảng thời gian nào? |
| Tài khoản tại hệ thống đích | `ops_shared` trên `app-prod-07` | Tài khoản nào thực thi thao tác ở đích? |

Giữ `ops_shared` làm tài khoản đích không đồng nghĩa với việc tiếp tục cho cả nhóm dùng chung một tài khoản đăng nhập PAM. Mỗi người phải có định danh cá nhân ở lớp yêu cầu; PAM mới có cơ sở gắn người dùng với việc sử dụng tài khoản đích.

Nếu ứng dụng đích hỗ trợ tài khoản cá nhân và phân quyền phù hợp, loại bỏ tài khoản dùng chung có thể đem lại khả năng quy trách nhiệm tốt hơn. Nếu hệ thống cũ chỉ hỗ trợ một tài khoản quản trị, có thể giữ tài khoản đó ở phía sau cơ chế cấp phiên hoặc cấp credential được quản lý.

### 2.2. So sánh trạng thái trước và sau

| Khía cạnh | Trước migration | Trạng thái mong muốn |
|---|---|---|
| Đăng nhập | Cả nhóm biết cùng một mật khẩu | Người dùng xác thực cá nhân, thường kèm MFA |
| Cấp quyền | Biết mật khẩu là có thể dùng | Có quyền trên đúng đối tượng, đúng thời gian và đúng mục đích |
| Lưu credential | Ghi chú, tệp, công cụ chia sẻ hoặc trí nhớ | Vault kiểm soát lưu trữ, truy xuất và vòng đời |
| Đường truy cập | Nhiều đường trực tiếp ít được theo dõi | Các đường được phê duyệt và kiểm soát rõ ràng |
| Rotation | Thực hiện thủ công, thiếu dependency | Có cơ chế thay đổi và kiểm tra đăng nhập sau thay đổi |
| Điều tra | Log chỉ thấy `ops_shared` | Liên kết người dùng, yêu cầu, phiên PAM và sự kiện đích |
| Thu hồi | Khó thu hồi vì người dùng vẫn biết mật khẩu | Thu hồi quyền cá nhân, xử lý credential và phiên còn hiệu lực |

Việc bổ sung MFA ở cổng PAM không tự bảo vệ một đường SSH, RDP, console hoặc API vẫn cho phép dùng trực tiếp mật khẩu cũ. Cần kiểm chứng cả đường truy cập thực tế ở đích.

### 2.3. Hai kiểu sử dụng cần kiểm soát khác nhau

**Cấp phiên qua proxy hoặc broker:** người dùng yêu cầu một phiên tới đích; PAM có thể sử dụng credential mà không tiết lộ trực tiếp cho người dùng. Khả năng che credential, ghi hình hoặc ghi lệnh phụ thuộc sản phẩm, giao thức và cách triển khai, cần kiểm tra bằng thử nghiệm.

**Cấp credential để sử dụng:** người dùng được xem hoặc lấy credential trong thời hạn cho phép. Việc checkout hết hạn chỉ kết thúc quyền cấp phát theo PAM; mật khẩu tĩnh đã được tiết lộ không tự mất hiệu lực ở đích nếu chưa đổi hoặc vô hiệu hóa bằng cơ chế tương ứng.

Khi phải tiết lộ credential, nên cân nhắc checkout độc quyền nếu hệ thống hỗ trợ, thời hạn ngắn và rotation sau sử dụng. Kiểm tra tác động đến phiên đang mở và workload trước khi áp dụng. Rotation mật khẩu thường không đồng nghĩa với việc chấm dứt mọi phiên hoặc token đã được cấp trước đó.

## 3. Chọn đích migration trước khi chọn công cụ

### 3.1. Tài khoản dùng chung không phải lúc nào cũng cần giữ

Phân loại từng tài khoản theo chức năng và khả năng hệ thống:

| Tình huống | Hướng xử lý ưu tiên | Điểm cần xác minh |
|---|---|---|
| Nhiều quản trị viên dùng chung tài khoản nhưng đích hỗ trợ định danh cá nhân | Tạo quyền cá nhân, áp dụng least privilege và loại bỏ nhu cầu dùng chung | Không tạo hàng loạt tài khoản có quyền rộng ngang tài khoản cũ |
| Thiết bị chỉ có một tài khoản quản trị phù hợp | Giữ tài khoản đích, đặt sau PAM và kiểm soát đường truy cập | Khả năng gắn người dùng với phiên, xử lý phiên đồng thời |
| Một tài khoản được nhiều ứng dụng cùng sử dụng | Tách thành danh tính workload theo ứng dụng hoặc ranh giới trách nhiệm | Dependency, khả năng nạp credential mới và rollback |
| Con người và dịch vụ cùng sử dụng một tài khoản | Tách hai luồng trước khi áp dụng chính sách rotation cho người dùng | Dịch vụ không bị đổi mật khẩu ngoài kế hoạch |
| Tài khoản không còn nhu cầu sử dụng | Vô hiệu hóa hoặc xóa theo quy trình đã phê duyệt | Quan sát đủ chu kỳ vận hành và giữ đường phục hồi phù hợp |
| Tài khoản phục vụ truy cập khẩn cấp | Quản lý theo quy trình break-glass riêng | Có thể dùng trong tình huống mất thành phần PAM hoặc IdP dự kiến |

Không chuyển cả một nhóm người vào chung một danh tính PAM để giữ nguyên thói quen cũ. Cách đó làm mất cơ sở phân quyền cá nhân ngay ở lớp kiểm soát mới.

### 3.2. Least privilege và JIT/JEA trong kế hoạch

Nếu tài khoản cũ có quyền quản trị toàn hệ thống nhưng người vận hành chỉ cần xem log hoặc khởi động một dịch vụ, đưa nguyên quyền đó vào vault mới chỉ thay đổi cách giữ mật khẩu. Cần xem xét phân tách vai trò, quyền vừa đủ cho nhiệm vụ (JEA) và quyền chỉ cấp khi cần (JIT), nếu hệ thống và sản phẩm hỗ trợ.

Trong kế hoạch cần nói rõ thứ gì hết hạn: quyền yêu cầu, quyền lấy credential, phiên truy cập hay quyền thực thi trên hệ thống đích. Một TTL ở PAM không tự biến tài khoản quản trị tĩnh thành tài khoản hết quyền tại đích.

Có thể chia migration thành hai mốc: đưa credential và đường truy cập vào kiểm soát trước, rồi giảm quyền theo một thay đổi riêng. Nếu chọn cách này, ghi rõ quyền rộng còn tồn tại, người chấp nhận rủi ro và hạn xử lý; không đánh dấu đã hoàn thành mục tiêu least privilege khi chưa kiểm chứng.

## 4. Kiểm kê tài khoản và dependency

### 4.1. Đơn vị kiểm kê là tài khoản trên một phạm vi xác thực

Hai máy có cùng username `admin` không nhất thiết dùng chung một danh tính. Ngược lại, một tài khoản miền hoặc tài khoản ứng dụng tập trung có thể tác động tới nhiều hệ thống.

Mỗi bản ghi nên có định danh gồm phạm vi xác thực, hệ thống hoặc nhóm hệ thống chịu ảnh hưởng và username. Phải phân biệt tài khoản cục bộ, tài khoản miền, tài khoản cơ sở dữ liệu và tài khoản ứng dụng trước khi xác định blast radius của rotation.

Các trường kiểm kê quan trọng:

- Mã tài khoản, username, hệ thống đích, môi trường và phạm vi xác thực.
- Chủ sở hữu nghiệp vụ, chủ sở hữu kỹ thuật và người có quyền quyết định thay đổi.
- Quyền hiện tại, mục đích sử dụng, mức nhạy cảm của dữ liệu và dịch vụ.
- Những người, nhóm, công cụ và workload đang sử dụng tài khoản.
- Phương thức xác thực: mật khẩu, SSH key, certificate, token hoặc cơ chế khác.
- Nơi lưu credential đã biết và cách người dùng đang lấy credential.
- Các đường truy cập: giao thức, nguồn kết nối, console và đường quản trị ngoài băng.
- Khả năng đổi credential, giới hạn định dạng, lịch bảo trì và khả năng kiểm tra đăng nhập.
- Những phiên, kết nối hoặc token còn hiệu lực độc lập với mật khẩu.
- Cơ chế khôi phục, quản trị tài khoản và xử lý khi tài khoản bị khóa.

Tệp kiểm kê chỉ lưu tham chiếu tới secret được bảo vệ. Không đưa mật khẩu, private key, token hoặc bản sao credential vào bảng migration, ticket và log kiểm thử.

### 4.2. Dependency cần thu thập từ nhiều nguồn

Phỏng vấn quản trị viên là một nguồn, nhưng thường không đủ. Có thể đối chiếu log xác thực, cấu hình dịch vụ, bộ lập lịch, pipeline, công cụ giám sát, kho cấu hình và thông tin từ chủ ứng dụng trong phạm vi được phép.

Với mỗi dependency, cần biết nơi lấy credential, thời điểm sử dụng, cơ chế cache, cách nạp lại và cách kiểm tra thành công. Một tác vụ sao lưu chạy mỗi tuần có thể không xuất hiện trong một cửa sổ quan sát hai giờ.

Phân biệt ba nhóm dependency:

1. **Tương tác:** quản trị viên, nhà cung cấp hỗ trợ, nhóm trực ca.
2. **Không tương tác:** service, job, tác vụ sao lưu, pipeline, giám sát hoặc script tự động.
3. **Khôi phục:** tác vụ phục hồi, tài khoản sửa mật khẩu, đường console và quy trình break-glass.

Thời gian quan sát phải phủ các chu kỳ sử dụng có liên quan hoặc có bằng chứng thử nghiệm thay thế. Việc chưa thấy log không chứng minh rằng tài khoản không còn dependency.

### 4.3. Mẫu kiểm kê không chứa secret

```yaml
# Ví dụ thiết kế, không phải schema import của sản phẩm PAM.
account_id: pam-mig-002
identity:
  username: ops_shared
  authority: local-app-prod-07
  target: app-prod-07
environment: production
owners:
  business: application-owner
  technical: platform-operations
usage:
  interactive:
    - platform-oncall
  non_interactive:
    - nightly-health-check
    - monthly-export
credential:
  type: password
  location_reference: approved-secret-record
  value: OMITTED
access_paths:
  - approved-management-network
  - approved-recovery-console
migration:
  target_pattern: individual-request-to-shared-target
  dependency_review: pending
  first_rotation: blocked-until-dependencies-verified
  change_reference: CHG-4821
```

`authority` trong ví dụ giúp phân biệt tài khoản cục bộ này với tài khoản có cùng tên ở nơi khác. Giá trị `OMITTED` nhấn mạnh đây là tài liệu kế hoạch; secret thật phải đi qua cơ chế tiếp nhận được phê duyệt của vault.

### 4.4. Dấu hiệu phải dừng trước rotation

Chưa nên đổi credential khi chưa có người chịu trách nhiệm cho một dependency đang hoạt động, chưa biết cách khôi phục tài khoản hoặc chưa xác định đúng phạm vi tác động. Tương tự, nếu việc nhập credential vào PAM tự động kích hoạt rotation thì phải xử lý dependency trước khi bật cơ chế đó.

Có thể tiếp tục làm sạch kiểm kê, thiết kế quyền và thử connector trên môi trường phù hợp trong lúc chờ. Việc cần dừng là thay đổi có thể làm đứt truy cập, không phải mọi hoạt động chuẩn bị.

## 5. Thiết kế quyền sở hữu và chính sách PAM

### 5.1. Tách quyền sử dụng khỏi quyền quản trị vault

Một người được mở phiên tới tài khoản không nhất thiết được xem mật khẩu, sửa chính sách, đổi owner hoặc xóa bản ghi. Nhóm quản trị PAM cũng không nên mặc nhiên được sử dụng toàn bộ tài khoản nghiệp vụ chỉ vì họ vận hành nền tảng.

| Vai trò | Trách nhiệm trong migration |
|---|---|
| Chủ hệ thống | Xác nhận nhu cầu, dependency và khả năng vận hành sau cutover |
| Chủ ứng dụng | Kiểm chứng luồng nghiệp vụ và workload dùng credential |
| Nhóm PAM | Tạo bản ghi, connector, chính sách và bằng chứng vận hành PAM |
| Nhóm IAM | Bảo đảm danh tính cá nhân, nhóm truy cập và luồng thu hồi |
| Nhóm mạng/hệ điều hành | Triển khai và kiểm tra đường quản trị được phê duyệt |
| Nhóm giám sát | Nhận sự kiện, xác nhận cảnh báo và khả năng truy vết |
| Người điều phối thay đổi | Ra quyết định go/no-go, ghi mốc cutover và kích hoạt phương án phục hồi |

Một cá nhân có thể đảm nhiệm nhiều vai trò trong tổ chức nhỏ, nhưng vẫn cần chỉ rõ ai phê duyệt và ai thực thi. Đối với tài khoản nhạy cảm, cân nhắc tách nhiệm vụ và phê duyệt độc lập theo chính sách.

### 5.2. Những quyết định cần chốt

Trước cutover phải có câu trả lời cho các câu hỏi sau:

- Ai được yêu cầu dùng tài khoản và nhóm đó được quản lý từ nguồn nào?
- Ai được phê duyệt, trong trường hợp nào và ngoài giờ làm việc xử lý ra sao?
- Cho phép lấy credential, chỉ mở phiên hay cả hai?
- Có cho phép nhiều phiên đồng thời không, và sự đồng thời ảnh hưởng truy vết thế nào?
- Thời hạn yêu cầu, phiên và quyền truy xuất được đặt ra sao?
- Rotation diễn ra định kỳ, sau tiết lộ, sau phiên hay theo sự kiện?
- Khi rotation hoặc kiểm tra credential thất bại, tài khoản chuyển sang trạng thái nào?
- Ai được thực hiện reconcile/reset và quyền đó được bảo vệ như thế nào?
- Log, recording và thông tin nhạy cảm trong phiên được truy cập và lưu giữ ra sao?

Đừng bật đồng thời tất cả tính năng kiểm soát mới mà chưa có tiêu chí thử nghiệm. Mỗi kiểm soát phải có hành vi mong đợi, cách xác minh và cách xử lý khi gây lỗi.

### 5.3. Credential dùng để quản lý credential

Một connector có thể cần quyền đổi mật khẩu hoặc tài khoản khôi phục riêng để sửa lệch trạng thái. Những quyền này cũng là đặc quyền và cần nằm trong phạm vi kiểm kê, phân quyền và giám sát.

Không thiết kế một vòng phụ thuộc mà chỉ dùng tài khoản đang lỗi mới có thể sửa chính tài khoản đó. Đồng thời, một tài khoản reconcile có quyền rộng trên nhiều đích sẽ làm tăng blast radius; cần giới hạn phạm vi và thử đúng quyền tối thiểu mà cơ chế quản lý yêu cầu.

## 6. Lập các đợt migration và tiêu chí go/no-go

### 6.1. Gom đợt theo dependency

Đợt migration nên là đơn vị có thể kiểm thử và khôi phục độc lập, không đơn giản là một số lượng username. Nhiều tài khoản cùng dùng một connector, cùng thuộc một cụm ứng dụng hoặc cùng dùng một pipeline cập nhật secret có thể tạo ra rủi ro liên quan.

Pilot nên có phạm vi tác động hạn chế nhưng đại diện cho kiểu tích hợp thực tế. Một tài khoản lab không có workload không chứng minh được rằng việc đổi tài khoản production có job định kỳ sẽ an toàn.

Ví dụ chia đợt:

1. Tài khoản quản trị tương tác trên hệ thống ít phụ thuộc.
2. Tài khoản quản trị trên hệ thống production có cửa sổ bảo trì và owner trực.
3. Tài khoản có workload sau khi đã tách danh tính hoặc hoàn thành tích hợp secret.
4. Tài khoản nhạy cảm, hệ thống cũ và các trường hợp cần ngoại lệ có thời hạn.

Đây là cách tổ chức ví dụ; mức ưu tiên thực tế còn phụ thuộc nguy cơ lộ credential, mức nhạy cảm, khả năng gián đoạn và nhu cầu xử lý khẩn cấp.

### 6.2. Gate trước thay đổi đầu tiên

Chỉ quyết định go khi những điều kiện của đợt đã được kiểm chứng:

- Đúng tài khoản và đúng hệ thống; owner xác nhận phạm vi tác động.
- Credential hiện tại được tiếp nhận an toàn và kiểm tra hợp lệ theo quy trình.
- Dependency đã có người chịu trách nhiệm, phương án cập nhật và kiểm thử.
- Connector có đường kết nối, quyền và định dạng credential phù hợp.
- Chính sách quyền, MFA, phê duyệt và thời hạn đã được thử.
- Có đường khôi phục độc lập phù hợp với sự cố dự kiến.
- Cơ chế ghi log và liên kết bằng chứng hoạt động.
- Có người quyết định, người xử lý sự cố, thời gian tối đa và điều kiện rollback.

Giới hạn thời gian, ngưỡng lỗi và số lần retry phải được quyết định trong kế hoạch của hệ thống. Các con số minh họa trong tài liệu không thay thế những giới hạn đó.

## 7. Quy trình migration từ chuẩn bị tới cutover

### Bước 1 — Chốt baseline và quyền thay đổi

Ghi nhận hiện trạng tài khoản, quyền, credential reference, luồng truy cập, các phiên đã mở và trạng thái dịch vụ. Lưu các cấu hình cần phục hồi trong nơi được bảo vệ; backup chứa secret phải được xử lý như secret.

Xác định ai đang có quyền đổi credential. Trong cửa sổ cutover cần tránh việc nhóm cũ và PAM cùng đổi mật khẩu độc lập. Một thay đổi ngoài kế hoạch có thể làm vault giữ credential khác với credential ở đích.

### Bước 2 — Tách dependency không phù hợp

Nếu tài khoản dùng cho cả con người và một tác vụ tự động, tạo hoặc chuyển tác vụ sang danh tính riêng khi có thể. Workload cần quyền và vòng đời credential riêng; không dùng quyền checkout của con người làm cơ chế cấp secret cho dịch vụ chạy nền.

Nếu chưa thể tách, ghi rõ toàn bộ consumer và phối hợp cập nhật. Có thể cần dừng consumer, thực hiện rotation trong cửa sổ thay đổi rồi nạp credential mới và mở lại. Không giả định hệ thống hỗ trợ hai mật khẩu cùng tồn tại; chỉ dùng cơ chế chuyển tiếp song song nếu đích thực sự hỗ trợ và đã thử nghiệm.

### Bước 3 — Onboard vào PAM ở chế độ kiểm soát phù hợp

Tạo đúng một bản ghi quản lý cho danh tính trong phạm vi đã xác định, gán owner, nhóm quyền và chính sách. Thực hiện nhập credential bằng phương thức được phê duyệt, tránh để secret xuất hiện trong command history hoặc log.

Nếu sản phẩm hỗ trợ giai đoạn onboard chưa tự đổi credential, dùng nó để xác minh ánh xạ và khả năng truy cập trước khi bật rotation. Nếu onboarding tự đổi credential, coi đó là một phần của cutover và áp dụng đầy đủ gate trước thay đổi.

Không để hai hệ thống PAM hoặc hai job rotation cùng là nguồn quản lý chủ động cho một credential. Khi chuyển từ công cụ cũ, cần có điểm chuyển quyền quản lý rõ ràng và dừng các job cũ trước khi công cụ mới nhận trách nhiệm.

### Bước 4 — Thử luồng yêu cầu và phiên pilot

Người vận hành sử dụng danh tính cá nhân, thực hiện MFA và yêu cầu quyền theo chính sách. Người phê duyệt kiểm tra phạm vi và mục đích, sau đó người dùng mở phiên hoặc nhận credential theo thiết kế.

Chọn thao tác xác minh ít tác động, đã được owner đồng ý. Kiểm tra tài khoản đích, quyền thực tế và sự kiện tại hệ thống. Nếu cần thử chức năng ghi hoặc quản trị đặc biệt, dùng đối tượng thử và điều kiện hoàn tác đã được phê duyệt.

Kết thúc phiên và kiểm tra hành vi khi yêu cầu hết hạn. Kiểm chứng cả trường hợp không được cấp quyền; chỉ thử thành công chưa đủ để chứng minh chính sách có hiệu lực.

### Bước 5 — Thực hiện rotation đầu tiên và xác minh lại

Rotation đầu tiên là một phép thử quan trọng: nó chứng minh PAM có thể thay đổi credential ở đích, giữ giá trị đúng và sử dụng giá trị mới. Một thao tác ghi secret vào vault chưa chứng minh được những điều đó.

Trình tự logic cần có:

1. Xác nhận cửa sổ thay đổi, trạng thái workload và đường phục hồi.
2. Thực hiện rotation qua cơ chế đã chọn.
3. Kiểm tra trạng thái thao tác và trạng thái bản ghi PAM.
4. Thực hiện một xác thực mới từ luồng được phê duyệt.
5. Kiểm tra consumer không tương tác và các chức năng liên quan.
6. Xác nhận credential cũ không còn được chấp nhận bằng phép thử có kiểm soát, nếu phép thử này nằm trong kế hoạch.
7. Xử lý các phiên và token cũ theo cơ chế riêng của hệ thống.

Phép thử credential cũ có thể gây tăng bộ đếm lỗi đăng nhập hoặc khóa tài khoản. Giới hạn số lần thử và phối hợp với chính sách lockout; không thực hiện vòng lặp thử credential để đoán trạng thái.

### Bước 6 — Chuyển đường truy cập và xử lý kênh cũ

Sau khi đường mới được kiểm chứng, áp dụng các thay đổi để người dùng thông thường chỉ truy cập qua đường được phê duyệt. Có thể cần phối hợp quy tắc mạng, cấu hình giao thức, quyền hệ điều hành, nhóm nguồn và quy trình vận hành.

Đường khôi phục ngoài PAM, nếu được giữ, phải có owner, giới hạn quyền, cơ chế kiểm soát credential và giám sát riêng. Một ngoại lệ được quản lý khác với một cửa hậu vẫn mở vì chưa ai kiểm tra.

Thu hồi quyền trên các kho credential cũ và xử lý bản sao đã biết theo chính sách. Việc xóa một tệp chia sẻ không chứng minh mọi người đã quên mật khẩu; rotation mới là bước vô hiệu hóa các bản sao của credential cũ, nếu không còn cơ chế xác thực thay thế sử dụng cùng quyền.

### Bước 7 — Theo dõi tăng cường và bàn giao

Trong giai đoạn sau cutover, theo dõi lỗi xác thực, lỗi rotation, yêu cầu bị từ chối bất thường, truy cập trực tiếp, job định kỳ và phản hồi của nhóm vận hành. Quan sát các chu kỳ nghiệp vụ đủ để đánh giá dependency đã xác định.

Bàn giao cho nhóm vận hành khi có runbook, người trực, cảnh báo, bằng chứng và danh sách ngoại lệ còn hiệu lực. Không kéo dài vô hạn trạng thái hỗ trợ đặc biệt để che việc chưa có owner hoặc chưa có quy trình vận hành thường xuyên.

## 8. Tình huống minh họa: tài khoản quản trị có dependency ẩn

### 8.1. Hiện trạng

`ops_shared` là tài khoản quản trị cục bộ trên `app-prod-07`. Sáu người vận hành biết mật khẩu. Một tác vụ `nightly-health-check` và tác vụ `monthly-export` cũng dùng tài khoản này. Người quản lý ban đầu chỉ liệt kê sáu người và dự định bật rotation sau mỗi phiên.

Nếu triển khai ngay, phiên của một quản trị viên kết thúc có thể làm mật khẩu đổi trước lần chạy tiếp theo của job. Vì `monthly-export` chưa chạy trong giai đoạn pilot ngắn, sự cố có thể xuất hiện nhiều ngày sau khi đội triển khai đã tuyên bố thành công.

### 8.2. Thiết kế xử lý

- Tạo danh tính workload riêng cho hai tác vụ theo khả năng của ứng dụng, với quyền cần thiết cho từng tác vụ.
- Cập nhật cách lấy secret và kiểm tra nạp lại credential của từng consumer.
- Thử job theo một kịch bản đại diện đã được owner chấp thuận, thay vì chỉ chờ lịch chạy.
- Giữ `ops_shared` làm tài khoản tương tác phía sau PAM trong giai đoạn hiện tại.
- Mỗi người dùng danh tính cá nhân, yêu cầu có thời hạn và mở phiên qua đường quản trị được phê duyệt.
- Đưa việc giảm quyền hoặc loại bỏ `ops_shared` vào mục tiêu tiếp theo nếu hệ thống hỗ trợ.

Nếu không tạo được danh tính riêng ngay, cần xử lý hai tác vụ như dependency chính thức của tài khoản: dùng lịch rotation phối hợp, giới hạn blast radius và ghi ngoại lệ có thời hạn. Chưa thể áp dụng rotation sau mọi phiên nếu hành vi đó làm gián đoạn consumer.

### 8.3. Timeline minh họa

```text
Chuẩn bị      : xác định owner, consumer, cách nạp secret và đường phục hồi
Pilot         : thử tài khoản tương đương, quyền, connector và bằng chứng
Trước cutover : tách hai workload; xác minh job với danh tính mới
Cutover       : onboard, mở phiên thử, rotation, xác thực mới
Khóa đường cũ : giới hạn truy cập trực tiếp theo kế hoạch đã thử
Theo dõi      : quan sát job, rotation kế tiếp và luồng ngoài giờ
Bàn giao      : owner ký nhận, đóng thay đổi và ghi ngoại lệ còn lại
```

Một mốc trong timeline chỉ được đóng khi có bằng chứng tương ứng. Việc hoàn thành bước tiếp theo không bù cho một phép thử thất bại chưa được giải quyết ở bước trước.

## 9. Ma trận kiểm thử nghiệm thu

Phải xác định trước kết quả mong đợi và nơi lấy bằng chứng. Thử nghiệm trên production cần nằm trong phạm vi thay đổi đã phê duyệt, đặc biệt với lockout, ngắt phiên và thay đổi đường truy cập.

| Nhóm | Kịch bản | Kết quả cần thấy | Bằng chứng |
|---|---|---|---|
| Quyền hợp lệ | Người có quyền mở phiên trong thời hạn | Dùng đúng tài khoản và đúng đích | Request, session ID và sự kiện đích |
| Quyền bị từ chối | Người ngoài nhóm yêu cầu truy cập | Không được cấp quyền hoặc credential | Sự kiện quyết định chính sách |
| Phê duyệt | Yêu cầu thuộc diện cần phê duyệt | Chỉ thực hiện sau phê duyệt đúng thẩm quyền | Người phê duyệt, thời điểm, phạm vi |
| Thời hạn | Yêu cầu hoặc quyền truy xuất hết hạn | Không thể dùng lại quyền đã hết hạn theo thiết kế | Quyết định từ chối và trạng thái yêu cầu |
| Phiên tồn tại | Thời hạn kết thúc khi đang có phiên | Hành vi ngắt hoặc duy trì đúng chính sách đã xác định | Log kết thúc, thời lượng và sự kiện đích |
| Rotation | PAM thay credential rồi xác thực mới | Giá trị quản lý và đích đồng bộ | Kết quả rotation, lần xác thực mới |
| Credential cũ | Thử một lần có kiểm soát sau rotation | Credential cũ bị từ chối nếu đã được thay hoàn toàn | Log thử đã che secret |
| Consumer | Chạy các workload đã kiểm kê | Đáp ứng chức năng với credential hoặc danh tính mới | Kết quả job và kiểm tra nghiệp vụ |
| Đường cũ | Kết nối từ nguồn không được phê duyệt | Bị chặn theo thiết kế | Log mạng hoặc xác thực tương ứng |
| Thu hồi | Bỏ quyền của một người dùng | Không phát sinh quyền hoặc phiên mới trái chính sách | Log IAM/PAM và kết quả thử |
| Khôi phục | Mô phỏng sự cố được chọn | Phục hồi theo runbook trong điều kiện đã thử | Mốc thời gian và biên bản thử |
| Truy vết | Chọn một thao tác thử đã biết | Liên kết được người dùng, yêu cầu, phiên và đích | Chuỗi sự kiện tương quan |

Kiểm tra thu hồi cần phân biệt quyền tạo phiên mới với phiên đang mở. Nếu phiên hiện tại vẫn tồn tại theo thiết kế, runbook phải nêu cách phát hiện và chấm dứt khi cần.

Nếu có nhiều phiên dùng chung một tài khoản đích đồng thời, log ở đích có thể không đủ để quy từng lệnh cho từng người chỉ dựa trên username. Cần dựa vào session metadata, nguồn kết nối, thời gian và dữ liệu tương quan phù hợp; nêu rõ giới hạn khi chứng cứ không phân biệt được.

## 10. Lỗi thường gặp và phương án phục hồi

### 10.1. Các trạng thái lỗi không tương đương

| Dấu hiệu | Khả năng cần kiểm tra | Hành động trước tiên |
|---|---|---|
| PAM không kết nối được tới đích | Mạng, DNS, giao thức, connector hoặc tình trạng đích | Kiểm tra đường kết nối và tình trạng dịch vụ trước khi reset mật khẩu |
| Rotation báo lỗi, credential hiện tại vẫn dùng được | Thao tác đổi bị từ chối hoặc chưa xảy ra | Xác minh trạng thái ở đích và lý do lỗi |
| PAM không xác thực sau rotation | Giá trị lệch, đổi thành công nhưng lưu lỗi, khóa tài khoản hoặc lỗi khác | Dừng retry không kiểm soát, xác định trạng thái và dùng runbook phục hồi |
| Người dùng mở được phiên nhưng job lỗi | Dependency chưa cập nhật hoặc consumer dùng cache cũ | Liên hệ owner consumer, kiểm tra cơ chế nạp secret |
| Vault đúng nhưng không mở được phiên | Lỗi broker/proxy, chính sách hoặc tài nguyên phiên | Tách lỗi cấp phiên khỏi lỗi credential |
| Truy cập được từ đường cũ sau cutover | Quy tắc chưa bao phủ nguồn/giao thức hoặc ngoại lệ rộng | Xác định đường thực tế và khắc phục theo thay đổi được duyệt |

Không reset credential liên tục khi chưa biết vấn đề là mạng hay mật khẩu. Retry nhiều có thể làm khóa tài khoản, gây thêm thay đổi và phá vỡ bằng chứng cần điều tra.

### 10.2. Rollback không nhất thiết là khôi phục mật khẩu cũ

Một rollback hợp lệ là khôi phục khả năng quản trị và trạng thái vận hành được chấp nhận, trong khi giữ kiểm soát phù hợp. Có thể phục hồi cấu hình đường truy cập, chuyển sang đường khẩn cấp đã chuẩn bị hoặc đặt một credential mới rồi đồng bộ lại PAM và consumer.

Không mặc định đặt lại mật khẩu cũ, đặc biệt nếu mật khẩu đó đã bị lộ hoặc đã phân phối cho nhiều người. Một số hệ thống còn chặn tái sử dụng do password history. Nếu sự cố liên quan nghi ngờ xâm phạm, cần phối hợp quy trình ứng phó sự cố khi chọn trạng thái phục hồi.

Phân biệt các tình huống:

- **Trước rotation:** có thể hoãn cutover và giữ trạng thái cũ trong giới hạn thay đổi, nếu chưa có kiểm soát nào bị thay đổi hoặc credential bị lộ.
- **Sau rotation:** cần xác định credential nào đang hiệu lực và trạng thái consumer; không suy đoán vault hoặc đích chắc chắn đúng.
- **Sau khóa đường cũ:** việc mở lại phải có phạm vi, thời hạn, owner và giám sát; không mở rộng toàn mạng để giải quyết lỗi cục bộ.
- **Sau thu hồi quyền người dùng:** cần xử lý cả quyền mới, phiên hiện có và credential đã tiết lộ theo khả năng của hệ thống.

### 10.3. Mẫu runbook ra quyết định

```text
Khi một bước cutover thất bại:
  1. Dừng phát sinh phiên và thay đổi credential mới trong phạm vi sự cố.
  2. Giữ một người điều phối và một nguồn quản lý credential chủ động.
  3. Ghi thời điểm, account ID, change ID và mã lỗi; không ghi secret.
  4. Kiểm tra tình trạng hệ thống đích, mạng, PAM và consumer.
  5. Nếu chưa xác định được credential đang hiệu lực:
       dùng phương án khôi phục đã phê duyệt;
       reset/reconcile có kiểm soát nếu phù hợp;
       xác minh đăng nhập mới và đồng bộ consumer.
  6. Nếu vượt ngưỡng thời gian hoặc ảnh hưởng đã định:
       người có thẩm quyền quyết định rollback/phục hồi.
  7. Chỉ tiếp tục khi trạng thái đã rõ và các phép thử bắt buộc PASS.
```

Runbook phải nêu người thực thi và cách sử dụng quyền khôi phục. Một câu “liên hệ admin” chưa đủ khi chính tài khoản admin là tài khoản đang mất truy cập.

## 11. Bằng chứng và điều kiện hoàn thành

### 11.1. Chuỗi bằng chứng tối thiểu

Đối với một phiên mẫu, nên liên kết được:

```text
Danh tính cá nhân
  -> nhóm quyền và quyết định xác thực
  -> yêu cầu có mục đích, đích và thời hạn
  -> phê duyệt nếu chính sách yêu cầu
  -> tài khoản đích và phiên PAM
  -> sự kiện/thao tác đã chọn tại hệ thống đích
  -> kết thúc phiên và xử lý credential sau sử dụng
```

Cần có thời gian đồng bộ đủ chính xác cho việc tương quan và biết múi giờ của nguồn log. Giữ ID của request, session và account thay vì chỉ lưu ảnh chụp màn hình có tên người dùng.

Recording có thể chứa dữ liệu nhạy cảm. Quyền xem, thời gian lưu, bảo vệ dữ liệu và việc xuất recording phải theo chính sách của tổ chức. Không lấy recording làm nơi lưu mật khẩu hoặc đưa secret vào tài liệu nghiệm thu.

### 11.2. Tách trạng thái quản lý để tránh báo cáo quá mức

| Trạng thái | Ý nghĩa |
|---|---|
| Đã kiểm kê | Biết tài khoản, owner và phạm vi sử dụng đã xác minh |
| Đã onboard | Có bản ghi PAM và cấu hình liên quan |
| Đã kiểm tra truy cập | Luồng truy cập được chọn hoạt động |
| Đã kiểm tra rotation | Đổi credential và đăng nhập mới thành công |
| Đã cutover | Đường truy cập và consumer đã chuyển theo kế hoạch |
| Đã nghiệm thu | Đủ tiêu chí, bằng chứng, bàn giao và xử lý ngoại lệ |

“Đã onboard” không thay thế “đã nghiệm thu”. Nếu đang giữ một đường trực tiếp chưa đáp ứng thiết kế, bản ghi phải thể hiện ngoại lệ hoặc công việc còn lại.

Một tài khoản chỉ nên được tính là migrate hoàn tất khi:

1. Định danh và owner đúng, dependency được kiểm chứng.
2. Người dùng dùng danh tính cá nhân ở lớp yêu cầu.
3. Quyền và cách cấp credential/phiên đáp ứng chính sách đã chọn.
4. Rotation hoặc cơ chế vòng đời tương ứng đã được thử và xác minh.
5. Consumer hoạt động, các phiên hoặc token cũ được xử lý theo kế hoạch.
6. Đường cũ được đóng hoặc chuyển thành ngoại lệ được quản lý.
7. Có bằng chứng truy vết, cảnh báo, runbook và bàn giao.

### 11.3. Đo tiến độ có mẫu số rõ ràng

Ví dụ: một đợt có 24 tài khoản trong phạm vi. Cả 24 đã onboard, 21 đã thử rotation và 18 đã hoàn tất cutover cùng nghiệm thu. Khi đó tỷ lệ onboard là 24/24, tỷ lệ đã thử rotation là 21/24 và tỷ lệ nghiệm thu là 18/24.

Không báo một tỷ lệ 100% chung nếu mới hoàn thành việc tạo bản ghi. Cũng không coi sáu tài khoản chưa nghiệm thu là đồng nhất: có thể một số đang chờ dependency, một số có ngoại lệ và một số đã thất bại kiểm thử.

Ngoài số lượng, theo dõi nhóm tài khoản rủi ro cao, tuổi của ngoại lệ, lỗi rotation, dependency chưa có owner và truy cập trực tiếp sau cutover. Cách đo này làm rõ phần rủi ro còn lại thay vì chỉ đếm công việc đã nhập vào vault.

## 12. Những sai lầm cần tránh

**Nhập credential rồi tuyên bố hoàn tất.** Cách này chưa chứng minh rotation, kiểm soát đường truy cập hoặc thu hồi. Cần gắn trạng thái với từng bằng chứng nghiệm thu.

**Đổi mật khẩu trước khi biết consumer.** Hậu quả có thể là job nền lỗi sau nhiều ngày. Phải kiểm kê đủ chu kỳ sử dụng, thử consumer hoặc ghi rõ phần chưa chứng minh.

**Bật rotation sau mỗi phiên cho tài khoản dùng chung với dịch vụ.** Chính sách hợp lý với con người có thể làm consumer mất kết nối. Tách danh tính hoặc phối hợp vòng đời credential trước.

**Giữ mọi quyền cũ chỉ vì tài khoản đã vào PAM.** Vault bảo vệ credential, không tự thu hẹp quyền trên đích. Cần kế hoạch least privilege riêng hoặc tích hợp trong migration.

**Coi hết hạn checkout là mật khẩu đã vô hiệu.** Credential đã tiết lộ vẫn có thể dùng ở đích cho tới khi được thay đổi hoặc thu hồi bằng cơ chế có hiệu lực.

**Coi rotation là đã chấm dứt mọi phiên.** Phiên và token có vòng đời riêng. Phải xác định rõ hành vi của từng hệ thống và kiểm thử khi cần thu hồi tức thời.

**Để hai bộ quản lý cùng đổi một credential.** Đây là nguồn gây lệch trạng thái. Cần chuyển quyền quản lý theo một mốc rõ ràng và kiểm tra các job cũ đã dừng.

**Giữ đường khẩn cấp nhưng không thử.** Quy trình khôi phục có thể phụ thuộc vào thành phần đang hỏng. Thử các kịch bản lỗi đại diện và ghi giới hạn của từng đường.

**Dùng log tài khoản đích để khẳng định chắc chắn người thực hiện.** Với tài khoản dùng chung và phiên đồng thời, cần tương quan thêm bằng chứng; nếu chưa đủ thì phải ghi rõ giới hạn quy trách nhiệm.

## 13. Bài thực hành thiết kế migration

Một thiết bị quản trị có tài khoản `netops_shared`. Bốn nhân viên nội bộ và một nhóm hỗ trợ bên ngoài biết mật khẩu. Công cụ sao lưu cấu hình kết nối mỗi đêm bằng tài khoản này. Thiết bị có console khôi phục; khả năng tạo tài khoản cá nhân có giới hạn. Đội triển khai dự định đưa tài khoản vào vault và thay mật khẩu ngay.

### Yêu cầu

1. Lập danh sách thông tin còn thiếu trước khi đổi credential.
2. Đề xuất đích migration cho người dùng, nhà cung cấp và công cụ sao lưu.
3. Xác định ít nhất một phép thử quyền hợp lệ, một phép thử từ chối và một phép thử phục hồi.
4. Nêu điều kiện để đóng đường truy cập trực tiếp.
5. Viết tiêu chí hoàn thành có thể kiểm chứng cho tài khoản.

### Gợi ý lập luận

Trước hết cần biết owner, quyền tài khoản, cơ chế đổi mật khẩu, phạm vi xác thực, khả năng tạo danh tính riêng, nguồn truy cập của nhà cung cấp và cách công cụ sao lưu nạp secret. Đồng thời xác minh console có thực sự sử dụng được khi đường PAM hoặc IdP gặp lỗi dự kiến hay không.

Người dùng nội bộ và nhà cung cấp nên có định danh cá nhân hoặc định danh bên ngoài được quản lý ở lớp yêu cầu PAM, quyền theo vai trò và thời hạn phù hợp. Quyền của nhà cung cấp cần owner và cơ chế thu hồi khi hết hợp đồng hoặc hết phiên hỗ trợ.

Công cụ sao lưu nên có danh tính workload và quyền phù hợp nếu thiết bị hỗ trợ. Nếu buộc phải dùng chung tài khoản đích, cần một kế hoạch cập nhật credential cho công cụ, thử xác thực mới và kiểm tra kết quả sao lưu trước khi bật rotation thường xuyên.

Chỉ đóng đường trực tiếp sau khi luồng qua PAM và đường phục hồi đã được xác minh, các consumer hoạt động và người có thẩm quyền chấp nhận kết quả. Nếu một đường phải giữ lại, ghi nó thành ngoại lệ có phạm vi, thời hạn và cơ chế theo dõi.

## 14. Tự kiểm tra

**Tài khoản đã xuất hiện trong vault có được coi là đã migrate không?** Chưa đủ. Cần kiểm tra vòng đời credential, quyền, đường truy cập, consumer và bằng chứng bàn giao theo tiêu chí của đợt.

**Có bắt buộc xóa mọi tài khoản dùng chung ở hệ thống đích không?** Không phải hệ thống nào cũng hỗ trợ. Có thể giữ tài khoản đích nhưng phải kiểm soát danh tính cá nhân ở lớp yêu cầu và ghi rõ giới hạn truy vết. Khi có thể, ưu tiên loại bỏ nhu cầu dùng chung hoặc giảm quyền.

**Vì sao phải kiểm tra lần đăng nhập mới sau rotation?** Phiên đang mở có thể tiếp tục hoạt động dù credential mới chưa được đồng bộ đúng. Một xác thực mới kiểm tra được đường sử dụng credential sau thay đổi.

**Nếu phát hiện một job chưa rõ owner trong cửa sổ cutover thì làm gì?** Dừng bước có thể ảnh hưởng job, ghi dependency và tìm người chịu trách nhiệm trước khi tiếp tục. Không đoán rằng job có thể bỏ qua chỉ vì chưa thấy lỗi.

**Khi nào có thể rollback bằng cách mở lại đường cũ?** Khi phương án đó nằm trong kế hoạch được phê duyệt hoặc được người có thẩm quyền chấp nhận trong sự cố, có phạm vi và thời hạn rõ ràng, và không làm mất kiểm soát credential hoặc bằng chứng. Mở lại đường cũ là một thay đổi cần kiểm soát, không phải phản xạ mặc định.

Một kế hoạch migrate shared account có chất lượng phải trả lời được bốn câu hỏi xuyên suốt: ai sử dụng, sử dụng qua đường nào, credential thay đổi ra sao và lấy bằng chứng ở đâu. Chỉ khi các câu trả lời đã được kiểm chứng trên phạm vi thực tế, tài khoản mới sẵn sàng chuyển sang vận hành thường xuyên trong PAM.
