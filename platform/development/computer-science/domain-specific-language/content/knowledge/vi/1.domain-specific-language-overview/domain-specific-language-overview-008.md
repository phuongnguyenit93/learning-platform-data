# Lợi ích và giới hạn của ngôn ngữ đặc tả miền (DSL)

Ngôn ngữ đặc tả miền (*Domain-Specific Language*, viết tắt là DSL) được thiết kế để diễn đạt một nhóm vấn đề thuộc một lĩnh vực cụ thể. SQL tập trung vào truy vấn dữ liệu, biểu thức chính quy tập trung vào mô tả mẫu văn bản, CSS mô tả cách trình bày giao diện, còn các ngôn ngữ cấu hình hạ tầng mô tả trạng thái mong muốn của hệ thống. Mỗi ngôn ngữ đều cung cấp một tập từ vựng, quy tắc và cách biểu đạt phù hợp với công việc mà nó hướng đến.

DSL có thể giúp một nhóm làm việc diễn đạt ý định ngắn gọn, nhất quán và gần với khái niệm nghiệp vụ. Tuy nhiên, một ngôn ngữ chuyên biệt cũng tạo ra chi phí thiết kế, học tập, bảo trì và tích hợp. DSL không tự động làm cho phần mềm tốt hơn; giá trị của nó phụ thuộc vào mức độ phù hợp giữa ngôn ngữ, miền bài toán và cách tổ chức hệ thống.

## 1. DSL giải quyết vấn đề gì?

Một ngôn ngữ lập trình đa dụng (*General-Purpose Language*, GPL) như Java, C# hoặc Python có thể được dùng để xây dựng nhiều loại ứng dụng. Tính đa dụng này đem lại sự linh hoạt, nhưng đôi khi khiến một thao tác trong một miền cụ thể phải được diễn đạt bằng nhiều cấu trúc tổng quát.

DSL thu hẹp phạm vi biểu đạt để tập trung vào một miền. Thay vì yêu cầu người viết mô tả từng bước máy tính phải thực hiện, DSL có thể cho phép họ mô tả trực tiếp điều cần đạt được bằng khái niệm của miền đó.

Ví dụ, một truy vấn SQL diễn đạt tập dữ liệu cần lấy:

~~~sql
SELECT customer_id, SUM(amount) AS total_spent
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) > 1000000;
~~~

Đoạn SQL mô tả các điều kiện lọc, phép nhóm và phép tổng hợp. Người viết không phải tự cài đặt vòng lặp, cấu trúc nhóm hay thuật toán cộng từng phần tử. Hệ quản trị cơ sở dữ liệu chịu trách nhiệm lựa chọn cách thực thi phù hợp.

Nếu dùng một ngôn ngữ đa dụng để tự xử lý dữ liệu, lập trình viên có thể phải viết nhiều mã hơn để biểu diễn cùng một ý định. Điều đó không có nghĩa SQL luôn là lựa chọn tốt hơn: khi cần quy trình xử lý phức tạp, thay đổi theo từng bước hoặc tương tác với nhiều dịch vụ, mã đa dụng có thể dễ tổ chức hơn.

Điểm cốt lõi là DSL tạo ra một mức trừu tượng phù hợp với một miền, giúp người viết tập trung vào khái niệm quan trọng của miền đó.

### 1.1. DSL bên ngoài và DSL nhúng

Có hai cách triển khai thường gặp:

| Dạng DSL | Đặc điểm | Ví dụ |
|---|---|---|
| DSL bên ngoài (*external DSL*) | Có cú pháp và thường có bộ phân tích cú pháp riêng, độc lập với ngôn ngữ chủ | SQL, biểu thức chính quy, ngôn ngữ truy vấn hoặc cấu hình chuyên biệt |
| DSL nhúng (*embedded/internal DSL*) | Được xây dựng bằng các cấu trúc của một ngôn ngữ chủ, thường thông qua API, hàm, đối tượng hoặc toán tử | API truy vấn dạng fluent trong Java, DSL định tuyến trong một framework web |

DSL bên ngoài có thể tạo ra cú pháp rất sát với miền nghiệp vụ, nhưng nhóm phát triển phải xây dựng hoặc tích hợp parser, công cụ kiểm tra và hỗ trợ biên tập. DSL nhúng tận dụng compiler, kiểu dữ liệu và hệ sinh thái của ngôn ngữ chủ, nhưng cú pháp bị giới hạn bởi ngôn ngữ đó.

Hai dạng này có cùng mục tiêu: cung cấp cách diễn đạt tập trung vào một miền. Việc chọn dạng nào là một quyết định thiết kế, không phải thước đo chất lượng tuyệt đối.

## 2. Lợi ích của DSL

### 2.1. Diễn đạt gần với ngôn ngữ của miền bài toán

Một DSL tốt dùng các khái niệm mà người làm việc trong miền đã quen thuộc. Người viết có thể đọc một quy tắc và nhận ra ý nghĩa nghiệp vụ mà không phải lần theo nhiều lớp mã kỹ thuật.

Chẳng hạn, trong một hệ thống định giá, các khái niệm như **customerTier**, **discountRate**, **minimumOrderValue** có ý nghĩa trực tiếp với quy tắc bán hàng. Nếu DSL cho phép mô tả điều kiện và hành động bằng những khái niệm này, chuyên gia nghiệp vụ và lập trình viên có thể trao đổi trên cùng một mô hình.

Lợi ích này chỉ xuất hiện khi từ vựng của DSL phản ánh đúng miền. Nếu tên lệnh mơ hồ, thuật ngữ không nhất quán hoặc cú pháp quá khác cách người dùng miền suy nghĩ, DSL có thể làm việc giao tiếp khó hơn.

### 2.2. Biểu đạt ngắn gọn và giảm mã lặp

DSL thường gom các thao tác lặp đi lặp lại vào một cấu trúc có ý nghĩa cao hơn. Người dùng không cần viết lại phần điều phối, kiểm tra hoặc xử lý cơ bản cho từng trường hợp.

Ví dụ, biểu thức chính quy:

~~~regex
^[A-Z]{2}[0-9]{6}$
~~~

diễn đạt một chuỗi gồm hai chữ cái in hoa theo sau bởi sáu chữ số. Với người đã hiểu cú pháp regex, một biểu thức ngắn có thể thay thế nhiều dòng kiểm tra ký tự. Nhưng với người chưa biết regex, chuỗi ký hiệu này khó đọc hơn một hàm kiểm tra được đặt tên rõ ràng.

Do đó, sự ngắn gọn chỉ có ích khi người đọc hiểu được ý nghĩa. Mã ít ký tự hơn không đồng nghĩa với mã dễ hiểu hơn.

### 2.3. Tập trung vào ý định thay vì chi tiết thực thi

DSL có thể cho phép người viết mô tả *muốn điều gì xảy ra* thay vì *phải thực hiện từng bước như thế nào*. Đây là đặc điểm thường thấy ở ngôn ngữ khai báo.

Trong SQL, người viết mô tả kết quả truy vấn. Bộ tối ưu của hệ quản trị cơ sở dữ liệu có thể chọn chỉ mục, thứ tự nối bảng và chiến lược thực thi. Trong công cụ quản lý hạ tầng, người dùng có thể khai báo trạng thái mong muốn; công cụ sẽ tính toán các thay đổi cần thiết để đạt trạng thái đó.

Việc tách ý định khỏi cách thực thi tạo điều kiện để thay đổi thuật toán hoặc tối ưu bên dưới mà không buộc mọi người viết DSL phải thay đổi mã. Tuy vậy, lợi ích này phụ thuộc vào việc bộ thực thi có đủ thông tin và quyền quyết định để chọn cách làm phù hợp.

### 2.4. Giới hạn thao tác và giảm lỗi trong một miền

Một DSL có thể chỉ cung cấp những thao tác hợp lệ đối với miền bài toán. Người dùng không phải tiếp xúc với toàn bộ khả năng của một ngôn ngữ đa dụng, vì vậy phạm vi lỗi có thể được thu hẹp.

Ví dụ, DSL mô tả quy tắc phân quyền có thể chỉ cho phép khai báo vai trò, tài nguyên, hành động và điều kiện. Nếu cú pháp không hỗ trợ thực thi lệnh hệ điều hành hoặc truy cập tệp tùy ý, người viết quy tắc khó vô tình thực hiện những thao tác nằm ngoài mục đích.

Giới hạn ngôn ngữ cũng có thể giúp kiểm tra lỗi sớm. Parser hoặc bộ kiểm tra kiểu có thể phát hiện trường không tồn tại, toán tử không hợp lệ, kiểu dữ liệu không tương thích hoặc cấu trúc thiếu thành phần bắt buộc trước khi chạy.

Tuy nhiên, một DSL có cú pháp hạn chế không tự động an toàn. Bộ thực thi vẫn phải kiểm tra quyền, dữ liệu đầu vào và các điều kiện tại thời điểm chạy. Các giới hạn của ngôn ngữ chỉ là một lớp bảo vệ trong thiết kế tổng thể.

### 2.5. Chuẩn hóa quy tắc và tái sử dụng

Khi nhiều nhóm cùng viết một loại quy tắc, mỗi nhóm có thể tạo ra cách triển khai riêng. Điều này dễ dẫn đến khác biệt về cách xử lý trường hợp biên, cách đặt tên và cách diễn giải chính sách.

Một DSL dùng chung có thể chuẩn hóa:

- Từ vựng và cấu trúc của quy tắc.
- Cách biểu diễn điều kiện, hành động và giá trị.
- Các phép kiểm tra hợp lệ.
- Cách diễn giải và thực thi quy tắc.
- Cách lưu trữ, chia sẻ và kiểm soát phiên bản.

Ví dụ, nếu nhiều dịch vụ cùng sử dụng một DSL về chính sách giảm giá, nhóm phát triển có thể dùng chung parser, bộ kiểm tra và bộ thực thi. Quy tắc cũng có thể được lưu trữ độc lập với mã nguồn của từng dịch vụ.

Tái sử dụng chỉ hiệu quả khi các nhóm thực sự có chung khái niệm và ngữ nghĩa. Nếu mỗi nhóm hiểu một thuật ngữ theo cách khác nhau, một DSL dùng chung có thể che giấu sự khác biệt và tạo ra lỗi khó phát hiện.

### 2.6. Cải thiện trao đổi giữa chuyên gia miền và lập trình viên

Trong nhiều dự án, người hiểu nghiệp vụ và người triển khai kỹ thuật không có cùng nền tảng. Yêu cầu thường phải đi qua tài liệu, cuộc họp và nhiều lớp chuyển đổi trước khi trở thành mã.

DSL có thể đóng vai trò như một ngôn ngữ trung gian. Chuyên gia miền có thể xem xét quy tắc ở dạng gần với nghiệp vụ; lập trình viên có thể xây dựng công cụ phân tích, xác thực và thực thi quy tắc đó.

Ví dụ, một quy tắc vận chuyển có thể được biểu diễn bằng các khái niệm như khu vực giao hàng, trọng lượng tối đa, thời gian dự kiến và phụ phí. Hai bên có thể thảo luận trực tiếp trên các khái niệm này.

Để đạt được lợi ích, DSL phải có tài liệu và ví dụ dễ hiểu. Không nên mặc định rằng chuyên gia nghiệp vụ có thể tự viết hoặc chỉnh sửa DSL chỉ vì cú pháp trông giống ngôn ngữ tự nhiên. Người dùng vẫn cần được hướng dẫn và có công cụ phản hồi lỗi rõ ràng.

### 2.7. Hỗ trợ công cụ hóa và tự động hóa

Khi cấu trúc DSL ổn định, hệ thống có thể phân tích nội dung để tạo ra nhiều kết quả:

- Kiểm tra cú pháp và kiểu dữ liệu.
- Phát hiện quy tắc mâu thuẫn hoặc không thể đạt tới.
- Sinh mã, truy vấn hoặc cấu hình cho hệ thống khác.
- Tạo tài liệu từ định nghĩa có cấu trúc.
- Đề xuất hoàn thành cú pháp trong trình soạn thảo.
- Theo dõi thay đổi và kiểm tra khác biệt giữa các phiên bản.

Chẳng hạn, một DSL mô tả API có thể được dùng để sinh tài liệu, mã client và các kiểm tra hợp đồng. Khi đó, một định nghĩa có cấu trúc trở thành nguồn thông tin chung cho nhiều công đoạn.

Khả năng tự động hóa này phụ thuộc vào chất lượng mô hình và công cụ xung quanh DSL. Một tập lệnh tự phát, không có parser ổn định hoặc không có quy ước rõ ràng sẽ khó tạo ra hệ sinh thái công cụ đáng tin cậy.

## 3. Giới hạn và chi phí của DSL

### 3.1. Phạm vi sử dụng hẹp

DSL được tối ưu cho một miền nên thường không phù hợp với mọi loại công việc. Khi bài toán đi ra ngoài miền đã thiết kế, người dùng có thể không biểu diễn được yêu cầu hoặc phải tạo nhiều cơ chế mở rộng.

Ví dụ, SQL phù hợp với truy vấn và thao tác dữ liệu quan hệ, nhưng không phải lựa chọn tự nhiên để xây dựng giao diện người dùng hay điều phối một quy trình nghiệp vụ dài có nhiều tương tác với dịch vụ bên ngoài.

Một DSL càng chuyên biệt thì càng cần xác định rõ ranh giới miền. Nếu ranh giới này không rõ, ngôn ngữ có thể liên tục được bổ sung tính năng cho các trường hợp ngoại lệ và dần trở thành một ngôn ngữ đa dụng khó kiểm soát.

### 3.2. Chi phí thiết kế và triển khai ban đầu

Tạo một DSL không chỉ là chọn vài từ khóa dễ đọc. Nhóm phát triển cần xác định:

- Các khái niệm cốt lõi và mối quan hệ giữa chúng.
- Cú pháp, quy tắc phân tích và ngữ nghĩa.
- Hệ thống kiểu, giá trị mặc định và cách xử lý lỗi.
- Cách đánh giá hoặc thực thi biểu thức.
- Cách tích hợp với ứng dụng và dữ liệu hiện có.
- Công cụ biên tập, kiểm tra, tài liệu và kiểm thử.

Với DSL bên ngoài, chi phí có thể bao gồm lexer, parser, cây cú pháp trừu tượng (AST), trình kiểm tra ngữ nghĩa và bộ thực thi. Với DSL nhúng, một phần hạ tầng được ngôn ngữ chủ cung cấp, nhưng nhóm phát triển vẫn phải thiết kế API, quy ước sử dụng và cách xử lý lỗi.

Nếu miền bài toán nhỏ, ít thay đổi hoặc chỉ có một vài trường hợp sử dụng, chi phí này có thể lớn hơn lợi ích thu được. Một thư viện có API rõ ràng hoặc một cấu trúc dữ liệu cấu hình đơn giản có thể đáp ứng tốt hơn.

### 3.3. Người dùng phải học thêm một ngôn ngữ

DSL có thể dễ học đối với người am hiểu miền nhưng vẫn đòi hỏi người dùng hiểu cú pháp, ngữ nghĩa và quy tắc đặc thù.

Một nhóm có thể phải duy trì kiến thức về cả ngôn ngữ lập trình chính lẫn DSL. Khi thành viên mới tham gia, họ cần học cách viết, kiểm tra, chạy và gỡ lỗi nội dung DSL. Nếu tài liệu ít hoặc thông báo lỗi khó hiểu, quá trình này có thể làm giảm năng suất.

Các biểu thức ngắn cũng có thể tạo ra cảm giác dễ dùng giả tạo. Chẳng hạn, regex có cú pháp súc tích nhưng một biểu thức dài với nhiều nhóm lồng nhau có thể rất khó bảo trì. Khi đó, chia nhỏ biểu thức, đặt tên cho các phần hoặc dùng một hàm có tên rõ ràng có thể giúp người đọc hiểu tốt hơn.

### 3.4. Khó gỡ lỗi và quan sát quá trình thực thi

Mã DSL thường được phân tích hoặc chuyển đổi trước khi thực thi. Khi kết quả sai, người phát triển có thể phải lần theo nhiều lớp: nội dung DSL, parser, cây cú pháp, bộ kiểm tra, bộ chuyển đổi và hệ thống thực thi.

Thông báo lỗi chung chung như “cấu hình không hợp lệ” không đủ để người dùng tìm nguyên nhân. Một công cụ DSL tốt cần chỉ ra vị trí lỗi, khái niệm liên quan, giá trị được mong đợi và gợi ý cách sửa khi có thể.

Với DSL nhúng, lỗi đôi khi xuất hiện dưới dạng lỗi biên dịch hoặc lỗi kiểu của ngôn ngữ chủ. Điều này giúp tận dụng công cụ sẵn có, nhưng thông báo lỗi có thể phản ánh cấu trúc nội bộ của thư viện thay vì khái niệm mà người dùng DSL đang làm việc.

Khả năng quan sát cũng quan trọng. Nếu DSL kích hoạt nhiều bước xử lý, người vận hành cần biết quy tắc nào được chọn, điều kiện nào đúng hoặc sai và hành động nào đã được thực hiện.

### 3.5. Phụ thuộc vào công cụ và hệ sinh thái

Một DSL có giá trị sử dụng lâu dài thường cần trình soạn thảo, định dạng tự động, kiểm tra cú pháp, hoàn thành mã, tài liệu và công cụ gỡ lỗi. Nếu thiếu các công cụ này, người dùng phải ghi nhớ nhiều quy tắc và tự phát hiện lỗi.

DSL phổ biến có thể được hỗ trợ bởi nhiều IDE, thư viện và cộng đồng. DSL nội bộ của một tổ chức thường có hệ sinh thái nhỏ hơn, phụ thuộc vào nhóm đã tạo ra nó.

Khi nhóm tác giả rời dự án hoặc tổ chức thay đổi kiến trúc, việc duy trì parser và bộ thực thi có thể trở thành gánh nặng. Vì vậy, quyết định tạo DSL cũng là quyết định chịu trách nhiệm duy trì một giao diện ngôn ngữ trong thời gian dài.

### 3.6. Khó kết hợp với các miền và hệ thống khác

Mỗi DSL thường có mô hình dữ liệu, kiểu giá trị và quy tắc riêng. Khi một quy trình cần kết hợp nhiều miền, việc chuyển đổi giữa các mô hình có thể phức tạp.

Ví dụ, một hệ thống có thể dùng DSL để mô tả truy vấn, một DSL khác để mô tả quy tắc nghiệp vụ và một định dạng cấu hình riêng để triển khai. Nếu không có ranh giới và giao diện rõ ràng, nhóm phát triển phải xây dựng nhiều lớp chuyển đổi và đồng bộ.

DSL nhúng có thể dễ tích hợp với ngôn ngữ chủ hơn, nhưng cũng có nguy cơ phụ thuộc chặt vào API hoặc phiên bản của ngôn ngữ đó. DSL bên ngoài có thể độc lập hơn, song cần cơ chế kết nối với mã nguồn, dữ liệu và công cụ triển khai.

### 3.7. Nguy cơ ngữ nghĩa ẩn và hiệu năng khó dự đoán

Một câu lệnh ngắn không nhất thiết tương ứng với một thao tác đơn giản. DSL có thể che giấu truy vấn tốn kém, vòng lặp lớn, thao tác mạng hoặc việc cấp phát tài nguyên.

Ví dụ, một truy vấn SQL dễ đọc vẫn có thể quét toàn bộ bảng nếu thiếu chỉ mục hoặc có điều kiện lọc không phù hợp. Một cấu hình khai báo ngắn có thể kích hoạt nhiều tài nguyên hạ tầng.

Người dùng cần biết chi phí thực thi và có công cụ quan sát phù hợp. Với các DSL cho phép biểu thức tùy ý hoặc mở rộng bằng plugin, việc giới hạn tài nguyên và kiểm soát tác động càng quan trọng.

Ngoài ra, một lớp trừu tượng có thể không che giấu được mọi khác biệt của nền tảng bên dưới. Khi cần tối ưu sâu, người phát triển vẫn phải hiểu cách hệ thống thực thi DSL.

### 3.8. Rủi ro bảo mật khi xử lý đầu vào không tin cậy

DSL thường cho phép người dùng cung cấp biểu thức hoặc quy tắc để hệ thống phân tích và thực thi. Nếu bộ thực thi đánh giá nội dung như mã tùy ý, người dùng có thể tạo ra hành động vượt quá quyền được phép.

Một ví dụ phổ biến là ghép trực tiếp dữ liệu người dùng vào câu lệnh SQL:

~~~java
String sql = "SELECT * FROM users WHERE name = '" + userInput + "'";
~~~

Nếu userInput chứa cú pháp SQL ngoài dự kiến, câu truy vấn có thể bị thay đổi. Cách an toàn hơn là dùng truy vấn tham số hóa:

~~~java
String sql = "SELECT * FROM users WHERE name = ?";
PreparedStatement statement = connection.prepareStatement(sql);
statement.setString(1, userInput);
~~~

Ví dụ này minh họa rằng việc dùng một DSL có sẵn không loại bỏ yêu cầu bảo mật. Hệ thống phải phân biệt cú pháp với dữ liệu, kiểm soát quyền thực thi, giới hạn tài nguyên và xác thực đầu vào theo đúng ngữ cảnh.

Với DSL tự xây dựng, cần tránh thực thi mã tùy ý bằng cơ chế đánh giá biểu thức tổng quát nếu không có sandbox và mô hình quyền phù hợp. Nên cung cấp tập thao tác được cho phép, xác thực kiểu và giới hạn phạm vi tác động.

### 3.9. DSL có thể phát triển thành một ngôn ngữ khó kiểm soát

Khi có nhiều yêu cầu mới, nhóm phát triển thường muốn bổ sung cú pháp cho từng trường hợp. Theo thời gian, DSL có thể tích lũy nhiều từ khóa, quy tắc đặc biệt và ngoại lệ.

Hậu quả có thể gồm:

- Nhiều cách viết khác nhau cho cùng một ý định.
- Quy tắc ưu tiên toán tử hoặc giá trị mặc định khó nhớ.
- Các tính năng tương tác theo cách khó dự đoán.
- Tài liệu và ví dụ không còn phản ánh đầy đủ hành vi.
- Thay đổi nhỏ gây ảnh hưởng đến nội dung cũ.

Một DSL có phạm vi rõ ràng và ngữ nghĩa nhất quán thường dễ duy trì hơn một DSL cố gắng giải quyết mọi nhu cầu.

## 4. So sánh lợi ích và giới hạn

| Khía cạnh | Lợi ích có thể đạt được | Giới hạn hoặc chi phí cần tính đến |
|---|---|---|
| Biểu đạt | Câu lệnh gần với khái niệm của miền, ít mã lặp | Cú pháp chuyên biệt cần thời gian học |
| Năng suất | Tăng tốc các thao tác lặp lại, giảm phần điều phối | Phải đầu tư thiết kế và xây dựng công cụ |
| Độ an toàn | Giới hạn tập thao tác, kiểm tra lỗi theo miền | Bộ thực thi vẫn cần kiểm tra quyền và dữ liệu |
| Giao tiếp | Tạo ngôn ngữ chung giữa chuyên gia miền và lập trình viên | Thuật ngữ không rõ có thể làm hiểu sai yêu cầu |
| Bảo trì | Chuẩn hóa quy tắc và tái sử dụng định nghĩa | Cần quản lý phiên bản và tương thích ngược |
| Hiệu năng | Bộ thực thi có thể tối ưu dựa trên ý định khai báo | Chi phí thực tế có thể bị che giấu hoặc khó dự đoán |
| Tích hợp | Có thể sinh mã, tài liệu và cấu hình từ một mô hình | Phải chuyển đổi khi kết hợp nhiều DSL hoặc hệ thống |
| Mở rộng | Có thể thêm khả năng phù hợp với miền | Tính năng tăng nhanh có thể làm ngôn ngữ phức tạp |

Không có một DSL nào đồng thời tối đa hóa tất cả các khía cạnh. Thiết kế tốt là tìm được sự cân bằng phù hợp với người dùng, miền bài toán và vòng đời của hệ thống.

## 5. Khi nào nên sử dụng DSL?

DSL thường đáng cân nhắc khi một số điều kiện sau xuất hiện cùng lúc:

1. **Miền bài toán đủ rõ:** nhóm có thể xác định các khái niệm, quy tắc và thao tác thường gặp.
2. **Công việc được lặp lại:** nhiều người hoặc nhiều thành phần cần biểu diễn cùng một loại yêu cầu.
3. **Có lợi ích từ ngôn ngữ chung:** chuyên gia miền và lập trình viên cần cùng đọc, trao đổi hoặc kiểm tra quy tắc.
4. **Có thể giới hạn phạm vi:** phần lớn yêu cầu nằm trong tập khái niệm mà DSL hỗ trợ.
5. **Có kế hoạch duy trì:** nhóm có người chịu trách nhiệm về cú pháp, ngữ nghĩa, công cụ và tương thích phiên bản.
6. **Lợi ích dài hạn lớn hơn chi phí:** việc giảm lặp lại, tăng tính nhất quán hoặc hỗ trợ tự động hóa bù đắp được chi phí ban đầu.

Ngược lại, DSL có thể không cần thiết khi bài toán chỉ có một vài trường hợp đơn giản, yêu cầu thay đổi liên tục, không có người duy trì hoặc đã được giải quyết tốt bằng API và cấu trúc dữ liệu hiện có.

### 5.1. Một số lựa chọn thay thế

Trước khi tạo DSL mới, nên xem xét các lựa chọn sau:

| Lựa chọn | Phù hợp khi |
|---|---|
| Hàm hoặc API thông thường | Cần một số thao tác có tên rõ ràng và được gọi từ mã ứng dụng |
| Thư viện có sẵn | Miền bài toán đã có giải pháp ổn định, được hỗ trợ rộng rãi |
| Tệp cấu hình có schema | Cần khai báo dữ liệu và tùy chọn, không cần ngôn ngữ biểu thức phức tạp |
| Mẫu hoặc template | Cần tái sử dụng cấu trúc văn bản hay cấu hình có biến thay thế |
| DSL nhúng | Muốn có cú pháp diễn đạt theo miền nhưng vẫn tận dụng compiler và công cụ của ngôn ngữ chủ |
| DSL bên ngoài | Cần cú pháp độc lập, có thể dùng bởi nhiều ứng dụng hoặc nhóm không cùng ngôn ngữ lập trình |

Không phải mọi tệp cấu hình đều là DSL. Một tệp chỉ chứa các cặp khóa và giá trị có thể là dữ liệu cấu hình. Khi định dạng đó có cú pháp biểu thức, quy tắc điều khiển hoặc ngữ nghĩa riêng để mô tả hành vi trong một miền, nó có thể tiến gần đến một DSL.

## 6. Nguyên tắc thiết kế DSL để giữ được lợi ích

### 6.1. Bắt đầu từ ngôn ngữ và công việc thực tế của miền

Nên thu thập ví dụ từ các tác vụ thường gặp, cách chuyên gia miền gọi tên khái niệm và những trường hợp ngoại lệ quan trọng. Từ đó xác định tập từ vựng tối thiểu cần có.

Không nên bắt đầu bằng việc nghĩ ra nhiều từ khóa rồi tìm nơi sử dụng chúng. DSL nên phản ánh một mô hình miền đã hiểu rõ, thay vì buộc người dùng học một mô hình tùy tiện.

### 6.2. Giữ cú pháp nhỏ và nhất quán

Mỗi cấu trúc nên có một mục đích rõ ràng. Cùng một khái niệm nên được biểu diễn theo cùng một cách; quy tắc ưu tiên, kiểu dữ liệu và giá trị mặc định cần được công bố.

Nếu có nhiều cách viết tương đương, cần cân nhắc liệu sự linh hoạt đó có đem lại giá trị thật hay chỉ làm tăng gánh nặng đọc và bảo trì.

### 6.3. Định nghĩa ngữ nghĩa rõ ràng

Cú pháp trả lời câu hỏi “viết như thế nào”, còn ngữ nghĩa trả lời câu hỏi “cấu trúc đó có nghĩa gì”. Hai phần phải được mô tả tách bạch.

Ví dụ, nếu DSL có biểu thức điều kiện, tài liệu cần nói rõ cách xử lý giá trị rỗng, phép so sánh, chuyển đổi kiểu và thứ tự đánh giá. Những chi tiết tưởng như nhỏ này có thể tạo ra hành vi khác nhau giữa các phiên bản hoặc môi trường.

### 6.4. Đưa lỗi đến gần khái niệm của người dùng

Thông báo lỗi nên chỉ ra vị trí, nguyên nhân và cách khắc phục. Nếu người dùng khai báo một trường không tồn tại, thông báo nên nêu tên trường, đối tượng liên quan và những trường hợp hợp lệ có thể dùng.

Kiểm tra cú pháp sớm, kiểm tra ngữ nghĩa trước khi thực thi và cung cấp ví dụ hợp lệ giúp giảm thời gian tìm lỗi.

### 6.5. Có đường tích hợp với mã đa dụng

DSL không cần giải quyết mọi vấn đề. Nên xác định ranh giới mà DSL chịu trách nhiệm và cách gọi mã thông thường khi cần xử lý trường hợp đặc biệt.

Một cơ chế mở rộng có kiểm soát giúp DSL không phải liên tục bổ sung cú pháp cho mọi tình huống. Tuy nhiên, nếu quá nhiều quy tắc phải thoát ra mã đa dụng, có thể DSL đang có phạm vi hoặc mức trừu tượng chưa phù hợp.

### 6.6. Quản lý phiên bản và khả năng tương thích

Khi DSL được lưu trong cơ sở dữ liệu, kho mã hoặc hệ thống triển khai, nội dung DSL có thể tồn tại lâu hơn phiên bản ứng dụng tạo ra nó. Vì vậy, cần có quy tắc quản lý phiên bản.

Khi thay đổi cú pháp hoặc ngữ nghĩa, nhóm nên xác định:

- Nội dung cũ có tiếp tục chạy được không?
- Có cần công cụ chuyển đổi tự động không?
- Thông báo lỗi có chỉ rõ cú pháp đã lỗi thời không?
- Có thể triển khai nhiều phiên bản trong giai đoạn chuyển tiếp không?
- Cách kiểm thử để phát hiện thay đổi hành vi là gì?

Không nên âm thầm thay đổi ý nghĩa của một cấu trúc đang được sử dụng rộng rãi.

### 6.7. Thiết kế bảo mật và giới hạn tài nguyên

Nếu người dùng có thể cung cấp DSL, cần xem nội dung đó là đầu vào có thể không đáng tin cậy. Bộ phân tích và thực thi phải giới hạn thao tác được phép, xác thực dữ liệu, kiểm tra quyền và giới hạn thời gian hoặc tài nguyên.

Các thao tác có tác động lớn như xóa dữ liệu, thay đổi quyền hoặc tạo tài nguyên nên có cơ chế xác nhận, ghi log và kiểm soát truy cập phù hợp với mức độ rủi ro.

### 6.8. Kiểm thử bằng ví dụ thực tế

Bộ kiểm thử DSL nên bao gồm:

- Ví dụ hợp lệ đại diện cho các tác vụ thường gặp.
- Ví dụ không hợp lệ để kiểm tra thông báo lỗi.
- Trường hợp biên về kiểu, giá trị rỗng và dữ liệu thiếu.
- Kiểm thử tương thích giữa các phiên bản.
- Kiểm thử bảo mật và giới hạn tài nguyên nếu DSL có thực thi hành động.

Ví dụ trong tài liệu cũng nên được chạy tự động khi có thể, nhằm tránh tình trạng tài liệu mô tả cú pháp đã không còn được hỗ trợ.

## 7. Ví dụ quyết định: dùng DSL hay mã đa dụng?

Giả sử một hệ thống cần cho phép quản trị viên định nghĩa điều kiện để áp dụng ưu đãi. Có ba hướng tiếp cận:

**Hướng 1: Viết điều kiện trực tiếp trong mã Java.** Cách này phù hợp khi quy tắc ít, chỉ do lập trình viên quản lý và thay đổi thông qua quy trình phát hành phần mềm. Mã được kiểm tra bởi compiler và có thể tận dụng công cụ gỡ lỗi quen thuộc.

**Hướng 2: Lưu cấu hình có cấu trúc.** Nếu quy tắc chỉ gồm các điều kiện đơn giản như loại khách hàng, giá trị đơn hàng và tỷ lệ giảm giá, một schema JSON hoặc YAML có thể đủ. Cách này tránh phải xây dựng một ngôn ngữ biểu thức đầy đủ.

**Hướng 3: Xây dựng DSL cho quy tắc ưu đãi.** Nếu có nhiều loại điều kiện, nhiều nhóm cùng tạo quy tắc và cần kiểm tra quy tắc độc lập với chu kỳ phát hành ứng dụng, DSL có thể đem lại giá trị. Khi đó, nhóm cần xây dựng parser hoặc DSL nhúng, kiểm tra kiểu, thông báo lỗi, bộ thực thi và cơ chế quản lý phiên bản.

Ví dụ này cho thấy quyết định không nên dựa trên việc DSL có vẻ hiện đại hay linh hoạt. Cần xem ai tạo nội dung, tần suất thay đổi, mức độ phức tạp của quy tắc, yêu cầu an toàn và chi phí duy trì.

## 8. Câu hỏi tự đánh giá

1. Vì sao SQL có thể biểu diễn một truy vấn ngắn gọn hơn việc tự viết vòng lặp xử lý dữ liệu?
2. Một DSL giới hạn tập thao tác có thể giúp giảm lỗi như thế nào? Vì sao điều đó chưa đủ để bảo đảm an toàn?
3. Phân biệt DSL bên ngoài và DSL nhúng. Mỗi dạng có chi phí triển khai nào?
4. Vì sao một biểu thức ngắn chưa chắc dễ đọc hoặc dễ bảo trì?
5. Trong trường hợp nào một tệp cấu hình có schema là đủ, và khi nào cần cân nhắc DSL?
6. Những công cụ nào giúp người dùng DSL phát hiện lỗi và hiểu quá trình thực thi?
7. Vì sao cần quản lý phiên bản khi nội dung DSL được lưu trữ lâu dài?
8. Nếu người dùng có thể nhập biểu thức DSL, hệ thống cần kiểm soát những rủi ro nào?

## Kết luận

DSL giúp diễn đạt vấn đề bằng khái niệm của một miền, giảm phần mã lặp, chuẩn hóa quy tắc và tạo điều kiện cho kiểm tra hoặc tự động hóa. Giá trị rõ nhất xuất hiện khi nhiều người hoặc nhiều thành phần thường xuyên giải quyết cùng một loại vấn đề bằng một mô hình ổn định.

Đổi lại, DSL đòi hỏi chi phí thiết kế, công cụ, đào tạo, bảo mật và bảo trì. Phạm vi quá hẹp có thể gây khó mở rộng; phạm vi quá rộng có thể khiến ngôn ngữ phức tạp và khó kiểm soát. Vì vậy, nên chọn DSL khi lợi ích của cách diễn đạt chuyên biệt đủ lớn so với chi phí vòng đời, đồng thời giữ cú pháp, ngữ nghĩa và ranh giới miền rõ ràng.
