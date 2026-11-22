# Chiến lược kiểm thử là gì và những quyết định cần định hướng

Chiến lược kiểm thử là định hướng chung về cách một nhóm thu thập bằng chứng để đánh giá chất lượng sản phẩm và kiểm soát rủi ro trước, trong và sau khi phát hành. Chiến lược xác định điều gì cần được kiểm chứng, vì sao cần kiểm chứng, mức độ kiểm chứng phù hợp, cách thực hiện và cách dùng kết quả để đưa ra quyết định.

Một chiến lược tốt giúp nhóm tập trung thời gian vào những rủi ro có ảnh hưởng lớn nhất. Nó cũng tạo ra cách hiểu thống nhất giữa phát triển, kiểm thử, sản phẩm và vận hành về chất lượng mong đợi, trách nhiệm của từng bên và điều kiện để phát hành.

Chiến lược không phải danh sách test case cố định. Nó là tập hợp các lựa chọn và nguyên tắc định hướng; kế hoạch kiểm thử, bộ kiểm thử và lịch chạy kiểm thử được xây dựng dựa trên định hướng đó và có thể thay đổi theo từng tính năng hoặc bản phát hành.

## Vì sao cần có chiến lược kiểm thử?

Một sản phẩm có thể có hàng nghìn hành vi, nhiều cấu hình triển khai và nhiều cách người dùng tương tác. Thời gian, nhân lực và môi trường kiểm thử luôn hữu hạn, nên nhóm không thể kiểm tra mọi khả năng với cùng độ sâu.

Nếu thiếu định hướng chung, nhóm dễ gặp các vấn đề như:

- Tập trung quá nhiều vào các luồng dễ kiểm tra, trong khi luồng có tác động lớn đến người dùng hoặc dữ liệu lại ít được kiểm chứng.
- Các nhóm kiểm tra trùng lặp một phần nhưng vẫn bỏ sót ranh giới giữa những thành phần hoặc dịch vụ.
- Kiểm thử chỉ bắt đầu khi tính năng gần hoàn tất, khiến lỗi thiết kế và yêu cầu khó sửa trở nên tốn kém.
- Tự động hóa được nhiều bước nhưng bộ kiểm thử chậm, khó bảo trì hoặc thường xuyên báo lỗi không ổn định.
- Không thống nhất được mức độ lỗi nào có thể chấp nhận, ai có quyền quyết định và cần bằng chứng gì trước khi phát hành.

Chiến lược giải quyết những vấn đề này bằng cách làm rõ ưu tiên, phạm vi, phương pháp, trách nhiệm và tiêu chí ra quyết định. Nó không bảo đảm sản phẩm không còn lỗi; nó giúp nhóm nhận diện rủi ro sớm hơn và đưa ra quyết định dựa trên bằng chứng rõ ràng hơn.

## Phân biệt chiến lược, kế hoạch và trường hợp kiểm thử

Ba khái niệm này liên quan với nhau nhưng phục vụ những mục đích khác nhau.

| Thành phần | Câu hỏi chính | Nội dung thường có |
|---|---|---|
| Chiến lược kiểm thử | Nhóm sẽ tiếp cận chất lượng và rủi ro theo định hướng nào? | Mục tiêu chất lượng, nguyên tắc ưu tiên, phạm vi, cấp độ và loại kiểm thử, cách tự động hóa, trách nhiệm và tiêu chí quyết định |
| Kế hoạch kiểm thử | Với phạm vi cụ thể, ai sẽ làm gì, khi nào và bằng nguồn lực nào? | Phạm vi bản phát hành, lịch, nhân lực, môi trường, phụ thuộc, nhiệm vụ và mốc kiểm thử |
| Trường hợp kiểm thử | Một hành vi cụ thể được kiểm chứng như thế nào? | Điều kiện đầu vào, các bước thực hiện, kết quả mong đợi và dữ liệu cần thiết |

Ví dụ, chiến lược có thể quy định rằng các luồng thanh toán và ghi nhận giao dịch là rủi ro cao, cần được kiểm tra ở nhiều cấp độ và có kiểm thử tự động trong quy trình tích hợp liên tục. Kế hoạch của một bản phát hành sẽ xác định những thay đổi thanh toán nào cần kiểm tra, môi trường nào được dùng và ai phụ trách. Các trường hợp kiểm thử mô tả những tình huống cụ thể như thanh toán thành công, thẻ bị từ chối, yêu cầu gửi lặp hoặc kết nối bị gián đoạn.

## Bắt đầu từ bối cảnh và rủi ro

Không có một chiến lược phù hợp cho mọi sản phẩm. Trước khi chọn kỹ thuật hoặc công cụ, nhóm cần hiểu sản phẩm được dùng trong hoàn cảnh nào và điều gì có thể xảy ra nếu hệ thống hoạt động sai.

Những thông tin cần xem xét gồm:

- Người dùng, mục đích sử dụng và những hành trình quan trọng.
- Kiến trúc, các thành phần, dịch vụ bên ngoài, luồng dữ liệu và điểm tích hợp.
- Những thay đổi gần đây, phần mã phức tạp, khu vực thường phát sinh lỗi và các sự cố đã biết.
- Tác động của lỗi đến người dùng, doanh thu, dữ liệu, hoạt động vận hành, uy tín hoặc nghĩa vụ pháp lý.
- Môi trường triển khai, nền tảng và cấu hình mà sản phẩm cần hỗ trợ.
- Nhịp độ phát hành, khả năng quay lui, năng lực nhóm và giới hạn về thời gian hoặc hạ tầng.

Từ bối cảnh đó, nhóm xác định rủi ro. Có thể đánh giá rủi ro theo hai chiều: khả năng xảy ra và mức độ tác động nếu xảy ra. Đây là cách hỗ trợ thảo luận và ưu tiên, không phải phép đo chính xác tuyệt đối.

Ví dụ:

| Tình huống | Khả năng hoặc tác động cần cân nhắc | Hướng ưu tiên |
|---|---|---|
| Giao dịch bị ghi nhận hai lần | Có thể gây thiệt hại tài chính và khó đối soát | Kiểm tra xử lý yêu cầu lặp, tính nhất quán dữ liệu và khả năng phục hồi |
| Trang giới thiệu hiển thị sai khoảng cách nhỏ | Ảnh hưởng chủ yếu đến trình bày | Kiểm tra giao diện và khả năng hiển thị ở các kích thước phổ biến |
| Người dùng có thể xem dữ liệu của tài khoản khác | Ảnh hưởng nghiêm trọng đến quyền riêng tư và bảo mật | Kiểm tra phân quyền, cách ly dữ liệu và các trường hợp truy cập trái phép |
| Dịch vụ phụ thuộc phản hồi chậm | Có thể làm gián đoạn luồng nghiệp vụ | Kiểm tra timeout, retry, xử lý lỗi và hành vi khi dịch vụ phục hồi |

Khi ưu tiên, hãy xét cả mức độ nghiêm trọng lẫn khả năng phát hiện và khắc phục. Một lỗi ít xảy ra nhưng gây mất dữ liệu không thể phục hồi vẫn có thể cần mức kiểm chứng cao. Ngược lại, một lỗi dễ phát hiện, dễ quay lui và ít ảnh hưởng có thể được xử lý với mức ưu tiên khác.

## Những quyết định chiến lược cần định hướng

### 1. Mục tiêu chất lượng nào quan trọng nhất?

Nhóm cần xác định những thuộc tính chất lượng mà sản phẩm phải đáp ứng. Tùy bối cảnh, các mục tiêu có thể bao gồm:

- **Tính đúng đắn chức năng:** hệ thống thực hiện đúng quy tắc nghiệp vụ và trả về kết quả mong đợi.
- **Độ tin cậy:** hệ thống hoạt động ổn định, xử lý lỗi có kiểm soát và phục hồi được khi có sự cố.
- **Hiệu năng và khả năng mở rộng:** thời gian phản hồi, thông lượng và mức sử dụng tài nguyên phù hợp với tải dự kiến.
- **Bảo mật và quyền riêng tư:** dữ liệu được bảo vệ, quyền truy cập được kiểm soát và các thao tác nhạy cảm được xử lý an toàn.
- **Tính dễ sử dụng và khả năng tiếp cận:** người dùng có thể hoàn thành công việc, kể cả khi sử dụng công nghệ hỗ trợ.
- **Tương thích:** sản phẩm hoạt động trên những trình duyệt, thiết bị, hệ điều hành hoặc phiên bản được hỗ trợ.
- **Toàn vẹn dữ liệu:** dữ liệu được lưu, chuyển đổi, đồng bộ và khôi phục mà không bị mất hoặc sai lệch.

Không phải dự án nào cũng cần ưu tiên mọi thuộc tính ngang nhau. Nhóm nên diễn đạt mục tiêu thành tiêu chí có thể quan sát hoặc đo lường. Chẳng hạn, thay vì nói “hệ thống phải nhanh”, hãy xác định hành trình nào cần phản hồi trong khoảng thời gian nào, dưới mức tải nào và đo ở đâu.

### 2. Kiểm thử phần nào và chấp nhận phần nào chưa kiểm thử sâu?

Phạm vi cần bao gồm các hành vi, thành phần, tích hợp, dữ liệu và nền tảng liên quan đến mục tiêu chất lượng. Nhóm cũng cần ghi rõ những phần chưa kiểm thử hoặc được kiểm thử ở mức hạn chế, kèm lý do và rủi ro còn lại.

Việc xác định phạm vi không nên chỉ dựa trên danh sách yêu cầu. Hãy xét các luồng người dùng quan trọng, thay đổi trong bản phát hành, khu vực có lịch sử lỗi, ranh giới giữa dịch vụ và các đường đi có thể làm hỏng dữ liệu hoặc quyền truy cập.

Một phạm vi rõ ràng giúp tránh hai cực đoan: kiểm tra quá rộng mà không có ưu tiên, hoặc chỉ kiểm tra phần vừa thay đổi mà bỏ qua tác động dây chuyền.

### 3. Dùng cấp độ kiểm thử nào?

Các cấp độ kiểm thử thường được phối hợp để tìm lỗi ở những phạm vi khác nhau:

- **Kiểm thử đơn vị:** kiểm tra hàm, lớp hoặc đơn vị logic nhỏ trong điều kiện được kiểm soát. Cấp độ này thường cho phản hồi nhanh và giúp khoanh vùng nguyên nhân.
- **Kiểm thử thành phần:** kiểm tra một thành phần tương đối độc lập cùng các phụ thuộc được thay thế hoặc kiểm soát.
- **Kiểm thử tích hợp:** kiểm tra cách các thành phần, dịch vụ, cơ sở dữ liệu hoặc hệ thống bên ngoài trao đổi dữ liệu và phối hợp với nhau.
- **Kiểm thử hệ thống:** kiểm tra hệ thống như một sản phẩm hoàn chỉnh trong môi trường gần với cách sử dụng thực tế.
- **Kiểm thử chấp nhận:** xác nhận sản phẩm đáp ứng nhu cầu người dùng, quy tắc nghiệp vụ và điều kiện chấp nhận đã thống nhất.

Nhóm nên chọn cấp độ phù hợp với rủi ro và kiến trúc. Một lỗi quy tắc tính toán có thể được phát hiện nhanh bằng kiểm thử đơn vị; một lỗi về định dạng thông điệp giữa hai dịch vụ cần kiểm thử hợp đồng hoặc tích hợp; một vấn đề trong hành trình hoàn chỉnh có thể cần kiểm thử hệ thống hoặc chấp nhận.

Hình kim tự tháp kiểm thử thường được dùng để nhắc nhóm duy trì nhiều kiểm thử nhanh ở tầng thấp và ít kiểm thử đầu cuối hơn ở tầng cao. Đây là nguyên tắc tham khảo, không phải tỷ lệ bắt buộc. Hệ thống phân tán, ứng dụng di động hoặc sản phẩm phụ thuộc nhiều vào tích hợp có thể cần phân bổ khác. Điều quan trọng là kiểm thử ở đúng ranh giới có thể phát hiện rủi ro với chi phí hợp lý.

### 4. Cần những loại kiểm thử và kỹ thuật nào?

Loại kiểm thử mô tả mục tiêu cần xác minh; kỹ thuật kiểm thử giúp chọn dữ liệu và tình huống để thực hiện mục tiêu đó.

Với chức năng, nhóm có thể kết hợp:

- Kiểm thử luồng bình thường để xác nhận hành vi dự kiến.
- Kiểm thử âm tính để xác nhận hệ thống từ chối hoặc xử lý an toàn đầu vào không hợp lệ.
- Phân vùng tương đương để chọn đại diện từ các nhóm đầu vào có cách xử lý tương tự.
- Phân tích giá trị biên để tập trung vào giới hạn và điểm chuyển trạng thái.
- Kiểm thử chuyển trạng thái để kiểm tra hành vi khi đối tượng thay đổi trạng thái.
- Kiểm thử dựa trên thuộc tính hoặc sinh dữ liệu để kiểm tra nhiều trường hợp theo quy tắc tổng quát.
- Kiểm thử thăm dò để người kiểm thử chủ động tìm những hành vi bất ngờ mà kịch bản định sẵn có thể bỏ sót.

Với thuộc tính phi chức năng, có thể cần kiểm thử tải, kiểm thử căng thẳng, kiểm thử độ bền, kiểm thử khả năng phục hồi, bảo mật, khả năng tiếp cận và tương thích. Mỗi loại cần mục tiêu, điều kiện và cách diễn giải kết quả riêng. Ví dụ, kiểm thử tải cần nêu rõ mô hình tải và ngưỡng chấp nhận; kiểm thử phục hồi cần xác định sự cố giả lập và hành vi mong đợi sau khi dịch vụ hoạt động trở lại.

Không cần áp dụng mọi kỹ thuật cho mọi tính năng. Hãy chọn kỹ thuật dựa trên rủi ro, đặc tính dữ liệu, độ phức tạp và loại lỗi có thể xảy ra.

### 5. Môi trường và dữ liệu kiểm thử được chuẩn bị ra sao?

Kết quả kiểm thử chỉ có ý nghĩa khi môi trường và dữ liệu đủ phù hợp với điều kiện cần đánh giá. Chiến lược nên định hướng:

- Mức độ tương đồng giữa môi trường kiểm thử và môi trường thực tế.
- Cách quản lý cấu hình, phiên bản dịch vụ và phụ thuộc bên ngoài.
- Cách tạo, làm sạch, đặt lại và chia sẻ dữ liệu kiểm thử.
- Việc dùng dữ liệu tổng hợp, dữ liệu đã ẩn danh hoặc dữ liệu được kiểm soát.
- Cách cô lập các lần chạy để kiểm thử song song không gây ảnh hưởng lẫn nhau.
- Cách giả lập dịch vụ ngoài khi cần kiểm tra lỗi, độ trễ hoặc tình huống khó tái tạo.

Dữ liệu kiểm thử cần đại diện cho những trường hợp quan trọng, bao gồm dữ liệu biên, dữ liệu không hợp lệ và dữ liệu có quan hệ giữa nhiều bản ghi. Không nên đưa dữ liệu nhạy cảm vào môi trường kiểm thử nếu chưa có biện pháp bảo vệ phù hợp. Khi dữ liệu được tạo tự động, nhóm cần bảo đảm có thể tái tạo tình huống để điều tra lỗi.

### 6. Tự động hóa đến mức nào và ở đâu?

Tự động hóa có giá trị khi giúp kiểm tra lặp lại nhanh, nhất quán và đáng tin cậy. Những kiểm thử có quy tắc rõ, chạy thường xuyên, có kết quả xác định và có chi phí thực hiện thủ công cao thường là ứng viên tốt.

Chiến lược tự động hóa cần trả lời:

- Kiểm thử nào phải chạy trên mỗi thay đổi mã nguồn?
- Kiểm thử nào chạy theo lịch, trước phát hành hoặc sau triển khai?
- Kiểm thử nào nên tự động ở cấp độ đơn vị, hợp đồng, tích hợp hay giao diện?
- Ai sở hữu mã kiểm thử, dữ liệu, môi trường và việc sửa kiểm thử lỗi thời?
- Làm thế nào để phát hiện và xử lý kiểm thử không ổn định?

Một quy trình thường dùng là chạy nhóm kiểm thử nhanh khi tạo thay đổi, chạy thêm kiểm thử tích hợp khi tạo bản dựng, rồi thực hiện các bộ kiểm thử rộng hơn trước hoặc sau phát hành. Các kiểm tra quan trọng sau triển khai có thể theo dõi hành vi thực tế với lưu lượng giới hạn hoặc theo cơ chế canary.

Không nên đo thành công bằng số lượng test case tự động. Một bộ kiểm thử lớn nhưng chậm, trùng lặp và thường xuyên thất bại giả có thể làm giảm niềm tin. Cần tính cả chi phí xây dựng, thời gian chạy, bảo trì và giá trị phát hiện lỗi. Kiểm thử thủ công, đặc biệt là kiểm thử thăm dò và đánh giá trải nghiệm, vẫn có vai trò khi cần phán đoán của con người.

### 7. Kiểm thử diễn ra vào thời điểm nào?

Chiến lược nên đưa kiểm thử vào xuyên suốt vòng đời phát triển. Nhóm có thể rà soát yêu cầu và thiết kế trước khi triển khai, bổ sung kiểm thử cùng với mã nguồn, kiểm tra khi tích hợp, xác nhận trước phát hành và theo dõi sau triển khai.

Phát hiện sớm giúp giảm chi phí sửa lỗi vì nhóm còn nhớ bối cảnh và có thể điều chỉnh thiết kế trước khi nhiều thành phần phụ thuộc vào nó. Việc kiểm thử sau triển khai cũng quan trọng vì môi trường thực tế có cấu hình, dữ liệu, tải và phụ thuộc mà môi trường trước phát hành khó mô phỏng hoàn toàn.

Chiến lược cần định hướng các cổng kiểm tra phù hợp, chẳng hạn kiểm tra nhanh khi hợp nhất mã, xác nhận các luồng quan trọng trước phát hành và theo dõi chỉ số sức khỏe sau triển khai. Cổng kiểm tra phải có chủ sở hữu và cách xử lý khi thất bại rõ ràng.

### 8. Điều kiện bắt đầu, hoàn tất và quyết định phát hành là gì?

Tiêu chí bắt đầu giúp tránh chạy kiểm thử khi chưa có điều kiện tối thiểu, ví dụ bản dựng chưa sẵn sàng, môi trường chưa ổn định hoặc dữ liệu cần thiết chưa được chuẩn bị.

Tiêu chí hoàn tất có thể xét:

- Những luồng và rủi ro ưu tiên đã được kiểm tra.
- Các kiểm thử bắt buộc đã chạy và có kết quả có thể giải thích.
- Lỗi nghiêm trọng đã được xử lý hoặc có quyết định chấp nhận rủi ro được ghi nhận.
- Những giới hạn kiểm thử và rủi ro còn lại đã được thông báo cho người ra quyết định.
- Các kiểm tra vận hành cần thiết như giám sát, sao lưu hoặc khả năng quay lui đã sẵn sàng.

Không nên dùng một tỷ lệ kiểm thử đạt đơn lẻ làm bằng chứng duy nhất để phát hành. Một bộ kiểm thử đạt 99% vẫn có thể có một lỗi nghiêm trọng ở luồng thanh toán hoặc phân quyền. Quyết định phát hành cần kết hợp mức độ ảnh hưởng, bằng chứng kiểm thử, rủi ro còn lại, khả năng phát hiện sự cố và phương án khôi phục.

### 9. Ai chịu trách nhiệm về chất lượng?

Chất lượng là trách nhiệm chung, dù từng vai trò có đóng góp khác nhau. Nhà phát triển thường xây dựng kiểm thử ở cấp độ mã và xử lý lỗi kỹ thuật; người phụ trách kiểm thử thiết kế cách kiểm chứng, điều phối kiểm thử và cung cấp đánh giá độc lập; chủ sản phẩm làm rõ nhu cầu và tiêu chí chấp nhận; nhóm vận hành quan tâm đến khả năng quan sát, triển khai và phục hồi; chuyên gia bảo mật hoặc dữ liệu tham gia khi rủi ro yêu cầu.

Chiến lược cần nêu rõ ai sở hữu bộ kiểm thử, ai xử lý lỗi, ai đánh giá rủi ro còn lại và ai đưa ra quyết định phát hành. Sự rõ ràng này giúp kết quả kiểm thử trở thành đầu vào thực tế cho quyết định của nhóm thay vì chỉ là báo cáo cuối giai đoạn.

### 10. Dùng chỉ số nào để đánh giá hiệu quả?

Chỉ số nên giúp nhóm hiểu chất lượng và cải thiện cách kiểm thử. Một số chỉ số hữu ích gồm:

- Tỷ lệ lỗi được phát hiện trước và sau khi phát hành, cùng mức độ nghiêm trọng của chúng.
- Mức bao phủ yêu cầu, rủi ro hoặc hành trình quan trọng.
- Thời gian phản hồi của bộ kiểm thử và thời gian từ khi phát hiện đến khi xử lý lỗi.
- Tỷ lệ kiểm thử không ổn định và thời gian cần để điều tra chúng.
- Số sự cố lặp lại, thời gian phục hồi và mức độ ảnh hưởng đến người dùng.

Mỗi chỉ số có giới hạn. Độ bao phủ mã nguồn cao không đồng nghĩa mọi hành vi quan trọng đã được kiểm tra. Tỷ lệ kiểm thử đạt cao không chứng minh sản phẩm không có lỗi. Số lỗi phát hiện tăng có thể phản ánh khả năng phát hiện được cải thiện, chứ không nhất thiết chất lượng sản phẩm giảm. Vì vậy, cần đọc chỉ số cùng bối cảnh và xu hướng, tránh biến chúng thành mục tiêu khiến nhóm tối ưu con số thay vì giảm rủi ro thực tế.

## Ví dụ: định hướng kiểm thử cho luồng thanh toán

Giả sử một ứng dụng thương mại điện tử cho phép người dùng đặt hàng và thanh toán qua một dịch vụ bên ngoài. Nhóm xác định các rủi ro trọng yếu là tính tiền sai, ghi nhận giao dịch trùng, mất trạng thái đơn hàng, lộ thông tin thanh toán và không xử lý được khi dịch vụ thanh toán gián đoạn.

Từ các rủi ro đó, chiến lược có thể định hướng như sau:

| Quyết định | Cách áp dụng |
|---|---|
| Mục tiêu chất lượng | Tính đúng số tiền, bảo đảm mỗi giao dịch được ghi nhận nhất quán, bảo vệ dữ liệu và xử lý lỗi có thể phục hồi |
| Phạm vi ưu tiên | Tạo đơn, tính tổng tiền, áp dụng giảm giá, gửi yêu cầu thanh toán, nhận kết quả và cập nhật trạng thái đơn |
| Cấp độ kiểm thử | Kiểm thử đơn vị cho quy tắc tính tiền; kiểm thử hợp đồng cho giao tiếp với cổng thanh toán; kiểm thử tích hợp cho cập nhật dữ liệu; kiểm thử đầu cuối cho hành trình đặt hàng |
| Tình huống quan trọng | Thanh toán thành công, bị từ chối, hết thời gian chờ, gửi lại yêu cầu, nhận phản hồi trễ hoặc nhận cùng một thông báo nhiều lần |
| Dữ liệu và môi trường | Dùng tài khoản và phương thức thanh toán thử nghiệm, dữ liệu đơn hàng có thể tái tạo và môi trường tích hợp được kiểm soát |
| Tự động hóa | Chạy kiểm thử quy tắc và hợp đồng trên mỗi thay đổi; chạy các luồng tích hợp quan trọng trong quy trình xây dựng; kiểm tra khói sau triển khai |
| Điều kiện phát hành | Không còn lỗi nghiêm trọng chưa được xử lý trong luồng giao dịch; các tình huống lỗi và khôi phục trọng yếu có bằng chứng; rủi ro còn lại được người có thẩm quyền chấp nhận |

Ví dụ này cho thấy chiến lược bắt đầu từ hậu quả có thể xảy ra, rồi mới chọn phạm vi, cấp độ, dữ liệu và cách tự động hóa. Nếu nhóm chỉ kiểm tra trường hợp thanh toán thành công, nhiều rủi ro quan trọng như gửi lặp hoặc phản hồi trễ sẽ không được phát hiện.

## Cách xây dựng và duy trì chiến lược

Một tài liệu chiến lược hữu ích nên đủ ngắn để nhóm có thể tham khảo trong công việc, nhưng đủ rõ để giải thích các quyết định. Có thể xây dựng theo trình tự sau:

1. Mô tả sản phẩm, người dùng, kiến trúc và bối cảnh phát hành.
2. Xác định mục tiêu chất lượng và các rủi ro chính.
3. Xếp thứ tự ưu tiên, xác định phạm vi và ghi nhận phần chưa được kiểm chứng sâu.
4. Chọn cấp độ, loại và kỹ thuật kiểm thử phù hợp với từng rủi ro.
5. Quy định cách chuẩn bị môi trường, dữ liệu và phụ thuộc.
6. Xác định phạm vi tự động hóa, thời điểm chạy và người sở hữu.
7. Thống nhất tiêu chí bắt đầu, hoàn tất, báo cáo và quyết định phát hành.
8. Xem xét lại chiến lược khi kiến trúc, người dùng, rủi ro, nhịp độ phát hành hoặc kết quả sự cố thay đổi.

Chiến lược không nên là tài liệu viết một lần rồi bỏ quên. Sau mỗi bản phát hành hoặc sự cố đáng kể, nhóm có thể xem lại lỗi nào đã lọt qua, kiểm thử nào phát hiện được vấn đề, khu vực nào tốn nhiều công sức và rủi ro mới nào xuất hiện. Từ đó, nhóm điều chỉnh ưu tiên và cách kiểm chứng.

## Những sai lầm cần tránh

- **Đồng nhất chiến lược với danh sách test case:** danh sách trường hợp kiểm thử mô tả việc cần chạy, nhưng không giải thích đầy đủ vì sao chọn chúng và rủi ro nào đang được kiểm soát.
- **Dùng một công thức cho mọi sản phẩm:** cơ cấu kiểm thử phải phản ánh kiến trúc, mức độ rủi ro và cách phát hành thực tế.
- **Chỉ tập trung vào kiểm thử chức năng:** hiệu năng, bảo mật, khả năng phục hồi, khả năng tiếp cận và toàn vẹn dữ liệu cũng có thể quyết định chất lượng.
- **Tự động hóa mọi thứ:** kiểm thử không ổn định hoặc khó bảo trì có thể làm chậm phản hồi và giảm niềm tin vào kết quả.
- **Đợi đến cuối dự án mới kiểm thử:** lỗi yêu cầu và thiết kế thường khó sửa hơn khi nhiều thành phần đã phụ thuộc.
- **Xem số lượng hoặc độ bao phủ là bằng chứng đầy đủ:** cần đánh giá chất lượng tình huống, mức rủi ro được bao phủ và lỗi thực tế được phát hiện.
- **Không ghi nhận rủi ro còn lại:** quyết định phát hành luôn cần hiểu những gì đã được kiểm tra, những gì chưa được kiểm tra và hệ quả có thể xảy ra.

## Kết luận

Chiến lược kiểm thử định hướng cách nhóm tạo bằng chứng về chất lượng và giảm rủi ro trong suốt vòng đời sản phẩm. Những quyết định cốt lõi xoay quanh mục tiêu chất lượng, ưu tiên rủi ro, phạm vi, cấp độ và loại kiểm thử, môi trường và dữ liệu, tự động hóa, thời điểm thực hiện, trách nhiệm, chỉ số và điều kiện phát hành.

Khi các quyết định này được giải thích rõ và cập nhật theo bối cảnh, nhóm có thể phân bổ nguồn lực hợp lý, phát hiện vấn đề sớm và đưa ra quyết định phát hành có cơ sở.
