# Điều DSL không bao phủ

Ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) được tạo ra để diễn đạt công việc trong một miền bài toán xác định. Phạm vi hẹp là đặc điểm tạo nên giá trị của DSL: người dùng làm việc với những khái niệm gần với lĩnh vực của họ, thay vì phải dùng một ngôn ngữ tổng quát để biểu đạt mọi thao tác.

Tuy nhiên, một miền bài toán trong thực tế thường nằm bên trong một hệ thống lớn hơn. Một DSL có thể mô tả truy vấn dữ liệu, bố cục giao diện, quy tắc định tuyến hoặc cấu hình hạ tầng, nhưng ứng dụng vẫn cần giao tiếp với hệ thống khác, xác thực người dùng, xử lý lỗi, vận hành, giám sát và đáp ứng yêu cầu của tổ chức. Những phần này có thể nằm ngoài phạm vi mà DSL được thiết kế để giải quyết.

Hiểu rõ **điều DSL không bao phủ** giúp sử dụng ngôn ngữ đúng mục đích, tránh kỳ vọng quá mức và thiết kế ranh giới tích hợp hợp lý. Không có nghĩa mọi DSL đều thiếu những khả năng này. Một DSL có thể mở rộng sang các phần lân cận, nhưng khi đó cần xác định rõ ngữ nghĩa, trách nhiệm và chi phí của phần mở rộng.

## 1. Phạm vi miền là ranh giới của DSL

Một DSL thường được thiết kế quanh ba yếu tố:

- **Khái niệm miền:** những đối tượng mà người dùng quan tâm, chẳng hạn bảng, cột, đơn hàng, tài nguyên máy chủ, tuyến đường hoặc thành phần giao diện.
- **Quy tắc miền:** các điều kiện và quan hệ hợp lệ, chẳng hạn điều kiện lọc dữ liệu, phụ thuộc giữa tài nguyên hoặc quy tắc bố cục.
- **Thao tác miền:** những việc người dùng có thể yêu cầu, chẳng hạn truy vấn, tạo tài nguyên, áp dụng kiểu hoặc chạy một bước trong quy trình.

Các yếu tố này xác định điều gì có ý nghĩa trong DSL. Câu lệnh nằm ngoài phạm vi có thể không có cú pháp tương ứng, không có cách diễn giải được định nghĩa hoặc không thể được bộ thực thi xử lý.

Ví dụ, SQL cung cấp ngôn ngữ để định nghĩa và thao tác dữ liệu trong các hệ quản trị cơ sở dữ liệu. Nó có thể truy vấn đơn hàng, cập nhật trạng thái và định nghĩa ràng buộc dữ liệu. Nhưng một câu lệnh SQL thông thường không mô tả đầy đủ màn hình mà khách hàng nhìn thấy, quy trình hỗ trợ khách hàng, cách triển khai ứng dụng web hay cách nhân viên xử lý một trường hợp tranh chấp.

Một DSL tốt không cần bao phủ mọi hoạt động của tổ chức sử dụng nó. Nó cần giải quyết tốt phần việc đã chọn và cung cấp ranh giới rõ ràng để phần còn lại được xử lý bởi công cụ hoặc thành phần phù hợp.

## 2. DSL không thay thế ngôn ngữ lập trình đa dụng

Ngôn ngữ lập trình đa dụng (General-Purpose Programming Language — GPL) được thiết kế để giải quyết nhiều loại bài toán. Chúng thường cung cấp cấu trúc dữ liệu, hàm, mô-đun, điều khiển luồng, xử lý lỗi, nhập xuất và cơ chế tích hợp thư viện.

DSL có thể biểu đạt một phần công việc rất hiệu quả, nhưng thường không cung cấp toàn bộ khả năng cần thiết để xây dựng một hệ thống hoàn chỉnh.

### 2.1. Ví dụ: SQL và ứng dụng quản lý đơn hàng

SQL có thể diễn đạt việc lấy các đơn hàng chưa thanh toán:

~~~sql
SELECT order_id, customer_id, total
FROM orders
WHERE status = 'PENDING';
~~~

Câu truy vấn xác định dữ liệu cần lấy. Để xây dựng chức năng hoàn chỉnh cho nhân viên xử lý đơn hàng, ứng dụng vẫn cần những phần việc khác:

- Xác thực nhân viên và kiểm tra quyền truy cập.
- Hiển thị danh sách đơn hàng trên giao diện.
- Cho phép người dùng chọn một đơn hàng và xác nhận thao tác.
- Gọi dịch vụ thanh toán hoặc dịch vụ vận chuyển nếu quy trình yêu cầu.
- Xử lý thời gian chờ, lỗi mạng và phản hồi không hợp lệ.
- Ghi nhận lịch sử thao tác và thông báo kết quả.

SQL có thể tham gia vào một số phần của hệ thống, chẳng hạn lưu quyền, ghi lịch sử hoặc cập nhật dữ liệu. Tuy nhiên, truy vấn SQL không tự tạo ra toàn bộ trải nghiệm và quy trình nghiệp vụ nói trên. Ứng dụng cần một ngôn ngữ đa dụng, framework hoặc các dịch vụ chuyên trách để phối hợp những thành phần đó.

### 2.2. DSL và ngôn ngữ chủ

Một số DSL được nhúng trong một ngôn ngữ lập trình đa dụng. Ngôn ngữ đa dụng đó thường được gọi là **ngôn ngữ chủ (host language)**. Người dùng viết phần mô tả miền bằng cú pháp DSL, sau đó dùng ngôn ngữ chủ để kết nối, điều khiển hoặc mở rộng hành vi.

Ví dụ Kotlin DSL của Gradle:

~~~kotlin
tasks.register("packageApp") {
    dependsOn("compileJava")

    doLast {
        println("Packaging application")
    }
}
~~~

Gradle DSL mô tả task và quan hệ phụ thuộc. Phần thân doLast chứa mã Kotlin thực thi khi task chạy. Khi cần xử lý logic phức tạp, người viết có thể sử dụng khả năng của Kotlin hoặc gọi một công cụ chuyên dụng.

Cách kết hợp này giúp DSL tập trung vào miền xây dựng phần mềm, còn ngôn ngữ chủ đảm nhiệm những logic tổng quát. Tuy nhiên, nó cũng có nghĩa người dùng cần hiểu ranh giới giữa cú pháp DSL và mã của ngôn ngữ chủ.

## 3. DSL không tự giải quyết những miền bài toán lân cận

Một hệ thống thực tế thường kết hợp nhiều miền. DSL được tạo ra cho một miền không mặc nhiên hiểu các khái niệm và quy tắc của miền khác.

### 3.1. Ví dụ: CSS và giao diện ứng dụng

CSS mô tả cách trình bày phần tử giao diện:

~~~css
.notice {
  padding: 1rem;
  border: 1px solid #888;
  border-radius: 0.5rem;
}
~~~

Quy tắc này điều chỉnh khoảng cách, đường viền và góc của một thành phần. Nó không tự quyết định:

- Người dùng hiện tại có được xem thông báo hay không.
- Nội dung thông báo lấy từ cơ sở dữ liệu nào.
- Khi nào thông báo được tạo hoặc gửi.
- Người dùng đã đọc thông báo hay chưa.
- Cần gọi API nào để cập nhật trạng thái.

Những công việc đó thuộc về logic ứng dụng, dữ liệu và dịch vụ phía máy chủ. CSS có thể tương tác với HTML và JavaScript trong một trang web, nhưng mỗi công nghệ vẫn có vai trò và ngữ nghĩa riêng.

### 3.2. Ví dụ: DSL hạ tầng và hành vi ứng dụng

Một công cụ quản lý hạ tầng có thể dùng cấu hình khai báo để mô tả máy chủ, mạng và tài nguyên lưu trữ cần có. Công cụ có thể lập kế hoạch tạo hoặc cập nhật những tài nguyên đó.

Điều này không đồng nghĩa ứng dụng được triển khai trên máy chủ sẽ tự hoạt động đúng. Những việc như xử lý yêu cầu nghiệp vụ, kiểm tra dữ liệu đầu vào, quản lý phiên đăng nhập, gửi email hay tính toán kết quả vẫn thuộc về ứng dụng và các dịch vụ của nó.

Tương tự, cấu hình hạ tầng có thể mô tả số lượng máy chủ hoặc quy tắc cân bằng tải, nhưng không tự chứng minh rằng mã ứng dụng không có lỗi hoặc rằng trải nghiệm người dùng đáp ứng yêu cầu nghiệp vụ.

### 3.3. Khi một DSL mở rộng sang miền khác

Có thể mở rộng DSL để hỗ trợ thêm khái niệm của miền lân cận. Chẳng hạn một công cụ triển khai có thể cung cấp cả cấu hình máy chủ, mạng, biến môi trường và bước chạy lệnh sau triển khai.

Khi mở rộng, cần xác định:

- Khái niệm mới thuộc miền nào và có quan hệ gì với khái niệm hiện tại.
- Thành phần nào chịu trách nhiệm thực thi.
- Quy tắc nào được kế thừa và quy tắc nào cần định nghĩa riêng.
- Cách báo lỗi khi hai phần cấu hình xung đột.
- Người dùng cần biết những kiến thức nào để sử dụng phần mở rộng.

Nếu liên tục thêm chức năng không liên quan, DSL sẽ mất tính tập trung và trở nên khó học, khó kiểm thử, khó bảo trì.

## 4. DSL không tự bảo đảm chất lượng phi chức năng

DSL thường giúp diễn đạt chức năng của miền, nhưng một hệ thống còn phải đáp ứng các yêu cầu phi chức năng (non-functional requirements), chẳng hạn hiệu năng, bảo mật, độ tin cậy, khả năng mở rộng, khả năng quan sát và khả năng phục hồi.

Một số DSL có thể cung cấp cấu hình liên quan đến các yêu cầu này. Ví dụ, DSL hạ tầng có thể cho phép chọn số bản sao của dịch vụ; DSL truy vấn có thể biểu đạt giới hạn kết quả; DSL định tuyến có thể cấu hình thời gian chờ. Dù vậy, việc có một thuộc tính cấu hình không đồng nghĩa hệ thống đã được bảo đảm chất lượng tương ứng.

### 4.1. Hiệu năng

Một truy vấn có cú pháp hợp lệ vẫn có thể chạy chậm do dữ liệu lớn, chỉ mục không phù hợp, thống kê lỗi thời hoặc kế hoạch thực thi không tốt.

~~~sql
SELECT *
FROM transactions
WHERE customer_id = 12345;
~~~

Câu truy vấn diễn đạt đúng mục tiêu lọc dữ liệu, nhưng hiệu năng phụ thuộc vào cấu trúc bảng, số lượng bản ghi, chỉ mục, thống kê và cách hệ quản trị cơ sở dữ liệu thực thi. DSL truy vấn không tự đảm bảo truy vấn sẽ đáp ứng một ngưỡng thời gian cụ thể.

Cần đo đạc trên dữ liệu và môi trường gần với thực tế, phân tích kế hoạch thực thi và tối ưu ở đúng thành phần.

### 4.2. Bảo mật

Một cấu hình có thể hợp lệ về cú pháp nhưng vẫn cấp quyền quá rộng. Một truy vấn có thể trả về dữ liệu đúng yêu cầu kỹ thuật nhưng không nên được người dùng hiện tại xem.

Ví dụ, điều kiện lọc theo trạng thái đơn hàng không thay thế việc kiểm tra người dùng có quyền truy cập đơn hàng đó hay không. Việc xác thực và phân quyền cần được thực hiện ở tầng có trách nhiệm, chẳng hạn ứng dụng, dịch vụ định danh hoặc chính sách bảo mật của cơ sở dữ liệu.

DSL có thể cung cấp cách mô tả chính sách bảo mật, nhưng hệ thống vẫn phải kiểm tra cách chính sách được áp dụng, phạm vi tác động và khả năng vượt quyền.

### 4.3. Độ tin cậy và khả năng phục hồi

Một DSL có thể mô tả số bản sao, thời gian chờ hoặc chính sách thử lại. Nhưng khả năng phục hồi còn phụ thuộc vào trạng thái của dịch vụ, dữ liệu, mạng, vùng lỗi và cách xử lý khi thao tác chỉ thành công một phần.

Ví dụ, tự động thử lại một yêu cầu thanh toán có thể gây thu tiền hai lần nếu dịch vụ không hỗ trợ cơ chế chống xử lý trùng lặp. Chỉ thêm một cấu hình retry không giải quyết được toàn bộ vấn đề. Cần có thiết kế phù hợp về tính lặp an toàn, mã giao dịch, trạng thái và xử lý kết quả không chắc chắn.

### 4.4. Khả năng quan sát và vận hành

Cấu hình mô tả hệ thống không thay thế việc thu thập log, metric, trace, cảnh báo và quy trình phản ứng sự cố. Một dịch vụ có thể được triển khai thành công nhưng vẫn khó vận hành nếu không có tín hiệu để phát hiện lỗi hoặc không có hướng dẫn xử lý.

Những yêu cầu này cần được thiết kế cùng hệ thống. DSL có thể hỗ trợ cấu hình một phần, nhưng trách nhiệm vận hành còn liên quan đến nền tảng và con người.

## 5. DSL không tự hiểu đầy đủ ngữ cảnh nghiệp vụ

DSL chỉ có thể xử lý những khái niệm, dữ liệu và quy tắc đã được định nghĩa hoặc được cung cấp cho bộ thực thi. Nó không tự suy luận đầy đủ ý định của tổ chức hay giải quyết mọi trường hợp ngoại lệ trong hoạt động thực tế.

Ví dụ, một quy tắc có thể biểu diễn rằng đơn hàng trên một mức tiền nhất định cần được phê duyệt. Nhưng để xác định quy tắc đó có phù hợp hay không, tổ chức còn phải làm rõ:

- Mức tiền được tính trước hay sau thuế và giảm giá.
- Ai có thẩm quyền phê duyệt.
- Đơn hàng có nhiều loại tiền tệ được quy đổi theo tỷ giá nào.
- Điều gì xảy ra khi người phê duyệt vắng mặt.
- Có ngoại lệ nào dành cho khách hàng hoặc loại sản phẩm đặc biệt.
- Quy định nào cần lưu lại để phục vụ kiểm toán.

Nếu các khái niệm này chưa được định nghĩa, DSL không thể tự tạo ra một chính sách chính xác. Người thiết kế cần làm rõ yêu cầu với chuyên gia miền và chuyển các quyết định đó thành quy tắc có thể kiểm tra.

### 5.1. Dữ liệu đầu vào có thể không đầy đủ hoặc sai

DSL có thể kiểm tra cấu trúc và kiểu dữ liệu, nhưng dữ liệu hợp lệ về mặt hình thức chưa chắc đúng về nghiệp vụ.

Ví dụ, một trường ngày có thể chứa giá trị ngày hợp lệ nhưng lại là ngày giao hàng trước ngày đặt hàng. Một mã khách hàng có thể đúng định dạng nhưng không tồn tại trong hệ thống. Một đơn hàng có thể có tổng tiền hợp lệ nhưng không khớp với các dòng chi tiết.

Cần phân biệt:

- **Kiểm tra cú pháp:** câu lệnh có tuân theo cấu trúc ngôn ngữ không?
- **Kiểm tra kiểu và cấu trúc:** giá trị có đúng kiểu, đúng trường và đúng định dạng không?
- **Kiểm tra ràng buộc miền:** dữ liệu có thỏa mãn quy tắc nghiệp vụ không?
- **Kiểm tra ngữ cảnh:** thao tác có phù hợp với trạng thái hiện tại và quyền của người thực hiện không?

Một DSL có thể hỗ trợ nhiều mức kiểm tra, nhưng phạm vi kiểm tra phải được định nghĩa rõ. Không nên coi việc phân tích cú pháp thành công là bằng chứng dữ liệu hay nghiệp vụ đã đúng.

## 6. DSL không tự quản lý mọi tác động bên ngoài

Khi thực thi, một chương trình DSL có thể cần tương tác với cơ sở dữ liệu, hệ thống tệp, API, mạng, hàng đợi thông điệp hoặc dịch vụ của bên thứ ba. DSL thường mô tả yêu cầu ở mức miền, còn việc giao tiếp thực tế do bộ thực thi, thư viện hoặc nền tảng đảm nhiệm.

Những vấn đề có thể nằm ngoài phạm vi của DSL gồm:

- Thông tin xác thực và vòng đời của khóa truy cập.
- Kết nối mạng, DNS, proxy và chứng chỉ TLS.
- Giới hạn tốc độ, hạn mức và chi phí của dịch vụ bên ngoài.
- Thời gian chờ, thử lại và xử lý phản hồi không xác định.
- Tính nhất quán giữa nhiều hệ thống.
- Việc một thao tác đã xảy ra ở hệ thống ngoài nhưng kết quả phản hồi bị thất lạc.

Ví dụ, một DSL quy trình có thể mô tả bước gửi yêu cầu đến dịch vụ vận chuyển. Câu lệnh đó không tự bảo đảm dịch vụ vận chuyển đang hoạt động, thông tin đăng nhập còn hiệu lực hoặc yêu cầu không bị xử lý hai lần.

Cần xác định thành phần nào quản lý kết nối, lỗi, bảo mật và tính nhất quán. Nếu DSL che giấu toàn bộ những chi tiết này, tài liệu của nó vẫn phải giải thích hành vi khi hệ thống ngoài gặp sự cố.

## 7. DSL không tự xác định ranh giới giao dịch và tính nhất quán

Trong các hệ thống có nhiều thao tác liên quan, kết quả đúng còn phụ thuộc vào cách các thao tác được phối hợp.

Ví dụ, một quy trình đặt hàng có thể gồm:

1. Tạo đơn hàng.
2. Giữ hàng trong kho.
3. Thu tiền.
4. Tạo yêu cầu vận chuyển.
5. Gửi thông báo cho khách hàng.

Nếu bước thu tiền thành công nhưng bước tạo vận chuyển thất bại, hệ thống phải quyết định giữ đơn hàng ở trạng thái nào, có hoàn tiền hay thử lại, và làm sao tránh tạo hai yêu cầu vận chuyển.

Một DSL có thể mô tả thứ tự các bước hoặc một số chính sách giao dịch. Nhưng khả năng bảo đảm tính nguyên tử, cô lập, nhất quán và bền vững phụ thuộc vào mô hình giao dịch và nền tảng thực thi. Giao dịch cơ sở dữ liệu thường chỉ bao phủ một ranh giới tài nguyên nhất định; nó không tự động tạo thành giao dịch nguyên tử trên nhiều dịch vụ độc lập.

Với quy trình phân tán, hệ thống có thể cần cơ chế như saga, thao tác bù, khóa chống trùng lặp, outbox hoặc xử lý sự kiện. Việc chọn cơ chế phù hợp là quyết định kiến trúc và nghiệp vụ, không chỉ là vấn đề cú pháp DSL.

## 8. DSL không tự thay thế kiểm thử, tài liệu và quy trình phát triển

Một DSL có thể giúp mô tả yêu cầu nhất quán và cho phép kiểm tra cấu hình. Tuy nhiên, nó không tự chứng minh toàn bộ hệ thống hoạt động đúng.

Cần xem xét các hoạt động bổ trợ:

- **Kiểm thử đơn vị:** kiểm tra logic hoặc thành phần ở phạm vi nhỏ.
- **Kiểm thử tích hợp:** kiểm tra tương tác giữa DSL, bộ thực thi và hệ thống bên ngoài.
- **Kiểm thử đầu cuối:** xác minh quy trình thực tế từ đầu đến cuối.
- **Kiểm tra bảo mật:** xác minh quyền, dữ liệu nhạy cảm và các đường truy cập.
- **Kiểm tra hiệu năng:** đo thời gian phản hồi, thông lượng và mức sử dụng tài nguyên.
- **Quản lý phiên bản:** theo dõi thay đổi của DSL, cấu hình và ngữ nghĩa.
- **Tài liệu vận hành:** giải thích cách triển khai, giám sát và khôi phục khi có lỗi.

Ví dụ, cấu hình CI có thể mô tả các bước chạy kiểm thử, nhưng bản thân cấu hình không bảo đảm các kiểm thử đó bao phủ đủ trường hợp. Một cấu hình triển khai có thể hợp lệ nhưng vẫn gây gián đoạn nếu thay đổi không tương thích với phiên bản ứng dụng hoặc dữ liệu hiện có.

DSL là một phần của quy trình phát triển. Chất lượng cuối cùng cần được xác minh bằng kiểm thử và vận hành thực tế.

## 9. Những dấu hiệu cho thấy một yêu cầu nằm ngoài DSL

Khi sử dụng DSL, có thể nhận biết yêu cầu vượt khỏi phạm vi hiện tại qua một số dấu hiệu:

| Dấu hiệu | Vấn đề có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Cần khái niệm không tồn tại trong DSL | Không có cách diễn đạt có ngữ nghĩa rõ ràng | Xem xét mở rộng DSL nếu khái niệm thuộc miền |
| Phải viết nhiều đoạn mã vòng quanh một cấu hình đơn giản | DSL thiếu điểm tích hợp hoặc khả năng mở rộng phù hợp | Dùng API, plugin hoặc ngôn ngữ chủ |
| Cùng một DSL bị dùng để điều khiển nhiều miền không liên quan | Phạm vi ngôn ngữ quá rộng và khó hiểu | Chia thành DSL nhỏ hoặc xác định ranh giới mô-đun |
| Câu lệnh hợp lệ nhưng kết quả sai về nghiệp vụ | Thiếu ràng buộc hoặc thiếu ngữ cảnh | Bổ sung quy tắc miền và kiểm tra dữ liệu |
| Cấu hình thành công nhưng hệ thống vẫn không đáp ứng yêu cầu vận hành | Thiếu kiểm tra phi chức năng hoặc năng lực nền tảng | Bổ sung giám sát, kiểm thử và chính sách vận hành |
| Không thể xử lý lỗi của hệ thống ngoài | Trách nhiệm tích hợp chưa rõ | Định nghĩa timeout, retry, bù trừ và xử lý trạng thái không chắc chắn |
| Người dùng phải thường xuyên thoát khỏi DSL để viết mã tổng quát | DSL không còn phù hợp với phần lớn tác vụ đang yêu cầu | Cân nhắc dùng ngôn ngữ đa dụng hoặc thiết kế lại ranh giới |

Không phải mọi dấu hiệu đều yêu cầu mở rộng DSL. Nếu yêu cầu chỉ là một thao tác hiếm gặp và thuộc trách nhiệm của thành phần khác, gọi API hoặc dùng một công cụ chuyên biệt thường hợp lý hơn.

## 10. Cách thiết kế ranh giới DSL

Khi xây dựng DSL, cần xác định phạm vi ngay từ đầu và ghi lại những phần được hỗ trợ, những phần được ủy quyền và những phần nằm ngoài mục tiêu.

### 10.1. Xác định người dùng và công việc chính

Trả lời các câu hỏi:

- Ai sẽ viết và đọc DSL?
- Họ đang giải quyết công việc nào?
- Những khái niệm nào xuất hiện thường xuyên?
- Kết quả nào cần được kiểm tra hoặc thực thi?
- Những thao tác nào cần quyền hạn đặc biệt?

Một DSL cho chuyên viên phân tích dữ liệu có thể ưu tiên truy vấn và biến đổi dữ liệu. DSL cho kỹ sư hạ tầng có thể ưu tiên tài nguyên và phụ thuộc. Không nên đưa toàn bộ cú pháp của ngôn ngữ đa dụng vào DSL chỉ vì có thể làm được.

### 10.2. Viết rõ phần hỗ trợ và phần không hỗ trợ

Tài liệu ngôn ngữ nên nêu rõ:

- Các đối tượng, câu lệnh và kiểu dữ liệu được hỗ trợ.
- Các ràng buộc và quy tắc đánh giá.
- Các hành động có tác động phụ.
- Các giới hạn về tài nguyên, môi trường và tích hợp.
- Cách xử lý cú pháp hoặc tính năng không được hỗ trợ.
- Những trách nhiệm được giao cho host language, runtime hoặc dịch vụ khác.

Thông báo lỗi cần chỉ ra vị trí và nguyên nhân để người dùng biết câu lệnh sai cú pháp, sai kiểu, vi phạm quy tắc miền hay yêu cầu một khả năng không tồn tại.

### 10.3. Chọn cơ chế mở rộng phù hợp

Có một số cách kết nối DSL với phần còn lại của hệ thống:

**Dùng API hoặc thư viện:** DSL giữ phạm vi nhỏ; ứng dụng gọi API để thực hiện những tác vụ tổng quát hoặc thuộc miền khác.

**Nhúng DSL trong ngôn ngữ chủ:** dùng cú pháp DSL cho phần mô tả miền và ngôn ngữ chủ cho logic điều khiển, tích hợp hoặc xử lý ngoại lệ.

**Dùng plugin hoặc extension:** cho phép bổ sung khả năng theo mô-đun, có hợp đồng rõ ràng về kiểu dữ liệu, vòng đời và quyền thực thi.

**Kết hợp nhiều DSL:** mỗi DSL phụ trách một miền, sau đó được điều phối bởi một lớp tích hợp hoặc quy trình cấp cao hơn.

Không có cơ chế nào phù hợp với mọi hệ thống. Lựa chọn phụ thuộc vào người dùng, mức độ phức tạp, yêu cầu an toàn và cách triển khai.

### 10.4. Tránh mở rộng vô hạn

Mỗi tính năng mới đều làm tăng chi phí thiết kế cú pháp, định nghĩa ngữ nghĩa, kiểm thử, tài liệu và tương thích ngược. Trước khi thêm một khả năng, hãy xác định:

- Có nhiều người dùng cần khả năng này không?
- Nó có thuộc cùng miền bài toán không?
- Có thể giải quyết bằng API hoặc plugin hiện có không?
- Nó có tạo ra cách diễn đạt mơ hồ hoặc xung đột không?
- Bộ thực thi có thể hỗ trợ và kiểm thử hành vi đó một cách đáng tin cậy không?

Một DSL tập trung với ranh giới tốt thường dễ học và duy trì hơn một DSL cố gắng trở thành công cụ cho mọi việc.

## 11. Ví dụ tổng hợp: DSL truy vấn trong hệ thống thương mại điện tử

Giả sử nhóm phát triển xây dựng một DSL nội bộ cho nhân viên phân tích dữ liệu. DSL cho phép chọn tập dữ liệu, lọc đơn hàng, nhóm theo khách hàng và tính tổng doanh thu.

Một mô tả giả định có thể như sau:

~~~text
dataset orders
where status == "PAID"
group by customer_id
calculate revenue = sum(total)
sort by revenue descending
~~~

DSL này có thể bao phủ việc truy xuất và tổng hợp dữ liệu đơn hàng. Để hệ thống sử dụng được trong môi trường thật, còn nhiều trách nhiệm cần xử lý:

| Trách nhiệm | DSL truy vấn có thể làm gì? | Thành phần thường đảm nhiệm |
| --- | --- | --- |
| Chọn và tổng hợp dữ liệu | Diễn đạt tập dữ liệu, điều kiện và phép tính | Bộ thực thi truy vấn và cơ sở dữ liệu |
| Xác thực người dùng | Có thể tham chiếu vai trò hoặc chính sách nếu được thiết kế | Hệ thống định danh và phân quyền |
| Bảo vệ dữ liệu nhạy cảm | Có thể hỗ trợ quy tắc lọc hoặc che dữ liệu | Lớp bảo mật, chính sách dữ liệu và cơ sở dữ liệu |
| Hiển thị báo cáo | Không phải mục tiêu chính của DSL truy vấn | Ứng dụng báo cáo hoặc giao diện |
| Lập lịch chạy báo cáo | Có thể mô tả tham số lịch nếu DSL hỗ trợ | Bộ lập lịch hoặc hệ thống workflow |
| Gửi báo cáo qua email | Có thể yêu cầu một hành động nếu có tích hợp | Dịch vụ email và bộ điều phối |
| Theo dõi lỗi và hiệu năng | Có thể cung cấp thông tin thực thi | Hệ thống log, metric, trace và giám sát |

Bảng trên phân biệt khả năng diễn đạt với trách nhiệm thực thi. Một sản phẩm có thể tích hợp tất cả chức năng vào cùng giao diện, nhưng điều đó không làm cho chúng tự động thuộc về ngữ nghĩa của DSL truy vấn.

Nếu nhóm quyết định bổ sung cú pháp gửi báo cáo qua email, cần xác định rõ đây là một phần mở rộng của DSL hay một bước trong DSL workflow riêng. Cần quy định người dùng nào được phép gửi, địa chỉ nhận được kiểm tra ra sao, dữ liệu nhạy cảm được xử lý thế nào và hành vi khi dịch vụ email lỗi. Chỉ thêm một từ khóa send không giải quyết những yêu cầu này.

## 12. Kết luận

DSL có giá trị vì tập trung vào một miền bài toán và cung cấp cách diễn đạt gần với khái niệm của miền đó. Phạm vi của nó không mặc nhiên bao gồm toàn bộ logic ứng dụng, các miền nghiệp vụ lân cận, yêu cầu phi chức năng, tích hợp hệ thống, vận hành và quyết định của con người.

Một DSL có thể mở rộng hoặc kết hợp với ngôn ngữ đa dụng, API, plugin và các DSL khác. Khi làm vậy, cần chỉ rõ ai chịu trách nhiệm cho từng phần, ngữ nghĩa nào được bảo đảm và giới hạn nào vẫn tồn tại.

Khi gặp một yêu cầu mới, hãy xác định nó có thuộc miền mà DSL phục vụ hay không, DSL có đủ thông tin để diễn đạt chính xác hay không, và thành phần nào chịu trách nhiệm thực thi. Nếu yêu cầu nằm ngoài phạm vi, hãy chuyển nó đến công cụ hoặc thành phần phù hợp; chỉ mở rộng DSL khi khả năng mới thực sự phục vụ miền và có thể được định nghĩa, kiểm thử, duy trì rõ ràng.

