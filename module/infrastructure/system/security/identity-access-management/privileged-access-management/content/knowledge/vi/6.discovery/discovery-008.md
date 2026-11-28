# Phát hiện quyền kế thừa trong kiểm kê đặc quyền

## 1. Quyền kế thừa là gì?

**Quyền kế thừa** là quyền áp dụng cho một đối tượng nhờ quan hệ của đối tượng đó với một phạm vi hoặc đối tượng khác, theo cơ chế phân quyền của nền tảng. Một tài nguyên có thể chịu tác động của quyền được gán ở cấp cha dù cấu hình trực tiếp tại tài nguyên không liệt kê lại chủ thể được cấp quyền.

Ví dụ khái niệm:

~~~text
Tổ chức
  └─ Đơn vị vận hành: nhóm Platform-Ops được gán quyền quản trị
       └─ Dự án thanh toán
            └─ Máy chủ app-pay-03
~~~

Nếu cơ chế phân quyền cho phép gán quyền tại đơn vị vận hành áp dụng xuống các tài nguyên con tương ứng, thành viên Platform-Ops có thể quản trị app-pay-03 mà không cần một bản gán quyền trực tiếp trên máy chủ.

Trong quản lý truy cập đặc quyền (PAM), chỉ xem quyền tại tài nguyên đích có thể bỏ sót những đường cấp quyền này. Hệ quả là thiếu tài khoản trong phạm vi kiểm kê, đánh giá sai least privilege, thu hồi không hết quyền hoặc không giải thích được vì sao một phiên đã thực hiện thao tác đặc quyền.

Mục tiêu của bài:

1. Phân biệt quyền trực tiếp, kế thừa và quyền thông qua quan hệ danh tính.
2. Xác định nguồn cấp quyền, phạm vi áp dụng và điều kiện truyền quyền xuống tài nguyên.
3. Thu thập bằng chứng đủ để phân loại quyền tiềm năng và quyền có hiệu lực.
4. Xử lý dữ liệu thiếu, thay đổi cây tài nguyên và khác biệt ngữ nghĩa giữa các hệ thống.
5. Dùng kết quả discovery để thu hẹp quyền, triển khai JIT/JEA và hỗ trợ kiểm toán, ứng phó sự cố.

## 2. Những quan hệ dễ bị nhầm với nhau

### 2.1. Kế thừa theo tài nguyên

Quyền được gán ở một phạm vi và có thể áp dụng cho tài nguyên nằm dưới phạm vi đó:

~~~text
Nhóm Platform-Ops
  → được gán vai trò tại Project-Pay
    → vai trò áp dụng cho VM-Pay-03 nằm trong Project-Pay
~~~

Câu hỏi chính là: **điểm gán quyền nào ở cấp cha đang tác động tới tài nguyên này?**

### 2.2. Quyền thông qua nhóm

Tài khoản nhận quyền vì là thành viên trực tiếp hoặc gián tiếp của một nhóm:

~~~text
linh.ops → Team-SRE → Platform-Ops → vai trò tại Project-Pay
~~~

Đây là đường quan hệ danh tính. Nó có thể kết hợp với kế thừa theo tài nguyên, nhưng không thay thế việc phân tích phạm vi tài nguyên.

Một đường đầy đủ có thể gồm cả hai phía:

~~~text
linh.ops
  → Team-SRE
  → Platform-Ops
  → điểm gán vai trò ở Project-Pay
  → phạm vi áp dụng xuống VM-Pay-03
~~~

Muốn giải thích quyền của linh.ops trên VM-Pay-03, phải chứng minh được cả chuỗi danh tính lẫn chuỗi phạm vi.

### 2.3. Quyền được sao chép hoặc tạo từ mẫu

Một công cụ triển khai có thể chép cùng cấu hình quyền xuống nhiều tài nguyên. Một cơ chế khác có thể tạo quyền ban đầu cho đối tượng mới dựa trên mặc định của thư mục cha.

Điều đó chưa có nghĩa các đối tượng tiếp tục nhận thay đổi từ nguồn ban đầu. Cần phân biệt:

| Cơ chế | Quan hệ với nguồn | Câu hỏi discovery |
|---|---|---|
| Kế thừa đang được nền tảng áp dụng | Quyền phụ thuộc quy tắc kế thừa hoặc phạm vi cấp cha | Nguồn nào đang có tác động tới đích? |
| Bản sao quyền trực tiếp | Quyền đã trở thành cấu hình riêng ở đích | Bản sao có còn liên kết sống với nguồn không? |
| Quyền mặc định khi tạo đối tượng | Tác động tại thời điểm tạo theo cơ chế cụ thể | Đối tượng đã tồn tại có tự nhận thay đổi sau đó không? |
| Cấu hình do công cụ đồng bộ | Công cụ cập nhật lại quyền theo lịch hoặc sự kiện | Nguồn cấu hình và lần đồng bộ nào tạo trạng thái hiện tại? |

Không kết luận có kế thừa chỉ vì hai tài nguyên có danh sách quyền giống nhau. Ngược lại, một bản ghi quyền được hiển thị tại tài nguyên có thể là biểu diễn của quyền kế thừa, không phải bản gán trực tiếp.

### 2.4. Vai trò tổng hợp và khả năng quản lý quyền

Một vai trò có thể bao gồm quyền của vai trò khác theo ngữ nghĩa nền tảng. Đây là quan hệ giữa định nghĩa vai trò, cần mở rộng riêng với quan hệ cha–con của tài nguyên.

Chủ thể có khả năng sửa chính sách cấp cha cũng có thể tạo quyền cho mình hoặc người khác. Khả năng thay đổi chính sách là một đường ảnh hưởng tới đặc quyền, nhưng không đồng nghĩa chủ thể hiện đang có mọi quyền dữ liệu của tài nguyên con.

## 3. Quyền hiệu lực không chỉ là một phép hợp đơn giản

Trong một mô hình cộng dồn đơn giản, quyền từ nhiều nguồn có thể được kết hợp. Tuy nhiên, các nền tảng còn có thể áp dụng giới hạn, điều kiện, quy tắc từ chối, ranh giới quyền hoặc cơ chế không kế thừa.

Vì vậy, không dùng công thức “quyền trực tiếp cộng quyền cha” như bộ đánh giá chung cho mọi hệ thống. Cần xác định ngữ nghĩa của từng nguồn và từng loại tài nguyên.

Một cách mô tả trung lập là:

~~~text
Quyết định cho một thao tác
  = đánh giá theo cơ chế của nền tảng đối với:
      danh tính và ngữ cảnh xác thực,
      các nguồn cấp quyền có liên quan,
      phạm vi và điều kiện áp dụng,
      các chính sách hạn chế có liên quan,
      trạng thái quyền và phiên tại thời điểm đánh giá.
~~~

Ví dụ, thêm một vai trò hẹp ở tài nguyên con không nhất thiết thay thế vai trò rộng từ cấp cha. Nếu nền tảng cộng dồn các quyền đó, chủ thể vẫn giữ phần quyền rộng đã kế thừa.

Tương tự, không mặc định rằng mọi quy tắc từ chối đều thắng mọi quy tắc cho phép, hoặc rằng một bản gán trực tiếp luôn thắng bản kế thừa. Cách ưu tiên có thể phụ thuộc loại chính sách, thứ tự đánh giá, loại đối tượng và hành động. Discovery phải lưu ngữ nghĩa áp dụng thay vì suy luận bằng tên gọi.

### 3.1. Các mức kết luận nên tách riêng

| Mức kết luận | Bằng chứng tối thiểu |
|---|---|
| Có điểm gán quyền tại cấp cha | Đọc được bản gán, chủ thể, vai trò và phạm vi nguồn |
| Có đường kế thừa tiềm năng tới đích | Có quan hệ tài nguyên và cơ chế truyền quyền phù hợp hoặc đang chờ xác minh |
| Quyền được đánh giá là cho phép | Có đánh giá cho hành động, chủ thể và ngữ cảnh xác định với các đầu vào cần thiết |
| Thao tác đã được thực hiện | Có bằng chứng hoạt động tại tài nguyên tương ứng |
| Chưa đủ dữ liệu | Có thiếu hụt về chính sách, định nghĩa vai trò, danh tính, phạm vi hoặc ngữ cảnh |

Một thao tác đã thực hiện chứng minh khả năng trong tình huống đó; nó không tự chứng minh mọi quyền khác của vai trò. Kết quả mô phỏng cũng cần được phân biệt với kết quả thực thi trong một phiên thật.

## 4. Xác định đúng cây hoặc đồ thị tài nguyên

### 4.1. Không suy quan hệ kế thừa từ tên hoặc đường dẫn hiển thị

Hai tài nguyên có cùng tiền tố tên không nhất thiết có quan hệ cha–con về phân quyền. Nhãn “production” hoặc đường dẫn trong giao diện quản lý cũng không tự chứng minh phạm vi kế thừa.

Cần lấy quan hệ quản lý từ nguồn có thẩm quyền:

- Định danh tài nguyên.
- Định danh phạm vi cha.
- Loại quan hệ và loại tài nguyên.
- Cơ chế phân quyền được áp dụng trên quan hệ đó.
- Thời điểm quan sát hoặc phiên bản cấu hình.

Khóa nên kết hợp định danh ổn định của đối tượng với nguồn quản lý. Đường dẫn có thể thay đổi khi đổi tên hoặc di chuyển; nó phù hợp để hiển thị nhưng không nên là bằng chứng định danh duy nhất.

### 4.2. Không phải quan hệ chứa nào cũng truyền quyền

Một thư mục tổ chức, nhóm tài nguyên và danh mục quản lý có thể phục vụ các mục đích khác nhau. Quan hệ “thuộc về” cần được phân biệt với quan hệ “nằm trong phạm vi áp dụng của chính sách”.

Mô hình dữ liệu nên tách:

~~~text
CONTAINS             Cấu trúc tổ chức hoặc quản lý tài nguyên.
POLICY_SCOPE_REACHES  Phạm vi chính sách có thể áp dụng tới tài nguyên.
ASSIGNED_ROLE        Chủ thể được gán vai trò tại một phạm vi.
MEMBER_OF            Quan hệ thành viên của danh tính.
CAN_MODIFY_POLICY    Khả năng thay đổi cấu hình phân quyền.
~~~

Chỉ dùng CONTAINS để suy quyền khi đã biết nền tảng coi loại cạnh đó là đường truyền quyền trong trường hợp đang xét.

### 4.3. Ranh giới giữa các hệ thống

Quyền quản lý tài nguyên ở mặt phẳng điều khiển không mặc nhiên tương đương với quyền đọc dữ liệu hoặc quyền quản trị bên trong tài nguyên. Tùy nền tảng, các lớp này có thể độc lập, liên quan một phần hoặc có những thao tác cho phép chuyển từ lớp này sang lớp khác.

Ví dụ, người có quyền quản lý cấu hình máy ảo chưa chắc đã có quyền đăng nhập hệ điều hành theo cùng cơ chế. Nếu họ có thể thay cấu hình để lấy quyền trong máy, hãy ghi nhận khả năng tác động đó riêng, với bằng chứng cụ thể.

Đối với PAM, cần biết đường cấp quyền dẫn tới loại hành động nào: quản lý hạ tầng, thao tác dữ liệu, sử dụng credential hay quản lý danh tính. Gộp tất cả thành “admin” sẽ làm mất phạm vi cần kiểm soát bằng JEA.

## 5. Những dữ liệu phải thu thập

### 5.1. Bản gán quyền và định nghĩa vai trò

Mỗi bản gán nên giữ ít nhất:

| Dữ liệu | Mục đích |
|---|---|
| Assignment ID | Phân biệt các điểm gán và truy nguồn thay đổi |
| Chủ thể được gán | Liên kết tới tài khoản, nhóm hoặc danh tính dịch vụ |
| Vai trò hoặc tập quyền | Xác định các hành động có thể được cấp |
| Phạm vi nguồn | Biết quyền bắt đầu từ đối tượng nào |
| Quy tắc áp dụng xuống dưới | Biết có truyền quyền, truyền tới loại đối tượng nào và đến đâu |
| Điều kiện | Giới hạn theo tài nguyên, thời gian, ngữ cảnh hoặc thuộc tính |
| Trạng thái và thời hạn | Phân biệt thường trực, đủ điều kiện, đang hoạt động, hết hạn |
| Nguồn và thời điểm | Đánh giá tính mới và khả năng đối chiếu bằng chứng |

Lưu tham chiếu phiên bản hoặc dấu vết nội dung định nghĩa vai trò khi có thể. Cùng một tên vai trò có thể mang tập hành động khác sau khi quản trị viên sửa định nghĩa.

Một vai trò có tên “Operator” không đủ để xác định mức đặc quyền. Cần xem các hành động như sửa chính sách, cấp danh tính, đọc secret, chạy lệnh, thay cấu hình nhạy cảm hoặc thao tác dữ liệu quan trọng theo phạm vi công việc.

### 5.2. Chính sách hạn chế và điểm ngắt kế thừa

Tùy nền tảng, cần thu thập:

- Cờ hoặc cấu hình bảo vệ đối tượng khỏi một loại kế thừa.
- Giới hạn số cấp hoặc loại đối tượng được nhận quyền.
- Quy tắc chỉ áp dụng cho con, chỉ áp dụng tại đích hoặc chỉ cho một loại tài nguyên.
- Chính sách từ chối hoặc các giới hạn liên quan.
- Điều kiện về danh tính, thiết bị, mạng, thời gian, thuộc tính tài nguyên.
- Cấu hình phân quyền riêng tại đích.

Không phải hệ thống nào cũng có các cơ chế này hoặc dùng cùng cách ưu tiên. Tên trường trong mô hình discovery chỉ nên được ánh xạ sau khi hiểu ngữ nghĩa nguồn.

Nếu không đọc được chính sách hạn chế, có thể vẫn ghi nhận đường cấp quyền đã quan sát, nhưng chưa đủ cơ sở kết luận hành động sẽ được phép.

### 5.3. Danh tính, trạng thái và đường thành viên

Với chủ thể là nhóm, cần biết tài khoản nào nằm phía sau nhóm đó. Với quyền JIT, cần biết chủ thể chỉ đủ điều kiện hay đã kích hoạt, mốc hết hạn và điều kiện đi kèm.

Việc tài khoản bị vô hiệu hóa có thể ngăn đăng nhập mới nhưng chưa chứng minh mọi phiên hoặc credential đã phát hành đều không còn sử dụng được. Giữ trạng thái danh tính và trạng thái phiên thành các dữ liệu riêng.

Tài khoản dịch vụ cần được liên kết với workload, chủ thể chịu trách nhiệm và công việc sử dụng quyền. Một tài khoản không có chủ sở hữu rõ ràng vẫn là đối tượng cần kiểm kê; không loại nó khỏi kết quả vì thiếu thông tin vận hành.

### 5.4. Tính đầy đủ và thời điểm

Một lần discovery có thể đọc cấu trúc tài nguyên lúc 09:00, quyền lúc 09:03 và thành viên nhóm lúc 09:05. Nếu có thay đổi trong khoảng đó, kết luận không nhất thiết đại diện cho một snapshot nhất quán.

Cần ghi:

~~~text
scan_id
collection_started_at
collection_finished_at
source_observation_time
source_version_or_snapshot_reference
per_scope_completeness
collection_errors_and_gaps
~~~

Nếu nguồn hỗ trợ snapshot, phiên bản hoặc cơ chế kiểm tra thay đổi, sử dụng chúng để giảm sai lệch. Nếu không, nêu rõ cửa sổ quan sát và giới hạn tính nhất quán.

## 6. Quy trình discovery từ một tài nguyên nhạy cảm

### Bước 1: Xác định đích và câu hỏi quyền

Chọn tài nguyên cụ thể cùng hành động cần đánh giá. Ví dụ:

~~~text
Đích: VM-Pay-03
Chủ thể: svc-report
Câu hỏi: có thể thực hiện thao tác quản trị máy ảo hay không?
Thời điểm/ngữ cảnh: phiên hoặc request được xác định trong cuộc rà soát.
~~~

Với kiểm kê rộng, có thể bắt đầu từ toàn bộ tài nguyên trong phạm vi được giao, nhưng đầu ra vẫn cần liên kết được về từng đích và loại quyền.

### Bước 2: Đọc quan hệ phạm vi có thẩm quyền

Đi từ tài nguyên lên các phạm vi cha liên quan đến cơ chế phân quyền. Không dừng ở một cấp cha nếu nền tảng cho phép quyền từ các cấp cao hơn tác động xuống.

Với đồ thị có nhiều loại quan hệ, chỉ mở rộng những cạnh đúng ngữ nghĩa. Nếu mô hình nguồn yêu cầu cây mà dữ liệu lại có chu trình, ghi lỗi cấu trúc hoặc dữ liệu chưa xác minh; không tiếp tục coi đó là một cây hợp lệ.

### Bước 3: Thu thập bản gán và chính sách liên quan

Đọc quyền trực tiếp tại đích và quyền ở các phạm vi cha, cùng chính sách hạn chế cần thiết. Theo dõi phân trang, lỗi truy cập, giới hạn tốc độ và dữ liệu không phân giải được.

Kết quả “không có bản gán” chỉ hợp lệ khi đã đọc đầy đủ nguồn và phạm vi tương ứng. Một phản hồi lỗi hoặc danh sách thiếu trang không phải bằng chứng quyền không tồn tại.

### Bước 4: Đánh giá đường áp dụng xuống đích

Với mỗi bản gán, kiểm tra:

1. Đích có nằm trong phạm vi mà bản gán thực sự áp dụng không?
2. Loại tài nguyên có được nhận quyền theo quy tắc đó không?
3. Có giới hạn độ sâu, điểm ngắt hoặc điều kiện truyền quyền không?
4. Quyền đang hoạt động, chỉ đủ điều kiện hay đã hết hạn?
5. Chủ thể đang xét có liên quan tới bên được gán theo bằng chứng nào?
6. Còn dữ liệu thiếu có thể làm thay đổi kết luận không?

Không bỏ qua một điểm gán chỉ vì nó nằm xa tài nguyên. Quyền ở cấp tổ chức có thể rộng hơn nhiều so với quyền trực tiếp ở máy chủ.

### Bước 5: Đánh giá quyền theo hành động và ngữ cảnh

Khi có đủ dữ liệu, sử dụng cơ chế đánh giá tương ứng với nền tảng. Giữ rõ kết quả là phân tích tĩnh, đánh giá chính sách của hệ thống hay bằng chứng thao tác thật.

Nếu chưa đủ dữ liệu, trả kết luận chưa xác định thay vì tự chọn “cho phép” hoặc “không có quyền”. Tuy nhiên, vẫn giữ các đường cấp quyền đã được chứng minh để phục vụ rà soát.

### Bước 6: Lưu nguồn gốc và khoảng trống

Một finding nên chỉ ra được:

~~~text
Ai → qua danh tính/nhóm nào → bản gán nào
   → phạm vi nguồn nào → quy tắc kế thừa nào
   → tài nguyên đích nào → tập hành động nào
   → trạng thái/điều kiện gì → dựa trên bằng chứng lúc nào
~~~

Khoảng trống phải gắn với nguồn, đối tượng và câu hỏi bị ảnh hưởng. Nhãn chung “scan failed” không đủ để người rà soát biết kết luận nào còn dùng được.

## 7. Pseudocode cho bộ thu thập

Đoạn sau minh họa việc tổ chức xử lý, không phải mã chạy hay cấu hình của một sản phẩm. Các hàm đánh giá phải được ánh xạ theo ngữ nghĩa nguồn.

~~~text
discover_inherited_access(target, subject, context):
    topology = read_authoritative_policy_ancestors(target)
    gaps = collect_topology_gaps(topology)
    candidate_paths = []
    policy_inputs = []

    scopes = unique([target] + topology.relevant_ancestors)

    for scope in scopes:
        assignments = read_all_assignments(scope)
        constraints = read_relevant_constraints(scope, target)

        preserve_evidence(assignments, constraints)
        gaps += assignments.gaps + constraints.gaps
        policy_inputs += constraints.visible_policies

        for assignment in assignments.visible_items:
            identity_match = resolve_subject_relation(
                subject, assignment.principal, context
            )

            propagation = evaluate_scope_propagation(
                assignment, topology, target
            )

            if identity_match == NO or propagation == NO:
                record_nonapplicable_reason(assignment)
                continue

            if identity_match == UNKNOWN or propagation == UNKNOWN:
                gaps += unresolved_evidence(assignment)

            role = read_role_definition(assignment.role_reference)
            gaps += role.gaps

            candidate_paths += {
                assignment,
                role,
                identity_match,
                propagation,
                source_scope: scope,
                target,
                evidence_references
            }

            policy_inputs += assignment

    assessment = platform_specific_authorization_assessment(
        subject,
        target,
        context,
        candidate_paths,
        policy_inputs,
        gaps
    )

    return {
        candidate_paths,
        assessment,
        completeness: derive_coverage(gaps),
        gaps
    }
~~~

### 7.1. Ba trạng thái trong đánh giá sơ bộ

Các hàm resolve_subject_relation và evaluate_scope_propagation nên phân biệt:

- **YES:** có bằng chứng phù hợp cho quan hệ đang xét.
- **NO:** có đủ căn cứ cho thấy quan hệ hoặc khả năng áp dụng không tồn tại trong phạm vi câu hỏi.
- **UNKNOWN:** chưa đủ dữ liệu để quyết định.

Nếu không đọc được nhóm cha hoặc cờ kế thừa, không trả NO chỉ vì chưa tìm thấy. Nếu bản gán ở một phạm vi đã xác minh không bao phủ tài nguyên, có thể loại đường đó với lý do rõ ràng.

UNKNOWN ở một nguồn không luôn làm mọi kết luận đều vô giá trị. Nó làm giảm mức chắc chắn của những câu hỏi bị ảnh hưởng. Bộ đánh giá cần biết dữ liệu thiếu có thể bổ sung quyền, hạn chế quyền hay ảnh hưởng cả hai.

### 7.2. Tái sử dụng dữ liệu mà không làm mất ngữ cảnh

Có thể cache cấu trúc tài nguyên và định nghĩa vai trò để giảm truy vấn. Khóa cache cần bao gồm nguồn, định danh và phiên bản hoặc thời hạn phù hợp.

Không dùng một tập thành viên nhóm cũ cho mọi câu hỏi thời điểm, hoặc tái sử dụng quyết định quyền của môi trường thử nghiệm cho tài nguyên sản xuất chỉ vì cùng tên vai trò.

Khi duyệt số lượng lớn tài nguyên từ gốc xuống, cần theo dõi mỗi bản gán cùng phạm vi truyền quyền của nó. Tập visited chỉ dựa trên tài nguyên có thể làm mất nguồn quyền thứ hai đi tới cùng đích nếu thuật toán chưa giữ đầy đủ trạng thái chính sách.

## 8. Ví dụ xuyên suốt: tài khoản dịch vụ nhận quyền từ cấp cha

### 8.1. Cấu trúc và các bản gán

Giả sử một nền tảng có cơ chế sau:

- Quyền tại đơn vị quản lý được áp dụng xuống các dự án và máy ảo bên dưới.
- Các bản gán trong ví dụ có hiệu lực cộng dồn.
- Không có chính sách hạn chế bổ sung trong phần dữ liệu đã xác minh của tình huống.
- Vai trò Infra-Operator trong ví dụ cho phép quản lý cấu hình máy ảo và chạy một số thao tác vận hành nhạy cảm.

Đây là giả định riêng của ví dụ, không phải quy tắc chung cho mọi nền tảng.

~~~text
Org-01
  └─ Unit-Core
       └─ Project-Pay
            └─ VM-Pay-03
~~~

Các bản gán:

| ID | Chủ thể | Vai trò | Phạm vi | Cách áp dụng |
|---|---|---|---|---|
| asg-01 | Platform-Ops | Infra-Operator | Unit-Core | Áp dụng xuống các dự án và máy ảo phù hợp |
| asg-02 | svc-report | Metrics-Reader | VM-Pay-03 | Chỉ tại đích |
| asg-03 | Emergency-Ops | Infra-Operator | Project-Pay | Chỉ đủ điều kiện kích hoạt theo quy trình |

Quan hệ danh tính đã thu thập:

~~~text
svc-report → Reporting-Services → Platform-Ops
linh.ops   → Platform-Ops
~~~

### 8.2. Vì sao chỉ đọc quyền tại đích sẽ bỏ sót?

Nếu chỉ đọc cấu hình trực tiếp ở VM-Pay-03, người kiểm kê thấy svc-report có vai trò Metrics-Reader. Từ đó có thể kết luận sai rằng tài khoản chỉ đọc số liệu.

Khi nối hai phía danh tính và tài nguyên:

~~~mermaid
flowchart LR
    S["svc-report"] --> G1["Reporting-Services"]
    G1 --> G2["Platform-Ops"]
    G2 --> A["asg-01: Infra-Operator"]
    A --> U["Unit-Core"]
    U --> P["Project-Pay"]
    P --> V["VM-Pay-03"]
    S --> D["asg-02: Metrics-Reader tại đích"]
    D --> V
~~~

Đường qua asg-01 là nguồn quyền rộng hơn. Với ngữ nghĩa cộng dồn đã giả định, asg-02 không làm giảm quyền được nhận qua asg-01.

Phát hiện này quan trọng với PAM vì svc-report có thể được vận hành như một tài khoản đọc số liệu, trong khi credential của nó lại dẫn tới năng lực quản trị hạ tầng.

### 8.3. Không gộp quyền đủ điều kiện vào quyền đang hoạt động

asg-03 cho biết Emergency-Ops có một đường kích hoạt quyền, chưa chứng minh quyền đang hoạt động. Báo cáo cần giữ điều kiện, thời hạn kích hoạt và bằng chứng trạng thái nếu muốn đánh giá quyền tại một thời điểm cụ thể.

Nếu một thành viên Emergency-Ops đã kích hoạt grant, cần liên kết grant đó với phạm vi Project-Pay và cách quyền áp dụng xuống VM-Pay-03. Nếu grant đã hết hạn nhưng phiên cũ vẫn còn, trạng thái phiên cần được xem xét riêng theo cơ chế của nền tảng.

### 8.4. Mẫu finding có truy nguồn

~~~json
{
  "finding_id": "inheritance-008-01",
  "scan_id": "scan-24",
  "subject": {
    "source": "directory-prod",
    "object_id": "svc-report-id",
    "type": "service_identity"
  },
  "target": {
    "source": "infra-control",
    "resource_id": "vm-pay-03-id"
  },
  "identity_path": [
    "svc-report-id",
    "reporting-services-id",
    "platform-ops-id"
  ],
  "source_assignment": {
    "assignment_id": "asg-01",
    "scope_id": "unit-core-id",
    "role_id": "infra-operator-id",
    "role_version": "rev-7"
  },
  "resource_path": [
    "unit-core-id",
    "project-pay-id",
    "vm-pay-03-id"
  ],
  "propagation_assessment": "CONFIRMED_FOR_RESOURCE_TYPE",
  "authorization_assessment": "STATIC_POLICY_ANALYSIS",
  "assignment_state": "ACTIVE",
  "coverage": "COMPLETE_FOR_DECLARED_SOURCES",
  "observed_window": {
    "started_at": "2026-11-26T09:00:00+07:00",
    "finished_at": "2026-11-26T09:06:00+07:00"
  }
}
~~~

Mẫu rút gọn này chưa liệt kê từng hành động và tham chiếu bằng chứng. Trong triển khai, cần bổ sung chúng để người rà soát biết chính xác kết luận nào được hỗ trợ.

COMPLETE_FOR_DECLARED_SOURCES chỉ có nghĩa đã đọc đủ các nguồn và phạm vi được công bố cho finding. Nó không bảo đảm đã kiểm kê được mọi cơ chế cấp quyền trong toàn bộ tổ chức.

### 8.5. Hướng khắc phục phù hợp

Nếu svc-report chỉ cần đọc số liệu, nhóm vận hành cần xác minh việc tài khoản thuộc Reporting-Services và nhóm này thuộc Platform-Ops có còn phục vụ mục đích nào khác.

Các hướng có thể cân nhắc sau khi kiểm kê phụ thuộc:

1. Loại đường thành viên đưa tài khoản đọc số liệu tới nhóm vận hành hạ tầng.
2. Tách nhóm theo mục đích thay vì dùng một nhóm chung cho nhiều loại quyền.
3. Chuyển điểm gán Infra-Operator xuống phạm vi nhỏ hơn nếu quyền ở Unit-Core quá rộng.
4. Dùng quyền theo tác vụ hoặc JIT/JEA cho công việc cần đặc quyền tạm thời.
5. Xác minh mọi đường cấp quyền khác trước khi kết luận đã giảm quyền.

Không xóa asg-01 ngay chỉ vì tìm thấy một tài khoản không phù hợp. Thay đổi đó có thể ảnh hưởng cả đội vận hành, các dịch vụ khác và các tài nguyên con ngoài Project-Pay.

## 9. Những tình huống đặc biệt

### 9.1. Đối tượng chặn một loại kế thừa

Một đối tượng có thể không nhận một loại quyền từ cha, trong khi vẫn nhận các giới hạn hoặc loại chính sách khác. Cần biết điểm ngắt áp dụng cho cơ chế nào.

Không dùng một cờ “inheritance disabled” trong mô hình tổng hợp để kết luận mọi quan hệ phân quyền ở cấp cha đều không còn tác dụng. Hãy lưu nguồn, loại chính sách và phạm vi của điểm ngắt.

Nếu nền tảng cho phép chuyển quyền kế thừa thành bản sao trực tiếp, sau khi tắt kế thừa tài nguyên vẫn có thể giữ các quyền đã sao chép. Discovery phải kiểm tra trạng thái sau chuyển đổi, không chỉ cờ kế thừa.

### 9.2. Quyền chỉ dành cho đối tượng con hoặc loại đối tượng cụ thể

Một bản gán có thể không áp dụng cho chính đối tượng nguồn nhưng áp dụng cho con. Một bản gán khác chỉ áp dụng cho thư mục, máy ảo hoặc một loại đối tượng cụ thể.

Báo cáo cần ghi phạm vi đó. Nếu chỉ lưu nguồn và đích mà bỏ quy tắc loại đối tượng, thuật toán có thể tạo finding sai cho những tài nguyên nằm trong cùng cây nhưng không thuộc loại được cấp quyền.

Các tên cờ và cách truyền qua nhiều cấp phải được lấy theo cơ chế của hệ thống. Không tái sử dụng trực tiếp logic ACL của hệ thống này cho chính sách IAM của hệ thống khác.

### 9.3. Di chuyển hoặc tái cấu trúc tài nguyên

Di chuyển tài nguyên sang phạm vi cha khác có thể làm thay đổi các nguồn quyền áp dụng. Tuy vậy, mức độ thay đổi và cách quyền cũ được giữ hoặc loại bỏ phụ thuộc nền tảng.

Discovery cần đối chiếu:

- Quan hệ cha trước và sau.
- Bản gán tại phạm vi nguồn và phạm vi mới.
- Quyền trực tiếp còn tồn tại ở đích.
- Quy tắc chuyển đổi hoặc sao chép nếu có.
- Các phiên, token và cache có thể còn mang trạng thái trước thay đổi.

Đổi đường dẫn hiển thị không đủ để chứng minh quyền đã thay đổi. Ngược lại, thay đổi phạm vi chính sách có thể tác động tới nhiều tài nguyên dù tên hiển thị của chúng không đổi.

### 9.4. Tài nguyên mới xuất hiện dưới phạm vi có quyền rộng

Một nhóm được gán quyền tại cấp cha có thể tự nhận khả năng truy cập tài nguyên con được tạo trong tương lai nếu cơ chế kế thừa áp dụng.

Vì vậy, phạm vi ảnh hưởng không chỉ là danh sách tài nguyên đang có. Cần ghi khả năng mở rộng theo cấu trúc và rà soát việc tạo tài nguyên mới trong những phạm vi đó.

Tuy nhiên, không khẳng định mọi tài nguyên mới đều nhận quyền nếu còn phụ thuộc loại đối tượng, điều kiện hoặc cơ chế tạo. Đánh giá theo từng mẫu tài nguyên và quy tắc áp dụng.

### 9.5. Điều kiện dựa trên thuộc tính thay đổi

Một quyền có thể chỉ áp dụng khi tài nguyên mang nhãn hoặc thuộc tính phù hợp. Nếu thiếu thuộc tính tại thời điểm quan sát, không thể tự đánh giá điều kiện là đúng.

Quyền sửa thuộc tính có thể ảnh hưởng tới việc điều kiện được thỏa mãn trong tương lai. Lưu khả năng đó như một đường tác động riêng, không biến nó thành bằng chứng rằng quyền đã có hiệu lực.

### 9.6. Credential, vault và quyền kế thừa

Nhóm có thể nhận quyền sử dụng secret hoặc quản lý vùng lưu trữ thông qua phạm vi cha của vault. Việc discovery cần xác định đó là quyền xem metadata, sử dụng credential, đọc giá trị secret hay thay đổi chính sách.

Không đọc hoặc xuất secret chỉ để chứng minh rằng có quyền kế thừa. Có thể dùng metadata phân quyền, cơ chế đánh giá phù hợp và bằng chứng hoạt động đã được bảo vệ.

Nếu quyền kế thừa cho phép sử dụng credential của một tài khoản quản trị, tác động có thể vượt khỏi chính vault. Cần liên kết tài khoản đó tới tài nguyên và phiên liên quan, đồng thời giữ riêng đường quyền trên vault và đường quyền của tài khoản tại đích.

## 10. Từ discovery tới kiểm soát PAM

### 10.1. Xác định đúng phạm vi onboarding

Một tài khoản không xuất hiện trong danh sách quản trị trực tiếp vẫn có thể là tài khoản đặc quyền qua kế thừa. Phạm vi onboarding PAM cần dựa trên khả năng và đường quyền thực tế, không chỉ tên tài khoản hoặc nơi nó được gán vai trò.

Đối với tài khoản dịch vụ, discovery phải liên kết quyền với nơi sử dụng credential và công việc phụ thuộc. Đưa credential vào vault hoặc thay đổi chu kỳ rotation cần kế hoạch cập nhật ứng dụng và xác nhận vận hành; finding kế thừa là đầu vào để lập kế hoạch đó.

### 10.2. Least privilege phải xét mọi nguồn quyền

Một vai trò hẹp tại đích không bảo đảm least privilege nếu quyền rộng ở cấp cha vẫn áp dụng. Trước khi điều chỉnh, cần lập danh sách các nguồn cấp quyền liên quan và những hành động thực tế cần giữ.

Không nhất thiết xóa mọi quyền cấp cha. Một quyền đọc chung ở cấp cha có thể có mục đích rõ ràng, trong khi quyền sửa nhạy cảm được cấp hẹp hơn. Mục tiêu là tập quyền phù hợp công việc và có thể giải thích được.

### 10.3. JIT/JEA cần loại quyền thường trực đi vòng

Nếu một tài khoản được cấp quyền JIT cho một phiên nhưng vẫn có đường quản trị thường trực từ cấp tổ chức, việc grant JIT hết hạn chưa loại quyền quản trị nền.

Cần kiểm tra:

~~~text
Grant tạm đã hết hạn?
Đường kế thừa thường trực có còn không?
Còn quyền qua nhóm, vai trò khác hoặc credential khác không?
Phiên đang hoạt động có còn sử dụng quyền cũ không?
~~~

JIT giới hạn thời gian của một nguồn quyền. JEA giới hạn thao tác và tài nguyên của nguồn đó. Discovery quyền kế thừa giúp nhận ra các nguồn khác có thể làm mất ý nghĩa của hai giới hạn này.

### 10.4. Giám sát thay đổi tại cấp cha

Một thay đổi ở cấp cha có thể tác động tới nhiều tài nguyên con. Theo dõi việc thêm bản gán, mở rộng định nghĩa vai trò, sửa điều kiện hoặc thay cấu trúc tài nguyên giúp phát hiện thay đổi đặc quyền sớm hơn việc chỉ xem các đối tượng đích.

Khi có sự kiện thay đổi, cần tính lại tác động trên phần đồ thị liên quan. Nếu luồng sự kiện bị gián đoạn, giữ trạng thái chưa đối soát và thực hiện đồng bộ lại theo cơ chế của nguồn.

## 11. Bằng chứng cho kiểm toán và ứng phó sự cố

### 11.1. Một finding cần kể được toàn bộ đường quyền

Bộ bằng chứng nên trả lời được:

| Câu hỏi | Bằng chứng cần giữ |
|---|---|
| Ai có đường tới quyền? | Định danh chủ thể và quan hệ nhóm hoặc ủy quyền liên quan |
| Quyền bắt nguồn ở đâu? | Assignment ID, phạm vi nguồn và chủ thể được gán |
| Vì sao tới được đích? | Quan hệ phạm vi và quy tắc áp dụng xuống đích |
| Được làm gì? | Định nghĩa vai trò, hành động và phạm vi đối tượng |
| Có giới hạn gì? | Điều kiện, điểm ngắt, chính sách hạn chế và trạng thái grant |
| Kết luận ở thời điểm nào? | Thời điểm quan sát, phiên bản và cửa sổ thu thập |
| Đã sử dụng quyền chưa? | Log thao tác hoặc phiên được liên kết đáng tin cậy |
| Còn điều gì chưa biết? | Nguồn chưa đọc đủ, lỗi phân giải và tác động tới kết luận |

Không lưu credential, private key hoặc giá trị secret trong bản ghi discovery. Cấu trúc quyền cũng là thông tin nhạy cảm; kho bằng chứng cần kiểm soát người xem, thay đổi và xuất dữ liệu.

### 11.2. Khi một tài khoản bị nghi xâm phạm

Để đánh giá phạm vi ảnh hưởng, cần truy từ tài khoản tới các nhóm, bản gán và phạm vi cấp cha liên quan, rồi xác định các tài nguyên con mà quyền có thể áp dụng.

Tách ba lớp kết luận:

1. **Có khả năng tiếp cận:** đường quyền phù hợp trong dữ liệu đã thu thập.
2. **Được đánh giá là có quyền:** quyết định theo hành động và ngữ cảnh xác định.
3. **Đã có hoạt động:** bằng chứng thao tác hoặc phiên tại tài nguyên.

Không suy ra rằng mọi tài nguyên có thể truy cập đều đã bị tác động. Ngược lại, thiếu log không đủ để khẳng định tài nguyên không bị tác động nếu khả năng ghi nhận hoặc lưu trữ chưa đầy đủ.

Sau thu hồi, cần xác định những nguồn quyền thay thế, credential còn dùng được và phiên đang hoạt động. Xóa một bản gán không tự hoàn tác thao tác đã thực hiện hoặc thay đổi bền vững do tài khoản tạo ra.

## 12. Xác minh sau khi giảm hoặc thu hồi quyền

Thực hiện thay đổi theo phạm vi đã được đánh giá, rồi kiểm tra cả cấu hình và trạng thái vận hành:

1. Xác nhận bản gán, quan hệ nhóm hoặc quy tắc kế thừa đã thay đổi tại nguồn có thẩm quyền.
2. Thu thập lại những phạm vi cha và tài nguyên bị ảnh hưởng.
3. Đối chiếu các đường khác dẫn tới cùng hành động.
4. Xác định tài nguyên đã nhận trạng thái mới theo cơ chế của nền tảng.
5. Xử lý phiên, token, credential hoặc cache quyền còn liên quan.
6. Kiểm tra công việc hợp lệ vẫn hoạt động trong phạm vi mới.
7. Lưu bằng chứng và các ngoại lệ còn tồn tại.

Một request bị lỗi do mạng không chứng minh đã thu hồi quyền. Một request bị từ chối trong một ngữ cảnh cũng không tự chứng minh mọi đường cấp quyền khác đã biến mất.

Ngược lại, việc không còn nhìn thấy bản gán trong một lần quét lỗi không phải bằng chứng nó đã bị xóa. Cần phân biệt “đã xác nhận kết thúc” với “chưa quan sát lại được”.

Nếu không thể hoàn tất việc dọn quyền hoặc kết thúc phiên, giữ trạng thái xử lý chưa hoàn tất cùng người chịu trách nhiệm. Không đóng finding chỉ vì thao tác xóa cấu hình đã trả về thành công.

## 13. Chất lượng dữ liệu và chỉ số vận hành

Một chương trình discovery cần theo dõi cả độ bao phủ và khả năng giải thích, thay vì chỉ đếm số tài khoản đặc quyền.

| Chỉ số | Ý nghĩa và giới hạn |
|---|---|
| Tỷ lệ tài nguyên có đủ chuỗi phạm vi liên quan | Cho biết đã nhìn thấy cấu trúc cần đánh giá tới đâu |
| Tỷ lệ phạm vi đọc đủ bản gán và chính sách | Phản ánh chất lượng thu thập, không chỉ số request thành công |
| Số đường kế thừa chưa phân giải | Làm rõ các khoảng trống cần xử lý |
| Số tài khoản có quyền từ nhiều nguồn | Hỗ trợ rà soát quyền thừa và thu hồi |
| Độ mới theo nguồn | Cho biết dữ liệu phản ánh trạng thái cách đây bao lâu |
| Thời gian phát hiện thay đổi ở cấp cha | Đánh giá khả năng nhận biết mở rộng phạm vi đặc quyền |
| Tỷ lệ finding có bằng chứng từng bước | Đánh giá khả năng kiểm toán và tái hiện kết luận |

Mẫu số phải được công bố. Nếu mới biết một phần tài nguyên hoặc một số hệ thống phân quyền, tỷ lệ hoàn tất trong phần đó không đại diện cho toàn bộ hạ tầng.

Với nguồn chưa đọc được, lưu lỗi và ảnh hưởng tới kết luận. Không làm đẹp tỷ lệ bao phủ bằng cách loại nguồn khó thu thập khỏi danh sách mà không công bố.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ đọc quyền ở đích | Bỏ sót quyền từ các phạm vi cha | Thu thập chuỗi phạm vi liên quan theo cơ chế nguồn |
| Xem mọi quan hệ chứa là đường truyền quyền | Tạo đường quyền không tồn tại | Phân biệt cấu trúc quản lý và ngữ nghĩa áp dụng chính sách |
| Mặc định quyền con thay quyền cha | Bỏ sót quyền cộng dồn | Đánh giá quy tắc kết hợp thực tế |
| Dùng một quy tắc ưu tiên deny cho mọi hệ thống | Đánh giá sai quyền hiệu lực | Ánh xạ bộ đánh giá theo loại chính sách và nền tảng |
| Gộp bản sao với quyền kế thừa sống | Sửa nguồn nhưng quyền ở đích vẫn còn | Theo dõi nguồn gốc và trạng thái liên kết |
| Chỉ lưu tên vai trò | Không biết hành động thật hoặc thay đổi định nghĩa | Lưu tham chiếu và phiên bản định nghĩa |
| Coi không đọc được là không có quyền | Đưa ra kết luận an toàn sai | Giữ trạng thái chưa xác định và khoảng trống |
| Chỉ kết thúc grant JIT | Quyền thường trực hoặc phiên cũ vẫn tồn tại | Đối chiếu toàn bộ nguồn quyền và trạng thái phiên |
| Xóa quyền rộng ở cha mà chưa đánh giá ảnh hưởng | Gián đoạn nhiều tài nguyên và dịch vụ | Liệt kê chủ thể, phạm vi và phụ thuộc trước thay đổi |
| Đồng nhất quyền quản lý hạ tầng với quyền dữ liệu | Báo quá mức hoặc bỏ sót đường tác động | Tách loại hành động và lớp phân quyền |

## 15. Bài tập áp dụng

Giả sử môi trường có cấu trúc:

~~~text
Org-A
  └─ Folder-Prod
       ├─ Project-Pay
       │    └─ Database-Pay
       └─ Project-Logs
            └─ Storage-Logs
~~~

Các giả định của bài tập:

- Nhóm Shared-Ops được gán quyền quản lý hạ tầng tại Folder-Prod và quyền này áp dụng xuống các dự án tương ứng.
- svc-logs là thành viên Shared-Ops.
- svc-logs được gán trực tiếp quyền chỉ đọc tại Storage-Logs.
- Có một chính sách hạn chế tại Project-Pay nhưng lần thu thập hiện tại chưa đọc được nội dung.
- Chưa có dữ liệu về phiên hoặc token đã phát hành.

Hãy trả lời:

1. Nguồn quyền nào bị bỏ sót nếu chỉ đọc cấu hình của Storage-Logs?
2. Bản gán chỉ đọc tại Storage-Logs có tự làm mất quyền rộng hơn không?
3. Có thể kết luận svc-logs được quản lý mọi đối tượng trong Project-Pay chưa?
4. Cần thêm bằng chứng gì để đánh giá quyền với một hành động cụ thể?
5. Sau khi xóa svc-logs khỏi Shared-Ops, cần xác minh những gì?
6. Nếu svc-logs chỉ phục vụ thu thập log, hướng thiết kế least privilege nào phù hợp?

Hướng phân tích:

- Cần xem bản gán tại Folder-Prod và đường thành viên dẫn tới Shared-Ops.
- Tác động của bản gán chỉ đọc phụ thuộc quy tắc kết hợp; không tự coi nó là giới hạn thay thế.
- Chính sách hạn chế chưa đọc được khiến kết luận ở Project-Pay chưa đầy đủ.
- Quyền quản lý hạ tầng chưa tự chứng minh quyền đọc dữ liệu của Database-Pay.
- Thu hồi quan hệ nhóm cần đi kèm kiểm tra nguồn quyền khác và trạng thái phiên, credential liên quan.
- Quyền của svc-logs nên gắn với phạm vi và thao tác thực sự cần cho thu thập log; nếu có công việc quản trị tạm thời, xem xét grant riêng theo JIT/JEA.

## 16. Ghi nhớ

Phát hiện quyền kế thừa là truy nguồn tác động của các điểm gán quyền tới tài nguyên đích theo đúng cơ chế phân quyền. Cần nối được danh tính, bản gán, phạm vi nguồn, đường áp dụng, hành động và điều kiện tại thời điểm đánh giá.

Trong PAM, một kết luận có giá trị phải giải thích được quyền đến từ đâu, còn đường thay thế nào và điều gì chưa được xác minh. Từ đó mới có thể kiểm kê đúng tài khoản đặc quyền, thu hẹp phạm vi, triển khai JIT/JEA và chứng minh việc thu hồi bằng bằng chứng tại các hệ thống liên quan.
