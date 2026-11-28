# Phát hiện nested group trong kiểm kê quyền đặc quyền

## 1. Nested group là gì và vì sao PAM cần phát hiện?

**Nested group** là quan hệ trong đó một nhóm là thành viên của nhóm khác. Khi nền tảng phân quyền áp dụng quan hệ thành viên bắc cầu, tài khoản nằm trong nhóm con có thể nhận quyền thông qua một hoặc nhiều nhóm cha mà không xuất hiện trong danh sách thành viên trực tiếp của nhóm được cấp quyền.

Trong quản lý truy cập đặc quyền (PAM), chỉ kiểm kê tài khoản được gán vai trò quản trị trực tiếp sẽ bỏ sót các đường cấp quyền này. Một tài khoản người dùng, tài khoản dịch vụ hoặc nhóm do đội ứng dụng quản lý có thể dẫn tới quyền quản trị hạ tầng nhạy cảm qua nhiều lớp nhóm.

Ví dụ minh họa:

~~~text
svc-deploy
  └─ là thành viên của Release-Automation
       └─ là thành viên của Production-Ops
            └─ được gán vai trò quản trị trên cụm app-prod
~~~

Nếu môi trường thực sự hỗ trợ và áp dụng sự lồng nhóm trên đường cấp quyền này, tài khoản dịch vụ có thể nhận năng lực quản trị trên cụm sản xuất. Việc chỉ đọc thành viên trực tiếp của Production-Ops sẽ thấy Release-Automation, nhưng chưa trả lời đầy đủ những tài khoản nào nằm phía sau nhóm đó.

Mục tiêu của bài:

1. Mô hình hóa quan hệ nhóm và điểm gán quyền thành đồ thị có hướng.
2. Tìm thành viên bắc cầu mà vẫn giữ bằng chứng về đường dẫn.
3. Xử lý chu trình, nhiều đường dẫn, ranh giới nguồn danh tính và kết quả thu thập chưa đầy đủ.
4. Phân biệt quan hệ thành viên với quyền có hiệu lực tại tài nguyên.
5. Dùng kết quả discovery để hỗ trợ least privilege, JIT/JEA, quản lý credential và điều tra sự cố.

## 2. Ba câu hỏi khác nhau trong discovery

### 2.1. Ai là thành viên trực tiếp?

Quan hệ trực tiếp là thông tin do nguồn danh tính hoặc hệ thống đích xác nhận tại thời điểm thu thập:

~~~text
an.ops → Team-Operations
Team-Operations → Server-Maintainers
~~~

Quy ước trong bài: mũi tên đi từ **thành viên đến nhóm chứa thành viên**. Với quy ước này, đường đi từ một tài khoản tới nhóm được cấp quyền biểu thị một chuỗi thành viên có thể cần đánh giá.

### 2.2. Ai là thành viên bắc cầu?

Nếu nguồn hỗ trợ quan hệ bắc cầu tương ứng:

~~~text
an.ops → Team-Operations → Server-Maintainers
~~~

thì an.ops là thành viên gián tiếp của Server-Maintainers. Độ sâu đường dẫn trong bài là số cạnh thành viên: tài khoản trực tiếp có độ sâu 1; ví dụ trên có độ sâu 2.

Độ sâu là dữ liệu phục vụ giải thích và phân tích. Một đường dẫn chỉ có một cạnh vẫn có thể mang quyền rất rộng; nhiều cạnh không tự chứng minh rủi ro cao hơn nếu chưa xét tài nguyên và hành động được cấp.

### 2.3. Quyền nào thực sự được thực thi?

Ngay cả khi quan hệ thành viên đã được xác nhận, quyền thực tế còn phụ thuộc vào:

- Loại nhóm và việc nền tảng có chấp nhận lồng nhóm trong ngữ cảnh đó hay không.
- Điểm gán vai trò hoặc quyền, phạm vi tài nguyên và điều kiện đi kèm.
- Trạng thái kích hoạt quyền, thời hạn hoặc điều kiện JIT/JEA.
- Cách tài nguyên xác thực, ánh xạ danh tính và đánh giá quyền.
- Chính sách hạn chế, phiên đăng nhập, token hoặc cache quyền đang được sử dụng.

Vì vậy, cần ghi **đường dẫn có khả năng dẫn tới đặc quyền** khi mới có bằng chứng thành viên và điểm gán quyền. Chỉ khẳng định quyền hiệu lực khi có thêm bằng chứng đánh giá quyền phù hợp với tài nguyên, thời điểm và ngữ cảnh.

## 3. Chọn đúng điểm bắt đầu

Discovery nested group trong PAM thường bắt đầu từ các **điểm gán quyền đặc quyền** đã được xác định, rồi mở rộng xuống các nhóm thành viên.

Điểm bắt đầu có thể là:

| Điểm gán quyền | Ví dụ phạm vi cần ghi nhận |
|---|---|
| Nhóm được gán quyền quản trị máy chủ | Máy chủ cụ thể hoặc tập máy được quản lý |
| Nhóm được ánh xạ vào vai trò cơ sở dữ liệu | Instance, database hoặc tập đối tượng |
| Nhóm được gán vai trò quản trị nền tảng | Tài khoản, project, namespace hoặc cụm |
| Nhóm được phép sử dụng công cụ vận hành | Tập thao tác, endpoint hoặc hệ thống đích |
| Nhóm có quyền quản lý credential trong vault | Vùng lưu trữ, secret hoặc loại hành động |

Không nên kết luận một nhóm là đặc quyền chỉ vì tên có chữ Admin hoặc Ops. Cần có bằng chứng về quyền hoặc vai trò được gán. Tên nhóm hỗ trợ tìm ứng viên; cấu hình gán quyền mới giúp giải thích ảnh hưởng.

Ví dụ, cùng một nhóm Server-Maintainers có thể được gán quyền đọc ở môi trường thử nghiệm và quyền quản trị ở sản xuất. Báo cáo phải giữ từng điểm gán quyền và phạm vi riêng, thay vì gộp thành một nhãn “admin”.

### 3.1. Hai hướng truy vấn bổ sung nhau

- **Từ quyền về chủ thể:** bắt đầu ở nhóm được cấp quyền, truy ra các nhóm con và tài khoản thành viên. Phù hợp để kiểm kê ai có đường dẫn tới một phạm vi đặc quyền.
- **Từ chủ thể về quyền:** bắt đầu ở tài khoản cần điều tra, truy lên các nhóm cha rồi đối chiếu các điểm gán quyền. Phù hợp khi xác minh một tài khoản bị nghi lộ credential.

Cả hai hướng đều cần đúng chiều cạnh và phạm vi nguồn dữ liệu. Một thuộc tính liệt kê nhóm cha trên tài khoản có thể chưa bao gồm toàn bộ thành viên bắc cầu, nhóm cục bộ, quan hệ ở nguồn khác hoặc các cơ chế thành viên đặc biệt của nền tảng.

## 4. Mô hình dữ liệu: giữ danh tính, cạnh và bằng chứng

### 4.1. Nút danh tính

Mỗi nút nên có khóa ổn định do nguồn cấp, kèm định danh nguồn hoặc miền quản lý:

~~~text
principal_key = source_namespace + immutable_object_id
~~~

Các loại nút thường gặp:

- Tài khoản người dùng.
- Tài khoản dịch vụ hoặc danh tính workload.
- Nhóm.
- Chủ thể bên ngoài chưa phân giải được.
- Danh tính cục bộ tại tài nguyên.

Không gộp hai nút chỉ vì trùng tên hiển thị hoặc địa chỉ dễ thay đổi. Hai miền có thể cùng có nhóm Production-Ops nhưng là hai đối tượng độc lập. Đối tượng bị xóa rồi tạo lại cùng tên cũng có thể mang định danh khác.

Không sao chép mọi thuộc tính vào kho discovery nếu không cần. Ưu tiên định danh, loại đối tượng, trạng thái, chủ thể sở hữu và thông tin phục vụ liên kết bằng chứng.

### 4.2. Cạnh có kiểu rõ ràng

| Kiểu cạnh | Ý nghĩa | Có dùng như cạnh thành viên khi tính bắc cầu? |
|---|---|---|
| MEMBER_OF | Một chủ thể là thành viên của nhóm | Có, nếu ngữ nghĩa nguồn cho phép |
| ASSIGNED_ROLE | Nhóm hoặc chủ thể được gán vai trò tại phạm vi | Là điểm nối sang quyền, không phải quan hệ nhóm |
| CAN_MODIFY_MEMBERS | Chủ thể có khả năng sửa thành viên nhóm | Phân tích riêng về khả năng tác động |
| OWNS | Chủ thể được ghi nhận là chủ sở hữu | Chỉ suy ra quyền nếu có bằng chứng quyền tương ứng |
| ELIGIBLE_FOR | Chủ thể đủ điều kiện kích hoạt một quyền | Không tự coi là thành viên hoặc quyền đang hoạt động |

Không dùng cạnh “là chủ sở hữu” như thể đó là cạnh “là thành viên”. Tương tự, quyền thêm thành viên nhóm biểu thị khả năng thay đổi đường cấp quyền trong tương lai; nó không chứng minh chủ thể đã là thành viên.

### 4.3. Bằng chứng của từng cạnh

Một cạnh thành viên nên đi kèm:

- Định danh thành viên và nhóm chứa thành viên.
- Nguồn thu thập, định danh lần quét và thời điểm quan sát.
- Loại quan hệ: trực tiếp, được nguồn trả về là bắc cầu hoặc được thuật toán suy ra.
- Trạng thái quan hệ và thời hạn nếu nguồn cung cấp.
- Tham chiếu bản ghi hoặc phản hồi đã được bảo vệ để đối chiếu.
- Dấu hiệu dữ liệu thiếu, mâu thuẫn hoặc chưa phân giải.

Không gắn nhãn một quan hệ suy ra là “trực tiếp”. Nếu API chỉ trả danh sách thành viên bắc cầu mà không trả từng cạnh trung gian, có thể biết một tài khoản thuộc tập thành viên mở rộng nhưng chưa đủ bằng chứng để dựng đúng chuỗi nhóm dẫn tới tài khoản đó.

## 5. Thu thập dữ liệu trước khi mở rộng đồ thị

### 5.1. Thu thập từng trang và đánh dấu mức độ đầy đủ

Với mỗi nhóm, cần lấy đủ các trang thành viên mà nguồn cho phép đọc. Nếu một trang lỗi, hết thời gian, bị giới hạn tốc độ hoặc không đủ quyền xem, trạng thái của nhóm là chưa đầy đủ.

Phân biệt ít nhất bốn kết quả:

~~~text
COMPLETE_EMPTY       Đã đọc đầy đủ, nhóm không có thành viên tại lần quan sát.
COMPLETE_NONEMPTY    Đã đọc đầy đủ và có thành viên.
PARTIAL             Chỉ đọc được một phần dữ liệu.
UNRESOLVED          Chưa xác định được đối tượng hoặc chưa đọc được nguồn.
~~~

Không chuyển lỗi truy cập thành danh sách rỗng. “Không thấy thành viên” và “đã xác minh không có thành viên” là hai kết luận khác nhau.

Nguồn có thể không cung cấp một snapshot nhất quán cho cả quá trình phân trang. Nếu nhóm thay đổi giữa lúc đọc trang đầu và trang cuối, kết quả có thể thiếu hoặc lặp bản ghi. Khi có cơ chế snapshot hoặc phiên bản dữ liệu, nên lưu tham chiếu đó. Nếu không có, ghi cửa sổ thời gian thu thập và giới hạn nhất quán.

### 5.2. Chuẩn hóa mà không làm mất ngữ nghĩa

Trước khi duyệt:

1. Chuẩn hóa định danh theo từng nguồn, giữ nguyên ranh giới quản lý.
2. Phân loại người dùng, nhóm, tài khoản dịch vụ và đối tượng bên ngoài.
3. Loại cạnh trùng theo định danh và kiểu quan hệ, nhưng giữ các tham chiếu bằng chứng cần thiết.
4. Gắn trạng thái đầy đủ cho kết quả đọc từng nhóm.
5. Đối chiếu việc nguồn có hỗ trợ lồng nhóm và bắc cầu trong ngữ cảnh đang xét.

Không biến chuỗi ký tự giống tên nhóm thành một nút nhóm đã xác thực. Nếu chưa phân giải được loại đối tượng hoặc nguồn quản lý, giữ nó ở trạng thái chưa phân giải.

### 5.3. Thu thập với quyền phù hợp

Tài khoản discovery cần đủ quyền đọc các quan hệ và điểm gán quyền trong phạm vi đã thống nhất. Không mặc nhiên cấp quyền quản trị chỉ để tiện kiểm kê.

Discovery nested group thông thường không cần đọc mật khẩu hay private key của các tài khoản thành viên. Nếu connector cần credential, quản lý credential đó qua cơ chế phù hợp và tránh đưa chúng vào log hay bản ghi đồ thị.

Với hệ thống nhạy cảm, giới hạn tốc độ và số truy vấn đồng thời để việc kiểm kê không làm ảnh hưởng dịch vụ. Kết quả bị giới hạn vì ngân sách truy vấn phải được ghi là chưa đầy đủ.

## 6. Thuật toán tìm thành viên bắc cầu

### 6.1. Duyệt từ nhóm đặc quyền về các thành viên

Từ một điểm gán quyền, thuật toán duyệt xuống nhóm chứa thành viên. Đây là chiều ngược với mũi tên MEMBER_OF trong mô hình của bài.

Ví dụ:

~~~text
Cạnh lưu trong đồ thị:
  an.ops → Team-Operations → Server-Maintainers

Hướng thu thập từ nhóm được cấp quyền:
  Server-Maintainers
    → đọc thành viên trực tiếp Team-Operations
      → đọc thành viên trực tiếp an.ops
~~~

Có thể dùng BFS để tìm một đường dẫn đại diện có ít cạnh nhất theo số quan hệ thành viên trong đồ thị đã thu thập. Dùng DFS cũng có thể tìm các chủ thể tới được; lựa chọn thuật toán không thay thế việc kiểm tra ngữ nghĩa quyền.

Pseudocode sau minh họa BFS cho **một điểm gán quyền**. Đây là mô hình thuật toán, không phải chương trình hay cấu hình của một sản phẩm:

~~~text
discover(binding):
    root = binding.principal_group
    queue = [(root, [root], 0)]
    scheduled_groups = {root}
    evidence_edges = {}
    principal_findings = {}
    gaps = []

    while queue is not empty:
        group, path_to_root, depth = queue.pop_front()

        if depth >= configured_group_expansion_limit:
            gaps.add(group, "DEPTH_LIMIT")
            continue

        result = read_all_direct_members(group)
        preserve_source_evidence(result)

        if result.completeness is not COMPLETE:
            gaps.add(group, result.failure_or_partial_reason)

        for member in result.visible_members:
            edge = MEMBER_OF(member, group)
            evidence_edges.add(edge, result.evidence_reference)
            candidate_path = [member] + path_to_root
            record_observed_path(member, binding, candidate_path)

            if member.kind == GROUP:
                if not nesting_semantics_resolved(member, group, binding):
                    gaps.add(member, "NESTING_SEMANTICS_UNRESOLVED")
                    continue

                if member not in scheduled_groups:
                    scheduled_groups.add(member)
                    queue.push_back(
                        member, candidate_path, depth + 1
                    )

            else if member.kind in {USER, SERVICE_IDENTITY}:
                principal_findings.add(member, binding, candidate_path)

            else:
                gaps.add(member, "UNRESOLVED_PRINCIPAL")

    return principal_findings, evidence_edges, gaps
~~~

Các điểm cần giữ khi triển khai:

- Luôn lưu cạnh quan sát được trước khi bỏ qua một nhóm đã duyệt. Nếu không, có thể làm mất đường dẫn thay thế.
- Một nút nằm trong scheduled_groups chỉ có nghĩa đã được đưa vào lịch xử lý; không có nghĩa đã đọc đầy đủ.
- Lỗi thu thập phải nằm trong gaps và có trạng thái để thử lại phù hợp.
- Với nhiều điểm gán quyền, phải giữ liên kết kết quả tới từng binding. Có thể tái sử dụng dữ liệu thành viên đã đọc, nhưng không đánh mất phạm vi, điều kiện và gốc quyền riêng.
- Khi đạt giới hạn độ sâu, không báo hoàn tất nếu còn nhóm chưa mở rộng.

BFS trên đồ thị đầy đủ có thể tìm đường ít cạnh nhất. Với dữ liệu thiếu hoặc bị giới hạn, chỉ nên gọi đó là đường đại diện ngắn nhất **trong phần đồ thị đã quan sát**.

### 6.2. Chi phí và giới hạn thực tế

Với một đồ thị đã có trong bộ nhớ, phép duyệt cơ bản có chi phí xấp xỉ O(V + E), trong đó V là số nút và E là số cạnh được duyệt. Chi phí thực tế còn phụ thuộc vào số trang API, độ trễ mạng, số điểm gán quyền và cách lưu đường dẫn.

Liệt kê mọi đường dẫn có thể tốn nhiều tài nguyên, đặc biệt khi có nhiều nhánh hội tụ hoặc chu trình. Một chiến lược thực dụng là:

1. Lưu đầy đủ cạnh đã quan sát và bằng chứng.
2. Trả một đường đại diện cho mỗi chủ thể và điểm gán quyền.
3. Cho phép truy vấn thêm các đường khác khi cần điều tra.
4. Ghi rõ giới hạn số đường hoặc giới hạn độ dài trong kết quả.

Một đường đại diện đủ để chứng minh tồn tại một chuỗi quan hệ đã quan sát. Nó chưa đủ để chứng minh rằng xóa một cạnh trên đường đó sẽ loại bỏ mọi đường cấp quyền.

## 7. Chu trình và nhiều đường dẫn

### 7.1. Chu trình không đồng nghĩa với một nút đã được thăm

Ví dụ nhiều nhánh hội tụ nhưng không có chu trình:

~~~text
an.ops → Team-A → Root-Admins
an.ops → Team-B → Root-Admins
~~~

an.ops xuất hiện hai lần qua các nhánh khác nhau. Đây không phải bằng chứng có vòng lặp.

Ví dụ một chu trình trong dữ liệu nhóm:

~~~text
Group-A → Group-B
Group-B → Group-C
Group-C → Group-A
~~~

Không phải nền tảng nào cũng cho phép tạo chu trình. Tuy vậy, bộ thu thập nên xử lý được dữ liệu có vòng lặp, dữ liệu nhập sai hoặc dữ liệu tổng hợp từ nhiều nguồn.

Tập visited hoặc scheduled giúp tránh lặp vô hạn, nhưng không đủ để phân loại chu trình. Muốn phát hiện chu trình, có thể dùng DFS với tập nút đang nằm trên nhánh duyệt, hoặc tìm các thành phần liên thông mạnh trên đồ thị nhóm đã thu thập. Chỉ một cạnh trỏ tới nút đang có trong nhánh DFS hiện tại mới cho bằng chứng vòng lặp theo cách kiểm tra đó.

Nếu đồ thị chưa đầy đủ, “chưa phát hiện chu trình” không đồng nghĩa với “không có chu trình trong nguồn”.

### 7.2. Nhiều đường dẫn khiến việc thu hồi dễ bị thiếu

Giả sử:

~~~text
svc-backup → Backup-Team → Production-Admins
svc-backup → Legacy-Ops  → Production-Admins
~~~

Xóa svc-backup khỏi Backup-Team chỉ loại một đường. Tài khoản vẫn có thể nhận quyền qua Legacy-Ops nếu đường đó còn được nền tảng áp dụng.

Báo cáo khắc phục cần đối chiếu tất cả các đường đã quan sát và cả quyền gán trực tiếp. Khi discovery chưa đầy đủ, không được xác nhận “đã hết quyền” chỉ dựa trên việc đường đại diện biến mất.

## 8. Những trường hợp cần đánh giá riêng

### 8.1. Nhóm động

Với nhóm động, thành viên được xác định từ quy tắc hoặc thuộc tính, thay vì chỉ từ thao tác thêm thành viên thủ công. Discovery cần phân biệt:

- Quy tắc xác định thành viên.
- Tập thành viên đã được nguồn đánh giá.
- Thời điểm đánh giá hoặc độ trễ cập nhật nếu có thông tin.
- Quyền sửa quy tắc hoặc sửa thuộc tính ảnh hưởng tới tư cách thành viên.

Không tự chạy lại một biểu thức nhóm bằng một bộ dữ liệu không đầy đủ rồi coi kết quả là trạng thái chính thức. Nếu nguồn chưa cung cấp tập thành viên hoặc không xác định được tính mới của dữ liệu, ghi rõ giới hạn đó.

Một thay đổi thuộc tính tài khoản có thể làm thay đổi thành viên nhóm động. Đây là khả năng tác động tới đường cấp quyền và cần được phân tích cùng quyền sửa thuộc tính; nó không phải cạnh thành viên đã tồn tại tại thời điểm quét.

### 8.2. Nhóm cục bộ trên tài nguyên

Một nhóm quản trị cục bộ có thể chứa nhóm từ nguồn danh tính tập trung:

~~~text
an.ops → Directory/Team-Ops → Host/app-03/Local-Administrators
~~~

Chỉ thu thập thư mục tập trung sẽ thiếu cạnh cuối nếu không đọc cấu hình phù hợp ở máy đích. Ngược lại, chỉ kiểm kê nhóm cục bộ sẽ chưa thấy các thành viên nằm trong Directory/Team-Ops.

Cần giữ định danh máy đích trong khóa của nhóm cục bộ. Hai nhóm cùng tên trên hai máy khác nhau là hai đối tượng phân quyền khác nhau.

### 8.3. Quan hệ qua miền, tenant hoặc nguồn ngoài

Một nhóm có thể chứa chủ thể từ miền quản lý khác hoặc một đối tượng tham chiếu ra ngoài. Kết quả cần lưu định danh gốc và trạng thái phân giải của chủ thể đó.

Không giả định rằng mọi nguồn có thể mở rộng lẫn nhau. Quan hệ tin cậy, khả năng đọc dữ liệu, cách ánh xạ danh tính và giới hạn loại nhóm có thể khác nhau. Nếu không phân giải được nhóm bên ngoài, ghi “còn nhánh chưa biết” thay vì loại nhánh khỏi báo cáo.

Một điểm dừng chưa phân giải cần có chủ thể hoặc đơn vị chịu trách nhiệm bổ sung dữ liệu. Nếu nhánh đó nằm dưới nhóm được cấp quyền rất rộng, bản thân khoảng trống bằng chứng là yếu tố cần ưu tiên xử lý.

### 8.4. Quyền đủ điều kiện và quyền đang hoạt động

Trong một thiết kế JIT, tài khoản có thể đủ điều kiện kích hoạt vai trò hoặc nhóm mà chưa có quyền đang hoạt động. Discovery nên tách các trạng thái:

~~~text
Eligible: có thể yêu cầu hoặc kích hoạt theo điều kiện.
Active: quan hệ hoặc grant đang hoạt động trong thời hạn.
Expired/Revoked: quyền tạm đã hết hạn hoặc bị thu hồi theo nguồn.
Unknown: chưa có đủ dữ liệu để xác định trạng thái.
~~~

Không gộp Eligible và Active thành một danh sách “đang là admin”. Ngược lại, danh sách quyền đang hoạt động cũng chưa phản ánh toàn bộ khả năng kích hoạt đặc quyền.

Kết quả cần giữ điều kiện kích hoạt, mốc thời gian và nguồn bằng chứng nếu có. Nếu approval cần người duyệt, xác thực tăng cường hoặc giới hạn tác vụ, đó là thông tin giúp hiểu khoảng cách từ quyền đủ điều kiện tới quyền có thể sử dụng.

### 8.5. Phiên cũ, token và cache quyền

Thành viên trong nguồn danh tính thay đổi không bảo đảm tất cả phiên đang mở nhận thay đổi ngay. Một tài nguyên có thể tiếp tục dùng ngữ cảnh quyền đã tạo trước đó cho tới khi cập nhật hoặc kết thúc theo cơ chế của nó.

Vì vậy, discovery thành viên tại thời điểm hiện tại và discovery phiên đặc quyền đang hoạt động là hai tập dữ liệu bổ sung nhau. Sau khi xóa cạnh thành viên, cần xác định những phiên hoặc credential nào còn có thể mang quyền cũ.

### 8.6. Quyền sửa nhóm và quản lý credential

Người có quyền thêm thành viên vào nhóm quản trị có thể tạo ra một đường cấp quyền mới dù hiện tại không nằm trong nhóm đó. Đây là câu hỏi về **khả năng thay đổi quyền**, khác với câu hỏi về **thành viên hiện tại**.

Tương tự, chủ thể có thể đọc hoặc sử dụng credential của một tài khoản đặc quyền có khả năng thao tác dưới danh tính của tài khoản đó. Việc phân tích cạnh truy cập credential giúp PAM nhìn thấy thêm đường tới đặc quyền, nhưng không nên gắn nhãn chúng là nested membership.

Một báo cáo rõ ràng tách ít nhất:

1. Đường thành viên dẫn tới điểm gán quyền.
2. Khả năng thay đổi nhóm hoặc cấu hình phân quyền.
3. Khả năng sử dụng credential của danh tính đặc quyền.
4. Phiên hoặc grant đặc quyền đang hoạt động.

## 9. Ví dụ xuyên suốt: tìm quyền gián tiếp của tài khoản dịch vụ

Giả sử hệ thống quản trị app-prod chấp nhận thành viên nhóm bắc cầu theo các quan hệ dưới đây. Production-Admins được gán vai trò quản trị cụm; việc gán quyền đã được thu thập riêng.

### 9.1. Dữ liệu đầu vào

| Thành viên | Nhóm chứa thành viên |
|---|---|
| an.ops | Oncall-Ops |
| svc-deploy | Release-Automation |
| Oncall-Ops | Production-Admins |
| Release-Automation | Production-Admins |
| svc-deploy | Legacy-Operations |
| Legacy-Operations | Production-Admins |
| External-Support | Production-Admins |

Nguồn hiện tại chưa đọc được thành viên của External-Support.

~~~mermaid
flowchart LR
    A["an.ops"] --> O["Oncall-Ops"]
    S["svc-deploy"] --> R["Release-Automation"]
    S --> L["Legacy-Operations"]
    O --> P["Production-Admins"]
    R --> P
    L --> P
    E["External-Support: chưa mở rộng"] --> P
    P --> B["Vai trò quản trị: app-prod"]
~~~

Các mũi tên đi từ thành viên tới nhóm cha; cạnh cuối nối nhóm tới điểm gán quyền.

### 9.2. Kết quả đúng mức bằng chứng

| Chủ thể | Đường quan sát được | Kết luận |
|---|---|---|
| an.ops | an.ops → Oncall-Ops → Production-Admins | Có đường thành viên đã quan sát tới nhóm được gán quyền |
| svc-deploy | Qua Release-Automation và Legacy-Operations | Có ít nhất hai đường; cần xét cả hai khi khắc phục |
| Thành viên của External-Support | Chưa biết | Nhánh chưa đầy đủ; không thể kết luận toàn bộ ai có quyền |

Nếu cấu hình phân quyền tại app-prod, trạng thái thành viên và điều kiện áp dụng đều đã được xác minh trong cùng ngữ cảnh, có thể nâng kết luận về quyền cho những đường tương ứng. Tuy nhiên, việc chưa đọc được External-Support vẫn ngăn kết luận rằng danh sách chủ thể của toàn bộ nhóm gốc đã đầy đủ.

### 9.3. Mẫu bản ghi kết quả

Dữ liệu sau là ví dụ về một finding, không chứa credential:

~~~json
{
  "finding_id": "finding-0042",
  "scan_id": "scan-discovery-18",
  "subject": {
    "source": "directory-prod",
    "object_id": "principal-8b2",
    "type": "service_identity",
    "display_name": "svc-deploy"
  },
  "binding_id": "binding-app-prod-admin",
  "target_scope": "cluster/app-prod",
  "representative_path": [
    "directory-prod/principal-8b2",
    "directory-prod/group-release",
    "directory-prod/group-prod-admins"
  ],
  "membership_depth": 2,
  "alternate_path_observed": true,
  "membership_evidence": "OBSERVED_DIRECT_EDGES",
  "authorization_assessment": "CANDIDATE_PRIVILEGE_PATH",
  "root_coverage": "PARTIAL",
  "coverage_gaps": [
    {
      "object_id": "directory-prod/group-external-support",
      "reason": "MEMBERSHIP_NOT_READABLE"
    }
  ],
  "observed_window": {
    "started_at": "2026-11-26T09:00:00+07:00",
    "finished_at": "2026-11-26T09:04:00+07:00"
  }
}
~~~

root_coverage mô tả mức độ thu thập dưới điểm gốc, không phủ nhận các cạnh đã thực sự quan sát. Một finding có đường dẫn rõ ràng có thể đồng thời nằm trong một lần quét tổng thể chưa đầy đủ.

Trong triển khai, cần có tham chiếu bằng chứng cho từng cạnh, phiên bản hoặc trạng thái điểm gán quyền và đánh giá điều kiện. Mẫu trên rút gọn các trường đó để làm rõ cách biểu diễn kết luận.

### 9.4. Hướng xử lý trong PAM

Với svc-deploy, nhóm vận hành cần xác minh công việc thực tế. Nếu pipeline chỉ cần triển khai một ứng dụng, quyền quản trị toàn cụm có thể rộng hơn nhu cầu.

Một hướng điều chỉnh là cấp một vai trò phù hợp với thao tác triển khai tại phạm vi cần thiết, gắn quyền với lần chạy công việc và xử lý cả hai đường thành viên cũ. Trước khi thay đổi, cần kiểm kê nơi sử dụng tài khoản, lịch job và phụ thuộc để tránh làm gián đoạn vận hành.

Không tự đưa tài khoản vào vault rồi luân chuyển credential ngay chỉ dựa trên việc phát hiện nó trong đồ thị. Discovery xác định phạm vi và rủi ro; onboarding và rotation còn cần biết cách ứng dụng lấy credential, khả năng cập nhật và cách xử lý lỗi.

## 10. Phân loại và ưu tiên kết quả discovery

Không phải mọi nested group đều là lỗi. Lồng nhóm có thể giúp phân chia trách nhiệm và quản lý quyền theo đội. Mục tiêu là làm rõ quyền, chủ thể sở hữu và khả năng kiểm soát.

Có thể đánh giá ưu tiên theo các chiều:

| Chiều đánh giá | Câu hỏi thực tế |
|---|---|
| Ảnh hưởng | Điểm gán quyền cho phép làm gì trên tài nguyên nào? |
| Phạm vi chủ thể | Có bao nhiêu tài khoản người, dịch vụ hoặc nguồn ngoài có đường dẫn? |
| Mục đích | Quyền có phục vụ công việc hiện tại và đã có người chịu trách nhiệm? |
| Tính thường trực | Quyền luôn tồn tại hay chỉ hoạt động theo grant có hạn? |
| Khả năng thay đổi | Ai có thể thêm thành viên, sửa quy tắc hoặc thay điểm gán quyền? |
| Mức bảo đảm | Có xác thực phù hợp, giới hạn phiên và giám sát thao tác? |
| Mức độ bằng chứng | Đường dẫn đã xác nhận tới đâu và nhánh nào chưa đọc được? |

Các tình huống thường cần ưu tiên:

- Nhóm từ môi trường ít nhạy cảm được lồng vào nhóm quản trị sản xuất.
- Nhóm có tập thành viên lớn hoặc chủ thể sở hữu chưa xác định nằm dưới điểm quyền rất rộng.
- Tài khoản dịch vụ có quyền quản trị vượt phạm vi công việc và dùng credential lâu dài.
- Chủ thể bên ngoài chưa phân giải được nhưng nằm trong đường tới tài nguyên nhạy cảm.
- Tài khoản đã ngừng sử dụng vẫn xuất hiện trên đường thành viên.
- Người quản lý thành viên nhóm có thể thay đổi đường cấp quyền mà thiếu quy trình phù hợp.

Độ sâu lồng nhóm có thể làm việc giải thích và rà soát khó hơn, nhưng không nên dùng nó như điểm rủi ro duy nhất. Một nhóm một tầng chứa mọi nhân viên và được cấp quyền quản trị có thể nghiêm trọng hơn chuỗi nhiều tầng có kiểm soát rõ ràng.

## 11. Khắc phục và xác minh sau thay đổi

### 11.1. Trước khi thay đổi

Mỗi đề xuất cần nêu rõ cạnh hoặc điểm gán quyền sẽ thay đổi, các chủ thể bị ảnh hưởng và công việc cần tiếp tục hoạt động.

Với một nhóm dùng chung, xóa một nhóm con có thể tác động tới nhiều tài khoản dịch vụ và job chạy theo lịch. Cần xác nhận chủ sở hữu, cửa sổ thực hiện và phương án khôi phục phù hợp với thay đổi.

Các lựa chọn có thể gồm:

- Thu hẹp vai trò hoặc phạm vi tài nguyên ở điểm gán quyền.
- Tách nhóm quản trị khỏi nhóm dùng cho mục đích cộng tác thông thường.
- Loại đường thành viên không còn cần thiết sau khi đã xác minh phụ thuộc.
- Chuyển quyền thường trực sang điều kiện kích hoạt hoặc grant JIT phù hợp.
- Giới hạn tập thao tác theo JEA, thay vì chỉ giới hạn thời gian.
- Kiểm soát chặt quyền sửa thành viên nhóm và lưu bằng chứng thay đổi.

Chọn phương án theo khả năng thực thi của nền tảng. Không coi việc đổi tên nhóm hoặc gắn nhãn “JIT” là đã thay đổi quyền.

### 11.2. Sau khi thay đổi

Việc xác minh cần trả lời các câu hỏi riêng:

1. Cạnh thành viên hoặc điểm gán quyền đã thay đổi trong nguồn chính thức chưa?
2. Còn đường cấp quyền thay thế nào đã biết không?
3. Các nguồn quan trọng đã đọc đầy đủ trong lần xác minh chưa?
4. Tài nguyên đích đã áp dụng thay đổi theo cơ chế của nó chưa?
5. Phiên hoặc credential cũ có cần kết thúc, thu hồi hoặc thay mới không?
6. Công việc hợp lệ còn hoạt động trong phạm vi quyền mới không?

Không lấy một lần gọi API thất bại làm bằng chứng duy nhất rằng tài khoản đã mất quyền. Lỗi đó có thể đến từ mạng, xác thực hoặc tài nguyên không sẵn sàng. Cần có bằng chứng liên quan trực tiếp đến đánh giá quyền, kết hợp trạng thái phân quyền và phiên phù hợp.

Cũng không lấy một kết quả thành công làm bằng chứng rằng toàn bộ phạm vi JEA đều đúng. Phải kiểm tra cả thao tác được phép và những hành động đáng lẽ bị từ chối trong ngữ cảnh đã xác định.

## 12. Duy trì kết quả discovery theo thời gian

### 12.1. Phân biệt quan sát cũ và hiện tại

Một bản ghi “đã thấy cạnh lúc 09:00” không đồng nghĩa cạnh vẫn còn ở thời điểm 15:00. Báo cáo cần hiển thị thời điểm quan sát, lần xác nhận gần nhất và trạng thái mới nhất.

Nếu lần quét trước thấy một cạnh nhưng lần quét sau bị thiếu dữ liệu, chưa đủ căn cứ kết luận cạnh đã bị xóa. Có thể giữ “đã quan sát trước đây, chưa xác minh lại” thay vì tự chuyển sang “không tồn tại”.

Một mô hình trạng thái có thể là:

~~~text
OBSERVED_CURRENT       Được xác nhận trong lần thu thập hiện tại.
OBSERVED_PREVIOUSLY    Đã thấy trước đây, chưa được xác nhận lại.
REMOVAL_CONFIRMED      Có bằng chứng phù hợp rằng quan hệ đã kết thúc.
UNKNOWN                Chưa đủ dữ liệu để xác định.
~~~

Các trạng thái này phục vụ bằng chứng và độ mới dữ liệu; không thay thế trạng thái Active hoặc Eligible của hệ thống phân quyền.

### 12.2. Quét đầy đủ và cập nhật gia tăng

Quét đầy đủ tạo đường cơ sở và giúp phát hiện khoảng trống. Cập nhật gia tăng hoặc sự kiện thay đổi giúp phát hiện nhanh việc thêm thành viên, đổi quy tắc nhóm hoặc sửa điểm gán quyền.

Luồng sự kiện có thể bị gián đoạn hoặc bỏ sót nếu không theo dõi con trỏ, khoảng thời gian và trạng thái xử lý. Vì vậy, cần cơ chế đối soát phù hợp với mức độ tin cậy của nguồn, thay vì giả định rằng chưa nhận sự kiện có nghĩa dữ liệu không đổi.

Các thay đổi cần đánh giá lại có thể gồm:

- Thêm hoặc xóa cạnh thành viên.
- Thay vai trò hoặc phạm vi tại một điểm gán quyền.
- Đổi quy tắc nhóm động hay thuộc tính liên quan.
- Kích hoạt, gia hạn hoặc thu hồi grant.
- Thay quan hệ liên kết danh tính giữa các nguồn.
- Xóa hoặc tạo lại đối tượng có cùng tên hiển thị.

Nếu một nhóm cha được gán quyền mới, nhiều tài khoản phía dưới có thể bị ảnh hưởng dù không có thay đổi nào ở tài khoản. Tính lại tác động chỉ theo danh sách tài khoản vừa sửa sẽ bỏ sót trường hợp này.

### 12.3. Chỉ số chất lượng kiểm kê

| Chỉ số | Ý nghĩa |
|---|---|
| Tỷ lệ điểm gán quyền có cây thành viên được đọc đầy đủ | Đo mức bao phủ tại các gốc đặc quyền |
| Số nhóm hoặc chủ thể chưa phân giải | Làm rõ những nhánh còn thiếu bằng chứng |
| Độ mới dữ liệu theo nguồn và phạm vi | Cho biết kết luận dựa trên quan sát cách đây bao lâu |
| Số đường gián tiếp tới quyền đặc quyền | Hỗ trợ rà soát quy mô và khả năng giải thích |
| Số finding có bằng chứng từng cạnh | Đánh giá khả năng truy vết kết luận |
| Số thay đổi quyền chưa đối soát | Theo dõi độ trễ giữa sự kiện và trạng thái kiểm kê |

Định nghĩa mẫu số của từng chỉ số. Nếu chưa kiểm kê được đầy đủ các điểm gán quyền, “100% nhóm đã đọc” trong một danh sách nhỏ không có nghĩa đã bao phủ toàn bộ môi trường.

## 13. Những lỗi dễ dẫn tới kết luận sai

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ đọc thành viên trực tiếp | Bỏ sót tài khoản trong nhóm con | Mở rộng đồ thị theo ngữ nghĩa nguồn |
| Đảo chiều cạnh | Truy ra tập đối tượng không đúng câu hỏi | Quy định chiều MEMBER_OF và hướng duyệt riêng |
| Gộp đối tượng theo tên | Trộn danh tính giữa miền hoặc đối tượng được tạo lại | Dùng định danh ổn định kèm nguồn |
| Xem mọi nút đã thăm là chu trình | Báo sai với các nhánh hội tụ | Dùng cơ chế phát hiện chu trình phù hợp |
| Ngừng ở giới hạn độ sâu rồi báo đầy đủ | Che giấu nhánh chưa khám phá | Giữ trạng thái cắt ngắn và khoảng trống |
| Coi lỗi đọc là không có thành viên | Tạo cảm giác an toàn sai | Phân biệt rỗng đã xác minh và dữ liệu thiếu |
| Gán quyền hiệu lực từ thành viên đơn thuần | Bỏ qua điều kiện và cơ chế tài nguyên | Tách bằng chứng thành viên và đánh giá quyền |
| Xóa một đường rồi đóng finding | Bỏ sót quyền qua đường khác | Đối chiếu các đường và quyền gán trực tiếp |
| Gộp Eligible với Active | Sai trạng thái đặc quyền tại thời điểm báo cáo | Lưu riêng trạng thái và thời hạn |
| Xem nhóm có tên quản trị là đủ bằng chứng | Báo thừa hoặc thiếu quyền thực tế | Đối chiếu điểm gán quyền và phạm vi |

## 14. Bài tập áp dụng

Cho các quan hệ:

~~~text
user-a   → Team-A
svc-job  → Team-A
Team-A   → Ops-Core
user-a   → Team-B
Team-B   → Ops-Core
Ops-Core → quyền quản trị trên cluster-01
Partner  → Ops-Core
~~~

Đã đọc đầy đủ Team-A, Team-B và Ops-Core, nhưng không đủ quyền đọc thành viên của Partner. Nền tảng đã được xác định là có áp dụng bắc cầu cho các cạnh thành viên đã nêu.

Hãy thực hiện trên giấy hoặc bằng mô hình dữ liệu giả lập:

1. Liệt kê các đường đã quan sát từ user-a và svc-job tới điểm gán quyền.
2. Đánh dấu độ sâu theo số cạnh thành viên, tách cạnh gán quyền.
3. Giải thích vì sao danh sách toàn bộ chủ thể của Ops-Core vẫn chưa đầy đủ.
4. Xác định kết luận nào cần thêm bằng chứng về vai trò, điều kiện và phiên.
5. Đề xuất cách giảm quyền của svc-job nếu nó chỉ cần cập nhật một tác vụ.
6. Nêu bằng chứng cần có sau khi xóa user-a khỏi Team-A.

Hướng phân tích:

- user-a có hai đường thành viên đã biết; svc-job có một đường đã biết.
- Mỗi đường từ tài khoản qua Team-A hoặc Team-B tới Ops-Core có hai cạnh thành viên.
- Nhánh Partner chưa đọc được nên không thể khẳng định đã biết toàn bộ tài khoản phía dưới Ops-Core.
- Xóa user-a khỏi Team-A vẫn để lại đường qua Team-B.
- Nếu muốn kết luận user-a không còn quyền ở cluster-01, còn phải xem các điểm gán quyền khác, độ đầy đủ dữ liệu và quyền giữ trong phiên hoặc credential liên quan.

Có thể mở rộng bài tập bằng việc thêm một cạnh tạo chu trình giữa hai nhóm, rồi mô tả cách thuật toán dừng mà vẫn lưu đủ cạnh quan sát được. Không giả định hệ thống thật cho phép tạo chu trình chỉ vì dữ liệu giả lập có tình huống này.

## 15. Ghi nhớ

Phát hiện nested group là truy vết những đường thành viên có thể đưa một chủ thể tới điểm gán quyền đặc quyền. Một kết quả hữu ích cần giữ đúng định danh, chiều cạnh, phạm vi quyền, thời điểm quan sát và bằng chứng của từng bước.

Trong PAM, giá trị của discovery nằm ở việc giải thích được ai có thể tiếp cận tài nguyên nhạy cảm và vì sao. Chất lượng kết luận phụ thuộc cả vào những đường đã tìm thấy lẫn những nhánh chưa đọc được. Từ nền tảng đó mới có thể thu hẹp quyền, chuyển sang JIT/JEA, quản lý credential và xác minh thu hồi một cách có căn cứ.
