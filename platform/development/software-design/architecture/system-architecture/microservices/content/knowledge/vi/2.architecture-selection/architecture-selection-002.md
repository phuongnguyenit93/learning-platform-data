# Động lực lựa chọn Microservices: tốc độ thay đổi, quy mô nhóm và khả năng mở rộng

## 1. Bối cảnh và câu hỏi kiến trúc

Microservices là cách tổ chức hệ thống thành nhiều dịch vụ có ranh giới trách nhiệm rõ ràng, giao tiếp qua hợp đồng và có thể phát triển, triển khai, vận hành tương đối độc lập. Giá trị chính của cách tổ chức này thường xuất hiện khi **chi phí phối hợp để thay đổi một hệ thống lớn** trở thành nút thắt.

Ba động lực thường được cân nhắc cùng nhau:

1. **Tốc độ thay đổi:** nhiều luồng tính năng cần được sửa, thử nghiệm và phát hành thường xuyên mà ít ảnh hưởng lẫn nhau.
2. **Quy mô nhóm:** nhiều nhóm kỹ thuật cần quyền sở hữu rõ ràng để ra quyết định, phát hành và chịu trách nhiệm mà không phải chờ một hàng đợi triển khai chung.
3. **Khả năng mở rộng:** các phần của hệ thống có đặc tính tải, tài nguyên và nhịp tăng trưởng khác nhau nên cần mở rộng và tối ưu riêng.

Đây là những **động lực kinh doanh và tổ chức**, không phải chứng cứ tự động rằng microservices là lựa chọn tốt nhất. Một monolith được thiết kế theo mô-đun vẫn có thể đáp ứng ba nhu cầu này trong nhiều giai đoạn.

## 2. Động lực thứ nhất: tăng tốc độ thay đổi

### 2.1. Vấn đề thường gặp khi hệ thống lớn dần

Trong một hệ thống có mức liên kết cao, thay đổi nhỏ ở một chức năng có thể đòi hỏi kiểm thử toàn bộ ứng dụng, phối hợp lịch phát hành của nhiều nhóm và triển khai chung. Khi hệ thống cùng lúc có nhiều nhánh công việc, các xung đột mã nguồn, thay đổi lược đồ dữ liệu và phụ thuộc giữa mô-đun làm thời gian đưa giá trị tới người dùng tăng lên.

Có thể quan sát nút thắt qua:

- Thời gian từ lúc bắt đầu thực hiện một yêu cầu đến khi yêu cầu được chạy trên production kéo dài, dù thời gian viết mã không tăng nhiều.
- Một thay đổi độc lập vẫn phải chờ lịch phát hành hoặc phê duyệt của nhiều nhóm khác.
- Phạm vi hồi quy rộng, quy trình kiểm thử và triển khai bị ùn tắc.
- Một lỗi tại một chức năng thường buộc rollback cả bản phát hành của hệ thống.
- Các thử nghiệm sản phẩm có nhịp khác nhau nhưng bị ép theo một chu kỳ phát hành chung.

### 2.2. Cách microservices có thể giúp

Khi tách **đúng ranh giới năng lực nghiệp vụ** (business capability) và giảm phụ thuộc vận hành, một nhóm có thể chỉnh sửa, kiểm thử, phát hành và rollback dịch vụ mình sở hữu mà không cần đồng bộ với toàn bộ hệ thống. Mỗi dịch vụ có pipeline và chu kỳ thay đổi phù hợp với rủi ro của nó; ví dụ dịch vụ gợi ý sản phẩm có thể thay đổi thường xuyên hơn dịch vụ thanh toán.

Giá trị này chỉ đạt được khi đáp ứng các điều kiện:

- **Ranh giới ổn định:** thay đổi nghiệp vụ thường nằm gọn trong một dịch vụ hoặc một số ít dịch vụ.
- **Hợp đồng tương thích:** API, schema sự kiện và hành vi cũ được duy trì đủ lâu để các bên nâng cấp độc lập.
- **Triển khai độc lập thực sự:** không có yêu cầu ngầm rằng nhiều dịch vụ luôn phải phát hành cùng một thời điểm.
- **Kiểm thử phù hợp:** kiểm thử đơn vị, tích hợp và contract giúp phát hiện sai khác giữa các bên mà không buộc chạy một bộ end-to-end quá lớn cho mọi lần sửa.
- **Tự động hóa vận hành:** build, triển khai, quan sát, rollback và kiểm soát cấu hình đủ ổn định để tần suất phát hành cao không tạo thêm sự cố.

Nếu mỗi yêu cầu phải sửa đồng thời năm dịch vụ, chỉnh sửa nhiều kho mã và đợi một đợt tích hợp chung, việc chia hệ thống thành dịch vụ nhỏ có thể **làm giảm** tốc độ thay đổi. Khi đó cần xem lại ranh giới hoặc cân nhắc modular monolith.

### 2.3. Đo kết quả thay vì đếm số dịch vụ

Các chỉ số hữu ích gồm:

| Chỉ số | Cách diễn giải |
| --- | --- |
| Lead time for changes | Thời gian từ thay đổi mã đến khi chạy trên production; giảm cho thấy luồng phát hành nhanh hơn. |
| Deployment frequency | Tần suất triển khai thành công; nên xem cùng độ ổn định, tránh tối ưu số lần deploy một cách hình thức. |
| Change failure rate | Tỷ lệ thay đổi gây lỗi cần khắc phục; tốc độ không có ý nghĩa nếu rủi ro tăng mạnh. |
| Failed deployment recovery time | Thời gian phục hồi sau một lần triển khai lỗi; thể hiện khả năng cô lập và xử lý sự cố. |
| Tỷ lệ thay đổi liên dịch vụ | Bao nhiêu yêu cầu cần sửa nhiều dịch vụ hoặc triển khai phối hợp; tỷ lệ cao cảnh báo ranh giới sai. |
| Thời gian chờ liên nhóm | Phần lead time dành cho chờ review, phụ thuộc, môi trường và lịch phát hành; dùng để xác định nút thắt tổ chức. |

Đo trước và sau một thay đổi kiến trúc theo cùng loại công việc, trên thời gian đủ dài. Phân biệt tác động của kiến trúc với việc đồng thời bổ sung CI/CD, tăng nhân sự hoặc thay đổi quy trình.

## 3. Động lực thứ hai: hệ thống và tổ chức có nhiều nhóm

### 3.1. Vấn đề phối hợp

Khi số kỹ sư tăng, chi phí phối hợp không tăng tuyến tính nếu tất cả cùng làm trên một miền mã nguồn liên kết chặt. Những tình huống thường gặp:

- Nhiều nhóm cùng chỉnh sửa các lớp nghiệp vụ chung, phải thương lượng ưu tiên và trình tự merge.
- Không rõ ai chịu trách nhiệm về một chức năng, chất lượng dữ liệu hay sự cố sản xuất.
- Đội A muốn thử một giải pháp nhưng phải xin chấp thuận từ đội B cho các chi tiết không liên quan.
- Việc vận hành, trực sự cố và theo dõi chỉ số không khớp với người quyết định thay đổi.
- Mỗi lần thêm người vào dự án khiến yêu cầu họp, review chéo và chuyển giao tăng nhanh.

Microservices có thể giúp thiết lập quyền sở hữu từ đầu đến cuối cho các **nhóm phụ trách một năng lực nghiệp vụ**, chẳng hạn Catalog, Order, Payment hoặc Fulfillment. Một nhóm chịu trách nhiệm mã nguồn, dữ liệu thuộc phạm vi sở hữu, hợp đồng giao tiếp, kiểm thử, triển khai và mức độ tin cậy của dịch vụ.

### 3.2. Ranh giới nhóm và ranh giới dịch vụ

Nên xác định ranh giới từ domain và mức độ thay đổi cùng nhau, không chia chỉ theo tầng kỹ thuật (frontend, business logic, database) hoặc theo số lượng nhân viên. Các nguyên tắc:

1. **Cohesion cao trong ranh giới:** quy tắc nghiệp vụ và dữ liệu thường thay đổi cùng nhau nên ở gần nhau.
2. **Coupling thấp qua ranh giới:** nhóm khác phụ thuộc vào hợp đồng rõ ràng, không gọi trực tiếp vào cấu trúc nội bộ hoặc bảng cơ sở dữ liệu của dịch vụ.
3. **Ownership rõ:** có nhóm chịu trách nhiệm về hành vi, độ tin cậy, cảnh báo và vòng đời API.
4. **Quy mô hiểu được:** phạm vi dịch vụ hoặc tập dịch vụ đủ nhỏ để một nhóm nắm vững, nhưng không nhỏ tới mức phải phối hợp liên tục cho một thao tác.
5. **Nền tảng dùng chung hợp lý:** cung cấp các khả năng như CI/CD, logging, tracing, secrets, discovery và chính sách bảo mật để từng nhóm không phải xây lại hạ tầng.

Luật Conway gợi ý rằng cấu trúc giao tiếp của tổ chức có xu hướng thể hiện trong cấu trúc hệ thống. Có thể chủ động tổ chức nhóm quanh các luồng giá trị để giảm các giao tiếp bắt buộc. Tuy nhiên, **không mặc định mỗi nhóm đúng một dịch vụ**: một nhóm có thể sở hữu vài dịch vụ liên quan, và một dịch vụ nhỏ có thể chưa cần tách khỏi mô-đun của ứng dụng chính.

### 3.3. Ngưỡng tổ chức không phải một con số cố định

Không tồn tại mốc "từ N lập trình viên thì phải dùng microservices". Cần xem mức độ độc lập của roadmap, số nhóm thay đổi đồng thời, tần suất xung đột trách nhiệm và năng lực tự vận hành.

Một nhóm nhỏ đang khám phá sản phẩm thường hưởng lợi từ monolith/modular monolith vì quyết định nhanh, kiểm thử và debug đơn giản. Nhiều nhóm với các miền nghiệp vụ ổn định, lịch phát hành khác nhau và đầu tư platform đủ mạnh có thể hưởng lợi từ microservices. Nếu vẫn tồn tại một nhóm hạ tầng hoặc kiến trúc phải duyệt mọi lần triển khai, microservices chưa chắc tăng quyền tự chủ thực tế.

## 4. Động lực thứ ba: mở rộng theo nhu cầu tải và tài nguyên

### 4.1. Phân biệt các loại mở rộng

- **Mở rộng lưu lượng (throughput):** đáp ứng nhiều yêu cầu hoặc tác vụ hơn.
- **Mở rộng dữ liệu:** xử lý tập dữ liệu lớn hơn, tăng dung lượng lưu trữ và giao dịch.
- **Mở rộng năng lực tính toán:** phân bổ CPU, bộ nhớ, GPU hoặc tác vụ nền riêng theo workload.
- **Mở rộng vận hành và phát triển:** giữ được tốc độ đổi mới khi có nhiều người, nhiều tính năng và nhiều dịch vụ.
- **Mở rộng độ tin cậy:** hạn chế phạm vi ảnh hưởng khi một thành phần lỗi, quá tải hoặc cần bảo trì.

Microservices hỗ trợ **scale độc lập** theo dịch vụ. Ví dụ Search đọc nhiều và cần tối ưu truy vấn; Image Processing tiêu tốn CPU; Order Processing có yêu cầu nhất quán dữ liệu cao. Khi tách hợp lý, hệ thống có thể cấp tài nguyên và chính sách autoscaling khác nhau cho từng workload.

Tuy nhiên, tách dịch vụ không tự giải quyết nút thắt. Nếu mọi dịch vụ dùng chung một cơ sở dữ liệu đang nghẽn, hoặc một luồng yêu cầu phải gọi nối tiếp nhiều dịch vụ, tăng số replica có thể không cải thiện đáng kể độ trễ. Một monolith stateless vẫn có thể scale ngang bằng load balancer, cache, queue, tối ưu truy vấn và phân vùng dữ liệu với chi phí thấp hơn.

### 4.2. Ví dụ tải không đồng đều

Giả sử một ứng dụng thương mại điện tử có ba luồng:

| Thành phần | Đặc tính tải | Hướng xử lý phù hợp |
| --- | --- | --- |
| Tìm kiếm sản phẩm | Lượt đọc cao, tăng đột biến khi chạy chiến dịch | Cache/index tìm kiếm, scale read replicas hoặc service Search riêng nếu cần. |
| Đặt hàng | Giao dịch ít hơn tìm kiếm nhưng yêu cầu tính đúng đắn cao | Giữ transaction và invariant quan trọng trong một ranh giới sở hữu. |
| Xử lý ảnh | Nặng CPU, chấp nhận xử lý bất đồng bộ | Queue và worker autoscaling riêng theo độ dài hàng đợi. |

Nếu ba luồng nằm trong một tiến trình, scale toàn bộ tiến trình có thể làm phát sinh tài nguyên dư thừa. Tách Image Processing thành worker độc lập có thể mang lại lợi ích rõ ngay cả khi phần nghiệp vụ còn lại vẫn là modular monolith. Không cần đồng thời tách mọi chức năng thành service.

### 4.3. Điều kiện để scale độc lập có ý nghĩa

- Dịch vụ phải có bottleneck riêng được xác nhận bằng số liệu: CPU, memory, I/O, thời gian xử lý, queue depth hoặc p95/p99 latency.
- Lưu lượng có mức chênh lệch đáng kể giữa các miền và khả năng cấp tài nguyên riêng tạo lợi ích chi phí/hiệu năng.
- Các dịch vụ ưu tiên stateless khi có thể, hoặc biết cách xử lý session, idempotency và dữ liệu khi scale ngang.
- Hạn chế chuỗi lời gọi đồng bộ dài; cân nhắc queue/event cho công việc phù hợp và chấp nhận nhất quán cuối cùng ở nơi nghiệp vụ cho phép.
- Có timeout, retry có giới hạn, backoff, circuit breaker, bulkhead và bảo vệ chống lan truyền quá tải.
- Nhận thức rằng giới hạn của hệ thống có thể nằm ở database, mạng, external API hoặc khóa dùng chung, chứ không nằm ở số instance ứng dụng.

## 5. Ba động lực tương tác thế nào?

| Tình huống | Vấn đề thật | Microservices có thể giúp nếu… |
| --- | --- | --- |
| Mỗi tháng ra nhiều tính năng độc lập | Chờ release chung, phạm vi kiểm thử quá rộng | Ranh giới dịch vụ khớp các luồng thay đổi, hợp đồng cho phép deploy độc lập. |
| Từ một nhóm tăng thành nhiều nhóm | Xung đột ownership và roadmap | Có các miền nghiệp vụ rõ, nhóm chịu trách nhiệm end-to-end và platform chung. |
| Một chức năng bất ngờ tăng tải | Scale toàn ứng dụng tốn kém | Thành phần đó có bottleneck riêng, tách được dữ liệu và điểm phụ thuộc chính. |
| Mọi yêu cầu luôn sửa nhiều nghiệp vụ cùng lúc | Ranh giới liên kết quá chặt | Trước tiên làm rõ domain và giảm coupling; tách sớm có thể làm tệ hơn. |
| Đội còn nhỏ, sản phẩm thay đổi liên tục | Chưa rõ ranh giới nghiệp vụ lâu dài | Thường ưu tiên modular monolith, quan sát hướng thay đổi rồi mới trích xuất. |

**Độc lập thay đổi, độc lập sở hữu và độc lập scale** là ba mục tiêu liên quan nhưng khác nhau. Có khi chỉ cần tách một workload xử lý nền, không cần biến toàn bộ ứng dụng thành microservices. Cũng có khi nhu cầu chính là phối hợp nhiều nhóm; một monolith mô-đun với ownership rõ và build/test tốt đã giải quyết phần lớn vấn đề.

## 6. Chi phí và đánh đổi cần tính vào quyết định

Microservices chuyển một phần độ phức tạp từ các lời gọi nội bộ sang một hệ thống phân tán:

- **Mạng và tính sẵn sàng:** lời gọi có latency, lỗi mạng, timeout, partial failure; các bước nghiệp vụ có thể hoàn tất một phần.
- **Dữ liệu:** mỗi dịch vụ sở hữu dữ liệu của mình làm giao dịch xuyên dịch vụ khó hơn; cần thiết kế saga, outbox, idempotency, event ordering hoặc reconciliation khi thật sự cần.
- **Quan sát:** cần correlation ID, distributed tracing, metrics, logs tập trung, SLO và quy trình điều tra xuyên dịch vụ.
- **Triển khai:** số pipeline, cấu hình, secret, phiên bản API, môi trường và đối tượng cảnh báo tăng.
- **Bảo mật:** nhiều điểm giao tiếp và quyền truy cập; yêu cầu xác thực/ủy quyền service-to-service và quản lý bí mật.
- **Chi phí nhân sự:** nhiều repository, thư viện, công cụ và kỹ năng vận hành hơn; có nguy cơ mỗi nhóm xây hạ tầng trùng lặp.
- **Kiểm thử:** contract và integration tests trở nên quan trọng; end-to-end có thể chậm, khó ổn định nếu thiết kế thiếu kiểm soát.

Một mô hình có 20 dịch vụ nhưng phải deploy đồng thời, dùng chung database và không có tracing thường mang thêm chi phí phân tán mà không thu được những lợi ích ban đầu. Vì vậy, yêu cầu quan trọng là chứng minh **lợi ích ròng** so với phương án đơn giản hơn.

## 7. Quy trình đánh giá trước khi quyết định

### Bước 1: Gọi tên nút thắt và mục tiêu

Viết một tuyên bố có thể kiểm chứng, ví dụ: “Nhóm Search cần phát hành thử nghiệm hàng ngày, nhưng phải chờ đợt release Order hàng tuần” hoặc “Job xử lý ảnh dùng 70% CPU khi có chiến dịch và làm tăng độ trễ API chính”.

Tránh mục tiêu trừu tượng như “hệ thống cần hiện đại hơn” hoặc “phải có thật nhiều service”.

### Bước 2: Đặt số liệu nền

Đo lead time, tần suất triển khai, tỷ lệ sự cố do thay đổi, thời gian khôi phục, thời gian chờ liên nhóm, sơ đồ phụ thuộc, CPU/memory, p95/p99 latency, throughput, tỷ lệ lỗi và chi phí hạ tầng.

### Bước 3: Tìm ranh giới theo domain

Dùng event storming, phân tích use case, bounded context, các nhóm quy tắc và dữ liệu thay đổi cùng nhau. Xác định invariant nào phải giữ trong một transaction. Tránh tách các thao tác có coupling cao thành hàng loạt lời gọi mạng.

### Bước 4: So sánh các phương án theo mức đầu tư

1. **Tối ưu monolith hiện có:** tăng test automation, build cache, feature flags, tách modules, cải thiện truy vấn hoặc cache.
2. **Modular monolith:** đặt ranh giới code và quyền sở hữu rõ, API nội bộ, giới hạn phụ thuộc, có thể phân nhóm phát triển mà chưa phát sinh giao tiếp phân tán.
3. **Tách từng thành phần có lợi ích rõ:** job nền, Search hoặc một bounded context có chu kỳ phát hành và tải khác biệt.
4. **Microservices rộng hơn:** khi nhiều ranh giới đã ổn định, đội ngũ đủ trưởng thành và lợi ích triển khai/scale độc lập lặp lại trên nhiều lĩnh vực.

### Bước 5: Thực hiện thử nghiệm có giới hạn

Chọn một miền có ranh giới rõ, tần suất thay đổi hoặc nhu cầu tải đáng kể, phụ thuộc dễ kiểm soát. Tạo contract và observability trước, di chuyển từng luồng dữ liệu, triển khai song song hoặc dùng strangler pattern khi phù hợp. Thiết lập phương án rollback; không chuyển cùng lúc tất cả phần mềm và dữ liệu.

### Bước 6: Quyết định bằng bằng chứng

Sau một vài chu kỳ phát hành, so sánh số liệu mục tiêu với chi phí mới: có giảm lead time, tăng tính độc lập, hạ chi phí scale hay không? Có tăng lỗi tích hợp, thời gian điều tra, độ trễ hoặc gánh nặng vận hành không? Nếu lợi ích không xuất hiện, điều chỉnh ranh giới hoặc dừng mở rộng việc tách dịch vụ.

## 8. Hai tình huống minh họa

### Tình huống A: startup 7 kỹ sư, sản phẩm còn thay đổi nhanh

Sản phẩm đang tìm product-market fit. Một nhóm cùng làm Catalog, Order và Payment; các tính năng thường thay đổi xuyên ba miền. Lưu lượng chưa cao, database không nghẽn.

**Hướng chọn:** modular monolith với module ownership, interface và kiểm thử rõ ràng. Đầu tư CI/CD, feature flags, tối ưu build và đo dependency trước. Microservices lúc này có thể kéo dài thời gian phát triển vì phải lo network, giao dịch phân tán và vận hành.

**Điểm tái đánh giá:** nhóm tách thành các đội độc lập có roadmap riêng; module Search hoặc Image Processing xuất hiện tải riêng rõ rệt; xung đột release thường xuyên dù đã cải thiện quy trình.

### Tình huống B: nền tảng thương mại có nhiều đội độc lập

Các nhóm Search, Catalog, Checkout, Payment và Fulfillment có roadmap khác nhau. Search cần thử nghiệm hàng ngày; Checkout chú trọng tính ổn định; xử lý ảnh tăng tải theo chiến dịch. Monolith hiện tại yêu cầu kiểm thử và deploy toàn bộ mỗi lần đổi.

**Hướng chọn:** ưu tiên ranh giới Search và xử lý ảnh nếu phù hợp, sau đó xét từng bounded context khác. Giữ các invariant đặt hàng/thanh toán trong ranh giới nhất quán phù hợp; xác định hợp đồng API, event, ownership, SLO và cách điều tra lỗi trước khi trích xuất.

**Dấu hiệu thành công:** Search triển khai thường xuyên hơn mà không đòi hỏi Checkout cùng phát hành; xử lý ảnh scale theo queue depth mà không tăng tài nguyên của Order; tỷ lệ lỗi người dùng và chi phí vận hành vẫn trong giới hạn chấp nhận.

## 9. Những ngộ nhận dễ dẫn tới quyết định sai

**“Có nhiều người thì phải tách nhiều service.”** Quy mô nhóm chỉ là tín hiệu. Chi phí phối hợp còn phụ thuộc ranh giới nghiệp vụ, code ownership và cơ chế phát hành. Nếu mọi nhóm sửa cùng một giao dịch xuyên dịch vụ, chia nhỏ có thể tăng xung đột.

**“Microservices luôn scale tốt hơn monolith.”** Monolith stateless có thể scale ngang rất hiệu quả. Phải đo xem workload nào cần cấp tài nguyên riêng và bottleneck thực sự ở đâu.

**“Đã tách repository là deploy độc lập.”** Độc lập triển khai còn phụ thuộc API tương thích, dữ liệu, môi trường, kiểm thử và khả năng chấp nhận phiên bản dịch vụ khác nhau.

**“Một service nên càng nhỏ càng tốt.”** Tách quá mịn làm phát sinh chatty calls, latency, transaction xuyên dịch vụ và chi phí ownership. Kích thước đúng phụ thuộc mức gắn kết của nghiệp vụ.

**“Dùng microservices tự động tăng tốc.”** Nếu thiếu CI/CD, observability và khả năng vận hành, tổng thời gian làm việc có thể tăng; đầu tư vào công cụ và thiết kế domain thường phải đi trước.

## 10. Checklist ra quyết định

Trước khi chọn hoặc mở rộng microservices, hãy tự trả lời:

- [ ] Có nút thắt cụ thể về tốc độ thay đổi, phối hợp nhóm hoặc scale đã đo được.
- [ ] Có bằng chứng rằng cải thiện monolith/modular monolith chưa đủ hoặc không kinh tế.
- [ ] Bounded context được xác định bằng nghiệp vụ, với dữ liệu và invariant sở hữu rõ.
- [ ] Thay đổi thường ngày có thể giới hạn vào một dịch vụ hoặc số ít dịch vụ.
- [ ] Các đội có khả năng phát triển, triển khai và vận hành phần mình sở hữu.
- [ ] API/event có quy tắc phiên bản và tương thích; không yêu cầu deploy đồng loạt thường xuyên.
- [ ] CI/CD, contract testing, logging, tracing, metrics, alerting và rollback đủ dùng.
- [ ] Các vấn đề mạng, partial failure, consistency và bảo mật có thiết kế xử lý.
- [ ] Chi phí vận hành, platform và năng lực on-call đã được đưa vào bài toán.
- [ ] Có chỉ số đo lợi ích sau khi tách và tiêu chí dừng nếu không đạt.

## 11. Kết luận

Microservices có cơ sở khi hệ thống thực sự cần **thay đổi độc lập, nhóm sở hữu độc lập và cấp tài nguyên độc lập**, đồng thời doanh nghiệp có đủ năng lực gánh chi phí vận hành phân tán. Động lực mạnh nhất không nằm ở số lượng dịch vụ, mà ở việc một ranh giới nghiệp vụ rõ giúp giảm chờ đợi, cô lập thay đổi và phân bổ nguồn lực đúng nơi có nhu cầu.

Khi ranh giới chưa rõ, quy mô nhóm nhỏ hoặc tải còn đồng đều, bắt đầu bằng modular monolith và tách dần dựa trên số liệu thường là một quyết định có tính kinh tế hơn.