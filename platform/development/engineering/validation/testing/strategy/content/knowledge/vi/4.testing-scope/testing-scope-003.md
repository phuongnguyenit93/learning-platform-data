# Lựa chọn chức năng, luồng nghiệp vụ và thuộc tính chất lượng cần kiểm tra

Phạm vi kiểm thử xác định những gì cần được kiểm chứng trong một sản phẩm, một tính năng hoặc một bản phát hành. Việc lựa chọn phạm vi không đơn giản là lấy toàn bộ danh sách yêu cầu rồi viết trường hợp kiểm thử cho từng mục. Nhóm cần hiểu người dùng thực hiện công việc gì, chức năng nào hỗ trợ công việc đó, dữ liệu và thành phần nào tham gia, đồng thời xác định những thuộc tính chất lượng có thể ảnh hưởng đến kết quả.

Một phạm vi tốt tập trung bằng chứng vào những hành vi và rủi ro quan trọng nhất. Nó cho biết phần nào sẽ được kiểm tra, ở mức độ nào, trong điều kiện nào và phần nào chưa được kiểm tra sâu. Phạm vi rõ ràng giúp nhóm phân bổ nguồn lực hợp lý, tránh bỏ sót các điểm nối giữa chức năng và luồng nghiệp vụ, đồng thời giúp người ra quyết định hiểu giới hạn của kết quả kiểm thử.

Trong chiến lược kiểm thử, việc lựa chọn phạm vi cần kết hợp ba góc nhìn:

- **Chức năng:** hệ thống cung cấp khả năng gì và từng quy tắc nghiệp vụ hoạt động ra sao.
- **Luồng nghiệp vụ:** người dùng hoặc hệ thống phối hợp nhiều chức năng để hoàn thành một mục tiêu như thế nào.
- **Thuộc tính chất lượng:** hệ thống thực hiện công việc với mức hiệu năng, bảo mật, độ tin cậy, khả năng sử dụng và các đặc tính khác ra sao.

Chỉ kiểm tra từng chức năng riêng lẻ có thể bỏ sót lỗi khi các chức năng kết hợp. Chỉ chạy một vài luồng đầu cuối cũng có thể không phát hiện được các giá trị biên, quy tắc riêng hoặc điều kiện lỗi. Chỉ xác nhận chức năng đúng cũng chưa đủ nếu sản phẩm chậm, không an toàn hoặc khó phục hồi. Vì vậy, nhóm cần chọn và liên kết cả ba góc nhìn theo rủi ro.

## 1. Hiểu sản phẩm trước khi chọn phạm vi

Trước khi liệt kê những gì cần kiểm thử, hãy tìm hiểu mục đích của sản phẩm và bối cảnh sử dụng. Một chức năng có vẻ nhỏ trong giao diện có thể liên quan đến nhiều dịch vụ, dữ liệu hoặc quy tắc quan trọng ở phía sau.

Những câu hỏi khởi đầu gồm:

- Ai sử dụng sản phẩm và họ muốn hoàn thành mục tiêu gì?
- Những hành trình nào có tần suất sử dụng cao hoặc ảnh hưởng lớn đến người dùng?
- Các quy tắc nghiệp vụ, trạng thái và điều kiện nào quyết định kết quả?
- Dữ liệu được tạo, đọc, cập nhật, xóa hoặc trao đổi giữa những thành phần nào?
- Những dịch vụ, thiết bị, nền tảng hoặc nhà cung cấp bên ngoài nào tham gia?
- Nếu một hành vi sai, ai bị ảnh hưởng và hậu quả là gì?
- Sản phẩm phải đáp ứng yêu cầu nào về hiệu năng, bảo mật, quyền riêng tư, khả năng tiếp cận hoặc tuân thủ?
- Những thay đổi nào xuất hiện trong bản phát hành và chúng có thể ảnh hưởng đến khu vực nào khác?

Nguồn thông tin có thể gồm yêu cầu, tiêu chí chấp nhận, mô hình nghiệp vụ, sơ đồ kiến trúc, hợp đồng API, thiết kế giao diện, dữ liệu vận hành, báo cáo sự cố và trao đổi với người hiểu sản phẩm. Không nên chỉ dựa vào tài liệu nếu hành vi thực tế đã khác; cần xác minh những giả định quan trọng với người phụ trách sản phẩm và kỹ thuật.

### Xây dựng bản đồ chức năng và hành trình

Có thể bắt đầu bằng cách lập danh sách các nhóm người dùng, mục tiêu và hành trình chính. Sau đó phân rã mỗi hành trình thành các bước nghiệp vụ, chức năng hỗ trợ và thành phần liên quan.

Ví dụ với một ứng dụng thương mại điện tử:

| Mục tiêu người dùng | Các bước nghiệp vụ | Chức năng liên quan |
|---|---|---|
| Tìm và chọn sản phẩm | Tìm kiếm, xem chi tiết, chọn biến thể | Tìm kiếm, lọc, xem tồn kho, quản lý danh mục |
| Đặt hàng | Thêm giỏ, áp dụng ưu đãi, nhập địa chỉ, xác nhận đơn | Giỏ hàng, khuyến mãi, tính phí, quản lý đơn |
| Thanh toán | Chọn phương thức, gửi yêu cầu, nhận kết quả | Tích hợp cổng thanh toán, ghi nhận giao dịch |
| Nhận hàng | Theo dõi, xác nhận giao, xử lý vấn đề | Vận chuyển, thông báo, cập nhật trạng thái |
| Đổi trả hoặc hoàn tiền | Tạo yêu cầu, kiểm tra điều kiện, xử lý hoàn tiền | Chính sách đổi trả, kho, thanh toán, kế toán |

Bản đồ này giúp nhìn thấy mối liên hệ giữa các chức năng. Chẳng hạn, thay đổi cách tính khuyến mãi có thể ảnh hưởng đến giỏ hàng, tổng tiền, thanh toán, hóa đơn và hoàn tiền. Nhóm có thể dùng bản đồ để xác định phạm vi kiểm thử theo cả chức năng thay đổi và hành trình chịu ảnh hưởng.

## 2. Lựa chọn chức năng cần kiểm tra

Chức năng mô tả khả năng mà hệ thống cung cấp, chẳng hạn tạo tài khoản, tìm kiếm, tính phí, phân quyền, xuất báo cáo hoặc hoàn tiền. Khi lựa chọn chức năng, cần xem xét giá trị đối với người dùng, mức độ quan trọng của quy tắc nghiệp vụ, độ phức tạp và rủi ro khi hành vi sai.

### Xác định các chức năng trọng yếu

Một chức năng thường đáng ưu tiên nếu nó:

- Nằm trên hành trình chính giúp người dùng đạt mục tiêu.
- Xử lý tiền, quyền truy cập, dữ liệu nhạy cảm hoặc dữ liệu khó khôi phục.
- Thực thi quy tắc nghiệp vụ phức tạp hoặc có nhiều điều kiện.
- Được nhiều người dùng hoặc nhiều thành phần phụ thuộc.
- Vừa được thay đổi đáng kể hoặc có lịch sử phát sinh lỗi.
- Có tác động lớn nếu ngừng hoạt động hoặc trả kết quả sai.
- Khó phát hiện hoặc khó khắc phục khi có lỗi.

Chức năng ít được dùng vẫn có thể có mức rủi ro cao. Ví dụ, chức năng quản trị quyền có thể chỉ được một số người dùng sử dụng nhưng nếu cấp quyền sai có thể làm lộ dữ liệu của toàn hệ thống. Ngược lại, một chức năng được dùng thường xuyên nhưng lỗi chỉ gây sai lệch trình bày nhỏ có thể được ưu tiên theo cách khác.

### Phân tích quy tắc và các trường hợp của chức năng

Sau khi chọn chức năng, hãy xác định quy tắc quyết định hành vi. Mỗi quy tắc có thể có:

- Điều kiện đầu vào và dữ liệu bắt buộc.
- Vai trò hoặc quyền cần có.
- Trạng thái trước khi thao tác.
- Điều kiện thành công và kết quả đầu ra.
- Điều kiện từ chối hoặc thất bại.
- Giới hạn, giá trị biên và trường hợp ngoại lệ.
- Tác động đến dữ liệu hoặc các thành phần khác.

Ví dụ, chức năng áp dụng mã giảm giá có thể cần kiểm tra mã tồn tại, còn hiệu lực, đạt giá trị đơn tối thiểu, áp dụng cho sản phẩm phù hợp, giới hạn số lần sử dụng và không vượt quá mức giảm tối đa. Kiểm tra duy nhất trường hợp mã hợp lệ sẽ không đủ để xác nhận toàn bộ quy tắc.

Có thể dùng các kỹ thuật thiết kế kiểm thử để chọn trường hợp đại diện:

- **Phân vùng tương đương:** chia đầu vào thành các nhóm được xử lý tương tự, sau đó chọn đại diện từ mỗi nhóm.
- **Phân tích giá trị biên:** kiểm tra ngay dưới, tại và ngay trên giới hạn.
- **Bảng quyết định:** liệt kê tổ hợp điều kiện và kết quả khi nhiều quy tắc tương tác.
- **Kiểm thử chuyển trạng thái:** kiểm tra hành vi khi đối tượng đi từ trạng thái này sang trạng thái khác.
- **Kiểm thử theo cặp hoặc tổ hợp:** chọn tổ hợp cấu hình có khả năng gây lỗi mà không cần thử mọi tổ hợp có thể.
- **Kiểm thử dựa trên thuộc tính:** xác minh quy tắc tổng quát trên nhiều dữ liệu được sinh ra.

Không phải chức năng nào cũng cần mọi kỹ thuật. Hãy chọn kỹ thuật theo số lượng điều kiện, tính phức tạp và hậu quả của lỗi.

### Xem xét cả hành vi bình thường và bất thường

Với mỗi chức năng quan trọng, cần cân nhắc các nhóm tình huống sau:

| Nhóm tình huống | Điều cần xác minh |
|---|---|
| Luồng bình thường | Đầu vào hợp lệ tạo ra kết quả đúng và trạng thái được cập nhật như mong đợi |
| Đầu vào không hợp lệ | Hệ thống từ chối dữ liệu sai và cung cấp phản hồi phù hợp |
| Giá trị biên | Các giới hạn số lượng, độ dài, thời gian, dung lượng hoặc mức tiền được xử lý đúng |
| Quyền và vai trò | Người dùng chỉ thực hiện được thao tác được phép |
| Trạng thái không phù hợp | Thao tác bị từ chối hoặc xử lý có kiểm soát khi đối tượng ở trạng thái không cho phép |
| Lỗi phụ thuộc | Hệ thống xử lý khi dịch vụ, cơ sở dữ liệu hoặc mạng gặp sự cố |
| Gửi lặp hoặc đồng thời | Hệ thống không tạo dữ liệu trùng hoặc trạng thái mâu thuẫn |
| Khả năng phục hồi | Có thể tiếp tục, thử lại hoặc hoàn tác theo quy tắc sau khi lỗi xảy ra |

Ví dụ, chức năng tạo đơn hàng cần kiểm tra dữ liệu hợp lệ, sản phẩm hết hàng, địa chỉ không hợp lệ, giỏ hàng thay đổi trong lúc xác nhận, yêu cầu gửi lặp và lỗi khi dịch vụ thanh toán không phản hồi. Những trường hợp này giúp đánh giá hành vi trong điều kiện gần với thực tế.

## 3. Lựa chọn luồng nghiệp vụ cần kiểm tra

Luồng nghiệp vụ mô tả một chuỗi hoạt động phối hợp để đạt mục tiêu. Luồng có thể đi qua nhiều màn hình, dịch vụ, cơ sở dữ liệu, người dùng hoặc hệ thống bên ngoài. Lỗi thường xuất hiện tại điểm chuyển tiếp: dữ liệu không được truyền đúng, trạng thái cập nhật không đồng bộ hoặc một bước thất bại khiến các bước sau xử lý sai.

### Ưu tiên theo mục tiêu và hậu quả

Một luồng nghiệp vụ nên được ưu tiên khi:

- Đại diện cho mục tiêu cốt lõi của người dùng hoặc hoạt động kinh doanh.
- Có tần suất sử dụng cao hoặc phục vụ lượng lớn người dùng.
- Liên quan đến giao dịch, dữ liệu quan trọng, quyền truy cập hoặc nghĩa vụ pháp lý.
- Đi qua nhiều thành phần hoặc phụ thuộc bên ngoài.
- Có nhiều nhánh, trạng thái và tình huống lỗi.
- Từng gây sự cố hoặc có thay đổi tác động rộng.
- Khi bị gián đoạn sẽ gây tổn thất đáng kể hoặc khó khôi phục.

Không nên chỉ chọn luồng dựa trên số lần người dùng thực hiện. Một luồng khôi phục tài khoản có thể ít xảy ra nhưng có ảnh hưởng lớn đến khả năng truy cập. Một luồng hoàn tiền có tần suất thấp nhưng liên quan trực tiếp đến tiền và đối soát.

### Kiểm tra điểm nối giữa các bước

Với từng luồng, hãy xác định:

1. Điều kiện để bắt đầu và vai trò tham gia.
2. Dữ liệu được tạo hoặc sử dụng ở mỗi bước.
3. Trạng thái trước và sau từng thao tác.
4. Thành phần chịu trách nhiệm và giao tiếp giữa chúng.
5. Những điểm có thể thất bại, bị lặp hoặc đến sai thứ tự.
6. Cách hệ thống tiếp tục, hoàn tác hoặc phục hồi.
7. Bằng chứng để xác nhận toàn bộ mục tiêu đã hoàn tất.

Đặc biệt chú ý đến tính nhất quán giữa các bước. Nếu một đơn hàng đã thanh toán nhưng trạng thái vẫn là chờ thanh toán, hệ thống có thể gây giao dịch trùng khi người dùng thử lại. Nếu một yêu cầu hoàn tiền đã được gửi nhưng kết quả không được ghi nhận, nhân viên hỗ trợ có thể xử lý lặp.

### Bao phủ luồng chính và các nhánh quan trọng

Không cần kiểm tra mọi tổ hợp đường đi trong một luồng dài. Hãy xác định đường đi chính và những nhánh có rủi ro cao:

- Nhánh thành công hoàn chỉnh.
- Nhánh bị từ chối do điều kiện nghiệp vụ.
- Nhánh lỗi tại một bước trung gian.
- Nhánh người dùng hủy hoặc quay lại.
- Nhánh phụ thuộc phản hồi chậm hoặc mất kết nối.
- Nhánh gửi lặp, xử lý đồng thời hoặc nhận thông báo trễ.
- Nhánh phục hồi sau khi sự cố được giải quyết.

Ví dụ, với luồng đặt hàng và thanh toán, đường đi chính là chọn sản phẩm, xác nhận giỏ hàng, tạo đơn, thanh toán thành công và nhận xác nhận. Những nhánh cần chú ý có thể là thanh toán bị từ chối, cổng thanh toán hết thời gian chờ, phản hồi đến muộn, người dùng nhấn nút nhiều lần, tồn kho thay đổi hoặc hệ thống nhận cùng một thông báo thanh toán nhiều lần.

### Ví dụ sơ đồ luồng đặt hàng

~~~mermaid
flowchart TD
    A[Bắt đầu đặt hàng] --> B[Kiểm tra giỏ hàng và tồn kho]
    B --> C{Dữ liệu hợp lệ?}
    C -- Không --> D[Thông báo và yêu cầu điều chỉnh]
    C -- Có --> E[Tạo đơn ở trạng thái chờ thanh toán]
    E --> F[Gửi yêu cầu thanh toán]
    F --> G{Kết quả thanh toán}
    G -- Thành công --> H[Ghi nhận giao dịch và xác nhận đơn]
    G -- Bị từ chối --> I[Thông báo thất bại]
    G -- Không rõ hoặc hết thời gian --> J[Đối soát trạng thái giao dịch]
    J --> H
    J --> I
    H --> K[Hoàn tất]
    I --> L[Cho phép thử lại theo quy tắc]
~~~

Sơ đồ chỉ minh họa các điểm cần xem xét. Cách xử lý khi không rõ kết quả thanh toán phải tuân theo thiết kế thực tế, chẳng hạn truy vấn trạng thái giao dịch hoặc đối soát qua thông báo từ nhà cung cấp. Không nên mặc định gửi lại yêu cầu thanh toán ngay vì có thể tạo giao dịch trùng.

## 4. Lựa chọn thuộc tính chất lượng cần kiểm tra

Thuộc tính chất lượng mô tả mức độ tốt của hệ thống khi thực hiện chức năng. Một chức năng có thể cho kết quả đúng nhưng vẫn không đáp ứng nhu cầu nếu phản hồi quá chậm, không bảo vệ dữ liệu hoặc thường xuyên gián đoạn.

Nhóm cần chọn thuộc tính chất lượng dựa trên loại sản phẩm, bối cảnh sử dụng, kỳ vọng của người dùng, kiến trúc và hậu quả của lỗi. Không phải thuộc tính nào cũng cần cùng mức độ kiểm thử cho mọi tính năng.

### Các thuộc tính chất lượng phổ biến

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ kiểm tra |
|---|---|---|
| Hiệu năng | Hệ thống phản hồi nhanh đến mức nào dưới tải dự kiến? | Đo thời gian phản hồi, thông lượng và tài nguyên |
| Khả năng mở rộng | Hệ thống xử lý tải tăng mà vẫn đáp ứng mục tiêu không? | Tăng dần số người dùng hoặc yêu cầu đồng thời |
| Độ tin cậy | Hệ thống hoạt động ổn định trong khoảng thời gian và điều kiện mong đợi không? | Chạy kéo dài, theo dõi lỗi và tính sẵn sàng |
| Khả năng phục hồi | Hệ thống có thể tiếp tục hoặc khôi phục sau sự cố không? | Ngắt phụ thuộc, khởi động lại, kiểm tra phục hồi dữ liệu |
| Bảo mật | Hệ thống có ngăn truy cập và thao tác trái phép không? | Kiểm tra xác thực, phân quyền, đầu vào và cấu hình |
| Quyền riêng tư | Dữ liệu cá nhân được thu thập, sử dụng và bảo vệ đúng cách không? | Kiểm tra quyền truy cập, lưu trữ và hiển thị dữ liệu |
| Tính dễ sử dụng | Người dùng có thể hoàn thành công việc dễ hiểu và ít nhầm lẫn không? | Quan sát nhiệm vụ, phản hồi và lỗi thao tác |
| Khả năng tiếp cận | Người dùng có nhu cầu khác nhau có thể sử dụng sản phẩm không? | Kiểm tra bàn phím, trình đọc màn hình, tương phản |
| Tương thích | Sản phẩm hoạt động đúng trên nền tảng được hỗ trợ không? | Kiểm tra trình duyệt, thiết bị, hệ điều hành và phiên bản |
| Toàn vẹn dữ liệu | Dữ liệu có chính xác và nhất quán qua các thao tác không? | Kiểm tra ràng buộc, đồng bộ, giao dịch và khôi phục |
| Khả năng bảo trì | Hệ thống có thể thay đổi và sửa lỗi mà không tạo rủi ro quá lớn không? | Kiểm tra cấu trúc, độ phức tạp và khả năng kiểm thử |
| Khả năng quan sát | Nhóm có thể phát hiện và điều tra vấn đề trong vận hành không? | Kiểm tra log, metric, trace và cảnh báo |

Các thuộc tính có thể xung đột. Tăng mức mã hóa hoặc kiểm tra bảo mật có thể ảnh hưởng đến hiệu năng; lưu log chi tiết có thể hỗ trợ điều tra nhưng tạo rủi ro quyền riêng tư; tối ưu chi phí có thể ảnh hưởng đến khả năng dự phòng. Chiến lược cần nêu rõ mục tiêu và giới hạn chấp nhận để nhóm đánh giá các đánh đổi này.

### Chuyển thuộc tính chất lượng thành tiêu chí kiểm chứng

Các cụm từ như “nhanh”, “an toàn”, “ổn định” hoặc “dễ dùng” quá chung chung để làm tiêu chí kiểm thử. Cần chuyển chúng thành điều kiện quan sát hoặc đo lường.

Ví dụ:

- Thay vì “trang tìm kiếm phải nhanh”, xác định thời gian phản hồi mục tiêu ở phân vị phù hợp, dưới số yêu cầu đồng thời và bộ dữ liệu cụ thể.
- Thay vì “chỉ người có quyền mới được xem đơn”, xác định vai trò nào được xem đơn của ai và kiểm tra cả truy cập trực tiếp qua API.
- Thay vì “hệ thống phải phục hồi tốt”, xác định loại sự cố, thời gian phục hồi mong đợi và mức mất dữ liệu có thể chấp nhận.
- Thay vì “giao diện dễ sử dụng”, xác định nhiệm vụ người dùng cần hoàn thành, tiêu chí thành công và những rào cản cần quan sát.
- Thay vì “dữ liệu luôn chính xác”, xác định các bất biến nghiệp vụ phải giữ sau thao tác, lỗi và xử lý đồng thời.

Tiêu chí nên nêu rõ đối tượng, điều kiện, phép đo và ngưỡng chấp nhận. Khi chưa thể xác định ngưỡng, hãy ghi rõ giả định và người cần thống nhất, tránh tự đặt con số không có cơ sở.

## 5. Dùng rủi ro để cân bằng ba góc nhìn

Danh sách chức năng, luồng và thuộc tính chất lượng có thể rất dài. Để chọn phạm vi khả thi, nhóm cần đánh giá rủi ro của từng mục và ưu tiên theo hậu quả nếu kiểm thử bỏ sót.

Một cách đơn giản là xem xét:

- **Tác động:** nếu xảy ra lỗi, ảnh hưởng đến người dùng, dữ liệu, tiền, bảo mật hoặc hoạt động kinh doanh lớn đến đâu?
- **Khả năng xảy ra:** hành vi có phức tạp, thường xuyên thay đổi, có nhiều phụ thuộc hoặc từng phát sinh lỗi không?
- **Khả năng phát hiện:** nếu lỗi xuất hiện, hệ thống hoặc nhóm có nhận ra nhanh không?
- **Khả năng phục hồi:** có thể quay lui, khôi phục dữ liệu hoặc xử lý thủ công an toàn không?
- **Mức độ phơi nhiễm:** bao nhiêu người dùng, giao dịch hoặc thành phần chịu ảnh hưởng?

Có thể dùng ma trận định tính để bắt đầu:

| Tác động | Khả năng xảy ra | Ưu tiên gợi ý |
|---|---|---|
| Cao | Cao | Rất cao |
| Cao | Thấp | Cao, đặc biệt nếu khó phát hiện hoặc khó phục hồi |
| Trung bình | Cao | Trung bình đến cao tùy mức phơi nhiễm |
| Thấp | Thấp | Thấp, có thể lấy mẫu hoặc kiểm tra ở mức cơ bản |

Đây là công cụ hỗ trợ thảo luận, không phải phép tính chính xác. Một rủi ro hiếm nhưng gây lộ dữ liệu hoặc mất tiền vẫn có thể cần kiểm tra sâu. Cũng cần xem xét rủi ro kết hợp: nhiều lỗi nhỏ ở các bước khác nhau có thể tạo thành hậu quả lớn khi cả luồng được thực hiện.

### Ví dụ bảng ưu tiên phạm vi

| Hạng mục | Loại | Rủi ro chính | Mức kiểm tra đề xuất |
|---|---|---|---|
| Tính tổng tiền đơn hàng | Chức năng | Tính sai tiền hoặc áp dụng ưu đãi sai | Kiểm thử quy tắc, giá trị biên và hồi quy |
| Đặt hàng và thanh toán | Luồng nghiệp vụ | Giao dịch trùng, mất trạng thái hoặc không đối soát được | Kiểm thử tích hợp và đầu cuối, gồm nhánh lỗi và gửi lặp |
| Phân quyền xem đơn | Chức năng và bảo mật | Người dùng xem dữ liệu của người khác | Kiểm thử quyền ở giao diện và API, gồm truy cập trái phép |
| Tìm kiếm sản phẩm | Chức năng và hiệu năng | Kết quả sai hoặc phản hồi chậm khi tải tăng | Kiểm thử chức năng, dữ liệu và tải theo mục tiêu |
| Hiển thị biểu tượng phụ | Giao diện | Sai lệch nhỏ, dễ nhận biết | Kiểm tra giao diện ở một số cấu hình đại diện |

Mức kiểm tra trong bảng chỉ mang tính minh họa. Nhóm cần điều chỉnh dựa trên dữ liệu thực tế, yêu cầu sản phẩm và các cam kết chất lượng.

## 6. Xác định phạm vi trong một bản phát hành

Phạm vi chiến lược có thể bao phủ toàn bộ sản phẩm, nhưng mỗi bản phát hành cần lựa chọn phần kiểm thử cụ thể. Để làm điều đó, hãy kết hợp thay đổi mới với tác động đến những khu vực hiện có.

### Phân tích thay đổi và ảnh hưởng dây chuyền

Với mỗi thay đổi, xác định:

- Chức năng hoặc quy tắc nào được thêm, sửa hoặc loại bỏ?
- API, cấu trúc dữ liệu, sự kiện hoặc hợp đồng nào thay đổi?
- Những luồng nghiệp vụ nào đi qua thành phần đó?
- Vai trò, quyền, cấu hình và nền tảng nào bị ảnh hưởng?
- Những kiểm thử hiện có nào cần cập nhật?
- Có rủi ro hồi quy ở khu vực không thay đổi trực tiếp không?

Ví dụ, thay đổi công thức tính phí vận chuyển có thể ảnh hưởng đến trang giỏ hàng, tổng tiền đơn, thanh toán, hóa đơn, báo cáo doanh thu và hoàn tiền. Chỉ kiểm tra màn hình hiển thị phí mới sẽ không đủ để phát hiện sai lệch ở các bước sau.

Có thể dùng sơ đồ phụ thuộc, tìm kiếm tham chiếu mã nguồn, hợp đồng API và trao đổi với người sở hữu thành phần để xác định phạm vi ảnh hưởng. Nếu chưa biết đầy đủ tác động, hãy ghi nhận vùng chưa chắc chắn và tăng kiểm tra thăm dò hoặc hồi quy có trọng điểm.

### Phân biệt phạm vi kiểm thử và phần chưa kiểm tra

Một mô tả phạm vi nên nêu:

- Những chức năng và hành trình nằm trong phạm vi.
- Những thuộc tính chất lượng sẽ được đánh giá.
- Cấp độ kiểm thử và môi trường dự kiến.
- Nền tảng, cấu hình và dữ liệu đại diện.
- Những phần bị loại khỏi phạm vi hoặc chỉ kiểm tra ở mức giới hạn.
- Lý do loại trừ và rủi ro còn lại.
- Điều kiện khiến phạm vi cần được mở rộng.

Việc ghi rõ phần chưa kiểm tra giúp người ra quyết định hiểu giới hạn bằng chứng. Không nên ngầm hiểu rằng một phần không xuất hiện trong báo cáo nghĩa là phần đó đã được kiểm tra và đạt.

## 7. Liên kết yêu cầu, rủi ro và bằng chứng kiểm thử

Khi phạm vi có nhiều chức năng và luồng, nhóm cần cách truy vết để biết mỗi rủi ro được kiểm tra ở đâu và còn khoảng trống nào.

Có thể tạo ma trận truy vết đơn giản:

| Yêu cầu hoặc rủi ro | Chức năng | Luồng liên quan | Thuộc tính chất lượng | Bằng chứng |
|---|---|---|---|---|
| Tổng tiền phải chính xác | Tính giá và ưu đãi | Đặt hàng, hoàn tiền | Toàn vẹn dữ liệu | Kiểm thử đơn vị và tích hợp |
| Người dùng chỉ xem được đơn của mình | Xác thực và phân quyền | Tra cứu đơn | Bảo mật, quyền riêng tư | Kiểm thử API và kiểm thử bảo mật |
| Thanh toán không tạo giao dịch trùng | Gửi và ghi nhận thanh toán | Đặt hàng | Độ tin cậy, toàn vẹn dữ liệu | Kiểm thử hợp đồng, tích hợp và gửi lặp |
| Tìm kiếm đáp ứng tải dự kiến | Tìm kiếm và lọc | Khám phá sản phẩm | Hiệu năng, khả năng mở rộng | Kiểm thử chức năng và tải |

Ma trận không nhất thiết phải là tài liệu lớn hoặc công cụ riêng. Có thể quản lý bằng hệ thống theo dõi yêu cầu, công cụ quản lý kiểm thử hoặc tài liệu nhóm. Điều quan trọng là có thể trả lời:

- Rủi ro quan trọng nào chưa có kiểm thử?
- Một kiểm thử thất bại ảnh hưởng đến yêu cầu hoặc luồng nào?
- Thay đổi này cần chạy lại những kiểm thử nào?
- Bằng chứng nào hỗ trợ quyết định hoàn tất hoặc phát hành?

Cần tránh tạo liên kết hình thức. Một yêu cầu được gắn với nhiều trường hợp kiểm thử vẫn có thể chưa được bao phủ nếu các trường hợp đó không kiểm tra đúng quy tắc hoặc điều kiện rủi ro.

## 8. Chọn mức độ kiểm tra phù hợp

Không phải mọi hạng mục trong phạm vi đều cần kiểm tra ở tất cả cấp độ. Hãy chọn nơi có thể phát hiện loại lỗi cần quan tâm với tốc độ và chi phí hợp lý.

- **Kiểm thử đơn vị** phù hợp với quy tắc tính toán, điều kiện và logic có thể cô lập.
- **Kiểm thử thành phần** phù hợp với hành vi của một thành phần cùng các phụ thuộc được kiểm soát.
- **Kiểm thử hợp đồng** phù hợp với cấu trúc và kỳ vọng giao tiếp giữa các dịch vụ.
- **Kiểm thử tích hợp** phù hợp với luồng dữ liệu và phối hợp giữa các thành phần thật.
- **Kiểm thử hệ thống hoặc đầu cuối** phù hợp với hành trình xuyên suốt và hành vi tổng thể.
- **Kiểm thử chấp nhận** phù hợp để xác nhận sản phẩm đáp ứng nhu cầu và điều kiện nghiệp vụ.
- **Kiểm thử phi chức năng chuyên biệt** phù hợp với mục tiêu hiệu năng, bảo mật, khả năng phục hồi hoặc khả năng tiếp cận.

Ví dụ, quy tắc tính giảm giá nên được kiểm tra sâu ở cấp độ đơn vị với các tổ hợp điều kiện. Tích hợp giữa giỏ hàng và dịch vụ khuyến mãi cần kiểm tra hợp đồng hoặc tích hợp. Hành trình đặt hàng hoàn chỉnh cần một số kiểm thử đầu cuối đại diện. Kiểm thử hiệu năng nên tập trung vào điểm nóng như tìm kiếm hoặc xác nhận đơn thay vì chạy tải lớn trên mọi chức năng.

Một chiến lược tốt chọn đúng cấp độ cho từng rủi ro. Nếu mọi kiểm tra đều dồn lên tầng đầu cuối, phản hồi thường chậm và khó khoanh vùng lỗi. Nếu chỉ kiểm tra đơn vị, các vấn đề về tích hợp, cấu hình và hành trình người dùng có thể bị bỏ sót.

## 9. Cân nhắc nguồn lực và giới hạn thực tế

Phạm vi cần đủ để kiểm soát rủi ro nhưng vẫn có thể thực hiện trong thời gian và nguồn lực hiện có. Khi không thể kiểm tra mọi thứ, hãy ưu tiên dựa trên hậu quả và ghi nhận giới hạn.

Những yếu tố cần cân nhắc gồm:

- Thời gian dành cho kiểm thử trước mốc phát hành.
- Số lượng và kỹ năng của thành viên.
- Khả năng sẵn sàng của môi trường và dữ liệu.
- Thời gian chạy, độ ổn định và chi phí bảo trì của bộ kiểm thử.
- Mức độ sẵn sàng của dịch vụ phụ thuộc hoặc thiết bị.
- Khả năng tái tạo sự cố và thu thập bằng chứng.
- Yêu cầu kiểm tra độc lập hoặc chuyên môn đặc thù.

Có thể chia phạm vi thành các nhóm ưu tiên:

- **Bắt buộc:** rủi ro nghiêm trọng, yêu cầu bắt buộc, luồng cốt lõi và điều kiện phát hành.
- **Ưu tiên cao:** khu vực thay đổi lớn, có lịch sử lỗi hoặc ảnh hưởng đáng kể đến người dùng.
- **Ưu tiên tiếp theo:** chức năng ít rủi ro hơn, cấu hình ít phổ biến hoặc tình huống có thể lấy mẫu.
- **Theo dõi hoặc trì hoãn có kiểm soát:** phần chưa kiểm tra sâu, kèm lý do, rủi ro còn lại và kế hoạch xem xét.

Phân nhóm này cần được thống nhất với người có trách nhiệm về sản phẩm và phát hành. Không nên âm thầm bỏ kiểm thử bắt buộc hoặc hạ mức kiểm tra chỉ để đạt thời hạn.

## 10. Ví dụ tổng hợp: chọn phạm vi cho tính năng đặt lịch

Giả sử một ứng dụng cho phép khách hàng đặt lịch dịch vụ. Khách hàng chọn dịch vụ, địa điểm, nhân viên và khung giờ; hệ thống kiểm tra khả năng phục vụ, giữ chỗ và gửi xác nhận.

Nhóm có thể phân tích như sau:

### Chức năng cần kiểm tra

- Tìm dịch vụ và địa điểm.
- Hiển thị khung giờ còn trống.
- Kiểm tra điều kiện đặt lịch.
- Tạo, sửa và hủy lịch.
- Gửi thông báo xác nhận hoặc thay đổi.
- Quản lý quyền của khách hàng và nhân viên.

Với từng chức năng, cần kiểm tra dữ liệu hợp lệ, không hợp lệ, giới hạn thời gian, trạng thái lịch và quyền thao tác.

### Luồng nghiệp vụ cần kiểm tra

- Đặt lịch thành công từ lúc tìm dịch vụ đến khi nhận xác nhận.
- Hai khách hàng cùng chọn một khung giờ.
- Khách hàng sửa hoặc hủy lịch theo chính sách.
- Nhân viên thay đổi lịch và khách hàng nhận thông báo.
- Dịch vụ gửi thông báo tạm thời không khả dụng.
- Yêu cầu tạo lịch bị gửi lặp hoặc phản hồi đến muộn.

Những luồng đồng thời và gửi lặp cần chú ý vì có thể tạo hai lịch cho cùng một nguồn lực.

### Thuộc tính chất lượng cần kiểm tra

| Thuộc tính | Mối quan tâm | Hướng kiểm chứng |
|---|---|---|
| Toàn vẹn dữ liệu | Không có hai lịch hợp lệ chiếm cùng một nguồn lực và khung giờ | Kiểm thử đồng thời, ràng buộc và giao dịch |
| Hiệu năng | Tìm kiếm lịch trống phản hồi phù hợp khi nhiều người dùng truy cập | Kiểm thử tải với dữ liệu và mô hình truy cập đại diện |
| Bảo mật | Khách hàng không xem hoặc sửa lịch của người khác | Kiểm thử xác thực và phân quyền ở API |
| Độ tin cậy | Lịch đã tạo không bị mất khi dịch vụ thông báo gặp lỗi | Kiểm thử lỗi phụ thuộc và cơ chế gửi lại |
| Khả năng sử dụng | Người dùng hiểu rõ múi giờ, thời lượng và trạng thái đặt lịch | Đánh giá hành trình và nội dung giao diện |
| Khả năng tiếp cận | Các thao tác chọn dịch vụ và khung giờ dùng được bằng bàn phím và công nghệ hỗ trợ | Kiểm thử khả năng tiếp cận |

### Ưu tiên theo rủi ro

Rủi ro cao nhất có thể là đặt trùng lịch, vì nó ảnh hưởng trực tiếp đến khách hàng và hoạt động phục vụ. Do đó, nhóm cần kiểm tra kỹ quy tắc giữ chỗ, xử lý đồng thời, gửi lặp và phục hồi. Hiệu năng tìm kiếm cũng quan trọng nếu lượng truy cập cao. Một số chi tiết trình bày ít ảnh hưởng có thể được kiểm tra ở mức đại diện.

Ví dụ này cho thấy phạm vi cần xuất phát từ mục tiêu nghiệp vụ và hậu quả, sau đó chọn chức năng, luồng và thuộc tính chất lượng tương ứng. Một bộ kiểm thử chỉ xác nhận màn hình tạo lịch hiển thị thành công sẽ chưa chứng minh rằng hệ thống ngăn được đặt trùng hoặc xử lý đúng khi dịch vụ thông báo gặp sự cố.

## 11. Những sai lầm thường gặp khi lựa chọn phạm vi

- **Chỉ dựa trên danh sách chức năng:** bỏ qua tương tác giữa các chức năng và các điểm nối trong luồng.
- **Chỉ kiểm tra luồng thành công:** không xem xét từ chối, hủy, gửi lặp, lỗi phụ thuộc và phục hồi.
- **Bỏ qua thuộc tính chất lượng:** chức năng đúng vẫn có thể không đáp ứng nhu cầu nếu chậm, không an toàn hoặc khó sử dụng.
- **Ưu tiên theo tần suất sử dụng đơn thuần:** các chức năng ít dùng nhưng có hậu quả nghiêm trọng vẫn cần kiểm tra.
- **Kiểm tra quá rộng mà không có trọng tâm:** tiêu tốn nguồn lực cho nhiều trường hợp ít giá trị trong khi rủi ro cao chưa được xử lý.
- **Không phân tích tác động của thay đổi:** kiểm tra phần vừa sửa nhưng bỏ qua các luồng và thành phần phụ thuộc.
- **Dùng tiêu chí mơ hồ:** các yêu cầu như “nhanh” hoặc “ổn định” không thể xác minh nếu thiếu điều kiện và ngưỡng.
- **Không ghi nhận phần bị loại trừ:** người ra quyết định có thể hiểu nhầm rằng mọi phần đều đã được kiểm tra.
- **Nhầm độ bao phủ với chất lượng:** có trường hợp kiểm thử cho mọi yêu cầu không có nghĩa các trường hợp đó đủ sâu hoặc có giá trị.
- **Không cập nhật phạm vi:** rủi ro, kiến trúc và hành vi sản phẩm thay đổi nhưng bộ kiểm thử vẫn theo giả định cũ.

Khi phát hiện một khoảng trống, hãy tìm nguyên nhân trước khi thêm hàng loạt trường hợp kiểm thử. Có thể vấn đề nằm ở yêu cầu chưa rõ, quy tắc nghiệp vụ chưa thống nhất, kiến trúc khó kiểm thử, dữ liệu thiếu hoặc tiêu chí chất lượng chưa được xác định.

## 12. Mẫu mô tả phạm vi kiểm thử

Một mô tả phạm vi có thể dùng cấu trúc ngắn gọn sau:

| Hạng mục | Nội dung cần ghi |
|---|---|
| Sản phẩm hoặc bản phát hành | Phần sản phẩm, phiên bản và thay đổi đang được đánh giá |
| Mục tiêu | Người dùng hoặc kết quả nghiệp vụ cần bảo vệ |
| Chức năng trong phạm vi | Các chức năng, quy tắc và trạng thái cần kiểm tra |
| Luồng nghiệp vụ | Hành trình chính và các nhánh rủi ro cao |
| Thuộc tính chất lượng | Các thuộc tính được đánh giá và tiêu chí đo lường |
| Rủi ro ưu tiên | Hậu quả, khả năng xảy ra, khả năng phát hiện và phục hồi |
| Cấp độ kiểm thử | Đơn vị, thành phần, hợp đồng, tích hợp, hệ thống hoặc chấp nhận |
| Môi trường và dữ liệu | Cấu hình, nền tảng và dữ liệu đại diện |
| Ngoài phạm vi | Phần chưa kiểm tra sâu, lý do và rủi ro còn lại |
| Điều kiện hoàn tất | Bằng chứng cần có và người chấp nhận rủi ro còn lại |

Mẫu này có thể được điều chỉnh theo quy mô dự án. Với thay đổi nhỏ, một mô tả ngắn trong yêu cầu hoặc pull request có thể đủ. Với hệ thống có rủi ro cao, phạm vi cần được ghi nhận chi tiết và có sự thống nhất của các bên liên quan.

## Kết luận

Lựa chọn phạm vi kiểm thử đòi hỏi nhóm hiểu chức năng, hành trình nghiệp vụ và thuộc tính chất lượng trong cùng một bức tranh. Chức năng cho biết hệ thống phải làm gì; luồng nghiệp vụ cho biết nhiều chức năng phối hợp để tạo ra kết quả như thế nào; thuộc tính chất lượng cho biết kết quả đó cần đạt mức độ hiệu năng, an toàn, tin cậy và dễ sử dụng ra sao.

Khi ưu tiên theo rủi ro, phân tích tác động của thay đổi và liên kết yêu cầu với bằng chứng kiểm thử, nhóm có thể tập trung vào những phần quan trọng nhất mà vẫn minh bạch về giới hạn. Phạm vi cần được xem xét lại khi sản phẩm, kiến trúc, người dùng hoặc điều kiện vận hành thay đổi, để hoạt động kiểm thử tiếp tục bảo vệ đúng những mục tiêu mà sản phẩm cần đạt.
