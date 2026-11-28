# Phân loại incident: từ tín hiệu vận hành đến yêu cầu phản ứng

## 1. Phân loại sự cố để đưa ra quyết định nào?

Trong vận hành, một cảnh báo có thể chỉ là một lần đăng nhập sai, một lỗi cấu hình hoặc dấu hiệu truy cập dữ liệu trái phép. Nếu mọi cảnh báo đều được gọi là sự cố nghiêm trọng, đội ứng cứu sẽ khó tập trung. Nếu chỉ công nhận sự cố khi đã biết đầy đủ nguyên nhân và tác động, việc ngăn chặn có thể quá muộn.

Phân loại incident là quá trình đánh giá và cập nhật cách mô tả sự cố để lựa chọn mức phản ứng phù hợp:

- Vấn đề thuộc nhóm nào?
- Tài sản, dữ liệu, người dùng hoặc tenant nào đã hoặc có thể bị ảnh hưởng?
- Tác động nghiêm trọng đến đâu?
- Kết luận đang dựa trên thông tin chắc chắn hay giả thuyết?
- Ai chịu trách nhiệm, việc gì phải bắt đầu và trong thời hạn nào?
- Khi nào phải đánh giá lại?

Trong module yêu cầu bảo mật, mục tiêu là biến những quyết định này thành quy tắc đủ rõ để triển khai, vận hành và kiểm chứng. Một câu “xử lý sự cố kịp thời” chưa cho biết khi nào đồng hồ bắt đầu chạy, ai phải xác nhận và điều gì xảy ra nếu không có người nhận.

Các mức và mốc thời gian trong bài là quy ước minh họa. Tổ chức cần chọn chính sách phù hợp với dịch vụ, tài sản, rủi ro và nghĩa vụ đã xác định.

## 2. Phân biệt event, alert và incident

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Event | Một sự kiện được ghi nhận trong hệ thống | Một lần đăng nhập thất bại hoặc thay đổi vai trò |
| Alert | Tín hiệu cần được xem xét theo một quy tắc phát hiện | Nhiều lần đăng nhập thất bại trong một khoảng thời gian |
| Incident | Tình huống thỏa tiêu chí sự cố của tổ chức và cần quy trình xử lý tương ứng | Tài khoản bị chiếm quyền và thực hiện thao tác trái phép |
| Finding hoặc điểm yếu | Vấn đề cần xử lý nhưng chưa chắc là sự cố đang xảy ra | Một quyền được cấp quá rộng được phát hiện trong rà soát |
| Giả thuyết điều tra | Cách giải thích cần được kiểm tra | Worker có thể đã dùng sai tenant khi tạo bản xuất |

Không phải mọi event đều tạo alert, và không phải mọi alert đều được xác nhận là incident.

Một điểm yếu chưa có bằng chứng khai thác vẫn có thể cần xử lý khẩn. Tuy nhiên, hồ sơ phải phân biệt việc phát hiện điểm yếu với việc đã quan sát một tác động trái phép.

Ngược lại, tổ chức có thể kích hoạt phản ứng sự cố với một nghi ngờ có cơ sở khi tác động tiềm tàng lớn, dù chưa xác nhận đầy đủ. Trạng thái “nghi ngờ” không đồng nghĩa được phép bỏ qua tín hiệu.

Một gián đoạn dịch vụ có thể là sự cố vận hành, sự cố bảo mật hoặc đồng thời cả hai tùy tiêu chí và tác động. Không cần biết danh tính kẻ tấn công mới được xem xét ảnh hưởng tới tính sẵn sàng.

## 3. Không gom mọi quyết định vào một nhãn

Một hồ sơ sự cố nên tách ít nhất các chiều sau:

| Chiều | Câu hỏi | Giá trị minh họa |
| --- | --- | --- |
| Loại sự cố | Điều gì đang bị xâm hại hoặc kiểm soát nào gặp vấn đề? | Truy cập trái phép, lộ dữ liệu, sai toàn vẹn, gián đoạn |
| Phạm vi | Ai và thành phần nào bị ảnh hưởng? | Một tài khoản, một tenant, nhiều tenant, chưa xác định |
| Tác động | Hậu quả thực tế và tiềm tàng là gì? | Lộ dữ liệu nhạy cảm, thay đổi quyền, dừng nghiệp vụ |
| Độ chắc chắn | Điều gì đã được chứng minh? | Nghi ngờ, đã xác nhận, đã bác bỏ một giả thuyết |
| Mức nghiêm trọng | Tác động đáng kể đến đâu theo chính sách? | SEV-1 đến SEV-4 trong ví dụ |
| Ưu tiên hành động | Việc nào phải làm trước và vì sao? | Ngăn tác động đang tiếp diễn, bảo toàn dữ liệu, điều tra tiếp |
| Trạng thái xử lý | Công việc đang ở giai đoạn nào? | Đang đánh giá, đang ngăn chặn, phục hồi, theo dõi, đóng |

Một incident có thể vừa là vấn đề phân quyền, vừa gây lộ dữ liệu và ảnh hưởng quyền riêng tư. Không bắt buộc chỉ chọn một loại nếu điều đó làm mất thông tin.

“Chưa xác nhận lộ dữ liệu” là trạng thái bằng chứng. Nó không phải một mức nghiêm trọng.

“Đã ngăn chặn” là trạng thái kiểm soát tác động. Nó không tự chứng minh dữ liệu chưa từng bị truy cập, hoặc tác động trong quá khứ đã được đảo ngược.

## 4. Danh mục loại sự cố có thể sử dụng

Danh mục nên đủ ổn định để định tuyến và tổng hợp, nhưng vẫn cho phép cập nhật khi có bằng chứng mới.

| Nhóm | Dấu hiệu hoặc tình huống | Câu hỏi phân loại quan trọng |
| --- | --- | --- |
| Xác thực và danh tính | Phiên bị dùng trái phép, thông tin xác thực bị lộ | Tài khoản nào, mức quyền nào, phiên còn hiệu lực không? |
| Phân quyền và ranh giới tenant | Người dùng đọc hoặc sửa đối tượng ngoài phạm vi | Đối tượng nào, đường truy cập nào, có nhiều tenant không? |
| Bí mật dữ liệu | Nội dung hoặc bí mật xuất hiện ở nơi không được phép | Loại dữ liệu, bên nhận, khả năng tiếp cận và khoảng thời gian? |
| Toàn vẹn | Dữ liệu, cấu hình hoặc quyết định bị thay đổi trái phép | Có thể xác định trạng thái tin cậy và tác động nghiệp vụ không? |
| Sẵn sàng và khả năng phục hồi | Dịch vụ trọng yếu gián đoạn, phục hồi không đạt | Chức năng nào mất, phụ thuộc nào bị ảnh hưởng, mức suy giảm? |
| Quyền riêng tư và mục đích xử lý | Dữ liệu bị thu, chuyển hoặc giữ sai chính sách | Nhóm dữ liệu, mục đích, bên nhận và phạm vi xử lý nào? |
| Bí mật tích hợp và phụ thuộc | Khóa tích hợp lộ, bên ngoài báo sự cố liên quan | Quyền của khóa, phạm vi phụ thuộc và tác động lan truyền? |
| Quan sát và kiểm soát vận hành | Audit bị ngắt, cảnh báo không chạy, dấu vết bị sửa | Mất khả năng phát hiện trong phạm vi nào, có tác động kèm theo không? |

Không coi tên nhóm là kết luận nguyên nhân gốc. Ví dụ, “lộ dữ liệu” mô tả tác động; nguyên nhân có thể là phân quyền, cấu hình lưu trữ, log hoặc một luồng tích hợp.

“Không rõ nguyên nhân” không được dùng thay cho mọi thông tin phân loại đã biết. Có thể biết dữ liệu tenant A đã trả cho tenant B dù chưa biết vì sao truy vấn sai.

### 4.1. Phân loại chính và nhãn bổ sung

Có thể dùng:

- Loại chính để chọn nhóm điều phối.
- Nhãn bổ sung để theo dõi tác động hoặc kiểm soát liên quan.
- Liên kết tới các incident hoặc alert cùng chuỗi.
- Trường giả thuyết nguyên nhân riêng.

Ví dụ: loại chính là phân quyền, nhãn bổ sung gồm bí mật dữ liệu và quyền riêng tư. Không cần mở ba incident độc lập chỉ để phản ánh ba nhãn nếu chúng thuộc cùng một tình huống cần điều phối chung.

Ngược lại, không gộp các sự cố độc lập chỉ vì cùng liên quan một nhà cung cấp. Việc gộp phải giữ được phạm vi, bằng chứng và trách nhiệm xử lý.

## 5. Đánh giá tác động và phạm vi

### 5.1. Những yếu tố cần thu thập

Mức nghiêm trọng không nên chỉ dựa trên số request hoặc số tài khoản:

| Yếu tố | Nội dung đánh giá |
| --- | --- |
| Độ nhạy cảm và giá trị tài sản | Bí mật tích hợp, quyền quản trị, dữ liệu cá nhân, dữ liệu nghiệp vụ quan trọng |
| Tác động lên bí mật | Có dữ liệu được trả, công khai hoặc chuyển tới bên không được phép không? |
| Tác động lên toàn vẹn | Có thay đổi quyền, dữ liệu, cấu hình hoặc quyết định quan trọng không? |
| Tác động lên sẵn sàng | Chức năng nào dừng, phạm vi người dùng, thời gian và khả năng làm việc thay thế |
| Độ rộng quyền | Một đối tượng riêng lẻ hay một danh tính có thể tác động nhiều hệ thống |
| Khả năng tiếp diễn và lan rộng | Đường truy cập còn mở, khóa còn hiệu lực, xử lý nền còn chạy |
| Khả năng phát hiện và khôi phục | Dấu vết đủ không, trạng thái tin cậy ở đâu, backup có dùng được không |
| Mức quan trọng nghiệp vụ | Dịch vụ và thời điểm có ý nghĩa gì với hoạt động thực tế |
| Hệ quả với người liên quan | Có khả năng gây hại đáng kể cho người dùng hoặc bên phụ thuộc không |
| Nghĩa vụ và cam kết áp dụng | Có yêu cầu đánh giá, phối hợp hoặc thông báo nào cần người có trách nhiệm xem xét không |

Một khóa quản trị bị lộ có thể đáng lo hơn hàng nghìn request bị từ chối. Một hồ sơ đặc biệt nhạy cảm có thể có tác động lớn dù số lượng nhỏ.

Không dùng trạng thái mã hóa lưu trữ để tự loại bỏ tác động nếu dữ liệu đã được trả qua một API hợp lệ về mặt kỹ thuật cho sai người.

### 5.2. Tách đã xác nhận, có thể ảnh hưởng và chưa biết

Ví dụ:

- **Đã xác nhận:** hai tài liệu tenant A được trả cho một danh tính tenant B.
- **Có thể ảnh hưởng:** cùng đường xử lý phục vụ nhiều tenant trong phiên bản bị lỗi.
- **Chưa biết:** có bao nhiêu request trong khoảng thiếu log và dữ liệu đã được bên nhận giữ hay chưa.

Không ghi “hai tài liệu bị ảnh hưởng” như tổng phạm vi cuối cùng nếu đó mới là số đã quan sát.

Không ghi “không có lộ dữ liệu” chỉ vì chưa tìm thấy log tải. Có thể đường ghi log không bao phủ hoặc không còn đủ dữ liệu.

Chưa biết không tự động có nghĩa là trường hợp xấu nhất đã xảy ra. Cần dùng các khả năng có cơ sở và giới hạn kiến trúc để chọn mức phản ứng, đồng thời ghi rõ điều chưa được xác nhận.

## 6. Một mô hình mức nghiêm trọng minh họa

Tổ chức có thể chọn tên và số mức khác. Bảng dưới dùng SEV-1 là cao nhất.

| Mức | Tiêu chí tác động minh họa | Cách phản ứng tương ứng |
| --- | --- | --- |
| SEV-1 — Khẩn cấp | Tác động rất lớn đang diễn ra hoặc khả năng đáng tin cậy tác động tới phạm vi trọng yếu: quyền điều khiển rộng bị chiếm, dữ liệu rất nhạy cảm có thể bị truy cập rộng, toàn vẹn nghiêm trọng hoặc khả năng phục hồi trọng yếu không còn đáng tin | Điều phối ngay, huy động vai trò cần thiết, ưu tiên ngăn tác động và đánh giá liên tục |
| SEV-2 — Cao | Tác động đáng kể đã xác nhận hoặc có cơ sở mạnh, phạm vi có thể giới hạn; vẫn cần phản ứng nhanh và phối hợp nhiều bên | Có người phụ trách rõ, ngăn tác động theo kế hoạch và cập nhật thường xuyên |
| SEV-3 — Trung bình | Tác động hạn chế, phạm vi đã có cơ sở xác định, không có dấu hiệu lan rộng đáng kể và biện pháp bảo vệ còn hiệu lực | Xử lý theo thời hạn đã chốt, điều tra và theo dõi thay đổi |
| SEV-4 — Thấp | Sự cố tác động nhỏ, có phạm vi và hậu quả thấp theo chính sách, không cần điều phối khẩn | Theo dõi tới khi xử lý, giữ hồ sơ và kiểm tra điều kiện nâng mức |

Các mô tả định tính cần được cụ thể hóa thêm cho dịch vụ: tài sản trọng yếu là gì, loại dữ liệu nào nhạy cảm, gián đoạn bao lâu hoặc phạm vi nào vượt ngưỡng.

Không được dùng bảng mẫu để tự suy ra một chính sách đầy đủ cho mọi tổ chức.

### 6.1. Cách sử dụng bảng

- Đối chiếu tác động đã biết và tác động tiềm tàng có cơ sở.
- Nếu nhiều tiêu chí áp dụng, chọn mức phản ứng đáp ứng tiêu chí nghiêm trọng hơn.
- Ghi lý do, bằng chứng và giả định.
- Giữ mức tạm thời khi cần, đồng thời đặt thời điểm đánh giá lại.
- Nâng mức ngay khi có thông tin làm thay đổi yêu cầu phản ứng.

Một alert vô hại không phải mặc định là SEV-4. Nếu chưa thỏa tiêu chí incident, có thể đóng alert sau đánh giá và giữ lý do theo quy trình.

Một nguy cơ rộng chỉ được suy ra từ tưởng tượng chưa đủ cơ sở không nên biến thành sự thật trong hồ sơ. Nhưng khi khóa bị lộ thực sự có quyền trên toàn hệ thống, độ rộng quyền là cơ sở cụ thể để xem xét tác động lớn dù chưa có số đếm đầy đủ.

### 6.2. Độ chắc chắn không làm biến mất nhu cầu phản ứng

Có thể ghi:

```text
Trạng thái xác nhận: nghi ngờ có cơ sở
Loại chính: lộ thông tin xác thực
Mức tạm thời: SEV-1
Cơ sở: khóa có quyền điều khiển rộng xuất hiện tại nơi bên ngoài tiếp cận được
Đã biết: giá trị khóa khớp với khóa đang có hiệu lực
Chưa biết: có thao tác trái phép nào đã sử dụng khóa hay chưa
```

Không cần chờ xác định mọi thao tác mới bắt đầu xử lý khóa. Đồng thời, hồ sơ không được khẳng định kẻ tấn công đã chiếm hệ thống nếu chưa có bằng chứng.

### 6.3. Severity khác ưu tiên công việc

Mức nghiêm trọng mô tả tác động theo chính sách. Ưu tiên công việc còn phụ thuộc vào:

- Tác động có đang tiếp diễn không.
- Có cửa sổ để ngăn thiệt hại hay bảo toàn dữ liệu không.
- Phụ thuộc nào cần xử lý trước.
- Biện pháp tạm thời đã có hiệu lực chưa.
- Có cam kết hoặc nghĩa vụ cần đánh giá riêng không.

Sau khi cô lập một đường lỗi, ưu tiên có thể chuyển từ chặn truy cập sang xác định phạm vi. Không cần hạ mức nghiêm trọng chỉ để thể hiện việc ngăn chặn đã hoàn tất.

Nên giữ mức ban đầu, mức hiện tại và mức cao nhất cùng lịch sử thay đổi. Chỉ thay mức khi có cơ sở theo chính sách, không nhằm làm đẹp số liệu.

## 7. Quy trình phân loại và cập nhật

### Bước 1: Tiếp nhận và giữ dấu vết ban đầu

Ghi nguồn, thời điểm nhận, dịch vụ liên quan, mô tả tín hiệu và người hoặc hệ thống tiếp nhận.

Phân biệt:

- Thời điểm hành vi có thể đã xảy ra.
- Thời điểm hệ thống quan sát hoặc phát hiện.
- Thời điểm tín hiệu đến kênh tiếp nhận sự cố.
- Thời điểm người phụ trách xác nhận và phân loại.

Không dùng thời điểm tạo ticket thay cho mọi mốc nếu tín hiệu đã đến kênh chính thức từ trước.

Chỉ giữ dữ liệu cần thiết. Không sao chép token hoặc nội dung nhạy cảm vào tiêu đề và kênh trao đổi rộng.

### Bước 2: Xác định có cần luồng incident không

Đối chiếu tiêu chí của tổ chức:

- Có tác động trái phép đã quan sát không?
- Có nghi ngờ đủ cơ sở và tác động đáng kể cần xử lý không?
- Có điều kiện phải kích hoạt ứng cứu ngay không?
- Đây là điểm yếu, sự cố vận hành hay tín hiệu cần theo dõi khác?

Ghi kết luận và lý do. Nếu chưa đủ thông tin nhưng hậu quả có thể lớn, chọn mức phản ứng tạm thời và tiếp tục đánh giá thay vì đóng ngay.

### Bước 3: Thu thông tin tối thiểu để quyết định

Ưu tiên các câu hỏi có thể thay đổi phản ứng:

1. Tài sản và mức quyền nào liên quan?
2. Đường truy cập còn hoạt động không?
3. Có dữ liệu hoặc trạng thái nào đã bị tác động?
4. Phạm vi được xác nhận và phạm vi có thể lan rộng là gì?
5. Những biện pháp hiện có đã giới hạn được tác động chưa?
6. Có mất dấu vết hoặc mất khả năng phục hồi không?

Không cần hoàn tất điều tra nguyên nhân gốc trước khi phân loại ban đầu.

### Bước 4: Gán loại, mức và người phụ trách

Ghi loại chính, nhãn liên quan, trạng thái xác nhận, phạm vi, mức nghiêm trọng và cơ sở lựa chọn.

Gán người điều phối hoặc vai trò chịu trách nhiệm phù hợp. Nếu người đó không xác nhận trong hạn, phải có đường dự phòng theo chính sách.

Một nhãn mức độ mà không có người nhận và hành động tiếp theo chưa tạo ra khả năng phản ứng thực tế.

### Bước 5: Kích hoạt hành động theo phạm vi

Phân loại phải liên kết đến playbook và quyền hành động.

Ví dụ:

- Khóa bị lộ: đánh giá phạm vi quyền, thu hồi hoặc thay khóa theo quy trình liên quan.
- Truy cập chéo tenant: giới hạn đường lỗi và kiểm tra các điểm vào cùng kiểm soát.
- Toàn vẹn không đáng tin: hạn chế thao tác tiếp theo có thể làm tác động lớn hơn, xác định nguồn trạng thái tin cậy.
- Phục hồi có nguy cơ đưa dữ liệu hoặc quyền cũ trở lại: giữ cổng mở dịch vụ cho đến khi kiểm tra điều kiện an toàn.

Biện pháp phải phù hợp phạm vi. Không mặc định mọi incident đều đòi hỏi tắt toàn bộ hệ thống.

Bảo toàn bằng chứng cần được phối hợp với ngăn tác động. Không trì hoãn một biện pháp ngăn thiệt hại cần thiết chỉ để tạo hồ sơ hoàn hảo; phải ghi các thay đổi và ảnh hưởng của chúng đến bằng chứng.

### Bước 6: Đánh giá lại theo thông tin và thời hạn

Các tác nhân cần xem lại gồm:

- Xuất hiện tenant, tài khoản hoặc thành phần mới.
- Xác nhận dữ liệu nhạy cảm hơn dự kiến.
- Phát hiện khóa có quyền rộng hoặc tác động lên toàn vẹn.
- Biện pháp ngăn chặn không đạt.
- Log thiếu hoặc trạng thái phục hồi không tin cậy.
- Bằng chứng bác bỏ một giả thuyết quan trọng.
- Đến mốc cập nhật theo mức độ.

Không chờ cuộc họp định kỳ nếu thông tin mới cho thấy cần nâng mức ngay.

### Bước 7: Chốt phân loại cuối và bài học yêu cầu

Khi kết thúc, giữ:

- Loại và mức ban đầu, thay đổi và kết luận cuối.
- Tác động được xác nhận cùng phần còn giới hạn.
- Cơ sở đóng hoặc chuyển sang theo dõi.
- Những yêu cầu thiếu, sai hoặc chưa được thực thi.
- Hành động khắc phục và kiểm chứng liên quan.

Phục hồi dịch vụ chưa chắc đủ để đóng incident nếu vẫn chưa giải quyết khả năng tiếp tục truy cập, trạng thái không tin cậy hoặc việc đánh giá tác động còn bắt buộc.

## 8. Ví dụ: nghi ngờ xuất dữ liệu chéo tenant

### 8.1. Thông tin ban đầu

Một alert cho thấy:

```text
actorTenant: B
documentTenant: A
action: EXPORT_DOWNLOAD
outcome: ALLOWED
```

Đây là tín hiệu cần xem xét. Có thể có lỗi phân quyền, lỗi ghi trường tenant hoặc một cơ chế truy cập đặc biệt đã được cấp quyền.

Người rà soát phải xác nhận ý nghĩa của các trường và chính sách truy cập. Không coi trường tenant do phía gọi tự khai là bằng chứng chắc chắn về danh tính.

Giả sử endpoint không cho phép tải chéo tenant và dữ liệu danh tính từ nguồn có thẩm quyền khớp với alert. Nhóm có cơ sở nghi ngờ sự cố bảo mật.

### 8.2. Phân loại theo diễn biến

| Mốc | Thông tin | Quyết định minh họa |
| --- | --- | --- |
| T0 | Một lượt tải có dấu hiệu sai tenant; chưa biết lỗi log hay truy cập thực | Mở hồ sơ nghi ngờ, loại phân quyền/bí mật dữ liệu; mức tạm thời theo chính sách, gán người phụ trách |
| T1 | Xác nhận nội dung tenant A thực sự được trả cho danh tính tenant B | Xác nhận incident; trong bối cảnh ban đầu phạm vi hẹp và dữ liệu nhạy cảm đáng kể, xử lý ở SEV-2 |
| T2 | Cùng worker có quyền đọc nhiều tenant, đường lỗi còn mở và không giới hạn được phạm vi | Nâng SEV-1 theo tiêu chí tác động rộng có cơ sở; triển khai ngăn tác động theo playbook |
| T3 | Đường xuất đã được giới hạn; tìm thấy thêm dữ liệu của một tenant khác | Ghi đã ngăn đường đã biết, tăng số tenant xác nhận; giữ phạm vi tiềm tàng riêng |
| T4 | Có khoảng thiếu log trong thời gian phiên bản lỗi hoạt động | Giảm độ chắc chắn của ước lượng phạm vi; không ghi số đã thấy là tổng cuối |
| T5 | Sửa kiểm soát và kiểm chứng các đường liên quan; đánh giá phạm vi đạt điều kiện chốt | Cập nhật trạng thái phục hồi/kết thúc theo chính sách, giữ mức cao nhất và lịch sử |

Mức T1 và T2 phụ thuộc giả định bối cảnh đã nêu. Nếu ngay T1 là dữ liệu đặc biệt nhạy cảm hoặc tài sản trọng yếu, chính sách có thể yêu cầu SEV-1 từ đầu.

Không hạ SEV-1 chỉ vì T3 đã chặn đường lỗi. Tác động trước đó và việc xác định phạm vi vẫn cần xử lý.

Nếu sau điều tra phát hiện alert xuất phát từ lỗi ánh xạ tenant và không có truy cập trái phép, cập nhật kết luận với bằng chứng, không xóa lịch sử nghi ngờ và phản ứng ban đầu.

### 8.3. Yêu cầu bảo mật được làm rõ từ ví dụ

Qua sự cố, nhóm có thể phát hiện:

- API chỉ kiểm tra quyền đầu vào nhưng worker không giữ ranh giới tenant.
- Đường tải tệp chưa áp dụng cùng chính sách.
- Audit không đủ để xác định phiên bản và đối tượng.
- Không có cơ chế giới hạn chức năng xuất theo phạm vi.
- Không có dữ liệu đủ để phân biệt tenant đã xác nhận và tenant có thể ảnh hưởng.

Các điểm này cần trở thành yêu cầu, thiết kế và tiêu chí kiểm chứng, không chỉ là câu “tăng cường giám sát” trong báo cáo.

Ví dụ yêu cầu:

> Mỗi công việc xuất phải gắn với tenant và phạm vi được cấp từ nguồn đã xác thực; worker không được sử dụng tenant do thông điệp không tin cậy tự quyết định. Kiểm thử phải bao gồm người dùng hợp lệ của tenant khác và đường tải trực tiếp.

Phân loại sự cố cung cấp đầu vào để ưu tiên và xác định tác động. Nó không tự chứng minh thay đổi trên đã được triển khai.

## 9. Đặc tả yêu cầu vận hành từ chính sách phân loại

### 9.1. Bộ yêu cầu minh họa

| ID | Yêu cầu | Tiêu chí kiểm chứng |
| --- | --- | --- |
| IR-CLS-01 | Hồ sơ phải có loại, trạng thái xác nhận, phạm vi đã biết/chưa biết, mức, cơ sở và người phụ trách | Tạo hồ sơ thử, kiểm tra trường bắt buộc và không cho thiếu thông tin quyết định |
| IR-CLS-02 | Mọi tín hiệu đi vào kênh incident phải có người phụ trách và phân loại sơ bộ trong 15 phút từ lúc kênh nhận | Bơm tín hiệu tổng hợp, đối chiếu mốc tiếp nhận, gán trách nhiệm và phân loại |
| IR-CLS-03 | Tín hiệu có điều kiện khẩn đã xác định phải được người trực xác nhận trong 5 phút; nếu quá hạn phải chuyển tuyến dự phòng | Mô phỏng có nhận, không nhận và tuyến đầu không sẵn sàng |
| IR-CLS-04 | Thông tin mới thỏa quy tắc nâng lên SEV-1 phải tạo yêu cầu nâng mức và định tuyến trong tối đa 2 phút từ khi nhận thông tin đó | Phát thông tin bổ sung có dấu thời gian, kiểm tra yêu cầu và bên nhận mô phỏng |
| IR-CLS-05 | Thay đổi loại, mức hoặc phạm vi phải lưu người thay đổi, thời điểm, giá trị trước/sau và cơ sở | Thử cập nhật, kiểm tra lịch sử và quyền sửa |
| IR-CLS-06 | Phân loại phải liên kết với playbook, vai trò chịu trách nhiệm và phạm vi hành động | Chạy diễn tập từng nhánh, kiểm tra nhiệm vụ và điều kiện kích hoạt |
| IR-CLS-07 | Hồ sơ và bằng chứng phải giới hạn quyền, không chứa bí mật trực tiếp trong tiêu đề hoặc kênh rộng | Thử quyền truy cập và marker tổng hợp tại các điểm hiển thị |
| IR-CLS-08 | Hồ sơ mức cao đang hoạt động phải có mốc đánh giá lại theo chính sách; thay đổi vật chất phải được xử lý ngay theo quy tắc liên quan | Mô phỏng quá hạn cập nhật và thông tin mới, kiểm tra nhắc việc/định tuyến |

Các ngưỡng trên chỉ dùng cho chính sách giả định. Một hệ thống thực tế cần xem xét năng lực trực, mức rủi ro và các cam kết của mình.

“Kênh nhận” phải là điểm được xác định rõ, chẳng hạn hệ thống tiếp nhận incident. Không được dời mốc sang lúc người trực mở ticket để làm thời gian phản ứng có vẻ ngắn hơn.

Với IR-CLS-04, tạo và định tuyến yêu cầu nâng mức không đồng nghĩa mọi hoạt động ngăn chặn phải hoàn tất trong 2 phút. Các hoạt động có mục tiêu và bằng chứng riêng.

### 9.2. Quyền nâng, hạ và thay đổi kết luận

Nên đặc tả rõ:

- Vai trò nào được đặt mức tạm thời.
- Người trực có thể nâng mức ngay trong phạm vi thẩm quyền nào.
- Ai được hạ mức và cơ sở nào bắt buộc.
- Điều gì phải thông báo khi thay đổi.
- Lịch sử được giữ và bảo vệ ra sao.

Không để việc nâng mức khẩn bị chặn vì người phê duyệt thường lệ chưa có mặt nếu chính sách đã giao quyền cho người trực.

Việc hạ mức không được xóa mức cao nhất hoặc lý do phản ứng trước đó. Trường hợp một giả thuyết bị bác bỏ cũng cần lịch sử để người sau hiểu vì sao nhóm đã hành động.

### 9.3. Phân loại không tự quyết định mọi nghĩa vụ thông báo

Một mức SEV có thể kích hoạt nhiệm vụ đánh giá nghĩa vụ, hợp đồng hoặc phối hợp bên ngoài. Nó không tự thay thế việc xác định điều kiện áp dụng của từng nghĩa vụ.

Không mặc định “SEV-1 luôn phải thông báo cho mọi khách hàng” hoặc “SEV-3 không bao giờ cần xem xét quyền riêng tư”.

Yêu cầu vận hành nên chỉ rõ người phụ trách đánh giá, thông tin cần cung cấp, kênh phối hợp và thời hạn theo nghĩa vụ đã được xác định. Không tự đưa một mốc chung vào mọi incident.

## 10. Mẫu hồ sơ giữ rõ phạm vi và bằng chứng

Ví dụ dưới đây là dữ liệu mô phỏng, không mô tả một sự cố thực tế:

```yaml
incidentId: INC-SYNTHETIC-001
recordVersion: 3
service: document-export
primaryCategory: AUTHORIZATION_BOUNDARY
relatedCategories:
  - DATA_CONFIDENTIALITY
  - PRIVACY
confirmationStatus: CONFIRMED
scopeConfidence: MEDIUM

scope:
  confirmed:
    tenantCount: 2
    description: "Có bằng chứng dữ liệu của hai tenant bị trả sai phạm vi"
  potential:
    description: "Các tenant được phục vụ bởi đường worker trong phiên bản lỗi"
  unknown:
    - "Tổng số lượt trong khoảng thiếu log"
    - "Bên nhận có giữ lại dữ liệu hay không"

severity:
  initial: SEV-2
  current: SEV-1
  highest: SEV-1
  basis: "Đường lỗi còn mở tại lúc nâng mức và worker có quyền trên nhiều tenant"

responseState: CONTAINED
ownerRole: INCIDENT_COORDINATOR
playbookRef: "<playbook đã được phê duyệt và phiên bản>"
evidenceRefs:
  - "<tham chiếu bằng chứng truy cập đã xác nhận>"
  - "<tham chiếu cấu hình quyền worker>"

timestamps:
  firstKnownOccurrence: "<thời điểm hoặc khoảng thời gian, nếu biết>"
  receivedAt: "<mốc kênh tiếp nhận nhận tín hiệu>"
  acknowledgedAt: "<mốc người trực xác nhận>"
  initiallyClassifiedAt: "<mốc phân loại sơ bộ>"
  lastMaterialEvidenceReceivedAt: "<mốc nhận thông tin thay đổi đánh giá>"
  lastReviewedAt: "<mốc đánh giá gần nhất>"
  nextReviewAt: "<mốc đánh giá tiếp theo>"

openQuestions:
  - "Giới hạn phạm vi trong khoảng thiếu log"
  - "Xác nhận các đường tải liên quan đã được kiểm chứng"
```

Các mốc thời gian phải có múi giờ và ý nghĩa nhất quán. Nếu chỉ biết một khoảng, giữ khoảng đó thay vì tạo ra một timestamp chính xác giả.

Hồ sơ trên được ghi nhận đã ngăn đường đã biết nhưng chưa đóng. Trạng thái đó không xóa các câu hỏi về phạm vi.

Tham chiếu bằng chứng cần trỏ đến kho có quyền phù hợp. Không nhúng token, khóa riêng hoặc toàn bộ dữ liệu người dùng vào hồ sơ điều phối.

## 11. Kiểm thử quy tắc phân loại và định tuyến

### 11.1. Dùng tình huống tổng hợp có kết quả mong đợi

Các test có thể bao gồm:

| Test | Đầu vào | Kết quả cần kiểm tra |
| --- | --- | --- |
| Event chưa phải incident | Một lần đăng nhập sai bị chặn bình thường | Không tự gán incident chỉ vì có event; kết quả theo tiêu chí đã chốt |
| Tín hiệu tác động cao chưa xác nhận | Khóa thử có quyền rộng được phát hiện ở nơi ngoài phạm vi | Có mức phản ứng tạm thời, không đợi đủ nguyên nhân; trạng thái bằng chứng vẫn đúng |
| Phạm vi tăng | Hồ sơ ban đầu một tenant có thêm bằng chứng nhiều tenant | Yêu cầu nâng mức/định tuyến trong hạn, giữ lịch sử |
| Phạm vi chưa biết | Thiếu log một khoảng | Không đổi unknown thành 0 hoặc tự tuyên bố không ảnh hưởng |
| Người trực không nhận | Tín hiệu khẩn không được xác nhận | Tuyến dự phòng hoạt động, không coi gửi thành công là đã có người nhận |
| Thử hạ mức thiếu thẩm quyền | Danh tính không có quyền thay đổi mức | Bị từ chối, không sửa lịch sử trái phép |
| Bác bỏ giả thuyết | Bằng chứng chỉ ra lỗi log thay vì truy cập trái phép | Cập nhật kết luận có cơ sở, giữ lịch sử và phân biệt tác động thật |
| Marker bí mật trong đầu vào | Dữ liệu thử chứa giá trị bị cấm | Không xuất hiện ở tiêu đề hoặc điểm chia sẻ không được phép |

Không chỉ kiểm tra một hàm chọn SEV. Cần kiểm chứng đường tiếp nhận, đồng hồ, gán trách nhiệm, kênh dự phòng, quyền và lịch sử.

### 11.2. Mã giả cho tình huống nâng mức

```text
fixture = createSyntheticIncident(
    severity = "SEV-2",
    confirmedScope = "Một tenant"
)

assert fixture.hasAssignedOwner()
beforeHistory = readClassificationHistory(fixture.id)

newEvidence = publishSyntheticMaterialEvidence(
    incidentId = fixture.id,
    condition = "Đường lỗi có quyền trên nhiều tenant và chưa được giới hạn"
)

result = waitForEscalationDecisionPoint(fixture.id)

assert escalationRequestExistsFor(newEvidence.id)
assert routedToRequiredRoleOrFallback(fixture.id)
assert routingDelayWithinDefinedLimit(newEvidence.receivedAt)

assert currentClassificationMatchesApprovedRules(fixture.id)
assert historyPreservesPreviousValues(beforeHistory)
assert unknownScopeIsNotRecordedAsZero(fixture.id)
assert noSecretMarkerInBroadlyVisibleFields(fixture.id)
```

Đây là mã giả, không phải API của một thư viện. Kênh nhận trong diễn tập là bên nhận mô phỏng hoặc môi trường thử đã được xác định, không phải gửi thông báo sự cố thật ra ngoài.

Nếu không quan sát được định tuyến hoặc người nhận, phải ghi lỗi bộ thử hoặc thiếu cơ sở kết luận. Không coi việc gọi hàm gửi không báo lỗi là bằng chứng đã có người tiếp nhận.

### 11.3. Tabletop và diễn tập kỹ thuật bổ sung cho nhau

Tabletop là diễn tập thảo luận theo tình huống, phù hợp để kiểm tra:

- Tiêu chí có được các vai trò hiểu thống nhất không.
- Ai quyết định và chuyển tuyến thế nào.
- Có mâu thuẫn giữa mục tiêu ngăn chặn, bảo toàn và phục hồi không.
- Có thiếu thông tin để chốt phân loại không.

Diễn tập kỹ thuật kiểm tra cơ chế thực tế: tiếp nhận, quyền, thông báo, timestamp, audit và điều kiện chạy playbook.

Một tabletop thành công không tự chứng minh công cụ định tuyến đã hoạt động. Một test gửi cảnh báo thành công cũng không chứng minh mọi người hiểu đúng thẩm quyền và quy tắc.

## 12. Đo thời gian và đánh giá chất lượng

### 12.1. Chọn mốc đo đúng

Ví dụ các đại lượng:

- Thời gian xác nhận: mốc người trực xác nhận trừ mốc kênh nhận.
- Thời gian phân loại sơ bộ: mốc phân loại đầu trừ mốc kênh nhận.
- Thời gian xử lý thông tin nâng mức: mốc quyết định hoặc định tuyến tương ứng trừ mốc nhận thông tin mới.
- Số hồ sơ quá hạn đánh giá lại.
- Số lần thiếu owner, thiếu cơ sở hoặc thiếu trường phạm vi.

Nếu mốc xảy ra thực tế không biết, không tính thời gian phát hiện như bằng không. Ghi giới hạn hoặc dùng khoảng nếu có cơ sở.

Khi ghép thời gian từ nhiều nguồn, cần đồng bộ phù hợp và biết sai lệch. Không kết luận đạt một ngưỡng sát biên nếu sai số có thể làm đổi kết quả.

Chuyển người phụ trách, gộp ticket hoặc mở lại hồ sơ không được âm thầm đặt lại đồng hồ để bỏ qua thời gian đã trôi qua.

### 12.2. Không tối ưu chỉ số bằng cách đổi nhãn

Các hành vi làm sai chất lượng đo:

- Để tín hiệu ở ngoài kênh incident cho đến khi sẵn sàng xử lý.
- Hạ SEV để không vi phạm mục tiêu.
- Ghi không ảnh hưởng khi mới chưa có đủ dữ liệu.
- Tạo nhiều incident nhỏ để tránh nhìn thấy tác động chung.
- Gộp sự cố độc lập làm mất trách nhiệm hoặc phạm vi.
- Đóng hồ sơ sau khi dịch vụ hoạt động mà chưa đạt điều kiện đóng.

Số lần đổi mức cao không tự chứng minh phân loại kém. Thông tin mới có thể làm thay đổi đánh giá hợp lý. Cần xem chất lượng quyết định theo thông tin có tại thời điểm đó.

Kết quả phân tích sau sự cố nên quay lại yêu cầu: bổ sung trường log, điều kiện nâng mức, ranh giới quyền, tiêu chí phục hồi hoặc test còn thiếu.

## 13. Sai lầm thường gặp và checklist

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Coi alert là incident đã xác nhận | Tạo kết luận sai và nhiễu phản ứng | Tách trạng thái xác nhận và cơ sở |
| Chờ biết nguyên nhân gốc mới phân loại | Trì hoãn ngăn tác động | Dùng mức tạm thời với thông tin tối thiểu |
| Dùng một nhãn cho loại, mức và trạng thái | Khó định tuyến và hiểu diễn biến | Tách các chiều và giữ lịch sử |
| Chỉ đếm số tài khoản | Bỏ qua mức quyền, độ nhạy cảm và tác động | Đánh giá nhiều yếu tố |
| Không thấy log nên kết luận không lộ | Bỏ qua khoảng trống quan sát | Ghi unknown và giới hạn |
| Hạ mức ngay khi chặn đường lỗi | Che tác động đã xảy ra và việc còn lại | Tách mức nghiêm trọng với trạng thái ngăn chặn |
| Không ai nhận trách nhiệm | Hồ sơ có nhãn nhưng không có hành động | Có owner, thời hạn và tuyến dự phòng |
| Tự quyết nghĩa vụ thông báo bằng SEV | Bỏ sót hoặc áp dụng sai phạm vi | Có bước đánh giá đúng trách nhiệm |
| Sao chép bí mật vào ticket | Tạo thêm điểm lộ thông tin | Dùng tham chiếu và dữ liệu tối thiểu |
| Đóng sự cố mà không sửa yêu cầu | Lặp lại khoảng trống kiểm soát | Liên kết phát hiện với yêu cầu và kiểm chứng mới |

Trước khi chốt một lần phân loại:

- [ ] Phân biệt event, alert, incident và giả thuyết.
- [ ] Loại chính và nhãn liên quan phản ánh điều đã biết.
- [ ] Phạm vi xác nhận, tiềm tàng và chưa biết được tách rõ.
- [ ] Tác động xét cả dữ liệu, quyền, toàn vẹn, sẵn sàng và phục hồi.
- [ ] Mức hiện tại có cơ sở theo chính sách, không chỉ cảm tính.
- [ ] Trạng thái xác nhận và độ chắc chắn không bị nhầm với mức.
- [ ] Có người phụ trách, hành động tiếp theo và mốc đánh giá lại.
- [ ] Quyền nâng/hạ mức và lịch sử thay đổi được kiểm soát.
- [ ] Bằng chứng và kênh điều phối không làm lộ thêm dữ liệu.
- [ ] Mốc thời gian và giới hạn quan sát được ghi trung thực.
- [ ] Nghĩa vụ hoặc phối hợp bên ngoài được đánh giá qua trách nhiệm tương ứng.
- [ ] Bài học được chuyển thành yêu cầu và tiêu chí kiểm chứng khi cần.
