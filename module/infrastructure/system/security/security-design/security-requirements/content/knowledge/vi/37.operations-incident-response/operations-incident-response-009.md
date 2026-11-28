# Vulnerability disclosure: tiếp nhận và phối hợp công bố lỗ hổng

## 1. Disclosure là một phần của yêu cầu bảo mật vận hành

Một người bên ngoài phát hiện rằng tài khoản của tenant B có thể tải tài liệu tenant A. Người đó cần biết báo cho ai, gửi bằng cách nào và cung cấp thông tin đến mức nào. Đội phát triển cần xác minh, giới hạn tác động, sửa lỗi và phối hợp thông tin cho người có thể bị ảnh hưởng.

Nếu không có quy trình, báo cáo có thể nằm trong hộp thư không được theo dõi, bằng chứng nhạy cảm bị chia sẻ rộng hoặc thông báo “đã sửa” được gửi trước khi bản vá thực sự đến hệ thống liên quan.

Vulnerability disclosure là hoạt động thông báo và trao đổi thông tin về lỗ hổng để các bên có thể đánh giá, xử lý và đưa ra quyết định công bố phù hợp. Khi có nhiều bên phối hợp về nội dung, thời điểm và cách giảm tác động, quy trình thường được gọi là công bố lỗ hổng có phối hợp.

Trong module yêu cầu bảo mật, vấn đề cần đặc tả là:

- Có kênh tiếp nhận hoạt động và người chịu trách nhiệm.
- Báo cáo được xác nhận, đánh giá và chuyển tuyến trong thời hạn rõ.
- Bằng chứng được xử lý như dữ liệu nhạy cảm và đầu vào không tin cậy.
- Việc sửa, kiểm chứng, phát hành và triển khai được phân biệt.
- Người báo cáo nhận thông tin đúng với trạng thái thực.
- Việc công bố cung cấp đủ thông tin bảo vệ người dùng, với phạm vi và giới hạn trung thực.

Bài học trình bày quy trình và yêu cầu kỹ thuật minh họa. Phạm vi kiểm thử được cho phép, cam kết tổ chức và nghĩa vụ áp dụng cần được chủ thể có thẩm quyền xác nhận; bộ phận kỹ thuật không tự tạo các bảo đảm vượt thẩm quyền.

## 2. Phân biệt các khái niệm liên quan

| Khái niệm | Ý nghĩa | Điều không nên tự suy ra |
| --- | --- | --- |
| Báo cáo lỗ hổng | Thông tin cho rằng một kiểm soát có thể bị vượt qua | Chưa có nghĩa tác động đã được xác nhận |
| Chính sách tiếp nhận và công bố | Quy định kênh, phạm vi, cách trao đổi và quy trình xử lý | Không tự đồng nghĩa với chương trình trả thưởng |
| Chương trình trả thưởng | Cơ chế đánh giá và thưởng theo điều kiện riêng | Không thay thế yêu cầu an toàn khi kiểm thử |
| Công bố có phối hợp | Trao đổi giữa bên phát hiện, bên chịu trách nhiệm và bên liên quan | Không có nghĩa mọi thông tin phải bị giữ kín vô thời hạn |
| Thông báo bảo mật công khai | Nội dung giúp người sử dụng nhận biết ảnh hưởng và hành động | Không bắt buộc phải kèm mọi chi tiết khai thác |
| Security incident | Tình huống thỏa tiêu chí sự cố cần phản ứng | Một lỗ hổng chưa có bằng chứng khai thác không tự chứng minh incident đã xảy ra |

Một báo cáo có thể đồng thời chỉ ra điểm yếu và cung cấp dấu hiệu sự cố đang diễn ra. Khi đó cần mở luồng phản ứng sự cố phù hợp song song, không chờ quy trình xử lý lỗ hổng thông thường hoàn tất.

Ngược lại, không tuyên bố “đã bị xâm nhập” chỉ vì nhận được mô tả về một khả năng tấn công chưa xác minh.

### 2.1. Công bố riêng và công bố rộng có mục tiêu khác nhau

Trao đổi riêng ban đầu giúp xác minh và chuẩn bị biện pháp. Thông báo cho bên bị ảnh hưởng giúp họ giảm rủi ro. Công bố rộng có thể giúp cộng đồng hiểu vấn đề và cập nhật hệ thống.

Các nhóm thông tin không nhất thiết có cùng người nhận hoặc cùng thời điểm:

- Bằng chứng gốc có thể chỉ dành cho nhóm xử lý.
- Người vận hành cần biết phiên bản, phạm vi và cách giảm tác động.
- Người dùng cần biết hành động liên quan đến họ.
- Chi tiết đủ để tái tạo một đường khai thác có thể cần quyết định công bố riêng.

Mục tiêu là đưa đúng thông tin đến đúng đối tượng theo một kế hoạch có cơ sở.

## 3. Đặc tả chính sách tiếp nhận trước khi có báo cáo

Một chính sách hữu ích cần đủ rõ để người báo cáo và đội xử lý không phải đoán.

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| Kênh chính thức | Gửi ở đâu, có đường dự phòng nào? |
| Tài sản và phiên bản trong phạm vi | Sản phẩm, dịch vụ, tên miền hoặc thành phần nào được tiếp nhận? |
| Ranh giới kiểm thử | Hoạt động nào được chủ sở hữu cho phép và giới hạn gì phải giữ? |
| Thông tin cần cung cấp | Cần mô tả, phiên bản, điều kiện, bước tái hiện và bằng chứng tối thiểu nào? |
| Bảo vệ dữ liệu | Khi gặp dữ liệu người khác, người báo cáo cần dừng và báo theo cách nào? |
| Phản hồi | Thời hạn xác nhận, đánh giá ban đầu và cập nhật là gì? |
| Phối hợp | Ai điều phối, có cách trao đổi riêng hoặc bảo vệ bằng chứng không? |
| Công bố | Cách thảo luận mốc, thay đổi kế hoạch và xử lý bất đồng? |
| Ghi nhận | Việc nêu tên hoặc thông tin người báo cáo cần lựa chọn nào? |
| Trả thưởng | Nếu có, điều kiện nằm ở đâu và ai quyết định? |

Chỉ công bố các cam kết đã được xác nhận và có khả năng thực hiện. Nếu tổ chức muốn có nội dung về sự cho phép hoặc bảo đảm liên quan, cần được bên có thẩm quyền xem xét trước khi sử dụng.

Không coi việc thấy một kênh báo cáo công khai là được phép thực hiện mọi hoạt động trên mọi tài sản liên quan.

### 3.1. Phạm vi kỹ thuật và trách nhiệm phối hợp

Một báo cáo có thể liên quan tài sản ngoài phạm vi chương trình nhưng vẫn chỉ ra dữ liệu hoặc phụ thuộc của tổ chức đang có rủi ro.

Quy trình nên xác định cách đánh giá và chuyển đúng trách nhiệm, thay vì tự động bỏ qua chỉ vì tên miền không nằm trong danh sách.

Việc chuyển tiếp không được mặc định chia sẻ mọi thông tin cá nhân, bằng chứng hoặc bí mật của người báo cáo. Chỉ chuyển phần cần thiết theo quyền và cơ chế đã xác định.

## 4. Kênh tiếp nhận cũng cần yêu cầu bảo mật

### 4.1. Có kênh không có nghĩa là có người nhận

Một địa chỉ được công bố nhưng thư bị lọc bỏ hoặc tài khoản không còn người quản lý không tạo ra khả năng tiếp nhận thực tế.

Cần đặc tả và kiểm chứng:

- Kênh truy cập được và hướng đến nơi có người phụ trách.
- Báo cáo được tạo mã theo dõi ổn định.
- Kênh dự phòng hoạt động khi kênh chính lỗi.
- Xác nhận gửi đi phản ánh việc đã nhận, chưa tự tuyên bố đã xác minh.
- Có định tuyến khi người phụ trách vắng mặt.
- Có cách theo dõi báo cáo quá hạn hoặc bị kẹt.

Nếu chọn một kênh có mã hóa, cần quản lý thông tin khóa, quyền truy cập và thay đổi khóa phù hợp. Không quảng bá cơ chế mà đội tiếp nhận không thể sử dụng hoặc không kiểm tra được.

### 4.2. Báo cáo là đầu vào không tin cậy

Nội dung báo cáo, liên kết và tệp đính kèm có thể chứa mã, dữ liệu độc hại hoặc chỉ dẫn không phù hợp.

Quy trình tiếp nhận phải tránh:

- Tự chạy tệp hoặc mã chứng minh khai thác trong môi trường vận hành.
- Tự mở tài nguyên bên ngoài bằng danh tính có quyền rộng.
- Đưa toàn bộ nội dung vào hệ thống khác mà chưa kiểm soát dữ liệu.
- Coi chỉ dẫn trong báo cáo là lệnh có thẩm quyền.
- Chia sẻ token hoặc thông tin khách hàng qua điểm hiển thị rộng.

Cần có giới hạn kích thước, cách lưu tệp, quyền xem và môi trường phân tích phù hợp. Nếu phải thực thi một mẫu để xác minh, dùng môi trường cô lập và phạm vi đã được cho phép.

### 4.3. Bằng chứng tối thiểu, có ích và được bảo vệ

Một báo cáo tốt có thể gồm:

- Thành phần, phiên bản hoặc môi trường quan sát.
- Điều kiện cần có về tài khoản, quyền và cấu hình.
- Hành vi mong đợi và hành vi thực tế.
- Các bước tái hiện tối thiểu.
- Tác động có thể xảy ra, phân biệt với điều đã quan sát.
- Request hoặc log đã loại bí mật và dữ liệu không cần thiết.
- Cách liên hệ và lựa chọn ghi nhận nếu người báo cáo muốn cung cấp.

Không yêu cầu người báo cáo lấy thêm dữ liệu thật của người khác chỉ để chứng minh quy mô. Đội xử lý cần tìm cách xác minh bằng dữ liệu tổng hợp, môi trường thử hoặc bằng chứng đã có.

Một ảnh chụp có thể hữu ích nhưng chưa đủ giải thích mọi giả định. Yêu cầu bổ sung nên cụ thể và giới hạn vào phần cần xác minh.

## 5. Quy trình từ báo cáo đến công bố

### Bước 1: Tiếp nhận và xác nhận

Tạo mã theo dõi, giữ mốc nhận tại kênh chính thức và kiểm tra rủi ro cần chuyển tuyến khẩn.

Thông điệp xác nhận nên cho biết:

- Báo cáo đã được nhận và mã theo dõi.
- Bên hoặc vai trò đang xử lý.
- Mốc cập nhật dự kiến.
- Cách gửi bổ sung an toàn.
- Việc xác minh kỹ thuật chưa hoàn tất nếu đúng như vậy.

Không gửi thông tin nội bộ không cần thiết chỉ để làm phản hồi có vẻ chi tiết.

### Bước 2: Đánh giá ban đầu và trách nhiệm

Xác định sản phẩm, chủ sở hữu, phạm vi, mức tác động tiềm tàng và chất lượng bằng chứng.

Nếu có dấu hiệu khóa đang có hiệu lực bị lộ, truy cập trái phép đang diễn ra hoặc tác động rộng, định tuyến tới vai trò ứng cứu theo chính sách. Chuyển tuyến khẩn không đồng nghĩa mọi tuyên bố trong báo cáo đã được xác nhận.

Nếu thiếu thông tin, ghi rõ câu hỏi còn mở và phần đã đánh giá được. Không đóng “không tái hiện” khi bộ thử chưa có đúng phiên bản hoặc cấu hình.

### Bước 3: Xác minh kỹ thuật

Tạo điều kiện tái hiện trong môi trường được kiểm soát. Xác nhận:

- Ranh giới bảo mật nào bị vượt.
- Tác nhân cần quyền và điều kiện gì.
- Phiên bản hoặc cấu hình nào bị ảnh hưởng.
- Hành vi đã quan sát có đúng là vượt yêu cầu không.
- Có dấu hiệu tác động thực cần xử lý như incident không.

Không nhầm “hệ thống được thiết kế như vậy” với “không có vấn đề bảo mật”. Nếu thiết kế cho phép hành vi gây hại ngoài mục tiêu bảo vệ, cần xem lại yêu cầu và rủi ro.

### Bước 4: Đánh giá tác động và chọn cách xử lý

Xem xét bí mật, toàn vẹn, sẵn sàng, quyền riêng tư và khả năng lan rộng. Điểm số chuẩn hóa nếu có chỉ là một đầu vào; cần biết giả định và cách diễn giải của điểm đó.

Ghi phạm vi đã xác nhận, phạm vi có thể ảnh hưởng và phần chưa biết.

Chọn:

- Biện pháp giảm tác động tạm thời.
- Hướng sửa nguyên nhân.
- Các nhánh, bản triển khai hoặc bên phụ thuộc cần xử lý.
- Chủ sở hữu và mục tiêu thời gian.
- Điều kiện cần để công bố hoặc cập nhật kế hoạch.

Một biện pháp tạm thời không tự đồng nghĩa nguyên nhân đã được sửa.

### Bước 5: Sửa và kiểm chứng

Kiểm tra cả trường hợp bị cấm lẫn hành vi hợp lệ:

- PoC tối thiểu không còn vượt kiểm soát.
- Các biến thể cùng nguyên nhân cũng được xử lý.
- Đường API, worker, tải tệp hoặc điểm vào khác có liên quan không bị bỏ sót.
- Người có quyền vẫn thực hiện được chức năng cần thiết.
- Sửa lỗi không làm lộ dữ liệu trong phản hồi hoặc log.
- Có kết quả gắn với phiên bản, cấu hình và môi trường.

Không chỉ chặn đúng ID hoặc chuỗi mà người báo cáo đã gửi nếu lỗi nằm ở quy tắc chung.

### Bước 6: Phát hành, triển khai và phối hợp thông tin

Phân biệt bản sửa có trong mã, artifact đã được kiểm chứng, phiên bản đã phát hành và hệ thống thực sự đã được triển khai.

Với phần mềm do người khác vận hành, bản vá sẵn có không có nghĩa mọi người sử dụng đã cập nhật. Với dịch vụ tự vận hành, một môi trường đã sửa không có nghĩa mọi vùng hoặc đường phục vụ đã sửa.

Kế hoạch thông tin phải phản ánh trạng thái thật của từng phạm vi.

### Bước 7: Công bố theo kế hoạch và theo dõi

Thống nhất đối tượng, nội dung, mốc dự kiến và điều kiện thay đổi. Nếu có nhiều nhà cung cấp hoặc nhóm phụ thuộc, ghi trách nhiệm và trạng thái của từng bên.

Khi điều kiện thay đổi, đánh giá lại kế hoạch thay vì để một mốc cũ tự chạy mà không xem tác động.

Có thể cần thông tin bảo vệ người dùng trước khi mọi bản vá hoàn tất, đặc biệt khi rủi ro đang tiếp diễn. Khi đó cần nói rõ giới hạn, biện pháp tạm thời và trạng thái bản vá, đồng thời cân nhắc mức chi tiết công bố.

### Bước 8: Đóng hồ sơ có điều kiện rõ

Điều kiện đóng có thể bao gồm kết luận kỹ thuật, phạm vi xử lý, trạng thái các bản sửa liên quan, trao đổi với người báo cáo và các hành động còn lại đã được quản lý.

Đóng một hồ sơ điều phối không được xóa nhiệm vụ cập nhật, giám sát hoặc khắc phục ở các nhánh còn lại.

## 6. Ví dụ xuyên suốt: báo cáo tải tài liệu chéo tenant

### 6.1. Báo cáo ban đầu

Một người kiểm thử trong phạm vi được chủ sở hữu cho phép dùng hai tenant tổng hợp A và B:

1. Tạo tài liệu DOC-A trong tenant A.
2. Tạo tài liệu DOC-B trong tenant B.
3. Xác nhận mỗi tài khoản đọc được tài liệu của mình.
4. Dùng tài khoản B gọi đường tải DOC-A.
5. Quan sát nội dung có marker thuộc tenant A.

Báo cáo gửi mã theo dõi fixture, phiên bản và request đã loại thông tin xác thực. Người báo cáo không cần lấy tài liệu của khách hàng thật để chứng minh lỗi.

Đội tiếp nhận ghi đây là nghi ngờ vượt ranh giới tenant và ưu tiên xác minh theo tác động có thể xảy ra.

### 6.2. Xác minh và điều tra phạm vi

Trong môi trường thử, đội xử lý xác nhận:

- Tài khoản B có phiên hợp lệ nhưng không có quyền trên DOC-A.
- API tải kiểm tra có đăng nhập nhưng không ràng buộc tenant và tài liệu.
- Nội dung tenant A thực sự được trả về.
- Một đường tải khác dùng cùng logic kiểm tra.
- Chưa đủ bằng chứng để kết luận có khách hàng thực bị khai thác.

Kết luận phù hợp là lỗ hổng đã được xác nhận trên phiên bản và cấu hình được thử. Tình trạng khai thác thực tế vẫn cần đánh giá riêng.

Nếu phát hiện log truy cập trái phép thực, kích hoạt quy trình incident. Không dùng hồ sơ disclosure để thay thế việc đánh giá và xử lý tác động đã xảy ra.

### 6.3. Chuyển thành yêu cầu và test

Yêu cầu sửa cần nói rõ:

> Mọi đường trả nội dung tài liệu phải kiểm tra danh tính, tenant, tài liệu và quyền hành động ở phía máy chủ. Một tài khoản hợp lệ của tenant khác không được nhận nội dung hoặc metadata ngoài phạm vi được cấp.

Tiêu chí kiểm chứng:

- Tài khoản A tải được DOC-A khi có quyền.
- Tài khoản B không nhận được nội dung DOC-A.
- Người cùng tenant nhưng không được cấp quyền cũng bị từ chối.
- Thay đổi mã tài liệu hoặc đường tải không vượt kiểm soát.
- Tệp đã được tạo trước khi sửa cũng chịu chính sách truy cập tương ứng.
- Worker và đường tải dùng quyền hiện hành theo yêu cầu vòng đời đã chốt.
- Phản hồi lỗi và log không làm lộ token hoặc nội dung bị cấm.

Không đủ nếu chỉ ẩn nút tải, đổi ID khó đoán hoặc chặn đúng DOC-A trong báo cáo.

### 6.4. Theo dõi phiên bản và triển khai riêng

Bảng sau dùng tên và phiên bản giả định:

| Phạm vi | Kết quả kỹ thuật | Trạng thái xử lý |
| --- | --- | --- |
| Nhánh 2.4.0 được thử | Xác nhận bị ảnh hưởng | Cần sửa hoặc biện pháp tạm thời |
| Bản 2.4.1 ứng viên | Test hồi quy đạt trong môi trường thử | Chưa tự đồng nghĩa đã phát hành |
| Nhánh 2.3.x | Chưa đủ thông tin | Không được ghi an toàn chỉ vì chưa thử |
| Dịch vụ do tổ chức vận hành tại vùng A | Đã triển khai artifact đã kiểm chứng | Tiếp tục quan sát theo kế hoạch |
| Dịch vụ tại vùng B | Chưa triển khai xong | Giữ biện pháp tạm thời và trạng thái chờ |
| Bản do khách hàng tự vận hành | Có bản vá sẵn có theo kế hoạch phát hành | Chưa biết mọi bên đã cập nhật hay chưa |

Không suy ra một dải phiên bản rộng chỉ từ một phiên bản đã tái hiện. Cần căn cứ về mã, lịch sử và các nhánh liên quan để mô tả phạm vi.

Thông báo công khai hoặc trao đổi riêng phải dùng đúng thông tin này. “Đã có bản vá” khác với “mọi hệ thống đã được vá”.

## 7. Quản lý trạng thái mà không che mất công việc còn lại

Một trạng thái `DONE` có thể gây nhầm vì nhiều chiều công việc không kết thúc cùng lúc.

Có thể theo dõi riêng:

| Chiều | Giá trị minh họa |
| --- | --- |
| Xác minh báo cáo | Mới nhận, cần thông tin, đang xác minh, đã xác nhận, chưa tái hiện, ngoài phạm vi, trùng |
| Khắc phục | Chưa phân công, đang sửa, đã giảm tác động, chờ kiểm chứng, đã kiểm chứng |
| Phát hành và triển khai | Ứng viên, đã phát hành, triển khai một phần, triển khai xong trong phạm vi, chưa biết phía sử dụng |
| Phối hợp công bố | Đang trao đổi riêng, có kế hoạch, cần xem lại, đã thông báo theo phạm vi |
| Theo dõi điều phối | Đang mở, chờ bên liên quan, đủ điều kiện đóng |

“Chưa tái hiện” không đồng nghĩa chắc chắn báo cáo sai. Cần ghi điều kiện đã thử và điều còn thiếu.

“Ngoài phạm vi” không đồng nghĩa không có rủi ro. Cần biết trách nhiệm chuyển tiếp hoặc xử lý thông tin liên quan.

“Trùng” cần tham chiếu hồ sơ gốc và kiểm tra xem báo cáo mới có thêm phiên bản, cấu hình hoặc tác động chưa được xử lý không. Không đóng trùng chỉ vì tiêu đề giống nhau.

Nếu quy trình cho phép chờ thông tin hoặc tạm dừng một đồng hồ xử lý, phải ghi điều kiện, mốc và trách nhiệm rõ. Không tự dừng mọi thời hạn chỉ vì đã gửi một câu hỏi.

## 8. Phối hợp thời điểm và mức chi tiết công bố

### 8.1. Có kế hoạch, có mốc xem lại

Một kế hoạch phối hợp nên ghi:

- Bên điều phối và cách liên hệ.
- Thành phần, phiên bản và người sử dụng có thể bị ảnh hưởng.
- Biện pháp tạm thời đang có.
- Trạng thái bản vá và khả năng phân phối.
- Ngày dự kiến và các mốc cập nhật.
- Thông tin nào dành cho nhóm nào.
- Điều kiện phải thay đổi kế hoạch.
- Cách xử lý khi không nhận được phản hồi.

Không có một thời hạn công bố chung đúng cho mọi trường hợp. Một con số trong chính sách mẫu không tự trở thành nghĩa vụ hoặc quyết định phù hợp cho sản phẩm khác.

Mốc dự kiến cũng không phải lý do trì hoãn vô thời hạn. Nếu tiến độ thay đổi, cần trao đổi có nội dung và nêu quyết định mới, không chỉ liên tục yêu cầu “đợi thêm”.

### 8.2. Cân bằng thông tin hành động và chi tiết khai thác

Người vận hành cần biết cách nhận diện phiên bản bị ảnh hưởng, cập nhật hoặc giảm tác động. Họ không nhất thiết cần ngay mọi chi tiết đủ để tự động hóa khai thác.

Quyết định mức chi tiết nên xét:

- Rủi ro đang tiếp diễn và thông tin đã công khai.
- Tình trạng bản vá, biện pháp tạm thời và phạm vi triển khai.
- Khả năng người sử dụng tự bảo vệ.
- Rủi ro với dữ liệu và các bên phụ thuộc.
- Sự phối hợp cần thiết giữa các nhà cung cấp.
- Các nghĩa vụ đã được người có trách nhiệm xác định.

Giữ kín một chi tiết không tự bảo đảm không ai khác biết lỗ hổng. Công bố một thông báo ngắn cũng không tự chứng minh người dùng đã nhận và thực hiện hành động.

### 8.3. Nhiều bên và phụ thuộc

Một lỗi trong thư viện hoặc dịch vụ tích hợp có thể ảnh hưởng nhiều sản phẩm. Cần xác định ai:

- Sửa thành phần gốc.
- Tích hợp hoặc phát hành lại.
- Kiểm chứng cấu hình sản phẩm.
- Thông báo cho người sử dụng.
- Theo dõi nhánh chưa xử lý.

Không tự chuyển toàn bộ bằng chứng cho mọi bên. Chia sẻ phần cần thiết qua cơ chế phù hợp và giữ rõ quyền truy cập.

Nếu một bên không phản hồi, dùng tuyến liên hệ dự phòng hoặc vai trò điều phối đã được xác định. Việc đổi kế hoạch công bố cần một quyết định có cơ sở, không phải thao tác tự động do không nhận được email.

### 8.4. Ghi nhận người báo cáo

Nếu có ghi nhận công khai, xác nhận tên hoặc bí danh mà người báo cáo muốn dùng và phạm vi được phép nêu.

Không công khai email, thông tin liên hệ hoặc danh tính chỉ vì chúng xuất hiện trong báo cáo. Đồng ý được ghi nhận cũng không mặc định đồng ý công khai toàn bộ trao đổi.

Nếu có chương trình trả thưởng, quyết định liên quan phải theo quy trình riêng. Không để việc thảo luận thưởng làm đình trệ xử lý một rủi ro đang tồn tại.

## 9. Đặc tả yêu cầu đo được cho quy trình disclosure

### 9.1. Chính sách thời gian minh họa

Giả sử một tổ chức chọn:

- Gửi xác nhận tiếp nhận trong 24 giờ liên tục kể từ khi kênh chính thức nhận báo cáo.
- Có kết quả đánh giá ban đầu trong 72 giờ liên tục.
- Cập nhật có nội dung ít nhất mỗi 7 ngày lịch khi hồ sơ đang mở.
- Định tuyến đánh giá khẩn trong 15 phút với báo cáo thỏa điều kiện khẩn đã xác định.

Đây là mục tiêu ví dụ, không phải thời hạn bắt buộc chung. Báo cáo có rủi ro khẩn không được chờ hết 72 giờ mới được xem xét.

Kết quả đánh giá ban đầu có thể là đã xác nhận, cần thông tin cụ thể, cần chuyển trách nhiệm hoặc đang điều tra một điểm đã xác định. Không được ghi “đã xác nhận” chỉ để đạt chỉ số.

Với báo cáo không có cách liên hệ hợp lệ, ghi rõ không thể gửi xác nhận qua kênh nào. Không coi việc tạo một thông điệp nhưng gửi thất bại là đã liên hệ được người báo cáo.

### 9.2. Ma trận yêu cầu và kiểm chứng

| ID | Yêu cầu | Cách kiểm chứng |
| --- | --- | --- |
| VD-INT-01 | Kênh chính thức và dự phòng tiếp nhận được báo cáo, tạo mã theo dõi và giữ mốc nhận | Gửi báo cáo tổng hợp qua môi trường thử, kiểm tra mã và định tuyến |
| VD-ACK-01 | Xác nhận trong 24 giờ theo phạm vi và điều kiện liên hệ đã định nghĩa | Đối chiếu thời điểm nhận, nội dung xác nhận và kết quả gửi |
| VD-TRI-01 | Đánh giá ban đầu trong 72 giờ, có owner, kết luận hiện tại và câu hỏi còn mở | Kiểm tra hồ sơ trước/sau hạn và trường bắt buộc |
| VD-URG-01 | Báo cáo có dấu hiệu thuộc danh mục khẩn được định tuyến đánh giá trong 15 phút | Mô phỏng tình huống khẩn, người trực vắng và tuyến dự phòng |
| VD-DAT-01 | Hồ sơ và bằng chứng chỉ được truy cập theo vai trò; bí mật không xuất hiện ở điểm hiển thị rộng | Thử quyền, marker tổng hợp, tệp đính kèm và log |
| VD-SCP-01 | Phạm vi phiên bản, cấu hình và trạng thái triển khai được tách rõ | Thử trường hợp nhiều nhánh, một phần chưa kiểm chứng hoặc chưa triển khai |
| VD-FIX-01 | Chỉ ghi đã kiểm chứng khi có test hồi quy liên kết với yêu cầu và artifact cụ thể | Đối chiếu test bị cấm, test hợp lệ và phiên bản |
| VD-UPD-01 | Cập nhật ít nhất mỗi 7 ngày khi mở, có trạng thái thực và bước tiếp theo | Mô phỏng chờ bên khác, không có tiến triển và quá hạn |
| VD-PUB-01 | Nội dung công bố được rà soát phạm vi, trạng thái và dữ liệu nhạy cảm theo trách nhiệm đã giao | Kiểm tra bản nháp tổng hợp có lỗi phạm vi hoặc marker bí mật |
| VD-CRE-01 | Ghi nhận công khai chỉ dùng thông tin đã được người báo cáo đồng ý | Thử trường hợp chọn bí danh, không ghi nhận hoặc thay đổi lựa chọn |

Danh mục khẩn cần có điều kiện đủ rõ, chẳng hạn báo cáo chứa dấu hiệu thông tin xác thực có quyền rộng bị lộ hoặc bằng chứng truy cập dữ liệu trái phép đang diễn ra.

Quy tắc định tuyến có thể dựa trên nghi ngờ để ưu tiên đánh giá. Nó không được tự biến một tuyên bố chưa kiểm tra thành kết luận sự cố đã xác nhận.

### 9.3. Đo phản hồi theo đúng ý nghĩa

Phân biệt:

- Hệ thống đã nhận báo cáo.
- Đã tạo thông điệp xác nhận.
- Kênh gửi đã chấp nhận thông điệp.
- Có xác nhận phát tới đích nếu kênh cung cấp.
- Người báo cáo đã phản hồi.

Không giả định biết người báo cáo đã đọc nếu cơ chế không cung cấp thông tin đó.

Nếu dùng giờ làm việc thay cho giờ liên tục, cần chốt lịch, múi giờ và cách tính. Ví dụ trên dùng giờ liên tục để tránh bỏ ngỏ điều kiện này.

## 10. Mẫu hồ sơ kỹ thuật và thông báo

### 10.1. Hồ sơ điều phối nội bộ

```yaml
reportId: VULN-SYNTHETIC-009
reportVersion: 2
receivedAt: "<mốc kênh chính thức nhận, có múi giờ>"
reporterContactRef: "<tham chiếu liên hệ hạn chế quyền, nếu có>"
publicCreditPreference: "<không ghi nhận hoặc tên/bí danh được xác nhận>"

product: "<sản phẩm chịu trách nhiệm>"
ownerRole: PRODUCT_SECURITY_OWNER
validationStatus: CONFIRMED
summary: "Thiếu kiểm tra phạm vi tenant trên đường tải tài liệu"

impact:
  confirmed: "Tái hiện được bằng hai tenant tổng hợp"
  potential: "Các đường dùng cùng logic kiểm tra cần được rà soát"
  exploitationInProduction: UNKNOWN

affectedScope:
  confirmedVersions:
    - "<phiên bản và cấu hình đã xác nhận>"
  unassessedBranches:
    - "<nhánh chưa có kết luận>"

remediation:
  state: VERIFICATION_PENDING
  temporaryMitigation: "<phạm vi và giới hạn nếu có>"
  candidateArtifact: "<định danh artifact>"
  regressionTests:
    - "<test từ yêu cầu phân quyền>"
    - "<test đường tải liên quan>"

deployment:
  fixedScopes:
    - "<phạm vi đã triển khai và kiểm chứng>"
  pendingScopes:
    - "<phạm vi chưa hoàn tất>"

coordination:
  nextUpdateAt: "<mốc cập nhật>"
  proposedDisclosureAt: "<mốc dự kiến hoặc chưa chốt>"
  unresolvedQuestions:
    - "<câu hỏi cần bên chịu trách nhiệm quyết định>"

evidenceRefs:
  - "<tham chiếu bằng chứng trong kho hạn chế quyền>"
```

Đây là mẫu minh họa. Các giá trị trong dấu `<...>` cần được điền bằng thông tin thật khi sử dụng; chúng không phải bằng chứng đã có.

Thông tin liên hệ và bằng chứng gốc không cần xuất hiện ở mọi bản sao hồ sơ. Mã hóa hoặc che dữ liệu cũng cần đi cùng quyền truy cập và quy trình sử dụng phù hợp.

### 10.2. Khung thông báo bảo mật

```text
Tiêu đề:
  <Sản phẩm> — <mô tả ngắn tác động>

Phạm vi:
  <Phiên bản, cấu hình và điều kiện đã xác nhận>
  <Nhánh hoặc phạm vi chưa có kết luận nếu liên quan>

Tác động:
  <Hành vi trái phép có thể xảy ra và điều kiện cần>
  <Phân biệt tác động có thể có với bằng chứng đã quan sát>

Hành động:
  <Bản sửa hoặc cách giảm tác động đã được kiểm chứng>
  <Giới hạn và trạng thái triển khai/phân phối>

Tình trạng:
  <Thông tin thực về khai thác đã biết, chưa biết hoặc đang đánh giá>
  <Thời điểm cập nhật nội dung>

Liên hệ và ghi nhận:
  <Kênh phù hợp>
  <Tên/bí danh nếu đã được đồng ý>
```

Nếu dùng một mã định danh lỗ hổng công khai, sử dụng mã thực được cấp theo quy trình phù hợp. Không tự tạo mã hoặc viết như thể việc cấp đã hoàn tất khi chưa có kết quả.

“Chưa tìm thấy bằng chứng khai thác” khác với “không có khai thác”. Cách diễn đạt phải phản ánh nguồn và giới hạn đánh giá.

Thông báo cần giúp người sử dụng ra quyết định; không cần đưa chi tiết nội bộ không phục vụ hành động hoặc làm lộ thêm dữ liệu.

## 11. Kiểm thử quy trình tiếp nhận và phối hợp

### 11.1. Các tình huống cần thử

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Báo cáo đầy đủ | Nhận được, có ID, owner, xác nhận và mốc xử lý |
| Báo cáo thiếu phiên bản | Có câu hỏi cụ thể, giữ phần đã đánh giá, không tự kết luận sai |
| Báo cáo ẩn danh hoặc không liên hệ được | Vẫn ghi nhận và xử lý theo chính sách; giới hạn phản hồi được thể hiện |
| Báo cáo trùng có phạm vi mới | Kiểm tra thông tin mới, liên kết hồ sơ gốc, không đóng máy móc |
| Kênh chính lỗi | Có đường dự phòng và cảnh báo cho vai trò phụ trách |
| Người phụ trách vắng | Định tuyến thay thế hoạt động |
| Tệp hoặc nội dung có chỉ dẫn nguy hiểm | Không tự thực thi, có cơ chế phân tích phù hợp |
| Một vùng đã sửa, vùng khác chưa | Không gửi kết luận mọi nơi đã được vá |
| Bản nháp có marker bí mật | Bị phát hiện trước điểm công bố trong phạm vi kiểm tra |
| Người báo cáo chọn không ghi nhận | Không xuất hiện thông tin liên hệ hoặc tên ngoài lựa chọn |

Bộ thử dùng kênh nhận, người nhận và dữ liệu mô phỏng theo phạm vi đã định nghĩa. Không gửi thông báo lỗ hổng thật ra ngoài chỉ để kiểm tra pipeline.

### 11.2. Mã giả cho bài thử trạng thái triển khai

```text
report = createSyntheticValidatedReport()
candidate = registerVerifiedCandidateArtifact(report.id)

setDeploymentState(
    report.id,
    fixed = ["region-a"],
    pending = ["region-b"]
)

draft = generateCoordinationUpdate(report.id)

assert draft.saysFixAvailableWhenAppropriate()
assert draft.distinguishesFixedAndPendingScopes()
assert not draft.claimsAllDeploymentsFixed()
assert draft.nextUpdateIsDefined()

setReporterCreditPreference(report.id, "NO_PUBLIC_CREDIT")
publicDraft = prepareSyntheticAdvisory(report.id)

assert noReporterContactIn(publicDraft)
assert noForbiddenEvidenceMarkerIn(publicDraft)
assert affectedScopeHasSupportingReferences(publicDraft)
assert requiredReviewStateRecorded(publicDraft)
```

Đây là mã giả, không phải API của một thư viện. Bản nháp trong test không phải nội dung đã được công bố.

Một bộ sinh thông báo đúng trong test logic chưa chứng minh quyền xuất bản, kênh gửi và cơ chế chặn dữ liệu nhạy cảm hoạt động. Cần kiểm chứng các ranh giới liên quan bằng diễn tập tích hợp phù hợp.

### 11.3. Phân biệt đạt, lỗi và thiếu bằng chứng

- **PASS:** các assertion bắt buộc được thực hiện và đạt trong phạm vi.
- **FAIL:** có hành vi trái yêu cầu, chẳng hạn báo đã vá toàn bộ khi còn vùng chưa sửa.
- **ERROR:** bộ thử hoặc hạ tầng không thực hiện đúng phép thử.
- **INCONCLUSIVE:** thiếu quan sát để kết luận.
- **SKIPPED:** không chạy test và có lý do.

Kênh gửi không báo lỗi chưa chắc chứng minh đầu kia đã nhận theo tiêu chí. Không quan sát được một thông báo cũng chưa chứng minh nó không được gửi; cần đối chiếu hệ thống nguồn và bên nhận trong phạm vi.

## 12. Chỉ số và cải thiện yêu cầu

Có thể theo dõi:

- Thời gian nhận đến xác nhận và đánh giá ban đầu.
- Số báo cáo không có owner hoặc quá hạn cập nhật.
- Thời gian xác nhận đến biện pháp tạm thời, bản sửa và kiểm chứng.
- Thời gian bản sửa sẵn có đến triển khai trong các phạm vi do tổ chức quản lý.
- Số báo cáo phải mở lại vì bỏ sót nhánh hoặc đường truy cập.
- Số lỗi về quyền xem bằng chứng, dữ liệu trong thông báo hoặc ghi nhận sai lựa chọn.
- Các khoảng trống được chuyển thành yêu cầu và test hồi quy.

Không dùng số báo cáo bị từ chối cao hoặc số lỗ hổng xác nhận thấp như bằng chứng tự thân về chất lượng bảo mật. Cần xem tính đúng của quyết định và mức độ xử lý rủi ro.

Không đặt lại mốc nhận vì chuyển đội, đổi ticket hoặc chờ người phụ trách. Nếu có điều kiện dừng một chỉ số, phải có chính sách và lịch sử rõ.

Sau mỗi trường hợp đáng chú ý, xem lại:

- Kênh và trách nhiệm có rõ không.
- Yêu cầu phản hồi có thực hiện được không.
- Tại sao kiểm thử trước đó bỏ sót lỗi.
- Có cùng nguyên nhân ở thành phần khác không.
- Việc phân phối và thông tin có phản ánh đúng trạng thái không.
- Cần bổ sung yêu cầu xác thực, phân quyền, dữ liệu, audit hoặc phục hồi nào.

## 13. Lỗi thường gặp và checklist

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Công bố kênh nhưng không có người theo dõi | Báo cáo bị bỏ quên | Kiểm thử tiếp nhận, owner và tuyến dự phòng |
| Xác nhận tiếp nhận như đã xác minh | Người báo cáo hiểu sai trạng thái | Dùng nội dung đúng với bước xử lý |
| Đòi thêm dữ liệu khách hàng thật | Tăng tác động của phát hiện | Dùng bằng chứng tối thiểu và fixture tổng hợp |
| Chạy PoC trực tiếp trong vận hành | Tạo rủi ro mới | Phân tích như đầu vào không tin cậy |
| Đóng “trùng” hoặc “ngoài phạm vi” máy móc | Bỏ sót phạm vi và trách nhiệm mới | Đánh giá thông tin liên quan và chuyển đúng nơi |
| Chỉ vá đúng tình huống báo cáo | Còn biến thể cùng nguyên nhân | Rà soát quy tắc chung và thêm test hồi quy |
| Có commit sửa là báo hoàn tất | Nhánh hoặc bản triển khai vẫn bị ảnh hưởng | Tách kiểm chứng, phát hành và triển khai |
| Công bố một dải phiên bản không có cơ sở | Người sử dụng hành động sai | Ghi phạm vi xác nhận và phần chưa biết |
| Lặp yêu cầu chờ mà không có nội dung | Mất khả năng phối hợp | Có mốc, tiến độ thật và quyết định xem lại |
| Công khai danh tính theo mặc định | Làm lộ thông tin người báo cáo | Xác nhận lựa chọn ghi nhận riêng |

Trước khi chốt một vòng xử lý:

- [ ] Kênh, phạm vi và trách nhiệm đã được xác định.
- [ ] Có mã theo dõi, mốc nhận và phản hồi đúng hạn theo chính sách.
- [ ] Dấu hiệu khẩn được chuyển tới luồng ứng cứu phù hợp.
- [ ] Bằng chứng được bảo vệ và không tự thực thi.
- [ ] Kết luận kỹ thuật tách khỏi giả thuyết hoặc thông tin chưa biết.
- [ ] Phạm vi phiên bản, cấu hình và bên liên quan có cơ sở.
- [ ] Bản sửa được kiểm chứng bằng hành vi bị cấm và hợp lệ.
- [ ] Trạng thái phát hành và triển khai không bị gộp với đã sửa.
- [ ] Kế hoạch công bố có mốc xem lại, người quyết định và mức chi tiết phù hợp.
- [ ] Nội dung không lộ bí mật, dữ liệu thừa hoặc danh tính ngoài lựa chọn.
- [ ] Hành động còn lại có owner và được theo dõi sau khi đóng điều phối.
- [ ] Bài học được chuyển về yêu cầu và tiêu chí kiểm chứng.
