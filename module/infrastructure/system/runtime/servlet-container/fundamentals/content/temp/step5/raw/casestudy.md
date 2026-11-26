1. Ứng dụng triển khai hai Servlet với mapping /api/* và /api/admin/*; request tới /api/admin/users lại vào handler tổng quát, nhóm cần kiểm tra thứ tự ưu tiên mapping và context path.
2. Một hệ thống cũ đồng thời khai báo mapping chính xác, mapping theo path và mapping phần mở rộng như *.do; vài URL bị xử lý bởi Servlet khác dự kiến và cần xác định quy tắc chọn mapping của container.
3. Reverse proxy thêm tiền tố /portal nhưng WAR cũng được triển khai với context path /portal; request bị lặp tiền tố và trả 404, đội vận hành cần phân định đường dẫn bên ngoài với context path nội bộ.
4. Trang chủ hoạt động khi gọi trực tiếp nhưng URL thư mục trả 404 sau khi chuyển container; ứng dụng có welcome file và static resource nằm dưới web root cần được kiểm tra cùng default servlet.
5. Một ứng dụng khai báo Servlet bằng annotation và web.xml, nhưng cấu hình production không nhận annotation sau khi bật metadata-complete; nhóm cần đánh giá nguồn cấu hình và cách hợp nhất metadata.
6. Hai module dùng cùng tên tham số cấu hình nhưng một module đọc ServletConfig, module kia đọc ServletContext; giá trị bị dùng nhầm giữa cấu hình riêng Servlet và cấu hình toàn ứng dụng.
7. Servlet được cấu hình khởi tạo lười và chỉ lỗi khi request đầu tiên đến do không kết nối được dịch vụ ngoài; đội triển khai cần cân nhắc thời điểm khởi tạo và kiểm tra readiness.
8. Một Servlet dùng chung một instance cho nhiều request và lưu người dùng hiện tại vào field của instance; tải đồng thời khiến dữ liệu giữa hai request bị lẫn.
9. Trong lúc undeploy, container ngừng nhận request mới nhưng thời gian drain của nền tảng ngắn hơn request đang chạy; nhóm cần xem xét graceful shutdown, thời gian chờ và đóng tài nguyên.
10. Nhiều Filter xử lý encoding, xác thực, correlation ID và ghi log nhưng thứ tự mapping khác nhau giữa môi trường; lỗi hiển thị ký tự và log thiếu danh tính xuất hiện không ổn định.
11. Filter chỉ được map cho REQUEST nên không chạy khi Servlet forward sang trang lỗi; nhóm cần xác định dispatcher type phù hợp cho FORWARD, INCLUDE, ERROR và ASYNC.
12. Filter xác thực trả response trực tiếp khi thiếu quyền nhưng một nhánh khác quên gọi FilterChain.doFilter; request hợp lệ bị dừng trước khi tới Servlet.
13. Filter kiểm tra nội dung request đọc hết InputStream để ghi log, khiến Servlet phía sau không còn body; nhóm cần chọn cách giới hạn hoặc bọc request an toàn.
14. Filter nén response dùng wrapper nhưng flush sớm làm response bị commit trước khi header được cập nhật; cần phân tích buffer, flush và thời điểm gửi response.
15. ServletContextListener tạo connection pool rồi bước khởi tạo tiếp theo thất bại; ứng dụng cần thu hồi tài nguyên đã tạo một phần để tránh rò rỉ qua các lần deploy lại.
16. Bộ đếm phiên đăng nhập dùng HttpSessionListener cho thấy số session khác nhau giữa các node sau khi bật clustering; nhóm cần phân biệt event vòng đời cục bộ với cơ chế session phân tán.
17. HttpSessionAttributeListener ghi audit khi thuộc tính session thay đổi, nhưng hai request đồng thời cập nhật cùng thuộc tính; nhóm cần xác định tính nguyên tử và cách phối hợp dữ liệu.
18. Người dùng đăng nhập thành công nhưng session ID trước đăng nhập vẫn còn hiệu lực; nhóm bảo mật cần xem xét session fixation và thời điểm đổi định danh phiên.
19. Cookie session hoạt động trên HTTP nội bộ nhưng mất khi qua HTTPS proxy hoặc bị gửi trong ngữ cảnh cross-site; cần kiểm tra Secure, HttpOnly, SameSite, Path và Domain.
20. Ứng dụng bật URL rewriting để duy trì session cho client không nhận cookie; session ID xuất hiện trong URL và lọt vào access log, lịch sử trình duyệt cùng header Referer.
21. Một request đang xử lý gọi invalidate session trong khi tab khác tiếp tục dùng session đó; ứng dụng phát sinh IllegalStateException và cần quản lý truy cập đồng thời, hết hạn.
22. Ứng dụng chạy nhiều node với sticky session; khi node bị thay thế, người dùng mất trạng thái đăng nhập dù các node còn lại vẫn khỏe mạnh.
23. Session chứa giỏ hàng lớn và nhiều đối tượng không Serializable; bật session persistence khiến restart hoặc replication phát sinh lỗi tuần tự hóa và tăng độ trễ.
24. Servlet gọi startAsync để chờ dịch vụ ngoài nhưng luồng xử lý không gọi dispatch hoặc complete; request treo đến timeout và chiếm tài nguyên của container.
25. AsyncListener nhận onTimeout và worker hoàn tất gần như cùng lúc; response bị ghi hai lần, nhóm cần xử lý trạng thái hoàn tất và đồng bộ callback.
26. Ứng dụng bật async trên Servlet nhưng một Filter trong chain không hỗ trợ async; startAsync thất bại ở production dù môi trường phát triển chạy được.
27. AsyncContext được truyền cho nhiều tác vụ nền và hai tác vụ cùng gọi complete; cần phân tích quyền sở hữu vòng đời request và xử lý kết quả đến muộn.
28. Thread pool xử lý request của container cạn kiệt vì mỗi Servlet chờ đồng bộ một API thanh toán chậm; latency tăng và request mới xếp hàng hoặc bị từ chối.
29. Số thread xử lý request tăng nhưng request vẫn chờ lấy connection JDBC; nhóm vận hành cần đối chiếu giới hạn thread pool của container với connection pool của ứng dụng.
30. Filter đặt tenant và thông tin người dùng vào ThreadLocal nhưng không dọn ở nhánh exception; request tiếp theo chạy trên cùng thread có thể nhận nhầm ngữ cảnh.
31. Servlet tự tạo thread nền để gửi email sau response; khi undeploy, thread vẫn giữ classloader của ứng dụng và tiếp tục chạy ngoài vòng đời container.
32. Hai WAR cần hai phiên bản thư viện khác nhau nhưng một thư viện lại được đặt trong thư mục lib dùng chung của container; lỗi tương thích xuất hiện giữa các ứng dụng.
33. Ứng dụng biên dịch với javax.servlet nhưng container mới chỉ cung cấp jakarta.servlet; deployment thất bại do khác namespace dù API và tên lớp có vẻ tương tự.
34. Sau nhiều lần redeploy, heap tăng dần và classloader cũ vẫn còn trong heap dump; nhóm cần tìm thread, ThreadLocal, JDBC driver hoặc static reference giữ classloader.
35. Thư viện dùng Thread Context ClassLoader để tìm service provider và resource; tác vụ nền chạy sau khi request kết thúc lại dùng sai classloader của container.
36. Hai WAR cùng cấu hình context root rỗng khi triển khai vào một container; một ứng dụng chiếm root context và ứng dụng kia không khởi động như mong đợi.
37. Ứng dụng tạo redirect HTTP dù client truy cập HTTPS qua load balancer; request scheme và secure cookie sai vì container chưa được cấu hình tin cậy forwarded headers.
38. Upload multipart lớn làm đầy thư mục tạm của container và gây lỗi cho cả ứng dụng khác; nhóm cần xem giới hạn kích thước, vị trí lưu tạm và dọn file sau xử lý.
39. Servlet đọc request parameter trước khi Filter đặt character encoding; dữ liệu tiếng Việt bị lỗi vì body đã được parse với charset mặc định.
40. URL bị chặn bởi security constraint trong web.xml dù framework đã xác thực người dùng; nhóm cần lần theo thứ tự xác thực container, role mapping và bảo vệ ở framework.
41. Trình duyệt gửi CORS preflight OPTIONS nhưng Filter xác thực yêu cầu session trước khi xử lý CORS; API bị chặn dù request thực tế có token hợp lệ.
42. Ứng dụng dùng cookie session cho xác thực nhưng thiếu CSRF protection trên thao tác thay đổi dữ liệu; đội bảo mật cần đánh giá ranh giới giữa cookie, SameSite và token chống giả mạo.
43. Spring MVC DispatcherServlet chỉ nhận request trong mapping riêng, trong khi Filter của container chạy trước framework; nhóm cần phân biệt Filter, Servlet mapping và HandlerInterceptor.
44. Controller của framework trả response bất đồng bộ nhưng timeout của framework và async timeout của Servlet container khác nhau; người dùng nhận lỗi không nhất quán khi dịch vụ chậm.
45. Exception phát sinh sau khi response đã commit nên error page của container không thể thay nội dung; nhóm cần phân biệt exception dispatch với xử lý lỗi ở framework.
46. Access log của container ghi status 200 nhưng người dùng nhận lỗi nghiệp vụ do framework xử lý trong response body; nhóm cần liên kết access log, application log và trace.
47. Pod được đánh dấu ready ngay khi process Java mở port dù ServletContext vẫn đang khởi tạo datasource và listener; traffic đến sớm gây lỗi ngẫu nhiên sau deploy.
48. Ứng dụng tra cứu DataSource qua JNDI hoạt động ở máy phát triển nhưng thất bại trên container production do resource binding và quyền truy cập khác nhau.
