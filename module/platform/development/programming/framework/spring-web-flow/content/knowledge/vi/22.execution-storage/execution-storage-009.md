# Ảnh hưởng của việc tắt snapshot đến lịch sử điều hướng

Trong Spring Web Flow, một flow execution có thể được tiếp tục qua nhiều HTTP request. Sau mỗi lần xử lý, framework cần lưu trạng thái đủ để request kế tiếp tiếp tục đúng state, scope và dữ liệu của hành trình. Ngoài trạng thái hiện tại, repository có thể giữ các snapshot của những thời điểm trước đó. Các snapshot này cho phép khôi phục execution về một điểm đã lưu, hỗ trợ hành vi quay lại bằng lịch sử trình duyệt.

Tắt snapshot làm thay đổi cách ứng dụng xử lý các request quay về trạng thái cũ. Trình duyệt vẫn có thể hiển thị một trang trước đó từ bộ nhớ cache, nhưng điều đó không bảo đảm server còn snapshot tương ứng để tiếp tục flow từ trang ấy. Vì vậy, cần hiểu rõ sự khác nhau giữa lịch sử hiển thị của trình duyệt, lịch sử snapshot của flow execution và điều hướng nghiệp vụ được mô hình hóa bằng transition.

Bài học thuộc chương **Lưu trữ execution** của module **Spring Web Flow**. Module này hướng dẫn mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi gặp lỗi.

## 1. Snapshot trong Spring Web Flow là gì?

Một flow execution lưu trạng thái của một lần chạy flow: state hiện tại, dữ liệu trong các scope, trạng thái subflow và các thông tin cần thiết để xử lý request tiếp theo. Khi flow tạm dừng để chờ người dùng tương tác, execution repository lưu trạng thái đó để có thể khôi phục ở request sau.

**Snapshot** là ảnh chụp trạng thái execution tại một thời điểm. Repository có thể giữ nhiều snapshot của cùng một execution. Mỗi snapshot đại diện cho một điểm mà flow đã đạt tới trong quá trình tương tác.

Ví dụ một hành trình đặt lịch:

1. Người dùng chọn dịch vụ.
2. Người dùng chọn ngày và giờ.
3. Người dùng nhập thông tin liên hệ.
4. Người dùng xem lại và xác nhận.

Sau mỗi lần flow xử lý request và tạm dừng chờ người dùng, framework có thể lưu snapshot tương ứng. Khi người dùng dùng nút Back của trình duyệt để quay lại một URL execution cũ, repository có thể dùng snapshot cũ để khôi phục trạng thái trước đó, nếu snapshot đó vẫn còn và repository hỗ trợ hành vi này.

Cần phân biệt ba khái niệm:

| Khái niệm | Nội dung | Ai quản lý? |
|---|---|---|
| Lịch sử trình duyệt | Danh sách URL và tài liệu mà trình duyệt đã truy cập | Trình duyệt |
| Snapshot history | Các trạng thái flow execution đã được lưu để có thể khôi phục | Flow execution repository |
| Điều hướng nghiệp vụ | Các bước được mô hình hóa bằng state, event và transition | Flow definition và flow engine |

Ba loại lịch sử có liên quan nhưng không đồng nhất. Trình duyệt có thể giữ một trang cũ trong cache ngay cả khi snapshot phía server đã bị xóa. Ngược lại, ứng dụng có thể chủ động chuyển người dùng về bước trước bằng một transition mà không cần khôi phục snapshot lịch sử của trình duyệt.

## 2. Snapshot hỗ trợ điều hướng quay lại như thế nào?

Trong chế độ lưu snapshot, URL của flow execution thường mang thông tin nhận diện execution và điểm snapshot tương ứng. Khi trình duyệt gửi lại một URL cũ, repository có thể xác định snapshot cần khôi phục, tái tạo trạng thái flow tại thời điểm đó rồi xử lý request tiếp theo.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant W as FlowExecutor
    participant R as ExecutionRepository
    participant S as SnapshotStore

    U->>W: Gửi request với execution key hiện tại
    W->>R: Khôi phục flow execution
    R->>S: Tìm snapshot được chỉ ra bởi key
    S-->>R: Trạng thái snapshot
    R-->>W: Execution đã được khôi phục
    W->>W: Xử lý event và transition
    W->>R: Lưu trạng thái mới / snapshot mới
    R-->>U: Trả view và URL tiếp tục mới
~~~

Ví dụ, người dùng đang ở màn hình xác nhận. Họ nhấn Back của trình duyệt và gửi lại URL gắn với snapshot trước đó. Nếu snapshot còn tồn tại, flow có thể được khôi phục về màn hình nhập thông tin liên hệ.

Khả năng khôi phục này phụ thuộc vào loại repository, cách cấu hình snapshot và thời gian snapshot được giữ lại. Không nên giả định mọi cấu hình repository đều hỗ trợ cùng một hành vi browser back.

Snapshot cũng không phải bản sao của trang HTML. Nó lưu trạng thái thực thi phía server theo cơ chế của repository. Khi khôi phục snapshot, view có thể được render lại từ trạng thái đã lưu; nội dung hiển thị vẫn có thể khác nếu dữ liệu bên ngoài đã thay đổi hoặc view gọi service lấy dữ liệu mới.

## 3. Tắt snapshot ảnh hưởng thế nào?

Khi snapshot bị tắt hoặc số snapshot được giữ lại được cấu hình bằng không, repository không còn lịch sử trạng thái cũ để khôi phục theo cách snapshot thông thường. Flow vẫn cần lưu trạng thái hiện tại để tiếp tục request tiếp theo; tắt snapshot history không đồng nghĩa với việc flow không còn khả năng tiếp tục qua nhiều request.

Tác động thường thấy:

- Request mới nhất vẫn có thể tiếp tục execution hiện tại nếu key và trạng thái hiện tại còn hợp lệ.
- Nút Back của trình duyệt có thể hiển thị trang cũ từ cache, nhưng request gửi từ trang cũ có thể không khôi phục được snapshot đã bị tắt hoặc loại bỏ.
- Người dùng có thể gặp lỗi execution không còn khả dụng, lỗi khôi phục hoặc được chuyển tới trang xử lý hết hạn tùy cấu hình ứng dụng.
- Nhiều tab cùng giữ các URL cũ có nguy cơ gửi request dựa trên trạng thái đã lỗi thời.
- Ứng dụng giảm chi phí lưu trữ nhiều bản sao execution, nhưng phải thiết kế điều hướng và phục hồi rõ ràng hơn.

So sánh hai lựa chọn:

| Hành vi | Có giữ snapshot | Tắt snapshot history |
|---|---|---|
| Tiếp tục execution mới nhất | Có | Có, nếu repository vẫn lưu trạng thái hiện tại |
| Khôi phục execution từ URL cũ | Có thể, khi snapshot còn tồn tại | Không thể dựa vào snapshot cũ |
| Browser Back | Có thể khôi phục trạng thái flow trước đó | Có thể chỉ hiển thị trang cache; submit có thể thất bại |
| Dùng nhiều tab | Có thể quay lại các điểm snapshot còn giữ | Request từ tab cũ dễ trở thành request lỗi thời |
| Chi phí lưu trạng thái | Cao hơn khi giữ nhiều snapshot | Thấp hơn do không giữ lịch sử snapshot |
| Điều hướng nghiệp vụ bằng transition | Vẫn hoạt động | Vẫn hoạt động |

Điểm quan trọng là tắt snapshot history không tự động xóa lịch sử URL của trình duyệt và cũng không thay thế các transition trong flow definition. Nó chỉ thay đổi khả năng khôi phục các phiên bản trạng thái execution đã lưu.

## 4. Cấu hình số lượng snapshot

Trong cấu hình Spring Web Flow, giới hạn snapshot thường được điều khiển bằng thuộc tính **max-execution-snapshots** của flow executor. Giá trị này biểu thị số snapshot tối đa được giữ cho mỗi flow execution. Khi giới hạn bị vượt quá, các snapshot cũ nhất có thể bị loại bỏ để giữ số lượng trong giới hạn.

Ví dụ cấu hình XML minh họa:

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry"
                       max-execution-snapshots="10" />
~~~

Với cấu hình này, repository được yêu cầu giữ tối đa 10 snapshot cho mỗi execution theo cơ chế của phiên bản Spring Web Flow đang dùng. Khi người dùng tiếp tục flow qua nhiều request hơn, snapshot cũ có thể không còn trong lịch sử.

Nếu muốn tắt việc giữ snapshot history, một số phiên bản/cấu hình cho phép đặt giới hạn này thành 0:

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry"
                       max-execution-snapshots="0" />
~~~

Hãy xác minh ý nghĩa của giá trị 0 và vị trí cấu hình trong đúng phiên bản Spring Web Flow của dự án trước khi triển khai. Không nên suy luận rằng mọi implementation repository tùy chỉnh đều diễn giải giá trị này giống repository mặc định. Nếu ứng dụng tự cung cấp FlowExecutionRepository hoặc snapshot factory, hành vi có thể do implementation đó quyết định.

Khi giảm giới hạn snapshot từ một giá trị lớn xuống một giá trị nhỏ, ứng dụng cũng giảm độ sâu lịch sử có thể khôi phục. Đặt giới hạn nhỏ không giống hoàn toàn với tắt snapshot: repository vẫn có thể giữ một số điểm gần nhất, trong khi các điểm xa hơn bị loại bỏ.

## 5. Tắt snapshot không phải tắt lưu trạng thái hiện tại

Đây là nhầm lẫn cần tránh. Một flow execution phải có cơ chế lưu và khôi phục trạng thái hiện tại qua các request. Snapshot history là lớp lưu các phiên bản trạng thái trước đó để hỗ trợ khôi phục về quá khứ.

Nếu ứng dụng vô tình thay repository hoặc tắt luôn cơ chế lưu execution hiện tại, request tiếp theo có thể không tìm thấy execution và flow không thể tiếp tục. Đó là lỗi cấu hình lưu trữ execution, không chỉ là tác động của việc tắt snapshot history.

Có thể phân biệt:

- **Lưu trạng thái hiện tại:** cần thiết để tiếp tục flow sau mỗi request.
- **Lưu snapshot lịch sử:** tùy chọn theo repository và chính sách ứng dụng, hỗ trợ khôi phục trạng thái trước.
- **Lưu dữ liệu nghiệp vụ bền vững:** do database hoặc hệ thống lưu trữ nghiệp vụ đảm nhiệm, phục vụ khôi phục sau khi flow/session kết thúc.

Không dùng snapshot làm bản lưu hồ sơ nghiệp vụ. Snapshot có vòng đời gắn với execution và repository; nó có thể bị giới hạn, xóa hoặc mất khi session hết hạn. Nếu người dùng cần tiếp tục một đơn hàng vào ngày hôm sau, hãy lưu bản nháp bằng ID nghiệp vụ trong database.

## 6. Browser Back khác với transition quay lại trong flow

Nếu sản phẩm cần người dùng quay lại bước trước một cách ổn định, hãy mô hình hóa hành động đó thành transition rõ ràng trong flow definition.

Ví dụ:

~~~xml
<view-state id="enterContact" view="booking/contact">
    <transition on="back" to="chooseSlot" />
    <transition on="continue" to="review" />
</view-state>

<view-state id="chooseSlot" view="booking/slot">
    <transition on="continue" to="enterContact" />
</view-state>
~~~

View có thể cung cấp nút “Quay lại” gửi event **back** tới flow execution hiện tại. Flow engine xử lý transition từ **enterContact** sang **chooseSlot**. Đây là điều hướng nghiệp vụ được định nghĩa rõ ràng và không phụ thuộc vào việc trình duyệt có thể khôi phục một snapshot cũ hay không.

Khi chuyển về state trước, cần quyết định dữ liệu nào được giữ:

- Lựa chọn dịch vụ đã xác nhận có thể nằm trong flow scope.
- Ngày và giờ đang chọn có thể được giữ hoặc khởi tạo lại theo quy tắc nghiệp vụ.
- Dữ liệu nhập ở màn hình liên hệ có thể được giữ để người dùng sửa, nếu phù hợp.
- Dữ liệu xem trước chỉ phục vụ màn hình cũ có thể được tính lại.

Transition không tự động đảo ngược mọi tác động đã xảy ra ở hệ thống bên ngoài. Nếu một bước trước đã giữ chỗ, tạo đơn hoặc thu tiền, quay lại state trước không đồng nghĩa với việc database hay hệ thống thanh toán được hoàn tác. Hãy dùng transaction, trạng thái nghiệp vụ và thao tác bù trừ khi cần.

## 7. Snapshot, nhiều tab và request lỗi thời

Khi người dùng mở cùng một flow trong hai tab, mỗi tab có thể giữ một URL execution key được render ở thời điểm khác nhau. Nếu một tab tiếp tục flow, tab còn lại có thể vẫn chứa key hoặc snapshot cũ.

Khi snapshot history còn được giữ, repository có thể khôi phục một điểm cũ nếu snapshot đó vẫn tồn tại. Tuy nhiên, việc quay lại snapshot có thể làm trạng thái flow lùi về quá khứ, nên ứng dụng phải cân nhắc liệu dữ liệu nghiệp vụ bên ngoài đã thay đổi hay chưa.

Khi snapshot bị tắt, request từ tab cũ có thể không còn điểm khôi phục. Ứng dụng nên:

1. Nhận diện lỗi execution key hoặc snapshot không còn khả dụng.
2. Không tiếp tục xử lý event như thể dữ liệu form vẫn thuộc trạng thái mới nhất.
3. Hiển thị thông báo cho biết hành trình đã thay đổi hoặc hết hạn.
4. Cung cấp đường dẫn quay về trang bắt đầu hoặc khởi tạo lại flow.
5. Nếu có bản nháp nghiệp vụ bền vững, cho phép người dùng tải lại bản nháp sau khi xác thực và kiểm tra quyền.

Không nên tự động chạy lại request cũ trên trạng thái mới nhất. Request đó có thể mang dữ liệu form được tạo ra từ một state cũ và dẫn tới hành vi ngoài ý muốn.

## 8. Tác động đến hiệu năng và tài nguyên

Mỗi snapshot có thể chứa một phần đáng kể trạng thái execution, gồm flow scope, dữ liệu form, thông tin subflow và các object mà ứng dụng giữ trong scope. Giữ nhiều snapshot làm tăng bộ nhớ hoặc dung lượng lưu trữ tùy implementation repository.

Lợi ích khi giảm hoặc tắt snapshot:

- Giảm số phiên bản execution cần lưu.
- Giảm chi phí tạo, tuần tự hóa và khôi phục snapshot.
- Giảm nguy cơ giữ nhiều bản sao của object lớn trong session hoặc repository.
- Giảm thời gian dọn dẹp các snapshot cũ.

Đổi lại, người dùng ít khả năng khôi phục trạng thái cũ bằng browser back. Nếu flow có nhiều bước và người dùng thường xuyên cần quay lại, tắt snapshot có thể làm trải nghiệm kém thuận tiện và tăng số lần phải bắt đầu lại.

Không nên dùng việc tắt snapshot như giải pháp duy nhất cho vấn đề bộ nhớ. Trước tiên, hãy rà soát dữ liệu trong flow scope và conversation scope. Tránh giữ entity lớn, collection không giới hạn, file upload hoặc object có thể truy vấn lại. Chỉ lưu ID hoặc DTO tối thiểu khi có thể, và phân trang dữ liệu hiển thị.

## 9. Ảnh hưởng đến bảo mật và dữ liệu nhạy cảm

Snapshot có thể giữ lại dữ liệu mà flow đang mang trong các scope. Nếu form chứa thông tin cá nhân hoặc dữ liệu nhạy cảm, giữ nhiều snapshot đồng nghĩa với việc có nhiều phiên bản của dữ liệu đó tồn tại trong thời gian execution còn sống.

Khi thiết kế chính sách snapshot:

- Chỉ đưa dữ liệu cần thiết vào flow scope và conversation scope.
- Không lưu mật khẩu, token bí mật dài hạn hoặc dữ liệu thanh toán nhạy cảm trong trạng thái flow.
- Xác định thời hạn lưu snapshot và session theo yêu cầu bảo mật.
- Kiểm tra repository có lưu dữ liệu trong session, bộ nhớ hay cơ chế khác và áp dụng biện pháp bảo vệ phù hợp.
- Bảo đảm người dùng chỉ khôi phục execution thuộc phiên và quyền truy cập hợp lệ.
- Không ghi execution key, payload snapshot hoặc dữ liệu nhạy cảm vào log không được bảo vệ.

Tắt snapshot có thể giảm số bản sao dữ liệu, nhưng không thay thế việc giới hạn dữ liệu lưu trong execution và kiểm soát quyền truy cập.

## 10. Kiểm thử khi thay đổi chính sách snapshot

Trước khi tắt snapshot trong môi trường thật, hãy kiểm thử cả hành vi bình thường lẫn các đường quay lại.

| Kịch bản | Khi giữ snapshot | Khi tắt snapshot history |
|---|---|---|
| Tiếp tục từ view hiện tại | Execution được khôi phục và xử lý event | Execution hiện tại vẫn được tiếp tục nếu repository hỗ trợ lưu trạng thái |
| Nhấn Back của trình duyệt | Có thể khôi phục snapshot trước nếu còn | Trang cache có thể hiện, nhưng request cũ có thể thất bại |
| Submit form từ trang cũ | Có thể khôi phục snapshot tương ứng | Cần xử lý lỗi execution/snapshot cũ |
| Mở hai tab và gửi request lần lượt | Kiểm tra chính sách snapshot và truy cập đồng thời | Tab cũ cần được nhận diện và hướng dẫn làm mới |
| Snapshot vượt giới hạn | Snapshot cũ bị loại theo chính sách | Không có lịch sử snapshot để khôi phục |
| Session hết hạn | Snapshot gắn với session/execution có thể không còn | Execution cũng không còn; cần luồng bắt đầu lại hoặc phục hồi bản nháp |
| Tác động nghiệp vụ đã ghi database | Snapshot không tự hoàn tác dữ liệu bên ngoài | Transition quay lại cũng không tự hoàn tác dữ liệu bên ngoài |

Một bộ kiểm thử nên bao gồm:

1. Khởi chạy flow và xác nhận request đầu tiên tạo execution.
2. Tiếp tục qua ít nhất hai view-state và lưu các giá trị phân biệt được ở từng bước.
3. Kiểm tra URL execution hoặc key mà view nhận được theo cơ chế của phiên bản đang dùng.
4. Khi bật snapshot, thử gửi lại URL của snapshot trước và xác nhận hành vi khôi phục.
5. Khi tắt snapshot, thử gửi lại URL cũ và xác nhận ứng dụng xử lý lỗi một cách có kiểm soát.
6. Kiểm tra nút transition **back** trong flow vẫn hoạt động độc lập với browser back.
7. Kiểm tra session timeout, nhiều tab, request trùng và request đến từ tab cũ.
8. Xác nhận thao tác nghiệp vụ không bị lặp hoặc hoàn tác sai khi người dùng quay lại.

Kiểm thử phải chạy qua repository và cấu hình thực tế của ứng dụng. Mock một flow engine đơn giản có thể xác nhận transition, nhưng không đủ để chứng minh hành vi snapshot của repository.

## 11. Chọn chính sách snapshot phù hợp

Giữ snapshot thường hữu ích khi:

- Hành trình có nhiều bước và người dùng cần quay lại bằng nút Back của trình duyệt.
- Các view-state có dữ liệu nhập cần được khôi phục theo đúng thời điểm.
- Ứng dụng muốn hỗ trợ nhiều điểm quay lại trong giới hạn rõ ràng.
- Chi phí lưu trữ snapshot có thể chấp nhận được.

Giảm số lượng snapshot có thể phù hợp khi:

- Flow dài nhưng chỉ cần quay lại một vài bước gần nhất.
- Execution chứa dữ liệu tương đối lớn.
- Ứng dụng cần cân bằng giữa khả năng quay lại và tài nguyên session.
- Sản phẩm có điều hướng nghiệp vụ riêng và không phụ thuộc nhiều vào browser back.

Tắt snapshot history có thể phù hợp khi:

- Hành trình được thiết kế theo hướng tiến về phía trước.
- Ứng dụng có transition quay lại rõ ràng hoặc cho phép bắt đầu lại có kiểm soát.
- Request từ URL cũ được xử lý bằng thông báo và đường phục hồi phù hợp.
- Việc giảm chi phí lưu trữ quan trọng hơn khả năng khôi phục các trạng thái trước đó.

Không có một giá trị giới hạn snapshot phù hợp cho mọi ứng dụng. Hãy dựa vào kích thước dữ liệu execution, thời lượng flow, hành vi điều hướng mong muốn, tải đồng thời và chính sách lưu dữ liệu để quyết định.

## 12. Quy trình triển khai thay đổi snapshot

Khi thay đổi cấu hình snapshot, hãy làm theo trình tự:

1. Xác định repository đang được flow executor sử dụng và xác nhận implementation hỗ trợ snapshot ra sao.
2. Xác định giá trị giới hạn snapshot hiện tại và ý nghĩa của giá trị mới trong phiên bản đang dùng.
3. Đo kích thước dữ liệu execution và số snapshot được giữ dưới tải thực tế.
4. Xác định hành vi mong muốn cho browser back, nhiều tab và URL execution cũ.
5. Thiết kế transition quay lại hoặc đường bắt đầu lại cho các trường hợp không thể khôi phục snapshot.
6. Bảo đảm dữ liệu cần phục hồi lâu dài được lưu trong tầng nghiệp vụ.
7. Kiểm thử trên cấu hình repository thực tế trước khi triển khai.
8. Theo dõi lỗi khôi phục execution, session timeout, bộ nhớ và phản hồi người dùng sau khi phát hành.

Tắt snapshot làm giảm khả năng quay lại các trạng thái execution cũ, nhưng không loại bỏ việc lưu trạng thái hiện tại để tiếp tục flow. Khi phân biệt snapshot history với browser history và transition nghiệp vụ, đồng thời thiết kế đường phục hồi cho URL cũ, ứng dụng Spring Web Flow có thể kiểm soát tài nguyên lưu trữ mà vẫn giữ hành trình người dùng rõ ràng và nhất quán.
