# Tiêu chí nhận diện ranh giới bị vi phạm

Trong ứng dụng theo mô hình **Model–View–Controller (MVC)**, Model quản lý trạng thái và quy tắc của ứng dụng, View chịu trách nhiệm trình bày, còn Controller tiếp nhận tương tác và điều phối luồng xử lý. Ba vai trò này cần phối hợp để hoàn thành một request, vì vậy việc chúng gọi hoặc trao đổi dữ liệu với nhau là bình thường. Vấn đề xuất hiện khi một vai trò bắt đầu sở hữu công việc thuộc về vai trò khác, phụ thuộc vào chi tiết triển khai của phần khác hoặc làm cho một thay đổi cục bộ lan rộng qua nhiều thành phần.

Nhận diện ranh giới bị vi phạm là bước quan trọng khi thiết kế và đánh giá MVC. Nếu chỉ nhìn tên package hoặc tên lớp, ta có thể thấy các thư mục `controller`, `model`, `view` được tách riêng nhưng trách nhiệm bên trong vẫn trộn lẫn. Ngược lại, một ứng dụng có ít lớp vẫn có thể có ranh giới tốt nếu mỗi thành phần có mục đích rõ ràng và giao tiếp qua hợp đồng ổn định.

Bài học này trình bày các tiêu chí có thể dùng để quan sát mã nguồn, lần theo một request, nhận diện dấu hiệu bất thường và quyết định nơi cần chuyển trách nhiệm. Các ví dụ tập trung vào ứng dụng web Java, biểu mẫu, xử lý lỗi, bảo mật và kiểm thử trong MVC.

## 1. Ranh giới trong MVC có ý nghĩa gì?

Ranh giới là đường phân chia trách nhiệm, quyền quyết định và sự phụ thuộc giữa các thành phần. Nó trả lời ba câu hỏi:

1. Thành phần nào chịu trách nhiệm cho một quyết định hoặc quy tắc?
2. Thành phần nào được phép biết những chi tiết của thành phần khác?
3. Các thành phần trao đổi với nhau thông qua dữ liệu và hợp đồng nào?

Ví dụ, khi người dùng gửi biểu mẫu tạo đơn hàng:

- Controller biết request HTTP đến từ URL nào, tham số nào được gửi và phản hồi web nào cần trả về.
- Model hoặc dịch vụ nghiệp vụ quyết định đơn hàng có hợp lệ không, giá được tính thế nào và trạng thái nào được phép chuyển đổi.
- View quyết định cách trình bày thông tin đơn hàng, trường biểu mẫu và thông báo lỗi.

Controller cần gọi nghiệp vụ và nhận kết quả để phản hồi. View cần nhận dữ liệu do Controller cung cấp. Sự phối hợp này không phải vi phạm ranh giới. Vi phạm xảy ra khi Controller tự quyết định chính sách giảm giá, View tự truy vấn tồn kho, hoặc Model phải biết `HttpServletRequest` để thực hiện quy tắc đặt hàng.

Có thể hình dung luồng trách nhiệm thông thường như sau:

~~~mermaid
flowchart LR
    U[Người dùng] --> V[View]
    V -->|Tương tác / request| C[Controller]
    C -->|Command / dữ liệu đầu vào| M[Model và nghiệp vụ]
    M -->|Kết quả nghiệp vụ| C
    C -->|Dữ liệu trình bày| V
    V --> U
    M <--> R[Repository / kho dữ liệu]
~~~

Sơ đồ là cách khái quát hóa một ứng dụng web. Framework có thể tổ chức chi tiết khác nhau: một số framework để View gửi request đến Controller qua trình duyệt, một số cung cấp đối tượng Model để Controller đưa dữ liệu sang View. Điều cần giữ là trách nhiệm nghiệp vụ không bị buộc vào chi tiết giao diện hoặc giao thức HTTP.

## 2. Những tiêu chí cốt lõi để đánh giá ranh giới

Không có một chỉ số đơn lẻ nào đủ để kết luận thiết kế MVC tốt hay xấu. Hãy kết hợp các tiêu chí dưới đây và quan sát tác động thực tế của chúng.

### 2.1. Trách nhiệm và lý do thay đổi

Một thành phần nên tập trung vào một nhóm trách nhiệm có liên quan. Khi một lớp thường xuyên thay đổi vì những nguyên nhân không liên quan, đó là dấu hiệu trách nhiệm đang bị trộn.

Ví dụ, `OrderController` thay đổi khi:

- URL hoặc phương thức HTTP thay đổi.
- Quy tắc tính giá thay đổi.
- Cấu trúc bảng cơ sở dữ liệu thay đổi.
- Bố cục HTML thay đổi.

Một Controller phải thay đổi vì tất cả những lý do trên có thể đang làm quá nhiều việc. Controller có thể cần điều chỉnh khi hợp đồng request hoặc cách điều phối thay đổi, nhưng không nên trở thành nơi sở hữu chính sách giá và chi tiết lưu trữ.

Hãy tự hỏi: **Nếu chỉ thay đổi một quy tắc nghiệp vụ, những thành phần nào buộc phải sửa?** Nếu câu trả lời thường xuyên bao gồm nhiều Controller và View, quy tắc có thể đang nằm sai chỗ hoặc bị sao chép.

### 2.2. Mức độ phụ thuộc vào chi tiết của thành phần khác

Một thành phần có ranh giới rõ nên phụ thuộc vào hợp đồng cần thiết, không cần biết cách thành phần khác thực hiện công việc bên trong.

Các dấu hiệu phụ thuộc quá sâu gồm:

- Model nhận trực tiếp `HttpServletRequest`, `HttpSession` hoặc kiểu dữ liệu đặc thù của framework web.
- View gọi repository hoặc tự mở kết nối cơ sở dữ liệu.
- Controller thao tác trực tiếp với cấu trúc bảng, câu SQL hoặc chi tiết ánh xạ ORM.
- Logic nghiệp vụ tạo HTML, tên template hoặc mã trạng thái HTTP.
- Nhiều lớp phải truy cập thuộc tính nội bộ của nhau để hoàn thành một thao tác.

Việc sử dụng một interface hoặc DTO không tự động tạo ra ranh giới tốt. Hợp đồng đó cũng cần ổn định, có ý nghĩa và chỉ công khai dữ liệu mà bên gọi thực sự cần.

### 2.3. Mức độ tập trung của dữ liệu và quy tắc

Trạng thái quan trọng cần có nơi quản lý nhất quán. Nếu cùng một quy tắc được triển khai ở nhiều Controller, nhiều View hoặc nhiều kênh truy cập, các bản sao có thể lệch nhau.

Ví dụ, điều kiện một đơn hàng chỉ được hủy khi đang ở trạng thái `PENDING` nên được bảo vệ bởi Model hoặc dịch vụ nghiệp vụ. Nếu trang web kiểm tra điều kiện này nhưng API lại tự cập nhật trạng thái mà không kiểm tra, ứng dụng có hai cách hiểu khác nhau về cùng một quy tắc.

Hãy hỏi: **Nếu quy tắc thay đổi, có một nơi rõ ràng để cập nhật và kiểm thử không?** Nếu phải tìm nhiều bản sao hoặc dựa vào việc giao diện đã ẩn nút thao tác, ranh giới dữ liệu và nghiệp vụ có thể chưa đúng.

### 2.4. Hợp đồng dữ liệu giữa các thành phần

Dữ liệu đi qua ranh giới cần có hình dạng và ý nghĩa rõ. Request web, đối tượng nghiệp vụ, bản ghi ORM và dữ liệu dùng để hiển thị phục vụ những mục đích khác nhau.

Ví dụ:

| Dữ liệu | Mục đích | Thành phần thường sử dụng |
|---|---|---|
| Request parameter | Dữ liệu thô do client gửi | Ranh giới HTTP / Controller |
| Form object hoặc request DTO | Hợp đồng đầu vào, gồm các trường client được phép gửi | Binding và validation |
| Command | Ý định nghiệp vụ đã được chuyển thành dữ liệu có cấu trúc | Dịch vụ nghiệp vụ / Model |
| Entity hoặc domain object | Trạng thái và quy tắc của miền nghiệp vụ | Model |
| View model | Dữ liệu đã được chuẩn bị để trình bày | Controller và View |

Không phải ứng dụng nào cũng cần đủ năm loại đối tượng. Một ứng dụng nhỏ có thể dùng chung một số kiểu dữ liệu. Tiêu chí là không để dữ liệu trình bày hoặc chi tiết HTTP vô tình trở thành hợp đồng lâu dài của Model.

Ví dụ, không nên gửi nguyên một entity có nhiều trường nội bộ sang trình duyệt chỉ vì View cần hiển thị tên và trạng thái đơn hàng. Một view model chỉ chứa các trường cần thiết thường giúp giảm phụ thuộc và tránh lộ dữ liệu ngoài ý muốn.

### 2.5. Quyền sở hữu tác dụng phụ và giao dịch

Các thao tác như ghi cơ sở dữ liệu, gửi email, phát sự kiện, cập nhật tồn kho hoặc gọi dịch vụ bên ngoài đều là tác dụng phụ. Cần xác định rõ thành phần nào điều phối chúng và phạm vi nào phải nhất quán.

Controller không nên tự chia một nghiệp vụ thành nhiều câu lệnh ghi rời rạc nếu điều đó làm mất tính nguyên tử. Model hoặc application service thường là nơi điều phối trường hợp sử dụng và ranh giới giao dịch.

Ví dụ, tạo đơn hàng có thể cần giữ tồn kho và lưu đơn hàng. Nếu hai thao tác thành công hoặc thất bại độc lập, ứng dụng có thể tạo đơn mà không giữ được hàng. Việc xác định transaction boundary, xử lý cạnh tranh và phục hồi lỗi cần thuộc thiết kế nghiệp vụ và lưu trữ, không nên bị quyết định ngẫu nhiên bởi cách một Controller trả response.

### 2.6. Khả năng kiểm thử độc lập

Ranh giới tốt giúp kiểm thử một trách nhiệm mà không phải khởi động toàn bộ hệ thống.

- Có thể kiểm tra quy tắc chuyển trạng thái đơn hàng bằng đối tượng nghiệp vụ và dữ liệu đầu vào.
- Có thể kiểm tra Controller bằng mock dịch vụ để xác minh việc điều phối, binding và phản hồi.
- Có thể kiểm tra View bằng dữ liệu mẫu để xác minh cách hiển thị và escape đầu ra.
- Có thể kiểm tra tích hợp để xác nhận repository và transaction hoạt động đúng với cơ sở dữ liệu.

Nếu muốn kiểm tra một quy tắc giá đơn giản mà phải dựng Servlet container, template engine, cơ sở dữ liệu và session, đó là dấu hiệu quy tắc đang phụ thuộc vào quá nhiều chi tiết.

### 2.7. Ranh giới tin cậy và bảo mật

Ranh giới kiến trúc cũng là nơi dữ liệu đi từ vùng ít tin cậy sang vùng được ứng dụng kiểm soát. Dữ liệu từ trình duyệt không đáng tin chỉ vì nó đã được binding thành một đối tượng Java.

Các câu hỏi cần đặt ra:

- Dữ liệu nào được phép đến từ client?
- Trường nào phải được xác định lại từ nguồn tin cậy ở máy chủ?
- Quyền truy cập tài nguyên được kiểm tra ở đâu?
- Dữ liệu động được escape tại nơi nào trước khi đưa vào HTML?
- Câu truy vấn được tham số hóa ở lớp truy cập dữ liệu như thế nào?

Ẩn nút trên View không thay thế kiểm tra quyền tại máy chủ. DTO đầu vào giúp giới hạn trường được bind, nhưng không thay thế xác thực, phân quyền hoặc kiểm tra quy tắc nghiệp vụ.

## 3. Các dấu hiệu thường gặp khi ranh giới bị vi phạm

Các dấu hiệu dưới đây là **code smell** để bắt đầu điều tra, không phải quy tắc cứng rằng cứ xuất hiện là thiết kế sai. Cần xem xét tần suất, mức độ phức tạp và tác động khi thay đổi.

### 3.1. Fat Controller: Controller chứa nghiệp vụ

Controller có nhiều nhánh điều kiện, công thức tính tiền, quy tắc phân quyền theo nghiệp vụ, truy vấn và cập nhật dữ liệu. Phương thức xử lý request dài đến mức khó nhận ra luồng chính.

Ví dụ:

~~~java
@PostMapping("/orders")
public String create(OrderForm form) {
    Product product = productRepository.findById(form.getProductId())
            .orElseThrow();

    if (product.getStock() < form.getQuantity()) {
        return "orders/out-of-stock";
    }

    BigDecimal total = product.getPrice()
            .multiply(BigDecimal.valueOf(form.getQuantity()));

    if (form.getCouponCode() != null
            && form.getCouponCode().equals("SAVE10")) {
        total = total.multiply(new BigDecimal("0.90"));
    }

    Order order = new Order(product, form.getQuantity(), total);
    orderRepository.save(order);
    product.setStock(product.getStock() - form.getQuantity());

    return "redirect:/orders/" + order.getId();
}
~~~

Controller trên vừa đọc dữ liệu, kiểm tra tồn kho, tính giảm giá, tạo đơn và thay đổi tồn kho. Các quy tắc này khó dùng lại cho API hoặc tác vụ nền, và khó kiểm thử độc lập.

Hướng điều chỉnh là chuyển thao tác tạo đơn vào một dịch vụ nghiệp vụ. Controller giữ phần tiếp nhận request, chuyển dữ liệu thành command, gọi dịch vụ và chọn phản hồi.

### 3.2. Smart View: View tự quyết định nghiệp vụ

View không chỉ trình bày dữ liệu mà còn:

- Tính giá cuối cùng hoặc tự áp dụng mã giảm giá.
- Tự quyết định người dùng có được phép thực hiện thao tác hay không.
- Gọi repository hoặc truy vấn dữ liệu.
- Tự thay đổi trạng thái nghiệp vụ khi người dùng nhấn nút.

Một biểu thức điều kiện để ẩn hoặc hiện phần tử theo dữ liệu đã được Controller cung cấp là bình thường. Vấn đề là khi View trở thành nơi quyết định quy tắc có hiệu lực. Ví dụ, View có thể ẩn nút hủy đơn khi trạng thái không phù hợp để cải thiện trải nghiệm, nhưng Model vẫn phải từ chối lệnh hủy không hợp lệ.

### 3.3. Anemic Model hoặc Model chỉ làm nhiệm vụ chuyển tiếp

Một dấu hiệu khác là các lớp Model chỉ chứa getter/setter hoặc dữ liệu thô, trong khi mọi quy tắc bị dồn vào Controller hoặc một lớp tiện ích tổng quát. Điều này có thể làm trạng thái nghiệp vụ dễ bị thay đổi từ nhiều nơi.

Tuy nhiên, không nên kết luận mọi entity ít hành vi đều sai. Có ứng dụng sử dụng mô hình transaction script hoặc application service với entity đơn giản và vẫn có ranh giới tốt. Cần đánh giá xem quy tắc có được tập trung, bảo vệ và kiểm thử nhất quán hay không, thay vì bắt buộc mọi entity phải có nhiều phương thức.

### 3.4. Model phụ thuộc vào HTTP hoặc giao diện

Nếu lớp nghiệp vụ cần biết URL, session, cookie, template hoặc mã trạng thái HTTP để quyết định có cho phép thao tác hay không, chi tiết trình bày đã rò vào Model.

Ví dụ không phù hợp:

~~~java
public Order create(HttpServletRequest request) {
    String customerId = request.getSession()
            .getAttribute("customerId").toString();
    // Thực hiện quy tắc tạo đơn...
}
~~~

Model nên nhận dữ liệu có ý nghĩa nghiệp vụ như `customerId` và `CreateOrderCommand`. Controller hoặc lớp xác thực ở ranh giới web chịu trách nhiệm lấy danh tính từ ngữ cảnh request và truyền thông tin đã xác thực vào trường hợp sử dụng.

### 3.5. Controller hoặc View biết cấu trúc lưu trữ quá sâu

Controller viết SQL, điều khiển transaction thủ công hoặc truy cập trực tiếp các trường nội bộ của ORM để xây dựng phản hồi. View nhận một entity lớn rồi truy cập sâu vào quan hệ lazy-loaded, khiến lúc render có thể phát sinh nhiều truy vấn ngoài dự kiến.

Hãy xem xét việc đưa truy cập dữ liệu vào repository và chuẩn bị dữ liệu hiển thị ở tầng điều phối phù hợp. Tránh để template vô tình quyết định lúc nào cần tải dữ liệu từ cơ sở dữ liệu.

### 3.6. Quy tắc bị sao chép giữa nhiều điểm vào

Trang web, API và tác vụ nền đều có đoạn mã riêng để tính giá hoặc kiểm tra trạng thái đơn hàng. Một quy tắc thay đổi đòi hỏi cập nhật nhiều nơi.

Đây là dấu hiệu quy tắc chưa có chủ sở hữu rõ. Hãy gom quy tắc về Model hoặc dịch vụ nghiệp vụ mà các điểm vào có thể gọi chung.

### 3.7. Lỗi nghiệp vụ bị gắn chặt với phản hồi HTTP

Model trả về `HttpServletResponse`, mã 404 hoặc chuỗi HTML để biểu thị lỗi không tìm thấy sản phẩm. Điều đó khiến cùng một nghiệp vụ khó dùng từ API, tác vụ nền hoặc ứng dụng khác.

Model nên biểu diễn kết quả hoặc lỗi bằng khái niệm có ý nghĩa trong ứng dụng, chẳng hạn `ProductNotFound` hoặc `OrderRuleViolation`. Controller ánh xạ lỗi đó sang HTTP status, trang lỗi hoặc JSON tùy điểm truy cập.

### 3.8. Phụ thuộc vòng và thay đổi lan truyền

Ví dụ, Controller gọi View helper, View helper gọi lại dịch vụ nghiệp vụ, rồi dịch vụ lại gọi thành phần web để lấy session. Một thay đổi nhỏ có thể buộc sửa nhiều lớp và làm phát sinh vòng phụ thuộc.

Hãy lần theo đồ thị phụ thuộc. Thành phần điều phối ở ranh giới web có thể gọi vào nghiệp vụ; Model không nên gọi ngược lên Controller hoặc View. Khi cần thông tin từ bên ngoài, truyền nó qua tham số hoặc một interface phù hợp.

## 4. Phân biệt phối hợp hợp lệ với vi phạm ranh giới

Không phải mọi tương tác chéo đều là vấn đề. MVC vốn là mô hình phối hợp nhiều vai trò.

| Tình huống | Đánh giá | Lý do |
|---|---|---|
| Controller gọi `OrderService.create(command)` | Hợp lệ | Controller điều phối và chuyển lệnh nghiệp vụ |
| Controller nhận kết quả rồi chuẩn bị view model | Hợp lệ | Đây là dữ liệu dành cho phản hồi |
| View hiển thị lỗi validation đã được cung cấp | Hợp lệ | View trình bày kết quả kiểm tra |
| View ẩn nút theo quyền hoặc trạng thái đã được cung cấp | Hợp lệ như hỗ trợ trải nghiệm | Máy chủ vẫn phải kiểm tra quyền và quy tắc khi nhận lệnh |
| Model dùng repository để đọc và lưu trạng thái | Hợp lệ | Model cần cơ chế lưu trữ để thực hiện trường hợp sử dụng |
| Model đọc trực tiếp `HttpServletRequest` | Dấu hiệu vi phạm | Nghiệp vụ phụ thuộc vào giao thức web |
| View gọi repository để lấy giá | Dấu hiệu vi phạm | Trình bày sở hữu truy cập dữ liệu |
| Controller tự tính chính sách giảm giá | Dấu hiệu vi phạm | Quy tắc nghiệp vụ nằm ở ranh giới request |
| Entity ORM được trả thẳng ra API mà không xem xét trường dữ liệu | Cần đánh giá | Có thể làm lộ dữ liệu và gắn hợp đồng API với cấu trúc lưu trữ |

Điểm phân biệt quan trọng là **ai có quyền quyết định**. Controller có thể kiểm tra định dạng request để báo lỗi sớm, nhưng Model vẫn phải bảo vệ bất biến nghiệp vụ. View có thể ẩn một thao tác không phù hợp, nhưng máy chủ phải từ chối lệnh nếu client tự gửi request.

## 5. Ví dụ chẩn đoán một chức năng đặt hàng

Giả sử ứng dụng có ba cách tạo đơn: trang web, API cho ứng dụng di động và tác vụ nhập đơn từ file. Sau một thời gian, nhóm phát triển nhận thấy mỗi luồng có công thức tính tổng tiền hơi khác nhau.

### Bước 1: Lần theo cùng một trường hợp sử dụng

Vẽ lại luồng xử lý của cả ba điểm vào và đánh dấu nơi mỗi quy tắc được thực hiện. Nếu web tính giảm giá trong Controller, API tính trong một helper riêng và tác vụ nền tính trong batch processor, quy tắc đã bị phân tán.

~~~mermaid
flowchart TD
    W[Web Controller] --> W1[Tính giảm giá]
    A[API Controller] --> A1[Tính giảm giá khác]
    B[Batch Import] --> B1[Tính giảm giá riêng]
    W1 --> D[(Order Repository)]
    A1 --> D
    B1 --> D
~~~

Sơ đồ cho thấy ba điểm vào đang tự sở hữu cùng một quy tắc. Kết quả là dữ liệu lưu xuống có thể không nhất quán dù cùng một sản phẩm và mã giảm giá.

### Bước 2: Xác định quy tắc thuộc về đâu

Chính sách giảm giá là quy tắc nghiệp vụ. Đặt nó trong một thành phần nghiệp vụ dùng chung, ví dụ `PricingPolicy` được `OrderService` sử dụng. Các Controller và batch processor chỉ chuyển dữ liệu đầu vào phù hợp.

~~~mermaid
flowchart TD
    W[Web Controller] --> S[Order Service]
    A[API Controller] --> S
    B[Batch Import] --> S
    S --> P[Pricing Policy]
    S --> R[(Order Repository)]
~~~

### Bước 3: Thiết lập hợp đồng đầu vào rõ ràng

Mỗi điểm vào có thể có DTO riêng vì hình dạng request khác nhau. Sau khi kiểm tra định dạng và xác thực danh tính, chúng chuyển thành command chung có ý nghĩa nghiệp vụ.

~~~java
public record CreateOrderCommand(
        String customerId,
        String productId,
        int quantity,
        String couponCode
) {}
~~~

Command không cần biết dữ liệu đến từ biểu mẫu HTML, JSON hay file CSV. Nó biểu diễn ý định tạo đơn với các thông tin mà nghiệp vụ cần.

### Bước 4: Đưa quy tắc vào dịch vụ nghiệp vụ

~~~java
public class OrderService {
    private final ProductRepository products;
    private final OrderRepository orders;
    private final PricingPolicy pricingPolicy;

    public OrderReceipt create(CreateOrderCommand command) {
        Product product = products.getRequired(command.productId());

        if (!product.canSupply(command.quantity())) {
            throw new OrderRuleViolation("out_of_stock");
        }

        Money total = pricingPolicy.calculate(
                product,
                command.quantity(),
                command.couponCode()
        );

        Order order = Order.create(
                command.customerId(),
                product,
                command.quantity(),
                total
        );
        orders.save(order);

        return new OrderReceipt(order.getId(), total);
    }
}
~~~

Đây là mã minh họa về ranh giới. Trong hệ thống có nhiều thao tác ghi hoặc cập nhật tồn kho đồng thời, cần bổ sung transaction phù hợp, cơ chế chống đặt vượt tồn kho và xử lý tranh chấp. Việc kiểm tra tồn kho đơn thuần rồi mới lưu có thể gặp race condition nếu nhiều request chạy cùng lúc.

### Bước 5: Để mỗi Controller chuyển kết quả thành phản hồi riêng

Web có thể chuyển hướng đến trang chi tiết đơn hàng. API có thể trả JSON với mã 201. Batch processor có thể ghi nhận kết quả cho từng dòng dữ liệu. Các cách phản hồi khác nhau không làm thay đổi cách tính giá hoặc quy tắc tạo đơn.

Đây là kết quả mong đợi khi ranh giới rõ: nhiều điểm vào có thể dùng chung nghiệp vụ nhưng vẫn giữ cách giao tiếp phù hợp với từng kênh.

## 6. Tiêu chí xem xét dữ liệu đi qua từng ranh giới

Khi kiểm tra một luồng request, hãy xem dữ liệu tại từng chặng thay đổi ra sao.

### Từ client đến Controller

- Chỉ nhận các trường mà chức năng cho phép.
- Chuyển kiểu dữ liệu và kiểm tra định dạng, giới hạn kích thước, trường bắt buộc.
- Xác thực danh tính và kiểm tra quyền tại máy chủ theo tài nguyên đang thao tác.
- Không tin giá, vai trò, chủ sở hữu hoặc trạng thái nhạy cảm do client tự khai báo.

### Từ Controller đến Model

- Chuyển dữ liệu thô thành command hoặc tham số có ý nghĩa nghiệp vụ.
- Không truyền `HttpServletRequest`, đối tượng template hoặc chi tiết giao diện xuống Model.
- Truyền thông tin người dùng đã được xác thực nếu nghiệp vụ cần biết chủ thể thực hiện.
- Để Model kiểm tra lại các bất biến nghiệp vụ, kể cả khi Controller đã validation.

### Từ Model đến kho dữ liệu

- Repository chịu trách nhiệm chi tiết truy vấn và ánh xạ lưu trữ.
- Dùng truy vấn có tham số thay vì nối chuỗi dữ liệu đầu vào vào SQL.
- Xác định transaction boundary cho các thao tác cần nhất quán.
- Xem xét đồng thời, khóa hoặc cơ chế cập nhật có điều kiện khi nhiều request cùng sửa trạng thái.

### Từ Controller đến View

- Cung cấp dữ liệu vừa đủ cho màn hình.
- Dùng view model khi cấu trúc hiển thị khác với entity nghiệp vụ.
- Chuyển lỗi thành thông báo và mã lỗi phù hợp với kênh giao tiếp.
- Đảm bảo View escape dữ liệu động theo đúng ngữ cảnh HTML.

## 7. Quy trình thực tế để tìm và sửa ranh giới bị vi phạm

Không cần bắt đầu bằng việc đổi tên hoặc di chuyển hàng loạt lớp. Hãy chọn một chức năng cụ thể và làm theo trình tự sau.

1. **Chọn một luồng người dùng:** Ví dụ tạo đơn, cập nhật hồ sơ hoặc hủy đơn. Ghi lại request, kết quả và các tác dụng phụ.
2. **Lần theo đường đi của dữ liệu:** Từ URL và tham số, qua Controller, Model, repository rồi đến View hoặc response.
3. **Đánh dấu nơi ra quyết định:** Ghi rõ lớp nào quyết định quy tắc nghiệp vụ, lớp nào chỉ chuyển dữ liệu và lớp nào trình bày.
4. **Tìm dấu hiệu phụ thuộc sai chiều:** Tìm kiểu HTTP trong Model, truy vấn trong View, quy tắc nghiệp vụ trong Controller và vòng phụ thuộc.
5. **Xác định một chủ sở hữu cho mỗi quy tắc:** Chọn nơi phù hợp với ý nghĩa của quy tắc, sau đó để các điểm vào gọi chung.
6. **Thiết lập hợp đồng dữ liệu:** Tách dữ liệu request, command nghiệp vụ và dữ liệu trình bày khi các mục đích khác nhau rõ ràng.
7. **Chuyển một trách nhiệm mỗi lần:** Giữ hành vi bên ngoài ổn định trong khi chuyển quy tắc hoặc tác dụng phụ sang thành phần phù hợp.
8. **Kiểm thử ở từng ranh giới:** Kiểm tra quy tắc nghiệp vụ, điều phối Controller, hiển thị View và tích hợp lưu trữ.
9. **Đánh giá lại thay đổi:** Một thay đổi nghiệp vụ tương tự có còn buộc sửa nhiều màn hình hoặc nhiều điểm vào không?

Khi refactor, nên giữ một đường đi hoạt động được sau mỗi thay đổi nhỏ. Điều đó giúp xác định lỗi phát sinh ở bước nào và tránh việc chuyển trách nhiệm quá rộng cùng lúc.

## 8. Ma trận kiểm tra nhanh

Bảng dưới đây có thể dùng trong code review hoặc khi khảo sát một module MVC.

| Câu hỏi | Dấu hiệu ranh giới tốt | Dấu hiệu cần điều tra |
|---|---|---|
| Controller làm gì? | Tiếp nhận, chuyển đổi, điều phối và chọn phản hồi | Chứa công thức, chính sách hoặc truy vấn phức tạp |
| View làm gì? | Trình bày dữ liệu và lỗi đã được chuẩn bị | Tự quyết định nghiệp vụ hoặc đọc dữ liệu |
| Model làm gì? | Bảo vệ trạng thái và quy tắc ứng dụng | Phụ thuộc HTTP, HTML hoặc template |
| Dữ liệu đi qua các lớp thế nào? | Có hợp đồng rõ theo mục đích | Entity, request và view data bị dùng lẫn lộn |
| Quy tắc được đặt ở đâu? | Có chủ sở hữu rõ, các kênh dùng chung | Bị sao chép trong nhiều điểm vào |
| Tác dụng phụ được điều phối thế nào? | Có nơi quản lý transaction và lỗi | Ghi dữ liệu rải rác trong Controller hoặc View |
| Có thể kiểm thử độc lập không? | Quy tắc có thể kiểm tra không cần web server | Mọi test phải dựng toàn bộ ứng dụng |
| Bảo mật được thực thi ở đâu? | Kiểm tra quyền ở máy chủ, escape đầu ra, truy vấn an toàn | Dựa vào giao diện hoặc dữ liệu client tự khai báo |

Không nên dùng bảng như một thang điểm máy móc. Một dấu hiệu đơn lẻ có thể là lựa chọn có chủ đích trong ứng dụng nhỏ. Hãy ưu tiên những vấn đề gây lỗi thực tế, làm quy tắc không nhất quán hoặc khiến thay đổi lan rộng.

## 9. Những ngộ nhận khi đánh giá ranh giới

### “Mỗi vai trò phải là một lớp duy nhất”

MVC mô tả vai trò kiến trúc, không quy định số lượng lớp. Model có thể gồm entity, service, repository và policy. Controller có thể có nhiều lớp theo nhóm chức năng. View có thể gồm nhiều template và component. Quan trọng là mỗi phần có trách nhiệm và hợp đồng rõ.

### “Tách package là đã tách trách nhiệm”

Một lớp tên `OrderService` đặt trong package `model` vẫn có thể phụ thuộc vào `HttpServletRequest`. Một template đặt trong package `view` vẫn có thể gọi repository. Cần xem nội dung và hướng phụ thuộc, không chỉ nhìn cấu trúc thư mục.

### “Controller không được chứa bất kỳ logic nào”

Controller cần có logic điều phối: chọn nhánh phản hồi, chuyển đổi dữ liệu request, xử lý lỗi binding và chọn redirect hoặc view. Điều cần tránh là để Controller sở hữu chính sách nghiệp vụ và chi tiết lưu trữ.

### “Validation chỉ cần thực hiện một lần”

Validation ở ranh giới request kiểm tra dữ liệu có đúng cấu trúc và định dạng không. Model vẫn phải bảo vệ bất biến nghiệp vụ vì một trường hợp sử dụng có thể được gọi từ nhiều kênh khác nhau. Hai lớp kiểm tra này có mục đích khác nhau.

### “DTO luôn tốt hơn entity”

DTO hữu ích khi hợp đồng bên ngoài khác với trạng thái nội bộ hoặc cần giới hạn dữ liệu được gửi/nhận. Với một ứng dụng rất nhỏ, dùng chung một kiểu dữ liệu có thể hợp lý. Quyết định nên dựa trên rủi ro phụ thuộc, bảo mật và chi phí thay đổi, không phải số lượng lớp.

## 10. Checklist trước khi kết luận ranh giới bị vi phạm

Trước khi đề xuất refactor, hãy xác nhận các điểm sau:

- [ ] Đã lần theo một luồng request thực tế từ đầu vào đến phản hồi.
- [ ] Đã phân biệt kiểm tra định dạng request với quy tắc nghiệp vụ.
- [ ] Đã xác định nơi sở hữu từng quy tắc và trạng thái quan trọng.
- [ ] Đã kiểm tra Controller có phụ thuộc quá sâu vào lưu trữ hoặc chính sách nghiệp vụ không.
- [ ] Đã kiểm tra View có truy cập dữ liệu hoặc quyết định nghiệp vụ không.
- [ ] Đã kiểm tra Model có phụ thuộc HTTP, session hoặc chi tiết trình bày không.
- [ ] Đã xem xét hợp đồng DTO, command và view model có phù hợp với mục đích không.
- [ ] Đã xác định nơi quản lý transaction và các tác dụng phụ liên quan.
- [ ] Đã xem xét quyền truy cập, dữ liệu không đáng tin cậy và cách escape đầu ra.
- [ ] Đã xác định cách kiểm thử riêng từng trách nhiệm sau khi điều chỉnh.

## Kết luận

Ranh giới MVC được xem là rõ khi mỗi thành phần có trách nhiệm và quyền quyết định phù hợp, phụ thuộc vào hợp đồng cần thiết, trao đổi dữ liệu có mục đích và có thể được kiểm thử trong phạm vi hợp lý. Các dấu hiệu như Fat Controller, Smart View, Model phụ thuộc HTTP, truy vấn nằm trong template, quy tắc bị sao chép và lỗi nghiệp vụ gắn với mã HTTP đều cho thấy cần điều tra sâu hơn. Hãy lần theo một luồng request, xác định nơi ra quyết định và quyền sở hữu dữ liệu, sau đó chuyển từng trách nhiệm về đúng thành phần. Cách đánh giá dựa trên tác động thay đổi và hành vi thực tế giúp MVC duy trì được sự tách biệt giữa nghiệp vụ, trình bày và tiếp nhận tương tác khi ứng dụng phát triển.
