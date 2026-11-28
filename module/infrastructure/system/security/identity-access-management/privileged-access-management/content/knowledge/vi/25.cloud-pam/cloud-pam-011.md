# Multi-account privilege

## Mục tiêu bài học

Trong chương Cloud PAM của module Privileged Access Management (PAM), **multi-account privilege** là bài toán quản lý quyền đặc biệt khi tổ chức vận hành nhiều ranh giới cloud và cho phép một số danh tính, dịch vụ hoặc hệ thống quản trị truy cập xuyên các ranh giới đó.

Một tổ chức có thể tách môi trường production, thử nghiệm, dịch vụ dùng chung và kiểm toán thành những tài khoản riêng. Việc tách tài khoản giúp tổ chức các ranh giới quản trị, nhưng không tự bảo đảm chúng độc lập về bảo mật. Một role được tin cậy quá rộng, một hệ thống triển khai có quyền trên mọi tài khoản hoặc một credential dùng chung có thể nối lại tất cả các ranh giới.

Bài học sử dụng “tài khoản cloud” như một khái niệm tổ chức quyền. Tùy nền tảng, các ranh giới có thể là account, subscription, project hoặc cấu trúc khác. Chúng không hoàn toàn tương đương về IAM, kế thừa và quản trị. Các sơ đồ, policy và mã giả dưới đây mô tả thiết kế trung lập với nhà cung cấp, không phải cấu hình có thể đưa trực tiếp vào cloud.

Sau bài học, bạn có thể:

- Lập bản đồ đường truy cập đặc quyền giữa các tài khoản.
- Phân biệt quyền ở tài khoản nguồn, quan hệ tin cậy và quyền tại tài khoản đích.
- Thiết kế hệ thống PAM tập trung mà vẫn giữ phạm vi quyền theo từng tài khoản và nhiệm vụ.
- Áp dụng least privilege, JIT/JEA, phân tách nhiệm vụ và kiểm soát danh tính workload.
- Quản lý vòng đời tài khoản, thay đổi trust và thu hồi quyền xuyên tài khoản.
- Đối soát bằng chứng và xử lý sự cố ảnh hưởng nhiều tài khoản.

## 1. Tách tài khoản giải quyết điều gì?

Một mô hình đơn giản có thể gồm:

| Ranh giới minh họa | Mục đích |
|---|---|
| Quản trị tổ chức | Quản lý cấu trúc tài khoản và một số chính sách chung |
| Danh tính và PAM | Liên kết danh tính, điều phối yêu cầu và cấp quyền |
| Production của từng miền nghiệp vụ | Cô lập workload và quyền vận hành |
| Thử nghiệm | Phát triển, kiểm thử và thực hành với dữ liệu phù hợp |
| Dịch vụ dùng chung | Cung cấp các thành phần được nhiều hệ thống sử dụng |
| Bằng chứng bảo mật | Thu thập và bảo vệ log, phục vụ điều tra |

Lợi ích mong muốn là giảm phạm vi ảnh hưởng của một lỗi hoặc tài khoản bị chiếm quyền. Nếu một workload thử nghiệm bị xâm nhập, nó không nên tự động trở thành đường quản trị production.

Tuy nhiên, có nhiều đường nối ngoài việc “đăng nhập sang tài khoản khác”:

- Role có thể được sử dụng từ một tài khoản khác.
- Resource policy có thể cho principal bên ngoài truy cập.
- Workload có thể đọc secret của một danh tính mạnh hơn.
- Pipeline có thể triển khai mã vào nhiều tài khoản.
- Quyền quản trị tổ chức có thể ảnh hưởng chính sách hoặc cấu trúc quản lý bên dưới, tùy nền tảng.
- Dữ liệu, khóa, backup và kho artifact có thể được chia sẻ.
- Một tài khoản có thể có quyền quản trị dịch vụ được ủy quyền trên các tài khoản khác.

Do đó, danh sách tài khoản là điểm bắt đầu. Để hiểu quyền, cần lập bản đồ những đường cho phép một chủ thể tác động tới tài nguyên ở ranh giới khác.

### Kết nối mạng không phải quyền IAM

Hai tài khoản có kết nối mạng chưa có nghĩa principal ở tài khoản này được phép gọi mọi API ở tài khoản kia. Ngược lại, một API cloud có thể được truy cập qua một đường được phép mà không cần mạng riêng giữa hai workload.

Thiết kế phải kiểm tra cả khả năng đi tới đích và khả năng được đích chấp nhận. Chỉ kiểm tra một trong hai sẽ bỏ sót đường truy cập hoặc hiểu sai mức cô lập.

## 2. Ba lớp quyền trong một đường truy cập xuyên tài khoản

Xét một kỹ sư vận hành cần thao tác trên dịch vụ ở tài khoản production. Hệ thống có thể sử dụng broker PAM để hỗ trợ tạo phiên dưới một role tại tài khoản đích.

Có ba lớp cần phân biệt:

1. **Quyền hoặc điều kiện ở nguồn:** ai được yêu cầu hoặc bắt đầu đường truy cập.
2. **Quan hệ tin cậy tại ranh giới đích:** đích chấp nhận principal, phiên hoặc cơ chế ủy quyền nào.
3. **Quyền hành động tại đích:** sau khi được chấp nhận, phiên được làm gì trên tài nguyên nào.

Tùy nền tảng và loại truy cập, các policy kết hợp khác nhau. Không dùng sơ đồ này như một công thức đánh giá quyền chung cho mọi cloud; cần ánh xạ nó sang cơ chế thực tế.

```text
Kỹ sư đã được xác thực
    |
    | được yêu cầu nhiệm vụ trong phạm vi eligibility
    v
Broker PAM
    |
    | đích tin cậy đúng danh tính và điều kiện được phép
    v
Role vận hành ở tài khoản production
    |
    | tập quyền hẹp cho nhiệm vụ
    v
Đúng tài nguyên production được duyệt
```

Một trust cho phép broker tạo phiên không có nghĩa broker cần được tin cậy bởi mọi role. Một role tại đích có quyền rộng cũng không được coi là hẹp chỉ vì giao diện PAM đặt tên yêu cầu là “xem trạng thái”.

### Ví dụ về hai lỗi khác nhau

**Lỗi trust:** role vận hành production chấp nhận quá nhiều principal ở tài khoản quản trị. Một workload không liên quan có thể đi qua đường đó.

**Lỗi permission:** trust chỉ chấp nhận đúng broker, nhưng role tại đích có quyền quản trị IAM và đọc mọi secret. Một yêu cầu vận hành nhỏ vẫn nhận phạm vi quá lớn.

Cần sửa đúng lớp. Thu hẹp trust không tự thu hẹp quyền của phiên hợp lệ. Thu hẹp permission không tự ngăn principal ngoài dự kiến tạo phiên nếu trust vẫn mở.

## 3. Mô hình hóa quyền bằng đồ thị

Trong môi trường nhiều tài khoản, bảng “người dùng có role nào” thường chưa đủ. Cần nhìn các cạnh nối principal, role, workload và tài nguyên.

Một đồ thị khái niệm có thể gồm:

```text
Danh tính kỹ sư
    --> eligibility trong PAM
    --> kế hoạch được phê duyệt
    --> broker
    --> role theo nhiệm vụ ở account-P
    --> dịch vụ production

Pipeline
    --> role triển khai ở account-P
    --> thay image của workload
    --> workload identity
    --> đọc dữ liệu nghiệp vụ

Principal bên ngoài
    --> resource policy ở account-D
    --> đọc một tập đối tượng được chia sẻ
```

Đường thứ hai cho thấy quyền thay image có thể tạo tác động tương tự việc sử dụng quyền của workload. Nếu pipeline được phép thay mã của một dịch vụ có quyền đọc dữ liệu nhạy cảm, không thể đánh giá pipeline chỉ là “quyền triển khai”.

Đường thứ ba cho thấy không phải truy cập xuyên tài khoản nào cũng đi qua role trung gian. Một resource policy có thể tạo đường riêng tùy loại dịch vụ và nền tảng.

### Những cạnh cần kiểm kê

| Cạnh quyền | Câu hỏi cần trả lời |
|---|---|
| Principal sang role | Ai được bắt đầu phiên, với điều kiện nào? |
| Role sang role khác | Có thể chuyển tiếp hoặc mở rộng quyền không? |
| Principal sang resource policy | Tài nguyên có chấp nhận principal bên ngoài không? |
| Principal sang secret | Secret mở ra danh tính hoặc hệ thống nào? |
| Principal sang workload | Có được thay mã, tham số hoặc danh tính thực thi không? |
| Principal sang policy hoặc trust | Có thể tự sửa đường cấp quyền không? |
| Tài khoản sang dịch vụ quản trị chung | Có ủy quyền quản trị liên tài khoản nào? |
| Principal sang log và bằng chứng | Có thể xóa hoặc làm gián đoạn dấu vết không? |
| Principal sang backup hoặc khóa | Có thể tiếp cận bản sao dữ liệu hoặc thay đổi khả năng khôi phục không? |

Bản đồ cần mô tả quyền đang có hiệu lực và cả khả năng cấp lại quyền. Một principal chưa có quyền đọc dữ liệu nhưng có thể tự sửa policy để nhận quyền đó vẫn là chủ thể có khả năng đặc biệt cần kiểm soát.

## 4. Kiểm kê tài khoản và định danh ổn định

Một danh mục tài khoản nên chứa ít nhất:

- Định danh ổn định trong nền tảng.
- Tên hiển thị và môi trường.
- Chủ sở hữu nghiệp vụ và chủ sở hữu kỹ thuật.
- Vị trí trong cấu trúc quản lý.
- Mức nhạy cảm và các workload quan trọng.
- Đường danh tính được phép.
- Role hoặc gói quyền PAM được hỗ trợ.
- Các trust, resource policy và ủy quyền xuyên tài khoản quan trọng.
- Trạng thái vòng đời và khả năng thu thập bằng chứng.

Không xác định môi trường chỉ bằng chuỗi “prod” trong tên tài khoản. Tên hiển thị có thể đổi, trùng hoặc bị gắn sai. Các thuộc tính dùng để quyết định quyền phải có nguồn đáng tin và quyền sửa được kiểm soát.

Một khóa định danh trong hệ thống điều phối có thể là:

```text
target = (
  provider,
  organization_or_tenant_id,
  account_boundary_id,
  role_or_permission_package_id,
  resource_scope,
  configuration_revision
)
```

Không dùng một tên role đơn lẻ làm đích đầy đủ. “Operator” trong tài khoản thử nghiệm và “Operator” trong production là hai đích khác nhau.

### Tài khoản quản trị tổ chức cần được đánh giá riêng

Tài khoản hoặc principal quản trị cấu trúc tổ chức không nên được xem như một workload account bình thường. Tác động của nó có thể nằm ở việc thay đổi chính sách chung, đăng ký tài khoản hoặc ủy quyền quản trị dịch vụ.

Khả năng cụ thể phụ thuộc nền tảng. Không mặc định rằng quyền quản trị tổ chức tự cho phép đọc mọi dữ liệu, nhưng cũng không bỏ qua các đường mà quyền đó có thể mở ra.

Cần đánh giá riêng quyền sửa cấu trúc quản lý, quyền triển khai guardrail, quyền ủy quyền quản trị và quyền truy cập dữ liệu.

## 5. Kiến trúc PAM tập trung, quyền thực thi theo tài khoản

Một mô hình thường dễ kiểm soát là tập trung danh tính và quy trình yêu cầu, đồng thời giữ role thực thi theo từng tài khoản và nhiệm vụ.

```text
                       Nguồn danh tính
                             |
                             v
                   PAM: yêu cầu và phê duyệt
                             |
                   Broker theo phạm vi được phép
                     /               \
                    v                 v
             Role ở account-A   Role ở account-B
             Nhiệm vụ A          Nhiệm vụ B
                    |                 |
                    v                 v
             Tài nguyên A       Tài nguyên B

          Bằng chứng từ các nhánh --> vùng bảo vệ bằng chứng
```

Tập trung không nên đồng nghĩa một credential quản trị chung được phát cho mọi người. Broker phải sử dụng đúng đích, kiểm tra quyền yêu cầu và bảo toàn khả năng quy trách nhiệm.

### Phân tách vai trò của các thành phần chung

| Thành phần | Trách nhiệm chính | Quyền không nên mặc nhiên đi kèm |
|---|---|---|
| Nguồn danh tính | Xác thực và cung cấp thuộc tính tin cậy | Sửa mọi policy workload |
| PAM | Xác định eligibility, phê duyệt, thời hạn | Tùy ý thực thi mọi API cloud |
| Broker | Mở đường thực thi theo kế hoạch | Chọn bất kỳ tài khoản hoặc role ngoài danh mục |
| Pipeline nền tảng | Triển khai baseline và role đã duyệt | Sử dụng thường xuyên quyền nghiệp vụ của người vận hành |
| Nhóm kiểm toán | Đọc và đối soát bằng chứng | Sửa quyền hoặc xóa dấu vết đang kiểm toán |
| Cơ chế khẩn cấp | Khôi phục khả năng điều khiển cần thiết | Trở thành đường quản trị thường trực không được rà soát |

Broker và pipeline triển khai role đều là thành phần đặc quyền. Nếu cùng một principal có thể sửa trust, sửa permission, tự phê duyệt rồi thực thi, việc tách thành nhiều màn hình không tạo ra phân tách nhiệm vụ.

### Giới hạn phạm vi ảnh hưởng của hub

Một broker duy nhất có thể là điểm tập trung rủi ro. Tùy yêu cầu, có thể chia broker theo môi trường, miền nghiệp vụ hoặc mức nhạy cảm.

Điều cần kiểm tra là khi một thành phần bị chiếm quyền, nó có thể tiếp cận những tài khoản nào và làm gì trong từng tài khoản. Một thiết kế tốt có câu trả lời cụ thể thay vì “tất cả đã đi qua PAM”.

Không kết nối mặc định mọi tài khoản mới vào role quản trị của hub chỉ vì chúng cùng tổ chức. Thành viên tổ chức là một thuộc tính quản lý; nó không thay thế quyết định cấp quyền theo mục đích.

## 6. Thiết kế role và trust theo nhiệm vụ

Một gói quyền nên được mô tả bằng khả năng thực tế, chẳng hạn:

```text
Gói quyền: payment-service-restart
Đích: account-P / payment-service
Cho phép: các hành động thực sự cần để khởi động lại dịch vụ
Không bao gồm: sửa IAM, đọc secret, thay image, thay workload identity
Thời gian: theo yêu cầu JIT được duyệt
Người được yêu cầu: nhóm vận hành được xác định
```

Nếu nền tảng không cung cấp một quyền restart hẹp, có thể cần broker hoặc runbook thực thi các hành động cần thiết. Khi đó phải bảo vệ runbook, tham số và danh tính của nó. Không coi tên nút Restart là bằng chứng thao tác đã bị giới hạn.

### Trust cần xác định chủ thể và điều kiện

Một trust khái niệm cần làm rõ:

- Principal nguồn chính xác.
- Loại phiên hoặc cơ chế liên kết danh tính được chấp nhận.
- Đối tượng nhận hoặc mục đích token nếu có.
- Các thuộc tính và điều kiện do bên tin cậy thực sự xác minh.
- Giới hạn nguồn và môi trường khi cơ chế hỗ trợ.
- Ai có thể sửa trust.
- Điều gì xảy ra khi principal nguồn hoặc tài khoản nguồn đổi trạng thái.

Không tin một claim chỉ vì nó có tên quen thuộc. Claim do client tự gửi không tương đương thuộc tính đã được nguồn danh tính tin cậy xác nhận.

### Quyền hiệu lực không chỉ nằm trong role đích

Một phiên có thể còn chịu ảnh hưởng của policy tài nguyên, ràng buộc tổ chức, giới hạn phiên và các lớp khác của nền tảng. Những lớp này có quy tắc kết hợp riêng.

Cần kiểm chứng quyền hiệu lực bằng cơ chế phù hợp thay vì sao chép một công thức “cộng tất cả quyền” hoặc “mọi policy đều giao nhau” cho mọi tình huống.

Đối với tài nguyên dùng chung, phải đánh giá đồng thời quyền được cấp cho principal và cách tài nguyên chấp nhận bên ngoài. Một role hẹp ở account-A không có nghĩa tài nguyên account-B đã từ chối mọi đường khác.

## 7. Danh tính con người và khả năng quy trách nhiệm

Nếu nhiều kỹ sư đều xuất hiện trong log cloud dưới cùng một tên broker mà không có liên kết ngược, việc điều tra ai đã làm gì sẽ khó khăn.

Chuỗi bằng chứng cần nối được:

```text
Danh tính con người
    --> yêu cầu PAM
    --> kế hoạch được duyệt
    --> phiên hoặc hành động do broker thực hiện
    --> principal và sự kiện trong tài khoản đích
```

Các cơ chế có thể khác nhau: metadata phiên, correlation ID, định danh yêu cầu hoặc log của broker. Không phải mọi nền tảng đều chuyển đầy đủ danh tính người dùng cuối tới mọi dịch vụ. Phải biết phần nào do cloud cung cấp và phần nào phải liên kết từ hệ thống khác.

Tên phiên dễ đọc không tự là bằng chứng danh tính nếu người gọi có thể tự chọn nó. Cần ràng buộc metadata với thông tin đã xác minh và bảo vệ quyền sửa.

### Tránh tài khoản quản trị dùng chung

Tài khoản dùng chung làm khó thu hồi theo cá nhân và đối soát trách nhiệm. Nếu cần một danh tính kỹ thuật cho broker, người dùng không nên trực tiếp nhận credential của danh tính ấy.

Nếu tồn tại credential dài hạn cho một tích hợp đặc biệt, phải quản lý như secret đặc quyền: chủ sở hữu, nơi lưu, quyền lấy, rotation và quy trình xử lý lộ lọt. Credential dùng cho nhiều tài khoản có phạm vi ảnh hưởng lớn hơn credential chỉ có một nhiệm vụ ở một đích.

### Thay đổi nhân sự và eligibility

Khi một người đổi nhóm hoặc nghỉ việc, cần chặn đường yêu cầu mới và xử lý phiên hoặc quyền đã được cấp. Xóa người khỏi một nhóm ở nguồn danh tính không mặc nhiên chứng minh mọi phiên cloud đã kết thúc ngay.

Rà soát cũng cần tính tới người có nhiều danh tính, nhóm lồng nhau và quyền được cấp trực tiếp ngoài đường PAM.

## 8. Workload và pipeline xuyên tài khoản

Một workload ở tài khoản này có thể cần truy cập tài nguyên ở tài khoản khác vì nghiệp vụ chính đáng. Thiết kế phải tách danh tính workload khỏi danh tính con người và giới hạn theo chức năng.

Ví dụ, một job xử lý có thể được đọc một tập đối tượng ở tài khoản dữ liệu. Nó không cần vì vậy được quản trị role, đọc mọi secret hoặc thay đổi quyền của kho dữ liệu.

### Đặc biệt chú ý quyền triển khai

Một pipeline có quyền thay mã của workload có thể tác động tới dữ liệu mà workload được phép đọc. Cần đánh giá:

- Ai sửa mã và cấu hình pipeline.
- Ai duyệt artifact được triển khai.
- Pipeline có thể chọn account, role và tài nguyên nào.
- Có thể thay danh tính thực thi hoặc đọc credential triển khai không.
- Nhánh, job hoặc repository ngoài dự kiến có nhận được quyền không.
- Token workload có bị chấp nhận ở sai đối tượng nhận hoặc sai môi trường không.

Không dùng một secret triển khai toàn tổ chức trong mọi repository. Khi có cơ chế danh tính workload phù hợp, giới hạn trust theo nguồn thực thi được xác minh và scope cần thiết.

### Dịch vụ dùng chung không mặc nhiên là vùng ít rủi ro

Kho artifact, hệ thống backup, vault, dịch vụ khóa và nền tảng quan sát có thể ảnh hưởng nhiều tài khoản.

Một thay đổi artifact có thể đi vào nhiều workload. Quyền backup có thể tiếp cận bản sao dữ liệu. Một quyền đọc secret ở dịch vụ chung có thể mở thêm danh tính tại tài khoản khác.

Vì vậy, cần đưa các dịch vụ này vào đồ thị đặc quyền và thiết kế quyền theo người tiêu dùng cụ thể, không chỉ theo nhãn “shared services”.

## 9. JIT cho một hoặc nhiều tài khoản

Một yêu cầu JIT cần liệt kê đích cụ thể. Không nên phê duyệt “quyền vận hành production” rồi để người dùng chọn thêm tài khoản sau đó.

Một kế hoạch có thể là:

```yaml
# Mô hình giảng dạy, không phải policy cloud có thể triển khai.
requestId: change-581
revision: 2
requester: engineer-18
purpose: restart-approved-services
targets:
  - accountId: account-P1
    permissionPackage: service-restart
    resourceId: payment-service
  - accountId: account-P2
    permissionPackage: service-restart
    resourceId: reconciliation-service
time:
  start: approved-start
  deadline: approved-deadline
constraints:
  allowAdditionalTargets: false
  allowIamChanges: false
  allowDelegation: false
approval:
  bindToExactPlanRevision: true
```

Các điều kiện trong mô hình chỉ có giá trị khi được ánh xạ thành kiểm soát thực sự ở PAM, broker và cloud. Một trường allowDelegation=false không ngăn được chuyển quyền nếu role thực tế vẫn cho phép.

### Phê duyệt theo phạm vi trách nhiệm

Chủ sở hữu account-P1 không mặc nhiên có thẩm quyền duyệt account-P2. Một yêu cầu nhiều đích có thể cần các phê duyệt khác nhau theo phạm vi.

Không lấy một phê duyệt rộng hơn nội dung người duyệt đã nhìn thấy. Nếu thay đổi danh sách tài khoản, role, tài nguyên hoặc thời hạn, cần tạo phiên bản kế hoạch mới và áp dụng lại điều kiện phê duyệt tương ứng.

### Không giả định có giao dịch nguyên tử xuyên tài khoản

Cấp quyền ở account-P1 có thể thành công trong khi account-P2 thất bại. Bộ điều phối cần biết trạng thái từng đích.

Có thể chọn một trong các cách theo yêu cầu nghiệp vụ:

- Chỉ cho người dùng bắt đầu khi mọi đích cần thiết đã sẵn sàng.
- Cho thực hiện từng phần nếu điều đó được kế hoạch cho phép.
- Thu hồi những grant đã tạo khi một đích bắt buộc thất bại.

Việc thu hồi bù chỉ xử lý quyền đã cấp. Nó không tự hoàn tác một thao tác nghiệp vụ đã chạy trước đó.

Ngay cả khi giao diện chưa báo ACTIVE, một binding đã được tạo có thể có tác động. Cần hạn chế cửa sổ cấp dở, quản lý ownership và đối soát sau lỗi. Không mô tả một chuỗi API liên tài khoản như một giao dịch tất cả hoặc không có gì nếu cơ chế thực tế không bảo đảm điều đó.

### Quản lý grant theo đích và phiên bản

```text
managed_grant = (
  request_id,
  request_revision,
  target_account_id,
  target_role_or_binding_id,
  principal_id,
  owner_controller,
  deadline
)
```

Retry phải đối soát đúng grant. Job dọn của phiên bản cũ không được xóa quyền của yêu cầu mới hoặc quyền dùng chung mà nó không sở hữu.

Nếu nhiều yêu cầu chia sẻ một binding, cần mô hình quản lý tham chiếu và thu hồi phù hợp. Không xóa binding chỉ vì một trong nhiều yêu cầu hết hạn.

### Thời hạn quyền và thời hạn phiên

Phiên tạo sát deadline không được mặc nhiên có thêm một thời lượng đầy đủ vượt quá thời hạn được duyệt. Thiết kế cần giới hạn khả năng tạo phiên và tuổi thọ phiên theo ngữ nghĩa nền tảng.

Khi thu hồi một đường truy cập xuyên tài khoản, phải xem cả:

- Khả năng tạo phiên mới tại đích.
- Binding hoặc grant đang tồn tại.
- Credential phiên đã phát hành.
- Những phiên hoặc danh tính khác được tạo tiếp qua delegation.
- Những thay đổi lâu dài đã được thực hiện trong cửa sổ quyền.

Xóa trust có thể chặn một đường tạo phiên mới, nhưng không được mặc định rằng nó đã kết thúc mọi credential có sẵn. Cần kiểm chứng theo cơ chế cloud được dùng.

## 10. Vòng đời tài khoản là vòng đời của quan hệ tin cậy

### 10.1. Onboarding

Một tài khoản mới không nên nhận ngay mọi trust và quyền quản trị của các tài khoản đang hoạt động.

Một trình tự có thể gồm:

1. Đăng ký định danh và chủ sở hữu.
2. Xác định môi trường, mức nhạy cảm và vị trí quản lý.
3. Triển khai baseline danh tính và thu thập bằng chứng.
4. Tạo các role theo nhiệm vụ và trust được phê duyệt.
5. Kiểm chứng đường cho phép và đường từ chối.
6. Đăng ký tài khoản vào danh mục PAM.
7. Cho phép kích hoạt quyền theo phạm vi đã sẵn sàng.

Có thể dùng trạng thái trung gian để tài khoản chưa hoàn tất baseline không trở thành đích JIT thông thường.

Pipeline onboarding là thành phần đặc quyền. Cần giới hạn người sửa template, người phê duyệt và khả năng chọn principal được tin cậy. Một lỗi template có thể nhân rộng trust sai tới nhiều tài khoản.

### 10.2. Thay đổi vị trí hoặc chủ sở hữu

Khi tài khoản đổi miền nghiệp vụ, đổi môi trường hoặc chuyển vị trí quản lý, có thể thay đổi policy kế thừa và thẩm quyền phê duyệt.

Cần rà soát:

- Role và eligibility còn phù hợp không.
- Trust cũ có còn được phép không.
- Nhóm cũ có còn quyền truy cập trực tiếp không.
- Các tài nguyên chia sẻ và pipeline cũ còn cần thiết không.
- Bằng chứng lịch sử có giữ được thông tin chủ sở hữu tại thời điểm sự kiện không.

Không chỉ đổi một nhãn môi trường rồi giữ nguyên mọi đường quản trị.

### 10.3. Tạm ngừng hoặc cô lập

Nếu cần cô lập một tài khoản vì sự cố, việc gỡ nó khỏi danh mục PAM chỉ ngăn một đường yêu cầu. Các trust, resource policy, credential và phiên còn lại có thể vẫn có tác động.

Kế hoạch cô lập phải dựa trên đồ thị quyền thực tế, đồng thời giữ đường phục hồi và thu thập bằng chứng phù hợp. Không cắt toàn bộ quyền của nhóm ứng cứu trước khi bảo đảm còn một cơ chế kiểm soát đã được thiết kế.

### 10.4. Decommission

Trước khi đóng hoặc ngừng sử dụng tài khoản, cần xử lý cả quan hệ đi vào và đi ra:

- Trust và grant cho principal bên ngoài.
- Quyền của principal trong tài khoản đối với các tài khoản khác.
- Credential và secret được cấp cho tích hợp.
- Pipeline, lịch chạy và job còn tham chiếu.
- Resource policy ở tài khoản khác đang tin cậy principal cũ.
- Dữ liệu, khóa, backup và nghĩa vụ giữ bằng chứng.
- Tài nguyên dùng chung còn có chủ sở hữu mới hay không.

Không giả định xóa một role hoặc đóng một tài khoản sẽ tự dọn mọi tham chiếu ở nơi khác. Việc xử lý cần đúng khả năng nền tảng và được đối soát.

## 11. Guardrail, chuẩn hóa và phát hiện drift

Guardrail là các ràng buộc chung giúp hạn chế việc cấp hoặc sử dụng quyền ngoài ý định. Chúng có thể được triển khai ở nhiều lớp tùy nền tảng.

Ví dụ mục tiêu kiểm soát:

- Không cho workload thử nghiệm nhận quyền quản trị production.
- Không cho role vận hành thông thường sửa IAM hoặc làm gián đoạn bằng chứng.
- Chỉ cho trust đến từ các principal đã đăng ký.
- Không cho broker cấp một gói quyền ngoài danh mục đã duyệt.
- Hạn chế đường tạo credential lâu dài trong phiên vận hành.

Không mặc định guardrail ở cấp tổ chức bao phủ mọi loại principal, tài nguyên hoặc quyền đặc biệt. Cần xác minh phạm vi áp dụng và các ngoại lệ của cơ chế cụ thể.

### Template là baseline, không phải quyền hiệu lực

Hai tài khoản có thể cùng được triển khai một template ban đầu nhưng khác nhau sau nhiều tháng vì thay đổi thủ công, phiên bản cũ hoặc tài nguyên mới.

Cần so sánh trạng thái quan sát với baseline được phê duyệt:

| Loại drift | Ví dụ |
|---|---|
| Trust rộng hơn | Xuất hiện principal ngoài danh mục |
| Permission rộng hơn | Role restart có thêm quyền sửa IAM |
| Phạm vi sai | Binding ở cấp tài khoản thay vì một tài nguyên |
| Thời hạn bị mất | Grant tạm không còn điều kiện hoặc lịch thu hồi |
| Đường ngoài PAM | Có quyền trực tiếp cho người dùng không được ghi nhận |
| Bằng chứng suy giảm | Một tài khoản không còn gửi đủ sự kiện |
| Ownership không rõ | Grant được tạo nhưng không liên kết được yêu cầu |

### Sửa drift phải theo đúng ownership

Không tự xóa mọi role hoặc binding khác template mà không xác định nguồn gốc. Một quyền có thể thuộc hệ thống hợp lệ khác, một ngoại lệ đã được duyệt hoặc một hoạt động ứng cứu đang diễn ra.

Với đối tượng do controller quản lý, dùng định danh, phiên bản và khả năng cập nhật có điều kiện nếu có. Sau thao tác, đọc lại và đối soát.

Một kiểm tra revision trong cơ sở dữ liệu local không tự ngăn được một API cloud đang chạy chậm. Cần xét khả năng cạnh tranh, tuần tự hóa và bước xác minh sau thay đổi.

## 12. Bằng chứng xuyên tài khoản

Một lần truy cập có thể tạo sự kiện ở nguồn danh tính, PAM, broker, tài khoản nguồn và tài khoản đích. Không phải mọi sự kiện đều có cùng trường định danh hoặc cùng thời điểm xuất hiện.

Chuỗi đối soát nên liên kết được:

```text
request_id + revision
    --> danh tính người hoặc workload
    --> phê duyệt và phạm vi
    --> principal nguồn
    --> role hoặc principal đích
    --> phiên hoặc thao tác thực tế
    --> hành động trên tài nguyên
    --> kết thúc và xác minh quyền
```

### Thông tin cần lưu

| Nhóm | Dữ liệu cần thiết |
|---|---|
| Ranh giới | Nhà cung cấp, định danh tổ chức và tài khoản nguồn/đích |
| Chủ thể | Danh tính gốc, principal nguồn, principal đích |
| Thẩm quyền | Request ID, revision, approval reference, gói quyền |
| Phiên | Session reference, thời điểm tạo và giới hạn liên quan |
| Hoạt động | Hành động, định danh tài nguyên, kết quả |
| Cấu hình | Phiên bản trust, role hoặc policy cần cho điều tra |
| Thu hồi | Đối tượng được thu hồi, thời điểm, quan sát và phần chưa xác minh |

Không ghi credential, token, private key hoặc secret vào log để thuận tiện nối sự kiện. Correlation ID phải là tham chiếu, không phải một giá trị cho phép tái sử dụng phiên.

### Bảo vệ bằng chứng khỏi principal đang được giám sát

Người vận hành tài khoản workload không nên mặc nhiên có quyền sửa hoặc xóa bản sao bằng chứng phục vụ điều tra độc lập.

Tuy nhiên, chuyển log sang một tài khoản khác chưa đủ. Cần kiểm soát đường gửi, quyền sửa cấu hình, quyền xóa, thời hạn lưu và khả năng phát hiện ngừng thu thập.

Một khoảng trống log không chứng minh không có hoạt động. Phải phân biệt không có sự kiện, sự kiện đến trễ và đường thu thập đã bị gián đoạn.

### Giữ bối cảnh tại thời điểm sự kiện

Tài khoản có thể đổi tên, chuyển nhóm quản lý hoặc thay chủ sở hữu. Bằng chứng chỉ dựa vào danh mục hiện tại có thể diễn giải sai sự kiện cũ.

Cần giữ thông tin lịch sử hoặc tham chiếu phiên bản cấu hình phù hợp để trả lời lúc đó role, trust và phạm vi có ý nghĩa gì.

## 13. Ứng phó sự cố liên quan quyền xuyên tài khoản

### Tài khoản workload bị chiếm quyền

Không chỉ kiểm tra quyền ở chính tài khoản đó. Cần tìm đường đi ra:

- Principal nào có thể dùng role ở tài khoản khác.
- Resource policy nào chấp nhận principal bị ảnh hưởng.
- Secret hoặc credential nào đã có thể được đọc.
- Pipeline hoặc workload nào ở nơi khác có thể bị sửa.
- Phiên nào đã được tạo trước khi phát hiện.
- Đối tượng nào đã được tạo để duy trì quyền.

Thu hồi quyền nguồn cần đi kèm xử lý các đường và phiên liên quan theo khả năng nền tảng. Việc một API từ nguồn bị từ chối không chứng minh principal đã chuyển sang một danh tính khác cũng bị chặn.

### Broker hoặc nguồn danh tính chung bị chiếm quyền

Phạm vi ảnh hưởng có thể rộng hơn một tài khoản. Ưu tiên xác định những đích mà thành phần đó được tin cậy và các gói quyền nó có thể nhận.

Một kế hoạch phản ứng cần có:

1. Cơ chế chặn cấp quyền hoặc tạo phiên mới từ đường bị ảnh hưởng.
2. Danh sách trust, grant và phiên cần xử lý ở từng đích.
3. Đường ứng cứu độc lập phù hợp để tránh tự khóa khả năng phục hồi.
4. Bảo toàn bằng chứng trước khi sửa cấu hình nhạy cảm khi điều kiện cho phép.
5. Kiểm tra thay đổi IAM, credential, pipeline và logging trong cửa sổ sự cố.
6. Xác minh riêng từng tài khoản và ghi phần chưa được chứng minh.
7. Khôi phục trust theo từng phạm vi đã kiểm tra.

Không vội bật lại toàn bộ trust chỉ vì broker đã được khởi động lại. Phải xử lý cả danh tính, credential và cấu hình tin cậy liên quan.

### Không đồng nhất thu hồi với xóa dấu vết persistence

Thu hồi một grant có thể ngăn một đường truy cập. Nó không xóa credential mới, artifact bị thay, dữ liệu bị sao chép hoặc role khác đã được tạo.

Cần điều tra các thay đổi bền vững và xử lý theo từng loại. Một cơ chế rotation credential chung không tự hoàn tác mọi thay đổi IAM hoặc phục hồi tính toàn vẹn của workload.

## 14. Tình huống minh họa

### Bối cảnh

Một tổ chức có năm tài khoản:

```text
account-I: danh tính và điều phối PAM
account-P: dịch vụ thanh toán production
account-O: dịch vụ đơn hàng production
account-B: pipeline và artifact
account-L: bằng chứng bảo mật
```

Kỹ sư Lan cần khởi động lại payment-service trong account-P. Một pipeline ở account-B triển khai phần mềm cho account-P và account-O.

### Thiết kế đường vận hành

Lan chỉ đủ điều kiện xin gói payment-service-restart ở account-P. Kế hoạch được duyệt gắn với định danh dịch vụ và deadline.

Broker ở account-I chỉ mở đường tới role phù hợp. Role này không được sửa IAM, đọc secret hoặc thay image. Nếu phải dùng runbook để giữ giới hạn, Lan chỉ được chọn các đầu vào đã cho phép.

Hoạt động được liên kết về yêu cầu của Lan, đồng thời bằng chứng được chuyển tới account-L theo đường thu thập đã bảo vệ.

### Vì sao vẫn phải đánh giá account-B?

Nếu Lan cũng có thể sửa pipeline hoặc artifact mà không có kiểm soát độc lập, cô ấy có thể tác động tới mã chạy dưới workload identity ở production. Đường đó có thể mở quyền rộng hơn gói restart.

Vì vậy, ma trận quyền phải tính cả:

- Quyền sử dụng PAM.
- Quyền sửa pipeline.
- Quyền phát hành artifact.
- Quyền thay workload identity.
- Khả năng truy cập secret dùng để triển khai.

Không thể kết luận quyền của Lan chỉ là restart bằng cách nhìn một role trong account-P.

### Khi account-P cần bị cô lập

Tổ chức chặn đường kích hoạt mới, xử lý grant và phiên liên quan, kiểm tra đường từ pipeline, rà soát resource policy và giữ khả năng ứng cứu.

Không xóa toàn bộ quyền của account-L hoặc cắt luồng bằng chứng chỉ vì chúng có liên hệ với account-P. Mỗi đường được xử lý theo mục đích và quyền thực tế.

## 15. Bài thực hành lập bản đồ và kiểm chứng quyền

Dùng môi trường thử nghiệm với dữ liệu giả, hoặc thực hiện phần lập mô hình trên giấy nếu chưa có cloud phù hợp. Không cần mở quyền rộng trên production để làm bài.

### Bước 1: Lập danh mục ba ranh giới

Chọn ba tài khoản giả:

```text
account-C: điều phối
account-T: workload thử nghiệm
account-E: bằng chứng
```

Xác định chủ sở hữu, principal, role, tài nguyên và các đường chia sẻ. Ghi rõ định danh đích thay vì chỉ tên hiển thị.

### Bước 2: Vẽ đồ thị quyền

Thêm các cạnh:

- Người dùng tới eligibility.
- Broker tới role ở account-T.
- Role tới một tài nguyên thử nghiệm.
- Pipeline tới quyền sửa workload.
- Tài khoản workload tới đường gửi bằng chứng.
- Mọi đường đọc secret hoặc chuyển danh tính nếu có.

Đánh dấu cạnh nào là quyền hiện hữu, cạnh nào chỉ là đủ điều kiện xin quyền và cạnh nào là khả năng sửa policy.

### Bước 3: Định nghĩa một nhiệm vụ

Chọn một thao tác hẹp và an toàn. Xác định role, hành động, tài nguyên, thời hạn và người phê duyệt.

Tìm các quyền gián tiếp có thể phá giới hạn: sửa trust, thay image, gắn danh tính mạnh hơn, đọc credential và sửa log. Nếu chúng không cần cho nhiệm vụ, không đưa vào gói quyền.

### Bước 4: Kiểm chứng các đường cho phép và từ chối

| Tình huống | Kết quả mong đợi |
|---|---|
| Đúng người, đúng kế hoạch, đúng tài khoản đích | Cho phép đúng nhiệm vụ |
| Cùng tên role nhưng ở tài khoản không được duyệt | Từ chối |
| Người yêu cầu tự đổi target sau phê duyệt | Phê duyệt cũ không còn hợp lệ |
| Workload không liên quan trong tài khoản nguồn gọi đích | Bị trust hoặc kiểm soát tương ứng chặn |
| Principal hợp lệ gọi hành động ngoài gói nhiệm vụ | Từ chối |
| Người vận hành sửa trust để tự mở rộng quyền | Bị phân tách quyền chặn |
| Phiên thử nghiệm tìm đường vào production | Không có đường được phép ngoài kế hoạch |
| Resource policy mở quyền ngoài PAM | Được phát hiện trong bản đồ quyền |
| Pipeline có thể thay workload có quyền mạnh | Được ghi nhận là đường đặc quyền cần kiểm soát |
| Một đích cấp quyền thành công, đích khác lỗi | Trạng thái từng đích rõ và xử lý bù theo kế hoạch |
| Retry cấp quyền sau timeout | Không tạo grant thừa ngoài kiểm soát |
| Job thu hồi cũ chạy sau yêu cầu mới | Không xóa nhầm grant mới |
| Gỡ trust khi còn phiên đã phát hành | Xử lý hoặc theo dõi phiên theo ngữ nghĩa đã xác minh |
| Thêm tài khoản mới vào tổ chức | Không tự nhận trust quản trị ngoài thiết kế |
| Đổi chủ sở hữu hoặc vị trí quản lý | Quyền kế thừa và thẩm quyền được rà soát |
| Ngừng sử dụng tài khoản | Quan hệ đi vào, đi ra và tham chiếu được đối soát |
| Tìm một sự kiện tại tài khoản đích | Nối được về chủ thể và yêu cầu, không lộ credential |

Nếu một phép thử chỉ chứng minh một đường bị chặn, ghi rõ giới hạn đó. Không suy luận toàn bộ đồ thị đã an toàn từ một API trả về lỗi.

### Bước 5: Hoàn thiện bằng chứng

Kết quả thực hành nên có:

- Danh mục tài khoản và chủ sở hữu.
- Đồ thị đường quyền trực tiếp và gián tiếp.
- Ma trận role, trust, hành động và tài nguyên.
- Một kế hoạch JIT với đích bất biến.
- Bằng chứng cấp, sử dụng và kết thúc quyền.
- Danh sách giới hạn nền tảng chưa được kiểm chứng.
- Quy trình xử lý khi tài khoản nguồn hoặc broker bị chiếm quyền.

## 16. Các lỗi thường gặp

**Cho rằng mọi tài khoản trong cùng tổ chức đều nên tin cậy nhau.** Tư cách thành viên tổ chức không thay thế mục đích nghiệp vụ. Trust cần theo chủ thể, nhiệm vụ và phạm vi được kiểm soát.

**Dùng một role quản trị chung ở mọi tài khoản.** Một lỗi ở nguồn có thể mở rộng tới nhiều đích. Tách quyền theo nhiệm vụ, môi trường và miền nghiệp vụ khi cần giới hạn phạm vi ảnh hưởng.

**Chỉ kiểm kê role mà bỏ resource policy, secret và pipeline.** Những đường này có thể cấp khả năng truy cập mà không đi qua role được PAM hiển thị.

**Tin tên phiên hoặc trường người dùng do client gửi.** Cần liên kết bằng dữ liệu được xác minh, không coi chuỗi dễ đọc là danh tính đáng tin.

**Thu hồi ở nguồn rồi kết luận mọi đích đã an toàn.** Cần xử lý grant, phiên, delegation và thay đổi lâu dài ở các đích liên quan.

**Dùng template giống nhau rồi bỏ đối soát.** Trạng thái thực tế có thể thay đổi theo thời gian. Cần quan sát quyền và trust đang tồn tại.

**Tập trung cả phê duyệt, cấp quyền và xóa log vào một principal.** Điều đó tạo một đường phá vỡ toàn bộ kiểm soát. Phân tách trách nhiệm và bảo vệ bằng chứng ở ranh giới thích hợp.

**Xóa quyền hoặc tài khoản trước khi xác định phụ thuộc.** Có thể làm mất đường phục hồi, gián đoạn dịch vụ hoặc mất khả năng xử lý dữ liệu lưu trữ. Vòng đời phải tính tới quyền và dữ liệu ở những tài khoản khác.

## 17. Các câu hỏi trước khi mở quyền xuyên tài khoản

Một thiết kế cần trả lời được:

1. Chủ thể nào cần đi từ ranh giới nào tới ranh giới nào, vì nhiệm vụ gì?
2. Đích đang tin cậy chính xác principal và điều kiện nào?
3. Sau khi qua trust, phiên được thực hiện những hành động nào trên tài nguyên nào?
4. Ai có thể sửa trust, permission, pipeline hoặc danh tính workload?
5. Có resource policy, secret hoặc đường chia sẻ nào bỏ qua luồng PAM không?
6. Quyền có được cấp và kết thúc riêng theo từng đích, phiên bản và ownership không?
7. Phiên đã phát hành còn sống bao lâu sau khi chặn đường tạo phiên mới?
8. Nếu hub bị chiếm quyền, phạm vi ảnh hưởng tối đa là những tài khoản và hành động nào?
9. Bằng chứng tại đích có nối được về danh tính gốc và yêu cầu không?
10. Khi tài khoản đổi chủ, bị cô lập hoặc decommission, ai xử lý các quan hệ đi vào và đi ra?

Multi-account privilege cần được quản lý như một mạng quan hệ quyền. PAM cung cấp khả năng kiểm soát khi từng đường có mục đích, phạm vi, chủ sở hữu, thời hạn phù hợp và bằng chứng có thể đối soát. Số lượng tài khoản chỉ mô tả cách chia hạ tầng; các quan hệ tin cậy và khả năng cấp lại quyền mới cho biết mức cô lập thực tế.
