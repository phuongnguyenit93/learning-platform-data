# Đặc trưng của ngôn ngữ chuyên biệt miền (DSL)

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích được ngôn ngữ chuyên biệt miền (Domain-Specific Language, viết tắt là DSL) và phân biệt nó với ngôn ngữ lập trình đa dụng.
- Nhận diện các đặc trưng thường gặp của một DSL qua cú pháp, ngữ nghĩa, phạm vi sử dụng và cách nó mô hình hóa nghiệp vụ.
- Phân biệt DSL bên ngoài với DSL nhúng, đồng thời hiểu rằng DSL có thể mang tính khai báo hoặc mệnh lệnh.
- Đánh giá lợi ích, giới hạn và mức độ phù hợp của DSL đối với một bài toán.

## 1. DSL là gì?

Ngôn ngữ chuyên biệt miền là một ngôn ngữ được thiết kế để mô tả vấn đề hoặc thực hiện công việc trong một lĩnh vực tương đối cụ thể. Lĩnh vực đó có thể là truy vấn dữ liệu, định dạng giao diện, xây dựng phần mềm, mô tả quy trình nghiệp vụ, cấu hình hạ tầng hoặc kiểm thử.

Khác với ngôn ngữ lập trình đa dụng (General-Purpose Language, GPL) như Java, Python hay C#, DSL tập trung vào một nhóm khái niệm và thao tác của miền ứng dụng. Người viết DSL thường diễn đạt trực tiếp điều họ muốn trong miền đó thay vì phải mô tả mọi bước tính toán ở mức thấp.

Một số ví dụ quen thuộc:

| DSL | Miền sử dụng | Điều người viết mô tả |
|---|---|---|
| SQL | Cơ sở dữ liệu quan hệ | Bảng, cột, điều kiện lọc, phép nối và kết quả truy vấn |
| Regular expressions (regex) | Tìm kiếm và kiểm tra chuỗi | Mẫu ký tự cần tìm hoặc cần khớp |
| CSS | Trình bày giao diện web | Bộ chọn phần tử và quy tắc hiển thị |
| HCL trong Terraform | Mô tả hạ tầng | Tài nguyên, cấu hình và quan hệ giữa các thành phần hạ tầng |
| Makefile | Tự động hóa quá trình build | Mục tiêu, phụ thuộc và lệnh cần chạy |

Các ví dụ này có hình thức khác nhau, nhưng đều cung cấp những khái niệm và cấu trúc phù hợp với một loại công việc cụ thể. Chẳng hạn, SQL cho phép mô tả dữ liệu cần lấy và điều kiện truy vấn mà không buộc người viết tự cài đặt thuật toán duyệt từng bản ghi.

Một định dạng dữ liệu hoặc một tệp cấu hình không tự động trở thành DSL chỉ vì nó có cú pháp riêng. Cần xem xét liệu nó có cung cấp ngôn ngữ, quy tắc và khái niệm để diễn đạt các tác vụ của một miền hay không. Ví dụ, YAML chủ yếu là định dạng tuần tự hóa dữ liệu; một hệ thống có thể dùng YAML để biểu diễn một DSL cấu hình chuyên biệt, nhưng bản thân YAML không mặc nhiên là DSL của hệ thống đó.

## 2. Những đặc trưng cốt lõi của DSL

Không có một danh sách hình thức duy nhất mà mọi DSL bắt buộc phải đáp ứng. Tuy vậy, các đặc trưng dưới đây thường được dùng để nhận diện và đánh giá một DSL. Một DSL tốt cần làm cho công việc trong miền của nó rõ ràng, có ý nghĩa và dễ kiểm soát.

### 2.1. Tập trung vào một miền vấn đề cụ thể

Đặc trưng quan trọng nhất là phạm vi ứng dụng có chủ đích. DSL cung cấp cách diễn đạt cho một miền, chẳng hạn truy vấn dữ liệu, thiết kế kiểu chữ và màu sắc, hoặc mô tả luồng xử lý đơn hàng.

Phạm vi hẹp giúp ngôn ngữ có thể dành từ vựng và cấu trúc cho các khái niệm quan trọng trong miền. SQL có các cấu trúc như SELECT, FROM, WHERE và JOIN; regex có các ký hiệu biểu thị lớp ký tự, số lần lặp và nhóm; CSS có bộ chọn, thuộc tính và giá trị.

Giới hạn phạm vi không nhất thiết là nhược điểm. DSL không cần giải quyết mọi loại bài toán. Nó chỉ cần diễn đạt tốt các tác vụ nằm trong phạm vi đã xác định. Khi một yêu cầu vượt khỏi phạm vi đó, hệ thống có thể cần một ngôn ngữ đa dụng hoặc một cơ chế mở rộng.

### 2.2. Sử dụng khái niệm và từ vựng của miền

DSL thường đặt các khái niệm mà người làm việc trong miền đã quen thuộc vào trung tâm của ngôn ngữ. Tên lệnh, cấu trúc và tham số phản ánh đối tượng hoặc thao tác thực tế.

Ví dụ, trong SQL, người dùng làm việc với bảng, hàng, cột, phép nối và điều kiện. Trong một DSL mô tả quy trình bán hàng, các khái niệm có thể là đơn hàng, khách hàng, trạng thái, điều kiện phê duyệt và hành động giao hàng.

Việc dùng từ vựng đúng miền giúp thu hẹp khoảng cách giữa cách chuyên gia mô tả công việc và cách hệ thống biểu diễn công việc đó. Tuy nhiên, tên gọi quen thuộc chỉ hữu ích khi ý nghĩa của chúng được định nghĩa nhất quán. Một từ khóa nghe tự nhiên nhưng có nhiều cách hiểu sẽ làm ngôn ngữ khó sử dụng hơn.

### 2.3. Có mức trừu tượng phù hợp với người dùng miền

DSL thường che giấu một phần chi tiết triển khai để người viết tập trung vào mục tiêu của tác vụ. Người viết truy vấn SQL có thể nêu tập dữ liệu cần lấy và điều kiện lọc mà không phải tự quản lý cách đọc từng trang dữ liệu, cấp phát bộ nhớ hay lập lịch truy cập đĩa.

Mức trừu tượng phải phù hợp với miền. Nếu trừu tượng quá thấp, người dùng vẫn phải thao tác với nhiều chi tiết kỹ thuật và DSL không tạo ra nhiều giá trị. Nếu trừu tượng quá cao hoặc che giấu quá nhiều quy tắc, người dùng khó dự đoán kết quả, khó gỡ lỗi và khó xử lý trường hợp đặc biệt.

Vì vậy, trừu tượng tốt không đơn giản là làm cho mã ngắn hơn. Nó giữ lại những thông tin quan trọng đối với miền, đồng thời giảm bớt những chi tiết không cần thiết cho công việc đang mô tả.

### 2.4. Diễn đạt súc tích và giàu ý nghĩa trong miền

Một DSL thường cho phép mô tả một thao tác miền bằng một cấu trúc ngắn gọn. Cấu trúc đó có thể thay thế nhiều dòng mã đa dụng hoặc một chuỗi thao tác kỹ thuật.

Ví dụ, truy vấn sau mô tả trực tiếp tập sinh viên có điểm từ 8 trở lên và sắp xếp theo điểm giảm dần:

~~~sql
SELECT ten, diem
FROM sinh_vien
WHERE diem >= 8.0
ORDER BY diem DESC;
~~~

Người đọc có thể nhận ra mục tiêu của truy vấn qua các từ khóa và cấu trúc quen thuộc. Nếu viết cùng chức năng bằng một ngôn ngữ đa dụng, chương trình có thể phải thể hiện rõ hơn cách lấy dữ liệu, duyệt phần tử, kiểm tra điều kiện và sắp xếp.

Tính súc tích chỉ có giá trị khi ý nghĩa vẫn rõ ràng. Việc tạo ra nhiều ký hiệu viết tắt hoặc cú pháp quá dày đặc có thể làm mã ngắn hơn nhưng khó đọc và khó bảo trì hơn.

### 2.5. Có cú pháp và quy tắc sử dụng được giới hạn rõ

Cú pháp (syntax) quy định cách viết một biểu thức hoặc câu lệnh hợp lệ: từ khóa nào được dùng, thành phần nào phải xuất hiện, thứ tự của chúng ra sao và cách nhóm chúng như thế nào.

Do tập trung vào một miền, DSL thường có bộ cấu trúc nhỏ hơn ngôn ngữ đa dụng. Ví dụ, regex định nghĩa các toán tử cho lớp ký tự, nhóm, lựa chọn và số lần lặp. CSS định nghĩa cấu trúc bộ chọn cùng các khai báo thuộc tính và giá trị.

Giới hạn cú pháp giúp công cụ phân tích có thể phát hiện nhiều cách viết không hợp lệ. Tuy nhiên, cú pháp dễ học không chỉ phụ thuộc vào số lượng quy tắc. Một ngôn ngữ có ít quy tắc nhưng quy tắc khó đoán vẫn có thể gây nhầm lẫn.

### 2.6. Có ngữ nghĩa xác định

Ngữ nghĩa (semantics) giải thích một cấu trúc hợp lệ có ý nghĩa gì và khi thực thi hoặc diễn giải thì nó tạo ra kết quả nào. Hai câu lệnh có cú pháp giống nhau nhưng ngữ nghĩa khác nhau sẽ dẫn đến hành vi khác nhau.

Một DSL cần quy định rõ các vấn đề như:

- Biểu thức được đánh giá theo thứ tự nào.
- Giá trị thiếu, giá trị rỗng hoặc lỗi được xử lý ra sao.
- Kiểu dữ liệu nào được phép dùng trong từng vị trí.
- Một thao tác có tác dụng phụ hay chỉ tạo ra kết quả mô tả.
- Quy tắc ưu tiên giữa các toán tử và điều kiện là gì.

Ví dụ, trong biểu thức điều kiện, người dùng cần biết AND và OR được nhóm theo quy tắc nào. Nếu thứ tự ưu tiên không rõ, cùng một biểu thức có thể bị hiểu khác nhau giữa người viết và hệ thống.

Ngữ nghĩa rõ ràng giúp DSL dễ học, dễ kiểm thử và dễ triển khai công cụ hỗ trợ. Nó cũng giúp người dùng dự đoán được kết quả trước khi chạy một cấu hình hoặc quy trình.

### 2.7. Hướng đến khả năng đọc và cách làm việc của người dùng mục tiêu

Người sử dụng DSL có thể là lập trình viên, quản trị viên hệ thống, chuyên viên phân tích dữ liệu, nhà thiết kế hoặc chuyên gia nghiệp vụ. Vì vậy, DSL cần cân nhắc kiến thức và thói quen của nhóm người dùng mục tiêu.

Một ngôn ngữ dành cho chuyên gia dữ liệu có thể ưu tiên cấu trúc truy vấn và phép biến đổi dữ liệu. Một ngôn ngữ dành cho người thiết kế giao diện có thể dùng các khái niệm như màu sắc, khoảng cách, phông chữ và bố cục.

Khả năng đọc không đồng nghĩa với việc DSL phải giống ngôn ngữ tự nhiên. Một DSL dùng ký hiệu có thể rất dễ đọc đối với người đã quen với miền đó, như regex đối với người thường xuyên xử lý mẫu chuỗi. Ngược lại, câu lệnh gần giống tiếng Anh vẫn có thể khó hiểu nếu quy tắc của nó thiếu nhất quán.

### 2.8. Hỗ trợ kiểm tra tính hợp lệ và phát hiện lỗi

Do phạm vi được giới hạn, DSL có thể áp dụng các kiểm tra phù hợp với miền. Công cụ có thể kiểm tra cú pháp, kiểu dữ liệu, tên tài nguyên, thuộc tính hợp lệ, quan hệ phụ thuộc hoặc quy tắc nghiệp vụ.

Ví dụ, một DSL cấu hình giao diện có thể báo lỗi khi dùng thuộc tính không được hỗ trợ. Một DSL mô tả quy trình có thể phát hiện bước tham chiếu đến trạng thái không tồn tại. Một DSL truy vấn có thể báo lỗi khi tên cột không hợp lệ.

Thông báo lỗi nên chỉ ra vị trí, nguyên nhân và cách sửa có thể thực hiện. Nếu DSL chỉ báo rằng cấu hình không hợp lệ mà không giải thích vì sao, lợi ích về năng suất sẽ giảm đáng kể.

### 2.9. Có khả năng kết hợp và tái sử dụng cấu trúc

Các tác vụ trong một miền thường được ghép từ những phần nhỏ. DSL có thể hỗ trợ đặt tên cho biểu thức, tái sử dụng quy tắc, kết hợp điều kiện, chia cấu hình thành mô-đun hoặc tham chiếu thành phần đã định nghĩa.

Chẳng hạn, truy vấn SQL có thể kết hợp bảng bằng JOIN, kết hợp điều kiện bằng AND và OR, hoặc tổ chức truy vấn con. CSS cho phép nhóm bộ chọn và tái sử dụng quy tắc qua lớp. Các công cụ build cho phép một mục tiêu phụ thuộc vào những mục tiêu khác.

Khả năng kết hợp giúp tránh lặp lại và hỗ trợ mở rộng chương trình. Tuy nhiên, cơ chế tái sử dụng cần đủ rõ để người đọc lần theo được quan hệ giữa các thành phần.

### 2.10. Gắn với môi trường thực thi hoặc công cụ của miền

DSL thường cần một thành phần diễn giải hoặc thực thi. Thành phần đó có thể là trình thông dịch, trình biên dịch, bộ phân tích, công cụ sinh mã, bộ máy truy vấn hoặc ứng dụng hiểu định dạng DSL.

Ví dụ, hệ quản trị cơ sở dữ liệu phân tích và thực thi truy vấn SQL; trình duyệt xử lý CSS để trình bày trang web; công cụ Terraform đọc HCL để lập kế hoạch và quản lý tài nguyên hạ tầng.

Môi trường đi kèm có ảnh hưởng trực tiếp đến trải nghiệm sử dụng DSL. Trình soạn thảo có tô màu cú pháp, tự hoàn thành, kiểm tra lỗi và tài liệu tham chiếu sẽ giúp người dùng làm việc hiệu quả hơn. Một DSL có cú pháp tốt nhưng thiếu công cụ và tài liệu vẫn có thể khó áp dụng trong thực tế.

## 3. Bảng tổng hợp đặc trưng và giá trị

| Đặc trưng | Giá trị mang lại | Câu hỏi khi đánh giá |
|---|---|---|
| Tập trung vào miền | Giữ ngôn ngữ đúng phạm vi công việc | DSL giải quyết chính xác loại bài toán nào? |
| Từ vựng theo miền | Giúp người dùng diễn đạt bằng khái niệm quen thuộc | Tên gọi có phản ánh đúng khái niệm nghiệp vụ không? |
| Trừu tượng phù hợp | Giảm chi tiết kỹ thuật không cần thiết | Người dùng có kiểm soát được hành vi quan trọng không? |
| Diễn đạt súc tích | Mô tả tác vụ bằng ít cấu trúc chuyên biệt hơn | Mã ngắn có còn dễ hiểu không? |
| Cú pháp rõ ràng | Giúp viết và phân tích biểu thức nhất quán | Quy tắc viết có dễ đoán và nhất quán không? |
| Ngữ nghĩa xác định | Giúp dự đoán và kiểm thử kết quả | Mỗi cấu trúc có hành vi được định nghĩa rõ không? |
| Dễ đọc với người dùng mục tiêu | Giảm khoảng cách giữa nghiệp vụ và biểu diễn kỹ thuật | Ai sẽ đọc và chỉnh sửa DSL? |
| Kiểm tra theo miền | Phát hiện lỗi sớm và chính xác hơn | Công cụ kiểm tra được những quy tắc nào? |
| Kết hợp và tái sử dụng | Hạn chế lặp lại, hỗ trợ mở rộng | Các cấu trúc có thể được ghép và quản lý thế nào? |
| Công cụ hỗ trợ | Giúp viết, kiểm tra và vận hành thuận tiện | Có parser, tài liệu, trình gỡ lỗi hoặc IDE phù hợp không? |

Các đặc trưng trên có quan hệ với nhau. Ví dụ, từ vựng theo miền chỉ phát huy tác dụng khi ngữ nghĩa rõ ràng; cú pháp giới hạn giúp kiểm tra tốt hơn khi công cụ hiểu được quy tắc của miền; khả năng tái sử dụng cần đi kèm cấu trúc đủ dễ đọc.

## 4. Các cách phân loại DSL

DSL có thể được phân loại theo cách triển khai hoặc theo phong cách diễn đạt. Những cách phân loại này mô tả các khía cạnh khác nhau và không loại trừ lẫn nhau.

### 4.1. DSL bên ngoài (External DSL)

External DSL có cú pháp riêng, tách biệt với cú pháp của ngôn ngữ lập trình đa dụng. Thông thường, nó cần bộ phân tích hoặc công cụ chuyên biệt để đọc và xử lý.

SQL, regex và CSS là những ví dụ quen thuộc. Người viết sử dụng cú pháp của chính ngôn ngữ đó, sau đó một công cụ tương ứng phân tích và diễn giải nội dung.

Ưu điểm của cách tiếp cận này là ngôn ngữ có thể được thiết kế sát với miền và không bị ràng buộc hoàn toàn bởi cú pháp của ngôn ngữ chủ. Đổi lại, nhóm phát triển phải xây dựng hoặc tích hợp parser, thông báo lỗi, công cụ biên tập, tài liệu và cơ chế bảo trì cú pháp.

### 4.2. DSL nhúng (Embedded DSL hoặc Internal DSL)

Embedded DSL được xây dựng bên trong một ngôn ngữ chủ. Nó tận dụng cú pháp, kiểu dữ liệu, hàm, đối tượng hoặc cơ chế của ngôn ngữ chủ để tạo ra cách diễn đạt chuyên biệt.

Ví dụ, Gradle Kotlin DSL dùng cú pháp Kotlin để mô tả cấu hình build. LINQ trong C# cung cấp các cấu trúc truy vấn dữ liệu được tích hợp vào ngôn ngữ và hệ sinh thái C#.

Ưu điểm của DSL nhúng là có thể tái sử dụng trình biên dịch, hệ kiểu, thư viện, trình gỡ lỗi và công cụ sẵn có của ngôn ngữ chủ. Nhược điểm là cú pháp và cách diễn đạt có thể bị giới hạn bởi ngôn ngữ chủ; người dùng cũng có thể cần biết ngôn ngữ chủ trước khi sử dụng DSL.

| Tiêu chí | External DSL | Embedded DSL |
|---|---|---|
| Cú pháp | Có cú pháp riêng | Dựa trên cú pháp ngôn ngữ chủ |
| Phân tích | Thường cần parser hoặc công cụ riêng | Thường tận dụng parser và cơ chế của ngôn ngữ chủ |
| Mức tự do khi thiết kế | Cao hơn, có thể sát với miền | Bị ảnh hưởng bởi ngôn ngữ chủ |
| Công cụ | Cần đầu tư xây dựng hoặc tích hợp | Có thể tận dụng công cụ hiện có |
| Người dùng | Có thể chỉ cần học DSL | Thường cần biết thêm ngôn ngữ chủ |

### 4.3. DSL khai báo và DSL mệnh lệnh

Đây là cách phân loại theo phong cách diễn đạt, không phải theo việc DSL bên ngoài hay nhúng.

- **Khai báo (declarative):** người viết nêu kết quả, điều kiện hoặc trạng thái mong muốn; hệ thống quyết định cách thực hiện. SQL là ví dụ điển hình: truy vấn mô tả dữ liệu cần lấy và điều kiện áp dụng.
- **Mệnh lệnh (imperative):** người viết mô tả các bước hoặc hành động cần thực hiện. Một DSL tự động hóa có thể cung cấp các lệnh tuần tự, điều kiện và vòng lặp để điều khiển quy trình.

Một DSL có thể kết hợp cả hai phong cách. Chọn phong cách nào phụ thuộc vào bản chất công việc và mức kiểm soát mà người dùng cần có.

### 4.4. DSL văn bản và DSL trực quan

DSL văn bản biểu diễn mô hình bằng từ khóa, biểu thức hoặc cấu trúc ký tự. DSL trực quan dùng sơ đồ, khối, nút hoặc ký hiệu đồ họa. Ví dụ, BPMN cung cấp ký hiệu để mô hình hóa quy trình nghiệp vụ.

DSL trực quan có thể giúp người dùng nhìn thấy quan hệ và luồng xử lý. Tuy nhiên, mô hình lớn dễ trở nên rối; việc so sánh phiên bản, hợp nhất thay đổi và xử lý tự động đôi khi thuận tiện hơn với biểu diễn văn bản. Một số công cụ hỗ trợ chuyển đổi giữa biểu diễn trực quan và văn bản.

## 5. DSL khác ngôn ngữ lập trình đa dụng như thế nào?

Ngôn ngữ đa dụng được thiết kế để giải quyết nhiều loại bài toán. Nó thường cung cấp biến, kiểu dữ liệu, hàm, cấu trúc điều khiển, mô-đun và khả năng tương tác với nhiều thư viện. DSL tập trung các cấu trúc đó vào một miền cụ thể hoặc cung cấp một cách diễn đạt chuyên biệt cho miền đó.

| Khía cạnh | DSL | Ngôn ngữ lập trình đa dụng |
|---|---|---|
| Phạm vi | Một miền hoặc nhóm tác vụ xác định | Nhiều miền và loại tác vụ |
| Từ vựng | Ưu tiên khái niệm của miền | Khái niệm tính toán và trừu tượng tổng quát |
| Cấu trúc | Tối ưu cho các thao tác miền | Có nhiều cấu trúc để xây dựng chương trình tổng quát |
| Mức biểu đạt | Có thể rất ngắn gọn trong miền mục tiêu | Linh hoạt cho nhiều dạng thuật toán |
| Khả năng mở rộng | Thường bị giới hạn bởi phạm vi DSL và cơ chế mở rộng | Thường rộng hơn nhờ hệ sinh thái và thư viện |
| Người dùng chính | Người làm việc trong miền và lập trình viên hỗ trợ miền | Chủ yếu là người phát triển phần mềm, tùy ngôn ngữ |

Ví dụ, SQL diễn đạt việc lọc và kết hợp dữ liệu bằng các cấu trúc truy vấn. Java có thể thực hiện cùng công việc, nhưng người viết thường phải dùng các cấu trúc và thư viện tổng quát hơn. SQL thuận tiện khi nhiệm vụ thuộc miền truy vấn dữ liệu; Java linh hoạt hơn khi cần xây dựng logic ứng dụng rộng, phối hợp nhiều dịch vụ hoặc triển khai thuật toán tùy biến.

Hai loại ngôn ngữ có thể được sử dụng cùng nhau. Một ứng dụng Java có thể gửi truy vấn SQL đến cơ sở dữ liệu, xử lý kết quả bằng Java rồi dùng một DSL khác để cấu hình hoặc tự động hóa quá trình build.

## 6. Ví dụ minh họa cách DSL mô hình hóa miền

Giả sử một hệ thống bán hàng cần áp dụng quy tắc miễn phí vận chuyển cho đơn hàng có tổng tiền từ 500.000 đồng trở lên. Một DSL giả định dành cho quy tắc bán hàng có thể biểu diễn như sau:

~~~text
rule "mien_phi_van_chuyen" {
    when order.total >= 500000
    then order.shipping_fee = 0
}
~~~

Đây là cú pháp minh họa do bài học đặt ra, không phải cú pháp của một sản phẩm hay ngôn ngữ có sẵn. Nó cho thấy một số quyết định thiết kế của DSL:

1. **Từ vựng theo miền:** order, total và shipping_fee là các khái niệm của đơn hàng.
2. **Cấu trúc theo mục đích:** when biểu thị điều kiện; then biểu thị hành động khi điều kiện đúng.
3. **Trừu tượng:** người viết mô tả quy tắc nghiệp vụ mà không phải viết vòng lặp duyệt đơn hàng hoặc gọi trực tiếp cơ sở dữ liệu.
4. **Giới hạn phạm vi:** biểu thức chỉ cần hỗ trợ các điều kiện và hành động được phép trong hệ thống quy tắc bán hàng.
5. **Khả năng kiểm tra:** công cụ có thể xác nhận order.total là trường hợp lệ, giá trị so sánh là số và shipping_fee có thể nhận giá trị được gán.

Một ngữ pháp đơn giản cho ví dụ có thể được phác thảo như sau:

~~~text
rule        ::= "rule" STRING "{" condition action "}"
condition   ::= "when" EXPRESSION
action      ::= "then" ASSIGNMENT
ASSIGNMENT  ::= FIELD "=" VALUE
~~~

Ngữ pháp này chỉ mô tả khung cú pháp. Để triển khai DSL thực tế, nhóm phát triển còn phải định nghĩa ngữ nghĩa của biểu thức, kiểu dữ liệu, đơn vị tiền tệ, quyền được thay đổi trường, hành vi khi dữ liệu thiếu và cách xử lý lỗi. Ví dụ, hệ thống cần xác định rõ 500000 là số tiền theo đồng Việt Nam hay một đơn vị tiền tệ khác.

Qua ví dụ này có thể thấy, thiết kế DSL không dừng ở việc chọn những từ khóa dễ đọc. Mỗi cấu trúc phải có ý nghĩa chính xác và có thể được công cụ kiểm tra, diễn giải hoặc thực thi.

## 7. Lợi ích và giới hạn của DSL

### 7.1. Lợi ích

- **Tăng năng suất trong miền mục tiêu:** các thao tác thường gặp có thể được biểu diễn trực tiếp, giảm lượng mã lặp lại.
- **Giảm khoảng cách giữa nghiệp vụ và kỹ thuật:** từ vựng và cấu trúc phản ánh cách chuyên gia miền mô tả công việc.
- **Tạo quy tắc nhất quán:** người dùng cùng sử dụng một tập cú pháp và ngữ nghĩa, giúp giảm cách diễn giải tùy tiện.
- **Hỗ trợ kiểm tra chuyên biệt:** công cụ có thể phát hiện lỗi liên quan đến quy tắc miền trước khi thực thi.
- **Tách mô tả khỏi cơ chế thực thi:** trong nhiều trường hợp, cùng một mô tả có thể được xử lý bởi các phiên bản công cụ khác nhau mà không yêu cầu người dùng viết lại toàn bộ quy tắc.
- **Tăng khả năng trao đổi:** DSL được thiết kế tốt có thể giúp chuyên gia nghiệp vụ và lập trình viên cùng thảo luận trên một mô hình chung.

### 7.2. Giới hạn và chi phí

- **Phạm vi có giới hạn:** DSL có thể không diễn đạt được yêu cầu nằm ngoài miền đã thiết kế.
- **Chi phí xây dựng và bảo trì:** một DSL riêng cần đặc tả, parser hoặc bộ xử lý, tài liệu, công cụ phát triển và quy trình quản lý phiên bản.
- **Khó gỡ lỗi nếu thiếu công cụ:** khi một câu lệnh DSL được chuyển thành nhiều bước thực thi, người dùng cần cách truy vết từ kết quả về biểu thức nguồn.
- **Nguy cơ tạo thêm độ phức tạp:** một DSL thiết kế thiếu nhất quán có thể khiến người dùng phải học thêm nhiều quy tắc mà lợi ích nhận được không tương xứng.
- **Phụ thuộc vào nền tảng:** DSL có thể gắn chặt với một runtime, hệ thống hoặc nhà cung cấp cụ thể.
- **Khó mở rộng sai hướng:** thêm quá nhiều tính năng tổng quát có thể khiến DSL mất trọng tâm và trở nên gần giống một ngôn ngữ đa dụng nhưng thiếu hệ sinh thái tương ứng.

Do đó, không phải bài toán nào cũng cần một DSL mới. Nếu một thư viện, API, định dạng cấu hình hiện có hoặc ngôn ngữ đa dụng đã giải quyết tốt công việc, việc tạo thêm DSL có thể làm tăng chi phí mà không đem lại lợi ích rõ ràng.

## 8. Khi nào nên cân nhắc xây dựng DSL?

DSL thường đáng cân nhắc khi một nhóm người dùng phải lặp lại nhiều tác vụ có cấu trúc tương tự trong cùng một miền, các khái niệm miền tương đối ổn định và cách biểu diễn hiện tại khó đọc hoặc dễ sai.

Một số dấu hiệu tích cực:

- Có nhiều quy tắc hoặc cấu hình lặp lại, nhưng chúng đều tuân theo một mô hình chung.
- Chuyên gia miền cần đọc hoặc chỉnh sửa mô tả công việc mà không phải hiểu toàn bộ mã nguồn ứng dụng.
- Có thể xác định rõ các cấu trúc hợp lệ và quy tắc nghiệp vụ để kiểm tra tự động.
- Một bộ công cụ dùng chung có thể xử lý nhiều mô tả DSL và đem lại lợi ích lâu dài.

Ngược lại, DSL có thể không phù hợp nếu yêu cầu chỉ xuất hiện một lần, miền thay đổi liên tục, tác vụ quá đa dạng hoặc ngôn ngữ đa dụng hiện tại đã diễn đạt rõ ràng. Trước khi xây dựng DSL, nên thử nghiệm bằng một tập tác vụ thực tế và so sánh khả năng đọc, chi phí triển khai, khả năng kiểm tra và chi phí bảo trì.

## 9. Các câu hỏi dùng để đánh giá một DSL

Khi xem xét một DSL có phù hợp hoặc được thiết kế tốt hay không, có thể dùng các câu hỏi sau:

1. **Miền và người dùng:** DSL phục vụ lĩnh vực nào? Ai là người viết, đọc và bảo trì nó?
2. **Tác vụ:** Những công việc phổ biến nào được hỗ trợ trực tiếp? Những trường hợp nào nằm ngoài phạm vi?
3. **Từ vựng:** Tên lệnh và khái niệm có khớp với thuật ngữ mà người dùng miền thực sự sử dụng không?
4. **Cú pháp:** Cấu trúc có nhất quán, dễ đoán và dễ phát hiện lỗi không?
5. **Ngữ nghĩa:** Mỗi biểu thức có hành vi xác định, tài liệu rõ và có thể kiểm thử không?
6. **Trừu tượng:** DSL có giảm chi tiết kỹ thuật mà vẫn giữ đủ quyền kiểm soát cần thiết không?
7. **Kiểm tra:** Công cụ có thể phát hiện lỗi cú pháp, kiểu dữ liệu và quy tắc miền ở thời điểm phù hợp không?
8. **Tích hợp:** DSL kết nối với hệ thống hiện có và quy trình phát triển như thế nào?
9. **Bảo trì:** Có cơ chế quản lý phiên bản, tương thích ngược, tài liệu và di chuyển cấu hình không?
10. **Hiệu quả:** Lợi ích về năng suất, độ chính xác và khả năng trao đổi có lớn hơn chi phí xây dựng và vận hành không?

## 10. Bài tập tự kiểm tra

### Bài 1: Nhận diện DSL

Với từng ví dụ sau, hãy nêu miền sử dụng và giải thích vì sao nó có thể được xem là DSL:

- Một câu truy vấn SQL dùng SELECT, WHERE và ORDER BY.
- Một biểu thức regex dùng để kiểm tra mã bưu chính.
- Một tệp CSS quy định màu sắc và khoảng cách của các thành phần giao diện.
- Một chương trình Java xử lý danh sách đơn hàng bằng vòng lặp và điều kiện.

Gợi ý: hãy xem xét phạm vi, từ vựng, cấu trúc và mục đích của từng ngôn ngữ. Java là ngôn ngữ đa dụng; việc nó được dùng để giải quyết bài toán đơn hàng không làm nó trở thành DSL.

### Bài 2: Phân loại DSL

Hãy phân loại SQL và Gradle Kotlin DSL theo các tiêu chí sau:

- External hay embedded?
- Chủ yếu khai báo hay mệnh lệnh?
- Văn bản hay trực quan?

Giải thích vì sao các tiêu chí này mô tả những khía cạnh khác nhau của DSL.

### Bài 3: Thiết kế một DSL nhỏ

Giả sử cần mô tả quy tắc giảm giá cho cửa hàng trực tuyến. Hãy đề xuất:

- Ba đến năm khái niệm thuộc miền bán hàng.
- Cú pháp cho một điều kiện áp dụng giảm giá.
- Cú pháp cho hành động tính hoặc gán mức giảm giá.
- Hai quy tắc hợp lệ và hai trường hợp cần báo lỗi.

Sau đó, giải thích DSL của bạn giúp người làm nghiệp vụ dễ hiểu hơn ở điểm nào và còn thiếu quy tắc gì để có thể thực thi an toàn.

### Bài 4: Phân tích lựa chọn

Một nhóm chỉ cần tạo một tệp cấu hình gồm ba giá trị cố định. Nhóm khác cần quản lý hàng trăm quy tắc định tuyến có điều kiện, được nhiều chuyên viên nghiệp vụ chỉnh sửa và cần kiểm tra tính hợp lệ tự động.

Trong trường hợp nào việc xây dựng DSL riêng có thể hợp lý hơn? Hãy giải thích dựa trên tần suất sử dụng, độ ổn định của miền, số lượng người dùng, khả năng kiểm tra và chi phí bảo trì.

## Kết luận

DSL là ngôn ngữ được tối ưu cho một miền vấn đề. Những đặc trưng thường gặp của nó gồm phạm vi chuyên biệt, từ vựng theo miền, mức trừu tượng phù hợp, khả năng diễn đạt súc tích, cú pháp và ngữ nghĩa rõ ràng, khả năng kiểm tra theo miền, khả năng kết hợp và công cụ hỗ trợ. DSL có thể được triển khai như một ngôn ngữ bên ngoài hoặc nhúng trong ngôn ngữ chủ; nó cũng có thể dùng phong cách khai báo, mệnh lệnh, văn bản hoặc trực quan. Giá trị của DSL nằm ở việc giúp diễn đạt và kiểm soát công việc trong miền hiệu quả hơn, vì vậy quyết định sử dụng DSL cần cân nhắc cả lợi ích lẫn chi phí thiết kế và bảo trì.
