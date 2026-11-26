# Phân biệt lỗi bên trong flow với lỗi khôi phục execution

## 1. Hai thời điểm lỗi khác nhau

Trong Spring Web Flow, một request có thể thất bại ở hai giai đoạn rất khác nhau:

1. **Flow execution đã được tìm thấy và đang chạy:** Web Flow đã xác định được flow execution, khôi phục được state hiện tại và bắt đầu xử lý event. Lỗi có thể phát sinh khi binding form, validation, chạy action, gọi service, thực hiện transition hoặc render view.
2. **Flow execution chưa thể được khôi phục:** request mang execution key hoặc continuation nhưng repository không thể tìm, đọc hoặc tái tạo execution tương ứng. Flow chưa có một state runtime đáng tin cậy để tiếp tục.

Hai nhóm lỗi này cần được xử lý ở hai ranh giới khác nhau. Khi execution đang hoạt động, flow có thể đưa người dùng sang state xử lý lỗi, giữ họ ở view-state để sửa dữ liệu hoặc kết thúc một nhánh nghiệp vụ. Khi không thể khôi phục execution, không có state hiện tại để thực hiện transition; ứng dụng phải xử lý ở tầng tiếp nhận request và quyết định có thể bắt đầu một execution mới hay cần yêu cầu người dùng bắt đầu lại.

Bài học này thuộc chương **Ngoại lệ và phục hồi** của module **SPRING_WEB_FLOW**. Trong một ứng dụng mô hình hóa hành trình nhiều bước bằng state, event, transition và subflow, phân biệt đúng thời điểm lỗi giúp chọn cơ chế phục hồi phù hợp, tránh chuyển nhầm lỗi hạ tầng thành lỗi biểu mẫu và tránh tiếp tục một hành trình với trạng thái không còn đáng tin cậy.

## 2. Vòng đời xử lý request và vị trí phát sinh lỗi

Một request tiếp tục flow thường đi qua các bước khái quát sau:

~~~mermaid
flowchart TD
    A["HTTP request đến DispatcherServlet"] --> B["FlowHandlerMapping xác định flow"]
    B --> C["FlowHandlerAdapter gọi FlowExecutor"]
    C --> D["Repository tìm và khôi phục execution"]
    D --> E{"Khôi phục thành công?"}
    E -- "Không" --> F["Lỗi tìm kiếm hoặc khôi phục execution"]
    F --> G["Xử lý ở tầng MVC / flow handler"]
    E -- "Có" --> H["RequestContext và state hiện tại sẵn sàng"]
    H --> I["Xử lý event, binding, action và transition"]
    I --> J{"Xử lý thành công?"}
    J -- "Có" --> K["Render view hoặc trả outcome"]
    J -- "Không" --> L["Lỗi trong flow execution"]
    L --> M["Xử lý tại flow / execution exception handler"]
~~~

Sơ đồ giúp xác định ranh giới quan trọng: lỗi ở bước D xảy ra trước khi flow có thể xử lý event trong state; lỗi ở bước I xảy ra khi execution đã tồn tại và đang được điều phối.

Không phải mọi lỗi HTTP đều thuộc hai nhóm này. Ví dụ, lỗi xác thực người dùng có thể xảy ra trước khi flow được gọi; lỗi template có thể xảy ra trong quá trình render; lỗi mạng tới hệ thống thanh toán có thể phát sinh trong action. Hãy xác định chính xác tầng phát sinh trước khi chọn cách xử lý.

## 3. Lỗi bên trong flow execution

### 3.1. Lỗi binding và validation

Khi người dùng gửi form, Web Flow liên kết dữ liệu request vào model của view-state. Dữ liệu có thể thiếu, sai định dạng hoặc vi phạm ràng buộc.

Phần lớn lỗi validation là **lỗi đầu vào có thể sửa**, không nhất thiết là exception. Binding/validation có thể ghi lỗi vào message context và giữ người dùng ở view-state hiện tại để sửa dữ liệu.

Ví dụ, form đặt chỗ yêu cầu ngày trả phòng phải sau ngày nhận phòng. Nếu người dùng nhập ngày không hợp lệ, ứng dụng nên hiển thị thông báo tại form và giữ lại dữ liệu có thể dùng để sửa. Không nên đưa lỗi này sang trang lỗi hệ thống chung.

Cần phân biệt:

- Lỗi binding: request không thể chuyển thành kiểu dữ liệu hoặc thuộc tính model mong muốn.
- Lỗi validation: dữ liệu có kiểu hợp lệ nhưng vi phạm quy tắc đầu vào.
- Lỗi nghiệp vụ: dữ liệu có thể đúng định dạng nhưng hành động không được phép trong trạng thái hiện tại, ví dụ phòng vừa hết chỗ.

Ba loại lỗi có thể cùng xuất hiện ở một màn hình nhưng cách phản hồi khác nhau.

### 3.2. Lỗi nghiệp vụ được dự kiến

Ví dụ, service kiểm tra tồn kho có thể trả kết quả `notAvailable`, hoặc phát sinh ngoại lệ nghiệp vụ như `InventoryUnavailableException`. Nếu đây là tình huống có thể dự đoán, flow nên có đường xử lý rõ ràng:

- Thông báo mặt hàng hoặc phòng không còn khả dụng.
- Giữ các dữ liệu người dùng đã nhập nếu vẫn hợp lệ.
- Cho phép chọn phương án khác hoặc quay lại bước trước.
- Không đánh dấu đơn hàng đã xác nhận.

Có thể biểu diễn kết quả dự kiến bằng event từ action hoặc bằng exception được ánh xạ sang nhánh xử lý phù hợp. Lựa chọn phụ thuộc cách tổ chức service và quy ước của ứng dụng. Điểm quan trọng là lỗi nghiệp vụ được nhận diện và trở thành kết quả mà flow có thể xử lý có chủ đích.

### 3.3. Lỗi kỹ thuật trong action hoặc service

Một action có thể gọi cơ sở dữ liệu, dịch vụ từ xa, hệ thống thanh toán hoặc API khác. Các lỗi như timeout, mất kết nối, lỗi cấu hình hoặc lỗi lập trình có thể xảy ra trong lúc flow đang chạy.

Nếu lỗi được chuyển thành một kết quả có thể phục hồi, flow có thể đưa người dùng tới state retry hoặc state thông báo. Nếu lỗi không được xử lý trong flow, nó có thể thoát ra dưới dạng lỗi thực thi flow và được xử lý bởi cơ chế exception handler ở cấp execution hoặc tầng tích hợp.

Không nên bắt mọi exception rồi trả về `success`. Cách đó khiến flow tiếp tục dù action chưa hoàn tất, có thể bỏ qua việc lưu dữ liệu hoặc tạo trạng thái nghiệp vụ không nhất quán.

### 3.4. Lỗi transition và định nghĩa flow

Một event có thể không khớp transition nào của state hiện tại. Khi đó, Web Flow không có đường điều hướng phù hợp và có thể phát sinh lỗi như `NoMatchingTransitionException`.

Các nguyên nhân thường gặp:

- View gửi event ID không đúng với flow definition.
- Action trả về event khác tên dự kiến.
- Wildcard hoặc transition tổng quát che transition cụ thể.
- State hiện tại không hỗ trợ event đó.
- Flow definition và code phát event không còn đồng bộ.

Đây là lỗi trong lúc execution đang hoạt động. Cần kiểm tra state hiện tại, event ID và danh sách transition. Nếu event không khớp là trường hợp người dùng có thể gặp hợp lệ, hãy thiết kế nhánh dự phòng. Nếu nó chỉ ra lỗi lập trình hoặc hợp đồng event bị lệch, hãy ghi nhận như lỗi kỹ thuật để sửa.

## 4. Lỗi khôi phục flow execution

### 4.1. Repository không tìm thấy execution

Khi request tiếp tục flow, Web Flow cần dùng thông tin định danh execution để lấy trạng thái từ repository. Execution có thể không còn vì:

- Người dùng đã kết thúc flow trước đó.
- Execution đã hết hạn hoặc bị dọn dẹp.
- HTTP session hết hạn trong cấu hình repository gắn execution với session.
- Người dùng gửi lại một URL cũ hoặc execution key không hợp lệ.
- Server khởi động lại và repository đang dùng không lưu trạng thái qua lần khởi động.

Trong tình huống này, không có state hiện tại để flow xử lý event. Việc thêm transition `on="*"` hoặc một exception transition bên trong flow không giải quyết được, vì flow chưa được khôi phục để xét transition.

Ứng dụng nên phản hồi theo chính sách đã định: thông báo hành trình đã hết hạn, đưa người dùng tới danh sách bản nháp, hoặc cho phép bắt đầu flow mới nếu có dữ liệu nghiệp vụ lưu bền.

### 4.2. Execution tồn tại nhưng không thể đọc hoặc tái tạo

Repository có thể tìm thấy dữ liệu nhưng không thể khôi phục execution. Ví dụ:

- Dữ liệu serialized không còn tương thích với class hoặc phiên bản ứng dụng mới.
- Flow definition đã thay đổi theo cách không tương thích với snapshot cũ.
- Lỗi đọc/ghi ở kho lưu trữ execution.
- Thiếu dependency hoặc cấu hình cần thiết để dựng lại execution.
- Lỗi trong quá trình deserialize hoặc khởi tạo trạng thái runtime.

Một lỗi phục hồi có thể được biểu diễn bằng các exception thuộc nhóm repository/execution, ví dụ `FlowExecutionRestorationFailureException` trong các phiên bản Spring Web Flow có lớp này. Cần xem loại exception và cause thực tế theo phiên bản đang dùng; không nên chỉ dựa vào tên lớp ngoài cùng.

Khi không thể dựng lại state, ứng dụng không thể an toàn giả định event cũ sẽ được xử lý như trước. Cần quyết định có thể khởi tạo execution mới từ bản nháp nghiệp vụ hay phải kết thúc hành trình và yêu cầu thao tác lại.

### 4.3. Xung đột truy cập hoặc repository gặp sự cố

Một số repository có cơ chế khóa hoặc giới hạn truy cập execution để tránh hai request đồng thời làm thay đổi cùng trạng thái. Request đồng thời, khóa không lấy được, lỗi lưu snapshot hoặc kho dữ liệu tạm thời không khả dụng có thể khiến việc tiếp tục thất bại.

Đây là lỗi ở ranh giới lưu/khôi phục execution. Nếu nguyên nhân tạm thời, ứng dụng có thể cho phép thử lại với thông báo rõ ràng. Nếu execution đã bị mất hoặc trạng thái lưu không còn tin cậy, cần phục hồi từ bản nháp nghiệp vụ đã lưu bền thay vì lặp lại request vô hạn.

Không nên coi mọi lỗi repository là “session hết hạn”. Cần phân biệt execution không tồn tại, dữ liệu không tương thích và kho lưu trữ đang gặp sự cố vì hướng xử lý khác nhau.

## 5. So sánh hai nhóm lỗi

| Tiêu chí | Lỗi bên trong flow | Lỗi khôi phục execution |
| --- | --- | --- |
| Thời điểm | Sau khi execution đã được khôi phục | Trước khi execution có thể tiếp tục |
| State hiện tại | Có thể xác định | Chưa có state đáng tin cậy |
| RequestContext | Có trong quá trình xử lý flow | Có thể chưa được tạo đầy đủ cho execution |
| Cơ chế xử lý | Validation, event, transition, exception handler của flow | Repository, FlowExecutor, flow handler hoặc tầng MVC |
| Có thể dùng transition? | Có, nếu execution còn hoạt động và lỗi được chuyển vào flow | Không thể dùng transition của execution chưa khôi phục |
| Ví dụ | Validation lỗi, service ném exception, event không khớp | Execution key hết hạn, session mất, snapshot không deserialize được |
| Phục hồi thường gặp | Giữ form, retry, chọn nhánh thay thế, kết thúc có kiểm soát | Tải bản nháp và tạo execution mới hoặc yêu cầu bắt đầu lại |

Một dấu hiệu chẩn đoán hữu ích là câu hỏi: **Web Flow đã có state hiện tại để xử lý event chưa?** Nếu có, điều tra lỗi trong execution. Nếu chưa, điều tra việc tìm kiếm và khôi phục execution.

## 6. Chọn đúng tầng xử lý

### 6.1. Xử lý lỗi có thể sửa ngay trong view-state

Với binding và validation, giữ người dùng ở form, gắn lỗi vào trường hoặc message context và hiển thị thông báo dễ hiểu. Không cần kết thúc flow chỉ vì người dùng nhập sai.

### 6.2. Xử lý lỗi nghiệp vụ trong flow

Với kết quả nghiệp vụ dự kiến, thiết kế event hoặc exception mapping tới state phù hợp. Ví dụ:

~~~xml
<action-state id="checkAvailability">
    <evaluate expression="bookingService.checkAvailability(draft)"/>
    <transition on="available" to="review"/>
    <transition on="notAvailable" to="chooseAnotherRoom"/>
</action-state>
~~~

Đoạn XML minh họa action trả về event theo hợp đồng của ứng dụng. Nếu service ném exception thay vì trả event, cần cấu hình exception handling tương ứng với loại exception đó. Không nên giả định một exception Java tự động trở thành event `notAvailable`.

Với ngoại lệ cụ thể có thể xử lý trong flow, Web Flow hỗ trợ transition theo exception trong các ngữ cảnh phù hợp. Ví dụ minh họa:

~~~xml
<transition
    on-exception="com.example.booking.InventoryUnavailableException"
    to="chooseAnotherRoom"/>
~~~

Cú pháp và vị trí khai báo phải được xác nhận theo phiên bản Web Flow và loại state đang dùng. Chỉ ánh xạ các exception đã hiểu rõ ý nghĩa nghiệp vụ; không ánh xạ mọi `RuntimeException` vào một state thành công.

### 6.3. Xử lý lỗi khôi phục ở tầng tích hợp

Khi repository không thể trả về execution, không có flow state để hiển thị trang lỗi thông qua transition. Tầng tích hợp Spring MVC hoặc flow handler có thể:

- Ghi nhận loại lỗi và cause.
- Phân biệt execution hết hạn với lỗi repository tạm thời.
- Trả trang thông báo phù hợp hoặc redirect tới danh sách bản nháp.
- Bảo đảm request tiếp theo không tiếp tục dùng execution key đã hỏng.
- Cho phép người dùng bắt đầu flow mới nếu bản nháp còn hợp lệ.

Có thể triển khai qua cấu hình exception handling của ứng dụng MVC, custom flow handler hoặc adapter phù hợp với phiên bản. Hãy đặt xử lý tại nơi thực sự nhận được exception khôi phục; một `@ExceptionHandler` ở controller không nhất thiết bắt được mọi lỗi nếu request đã được `FlowHandlerAdapter` xử lý trước đó.

## 7. Thiết kế phục hồi từ bản nháp nghiệp vụ

Flow execution và bản nháp nghiệp vụ có vòng đời khác nhau. Nếu cần cho phép người dùng tiếp tục sau khi execution cũ không còn, dữ liệu cần thiết phải được lưu bền vững ngoài repository execution.

Một quy trình an toàn:

1. Người dùng mở lại liên kết hoặc chọn bản nháp trong danh sách.
2. Ứng dụng xác thực người dùng.
3. Service tìm bản nháp theo ID và chủ sở hữu.
4. Service kiểm tra trạng thái, thời hạn và quyền tiếp tục.
5. Ứng dụng tạo flow execution mới với input tối thiểu, thường là draft ID.
6. Flow tải dữ liệu hiện tại qua service và xác định state phù hợp từ trạng thái nghiệp vụ.
7. Trước khi xác nhận hoặc thực hiện side effect, service kiểm tra lại version và điều kiện hiện tại.

~~~mermaid
flowchart TD
    A["Request tiếp tục execution cũ"] --> B{"Khôi phục được?"}
    B -- "Có" --> C["Kiểm tra trạng thái nghiệp vụ"]
    B -- "Không" --> D["Hiển thị lựa chọn tiếp tục bản nháp"]
    D --> E["Xác thực và kiểm tra chủ sở hữu"]
    E --> F{"Bản nháp còn hợp lệ?"}
    F -- "Không" --> G["Thông báo hết hạn hoặc không có quyền"]
    F -- "Có" --> H["Tạo execution mới"]
    H --> I["Tải dữ liệu bền vững"]
    C --> J["Tiếp tục hành trình"]
    I --> J
~~~

Không nên cố phục hồi bằng cách tự tạo một flow state từ các tham số URL hoặc dữ liệu form cũ. Những giá trị đó do client kiểm soát và có thể không còn phản ánh trạng thái nghiệp vụ. Hãy tải bản nháp từ nguồn dữ liệu đáng tin cậy.

Nếu flow definition đã thay đổi, có thể lưu `workflowVersion` hoặc `schemaVersion` trong bản nháp. Khi khởi chạy execution mới, service có thể chuyển đổi dữ liệu cũ, yêu cầu người dùng xác nhận lại hoặc từ chối tiếp tục nếu không thể bảo đảm tính đúng đắn.

## 8. Phân loại mức độ phục hồi

Không phải lỗi nào cũng nên retry hoặc bắt đầu lại. Có thể dùng bảng quyết định sau:

| Loại lỗi | Hướng xử lý phù hợp |
| --- | --- |
| Dữ liệu form sai | Hiển thị lỗi và cho sửa |
| Quy tắc nghiệp vụ không thỏa | Chuyển nhánh nghiệp vụ hoặc yêu cầu thay đổi lựa chọn |
| Dịch vụ ngoài timeout tạm thời | Retry có giới hạn, có backoff và idempotency |
| Lỗi lập trình hoặc invariant bị vi phạm | Ghi log, dừng thao tác không an toàn và trả thông báo chung |
| Execution key không còn hợp lệ | Kiểm tra bản nháp và tạo execution mới nếu được phép |
| Snapshot không tương thích | Phục hồi từ bản nháp đã lưu, chuyển đổi version hoặc yêu cầu bắt đầu lại |
| Repository tạm thời không khả dụng | Thông báo lỗi tạm thời; không tạo execution trùng khi chưa biết kết quả ghi |
| Người dùng không có quyền với bản nháp | Từ chối truy cập, không tiết lộ dữ liệu |

Retry chỉ phù hợp khi thao tác có thể thực hiện an toàn nhiều lần hoặc đã có idempotency key. Không retry vô hạn các lỗi không thể phục hồi như execution đã bị xóa hoặc snapshot không còn tương thích.

## 9. Transaction và side effect khi flow gặp lỗi

Một lỗi có thể xảy ra sau khi service đã thực hiện một phần công việc. Ví dụ, hệ thống đã tạo yêu cầu thanh toán nhưng response bị timeout trước khi flow nhận được kết quả. Nếu người dùng bấm lại, ứng dụng có thể tạo yêu cầu thứ hai.

Để tránh trạng thái không nhất quán:

- Giữ transaction cơ sở dữ liệu ngắn trong từng lần gọi service.
- Dùng transaction boundary ở tầng nghiệp vụ, không kéo dài transaction qua thời gian người dùng tương tác.
- Dùng idempotency key cho các thao tác tạo đơn, thanh toán hoặc gửi yêu cầu.
- Ghi nhận trạng thái yêu cầu và kết quả xử lý để có thể truy vấn lại khi response bị mất.
- Dùng outbox hoặc cơ chế retry có kiểm soát khi cần phối hợp database với hệ thống ngoài.
- Chỉ cho flow chuyển sang state hoàn tất sau khi service xác nhận kết quả nghiệp vụ.

Nếu flow execution bị mất sau khi side effect đã hoàn thành, execution mới phải truy vấn trạng thái giao dịch trước khi thực hiện lại. Không dựa vào việc flow cũ chưa đi tới state `completed` để kết luận giao dịch chưa xảy ra.

## 10. Ghi log và quan sát lỗi đúng ranh giới

Để phân biệt hai nhóm lỗi trong môi trường thật, log cần đủ thông tin liên kết request với flow và execution.

Nên ghi:

- Correlation ID hoặc request ID.
- Flow ID và state ID nếu đã khôi phục được.
- Giai đoạn lỗi: mapping, repository lookup, restoration, event processing, action hay view rendering.
- Loại exception và cause gốc.
- Execution key đã được che hoặc rút gọn theo chính sách log.
- Kết quả phục hồi: retry, restart từ draft, redirect hoặc từ chối.

Không ghi toàn bộ flow scope, payload biểu mẫu, access token, session cookie hoặc dữ liệu cá nhân nhạy cảm. Execution key cũng không nên được ghi nguyên dạng nếu nó có thể giúp truy cập trạng thái.

Metric hữu ích có thể gồm số lỗi binding/validation, số lỗi action, số lần không tìm thấy execution, số lỗi restoration, số lần bắt đầu lại từ draft và số lần retry repository. Tách metric theo giai đoạn giúp phát hiện việc session timeout tăng đột biến hoặc repository gặp lỗi mà không nhầm với validation của người dùng.

## 11. Các lỗi chẩn đoán thường gặp

| Triệu chứng | Nhóm lỗi cần kiểm tra | Hướng điều tra |
| --- | --- | --- |
| Form hiển thị lỗi nhưng flow vẫn ở màn hình hiện tại | Binding/validation trong flow | Kiểm tra field error, message context và validator |
| Event hợp lệ nhưng action thất bại | Lỗi trong flow execution | Kiểm tra service, transaction và cause exception |
| Flow báo không có transition phù hợp | Lỗi event/state trong execution | Đối chiếu state hiện tại, event ID và thứ tự transition |
| URL cũ không tiếp tục được sau thời gian dài | Lỗi lookup/restore execution | Kiểm tra execution key, session và chính sách repository |
| Chỉ lỗi sau khi deploy phiên bản mới | Snapshot hoặc flow definition không tương thích | Kiểm tra serialization, schema version và cách triển khai |
| Nhiều request đồng thời làm flow không tiếp tục | Lock hoặc repository concurrency | Kiểm tra request trùng, lock timeout và chính sách truy cập |
| Trang lỗi xuất hiện trước khi view-state được render | Lỗi khôi phục hoặc lỗi ở tầng MVC | Kiểm tra log trước khi tạo RequestContext và exception handler thực sự nhận lỗi |
| Người dùng gửi lại xác nhận sau timeout tạo hai giao dịch | Side effect không idempotent | Kiểm tra idempotency key và trạng thái giao dịch đã lưu |

Khi điều tra, hãy thu thập thời điểm request, flow ID, execution key đã che, state ID nếu có, event ID nếu đã xử lý và exception cause. Đừng suy luận lỗi khôi phục chỉ từ mã HTTP; cùng một mã 4xx hoặc 5xx có thể được trả về bởi nhiều tầng khác nhau.

## 12. Kiểm thử hai nhóm lỗi riêng biệt

Bộ kiểm thử nên chứng minh ứng dụng phản ứng đúng theo giai đoạn lỗi.

### 12.1. Kiểm thử lỗi bên trong flow

- Gửi form không hợp lệ và xác nhận người dùng ở lại view-state.
- Cho validator phát lỗi nghiệp vụ và xác nhận thông báo xuất hiện đúng.
- Cho action trả về event thành công và event thay thế; xác nhận transition tương ứng.
- Cho action ném exception đã ánh xạ và xác nhận flow tới state phục hồi.
- Cho action ném exception không dự kiến và xác nhận lỗi được ghi nhận, không bị biến thành thành công.
- Gửi event không có transition và xác nhận cơ chế xử lý lỗi đúng với thiết kế.

### 12.2. Kiểm thử lỗi khôi phục execution

- Dùng execution key không tồn tại hoặc đã hết hạn.
- Làm session hết hạn khi repository phụ thuộc session.
- Mô phỏng repository không thể đọc snapshot.
- Kiểm tra hành vi khi dữ liệu serialized không tương thích với phiên bản mới.
- Mô phỏng lỗi lock hoặc truy cập đồng thời nếu repository hỗ trợ cơ chế này.
- Xác nhận không có transition trong flow cũ được gọi khi execution chưa khôi phục.
- Xác nhận đường tạo execution mới chỉ hoạt động sau khi kiểm tra bản nháp, chủ sở hữu và thời hạn.

### 12.3. Kiểm thử phục hồi và side effect

- Làm request timeout sau khi service đã tạo giao dịch, sau đó gửi lại cùng idempotency key.
- Xác nhận chỉ có một giao dịch nghiệp vụ.
- Làm execution cũ mất sau khi bản nháp đã được lưu và xác nhận flow mới tải lại dữ liệu đúng.
- Xác nhận bản nháp hết hạn hoặc thuộc người dùng khác không được khôi phục.
- Kiểm tra log có correlation ID và phân loại đúng giai đoạn nhưng không chứa dữ liệu nhạy cảm.

## 13. Quy trình xử lý sự cố trong production

Khi nhận báo cáo flow bị lỗi, hãy đi theo thứ tự:

1. **Xác định request đã tới flow chưa.** Kiểm tra handler mapping và URL.
2. **Kiểm tra repository lookup/restore.** Xem execution có được tìm và khôi phục không.
3. **Nếu khôi phục thành công, xác định state và event.** Tìm lỗi binding, validation, transition hoặc action.
4. **Đọc cause gốc.** Không chỉ dựa vào exception wrapper hoặc thông báo trên màn hình.
5. **Xác định side effect đã xảy ra chưa.** Tra cứu đơn hàng, thanh toán hoặc yêu cầu ngoài bằng ID nghiệp vụ.
6. **Chọn phục hồi.** Sửa form, retry an toàn, chuyển nhánh, tiếp tục execution còn hợp lệ hoặc tạo execution mới từ bản nháp.
7. **Xác nhận quyền và trạng thái.** Không khôi phục dữ liệu chỉ vì client còn giữ execution key hoặc draft ID.
8. **Ghi nhận nguyên nhân và cải thiện test.** Bổ sung ca kiểm thử cho đúng giai đoạn lỗi vừa gặp.

Cách phân loại này tránh hai sai lầm phổ biến: cố dùng transition để xử lý một execution chưa tồn tại, hoặc buộc người dùng bắt đầu lại toàn bộ nghiệp vụ khi bản nháp vẫn còn hợp lệ.

## 14. Tự kiểm tra

- Lỗi validation có luôn là exception không? Không. Thông thường nó được ghi nhận như lỗi binding/validation để người dùng sửa form.
- Khi action trong state đang chạy ném exception, execution đã được khôi phục chưa? Thông thường có; đây là lỗi trong quá trình thực thi flow.
- Khi repository không thể khôi phục execution, flow có thể chạy transition on-exception của state cũ không? Không, vì state đó chưa được tái tạo.
- Execution key hết hạn có đồng nghĩa bản nháp nghiệp vụ bị mất không? Không. Bản nháp có thể còn trong kho dữ liệu bền vững.
- Vì sao cần đọc cause gốc? Exception ngoài có thể chỉ là wrapper cho lỗi repository, deserialize hoặc service thực tế.
- Khi nào nên retry? Khi lỗi có khả năng tạm thời và thao tác có thể lặp an toàn hoặc được bảo vệ bằng idempotency.
- Khi nào nên tạo execution mới? Khi execution cũ không thể khôi phục nhưng bản nháp còn hợp lệ và người dùng có quyền tiếp tục.
- Vì sao không được coi execution key là bằng chứng quyền truy cập? Vì nó chỉ định vị trạng thái flow, không thay thế xác thực và authorization.

Phân biệt lỗi bên trong flow với lỗi khôi phục execution giúp đặt xử lý đúng tầng. Khi flow còn state, hãy xử lý theo ngữ cảnh nghiệp vụ và event; khi execution không thể được khôi phục, hãy kiểm tra repository rồi phục hồi từ dữ liệu nghiệp vụ bền vững nếu được phép. Kết hợp cách phân loại này với transaction ngắn, idempotency, log có cấu trúc và kiểm thử riêng cho từng giai đoạn sẽ giúp hành trình Spring Web Flow an toàn và dễ vận hành hơn.

