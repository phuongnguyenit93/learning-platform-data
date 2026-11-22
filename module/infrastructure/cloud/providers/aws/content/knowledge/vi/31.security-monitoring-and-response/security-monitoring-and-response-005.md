# Amazon Detective và điều tra quan hệ sự kiện

Trong hệ sinh thái AWS, một sự cố an ninh thường để lại dấu vết ở nhiều nơi: hoạt động đăng nhập và gọi API trong AWS CloudTrail, kết nối mạng trong VPC Flow Logs, hoạt động của workload Kubernetes trong EKS audit logs và cảnh báo từ Amazon GuardDuty. Mỗi nguồn cho thấy một phần của câu chuyện. Khi người điều tra phải tự ghép các bản ghi rời rạc, họ dễ bỏ sót mối liên hệ giữa danh tính, địa chỉ IP, phiên truy cập, máy chủ và tài nguyên bị tác động.

Amazon Detective giúp rút ngắn quá trình đó. Dịch vụ thu thập và phân tích dữ liệu bảo mật từ các nguồn được hỗ trợ, xây dựng đồ thị hành vi cho môi trường AWS, rồi trình bày các thực thể và mối quan hệ của chúng theo thời gian. Người điều tra có thể bắt đầu từ một phát hiện, lần theo các thực thể liên quan, so sánh hoạt động hiện tại với hành vi thông thường và hình thành giả thuyết về nguyên nhân cũng như phạm vi ảnh hưởng.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: khám phá cách các dịch vụ AWS phối hợp trong giám sát và ứng phó an ninh. Trọng tâm là cách dùng Amazon Detective để điều tra quan hệ sự kiện, kết hợp ngữ cảnh về IAM, mạng VPC, tài nguyên tính toán và các nguồn nhật ký. Detective hỗ trợ phân tích; quyết định cô lập, thu hồi quyền hay khôi phục hệ thống vẫn cần quy trình ứng phó sự cố của tổ chức.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Amazon Detective trong quy trình giám sát và ứng phó sự cố trên AWS.
- Mô tả cách Detective xây dựng behavior graph từ dữ liệu bảo mật và cách biểu diễn thực thể, hoạt động, mối quan hệ.
- Lần theo một phát hiện từ GuardDuty để điều tra danh tính, IP, phiên truy cập và tài nguyên có liên quan.
- Đọc hồ sơ thực thể, phạm vi thời gian, hoạt động bất thường và nhóm phát hiện để hình thành dòng thời gian sự cố.
- Phân biệt nhiệm vụ của Detective với GuardDuty, AWS CloudTrail, VPC Flow Logs và AWS Security Hub.
- Nhận biết giới hạn dữ liệu, phạm vi Region, quyền truy cập và chi phí khi triển khai Detective.

## 2. Amazon Detective giải quyết vấn đề gì?

### 2.1. Nhật ký rời rạc khiến việc điều tra chậm

Giả sử GuardDuty phát hiện một IAM role có hoạt động API bất thường. Để xác định sự cố, nhóm bảo mật cần trả lời nhiều câu hỏi:

1. Danh tính nào đã thực hiện hành động? Đó là IAM user, assumed role session hay một dịch vụ AWS?
2. Phiên truy cập bắt đầu từ địa chỉ IP nào, vào thời điểm nào và ở Region nào?
3. Danh tính đó đã gọi những API nào trước và sau phát hiện?
4. Phiên truy cập có liên hệ với EC2 instance, S3 bucket, EKS workload hoặc tài nguyên nào khác?
5. Hành vi này có khác với hoạt động bình thường của danh tính hoặc tài nguyên không?
6. Có phát hiện nào khác cùng liên quan đến IP, danh tính hoặc tài nguyên đó không?

Nếu chỉ xem từng sự kiện CloudTrail, từng bản ghi mạng và từng finding riêng lẻ, người điều tra phải tự nối các mảnh thông tin. Việc này tốn thời gian và dễ bỏ qua một hoạt động xảy ra trước thời điểm cảnh báo.

### 2.2. Detective cung cấp ngữ cảnh và mối liên hệ

Amazon Detective phân tích dữ liệu từ các nguồn được hỗ trợ để tạo behavior graph. Đồ thị mô hình hóa các thực thể trong môi trường AWS, hoạt động của chúng và những mối quan hệ có thể quan sát được. Detective cũng dùng phân tích thống kê và học máy để giúp người điều tra hiểu hoạt động theo thời gian, bao gồm cả việc so sánh với đường cơ sở hành vi.

Ví dụ, khi xem một IAM role, người điều tra có thể lần theo các phiên role được sử dụng, địa chỉ IP liên quan, hoạt động API và những tài nguyên mà các phiên đó tương tác. Khi xem một IP, họ có thể kiểm tra IP đó từng liên hệ với những danh tính hoặc workload nào trong phạm vi dữ liệu sẵn có.

Detective giúp trả lời câu hỏi “những sự kiện và thực thể này có liên hệ với nhau như thế nào?”. Nó không tự kết luận mọi hoạt động bất thường đều là tấn công, cũng không tự thay thế người điều tra trong việc xác minh bằng chứng.

## 3. Behavior graph và dữ liệu đầu vào

### 3.1. Behavior graph là gì?

Behavior graph là mô hình phân tích của Detective cho một môi trường AWS trong một Region. Graph được xây dựng từ dữ liệu của tài khoản đã bật Detective và các tài khoản thành viên được chia sẻ vào graph quản trị. Detective phân tích hoạt động theo thời gian và liên kết dữ liệu với các thực thể có liên quan.

Một số đặc điểm cần ghi nhớ:

- **Theo Region:** Detective hoạt động theo phạm vi Region. Khi điều tra môi trường nhiều Region, cần bảo đảm Detective được bật và dữ liệu cần thiết có mặt ở từng Region liên quan.
- **Theo tài khoản:** Một graph có thể bao gồm tài khoản quản trị và các tài khoản thành viên. Tổ chức nhiều tài khoản có thể dùng tài khoản quản trị Detective được ủy quyền để điều phối phạm vi điều tra.
- **Dữ liệu tích lũy:** Giá trị của phân tích phụ thuộc vào thời gian thu thập và độ bao phủ của nguồn dữ liệu. Một graph mới bật có thể chưa có đủ lịch sử để tạo bức tranh hành vi phong phú.
- **Không phải kho lưu trữ mọi loại log:** Detective phân tích những nguồn dữ liệu mà dịch vụ hỗ trợ. Với điều tra chuyên sâu, người vận hành vẫn cần truy cập nguồn nhật ký gốc hoặc hệ thống lưu trữ log của tổ chức.

### 3.2. Những nguồn dữ liệu chính

Các nguồn dữ liệu cốt lõi thường gặp trong điều tra AWS gồm:

| Nguồn | Thông tin cung cấp | Giá trị khi điều tra |
|---|---|---|
| AWS CloudTrail | Sự kiện quản lý và hoạt động API của AWS, danh tính gọi API, thời gian, Region, nguồn truy cập và tài nguyên liên quan | Dựng lại chuỗi hành động của user, role hoặc phiên dịch vụ |
| VPC Flow Logs | Thông tin luồng mạng IP trong VPC như địa chỉ nguồn/đích, cổng, giao thức và trạng thái luồng | Xác định liên hệ mạng, lưu lượng bất thường và kết nối giữa workload với địa chỉ bên ngoài |
| EKS audit logs | Hoạt động gọi Kubernetes API trong cụm EKS khi nguồn này được cấu hình và hỗ trợ | Điều tra hành động đối với cluster, workload và tài nguyên Kubernetes |
| Amazon GuardDuty findings | Phát hiện bảo mật do GuardDuty tạo ra | Cung cấp điểm bắt đầu cho cuộc điều tra và ngữ cảnh về mối đe dọa đã được phát hiện |

Phạm vi nguồn dữ liệu và khả năng tích hợp có thể thay đổi theo tính năng, Region và cấu hình tài khoản. Khi triển khai, hãy kiểm tra trang cấu hình Detective trong Region mục tiêu để xác nhận nguồn nào đang được thu thập và có được bật hay không.

CloudTrail, VPC Flow Logs và EKS audit logs cung cấp các góc nhìn khác nhau. CloudTrail mô tả hoạt động trên mặt phẳng điều khiển AWS; VPC Flow Logs mô tả luồng mạng; EKS audit logs mô tả yêu cầu đến Kubernetes API. GuardDuty bổ sung các phát hiện bảo mật được tạo từ dữ liệu mà dịch vụ phân tích. Kết hợp các góc nhìn này giúp người điều tra hiểu cả hành động lẫn đường đi của hoạt động đáng ngờ.

### 3.3. Thực thể và quan hệ

Tùy loại dữ liệu và hoạt động quan sát được, Detective có thể liên kết các thực thể như:

- Tài khoản AWS.
- IAM user, IAM role và phiên assumed role.
- Địa chỉ IP.
- EC2 instance.
- S3 bucket.
- EKS cluster và các thực thể Kubernetes được hỗ trợ.

Hãy xem một chuỗi quan hệ minh họa:

~~~text
Địa chỉ IP bên ngoài
        |
        | tạo hoạt động truy cập
        v
IAM role session
        |
        | thực hiện API call
        v
S3 bucket
        |
        | xuất hiện trong cùng chuỗi hoạt động
        v
Phát hiện GuardDuty
~~~

Đây là cách mô tả khái niệm, không phải cam kết rằng mọi loại quan hệ đều được hiển thị thành một cạnh đồ thị riêng. Detective chỉ có thể liên kết những gì dữ liệu nguồn và mô hình phân tích của dịch vụ hỗ trợ. Người điều tra nên mở hồ sơ từng thực thể và kiểm tra chi tiết hoạt động thay vì suy ra quan hệ chỉ từ hình vẽ.

### 3.4. Hành vi nền và bất thường

Một sự kiện riêng lẻ thường không đủ để kết luận. Ví dụ, một role gọi API ListBuckets có thể là hoạt động quản trị bình thường. Nhưng nếu role đó thường chỉ hoạt động từ một workload trong VPC, rồi đột ngột được sử dụng từ IP lạ, ở thời điểm ít xuất hiện và gọi thêm các API nhạy cảm, chuỗi hoạt động này đáng được xem xét.

Detective cung cấp các biểu đồ và số liệu để người điều tra xem hoạt động theo thời gian, quan sát thay đổi về tần suất và so sánh với hành vi nền. Hãy chú ý:

- Hoạt động tăng đột biến hoặc xuất hiện ở thời điểm bất thường.
- IP, Region, user agent hoặc nguồn truy cập mới trong bối cảnh của thực thể.
- Một danh tính bắt đầu truy cập loại tài nguyên trước đây chưa từng tương tác.
- Nhiều phát hiện cùng xuất hiện quanh một danh tính, IP hoặc tài nguyên.
- Hoạt động trước và sau thời điểm finding có thể cho thấy bước chuẩn bị, mở rộng quyền hoặc truy cập dữ liệu.

Hành vi nền là tín hiệu phân tích, không phải chính sách cho phép hay từ chối. Một hoạt động khác thường có thể hợp lệ trong một đợt triển khai, kiểm thử hoặc vận hành khẩn cấp. Cần đối chiếu với lịch thay đổi, chủ sở hữu hệ thống và bằng chứng gốc.

## 4. Quy trình điều tra bằng Amazon Detective

### 4.1. Chuẩn bị phạm vi quan sát

Trước khi điều tra, xác nhận các điều kiện sau:

1. Detective đã được bật trong Region chứa tài nguyên hoặc hoạt động cần điều tra.
2. Tài khoản AWS liên quan đã tham gia behavior graph phù hợp.
3. Các nguồn dữ liệu cần thiết đang được thu thập, chẳng hạn CloudTrail, VPC Flow Logs và EKS audit logs nếu có workload EKS.
4. GuardDuty được bật nếu quy trình điều tra bắt đầu từ GuardDuty findings.
5. Người điều tra có quyền IAM cần thiết để xem behavior graph, finding và hồ sơ thực thể.

Trong môi trường AWS Organizations, nên xác định tài khoản quản trị Detective được ủy quyền, quy trình thêm tài khoản thành viên và trách nhiệm của nhóm bảo mật. Việc quản trị tập trung giúp điều tra xuyên tài khoản, nhưng quyền xem dữ liệu vẫn cần được giới hạn theo vai trò công việc.

### 4.2. Bắt đầu từ finding

Một quy trình phổ biến là bắt đầu từ finding của GuardDuty:

1. Mở finding trong GuardDuty hoặc mở finding tương ứng trong Detective.
2. Xác nhận loại finding, thời gian, Region, tài khoản và thực thể được nêu.
3. Đặt phạm vi thời gian đủ rộng để xem hoạt động trước và sau thời điểm phát hiện.
4. Mở các thực thể liên quan, ví dụ IAM role, IP hoặc EC2 instance.
5. Kiểm tra hoạt động của từng thực thể và các finding khác có liên hệ.

Đừng chỉ xem đúng phút mà finding được tạo. Kẻ tấn công có thể đã chiếm thông tin xác thực trước đó, thử quyền truy cập trước khi hành động hoặc tiếp tục hoạt động sau khi cảnh báo xuất hiện. Phạm vi thời gian cần đủ rộng để dựng lại chuỗi sự kiện, đồng thời đủ hẹp để người điều tra tập trung vào tín hiệu liên quan.

### 4.3. Đọc hồ sơ thực thể

Hồ sơ thực thể tập hợp thông tin và biểu đồ hoạt động có liên quan đến một thực thể. Tùy loại thực thể, người điều tra có thể xem:

- Danh tính và thuộc tính nhận diện của thực thể.
- Hoạt động API hoặc hoạt động mạng theo thời gian.
- Những IP, tài khoản, role hoặc tài nguyên có liên quan.
- Các finding liên kết với thực thể.
- Thay đổi về tần suất hoạt động so với hành vi nền.

Khi xem IAM role, hãy kiểm tra phiên sử dụng role, nguồn truy cập và các API được gọi. Khi xem IP, hãy xác định các danh tính hoặc workload có hoạt động với IP đó. Khi xem EC2 instance, hãy kết hợp hoạt động mạng với những hành động quản lý instance trong CloudTrail. Mỗi góc nhìn trả lời một phần của câu chuyện.

### 4.4. Dựng dòng thời gian

Một dòng thời gian tốt phải cho thấy thứ tự và mối liên hệ của các sự kiện. Ví dụ:

| Thời điểm minh họa | Sự kiện | Câu hỏi điều tra |
|---|---|---|
| 09:02 | Một phiên role được sử dụng từ IP chưa quen thuộc | Phiên này thuộc workload hay người vận hành nào? |
| 09:04 | Phiên gọi các API liệt kê tài nguyên | Đây có phải hành vi thường lệ của role không? |
| 09:07 | Phiên truy cập một S3 bucket nhạy cảm | Bucket có thuộc phạm vi công việc của role không? |
| 09:10 | GuardDuty tạo finding liên quan | Finding dựa trên tín hiệu nào và còn thực thể nào liên quan? |
| 09:14 | Xuất hiện thêm hoạt động từ cùng IP | Đây là một phiên tiếp diễn hay một danh tính khác? |

Thời gian trong bảng chỉ minh họa phương pháp. Trong điều tra thật, hãy dùng timestamp từ dữ liệu nguồn, kiểm tra múi giờ và đối chiếu với thời gian hiển thị trong từng dịch vụ.

### 4.5. Mở rộng từ một thực thể sang các thực thể liên quan

Sau khi xác định thực thể trọng tâm, lần theo các quan hệ có ý nghĩa:

- Từ finding sang IAM principal hoặc role session.
- Từ role session sang IP nguồn và chuỗi API call.
- Từ IP sang những danh tính hoặc workload khác từng liên hệ với IP đó.
- Từ EC2 instance sang luồng mạng và hoạt động quản lý instance.
- Từ hoạt động EKS sang cluster hoặc workload có liên quan.

Khi một IP liên hệ với nhiều role, hãy kiểm tra xem đó có phải NAT gateway, proxy doanh nghiệp, VPN hay dịch vụ dùng chung không. Một IP dùng chung không đủ để kết luận nhiều danh tính bị cùng một tác nhân kiểm soát. Tương tự, hai sự kiện gần nhau về thời gian chưa chắc có quan hệ nhân quả.

### 4.6. Xác minh giả thuyết bằng dữ liệu gốc

Detective giúp tìm mối liên hệ và định hướng điều tra. Khi cần xác nhận một hành động cụ thể, hãy đối chiếu với nguồn gốc:

- Dùng CloudTrail event history hoặc trail đã lưu để xác minh API, principal, request parameters và kết quả.
- Dùng VPC Flow Logs để kiểm tra luồng mạng, địa chỉ, cổng và thời điểm.
- Dùng EKS audit logs để xác minh yêu cầu Kubernetes API.
- Kiểm tra cấu hình IAM, resource policy, security group và lịch triển khai có liên quan.
- Trao đổi với chủ sở hữu workload để xác nhận hoạt động vận hành hợp lệ.

Nếu cần lưu bằng chứng, hãy tuân thủ quy trình quản lý chứng cứ của tổ chức: giữ nguyên bản ghi, ghi lại thời điểm truy xuất, nguồn, phạm vi và người thực hiện. Không sửa hoặc xóa log gốc trong quá trình điều tra.

### 4.7. Chuyển kết quả sang ứng phó sự cố

Khi có đủ bằng chứng, nhóm ứng phó có thể quyết định hành động phù hợp, chẳng hạn vô hiệu hóa access key bị lộ, điều chỉnh trust policy của role, chặn luồng mạng, cô lập EC2 instance hoặc hạn chế quyền truy cập vào tài nguyên dữ liệu. Hành động cụ thể phải dựa trên mức độ ảnh hưởng, quyền hạn của người xử lý và quy trình phê duyệt sự cố.

Amazon Detective tập trung vào điều tra và phân tích. Dịch vụ không thay thế các công cụ thực thi hành động ứng phó. Có thể phối hợp với IAM, EC2, VPC security groups, AWS Systems Manager, AWS Security Hub, EventBridge hoặc hệ thống SOAR của tổ chức để thực hiện và theo dõi biện pháp xử lý.

## 5. Ví dụ: điều tra một phiên IAM role đáng ngờ

### 5.1. Bối cảnh

Một ứng dụng nội bộ sử dụng IAM role để đọc dữ liệu từ S3. GuardDuty phát hiện hoạt động đáng ngờ liên quan đến thông tin xác thực của role. Nhóm bảo mật cần xác định liệu đây là một lần triển khai hợp lệ hay một phiên truy cập bị lạm dụng.

Thông tin minh họa ban đầu:

- Tài khoản: tài khoản ứng dụng trong AWS Organizations.
- Region: Region đang vận hành ứng dụng.
- Danh tính: một assumed role session của role ứng dụng.
- Nguồn truy cập: IP chưa từng xuất hiện trong hoạt động thường lệ của role.
- Tài nguyên: một S3 bucket chứa dữ liệu nội bộ.

### 5.2. Xem sự kiện CloudTrail

Một sự kiện CloudTrail có thể chứa những trường quan trọng như ví dụ rút gọn dưới đây:

~~~json
{
  "eventTime": "2026-11-20T02:04:12Z",
  "eventSource": "s3.amazonaws.com",
  "eventName": "PutBucketPolicy",
  "awsRegion": "ap-southeast-1",
  "sourceIPAddress": "198.51.100.24",
  "userIdentity": {
    "type": "AssumedRole",
    "arn": "arn:aws:sts::111122223333:assumed-role/AppDataReader/session-example",
    "sessionContext": {
      "sessionIssuer": {
        "arn": "arn:aws:iam::111122223333:role/AppDataReader"
      }
    }
  },
  "requestParameters": {
    "bucketName": "internal-data-bucket"
  },
  "recipientAccountId": "111122223333"
}
~~~

Các giá trị IP và tài khoản trong ví dụ chỉ dùng để minh họa. Khi phân tích, hãy chú ý:

- **eventTime:** thời điểm sự kiện xảy ra; cần chuẩn hóa múi giờ khi ghép với nguồn khác.
- **eventSource và eventName:** dịch vụ và API được gọi.
- **awsRegion:** Region xử lý hoạt động.
- **sourceIPAddress:** địa chỉ nguồn được CloudTrail ghi nhận; có thể là IP của NAT, proxy hoặc dịch vụ trung gian.
- **userIdentity.type và arn:** loại danh tính và ARN của phiên đã thực hiện hành động.
- **sessionIssuer.arn:** role gốc đã cấp phiên assumed role.

### 5.3. Lần theo quan hệ trong Detective

Người điều tra mở finding liên quan, kiểm tra role và IP, rồi đặt phạm vi thời gian bao quanh sự kiện. Các bước suy luận có thể diễn ra như sau:

1. **Kiểm tra role:** role này có thường gọi API S3 không? Hoạt động có tăng đột biến hoặc xuất hiện ngoài khung vận hành không?
2. **Kiểm tra IP:** IP này đã từng liên hệ với role hoặc workload nào? Có phải IP egress của NAT gateway hoặc VPN hợp lệ không?
3. **Kiểm tra chuỗi API:** trước PutBucketPolicy có hoạt động AssumeRole hoặc hành động quản lý nào bất thường không? Sau đó có GetObject, thay đổi bucket policy hay hành động nhạy cảm khác không?
4. **Kiểm tra tài nguyên:** bucket có thuộc ứng dụng mà role phục vụ không? Chính sách bucket có thay đổi gần thời điểm đó không?
5. **Kiểm tra finding liên quan:** có finding khác gắn với cùng role, IP hoặc tài nguyên không?
6. **Đối chiếu thay đổi:** có ticket triển khai, tác vụ vận hành hoặc thay đổi mạng giải thích được nguồn IP và thời điểm không?

Kết quả có thể dẫn đến hai hướng. Nếu IP là NAT gateway mới được triển khai, hoạt động API khớp với lịch thay đổi và không có dấu hiệu truy cập ngoài phạm vi, nhóm có thể ghi nhận đây là hoạt động hợp lệ sau khi xác minh. Nếu IP không thuộc hạ tầng tin cậy, phiên role có hành động ngoài chức năng và có dấu hiệu truy cập dữ liệu bất thường, nhóm cần mở rộng điều tra và cân nhắc cô lập quyền truy cập.

### 5.4. Ghi nhận kết quả

Một bản ghi điều tra nên có:

| Trường | Nội dung cần ghi |
|---|---|
| Mã finding | ID hoặc loại finding và dịch vụ phát hiện |
| Phạm vi | Tài khoản, Region, khoảng thời gian |
| Thực thể trọng tâm | Role, session, IP, instance hoặc tài nguyên |
| Chuỗi sự kiện | Các hoạt động đã xác minh theo thứ tự thời gian |
| Bằng chứng | Tham chiếu CloudTrail, VPC Flow Logs, EKS audit logs và dữ liệu liên quan |
| Đánh giá | Hoạt động hợp lệ, đáng ngờ hay đã xác nhận sự cố; nêu rõ độ tin cậy |
| Hành động | Biện pháp đã thực hiện, người chịu trách nhiệm và thời điểm |
| Việc tiếp theo | Câu hỏi còn mở, hệ thống cần kiểm tra và thời hạn theo dõi |

Ghi rõ đâu là sự kiện quan sát được, đâu là giả thuyết và đâu là kết luận đã xác minh. Cách ghi nhận này giúp nhóm khác tiếp tục điều tra mà không nhầm suy đoán với bằng chứng.

## 6. Finding groups và điều tra nhiều phát hiện

Một sự cố có thể tạo ra nhiều finding ở các thời điểm khác nhau hoặc liên quan đến nhiều thực thể. Detective hỗ trợ nhóm các finding có liên hệ thành finding group để người điều tra xem chúng trong cùng ngữ cảnh.

Khi phân tích một finding group:

1. Xem các finding thành phần và loại hành vi được cảnh báo.
2. Xác định những thực thể xuất hiện chung, chẳng hạn IP, role, EC2 instance hoặc tài nguyên.
3. So sánh thời gian của từng finding để xác định thứ tự hoạt động.
4. Mở hồ sơ thực thể để xem thêm hoạt động ngoài các finding đã được nhóm.
5. Xác minh xem nhóm finding có thể xuất phát từ cùng một chuỗi hành vi hay chỉ trùng một thuộc tính như IP dùng chung.

Finding group giúp giảm việc xử lý từng cảnh báo một cách tách biệt. Tuy nhiên, nhóm finding là gợi ý về mối liên hệ để điều tra, không phải bằng chứng cuối cùng rằng tất cả finding có cùng nguyên nhân hoặc cùng tác nhân.

## 7. Detective phối hợp với các dịch vụ AWS khác

Mỗi dịch vụ có một vai trò riêng trong chuỗi giám sát và ứng phó:

| Dịch vụ | Vai trò chính | Cách phối hợp với Detective |
|---|---|---|
| Amazon GuardDuty | Phát hiện mối đe dọa từ dữ liệu và tín hiệu được hỗ trợ | Cung cấp finding làm điểm bắt đầu; Detective bổ sung ngữ cảnh và quan hệ thực thể |
| AWS CloudTrail | Ghi nhận hoạt động API và sự kiện tài khoản AWS | Cung cấp bằng chứng về ai đã gọi API nào, khi nào và từ đâu |
| VPC Flow Logs | Ghi nhận thông tin luồng mạng trong VPC | Bổ sung góc nhìn về kết nối giữa workload và địa chỉ IP |
| Amazon Security Hub | Tổng hợp và quản lý findings bảo mật từ nhiều nguồn | Hỗ trợ quản lý posture và finding tập trung; có thể dẫn quy trình điều tra sang dịch vụ phù hợp |
| AWS Config | Ghi nhận cấu hình và thay đổi cấu hình tài nguyên được hỗ trợ | Giúp xác minh trạng thái hoặc thay đổi cấu hình quanh thời điểm sự cố |
| AWS Systems Manager | Vận hành và quản lý các node được hỗ trợ | Có thể hỗ trợ một số hoạt động kiểm tra hoặc xử lý sau khi nhóm ứng phó quyết định |
| Amazon EventBridge | Định tuyến sự kiện giữa các dịch vụ | Có thể kích hoạt workflow hoặc thông báo khi có finding phù hợp |

Một cách ghi nhớ quy trình:

- GuardDuty giúp phát hiện tín hiệu đe dọa.
- Detective giúp điều tra mối liên hệ và ngữ cảnh hành vi.
- CloudTrail, VPC Flow Logs và EKS audit logs cung cấp bằng chứng hoạt động gốc.
- Security Hub giúp tổng hợp findings và quản lý trạng thái bảo mật.
- Các dịch vụ vận hành hoặc hệ thống SOAR hỗ trợ thực thi hành động ứng phó đã được phê duyệt.

~~~mermaid
flowchart TD
    A[CloudTrail] --> D[Amazon Detective]
    B[VPC Flow Logs] --> D
    C[EKS audit logs] --> D
    G[Amazon GuardDuty findings] --> D
    D --> E[Behavior graph]
    E --> F[Thực thể và quan hệ]
    F --> H[Điều tra và dựng dòng thời gian]
    H --> I[Xác minh bằng log gốc]
    I --> J[Đánh giá phạm vi và mức độ ảnh hưởng]
    J --> K[Quy trình ứng phó của tổ chức]
~~~

## 8. Triển khai và vận hành trong môi trường nhiều tài khoản

### 8.1. Chọn tài khoản quản trị

Với môi trường nhiều tài khoản, nhóm bảo mật nên thống nhất tài khoản quản trị Detective và quy trình ủy quyền trong AWS Organizations. Tài khoản quản trị có thể quản lý việc thêm tài khoản thành viên vào behavior graph theo mô hình tổ chức. Cần xác định rõ ai được phép thay đổi cấu hình, ai được phép điều tra và ai có quyền thực hiện biện pháp ứng phó.

Không nên cấp quyền quản trị Detective rộng cho mọi người chỉ vì họ cần xem finding. Hãy phân biệt quyền quản lý graph, quyền xem dữ liệu điều tra và quyền thay đổi tài nguyên AWS.

### 8.2. Lập kế hoạch theo Region

Detective có phạm vi theo Region. Với workload triển khai ở nhiều Region:

- Liệt kê Region có tài nguyên quan trọng và nơi GuardDuty đang phát hiện vấn đề.
- Bật Detective tại các Region cần điều tra.
- Kiểm tra tài khoản thành viên và nguồn dữ liệu ở từng Region.
- Đưa Region và tài khoản vào quy trình trực ca để người xử lý biết cần mở đúng graph.
- Kiểm tra khả năng truy cập và dữ liệu sau khi thêm tài khoản hoặc thay đổi cấu hình.

Không nên giả định rằng bật Detective ở một Region sẽ tự tạo dữ liệu điều tra cho mọi Region khác.

### 8.3. Quyền IAM và phân tách nhiệm vụ

Sử dụng IAM policy theo nguyên tắc đặc quyền tối thiểu. Người phân tích có thể cần quyền đọc graph, finding và hồ sơ thực thể. Người quản trị dịch vụ cần quyền cấu hình graph hoặc quản lý thành viên. Người ứng phó có thể cần quyền riêng trên IAM, EC2, VPC hoặc dịch vụ dữ liệu để xử lý sự cố.

Phân tách các nhóm quyền giúp tránh tình huống một tài khoản phân tích có thể tự ý thay đổi tài nguyên sản xuất. Quyền truy cập Detective cũng nên được rà soát định kỳ, nhất là khi nhân sự chuyển nhóm hoặc kết thúc nhiệm vụ trực sự cố.

### 8.4. Kiểm tra độ bao phủ dữ liệu

Một graph có thể hoạt động nhưng vẫn thiếu ngữ cảnh nếu nguồn dữ liệu quan trọng chưa được bật hoặc tài khoản liên quan chưa tham gia. Nên xây dựng danh sách kiểm tra vận hành:

- Detective đang bật trong các Region cần thiết.
- Các tài khoản AWS quan trọng đã được đưa vào phạm vi graph.
- Nguồn dữ liệu cần thiết đang được thu thập.
- GuardDuty findings có thể được xem trong quy trình điều tra dự kiến.
- Nhóm bảo mật có quyền truy cập phù hợp.
- Quy trình mở finding, điều tra và lưu bằng chứng đã được thực hành.

Khi có thay đổi về tài khoản, Region, VPC hoặc cụm EKS, hãy đánh giá lại độ bao phủ dữ liệu thay vì chờ đến khi xảy ra sự cố.

## 9. Chi phí, giới hạn và cách diễn giải kết quả

### 9.1. Theo dõi chi phí

Chi phí Detective phụ thuộc vào lượng dữ liệu được dịch vụ xử lý và phạm vi sử dụng theo Region. Khi thiết kế triển khai, cần:

- Ước tính số tài khoản, Region và workload cần đưa vào phạm vi điều tra.
- Theo dõi mức sử dụng và chi phí Detective trong AWS Billing and Cost Management.
- Đánh giá nguồn dữ liệu có giá trị điều tra thực tế đối với workload.
- Đưa chi phí giám sát vào ngân sách bảo mật và quy trình rà soát định kỳ.

Không nên dùng một mức giá cố định trong tài liệu vận hành vì giá và phạm vi tính phí có thể thay đổi. Hãy kiểm tra trang giá Amazon Detective tại thời điểm triển khai và đối chiếu với Region đang sử dụng.

### 9.2. Giới hạn dữ liệu

Detective chỉ phân tích những nguồn và loại hoạt động mà dịch vụ hỗ trợ. Nếu CloudTrail, VPC Flow Logs hoặc EKS audit logs không có dữ liệu cần thiết, graph không thể tự tái tạo phần hoạt động bị thiếu. Dữ liệu mới cũng cần thời gian để được thu thập và phân tích.

Ngoài ra, Detective có phạm vi theo Region và tài khoản. Một cuộc điều tra xuyên Region hoặc xuyên tài khoản chỉ đầy đủ khi các phạm vi cần thiết đã được cấu hình đúng.

### 9.3. Không diễn giải tương quan thành quan hệ nhân quả

Hai thực thể có hoạt động gần nhau hoặc cùng xuất hiện trong một finding group chưa đủ để kết luận thực thể này điều khiển thực thể kia. Một IP có thể đại diện cho NAT gateway, proxy hoặc hạ tầng dùng chung. Một role có thể được nhiều workload sử dụng theo thiết kế.

Hãy kết hợp các yếu tố sau trước khi kết luận:

- Chuỗi thời gian và thứ tự sự kiện.
- Danh tính, session issuer và nguồn truy cập.
- API hoặc hoạt động mạng cụ thể.
- Quyền IAM và chính sách của tài nguyên.
- Lịch triển khai, thay đổi và tác vụ vận hành.
- Bằng chứng gốc từ hệ thống ghi log.

## 10. Những lỗi thường gặp khi điều tra

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ xem đúng thời điểm finding | Bỏ sót hoạt động chuẩn bị hoặc tiếp diễn | Mở rộng phạm vi thời gian và dựng timeline |
| Cho rằng IP lạ luôn là độc hại | Nhận định sai với NAT, VPN hoặc proxy mới | Đối chiếu sơ đồ mạng và chủ sở hữu IP |
| Chỉ xem role mà không xem session | Không xác định được phiên cụ thể đã hành động | Kiểm tra assumed role session, session issuer và thời gian |
| Bỏ qua tài khoản hoặc Region | Graph thiếu thực thể liên quan | Xác nhận phạm vi graph ở từng tài khoản và Region |
| Xem finding group như kết luận | Có thể gộp nhầm hoạt động chỉ trùng thuộc tính | Kiểm tra từng finding và bằng chứng nguồn |
| Tin rằng Detective thay thế log gốc | Thiếu bằng chứng chi tiết khi cần xác minh | Đối chiếu CloudTrail, VPC Flow Logs và EKS audit logs |
| Thực hiện remediation ngay khi chưa xác minh | Có thể gây gián đoạn workload hợp lệ | Đánh giá tác động, theo quy trình ứng phó và phê duyệt |

## 11. Checklist điều tra nhanh

Khi nhận một finding cần điều tra, hãy đi theo checklist sau:

1. Xác nhận tài khoản, Region, finding ID và thời điểm.
2. Mở finding trong Detective và chọn khoảng thời gian phù hợp.
3. Xác định thực thể trọng tâm: principal, role session, IP, instance, cluster hoặc tài nguyên dữ liệu.
4. Kiểm tra hồ sơ và hoạt động nền của từng thực thể.
5. Lần theo quan hệ sang các thực thể liên quan.
6. Dựng dòng thời gian từ các sự kiện có thể xác minh.
7. Kiểm tra finding khác và finding group có liên quan.
8. Đối chiếu bằng chứng với log gốc và lịch thay đổi.
9. Đánh giá phạm vi ảnh hưởng, mức độ tin cậy và câu hỏi còn mở.
10. Ghi nhận kết quả rồi chuyển sang quy trình ứng phó phù hợp.

## 12. Kết luận

Amazon Detective giúp nhóm bảo mật hiểu một finding trong ngữ cảnh rộng hơn bằng cách liên kết dữ liệu, thực thể và hoạt động theo thời gian trong behavior graph. Giá trị lớn nhất của dịch vụ là giúp người điều tra lần theo mối liên hệ giữa danh tính, IP, workload và tài nguyên, từ đó dựng lại chuỗi sự kiện và xác định phạm vi cần kiểm tra.

Để dùng Detective hiệu quả, tổ chức cần bật dịch vụ ở đúng Region, đưa đúng tài khoản vào graph, bảo đảm các nguồn dữ liệu quan trọng được thu thập và cấp quyền điều tra phù hợp. Người điều tra phải kiểm tra hành vi nền, xác minh tương quan bằng log gốc và ghi rõ bằng chứng trước khi đưa ra kết luận. Sau bước phân tích, các biện pháp cô lập, thu hồi quyền hoặc khôi phục hệ thống được thực hiện qua quy trình ứng phó và các dịch vụ AWS tương ứng.

Khi phối hợp GuardDuty để phát hiện, Detective để điều tra, CloudTrail và VPC Flow Logs để xác minh, cùng các công cụ vận hành để xử lý, đội ngũ có thể chuyển từ những cảnh báo rời rạc sang một quy trình phản ứng có căn cứ và dễ kiểm tra.
