# Phân bổ nguồn lực vào vùng quan trọng hoặc thay đổi nhiều

## Mục tiêu bài học

Trong chiến lược VALIDATION_TESTING_STRATEGY, nguồn lực kiểm thử luôn có giới hạn: thời gian của nhóm, năng lực chuyên môn, môi trường, dữ liệu, thiết bị và ngân sách tự động hóa đều không thể tăng vô hạn. Vì vậy, nhóm cần quyết định kiểm thử sâu ở đâu, kiểm tra nào cần chạy thường xuyên, phần nào cần chuyên gia tham gia và khu vực nào có thể dùng mức kiểm tra nhẹ hơn.

Một cách tiếp cận hiệu quả là phân bổ nguồn lực theo rủi ro. Những vùng có hậu quả lỗi nghiêm trọng cần được chú ý ngay cả khi ít thay đổi. Những vùng thay đổi thường xuyên cũng cần được xem xét vì mỗi thay đổi có thể tạo lỗi mới hoặc làm mất hiệu lực của bằng chứng cũ. Khi một vùng vừa quan trọng vừa biến động nhiều, mức ưu tiên thường cao hơn và cần sự kết hợp giữa kiểm thử phòng ngừa, kiểm thử thay đổi và giám sát sau phát hành.

Sau bài học, người học có thể:

- Giải thích vì sao cần ưu tiên nguồn lực kiểm thử theo rủi ro thay vì chia đều.
- Nhận diện vùng quan trọng và vùng có mức thay đổi cao.
- Đánh giá khả năng xảy ra lỗi, hậu quả, phạm vi ảnh hưởng và độ bất định của thay đổi.
- Lập thứ tự ưu tiên kiểm thử và phân bổ nhân lực, thời gian, môi trường, dữ liệu.
- Điều chỉnh kế hoạch khi phạm vi, kiến trúc, lịch phát hành hoặc bằng chứng rủi ro thay đổi.
- Đo lường xem nguồn lực đã được tập trung đúng nơi và có làm giảm rủi ro hay không.

## 1. Vì sao không thể phân bổ nguồn lực đồng đều?

Một sản phẩm thường có nhiều thành phần với mức độ quan trọng khác nhau. Một lỗi hiển thị sai biểu tượng có thể gây bất tiện nhỏ; một lỗi phân quyền có thể làm lộ dữ liệu của nhiều khách hàng. Nếu mỗi thành phần đều nhận cùng thời lượng kiểm thử, nhóm có nguy cơ dành quá nhiều công sức cho những khu vực ít ảnh hưởng và không đủ thời gian cho các luồng có hậu quả nghiêm trọng.

Mức độ thay đổi cũng không đồng đều. Một thành phần ổn định có thể đã có bộ kiểm thử đáng tin cậy và ít thay đổi trong nhiều phiên bản. Một thành phần khác có thể được chỉnh sửa liên tục do yêu cầu mới, sửa lỗi, tái cấu trúc, thay đổi thư viện hoặc phụ thuộc bên ngoài. Các thay đổi liên tiếp có thể làm phát sinh lỗi hồi quy, khiến giả định trước đó không còn đúng hoặc làm tăng độ bất định.

Phân bổ theo rủi ro giúp trả lời những câu hỏi thực tế:

- Thành phần nào cần được kiểm thử sâu trước khi phát hành?
- Thay đổi nào cần rà soát tác động và kiểm thử hồi quy mở rộng?
- Luồng nào cần người có chuyên môn bảo mật, dữ liệu hoặc nghiệp vụ tham gia?
- Môi trường và dữ liệu kiểm thử nào cần được ưu tiên?
- Kiểm tra nào cần chạy ở mọi lần tích hợp, kiểm tra nào chỉ cần chạy theo mốc?
- Có thể giảm hoặc chuyển nguồn lực ở đâu mà vẫn duy trì mức rủi ro chấp nhận được?

Mục tiêu không phải là kiểm thử thật nhiều ở mọi nơi. Mục tiêu là dùng nguồn lực có giới hạn để thu thập bằng chứng tốt nhất về những rủi ro có ý nghĩa nhất.

## 2. Hai căn cứ ưu tiên: mức độ quan trọng và mức độ thay đổi

### 2.1. Vùng quan trọng

Một vùng được xem là quan trọng khi lỗi tại đó có thể gây hậu quả lớn đối với người dùng, tổ chức hoặc hệ thống. Mức quan trọng không chỉ phụ thuộc vào số lượng người dùng. Một chức năng ít được sử dụng vẫn có thể rất quan trọng nếu nó kiểm soát quyền truy cập, xử lý dữ liệu nhạy cảm, thực hiện thanh toán hoặc phục hồi sau thảm họa.

Các dấu hiệu thường gặp:

- **Tác động nghiệp vụ:** lỗi làm gián đoạn quy trình cốt lõi, thất thoát doanh thu hoặc ngăn người dùng hoàn thành công việc.
- **Tác động dữ liệu:** lỗi có thể làm mất, sai lệch, nhân bản hoặc tiết lộ dữ liệu.
- **Bảo mật và quyền riêng tư:** vùng liên quan đến xác thực, phân quyền, bí mật, dữ liệu cá nhân hoặc ranh giới tin cậy.
- **An toàn:** lỗi có thể gây tổn hại đến con người, thiết bị hoặc môi trường.
- **Tuân thủ và hợp đồng:** lỗi có thể vi phạm yêu cầu pháp lý, tiêu chuẩn, nghĩa vụ hợp đồng hoặc cam kết dịch vụ.
- **Phạm vi ảnh hưởng:** lỗi ở một thành phần dùng chung có thể lan đến nhiều dịch vụ, khách hàng hoặc luồng nghiệp vụ.
- **Khả năng phục hồi:** lỗi khó phát hiện, khó đảo ngược hoặc cần thời gian dài để khôi phục thường có rủi ro cao hơn.

Nhóm nên ghi rõ vì sao một vùng được xếp quan trọng và ai xác nhận mức độ ảnh hưởng. Nhãn “critical” cần có căn cứ như phân tích tác động nghiệp vụ, phân loại dữ liệu, mô hình đe dọa, SLO hoặc yêu cầu an toàn.

### 2.2. Vùng thay đổi nhiều

Một vùng có mức thay đổi cao khi mã nguồn, cấu hình, dữ liệu, giao diện, hợp đồng hoặc phụ thuộc của nó thường xuyên được sửa đổi. Có thể quan sát mức thay đổi qua:

- Số lần thay đổi trong một khoảng thời gian.
- Số dòng hoặc số tệp bị sửa, nhưng cần xem cùng ngữ cảnh vì số dòng không phản ánh đầy đủ rủi ro.
- Số lượng pull request, commit hoặc bản phát hành chạm đến thành phần.
- Số người hoặc nhóm cùng sửa một khu vực.
- Tần suất thay đổi yêu cầu, thiết kế hoặc hợp đồng API.
- Mức độ thay đổi phụ thuộc bên ngoài, thư viện, nền tảng hoặc cấu hình triển khai.
- Tỷ lệ lỗi, rollback hoặc sự cố sau các thay đổi trước đó.

Không nên coi mọi thay đổi thường xuyên đều có rủi ro cao. Một thay đổi nhỏ, độc lập, có kiểm thử tốt có thể ít rủi ro hơn một thay đổi hiếm gặp nhưng ảnh hưởng đến kiến trúc hoặc dữ liệu cốt lõi. Tần suất thay đổi là tín hiệu để điều tra và điều chỉnh kiểm thử, không phải kết luận duy nhất.

### 2.3. Ma trận quan trọng và biến động

Có thể dùng ma trận hai chiều để bắt đầu phân loại:

| Mức độ quan trọng | Mức thay đổi thấp | Mức thay đổi cao |
|---|---|---|
| Cao | Duy trì kiểm thử nền tảng, kiểm tra định kỳ các điều kiện biên và phụ thuộc; xác nhận mọi thay đổi dù nhỏ. | Ưu tiên cao nhất: phân tích tác động, rà soát chuyên môn, kiểm thử tự động ở nhiều tầng, kiểm thử hồi quy và giám sát sau phát hành. |
| Thấp hơn | Kiểm thử theo phạm vi và lấy mẫu hợp lý; duy trì kiểm tra cơ bản để phát hiện sai lệch. | Tăng kiểm thử tập trung vào thay đổi, kiểm tra tương thích và hồi quy liên quan; theo dõi xu hướng lỗi để điều chỉnh ưu tiên. |

Ma trận này là công cụ sàng lọc, không phải quy tắc cứng. Một vùng được xếp “thấp hơn” vẫn có thể cần ưu tiên cao nếu có lỗ hổng bảo mật mới, thay đổi lớn hoặc dấu hiệu sự cố. Ngược lại, vùng quan trọng nhưng ổn định vẫn cần được kiểm tra ở các mốc thích hợp vì hậu quả lỗi vẫn lớn.

## 3. Đánh giá rủi ro để quyết định mức đầu tư

Một cách phổ biến là xem xét rủi ro theo khả năng xảy ra và mức độ tác động. Có thể mở rộng đánh giá bằng độ khó phát hiện, phạm vi ảnh hưởng và khả năng phục hồi.

### 3.1. Các yếu tố đánh giá

| Yếu tố | Câu hỏi | Ví dụ bằng chứng |
|---|---|---|
| Khả năng xảy ra | Có điều kiện nào làm lỗi dễ phát sinh không? Thành phần có phức tạp hoặc thường xuyên thay đổi không? | Lịch sử lỗi, thay đổi gần đây, độ phức tạp, phụ thuộc và kết quả review. |
| Mức độ tác động | Nếu lỗi xảy ra, người dùng hoặc tổ chức chịu hậu quả gì? | Phân tích tác động nghiệp vụ, phân loại dữ liệu, SLO, yêu cầu an toàn và tuân thủ. |
| Khả năng phát hiện | Nhóm có thể nhận ra lỗi trước khi người dùng bị ảnh hưởng không? | Độ bao phủ giám sát, cảnh báo, kiểm thử tự động, log và khả năng tái hiện. |
| Phạm vi lan truyền | Lỗi có thể ảnh hưởng đến bao nhiêu luồng, dịch vụ hoặc nhóm người dùng? | Sơ đồ phụ thuộc, kiến trúc, luồng dữ liệu và hợp đồng API. |
| Khả năng phục hồi | Có thể rollback, khôi phục dữ liệu hoặc chuyển sang phương án dự phòng nhanh đến mức nào? | Diễn tập phục hồi, backup, rollback plan, thời gian khôi phục và runbook. |
| Độ bất định | Nhóm hiểu rõ thay đổi và tác động của nó đến đâu? | Yêu cầu chưa rõ, thiết kế mới, công nghệ mới, thiếu dữ liệu hoặc thiếu chuyên môn. |

### 3.2. Dùng thang điểm có kiểm soát

Nhóm có thể chấm từng yếu tố theo thang định tính, ví dụ thấp, trung bình, cao hoặc rất cao. Nếu cần một con số để sắp xếp, có thể quy đổi thành thang 1–5 và dùng phép nhân khả năng xảy ra với mức tác động làm điểm sàng lọc. Điểm số chỉ hỗ trợ thảo luận; không nên tạo cảm giác chính xác giả tạo hoặc thay thế phán đoán chuyên môn.

Ví dụ bảng đánh giá ban đầu:

| Thành phần | Khả năng xảy ra | Tác động | Độ bất định/thay đổi | Ưu tiên sơ bộ |
|---|---:|---:|---:|---|
| Dịch vụ phân quyền | 3 | 5 | 3 | Cao do hậu quả truy cập trái phép nghiêm trọng. |
| Bộ tính giá và thanh toán | 4 | 5 | 4 | Rất cao do thay đổi thường xuyên và ảnh hưởng giao dịch. |
| Trang trợ giúp tĩnh | 2 | 1 | 2 | Thấp, trừ khi nội dung có nghĩa vụ pháp lý. |
| Bộ lọc báo cáo nội bộ | 4 | 2 | 4 | Trung bình; cần kiểm thử tập trung vào thay đổi và dữ liệu. |

Các con số trên chỉ minh họa cách thảo luận. Dự án cần thống nhất định nghĩa từng mức, ngưỡng ưu tiên và người có quyền chấp nhận rủi ro. Không cộng hoặc nhân các điểm theo cách máy móc nếu các yếu tố bị trùng lặp hoặc không có dữ liệu đáng tin cậy.

### 3.3. Phân biệt rủi ro sản phẩm và rủi ro dự án

- **Rủi ro sản phẩm** liên quan đến khả năng phần mềm không đáp ứng yêu cầu hoặc gây hậu quả trong sử dụng, ví dụ sai số tiền, mất dữ liệu, lộ thông tin hoặc hệ thống ngừng hoạt động.
- **Rủi ro dự án** liên quan đến khả năng quá trình phát triển và kiểm thử không đạt mục tiêu, ví dụ thiếu người có chuyên môn, môi trường không sẵn sàng, dữ liệu kiểm thử không đủ hoặc thời gian kiểm thử bị rút ngắn.

Hai loại rủi ro có quan hệ với nhau. Thiếu chuyên gia bảo mật là rủi ro dự án có thể làm tăng rủi ro sản phẩm. Kế hoạch phân bổ nguồn lực cần theo dõi cả hai.

## 4. Lập thứ tự ưu tiên kiểm thử

Sau khi đánh giá, nhóm chuyển kết quả thành thứ tự ưu tiên cụ thể. Thứ tự này cần phản ánh cả hậu quả của lỗi và thông tin mới từ thay đổi.

### 4.1. Các câu hỏi khi ưu tiên

1. Nếu vùng này lỗi, ai bị ảnh hưởng và hậu quả nghiêm trọng đến đâu?
2. Vùng này có thay đổi kể từ lần kiểm thử đáng tin cậy gần nhất không?
3. Thay đổi có vượt qua ranh giới thành phần, dữ liệu hoặc quyền truy cập không?
4. Có lỗi tương tự hoặc sự cố lặp lại trong lịch sử không?
5. Có kiểm thử tự động đáng tin cậy và môi trường phù hợp không?
6. Lỗi có thể được phát hiện trước phát hành hay chỉ xuất hiện dưới tải hoặc dữ liệu thực tế?
7. Cần chuyên gia nào để đánh giá đúng rủi ro?
8. Có thể giảm rủi ro bằng kiểm thử, review, giới hạn phát hành, feature flag hoặc giám sát không?

### 4.2. Ví dụ các mức ưu tiên

| Mức | Đặc điểm | Cách phân bổ thường dùng |
|---|---|---|
| P0 – Rất cao | Có thể gây mất an toàn, lộ dữ liệu nghiêm trọng, sai lệch giao dịch cốt lõi hoặc vi phạm nghĩa vụ trọng yếu. | Dành chuyên gia phù hợp; review độc lập; kiểm thử sâu; xác minh thủ công các kịch bản trọng yếu; có cổng phát hành và phương án phục hồi. |
| P1 – Cao | Ảnh hưởng lớn đến luồng chính hoặc thành phần dùng chung; thay đổi phức tạp hoặc có lịch sử lỗi. | Kiểm thử hồi quy mở rộng, tích hợp, hợp đồng, dữ liệu biên và kiểm tra vận hành trước phát hành. |
| P2 – Trung bình | Phạm vi ảnh hưởng giới hạn, có thể phục hồi tương đối dễ, nhưng vẫn có thay đổi đáng kể. | Kiểm thử theo phạm vi thay đổi, các luồng lân cận và kiểm tra tương thích. |
| P3 – Thấp | Hậu quả nhỏ, khu vực cô lập, ít phụ thuộc và có bằng chứng ổn định. | Kiểm tra cơ bản, kiểm thử tự động chung và lấy mẫu theo kế hoạch. |

Mức ưu tiên có thể thay đổi khi xuất hiện bằng chứng mới. Một lỗi bảo mật mới có thể đẩy một thành phần lên P0; một thay đổi được giới hạn bằng feature flag và có phương án tắt rõ ràng có thể giảm một phần rủi ro triển khai, nhưng không làm mất nhu cầu kiểm thử chức năng và bảo mật.

## 5. Phân bổ từng loại nguồn lực

Phân bổ nguồn lực không chỉ là chia số giờ của người kiểm thử. Nhóm cần cân nhắc đồng thời nhân lực, thời gian, môi trường, dữ liệu, công cụ và năng lực vận hành.

### 5.1. Nhân lực và chuyên môn

- Giao vùng quan trọng cho người có hiểu biết về nghiệp vụ và kỹ thuật liên quan.
- Mời chuyên gia bảo mật, dữ liệu, hiệu năng hoặc an toàn tham gia khi rủi ro đòi hỏi.
- Dùng review chéo cho thay đổi ở thành phần cốt lõi hoặc có ảnh hưởng rộng.
- Tránh phụ thuộc vào một cá nhân duy nhất; chia sẻ kiến thức, tài liệu hóa và luân phiên có kiểm soát.
- Dành thời gian cho điều tra nguyên nhân, không chỉ chạy thêm test case khi lỗi liên tục tái diễn.

### 5.2. Thời gian kiểm thử

Thời gian nên được đặt theo mức rủi ro và độ bất định. Thay đổi liên quan đến phân quyền hoặc di trú dữ liệu có thể cần thời gian phân tích tác động, kiểm thử dữ liệu và diễn tập phục hồi. Thay đổi giao diện cô lập có thể cần phạm vi kiểm thử ngắn hơn nếu đã có bằng chứng về thành phần dùng chung.

Không nên cắt phần kiểm thử quan trọng chỉ để giữ ngày phát hành. Nếu thời gian không đủ, nhóm cần giảm phạm vi phát hành, chia nhỏ thay đổi, tăng kiểm soát triển khai hoặc xin quyết định chấp nhận rủi ro từ người có thẩm quyền.

### 5.3. Môi trường và dữ liệu

- Ưu tiên môi trường gần với điều kiện vận hành cho các luồng có rủi ro cao.
- Bảo đảm dữ liệu kiểm thử đại diện cho trường hợp biên, khối lượng lớn và trạng thái bất thường.
- Dùng dữ liệu tổng hợp hoặc đã được bảo vệ phù hợp; không đưa dữ liệu nhạy cảm vào môi trường không được phép.
- Dành tài nguyên môi trường hiệu năng, bảo mật hoặc tương thích cho các thay đổi có ảnh hưởng liên quan.
- Kiểm soát phiên bản cấu hình để kết quả kiểm thử có thể tái lập.

### 5.4. Tự động hóa và công cụ

Tự động hóa có giá trị cao khi kiểm tra được lặp lại thường xuyên, có tiêu chí rõ và kết quả ổn định. Ưu tiên tự động hóa:

- Luồng nghiệp vụ cốt lõi và các trường hợp hồi quy thường gặp.
- Hợp đồng API và giao tiếp giữa thành phần dùng chung.
- Kiểm tra phân quyền, xác thực và quy tắc dữ liệu quan trọng.
- Kiểm tra migration, tính nhất quán và tính toàn vẹn dữ liệu.
- Smoke test sau triển khai và kiểm tra health check.
- Các phép đo hiệu năng có thể lặp lại và so sánh theo phiên bản.

Không nên tự động hóa một kiểm tra không ổn định chỉ để tăng số lượng test. Chi phí bảo trì, thời gian chạy, độ tin cậy và khả năng chẩn đoán lỗi cần được tính vào quyết định đầu tư.

## 6. Chiến lược kiểm thử cho vùng quan trọng

Vùng quan trọng cần nhiều lớp bằng chứng vì hậu quả lỗi lớn. Tùy loại rủi ro, nhóm có thể kết hợp:

- Rà soát yêu cầu, quy tắc nghiệp vụ và thiết kế trước khi triển khai.
- Review mã nguồn độc lập cho thay đổi có ảnh hưởng lớn.
- Kiểm thử đơn vị và kiểm thử thành phần cho các quy tắc cốt lõi.
- Kiểm thử tích hợp và hợp đồng tại ranh giới dịch vụ.
- Kiểm thử đầu cuối cho luồng nghiệp vụ quan trọng.
- Kiểm thử bảo mật, quyền truy cập và xử lý dữ liệu nhạy cảm.
- Kiểm thử tải, độ bền, phục hồi và tình huống phụ thuộc thất bại.
- Xác minh backup, restore, rollback hoặc roll-forward khi phù hợp.
- Giám sát sau phát hành với ngưỡng cảnh báo và người chịu trách nhiệm.

Mức kiểm thử phải tương xứng với hậu quả. Ví dụ, chức năng tính tiền cần kiểm tra quy tắc làm tròn, tiền tệ, thuế, giảm giá, giao dịch lặp, hoàn tiền và tính nhất quán giữa đơn hàng với hóa đơn. Chỉ kiểm tra một luồng thanh toán thành công là chưa đủ để bao phủ các rủi ro chính.

## 7. Chiến lược kiểm thử cho vùng thay đổi nhiều

Vùng thay đổi nhiều cần kiểm thử tập trung vào thay đổi và tác động lan truyền. Một quy trình phù hợp thường gồm:

1. **Phân tích thay đổi:** xác định tệp, thành phần, hợp đồng, cấu hình, dữ liệu và phụ thuộc bị ảnh hưởng.
2. **Đánh giá độ rộng tác động:** xem luồng nào sử dụng thành phần, API nào phụ thuộc và dữ liệu nào có thể bị biến đổi.
3. **Kiểm thử tại nơi thay đổi:** chạy kiểm thử đơn vị, thành phần và các trường hợp biên trực tiếp liên quan.
4. **Kiểm thử tại ranh giới:** xác minh hợp đồng, tương thích ngược, giao tiếp và tích hợp với thành phần phụ thuộc.
5. **Hồi quy có mục tiêu:** chọn các luồng dễ bị ảnh hưởng dựa trên sơ đồ phụ thuộc và lịch sử lỗi.
6. **Kiểm tra sau triển khai:** chạy smoke test, theo dõi log, lỗi, độ trễ và chỉ số nghiệp vụ.
7. **Cập nhật bộ kiểm thử:** bổ sung trường hợp mới khi phát hiện lỗi hoặc khi thay đổi làm xuất hiện rủi ro mới.

Nếu một thành phần thay đổi thường xuyên nhưng kiểm thử hồi quy vẫn luôn chạy toàn bộ, pipeline có thể chậm và gây tắc nghẽn. Có thể chia kiểm thử thành lớp nhanh chạy trên mỗi pull request, lớp tích hợp chạy sau hợp nhất và lớp hồi quy đầy đủ chạy theo mốc hoặc trước phát hành. Việc chọn lớp nào phải dựa trên rủi ro và thời gian phản hồi cần thiết.

### 7.1. Tác động của thay đổi quan trọng hơn số dòng mã

Một thay đổi nhỏ có thể có rủi ro lớn nếu sửa điều kiện phân quyền, cấu hình bảo mật, logic tính tiền hoặc migration dữ liệu. Một thay đổi lớn có thể ít rủi ro hơn nếu nằm trong thành phần cô lập, có hợp đồng ổn định và được kiểm thử tốt.

Khi đánh giá thay đổi, cần xem:

- Thành phần nào được sửa và thành phần đó có vai trò gì?
- Có thay đổi hành vi công khai, API, schema hoặc định dạng dữ liệu không?
- Có thay đổi quyền truy cập, ranh giới tin cậy hoặc xử lý bí mật không?
- Có thay đổi thuật toán, thứ tự xử lý, xử lý đồng thời hoặc cơ chế retry không?
- Có thêm hoặc nâng cấp phụ thuộc bên ngoài không?
- Có thay đổi ảnh hưởng khả năng rollback hoặc tương thích phiên bản không?

## 8. Kết hợp mức quan trọng và mức thay đổi trong kế hoạch

Khi một thành phần vừa quan trọng vừa thay đổi nhiều, cần ưu tiên cả kiểm thử trước khi tích hợp và kiểm soát sau triển khai. Một kế hoạch có thể chia nguồn lực như sau:

| Nhóm vùng | Trọng tâm | Nguồn lực ưu tiên |
|---|---|---|
| Quan trọng, thay đổi nhiều | Giảm xác suất lỗi và giới hạn hậu quả. | Chuyên gia, review độc lập, kiểm thử nhiều tầng, môi trường đại diện, hồi quy mở rộng, giám sát và kế hoạch phục hồi. |
| Quan trọng, ít thay đổi | Bảo đảm các cam kết cốt lõi vẫn đúng. | Kiểm thử nền tảng, kiểm tra định kỳ, xác minh thay đổi phụ thuộc và diễn tập phục hồi. |
| Ít quan trọng hơn, thay đổi nhiều | Phát hiện lỗi do thay đổi mà không làm chậm toàn bộ quy trình. | Kiểm thử tự động theo tác động, smoke test, kiểm tra tương thích và lấy mẫu có chủ đích. |
| Ít quan trọng hơn, ít thay đổi | Duy trì mức bảo vệ hợp lý với chi phí thấp. | Bộ kiểm thử cơ bản, phân tích tĩnh và kiểm tra theo lịch hoặc khi có thay đổi liên quan. |

Không nên gán phần trăm nguồn lực cố định cho từng nhóm nếu chưa có dữ liệu. Tỷ lệ phân bổ cần được điều chỉnh theo quy mô sản phẩm, lịch phát hành, số lượng thay đổi, mức độ trưởng thành của tự động hóa và các rủi ro đang tồn tại.

## 9. Quy trình phân bổ nguồn lực có thể áp dụng

### Bước 1: Lập bản đồ thành phần và luồng nghiệp vụ

Liệt kê các chức năng, dịch vụ, API, dữ liệu và luồng quan trọng. Ghi lại quan hệ phụ thuộc và nhóm chịu trách nhiệm. Đảm bảo bản đồ đủ mới để phản ánh kiến trúc hiện tại.

### Bước 2: Xác định mức quan trọng

Đánh giá tác động đến người dùng, nghiệp vụ, dữ liệu, bảo mật, an toàn, tuân thủ và vận hành. Ghi lại căn cứ và người xác nhận. Không chỉ dựa vào tên gọi hoặc mức độ nổi bật của chức năng.

### Bước 3: Đo mức thay đổi và độ bất định

Xem lịch sử thay đổi, lỗi, sự cố, phụ thuộc mới, mức độ thay đổi yêu cầu và độ phức tạp. Đánh dấu khu vực chưa có đủ bằng chứng hoặc đang được tái cấu trúc lớn.

### Bước 4: Đánh giá và xếp hạng rủi ro

Kết hợp khả năng xảy ra, tác động, khả năng phát hiện, phạm vi lan truyền và khả năng phục hồi. Dùng thang định tính hoặc định lượng nhất quán. Đánh dấu các trường hợp có hậu quả đặc biệt nghiêm trọng để xem xét riêng.

### Bước 5: Xác định bằng chứng cần có

Với từng vùng ưu tiên, xác định các kiểm tra cần thiết, mức bao phủ, dữ liệu, môi trường, người đánh giá và điều kiện phát hành. Chọn kiểm tra theo khả năng phát hiện rủi ro, không chỉ theo số lượng test case.

### Bước 6: Phân bổ nguồn lực và lập lịch

Giao người có chuyên môn phù hợp, đặt thời gian cho phân tích tác động và kiểm thử, đặt chỗ môi trường, chuẩn bị dữ liệu và xác định lớp tự động hóa. Cân đối nguồn lực giữa kiểm thử trước phát hành và giám sát sau phát hành.

### Bước 7: Theo dõi và điều chỉnh

Cập nhật đánh giá khi có thay đổi lớn, lỗi nghiêm trọng, sự cố, thay đổi phụ thuộc hoặc bằng chứng mới. Sau mỗi phiên bản, xem xét liệu nguồn lực có được đặt đúng chỗ và có giảm được rủi ro hay không.

## 10. Ví dụ thực tế: nền tảng thương mại điện tử

Một nền tảng thương mại điện tử có các khu vực: đăng nhập và phân quyền, giỏ hàng, thanh toán, trang nội dung và báo cáo nội bộ. Nhóm có nguồn lực kiểm thử giới hạn và chuẩn bị phát hành phiên bản mới.

- **Đăng nhập và phân quyền:** mức quan trọng cao vì lỗi có thể cho phép truy cập trái phép. Dù mã ít thay đổi, nhóm vẫn duy trì kiểm thử xác thực, phân quyền theo vai trò, phiên hết hạn và kiểm tra bảo mật.
- **Thanh toán:** vừa quan trọng vừa thay đổi nhiều vì nhóm thường bổ sung phương thức thanh toán, mã giảm giá và quy tắc thuế. Nhóm ưu tiên chuyên gia nghiệp vụ, kiểm thử dữ liệu biên, giao dịch lặp, hoàn tiền, tích hợp cổng thanh toán, kiểm thử hồi quy và giám sát tỷ lệ giao dịch thành công.
- **Trang nội dung:** mức quan trọng nghiệp vụ thấp hơn và thay đổi chủ yếu là nội dung. Nhóm dùng kiểm tra liên kết, hiển thị, khả năng truy cập cơ bản và quy trình duyệt nội dung.
- **Báo cáo nội bộ:** thay đổi thường xuyên khi thêm bộ lọc và trường dữ liệu. Nhóm kiểm thử quyền xem dữ liệu, tính đúng của truy vấn và hồi quy các báo cáo được sử dụng nhiều; không cần chạy mọi kịch bản thanh toán ở mỗi lần sửa bộ lọc.

Khi nhóm phát hiện một thay đổi trong dịch vụ phân quyền ảnh hưởng đến API thanh toán, ưu tiên được cập nhật ngay. Dù pull request chỉ sửa một điều kiện, phạm vi kiểm thử cần bao gồm các vai trò, luồng thanh toán và kiểm tra truy cập dữ liệu liên quan. Sau triển khai, nhóm theo dõi lỗi từ chối giao dịch và dấu hiệu truy cập bất thường.

Ví dụ cho thấy nguồn lực cần đi theo tác động và quan hệ phụ thuộc. Một thành phần ít thay đổi vẫn cần kiểm thử nền tảng nếu hậu quả lỗi lớn; một thành phần thay đổi nhiều cần kiểm thử hồi quy tập trung theo từng thay đổi.

## 11. Đo lường hiệu quả phân bổ nguồn lực

Không chỉ đo số giờ kiểm thử hoặc số test case. Nhóm cần đánh giá cả kết quả chất lượng và hiệu quả sử dụng nguồn lực.

| Nhóm đo lường | Chỉ số tham khảo | Cách diễn giải |
|---|---|---|
| Rủi ro và chất lượng | Lỗi lọt ra môi trường vận hành theo mức độ; sự cố nghiêm trọng; lỗi tái diễn; tỷ lệ thay đổi gây sự cố. | Kiểm tra vùng ưu tiên có giảm được lỗi có hậu quả lớn hay không. |
| Độ bao phủ rủi ro | Tỷ lệ rủi ro quan trọng có kiểm tra hoặc biện pháp kiểm soát; yêu cầu trọng yếu có bằng chứng. | Đánh giá nhóm có kiểm tra đúng các mối nguy đã xác định không. |
| Hiệu quả phản hồi | Thời gian pipeline; thời gian phát hiện lỗi; thời gian tái hiện và chẩn đoán. | Xác định nơi kiểm thử gây tắc nghẽn hoặc phản hồi quá muộn. |
| Phục hồi | Thời gian khôi phục; tỷ lệ rollback thành công; kết quả diễn tập restore. | Đánh giá khả năng giới hạn hậu quả khi lỗi lọt qua. |
| Sử dụng nguồn lực | Thời gian chuyên gia dành cho vùng rủi ro cao; thời gian chờ môi trường; công sức bảo trì kiểm thử. | Phát hiện nguồn lực bị sử dụng sai chỗ hoặc phụ thuộc vào cá nhân. |
| Ổn định thay đổi | Lỗi theo thành phần và loại thay đổi; tỷ lệ hồi quy thất bại sau thay đổi. | Xác định khu vực biến động cần phân tích sâu hoặc cải thiện thiết kế. |

Cần đọc chỉ số cùng bối cảnh. Số lỗi phát hiện tăng có thể do kiểm thử tốt hơn chứ không nhất thiết sản phẩm kém đi. Tỷ lệ pass cao có thể chỉ phản ánh bộ kiểm thử ít bao phủ rủi ro. Giảm thời gian kiểm thử nhưng tăng lỗi nghiêm trọng sau phát hành là dấu hiệu phân bổ không hiệu quả.

Có thể xem xét hiệu quả theo từng phiên bản: rủi ro nào đã được kiểm tra, nguồn lực nào đã sử dụng, lỗi nào lọt qua, biện pháp nào phát huy tác dụng và vùng nào cần điều chỉnh ưu tiên.

## 12. Những sai lầm thường gặp

- **Chia đều thời gian cho mọi thành phần:** bỏ qua khác biệt về hậu quả và mức độ biến động.
- **Chỉ ưu tiên vùng thay đổi nhiều:** có thể bỏ sót thành phần ổn định nhưng rất quan trọng như phân quyền, mã hóa hoặc khôi phục dữ liệu.
- **Chỉ ưu tiên vùng quan trọng:** có thể bỏ qua một thành phần ít quan trọng hơn nhưng đang thay đổi liên tục và có lỗi hồi quy lặp lại.
- **Dùng số dòng mã làm thước đo rủi ro:** không phản ánh đầy đủ thay đổi về hợp đồng, dữ liệu, quyền truy cập hoặc phụ thuộc.
- **Dùng điểm số như sự thật tuyệt đối:** dữ liệu đầu vào có thể chủ quan hoặc thiếu; cần ghi rõ giả định và rà soát khi có bằng chứng mới.
- **Dồn mọi kiểm thử vào cuối chu kỳ:** lỗi ở vùng rủi ro cao được phát hiện muộn, làm tăng chi phí sửa và gây áp lực phát hành.
- **Tự động hóa mọi thứ:** kiểm thử không ổn định hoặc không có giá trị phát hiện rủi ro có thể làm pipeline chậm và giảm niềm tin.
- **Không cập nhật bản đồ phụ thuộc:** thay đổi ở một thành phần có thể ảnh hưởng các luồng mà kế hoạch cũ không còn nhận diện.
- **Bỏ qua năng lực phục hồi:** kiểm thử trước phát hành không thay thế cho backup, rollback, giám sát và diễn tập ứng phó.
- **Không dành nguồn lực cho việc cải thiện hệ thống kiểm thử:** bộ kiểm thử cũ, dữ liệu kém và môi trường không ổn định sẽ làm mọi lần kiểm thử sau đó kém hiệu quả.

## 13. Checklist trước khi chốt phân bổ nguồn lực

- [ ] Đã lập bản đồ thành phần, luồng nghiệp vụ và phụ thuộc chính.
- [ ] Đã xác định vùng quan trọng dựa trên tác động nghiệp vụ, dữ liệu, bảo mật, an toàn và tuân thủ.
- [ ] Đã xem lịch sử thay đổi, lỗi, sự cố và độ bất định.
- [ ] Đã đánh giá khả năng xảy ra, tác động, khả năng phát hiện và khả năng phục hồi.
- [ ] Đã xếp thứ tự ưu tiên và ghi rõ căn cứ.
- [ ] Đã xác định loại kiểm thử và bằng chứng cần có cho từng vùng.
- [ ] Đã phân bổ người, thời gian, môi trường, dữ liệu và công cụ phù hợp.
- [ ] Đã có kiểm thử hồi quy theo tác động thay đổi.
- [ ] Đã có giám sát, phương án phục hồi và người chịu trách nhiệm cho vùng quan trọng.
- [ ] Đã xác định chỉ số để đánh giá và cập nhật phân bổ sau mỗi chu kỳ.

## Kết luận

Nguồn lực kiểm thử cần được phân bổ theo rủi ro, dựa trên mức độ quan trọng, mức độ thay đổi, phạm vi ảnh hưởng và khả năng phục hồi. Vùng quan trọng cần bằng chứng đủ sâu dù ít thay đổi; vùng biến động cần phân tích tác động và hồi quy có mục tiêu; vùng vừa quan trọng vừa biến động cần ưu tiên cao nhất. Đánh giá phải được cập nhật theo bằng chứng mới để thời gian, chuyên môn, môi trường và tự động hóa luôn tập trung vào nơi có thể giảm rủi ro nhiều nhất.
