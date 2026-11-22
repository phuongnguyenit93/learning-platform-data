# Kiểm tra sao lưu, khôi phục và mục tiêu phục hồi theo yêu cầu

**Chương:** Phi chức năng  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Sao lưu dữ liệu chỉ có giá trị khi tổ chức có thể khôi phục dữ liệu và đưa dịch vụ trở lại trạng thái sử dụng được trong giới hạn đã cam kết. Một tác vụ sao lưu chạy thành công không chứng minh rằng bản sao lưu đầy đủ, không bị hỏng, có thể giải mã hoặc tương thích với phiên bản ứng dụng cần phục hồi. Tương tự, khôi phục được một cơ sở dữ liệu không có nghĩa toàn bộ dịch vụ đã sẵn sàng: cấu hình, khóa mã hóa, danh tính, hàng đợi, tệp đính kèm và các hệ thống phụ thuộc cũng có thể cần được phục hồi.

Kiểm thử sao lưu và khôi phục cần bắt đầu từ yêu cầu về mức mất dữ liệu và thời gian gián đoạn có thể chấp nhận. Nhóm phải xác định rõ mục tiêu phục hồi, thiết kế tình huống kiểm thử, thực hiện khôi phục trong môi trường kiểm soát và thu thập bằng chứng về tính toàn vẹn cũng như thời gian hoàn thành.

Bài học này giải thích cách xác định RPO và RTO, phân biệt sao lưu với các cơ chế sẵn sàng cao, lập kế hoạch kiểm thử backup/restore và đánh giá khả năng phục hồi của cả dịch vụ. Trọng tâm là chứng minh khả năng khôi phục theo yêu cầu đã thống nhất, không chỉ chứng minh rằng một công việc sao lưu đã chạy.

Sau bài học, người học có thể:

- Giải thích mục tiêu RPO, RTO và mối liên hệ của chúng với yêu cầu nghiệp vụ.
- Xác định phạm vi dữ liệu, cấu hình và phụ thuộc cần được sao lưu, khôi phục.
- Phân biệt backup, snapshot, replication và high availability.
- Thiết kế kiểm thử tính toàn vẹn, khả năng đọc, giải mã và khả năng sử dụng của bản sao lưu.
- Thực hiện diễn tập khôi phục theo kịch bản và đo thời gian phục hồi thực tế.
- Đánh giá sai lệch giữa kết quả kiểm thử với RPO/RTO, ghi nhận rủi ro còn lại và cải thiện kế hoạch phục hồi.

## 1. Vì sao phải kiểm thử sao lưu và khôi phục?

Hệ thống có thể mất dữ liệu hoặc ngừng hoạt động do nhiều nguyên nhân: lỗi phần cứng, thao tác xóa nhầm, lỗi phần mềm, hỏng cơ sở dữ liệu, cấu hình sai, sự cố trung tâm dữ liệu, lỗi nhà cung cấp, tấn công mã độc hoặc tài khoản có quyền cao bị chiếm đoạt. Một số sự cố chỉ ảnh hưởng một thành phần; một số khác làm mất khả năng truy cập toàn bộ môi trường.

Sao lưu tạo ra một hoặc nhiều điểm có thể dùng để khôi phục dữ liệu. Kiểm thử khôi phục xác minh rằng các điểm đó thực sự dùng được và quy trình có thể đưa hệ thống trở lại trạng thái cần thiết.

Nếu không thực hiện kiểm thử khôi phục, tổ chức có thể phát hiện quá muộn rằng:

- Tệp sao lưu bị hỏng hoặc chỉ chứa một phần dữ liệu.
- Bản sao lưu hoàn tất nhưng không thể giải nén, đọc hoặc nạp vào phiên bản cơ sở dữ liệu dự kiến.
- Khóa mã hóa, thông tin xác thực hoặc catalog sao lưu không còn truy cập được.
- Dữ liệu có thể khôi phục nhưng cấu hình ứng dụng, tệp đính kèm hoặc khóa định danh lại bị thiếu.
- Thời gian tải dữ liệu và xác minh lâu hơn mục tiêu phục hồi.
- Các bước trong runbook không rõ, quyền truy cập không đủ hoặc phụ thuộc bên ngoài không sẵn sàng.
- Bản sao lưu gần nhất đã chứa dữ liệu hỏng hoặc mã độc trước thời điểm sự cố được phát hiện.

Kiểm thử sao lưu và khôi phục vì vậy là một phần của kiểm thử phi chức năng về độ tin cậy, khả năng phục hồi và tính liên tục của dịch vụ. Nó cũng cung cấp bằng chứng để đánh giá các cam kết nội bộ, hợp đồng và yêu cầu tuân thủ có liên quan.

## 2. Hiểu các mục tiêu phục hồi

Hai chỉ số thường dùng để mô tả yêu cầu phục hồi là RPO và RTO. Cần thống nhất cách đo, điểm bắt đầu, điểm kết thúc và phạm vi dịch vụ trước khi dùng chúng làm tiêu chí kiểm thử.

### 2.1. RPO — mục tiêu điểm phục hồi

RPO (Recovery Point Objective) là mức mất dữ liệu tối đa có thể chấp nhận được, thường biểu diễn bằng khoảng thời gian. RPO cho biết tổ chức có thể chấp nhận khôi phục dữ liệu về một thời điểm cách thời điểm gián đoạn bao lâu.

Ví dụ, RPO 15 phút có nghĩa là trong tình huống sự cố thuộc phạm vi đánh giá, dữ liệu được khôi phục không được cũ hơn quá 15 phút so với mốc sự cố đã thống nhất. Nếu sự cố xảy ra lúc 14:00 và điểm phục hồi hợp lệ gần nhất là 13:50, khoảng mất dữ liệu tiềm tàng là 10 phút, nên đạt mục tiêu RPO 15 phút trong ví dụ này.

RPO không đồng nghĩa với tần suất chạy bản sao lưu đầy đủ. Nếu hệ thống dùng backup nền kết hợp log giao dịch hoặc cơ chế point-in-time recovery, điểm phục hồi có thể gần thời điểm sự cố hơn thời điểm của bản backup đầy đủ gần nhất.

### 2.2. RTO — mục tiêu thời gian phục hồi

RTO (Recovery Time Objective) là khoảng thời gian tối đa được phép để khôi phục dịch vụ hoặc năng lực nghiệp vụ về mức sử dụng đã xác định sau khi xảy ra gián đoạn.

Ví dụ, RTO 90 phút nghĩa là dịch vụ phải đạt điều kiện sẵn sàng đã thống nhất trong tối đa 90 phút kể từ mốc bắt đầu sự cố. Nhóm cần xác định rõ đồng hồ bắt đầu khi sự cố xảy ra, khi được phát hiện hay khi được tuyên bố; đồng thời xác định điểm kết thúc là máy chủ khởi động, API phản hồi hay người dùng có thể hoàn tất nhiệm vụ chính.

Để tránh báo cáo RTO quá lạc quan, điểm kết thúc nên bao gồm các bước cần thiết để dịch vụ thực sự có thể sử dụng: phục hồi dữ liệu, khởi động thành phần, kiểm tra tính nhất quán, xác minh tích hợp và cho phép lưu lượng theo quy trình đã định. Chỉ khởi động được máy chủ không chứng minh dịch vụ đã phục hồi.

### 2.3. Phân biệt RPO và RTO

| Chỉ số | Câu hỏi | Cách biểu diễn | Bằng chứng kiểm thử |
|---|---|---|---|
| RPO | Có thể mất tối đa bao nhiêu dữ liệu? | Khoảng thời gian | Thời điểm của dữ liệu/điểm phục hồi hợp lệ cuối cùng so với mốc sự cố |
| RTO | Có thể gián đoạn tối đa bao lâu? | Khoảng thời gian | Thời gian từ mốc bắt đầu sự cố đến khi dịch vụ đạt tiêu chí sử dụng |

Một hệ thống có thể đạt RPO nhưng không đạt RTO: dữ liệu được khôi phục đến thời điểm rất gần sự cố nhưng mất nhiều giờ để đưa dịch vụ hoạt động. Ngược lại, hệ thống có thể nhanh chóng khởi động lại từ một bản sao lưu cũ và đạt RTO, nhưng mất quá nhiều dữ liệu so với RPO.

### 2.4. Các khái niệm liên quan

- **MTPD/MAO:** thời gian gián đoạn tối đa có thể chịu đựng hoặc thời gian hoạt động tối đa có thể chấp nhận. Thuật ngữ và cách dùng khác nhau giữa các tổ chức; cần định nghĩa trong chính sách liên tục kinh doanh.
- **WRT (Work Recovery Time):** thời gian cần thêm sau khi hệ thống kỹ thuật hoạt động để khôi phục công việc, xử lý tồn đọng, đối soát hoặc hoàn tất thao tác thủ công. Một số tổ chức tính WRT bên trong mục tiêu thời gian phục hồi tổng thể, một số tách riêng; phải thống nhất cách đo.
- **Rủi ro mất dữ liệu:** hậu quả nghiệp vụ của dữ liệu bị mất, sai lệch hoặc không nhất quán sau phục hồi.
- **Điểm phục hồi (recovery point):** thời điểm dữ liệu được khôi phục phản ánh, có thể là thời điểm của backup hoặc một thời điểm được dựng lại bằng log giao dịch.

RTO/RPO nên được đặt trong bối cảnh nghiệp vụ. Một dịch vụ báo cáo nội bộ có thể chấp nhận RPO và RTO dài hơn hệ thống nhận thanh toán hoặc xử lý đơn hàng. Không nên áp một con số giống nhau cho mọi hệ thống nếu hậu quả và mức độ phụ thuộc khác nhau.

## 3. Chuyển yêu cầu nghiệp vụ thành mục tiêu kiểm thử

RPO và RTO chỉ có ý nghĩa khi được xác định theo dịch vụ, dữ liệu, tình huống sự cố và mức chức năng cần phục hồi.

### 3.1. Xác định dịch vụ và quy trình nghiệp vụ quan trọng

Trước tiên, xác định:

- Dịch vụ hoặc quy trình nào cần được phục hồi.
- Nhóm người dùng hoặc hệ thống nào phụ thuộc vào nó.
- Hoạt động nào phải được khôi phục trước để nghiệp vụ có thể tiếp tục.
- Dữ liệu nào là thiết yếu, dữ liệu nào có thể tái tạo từ nguồn khác.
- Hậu quả nếu dữ liệu mất, dữ liệu cũ hoặc dịch vụ ngừng hoạt động.
- Các nghĩa vụ pháp lý, hợp đồng hoặc cam kết dịch vụ có liên quan.

Không phải mọi thành phần cần phục hồi cùng lúc. Một ứng dụng có thể cần khôi phục chức năng đọc đơn hàng trước, trong khi báo cáo phân tích có thể phục hồi sau. Thứ tự phải phản ánh phụ thuộc và mức ưu tiên nghiệp vụ.

### 3.2. Xác định mức phục hồi có thể chấp nhận

RPO/RTO nên được bên chịu trách nhiệm nghiệp vụ, kỹ thuật, vận hành và quản trị rủi ro thống nhất. Nhóm cần ghi rõ:

- Phạm vi dịch vụ và dữ liệu áp dụng.
- Loại sự cố được tính đến, chẳng hạn lỗi một máy chủ, mất vùng triển khai hoặc hỏng dữ liệu.
- Mốc bắt đầu đo RTO và RPO.
- Tiêu chí kết thúc phục hồi.
- Mức dữ liệu có thể mất và cách xử lý dữ liệu phát sinh sau điểm phục hồi.
- Các ngoại lệ, giả định và phụ thuộc bên ngoài.

Nếu yêu cầu chưa có con số, hãy thu thập thông tin để bên nghiệp vụ quyết định. Không tự chọn một mục tiêu kỹ thuật rồi coi đó là cam kết được phê duyệt.

### 3.3. Ví dụ về mục tiêu theo dịch vụ

| Dịch vụ minh họa | RPO mục tiêu | RTO mục tiêu | Lý do nghiệp vụ |
|---|---:|---:|---|
| Xử lý thanh toán | 5 phút | 60 phút | Cần bảo vệ trạng thái giao dịch và tiếp tục xử lý đơn hàng |
| Quản lý đơn hàng | 15 phút | 90 phút | Mất dữ liệu ảnh hưởng đến đơn và vận hành giao hàng |
| Báo cáo nội bộ | 24 giờ | 2 ngày | Có thể tái tạo một phần từ dữ liệu nguồn |

Các giá trị chỉ nhằm minh họa sự khác nhau giữa các dịch vụ. Mục tiêu thực tế phải được phân tích theo tác động, kiến trúc, chi phí và khả năng đáp ứng.

### 3.4. Viết tiêu chí chấp nhận cho một cuộc diễn tập

Ví dụ tiêu chí cho hệ thống quản lý đơn hàng:

- Điểm phục hồi hợp lệ gần nhất không cũ hơn 15 phút so với mốc sự cố.
- Dịch vụ đọc và cập nhật đơn hàng đạt tiêu chí sẵn sàng trong 90 phút.
- Các bản ghi đơn hàng và giao dịch trong phạm vi kiểm tra không bị thiếu hoặc trùng ngoài mức sai lệch được phê duyệt.
- Các tác vụ nền và tích hợp quan trọng được kích hoạt lại an toàn.
- Báo cáo diễn tập ghi nhận thời điểm bắt đầu, các mốc khôi phục, kết quả xác minh và mọi ngoại lệ.

Tiêu chí cần mô tả được cách đo. Cụm từ “khôi phục thành công” không đủ rõ nếu không nêu dữ liệu nào phải có, chức năng nào phải hoạt động và ai xác nhận.

## 4. Phân biệt backup, snapshot, replication và high availability

Các cơ chế này có thể cùng góp phần vào khả năng phục hồi, nhưng giải quyết các vấn đề khác nhau.

### 4.1. Backup — bản sao lưu

Backup là bản sao dữ liệu hoặc trạng thái được lưu giữ để có thể khôi phục về một thời điểm hoặc phiên bản trước. Backup có thể được tạo định kỳ, theo sự kiện hoặc liên tục tùy công nghệ.

Các dạng phổ biến:

- **Full backup:** sao lưu toàn bộ phạm vi dữ liệu được chọn. Dễ hiểu khi khôi phục nhưng có thể tốn thời gian và dung lượng.
- **Incremental backup:** sao lưu phần thay đổi kể từ lần backup trước theo cách triển khai. Khôi phục có thể cần bản đầy đủ và chuỗi incremental liên quan.
- **Differential backup:** sao lưu phần thay đổi kể từ lần full backup gần nhất. Chuỗi khôi phục thường gồm bản full và bản differential phù hợp.
- **Log backup / point-in-time recovery:** lưu log giao dịch hoặc thay đổi để dựng dữ liệu đến một thời điểm cụ thể, nếu hệ thống hỗ trợ và chuỗi log còn đầy đủ.
- **Logical backup:** xuất dữ liệu ở dạng logic như bảng, bản ghi hoặc lệnh SQL.
- **Physical backup:** sao lưu các tệp hoặc cấu trúc lưu trữ ở mức vật lý theo công nghệ cơ sở dữ liệu.

Mỗi phương thức có yêu cầu khác nhau về thứ tự, tính nhất quán, phiên bản và phụ thuộc. Kiểm thử cần xác minh đúng chuỗi cần thiết để khôi phục, không chỉ một tệp được tạo gần đây.

### 4.2. Snapshot — ảnh chụp trạng thái

Snapshot ghi lại trạng thái của một ổ đĩa, volume, máy ảo hoặc hệ thống lưu trữ tại một thời điểm. Snapshot có thể tạo điểm quay lui nhanh và hữu ích cho vận hành, nhưng không tự động là bản backup độc lập.

Nếu snapshot nằm cùng tài khoản, vùng lỗi hoặc hệ thống lưu trữ với dữ liệu gốc, một sự cố diện rộng hoặc quyền truy cập bị chiếm có thể ảnh hưởng cả hai. Snapshot cũng có thể chỉ nhất quán ở mức crash-consistent, chưa chắc nhất quán ở mức ứng dụng hoặc giao dịch. Cần hiểu đặc tính của công nghệ và kiểm tra quy trình tạo/khôi phục cụ thể.

### 4.3. Replication — sao chép dữ liệu

Replication duy trì bản sao dữ liệu ở một nút, vùng hoặc hệ thống khác để tăng khả năng sẵn sàng hoặc phân phối tải. Replication có thể giúp chuyển đổi khi một nút lỗi, nhưng thay đổi sai, xóa nhầm hoặc mã độc có thể được sao chép sang bản phụ.

Replication không thay thế backup có lịch sử điểm phục hồi độc lập. Muốn khôi phục về trạng thái trước một thao tác phá hoại, cần có điểm sao lưu hoặc lịch sử đủ để quay lại.

### 4.4. High availability — tính sẵn sàng cao

High availability (HA) dùng dự phòng và cơ chế chuyển đổi để giảm gián đoạn khi một thành phần gặp lỗi. HA giúp dịch vụ tiếp tục hoạt động, nhưng không nhất thiết bảo vệ khỏi lỗi logic, dữ liệu bị hỏng hoặc thao tác xóa nhầm được nhân bản.

| Cơ chế | Mục tiêu chính | Rủi ro không tự giải quyết |
|---|---|---|
| Backup | Khôi phục dữ liệu hoặc trạng thái trước đó | Bản sao lưu có thể hỏng, thiếu hoặc không khôi phục được |
| Snapshot | Tạo điểm trạng thái để quay lui nhanh | Có thể cùng miền lỗi và chưa nhất quán ứng dụng |
| Replication | Duy trì bản sao để tăng sẵn sàng hoặc phân phối | Có thể sao chép cả dữ liệu sai hoặc thao tác phá hoại |
| HA | Giảm gián đoạn khi thành phần lỗi | Không thay thế khả năng quay về điểm dữ liệu sạch trước sự cố |

Một kiến trúc phục hồi tốt có thể kết hợp HA, replication và backup độc lập. Kiểm thử cần chứng minh từng cơ chế đáp ứng mục tiêu riêng và phối hợp đúng khi xảy ra sự cố.

## 5. Xác định đầy đủ phạm vi cần sao lưu

Một hệ thống thường có nhiều loại trạng thái. Chỉ sao lưu cơ sở dữ liệu có thể chưa đủ để phục hồi dịch vụ.

Hãy lập danh mục:

- **Dữ liệu nghiệp vụ:** cơ sở dữ liệu, tệp tải lên, tài liệu, ảnh và dữ liệu giao dịch.
- **Cấu hình ứng dụng:** cấu hình triển khai, biến môi trường được quản lý, định tuyến và tham số dịch vụ.
- **Mã và artifact triển khai:** phiên bản ứng dụng, image, package hoặc artifact cần thiết để khởi động lại đúng phiên bản.
- **Danh tính và quyền:** cấu hình IAM, tài khoản dịch vụ, vai trò và quyền truy cập cần để vận hành phục hồi.
- **Khóa và bí mật:** khóa mã hóa, chứng thư, thông tin xác thực và cơ chế truy cập bí mật.
- **Hàng đợi và trạng thái xử lý:** thông điệp chưa xử lý, offset, trạng thái outbox/inbox hoặc thông tin giúp xử lý lại an toàn.
- **Tài nguyên phụ thuộc:** DNS, cấu hình mạng, chứng thư, gateway, storage, dịch vụ định danh và tích hợp đối tác.
- **Catalog và metadata backup:** danh mục bản sao, manifest, log, thông tin phiên bản, chuỗi incremental và thời điểm tạo.

Không phải tất cả đều cần sao lưu theo cùng cách. Một số thành phần có thể được tái tạo từ mã nguồn hoặc cấu hình quản lý bằng phiên bản; một số bí mật cần được bảo vệ và phục hồi qua quy trình riêng. Hãy ghi rõ nguồn phục hồi và người chịu trách nhiệm cho từng mục.

### 5.1. Nhất quán giữa các thành phần

Nếu cơ sở dữ liệu và tệp đính kèm được sao lưu ở các thời điểm khác nhau, sau khôi phục có thể xuất hiện bản ghi tham chiếu đến tệp không tồn tại hoặc tệp không còn bản ghi sở hữu. Tương tự, trạng thái đơn hàng và thông điệp trong hàng đợi có thể không khớp nếu không có chiến lược snapshot hoặc đối soát.

Nhóm cần xác định:

- Các thành phần nào phải được chụp cùng một điểm nhất quán?
- Có cần tạm dừng ghi, tạo checkpoint hoặc dùng cơ chế backup nhất quán của ứng dụng không?
- Các thay đổi phát sinh trong lúc sao lưu được xử lý thế nào?
- Sau khôi phục, cần đối soát hoặc phát lại thông điệp nào?
- Có thể tái tạo thành phần nào từ nguồn dữ liệu khác?

### 5.2. Mã hóa và quản lý khóa

Backup có thể chứa dữ liệu nhạy cảm. Cần xác minh dữ liệu được mã hóa khi truyền và khi lưu theo chính sách. Đồng thời, khóa giải mã phải được bảo vệ và có thể truy cập trong tình huống phục hồi.

Nếu khóa chỉ tồn tại trong cùng môi trường bị mất hoặc bị chiếm quyền, bản backup mã hóa có thể trở nên vô dụng. Kiểm thử cần xác minh quy trình truy cập khóa khẩn cấp, quyền hạn, phê duyệt và khả năng giải mã trong môi trường phục hồi được kiểm soát. Không ghi khóa hoặc bí mật thật vào báo cáo diễn tập.

### 5.3. Tính độc lập và khả năng chống phá hoại

Để giảm nguy cơ một sự cố phá hủy cả dữ liệu gốc và backup, tổ chức có thể dùng bản sao ở tài khoản hoặc miền quản trị riêng, lưu trữ ngoại tuyến hoặc cơ chế bất biến (immutable/WORM) trong thời hạn xác định. Kiểm thử cần xác minh quyền xóa, quyền sửa, thời hạn lưu và khả năng truy cập bản sao khi môi trường chính bị xâm phạm.

Một bản sao nằm ở vị trí khác nhưng dùng chung danh tính quản trị và quyền xóa có thể vẫn bị phá hủy cùng dữ liệu gốc. Hãy kiểm tra ranh giới quyền và quy trình khôi phục quyền truy cập, không chỉ vị trí lưu trữ.

## 6. Kiểm tra chất lượng của bản sao lưu

Một tác vụ backup báo trạng thái “thành công” mới chỉ là một tín hiệu. Cần có các kiểm tra độc lập để đánh giá bản sao lưu có đầy đủ và sử dụng được không.

### 6.1. Kiểm tra tính đầy đủ và metadata

Kiểm tra:

- Bản sao lưu được tạo đúng lịch và phạm vi.
- Kích thước, số lượng đối tượng hoặc số bản ghi nằm trong khoảng hợp lý.
- Manifest hoặc catalog liệt kê đủ các phần cần thiết.
- Chuỗi full/incremental/log không bị thiếu mắt xích.
- Dấu thời gian và điểm dữ liệu phản ánh đúng khoảng yêu cầu.
- Mã kiểm tra toàn vẹn hoặc checksum khớp khi đọc lại.
- Trạng thái sao chép sang vị trí độc lập được xác nhận.

Các kiểm tra về kích thước hoặc số lượng chỉ giúp phát hiện bất thường; chúng không chứng minh dữ liệu có ý nghĩa nghiệp vụ. Cần kết hợp với kiểm thử khôi phục và xác minh nội dung.

### 6.2. Kiểm tra khả năng đọc và giải mã

Định kỳ lấy một bản backup đại diện, kiểm tra cấu trúc, giải nén hoặc giải mã trong môi trường được kiểm soát. Xác minh công cụ và phiên bản cần thiết còn sẵn sàng, thông tin khóa có thể truy cập theo quy trình và dữ liệu không bị hỏng.

Nếu backup được mã hóa, kiểm thử phải bao gồm đường đi lấy khóa và giải mã. Chỉ kiểm tra tệp tồn tại hoặc checksum của ciphertext không chứng minh rằng tổ chức có thể sử dụng dữ liệu sau khi giải mã.

### 6.3. Kiểm tra tính nhất quán của ứng dụng

Với cơ sở dữ liệu, có thể dùng công cụ kiểm tra cấu trúc, tính nhất quán hoặc truy vấn xác minh các bất biến. Với dữ liệu nghiệp vụ, kiểm tra số lượng, quan hệ, tổng tiền, trạng thái và các khóa tham chiếu quan trọng.

Ví dụ, với hệ thống đơn hàng:

- Mỗi chi tiết đơn hàng tham chiếu đến một đơn hàng hợp lệ.
- Mỗi giao dịch thanh toán gắn với đúng đơn hàng.
- Tổng tiền được tính lại khớp với các thành phần theo quy tắc.
- Không có trạng thái thanh toán không hợp lệ hoặc bản ghi trùng ngoài quy định.
- Tệp đính kèm tham chiếu từ bản ghi có thể đọc được.

Các truy vấn và kiểm tra phải được thiết kế theo mô hình dữ liệu thực tế. Không nên dùng một phép đếm bản ghi duy nhất để kết luận toàn bộ dữ liệu hợp lệ.

### 6.4. Theo dõi thời gian và độ mới của backup

Theo dõi thời điểm của điểm phục hồi có thể dùng được gần nhất, không chỉ thời điểm công việc backup bắt đầu. Nếu backup thất bại hoặc log giao dịch bị đứt chuỗi, RPO thực tế có thể xấu đi dù lịch chạy vẫn hiển thị nhiều lần thực thi.

Một chỉ số hữu ích là tuổi của điểm phục hồi gần nhất đã được xác minh. Nếu tuổi này vượt ngưỡng chính sách, cần cảnh báo và xử lý trước khi xảy ra sự cố.

## 7. Kiểm thử khôi phục theo kịch bản

Kiểm thử khôi phục (restore test) là việc sử dụng bản sao lưu hoặc điểm phục hồi để dựng lại dữ liệu, thành phần hoặc dịch vụ, sau đó xác minh kết quả. Kiểm thử cần được thực hiện định kỳ và sau các thay đổi quan trọng đối với công nghệ, cấu hình, quy trình hoặc nhà cung cấp.

### 7.1. Khôi phục vào môi trường cô lập

Ưu tiên thực hiện diễn tập trong môi trường riêng, không ghi đè dữ liệu sản xuất và không gửi thông báo hoặc giao dịch thật ngoài ý muốn. Môi trường khôi phục cần có quyền truy cập, dung lượng, cấu hình và phiên bản đủ tương đồng để đánh giá quy trình.

Trước khi bắt đầu, xác định:

- Bản sao lưu hoặc điểm thời gian sẽ dùng.
- Môi trường đích và người có quyền thực hiện.
- Cách ngăn truy cập hoặc ghi dữ liệu ngoài phạm vi.
- Nguồn khóa và bí mật theo quy trình an toàn.
- Dữ liệu hoặc dịch vụ nào cần được giả lập.
- Tiêu chí dừng nếu phát hiện nguy cơ ảnh hưởng hệ thống khác.

### 7.2. Các bước kiểm thử khôi phục điển hình

1. Ghi nhận thời điểm bắt đầu và tuyên bố tình huống diễn tập.
2. Chọn bản backup hoặc điểm phục hồi phù hợp với mục tiêu RPO.
3. Xác minh manifest, chuỗi backup, quyền truy cập và khả năng giải mã.
4. Chuẩn bị hạ tầng, phiên bản ứng dụng, mạng và danh tính trong môi trường đích.
5. Khôi phục dữ liệu theo đúng thứ tự phụ thuộc.
6. Áp dụng log giao dịch hoặc các bước point-in-time recovery nếu có.
7. Khởi động các thành phần theo thứ tự và kiểm tra trạng thái sức khỏe.
8. Chạy kiểm tra tính toàn vẹn, đối soát dữ liệu và kiểm thử chức năng trọng yếu.
9. Xác minh tích hợp, hàng đợi, tác vụ nền và quyền truy cập.
10. Ghi nhận thời điểm đạt tiêu chí sử dụng, kết thúc đo RTO và tính RPO thực tế.
11. Thu thập bằng chứng, ghi sai lệch và dọn dẹp môi trường diễn tập theo quy trình.

Thứ tự thực tế phụ thuộc kiến trúc. Có hệ thống cần khôi phục danh tính và khóa trước khi truy cập dữ liệu; hệ thống khác cần dựng mạng và storage trước. Runbook phải thể hiện đúng các phụ thuộc đó.

### 7.3. Xác minh sau khi khôi phục

Không dừng ở trạng thái dịch vụ “healthy”. Cần kiểm tra:

- Người dùng hoặc tác nhân có thể hoàn thành các nhiệm vụ cốt lõi không?
- Dữ liệu ở điểm phục hồi có đúng và nhất quán không?
- Có bản ghi thiếu, trùng hoặc tham chiếu hỏng không?
- Tác vụ nền có tiếp tục từ vị trí đúng không?
- Hàng đợi có thông điệp cũ hoặc lặp cần xử lý không?
- Tích hợp có thể kết nối và xác thực đúng không?
- Log, giám sát và cảnh báo có hoạt động không?
- Các thao tác ghi mới có được lưu bền vững sau phục hồi không?

Nếu hệ thống khôi phục từ một điểm cũ, cần có quy trình xác định dữ liệu phát sinh sau điểm đó, dữ liệu có thể tái tạo và giao dịch cần đối soát thủ công. Không tự động phát lại tất cả yêu cầu nếu hành động có thể tạo tác dụng phụ trùng lặp.

## 8. Đo RPO và RTO trong cuộc diễn tập

Đo lường cần có mốc thời gian rõ và đồng hồ đồng bộ. Hãy lưu các mốc quan trọng để có thể tính lại kết quả sau diễn tập.

### 8.1. Đo RPO thực tế

RPO thực tế có thể tính bằng:

\[
\text{RPO thực tế} = \text{Mốc sự cố} - \text{Thời điểm dữ liệu phục hồi hợp lệ gần nhất}
\]

Ví dụ, sự cố được xác định bắt đầu lúc 14:00. Sau khôi phục, dữ liệu mới nhất có thể xác minh đầy đủ phản ánh thời điểm 13:50. RPO thực tế là 10 phút. Nếu mục tiêu là 15 phút, kết quả đạt trong kịch bản này.

Với point-in-time recovery, thời điểm dữ liệu phục hồi hợp lệ có thể được dựng từ backup nền và log giao dịch. Cần xác minh chuỗi log liên tục và tính nhất quán tại điểm đích, không chỉ dùng timestamp được ghi trong tên tệp.

### 8.2. Đo RTO thực tế

RTO thực tế được tính từ mốc bắt đầu sự cố đã thống nhất đến thời điểm dịch vụ đạt tiêu chí sử dụng:

\[
\text{RTO thực tế} = \text{Thời điểm dịch vụ phục hồi đạt tiêu chí} - \text{Mốc bắt đầu sự cố}
\]

Ví dụ, sự cố bắt đầu lúc 14:00; dữ liệu được nạp xong lúc 14:55; xác minh nghiệp vụ và tích hợp hoàn tất lúc 15:20; dịch vụ được cho phép nhận lưu lượng lúc 15:25. Nếu tiêu chí kết thúc là sẵn sàng nhận lưu lượng, RTO thực tế là 85 phút. Với mục tiêu 90 phút, diễn tập đạt RTO nhưng chỉ còn 5 phút dự phòng.

Nên ghi riêng thời gian phát hiện, quyết định, chuẩn bị hạ tầng, khôi phục dữ liệu, xác minh và mở dịch vụ. Phân rã này giúp biết phần nào chiếm nhiều thời gian và cần cải thiện.

### 8.3. Tính kết quả theo tiêu chí đã thống nhất

| Chỉ số | Mục tiêu giả định | Kết quả diễn tập | Đánh giá |
|---|---:|---:|---|
| RPO | Không quá 15 phút | 10 phút | Đạt |
| RTO | Không quá 90 phút | 85 phút | Đạt, dự phòng 5 phút |
| Tính toàn vẹn | Không có sai lệch trọng yếu | Không phát hiện sai lệch trong phạm vi đã kiểm tra | Đạt trong phạm vi kiểm thử |
| Luồng nghiệp vụ chính | Hoàn tất được hành trình tạo đơn và tra cứu đơn | Hoàn tất sau khôi phục | Đạt |

Không nên báo cáo “đạt hoàn toàn” nếu chỉ kiểm tra một phần dữ liệu hoặc một số luồng. Hãy ghi phạm vi kiểm chứng và các giới hạn để người phê duyệt hiểu chính xác bằng chứng.

## 9. Các kịch bản kiểm thử khôi phục cần cân nhắc

Một cuộc diễn tập chỉ kiểm tra khôi phục từ lỗi máy chủ có thể chưa đại diện cho các tình huống khác. Nên xây dựng danh mục kịch bản theo rủi ro.

### 9.1. Khôi phục một phần dữ liệu bị xóa nhầm

Mô phỏng việc một bảng, tệp hoặc nhóm bản ghi bị xóa ngoài ý muốn. Kiểm tra khả năng khôi phục phạm vi cần thiết mà không ghi đè dữ liệu hợp lệ phát sinh sau đó. Xác minh quan hệ giữa bản ghi được phục hồi và các dữ liệu liên quan.

### 9.2. Khôi phục toàn bộ cơ sở dữ liệu

Dựng lại cơ sở dữ liệu từ backup và log cần thiết. Kiểm tra schema, migration, ràng buộc, dữ liệu và các truy vấn trọng yếu. Xác minh ứng dụng tương thích với phiên bản dữ liệu đã phục hồi.

### 9.3. Khôi phục point-in-time

Chọn một thời điểm trước thao tác sai hoặc trước khi dữ liệu bị hỏng. Dựng dữ liệu đến thời điểm đó và xác minh các thay đổi trước mốc được giữ lại, các thay đổi sau mốc không xuất hiện ngoài dự kiến. Kiểm tra chuỗi log và tính nhất quán của điểm đích.

### 9.4. Khôi phục sau lỗi vùng hoặc hạ tầng

Mô phỏng mất khả năng truy cập một vùng, tài khoản hoặc hệ thống lưu trữ theo phạm vi diễn tập được phê duyệt. Kiểm tra khả năng truy cập bản backup độc lập, quyền quản trị khẩn cấp, mạng, DNS và thứ tự dựng lại dịch vụ.

### 9.5. Khôi phục sau sự cố bảo mật hoặc mã độc

Không mặc định bản backup mới nhất là bản sạch. Khi sự cố có thể tồn tại trong hệ thống một thời gian trước khi được phát hiện, cần xác định điểm phục hồi trước thời điểm xâm nhập ước tính, kiểm tra nguồn gốc và quét dữ liệu theo quy trình bảo mật. Xác minh bản backup bất biến hoặc ngoại tuyến không bị thay đổi và quyền truy cập khôi phục còn an toàn.

### 9.6. Khôi phục khi thiếu khóa hoặc phụ thuộc

Diễn tập tình huống khóa mã hóa, chứng thư, tài khoản dịch vụ hoặc nhà cung cấp phụ thuộc không sẵn sàng theo cách an toàn. Mục tiêu là xác minh quy trình lấy lại quyền và phụ thuộc cần thiết, đồng thời phát hiện điểm đơn lẻ có thể khiến backup không thể sử dụng.

### 9.7. Khôi phục thông điệp và tác vụ nền

Kiểm tra thông điệp đang chờ, vị trí consumer, outbox/inbox và tác vụ định kỳ. Xác minh không mất thông điệp quan trọng, không xử lý trùng gây tác dụng phụ và các tác vụ tiếp tục từ vị trí phù hợp.

### 9.8. Bảng chọn kịch bản

| Kịch bản | Câu hỏi chính | Bằng chứng quan trọng |
|---|---|---|
| Xóa nhầm một phần dữ liệu | Có thể phục hồi phạm vi cần thiết mà không làm hỏng dữ liệu khác không? | Bản ghi trước/sau, quan hệ và đối soát |
| Hỏng toàn bộ cơ sở dữ liệu | Có thể dựng lại dữ liệu và cho ứng dụng hoạt động không? | Log phục hồi, kiểm tra schema, truy vấn nghiệp vụ |
| Point-in-time recovery | Có thể quay về đúng thời điểm trước sự cố không? | Mốc thời gian, chuỗi log, dữ liệu trước/sau mốc |
| Mất vùng triển khai | Bản sao độc lập và hạ tầng thay thế có sẵn không? | Nhật ký dựng môi trường, quyền truy cập, RTO |
| Sự cố mã độc | Có thể chọn điểm sạch và khôi phục an toàn không? | Nguồn gốc backup, kết quả quét, kiểm soát quyền |
| Thiếu khóa hoặc dịch vụ phụ thuộc | Có thể truy cập khóa và khôi phục các phụ thuộc không? | Nhật ký truy cập, kiểm tra giải mã, kiểm thử tích hợp |

## 10. Kiểm tra runbook và khả năng vận hành

Runbook là hướng dẫn vận hành cho các bước xử lý cụ thể trong một tình huống. Một kiến trúc có backup tốt vẫn có thể không đạt RTO nếu người thực hiện không biết bắt đầu ở đâu hoặc phải chờ quyền truy cập.

Runbook phục hồi nên có:

- Điều kiện kích hoạt và người có quyền tuyên bố sự cố.
- Danh sách liên hệ và vai trò trong cuộc diễn tập hoặc sự cố thật.
- Nguồn backup, catalog, khóa và hướng dẫn truy cập khẩn cấp.
- Thứ tự phục hồi các thành phần và phụ thuộc.
- Lệnh hoặc thao tác cần thực hiện cùng kết quả mong đợi.
- Điều kiện dừng, phương án quay lui và cách xử lý lỗi.
- Kiểm tra tính toàn vẹn, chức năng và tiêu chí cho phép mở dịch vụ.
- Cách ghi nhận thời gian, quyết định, bằng chứng và ngoại lệ.
- Quy trình thông báo, đối soát và xử lý tồn đọng sau phục hồi.

### 10.1. Kiểm tra quyền và năng lực thực hiện

Không nên chỉ để một cá nhân duy nhất biết cách khôi phục. Diễn tập cần kiểm tra người được phân công có quyền, công cụ và kiến thức cần thiết. Khi có thể, hãy luân phiên người thực hiện để phát hiện hướng dẫn phụ thuộc vào kiến thức ngầm.

### 10.2. Kiểm tra quy trình phê duyệt

Một số thao tác như truy cập khóa khẩn cấp, chuyển vùng hoặc mở lại lưu lượng có thể cần phê duyệt. Cần xác minh người phê duyệt có thể liên hệ trong thời gian mục tiêu và quy trình không tạo ra điểm chờ kéo dài ngoài dự kiến.

### 10.3. Đo thời gian theo từng giai đoạn

Ghi thời gian của các giai đoạn như phát hiện, tuyên bố, chuẩn bị, khôi phục dữ liệu, xác minh, mở dịch vụ và xử lý tồn đọng. Nếu phần xác minh chiếm phần lớn thời gian, có thể cần tự động hóa kiểm tra tính toàn vẹn hoặc chuẩn bị bộ truy vấn xác nhận. Nếu thời gian chờ phê duyệt quá lâu, cần xem xét cơ chế phân quyền khẩn cấp.

## 11. Thiết kế test case cho backup và restore

Mỗi test case cần có mục tiêu, điều kiện, thao tác, kết quả mong đợi và bằng chứng. Có thể tổ chức một số trường hợp mẫu như sau.

### 11.1. Test case kiểm tra backup

| Trường | Nội dung minh họa |
|---|---|
| Mã | `BKP-001` |
| Mục tiêu | Xác minh backup dữ liệu đơn hàng được tạo đúng lịch và có thể đọc |
| Tiền điều kiện | Môi trường kiểm thử có dữ liệu đại diện; lịch backup và quyền truy cập đã cấu hình |
| Bước 1 | Kích hoạt hoặc chờ lịch backup theo quy trình |
| Bước 2 | Kiểm tra trạng thái job, manifest và phạm vi dữ liệu |
| Bước 3 | Đọc lại bản backup, kiểm tra checksum và metadata |
| Bước 4 | Xác minh chuỗi backup/log cần thiết không bị thiếu |
| Kết quả mong đợi | Backup tồn tại, đủ phạm vi, metadata hợp lệ và có thể đọc; điểm phục hồi đáp ứng chính sách |
| Bằng chứng | ID job, timestamp, checksum, manifest và báo cáo kiểm tra |

### 11.2. Test case kiểm tra khôi phục

| Trường | Nội dung minh họa |
|---|---|
| Mã | `RST-001` |
| Mục tiêu | Khôi phục dữ liệu đơn hàng trong môi trường cô lập và xác minh RPO/RTO |
| Tiền điều kiện | Có backup hợp lệ; môi trường đích sẵn sàng; quyền và khóa được cấp theo quy trình |
| Bước 1 | Ghi thời điểm bắt đầu diễn tập và chọn điểm phục hồi |
| Bước 2 | Khôi phục dữ liệu theo runbook |
| Bước 3 | Khởi động dịch vụ và xác minh sức khỏe |
| Bước 4 | Đối soát bản ghi đơn hàng, giao dịch và các quan hệ quan trọng |
| Bước 5 | Chạy các luồng nghiệp vụ cốt lõi trên môi trường khôi phục |
| Bước 6 | Ghi thời điểm dịch vụ đạt tiêu chí sử dụng và tính RPO/RTO |
| Kết quả mong đợi | Dữ liệu hợp lệ; chức năng trọng yếu hoạt động; RPO/RTO nằm trong mục tiêu đã phê duyệt |
| Bằng chứng | Nhật ký thời gian, log phục hồi, kết quả đối soát, báo cáo test và quyết định nghiệm thu |

Các bước và ngưỡng phải được điều chỉnh theo hệ thống. Test case không nên chứa bí mật truy cập hoặc thông tin nhạy cảm; chỉ tham chiếu đến kho lưu trữ được kiểm soát.

## 12. Đánh giá kết quả và xử lý sai lệch

Sau mỗi lần kiểm thử, so sánh kết quả với mục tiêu đã phê duyệt và phân loại sai lệch.

Các dạng sai lệch thường gặp:

- **RPO không đạt:** backup quá thưa, log không đầy đủ, replication hoặc catalog bị gián đoạn.
- **RTO không đạt:** dung lượng khôi phục lớn, thiếu tự động hóa, thiếu quyền, phụ thuộc không sẵn sàng hoặc xác minh thủ công kéo dài.
- **Dữ liệu không nhất quán:** các thành phần được sao lưu ở thời điểm khác nhau, chuỗi log thiếu hoặc quy trình đối soát chưa đầy đủ.
- **Không thể giải mã:** khóa hoặc quy trình truy cập khóa không khả dụng.
- **Không thể khởi động ứng dụng:** thiếu cấu hình, artifact, chứng thư, schema hoặc phiên bản tương thích.
- **Không thể vận hành sau khôi phục:** giám sát, hàng đợi, lịch chạy, quyền hoặc tích hợp chưa được bật lại đúng.

Với mỗi sai lệch, ghi nguyên nhân, ảnh hưởng, biện pháp khắc phục, người chịu trách nhiệm và thời hạn. Nếu mục tiêu không thể đạt bằng kiến trúc hiện tại, cần đưa ra phương án và xin quyết định chấp nhận rủi ro từ người có thẩm quyền; không tự hạ mục tiêu để làm báo cáo đạt.

### 12.1. Theo dõi xu hướng, không chỉ một lần diễn tập

Một lần khôi phục đạt mục tiêu không bảo đảm các lần sau cũng đạt. Theo dõi xu hướng:

- Tuổi của điểm backup hợp lệ gần nhất.
- Tỷ lệ job backup thành công và tỷ lệ bản backup đã được xác minh.
- Thời gian khôi phục dữ liệu theo dung lượng.
- Thời gian từ lúc bắt đầu sự cố đến lúc dịch vụ sẵn sàng.
- Tỷ lệ test restore thành công.
- Số lỗi hoặc bước thủ công phát hiện trong diễn tập.
- Số rủi ro và hành động khắc phục còn mở.

Đánh giá lại khi dung lượng dữ liệu, kiến trúc, nhà cung cấp, chính sách lưu trữ hoặc mục tiêu nghiệp vụ thay đổi.

## 13. Những sai lầm thường gặp

### 13.1. Chỉ kiểm tra job backup có trạng thái thành công

Trạng thái job không chứng minh dữ liệu có thể đọc, giải mã và khôi phục. Cần thực hiện restore test và kiểm tra nội dung theo phạm vi rủi ro.

### 13.2. Coi replication là backup

Replication có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu bị mã hóa bởi mã độc. Cần có điểm phục hồi độc lập và lịch sử phù hợp.

### 13.3. Đo RTO đến lúc máy chủ khởi động

Máy chủ chạy không có nghĩa người dùng hoàn thành được nhiệm vụ. Hãy định nghĩa tiêu chí kết thúc gồm dữ liệu, tích hợp, chức năng và khả năng nhận lưu lượng.

### 13.4. Không xác định mốc tính RPO/RTO

Nếu mỗi nhóm chọn một mốc bắt đầu hoặc kết thúc khác nhau, kết quả không thể so sánh. Thống nhất cách đo và ghi đầy đủ các mốc thời gian.

### 13.5. Chỉ khôi phục cơ sở dữ liệu

Ứng dụng có thể cần tệp, cấu hình, khóa, danh tính, hàng đợi và dịch vụ phụ thuộc. Hãy kiểm tra toàn bộ phạm vi cần thiết để khôi phục quy trình nghiệp vụ.

### 13.6. Dùng bản backup mới nhất mà không xét sự cố bảo mật

Nếu mã độc hoặc dữ liệu hỏng đã tồn tại trước khi được phát hiện, backup gần nhất có thể không sạch. Cần xác định điểm phục hồi đáng tin cậy, kiểm tra nguồn gốc và làm theo quy trình bảo mật.

### 13.7. Chỉ một người biết quy trình khôi phục

Quy trình phụ thuộc kiến thức cá nhân có thể thất bại khi người đó không sẵn sàng. Hãy tài liệu hóa, phân quyền và diễn tập với người thay thế.

### 13.8. Không diễn tập đủ các phụ thuộc

Khôi phục dữ liệu mà không kiểm tra khóa, chứng thư, DNS, hàng đợi hoặc tích hợp có thể tạo ra một hệ thống chỉ hoạt động một phần. Phải xác định và kiểm tra thứ tự phụ thuộc.

## 14. Danh sách rà soát kiểm thử sao lưu và khôi phục

Trước khi kết thúc một kế hoạch hoặc cuộc diễn tập, hãy kiểm tra:

- [ ] Dịch vụ, dữ liệu và quy trình nghiệp vụ cần bảo vệ đã được xác định.
- [ ] RPO và RTO có định nghĩa, phạm vi và mốc đo rõ ràng.
- [ ] Các mục tiêu được bên có thẩm quyền nghiệp vụ và kỹ thuật thống nhất.
- [ ] Phạm vi backup gồm dữ liệu, cấu hình, khóa, artifact và phụ thuộc cần thiết.
- [ ] Backup được bảo vệ, có kiểm tra toàn vẹn và có bản sao độc lập phù hợp.
- [ ] Chuỗi full, incremental, differential hoặc log cần thiết được xác minh.
- [ ] Có kiểm tra khả năng đọc, giải mã và khôi phục thực tế.
- [ ] Restore được diễn tập trong môi trường cô lập và an toàn.
- [ ] Dữ liệu sau khôi phục được kiểm tra tính toàn vẹn và đối soát nghiệp vụ.
- [ ] Các dịch vụ, hàng đợi, tác vụ nền và tích hợp quan trọng hoạt động đúng.
- [ ] RPO/RTO thực tế được tính từ các mốc đã thống nhất.
- [ ] Sai lệch, rủi ro còn lại, người phụ trách và thời hạn khắc phục được ghi nhận.
- [ ] Runbook, quyền truy cập và năng lực người thực hiện đã được kiểm tra.
- [ ] Có lịch diễn tập lại và điều kiện kích hoạt đánh giá khi hệ thống thay đổi.

## 15. Kết luận

Kiểm thử sao lưu và khôi phục phải chứng minh rằng tổ chức có thể lấy lại dữ liệu đáng tin cậy và đưa dịch vụ trở lại mức sử dụng đã xác định trong giới hạn RPO/RTO. Backup, snapshot, replication và HA có vai trò khác nhau; không cơ chế riêng lẻ nào bảo đảm toàn bộ khả năng phục hồi.

Một kế hoạch kiểm thử tốt xác định phạm vi dữ liệu và phụ thuộc, kiểm tra tính toàn vẹn và khả năng giải mã, diễn tập khôi phục trong môi trường kiểm soát, xác minh hành vi nghiệp vụ và đo thời gian thực tế. Kết quả cần được so sánh với mục tiêu đã phê duyệt, ghi rõ giới hạn và chuyển sai lệch thành hành động cải thiện. Chỉ khi khôi phục được kiểm chứng định kỳ, tổ chức mới có bằng chứng đáng tin cậy về khả năng tiếp tục hoạt động khi sự cố xảy ra.
