# Đã rotate tự động

## 1. Mục đích của mục checklist

Trong hệ thống quản lý truy cập đặc quyền (PAM), đánh dấu **“Đã rotate tự động”** có nghĩa là đã chứng minh được một chu trình thay đổi credential hoạt động từ đầu đến cuối trong phạm vi production đã khai báo. Hệ thống không chỉ tạo mật khẩu mới hoặc bật lịch chạy: credential phải được thay trên đích, được quản lý đúng trong vault, được consumer sử dụng, còn credential cũ phải mất khả năng tạo truy cập mới theo chính sách.

Đây là một điều kiện vận hành thuộc chương **Checklist production**. Nó liên kết việc kiểm kê tài khoản quản trị, tài khoản dịch vụ, least privilege, vault, luân chuyển credential, giám sát phiên và lưu bằng chứng. Mục tiêu là giảm thời gian một credential bị lộ còn hữu dụng, đồng thời tránh biến biện pháp bảo mật thành nguyên nhân gây gián đoạn dịch vụ.

Một scheduler hiển thị màu xanh chưa đủ để kết luận. Bằng chứng phải trả lời được:

- Những credential nào thuộc phạm vi và ai chịu trách nhiệm cho từng nhóm?
- Sự kiện nào kích hoạt rotation, và lần rotation thực tế gần nhất diễn ra khi nào?
- Đích có chấp nhận credential mới trong một lần xác thực mới hay không?
- Consumer đã chuyển sang dùng phiên bản mới bằng cách nào?
- Credential cũ có còn mở được truy cập mới không? Nếu có khoảng chồng lấn, giới hạn của nó là gì?
- Khi quá trình bị lỗi ở giữa, hệ thống biết trạng thái nào là thật và ai sẽ xử lý?
- Bằng chứng có được lưu mà không làm lộ secret không?

Ví dụ, việc đổi mật khẩu tài khoản dịch vụ trên cơ sở dữ liệu nhưng chưa cập nhật các replica ứng dụng là một rotation chưa hoàn tất. Ngược lại, cập nhật secret trong vault mà chưa đổi mật khẩu tại cơ sở dữ liệu có thể làm mọi lần kết nối mới thất bại.

## 2. Hiểu đúng credential và phạm vi rotation

### 2.1. Các loại credential có vòng đời khác nhau

Không nên dùng một cơ chế “đổi password” cho mọi loại thông tin xác thực.

| Loại | Thao tác vòng đời cần chứng minh | Điểm dễ bỏ sót |
|---|---|---|
| Mật khẩu tài khoản quản trị | Thay tại hệ thống đích, lưu bản mới, kiểm tra xác thực, xử lý bản cũ | Phiên đã mở có thể tiếp tục tồn tại sau khi đổi mật khẩu |
| Mật khẩu tài khoản dịch vụ | Thay tại đích và phối hợp consumer chuyển sang bản mới | Cache, connection pool, job định kỳ hoặc instance ít hoạt động chưa được cập nhật |
| API key hỗ trợ nhiều khóa | Tạo khóa mới, chuyển consumer, vô hiệu hóa hoặc xóa khóa cũ | Khóa cũ bị giữ vô thời hạn vì sợ ảnh hưởng |
| Khóa SSH | Cấp cặp khóa mới, phân phối public key mới, chuyển người dùng hoặc workload, gỡ quyền của public key cũ | Xóa private key ở một máy không gỡ quyền đã cấp tại các máy đích |
| Credential ngắn hạn | Cấp mới, giới hạn TTL, gia hạn khi được phép, xử lý hết hạn và thu hồi theo khả năng hệ thống | Gia hạn mãi một quyền không còn cần thiết hoặc cho rằng hết TTL của một token sẽ đóng mọi phiên |
| Chứng thư dùng để xác thực | Cấp lại, chuyển nơi sử dụng, kiểm tra trust và xử lý chứng thư cũ | Cài chứng thư mới nhưng endpoint hoặc client vẫn dùng bản cũ |

Với credential ngắn hạn, mục checklist cần được diễn đạt bằng bằng chứng về cấp phát, gia hạn, hết hạn và thu hồi; không ép hệ thống làm thao tác không tồn tại như “đổi mật khẩu token”.

Chỉ đổi tên secret hoặc đổi nhãn phiên bản không làm thay đổi credential. Cấp credential mới nhưng giữ credential cũ còn hiệu lực vô thời hạn cũng chưa đạt mục tiêu giảm rủi ro.

### 2.2. Khai báo rõ phạm vi được nghiệm thu

Đơn vị quản lý nên là **credential gắn với một identity tại một đích và các consumer của nó**. Một tài khoản có thể được dùng bởi nhiều ứng dụng; một ứng dụng cũng có thể phụ thuộc vào nhiều credential.

Bản kiểm kê phục vụ rotation tối thiểu cần có:

| Trường | Ý nghĩa |
|---|---|
| Identity và hệ thống đích | Tài khoản nào được thay credential trên hệ thống nào |
| Loại credential | Password, key, certificate hay credential ngắn hạn |
| Owner nghiệp vụ và owner kỹ thuật | Ai quyết định nhu cầu truy cập, ai vận hành thay đổi |
| Tham chiếu vault | Định danh secret hoặc object, không chứa giá trị secret |
| Consumer | Ứng dụng, replica, job, agent, tác vụ quản trị có sử dụng |
| Cơ chế chuyển bản mới | Fetch khi kết nối, reload, restart có kiểm soát hoặc cơ chế khác đã kiểm thử |
| Điều kiện kích hoạt | Theo lịch, sau sử dụng, sau sự cố, sau thay đổi nhân sự hoặc sự kiện khác |
| Giới hạn độ cũ | Bao lâu credential được phép không thay trong điều kiện bình thường |
| Ràng buộc chồng lấn | Có cho phép hai credential cùng hiệu lực không, trong bao lâu |
| Cách xác minh | Bằng chứng trên đích, consumer và credential cũ |
| Phương án phục hồi | Reconcile, đổi tiếp sang bản khác, cô lập hoặc dùng truy cập khẩn cấp |
| Ngoại lệ | Lý do, kiểm soát bù, người chấp nhận và ngày hết hạn |

Không được ghi một tỷ lệ “100% đã rotate” khi mẫu số chỉ gồm các account đã đưa vào vault, còn tài khoản chưa onboarding bị bỏ khỏi báo cáo. Phải nêu mẫu số, các loại trừ và phạm vi discovery đã thực hiện.

## 3. Tiêu chí đánh dấu hoàn tất

Một nhóm credential chỉ được đánh dấu đạt khi đáp ứng đồng thời các điều kiện sau:

1. Có policy rotation được phê duyệt cho đúng loại identity và mức độ nhạy cảm.
2. Có trigger tự động và có bằng chứng trigger thực sự dẫn đến rotation thành công.
3. Quyền của thành phần rotation đủ để thực hiện nhiệm vụ và được giới hạn trong phạm vi cần thiết.
4. Credential mới được áp dụng tại đích và được lưu, phát hành cho consumer theo trình tự đã kiểm thử.
5. Từng nhóm consumer có bằng chứng sử dụng bản mới; kiểm tra có bao phủ kết nối mới và tác vụ ít chạy.
6. Credential cũ không còn tạo được truy cập mới sau hạn cho phép.
7. Có quan sát trạng thái, cảnh báo, retry có giới hạn và người nhận xử lý.
8. Đã kiểm thử tình huống lỗi quan trọng và có phương án khôi phục truy cập.
9. Có bằng chứng đầy đủ, truy vết được mà không chứa secret.
10. Ngoại lệ còn lại được công khai; không gộp “chưa hỗ trợ tự động” vào “đã đạt”.

Các khoảng thời gian dùng trong bài như chu kỳ một ngày, cửa sổ chồng lấn mười phút hoặc thời gian phục hồi mười lăm phút chỉ là ví dụ thiết kế. Giá trị thực tế phải dựa trên rủi ro, khả năng đích, SLA ứng dụng và kết quả thử nghiệm; không có một chu kỳ cố định phù hợp cho mọi tài khoản.

Nếu hệ thống đã bật tự động nhưng chưa trải qua một chu trình có bằng chứng, trạng thái phù hợp là **chưa đủ bằng chứng nghiệm thu**. Nếu đã chạy tốt nhưng còn một consumer bắt buộc chưa chuyển, trạng thái vẫn là **chưa hoàn tất**.

## 4. Thiết kế policy trước khi bật lịch

### 4.1. Điều kiện kích hoạt

Rotation theo lịch giúp giới hạn tuổi credential trong điều kiện bình thường, nhưng không thay thế các trigger theo sự kiện.

Các sự kiện thường cần xem xét gồm:

- Kết thúc một lượt sử dụng tài khoản đặc quyền được checkout.
- Kết thúc một phiên truy cập của bên thứ ba.
- Credential bị nghi ngờ lộ hoặc bị sao chép vào nơi không được phép.
- Người từng biết credential không còn được phép sử dụng.
- Hoàn tất một quy trình khẩn cấp có sử dụng credential dự phòng.
- Thay đổi cấu hình hoặc phát hiện sai lệch khiến vault và đích không còn đồng bộ.

Không phải mọi sự kiện đều dùng cùng một workflow. Khi nghi lộ credential, việc cấp quyền mới, chuyển consumer, thu hồi credential cũ và xử lý phiên đang hoạt động phải được phối hợp trong ứng phó sự cố. Không chờ đến lịch rotation thông thường.

### 4.2. Các giới hạn phải được tách riêng

Policy nên định nghĩa ít nhất bốn giới hạn:

- **Tuổi tối đa:** thời gian credential được phép tồn tại từ lần thay thành công gần nhất.
- **Độ trễ sau trigger:** khoảng thời gian tối đa từ sự kiện bắt buộc đến khi rotation hoàn tất.
- **Thời gian chồng lấn:** giới hạn hai credential cùng hiệu lực nếu đích hỗ trợ.
- **Thời gian phục hồi:** mục tiêu đưa hệ thống về trạng thái truy cập được và credential được kiểm soát sau lỗi.

Một lịch chạy mỗi giờ không chứng minh credential luôn trẻ hơn một giờ. Nếu job thất bại liên tục, tuổi credential vẫn tăng. Cần đo thời điểm thành công gần nhất, không chỉ thời điểm scheduler gọi job gần nhất.

Tương tự, thời điểm secret mới xuất hiện trong vault không phải thời điểm rotation hoàn tất nếu consumer chưa chuyển hoặc khóa cũ chưa bị thu hồi.

### 4.3. Điều kiện vận hành và giới hạn tải

Rotation hàng nghìn account cùng lúc có thể gây tải lên vault, directory, API đích và hệ thống giám sát. Cần giới hạn số job đồng thời, phân nhóm theo đích và phân tán lịch chạy.

Việc trì hoãn để giảm tải phải có giới hạn. Khi một credential sắp vượt tuổi tối đa, hệ thống phải cảnh báo và xử lý ưu tiên thay vì lùi lịch vô thời hạn.

Không để các job rotation sử dụng cùng một account đặc quyền rộng trên mọi đích nếu có thể phân tách theo miền quản trị. Một thành phần bị xâm nhập không nên có khả năng thay credential của toàn bộ hạ tầng.

## 5. Chu trình rotation từ đầu đến cuối

Mỗi công nghệ có giao thức riêng, nhưng có thể dùng mô hình trạng thái chung để xác định việc nào đã thực sự xảy ra.

~~~text
Đủ điều kiện và xác minh phạm vi
                |
                v
Giành quyền xử lý một credential
                |
                v
Chuẩn bị phiên bản mới và kế hoạch phục hồi
                |
                v
Áp dụng thay đổi tại đích
                |
                v
Xác minh credential mới tại đích
                |
                v
Cho consumer chuyển sang bản mới
                |
                v
Xác minh consumer và xử lý credential cũ
                |
                v
Đóng job, ghi bằng chứng, giải phóng quyền xử lý
~~~

Trình tự cụ thể giữa vault và đích phụ thuộc khả năng của sản phẩm, giao thức và đích. Không nên coi sơ đồ này là một giao dịch nguyên tử có thể áp dụng nguyên xi cho mọi hệ thống.

### 5.1. Chống hai job cùng thay một credential

Trước khi thay đổi, cần bảo đảm chỉ một job hợp lệ đang xử lý credential đó. Có thể dùng cơ chế khóa, lease, version check hoặc khả năng điều phối tương đương.

Lease hết hạn không bảo đảm tiến trình cũ đã dừng. Nếu một worker cũ vẫn có thể gửi lệnh sau khi worker mới giành lease, cần cơ chế ngăn thao tác từ chủ sở hữu đã lỗi thời, chẳng hạn fencing khi hệ thống hỗ trợ hoặc kiểm tra thế hệ ngay tại nơi thực thi.

Điều cần nghiệm thu là tính chất vận hành: không có hai tác nhân cùng ghi những credential khác nhau rồi mỗi bên đều tuyên bố thành công. Không cần bắt mọi sản phẩm triển khai cùng một thuật toán khóa.

### 5.2. Chuẩn bị và bảo vệ phiên bản mới

Credential mới phải được sinh theo policy phù hợp với đích và bằng cơ chế sinh an toàn của nền tảng. Nó chỉ được tồn tại ở các vị trí cần thiết trong thời gian cần thiết.

Không đưa giá trị credential vào:

- Dòng lệnh có thể bị lưu trong lịch sử hoặc hiển thị trong danh sách process.
- Log debug, trace, metric label hoặc sự kiện cảnh báo.
- Ticket, ảnh chụp màn hình, tài liệu bằng chứng hoặc email.
- File cấu hình tạm không có kiểm soát quyền và thời hạn.
- Báo cáo diff giữa phiên bản cũ và mới.

Mã phiên bản như một ID do vault cấp giúp đối chiếu mà không tiết lộ giá trị. Không mặc định hash của một mật khẩu là bằng chứng an toàn để phát tán: với secret yếu, hash có thể hỗ trợ đoán offline.

### 5.3. Thay tại đích và xác minh

Thao tác thay đổi phải xác minh đúng tài khoản và đúng đích, qua kênh được bảo vệ, với xác thực danh tính đích phù hợp. Kết quả “API nhận request” có thể chỉ nghĩa là thao tác đã được xếp hàng.

Sau khi đích xác nhận thay đổi, cần kiểm tra một lần xác thực mới bằng credential mới hoặc bằng cơ chế xác nhận tương đương đã được chứng minh cho loại đích đó. Việc đọc lại secret trong vault chỉ chứng minh vault trả được dữ liệu.

Bài kiểm tra nên giới hạn tác động. Ví dụ, xác thực tài khoản dịch vụ và thực hiện một truy vấn đọc vô hại trong phạm vi cho phép có thể phù hợp hơn việc ghi dữ liệu nghiệp vụ để kiểm tra. Quyền kiểm tra không được trở thành lý do cấp thêm quyền quản trị cho consumer.

### 5.4. Phát hành cho consumer

Consumer phải có cách lấy bản mới đáng tin cậy. Cần biết rõ mỗi ứng dụng:

- Đọc secret ở thời điểm khởi động hay trước mỗi lần tạo kết nối?
- Có cache và cache hết hạn trong bao lâu?
- Có thể reload mà không restart hay cần rolling restart?
- Có tiến trình con hoặc job nền giữ bản cũ không?
- Có endpoint lỗi hoặc đường dẫn dự phòng âm thầm dùng credential tĩnh không?

Nếu secret được gắn qua file hoặc cơ chế projection, việc file thay đổi không bảo đảm process đã đọc lại. Nếu secret được đưa vào biến môi trường khi process khởi động, cần chứng minh process nhận bản mới theo cơ chế triển khai thực tế.

### 5.5. Hoàn tất bản cũ và đóng job

Với cơ chế hỗ trợ nhiều credential, job chưa hoàn tất nếu chỉ tạo và chuyển sang khóa mới nhưng chưa xử lý khóa cũ. Thời điểm thu hồi phải gắn với điều kiện chuyển consumer và giới hạn chồng lấn.

Với cơ chế chỉ có một mật khẩu, đổi thành công thường làm mật khẩu cũ mất khả năng xác thực mới, nhưng vẫn cần xác minh đúng hành vi của đích. Các lớp cache, bản sao hoặc cơ chế xác thực khác có thể ảnh hưởng kết quả.

Đổi mật khẩu không đồng nghĩa kết thúc mọi phiên đã xác thực, thu hồi mọi token đã phát hành hoặc đóng mọi kết nối trong pool. Phải có quyết định riêng về các phiên đó, đặc biệt khi rotation xuất phát từ nghi lộ credential.

## 6. Hai mô hình cần phân biệt

### 6.1. Đích cho phép hai credential cùng tồn tại

Ví dụ minh họa là một dịch vụ cho phép identity có hai API key.

~~~text
Ban đầu:       K1 hoạt động
Cấp mới:       K1 và K2 hoạt động
Chuyển dùng:   consumer dùng K2, theo dõi những nơi còn dùng K1
Thu hồi:       K1 mất hiệu lực, K2 hoạt động
Nghiệm thu:    kết nối mới bằng K2 thành công; K1 bị từ chối
~~~

Khoảng chồng lấn làm việc chuyển đổi dễ hơn nhưng cũng là khoảng cả hai credential có thể bị lạm dụng. Cần đặt thời hạn, không chỉ chờ “khi không còn lỗi”.

Telemetry nên phân biệt credential ID hoặc version để biết nơi còn dùng bản cũ. Nếu đích không cung cấp khả năng phân biệt, phải dùng bằng chứng thay thế phù hợp, chẳng hạn xác nhận reload của từng consumer kết hợp kiểm tra kết nối mới và thu hồi cũ có giám sát. Không tuyên bố có quan sát trực tiếp khi thực tế chỉ suy luận.

### 6.2. Đích chỉ cho phép một credential

Đây là trường hợp khó hơn vì thay tại đích có thể lập tức làm bản consumer đang giữ trở nên không dùng được.

Cần lập kế hoạch cho:

- Cách bảo vệ candidate mới trước khi thay và phục hồi khi mất kết nối.
- Thứ tự cập nhật đích, vault và consumer theo khả năng tích hợp.
- Thời gian tối đa consumer được phép chậm cập nhật.
- Cách tạo kết nối mới sau thay đổi.
- Khả năng rolling reload hoặc cửa sổ bảo trì.
- Đường truy cập phục hồi độc lập nếu account không còn đăng nhập được.

Không giả định hai bước “đổi ở đích” và “cập nhật vault” sẽ luôn cùng thành công. Đây thường là chuỗi thao tác phân tán có thể dừng giữa chừng.

Nếu đã xác định credential mới có hiệu lực tại đích, ưu tiên khôi phục tính nhất quán theo kế hoạch đã kiểm thử. Việc tự động đổi ngược về một credential cũ từng bị nghi lộ có thể tái mở rủi ro. “Rollback” phải nêu rõ quay lại cấu hình nào, credential nào và vì sao vẫn chấp nhận được; trong nhiều tình huống, cấp một bản mới khác để tiến tới trạng thái an toàn là lựa chọn phù hợp hơn.

## 7. Chứng minh consumer thật sự dùng bản mới

Một ứng dụng vẫn khỏe sau rotation có thể chỉ đang dùng các kết nối đã mở. Khi pool tạo kết nối mới sau vài giờ, lỗi mới xuất hiện.

Bộ bằng chứng nên bao phủ cả hai mặt:

| Kiểm tra | Chứng minh được | Không tự chứng minh được |
|---|---|---|
| Vault trả về phiên bản mới | Consumer có thể lấy dữ liệu bản mới qua đường truy cập đã kiểm tra | Đích chấp nhận dữ liệu đó |
| Consumer báo reload thành công | Cơ chế reload đã chạy và nhận version mong đợi | Mọi tiến trình con hoặc mọi replica đều dùng bản mới |
| Tạo kết nối mới và thao tác tối thiểu thành công | Một luồng mới dùng credential mới hoạt động | Mọi consumer khác đều đã chuyển |
| Job định kỳ chạy thành công sau rotation | Đường dùng của job đã kiểm tra hoạt động | Các job khác hoặc đường chạy hiếm đã được kiểm tra |
| Credential cũ bị từ chối trong kiểm tra có kiểm soát | Đường xác thực mới đã kiểm tra không chấp nhận bản cũ | Các phiên cũ đã bị hủy |
| Không có lỗi đăng nhập tăng bất thường | Chưa quan sát thấy lỗi vượt ngưỡng trong cửa sổ theo dõi | Credential cũ chắc chắn đã mất hiệu lực |

Nên chọn đại diện kiểm thử theo cơ chế dùng secret, không chỉ theo tên ứng dụng. Hai ứng dụng cùng framework nhưng một ứng dụng đọc secret lúc boot, ứng dụng còn lại đọc động cần hai cách xác minh khác nhau.

Với nhiều replica, cần có xác nhận version hoặc bằng chứng tương đương trên các replica trong phạm vi. Replica đang tắt phải được bảo đảm lấy bản hiện hành khi khởi động lại, thay vì quay về secret đóng gói từ trước.

Job chỉ chạy cuối tháng không được bỏ quên chỉ vì cửa sổ quan sát sau rotation kéo dài vài phút. Có thể chạy đường kiểm tra an toàn đại diện hoặc xác minh cơ chế lấy credential lúc thực thi; phải ghi rõ giới hạn của bằng chứng.

## 8. Xử lý lỗi và trạng thái không chắc chắn

### 8.1. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng có thể xử lý bằng việc thử lại.

| Tình huống | Rủi ro chính | Hướng xử lý |
|---|---|---|
| Đích chưa nhận thao tác, lỗi xảy ra trước bước thay đổi | Credential vẫn cũ, job có thể chạy lại | Retry có giới hạn sau khi xác nhận tiền điều kiện |
| Request timeout sau khi đã gửi lệnh thay | Không biết đích đã đổi hay chưa | Chuyển trạng thái chưa xác định và reconcile; không gửi ngay candidate khác |
| Đích đã đổi nhưng vault chưa hoàn tất lưu bản có thể phát hành | Vault và đích lệch nhau | Dùng cơ chế phục hồi đã thiết kế để xác định bản hiệu lực và hoàn tất đồng bộ |
| Vault có bản mới nhưng đích không chấp nhận | Consumer có thể bị phát hành secret sai | Chặn phát hành hoặc dừng chuyển đổi, kiểm tra kết quả trên đích |
| Consumer chưa reload | Lỗi có thể chỉ xuất hiện ở lần kết nối mới | Xác định consumer bị chậm, thực hiện reload/restart đã phê duyệt và kiểm tra |
| Thu hồi khóa cũ thất bại | Hai khóa cùng còn hiệu lực quá hạn | Cảnh báo mức phù hợp, giới hạn truy cập và xử lý thu hồi |
| Rotation account bị khóa hoặc thiếu quyền | Retry có thể gây thêm lỗi hoặc lockout | Dừng retry không hữu ích, chuyển người có trách nhiệm xử lý |
| Kiểm tra credential mới thất bại vì đích không sẵn sàng | Dễ kết luận nhầm credential sai | Tách lỗi khả dụng khỏi lỗi xác thực, xác minh trạng thái thay đổi trước bước tiếp theo |

Retry cần backoff, giới hạn số lần và giới hạn thời gian. Khi chạm giới hạn, job phải chuyển sang trạng thái có người nhận xử lý. Không để một vòng retry chạy mãi và che khuất việc credential đã quá tuổi.

### 8.2. Reconciliation khác rotation bình thường

**Reconciliation** là quá trình đưa thông tin quản lý và trạng thái thật của đích về nhất quán. Nó có thể cần một tài khoản có quyền đặt lại credential mà không biết mật khẩu hiện tại.

Tài khoản reconciliation thường có quyền mạnh. Cần giới hạn đích, quản lý credential riêng, theo dõi mọi lần sử dụng và kiểm soát quyền gọi chức năng này. Không đặt credential phục hồi vào cùng một chuỗi phụ thuộc duy nhất có thể đang bị hỏng.

Nếu cần thử candidate để xác định bản nào còn hiệu lực, phải giới hạn số lần, nhận biết chính sách khóa account và tránh thử hàng loạt. Không biến việc tìm trạng thái thật thành dò mật khẩu hoặc làm khóa tài khoản production.

### 8.3. Không đánh đồng trạng thái lỗi với trạng thái an toàn

Các trạng thái dưới đây có ý nghĩa khác nhau:

~~~text
FAILED_BEFORE_CHANGE   Chưa có thay đổi tại đích được xác nhận
STATE_UNKNOWN         Có thể đã thay đổi; cần xác minh trước hành động tiếp
TARGET_UPDATED        Đích đã đổi, chu trình còn bước chưa hoàn tất
CONSUMER_PENDING      Còn consumer chưa chuyển
OLD_CREDENTIAL_ACTIVE Bản cũ còn hiệu lực ngoài điều kiện mong muốn
COMPLETED             Đã đạt đầy đủ điều kiện đóng job
~~~

Tên trạng thái là ví dụ minh họa, không phải schema bắt buộc của một sản phẩm. Điểm quan trọng là trạng thái phải cho người vận hành biết còn nguy cơ nào và cần làm gì; một nhãn “FAILED” chung chung không đủ cho phục hồi.

## 9. Quan sát và cảnh báo

### 9.1. Những tín hiệu cần theo dõi

Các tín hiệu hữu ích gồm:

- Thời điểm rotation thành công gần nhất cho mỗi credential trong phạm vi.
- Tuổi hiện tại và thời gian còn lại trước giới hạn policy.
- Độ trễ từ trigger đến lúc hoàn tất.
- Tỷ lệ thành công theo loại đích và cơ chế tích hợp.
- Số job ở trạng thái chưa xác định hoặc đang chờ phục hồi.
- Số consumer chưa chuyển sang bản mới.
- Số credential cũ còn hiệu lực quá thời hạn.
- Lỗi xác thực, lockout, reconnect và tác động đến SLA ứng dụng sau rotation.
- Tình trạng scheduler, hàng đợi, connector và kênh nhận cảnh báo.

Không đưa secret hay thông tin có cardinality không kiểm soát vào metric label. Dữ liệu chi tiết theo credential có thể nằm trong kho sự kiện với quyền đọc phù hợp; metric tổng hợp chỉ nên giữ các nhãn cần thiết để vận hành.

### 9.2. Cảnh báo phải dẫn đến hành động

Một cảnh báo tốt có ít nhất identity reference, đích, run ID, trạng thái hiện tại, thời điểm thay đổi gần nhất, mức tác động, owner và runbook. Nội dung cảnh báo không chứa credential.

Cần thử cả đường nhận cảnh báo: có phát sự kiện nhưng không ai nhận, hoặc người nhận không có quyền truy cập runbook, vẫn là lỗi vận hành.

Một lần rotation thành công sau chuỗi thất bại không xóa nhu cầu điều tra khoảng thời gian credential bị quá tuổi. Lịch sử phải giữ được cả thất bại, thời gian tồn đọng và hành động khắc phục.

## 10. Bằng chứng nghiệm thu không chứa secret

Một bản ghi bằng chứng có thể sử dụng cấu trúc sau. Tất cả ID và thời gian bên dưới chỉ là dữ liệu minh họa.

~~~yaml
rotationEvidence:
  identityRef: svc-order-reader
  targetRef: db-order-prod
  policyRef: rotation-policy-service-account-v3
  runId: rot-example-0042
  trigger: SCHEDULED
  startedAt: "2026-01-15T02:00:00Z"
  completedAt: "2026-01-15T02:04:20Z"
  previousVersionRef: version-17
  currentVersionRef: version-18
  targetChange: CONFIRMED
  newAuthentication: PASS
  consumers:
    expected: 3
    verified: 3
    method: NEW_CONNECTION_AFTER_RELOAD
  oldCredential:
    newAuthentication: DENIED
    activeSessionsDisposition: DOCUMENTED_SEPARATELY
  recoveryTestRef: recovery-test-example-12
  result: COMPLETED
~~~

Một record như vậy chỉ hữu ích khi các kết quả trỏ được tới bằng chứng thực tế: sự kiện của vault, kết quả thay đổi ở đích, kiểm tra consumer và xác nhận xử lý bản cũ. Không tự điền **PASS** từ kết quả scheduler.

Nếu không thể hoặc không nên thực hiện negative test bằng credential cũ, ghi phương pháp xác minh thay thế cùng giới hạn của nó; không ghi **DENIED** khi chưa quan sát được sự từ chối.

Quyền đọc bằng chứng cũng cần kiểm soát. Dù không chứa secret, bản ghi vẫn có thể tiết lộ tài khoản đặc quyền, tên đích và sơ đồ phụ thuộc của hệ thống. Thời hạn lưu, tính toàn vẹn và quyền xóa phải phù hợp với chính sách của tổ chức.

Không lưu bản sao credential cũ chỉ để tiện kiểm toán. Kiểm toán cần chứng minh quá trình và kết quả, không cần được cấp một kho secret lịch sử ngoài vault.

## 11. Kịch bản nghiệm thu mẫu

Giả sử tài khoản **svc-order-reader** chỉ có quyền đọc dữ liệu cần thiết. Ba replica của một ứng dụng dùng tài khoản này. Đích chỉ hỗ trợ một mật khẩu đang hiệu lực; ứng dụng có cơ chế reload secret và tạo kết nối mới mà không dừng toàn bộ dịch vụ.

### 11.1. Chuẩn bị

Đội vận hành xác nhận:

- Owner của account và ứng dụng đã thống nhất policy và cửa sổ triển khai.
- Cả ba replica nằm trong danh sách consumer, không có cron job hoặc script khác bị bỏ sót.
- Thành phần rotation chỉ có quyền cần thiết trên đích.
- Cơ chế lưu candidate và phục hồi khi cập nhật dở dang đã được kiểm thử.
- Có thể tạo kết nối kiểm tra mà không ghi dữ liệu nghiệp vụ.
- Cảnh báo và đường truy cập phục hồi hoạt động độc lập với account đang rotate.

Trước lần triển khai production, nhóm đã diễn tập các lỗi quan trọng ở môi trường phù hợp. Việc tạo lỗi trong production chỉ thực hiện trong phạm vi đã được phê duyệt, với giới hạn tác động rõ ràng.

### 11.2. Thực hiện và quan sát

Job lấy quyền xử lý credential, chuẩn bị bản mới, thay mật khẩu tại đích rồi xác minh xác thực mới. Sau khi thông tin quản lý nhất quán và bản mới sẵn sàng cho consumer, hệ thống yêu cầu các replica reload.

Mỗi replica phải có bằng chứng reload đúng version và tạo được kết nối mới sau reload. Chỉ nhìn số kết nối đang mở hoặc HTTP health check không chạm cơ sở dữ liệu là chưa đủ.

Nhóm kiểm tra hành vi của mật khẩu cũ qua phương pháp có kiểm soát, đồng thời ghi riêng quyết định về các phiên đã mở. Trong trường hợp rotation thông thường, tổ chức có thể cho một số phiên hợp lệ kết thúc tự nhiên theo policy; khi nghi lộ credential, có thể cần thu hồi hoặc đóng phiên bằng cơ chế khác.

### 11.3. Một replica bị chậm

Giả sử hai replica đã chuyển, replica thứ ba chưa reload. Tác vụ phải thể hiện **CONSUMER_PENDING**, cảnh báo owner và giữ trạng thái chưa hoàn tất.

Vì đích chỉ có một mật khẩu, không được giả định replica thứ ba vẫn an toàn chỉ vì còn phục vụ qua kết nối cũ. Nó có thể lỗi ngay lần reconnect kế tiếp. Nhóm xử lý theo runbook đã phê duyệt, chẳng hạn rút replica khỏi nhận tải, reload hoặc khởi tạo lại, xác minh kết nối mới rồi đưa lại vào cụm.

Sau khi consumer cuối cùng đạt kiểm tra và không còn điều kiện tồn đọng, job mới được đóng. Bằng chứng giữ lại cả giai đoạn chậm chuyển để phục vụ đánh giá độ tin cậy.

## 12. Ma trận kiểm thử tối thiểu

Các bài kiểm thử phải được chọn theo rủi ro và khả năng của đích. Không cần tạo mọi lỗi trực tiếp trong production để chứng minh quy trình.

| Kịch bản | Kết quả cần quan sát | Điều kiện chưa đạt |
|---|---|---|
| Rotation theo lịch bình thường | Trigger, thay ở đích, chuyển consumer và đóng job có bằng chứng | Chỉ thấy lịch chạy hoặc secret mới |
| Rotation do sự kiện khẩn cấp | Độ trễ phù hợp policy, xử lý credential cũ và phiên theo kế hoạch | Chờ lịch định kỳ hoặc bỏ qua phiên liên quan |
| Đích không kết nối được trước thay đổi | Không phát hành bản chưa xác minh, retry có giới hạn | Consumer nhận secret mà đích chưa dùng |
| Mất phản hồi sau lệnh thay | Trạng thái chưa xác định được phát hiện, reconcile an toàn | Thay tiếp candidate khác một cách mù quáng |
| Vault hoặc connector lỗi giữa chu trình | Có bằng chứng phục hồi, không lộ candidate | Không biết bản nào có hiệu lực |
| Consumer không reload | Xác định đúng consumer, có cảnh báo và cách khắc phục | Job vẫn báo hoàn tất |
| Job trùng hoặc failover điều phối | Không tạo hai chu trình ghi xung đột trên cùng credential | Hai worker cùng đổi và vault lệch đích |
| Thu hồi credential cũ thất bại | Phát hiện chồng lấn quá hạn và có người nhận xử lý | Bản cũ bị quên sau khi cấp bản mới |
| Rotation account thiếu quyền hoặc bị khóa | Dừng retry không hữu ích, cảnh báo đúng nguyên nhân | Retry làm tăng lockout hoặc tác động diện rộng |
| Tác vụ ít chạy, replica vừa khởi động lại | Lấy bản hiện hành và xác thực mới được | Dùng secret đóng gói cũ |
| Mất kênh cảnh báo | Hệ thống phát hiện hoặc có giám sát thay thế | Lỗi im lặng kéo dài không người nhận |
| Phục hồi truy cập | Khôi phục bằng đường được kiểm soát, có audit | Phải dùng secret rải ngoài vault để cứu hệ thống |

Đối với negative test bằng credential cũ, cần tránh gây lockout hoặc thử trên các endpoint không được phép. Nếu chỉ kiểm thử ở một node trong hệ thống xác thực phân tán, bằng chứng chưa đại diện cho mọi đường truy cập; phải hiểu cơ chế đồng bộ và chọn cách xác minh phù hợp.

## 13. Runbook khi rotation bị lỗi

Runbook nên ngắn, dùng được khi có áp lực và không đòi hỏi người xử lý tự đoán trạng thái.

### Bước 1 — Xác định tác động và phạm vi

Lấy run ID, identity reference, đích và danh sách consumer. Phân biệt mất khả dụng, sai lệch credential và nghi lộ credential. Không bật debug chứa secret để tìm lỗi nhanh.

### Bước 2 — Ngăn thay đổi xung đột

Dừng hoặc chặn các job cạnh tranh trên cùng credential theo cơ chế điều phối. Không tắt toàn bộ rotation của cả module nếu chỉ một nhóm đích bị ảnh hưởng và có thể cô lập an toàn.

Nếu tạm dừng lịch, ghi rõ phạm vi, owner, thời hạn và điều kiện khôi phục. Credential vẫn tiếp tục già đi trong thời gian tạm dừng.

### Bước 3 — Xác định bước cuối đã được xác nhận

Đối chiếu sự kiện quản lý với trạng thái đích và consumer. Tách rõ “request đã gửi”, “đích đã đổi”, “vault đã phát hành” và “consumer đã dùng”.

Nếu không chắc đích đã đổi, dùng quy trình reconciliation đã kiểm thử. Không gửi liên tiếp nhiều lệnh thay chỉ để tìm một trạng thái có vẻ hoạt động.

### Bước 4 — Phục hồi tính nhất quán

Thực hiện phương án phù hợp loại đích: hoàn tất lưu và phát hành bản đã được xác minh, cấp một bản mới khác, khôi phục consumer hoặc sử dụng đường truy cập khẩn cấp.

Nếu dùng quyền reconciliation hoặc break-glass, phải ghi nhận chủ thể, lý do và thao tác. Credential được lộ cho người xử lý hoặc từng dùng trong quy trình khẩn cấp cần được xử lý lại theo policy sau khi ổn định.

### Bước 5 — Xác minh lại và khôi phục điều phối

Kiểm tra kết nối mới của consumer, credential cũ và các phiên liên quan. Khôi phục scheduler hoặc queue đã dừng, rồi kiểm tra không có job cũ còn khả năng gửi thay đổi muộn.

### Bước 6 — Đóng sự cố và giữ bằng chứng

Ghi nguyên nhân, thời gian credential quá tuổi nếu có, tác động, biện pháp đã thực hiện và việc cần sửa trước lần tiếp theo. Chỉ đóng mục rotation khi các điều kiện hoàn tất đã được chứng minh lại.

## 14. Ngoại lệ và kiểm soát bù

Một số đích không hỗ trợ tích hợp tự động, có giới hạn mật khẩu không tương thích hoặc cần thao tác thủ công. Trường hợp này cần quản lý ngoại lệ minh bạch.

Ngoại lệ tối thiểu có phạm vi, lý do, owner, thời hạn, người chấp nhận rủi ro, kế hoạch khắc phục và biện pháp kiểm soát bù. Có thể xem xét giảm quyền, hạn chế đường truy cập, tăng giám sát, đặt lịch thay thủ công có kiểm chứng hoặc loại bỏ nhu cầu dùng credential tĩnh.

Các biện pháp đó làm giảm rủi ro nhưng không biến một account chưa tự động rotate thành account đã đạt. Báo cáo nên tách số đạt đầy đủ, số có ngoại lệ còn hiệu lực và số chưa đạt.

Không tự động đổi credential của thiết bị hoặc ứng dụng quan trọng khi chưa biết consumer và chưa có đường phục hồi. Điều cần làm là hoàn thiện khả năng vận hành và ngoại lệ có thời hạn, không che phần thiếu bằng một job scheduler.

## 15. Checklist bàn giao production

Có thể dùng bảng sau trong biên bản bàn giao. Cột bằng chứng phải chứa tham chiếu đến record hoặc kết quả kiểm tra đã có, không chứa secret.

| Nhóm | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
|---|---|---|
| Phạm vi | Đã kiểm kê credential, đích và consumer trong phạm vi chưa? | Inventory có owner, loại trừ và phạm vi discovery |
| Policy | Chu kỳ, trigger, độ trễ và giới hạn chồng lấn đã rõ chưa? | Policy theo loại credential và mức độ nhạy cảm |
| Quyền | Thành phần rotation và reconciliation có quyền giới hạn không? | Cấu hình quyền và kiểm thử đường vận hành |
| Tự động | Trigger thật đã tạo ra ít nhất một chu trình thành công chưa? | Run ID từ trigger đến kết quả cuối |
| Đích | Credential mới được xác thực tại đúng đích chưa? | Xác nhận thay và kiểm tra xác thực mới |
| Consumer | Các kiểu consumer và trường hợp ít chạy đã được bao phủ chưa? | Reload/version và kết nối mới hoặc bằng chứng tương đương |
| Bản cũ | Đã xử lý hiệu lực của credential cũ và phiên riêng biệt chưa? | Xác minh thu hồi hoặc từ chối, quyết định về phiên |
| Điều phối | Job trùng, timeout và failover đã được xử lý an toàn chưa? | Kết quả diễn tập và trạng thái phục hồi |
| Cảnh báo | Lỗi, quá tuổi và tồn đọng có tới đúng người không? | Sự kiện thử, xác nhận nhận và runbook |
| Phục hồi | Đã diễn tập đường lấy lại truy cập và tính nhất quán chưa? | Record phục hồi có thời gian và kết quả |
| Bằng chứng | Log và báo cáo có đầy đủ mà không chứa secret không? | Record được kiểm tra, quyền truy cập và thời hạn lưu |
| Ngoại lệ | Phần chưa hỗ trợ có được tách khỏi trạng thái đạt không? | Danh sách ngoại lệ có ngày hết hạn và owner |

## 16. Tự kiểm tra trước khi xác nhận

**Scheduler chạy thành công nhưng mật khẩu tại đích không đổi có đạt không?**

Không. Cần bằng chứng thay đổi tại đích và xác thực mới bằng bản mới; kết quả gọi job chỉ là một bước.

**Ứng dụng vẫn trả HTTP 200 sau rotation có đủ không?**

Chưa đủ. Ứng dụng có thể chưa chạm hệ thống đích hoặc đang dùng kết nối đã mở. Cần kiểm tra luồng tạo kết nối mới và các consumer nằm trong phạm vi.

**Cấp khóa mới nhưng để khóa cũ hoạt động nhằm tránh lỗi có được tính hoàn tất không?**

Chỉ khi việc chồng lấn nằm trong khoảng và điều kiện được phép, và chu trình vẫn theo dõi bước thu hồi. Khi bản cũ còn hiệu lực quá hạn, mục checklist chưa đạt.

**Timeout sau lệnh đổi mật khẩu có nên chạy lại ngay không?**

Không nên chạy lại một cách mù quáng. Đích có thể đã đổi dù phản hồi bị mất. Cần xác minh trạng thái hoặc reconciliation trước khi gửi thay đổi tiếp theo.

**Đổi mật khẩu có xử lý xong một vụ lộ credential không?**

Không tự động. Còn phải đánh giá token, phiên, kết nối, quyền truy cập khác, dấu vết sử dụng và các credential liên quan theo quy trình ứng phó sự cố.

**Điều gì phân biệt “đã cấu hình” và “đã rotate tự động”?**

“Đã cấu hình” mô tả ý định và thiết lập. “Đã rotate tự động” trong checklist production đòi hỏi bằng chứng vận hành: thay đúng đích, consumer dùng bản mới, xử lý bản cũ, phát hiện lỗi và phục hồi được trong giới hạn đã thống nhất.
