# Denial-of-service defense — Đặc tả yêu cầu chống từ chối dịch vụ

## 1. Mục tiêu bảo vệ và phạm vi bài học

**Denial of service (DoS)** là tình huống làm suy giảm hoặc ngăn khả năng sử dụng một dịch vụ bằng cách chiếm dụng, làm cạn hoặc gây tắc nghẽn các tài nguyên cần thiết để phục vụ. **Distributed denial of service (DDoS)** sử dụng nhiều nguồn gây tác động; việc lọc theo một địa chỉ nguồn thường không đủ giải quyết tình huống này.

Trong đặc tả yêu cầu bảo mật, mục tiêu cần bảo vệ là khả năng thực hiện nghiệp vụ của người dùng hợp lệ, đồng thời giữ đúng xác thực, phân quyền, dữ liệu và audit. Một hệ thống vẫn phản hồi nhanh nhưng từ chối toàn bộ khách hàng không đạt mục tiêu đó.

Yêu cầu “có cơ chế chống DDoS” chưa cho biết năng lực nào cần duy trì, trước loại tác động nào, đến mức nào và được kiểm chứng ra sao. Cần chuyển nó thành các phát biểu có phạm vi và ngưỡng đo được.

Sau bài học, người đọc có thể:

- Liên kết kịch bản gây cạn tài nguyên với rủi ro mất khả dụng.
- Phân biệt bảo vệ đường truyền, tài nguyên giao thức và tài nguyên ứng dụng.
- Đặc tả hạn mức, khả năng cô lập, hành vi quá tải và giới hạn tăng tài nguyên.
- Viết tiêu chí nghiệm thu dựa trên trải nghiệm người dùng hợp lệ và bằng chứng vận hành.

Bài học thuộc phạm vi chuyển mục tiêu an toàn thông tin và mô hình đe dọa thành yêu cầu bảo mật cụ thể. Các con số là ví dụ của một cổng đặt hàng nhiều tenant, không phải ngưỡng mặc định cho mọi hệ thống.

## 2. Nhận diện đúng tài nguyên có thể bị làm cạn

DoS không chỉ xuất hiện khi số request rất lớn. Một thao tác ít lần nhưng có chi phí cao hoặc giữ tài nguyên lâu cũng có thể làm gián đoạn dịch vụ.

| Bề mặt hoặc tài nguyên | Tình huống gây suy giảm | Năng lực cần bảo vệ |
|---|---|---|
| Đường truyền trước cổng vào | Lưu lượng chiếm hết băng thông trước khi bộ lọc của ứng dụng nhận được request. | Khả năng khách hàng tiếp cận điểm phục vụ. |
| Kết nối và trạng thái giao thức | Nhiều kết nối tồn tại lâu, quá trình nhận dữ liệu không hoàn tất. | Chỗ cho kết nối hợp lệ và bộ nhớ trạng thái. |
| CPU ứng dụng | Công việc phân tích dữ liệu, xác thực hoặc tính toán tiêu tốn quá nhiều tài nguyên. | Thời gian xử lý của nghiệp vụ trọng yếu. |
| Bộ nhớ và hàng đợi | Yêu cầu được nhận nhanh hơn khả năng hoàn thành; dữ liệu chờ tích tụ. | Khả năng tiếp tục nhận và xử lý tải nằm trong cam kết. |
| Pool kết nối dữ liệu | Truy vấn chậm hoặc công việc dài giữ hết kết nối. | Khả năng thực hiện giao dịch ngắn cần thiết. |
| Dịch vụ định danh và kiểm tra quyền | Lưu lượng kiểm tra danh tính vượt năng lực phụ thuộc. | Đăng nhập và quyết định quyền hợp lệ. |
| Worker xử lý bất đồng bộ | Công việc tốn chi phí chiếm hết worker, hàng đợi hoặc nơi lưu kết quả. | Các công việc cần hoàn thành đúng thời hạn. |
| Hệ thống log và giám sát | Log tăng quá nhanh hoặc bên nhận log bị nghẽn. | Khả năng quan sát và audit theo chính sách. |
| Ngân sách vận hành | Tài nguyên tự mở rộng không có giới hạn hoặc gọi dịch vụ trả phí quá nhiều. | Khả năng duy trì dịch vụ trong ngân sách đã chấp nhận. |

Cùng một tốc độ request có thể gây tác động khác nhau theo kích thước dữ liệu, thời gian giữ kết nối, độ phức tạp truy vấn và tỷ lệ cache miss. Vì vậy, đơn vị “request/giây” cần đi kèm loại thao tác và chi phí liên quan.

Một tài khoản đã xác thực cũng có thể lạm dụng chức năng hợp lệ. Yêu cầu chống DoS phải xem xét cả lưu lượng chưa xác thực và hành vi sau xác thực, thay vì coi đăng nhập thành công là bằng chứng rằng mọi mức sử dụng đều được phép.

## 3. Từ tác động nghiệp vụ tới kịch bản đe dọa

Giả sử cổng đặt hàng có ba nhóm chức năng:

- Tạo và tra cứu đơn là nghiệp vụ trọng yếu.
- Xem danh mục có thể sử dụng cache trong giới hạn độ cũ đã được chấp nhận.
- Xuất báo cáo có thể trì hoãn khi thiếu tài nguyên.

Mỗi tổ chức khách hàng là một tenant. Năng lực tạo đơn của tenant đang sử dụng trong hạn mức cần được bảo vệ khi một tenant khác gây quá tải.

| Kịch bản đe dọa | Hậu quả | Yêu cầu cần dẫn xuất |
|---|---|---|
| Một tenant gửi quá nhiều lần tạo đơn | Tenant khác chờ lâu hoặc không tạo được đơn. | Hạn mức theo tenant và bảo đảm phần tài nguyên cho nhóm được bảo vệ. |
| Một tài khoản yêu cầu nhiều báo cáo nặng | Worker, CPU và kết nối dữ liệu bị chiếm hết. | Giới hạn công việc đồng thời, hàng đợi và thời gian thực thi theo loại công việc. |
| Lưu lượng chưa xác thực tăng mạnh | Chi phí kiểm tra danh tính làm nghẽn toàn hệ thống. | Kiểm soát sớm ở biên và giới hạn tài nguyên cho giai đoạn xác thực. |
| Client gửi dữ liệu chậm hoặc quá lớn | Kết nối và bộ nhớ tồn tại kéo dài. | Giới hạn thời gian nhận, kích thước, mức đồng thời và cách kết thúc. |
| Nhiều request cùng làm mới một dữ liệu cache | Phụ thuộc dữ liệu nhận tải tăng đột biến. | Giới hạn công việc làm mới và bảo vệ phụ thuộc khi cache không có dữ liệu. |
| Phụ thuộc bị chậm, client và nhiều tầng cùng retry | Tải tăng thêm đúng lúc năng lực đã suy giảm. | Deadline, ngân sách retry, cơ chế giảm nhận tải và cô lập lỗi. |
| Lưu lượng bão hòa đường truyền bên ngoài | Bộ lọc trong ứng dụng không còn cơ hội xử lý. | Xác định năng lực bảo vệ phía trước điểm bão hòa và trách nhiệm phối hợp. |

Chuỗi truy vết cần giữ rõ:

> Tài sản và tác động → kịch bản đe dọa → yêu cầu đo được → quyết định kiến trúc → ca kiểm thử → bằng chứng.

Ví dụ, “dùng gateway” là một lựa chọn kiến trúc. Yêu cầu cần chứng minh rằng tenant không gây quá tải vẫn tạo được đơn trong điều kiện đã cam kết, đồng thời gateway không làm mất kiểm soát quyền hoặc che mất số liệu lỗi.

## 4. Đặt ranh giới cho lời cam kết bảo vệ

Không nên cam kết “chống được mọi DoS”. Đặc tả phải nêu điều kiện mà hệ thống được yêu cầu chịu đựng và cách xử lý khi điều kiện vượt phạm vi.

Một hồ sơ điều kiện tối thiểu cần có:

| Thành phần | Nội dung phải xác định |
|---|---|
| Năng lực nghiệp vụ | Hành trình cần giữ, chẳng hạn tạo đơn đúng và tra cứu trạng thái. |
| Nhóm người dùng | Tenant, tài khoản, khu vực hoặc kênh truy cập được bảo vệ. |
| Tải hợp lệ | Tốc độ, mức đồng thời, phân bố tenant, kích thước và loại thao tác. |
| Tải gây nhiễu | Nguồn logic, trạng thái xác thực, loại thao tác, tốc độ và thời gian duy trì. |
| Ranh giới hạ tầng | Điểm lưu lượng đi vào, đường truyền và phụ thuộc nằm trong phép thử. |
| Mức dịch vụ tối thiểu | Tỷ lệ thành công đúng, thời hạn hoàn thành và cửa sổ đo. |
| Giới hạn tài nguyên | Kết nối, bộ nhớ, hàng đợi, worker, dung lượng lưu và năng lực mở rộng. |
| Hành vi vượt khả năng | Từ chối, trì hoãn, giảm chức năng, cảnh báo và điều kiện phục hồi. |
| Ngoại lệ và phụ thuộc | Những sự cố chưa được cam kết chịu đựng cùng người chịu trách nhiệm. |
| Bằng chứng | Điểm đo, dữ liệu thô, cấu hình và ca thử đủ để đánh giá. |

Nếu chỉ kiểm thử lưu lượng tại tầng ứng dụng trong một môi trường có đường truyền còn dư, kết luận chỉ áp dụng cho điều kiện ấy. Không được dùng kết quả đó để tuyên bố chịu được bão hòa đường truyền hoặc mọi dạng tấn công phân tán.

Giới hạn trách nhiệm kỹ thuật cũng cần gắn với đường đi thực tế. Bộ lọc phía sau một đường truyền đã đầy không thể tự khôi phục khả năng truy cập qua đường truyền đó.

## 5. Đo khả năng phục vụ người dùng hợp lệ

### 5.1. Định nghĩa sự kiện tốt

Với tạo đơn, một lần thử đủ điều kiện là yêu cầu có dữ liệu đúng, quyền hợp lệ, thuộc tenant đã kích hoạt và nằm trong hạn mức sử dụng đã công bố.

Một lần thử tốt phải đồng thời:

1. Hoàn thành xác nhận trong không quá hai giây tại ranh giới đo đã chọn.
2. Ghi nhận đúng một đơn theo hợp đồng chống lặp của giao dịch.
3. Gắn đúng tenant và chủ thể.
4. Thực thi đầy đủ kiểm soát xác thực, phân quyền và điều kiện audit bắt buộc.

Ranh giới minh họa là từ khi cổng vào được quản lý nhận đủ yêu cầu tới khi phát xong phản hồi. Khả năng tiếp cận cổng vào cần phép đo bên ngoài bổ sung; không chỉ dùng log ứng dụng để đánh giá trường hợp lưu lượng bị chặn hoặc mất trước cổng vào.

~~~text
SLI bảo vệ nghiệp vụ
  = số lần thử hợp lệ được hoàn thành đúng trong thời hạn
    / tổng số lần thử hợp lệ thuộc phạm vi bảo vệ
~~~

Một phản hồi thành công nhưng dữ liệu sai tenant không được tính là sự kiện tốt. Một phản hồi từ chối nhanh do hết tài nguyên cũng không phải thành công nghiệp vụ.

### 5.2. Giữ nguyên mẫu số khi đánh giá

Phải xác định quy tắc phân loại trước bài thử hoặc trước kỳ đo:

- Yêu cầu hợp lệ của tenant được bảo vệ bị từ chối nhầm phải tính là lỗi phục vụ.
- Yêu cầu vượt hạn mức của nhóm gây nhiễu không được trộn vào mẫu số người dùng đang dùng trong cam kết.
- Không coi mọi lỗi xác thực là lưu lượng xấu khi chính phụ thuộc xác thực đang bị gián đoạn.
- Không loại timeout hoặc lỗi trước khi vào ứng dụng chỉ vì log ứng dụng không ghi nhận chúng.
- Tách kết quả theo tenant hoặc nhóm chịu rủi ro để số tổng không che mất một nhóm bị chặn hoàn toàn.
- Khoảng mất dữ liệu quan sát phải được báo cáo, không tự tính là hệ thống hoạt động tốt.

Trong bài thử, danh tính và tính hợp lệ của hai nhóm tải cần được biết trước. Trong vận hành, cần phương pháp đối soát, lấy mẫu hoặc phép đo độc lập để đánh giá tác động mà không chỉ tin quyết định phân loại của chính bộ lọc.

### 5.3. Tách ba nhóm chỉ số

| Nhóm chỉ số | Ví dụ | Ý nghĩa |
|---|---|---|
| Kết quả nghiệp vụ | Tỷ lệ tạo đơn đúng trong thời hạn, lỗi theo tenant. | Chứng minh người dùng hợp lệ còn được phục vụ. |
| Hiệu quả kiểm soát | Số request bị hạn chế, tác vụ bị từ chối trước khi tốn chi phí lớn. | Cho biết kiểm soát đã hoạt động như thế nào. |
| Sức khỏe tài nguyên | Độ dài hàng đợi, kết nối còn giữ, bộ nhớ, worker và mức mở rộng. | Phát hiện cạn tài nguyên hoặc công việc tích tụ phía sau phản hồi. |

Số lượng request bị chặn lớn không tự chứng minh đạt mục tiêu. Nếu bộ lọc chặn nhầm phần lớn người dùng hợp lệ, chỉ số “đã chặn” có thể tăng trong khi dịch vụ vẫn thất bại.

## 6. Đặc tả các lớp kiểm soát

### 6.1. Bảo vệ trước điểm bão hòa

Với nguy cơ bão hòa đường truyền, yêu cầu cần nêu năng lực bảo vệ ở phía trước điểm đó, cách chuyển lưu lượng qua lớp bảo vệ, điều kiện kích hoạt và người chịu trách nhiệm phối hợp.

Cần kiểm tra các đường truy cập thay thế có làm bỏ qua lớp bảo vệ hay không. Điểm vào dành cho quản trị, dịch vụ nội bộ hoặc origin cần chính sách tiếp cận phù hợp; nếu chúng mở công khai không có kiểm soát tương ứng, đường đi chính được bảo vệ vẫn chưa đủ.

Một nguồn được tin cậy để chuyển tiếp lưu lượng phải được xác định bằng cơ chế có thể kiểm chứng. Không coi header do client tự gửi là bằng chứng rằng request đã đi qua một proxy được phép.

### 6.2. Kiểm soát sớm nhưng giữ đúng danh tính

Trước xác thực, hệ thống có thể dựa trên tín hiệu kết nối hoặc nguồn truy cập để giới hạn chi phí ban đầu. Sau xác thực, có thể áp hạn mức theo tài khoản, tenant, ứng dụng gọi hoặc nhóm thao tác.

Địa chỉ IP không đồng nghĩa với một người dùng. Nhiều khách hàng có thể chia sẻ địa chỉ nguồn; nhiều địa chỉ nguồn cũng có thể thuộc cùng một nhóm gây quá tải. Chính sách chỉ dựa vào IP cần được đánh giá về chặn nhầm, khả năng né giới hạn và tác động tới nhóm người dùng cụ thể.

Không cho phép client tự khai tenant hoặc danh tính trong một trường chưa được xác minh rồi dùng trường đó để tiêu thụ hạn mức của tenant khác. Cần gắn hạn mức với danh tính đã được thiết lập qua cơ chế tin cậy.

### 6.3. Giới hạn theo chi phí và mức đồng thời

Hạn mức số request không thay thế giới hạn tài nguyên. Cần xem xét:

- Tốc độ nhận công việc trong khoảng đo đã xác định.
- Mức tăng ngắn hạn được chấp nhận và cách hồi phục hạn mức.
- Số tác vụ đang thực thi theo tenant và toàn hệ thống.
- Độ dài hàng đợi và thời gian tối đa được chờ.
- Thời gian thực thi, kích thước dữ liệu và số lượng kết quả.
- Giới hạn công việc phụ phát sinh từ một yêu cầu.

Hai endpoint có chi phí rất khác nhau không nhất thiết dùng chung một đơn vị hạn mức. Nếu dùng trọng số chi phí, cần mô tả cách tính, dữ liệu chứng minh và hành vi khi có thao tác mới chưa được phân loại.

### 6.4. Kiểm soát dữ liệu đầu vào và công việc phát sinh

Giới hạn phải áp dụng trước hoặc tại nơi phát sinh chi phí lớn. Ví dụ gồm kích thước yêu cầu, độ sâu cấu trúc, số phần tử, phạm vi phân trang, dung lượng sau giải nén và số công việc con.

Nếu chỉ giới hạn kích thước dữ liệu truyền nhưng không giới hạn dữ liệu sau giải nén hoặc lượng công việc suy ra, tài nguyên bên trong vẫn có thể bị làm cạn. Tương tự, giới hạn số request không đủ cho một request tạo ra rất nhiều thao tác dữ liệu.

Yêu cầu cần nêu hành vi khi chạm giới hạn, việc dọn dữ liệu tạm và thông tin trả về. Đầu vào bị từ chối không được làm lộ cấu trúc nội bộ hoặc dữ liệu nhạy cảm trong thông báo lỗi.

## 7. Cô lập, giảm nhận tải và chế độ suy giảm

### 7.1. Cô lập nghiệp vụ và tenant

Một công việc báo cáo dài không nên mặc nhiên được quyền dùng hết nguồn lực dành cho giao dịch tạo đơn. Thiết kế có thể dùng pool riêng, hạn mức đồng thời, phân vùng hoặc cơ chế điều phối khác; yêu cầu phải mô tả kết quả cần giữ.

Tương tự, giới hạn theo tenant cần có phạm vi rõ ràng. Nếu mỗi replica tự cấp toàn bộ hạn mức, tăng số replica có thể làm tổng hạn mức tăng ngoài dự kiến. Đặc tả phải nêu hạn mức là cục bộ hay chung, cách xử lý cập nhật đồng thời và mức vượt tạm thời được phép nếu có.

Khi nơi lưu trạng thái hạn mức không truy cập được, cần chính sách đã xác định: dùng phần hạn mức cục bộ đã phân bổ, giảm nhận tải hoặc từ chối loại thao tác phù hợp. Không được âm thầm biến lỗi của bộ đếm thành khả năng nhận công việc không giới hạn.

### 7.2. Từ chối trước khi công việc vượt khả năng

Hàng đợi hữu hạn giúp hấp thụ một phần dao động ngắn, nhưng không tạo thêm năng lực xử lý lâu dài. Khi tốc độ nhận liên tục lớn hơn tốc độ hoàn thành, cần giảm nhận tải hoặc từ chối theo hợp đồng.

Yêu cầu cần xác định:

- Điểm kiểm tra hạn mức và điểm công việc được coi là đã chấp nhận.
- Khi nào phản hồi là từ chối trước xử lý, khi nào kết quả vẫn đang chờ hoặc chưa rõ.
- Client được phép thử lại thế nào; thông tin chờ có làm các client cùng retry một lúc không.
- Thời gian tối đa công việc được giữ trong hàng đợi.
- Cách hủy, dọn dữ liệu tạm và xử lý công việc hết hạn.
- Số liệu tách riêng công việc bị từ chối, đã nhận, đã hoàn thành và đã thất bại.

Một xác nhận “đã nhận báo cáo” chỉ chứng minh hệ thống nhận việc. Nếu có cam kết hoàn thành báo cáo, phải có chỉ số và thời hạn riêng cho kết quả đó.

### 7.3. Giảm chức năng theo chính sách

| Chức năng | Hành vi có thể áp dụng khi quá tải | Ràng buộc phải giữ |
|---|---|---|
| Danh mục công khai | Phục vụ cache trong giới hạn độ cũ đã chấp nhận. | Không trộn dữ liệu riêng vào cache công khai. |
| Tạo đơn | Ưu tiên tài nguyên và từ chối rõ khi không thể xử lý đúng. | Không xác nhận thành công khi chưa đáp ứng cam kết ghi dữ liệu. |
| Báo cáo | Giảm số công việc đồng thời, trì hoãn hoặc từ chối khi đầy. | Kiểm soát quyền tải kết quả và dọn dữ liệu tạm. |
| Thay đổi quyền, cấu hình nhạy cảm | Tạm dừng khi không xác minh được điều kiện bắt buộc. | Không bỏ kiểm tra để tăng khả năng phục vụ. |
| Log chẩn đoán | Giới hạn bộ đệm và mức chi tiết theo chính sách. | Có bằng chứng về mất log; không tăng ghi bí mật để hỗ trợ điều tra. |
| Audit bắt buộc | Dùng nguồn lưu dự phòng được phép hoặc dừng thao tác liên quan. | Không âm thầm bỏ audit để báo thành công. |

Nếu áp dụng thử thách tương tác hoặc hạn chế truy cập theo tín hiệu rủi ro, phải đánh giá tác động tới người dùng hợp lệ, ứng dụng tích hợp và khả năng tiếp cận. Kết quả chặn nhầm vẫn là lỗi phục vụ khi yêu cầu thuộc phạm vi đã cam kết.

## 8. Bộ yêu cầu chống DoS mẫu

Bối cảnh nghiệm thu: mười tenant được bảo vệ, mỗi tenant gửi đều 10 lần tạo đơn hợp lệ mỗi giây. Tổng tải hợp lệ là 100 lần/giây. Môi trường có cấu hình, dữ liệu, năng lực phát tải và băng thông được ghi trong hồ sơ thử.

Nhóm gây nhiễu được tách riêng và không chiếm danh tính của các tenant được bảo vệ. Bài thử chỉ chạy trong môi trường và phạm vi đã được phép.

### SR-DOS-001 — Duy trì giao dịch hợp lệ khi có tải gây nhiễu

Trong khoảng 20 phút có tải gây nhiễu 1.000 lần/giây của một tenant khác, ít nhất 99,9% lần tạo đơn hợp lệ của nhóm được bảo vệ phải hoàn thành đúng trong hai giây. Loại dữ liệu, kích thước yêu cầu và cách phát tải phải được cố định trước khi chạy.

Chỉ số được tính trên chính khoảng có gây nhiễu và báo cáo riêng cho từng tenant được bảo vệ. Với tải hợp lệ được phát đủ, tổng số lần thử là:

~~~text
100 lần/giây × 20 phút × 60 giây/phút = 120.000 lần thử

Ngân sách lỗi theo tỷ lệ 99,9%:
120.000 × 0,1% = 120 lần không tốt
~~~

Ngoài ngưỡng tổng, từng tenant trong ví dụ cũng phải đạt 99,9% trong khoảng này. Với 12.000 lần thử của một tenant, tối đa 12 lần không tốt được phép theo chỉ số tỷ lệ.

Những lần đủ điều kiện bị chặn nhầm, từ chối vì thiếu tài nguyên hoặc timeout được tính là lỗi. Một lỗi về quyền hoặc tính toàn vẹn không được bỏ qua chỉ vì tổng tỷ lệ vẫn còn trong ngân sách; các ràng buộc bảo mật tương ứng phải được kiểm chứng riêng.

### SR-DOS-002 — Hạn mức tenant có phạm vi nhất quán

Trong cấu hình minh họa, mỗi tenant được nhận tối đa 20 lần tạo đơn trong mỗi cửa sổ trượt một giây, tính chung qua tất cả replica phục vụ endpoint đó; không cấp burst bổ sung trong hồ sơ thử này.

Yêu cầu vượt hạn mức phải bị từ chối trước khi bắt đầu công việc ghi dữ liệu tốn chi phí. Cơ chế xác lập tenant phải dựa trên danh tính đã được xác minh; trường do client tự khai không được dùng để trừ hạn mức của tenant khác.

Bằng chứng phải có thử nghiệm phân tán request qua nhiều replica và tăng số replica trong phạm vi triển khai cho phép. Chính sách khi bộ đếm hạn mức gặp lỗi phải được ghi rõ và có phép thử; không được mặc nhiên chuyển sang nhận không giới hạn.

Giới hạn này là một tham số của ví dụ, chưa đại diện mọi gói dịch vụ. Nếu sản phẩm cho phép burst hoặc có sai số đồng bộ chấp nhận được, các giá trị đó phải được thay bằng định nghĩa cụ thể trong yêu cầu thực tế.

### SR-DOS-003 — Công việc báo cáo không chiếm hết tài nguyên

Mỗi tenant được chạy tối đa hai báo cáo đồng thời; toàn hệ thống thử chạy tối đa tám báo cáo đồng thời và giữ tối đa 40 báo cáo trong hàng đợi chờ.

Một công việc chờ quá 30 giây mà chưa bắt đầu phải hết hạn theo hợp đồng đã công bố. Mỗi báo cáo đang thực thi có giới hạn thời gian 60 giây trong hồ sơ thử. Cần phân biệt bên gọi ngừng chờ với công việc thực sự đã dừng.

Không được chuyển công việc vượt giới hạn sang một hàng đợi không có giới hạn khác. Công việc đã yêu cầu hủy nhưng chưa dừng vẫn phải được theo dõi và tính vào giới hạn tài nguyên còn sử dụng.

Khi nhóm gây nhiễu liên tục yêu cầu báo cáo, nhóm được bảo vệ vẫn phải đạt tiêu chí tạo đơn của SR-DOS-001 trong bài thử riêng 20 phút. Bài thử này tách khỏi tải tạo đơn gây nhiễu để xác định rõ tác động của từng loại công việc.

### SR-DOS-004 — Giới hạn tài nguyên trước và trong xử lý

Endpoint tạo đơn phải giới hạn body tối đa 16 KiB trong cấu hình thử. Quá trình nhận header có thời hạn tổng hai giây kể từ byte đầu tiên; quá trình nhận body có thời hạn tổng bốn giây kể từ khi nhận đủ header.

Thời gian kết nối chờ byte đầu tiên và số kết nối đồng thời phải có giới hạn riêng được ghi trong cấu hình nghiệm thu. Dữ liệu tạm sau khi kết thúc nhận phải được dọn theo giới hạn thời gian đã đặc tả.

Các giai đoạn chờ hàng đợi, chờ kết nối dữ liệu và gọi phụ thuộc phải chịu deadline xử lý chung. Việc client đều đặn gửi một phần dữ liệu không được làm vô hiệu giới hạn tổng thời gian nhận.

Bằng chứng gồm thử nghiệm dữ liệu quá giới hạn, nhận chậm, ngắt kết nối và công việc phía sau còn chạy. Phải kiểm tra cả bộ nhớ, kết nối và tài nguyên tạm sau nhiều lần lặp.

### SR-DOS-005 — Không suy giảm kiểm soát quyền khi quá tải

Khi hệ thống đang hạn chế tải hoặc dịch vụ định danh phản hồi chậm, mọi giao dịch tạo đơn vẫn phải có bằng chứng quyền hợp lệ theo chính sách.

Không được chấp nhận danh tính từ header không tin cậy, dùng kết quả quyền của tenant khác hoặc chuyển lỗi kiểm tra quyền thành cho phép mặc định. Các cache quyết định quyền chỉ được dùng trong phạm vi hiệu lực và thu hồi đã phê duyệt.

Bằng chứng phải gồm tài khoản có quyền, không có quyền, đã bị thu hồi quyền và các phản hồi quyền đến muộn. Một giao dịch bị từ chối an toàn vẫn cần được phản ánh là không thành công đối với hành trình của người dùng hợp lệ nếu nó nằm trong phạm vi cam kết.

### SR-DOS-006 — Giới hạn mở rộng và khả năng phục hồi

Cấu hình nghiệm thu phải công bố số replica, worker và kết nối tối đa, cùng các giới hạn tài nguyên hoặc hạn mức dịch vụ liên quan. Cơ chế tự mở rộng không được vượt các giá trị đó.

Trong vòng năm phút sau khi dừng tải gây nhiễu, khi tải hợp lệ tiếp tục ở mức 100 lần/giây, các chỉ số hàng đợi và tài nguyên phải trở về phạm vi vận hành bình thường đã xác định trước bài thử. Không để backlog, công việc mồ côi hoặc cơ chế retry duy trì tình trạng quá tải.

Khoảng phục hồi năm phút không thay thế tiêu chí phục vụ trong lúc có gây nhiễu. Thành công nghiệp vụ sau khi ngừng gây nhiễu vẫn phải được báo cáo, thay vì chỉ kiểm tra số replica đã giảm.

Nếu giới hạn chi phí hoặc tài nguyên làm mục tiêu nghiệp vụ không khả thi, phải đưa xung đột đó tới chủ sở hữu rủi ro để điều chỉnh phạm vi hoặc nguồn lực. Không tăng năng lực vô hạn rồi coi đó là một biện pháp bảo vệ đã hoàn chỉnh.

### SR-DOS-007 — Phát hiện và lưu bằng chứng

Trong ví dụ, điều kiện cảnh báo là tỷ lệ lỗi nghiệp vụ của nhóm được bảo vệ vượt 1% trong hai cửa sổ một phút liên tiếp khi đủ dữ liệu đo. Hệ thống phải phát cảnh báo trong 60 giây kể từ lúc xác nhận điều kiện ấy.

Ngưỡng này là ngưỡng vận hành minh họa, không thay đổi tiêu chí nghiệm thu 99,9%. Các dấu hiệu cạn tài nguyên hoặc lưu lượng bất thường có thể có cảnh báo sớm riêng, không cần chờ thất bại nghiệp vụ.

Bằng chứng cần phân biệt lưu lượng hợp lệ, lưu lượng vượt hạn mức, lý do từ chối, tác vụ còn chạy và thay đổi cấu hình. Không ghi token, mật khẩu hoặc toàn bộ nội dung nhạy cảm để phục vụ phân loại.

## 9. Ma trận kiểm thử và bằng chứng nghiệm thu

| Phép thử | Điều kiện cần tạo | Bằng chứng quyết định đạt |
|---|---|---|
| Tenant vượt hạn mức | Một tenant gây nhiễu trong khi mười tenant khác giữ tải hợp lệ. | SLI tổng và theo tenant đạt; giới hạn không bị nhân lên theo replica. |
| Tải trước xác thực | Lưu lượng không đủ điều kiện xác thực tăng trong phạm vi thử được xác định. | Chi phí xác thực được giới hạn, quyền vẫn đúng và tải hợp lệ được đo riêng. |
| Lạm dụng báo cáo | Liên tục gửi yêu cầu báo cáo trong bài thử riêng. | Số chạy, số chờ, thời gian chờ và khả năng tạo đơn đúng ngưỡng. |
| Nhận dữ liệu chậm | Client không hoàn tất dữ liệu trong thời gian cho phép. | Giới hạn tổng có hiệu lực, tài nguyên không tích tụ qua các lần lặp. |
| Bộ đếm hạn mức bị lỗi | Làm mất hoặc trì hoãn truy cập trạng thái hạn mức. | Hành vi đúng chính sách, không tự nhận không giới hạn và không chuyển lỗi thành quyền truy cập. |
| Cache không có dữ liệu | Tạo điều kiện nhiều yêu cầu cùng cần dữ liệu từ phụ thuộc. | Công việc làm mới và tải xuống phụ thuộc có giới hạn; số liệu không chỉ dựa trên cache nóng. |
| Phụ thuộc bị chậm | Làm tăng thời gian xử lý của phụ thuộc trong phạm vi kiểm soát. | Deadline, hủy và retry không tạo lượng công việc tăng vô hạn. |
| Tăng số replica | Thay đổi số replica trong giới hạn triển khai khi tải đang chạy. | Hạn mức và giới hạn toàn hệ thống vẫn đúng phạm vi công bố. |
| Ngừng gây nhiễu | Dừng nguồn gây nhiễu, duy trì tải hợp lệ. | Backlog và tài nguyên hồi phục; dịch vụ không tiếp tục bị retry hoặc công việc mồ côi làm nghẽn. |
| Đường truy cập thay thế | Kiểm tra các điểm vào trong phạm vi tài sản được giao. | Không có đường bỏ qua kiểm soát trái chính sách; bằng chứng nêu rõ giới hạn kiểm tra. |

Phép thử tải trước xác thực, cache miss hoặc phụ thuộc chậm cần có mức tải, thời gian và ngưỡng riêng trước khi dùng để nghiệm thu. Không sao chép kết quả của một kịch bản sang kịch bản khác chỉ vì chúng cùng gây CPU cao.

Ví dụ kịch bản cho SR-DOS-001 và SR-DOS-002:

~~~gherkin
Feature: Bảo vệ tenant trong hạn mức khi tenant khác gây quá tải

  Scenario: Tạo đơn hợp lệ tiếp tục đạt mức dịch vụ
    Given mười tenant được bảo vệ có quyền tạo đơn
    And mỗi tenant gửi đều 10 lần mỗi giây với dữ liệu hợp lệ
    And hạn mức thử được áp thống nhất qua tất cả replica
    When một tenant khác gửi 1000 lần mỗi giây trong 20 phút
    Then SLI tạo đơn của nhóm được bảo vệ đạt ít nhất 99,9%
    And từng tenant được bảo vệ đạt ít nhất 99,9%
    And sự kiện tốt hoàn thành đúng trong hai giây
    And các lần vượt hạn mức bị từ chối theo hợp đồng
    And không có đơn sai tenant hoặc hiệu ứng tạo đơn trùng
    And tài nguyên không vượt giới hạn cấu hình đã công bố
~~~

Hồ sơ thử cần lưu phiên bản ứng dụng, cấu hình bảo vệ, số replica, dữ liệu thử, trạng thái cache, cách phát tải và lịch gây nhiễu. Bộ phát tải phải chứng minh nó thực sự tạo đủ tải và không tự trở thành nút thắt.

Phải đo cả thời gian có gây nhiễu và thời gian sau đó. Trung bình toàn bài thử có thể che một khoảng gián đoạn nặng. Nếu thiếu dữ liệu hoặc phát tải thấp hơn mức đã cam kết đáng kể, kết luận phải nêu chưa đủ bằng chứng thay vì đánh dấu đạt.

## 10. Vận hành khi đang bị gây gián đoạn

Yêu cầu vận hành cần làm rõ người có quyền điều chỉnh hạn mức, điều kiện kích hoạt chế độ suy giảm, cách liên hệ lớp bảo vệ phía trước và tiêu chí kết thúc ứng phó.

Một quy trình có thể cần các bước sau:

1. Xác nhận tác động nghiệp vụ và nhóm người dùng bị ảnh hưởng bằng nhiều nguồn đo.
2. Xác định tài nguyên đang chạm giới hạn và nơi lưu lượng bị nghẽn.
3. Kích hoạt biện pháp đã được phê duyệt cho đúng phạm vi; ghi lại cấu hình và thời điểm.
4. Theo dõi chặn nhầm, trạng thái quyền và công việc còn chạy phía sau phản hồi.
5. Kiểm tra giao dịch có kết quả chưa rõ, nguy cơ gửi lại và nhu cầu đối soát.
6. Gỡ các hạn chế tạm thời theo tiêu chí phục hồi; xác nhận không còn backlog gây quá tải tiếp diễn.
7. Lưu bằng chứng và cập nhật yêu cầu từ những thiếu hụt đã quan sát.

Giao diện quản trị và đường quan sát cần đủ khả năng hoạt động để điều khiển hệ thống khi tải chính gặp sự cố. Chúng vẫn phải giữ xác thực mạnh và phân quyền; không mở đường quản trị công khai không kiểm soát để giải quyết khó khăn truy cập.

Sự kiện log nên có mã tương quan, loại thao tác, giai đoạn từ chối, quy tắc áp dụng và nhóm tài nguyên bị giới hạn. Tránh dùng định danh có số lượng không giới hạn làm nhãn của mọi metric; giữ thông tin truy vết chi tiết ở nơi có kiểm soát truy cập và chính sách lưu phù hợp.

Không tăng độ chi tiết log không giới hạn trong lúc đang cạn tài nguyên. Log phục vụ ứng phó cũng cần hạn mức và cách xử lý nghẽn, đồng thời không được âm thầm làm mất audit bắt buộc.

## 11. Truy vết yêu cầu tới kiến trúc và vòng đời phát triển

| Rủi ro | Yêu cầu liên quan | Quyết định kiến trúc cần đánh giá | Bằng chứng |
|---|---|---|---|
| Tenant gây quá tải làm tenant khác ngừng tạo đơn | SR-DOS-001, SR-DOS-002 | Nguồn danh tính, hạn mức và phân bổ tài nguyên. | SLI theo tenant, kết quả phân tán qua replica. |
| Báo cáo chiếm hết worker hoặc kết nối | SR-DOS-003 | Cô lập công việc, hàng đợi hữu hạn và xử lý hủy. | Số chạy, số chờ, tài nguyên và giao dịch trọng yếu. |
| Kết nối hoặc dữ liệu giữ tài nguyên lâu | SR-DOS-004 | Giới hạn tại biên, deadline và dọn trạng thái. | Phép thử nhận chậm, quá cỡ và lặp nhiều lần. |
| Quá tải dẫn tới bỏ kiểm tra quyền | SR-DOS-005 | Chính sách lỗi phụ thuộc và hiệu lực cache quyền. | Ca thử quyền, thu hồi và phản hồi muộn. |
| Mở rộng hoặc retry kéo dài thiệt hại | SR-DOS-006 | Trần tài nguyên, giới hạn retry và xử lý backlog. | Diễn biến tài nguyên trong và sau gây nhiễu. |
| Phản ứng chậm hoặc thiếu bằng chứng | SR-DOS-007 | Điểm đo, cảnh báo và kênh vận hành. | Mốc phát hiện, cảnh báo, thay đổi cấu hình và kết quả. |

Khi phân tích nghiệp vụ, xác định chức năng trọng yếu và mức suy giảm chấp nhận được. Khi mô hình hóa đe dọa, xem xét cả tài khoản hợp lệ bị lạm dụng và tài nguyên dùng chung.

Khi thiết kế, kiểm tra các giới hạn có thực sự áp dụng trên toàn phạm vi cam kết hay chỉ trên một tiến trình. Khi phát triển, bảo đảm đường xử lý lỗi không tạo thêm công việc không giới hạn hoặc làm yếu kiểm soát bảo mật.

Khi nghiệm thu, dùng phép thử tương ứng với từng yêu cầu. Khi vận hành, đánh giá lại yêu cầu sau thay đổi endpoint, dữ liệu, cách tính hạn mức, số replica, cấu trúc tenant hoặc phụ thuộc. Một ngưỡng phù hợp với tải cũ có thể không còn bảo vệ được hành trình mới.

## 12. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Có WAF nên chống được DoS.” | Chưa chứng minh mọi điểm nghẽn và lớp tài nguyên được bảo vệ. | Nêu kịch bản, năng lực cần giữ và bằng chứng cho từng phạm vi. |
| “Chặn được nhiều request là đạt.” | Có thể chặn nhầm người dùng hợp lệ. | Đo thành công nghiệp vụ và tác động theo tenant. |
| “Giới hạn theo IP là đủ.” | Người dùng có thể chung nguồn; nguồn gây tải có thể phân tán. | Kết hợp danh tính tin cậy, hạn mức và giới hạn tài nguyên phù hợp. |
| “Đăng nhập rồi thì được dùng không giới hạn.” | Chức năng hợp lệ vẫn có thể bị lạm dụng để làm cạn tài nguyên. | Kiểm soát chi phí và mức dùng sau xác thực. |
| “Thêm replica sẽ giải quyết được.” | Phụ thuộc hoặc ngân sách có thể chạm giới hạn trước. | Đặt trần và kiểm chứng toàn đường xử lý. |
| “Hàng đợi càng lớn càng an toàn.” | Có thể tăng bộ nhớ, độ trễ và lượng công việc không còn hữu ích. | Giới hạn số chờ, thời gian chờ và hành vi khi đầy. |
| “Timeout rồi nghĩa là công việc đã dừng.” | Tác vụ có thể tiếp tục giữ tài nguyên hoặc đã ghi dữ liệu. | Theo dõi hủy, trạng thái thực thi và kết quả nghiệp vụ. |
| “Bộ đếm lỗi thì bỏ hạn mức tạm.” | Lỗi kiểm soát có thể mở đường nhận tải vô hạn. | Đặc tả chính sách khi bộ đếm không khả dụng và kiểm thử nó. |
| “Bài thử ứng dụng chứng minh chịu mọi DDoS.” | Chưa xét bão hòa đường truyền và đường truy cập khác. | Giữ kết luận trong đúng phạm vi đã được kiểm chứng. |

## 13. Bài tập áp dụng

Một nền tảng thi trực tuyến cần bảo vệ bắt đầu bài thi, lưu câu trả lời và nộp bài khi lưu lượng tăng mạnh. Một nhóm tài khoản hợp lệ có thể liên tục gọi chức năng xuất kết quả tổng hợp tốn tài nguyên.

Hãy đặc tả:

1. Hành trình trọng yếu, người dùng được bảo vệ và một sự kiện tốt cho từng hành trình.
2. Điều kiện tải hợp lệ, tải gây nhiễu và ranh giới hạ tầng nằm trong cam kết.
3. Hạn mức theo chủ thể tin cậy, giới hạn đồng thời và hành vi khi trạng thái hạn mức không truy cập được.
4. Cách cô lập xuất kết quả khỏi lưu câu trả lời và nộp bài.
5. Chế độ suy giảm vẫn giữ xác thực, quyền và tính toàn vẹn bài làm.
6. Ca kiểm thử gồm chặn nhầm, tác vụ chưa dừng sau timeout và khôi phục sau khi ngừng gây nhiễu.
7. Bằng chứng đủ để phân biệt hệ thống “đã chặn lưu lượng” với hệ thống “vẫn phục vụ đúng người học hợp lệ”.

Với thao tác nộp bài, cần xử lý riêng trường hợp phản hồi mất sau khi đã lưu. Yêu cầu bảo vệ tài nguyên phải đi cùng hợp đồng chống nộp trùng và khả năng xác định trạng thái bài làm; một phản hồi lỗi nhanh không đủ chứng minh người học đã được phục vụ đúng.

