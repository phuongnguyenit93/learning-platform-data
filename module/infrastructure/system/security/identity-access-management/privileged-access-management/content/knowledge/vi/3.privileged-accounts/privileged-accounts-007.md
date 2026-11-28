# Cloud privileged account

## Mục tiêu bài học

Trong chương **Tài khoản đặc quyền**, cloud privileged account là tài khoản hoặc principal có khả năng thực hiện hành động đặc quyền trong môi trường cloud. Chủ thể đó có thể là quản trị viên, danh tính liên kết từ hệ thống bên ngoài, tài khoản dịch vụ hoặc workload tự động.

Trong phạm vi **Privileged Access Management (PAM)**, cần quản lý cả danh tính, quyền, quan hệ tin cậy, credential và các phiên sử dụng quyền. Bài học tập trung vào kiểm kê, least privilege, JIT/JEA, vault, luân chuyển credential và bằng chứng cho kiểm toán, ứng phó sự cố.

Sau bài học, bạn có thể:

- Phân biệt principal quản trị với các vùng chứa tài nguyên như account, subscription hoặc project.
- Phân tích đặc quyền ở control plane, data plane và những đường cấp quyền gián tiếp.
- Thiết kế truy cập cho con người và workload theo phạm vi, thời gian, nhiệm vụ.
- Giải thích giới hạn của MFA, credential ngắn hạn và việc thu hồi role.
- Xác định cách liên kết một hành động cloud với chủ thể, phiên và yêu cầu được chấp nhận.

## 1. Làm rõ từ “account” trong môi trường cloud

Từ account có thể chỉ hai đối tượng khác nhau:

| Cách dùng | Ý nghĩa | Ví dụ khái niệm |
| --- | --- | --- |
| Tài khoản hoặc principal truy cập | Chủ thể được xác thực và phân quyền | Người quản trị, danh tính dịch vụ, principal liên kết |
| Vùng chứa tài nguyên và phạm vi quản trị | Một đơn vị tổ chức tài nguyên, chính sách hoặc thanh toán | Cloud account, subscription hoặc project tùy nền tảng |

Các vùng chứa này không có ngữ nghĩa giống hệt nhau giữa các nhà cung cấp. Cần xem mô hình cụ thể của nền tảng thay vì thay tên trực tiếp trong một thiết kế phân quyền.

Trong bài này, **cloud privileged account chủ yếu chỉ chủ thể có đặc quyền**. Khi nói đến vùng chứa tài nguyên, bài sẽ dùng cụm “phạm vi tài nguyên” hoặc gọi rõ account, subscription, project.

Một danh tính được coi là có đặc quyền khi có thể thực hiện hành động nhạy cảm, chẳng hạn:

- Quản lý danh tính, vai trò, chính sách hoặc quan hệ tin cậy.
- Tạo, sửa, xóa tài nguyên production.
- Đọc hoặc xuất dữ liệu nhạy cảm trên phạm vi lớn.
- Đọc bí mật hoặc sử dụng khóa bảo vệ dữ liệu.
- Thay đổi mạng, audit, bản sao lưu hoặc cơ chế phục hồi.
- Gán danh tính mạnh cho workload hoặc thay đổi mã chạy dưới danh tính đó.

Đặc quyền không chỉ nằm ở một role có tên “Administrator”. Cần đánh giá mọi khả năng có thể tạo tác động tương đương.

## 2. Cloud có nhiều lớp quyền cần nhìn cùng nhau

### 2.1. Control plane: quản lý tài nguyên và cấu hình

Control plane là lớp dùng để tạo và điều khiển tài nguyên, chính sách hoặc cấu hình dịch vụ.

Ví dụ:

- Tạo máy ảo, thay cấu hình dịch vụ hoặc xóa cụm.
- Thay đổi chính sách IAM, mạng và quan hệ tin cậy.
- Tạo bản sao hoặc phục hồi tài nguyên.
- Cấu hình nơi ghi audit và các cơ chế bảo vệ.

Một principal có quyền control plane mạnh có thể không được gán quyền đọc dữ liệu trực tiếp, nhưng vẫn có thể có đường ảnh hưởng đến dữ liệu qua cấu hình, danh tính hoặc bản sao. Khả năng đó phụ thuộc dịch vụ và cơ chế bảo vệ thực tế.

### 2.2. Data plane: sử dụng dữ liệu và chức năng của dịch vụ

Data plane là lớp thực hiện các hoạt động như:

- Đọc hoặc ghi đối tượng trong kho lưu trữ.
- Truy vấn cơ sở dữ liệu.
- Đọc giá trị bí mật.
- Gửi, nhận hoặc xử lý thông điệp.
- Thực hiện thao tác mật mã được cấp trên một khóa.

Hai lớp có thể dùng cơ chế phân quyền khác nhau. Quyền quản lý tài nguyên không mặc nhiên tương đương quyền đọc dữ liệu, nhưng cũng không nên coi chúng hoàn toàn độc lập nếu tồn tại đường cấp lại quyền hoặc tạo bản sao.

### 2.3. Quản trị tổ chức, danh tính và tài chính

Ngoài từng tài nguyên, cloud còn có các lớp quản trị rộng hơn:

- Cấu trúc tổ chức và phân cấp tài nguyên.
- Nhà cung cấp danh tính và cơ chế liên kết.
- Chính sách áp dụng ở phạm vi cha.
- Thanh toán, hạn mức hoặc điều kiện sử dụng tài nguyên.
- Công cụ triển khai và nền tảng bảo mật.

Quyền tài chính không tự động là quyền dữ liệu, nhưng một số thao tác có thể ảnh hưởng khả năng vận hành hoặc duy trì dịch vụ. Cần kiểm kê từng khả năng, không suy từ chức danh.

## 3. Những loại chủ thể đặc quyền thường gặp

| Nhóm | Đường sử dụng quyền | Rủi ro cần chú ý |
| --- | --- | --- |
| Quản trị viên cloud | Console, CLI, API hoặc công cụ quản trị | Quyền thường trực, nhiều môi trường, credential bị sao chép |
| Quản trị IAM hoặc tổ chức | Quản lý role, nhóm, chính sách, liên kết | Tự cấp quyền, cấp quyền tiếp, thay ranh giới tin cậy |
| Danh tính nền tảng hoặc bootstrap có quyền rất cao | Khởi tạo, khôi phục, thao tác đặc biệt theo nền tảng | Tác động lớn, ít sử dụng nhưng cần khả năng truy cập khi khẩn cấp |
| Tài khoản dịch vụ và workload | API, job, controller, ứng dụng | Credential dài hạn, quyền dư, chủ sở hữu không rõ |
| Pipeline triển khai | Nhận role rồi thay đổi production | Mã hoặc workflow không được tin cậy có thể tiếp cận quyền phát hành |
| Principal từ bên ngoài | Liên kết danh tính, ủy quyền hoặc truy cập nhà cung cấp | Quan hệ tin cậy rộng, không rõ thời hạn và người bảo trợ |
| Danh tính công cụ bảo mật, sao lưu hoặc vault | Thu thập, bảo vệ, phục hồi tài nguyên | Có thể tiếp cận nhiều dữ liệu hoặc làm suy yếu khả năng bảo vệ |

Tên gọi và quyền của danh tính gốc hoặc tài khoản khởi tạo khác nhau theo nhà cung cấp. Không nên đồng nhất chúng với tài khoản root của hệ điều hành trong máy ảo.

Một tài khoản đăng nhập vào console cũng có thể nhận nhiều role khác nhau. Chủ thể ban đầu, role được nhận và principal xuất hiện trong audit ở đích cần được liên kết, không chỉ ghi một tên đăng nhập.

## 4. Phạm vi đặc quyền được tạo ra như thế nào?

Một principal có thể có quyền qua nhiều đường:

```text
Danh tính ban đầu
       |
       +--> Quyền hoặc vai trò được cấp trực tiếp
       |
       +--> Nhóm và quan hệ kế thừa
       |
       +--> Liên kết / ủy quyền để nhận principal khác
       |
       +--> Chính sách gắn với tài nguyên
       |
       +--> Khả năng thay đổi workload hoặc cơ chế cấp quyền
                         |
                         v
             Tập khả năng thực tế trên tài nguyên
```

Quyền hiệu lực không phải lúc nào cũng là phép cộng đơn giản. Nền tảng có thể áp dụng điều kiện, giới hạn, chính sách ở nhiều cấp và quy tắc đánh giá riêng. Cần xác minh đúng cơ chế của từng dịch vụ.

### 4.1. Phạm vi cha có thể làm quyền rộng hơn dự kiến

Một role được gán ở cấp tổ chức hoặc phạm vi cha có thể ảnh hưởng nhiều tài nguyên con theo mô hình kế thừa của nền tảng.

Nếu đội chỉ rà soát role gán trực tiếp trên một tài nguyên, họ có thể bỏ sót quyền từ cấp khác. Ngược lại, không nên khẳng định mọi role đều kế thừa giống nhau ở mọi dịch vụ.

### 4.2. Quyền cấp tiếp là đặc quyền quan trọng

Các khả năng sau cần được đánh giá riêng:

- Gán một role mạnh cho mình hoặc chủ thể khác.
- Sửa chính sách tin cậy để nhận principal khác.
- Gắn danh tính có quyền cao vào workload.
- Sửa mã hoặc cấu hình của workload có quyền cao.
- Quản lý credential của principal khác.
- Thay đổi nơi lưu bí mật hoặc chính sách truy cập bí mật.

Một role có tên hẹp vẫn có thể mở đường tới quyền rộng nếu chứa những khả năng này.

### 4.3. Nhãn tài nguyên không tự tạo ranh giới an toàn

Nhãn hoặc tag có thể được dùng trong chính sách khi nền tảng hỗ trợ. Tuy nhiên, nếu người dùng được tùy ý sửa chính nhãn quyết định quyền, ranh giới có thể bị suy yếu.

Cần kiểm soát cả điều kiện phân quyền và khả năng thay đổi dữ liệu đầu vào của điều kiện đó.

## 5. Vì sao tài khoản đặc quyền cloud dễ tạo tác động diện rộng?

### Một credential có thể điều khiển nhiều tài nguyên

API credential hoặc phiên mạnh có thể được dùng qua công cụ tự động để tác động hàng loạt tài nguyên trong phạm vi quyền. Không cần mở từng máy chủ bằng một phiên tương tác.

### Quyền có thể lan qua nhiều phạm vi tin cậy

Một principal ở môi trường thử nghiệm có thể có đường nhận role production nếu quan hệ tin cậy quá rộng. Sự cố ở một nơi ít nhạy cảm có thể ảnh hưởng nơi nhạy cảm hơn.

### Trạng thái thay đổi nhanh

Tài nguyên, workload và binding có thể được tạo hoặc xóa bởi tự động hóa. Một bản kiểm kê tĩnh nhanh chóng không còn mô tả đầy đủ hệ thống nếu không được cập nhật theo thay đổi.

### Control plane có thể tác động khả năng bảo vệ và phục hồi

Quyền sửa audit, thay chính sách sao lưu, thay cấu hình mạng hoặc quản lý khóa có thể ảnh hưởng cách phát hiện và phục hồi sau sự cố.

Các cơ chế chống xóa hoặc bảo vệ bản sao lưu chỉ tạo ranh giới theo năng lực và cấu hình thực tế của dịch vụ. Không nên coi tên một tính năng là bằng chứng rằng mọi quản trị viên đều không thể làm suy yếu nó.

### Console chỉ là một trong nhiều đường truy cập

Bảo vệ đăng nhập console chưa bao quát CLI, API key, token, SDK, pipeline và các principal được ủy quyền. Kiểm soát PAM cần bao phủ các đường sử dụng quyền thực tế.

## 6. Kiểm kê tài khoản và quyền cloud

Một bản kiểm kê nên trả lời các câu hỏi sau:

| Nhóm | Nội dung cần xác định |
| --- | --- |
| Chủ thể | Con người, workload, principal liên kết hay tài khoản đặc biệt |
| Chủ sở hữu | Cá nhân hoặc đội chịu trách nhiệm, người bảo trợ và đầu mối sự cố |
| Mục đích | Nhiệm vụ cần quyền, tài nguyên và hành động cần thiết |
| Phạm vi | Tổ chức, tenant, account, subscription, project hoặc tài nguyên cụ thể theo nền tảng |
| Quyền hiệu lực | Role, nhóm, điều kiện, quyền kế thừa và đường nhận quyền khác |
| Credential | Loại credential, nơi cấp, thời hạn, khả năng thu hồi và nơi phân phối |
| Quan hệ tin cậy | Nguồn danh tính, chủ thể được chấp nhận, điều kiện và bên sửa được chính sách |
| Đường sử dụng | Console, CLI, API, workload, công cụ trung gian và đường ngoại lệ |
| Bằng chứng | Audit nguồn, audit đích, định danh phiên và nơi bảo vệ log |
| Vòng đời | Ngày xem xét, điều kiện kết thúc, cách thu hồi và xử lý phụ thuộc |

Không ghi giá trị mật khẩu, khóa bí mật hay token vào bảng kiểm kê.

Cần kiểm kê cả quyền tại nhà cung cấp danh tính bên ngoài. Nếu một người không có role cloud trực tiếp nhưng sửa được nhóm hoặc ứng dụng liên kết dẫn đến role quản trị cloud, người đó vẫn có đường tác động đến đặc quyền.

## 7. Least privilege và ranh giới quản trị

### 7.1. Viết yêu cầu bằng hành động và tài nguyên

Yêu cầu “cần quyền cloud admin” nên được làm rõ, ví dụ:

> Đội ứng dụng A cần cập nhật phiên bản dịch vụ A trên production, xem trạng thái liên quan và xử lý một số thao tác vận hành đã xác định.

Từ đó phân biệt với những quyền không mặc nhiên cần thiết:

- Quản lý toàn bộ IAM.
- Đọc bí mật của ứng dụng khác.
- Thay cấu hình audit.
- Xóa bản sao lưu.
- Quản lý khóa bảo vệ dữ liệu của toàn tổ chức.

### 7.2. Tách môi trường và nhiệm vụ

Một số hướng phân tách có thể gồm:

- Production và môi trường phát triển.
- Triển khai ứng dụng và quản trị danh tính.
- Quản trị nền tảng và đọc dữ liệu nghiệp vụ.
- Tạo bản sao lưu và xóa hoặc thay chính sách bảo vệ bản sao.
- Thực hiện thao tác và quản lý bằng chứng.

Mức phân tách phải phù hợp với năng lực nền tảng. Chỉ tạo hai role khác tên không tạo ranh giới nếu role thứ nhất có thể tự gán role thứ hai.

### 7.3. Kết hợp chính sách ở nhiều lớp

Cloud có thể hỗ trợ các giới hạn ở phạm vi tổ chức, danh tính, phiên hoặc tài nguyên. Chúng có thể giúp giảm khả năng một role cục bộ mở rộng quyền ngoài ý định.

Cần chỉ rõ ai sửa được từng lớp, chính sách áp dụng cho những dịch vụ nào và có ngoại lệ nào. Không giả định một quy tắc ở cấp tổ chức bao phủ mọi data plane hoặc mọi đường truy cập.

## 8. Truy cập của con người: liên kết danh tính, MFA, JIT và JEA

### Liên kết danh tính

Liên kết với hệ thống danh tính tập trung có thể hỗ trợ quản lý vòng đời và giảm nhu cầu tạo nhiều tài khoản độc lập. Tuy nhiên, vẫn cần kiểm soát:

- Nhóm hoặc claim nào ánh xạ tới role cloud.
- Ai được sửa ánh xạ và chính sách.
- Người dùng có tài khoản cục bộ hoặc credential khác để đi ngoài luồng không.
- Điều gì xảy ra khi danh tính nguồn bị vô hiệu hóa.
- Những phiên hoặc token đích nào vẫn còn hiệu lực.

### MFA

MFA giúp làm mạnh bước xác thực của con người. Cần kiểm tra cơ chế áp dụng với console, luồng nhận role và công cụ dòng lệnh thực tế.

Một lần MFA ở nguồn không tự chứng minh mọi API credential đều yêu cầu cùng điều kiện. Credential độc lập hoặc một phiên đã được phát hành có thể có vòng đời và cơ chế kiểm tra khác.

### JIT

Just-in-Time giới hạn khoảng thời gian quyền quản trị được cấp hoặc sử dụng theo nhiệm vụ. Yêu cầu nên nêu rõ tài nguyên, hành động, lý do và thời hạn.

Khi hết hạn, cần xác định cách xử lý role, token, phiên và khả năng xin credential mới. Thu hồi một binding không mặc nhiên vô hiệu hóa tức thì mọi phiên đã được phát hành.

### JEA

Just Enough Administration giới hạn tập khả năng quản trị. Với cloud, nguyên tắc này có thể được thực hiện qua role hẹp, policy API hoặc giao diện tác vụ có kiểm soát.

Quyền khởi động lại một dịch vụ khác với quyền sửa mọi tài nguyên trong project. Đồng thời, quyền sửa cấu hình hoặc mã của một workload mạnh có thể tạo tác động vượt khỏi tên tác vụ.

JIT và JEA trong bài là các nguyên tắc thiết kế; không phải mọi nhà cung cấp đều có tính năng cùng tên hoặc cùng hành vi.

## 9. Truy cập của workload và quản lý credential

### 9.1. Dùng danh tính riêng cho nhiệm vụ

Pipeline, dịch vụ và controller nên có danh tính theo ranh giới workload, môi trường và nhiệm vụ phù hợp. Không dùng tài khoản quản trị cá nhân làm credential chạy tự động.

Một pipeline build không đương nhiên cần cùng quyền với luồng phát hành production. Mã hoặc job không được tin cậy cần được tách khỏi ngữ cảnh có thể nhận quyền production.

### 9.2. Credential ngắn hạn và federation

Khi được nền tảng hỗ trợ, workload có thể nhận credential có thời hạn dựa trên danh tính runtime hoặc bằng chứng từ nguồn được tin cậy.

Cần kiểm tra:

- Nguồn phát hành bằng chứng.
- Chủ thể được chấp nhận.
- Đối tượng nhận của bằng chứng.
- Thời hạn và điều kiện đổi hoặc sử dụng credential.
- Quyền thực tế của principal đích.
- Ai kiểm soát runtime hoặc workflow tạo ra bằng chứng.

Không nên dùng quan hệ tin cậy rộng cho mọi workload chỉ vì credential đích có thời hạn ngắn. Nếu runtime đã bị chiếm và tiếp tục được cấp credential mới, nguy cơ sử dụng quyền vẫn tồn tại.

### 9.3. Khi vẫn cần khóa hoặc bí mật dài hạn

Một số tích hợp cần credential dài hạn. Khi đó cần:

1. Có chủ sở hữu và mục đích rõ ràng.
2. Lưu và phân phối qua vault hoặc cơ chế quản lý bí mật phù hợp.
3. Giới hạn quyền và phạm vi sử dụng.
4. Kiểm soát bản sao trong cấu hình, công cụ và đầu ra tác vụ.
5. Luân chuyển có kế hoạch với các bên phụ thuộc.
6. Thu hồi khi nghi bị lộ hoặc hết nhu cầu.
7. Xác nhận credential cũ đã bị xử lý theo cơ chế nền tảng.

Cập nhật giá trị trong vault không chứng minh mọi ứng dụng đã chuyển sang credential mới. Tương tự, chặn quyền lấy bí mật không vô hiệu hóa những bản sao đã lấy trước đó.

## 10. Ví dụ: quyền phát hành ứng dụng A

Hệ thống giả định có một luồng phát hành được bảo vệ cho ứng dụng A. Luồng đó cần cập nhật dịch vụ A trên production.

Mô tả sau là **ý định kiểm soát, không phải cấu hình triển khai cho một nhà cung cấp cụ thể**:

```yaml
principal:
  purpose: application-a-production-release
  type: federated-workload
  owner: application-a-operations

trust:
  accepted_source: approved-release-identity-provider
  accepted_subject: protected-application-a-release-workflow
  intended_receiver: production-credential-service

permissions:
  scope: application-a-production
  capabilities:
    - update-application-release

lifecycle:
  credential: short-lived
  access: limited-to-accepted-release-context
  revocation: covers-future-issuance-and-issued-access

evidence:
  correlate:
    - workflow-run-id
    - artifact-digest
    - target-principal-id
    - credential-session-id
    - cloud-audit-event
```

Khi chuyển thành cấu hình thật, cần kiểm tra:

- Vai trò đích có chứa quyền quản lý IAM hoặc tài nguyên ngoài ứng dụng A không.
- Principal có thể gắn danh tính mạnh khác vào workload không.
- Ai sửa được workflow, chính sách tin cậy và môi trường production.
- Tác vụ không được tin cậy có đường nhận cùng role không.
- Credential có thể bị lấy từ runtime dùng chung không.
- Audit có liên kết hành động với đúng lần chạy và artifact không.
- Thu hồi có xử lý được cả việc phát hành credential mới lẫn quyền đã phát hành không.

Nếu chỉ ghi phạm vi hẹp trong yêu cầu nhưng role thực tế vẫn có quyền rộng, thiết kế chưa đạt mục tiêu.

## 11. Tài khoản có quyền rất cao và truy cập khẩn cấp

Một số nền tảng có danh tính gốc, tài khoản khởi tạo hoặc khả năng quản trị đặc biệt dùng cho các thao tác nhất định. Cần xác định đúng vai trò của chúng theo nền tảng.

Hướng quản lý gồm:

- Giới hạn sử dụng vào những mục đích được xác định.
- Bảo vệ phương tiện xác thực và cơ chế khôi phục.
- Xác định người chịu trách nhiệm và điều kiện được truy cập.
- Có cảnh báo và xem xét sau sử dụng.
- Kiểm tra khả năng truy cập trong tình huống khôi phục theo kế hoạch.
- Quản lý các ngoại lệ và bằng chứng riêng.

Cần tránh vòng phụ thuộc khiến phương án khẩn cấp không dùng được khi thành phần chính hỏng. Ví dụ, nếu credential khôi phục chỉ lấy được qua đúng hệ thống danh tính đang gặp sự cố, tổ chức cần một phương án thay thế đã được kiểm soát.

Phương án khẩn cấp vẫn phải có giới hạn và khả năng quy trách nhiệm. Không nên biến tài khoản này thành lối tắt vận hành hằng ngày.

## 12. Bằng chứng và giám sát đặc quyền cloud

Cloud thường có nhiều nguồn audit. Cần thiết kế cách đối chiếu:

```text
Người hoặc workload ban đầu
            |
            v
Sự kiện xác thực / bằng chứng danh tính nguồn
            |
            v
Sự kiện nhận role hoặc cấp credential
            |
            v
Principal và phiên ở cloud đích
            |
            v
Hành động trên control plane hoặc data plane
```

Thông tin hữu ích gồm:

- Định danh chủ thể nguồn, principal đích và phiên.
- Mã yêu cầu quyền, mã sự cố hoặc lần chạy liên quan.
- Role, điều kiện và phạm vi được cấp tại thời điểm đó.
- Tài nguyên, hành động, kết quả và thời gian.
- Thay đổi chính sách, quan hệ tin cậy, credential và audit.
- Nguồn kết nối cùng ngữ cảnh phù hợp để điều tra.

Địa chỉ mạng hoặc tên phiên do client cung cấp chỉ là một phần bằng chứng. Không nên dùng một trường dễ thay đổi để kết luận chắc chắn ai đã thao tác.

### Những hành vi cần được xem xét

- Cấp role mạnh ngoài quy trình hoặc ngoài phạm vi dự kiến.
- Tạo credential mới cho một principal nhạy cảm.
- Thay chính sách tin cậy giữa các môi trường.
- Thay cấu hình audit hoặc nơi lưu log.
- Truy cập bí mật, bản sao dữ liệu hoặc tài nguyên ngoài nhiệm vụ.
- Danh tính workload sử dụng quyền quản trị IAM không phù hợp.
- Sử dụng danh tính khẩn cấp.

Các sự kiện này cần ngữ cảnh; chúng không tự chứng minh hành vi xấu. Có thể có thao tác khôi phục hoặc thay đổi hợp lệ nhưng vẫn cần đối chiếu.

### Bảo vệ log và dữ liệu nhạy cảm

Cần xác định quyền truy cập, nơi lưu và cơ chế bảo vệ bằng chứng phù hợp. Nếu cùng một principal có thể thực hiện thao tác và xóa mọi bằng chứng liên quan, khả năng điều tra bị suy yếu.

Không ghi khóa bí mật, mật khẩu hoặc token đầy đủ vào log. Một số nguồn audit không tự bao phủ mọi hoạt động data plane; cần xác định cụ thể mức quan sát thay vì suy từ việc “đã bật audit”.

## 13. Thu hồi quyền và ứng phó sự cố

Giả sử một credential quản trị được phát hiện trong đầu ra của pipeline.

### Bước 1: Xác định phạm vi

Làm rõ credential thuộc principal nào, có hiệu lực trên phạm vi nào, đã tồn tại bao lâu và có thể đã xuất hiện ở những nơi nào. Đối chiếu chính sách và quyền tại thời điểm liên quan, không chỉ trạng thái hiện tại.

### Bước 2: Ngăn truy cập tiếp

Theo mức khẩn cấp và cơ chế nền tảng, có thể cần hạn chế principal, đường cấp credential, quan hệ tin cậy hoặc runtime đang bị nghi ngờ.

Ngừng in credential trong log chỉ sửa đường lộ về sau, không thu hồi bản credential đã lộ.

### Bước 3: Xử lý quyền đã phát hành

Kiểm tra khóa, token, phiên và credential đích liên quan. Một số quyền đã cấp có thể có vòng đời hoặc cơ chế thu hồi riêng.

Không mặc định vô hiệu hóa danh tính ở nguồn sẽ làm mọi token đích mất hiệu lực ngay. Cần xác nhận hành vi của hệ thống và những biện pháp kiểm soát bổ sung phù hợp.

### Bước 4: Tìm thay đổi và tác động phát sinh

Trong phạm vi điều tra, kiểm tra:

- Principal, khóa hoặc credential mới.
- Role, chính sách và quan hệ tin cậy bị thay đổi.
- Workload, tác vụ hoặc cấu hình có thể duy trì truy cập.
- Dữ liệu, bí mật và bản sao đã được tiếp cận.
- Thay đổi audit, mạng, khóa và khả năng phục hồi.

Chỉ thu hồi credential ban đầu có thể bỏ sót đường truy cập được tạo sau đó.

### Bước 5: Khôi phục và xác nhận

Bảo toàn bằng chứng cần thiết, sửa nguyên nhân, xử lý runtime hoặc cấu hình không còn được tin cậy và cấp lại quyền tối thiểu phù hợp. Xác nhận các đường truy cập cũ đã được xử lý, đồng thời kiểm tra tác động vận hành.

Không có sự kiện trong một nguồn log chưa đầy đủ không đủ để chứng minh không có truy cập trái phép.

## 14. Tình huống tự đánh giá

Một tổ chức có thiết kế sau:

- Quản trị viên đăng nhập console qua hệ thống danh tính tập trung và có MFA.
- Một số người vẫn giữ khóa API dài hạn của tài khoản cloud quản trị.
- Pipeline thử nghiệm có thể nhận role triển khai production.
- Role triển khai được phép sửa tài nguyên ứng dụng, cấp role và thay cấu hình audit.
- Token của pipeline có thời hạn ngắn.
- Nhóm cho rằng MFA và token ngắn hạn đã kiểm soát toàn bộ rủi ro.

### Phân tích

**Đường truy cập không đồng nhất:** MFA ở console chưa chứng minh khóa API dài hạn chịu cùng điều kiện.

**Ranh giới môi trường yếu:** pipeline thử nghiệm có thể tiếp cận quyền production.

**Quyền triển khai vượt nhiệm vụ:** quyền cấp role và thay audit tạo khả năng mở rộng quyền hoặc làm suy yếu bằng chứng.

**Thời hạn chưa đủ:** pipeline vẫn có thể xin token mới nếu quan hệ tin cậy không đổi; token ngắn hạn không sửa phạm vi quyền quá rộng.

### Hướng cải thiện

- Kiểm kê và xử lý các credential quản trị dài hạn cùng phụ thuộc.
- Thu hẹp quan hệ tin cậy vào luồng phát hành được bảo vệ.
- Tách quyền theo ứng dụng, môi trường và nhiệm vụ.
- Loại quyền quản trị IAM hoặc audit khỏi role triển khai khi không cần.
- Bảo vệ runtime, workflow và các cấu hình quyết định việc cấp quyền.
- Liên kết chủ thể nguồn, sự kiện cấp credential và hành động ở đích.
- Xác định cách ngăn cấp mới và xử lý phiên, token đã phát hành khi có sự cố.

Các thay đổi cần được điều phối để giữ khả năng vận hành và phục hồi. Không nên xóa credential đang có phụ thuộc chưa rõ rồi coi gián đoạn là điều không thể tránh.

## 15. Những điểm cần ghi nhớ

- Cloud privileged account là principal có khả năng nhạy cảm; cần phân biệt với vùng chứa tài nguyên mang tên account, subscription hoặc project.
- Đặc quyền có thể nằm ở control plane, data plane, IAM, workload, bí mật, khóa và khả năng phục hồi.
- Phải đánh giá cả quyền trực tiếp, kế thừa, liên kết và khả năng cấp lại quyền hoặc sửa workload mạnh hơn.
- MFA và credential ngắn hạn là thành phần quan trọng nhưng không thay thế least privilege, JIT/JEA và kiểm soát quan hệ tin cậy.
- Vault và luân chuyển cần quản lý cả phân phối, phụ thuộc, bản sao credential và thu hồi.
- Bằng chứng phải liên kết được **chủ thể nguồn, principal đích, phiên, quyền, tài nguyên, hành động và kết quả thu hồi**.