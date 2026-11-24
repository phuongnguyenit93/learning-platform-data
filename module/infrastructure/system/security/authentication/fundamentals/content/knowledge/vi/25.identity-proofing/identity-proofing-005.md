# Biometric verification — Xác minh sinh trắc học trong định danh

> **Chương:** Identity proofing  
> **Chủ đề:** Biometric verification  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào vai trò của sinh trắc học trong quy trình chứng minh danh tính, cách thu nhận và so khớp mẫu sinh trắc, phát hiện giả mạo, đánh giá sai số, bảo vệ dữ liệu nhạy cảm và thiết kế phương án thay thế an toàn.

## 1. Biometric verification là gì?

**Biometric verification (xác minh sinh trắc học)** là quá trình đo một hoặc nhiều đặc điểm sinh học/hành vi của một người rồi so sánh với mẫu tham chiếu đã được liên kết với một danh tính hoặc tài khoản. Hệ thống đưa ra kết quả dựa trên độ tương đồng và ngưỡng quyết định đã cấu hình.

Các đặc điểm có thể dùng gồm khuôn mặt, vân tay, mống mắt, giọng nói hoặc một số đặc trưng hành vi. Ví dụ, một dịch vụ mở tài khoản từ xa yêu cầu người đăng ký chụp giấy tờ định danh và quay video khuôn mặt. Hệ thống kiểm tra giấy tờ, đánh giá người đang tương tác có phải người hiện diện thật hay không, rồi so khớp khuôn mặt với ảnh tham chiếu trên giấy tờ hoặc nguồn tin cậy phù hợp. Kết quả này là một phần của quy trình identity proofing.

Sinh trắc học có thể giúp trả lời câu hỏi “mẫu đang được thu nhận có tương đồng với mẫu tham chiếu của người đã khai báo hay không?”. Nó không tự chứng minh mọi thuộc tính pháp lý, quyền sở hữu tài khoản, sự đồng ý của người đó hoặc tính hợp lệ của giấy tờ. Một kết quả match cao cũng không thay thế việc xác minh nguồn gốc và tính xác thực của bằng chứng định danh.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt biometric verification, biometric identification, biometric authentication và identity proofing.
2. Mô tả vòng đời từ thu nhận mẫu, tạo template, liên kết danh tính, so khớp đến lưu kết quả.
3. Giải thích liveness detection và Presentation Attack Detection (PAD).
4. Đọc và diễn giải các chỉ số FAR, FRR, FMR, FNMR, FTE và FTA.
5. Đánh giá ảnh hưởng của ngưỡng match, chất lượng mẫu, điều kiện môi trường và nhóm người dùng.
6. Thiết kế bảo vệ template sinh trắc học, quyền riêng tư, retention và xóa dữ liệu.
7. Xây dựng fallback/recovery để người không thể hoặc không muốn dùng sinh trắc vẫn có lối đi phù hợp.
8. Tích hợp sinh trắc học với identity proofing, passkey, MFA, session và chính sách assurance mà không đánh đồng các cơ chế.

## 2. Phân biệt verification, identification, authentication và proofing

Các thuật ngữ liên quan nhưng giải quyết các câu hỏi khác nhau.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Biometric verification (1:1)** | Mẫu vừa thu nhận có khớp với mẫu tham chiếu của danh tính đã khai báo không? | Người dùng khai mình là Mai; hệ thống so khuôn mặt hiện tại với ảnh tham chiếu của Mai. |
| **Biometric identification (1:N)** | Mẫu này có thể thuộc về ai trong một tập hợp mẫu? | Tìm khuôn mặt trong một gallery lớn. |
| **Biometric authentication** | Người đang truy cập có đáp ứng phép kiểm tra sinh trắc đã đăng ký cho credential/account không? | Mở khóa thiết bị bằng vân tay đã enroll. |
| **Identity proofing** | Bằng chứng và người đăng ký có đủ căn cứ để thiết lập một danh tính trong hệ thống không? | Kiểm tra giấy tờ, nguồn phát hành, người hiện diện và đối chiếu dữ liệu. |
| **Authorization** | Danh tính đã được xác minh có quyền thực hiện hành động cụ thể không? | Tài khoản được phép xem hồ sơ nào. |

Verification thường là phép so khớp một-một với một danh tính đã được khai báo hoặc xác lập. Identification là tìm kiếm một-nhiều, có rủi ro riêng về quyền riêng tư, giám sát và false match. Không nên gọi mọi hoạt động nhận diện khuôn mặt là “xác minh” nếu hệ thống thực tế đang tìm một người trong một tập dữ liệu.

**Biometric match không đồng nghĩa identity proofing hoàn tất.** Quy trình proofing có thể cần kiểm tra giấy tờ, tính hợp lệ của nguồn cấp, dữ liệu thuộc tính, sự hiện diện của người đăng ký, quyền đại diện và các bước giải quyết ngoại lệ.

## 3. Sinh trắc học đứng ở đâu trong identity proofing?

Identity proofing thiết lập mối liên hệ giữa một người hiện diện, bằng chứng định danh và một danh tính mà hệ thống sẽ quản lý. Sinh trắc học có thể hỗ trợ khâu xác minh người đang tương tác có tương đồng với người trên bằng chứng hoặc mẫu tham chiếu đã tin cậy.

Một quy trình từ xa có thể gồm:

1. Thu thập thuộc tính được khai báo và xác định mục đích proofing.
2. Thu nhận giấy tờ hoặc bằng chứng định danh phù hợp.
3. Kiểm tra tính xác thực, thời hạn và nguồn phát hành của bằng chứng.
4. Thu nhận mẫu sinh trắc trong một phiên được bảo vệ.
5. Kiểm tra chất lượng mẫu và phát hiện presentation attack.
6. So khớp mẫu sống với ảnh/mẫu tham chiếu được phép sử dụng.
7. Đánh giá kết quả cùng các tín hiệu khác, xử lý ngoại lệ và review khi cần.
8. Ghi kết quả proofing, assurance, provenance và thời điểm.
9. Chỉ sau khi policy đạt mới tạo hoặc liên kết account.

~~~mermaid
flowchart TD
    A["Người đăng ký khai báo danh tính"] --> B["Thu thập bằng chứng định danh"]
    B --> C["Kiểm tra nguồn, tính hợp lệ và thuộc tính"]
    C --> D["Thu nhận mẫu sinh trắc"]
    D --> E["Kiểm tra chất lượng + PAD"]
    E --> F["So khớp 1:1 với mẫu tham chiếu"]
    F --> G{"Kết quả và policy đạt?"}
    G -- "Không rõ / rủi ro cao" --> H["Review hoặc phương án thay thế"]
    G -- "Không đạt" --> I["Từ chối hoặc yêu cầu thu nhận lại"]
    G -- "Đạt" --> J["Đánh giá tổng hợp identity proofing"]
    H --> J
    J --> K["Ghi provenance và assurance"]
    K --> L["Thiết lập / liên kết account"]
~~~

Một phép so khớp thành công chỉ là một tín hiệu. RP hoặc hệ thống proofing cần biết mẫu tham chiếu đến từ đâu, có được phép dùng cho mục đích này không, đã được xác minh ra sao và có đủ chất lượng hay không.

## 4. Các phương thức sinh trắc học

| Phương thức | Đặc điểm | Yếu tố ảnh hưởng | Lưu ý bảo mật/vận hành |
| --- | --- | --- | --- |
| **Khuôn mặt** | Đặc trưng hình học/biểu diễn từ ảnh hoặc video | Ánh sáng, góc, camera, tuổi, biểu cảm, che mặt | Cần PAD, chống ảnh/video phát lại và kiểm soát injection. |
| **Vân tay** | Đặc trưng đường vân và minutiae | Da khô/ướt, vết thương, cảm biến, vị trí đặt ngón | Chất lượng cảm biến và khả năng giả mạo cần được đánh giá. |
| **Mống mắt** | Mẫu đặc trưng vùng mống mắt | Ánh sáng, khoảng cách, kính/che mắt, chất lượng camera | Cần cảm biến và quy trình thu nhận phù hợp. |
| **Giọng nói** | Đặc trưng giọng và cách phát âm | Tiếng ồn, bệnh, cảm xúc, micro, codec | Dễ chịu tác động bởi ghi âm, tổng hợp giọng và replay. |
| **Hành vi** | Nhịp gõ, cách cầm thiết bị, dáng đi hoặc mẫu tương tác | Thiết bị, hoạt động, sức khỏe, môi trường | Có thể biến đổi theo thời gian; thường phù hợp như tín hiệu bổ sung. |

Không có phương thức nào luôn chính xác hoặc phù hợp với mọi người. Lựa chọn cần dựa trên mục đích, môi trường, nhóm người dùng, thiết bị, rủi ro giả mạo, quyền riêng tư và khả năng cung cấp phương án thay thế.

## 5. Enrollment: thu nhận và liên kết mẫu tham chiếu

**Enrollment (đăng ký mẫu sinh trắc)** là quá trình thu nhận dữ liệu ban đầu, kiểm tra chất lượng, tạo template và liên kết template với một danh tính/tài khoản hoặc credential. Nếu enrollment sai, mọi lần so khớp sau đó có thể chính xác về mặt kỹ thuật nhưng gắn với sai người.

Một enrollment có kiểm soát cần:

- Xác định danh tính và nguồn tham chiếu trước khi tạo liên kết.
- Xác minh người đang enrollment được phép đăng ký cho account đó.
- Thu nhận qua thiết bị/kênh được tin cậy và bảo vệ đường truyền.
- Kiểm tra chất lượng, độ đầy đủ và tính nhất quán của nhiều lần capture khi cần.
- Chạy PAD phù hợp với phương thức và threat model.
- Tạo template theo thuật toán và phiên bản đã được quản trị.
- Gắn template với account/credential bằng định danh nội bộ, không chỉ email.
- Ghi nguồn, thời điểm, thiết bị/cảm biến và phiên bản quy trình cần thiết cho audit.
- Thông báo cho chủ thể và cung cấp quy trình sửa, thu hồi hoặc xóa theo policy.

### Chất lượng enrollment

Mẫu kém chất lượng có thể làm tăng false reject hoặc khiến người dùng phải enroll lại nhiều lần. Hệ thống nên kiểm tra quality gate trước khi lưu template, cung cấp hướng dẫn dễ hiểu và không ép người dùng thực hiện vô hạn. Nếu không thể thu được mẫu đạt yêu cầu, phải có phương án thay thế.

### Liên kết đúng account

Không cho client gửi account ID bất kỳ rồi lưu template vào account đó. Server phải xác định principal từ phiên đủ tin cậy, xác minh quyền enrollment và có thể yêu cầu step-up. Việc thêm một phương thức sinh trắc mới là thay đổi credential nhạy cảm và cần audit, thông báo, kiểm soát recovery.

## 6. Raw sample và biometric template

Hai loại dữ liệu này cần được phân biệt:

- **Raw sample:** ảnh, video, âm thanh hoặc dữ liệu cảm biến thu nhận ban đầu.
- **Biometric template:** biểu diễn đặc trưng được thuật toán tạo ra để so sánh; không nhất thiết là ảnh gốc và không nhất thiết có thể chuyển ngược thành ảnh, nhưng vẫn là dữ liệu nhạy cảm.

Template không phải lúc nào cũng “không thể đảo ngược”. Mức độ có thể tái dựng hoặc liên kết danh tính phụ thuộc thuật toán, định dạng, dữ liệu phụ trợ và khả năng của attacker. Vì vậy không được xem template là dữ liệu vô hại.

Nguyên tắc thiết kế:
- Tránh lưu raw sample nếu không cần cho mục đích đã công bố.
- Nếu cần giữ để review, giới hạn thời gian, mã hóa và phân quyền rất chặt.
- Dùng template format được quản trị, kiểm soát phiên bản và thuật toán.
- Tách template khỏi dữ liệu profile và bảng account khi kiến trúc cho phép.
- Không dùng template sinh trắc làm password hoặc token để gửi qua mạng.
- Không ghi ảnh, video, audio hoặc template vào log/analytics.
- Đánh giá rủi ro liên kết template giữa các dịch vụ và nhà cung cấp.

## 7. Matching: cách hệ thống đưa ra quyết định

Một hệ thống matching thường thực hiện:

1. Nhận mẫu mới từ sensor hoặc kênh capture.
2. Kiểm tra format, quality và tính đầy đủ.
3. Chạy PAD/liveness nếu flow yêu cầu.
4. Trích xuất đặc trưng bằng thuật toán.
5. So sánh đặc trưng với template tham chiếu.
6. Tính similarity score hoặc distance score.
7. So sánh score với threshold đã chọn.
8. Trả kết quả theo policy, đồng thời giữ thông tin về chất lượng và lý do không thể kết luận.

Không nên diễn giải score như xác suất tuyệt đối rằng người đó đúng là chủ thể. Score phụ thuộc model, dữ liệu, điều kiện capture, thuật toán, threshold và cách vendor hiệu chuẩn. Hai hệ thống có score 0.82 không nhất thiết có cùng ý nghĩa.

### Threshold

Nếu hệ thống dùng similarity score mà score cao biểu thị giống nhau:
- threshold thấp hơn thường chấp nhận nhiều trường hợp hơn, giảm false reject nhưng có thể tăng false accept;
- threshold cao hơn thường nghiêm ngặt hơn, giảm false accept nhưng có thể tăng false reject.

Với distance score, chiều diễn giải có thể ngược lại. Luôn đọc tài liệu thuật toán và kết quả đánh giá của nhà cung cấp trước khi cấu hình.

Không thay threshold chỉ để tăng conversion rate mà không đánh giá lại rủi ro và phân bố sai số. Threshold cần được chọn theo mục đích, mức thiệt hại nếu chấp nhận sai và khả năng review/fallback.

## 8. Chỉ số đánh giá và sai số sinh trắc

Sinh trắc học là phép đo xác suất; không có hệ thống thực tế nào nên được mô tả như “chính xác tuyệt đối”.

| Chỉ số | Ý nghĩa |
| --- | --- |
| **FAR — False Acceptance Rate** | Tỷ lệ trường hợp không khớp bị hệ thống chấp nhận trong một thiết lập thử nghiệm. |
| **FRR — False Rejection Rate** | Tỷ lệ trường hợp khớp hợp lệ bị hệ thống từ chối. |
| **FMR — False Match Rate** | Tỷ lệ so sánh giữa hai mẫu khác người nhưng hệ thống cho là match. |
| **FNMR — False Non-Match Rate** | Tỷ lệ so sánh giữa hai mẫu cùng người nhưng hệ thống cho là non-match. |
| **FTE — Failure to Enroll** | Tỷ lệ người không thể hoàn tất enrollment đạt yêu cầu. |
| **FTA — Failure to Acquire** | Tỷ lệ lần thu nhận không tạo được mẫu đủ điều kiện để xử lý. |
| **EER — Equal Error Rate** | Điểm mà một số định nghĩa FMR/FNMR bằng nhau; hữu ích để so sánh nhưng không nhất thiết là threshold vận hành phù hợp. |

FAR/FRR và FMR/FNMR có thể được định nghĩa ở các tầng đo khác nhau trong tài liệu tiêu chuẩn/vendor. Khi so sánh sản phẩm, phải xác nhận định nghĩa, tập dữ liệu, số lần thử, threshold, điều kiện capture và cách tính.

### Không chỉ xem một con số

Đánh giá cần bao gồm:
- hiệu năng ở threshold triển khai thực tế;
- phân bố sai số theo nhóm dân số và điều kiện sử dụng;
- tỷ lệ FTA/FTE và số lần người dùng phải thử lại;
- hiệu năng trong điều kiện camera/micro/thiết bị thực tế;
- khả năng phát hiện presentation attack;
- độ trễ, tỷ lệ timeout và tỷ lệ cần human review;
- tác động của cập nhật model hoặc thay đổi sensor.

Kết quả thử nghiệm trong phòng lab không tự động phản ánh hiệu năng ngoài đời. Cần pilot có giám sát, đo false accept/reject và có phương án xử lý khi sai số vượt ngưỡng.

## 9. Liveness detection và Presentation Attack Detection

**Liveness detection** thường được dùng để đánh giá mẫu có xuất phát từ một người hiện diện trong quá trình capture hay không. **Presentation Attack Detection (PAD)** là thuật ngữ rộng hơn cho các cơ chế phát hiện mẫu được trình bày cho sensor nhằm đánh lừa hệ thống.

Ví dụ presentation attack:
- Ảnh in hoặc ảnh hiển thị trên màn hình.
- Video/recording phát lại.
- Mặt nạ hoặc vật thể mô phỏng đặc điểm sinh trắc.
- Bản ghi giọng nói được phát qua loa.
- Vân tay giả từ vật liệu mô phỏng.
- Mẫu được trình bày qua thiết bị trung gian hoặc injection vào luồng camera/micro.

PAD có thể sử dụng tín hiệu chủ động hoặc thụ động, kiểm tra chuyển động, chiều sâu, phản xạ, texture, challenge-response, tín hiệu sensor hoặc mô hình học máy. Không có một phép kiểm tra đơn giản nào ngăn mọi loại attack.

### PAD không đồng nghĩa xác minh danh tính

Một người thật đang đứng trước camera có thể vượt liveness nhưng không phải người có danh tính được khai báo. Ngược lại, một người thật có thể bị PAD từ chối do ánh sáng, thiết bị hoặc điều kiện sức khỏe. Vì vậy cần tách:
- kiểm tra mẫu đến từ presentation hợp lệ;
- so khớp với danh tính tham chiếu;
- xác minh bằng chứng định danh;
- đánh giá tổng thể identity proofing.

### Injection và virtual camera

PAD ở tầng hình ảnh có thể không phát hiện được dữ liệu đã bị chèn vào trước khi đến sensor hoặc SDK. Với remote proofing, cần đánh giá cả chuỗi capture: ứng dụng, browser, camera API, OS, SDK, transport và backend. Ràng buộc thiết bị, attestation hoặc kiểm tra integrity có thể bổ sung tín hiệu, nhưng cũng có giới hạn và không nên được coi là bảo đảm tuyệt đối.

## 10. Deepfake và tấn công đa phương thức

Các công cụ tổng hợp ảnh/video/giọng nói làm tăng rủi ro đối với hệ thống remote verification. Attacker có thể:
- phát video deepfake trước camera;
- dùng face swap theo thời gian thực;
- tạo giọng nói tổng hợp để qua voice verification;
- phối hợp ảnh giấy tờ giả và khuôn mặt tổng hợp;
- điều khiển luồng capture hoặc thay thế media stream;
- relay một người thật ở xa để vượt kiểm tra hiện diện nhưng thực hiện giao dịch cho attacker.

Kiểm soát có thể gồm:
- PAD được đánh giá độc lập cho attack presentation phù hợp;
- kiểm tra tính toàn vẹn của luồng capture;
- challenge ngẫu nhiên có thời hạn, gắn với phiên và không lặp;
- kiểm tra nhất quán giữa giấy tờ, mẫu sinh trắc và dữ liệu phiên;
- phân tích tín hiệu thiết bị/kênh và bất thường;
- human review cho trường hợp rủi ro cao hoặc không chắc chắn;
- step-up bằng phương thức độc lập khi phù hợp.

Không dựa vào một động tác yêu cầu người dùng chớp mắt hoặc quay đầu như bằng chứng chắc chắn. Challenge có thể bị ghi trước, điều khiển hoặc tổng hợp; cần đánh giá phương thức PAD trong threat model thực tế.

## 11. Ngưỡng quyết định và xử lý kết quả không chắc chắn

Một hệ thống tốt không chỉ có hai trạng thái “pass/fail”. Có thể cần ít nhất các kết quả:

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| **Match** | Score đạt threshold và các kiểm tra bắt buộc thành công | Tiếp tục đánh giá proofing theo policy. |
| **Non-match** | Score dưới threshold | Có thể thu nhận lại có giới hạn hoặc dùng phương án thay thế. |
| **Inconclusive** | Chất lượng, score hoặc tín hiệu không đủ để kết luận | Hướng dẫn capture lại hoặc chuyển review. |
| **PAD failure** | Phát hiện hoặc nghi presentation attack | Dừng flow, bảo toàn audit cần thiết và áp dụng risk response. |
| **Capture failure** | Không có mẫu hợp lệ để so khớp | Kiểm tra thiết bị/điều kiện, cung cấp alternative. |
| **Service error** | Timeout, provider unavailable hoặc lỗi kỹ thuật | Không coi lỗi kỹ thuật là non-match hoặc match; xử lý theo availability policy. |

Không được biến timeout của nhà cung cấp thành “match thành công”. Cũng không nên tự động khóa tài khoản vĩnh viễn sau một vài false reject do điều kiện capture. Cần rate limit, cooldown, giám sát abuse và lối xử lý hỗ trợ.

## 12. Sai lệch, công bằng và khả năng tiếp cận

Hiệu năng sinh trắc có thể khác nhau theo:
- độ tuổi và thay đổi đặc điểm theo thời gian;
- màu da, giới tính, đặc điểm khuôn mặt và nhóm dân số;
- khuyết tật, chấn thương, bệnh lý hoặc thay đổi sinh học;
- điều kiện ánh sáng, tiếng ồn, camera/micro và băng thông;
- cách người dùng thực hiện thao tác hoặc khả năng hiểu hướng dẫn.

Một tỷ lệ trung bình tốt có thể che giấu nhóm người bị false reject cao hơn. Tổ chức cần đánh giá hiệu năng theo nhóm có liên quan, trong giới hạn pháp lý và quyền riêng tư; kiểm tra dữ liệu huấn luyện/validation của vendor và đo thực tế trong population mục tiêu.

### Thiết kế công bằng

- Cung cấp phương án thay thế có mức assurance phù hợp.
- Hướng dẫn rõ cách thu nhận và lý do mẫu chưa đạt, tránh thông báo mơ hồ.
- Không ép người dùng thử lại vô hạn.
- Có human review và quy trình khiếu nại.
- Kiểm thử với thiết bị phổ biến và điều kiện thực tế.
- Theo dõi chênh lệch FMR/FNMR, FTA/FTE giữa nhóm.
- Đánh giá model/version mới trước khi triển khai rộng.

Fallback không nên trở thành một đường yếu cho attacker. Cần bảo đảm phương án thay thế đủ tin cậy, dễ tiếp cận và được kiểm soát tương xứng với mục tiêu proofing.

## 13. Bảo vệ template và quyền riêng tư

Dữ liệu sinh trắc có tính nhạy cảm đặc biệt: người dùng không thể dễ dàng thay khuôn mặt, mống mắt hoặc vân tay như thay password. Khi template bị lộ, tác động có thể kéo dài và khó khắc phục.

Các nguyên tắc bảo vệ:
- **Data minimization:** chỉ thu thập modality và thuộc tính cần thiết.
- **Purpose limitation:** không dùng lại mẫu cho nhận diện, quảng cáo hoặc giám sát ngoài mục đích đã thông báo.
- **Encryption in transit and at rest:** bảo vệ khi truyền và lưu.
- **Access control:** giới hạn service/operator được truy cập; phân tách vai trò và audit.
- **Template isolation:** tách kho template khỏi profile/account database nếu phù hợp.
- **Retention:** xóa raw sample và template khi hết mục đích hoặc theo yêu cầu hợp lệ.
- **Key management:** quản lý khóa mã hóa riêng, rotation và truy cập có kiểm soát.
- **Vendor governance:** biết dữ liệu được xử lý ở đâu, ai là processor, có subcontractor nào và cách xóa/ứng phó sự cố.

Mã hóa at rest không giải quyết mọi rủi ro nếu ứng dụng có quyền giải mã rộng. Cần giới hạn đường truy cập, bảo vệ key, giám sát truy vấn và đánh giá insider threat.

### Cancelable biometrics và template transformation

Một số thiết kế biến đổi template theo ứng dụng hoặc secret để giảm khả năng liên kết giữa hệ thống và hỗ trợ thay thế representation khi có sự cố. Đây không phải phép màu: cần đánh giá khả năng đảo ngược, liên kết, va chạm và mức độ bảo vệ của thuật toán. Không tuyên bố template “có thể đổi như password” nếu kiến trúc chỉ lưu một template sinh trắc cố định.

## 14. Consent, thông báo và retention

Việc thu thập sinh trắc cần mục đích rõ, thông báo dễ hiểu và cơ sở xử lý phù hợp với luật áp dụng. Tùy bối cảnh, consent có thể là một căn cứ hoặc cần căn cứ khác; không nên mặc định một checkbox đồng ý luôn giải quyết đầy đủ nghĩa vụ pháp lý.

Thông tin người dùng cần hiểu:
- dữ liệu nào được thu thập (ảnh, video, audio, template, metadata);
- mục đích và bước xử lý;
- dữ liệu được lưu ở đâu, trong bao lâu;
- bên cung cấp dịch vụ nào có thể xử lý;
- dữ liệu có được dùng cho mục đích khác hay không;
- cách rút lại sự đồng ý/yêu cầu xóa khi áp dụng;
- phương án thay thế nếu không muốn hoặc không thể dùng sinh trắc;
- kênh hỗ trợ và xử lý khiếu nại.

Retention policy cần phân biệt raw sample, template, kết quả match, PAD result, audit metadata và hồ sơ proofing. Không giữ mọi dữ liệu vô thời hạn chỉ vì có thể hữu ích cho điều tra tương lai.

## 15. Ranh giới tin cậy trong kiến trúc sinh trắc

Một kiến trúc remote biometric proofing có nhiều thành phần:

~~~mermaid
flowchart LR
    U["Người đăng ký"] --> C["App / Browser capture"]
    C --> S["Sensor: camera / fingerprint / mic"]
    S --> SDK["Capture SDK + PAD"]
    SDK --> T["Protected transport"]
    T --> V["Verification service"]
    V --> M["Matcher + reference template"]
    V --> P["Proofing policy engine"]
    P --> R["Review / decision record"]
    R --> A["Identity account service"]
~~~

Các ranh giới cần kiểm soát:
- Người dùng có thể kiểm soát thiết bị và môi trường capture.
- App/SDK có thể bị sửa đổi hoặc chạy trong môi trường không tin cậy.
- Sensor có thể bị giả lập, thay thế hoặc nhận media injection.
- Network cần bảo vệ confidentiality/integrity và ràng buộc phiên.
- Vendor service cần xác minh endpoint, hợp đồng dữ liệu và khả năng audit.
- Reference template phải được liên kết với đúng danh tính.
- Policy engine phải phân biệt match result với quyết định proofing cuối cùng.
- Account service chỉ tạo/liên kết account sau khi nhận quyết định từ nguồn tin cậy.

Không nên tin một boolean do client gửi như `livenessPassed=true` hoặc `faceMatch=true`. Server cần nhận kết quả có xác thực từ verification service, ràng buộc với transaction ID, thời hạn, applicant/account và mục đích.

## 16. Tích hợp với passkey, MFA và authentication

Sinh trắc học có thể xuất hiện ở nhiều tầng khác nhau:

1. **Remote identity proofing:** so khớp người hiện diện với bằng chứng định danh.
2. **Local user verification:** thiết bị dùng sinh trắc để mở khóa private key hoặc credential.
3. **Biometric authentication:** hệ thống so khớp với template đã enroll để xác nhận người đang dùng thiết bị.
4. **Step-up:** một hành động nhạy cảm yêu cầu xác minh người dùng bổ sung theo policy.

Các trường hợp này không tương đương.

### Sinh trắc học cục bộ với passkey

Khi người dùng dùng passkey, thiết bị có thể yêu cầu vân tay, khuôn mặt hoặc PIN để cho phép sử dụng private key. Trong WebAuthn, RP thường nhận tín hiệu User Verification (UV) trong authenticator data đã được xác minh; RP không nhận dữ liệu sinh trắc thô và không biết chắc thiết bị dùng modality cụ thể nào nếu giao thức không cung cấp một thông tin được xác thực như vậy.

Vì vậy:
- Không mô tả WebAuthn UV là “server đã nhận và so khớp khuôn mặt”.
- Không gửi biometric template lên RP chỉ để xác thực passkey thông thường.
- Không suy ra modality hoặc mức bảo đảm vượt quá semantics của authenticator và policy.
- Tách identity proofing ban đầu khỏi authentication mỗi lần đăng nhập.

### Sinh trắc học có phải MFA không?

Một kết quả face match đơn lẻ không tự động là MFA. MFA phụ thuộc các yếu tố độc lập và cách credential/authenticator được bảo vệ. Sinh trắc có thể là yếu tố inherence trong một authenticator, nhưng cần xét thiết bị, possession, user verification và policy. Hai lần chụp khuôn mặt hoặc khuôn mặt cộng giọng nói không mặc nhiên tạo ra hai yếu tố độc lập nếu cùng dựa trên một thiết bị/kênh bị chiếm.

## 17. Fallback và recovery

Người dùng có thể không có camera phù hợp, không thể cung cấp modality đã chọn, bị thương, thay đổi ngoại hình, gặp lỗi thiết bị hoặc không muốn xử lý sinh trắc. Một hệ thống đáng tin cần lối đi thay thế được thiết kế trước.

Các lựa chọn:
- kiểm tra giấy tờ và review thủ công;
- xác minh qua nguồn authoritative hoặc tổ chức có thẩm quyền;
- dùng phương thức proofing khác phù hợp mức assurance;
- đặt lịch xác minh trực tiếp khi cần;
- hỗ trợ nhiều authenticator/phương thức thay thế;
- yêu cầu step-up bằng passkey, security key hoặc quy trình phù hợp.

Không dùng câu hỏi kiến thức cá nhân dễ tra cứu hoặc email đơn thuần làm fallback cho proofing có rủi ro cao. Không cho phép support staff tự bỏ qua PAD hoặc match failure mà không có phê duyệt, bằng chứng và audit.

### Re-enrollment và thay đổi template

Khi thay thiết bị hoặc modality:
1. Xác minh lại account/identity ở mức phù hợp.
2. Thu nhận mẫu mới qua flow có PAD/quality gate.
3. Gắn template mới với đúng account.
4. Vô hiệu template cũ theo policy.
5. Ghi audit và thông báo thay đổi.
6. Đánh giá session/credential liên quan nếu có dấu hiệu compromise.

## 18. Lỗi thiết kế và tấn công thường gặp

| Lỗi/tấn công | Cách xảy ra | Phòng vệ |
| --- | --- | --- |
| **Enrollment takeover** | Attacker gắn template của mình vào account nạn nhân | Reauthentication, account binding và audit trước enrollment. |
| **Photo/video replay** | Dùng ảnh hoặc video ghi sẵn | PAD, challenge phù hợp và integrity của capture chain. |
| **Deepfake/face swap** | Media tổng hợp giả người thật | PAD đánh giá độc lập, injection detection và review theo rủi ro. |
| **Virtual camera injection** | Chèn media trước bước phân tích | Bảo vệ capture path, app/device integrity và transaction binding. |
| **Template theft** | Lộ kho template | Encryption, isolation, least privilege, key management và incident plan. |
| **Cross-service linkage** | Dùng template giống nhau để liên kết người dùng giữa dịch vụ | Template protection/transformations và cấm reuse ngoài purpose. |
| **False accept** | Threshold hoặc model không phù hợp | Đánh giá FMR/FNMR tại operating point và risk policy. |
| **False reject** | Điều kiện capture hoặc model loại nhầm người hợp lệ | Quality guidance, retries có giới hạn, alternative path. |
| **Demographic performance gap** | Hiệu năng khác nhau giữa nhóm | Đánh giá phân nhóm, pilot, vendor governance và remediation. |
| **Replay kết quả vendor** | Tái sử dụng một kết quả match cũ cho giao dịch mới | Transaction ID, nonce, expiry và chữ ký response. |
| **Client-side boolean trust** | Browser tự khai PAD/match thành công | Xác minh kết quả từ service tin cậy phía server. |
| **Insider misuse** | Nhân viên truy cập mẫu không đúng mục đích | RBAC, dual control, audit và alert. |
| **Weak fallback** | Attacker bỏ qua sinh trắc bằng email/support yếu | Recovery assurance tương xứng và kiểm soát ngoại lệ. |
| **Over-retention** | Raw video/template lưu vô thời hạn | Retention schedule, deletion workflow và audit. |

## 19. Ví dụ API và quyết định phía server

Một flow có thể dùng transaction ID do server tạo:

~~~http
POST /identity-proofing/biometric-sessions
Authorization: Bearer <authenticated-session>
Content-Type: application/json

{
  "evidenceId": "evidence-882",
  "modality": "FACE",
  "purpose": "REMOTE_IDENTITY_PROOFING"
}
~~~

Server xác minh account và quyền proofing, tạo transaction ngắn hạn rồi trả thông tin capture được giới hạn theo policy. Client gửi mẫu trực tiếp qua kênh được thiết kế hoặc tới endpoint vendor đã được xác minh.

Kết quả xử lý từ service cần gắn với transaction:

~~~json
{
  "transactionId": "proof-2026-0042",
  "status": "MATCH",
  "padStatus": "PASS",
  "qualityStatus": "PASS",
  "referenceId": "evidence-882",
  "modelVersion": "biometric-model-v7",
  "evaluatedAt": "2026-11-22T10:15:00Z",
  "decisionReference": "decision-901"
}
~~~

Đây là response minh họa; trong production cần chữ ký hoặc kênh service-to-service đã xác thực, kiểm tra issuer/service identity, transaction binding, freshness, schema version và trạng thái một lần nếu kết quả không được replay.

Giả mã quyết định:

~~~java
ProofingDecision evaluateBiometricResult(
        VerifiedBiometricResult result,
        ProofingTransaction tx) {

    transactionStore.requireActive(tx.id());
    resultVerifier.verifyServiceSignature(result);
    resultVerifier.requireTransaction(result, tx.id());
    resultVerifier.requireFresh(result.evaluatedAt(), clock.instant());

    if (!result.padPassed()) {
        return ProofingDecision.reviewOrReject("PAD_FAILED");
    }
    if (!result.qualityPassed()) {
        return ProofingDecision.retryOrAlternative("QUALITY_INSUFFICIENT");
    }
    if (result.status() == MatchStatus.INCONCLUSIVE) {
        return ProofingDecision.manualReview("INCONCLUSIVE");
    }
    if (result.status() != MatchStatus.MATCH) {
        return ProofingDecision.retryOrAlternative("NON_MATCH");
    }

    // Match là một tín hiệu; policy còn kiểm tra bằng chứng và nguồn tham chiếu.
    return proofingPolicy.evaluateAllEvidence(tx, result);
}
~~~

Đây là giả mã, không phải thuật toán sinh trắc hoặc thư viện PAD. Không tự viết thuật toán so khớp ảnh để dùng production dựa trên ví dụ này. Policy engine phải kiểm tra nguồn reference, bằng chứng định danh, trạng thái transaction, giới hạn retry và các yêu cầu pháp lý/nghiệp vụ.

## 20. Kiểm thử sinh trắc học và identity proofing

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Mẫu hợp lệ khớp reference đã xác minh | Ghi match result và tiếp tục đánh giá proofing. |
| Mẫu của người khác | Non-match; không liên kết account. |
| Mẫu kém chất lượng | Quality failure/inconclusive; hướng dẫn thu nhận lại hoặc fallback. |
| Ảnh in trước camera | PAD phát hiện theo phạm vi đánh giá; không tạo proofing pass. |
| Video phát lại | PAD/challenge kiểm tra và từ chối hoặc review. |
| Deepfake/face swap | Đánh giá theo PAD và injection controls; không giả định một test đơn lẻ bắt được mọi trường hợp. |
| Media injection qua virtual camera | Capture integrity/transaction control phát hiện hoặc chuyển review. |
| Client gửi `padPassed=true` giả | Server bỏ qua client assertion; chỉ tin kết quả service xác minh. |
| Kết quả vendor sai transaction ID | Từ chối. |
| Kết quả vendor cũ hoặc đã dùng | Từ chối theo freshness/one-time policy. |
| Chữ ký service response sai | Từ chối và audit. |
| Reference không có provenance | Không chấp nhận match như proofing hoàn chỉnh. |
| Người dùng không thể enroll | Cung cấp alternative path; không khóa khỏi dịch vụ không cần thiết. |
| False reject lặp lại | Rate limit, hỗ trợ và review; không tự động khóa vô hạn. |
| Hiệu năng khác nhau giữa nhóm | Phát hiện qua phân tích subgroup và remediation. |
| Template truy cập bởi role không được phép | Deny và audit. |
| Raw sample hết retention | Xóa theo lịch và xác minh deletion. |
| User rút lại consent khi áp dụng | Xử lý theo policy/pháp luật và đánh giá tác động đến account. |
| Template bị compromise | Incident response, revoke/replace representation nếu kiến trúc hỗ trợ, re-proofing khi cần. |
| Re-enrollment cho account đã tồn tại | Reauthenticate, xác minh binding và audit. |
| Kết quả match thành công nhưng giấy tờ không hợp lệ | Proofing không đạt; biometric match không override evidence failure. |
| Service timeout | Trạng thái technical error; không coi là match. |

### Đánh giá operating point

Kiểm thử phải đo tại threshold dự kiến triển khai và trên population/thiết bị mục tiêu. Ghi rõ:
- dataset và cách lấy mẫu;
- modality, sensor và điều kiện capture;
- threshold/model version;
- định nghĩa metric;
- FMR/FNMR hoặc FAR/FRR;
- FTA/FTE;
- PAD attack species được thử;
- subgroup performance;
- latency và tỷ lệ manual review.

Không chỉ báo cáo EER hoặc một accuracy trung bình mà không nêu operating threshold và bối cảnh thử nghiệm.

## 21. Vận hành, audit và ứng phó sự cố

Audit có thể ghi:
- proofing transaction ID;
- account/applicant ID nội bộ;
- reference/evidence ID và nguồn;
- modality và model/version;
- quality/PAD/match status;
- timestamp, operator/service identity và reason code;
- quyết định cuối cùng và policy version;
- các lần retry/review và người phê duyệt.

Không ghi raw sample, template, ảnh/video/audio, token hoặc thông tin cá nhân không cần thiết vào log. Nếu cần bằng chứng điều tra, lưu trong kho bảo vệ riêng với quyền truy cập, retention và audit rõ ràng.

Khi nghi ngờ lộ template hoặc dữ liệu sinh trắc:
1. Khoanh vùng hệ thống, tenant, modality, template và thời gian ảnh hưởng.
2. Ngăn truy cập trái phép và bảo toàn log cần thiết.
3. Thu hồi quyền service/operator và rotate key liên quan.
4. Đánh giá raw sample/template có bị truy cập, export hoặc liên kết chéo dịch vụ không.
5. Xác định account/transaction bị ảnh hưởng và có cần re-proofing hoặc bổ sung credential không.
6. Thực hiện thông báo theo nghĩa vụ áp dụng.
7. Khắc phục đường truy cập, kiểm thử và rà soát các kho dữ liệu tương tự.

Không hứa rằng người dùng có thể “đổi khuôn mặt” sau khi lộ template. Tùy kiến trúc, có thể thay credential khác, dùng template transformation, thu hồi enrollment hoặc thực hiện quy trình proofing lại; cần nói rõ giới hạn.

## 22. Bài tập tình huống

Một dịch vụ tài chính cho phép mở tài khoản từ xa. Người dùng chụp giấy tờ và quay video selfie. Hệ thống dùng vendor để kiểm tra PAD và so khớp khuôn mặt với ảnh trên giấy tờ. Khi vendor trả `match=true`, backend tạo account ngay. Dữ liệu video và template được lưu không thời hạn để “phục vụ điều tra”. Một số nhóm người dùng có tỷ lệ false reject cao, và support có thể bỏ qua bước sinh trắc chỉ bằng email.

**Yêu cầu:**

1. Chỉ ra vì sao match=true chưa đủ để hoàn tất identity proofing.
2. Thiết kế các bước kiểm tra giấy tờ, nguồn tham chiếu, PAD, quality và match.
3. Xác định dữ liệu nào cần lưu, dữ liệu nào nên xóa sớm và vì sao.
4. Đề xuất cách đo FMR/FNMR, FTA/FTE theo nhóm và threshold thực tế.
5. Thiết kế fallback/review cho người bị false reject hoặc không thể dùng camera.
6. Bảo vệ vendor result khỏi replay hoặc giả mạo.
7. Xây dựng quy trình xử lý nếu template bị lộ.

**Hướng phân tích:** Kiểm tra giấy tờ và nguồn trước; transaction gắn applicant/evidence; xác minh service response, PAD, quality, freshness và reference provenance; sau đó policy đánh giá tổng thể. Tách raw video, template và audit decision, retention theo purpose. Đo metric tại operating threshold trên population mục tiêu. Fallback cần bằng chứng thay thế/review với assurance tương xứng, không chỉ email. Vendor result cần xác thực service, transaction ID, timestamp và one-time handling. Sự cố template cần khoanh vùng, revoke access, đánh giá dữ liệu lộ và thực hiện remediation/thông báo phù hợp.

## 23. Checklist review

- [ ] Mục đích sinh trắc được xác định rõ trong identity proofing hoặc authentication.
- [ ] Verification 1:1 được phân biệt với identification 1:N.
- [ ] Bằng chứng định danh và nguồn reference đã được xác minh độc lập.
- [ ] Enrollment gắn với account qua phiên và quyền đủ tin cậy.
- [ ] Raw sample và template được phân loại, bảo vệ và retention riêng.
- [ ] Quality gate và PAD được đánh giá theo threat model.
- [ ] Match threshold được chọn theo rủi ro và operating point, không theo marketing score.
- [ ] FMR/FNMR, FAR/FRR, FTA/FTE được định nghĩa rõ và đo trên population phù hợp.
- [ ] Hiệu năng subgroup và khả năng tiếp cận được đánh giá.
- [ ] Có alternative path, human review và quy trình khiếu nại.
- [ ] Template không được coi là password có thể reset hoặc dữ liệu vô hại.
- [ ] Mã hóa, access control, key management, isolation và audit được triển khai.
- [ ] Không tin boolean PAD/match từ client; kết quả service được xác thực và transaction-bound.
- [ ] Có chống replay, freshness và one-time handling cho proofing result.
- [ ] Sinh trắc cục bộ của passkey được phân biệt với remote biometric proofing.
- [ ] Không suy ra modality hoặc MFA assurance vượt quá tín hiệu được giao thức xác minh.
- [ ] Recovery/re-enrollment không tạo đường vòng yếu.
- [ ] Có incident response cho lộ raw sample/template và vendor compromise.

## 24. Ghi nhớ

**Biometric verification là phép so khớp mẫu sinh trắc với mẫu tham chiếu, thường theo mô hình 1:1; nó là một tín hiệu có xác suất trong quy trình identity proofing, không phải bằng chứng duy nhất cho toàn bộ danh tính.** Thiết kế đáng tin cần xác minh nguồn tham chiếu, kiểm soát enrollment, quality và PAD, chọn threshold theo rủi ro, đo sai số theo nhóm, bảo vệ template và cung cấp fallback có assurance phù hợp.

Khi review một flow, hãy hỏi: **Mẫu tham chiếu đến từ đâu? Người đang enroll có quyền gắn mẫu với account không? PAD kiểm tra loại tấn công nào? Threshold có được đánh giá trong điều kiện thực tế không? Ai có thể truy cập template và khi nào dữ liệu bị xóa? Người không thể dùng sinh trắc có lối đi nào? Kết quả match có bị nhầm thành authentication hoặc authorization không?**
