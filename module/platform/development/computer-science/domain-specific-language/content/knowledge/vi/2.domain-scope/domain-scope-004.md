# Ranh giới của DSL

Ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL) được thiết kế để mô tả và giải quyết một nhóm vấn đề trong một miền cụ thể. Ranh giới của DSL xác định miền vấn đề mà ngôn ngữ muốn biểu đạt, những khái niệm và thao tác được xem là hợp lệ, cũng như cách DSL tương tác với chương trình và môi trường bên ngoài. Xác định ranh giới rõ ràng giúp ngôn ngữ tập trung, dễ học và dễ kiểm soát; ranh giới quá hẹp khiến người dùng thường xuyên phải thoát ra ngôn ngữ khác, còn ranh giới quá rộng khiến DSL dần trở thành một ngôn ngữ mục đích tổng quát khó duy trì.

## 1. Ranh giới bắt đầu từ miền vấn đề

Miền vấn đề (problem domain) là lĩnh vực mà người dùng cần mô hình hóa. Nó có thể là truy vấn dữ liệu quan hệ, mô tả giao diện, cấu hình hạ tầng, xây dựng quy trình xử lý dữ liệu hoặc biểu diễn quy tắc nghiệp vụ. DSL chọn ra một phần của miền đó để cung cấp cách diễn đạt ngắn gọn và gần với ngôn ngữ của chuyên gia.

Khi xác định phạm vi, cần làm rõ:

- **Đối tượng:** những thực thể nào tồn tại trong miền, chẳng hạn bảng và cột trong cơ sở dữ liệu, dịch vụ và cổng mạng trong hệ thống triển khai.
- **Thuộc tính:** những đặc điểm nào người dùng có thể khai báo, chẳng hạn kiểu dữ liệu, số bản sao, trạng thái hoặc giới hạn.
- **Thao tác:** những hành động nào DSL cho phép, chẳng hạn lọc, kết hợp, triển khai hoặc kiểm tra.
- **Quy tắc và bất biến:** điều kiện nào phải luôn đúng, chẳng hạn một cột khóa chính không được trùng hoặc một dịch vụ phải có cấu hình cổng hợp lệ.
- **Người sử dụng và mục tiêu:** ai viết chương trình DSL, họ cần hoàn thành công việc nào và cần hiểu kết quả ở mức độ nào.

Phạm vi miền cũng bao gồm những điều DSL chủ động không mô hình hóa. Ví dụ, một DSL mô tả quy trình triển khai có thể tập trung vào dịch vụ, phiên bản, tài nguyên, kiểm tra sức khỏe và thứ tự triển khai. Việc chỉnh sửa ảnh, quản lý tài liệu cá nhân hay thực hiện mọi phép tính tùy ý không thuộc phạm vi của ngôn ngữ đó, dù về mặt kỹ thuật có thể viết thêm cú pháp để hỗ trợ chúng.

## 2. Phân biệt DSL với ngôn ngữ mục đích tổng quát

Ngôn ngữ mục đích tổng quát (General-Purpose Language, GPL) như Java, Python hoặc C# được thiết kế để biểu đạt nhiều loại thuật toán và ứng dụng. DSL tập trung vào một miền hẹp hơn và thường cung cấp các khái niệm trực tiếp của miền đó.

| Khía cạnh | DSL | Ngôn ngữ mục đích tổng quát |
|---|---|---|
| Mục tiêu | Giải quyết một nhóm công việc trong miền xác định | Xây dựng nhiều loại chương trình khác nhau |
| Từ vựng | Khái niệm gần với nghiệp vụ hoặc chuyên môn | Khái niệm lập trình tổng quát như biến, hàm, kiểu và cấu trúc điều khiển |
| Cách biểu đạt | Tối ưu cho các thao tác thường gặp trong miền | Linh hoạt cho nhiều kiểu thuật toán và kiến trúc |
| Người dùng chính | Chuyên gia miền, nhà phân tích hoặc lập trình viên làm việc trong miền | Lập trình viên và kỹ sư phần mềm ở nhiều lĩnh vực |
| Giới hạn | Cố ý giới hạn những gì có thể diễn đạt | Phạm vi biểu đạt rộng hơn, thường cần nhiều cấu trúc hơn |

Chẳng hạn, SQL diễn đạt truy vấn và thao tác trên dữ liệu quan hệ. Người viết có thể mô tả dữ liệu cần lấy, điều kiện lọc và cách nhóm dữ liệu mà không phải tự viết thuật toán duyệt từng bản ghi. Tuy nhiên, SQL không nhằm thay thế toàn bộ ngôn ngữ dùng để xây dựng giao diện, quản lý vòng đời ứng dụng hay xử lý mọi tác vụ của hệ điều hành.

Sự khác biệt nằm ở mục đích và phạm vi được ưu tiên, không chỉ ở kích thước cú pháp. Một DSL có thể có nhiều tính năng, còn một GPL có thể được dùng trong một miền cụ thể; điều quyết định là ngôn ngữ được thiết kế quanh các khái niệm nào và chủ động giới hạn việc biểu đạt ra sao.

## 3. Các lớp ranh giới của một DSL

Ranh giới DSL không chỉ là danh sách tính năng. Nó xuất hiện ở nhiều lớp trong quá trình một mô tả được viết, kiểm tra và thực thi.

### 3.1. Ranh giới cú pháp

Cú pháp quy định cấu trúc văn bản nào được chấp nhận. Nó bao gồm từ khóa, toán tử, biểu thức, dấu phân cách và cách kết hợp các thành phần. Bộ phân tích cú pháp (parser) dùng các quy tắc này để xác định cấu trúc của chương trình DSL, thường tạo ra cây cú pháp trừu tượng (Abstract Syntax Tree, AST).

Ví dụ, một DSL cấu hình dịch vụ có thể chấp nhận cấu trúc `service`, `replicas` và `port`. Nếu người dùng đặt `replicas` ở vị trí không hợp lệ hoặc thiếu dấu đóng khối, chương trình không vượt qua được ranh giới cú pháp. Cú pháp nên phản ánh cách chuyên gia miền suy nghĩ và giúp lỗi dễ được nhận biết.

### 3.2. Ranh giới ngữ nghĩa

Một chương trình có thể đúng cú pháp nhưng vẫn vô nghĩa hoặc không hợp lệ trong miền. Ngữ nghĩa quy định ý nghĩa của cấu trúc và các điều kiện mà cấu trúc phải thỏa mãn.

Ví dụ, `replicas = -2` có thể được parser chấp nhận nếu giá trị được đọc như một số nguyên, nhưng quy tắc miền có thể yêu cầu số bản sao lớn hơn hoặc bằng không. Tương tự, một tham chiếu đến dịch vụ chưa được khai báo có thể hợp lệ về mặt cú pháp nhưng sai về ngữ nghĩa.

Ranh giới ngữ nghĩa thường được thực thi bằng kiểm tra kiểu, kiểm tra tham chiếu, xác thực miền giá trị và kiểm tra các bất biến. Tách biệt lỗi cú pháp với lỗi ngữ nghĩa giúp thông báo lỗi cụ thể hơn và giúp người dùng hiểu vì sao mô tả của họ không hợp lệ.

### 3.3. Ranh giới thực thi

Ranh giới thực thi xác định một chương trình DSL có thể gây ra những hiệu ứng nào. DSL có thể được thông dịch trực tiếp, biên dịch thành mã của ngôn ngữ khác, chuyển thành cấu hình cho một hệ thống, hoặc được thực thi bởi một bộ máy chuyên biệt.

Một DSL chỉ mô tả biểu đồ có thể tạo ra dữ liệu hình học hoặc hình ảnh. Một DSL triển khai hạ tầng có thể tạo tài nguyên, thay đổi cấu hình và gọi dịch vụ bên ngoài. Hai DSL này có mức độ tác động rất khác nhau. Vì vậy, cần xác định rõ thao tác nào được phép, tài nguyên nào có thể truy cập và lỗi được xử lý ở đâu.

### 3.4. Ranh giới tích hợp

Nhiều DSL không hoạt động độc lập mà được nhúng trong một ngôn ngữ chủ (host language) hoặc được gọi từ ứng dụng khác. Ranh giới tích hợp quy định dữ liệu, hàm, kiểu và lỗi được truyền qua lại như thế nào.

Một DSL nhúng có thể tận dụng cú pháp và hệ thống kiểu của ngôn ngữ chủ. Một DSL độc lập có thể có parser, trình kiểm tra và runtime riêng. Dù chọn cách nào, giao diện giữa DSL và môi trường cần có hợp đồng rõ ràng: đầu vào có dạng gì, kết quả có dạng gì, ngoại lệ được biểu diễn ra sao và thành phần nào chịu trách nhiệm thực thi hiệu ứng bên ngoài.

## 4. Xác định điều gì thuộc và không thuộc DSL

Một yêu cầu mới không tự động trở thành tính năng của DSL chỉ vì người dùng muốn thực hiện nó trong cùng một tệp. Hãy xem xét yêu cầu theo các câu hỏi sau:

1. Yêu cầu có xuất hiện thường xuyên trong công việc của miền không?
2. Nó có thể được mô tả bằng khái niệm mà chuyên gia miền hiểu trực tiếp không?
3. Có quy tắc hoặc bất biến đặc thù nào mà DSL có thể kiểm tra và bảo vệ không?
4. Tính năng mới có làm cho các chương trình hiện tại khó đọc hoặc khó dự đoán hơn không?
5. Yêu cầu có thể được xử lý tốt hơn ở ngôn ngữ chủ, thư viện hoặc công cụ bên ngoài không?

Nếu một thao tác là phần cốt lõi, lặp lại và có ý nghĩa rõ trong miền, việc đưa nó vào DSL thường làm chương trình dễ hiểu hơn. Nếu thao tác mang tính tổng quát, hiếm gặp hoặc thuộc trách nhiệm của hệ thống khác, nên cân nhắc để nó ở lớp tích hợp.

Ví dụ, trong DSL mô tả truy vấn dữ liệu, lọc, nhóm và kết hợp bảng là các thao tác cốt lõi. Gửi email thông báo sau khi truy vấn hoàn tất có thể thuộc ứng dụng sử dụng DSL. Ứng dụng có thể nhận kết quả truy vấn rồi gọi thư viện gửi email, thay vì mở rộng DSL truy vấn thành một ngôn ngữ tự động hóa mọi tác vụ.

## 5. Hệ quả khi ranh giới quá hẹp hoặc quá rộng

**Ranh giới quá hẹp** khiến DSL thiếu những thao tác phổ biến của miền. Người dùng phải thường xuyên chuyển sang mã của ngôn ngữ chủ, tự xử lý các chi tiết mà DSL đáng lẽ có thể che giấu, hoặc tạo nhiều phần mở rộng nhỏ và không nhất quán. Khi đó, lợi ích về khả năng đọc và năng suất giảm đi.

**Ranh giới quá rộng** khiến DSL tích lũy nhiều tính năng ít liên quan, có nhiều cách làm cùng một việc và khó duy trì quy tắc nhất quán. Người dùng phải học một hệ thống phức tạp trong khi các khái niệm miền không còn nổi bật. Nếu DSL bắt đầu cần biến, vòng lặp, hàm tổng quát, quản lý bộ nhớ và hàng loạt cấu trúc không gắn với miền, nhóm thiết kế nên xem xét liệu một GPL hoặc một DSL nhúng có phù hợp hơn.

Một số DSL cung cấp lối thoát (escape hatch) để gọi mã của ngôn ngữ chủ khi gặp trường hợp đặc biệt. Đây là cách cân bằng hữu ích nếu giao diện được kiểm soát rõ ràng. Tuy nhiên, nếu hầu hết công việc đều phải dùng lối thoát, đó có thể là dấu hiệu phạm vi DSL đang được xác định chưa đúng.

## 6. Ví dụ: ranh giới của DSL triển khai dịch vụ

Giả sử một nhóm xây dựng DSL để mô tả cách triển khai các dịch vụ của một ứng dụng. Một mô tả đơn giản có thể như sau:

```text
application "shop" {
    service "api" {
        image = "shop-api:2.4"
        replicas = 3
        port = 8080
    }

    service "worker" {
        image = "shop-worker:2.4"
        replicas = 2
    }
}
```

Các khái niệm `application`, `service`, `image`, `replicas` và `port` thuộc miền triển khai. DSL có thể kiểm tra tên dịch vụ, định dạng ảnh, số bản sao và tính hợp lệ của cổng. Bộ thực thi có thể chuyển mô tả này thành cấu hình mà nền tảng triển khai hiểu được.

Trong phạm vi đó, một số yêu cầu có thể được xem là phù hợp:

- Khai báo tài nguyên và số bản sao của dịch vụ.
- Xác định cổng, biến cấu hình và kiểm tra sức khỏe.
- Khai báo quan hệ phụ thuộc giữa các dịch vụ.
- Kiểm tra các quy tắc triển khai trước khi áp dụng.

Những việc như chỉnh sửa mã nguồn ứng dụng, quản lý tài khoản nhân sự hoặc viết thuật toán xử lý ảnh không phải trách nhiệm trực tiếp của DSL này. Chúng có thể được thực hiện bởi công cụ khác và kết nối với quy trình triển khai thông qua giao diện đã xác định.

Ví dụ cũng cho thấy cú pháp chỉ là một phần của ranh giới. Hai mô tả có cùng cấu trúc vẫn có thể khác nhau về tính hợp lệ nếu một mô tả tham chiếu đến dịch vụ không tồn tại hoặc đặt số bản sao ngoài giới hạn mà nền tảng cho phép. Bộ kiểm tra ngữ nghĩa và bộ thực thi cần áp dụng cùng một mô hình miền để tránh kết quả không nhất quán.

## 7. Duy trì ranh giới khi DSL phát triển

Miền vấn đề có thể thay đổi theo thời gian. Khi có yêu cầu mới, nhóm phát triển nên xem xét nó có thuộc trách nhiệm cốt lõi của DSL hay không, sau đó đánh giá ảnh hưởng đến cú pháp, ngữ nghĩa, runtime và giao diện tích hợp.

Một thay đổi mở rộng ranh giới có thể làm chương trình cũ mất tính hợp lệ hoặc thay đổi ý nghĩa. Vì vậy, cần cân nhắc khả năng tương thích, phiên bản ngôn ngữ, thông báo lỗi và cách chuyển đổi cấu hình cũ. Tài liệu DSL nên nêu rõ các khái niệm được hỗ trợ, giới hạn đã biết và cách kết nối với công cụ bên ngoài.

Có thể mở rộng DSL qua các module hoặc plugin khi nhiều nhóm cần thêm khái niệm chuyên biệt. Mỗi phần mở rộng cần có phạm vi và hợp đồng rõ ràng để không làm mờ ý nghĩa của ngôn ngữ lõi. Những phần mở rộng không liên quan nên được giữ độc lập thay vì đưa tất cả vào một bộ cú pháp chung.

Khi thiết kế hoặc đánh giá một DSL, hãy bắt đầu từ công việc thực tế của người dùng, xác định các khái niệm và quy tắc cốt lõi, rồi quyết định nơi DSL dừng lại và nơi ngôn ngữ chủ hoặc hệ thống bên ngoài tiếp tục. Một ranh giới tốt giúp người dùng diễn đạt đúng công việc trong miền bằng ít chi tiết không cần thiết, đồng thời giữ cho hành vi của chương trình rõ ràng và có thể dự đoán.
