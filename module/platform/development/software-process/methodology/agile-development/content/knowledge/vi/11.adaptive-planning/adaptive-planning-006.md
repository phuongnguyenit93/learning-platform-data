# Xác định mục tiêu ngắn hạn cùng phần giá trị có thể bàn giao

## 1. Vì sao kế hoạch Agile bắt đầu từ mục tiêu và giá trị?

Trong phát triển phần mềm, kế hoạch dài hạn thường chứa nhiều giả định về nhu cầu, công nghệ, năng lực và sự phụ thuộc giữa các nhóm. Một số giả định chỉ được kiểm chứng khi người dùng thực sự thao tác với sản phẩm. Vì vậy, Agile khuyến khích **lập kế hoạch theo các khoảng thời gian gần, giao phần sản phẩm dùng được, nhận phản hồi và điều chỉnh bước tiếp theo**.

Điều này không có nghĩa là làm việc không có kế hoạch. Nhóm vẫn cần biết đang hướng tới đâu, điều gì đáng ưu tiên, công việc nào có thể hoàn tất và đâu là các ràng buộc về chất lượng. Khác biệt nằm ở việc **mục tiêu định hướng cách lựa chọn công việc**, còn kế hoạch thực hiện được cập nhật theo thông tin mới.

Ví dụ, một nhóm đang xây nền tảng học trực tuyến có thể nhận một danh sách yêu cầu:

- Thiết kế lại trang khóa học.
- Thêm API đăng ký.
- Tạo bảng lưu đăng ký.
- Gửi email xác nhận.
- Làm dashboard cho quản trị viên.

Danh sách trên mô tả **công việc**. Nó chưa trả lời câu hỏi người dùng sẽ nhận được điều gì sau giai đoạn sắp tới. Nếu nhóm hoàn tất ba trong năm việc nhưng học viên vẫn không thể đăng ký một khóa học, rất khó chứng minh sản phẩm đã tiến gần hơn tới kết quả mong muốn.

Một mục tiêu ngắn hạn hữu ích hơn có thể là:

> Trong hai tuần tới, tạo được luồng đăng ký khóa học miễn phí từ đầu đến cuối cho nhóm học viên thử nghiệm, để họ có thể chọn khóa còn chỗ, đăng ký và nhận xác nhận đáng tin cậy.

Mục tiêu này giúp nhóm chọn **lát cắt giá trị** phù hợp, thay vì đánh giá tiến độ chỉ bằng số việc đã hoàn thành.

Trong module **AGILE_DEVELOPMENT**, năng lực xác định mục tiêu ngắn hạn kết nối trực tiếp với user story, Product Backlog, Scrum, Kanban, các thực hành kỹ thuật của XP và đo lường luồng công việc. Mọi phương pháp đều cần một cách hiểu rõ ràng về **giá trị sẽ được tạo ra và bằng chứng xác nhận giá trị đó**.

## 2. Phân biệt mục tiêu, kết quả, đầu ra và công việc

Bốn khái niệm này liên quan nhưng không thể thay thế nhau:

| Khái niệm | Câu hỏi | Ví dụ với đăng ký khóa học |
| --- | --- | --- |
| **Mục tiêu (goal)** | Nhóm muốn thay đổi điều gì trong một khoảng thời gian? | Giúp học viên thử nghiệm tự đăng ký được khóa học miễn phí. |
| **Kết quả (outcome)** | Khi dùng sản phẩm, hành vi/lợi ích thực tế thay đổi ra sao? | Học viên hoàn tất đăng ký mà không cần nhờ nhân viên. |
| **Đầu ra/phần bàn giao (output/increment)** | Sản phẩm có thêm khả năng hoạt động nào? | Luồng xem chỗ trống → đăng ký → lưu kết quả → xác nhận. |
| **Công việc (activity/task)** | Nhóm phải thực hiện những gì? | Viết API, cập nhật giao diện, xử lý giao dịch dữ liệu, viết test. |

**Mục tiêu không phải danh sách tác vụ.** Câu “hoàn thành 8 ticket” không cho biết 8 ticket ấy có góp phần giải quyết vấn đề người dùng hay không. Câu “tăng 20% số học viên đăng ký thành công” là một mục tiêu kết quả có thể đo, nhưng nhóm cần có số liệu nền, khoảng thời gian, phạm vi thử nghiệm và khả năng tác động thực tế trước khi xem đó là một cam kết hợp lý.

Một cách biểu đạt đầy đủ gồm:

1. **Mục đích:** vấn đề và đối tượng cụ thể.
2. **Kết quả kỳ vọng:** điều người dùng có thể làm tốt hơn.
3. **Phần có thể bàn giao:** hành vi sản phẩm đủ hoàn chỉnh để dùng hoặc kiểm chứng.
4. **Bằng chứng:** tiêu chí chấp nhận, test và tín hiệu sử dụng.
5. **Giới hạn:** thời gian, phạm vi người dùng, chất lượng và phụ thuộc.

Không phải mọi kết quả sử dụng đều xuất hiện ngay khi phần mềm được hoàn tất. Nhóm có thể **cam kết chất lượng và phần sản phẩm nằm trong quyền kiểm soát**, đồng thời xem những chỉ số hành vi người dùng là **giả thuyết cần đo**, tránh hứa một kết quả chịu ảnh hưởng lớn từ tiếp thị, mùa vụ hoặc yếu tố ngoài sản phẩm.

### 2.1. Mục tiêu tốt định hướng lựa chọn, không khóa cứng giải pháp

So sánh:

> “Hoàn thành trang đăng ký mới bằng framework X, xây ba API và chuyển dữ liệu sang bảng Y.”

với:

> “Học viên thử nghiệm có thể hoàn tất đăng ký khóa còn chỗ trên web và biết chắc kết quả đã được ghi nhận.”

Ví dụ thứ nhất cố định cách triển khai. Ví dụ thứ hai cho phép nhóm cùng Product Owner tìm ra cách tạo giá trị trong các ràng buộc đã biết. Nếu kiến trúc hiện tại đã có API phù hợp, nhóm có thể dùng lại thay vì xây một API mới chỉ để đúng kế hoạch ban đầu.

Mục tiêu vẫn phải nêu rõ **giới hạn bắt buộc**. Ví dụ, không được tạo đăng ký trùng, không lộ dữ liệu học viên, không bỏ qua kiểm thử tích hợp cần thiết hoặc thay đổi hợp đồng API chung mà không phối hợp với chủ sở hữu.

### 2.2. Mục tiêu là định hướng; tiêu chí hoàn tất là cơ chế kiểm chứng

Hai câu hỏi khác nhau:

- **Đã đạt mục tiêu chưa?** Học viên trong phạm vi thử nghiệm có thể tự đăng ký hợp lệ không?
- **Increment đã Done chưa?** Những phần sản phẩm được tuyên bố hoàn tất đã đáp ứng Definition of Done chưa?

Nhóm có thể tạo một Increment đáp ứng DoD nhưng giả thuyết sản phẩm chưa được xác nhận vì chưa đủ người dùng thử. Điều này không biến Increment thành “chưa hoàn tất kỹ thuật”, nhưng nhắc nhóm rằng **việc giao sản phẩm và việc chứng minh kết quả sử dụng là hai bước khác nhau**.

## 3. Chọn khung thời gian gần mà vẫn giữ định hướng dài hạn

Kế hoạch thích ứng thường có nhiều tầng, mỗi tầng mang độ chi tiết và mức chắc chắn khác nhau:

| Tầm nhìn kế hoạch | Nội dung nên làm rõ | Mức độ chi tiết phù hợp |
| --- | --- | --- |
| **Tầm nhìn/chiến lược** | Sản phẩm phục vụ ai, giải quyết vấn đề gì và có giá trị dài hạn nào? | Định hướng rộng; xem lại khi bối cảnh thay đổi. |
| **Mục tiêu sản phẩm** | Năng lực/kết quả trung hạn cần đạt để tiến đến tầm nhìn? | Mục tiêu rõ; nhiều lựa chọn giải pháp còn mở. |
| **Mục tiêu ngắn hạn** | Trong vòng làm việc gần, phần thay đổi có ích nào cần hoàn tất hoặc kiểm chứng? | Cụ thể đủ để chọn backlog và đo kết quả. |
| **Kế hoạch thực hiện gần** | Hạng mục nào, thứ tự nào, ai phối hợp và phụ thuộc gì? | Chi tiết hơn, được cập nhật khi học thêm. |
| **Điều chỉnh hằng ngày/liên tục** | Đang mắc ở đâu, điều gì cần làm tiếp để đạt mục tiêu? | Dựa trên tình trạng thực tế và dòng công việc. |

Trong Scrum, **Product Goal** là cam kết gắn với Product Backlog, còn **Sprint Goal** là cam kết gắn với Sprint Backlog. Trong Kanban, nhóm có thể sử dụng mục tiêu dịch vụ/sản phẩm ngắn hạn cùng chính sách nhận việc và nhịp xem xét, mà không cần một Sprint cố định.

**Không có một độ dài đúng cho mọi mục tiêu ngắn hạn.** Hai tuần có thể phù hợp cho một nhóm với khả năng tích hợp và nhận phản hồi thường xuyên; nhóm khác có thể chọn nhịp một tuần hoặc một vài ngày cho thử nghiệm. Nếu dùng Scrum, Sprint có độ dài cố định **tối đa một tháng**. Một vòng lặp ngắn có ích khi nhóm có năng lực hoàn tất và kiểm chứng được điều gì đó, thay vì chỉ tăng số cuộc họp.

### 3.1. Rolling-wave planning: lập kế hoạch gần chi tiết hơn xa

Thay vì dự đoán mọi hạng mục trong sáu tháng tới ở cùng độ chi tiết, nhóm có thể:

1. Giữ mục tiêu sản phẩm và các cột mốc bắt buộc ở mức rõ ràng.
2. Làm rõ các hạng mục có khả năng được thực hiện sớm.
3. Chia nhỏ phần lớn hoặc nhiều rủi ro trước khi bắt đầu.
4. Dựa vào kết quả mỗi lần giao để điều chỉnh thứ tự và mức chi tiết của các hạng mục tiếp theo.

Cách này đôi khi gọi là **rolling-wave planning**. Điểm cốt lõi là mức chi tiết tăng lên khi thời điểm quyết định đến gần và thông tin đáng tin cậy hơn.

## 4. Cách viết mục tiêu ngắn hạn có thể hành động

Một mẫu đơn giản:

> Trong **[khoảng thời gian/nhịp làm việc]**, nhóm hướng tới **[kết quả có ích cho đối tượng cụ thể]** bằng cách bàn giao hoặc kiểm chứng **[khả năng sản phẩm cụ thể]**, với **[bằng chứng thành công]** và **[ràng buộc không thể bỏ qua]**.

**Ví dụ:**

> Trong vòng làm việc hai tuần, giúp học viên thử nghiệm tự đăng ký một khóa học miễn phí còn chỗ và nhận xác nhận. Nhóm dự kiến giao lát cắt từ giao diện đến dữ liệu, kiểm thử đăng ký lặp và tranh chấp chỗ cuối; đo tỷ lệ hoàn tất cùng phản hồi về sự dễ hiểu của trạng thái đăng ký.

Mẫu không bắt buộc mọi mục tiêu phải có một con số. Một mục tiêu như **“cho phép nhân viên hỗ trợ tra cứu tình trạng đăng ký đúng quyền, không cần truy cập trực tiếp cơ sở dữ liệu”** vẫn có thể được kiểm chứng bằng tình huống sử dụng rõ ràng.

### 4.1. Năm phép thử cho mục tiêu

| Phép thử | Câu hỏi | Dấu hiệu cần sửa |
| --- | --- | --- |
| **Gắn với giá trị** | Ai sẽ được lợi và vì sao? | Mục tiêu chỉ liệt kê công việc kỹ thuật. |
| **Có trọng tâm** | Nhóm có thể giải thích một kết quả chung không? | Gộp nhiều chủ đề không liên hệ vào một mục tiêu. |
| **Có thể kiểm chứng** | Quan sát điều gì để biết nhóm đã tiến gần hoặc đạt mục tiêu? | “Cải thiện trải nghiệm” nhưng không có hành vi cụ thể. |
| **Khả thi trong khung gần** | Có phần đủ nhỏ và cơ hội tích hợp/kiểm thử không? | Chỉ hoàn tất các tầng kỹ thuật rời rạc, chưa dùng được. |
| **Có ràng buộc rõ** | Chất lượng, bảo mật, người dùng và phụ thuộc đã được nêu chưa? | Nhóm phải tự đoán chính sách hoặc hạ chuẩn để kịp hạn. |

Mục tiêu không nên biến thành công thức đo số lượng máy móc. Chỉ tiêu **“100% ticket đóng đúng thứ Sáu”** dễ thúc đẩy chia ticket giả tạo hoặc đánh dấu Done sớm. Hãy định nghĩa kết quả từ góc nhìn người dùng và chất lượng sản phẩm.

### 4.2. Một mục tiêu, nhiều cách đạt mục tiêu

Mục tiêu ngắn hạn nên chừa chỗ cho nhóm lựa chọn giải pháp:

- Tái sử dụng thành phần sẵn có nếu đáp ứng đúng yêu cầu.
- Chọn lát cắt nhỏ để kiểm tra giả định quan trọng nhất.
- Thay đổi thứ tự chi tiết khi phát hiện phụ thuộc mới.
- Bỏ một tính năng phụ ít giá trị để giữ kết quả chính.
- Tham vấn người có thẩm quyền khi ràng buộc nghiệp vụ chưa rõ.

Nhóm cần minh bạch với Product Owner và bên liên quan khi những điều chỉnh này ảnh hưởng dự báo hoặc phạm vi.

## 5. Xác định “phần giá trị có thể bàn giao” là gì?

### 5.1. Increment không phải một phần việc đang dở

**Increment** là phần sản phẩm tăng thêm, tích hợp với những phần đã hoàn tất trước đó và có thể sử dụng trong phạm vi dự định. Trong Scrum, Increment phải đáp ứng **Definition of Done (DoD)**; một Sprint có thể có nhiều Increment và có thể phát hành chúng trước khi Sprint kết thúc.

Một API riêng lẻ chưa tích hợp, một giao diện chỉ dùng dữ liệu giả hoặc cơ sở dữ liệu đã tạo xong chưa tự động là phần giá trị bàn giao cho học viên. Những kết quả này có thể là tiến độ kỹ thuật cần thiết, nhưng **không nên mô tả là luồng người dùng hoàn tất**.

Phân biệt ba mức:

| Mức | Ví dụ | Có thể khẳng định điều gì? |
| --- | --- | --- |
| **Task hoàn tất** | Viết logic xử lý số chỗ và test đơn vị. | Một công việc kỹ thuật hoàn tất theo tiêu chí của nó. |
| **Increment hoàn tất** | Học viên đăng ký được trên luồng tích hợp, hệ thống lưu chính xác, đáp ứng DoD. | Có thêm khả năng sản phẩm dùng được trong phạm vi xác định. |
| **Kết quả sử dụng được chứng minh** | Người dùng thử thật hoàn tất đăng ký nhanh hơn và không gặp lỗi nghiêm trọng. | Có bằng chứng về giả thuyết giá trị, trong giới hạn dữ liệu và thử nghiệm. |

**Done không nhất thiết đồng nghĩa với “đã phát hành rộng rãi”**. Một Increment có thể được kiểm chứng và sẵn sàng sử dụng nhưng tổ chức lựa chọn thời điểm release riêng theo chính sách vận hành, an toàn hoặc mục tiêu sản phẩm.

### 5.2. Chọn lát cắt dọc (vertical slice)

Lát cắt dọc là một phần hành vi sử dụng hoàn chỉnh, đi qua **những lớp kỹ thuật cần thiết** để người dùng thực hiện tác vụ có ý nghĩa.

Ví dụ với đăng ký khóa học:

~~~mermaid
flowchart LR
    A["Học viên xem chỗ trống"] --> B["Chọn và gửi đăng ký"]
    B --> C["Kiểm tra quy tắc và quyền"]
    C --> D["Lưu đăng ký nhất quán"]
    D --> E["Hiển thị kết quả"]
    E --> F["Đo phản hồi / điều chỉnh"]
~~~

Không phải lát cắt nào cũng cần mọi thành phần trong sơ đồ. Phạm vi phụ thuộc kiến trúc và nhu cầu thực tế, nhưng một lát cắt bàn giao phải tạo **hành vi có thể kiểm chứng từ đầu đến cuối**.

### 5.3. Những cách chia lát cắt thường hữu ích

| Cách chia | Lát cắt sớm | Phần để sau |
| --- | --- | --- |
| **Theo hành trình người dùng** | Đăng ký một khóa còn chỗ. | Đổi, hủy, đăng ký hộ. |
| **Theo nhóm đối tượng** | Học viên cá nhân đã đăng nhập. | Quản trị viên đăng ký cho nhiều người. |
| **Theo quy tắc nghiệp vụ** | Đăng ký miễn phí với sức chứa xác định. | Đăng ký cần thanh toán hoặc danh sách chờ. |
| **Theo trường hợp sử dụng** | Đường đi thành công và lỗi bắt buộc để hệ thống đúng. | Những biến thể nâng cao độc lập. |
| **Theo kênh** | Trải nghiệm web được hỗ trợ. | Ứng dụng di động riêng hoặc thông báo đa kênh. |
| **Theo mức độ tự động hóa** | Quy trình cho một nhóm thử nghiệm nhỏ nhưng vận hành an toàn. | Tự động hóa quy mô lớn khi nhu cầu đã được chứng minh. |
| **Theo độ phức tạp tích hợp** | Một tích hợp cần thiết với hợp đồng rõ. | Các tích hợp bổ sung không phục vụ giá trị đầu tiên. |

**Không được chia nhỏ bằng cách bỏ tính đúng đắn, bảo mật, xử lý lỗi cốt lõi hoặc Definition of Done.** Chỉ nên hoãn những khả năng độc lập hoặc trường hợp chưa cần thiết trong phạm vi sử dụng đã công bố. Ví dụ, không thể gọi “đăng ký khóa học” là hoàn tất nếu hai học viên cùng chọn chỗ cuối làm vượt sức chứa.

### 5.4. Kiểm tra điều kiện bàn giao của một lát cắt

Một lát cắt tốt cần:

1. Có người dùng hoặc người kiểm chứng phù hợp.
2. Giải quyết một hành vi/kết quả rõ ràng.
3. Có ranh giới dữ liệu, quyền truy cập và các trường hợp lỗi quan trọng.
4. Tích hợp với sản phẩm hiện tại thay vì chỉ chạy trong môi trường tách biệt.
5. Đáp ứng DoD và tiêu chí chấp nhận.
6. Cho phép nhận phản hồi hoặc xác nhận rủi ro/giả định quan trọng.

Nếu chưa thể tạo lát cắt đủ nhỏ trong khung thời gian, nhóm có thể ưu tiên **khám phá kỹ thuật có timebox** để giảm bất định và cập nhật kế hoạch. Nhưng một spike chỉ đưa ra kiến thức/khuyến nghị **không được mặc nhiên gọi là Increment chức năng của sản phẩm**.

## 6. Tình huống thực tế: lên kế hoạch ngắn hạn cho đăng ký khóa học

### 6.1. Bối cảnh và số liệu giả định

Một nền tảng học trực tuyến cho phép học viên xem danh mục khóa học nhưng đang phải gửi yêu cầu qua nhân viên để đăng ký. Nhóm muốn thử nghiệm tính năng tự đăng ký.

Thông tin ban đầu **chỉ là giả định minh họa**:

- Khoảng 80 yêu cầu đăng ký mỗi tuần đi qua nhân viên.
- Quy trình hiện tại làm học viên chờ phản hồi trong giờ làm việc.
- Chưa rõ học viên có tự hoàn tất tốt nếu cung cấp giao diện trực tuyến.
- Nhóm có khả năng phát triển giao diện, backend, kiểm thử và phối hợp với nghiệp vụ trong hai tuần gần.

Mục tiêu sản phẩm ở cấp rộng hơn là **giảm thao tác thủ công trong quá trình học viên tham gia khóa học**. Nhóm cần chọn bước đủ nhỏ để học sớm.

### 6.2. Viết mục tiêu ngắn hạn

**Mục tiêu gợi ý:**

> Trong vòng làm việc hai tuần, nhóm đưa vào thử nghiệm một luồng đăng ký khóa học miễn phí cho học viên đã đăng nhập, giúp họ tự chọn khóa còn chỗ, đăng ký và nhận kết quả đáng tin cậy. Dùng phản hồi thử nghiệm để quyết định bước cải tiến tiếp theo.

**Ranh giới đã thống nhất:**

- Chỉ hỗ trợ khóa học miễn phí và học viên cá nhân đã đăng nhập.
- Xem số chỗ còn, đăng ký, lưu đúng một đăng ký hợp lệ và hiển thị xác nhận.
- Hết chỗ và đăng ký lặp phải được xử lý đúng.
- Bảo vệ thông tin cá nhân và quyền truy cập theo chính sách.
- Chưa có thanh toán, đăng ký hộ, danh sách chờ và SMS nhắc học.

Mục tiêu đủ cụ thể để hướng dẫn thứ tự công việc, nhưng không khóa vào lựa chọn công nghệ hay một bảng task cố định.

### 6.3. Xác định phần bàn giao và các hạng mục ứng viên

| Ứng viên | Giá trị kỳ vọng | Có cần cho lát cắt đầu tiên? | Quyết định minh họa |
| --- | --- | --- | --- |
| Xem khóa học còn chỗ | Học viên tìm được lựa chọn hợp lệ. | Có | Bao gồm. |
| Gửi và lưu đăng ký an toàn | Học viên hoàn tất thao tác. | Có | Bao gồm. |
| Xử lý đăng ký trùng và tranh chấp chỗ cuối | Bảo vệ tính chính xác. | Có | Bao gồm trong chuẩn chấp nhận/chất lượng. |
| Hiển thị kết quả và lỗi dễ hiểu | Học viên biết đăng ký đã thành công hay chưa. | Có | Bao gồm. |
| Tìm kiếm nâng cao theo nhiều tiêu chí | Giảm thời gian tìm khóa phù hợp. | Không bắt buộc cho thử nghiệm nhỏ. | Hoãn hoặc tách riêng. |
| Thanh toán trực tuyến | Thêm luồng cho khóa trả phí. | Không; ngoài phạm vi lần này. | Backlog tương lai. |
| Nhắc học qua SMS | Giảm khả năng quên lịch. | Không | Backlog, cần khám phá nhu cầu. |

Đây là **lựa chọn phạm vi theo mục tiêu**, không phải đánh giá các khả năng bị hoãn là không quan trọng. Nếu kết quả thử nghiệm cho thấy vấn đề lớn nhất là học viên không tìm thấy khóa phù hợp, thứ tự backlog có thể thay đổi.

### 6.4. User story và ví dụ kiểm chứng

**User story:**

> Là học viên đã đăng nhập, tôi muốn đăng ký một khóa học miễn phí còn chỗ để tham gia học mà không phải nhờ nhân viên hỗ trợ.

Một vài ví dụ có thể dùng để làm rõ tiêu chí chấp nhận:

~~~gherkin
Feature: Học viên tự đăng ký khóa học miễn phí

  Scenario: Đăng ký thành công khi còn chỗ
    Given học viên A đã đăng nhập và chưa đăng ký khóa học X
    And khóa học X còn ít nhất một chỗ
    When A xác nhận đăng ký khóa học X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A thấy thông báo xác nhận thành công

  Scenario: Đăng ký lặp lại không tạo bản ghi trùng
    Given học viên A đã có đăng ký hiệu lực ở khóa X
    When A gửi lại yêu cầu đăng ký cùng khóa X
    Then hệ thống không tạo đăng ký hiệu lực thứ hai
    And A nhận được trạng thái đăng ký hiện tại

  Scenario: Hai học viên chọn chỗ cuối
    Given khóa học X chỉ còn một chỗ
    When hai học viên đủ điều kiện đồng thời xác nhận đăng ký
    Then tối đa một đăng ký mới được xác nhận
    And số đăng ký không vượt sức chứa của X

  Scenario: Học viên không có quyền truy cập
    Given một người dùng không có quyền đăng ký cho học viên A
    When người đó cố thay đổi đăng ký của A
    Then hệ thống từ chối thay đổi
~~~

Đây là **mô tả hành vi bằng ví dụ**. Nó chỉ là kiểm thử tự động sau khi được nối với mã và thực thi trên các tầng kiểm thử phù hợp. Nhóm vẫn phải làm rõ chính sách nghiệp vụ với người có thẩm quyền và kiểm chứng các yêu cầu chất lượng liên quan.

### 6.5. Tạo kế hoạch thực hiện, không cố định mọi việc ngay từ đầu

Một kế hoạch gần có thể là:

| Hoạt động | Mục đích | Tín hiệu hoàn thành |
| --- | --- | --- |
| Làm rõ quy tắc đăng ký và trường hợp đồng thời | Giảm hiểu sai và rủi ro dữ liệu. | Người phụ trách sản phẩm thống nhất ví dụ hành vi. |
| Tạo lát cắt từ giao diện đến dữ liệu | Có một hành vi đầu cuối để kiểm chứng. | Đăng ký thành công qua phiên bản tích hợp. |
| Bổ sung kiểm thử lỗi, quyền truy cập và cạnh tranh | Bảo vệ tính đúng đắn. | Các kiểm thử bắt buộc đáp ứng DoD. |
| Cho nhóm học viên đại diện dùng thử | Kiểm tra giả thuyết giá trị. | Có dữ liệu thao tác, phản hồi và vấn đề còn mở. |
| Xem lại kết quả và backlog | Quyết định đầu tư tiếp vào đâu. | Ưu tiên mới có lý do và bằng chứng. |

Các hoạt động có thể diễn ra xen kẽ; không cần đợi một “giai đoạn phân tích” hoàn toàn kết thúc rồi mới bắt đầu kiểm thử. Ví dụ, nhóm có thể làm rõ quy tắc đồng thời trong lúc triển khai một lát cắt nhỏ, miễn các quyết định quan trọng được xác nhận trước khi phát hành.

### 6.6. Định nghĩa thành công bằng hai lớp bằng chứng

**Lớp A — Bằng chứng bàn giao nằm trong quyền kiểm soát nhóm:**

- Luồng đăng ký đầu cuối hoạt động trong phạm vi thử nghiệm.
- Các tiêu chí chấp nhận và Definition of Done được đáp ứng.
- Không vượt sức chứa, không đăng ký trùng, quyền truy cập được bảo vệ.
- Kết quả được tích hợp, có thể trình diễn và kiểm tra trên môi trường thích hợp.

**Lớp B — Bằng chứng giá trị cần học từ người dùng:**

- Bao nhiêu người dùng thử hoàn tất mà không cần trợ giúp?
- Bước nào gây hiểu nhầm hoặc khiến người dùng bỏ dở?
- Học viên có hiểu tình trạng đăng ký và số chỗ không?
- Nhân viên hỗ trợ có thực sự giảm thao tác trong phạm vi thử nghiệm không?

Nếu chưa có đủ người dùng thử, không nên kết luận mục tiêu kinh doanh đã đạt. Nhóm có thể báo **Increment hoàn tất; giả thuyết giảm thao tác hỗ trợ đang chờ đủ dữ liệu**.

## 7. Gắn mục tiêu ngắn hạn với Scrum

### 7.1. Product Goal, Sprint Goal và Increment

Trong Scrum Guide 2020, có ba cam kết gắn với ba artifact:

| Artifact | Cam kết | Ý nghĩa |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Mô tả trạng thái tương lai mà Scrum Team hướng tới khi cải thiện sản phẩm. |
| **Sprint Backlog** | **Sprint Goal** | Một mục tiêu chung cho Sprint; tạo trọng tâm, sự gắn kết và linh hoạt lựa chọn công việc. |
| **Increment** | **Definition of Done** | Mô tả trạng thái chất lượng cần đáp ứng để phần sản phẩm hoàn tất. |

**Sprint Goal** do Scrum Team cùng tạo trong Sprint Planning. Developers cùng Product Owner xác định các Product Backlog Items có thể hướng tới mục tiêu đó; Developers lập kế hoạch cách thực hiện.

Một Sprint Goal tốt **không chỉ là viết lại danh sách Product Backlog Items**. Nó giải thích lý do nhóm cùng thực hiện những mục đã chọn.

**Ví dụ yếu:**

> “Hoàn thành API đăng ký, giao diện đăng ký, bảng dữ liệu và trang email.”

**Ví dụ có trọng tâm:**

> “Học viên thử nghiệm có thể tự đăng ký khóa học miễn phí còn chỗ và nhận được xác nhận đáng tin cậy.”

Nếu phát hiện email tự động không cần cho lần thử nhưng giao diện xác nhận bắt buộc, nhóm có cơ sở thương lượng phạm vi mà vẫn giữ mục tiêu chính.

### 7.2. Trong Sprint, mục tiêu giúp điều chỉnh kế hoạch

Scrum dựa trên kiểm tra và thích ứng. Trong Sprint:

- Không thực hiện thay đổi làm **đe dọa Sprint Goal**.
- Chất lượng **không được giảm**.
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được làm rõ và thương lượng lại với Product Owner khi nhóm học thêm.

Nếu thấy xử lý đăng ký trùng phức tạp hơn dự kiến, Developers cần đánh giá giải pháp và công việc còn lại; cùng Product Owner trao đổi về việc hoãn phần lọc nâng cao hoặc một khả năng không thiết yếu. Không được bỏ kiểm thử đồng thời hoặc tuyên bố Done khi dữ liệu vẫn có thể sai chỉ để kịp ngày kết thúc Sprint.

Nếu Sprint Goal trở nên lỗi thời vì bối cảnh thay đổi, **Product Owner có thẩm quyền hủy Sprint** theo Scrum. Đây là trường hợp đặc biệt, không phải lựa chọn mặc định mỗi khi phát sinh yêu cầu.

### 7.3. Sprint Review và Retrospective phục vụ hai việc khác nhau

- **Sprint Review:** Scrum Team và stakeholder kiểm tra kết quả Sprint, những thay đổi trong môi trường và các cơ hội tiếp theo; Product Backlog có thể được điều chỉnh. Nên trình diễn Increment hoạt động được và thảo luận giá trị, không chỉ báo tỷ lệ task.
- **Sprint Retrospective:** nhóm xem xét chất lượng, hiệu quả và cách cộng tác; chọn cải tiến cho lần làm việc tiếp theo, chẳng hạn giảm thời gian chờ test hoặc cải thiện cách chia user story.

Sprint Review không thay thế việc nhận phản hồi trong Sprint. Nhóm có thể trao đổi với người dùng và kiểm thử ngay khi có phần sản phẩm phù hợp.

### 7.4. Phân biệt kế hoạch Sprint với cam kết bất biến về từng hạng mục

Sprint Goal là cam kết định hướng, còn Sprint Backlog là **kế hoạch được Developers cập nhật trong Sprint**. Product Backlog Item có thể được làm rõ, chia nhỏ hoặc thương lượng về phạm vi theo hiểu biết mới.

Nếu xem mọi ticket đã chọn là cam kết bất biến, nhóm dễ đánh đổi tính đúng đắn hoặc bỏ qua thông tin mới để đóng task. Nếu bỏ mục tiêu chung và chỉ đổi việc theo yêu cầu mới nhất, nhóm dễ mất tập trung. Sprint Goal giúp cân bằng hai nhu cầu này.

## 8. Gắn mục tiêu ngắn hạn với Kanban và luồng liên tục

Kanban thường sử dụng **dòng công việc liên tục** cùng chính sách nhận việc, giới hạn WIP và nhịp xem xét, thay vì bắt buộc mọi công việc phải nằm trong Sprint.

Nhóm vẫn cần mục tiêu gần, ví dụ:

> “Trong vài tuần tới, giảm thời gian học viên chờ xác nhận đăng ký bằng cách đưa luồng tự đăng ký đầu tiên vào dùng thử, đồng thời giữ số lỗi đăng ký trùng ở mức chấp nhận được theo tiêu chuẩn đã thống nhất.”

Để biến mục tiêu thành dòng công việc, nhóm có thể:

1. Xếp backlog theo giá trị, rủi ro, phụ thuộc và tính cấp thiết.
2. Làm rõ chính sách **Ready** cho hạng mục có thể bắt đầu.
3. Chia công việc thành lát cắt đủ nhỏ để hoàn tất.
4. Duy trì **WIP limit** để tránh mở quá nhiều việc.
5. Dùng cơ chế **pull**: nhận việc khi có năng lực, ưu tiên hoàn tất việc đang làm.
6. Theo dõi cycle time, work item age, throughput và phản hồi sản phẩm.
7. Rà soát thứ tự ưu tiên và mục tiêu khi dữ liệu cho thấy cần điều chỉnh.

Ví dụ workflow:

~~~mermaid
flowchart LR
    A["Ý tưởng / Backlog"] --> B["Đủ rõ để làm"]
    B --> C["Đang phát triển"]
    C --> D["Kiểm thử / Review"]
    D --> E["Done theo chính sách"]
    D --> C
    E --> F["Phản hồi và đo kết quả"]
    F -. "Điều chỉnh ưu tiên" .-> A
~~~

Các trạng thái chỉ là minh họa. Nhóm cần quy định điểm bắt đầu/kết thúc, cách thể hiện việc bị chặn, điều kiện chuyển trạng thái và khi nào được coi là Done. Một item chờ kiểm thử **vẫn là công việc chưa hoàn tất**, dù mã đã được viết xong.

### 8.1. Không biến mục tiêu ngắn hạn thành danh sách “phải kéo hết”

Trong Kanban, backlog có thể chứa nhiều mục giá trị, nhưng hệ thống làm việc bị giới hạn bởi năng lực và WIP. Nếu có ba hạng mục đang chờ tích hợp, mở thêm năm hạng mục mới chỉ để mọi thành viên bận rộn có thể kéo dài thời gian bàn giao.

Nhóm nên xem lại **việc nào gần hoàn tất, trở ngại nào đang chặn giá trị và đâu là lát cắt nhỏ nhất còn thiếu** để có kết quả có thể kiểm chứng.

## 9. Vai trò của thực hành kỹ thuật XP và Definition of Done

Một mục tiêu ngắn hạn chỉ hữu ích nếu nhóm có khả năng tạo Increment đáng tin cậy. Những thực hành thường gắn với **Extreme Programming (XP)** giúp giảm thời gian phản hồi kỹ thuật:

- **Tích hợp liên tục:** thay đổi được tích hợp và kiểm tra thường xuyên, hạn chế phát hiện lỗi tích hợp muộn.
- **Kiểm thử tự động:** phản hồi về hành vi cốt lõi và hồi quy; lựa chọn mức test phù hợp với rủi ro.
- **Test-driven development (TDD) khi phù hợp:** làm rõ hành vi qua chu kỳ test–code–refactor, nhưng không thay thế kiểm thử tích hợp và đánh giá nghiệp vụ.
- **Pair programming và review mã:** chia sẻ hiểu biết, kiểm tra giải pháp và phát hiện rủi ro sớm.
- **Refactoring có kiểm thử bảo vệ:** giữ thiết kế dễ thay đổi khi yêu cầu tiến hóa.
- **Cộng tác gần với người hiểu nghiệp vụ:** làm rõ quy tắc và trường hợp biên trước khi sai lệch lan rộng.

**Definition of Done** nên phản ánh các tiêu chuẩn cần thiết cho sản phẩm: hành vi được kiểm chứng, mã được tích hợp, yêu cầu bảo mật/quyền truy cập phù hợp, tài liệu chịu tác động được cập nhật và không còn lỗi nghiêm trọng vi phạm chính sách hoàn tất.

### 9.1. Ví dụ DoD cho luồng đăng ký

Đây là một ví dụ để nhóm thảo luận, không phải bộ tiêu chuẩn áp dụng cho mọi dự án:

- [ ] Tiêu chí chấp nhận quan trọng được xác nhận với Product Owner/người có thẩm quyền.
- [ ] Luồng giao diện → API → dữ liệu hoạt động trong môi trường tích hợp phù hợp.
- [ ] Không phát sinh đăng ký trùng, không vượt sức chứa khi yêu cầu cạnh tranh.
- [ ] Các kiểm thử bắt buộc chạy đạt; lỗi nghiêm trọng được xử lý theo chính sách.
- [ ] Quyền truy cập và thông tin cá nhân được kiểm tra phù hợp rủi ro.
- [ ] Hướng dẫn, hợp đồng API hoặc tài liệu vận hành chịu tác động đã cập nhật.
- [ ] Increment tích hợp với phiên bản trước và có thể sử dụng trong phạm vi đã công bố.

Nếu phần mềm chưa đáp ứng DoD, cần công khai rằng phần việc **chưa Done** và điều chỉnh kế hoạch phù hợp. Không nên tự ý giảm chất lượng để báo đã đạt mục tiêu ngắn hạn.

## 10. Dự báo năng lực và quản lý bất định

### 10.1. Forecast không phải lời bảo đảm mọi việc đều xong

Khi lập kế hoạch ngắn hạn, nhóm cần dự báo xem công việc nào **có khả năng hoàn tất** với năng lực hiện tại. Dự báo nên dựa vào dữ liệu gần đây, độ phức tạp, số thành viên sẵn sàng, phụ thuộc, kiểm thử và mức độ bất định.

Ví dụ minh họa: trong vài chu kỳ gần đây, nhóm thường hoàn tất **3–5 hạng mục có kích thước tương đương** mỗi hai tuần, với những điều kiện phối hợp tương tự. Một kế hoạch gồm 12 hạng mục cùng lúc có thể cần được chia nhỏ, đổi thứ tự hoặc xem xét lại. Con số 3–5 là **quan sát giả định trong ví dụ**, không phải mức năng suất chuẩn.

Không nên biến số item, story point hoặc giờ công thành công thức chắc chắn. Hai item cùng tên “user story” có thể khác nhau đáng kể về rủi ro và độ phức tạp. Lượng thời gian làm việc cũng không đồng nghĩa với thời gian có thể hoàn tất nếu phải chờ phê duyệt và tích hợp.

### 10.2. Dự báo nên kèm giả định và giới hạn

Một dự báo hữu ích có thể ghi:

| Nội dung | Ví dụ |
| --- | --- |
| **Mục tiêu** | Đưa luồng tự đăng ký khóa miễn phí vào dùng thử. |
| **Phần bàn giao dự kiến** | Xem chỗ, đăng ký, chống trùng, xác nhận và kiểm thử bắt buộc. |
| **Điều kiện** | Có tài khoản sandbox, Product Owner xác nhận quy tắc đăng ký. |
| **Rủi ro chính** | Cơ chế cạnh tranh chỗ cuối phức tạp hơn dự kiến. |
| **Cách giảm rủi ro** | Thử nghiệm giao dịch đồng thời và kiểm tra hợp đồng API sớm. |
| **Điều có thể hoãn** | Bộ lọc nâng cao, SMS nhắc học và dashboard. |
| **Bằng chứng hoàn tất** | Increment đáp ứng DoD, được nhóm thử nghiệm kiểm chứng. |
| **Điểm kiểm tra** | Khi kết quả thử nghiệm kỹ thuật hoặc phản hồi người dùng đầu tiên có sẵn. |

Điều kiện và giả định nên hiển thị với người liên quan. Nếu một phụ thuộc quan trọng không được đáp ứng, nhóm cần cập nhật dự báo sớm, tránh giữ một ngày giao không còn căn cứ.

### 10.3. Kiểm soát phạm vi thay đổi khi đang thực hiện

Giữa vòng làm việc, có thể xuất hiện yêu cầu mới như thanh toán trực tuyến hoặc nhắc học qua SMS. Cần phân biệt:

- **Làm rõ hành vi đã thống nhất:** như xác định đúng cách xử lý bấm đăng ký nhiều lần.
- **Khắc phục lỗi/đáp ứng DoD:** như sửa dữ liệu lưu trùng hoặc lỗ hổng quyền truy cập.
- **Mở rộng khả năng sản phẩm:** như thêm đăng ký hộ hoặc thanh toán.
- **Thay đổi giải pháp kỹ thuật:** như sửa cơ chế giao dịch để đúng hành vi cũ.

Một yêu cầu mở rộng có thể rất có giá trị, nhưng nên được **đánh giá và sắp xếp ưu tiên minh bạch**. Nếu chọn làm ngay, nhóm cần thương lượng xem điều gì được hoãn hoặc thay thế, cùng tác động lên mục tiêu, chất lượng và phụ thuộc.

## 11. Đo lường tiến độ theo giá trị và luồng giao hàng

Không nên đánh giá tiến độ chỉ bằng phần trăm ticket hoàn tất hoặc số dòng mã được viết. Nhóm cần biết **đã có phần giá trị nào dùng được, quá trình giao có ổn định không và người dùng có đạt kết quả tốt hơn không**.

| Nhóm tín hiệu | Câu hỏi | Ví dụ | Giới hạn diễn giải |
| --- | --- | --- | --- |
| **Khả năng đã hoàn tất** | Sản phẩm đã làm được thêm gì? | Luồng đăng ký đầu cuối đáp ứng DoD. | Chưa tự chứng minh lợi ích thực tế nếu chưa được sử dụng. |
| **Kết quả người dùng** | Người dùng làm tốt hơn điều gì? | Tỷ lệ học viên tự đăng ký thành công. | Cần đủ dữ liệu và xem xét yếu tố ngoài sản phẩm. |
| **Thời gian phản hồi** | Mất bao lâu từ ý tưởng đến lúc kiểm chứng giả thuyết? | Thời gian từ chọn lát cắt đến thử với học viên. | Nhanh nhưng dữ liệu sai đối tượng không giúp học đúng. |
| **Cycle time** | Một hạng mục mất bao lâu từ lúc bắt đầu xử lý đến khi hoàn tất? | Thời gian làm của từng lát cắt. | Mốc bắt đầu/kết thúc phải được định nghĩa nhất quán. |
| **Lead time** | Từ điểm yêu cầu/tiếp nhận đã thống nhất đến giao/hoàn tất mất bao lâu? | Thời gian học viên hoặc Product Owner chờ hạng mục. | Có thể gồm nhiều khoảng chờ trước khi bắt đầu làm. |
| **WIP / work item age** | Có quá nhiều việc dở dang hoặc việc mắc kẹt không? | Ba item ở cột kiểm thử nhiều ngày. | Hỏi nguyên nhân trước khi thay đổi WIP limit. |
| **Throughput** | Có bao nhiêu hạng mục Done trong khoảng thời gian? | Số lát cắt hoàn tất mỗi tuần. | Không đo trực tiếp giá trị; phụ thuộc cách chia việc. |
| **Chất lượng** | Increment có đáng tin cậy không? | Lỗi sau phát hành, thất bại triển khai, sự cố dữ liệu. | Không đánh đổi lỗi nghiêm trọng để tăng tốc độ. |

### 11.1. Ví dụ đo kết quả mà không hứa quá mức

Giả sử trước thử nghiệm, toàn bộ đăng ký do nhân viên thực hiện. Sau khi mở luồng mới cho một nhóm nhỏ, **30 người** đủ điều kiện được mời dùng thử và **21 người** tự hoàn tất đăng ký không cần trợ giúp.

\[
\text{Tỷ lệ hoàn tất trong nhóm thử}=\frac{21}{30}\times 100\%=70\%.
\]

Kết quả 70% là **số liệu minh họa**, chỉ mô tả nhóm 30 người trong ví dụ. Nó chưa chứng minh hệ thống sẽ có 70% hoàn tất ở mọi nhóm người dùng hoặc rằng tính năng mới là nguyên nhân duy nhất của thay đổi. Nhóm cần xem những người chưa hoàn tất gặp trở ngại gì và xác định cải tiến có giá trị nhất.

Một mục tiêu ngắn hạn tốt giúp nhóm **có cơ hội nhận được dữ liệu này sớm**, thay vì chờ làm xong nhiều tính năng phụ trợ mới bắt đầu thử nghiệm.

### 11.2. Báo cáo trạng thái nên nêu bằng chứng và điều chưa biết

Thay vì:

> “Sprint hoàn thành 75%, đã đóng 15 task.”

Có thể nêu:

> “Luồng đăng ký từ giao diện đến dữ liệu đã chạy và đáp ứng các kiểm thử chính. Kiểm thử hai yêu cầu tranh chỗ cuối còn đang chờ môi trường tích hợp, nên Increment chưa đáp ứng đầy đủ DoD. Nhóm đang phối hợp mở quyền sandbox; phần lọc nâng cao được hoãn để giữ mục tiêu đăng ký đáng tin cậy.”

Cách báo cáo này cho người liên quan biết **giá trị đã có, giới hạn hiện tại và quyết định tiếp theo**. Nó giúp điều chỉnh kế hoạch dựa trên thực tế.

## 12. Khi kế hoạch ngắn hạn không đi như dự kiến

Lập kế hoạch thích ứng không có nghĩa là “muốn đổi thế nào cũng được”. Khi gặp dữ liệu trái dự đoán, nhóm nên phân loại để xử lý có trách nhiệm:

| Tình huống | Câu hỏi kiểm tra | Hành động tham khảo |
| --- | --- | --- |
| **Phát hiện yêu cầu khó hơn dự kiến** | Có thể chia nhỏ mà vẫn giữ hành vi đúng và chất lượng? | Thử phương án kỹ thuật nhỏ, thương lượng hoãn khả năng phụ. |
| **Phụ thuộc ngoài nhóm bị chậm** | Có thể tạo hợp đồng, test double, hoặc xử lý việc độc lập trong giới hạn WIP? | Phối hợp người có thẩm quyền, cập nhật dự báo sớm. |
| **Phản hồi cho thấy giả thuyết sai** | Giá trị nào không được chứng minh? | Điều chỉnh mục tiêu/ưu tiên giai đoạn tiếp theo, cân nhắc dừng đầu tư. |
| **Phát hiện vấn đề an toàn hoặc dữ liệu** | Có chính sách ứng cứu, kiểm soát bắt buộc nào? | Ưu tiên xử lý theo mức nghiêm trọng, không bỏ qua để kịp Sprint. |
| **Mục tiêu gồm quá nhiều khả năng** | Kết quả cốt lõi là gì, lát cắt nhỏ nhất tạo giá trị? | Tách tính năng độc lập, sắp xếp lại backlog. |
| **Nhóm hoàn tất việc nhưng chưa có phản hồi** | Cần người dùng, môi trường hoặc cách đo nào? | Lập bước kiểm chứng giá trị tiếp theo, tránh suy đoán thành công. |

Trong Scrum, những thay đổi trong Sprint phải bảo vệ Sprint Goal và không hạ chất lượng; phạm vi được làm rõ/thương lượng theo quy định. Trong Kanban, nhóm điều chỉnh thứ tự nhận việc, chính sách luồng và WIP dựa trên bằng chứng. Với cả hai, **kế hoạch nên công khai sự bất định và lý do thay đổi**, thay vì âm thầm đổi cam kết.

### 12.1. Khi chưa thể có tính năng bàn giao ngay

Có những giai đoạn bắt buộc tập trung vào hạ tầng, nâng cấp tương thích hoặc khám phá rủi ro. Nhóm có thể đặt **mục tiêu học hỏi ngắn hạn có kiểm chứng**:

> “Trong tuần này, xác minh cơ chế đăng ký đồng thời có thể giữ số chỗ nhất quán ở mức tải dự kiến và chọn phương án triển khai dựa trên kết quả.”

Sản phẩm của hoạt động có thể là **kết quả thử nghiệm, quyết định kiến trúc và kiểm thử tái hiện được**. Cần báo cáo đúng bản chất của nó: bước khám phá hỗ trợ quyết định tiếp theo, **không tự nhận đó là Increment chức năng đã có giá trị sử dụng trực tiếp**.

Ngay sau khi giảm được bất định, nhóm nên tìm cách quay lại các lát cắt có thể bàn giao, tránh kéo dài nghiên cứu mà không gắn với mục tiêu sản phẩm.

## 13. Những phản mẫu làm kế hoạch thiếu thích ứng

| Phản mẫu | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| **Mục tiêu là danh sách task** | Không biết các phần đã đóng có tạo giá trị chung không. | Mô tả kết quả và hành vi người dùng trước khi chọn việc. |
| **Cam kết kết quả người dùng như một điều nhóm hoàn toàn kiểm soát** | Dễ diễn giải sai khi dữ liệu thực tế khác dự đoán. | Tách cam kết về Increment/DoD khỏi giả thuyết outcome cần đo. |
| **Làm xong từng lớp kỹ thuật nhưng không có luồng dùng được** | Phản hồi đến muộn, rủi ro tích hợp lớn. | Chia lát cắt dọc và tích hợp thường xuyên. |
| **Thêm mọi yêu cầu mới vào cùng Sprint/hạng mục** | Scope creep, WIP tăng, ít việc Done. | Thương lượng thứ tự/đánh đổi; tách khả năng độc lập vào backlog. |
| **Hạ tiêu chuẩn kiểm thử để kịp ngày giao** | Đánh dấu hoàn tất sai và gây lỗi về sau. | Bảo vệ DoD, giảm phạm vi tùy chọn hoặc cập nhật dự báo. |
| **Lấy story point/ticket làm thước đo giá trị** | Tập trung sản xuất số liệu thay vì kết quả. | Theo dõi Increment, outcome và chất lượng. |
| **Chọn mục tiêu quá lớn trong khoảng ngắn** | Không thể bàn giao gì có ích, dự báo kém. | Tìm hành vi nhỏ nhất có giá trị và có thể kiểm chứng. |
| **Kế hoạch cố định dù phản hồi đã thay đổi** | Tiếp tục làm những điều ít giá trị. | Rà soát backlog và mục tiêu ở nhịp phù hợp. |
| **Bắt đầu quá nhiều việc để ai cũng bận** | Chuyển ngữ cảnh, tắc nghẽn, thời gian hoàn tất dài. | Giới hạn WIP, ưu tiên hoàn tất lát cắt. |
| **Chỉ demo giao diện hoặc mock rồi tuyên bố Done** | Bên liên quan hiểu nhầm khả năng thực tế. | Phân biệt prototype với Increment tích hợp đáp ứng DoD. |
| **Không nêu phụ thuộc và giả định dự báo** | Bất ngờ khi không thể tích hợp hoặc lấy phản hồi. | Công bố điều kiện, rủi ro và mốc kiểm tra. |

## 14. Bài tập thực hành

### Bài tập 1 — Viết lại mục tiêu theo giá trị

Một nhóm nhận danh sách:

- Tạo API đăng ký.
- Thiết kế form.
- Thêm bảng dữ liệu.
- Gửi email xác nhận.
- Viết dashboard quản lý.

**Yêu cầu:** viết một mục tiêu ngắn hạn có trọng tâm cho một vòng hai tuần; chọn phần có thể bàn giao và nêu hai hạng mục có thể hoãn.

**Gợi ý:**

> “Học viên thử nghiệm có thể tự đăng ký một khóa miễn phí còn chỗ và nhận xác nhận chính xác.”

Lát cắt cần giao diện, nghiệp vụ, dữ liệu và kiểm thử phù hợp; dashboard quản lý và email tự động có thể được đánh giá, hoãn nếu không bắt buộc cho mục tiêu hoặc các nghĩa vụ hiện tại. Không được bỏ kiểm tra chống trùng hoặc quyền truy cập chỉ để giảm công sức.

### Bài tập 2 — Phân biệt Increment và tiến độ kỹ thuật

Cho ba tình huống:

1. Backend đã viết xong API tạo đăng ký, test đơn vị đạt, giao diện chưa tích hợp.
2. Giao diện đang dùng dữ liệu giả để trình diễn luồng đăng ký; chưa lưu được thông tin.
3. Học viên thực hiện đăng ký đầu cuối trên môi trường tích hợp, dữ liệu đúng, các kiểm thử bắt buộc và DoD đạt.

**Câu hỏi:** tình huống nào chứng minh có Increment chức năng dùng được? Những tình huống còn lại tạo bằng chứng gì và cần gì để tiến tới Done?

**Hướng trả lời:** tình huống 3 phù hợp để coi là Increment trong phạm vi đã nêu. Tình huống 1 chứng minh tiến độ thành phần; tình huống 2 có thể là nguyên mẫu hữu ích để thu phản hồi trải nghiệm. Cả hai chưa chứng minh hành vi sản phẩm tích hợp và đạt DoD.

### Bài tập 3 — Điều chỉnh kế hoạch khi phát hiện phụ thuộc

**Bối cảnh:** giữa vòng làm việc, nhóm phát hiện API kiểm tra quyền học viên của đội khác chưa sẵn sàng. Đây là điều kiện bắt buộc của luồng tự đăng ký.

Hãy đề xuất:

1. Cách mô tả ảnh hưởng đến mục tiêu, Increment và DoD.
2. Người/vai trò cần phối hợp để làm rõ hợp đồng và thời điểm.
3. Phần việc nào có thể làm song song an toàn.
4. Điều kiện để gọi blocker đã được gỡ.
5. Khi nào cần trao đổi lại về phạm vi hoặc dự báo.

**Gợi ý:** dùng contract test với hợp đồng được thống nhất và test double cho phần độc lập; không gọi kiểm thử giả lập là bằng chứng tích hợp hoàn tất. Liên hệ chủ sở hữu API sớm, cập nhật tình trạng và thảo luận phạm vi phụ với Product Owner nếu mục tiêu bị ảnh hưởng.

### Bài tập 4 — Chọn lát cắt đầu tiên cho hệ thống hỗ trợ khách hàng

Giả sử nhóm muốn giảm thời gian khách theo dõi yêu cầu hỗ trợ. Backlog gồm: tạo ticket, xem trạng thái, upload tệp, chat trực tiếp, báo cáo SLA và tích hợp ba kênh thông báo.

Hãy xác định:

- Một kết quả người dùng ngắn hạn có thể kiểm chứng.
- Một lát cắt từ đầu đến cuối có thể bàn giao.
- Những khả năng nên hoãn.
- Tiêu chí chấp nhận và DoD quan trọng.
- Chỉ số phản hồi để xem mục tiêu có hữu ích không.

**Gợi ý:** thử “khách tạo yêu cầu và tra cứu trạng thái đã được ghi nhận” trước; giữ quy tắc quyền truy cập và dữ liệu đúng, hoãn các kênh/phân tích nâng cao nếu độc lập. Sau khi bàn giao, đo số lần khách phải liên hệ để hỏi tiến độ.

### Bài tập 5 — Dự báo theo dữ liệu, không đếm hạng mục một cách máy móc

Một nhóm có dữ liệu minh họa từ bốn vòng hai tuần gần nhất: **3, 4, 3, 5** hạng mục tương đương được hoàn tất, nhưng Sprint sắp tới có một thành viên nghỉ phép và một API mới chưa được xác nhận.

**Câu hỏi:**

1. Có nên cam kết chắc chắn hoàn tất sáu hạng mục không?
2. Thông tin nào cần thu thập trước khi dự báo?
3. Mục tiêu và lát cắt nào phải bảo vệ?
4. Nếu muốn tăng tính chắc chắn, cần chia nhỏ hoặc giảm phụ thuộc thế nào?

**Hướng trả lời:** dữ liệu cũ chỉ là đầu vào dự báo; giảm năng lực và rủi ro API làm độ chắc chắn thấp hơn. Nên xem loại hạng mục, work item age, phụ thuộc và khả năng hoàn tất một lát cắt có giá trị trước khi nhận thêm việc.

## 15. Checklist trước khi chốt kế hoạch ngắn hạn

- [ ] Mục tiêu gắn với một vấn đề/người dùng/kết quả rõ, không chỉ là danh sách task.
- [ ] Có một phần giá trị bàn giao hoặc giả thuyết cần kiểm chứng phù hợp khung thời gian.
- [ ] Phần bàn giao được chia thành lát cắt có thể sử dụng từ đầu đến cuối.
- [ ] Phạm vi bao gồm các trường hợp lỗi và chất lượng bắt buộc; phần hoãn đã được nêu.
- [ ] Tiêu chí chấp nhận và Definition of Done được hiểu rõ.
- [ ] Những rủi ro kỹ thuật, nghiệp vụ, bảo mật và phụ thuộc lớn đã được nhận diện.
- [ ] Dự báo dựa vào năng lực thực tế và ghi rõ giả định quan trọng.
- [ ] Đã thống nhất cách xử lý yêu cầu phát sinh và người có quyền ưu tiên.
- [ ] Workflow/WIP cho phép nhóm tập trung hoàn tất thay vì mở quá nhiều việc.
- [ ] Có người dùng, môi trường hoặc dữ liệu để thu phản hồi sau khi giao.
- [ ] Có chỉ số phản ánh cả chất lượng bàn giao lẫn kết quả sử dụng.
- [ ] Có thời điểm xem lại mục tiêu và cập nhật backlog khi nhận thông tin mới.

Không cần biến checklist thành thủ tục kéo dài cho mọi thay đổi nhỏ. Nhóm nên chọn mức chi tiết tương xứng với rủi ro và giá trị, giữ trọng tâm ở **khả năng giao sản phẩm đáng tin cậy và học hỏi sớm**.

## 16. Ghi nhớ

**Mục tiêu ngắn hạn** trả lời nhóm muốn tạo ra hoặc kiểm chứng thay đổi có ích nào trong khoảng thời gian gần. **Phần giá trị có thể bàn giao** là hành vi sản phẩm đủ nhỏ để hoàn tất, tích hợp, kiểm tra và đưa vào sử dụng trong phạm vi dự định. **Kế hoạch thích ứng** là cách liên tục điều chỉnh thứ tự và cách thực hiện dựa trên rủi ro, năng lực, phụ thuộc và phản hồi.

Nhóm Agile không cần biết mọi chi tiết từ ngày đầu, nhưng cần nêu rõ **vì sao đang làm, điều gì phải đúng, kết quả nào có thể kiểm chứng và quyết định nào sẽ thay đổi khi học thêm**. Scrum cung cấp Sprint Goal và Increment để kiểm tra–thích ứng theo timebox; Kanban giúp quản lý luồng liên tục và WIP; XP giúp bảo đảm những Increment nhỏ vẫn có chất lượng.

Một kế hoạch tốt có thể thay đổi chi tiết mà vẫn **giữ mục tiêu có giá trị, minh bạch sự đánh đổi và tránh tuyên bố hoàn tất khi phần mềm chưa đáp ứng chuẩn chất lượng**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa ngắn |
| --- | --- |
| **Short-term goal** | Mục tiêu gần, có trọng tâm và có thể kiểm chứng trong một nhịp làm việc. |
| **Outcome** | Thay đổi ở hành vi hoặc lợi ích của người dùng/tổ chức sau khi sử dụng sản phẩm. |
| **Output** | Sản phẩm hay đầu ra cụ thể của hoạt động phát triển. |
| **Increment** | Phần sản phẩm tăng thêm được tích hợp, có thể sử dụng và đáp ứng DoD. |
| **Vertical slice** | Lát cắt hành vi đi qua những thành phần cần thiết để tạo khả năng sử dụng từ đầu đến cuối. |
| **Product Goal** | Cam kết về mục tiêu trạng thái tương lai của sản phẩm trong Scrum. |
| **Sprint Goal** | Cam kết về một mục tiêu chung của Sprint, cho phép linh hoạt cách thực hiện. |
| **Sprint Backlog** | Sprint Goal, các Product Backlog Items được chọn và kế hoạch thực hiện của Developers. |
| **Definition of Done (DoD)** | Tiêu chuẩn chất lượng chung để xác định Increment hoàn tất. |
| **Rolling-wave planning** | Lập kế hoạch gần chi tiết hơn xa, cập nhật theo hiểu biết mới. |
| **Forecast** | Dự báo những gì có khả năng hoàn thành dựa trên bằng chứng và giả định. |
| **Work in Progress (WIP)** | Những hạng mục đã bắt đầu nhưng chưa hoàn tất. |
| **Cycle time / Lead time** | Các cách đo thời gian xử lý và thời gian chờ/giao theo mốc được định nghĩa rõ. |
| **Spike** | Hoạt động khám phá/kiểm chứng được giới hạn để giảm bất định trước quyết định. |
