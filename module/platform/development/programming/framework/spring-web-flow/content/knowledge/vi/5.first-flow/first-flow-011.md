# Đối chiếu hành vi trên trình duyệt với sơ đồ đã thiết kế

> **Chương:** Flow đầu tiên  
> **Module:** SPRING_WEB_FLOW

Trong module **SPRING_WEB_FLOW**, bạn học cách mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; tổ chức form binding, validation, scope và phiên; tích hợp Spring Web Flow với Spring MVC; đồng thời kiểm thử và phục hồi luồng khi có lỗi. Bài này tập trung vào bước kiểm chứng đầu tiên sau khi thiết kế: chạy flow trong trình duyệt, ghi lại những gì thực sự xảy ra và đối chiếu chuỗi state/event/transition đó với sơ đồ.

Một trang hiển thị đúng chưa đủ chứng minh flow chạy đúng. Cần xác định thao tác nào đã gửi event nào, flow đang ở state nào trước và sau thao tác, transition nào được chọn, và dữ liệu có được giữ đúng qua các bước hay không.

## Mục tiêu

Sau bài học, bạn có thể:

- Khởi chạy một flow trong một phiên trình duyệt mới và thực hiện từng nhánh theo sơ đồ.
- Nhận biết state, event và transition qua cấu hình, request mạng và log phía máy chủ.
- Đối chiếu đường đi bình thường, thao tác quay lại, dữ liệu không hợp lệ và các nhánh kết thúc.
- Phân biệt lỗi điều hướng với lỗi binding, validation, action, session hoặc flow execution key.
- Ghi lại sai khác đủ rõ để sửa cấu hình hoặc cập nhật sơ đồ thiết kế.

## 1. Sơ đồ mô tả điều gì, trình duyệt cho ta thấy điều gì?

Sơ đồ flow biểu diễn cấu trúc điều khiển ở phía máy chủ:

| Thành phần | Ý nghĩa khi kiểm chứng |
|---|---|
| **State** | Một trạng thái của flow, chẳng hạn một màn hình cần người dùng nhập liệu, một bước xử lý hoặc điểm kết thúc. |
| **Event** | Tín hiệu được gửi để yêu cầu flow xử lý, thường xuất phát từ một nút hoặc thao tác trên form. |
| **Transition** | Quy tắc chuyển từ state hiện tại sang state tiếp theo khi event phù hợp được nhận và điều kiện cho phép. |
| **Guard / điều kiện** | Điều kiện quyết định một transition có được chọn hay không. |
| **Action** | Công việc chạy trong một bước hoặc trong quá trình chuyển trạng thái, ví dụ gọi service hoặc ghi nhận kết quả. |
| **Subflow** | Một flow con được gọi từ flow cha; flow cha tiếp tục dựa trên kết quả kết thúc mà flow con trả về. |
| **End state** | Điểm kết thúc của flow hoặc kết quả mà flow con trả về cho flow cha. |

Trình duyệt chỉ quan sát được phần biểu hiện của quá trình: nội dung trang, nút bấm, URL, request, response và cookie phiên. Phần state và quyết định chọn transition được thực hiện trong Spring Web Flow ở máy chủ.

Vì vậy, không nên suy ra state chỉ từ tên trang hoặc URL. Một view có thể được dùng ở nhiều tình huống; một action-state có thể chạy mà không hiển thị trang mới; một validation error có thể khiến flow ở lại view-state hiện tại. URL thường chứa thông tin định danh flow execution để máy chủ tiếp tục đúng phiên thực thi. Giá trị đó không phải tên state và cũng không nên được diễn giải như dữ liệu nghiệp vụ.

Khi đối chiếu, hãy ghi lại chuỗi **state trước → event → transition → state sau**. Nội dung trang và URL là bằng chứng bổ sung để xác nhận chuỗi đó.

## 2. Dùng một flow nhỏ làm chuẩn đối chiếu

Giả sử flow đặt lịch có ba bước: nhập thông tin, xem lại và hoàn tất. Người dùng có thể quay lại để sửa thông tin. Khi dữ liệu nhập không hợp lệ, ứng dụng hiển thị lỗi và yêu cầu sửa ngay tại bước nhập.

Sơ đồ hành vi mong đợi:

~~~mermaid
stateDiagram-v2
    [*] --> enter
    enter --> review: next / dữ liệu hợp lệ
    enter --> enter: lỗi binding hoặc validation
    review --> enter: back
    review --> done: confirm
    done --> [*]
~~~

Vòng lặp tại **enter** biểu diễn kết quả quan sát được khi dữ liệu không hợp lệ: người dùng vẫn ở màn hình nhập và thấy thông báo lỗi. Tùy cấu hình validation, đây có thể là trường hợp transition chưa được thực hiện, chứ không nhất thiết là một transition tự trỏ về chính nó được khai báo trong XML.

Một flow XML rút gọn có thể có cấu trúc như sau:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        http://www.springframework.org/schema/webflow/spring-webflow.xsd"
      start-state="enter">

    <view-state id="enter" view="booking/enter">
        <transition on="next" to="review"/>
    </view-state>

    <view-state id="review" view="booking/review">
        <transition on="back" to="enter"/>
        <transition on="confirm" to="done"/>
    </view-state>

    <end-state id="done"/>
</flow>
~~~

Đây là bộ khung để đọc đường đi, không phải cấu hình đầy đủ cho một ứng dụng đặt lịch. Model, binding, validation, action và view resolver cần được bổ sung theo ứng dụng thực tế. Khi kiểm chứng, hãy dùng đúng flow XML và cấu hình đang chạy; đừng dùng sơ đồ minh họa này để kết luận về một nhánh chưa được cấu hình.

Trong view của Spring Web Flow, nút gửi event thường dùng quy ước tên tham số **_eventId_<tên-event>**. Ví dụ, nút chuyển từ bước nhập sang bước xem lại có thể được viết như sau:

~~~html
<form method="post">
    <!-- Đặt action của form là URL flow execution hiện tại -->
    <!-- Các trường nhập được binding vào model của view-state -->
    <button type="submit" name="_eventId_next" value="next">
        Tiếp tục
    </button>
</form>
~~~

URL flow execution được phần tích hợp Spring Web Flow cung cấp cho view; cách biểu diễn thuộc tính action có thể khác theo công nghệ view và cấu hình Spring MVC. Điều cần xác minh là form gửi đến đúng URL của flow execution hiện tại và request mang event mà transition đang chờ. Nếu cấu hình dùng event khác, tên tham số trên form phải khớp với event trong flow definition.

## 3. Chuẩn bị một lần chạy có thể lặp lại

Trước khi mở trình duyệt, hãy xác định:

1. **Flow khởi chạy ở đâu:** URL hoặc endpoint Spring MVC dùng để bắt đầu flow.
2. **Sơ đồ phiên bản nào đang được kiểm chứng:** sơ đồ phải phản ánh cấu hình hiện tại, gồm cả nhánh lỗi và nhánh quay lại.
3. **Dữ liệu thử:** một bộ dữ liệu hợp lệ và ít nhất một bộ dữ liệu cố ý không hợp lệ.
4. **Kết quả mong đợi:** view, event, state đích và dữ liệu cần giữ lại sau mỗi thao tác.
5. **Phiên thử:** bắt đầu bằng phiên mới để tránh nhầm flow execution cũ với lần chạy hiện tại.

Mở cửa sổ riêng tư hoặc xóa trạng thái phiên thử nghiệm theo cách phù hợp với môi trường, sau đó truy cập URL khởi chạy flow. Không bắt đầu bằng cách dán lại một URL flow execution cũ từ lịch sử trình duyệt: URL đó có thể gắn với execution đã kết thúc hoặc đã hết hạn.

Mở Developer Tools trước khi thao tác. Trong thẻ **Network**, bật giữ lại lịch sử request khi điều hướng nếu trình duyệt hỗ trợ. Điều này giúp xem được request trước khi trang chuyển hướng hoặc tải lại. Không chia sẻ cookie, session identifier, flow execution key hay dữ liệu cá nhân trong ảnh chụp màn hình và log gửi cho người khác.

## 4. Theo dõi từng event trong trình duyệt

Thực hiện mỗi thao tác một lần rồi chờ response hoàn tất. Đừng bấm liên tiếp nhiều nút vì khi đó khó xác định request nào tạo ra thay đổi đang quan sát.

Với mỗi bước, ghi lại bốn nhóm bằng chứng:

- **Trước thao tác:** trang đang hiển thị, dữ liệu đã nhập và bước mà sơ đồ cho biết flow đang ở.
- **Thao tác:** nút được bấm hoặc form được gửi; event mà nút dự kiến phát ra.
- **Request/response:** method, endpoint, tham số event, mã trạng thái HTTP, redirect nếu có và view được trả về.
- **Sau thao tác:** nội dung trang, thông báo validation, dữ liệu còn được giữ và state mà log hoặc debugger phía máy chủ xác nhận.

Trong Network, chọn request tương ứng với thao tác và xem phần payload hoặc form data. Với ví dụ ở trên, thao tác Tiếp tục cần phát event **next**, thường thể hiện qua tham số **_eventId_next**. Nếu request không có tham số event dự kiến, hãy kiểm tra tên nút, form, JavaScript xử lý submit và cấu trúc HTML được render.

Một lần chuyển state có thể tạo ra nhiều request tùy cơ chế điều hướng và cấu hình redirect. Hãy đọc toàn bộ chuỗi request liên quan, thay vì chỉ nhìn request cuối cùng. Mã HTTP 200 hoặc 302 tự nó không chứng minh transition đúng; cần xác nhận view và state đích.

Ở phía máy chủ, dùng log hoặc debugger để đối chiếu flow id, flow execution, state hiện tại, event nhận được và transition được chọn. Có thể đặt breakpoint trong action/service liên quan hoặc dùng cơ chế theo dõi flow execution của phiên bản Spring Web Flow đang chạy. Chỉ ghi các định danh kỹ thuật cần thiết; tránh ghi nội dung nhạy cảm của form, cookie hoặc session key.

## 5. Đối chiếu đường đi bình thường và đường đi quay lại

Với flow mẫu, chạy theo thứ tự sau:

| Bước | Thao tác trên trình duyệt | Kết quả mong đợi theo sơ đồ |
|---|---|---|
| 1 | Mở endpoint khởi chạy flow | Flow bắt đầu ở state **enter**, hiển thị view nhập thông tin. |
| 2 | Nhập dữ liệu hợp lệ, bấm Tiếp tục | Request phát event **next**; flow chuyển sang **review**. |
| 3 | Bấm Quay lại | Request phát event **back**; flow trở lại **enter**. |
| 4 | Kiểm tra các trường đã nhập | Dữ liệu cần giữ vẫn còn theo thiết kế của model và scope. |
| 5 | Bấm Tiếp tục rồi Xác nhận | Flow đi qua **review**, nhận event **confirm** và kết thúc ở **done**. |

Sau mỗi bước, đánh dấu transition tương ứng trên sơ đồ. Nếu trang thay đổi đúng nhưng log cho thấy flow đi qua một state khác dự kiến, sơ đồ hoặc cấu hình đang không đồng nhất. Nếu log xác nhận state đúng nhưng trang sai, hãy kiểm tra ánh xạ view, view resolver và dữ liệu được đưa vào model.

Ở bước quay lại, đừng chỉ kiểm tra rằng trang nhập xuất hiện. Hãy xác nhận dữ liệu cần thiết còn nguyên, dữ liệu tạm không còn phù hợp đã được xử lý, và thao tác tiếp tục lần nữa không tạo ra một nhánh ngoài sơ đồ.

## 6. Kiểm chứng binding và validation

Dùng một bộ dữ liệu không hợp lệ, chẳng hạn bỏ trống trường bắt buộc hoặc nhập giá trị sai định dạng. Gửi form theo đúng cách người dùng thực hiện.

Kết quả thường được mong đợi ở bước nhập là:

- Các thông báo lỗi xuất hiện cạnh trường hoặc ở vùng thông báo phù hợp.
- Giá trị hợp lệ mà người dùng đã nhập vẫn được giữ để họ sửa tiếp.
- Flow không đi sang bước xem lại nếu điều kiện validation của transition chưa đạt.
- Người dùng có thể sửa dữ liệu và gửi lại mà không cần khởi chạy một flow mới.

Nếu trang vẫn chuyển sang bước tiếp theo, kiểm tra nơi validation được kích hoạt và điều kiện cho phép transition. Nếu trang ở lại nhưng không có thông báo lỗi, kiểm tra binding, cấu hình validator, message code và cách view hiển thị lỗi. Nếu giá trị biến mất, kiểm tra model gắn với view-state và scope chứa dữ liệu.

Phân biệt ba trường hợp:

1. **Binding error:** dữ liệu request không thể chuyển thành kiểu dữ liệu của thuộc tính model, ví dụ nhập chữ vào trường số.
2. **Validation error:** dữ liệu đã binding được nhưng vi phạm quy tắc nghiệp vụ, ví dụ ngày kết thúc sớm hơn ngày bắt đầu.
3. **Action/service error:** dữ liệu qua binding và validation nhưng bước xử lý phía máy chủ gặp lỗi, ví dụ dịch vụ lưu dữ liệu không khả dụng.

Ba trường hợp này có thể hiển thị thông báo gần giống nhau, nhưng nguyên nhân và cách phục hồi khác nhau. Hãy xem lỗi trong response, message context, log và action được gọi để xác định đúng tầng gây lỗi.

## 7. Kiểm chứng subflow và kết quả trả về

Nếu sơ đồ có flow con, hãy coi thời điểm gọi subflow và thời điểm flow cha tiếp tục là hai mốc cần xác minh riêng. Ví dụ, flow đặt lịch có thể gọi flow thanh toán:

~~~xml
<subflow-state id="payment" subflow="payment-flow">
    <transition on="paid" to="done"/>
    <transition on="cancelled" to="review"/>
</subflow-state>
~~~

Trong ví dụ, flow cha tạm dừng tại state **payment** trong khi flow **payment-flow** thực thi. Khi flow con kết thúc, kết quả kết thúc của nó được dùng để chọn transition tương ứng trong flow cha. Tên event trên transition của flow cha cần khớp với end state mà flow con trả về.

Chạy ít nhất hai tình huống: thanh toán thành công và người dùng hủy. Với mỗi tình huống, kiểm tra:

- Flow cha đã thực sự gọi đúng flow con chưa.
- Người dùng có nhìn thấy các view thuộc flow con theo đúng thứ tự không.
- Kết quả kết thúc của flow con có làm flow cha đi đúng transition không.
- Dữ liệu đầu vào và đầu ra cần trao đổi giữa hai flow có được ánh xạ đúng không.
- Khi hủy hoặc lỗi, flow cha có trở lại state hợp lý và giữ được dữ liệu cần thiết không.

Nếu flow con hiển thị đúng nhưng flow cha không tiếp tục, hãy kiểm tra tên end state, transition của **subflow-state** và mapping dữ liệu đầu ra. Không suy ra flow cha đã hoàn tất chỉ vì trình duyệt đã rời khỏi màn hình của flow con.

## 8. Kiểm tra scope, session và lịch sử trình duyệt

Hành vi khi quay lại trang, tải lại hoặc mở tab mới có thể phụ thuộc vào flow execution repository, cách ứng dụng xử lý continuation và cấu hình session. Hãy kiểm tra theo cấu hình thật của ứng dụng.

| Phạm vi dữ liệu | Vòng đời cần nhớ khi kiểm thử |
|---|---|
| **requestScope** | Chỉ gắn với request hiện tại; không dùng để giữ dữ liệu qua nhiều bước. |
| **viewScope** | Gắn với một view-state; phù hợp với dữ liệu phục vụ view đó. |
| **flashScope** | Dùng cho dữ liệu tạm đi qua một lần chuyển tiếp theo cơ chế flash của flow. |
| **flowScope** | Giữ dữ liệu trong vòng đời flow hiện tại, qua các state của flow. |
| **conversationScope** | Chia sẻ dữ liệu trong vòng đời conversation, hữu ích khi flow cha và subflow cần cùng truy cập dữ liệu. |

Hãy xác định rõ dữ liệu nào phải tồn tại khi người dùng quay lại, dữ liệu nào chỉ cần trong một màn hình và dữ liệu nào được chia sẻ với subflow. Không đặt dữ liệu cần lưu bền vững vào flow scope rồi coi nó là bản ghi nghiệp vụ đã được lưu. Scope của flow phục vụ điều phối một lần thực thi; dữ liệu nghiệp vụ cần được lưu qua service và kho dữ liệu phù hợp.

Thực hiện thêm các thử nghiệm sau:

- **Refresh sau khi submit:** xem trình duyệt gửi lại request hay hiển thị response đã có. Xác nhận thao tác lưu hoặc thanh toán không bị thực hiện lặp ngoài ý muốn.
- **Browser Back:** xem ứng dụng khôi phục snapshot trước đó, yêu cầu tải lại hay báo execution đã hết hạn. Hành vi cụ thể phụ thuộc repository và cấu hình continuation.
- **Mở tab mới:** xác nhận tab mới đang tiếp tục cùng execution hay bắt đầu một flow độc lập theo cách ứng dụng thiết kế.
- **Double click:** kiểm tra hai request gần nhau có thể gọi action hai lần hay không; các thao tác nghiệp vụ quan trọng cần có cơ chế chống xử lý trùng phù hợp.
- **Session timeout:** để phiên hết hạn rồi tiếp tục thao tác. Ứng dụng cần đưa người dùng về điểm bắt đầu hoặc hiển thị hướng dẫn khởi tạo lại rõ ràng.
- **Dùng URL execution cũ:** thử mở lại URL của một flow đã kết thúc hoặc hết hạn. Ứng dụng phải xử lý trạng thái không còn hợp lệ theo cấu hình, không để người dùng đi tắt qua các bước nghiệp vụ.

Flow execution key là thông tin điều phối phiên thực thi. Không tự chỉnh sửa giá trị này để thử đi đến một state khác và không dùng nó như một cơ chế phân quyền. Quyền truy cập và tính hợp lệ của hành động phải được kiểm tra ở phía máy chủ.

## 9. Phân loại sai khác khi kết quả không khớp sơ đồ

Khi quan sát thấy sai khác, hãy xác định request và event đầu tiên mà kết quả lệch khỏi dự kiến. Một số nguyên nhân thường gặp:

| Hiện tượng | Điểm cần kiểm tra |
|---|---|
| Bấm nút nhưng không có request | Nút có nằm trong form không, form có hợp lệ không, JavaScript có chặn submit không. |
| Request có nhưng thiếu event | Tên tham số **_eventId_...**, tên event trong view và cấu hình transition có khớp không. |
| Có event nhưng flow ở nguyên state | Transition có tồn tại cho event đó không; validation hoặc guard có ngăn chuyển không. |
| Flow sang state không mong muốn | Có transition khác cùng event, điều kiện hoặc action nào làm thay đổi kết quả không. |
| State đúng nhưng view sai | Kiểm tra thuộc tính view, view resolver, tên template và dữ liệu model. |
| Dữ liệu biến mất khi quay lại | Kiểm tra model, binding và vòng đời view/flow/conversation scope. |
| Subflow kết thúc nhưng flow cha không đi tiếp | Kiểm tra end state của flow con, event trả về và transition của flow cha. |
| Request báo execution không hợp lệ hoặc hết hạn | Kiểm tra session, flow execution key, lịch sử trình duyệt và repository. |
| Action được gọi nhiều lần | Kiểm tra refresh, double click, retry của client và tính idempotent của nghiệp vụ. |

Dùng một ví dụ cụ thể để phân tích: sơ đồ nói từ **enter** nhận **next** sẽ sang **review**, nhưng trình duyệt vẫn hiển thị trang nhập. Trước hết kiểm tra Network xem request có gửi **_eventId_next** hay không. Nếu không có, lỗi nằm ở form hoặc event của view. Nếu có, xem log để biết flow có nhận event không. Nếu flow nhận event nhưng không chuyển, kiểm tra validation và guard. Nếu flow đã sang **review**, kiểm tra view mapping và response. Cách lần theo từng tầng giúp tránh sửa nhầm sơ đồ khi nguyên nhân thực tế nằm ở form hoặc cấu hình view.

Không cập nhật sơ đồ chỉ để làm cho nó khớp với một hành vi sai. Trước khi sửa sơ đồ, xác định hành vi quan sát được có phải yêu cầu nghiệp vụ đã thống nhất hay là lỗi triển khai. Khi yêu cầu nghiệp vụ thay đổi, cập nhật sơ đồ và cấu hình cùng một quyết định thiết kế.

## 10. Ghi nhận kết quả kiểm chứng

Với mỗi đường đi, ghi lại state, event và bằng chứng tương ứng. Có thể dùng mẫu sau trong ghi chú kiểm thử:

| State trước | Event / thao tác | State mong đợi | State thực tế | Bằng chứng và kết luận |
|---|---|---|---|---|
| **enter** | **next**, dữ liệu hợp lệ | **review** | … | Request, response, log |
| **enter** | **next**, dữ liệu không hợp lệ | **enter** | … | Lỗi binding/validation, dữ liệu còn lại |
| **review** | **back** | **enter** | … | Event, view và dữ liệu được giữ |
| **review** | **confirm** | **done** | … | Action, kết quả xử lý, end state |
| **payment** | Flow con trả **paid** hoặc **cancelled** | State tương ứng trong flow cha | … | End state và transition của flow cha |

Đánh dấu từng dòng là **PASS**, **FAIL** hoặc **NEEDS INVESTIGATION**. Với dòng FAIL, ghi request cụ thể, event, state trước/sau theo log, thông báo lỗi và bước tái hiện. Không đưa cookie, session identifier, flow execution key hoặc dữ liệu cá nhân vào báo cáo.

Một lần kiểm chứng có thể coi là hoàn tất khi:

- Đường đi bình thường khớp sơ đồ từ state bắt đầu đến end state.
- Các nhánh quay lại và validation cho kết quả đúng.
- Các nhánh subflow trả kết quả đúng cho flow cha, nếu có.
- Dữ liệu tồn tại đúng vòng đời scope đã thiết kế.
- Refresh, Back, submit lặp và session timeout có hành vi đã được xác định.
- Mọi sai khác đều có bằng chứng và được phân loại là lỗi triển khai hoặc thay đổi yêu cầu thiết kế.

## 11. Từ kiểm tra thủ công đến kiểm thử tự động

Kiểm tra trên trình duyệt giúp xác nhận tích hợp thực tế giữa flow, Spring MVC, view, session và trình duyệt. Để kết quả ổn định qua các lần sửa, hãy chuyển những đường đi quan trọng thành kiểm thử tự động ở đúng tầng:

- **Kiểm thử service:** xác nhận quy tắc nghiệp vụ và validation độc lập với điều hướng.
- **Kiểm thử flow execution:** xác nhận event, transition, điều kiện và kết quả của state theo flow definition.
- **Kiểm thử tích hợp Spring MVC:** xác nhận form binding, response, redirect, session và cách view được render.
- **Kiểm thử trình duyệt đầu cuối:** xác nhận người dùng thực sự nhìn thấy trang, thông báo lỗi và điều hướng đúng qua các thao tác.

Không nên chỉ kiểm thử rằng một URL trả về mã 200. Một kiểm thử hữu ích cần xác nhận cả event gửi vào, kết quả chuyển state hoặc việc ở lại state, dữ liệu cần giữ và nội dung phản hồi có ý nghĩa với người dùng. Giữ lại một số kịch bản trình duyệt cho các luồng nghiệp vụ quan trọng; dùng kiểm thử ở tầng thấp hơn để bao phủ nhanh các tổ hợp event và điều kiện.

## Kết luận

Đối chiếu flow trên trình duyệt là quá trình nối ba nguồn bằng chứng: sơ đồ thiết kế, request/response từ trình duyệt và state/event được Spring Web Flow xử lý ở máy chủ. Khi ghi nhận được chuỗi state trước, event, transition và state sau cho cả đường đi bình thường lẫn đường đi lỗi, bạn có thể xác định chính xác phần nào đang sai và sửa đúng cấu hình, view, validation hoặc thiết kế flow.
