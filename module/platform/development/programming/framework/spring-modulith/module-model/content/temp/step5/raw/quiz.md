Câu 1. Với Spring Boot đặt ở package com.acme, cấu trúc nào thường tạo hai application module mặc định?
A. Hai class @Service trong cùng package com.acme.orders
B. Hai method @Bean trong cấu hình com.acme.Application
C. Hai subpackage com.acme.orders và com.acme.billing ở base
D. Hai repository trong package com.acme.orders.data
Đáp án đúng: C

Câu 2. Nếu có com.acme.orders.internal nằm dưới module orders mặc định, package đó được hiểu thế nào?
A. Là một module mới vì tên package có thêm một cấp
B. Là root package công khai của module billing lân cận
C. Là package ngoài ứng dụng do không ở base package
D. Thuộc nội bộ orders, không tự tạo module mới
Đáp án đúng: D

Câu 3. Spring Modulith mặc định suy ra module từ yếu tố nào trong ứng dụng Spring Boot?
A. Cấu trúc package dưới application base package
B. Tên các table được khai báo trong database schema
C. Số lượng @Transactional method của từng service
D. Danh sách endpoint HTTP đăng ký vào DispatcherServlet
Đáp án đúng: A

Câu 4. Giả sử com.acme.orders.OrderFacade là public class ở package gốc của module orders, nó thuộc nhóm nào?
A. Thành phần nội bộ vì mọi class @Service đều là internal
B. Named Interface spi dù chưa có khai báo Named Interface
C. Thành phần API của orders được phép tham chiếu từ module khác
D. Module độc lập với orders vì class có modifier public
Đáp án đúng: C

Câu 5. Với class public com.acme.orders.internal.OrderValidator, mô tả nào đúng về ranh giới Modulith mặc định?
A. Class public ở mọi subpackage đều thuộc API module orders
B. Modulith tự đổi quyền truy cập Java thành package-private
C. Validator tạo một module riêng nếu có annotation @Component
D. Java cho phép import, nhưng Modulith coi đây là nội bộ orders
Đáp án đúng: D

Câu 6. Một module thanh toán import trực tiếp orders.internal.PriceCalculator. Rủi ro kiến trúc nào xuất hiện?
A. Phụ thuộc hợp lệ vì PriceCalculator có modifier public
B. Phụ thuộc vào implementation nội bộ của module orders
C. Tạo Named Interface tự động cho package orders.internal
D. Chỉ gây lỗi khi ứng dụng triển khai thành microservice
Đáp án đúng: B

Câu 7. Muốn module khác gọi dịch vụ orders mà không lộ implementation, thiết kế nào hợp lý?
A. Đặt giao diện API cùng implementation ở orders.internal
B. Giao diện ở orders root, triển khai trong internal
C. Đặt toàn bộ lớp service vào package gốc com.acme
D. Dùng reflection để gọi class internal mà không import
Đáp án đúng: B

Câu 8. Khi package com.acme.orders.api là một subpackage, muốn nó thành API có tên của orders, dùng gì?
A. Khai @NamedInterface cho package com.acme.orders.api
B. Đặt @ApplicationModule trên từng @Service trong api
C. Đặt @Transactional trên toàn bộ class trong api
D. Dùng @Primary để bean trong api được xem là public API
Đáp án đúng: A

Câu 9. Nơi nào phù hợp để khai @NamedInterface cho một package API?
A. package-info.java nằm trong chính package API được công bố
B. Application.java tại root, không cần chỉ rõ package API
C. File application.properties trong mọi module tiêu thụ
D. Tất cả interface trong api đều phải khai @Bean
Đáp án đúng: A

Câu 10. Annotation @NamedInterface("spi") dùng để làm gì trong module model?
A. Đánh dấu toàn bộ bean của spi thành transaction proxy
B. Gộp package spi thành một Spring Boot app riêng biệt
C. Tạo interface Java tự động cho mọi class trong spi
D. Đặt tên phần API bổ sung mà module khác có thể sử dụng
Đáp án đúng: D

Câu 11. Module reports cần công bố hợp đồng callback cho module khác nhưng giữ renderer nội bộ. Cách nào phù hợp?
A. Đưa renderer vào spi rồi cấm mọi client import interface
B. Công bố package spi bằng Named Interface, để renderer ở internal
C. Công bố toàn bộ reports.internal vì SPI là phần triển khai
D. Đổi reports.internal thành package root mới của application
Đáp án đúng: B

Câu 12. Khi xem một Named Interface, điều gì xác định thành viên của nó nếu khai trên package?
A. Những type thuộc package được đánh dấu Named Interface
B. Mọi type trong tất cả package con trực tiếp của application
C. Mọi bean dùng cùng qualifier với tên Named Interface
D. Chỉ những method được khai trong một Spring @Controller
Đáp án đúng: A

Câu 13. Trong @ApplicationModule(allowedDependencies="inventory"), inventory được hiểu là gì?
A. Tên class Java phải nằm trong package có tên inventory
B. Tên module được phép phụ thuộc theo khai báo ràng buộc
C. Tên bean mà Spring tự inject vào module đang khai báo
D. Tên một event được publish khi kiểm thử kiến trúc
Đáp án đúng: B

Câu 14. Module checkout được phép phụ thuộc vào inventory nhưng không muốn mở quyền tới billing. Cấu hình nào phục vụ mục tiêu này?
A. @ApplicationModule của inventory khai allowedDependencies là checkout
B. @NamedInterface trong billing được đặt tên checkout
C. @ComponentScan của checkout quét package billing.internal
D. @ApplicationModule của checkout khai allowedDependencies là inventory
Đáp án đúng: D

Câu 15. Khi @ApplicationModule(allowedDependencies="inventory::spi") được dùng, phần spi biểu diễn gì?
A. Named Interface spi do module inventory công bố
B. Java package bất kỳ tên spi bên trong module checkout
C. Một kiểu transaction propagation cho module inventory
D. Một alias của bean inventory được thêm bởi Spring Boot
Đáp án đúng: A

Câu 16. Một module chỉ được phép tham chiếu inventory::spi nhưng lại dùng inventory.internal.StockWriter. Kết luận phù hợp?
A. Hợp lệ vì toàn bộ inventory đều được export qua spi
B. Hợp lệ nếu StockWriter được đánh dấu @Repository
C. Không hợp lệ vì StockWriter thuộc phần internal
D. Không liên quan tới cấu hình allowedDependencies
Đáp án đúng: C

Câu 17. Nếu checkout đã khai allowedDependencies chỉ tới inventory, rồi import billing.BillingFacade, việc verify sẽ phát hiện gì?
A. Dependency tới billing nằm ngoài tập module đã cho phép
B. Tự bổ sung billing vào allowedDependencies của checkout
C. Bỏ qua dependency vì BillingFacade ở root package
D. Tạo một Named Interface billing trong module inventory
Đáp án đúng: A

Câu 18. Nên đặt @ApplicationModule cho cấu hình ranh giới package ở đâu?
A. Trên method @Bean bất kỳ của cấu hình DataSource
B. package-info.java nằm tại root package của module
C. Trên entity class ở tất cả subpackage internal
D. Trong tệp pom.xml của module khi khai dependencies
Đáp án đúng: B

Câu 19. Sử dụng @ApplicationModule(displayName="Order Processing") chủ yếu nhằm gì?
A. Chuyển package com.acme.orders thành com.acme.Order Processing
B. Chỉ định tên database schema cho repository của orders
C. Buộc Spring tạo bean với tên Order Processing
D. Gắn tên mô tả cho module trong metadata và mô hình
Đáp án đúng: D

Câu 20. Một application module của Spring Modulith thông thường được triển khai ra sao?
A. Mỗi module bắt buộc chạy JVM độc lập trên host khác
B. Mỗi module bắt buộc có database riêng và HTTP server
C. Cùng tiến trình và artifact triển khai với các module khác
D. Mỗi module được chạy thành một Spring Boot deployment
Đáp án đúng: C

Câu 21. Spring Modulith giúp modular monolith bằng cách nào?
A. Thay JVM classloader bằng container cho từng module
B. Tự chia ứng dụng thành nhiều image triển khai riêng
C. Mô hình hóa ranh giới và kiểm tra phụ thuộc giữa package
D. Tự quản lý cluster và route mọi request xuyên mạng
Đáp án đúng: C

Câu 22. Trong kiến trúc module theo nghiệp vụ, cấu trúc package nào thường phù hợp hơn?
A. controllers, services, repositories nằm trực tiếp dưới base package
B. dtos, enums, exceptions nằm trực tiếp dưới base package
C. rest, jdbc, messaging nằm trực tiếp dưới base package
D. orders, payments, shipping nằm trực tiếp dưới base package
Đáp án đúng: D

Câu 23. Nếu đặt controller, service và repository thành ba package con trực tiếp dưới base, hệ quả với mô hình mặc định là gì?
A. Chúng tự gộp thành một module nghiệp vụ theo tên entity
B. Chúng có thể bị coi là ba module theo tầng kỹ thuật
C. Chúng bị tự loại khỏi ApplicationModules vì tên kỹ thuật
D. Chúng chỉ được coi là module khi có @NamedInterface
Đáp án đúng: B

Câu 24. Với orders.api, orders.internal và orders.persistence cùng thuộc một module, cách đặt package nào tránh tạo module phụ mặc định?
A. Chuyển api và internal thành hai package ngang cấp với orders
B. Đặt mọi package ở ngoài com.acme để không thuộc application
C. Thêm @Controller lên mỗi package để ghép vào module
D. Đặt api, internal, persistence dưới com.acme.orders
Đáp án đúng: D

Câu 25. Công cụ nào trong Spring Modulith dựng mô hình các module để kiểm tra trong test?
A. ApplicationModules.of(Application.class)
B. ApplicationContext.getBeanDefinitionNames()
C. SpringApplication.run(Application.class)
D. BeanFactoryUtils.beansOfTypeIncludingAncestors()
Đáp án đúng: A

Câu 26. Lời gọi nào thường dùng để kiểm chứng kiến trúc từ một ApplicationModules đã dựng?
A. modules.start() tạo JVM độc lập cho mỗi module
B. modules.deploy() xuất nhiều container từ một jar
C. modules.verify() kiểm tra các quy tắc của module model
D. modules.persist() lưu quan hệ module vào database
Đáp án đúng: C

Câu 27. Một vòng phụ thuộc ở cấp module orders → payments → orders sẽ được xử lý thế nào bởi kiểm chứng mô hình?
A. Được chấp nhận khi hai module đều có public API
B. Báo lỗi vòng dependency giữa orders và payments
C. Được Spring tự cắt vòng bằng cách đổi bean scope
D. Được bỏ qua nếu method @Transactional là read-only
Đáp án đúng: B

Câu 28. Nếu shipping dùng trực tiếp một type chỉ nằm trong orders.internal, ApplicationModules.verify() nhằm phát hiện gì?
A. Lỗi biên dịch Java nếu type là public class
B. Lỗi JSON serialization của mọi event gửi từ shipping
C. Phát hiện type nội bộ orders bị module khác dùng
D. Lỗi thiếu database transaction khi method được gọi
Đáp án đúng: C

Câu 29. Điều kiện nào thường được kiểm tra khi verify mô hình module của Spring Modulith?
A. Chu kỳ, truy cập internal và hạn chế phụ thuộc
B. Hiệu năng truy vấn SQL, query plan và index dữ liệu
C. Bảo mật session HTTP và cấu hình cookie trình duyệt
D. Thời gian startup của Kafka consumer và JMS listener
Đáp án đúng: A

Câu 30. Kiểm thử ApplicationModules.of(Application.class).verify() mang lại giá trị nào cho CI?
A. Tự biến mọi class internal thành public API trước release
B. Chạy end-to-end toàn bộ endpoint HTTP của ứng dụng
C. Thay thế mọi kiểm thử tích hợp cho repository và service
D. Phát hiện sớm vi phạm ranh giới khi code thay đổi
Đáp án đúng: D

Câu 31. Nếu chuyển public interface OrderLookup từ orders gốc xuống orders.internal, điều gì cần đánh giá lại?
A. Spring sẽ tự cập nhật mọi import để trỏ tới named interface
B. Các module khác dùng OrderLookup có thể vi phạm API boundary
C. Interface vẫn thuộc API mặc định vì giữ modifier public
D. Module orders bị xóa khỏi danh sách do thiếu interface
Đáp án đúng: B

Câu 32. Một ApplicationModule mô tả mối quan hệ giữa mô-đun chủ yếu dựa trên gì?
A. Dựa trên dependency giữa type ở các package
B. Số lần API HTTP được người dùng gọi trong production
C. Số lượng row dữ liệu hiện tại của từng JPA entity
D. Tên database table theo quy ước ORM của Spring Data
Đáp án đúng: A

Câu 33. Khi module A import API công khai của B và B import API công khai của A, vấn đề nào vẫn tồn tại?
A. Vòng dependency giữa hai module dù cùng dùng public API
B. Không có vấn đề vì API công khai luôn miễn kiểm tra chu kỳ
C. Chỉ lỗi nếu cả hai module cùng khai @NamedInterface
D. Spring tự gom hai package thành một module mặc định
Đáp án đúng: A

Câu 34. Nếu một class của orders gọi trực tiếp bean implementation trong shipping.internal, thiết kế nào giảm coupling?
A. Đánh dấu bean internal là @Primary để trở thành API
B. Sử dụng contract công bố của shipping, không import internal
C. Đổi scope bean sang prototype để không bị verify
D. Dùng @Autowired trên field thay vì constructor injection
Đáp án đúng: B

Câu 35. Mục đích cốt lõi của named interface so với package gốc module là gì?
A. Đặt tên module con có artifact triển khai độc lập
B. Thay thế Java interface bằng bean registry Spring
C. Công bố một phần API có tên từ package không nằm ở root
D. Định nghĩa riêng package scan cho mọi REST controller
Đáp án đúng: C

Câu 36. Nếu module billing cần các type trong inventory.spi, thiết kế nào đúng về ranh giới?
A. Inventory công bố spi và billing tham chiếu phần API đó
B. Billing tự đánh dấu inventory.internal là public bằng annotation
C. Billing đổi package inventory.spi thành billing.spi qua import
D. Inventory chỉ cần khai public class mà không cần công bố spi
Đáp án đúng: A

Câu 37. Khi review kiến trúc, vì sao hạn chế import class internal giữa các module là quan trọng?
A. Bảo đảm mọi component dùng cùng transaction manager
B. Giảm coupling với implementation nội bộ
C. Giữ mọi class có cùng vòng đời @RequestScope
D. Tự tạo một URL riêng cho mỗi Spring module
Đáp án đúng: B

Câu 38. Một module inventory có package root chứa InventoryApi và internal chứa StockService. Lựa chọn đúng là gì?
A. StockService được công khai vì mọi @Service đều là API
B. InventoryApi là internal trừ khi có @NamedInterface
C. Cả hai luôn được công khai nếu là public Java class
D. InventoryApi là API, StockService là internal
Đáp án đúng: D

Câu 39. Khi cùng thuộc module orders, class trong orders.api có thể tham chiếu public type ở orders.internal không?
A. Không thể, vì mọi import từ subpackage đều bị Modulith cấm
B. Chỉ có thể nếu tất cả method mang @Transactional
C. Chỉ có thể bằng Named Interface của module khác
D. Có thể, vì ranh giới module áp cho truy cập giữa module
Đáp án đúng: D

Câu 40. Nếu shared utility nằm ở com.acme.shared là module riêng mặc định, tác động nào nên cân nhắc?
A. Tất cả type shared tự trở thành Java standard library
B. shared được tự gộp vào base package và không thành module
C. Các module dùng shared sẽ tạo phụ thuộc tới module shared
D. Modulith sẽ sinh bản sao shared trong từng module dùng nó
Đáp án đúng: C

Câu 41. Khi muốn tránh module shared thành nơi mọi domain module phụ thuộc ngược lẫn nhau, cách nào hợp lý?
A. Đưa mọi service nghiệp vụ vào shared để không còn vòng
B. Đặt tất cả repository vào shared để bỏ dependency graph
C. Đánh dấu shared là @Primary cho mọi interface có tên giống nhau
D. Giữ shared nhỏ, ổn định và tránh kéo domain dependency vào đó
Đáp án đúng: D

Câu 42. Nếu tách module notifications ra khỏi orders nhưng vẫn truy cập orders.internal, bước refactor nào nên làm?
A. Chỉ đổi tên bean notifications để tránh dependency check
B. Đổi method trong orders.internal thành static và giữ import
C. Tắt @ComponentScan của orders khi chạy application
D. Đưa hợp đồng cần dùng ra API orders hoặc Named Interface
Đáp án đúng: D

Câu 43. Mục đích của allowedDependencies khi không muốn kết nối nghiệp vụ tùy tiện là gì?
A. Giới hạn số thread được tạo bởi ApplicationContext mỗi module
B. Giới hạn số kết nối JDBC cho phép theo root package
C. Giới hạn module và Named Interface được phép tham chiếu
D. Giới hạn số event được gửi bởi Spring Modulith runtime
Đáp án đúng: C

Câu 44. Giả sử orders được phép phụ thuộc inventory::spi, nhưng cần inventory root API khác. Hướng thay đổi phù hợp là gì?
A. Import trực tiếp inventory.internal để tránh sửa cấu hình
B. Xem lại hợp đồng dependency và mở quyền có chủ đích nếu cần
C. Đặt @Component lên class root API để vượt qua allowedDependencies
D. Đổi tên module inventory trong JVM để verify bỏ qua
Đáp án đúng: B

Câu 45. Khi cần hiển thị ranh giới module và phụ thuộc để thảo luận với nhóm, nên xuất phát từ đâu?
A. Đồ thị transaction manager vì nó quyết định module boundary
B. Danh sách HTTP request log vì request định nghĩa module
C. Mô hình ApplicationModules phản ánh cấu trúc và dependencies
D. Danh sách database connection vì mỗi pool là một module
Đáp án đúng: C

Câu 46. Khi một module chỉ giao tiếp qua API được công bố của module khác, kết quả nào đúng nhất?
A. Giảm phụ thuộc vào implementation nội bộ của module kia
B. Bảo đảm hai module không bao giờ có dependency cycle
C. Tự tạo network isolation giữa hai module cùng JVM
D. Thay thế được toàn bộ kiểm thử contract giữa các module
Đáp án đúng: A

Câu 47. Khi bổ sung một module mới trực tiếp dưới base package, điều gì nên làm để giữ kiến trúc?
A. Bỏ toàn bộ kiểm thử kiến trúc để module được scan nhanh
B. Đặt tên package theo tầng để Spring tự gom module
C. Chạy kiểm tra ApplicationModules và rà lại dependency graph
D. Dùng @Profile tắt các module khác ở môi trường test
Đáp án đúng: C

Câu 48. Nếu một module chỉ khai @ApplicationModule nhưng chưa ghi allowedDependencies, điều nào đúng nhất?
A. Module đó không còn được nhận diện từ cấu trúc package
B. Ranh giới API và kiểm tra chu kỳ vẫn có ý nghĩa
C. Tất cả type trong internal tự trở thành Named Interface
D. Việc verify không còn kiểm tra phụ thuộc với module khác
Đáp án đúng: B
