1. Mục tiêu chính của threat modeling là gì?
A. Ưu tiên rủi ro để xử lý từ giai đoạn thiết kế.
B. Chứng minh hệ thống không còn bất kỳ lỗ hổng nào.
C. Thay thế kiểm thử bảo mật bằng tài liệu thiết kế.
D. Liệt kê thành phần mà không cần đánh giá rủi ro.
Đáp án đúng: A

2. Khi xác định phạm vi threat model, nhóm thiết kế nên làm gì?
A. Chỉ xét mã nguồn do nhóm phát triển trực tiếp viết.
B. Loại bỏ dịch vụ bên ngoài khỏi sơ đồ kiến trúc.
C. Chỉ đánh giá các thành phần đã có sự cố bảo mật.
D. Chọn hệ thống, tài sản và phụ thuộc cần đánh giá.
Đáp án đúng: D

3. Tài sản trong threat model nên được xác định dựa trên yếu tố nào?
A. Số lượng máy chủ và dung lượng lưu trữ đang sử dụng.
B. Tên nhóm phát triển chịu trách nhiệm bảo trì thành phần.
C. Giá trị nghiệp vụ và yêu cầu bảo mật của tài sản.
D. Mức độ phổ biến của công nghệ trong cộng đồng.
Đáp án đúng: C

4. Threat actor được mô tả phù hợp nhất bằng cách nào?
A. Một lỗ hổng kỹ thuật đã được xác nhận trong mã nguồn.
B. Chủ thể có mục tiêu, năng lực và cơ hội gây hại.
C. Một biện pháp kiểm soát được triển khai ở ranh giới mạng.
D. Một tài sản cần bảo vệ trong kiến trúc hệ thống.
Đáp án đúng: B

5. Trong DFD, thành phần nào thường biểu diễn tiến trình xử lý dữ liệu?
A. Một process nhận, biến đổi hoặc phát dữ liệu.
B. Một trust boundary phân chia hai vùng tin cậy.
C. Một external entity nằm ngoài phạm vi hệ thống.
D. Một data store chỉ giữ dữ liệu mà không xử lý.
Đáp án đúng: A

6. Trust boundary trong sơ đồ luồng dữ liệu biểu thị điều gì?
A. Nơi dữ liệu được sao lưu sang một vùng lưu trữ khác.
B. Nơi tiến trình chuyển từ đồng bộ sang bất đồng bộ.
C. Nơi một thành phần đổi giao thức truyền thông.
D. Nơi dữ liệu hoặc lời gọi đi qua miền tin cậy khác.
Đáp án đúng: D

7. Theo STRIDE, attacker dùng token bị đánh cắp để giả làm user khác thuộc nhóm nào?
A. Tampering: sửa đổi dữ liệu trong quá trình truyền.
B. Repudiation: phủ nhận hành động đã thực hiện.
C. Spoofing: giả mạo danh tính của chủ thể hợp lệ.
D. Information disclosure: đọc dữ liệu ngoài quyền.
Đáp án đúng: C

8. Một API cho phép sửa giá đơn hàng mà không kiểm tra tính toàn vẹn. STRIDE nào phù hợp?
A. Tampering: sửa dữ liệu hoặc tham số trái phép.
B. Spoofing: giả danh một người dùng đã xác thực.
C. Denial of service: làm cạn tài nguyên của dịch vụ.
D. Repudiation: phủ nhận một giao dịch đã gửi.
Đáp án đúng: A

9. Hệ thống không lưu dấu vết đủ tin cậy để quy hành động về actor. Đây là nguy cơ STRIDE nào?
A. Spoofing: kẻ tấn công giả danh một principal khác.
B. Repudiation: khó chứng minh ai đã thực hiện hành động.
C. Elevation of privilege: user có thêm quyền quản trị.
D. Information disclosure: dữ liệu bí mật bị đọc trái phép.
Đáp án đúng: B

10. Log chứa access token và được nhiều người đọc. STRIDE nào mô tả trực tiếp rủi ro này?
A. Tampering: log bị sửa mà không để lại dấu vết.
B. Denial of service: log chiếm hết dung lượng lưu trữ.
C. Spoofing: actor dùng danh tính giả để đăng nhập.
D. Information disclosure: lộ dữ liệu trái phép.
Đáp án đúng: D

11. Một endpoint cho phép request lớn không giới hạn khiến worker cạn bộ nhớ. STRIDE nào phù hợp?
A. Tampering: thay nội dung request sau khi xác thực.
B. Repudiation: người dùng phủ nhận đã gửi request.
C. Denial of service: làm dịch vụ không đáp ứng yêu cầu.
D. Information disclosure: worker để lộ dữ liệu bộ nhớ.
Đáp án đúng: C

12. Lỗi kiểm tra quyền cho phép user thường gọi thao tác admin. Đây là STRIDE nào?
A. Spoofing: dùng tên user khác khi xác thực.
B. Elevation of privilege: đạt quyền cao hơn được cấp.
C. Tampering: sửa dữ liệu lưu trữ ngoài quy trình.
D. Denial of service: khiến dịch vụ ngừng hoạt động.
Đáp án đúng: B

13. Khi áp dụng STRIDE cho một process trong DFD, cách nào hữu ích nhất?
A. Gán đủ sáu loại đe dọa cho mọi thành phần theo mặc định.
B. Chỉ xét spoofing nếu process có giao diện đăng nhập.
C. Chỉ áp dụng STRIDE cho máy chủ đặt ngoài Internet.
D. Xem xét từng loại đe dọa theo bề mặt và luồng liên quan.
Đáp án đúng: D

14. LINDDUN được dùng chủ yếu để phân tích khía cạnh nào?
A. Lỗi cấu hình mạng và phân đoạn hạ tầng.
B. Khả năng chịu tải và tính sẵn sàng của dịch vụ.
C. Rủi ro quyền riêng tư và dữ liệu cá nhân.
D. Lỗ hổng thực thi mã trong thư viện bên thứ ba.
Đáp án đúng: C

15. Trong LINDDUN, Linkability mô tả nguy cơ nào?
A. Liên kết các bản ghi để suy ra chúng thuộc cùng cá nhân.
B. Xác định danh tính một người từ một bản ghi riêng lẻ.
C. Phát hiện một người có đang dùng dịch vụ hay không.
D. Tiết lộ nội dung dữ liệu cá nhân cho bên không có quyền.
Đáp án đúng: A

16. Một bộ dữ liệu tưởng đã ẩn danh nhưng còn thuộc tính hiếm giúp suy ra cá nhân. LINDDUN nào liên quan?
A. Identifiability: khả năng nhận diện một cá nhân.
B. Linkability: khả năng nối các bản ghi liên quan.
C. Detectability: khả năng nhận biết sự hiện diện của dữ liệu.
D. Unawareness: người dùng không biết dữ liệu được xử lý.
Đáp án đúng: A

17. Một dịch vụ cho phép bên ngoài chứng minh một người đã thực hiện hành động cụ thể. LINDDUN nào cần xem xét?
A. Disclosure: nội dung dữ liệu được tiết lộ trái phép.
B. Non-repudiation: khả năng gắn hành động với cá nhân.
C. Detectability: sự hiện diện của người dùng có thể bị nhận biết.
D. Non-compliance: xử lý dữ liệu trái yêu cầu pháp lý.
Đáp án đúng: B

18. Kẻ quan sát suy ra một người đang khám bệnh qua thời điểm truy cập portal. LINDDUN nào phù hợp?
A. Identifiability: xác định chính xác danh tính người đó.
B. Linkability: ghép nhiều bản ghi thành cùng một hồ sơ.
C. Unawareness: người dùng không biết có thu thập dữ liệu.
D. Detectability: nhận biết sự hiện diện hoặc hoạt động.
Đáp án đúng: D

19. API trả về hồ sơ cá nhân cho client không có quyền. LINDDUN nào mô tả trực tiếp?
A. Unawareness: thiếu nhận thức về cách dữ liệu được dùng.
B. Disclosure: tiết lộ dữ liệu cá nhân ngoài dự kiến.
C. Non-compliance: không đáp ứng nghĩa vụ bảo vệ dữ liệu.
D. Linkability: liên kết nhiều sự kiện về cùng cá nhân.
Đáp án đúng: B

20. Ứng dụng thu thập vị trí liên tục nhưng không thông báo rõ cho người dùng. LINDDUN nào liên quan?
A. Detectability: người khác suy ra người dùng đang hiện diện.
B. Identifiability: dữ liệu giúp xác định một cá nhân cụ thể.
C. Unawareness: người dùng không nhận biết hoạt động xử lý.
D. Disclosure: nội dung vị trí bị gửi cho bên không có quyền.
Đáp án đúng: C

21. Một sản phẩm lưu dữ liệu lâu hơn mục đích và trái chính sách đã công bố. LINDDUN nào phù hợp?
A. Non-compliance: vi phạm chính sách hoặc nghĩa vụ.
B. Linkability: ghép bản ghi từ nhiều hệ thống khác nhau.
C. Disclosure: gửi dữ liệu cho người nhận không được phép.
D. Detectability: suy ra một người đang dùng dịch vụ.
Đáp án đúng: A

22. Trong attack tree, nút gốc thường biểu diễn điều gì?
A. Một biện pháp kiểm soát được chọn để giảm rủi ro.
B. Một tài sản hợp lệ mà hệ thống cần bảo vệ.
C. Một sự kiện kiểm thử đã xác nhận khai thác thành công.
D. Mục tiêu tấn công tổng thể cần đạt được.
Đáp án đúng: D

23. Trong attack tree, AND và OR node khác nhau như thế nào?
A. AND cần một nhánh; OR cần tất cả nhánh con thành công.
B. Cả hai loại node đều yêu cầu mọi nhánh con thành công.
C. AND cần mọi nhánh; OR chỉ cần một nhánh con thành công.
D. Hai loại node chỉ biểu thị thứ tự thực hiện các bước.
Đáp án đúng: C

24. Abuse case khác use case thông thường ở điểm nào?
A. Mô tả luồng nghiệp vụ hợp lệ từ góc nhìn người dùng.
B. Liệt kê giao diện cần xây dựng trong từng sprint.
C. Ghi lại kết quả kiểm thử hiệu năng của hệ thống.
D. Mô tả cách chức năng bị lạm dụng gây hại.
Đáp án đúng: D

25. Khi ước lượng likelihood của một threat, yếu tố nào nên được xem xét?
A. Chỉ số lượng dòng mã trong thành phần bị ảnh hưởng.
B. Khả năng, cơ hội, mức phơi lộ và kiểm soát hiện có.
C. Chỉ mức độ nghiêm trọng tối đa nếu tấn công thành công.
D. Số lượng nhóm đã tham gia buổi threat modeling.
Đáp án đúng: B

26. Impact của một threat nên đánh giá theo cách nào?
A. Chỉ tính chi phí hạ tầng cần để khôi phục máy chủ.
B. Chỉ đếm số request mà attacker có thể gửi mỗi giây.
C. Đánh giá hậu quả với dữ liệu, dịch vụ và nghiệp vụ.
D. Dùng số lượng lỗ hổng trong scanner làm đại diện.
Đáp án đúng: C

27. Một rủi ro có likelihood thấp nhưng impact rất lớn. Cách ưu tiên nào hợp lý?
A. Xếp cuối vì xác suất thấp luôn quan trọng hơn tác động.
B. Đánh giá theo ma trận và khẩu vị rủi ro đã thống nhất.
C. Bỏ qua vì chưa có bằng chứng sự cố xảy ra thực tế.
D. Chỉ ưu tiên sau khi scanner tự động xác nhận lỗ hổng.
Đáp án đúng: B

28. Risk matrix định tính nên được sử dụng như thế nào?
A. Hỗ trợ nhất quán khi xếp hạng, không thay thế phán đoán.
B. Tạo xác suất chính xác tuyệt đối cho mọi kịch bản.
C. Chứng minh rủi ro thấp không thể xảy ra trong production.
D. Thay thế việc ghi rõ giả định và mức độ bất định.
Đáp án đúng: A

29. Nhóm thiết kế quyết định loại bỏ tính năng upload công khai để giảm threat. Đây là chiến lược nào?
A. Avoidance: loại bỏ hoạt động tạo ra rủi ro.
B. Mitigation: thêm kiểm soát để giảm khả năng hoặc tác động.
C. Transfer: chuyển một phần trách nhiệm hoặc tổn thất.
D. Acceptance: chấp nhận rủi ro còn lại có chủ đích.
Đáp án đúng: A

30. Một control làm giảm xác suất khai thác nhưng không loại bỏ threat. Đây là cách xử lý nào?
A. Avoidance: loại bỏ hoàn toàn chức năng liên quan.
B. Transfer: chuyển rủi ro sang nhà cung cấp bảo hiểm.
C. Acceptance: ghi nhận rủi ro mà không cần xử lý.
D. Mitigation: giảm likelihood hoặc impact của rủi ro.
Đáp án đúng: D

31. Sau khi thêm MFA và kiểm tra quyền, một phần rủi ro vẫn còn. Phần đó gọi là gì?
A. Inherent risk: rủi ro trước khi áp dụng kiểm soát.
B. Transferred risk: rủi ro đã chuyển cho bên khác.
C. Residual risk: rủi ro còn lại sau kiểm soát.
D. Detection risk: rủi ro do công cụ giám sát bỏ sót.
Đáp án đúng: C

32. Một threat model ghi giả định rằng API chỉ nhận traffic từ gateway. Việc nào cần làm?
A. Coi giả định là đúng vì đã được ghi trong tài liệu.
B. Xóa threat liên quan vì gateway nằm trong mạng nội bộ.
C. Xác minh giả định bằng kiến trúc và kiểm soát thực tế.
D. Chỉ kiểm tra giả định sau khi xảy ra sự cố production.
Đáp án đúng: C

33. Cách nào kiểm chứng một mitigation đã thiết kế thực sự hiệu quả?
A. Đánh dấu hoàn thành khi ticket triển khai đã đóng.
B. Tạo kiểm thử chứng minh control chặn kịch bản.
C. Dựa vào việc threat không xuất hiện trong log tuần qua.
D. Chỉ kiểm tra tài liệu có mô tả control tương ứng.
Đáp án đúng: B

34. Khi kiến trúc thay đổi thêm data store và trust boundary mới, nên làm gì?
A. Giữ nguyên threat model vì mục tiêu nghiệp vụ không đổi.
B. Chỉ cập nhật danh sách tài sản mà không xét luồng dữ liệu.
C. Chờ đánh giá định kỳ cuối năm mới sửa threat model.
D. Cập nhật DFD và đánh giá lại các threat liên quan.
Đáp án đúng: D

35. Trong kiến trúc cloud, một dịch vụ managed do nhà cung cấp vận hành. Threat model nên xử lý ra sao?
A. Loại dịch vụ khỏi mô hình vì nhà cung cấp chịu mọi rủi ro.
B. Xác định ranh giới trách nhiệm và kiểm soát của mỗi bên.
C. Giả định mọi cấu hình mặc định của dịch vụ đều an toàn.
D. Chỉ đánh giá bảo mật vật lý của trung tâm dữ liệu.
Đáp án đúng: B

36. Một thư viện bên thứ ba xử lý dữ liệu nhạy cảm trong luồng. Threat modeling nên xét gì?
A. Nguồn gốc, quyền truy cập, cập nhật và hành vi phụ thuộc.
B. Chỉ số phiên bản vì thư viện phổ biến thường đáng tin cậy.
C. Chỉ giấy phép phần mềm vì rủi ro chủ yếu là pháp lý.
D. Chỉ hiệu năng vì thư viện không nằm trong mã nội bộ.
Đáp án đúng: A
