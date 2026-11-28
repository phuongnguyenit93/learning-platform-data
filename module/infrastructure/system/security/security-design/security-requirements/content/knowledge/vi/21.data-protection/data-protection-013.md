# Data retention

## 1. Lưu giữ dữ liệu là một yêu cầu bảo mật

Data retention là việc xác định dữ liệu được giữ để làm gì, trong bao lâu, ở trạng thái nào, ai được sử dụng và phải xử lý thế nào khi không còn căn cứ lưu giữ.

Một yêu cầu lưu giữ đầy đủ không chỉ có số ngày. Nó phải chỉ ra loại dữ liệu, sự kiện bắt đầu tính thời gian, các bản sao liên quan, hành động khi đến hạn và bằng chứng thực thi.

Ví dụ, “giữ hồ sơ hỗ trợ 90 ngày” còn thiếu nhiều thông tin:

- 90 ngày tính từ khi tạo, lần sửa cuối hay khi đóng hồ sơ?
- Nội dung trao đổi và tệp đính kèm có cùng thời hạn không?
- Bản sao trong kho tìm kiếm, tệp xuất và backup được xử lý thế nào?
- Đến hạn thì chặn đọc ngay hay chỉ chờ một tác vụ xóa?
- Nếu có lệnh bảo toàn chứng cứ, ai được đặt và gỡ lệnh?
- Làm sao chứng minh không xóa sớm và không giữ quá hạn?

Trong thiết kế yêu cầu bảo mật, lưu giữ giúp cân bằng hai nhóm rủi ro. Giữ quá lâu làm tăng dữ liệu có thể bị lộ, bị sử dụng sai mục đích hoặc bị khôi phục ngoài dự kiến. Xóa quá sớm có thể làm mất bằng chứng, phá khả năng phục hồi hoặc làm gián đoạn nghiệp vụ có căn cứ.

Mục tiêu là chuyển những nhu cầu đó thành điều kiện có thể đo và kiểm chứng trong suốt vòng đời dữ liệu.

## 2. Phân biệt retention với các cơ chế liên quan

| Khái niệm | Ý nghĩa | Điều không được mặc định |
| --- | --- | --- |
| Retention policy | Quy tắc giữ và xử lý dữ liệu theo loại, mục đích và điều kiện | Không tự được thực thi chỉ vì đã ghi trong tài liệu |
| TTL | Thời hạn mà một cơ chế gán cho bản ghi hoặc đối tượng | Có thể chỉ điều khiển hết hạn truy cập hoặc lịch xử lý; chưa chứng minh xóa mọi bản sao |
| Cache expiry | Hết thời gian tái sử dụng một bản cache | Không quyết định thời hạn dữ liệu nguồn |
| Archive | Chuyển dữ liệu sang trạng thái hoặc lớp lưu trữ khác | Dữ liệu vẫn tồn tại và vẫn cần quyền truy cập, hạn lưu, xử lý cuối vòng đời |
| Soft delete | Đánh dấu dữ liệu không còn xuất hiện trong luồng thông thường | Dữ liệu có thể còn nguyên và có thể được khôi phục |
| Logical deletion | Loại dữ liệu khỏi khả năng truy cập theo một mô hình logic | Không tự chứng minh không thể khôi phục từ phương tiện hoặc bản sao khác |
| Media sanitization | Xử lý phương tiện lưu trữ nhằm hạn chế khả năng khôi phục dữ liệu theo mức bảo đảm đã chọn | Không thể suy ra chỉ từ việc một API xóa trả thành công |
| Backup retention | Quy tắc giữ và hủy các bản sao phục hồi | Không cho phép biến backup thành kho lưu lịch sử vô hạn |
| Anonymization | Xử lý nhằm hạn chế khả năng nhận diện trong ngữ cảnh được đánh giá | Bỏ tên hoặc thay bằng token chưa đủ để kết luận đã ẩn danh |

Cần viết rõ mức bảo đảm của hành động cuối vòng đời. NIST mô tả media sanitization theo khả năng làm việc truy cập dữ liệu trên phương tiện trở nên không khả thi với một mức nỗ lực nhất định; đó là một mục tiêu khác với việc đơn thuần ẩn một bản ghi khỏi giao diện. [NIST SP 800-88 Rev. 2](https://csrc.nist.gov/pubs/sp/800/88/r2/final).

### Một dữ liệu có thể đi qua nhiều trạng thái

~~~text
Đang phục vụ nghiệp vụ
    -> giữ hạn chế hoặc lưu trữ
    -> đến hạn xử lý
    -> bị chặn khỏi sử dụng thông thường
    -> đang xóa ở các nơi liên quan
    -> hoàn tất trong phạm vi đã xác minh
~~~

Có thể cần trạng thái bảo toàn dữ liệu hoặc chờ xử lý lỗi. Mỗi trạng thái phải có quyền truy cập và điều kiện chuyển rõ ràng. “Đã archive” hoặc “đã soft delete” không nên là trạng thái cuối nếu chính sách yêu cầu xóa.

## 3. Từ mục tiêu và mô hình đe dọa đến yêu cầu lưu giữ

### 3.1. Những tài sản cần bảo vệ

Ngoài nội dung nghiệp vụ, cần xem xét:

- Dữ liệu nhận diện, nội dung trao đổi và tệp đính kèm.
- Nhật ký truy cập, audit, trace và dữ liệu debug.
- Đối tượng trong kho tệp, phiên bản cũ và bản sao ở vùng khác.
- Chỉ mục tìm kiếm, cache, báo cáo, tệp xuất và dữ liệu dẫn xuất.
- Hàng đợi, bản ghi retry và dead-letter queue.
- Snapshot, bản sao phục hồi và dữ liệu đã khôi phục vào môi trường tạm.
- Chính sách retention, mốc thời gian và lệnh bảo toàn hoặc xóa.
- Khóa mật mã nếu khả năng truy cập cuối vòng đời phụ thuộc vào khóa.

Các trường phục vụ quyết định retention cũng là dữ liệu cần bảo vệ tính toàn vẹn. Nếu người dùng có thể tùy ý sửa mốc bắt đầu, họ có thể kéo dài việc giữ dữ liệu hoặc làm dữ liệu bị xóa sớm.

### 3.2. Bảng rủi ro minh họa

| Đe dọa hoặc sai sót | Hậu quả | Kết quả cần đặc tả |
| --- | --- | --- |
| Thu thập nhiều nhưng không có lịch xử lý | Kho dữ liệu nhạy cảm tăng mãi | Mỗi nhóm dữ liệu có mục đích, owner và thời hạn được phê duyệt |
| Tính hạn từ lần đọc hoặc cập nhật kỹ thuật | Dữ liệu cũ không bao giờ đến hạn | Mốc nghiệp vụ đáng tin cậy và không bị reset ngoài chính sách |
| Tác vụ xóa chỉ xử lý bảng chính | Dữ liệu vẫn đọc được qua tìm kiếm, export hoặc cache | Phạm vi bao gồm các bản sao và đường truy cập đã kiểm kê |
| Người không có quyền rút ngắn hạn audit | Mất bằng chứng điều tra | Thay đổi chính sách và xóa ngoại lệ có phân quyền, audit phù hợp |
| Giữ mọi thứ để phòng tranh chấp | Giữ dữ liệu không giới hạn | Bảo toàn có phạm vi, căn cứ, owner và rà soát |
| Khôi phục backup cũ | Dữ liệu đã hết hạn hoạt động lại | Kiểm tra lại retention trước khi mở dữ liệu cho sử dụng |
| Xóa nhầm khi thiếu metadata | Mất dữ liệu cần giữ | Chính sách xử lý trạng thái không xác định, cảnh báo và hạn giải quyết |
| Tác vụ dọn thất bại nhưng vẫn báo thành công | Không biết dữ liệu đang bị giữ quá hạn | Báo trạng thái theo từng nơi, cảnh báo và đối soát |
| Nhà cung cấp giữ thêm bản sao | Cam kết xóa không phản ánh thực tế | Phạm vi trách nhiệm và bằng chứng từ bên xử lý được xác định |

Yêu cầu tốt nối được rủi ro với một hành vi, một điểm thực thi và một phép đo. “Có job cleanup” chỉ là mô tả một phần triển khai.

## 4. Xác định căn cứ, mục đích và người chịu trách nhiệm

### 4.1. Không chọn số ngày theo cảm tính

Nguồn của yêu cầu lưu giữ có thể gồm nhu cầu nghiệp vụ đã được duyệt, yêu cầu điều tra, mục tiêu phục hồi và các nghĩa vụ được nhóm có thẩm quyền xác định.

Đối với từng nhóm dữ liệu, cần lưu được:

1. Dữ liệu được giữ cho mục đích nào.
2. Ai chịu trách nhiệm về mục đích và thời hạn.
3. Nguồn yêu cầu và phiên bản áp dụng.
4. Điều kiện bắt đầu, kết thúc hoặc thay đổi thời hạn.
5. Hành động khi hết mục đích hoặc đến hạn.
6. Cách xử lý ngoại lệ và mâu thuẫn.

Bài học này dùng các thời hạn giả định để minh họa phương pháp đặc tả; không xác định thời hạn pháp lý cho một loại hồ sơ cụ thể.

### 4.2. Phân biệt thời hạn tối thiểu và giới hạn tối đa

Một yêu cầu có thể quy định không xóa trước thời điểm nhất định. Yêu cầu khác có thể giới hạn việc tiếp tục lưu sau một thời điểm.

Không dùng quy tắc “chọn thời hạn dài nhất” cho mọi tình huống. Cách đó có thể đáp ứng một yêu cầu giữ tối thiểu nhưng vi phạm một giới hạn lưu tối đa đang áp dụng.

Nếu các yêu cầu thực sự áp dụng cho cùng dữ liệu và cùng mục đích không có khoảng thời gian tương thích, cần chuyển cho owner và nhóm có thẩm quyền giải quyết. Hệ thống không được âm thầm chọn một số ngày hoặc tự bỏ qua một nguồn yêu cầu.

Trước hết cũng cần kiểm tra có thể tách nội dung, trường dữ liệu hoặc mục đích hay không. Một bằng chứng giao dịch cần giữ không nhất thiết đòi hỏi giữ toàn bộ nội dung trao đổi và tệp đính kèm cùng thời gian.

### 4.3. Thay đổi mục đích không phải thao tác reset vô điều kiện

Nếu dữ liệu cần được giữ cho một mục đích khác, phải xác định mục đích mới có căn cứ gì, phạm vi nào thực sự cần và quyền truy cập nào được phép.

Không tự gia hạn mọi bản ghi chỉ vì một bộ phận có thể muốn dùng dữ liệu trong tương lai. Việc thay chính sách phải tạo ra quyết định có thể truy vết, không chỉ một thay đổi cấu hình không có người chịu trách nhiệm.

## 5. Kiểm kê dữ liệu theo dòng chảy, không chỉ theo bảng chính

### 5.1. Mỗi bản sao cần có một quy tắc hoặc quan hệ kế thừa

Một bản ghi có thể xuất hiện trong nhiều nơi:

~~~mermaid
flowchart LR
    A["Nguồn tiếp nhận"] --> B["Kho nghiệp vụ"]
    B --> C["Replica và cache"]
    B --> D["Sự kiện và hàng đợi"]
    D --> E["Kho phân tích và tìm kiếm"]
    B --> F["Tệp xuất được quản lý"]
    B --> G["Snapshot và backup"]
    G --> H["Vùng phục hồi cách ly"]
    H --> I["Đối soát retention trước khi sử dụng"]
~~~

Sơ đồ giúp xác định các điểm phải thực thi. Không được suy rằng xóa ở B sẽ tự xóa ở C, D, E, F và G.

Bảng kiểm kê nên ghi loại dữ liệu, nơi lưu, owner, đường tạo bản sao, mục đích, thời hạn, cơ chế xử lý, quyền truy cập và cách lấy bằng chứng.

Với bản sao phục vụ cùng mục đích, có thể cần kế thừa hạn của nguồn. Với dữ liệu có mục đích khác, phải có quyết định riêng. Chẳng hạn, audit tối thiểu phục vụ điều tra có thể có hạn khác nội dung hồ sơ mà nó ghi nhận, nhưng không vì vậy được sao chép toàn bộ hồ sơ vào audit.

### 5.2. Dữ liệu dẫn xuất không tự nằm ngoài phạm vi

Báo cáo, bảng tổng hợp, embedding hoặc tập dữ liệu được thay định danh vẫn có thể chứa nội dung nhạy cảm hoặc hỗ trợ liên kết.

Cần xác định dữ liệu dẫn xuất có thể nối ngược với nguồn hay không, còn giữ chi tiết nào, và có phải cập nhật hoặc xóa khi nguồn hết hạn không.

Nếu muốn tiếp tục giữ một tập tổng hợp vì đã đáp ứng mục tiêu hạn chế nhận diện, cần có tiêu chí đánh giá và bằng chứng tương ứng. Không coi tên bảng “anonymous” là kết quả kiểm chứng.

### 5.3. Export và bên xử lý khác

Tệp xuất cho người dùng hoặc đối tác có thể rời khỏi ranh giới mà hệ thống kiểm soát trực tiếp. Yêu cầu phải ghi rõ khả năng thực thi và giới hạn bằng chứng.

Với tệp xuất còn do hệ thống quản lý, có thể yêu cầu hạn truy cập, hạn lưu đối tượng, kiểm soát tải và xử lý phiên bản cũ. Hết hạn liên kết tải không tự chứng minh tệp đã bị xóa.

Với bản đã được tải về một môi trường khác, cần xác định trách nhiệm, cơ chế yêu cầu xử lý và bằng chứng khả dụng. Không báo “đã xóa mọi bản sao” chỉ dựa vào việc xóa liên kết ở hệ thống nguồn.

## 6. Đặc tả thời gian sao cho có thể thực thi

### 6.1. Chọn mốc bắt đầu đáng tin cậy

Ví dụ các mốc khác nhau:

| Nhóm dữ liệu | Mốc có thể dùng theo chính sách | Rủi ro nếu chọn sai |
| --- | --- | --- |
| Hồ sơ đã kết thúc xử lý | Sự kiện đóng hợp lệ | Tính từ lúc tạo có thể xóa khi vẫn đang xử lý |
| Tệp import tạm | Lúc nhận hoặc hoàn tất tác vụ theo hợp đồng | Retry có thể làm tệp được giữ mãi |
| Sự kiện audit | Thời điểm sự kiện hoặc tiếp nhận theo quy tắc đã chọn | Sự kiện đến muộn có thể làm tính hạn sai |
| Liên kết chia sẻ | Thời điểm cấp liên kết | Một lần đọc không nên tự gia hạn ngoài chính sách |
| Backup | Thời điểm bản backup được tạo theo định nghĩa cụ thể | Nhầm tuổi bản backup với tuổi từng bản ghi bên trong |

Không dùng updated_at của mọi thay đổi làm mốc nếu tác vụ bảo trì, lập chỉ mục hoặc sửa metadata cũng cập nhật trường đó.

Mốc nghiệp vụ phải có nguồn có thẩm quyền, được bảo vệ khỏi sửa tùy ý và có lịch sử thay đổi cần thiết.

### 6.2. Phân biệt ba thời điểm

Có thể định nghĩa:

~~~text
T_anchor: mốc nghiệp vụ đã xác định
T_eligible: thời điểm dữ liệu đến hạn theo chính sách
T_deadline: hạn chót hoàn tất hành động đã cam kết

T_eligible = T_anchor + retention_duration
T_deadline = T_eligible + maximum_processing_delay
~~~

Công thức chỉ là ví dụ cho chính sách theo khoảng thời gian cố định. Chính sách theo tháng lịch, kết thúc năm hoặc điều kiện nghiệp vụ phải có cách tính tương ứng.

Khoảng từ T_eligible tới T_deadline là thời gian xử lý được chấp thuận, không phải một ngoại lệ vô hình. Phải nói rõ dữ liệu được đọc hoặc sử dụng thế nào trong khoảng này.

Nếu muốn chặn truy cập tại T_eligible nhưng cho phép dọn dữ liệu trong 24 giờ tiếp theo, cần hai yêu cầu riêng. Không dùng một job chạy mỗi ngày để cam kết mọi API chặn đúng thời điểm nếu API không kiểm tra hạn.

### 6.3. Đơn vị, đồng hồ và ranh giới

Đặc tả cần chốt:

- “Ngày” là chu kỳ 24 giờ hay ngày lịch theo múi giờ nào.
- Timestamp được lưu và so sánh theo chuẩn nào.
- Tại đúng mốc hết hạn, điều kiện dùng lớn hơn hay lớn hơn hoặc bằng.
- Cách xử lý timestamp tương lai, thiếu, không hợp lệ và dữ liệu đến muộn.
- Nguồn đồng hồ và giới hạn sai lệch được chấp thuận.
- Lịch batch, retry và thời gian đối soát có nằm trong độ trễ tối đa không.

Nếu cam kết độ chính xác một phút nhưng lịch quét và sai lệch đồng hồ lớn hơn một phút, thiết kế chưa chứng minh đáp ứng.

### 6.4. Dữ liệu thiếu mốc hoặc thiếu chính sách

Không được mặc định xóa ngay, cũng không được âm thầm giữ mãi.

Một chính sách có thể yêu cầu hạn chế truy cập, đưa bản ghi vào hàng xử lý ngoại lệ, cảnh báo owner và giải quyết trong một hạn riêng. Việc quyết định cuối cùng phải dựa vào nguồn thông tin có thẩm quyền.

Trong giai đoạn nhập dữ liệu cũ, cần có kế hoạch xác định mốc và phạm vi không chắc chắn. Không lấy ngày migrate làm ngày tạo mới nếu việc đó kéo dài retention trái chính sách.

## 7. Bảo toàn dữ liệu và những ngoại lệ có kiểm soát

### 7.1. Tách trạng thái bảo toàn khỏi quyền sử dụng

Một lệnh bảo toàn dữ liệu, thường được gọi là hold, tạm ngăn hành động hủy trong một phạm vi đã xác định. Hold có thể phục vụ một quá trình điều tra hoặc yêu cầu do bộ phận có thẩm quyền ban hành.

Hold không tự cấp quyền cho mọi người đọc dữ liệu và không tự cho phép dùng dữ liệu vào mục đích mới. Quyền truy cập trong thời gian bảo toàn vẫn phải được kiểm soát.

Một bản ghi hold cần có:

- Mã tham chiếu, nguồn yêu cầu và người có thẩm quyền.
- Phạm vi dữ liệu, tenant, phiên bản hoặc điều kiện chọn.
- Thời điểm bắt đầu hiệu lực.
- Owner, lịch rà soát và điều kiện kết thúc.
- Thông tin hạn chế truy cập, nếu áp dụng.
- Audit đặt, sửa và gỡ hold.

Không dùng cờ hold toàn hệ thống để giải quyết mọi ngoại lệ nhỏ. Phạm vi càng rộng càng cần chứng minh lý do và tác động.

### 7.2. Cuộc đua giữa đặt hold và xóa

Một danh sách ứng viên được tạo lúc 01:00 có thể không còn đúng lúc 01:10 nếu hold được đặt trong khoảng đó.

Trước hành động không thể đảo, hệ thống phải kiểm tra điều kiện hiện hành theo mô hình nhất quán đã chọn. Kiểm tra hold một lần ở đầu batch rồi xóa không giới hạn về sau có thể không đáp ứng chính sách.

Cần xác định mốc cam kết của lệnh hold và điểm quyết định của lệnh xóa. Nếu hủy đã hoàn tất trước khi hold có hiệu lực, hệ thống không được báo đã bảo toàn được dữ liệu đó; phải phản ánh chính xác phần không còn khả dụng.

### 7.3. Gỡ hold không tự bắt đầu một vòng lưu giữ mới

Nếu hạn gốc đã qua, sau khi hold được gỡ, dữ liệu cần quay lại cơ chế đánh giá và xử lý theo chính sách đã phê duyệt.

Không tự tính thêm toàn bộ thời hạn từ ngày gỡ hold, trừ khi đó là quy tắc có căn cứ riêng. Cũng cần chốt thời gian tối đa để xử lý lượng dữ liệu tồn sau hold, thay vì để trong hàng chờ vô thời hạn.

### 7.4. Đối tượng hết hạn nhưng đang được dùng

Tác vụ dài, stream, export và batch cần ngữ nghĩa riêng. Dữ liệu có được tiếp tục đọc nếu tác vụ bắt đầu trước hạn không? Có phải tái kiểm tra trước khi phát thêm dữ liệu hoặc ghi kết quả không?

Một quyết định cấp quyền từ nhiều giờ trước không nên mặc nhiên cho phép tạo bản sao mới sau hạn. Nếu có ngoại lệ nghiệp vụ, phải nêu phạm vi và giới hạn rõ ràng.

## 8. Từ yêu cầu đến cơ chế xóa và lưu trữ

### 8.1. Tách yêu cầu kết quả khỏi tên công nghệ

Các cơ chế có thể gồm TTL của kho dữ liệu, lifecycle của object storage, job theo lô, sự kiện xóa, thao tác phân vùng hoặc xử lý khóa.

Yêu cầu vẫn cần diễn đạt kết quả: dữ liệu nào bị chặn, dữ liệu nào được loại khỏi từng nơi, trong bao lâu, và cách chứng minh.

Ví dụ, “bật lifecycle 30 ngày” chưa đủ nếu phiên bản cũ, replica hoặc tệp export không nằm trong quy tắc. Cần xác minh ngữ nghĩa của cơ chế được chọn và mọi khoảng trễ mà nó cho phép.

### 8.2. Xử lý quan hệ giữa các bản ghi

Xóa một hồ sơ có thể để lại tệp mồ côi, chỉ mục còn nội dung hoặc bản ghi tham chiếu không hợp lệ.

Cần xác định nhóm đối tượng phải được xử lý cùng nhau và phần metadata nào được phép giữ. Nếu giữ tombstone để chống tái nhập dữ liệu, tombstone phải tối thiểu, có quyền truy cập và hạn lưu riêng.

Một tombstone chứa nguyên nội dung đã xóa chỉ chuyển dữ liệu sang chỗ khác.

### 8.3. Bền vững, idempotency và lỗi từng phần

Retry không được xóa nhầm một đối tượng mới có cùng khóa tái sử dụng. Lệnh xóa cần ràng buộc với đúng đối tượng, phiên bản hoặc thế hệ dữ liệu theo thiết kế.

Khi một nơi đã xử lý xong nhưng nơi khác thất bại, trạng thái phải phản ánh phần còn thiếu. Không ghi completed cho toàn phạm vi chỉ vì API kho chính trả thành công.

Cơ chế điều phối cần cho phép retry có giới hạn, đối soát và chuyển xử lý khi quá hạn. Hàng đợi lỗi cũng phải có retention và không trở thành nơi cất bản sao dữ liệu gốc vô hạn.

### 8.4. Dữ liệu mã hóa và hủy khóa

Mã hóa làm giảm một số rủi ro truy cập nhưng không tự hết nhu cầu retention.

Nếu dùng hủy khóa như một phần xử lý cuối vòng đời, phải xác định dữ liệu nào dùng khóa đó, các bản sao khóa, khóa bao ngoài, cache và bản plaintext có thể tồn tại. Không gọi việc vô hiệu hóa một khóa quản trị là hủy không thể phục hồi nếu khóa vẫn có thể được khôi phục theo quy trình khác.

Khóa dùng chung có thể ảnh hưởng nhiều nhóm dữ liệu. Chọn đơn vị hủy phải phù hợp với đơn vị retention và phạm vi bảo toàn, không chỉ thuận tiện cho vận hành.

## 9. Backup, bản sao bất biến và chống hồi sinh dữ liệu

### 9.1. Tuổi backup khác tuổi bản ghi

Một backup tạo hôm nay có thể chứa dữ liệu đã được tạo nhiều năm trước. Quy tắc giữ backup 14 ngày chỉ cho biết vòng đời của bản backup, không chứng minh dữ liệu bên trong đã được giữ đúng hạn ở nguồn.

Nếu dữ liệu quá hạn vẫn nằm trong kho chính, các backup mới có thể tiếp tục mang nó đi. Vì vậy, không thể chỉ cấu hình backup retention rồi bỏ qua retention của hệ thống đang chạy.

Cần có hạn riêng cho dữ liệu hoạt động và giới hạn tồn dư trong các bản sao phục hồi đã được phê duyệt.

### 9.2. Bản sao bất biến phải được xét ngay khi chọn kiến trúc

Một snapshot hoặc phương tiện bất biến có thể không hỗ trợ xóa riêng một bản ghi. Nếu vẫn chọn cơ chế đó, yêu cầu phải nêu:

- Dữ liệu nào có thể còn tồn tại trong bản sao.
- Tại sao và trong bao lâu sự tồn tại đó được chấp thuận.
- Ai được tiếp cận và cho mục đích nào.
- Khi nào bản sao không còn khả năng phục hồi.
- Điều kiện phải thực hiện khi khôi phục.
- Bằng chứng nào xác nhận bản sao đã hết vòng đời.

Không áp dụng đồng thời cam kết “mọi bản sao xóa ngay” với một kiến trúc không thực hiện được, rồi coi hạn backup là ngoại lệ không được ghi nhận.

Nếu nguồn yêu cầu không cho phép phần tồn dư đó, phải thay đổi kiến trúc hoặc giải quyết mâu thuẫn với nhóm có thẩm quyền trước khi cam kết.

### 9.3. Phục hồi vào vùng cách ly

Một quy trình có thể gồm:

1. Chọn bản backup và xác định chính sách liên quan.
2. Phục hồi vào vùng hạn chế truy cập, chưa mở cho nghiệp vụ.
3. Nạp trạng thái chính sách, hold và lịch sử xử lý có thẩm quyền.
4. Tính lại dữ liệu đã đến hạn tại thời điểm phục hồi.
5. Loại bỏ hoặc hạn chế dữ liệu theo yêu cầu hiện hành.
6. Kiểm tra các replica, chỉ mục và đầu ra sẽ được tái tạo.
7. Chỉ mở dịch vụ khi điều kiện bảo mật đã đạt.

Không chỉ chạy cleanup dựa trên ngày trong backup. Một bản backup có thể thiếu lệnh xóa hoặc thay đổi chính sách phát sinh sau khi nó được tạo.

Nếu phải giữ danh mục chống hồi sinh, cần định nghĩa định danh tối thiểu, nguồn chuẩn, quyền truy cập và thời gian tồn tại đủ bao phủ khả năng phục hồi bản cũ. Danh mục đó không cần giữ nguyên nội dung đã xóa.

### 9.4. Đo giới hạn tồn dư một cách trung thực

Ví dụ, kho hoạt động có hạn xử lý 24 giờ sau T_eligible. Mỗi backup được phép tồn tại tối đa 14 ngày kể từ mốc tạo đã xác định, tính cả thời gian thực thi hủy.

Có thể diễn đạt:

~~~text
T_live_purged <= T_eligible + 24 giờ

Với mỗi backup b còn chứa dữ liệu:
T_backup_unusable(b) <= T_backup_created(b) + 14 ngày
~~~

Nếu bảo đảm không có nguồn backup nào tiếp tục đưa dữ liệu đó vào bản sao sau T_live_purged, giới hạn tồn dư cuối cùng có thể được suy ra từ mốc chụp cuối cùng và tuổi backup tối đa.

Nếu chưa chứng minh điều kiện này, không được tự kết luận dữ liệu sẽ biến mất hoàn toàn sau “24 giờ cộng 14 ngày”.

Lệnh đánh dấu backup hết hạn và thời điểm thực sự không thể phục hồi có thể khác nhau. Hạn cam kết phải bao gồm độ trễ của cơ chế được sử dụng.

## 10. Log, audit và bằng chứng xử lý

### 10.1. Mỗi loại log có mục đích riêng

Log debug, trace vận hành và audit bảo mật có thể cần thời hạn khác nhau. Không dùng một thời hạn rất dài cho mọi log chỉ vì một nhóm audit cần giữ lâu hơn.

OWASP nhấn mạnh rằng log, log debug tạm thời và các bản sao hoặc trích xuất của chúng cần được xử lý theo thời hạn lưu giữ áp dụng, tránh hủy sớm hoặc giữ quá hạn. Phạm vi retention vì vậy phải bao gồm cả các bản trích xuất phục vụ điều tra. [OWASP Logging Cheat Sheet, Disposal of logs](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#disposal-of-logs).

Ngay từ thiết kế, cần giảm nội dung không cần thiết trong log. Chính sách giữ log không phải lý do để ghi mật khẩu, token truy cập hoặc toàn bộ hồ sơ nhạy cảm.

### 10.2. Ghi bằng chứng mà không giữ lại dữ liệu đã xử lý

Bằng chứng hữu ích có thể gồm:

- Mã lệnh và mã batch.
- Nhóm dữ liệu, tenant và phạm vi kho được xử lý.
- Phiên bản chính sách và mốc đánh giá.
- Số đối tượng đủ điều kiện, bị hold, hoàn tất hoặc lỗi.
- Thời điểm bắt đầu, kết thúc và các xác nhận theo từng nơi.
- Actor thực hiện và mã lý do ngoại lệ.

Nếu cần định danh từng đối tượng để đối soát, phải đánh giá mức dữ liệu tối thiểu cần giữ và hạn lưu của chính bằng chứng đó.

Không ghi nguyên nội dung bị xóa vào sự kiện “đã xóa”. Một ảnh chụp bảng trước khi dọn để làm bằng chứng cũng là một bản sao cần được quản lý.

### 10.3. Ngữ nghĩa của trạng thái hoàn tất

Nên phân biệt:

- Đã tiếp nhận lệnh.
- Đã đánh giá đủ điều kiện.
- Đã chặn truy cập thông thường.
- Đã xử lý kho hoạt động trong phạm vi.
- Còn bản backup được giữ theo ngoại lệ đã phê duyệt.
- Đã hoàn tất mức xử lý cuối vòng đời được cam kết.

Tên trạng thái và API phải phản ánh đúng kết quả. Không dùng một cờ deleted để biểu thị đồng thời mọi mức bảo đảm.

Việc API không tìm thấy bản ghi chỉ là bằng chứng của đường truy cập đó, chưa phải bằng chứng tất cả bản sao hoặc phương tiện đã được xử lý.

## 11. Bảo vệ chính sách và cơ chế retention

### 11.1. Phân quyền các hành động có tác động lớn

Cần xác định ai được:

- Định nghĩa hoặc đổi chính sách.
- Gán nhóm dữ liệu và sửa mốc nghiệp vụ.
- Đặt, sửa hoặc gỡ hold.
- Chạy xóa ngoại lệ hoặc xóa hàng loạt.
- Tạm dừng tác vụ xử lý khi có sự cố.
- Khôi phục dữ liệu và mở lại cho nghiệp vụ.

Quyền đọc dữ liệu không tự bao gồm quyền thay retention. Quyền vận hành tác vụ cũng không tự cho phép rút ngắn thời hạn audit hoặc bỏ qua hold.

Đối với phạm vi có tác động lớn, có thể cần tách vai trò hoặc kiểm soát bổ sung theo đánh giá rủi ro. Cơ chế phải tương xứng với loại dữ liệu và khả năng phục hồi.

### 11.2. Chính sách có phiên bản và tác động xác định

Khi đổi từ 180 ngày xuống 90 ngày, hệ thống có áp dụng cho bản ghi cũ không? Nếu áp dụng, có thể xuất hiện lượng lớn dữ liệu lập tức đủ điều kiện xử lý.

Khi tăng thời hạn, dữ liệu đã được hủy không tự quay lại. Những bản backup còn giữ dữ liệu cũng không nên được dùng để tái tạo vào kho hoạt động chỉ vì chính sách mới dài hơn.

Một thay đổi cần có thời điểm hiệu lực, phạm vi hồi tố, cách xử lý hold, kế hoạch năng lực và bằng chứng đối soát.

### 11.3. Giữ chính sách đúng qua các đường triển khai

Bản triển khai cũ, dịch vụ batch riêng và một công cụ quản trị có thể dùng quy tắc khác nhau. Cần nguồn chính sách có thẩm quyền và cách phát hiện lệch phiên bản.

Rollback phần mềm không được âm thầm khôi phục dữ liệu đã đến hạn hoặc áp dụng lại lịch giữ cũ trái quyết định hiện hành.

Nếu không thể lấy được chính sách bắt buộc, hành vi phải được quy định. Không mặc định xóa hàng loạt hoặc giữ mọi dữ liệu vô hạn để che lỗi hệ thống.

## 12. Ví dụ từ ma trận retention đến tiêu chí chấp nhận

### 12.1. Phạm vi và giả định

Giả sử một nền tảng hỗ trợ khách hàng có nội dung hồ sơ, tệp đính kèm, tệp import tạm, audit và backup.

Các con số dưới đây chỉ là lựa chọn minh họa của bài học. Trong ví dụ:

- Một ngày được tính là 24 giờ; các mốc lưu và so sánh theo UTC.
- Với hồ sơ đã đóng, mốc là sự kiện đóng hợp lệ đang có hiệu lực.
- Mở lại hồ sơ trước hạn phải là hành động nghiệp vụ được cấp quyền và audit; lần đóng hợp lệ tiếp theo xác lập mốc theo chính sách.
- Đọc hồ sơ, cập nhật chỉ mục và migrate dữ liệu không thay mốc.
- Dữ liệu đến hạn bị chặn khỏi sử dụng thông thường; xử lý kho hoạt động có độ trễ tối đa 24 giờ.
- Hold hợp lệ được đánh giá trước hành động hủy; quyền đọc vẫn theo chính sách riêng.

Không có thao tác “mở lại” một hồ sơ đã được hủy để kéo dài retention. Một hồ sơ mới hoặc dữ liệu được thu thập lại cần có căn cứ và vòng đời riêng.

### 12.2. Ma trận minh họa

| Nhóm dữ liệu | Mục đích | Mốc tính hạn | Khoảng lưu giữ ví dụ | Xử lý khi đến hạn |
| --- | --- | --- | --- | --- |
| Nội dung hồ sơ đã đóng | Hỗ trợ đối soát trong thời gian đã chọn | Sự kiện đóng hợp lệ | 90 ngày | Chặn đọc thông thường; xử lý kho hoạt động trong 24 giờ nếu không có hold |
| Tệp đính kèm | Bổ sung thông tin cho xử lý hồ sơ | Sự kiện đóng hợp lệ | 30 ngày | Chặn tải; loại nội dung và các phiên bản thuộc phạm vi trong 24 giờ nếu không có hold |
| Tệp import tạm | Hoàn thành tác vụ nhập | Thời điểm tiếp nhận đáng tin cậy | 24 giờ | Chặn sử dụng sau hạn và xử lý trong 24 giờ; tác vụ chưa xong chuyển sang ngoại lệ có owner |
| Audit tối thiểu | Truy vết hành động | Thời điểm hệ thống ghi nhận sự kiện | 180 ngày | Không cho xóa tùy ý trước hạn; xử lý khi đến hạn, có xét hold |
| Backup phục hồi | Khôi phục sự cố | Mốc tạo backup được định nghĩa | Tuổi tối đa 14 ngày | Không còn khả năng phục hồi sau giới hạn; có kiểm soát vùng restore |

Bảng này chưa thay thế toàn bộ đặc tả. Mỗi hàng còn cần inventory kho, owner, phương pháp xử lý, bằng chứng và cách xác nhận ngoại lệ.

Ví dụ, audit dùng thời điểm ghi nhận thì phải xác định cách đánh dấu sự kiện đến muộn, không cho caller tự chọn mốc để làm sự kiện bị hủy sớm.

### 12.3. Bộ yêu cầu đo được

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| RT-01 | Mọi nhóm dữ liệu trong inventory có mục đích, owner, mốc, chính sách phiên bản và xử lý cuối vòng đời | Không có kho hoặc luồng đã kiểm kê bị bỏ trống quy tắc; ngoại lệ có trạng thái và hạn giải quyết |
| RT-02 | Mốc nghiệp vụ không thay đổi bởi đọc, retry kỹ thuật, lập chỉ mục hoặc migrate | Thực hiện các thao tác này không làm tăng hạn; thay mốc chỉ qua sự kiện hợp lệ có audit |
| RT-03 | Dữ liệu đến hạn bị chặn khỏi sử dụng thông thường trong tối đa 60 giây sau T_eligible | Mọi quyết định đọc, tải và xuất mới trong phạm vi từ sau giới hạn đều từ chối, kể cả cache nóng |
| RT-04 | Dữ liệu đủ điều kiện, không có hold được xử lý ở kho hoạt động trong tối đa 24 giờ sau T_eligible | Xác nhận theo từng kho chính, replica, chỉ mục, cache, object và export còn do hệ thống quản lý |
| RT-05 | Không hủy dữ liệu trước hạn giữ bắt buộc hoặc trong khi hold có hiệu lực | Kiểm tra tại ranh giới thời gian và ca đặt hold đồng thời; hành động không thể đảo chỉ xảy ra khi đủ điều kiện |
| RT-06 | Đặt, sửa và gỡ hold phải kiểm tra quyền và ghi audit | Actor thiếu quyền không tác động trạng thái; gỡ hold không tự reset mốc retention |
| RT-07 | Xóa từng phần thất bại không được báo hoàn tất toàn phạm vi | Trạng thái thể hiện nơi còn lỗi, retry được đối soát và quá hạn được cảnh báo |
| RT-08 | Backup không vượt tuổi tối đa 14 ngày đã định và restore không làm sống lại dữ liệu hết hạn | Xác minh trạng thái backup; bản restore cũ chỉ mở sau khi tái áp dụng retention, hold và lịch sử xử lý |
| RT-09 | Thiếu mốc hoặc chính sách phải được đưa vào xử lý ngoại lệ, không âm thầm xóa hay giữ mãi | Owner nhận cảnh báo trong 15 phút từ phát hiện; có quyết định xử lý trong 48 giờ theo quy trình đã chọn |
| RT-10 | Bằng chứng xử lý không chứa nguyên nội dung bị xóa và có hạn lưu riêng | Đối soát được lệnh và kết quả mà không tạo kho dữ liệu gốc phụ; quyền đọc audit được kiểm soát |
| RT-11 | Thay đổi chính sách có phiên bản, thời điểm hiệu lực và quy tắc hồi tố | Bản ghi cũ và mới được đánh giá theo đúng phiên bản; rollback không đảo trạng thái đã xử lý |
| RT-12 | Dữ liệu quá hạn và lỗi xử lý được giám sát theo từng loại kho | Có thể xác định đối tượng quá hạn lâu nhất, phạm vi ảnh hưởng và owner; số lệnh chạy thành công không thay số liệu hiệu lực |

RT-03 cho phép độ trễ chặn 60 giây thay cho giả định chặn chính xác từng thời điểm. Nếu nghiệp vụ cần chặn ngay tại T_eligible, phải đổi yêu cầu và chứng minh cơ chế đáp ứng.

RT-04 không bao gồm phần tồn dư trong backup đã được quy định riêng tại RT-08. Khi báo cáo cho người dùng hoặc kiểm toán, phải nêu đúng phạm vi thay vì gộp thành “đã xóa tất cả”.

## 13. Ví dụ một yêu cầu có truy vết và ranh giới rõ ràng

~~~yaml
requirement_id: RT-04
risk_id: TH-RETENTION-03
risk: Dữ liệu hết hạn vẫn còn ở các kho phụ và có thể bị truy cập hoặc rò rỉ
data_scope:
  - Nội dung hồ sơ đã đóng
  - Tệp đính kèm thuộc nhóm chính sách tương ứng
policy_source: Ma trận retention đã được owner phê duyệt
time_model:
  timestamp_basis: UTC
  day_definition: 24 giờ
  anchor: Sự kiện đóng hợp lệ theo chính sách có hiệu lực
  eligible_at: Mốc đóng cộng khoảng lưu giữ của từng nhóm
  maximum_processing_delay_hours: 24
eligibility:
  - Đã đến hạn
  - Không có hold có hiệu lực tại điểm quyết định hủy
required_behavior:
  - Xử lý dữ liệu thuộc phạm vi tại từng kho hoạt động được kiểm kê
  - Không tạo bản sao mới để né thời hạn
  - Không báo hoàn tất khi còn nơi xử lý lỗi hoặc chưa xác minh
enforcement_scope:
  - Kho nghiệp vụ và replica
  - Chỉ mục tìm kiếm và cache
  - Object storage và các phiên bản thuộc chính sách
  - Export còn trong phạm vi hệ thống quản lý
separate_requirements:
  - Chặn sử dụng thông thường theo RT-03
  - Xử lý backup và điều kiện restore theo RT-08
verification:
  - Dữ liệu chưa đến hạn không bị hủy
  - Dữ liệu đủ điều kiện được xử lý trước hạn chót
  - Hold đồng thời không bị bỏ qua
  - Lỗi một kho không bị che bởi kết quả thành công ở kho khác
evidence:
  - Phiên bản chính sách và mốc đánh giá
  - Kết quả theo từng nơi lưu
  - Audit thao tác và trạng thái đối soát
owner: Nhóm hồ sơ, nhóm dữ liệu và nhóm vận hành lưu trữ
~~~

Đây là đặc tả minh họa, không phải cấu hình triển khai. Với hệ thống thực tế cần gắn từng mục enforcement_scope với inventory cụ thể, cơ chế thực thi và người chịu trách nhiệm.

Một phép đo RT-04 có thể dùng:

~~~text
Với mỗi đối tượng x đủ điều kiện, không bị hold:
    completion_time(x, live_scope) <= eligible_at(x) + 24 giờ

Chỉ ghi completion_time khi mọi nơi thuộc live_scope đã xác nhận
hoặc đã được xác minh bằng cơ chế tương đương được chấp thuận.
~~~

Nếu một nơi chưa quan sát được, kết quả là chưa xác minh hoặc lỗi theo quy trình; không coi thiếu phản hồi là bằng chứng đã xóa.

## 14. Thiết kế kiểm chứng và vận hành theo rủi ro

### 14.1. Kiểm thử ranh giới thời gian

Cần có dữ liệu thử nghiệm tại các mốc:

- Ngay trước T_eligible.
- Đúng T_eligible.
- Sau thời hạn chặn truy cập.
- Ngay trước và sau hạn hoàn tất xử lý.
- Có hold trước hạn và hold được đặt gần thời điểm hủy.
- Thiếu mốc, mốc tương lai hoặc quy tắc không xác định.

Dùng cơ chế kiểm soát thời gian trong môi trường kiểm thử khi thích hợp. Không thay đồng hồ của hệ thống đang phục vụ thật chỉ để làm bài kiểm tra.

Phải kiểm tra cả hành vi được phép và hành vi bị cấm. Chỉ quan sát dữ liệu cũ biến mất không chứng minh hệ thống không xóa sớm dữ liệu còn cần giữ.

### 14.2. Kiểm thử phạm vi bản sao

Tạo dữ liệu tổng hợp có thể nhận diện qua đường nghiệp vụ, chờ hoặc mô phỏng nó tới hạn, rồi kiểm tra theo inventory:

1. API đọc và tải.
2. Kho chính và replica liên quan.
3. Tìm kiếm, cache và kho tệp.
4. Hàng đợi, retry và tệp xuất do hệ thống quản lý.
5. Tập phân tích hoặc dữ liệu dẫn xuất thuộc yêu cầu.
6. Các backup còn chứa dữ liệu và quy tắc tồn dư.
7. Điều kiện mở lại sau phục hồi.

Không chỉ dùng thông tin “affected rows” của một câu lệnh xóa để kết luận toàn hệ thống đạt yêu cầu.

Tìm chuỗi tổng hợp giúp phát hiện một số bản sao, nhưng dữ liệu có thể bị chuẩn hóa, cắt nhỏ hoặc biến đổi. Cần phối hợp kiểm tra schema, luồng dữ liệu và cơ chế lưu trữ, thay vì coi một lần tìm không thấy là bằng chứng tuyệt đối.

### 14.3. Kiểm thử phân quyền và cuộc đua

Thử các actor có quyền đọc nhưng không có quyền sửa chính sách, actor chỉ có quyền vận hành batch và actor không có quyền trên tenant đang xét.

Các tình huống đồng thời cần bao gồm:

- Hold được đặt sau khi chọn ứng viên nhưng trước khi hủy.
- Gỡ hold khi một batch cũ đang chờ.
- Hồ sơ được mở lại hợp lệ trước hạn trong khi đánh giá retention.
- Retry lệnh xóa sau khi đối tượng hoặc phiên bản đã thay đổi.
- Thay chính sách khi batch đang chạy.
- Một consumer chậm tiếp tục xử lý sự kiện cũ.

Thiết kế phải xác định kết quả đúng theo điểm quyết định và phiên bản, không chỉ đưa ra kết quả phụ thuộc ngẫu nhiên vào thứ tự chạy.

### 14.4. Kiểm thử lỗi và phục hồi

Cần thử gián đoạn từng nơi lưu, lỗi API xóa, quota, mất sự kiện, batch dừng giữa chừng và tiến trình khởi động lại.

Kết quả phải chứng minh:

- Không xóa nhầm dữ liệu chưa đủ điều kiện.
- Không bỏ qua hold vì nguồn trạng thái tạm không sẵn sàng.
- Không báo thành công toàn phạm vi khi còn lỗi.
- Retry không làm thay đổi ý nghĩa lệnh.
- Cảnh báo xuất hiện trong thời hạn đã đặc tả.
- Dữ liệu quá hạn không được tái công bố qua restore, replay hoặc tái lập chỉ mục.

Khi phục hồi một snapshot cũ, cần kiểm tra cả trường hợp hệ thống chính sách hiện hành không sẵn sàng. Nếu không xác minh được điều kiện bắt buộc, dữ liệu không được mở theo một giả định cho phép không có trong đặc tả.

### 14.5. Dữ liệu thử nghiệm và bằng chứng

Dùng dữ liệu tổng hợp, tenant thử và phạm vi kho tách biệt phù hợp. Các thao tác hủy không thể đảo cần được thực hiện trên đối tượng đã xác định cho kiểm thử.

Báo cáo nên ghi mốc, phiên bản chính sách, điểm thực thi, kết quả và phần chưa xác minh. Không sao chép dữ liệu thật vào báo cáo để chứng minh đã xóa.

Một ca kiểm thử có thể chứng minh hành vi của phạm vi đã chạy. Muốn đưa ra cam kết toàn hệ thống còn cần inventory, cấu hình, quy trình vận hành và bằng chứng giám sát tương ứng.

### 14.6. Số liệu vận hành phải phản ánh hiệu lực

Các số liệu hữu ích gồm:

| Số liệu | Điều cần biết |
| --- | --- |
| Số đối tượng đủ điều kiện chưa hoàn tất | Phân theo loại dữ liệu, nơi lưu và trạng thái hold |
| Độ quá hạn lớn nhất | Phát hiện vi phạm ở đuôi phân phối mà số trung bình che mất |
| Số đối tượng thiếu mốc hoặc chính sách | Theo dõi phần không thể đánh giá thay vì loại khỏi báo cáo |
| Lỗi xử lý theo từng nơi | Nhận diện kho phụ hoặc vùng triển khai đang tồn dữ liệu |
| Số hold và lần rà soát quá hạn | Phát hiện ngoại lệ kéo dài không được xem xét |
| Backup vượt tuổi tối đa | Kiểm tra kết quả hủy, không chỉ cấu hình lịch |
| Số restore hoặc replay chưa đối soát | Tránh mở lại dữ liệu chưa đạt điều kiện |
| Mức phủ inventory | Biết số liệu đang đại diện cho bao nhiêu kho và consumer |

Nếu cam kết là một giới hạn tối đa, báo cáo chỉ p95 hoặc số trung bình không chứng minh mọi đối tượng đáp ứng. Cần theo dõi vi phạm giới hạn và phạm vi chưa quan sát được.

Khi lượng dữ liệu đến hạn vượt năng lực dọn, giảm backlog phải đi cùng ưu tiên rủi ro và kế hoạch năng lực. Không thay deadline trong cấu hình chỉ để làm số liệu quá hạn biến mất.

## 15. Những cách viết yêu cầu dễ gây hiểu nhầm

| Cách viết | Điều còn thiếu | Cách làm rõ |
| --- | --- | --- |
| Giữ dữ liệu 90 ngày | Mốc bắt đầu, phạm vi và hành động đến hạn | Nêu nhóm dữ liệu, sự kiện, quyền truy cập và deadline |
| Xóa ngay khi hết hạn | “Ngay” chưa có mốc đo và giới hạn | Đặc tả thời gian chặn, thời gian xử lý và điểm đo |
| Lấy updated_at làm mốc cho mọi bảng | Cập nhật kỹ thuật có thể gia hạn mãi | Dùng sự kiện nghiệp vụ có thẩm quyền |
| Chọn hạn dài nhất để chắc chắn | Có thể bỏ qua giới hạn lưu tối đa | Xử lý theo nguồn yêu cầu và quyết định của owner |
| Archive là hết trách nhiệm retention | Dữ liệu vẫn tồn tại | Áp dụng hạn và quyền cho lớp lưu trữ |
| Soft delete là xóa hoàn toàn | Có thể đọc hoặc khôi phục qua đường khác | Nêu mức bảo đảm và các bản sao phải xử lý |
| Backup giữ 14 ngày nên dữ liệu chỉ còn 14 ngày | Backup mới có thể tiếp tục chứa dữ liệu quá hạn | Kiểm soát cả nguồn và mốc chụp cuối cùng |
| Có hold thì mọi người được đọc tiếp | Nhầm bảo toàn với quyền sử dụng | Tách chặn hủy khỏi phân quyền truy cập |
| Gỡ hold thì tính lại retention từ đầu | Tự gia hạn không có căn cứ | Tái đánh giá theo mốc và chính sách được phê duyệt |
| Job chạy thành công là đã đạt | Có thể bỏ sót kho phụ hoặc lỗi từng phần | Đối soát kết quả theo phạm vi và deadline |
| Đã mã hóa nên giữ mãi cũng được | Mục đích và rủi ro vẫn còn | Áp dụng vòng đời cho dữ liệu, khóa và bản sao |
| Restore là khôi phục nguyên trạng để dùng ngay | Có thể hồi sinh dữ liệu đã hết hạn | Cách ly và tái áp dụng trạng thái có thẩm quyền trước khi mở |

Một yêu cầu lưu giữ đáng tin cậy phải trả lời được dữ liệu nào cần giữ, vì sao, đến khi nào, ai được dùng trong từng giai đoạn và bằng chứng nào xác nhận việc xử lý cuối vòng đời. Những câu trả lời này cần nhất quán từ mô hình đe dọa, kiến trúc lưu trữ đến kiểm thử và vận hành.
