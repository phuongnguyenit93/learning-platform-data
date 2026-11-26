Câu 01. Mục tiêu chính của externalized configuration trong Spring Boot là gì?
A. Tự thay đổi cấu trúc bean dựa trên tải CPU của JVM
B. Cùng artifact chạy nhiều môi trường với giá trị cấu hình khác
C. Biên dịch một artifact riêng cho từng môi trường triển khai
D. Lưu trạng thái phiên HTTP vào từng PropertySource của ứng dụng
Đáp án đúng: B

Câu 02. File đóng gói đặt `server.port=8080`, còn chạy với `--server.port=9090`; cổng nào có hiệu lực?
A. Cổng 9090 do tham số command line được ưu tiên hơn file
B. Cổng 8080 do file cấu hình đóng gói được ưu tiên hơn CLI
C. Cổng ngẫu nhiên do hai nguồn cùng khai báo một khóa
D. Cổng mặc định 8080 do Spring bỏ qua tham số dòng lệnh
Đáp án đúng: A

Câu 03. Nếu biến môi trường `APP_MODE=prod` và file chứa `app.mode=dev`, giá trị đọc được thông thường là gì?
A. Giá trị `prod` vì biến môi trường ưu tiên hơn config file
B. Giá trị rỗng vì hai PropertySource xung đột tên thuộc tính
C. Giá trị `default` vì Spring không hỗ trợ env overrides
D. Giá trị `dev` vì file thuộc classpath ưu tiên hơn hệ điều hành
Đáp án đúng: A

Câu 04. Biến môi trường nào biểu diễn khóa cấu hình `server.port` trong Spring Boot?
A. `SERVERPORT` được ánh xạ sang thuộc tính `server.port`
B. `SPRING_PORT` được ánh xạ sang thuộc tính `server.port`
C. `SERVER_PORT` được ánh xạ sang thuộc tính `server.port`
D. `PORT_SERVER` được ánh xạ sang thuộc tính `server.port`
Đáp án đúng: C

Câu 05. Với YAML `app: {timeout: 3s}`, khóa phẳng nào được tạo khi nạp cấu hình?
A. Khóa `app.timeout` có giá trị chuỗi cấu hình `3s`
B. Khóa `timeout.app` có giá trị chuỗi cấu hình `3s`
C. Khóa `app.timeout.3s` có giá trị boolean `true`
D. Khóa `app` có giá trị duration và không có khóa con
Đáp án đúng: A

Câu 06. Placeholder `${api.host:localhost}` có ý nghĩa gì khi `api.host` chưa có giá trị?
A. Dùng `localhost` làm giá trị dự phòng cho thuộc tính này
B. Dùng `api.host` làm chuỗi cố định trong giá trị đã bind
C. Đọc `localhost` như tên profile cần được kích hoạt
D. Báo lỗi placeholder do thuộc tính không nằm trong YAML
Đáp án đúng: A

Câu 07. Cách chỉ định profile `prod` bằng tham số chạy Spring Boot nào phù hợp?
A. Truyền `--spring.application.name=prod` để bật profile
B. Truyền `--spring.profiles.active=prod` khi khởi động
C. Truyền `--spring.config.activate=prod` khi khởi động
D. Truyền `--spring.profiles.default=prod` để ép active
Đáp án đúng: B

Câu 08. Khi profile `prod` hoạt động, `application-prod.yml` có thể tác động thế nào?
A. Bị bỏ qua do file cơ sở được nạp sau các profile
B. Ghi đè giá trị trùng khóa trong `application.yml` cơ sở
C. Chỉ cung cấp metadata cho bean mà không đổi thuộc tính
D. Được dùng để cập nhật trọng số của thư viện Spring Boot
Đáp án đúng: B

Câu 09. Trong một file YAML nhiều document, khóa nào kích hoạt một document theo profile?
A. `spring.application.name` chọn document dựa vào tên bean
B. `spring.main.banner-mode` chọn document dựa vào môi trường
C. `spring.profiles.default` chọn document dựa vào tên nhóm
D. `spring.config.activate.on-profile` chọn document phù hợp
Đáp án đúng: D

Câu 10. Một profile group tên `production` chứa `db-prod` và `metrics`; kích hoạt `production` dẫn tới gì?
A. Các profile thành viên trong nhóm cũng được kích hoạt
B. Group chỉ có hiệu lực khi Java code gọi `@Profile`
C. Nhóm chỉ đổi tên profile được ghi vào log startup
D. Các profile thành viên được vô hiệu hóa để tránh trùng
Đáp án đúng: A

Câu 11. Khi không có active profile, `spring.profiles.default=local` tác động ra sao?
A. Profile `local` được cộng thêm vào active profile `prod`
B. Profile `local` thay tên bean của `ApplicationContext`
C. Profile `local` được dùng làm profile mặc định
D. Profile `local` đổi thư mục lưu cache của build Maven
Đáp án đúng: C

Câu 12. Cùng khóa trong file cấu hình ngoài JAR và file đóng gói JAR, tại các vị trí mặc định, nguồn nào ưu tiên?
A. Giá trị từ bean `@Value` có sẵn được chọn trước
B. Giá trị từ cấu hình bên ngoài JAR được chọn trước
C. Giá trị từ `@Profile` được tính như thuộc tính mới
D. Giá trị từ file nằm trong JAR được chọn trước
Đáp án đúng: B

Câu 13. Muốn bổ sung thư mục cấu hình mới mà vẫn giữ các vị trí tìm mặc định, dùng thuộc tính nào?
A. `spring.profiles.active` chọn thư mục theo profile
B. `spring.config.additional-location` bổ sung nơi tìm config
C. `spring.config.location` thay thế toàn bộ vị trí mặc định
D. `spring.config.name` đổi tên basename được tìm kiếm
Đáp án đúng: B

Câu 14. Khi dùng `spring.config.location` để chỉ rõ vị trí cấu hình, điểm khác với additional-location là gì?
A. Nó thay các vị trí tìm cấu hình mặc định bằng nơi đã chỉ
B. Nó giữ toàn bộ vị trí mặc định rồi ghép thêm nơi đã chỉ
C. Nó đổi thứ tự các PropertySource của biến môi trường
D. Nó được áp dụng sau khi các bean singleton khởi tạo
Đáp án đúng: A

Câu 15. Muốn tùy chọn file cấu hình ngoài có thể không tồn tại mà startup vẫn tiếp tục, cú pháp nào phù hợp?
A. Đổi `spring.config.name` thành `optional` trong file cơ sở
B. Thêm profile `ignore-missing` vào `@ActiveProfiles`
C. Thêm tiền tố `required:` trước vị trí cấu hình được nạp
D. Thêm tiền tố `optional:` trước vị trí cấu hình được nạp
Đáp án đúng: D

Câu 16. Muốn nạp thêm file `extra.properties` từ config data, cấu hình nào phù hợp?
A. `spring.application.name=optional:file:./extra.properties`
B. `spring.config.name=optional:file:./extra.properties`
C. `spring.config.import=optional:file:./extra.properties`
D. `spring.profiles.active=optional:file:./extra.properties`
Đáp án đúng: C

Câu 17. Với secret mount thành các file, `configtree:/run/secrets/` được dùng để làm gì?
A. Đọc tên file làm profile và nội dung làm tên bean component
B. Đọc thư mục làm khóa và tên file làm cổng web server
C. Đọc tên file làm khóa và nội dung file làm giá trị cấu hình
D. Đọc nội dung file thành YAML rồi tạo profile theo tên file
Đáp án đúng: C

Câu 18. Muốn Spring tìm `service.properties` thay tên cơ sở `application.properties`, nên đặt gì từ CLI hoặc env sớm?
A. Đặt `spring.application.name=service` sau bước context refresh
B. Đặt `spring.config.import=service` trong bean `@PostConstruct`
C. Đặt `spring.profiles.active=service` trước bước nạp config data
D. Đặt `spring.config.name=service` trước bước nạp config data
Đáp án đúng: D

Câu 19. Đọc một property linh hoạt từ code khi đã có `Environment` của Spring, cách nào phù hợp?
A. Gọi `environment.getSource("app.timeout")` để lấy giá trị
B. Gọi `environment.getBean("app.timeout")` để lấy giá trị
C. Gọi `environment.getProperty("app.timeout")` để lấy giá trị
D. Gọi `environment.getProfile("app.timeout")` để lấy giá trị
Đáp án đúng: C

Câu 20. Khi chèn một thuộc tính đơn vào tham số constructor của bean qua annotation, thường dùng gì?
A. Dùng `@Profile("${app.host}")` để lấy giá trị đã resolve
B. Dùng `@Order("${app.host}")` để lấy giá trị đã resolve
C. Dùng `@Value("${app.host}")` để lấy giá trị đã resolve
D. Dùng `@Primary("${app.host}")` để lấy giá trị đã resolve
Đáp án đúng: C

Câu 21. Một nhóm cấu hình `app.mail.host`, `app.mail.port` nên được bind có kiểu và dùng lại; chọn gì?
A. Tạo bean `@PropertySource(prefix="app.mail")` để bind nhóm
B. Tạo bean `@ConfigurationProperties(prefix="app.mail")`
C. Tạo bean `@Qualifier(prefix="app.mail")` để bind cả nhóm
D. Tạo bean `@Profile(prefix="app.mail")` để bind cả nhóm
Đáp án đúng: B

Câu 22. Các lớp `@ConfigurationProperties` không gắn `@Component` cần được phát hiện qua package scan; annotation nào phù hợp?
A. Thêm `@EnableScheduling` trên lớp cấu hình để scan record
B. Thêm `@ConfigurationPropertiesScan` trên lớp cấu hình
C. Thêm `@ComponentScan` trên record chưa được khai báo bean
D. Thêm `@PropertySource` trên lớp cấu hình để scan record
Đáp án đúng: B

Câu 23. Muốn đăng ký cụ thể lớp `MailProperties` đã được annotate `@ConfigurationProperties`, dùng gì?
A. `@EnableAutoConfiguration(MailProperties.class)`
B. `@ImportResource(MailProperties.class)` khi bind profile
C. `@EnableConfigurationProperties(MailProperties.class)`
D. `@PropertySource("classpath:mail.properties")` đăng ký bean props
Đáp án đúng: C

Câu 24. Trong Spring Boot 3, một record có một constructor để bind `@ConfigurationProperties` có thể hoạt động theo cách nào?
A. Record phải có constructor không đối số để nhận giá trị
B. Binding chỉ chạy khi record được gắn `@RequestBody`
C. Spring phải gọi setter public để gán các trường record
D. Constructor binding được suy ra từ constructor của record
Đáp án đúng: D

Câu 25. Trong `@ConfigurationProperties(prefix="my")`, khóa `my.service-timeout` bind vào trường `serviceTimeout` nhờ cơ chế nào?
A. Placeholder resolution tự chuyển key thành system property
B. Relaxed binding nhận dạng biến thể tên property với tên field
C. Profile matching tự đổi tên file thành `my.service.timeout`
D. PropertySource ưu tiên key có dấu gạch ngang hơn dấu chấm
Đáp án đúng: B

Câu 26. Biến môi trường `APP_TIMEOUT` thường được map đến tên property nào?
A. Khóa `app-timeout` nhờ đổi dấu chấm thành dấu gạch ngang
B. Khóa `app_timeout` nhưng không thể truy cập dưới tên khác
C. Khóa `timeout.app` nhờ đảo thứ tự token trong biến env
D. Khóa `app.timeout` nhờ quy tắc tên env của Spring Boot
Đáp án đúng: D

Câu 27. Khi bind `app.wait=5s` vào trường `Duration` trong `@ConfigurationProperties`, kết quả nào hợp lý?
A. Một `Duration` có độ dài năm phút
B. Giữ nguyên chuỗi `5s` trong field `Duration`
C. Một `Duration` có độ dài năm mili giây
D. Một `Duration` có độ dài năm giây
Đáp án đúng: D

Câu 28. Khi bind `app.limit=16MB` vào trường `DataSize`, ý nghĩa giá trị được bind là gì?
A. Một chuỗi `16MB` được giữ nguyên trong trường DataSize
B. Một `DataSize` có kích thước mười sáu megabyte
C. Một `DataSize` có kích thước mười sáu byte
D. Một `DataSize` có kích thước mười sáu gigabyte
Đáp án đúng: B

Câu 29. Với cấu hình `app.mail.host`, mô hình class nào giúp bind thông tin lồng nhau?
A. Có field `mail.host` trong Java và bỏ object cấu hình lồng
B. Có field `host` tại root và không khai báo prefix `app`
C. Có một bean `@Profile("mail")` thay cho object cấu hình
D. Có object `mail` với field `host` trong properties của `app`
Đáp án đúng: D

Câu 30. Với constructor-bound `@ConfigurationProperties`, muốn giá trị mặc định cho tham số thiếu cấu hình, dùng gì?
A. Annotate tham số bằng `@DefaultValue` khi bind constructor
B. Annotate tham số bằng `@Profile` khi bind constructor
C. Annotate tham số bằng `@Primary` khi bind constructor
D. Annotate tham số bằng `@Order` khi bind constructor
Đáp án đúng: A

Câu 31. Để kiểm giá trị `@ConfigurationProperties` như host không rỗng, với Bean Validation trên classpath, nên làm gì?
A. Thêm `@PropertySource` và constraint như `@Bean` tại field
B. Thêm `@Profile` và constraint như `@Order` tại field
C. Thêm `@Validated` và constraint như `@NotBlank` tại field
D. Thêm `@Primary` và constraint như `@Qualifier` tại field
Đáp án đúng: C

Câu 32. Khi validation của `@ConfigurationProperties` phát hiện `@NotBlank` sai tại startup, điều gì xảy ra?
A. Giá trị sai được chuyển về profile mặc định khi bind
B. Ứng dụng thay chuỗi trống bằng tên property tương ứng
C. Bean được khởi tạo và lỗi được trì hoãn tới HTTP request
D. Binding bean cấu hình thất bại và startup có thể dừng
Đáp án đúng: D

Câu 33. Muốn coi property lạ dưới prefix là lỗi thay vì bỏ qua khi bind, chọn thuộc tính nào?
A. Đặt `spring.profiles.default=none` trong cấu hình ngoài
B. Đặt `@Primary` trên các bean cùng prefix cấu hình
C. Đặt `ignoreInvalidFields=true` trên `@ConfigurationProperties`
D. Đặt `ignoreUnknownFields=false` trên `@ConfigurationProperties`
Đáp án đúng: D

Câu 34. Với mật khẩu DB thay đổi theo môi trường, cách phân phối nào hạn chế lộ secret trong source?
A. Nạp secret từ secret manager hoặc biến môi trường được bảo vệ
B. Ghi mật khẩu vào log để kiểm tra property đã được bind
C. Commit mật khẩu cùng `application-prod.yml` để dễ tái hiện
D. Đưa mật khẩu vào tên profile để bean tự chọn khi chạy
Đáp án đúng: A

Câu 35. Khi bật endpoint cấu hình của Actuator, cách nào giảm nguy cơ lộ secret?
A. Giới hạn quyền truy cập và giữ cơ chế che giá trị nhạy cảm
B. Mở công khai `/actuator/env` để xác minh ưu tiên thuộc tính
C. Tắt cơ chế lọc giá trị nhưng dùng URL khó đoán hơn
D. Đưa secret vào query parameter để dễ kiểm qua proxy
Đáp án đúng: A

Câu 36. Có cả `application.properties` và `application.yml` tại cùng một vị trí nạp, khóa trùng nhau ưu tiên dạng nào?
A. Spring chọn file có thời điểm sửa gần nhất khi khởi động
B. Spring xem hai file là nhóm rồi báo lỗi khóa trùng
C. File `.properties` được ưu tiên hơn YAML trong cùng vị trí
D. File `.yml` được ưu tiên hơn properties trong cùng vị trí
Đáp án đúng: C

Câu 37. Sau startup, biến môi trường bị thay ngoài tiến trình; một bean `@ConfigurationProperties` thông thường sẽ ra sao?
A. Xóa property khỏi Environment ngay khi request tiếp theo
B. Tự bind lại field khi thread đọc bean ở lần tiếp theo
C. Đổi profile active để nạp lại file ứng dụng từ đầu
D. Giữ giá trị đã bind cho tới khi có cơ chế refresh hoặc restart
Đáp án đúng: D

Câu 38. Muốn kiểm profile `test` trong integration test Spring Boot, dùng annotation nào?
A. `@EnableConfigurationProperties("test")` để chọn profile test
B. `@PropertySource("test")` để kích hoạt profile theo tên
C. `@ActiveProfiles("test")` để kích hoạt cấu hình profile test
D. `@ConditionalOnProperty("test")` để kích hoạt profile test
Đáp án đúng: C

Câu 39. Khi Testcontainers cấp cổng DB động cho test, nên đăng ký property runtime bằng gì?
A. `@DynamicPropertySource` thêm giá trị vào Environment test
B. `@ConfigurationPropertiesScan` bind cổng trước khi container chạy
C. `@Profile` cấp cổng bằng thứ tự khởi tạo của component
D. `@TestPropertySource` đọc cổng động từ profile đóng gói
Đáp án đúng: A

Câu 40. Để chẩn đoán property đã bind và nguồn cấu hình qua Spring Boot Actuator, nên kiểm nhóm endpoint nào?
A. `/actuator/health` và `/actuator/info` thay cho property
B. `/actuator/configprops` và `/actuator/env` với quyền phù hợp
C. `/actuator/beans` và `/actuator/mappings` thay cho property
D. `/actuator/metrics` và `/actuator/threaddump` thay cho config
Đáp án đúng: B
