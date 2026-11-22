# Điều kiện policy, network sources và kiểm soát truy cập

Một policy IAM trong Oracle Cloud Infrastructure (OCI) không nhất thiết cấp cùng một quyền trong mọi hoàn cảnh. Ngoài chủ thể, hành động và compartment, policy có thể có điều kiện để giới hạn khi nào câu lệnh được áp dụng.

Ví dụ, nhóm học viên được đọc object của bucket thực hành, nhưng chỉ khi yêu cầu đi từ nguồn mạng đã được tổ chức chấp nhận. Bài toán này cần kết hợp ba phần: quyền của danh tính, điều kiện policy và cách OCI nhận biết nguồn của yêu cầu.

Bài học hướng dẫn xây dựng điều kiện, sử dụng network sources và kiểm chứng quyền hiệu lực trong môi trường lab. Các policy và địa chỉ dưới đây là ví dụ học tập; không được áp dụng nguyên xi vào tenancy nếu chưa thay đúng danh tính, phạm vi và địa chỉ thực tế.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Đọc phần điều kiện trong một câu lệnh policy OCI.
- Phân biệt phép kết hợp all và any.
- Giải thích vai trò của request.networkSource.name.
- Thiết kế một network source theo public egress hoặc VCN phù hợp.
- Phân biệt điều kiện IAM với route, NSG và kiểm soát kết nối ứng dụng.
- Phát hiện những policy khác đang làm phạm vi quyền rộng hơn dự kiến.
- Xây dựng bộ kiểm thử có cả trường hợp được phép và bị từ chối.

Bài học tập trung vào quyền truy cập tài nguyên OCI. Quy tắc đăng nhập identity domain, kết nối SSH và quyền bên trong database là những lớp kiểm soát có liên quan nhưng không tự động được cấu hình bởi các policy minh họa ở đây.

## 2. Nhắc lại cấu trúc câu lệnh policy

Dạng khái quát:

~~~text
Allow <subject> to <verb> <resource-type> in <location> where <condition>
~~~

Các thành phần chính:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| subject | Ai hoặc principal nào được cấp quyền? |
| verb | Mức thao tác nào được cấp? |
| resource-type | Loại tài nguyên nào? |
| location | Trong tenancy hoặc compartment nào? |
| condition | Chỉ cấp khi những điều kiện nào đúng? |

Ví dụ chưa có điều kiện:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab
~~~

Trong ví dụ, Default là tên identity domain và LabReaders là nhóm thuộc domain đó. Cần thay bằng tên thực tế và cú pháp định danh chủ thể phù hợp với tenancy. Nếu tên có khoảng trắng hoặc ký tự cần xử lý riêng, sử dụng cách biểu diễn được OCI hỗ trợ.

learning-lab là phạm vi compartment của ví dụ. Vị trí lưu policy và phân cấp compartment phải cho phép câu lệnh tác động tới phạm vi đó. Nếu môi trường có đường dẫn compartment lồng nhau, cần chỉ rõ phạm vi theo cách định danh được hỗ trợ thay vì dựa vào một tên có thể trùng.

Không đặt một policy ở compartment con rồi kỳ vọng nó cấp quyền lên mọi compartment cha hoặc toàn tenancy.

### 2.1. Điều kiện giới hạn một câu lệnh cấp quyền

Thêm điều kiện:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where request.networkSource.name = 'corpnet'
~~~

Câu lệnh có nghĩa: nhóm phù hợp được cấp mức quyền đọc object trong phạm vi đã nêu khi yêu cầu đáp ứng network source corpnet.

Nó không có nghĩa:

- Mọi principal từ corpnet đều có quyền đọc.
- Nhóm này được đọc mọi loại tài nguyên trong compartment.
- Mọi quyền của nhóm đều bị giới hạn vào corpnet.
- OCI đã tạo route hoặc firewall cho người dùng.
- Việc đăng nhập Console đã bị giới hạn vào corpnet.

Điều kiện chỉ là một phần của việc xét câu lệnh cấp quyền cụ thể.

### 2.2. Policy khác vẫn có thể cấp quyền

Giả sử ngoài câu lệnh trên còn có:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab
~~~

Câu lệnh thứ hai cấp quyền đọc object mà không có điều kiện network source. Trong phạm vi IAM đó, thêm câu lệnh có điều kiện không thu hẹp quyền đã được câu lệnh không điều kiện cấp.

Quyền có thể đến từ:

- Nhiều policy cùng tác động.
- Policy tại compartment cha.
- Những nhóm khác mà người dùng là thành viên.
- Một principal khác đang được công cụ sử dụng.

Muốn xác nhận “chỉ từ corpnet”, phải kiểm tra các đường cấp quyền liên quan. Không dùng một policy hẹp để giả lập một lệnh từ chối toàn cục.

## 3. Cách viết điều kiện

### 3.1. Biến yêu cầu và biến tài nguyên đích

Điều kiện thường sử dụng các biến có ngữ cảnh:

| Nhóm | Ví dụ | Phản ánh điều gì? |
| --- | --- | --- |
| Yêu cầu | request.networkSource.name | Nguồn mạng đáp ứng định nghĩa network source |
| Yêu cầu | request.operation | Thao tác API đang được xét |
| Yêu cầu | request.permission | Permission được xét cho yêu cầu |
| Đích | target.bucket.name | Bucket đích đối với các thao tác hỗ trợ biến này |

Không phải mọi biến đều có ý nghĩa với mọi thao tác. Cần kiểm tra biến và điều kiện được hỗ trợ cho loại tài nguyên cùng API cụ thể.

Ví dụ, một thao tác liệt kê nhiều bucket không đồng nghĩa đang nhắm tới một bucket duy nhất. Điều kiện yêu cầu một biến đích không có trong ngữ cảnh có thể khiến câu lệnh không cấp quyền cho thao tác đó.

Không dùng phép so sánh “khác một giá trị” để suy ra yêu cầu chắc chắn được phép khi biến không hiện diện. Việc đánh giá phụ thuộc biến có áp dụng trong ngữ cảnh và quy tắc điều kiện của OCI.

### 3.2. all: tất cả điều kiện phải đúng

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where all {target.bucket.name = 'lab-artifacts', request.networkSource.name = 'corpnet'}
~~~

Câu lệnh yêu cầu đồng thời:

1. Bucket đích là lab-artifacts.
2. Yêu cầu đáp ứng network source corpnet.

Nếu một điều kiện không đúng hoặc không áp dụng theo ngữ cảnh, không được suy ra câu lệnh này cấp quyền.

### 3.3. any: chỉ cần một điều kiện đúng

Ví dụ cho phép hai nguồn mạng:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where any {request.networkSource.name = 'corpnet', request.networkSource.name = 'lab-egress'}
~~~

Câu lệnh chấp nhận yêu cầu đáp ứng một trong hai network source đã nêu, với các thành phần chủ thể, hành động và phạm vi còn lại vẫn phải phù hợp.

Không nhầm với ví dụ sau:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where any {target.bucket.name = 'lab-artifacts', request.networkSource.name = 'corpnet'}
~~~

Ví dụ này không yêu cầu đồng thời đúng bucket và đúng nguồn. Theo logic any:

- Đúng bucket có thể đủ để thỏa phần điều kiện dù nguồn không phải corpnet.
- Đúng nguồn có thể đủ để thỏa phần điều kiện đối với bucket khác trong phạm vi câu lệnh.

Nếu yêu cầu là “đúng bucket và đúng nguồn”, phải dùng all.

### 3.4. Bảng chân trị giúp rà soát

| Đúng bucket? | Đúng nguồn? | all | any |
| --- | --- | --- | --- |
| Có | Có | Đúng | Đúng |
| Có | Không | Sai | Đúng |
| Không | Có | Sai | Đúng |
| Không | Không | Sai | Sai |

Đây là bảng logic khi cả hai biến đều có ngữ cảnh phù hợp. Khi một biến không được API cung cấp hoặc không áp dụng, phải kiểm tra quy tắc đánh giá thực tế của dịch vụ.

Trước khi đưa policy vào sử dụng, diễn giải từng điều kiện thành câu tiếng Việt. Nếu mô tả nghiệp vụ nói “và” nhưng policy dùng any, cần xem lại ngay.

## 4. Network source là gì?

### 4.1. Một định nghĩa nguồn mạng được đặt tên

Network source trong OCI IAM mô tả các nguồn yêu cầu được nhận diện bằng thông tin mạng được hỗ trợ. Một policy có thể tham chiếu nguồn đó qua:

~~~text
request.networkSource.name = 'corpnet'
~~~

Network source có thể được xây dựng từ những thành phần phù hợp như:

- Public IP hoặc public CIDR của nguồn truy cập.
- Một VCN cụ thể và các dải private IP tương ứng theo cơ chế được hỗ trợ.

Tên corpnet là tên network source, không phải hostname, tên subnet hay tên một security list.

Network source là đối tượng quản trị IAM ở phạm vi tenancy, không phải một rule tự động được gắn vào mọi subnet.

### 4.2. Public source thường là địa chỉ sau NAT

Giả sử máy học viên có địa chỉ private 192.168.1.20 và truy cập API OCI qua mạng văn phòng. Nếu lưu lượng đi qua NAT của văn phòng, nguồn public được dịch vụ nhận biết có thể là IP egress của văn phòng.

Đưa 192.168.1.0/24 vào phần public source không làm nó trở thành địa chỉ nguồn public của yêu cầu.

Cần xác định đường đi thực tế:

~~~text
Máy học viên
  -> VPN/proxy/NAT của tổ chức
  -> mạng tới endpoint OCI
  -> dịch vụ nhận yêu cầu
~~~

Nếu người dùng bật VPN, đi qua proxy hoặc chuyển sang mạng di động, địa chỉ egress có thể thay đổi. Network source phải được thiết kế theo những đường truy cập được tổ chức cho phép, không theo địa chỉ hiển thị trên card mạng của máy người dùng.

Một IP public chung cũng không xác định duy nhất một người dùng. IAM vẫn cần kiểm tra principal và các thành phần cấp quyền khác.

### 4.3. Nguồn VCN cần cả danh tính mạng và dải IP phù hợp

Khi khai báo nguồn VCN, cần đúng VCN và dải private IP theo yêu cầu cấu hình. Không chỉ ghi một dải 10.x.x.x rồi suy ra mọi VCN dùng dải đó đều được phép.

Ví dụ khái niệm:

~~~text
Network source: lab-private

VCN:           OCID của VCN lab được phép
Private range: 10.42.4.0/24
~~~

Cơ chế nhận diện nguồn VCN phụ thuộc đường truy cập dịch vụ được hỗ trợ. Với truy cập dịch vụ OCI qua service gateway, thông tin nguồn mạng có vai trò khác với đường đi ra public endpoint qua NAT hoặc Internet Gateway.

Không mặc định một instance nằm trong VCN là mọi yêu cầu của nó đều được nhận diện dưới dạng VCN source. Nếu yêu cầu đi qua NAT tới public endpoint, phải kiểm tra ngữ cảnh nguồn mà dịch vụ thực sự nhận biết.

Trước khi đưa VCN source vào policy, xác minh dịch vụ, đường mạng và điều kiện hỗ trợ của đúng kiểu truy cập.

### 4.4. Không dựa vào header do client tự khai báo

Địa chỉ client ghi trong một header ứng dụng không tự trở thành nguồn mà IAM dùng để xét network source.

Không hướng dẫn người dùng tự thêm X-Forwarded-For hoặc một header tương tự để vượt qua điều kiện. Cần xác định nguồn theo cơ chế OCI hỗ trợ và đường mạng thực tế.

## 5. Network source không thay thế các lớp khác

| Lớp | Mục đích | Network source có tự cấu hình không? |
| --- | --- | --- |
| Route table, gateway | Tạo đường đi mạng | Không |
| NSG, security list | Kiểm soát lưu lượng theo kiến trúc mạng | Không |
| IAM policy | Cho phép principal thực hiện thao tác tài nguyên | Network source là một điều kiện khi được tham chiếu |
| TLS và xác thực API | Bảo vệ kết nối, xác minh danh tính | Không |
| SSH và tài khoản hệ điều hành | Truy cập máy chủ | Không |
| Database user, role và quyền SQL | Truy cập bên trong database | Không |
| Chính sách đăng nhập identity domain | Kiểm soát phiên đăng nhập theo cấu hình danh tính | Không tự được thay đổi bởi policy tài nguyên |

Một yêu cầu có thể bị IAM từ chối dù đường mạng thông. Ngược lại, principal có quyền IAM phù hợp nhưng không có route hoặc DNS đúng vẫn không kết nối được endpoint.

Điều kiện network source trong policy tài nguyên không mặc nhiên chặn đăng nhập OCI Console từ nguồn khác. Người dùng có thể đăng nhập được nhưng một thao tác tài nguyên cụ thể bị từ chối.

Các đường truy cập như object công khai, pre-authenticated request hoặc giao thức dữ liệu có cơ chế cấp quyền riêng cần được rà soát riêng. Không tuyên bố một policy IAM có điều kiện đã bao phủ mọi cách đọc dữ liệu của hệ thống.

## 6. Thiết kế tình huống lab

### 6.1. Yêu cầu nghiệp vụ

Nhóm học viên cần:

- Đọc object trong bucket lab-artifacts của compartment learning-lab.
- Chỉ thực hiện các yêu cầu này từ egress đã được tổ chức chấp nhận.
- Không được ghi hoặc xóa object.
- Không được đọc object của bucket khác nhờ các câu lệnh lab.
- Không được tự sửa định nghĩa network source.

Danh tính minh họa là nhóm Default/LabReaders. Các tài nguyên và nguồn mạng phải được người quản lý lab chuẩn bị hoặc cấp phạm vi phù hợp.

### 6.2. Những điều cần xác nhận trước

| Thành phần | Thông tin cần có |
| --- | --- |
| Principal | Đúng tài khoản, domain và nhóm |
| Phạm vi | OCID compartment, bucket và region thực tế |
| Nguồn public | Egress thực của đường truy cập được phép |
| Nguồn private nếu dùng | VCN, dải private và đường truy cập dịch vụ |
| Quyền nền | Những policy khác đang cấp quyền cho principal |
| Dữ liệu kiểm thử | Một object không nhạy cảm đã biết tồn tại |
| Đường truy cập | Endpoint và công cụ thực sự dùng để gọi dịch vụ |

Các CIDR 198.51.100.0/24 hoặc 203.0.113.0/24 khi xuất hiện trong ví dụ tài liệu là dải dành cho minh họa. Không chép chúng thành egress thật của tổ chức.

Nếu chưa biết public egress thực, cần xác nhận với người quản lý mạng qua phương pháp được tổ chức cho phép. Không lấy IP private của laptop để thay thế.

## 7. Tạo network source và policy có điều kiện

### 7.1. Phân tách người quản trị và người sử dụng

Người quản lý IAM hoặc người được giao quyền phù hợp tạo network source, xem xét policy và ghi nhận thay đổi. Nhóm học viên chỉ nhận quyền sử dụng tài nguyên cần thiết.

Đặc biệt, không cấp cho nhóm bị giới hạn khả năng sửa network source để họ có thể tự mở rộng nguồn được phép. Thay đổi một dải IP trong network source có thể ảnh hưởng nhiều policy cùng tham chiếu.

Không cần cấp quyền quản trị toàn tenancy cho học viên chỉ để thực hiện bài kiểm thử.

### 7.2. Tạo network source

Trong nhóm quản trị IAM của Console, mở chức năng Network Sources hoặc chức năng tương đương trong giao diện hiện có.

Thực hiện theo các bước:

1. Đặt tên rõ mục đích, ví dụ corpnet.
2. Mô tả đội sở hữu, đường egress và phạm vi sử dụng.
3. Khai báo public IP/CIDR hoặc nguồn VCN theo thiết kế.
4. Kiểm tra đúng định dạng và biên CIDR.
5. Xác minh không vô tình đưa vào một dải quá rộng.
6. Lưu và đọc lại nội dung.

Không dùng 0.0.0.0/0 làm cách “sửa nhanh” khi nguồn không khớp. Cấu hình đó không đạt mục tiêu giới hạn nguồn public.

Việc network source được tạo thành công chỉ xác nhận định nghĩa đã được lưu. Nó chưa chứng minh yêu cầu thử nghiệm sẽ khớp hoặc policy đã tham chiếu đúng.

### 7.3. Cấp quyền đọc object có điều kiện

Policy minh họa chính:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where all {target.bucket.name = 'lab-artifacts', request.networkSource.name = 'corpnet'}
~~~

Câu lệnh này tập trung vào quyền đọc object trong bucket đích. Không dùng manage object-family nếu mục tiêu chỉ là đọc.

Trước khi lưu, kiểm tra:

- Chủ thể có đúng domain và nhóm không.
- Compartment có đúng phạm vi và vị trí gắn policy không.
- Tên bucket có đúng tài nguyên được giao không.
- Network source đã tồn tại và được tham chiếu đúng tên không.
- Đang dùng all để yêu cầu đồng thời hai điều kiện.
- Không có statement khác vô điều kiện cấp cùng quyền rộng hơn.

Các quy tắc so sánh và biến đích cần được đối chiếu với loại thao tác Object Storage định sử dụng, không suy rộng sang các dịch vụ khác.

### 7.4. Quyền điều hướng Console có thể là câu lệnh khác

Đọc object và liệt kê bucket là hai thao tác khác nhau. Nếu người học cần thấy danh sách bucket trong Console, có thể cần quyền metadata phù hợp.

Ví dụ bổ sung:

~~~text
Allow group Default/LabReaders to inspect buckets in compartment learning-lab where request.networkSource.name = 'corpnet'
~~~

Câu lệnh này cho phép khả năng inspect theo phạm vi, không cấp quyền đọc nội dung object của mọi bucket. Nó có thể làm lộ metadata của nhiều bucket trong compartment, nên chỉ thêm khi mục tiêu lab chấp nhận mức nhìn thấy đó.

Không gắn điều kiện target.bucket.name một cách máy móc vào thao tác liệt kê nhiều bucket rồi cho rằng nó sẽ trả một danh sách chỉ có một dòng. IAM policy không phải bộ lọc kết quả theo từng đối tượng cho mọi API.

Nếu muốn tránh cấp khả năng liệt kê rộng, có thể kiểm thử trực tiếp bucket và object đã được cung cấp tên, bằng công cụ phù hợp. Những thao tác phụ khác của Console vẫn cần được đánh giá riêng.

### 7.5. Chờ hiệu lực có kiểm soát

Sau khi đổi policy hoặc network source, có thể cần thời gian để thay đổi được phản ánh đầy đủ.

Không sửa liên tục nhiều điều kiện chỉ vì lần thử đầu chưa thành công. Ghi thời điểm thay đổi, chờ trong phạm vi vận hành phù hợp rồi kiểm thử lại cùng một ca.

Đồng thời vẫn xác nhận đúng principal, endpoint, bucket và nguồn mạng. Chờ thêm không sửa được tên nhóm sai hoặc CIDR sai.

## 8. Kiểm thử cả chiều cho phép và từ chối

### 8.1. Ma trận kiểm thử

Dưới đây là kết quả mong muốn đối với quyền từ các statement lab, với giả định không có policy khác cấp quyền rộng hơn:

| Principal và yêu cầu | Nguồn | Kết quả mong muốn |
| --- | --- | --- |
| LabReaders đọc object đã biết trong lab-artifacts | Khớp corpnet | Được phép |
| Cùng principal đọc cùng object | Không khớp corpnet | Không được các statement lab cấp quyền |
| LabReaders đọc object ở bucket khác | Khớp corpnet | Không được statement đọc object của lab cấp quyền |
| LabReaders ghi hoặc xóa object lab | Khớp corpnet | Không được các statement lab cấp quyền |
| Principal không được cấp quyền tương ứng đọc object | Khớp corpnet | Không được phép chỉ nhờ nguồn mạng |
| LabReaders liệt kê bucket | Khớp corpnet | Phụ thuộc có thêm statement inspect buckets hay không |

Không chạy thử ghi hoặc xóa lên dữ liệu có giá trị. Trường hợp kiểm thử thay đổi cần tài nguyên dùng thử được cho phép hoặc phương pháp đánh giá quyền phù hợp.

Với bài lab chỉ đọc, có thể kiểm tra các ca đọc được phép/bị từ chối và rà soát statement để đánh giá quyền thay đổi, đồng thời ghi rõ ca nào chưa thực thi.

### 8.2. Dùng cùng một danh tính khi so sánh hai nguồn

Để kết luận điều kiện mạng có tác dụng, cần giữ ổn định:

- Principal và cấu hình xác thực.
- API hoặc thao tác.
- Endpoint và region.
- Bucket, object và tên namespace nếu API yêu cầu.
- Thời điểm tương đối với lần đổi policy.

Chỉ thay đường truy cập nguồn theo kế hoạch thử nghiệm được phép. Nếu ở văn phòng dùng user A nhưng về nhà dùng user B, kết quả khác nhau chưa chứng minh nguyên nhân là network source.

Không bật một VPN không được phép hoặc dùng máy của người khác để thử vượt điều kiện.

### 8.3. Ví dụ kiểm tra metadata object bằng OCI CLI

Đây là ví dụ học tập, không phải lệnh được tự động chạy. Cần OCI CLI đã xác thực đúng principal, region phù hợp và một object thử nghiệm có sẵn.

~~~powershell
$env:OCI_OS_NAMESPACE = "<namespace-thuc-te>"
$env:OCI_LAB_REGION = "<region-cua-bucket>"

oci os object head --namespace-name $env:OCI_OS_NAMESPACE --bucket-name lab-artifacts --name policy-check.txt --region $env:OCI_LAB_REGION
~~~

Thao tác HEAD đọc metadata của object, không tải nội dung về file và không tạo object. Các giá trị placeholder cần được thay bằng thông tin lab thực tế.

Thử cùng thao tác từ đường truy cập được phép và đường không nằm trong nguồn cho phép, với phạm vi thử nghiệm đã được giao.

Nếu lệnh thất bại, chưa thể kết luận ngay là do network source. Cần xác nhận object tồn tại, namespace đúng, region đúng, principal đúng và đường mạng hoạt động.

### 8.4. Đừng dùng Console đơn lẻ làm bằng chứng

Một trang Console có thể gọi nhiều API: liệt kê bucket, lấy metadata, liệt kê object và đọc object. Một thao tác phụ bị từ chối có thể khiến trang hiển thị lỗi dù thao tác mục tiêu có policy phù hợp.

Ngược lại, thấy tên bucket trong Console không chứng minh có quyền đọc object. Cần kiểm tra đúng hành động mà yêu cầu nghiệp vụ đề cập.

Nên ghi kết quả theo từng API hoặc thao tác cụ thể, không chỉ ghi “Console hoạt động” hoặc “Console lỗi”.

## 9. Điều tra khi kết quả không như mong đợi

### 9.1. Ngoài nguồn cho phép vẫn đọc được

Kiểm tra:

1. Principal thực tế có đúng là tài khoản kiểm thử không.
2. Có nhóm khác cấp quyền đọc hoặc quản trị không.
3. Có statement không điều kiện tại compartment cha hoặc phạm vi khác không.
4. Yêu cầu có thực sự đi qua egress khác không, hay vẫn qua VPN/proxy của tổ chức.
5. Đang đọc qua API có IAM theo thiết kế hay qua một đường chia sẻ khác.
6. Network source có bị cấu hình rộng hơn dự kiến không.
7. Đang kiểm thử dữ liệu mới nhận từ dịch vụ hay nội dung đã có sẵn trong cache.

Một policy hẹp không thu hồi quyền rộng đã được cấp ở nơi khác. Cần tìm đường cấp quyền đó và xử lý theo trách nhiệm quản trị.

### 9.2. Trong nguồn cho phép vẫn bị từ chối

Kiểm tra:

- Tên domain, nhóm và thành viên nhóm.
- Vị trí policy và compartment thực tế của tài nguyên.
- Biến điều kiện có áp dụng cho API đang gọi không.
- Bucket và object có đúng không.
- Egress thực có nằm trong CIDR đã khai báo không.
- Với VCN source, VCN và đường truy cập dịch vụ có đúng không.
- Có quyền cho những thao tác phụ mà công cụ đang gọi không.
- Thay đổi vừa thực hiện đã có thời gian phản ánh phù hợp chưa.

Không khắc phục bằng cách mở toàn bộ nguồn hoặc tăng lên manage all-resources. Cần xác định điều kiện sai trước.

### 9.3. Không kết nối được endpoint

Nếu DNS, TLS hoặc kết nối mạng thất bại trước khi nhận phản hồi API phù hợp, trước tiên kiểm tra đường mạng và endpoint.

Điều kiện IAM không tạo service gateway, NAT Gateway hoặc kết nối private endpoint. Policy đúng không sửa route bị thiếu.

Cũng không dùng kết quả timeout làm bằng chứng rằng IAM đã chặn đúng. Một ca từ chối quyền cần được phân biệt với một ca không tới được dịch vụ.

### 9.4. Sử dụng Audit và mã yêu cầu

Khi có dữ liệu tương ứng, đối chiếu:

- Thời điểm và principal.
- Dịch vụ, thao tác và tài nguyên.
- Request ID.
- Địa chỉ nguồn hoặc thông tin mạng mà sự kiện thực tế ghi nhận.
- Kết quả và thông báo lỗi.

Không giả định mọi sự kiện Audit đều chứa tên network source hoặc một lời giải đầy đủ về statement nào đã quyết định quyền. Mức chi tiết phụ thuộc dịch vụ và loại sự kiện.

Giữ dữ liệu kiểm thử ở mức cần thiết; không đưa private key, token hay header xác thực vào báo cáo.

## 10. Quản trị thay đổi network source

### 10.1. Định nghĩa dùng chung có phạm vi ảnh hưởng lớn

Nếu nhiều policy cùng tham chiếu corpnet, thêm một CIDR vào corpnet có thể mở rộng điều kiện mạng cho nhiều câu lệnh cùng lúc.

Trước thay đổi, cần biết:

- Những policy nào đang tham chiếu.
- Những nhóm và tài nguyên nào bị ảnh hưởng.
- Dải mới thuộc ai và có ổn định không.
- Có đang mở rộng sang một mạng dùng chung quá lớn không.
- Cách kiểm thử và khôi phục cấu hình trước.

Không chỉ rà soát policy khi sửa statement; sửa network source cũng là thay đổi kiểm soát truy cập.

### 10.2. Tránh phụ thuộc vào egress không ổn định

Một network source theo IP public của kết nối dân dụng có thể mất tác dụng khi nhà cung cấp thay địa chỉ. Người dùng cũng có thể đi qua nhiều egress tùy VPN hoặc tuyến dự phòng.

Phương án vận hành cần chỉ rõ:

- Nguồn được chấp nhận.
- Cách cập nhật khi egress thay đổi.
- Người phê duyệt.
- Thời hạn cho các ngoại lệ.
- Cách kiểm tra lại sau thay đổi.

Không giải quyết sự bất tiện bằng việc mở dải rất rộng mà không đánh giá ảnh hưởng.

### 10.3. Giữ lối quản trị phù hợp

Trước khi áp dụng điều kiện trên phạm vi lớn, kiểm thử với nhóm lab và tài nguyên không quan trọng. Người quản trị phải có phương án khôi phục theo quy trình của tổ chức nếu cấu hình sai làm gián đoạn truy cập hợp lệ.

Điều này không có nghĩa tạo một tài khoản quản trị ngoài mọi kiểm soát. Phương án khôi phục cũng cần được bảo vệ, phân công và kiểm tra.

## 11. Quy trình thực hành hoàn chỉnh

### Bước 1: xác nhận đầu vào

Nhận hoặc xác minh:

- Danh tính kiểm thử và các nhóm liên quan.
- Compartment, bucket và object có sẵn.
- Nguồn mạng cho phép và nguồn thử nghiệm ngoài phạm vi.
- Người được quyền tạo policy và network source.
- Những statement rộng cần được xem xét trong quyền hiệu lực.

Không tự thay đổi policy của môi trường dùng chung để làm cho kết quả bài lab dễ quan sát hơn.

### Bước 2: ghi nhận quyền ban đầu

Thực hiện thao tác đọc đã được phép kiểm thử và ghi kết quả. Xác định kết quả ban đầu đến từ quyền nào trước khi thêm statement mới.

Nếu principal đã có quyền quản trị rộng, không dùng nó làm bằng chứng cho tính hiệu lực của policy đọc có điều kiện. Cần một principal kiểm thử có phạm vi quyền phù hợp.

### Bước 3: cấu hình có kiểm soát

Người được giao quyền:

1. Tạo hoặc dùng network source đúng phạm vi.
2. Thêm statement đọc object với all.
3. Chỉ thêm inspect buckets nếu cần và chấp nhận phạm vi metadata.
4. Ghi nhận cấu hình cùng thời điểm thay đổi.
5. Chờ hiệu lực rồi kiểm tra.

### Bước 4: chạy ma trận kiểm thử

Ưu tiên:

- Đúng principal, đúng bucket, đúng nguồn.
- Cùng principal và đối tượng nhưng nguồn ngoài phạm vi.
- Đúng nguồn nhưng đối tượng ngoài phạm vi.
- Phân biệt thao tác đọc object với thao tác liệt kê bucket.

Với các ca chưa được phép thực hiện, ghi rõ chưa kiểm thử thay vì báo đã đạt.

### Bước 5: báo cáo kết quả

| Ca kiểm thử | Principal | Nguồn thực tế | Thao tác và đích | Kỳ vọng | Quan sát | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| Đọc hợp lệ | Danh tính lab | Khớp corpnet | HEAD object lab | Được phép | Kết quả thực tế | Đạt hoặc cần điều tra |
| Ngoài nguồn | Cùng danh tính | Không khớp | Cùng object | Không được cấp quyền bởi policy lab | Kết quả thực tế | Đạt hoặc cần điều tra |
| Ngoài bucket | Cùng danh tính | Khớp corpnet | Object ở bucket khác | Không được statement đọc lab cấp quyền | Kết quả thực tế | Đạt hoặc cần điều tra |

Nếu kết quả khác kỳ vọng, ghi nguyên nhân đã xác minh hoặc phần còn thiếu bằng chứng. Không kết luận chỉ từ một mã lỗi mà chưa đối chiếu đối tượng và quyền nền.

### Bước 6: kết thúc lab

- Gỡ những statement chỉ dùng cho lab khi được giao.
- Kiểm tra policy tham chiếu trước khi sửa hoặc xóa network source.
- Giữ nguyên network source dùng chung nếu còn người sử dụng.
- Thu hồi thành viên nhóm thử nghiệm theo quy trình.
- Lưu cấu hình cuối cùng và kết quả kiểm thử được phép lưu.

Không xóa bucket hoặc dữ liệu chỉ để kết thúc bài IAM nếu chúng thuộc một lab khác hoặc được dùng chung.

## 12. Tự kiểm tra

### Câu 1: all và any khác nhau như thế nào?

all yêu cầu mọi điều kiện bên trong đúng; any chỉ yêu cầu ít nhất một điều kiện đúng. Khi yêu cầu nghiệp vụ là đúng bucket và đúng nguồn, dùng any có thể mở rộng quyền ngoài ý định.

### Câu 2: Đã có policy đọc không điều kiện, thêm một policy đọc có network source có thu hẹp quyền không?

Không. Câu lệnh có điều kiện không hủy câu lệnh cấp quyền rộng hơn. Phải rà soát các quyền có hiệu lực từ mọi nguồn liên quan.

### Câu 3: IP private của laptop có phải public source mà API OCI thấy không?

Thông thường không, nếu yêu cầu đi qua NAT ra public endpoint. Cần xác định egress thực và cách dịch vụ nhận diện nguồn.

### Câu 4: Tạo network source có tự chặn SSH từ mạng ngoài không?

Không. SSH cần kiểm soát đường mạng, NSG/security list và hệ điều hành phù hợp. Điều kiện IAM áp dụng cho các thao tác tài nguyên theo policy tương ứng.

### Câu 5: Vì sao đọc object bằng công cụ trực tiếp được nhưng Console vẫn báo lỗi?

Console có thể gọi thêm API liệt kê hoặc đọc metadata chưa được cấp. Phải kiểm tra từng thao tác, không xem mọi lời gọi của Console là một quyền duy nhất.

### Câu 6: Một request timeout có chứng minh network source đã từ chối không?

Không. Timeout có thể do DNS, route, firewall hoặc endpoint. Cần phân biệt lỗi kết nối với phản hồi từ chối quyền của dịch vụ.

### Câu 7: Ai được phép sửa network source có thể ảnh hưởng đến quyền truy cập không?

Có. Mở rộng định nghĩa nguồn có thể làm nhiều policy tham chiếu chấp nhận thêm yêu cầu. Quyền sửa network source cần được quản trị như thay đổi kiểm soát truy cập.

## 13. Danh sách kiểm tra

- [ ] Chủ thể, domain và nhóm đã đúng.
- [ ] Vị trí policy và compartment đích đã được xác minh.
- [ ] Verb và resource type đủ dùng, không rộng hơn nhu cầu lab.
- [ ] Biến điều kiện áp dụng cho đúng API.
- [ ] all hoặc any phản ánh đúng yêu cầu nghiệp vụ.
- [ ] Network source dùng egress hoặc VCN thực tế, không dùng địa chỉ minh họa.
- [ ] Đã xác định đường đi qua NAT, proxy hoặc service gateway khi liên quan.
- [ ] Đã rà soát những statement và nhóm khác có thể cấp quyền rộng.
- [ ] Đã phân biệt IAM với mạng, đăng nhập Console và quyền dữ liệu ứng dụng.
- [ ] Đã kiểm thử cả ca được phép và bị từ chối bằng principal phù hợp.
- [ ] Kết quả đã được đối chiếu theo thao tác, nguồn và đối tượng cụ thể.
- [ ] Có chủ sở hữu và quy trình thay đổi cho network source.

Điều kiện policy có giá trị khi nó phản ánh đúng ngữ cảnh của yêu cầu và được kiểm chứng cùng toàn bộ quyền hiệu lực. Network source bổ sung một ràng buộc về nơi yêu cầu xuất phát; danh tính, phạm vi tài nguyên và các lớp mạng vẫn phải được thiết kế đầy đủ.
