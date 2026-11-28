# Assume-role workflow

Assume-role là luồng trong đó một danh tính đã được xác thực yêu cầu sử dụng một role, rồi nhận phiên với credential tạm thời để thực hiện công việc trong phạm vi được cho phép. Trong Cloud PAM, mục tiêu là biến việc sử dụng quyền mạnh thành một quá trình có điều kiện, có thời hạn và có thể truy vết về người hoặc workload chịu trách nhiệm.

Bài học dùng AWS IAM và AWS Security Token Service (STS) để minh họa thuật ngữ assume-role. Các thiết kế về yêu cầu công việc, phê duyệt, JIT, bằng chứng và ứng phó sự cố là mô hình triển khai PAM đề xuất; không phải mọi bước ấy đều có sẵn trong một lệnh gọi STS.

Một phiên tạm thời không tự trở thành phiên an toàn. Nếu role quá rộng, nguồn yêu cầu không được kiểm soát hoặc người dùng đi vòng qua cổng phê duyệt, rủi ro quản trị vẫn tồn tại dù credential chỉ sống trong thời gian ngắn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt danh tính nguồn, role đích, phiên role và credential tạm thời.
- Phân biệt quyền được assume role với quyền thực hiện hành động sau khi assume.
- Thiết kế luồng cho người vận hành và workload mà không dùng chung danh tính.
- Ràng buộc yêu cầu PAM với role, tài nguyên, mục đích và thời gian.
- Nhận diện đường bỏ qua phê duyệt, role chaining và quyền quản trị gián tiếp.
- Kiểm tra danh tính hiệu lực, quyền được phép và trường hợp phải bị từ chối.
- Phân biệt ngăn cấp phiên mới, chặn quyền của phiên hiện hữu và xử lý tác động đã xảy ra.

## 2. Các thành phần cần phân biệt

### 2.1. Danh tính nguồn

Danh tính nguồn là principal dùng để bắt đầu yêu cầu. Nó có thể là:

- Người dùng doanh nghiệp đã đăng nhập qua hệ thống liên kết danh tính.
- Một role nguồn mà người hoặc workload đang sử dụng.
- Workload có danh tính do nền tảng cung cấp.
- Broker PAM thực hiện lời gọi thay cho một yêu cầu đã được xác minh.

Phải biết danh tính nguồn đến từ đâu, ai kiểm soát nó và cách chứng minh người hoặc máy đang sử dụng nó. Một tên người dùng trong trường mô tả không thay thế xác thực.

### 2.2. Role đích và phiên role

Role đích là đối tượng định nghĩa khả năng truy cập. Phiên role là một lần sử dụng role với ngữ cảnh và thời hạn cụ thể.

Cần giữ hai khái niệm tách biệt:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Principal nguồn | Ai hoặc workload nào đang yêu cầu? |
| Role đích | Có thể sử dụng tập năng lực nào? |
| Trust policy | Principal nào được phép đi vào role theo điều kiện nào? |
| Permissions policy | Role được phép làm gì? |
| Phiên | Lần sử dụng nào, với ngữ cảnh và thời hạn nào? |
| Credential tạm thời | Dùng gì để xác thực các request của phiên? |
| Grant PAM | Vì sao lần sử dụng này được phép theo quy trình của tổ chức? |

Grant PAM và phiên cloud không phải cùng một đối tượng. Hệ thống cần có cách liên kết chúng thay vì giả định chỉ cần tạo một phiên là đã có phê duyệt hợp lệ.

### 2.3. Credential tạm thời vẫn là bí mật

AWS STS AssumeRole trả về bộ credential gồm access key ID, secret access key và session token, kèm thông tin hết hạn. Bộ credential này dùng để thực hiện request trong ngữ cảnh phiên role. Thời hạn được yêu cầu phải nằm trong giới hạn của API và cấu hình role. Với role chaining qua CLI hoặc API, phiên bị giới hạn tối đa một giờ. [Tài liệu AssumeRole của AWS STS](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html).

Không đưa bộ credential vào:

- Nội dung ticket.
- Bản ghi phê duyệt.
- Chat hỗ trợ.
- Log ứng dụng hoặc log pipeline.
- Ảnh chụp màn hình.
- Artifact hoặc mã nguồn.

Một người có thể sử dụng credential bị lộ mà không cần đi lại toàn bộ luồng đăng nhập ban đầu. Do đó, hạn chế nơi credential xuất hiện cũng quan trọng như hạn chế thời hạn.

## 3. Hai quyết định cấp quyền khác nhau

### 3.1. Có được vào role không?

Quyết định thứ nhất xét principal nguồn và quan hệ trust để xác định yêu cầu assume-role có được chấp nhận hay không.

Trong AWS, truy cập role khác account cần cấu hình trust ở phía đích và quyền gọi AssumeRole phù hợp ở phía nguồn. Trong cùng account, trust policy cấp trực tiếp cho một principal có thể tạo đường cho phép khác với mô hình chỉ tin account rồi ủy quyền qua identity policy; không nên áp dụng một công thức duy nhất cho mọi trường hợp. [Hợp đồng quyền của AssumeRole](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html).

Khi rà soát, cần xác định đường cấp quyền thật sự được dùng. Một role có tên production-readonly nhưng trust rộng vẫn có thể bị nhiều principal không mong muốn sử dụng.

### 3.2. Vào role rồi có được làm hành động này không?

Quyết định thứ hai diễn ra khi phiên gọi dịch vụ đích. Assume-role thành công không chứng minh phiên được đọc một đối tượng, sửa một cấu hình hoặc quản trị một tài nguyên cụ thể.

Quyền của danh tính nguồn và role đích không tự cộng lại thành một tập quyền chung cho request dùng credential đích. Khi có session policy, nó giới hạn phần quyền mà identity policy của role cấp cho phiên, không dùng để cấp thêm quyền vượt phần đó. [Sử dụng role qua AWS API](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-api.html).

Cách suy nghĩ an toàn là luôn đặt hai câu hỏi riêng:

~~~text
Cửa vào role:
    principal này có được tạo phiên role này không?

Cửa vào tài nguyên:
    phiên này có được thực hiện hành động này trên tài nguyên này không?
~~~

### 3.3. Không rút gọn toàn bộ IAM thành một phép giao

Quyền hiệu lực còn phụ thuộc các policy áp dụng cho request và cách principal được tham chiếu. Resource policy, permissions boundary, policy tổ chức và explicit deny có vai trò khác nhau; explicit deny áp dụng có thể chặn một allow. Cần đánh giá đúng ngữ cảnh, không coi role policy hoặc một session policy là toàn bộ hệ thống quyền. [Logic đánh giá policy của AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html).

Trong thiết kế PAM, điều này dẫn đến yêu cầu thực tế: kiểm thử quyền hiệu lực trên tài nguyên thật trong phạm vi thử nghiệm, thay vì chỉ đọc tên role hoặc nhìn thấy một policy hẹp.

## 4. Từ nhu cầu công việc tới role có phạm vi rõ ràng

### 4.1. Xác định hành động trước khi chọn role

Một yêu cầu tốt không chỉ nói “cần vào production”. Nó cần làm rõ:

- Công việc cần hoàn thành.
- Account và môi trường.
- Dịch vụ và tập tài nguyên.
- Hành động cần thực hiện.
- Hành động bị loại trừ.
- Thời gian dự kiến.
- Điều kiện phê duyệt hoặc tự động cho phép.
- Owner chịu trách nhiệm.
- Bằng chứng cần lưu.

Ví dụ: người trực ca cần đọc hai object báo cáo trong một prefix đã xác định để kiểm tra lỗi đối soát. Nhu cầu đó không đòi hỏi role quản trị toàn bộ storage hay quyền thay bucket policy.

### 4.2. Phân biệt quyền sử dụng và quyền thay đổi cơ chế cấp quyền

Role tác nghiệp không nên tự có khả năng:

- Sửa trust policy của chính nó.
- Gắn thêm permissions policy.
- Tạo principal mới để giữ quyền.
- Tắt hoặc đổi đường audit.
- Cấp quyền cho workload ngoài phạm vi.
- Sửa broker hoặc policy engine kiểm tra grant.

Đây là các khả năng quản trị cơ chế cấp quyền. Nếu cùng role vừa thực hiện công việc vừa sửa được giới hạn của mình, phạm vi được mô tả ban đầu có thể không giữ được.

### 4.3. JIT và JEA bổ sung cho nhau

Just-in-Time giới hạn khi nào quyền được sử dụng. Just Enough Administration giới hạn công việc nào được làm.

Một phiên toàn quyền trong 15 phút có thời hạn ngắn nhưng vẫn có thể gây tác động rộng. Ngược lại, một role hẹp được cấp thường trực cho mọi người vẫn tạo quyền tồn đọng.

Thiết kế phù hợp thường kết hợp:

- Role nền có phạm vi hẹp.
- Điều kiện sử dụng theo nhiệm vụ.
- Phiên đủ ngắn cho công việc.
- Giới hạn tài nguyên và hành động.
- Cơ chế theo dõi và chặn tiếp tục sử dụng khi cần.

Không nên chọn thời hạn chỉ để đạt một con số đẹp. Cần cân bằng thời gian tác nghiệp, khả năng refresh và khả năng ứng phó khi credential bị lộ.

## 5. Workflow tham khảo cho người vận hành

### 5.1. Toàn cảnh

~~~text
Người vận hành
    |
    v
Đăng nhập doanh nghiệp và kiểm tra điều kiện xác thực
    |
    v
Gửi yêu cầu: nhiệm vụ + role + tài nguyên + thời gian
    |
    v
PAM kiểm tra policy, owner và phê duyệt nếu cần
    |
    v
Tạo grant có phạm vi, thời hạn và mã tương quan
    |
    v
Đường cấp phiên kiểm tra grant và gọi dịch vụ token
    |
    v
Nhận phiên tạm thời theo phạm vi được thực thi
    |
    v
Xác minh danh tính hiệu lực, thực hiện công việc, lưu audit
    |
    v
Kết thúc: ngăn cấp tiếp, quản lý credential và đối soát
~~~

Sơ đồ mô tả trách nhiệm. Tùy kiến trúc, cổng PAM có thể không trực tiếp giữ credential. Một broker, cơ chế federation hoặc credential provider có thể thực hiện phần cấp phiên.

### 5.2. Bước 1: xác thực danh tính và ngữ cảnh

PAM cần biết người thật đang yêu cầu, trạng thái tài khoản và điều kiện xác thực phù hợp với mức quyền.

Với người dùng, có thể yêu cầu xác thực tăng cường theo policy. Tuy nhiên, phải hiểu cách bằng chứng xác thực được truyền tới điểm cấp phiên. Không mặc định một claim hoặc condition của luồng xác thực trực tiếp cũng xuất hiện trong mọi luồng federation.

Mục tiêu là xác minh điều kiện tại đúng nơi có quyền quyết định. Một dòng chữ “đã MFA” do client tự gửi không phải bằng chứng đáng tin cậy.

### 5.3. Bước 2: đánh giá nhu cầu và tạo grant

Một grant minh họa:

~~~yaml
grantId: GRANT-2841
requester: operator-017
purpose: Kiem tra loi doi soat hoa don
target:
  account: "444455556666"
  environment: production
  role: billing-evidence-reader
scope:
  actions:
    - read-approved-evidence
  resourceSet: billing-run-2026-11-26
validity:
  startsAt: "2026-11-26T14:00:00+07:00"
  endsAt: "2026-11-26T14:30:00+07:00"
approval:
  policy: production-evidence-read
  reference: CHG-2841
state: approved
~~~

Đây là schema nghiệp vụ minh họa của hệ thống PAM, không phải policy AWS có thể gửi trực tiếp cho STS. Các tên hành động trừu tượng cần được ánh xạ sang quyền thật và tài nguyên thật.

Grant phải được lưu trong hệ thống có kiểm soát truy cập. Client không được tự sửa requester, resourceSet hoặc state rồi dùng bản đã sửa để nhận credential.

### 5.4. Bước 3: cấp phiên qua đường được kiểm soát

Điểm cấp phiên cần kiểm tra lại:

1. Grant còn tồn tại và còn hiệu lực.
2. Người yêu cầu hoặc workload đúng với grant.
3. Role và account đúng với đích đã duyệt.
4. Phạm vi tài nguyên được ánh xạ chính xác.
5. Yêu cầu không xin thời hạn hoặc khả năng vượt phạm vi.
6. Không có quyết định thu hồi đang áp dụng.
7. Mã tương quan được gắn theo quy tắc để truy vết.

Việc có grant không đồng nghĩa phiên tự bị giới hạn theo mọi trường của grant. Kiến trúc phải chuyển các giới hạn cần thiết thành policy, role, điều kiện hoặc điểm thực thi thực tế.

Nếu grant chỉ liệt kê hai object nhưng role đích vẫn đọc cả bucket và không có giới hạn bổ sung, hệ thống chưa thực thi được phạm vi đã hứa.

### 5.5. Bước 4: xác minh danh tính hiệu lực

Trước thao tác nhạy cảm, cần xác minh đang dùng đúng:

- Account.
- Role.
- Phiên và nhiệm vụ.
- Môi trường.
- Vùng hoặc dịch vụ liên quan nếu có.

Một công cụ có nhiều profile, biến môi trường hoặc cache dễ dùng nhầm credential. Việc giao diện PAM hiển thị đúng role không bảo đảm tiến trình đang gọi API bằng role đó.

Xác minh danh tính chỉ là một kiểm tra ngữ cảnh. Nó không thay thế phép thử cho hành động và tài nguyên cụ thể.

### 5.6. Bước 5: kết thúc và đối soát

Khi người dùng bấm kết thúc:

- Không cấp thêm phiên hoặc refresh ngoài điều kiện.
- Đóng luồng tương tác theo khả năng hệ thống.
- Xử lý credential được lưu ở nơi hệ thống quản lý.
- Xác định phiên cloud còn hiệu lực hay đã bị chặn quyền.
- Đối soát hành động với công việc được duyệt.
- Lưu bằng chứng và đánh dấu grant kết thúc.

Không ghi “đã thu hồi toàn bộ quyền” chỉ vì cửa sổ trình duyệt đã đóng.

## 6. Phê duyệt phải nằm trên đường thực thi

### 6.1. Rủi ro của phê duyệt chỉ ở giao diện

Giả sử cổng PAM buộc người dùng xin duyệt, nhưng principal nguồn vẫn có thể gọi STS trực tiếp để vào cùng role. Khi đó, luồng phê duyệt chỉ là quy trình giao diện; nó chưa kiểm soát toàn bộ đường cấp phiên.

Một phép thử quan trọng là: với cùng principal nguồn nhưng không có grant hợp lệ, có thể tạo phiên đích bằng CLI, SDK hoặc API khác không?

Nếu có, phải xác định đó là đường được phép theo thiết kế hay lỗ hổng của ranh giới PAM.

### 6.2. Các hướng thiết kế

Có thể áp dụng một hoặc kết hợp nhiều cách:

- Chỉ broker được phép vào role tác nghiệp; broker kiểm tra grant trước khi cấp phiên.
- Cấp entitlement hoặc quyền nguồn có hạn qua cơ chế được kiểm soát.
- Dùng role riêng cho nhiệm vụ có phạm vi rõ, thay vì mọi yêu cầu cùng vào một role rộng.
- Đặt điều kiện tại điểm tài nguyên mà ngữ cảnh được bảo vệ có thể đáp ứng.
- Giới hạn đường phát hành credential và bảo vệ cấu hình của đường đó.

Mỗi cách có rủi ro riêng. Broker có thể trở thành tài sản đặc quyền cao; entitlement có thể bị chậm thu hồi; role theo nhiệm vụ có thể tăng chi phí quản lý.

Phải chọn ranh giới có thể kiểm chứng trong hạ tầng thực tế, không chỉ thêm một mã ticket vào tên phiên.

### 6.3. Tránh broker trở thành confused deputy trong chính tổ chức

Broker cần phân biệt:

- Ai được yêu cầu.
- Được yêu cầu thay mặt ai.
- Được chọn role nào.
- Được chọn account nào.
- Được ánh xạ tới tài nguyên nào.
- Được đặt giá trị ngữ cảnh nào.

Nếu broker nhận tùy ý role ARN từ request rồi sử dụng quyền rộng của mình để assume, người dùng có thể mượn broker làm việc ngoài quyền của họ.

Cần có danh mục đích được quản lý, kiểm tra owner và xác thực mọi tham chiếu. Không dùng quyền của broker làm căn cứ rằng người yêu cầu cũng được phép.

## 7. Workload cần workflow riêng

### 7.1. Danh tính máy không phải tài khoản người dùng được tự động hóa

Workload có thể là:

- Pipeline triển khai.
- Job kiểm kê.
- Agent sao lưu.
- Dịch vụ luân chuyển credential.
- Công cụ vận hành theo lịch.

Không dùng tài khoản người dùng kèm credential cá nhân để giữ công việc tự động hoạt động. Cần owner, mục đích, phạm vi runtime và vòng đời danh tính máy riêng.

### 7.2. Cấp quyền dựa trên workload và lần chạy

Một yêu cầu của pipeline nên gắn với những thuộc tính phù hợp như:

- Repository hoặc nguồn mã được tin cậy.
- Workflow hoặc loại job.
- Môi trường phát hành.
- Phiên bản đã được duyệt.
- Run ID.
- Tài nguyên đích.
- Thời hạn tối đa.

Các thuộc tính có giá trị khi nguồn phát hành được tin cậy và mapping được bảo vệ. Một biến do người sửa mã tùy ý đặt không nên tự trở thành căn cứ cấp quyền production.

### 7.3. Hạn chế credential dài hạn và refresh không giới hạn

Ưu tiên cơ chế danh tính workload phù hợp với nền tảng. Nếu bắt buộc dùng credential nguồn lưu trong vault, cần kiểm soát ai lấy được, mục đích, thời hạn, luân chuyển và thu hồi.

Phiên ngắn không giảm quyền tồn đọng nếu workload có thể liên tục nhận phiên mới bằng một quyền nguồn thường trực quá rộng. Cần quản lý cả khả năng tái cấp.

Khi job kết thúc, thiết kế phải xác định rõ credential nào còn tồn tại và ai có thể dùng lại. Tránh dùng chung cache giữa các job không cùng ranh giới tin cậy.

## 8. Ngữ cảnh phiên và khả năng truy vết

### 8.1. Tên phiên giúp liên kết, không chứng minh danh tính

Một tên như chg2841-operator017 có thể hỗ trợ tìm kiếm. Nhưng nếu người gọi tự chọn được mọi giá trị, tên đó không chứng minh operator017 thực sự là người gọi hoặc CHG-2841 đã được duyệt.

Quy tắc đặt tên cần đi cùng:

- Danh tính đã xác thực.
- Kiểm tra quyền đặt trường.
- Bản ghi grant.
- Sự kiện tạo phiên.
- Sự kiện sử dụng phiên.

Không đưa thông tin cá nhân hoặc bí mật không cần thiết vào tên phiên, vì tên có thể xuất hiện trong nhiều hệ thống log.

### 8.2. Source identity

AWS hỗ trợ source identity để liên kết hoạt động của phiên với danh tính nguồn. Khi đã được đặt, giá trị không đổi trong phiên và được giữ qua role chaining. Việc dùng tính năng này cần quyền và trust tương ứng, bao gồm yêu cầu liên quan đến SetSourceIdentity. Giá trị vẫn cần được ràng buộc với nguồn đáng tin cậy; bản thân một chuỗi do client chọn không xác thực danh tính. [Theo dõi hoạt động của assumed role](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_control-access_monitor.html).

Trong thiết kế PAM, nên xác định rõ ai được đặt giá trị này và cơ chế mapping tới người hoặc workload. Không dùng một quy tắc chỉ kiểm tra tiền tố hợp lệ làm bằng chứng đầy đủ về danh tính.

### 8.3. Thuộc tính dùng để cấp quyền phải được bảo vệ

Nếu session attribute hoặc tag ảnh hưởng tới quyền tài nguyên, cần quản lý khả năng đặt chúng như một quyền bảo mật.

Ví dụ, nếu thuộc tính environment=production mở quyền production, người yêu cầu không được tùy ý tự gán thuộc tính ấy chỉ vì API cho phép truyền một chuỗi.

Tương tự, thuộc tính ticket=CHG-2841 không thay thế việc tra cứu trạng thái phê duyệt. Một trường phục vụ truy vết và một điều kiện dùng để cấp quyền có trách nhiệm khác nhau.

### 8.4. External ID trong truy cập bên thứ ba

External ID dùng để giảm rủi ro confused deputy khi một nhà cung cấp assume role cho nhiều khách hàng. Nhà cung cấp cần dùng đúng giá trị riêng cho khách hàng và phía khách hàng yêu cầu giá trị đó trong trust. AWS không coi external ID là secret; nó không thay thế credential hay xác thực principal. [Truy cập account qua bên thứ ba](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_common-scenarios_third-party.html).

Một kiểm thử hữu ích cho tích hợp là yêu cầu thiếu hoặc sai external ID phải bị chặn khi trust đã được thiết kế bắt buộc trường này. Không thêm external ID như một “mật khẩu phụ” rồi giữ nguyên trust quá rộng.

## 9. Role chaining và quyền quản trị gián tiếp

### 9.1. Kiểm kê đường đi, không chỉ role cuối

Một đường truy cập có thể là:

~~~text
Người dùng -> role nền -> role vận hành -> role quản trị khác account
~~~

Mỗi chặng làm tăng yêu cầu về:

- Trust.
- Mapping danh tính.
- Điều kiện phiên.
- Log tương quan.
- Khả năng thu hồi.
- Giới hạn thời gian.
- Rà soát quyền hiệu lực.

Không nên thêm chặng chỉ để có thêm một role mang tên “PAM”. Mỗi chặng phải phục vụ một ranh giới cụ thể.

### 9.2. Không mặc định quyền giới hạn ở chặng trước truyền sang chặng sau

Nếu phiên đầu có phạm vi hẹp nhưng được phép tạo phiên ở role đích rộng, chặng sau có thể tạo ra khả năng vượt mục tiêu ban đầu.

Cần kiểm tra riêng quyền và điều kiện của role đích. Các giới hạn của grant phải tiếp tục được thực thi ở nơi gây tác động; không suy ra chúng từ việc người gọi đã đi qua một phiên trước đó.

Thiết kế nên hạn chế role nào được assume tiếp và mục đích của từng đường. Có thể dùng role trực tiếp phù hợp thay vì một chuỗi dài khó kiểm chứng.

### 9.3. AssumeRole khác PassRole

AssumeRole tạo phiên để principal sử dụng role. PassRole là quyền cho phép chuyển một role cho dịch vụ AWS sử dụng trong ngữ cảnh cấu hình tài nguyên phù hợp. Người không tự assume được role vẫn có thể gây tác động qua dịch vụ nếu được gắn role mạnh vào workload mà họ kiểm soát. [Quyền PassRole của AWS IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html).

Vì vậy, khi kiểm kê quyền đặc biệt, cần xét cả quyền tạo hoặc sửa workload, quyền thay mã và khả năng gắn danh tính. Chỉ chặn một đường AssumeRole không đủ nếu còn đường thực thi gián tiếp mạnh tương đương.

## 10. Ví dụ sử dụng profile và xác minh phiên

### 10.1. Cấu hình minh họa

Với một nguồn credential đã được cấu hình hợp lệ, AWS CLI có thể dùng profile role để tự gọi AssumeRole và quản lý credential tạm thời, bao gồm cache và refresh theo cơ chế của CLI. Cần bảo vệ cache và kiểm soát khả năng nhận phiên mới. [Dùng IAM role trong AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-role.html).

~~~ini
[profile billing-evidence]
role_arn = arn:aws:iam::444455556666:role/billing-evidence-reader
source_profile = approved-source
role_session_name = chg2841-op017
duration_seconds = 900
~~~

Ví dụ chỉ minh họa cách một profile đích tham chiếu nguồn. Nó không tạo grant PAM và không chứng minh approved-source đã trải qua phê duyệt. Việc đặt tên profile có chữ approved không tạo thuộc tính bảo mật nào.

Nguồn phải được thiết lập bằng cơ chế phù hợp của tổ chức. Không đưa secret access key vào tệp ví dụ hoặc yêu cầu người dùng chia sẻ credential của broker.

### 10.2. Kiểm tra trước khi thực hiện công việc

Trong môi trường thử nghiệm được phép, có thể xác minh danh tính của profile trước khi thử quyền tài nguyên. Đầu ra cần được đối chiếu với account và role mong đợi.

Sau đó, kiểm thử hai nhóm:

- Hành động cần thiết trên tài nguyên được duyệt.
- Hành động ngoài phạm vi phải bị từ chối.

Không dùng một thao tác sửa hoặc xóa production chỉ để thử role. Chọn tài nguyên lab và phép thử có tác động được kiểm soát.

### 10.3. Tránh lẫn nguồn và đích

Một số lỗi vận hành phổ biến:

- Terminal còn biến môi trường credential của phiên khác.
- Công cụ con không dùng cùng profile.
- IDE hoặc SDK có credential provider khác CLI.
- Một tiến trình tiếp tục chạy sau khi người dùng đóng giao diện.
- Job đọc cache hoặc mount của job trước.

Cần xác định công cụ nào thực sự giữ credential và cơ chế chọn credential của nó. Kiểm tra account trên giao diện khác không thay thế kiểm tra của tiến trình đang gọi API.

## 11. Bằng chứng cần lưu

### 11.1. Chuỗi liên kết tối thiểu

~~~text
Yêu cầu nghiệp vụ
        |
        v
Quyết định policy hoặc phê duyệt
        |
        v
Grant PAM
        |
        v
Sự kiện tạo phiên
        |
        v
Hành động trên tài nguyên
        |
        v
Hết hạn / chặn quyền / đối soát
~~~

Một hồ sơ tốt cho phép trả lời:

- Ai yêu cầu và ai phê duyệt?
- Role nào, account nào và phạm vi nào?
- Grant còn hiệu lực khi tạo phiên không?
- Phiên nào thực hiện hành động nào?
- Hành động có nằm trong nhu cầu được duyệt không?
- Khi kết thúc hoặc thu hồi, hệ thống đã làm gì?
- Có dấu hiệu sử dụng ngoài luồng hoặc tái cấp bất thường không?

### 11.2. Bản ghi PAM minh họa

~~~json
{
  "event": "privileged_session_issued",
  "grantId": "GRANT-2841",
  "changeId": "CHG-2841",
  "requester": "operator-017",
  "issuer": "pam-session-service",
  "targetAccount": "444455556666",
  "targetRole": "billing-evidence-reader",
  "roleSessionName": "chg2841-op017",
  "scopeReference": "billing-run-2026-11-26",
  "decision": "allow",
  "correlationId": "pam-session-019"
}
~~~

Đây là bản ghi nghiệp vụ đề xuất, không phải mẫu CloudTrail nguyên bản. Tránh coi các tên trường minh họa là thuộc tính luôn có trong log cloud.

Không lưu credential vào bằng chứng. Khi cần lưu thông tin tương quan, chỉ dùng metadata phù hợp và bảo vệ quyền đọc log.

### 11.3. Kiểm tra độ bao phủ log

Không giả định mọi thao tác trên mọi loại tài nguyên đều tự xuất hiện trong cùng một nguồn log.

Khi triển khai, cần xác minh:

- Sự kiện tạo phiên được thu ở đâu.
- Hoạt động dịch vụ đích được thu theo cấu hình nào.
- Có loại thao tác cần bật log riêng không.
- Độ trễ và thời gian lưu.
- Account nào giữ bằng chứng.
- Principal nào có quyền sửa cấu hình audit.
- Cách phát hiện thiếu sự kiện.

Nếu yêu cầu nghiệp vụ là đọc hai object, log chỉ cho biết đã assume role chưa đủ chứng minh đã truy cập object nào.

### 11.4. Giám sát API không đồng nghĩa ghi hình phiên

Assume-role thường phục vụ API hoặc công cụ tự động. Không phải lần sử dụng nào cũng có terminal hoặc màn hình để ghi.

Có thể cần kết hợp log API, sự kiện PAM, log pipeline và ghi phiên tương tác khi phù hợp. Ghi hình màn hình không thay thế log tài nguyên; log API cũng không tự cung cấp toàn bộ ngữ cảnh thao tác của người dùng.

## 12. Hết hạn, ngăn cấp mới và thu hồi

### 12.1. Ba trạng thái độc lập

| Việc cần làm | Tác động mong đợi |
| --- | --- |
| Ngăn cấp phiên mới | Principal không nhận thêm credential cho role |
| Chặn quyền phiên hiện hữu | Credential đã cấp không tiếp tục thực hiện hành động bị chặn |
| Xử lý tác động đã xảy ra | Khôi phục cấu hình, đánh giá dữ liệu và xử lý quyền phát sinh |

Thay trust để ngăn assume mới không nên được coi là bằng chứng rằng mọi phiên cũ đã mất quyền. Tương tự, xóa credential ở một máy không chứng minh bản bị sao chép ở máy khác không dùng được.

### 12.2. Thu hồi trong AWS phải theo đúng cơ chế

Với IAM role thông thường, AWS có cơ chế gắn policy từ chối các phiên được tạo trước một mốc thời gian; việc này có thể ảnh hưởng nhiều người dùng của cùng role. Các role từ permission set của IAM Identity Center cần theo quy trình thu hồi tương ứng của Identity Center. [Thu hồi credential tạm thời của IAM role](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html).

Runbook phải xác định loại role, phạm vi ảnh hưởng và cách kiểm tra sau thao tác. Không dùng một thao tác thu hồi diện rộng như thể chỉ đóng một phiên của một người.

### 12.3. Kiểm tra hiệu lực của việc chặn

Sau khi thực hiện biện pháp thu hồi:

1. Xác minh không thể nhận phiên mới qua đường bị chặn.
2. Dùng phép thử được kiểm soát với phiên cũ để xác định quyền đã bị từ chối.
3. Kiểm tra broker, cache và job không tạo lại đường truy cập.
4. Theo dõi sự kiện sau mốc thu hồi.
5. Đánh giá tác động tới người dùng hoặc workload hợp lệ.
6. Lưu kết quả cùng thời điểm xác minh.

Cần tính tới độ trễ áp dụng của hệ thống và ranh giới kiểm tra. Một lỗi mạng không chứng minh credential đã bị chặn quyền.

### 12.4. Thu hồi không dừng mọi tác động đang diễn ra

Một phiên có thể đã:

- Tạo job.
- Thay cấu hình.
- Triển khai workload.
- Tạo principal khác.
- Xuất dữ liệu.
- Cấp quyền cho tài nguyên khác.

Các tác động ấy cần được điều tra và xử lý riêng. Phiên đã bị chặn không có nghĩa cấu hình đã trở về trạng thái trước hoặc dữ liệu đã được thu hồi.

## 13. Kịch bản sự cố: credential của phiên bị lộ

### 13.1. Bối cảnh

Một job chẩn đoán vô tình ghi bộ credential tạm thời vào artifact. Phiên có quyền đọc một nhóm báo cáo production.

Owner phát hiện khi phiên chưa hết hạn. Một phản ứng chỉ xóa artifact sẽ không đủ vì không biết đã có ai tải bản sao hay chưa.

### 13.2. Trình tự xử lý tham khảo

- Giữ bằng chứng cần thiết và hạn chế tiếp tục truy cập artifact.
- Xác định role, thời điểm cấp, grant và nguồn phát hành.
- Ngăn tái cấp nếu nguồn hoặc grant có nguy cơ bị lạm dụng.
- Dùng cơ chế phù hợp để chặn quyền của phiên bị ảnh hưởng.
- Xác minh biện pháp chặn bằng phép thử kiểm soát.
- Tra cứu hoạt động của phiên trong các nguồn log có phạm vi phù hợp.
- Đánh giá dữ liệu đã được truy cập hoặc quyền phát sinh.
- Sửa nơi làm lộ credential và kiểm tra các bản sao liên quan.
- Khôi phục truy cập hợp lệ bằng phiên mới khi điều kiện đã đạt.

Mức độ thu hồi phụ thuộc khả năng nền tảng. Nếu cần chặn nhiều phiên của cùng role, phải đánh giá ảnh hưởng tác nghiệp và phối hợp theo quy trình sự cố đã được định trước.

### 13.3. Bài học thiết kế

Credential ngắn hạn giúp giới hạn cửa sổ sử dụng nhưng không thay thế kiểm soát log và artifact. Quyền role hẹp giúp giảm phạm vi ảnh hưởng; khả năng truy vết giúp xác định điều gì đã xảy ra.

Không tăng thời hạn phiên hoặc chuyển sang credential dài hạn chỉ để tránh lỗi refresh trước khi hiểu nguyên nhân.

## 14. Ma trận kiểm thử workflow

Kiểm thử cần bao phủ cả tạo phiên và sử dụng phiên.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Người hợp lệ, grant còn hiệu lực, role và tài nguyên khớp | Tạo phiên đúng điều kiện |
| Không có grant nhưng gọi đường cấp qua broker | Từ chối tại kiểm tra grant |
| Người dùng gọi trực tiếp một đường được thiết kế chỉ cho broker | Từ chối |
| Đổi role ARN sang role khác | Từ chối theo danh mục và quyền |
| Dùng grant staging để xin quyền production | Từ chối theo môi trường và account |
| Grant hết hạn trước thời điểm cấp | Không cấp phiên mới |
| Yêu cầu thời hạn vượt giới hạn cho phép | Từ chối hoặc giới hạn theo hợp đồng được công bố |
| Giả mạo requester trong payload | Không thay thế danh tính đã xác thực |
| Tên phiên chứa mã ticket hợp lệ nhưng ticket chưa được duyệt | Không coi tên phiên là phê duyệt |
| Phiên đọc đúng object được duyệt | Cho phép và có bằng chứng theo cấu hình log |
| Phiên đọc object ngoài phạm vi | Từ chối |
| Phiên thử sửa policy, trust hoặc audit | Từ chối nếu ngoài nhiệm vụ |
| Phiên thử assume role khác không được phép | Từ chối |
| Người dùng kết thúc phiên ở giao diện | Hệ thống báo đúng trạng thái credential còn hay mất hiệu lực |
| Thực hiện thu hồi | Kiểm tra cả cấp mới và quyền phiên cũ |
| Refresh sau khi grant kết thúc | Không tự tiếp tục cấp ngoài policy |
| Log tài nguyên chưa được bật đúng | Phát hiện thiếu bằng chứng trước khi coi workflow đạt |
| Một phiên đã tạo job trước khi bị chặn | Job được xử lý theo hợp đồng riêng |

Đối với truy cập bên thứ ba dùng external ID, bổ sung trường hợp thiếu, sai và đúng external ID theo trust đã thiết kế. Đối với workload, bổ sung kiểm thử nguồn mã, run ID và môi trường không hợp lệ.

Một request AccessDenied cần được đối chiếu với log và điều kiện thực tế. Không ghi nhận mọi lỗi AccessDenied là thành công của đúng kiểm soát đang thử.

## 15. Bài thực hành: đọc báo cáo production theo nhiệm vụ

### 15.1. Bối cảnh

Nhóm Billing cần cho người trực ca đọc báo cáo của một lần xử lý để điều tra sai lệch. Trước đây mọi kỹ sư đều có quyền vào một role đọc toàn bộ kho báo cáo, và không có liên kết rõ giữa lần truy cập với ticket.

Yêu cầu mới:

- Chỉ người thuộc nhóm và còn đủ điều kiện được yêu cầu.
- Chỉ đọc tập báo cáo liên quan tới nhiệm vụ.
- Không sửa dữ liệu hoặc policy.
- Quyền dùng trong khoảng thời gian được duyệt.
- Không có đường cấp phiên bỏ qua điều kiện.
- Có bằng chứng từ yêu cầu tới hành động.
- Có runbook khi credential bị lộ.

### 15.2. Thiết kế cần nộp

1. Sơ đồ principal nguồn, điểm cấp phiên và role đích.
2. Inventory owner, trust và quyền hiệu lực.
3. Schema grant với tài nguyên và thời hạn.
4. Cách ánh xạ grant sang kiểm soát cloud.
5. Cách phân biệt role tác nghiệp với role quản trị.
6. Cách bảo vệ credential và cache.
7. Kế hoạch log và đối soát.
8. Ma trận kiểm thử âm tính.
9. Quy trình thu hồi và phạm vi ảnh hưởng.

### 15.3. Các câu hỏi bắt buộc trả lời

- Nếu cổng PAM không hoạt động, người dùng có còn đường assume trực tiếp không?
- Nếu role đích đọc rộng hơn grant, giới hạn thực sự nằm ở đâu?
- Ai được thay trust và policy của role?
- Broker có được tùy ý chọn account hoặc role không?
- Một grant được duyệt có thể bị dùng lại để cấp nhiều phiên không?
- Khi nào refresh được phép?
- Một phiên cũ còn làm gì sau khi grant kết thúc?
- Nếu phải thu hồi toàn role, ai bị ảnh hưởng?
- Nguồn log nào chứng minh object đã được đọc?

Không có một đáp án kiến trúc duy nhất. Bài đạt khi ranh giới quyền được mô tả, được thực thi và có thể kiểm chứng bằng trường hợp ngoài phạm vi.

## 16. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Role có tên readonly thì chắc chắn chỉ đọc | Cần xem quyền hiệu lực và mọi đường tác động gián tiếp |
| Tạo phiên thành công là đã có quyền tài nguyên | Mỗi request tài nguyên vẫn cần được cho phép |
| Session ngắn là đủ cho least privilege | Thời hạn và phạm vi là hai chiều khác nhau |
| Mã ticket trong tên phiên chứng minh phê duyệt | Cần kiểm tra bản ghi được tin cậy và ràng buộc |
| MFA ở một nơi tự bảo đảm mọi luồng cấp phiên | Cần hiểu và kiểm tra bằng chứng tại đúng đường xác thực |
| Source identity do client tự đặt luôn phản ánh người thật | Cần bảo vệ cách đặt và mapping giá trị |
| External ID là secret thay cho credential | Nó phục vụ điều kiện ngữ cảnh, không thay xác thực |
| Kết thúc trình duyệt là thu hồi credential | Credential hoặc tiến trình khác có thể vẫn tồn tại |
| Chặn assume mới là chặn toàn bộ phiên cũ | Hai trạng thái cần được xác minh riêng |
| Đổi khóa nguồn sẽ giải quyết mọi phiên đích | Cần xử lý credential đã cấp và quyền đang hiệu lực |
| Thu hồi phiên tự hoàn tác mọi thao tác | Tác động đã tạo phải được điều tra và xử lý riêng |

## 17. Chỉ số để duy trì kiểm soát

Các chỉ số có ích gồm:

- Tỷ lệ role đặc quyền có owner và mục đích rõ.
- Số đường assume-role ngoài luồng được duyệt.
- Số principal còn khả năng assume role rộng thường trực.
- Tỷ lệ phiên liên kết được với grant và hành động tài nguyên.
- Tỷ lệ grant kết thúc nhưng vẫn có thể tái cấp ngoài policy.
- Thời gian từ quyết định thu hồi tới khi phép thử quyền cũ bị chặn.
- Số role có quyền tự thay cơ chế giới hạn.
- Tỷ lệ workload dùng danh tính riêng thay cho credential cá nhân.
- Số phát hiện credential trong log, artifact hoặc mã nguồn.
- Số ngoại lệ và role chaining chưa có owner đánh giá.

Mỗi chỉ số cần nêu rõ phạm vi account, role và loại hoạt động. Không dùng tổng số sự kiện STS làm đại diện cho mức độ kiểm soát nếu chưa biết các phiên đã làm gì sau khi được cấp.

## 18. Câu hỏi tự kiểm tra

**Assume-role có phải là chia sẻ mật khẩu của một tài khoản quản trị không?**

Không. Nó tạo ngữ cảnh phiên với credential tạm thời. Tuy nhiên, credential của phiên vẫn phải được bảo vệ như bí mật.

**Vì sao phải kiểm tra cả trust và quyền tác nghiệp?**

Trust quyết định đường vào role; quyền tác nghiệp quyết định hành động trên tài nguyên. Hai quyết định giải quyết hai câu hỏi khác nhau.

**Vì sao phiên hẹp ở chặng trước không đủ bảo đảm chặng sau cũng hẹp?**

Mỗi role đích có quyền và điều kiện riêng. Cần thực thi lại ranh giới cần thiết ở nơi tạo quyền và gây tác động.

**Một broker được trust có thể nhận mọi role ARN từ người dùng không?**

Không nên. Broker phải xác minh người yêu cầu được dùng đúng đích đó theo grant và danh mục được quản lý.

**Vì sao credential ngắn hạn vẫn có thể tạo quyền tồn đọng?**

Nếu nguồn có thể liên tục nhận phiên mới bằng quyền thường trực rộng, khả năng sử dụng đặc quyền vẫn tồn tại.

**Bằng chứng assume-role có đủ để kiểm toán dữ liệu đã được đọc không?**

Chưa đủ. Cần liên kết tới hoạt động trên tài nguyên với cấu hình log có độ bao phủ phù hợp.

**Khi người dùng kết thúc nhiệm vụ, cần báo trạng thái gì?**

Cần báo đúng việc cấp tiếp đã dừng hay chưa, credential hiện hữu còn quyền hay đã bị chặn, và đối soát đã hoàn tất đến đâu.

Assume-role workflow đạt mục tiêu Cloud PAM khi nó kiểm soát được cả đường tạo phiên, quyền sử dụng trong phiên và vòng đời sau khi kết thúc nhiệm vụ. Phiên tạm thời là một thành phần của cơ chế đó; phạm vi quyền, ràng buộc grant, giám sát và khả năng thu hồi quyết định hiệu quả vận hành.
