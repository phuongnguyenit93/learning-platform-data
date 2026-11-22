# Đánh giá tư thế bảo mật bằng Microsoft Defender for Cloud

Một hệ thống đang chạy ổn định trên Azure chưa chắc đã được cấu hình an toàn. Máy ảo có thể chưa được cập nhật, tài khoản lưu trữ có thể cho phép truy cập công khai, ứng dụng có thể sử dụng quyền quá rộng, hoặc dữ liệu quan trọng chưa được giám sát đúng cách. Để quản lý những rủi ro này trên nhiều subscription và resource group, tổ chức cần một cách liên tục nhìn thấy cấu hình bảo mật, xác định điểm yếu và theo dõi việc khắc phục.

**Microsoft Defender for Cloud** là dịch vụ quản lý tư thế bảo mật và bảo vệ workload trên đám mây của Microsoft. Bài học này tập trung vào cách sử dụng khả năng **Cloud Security Posture Management (CSPM)** của Defender for Cloud để đánh giá tài nguyên Azure: xem khuyến nghị, hiểu **Secure score**, ưu tiên rủi ro, thực hiện khắc phục và xác minh kết quả. Đây là một phần trong việc triển khai, giám sát và bảo vệ kiến trúc ứng dụng trên Azure, bên cạnh quản lý danh tính bằng Microsoft Entra ID, tổ chức tài nguyên theo subscription/resource group, kiểm soát mạng và quản lý dữ liệu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khái niệm tư thế bảo mật và phân biệt quản lý tư thế với phát hiện mối đe dọa.
2. Nhận biết các thành phần chính trong Defender for Cloud phục vụ đánh giá bảo mật.
3. Đọc Secure score, trạng thái recommendation và phạm vi tài nguyên bị ảnh hưởng.
4. Đánh giá một subscription Azure bằng Azure portal theo quy trình có thể lặp lại.
5. Ưu tiên, giao trách nhiệm, khắc phục và xác minh các phát hiện bảo mật.
6. Phân biệt đánh giá kỹ thuật với chứng nhận tuân thủ và nhận biết giới hạn của kết quả.

## 1. Tư thế bảo mật là gì?

**Tư thế bảo mật (security posture)** thể hiện mức độ tài nguyên, cấu hình, danh tính và quy trình của một tổ chức đáp ứng những kiểm soát bảo mật cần thiết tại một thời điểm. Thay vì chỉ hỏi "có cuộc tấn công đang diễn ra không?", đánh giá tư thế hỏi:

- Tài nguyên nào đang tồn tại và thuộc phạm vi quản trị nào?
- Cấu hình nào chưa đáp ứng chính sách hoặc khuyến nghị?
- Điểm yếu nào có thể khiến dữ liệu hoặc dịch vụ bị lộ?
- Những vấn đề nào cần khắc phục trước, ai chịu trách nhiệm?
- Sau khi sửa, có bằng chứng nào cho thấy rủi ro đã giảm?

Ví dụ: một Azure Storage Account có thể hoạt động bình thường nhưng vẫn cho phép truy cập từ mạng công cộng quá rộng. Đây là vấn đề **tư thế bảo mật** ngay cả khi chưa có bằng chứng bị khai thác. Nếu hệ thống phát hiện hành vi truy cập bất thường hoặc hoạt động độc hại vào dữ liệu, đó là một vấn đề **phát hiện và ứng phó mối đe dọa**.

Defender for Cloud hỗ trợ cả hai hướng, nhưng chức năng và phạm vi bảo vệ khác nhau tùy gói dịch vụ.

| Khả năng | Câu hỏi chính | Ví dụ kết quả |
|---|---|---|
| CSPM — Cloud Security Posture Management | Hệ thống có điểm yếu cấu hình và quản trị nào? | Recommendation về quyền, mạng, cập nhật hay cấu hình bảo vệ dữ liệu |
| CWPP — Cloud Workload Protection Platform | Workload có dấu hiệu bị tấn công hoặc khai thác không? | Cảnh báo bảo mật cho máy chủ, cơ sở dữ liệu, lưu trữ hoặc dịch vụ khác khi gói bảo vệ phù hợp được bật |
| Quản trị tuân thủ | Các kiểm soát được đo lường đáp ứng chuẩn hoặc yêu cầu nào? | Trạng thái của các control được ánh xạ với một bộ tiêu chuẩn |

**Điều quan trọng:** Một recommendation chỉ ra một điều kiện cần đánh giá và khắc phục; nó không tự động chứng minh đã xảy ra sự cố. Ngược lại, không có cảnh báo tấn công cũng không đồng nghĩa cấu hình hiện tại an toàn.

## 2. Defender for Cloud cung cấp những gì?

Defender for Cloud tập hợp thông tin về tài nguyên và các phát hiện bảo mật tại phạm vi Azure được phép quan sát. Các khả năng thường gặp liên quan tới CSPM gồm:

- **Asset inventory / Inventory:** nhận diện tài nguyên và tìm tài nguyên có phát hiện liên quan.
- **Security recommendations:** những kiểm tra cụ thể về cấu hình và trạng thái bảo mật, kèm tài nguyên bị ảnh hưởng, mô tả rủi ro và hướng khắc phục.
- **Secure score:** chỉ số tổng hợp giúp theo dõi mức độ áp dụng các kiểm soát bảo mật có tính điểm.
- **Security controls:** nhóm khuyến nghị liên quan tới một mục tiêu bảo mật, chẳng hạn quản lý quyền hoặc hạn chế truy cập mạng.
- **Regulatory compliance:** thể hiện trạng thái của các kiểm soát được ánh xạ với một số chuẩn và bộ chính sách có sẵn hoặc được cấu hình.
- **Attack path analysis và các khả năng CSPM nâng cao:** có thể giúp phân tích chuỗi đường đi tiềm năng tới tài sản quan trọng khi gói dịch vụ, môi trường và điều kiện hỗ trợ phù hợp.
- **Workflow automation và tích hợp quản trị:** hỗ trợ đưa phát hiện vào quy trình xử lý, cảnh báo hoặc hệ thống quản lý công việc theo cấu hình tổ chức.

Một số thông tin và khuyến nghị CSPM nền tảng có sẵn mà không cần bật các gói bảo vệ workload trả phí. Những khả năng nâng cao, chẳng hạn Defender CSPM hoặc các Defender plan dành cho workload, có thể phát sinh chi phí và có giới hạn theo loại tài nguyên hoặc khu vực. Trước khi bật bất kỳ plan nào, cần xem **Environment settings**, phạm vi subscription, tính năng được cung cấp và trang giá hiện hành của Microsoft. Không suy ra rằng mở giao diện Defender for Cloud đồng nghĩa toàn bộ tính năng đã được kích hoạt.

### Phạm vi và nguồn dữ liệu

Trong Azure, người vận hành thường bắt đầu từ một hoặc nhiều **subscription**. Defender for Cloud có thể tổng hợp tài nguyên ở phạm vi được kết nối hoặc được cấp quyền. Khi tổ chức kết nối tài khoản AWS, dự án GCP hoặc máy chủ Azure Arc, khả năng quan sát cũng phụ thuộc connector, gói đã bật và thiết lập thu thập tương ứng.

Kết quả luôn phải được hiểu cùng với **phạm vi đo lường**: một score cao ở subscription thử nghiệm không phản ánh mức an toàn của subscription sản xuất chưa được đánh giá.

## 3. Secure score: đọc đúng ý nghĩa

**Secure score** là chỉ số giúp tóm tắt mức độ đáp ứng những kiểm soát có tính điểm trong phạm vi đánh giá. Các recommendation liên quan được nhóm thành security control. Mỗi control có cách đóng góp điểm theo quy tắc của Defender for Cloud, dựa trên trạng thái những tài nguyên áp dụng kiểm soát đó.

Ví dụ giả định: màn hình cho biết Secure score của một subscription là **68%**. Điều này cho thấy có các kiểm soát có thể cải thiện; nó **không** có nghĩa subscription "an toàn 68%", và cũng không thể kết luận xác suất bị tấn công là 32%. Đây là một chỉ báo quản lý ưu tiên theo bộ quy tắc tính điểm của sản phẩm.

Khi đọc Secure score, hãy xem:

1. **Scope:** score thuộc subscription nào, hay tập hợp subscription nào?
2. **Security control:** nhóm kiểm soát nào đang mất nhiều điểm?
3. **Recommendation:** điều kiện cụ thể nào làm điểm chưa đạt?
4. **Affected resources:** tài nguyên nào bị đánh dấu chưa khỏe mạnh?
5. **Max score / potential increase:** cải thiện một kiểm soát có thể tác động thế nào đến chỉ số tổng hợp?
6. **Xu hướng theo thời gian:** điểm thay đổi do cấu hình được sửa, do tài nguyên mới, hay do quy tắc đánh giá thay đổi?

Không nên tối ưu điểm số một cách máy móc. Một recommendation có tác động Secure score nhỏ vẫn có thể rất cấp bách nếu liên quan đến dữ liệu khách hàng hoặc máy chủ lộ trực tiếp trên Internet. Ngược lại, một recommendation chỉ có ý nghĩa trong bối cảnh kiến trúc cụ thể có thể cần phân tích ngoại lệ trước khi thực thi.

## 4. Hiểu một security recommendation

Recommendation là đơn vị hành động quan trọng khi đánh giá tư thế bảo mật. Nội dung cụ thể có thể khác nhau theo dịch vụ, phiên bản giao diện, chính sách và plan đang dùng; thông thường người vận hành cần tìm:

| Trường thông tin | Cách sử dụng |
|---|---|
| Tên và mô tả | Hiểu điều kiện nào đang bị kiểm tra |
| Severity / risk | Nhận biết mức độ nghiêm trọng do hệ thống đánh giá |
| Status | Xác định trạng thái healthy, unhealthy, not applicable hoặc trạng thái tương đương |
| Affected resources | Liệt kê chính xác resource ID, subscription và resource group cần xử lý |
| Remediation steps | Tìm hướng dẫn sửa, thao tác được hỗ trợ và những tác động cần cân nhắc |
| Secure score impact | Nhận biết tác động dự kiến của việc cải thiện kiểm soát có tính điểm |
| Exemption / governance | Ghi nhận ngoại lệ hoặc người phụ trách theo cơ chế tổ chức đang sử dụng |

**Healthy** thường có nghĩa điều kiện kiểm tra hiện được đáp ứng. **Unhealthy** thể hiện tài nguyên chưa đáp ứng điều kiện. **Not applicable** cho biết kiểm tra không áp dụng cho tài nguyên hoặc tình huống đó. Một phát hiện mới có thể cần thời gian để được cập nhật sau khi thay đổi cấu hình. Hãy đọc từng recommendation thay vì chỉ dựa vào màu sắc hoặc số lượng.

Một số kiểm tra được tạo từ **Azure Policy** hoặc có liên hệ với policy assessment. Khuyến nghị có thể phụ thuộc việc chính sách nào được gán, gói bảo vệ nào được kích hoạt và dữ liệu nào đã thu thập thành công. Vì thế, hai subscription có tập recommendation khác nhau dù sử dụng dịch vụ tương tự.

### Ví dụ diễn giải

Giả sử một recommendation báo **"Storage account nên giới hạn truy cập mạng công cộng"** và hiển thị hai tài khoản lưu trữ bị ảnh hưởng. Người vận hành không nên ngay lập tức chặn mọi truy cập công khai mà cần hỏi: ứng dụng nào truy cập tài khoản này, luồng truy cập đang qua public endpoint hay private endpoint, có quy trình batch ngoài mạng Azure hay không, và thay đổi có gây gián đoạn không?

Sau khi xác định thiết kế đích, nhóm có thể áp dụng giới hạn mạng phù hợp, thử kết nối của ứng dụng và chờ hệ thống đánh giá lại. Điều kiện được chuyển sang healthy là **bằng chứng cấu hình** đã được cải thiện; để xác nhận hệ thống an toàn về mặt nghiệp vụ vẫn cần kiểm thử truy cập và quyền dữ liệu.

## 5. Chuẩn bị trước khi đánh giá

Một bài thực hành đọc và phân tích tư thế bảo mật có thể được làm ở chế độ quan sát, không nhất thiết cần thay đổi tài nguyên.

### 5.1. Xác định phạm vi

Ghi nhận:

- Tenant Microsoft Entra đang đăng nhập.
- Subscription và resource group thuộc workload cần đánh giá.
- Môi trường (dev/test/prod), nhóm ứng dụng và chủ sở hữu.
- Những dịch vụ quan trọng: Azure Virtual Machines, App Service, Azure SQL Database, Storage Account, Virtual Network, Key Vault và dịch vụ danh tính.
- Dữ liệu hoặc quy trình nghiệp vụ quan trọng để ưu tiên rủi ro.

Trong ví dụ xuyên suốt, giả sử hệ thống bán hàng có subscription **sub-sales-prod**, resource group **rg-sales-prod**, API trên App Service, dữ liệu giao dịch trên Azure SQL Database, hình ảnh sản phẩm trên Storage Account và khóa/bí mật trên Key Vault. Những tên này chỉ là ví dụ, không phải tài nguyên Azure thực có.

### 5.2. Kiểm tra quyền truy cập

Để xem thông tin bảo mật, tài khoản cần có quyền đọc phù hợp ở subscription hoặc resource group, ví dụ một vai trò đọc thông tin bảo mật như **Security Reader** theo phạm vi được cấp. Các chức năng sửa cấu hình, tạo exemption, thay đổi policy hoặc bật Defender plan cần quyền riêng và có thể yêu cầu phê duyệt.

Nếu không thấy subscription hoặc một recommendation, kiểm tra tenant, scope, role assignment và cấu hình Defender for Cloud trước khi kết luận không có vấn đề. Không tự nâng quyền chỉ để làm bài thực hành.

### 5.3. Kiểm tra plan và chi phí

Trong **Environment settings**, xác định subscription nào đang được giám sát và các Defender plan nào đang bật. Ghi nhận khả năng đang có trước khi chạy đánh giá. Việc bật một Defender plan trả phí hoặc tính năng quét nâng cao có thể phát sinh chi phí; chỉ thay đổi khi đã được chủ sở hữu subscription chấp thuận.

## 6. Thực hành đánh giá bằng Azure portal

Các tên trang và bố cục có thể thay đổi theo phiên bản giao diện. Quy trình dưới đây tập trung vào nhiệm vụ cần thực hiện để áp dụng được dù menu có thay đổi nhẹ.

### Bước 1: mở Defender for Cloud và chọn phạm vi

1. Đăng nhập **Azure portal** tại https://portal.azure.com.
2. Tìm **Microsoft Defender for Cloud** bằng ô tìm kiếm dịch vụ.
3. Chọn phạm vi subscription có quyền quan sát và bảo đảm đây là subscription của workload cần đánh giá.
4. Ghi nhận thời điểm đánh giá, số lượng tài nguyên và plan đang bật.

Nếu phạm vi hiển thị nhiều subscription, hãy dùng bộ lọc để tránh gộp nhầm tài nguyên của các môi trường. Tất cả nhận định về score và recommendations phải gắn với phạm vi cụ thể.

### Bước 2: xem tổng quan bảo mật và Secure score

Tại trang tổng quan, tìm **Secure score** hoặc mục quản lý tư thế tương ứng. Đọc điểm hiện tại và phân tích các security control đóng góp vào điểm. Chọn một control có tài nguyên unhealthy rồi xem recommendation bên trong.

Ghi lại ít nhất ba thông tin: score tại thời điểm đánh giá, những control cần cải thiện nhất và resource group nào có nhiều tài nguyên bị ảnh hưởng. Chưa nên đưa ra kế hoạch khắc phục nếu chưa biết các tài nguyên đó có vai trò nghiệp vụ gì.

### Bước 3: lọc và xem chi tiết recommendations

Mở mục **Recommendations**, sau đó:

1. Lọc theo subscription hoặc resource group.
2. Xem các recommendation có trạng thái chưa đáp ứng và mức độ ưu tiên/rủi ro phù hợp.
3. Mở một recommendation để đọc lý do, yêu cầu cấu hình và hướng khắc phục.
4. Liệt kê tài nguyên bị ảnh hưởng cùng resource ID chính xác.
5. Xác định công việc dự kiến, người phụ trách và khả năng gián đoạn.

Khi một recommendation ảnh hưởng tới nhiều tài nguyên, đừng mặc định mọi tài nguyên đều có cùng mức rủi ro. Ví dụ, một VM trong mạng thử nghiệm bị cô lập và một VM vận hành hệ thống thanh toán với truy cập Internet cần mức ưu tiên khác nhau.

### Bước 4: sử dụng Inventory để kiểm tra độ bao phủ

Mở **Inventory** nếu phạm vi và plan đang sử dụng hỗ trợ. Tìm một tài nguyên cụ thể, chẳng hạn Storage Account chứa dữ liệu ứng dụng, rồi xem những phát hiện và trạng thái liên quan.

Đối chiếu danh sách này với danh sách tài nguyên kỳ vọng trong subscription. Nếu thiếu tài nguyên, có thể do scope, quyền, connector, trạng thái thu thập dữ liệu hoặc đặc tính hỗ trợ của resource type. Cần điều tra độ bao phủ trước khi phát biểu rằng tất cả tài nguyên đã được đánh giá.

### Bước 5: xem Regulatory compliance

Nếu mục **Regulatory compliance** có dữ liệu, chọn bộ tiêu chuẩn được áp dụng cho tổ chức. Xem control nào đạt, chưa đạt hoặc chưa có dữ liệu, và truy ngược về recommendation hoặc tài nguyên liên quan.

Dashboard này giúp theo dõi kiểm soát kỹ thuật theo một số bộ chuẩn đã được ánh xạ. Nó không tự động xác nhận tổ chức đáp ứng đầy đủ yêu cầu pháp lý, hợp đồng hoặc kiểm toán. Các yêu cầu về quy trình con người, bằng chứng nghiệp vụ và kiểm soát ngoài Azure vẫn cần được đánh giá riêng.

### Bước 6: ghi nhận baseline và lập kế hoạch

Lưu báo cáo ngắn gồm phạm vi, ngày đánh giá, Secure score, những recommendation quan trọng, tài nguyên bị ảnh hưởng, mức ưu tiên, người xử lý và ngày dự kiến xác minh lại. Đây là **baseline** để so sánh trước và sau khi khắc phục.

Với môi trường sản xuất, thay đổi cấu hình cần đi qua quy trình change management của tổ chức. Nếu chỉ làm bài thực hành đọc dữ liệu, có thể dừng tại bước ghi nhận baseline mà chưa sửa tài nguyên.

## 7. Ưu tiên xử lý theo rủi ro thực tế

Recommendation và Secure score giúp sắp xếp công việc, nhưng ưu tiên xử lý cần phản ánh bối cảnh của ứng dụng.

Hãy cân nhắc:

1. **Mức độ phơi lộ:** tài nguyên có thể truy cập từ Internet, từ mạng nội bộ hay chỉ qua kết nối riêng?
2. **Độ nhạy dữ liệu:** tài nguyên lưu dữ liệu cá nhân, thanh toán, thông tin xác thực hay dữ liệu thử nghiệm?
3. **Khả năng bị khai thác:** có đường truy cập, quyền hoặc cấu hình nào tạo điều kiện cho tấn công?
4. **Ảnh hưởng kinh doanh:** nếu tài nguyên bị xâm nhập hoặc ngừng hoạt động, doanh nghiệp chịu thiệt hại nào?
5. **Phạm vi ảnh hưởng:** một cấu hình sai có lặp lại ở nhiều tài nguyên hoặc subscription không?
6. **Tính khả thi và tác động sửa chữa:** có giải pháp an toàn, ít gián đoạn nào có thể thực hiện sớm?

Ví dụ giả định cho subscription **sub-sales-prod**:

| Phát hiện giả định | Bối cảnh | Đánh giá ban đầu | Hành động dự kiến |
|---|---|---|---|
| Storage chứa tài liệu đơn hàng có truy cập mạng quá rộng | Dữ liệu nhạy cảm, có tích hợp qua mạng công cộng | Ưu tiên cao | Xác định luồng truy cập hợp lệ, thiết kế private endpoint hoặc hạn chế firewall phù hợp |
| Máy ảo production có cổng quản trị mở cho mọi địa chỉ | Bề mặt tấn công trực tiếp, quyền quản trị cao | Ưu tiên rất cao | Thu hẹp nguồn truy cập, dùng phương án quản trị an toàn, kiểm thử trước/sau thay đổi |
| Một tài khoản thử nghiệm thiếu tag người sở hữu | Không chứa dữ liệu nhạy cảm, ít ảnh hưởng trực tiếp | Ưu tiên thấp hơn | Bổ sung tag và chính sách gắn trách nhiệm |
| Quyền truy cập Key Vault quá rộng | Lưu bí mật dùng bởi API sản xuất | Ưu tiên cao | Rà soát role assignment và giảm quyền, thử quyền của ứng dụng |

Đây là dữ liệu minh họa cho cách suy luận, không phải kết quả Defender for Cloud thực tế. Điểm ưu tiên cuối cùng phải được người phụ trách xác nhận dựa trên tài nguyên thật.

### Sắp xếp công việc có trách nhiệm

Mỗi phát hiện nên có tối thiểu:

- **Chủ sở hữu:** người hoặc nhóm có quyền và kiến thức để sửa.
- **Mức độ ưu tiên và lý do:** nêu rõ tài sản, tác động và đường phơi lộ.
- **Hành động:** thay đổi cấu hình, thay đổi kiến trúc hay chấp nhận rủi ro có kiểm soát.
- **Thời hạn:** phù hợp mức độ rủi ro và khả năng vận hành.
- **Bằng chứng xác minh:** trạng thái recommendation, cấu hình Azure và kết quả kiểm thử.

Không nên dùng số lượng recommendation đã đóng làm thước đo duy nhất. Một thay đổi sai có thể làm Secure score tăng nhưng gây gián đoạn dịch vụ hoặc mở ra rủi ro mới.

## 8. Khắc phục và xác minh kết quả

Khuyến nghị trong Defender for Cloud có thể kèm hướng dẫn thủ công, liên kết đến tài nguyên hoặc khả năng khắc phục tự động đối với một số điều kiện. Tính sẵn có của nút **Fix**, **Quick fix** hoặc hình thức remediation phụ thuộc recommendation, gói dịch vụ và quyền người dùng.

Quy trình đề xuất:

1. **Đọc chính xác điều kiện:** ví dụ yêu cầu hạn chế truy cập mạng, không chỉ là "cải thiện bảo mật".
2. **Phân tích tác động:** tìm tất cả ứng dụng, danh tính, địa chỉ mạng và dịch vụ phụ thuộc.
3. **Chọn thay đổi tối thiểu:** dùng RBAC, network rules, managed identity hoặc thiết lập bảo vệ phù hợp.
4. **Thử trên môi trường phù hợp:** ưu tiên kiểm tra ở môi trường thử nghiệm khi có thể.
5. **Thực hiện thay đổi được phê duyệt:** ghi nhận người thao tác và cấu hình trước/sau.
6. **Kiểm thử ứng dụng:** xác nhận người dùng hợp lệ vẫn truy cập được, luồng dữ liệu hoạt động và log không xuất hiện lỗi mới.
7. **Chờ hệ thống đánh giá lại:** recommendation và Secure score có thể cần thời gian cập nhật sau khi thay đổi.
8. **Xác minh bằng hai nguồn:** kiểm tra trạng thái trong Defender for Cloud và cấu hình thực tế tại tài nguyên.

Nếu recommendation vẫn unhealthy, kiểm tra lại điều kiện kỹ thuật, phạm vi, độ trễ thu thập và các tài nguyên còn bị ảnh hưởng. Nếu điều kiện đã đáp ứng nhưng hệ thống chưa đánh giá lại, cần theo dõi hoặc kiểm tra vấn đề thu thập dữ liệu; không nên tự đánh dấu đã an toàn chỉ vì nhóm vừa lưu cấu hình.

### Khi không thể làm đúng recommendation

Một hệ thống cũ có thể chưa tương thích với cấu hình bảo mật được khuyến nghị. Trường hợp này cần ghi nhận **ngoại lệ có kiểm soát**: lý do kỹ thuật, tài nguyên áp dụng, rủi ro còn lại, kiểm soát bù trừ, người phê duyệt và thời hạn xem xét lại. Nếu môi trường hỗ trợ exemption hoặc governance workflow, hãy dùng tính năng phù hợp với quy trình tổ chức.

**Exemption không đồng nghĩa với việc rủi ro biến mất.** Nó cho biết tổ chức đã có quyết định quản trị về điều kiện kiểm tra đó. Không nên tạo ngoại lệ chỉ để làm đẹp báo cáo hoặc Secure score.

## 9. Truy vấn assessment theo phạm vi bằng Azure Resource Graph

Ngoài Azure portal, người có quyền đọc phù hợp có thể sử dụng **Azure Resource Graph** để tổng hợp một số dữ liệu security assessment. Đây là cách hữu ích khi muốn xem nhiều subscription hoặc xuất danh sách phục vụ phân tích. Cấu trúc dữ liệu có thể khác nhau theo loại assessment và khả năng hỗ trợ; cần kiểm tra dữ liệu thực tế trước khi tự động hóa.

Truy vấn KQL sau minh họa cách đếm assessment theo trạng thái:

~~~kusto
securityresources
| where type =~ "microsoft.security/assessments"
| extend assessmentStatus = tostring(properties.status.code)
| summarize totalAssessments = count() by assessmentStatus
| order by totalAssessments desc
~~~

Để xem tên assessment cùng trạng thái:

~~~kusto
securityresources
| where type =~ "microsoft.security/assessments"
| extend recommendationName = tostring(properties.displayName),
         assessmentStatus = tostring(properties.status.code)
| project subscriptionId, name, recommendationName, assessmentStatus
| order by assessmentStatus asc
~~~

Có thể chạy truy vấn này trong giao diện **Resource Graph Explorer** khi tài khoản có quyền truy vấn các subscription đã chọn và dữ liệu security assessment được cung cấp trong bảng. Kết quả thể hiện **bản ghi assessment**, không nhất thiết là số lượng tài nguyên duy nhất: một resource có thể có nhiều assessment. Do đó không dùng tổng đếm này để thay thế trực tiếp Secure score hoặc số resource unhealthy hiển thị ở một trang khác.

Nếu truy vấn không có kết quả, hãy kiểm tra subscription được chọn, quyền truy cập, điều kiện thu thập và kiểu tài nguyên trả về. Không vội kết luận rằng subscription không có rủi ro bảo mật.

## 10. Tích hợp đánh giá tư thế với quản trị Azure

Một báo cáo bảo mật chỉ có giá trị lâu dài khi kết quả được biến thành công việc của nhóm vận hành. Trong một tổ chức sử dụng nhiều subscription và resource group, nên gắn quy trình CSPM với các cơ chế quản trị sẵn có:

| Thành phần Azure | Vai trò trong quy trình |
|---|---|
| Microsoft Entra ID | Xác định người dùng, nhóm, danh tính workload và phương thức xác thực |
| Azure RBAC | Kiểm soát ai có thể xem và ai có thể thay đổi cấu hình bảo mật ở từng scope |
| Management group / subscription | Xác định phạm vi quản trị, phân chia môi trường và đơn vị chịu trách nhiệm |
| Resource group / tag | Giúp nhận diện chủ sở hữu ứng dụng và luồng xử lý phát hiện |
| Azure Policy | Áp dụng hoặc đánh giá các quy tắc cấu hình trong phạm vi được gán |
| Defender for Cloud | Tổng hợp khuyến nghị, chỉ số tư thế và các thông tin bảo mật được hỗ trợ |
| Azure Monitor | Theo dõi metric, log và cảnh báo vận hành sau thay đổi |
| Cost Management | Theo dõi chi phí dịch vụ bảo mật và tác động của cấu hình được bật |

Một cách tổ chức thực tế là nhóm bảo mật xác định chuẩn cấu hình và mức ưu tiên, nhóm nền tảng quản lý policy và ranh giới subscription, còn nhóm ứng dụng sửa cấu hình của workload mình sở hữu. Các nhóm cùng xác nhận kết quả bằng bằng chứng kỹ thuật.

### Theo dõi xu hướng thay vì chỉ xem một lần

Thiết lập lịch đánh giá định kỳ và đánh giá lại khi có thay đổi lớn như thêm subscription, triển khai ứng dụng mới, mở public endpoint, thay đổi kết nối mạng hoặc mở rộng quyền. Mỗi kỳ có thể so sánh:

- Secure score trong **cùng phạm vi** và các thay đổi lớn về bộ kiểm soát.
- Những recommendation có rủi ro cao còn tồn đọng.
- Số resource mới chưa có chủ sở hữu hoặc chưa được đánh giá đủ.
- Thời gian từ lúc phát hiện tới lúc khắc phục và xác minh.
- Số ngoại lệ sắp hết hạn hoặc chưa được rà soát.

Khi score thay đổi đột ngột, kiểm tra xem có tài nguyên mới, cấu hình mới, scope mới hay thay đổi logic đánh giá. Không quy mọi biến động của chỉ số cho một lần sửa cấu hình.

## 11. Giới hạn và sai lầm thường gặp

**"Secure score cao nghĩa là không thể bị tấn công."** Secure score chỉ phản ánh các kiểm soát được tính trong phạm vi và thời điểm đánh giá. Nó không thay thế kiểm thử bảo mật ứng dụng, quản lý lỗ hổng, giám sát runtime hoặc ứng phó sự cố.

**"Có recommendation nghĩa là hệ thống đã bị xâm nhập."** Recommendation mô tả điều kiện cấu hình hoặc trạng thái chưa đạt; việc phát hiện tấn công là luồng thông tin khác và phụ thuộc gói bảo vệ được bật.

**"Đánh dấu ngoại lệ là đã sửa xong."** Ngoại lệ là quyết định quản trị chấp nhận một rủi ro nhất định với lý do và phạm vi rõ ràng. Rủi ro kỹ thuật có thể vẫn tồn tại.

**"Đã bật Defender for Cloud thì mọi tài nguyên đều được quét như nhau."** Phạm vi, độ bao phủ và dữ liệu phụ thuộc subscription, loại tài nguyên, connector, quyền, plan và cấu hình thu thập.

**"Regulatory compliance hiển thị đạt nên đã đáp ứng hoàn toàn quy định."** Dashboard chỉ cung cấp bằng chứng cho những control được ánh xạ và đánh giá. Việc tuân thủ còn liên quan chính sách, con người, quy trình, hồ sơ và các hệ thống ngoài phạm vi sản phẩm.

**"Có thể sửa tất cả recommendation bằng một nút."** Một số điều kiện có tính năng remediation, nhưng nhiều cấu hình cần thay đổi kiến trúc, xác định dependency hoặc kiểm tra nghiệp vụ trước khi thực hiện.

**"Có thể bật mọi Defender plan mà không phát sinh phí."** Các gói bảo vệ workload và CSPM nâng cao có cơ chế tính phí riêng. Cần kiểm tra phạm vi, báo giá và sự chấp thuận trước khi bật.

## 12. Bài tập tình huống

Một subscription chứa ứng dụng thương mại điện tử với ba lớp: App Service chạy API, Azure SQL Database lưu đơn hàng và Storage Account lưu tài liệu khách hàng. Nhóm bảo mật thấy ba phát hiện giả định:

1. Storage Account có cấu hình mạng cho phép truy cập rộng.
2. Một danh tính ứng dụng được cấp quyền lớn hơn nhu cầu thực tế trên resource group.
3. Subscription chưa có người phụ trách xử lý một số recommendation ở mức ưu tiên trung bình.

Hãy lập phương án:

- Xác định tài sản và dữ liệu bị ảnh hưởng trong từng phát hiện.
- Ghi nhận scope, chủ sở hữu, độ phơi lộ và tác động kinh doanh.
- Sắp xếp thứ tự khắc phục và giải thích lý do.
- Chỉ ra thay đổi kỹ thuật cần được thử trước khi áp dụng.
- Mô tả cách kiểm thử ứng dụng và cách xác minh recommendation đã healthy.
- Nêu dữ liệu nào phải đưa vào báo cáo định kỳ của nhóm bảo mật.

Một phương án hợp lý thường ưu tiên điểm có thể làm lộ dữ liệu khách hàng hoặc cho phép danh tính vượt quyền, đồng thời xác định luồng truy cập hợp lệ để tránh chặn ứng dụng. Việc phân công người xử lý cần thực hiện ngay, dù recommendation có mức nghiêm trọng thấp hơn.

## 13. Checklist thực hành

| Công việc | Bằng chứng hoàn thành |
|---|---|
| Xác định subscription, resource group và ngày đánh giá | Tên scope, danh sách tài nguyên kỳ vọng và thời điểm chụp baseline |
| Kiểm tra quyền và Defender plan | Ghi nhận khả năng quan sát, plan, giới hạn và chi phí nếu có |
| Xem Secure score | Điểm và các control cần cải thiện trong đúng scope |
| Đọc recommendations | Danh sách phát hiện, resource ID, trạng thái và hướng khắc phục |
| Kiểm tra asset inventory | Độ bao phủ tài nguyên được xác nhận hoặc ghi nhận khoảng trống |
| Xem regulatory compliance nếu có | Control chưa đạt và giới hạn của việc ánh xạ được ghi nhận |
| Ưu tiên theo tác động kinh doanh | Người phụ trách, thời hạn, rủi ro và kế hoạch thay đổi |
| Khắc phục và kiểm thử | Cấu hình trước/sau, kiểm thử chức năng và quyền truy cập |
| Đánh giá lại | Recommendation và Secure score cập nhật, ngoại lệ được quản lý |
| Theo dõi định kỳ | Báo cáo xu hướng, phát hiện còn tồn đọng và công việc tiếp theo |

## Câu hỏi tự kiểm tra

1. Security posture khác với việc phát hiện một cuộc tấn công đang diễn ra như thế nào?
2. Secure score 85% có chứng minh xác suất bị tấn công chỉ là 15% không? Vì sao?
3. Khi recommendation báo Storage Account chưa hạn chế truy cập công cộng, cần kiểm tra gì trước khi sửa?
4. Vì sao hai subscription tương tự nhau có thể hiển thị khác số lượng recommendation?
5. Khi recommendation chuyển sang healthy, nhóm cần làm gì để bảo đảm ứng dụng vẫn hoạt động và quyền truy cập đúng?
6. Vì sao một dashboard regulatory compliance không đủ để kết luận tổ chức đã tuân thủ toàn bộ yêu cầu pháp lý?
7. Sự khác nhau giữa miễn trừ một recommendation và thực sự khắc phục cấu hình là gì?
8. Nếu đội ngũ chưa được phép bật một plan trả phí, họ vẫn có thể thực hiện những bước đọc và phân tích nào?

## Tài liệu tham khảo

- Microsoft Learn — *What is Microsoft Defender for Cloud?*: https://learn.microsoft.com/azure/defender-for-cloud/defender-for-cloud-introduction
- Microsoft Learn — *Cloud security posture management*: https://learn.microsoft.com/azure/defender-for-cloud/concept-cloud-security-posture-management
- Microsoft Learn — *Secure score and security controls*: https://learn.microsoft.com/azure/defender-for-cloud/secure-score-security-controls
- Microsoft Learn — *Review security recommendations*: https://learn.microsoft.com/azure/defender-for-cloud/review-security-recommendations
- Microsoft Learn — *Regulatory compliance dashboard*: https://learn.microsoft.com/azure/defender-for-cloud/regulatory-compliance-dashboard
