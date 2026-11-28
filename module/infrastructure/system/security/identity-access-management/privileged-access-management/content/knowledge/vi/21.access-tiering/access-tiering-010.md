# Kiểm tra đường đi leo thang trong mô hình phân tầng truy cập

## 1. Đường đi leo thang là gì?

Trong kiểm soát truy cập đặc quyền, **đường đi leo thang** là một chuỗi quan hệ cho phép chủ thể có phạm vi quyền ban đầu tác động tới một quyền, danh tính hoặc tài nguyên mạnh hơn ngoài ý định của thiết kế.

Chuỗi này không nhất thiết bắt đầu bằng một lỗ hổng phần mềm. Nó có thể được hình thành từ các quyền hợp lệ khi kết hợp với nhau:

~~~text
Tài khoản vận hành server
  → được sửa công cụ triển khai
  → công cụ có thể chạy tác vụ trên thành phần danh tính
  → tác vụ có quyền thay đổi miền tin cậy.
~~~

Mỗi quan hệ riêng có thể được coi là thuận tiện cho vận hành. Khi ghép lại, chúng có thể làm mất ranh giới giữa quản trị server và quản trị control plane.

**Kiểm tra đường đi leo thang** là xác định các chuỗi đó, đánh giá điều kiện để chúng có hiệu lực, tìm bằng chứng và xác minh biện pháp chặn trong phạm vi được phép.

Mục tiêu của bài học là hỗ trợ đánh giá phòng thủ trong PAM và access tiering. Kết quả cần giúp trả lời:

- Ai có thể tác động tới thành phần nào?
- Qua những quyền trực tiếp hoặc gián tiếp nào?
- Điều kiện nào phải đồng thời đạt?
- Ranh giới tier bị vượt ở đâu?
- Có bằng chứng nào cho từng cạnh của đường?
- Cần thay đổi điều gì và kiểm chứng ra sao?

## 2. Những khái niệm phải tách rõ

| Khái niệm | Ý nghĩa | Không tự chứng minh |
|---|---|---|
| Có kết nối mạng | Có thể tiếp cận endpoint theo một luồng | Có quyền xác thực hoặc quản trị |
| Có credential | Có khả năng sử dụng một bằng chứng xác thực | Credential được chấp nhận ở mọi target |
| Có quyền đọc | Có thể lấy một loại dữ liệu | Có thể thay đổi hoặc thực thi mã |
| Có quyền cấu hình | Có thể sửa những thuộc tính cụ thể | Mọi thuộc tính đều tác động tới đặc quyền |
| Có quyền quản trị host | Có khả năng điều khiển host trong phạm vi thực tế | Đã kiểm soát mọi hệ thống liên quan |
| Đường tiềm năng | Có chuỗi quan hệ cần được đánh giá | Mọi điều kiện đã được xác nhận |
| Đường xác nhận theo cấu hình | Các quyền và điều kiện liên quan có bằng chứng đủ trong phạm vi đánh giá | Đã diễn ra khai thác hoặc mọi hiệu ứng runtime đã được thử |
| Không tìm thấy đường | Dữ liệu đã thu thập chưa cho ra chuỗi phù hợp | Toàn hệ thống không có đường nào |

Không đồng nhất “có một chuỗi trên sơ đồ” với “đã chứng minh có thể chiếm hệ thống”. Cũng không coi thiếu bằng chứng là một biện pháp chặn.

Trong báo cáo, cần giữ được sự khác biệt giữa điều kiện bị từ chối, điều kiện chưa được kiểm tra và dữ liệu không thu thập được.

## 3. Xác định ranh giới tier và mục tiêu cần bảo vệ

### 3.1. Tier phản ánh phạm vi điều khiển

Tiering không chỉ là đặt máy chủ vào các nhóm có tên khác nhau. Cần xác định những thành phần có thể thay đổi danh tính, policy, credential và nguồn thực thi nào.

Ví dụ về các phạm vi cần xem xét:

- Miền danh tính và nguồn phát hành bằng chứng xác thực.
- PAM, vault và dịch vụ ký.
- Nền tảng quản lý endpoint hoặc máy trạm admin.
- Hypervisor và hạ tầng chứa thành phần nhạy cảm.
- Công cụ triển khai, image và pipeline.
- Backup, khôi phục và khóa bảo vệ dữ liệu.
- Server ứng dụng, database và dữ liệu nghiệp vụ.

Một máy chủ mang tên monitoring vẫn có thể là thành phần ảnh hưởng cao nếu hệ thống quản lý của nó được phân phối mã tới domain controller.

### 3.2. Chọn điểm xuất phát và đích

Một đợt đánh giá nên nêu rõ:

~~~text
Điểm xuất phát:
  chủ thể hoặc phạm vi quyền được giả định đã có.

Đích:
  danh tính, quyền hoặc tài nguyên ngoài phạm vi cần bảo vệ.

Ranh giới:
  quan hệ điều khiển nào không được phép tồn tại theo thiết kế.

Phạm vi:
  môi trường, thời điểm dữ liệu và các hệ thống đã kiểm tra.
~~~

Ví dụ, điểm xuất phát là nhóm server operator của ứng dụng A; đích là khả năng sửa policy xác thực của miền danh tính.

Không chỉ chọn các đích mang nhãn “administrator”. Quyền đọc kho secret hoặc dữ liệu nhạy cảm có thể là mục tiêu ảnh hưởng lớn dù không tạo một tài khoản admin mới.

### 3.3. Xem xét cả người dùng và workload

Điểm xuất phát có thể là tài khoản cá nhân, service identity, runner, connector hoặc công cụ quản lý.

Workload có credential và dependency khác con người. Không áp giả định rằng mọi cạnh đều cần người dùng thực hiện MFA tương tác.

## 4. Lập đồ thị quyền

### 4.1. Node và cạnh

Một đồ thị có thể dùng các loại node:

| Loại node | Ví dụ |
|---|---|
| Chủ thể | Người dùng, service identity, tài khoản kỹ thuật |
| Nhóm hoặc role | Nhóm quản trị, role triển khai |
| Tài nguyên | Server, ứng dụng, API, control plane |
| Credential hoặc khả năng ký | Khóa, quyền lấy secret, danh tính liên kết |
| Thành phần thực thi | Agent, runner, gateway |
| Policy hoặc artifact | Cấu hình, script, image, gói triển khai |
| Nguồn tin cậy | IdP, CA, kho inventory hoặc hệ thống posture |

Cạnh có hướng diễn tả một khả năng cụ thể:

~~~text
A là thành viên nhóm B.
B có quyền sửa thuộc tính X của C.
C phân phối artifact D tới agent E.
E thực thi tác vụ với quyền F.
A được lấy credential G.
G được chấp nhận cho account H trên target I.
~~~

Không dùng nhãn “có quyền trên” cho mọi cạnh. Nó che mất khác biệt giữa đọc, sửa lịch, sửa mã thực thi và sửa quyền cấp cho người khác.

### 4.2. Gắn điều kiện và bằng chứng

Một cạnh cần có các dữ kiện như:

~~~text
Nguồn và đích bằng định danh ổn định.
Loại quan hệ và thao tác cụ thể.
Phạm vi tài nguyên.
Điều kiện cần thiết.
Nguồn dữ liệu và thời điểm quan sát.
Phiên bản cấu hình hoặc policy liên quan.
Bằng chứng hoặc tham chiếu có thể đối chiếu.
Trạng thái xác minh.
Owner chịu trách nhiệm.
~~~

Ví dụ, “được sửa job” cần làm rõ là sửa thời gian chạy hay sửa nội dung được thực thi. Chỉ một trong hai có thể phù hợp với đường đang đánh giá.

### 4.3. Đừng ghép các cạnh không tương thích

Một cạnh chỉ hợp lệ trong môi trường thử nghiệm không tự ghép với quyền chỉ tồn tại ở production. Một quyền đã hết hạn không tự kết hợp với một grant mới xuất hiện sau đó.

Cũng cần phân biệt chủ thể. Nếu bước tiếp theo yêu cầu quyết định của một người độc lập không bị chủ thể ban đầu điều khiển, không được tự coi cạnh đó đã đi qua.

Đồ thị phải giữ điều kiện theo thời gian, phạm vi và thẩm quyền, thay vì chỉ nối các tên có liên quan.

## 5. Những nhóm quan hệ cần kiểm tra

### 5.1. Group, role và ủy quyền

Kiểm tra tư cách thành viên trực tiếp, lồng nhau và những quyền cho phép thay đổi membership hoặc quyền của đối tượng khác.

Một tài khoản có quyền sửa nhóm cấp đặc quyền có thể có ảnh hưởng lớn hơn một thành viên chỉ sử dụng quyền sẵn có. Cần xem cả người quản lý nhóm và người được nhóm cấp quyền.

Không mặc định mọi policy engine có cùng quy tắc kế thừa, deny hoặc cách kết hợp identity policy với resource policy. Phải dùng semantics của hệ thống đang được đánh giá.

### 5.2. Quản lý danh tính và phục hồi

Các quyền như reset credential, thêm authenticator, đổi cấu hình federation hoặc thay nguồn xác thực cần được đưa vào đồ thị.

Một quy trình phục hồi có thể trở thành đường cấp quyền nếu người xử lý được thay thế điều kiện xác thực của danh tính nhạy cảm mà không có kiểm soát tương ứng.

Không chỉ hỏi ai đăng nhập được bằng mật khẩu hiện tại. Cần hỏi ai có thể thay đổi cách đăng nhập hoặc người được chấp nhận là chủ thể đó.

### 5.3. Secret, token và dịch vụ ký

Cần biết ai có thể đọc secret, gọi chức năng ký, sửa policy vault, thay mapping credential hoặc tạo một yêu cầu phát hành mới.

Không cần lấy secret thật để xác minh quyền đọc trong mọi trường hợp. Có thể dùng effective permissions, cấu hình và đối tượng thử được cho phép.

Một quyền lấy secret chưa chứng minh đường hoàn tất: vẫn cần biết credential còn hiệu lực, được chấp nhận ở đâu và có điều kiện bổ sung nào.

### 5.4. Thực thi và artifact

Kiểm tra quyền đối với script, job, image, plugin và nguồn gói có thể được thực thi bởi thành phần mạnh hơn.

Cần xác định liệu chủ thể có sửa được nội dung thực thi, nguồn tải, tham số quan trọng hoặc bước kiểm tra hay chỉ sửa metadata không ảnh hưởng tác vụ.

Nếu có bước ký hoặc phê duyệt độc lập, phải đánh giá bước đó có thực sự ràng buộc đúng artifact và phiên bản được triển khai không.

### 5.5. Quản lý hạ tầng và phục hồi

Hypervisor, backup, công cụ quản lý endpoint và console hỗ trợ có thể điều khiển hoặc lấy dữ liệu của hệ thống khác.

Quyền xem trạng thái khác với quyền lấy snapshot, phục hồi dữ liệu hoặc phân phối lệnh. Mỗi quyền cần được thể hiện đúng.

Một nhóm quản trị “server chung” có thể vượt tier nếu nó điều khiển nền tảng chứa hoặc quản lý control plane nhạy cảm.

### 5.6. Phiên và môi trường nguồn

Một môi trường thấp hơn có thể ảnh hưởng danh tính cao nếu danh tính đó được sử dụng ở đó. Cần xem vị trí đăng nhập, credential delegation, session artifact, agent forwarding và quyền quản lý máy nguồn.

Không kết luận mọi giao thức đều để lại cùng một loại credential. Cần đánh giá cơ chế cụ thể và khả năng điều khiển phiên ngay cả khi secret không được sao chép.

## 6. Thu thập dữ liệu có phạm vi và nguồn gốc

### 6.1. Bắt đầu từ câu hỏi kiểm tra

Ví dụ:

> Nhóm vận hành ứng dụng A có thể thay đổi hoặc sử dụng quyền điều khiển miền danh tính qua công cụ quản lý nào?

Từ câu hỏi đó, xác định hệ thống cần đọc cấu hình, loại quan hệ cần lấy và quyền của người thu thập.

Không cần quét mọi endpoint hoặc thử credential ở mọi nơi để bắt đầu lập đồ thị. Dữ liệu inventory, group, ACL, policy và cấu hình quản lý thường là đầu vào quan trọng.

### 6.2. Phân biệt thiếu quyền đọc với không tồn tại quyền

Một collector có thể không nhìn thấy role, group lồng nhau, policy ở hệ thống khác hoặc quyền cục bộ.

Nếu dữ liệu bị giới hạn, ghi rõ:

~~~text
Đã thu thập:
  các hệ thống và loại quan hệ xác định.

Chưa thu thập hoặc không đọc được:
  các nguồn có thể ảnh hưởng kết luận.

Thời điểm:
  snapshot và khoảng mà dữ liệu có thể đã thay đổi.
~~~

Một collector trả danh sách rỗng do thiếu quyền không được hiểu như danh sách quyền thực tế rỗng.

### 6.3. Bảo vệ dữ liệu đánh giá

Đồ thị quyền có thể tiết lộ cấu trúc đặc quyền và các điểm yếu của tổ chức. Cần quản lý quyền truy cập, artifact xuất và vòng đời theo mục đích.

Không lưu private key, mật khẩu, token đầy đủ hoặc dữ liệu credential không cần thiết. Dùng định danh đối tượng, fingerprint phù hợp và tham chiếu bằng chứng.

Một hash của tệp cấu hình giúp đối chiếu nội dung đã thu thập, nhưng không tự chứng minh nguồn cấu hình là đáng tin nếu nguồn và quy trình thu thập chưa được xác minh.

## 7. Tìm đường và đánh giá tính khả thi

### 7.1. Tìm đường là bước tạo ứng viên

Có thể tìm các chuỗi từ tập chủ thể xuất phát tới tập đích nhạy cảm. Tuy nhiên, kết quả của việc nối cạnh chỉ là ứng viên cho đến khi đánh giá điều kiện.

Một logic minh họa:

~~~text
Khởi tạo các trạng thái từ chủ thể xuất phát.

Với mỗi quan hệ đi ra:
  kiểm tra loại quyền và semantics của hệ thống;
  giữ lại điều kiện, phạm vi và nguồn bằng chứng;
  loại nhánh có điều kiện đã xác nhận là không thể đạt;
  giữ riêng nhánh thiếu dữ liệu là chưa xác định;
  chỉ chuyển sang chủ thể khác khi có căn cứ cho chuyển quyền đó.

Nếu tới đích:
  trả đường cùng các điều kiện và mức xác minh.

Nếu bị giới hạn độ sâu, thời gian hoặc dữ liệu:
  báo giới hạn, không kết luận đã kiểm tra hết.
~~~

Đây là cách diễn giải đánh giá, không phải mã khai thác.

### 7.2. Điều kiện phải có thể cùng tồn tại

Một đường có thể yêu cầu đồng thời:

- Grant còn hiệu lực.
- Credential chưa bị thu hồi.
- Target có thể tiếp cận.
- Phê duyệt độc lập.
- Artifact đúng phiên bản.
- Nguồn thiết bị được chấp nhận.
- Role có quyền tại thời điểm thực thi.

Nếu các điều kiện mâu thuẫn hoặc không thể cùng đạt bởi chủ thể được xét, đường không khả thi theo mô hình đó. Nếu chưa biết, giữ trạng thái chưa xác định.

### 7.3. Đường ngắn nhất chưa chắc ưu tiên nhất

Một đường ít cạnh nhưng bị kiểm soát độc lập tốt có thể ít cấp bách hơn một đường dài hơn, luôn hoạt động và chạm nhiều target.

Ưu tiên cần xem:

- Tác động của đích.
- Độ chắc chắn của các cạnh.
- Số chủ thể có điểm xuất phát đó.
- Điều kiện và khả năng bị phát hiện.
- Phạm vi thường trực hoặc thời hạn.
- Chi phí và tác động của biện pháp khắc phục.

Không dùng riêng số cạnh làm thước đo rủi ro.

## 8. Xác minh bằng cách an toàn và có thể đối chiếu

### 8.1. Ưu tiên cấu hình và quyền hiệu lực

Có thể bắt đầu bằng:

- Đọc policy và ACL liên quan.
- Kiểm tra effective permissions bằng cơ chế được hỗ trợ.
- Đối chiếu group và role theo nguồn có thẩm quyền.
- Xác minh account chạy tác vụ và scope target.
- Kiểm tra quy trình phê duyệt và ràng buộc phiên bản.
- Đối chiếu log hoạt động hợp lệ trước đó.

Một quyền cấu hình được xác nhận chưa tự chứng minh mọi điều kiện runtime. Khi cần, xác minh thêm trong lab hoặc với đối tượng thử thuộc phạm vi được phép.

### 8.2. Thử nghiệm đại diện

Có thể dùng nhóm, artifact hoặc target thử có cùng loại policy để quan sát kết quả, với dữ liệu giả và quyền được giao cho kiểm tra.

Không cần reset credential quản trị thật, lấy secret production hoặc sửa thành phần danh tính chỉ để chứng minh một cạnh khi bằng chứng khác đã đủ cho kết luận trong phạm vi.

Nếu một thử nghiệm có thể thay đổi trạng thái, cần có phạm vi, owner, cách khôi phục và điều kiện dừng được xác định trong quy trình đánh giá.

### 8.3. Ghi rõ mức kết luận

Một bộ nhãn nội bộ có thể là:

| Trạng thái | Ý nghĩa |
|---|---|
| POTENTIAL | Có chuỗi ứng viên, còn điều kiện chưa xác minh |
| CONFIG_VERIFIED | Quyền và điều kiện cấu hình liên quan đã được đối chiếu |
| SAFE_TEST_VERIFIED | Hành vi đại diện được kiểm chứng an toàn trong phạm vi đã nêu |
| BLOCKED_UNDER_TESTED_CONDITIONS | Một điều kiện chặn đã được kiểm chứng với ngữ cảnh xác định |
| UNKNOWN | Thiếu dữ liệu hoặc không thể xác nhận |
| OUT_OF_SCOPE | Không thuộc phạm vi đánh giá hiện tại |

Các nhãn cần dùng nhất quán. SAFE_TEST_VERIFIED ở lab không tự chứng minh mọi cấu hình production giống lab. BLOCKED trong một tình huống không chứng minh các đường thay thế đều bị chặn.

## 9. Ví dụ xuyên suốt: quyền triển khai vượt ranh giới tier

### 9.1. Bối cảnh

Nhóm App-A-Operators chỉ được quản trị member server của ứng dụng A. Thiết kế không cho nhóm này điều khiển thành phần danh tính.

Tuy nhiên, nhóm có một role trên công cụ triển khai chung. Công cụ đó quản lý cả agent của ứng dụng và agent trên một thành phần thuộc control plane danh tính.

Đồ thị ứng viên:

~~~mermaid
flowchart LR
    U["App-A-Operators"] -->|Role được gán| R["Quyền quản lý công cụ triển khai"]
    R -->|Cần xác minh thuộc tính được sửa| J["Job cho control plane"]
    J -->|Phải qua điều kiện phát hành| F["Cổng phát hành"]
    F -->|Nếu được cấp thực thi| A["Agent trên thành phần danh tính"]
    A -->|Quyền hiệu lực cần xác minh| D["Cấu hình miền tin cậy"]
~~~

Sơ đồ chưa kết luận đường có hiệu lực. Hai cạnh quan trọng còn cần xác minh là quyền sửa job và quyền của agent, cùng điều kiện tại cổng phát hành.

### 9.2. Xác minh cạnh quyền cấu hình

Rà soát cần biết role của nhóm có thể:

- Chỉ xem trạng thái job.
- Đổi lịch nhưng không đổi nội dung.
- Đổi artifact hoặc nguồn lấy artifact.
- Thay lệnh hoặc tham số có ảnh hưởng thực thi.
- Đổi tập target hoặc account chạy.
- Sửa hoặc bỏ qua điều kiện phê duyệt.

Mỗi khả năng tạo kết luận khác nhau. Không lấy một nhãn “job administrator” làm bằng chứng đủ cho tất cả.

### 9.3. Xác minh cổng phát hành

Giả sử job bắt buộc một người độc lập phê duyệt đúng artifact và phiên bản. Cần kiểm tra:

1. Người sửa job có tự duyệt được không?
2. Có thể thay approver hoặc sửa rule phê duyệt không?
3. Quyết định có gắn với nội dung thực sự triển khai không?
4. Artifact có thể thay đổi sau khi được duyệt không?
5. Có đường API hoặc job khác không qua cổng đó không?
6. Retry hoặc rollback có sử dụng cùng phạm vi đã duyệt không?

Nếu cổng độc lập thực sự ngăn chủ thể ban đầu đạt bước phát hành trong điều kiện đã kiểm chứng, đây là một điều kiện chặn của đường đó.

Nếu chưa kiểm tra các câu hỏi này, trạng thái là chưa xác định. Không coi biểu tượng “approval required” trên giao diện là bằng chứng hoàn tất.

### 9.4. Xác minh account và agent

Agent có thể chạy với quyền rộng hoặc chỉ được gọi một tập tác vụ hạn chế. Cần xác định quyền thật và khả năng thay cấu hình miền tin cậy.

Không suy rằng mọi agent trên một host nhạy cảm đều có cùng quyền. Cũng không bỏ qua khả năng sửa mã hoặc công cụ mà agent dùng.

Bằng chứng cần nối được từ job tới đúng agent và account, thay vì chỉ thấy hai thành phần cùng có tên tương tự.

### 9.5. Kết luận có phạm vi

Có thể có những kết quả khác nhau:

~~~text
Trường hợp A:
Nhóm chỉ được xem job.
Cạnh sửa nội dung không tồn tại trong dữ liệu đã xác minh.
Đường ứng viên này không hoàn tất theo điều kiện đó.

Trường hợp B:
Nhóm được sửa artifact nhưng không thể phát hành qua cổng độc lập.
Đường bị chặn theo các điều kiện đã kiểm chứng.
Các đường phát hành khác vẫn cần đánh giá.

Trường hợp C:
Nhóm được sửa nội dung và điều kiện phát hành không độc lập như thiết kế.
Account thực thi có quyền tác động control plane.
Có đường điều khiển vượt phạm vi đã xác nhận theo cấu hình.

Trường hợp D:
Không đọc được policy phát hành hoặc account của agent.
Không đủ dữ liệu kết luận đường đã bị chặn hay hoàn tất.
~~~

Các kết luận này không khẳng định đã có người sử dụng đường để tấn công. Muốn xác định hoạt động thực tế cần thêm log và bằng chứng sự kiện.

## 10. Kiểm tra PAM như một phần của đồ thị

PAM kiểm soát đặc quyền nhưng bản thân nó cũng có các quan hệ đặc quyền.

### 10.1. Quyền sử dụng khác quyền cấu hình

Cần phân biệt:

- Được yêu cầu một phiên.
- Được phê duyệt yêu cầu.
- Được sửa entitlement.
- Được thay danh mục target hoặc account mapping.
- Được đọc credential.
- Được sửa policy vault.
- Được cài plugin hoặc quản trị connector.
- Được sửa nơi lưu và quyền truy cập bằng chứng.

Một người chỉ có role vận hành server nhưng được sửa mapping tới credential directory admin có thể tạo ra đường ngoài ý định.

### 10.2. Gateway và connector

Gateway có thể tiếp cận target và sử dụng credential thay người dùng. Quyền điều khiển gateway cần được đưa vào cùng phạm vi đánh giá.

Tách thư mục secret không đủ nếu một vai trò quản trị vẫn có thể sửa mọi policy hoặc gọi mọi khả năng ký.

Một connector dùng chung giữa các tier cần được xem xét về nguồn quản lý, quyền runtime, mạng, plugin và phạm vi secret có thể tiếp cận.

### 10.3. Phê duyệt và JIT

MFA hoặc phê duyệt có thể là điều kiện chặn, nhưng chỉ khi nó áp dụng đúng chủ thể, tác vụ và phạm vi.

Cần hỏi ai có thể sửa workflow, thay approver hoặc tạo grant ngoài luồng. Một người được tự thay điều kiện rồi tự sử dụng quyền không được coi là bị chặn bởi chính điều kiện đó.

JIT giúp giới hạn thời gian nhưng không xóa mọi đường leo thang. Nếu chủ thể luôn có thể tự cấp quyền lại, cần đánh giá khả năng đó như một cạnh độc lập.

### 10.4. Credential và phiên đã tồn tại

Một cạnh đã bị gỡ trong cấu hình cấp mới có thể còn dấu vết hiệu lực ở token, ticket, chứng thư hoặc phiên đang mở.

Đánh giá cần phân biệt:

~~~text
Khả năng nhận quyền mới.
Khả năng tiếp tục dùng quyền đã cấp.
Khả năng dùng credential ngoài PAM.
Hoạt động hoặc thay đổi đã tạo ở target.
~~~

Không kết luận đường đã bị cắt hoàn toàn chỉ vì một grant đã bị xóa khỏi danh sách.

## 11. Chọn biện pháp cắt đường ảnh hưởng

### 11.1. Xử lý quyền hoặc dependency tạo ra đường

Các lựa chọn có thể gồm:

- Tách role quản trị theo phạm vi target.
- Gỡ quyền sửa đối tượng đặc quyền ngoài nhiệm vụ.
- Dùng danh tính và credential riêng.
- Tách runner, agent, gateway hoặc vùng quản lý.
- Giới hạn nơi sử dụng credential.
- Gắn phê duyệt độc lập với đúng artifact và phạm vi.
- Bảo vệ nguồn image và công cụ cập nhật.
- Thu hẹp quyền hiệu lực tại target.
- Giảm thời gian giữ quyền bằng cơ chế phù hợp.

Chọn theo cạnh đã xác nhận và tác động vận hành. Không mở một quy trình thay đổi lớn hơn cần thiết nếu một ủy quyền sai có thể được sửa chính xác.

### 11.2. Không chỉ cắt một đường hiển thị

Nếu nhóm còn một đường khác qua backup hoặc công cụ hỗ trợ, sửa job triển khai không giải quyết tất cả.

Sau thay đổi cần xây lại những phần đồ thị liên quan và kiểm tra đường thay thế. Kết luận phải gắn với dữ liệu và phạm vi đã đánh giá, không tự mở rộng sang toàn hệ thống.

### 11.3. Tránh thay đổi quyền bằng cách gây mất vận hành

Một service identity có thể phục vụ nhiều consumer. Thay hoặc khóa credential cần kế hoạch xác định consumer, kiểm tra hoạt động và phục hồi theo phạm vi.

Không dùng danh tính mạnh hơn để “sửa nhanh” mọi lỗi phát sinh. Cần hiểu quyền nào thực sự còn thiếu và cấp đúng tác vụ.

### 11.4. Ưu tiên cạnh có tác động rộng

Một quyền quản lý trung tâm có thể nằm trên nhiều đường tới nhiều đích. Xử lý cạnh đó có thể giảm nhiều quan hệ vượt tier hơn việc sửa từng server riêng.

Tuy nhiên, cần xem tác động và khả năng phục hồi của thành phần trung tâm. Lợi ích trên đồ thị không tự loại bỏ rủi ro vận hành khi thay đổi.

## 12. Kiểm tra lại sau khắc phục

### 12.1. Đối chiếu trạng thái mong muốn và thực tế

Cần xác nhận:

1. Quyền hoặc quan hệ đã được thay đổi đúng nguồn có thẩm quyền.
2. Các điểm nhận cấu hình đã cập nhật.
3. Cache và bản sao được xử lý theo semantics.
4. Quyền đã phát hành và phiên hiện hữu được đánh giá riêng.
5. Công việc hợp lệ vẫn hoạt động trong phạm vi cần thiết.
6. Các đường thay thế liên quan đã được kiểm tra.
7. Ngoại lệ và việc còn lại có owner.

Một API trả thành công cho thao tác sửa policy chưa chứng minh mọi agent hoặc gateway đã áp dụng.

### 12.2. Tái sử dụng cùng câu hỏi đánh giá

Nếu câu hỏi ban đầu là nhóm server operator có thể tác động control plane qua công cụ triển khai không, kiểm tra lại phải trả lời đúng câu hỏi đó với dữ liệu mới.

Không thay bằng một phép thử yếu hơn như “người dùng không thấy nút trên giao diện”. API hoặc quyền cấu hình phía sau có thể vẫn còn.

### 12.3. Phân biệt cắt cạnh mới với xử lý quá khứ

Sửa quyền ngăn hành động mới không tự đảo ngược artifact đã triển khai, tài khoản đã tạo hoặc secret đã được lấy.

Nếu có bằng chứng hoặc nghi vấn đường đã được sử dụng, cần đánh giá hoạt động quá khứ theo quy trình ứng phó và giữ phần việc đó riêng với thay đổi policy.

## 13. Hồ sơ một phát hiện

Một mẫu nội dung minh họa:

~~~yaml
# Mẫu dữ liệu báo cáo; không phải cấu hình thực thi.
finding:
  id: TIER-PATH-EXAMPLE-027
  objective: prevent_member_server_role_from_controlling_identity_plane
  start_subject: approved_server_operator_group
  target: reviewed_identity_control_plane
  status: CONFIG_VERIFIED
  assessed_scope: named_environment_and_snapshot

path:
  - relation: assigned_role
    evidence: evidence-reference-01
  - relation: can_modify_relevant_deployment_content
    evidence: evidence-reference-02
  - relation: release_condition_not_independent_in_assessed_scope
    evidence: evidence-reference-03
  - relation: execution_identity_can_change_protected_configuration
    evidence: evidence-reference-04

limits:
  runtime_effect_not_tested_on_production: true
  alternative_paths_require_separate_review: true

remediation:
  owner: assigned_control_owner
  intended_change: split_release_authority_and_target_scope
  validation: recheck_relations_and_safe_representative_behavior
~~~

Một báo cáo đọc được cần bổ sung diễn giải:

- Căn cứ nào xác định đây là ngoài ý định.
- Điều kiện phải đạt để đường có hiệu lực.
- Tác động nếu chủ thể sử dụng đường.
- Nguồn và độ mới của bằng chứng.
- Điều gì chưa được kiểm tra.
- Thay đổi được đề xuất và tác động cần quản lý.
- Kết quả kiểm tra lại và phần còn mở.

Không cần đưa secret, lệnh nguy hiểm hoặc dữ liệu có thể dùng trực tiếp để truy cập hệ thống vào báo cáo phổ biến rộng.

## 14. Quản lý ngoại lệ và giới hạn đánh giá

### 14.1. Ngoại lệ có trách nhiệm

Một quan hệ vượt tier có thể tạm thời được giữ vì nhu cầu vận hành. Nếu vậy, cần ghi:

- Chủ thể và phạm vi tài nguyên.
- Mục đích.
- Quyền hoặc quan hệ cụ thể.
- Rủi ro còn lại.
- Điều kiện bù trừ có thể thực thi.
- Người có thẩm quyền.
- Owner và thời hạn xử lý.
- Điều kiện kiểm tra lại.

Một dòng “accepted risk” không làm đường biến mất khỏi đồ thị. Nó cần trạng thái được theo dõi và không nên tự được tính như một boundary đã đạt.

### 14.2. Giới hạn phải đi cùng kết luận

Ví dụ:

~~~text
Đã đánh giá:
  quyền trên công cụ triển khai và các target được quản lý trong snapshot.

Chưa đánh giá:
  kho backup ngoài phạm vi, nguồn identity khác và các agent không đọc được.

Kết luận:
  đường xác định đã bị chặn theo điều kiện đã kiểm chứng;
  chưa có căn cứ kết luận không còn mọi đường vượt tier.
~~~

Cách diễn đạt này giúp người nhận biết kết quả có thể dùng cho quyết định nào.

### 14.3. Trạng thái không rõ cần owner

UNKNOWN không nên bị bỏ qua vô hạn. Nó có thể cần quyền đọc bổ sung, owner cung cấp cấu hình hoặc một cách kiểm chứng khác trong phạm vi được ủy quyền.

Tuy nhiên, không tự thực hiện thay đổi hoặc thử nghiệm xâm lấn chỉ để biến một trạng thái chưa biết thành đã biết. Cần chọn phương pháp tương xứng với câu hỏi và thẩm quyền đánh giá.

## 15. Duy trì kiểm tra khi hệ thống thay đổi

Đồ thị phản ánh một tập dữ liệu tại một thời điểm. Những sự kiện sau có thể tạo đường mới:

- Thêm role, group hoặc thành viên.
- Đổi ACL, trust hoặc ủy quyền.
- Thêm target, agent hoặc connector.
- Mở rộng scope công cụ triển khai.
- Đổi pipeline, image hoặc nguồn artifact.
- Thay thiết bị quản trị và công cụ hỗ trợ.
- Thêm nguồn identity, CA hoặc federation.
- Đổi phương án backup và phục hồi.
- Tạo ngoại lệ khẩn cấp.
- Thay cách cấp và giữ credential.

Cần kết hợp kiểm tra khi có thay đổi với rà soát theo vòng đời. Một lần đánh giá ban đầu không tự bảo vệ ranh giới cho mọi cấu hình tương lai.

Có thể so sánh quan hệ giữa các snapshot để phát hiện cạnh mới hoặc phạm vi mở rộng. Cần lưu ý thay đổi dữ liệu thu thập cũng có thể tạo khác biệt; không coi mọi cạnh mới xuất hiện trong báo cáo đều là quyền vừa được cấp.

Nếu đồ thị có chu trình điều khiển giữa các nhóm được cho là tách biệt, cần đánh giá xem chúng có thực sự tạo ranh giới độc lập không. Các điều kiện trên từng cạnh vẫn phải được giữ khi phân tích chu trình.

## 16. Kiểm chứng quy trình đánh giá

| Tình huống | Kết quả cần có |
|---|---|
| Group lồng nhau tạo quyền ngoài dự kiến | Quan hệ được thể hiện với nguồn bằng chứng |
| Chủ thể chỉ có quyền xem, không có quyền sửa | Không tạo cạnh điều khiển giả |
| Có quyền sửa lịch nhưng không sửa nội dung tác vụ | Phân biệt đúng loại ảnh hưởng |
| Cổng phát hành độc lập có hiệu lực | Ghi điều kiện chặn với phạm vi đã kiểm |
| Chủ thể có thể thay approver hoặc rule phát hành | Không coi approval là chặn độc lập |
| Collector thiếu quyền đọc | Dữ liệu không bị hiểu thành không có quyền |
| Quyền ở hai môi trường khác nhau | Không ghép thành đường trong cùng phạm vi nếu thiếu căn cứ |
| Hai điều kiện không cùng tồn tại về thời gian | Không kết luận đường có hiệu lực đồng thời |
| Grant đã thu hồi nhưng token hoặc phiên còn | Giữ phần hiệu lực còn lại riêng |
| Target ngoài menu PAM vẫn có API quản trị | Không bỏ sót vì giao diện không hiển thị |
| Sửa một cạnh nhưng còn đường qua backup | Không kết luận đã cắt mọi đường |
| Có giới hạn độ sâu hoặc thời gian tìm kiếm | Báo đánh giá chưa đầy đủ |
| Safe test chỉ chạy ở lab | Không tự suy toàn bộ production giống lab |
| Quyền mới được thêm sau snapshot | Có cơ chế đánh giá thay đổi hoặc cảnh báo theo phạm vi |
| Bằng chứng không còn truy xuất được | Không giữ mức xác nhận vượt dữ liệu hiện có |

Các chỉ số có thể theo dõi gồm số đường ngoài ý định theo trạng thái xác minh, các quyền trung tâm tạo nhiều đường, số UNKNOWN chưa có owner, ngoại lệ quá hạn và thời gian xử lý phát hiện.

Không chỉ đo số đường được công cụ tìm thấy. Thay đổi cách thu thập, số node hoặc quy tắc mô hình có thể làm số đường tăng mà không tương ứng một mức tăng rủi ro thực tế.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ xem membership nhóm admin | Bỏ sót quyền điều khiển gián tiếp | Đánh giá ACL, công cụ, credential và phục hồi |
| Mọi cạnh đều mang nhãn “admin” | Mất semantics của quyền | Ghi thao tác, phạm vi và điều kiện |
| Có mạng là coi có quyền | Tạo đường không có căn cứ | Xác minh thêm xác thực và ủy quyền |
| Có một sơ đồ là coi đã có khai thác | Vượt mức bằng chứng | Phân biệt ứng viên, cấu hình và hành vi kiểm chứng |
| Không tìm thấy đường là coi an toàn tuyệt đối | Che thiếu dữ liệu và giới hạn tìm kiếm | Gắn kết luận với phạm vi |
| MFA được coi là chặn mọi đường | Bỏ qua phiên, workload và quyền sửa policy | Xác định điểm MFA thực sự áp dụng |
| Approval không kiểm tra tính độc lập | Chủ thể có thể tự thay hoặc tự duyệt | Đánh giá thẩm quyền và ràng buộc phiên bản |
| Chỉ sửa quyền trong giao diện | API hoặc nguồn cấu hình khác có thể còn | Kiểm tra điểm thực thi có thẩm quyền |
| Thu hồi grant là coi hết hiệu lực cũ | Token, credential hoặc phiên còn | Theo dõi vòng đời từng lớp |
| Ngoại lệ được bỏ khỏi đồ thị | Mất khả năng theo dõi rủi ro | Giữ quan hệ và trạng thái chấp nhận có thời hạn |
| Chạy thử trực tiếp trên thành phần nhạy cảm khi chưa cần | Tạo tác động không tương xứng | Dùng cấu hình và kiểm chứng đại diện phù hợp |
| Đóng phát hiện khi còn UNKNOWN quan trọng | Kết luận quá mức | Có owner và ghi phần chưa giải quyết |

## 18. Bài tập áp dụng

Một đội tách tài khoản server admin khỏi domain admin. Công cụ rà soát nhóm không thấy server admin trong các nhóm đặc quyền directory. Tuy nhiên:

- Nhóm server admin quản lý một công cụ cập nhật agent trên nhiều loại server.
- Một số agent chạy trên thành phần danh tính.
- Công cụ có bước duyệt nhưng chưa rõ ai sửa được workflow.
- Một vault connector dùng chung phục vụ cả hai phạm vi.
- Kho backup chưa nằm trong dữ liệu thu thập.
- Sau khi gỡ một role, một số phiên cũ vẫn còn hoạt động.

Hãy lập phương án đánh giá:

1. Điểm xuất phát, đích và boundary nào cần xác định?
2. Các node và loại cạnh nào phải đưa vào đồ thị?
3. Quyền quản lý công cụ thực sự cho sửa thuộc tính gì?
4. Cần bằng chứng nào để coi cổng phê duyệt là độc lập?
5. Connector và kho backup có thể ảnh hưởng kết luận thế nào?
6. Cạnh nào đã được xác nhận, cạnh nào còn UNKNOWN?
7. Nên ưu tiên thay đổi nào để giảm quan hệ vượt tier?
8. Kiểm tra lại cấp mới, phiên cũ và đường thay thế ra sao?
9. Báo cáo nên diễn đạt thế nào khi chưa có dữ liệu backup?

Một kết quả đạt mục tiêu phải giải thích được chuỗi quyền, điều kiện, bằng chứng và giới hạn. Kiểm tra đường đi leo thang có giá trị khi nó chỉ ra ranh giới điều khiển thực tế và giúp xác nhận rằng các thay đổi quyền đã giảm đúng khả năng ảnh hưởng ngoài ý định.
