# Giữ dữ liệu ở viewScope qua các tương tác trong cùng state

Trong Spring Web Flow, một màn hình thường không chỉ được hiển thị đúng một lần. Người dùng có thể nhập dữ liệu, gửi event, nhận lỗi validation, thay đổi lựa chọn hoặc yêu cầu cập nhật một phần giao diện rồi tiếp tục làm việc trên chính màn hình đó. Những tương tác này có thể tạo ra nhiều HTTP request trong khi flow vẫn ở cùng một **view-state**.

**viewScope** là phạm vi dữ liệu dành riêng cho view-state đang hoạt động. Nó cho phép giữ lựa chọn tạm thời, dữ liệu phụ trợ và trạng thái giao diện qua nhiều lần render hoặc xử lý event trong cùng state. Khi flow rời view-state, phạm vi này kết thúc. Hiểu đúng vòng đời đó giúp tránh mất trạng thái màn hình khi validation thất bại, tránh khởi tạo lại dữ liệu ngoài ý muốn và xác định dữ liệu nào cần được chuyển sang **flowScope** trước khi sang bước tiếp theo.

Bài học thuộc chương **View-state** của module **Spring Web Flow**. Module này hướng dẫn mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow, đồng thời thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi gặp lỗi.

## 1. Vì sao một view-state cần giữ dữ liệu?

Giả sử một màn hình tìm kiếm cho phép người dùng nhập từ khóa, chọn trạng thái và điều chỉnh bộ lọc ngày. Người dùng nhấn “Tìm kiếm”, nhưng dữ liệu chưa hợp lệ hoặc hệ thống cần yêu cầu bổ sung một trường. Flow trả lại chính màn hình tìm kiếm để người dùng sửa.

Nếu mỗi lần render đều tạo lại form, từ khóa và bộ lọc đã nhập có thể bị mất. Người dùng phải nhập lại và trải nghiệm trở nên khó chịu. Tương tự, một màn hình chọn sản phẩm có thể cần giữ tab đang mở, mục đang chọn hoặc lựa chọn tạm thời trong lúc người dùng thao tác nhiều lần.

Đưa tất cả dữ liệu này vào **sessionScope** sẽ khiến phạm vi sống quá rộng: nhiều flow hoặc nhiều màn hình có thể vô tình dùng chung trạng thái. Đặt vào **flowScope** lại có thể giữ dữ liệu lâu hơn cần thiết, kể cả sau khi người dùng đã rời màn hình. **viewScope** phù hợp với dữ liệu chỉ cần tồn tại trong thời gian view-state hiện tại đang hoạt động.

## 2. Vòng đời và quy tắc của viewScope

viewScope được tạo và gắn với một lần vào view-state. Trong thời gian flow execution vẫn ở view-state đó, dữ liệu trong scope có thể được dùng lại qua các lần render và xử lý event tiếp theo.

Có thể ghi nhớ ba quy tắc:

1. **Khi vào state:** view-state được kích hoạt và viewScope của state đó sẵn sàng để chứa dữ liệu.
2. **Khi vẫn ở state:** các request tiếp theo được xử lý mà không rời view-state, chẳng hạn render lại do lỗi validation hoặc xử lý một event tại màn hình. Dữ liệu viewScope vẫn còn.
3. **Khi rời state:** transition chuyển flow sang state khác làm kết thúc vòng đời của viewScope hiện tại. Nếu flow quay lại view-state đó sau này, đó là một lần vào state mới và dữ liệu view scope được khởi tạo lại.

Sơ đồ vòng đời khái niệm:

~~~mermaid
flowchart TD
    A["Flow vào view-state"] --> B["Tạo / khởi tạo viewScope"]
    B --> C["Render view"]
    C --> D["Người dùng gửi event"]
    D --> E{"Flow còn ở view-state?"}
    E -->|Có: validation lỗi hoặc xử lý tại chỗ| F["Giữ viewScope và render lại"]
    F --> C
    E -->|Không: transition sang state khác| G["Rời view-state"]
    G --> H["Kết thúc viewScope"]
    H --> I["State tiếp theo"]
~~~

viewScope gắn với view-state đang hoạt động trong flow execution, không phải một kho dữ liệu tồn tại suốt HTTP session. Nó cũng không phải nơi lưu trữ bền vững. Khi state kết thúc, ứng dụng không nên trông đợi dữ liệu trong scope còn tồn tại để phục hồi một hành trình sau khi session hết hạn hoặc người dùng đăng nhập lại.

## 3. Phân biệt viewScope với các scope khác

Chọn scope dựa trên câu hỏi: dữ liệu cần tồn tại trong bao lâu và được chia sẻ ở phạm vi nào?

| Scope | Phạm vi tồn tại | Ví dụ phù hợp |
|---|---|---|
| requestScope | Trong một request HTTP | Thông tin tạm chỉ dùng khi xử lý request hiện tại |
| flashScope | Dữ liệu chuyển tiếp ngắn giữa các lần xử lý theo luồng | Thông báo sau khi hoàn tất một thao tác |
| viewScope | Trong thời gian một view-state đang hoạt động | Tab đang chọn, bộ lọc phụ, lựa chọn tạm và dữ liệu xem trước của màn hình |
| flowScope | Trong toàn bộ flow execution | Dữ liệu cần dùng ở nhiều view-state trong cùng flow |
| conversationScope | Trong conversation gồm các flow execution liên quan | Dữ liệu dùng chung giữa flow gốc và subflow |
| sessionScope | Trong HTTP session | Tùy chọn hoặc thông tin dùng chung ở cấp phiên |

Ví dụ trong hành trình tạo hồ sơ:

- Từ khóa và bộ lọc của màn hình tìm kiếm chỉ cần giữ khi người dùng đang ở màn hình tìm kiếm: đặt trong viewScope.
- Hồ sơ đã chọn và cần dùng ở các bước xác nhận, xem lại: đặt trong flowScope.
- Thông tin cần chia sẻ giữa flow gốc và subflow: cân nhắc conversationScope.
- Tùy chọn giao diện dùng chung qua nhiều hành trình trong cùng phiên: có thể thuộc sessionScope, nếu vòng đời nghiệp vụ thực sự yêu cầu.

Không nên chọn flowScope chỉ vì muốn giữ dữ liệu qua nhiều request. Một view-state có thể tồn tại qua nhiều request mà không cần dữ liệu của nó sống suốt flow. Ngược lại, nếu dữ liệu phải được sử dụng ở state tiếp theo thì viewScope sẽ kết thúc quá sớm; hãy chuyển dữ liệu đó sang scope có vòng đời dài hơn.

## 4. Khởi tạo dữ liệu một lần khi vào view-state

Hãy đặt dữ liệu khởi tạo trong on-entry. Action này chạy khi flow vào state. on-render có mục đích xử lý mỗi lần view được render, vì vậy nếu tạo lại form trong on-render, dữ liệu người dùng vừa nhập có thể bị ghi đè khi màn hình được render lại.

Ví dụ dưới đây tạo một form tìm kiếm khi vào view-state:

~~~xml
<view-state id="search" view="search" model="searchForm">
    <on-entry>
        <set name="flowScope.searchForm"
             value="searchService.newSearchForm()" />
        <set name="viewScope.activeTab" value="'basic'" />
        <set name="viewScope.preview" value="null" />
    </on-entry>

    <binder>
        <binding property="keyword" />
        <binding property="status" />
        <binding property="fromDate" />
        <binding property="toDate" />
    </binder>

    <transition on="preview">
        <evaluate expression="searchService.preview(searchForm)"
                  result="viewScope.preview" />
    </transition>

    <transition on="search" to="results">
        <evaluate expression="searchService.search(searchForm)"
                  result="flowScope.searchResults" />
    </transition>

    <transition on="cancel" to="home" />
</view-state>
~~~

Trong ví dụ:

- searchService.newSearchForm() tạo model ban đầu.
- Model form được đặt trong flowScope.searchForm để view-state binding dùng làm model tên searchForm.
- viewScope.activeTab và viewScope.preview giữ trạng thái riêng của màn hình trong khi người dùng vẫn ở state tìm kiếm.
- binder khai báo các thuộc tính form được phép binding. Chỉ khai báo những trường giao diện thực sự cần cập nhật.
- Khi event search được xử lý thành công, service thực hiện tìm kiếm và đặt kết quả vào flowScope.searchResults để state tiếp theo sử dụng.
- Khi transition sang results hoặc home, view-state tìm kiếm kết thúc và viewScope của nó không còn là nơi lưu dữ liệu cho bước sau.

model="searchForm" đặt tên model mà view-state sử dụng để binding với view. Trong ví dụ này, model form nằm trong flowScope theo cách tổ chức phổ biến của view-state; viewScope giữ các giá trị phụ trợ chỉ cần trong màn hình, chẳng hạn tab đang chọn và dữ liệu xem trước. Tách hai loại dữ liệu như vậy giúp tránh phụ thuộc vào chi tiết phân giải model của từng cấu hình Web Flow.

Một view JSP sử dụng Spring form tag có thể có dạng:

~~~jsp
<form:form modelAttribute="searchForm" method="post">
    <label for="keyword">Từ khóa</label>
    <form:input path="keyword" id="keyword" />

    <label for="status">Trạng thái</label>
    <form:select path="status" id="status">
        <form:option value="" label="Tất cả" />
        <form:option value="ACTIVE" label="Đang hoạt động" />
        <form:option value="INACTIVE" label="Ngừng hoạt động" />
    </form:select>

    <button type="submit" name="_eventId_search">Tìm kiếm</button>
    <button type="submit" name="_eventId_cancel">Hủy</button>
</form:form>
~~~

Tên event trong nút submit được Web Flow dùng để xác định transition tương ứng. Khi view được render lại trong cùng state, model được khôi phục theo scope đã cấu hình cho model; các trạng thái phụ trợ trong viewScope cũng được giữ để giao diện tiếp tục đúng ngữ cảnh.

## 5. Giữ dữ liệu khi validation thất bại

Một tình huống điển hình làm rõ lợi ích của viewScope là validation. Người dùng nhập form và gửi event submit, nhưng dữ liệu không hợp lệ. Ứng dụng cần hiển thị thông báo lỗi và giữ nguyên các giá trị hợp lệ mà người dùng đã nhập để họ chỉ phải sửa trường có vấn đề.

Trong Spring Web Flow, validation có thể được thực hiện thông qua binding/validation của model hoặc action nghiệp vụ sử dụng MessageContext. Khi có lỗi và flow tiếp tục hiển thị view-state hiện tại, state chưa kết thúc. Do đó dữ liệu thuộc viewScope vẫn còn trong thời gian state đó hoạt động.

Ví dụ action validation:

~~~xml
<view-state id="editProfile" view="profile/edit" model="profileForm">
    <on-entry>
        <set name="flowScope.profileForm"
             value="profileService.newForm(currentUser)" />
    </on-entry>

    <transition on="submit" to="review">
        <evaluate expression="profileService.validate(profileForm, messageContext)" />
    </transition>
</view-state>
~~~

Service có thể thêm thông báo lỗi vào messageContext. Khi validation thất bại và flow ở lại view-state, viewScope vẫn giữ các trạng thái phụ trợ của màn hình, chẳng hạn tab hoặc phần đang mở; model form tiếp tục giữ các giá trị đã binding theo scope được cấu hình cho model. Khi dữ liệu hợp lệ và transition sang review được thực hiện, state chỉnh sửa kết thúc.

Điểm cần chú ý là không khởi tạo lại form trong on-render:

~~~xml
<!-- Không nên: mỗi lần render có thể tạo form mới và làm mất dữ liệu -->
<on-render>
    <set name="flowScope.profileForm"
         value="profileService.newForm(currentUser)" />
</on-render>
~~~

on-render có thể chạy nhiều lần trong cùng vòng đời view-state. Hãy dùng nó cho các công việc thực sự cần chạy mỗi lần render, ví dụ chuẩn bị dữ liệu hiển thị phụ thuộc vào lần render hiện tại. Nếu cần đặt giá trị mặc định, ưu tiên on-entry hoặc chỉ cập nhật khi thuộc tính chưa có giá trị.

## 6. Xử lý nhiều tương tác trong cùng view-state

Một view-state có thể là nơi diễn ra nhiều tương tác trước khi flow chuyển sang bước tiếp theo. Ví dụ, màn hình cấu hình báo cáo cho phép người dùng thay đổi bộ lọc, xem trước, đổi kiểu sắp xếp và cuối cùng mới xác nhận.

Có thể giữ trạng thái giao diện trong viewScope:

~~~xml
<view-state id="configureReport" view="report/configure">
    <on-entry>
        <set name="viewScope.reportOptions"
             value="reportService.defaultOptions()" />
        <set name="viewScope.preview" value="null" />
    </on-entry>

    <transition on="preview">
        <evaluate expression="reportService.preview(viewScope.reportOptions)"
                  result="viewScope.preview" />
    </transition>

    <transition on="reset">
        <set name="viewScope.reportOptions"
             value="reportService.defaultOptions()" />
        <set name="viewScope.preview" value="null" />
    </transition>

    <transition on="continue" to="confirmReport">
        <set name="flowScope.confirmedOptions"
             value="viewScope.reportOptions" />
    </transition>
</view-state>
~~~

Hai event preview và reset được xử lý trong màn hình cấu hình. Chúng không chỉ định state đích khác, nên flow tiếp tục ở view-state hiện tại và dữ liệu viewScope được giữ để render tiếp. Event continue chuyển sang confirmReport; trước khi rời state, transition chuyển lựa chọn cần dùng tiếp sang flowScope.confirmedOptions.

Khi áp dụng mẫu này, hãy kiểm tra hành vi của transition theo cấu hình Web Flow đang dùng. Nếu một event dẫn flow sang state khác rồi quay lại, đó là một lần vào state mới; không dựa vào viewScope cũ để giữ dữ liệu qua ranh giới đó.

## 7. Chuyển dữ liệu cần giữ sang flowScope trước khi rời state

viewScope có vòng đời ngắn theo view-state. Trước một transition sang state khác, hãy xác định dữ liệu nào cần thiết ở bước tiếp theo. Chuyển đúng phần dữ liệu đó sang flowScope hoặc scope phù hợp.

Ví dụ:

~~~xml
<transition on="continue" to="review">
    <set name="flowScope.submittedOptions"
         value="viewScope.reportOptions" />
</transition>
~~~

Sau transition, state review có thể dùng flowScope.submittedOptions mà không phụ thuộc vào viewScope của state trước.

Nếu object có thể tiếp tục bị thay đổi ở state mới, việc gán trực tiếp có thể làm hai scope tham chiếu cùng một object trong khoảng chuyển tiếp. Khi cần một bản chụp dữ liệu ổn định, hãy gọi service để tạo DTO hoặc bản sao chỉ chứa các trường cần thiết:

~~~xml
<transition on="continue" to="review">
    <evaluate expression="reportService.toReviewCommand(viewScope.reportOptions)"
              result="flowScope.reviewCommand" />
</transition>
~~~

Không nên sao chép toàn bộ form vào flowScope theo thói quen. Hãy chỉ giữ các trường cần thiết cho bước tiếp theo để giảm dữ liệu tồn tại lâu hơn yêu cầu.

## 8. Những lỗi thiết kế thường gặp

| Cách làm | Hậu quả | Cách xử lý |
|---|---|---|
| Khởi tạo lại form trong on-render | Mất dữ liệu sau mỗi lần render lại | Khởi tạo trong on-entry |
| Đặt dữ liệu chỉ dùng ở một màn hình vào flowScope | Dữ liệu sống lâu hơn cần thiết, dễ bị dùng nhầm ở state khác | Dùng viewScope |
| Chuyển state nhưng vẫn kỳ vọng viewScope cũ tồn tại | Mất dữ liệu ở bước tiếp theo | Chuyển dữ liệu cần giữ sang flowScope trước transition |
| Đưa entity lớn hoặc toàn bộ kết quả truy vấn vào view scope | Tăng bộ nhớ và chi phí lưu execution | Giữ ID hoặc dữ liệu hiển thị tối thiểu; phân trang khi cần |
| Cho phép binding mọi thuộc tính của object | Người dùng có thể gửi thêm trường không dự kiến | Khai báo binder allowlist và kiểm tra dữ liệu ở service |
| Coi viewScope là ranh giới bảo mật | Dữ liệu vẫn có thể bị gửi lên từ client theo request | Xác thực, phân quyền và kiểm tra nghiệp vụ ở server |
| Dựa vào viewScope để khôi phục sau khi session hết hạn | Không còn dữ liệu để tiếp tục | Lưu bản nháp bền vững nếu nghiệp vụ yêu cầu |

Ngoài ra, cần lưu ý các tình huống sau:

- **Nhiều tab hoặc request cũ:** Người dùng có thể gửi một form được render từ trạng thái trước đó. Flow execution key hoặc trạng thái execution có thể đã thay đổi. Hãy xử lý lỗi execution hết hạn hoặc event không còn hợp lệ bằng thông báo có hướng dẫn, không để lỗi nội bộ xuất hiện trên giao diện.
- **Request đồng thời:** Cơ chế điều phối conversation/flow execution giúp framework quản lý truy cập trạng thái, nhưng không thay thế transaction, kiểm tra phiên bản dữ liệu hoặc idempotency của nghiệp vụ.
- **Dữ liệu nhạy cảm:** Không lưu mật khẩu, token bí mật dài hạn hoặc dữ liệu thanh toán nhạy cảm trong view scope. Mọi dữ liệu gửi từ trình duyệt đều cần được kiểm tra lại ở server.
- **Subflow:** View scope thuộc view-state hiện tại. Nếu dữ liệu cần chia sẻ giữa flow gốc và subflow, hãy dùng tham số đầu vào/đầu ra hoặc conversationScope theo thiết kế, thay vì giả định view scope của state cha vẫn có thể được dùng trong mọi state của subflow.

## 9. Kiểm thử việc giữ dữ liệu trong cùng state

Một bài kiểm thử tốt cần chứng minh dữ liệu được giữ khi flow ở lại state và được giải phóng khi state kết thúc.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Vào view-state lần đầu | on-entry tạo model và giá trị mặc định |
| Render view lần đầu | View nhận đúng model và dữ liệu ban đầu |
| Gửi event làm validation thất bại | Flow ở lại view-state; dữ liệu người dùng nhập vẫn được giữ |
| Render lại sau lỗi | Thông báo lỗi hiển thị và các trường hợp lệ không bị reset |
| Gửi event xử lý tại chỗ như preview/reset | Các thuộc tính viewScope còn dùng được ở lần render kế tiếp |
| Transition sang state khác | Dữ liệu chỉ thuộc view-state không còn được dựa vào |
| Quay lại view-state sau đó | on-entry khởi tạo một vòng đời view scope mới |
| Session hoặc execution hết hạn | Ứng dụng hiển thị hướng dẫn bắt đầu lại hoặc phục hồi từ dữ liệu bền vững |

Có thể kiểm thử bằng flow executor với request context giả lập, sau đó kiểm tra state hiện tại và dữ liệu scope sau từng event. Kiểm thử tích hợp qua Spring MVC nên xác nhận cả việc binding form, gửi đúng event ID, render lại khi có lỗi và chuyển state khi dữ liệu hợp lệ.

Một bộ kiểm thử thực tế cho form tìm kiếm có thể đi theo trình tự:

1. Khởi chạy flow và xác nhận form được khởi tạo.
2. Gửi event search với một trường không hợp lệ.
3. Xác nhận flow vẫn ở state search và dữ liệu hợp lệ đã nhập còn nguyên.
4. Gửi lại event sau khi sửa dữ liệu.
5. Xác nhận flow chuyển sang results và kết quả được lưu trong flowScope.
6. Quay lại màn hình tìm kiếm theo một đường transition mới và xác nhận form được tạo theo vòng đời mới.

Không chỉ kiểm tra giá trị trên giao diện. Hãy kiểm tra cả state của flow execution và scope ở server để phát hiện trường hợp view tình cờ hiển thị dữ liệu cũ trong khi flow đã chuyển state.

## 10. Quy trình chọn và quản lý dữ liệu viewScope

Khi thiết kế một view-state, hãy tự hỏi:

1. Dữ liệu có chỉ phục vụ màn hình hiện tại không? Nếu có, cân nhắc viewScope.
2. Dữ liệu được tạo khi nào? Khởi tạo một lần trong on-entry nếu cần tồn tại qua nhiều lần render.
3. Event nào giữ flow ở state hiện tại? Kiểm tra validation, preview, reset và các event tương tác tại chỗ.
4. Event nào rời state? Chuyển dữ liệu cần dùng tiếp sang flowScope hoặc scope rộng hơn trước transition.
5. Dữ liệu có cần tồn tại sau khi flow/session kết thúc không? Nếu có, lưu bằng tầng persistence của ứng dụng.
6. Form binding có giới hạn trường được phép cập nhật không? Dùng binder phù hợp và xác thực lại ở tầng nghiệp vụ.
7. Các tình huống render lại, request cũ, nhiều tab và hết hạn đã được kiểm thử chưa?

viewScope giúp một view-state duy trì trạng thái giao diện và dữ liệu phụ trợ của màn hình qua nhiều tương tác khi flow vẫn ở cùng state. Khi khởi tạo dữ liệu đúng thời điểm, tránh reset trong mỗi lần render và chuyển dữ liệu cần thiết sang scope dài hơn trước khi rời state, ứng dụng Spring Web Flow có thể giữ trải nghiệm form nhất quán mà vẫn kiểm soát được vòng đời của dữ liệu.
