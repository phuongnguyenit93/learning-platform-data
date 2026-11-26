Câu 1. Mục tiêu chính khi tích hợp JMX vào ứng dụng Spring là gì?
A. Thay cơ chế Spring MVC xử lý HTTP request của ứng dụng.
B. Quan sát thuộc tính và gọi thao tác quản trị qua MBean.
C. Định nghĩa transaction JPA cho các repository được quản lý.
D. Thay thế BeanFactory trong việc khởi tạo bean theo scope.
Đáp án đúng: B

Câu 2. Trong kiến trúc JMX, `MBeanServer` đảm nhiệm việc gì?
A. Sinh class Java proxy cho các bean trong ApplicationContext.
B. Tạo HTTP controller từ các operation của từng MBean.
C. Giữ registry MBean và cho phép truy cập qua ObjectName.
D. Thực thi tác vụ scheduling của bean theo chu kỳ cấu hình.
Đáp án đúng: C

Câu 3. Vai trò của Spring `MBeanExporter` khi cấu hình JMX là gì?
A. Chuyển các MBean operation thành endpoint Spring MVC.
B. Đăng ký Spring bean thành MBean với MBeanServer.
C. Đóng vai trò JConsole và hiển thị biểu đồ của bean.
D. Gửi email cảnh báo mỗi khi một JMX attribute thay đổi.
Đáp án đúng: B

Câu 4. Annotation cấu hình nào giúp bật hỗ trợ export MBean theo annotation trong Spring?
A. Đặt `@EnableAsync` lên class cấu hình thích hợp.
B. Đặt `@EnableTransactionManagement` lên class cấu hình.
C. Đặt `@EnableScheduling` lên class cấu hình thích hợp.
D. Đặt `@EnableMBeanExport` lên class cấu hình thích hợp.
Đáp án đúng: D

Câu 5. Trên class Spring bean, `@ManagedResource` thường biểu thị điều gì?
A. Bean sẽ tự tạo connection pool cho các JMX client.
B. Bean được khai báo là listener nhận Spring application event.
C. Bean được mô tả làm JMX managed resource để export.
D. Bean sẽ tự mở HTTP endpoint quản trị bằng REST.
Đáp án đúng: C

Câu 6. Chuỗi nào là `ObjectName` JMX hợp lệ cho một cache tên primary?
A. `com.example:type=Cache,name=primary` trong một domain.
B. `com.example:type=Cache:name=primary` trong một domain.
C. `com.example/type=Cache,name=primary` trong một domain.
D. `com.example,type=Cache,name=primary` trong một domain.
Đáp án đúng: A

Câu 7. Hai MBean đăng ký vào cùng server với cùng `ObjectName` gây vấn đề gì?
A. Hai MBean tự hợp nhất attribute và operation theo tên.
B. JConsole đổi nhãn hiển thị còn registry không xung đột.
C. Server tự thêm timestamp cho ObjectName để không bị trùng.
D. Xảy ra xung đột tên; cần tên riêng hoặc chính sách xử lý.
Đáp án đúng: D

Câu 8. Muốn lấy tên MBean từ `@ManagedResource(objectName=...)`, naming strategy nào hỗ trợ?
A. Dùng Spring `MetadataNamingStrategy` đọc metadata quản trị.
B. Dùng Spring `KeyNamingStrategy` đọc thuộc tính entity ID.
C. Dùng Spring `BeanNameGenerator` để tạo tên JMX từ URL.
D. Dùng Spring `PropertyPlaceholderConfigurer` để gọi operation.
Đáp án đúng: A

Câu 9. Trên getter `getActiveCount()`, `@ManagedAttribute` được dùng để làm gì?
A. Tăng counter khi JConsole thực hiện thao tác gọi getter.
B. Công bố getter thành listener nhận notification từ MBean.
C. Công bố giá trị activeCount thành thuộc tính đọc qua JMX.
D. Đăng ký lại MBean sau khi giá trị của getter thay đổi.
Đáp án đúng: C

Câu 10. Muốn JConsole chỉnh được thuộc tính `threshold` của MBean, thiết kế nào phù hợp?
A. Đổi ObjectName thành threshold để server cho phép sửa value.
B. Khai báo notification có tên threshold rồi chờ JConsole.
C. Export getter và setter thích hợp cho thuộc tính có thể ghi.
D. Export getter và giả định JConsole suy ra setter Java.
Đáp án đúng: C

Câu 11. Với method `resetCounters()`, annotation nào dùng để công bố thành JMX operation?
A. Đánh dấu method bằng `@ManagedNotification` để nhận command.
B. Đánh dấu method bằng `@ManagedAttribute` như field đọc thuần.
C. Đánh dấu method bằng `@ManagedResource` thay cho class bean.
D. Đánh dấu method bằng `@ManagedOperation` khi export bean.
Đáp án đúng: D

Câu 12. `@ManagedOperationParameter` trong Spring JMX chủ yếu cung cấp gì?
A. Giá trị mặc định để JVM tự gọi operation khi không có input.
B. Cơ chế validation dành cho tham số nhận từ JConsole.
C. Quyền truy cập theo role cho từng tham số của operation.
D. Metadata tên và mô tả tham số của operation được export.
Đáp án đúng: D

Câu 13. Khi gắn `@ManagedMetric(metricType=MetricType.COUNTER)`, mục tiêu phù hợp là gì?
A. Công bố metric kèm metadata kiểu counter cho công cụ JMX.
B. Đặt metric vào transaction để rollback mỗi khi client đọc.
C. Chuyển metric thành Prometheus endpoint mà không cần exporter.
D. Tạo scheduler để tăng giá trị metric theo thời gian.
Đáp án đúng: A

Câu 14. `@ManagedNotification` trên managed resource giúp mô tả điều gì?
A. Tạo durable queue cho các notification của Spring bean.
B. Khai báo loại notification được MBean hỗ trợ trong metadata.
C. Gửi notification mỗi khi getter được gọi mà không cần code.
D. Đăng ký HTTP webhook nhận notification từ hệ thống khác.
Đáp án đúng: B

Câu 15. Khi client gọi `MBeanServer.getMBeanInfo(name)`, thường nhận dữ liệu gì?
A. Metadata về attribute, operation và notification của MBean.
B. Giá trị hiện tại của các attribute dưới dạng JSON.
C. Lịch sử các lần client đã gọi MBean operation trên server.
D. Danh sách các HTTP endpoint thuộc Spring ApplicationContext.
Đáp án đúng: A

Câu 16. Khi dùng metadata annotation để build JMX ModelMBeanInfo, Spring class nào phù hợp?
A. Dùng `BeanPropertyRowMapper` đọc annotation từ ResultSet.
B. Dùng `SimpleMappingExceptionResolver` ánh xạ operation.
C. Dùng `MethodValidationPostProcessor` sinh JMX ModelMBeanInfo.
D. Dùng `AnnotationMBeanInfoAssembler` xử lý annotation JMX.
Đáp án đúng: D

Câu 17. Nếu muốn export một bean thủ công qua `MBeanExporter` thay vì tự động dò, nên cấu hình gì?
A. Đặt bean vào map `advice` của AOP proxy rồi gọi exporter.
B. Đưa bean và ObjectName vào map `beans` của exporter.
C. Gán bean vào `ApplicationEventMulticaster` để mở operation.
D. Đăng ký bean vào `ViewResolver` để MBeanServer tra cứu.
Đáp án đúng: B

Câu 18. `RegistrationPolicy.IGNORE_EXISTING` dùng với MBeanExporter có tác dụng nào?
A. Xóa MBean cũ trước khi đăng ký object mới cùng ObjectName.
B. Đổi ObjectName hiện hữu sang tên tự động để nhận bean mới.
C. Đưa các operation từ hai bean trùng tên vào một MBean.
D. Bỏ qua đăng ký mới nếu ObjectName đã tồn tại trên server.
Đáp án đúng: D

Câu 19. JMX client muốn đọc attribute `ActiveCount` đã export; lệnh `MBeanServer` nào phù hợp?
A. Gọi `getAttribute(objectName, "ActiveCount")` trên server.
B. Gọi `queryNames(objectName, null)` để nhận giá trị counter.
C. Gọi `invoke(objectName, "ActiveCount", ...)` như một operation.
D. Gọi `getMBeanInfo(objectName)` rồi coi metadata là counter.
Đáp án đúng: A

Câu 20. Để JMX client thực thi operation `resetCounters`, API nào của `MBeanServer` phù hợp?
A. Gọi `getAttribute(objectName, "resetCounters")` để thực thi.
B. Gọi `invoke(objectName, "resetCounters", params, signature)`.
C. Gọi `queryNames(objectName, null)` để trigger operation.
D. Gọi `addNotificationListener` để chạy operation lập tức.
Đáp án đúng: B

Câu 21. Muốn liệt kê các MBean trong domain `com.example`, thao tác nào phù hợp?
A. Gọi `invoke` với operation `listMBeans` do JMX tự tạo.
B. Gọi `queryNames` với một `ObjectName` pattern thích hợp.
C. Gọi `setAttribute` trên domain để đọc danh sách bean.
D. Gọi `getAttribute` bằng tên domain nhưng không có property.
Đáp án đúng: B

Câu 22. Spring bean muốn chủ động phát JMX notification, interface nào có thể implement?
A. Triển khai `MBeanServerConnection` để nhận event từ publisher.
B. Triển khai `ApplicationListener` để nhận remote JMX listener.
C. Triển khai `NotificationPublisherAware` để nhận publisher.
D. Triển khai `BeanNameAware` để tự động phát notification.
Đáp án đúng: C

Câu 23. Sau khi Spring cấp `NotificationPublisher`, bean phát sự kiện JMX bằng cách nào?
A. Tạo `Notification` rồi gọi `sendNotification` trên publisher.
B. Gọi `@ManagedNotification` trực tiếp trên instance của bean.
C. Gọi `ObjectName.getKeyPropertyList()` để broadcast message.
D. Gọi `MBeanServer.queryNames` để phát event đến listener.
Đáp án đúng: A

Câu 24. Một công cụ JMX muốn đăng ký nhận notification từ MBean, cần dùng gì?
A. Gắn `ApplicationEventPublisher` qua `getMBeanInfo`.
B. Gắn `NotificationListener` qua `addNotificationListener`.
C. Gắn `RowCallbackHandler` qua `MBeanServer.registerMBean`.
D. Gắn `TaskScheduler` qua `MBeanServer.queryNames` của bean.
Đáp án đúng: B

Câu 25. Khi client ngắt kết nối JMX đúng lúc có notification, điều nào cần lưu ý?
A. Notification được ghi vào database nhờ MBeanExporter mặc định.
B. JMX giữ notification chưa ACK đến khi client kết nối lại.
C. Notification thông thường không có cơ chế lưu và phát lại bền vững.
D. Client nhận lại notification đã mất khi chạy getMBeanInfo.
Đáp án đúng: C

Câu 26. Muốn gọi MBean như một Java interface từ client Spring, bean hỗ trợ nào phù hợp?
A. Dùng `MBeanExporter` để tạo client proxy từ HTTP controller.
B. Dùng `MBeanServerFactoryBean` để sinh proxy của HTTP service.
C. Dùng `JmxAttributeSource` thay cho Java interface proxy.
D. Dùng `MBeanProxyFactoryBean` cấu hình ObjectName và interface.
Đáp án đúng: D

Câu 27. `MBeanServerConnection` chủ yếu hữu ích cho kịch bản nào?
A. Client truy cập attribute và operation MBean qua kết nối JMX.
B. Exporter đóng gói Notification thành HTTP response của MVC.
C. JConsole tự sinh Spring bean từ MBean attribute trên server.
D. Service khởi tạo DataSource rồi tự mở transaction của MBean.
Đáp án đúng: A

Câu 28. Với JConsole, người vận hành thường quan sát MBean tùy chỉnh ở đâu?
A. Chọn tab `Classes` để chỉnh JMX ObjectName của Spring bean.
B. Chọn tab `VM Summary` để gọi method resetCounters của MBean.
C. Chọn tab `Threads` để xem các repository REST endpoint.
D. Chọn tab `MBeans` để xem thuộc tính và gọi operation.
Đáp án đúng: D

Câu 29. Ứng dụng không có endpoint HTTP quản trị nhưng MBean đã đăng ký; nhận định nào đúng?
A. JConsole cần `DispatcherServlet` để gọi MBean operation.
B. MBeanServer tạo route Spring MVC cho managed bean.
C. MBean có thể được quản lý qua JMX mà không cần REST endpoint.
D. JMX yêu cầu bean được gắn `@RestController` để hoạt động.
Đáp án đúng: C

Câu 30. Khi bật remote JMX cho production, cấu hình an toàn nào phù hợp?
A. Đổi cổng mặc định rồi bỏ kiểm soát truy cập JMX.
B. Bật xác thực, TLS và giới hạn truy cập mạng tới JMX.
C. Tắt xác thực để JConsole có thể kết nối từ mọi máy.
D. Bật JMX agent và bỏ kiểm tra chứng chỉ khi dùng TLS.
Đáp án đúng: B

Câu 31. Một MBean có thể hiển thị chuỗi kết nối chứa password; lựa chọn thiết kế nào an toàn?
A. Dựa vào việc JConsole ẩn field nếu attribute có tên password.
B. Đặt password vào ObjectName để tránh expose như attribute.
C. Không export secret thô, đồng thời giới hạn quyền đọc JMX.
D. Đổi kiểu attribute sang String và coi TLS ngăn đọc nội bộ.
Đáp án đúng: C

Câu 32. Muốn kiểm thử Spring JMX export và operation thực sự hoạt động, hướng nào phù hợp?
A. Khởi động Spring context, query MBeanServer rồi đọc/gọi MBean.
B. Test HTTP controller thay vì chạy quản lý MBean.
C. Kiểm tra annotation trên class nhưng không đăng ký MBean.
D. Mock `NotificationPublisher` rồi suy ra MBeanServer đã sẵn sàng.
Đáp án đúng: A
