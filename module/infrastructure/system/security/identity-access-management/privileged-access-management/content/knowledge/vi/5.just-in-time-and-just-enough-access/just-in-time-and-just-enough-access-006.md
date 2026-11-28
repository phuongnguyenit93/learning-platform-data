# Giới hạn phạm vi tài nguyên

Trong chương **JIT và JEA**, giới hạn phạm vi tài nguyên trả lời câu hỏi: **một quyền đặc biệt được phép tác động lên những đối tượng cụ thể nào?** Đây là phần thiết yếu của quản lý truy cập đặc quyền (PAM): một quyền đúng thao tác, cấp đúng lúc nhưng áp dụng cho toàn bộ hạ tầng vẫn có thể gây thiệt hại lớn.

Bài học tập trung vào tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm. Mục tiêu là biến một yêu cầu vận hành thành tập tài nguyên có thể kiểm kê, phê duyệt, cưỡng chế thực thi và đối chiếu khi kiểm toán hoặc ứng phó sự cố.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Tách giới hạn thời gian, giới hạn thao tác và giới hạn tài nguyên trong một yêu cầu cấp quyền.
- Chọn tập tài nguyên nhỏ nhất đủ hoàn thành công việc, dựa trên định danh đáng tin cậy.
- Nhận diện phạm vi bị mở rộng qua kế thừa quyền, nhãn, wildcard, tài khoản dùng chung hoặc đường truy cập phụ.
- Thiết kế kiểm tra tại thời điểm yêu cầu, cấp quyền và thực thi thao tác.
- Chuẩn bị bằng chứng chứng minh thao tác đã diễn ra đúng phạm vi được duyệt.

## 2. JIT, JEA và phạm vi tài nguyên bổ sung cho nhau

**Just-in-time (JIT)** giới hạn thời điểm quyền có hiệu lực và khoảng thời gian quyền được sử dụng. **Just-enough access (JEA)** giới hạn quyền ở mức đủ cho công việc, gồm thao tác và đối tượng được phép tác động. Trong bài này, JEA được dùng theo nghĩa nguyên tắc thiết kế quyền; các ví dụ không phải cấu hình của một sản phẩm cụ thể.

So sánh ba yêu cầu sau:

| Yêu cầu | Thời gian | Thao tác | Tài nguyên | Nhận xét |
|---|---|---|---|---|
| Cấp quản trị production trong 20 phút | Có giới hạn | Quá rộng | Toàn production | Có thời hạn nhưng phạm vi ảnh hưởng lớn |
| Cho khởi động lại dịch vụ trên mọi máy trong 20 phút | Có giới hạn | Đã thu hẹp | Vẫn quá rộng | Một thao tác vẫn có thể làm gián đoạn cả hệ thống |
| Cho khởi động lại hai service instance đã chỉ định trong 20 phút | Có giới hạn | Cụ thể | Cụ thể | Phù hợp hơn nếu công việc chỉ cần hai instance đó |

Một yêu cầu nên thể hiện ít nhất năm thành phần:

```text
Chủ thể + thao tác + tài nguyên + điều kiện sử dụng + thời hạn
```

Ví dụ:

> Trong cửa sổ xử lý sự cố đã duyệt, kỹ sư trực ca được xem trạng thái và khởi động lại hai instance `order-worker` thuộc tenant Acme, môi trường production. Quyền có hiệu lực tối đa 20 phút kể từ khi kích hoạt; việc thực thi phải đi qua bộ trung gian PAM và gắn với mã sự cố.

Thời hạn ngắn không thay thế giới hạn tài nguyên. Một thao tác phá hủy hoặc gây gián đoạn có thể hoàn tất trước khi quyền hết hạn.

## 3. Xác định tài nguyên ở đúng độ chi tiết

“Tài nguyên” có thể là tài khoản cloud, máy chủ, cơ sở dữ liệu, secret, namespace, thiết bị mạng hoặc một đối tượng con trong các hệ thống đó. Cấp quyền ở mức đối tượng cha thường rộng hơn nhu cầu thao tác thực tế.

| Bối cảnh | Phạm vi quá rộng | Phạm vi cần xem xét |
|---|---|---|
| Quản trị máy chủ | Mọi máy trong một cụm | Một máy cụ thể, hoặc một service instance trên máy đó |
| Vận hành cơ sở dữ liệu | Toàn bộ máy chủ cơ sở dữ liệu | Cơ sở dữ liệu, schema hoặc đối tượng đúng với thao tác cần làm |
| Lấy credential từ vault | Toàn bộ kho hoặc mọi secret của đội | Secret hoặc đường dẫn credential đã được duyệt |
| Quản trị workload | Mọi workload trong một môi trường | Workload và phạm vi triển khai cụ thể |
| Thay đổi mạng | Toàn bộ hệ thống thiết bị | Thiết bị và đối tượng cấu hình liên quan đến yêu cầu |

Độ chi tiết thực tế phụ thuộc vào khả năng của hệ thống đích và điểm thực thi chính sách. Không nên ghi “chỉ một schema” trong yêu cầu nếu credential thực tế có toàn quyền trên toàn bộ máy chủ cơ sở dữ liệu và không có cơ chế nào cưỡng chế giới hạn đó.

### 3.1. Phân biệt tên hiển thị và định danh tài nguyên

Tên như `orders-prod-02` thuận tiện cho con người nhưng có thể bị đổi, tái sử dụng hoặc trùng giữa các tenant. Phê duyệt nên liên kết với định danh ổn định trong một miền quản lý xác định, kèm các thuộc tính để người duyệt hiểu đối tượng đó.

Ví dụ kiểm kê dùng xuyên suốt bài:

| Định danh trong miền Acme | Loại tài nguyên | Máy chủ chứa đối tượng | Môi trường | Quyết định |
|---|---|---|---|---|
| `svc-72e8` | Service instance `order-worker` | `vm-04c2`, tên `orders-prod-02` | Production | Được chọn |
| `svc-91a4` | Service instance `order-worker` | `vm-77b1`, tên `orders-prod-03` | Production | Được chọn |
| `svc-33d0` | Service instance `payment-worker` | `vm-04c2`, tên `orders-prod-02` | Production | Không được chọn |
| `svc-0fa2` | Service instance `order-worker` | `vm-b129`, tên `orders-dev-01` | Development | Không được chọn |

Cùng một máy chủ có thể chứa nhiều dịch vụ. Quyền khởi động lại `svc-72e8` không bao hàm quyền khởi động lại máy `vm-04c2`, vì thao tác đó còn ảnh hưởng đến `svc-33d0`.

Định danh ổn định cũng cần được quản lý vòng đời. Khi tài nguyên bị xóa rồi tạo lại, hoặc chuyển sang miền quản lý khác, phải xác minh đối tượng mới có còn thuộc quyết định phê duyệt cũ hay không. Không tự động coi tên giống nhau là cùng một tài nguyên.

### 3.2. Thuộc tính cần đủ để tránh nhầm đích

Tùy hệ thống, bản ghi kiểm kê có thể cần:

- Miền quản lý hoặc tenant, định danh tài nguyên và loại đối tượng.
- Môi trường, chủ sở hữu nghiệp vụ và mức độ nhạy cảm.
- Quan hệ cha–con, máy chủ chứa đối tượng và các phụ thuộc liên quan.
- Nguồn kiểm kê, phiên bản bản ghi và thời điểm xác minh gần nhất.

Không tin địa chỉ mạng hoặc tên do người yêu cầu nhập như bằng chứng duy nhất về danh tính tài nguyên. Điểm thực thi phải ánh xạ định danh được duyệt sang đúng đối tượng đích từ nguồn được kiểm soát.

## 4. Biểu diễn phạm vi thành một tập hữu hạn

Gọi:

- `R_need`: tập tài nguyên thực sự cần cho công việc.
- `R_request`: tập tài nguyên người dùng yêu cầu.
- `R_approve`: tập tài nguyên được duyệt.
- `R_grant`: tập tài nguyên mà quyền vừa cấp thực sự có thể tác động.

Một thiết kế cấp quyền tối thiểu hướng tới:

```text
R_need ⊆ R_request
R_grant ⊆ R_approve ⊆ R_request
```

`R_request` vẫn phải được xem xét để loại bỏ các đối tượng không cần thiết. Một yêu cầu quá rộng không trở nên phù hợp chỉ vì quyền cấp ra bằng đúng yêu cầu.

Đối với một thao tác thành công theo luồng này, tài nguyên đích phải thuộc `R_grant` và thao tác phải nằm trong tập hành động được phép. Phép so sánh tập hợp chỉ có ý nghĩa khi hệ thống biết rõ thành viên từng tập và cùng sử dụng một cách định danh.

Các tập trên mô tả một lần cấp quyền. Khi đánh giá khả năng truy cập thực tế của chủ thể, phải xét thêm quyền thường trực, vai trò được kế thừa, phiên đã mở và credential đang giữ. Nếu kỹ sư vẫn có tài khoản quản trị thường trực trên mọi máy, grant JIT hẹp chưa đủ chứng minh rằng quyền thực tế đã được thu hẹp.

### 4.1. Ưu tiên danh sách cho phép cụ thể

Với yêu cầu vận hành nhỏ, danh sách định danh rõ ràng thường dễ phê duyệt và kiểm toán:

```text
Miền quản lý: acme
Tài nguyên: svc-72e8, svc-91a4
Thao tác: service.status, service.restart
```

Không diễn giải danh sách này thành “mọi tài nguyên cùng đội”, “mọi dịch vụ trên hai máy” hoặc “mọi instance có tên bắt đầu bằng order”. Các cách diễn giải đó tạo ra tập quyền khác với tập được duyệt.

### 4.2. Xử lý selector và nhãn một cách có kiểm soát

Selector theo nhãn có ích khi số lượng tài nguyên lớn hoặc hạ tầng thay đổi thường xuyên. Tuy nhiên, biểu thức như `environment=production AND team=orders` có thể khớp thêm tài nguyên sau lúc duyệt.

Có hai cách thiết kế cần phân biệt:

| Cách thiết kế | Cách hiểu quyết định duyệt | Điều cần kiểm soát |
|---|---|---|
| Chốt tập tài nguyên | Duyệt danh sách đã phân giải tại một thời điểm | Lưu danh sách và phiên bản; tài nguyên mới không tự được thêm |
| Phạm vi động | Duyệt quy tắc xác định thành viên thay đổi theo thời gian | Nêu rõ đây là quyền động; quản lý nhãn, giới hạn loại tài nguyên và kiểm tra thành viên khi sử dụng |

Với phạm vi động, người có thể sửa nhãn hoặc chuyển tài nguyên vào nhóm có thể gián tiếp mở rộng quyền. Vì vậy, quyền quản lý thuộc tính quyết định phạm vi phải được bảo vệ và giám sát. Chỉ kiểm tra cú pháp selector là chưa đủ.

Khi giao diện duyệt hiển thị danh sách chốt, bộ cấp quyền phải thực thi đúng danh sách đó. Không được âm thầm chuyển sang đánh giá một selector rộng hơn lúc sử dụng.

## 5. Từ phê duyệt đến thực thi: giữ nguyên phạm vi

Một dòng phê duyệt hoặc một trường trong ticket không tự giới hạn quyền. Cần có điểm thực thi chính sách ở nơi cấp credential, mở kết nối hoặc xử lý thao tác trên tài nguyên.

Luồng tham khảo:

```text
Yêu cầu công việc
    ↓
Phân giải định danh từ kiểm kê đáng tin cậy
    ↓
Đánh giá chính sách và phê duyệt tập tài nguyên cụ thể
    ↓
Cấp quyền có thời hạn với đúng thao tác và đối tượng
    ↓
Kiểm tra tại điểm thực thi trước khi chấp nhận thao tác
    ↓
Thu hồi quyền, xử lý phiên và lưu bằng chứng
```

### 5.1. Khi nhận yêu cầu

Hệ thống cần xác nhận công việc, chủ thể, tập tài nguyên và thao tác đề nghị. Các trường tên môi trường, tenant hoặc loại tài nguyên phải được đối chiếu với kiểm kê, không chỉ lấy từ lời khai của người dùng.

Yêu cầu không xác định được đích, selector khớp bất thường hoặc thông tin mâu thuẫn cần bị từ chối hoặc đưa về bước làm rõ. Không thay một tập rỗng bằng “tất cả” để giúp yêu cầu chạy tiếp.

### 5.2. Khi phê duyệt và cấp quyền

Người duyệt phải nhìn thấy tập tài nguyên hoặc quy tắc động thực sự được cấp, cùng thao tác, thời hạn và ảnh hưởng dự kiến. Mọi điều chỉnh mở rộng tài nguyên sau phê duyệt phải có quyết định phù hợp với chính sách mới.

Trước khi kích hoạt, bộ cấp quyền kiểm tra lại những điều kiện có thể đã thay đổi: tài nguyên còn tồn tại, còn đúng tenant và môi trường, yêu cầu còn hiệu lực, và người nhận vẫn đủ điều kiện. Nếu đối tượng không còn khớp quyết định duyệt, không tự tìm tài nguyên thay thế có tên tương tự.

### 5.3. Khi thực thi

Điểm thực thi cần ràng buộc cả thao tác lẫn đích. Ví dụ, một API trung gian chỉ nhận các hành động `service.status` và `service.restart`, sau đó tra ánh xạ được kiểm soát cho `svc-72e8`.

Nếu API còn cho truyền lệnh tùy ý, đường dẫn executable, script hoặc đích kết nối tự chọn, người dùng có thể vượt qua phạm vi đã duyệt. Quyền sửa cấu hình dịch vụ, thay binary, thêm plugin hoặc chỉnh dữ liệu mà tiến trình đặc quyền sẽ thực thi cũng có thể tạo đường mở rộng quyền.

Điểm kiểm tra nên nằm gần nơi quyền được sử dụng và được lặp lại trước thao tác khi kiến trúc cho phép. Với hệ thống chỉ kiểm tra lúc mở phiên hoặc cấp token, cần tính đến khoảng trễ đồng bộ chính sách và hiệu lực còn lại của token. Không coi việc phê duyệt trước đó là bằng chứng rằng mọi thao tác sau đó đều hợp lệ.

### 5.4. Khi hết hạn hoặc bị thu hồi

Cần phân biệt:

- Ngừng cấp token hoặc credential mới.
- Gỡ quyền đã gắn cho chủ thể.
- Vô hiệu hóa token còn hiệu lực nếu cơ chế đích hỗ trợ.
- Kết thúc hoặc hạn chế phiên đang hoạt động theo khả năng hệ thống.
- Xác minh quyền truy cập thực tế đã mất hiệu lực.

Một phiên đã đăng nhập có thể vẫn giữ khả năng thao tác sau khi nhóm quyền bị gỡ, tùy cơ chế đích. Vì vậy, TTL của yêu cầu và TTL thực tế của token, phiên, kết nối cần được thiết kế thống nhất. Thu hồi quyền cũng không tự đảo ngược thay đổi hoặc dừng mọi tác vụ đã khởi chạy; những việc đó cần được xử lý riêng khi có sự cố.

## 6. Ví dụ: khởi động lại đúng hai service instance

Giả sử sự cố `INC-2048` yêu cầu kỹ sư `engineer-184` khởi động lại hai instance trong bảng kiểm kê. Không có nhu cầu sửa file, lấy secret, mở shell hoặc thay đổi dịch vụ thanh toán.

Đặc tả dưới đây là **YAML minh họa mô hình chính sách**, không phải cú pháp có thể nạp trực tiếp vào một sản phẩm PAM:

```yaml
request_id: INC-2048
subject_id: engineer-184
management_domain: acme
purpose: Khoi dong lai hai order-worker instance bi treo
scope_mode: fixed_resource_set
resource_type: os_service_instance
approved_resources:
  - resource_id: svc-72e8
    parent_host_id: vm-04c2
  - resource_id: svc-91a4
    parent_host_id: vm-77b1
allowed_actions:
  - service.status
  - service.restart
required_attributes:
  environment: production
  owner_team: orders
activation:
  maximum_duration_minutes: 20
  must_start_within_approved_window: true
  absolute_end_at_approved_window_close: true
execution:
  channel: pam_service_broker
  arbitrary_shell_allowed: false
  revalidate_before_each_action: true
  deny_if_target_mapping_is_uncertain: true
  automatic_scope_expansion: false
```

`required_attributes` là điều kiện bổ sung trên hai đối tượng đã chọn; nó không có nghĩa rằng mọi đối tượng production thuộc đội orders đều được phép. Tên các trường chỉ nhằm làm rõ quyết định thiết kế.

Broker, tức bộ trung gian thực thi, nhận một định danh thuộc tập đã duyệt và tra đối tượng tương ứng từ kiểm kê được kiểm soát. Nó không cho người dùng thay `parent_host_id` hoặc đường dẫn dịch vụ để chuyển thao tác sang đích khác.

Thời điểm hết hạn cần được tính cụ thể khi kích hoạt:

```text
expires_at = min(activated_at + 20 phút, thời điểm đóng cửa sổ được duyệt)
```

Yêu cầu kích hoạt sau khi cửa sổ đóng phải bị từ chối. Thời gian được tính bằng đồng hồ tin cậy của hệ thống, không lấy tùy ý từ máy của người yêu cầu.

Logic sau là **mã giả**, dùng để diễn giải các kiểm tra, không phải cơ chế cấp quyền hoàn chỉnh:

```text
function authorize(request, grant, trusted_now):
    require grant.is_activated
    require not grant.is_revoked
    require grant.activated_at <= trusted_now < grant.expires_at
    require request.subject_id == grant.subject_id
    require request.management_domain == grant.management_domain
    require request.action in grant.allowed_actions
    require request.resource_id in grant.approved_resource_ids

    target = trusted_inventory.resolve(
        grant.management_domain,
        request.resource_id
    )

    require target exists
    require target.type == grant.resource_type
    require target.parent_host_id == grant.approved_parent_of(target.id)
    require target.environment == grant.required_environment
    require target.owner_team == grant.required_owner_team
    require execution_channel == grant.required_channel

    return allow_for_this_action_and_target
```

Sau quyết định này, broker vẫn phải bảo đảm kết nối và lệnh thực thi trỏ đúng đối tượng vừa kiểm tra. Nếu ánh xạ tài nguyên thay đổi giữa lúc kiểm tra và sử dụng, cần phát hiện và kiểm tra lại, hoặc ràng buộc giao dịch với phiên bản ánh xạ đã xác minh. Một hàm trả về `allow` không tự giải quyết được khoảng hở giữa kiểm tra và thực thi.

### 6.1. Những thao tác được phép và bị từ chối

| Yêu cầu trong thời gian grant còn hiệu lực | Kết quả mong đợi | Căn cứ |
|---|---|---|
| Xem trạng thái `svc-72e8` qua broker | Cho phép | Đúng đích, đúng thao tác, đúng kênh |
| Khởi động lại `svc-91a4` qua broker | Cho phép | Nằm trong tập được duyệt |
| Khởi động lại `svc-33d0` trên cùng máy với `svc-72e8` | Từ chối | Không nằm trong tập tài nguyên |
| Khởi động lại máy `vm-04c2` | Từ chối | Sai loại tài nguyên và thao tác |
| Sửa cấu hình hoặc binary của `svc-72e8` | Từ chối | Không nằm trong tập thao tác |
| Thêm một instance mới có nhãn `owner_team=orders` | Không tự cấp quyền cho instance mới | Phạm vi là danh sách cố định |
| Truy cập trực tiếp bằng tài khoản quản trị thường trực | Không được phát sinh từ grant này | Phải kiểm tra và kiểm soát đường quyền riêng đó |
| Khởi động lại đúng đích sau `expires_at` | Từ chối | Hết thời hạn |

Quyền restart vẫn có khả năng gây gián đoạn và có thể bị lạm dụng bằng cách gọi liên tục. Tùy yêu cầu, chính sách có thể bổ sung giới hạn số lần thực hiện, khoảng nghỉ hoặc xác nhận cho lần thao tác tiếp theo. Đây là kiểm soát tác động bổ sung bên cạnh giới hạn tài nguyên.

## 7. Credential, vault và phiên phải giữ cùng phạm vi

### 7.1. Tài khoản dùng chung có thể làm phạm vi bị rộng trở lại

Giả sử vault chỉ cho lấy một credential được gắn tên `orders-prod-02`, nhưng credential đó cũng đăng nhập được nhiều máy khác. Giới hạn việc lấy secret chưa đồng nghĩa với giới hạn quyền thực tế ở một máy.

Cần kiểm tra đồng thời:

1. Ai được yêu cầu sử dụng credential.
2. Credential có quyền ở những tài nguyên nào.
3. Người dùng có nhận được giá trị secret hay chỉ dùng qua broker.
4. Kết nối và thao tác bị giới hạn ở đâu.
5. Khi thu hồi, những credential, token hoặc phiên nào vẫn còn dùng được.

Ưu tiên cơ chế cấp danh tính hoặc credential có phạm vi hẹp và thời hạn phù hợp khi hệ thống đích hỗ trợ. Với tài khoản dùng chung, cần khả năng quy trách nhiệm từ yêu cầu đến phiên và thao tác; chỉ ghi tên tài khoản dùng chung thường không đủ xác định ai đã sử dụng.

### 7.2. Luân chuyển credential phục vụ thu hồi nhưng không thay thế mọi bước

Nếu secret đã được tiết lộ hoặc có nguy cơ sao chép, luân chuyển là một phần quan trọng của xử lý quyền còn sót. Tuy nhiên, đổi mật khẩu không bảo đảm mọi token hoặc phiên đã tạo từ trước đều mất hiệu lực. Cần xác minh hành vi của cơ chế xác thực và xử lý các phiên liên quan.

Đối với tài khoản dịch vụ, phạm vi phải gắn với danh tính workload và tài nguyên cần dùng, cùng cơ chế cấp và gia hạn thích hợp. Không bê nguyên luồng phê duyệt thủ công của kỹ sư sang workload rồi để dịch vụ phụ thuộc vào việc một người nhớ gia hạn. Cũng không trao secret quản trị của dịch vụ cho người dùng chỉ vì họ cần thực hiện một thao tác vận hành hẹp.

### 7.3. Giới hạn mạng là một lớp kiểm soát bổ sung

Chỉ cho broker kết nối tới các máy đã chọn giúp giảm đường truy cập. Tuy nhiên, giới hạn kết nối tới một máy không tự phân biệt được hai dịch vụ trên máy đó. Vẫn cần kiểm soát thao tác ở lớp phù hợp với loại tài nguyên.

Nếu tài nguyên đích cho phép nhảy tiếp sang hệ thống khác, đọc credential dùng chung hoặc thay cấu hình của thành phần đặc quyền, phạm vi ảnh hưởng có thể lớn hơn danh sách đích ban đầu. Những phụ thuộc này cần được đưa vào đánh giá quyền và thiết kế kênh thực thi.

## 8. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Dùng wildcard trong đích nhưng màn hình duyệt chỉ nêu vài tên ví dụ | Cấp quyền cho nhiều đối tượng hơn người duyệt hiểu | Hiển thị và lưu toàn bộ tập hoặc mô tả rõ quy tắc động |
| Gán vai trò ở đối tượng cha để thao tác một đối tượng con | Quyền có thể lan sang các đối tượng cùng nhánh | Gán ở mức hẹp nhất được hỗ trợ và kiểm tra quyền hiệu lực |
| Tin nhãn do chính người nhận quyền sửa được | Người nhận có thể đưa tài nguyên khác vào phạm vi | Bảo vệ thao tác sửa nhãn quyết định phạm vi; kiểm tra thay đổi |
| Chỉ kiểm tra tài nguyên lúc tạo ticket | Tài nguyên có thể đổi tenant, chủ sở hữu hoặc ánh xạ trước lúc dùng | Kiểm tra lại khi cấp quyền và tại điểm sử dụng phù hợp |
| Cấp quyền hẹp qua PAM nhưng giữ đường quản trị thường trực rộng | Người dùng vẫn có khả năng vượt phạm vi | Kiểm kê quyền tổng thể và xử lý đường truy cập còn sót |
| Cho chạy shell rồi dựa vào hướng dẫn “chỉ sửa đúng máy/dịch vụ” | Không có ràng buộc kỹ thuật đủ mạnh đối với thao tác | Dùng giao diện thao tác hẹp hoặc cơ chế thực thi giới hạn đã xác minh |
| Tự thêm tài nguyên phụ thuộc sau khi thao tác thất bại | Mở rộng quyền ngoài phê duyệt | Tạo phần bổ sung được phê duyệt, gắn với yêu cầu gốc |
| Chỉ ghi log mở phiên | Không chứng minh được đích và thao tác thực tế | Ghi sự kiện theo yêu cầu, grant, tài nguyên và thao tác |

Nếu hệ thống đích không hỗ trợ mức chi tiết mong muốn, phải mô tả trung thực quyền rộng thực sự được cấp. Có thể dùng broker, tài khoản riêng hoặc cơ chế trung gian khác nếu chúng thực sự cưỡng chế được giới hạn. Nếu vẫn còn phạm vi rộng, cần xử lý theo quy trình ngoại lệ được tổ chức cho phép; không ghi nhận là đã đạt JEA chỉ dựa trên nội dung ticket.

## 9. Lưu bằng chứng để kiểm toán và ứng phó sự cố

Bằng chứng cần nối được **điều đã xin, điều đã duyệt, quyền đã cấp và việc thực sự đã làm**.

| Nhóm bằng chứng | Thông tin cần liên kết |
|---|---|
| Yêu cầu | Mã công việc, chủ thể, mục đích, thao tác và tài nguyên đề nghị |
| Phê duyệt | Người hoặc chính sách ra quyết định, thời điểm, tập tài nguyên cuối cùng, phiên bản chính sách |
| Kiểm kê | Miền quản lý, định danh đích, thuộc tính và phiên bản ánh xạ dùng để kiểm tra |
| Cấp quyền | Mã grant, danh tính hiệu lực, quyền thực tế, thời điểm kích hoạt và hết hạn |
| Thực thi | Chủ thể, grant, đích thực tế, thao tác, thời gian, kết quả cho phép/từ chối và kết quả thực hiện |
| Thu hồi | Sự kiện hết hạn/thu hồi, xử lý phiên hoặc credential liên quan, kết quả xác minh |

Quyết định cho phép và kết quả thực hiện là hai sự kiện khác nhau. Một yêu cầu được phép nhưng thất bại do lỗi dịch vụ không nên bị ghi thành “đã restart thành công”. Ngược lại, một thao tác xảy ra trực tiếp trên hệ thống đích mà không có sự kiện broker tương ứng cần được điều tra như một đường truy cập khác.

Log cần có thời gian đủ nhất quán để ghép sự kiện, kiểm soát quyền sửa/xóa và thời gian lưu theo yêu cầu của tổ chức. Không đưa mật khẩu, token hoặc nội dung secret vào log. Bản ghi phiên và đầu ra lệnh có thể chứa dữ liệu nhạy cảm nên cũng cần hạn chế truy cập.

Khi phát hiện thao tác ngoài phạm vi, các bước xử lý có thể gồm: thu hồi grant, ngăn cấp quyền tiếp, xử lý phiên và credential còn hiệu lực, bảo toàn bằng chứng và xác định quyền nào đã cho phép thao tác đó. Sau đó đối chiếu các tài nguyên thực sự bị tác động với tập được duyệt để xác định phạm vi sự cố. Không mặc định rằng gỡ một vai trò đã loại bỏ mọi đường truy cập.

## 10. Bài tập thiết kế và tiêu chí nghiệm thu

### Tình huống

Đội vận hành đề nghị “quyền quản trị nhóm orders trong 20 phút” để khởi động lại hai service instance `svc-72e8` và `svc-91a4`. Máy `vm-04c2` còn chứa dịch vụ thanh toán `svc-33d0`. Một instance mới của orders có thể xuất hiện trong thời gian xử lý.

### Yêu cầu thực hành

1. Viết lại yêu cầu bằng chủ thể, mục đích, hai định danh đích, thao tác và thời hạn cụ thể.
2. Chọn phạm vi cố định hay động, giải thích tài nguyên mới có được vào phạm vi hay không.
3. Chỉ ra điểm thực thi nào ngăn truy cập `svc-33d0`, reboot máy chủ và sửa binary.
4. Xác định credential hoặc tài khoản nào thực thi thao tác và chúng còn quyền ở đâu khác.
5. Thiết kế cách xử lý hết hạn, thu hồi sớm và thay đổi ánh xạ tài nguyên.
6. Liệt kê bằng chứng đủ để truy ngược một lần restart về yêu cầu và quyết định duyệt.

### Hướng giải tham khảo

Chọn tập cố định gồm hai service instance, giới hạn thao tác ở xem trạng thái và restart, thực thi qua broker đã kiểm soát ánh xạ đích. Không cấp quyền quản trị toàn nhóm hoặc toàn máy. Instance mới phải được bổ sung qua quyết định phê duyệt phù hợp nếu thực sự cần thao tác. Thời hạn kết thúc theo cửa sổ được duyệt, đồng thời xử lý token và phiên theo cơ chế đích.

### Kiểm thử chấp nhận trên môi trường thực hành

Chỉ thực hiện các ca kiểm tra trên tài nguyên thực hành được phép, với thao tác không gây ảnh hưởng ngoài bài tập.

| Ca kiểm tra | Kết quả cần quan sát |
|---|---|
| Đúng người, đúng đích, đúng thao tác, trong thời hạn | Thao tác thành công và có log liên kết với grant |
| Đích khác nhưng cùng máy, cùng đội hoặc cùng môi trường | Bị từ chối, không có thay đổi ở đích |
| Đúng đích nhưng thao tác sửa cấu hình hoặc reboot máy | Bị từ chối |
| Tài nguyên mới được thêm nhãn sau lúc duyệt tập cố định | Không tự nhận quyền |
| Tài nguyên đổi ánh xạ hoặc không còn đúng thuộc tính bắt buộc | Không tiếp tục theo ánh xạ chưa được xác minh |
| Grant hết hạn hoặc bị thu hồi trong khi phiên còn mở | Không tiếp tục thực hiện thao tác đặc quyền theo grant; xác minh cơ chế xử lý phiên |
| Thử đường truy cập trực tiếp nằm ngoài broker | Kết quả phản ánh chính sách tổng thể; mọi đường quyền rộng còn tồn tại phải được phát hiện và xử lý |
| Đối chiếu log ở broker với log của tài nguyên đích | Xác định được tài nguyên thực sự bị tác động và kết quả thực hiện |

Một thiết kế đạt mục tiêu khi giới hạn tài nguyên được thể hiện nhất quán từ yêu cầu đến quyền hiệu lực và thao tác thực tế. Bằng chứng cần cho thấy cả thao tác hợp lệ được thực hiện lẫn thao tác vượt phạm vi bị ngăn chặn, thay vì chỉ chứng minh rằng yêu cầu đã được phê duyệt.