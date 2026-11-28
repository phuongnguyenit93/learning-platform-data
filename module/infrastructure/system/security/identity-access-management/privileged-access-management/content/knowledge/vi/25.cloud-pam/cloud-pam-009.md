# Cloud permission boundary

## 1. Permission boundary giải quyết vấn đề gì?

Cloud permission boundary là ranh giới giới hạn quyền được thiết kế cho một principal, nhóm danh tính hoặc phạm vi quản trị cloud. Mục đích là giữ quyền hiệu lực trong một tập năng lực được chấp nhận, kể cả khi một bên được ủy quyền tiếp tục cấp role hoặc policy bên trong phạm vi đó.

Trong một số nền tảng, “permissions boundary” là tên một loại chính sách cụ thể gắn với danh tính. Ở nền tảng khác, tổ chức có thể đạt một phần mục tiêu tương tự bằng giới hạn cấp tổ chức, chính sách điều kiện, cơ chế ủy quyền hoặc cổng quản trị. Không nên coi các cơ chế này có cùng ngữ nghĩa chỉ vì đều được gọi là guardrail.

Trong bài học này, cần phân biệt:

- **Ranh giới quyền mong muốn**: cam kết của thiết kế, ví dụ đội ứng dụng không thể tạo danh tính có quyền quản trị tổ chức.
- **Cơ chế boundary thực tế**: loại chính sách và điểm thực thi mà nền tảng hỗ trợ.
- **Quyền hiệu lực**: những hành động principal thực sự làm được sau khi xét các nguồn quyền và giới hạn liên quan.

Trong PAM, boundary giúp tổ chức ủy quyền các tác vụ quản trị mà vẫn giới hạn phạm vi tác động. Tuy nhiên, boundary không thay thế việc kiểm kê danh tính, thiết kế role tối thiểu, kiểm soát credential, JIT/JEA, giám sát sử dụng và thu hồi quyền.

### Ví dụ mở đầu

Đội Orders được tự tạo role cho các workload của mình. Nếu không có giới hạn phù hợp, đội có thể tạo một role quản trị rộng rồi gắn role đó vào ứng dụng hoặc pipeline.

Một thiết kế boundary có thể đặt yêu cầu:

> Role do đội Orders tạo chỉ phục vụ ứng dụng Orders trong scope đã duyệt; không được quản lý IAM, sửa audit hoặc nhận quyền quản trị tổ chức.

Đây là ý định quản trị. Để biến nó thành kiểm soát, cần biết nền tảng có thể giới hạn những hành động nào, boundary áp dụng với loại principal nào và những đường cấp quyền nào nằm ngoài cơ chế đó.

Sau bài học, bạn có thể xây dựng một hợp đồng ủy quyền, phân tích phạm vi thực thi của boundary, bảo vệ vòng đời policy và thiết kế kiểm thử chứng minh giới hạn quyền.

## 2. Boundary là giới hạn, không phải nguồn cấp quyền

Một nhầm lẫn phổ biến là coi những hành động được liệt kê trong boundary như quyền đã cấp cho principal.

Trong mô hình boundary giới hạn quyền từ policy danh tính, một hành động phải được cấp quyền bởi nguồn cho phép phù hợp và đồng thời không vượt giới hạn áp dụng. Việc boundary cho phép hành động không tự tạo một phép cấp quyền.

### Mô hình tập hợp có phạm vi rõ ràng

Giả sử đang xét một đường cấp quyền chỉ dựa trên policy danh tính và một boundary, chưa có policy tài nguyên, giới hạn khác hay điều kiện bổ sung:

~~~text
Quyền ứng viên từ policy danh tính: P
Tập hành động nằm trong boundary: B

Quyền có thể có qua đường này: P giao B
~~~

Ví dụ:

~~~text
P = {đọc cấu hình, sửa cấu hình, sửa IAM}
B = {đọc cấu hình, sửa cấu hình}

Qua đường đang xét:
    đọc cấu hình: có thể được phép
    sửa cấu hình: có thể được phép
    sửa IAM: bị giới hạn
~~~

Nếu principal không được cấp hành động sửa cấu hình trong P, chỉ thêm hành động đó vào B không làm principal có quyền sửa.

Đây là minh họa cho một loại đường cấp quyền. Không dùng công thức này làm thuật toán chung cho mọi yêu cầu trên mọi cloud. Trong hệ thống thực tế còn có thể có policy tài nguyên, ủy quyền, phiên, chính sách cấp tổ chức và điều kiện theo ngữ cảnh.

### Hai câu hỏi phải tách riêng

1. Nguồn nào cấp hành động cho principal?
2. Cơ chế nào giới hạn hành động đó, và cơ chế ấy có áp dụng với chính đường cấp quyền này không?

Nếu không trả lời câu thứ hai, tổ chức có thể tưởng một boundary là trần quyền toàn cục trong khi cơ chế thực tế chỉ giới hạn một phần đường truy cập.

## 3. Phân biệt boundary với các lớp kiểm soát khác

| Cơ chế | Vai trò điển hình | Không nên mặc định |
|---|---|---|
| Role hoặc policy cấp quyền | Cho phép một tập hành động trong phạm vi | Role hẹp tự bảo vệ được khi principal có nguồn quyền khác |
| Permission boundary trên danh tính | Giới hạn tập quyền theo cơ chế nền tảng hỗ trợ | Luôn bao phủ mọi kiểu cấp quyền cho mọi loại principal |
| Chính sách cấp tổ chức | Đặt giới hạn ở cấp quản trị rộng | Tự cấp quyền cho danh tính hoặc có ngữ nghĩa giống boundary |
| Policy trên tài nguyên | Quy định principal nào được truy cập tài nguyên | Luôn chịu cùng quy tắc với policy danh tính |
| Điều kiện nhận role hoặc trust | Quy định ai được nhận danh tính hoặc quyền | Giới hạn đầy đủ những việc danh tính đó làm sau khi nhận |
| Giới hạn phiên | Thu hẹp quyền cho một phiên nếu hệ thống hỗ trợ | Tự tồn tại sau khi chuyển sang danh tính khác |
| JIT | Giảm khoảng thời gian quyền mạnh có hiệu lực | Tự giảm tập hành động được phép |
| JEA | Giới hạn thao tác thực hiện theo tác vụ | Tự bảo vệ khi phía sau có đường gọi API khác |
| Kiểm soát mạng | Giới hạn nguồn, đích hoặc đường kết nối | Thay cho kiểm tra IAM trên tài nguyên |
| Vault và quản lý credential | Bảo vệ, cấp phát và rotate bí mật | Tự làm quyền của credential trở nên tối thiểu |

Các lớp này có thể phối hợp. Điều quan trọng là gán đúng trách nhiệm cho từng lớp.

Ví dụ, credential được lấy từ vault và chỉ có hiệu lực trong một khoảng ngắn vẫn có thể thực hiện thao tác nguy hiểm nếu role quá rộng và boundary không bao phủ đường thực hiện đó.

## 4. Viết hợp đồng ủy quyền trước khi viết policy

Boundary hữu ích khi tổ chức biết rõ đang ủy quyền việc gì và giữ lại quyền quyết định nào.

Một hợp đồng ủy quyền nên mô tả:

- Đội hoặc chủ thể được ủy quyền.
- Principal mà đội được tạo, sửa hoặc gán quyền.
- Scope tài nguyên, ứng dụng và môi trường.
- Nhóm hành động được phép.
- Năng lực quản trị phải giữ lại cho cấp khác.
- Cơ chế bắt buộc để danh tính mới nhận giới hạn.
- Điều kiện thay đổi hoặc loại bỏ giới hạn.
- Ngoại lệ, chủ sở hữu và thời hạn.
- Bằng chứng cùng kế hoạch kiểm chứng.

### Ví dụ hợp đồng cho đội Orders

> Đội Orders được quản lý role workload phục vụ Orders tại môi trường thử nghiệm. Các role phải sử dụng boundary đã được phê duyệt. Đội không được sửa nội dung boundary, chọn một boundary khác, gỡ boundary hoặc tạo đường sử dụng danh tính quản trị nền tảng. Triển khai production và thay đổi IAM production đi theo luồng riêng.

Hợp đồng này làm rõ ý định nhưng vẫn cần kiểm tra khả năng kỹ thuật.

Chẳng hạn, nếu đội được sửa workload bất kỳ trong production hoặc dùng danh tính mạnh của đội khác, ranh giới đặt trên các role mới tạo chưa bao phủ toàn bộ quyền hiệu lực của đội.

### Phạm vi “không được” cũng cần cụ thể

“Không quản trị IAM” có thể gồm nhiều năng lực:

- Tạo hoặc sửa role definition.
- Gán quyền cho principal.
- Sửa trust hoặc cấu hình liên kết danh tính.
- Tạo credential cho danh tính khác.
- Gắn danh tính mạnh vào compute.
- Sửa boundary hoặc chính sách bảo vệ boundary.
- Sửa nhóm được ánh xạ thành quyền.
- Đổi policy trên tài nguyên để cấp quyền theo đường khác.

Không chỉ tìm một permission có tên “administrator”. Cần phân rã các đường có thể tạo quyền tương đương.

## 5. Xác định đối tượng và đường truy cập được boundary bảo vệ

### 5.1. Principal nào thực sự nhận boundary?

Lập danh mục các loại principal liên quan:

- Tài khoản con người.
- Danh tính liên kết từ hệ thống khác.
- Role hoặc danh tính có thể nhận phiên.
- Workload và tài khoản dịch vụ.
- Danh tính triển khai.
- Danh tính do dịch vụ quản lý.
- Phiên hoặc principal phát sinh khi có ủy quyền.

Cần đối chiếu loại nào được nền tảng hỗ trợ gắn boundary, loại nào dùng cơ chế khác. Không mô tả một danh tính là “đã có boundary” chỉ vì một tài khoản quản trị nó có boundary.

### 5.2. Boundary có đi theo chuỗi nhận quyền không?

Giả sử một người dùng bị giới hạn ở danh tính A nhưng được phép sử dụng danh tính B:

~~~text
Người dùng -> Danh tính A -> Danh tính B -> Tài nguyên
~~~

Không được mặc định boundary của A tự trở thành giới hạn của B. Cần xác định nền tảng đánh giá gì tại bước nhận B và tại yêu cầu do B thực hiện.

Nếu B có quyền rộng và quan hệ nhận B không bị kiểm soát phù hợp, giới hạn trên A có thể không đạt mục tiêu ban đầu.

### 5.3. Policy tài nguyên và cấp quyền trực tiếp

Một tài nguyên có thể có cơ chế cấp quyền riêng cho principal hoặc phiên. Tùy mô hình của nền tảng và kiểu principal được cấp, tương tác giữa policy tài nguyên với boundary có thể khác đường policy danh tính.

Vì vậy, không dùng lập luận:

> Principal có boundary nên mọi policy tài nguyên cấp thêm quyền đều bị chặn.

Thay vào đó, cần lập ma trận cho các đường cấp quyền được dùng:

| Đường cấp quyền | Cần xác minh |
|---|---|
| Policy danh tính | Boundary giới hạn hành động và scope thế nào? |
| Gán từ nhóm hoặc scope cha | Giới hạn có áp dụng với quyền kế thừa này không? |
| Policy tài nguyên cho danh tính | Kiểu principal và cách đánh giá có gì khác? |
| Cấp cho phiên hoặc principal phát sinh | Boundary, điều kiện phiên và quyền nguồn tương tác thế nào? |
| Nhận danh tính khác | Giới hạn nào được đánh giá ở đích? |
| Quyền tại dịch vụ hoặc ứng dụng | Có nằm trong điểm thực thi IAM đang xét không? |

Nếu một đường không được boundary bao phủ, cần một kiểm soát khác hoặc phải điều chỉnh cam kết phạm vi.

## 6. Bảo vệ chính boundary và quyền quản trị của nó

Một boundary có nội dung tốt nhưng principal tự gỡ được boundary sẽ không tạo ra ranh giới bền vững.

Cần kiểm soát ít nhất bốn nhóm năng lực.

### 6.1. Quyền gắn và gỡ boundary

Nếu được ủy quyền tạo role, chủ thể có thể cần được buộc gắn đúng boundary ngay khi tạo hoặc trước khi role được sử dụng.

Phải xét:

- Có đường tạo role không gắn boundary không?
- Có API khác tạo danh tính hoặc quyền tương đương không?
- Có thể gỡ boundary sau khi tạo không?
- Có thể thay bằng boundary rộng hơn không?
- Có khoảng thời gian role tồn tại và dùng được trước khi boundary được gắn không?

Một công cụ định kỳ phát hiện role thiếu boundary là kiểm soát phát hiện. Nó không tương đương cơ chế ngăn tạo hoặc ngăn sử dụng role thiếu giới hạn.

### 6.2. Quyền sửa nội dung và phiên bản boundary

Khóa tên hoặc định danh boundary chưa đủ nếu chủ thể được sửa nội dung phía sau cùng định danh đó.

Nếu nền tảng có phiên bản policy, cần kiểm soát các thao tác có thể đổi nội dung hiệu lực, chẳng hạn tạo revision, chọn revision áp dụng hoặc thay tham chiếu.

Cần biết một boundary được nhiều principal sử dụng. Một thay đổi có thể ảnh hưởng toàn bộ tập principal này mà không phát sinh sự kiện gắn boundary mới.

### 6.3. Quyền sửa điểm thực thi và thuộc tính điều kiện

Một boundary dựa trên tag, nhãn hoặc thuộc tính chỉ đáng tin nếu chủ thể không thể tùy ý đổi các thuộc tính để tự thỏa điều kiện.

Ví dụ, policy giới hạn thao tác theo nhãn sở hữu “Orders”, nhưng người dùng được tự đổi nhãn của tài nguyên bất kỳ thành “Orders”. Nếu không có kiểm soát bổ sung, nhãn không còn đại diện đáng tin cậy cho ranh giới sở hữu.

Tương tự, không dùng tham số môi trường do client tự khai làm bằng chứng tài nguyên thuộc staging.

### 6.4. Quyền sửa trust và nguồn danh tính

Một principal có thể giữ nguyên boundary của mình nhưng mở trust của một danh tính khác để nhận quyền rộng hơn.

Vì vậy, chính sách bảo vệ phải xem cả:

- Điều kiện nhận role hoặc danh tính.
- Nguồn liên kết workload.
- Nhóm được phép kích hoạt.
- Quyền ủy quyền và gán danh tính.
- Danh tính mà pipeline hoặc compute được sử dụng.

Cần bảo vệ ranh giới quyền bằng một tập kiểm soát phù hợp, không chỉ một đối tượng policy.

## 7. Thiết kế boundary theo tác vụ và phạm vi

### 7.1. Bắt đầu từ nhóm năng lực

Một boundary có thể được thiết kế theo nhóm tác vụ, chẳng hạn:

- Workload runtime: đọc dữ liệu cần thiết, không quản lý IAM.
- Triển khai ứng dụng: cập nhật tập tài nguyên được duyệt, không tự đổi danh tính runtime.
- Vận hành: xem trạng thái và sửa cấu hình trong phạm vi.
- Kiểm toán: đọc bằng chứng phù hợp, không sửa log hoặc policy.
- Tạo hạ tầng thử nghiệm: tạo loại tài nguyên được phép, không mở quyền xuyên môi trường.

Không nên dùng một boundary rộng duy nhất chỉ để tránh lỗi truy cập cho mọi đội. Boundary càng rộng, phần việc còn lại của role và các kiểm soát khác càng quan trọng.

### 7.2. Giới hạn hành động và tài nguyên cùng nhau

Chỉ giới hạn tên dịch vụ có thể vẫn quá rộng. Trong cùng một dịch vụ có thể có hành động đọc, sửa cấu hình, đổi policy và xuất dữ liệu với tác động khác nhau.

Chỉ giới hạn tài nguyên cũng chưa đủ nếu được chạy mã tùy ý trên tài nguyên mang danh tính mạnh.

Một thiết kế nên xét:

1. Hành động.
2. Tài nguyên.
3. Môi trường.
4. Danh tính thực thi.
5. Điều kiện của yêu cầu.
6. Năng lực tạo hoặc chuyển tiếp quyền.

### 7.3. Cẩn trọng với tập quyền quá rộng hoặc loại trừ

Mẫu “cho phép mọi thứ trừ một vài hành động” có thể khó duy trì khi dịch vụ và permission thay đổi. Những hành động mới có thể không phù hợp ý định ban đầu.

Mẫu allowlist hẹp cũng cần bảo trì để tác vụ vẫn làm được khi nền tảng thay đổi. Không có lựa chọn nào loại bỏ trách nhiệm đánh giá.

Cần ghi rõ cách xử lý permission mới, người chịu trách nhiệm và cách phát hiện một thay đổi làm mở rộng hoặc gián đoạn quyền.

### 7.4. Tách production và thử nghiệm

Một boundary cho môi trường thử nghiệm không nên tự được dùng làm giới hạn production chỉ vì cùng ứng dụng.

Scope, dữ liệu, danh tính phụ thuộc và mức ảnh hưởng có thể khác nhau. Nếu dùng chung định nghĩa, phải chứng minh các tham số và điều kiện thực tế vẫn tạo đúng ranh giới của từng môi trường.

## 8. Permission boundary và JIT/JEA

Boundary trả lời về trần quyền trong phạm vi cơ chế hỗ trợ. JIT trả lời quyền có hiệu lực khi nào. JEA trả lời chủ thể được thực hiện những tác vụ nào qua cơ chế giới hạn thao tác.

Một tổ hợp phù hợp có thể là:

~~~text
Đủ điều kiện xin quyền
    -> Yêu cầu tác vụ cụ thể
    -> Phê duyệt và xác thực phù hợp
    -> Kích hoạt role trong thời hạn
    -> Thực hiện tác vụ qua điểm kiểm soát
    -> Role, boundary và các chính sách liên quan giới hạn quyền
    -> Kết thúc và kiểm chứng
~~~

### Những điều không tự xảy ra

- Có boundary không tự làm quyền thành tạm thời.
- Có JIT không tự ngăn permission quá rộng.
- Có giao diện JEA không tự chặn đường gọi API trực tiếp khác.
- Hết phiên không tự xóa thay đổi hoặc credential đã tạo.
- Gỡ role không tự chứng minh mọi nguồn quyền tương đương đã mất.

Với PAM, cần nối các cơ chế này vào cùng một vòng đời: kiểm kê, cấp quyền, sử dụng, giám sát, kết thúc và đối soát.

Ví dụ, một kỹ sư được kích hoạt role triển khai trong thời gian ngắn. Boundary cấm quản lý IAM nhưng role vẫn có thể đưa mã tùy ý vào workload có dữ liệu nhạy cảm. JIT và boundary chưa giải quyết hết rủi ro chuỗi triển khai; vẫn cần kiểm soát mã, artifact, runtime identity và tác vụ đã duyệt.

## 9. Hồ sơ thiết kế boundary minh họa

Mẫu sau là hồ sơ thiết kế, không phải cú pháp policy để nhập vào cloud. Các tên năng lực có ý nghĩa mô tả; phải ánh xạ chúng thành hành động, tài nguyên và điều kiện được nền tảng hỗ trợ.

~~~yaml
boundary_design_record:
  boundary_reference: example-orders-staging-ceiling
  definition_revision: revision-3
  accountable_owner: platform-security
  delegated_team: team-orders
  purpose: constrain-application-workload-roles

  intended_scope:
    application: orders
    environment: staging
    resource_set_reference: "<tập tài nguyên đã được kiểm chứng>"

  intended_capability_ceiling:
    - read-orders-operational-data
    - write-orders-application-output
    - read-orders-runtime-configuration

  excluded_capabilities:
    - manage-iam
    - modify-identity-trust
    - create-long-lived-credentials
    - change-audit-configuration
    - access-production-resources
    - select-privileged-runtime-identity

  delegation_requirements:
    approved_boundary_required: true
    boundary_removal_by_delegated_team: deny
    boundary_replacement_by_delegated_team: deny
    boundary_definition_edit_by_delegated_team: deny

  alternate_paths_to_verify:
    - resource-policy-grants
    - inherited-assignments
    - identity-delegation
    - workload-code-and-runtime-identity
    - cross-domain-trust

  lifecycle:
    change_review_reference: REVIEW-EX-031
    affected_principal_inventory_reference: INVENTORY-EX-031
    exception_reference: none
    verification_plan_reference: VERIFY-EX-031
~~~

Hồ sơ không phải bằng chứng đã thực thi. Đặc biệt, những mục “deny” chỉ mô tả yêu cầu quản trị nếu chưa được chuyển thành chính sách thực tế.

Một bản ánh xạ triển khai cần trả lời:

| Yêu cầu trong hồ sơ | Bằng chứng cần có |
|---|---|
| Đúng boundary bắt buộc | Cấu hình điểm cấp quyền và ca tạo principal thiếu hoặc sai boundary |
| Không gỡ boundary | Chính sách bảo vệ thao tác gỡ và ca kiểm thử bị từ chối |
| Không sửa định nghĩa | Quyền quản trị policy được tách, lịch sử revision được bảo vệ |
| Không truy cập production | Phân tích scope và thử yêu cầu ngoài môi trường |
| Không nhận danh tính mạnh | Phân tích trust, quyền sử dụng danh tính và ca từ chối |
| Không đi vòng qua policy tài nguyên | Kiểm tra các kiểu cấp quyền thực tế và lớp kiểm soát bổ sung nếu cần |

Nếu nền tảng không hỗ trợ một yêu cầu bằng boundary, phải ghi cơ chế thay thế đang chịu trách nhiệm. Không thêm một dòng vào hồ sơ rồi coi yêu cầu đã được đáp ứng.

## 10. Quy trình ủy quyền tạo danh tính có kiểm soát

### 10.1. Tách quyền tạo khỏi quyền sử dụng tùy ý

Một đội có thể được phép đề nghị tạo danh tính mà không trực tiếp có toàn bộ API quản trị IAM.

Ví dụ, một cổng cấp phát nhận yêu cầu, kiểm tra scope và tạo danh tính theo mẫu đã phê duyệt. Cổng dùng danh tính thực thi riêng; người dùng không nhận credential quản trị của cổng.

Quy trình minh họa:

1. Xác minh người yêu cầu và đội sở hữu.
2. Kiểm tra ứng dụng, môi trường và mục đích.
3. Chọn boundary đã duyệt từ phía hệ thống.
4. Tạo principal cùng các ràng buộc cần thiết.
5. Gán policy quyền tối thiểu cho tác vụ.
6. Đọc lại cấu hình thực tế và xác minh điều kiện bảo vệ.
7. Chỉ mở đường sử dụng hoặc cấp credential khi các bước bắt buộc đạt.
8. Ghi bằng chứng và đăng ký vào inventory.

Nếu API yêu cầu tạo và gắn giới hạn qua nhiều bước, phải xử lý trạng thái dở dang. Principal không nên được mở đường sử dụng trong khoảng chưa hoàn tất các ràng buộc bắt buộc.

### 10.2. Không tin boundary do client tự chọn

Nếu giao diện cho nhập một boundary reference bất kỳ, người dùng có thể chọn policy rộng hơn hoặc một đối tượng có cùng tên hiển thị nhưng khác miền quản lý.

Cần xác minh định danh chính xác, chủ sở hữu, revision hoặc tham chiếu hiệu lực theo mô hình nền tảng. Scope nguồn của policy cũng phải thuộc tập được phép.

Tương tự, nếu người dùng chọn runtime identity cho workload, cổng phải kiểm tra danh tính đó. Giới hạn trên role vừa tạo không bảo vệ một workload được gắn danh tính mạnh khác.

### 10.3. Bảo vệ chính cổng cấp phát

Cổng có thể là một điểm đặc quyền cao vì nó tạo danh tính và gán policy.

Cần quản lý:

- Ai được sửa mã và cấu hình cổng.
- Danh tính nào cổng dùng để thao tác cloud.
- Phạm vi tài nguyên mà cổng được quản lý.
- Mẫu role và boundary được tham chiếu.
- Nguồn dữ liệu dùng để xác định đội và môi trường.
- Cách xử lý yêu cầu bị từ chối, lỗi từng phần và retry.

Nếu sửa một tham số cấu hình là đủ để cổng tạo role ngoài ranh giới, tham số đó thuộc phạm vi thay đổi đặc quyền.

### 10.4. Tránh mở quyền khi kiểm tra bắt buộc không thực hiện được

Nếu một điểm kiểm tra thiết yếu không hoạt động, quy trình nên có hành vi đã xác định rõ. Với yêu cầu tạo đặc quyền mới, không nên mặc định bỏ qua kiểm tra rồi mở quyền.

Tổ chức có thể cần một đường ngoại lệ khẩn cấp riêng với thẩm quyền, thời hạn và bằng chứng. Ngoại lệ này không nên là một cờ tùy ý do người yêu cầu tự bật.

## 11. Kiểm thử boundary bằng yêu cầu cụ thể

Kiểm thử phải phân biệt các nguyên nhân từ chối. Một thao tác thất bại vì principal chưa có permission không chứng minh boundary đã chặn nó.

### 11.1. Thiết kế ca kiểm thử có ý nghĩa

Một ca kiểm thử nên xác định:

- Principal và cách nhận phiên.
- Policy cấp quyền đang có.
- Boundary và revision đang áp dụng.
- Các chính sách khác có thể ảnh hưởng.
- Hành động và tài nguyên đích.
- Kết quả mong đợi.
- Nguồn bằng chứng giúp giải thích kết quả.

Để kiểm chứng giới hạn một hành động trong môi trường thử nghiệm, có thể cần chủ động cấp hành động đó bằng một policy danh tính được kiểm soát, rồi xác minh boundary thực sự giới hạn đường này. Không mở rộng quyền trên production chỉ để thử.

### 11.2. Ma trận kiểm thử minh họa

| Ca kiểm thử | Kết quả hoặc bằng chứng mong đợi |
|---|---|
| Có permission và hành động nằm trong boundary, đúng scope | Được phép nếu các điều kiện khác thỏa mãn |
| Boundary chứa hành động nhưng không có nguồn cấp quyền phù hợp | Không tự được phép chỉ nhờ boundary |
| Policy danh tính cấp hành động ngoài boundary | Bị giới hạn trên đường mà boundary được thiết kế bao phủ |
| Đúng hành động nhưng tài nguyên ngoài scope | Bị từ chối theo giới hạn đã thiết kế |
| Tạo role thiếu boundary bắt buộc | Bị chặn hoặc không được mở đường sử dụng theo thiết kế |
| Tạo role với boundary không được duyệt | Bị từ chối |
| Gỡ hoặc thay boundary | Bị từ chối đối với bên được ủy quyền |
| Sửa nội dung hoặc revision hiệu lực của boundary | Bị từ chối đối với bên không có thẩm quyền |
| Đổi tag hoặc thuộc tính để vượt scope | Không tạo quyền ngoài hợp đồng ủy quyền |
| Nhận một danh tính mạnh khác | Bị từ chối nếu ngoài tập được duyệt |
| Cấp quyền qua policy tài nguyên | Kết quả phù hợp mô hình nền tảng và không vượt cam kết kiểm soát |
| Dùng API thay vì giao diện cấp phát | Không đi vòng qua kiểm soát bắt buộc |
| Thay đổi policy khi phiên cũ còn tồn tại | Kết quả và thời điểm hiệu lực đúng cơ chế đã xác định |
| Gọi từ workload có thể sửa mã | Không tạo đường vượt ranh giới đã tuyên bố |
| Kết thúc quyền JIT | Không nhận lại quyền mới ngoài thời hạn; phiên cũ được xử lý đúng thiết kế |
| Nguồn audit gặp lỗi | Có hành vi và cảnh báo phù hợp chính sách, không báo kiểm soát hoàn chỉnh khi thiếu bằng chứng |

“Không vượt cam kết kiểm soát” không có nghĩa mọi boundary đều tự chặn tất cả đường trong bảng. Nếu một đường không nằm trong cơ chế, ca kiểm thử phải xác nhận lớp bổ sung đang thực thi hoặc ghi nhận một khoảng trống cần xử lý.

### 11.3. Kết hợp phân tích policy và thử nghiệm thực tế

Công cụ phân tích hoặc mô phỏng có thể hỗ trợ hiểu quyền, nhưng cần biết nó bao phủ những loại policy, điều kiện và principal nào.

Một kết quả mô phỏng không nên được xem là bằng chứng cho lớp quyền mà công cụ không mô hình hóa.

Tương tự, một lần thử thành công hoặc thất bại chưa đủ để suy ra mọi scope. Hãy chọn ca kiểm thử đại diện cho các đường cấp quyền quan trọng và ghi rõ giới hạn của kết luận.

## 12. Thay đổi boundary và quản lý drift

### 12.1. Thay đổi boundary là thay đổi đặc quyền hàng loạt

Một boundary dùng chung có thể liên quan đến nhiều principal. Mở rộng boundary không tự cấp permission mới, nhưng có thể làm những permission đã được cấp sẵn trước đó bắt đầu có hiệu lực qua đường đang bị giới hạn.

Ví dụ:

~~~text
Trước thay đổi:
    Policy danh tính đã cấp đọc và sửa IAM.
    Boundary chỉ chứa quyền đọc.
    Sửa IAM chưa có hiệu lực qua đường này.

Sau khi boundary được mở rộng để chứa sửa IAM:
    Permission sửa IAM đã có trong policy danh tính
    có thể bắt đầu có hiệu lực nếu các điều kiện khác thỏa mãn.
~~~

Đây là lý do phải xem cả policy cấp quyền hiện có khi đánh giá tác động của việc nới boundary.

Thu hẹp boundary cũng có thể gây gián đoạn vận hành. Không nên triển khai thay đổi diện rộng chỉ vì nội dung mới “an toàn hơn” mà chưa đánh giá tác vụ bị ảnh hưởng.

### 12.2. Quy trình thay đổi

Một quy trình phù hợp có thể gồm:

1. Xác định mục đích và khác biệt của revision mới.
2. Liệt kê principal đang dùng boundary.
3. Đối soát permission đã được cấp nhưng đang bị giới hạn.
4. Đánh giá các nguồn quyền và đường nhận danh tính liên quan.
5. Kiểm thử trên môi trường được phép với ca thành công và từ chối.
6. Phê duyệt độc lập phù hợp mức ảnh hưởng.
7. Triển khai theo phạm vi kiểm soát và theo dõi tác vụ quan trọng.
8. Đọc lại cấu hình hiệu lực, cập nhật inventory và bằng chứng.
9. Xử lý rollback nếu cần theo một phương án đã được đánh giá.

Rollback cũng có thể khôi phục quyền rộng trước đó. Không coi quay về revision cũ là mặc nhiên an toàn.

### 12.3. Drift cần theo dõi

Drift có thể nằm ở nhiều nơi:

- Principal mới không có boundary bắt buộc.
- Boundary reference khác mẫu được duyệt.
- Nội dung policy dưới cùng tham chiếu đã thay đổi.
- Nhóm hoặc trust mở rộng tập người nhận quyền.
- Policy tài nguyên tạo đường cấp quyền ngoài ý định.
- Runtime identity bị thay.
- Thuộc tính điều kiện bị đổi.
- Đường gọi API mới đi vòng qua cổng cấp phát.

Kiểm tra định kỳ giúp phát hiện drift nhưng cần phân biệt với biện pháp ngăn chặn. Thời gian từ khi drift xuất hiện tới khi phát hiện và xử lý là một phần rủi ro cần quản lý.

### 12.4. Chỉ số phục vụ vận hành

Có thể theo dõi:

- Số principal thuộc phạm vi bắt buộc nhưng thiếu boundary hợp lệ.
- Số thay đổi boundary chưa liên kết được phê duyệt.
- Số ngoại lệ quá hạn.
- Số đường cấp quyền chưa được kiểm chứng.
- Thời gian phát hiện và xử lý drift.
- Số sự cố tác vụ bị chặn do thay đổi boundary.
- Số kết luận “bị boundary chặn” thiếu bằng chứng nguyên nhân.

Không đặt một ngưỡng chung cho mọi tổ chức. Chỉ số cần gắn với phạm vi, mức ảnh hưởng và năng lực ứng phó thực tế.

## 13. Audit và bằng chứng ranh giới quyền

Một báo cáo “tất cả role đều có boundary” mới chứng minh một thuộc tính cấu hình, chưa chứng minh quyền hiệu lực bị giới hạn đúng.

Bằng chứng nên liên kết được:

~~~text
Hợp đồng ủy quyền
  -> Boundary và revision đã duyệt
  -> Policy cấp quyền và principal được áp dụng
  -> Điểm bảo vệ gắn, gỡ, sửa boundary
  -> Các nguồn quyền khác liên quan
  -> Yêu cầu thực tế và kết quả
  -> Thay đổi, ngoại lệ và đối soát sau sự kiện
~~~

Các dữ liệu phù hợp gồm:

| Nhóm bằng chứng | Nội dung |
|---|---|
| Thiết kế | Mục đích, scope, chủ sở hữu, giới hạn và đường không bao phủ |
| Policy | Định danh, nội dung hoặc bản chụp cần thiết, revision và thay đổi |
| Áp dụng | Principal, boundary reference, thời điểm gắn hoặc gỡ |
| Ủy quyền | Người yêu cầu, người phê duyệt, nhóm và nguồn danh tính |
| Sử dụng | Principal thực thi, hành động, tài nguyên, ngữ cảnh và kết quả |
| Giải thích | Nguồn quyết định hoặc bằng chứng giúp phân biệt nguyên nhân từ chối |
| Ngoại lệ | Thẩm quyền, phạm vi, thời hạn và biện pháp xử lý |
| Kết thúc | Thu hồi quyền, phiên còn tồn tại và hiện vật cần đối soát |

Không ghi token, mật khẩu hoặc khóa bí mật vào log. Khi lưu bản chụp policy và cấu hình, phải quản lý dữ liệu nhạy cảm và quyền đọc bằng chứng.

### Không suy nguyên nhân chỉ từ mã từ chối

Một yêu cầu bị từ chối có thể do:

- Không có nguồn cấp permission.
- Boundary giới hạn.
- Policy cấp tổ chức.
- Điều kiện chưa thỏa mãn.
- Policy tại tài nguyên hoặc dịch vụ.
- Credential hết hiệu lực hoặc không hợp lệ.
- Tài nguyên không tồn tại hoặc không đúng phạm vi.

Cần dùng dữ liệu quyết định mà nền tảng cung cấp, cùng bản cấu hình và ngữ cảnh tương ứng. Nếu không đủ bằng chứng, báo rõ chỉ xác nhận thao tác bị từ chối, chưa xác định chắc boundary là nguyên nhân.

### Bảo vệ bằng chứng độc lập

Bên được ủy quyền không nên đồng thời có khả năng tùy ý xóa lịch sử áp dụng boundary hoặc sửa log kiểm chứng.

Cần xem cả quyền đổi nơi xuất log, chính sách lưu giữ và quyền truy cập đích lưu trữ, không chỉ thao tác xóa log trực tiếp.

## 14. Ứng phó khi boundary bị thay hoặc không bao phủ đủ

### Tình huống 1: principal tự gỡ được boundary

Đây là vấn đề ở quyền quản trị giới hạn, không chỉ ở nội dung policy.

Cần xác định:

1. Principal nào đã gỡ hoặc thay boundary.
2. Trong khoảng thời gian nào quyền có thể rộng hơn.
3. Những policy cấp quyền nào đã có sẵn.
4. Credential, phiên và danh tính nào được sử dụng.
5. Những thay đổi và hiện vật nào được tạo.
6. Vì sao điểm bảo vệ thao tác gỡ không có hiệu lực.

Gắn lại boundary là một bước xử lý cấu hình. Nó không tự xóa role mới, credential mới, policy tài nguyên hay mã đã triển khai trong khoảng bị ảnh hưởng.

### Tình huống 2: có đường cấp quyền khác ngoài cơ chế boundary

Nếu principal vẫn thực hiện được hành động ngoài trần mong muốn qua một policy tài nguyên hoặc danh tính trung gian, cần phân tích mô hình đánh giá thay vì chỉ sửa allowlist của boundary theo phỏng đoán.

Có thể cần:

- Thu hẹp policy tài nguyên.
- Hạn chế việc nhận hoặc sử dụng danh tính khác.
- Bảo vệ runtime identity và chuỗi triển khai.
- Áp dụng giới hạn ở cấp quản trị khác.
- Thay cách ủy quyền để loại bỏ đường không kiểm soát được.

Nếu một giới hạn không thể thực thi với cơ chế đã chọn, phải sửa thiết kế hoặc ghi nhận ngoại lệ có thẩm quyền.

### Tình huống 3: boundary gây gián đoạn

Không nên chữa mọi lỗi bằng cách chuyển sang boundary cho phép toàn bộ.

Trước hết cần xác định hành động bị chặn, scope, nguồn quyền và điều kiện. Có thể tác vụ đang làm nhiều hơn nhu cầu, gọi nhầm tài nguyên hoặc sử dụng sai danh tính.

Nếu cần mở quyền, thay đổi phải có phạm vi và bằng chứng. Một ngoại lệ có thời hạn cũng cần kế hoạch kết thúc và đối soát.

## 15. Tình huống thực tế: đội Orders tự quản lý role workload

### Bối cảnh

Đội nền tảng muốn cho Orders tự cấp role workload tại staging. Production phải được quản lý riêng.

Mẫu ban đầu yêu cầu đội gắn boundary B vào role mới, nhưng đội vẫn có quyền:

- Gỡ boundary.
- Sửa nội dung policy B.
- Thay runtime identity của workload bằng một danh tính khác.
- Sửa nhãn môi trường của tài nguyên.
- Cấp quyền trên một số tài nguyên bằng policy riêng.

Việc kiểm tra “role mới đã gắn B” không đủ để chứng minh ranh giới.

### Thiết kế cải thiện

Đội nền tảng giữ quyền quản trị nội dung B và chính sách bảo vệ nó. Luồng cấp phát chỉ nhận role thuộc scope staging của Orders và buộc dùng định danh boundary đã duyệt.

Bên được ủy quyền không được gỡ, thay hoặc mở rộng B. Việc đổi thuộc tính dùng làm điều kiện sở hữu phải đi qua kiểm soát phù hợp.

Runtime identity có một tập được phép riêng. Những nguồn cấp quyền trên tài nguyên và quan hệ nhận danh tính khác được đối soát để bảo đảm không tạo đường ngoài hợp đồng.

Các permission thực tế của role vẫn được cấp tối thiểu cho từng workload; không dựa vào boundary để biện minh cho việc gán policy quản trị rộng cho tất cả.

### Một yêu cầu cụ thể

Workload tạo báo cáo của Orders cần đọc tập dữ liệu thử nghiệm và ghi kết quả vào nơi lưu trữ đầu ra. Nó không cần sửa policy tài nguyên hoặc nhận danh tính triển khai.

Thiết kế cấp:

- Danh tính workload riêng có chủ sở hữu.
- Policy cấp đúng thao tác đọc và ghi cần thiết.
- Boundary giới hạn trong năng lực được duyệt.
- Nguồn nhận credential đã xác minh.
- Log đủ để liên kết workload với thao tác dữ liệu phù hợp khả năng nền tảng.

Boundary không thay thế quyền trên dữ liệu hoặc chính sách tại nơi lưu trữ. Cả hai phải được đối chiếu.

### Các kết quả cần chứng minh

| Hành động | Kết quả mong đợi |
|---|---|
| Đọc dữ liệu thử nghiệm đã duyệt | Được phép |
| Ghi vào đầu ra của Orders staging | Được phép |
| Sửa chính sách IAM | Bị từ chối |
| Gỡ hoặc sửa boundary | Bị từ chối |
| Truy cập dữ liệu production | Bị từ chối |
| Nhận danh tính triển khai mạnh hơn | Bị từ chối |
| Đổi nhãn để giả tài nguyên thuộc phạm vi | Không tạo quyền mới ngoài ý định |
| Gán policy rộng hơn vào role thử nghiệm | Không làm vượt trần qua đường boundary bao phủ; thao tác gán cũng phải đúng quyền ủy quyền |
| Nhận quyền qua policy tài nguyên | Được kiểm chứng riêng và không vượt hợp đồng tổng thể |
| Thu hồi nguồn workload | Khả năng cấp mới và phiên tồn tại được xử lý theo thiết kế |

Nếu ca policy tài nguyên cho thấy quyền vượt ý định, phải bổ sung kiểm soát thích hợp. Không bỏ ca này khỏi báo cáo chỉ vì role đã có boundary hợp lệ.

## 16. Những lỗi thường gặp

### Coi boundary là một role cấp quyền

Boundary giới hạn một đường quyền theo mô hình hỗ trợ; nó không tự tạo permission mà principal chưa được cấp.

### Coi boundary là trần toàn cục của mọi cloud

Phải biết loại principal, nguồn cấp quyền và điểm thực thi được bao phủ. Không suy rộng từ một đường policy danh tính sang mọi đường truy cập.

### Khóa tham chiếu nhưng cho sửa nội dung

Principal không đổi boundary reference nhưng vẫn mở rộng nội dung hoặc revision hiệu lực. Cần bảo vệ cả đối tượng và vòng đời policy.

### Dùng boundary để hợp thức hóa policy quản trị rộng

Policy cấp quá rộng làm tăng rủi ro khi boundary bị thay hoặc có đường cấp khác. Least privilege vẫn cần áp dụng ở nguồn cấp quyền.

### Quên người sửa mã workload

Một người không đọc secret trực tiếp nhưng được sửa mã runtime có thể có đường tác động tới dữ liệu và secret của runtime.

### Dựa vào tag tự khai

Nếu người dùng tự đổi được thuộc tính dùng để quyết định scope, thuộc tính đó có thể không còn đại diện đáng tin cậy cho ranh giới.

### Nhầm phát hiện với ngăn chặn

Một báo cáo hàng ngày về role thiếu boundary không ngăn role đó được sử dụng trước thời điểm báo cáo.

### Kết luận boundary hiệu quả từ một lỗi truy cập

Thao tác có thể thất bại vì chưa có permission hoặc một lớp khác. Cần thiết kế ca kiểm thử phân biệt nguyên nhân.

### Bỏ qua tác động khi nới boundary

Permission rộng đã tồn tại trong policy danh tính có thể bắt đầu có hiệu lực khi trần được mở. Cần đánh giá tập principal bị ảnh hưởng.

### Gắn lại boundary rồi kết luận sự cố đã hết

Những quyền, credential hoặc thay đổi đã tạo có thể còn tồn tại. Cần đối soát hậu quả và các đường truy cập tồn dư.

## 17. Bài thực hành

### Phần A: phân tích một đường quyền đơn giản

Giả sử mô hình thử nghiệm chỉ có policy danh tính và boundary cho đường đang xét, mọi điều kiện khác đều thỏa mãn:

~~~text
Policy P:
    đọc cấu hình Orders staging
    sửa cấu hình Orders staging
    sửa policy IAM staging

Boundary B:
    đọc cấu hình Orders staging
    sửa cấu hình Orders staging
    đọc trạng thái Orders staging
~~~

Hãy giải thích kết quả mong đợi cho từng hành động:

| Hành động | Gợi ý phân tích |
|---|---|
| Đọc cấu hình Orders staging | Có trong cả nguồn cấp và giới hạn |
| Sửa cấu hình Orders staging | Có trong cả nguồn cấp và giới hạn |
| Sửa policy IAM staging | Có nguồn cấp nhưng ngoài giới hạn của đường đang xét |
| Đọc trạng thái Orders staging | Có trong boundary nhưng chưa có nguồn cấp |
| Sửa cấu hình Payments staging | Không thuộc tập quyền đã mô tả |
| Sửa cấu hình Orders production | Khác môi trường và scope |

Sau đó thêm một nguồn cấp quyền trên tài nguyên. Không áp dụng máy móc kết luận từ mô hình hai tập hợp; hãy xác định nền tảng thực tế đánh giá đường mới thế nào.

### Phần B: thiết kế một hợp đồng ủy quyền

Đội Payments được tạo role workload tại staging, nhưng không được:

- Quản trị IAM ngoài phạm vi được ủy quyền.
- Sửa nội dung hoặc gỡ boundary bắt buộc.
- Nhận danh tính production.
- Tắt audit.
- Tự thay thuộc tính sở hữu để nhận thêm scope.

Sản phẩm cần tạo:

1. Hợp đồng ủy quyền có chủ sở hữu.
2. Danh mục principal và các đường cấp quyền.
3. Boundary dự kiến cùng bản ánh xạ vào nền tảng.
4. Chính sách bảo vệ gắn, gỡ, thay và sửa boundary.
5. Quy trình cấp phát xử lý lỗi từng phần.
6. Bảng kiểm thử có ca được phép, bị giới hạn và đi vòng.
7. Kế hoạch đổi revision, rollback và phát hiện drift.
8. Chuỗi bằng chứng kiểm toán.
9. Phương án xử lý khi không thể thực thi một yêu cầu bằng boundary.

Thực hành trên môi trường và danh tính được phép. Chọn thao tác ít tác động cho ca kiểm thử từ chối; không cần mở dữ liệu production để chứng minh ranh giới.

Một phương án đạt phải phân biệt ý định, cấu hình và kết quả thực tế. Mọi kết luận về trần quyền cần chỉ ra những đường đã kiểm chứng và những đường chưa được bao phủ.

## 18. Câu hỏi tự kiểm tra

**Boundary chứa quyền đọc có tự cấp quyền đọc không?**

Không, trong mô hình boundary giới hạn quyền từ policy danh tính. Principal vẫn cần một nguồn cấp quyền phù hợp; phải xét mô hình cụ thể của nền tảng.

**Vì sao không thể dùng một công thức giao tập hợp cho mọi cloud request?**

Vì yêu cầu có thể chịu nhiều nguồn cấp quyền, kiểu principal và lớp policy với ngữ nghĩa khác nhau. Công thức đơn giản chỉ đúng trong phạm vi giả định đã nêu.

**Khóa boundary reference có đủ không?**

Không nếu principal còn sửa được nội dung, revision hiệu lực hoặc điểm thực thi của boundary.

**Một boundary cho danh tính A có tự giới hạn danh tính B mà A nhận được không?**

Không thể mặc định. Cần kiểm tra cơ chế nhận quyền và chính sách áp dụng tại B.

**Tại sao vẫn cần least privilege trong policy cấp quyền?**

Vì boundary có thể thay đổi, không bao phủ mọi đường hoặc gặp sai cấu hình. Permission rộng ở nguồn cấp cũng làm tăng tác động khi trần được nới.

**Nới boundary có thể làm tăng quyền ngay cả khi không gán policy mới không?**

Có. Những permission đã được cấp nhưng đang bị boundary giới hạn có thể bắt đầu có hiệu lực qua đường đó nếu các điều kiện khác thỏa mãn.

**Một lỗi từ chối truy cập có chứng minh boundary hoạt động không?**

Chưa đủ. Cần xác định thao tác có nguồn cấp quyền và bằng chứng chỉ ra giới hạn hoặc nguyên nhân liên quan.

**Permission boundary có thay cho JIT và quản lý credential không?**

Không. Chúng xử lý những chiều khác nhau: tập quyền, thời gian hiệu lực và bằng chứng kỹ thuật để sử dụng danh tính.

**Gắn lại boundary sau sự cố có xóa quyền tồn dư không?**

Không. Cần đối soát credential, role, policy tài nguyên, trust, workload và các thay đổi đã tạo trong khoảng bị ảnh hưởng.
