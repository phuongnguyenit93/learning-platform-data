# Thiết lập cảnh báo chi phí và quy trình dọn tài nguyên thực hành

Một môi trường OCI phục vụ học tập có thể phát sinh chi phí sau khi bạn đã đóng trình duyệt hoặc dừng máy ảo. Volume, backup, database, load balancer và các dịch vụ khác có vòng đời riêng. Nếu chỉ nhìn trạng thái Compute, người học dễ bỏ sót những thành phần vẫn tồn tại.

Cảnh báo chi phí giúp phát hiện sớm mức sử dụng vượt dự kiến; quy trình dọn tài nguyên giúp kết thúc những nguồn phát sinh chi phí không còn cần thiết. Hai việc này cần được chuẩn bị trước khi bắt đầu lab.

Bài học hướng dẫn xây dựng ngân sách, chọn ngưỡng cảnh báo, xác định cách phản ứng và kiểm chứng việc dọn môi trường Oracle Cloud Infrastructure. Các con số trong ví dụ là ngân sách giả định, không phải báo giá dịch vụ OCI.

## 1. Mục tiêu và nguyên tắc

Sau bài học, bạn có thể:

- Thiết kế phạm vi theo dõi chi phí cho một môi trường thực hành.
- Tạo budget và các quy tắc cảnh báo phù hợp.
- Phân biệt chi phí thực tế, chi phí dự báo và giới hạn cấp phát.
- Phản ứng khi nhận cảnh báo mà không xóa nhầm dữ liệu hoặc tài nguyên dùng chung.
- Dọn tài nguyên theo quan hệ phụ thuộc.
- Đối chiếu trạng thái hạ tầng với dữ liệu chi phí sau khi dọn.

Ba nguyên tắc cần nhớ:

1. **Budget là công cụ giám sát chi tiêu, không phải bảo đảm ngừng tính phí tại một số tiền cố định.**
2. **Stop một tài nguyên không đồng nghĩa toàn bộ hệ thống liên quan đã được dọn.**
3. **Xóa tài nguyên không xóa khoản chi phí đã phát sinh trước đó.**

Mọi thao tác xóa thực tế cần nằm trong phạm vi lab được giao và bảo đảm dữ liệu cần giữ đã được xử lý phù hợp.

## 2. Hiểu đúng các công cụ kiểm soát

### 2.1. Budget, quota và quy trình dọn khác nhau

| Công cụ hoặc cơ chế | Giúp làm gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| Budget | Theo dõi chi tiêu trong phạm vi và kỳ được cấu hình | Không tự tạo trần thanh toán cứng |
| Budget alert rule | Thông báo khi điều kiện chi phí thực tế hoặc dự báo được đáp ứng | Không mặc nhiên dừng hay xóa tài nguyên |
| Cost Analysis | Phân tích chi phí theo chiều dữ liệu được hỗ trợ | Không tự thu hồi tài nguyên |
| Compartment quota | Hạn chế việc cấp phát theo tài nguyên và phạm vi áp dụng | Không chặn mọi loại chi phí ở một số tiền cụ thể |
| Service limit | Giới hạn sử dụng dịch vụ theo điều kiện của OCI | Không phải ngân sách tiền tệ |
| IAM | Giới hạn người được tạo, đổi hoặc xóa tài nguyên | Không tự tính chi phí hoặc bảo đảm không phát sinh phí |
| Lịch và quy trình dọn lab | Kết thúc sử dụng, thu hồi tài nguyên không cần nữa | Chỉ có hiệu lực nếu thực hiện và kiểm chứng |

Một tài nguyên được cấp phát hợp lệ trong quota vẫn có thể phát sinh chi phí. Một budget đã vượt ngưỡng cũng không có nghĩa OCI sẽ chấm dứt tài nguyên ngay.

### 2.2. Cảnh báo không phải cơ chế phản ứng tức thời

Dữ liệu sử dụng, dữ liệu chi phí và việc đánh giá cảnh báo có thể có độ trễ. Không lập kế hoạch dựa trên giả định cảnh báo đến ngay khi phát sinh thêm một khoản phí.

Hệ quả:

- Nên đặt ngưỡng sớm hơn mức chi tiêu tối đa mà bạn chấp nhận.
- Cần dành khoảng dự phòng cho độ trễ và thời gian người phụ trách phản ứng.
- Với tài nguyên có tốc độ phát sinh chi phí cao, phải kiểm tra trước khi tạo và chủ động theo dõi trong buổi lab.
- Chưa nhận email không chứng minh chi phí bằng không.

Một hệ thống tự động hóa phản ứng theo cảnh báo, nếu được xây dựng riêng, vẫn có độ trễ và có thể gặp lỗi quyền hoặc lỗi API. Không xem nó là cam kết hóa đơn sẽ dừng chính xác tại ngưỡng.

### 2.3. Free Tier và credit không thay thế kế hoạch chi phí

Không suy ra “đang dùng tài khoản học tập” đồng nghĩa mọi thao tác đều miễn phí. Khả năng miễn phí, điều kiện sử dụng credit và cách chuyển sang tài nguyên tính phí phải được kiểm tra cho đúng tài khoản và dịch vụ.

Các tình huống dễ nhầm gồm:

- Chọn cấu hình khác với cấu hình nằm trong quyền lợi miễn phí.
- Tạo thêm volume, backup hoặc dịch vụ ngoài phạm vi dự kiến.
- Dùng tài nguyên tại region hoặc cấu hình không phù hợp với điều kiện quyền lợi.
- Tiếp tục vận hành sau giai đoạn ưu đãi hoặc khi điều kiện tài khoản thay đổi.

Trước lab, cần xác nhận cấu hình và điều kiện tính phí hiện hành. Bài học không dùng một mức giá hoặc một ưu đãi cố định để suy ra chi phí của mọi tenancy.

## 3. Chuẩn bị phạm vi lab trước khi tạo tài nguyên

### 3.1. Ưu tiên một compartment riêng

Một compartment lab riêng giúp phân quyền, kiểm kê và đối chiếu chi phí dễ hơn. Nếu được tổ chức cấp sẵn compartment, sử dụng đúng phạm vi đó thay vì tự tạo cấu trúc mới.

Ví dụ kế hoạch:

~~~text
Compartment lab: learning-lab
Chủ sở hữu:     người học hoặc nhóm lab
Region:        region đã được giao
Thời gian:     một buổi thực hành có giờ kết thúc
Tài nguyên:    một instance, volume và mạng phục vụ bài lab
~~~ 

Tên trong ví dụ không phải yêu cầu tạo tài nguyên thật.

Khi chọn phạm vi budget, cần đọc rõ cách công cụ áp dụng cho compartment và nhánh con. Không giả định một lựa chọn ở compartment cha chỉ theo dõi đúng những tài nguyên trực tiếp bên trong nó.

Với lab đơn giản, dùng một compartment lá có phạm vi rõ ràng sẽ giảm nguy cơ lẫn chi phí của nhóm khác.

### 3.2. Phân biệt tài nguyên được tạo mới và tài nguyên dùng chung

Trước khi bắt đầu, lập hai nhóm:

| Nhóm | Ví dụ | Quy tắc cuối lab |
| --- | --- | --- |
| Do lab tạo và sở hữu | Instance thử nghiệm, volume riêng, bucket tạm | Đánh giá thu hồi theo kế hoạch |
| Dùng chung hoặc được mượn | VCN dùng chung, subnet lớp học, logging tập trung | Giữ lại; chỉ gỡ phần của lab khi được phép |

Một instance nằm trong subnet dùng chung không làm cho toàn bộ subnet trở thành tài nguyên được phép xóa.

Tương tự, có quyền xóa không đồng nghĩa mọi tài nguyên đang nhìn thấy đều thuộc phạm vi dọn của bạn.

### 3.3. Lập sổ tài nguyên

Nên lưu các trường sau trong hệ thống quản lý lab được phép:

| Trường | Mục đích |
| --- | --- |
| Lab ID | Nhóm các tài nguyên của cùng buổi thực hành |
| Loại tài nguyên và OCID | Nhận diện chính xác |
| Region và compartment | Xác định nơi kiểm kê |
| Chủ sở hữu | Người quyết định giữ hoặc thu hồi |
| Giờ hết hạn | Mốc phải xem xét dọn |
| Phụ thuộc | Xác định thứ tự thu hồi |
| Dữ liệu cần giữ | Tránh xóa mất kết quả quan trọng |
| Dùng chung hay riêng | Tránh phạm vi dọn quá rộng |
| Trạng thái sau lab | Đã xóa, giữ có lý do hoặc chờ xử lý |

Có thể dùng tag nếu tenancy đã có quy ước, chẳng hạn labId, owner và expiresAt. Tag hỗ trợ kiểm kê; bản thân tag hết hạn không tự chạy thao tác xóa.

Tag để nhận diện tài nguyên cũng không mặc nhiên là cost-tracking tag được cấu hình cho báo cáo chi phí. Nếu muốn dùng ngân sách theo tag, cần đáp ứng yêu cầu của cơ chế cost tracking và kiểm tra dữ liệu thực tế.

## 4. Thiết kế budget cho môi trường thực hành

### 4.1. Xác định số tiền và kỳ theo dõi

Giả sử ngân sách học tập là **20 đơn vị tiền tệ theo đồng tiền billing của tài khoản trong một tháng**.

Con số này chỉ minh họa cách tính ngưỡng. Người học phải chọn ngân sách dựa trên:

- Tài nguyên và cấu hình định dùng.
- Thời gian hoạt động dự kiến.
- Lưu trữ, backup và dịch vụ phụ trợ.
- Mức chi tiêu đã phát sinh trong kỳ.
- Khả năng chấp nhận chi phí của người sở hữu tài khoản.

Không nhập một con số theo VND nhưng hiểu giao diện đang dùng USD, hoặc ngược lại. Kiểm tra đơn vị tiền tệ hiển thị trước khi lưu.

Budget theo kỳ không phải bộ đếm tự reset chi phí của mỗi lần làm lab. Nếu dùng chung một budget tháng, buổi thực hành sau phải tính cả phần đã sử dụng trước đó.

### 4.2. Chọn phạm vi phù hợp

Các phương án thường cần cân nhắc:

- Theo dõi toàn tenancy để thấy tổng chi tiêu.
- Theo dõi compartment dành cho lab.
- Theo dõi theo cost-tracking tag khi môi trường đã thiết lập phù hợp.

Không chọn phạm vi chỉ vì tên có vẻ đúng. Đối chiếu compartment OCID, cấu trúc con và tập tài nguyên thực sự được cộng vào dữ liệu chi phí.

Có thể dùng một budget toàn tài khoản để cảnh báo tổng và một budget lab để khoanh vùng, nếu tính năng và quyền cho phép. Khi đó, hiểu rằng hai budget có thể cùng phản ánh một khoản chi; không cộng các thông báo thành hai lần sử dụng dịch vụ.

### 4.3. Ngưỡng minh họa

Với budget B = 20:

| Loại cảnh báo | Ngưỡng | Giá trị minh họa | Mục đích |
| --- | ---: | ---: | --- |
| Chi phí thực tế | 50% B | 10 | Kiểm tra tốc độ sử dụng |
| Chi phí thực tế | 80% B | 16 | Hạn chế tạo mới, rà soát tài nguyên |
| Chi phí thực tế | 100% B | 20 | Thực hiện kế hoạch xử lý đã thống nhất |
| Chi phí dự báo | 100% B | 20 cho cả kỳ dự báo | Phát hiện khả năng vượt trước khi chi thực tế chạm ngưỡng |

Chi phí dự báo không phải chi phí đã phát sinh. Nó phụ thuộc dữ liệu và phương pháp dự báo của dịch vụ; có thể chưa đủ ý nghĩa khi dữ liệu ít hoặc mức sử dụng thay đổi đột ngột.

Ngưỡng 100% không nên là cảnh báo duy nhất. Nếu nó đến sau khi số tiền đã được ghi nhận, bạn vẫn cần thời gian kiểm tra và dọn tài nguyên.

## 5. Thiết lập budget và cảnh báo trong Console

### 5.1. Kiểm tra quyền và ngữ cảnh

Trước khi cấu hình:

1. Xác nhận đúng tenancy và tài khoản.
2. Mở nhóm quản lý chi phí/billing và chức năng Budgets tương ứng.
3. Xác nhận danh tính được phép xem dữ liệu chi phí, quản lý budget và quy tắc cảnh báo trong phạm vi cần thiết.
4. Nếu tài khoản học viên không có quyền billing, phối hợp với người sở hữu tài khoản hoặc người quản trị được giao.

Quyền tạo Compute trong compartment lab không tự bảo đảm có quyền đọc hoặc quản lý budget. Không cần cấp quyền quản trị toàn tenancy chỉ để hoàn thành bài học.

Tên menu và vị trí trường có thể thay đổi theo giao diện. Hãy dựa vào chức năng và phạm vi hiển thị khi thực hiện.

### 5.2. Tạo budget

Trong chức năng tạo budget, kiểm tra các thông tin tương đương:

- Tên dễ nhận diện, ví dụ lab-monthly-budget.
- Phạm vi tenancy, compartment hoặc tag phù hợp.
- Compartment hoặc giá trị tag chính xác.
- Số tiền và đồng tiền hiển thị.
- Kỳ theo dõi và thời điểm áp dụng theo tùy chọn được hỗ trợ.
- Mô tả chủ sở hữu và mục tiêu sử dụng.

Sau khi lưu, mở lại budget và đối chiếu cấu hình. Đừng chỉ dựa vào thông báo tạo thành công.

Budget không yêu cầu tạo một instance để “kích hoạt”. Không tạo tài nguyên tính phí để kiểm tra xem budget có tồn tại hay không.

### 5.3. Tạo alert rule

Với mỗi ngưỡng đã thiết kế:

1. Chọn chi phí thực tế hoặc chi phí dự báo.
2. Chọn cách biểu diễn ngưỡng mà giao diện hỗ trợ, chẳng hạn phần trăm budget hoặc giá trị tiền.
3. Nhập đúng số và kiểm tra đơn vị.
4. Khai báo người nhận bằng cơ chế gửi cảnh báo mà budget cung cấp.
5. Thêm mô tả phản ứng nếu giao diện có trường phù hợp.
6. Lưu và đọc lại rule.

Một lỗi phổ biến là nhập 80 và không kiểm tra đang chọn phần trăm hay tiền. Hai cấu hình đó có ý nghĩa khác nhau.

Nếu rule hỗ trợ danh sách email người nhận, kiểm tra địa chỉ và cách phân tách theo yêu cầu của giao diện. Ưu tiên kênh được người sở hữu tài khoản theo dõi thường xuyên.

### 5.4. Xác minh đường nhận cảnh báo

Cần kiểm tra:

- Rule đã được lưu và áp dụng cho đúng budget chưa.
- Người nhận có đúng không.
- Kênh nhận có yêu cầu bước xác nhận hoặc điều kiện riêng nào không.
- Hộp thư có lọc hoặc chặn thông báo không.
- Người phụ trách có biết phải phản ứng thế nào không.
- Có người thay thế nếu người chính không theo dõi được không.

Nếu cơ chế đang dùng hỗ trợ gửi thử hoặc có cách kiểm chứng cấu hình, sử dụng theo quyền được giao. Nếu không có, ghi nhận giới hạn xác minh thay vì chủ động tiêu tiền để ép vượt ngưỡng.

Không mặc định rằng tạo một Notifications topic là đã kết nối nó với budget. Nếu triển khai thêm Events, Notifications, Functions hoặc một quy trình ngoài, phải cấu hình và kiểm tra đường tích hợp đó riêng.

### 5.5. Ghi lại trạng thái hoàn thành

Một budget được chuẩn bị xong nên có:

~~~text
Phạm vi:             đã xác minh
Số tiền và kỳ:       đã xác minh
Rule thực tế:        có các ngưỡng đã chọn
Rule dự báo:         có nếu phù hợp và được hỗ trợ
Người nhận:          đã đối chiếu
Quy trình phản ứng:  đã có người chịu trách nhiệm
Giới hạn:            không chặn chi tiêu tự động
~~~

Nếu chưa xác minh được việc nhận thông báo, không báo rằng toàn bộ chuỗi cảnh báo đã hoạt động chỉ vì giao diện có một rule.

## 6. Phản ứng khi nhận cảnh báo

### 6.1. Mức 50%: kiểm tra mức sử dụng

Khi chi phí thực tế đạt ngưỡng sớm:

- Mở Cost Analysis hoặc công cụ chi phí tương ứng.
- Chọn đúng khoảng thời gian.
- Lọc về compartment hoặc phạm vi của budget.
- Phân tích theo dịch vụ, region hoặc tài nguyên khi dữ liệu hỗ trợ.
- Đối chiếu với sổ tài nguyên lab.
- Kiểm tra có tài nguyên nào bị tạo trùng hoặc chạy ngoài lịch không.

Không cần xóa ngay mọi tài nguyên. Trước hết xác định nguồn phát sinh và mức chi tiêu có phù hợp với kế hoạch hay không.

### 6.2. Mức 80% hoặc dự báo vượt: giảm rủi ro vượt ngân sách

Thực hiện:

1. Tránh tạo thêm tài nguyên chưa cần thiết.
2. Kết thúc sớm những phần lab đã hoàn thành.
3. Thu hồi tài nguyên tạm không có dữ liệu cần giữ.
4. Xem lại tài nguyên chạy liên tục và tác vụ định kỳ.
5. Xác nhận có đủ dư địa cho độ trễ dữ liệu và thời gian dọn.
6. Trao đổi với người sở hữu tài khoản nếu cần tiếp tục.

Nếu chi phí chủ yếu đến từ lưu trữ, dừng Compute có thể không giải quyết được phần chính. Phải xử lý đúng nhóm dịch vụ đang phát sinh chi phí.

### 6.3. Mức 100%: thực hiện kế hoạch đã thống nhất

Ngưỡng này cần một quyết định rõ:

- Kết thúc lab và dọn tài nguyên riêng của lab; hoặc
- Tiếp tục với ngân sách được người chịu trách nhiệm chấp nhận.

Không đơn giản tăng budget để làm cảnh báo biến mất mà không hiểu nguyên nhân. Thay đổi ngưỡng không làm giảm khoản chi đã phát sinh.

Khi dọn, vẫn phải bảo vệ dữ liệu cần giữ và tài nguyên dùng chung. Một email vượt ngưỡng không phải quyền xóa mọi thứ trong tenancy.

### 6.4. Lưu dấu vết xử lý

Ghi nhận ngắn gọn:

~~~text
Thời điểm nhận cảnh báo
Budget và ngưỡng liên quan
Khoảng thời gian chi phí đang xem
Dịch vụ hoặc tài nguyên đóng góp chính
Hành động đã thực hiện
Tài nguyên cố ý giữ lại và người chịu trách nhiệm
Thời điểm kiểm tra lại
~~~

Không cần lưu thông tin xác thực hay toàn bộ header API để theo dõi việc xử lý chi phí.

## 7. Chuẩn bị dọn tài nguyên cuối lab

### 7.1. Chốt phạm vi trước khi xóa

Dọn tài nguyên bắt đầu bằng việc tạo một danh sách có thể kiểm tra, không phải bấm xóa lần lượt những gì nhìn thấy.

Với mỗi tài nguyên, trả lời:

1. Có thuộc đúng lab không?
2. Có đúng OCID, region và compartment không?
3. Có dùng chung không?
4. Có dữ liệu hoặc kết quả phải giữ không?
5. Có tài nguyên nào đang phụ thuộc vào nó không?
6. Xóa có tạo, giữ lại hoặc ảnh hưởng tới thành phần nào khác không?
7. Ai chịu trách nhiệm xác nhận hoàn tất?

Giữ lại tài nguyên phải là một quyết định có lý do, thời hạn và người sở hữu. Không để trạng thái “giữ tạm” tồn tại vô thời hạn.

### 7.2. Tạo sơ đồ phụ thuộc đơn giản

~~~mermaid
flowchart TD
    A["Ứng dụng hoặc tác vụ lab"] --> B["Compute hoặc database"]
    B --> C["Volume / dữ liệu / backup"]
    B --> D["VNIC hoặc endpoint"]
    E["Load balancer của lab"] --> D
    D --> F["Subnet"]
    F --> G["VCN và các thành phần mạng liên quan"]
~~~

Mũi tên thể hiện sự sử dụng hoặc phụ thuộc ở mức khái niệm, không thay cho sơ đồ chi tiết của từng dịch vụ.

Thường cần xử lý các thành phần sử dụng tài nguyên trước khi xóa tài nguyên mà chúng phụ thuộc. Với thành phần dùng chung, chỉ gỡ phần liên quan đến lab và giữ nguyên phần được giao giữ lại.

### 7.3. Ngừng các cơ chế có thể tạo lại tài nguyên

Trước khi dọn, kiểm tra:

- Lịch chạy tác vụ.
- Instance pool hoặc autoscaling.
- Pipeline triển khai.
- Công cụ IaC đang quản lý tài nguyên.
- Function hoặc automation có thể cấp phát lại.
- Tác vụ ghi dữ liệu, tạo backup hoặc đồng bộ.

Nếu xóa một instance nhưng pool hoặc pipeline tạo lại nó, chi phí và tài nguyên có thể tiếp tục xuất hiện.

Với tài nguyên do IaC quản lý, nên dùng quy trình thu hồi của cấu hình đó khi phù hợp, sau khi xem kế hoạch thay đổi. Xóa thủ công có thể làm state lệch thực tế hoặc khiến lần triển khai sau tạo lại.

## 8. Quy trình dọn theo từng nhóm tài nguyên

### 8.1. Bước 1: bảo vệ kết quả cần giữ

Xác định dữ liệu cần lưu trước khi thực hiện thao tác phá hủy:

- Mã nguồn và cấu hình có thể tái tạo môi trường.
- Kết quả bài tập cần nộp.
- Dữ liệu database cần xuất hoặc backup.
- Object hoặc file cần chuyển sang nơi lưu được cho phép.

Backup không phải mặc nhiên miễn phí hoặc được xóa cùng tài nguyên gốc. Nếu giữ backup, ghi rõ thời hạn và người chịu trách nhiệm.

Nếu không có dữ liệu cần giữ, cũng nên ghi nhận điều đó để tránh do dự hoặc hiểu nhầm khi kiểm tra sau.

### 8.2. Bước 2: xử lý workload và Compute

- Kết thúc các tác vụ đang chạy theo cách phù hợp.
- Gỡ instance khỏi những thành phần điều phối cần thiết.
- Xác nhận instance không thuộc nhóm sẽ tự tạo lại.
- Nếu lab đã kết thúc hoàn toàn, đánh giá terminate thay vì chỉ stop.
- Đọc kỹ lựa chọn giữ hay xóa boot volume và các thành phần liên quan.
- Chờ thao tác đạt kết quả cuối cùng, không chỉ chờ thông báo tiếp nhận.

Không giả định terminate instance sẽ xóa mọi block volume đã gắn. Cũng không giả định mọi boot volume luôn được giữ lại; tác động phụ thuộc lựa chọn và quy tắc của thao tác.

Sau đó, kiểm tra riêng danh sách volume và attachment trong phạm vi lab.

### 8.3. Bước 3: xử lý database

Với dịch vụ cơ sở dữ liệu:

1. Xác nhận đúng loại dịch vụ và đúng database của lab.
2. Chốt yêu cầu giữ dữ liệu.
3. Ngừng các ứng dụng hoặc tác vụ còn truy cập.
4. Đọc các lựa chọn xóa, backup cuối cùng và thời gian lưu theo dịch vụ.
5. Thực hiện thu hồi theo quyền và kế hoạch.
6. Kiểm tra tài nguyên, backup và thành phần liên quan còn giữ lại.

Không dùng một quy trình xóa giống nhau cho mọi dịch vụ database Oracle. Cấu trúc tài nguyên, lựa chọn dừng và cơ chế giữ backup có thể khác nhau.

Việc dừng database, nếu dịch vụ hỗ trợ, cũng phải được đối chiếu với những thành phần vẫn phát sinh chi phí.

### 8.4. Bước 4: xử lý lưu trữ

| Loại | Cần kiểm tra |
| --- | --- |
| Boot volume | Có còn sau khi terminate instance không, có cần giữ không |
| Block volume | Còn attachment, dữ liệu hoặc nhóm volume liên quan không |
| Volume backup | Có bản tự động hoặc thủ công cần thu hồi theo kế hoạch không |
| Object Storage | Object, phiên bản cũ và phần upload chưa hoàn tất nếu có |
| Bucket | Có dữ liệu, chính sách hoặc điều kiện ngăn xóa không |
| File Storage | Mount target, export và filesystem theo quan hệ dịch vụ |

Với bucket bật versioning, xóa object hiện tại có thể chưa loại bỏ các phiên bản dữ liệu cũ. Cần kiểm tra cơ chế versioning, delete marker và những mục còn lưu.

Nếu retention rule hoặc cơ chế bảo vệ dữ liệu đang có hiệu lực, không cố vượt qua để hoàn thành dọn. Ghi nhận lý do, chi phí cần theo dõi và người quản lý thời hạn.

Không xóa bản backup duy nhất của dữ liệu cần giữ chỉ vì nó chưa được ghi vào sổ lab.

### 8.5. Bước 5: xử lý endpoint và mạng riêng của lab

Sau khi workload không còn sử dụng:

- Thu hồi load balancer hoặc endpoint riêng do lab tạo nếu không cần giữ.
- Kiểm tra public IP được giữ riêng và xác định có cần giải phóng không.
- Gỡ những attachment hoặc kết nối chỉ phục vụ lab theo đúng quy trình dịch vụ.
- Xóa subnet riêng khi không còn tài nguyên phụ thuộc.
- Xử lý gateway, route và các thành phần mạng liên quan trước khi xóa VCN riêng, theo điều kiện OCI áp dụng.

Không xóa VCN hoặc subnet dùng chung của lớp học. Không suy ra mọi thành phần mạng đều có cùng cơ chế tính phí; cần đối chiếu dịch vụ và cấu hình thực tế.

Nếu VCN không xóa được, đọc lỗi phụ thuộc và xác định tài nguyên đang giữ liên kết. Không xóa hàng loạt mọi đối tượng trong compartment để vượt qua lỗi.

### 8.6. Bước 6: rà soát dịch vụ phụ trợ

Những tài nguyên dễ bị bỏ sót:

- Log và nơi lưu log do lab tạo.
- Backup theo lịch hoặc dữ liệu lưu trữ lâu dài.
- Function, image hoặc artifact trong registry.
- Hệ thống giám sát, agent hoặc tác vụ phát sinh dữ liệu.
- Tài nguyên của các dịch vụ phân tích hoặc dữ liệu được tạo trong phần mở rộng.
- Secret, key hoặc cấu hình còn giữ theo chính sách của tổ chức.

Không xóa hạ tầng giám sát hoặc khóa mã hóa dùng chung. Với key và dữ liệu mã hóa, cần hiểu hậu quả trước khi thu hồi; thao tác đó có thể ảnh hưởng khả năng đọc dữ liệu được giữ lại.

Mục tiêu rà soát là kiểm kê đầy đủ, không phải mặc định mọi mục trên đều có phí trong mọi cấu hình.

## 9. Kiểm kê bằng CLI ở chế độ chỉ đọc

Các lệnh dưới đây là ví dụ học tập để liệt kê tài nguyên. Không có lệnh xóa trong phần này.

Giả sử PowerShell đã có các biến do người học chuẩn bị:

~~~powershell
$env:OCI_LAB_COMPARTMENT_OCID = "<ocid-compartment-lab>"
$env:OCI_LAB_REGION = "<region-lab>"
~~~

Liệt kê Compute instance trong một compartment và region:

~~~powershell
oci compute instance list --compartment-id $env:OCI_LAB_COMPARTMENT_OCID --region $env:OCI_LAB_REGION --all --output json
~~~

Liệt kê VCN trong cùng phạm vi:

~~~powershell
oci network vcn list --compartment-id $env:OCI_LAB_COMPARTMENT_OCID --region $env:OCI_LAB_REGION --all --output json
~~~

Ý nghĩa cần đọc đúng:

- --all lấy đầy đủ các trang kết quả của lệnh trong phạm vi đang truy vấn; không có nghĩa tất cả region hoặc tất cả compartment.
- Hai lệnh chỉ kiểm kê hai loại tài nguyên; không chứng minh volume, database hoặc bucket đã hết.
- Danh tính thiếu quyền có thể không cung cấp một bức tranh đầy đủ.
- Cần đọc trạng thái để phân biệt tài nguyên còn hoạt động, đang xử lý hoặc đã kết thúc.
- Không đưa private key hoặc token vào báo cáo kiểm kê.

Nếu lab từng sử dụng nhiều region hoặc compartment con, kiểm tra từng phạm vi liên quan bằng công cụ và quyền phù hợp. Không tự mở rộng phạm vi xóa dựa trên việc CLI có thể liệt kê tài nguyên của đội khác.

## 10. Xác minh sau khi dọn

### 10.1. Kiểm tra hạ tầng

Một lần kiểm tra hoàn tất cần đối chiếu:

- Tài nguyên thuộc diện xóa đã đạt trạng thái cuối cùng phù hợp.
- Không còn attachment hoặc phụ thuộc chưa xử lý.
- Không có automation tạo lại tài nguyên.
- Các tài nguyên giữ lại đều có lý do, chủ sở hữu và thời hạn.
- Đã kiểm tra các region và compartment từng sử dụng.
- Tài nguyên dùng chung vẫn ở trạng thái dự kiến.

Một số tài nguyên có thể vẫn xuất hiện dưới trạng thái đã kết thúc trong một thời gian. Cần đọc trạng thái và định danh, không chỉ đếm số dòng trong danh sách.

### 10.2. Kiểm tra chi phí sau đó

Mở lại công cụ chi phí sau khi dữ liệu có thời gian cập nhật, rồi đối chiếu với thời điểm dọn.

Cần hiểu:

- Chi phí tích lũy trong kỳ không trở về 0 sau khi xóa.
- Dữ liệu ghi nhận muộn có thể phản ánh sử dụng xảy ra trước lúc xóa.
- Một khoản điều chỉnh hoặc dữ liệu tổng hợp không tự chứng minh có tài nguyên mới.
- Nếu mức sử dụng tiếp tục phát sinh cho thời gian sau khi dọn, phải điều tra dịch vụ và tài nguyên liên quan.

Nên xem theo ngày hoặc khoảng thời gian phù hợp thay vì chỉ nhìn tổng tháng. Khi dữ liệu hỗ trợ, phân nhóm theo dịch vụ, region, compartment hoặc tài nguyên để xác định nguồn.

Không kết luận “không còn chi phí” chỉ vì danh sách Compute đã trống. Cũng không kết luận việc dọn thất bại chỉ vì tổng tháng vẫn còn số tiền đã phát sinh.

### 10.3. Giữ budget để theo dõi phần còn lại

Không xóa ngay budget chỉ để không nhận thêm email sau khi kết thúc lab. Giữ cơ chế theo dõi cho đến khi đã kiểm tra các thành phần còn lại và dữ liệu chi phí cập nhật đủ.

Nếu budget dùng chung cho nhiều buổi thực hành, cập nhật ghi chú và sổ tài nguyên thay vì coi mỗi lần dọn là một kỳ ngân sách mới.

Việc ngừng hoặc sửa alert rule cần theo trách nhiệm quản lý tài khoản và mục đích sử dụng tiếp theo.

## 11. Tình huống tổng hợp

### Bối cảnh

Một học viên đặt budget tháng là 20 đơn vị tiền tệ, có cảnh báo thực tế ở 50%, 80% và 100%, cùng cảnh báo dự báo vượt 100%.

Sau buổi lab, học viên stop instance rồi đóng trình duyệt. Vài ngày sau, nhận cảnh báo 80%.

### Phân tích

Stop instance không chứng minh môi trường đã được thu hồi. Cần kiểm tra:

- Boot volume và block volume có còn không.
- Có load balancer hoặc database chưa kết thúc không.
- Có backup hoặc dữ liệu lưu trữ đang được giữ không.
- Có tác vụ nào tạo lại tài nguyên không.
- Khoản chi đang thấy thuộc thời gian trước hay sau khi stop.
- Có tài nguyên ở region khác hoặc compartment con không.

### Xử lý

1. Mở dữ liệu chi phí của đúng kỳ và đúng phạm vi.
2. Xác định dịch vụ đóng góp chính, không đoán theo tài nguyên dễ nhìn nhất.
3. Đối chiếu sổ tài nguyên và những mục giữ lại.
4. Bảo vệ dữ liệu cần giữ.
5. Thu hồi tài nguyên riêng của lab theo quan hệ phụ thuộc.
6. Ghi thời điểm hoàn tất từng thao tác.
7. Theo dõi dữ liệu chi phí cập nhật sau đó.
8. Sửa quy trình kết thúc lab để lần sau có kiểm kê và bước xác minh.

Kết quả mong muốn không phải “email ngừng xuất hiện”, mà là nguồn phát sinh đã được hiểu và những tài nguyên không cần thiết đã được xử lý.

## 12. Bài thực hành có thể kiểm tra

Bài này có thể thực hiện bằng việc cấu hình budget và lập kế hoạch dọn trên môi trường đã có. Không cần tạo thêm tài nguyên để làm ví dụ.

### Phần A: chuẩn bị cảnh báo

- Xác định compartment hoặc phạm vi theo dõi.
- Chọn ngân sách và kỳ phù hợp với đồng tiền billing.
- Lập các ngưỡng thực tế và dự báo nếu phù hợp.
- Tạo budget và alert rule khi được giao quyền.
- Đọc lại cấu hình và người nhận.
- Ghi rõ phần nào đã xác minh, phần nào chưa kiểm tra được.

Nếu tài khoản không có quyền billing, người học lập kế hoạch và phối hợp với người quản lý; không tự nâng quyền.

### Phần B: lập danh sách dọn

Chọn một lab có sẵn và điền bảng:

| Tài nguyên | OCID/định danh | Giữ hay xóa | Phụ thuộc cần xử lý trước | Dữ liệu cần giữ | Người xác nhận |
| --- | --- | --- | --- | --- | --- |
| Instance của lab | Giá trị thực tế | Theo kế hoạch | Pool, ứng dụng hoặc tác vụ liên quan | Kết quả cần nộp | Chủ lab |
| Volume riêng | Giá trị thực tế | Theo kế hoạch | Attachment | Dữ liệu cần lưu | Chủ lab |
| VCN dùng chung | Giá trị thực tế | Giữ | Không thuộc phạm vi xóa | Không áp dụng | Đội mạng |

Bảng là mẫu lập kế hoạch, không phải chỉ thị xóa những tài nguyên đang có.

### Phần C: kiểm tra hoàn tất

Nếu đã được giao thực hiện dọn, hoàn tất theo kế hoạch được xác nhận và lưu bằng chứng:

- Trạng thái tài nguyên sau thao tác.
- Danh sách cố ý giữ lại.
- Phạm vi region và compartment đã kiểm tra.
- Thời điểm dọn.
- Thời điểm sẽ kiểm tra dữ liệu chi phí.
- Những blocker như thiếu quyền, phụ thuộc dùng chung hoặc dữ liệu chưa được phép xóa.

Không báo “đã dọn hết” khi vẫn còn các mục chưa kiểm tra.

## 13. Tự kiểm tra

### Câu 1: Budget 20 có bảo đảm hóa đơn không vượt 20 không?

Không. Budget và cảnh báo không phải trần thanh toán cứng. Dữ liệu có độ trễ, và tài nguyên không tự dừng chỉ vì rule đã đạt ngưỡng.

### Câu 2: Cảnh báo chi phí dự báo có nghĩa số tiền đó đã phát sinh chưa?

Chưa. Dự báo là ước lượng cho kỳ theo dõi dựa trên dữ liệu và phương pháp của dịch vụ. Cần xem riêng chi phí thực tế.

### Câu 3: Stop instance đã đủ để dọn một lab chưa?

Chưa. Cần kiểm tra volume, backup, database, load balancer và các thành phần khác, đồng thời quyết định instance cần giữ hay terminate.

### Câu 4: --all trong lệnh CLI có nghĩa kiểm kê cả tenancy không?

Không. Nó xử lý phân trang của lệnh trong phạm vi được chỉ định. Region, compartment, loại tài nguyên và quyền vẫn giới hạn kết quả.

### Câu 5: Sau khi xóa tài nguyên, tổng chi phí tháng còn nguyên có phải dọn thất bại không?

Không nhất thiết. Chi phí đã phát sinh vẫn được ghi nhận và dữ liệu có thể cập nhật muộn. Cần phân tích thời gian sử dụng và nguồn chi phí.

### Câu 6: Có thể xóa VCN dùng chung vì instance của mình từng chạy trong đó không?

Không. Phải phân biệt tài nguyên lab sở hữu với tài nguyên mượn hoặc dùng chung. Chỉ xử lý phần được giao quyền và đúng phạm vi.

### Câu 7: Tag expiresAt có tự xóa tài nguyên khi đến giờ không?

Không. Tag chỉ lưu thông tin nếu chưa có automation riêng thực thi chính sách đó. Automation cũng cần quyền, kiểm thử, kiểm soát phạm vi và giám sát kết quả.

## 14. Danh sách kiểm tra cho mỗi buổi lab

### Trước khi bắt đầu

- [ ] Đã xác nhận điều kiện tính phí của cấu hình định dùng.
- [ ] Có phạm vi compartment và region rõ ràng.
- [ ] Có budget và các ngưỡng cảnh báo phù hợp.
- [ ] Đã đối chiếu người nhận và trách nhiệm xử lý.
- [ ] Có giờ kết thúc, chủ sở hữu và sổ tài nguyên.
- [ ] Đã phân biệt tài nguyên riêng với tài nguyên dùng chung.

### Khi kết thúc

- [ ] Đã ngừng tác vụ có thể ghi dữ liệu hoặc tạo lại tài nguyên.
- [ ] Đã giữ kết quả và dữ liệu cần thiết.
- [ ] Đã thu hồi theo quan hệ phụ thuộc và lựa chọn đúng dữ liệu giữ lại.
- [ ] Đã kiểm tra riêng volume, backup, database, endpoint và dịch vụ phụ trợ.
- [ ] Đã kiểm tra các region và compartment từng sử dụng.
- [ ] Các mục giữ lại có lý do, thời hạn và người quản lý.
- [ ] Đã ghi nhận trạng thái cuối cùng và blocker còn lại.
- [ ] Có lịch kiểm tra lại dữ liệu chi phí sau khi cập nhật.

Một môi trường lab được quản lý tốt có cả tín hiệu cảnh báo sớm lẫn cách kết thúc rõ ràng. Người học cần biết khoản chi đến từ đâu, ai sẽ phản ứng khi vượt dự kiến, tài nguyên nào phải được thu hồi và bằng chứng nào cho thấy việc dọn đã hoàn tất.
