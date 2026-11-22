# Phân rã monolith và ranh giới dịch vụ trên AWS

Một ứng dụng monolith thường bắt đầu như một cách triển khai hợp lý: các chức năng nghiệp vụ nằm trong cùng một codebase, dùng chung quy trình build và thường cùng truy cập một cơ sở dữ liệu. Cách tổ chức này giúp nhóm phát triển khởi đầu nhanh, dễ chạy thử và thực hiện giao dịch trong một tiến trình. Khi sản phẩm lớn lên, các nhóm phải thay đổi cùng một codebase, triển khai một phần nhỏ cũng có thể cần phát hành toàn bộ ứng dụng, còn một lỗi hoặc đợt tải tăng ở một chức năng có thể ảnh hưởng các chức năng khác.

Phân rã monolith thành các dịch vụ giúp tổ chức hệ thống theo năng lực nghiệp vụ, cho phép từng phần phát triển và mở rộng độc lập. Tuy nhiên, việc tách ứng dụng thành nhiều tiến trình cũng tạo ra giao tiếp qua mạng, lỗi phân tán, dữ liệu không đồng bộ và yêu cầu vận hành mới. Nếu chia theo bảng dữ liệu hoặc lớp kỹ thuật mà không có ranh giới nghiệp vụ rõ ràng, tổ chức có thể tạo ra một distributed monolith khó thay đổi hơn ứng dụng ban đầu.

Trên AWS, có nhiều cách triển khai các ranh giới đó: Amazon ECS hoặc Amazon EKS cho dịch vụ chạy liên tục, AWS Lambda cho xử lý theo sự kiện, Amazon API Gateway hoặc Application Load Balancer cho giao tiếp HTTP, Amazon SQS, Amazon SNS và Amazon EventBridge cho tích hợp bất đồng bộ, cùng các dịch vụ dữ liệu phù hợp với quyền sở hữu của từng miền nghiệp vụ. Dịch vụ AWS chỉ là phương tiện triển khai; ranh giới đúng phải bắt đầu từ cách doanh nghiệp tạo giá trị và quản lý dữ liệu.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: thiết kế ứng dụng có khả năng mở rộng, an toàn, dễ vận hành và kiểm soát chi phí. Trọng tâm là nhận diện giới hạn của monolith, xác định bounded context, chọn cách phân rã, di chuyển từng phần bằng Strangler Fig và thiết kế giao tiếp, dữ liệu, triển khai trên AWS.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện khi nào monolith cần được tái cấu trúc và khi nào vẫn nên giữ kiến trúc đơn khối.
- Phân biệt modular monolith, service-oriented architecture và microservices.
- Xác định service boundary dựa trên business capability, bounded context, quyền sở hữu dữ liệu và nhịp thay đổi.
- Phân rã một monolith theo miền nghiệp vụ thay vì tách máy móc theo lớp kỹ thuật hoặc bảng dữ liệu.
- Thiết kế giao tiếp đồng bộ và bất đồng bộ bằng API Gateway, load balancer, SQS, SNS và EventBridge.
- Lập kế hoạch chuyển đổi từng phần bằng Strangler Fig, kiểm soát dữ liệu và tránh dual-write.
- Chọn ECS, EKS hoặc Lambda theo đặc tính workload và năng lực vận hành của đội ngũ.
- Xử lý tính nhất quán, idempotency, timeout, retry, saga, quan sát hệ thống và bảo mật giữa các dịch vụ.

## 2. Monolith và lý do cần phân rã

### 2.1. Monolith là gì?

Monolith là ứng dụng được xây dựng và triển khai như một đơn vị. Một monolith có thể được tổ chức nội bộ rất tốt với module, interface và quy tắc phụ thuộc rõ ràng. Vì vậy, monolith không đồng nghĩa với code lộn xộn hoặc thiết kế kém.

Ví dụ một ứng dụng thương mại điện tử có thể chứa:

- Quản lý khách hàng và hồ sơ.
- Danh mục sản phẩm và giá.
- Giỏ hàng và đơn hàng.
- Thanh toán.
- Tồn kho.
- Vận chuyển.
- Thông báo và chăm sóc khách hàng.

Các chức năng có thể chạy trong một ứng dụng Spring Boot, dùng chung một relational database. Khi một request đặt hàng đến, ứng dụng gọi các module nội bộ và ghi nhiều bảng trong cùng một transaction.

### 2.2. Dấu hiệu monolith trở thành nút thắt

Không nên phân rã chỉ vì microservices đang phổ biến. Hãy tìm bằng chứng về vấn đề thực tế:

- **Triển khai bị khóa chéo:** thay đổi nhỏ ở một module buộc toàn bộ ứng dụng phải build, kiểm thử và phát hành.
- **Mở rộng không hiệu quả:** chức năng tìm kiếm có tải cao khiến phải tăng toàn bộ số instance dù thanh toán ít tải.
- **Nhịp thay đổi khác nhau:** nhóm thanh toán cần phát hành thường xuyên nhưng bị ràng buộc bởi lịch release của nhóm danh mục.
- **Lỗi lan truyền:** một tác vụ báo cáo nặng làm cạn connection pool hoặc thread pool, ảnh hưởng luồng đặt hàng.
- **Quyền sở hữu không rõ:** nhiều nhóm cùng sửa một module hoặc cùng thay đổi các bảng dữ liệu.
- **Khó chọn công nghệ:** một phần workload cần xử lý theo sự kiện hoặc chạy batch độc lập nhưng bị buộc vào runtime của monolith.

Các triệu chứng này cần được đo lường bằng thời gian build/deploy, tần suất phát hành, tỷ lệ rollback, độ trễ, mức sử dụng tài nguyên, tần suất xung đột code và thời gian khôi phục sự cố. Nếu nguyên nhân chính là module coupling trong code, một modular monolith có thể giải quyết vấn đề với chi phí thấp hơn.

### 2.3. Khi nào nên giữ monolith?

Monolith thường phù hợp khi:

- Sản phẩm còn nhỏ và miền nghiệp vụ chưa ổn định.
- Nhóm phát triển ít người, có thể phối hợp tốt trong một codebase.
- Giao dịch cần tính nguyên tử trên nhiều phần dữ liệu và chưa có nhu cầu phân tán.
- Tải chưa đòi hỏi mở rộng độc lập theo từng chức năng.
- Năng lực vận hành, giám sát và xử lý sự cố phân tán chưa sẵn sàng.

Có thể bắt đầu bằng modular monolith: chia code thành module theo miền nghiệp vụ, giới hạn truy cập dữ liệu, dùng interface rõ ràng và ngăn phụ thuộc vòng. Khi một miền có lý do kinh doanh đủ mạnh để triển khai độc lập, module đó đã có ranh giới tốt hơn để tách thành service.

## 3. Chọn mô hình kiến trúc

### 3.1. Modular monolith

Modular monolith vẫn được triển khai như một ứng dụng, nhưng cấu trúc bên trong có các module nghiệp vụ với API nội bộ rõ ràng. Mỗi module sở hữu logic và có quy tắc truy cập dữ liệu riêng. Module khác không được truy cập trực tiếp bảng hoặc class nội bộ nếu không thông qua hợp đồng được công bố.

Ưu điểm:

- Đơn giản khi triển khai và vận hành.
- Có thể dùng transaction trong cùng tiến trình.
- Dễ tái cấu trúc ranh giới trước khi phải xử lý lỗi mạng.
- Ít chi phí hạ tầng và quan sát hơn nhiều service.

Hạn chế là module chưa thể scale hoặc release độc lập. Nếu các module được cô lập tốt, đây có thể là bước trung gian an toàn trước khi tách dịch vụ.

### 3.2. Service-oriented architecture và microservices

Service-oriented architecture (SOA) tổ chức hệ thống thành các dịch vụ có hợp đồng giao tiếp. SOA có thể dùng dịch vụ có kích thước lớn và tích hợp qua nền tảng chung.

Microservices thường nhấn mạnh dịch vụ nhỏ theo miền nghiệp vụ, sở hữu dữ liệu và vòng đời triển khai riêng, có thể được phát triển bởi nhóm chịu trách nhiệm rõ ràng. Một service không nhất thiết phải nhỏ về số dòng code; nó cần có phạm vi nghiệp vụ đủ gắn kết và ít phụ thuộc trực tiếp vào service khác.

Không có một kích thước service chuẩn cho mọi hệ thống. Service quá lớn khó phát hành độc lập; service quá nhỏ làm tăng số lần gọi mạng, cấu hình, pipeline và điểm lỗi. Ranh giới tốt giảm nhu cầu phối hợp thường xuyên giữa các nhóm.

### 3.3. So sánh lựa chọn

| Tiêu chí | Modular monolith | Microservices |
|---|---|---|
| Đơn vị triển khai | Một ứng dụng | Nhiều dịch vụ độc lập |
| Giao tiếp nội bộ | Lời gọi trong tiến trình và API module | API hoặc message qua mạng |
| Giao dịch dữ liệu | Dễ dùng transaction cục bộ | Thường cần eventual consistency hoặc saga |
| Mở rộng | Chủ yếu mở rộng cả ứng dụng | Có thể mở rộng từng service |
| Phát hành | Một lịch phát hành chung | Có thể phát hành theo service |
| Vận hành | Ít thành phần phân tán hơn | Cần quản lý mạng, retry, quan sát và bảo mật giữa service |
| Phù hợp | Sản phẩm nhỏ đến trung bình, miền còn thay đổi | Miền nghiệp vụ ổn định, đội ngũ và nhu cầu độc lập đủ rõ |

Chọn kiến trúc theo mục tiêu kinh doanh và chi phí vận hành tổng thể. Số lượng service không phải thước đo trực tiếp của chất lượng kiến trúc.

## 4. Tìm ranh giới dịch vụ từ miền nghiệp vụ

### 4.1. Bắt đầu từ business capability

Business capability là khả năng mà tổ chức cần thực hiện để tạo ra giá trị, ví dụ quản lý danh mục, xử lý đơn hàng, thu tiền hoặc giao hàng. Capability thường bền vững hơn sơ đồ tổ chức hoặc tên nhóm kỹ thuật.

Khi phân tích, hãy hỏi:

- Khách hàng hoặc bộ phận vận hành đang cố hoàn thành công việc gì?
- Quy tắc nghiệp vụ nào thay đổi cùng nhau?
- Dữ liệu nào cần được một nhóm chịu trách nhiệm chính?
- Phần nào có tải, yêu cầu sẵn sàng hoặc bảo mật khác biệt?
- Một thay đổi ở miền này có cần phối hợp với miền khác thường xuyên không?

Các câu trả lời giúp xác định nhóm chức năng có tính gắn kết cao và các điểm phụ thuộc cần giảm.

### 4.2. Bounded context trong Domain-Driven Design

Bounded context là ranh giới trong đó một mô hình miền và ngôn ngữ nghiệp vụ có ý nghĩa nhất quán. Cùng một từ có thể mang ý nghĩa khác nhau ở các miền khác nhau.

Ví dụ, từ **Customer** trong hệ thống thương mại điện tử có thể có nhiều góc nhìn:

- Trong miền tài khoản, Customer là danh tính đăng nhập, thông tin liên hệ và trạng thái xác thực.
- Trong miền đơn hàng, Customer là bên mua gắn với địa chỉ nhận hàng và lịch sử mua.
- Trong miền hỗ trợ, Customer là hồ sơ phục vụ tra cứu và xử lý yêu cầu.

Các góc nhìn có thể tham chiếu cùng một mã khách hàng, nhưng không nên buộc tất cả miền dùng chung một model và bảng dữ liệu. Mỗi bounded context có thể duy trì mô hình phù hợp với quy tắc riêng.

Một bounded context có thể tương ứng với một service, nhưng không bắt buộc. Hai context có thể được triển khai cùng một service ở giai đoạn đầu nếu chúng có cùng chủ sở hữu và yêu cầu vận hành. Ngược lại, một context lớn có thể cần nhiều thành phần triển khai nhưng vẫn có một ranh giới dữ liệu và nghiệp vụ rõ ràng.

### 4.3. Dùng event storming và domain map

Event storming là kỹ thuật làm việc nhóm để mô tả các sự kiện nghiệp vụ đã xảy ra, hành động tạo ra sự kiện, người hoặc hệ thống kích hoạt và quy tắc liên quan. Ví dụ:

- Customer registered.
- Product price changed.
- Order placed.
- Payment authorized.
- Inventory reserved.
- Shipment dispatched.

Từ chuỗi sự kiện, nhóm tìm ra các command, aggregate, policy và bounded context. Hãy đánh dấu các điểm mà một miền cần thông tin từ miền khác, sau đó chọn cách giao tiếp phù hợp.

Domain map có thể ghi lại:

- Context và trách nhiệm chính.
- Nhóm sở hữu và người chịu trách nhiệm nghiệp vụ.
- Dữ liệu chính mà context quản lý.
- API hoặc event được cung cấp.
- Context phụ thuộc và mức độ phụ thuộc.
- Các hệ thống cũ cần được tích hợp trong giai đoạn chuyển đổi.

### 4.4. Nguyên tắc xác định service boundary

Một ranh giới dịch vụ tốt thường có những đặc điểm:

1. **Nghiệp vụ gắn kết:** các hành vi bên trong cùng phục vụ một mục tiêu hoặc capability.
2. **Dữ liệu có chủ sở hữu:** một service chịu trách nhiệm ghi và duy trì dữ liệu cốt lõi của miền.
3. **Hợp đồng rõ:** service khác truy cập qua API hoặc event được công bố, không đọc/ghi trực tiếp cơ sở dữ liệu nội bộ.
4. **Thay đổi tương đối độc lập:** quy tắc và lịch phát hành ít buộc phải phối hợp chéo.
5. **Có thể vận hành:** nhóm có khả năng triển khai, giám sát, xử lý lỗi và chịu trách nhiệm với service.
6. **Có kích thước hợp lý:** đủ lớn để tránh quá nhiều giao tiếp, đủ nhỏ để thay đổi mà không ảnh hưởng miền không liên quan.

Nếu hai service luôn phải phát hành cùng nhau, dùng chung transaction và thay đổi dữ liệu cùng nhau, hãy xem xét gộp chúng hoặc sửa lại ranh giới.

## 5. Ví dụ phân rã monolith thương mại điện tử

### 5.1. Trạng thái ban đầu

Giả sử monolith Spring Boot có các package và bảng:

- customer: hồ sơ khách hàng, địa chỉ.
- catalog: sản phẩm, danh mục, giá.
- order: đơn hàng và dòng hàng.
- payment: giao dịch thanh toán.
- inventory: số lượng tồn kho.
- shipping: vận đơn và trạng thái giao hàng.

Tất cả module dùng chung một relational database. Module Order có thể truy cập bảng Inventory và Payment trực tiếp. Khi tạo đơn, ứng dụng ghi order, trừ tồn kho và tạo payment trong một transaction lớn.

Điểm yếu không chỉ nằm ở một database. Vấn đề cốt lõi là ranh giới dữ liệu không rõ, một module có thể thay đổi trạng thái do module khác quản lý, và các nhóm không thể triển khai độc lập.

### 5.2. Đề xuất các bounded context

Một phương án ban đầu:

| Bounded context | Trách nhiệm | Dữ liệu sở hữu |
|---|---|---|
| Customer | Hồ sơ, liên hệ và trạng thái khách hàng | Customer profile, contact preferences |
| Catalog | Danh mục, mô tả, giá niêm yết | Product, category, catalog price |
| Order | Vòng đời đơn hàng, dòng hàng và trạng thái xử lý | Order, order item, order status |
| Payment | Ủy quyền, thu tiền, hoàn tiền và đối soát | Payment intent, transaction, refund |
| Inventory | Số lượng khả dụng, reservation và điều chỉnh tồn | Stock level, reservation |
| Shipping | Tạo vận đơn, theo dõi giao nhận | Shipment, tracking status |

Đây là một giả thuyết kiến trúc. Trước khi tách, cần xác minh cách doanh nghiệp vận hành. Ví dụ, nếu giá bán được chốt tại thời điểm đặt hàng, Order nên lưu snapshot giá và mô tả cần thiết của dòng hàng; nó không nên phụ thuộc vào việc Catalog luôn trả về giá hiện tại.

### 5.3. Quan hệ giữa các service

Khi một khách hàng đặt hàng, Order có thể cần xác thực dữ liệu giỏ hàng, kiểm tra tồn kho và yêu cầu thanh toán. Luồng minh họa:

~~~mermaid
flowchart TD
    C[Web hoặc Mobile] --> G[API Gateway hoặc ALB]
    G --> O[Order Service]
    O --> I[Inventory Service]
    O --> P[Payment Service]
    O --> E[EventBridge hoặc SQS]
    E --> S[Shipping Service]
    E --> N[Notification Service]
    K[Catalog Service] --> O
    U[Customer Service] --> O
~~~

Sơ đồ chỉ thể hiện các miền tham gia, không quy định mọi request đều phải gọi tuần tự tất cả service. Cần xác định dữ liệu nào phải kiểm tra ngay trong luồng đặt hàng và dữ liệu nào có thể cập nhật bất đồng bộ.

### 5.4. Đừng tách theo lớp kỹ thuật

Một cách chia thường gây vấn đề là tạo riêng User Interface Service, Business Logic Service và Database Service cho toàn hệ thống. Khi đó mọi thay đổi nghiệp vụ vẫn đi qua nhiều service chung, còn các service vẫn phải phối hợp để hoàn thành một chức năng. Ranh giới theo lớp kỹ thuật có thể phù hợp với một số kiến trúc SOA, nhưng không tự tạo ra quyền sở hữu nghiệp vụ độc lập.

Hãy tách theo capability và bounded context. Mỗi service cần có một mục đích nghiệp vụ mà nhóm sở hữu có thể giải thích rõ ràng.

## 6. Chiến lược di chuyển: Strangler Fig

### 6.1. Ý tưởng

Strangler Fig là cách hiện đại hóa theo từng phần. Thay vì viết lại toàn bộ monolith trong một lần, tổ chức đưa một chức năng mới ra service riêng, định tuyến request phù hợp sang service đó và dần giảm trách nhiệm của monolith.

Quy trình tổng quát:

1. Xác định một capability có ranh giới và rủi ro đủ rõ.
2. Tạo service mới cùng hợp đồng API hoặc event.
3. Chuẩn bị dữ liệu và cơ chế đồng bộ trong giai đoạn chuyển tiếp.
4. Định tuyến một phần request sang service mới.
5. So sánh kết quả, theo dõi lỗi và tăng dần lưu lượng.
6. Chuyển quyền ghi dữ liệu sang service mới khi đã sẵn sàng.
7. Loại bỏ chức năng cũ và các luồng tích hợp không còn dùng.

Mẫu này giúp giới hạn phạm vi mỗi lần thay đổi và cho phép rollback bằng cách chuyển routing về monolith khi điều kiện cho phép.

### 6.2. Chọn phần tách đầu tiên

Nên chọn một capability:

- Có giá trị kinh doanh hoặc lợi ích vận hành dễ đo.
- Ít phụ thuộc transaction với các module khác.
- Có đầu vào và đầu ra xác định.
- Có thể quan sát và kiểm thử độc lập.
- Có nhóm chịu trách nhiệm sau khi phát hành.

Ví dụ, Notification Service thường là ứng viên tốt vì gửi email/SMS có thể xử lý bất đồng bộ và ít cần transaction chung với Order. Catalog Read API cũng có thể là ứng viên nếu dữ liệu đọc có thể được đồng bộ và cache. Ngược lại, tách một phần nhỏ của quy trình thanh toán mà vẫn phụ thuộc nhiều vào transaction nội bộ có thể tạo ra rủi ro lớn.

### 6.3. Định tuyến request

Với HTTP, có thể dùng Amazon API Gateway hoặc Application Load Balancer làm điểm vào. Trong giai đoạn chuyển đổi, lớp routing có thể chuyển một số path hoặc nhóm request sang service mới, trong khi phần còn lại vẫn vào monolith.

Ví dụ:

| Request | Đích trong giai đoạn chuyển đổi |
|---|---|
| GET /catalog/* | Catalog Service |
| POST /orders | Monolith hoặc Order Service theo giai đoạn |
| GET /orders/* | Có thể đọc từ monolith trong thời gian đồng bộ |
| POST /legacy-checkout | Monolith cho đến khi luồng mới được xác minh |

Không nên chỉ đổi routing mà bỏ qua session, authentication, rate limit, request ID, timeout và định dạng lỗi. Cần giữ hợp đồng bên ngoài ổn định nếu client chưa thể thay đổi đồng thời.

### 6.4. Kế hoạch rollback

Trước mỗi lần tăng lưu lượng, xác định:

- Chỉ số nào cho phép tiếp tục, ví dụ error rate, latency và tỷ lệ xử lý thành công.
- Điều kiện dừng rollout.
- Cách chuyển routing về phiên bản trước.
- Cách xử lý request đã ghi dữ liệu ở service mới.
- Cách giữ dữ liệu nhất quán trong thời gian rollback.

Rollback code không tự đảo ngược dữ liệu. Nếu service mới đã ghi trạng thái khác với monolith, cần thiết kế quy trình đối soát hoặc bù trừ riêng.

## 7. Quyền sở hữu dữ liệu và nhất quán

### 7.1. Một service chịu trách nhiệm ghi dữ liệu miền

Trong microservices, database-per-service là nguyên tắc về quyền sở hữu logic: mỗi service chịu trách nhiệm thay đổi dữ liệu của miền mình. Điều này không nhất thiết yêu cầu mỗi service có một máy chủ database riêng ngay từ ngày đầu. Có thể dùng cùng một cluster được quản lý nhưng tách database/schema, credential và quyền truy cập; quan trọng là service khác không truy cập trực tiếp bảng nội bộ.

Ví dụ:

- Order Service sở hữu trạng thái đơn hàng.
- Payment Service sở hữu trạng thái thanh toán.
- Inventory Service sở hữu tồn kho và reservation.

Order có thể lưu paymentId hoặc trạng thái thanh toán được nhận qua event. Nó không được cập nhật trực tiếp bảng transaction của Payment.

### 7.2. Không dùng chung database như API ngầm

Nếu nhiều service cùng ghi một schema, thay đổi cột hoặc constraint ở một service có thể làm hỏng service khác mà không có thay đổi trong hợp đồng API. Đây là một dạng coupling ẩn.

Khi di chuyển dần:

1. Xác định service nào là chủ sở hữu cuối cùng của từng bảng hoặc tập dữ liệu.
2. Ngăn code mới truy cập trực tiếp bảng do miền khác sở hữu.
3. Cung cấp API hoặc event để consumer nhận thông tin.
4. Di chuyển quyền ghi trước, rồi chuyển các consumer đọc theo kế hoạch.
5. Gỡ quyền và code truy cập cũ khi không còn phụ thuộc.

Trong giai đoạn chuyển tiếp, có thể tồn tại bản sao đọc hoặc bảng tương thích. Hãy đánh dấu rõ đây là dữ liệu tạm, ai cập nhật và khi nào được loại bỏ.

### 7.3. Tránh dual-write

Dual-write xảy ra khi một request ghi cùng một thay đổi vào hai hệ thống độc lập, ví dụ ghi database rồi gửi message. Nếu database commit thành công nhưng gửi message thất bại, hai hệ thống lệch nhau. Nếu gửi message thành công nhưng transaction rollback, consumer nhận một sự kiện không có bản ghi tương ứng.

Transactional outbox là một cách xử lý phổ biến:

1. Service ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng database transaction.
2. Một publisher đọc các bản ghi outbox chưa gửi.
3. Publisher gửi event tới broker.
4. Sau khi xác nhận gửi, publisher đánh dấu bản ghi đã xử lý.
5. Consumer xử lý event theo cách idempotent.

Ví dụ cấu trúc bảng:

~~~sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    event_type     VARCHAR(120) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
~~~

Order Service có thể ghi Order và outbox event OrderPlaced trong cùng transaction. Publisher có thể chạy trong ứng dụng, worker riêng trên ECS hoặc Lambda được kích hoạt theo cơ chế polling/stream phù hợp. Cần thiết kế việc retry, khóa bản ghi và xử lý publisher chạy đồng thời.

### 7.4. Eventual consistency

Khi các service sở hữu dữ liệu riêng, cập nhật giữa các miền có thể không xảy ra cùng một transaction. Một event được phát ra rồi consumer cập nhật trạng thái sau đó. Trong khoảng thời gian ngắn, các màn hình hoặc service khác có thể nhìn thấy trạng thái cũ.

Thiết kế cần làm rõ:

- Trạng thái nào được coi là nguồn sự thật?
- Người dùng sẽ thấy trạng thái đang xử lý như thế nào?
- Bao lâu là độ trễ chấp nhận được?
- Consumer làm gì khi nhận event trùng hoặc sai thứ tự?
- Có quy trình đối soát khi event bị mất hoặc xử lý lỗi không?

Không phải mọi nghiệp vụ đều chấp nhận eventual consistency. Nếu cần kiểm tra một điều kiện ngay tại thời điểm giao dịch, hãy dùng API đồng bộ có timeout rõ ràng hoặc giữ phần nghiệp vụ đó trong cùng ranh giới cho đến khi có giải pháp phù hợp.

## 8. Chọn giao tiếp giữa các service

### 8.1. Giao tiếp đồng bộ qua API

HTTP/REST hoặc gRPC phù hợp khi caller cần kết quả ngay để tiếp tục xử lý. Trên AWS, điểm vào có thể là:

- Amazon API Gateway cho API công khai, quản lý xác thực, quota, throttling và tích hợp backend.
- Application Load Balancer cho định tuyến HTTP/HTTPS đến service chạy trên ECS, EKS hoặc EC2.
- Internal load balancer hoặc service discovery cho giao tiếp nội bộ trong mạng riêng.

Ưu điểm của API đồng bộ là luồng xử lý dễ hiểu và caller nhận kết quả ngay. Hạn chế là caller phụ thuộc khả năng sẵn sàng và độ trễ của callee. Chuỗi gọi nhiều service làm tăng tổng latency và mở rộng phạm vi lỗi.

Quy tắc thiết kế:

- Đặt timeout nhỏ hơn deadline tổng thể của request.
- Không retry vô hạn; dùng backoff có jitter và giới hạn số lần.
- Chỉ retry thao tác có thể thực hiện an toàn hoặc có idempotency key.
- Trả lỗi có cấu trúc, không lộ stack trace hoặc dữ liệu nhạy cảm.
- Giới hạn payload và bảo vệ khỏi request quá lớn.
- Truyền correlation ID hoặc trace context xuyên suốt chuỗi gọi.

### 8.2. Giao tiếp bất đồng bộ qua message và event

Giao tiếp bất đồng bộ phù hợp khi producer không cần chờ consumer hoàn tất ngay, hoặc khi muốn tách tải và thời điểm xử lý.

| Dịch vụ AWS | Mô hình | Khi nên dùng |
|---|---|---|
| Amazon SQS | Hàng đợi message, consumer nhận và xử lý | Công việc cần đệm tải, retry, kiểm soát tốc độ và tách producer/consumer |
| Amazon SNS | Pub/sub fan-out tới nhiều subscriber | Phát một thông báo tới nhiều đích như SQS, Lambda hoặc HTTPS |
| Amazon EventBridge | Event bus với rule lọc và định tuyến sự kiện | Kết nối các producer/consumer theo event nghiệp vụ hoặc sự kiện AWS |
| AWS Step Functions | Điều phối workflow có trạng thái | Quy trình nhiều bước, nhánh, retry, timeout và xử lý bù trừ |

Ví dụ, khi Order được tạo, Order Service phát event OrderPlaced. EventBridge có thể định tuyến event tới queue của Inventory, Shipping và Notification. Mỗi consumer xử lý độc lập và có thể mở rộng theo tốc độ queue.

SQS lưu message cho đến khi consumer xử lý và xóa. SNS fan-out thông báo tới nhiều subscriber. EventBridge định tuyến event theo rule và hỗ trợ tích hợp với nhiều dịch vụ AWS. Chọn dịch vụ theo mô hình giao tiếp, yêu cầu lọc, độ bền, thứ tự và khả năng replay, không chỉ theo tên gọi.

### 8.3. Chọn queue type và xử lý message lỗi

Amazon SQS Standard cung cấp khả năng mở rộng và thông lượng cao nhưng có thể giao message nhiều hơn một lần và không bảo đảm thứ tự tuyệt đối. Consumer cần idempotent.

SQS FIFO hỗ trợ thứ tự theo message group và deduplication trong phạm vi cơ chế dịch vụ. Nó hữu ích khi thứ tự nghiệp vụ quan trọng, nhưng cần thiết kế message group để tránh một nhóm duy nhất trở thành nút thắt.

Với cả hai loại queue:

- Đặt visibility timeout đủ dài cho thời gian xử lý dự kiến.
- Dùng dead-letter queue để cô lập message đã vượt số lần nhận.
- Theo dõi tuổi message cũ nhất và số message đang chờ.
- Có quy trình điều tra, sửa dữ liệu và phát lại message từ DLQ.
- Không xóa DLQ tự động khi chưa xác định nguyên nhân.

### 8.4. Thiết kế event contract

Event cần có schema ổn định, định danh duy nhất và thông tin đủ để consumer hiểu ý nghĩa nghiệp vụ:

~~~json
{
  "eventId": "evt-01JEXAMPLE",
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "occurredAt": "2026-11-20T05:00:00Z",
  "producer": "order-service",
  "correlationId": "req-7f31",
  "data": {
    "orderId": "ord-1042",
    "customerId": "cus-208",
    "currency": "VND",
    "totalAmount": 1250000
  }
}
~~~

Đây là payload minh họa. Hợp đồng thực tế cần quy định kiểu dữ liệu, trường bắt buộc, đơn vị tiền tệ, quy tắc versioning, dữ liệu nhạy cảm và chính sách tương thích ngược. Tránh đưa thông tin thanh toán hoặc thông tin cá nhân không cần thiết vào event.

Consumer nên bỏ qua hoặc xử lý tương thích với trường mới nếu schema được mở rộng theo hướng tương thích. Khi thay đổi phá vỡ hợp đồng, có thể phát hành version mới hoặc tạo event type mới theo chiến lược đã thống nhất.

## 9. Điều phối quy trình nghiệp vụ phân tán

### 9.1. Vì sao transaction phân tán khó?

Trong monolith, một transaction database có thể ghi Order, Payment và Inventory cùng lúc. Khi các phần này tách thành service với database riêng, không thể mặc định có một transaction ACID bao trùm mọi database và message broker.

Thay vì cố tạo một transaction phân tán dài, hệ thống thường dùng quy trình nhiều bước với trạng thái rõ ràng, retry và hành động bù trừ.

### 9.2. Saga pattern

Saga mô tả một giao dịch nghiệp vụ dài bằng chuỗi local transaction. Mỗi bước commit trong database của service sở hữu nó. Nếu một bước thất bại, workflow chạy hành động bù trừ để đưa hệ thống về trạng thái nghiệp vụ chấp nhận được.

Ví dụ quy trình đặt hàng:

1. Order Service tạo đơn ở trạng thái PENDING.
2. Inventory Service giữ hàng và phát InventoryReserved.
3. Payment Service yêu cầu thanh toán.
4. Nếu thanh toán thành công, Order chuyển sang CONFIRMED và phát event cho Shipping.
5. Nếu thanh toán thất bại, Order yêu cầu Inventory giải phóng reservation và chuyển sang CANCELLED.

Hành động bù trừ không phải lúc nào cũng đảo ngược hoàn toàn hành động trước đó. Một khoản thanh toán đã thu có thể cần hoàn tiền; một gói hàng đã gửi có thể cần quy trình trả hàng. Cần xác định trạng thái trung gian và cách xử lý khi bù trừ cũng thất bại.

### 9.3. Choreography và orchestration

**Choreography** dùng event để mỗi service tự phản ứng. Cách này giảm điều phối tập trung nhưng luồng nghiệp vụ có thể khó theo dõi khi có nhiều event và nhánh.

**Orchestration** dùng một bộ điều phối quản lý trạng thái workflow và yêu cầu từng service thực hiện bước tiếp theo. AWS Step Functions phù hợp với workflow có trạng thái, timeout, retry, branch và tích hợp với Lambda hoặc AWS service.

| Tiêu chí | Choreography | Orchestration |
|---|---|---|
| Điều phối | Các service phản ứng với event | Một workflow điều phối các bước |
| Độ kết hợp | Producer và consumer ít biết nhau | Workflow biết các bước và hợp đồng service |
| Theo dõi luồng | Cần ghép event và correlation ID | Có execution history tập trung |
| Phù hợp | Luồng event đơn giản, ít bước | Quy trình nhiều bước, nhánh và bù trừ |

Không nên dùng Step Functions cho mọi lời gọi giữa hai service. Dùng nó khi trạng thái và logic điều phối thực sự tạo giá trị.

## 10. Chọn nền tảng triển khai service trên AWS

### 10.1. Amazon ECS

Amazon ECS phù hợp với service đóng gói container, cần chạy liên tục hoặc theo task. ECS có thể chạy trên AWS Fargate để AWS quản lý hạ tầng máy chủ, hoặc trên EC2 khi cần kiểm soát sâu hơn về instance, capacity và cấu hình.

ECS thường là lựa chọn phù hợp khi tổ chức muốn chạy container mà không cần toàn bộ hệ sinh thái Kubernetes. Có thể dùng Application Load Balancer để định tuyến HTTP tới service, CloudWatch để thu thập log/metric và IAM task role để cấp quyền cho ứng dụng.

### 10.2. Amazon EKS

Amazon EKS phù hợp khi tổ chức đã chuẩn hóa Kubernetes, cần API và hệ sinh thái Kubernetes, hoặc có yêu cầu điều phối workload phức tạp. EKS cung cấp Kubernetes control plane được quản lý; nhóm vẫn chịu trách nhiệm về cấu hình cluster, node, network, add-on, bảo mật và nâng cấp theo mô hình sử dụng.

Không nên chọn EKS chỉ vì hệ thống có nhiều microservices. Kubernetes bổ sung nhiều khái niệm và công việc vận hành. Nếu ECS đáp ứng yêu cầu, ECS có thể giảm độ phức tạp.

### 10.3. AWS Lambda

AWS Lambda phù hợp với xử lý theo sự kiện, tác vụ ngắn hoặc workload có thời điểm chạy không liên tục. Ví dụ: xử lý event OrderPlaced, tạo thumbnail, gửi thông báo hoặc xử lý webhook.

Lambda có thể được kích hoạt từ SQS, EventBridge, API Gateway và nhiều nguồn khác. Khi dùng Lambda, cần chú ý giới hạn thời gian chạy, concurrency, cold start, kích thước payload, retry và xử lý message trùng.

### 10.4. Chọn theo workload

| Đặc tính | ECS/Fargate | EKS | Lambda |
|---|---|---|---|
| Chạy liên tục | Phù hợp | Phù hợp | Không phải mô hình mặc định |
| Event ngắn, bursty | Có thể dùng task/worker | Có thể dùng workload | Rất phù hợp |
| Kiểm soát runtime | Cao | Rất cao | Giới hạn theo runtime hỗ trợ |
| Gánh nặng nền tảng | Thấp đến vừa | Vừa đến cao | Thấp ở tầng máy chủ |
| Phù hợp khi | Cần container và vận hành đơn giản | Đã có năng lực Kubernetes | Xử lý theo event, thời gian chạy ngắn |

Một hệ thống có thể kết hợp các mô hình. Ví dụ Order API chạy trên ECS, consumer SQS chạy trên Lambda và workflow bù trừ được điều phối bởi Step Functions.

## 11. Dữ liệu, bảo mật và vận hành giữa các service

### 11.1. Chọn kho dữ liệu theo miền

Không bắt buộc mọi service dùng cùng loại database. Lựa chọn dựa trên access pattern và đặc tính dữ liệu:

- Amazon RDS hoặc Aurora khi cần relational model, SQL và transaction trong một miền.
- Amazon DynamoDB khi cần truy cập key-value/document với độ trễ thấp và mô hình truy cập rõ.
- Amazon ElastiCache khi cần cache dữ liệu truy cập thường xuyên.
- Amazon S3 cho object, tài liệu và dữ liệu phi cấu trúc.

Polyglot persistence có thể giúp mỗi miền dùng công nghệ phù hợp, nhưng làm tăng số nền tảng cần bảo mật, sao lưu, quan sát và kỹ năng vận hành. Hãy ưu tiên số lượng loại database nhỏ nhất đáp ứng yêu cầu.

### 11.2. Bảo mật danh tính service

Mỗi service cần danh tính và quyền riêng:

- Dùng IAM task role cho ECS task, IAM role cho workload EKS theo cơ chế phù hợp, và execution role/function role cho Lambda.
- Cấp quyền theo nguyên tắc đặc quyền tối thiểu, giới hạn tài nguyên và hành động.
- Dùng AWS Secrets Manager hoặc AWS Systems Manager Parameter Store để quản lý secret và cấu hình nhạy cảm.
- Dùng TLS cho giao tiếp qua mạng và mã hóa dữ liệu lưu trữ theo yêu cầu.
- Giới hạn service nội bộ trong private subnet khi phù hợp; chỉ công khai điểm vào cần thiết.
- Dùng security group để giới hạn nguồn và đích kết nối.

Không chia sẻ một access key tĩnh cho nhiều service. Credential nên được cấp tự động qua role và được luân chuyển theo cơ chế quản lý của dịch vụ.

### 11.3. API authentication và authorization

API Gateway có thể tích hợp Amazon Cognito, Lambda authorizer hoặc cơ chế xác thực phù hợp. Với giao tiếp service-to-service, cần xác thực danh tính gọi, kiểm tra quyền theo hành động và giới hạn truy cập mạng.

Xác thực cho biết caller là ai; authorization quyết định caller được làm gì. Một service có thể được phép gọi endpoint nhưng vẫn không được truy cập mọi order hoặc customer. Kiểm tra quyền ở cấp nghiệp vụ khi dữ liệu thuộc nhiều tenant hoặc người dùng.

### 11.4. Quan sát hệ thống phân tán

Khi một request đi qua nhiều service, một log riêng lẻ không đủ để giải thích toàn bộ lỗi. Nên chuẩn hóa:

- Log có cấu trúc với timestamp, service name, environment, request ID và correlation ID.
- Metric về request rate, error rate, latency percentile, queue depth và saturation.
- Distributed tracing để theo dõi request qua API và service.
- Alarm theo SLO và mức độ ảnh hưởng người dùng.
- Dashboard thể hiện dependency và trạng thái từng thành phần.

Amazon CloudWatch cung cấp log, metric, dashboard và alarm. AWS X-Ray hỗ trợ tracing cho các thành phần tích hợp; OpenTelemetry cũng có thể dùng để thu thập trace và metric theo chuẩn mở. Với event bất đồng bộ, cần truyền correlation ID trong message để nối producer với consumer.

### 11.5. Độ tin cậy và khả năng chịu lỗi

Mỗi service nên giả định dependency có thể chậm hoặc không khả dụng:

- Dùng timeout cho mọi lời gọi mạng.
- Retry có giới hạn với exponential backoff và jitter.
- Dùng circuit breaker hoặc cơ chế giới hạn tải để tránh dồn lỗi sang dependency.
- Thiết kế idempotency cho command có thể được gửi lại.
- Dùng queue để hấp thụ burst và tách producer khỏi consumer.
- Đưa message lỗi vào DLQ và có quy trình redrive.
- Giới hạn concurrency để bảo vệ database và dịch vụ phụ thuộc.

Đừng retry một thao tác không idempotent chỉ vì nhận timeout. Timeout có thể xảy ra sau khi server đã commit thay đổi nhưng response chưa về tới caller. Hãy dùng idempotency key hoặc kiểm tra trạng thái trước khi thử lại.

## 12. Các bước thực hiện một chương trình phân rã

### Giai đoạn 1: Hiểu hiện trạng

1. Vẽ sơ đồ module, database, API và luồng dữ liệu.
2. Thu thập số liệu deploy, latency, lỗi, tải và xung đột code.
3. Xác định điểm phụ thuộc trực tiếp giữa các module.
4. Phỏng vấn nhóm nghiệp vụ để hiểu capability và quy tắc thay đổi.
5. Chọn một vấn đề cụ thể mà chương trình phân rã cần giải quyết.

### Giai đoạn 2: Thiết kế ranh giới

1. Lập domain map và bounded context.
2. Xác định dữ liệu cốt lõi và service sở hữu dữ liệu đó.
3. Định nghĩa API/event contract.
4. Xác định giao dịch cần đồng bộ và phần có thể eventual consistency.
5. Chọn runtime và database phù hợp cho workload.
6. Đánh giá bảo mật, quan sát, chi phí và khả năng trực vận hành.

### Giai đoạn 3: Tách một capability

1. Tạo service mới và pipeline build/deploy độc lập.
2. Thiết lập IAM role, network, secret, log, metric và alarm.
3. Tạo API hoặc event contract và kiểm thử tương thích.
4. Di chuyển dữ liệu theo kế hoạch, xác định nguồn ghi duy nhất.
5. Định tuyến một phần request hoặc event sang service mới.
6. Đo hiệu quả, kiểm tra lỗi và giữ khả năng rollback.

### Giai đoạn 4: Mở rộng và loại bỏ code cũ

1. Tăng lưu lượng theo từng đợt khi chỉ số ổn định.
2. Chuyển quyền sở hữu dữ liệu và cập nhật consumer.
3. Xử lý dữ liệu trùng, thiếu hoặc không nhất quán.
4. Loại bỏ đường ghi/đọc cũ sau khi xác nhận không còn consumer.
5. Cập nhật runbook, sơ đồ kiến trúc và trách nhiệm vận hành.
6. Đánh giá lại ranh giới trước khi tách capability tiếp theo.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tách service theo bảng hoặc lớp kỹ thuật | Nhiều service vẫn phải phối hợp cho một nghiệp vụ | Bắt đầu từ capability và bounded context |
| Chia quá nhỏ | Tăng số lần gọi mạng, pipeline và gánh nặng trực vận hành | Gộp các phần thay đổi cùng nhau và có cùng chủ sở hữu |
| Nhiều service cùng ghi một database | Schema trở thành hợp đồng ngầm và dễ phát sinh lỗi dây chuyền | Xác định owner dữ liệu và dùng API/event |
| Gọi đồng bộ qua quá nhiều service | Latency và phạm vi lỗi tăng theo chuỗi | Dùng event/queue cho công việc không cần phản hồi ngay |
| Dùng retry vô hạn | Tạo retry storm và làm dependency quá tải | Timeout, backoff, jitter, giới hạn retry và DLQ |
| Dual-write database và message | Dữ liệu và event có thể lệch nhau | Transactional outbox và consumer idempotent |
| Giả định event chỉ đến một lần | Xử lý trùng gây tạo đơn hoặc thu tiền lặp | Idempotency key và lưu dấu event đã xử lý |
| Không có trace xuyên service | Khó tìm nguồn lỗi trong luồng phân tán | Correlation ID, distributed tracing và log có cấu trúc |
| Chuyển dữ liệu nhưng không xác minh | Monolith và service mới có thể trả kết quả khác nhau | Đối soát, shadow read và chuyển quyền ghi có kiểm soát |
| Tách service mà không có owner | Không ai chịu trách nhiệm SLO và sự cố | Gắn service với nhóm sở hữu và runbook |

## 14. Checklist đánh giá service boundary

Trước khi quyết định tách một module thành service, hãy trả lời:

1. Capability nghiệp vụ của service là gì?
2. Bounded context và ngôn ngữ nghiệp vụ có rõ không?
3. Service sở hữu dữ liệu nào và có quyền ghi duy nhất không?
4. Các service khác tương tác qua hợp đồng nào?
5. Giao tiếp nào cần đồng bộ, giao tiếp nào có thể bất đồng bộ?
6. Quy trình xử lý lỗi, retry, idempotency và đối soát đã rõ chưa?
7. Service có thể build, deploy, scale và rollback độc lập không?
8. Có IAM role, secret, network policy và mã hóa phù hợp không?
9. Có log, metric, trace, alarm, dashboard và runbook không?
10. Lợi ích kinh doanh có lớn hơn chi phí phân tán và vận hành không?

Nếu nhiều câu hỏi chưa có câu trả lời, hãy tiếp tục làm rõ module boundary trong monolith trước khi tách tiến trình.

## 15. Kết luận

Phân rã monolith là quá trình tìm và thiết lập ranh giới nghiệp vụ có thể được sở hữu, thay đổi và vận hành độc lập. Business capability và bounded context giúp xác định nơi đặt ranh giới; quyền sở hữu dữ liệu giúp ngăn phụ thuộc ngầm; API và event contract tạo cách giao tiếp có kiểm soát.

Trên AWS, có thể triển khai service bằng ECS, EKS hoặc Lambda, định tuyến qua API Gateway hoặc load balancer, tích hợp bất đồng bộ bằng SQS, SNS và EventBridge, điều phối quy trình bằng Step Functions, đồng thời dùng CloudWatch và tracing để quan sát toàn hệ thống. Lựa chọn dịch vụ cần dựa trên workload, kỹ năng đội ngũ và chi phí vận hành.

Di chuyển theo Strangler Fig giúp thay đổi từng phần và kiểm soát rủi ro. Mỗi bước cần có kế hoạch dữ liệu, routing, rollback và tiêu chí kiểm chứng. Khi kết hợp ranh giới nghiệp vụ rõ, quyền sở hữu dữ liệu, xử lý lỗi phân tán và vận hành có trách nhiệm, tổ chức có thể phát triển hệ thống theo nhu cầu mà không biến việc tách monolith thành một mạng lưới phụ thuộc khó kiểm soát.
