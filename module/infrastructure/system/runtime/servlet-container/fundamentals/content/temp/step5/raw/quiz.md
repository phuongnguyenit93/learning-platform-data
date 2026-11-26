1. Container chọn Servlet nào khi một request khớp nhiều kiểu URL mapping?
A. Chọn mapping ít wildcard nhất mà không xét loại pattern.
B. Chọn mapping khai báo sớm nhất trong mọi trường hợp.
C. Ưu tiên extension, rồi exact match, longest path, default mapping.
D. Ưu tiên exact match, rồi longest path, extension và default.
Đáp án đúng: D

2. Request /catalog/items.json khớp cả /catalog/* và *.json; mapping nào được chọn?
A. Extension mapping *.json được ưu tiên trước path mapping.
B. Container gọi cả hai Servlet theo thứ tự khai báo mapping.
C. Path mapping /catalog/* được ưu tiên trước extension mapping.
D. Container chọn mapping có thứ tự khai báo trước trong descriptor.
Đáp án đúng: C

3. Ba giá trị context path, servlet path và path info biểu diễn điều gì?
A. Context path chọn Servlet; servlet path là cookie path; path info là fragment.
B. Context path là URL pattern; servlet path là hostname; path info là query string.
C. Context path chọn web app; servlet path và path info mô tả phần đường dẫn còn lại.
D. Context path là query string; servlet path là port; path info là scheme.
Đáp án đúng: C

4. Một request tới URL thư mục cần tìm trang mặc định của ứng dụng; cơ chế nào xử lý?
A. Default servlet chọn file mới nhất trong thư mục làm trang mặc định.
B. Container thử các welcome-file theo thứ tự cấu hình trong web application.
C. Container luôn chuyển request tới index.html trước mọi welcome-file.
D. Servlet được map vào / tự động tạo trang mặc định cho mọi thư mục.
Đáp án đúng: B

5. web.xml đặt metadata-complete=true; ảnh hưởng nào phù hợp nhất?
A. Container không xử lý annotation được dùng để khai báo deployment metadata.
B. Container bỏ qua toàn bộ Servlet, Filter và Listener trong web.xml.
C. Container chuyển tất cả annotation thành cấu hình mặc định.
D. Container tắt annotation chỉ trong các class nằm ngoài WAR.
Đáp án đúng: A

6. Servlet có load-on-startup bằng 2 và Servlet khác bằng 5; điều gì được mong đợi?
A. Servlet có giá trị 5 được khởi tạo trước vì số lớn ưu tiên hơn.
B. Servlet có giá trị 2 được khởi tạo trước Servlet có giá trị 5.
C. Container khởi tạo theo alphabet của tên class, bỏ qua giá trị.
D. Cả hai chỉ khởi tạo khi request đầu tiên tới từng Servlet.
Đáp án đúng: B

7. Trong vòng đời Servlet, container gọi các phương thức theo trình tự nào?
A. Gọi init cho mỗi request, sau đó gọi service và destroy ngay.
B. Gọi service trước init, rồi container mới tạo instance và gọi destroy.
C. Khởi tạo instance, gọi init, xử lý request qua service, rồi destroy.
D. Gọi destroy trước khi ngừng nhận request, rồi tiếp tục service.
Đáp án đúng: C

8. Một Servlet dùng chung instance và nhiều request có thể chạy đồng thời; thiết kế nào an toàn?
A. Lưu user hiện tại trong field instance vì container tạo instance riêng.
B. Giả định container chỉ gọi service tuần tự trên một thread duy nhất.
C. Dùng biến cục bộ cho request và đồng bộ trạng thái chia sẻ.
D. Dùng một biến static để mỗi request có bản sao dữ liệu riêng.
Đáp án đúng: C

9. ServletConfig và ServletContext khác nhau chủ yếu ở phạm vi nào?
A. ServletConfig chia sẻ toàn server; ServletContext thuộc riêng từng request.
B. ServletConfig riêng cho Servlet; ServletContext dùng chung ứng dụng.
C. Cả hai đều chỉ tồn tại trong một lần gọi service của Servlet.
D. ServletContext chỉ chứa init parameter còn ServletConfig chứa session.
Đáp án đúng: B

10. Khi nhiều Filter cùng match một request và được khai báo trong web.xml, thứ tự chain dựa trên điều gì?
A. Thứ tự Filter được khởi tạo theo giá trị load-on-startup của Servlet.
B. Theo thứ tự filter-mapping phù hợp được khai báo trong web.xml.
C. Thứ tự alphabet của class name trong các Filter implementation.
D. Thứ tự ngẫu nhiên do container tối ưu dựa trên thời gian xử lý.
Đáp án đúng: B

11. Một filter-mapping không khai báo dispatcher type; request nào mặc định làm filter chạy?
A. Filter mặc định chỉ chạy khi container phát sinh ERROR dispatch.
B. Filter mặc định chỉ chạy với FORWARD và INCLUDE dispatch.
C. Filter mặc định chạy với mọi dispatcher type của request.
D. REQUEST là dispatcher type mặc định khi không khai báo.
Đáp án đúng: D

12. Filter muốn từ chối request không hợp lệ trước khi tới Servlet; cách xử lý nào đúng?
A. Tạo thread mới để gọi FilterChain sau khi response đã đóng.
B. Gọi Servlet trực tiếp qua RequestDispatcher rồi tiếp tục chain.
C. Ghi response phù hợp và không gọi FilterChain.doFilter.
D. Gọi FilterChain.doFilter trước rồi mới thay response bằng lỗi.
Đáp án đúng: C

13. Muốn Filter được gọi trong lần dispatch có dispatcher type ASYNC, cần cấu hình mapping nào?
A. Đặt async timeout lớn hơn để Filter tự được gọi lại.
B. Chuyển Filter thành Servlet listener để nhận async dispatch.
C. Chỉ khai báo dispatcher type REQUEST vì ASYNC luôn kế thừa nó.
D. Khai báo dispatcher type ASYNC trong mapping của Filter.
Đáp án đúng: D

14. Filter đọc request body để ghi log khiến Servlet phía sau không còn dữ liệu; giải pháp nào phù hợp?
A. Đọc body trong response wrapper để container tự phát lại request.
B. Dùng HttpServletRequestWrapper để buffer body với giới hạn kích thước.
C. Chuyển request body thành query parameter trước khi gọi chain.
D. Đọc lại getInputStream trên request gốc sau khi stream đã được tiêu thụ hết.
Đáp án đúng: B

15. Ứng dụng nhận tiếng Việt sai khi Servlet đọc request parameter; Filter nên đặt encoding lúc nào?
A. Đặt character encoding trước lần đầu đọc parameter hoặc body.
B. Chỉ đặt encoding khi request dùng multipart và có file upload.
C. Đặt encoding trong response sau khi request body được parse.
D. Đặt character encoding sau khi Servlet đã gọi getParameter.
Đáp án đúng: A

16. ServletContextListener cần khởi tạo tài nguyên trước khi Servlet phục vụ request; callback nào phù hợp?
A. contextDestroyed chạy trước khi context tạo và trước mọi listener khác.
B. sessionCreated chạy trước khi container đọc deployment descriptor.
C. requestInitialized chạy một lần khi web application được deploy.
D. contextInitialized chạy trước init của Filter và Servlet.
Đáp án đúng: D

17. Muốn theo dõi vòng đời session và thay đổi thuộc tính session, nên chọn listener nào?
A. HttpSessionIdListener theo dõi mọi lần thêm/xóa thuộc tính session.
B. HttpSessionAttributeListener theo dõi tạo/hủy; HttpSessionListener theo dõi thuộc tính.
C. HttpSessionListener theo dõi tạo/hủy; HttpSessionAttributeListener theo dõi thuộc tính.
D. ServletRequestListener theo dõi session; ServletContextListener theo dõi thuộc tính.
Đáp án đúng: C

18. Hai request đồng thời sửa một object mutable đang lưu trong HttpSession; giả định nào an toàn?
A. Đồng bộ object mutable; container không khóa object attribute.
B. HttpSession chỉ cho phép một request hoạt động tại một thời điểm.
C. Container khóa toàn bộ session trong suốt mọi request nên không cần đồng bộ.
D. Mỗi request tự nhận một bản sao sâu của mọi session attribute.
Đáp án đúng: A

19. Sau khi xác thực đăng nhập, ứng dụng muốn giảm nguy cơ session fixation mà giữ attribute hiện có; nên làm gì?
A. Giữ nguyên session ID vì xác thực đã chứng minh danh tính người dùng.
B. Gọi HttpServletRequest.changeSessionId để đổi định danh phiên.
C. Tạo session mới cho mọi request tiếp theo mà không chuyển trạng thái.
D. Xóa cookie session ở client nhưng giữ session ID cũ phía server.
Đáp án đúng: B

20. Cấu hình cookie session nào giúp giảm nguy cơ truy cập từ script và gửi qua kênh không an toàn?
A. Bật HttpOnly và Secure, đồng thời chọn SameSite theo luồng sử dụng.
B. Bật Domain rộng và Path / để giới hạn cookie chỉ trên HTTPS.
C. Đặt Max-Age dài và bỏ SameSite để tránh mất phiên đăng nhập.
D. Tắt HttpOnly để script có thể kiểm tra session, bật Secure tùy chọn.
Đáp án đúng: A

21. Client không nhận cookie và ứng dụng bật URL rewriting để duy trì session; rủi ro nào cần lưu ý?
A. URL rewriting chỉ thay đổi đường dẫn hiển thị, không mang session ID.
B. Session ID có thể lộ trong URL, history, referrer và access log.
C. Session ID được mã hóa tự động nên không thể bị ghi vào log.
D. Container sẽ từ chối mọi request có session ID trong URL.
Đáp án đúng: B

22. HttpSession.setMaxInactiveInterval(900) biểu thị điều gì?
A. Session hết hạn đúng 900 giây sau khi được tạo, bất kể hoạt động.
B. Session chỉ tồn tại tối đa 900 request trước khi bị hủy.
C. Session hết hạn sau 900 giây không có request nào truy cập session.
D. Session hết hạn sau 900 phút tính từ lần đăng nhập đầu tiên.
Đáp án đúng: C

23. Ứng dụng dùng sticky session trên load balancer nhưng người dùng mất phiên khi node hỏng; cần bổ sung gì?
A. Tăng thời gian sticky cookie để client quay lại node đã hỏng.
B. Tăng số thread trên mỗi node để giữ session trong bộ nhớ lâu hơn.
C. Session replication hoặc shared session store để chịu lỗi node.
D. Chỉ tăng timeout của session để load balancer tự khôi phục trạng thái.
Đáp án đúng: C

24. Servlet gọi startAsync nhưng một Filter trong chain không hỗ trợ async; kết quả nào có thể xảy ra?
A. Async processing không được hỗ trợ cho chain và startAsync có thể thất bại.
B. Filter tự động được chạy trên thread riêng mà không cần cấu hình.
C. Container tự bỏ qua Filter đó rồi tiếp tục async processing.
D. AsyncContext được tạo nhưng response tự complete ngay lập tức.
Đáp án đúng: A

25. AsyncContext.dispatch và AsyncContext.complete khác nhau thế nào?
A. Cả hai đều tạo request HTTP mới từ trình duyệt tới container.
B. dispatch đóng response ngay; complete chuyển request sang Servlet khác.
C. complete chỉ flush buffer; dispatch hủy toàn bộ request hiện tại.
D. dispatch chạy tiếp tại đích; complete kết thúc async cycle.
Đáp án đúng: D

26. Ứng dụng bắt đầu một async cycle mới sau dispatch và cần AsyncListener tiếp tục nhận callback; nên làm gì?
A. Đăng ký lại listener trong onStartAsync cho async cycle mới.
B. Tạo listener mới sau onComplete của cycle trước.
C. Đăng ký listener trong contextDestroyed để nhận callback tiếp theo.
D. Giữ listener cũ vì container tự đăng ký lại qua mọi async cycle.
Đáp án đúng: A

27. Trong async mode, Servlet cần đọc dữ liệu không chặn trên connection chậm; API nào phù hợp?
A. Dùng RequestDispatcher.include để đọc dữ liệu theo từng chunk.
B. Dùng HttpSessionListener để nhận byte mới từ socket.
C. Dùng ReadListener và isReady trên ServletInputStream.
D. Gọi read blocking trong vòng lặp trên thread xử lý request.
Đáp án đúng: C

28. Nhiều request đồng bộ chờ dịch vụ ngoài chậm làm cạn thread pool container; biện pháp nào phù hợp?
A. Tạo thread mới cho mỗi lần gọi dịch vụ và không cần timeout.
B. Tăng session timeout để giải phóng thread đang chờ I/O.
C. Dùng AsyncContext khi chờ I/O, đặt timeout và giới hạn worker xử lý tiếp.
D. Tăng thread vô hạn để mọi request luôn có worker riêng.
Đáp án đúng: C

29. Filter đặt user vào ThreadLocal nhưng không dọn khi request kết thúc; rủi ro nào xuất hiện?
A. Container tạo thread mới sau mỗi request nên không thể rò rỉ.
B. Dọn ThreadLocal trong finally trước khi thread được tái sử dụng.
C. Giá trị ThreadLocal chỉ tồn tại trong ServletContext của ứng dụng.
D. ThreadLocal tự xóa khi response commit và không thể giữ reference.
Đáp án đúng: B

30. Sau nhiều lần redeploy, classloader cũ vẫn còn trong heap; nguyên nhân nào nên kiểm tra?
A. ThreadLocal, static reference hoặc thread nền giữ classloader cũ.
B. Cookie session hết hạn chậm làm JVM giữ mọi class đã tải.
C. URL mapping chính xác khiến container không giải phóng class metadata.
D. Welcome file được cache trong browser và giữ classloader của server.
Đáp án đúng: A

31. Khi web application bị undeploy, nơi nào phù hợp để đóng executor và pool do ứng dụng tạo?
A. Filter.doFilter sau mỗi request để đóng pool toàn ứng dụng.
B. Servlet.init cho từng request để giải phóng tài nguyên dùng chung.
C. HttpSessionListener.sessionDestroyed vì mọi session hủy cùng lúc.
D. Đóng executor và pool trong ServletContextListener.contextDestroyed.
Đáp án đúng: D

32. Ứng dụng nhận upload multipart; cấu hình nào cho phép Servlet truy cập Part và giới hạn kích thước?
A. Khai báo multipart-config hoặc @MultipartConfig với các giới hạn phù hợp.
B. Chỉ cần gọi getInputStream; container tự áp dụng giới hạn upload mặc định.
C. Bật async-supported và container tự phân tích mọi body thành Part.
D. Đặt welcome-file-list để request body được chuyển thành file upload.
Đáp án đúng: A

33. Filter cần xử lý cả request gốc lẫn error dispatch tới trang lỗi; mapping nào cần có?
A. Dispatcher ASYNC tự nhận mọi error dispatch khi request timeout.
B. Container gọi Filter cho ERROR dù mapping chỉ ghi REQUEST.
C. Dispatcher INCLUDE tự chạy khi container chuyển tới trang lỗi.
D. Khai báo dispatcher type REQUEST và ERROR cho Filter.
Đáp án đúng: D

34. Ứng dụng muốn container áp dụng xác thực và role constraint khai báo trong web.xml; cơ chế nào phù hợp?
A. Khai báo security-constraint cùng auth-constraint và role mapping.
B. Đặt welcome-file cho từng role để container tự xác thực người dùng.
C. Dùng session timeout làm chính sách phân quyền theo từng URL.
D. Khai báo error-page cho URL nhạy cảm để thay thế kiểm tra quyền.
Đáp án đúng: A

35. Browser gửi CORS preflight OPTIONS nhưng Filter yêu cầu session trước khi trả CORS headers; cách xử lý nào phù hợp?
A. Cho phép mọi origin và mọi header để preflight không bị chặn.
B. Chuyển OPTIONS thành POST để browser gửi credential trước.
C. Tắt CORS ở browser bằng cách trả Access-Control-Allow-Origin wildcard.
D. Trả CORS preflight theo policy mà không đòi session; request thực tế vẫn xác thực.
Đáp án đúng: D

36. Filter và Spring MVC HandlerInterceptor khác nhau chủ yếu ở ranh giới nào?
A. Cả hai chỉ chạy sau khi controller đã chọn handler và tạo response.
B. HandlerInterceptor chạy trước Filter của container và có thể chặn request trước mọi Servlet.
C. Filter chỉ chạy sau controller; HandlerInterceptor phục vụ static resource.
D. Filter bao quanh Servlet; HandlerInterceptor chạy trong Spring MVC handler chain.
Đáp án đúng: D

37. Một ứng dụng map Servlet vào / và cần phục vụ CSS/ảnh tĩnh; cần chú ý điều gì?
A. Mapping / luôn để default servlet xử lý file tĩnh trước mọi mapping khác.
B. Mapping / có thể thay default servlet; cần cấu hình resource handler phù hợp.
C. Mapping / chỉ ảnh hưởng POST nên GET static resource không đổi.
D. Mapping / tự động chuyển mọi static file qua welcome-file list.
Đáp án đúng: B

38. Khi Servlet gọi RequestDispatcher.forward thay vì redirect, hành vi nào đúng?
A. forward chuyển nội bộ cùng request; redirect tạo request mới.
B. Container mở kết nối TCP mới từ browser tới cùng Servlet.
C. Container gửi redirect 302, browser tạo request mới và không giữ nguyên request body.
D. Container chuyển request thành INCLUDE và nối thêm response cũ.
Đáp án đúng: A

39. Spring MVC DispatcherServlet tham gia xử lý request như thế nào?
A. Là Listener nhận request trước khi container chọn context path.
B. Container gọi DispatcherServlet như Servlet; nó điều phối tới handler.
C. DispatcherServlet là Filter chạy trước mọi mapping của Servlet.
D. Là thread pool độc lập thay thế connector và Servlet lifecycle.
Đáp án đúng: B
