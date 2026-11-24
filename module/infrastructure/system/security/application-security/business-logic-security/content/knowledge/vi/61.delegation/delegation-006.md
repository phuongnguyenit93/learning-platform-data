# Delegation chain: bảo vệ chuỗi ủy quyền trong quy tắc nghiệp vụ

## 1. Chuỗi ủy quyền là gì?

Trong chương **Delegation**, delegation chain là một chuỗi chuyển giao quyền thực hiện một số hành động từ chủ thể này sang chủ thể khác. Ví dụ:

~~~text
A ủy quyền cho B.
B được phép ủy quyền lại một phần cho C.
C thực hiện thao tác dựa trên quyền đi qua A -> B -> C.
~~~

A, B và C có thể là người dùng hoặc service principal. Tuy nhiên, việc một dịch vụ gọi dịch vụ khác không tự tạo thành một chuỗi ủy quyền hợp lệ. Hệ thống phải có bằng chứng ai được giao quyền gì, cho đối tượng nào và trong thời gian nào.

Một chuỗi an toàn không chỉ kiểm tra C có đăng nhập hay không. Nó cần chứng minh:

- Quyền gốc tồn tại và được phép ủy quyền.
- Mỗi mắt xích được cấp bởi chủ thể thực sự có thẩm quyền.
- Quyền được thu hẹp hoặc giữ nguyên trong phạm vi được phép.
- Mọi mắt xích cần thiết vẫn hợp lệ tại thời điểm sử dụng.
- Người gọi hiện tại đúng là người nhận ở cuối chuỗi.
- Thao tác vẫn thỏa các quy tắc nghiệp vụ bắt buộc.

Nếu kiểm tra thiếu, người dùng có thể lợi dụng ủy quyền lại để mở rộng phạm vi, dùng quyền đã bị thu hồi, đổi đối tượng, né hạn mức hoặc biến một người thành nhiều người phê duyệt.

Mục tiêu bài học là thiết kế chuỗi ủy quyền có thể kiểm tra được tại transaction ghi quyết định nghiệp vụ, kể cả khi có retry, thu hồi và nhiều thao tác đồng thời.

## 2. Ví dụ xuyên suốt và các danh tính cần tách

### 2.1. Ví dụ phê duyệt mua sắm

Giả sử A có quyền gốc phê duyệt đề nghị mua sắm của đơn vị D01, tối đa 100 triệu VND mỗi đề nghị. Chính sách cho phép ủy quyền trong phạm vi này.

A cấp grant D1 cho B:

- Hành động: APPROVE_PURCHASE.
- Phạm vi: đơn vị D01 trong cùng tenant.
- Tối đa 60 triệu VND mỗi đề nghị.
- Có hiệu lực từ ngày 22 đến trước mốc kết thúc đã chỉ định ngày 30.
- Được ủy quyền lại tối đa một mắt xích nữa.

B cấp grant D2 cho C:

- Cùng hành động và đơn vị.
- Tối đa 25 triệu VND mỗi đề nghị.
- Kết thúc sớm hơn D1, tại mốc được chỉ định ngày 28.
- Không được ủy quyền tiếp.

Các mốc ngày trong ví dụ phải được lưu bằng instant chính xác theo chính sách, không dựa vào cách hiểu mơ hồ “hết ngày” của từng máy.

~~~mermaid
flowchart LR
    R["Quyền gốc của A: D01, tối đa 100 triệu"] --> A["A"]
    A -->|"D1: tối đa 60 triệu, cho ủy quyền lại"| B["B"]
    B -->|"D2: tối đa 25 triệu, không ủy quyền tiếp"| C["C"]
    C -->|"Yêu cầu phê duyệt"| P["Đề nghị thuộc D01"]
~~~

Nếu chỉ xét các trần tiền cùng đơn vị và cùng ý nghĩa, quyền hiệu lực của C không vượt:

~~~text
min(100 triệu, 60 triệu, 25 triệu) = 25 triệu VND
~~~

Không cộng 60 và 25. Không lấy trần 100 triệu của A để bỏ qua giới hạn mà A đã đặt cho B hoặc B đã đặt cho C.

### 2.2. Ba khái niệm không nên trộn

| Khái niệm | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Actor | C | Chủ thể đang được xác thực và gửi thao tác |
| Root authority principal | A | Chủ thể có quyền gốc mà chuỗi đang dựa vào |
| Business subject | Người hoặc đơn vị gắn với đề nghị | Chủ thể nghiệp vụ được thao tác, không mặc định là A hoặc C |

B là chủ thể trung gian trong chuỗi. B không biến mất khỏi bằng chứng chỉ vì C là actor cuối cùng.

Nếu C phê duyệt đề nghị của nhân viên P, cần lưu C là người thao tác, A là nguồn thẩm quyền và P là chủ thể nghiệp vụ tương ứng. Không ghi tất cả thành A và gọi đó là “thực hiện thay”, vì cách đó làm mất khả năng kiểm tra tách biệt nhiệm vụ và truy vết.

Nếu một người có nhiều tài khoản, chính sách độc lập cần dùng danh tính tổ chức đáng tin cậy để nhận diện quan hệ đó. Hai account ID khác nhau không luôn là hai người độc lập.

## 3. Quyền hiệu lực là giao của các ràng buộc

Gọi:

- P0 là quyền gốc được phép dùng và được phép ủy quyền.
- G1, G2, ..., Gn là các grant trên đường đã chọn.
- O là đối tượng nghiệp vụ thực tế được lấy từ dữ liệu máy chủ.
- X là hành động cần thực hiện.
- t là thời điểm quyết định.

Cách diễn đạt tổng quát:

~~~text
allowed =
    actor đúng người nhận cuối
    AND quyền gốc hiện hành hợp lệ
    AND tất cả grant trên đường hợp lệ
    AND mọi ràng buộc của P0, G1, ..., Gn đều cho phép (X, O, t)
    AND các điều kiện nghiệp vụ bắt buộc được đáp ứng
~~~

Đối với tập quyền có thể biểu diễn thành tập, quyền hiệu lực là phần giao, không phải phần hợp. Trong triển khai, nhiều ràng buộc là predicate theo đối tượng và ngữ cảnh; hệ thống phải đánh giá đầy đủ thay vì chỉ gộp danh sách role.

| Chiều ràng buộc | Quy tắc kết hợp |
| --- | --- |
| Hành động | Hành động phải được quyền gốc và mọi grant cho phép |
| Tenant | Phải khớp miền tenant được phép; ví dụ này cấm chuỗi xuyên tenant |
| Phạm vi đối tượng | Đối tượng phải nằm trong mọi phạm vi trên đường |
| Trần tiền mỗi đề nghị | Không vượt bất kỳ trần áp dụng nào |
| Thời gian | Nằm trong giao các khoảng hiệu lực |
| Mục đích hoặc loại nghiệp vụ | Phải thỏa mọi điều kiện liên quan |
| Ủy quyền tiếp | Mọi điều kiện cho phép tạo mắt xích mới phải được đáp ứng |
| Quota cộng dồn | Từng quota áp dụng phải còn đủ, không chỉ quota ở lá |

Phép min chỉ đúng khi các giới hạn so sánh được: cùng tiền tệ, cùng đơn vị và cùng phạm vi. Không lấy min giữa “60 triệu mỗi đề nghị” và “30 triệu mỗi ngày” rồi coi đó là một hạn mức duy nhất.

Các điều kiện không được ủy quyền, như tách biệt nhiệm vụ theo chính sách, vẫn nằm ngoài phép giao quyền cho phép. Có đủ grant không tự xóa các điều kiện cấm.

## 4. Business invariants của chuỗi

Những invariant nên được viết trước khi thiết kế API:

1. Mỗi grant thuộc một tenant và có định danh không nhập nhằng.
2. Parent của một grant con được cố định khi phát hành, không được đổi sang một nguồn quyền khác sau đó.
3. Người cấp grant con phải là người nhận hợp lệ của parent hoặc có một quyền quản trị riêng được chính sách cho phép.
4. Hành động, đối tượng, thời gian và giới hạn của grant con không mở rộng quyền có thể ủy quyền của parent.
5. Việc tạo grant con chỉ được phép nếu parent cho ủy quyền tiếp và còn đủ độ sâu.
6. Một đường ủy quyền không có chu trình theo các danh tính mà chính sách coi là cùng chủ thể.
7. Actor hiện tại phải khớp người nhận ở lá, không được tự khai actingAs để đổi danh tính.
8. Mọi ancestor cần thiết đều phải hợp lệ khi quyền được sử dụng.
9. Thu hồi ancestor phải làm đường phụ thuộc mất quyền theo hợp đồng thu hồi đã chọn.
10. Một quyết định nghiệp vụ phải dùng một đường cấp quyền hoàn chỉnh, không ghép các mảnh quyền không tương thích.
11. Retry không tạo thêm quyết định hoặc tiêu thụ quota thêm lần nữa.
12. Nhật ký giữ được actor thật, nguồn quyền gốc và đường đã dùng.

Một grant lá ACTIVE không chứng minh toàn bộ chuỗi ACTIVE. Tương tự, parent từng hợp lệ lúc cấp con không chứng minh parent còn hợp lệ lúc con được dùng.

## 5. Mô hình lưu trữ và đường ủy quyền

Một bản ghi delegation_grant có thể có:

| Nhóm | Trường minh họa |
| --- | --- |
| Định danh | tenant_id, grant_id |
| Quan hệ | parent_grant_id, grantor_principal_id, grantee_principal_id |
| Nguồn quyền | root_authority_id, root_principal_id |
| Nội dung | actions, resource_scope, constraints |
| Hạn mức | per_operation_limit, currency, quota_scope |
| Hiệu lực | valid_from, expires_at |
| Ủy quyền lại | can_redelegate, remaining_hops |
| Vòng đời | PENDING, ACTIVE, REVOKED, EXPIRED |
| Kiểm toán | issued_at, issued_by_actor, reason |
| Kiểm soát ghi | row_version hoặc cơ chế tương đương |

Danh tính principal cần bao gồm namespace phù hợp, chẳng hạn tenant, loại principal và ID. Không để một user ID và một service ID trùng chuỗi ký tự rồi bị coi là cùng chủ thể hoặc thay thế nhau.

Trong mô hình này:

- Grant đầu tiên D1 tham chiếu quyền gốc và không có parent grant.
- D2 tham chiếu D1 bằng parent_grant_id.
- Liên kết tenant và nguồn quyền phải khớp với parent.
- Định nghĩa bảo mật của grant đã phát hành là bất biến.
- Thay phạm vi hoặc thời hạn tạo một grant mới, không sửa âm thầm định nghĩa mà các grant con đang phụ thuộc.
- Thu hồi và đánh dấu hết hạn là chuyển trạng thái có kiểm soát.

Nếu muốn hỗ trợ thay đổi định nghĩa tại chỗ, phải có phiên bản bất biến và ràng buộc con với đúng phiên bản đó. Không để parent_id trỏ đến “nội dung mới nhất” có thể thay đổi ý nghĩa lịch sử.

Dữ liệu trạng thái có thể thay đổi, nhưng parent không được chuyển từ D1 sang D9 để lách việc D1 bị thu hồi.

### 5.1. Client chỉ cung cấp tham chiếu, không tự viết chuỗi

API có thể nhận leaf_grant_id để chỉ đường mong muốn. Máy chủ phải tự truy ngược parent trong dữ liệu đáng tin cậy.

Không tin một mảng do client gửi như:

~~~json
{
  "actor": "C",
  "onBehalfOf": "A",
  "chain": ["D1", "D2"],
  "effectiveLimitVnd": 100000000
}
~~~

Actor lấy từ xác thực. Nguồn quyền, đường và hạn mức hiệu lực đều do máy chủ xác minh. Dữ liệu client có thể là gợi ý để tìm kiếm, không phải bằng chứng quyền.

### 5.2. Không lẫn nhiều đường cấp quyền

C có thể đồng thời:

- Có một quyền trực tiếp riêng.
- Có đường A → B → C.
- Có đường X → C từ nguồn quyền khác.

Hệ thống có thể cho phép thao tác theo một trong các tuyến hợp lệ nếu chính sách cho phép. Nhưng mỗi tuyến phải tự đủ điều kiện.

Không lấy hành động APPROVE từ đường A, phạm vi đơn vị D02 từ đường X và hạn mức từ role trực tiếp để tạo một quyền tổng hợp chưa ai cấp.

Nếu chọn một tuyến khác, phải áp dụng đúng quota, nguồn thẩm quyền và audit của tuyến đó. Không tự chuyển tuyến sau khi quota của tuyến đầu hết mà bỏ qua điều kiện của tuyến mới.

## 6. Phát hành một grant con an toàn

Khi B muốn cấp D2 cho C, máy chủ cần:

1. Xác thực B và xác định tenant.
2. Đọc, khóa hoặc bảo vệ quyền gốc và đường tới D1 theo giao thức nhất quán.
3. Xác minh actor đúng người nhận được phép dùng D1.
4. Kiểm tra toàn bộ ancestor vẫn hợp lệ theo chính sách.
5. Kiểm tra D1 cho ủy quyền tiếp.
6. Kiểm tra quyền gốc và các giới hạn độ sâu còn cho phép thêm mắt xích.
7. Xác minh C là principal hợp lệ trong phạm vi được phép.
8. Kiểm tra C không tạo chu trình theo danh tính được chính sách sử dụng.
9. Chứng minh phạm vi D2 không rộng hơn quyền có thể chuyển từ D1.
10. Ghi D2, căn cứ và quyết định phê duyệt bổ sung nếu chính sách yêu cầu.
11. Commit rồi mới coi grant đã được phát hành.

Nếu grant còn PENDING vì thiếu phê duyệt, nó chưa được dùng để thực hiện hoặc cấp tiếp.

### 6.1. Thu hẹp phạm vi không chỉ là so hai chuỗi

Các điều kiện con hợp lệ có thể gồm:

~~~text
actions(D2) là tập con của actions có thể chuyển từ D1
scope(D2) nằm trong phạm vi có thể chuyển từ D1
limit(D2) <= limit có thể chuyển từ D1
valid_from(D2) >= valid_from(D1)
expires_at(D2) <= expires_at(D1)
~~~

Nếu hệ thống cho phép biểu thức điều kiện tùy ý, việc chứng minh predicate con không rộng hơn predicate cha có thể rất khó. Một thiết kế thực tế thường dùng cấu trúc scope và constraint giới hạn, có thuật toán kiểm tra quan hệ bao hàm rõ ràng.

Không dùng so tiền tố chuỗi như D01* để quyết định quan hệ giữa các đơn vị nếu đó không phải ngữ nghĩa đã được định nghĩa. Cũng không mặc định hai biểu thức JSON khác nhau có quan hệ bao hàm chỉ vì cùng chứa một departmentId.

Bài này chọn từ chối yêu cầu cấp con mở rộng phạm vi. Không âm thầm cắt bớt rồi trả thành công mà không cho người dùng biết nội dung thật sự đã được cấp.

### 6.2. Đếm độ sâu nhất quán

Giả sử remaining_hops là số mắt xích tiếp theo còn được phép tạo sau grant hiện tại.

Trong ví dụ:

~~~text
D1.remaining_hops = 1
D2.remaining_hops = 0
~~~

Khi tạo D2, phải có:

~~~text
D1.can_redelegate = true
D1.remaining_hops >= 1
D2.remaining_hops <= D1.remaining_hops - 1
~~~

Nếu D2.remaining_hops = 0 thì D2 không được cấp tiếp. Ngoài giới hạn từng grant, hệ thống cần một độ sâu tối đa tuyệt đối để giới hạn chi phí truy vết.

Grant con không được tự đặt remaining_hops về giá trị mặc định lớn hơn. Chính sách giới hạn độ sâu phải theo nguồn quyền và toàn đường, không chỉ theo từng request cấp grant.

## 7. Chu trình, nhận dạng và giả mạo nguồn quyền

### 7.1. Chặn chu trình theo đường

Ví dụ A → B → C → A có thể giúp quyền quay lại nguồn ban đầu dưới một hình thức khác, làm khó kiểm tra trách nhiệm và quota.

Bài này chọn cấm lặp principal trên cùng một đường theo danh tính chuẩn mà chính sách sử dụng. Đồng thời cần phát hiện:

- Lặp grant_id do dữ liệu lỗi hoặc liên kết bất thường.
- Parent bị thiếu.
- Liên kết tenant không khớp.
- Grantor của grant con không khớp grantee của parent.
- Nguồn quyền gốc bị đổi giữa đường.
- Độ sâu vượt giới hạn.

Một đồ thị có nhiều đường không tự là chu trình. Hai đường độc lập cùng đi tới C có thể hợp lệ. Điều cần kiểm tra là từng đường và các quy tắc liên quan đến việc dùng nhiều đường.

Nếu tổ chức có các tài khoản khác nhau của cùng một người, phải quyết định vòng lặp theo principal kỹ thuật hay theo danh tính người thật. Những kiểm soát tách biệt nhiệm vụ thường cần thông tin danh tính tổ chức bổ sung.

### 7.2. Không tự khai đại diện

Một header như X-On-Behalf-Of hoặc một trường rootPrincipalId trong body không tự cấp quyền. Dịch vụ nhận phải tạo một ngữ cảnh ủy quyền đã xác minh từ actor xác thực và nguồn grant đáng tin cậy.

Đối với giao tiếp giữa dịch vụ, cần xác định rõ:

- Dịch vụ gọi được xác thực là ai.
- Nó được phép đại diện cho chủ thể nào.
- Hành động và đối tượng nào đang được yêu cầu.
- Bằng chứng có đúng nơi nhận và mục đích không.
- Có được tiếp tục ủy quyền hay chỉ được thực hiện thao tác cuối.

Một service có quyền kỹ thuật rộng có thể trở thành confused deputy: dùng quyền của chính nó để làm việc mà người gọi không được phép. Kiểm tra chuỗi cần gắn với đối tượng thật, không chỉ kiểm tra service được gọi có tài khoản hệ thống hợp lệ.

### 7.3. Chữ ký không tự chứng minh quyền hiện hành

Một token được ký đúng có thể chứng minh nội dung đã được một nguồn phát hành. Nó chưa tự chứng minh:

- Ancestor chưa bị thu hồi.
- Quyền gốc vẫn tồn tại.
- Actor hiện tại được dùng token.
- Token đúng tenant, hành động, đối tượng và nơi nhận.
- Grant còn hạn hoặc còn quota.
- Hành động không vi phạm quy tắc nghiệp vụ.

Nếu sản phẩm cần thu hồi tức thời hoặc quota dùng chung, phải có cơ chế trạng thái và nhất quán tương ứng. Không coi một token dài hạn là bản sao vĩnh viễn của toàn bộ quyền trong chuỗi.

## 8. Kiểm tra toàn đường tại thời điểm sử dụng

### 8.1. Tìm đường chỉ là bước đầu

Một thuật toán truy vết có thể:

1. Bắt đầu từ leaf_grant_id trong đúng tenant.
2. Đi theo parent_grant_id tới grant đầu tiên.
3. Giới hạn số nút được đọc.
4. Phát hiện grant lặp, parent thiếu và liên kết bất thường.
5. Đảo thứ tự để có đường từ gốc tới lá.
6. Tìm nguồn quyền gốc được tham chiếu.
7. Xác minh actor khớp người nhận ở lá.

Không để dữ liệu lỗi tạo vòng lặp vô hạn hoặc khiến mỗi request đọc một đồ thị không giới hạn. Chỉ cần parent pointer cho một đường đã chọn; không duyệt mọi nhánh chỉ vì client muốn thử hàng nghìn grant.

Kết quả truy vết trước khi khóa là dữ liệu định tuyến. Nó chưa phải quyết định cho phép cuối cùng.

### 8.2. Những kiểm tra cần thực hiện lại dưới cơ chế nhất quán

Tại điểm quyết định:

- Quyền gốc vẫn thuộc đúng principal và cho phép hành động trên đối tượng thực tế.
- Quyền gốc vẫn cho phép dùng ủy quyền theo chính sách.
- Mỗi grant có trạng thái cho phép.
- Mỗi quan hệ parent, grantor và grantee khớp đường.
- Mọi tenant và nguồn quyền khớp nhau.
- Không có chu trình và không vượt độ sâu hiện hành.
- Thời gian nằm trong khoảng của mọi mắt xích.
- Mọi scope, trần tiền và điều kiện khác đều cho phép thao tác.
- Actor, root và các danh tính liên quan thỏa quy tắc nghiệp vụ.
- Quota áp dụng còn đủ.
- Đối tượng vẫn ở đúng trạng thái và revision.

Đối tượng cần được lấy từ dữ liệu máy chủ. Nếu client gửi departmentId = D01 trong body nhưng đề nghị thật thuộc D02, kiểm tra quyền phải dùng D02.

Tương tự, số tiền, chủ thể đề nghị, nhà cung cấp và bằng chứng phê duyệt phải gắn với phiên bản thật. Một request sửa giá xuống thấp để qua hạn mức rồi thực thi giá khác sẽ phá invariant nếu hai bước dùng hai nguồn dữ liệu.

### 8.3. Mô hình quyền gốc hiện hành

Ví dụ trong bài dùng mô hình tham chiếu quyền gốc hiện hành: chuỗi không tiếp tục cho phép một hành động mà A đã mất quyền thực hiện hoặc không còn được phép ủy quyền.

Nếu quyền gốc của A giảm từ 100 triệu xuống 20 triệu, C không được tiếp tục duyệt 25 triệu chỉ vì D2 vẫn ghi trần 25 triệu. Quyền hiệu lực phải tính lại với trần hiện hành 20 triệu.

Một hệ thống khác có thể cấp capability độc lập với thời hạn và quy tắc thu hồi riêng. Nếu chọn mô hình đó, cần diễn đạt rõ quyền đã được chuyển giao độc lập tới mức nào. Không dùng mô hình snapshot ở nơi này nhưng hứa thu hồi tức thời theo mô hình tham chiếu ở nơi khác.

## 9. Transaction ghi quyết định nghiệp vụ

### 9.1. Tại sao “đã kiểm tra chuỗi” có thể vẫn sai?

Ví dụ:

~~~text
T1 đọc D1 ACTIVE.
T2 thu hồi D1 và commit.
T1 chỉ khóa D2 rồi ghi phê duyệt.
~~~

Nếu hợp đồng yêu cầu parent còn hợp lệ tại điểm quyết định, T1 không được bỏ qua việc D1 đã bị thu hồi.

Có cùng một transaction chưa chắc đủ nếu T1 chỉ đọc D1 theo một snapshot cũ và không có cơ chế phát hiện hoặc ngăn thay đổi liên quan.

Cần một giao thức đồng thời bảo vệ toàn bộ dữ liệu có thể làm thay đổi kết quả cấp quyền, không chỉ hàng grant lá.

### 9.2. Phạm vi và thứ tự khóa

Giả sử quyền gốc, trạng thái grant, đối tượng phê duyệt, quota, quyết định và idempotency đều được bảo vệ trong cùng một cơ sở dữ liệu.

Một thứ tự khóa minh họa:

1. Bản ghi idempotency của thao tác.
2. Chính sách và các nguồn quyền gốc cần dùng, theo khóa ổn định.
3. Các grant trên đường, theo khóa ổn định.
4. Các đối tượng nghiệp vụ liên quan, theo khóa ổn định.
5. Các hàng quota áp dụng, theo khóa ổn định.
6. Ghi quyết định và các hệ quả local.

Mọi luồng cấp con, thu hồi, sửa quyền gốc và thực hiện thao tác cần tuân thủ giao thức chung đối với các hàng chúng chạm tới.

Không khóa từ lá tới gốc ở API thực thi nhưng từ gốc tới lá trong luồng khác theo thứ tự không tương thích. Việc sắp khóa theo ID ổn định là một lựa chọn; đó không phải lý do để bỏ kiểm tra thứ tự logic của đường sau khi có đủ khóa.

Vì định nghĩa và parent của grant trong ví dụ bất biến, ứng dụng có thể xác định trước tập hàng cần khóa rồi đọc lại trạng thái sau khóa. Nếu dữ liệu thiếu hoặc không khớp, dừng thay vì cố lắp một đường thay thế trong cùng quyết định.

### 9.3. Mã giả Java

Ví dụ dưới đây ghi một quyết định phê duyệt cho một bước của workflow. Nó không mặc định một quyết định đồng nghĩa toàn bộ đề nghị đã đủ mọi cấp duyệt.

~~~java
ApprovalResult approve(AuthContext auth, ApproveCommand cmd) {
    String fingerprint = fingerprint(
        cmd.requestId(), cmd.requestRevision(),
        cmd.approvalSlot(), cmd.leafGrantId()
    );

    return tx.required(connection -> {
        IdempotencyDecision key = idem.acquire(
            connection, auth, "APPROVE_PURCHASE",
            cmd.idempotencyKey(), fingerprint
        );

        if (key.hasResult()) {
            authorization.checkResultAccess(auth, key.originalResult());
            return key.originalResult();
        }

        DecisionContext context = delegation.lockDecisionContext(
            connection, auth, cmd.leafGrantId(),
            cmd.requestId(), cmd.approvalSlot()
        );

        PurchaseRequest request = context.request();
        request.requireRevision(cmd.requestRevision());
        request.requireApprovalStepOpen(cmd.approvalSlot());

        context.requireActorIsLeafGrantee(auth.principal());
        context.requireCurrentRootAuthority();
        context.requireValidStructureAndDepth();

        Money amount = pricing.verifiedAmountFor(request);
        Instant t = timeSource.nowAfterLocks(connection);

        context.requireEveryGrantActiveAt(t);
        context.requireEveryConstraint(
            "APPROVE_PURCHASE", request, amount
        );
        approvalPolicy.requireSeparationOfDuties(
            auth.principal(), context.rootPrincipal(),
            context.path(), request, cmd.approvalSlot()
        );

        usage.recordDecisionIfAllowed(
            connection, context, request, amount, t
        );

        ApprovalDecision decision = approvals.insertUnique(
            connection, request, cmd.approvalSlot(),
            auth.principal(), context.rootPrincipal(),
            context.pathEvidence(), t
        );

        workflow.applyApproval(connection, request, decision);
        return idem.complete(
            connection, key, ApprovalResult.recorded(decision.id())
        );
    });
}
~~~

Đây là mã giả; tx, delegation, usage và các API khác là abstraction cần triển khai. Những điều kiện đi kèm:

- Tất cả thao tác dữ liệu liên quan dùng cùng connection và transaction.
- tx.required chỉ đưa kết quả thành công ra ngoài sau commit.
- lockDecisionContext xác định và bảo vệ đường, quyền gốc, đối tượng, quota theo giao thức đã chọn.
- requireCurrentRootAuthority kiểm tra cả quyền hiện hành và quyền được ủy quyền cho hành động này.
- requireEveryConstraint kiểm tra mọi mắt xích, không chỉ hạn mức lá.
- Money có đơn vị tiền tệ rõ ràng; không so số tiền khác đơn vị bằng một phép min.
- insertUnique có ràng buộc nghiệp vụ phù hợp, chẳng hạn không tạo hai quyết định cho cùng một approval slot của cùng revision.
- workflow.applyApproval tính lại tiến trình theo chính sách; client không tự đặt trạng thái APPROVED.
- Nếu ghi quyết định thất bại, cập nhật quota trước đó cũng rollback.
- Không gọi một dịch vụ bên ngoài chậm trong lúc đang giữ khóa của đường.

Trong hệ thống nhiều tầng phê duyệt, ràng buộc duy nhất theo slot chưa đủ để chứng minh độc lập giữa các slot. Chính sách còn phải kiểm tra nguồn thẩm quyền và danh tính của các quyết định đã có.

### 9.4. Idempotency không thay kiểm tra nghiệp vụ

Nếu commit thành công nhưng client mất phản hồi, cùng key và cùng nội dung phải trả decision_id cũ. Không ghi thêm một quyết định hay trừ quota thêm lần nữa.

Nếu client dùng key mới, ràng buộc theo đối tượng, revision và approval slot vẫn phải ngăn tác động trùng.

Nếu transaction bị rollback rồi retry, phải kiểm tra lại đường, quyền gốc, trạng thái và thời gian. Không giữ lại một biến authorized = true từ lần trước.

Kết quả phát lại chỉ mô tả một quyết định đã commit. Nó không cấp thêm quyền dùng chuỗi cho một thao tác mới.

## 10. Hạn mức theo lần và quota dùng chung

### 10.1. Cấp nhiều grant con không tạo thêm ngân sách

Trần 25 triệu của D2 là trần mỗi đề nghị trong ví dụ. Nó không tự cho biết tổng giá trị C được duyệt trong ngày.

Giả sử chính sách bổ sung một quota 50 triệu mỗi ngày cho các quyết định đi qua D1. B tạo hai grant con, mỗi grant có trần mỗi lần 40 triệu. Nếu mỗi người nhận duyệt một đề nghị 30 triệu, từng lần đều dưới 40 triệu nhưng tổng 60 triệu vượt quota của D1.

Cần kiểm tra:

~~~text
mỗi quyết định thỏa trần của mọi cấp
AND tổng mới không vượt quota chung của D1
AND thỏa mọi quota khác được chính sách áp dụng
~~~

Không cấp cho mỗi child một bản sao quota 50 triệu độc lập rồi bỏ kiểm tra ancestor.

### 10.2. Cập nhật từng quota áp dụng trong cùng transaction

SQL minh họa cho một hàng quota đã được xác định từ chính sách và đường:

~~~sql
UPDATE delegation_usage
SET used_value = used_value + :decision_value
WHERE tenant_id = :tenant_id
  AND quota_scope_id = :quota_scope_id
  AND period_id = :period_id
  AND metric = :metric
  AND used_value <= limit_value
  AND :decision_value <= limit_value - used_value;
~~~

decision_value phải hợp lệ, không âm và nằm trong miền tính toán được hỗ trợ. Câu lệnh chỉ có hiệu lực khi ảnh hưởng đúng một hàng; hàng không tồn tại cần được khởi tạo theo giao thức có khóa duy nhất, không coi là quota vô hạn.

Nếu đường chịu nhiều quota, mọi cập nhật quota và quyết định phải cùng commit hoặc rollback. Trường hợp một quota còn đủ nhưng quota tiếp theo hết thì không để lại phần đã trừ.

Phải phân biệt các metric: tổng giá trị quyết định phê duyệt không mặc định là số tiền đã thanh toán. Quy tắc đếm, kỳ và cách hoàn trả cần được định nghĩa cho đúng nghiệp vụ.

### 10.3. Tránh reset hoặc đếm sai

Quota scope và period phải do máy chủ xác định. Client không được đổi ngày, timezone, parent grant hoặc root principal để tạo một bộ đếm mới.

Nếu nhiều nguồn ràng buộc cùng trỏ đến một hàng quota, chuẩn hóa tập khóa để cập nhật hàng đó theo đúng số lần chính sách yêu cầu. Không vô tình trừ hai lần cùng một quota vì nó xuất hiện dưới hai nhãn.

Ngược lại, hai grant khác nhau cùng phụ thuộc một quota gốc không được chia thành hai bộ đếm gốc độc lập.

Thu hồi hoặc cấp lại grant không tự hoàn quota đã dùng. Nếu nghiệp vụ cho giải phóng một khoản đã ghi, thao tác đó phải gắn đúng quyết định và có cơ chế chống hoàn lặp.

## 11. Tách biệt nhiệm vụ trong chuỗi ủy quyền

### 11.1. Đổi actor không luôn tạo được người kiểm tra độc lập

Giả sử A tạo đề nghị rồi ủy quyền cho B phê duyệt. B là actor khác, nhưng quyết định vẫn dựa trên thẩm quyền của A.

Nếu chính sách yêu cầu người tạo không được tự cấp nguồn quyền phê duyệt cho đề nghị của mình, việc A → B không làm đề nghị trở nên độc lập. Kiểm tra chỉ actor != creator là thiếu.

Tùy chính sách, cần xét:

- Danh tính actor thực.
- Danh tính gốc được đại diện.
- Người tạo, người hưởng lợi hoặc người yêu cầu.
- Các chủ thể trung gian khi quy tắc xung đột yêu cầu.
- Các quyết định phê duyệt khác đã có.

Không mặc định mọi ancestor là người tạo hoặc người hưởng lợi. Mối quan hệ phải lấy từ dữ liệu thật và điều kiện phải được chính sách quy định.

### 11.2. Hai người nhận có thể vẫn là một nguồn thẩm quyền

A ủy quyền cho B và C. B duyệt slot thứ nhất, C duyệt slot thứ hai.

Nếu chính sách yêu cầu hai người thao tác khác nhau, cần kiểm tra danh tính tương ứng. Nếu chính sách yêu cầu hai nguồn thẩm quyền độc lập, hai quyết định cùng dựa vào A chưa đủ.

Bởi vậy, audit và dữ liệu quyết định cần giữ root authority principal hoặc định danh nguồn quyền liên quan, không chỉ actor.

Không cho một chủ thể chia quyền thành nhiều grant con để tạo ra nhiều “phiếu đồng ý” độc lập từ cùng một nguồn.

### 11.3. Quyền không được ủy quyền

Một số hành động có thể buộc người có thẩm quyền thực hiện trực tiếp hoặc đi qua một luồng bổ sung. Ví dụ, chính sách có thể cấm ủy quyền quyền thay đổi chính cơ chế ủy quyền hoặc quyền duyệt một loại ngoại lệ đặc biệt.

Hệ thống cần kiểm tra thuộc tính được phép ủy quyền của hành động và phạm vi. Không suy ra “A được làm X” đồng nghĩa “A được giao X cho bất kỳ ai”.

## 12. Thu hồi, hết hạn và hiệu lực dây chuyền

### 12.1. Thu hồi ancestor làm đường mất hiệu lực

Nếu D1 bị thu hồi, D2 không còn dùng được trong mô hình tham chiếu của bài, dù D2 vẫn lưu state = ACTIVE.

Có hai công việc khác nhau:

- **Chặn cấp quyền:** kiểm tra ancestor trong quyết định sử dụng.
- **Dọn hoặc hiển thị trạng thái:** cập nhật descendant, cache, chỉ mục và thông báo.

Công việc dọn có thể chạy nền. Nó không được là điều kiện duy nhất để chặn quyền đã mất nguồn.

Không cần chờ duyệt hết hàng nghìn descendant mới coi D1 bị thu hồi về mặt cấp quyền. Tuy nhiên, mọi đường sử dụng phải thực sự kiểm tra hoặc có cơ chế vô hiệu hóa nhất quán theo hợp đồng.

### 12.2. Thu hồi đua với thao tác

Trong mô hình cùng DB, khi giao thức khóa được tuân thủ:

- Thu hồi commit trước: thao tác đọc lại thấy ancestor không hợp lệ và bị từ chối.
- Thao tác giữ các khóa cần thiết, ghi quyết định và commit trước: thu hồi sau ngăn những quyết định mới.

Một phê duyệt đã commit hợp lệ không tự biến mất khi grant bị thu hồi. Nếu cần hủy hoặc xét lại quyết định cũ, phải có workflow riêng cho đối tượng nghiệp vụ.

Không sửa lịch sử người phê duyệt để làm như quyết định trước đó chưa từng tồn tại.

### 12.3. Hết hạn theo toàn đường

Khoảng thời gian hiệu lực là phần giao các khoảng:

~~~text
effective_from = mốc bắt đầu muộn nhất
effective_until = mốc kết thúc sớm nhất

hợp lệ khi effective_from <= t < effective_until
~~~

Nếu phần giao rỗng thì không có thời điểm nào dùng được đường đó.

Đúng tại điểm kết thúc là hết hạn. Lấy thời gian chuẩn sau khi có các khóa cần thiết; không dùng giờ client hoặc giờ đã đọc trước khi chờ khóa.

Worker chưa chuyển một grant sang EXPIRED không làm thời hạn kéo dài. Ngược lại, một token con không được có hiệu lực dài hơn giới hạn được phép của đường cha.

### 12.4. Cache và nhiều dịch vụ

Nếu mỗi service cache đường quyền trong 10 phút, thu hồi trong DB không tự chặn mọi service ngay lập tức.

Phải chọn rõ mức bảo đảm:

- Tra cứu trạng thái chuẩn khi quyết định có tác động.
- Hoặc dùng cơ chế version, invalidation và kiểm tra độ mới đáp ứng hợp đồng.
- Hoặc chấp nhận một cửa sổ hiệu lực còn lại được quy định rõ của bằng chứng độc lập.

Không hứa thu hồi tức thời nếu kiến trúc chỉ có token tự chứa và không có kênh kiểm tra thu hồi tương ứng.

Khi không xác minh được dữ liệu bắt buộc, không mặc định dùng bản cache cũ như thể còn chắc chắn hợp lệ. Hành vi khi mất kết nối phải phù hợp mức rủi ro và hợp đồng cấp quyền.

## 13. Quyết định đã ghi và công việc bất đồng bộ

Giả sử C đã ghi một quyết định phê duyệt hợp lệ, đồng thời ghi outbox. Consumer xử lý sự kiện sau khi D1 bị thu hồi.

Cần phân biệt:

- Consumer đang thực hiện hệ quả của một quyết định đã commit.
- Consumer đang xin một quyền mới để thực hiện một hành động mới.

Trường hợp đầu cần xác minh sự kiện gắn với quyết định thật và chống xử lý trùng. Trường hợp sau phải đánh giá quyền hiện hành theo chính sách.

Nếu hành động ngoài hệ thống chỉ được thực hiện khi chuỗi vẫn còn hiệu lực tại lúc gửi, phải mô hình hóa thêm điều kiện đó. Không mặc định thời điểm phê duyệt và thời điểm thực thi là cùng một instant.

Bằng chứng quyết định nên giữ:

- Actor, root principal và đường được dùng.
- Phiên bản đối tượng, hành động và phạm vi.
- Nội dung hoặc digest thích hợp.
- Thời điểm quyết định.
- Phiên bản chính sách.
- Định danh quyết định và outbox liên quan.

Retry consumer không được phát sinh một phê duyệt mới hoặc tự tạo một đường ủy quyền thay thế. Outbox không tự bảo đảm hệ thống nhận chỉ gây tác động một lần; nơi nhận vẫn cần idempotency hoặc cơ chế tương đương.

Với tác vụ dài đang giữ tài nguyên, thu hồi grant còn đặt ra câu hỏi có cần dừng tác vụ đang chạy hay chỉ chặn tác vụ mới. Đó là hợp đồng thực thi riêng; việc ghi REVOKED trong DB không tự thu hồi quyền truy cập kỹ thuật của một worker đã nhận tài nguyên.

## 14. Những thiết kế dễ tạo đường leo thang quyền

| Thiết kế | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Chỉ kiểm tra grant lá | Bỏ qua parent đã thu hồi hoặc giới hạn gốc | Kiểm tra toàn đường tại lúc dùng |
| Hợp quyền của mọi grant | Ghép thành quyền chưa ai cấp | Chọn một đường hoàn chỉnh, lấy giao ràng buộc |
| Con tự đặt hạn mức lớn hơn cha | Mở rộng quyền qua ủy quyền lại | Kiểm tra quan hệ thu hẹp khi cấp và khi dùng |
| Cho parent_id thay đổi | Đổi nguồn quyền sau khi được cấp | Định nghĩa bất biến hoặc phiên bản cố định |
| Token đúng chữ ký là cho phép | Bỏ qua thu hồi, quota và điều kiện đối tượng | Xác minh đầy đủ theo hợp đồng |
| Tin actingAs hoặc rootPrincipal từ client | Giả mạo nguồn thẩm quyền | Tạo context từ xác thực và grant máy chủ |
| Mỗi child có quota gốc độc lập | Nhân bản tổng hạn mức | Dùng quota ancestor chung |
| Hai account khác nhau là hai người duyệt | Có thể cùng người hoặc cùng nguồn quyền | Kiểm tra danh tính và điều kiện độc lập |
| Thu hồi rồi chờ worker sửa con | Quyền tiếp tục dùng trong khoảng trễ | Chặn qua ancestor hoặc cơ chế nhất quán tương đương |
| Cấp lại grant làm reset quota | Né giới hạn theo kỳ | Quota scope theo chính sách, không chỉ theo ID mới |
| Ghi log như thể root trực tiếp thao tác | Mất actor thật và trách nhiệm | Lưu actor, root và đường |
| Duyệt một bước rồi đặt toàn bộ workflow hoàn tất | Bỏ qua những cấp còn lại | Tính chuyển trạng thái theo đầy đủ chính sách |

## 15. Kiểm thử các tình huống tấn công logic

### 15.1. Ma trận theo ví dụ A → B → C

Giả sử quyền gốc và các grant còn hiệu lực, đúng đối tượng và chưa vướng điều kiện khác.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| C duyệt 25 triệu tại D01 | Có thể được phép nếu đủ mọi điều kiện |
| C duyệt 25 triệu cộng một đơn vị tiền chuẩn | Bị chặn bởi D2 |
| C duyệt đề nghị D02 | Bị chặn vì ngoài phạm vi |
| Client khai tổng 20 triệu, DB ghi 30 triệu | Dùng giá trị thật và từ chối |
| C khai actingAs = A | Không được nâng lên hạn mức của A |
| Actor khác C dùng leaf D2 | Bị từ chối vì sai người nhận ở lá |
| B cấp con 80 triệu khi D1 chỉ 60 triệu | Bị từ chối khi phát hành |
| D2 có expires_at sau D1 | Bị từ chối theo quy tắc cấp con của bài |
| C cố tạo D3 khi remaining_hops = 0 | Không được ủy quyền tiếp |
| Grant con đổi tenant hoặc root_authority_id | Bị từ chối |
| Parent thiếu hoặc grantor không khớp | Không hình thành đường hợp lệ |
| A → B → C → A | Bị chặn theo quy tắc cấm chu trình |
| Chuỗi vượt độ sâu tối đa | Dừng có giới hạn, không duyệt vô hạn |
| D1 bị thu hồi, D2 vẫn ACTIVE | C không dùng được D2 |
| Quyền gốc của A mất APPROVE_PURCHASE | C không tiếp tục dùng quyền đó |
| Trần quyền gốc giảm xuống 20 triệu | C không được duyệt 25 triệu |
| Đúng tại deadline sớm nhất | Bị từ chối vì hết hạn |
| Chờ khóa qua deadline | Lấy thời gian mới và từ chối |
| Hai request đồng thời dùng quota chung | Tổng không vượt quota ancestor |
| Cấp thêm child hoặc đổi key | Không reset quota gốc |
| Retry sau mất phản hồi | Cùng decision_id, không trừ quota lần hai |
| Retry sau rollback | Đánh giá lại đường và thời gian hiện hành |
| Key mới cho cùng approval slot | Không ghi thêm quyết định hữu hiệu |
| A là người tạo đề nghị và C đại diện A | Áp dụng quy tắc xung đột theo actor và nguồn quyền |
| B, C duyệt hai slot cùng nguồn A | Không được coi là hai nguồn độc lập nếu chính sách yêu cầu |
| Có hai đường không hoàn chỉnh | Không ghép thành một quyền hoàn chỉnh |
| Một đường khác đủ điều kiện | Có thể chọn theo chính sách, với đúng quota và audit |
| Token đúng chữ ký nhưng parent đã thu hồi | Không cho qua nếu hợp đồng đòi trạng thái hiện hành |

### 15.2. Kiểm thử thu hồi đua với sử dụng

Dùng hai connection trên hệ quản trị mục tiêu:

1. Transaction A chuẩn bị ghi phê duyệt theo D2.
2. Transaction B thu hồi D1.
3. Điều phối để từng transaction lần lượt có được khóa quyết định trước.
4. Cho transaction đầu commit, sau đó transaction còn lại tiếp tục.
5. Kiểm tra kết quả và dữ liệu đã commit.

Các kết quả phải phù hợp thứ tự đã xác lập. Không có trường hợp thao tác dùng một đường đã bị thu hồi trước điểm quyết định nhưng vẫn thành công do đọc một bản sao cũ không được bảo vệ.

Kiểm thử tương tự cần thực hiện với thay đổi quyền gốc, quota, trạng thái đề nghị và revision.

### 15.3. Kiểm thử cấp con đua với thu hồi

Một tình huống khác:

~~~text
B bắt đầu cấp D2 dựa trên D1.
A đồng thời thu hồi D1.
~~~

Nếu thu hồi thắng theo giao thức, B không được phát hành một grant con có thể sử dụng như thể parent vẫn còn quyền. Nếu cấp con hoàn tất trước, D2 vẫn phải mất hiệu lực sử dụng khi D1 bị thu hồi sau đó.

Không coi việc D2 đã được tạo là lý do để nó tách khỏi ancestor.

### 15.4. Kiểm tra invariant sau commit

Ngoài phản hồi API, cần truy vấn dữ liệu bằng ảnh chụp nhất quán để xác nhận:

- Mỗi quyết định trỏ đến đúng actor, root và đường đã sử dụng.
- Phiên bản đối tượng và nội dung được quyết định khớp audit.
- Không có hai quyết định hữu hiệu cho cùng slot nếu chính sách chỉ cho một.
- Quota khớp các quyết định đang được tính theo chính sách.
- Không còn cập nhật quota riêng lẻ sau rollback.
- Một quyết định bị từ chối không làm workflow tiến lên bước sau.
- Parent và định nghĩa grant không bị thay đổi ngoài quy trình.

Unit test có thể kiểm tra các predicate và đường rẽ. Mock repository không chứng minh khóa hàng, ràng buộc duy nhất, thời gian sau chờ khóa và rollback hoạt động đúng trên DB thật.

Dùng barrier hoặc latch để điều phối các điểm cạnh tranh. Không chỉ sleep ngẫu nhiên rồi kết luận không có race condition.

## 16. Audit, quan sát và điều tra

Một quyết định dùng delegation chain nên lưu đủ để trả lời:

- Ai thực sự thực hiện?
- Người đó dựa trên nguồn thẩm quyền nào?
- Qua những grant và chủ thể trung gian nào?
- Hành động gì trên đối tượng và revision nào?
- Những scope, trần tiền, quota và điều kiện độc lập nào đã được áp dụng?
- Tại instant nào và theo phiên bản chính sách nào?
- Quyết định có phải replay của một lần đã commit không?

Audit có thể lưu danh sách định danh grant cùng phiên bản định nghĩa bất biến hoặc bằng chứng tương đương. Một path_digest hỗ trợ kiểm tra toàn vẹn, nhưng không đủ để giải thích lịch sử nếu hệ thống đã xóa mọi định nghĩa mà digest tham chiếu.

Không chỉ lưu tên hiển thị hiện tại của người dùng; tên đó có thể đổi. Đồng thời không ghi token xác thực, bí mật ký hoặc dữ liệu không cần thiết vào log.

Những tín hiệu hữu ích:

- Tần suất cấp lại và độ sâu chuỗi theo nhóm.
- Lần thử cấp con vượt phạm vi hoặc vượt độ sâu.
- Request dùng ancestor đã thu hồi.
- Thao tác sát trần và số lượng child tăng nhanh.
- Nhiều đường từ cùng nguồn dùng để né quota hoặc kiểm tra độc lập.
- Tỷ lệ sai tenant, sai actor lá và sai đối tượng.
- Độ trễ vô hiệu hóa cache so với hợp đồng thu hồi.
- Xung đột, retry và thời gian chờ khóa tại điểm quyết định.
- Sai lệch giữa quota và quyết định.

Các tín hiệu chỉ dẫn điều tra, không tự chứng minh mọi chuỗi dài hoặc nhiều grant là hành vi xấu.

Metric nên được tổng hợp theo nhóm phù hợp. Tránh dùng mọi grant_id hoặc request_id làm nhãn có số lượng giá trị không giới hạn; dùng log có kiểm soát để điều tra một đường cụ thể.

## 17. Checklist áp dụng

- Actor, root authority principal và business subject đã được phân biệt chưa?
- Quyền gốc có được phép ủy quyền cho hành động này không?
- Client chỉ cung cấp tham chiếu hay có thể tự khai toàn bộ đường?
- Parent và định nghĩa bảo mật của grant có bất biến hoặc gắn phiên bản cố định không?
- Grantor của con có khớp người nhận của parent không?
- Quyền con có được kiểm tra thu hẹp theo mọi chiều không?
- can_redelegate, remaining_hops và độ sâu tuyệt đối có ngữ nghĩa nhất quán không?
- Có phát hiện parent thiếu, chu trình, sai tenant và sai nguồn quyền không?
- Tại lúc dùng, hệ thống có kiểm tra toàn bộ ancestor và quyền gốc hiện hành không?
- Quyền hiệu lực có được tính theo một đường hoàn chỉnh thay vì hợp nhiều mảnh không?
- Hành động có được xét trên đối tượng, giá và revision thật phía máy chủ không?
- Tách biệt nhiệm vụ có tính actor, nguồn thẩm quyền và quan hệ liên quan không?
- Quota ancestor có dùng chung, cập nhật nguyên tử và không bị reset khi cấp con không?
- Quyết định, quota, workflow và idempotency có cùng ranh giới commit không?
- Thu hồi đua với sử dụng có một thứ tự quyết định được bảo vệ không?
- Cache, token và nhiều dịch vụ có đáp ứng đúng hợp đồng thu hồi không?
- Retry và tác vụ nền có tránh ghi hoặc gây tác động lần hai không?
- Audit có dựng lại được ai đã làm gì bằng đường quyền nào không?

Một chuỗi ủy quyền an toàn phải giữ được nguồn quyền và giới hạn qua mọi mắt xích. Người nhận ở cuối chỉ được dùng phần quyền còn hiệu lực trên toàn đường, trong đúng ngữ cảnh nghiệp vụ và với trách nhiệm có thể truy vết.
