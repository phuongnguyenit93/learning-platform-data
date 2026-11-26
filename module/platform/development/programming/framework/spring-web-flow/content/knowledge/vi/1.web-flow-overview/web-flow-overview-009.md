# Điều kiện phù hợp và giới hạn của mô hình flow phía máy chủ

Trong chương **Bản đồ Web Flow**, câu hỏi quan trọng không phải là ứng dụng có thể dùng Spring Web Flow hay không, mà là hành trình người dùng có đủ phức tạp để cần một mô hình điều khiển luồng riêng hay không. Spring Web Flow (SWF) mô tả một hành trình web bằng các trạng thái, sự kiện và chuyển tiếp. Cách tổ chức này giúp gom quy tắc điều hướng của một quy trình nhiều bước vào một định nghĩa flow có thể đọc, kiểm thử và bảo trì.

`SPRING_WEB_FLOW` tập trung vào việc mô hình hóa những hành trình web nhiều bước qua state, event, transition và subflow; xử lý form binding, validation, scope và phiên; tích hợp với Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Mô hình này có giá trị khi các khái niệm đó phản ánh đúng nghiệp vụ. Nếu quy trình chỉ có vài màn hình CRUD độc lập, việc đưa thêm flow engine thường làm ứng dụng phức tạp hơn mức cần thiết.

## 1. Bản chất của flow phía máy chủ

Một flow là một phiên thực thi có điểm bắt đầu, trạng thái hiện tại, dữ liệu đi kèm và quy tắc xác định bước tiếp theo. Người dùng gửi một sự kiện từ màn hình hiện tại; flow kiểm tra sự kiện đó và chọn transition hợp lệ để chuyển sang trạng thái khác, kết thúc hoặc gọi một subflow.

Ví dụ, hành trình đăng ký dịch vụ có thể gồm:

1. Nhập thông tin cá nhân.
2. Chọn gói dịch vụ.
3. Xem lại thông tin và xác nhận.
4. Hoàn tất hoặc hiển thị kết quả cần xử lý.

Tại bước chọn gói, người dùng có thể quay lại sửa thông tin cá nhân. Tại bước xem lại, họ có thể xác nhận hoặc quay lại thay đổi lựa chọn. Những nhánh này là quy tắc nghiệp vụ của hành trình, không chỉ là các URL dẫn tới những controller riêng lẻ.

Trong mô hình flow phía máy chủ, định nghĩa flow giữ cấu trúc của hành trình; máy chủ quản lý trạng thái thực thi và dữ liệu theo các scope được chọn. Trình duyệt gửi yêu cầu cùng thông tin nhận diện lần thực thi flow. Cách lưu trạng thái cụ thể phụ thuộc cấu hình repository và phiên bản ứng dụng; cấu hình phổ biến dùng repository gắn với HTTP session. Vì vậy, flow có thể phụ thuộc vào vòng đời phiên và cách hệ thống triển khai lưu trữ trạng thái.

## 2. Khi nào nên dùng Spring Web Flow?

Spring Web Flow phù hợp khi phần lớn các nhận định sau đúng với bài toán.

### Hành trình có nhiều bước và có thứ tự nghiệp vụ rõ ràng

Quy trình có nhiều màn hình phụ thuộc vào kết quả của bước trước. Không phải mọi đường đi đều hợp lệ: người dùng cần hoàn thành hoặc vượt qua một bước trước khi đến bước tiếp theo. Có thể có nhánh rẽ, bước quay lại, điều kiện bỏ qua hoặc các điểm kết thúc khác nhau.

Ví dụ: đăng ký tài khoản doanh nghiệp, nộp hồ sơ, đặt dịch vụ có nhiều lựa chọn, quy trình khai báo và xác nhận thông tin. Flow giúp biểu diễn những đường đi này trực tiếp bằng state và transition.

### Điều hướng là một phần quan trọng của nghiệp vụ

Ứng dụng cần kiểm soát rõ sự kiện nào được chấp nhận tại mỗi trạng thái. Chẳng hạn, sự kiện `confirm` chỉ hợp lệ sau khi người dùng đã xem lại thông tin; sự kiện `back` đưa họ về bước chỉnh sửa; một nhánh khác được mở khi họ chọn loại dịch vụ đặc biệt.

Khi các quy tắc này nằm rải rác trong nhiều controller, điều kiện và URL, rất khó nhìn thấy toàn bộ hành trình. Một flow tập trung hóa cấu trúc điều hướng và làm cho các nhánh hợp lệ dễ kiểm tra hơn.

### Dữ liệu cần tồn tại xuyên suốt một lần thực hiện

Các bước có thể cùng sử dụng một đối tượng nghiệp vụ tạm thời, ví dụ `ApplicationDraft` hoặc `BookingDraft`. Flow scope cho phép giữ dữ liệu trong thời gian flow đang chạy; conversation scope có thể chia sẻ dữ liệu giữa flow cha và các subflow trong cùng một conversation. Nhờ đó, ứng dụng không phải truyền mọi trường dữ liệu qua từng URL hoặc tự dựng một cơ chế điều phối riêng.

Điều này chỉ phù hợp với dữ liệu có vòng đời tương ứng với flow. Dữ liệu nhạy cảm, dữ liệu lớn hoặc dữ liệu phải tồn tại lâu dài vẫn cần được quản lý theo chính sách lưu trữ và bảo mật phù hợp.

### Có thể chia quy trình thành các phần tái sử dụng

Một quy trình lớn có thể gọi subflow để xử lý một phần có ranh giới rõ ràng, chẳng hạn xác minh địa chỉ hoặc chọn phương thức thanh toán. Subflow giúp tách trách nhiệm và tái sử dụng hành trình con trong những flow khác nhau.

Chỉ nên tách subflow khi phần quy trình thực sự có ý nghĩa độc lập và có thể mô tả hợp đồng đầu vào, đầu ra rõ ràng. Chia mỗi màn hình thành một subflow sẽ làm luồng tổng thể khó theo dõi.

### Giao diện chủ yếu là các form do máy chủ điều phối

Spring Web Flow kết hợp với Spring MVC phù hợp với ứng dụng render view ở phía máy chủ, nhận dữ liệu form, binding vào model và thực hiện validation trước khi chuyển bước. Mỗi view state có thể gắn với một view và một model; sự kiện từ form quyết định transition tiếp theo.

Nếu những điều kiện này phản ánh đúng kiến trúc và nhu cầu của ứng dụng, SWF có thể làm cho luồng nhiều bước dễ hiểu và dễ kiểm thử hơn.

## 3. Khi nào không nên dùng?

Không phải mọi chuỗi màn hình đều cần một flow. Các trường hợp sau thường có lựa chọn đơn giản hơn.

### CRUD đơn giản hoặc các trang độc lập

Nếu mỗi yêu cầu chỉ đọc, tạo, cập nhật hoặc xóa một tài nguyên và không phụ thuộc vào trạng thái của một hành trình dài, controller Spring MVC cùng service thông thường thường đã đủ. Thêm flow sẽ tạo thêm định nghĩa, trạng thái thực thi và quy tắc vận hành mà nghiệp vụ không cần.

### API REST hoặc dịch vụ stateless

API phục vụ ứng dụng di động, SPA hoặc hệ thống tích hợp thường được thiết kế theo từng request độc lập, tài nguyên và hợp đồng HTTP. Một flow phụ thuộc vào execution state của máy chủ có thể làm API khó mở rộng, khó dùng từ nhiều client và khó giữ tính stateless.

Nếu quy trình nghiệp vụ cần tồn tại giữa nhiều request API, hãy cân nhắc lưu trạng thái nghiệp vụ một cách tường minh trong domain/service layer hoặc dùng một hệ thống điều phối phù hợp với yêu cầu. Không nên buộc API phải mang theo mô hình điều hướng của giao diện web.

### Ứng dụng tương tác chủ yếu ở phía trình duyệt

Với SPA có router, state management và giao diện thay đổi thường xuyên ở client, việc thêm một state machine phía máy chủ có thể tạo ra hai nơi cùng quyết định màn hình hiện tại. Chỉ nên dùng SWF nếu máy chủ thực sự cần kiểm soát thứ tự nghiệp vụ và trạng thái của hành trình; nếu không, router phía client cùng API rõ ràng thường phù hợp hơn.

### Quy trình nền dài hạn hoặc điều phối nhiều hệ thống

Spring Web Flow được thiết kế cho hành trình tương tác web gắn với request và phiên người dùng. Nó không tự thay thế một workflow engine chuyên xử lý công việc nền, lịch chạy, retry dài hạn, hàng đợi, tác vụ con phân tán, phê duyệt kéo dài nhiều ngày hoặc theo dõi quy trình qua nhiều dịch vụ.

Ví dụ, một hồ sơ cần chờ nhiều phòng ban phê duyệt, tiếp tục xử lý dù người dùng đã đóng trình duyệt, hoặc phải tự retry khi một hệ thống ngoài tạm ngừng thường cần mô hình lưu trữ và điều phối bền vững hơn. Có thể dùng SWF cho phần giao diện nhập hồ sơ, nhưng vòng đời xử lý nghiệp vụ dài hạn nên do thành phần phù hợp khác đảm nhiệm.

### Không cần giữ trạng thái hội thoại ở máy chủ

Nếu mỗi bước có thể được xử lý độc lập bằng dữ liệu đã lưu trong hệ thống và không cần nhớ người dùng đang ở đâu trong một lần thực hiện, flow có thể là một lớp trung gian không cần thiết. Hãy đánh giá xem trạng thái flow có mang lại lợi ích nghiệp vụ cụ thể hay chỉ lặp lại trạng thái đã có trong cơ sở dữ liệu.

## 4. Hiểu các thành phần để đánh giá đúng độ phức tạp

| Thành phần | Vai trò | Câu hỏi khi thiết kế |
|---|---|---|
| Flow definition | Khai báo cấu trúc và quy tắc của hành trình | Quy trình bắt đầu, kết thúc và rẽ nhánh ở đâu? |
| State | Đại diện cho một điểm trong quá trình thực thi | Người dùng hoặc hệ thống đang ở bước nào? |
| Event | Tín hiệu gửi tới state hiện tại | Sự kiện nào được phép tại bước này? |
| Transition | Quy tắc chuyển từ state hiện tại sang state tiếp theo | Điều kiện nào phải thỏa mãn trước khi chuyển? |
| Action | Thực hiện một công việc trong quá trình chạy flow | Công việc này có tác dụng phụ hay cần giao dịch riêng không? |
| Subflow | Gọi một flow con như một phần của flow cha | Phần quy trình này có ranh giới và hợp đồng rõ không? |
| Scope | Xác định vòng đời và phạm vi truy cập của dữ liệu | Dữ liệu cần tồn tại đến khi nào và được chia sẻ ở đâu? |
| Flow execution | Một lần thực thi cụ thể của định nghĩa flow | Phiên, nhiều tab và yêu cầu đồng thời được xử lý thế nào? |

Một flow đơn giản thường có view state để hiển thị form, transition để phản hồi sự kiện, action state nếu cần thực hiện công việc không gắn trực tiếp với một view, và end state để kết thúc. Tên và cấu hình state cần diễn đạt được nghiệp vụ, tránh biến flow thành một danh sách kỹ thuật khó hiểu.

Ví dụ rút gọn sau minh họa hành trình đặt chỗ. Cú pháp XML cụ thể và cấu hình namespace cần khớp phiên bản Spring Web Flow mà dự án đang sử dụng.

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.Booking" />

    <view-state id="enterDetails"
                view="booking/details"
                model="booking">
        <transition on="continue" to="review" />
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="back" to="enterDetails" />
        <transition on="confirm" to="complete" />
    </view-state>

    <end-state id="complete" view="booking/confirmation" />
</flow>
```

Trong ví dụ, `enterDetails` nhận dữ liệu cho model `booking`. Khi người dùng gửi sự kiện `continue`, flow chuyển sang `review`. Tại bước xem lại, `back` đưa người dùng về form trước đó, còn `confirm` kết thúc flow. Đây là ví dụ về cấu trúc điều hướng; ứng dụng thực tế vẫn cần cấu hình binding, validation, khởi tạo model, xử lý lỗi và lưu kết quả nghiệp vụ.

## 5. Scope và vòng đời dữ liệu ảnh hưởng đến quyết định kiến trúc

Chọn scope theo thời gian dữ liệu cần tồn tại, không theo sự tiện tay khi viết expression.

| Scope | Vòng đời khái quát | Trường hợp thường gặp |
|---|---|---|
| `requestScope` | Trong một HTTP request | Giá trị tạm chỉ dùng khi xử lý request hiện tại |
| `flashScope` | Chuyển tiếp qua một lần chuyển view hoặc request kế tiếp theo cơ chế flash | Thông báo ngắn sau một hành động |
| `viewScope` | Trong thời gian ở một view state | Dữ liệu phục vụ riêng form hiện tại |
| `flowScope` | Trong suốt một lần thực thi flow | Bản nháp được dùng qua nhiều bước |
| `conversationScope` | Trong conversation chứa flow và các subflow liên quan | Dữ liệu cần chia sẻ giữa flow cha và flow con |

Tên và hành vi chi tiết của scope cần được đối chiếu với phiên bản SWF đang dùng. Dù chọn scope nào, dữ liệu vẫn cần được kiểm tra quyền truy cập ở phía máy chủ. Không coi việc một trường nằm trong flow scope là bằng chứng người dùng được phép đọc hoặc sửa trường đó.

Một số nguyên tắc thiết kế hữu ích:

- Chỉ giữ trong flow dữ liệu cần cho các bước tiếp theo; tránh lưu toàn bộ entity lớn hoặc đối tượng có vòng đời dài.
- Dùng DTO hoặc đối tượng bản nháp để binding form, sau đó kiểm tra và chuyển thành thay đổi nghiệp vụ hợp lệ ở service layer.
- Không dựa vào giá trị do trình duyệt gửi để quyết định giá, quyền sở hữu, trạng thái phê duyệt hoặc quyền hạn. Tải và kiểm tra lại dữ liệu đáng tin cậy ở máy chủ.
- Xác định cách xử lý khi flow hết hạn, người dùng mở nhiều tab hoặc gửi lại một form cũ.
- Tránh đặt tài nguyên không thể serialize hoặc tham chiếu phụ thuộc vào request vào nơi lưu trữ trạng thái có thể được khôi phục ở request khác.

Nếu dữ liệu cần tồn tại sau khi flow kết thúc, hãy lưu nó vào mô hình nghiệp vụ bền vững trước khi kết thúc. Flow scope không phải cơ sở dữ liệu và không nên được dùng làm nơi lưu hồ sơ chính thức.

## 6. Binding và validation phải gắn với ranh giới nghiệp vụ

Binding ánh xạ dữ liệu form vào model của view state. Chỉ cho phép binding những thuộc tính mà người dùng được phép nhập ở bước đó. Một form hiển thị nhiều thuộc tính không có nghĩa tất cả đều được phép cập nhật. Giới hạn binding giúp giảm nguy cơ mass assignment và tránh ghi đè những trường do máy chủ quản lý.

Validation nên diễn ra trước transition tới bước tiếp theo. Khi dữ liệu không hợp lệ, ứng dụng trả lỗi về view hiện tại để người dùng sửa; khi hợp lệ, flow mới tiếp tục. Cần phân biệt:

- **Kiểm tra dữ liệu đầu vào:** trường bắt buộc, định dạng, độ dài và giới hạn giá trị.
- **Kiểm tra nhất quán nghiệp vụ:** ngày kết thúc không trước ngày bắt đầu, lựa chọn còn khả dụng, tổng tiền hợp lệ.
- **Kiểm tra quyền:** người dùng hiện tại có quyền thao tác trên hồ sơ và hành động được yêu cầu hay không.
- **Kiểm tra tại thời điểm ghi:** dữ liệu có thể đã thay đổi sau khi người dùng mở form, nên service layer vẫn phải xác minh lại trước khi lưu.

Validation ở view state cải thiện trải nghiệm nhiều bước, nhưng không thay thế kiểm tra trong service/domain layer. Một request giả mạo hoặc một đường gọi khác vẫn có thể bỏ qua giao diện. Các quy tắc bảo vệ dữ liệu và quyền hạn phải được áp dụng tại ranh giới nghiệp vụ đáng tin cậy.

## 7. Giới hạn vận hành và các tình huống dễ gặp lỗi

Mô hình flow phía máy chủ đem lại trạng thái có cấu trúc, đồng thời tạo ra trách nhiệm vận hành tương ứng.

### Phiên và khả năng mở rộng ngang

Nếu repository lưu execution state trong HTTP session, yêu cầu tiếp theo phải được định tuyến tới nơi có thể khôi phục trạng thái đó. Khi chạy nhiều instance, cần cấu hình session affinity hoặc cơ chế lưu session/repository dùng chung phù hợp. Chỉ thêm nhiều instance ứng dụng không tự động giải quyết việc chia sẻ flow state.

Hãy kiểm tra giới hạn dung lượng session, thời gian hết hạn, khả năng serialize, phục hồi sau restart và hành vi khi một node mất kết nối. Không lưu dữ liệu lớn trong flow chỉ vì nó tiện truy cập.

### Nút Back, Refresh và nhiều tab

Người dùng có thể quay lại trang trước, tải lại trang, mở cùng một flow ở nhiều tab hoặc gửi form đã cũ. Các tình huống này có thể tạo yêu cầu dùng execution key cũ, lặp thao tác hoặc gửi sự kiện không còn hợp lệ với state hiện tại.

Thiết kế cần xác định rõ hành vi mong muốn: hiển thị thông báo flow hết hạn, cho phép bắt đầu lại, từ chối sự kiện cũ hay tải lại dữ liệu mới. Các thao tác có tác dụng phụ như tạo đơn hàng hoặc trừ tiền phải có cơ chế chống xử lý lặp ở tầng nghiệp vụ, chẳng hạn khóa idempotency hoặc ràng buộc duy nhất phù hợp.

### Tác dụng phụ và giao dịch

Không nên thực hiện một tác dụng phụ không thể đảo ngược chỉ vì người dùng vừa đi qua một transition. Người dùng có thể refresh, gửi lại request hoặc gặp lỗi sau khi hệ thống bên ngoài đã nhận lệnh nhưng trước khi flow nhận được kết quả.

Đặt quy tắc ghi dữ liệu trong service layer và thiết kế ranh giới giao dịch rõ ràng. Với thao tác gọi dịch vụ ngoài, cần xác định timeout, retry, tính idempotent và cách đối soát khi kết quả không rõ ràng. Flow điều khiển hành trình giao diện; nó không tự cung cấp giao dịch phân tán.

### Bảo mật

Execution key và URL của flow không phải cơ chế phân quyền. Mỗi hành động vẫn phải kiểm tra danh tính, quyền truy cập tài nguyên và tính hợp lệ của dữ liệu. Cần áp dụng CSRF protection cho form theo cấu hình Spring Security, giới hạn dữ liệu được binding, không đưa bí mật vào URL hoặc log, và xử lý an toàn khi flow hết hạn.

### Phụ thuộc phiên bản và chi phí bảo trì

Spring Web Flow có cấu hình, schema XML, cách tích hợp Spring MVC và API kiểm thử phụ thuộc phiên bản. Khi nâng cấp Spring Framework, Spring MVC hoặc Java, cần kiểm tra ma trận tương thích và tình trạng hỗ trợ của phiên bản SWF đang dùng. Một flow có quá nhiều state, transition hoặc expression cũng khó đọc như một nhóm controller rối rắm.

Giữ flow ở mức mô tả hành trình; chuyển quy tắc tính toán và nghiệp vụ sang service/domain layer. Đặt tên state và event theo ngôn ngữ nghiệp vụ, chia flow khi có ranh giới rõ, và ghi nhận lỗi theo flow id, state id cùng mã tương quan mà không log dữ liệu nhạy cảm.

## 8. So sánh nhanh các lựa chọn

| Nhu cầu chính | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Trang CRUD hoặc endpoint độc lập | Spring MVC controller và service | Ít trạng thái điều hướng, cấu trúc đơn giản |
| API stateless cho nhiều loại client | REST API và domain/service layer | Client không phụ thuộc execution state của giao diện web |
| SPA điều khiển phần lớn điều hướng | Router và state management phía client cùng API | Giao diện có một nơi điều khiển trạng thái màn hình |
| Form web nhiều bước, có nhánh và trạng thái phiên rõ ràng | Spring Web Flow | Flow mô tả trực tiếp state, event và transition |
| Tác vụ nền dài hạn, retry và điều phối nhiều dịch vụ | Workflow/job orchestration phù hợp | Cần lưu trạng thái bền vững và vận hành độc lập với phiên web |

Đây là hướng dẫn chọn kiến trúc, không phải quy tắc tuyệt đối. Một hệ thống có thể dùng Spring Web Flow cho hành trình nhập liệu, Spring MVC cho các trang thông thường, REST API cho tích hợp và một thành phần workflow riêng cho xử lý nền. Ranh giới nên dựa trên vòng đời và trách nhiệm của từng quy trình.

## 9. Quy trình ra quyết định trước khi tạo flow

Trước khi đưa một quy trình vào Spring Web Flow, hãy trả lời lần lượt:

1. **Có một hành trình nghiệp vụ thực sự không?** Liệt kê điểm bắt đầu, các bước, nhánh rẽ và điểm kết thúc. Nếu chỉ là các trang độc lập, dùng controller thông thường.
2. **Máy chủ có cần nhớ trạng thái của lần thực hiện không?** Xác định dữ liệu nào cần tồn tại giữa các bước và vì sao không thể tải lại an toàn từ nguồn dữ liệu nghiệp vụ.
3. **Ai sở hữu điều hướng?** Nếu client và server cùng điều khiển state mà không có hợp đồng rõ, hãy đơn giản hóa trước khi thêm flow.
4. **Flow tồn tại trong bao lâu?** Nếu phải tiếp tục sau nhiều ngày, qua nhiều người xử lý hoặc khi người dùng đã đóng phiên, đánh giá một cơ chế workflow bền vững.
5. **Điều gì xảy ra khi request bị gửi lại hoặc phiên hết hạn?** Xác định hành vi với Back, Refresh, nhiều tab, timeout, node restart và lỗi dịch vụ ngoài.
6. **Dữ liệu nào được binding và xác minh ở đâu?** Giới hạn thuộc tính form, kiểm tra quyền và đặt quy tắc nghiệp vụ quan trọng trong service/domain layer.
7. **Đội ngũ có thể kiểm thử và vận hành flow không?** Cần có kiểm thử các đường đi, log đủ ngữ cảnh, theo dõi lỗi và kế hoạch nâng cấp phiên bản.

Nếu các câu trả lời cho thấy hành trình có nhiều nhánh, cần quản lý trạng thái ở máy chủ và có vòng đời gắn với tương tác web, Spring Web Flow là lựa chọn đáng cân nhắc. Nếu phần lớn câu trả lời xoay quanh CRUD, API stateless hoặc công việc nền dài hạn, hãy chọn cơ chế phù hợp hơn với vòng đời đó.

## 10. Kiểm thử để xác nhận mô hình phù hợp

Một flow dễ đọc trên sơ đồ vẫn có thể sai khi chạy. Bộ kiểm thử nên bao phủ cả đường đi bình thường và những tình huống làm lộ giới hạn của trạng thái phía máy chủ.

- **Đường đi thành công:** khởi tạo flow, nhập dữ liệu, xem lại, xác nhận và kết thúc; xác minh kết quả nghiệp vụ được lưu đúng.
- **Validation thất bại:** gửi dữ liệu sai ở từng bước; xác minh flow ở lại view phù hợp và thông báo lỗi có thể hiển thị.
- **Sự kiện không hợp lệ:** gửi `confirm` khi chưa tới state xem lại; xác minh hành động bị từ chối an toàn.
- **Quay lại và gửi lại:** kiểm tra Back, Refresh, gửi form cũ và gửi lặp một hành động có tác dụng phụ.
- **Scope và subflow:** xác minh dữ liệu cần thiết được giữ đúng vòng đời, dữ liệu của flow con được chia sẻ theo hợp đồng và không rò rỉ sang lần thực thi khác.
- **Phiên và lỗi:** kiểm tra flow hết hạn, session mất, repository không khôi phục được state và dịch vụ ngoài timeout.
- **Quyền truy cập:** thử truy cập hồ sơ của người dùng khác và gửi các trường form không được phép thay đổi.

Spring Web Flow cung cấp các cơ chế kiểm thử flow execution; API và lớp hỗ trợ cụ thể thay đổi theo phiên bản. Có thể kiểm thử định nghĩa flow và các transition ở mức tích hợp, đồng thời kiểm thử service/domain độc lập để bảo đảm quy tắc nghiệp vụ không bị khóa vào engine điều hướng.

## Kết luận

Spring Web Flow phù hợp nhất với hành trình web nhiều bước có trạng thái, nhánh điều hướng và vòng đời gắn với một lần tương tác của người dùng. Nó giúp biểu diễn rõ state, event, transition và subflow, đồng thời hỗ trợ tổ chức binding, validation và dữ liệu theo scope. Đổi lại, ứng dụng phải quản lý execution state, phiên, khả năng mở rộng, yêu cầu cũ, tác dụng phụ và tương thích phiên bản.

Quyết định sử dụng SWF nên xuất phát từ cấu trúc và vòng đời nghiệp vụ. Khi flow làm cho quy trình dễ hiểu, dễ kiểm thử và có ranh giới rõ, nó là một công cụ phù hợp. Khi nó chỉ bọc các trang CRUD, API stateless hoặc công việc nền kéo dài, chi phí trạng thái và vận hành có thể lớn hơn lợi ích.
