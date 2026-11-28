# Recovery: đặc tả và kiểm chứng yêu cầu phục hồi an toàn sau incident

## 1. Recovery cần khôi phục điều gì?

Sau một incident, việc ứng dụng trả lại HTTP 200 chưa đủ để kết luận phục hồi thành công. Hệ thống có thể vẫn dùng khóa đã lộ, khôi phục quyền quản trị cũ, phục vụ dữ liệu bị sửa hoặc hoạt động mà không có audit.

Recovery là quá trình đưa các dịch vụ và hoạt động bị ảnh hưởng trở về trạng thái được chấp nhận, với dữ liệu, cơ chế bảo vệ và khả năng vận hành đã được kiểm chứng. Trong bài này, trọng tâm là phục hồi sau sự cố an toàn thông tin, không chỉ khởi động lại thành phần bị lỗi.

Trong chương Vận hành và incident của module Security Requirements, nhiệm vụ là chuyển mục tiêu phục hồi thành yêu cầu cụ thể: phục hồi dịch vụ nào, tới mốc dữ liệu nào, với quyền và cấu hình nào, trong thời hạn nào và dựa trên bằng chứng gì.

NIST SP 800-61 Rev. 3 đặt hoạt động ứng phó và phục hồi trong bối cảnh quản trị rủi ro an ninh mạng. Cách tiếp cận này giúp liên kết chuẩn bị, xử lý incident và cải thiện khả năng phục hồi thay vì coi recovery là một thao tác kỹ thuật riêng lẻ. [Nguồn: NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final).

Sau bài học, người học có thể:

- Phân biệt phục hồi dữ liệu với phục hồi dịch vụ an toàn.
- Đặc tả RTO, RPO, thứ tự phụ thuộc và tiêu chí sẵn sàng.
- Liên kết recovery với xác thực, phân quyền, dữ liệu, logging và quản lý khóa.
- Thiết kế điều kiện chuyển bước, tái kết nối và phản ứng khi kiểm chứng không đạt.
- Xác định bằng chứng, kịch bản diễn tập và yêu cầu cần cải thiện sau incident.

Các mã yêu cầu, ngưỡng, thời gian và tình huống trong bài là ví dụ cho hệ thống giả định. Chúng phải được điều chỉnh theo đánh giá tác động nghiệp vụ, rủi ro và nghĩa vụ áp dụng; không phải giá trị mặc định của một tiêu chuẩn.

## 2. Phân biệt các hoạt động liên quan

| Hoạt động | Mục đích | Điều chưa được chứng minh chỉ bằng hoạt động đó |
| --- | --- | --- |
| Backup | Tạo bản sao có thể dùng cho các mục đích đã định | Bản sao còn truy cập được, sạch và khôi phục được nghiệp vụ |
| Restore | Đưa dữ liệu hoặc trạng thái về từ một nguồn khôi phục | Dịch vụ an toàn, quyền đúng hoặc dữ liệu không bị sửa từ trước |
| Failover | Chuyển hoạt động sang thành phần hoặc môi trường khác | Môi trường đích không có cùng lỗ hổng hoặc dữ liệu lỗi |
| Containment | Hạn chế phạm vi và khả năng gây hại của incident | Nguyên nhân đã được xử lý hoặc hệ thống đã đủ điều kiện hoạt động lại |
| Eradication | Xử lý nguyên nhân, hiện diện hoặc cơ chế duy trì của mối đe dọa trong phạm vi xác định | Mọi chức năng nghiệp vụ đã sẵn sàng |
| Recovery | Khôi phục dịch vụ và khả năng bảo vệ theo điều kiện chấp nhận | Không còn bất kỳ điều chưa biết nào hoặc mọi rủi ro đã bằng không |
| Business continuity | Duy trì hoạt động quan trọng, có thể bằng phương án thay thế | Toàn bộ hệ thống gốc đã được phục hồi |

Các hoạt động có thể chồng lấn. Nhóm recovery có thể chuẩn bị môi trường trong khi nhóm incident tiếp tục điều tra. Tuy nhiên, việc đưa một thành phần trở lại phục vụ cần thỏa điều kiện đã thống nhất cho thành phần và phạm vi đó.

Không mặc định “bản mới nhất” là “bản phù hợp nhất”. Một bản sao gần hiện tại có thể đã chứa dữ liệu bị sửa hoặc cấu hình xâm nhập, trong khi một bản cũ hơn tạo khoảng mất dữ liệu vượt mục tiêu.

## 3. Bắt đầu từ dịch vụ nghiệp vụ và bản đồ phụ thuộc

Đơn vị ưu tiên phục hồi nên gắn với chức năng nghiệp vụ và tác động, không chỉ tên máy chủ.

Ví dụ chức năng xuất hóa đơn có thể phụ thuộc vào:

- Danh tính quản trị, xác thực người dùng và cơ chế thu hồi.
- DNS, thời gian hệ thống, mạng và chính sách kết nối.
- Khóa, bí mật ứng dụng và quyền truy cập nguồn backup.
- Database, lưu trữ file, queue và worker.
- Artifact, cấu hình và chính sách triển khai.
- Audit, giám sát và kênh điều phối incident.
- Hệ thống ngoài nhận thông báo hoặc giao dịch.

Khôi phục database trước nhưng không có khóa giải mã hoặc quyền đăng nhập phù hợp có thể khiến bản sao chưa dùng được. Khôi phục worker trước khi đối soát queue có thể phát lại thao tác đã hoàn tất.

### Phân cấp và thứ tự

Có thể xác định:

1. Năng lực cần để thực hiện recovery: quyền quản trị, tài liệu, kênh liên lạc và nguồn artifact.
2. Nền tảng tin cậy và phụ thuộc bảo mật.
3. Dữ liệu và dịch vụ nghiệp vụ theo mức ưu tiên.
4. Các chức năng ít quan trọng hơn và công việc tồn đọng.

Đây là cách lập kế hoạch minh họa, không phải thứ tự cố định cho mọi hệ thống. Bản đồ phụ thuộc phải chỉ ra các vòng phụ thuộc và phương án khởi tạo khi hạ tầng chính không sẵn sàng.

NIST SP 800-184 nhấn mạnh lập kế hoạch, ưu tiên tài nguyên, xây playbook, kiểm thử và cải thiện recovery. Có thể dùng các chủ đề đó để cấu trúc yêu cầu phục hồi trong vòng đời phát triển. [Nguồn: NIST SP 800-184](https://csrc.nist.gov/pubs/sp/800/184/final).

## 4. RTO, RPO và điều kiện sẵn sàng

### 4.1. RTO là mục tiêu, không phải tên một tác vụ

Recovery Time Objective là mục tiêu thời gian phục hồi. Để kiểm chứng, cần định nghĩa mốc bắt đầu và điều kiện kết thúc cho đúng dịch vụ.

Trong ví dụ:

- t0 là thời điểm dịch vụ bị gián đoạn bởi sự cố giả lập đã xác định.
- t_ready là lúc chức năng đạt toàn bộ điều kiện sẵn sàng đã thống nhất.
- Thời gian phục hồi quan sát được là t_ready - t0.
- RTO của chức năng xuất hóa đơn được giả định là tối đa 2 giờ.

Nếu t0 của hợp đồng là thời điểm gián đoạn, không được chỉ đo từ lúc kỹ sư bắt đầu restore. Thời gian phát hiện, điều phối và chuẩn bị có thể ảnh hưởng kết quả.

### 4.2. RPO gắn với dữ liệu thực sự khôi phục được

Recovery Point Objective xác định mục tiêu về điểm dữ liệu cần khôi phục. Với cách đo theo thời gian trong ví dụ:

- t_data là mốc dữ liệu nhất quán cuối cùng khôi phục được trước t0.
- Khoảng dữ liệu mất tính theo thời gian là t0 - t_data.
- RPO được giả định là tối đa 15 phút.

Thời gian tạo file backup không tự là t_data. Một snapshot mới có thể còn thiếu giao dịch nhất quán hoặc phụ thuộc cần thiết.

### 4.3. “Sẵn sàng” phải bao gồm bảo mật

t_ready không nên chỉ là lúc process chạy hoặc health check trả 200. Cần các điều kiện cụ thể về chức năng, dữ liệu, xác thực, quyền, khóa, audit và giới hạn vận hành.

Nếu tổ chức cho phép phục hồi một phần, định nghĩa mức dịch vụ đó và mục tiêu riêng. Việc mở chế độ chỉ đọc không tự chứng minh RTO của chức năng xuất hoặc ghi dữ liệu đã đạt.

## 5. Chuyển mục tiêu thành yêu cầu phục hồi

Một yêu cầu recovery nên có phạm vi, kịch bản, tiền điều kiện, kết quả, thời hạn, người sở hữu và bằng chứng. Không chỉ ghi tên công cụ backup hoặc một câu “có kế hoạch DR”.

Bộ yêu cầu minh họa cho dịch vụ hóa đơn:

| Mã | Yêu cầu | Bằng chứng hoặc tiêu chí chấp nhận |
| --- | --- | --- |
| REC-01 | Phục hồi chức năng xuất hóa đơn trong 2 giờ theo mốc đã định | Timeline và kiểm tra nghiệp vụ hoàn tất trên môi trường phục hồi |
| REC-02 | Khôi phục mốc dữ liệu nhất quán đáp ứng RPO 15 phút | Mốc giao dịch, đối soát dữ liệu và phép tính khoảng mất |
| REC-03 | Quyền truy cập quản trị và người dùng sau phục hồi tuân thủ policy hiện hành | Ca hợp lệ, ca bị cấm, trạng thái tài khoản và cấu hình hiệu lực |
| REC-04 | Không đưa lại bí mật hoặc thông tin truy cập đã xác định bị lộ vào sử dụng | Kế hoạch thay thế, kết quả thu hồi và kiểm tra phụ thuộc |
| REC-05 | Dữ liệu và nguồn phục hồi được đánh giá phù hợp với incident | Nguồn gốc, kiểm tra toàn vẹn, đánh giá nhiễm bẩn và giới hạn kết luận |
| REC-06 | Audit và giám sát bắt buộc hoạt động trước khi phục vụ phạm vi nhạy cảm | Sự kiện thử đầu cuối, truy vấn và phản ứng khi thiếu bằng chứng |
| REC-07 | Queue, worker và tích hợp ngoài không gây tác dụng phụ trùng hoặc sai phạm vi | Đối soát trạng thái, khóa nghiệp vụ và ca phát lại có kiểm soát |
| REC-08 | Đưa dịch vụ trở lại theo điều kiện được duyệt và có phương án xử lý khi kiểm tra không đạt | Quyết định chuyển bước, giới hạn lưu lượng, trigger hạn chế hoặc dừng |

Mỗi hàng cần được cụ thể hóa theo kiến trúc. Nếu một tiêu chí chưa có cách kiểm chứng, đó là khoảng trống của đặc tả hoặc khả năng quan sát cần xử lý trước incident.

### Năm nhóm yêu cầu bảo mật trong recovery

**Xác thực:** khôi phục cơ chế nhận diện đúng chủ thể, phương thức quản trị và khả năng thu hồi; không mở đường đăng nhập tạm thời vô thời hạn.

**Phân quyền:** đối chiếu quyền hiệu lực với nguồn có thẩm quyền. Snapshot cũ có thể đưa lại tài khoản đã bị khóa hoặc quyền đã bị thu hồi.

**Dữ liệu:** kiểm tra nguồn, tính nhất quán, mã hóa và phạm vi sử dụng. Bản sao dùng để phục hồi cũng cần được bảo vệ khi truyền và lưu.

**Logging:** giữ khả năng ghi nhận ai thay đổi gì trong quá trình recovery và quan sát dịch vụ sau khi mở lại.

**Phục hồi:** chứng minh chức năng nghiệp vụ, thời gian và mốc dữ liệu đạt mục tiêu, cùng các giới hạn còn tồn tại.

Các nhóm có quan hệ phụ thuộc. Một ứng dụng đã có dữ liệu nhưng chưa có danh tính tin cậy hoặc audit bắt buộc có thể chưa đạt điều kiện phục vụ.

## 6. Chuẩn bị năng lực recovery trước incident

### 6.1. Nguồn dữ liệu và môi trường phục hồi

Cần đặc tả loại bản sao, phiên bản, vị trí, quyền, cơ chế bảo vệ và cách xác định bản sao có thể dùng. Một nguồn cùng chịu quyền quản trị đã bị xâm nhập có thể không còn cung cấp mức độc lập mong muốn.

Các câu hỏi thiết kế gồm:

- Quyền bị chiếm ở môi trường chính có thể sửa hoặc xóa bản sao không?
- Khóa cần để đọc bản sao có sẵn khi hệ thống quản lý chính bị gián đoạn không?
- Có lịch sử đủ để chọn điểm trước thời gian nghi bị xâm nhập không?
- Có thể dựng môi trường phục hồi mà không phụ thuộc hoàn toàn vào hạ tầng bị ảnh hưởng không?
- Tài liệu, artifact và cấu hình tin cậy có thể truy cập bằng con đường phù hợp không?

Cơ chế lưu bất biến hoặc offline có thể hỗ trợ bảo vệ nguồn phục hồi, nhưng vẫn cần kiểm tra điều kiện quyền, khóa, thời hạn và khả năng sử dụng. Tên tính năng của sản phẩm chưa là bằng chứng đủ.

### 6.2. Danh tính, bí mật và quyền khẩn cấp

Lập trước cách truy cập quản trị khi IdP hoặc hệ thống thông thường không sẵn sàng: người được phép, điều kiện kích hoạt, xác thực, phạm vi, audit và thời điểm kết thúc.

Kế hoạch thay thế bí mật phải xét thứ tự phụ thuộc. Nếu thay hoặc hủy khóa duy nhất đọc được backup trước khi có phương án chuyển đổi, recovery có thể bị chặn. Canadian Centre for Cyber Security lưu ý tránh thay những thông tin truy cập cần để khôi phục theo cách làm mất khả năng phục hồi, đồng thời hướng dẫn phục hồi trong môi trường sạch được cách ly. [Nguồn: Ransomware playbook ITSM.00.099](https://www.cyber.gc.ca/en/guidance/ransomware-playbook-itsm00099).

Giữ quyền cần thiết để giải mã một bản sao lịch sử không đồng nghĩa tiếp tục dùng bí mật đã lộ cho dịch vụ đang chạy. Phải phân tách mục đích, quyền và kế hoạch thay thế rõ ràng.

### 6.3. Quy trình có thể thực hiện

Playbook cần đủ cụ thể để người trực biết tiền điều kiện, đầu vào, đầu ra, chủ sở hữu, thời gian dự kiến và điểm phải dừng. Cần có cách liên lạc và xác thực người điều phối khi một kênh thông thường không còn đáng tin.

Một checklist không có người phụ trách hoặc không biết lấy khóa ở đâu khó có giá trị trong incident. Năng lực thực hiện cần được kiểm chứng bằng diễn tập phù hợp.

## 7. Quy trình phục hồi có điều kiện chuyển bước

Một luồng minh họa:

~~~mermaid
flowchart TD
    A["Kích hoạt recovery theo phạm vi incident"] --> B["Chọn nguồn và điểm dữ liệu"]
    B --> C["Dựng môi trường, khôi phục kiểm soát nền tảng"]
    C --> D["Phục hồi dữ liệu và chức năng"]
    D --> E{"Đạt điều kiện dữ liệu, bảo mật và nghiệp vụ?"}
    E -->|"Chưa đạt"| F["Giữ giới hạn, xử lý nguyên nhân và kiểm chứng lại"]
    F --> C
    E -->|"Đạt"| G["Mở lại theo phạm vi được quyết định"]
    G --> H["Giám sát tăng cường và đối soát"]
    H --> I{"Ổn định theo điều kiện kết thúc?"}
    I -->|"Chưa"| F
    I -->|"Đạt"| J["Kết thúc giai đoạn recovery, theo dõi cải tiến"]
~~~

Luồng này không thay quy trình điều tra hoặc containment. Nếu kiểm tra phát hiện dấu hiệu mối đe dọa còn hoạt động, cần phối hợp lại với điều phối incident thay vì chỉ chạy restore thêm lần nữa.

### Điều kiện 1: đủ căn cứ chọn nguồn

Xác định nguồn, mốc dữ liệu, cách kiểm tra, phạm vi ảnh hưởng và những điều chưa biết. Không chỉ chọn bản có timestamp gần nhất.

### Điều kiện 2: môi trường và kiểm soát nền tảng sẵn sàng

Xác nhận môi trường phục hồi có ranh giới kết nối phù hợp, artifact và cấu hình được kiểm soát, danh tính quản trị đúng và cơ chế quan sát hoạt động.

### Điều kiện 3: dữ liệu và nghiệp vụ đạt

Kiểm tra tính nhất quán, khóa tham chiếu hoặc bất biến nghiệp vụ cần thiết, mốc dữ liệu, trạng thái tác vụ và các giao dịch liên quan. Kiểm tra cả hành vi hợp lệ và hành vi phải bị từ chối.

### Điều kiện 4: cho phép chuyển lưu lượng

Người có thẩm quyền quyết định dựa trên bằng chứng, phạm vi, rủi ro còn lại và tiêu chí chuyển bước. Có thể mở một phần nếu đã có điều kiện riêng cho mức dịch vụ đó.

Trước khi cho ghi dữ liệu, cần xác định nguồn có thẩm quyền và xử lý việc các node cũ có thể quay lại. Hai phía cùng nhận ghi có thể tạo dữ liệu không nhất quán.

### Điều kiện 5: quan sát và kết thúc

Theo dõi các tín hiệu nghiệp vụ và bảo mật trong khoảng đã quy định. Nếu xuất hiện dấu hiệu tái xâm nhập, sai dữ liệu, lỗi quyền hoặc thiếu audit bắt buộc, thực hiện phản ứng đã chuẩn bị.

Đưa dịch vụ trở lại không đồng nghĩa xóa ngay môi trường điều tra hoặc dữ liệu incident. Việc giữ, chuyển giao và xử lý bằng chứng cần theo quy trình riêng có liên quan.

## 8. Đánh giá nguồn khôi phục và dữ liệu đáng tin cậy

### 8.1. Toàn vẹn file không đồng nghĩa dữ liệu sạch

Checksum hoặc chữ ký phù hợp có thể hỗ trợ xác nhận hiện vật không đổi so với nguồn tham chiếu được tin cậy. Nó không tự chứng minh bản sao không chứa thay đổi trái phép đã tồn tại trước lúc backup.

Cần kết hợp các căn cứ phù hợp:

- Nguồn gốc và quyền tạo, sửa hoặc xóa bản sao.
- Mốc dữ liệu và khoảng thời gian có thể bị ảnh hưởng.
- Dấu hiệu kỹ thuật đã biết trong phạm vi điều tra.
- So sánh cấu hình, artifact và dữ liệu với baseline đáng tin cậy.
- Bất biến nghiệp vụ và nguồn đối soát độc lập khi có.
- Kết quả thử phục hồi trong môi trường được kiểm soát.

Một phép quét không phát hiện mã độc chỉ hỗ trợ kết luận trong khả năng và phạm vi của phép quét. Không ghi “chắc chắn sạch” nếu chưa có căn cứ cho mức khẳng định đó.

### 8.2. Điểm phục hồi gần nhất có thể không dùng được

Nếu bản mới nhất đã chứa dữ liệu bị sửa, chọn bản cũ hơn có thể cần thiết nhưng làm tăng khoảng mất dữ liệu. Khi khoảng đó vượt RPO, ghi nhận không đạt mục tiêu và đưa ra quyết định theo thẩm quyền.

Có thể xem xét tái lập giao dịch từ nguồn đáng tin cậy, nhưng phải đánh giá từng loại dữ liệu. Phát lại toàn bộ nhật ký thay đổi có thể đưa lại chính thao tác trái phép. Không tự coi replay là cách chứng minh mọi giao dịch đều đúng.

### 8.3. Các thành phần không có cùng điểm thời gian

Database, object storage, queue, chỉ mục tìm kiếm và hệ thống ngoài có thể không ở cùng mốc. Cần xác định nguồn có thẩm quyền cho từng trạng thái và cách xử lý chênh lệch.

Ví dụ database ghi một hóa đơn đã phát hành nhưng queue từ bản cũ vẫn có tác vụ gửi. Nếu worker chạy lại ngay, khách hàng có thể nhận lặp hoặc một tích hợp bị gọi thêm lần nữa.

Yêu cầu cần quy định khóa nghiệp vụ, tính lặp an toàn ở phạm vi hỗ trợ và đối soát trước khi phát lại. Với trường hợp không xác định được giao dịch ngoài đã hoàn tất hay chưa, cần quy trình xử lý cụ thể thay vì tự gửi lại vô điều kiện.

## 9. Tình huống: phục hồi dịch vụ hóa đơn sau xâm nhập

### 9.1. Bối cảnh

Giả sử thông tin truy cập của một worker bị lộ. Có bằng chứng dữ liệu bị sửa trong một khoảng thời gian và dịch vụ xuất hóa đơn phải dừng để xử lý.

Mục tiêu đã phê duyệt là RTO 2 giờ và RPO 15 phút, cùng các tiêu chí REC-03 đến REC-08. Dịch vụ chỉ đạt trạng thái sẵn sàng khi chức năng, dữ liệu, xác thực, quyền và audit thỏa điều kiện đã định.

Nhóm incident và nhóm recovery xác định một bản sao có mốc dữ liệu nhất quán 08:50 phù hợp để dùng theo căn cứ đã thu thập. Bản mới hơn lúc 08:58 chưa đủ căn cứ tin cậy do nằm trong khoảng bị ảnh hưởng.

### 9.2. Timeline minh họa

| Thời điểm | Sự kiện | Ý nghĩa đối với yêu cầu |
| --- | --- | --- |
| 08:50 | Mốc dữ liệu nhất quán của nguồn phục hồi được chọn | Dùng làm t_data, không lấy giờ sửa file |
| 09:00 | Chức năng xuất hóa đơn bị gián đoạn | t0 của hợp đồng đo |
| 09:15 | Recovery được kích hoạt, phạm vi và nguồn được ghi nhận | Có người điều phối và căn cứ chuyển bước |
| 09:30 | Môi trường phục hồi, quyền quản trị và phụ thuộc nền tảng sẵn sàng | Chưa đồng nghĩa nghiệp vụ đã phục hồi |
| 09:50 | Restore dữ liệu hoàn tất, health check trả 200 | Chỉ xác nhận một bước kỹ thuật |
| 10:10 | Kiểm thử phát hiện quyền cũ xuất hiện trong snapshot | Chưa được mở lại dịch vụ theo tiêu chí quyền |
| 10:30 | Áp dụng trạng thái quyền hiện hành, xử lý queue và cấu hình liên quan | Cần kiểm chứng lại phần thay đổi |
| 10:45 | Kiểm tra dữ liệu, quyền, chức năng, audit và điều kiện mở lại đạt | t_ready được xác nhận theo phạm vi |
| Sau 10:45 | Mở lại có kiểm soát và giám sát tăng cường | Theo dõi điều kiện ổn định và trigger phản ứng |

Tính kết quả theo hợp đồng:

~~~text
Thời gian phục hồi quan sát được:
  10:45 - 09:00 = 1 giờ 45 phút
  <= mục tiêu RTO 2 giờ

Khoảng dữ liệu mất theo thời gian:
  09:00 - 08:50 = 10 phút
  <= mục tiêu RPO 15 phút
~~~

Không dùng 09:50 làm t_ready khi tiêu chí quyền đến 10:45 mới đạt. Đồng thời, kết quả số học chỉ có giá trị khi căn cứ cho mốc dữ liệu và điều kiện sẵn sàng đã được kiểm chứng.

### 9.3. Các việc bảo mật cần được xác nhận

**Thông tin truy cập:** bí mật worker bị lộ không còn được dùng để truy cập; bí mật thay thế đã được cấp đúng phạm vi và các phụ thuộc đã được cập nhật.

**Quyền và phiên:** tài khoản, quyền hoặc phiên đã bị thu hồi không được sống lại do khôi phục snapshot cũ. Nguồn quyền hiện hành và cách áp dụng lại phải được ghi nhận.

**Dữ liệu:** các quan hệ và giá trị nghiệp vụ được kiểm tra bằng nguồn đối soát phù hợp; không chỉ so số lượng bản ghi.

**Worker:** tác vụ tồn đọng được phân loại, không tự phát lại toàn bộ. Những thao tác đã hoàn tất hoặc chưa rõ kết quả được xử lý theo quy trình.

**Audit:** thao tác recovery và hành vi sau mở lại được đối chiếu bằng mã liên quan, chủ thể và thời gian. Không ghi bí mật mới vào hồ sơ.

**Đường xâm nhập:** các biện pháp xử lý và giới hạn liên quan được nhóm có trách nhiệm xác nhận trong phạm vi quyết định. Nếu lỗ hổng hoặc khả năng truy cập liên quan chưa được kiểm soát đủ, restore dữ liệu không giải quyết được nguy cơ tái xâm nhập.

### 9.4. Nếu chỉ có bản tin cậy từ 08:35

Khoảng dữ liệu mất sẽ là 25 phút, vượt RPO 15 phút. Không sửa mốc t0 hoặc chọn timestamp khác của file để báo đạt.

Cần đánh giá khả năng tái lập dữ liệu từ nguồn đáng tin cậy, tác động nghiệp vụ và phương án duy trì hoạt động. Nếu chuyển sang mức dịch vụ giới hạn theo quyết định riêng, báo rõ mức đó; không dùng nó để kết luận toàn bộ hợp đồng phục hồi ban đầu đã đạt.

Nếu điều kiện sẵn sàng của hợp đồng bao gồm mục tiêu dữ liệu chưa đạt, phải ghi nhận chưa đủ điều kiện hoàn tất recovery theo hợp đồng đó.

## 10. Đưa dịch vụ trở lại mà không mở lại incident

### Chuyển lưu lượng từng phần

Có thể mở theo nhóm chức năng, nhóm người dùng hoặc phần lưu lượng đã định. Mỗi bước cần tín hiệu thành công, thời gian quan sát và điều kiện dừng.

Ví dụ một bước mở lại chức năng đọc không cho phép tự mở worker ghi dữ liệu. Phạm vi quyết định phải theo được các thành phần và tác dụng phụ.

### Giám sát tăng cường

Các tín hiệu nên gắn với incident và yêu cầu:

- Hoạt động đăng nhập, sử dụng quyền hoặc bí mật bất thường.
- Thay đổi cấu hình và dữ liệu ngoài phạm vi dự kiến.
- Sai lệch giữa trạng thái hóa đơn, file xuất và queue.
- Tác vụ hoặc tích hợp bị lặp.
- Thiếu sự kiện audit, độ trễ thu thập hoặc nguồn mất dữ liệu.
- Lỗi nghiệp vụ, mức sẵn sàng và thời gian xử lý.

Không có cảnh báo chưa chứng minh không còn vấn đề nếu nguồn quan sát chưa được xác nhận hoạt động.

### Dừng hoặc quay lại trạng thái trước

Khi phát hiện sai lệch, phản ứng có thể là hạn chế một chức năng, cách ly thành phần, giữ lưu lượng ở mức hiện tại hoặc quay lại điều phối incident. Cần xác định trước người quyết định và tác động dữ liệu.

Rollback không được hiểu đơn giản là đưa snapshot cũ vào chạy lại. Sau khi môi trường mới đã nhận ghi, quay về nguồn cũ có thể mất giao dịch hoặc tái đưa trạng thái bị xâm nhập vào sử dụng. Phương án cần xử lý cả dữ liệu và quyền ở hai phía.

### Kết thúc recovery có điều kiện rõ ràng

Điều kiện kết thúc nên gồm trạng thái dịch vụ, phạm vi dữ liệu, kiểm soát bảo mật, kết quả quan sát, rủi ro còn lại, người tiếp nhận vận hành và việc cần theo dõi.

Phục hồi không lấy lại được tính bí mật của dữ liệu đã bị sao chép ra ngoài. Nếu incident có khả năng lộ dữ liệu, hoạt động điều tra, quản lý tác động và nghĩa vụ liên quan tiếp tục theo phạm vi thích hợp dù dịch vụ đã hoạt động lại.

## 11. Kiểm thử khả năng recovery trước khi cần dùng

Một kế hoạch chưa từng được thực hiện có thể bỏ sót thời gian lấy quyền, thiếu khóa, tài liệu không truy cập được hoặc phụ thuộc ngoài phạm vi.

Có thể kết hợp các mức kiểm chứng:

| Mức | Điều giúp kiểm tra | Giới hạn |
| --- | --- | --- |
| Tabletop | Quyết định, vai trò, thứ tự và tình huống khó | Chưa chứng minh restore, thời gian hoặc dữ liệu thực tế |
| Thử phục hồi dữ liệu | Khả năng đọc bản sao và tính nhất quán trong phạm vi | Có thể chưa đủ phụ thuộc nghiệp vụ |
| Diễn tập tích hợp | Danh tính, khóa, dữ liệu, mạng, ứng dụng và audit | Cần ghi khác biệt với môi trường mục tiêu |
| Chuyển dịch vụ có kiểm soát | Khả năng chuyển lưu lượng và vận hành theo điều kiện | Không đại diện tự động cho mọi loại incident |
| Kiểm tra tình huống lỗi | Phản ứng khi nguồn, khóa, quyền hoặc phụ thuộc không đạt | Chỉ bao phủ các tình huống được thiết kế |

Tần suất và phạm vi cần theo mức quan trọng, thay đổi kiến trúc và kinh nghiệm sự cố. Sau thay đổi có ảnh hưởng như đổi kho backup, IdP, quản lý khóa hoặc queue, cần đánh giá phần phải kiểm chứng lại.

### Kịch bản cần cân nhắc

- Bản sao mới nhất không thể sử dụng hoặc không đủ căn cứ tin cậy.
- Hệ thống quản lý khóa chính không sẵn sàng.
- IdP hoặc kênh quản trị thông thường bị ảnh hưởng.
- Quyền bị thu hồi xuất hiện lại sau restore.
- Queue và database có mốc dữ liệu khác nhau.
- Audit không nhận được sự kiện trong môi trường phục hồi.
- Node cũ quay lại sau khi đã chuyển quyền ghi.
- Tài liệu hoặc nguồn artifact phụ thuộc vào chính môi trường đang gián đoạn.

Mỗi tình huống cần có kết quả mong đợi và điểm dừng, không chỉ mục tiêu “thử xem có chạy được không”.

### Tiêu chí kiểm thử phải bao gồm hành vi bị cấm

Ví dụ:

- Người dùng đúng quyền thực hiện được nghiệp vụ trên dữ liệu đã phục hồi.
- Người sai tổ chức không đọc được dữ liệu tổ chức khác.
- Thông tin truy cập đã bị thu hồi không hoạt động lại.
- Worker không phát sinh tác dụng phụ trùng trong các trường hợp đã quy định.
- Chế độ khẩn cấp không mở rộng quyền ngoài phạm vi và hết hiệu lực đúng điều kiện.
- Khi thiếu điều kiện bảo mật bắt buộc, bước chuyển lưu lượng bị chặn hoặc bị giới hạn theo policy.

Chỉ chạy ca nghiệp vụ hợp lệ chưa chứng minh cơ chế bảo vệ sau phục hồi vẫn đúng.

### Tính đại diện của phép đo

Nếu thử trên dữ liệu nhỏ, mạng nhanh hơn hoặc bỏ qua nhiều phụ thuộc, ghi rõ giới hạn trước khi dùng kết quả để hỗ trợ RTO/RPO.

Không tự nhân thời gian restore một file với số file rồi coi đó là thời gian phục hồi dịch vụ. Các bước truy cập, giải mã, kiểm tra dữ liệu, đối soát và chuyển lưu lượng có thể là phần chi phối.

## 12. Bằng chứng cho yêu cầu recovery

Một hồ sơ phục hồi hoặc diễn tập nên giữ:

1. Mã incident hoặc lần diễn tập, phạm vi và kịch bản.
2. Phiên bản yêu cầu, tiêu chí và playbook được sử dụng.
3. Danh mục dịch vụ, phụ thuộc và thứ tự thực hiện.
4. Nguồn khôi phục, mốc dữ liệu và căn cứ lựa chọn.
5. Artifact, cấu hình, policy và trạng thái quyền liên quan.
6. Timeline gồm t0, các bước quan trọng, t_data và t_ready.
7. Kết quả kiểm tra dữ liệu, nghiệp vụ, xác thực, quyền và audit.
8. Sai lệch, rủi ro còn lại, quyết định mở lại và giới hạn.
9. Kết quả quan sát sau mở lại và điều kiện kết thúc.
10. Việc cần khắc phục, người phụ trách và ca kiểm chứng lại.

Ví dụ bản tóm tắt nội bộ:

~~~text
Recovery record: REC-RUN-042
Scope: dịch vụ xuất hóa đơn và các đường truy cập được liệt kê
Scenario: dữ liệu bị sửa và thông tin truy cập worker bị lộ
Requirements: REC-01 ... REC-08, phiên bản đã thống nhất

Service interruption: 09:00
Recovered consistent data point: 08:50
Restore job completed: 09:50
Security and business readiness confirmed: 10:45

Observed recovery time: 1 giờ 45 phút
Observed data-loss interval: 10 phút
RTO target: 2 giờ
RPO target: 15 phút

Evidence: tham chiếu timeline, kiểm thử, cấu hình và audit
Limitations: phạm vi chưa được đánh giá hoặc giả định còn lại
Decision: người có thẩm quyền, thời điểm, phạm vi mở lại
Follow-up: việc cần xử lý và điều kiện đóng
~~~

Đây là mẫu thông tin, không phải báo cáo rằng tình huống này đã được thực hiện trên hệ thống thật.

Giữ bằng chứng phù hợp về nguồn dữ liệu và cách xác định mốc; một bảng thời gian do người viết tự điền không tự chứng minh các sự kiện đã xảy ra đúng như vậy.

Thông tin bí mật, token và khóa phục hồi không được đưa nguyên vẹn vào báo cáo chia sẻ. Dùng tham chiếu an toàn tới nguồn có quyền phù hợp. Cũng cần bảo vệ log và dữ liệu incident khi sao chép sang môi trường phục hồi.

## 13. Trách nhiệm và truyền thông trong recovery

| Vai trò | Trách nhiệm minh họa |
| --- | --- |
| Điều phối incident | Giữ phạm vi, mức ưu tiên, quyết định chuyển giai đoạn và phối hợp các nhóm |
| Chủ dịch vụ / nghiệp vụ | Xác định tác động, chức năng tối thiểu và tiêu chí sẵn sàng |
| Nhóm hạ tầng / recovery | Dựng môi trường, thực hiện các bước và ghi nhận timeline |
| Nhóm danh tính và bảo mật | Xác nhận quyền, bí mật, kiểm soát và điều kiện liên quan tới mối đe dọa |
| Chủ dữ liệu | Đánh giá tính nhất quán, mốc dữ liệu và đối soát nghiệp vụ |
| Nhóm quan sát / vận hành | Xác nhận audit, giám sát và khả năng xử lý khi có sai lệch |
| Người quyết định có thẩm quyền | Chấp nhận phạm vi mở lại và rủi ro còn lại trong hạn mức được giao |
| Người phụ trách truyền thông và nghĩa vụ liên quan | Thống nhất nội dung, đối tượng, thời điểm và căn cứ thông báo |

Tên và cách phân công tùy tổ chức. Điều quan trọng là không để người thực hiện restore tự suy ra họ đã có mọi thẩm quyền mở lại nghiệp vụ hoặc chấp nhận mất dữ liệu.

Thông tin trạng thái cần phân biệt “restore xong”, “kiểm chứng xong”, “đang phục vụ giới hạn” và “recovery hoàn tất”. Một thông báo “đã khôi phục” quá sớm có thể khiến nhóm khác gửi lại lưu lượng hoặc chạy tác vụ chưa được phép.

Nếu có nghĩa vụ thông báo theo hợp đồng hoặc quy định, người phụ trách cần xác định điều áp dụng. Không dùng một thời hạn chung chưa được xác nhận để thay thế việc xem xét phạm vi incident.

## 14. Sau recovery: biến bài học thành yêu cầu

Mục tiêu cải thiện là sửa các khoảng trống có bằng chứng, không chỉ cập nhật câu chữ của tài liệu.

Ví dụ:

| Điều quan sát được | Yêu cầu hoặc thay đổi cần xem xét |
| --- | --- |
| Mất nhiều thời gian lấy quyền đọc backup | Đặc tả và diễn tập đường truy cập khẩn cấp, người sở hữu và kiểm soát |
| Khóa phụ thuộc vào hạ tầng đã bị ảnh hưởng | Bổ sung khả năng truy cập hoặc phục hồi khóa với ràng buộc bảo mật |
| Quyền cũ sống lại | Bổ sung đối soát trạng thái quyền và kiểm thử sau restore |
| Queue phát lại thao tác đã hoàn tất | Bổ sung đối soát, khóa nghiệp vụ và ca phát lại có kiểm soát |
| Audit chỉ hoạt động ở môi trường chính | Đưa khả năng quan sát vào điều kiện sẵn sàng phục hồi |
| Bản sao tin cậy quá cũ so với RPO | Xem lại chiến lược dữ liệu, thời hạn lưu và cơ chế phát hiện ảnh hưởng |
| Không biết ai được mở lại chức năng | Làm rõ thẩm quyền, tiêu chí chuyển bước và giới hạn quyết định |

Mỗi việc cần có người phụ trách, ưu tiên theo rủi ro, mốc thực hiện và cách kiểm chứng. Thay đổi yêu cầu phải có phiên bản và liên kết tới bài học incident tương ứng.

Không sửa mục tiêu RTO/RPO chỉ để báo cáo lần diễn tập trước thành công. Nếu mục tiêu cần điều chỉnh vì tác động hoặc khả năng thực tế, đó là quyết định mới có căn cứ và thẩm quyền.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Coi backup thành công là recovery đạt | Không biết dữ liệu và nghiệp vụ có dùng được không | Thử phục hồi và kiểm tra tiêu chí đầy đủ |
| Chỉ đo thời gian restore | Bỏ sót chuẩn bị, kiểm chứng và chuyển lưu lượng | Đo theo mốc hợp đồng của dịch vụ |
| Chọn bản sao mới nhất mà không đánh giá | Có thể đưa lại trạng thái bị xâm nhập | Xác định nguồn, mốc và căn cứ tin cậy |
| Chỉ kiểm tra checksum | Không phát hiện dữ liệu sai đã tồn tại trước backup | Kết hợp kiểm tra nguồn, nội dung và nghiệp vụ |
| Đổi hoặc hủy khóa không xét phụ thuộc | Mất khả năng giải mã bản sao cần dùng | Lập thứ tự chuyển đổi và kiểm chứng quyền truy cập |
| Khôi phục snapshot danh tính cũ | Quyền hoặc phiên đã thu hồi có thể sống lại | Đối soát với trạng thái có thẩm quyền hiện hành |
| Mở worker ngay sau database | Phát lại thao tác hoặc gửi dữ liệu sai | Đối soát queue và nguồn trạng thái trước khi chạy |
| Mở lại khi audit chưa hoạt động | Thiếu khả năng nhận ra tái xâm nhập hoặc sai lệch | Kiểm tra quan sát đầu cuối trước phạm vi nhạy cảm |
| Rollback chỉ bằng đổi địa chỉ dịch vụ | Có thể mất dữ liệu mới hoặc tạo hai nguồn ghi | Chuẩn bị điều kiện dữ liệu và quyền ở hai phía |
| Báo recovery hoàn tất quá sớm | Các nhóm dùng dịch vụ ngoài phạm vi được phép | Thông báo đúng mức trạng thái và điều kiện |

## 16. Thực hành đặc tả recovery

Với một dịch vụ hóa đơn giả định, xây bộ yêu cầu gồm phạm vi nghiệp vụ, RTO/RPO, nguồn dữ liệu, phụ thuộc, quyền khẩn cấp, bí mật, audit và điều kiện mở lại.

Thiết kế một diễn tập trong đó bản sao mới nhất không đủ tin cậy và snapshot cũ có quyền đã bị thu hồi. Xác định mốc đo, nguồn đối soát, ca cho phép và từ chối, thứ tự khôi phục, cách xử lý queue và bằng chứng cần lưu.

Sau đó bổ sung tình huống kho khóa hoặc IdP chính không sẵn sàng. Kế hoạch cần chỉ ra cách duy trì kiểm soát, phần không thể phục hồi theo mục tiêu và quyết định cần đưa ra, thay vì tự bỏ qua các điều kiện bảo mật.

Một lần recovery cần để lại căn cứ về dịch vụ đã trở lại ở mức nào, dữ liệu được khôi phục tới đâu, kiểm soát nào đã được xác nhận và rủi ro nào còn được theo dõi. Những căn cứ đó phải quay lại yêu cầu, kiến trúc, playbook và kiểm thử cho các lần vận hành tiếp theo.
