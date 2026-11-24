# Phạm vi của Micrometer Metrics, Observation, Tracing và Context Propagation

Micrometer cung cấp các API và cơ chế tích hợp để ứng dụng Java phát ra tín hiệu quan sát được khi chạy. Hệ sinh thái này gồm nhiều phần có nhiệm vụ liên quan nhưng khác nhau: **Metrics** ghi nhận số liệu tổng hợp, **Observation** mô tả vòng đời của một hoạt động, **Tracing** theo dấu một lần thực thi qua nhiều thành phần, còn **Context Propagation** chuyển ngữ cảnh đi cùng công việc khi luồng thực thi thay đổi.

Hiểu đúng ranh giới giữa các phần giúp chọn API phù hợp, tránh tạo dữ liệu trùng lặp và thiết kế instrumentation có thể dùng được cả trong môi trường đồng bộ lẫn bất đồng bộ. Phạm vi của module này là cách đo lường ứng dụng Java bằng Micrometer, tích hợp với Spring Boot, xuất dữ liệu đến hệ thống giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## 1. Bốn khái niệm giải quyết bốn nhu cầu khác nhau

| Thành phần | Câu hỏi chính | Dữ liệu điển hình | Vai trò |
|---|---|---|---|
| Micrometer Metrics | Hệ thống đang hoạt động ở mức nào theo thời gian? | Số lần gọi, số tác vụ đang chạy, thời gian xử lý, kích thước dữ liệu | Thu thập số liệu tổng hợp để quan sát xu hướng, so sánh và đặt cảnh báo |
| Micrometer Observation | Một hoạt động được bắt đầu, diễn ra và kết thúc như thế nào? | Tên hoạt động, thời điểm, trạng thái, lỗi và các key-value gắn với hoạt động | Cung cấp mô hình instrumentation thống nhất và điểm mở rộng cho nhiều loại tín hiệu |
| Micrometer Tracing | Một yêu cầu cụ thể đã đi qua những thành phần nào và mất thời gian ở đâu? | Trace, span, quan hệ cha-con, thuộc tính và thông tin truyền tiếp | Theo dấu đường đi của một lần thực thi, đặc biệt qua ranh giới dịch vụ |
| Micrometer Context Propagation | Ngữ cảnh hiện tại được giữ lại ra sao khi công việc chuyển thread hoặc chuyển sang mô hình reactive? | Trace context, observation context, thông tin gắn với ThreadLocal hoặc Reactor Context | Khôi phục ngữ cảnh đúng tại nơi công việc tiếp tục chạy |

Có thể hình dung một yêu cầu HTTP đi vào ứng dụng, gọi cơ sở dữ liệu rồi gửi thông điệp sang dịch vụ khác. Metrics cho biết trong một phút có bao nhiêu yêu cầu, độ trễ phân vị ra sao và có bao nhiêu lỗi. Observation bao quanh các hoạt động như xử lý HTTP, truy vấn cơ sở dữ liệu hoặc xử lý nghiệp vụ. Tracing liên kết các span để xem một yêu cầu cụ thể đã đi qua những bước nào. Context Propagation giúp trace hoặc observation context vẫn hiện diện khi ứng dụng chuyển từ thread nhận yêu cầu sang executor hay pipeline reactive.

Các phần này phối hợp với nhau nhưng không thay thế lẫn nhau. Một biểu đồ metrics không cho biết chi tiết từng yêu cầu. Một trace không tự cung cấp phép tổng hợp ổn định cho toàn bộ lưu lượng. Context propagation không tự tạo metrics hay span; nó chỉ hỗ trợ chuyển ngữ cảnh mà các cơ chế khác sử dụng.

## 2. Micrometer Metrics: đo lường và tổng hợp

Metrics là các phép đo được ghi nhận theo thời gian. Trong Micrometer, mã ứng dụng tạo meter và đăng ký chúng vào một MeterRegistry. Registry quản lý meter, nhận các lần cập nhật và chuyển dữ liệu đến hệ thống đích thông qua implementation tương ứng.

Các loại meter thường gặp gồm:

- **Counter** đếm số sự kiện tăng dần, chẳng hạn số đơn hàng được tạo hoặc số lần xử lý thất bại.
- **Gauge** quan sát giá trị tại thời điểm đọc, chẳng hạn số phần tử đang nằm trong hàng đợi hoặc số kết nối đang được sử dụng.
- **Timer** đo thời lượng và số lần một hoạt động được thực hiện. Tùy cấu hình registry, timer còn cung cấp phân phối hoặc histogram để phân tích độ trễ.
- **DistributionSummary** ghi nhận phân phối của các giá trị không nhất thiết là thời gian, chẳng hạn kích thước payload hoặc số bản ghi trong một lô.
- **LongTaskTimer** theo dõi những tác vụ có thể chạy lâu và vẫn đang diễn ra.

Một meter thường được xác định bởi tên cùng tập tag. Ví dụ, meter có tên **orders.process** với tag **result=success** là một chuỗi số liệu khác với cùng meter có tag **result=failure**. Thiết kế tên và tag vì thế là một phần của thiết kế dữ liệu vận hành.

~~~java
Timer timer = Timer.builder("orders.process")
    .description("Thời gian xử lý đơn hàng")
    .tag("result", "success")
    .register(meterRegistry);

timer.record(() -> orderService.process(order));
~~~

Đoạn mã trên ghi nhận thời lượng mỗi lần gọi **process**. Trong ứng dụng thực tế, nhãn **result** cần phản ánh kết quả thực tế; nếu thao tác có thể thất bại, nên ghi nhận nhánh thất bại riêng hoặc dùng Observation để các handler thu thập trạng thái một cách nhất quán.

Metrics phù hợp với câu hỏi tổng hợp: lưu lượng tăng hay giảm, độ trễ có vượt ngưỡng không, tỷ lệ lỗi đang thay đổi thế nào, hàng đợi có bị dồn ứ không. Metrics thường được lưu thành chuỗi thời gian và truy vấn bằng hệ thống giám sát. Chúng không nên mang một định danh mới cho từng request hoặc từng người dùng, vì mỗi tổ hợp tag mới có thể tạo thêm một chuỗi thời gian.

### Cardinality là ràng buộc thiết kế

Cardinality là số lượng tổ hợp giá trị tag khác nhau của một meter. Tag như **method=GET**, **result=success** hoặc **region=ap-southeast** thường có tập giá trị hữu hạn và dễ kiểm soát. Tag như **user.id**, **order.id**, request ID, địa chỉ URL chứa ID thực hoặc thông điệp lỗi tùy biến có thể sinh ra số lượng giá trị rất lớn.

Nếu mỗi request tạo một tổ hợp tag riêng, lượng chuỗi thời gian sẽ tăng nhanh, làm tăng chi phí lưu trữ và truy vấn, đồng thời khiến dashboard khó đọc. Vì vậy:

- Dùng giá trị hữu hạn như loại thao tác, phương thức HTTP, trạng thái hoặc nhóm kết quả.
- Dùng route template như **/orders/{id}** thay vì đường dẫn chứa ID thực.
- Đưa định danh của một lần thực thi vào trace khi có nhu cầu điều tra chi tiết, thay vì biến nó thành tag metrics.
- Xem xét cả cardinality kết hợp: nhiều tag riêng lẻ có ít giá trị vẫn có thể tạo ra rất nhiều tổ hợp.

## 3. Micrometer Observation: mô tả vòng đời hoạt động

Observation là mô hình instrumentation xoay quanh một hoạt động có điểm bắt đầu, quá trình thực hiện và điểm kết thúc. Một observation có tên, context và vòng đời; context có thể chứa trạng thái, lỗi cùng các key-value mô tả hoạt động.

Ứng dụng thường tạo observation tại ranh giới có ý nghĩa vận hành, ví dụ:

- Một HTTP request được tiếp nhận và xử lý.
- Một lời gọi HTTP client hoặc truy vấn cơ sở dữ liệu được thực hiện.
- Một tác vụ nền bắt đầu và hoàn tất.
- Một bước nghiệp vụ như tính phí, giữ hàng hoặc xác nhận đơn hàng được thực hiện.

ObservationRegistry là nơi quản lý observation và các ObservationHandler được đăng ký. Handler nhận các sự kiện trong vòng đời observation và chuyển chúng thành dạng tín hiệu mà nó phụ trách. Khi cấu hình phù hợp, một observation có thể tạo metrics thông qua handler metrics và tạo span thông qua handler tracing. Nếu chỉ có một nhóm handler được cấu hình, observation chỉ tạo ra những tín hiệu mà nhóm đó hỗ trợ.

Đây là điểm khác biệt quan trọng: Observation mô tả hoạt động và cung cấp điểm tích hợp; nó không phải kho lưu trữ metrics, không phải backend tracing và cũng không tự bảo đảm rằng mọi phương thức trong ứng dụng đều được đo. Hoạt động cần được instrumentation trực tiếp hoặc thông qua tích hợp framework.

~~~java
Observation.createNotStarted("inventory.reserve", observationRegistry)
    .lowCardinalityKeyValue("operation", "reserve")
    .highCardinalityKeyValue("order.id", orderId)
    .observe(() -> inventoryService.reserve(orderId));
~~~

Ví dụ này tạo observation cho thao tác giữ hàng. **operation=reserve** có tập giá trị nhỏ nên phù hợp với low-cardinality key-value. **order.id** có thể có rất nhiều giá trị nên được đặt ở nhóm high-cardinality. Handler metrics thường sử dụng các giá trị low-cardinality làm tag; handler tracing có thể sử dụng cả hai nhóm làm thuộc tính span. Cách xử lý chính xác phụ thuộc vào handler và cấu hình tích hợp.

Observation hỗ trợ các điểm mở rộng để chuẩn hóa instrumentation:

- **ObservationConvention** quyết định tên và các key-value chuẩn cho một loại observation. Convention giúp nhiều nơi trong ứng dụng phát ra dữ liệu nhất quán.
- **ObservationFilter** cho phép điều chỉnh context sau khi observation được tạo, trước khi các handler xử lý.
- **ObservationHandler** nhận sự kiện vòng đời và tạo tín hiệu tương ứng, chẳng hạn cập nhật meter hoặc tạo span.
- **ObservationRegistry** tập hợp cấu hình và handler để ứng dụng sử dụng observation.

Nên ưu tiên Observation khi một hoạt động có ý nghĩa vận hành và có thể cần nhiều loại tín hiệu cùng lúc. Với một phép đo đơn giản chỉ phục vụ metrics, đăng ký Counter, Gauge hoặc Timer trực tiếp vẫn là lựa chọn hợp lý. Không cần tạo observation cho mọi dòng mã; hãy chọn các ranh giới có thể giải thích được trong vận hành.

## 4. Micrometer Tracing: theo dấu một lần thực thi

Tracing trả lời câu hỏi về đường đi của một lần thực thi. Một trace bao gồm một hoặc nhiều span. Mỗi span đại diện cho một hoạt động trong trace, có thời điểm bắt đầu và kết thúc, tên, thuộc tính, trạng thái và quan hệ với span khác. Quan hệ cha-con thể hiện việc một hoạt động gọi hoặc khởi tạo hoạt động khác.

Ví dụ, trace của một request đặt hàng có thể gồm:

1. Span tiếp nhận request tại HTTP server.
2. Span kiểm tra thông tin khách hàng.
3. Span truy vấn tồn kho.
4. Span gọi dịch vụ thanh toán.
5. Span ghi kết quả đơn hàng.

Tổng thời gian của trace cho biết thời gian quan sát được từ đầu đến cuối; các span con giúp xác định thành phần nào đóng góp nhiều vào độ trễ. Trace ID liên kết các span thuộc cùng một lần thực thi. Span ID xác định từng span. Context được truyền qua ranh giới dịch vụ để span ở dịch vụ tiếp theo có thể nối vào trace đang tồn tại.

Micrometer Tracing cung cấp API trừu tượng cho các thao tác tracing như tạo span, lấy span hiện tại, quản lý scope và truyền trace context. Việc tích hợp với thư viện tracing cụ thể được thực hiện qua bridge, chẳng hạn bridge cho Brave hoặc OpenTelemetry. Thành phần bridge kết nối API Micrometer với implementation tracing; exporter hoặc tích hợp tương ứng chịu trách nhiệm gửi dữ liệu đến hệ thống nhận trace.

Tracing và metrics bổ sung cho nhau:

- Metrics cho biết phân phối độ trễ của toàn bộ nhóm request trong một khoảng thời gian.
- Trace cho biết chi tiết các bước của một request được chọn để ghi nhận.
- Metrics phù hợp với dashboard và cảnh báo liên tục.
- Trace phù hợp với điều tra một request chậm, lỗi hoặc có hành vi bất thường.

Tracing thường áp dụng sampling để giới hạn lượng trace được lưu. Do đó, không nên giả định mọi request đều có trace đầy đủ. Dữ liệu thuộc tính trong span có thể chi tiết hơn tag metrics, nhưng vẫn cần kiểm soát kích thước, độ nhạy và chính sách dữ liệu. Không đưa bí mật, token, thông tin xác thực hoặc dữ liệu cá nhân không cần thiết vào span hay baggage.

## 5. Context Propagation: giữ ngữ cảnh qua ranh giới thực thi

Nhiều thư viện Java lưu ngữ cảnh hiện tại trong ThreadLocal. Cách này hoạt động thuận tiện khi toàn bộ thao tác chạy trên cùng một thread. Tuy nhiên, ứng dụng hiện đại thường chuyển công việc sang executor, thread pool, callback hoặc pipeline reactive. ThreadLocal không tự chuyển giá trị từ thread ban đầu sang thread thực thi tiếp theo.

Micrometer Context Propagation cung cấp cơ chế chụp, chuyển và khôi phục những giá trị ngữ cảnh đã đăng ký. Nó kết nối các mô hình lưu context khác nhau, đặc biệt là ThreadLocal và Reactor Context.

Các khái niệm chính gồm:

- **ThreadLocalAccessor** mô tả cách đọc, ghi và xóa một giá trị ngữ cảnh trong ThreadLocal.
- **ContextRegistry** quản lý các accessor để thư viện biết loại ngữ cảnh nào có thể được chuyển.
- **ContextSnapshot** đại diện cho ảnh chụp của các giá trị ngữ cảnh tại một thời điểm và có thể được dùng để khôi phục chúng khi chạy một tác vụ.
- **ContextSnapshotFactory** tạo snapshot theo các accessor và quy tắc đã cấu hình.

Ví dụ, khi một request tạo tác vụ gửi sang executor, ứng dụng có thể chụp context hiện tại rồi bọc tác vụ bằng snapshot. Khi tác vụ chạy, các giá trị đã đăng ký được khôi phục trong phạm vi thực thi và được dọn lại sau đó. Với Reactor, cơ chế tích hợp có thể chuyển giá trị giữa Reactor Context và ThreadLocal tại các điểm thực thi phù hợp.

Context Propagation không tự sinh trace, không ghi meter và không quyết định nội dung observation. Nó chỉ giúp các thành phần đã đăng ký tiếp tục nhìn thấy đúng ngữ cảnh khi luồng thực thi thay đổi. Nếu không đăng ký accessor hoặc không bật cơ chế tích hợp tương ứng, một giá trị tùy ý trong ThreadLocal sẽ không tự động được chuyển.

Khi sử dụng context propagation, cần chú ý ba điều. Thứ nhất, chỉ chuyển những giá trị thật sự cần cho công việc tiếp theo. Thứ hai, bảo đảm giá trị được khôi phục trong đúng phạm vi và được dọn sau khi tác vụ kết thúc để tránh rò rỉ giữa các request dùng chung thread. Thứ ba, kiểm thử cả trường hợp thành công, ngoại lệ và thực thi bất đồng bộ, vì lỗi context thường chỉ xuất hiện khi thread thay đổi hoặc khi tác vụ chạy lại trên thread pool.

## 6. Cách các thành phần kết nối trong ứng dụng

Luồng khái niệm dưới đây cho thấy nơi mỗi thành phần tham gia. Mã nghiệp vụ có thể ghi meter trực tiếp hoặc tạo observation. Các handler của observation chuyển hoạt động thành metrics và/hoặc span. Context propagation hỗ trợ duy trì context trong khi công việc đi qua các ranh giới thực thi.

~~~mermaid
flowchart TD
    A["Mã ứng dụng và framework"] --> B["Micrometer Metrics API"]
    A --> C["Observation API"]
    B --> D["MeterRegistry"]
    D --> E["Hệ thống metrics"]
    C --> F["ObservationRegistry"]
    F --> G["ObservationHandler cho metrics"]
    F --> H["ObservationHandler cho tracing"]
    G --> D
    H --> I["Micrometer Tracing"]
    I --> J["Bridge và exporter tracing"]
    J --> K["Hệ thống tracing"]
    A -. "đổi thread / reactive" .-> L["Context Propagation"]
    L -. "khôi phục context" .-> A
~~~

Sơ đồ cũng thể hiện rằng Metrics API và Observation API có thể cùng tồn tại. Một ứng dụng có thể dùng meter trực tiếp cho số liệu đơn giản và dùng observation cho những hoạt động cần được xử lý thống nhất bởi metrics hoặc tracing. Việc dùng cả hai cần có chủ đích để tránh đo trùng cùng một hoạt động và tạo ra các meter có tên hoặc ý nghĩa không nhất quán.

## 7. Tích hợp với Spring Boot

Spring Boot Actuator và các dependency Micrometer giúp ứng dụng bật instrumentation và xuất dữ liệu với ít cấu hình thủ công hơn. Tùy dependency trên classpath và cấu hình, Spring Boot có thể tự cấu hình MeterRegistry, ObservationRegistry, các handler và instrumentation cho những thành phần phổ biến như HTTP server, HTTP client hoặc truy cập dữ liệu.

Một cấu hình điển hình cần xác định rõ các phần sau:

1. **Actuator và registry**: thêm Actuator cùng registry phù hợp với hệ thống metrics đích. Registry quyết định định dạng và cách xuất số liệu.
2. **Observation**: sử dụng ObservationRegistry và các handler tương ứng. Với instrumentation tùy chỉnh, chọn tên, convention và key-value có ý nghĩa.
3. **Tracing**: thêm Micrometer Tracing, bridge tương ứng và cấu hình xuất trace. Cần thống nhất cách truyền trace context giữa các dịch vụ.
4. **Context Propagation**: bật tích hợp phù hợp với executor hoặc reactive stack khi công việc có thể đổi thread.
5. **Endpoint và quyền truy cập**: chỉ mở các endpoint quản trị cần thiết. Endpoint xem metrics của Actuator phục vụ kiểm tra; endpoint xuất dữ liệu cho một registry là cơ chế tích hợp riêng, tùy backend.

Trong quá trình triển khai, cần xác minh auto-configuration thực tế của phiên bản Spring Boot và các dependency đang dùng. Có mặt một thư viện trên classpath không đồng nghĩa mọi loại tín hiệu đều đã được xuất đến backend. Ví dụ, tạo observation không bảo đảm có span nếu chưa có tracing handler và bridge phù hợp; có meter trong registry cũng không bảo đảm backend nhận được dữ liệu nếu registry chưa được cấu hình đúng.

## 8. Kiểm thử và diễn giải kết quả

Instrumentation cần được kiểm thử như một phần của hành vi ứng dụng. Kiểm thử không chỉ xác nhận mã chạy mà còn xác nhận dữ liệu phát ra có tên, tag, trạng thái và vòng đời đúng.

- Với metrics, dùng registry trong bộ nhớ như SimpleMeterRegistry để kiểm tra counter tăng đúng, timer ghi nhận số lần và thời lượng, gauge quan sát đúng nguồn dữ liệu, và tag có giá trị mong đợi.
- Với observation, kiểm tra observation được tạo, bắt đầu, kết thúc và ghi nhận lỗi đúng. Kiểm tra convention và filter nếu ứng dụng có tùy biến.
- Với tracing, kiểm tra quan hệ cha-con, trạng thái lỗi, thuộc tính cần thiết và việc truyền trace context qua ranh giới dịch vụ.
- Với context propagation, kiểm tra giá trị xuất hiện trong tác vụ chạy ở thread khác, được khôi phục đúng sau ngoại lệ và không rò rỉ sang tác vụ tiếp theo trên cùng thread.

Khi đọc dashboard, hãy liên hệ metric với hành vi hệ thống. Counter tăng nhanh có thể phản ánh lưu lượng tăng, nhưng cũng có thể là retry hoặc lỗi lặp. Timer tăng ở percentile cao có thể cho thấy một nhóm request chậm dù giá trị trung bình vẫn thấp. Gauge chỉ có ý nghĩa khi hiểu cách lấy giá trị và vòng đời đối tượng được quan sát. Khi metrics chỉ ra một khoảng thời gian bất thường, trace có thể giúp tìm bước gây chậm nếu trace tương ứng đã được sampling và lưu lại.

Không nên diễn giải một chỉ số đơn lẻ tách khỏi ngữ cảnh. Hãy đối chiếu lưu lượng, độ trễ, tỷ lệ lỗi, mức sử dụng tài nguyên và các trace đại diện. Cũng cần phân biệt số liệu của ứng dụng với số liệu do registry hoặc backend tổng hợp, vì cách lấy mẫu, bucket histogram, đơn vị và khoảng thời gian truy vấn có thể ảnh hưởng đến kết quả hiển thị.

## 9. Ranh giới phạm vi của module

Module tập trung vào năng lực instrumentation và quan sát ứng dụng Java bằng Micrometer:

- Thiết kế và sử dụng Counter, Gauge, Timer, DistributionSummary cùng các meter phù hợp.
- Tổ chức MeterRegistry, cấu hình registry và xuất metrics đến hệ thống giám sát.
- Hiểu Observation, vòng đời, context, convention, filter và handler.
- Phân biệt metrics với tracing; tạo và truyền span context qua các thành phần.
- Duy trì context qua executor, thread pool và luồng reactive.
- Tích hợp với Spring Boot, kiểm soát cardinality và bảo vệ chất lượng dữ liệu quan sát.
- Kiểm thử instrumentation và diễn giải số đo để hỗ trợ vận hành.

Việc lựa chọn, cài đặt và vận hành một sản phẩm backend cụ thể có thể khác nhau theo môi trường. Module cần giúp người học hiểu hợp đồng API, cấu trúc dữ liệu và điểm tích hợp của Micrometer để có thể áp dụng chúng với backend phù hợp. Các chi tiết truy vấn, dashboard, cảnh báo và lưu trữ chuyên biệt của từng sản phẩm được xem xét theo hệ thống đích.

Khi thiết kế instrumentation, hãy bắt đầu từ câu hỏi vận hành cần trả lời, chọn tín hiệu phù hợp, đặt tên và nhãn có quy ước, rồi xác minh dữ liệu qua kiểm thử và backend. Metrics cho bức tranh tổng hợp, Observation cung cấp vòng đời hoạt động thống nhất, Tracing giải thích đường đi của từng lần thực thi, còn Context Propagation giữ ngữ cảnh nhất quán khi công việc di chuyển giữa các thread và mô hình thực thi.

