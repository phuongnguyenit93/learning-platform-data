# Sử dụng mô hình kim tự tháp kiểm thử để thảo luận phân bổ

## Mục tiêu bài học

Trong chiến lược VALIDATION_TESTING_STRATEGY, mô hình kim tự tháp kiểm thử (test pyramid) là một cách trực quan để nhóm thảo luận nên đặt kiểm tra ở tầng nào, với số lượng và tần suất ra sao. Mô hình thường đặt kiểm thử đơn vị ở đáy, kiểm thử dịch vụ hoặc tích hợp ở tầng giữa và kiểm thử đầu cuối qua giao diện ở đỉnh. Đáy rộng biểu thị nhiều kiểm tra nhanh, tập trung; đỉnh hẹp biểu thị ít kiểm tra đầu cuối hơn vì chúng thường chậm, tốn chi phí bảo trì và khó chẩn đoán khi thất bại.

Kim tự tháp không phải công thức bắt buộc về tỷ lệ test case. Giá trị của nó nằm ở việc giúp nhóm cân bằng tốc độ phản hồi, độ tin cậy của bằng chứng, phạm vi hành vi được kiểm tra và chi phí vận hành bộ kiểm thử. Cấu trúc phù hợp còn tùy kiến trúc hệ thống, rủi ro nghiệp vụ, khả năng cô lập thành phần và cách người dùng tương tác với sản phẩm.

Sau bài học, người học có thể:

- Giải thích ý nghĩa các tầng trong mô hình kim tự tháp kiểm thử.
- Phân biệt kiểm thử đơn vị, kiểm thử dịch vụ/tích hợp và kiểm thử đầu cuối.
- Chọn tầng phù hợp để kiểm tra một yêu cầu hoặc rủi ro.
- Thảo luận số lượng, phạm vi và tần suất kiểm tra dựa trên chi phí và bằng chứng.
- Nhận diện bộ kiểm thử mất cân đối và đề xuất cách cải thiện.
- Điều chỉnh mô hình theo kiến trúc, loại sản phẩm và mức độ rủi ro.

## 1. Mô hình kim tự tháp kiểm thử là gì?

Mô hình kim tự tháp kiểm thử là một phép ẩn dụ về cách phân bố các loại kiểm tra tự động trong một sản phẩm. Phiên bản phổ biến có ba tầng:

1. **Đáy — kiểm thử đơn vị (unit tests):** nhiều kiểm tra nhỏ, chạy nhanh, xác minh hành vi của các đơn vị logic trong phạm vi cô lập.
2. **Tầng giữa — kiểm thử dịch vụ, thành phần và tích hợp (service/component/integration tests):** kiểm tra giao tiếp giữa các thành phần, hợp đồng API, truy cập dữ liệu và quy tắc nghiệp vụ qua ranh giới thực tế.
3. **Đỉnh — kiểm thử giao diện đầu cuối (UI/end-to-end tests):** một số luồng quan trọng được thực hiện qua các thành phần gần với cách người dùng sử dụng sản phẩm.

~~~text
                 /\
                /  \
               / E2E\       Ít hơn, chậm hơn, phạm vi rộng
              /------\
             / Service\
            / / API /  \    Kiểm tra ranh giới và tích hợp
           /------------\
          / Unit tests   \
         /________________\
           Nhiều hơn, nhanh hơn, tập trung
~~~

Đáy rộng thể hiện khả năng kiểm tra nhiều quy tắc nhỏ với phản hồi nhanh. Tầng giữa kiểm tra các tương tác mà unit test cô lập không thể chứng minh. Đỉnh hẹp giữ lại các luồng người dùng quan trọng để xác nhận hệ thống hoạt động xuyên suốt.

Mô hình thường được dùng để thảo luận về kiểm thử tự động. Nó không hàm ý rằng kiểm thử thủ công, kiểm thử khám phá, đánh giá khả năng sử dụng, kiểm thử bảo mật chuyên sâu hoặc kiểm tra vận hành không quan trọng. Những hoạt động đó có mục đích và cách lập kế hoạch riêng, có thể bổ sung bằng chứng ở nhiều tầng.

## 2. Ba tầng chính và vai trò của từng tầng

### 2.1. Tầng đáy: kiểm thử đơn vị

Kiểm thử đơn vị xác minh hành vi của một đơn vị nhỏ trong mã nguồn, thường là một hàm, phương thức hoặc lớp. Các phụ thuộc có thể được thay bằng test double như stub, fake hoặc mock để kiểm tra logic trong điều kiện có kiểm soát.

Ví dụ, một hàm tính phí vận chuyển có thể được kiểm tra với các đầu vào:

- Đơn hàng dưới ngưỡng miễn phí vận chuyển.
- Đơn hàng đạt ngưỡng miễn phí vận chuyển.
- Khu vực giao hàng có mức phí khác nhau.
- Giá trị đầu vào biên hoặc không hợp lệ.
- Quy tắc làm tròn và loại tiền tệ.

Ưu điểm của unit test:

- Thường chạy nhanh, có thể thực hiện trên mỗi lần thay đổi mã.
- Phạm vi nhỏ giúp xác định nguyên nhân thất bại tương đối dễ.
- Có thể kiểm tra nhiều trường hợp biên với chi phí thấp.
- Hỗ trợ thiết kế mô-đun, tách biệt trách nhiệm và làm rõ quy tắc nghiệp vụ.
- Tạo phản hồi sớm trước khi thay đổi được tích hợp với các thành phần khác.

Giới hạn cần lưu ý:

- Một unit test cô lập không chứng minh các thành phần thật giao tiếp đúng với nhau.
- Test double có thể mô phỏng sai hành vi của hệ thống bên ngoài.
- Kiểm tra quá nhiều chi tiết triển khai có thể khiến test thất bại khi tái cấu trúc dù hành vi người dùng không đổi.
- Một bộ unit test có độ bao phủ dòng lệnh cao vẫn có thể bỏ sót quy tắc nghiệp vụ hoặc luồng quan trọng.

Nên kiểm tra hành vi và kết quả có ý nghĩa, không chỉ xác minh phương thức nội bộ đã được gọi bao nhiêu lần. Khi một quy tắc có thể được kiểm tra ở mức đơn vị mà vẫn tạo ra bằng chứng đáng tin cậy, đây thường là tầng có phản hồi nhanh và chi phí thấp.

### 2.2. Tầng giữa: kiểm thử dịch vụ, thành phần và tích hợp

Tầng giữa xác minh cách các phần của hệ thống phối hợp. Tùy kiến trúc, nhóm có thể kiểm tra một dịch vụ cùng cơ sở dữ liệu, một API qua mạng, một thành phần tích hợp với hàng đợi hoặc hợp đồng giữa hai dịch vụ.

Các loại kiểm tra thường gặp:

- **Kiểm thử thành phần (component test):** kiểm tra một thành phần tương đối hoàn chỉnh trong ranh giới xác định, có thể dùng các phụ thuộc thật hoặc được kiểm soát.
- **Kiểm thử tích hợp (integration test):** xác minh hai hay nhiều thành phần phối hợp, chẳng hạn ứng dụng với cơ sở dữ liệu hoặc dịch vụ với nhà cung cấp bên ngoài.
- **Kiểm thử API/dịch vụ:** gửi yêu cầu qua giao diện công khai của dịch vụ và xác minh mã phản hồi, dữ liệu, lỗi, quyền truy cập và hợp đồng.
- **Kiểm thử hợp đồng (contract test):** xác minh bên cung cấp và bên sử dụng thống nhất về cấu trúc, ngữ nghĩa và quy tắc tương tác.
- **Kiểm thử dữ liệu:** xác minh truy vấn, ràng buộc, migration, tính nhất quán và xử lý giao dịch.

Ví dụ, để kiểm tra quy trình đặt hàng, nhóm có thể gửi yêu cầu đến API đặt hàng, dùng cơ sở dữ liệu kiểm thử và mô phỏng hoặc tích hợp với dịch vụ thanh toán thử nghiệm. Kiểm tra này có thể xác nhận rằng đơn hàng được lưu đúng, tồn kho được cập nhật và giao dịch có trạng thái phù hợp.

Ưu điểm của tầng giữa:

- Phát hiện lỗi ở ranh giới mà unit test thường bỏ qua.
- Có thể kiểm tra hợp đồng và quy tắc nghiệp vụ qua giao diện thật.
- Thường ổn định và dễ chẩn đoán hơn một kịch bản giao diện dài.
- Bao phủ nhiều hành vi thực tế mà không cần điều khiển toàn bộ trình duyệt hoặc thiết bị.

Chi phí và giới hạn:

- Chậm hơn unit test do cần khởi tạo dịch vụ, cơ sở dữ liệu, mạng hoặc môi trường.
- Có thể phụ thuộc cấu hình, dữ liệu và trạng thái bên ngoài.
- Cần quản lý môi trường và dọn dẹp dữ liệu sau kiểm tra.
- Kiểm thử tích hợp rộng có thể khó xác định thành phần gây lỗi nếu phạm vi quá lớn.

Tầng giữa thường là nơi thích hợp để kiểm tra giao tiếp và tích hợp. Nếu một rủi ro nằm ở hợp đồng API, tính toàn vẹn dữ liệu hoặc tương tác giữa dịch vụ, việc chỉ tăng số unit test sẽ không tạo ra bằng chứng tương đương.

### 2.3. Tầng đỉnh: kiểm thử đầu cuối

Kiểm thử đầu cuối (end-to-end, E2E) xác minh một luồng hoàn chỉnh qua nhiều thành phần, thường từ góc nhìn người dùng hoặc hệ thống bên ngoài. Với sản phẩm web, kiểm tra có thể thao tác trình duyệt, đăng nhập, tạo dữ liệu, thực hiện nghiệp vụ và xác minh kết quả hiển thị.

Ví dụ, một kịch bản E2E cho cửa hàng trực tuyến có thể:

1. Đăng nhập bằng tài khoản thử nghiệm.
2. Tìm một sản phẩm và thêm vào giỏ hàng.
3. Áp dụng mã giảm giá.
4. Chọn địa chỉ giao hàng.
5. Hoàn tất thanh toán trong môi trường giả lập.
6. Xác minh đơn hàng và trạng thái xác nhận.

E2E hữu ích khi cần xác nhận các thành phần kết hợp tạo ra kết quả mà người dùng mong đợi. Nó có thể phát hiện lỗi cấu hình, điều hướng, tích hợp hoặc dữ liệu xuyên suốt mà kiểm thử ở tầng thấp không phát hiện được.

Tuy nhiên, E2E thường:

- Chạy chậm hơn và tiêu tốn nhiều tài nguyên.
- Nhạy cảm với thay đổi giao diện, thời gian chờ và dữ liệu dùng chung.
- Khó chẩn đoán khi một luồng dài thất bại.
- Dễ không ổn định nếu phụ thuộc mạng, dịch vụ ngoài hoặc môi trường không được kiểm soát.
- Tốn công bảo trì khi giao diện hoặc quy trình người dùng thay đổi.

Vì vậy, nên chọn một số luồng đại diện có giá trị cao: luồng tạo doanh thu, đăng nhập, phân quyền, thao tác dữ liệu cốt lõi hoặc các hành trình có ảnh hưởng lớn. Không nên đưa mọi biến thể dữ liệu và mọi trường hợp biên lên tầng E2E nếu chúng có thể được kiểm tra đáng tin cậy ở tầng thấp hơn.

## 3. Cách đọc và sử dụng hình dạng kim tự tháp

Kim tự tháp mô tả xu hướng phân bố: nhiều kiểm tra nhanh ở dưới, ít kiểm tra toàn luồng ở trên. Nó không đưa ra tỷ lệ cố định như 70% unit, 20% integration và 10% E2E. Các tỷ lệ thường thấy trong bài viết hoặc ví dụ chỉ có thể dùng làm điểm khởi đầu cho thảo luận, không phải chuẩn chung cho mọi hệ thống.

Một nhóm có thể có tỷ lệ khác tùy theo:

- Kiến trúc nguyên khối, microservices, ứng dụng di động, hệ thống nhúng hoặc nền tảng dữ liệu.
- Mức độ phức tạp của quy tắc nghiệp vụ.
- Khả năng cô lập logic và chất lượng thiết kế mô-đun.
- Mức độ phụ thuộc vào cơ sở dữ liệu, mạng và nhà cung cấp bên ngoài.
- Rủi ro của các luồng nghiệp vụ.
- Mức trưởng thành của môi trường và tự động hóa.
- Chi phí tạo, chạy và bảo trì từng loại kiểm tra.

Thay vì hỏi “mỗi tầng phải có bao nhiêu phần trăm test?”, nhóm nên hỏi:

- Những rủi ro quan trọng đã có bằng chứng ở tầng nào?
- Kiểm tra nào đang lặp lại cùng một khẳng định ở nhiều tầng?
- Có kiểm tra nào quá rộng, chậm hoặc khó chẩn đoán không?
- Một lỗi cụ thể sẽ được phát hiện sớm nhất ở tầng nào?
- Các luồng đầu cuối tối thiểu nào cần được giữ lại để xác nhận hành trình quan trọng?

## 4. Chọn tầng kiểm thử phù hợp

Một nguyên tắc hữu ích là kiểm tra ở tầng thấp nhất có thể cung cấp bằng chứng đáng tin cậy cho câu hỏi đang đặt ra. “Thấp nhất” không có nghĩa là luôn dùng unit test; nó có nghĩa là không đưa kiểm tra lên tầng rộng và tốn kém nếu một tầng thấp hơn có thể xác minh đúng rủi ro.

| Câu hỏi hoặc rủi ro | Tầng thường phù hợp | Lý do |
|---|---|---|
| Quy tắc tính phí có đúng với các giá trị biên không? | Unit | Logic có thể được kiểm tra trực tiếp với dữ liệu đầu vào xác định. |
| API có trả đúng mã lỗi và cấu trúc phản hồi không? | API/service | Cần gọi qua giao diện dịch vụ thực tế. |
| Dịch vụ có lưu đơn hàng và cập nhật tồn kho nhất quán không? | Integration/component | Cần xác minh tương tác giữa dịch vụ và kho dữ liệu hoặc thành phần liên quan. |
| Nhà cung cấp và bên sử dụng có hiểu cùng một hợp đồng không? | Contract | Cần xác minh cấu trúc và ngữ nghĩa giao tiếp giữa hai phía. |
| Người dùng có thể hoàn tất hành trình mua hàng quan trọng không? | E2E | Cần xác nhận các thành phần phối hợp trong luồng hoàn chỉnh. |
| Giao diện có dễ hiểu và phù hợp với nhu cầu người dùng không? | Đánh giá khả năng sử dụng, kết hợp E2E khi cần | Kết quả kỹ thuật tự động không thay thế phản hồi và quan sát người dùng. |
| Hệ thống chịu được tải dự kiến không? | Kiểm thử hiệu năng ở cấp dịch vụ/hệ thống | Cần đo hành vi dưới tải đại diện, không chỉ kiểm tra logic đơn vị. |

Một yêu cầu có thể cần bằng chứng ở nhiều tầng. Ví dụ, quy tắc áp dụng mã giảm giá có thể được kiểm tra chi tiết ở unit test, được xác nhận qua API khi kết hợp với dữ liệu thật và được kiểm tra trong một hành trình E2E đại diện. Mỗi tầng cần trả lời một câu hỏi khác nhau, tránh nhân bản cùng một trường hợp mà không tăng thêm niềm tin.

## 5. Ví dụ phân bổ cho một tính năng

Giả sử sản phẩm có chức năng đặt hàng. Người dùng chọn sản phẩm, áp dụng ưu đãi, thanh toán và nhận xác nhận đơn hàng.

| Khu vực | Kiểm tra ở tầng thấp | Kiểm tra tầng giữa | Kiểm tra E2E |
|---|---|---|---|
| Tính giá và giảm giá | Các quy tắc, ngưỡng, làm tròn và trường hợp biên. | API tính giá với dữ liệu và cấu hình thực tế. | Một số hành trình mua hàng đại diện. |
| Tồn kho | Quy tắc kiểm tra số lượng và trạng thái. | Giao dịch cập nhật tồn kho, xử lý đồng thời và rollback. | Xác minh đơn hàng không vượt tồn kho trong luồng chính. |
| Thanh toán | Logic trạng thái và xử lý phản hồi theo từng trường hợp. | Tích hợp với cổng thanh toán thử nghiệm, timeout và retry. | Một luồng thanh toán thành công và một luồng thất bại quan trọng. |
| Phân quyền | Quy tắc truy cập theo vai trò. | API từ chối truy cập không hợp lệ. | Luồng người dùng không thể xem hoặc thao tác đơn hàng ngoài quyền. |
| Xác nhận đơn hàng | Logic tạo nội dung và trạng thái. | Dịch vụ đơn hàng, hàng đợi và thông báo phối hợp đúng. | Người dùng thấy xác nhận sau khi giao dịch hoàn tất. |

Phần lớn trường hợp biên của tính giá nên nằm ở unit test vì chúng nhanh, dễ tạo dữ liệu và xác định lỗi rõ. Tương tác với cơ sở dữ liệu hoặc cổng thanh toán cần kiểm thử tầng giữa. Một số luồng đầu cuối quan trọng xác nhận hành trình tổng thể. Cách phân bổ này giúp giữ E2E gọn mà vẫn có bằng chứng ở các ranh giới quan trọng.

## 6. Cân bằng phạm vi kiểm thử, tốc độ và độ tin cậy

Một bộ kiểm thử tốt không chỉ có nhiều test case. Nó cần phản hồi đủ nhanh, phát hiện lỗi có ý nghĩa, dễ chẩn đoán và có chi phí bảo trì hợp lý.

### 6.1. Tối ưu phản hồi theo pipeline

Có thể tổ chức pipeline theo thứ tự từ nhanh đến chậm:

| Giai đoạn | Kiểm tra gợi ý | Mục đích |
|---|---|---|
| Khi tạo pull request | Format, lint, phân tích tĩnh, unit test, kiểm tra nhanh | Phát hiện lỗi sớm và cung cấp phản hồi cho người viết mã. |
| Sau khi hợp nhất | Component, API, contract và integration test | Xác minh tương tác giữa các thành phần. |
| Trước phát hành | Bộ E2E cốt lõi, hồi quy theo rủi ro, bảo mật và hiệu năng cần thiết | Xác nhận các luồng quan trọng và điều kiện phát hành. |
| Sau triển khai | Smoke test, health check, giám sát chỉ số và log | Xác nhận hệ thống hoạt động trong môi trường đích. |

Thứ tự cụ thể tùy hệ thống. Một số kiểm tra bảo mật hoặc hợp đồng cần chạy ngay ở pull request; một số kiểm tra hiệu năng chỉ phù hợp với môi trường chuyên dụng. Điều quan trọng là nhóm xác định rõ kiểm tra bắt buộc, thời điểm chạy và điều kiện chặn phát hành.

### 6.2. Giữ kiểm thử ổn định

Kiểm thử không ổn định (flaky test) có thể lúc đạt, lúc trượt dù mã nguồn không đổi. Nguyên nhân thường gồm phụ thuộc thời gian, dữ liệu dùng chung, thứ tự chạy, mạng, môi trường hoặc đồng bộ bất đồng bộ không rõ ràng.

Cách xử lý:

- Tạo dữ liệu riêng cho mỗi test hoặc mỗi lần chạy khi có thể.
- Dọn dẹp trạng thái sau kiểm tra và tránh phụ thuộc thứ tự.
- Dùng chờ theo điều kiện thay vì sleep cố định.
- Kiểm soát phiên bản môi trường và dịch vụ phụ thuộc.
- Ghi log và lưu bằng chứng đủ để chẩn đoán.
- Theo dõi flaky test, xác định người phụ trách và thời hạn khắc phục.

Không nên bỏ qua kiểm thử thất bại chỉ vì nó thường xuyên không ổn định. Nếu phải cách ly tạm thời, cần ghi rõ lý do, phạm vi rủi ro, người chịu trách nhiệm và thời hạn đưa lại vào pipeline.

### 6.3. Tránh kiểm thử trùng lặp không tạo thêm giá trị

Một trường hợp có thể được kiểm tra ở nhiều tầng nếu mỗi tầng chứng minh một điều khác nhau. Nhưng nếu hàng trăm E2E lặp lại mọi biến thể đã được xác minh bằng unit và API test, chi phí chạy và bảo trì có thể tăng mà độ tin cậy không tăng tương ứng.

Hãy xem xét mỗi test case:

- Nó xác minh khẳng định nào?
- Có tầng nào khác kiểm tra cùng khẳng định đáng tin cậy và rẻ hơn không?
- Nếu test thất bại, nhóm có thể xác định nguyên nhân nhanh không?
- Có rủi ro nào chỉ có thể phát hiện ở tầng hiện tại không?
- Test có còn đại diện cho hành vi hoặc kiến trúc hiện tại không?

Nếu không xác định được giá trị riêng, cân nhắc loại bỏ, gộp hoặc chuyển kiểm tra xuống tầng phù hợp hơn.

## 7. Nhận diện các dạng mất cân đối

### 7.1. Kim tự tháp ngược (ice cream cone)

Khi có quá ít unit test, rất ít kiểm tra tầng giữa nhưng nhiều E2E, bộ kiểm thử có thể giống một cây kem: phần trên nặng, phần đáy hẹp.

Hệ quả thường gặp:

- Pipeline chậm vì nhiều kịch bản giao diện.
- Lỗi logic nhỏ chỉ được phát hiện sau khi chạy luồng dài.
- Thất bại khó chẩn đoán do nhiều thành phần cùng tham gia.
- Bộ kiểm thử nhạy với thay đổi giao diện và dữ liệu.
- Nhóm mất nhiều thời gian bảo trì hơn là nhận phản hồi về logic.

Cách cải thiện là xác định các quy tắc nghiệp vụ có thể kiểm tra độc lập, bổ sung unit test và API/component test, rồi giữ lại E2E cho hành trình quan trọng.

### 7.2. Hình đồng hồ cát

Một bộ kiểm thử có nhiều unit test và nhiều E2E nhưng thiếu kiểm tra tầng giữa có thể bỏ sót ranh giới dịch vụ. Unit test dùng mock không phát hiện hợp đồng sai; E2E có thể phát hiện muộn và khó xác định thành phần lỗi.

Cách cải thiện là bổ sung contract test, API test và integration test cho các ranh giới có rủi ro cao.

### 7.3. Đáy lớn nhưng kiểm tra sai trọng tâm

Số lượng unit test lớn không đồng nghĩa với chất lượng tốt nếu chúng chủ yếu xác minh chi tiết triển khai, getter/setter hoặc tương tác mock không có ý nghĩa nghiệp vụ. Một bộ test như vậy có thể tạo cảm giác an toàn nhưng ít phát hiện lỗi người dùng gặp phải.

Cách cải thiện là rà soát mục tiêu từng test, ưu tiên hành vi và quy tắc có giá trị, giảm phụ thuộc vào cấu trúc nội bộ dễ thay đổi.

### 7.4. Đỉnh rộng do thiếu phân loại

Nhiều nhóm thêm E2E cho mọi lỗi từng gặp. Theo thời gian, bộ E2E phình to, chạy lâu và chứa nhiều kiểm tra trùng lặp. Sau khi lỗi được hiểu, nhóm nên bổ sung một kiểm tra ở tầng thấp nhất có thể tái hiện nguyên nhân, đồng thời giữ E2E nếu nó bảo vệ một luồng xuyên suốt có ý nghĩa riêng.

## 8. Điều chỉnh kim tự tháp theo kiến trúc và sản phẩm

Kim tự tháp ba tầng là mô hình tham khảo. Ranh giới giữa các tầng có thể thay đổi tùy sản phẩm.

### 8.1. Ứng dụng nguyên khối

Trong ứng dụng nguyên khối, unit test có thể kiểm tra quy tắc nghiệp vụ và tầng giữa kiểm tra tích hợp với cơ sở dữ liệu, bộ nhớ đệm hoặc dịch vụ ngoài. E2E tập trung vào các hành trình người dùng chính. Nhóm cần tránh việc mọi kiểm tra đều phải khởi động toàn bộ ứng dụng nếu chỉ một thành phần cần được xác minh.

### 8.2. Hệ thống microservices

Trong microservices, contract test và integration test đặc biệt hữu ích vì mỗi dịch vụ có thể được triển khai độc lập. Nhóm cần xác minh tương thích giữa phiên bản nhà cung cấp và bên sử dụng, xử lý timeout, retry, thông điệp lặp, thứ tự sự kiện và lỗi phụ thuộc.

E2E xuyên nhiều dịch vụ vẫn cần cho một số luồng nghiệp vụ trọng yếu, nhưng không nên trở thành cách duy nhất để kiểm tra mọi tương tác. Nếu tất cả kiểm tra chỉ chạy qua một môi trường tích hợp lớn, lỗi ở một dịch vụ có thể làm hỏng nhiều kịch bản và khó xác định nguyên nhân.

### 8.3. Ứng dụng di động

Unit test kiểm tra logic và trạng thái; tầng giữa kiểm tra API, lưu trữ, đồng bộ và tích hợp thiết bị; E2E trên thiết bị hoặc trình giả lập xác minh các hành trình quan trọng. Cần chọn ma trận thiết bị, hệ điều hành và kích thước màn hình dựa trên nhóm người dùng và rủi ro tương thích.

### 8.4. Hệ thống dữ liệu và xử lý theo lô

Đáy có thể gồm kiểm tra hàm biến đổi, quy tắc chất lượng dữ liệu và tính toán. Tầng giữa xác minh pipeline, schema, lưu trữ và xử lý dữ liệu giữa các bước. Tầng trên có thể là kiểm tra quy trình dữ liệu hoàn chỉnh, báo cáo hoặc kết quả nghiệp vụ. Cần chú ý dữ liệu mẫu đại diện, tính lặp lại và đối soát đầu ra.

### 8.5. Hệ thống nhúng hoặc phần cứng

Unit test có thể kiểm tra thuật toán và logic điều khiển; tầng giữa kiểm tra driver, giao tiếp và mô phỏng phần cứng; tầng trên xác minh hành vi trên thiết bị hoặc hệ thống thực. Một số kiểm tra vật lý, an toàn và độ bền không thể thay thế hoàn toàn bằng kiểm thử tự động ở tầng thấp.

## 9. Mô hình kim tự tháp và kiểm thử theo rủi ro

Kim tự tháp cho biết các tầng kiểm tra, còn phân tích rủi ro giúp quyết định cần đầu tư vào đâu. Hai cách nhìn bổ trợ nhau.

| Rủi ro | Bằng chứng ở đáy | Bằng chứng tầng giữa | Bằng chứng ở đỉnh |
|---|---|---|---|
| Sai quy tắc tính tiền | Nhiều trường hợp biên cho hàm tính. | API tính tiền với dữ liệu và cấu hình thật. | Một số hành trình thanh toán đại diện. |
| Lộ dữ liệu do phân quyền | Kiểm tra logic chính sách và vai trò. | API xác minh quyền trên tài nguyên thật. | Luồng người dùng không thể truy cập dữ liệu ngoài quyền. |
| Sai hợp đồng giữa dịch vụ | Kiểm tra logic tạo dữ liệu và schema. | Contract test và integration test. | Chỉ các luồng nghiệp vụ xuyên dịch vụ cần thiết. |
| Giao diện không hoàn tất luồng chính | Kiểm tra logic trạng thái nếu có thể. | API và component test cho các thao tác liên quan. | E2E cho hành trình người dùng trọng yếu. |
| Hiệu năng suy giảm | Kiểm tra độ phức tạp hoặc thuật toán khi thích hợp. | Load test ở cấp dịch vụ và cơ sở dữ liệu. | Kiểm tra một số hành trình dưới tải đại diện. |

Với vùng có hậu quả nghiêm trọng, có thể cần bằng chứng ở nhiều tầng. Nhưng mỗi tầng nên có mục tiêu rõ ràng. Ví dụ, unit test xác minh logic phân quyền theo vai trò; API test xác minh quyền thực tế trên tài nguyên; E2E xác minh giao diện không để người dùng truy cập trái phép. Ba kiểm tra này bổ sung chứ không thay thế nhau.

## 10. Quy trình dùng kim tự tháp trong buổi thảo luận phân bổ

Nhóm có thể dùng quy trình sau khi lập kế hoạch kiểm thử cho một tính năng hoặc phiên bản.

### Bước 1: Chọn luồng hoặc rủi ro cần thảo luận

Bắt đầu từ yêu cầu, luồng nghiệp vụ hoặc thay đổi có tác động. Nêu rõ người dùng, kết quả mong đợi và hậu quả nếu chức năng lỗi.

### Bước 2: Liệt kê các khẳng định cần xác minh

Ví dụ với chức năng đặt hàng:

- Tổng tiền được tính đúng.
- Người dùng chỉ xem được đơn hàng của mình.
- Giao dịch không bị ghi nhận hai lần khi retry.
- Đơn hàng, tồn kho và thanh toán có trạng thái nhất quán.
- Người dùng nhận được xác nhận sau khi hoàn tất.

### Bước 3: Đặt từng khẳng định vào tầng phù hợp

Với mỗi khẳng định, hỏi tầng nào có thể tạo bằng chứng đáng tin cậy với chi phí thấp nhất. Đánh dấu nếu cần kiểm tra ở nhiều tầng vì các tầng xác minh những khía cạnh khác nhau.

### Bước 4: Ước lượng chi phí và độ tin cậy

Xem thời gian chạy, độ ổn định, công sức chuẩn bị dữ liệu, yêu cầu môi trường và khả năng chẩn đoán. Kiểm tra nào chạy thường xuyên nên có phản hồi nhanh và ổn định.

### Bước 5: Xác định bộ kiểm tra tối thiểu cho luồng quan trọng

Giữ các unit test bao phủ quy tắc cốt lõi, kiểm tra tầng giữa bao phủ ranh giới quan trọng và E2E bảo vệ hành trình người dùng thiết yếu. Không đặt mục tiêu số lượng trước khi hiểu rủi ro.

### Bước 6: Thống nhất thời điểm chạy và điều kiện phát hành

Xác định kiểm tra nào chạy trên pull request, sau hợp nhất, trước phát hành và sau triển khai. Nêu rõ kiểm tra nào chặn hợp nhất hoặc phát hành, cách xử lý khi môi trường không sẵn sàng và ai quyết định ngoại lệ.

### Bước 7: Đánh giá lại bằng dữ liệu

Theo dõi lỗi lọt qua từng tầng, thời gian pipeline, flaky test, thời gian chẩn đoán và chi phí bảo trì. Khi lỗi chỉ được phát hiện ở E2E, xem xét có thể bổ sung một kiểm tra tầng thấp hơn để phát hiện sớm nguyên nhân tương tự hay không.

## 11. Ví dụ thực tế: thảo luận phân bổ cho chức năng đăng nhập

Một nhóm phát triển chức năng đăng nhập bằng mật khẩu và xác thực đa yếu tố. Đây là luồng quan trọng vì ảnh hưởng đến quyền truy cập tài khoản.

Nhóm thống nhất các mục tiêu và tầng kiểm tra:

- **Unit:** xác minh quy tắc khóa tài khoản, thời hạn mã xác thực, số lần thử, chuẩn hóa đầu vào và trạng thái phiên.
- **API/service:** xác minh thông tin xác thực đúng/sai, mã xác thực hết hạn, giới hạn tần suất, phản hồi lỗi và quyền truy cập sau đăng nhập.
- **Integration:** xác minh lưu trữ phiên, bộ nhớ đệm, dịch vụ gửi mã và xử lý khi dịch vụ phụ thuộc không phản hồi.
- **E2E:** xác minh người dùng có thể đăng nhập bình thường, hoàn tất xác thực đa yếu tố và bị từ chối khi dùng mã sai hoặc hết hạn.
- **Kiểm tra bảo mật chuyên sâu:** đánh giá các rủi ro như dò mật khẩu, chiếm phiên, lộ thông tin và vượt quyền; các kiểm tra này có thể kết hợp tự động và thủ công.

Nhóm không tạo E2E cho mọi giá trị biên của mã xác thực vì các trường hợp đó được kiểm tra chi tiết hơn ở unit và API. E2E giữ một số hành trình đại diện để xác nhận trải nghiệm và tích hợp. Nếu thay đổi nhà cung cấp gửi mã, nhóm tăng kiểm thử tầng giữa và một số kiểm tra E2E liên quan đến việc nhận, nhập mã.

Khi một E2E thất bại, nhóm xem log và kết quả ở các tầng thấp hơn để xác định lỗi thuộc logic, API, dịch vụ gửi mã hay giao diện. Nếu nguyên nhân là logic hết hạn mã, nhóm bổ sung hoặc sửa unit test tương ứng để phản hồi sớm trong các lần thay đổi tiếp theo.

## 12. Các chỉ số giúp đánh giá sự cân bằng

Có thể theo dõi các chỉ số sau để hiểu bộ kiểm thử có đang phân bổ hợp lý không:

- **Thời gian chạy theo tầng:** tổng thời gian và thời gian phản hồi trung vị của unit, service/integration và E2E.
- **Tỷ lệ thất bại không ổn định:** số lần test thất bại do môi trường hoặc thời gian thay vì lỗi sản phẩm.
- **Khả năng phát hiện sớm:** lỗi được phát hiện ở tầng nào so với nơi nguyên nhân xuất hiện.
- **Thời gian chẩn đoán:** thời gian từ khi test thất bại đến khi xác định nguyên nhân.
- **Chi phí bảo trì:** thời gian sửa test, dữ liệu và môi trường sau thay đổi.
- **Lỗi lọt qua:** lỗi chỉ được phát hiện ở tầng cao hơn hoặc sau phát hành.
- **Độ bao phủ rủi ro:** tỷ lệ rủi ro quan trọng có bằng chứng phù hợp ở một hoặc nhiều tầng.

Không nên tối ưu riêng số lượng unit test, tỷ lệ pass hoặc tổng số E2E. Một bộ kiểm thử có ít E2E nhưng bỏ sót hành trình quan trọng vẫn không tốt; một bộ unit test rất lớn nhưng kiểm tra chi tiết triển khai cũng không tạo nhiều giá trị. Đọc các chỉ số cùng mức độ rủi ro, lịch sử lỗi và trải nghiệm phát triển.

## 13. Những hiểu lầm thường gặp

- **Coi kim tự tháp là tỷ lệ cố định:** tỷ lệ phù hợp phụ thuộc kiến trúc, rủi ro và khả năng kiểm thử của sản phẩm.
- **Cho rằng càng nhiều unit test càng tốt:** số lượng không đảm bảo test có ý nghĩa hoặc kiểm tra đúng hành vi.
- **Coi mọi kiểm thử API là integration test:** cách phân loại tùy phạm vi. Một API test có thể kiểm tra hợp đồng dịch vụ, hoặc có thể tích hợp nhiều thành phần thật; cần mô tả điều nó xác minh.
- **Dùng mock cho mọi phụ thuộc:** mock giúp cô lập nhưng không chứng minh hệ thống thật tương thích. Các ranh giới quan trọng vẫn cần kiểm tra tích hợp hoặc hợp đồng.
- **Đưa mọi trường hợp lên E2E:** làm tăng thời gian chạy, độ không ổn định và chi phí bảo trì.
- **Cho rằng unit test có thể thay thế kiểm thử bảo mật hoặc khả năng sử dụng:** các thuộc tính này cần phương pháp và bằng chứng phù hợp.
- **Giữ E2E chỉ vì đã đầu tư viết:** nếu kịch bản trùng lặp, không còn đại diện hoặc không có giá trị phát hiện, cần xem xét điều chỉnh.
- **Đánh giá chất lượng chỉ bằng coverage:** coverage không cho biết khẳng định nghiệp vụ quan trọng đã được kiểm tra đúng hay chưa.

## 14. Checklist rà soát kim tự tháp kiểm thử

- [ ] Các luồng nghiệp vụ và rủi ro chính đã được xác định.
- [ ] Quy tắc logic có kiểm tra đơn vị đủ rõ và có giá trị.
- [ ] Các ranh giới dịch vụ, API, dữ liệu và hợp đồng có kiểm tra tầng giữa phù hợp.
- [ ] Các hành trình người dùng quan trọng có kiểm thử đầu cuối đại diện.
- [ ] Mỗi kiểm tra có mục tiêu rõ và không lặp lại vô ích ở nhiều tầng.
- [ ] Các kiểm tra nhanh chạy sớm trong pipeline.
- [ ] Kiểm thử E2E được giới hạn theo rủi ro và dễ chẩn đoán.
- [ ] Dữ liệu, môi trường và phụ thuộc được kiểm soát.
- [ ] Flaky test được theo dõi và có người chịu trách nhiệm.
- [ ] Bộ kiểm thử được rà soát khi kiến trúc, yêu cầu hoặc rủi ro thay đổi.
- [ ] Chỉ số thời gian, lỗi lọt qua và chi phí bảo trì được xem xét định kỳ.

## Kết luận

Mô hình kim tự tháp kiểm thử giúp nhóm thảo luận cách đặt bằng chứng ở các tầng khác nhau: nhiều kiểm tra đơn vị nhanh ở đáy, kiểm tra dịch vụ và tích hợp ở tầng giữa, cùng một số luồng đầu cuối quan trọng ở đỉnh. Đây là công cụ tư duy để cân bằng tốc độ, độ tin cậy và chi phí, không phải tỷ lệ test case bắt buộc. Hãy chọn tầng dựa trên rủi ro và câu hỏi cần xác minh, giữ kiểm tra ổn định, tránh trùng lặp và điều chỉnh phân bổ bằng dữ liệu thực tế.
