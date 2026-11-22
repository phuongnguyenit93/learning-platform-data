# Xác định mục tiêu kiểm thử toàn hệ thống và hành trình đầu cuối

Một thành phần có thể hoạt động đúng khi được kiểm tra riêng nhưng toàn bộ sản phẩm vẫn thất bại khi người dùng thực hiện một công việc hoàn chỉnh. Dữ liệu có thể không được chuyển đúng giữa các dịch vụ, trạng thái có thể không đồng bộ, quyền truy cập có thể thay đổi ở một bước trung gian hoặc một phụ thuộc bên ngoài có thể phản hồi khác dự kiến. Kiểm thử toàn hệ thống và kiểm thử đầu cuối giúp phát hiện những vấn đề chỉ xuất hiện khi nhiều phần phối hợp.

Để hai loại kiểm thử này tạo ra bằng chứng hữu ích, nhóm cần xác định rõ **hệ thống nào đang được đánh giá, hành trình nào cần hoạt động từ đầu đến cuối, chất lượng nào phải được chứng minh và kết quả nào đủ để kết luận**. Nếu mục tiêu chỉ là "chạy E2E" hoặc "kiểm thử toàn hệ thống" mà không có ranh giới, rủi ro và tiêu chí rõ ràng, bộ kiểm thử dễ trở nên lớn, chậm và khó chẩn đoán.

## 1. Kiểm thử toàn hệ thống và kiểm thử đầu cuối

### 1.1. Kiểm thử toàn hệ thống (system testing)

Kiểm thử toàn hệ thống đánh giá một hệ thống đã tích hợp như một chỉnh thể so với các yêu cầu hệ thống đã xác định. Đối tượng có thể bao gồm giao diện, dịch vụ, cơ sở dữ liệu, cấu hình, các thành phần nội bộ và những tích hợp thuộc ranh giới kiểm thử đã thống nhất.

Mục tiêu thường gồm:

- Xác minh các chức năng của hệ thống hoạt động đúng khi các thành phần phối hợp.
- Kiểm tra quy tắc nghiệp vụ và luồng xử lý ở cấp hệ thống.
- Đánh giá thuộc tính phi chức năng như hiệu năng, bảo mật, độ tin cậy, khả năng phục hồi, khả năng sử dụng và tương thích.
- Xác minh xử lý lỗi, quyền truy cập, dữ liệu, cấu hình và hành vi khi phụ thuộc không sẵn sàng.
- Cung cấp bằng chứng rằng hệ thống đáp ứng các yêu cầu và tiêu chí chất lượng đã thống nhất.

System testing thường được thực hiện trên một bản dựng tích hợp trong môi trường kiểm thử có kiểm soát. Nó không nhất thiết phải đi qua mọi hệ thống bên ngoài hoặc mọi bước trong hành trình thực tế của người dùng. Ranh giới cụ thể phụ thuộc vào sản phẩm và mục tiêu đánh giá.

### 1.2. Kiểm thử đầu cuối (end-to-end testing)

Kiểm thử đầu cuối xác minh một hành trình hoặc quy trình hoàn chỉnh từ điểm bắt đầu đến kết quả nghiệp vụ mong đợi, qua những thành phần và ranh giới cần thiết. Hành trình có thể đi qua nhiều dịch vụ nội bộ, giao diện, hệ thống bên ngoài, hàng đợi, nhà cung cấp hoặc vai trò người dùng.

Ví dụ, hành trình mua hàng có thể bắt đầu khi khách chọn sản phẩm và kết thúc khi đơn được xác nhận, thanh toán được ghi nhận, tồn kho được cập nhật và thông tin giao hàng được tạo. Nếu mục tiêu là xác minh trải nghiệm của khách, hành trình có thể bắt đầu từ giao diện người dùng. Nếu mục tiêu là xác minh quy trình tích hợp, hành trình có thể bắt đầu ở API hoặc sự kiện đầu vào.

E2E không đồng nghĩa với tự động hóa giao diện trình duyệt. Một hành trình đầu cuối có thể được kiểm tra bằng API, sự kiện, dịch vụ hoặc kết hợp nhiều cách. Điều quan trọng là nó xác minh kết quả xuyên suốt các ranh giới có ý nghĩa đối với mục tiêu.

### 1.3. Hai loại kiểm thử bổ sung cho nhau

| Tiêu chí | Kiểm thử toàn hệ thống | Kiểm thử đầu cuối |
|---|---|---|
| Câu hỏi chính | Hệ thống tích hợp có đáp ứng yêu cầu hệ thống không? | Một hành trình hoặc quy trình hoàn chỉnh có tạo ra kết quả nghiệp vụ mong đợi không? |
| Phạm vi | Hệ thống trong ranh giới đã xác định | Chuỗi bước qua các thành phần và ranh giới cần thiết |
| Điểm bắt đầu | Bản dựng hệ thống tích hợp và các yêu cầu hệ thống | Một hành động, sự kiện hoặc nhu cầu khởi tạo hành trình |
| Trọng tâm | Chức năng và thuộc tính chất lượng của hệ thống | Tính liên tục của hành trình, bàn giao và kết quả cuối |
| Ví dụ | Kiểm tra phân quyền, hiệu năng, xử lý lỗi và chức năng của hệ thống quản lý đơn | Khách đặt hàng, thanh toán, nhận xác nhận và theo dõi giao hàng |
| Rủi ro nổi bật | Thiếu yêu cầu hệ thống, cấu hình sai, tương tác nội bộ lỗi | Sai lệch giữa các bước, dữ liệu không đồng bộ, tích hợp bên ngoài thất bại |

Một bộ system test có thể bao phủ nhiều yêu cầu và thuộc tính chất lượng mà không đi qua một hành trình người dùng dài. Một bộ E2E có thể xác minh hành trình quan trọng nhưng không thể chứng minh mọi yêu cầu hệ thống, mọi nhánh lỗi hoặc mọi thuộc tính phi chức năng.

Do đó, hai loại kiểm thử nên được lựa chọn theo rủi ro và bằng chứng cần có. Không nên dùng một vài luồng E2E để đại diện cho toàn bộ system testing, cũng không nên mặc định một bộ system test đã chứng minh mọi hành trình liên hệ thống.

## 2. Bắt đầu từ mục tiêu chất lượng

Trước khi thiết kế kịch bản, hãy xác định điều gì cần được chứng minh. Mục tiêu nên mô tả kết quả có ý nghĩa, đối tượng được đánh giá, điều kiện kiểm thử và cách đo hoặc quan sát.

Một mục tiêu quá chung như "hệ thống ổn định" khó giúp nhóm lựa chọn kiểm thử. Có thể chuyển thành mục tiêu cụ thể hơn:

- Khi có số lượng người dùng đồng thời theo tải dự kiến, thời gian phản hồi của luồng tìm kiếm phải nằm trong ngưỡng đã thống nhất.
- Người dùng không có quyền không thể xem hoặc thay đổi dữ liệu thuộc tài khoản khác.
- Khi nhà cung cấp thanh toán timeout sau khi đã tiếp nhận giao dịch, hệ thống không tạo giao dịch trùng và có thể đối soát trạng thái.
- Khi một dịch vụ nội bộ tạm thời không sẵn sàng, hệ thống phản hồi theo chính sách lỗi và phục hồi được khi dịch vụ hoạt động lại.
- Khi khách hoàn tất đơn hàng, thông tin đơn, thanh toán và giao hàng phải liên kết đúng với cùng một mã giao dịch.

Một mục tiêu kiểm thử hữu ích thường trả lời:

1. **Đối tượng:** hệ thống, chức năng, hành trình, vai trò hoặc tích hợp nào đang được kiểm tra?
2. **Điều kiện:** phiên bản, cấu hình, dữ liệu, tải và trạng thái ban đầu là gì?
3. **Hành vi mong đợi:** hệ thống cần làm gì hoặc bảo đảm thuộc tính nào?
4. **Bằng chứng:** trạng thái, dữ liệu, phản hồi, log, chỉ số hoặc kết quả nào xác nhận điều đó?
5. **Mức chấp nhận:** ngưỡng hoặc điều kiện nào được dùng để kết luận?

## 3. Xác định ranh giới hệ thống và hành trình

### 3.1. Vẽ ranh giới hệ thống

Trước tiên, xác định những thành phần thuộc hệ thống đang kiểm thử và những phụ thuộc nằm ngoài ranh giới. Ranh giới có thể bao gồm:

- Ứng dụng web hoặc di động.
- API gateway và các dịch vụ nghiệp vụ.
- Cơ sở dữ liệu, cache và kho tệp.
- Message broker và các tác vụ nền.
- Dịch vụ xác thực, phân quyền và quản lý danh tính.
- Hệ thống bên ngoài như thanh toán, vận chuyển, email hoặc SMS.
- Hạ tầng triển khai, cấu hình, giám sát và các dịch vụ nền tảng.

Không phải tất cả thành phần đều cần chạy thật trong mọi lần kiểm thử. Nhóm có thể thay thế một phụ thuộc để cô lập hoặc tạo tình huống xác định, nhưng phải ghi rõ phần được mô phỏng và bổ sung bằng chứng ở cấp phù hợp cho ranh giới có rủi ro cao.

### 3.2. Xác định điểm bắt đầu và kết thúc của hành trình

Với mỗi hành trình, cần ghi:

- Ai khởi tạo hành trình: khách hàng, nhân viên, hệ thống khác hay một sự kiện theo lịch?
- Điều kiện trước khi bắt đầu: tài khoản, quyền, dữ liệu và trạng thái nào cần có?
- Hành động hoặc sự kiện khởi tạo là gì?
- Những bước nghiệp vụ và bàn giao nào phải xảy ra?
- Có nhánh quyết định, xử lý song song, chờ hoặc thử lại nào không?
- Kết quả nghiệp vụ nào đánh dấu hành trình hoàn tất?
- Có tác động phụ nào cần xác minh như cập nhật dữ liệu, gửi thông báo hoặc ghi audit?

Điểm kết thúc không nhất thiết là trang "Thành công" trên giao diện. Một hành trình thanh toán chỉ hiển thị thành công nhưng giao dịch chưa được ghi nhận hoặc chưa đối soát thì chưa chắc đã đạt mục tiêu nghiệp vụ.

### 3.3. Phân biệt hành trình chính và hành trình ngoại lệ

Một hành trình chính thường mô tả đường đi phổ biến hoặc có giá trị cao. Tuy nhiên, hệ thống thường thất bại ở các nhánh ngoại lệ:

- Người dùng thiếu quyền hoặc phiên đăng nhập hết hạn.
- Dữ liệu đầu vào không hợp lệ hoặc thay đổi giữa các bước.
- Phụ thuộc timeout, từ chối hoặc phản hồi không đúng định dạng.
- Yêu cầu được gửi lặp hoặc đến sai thứ tự.
- Một bước thành công nhưng bước tiếp theo thất bại.
- Người dùng hủy hoặc rời khỏi quy trình giữa chừng.
- Tác vụ nền chậm, chạy lại hoặc xử lý đồng thời.

Nhóm nên xác định các hành trình ngoại lệ theo rủi ro và hậu quả, không chỉ kiểm tra một luồng thành công duy nhất.

## 4. Phân tích rủi ro để chọn mục tiêu ưu tiên

Không thể kiểm tra mọi tổ hợp hành vi trong một hệ thống lớn. Hãy chọn mục tiêu và hành trình dựa trên khả năng xảy ra lỗi, mức độ ảnh hưởng, khả năng phát hiện và chi phí khắc phục.

Các câu hỏi gợi ý:

- Nếu hành trình thất bại, người dùng hoặc nghiệp vụ chịu hậu quả gì?
- Có liên quan đến tiền, dữ liệu nhạy cảm, quyền truy cập hoặc nghĩa vụ tuân thủ không?
- Hành trình đi qua bao nhiêu dịch vụ hoặc nhà cung cấp?
- Có trạng thái bất đồng bộ, retry, timeout hoặc xử lý song song không?
- Thành phần vừa thay đổi có nhiều phụ thuộc hoặc lịch sử lỗi không?
- Lỗi có dễ phát hiện từ log và giám sát hay chỉ xuất hiện qua khiếu nại?
- Có phương án khôi phục, quay lui hoặc xử lý thủ công không?

Có thể lập ma trận ưu tiên:

| Mức ưu tiên | Đặc điểm | Cách tiếp cận |
|---|---|---|
| Rất cao | Có thể gây mất tiền, sai giao dịch, lộ dữ liệu, vi phạm quy định hoặc mất dịch vụ diện rộng | System test và E2E có bằng chứng rõ cho cả đường thành công và lỗi quan trọng; xem xét kiểm thử bảo mật, phục hồi và đối soát |
| Cao | Hành trình cốt lõi, nhiều tích hợp hoặc thay đổi có tác động rộng | Bao phủ các nhánh chính, bàn giao, timeout, retry và trạng thái trung gian |
| Trung bình | Chức năng hỗ trợ, ảnh hưởng có giới hạn và có phương án xử lý | Chọn các tình huống đại diện, kết hợp kiểm thử ở cấp thấp hơn |
| Thấp | Tác động nhỏ, ít sử dụng hoặc có thể khôi phục dễ dàng | Kiểm thử chọn lọc và ghi nhận lý do về phạm vi |

Mức ưu tiên cần được xác nhận với chủ sở hữu nghiệp vụ và kỹ thuật. Một điểm rủi ro thấp về tần suất vẫn có thể cần kiểm soát nghiêm ngặt nếu hậu quả rất lớn.

## 5. Chuyển mục tiêu thành phạm vi kiểm thử

### 5.1. Bao phủ chức năng hệ thống

Xác định chức năng và quy tắc quan trọng cần xác minh ở cấp hệ thống:

- Luồng thao tác chính và các nhánh quyết định.
- Xác thực, phân quyền và quyền trên tài nguyên.
- Kiểm tra dữ liệu, ràng buộc và chuyển đổi.
- Trạng thái nghiệp vụ và tác động phụ.
- Tích hợp nội bộ, thông điệp và xử lý nền.
- Hành vi khi lỗi, thử lại, hủy và phục hồi.

Mỗi yêu cầu quan trọng nên liên kết với ít nhất một hoạt động kiểm thử và một kết quả mong đợi có thể quan sát. Nếu một yêu cầu không có bằng chứng hoặc không có người chịu trách nhiệm, đó là khoảng trống cần xử lý.

### 5.2. Bao phủ thuộc tính phi chức năng

Kiểm thử hệ thống cần xem xét những thuộc tính không thể đánh giá chỉ bằng việc chức năng trả về kết quả đúng:

| Thuộc tính | Mục tiêu có thể xác định | Bằng chứng phù hợp |
|---|---|---|
| Hiệu năng | Thời gian phản hồi, thông lượng, mức sử dụng tài nguyên ở tải xác định | Kết quả tải, phân vị thời gian phản hồi, CPU, bộ nhớ, truy vấn chậm |
| Khả năng mở rộng | Hệ thống duy trì mục tiêu khi tải tăng theo mô hình dự kiến | Kết quả tải tăng dần, giới hạn và điểm bão hòa |
| Bảo mật | Người dùng và dịch vụ chỉ truy cập tài nguyên được phép | Kết quả kiểm thử quyền, xác thực, kiểm tra lỗ hổng và audit |
| Độ tin cậy | Hệ thống duy trì hoặc khôi phục dịch vụ theo mục tiêu | Tỷ lệ lỗi, thời gian phục hồi, kết quả kiểm thử lỗi |
| Khả năng phục hồi | Hệ thống xử lý được sự cố và trở lại trạng thái nhất quán | Kết quả failover, restart, retry, đối soát và phục hồi dữ liệu |
| Khả năng sử dụng | Người dùng hoàn thành tác vụ với mức khó khăn chấp nhận được | Quan sát tác vụ, tỷ lệ hoàn thành, lỗi thao tác và phản hồi người dùng |
| Khả năng tiếp cận | Người dùng có thể thao tác bằng phương thức hỗ trợ được yêu cầu | Kiểm tra bàn phím, trình đọc màn hình, tương phản và cấu trúc nội dung |
| Tương thích | Hành vi đúng trên nền tảng và phiên bản được hỗ trợ | Ma trận trình duyệt, thiết bị, hệ điều hành và kết quả kiểm thử |
| Khả năng vận hành | Nhóm vận hành phát hiện, chẩn đoán và xử lý sự cố | Log, metric, trace, cảnh báo và runbook |

Không nhất thiết mọi thuộc tính đều cần kiểm thử E2E. Chọn cấp và phương pháp phù hợp: hiệu năng có thể cần tải ở API hoặc hệ thống; bảo mật cần kiểm tra nhiều lớp; khả năng sử dụng cần quan sát người dùng; phục hồi cần mô phỏng lỗi trên những thành phần có rủi ro.

### 5.3. Bao phủ theo hành trình

Với mỗi hành trình E2E, hãy xác định:

- Điều kiện đầu vào và dữ liệu ban đầu.
- Vai trò hoặc danh tính khởi tạo.
- Các dịch vụ và hệ thống tham gia.
- Các bước, sự kiện và bàn giao.
- Trạng thái mong đợi sau từng bước quan trọng.
- Kết quả cuối cùng và tác động phụ.
- Nhánh lỗi hoặc điều kiện dừng.
- Bằng chứng và nguồn xác nhận.

Một hành trình tốt không chỉ kiểm tra giao diện hiển thị đúng mà còn xác minh dữ liệu và trạng thái ở các ranh giới quan trọng.

## 6. Thiết kế mục tiêu đo được và tiêu chí chấp nhận

Mục tiêu nên có điều kiện và ngưỡng đủ rõ để người khác có thể đánh giá cùng một kết quả.

Ví dụ về mục tiêu hiệu năng:

> Với tải 300 người dùng đồng thời theo kịch bản sử dụng đã thống nhất, 95% yêu cầu tìm kiếm hoàn tất trong không quá 2 giây trong khoảng đo 15 phút, tỷ lệ lỗi dưới 1% và tài nguyên không vượt ngưỡng vận hành.

Ví dụ về mục tiêu nhất quán nghiệp vụ:

> Khi một giao dịch thanh toán được nhà cung cấp xác nhận thành công, đơn hàng được chuyển sang trạng thái đã thanh toán đúng một lần; callback lặp không tạo thêm giao dịch hoặc thông báo trùng.

Ví dụ về mục tiêu phân quyền:

> Người dùng thuộc tài khoản A không thể đọc, cập nhật hoặc tải tệp của tài khoản B bằng giao diện hoặc gọi trực tiếp API.

Khi đặt mục tiêu, cần thống nhất:

- Mức tải và phân bố hành vi đại diện.
- Thiết bị, nền tảng, vùng triển khai và cấu hình.
- Mốc thời gian, múi giờ và dữ liệu tham chiếu.
- Cách đo, công cụ và nguồn log.
- Ngưỡng đạt, ngưỡng cảnh báo và điều kiện thất bại.
- Người có thẩm quyền chấp nhận rủi ro còn lại.

Tránh đặt ngưỡng tùy ý chỉ để có con số. Mục tiêu nên xuất phát từ yêu cầu người dùng, SLO/SLA, chính sách, tiêu chuẩn hoặc dữ liệu vận hành.

## 7. Xây dựng kịch bản system test và E2E

### 7.1. Kịch bản system test

Một kịch bản system test thường có:

1. Mã và mục tiêu kiểm thử.
2. Yêu cầu hoặc rủi ro được liên kết.
3. Phiên bản hệ thống, cấu hình và môi trường.
4. Điều kiện bắt đầu và dữ liệu chuẩn bị.
5. Các bước thực hiện.
6. Kết quả mong đợi tại những điểm quan trọng.
7. Kết quả quan sát, log hoặc bằng chứng.
8. Tiêu chí đạt/không đạt và giới hạn đã biết.

Ví dụ: xác minh hệ thống từ chối truy cập API khi token hết hạn, không trả dữ liệu nhạy cảm, ghi audit phù hợp và cho phép người dùng đăng nhập lại theo chính sách.

### 7.2. Kịch bản E2E

Một kịch bản E2E nên mô tả một mục tiêu người dùng hoặc nghiệp vụ xuyên suốt. Nội dung thường gồm:

- Persona hoặc vai trò người thực hiện.
- Điểm bắt đầu của hành trình.
- Điều kiện và dữ liệu trước khi chạy.
- Các bước qua những thành phần liên quan.
- Các điểm bàn giao cần xác minh.
- Kết quả cuối và tác động phụ.
- Cách dọn dữ liệu hoặc khôi phục trạng thái sau kiểm thử.

Ví dụ: khách đăng nhập, chọn sản phẩm, áp dụng mã giảm giá, thanh toán bằng phương thức thử nghiệm, nhận xác nhận đơn và kiểm tra trạng thái giao hàng được tạo.

Không nên kiểm tra mọi chi tiết nội bộ qua một kịch bản E2E. Hãy giữ các khẳng định ở mức hành vi nghiệp vụ và kiểm tra chi tiết của từng thành phần ở cấp thấp hơn để khi lỗi xảy ra, nhóm có thể xác định nguyên nhân nhanh.

## 8. Ví dụ xuyên suốt: hành trình đặt hàng trực tuyến

Giả sử một nền tảng thương mại điện tử có các thành phần: Web App, Order Service, Inventory Service, Payment Service, Shipping Service, Notification Service và nhà cung cấp thanh toán bên ngoài.

### 8.1. Mục tiêu hệ thống

- Đơn hợp lệ được tạo với mã định danh duy nhất.
- Tồn kho được giữ hoặc trừ theo đúng quy tắc.
- Số tiền gửi thanh toán khớp với tổng tiền đơn hàng.
- Kết quả thanh toán cập nhật trạng thái đơn đúng một lần.
- Thông tin giao hàng được tạo khi đơn đủ điều kiện.
- Thông báo được gửi theo trạng thái nghiệp vụ đã xác nhận.
- Người dùng chỉ truy cập dữ liệu đơn thuộc quyền của mình.

### 8.2. Hành trình E2E thành công

~~~mermaid
flowchart TD
    A["Khách đăng nhập"] --> B["Chọn sản phẩm và xác nhận giỏ hàng"]
    B --> C["Kiểm tra giá và tồn kho"]
    C --> D["Tạo đơn chờ thanh toán"]
    D --> E["Gửi yêu cầu thanh toán"]
    E --> F["Nhận kết quả thanh toán hợp lệ"]
    F --> G["Xác nhận đơn và cập nhật tồn kho"]
    G --> H["Tạo thông tin giao hàng"]
    H --> I["Gửi thông báo xác nhận"]
    I --> J["Khách xem trạng thái đơn"]
~~~

Nhóm cần xác minh tại các điểm quan trọng:

| Điểm | Dữ liệu hoặc trạng thái cần xác minh |
|---|---|
| Tạo đơn | Mã đơn duy nhất, sản phẩm, số lượng, giá và chủ sở hữu |
| Giữ tồn kho | Số lượng khả dụng thay đổi theo chính sách |
| Tạo thanh toán | Số tiền, tiền tệ, mã đơn và khóa idempotency đúng |
| Nhận kết quả | Chữ ký hoặc nguồn callback hợp lệ; giao dịch liên kết đúng đơn |
| Xác nhận đơn | Trạng thái chỉ chuyển một lần và không ghi nhận trùng |
| Tạo giao hàng | Địa chỉ, mặt hàng, mã đơn và trạng thái bàn giao chính xác |
| Gửi thông báo | Đúng người nhận, nội dung và sự kiện nghiệp vụ |
| Xem đơn | Người dùng thấy trạng thái mới nhất trong phạm vi quyền |

### 8.3. Hành trình lỗi quan trọng

Ngoài đường thành công, chọn một số tình huống theo rủi ro:

- Thanh toán bị từ chối: đơn không chuyển sang đã thanh toán; tồn kho được xử lý theo chính sách.
- Nhà cung cấp timeout sau khi đã nhận yêu cầu: hệ thống không tạo giao dịch thứ hai khi thử lại.
- Callback thanh toán đến hai lần: trạng thái và số tiền chỉ được ghi nhận một lần.
- Tồn kho thay đổi trước khi xác nhận đơn: đơn bị từ chối hoặc xử lý theo quy tắc đã duyệt.
- Notification Service không sẵn sàng: trạng thái đơn vẫn nhất quán và thông báo có thể được thử lại.
- Người dùng khác gọi API xem đơn: hệ thống từ chối và không tiết lộ dữ liệu.
- Shipping Service thất bại sau khi thanh toán thành công: đơn được giữ ở trạng thái có thể xử lý tiếp, không làm mất dấu giao dịch.

Những tình huống này giúp kiểm tra tính nhất quán xuyên suốt và khả năng phục hồi khi một bước không hoàn tất.

## 9. Dữ liệu và môi trường kiểm thử

System test và E2E phụ thuộc nhiều vào dữ liệu, cấu hình và môi trường. Một kịch bản đúng vẫn có thể cho kết quả không đáng tin nếu dữ liệu cũ, phụ thuộc không ổn định hoặc cấu hình khác với mục tiêu.

### 9.1. Chuẩn bị dữ liệu

Mỗi kịch bản cần xác định:

- Dữ liệu đầu vào và dữ liệu tham chiếu.
- Người dùng, vai trò và quyền.
- Trạng thái ban đầu của đơn hàng, thanh toán hoặc tài nguyên.
- Các dữ liệu phụ thuộc như tồn kho, giá, khuyến mãi và địa chỉ.
- Định danh duy nhất để truy vết và tránh xung đột giữa các lần chạy.
- Cách làm sạch hoặc khôi phục sau kiểm thử.

Ưu tiên dữ liệu tổng hợp hoặc tài khoản thử nghiệm. Không dùng dữ liệu cá nhân hoặc thông tin bí mật production nếu chưa được phép và bảo vệ phù hợp.

### 9.2. Chọn môi trường

Môi trường kiểm thử cần phù hợp với mục tiêu:

- Môi trường tích hợp để kiểm tra các dịch vụ nội bộ.
- Sandbox để xác minh giao tiếp với nhà cung cấp bên ngoài.
- Staging hoặc môi trường tiền sản xuất để kiểm tra cấu hình và triển khai gần thực tế.
- Môi trường tải chuyên biệt để đánh giá hiệu năng và giới hạn tài nguyên.

Ghi lại khác biệt giữa môi trường kiểm thử và production: phiên bản, cấu hình, dữ liệu, quyền, quota, mạng, vùng triển khai và phụ thuộc. Một kết quả E2E trên sandbox không tự chứng minh rằng production có cùng hành vi.

### 9.3. Tránh kiểm thử gây tác động thật

Với hành trình có thể tạo giao dịch, gửi thông báo hoặc thay đổi dữ liệu, dùng tài khoản và dịch vụ thử nghiệm, hoặc cơ chế cô lập được phê duyệt. Bảo đảm thao tác dọn dẹp không làm thay đổi dữ liệu thật. Khi dùng dữ liệu mô phỏng, ghi rõ giới hạn của bằng chứng.

## 10. Chọn điểm kiểm tra và mức tự động hóa

Một bộ E2E quá lớn có thể chậm, dễ lỗi do môi trường và khó xác định nguyên nhân. Hãy chọn điểm kiểm tra ở nơi cung cấp bằng chứng rõ nhất.

- Dùng unit/component test cho logic nội bộ và điều kiện biên.
- Dùng contract test cho giao tiếp giữa provider và consumer.
- Dùng integration test cho ranh giới giữa các dịch vụ, cơ sở dữ liệu, broker hoặc nhà cung cấp.
- Dùng system test để đánh giá các yêu cầu và thuộc tính của hệ thống tích hợp.
- Dùng E2E cho hành trình nghiệp vụ có giá trị cao và những bàn giao cần xác minh xuyên suốt.

Tự động hóa E2E phù hợp khi hành trình ổn định, dữ liệu có thể quản lý, kết quả có thể quan sát và chi phí bảo trì hợp lý. Kiểm thử thăm dò vẫn cần thiết để tìm những vấn đề chưa được mô tả trong kịch bản. Một số đánh giá như khả năng sử dụng, trải nghiệm hoặc quy trình xử lý thủ công cần quan sát con người.

## 11. Tiêu chí bắt đầu và kết thúc

### 11.1. Ví dụ tiêu chí bắt đầu

- Bản dựng đúng phiên bản đã được triển khai và xác định.
- Các dịch vụ và phụ thuộc thiết yếu sẵn sàng.
- Cấu hình môi trường được kiểm tra.
- Dữ liệu và tài khoản thử nghiệm đã chuẩn bị.
- Yêu cầu, oracle và kết quả mong đợi đủ rõ.
- Các kiểm thử cấp thấp cần thiết đã đạt hoặc lỗi còn lại đã được đánh giá.
- Có thể thu thập log, metric, trace và bằng chứng cần thiết.

### 11.2. Ví dụ tiêu chí kết thúc

- Các mục tiêu ưu tiên cao đã có bằng chứng đạt.
- Những hành trình quan trọng và nhánh lỗi được chọn đã chạy.
- Không còn lỗi nghiêm trọng chưa được xử lý hoặc chấp nhận theo quy trình.
- Các kết quả phi chức năng đã được so sánh với ngưỡng.
- Dữ liệu, trạng thái và tác động phụ đã được xác minh.
- Lỗi còn lại, giới hạn môi trường và rủi ro chưa bao phủ được ghi nhận.
- Người có thẩm quyền đã xem xét bằng chứng và quyết định bước tiếp theo.

Tiêu chí vào/ra phải tương xứng với rủi ro. Không nên chỉ dùng tỷ lệ pass tổng thể vì một lỗi nghiêm trọng trong luồng thanh toán có thể bị che khuất bởi hàng trăm kiểm thử ít quan trọng đã đạt.

## 12. Theo dõi kết quả và khả năng chẩn đoán

Kết quả system test và E2E cần đủ thông tin để tái hiện và xác định ranh giới xảy ra lỗi. Nên thu thập:

- Mã hành trình, mã kiểm thử, phiên bản ứng dụng và môi trường.
- Người dùng thử nghiệm, dữ liệu và trạng thái trước khi chạy.
- Thời điểm, múi giờ và chuỗi hành động.
- Request/response hoặc sự kiện tại ranh giới cần thiết, đã loại bỏ bí mật.
- Log, metric, trace và correlation ID.
- Trạng thái dữ liệu trước/sau và tác động phụ.
- Kết quả mong đợi, kết quả thực tế và mức độ ảnh hưởng.

Với hành trình bất đồng bộ, không nên chỉ đợi một khoảng thời gian cố định rồi kiểm tra. Dùng điều kiện chờ có giới hạn, polling có kiểm soát hoặc tín hiệu hoàn tất phù hợp; khi hết hạn, lưu lại trạng thái và trace để điều tra.

## 13. Đo lường mức độ bao phủ và hiệu quả

Một số chỉ số có thể giúp nhóm đánh giá:

- Tỷ lệ yêu cầu hệ thống quan trọng có kiểm thử và bằng chứng.
- Tỷ lệ hành trình ưu tiên cao đã được xác minh.
- Số nhánh lỗi và điểm bàn giao quan trọng đã được kiểm tra.
- Số lỗi phát hiện ở system/E2E và số lỗi lọt ra production.
- Tỷ lệ kiểm thử E2E không ổn định và số lần chạy lại.
- Thời gian chạy bộ kiểm thử và thời gian điều tra thất bại.
- Tỷ lệ thất bại do sản phẩm, môi trường, dữ liệu hoặc phụ thuộc bên ngoài.
- Số rủi ro còn lại chưa có biện pháp kiểm soát hoặc người chấp nhận.

Không nên xem số lượng E2E hoặc tỷ lệ tự động hóa là thước đo chất lượng duy nhất. Một bộ nhỏ các hành trình có rủi ro cao, ổn định và có bằng chứng tốt có thể hữu ích hơn một bộ lớn nhưng khó bảo trì.

## 14. Những sai lầm thường gặp

- **Nhầm system test với E2E:** system test đánh giá hệ thống trong ranh giới đã xác định; E2E tập trung vào hành trình xuyên suốt. Cần chọn mục tiêu rõ ràng cho từng hoạt động.
- **Chỉ kiểm tra đường thành công:** bỏ qua timeout, từ chối, retry, hủy, quyền truy cập và trạng thái trung gian.
- **Xem giao diện thành công là bằng chứng hoàn tất:** cần xác minh trạng thái và tác động nghiệp vụ ở những ranh giới quan trọng.
- **Đưa mọi kiểm tra vào E2E:** làm bộ kiểm thử chậm, mong manh và khó chẩn đoán. Phân bổ kiểm thử ở cấp phù hợp.
- **Không xác định điểm kết thúc:** một hành trình có thể dừng ở bước trung gian nhưng vẫn bị xem là thành công.
- **Dùng dữ liệu dùng chung:** các lần chạy có thể ảnh hưởng lẫn nhau, gây lỗi ngẫu nhiên.
- **Bỏ qua khác biệt môi trường:** sandbox và staging không nhất thiết giống production.
- **Không thu thập trace và trạng thái:** lỗi liên dịch vụ khó tái hiện nếu thiếu correlation ID và bằng chứng.
- **Dùng ngưỡng không có căn cứ:** tiêu chí cần gắn với nhu cầu, SLO/SLA hoặc rủi ro đã xác nhận.
- **Bỏ qua rủi ro còn lại:** kết quả pass không có nghĩa mọi rủi ro đã được loại bỏ.

## 15. Checklist xác định mục tiêu system test và E2E

- [ ] Hệ thống và ranh giới kiểm thử được mô tả rõ.
- [ ] Mục tiêu chất lượng gắn với yêu cầu, người dùng hoặc rủi ro cụ thể.
- [ ] Hành trình có điểm bắt đầu, điều kiện trước và kết quả cuối rõ ràng.
- [ ] Các thành phần, dịch vụ và nhà cung cấp tham gia đã được xác định.
- [ ] Nhánh lỗi, retry, timeout, hủy và quyền truy cập quan trọng được xem xét.
- [ ] Kết quả mong đợi và nguồn xác nhận có thẩm quyền.
- [ ] Tiêu chí đo được và ngưỡng đạt/không đạt đã thống nhất.
- [ ] Dữ liệu, môi trường và cấu hình phù hợp với mục tiêu.
- [ ] Có log, metric, trace và cách truy vết hành trình.
- [ ] Kiểm thử được phân bổ ở cấp phù hợp, tránh dồn mọi thứ vào E2E.
- [ ] Tiêu chí vào/ra và người quyết định được xác định.
- [ ] Rủi ro, giới hạn và phần chưa được bao phủ được ghi nhận.

## 16. Luồng xây dựng mục tiêu và bằng chứng

~~~mermaid
flowchart TD
    A["Yêu cầu, người dùng và mục tiêu chất lượng"]
    B["Xác định ranh giới hệ thống"]
    C["Lập bản đồ hành trình và điểm bàn giao"]
    D["Đánh giá rủi ro và ưu tiên"]
    E["Chọn system test, E2E và cấp kiểm thử bổ trợ"]
    F["Xác định dữ liệu, môi trường, oracle và ngưỡng"]
    G["Thực thi và thu thập bằng chứng"]
    H["Đánh giá đạt, lỗi và rủi ro còn lại"]
    I["Quyết định phát hành hoặc hành động tiếp"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
    H -. "Khoảng trống hoặc thay đổi" .-> C
    I -. "Phản hồi vận hành" .-> A
~~~

Kiểm thử toàn hệ thống và đầu cuối có giá trị khi mục tiêu, ranh giới và bằng chứng được xác định trước. System testing cho biết hệ thống tích hợp có đáp ứng các yêu cầu và thuộc tính chất lượng hay không; E2E cho biết hành trình quan trọng có đi qua các thành phần và tạo ra kết quả nghiệp vụ hoàn chỉnh hay không. Khi lựa chọn theo rủi ro, kiểm tra cả nhánh lỗi và thu thập bằng chứng có thể truy vết, nhóm có cơ sở đáng tin cậy hơn để đánh giá chất lượng trước khi phát hành.
