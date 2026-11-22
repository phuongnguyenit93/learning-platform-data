# Ưu tiên kiểm thử khi cải tiến hệ thống cũ thiếu bộ hồi quy

## 1. Bối cảnh và mục tiêu

Hệ thống cũ thường chứa nhiều quy tắc nghiệp vụ đã tích lũy qua thời gian nhưng chỉ được thể hiện một phần trong tài liệu. Một thay đổi tưởng như nhỏ có thể ảnh hưởng đến luồng xử lý ít người biết, dữ liệu lịch sử, tích hợp bên ngoài hoặc hành vi mà người dùng đã quen thuộc. Khi hệ thống thiếu bộ kiểm thử hồi quy, nhóm không có một mạng lưới tự động đủ rộng để phát hiện sớm những thay đổi ngoài dự kiến.

Trong tình huống đó, mục tiêu đầu tiên không phải là tạo ngay một bộ kiểm thử bao phủ toàn bộ hệ thống. Nhóm cần giảm rủi ro cho thay đổi sắp thực hiện, xây dựng bằng chứng về hành vi hiện tại, rồi tăng dần khả năng phát hiện hồi quy theo mức độ quan trọng. Việc kiểm thử phải hỗ trợ cải tiến an toàn trong điều kiện thời gian, kiến thức hệ thống và khả năng thiết lập môi trường có hạn.

Một cách tiếp cận hiệu quả kết hợp kiểm thử đặc trưng hành vi (characterization testing), kiểm thử theo rủi ro, kiểm thử thăm dò có ghi nhận, kiểm tra tích hợp tại các ranh giới quan trọng và các bước xác nhận sau triển khai. Nhóm chọn nội dung kiểm thử dựa trên tác động của thay đổi, mức độ quan trọng của luồng nghiệp vụ, khả năng xảy ra lỗi và mức độ khó phát hiện hoặc khôi phục khi lỗi xuất hiện.

## 2. Hiểu đúng rủi ro của hệ thống thiếu hồi quy

Thiếu bộ hồi quy không có nghĩa là hệ thống hoàn toàn không có kiểm thử. Có thể vẫn tồn tại kiểm thử đơn lẻ, kịch bản thủ công, dữ liệu mẫu, quy trình nghiệm thu hoặc kinh nghiệm vận hành. Tuy nhiên, các bằng chứng này thường phân tán, không gắn với phiên bản mã nguồn, khó chạy lặp lại hoặc không bao phủ các luồng liên quan đến thay đổi.

Trước khi chọn kiểm thử, cần nhận diện các nguồn rủi ro sau:

- **Hành vi ngầm định:** quy tắc không được mô tả trong tài liệu nhưng đã trở thành một phần của cách hệ thống hoạt động.
- **Phụ thuộc chéo:** một thay đổi ở thành phần này tác động đến batch job, báo cáo, API, tích hợp hoặc dữ liệu của thành phần khác.
- **Dữ liệu lịch sử:** logic phụ thuộc vào dữ liệu cũ, trạng thái tích lũy, định dạng lưu trữ hoặc thứ tự xử lý.
- **Khó tái tạo môi trường:** thiếu cấu hình, dữ liệu kiểm thử, dịch vụ giả lập hoặc hướng dẫn dựng môi trường tương đương.
- **Thiếu quan sát:** log, metric, trace hoặc cảnh báo không đủ để nhận biết lỗi sau khi triển khai.
- **Khó quay lui:** thay đổi schema, chuyển đổi dữ liệu hoặc tác động bên ngoài có thể không đảo ngược đơn giản.
- **Kiến thức tập trung:** chỉ một vài cá nhân hiểu rõ hệ thống, khiến việc phân tích tác động và xác minh phụ thuộc vào họ.

Phân tích ban đầu nên trả lời: hệ thống đang phục vụ ai; luồng nào tạo ra giá trị hoặc nghĩa vụ quan trọng; dữ liệu nào có giá trị cao; thành phần nào thay đổi; và lỗi ở đâu sẽ gây hậu quả lớn nhất. Không nên đánh giá rủi ro chỉ dựa trên số dòng mã hoặc độ lớn của thay đổi. Một sửa đổi nhỏ trong tính toán tiền, phân quyền hoặc xử lý dữ liệu có thể có rủi ro cao hơn một thay đổi lớn ở giao diện ít quan trọng.

## 3. Lập bản đồ luồng và vùng ảnh hưởng trước khi viết kiểm thử

Khi tài liệu hệ thống không đầy đủ, hãy bắt đầu bằng một bản đồ đủ dùng cho phạm vi thay đổi. Không cần mô hình hóa toàn bộ kiến trúc ngay từ đầu. Tập trung vào đường đi của dữ liệu và các điểm mà thay đổi có thể tác động.

Một bản đồ tác động thường gồm:

1. **Điểm vào:** màn hình, API, lịch chạy, message, tệp nhập hoặc thao tác của người vận hành khởi động luồng.
2. **Xử lý chính:** quy tắc nghiệp vụ, phép tính, trạng thái và điều kiện rẽ nhánh liên quan.
3. **Dữ liệu đọc và ghi:** bảng, tệp, cache, sự kiện hoặc kho dữ liệu bị truy cập.
4. **Phụ thuộc:** dịch vụ ngoài, thư viện, hàng đợi, tác vụ nền và thành phần dùng chung.
5. **Đầu ra và tác động:** phản hồi cho người dùng, thay đổi trạng thái, thông báo, báo cáo hoặc hành động bên ngoài.
6. **Cơ chế vận hành:** log, metric, cảnh báo, sao lưu, khôi phục và cách tắt hoặc quay lui thay đổi.

Có thể lần theo luồng bằng cách đọc mã tại điểm vào, tìm nơi gọi các hàm liên quan, kiểm tra truy vấn và cấu hình, xem log hoặc trace có sẵn, rồi xác nhận với người hiểu nghiệp vụ. Kết luận quan trọng cần gắn với bằng chứng hoặc ghi rõ là giả thuyết cần xác minh. Không xem tên hàm hoặc bình luận cũ là bằng chứng đầy đủ về hành vi thực tế.

Với mỗi vùng ảnh hưởng, ghi lại thành phần, dữ liệu, phụ thuộc, hậu quả nếu lỗi xảy ra và cách xác nhận. Bản đồ này giúp nhóm chọn các kiểm thử có giá trị cao và tránh bỏ sót tác động nằm ngoài file vừa sửa.

## 4. Xếp thứ tự ưu tiên theo rủi ro

Khi nguồn lực có hạn, cần một cách xếp thứ tự minh bạch. Có thể đánh giá mỗi luồng hoặc vùng thay đổi theo các chiều sau:

| Chiều đánh giá | Câu hỏi gợi ý |
|---|---|
| Mức độ ảnh hưởng | Nếu lỗi xảy ra, tác động đến người dùng, dữ liệu, doanh thu, an toàn hoặc nghĩa vụ nào? |
| Khả năng xảy ra | Độ phức tạp, số lượng phụ thuộc, lịch sử lỗi và mức độ mới của thay đổi làm lỗi dễ xuất hiện đến đâu? |
| Khả năng phát hiện | Lỗi có được phát hiện nhanh qua kiểm thử, giám sát hoặc phản hồi người dùng không? |
| Khả năng khôi phục | Có thể quay lui hoặc sửa dữ liệu an toàn không? Thời gian khôi phục dự kiến ra sao? |
| Phạm vi lan truyền | Thành phần có được nhiều luồng hoặc hệ thống khác sử dụng không? |
| Độ không chắc chắn | Nhóm hiểu rõ hành vi và dữ liệu đến mức nào; còn giả định nào chưa được xác minh? |

Có thể phân loại thành mức ưu tiên cao, trung bình và thấp. Ví dụ, ưu tiên cao thường là luồng tạo hoặc cập nhật dữ liệu quan trọng, xác thực và phân quyền, tính toán tài chính, xử lý giao dịch, tích hợp trọng yếu, chuyển đổi schema và tác vụ chạy hàng loạt. Mức trung bình có thể gồm chức năng nghiệp vụ thường dùng nhưng có thể khôi phục dễ dàng. Mức thấp có thể gồm nội dung ít ảnh hưởng, có đường thay thế và không làm thay đổi dữ liệu quan trọng.

Không nên cộng điểm máy móc nếu nhóm chưa có dữ liệu hoặc cách chấm nhất quán. Một ma trận điểm có thể hỗ trợ trao đổi, nhưng cần giữ quyền đánh giá chuyên môn đối với rủi ro nghiêm trọng. Những yếu tố như yêu cầu pháp lý, bảo mật hoặc an toàn có thể là điều kiện bắt buộc, không được hạ ưu tiên chỉ vì điểm tổng thấp.

Khi thay đổi có phạm vi rộng hoặc tác động không rõ, tăng ưu tiên cho việc khảo sát và thu thập bằng chứng trước khi sửa. Sự không chắc chắn cao tự nó là một lý do để dành thêm thời gian kiểm tra, đặc biệt khi khả năng khôi phục thấp.

## 5. Tạo đường cơ sở hành vi bằng characterization testing

Characterization test ghi lại hành vi mà hệ thống đang thể hiện tại thời điểm khảo sát. Mục đích là tạo đường cơ sở có thể chạy lại trước và sau khi cải tiến. Với hệ thống cũ, kết quả hiện tại có thể chứa cả hành vi đúng, hành vi lỗi đã biết và hành vi chưa được xác định rõ. Vì vậy, không nên tự động xem mọi kết quả hiện tại là yêu cầu nghiệp vụ đúng.

Quy trình thực hiện:

1. Chọn một luồng có rủi ro hoặc liên quan trực tiếp đến thay đổi.
2. Chuẩn bị dữ liệu đại diện, bao gồm trường hợp thông thường, biên và dữ liệu lịch sử nếu phù hợp.
3. Ghi lại đầu vào, trạng thái ban đầu, hành động thực hiện và đầu ra quan sát được.
4. Lặp lại trên cùng phiên bản và điều kiện để kiểm tra tính ổn định.
5. Xác nhận với người có hiểu biết nghiệp vụ xem hành vi quan sát được là mong muốn, chấp nhận được hay là lỗi tồn tại.
6. Chuyển những hành vi đã được xác nhận thành kiểm thử tự động hoặc kịch bản kiểm thử có thể lặp lại.

Ví dụ, một chức năng tính phí có thể trả về tổng tiền, khoản giảm trừ và trạng thái giao dịch. Bộ characterization test đầu tiên ghi nhận các đầu ra hiện tại với một tập dữ liệu đã kiểm soát. Nếu phát hiện một trường hợp làm tròn không đúng chính sách, ghi nhận thành lỗi riêng và xác định kết quả mong muốn với người phụ trách nghiệp vụ. Không khóa lỗi đó thành hành vi chuẩn chỉ vì hệ thống cũ đang làm như vậy.

Khi đầu ra chứa dữ liệu biến động như thời gian hiện tại, mã ngẫu nhiên hoặc thứ tự không được bảo đảm, cần chuẩn hóa hoặc so sánh những thuộc tính có ý nghĩa. Không loại bỏ quá nhiều chi tiết đến mức kiểm thử không còn phát hiện được thay đổi quan trọng. Mọi quy tắc chuẩn hóa phải được giải thích để người duy trì hiểu điều gì đang được bỏ qua.

## 6. Xây dựng các lớp kiểm thử có giá trị cao

Không phải mọi vùng mã đều cần cùng một loại kiểm thử. Nên chọn lớp kiểm thử phù hợp với rủi ro và khả năng cô lập của hệ thống.

| Lớp kiểm thử | Mục đích trong hệ thống cũ | Khi nên ưu tiên |
|---|---|---|
| Kiểm thử khói | Xác nhận ứng dụng khởi động và các luồng sống còn hoạt động | Sau build, triển khai hoặc thay đổi hạ tầng |
| Kiểm thử đặc trưng hành vi | Khóa hành vi hiện tại đã được xác nhận để phát hiện thay đổi ngoài dự kiến | Khi thiếu đặc tả hoặc cần cải tiến một vùng chưa được kiểm thử |
| Kiểm thử đơn vị tại điểm có thể cô lập | Xác nhận quy tắc nghiệp vụ, phép tính và xử lý biên | Khi có thể tách logic khỏi phụ thuộc cũ |
| Kiểm thử tích hợp | Xác nhận tương tác với cơ sở dữ liệu, message broker, API hoặc hệ thống ngoài | Khi rủi ro nằm ở hợp đồng và ranh giới thành phần |
| Kiểm thử đầu cuối có chọn lọc | Xác nhận luồng người dùng quan trọng qua nhiều thành phần | Với một số hành trình trọng yếu, ổn định và có thể duy trì |
| Kiểm thử dữ liệu và migration | Xác nhận tính toàn vẹn, tương thích và khả năng chuyển đổi dữ liệu | Khi thay đổi schema, định dạng hoặc quy trình nhập xuất |
| Kiểm thử thăm dò | Phát hiện hành vi bất ngờ mà kịch bản hiện có chưa mô tả | Khi kiến thức nghiệp vụ hoặc phạm vi ảnh hưởng còn chưa rõ |

Một số hệ thống cũ khó viết unit test trực tiếp vì logic nghiệp vụ gắn chặt với cơ sở dữ liệu, biến toàn cục hoặc dịch vụ bên ngoài. Trong trường hợp đó, bắt đầu bằng kiểm thử tại ranh giới có thể dựng được, chẳng hạn chạy một thao tác qua API hoặc một tác vụ với cơ sở dữ liệu thử nghiệm. Sau khi có đường cơ sở, nhóm có thể dần tách logic qua các điểm thay thế phụ thuộc (seam) và bổ sung kiểm thử đơn vị cho phần đã cô lập.

Không cần ép mọi kiểm thử vào một tầng. Kiểm thử đầu cuối hữu ích cho luồng sống còn nhưng thường chậm và dễ phụ thuộc môi trường; kiểm thử đơn vị nhanh nhưng không chứng minh được cấu hình tích hợp; kiểm thử thủ công linh hoạt nhưng cần ghi lại dữ liệu và bước thực hiện để tái lập. Kết hợp các lớp theo rủi ro giúp cân bằng tốc độ và độ tin cậy.

## 7. Thiết kế kiểm thử quanh thay đổi và vùng có thể bị ảnh hưởng

Với mỗi thay đổi, lập một ma trận nhỏ nối yêu cầu, thành phần bị tác động, rủi ro, kiểm thử và bằng chứng. Ma trận này giúp kiểm tra rằng các phần quan trọng đều có cách xác nhận.

| Thay đổi | Rủi ro cần xem xét | Kiểm thử ưu tiên | Bằng chứng cần lưu |
|---|---|---|---|
| Sửa quy tắc tính toán | Sai kết quả ở biên, làm tròn, dữ liệu cũ | Kiểm thử đơn vị/đặc trưng với bộ dữ liệu biên; so sánh kết quả trước và sau | Đầu vào, kết quả mong đợi đã xác nhận, kết quả thực tế |
| Thay đổi truy vấn hoặc schema | Mất dữ liệu, sai quan hệ, chậm truy vấn, không tương thích | Kiểm thử tích hợp, migration trên bản sao dữ liệu, kiểm tra ràng buộc và hiệu năng | Script migration, số lượng bản ghi, kiểm tra toàn vẹn, thời gian chạy |
| Thay đổi API hoặc message | Phá hợp đồng với bên gọi hoặc bên nhận | Kiểm thử hợp đồng, kiểm thử tương thích và luồng tích hợp | Đặc tả phiên bản, payload mẫu, kết quả xác nhận |
| Thay đổi phân quyền | Truy cập trái phép hoặc chặn nhầm người dùng hợp lệ | Kiểm thử quyền theo vai trò, trường hợp được phép và bị từ chối | Ma trận vai trò/quyền, kết quả từng trường hợp |
| Thay đổi tác vụ nền | Xử lý lặp, bỏ sót, sai thứ tự hoặc không phục hồi | Kiểm thử retry, idempotency, xử lý lỗi và chạy lại | Dữ liệu đầu vào, trạng thái trước/sau, log và metric |
| Thay đổi giao diện | Luồng thao tác quan trọng bị gián đoạn | Kiểm thử hành trình trọng yếu và kiểm tra thủ công có cấu trúc | Phiên bản, thiết bị, bước thực hiện, ảnh hoặc kết quả |

Kiểm thử nên tập trung vào các điều kiện có thể làm thay đổi kết quả: giá trị biên, dữ liệu rỗng hoặc thiếu, dữ liệu cũ, trạng thái không hợp lệ, lỗi phụ thuộc, yêu cầu lặp lại và xử lý đồng thời nếu có. Chọn dữ liệu sao cho có thể tái lập và không làm lộ dữ liệu cá nhân hoặc bí mật sản xuất.

## 8. Tận dụng kiểm thử thăm dò có cấu trúc

Khi tài liệu thiếu, kiểm thử thăm dò giúp tìm hiểu hệ thống và phát hiện các hành vi chưa được dự đoán. Để kết quả có thể dùng lại, mỗi phiên thăm dò nên có mục tiêu, phạm vi, thời lượng hoặc giới hạn công việc, dữ liệu sử dụng và ghi nhận phát hiện.

Một phiên có thể tập trung vào một câu hỏi, ví dụ: “Điều gì xảy ra nếu một yêu cầu cập nhật được gửi hai lần?”, “Tác vụ có phục hồi khi dịch vụ ngoài tạm thời không phản hồi?” hoặc “Dữ liệu cũ có được đọc đúng sau khi chuyển đổi schema?”. Người kiểm thử ghi lại thao tác, kết quả quan sát, log liên quan, điều kiện tái hiện và các giả thuyết cần kiểm tra tiếp.

Phân loại phát hiện thành lỗi đã tái hiện, hành vi cần xác nhận nghiệp vụ, giới hạn đã biết hoặc câu hỏi chưa đủ bằng chứng. Khi phát hiện quan trọng được xác nhận, chuyển nó thành một trong các đầu ra có thể duy trì: test tự động, kịch bản thủ công, yêu cầu rõ ràng, hồ sơ lỗi hoặc điều kiện giám sát. Không để kiến thức quan trọng chỉ tồn tại trong ghi chú cá nhân.

## 9. Tăng dần khả năng kiểm thử mà không chặn cải tiến

Một lộ trình thực tế có thể chia thành các giai đoạn. Các giai đoạn có thể chồng lấn tùy mức độ rủi ro; không cần đợi toàn bộ hệ thống được kiểm thử mới bắt đầu cải tiến.

### Giai đoạn 1: Khảo sát và bảo vệ thay đổi trước mắt

- Xác định luồng và vùng ảnh hưởng của thay đổi.
- Trao đổi với người hiểu nghiệp vụ và vận hành để tìm hành vi quan trọng, lỗi đã biết và phụ thuộc.
- Chạy các kiểm tra hiện có, ghi lại trạng thái ban đầu và xác định điểm chưa có bằng chứng.
- Viết một số kiểm thử khói hoặc kiểm thử đặc trưng cho luồng có rủi ro cao nhất.
- Chuẩn bị cách quan sát và khôi phục nếu thay đổi gây sự cố.

### Giai đoạn 2: Tạo đường cơ sở có thể lặp lại

- Chọn dữ liệu thử nghiệm an toàn và có thể tái tạo.
- Tự động hóa các kịch bản đặc trưng đã được xác nhận.
- Đưa kiểm thử vào quy trình build hoặc pipeline ở vị trí phù hợp.
- Lưu kết quả, phiên bản mã nguồn, cấu hình và môi trường chạy.
- Phân loại lỗi kiểm thử và lỗi môi trường để tránh mất niềm tin vào bộ kiểm thử.

### Giai đoạn 3: Mở rộng theo rủi ro và tách phụ thuộc

- Bổ sung kiểm thử cho các luồng có tác động lớn hoặc nhiều lỗi lịch sử.
- Tạo điểm thay thế cho cơ sở dữ liệu, dịch vụ ngoài, thời gian và các phụ thuộc khó kiểm soát.
- Tách dần logic nghiệp vụ để có thể kiểm thử ở mức đơn vị.
- Bổ sung kiểm thử hợp đồng cho các ranh giới thường xuyên thay đổi.
- Đưa kiểm thử migration, tương thích và phục hồi vào quy trình khi phù hợp.

### Giai đoạn 4: Duy trì và điều chỉnh

- Theo dõi lỗi lọt qua kiểm thử, độ ổn định, thời gian chạy và chi phí bảo trì.
- Xóa hoặc sửa kiểm thử trùng lặp, lỗi thời hoặc không còn phản ánh yêu cầu.
- Rà soát lại ưu tiên khi kiến trúc, nghiệp vụ hoặc mức rủi ro thay đổi.
- Duy trì chủ sở hữu cho bộ kiểm thử và tài liệu hành vi quan trọng.

Tiến độ nên được đánh giá bằng mức giảm rủi ro và khả năng phản hồi, không chỉ bằng số lượng test mới. Một vài kiểm thử đáng tin cậy bảo vệ luồng quan trọng có thể tạo giá trị lớn hơn một bộ kiểm thử rộng nhưng không ổn định.

## 10. Kiểm soát thay đổi dữ liệu và khả năng quay lui

Hệ thống cũ thường có dữ liệu quan trọng hơn mã nguồn có thể triển khai lại. Vì vậy, thay đổi schema, chuyển đổi dữ liệu, tác vụ batch và đồng bộ với hệ thống ngoài cần được xem xét riêng.

Trước migration hoặc thao tác có tác động dữ liệu, cần xác định:

- Phạm vi bản ghi và bảng hoặc kho dữ liệu bị ảnh hưởng.
- Điều kiện dữ liệu đầu vào, dữ liệu bất thường và cách xử lý bản ghi không hợp lệ.
- Khả năng chạy thử trên bản sao dữ liệu có tính đại diện.
- Điều kiện toàn vẹn trước và sau thay đổi, chẳng hạn số lượng, quan hệ, tổng kiểm soát hoặc quy tắc nghiệp vụ.
- Tính lặp an toàn của thao tác nếu job bị chạy lại hoặc gián đoạn.
- Chiến lược tương thích giữa phiên bản ứng dụng cũ và schema mới trong thời gian chuyển tiếp.
- Cách sao lưu, khôi phục và giới hạn của phương án rollback.

Không mặc định rollback mã nguồn sẽ đảo ngược được dữ liệu đã biến đổi hoặc tác động đã gửi ra hệ thống bên ngoài. Với một số thay đổi, cách an toàn hơn là triển khai theo nhiều bước tương thích ngược, dùng cờ bật/tắt, ghi dữ liệu song song trong thời gian kiểm chứng hoặc chuẩn bị thao tác sửa bù (compensating action). Các phương án này phải được kiểm tra trong môi trường phù hợp trước khi dựa vào chúng trong phát hành thật.

## 11. Xác nhận trước và sau triển khai

Khi bộ hồi quy còn hạn chế, kiểm soát phát hành cần dựa trên tập kiểm tra có chủ đích và khả năng quan sát tốt. Trước triển khai, xác nhận bản dựng đúng, kiểm tra khói, các luồng ưu tiên cao, migration, cấu hình, phụ thuộc và điều kiện rollback. Ghi rõ những vùng chưa được kiểm thử và rủi ro được chấp nhận theo đúng thẩm quyền.

Triển khai theo phạm vi nhỏ hoặc từng bước nếu kiến trúc cho phép. Sau triển khai, quan sát các chỉ số gắn với rủi ro đã nhận diện: tỷ lệ lỗi, độ trễ, hàng đợi, số lượng giao dịch, lỗi tích hợp, tính toàn vẹn dữ liệu và các cảnh báo nghiệp vụ. So sánh với đường cơ sở trước thay đổi, tính đến biến động bình thường và lưu ý rằng metric không thay thế kiểm thử chức năng.

Xác định trước điều kiện dừng hoặc quay lui, người có quyền kích hoạt và cách thông báo. Nếu phát hiện sai lệch, bảo toàn log và dữ liệu chẩn đoán, giới hạn tác động, thực hiện phương án khôi phục đã chuẩn bị và bổ sung kiểm thử để lỗi tương tự có thể được phát hiện ở lần sau. Không chỉ sửa lỗi hiện tại rồi bỏ qua việc cập nhật đường cơ sở hồi quy.

## 12. Ví dụ minh họa: cải tiến một hệ thống quản lý đơn hàng cũ

Giả sử hệ thống quản lý đơn hàng được xây dựng từ lâu, chưa có bộ hồi quy tự động. Nhóm cần thay đổi cách tính trạng thái đơn khi có giao dịch thanh toán và hoàn tiền. Mã xử lý cập nhật trạng thái nằm trong một dịch vụ cũ, có tác vụ nền và tích hợp với cổng thanh toán.

**Khảo sát vùng ảnh hưởng:** nhóm lần theo API nhận kết quả thanh toán, bảng trạng thái đơn, tác vụ đối soát, message gửi sang hệ thống kho và quy trình hoàn tiền. Người vận hành cung cấp các trường hợp đã từng xảy ra như thông báo thanh toán đến trễ, webhook gửi lặp và giao dịch hoàn tiền một phần.

**Xếp ưu tiên:** luồng xác nhận thanh toán và hoàn tiền được xếp ưu tiên cao vì ảnh hưởng trực tiếp đến tiền và trạng thái đơn. Màn hình hiển thị lịch sử được xếp sau nếu có thể truy xuất lại dữ liệu và không làm thay đổi giao dịch.

**Tạo đường cơ sở:** nhóm chọn dữ liệu thử nghiệm đại diện, ghi lại trạng thái đơn trước và sau các tình huống thanh toán thành công, thất bại, webhook lặp, thông báo đến trễ và hoàn tiền một phần. Người phụ trách nghiệp vụ xác nhận kết quả mong đợi. Một hành vi cũ được phát hiện là cập nhật trạng thái hai lần khi webhook lặp được ghi thành lỗi riêng, không được coi là hành vi chuẩn.

**Kiểm thử theo lớp:** nhóm bổ sung kiểm thử đơn vị cho quy tắc chuyển trạng thái sau khi tách được phần logic; kiểm thử tích hợp cho ghi dữ liệu và xử lý webhook; kiểm thử đầu cuối cho một hành trình đặt hàng và thanh toán quan trọng. Kiểm thử retry xác nhận webhook lặp không tạo tác động giao dịch trùng.

**Phát hành có kiểm soát:** trước triển khai, nhóm chạy các kiểm thử ưu tiên cao và xác nhận dữ liệu thử nghiệm. Sau triển khai, theo dõi tỷ lệ webhook lỗi, giao dịch ở trạng thái chờ quá lâu, chênh lệch đối soát và số lần xử lý lặp. Kế hoạch quay lui hoặc xử lý bù được chuẩn bị dựa trên khả năng tương thích của schema và trạng thái giao dịch.

Ví dụ này cho thấy nhóm có thể bảo vệ một thay đổi rủi ro cao bằng tập kiểm thử nhỏ nhưng có chủ đích, đồng thời biến hiểu biết thu được thành bộ hồi quy lâu dài. Các kịch bản và ngưỡng vận hành thực tế phải được xác nhận theo hệ thống cụ thể, không sao chép nguyên xi từ ví dụ.

## 13. Những sai lầm cần tránh

- **Cố xây bộ hồi quy toàn diện trước khi hiểu luồng:** phạm vi quá lớn làm chậm thay đổi và dễ tạo kiểm thử dựa trên giả định sai. Bắt đầu từ vùng ảnh hưởng và rủi ro cao.
- **Đóng băng mọi hành vi cũ:** characterization test có thể ghi nhận cả lỗi lịch sử. Xác nhận hành vi mong muốn trước khi coi nó là chuẩn.
- **Chỉ kiểm thử phần mã vừa sửa:** lỗi có thể xuất hiện ở dữ liệu, tích hợp, tác vụ nền hoặc thành phần dùng chung. Lập bản đồ tác động trước khi chọn test.
- **Chỉ dựa vào kiểm thử thủ công:** kết quả khó tái lập và phụ thuộc người thực hiện. Chuyển các kịch bản quan trọng thành kiểm thử lặp lại được.
- **Tự động hóa kiểm thử không ổn định:** test chập chờn làm giảm niềm tin và khiến nhóm bỏ qua lỗi. Xác định nguyên nhân, cô lập phụ thuộc và theo dõi độ ổn định.
- **Dùng dữ liệu sản xuất thiếu kiểm soát:** có thể làm lộ thông tin hoặc gây tác động thật. Dùng dữ liệu tổng hợp, ẩn danh hoặc bản sao được bảo vệ theo quy định.
- **Coi rollback mã là khôi phục đầy đủ:** dữ liệu và tác động bên ngoài có thể không đảo ngược. Kiểm tra migration, backup và phương án sửa bù.
- **Đo tiến độ bằng số lượng test:** số lượng không phản ánh mức giảm rủi ro. Theo dõi độ bao phủ luồng quan trọng, lỗi lọt, khả năng tái lập và thời gian phản hồi.
- **Không chuyển phát hiện thành tài sản kiểm thử:** lỗi được sửa nhưng không có test ngăn tái diễn. Bổ sung kiểm thử hoặc kiểm soát phù hợp sau mỗi sự cố đáng kể.

## 14. Danh sách kiểm tra khi cải tiến hệ thống thiếu hồi quy

Trước khi bắt đầu thay đổi:

1. Đã xác định luồng nghiệp vụ, thành phần, dữ liệu và phụ thuộc bị ảnh hưởng.
2. Đã hỏi người hiểu nghiệp vụ và vận hành về hành vi quan trọng, lỗi lịch sử và tình huống ngoại lệ.
3. Đã xếp ưu tiên theo tác động, khả năng xảy ra, khả năng phát hiện, khả năng khôi phục và độ không chắc chắn.
4. Đã xác định dữ liệu thử nghiệm an toàn và điều kiện tái lập.
5. Đã chọn các kiểm thử khói, đặc trưng, đơn vị, tích hợp hoặc đầu cuối phù hợp.

Trước khi phát hành:

6. Đã có bằng chứng cho các luồng ưu tiên cao và ghi rõ khoảng trống chưa được kiểm thử.
7. Đã kiểm tra tương thích dữ liệu, migration, tác vụ nền và hợp đồng tích hợp có liên quan.
8. Đã chuẩn bị giám sát, điều kiện dừng, người chịu trách nhiệm và phương án khôi phục.
9. Đã xác định người có thẩm quyền chấp nhận rủi ro còn lại.

Sau khi phát hành:

10. Đã theo dõi các chỉ số và dấu hiệu gắn với rủi ro của thay đổi.
11. Đã lưu kết quả, log và thông tin phiên bản để có thể điều tra.
12. Đã chuyển lỗi hoặc hành vi quan trọng được phát hiện thành kiểm thử hồi quy hoặc tài liệu có thể duy trì.

## 15. Kết luận

Khi cải tiến hệ thống cũ thiếu bộ hồi quy, nhóm cần tiến từng bước dựa trên hiểu biết về luồng nghiệp vụ và rủi ro. Bắt đầu bằng việc lập bản đồ tác động, xác nhận hành vi hiện tại, chọn một số kịch bản có giá trị cao và chuẩn bị cách quan sát cũng như khôi phục. Sau đó, chuyển bằng chứng thành kiểm thử có thể lặp lại và mở rộng phạm vi khi đã hiểu rõ hơn về hệ thống.

Một chiến lược tốt không đo thành công chỉ bằng số lượng kiểm thử được bổ sung. Nó phải giúp nhóm biết thay đổi nào đang được bảo vệ, rủi ro nào còn tồn tại, bằng chứng nào hỗ trợ quyết định phát hành và cách phát hiện hoặc xử lý sai lệch. Cách làm này cho phép hệ thống được cải tiến liên tục trong khi năng lực hồi quy tăng lên cùng với kiến thức của nhóm.
