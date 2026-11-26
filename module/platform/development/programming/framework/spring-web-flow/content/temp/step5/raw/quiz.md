Câu 01. Spring Web Flow phù hợp nhất với loại tương tác web nào?
A. Cấu hình interceptor chung cho từng handler method trong MVC
B. Định tuyến HTTP theo URL template mà không cần trạng thái
C. REST endpoint độc lập không lưu trạng thái giữa các request
D. Điều phối hành trình nhiều bước qua state, event và transition
Đáp án đúng: D

Câu 02. Trong Spring Web Flow, thành phần nào đăng ký và tra cứu các định nghĩa flow theo ID?
A. `FlowExecutionRepository` lưu execution state đang chạy
B. `FlowDefinitionRegistry` tra cứu definitions theo flow ID
C. `FlowExecutor` thực thi một flow theo các event nhận được
D. `FlowHandlerAdapter` xử lý HTTP request cho flow trong MVC
Đáp án đúng: B

Câu 03. Component nào bắt đầu và tiếp tục chạy một flow execution trong runtime?
A. `FlowDefinitionRegistry` đăng ký các tài liệu XML định nghĩa flow
B. `FlowHandlerMapping` chọn flow ứng với request MVC hiện tại
C. `FlowExecutor` điều khiển việc launch và resume flow execution
D. `FlowBuilderServices` cung cấp hạ tầng expression cho builder
Đáp án đúng: C

Câu 04. Khi tích hợp Spring Web Flow với Spring MVC, thành phần nào ánh xạ URL tới flow handler?
A. `FlowExecutor` giữ state machine của flow đang chạy
B. `ViewResolver` ánh xạ view name sang template để render
C. `FlowHandlerAdapter` thực hiện flow sau bước chọn handler
D. `FlowHandlerMapping` tìm handler cho flow từ URL MVC
Đáp án đúng: D

Câu 05. Trong Spring MVC, thành phần nào thực thi request đã được map tới flow handler?
A. `ViewResolver` chọn trang hiển thị cho response MVC
B. `FlowHandlerAdapter` nối Spring MVC với engine Web Flow
C. `FlowHandlerMapping` chỉ tìm flow handler cho request
D. `SimpleUrlHandlerMapping` điều hướng request tới controller
Đáp án đúng: B

Câu 06. Trong XML định nghĩa flow, thuộc tính nào có thể chỉ rõ state khởi đầu?
A. `default-transition` chỉ định event đầu khi flow chạy
B. `active-state` chỉ định state phải khôi phục từ session
C. `next-state` chỉ định nơi resume từng flow execution
D. `start-state` chỉ định ID của state đầu trong flow
Đáp án đúng: D

Câu 07. State nào thường hiển thị trang và chờ sự kiện từ người dùng để chuyển bước?
A. `decision-state` rẽ nhánh dựa trên expression test
B. `end-state` chấm dứt flow theo outcome đã định
C. `view-state` render view và dừng chờ user event
D. `action-state` chạy expression rồi phát event kết quả
Đáp án đúng: C

Câu 08. Trong Spring Web Flow, `action-state` thường dùng để làm gì?
A. Gọi action nghiệp vụ rồi chuyển state theo outcome trả về
B. Hoàn tất toàn bộ flow ngay khi được truy cập qua URL
C. Render form và chờ người dùng gửi sự kiện từ browser
D. Khởi tạo một flow mới như child flow của phiên hiện tại
Đáp án đúng: A

Câu 09. Khi cần rẽ nhánh theo điều kiện như còn hàng hay hết hàng, state nào phù hợp?
A. `decision-state` chọn nhánh dựa trên phép kiểm điều kiện
B. `view-state` chọn nhánh chỉ bằng cách render một template
C. `subflow-state` chọn nhánh qua việc mở một flow con
D. `end-state` chọn nhánh mà vẫn tiếp tục flow hiện tại
Đáp án đúng: A

Câu 10. State nào kết thúc flow execution và trả về outcome cuối của luồng?
A. `action-state` chạy logic rồi có thể chuyển tới state khác
B. `decision-state` rẽ nhánh mà chưa kết thúc execution
C. `end-state` kết thúc execution và xác định flow outcome
D. `view-state` chờ user event trong cùng flow execution
Đáp án đúng: C

Câu 11. Trong một `view-state`, ý nghĩa của `<transition on="next" to="review"/>` là gì?
A. Transition chỉ đổi tên view mà không thay current state
B. Event `review` chuyển từ view hiện tại sang state `next`
C. Nhận event `next` và chuyển từ view hiện tại tới state `review`
D. State `next` tự kích hoạt event `review` ngay khi render
Đáp án đúng: C

Câu 12. Khi định nghĩa một flow có nhiều transition, event thường được chọn theo thông tin nào?
A. Tên bean của `FlowDefinitionRegistry` ở application context
B. ID sự kiện mà current state nhận từ request hoặc action
C. Tên file XML nơi đặt flow definition cần chạy
D. Tên SessionRepository đang giữ HttpSession của client
Đáp án đúng: B

Câu 13. Trong XML của Spring Web Flow, hook nào chạy logic khi execution mới bắt đầu?
A. `<on-exit>` khai báo action khi rời state hiện tại
B. `<on-end>` khai báo các action khi flow kết thúc
C. `<on-start>` khai báo các action lúc flow launch
D. `<on-entry>` khai báo các action mỗi lần vào state
Đáp án đúng: C

Câu 14. Nếu muốn tải dữ liệu mỗi lần bước `review` được vào, vị trí khai báo action nào phù hợp?
A. `<on-exit>` trong state `review` thực thi trước lúc rời
B. `<on-start>` ở root flow chỉ thực thi khi tạo execution
C. `<on-entry>` trong state `review` thực thi khi vào state
D. `<on-end>` ở root flow thực thi khi execution đã kết thúc
Đáp án đúng: C

Câu 15. Khi cần chạy cleanup lúc rời một state để tới state khác, hook nào phù hợp?
A. `<on-exit>` của state chạy trước khi rời state đó
B. `<on-entry>` của state chạy sau khi vừa tới state đó
C. `<on-start>` của flow chạy lúc execution được tạo
D. `<on-render>` của view chạy trước khi hiện view
Đáp án đúng: A

Câu 16. Trong flow XML, phần tử nào gọi phương thức bean làm expression action?
A. `<view-state id="load"/>` gọi bean method qua state ID
B. `<end-state id="load"/>` gọi bean method theo outcome
C. `<transition on="load" to="next"/>` gọi bean method trực tiếp
D. `<evaluate expression="service.load()"/>` gọi bean method và lấy kết quả
Đáp án đúng: D

Câu 17. Khi action trong `action-state` trả về outcome `success`, flow thường xử lý tiếp thế nào?
A. Kết thúc flow khi outcome không phải ID của view hiện tại
B. Chọn transition có `on="success"` để đi tới target state
C. Tìm `view-state` tên `success` bất kể transition định nghĩa
D. Tạo SessionRepository mới rồi chạy lại toàn bộ flow
Đáp án đúng: B

Câu 18. Khi form gửi `_eventId=confirm` trong flow đang chờ, giá trị đó chủ yếu dùng để làm gì?
A. Nhận event `confirm` và chọn transition từ state đang chờ
B. Tra cứu flow definition có ID `confirm` trong registry
C. Đặt lại execution key thành `confirm` và render form
D. Đổi HTTP session ID sang `confirm` sau khi validate
Đáp án đúng: A

Câu 19. Với HTML submit button đặt name `_eventId_cancel`, Spring Web Flow có thể suy ra event nào?
A. Event `submit` bất kể tên nút nào được nhấn
B. Event `cancel` khi nút tương ứng được submit
C. Event `cancelled` do framework tự thêm hậu tố
D. Event `_eventId_cancel` gồm toàn bộ tên parameter
Đáp án đúng: B

Câu 20. URL tiếp tục một flow execution trong Spring Web Flow 2 thường mang query parameter nào?
A. `repositoryId` chứa mã flow execution trong session
B. `flowId` chứa flow execution key của phiên đang chạy
C. `execution` chứa key của flow execution đang mở
D. `_eventId` chứa key định danh conversation hiện tại
Đáp án đúng: C

Câu 21. Dữ liệu cần giữ qua nhiều state trong cùng một flow nên đặt ở scope nào?
A. `requestScope` giữ dữ liệu qua nhiều request của flow
B. `viewScope` giữ dữ liệu qua nhiều state của root flow
C. `flashScope` giữ dữ liệu qua nhiều phiên đăng nhập
D. `flowScope` giữ dữ liệu qua các state thuộc cùng flow
Đáp án đúng: D

Câu 22. Dữ liệu chỉ cần trong lúc còn ở một `view-state` nên dùng scope nào?
A. `conversationScope` tự xóa dữ liệu khi user gửi một event
B. `viewScope` chỉ tồn tại khi current view-state còn active
C. `requestScope` tồn tại đến khi flow execution kết thúc
D. `flowScope` tự xóa dữ liệu mỗi lần view được render lại
Đáp án đúng: B

Câu 23. Một giá trị chỉ có ích trong một HTTP request xử lý flow nên nằm ở scope nào?
A. `requestScope` giới hạn dữ liệu vào request hiện hành
B. `viewScope` giới hạn dữ liệu vào request hiện hành
C. `flowScope` giới hạn dữ liệu vào request hiện hành
D. `conversationScope` giới hạn dữ liệu vào request hiện hành
Đáp án đúng: A

Câu 24. Muốn truyền thông báo ngắn cho lần render kế tiếp sau transition, scope nào phù hợp?
A. `flashScope` giữ dữ liệu tạm để trình bày ở bước kế
B. `conversationScope` dùng cho kết quả tồn tại toàn hội thoại
C. `flowScope` giữ dữ liệu tới khi root flow thực sự kết thúc
D. `requestScope` tự duy trì qua redirect sang HTTP request mới
Đáp án đúng: A

Câu 25. Một parent flow và các subflow cần chia sẻ một thông tin xuyên suốt hội thoại; scope nào phù hợp?
A. `viewScope` chia sẻ dữ liệu qua toàn bộ parent/subflow tree
B. `flashScope` chia sẻ dữ liệu ổn định tới cuối phiên người dùng
C. `requestScope` chia sẻ dữ liệu qua các flow execution khác nhau
D. `conversationScope` dùng chung giữa root và subflow
Đáp án đúng: D

Câu 26. Khi bước thanh toán muốn gọi một quy trình chọn địa chỉ tái sử dụng, loại state nào phù hợp?
A. `view-state` khởi chạy flow con theo view resolver
B. `subflow-state` khởi chạy flow con từ parent flow
C. `decision-state` khởi chạy flow con dựa trên guard
D. `end-state` khởi chạy flow con sau khi kết thúc parent
Đáp án đúng: B

Câu 27. Khi subflow kết thúc qua `<end-state id="addressSaved"/>`, parent thường nhận thông tin gì?
A. Outcome `addressSaved` kích hoạt transition tương ứng ở parent
B. Flow execution key mới để tiếp tục từ state ID trùng tên
C. Event `_eventId_addressSaved` gửi lại bởi browser của parent
D. Tên session cookie mới để thay parent conversation ID
Đáp án đúng: A

Câu 28. Để truyền ID khách hàng từ parent flow sang subflow, kỹ thuật nào đúng?
A. Khai báo input mapping từ parent vào subflow để truyền ID khách hàng
B. Đặt giá trị vào tên transition rồi tự parse tên state tiếp theo
C. Dùng view resolver để inject ID vào XML definition lúc runtime
D. Đặt ID trong servlet thread-local và bỏ input mapping của flow
Đáp án đúng: A

Câu 29. Để đưa kết quả nghiệp vụ từ subflow về parent, phần nào trong định nghĩa subflow hữu ích?
A. `<transition>` chỉ đổi màn hình, không hỗ trợ output mapping
B. `<on-entry>` của parent tự đổi dữ liệu trả về thành HTTP header
C. `<output>` định nghĩa giá trị trả về khi subflow kết thúc
D. `<view-state>` của parent tự đọc toàn bộ biến private trong child
Đáp án đúng: C

Câu 30. Trong `view-state`, thuộc tính `model="booking"` cho phép framework hỗ trợ gì?
A. Bind giá trị form vào model `booking` khi xử lý event
B. Chỉ định URL của flow định nghĩa `booking` cho registry
C. Chỉ định SessionRepository có tên `booking` để lưu flow
D. Chỉ định view resolver sẽ lưu HTML vào database booking
Đáp án đúng: A

Câu 31. Trong Spring Web Flow XML, `<var name="booking" class="..."/>` thường có tác dụng gì?
A. Đăng ký REST route `/booking` tới URL của ứng dụng
B. Thay thế HttpSession ID bằng tên biến `booking` của request
C. Tạo một Spring MVC controller bean có request mapping booking
D. Khai báo đối tượng biến dùng trong flow cho model/binding
Đáp án đúng: D

Câu 32. Muốn giới hạn những property được phép bind từ request vào model, nên dùng cấu hình nào?
A. `<end-state>` với output attributes thay cho binder
B. `<transition>` với các property name được phép bind
C. `<binder>` với các `<binding property="..."/>` được phép
D. `<on-start>` với danh sách property name để Spring validate
Đáp án đúng: C

Câu 33. Khi submit `view-state` có model binding nhưng validation không đạt, hành vi nào hợp lý?
A. Chuyển tới end-state dù model vi phạm validation constraints
B. Xóa cả conversationScope trước khi user sửa các lỗi binding
C. Bỏ qua validation để chuyển sang transition đích
D. Ở lại view và hiển thị các messages báo lỗi validation
Đáp án đúng: D

Câu 34. Muốn transition `cancel` khỏi form mà không chạy validation thông thường, tùy chọn nào phù hợp?
A. Đặt `on="cancel"` ở end-state để vô hiệu hóa toàn bộ binding
B. `validate="false"` trong transition `cancel` của view-state
C. Đặt `start-state="cancel"` để validation tự không chạy
D. Đặt `model="false"` trên flow definition để bỏ validation
Đáp án đúng: B

Câu 35. Khi validation của model sinh lỗi, abstraction nào có thể tích lũy messages trong flow execution?
A. `FlowHandlerMapping` thu thập lỗi form rồi tạo HTML
B. `FlowDefinitionRegistry` thu thập messages của validation
C. `FlowExecutionRepository` thu thập lỗi binding cho từng field
D. `MessageContext` thu thập messages để view hiển thị
Đáp án đúng: D

Câu 36. Vì sao flow execution cần một key khi gửi response ở state chờ người dùng?
A. Key thay thế dữ liệu form cần bind vào model
B. Key là ID cố định của một flow definition trong registry
C. Key chỉ là session cookie mã hóa do view-state phát hành
D. Key định vị execution đã tạm dừng ở request sau
Đáp án đúng: D

Câu 37. Nếu user gửi lại link mang execution key đã hết hạn hoặc bị xóa, app nên làm gì?
A. Cho phép bỏ qua validation và tới end-state nếu có cookie
B. Báo không phục hồi được execution và đề nghị khởi tạo flow mới
C. Dùng outcome từ tab khác để tiếp tục execution không tồn tại
D. Tái tạo lặng lẽ state cũ từ tham số browser gửi đến
Đáp án đúng: B

Câu 38. Với nhiều tab dùng cùng một flow execution, rủi ro nào cần kiểm tra?
A. Dữ liệu flowScope tự tách đôi giữa các tab dùng cùng key
B. Mỗi tab tự có flow ID mới dù chia sẻ một execution key
C. Key cũ hoặc event đồng thời có thể gây lệch state
D. FlowRegistry sẽ tự khóa request cùng tên user
Đáp án đúng: C

Câu 39. Để quan sát các mốc start, resume và end trong flow runtime, extension point nào phù hợp?
A. `FlowExecutionListener` theo dõi lifecycle của execution
B. `FlowHandlerMapping` phát event cho lifecycle listener
C. `ViewResolver` nhận các callbacks của flow execution
D. `SessionRepository` phát callback start/resume từ XML flow
Đáp án đúng: A

Câu 40. Khi unit test một XML flow, thao tác nào đánh giá đúng việc chuyển state?
A. Chỉ kiểm HTTP status 200 cho từng controller được khai báo
B. Start flow, gửi từng event rồi assert current state hoặc end outcome
C. Chỉ kiểm flow registry có ID mà không gửi event chuyển state
D. Chỉ so tên file XML với tên template mà không chạy flow
Đáp án đúng: B
