# Cập nhật execution key sau một tương tác

Spring Web Flow quản lý một hành trình nhiều bước bằng flow execution. Trình duyệt gửi event cùng dữ liệu form đến URL của execution; framework dùng execution key trong URL để tìm đúng trạng thái đang lưu, xử lý request rồi tạo trạng thái tiếp tục cho lần tương tác kế tiếp.

Với điều hướng toàn trang, view được render lại và các form hoặc liên kết thường nhận URL mới từ Spring Web Flow. Với AJAX, trình duyệt chỉ thay một phần giao diện. Nếu phần được thay không chứa form hoặc thông tin điều hướng, trang có thể tiếp tục giữ URL với execution key cũ. Lần AJAX tiếp theo khi đó có thể gửi request bằng key không còn đại diện cho snapshot mới nhất, dẫn đến lỗi không tìm thấy execution, phục hồi nhầm trạng thái cũ hoặc xử lý event trên một nhánh không mong muốn.

Vì vậy, mỗi phản hồi AJAX cần đồng bộ execution URL mới mà máy chủ cung cấp với những thành phần trình duyệt sẽ dùng để gửi tương tác tiếp theo. Cách an toàn là dùng **flowExecutionUrl** do Spring Web Flow tạo, đưa URL đó vào fragment hoặc metadata của phản hồi, rồi cập nhật form action và các điều khiển liên quan.

## 1. Execution key và flow execution URL

Một flow definition mô tả các state và transition. Khi người dùng khởi chạy flow, Spring Web Flow tạo một flow execution. Execution có thể tạm dừng tại view-state để chờ request tiếp theo. Repository lưu trạng thái và cung cấp key để framework tìm lại execution khi trình duyệt gửi request.

URL của flow execution gồm đường dẫn flow và thông tin nhận diện execution. Spring Web Flow cung cấp biến **flowExecutionUrl** cho view để tạo action hoặc liên kết tiếp tục flow. Giá trị này có thể thay đổi sau khi request được xử lý và execution tạo snapshot tiếp theo.

Hãy phân biệt:

| Khái niệm | Vai trò |
|---|---|
| Flow id | Xác định định nghĩa flow, ví dụ **booking**. |
| Flow execution | Một lần chạy cụ thể của flow, có state và dữ liệu riêng. |
| Execution key | Khóa mà repository dùng để tìm một trạng thái execution đã lưu. |
| Flow execution URL | URL được framework tạo để request tiếp tục đúng execution. |
| Event | Hành động mà request yêu cầu flow xử lý, ví dụ **checkAvailability** hoặc **confirm**. |

Execution key là thông tin điều phối nội bộ của flow, không phải mã giao dịch nghiệp vụ và cũng không phải bằng chứng xác thực người dùng. Không dùng key làm khóa đặt chỗ, mã thanh toán hoặc căn cứ phân quyền.

Không nên tự tách, tăng số hoặc ghép execution key. Cấu trúc key và cách biểu diễn trong URL thuộc trách nhiệm của Spring Web Flow và FlowUrlHandler. View chỉ cần dùng URL hiện hành mà framework cung cấp.

## 2. Vì sao AJAX cần cập nhật key?

Giả sử trang đặt chỗ được render với URL execution hiện tại là **U1**. Người dùng nhấn nút kiểm tra tình trạng phòng. Trình duyệt gửi AJAX request đến U1. Máy chủ tiếp tục flow, xử lý event, lưu snapshot mới và trả về fragment cùng URL execution tiếp theo là **U2**.

Nếu trình duyệt chỉ thay nội dung kết quả mà giữ form action ở U1, lần tương tác kế tiếp vẫn gửi đến key cũ. Khi đó:

- Repository có thể không còn giữ snapshot tương ứng với key cũ.
- Nếu snapshot cũ vẫn còn, request có thể tiếp tục từ trạng thái lịch sử thay vì trạng thái mới nhất mà người dùng vừa thấy.
- Event có thể được gửi lại trên một nhánh cũ, tạo lỗi nghiệp vụ hoặc kết quả khó giải thích.
- Hành vi có thể chỉ lỗi sau nhiều lần tương tác, khiến việc tái hiện khó hơn so với lỗi ở request đầu tiên.

Luồng đúng:

~~~text
Trang ban đầu dùng URL U1
          |
          | AJAX event
          v
Máy chủ tiếp tục execution từ U1
          |
          | xử lý event và lưu snapshot mới
          v
Phản hồi fragment + URL U2
          |
          v
Trình duyệt thay fragment
          |
          v
Cập nhật form action thành U2
          |
          | AJAX event tiếp theo
          v
Máy chủ tiếp tục execution từ U2
~~~

Điểm cần đồng bộ là URL dùng cho lần gửi tiếp theo. Nội dung fragment có thể đã mới nhưng nếu form action hoặc liên kết event vẫn giữ URL cũ thì trạng thái giao diện và trạng thái flow sẽ lệch nhau.

## 3. Dùng flowExecutionUrl trong view

Với JSP, đặt action của form theo biến **flowExecutionUrl**. Mỗi event được gửi bằng tên event mà flow khai báo:

~~~jsp
<form id="bookingForm"
      method="post"
      action="${flowExecutionUrl}"
      data-flow-form="true">

    <label for="checkInDate">Ngày nhận phòng</label>
    <input id="checkInDate"
           name="checkInDate"
           type="date">

    <button type="submit"
            name="_eventId_checkAvailability">
        Kiểm tra phòng
    </button>
</form>
~~~

Giá trị **flowExecutionUrl** được Spring Web Flow đưa vào model view. Khi view được render lại với snapshot mới, form nhận URL tương ứng với execution hiện hành.

Ví dụ flow có thể xử lý event kiểm tra phòng và tiếp tục ở view-state:

~~~xml
<view-state id="bookingDetails"
            view="booking/details"
            model="booking">
    <transition on="checkAvailability" to="bookingDetails">
        <evaluate expression="bookingService.checkAvailability(booking)"
                  result="viewScope.availability"/>
    </transition>
    <transition on="confirm" to="confirmBooking"/>
</view-state>
~~~

Đây là ví dụ rút gọn để minh họa event AJAX quay lại cùng view-state. Cấu hình fragment rendering cụ thể phụ thuộc view technology và AjaxHandler đang dùng. Điều quan trọng là phản hồi phải mang dữ liệu mới cùng URL execution hiện hành để trình duyệt có thể tiếp tục đúng flow.

Với ứng dụng dùng Spring form tag, có thể dùng **form:form** và gắn action theo **flowExecutionUrl** tương tự. Dù dùng thẻ HTML hay tag library, không viết cứng URL hoặc tự tạo tham số execution.

## 4. Trả execution URL trong phản hồi fragment

Một phản hồi AJAX thường chỉ chứa một vùng HTML. Nếu form nằm ngoài vùng được thay, action của form không tự cập nhật. Hãy đưa URL mới vào phản hồi bằng một trong hai cách:

1. Render lại chính form cùng với fragment. Form mới đã có action chứa **flowExecutionUrl** hiện hành.
2. Nếu chỉ render vùng kết quả, thêm một phần tử metadata chứa URL hiện hành và dùng JavaScript cập nhật action của form hiện có.

Ví dụ metadata trong JSP:

~~~jsp
<div id="flowMetadata"
     data-flow-execution-url="<c:out value='${flowExecutionUrl}'/>">
</div>

<div id="availabilityResult">
    <c:choose>
        <c:when test="${not empty availability}">
            <p>${availability.message}</p>
        </c:when>
        <c:otherwise>
            <p>Chưa có kết quả kiểm tra.</p>
        </c:otherwise>
    </c:choose>
</div>
~~~

Phần tử **flowMetadata** phải nằm trong nội dung mà AJAX response thực sự trả về. Nếu view chỉ render **availabilityResult**, metadata nằm ngoài fragment sẽ không đến được trình duyệt và URL cũ vẫn còn.

Nếu response render lại toàn bộ form:

~~~jsp
<div id="bookingFormFragment">
    <form id="bookingForm"
          method="post"
          action="<c:out value='${flowExecutionUrl}'/>"
          data-flow-form="true">
        <!-- Các trường và nút event -->
    </form>
</div>
~~~

Khi JavaScript thay **bookingFormFragment** bằng fragment mới, action của form mới đã được cập nhật. Cách này giảm nguy cơ quên cập nhật metadata riêng, nhưng cần chú ý trạng thái giao diện phía client như giá trị đang nhập, focus và event listener.

## 5. Cập nhật action sau khi thay fragment

Nếu chỉ thay vùng kết quả, JavaScript cần đọc URL từ metadata của phản hồi và cập nhật form:

~~~javascript
function synchronizeFlowExecutionUrl(fragmentRoot) {
    const metadata = fragmentRoot.querySelector("#flowMetadata");
    if (!metadata) {
        throw new Error("Phản hồi AJAX thiếu flow execution URL");
    }

    const nextUrl = metadata.dataset.flowExecutionUrl;
    if (!nextUrl) {
        throw new Error("Flow execution URL trong phản hồi bị rỗng");
    }

    document.querySelectorAll("[data-flow-form='true']").forEach(form => {
        form.action = nextUrl;
    });
}
~~~

Hàm này giả định fragment đã được parse thành DOM và chứa phần tử **flowMetadata**. Gọi hàm sau khi nhận phản hồi thành công và trước khi cho phép người dùng gửi event tiếp theo.

Một trình tự thay fragment có thể được tổ chức như sau:

~~~javascript
async function applyAjaxFragment(responseHtml) {
    const template = document.createElement("template");
    template.innerHTML = responseHtml;
    const fragmentRoot = template.content;

    const result = fragmentRoot.querySelector("#availabilityResult");
    if (!result) {
        throw new Error("Phản hồi không có fragment kết quả");
    }

    const currentResult = document.querySelector("#availabilityResult");
    currentResult.replaceWith(result);

    synchronizeFlowExecutionUrl(fragmentRoot);
}
~~~

Trong ứng dụng thực tế, hãy dùng cơ chế fragment rendering và xử lý HTML phù hợp với view technology, AjaxHandler và chính sách bảo mật của dự án. Ví dụ trên mô tả trách nhiệm đồng bộ URL; nó không thay thế bộ xử lý AJAX hoàn chỉnh hoặc quy trình kiểm tra nội dung HTML.

Nếu form được thay trực tiếp cùng fragment, không cần cập nhật action riêng cho form mới. Tuy nhiên, mọi form khác hoặc liên kết trong trang vẫn trỏ đến execution URL cũ cũng cần được render lại hoặc đồng bộ theo URL mới.

## 6. Không tự ghép URL hoặc cập nhật key bằng tay

Không nên:

- Tăng phần số trong key từ **e1s1** thành **e1s2**.
- Tự ghép query parameter tên **execution** hoặc **_flowExecutionKey**.
- Giữ một biến JavaScript cố định chứa key ban đầu suốt vòng đời trang.
- Tự suy luận URL mới từ URL cũ sau khi nhận AJAX response.
- Dùng execution key của tab này cho form ở tab khác.

Những cách này phụ thuộc chi tiết triển khai của repository và FlowUrlHandler. Chúng có thể sai khi đổi phiên bản Spring Web Flow, thay URL scheme, bật snapshot khác hoặc dùng flow handler tùy chỉnh.

Hãy lấy **flowExecutionUrl** từ view được render sau mỗi request. URL này là nguồn dữ liệu chuẩn để gửi tương tác kế tiếp. Nếu cần lưu ở JavaScript, chỉ cập nhật từ phản hồi mới của máy chủ và gắn với đúng form hoặc đúng vùng flow.

## 7. Đồng bộ nhiều form và liên kết event

Một trang flow có thể có nhiều form hoặc nhiều nút event. Chúng có thể cùng gửi request đến một execution nhưng thực hiện các hành động khác nhau.

Ví dụ:

~~~jsp
<form id="bookingForm"
      method="post"
      action="<c:out value='${flowExecutionUrl}'/>"
      data-flow-form="true">
    <!-- Trường nhập đặt chỗ -->
    <button type="submit" name="_eventId_checkAvailability">
        Kiểm tra
    </button>
    <button type="submit" name="_eventId_continue">
        Tiếp tục
    </button>
</form>
~~~

Nếu form được thay toàn bộ, cả hai nút sẽ dùng action mới. Nếu action được quản lý ở metadata riêng, cần cập nhật mọi form thuộc cùng execution.

Với liên kết event, không nên chỉ thay URL gốc mà bỏ mất event parameter. Hãy render lại liên kết từ server với **flowExecutionUrl** mới và event tương ứng, hoặc dùng một helper có quy tắc rõ ràng để tạo request theo API được ứng dụng hỗ trợ. Tránh tự ghép chuỗi không escape hoặc nối query parameter bằng cách giả định URL chưa có query string.

Nếu một trang chứa nhiều flow execution độc lập, ví dụ hai widget mỗi widget chạy một flow riêng, không cập nhật tất cả form bằng cùng một URL. Mỗi vùng giao diện phải giữ metadata và URL riêng của execution mà nó đại diện. Có thể gắn định danh vùng, chẳng hạn **data-flow-id**, để chọn đúng form khi đồng bộ.

## 8. Xử lý nhiều AJAX request đồng thời

Một execution là trạng thái có thứ tự. Nếu người dùng bấm nhiều nút hoặc JavaScript gửi nhiều request đồng thời với cùng execution key, các request có thể cạnh tranh để tiếp tục và lưu snapshot. Phản hồi có thể về không theo thứ tự gửi.

Ví dụ:

~~~text
Request A gửi với URL U1
Request B cũng gửi với URL U1
          |             |
          v             v
     Máy chủ xử lý A   Máy chủ xử lý B
          |             |
          v             v
     Trả URL U2       Trả URL U3
          |             |
          +------?------+
                 |
                 v
        Phản hồi về sai thứ tự
~~~

Nếu phản hồi cũ đến sau phản hồi mới và ghi đè URL hiện tại, trình duyệt có thể quay lại key cũ. Vì vậy:

- Khóa nút hoặc form trong khi một event làm thay đổi execution đang được xử lý.
- Tuần tự hóa các request phụ thuộc cùng một execution.
- Dùng request sequence hoặc token phía client để bỏ qua phản hồi đã lỗi thời.
- Chỉ áp dụng fragment và URL nếu phản hồi thuộc request mới nhất còn hiệu lực.
- Không cho phép một response cũ thay thế trạng thái giao diện đã được cập nhật bởi response mới hơn.

Ví dụ kiểm tra thứ tự phản hồi:

~~~javascript
let latestRequestSequence = 0;

async function handleFlowInteraction(sendRequest) {
    const sequence = ++latestRequestSequence;
    const responseHtml = await sendRequest();

    if (sequence !== latestRequestSequence) {
        return;
    }

    await applyAjaxFragment(responseHtml);
}
~~~

Sequence phía client chỉ giúp bỏ qua response lỗi thời trong một trang. Nó không thay thế khóa hoặc kiểm soát đồng thời ở server. Nếu ứng dụng cho phép nhiều request cùng tiếp tục một execution, cần hiểu chính sách repository và bảo đảm các thao tác nghiệp vụ có tính an toàn khi retry.

## 9. Xử lý flow kết thúc hoặc lỗi trong AJAX

Không phải mọi tương tác AJAX đều trả về một view-state tiếp tục flow. Một event có thể đưa flow đến end-state. Khi đó, execution đã kết thúc và không còn URL tiếp tục hợp lệ để form dùng cho request tiếp theo.

Phản hồi cần được xử lý theo kết quả:

| Kết quả | Cách xử lý ở trình duyệt |
|---|---|
| Flow vẫn tạm dừng | Cập nhật fragment và URL execution mới. |
| Flow kết thúc thành công | Điều hướng đến URL kết quả hoặc view do flow handler trả về. |
| Flow kết thúc theo nhánh hủy | Hiển thị kết quả hủy hoặc đưa người dùng về điểm bắt đầu phù hợp. |
| Execution key không còn hợp lệ | Hiển thị thông báo hết hiệu lực và cung cấp cách bắt đầu lại. |
| Lỗi mạng hoặc lỗi máy chủ | Giữ trạng thái UI phù hợp, không tự đoán key tiếp theo; truy vấn trạng thái hoặc tải lại theo chính sách ứng dụng. |

Nếu server đã xử lý event và lưu snapshot mới nhưng response bị mất trên mạng, trình duyệt không biết URL mới. Không thể tự tạo URL tiếp theo bằng cách sửa key cũ. Ứng dụng cần có đường phục hồi, ví dụ tải lại trang flow theo cơ chế được hỗ trợ, tra cứu kết quả nghiệp vụ bằng mã yêu cầu riêng hoặc yêu cầu người dùng bắt đầu lại nếu execution không còn tồn tại.

Không tự retry một event có tác dụng phụ bằng key mới. Việc đó có thể tạo giao dịch thứ hai. Service nghiệp vụ nên dùng idempotency key riêng cho lệnh ghi; execution key chỉ điều phối trạng thái flow.

## 10. Bảo mật và cache

Execution URL thường gắn với trạng thái riêng của một người dùng và một flow execution. Hãy giữ các nguyên tắc:

- Không đưa execution URL vào log công khai, telemetry không kiểm soát hoặc thông báo lỗi hiển thị rộng rãi.
- Không cache fragment chứa execution URL bằng shared cache giữa nhiều người dùng.
- Dùng chính sách cache phù hợp cho trang và phản hồi phụ thuộc session.
- Giữ CSRF protection cho các request thay đổi trạng thái theo cấu hình Spring Security.
- Xác thực người dùng và kiểm tra quyền nghiệp vụ ở server; execution key không thay thế authentication hay authorization.
- Không chấp nhận URL execution do client tự chế như một nguồn đáng tin cậy.
- Khi response có URL trong HTML attribute, dùng cơ chế escape của template để tránh lỗi markup hoặc injection.

Nếu ứng dụng hỗ trợ nhiều tab, mỗi tab cần giữ URL của execution tương ứng. Không lưu một execution URL toàn cục trong local storage rồi dùng chung cho mọi flow. Cách lưu như vậy có thể khiến một tab gửi event lên execution của tab khác.

## 11. Kiểm thử việc cập nhật execution key

Kiểm thử cần đi qua ít nhất hai tương tác AJAX liên tiếp. Nếu chỉ kiểm tra request đầu tiên, lỗi giữ URL cũ có thể không xuất hiện.

Các trường hợp nên có:

1. **Tương tác đầu tiên.** Trang render với URL U1; gửi event AJAX và xác nhận response chứa URL U2.
2. **Đồng bộ form.** Sau khi thay fragment, kiểm tra action của form bằng U2.
3. **Tương tác thứ hai.** Gửi event tiếp theo và xác nhận request dùng U2, server tiếp tục đúng execution.
4. **Chỉ thay vùng kết quả.** Form nằm ngoài fragment; metadata vẫn được trả về và action được cập nhật.
5. **Thay cả form.** Form mới được render với URL hiện hành và không giữ action cũ.
6. **Nhiều form cùng execution.** Xác nhận tất cả form liên quan được đồng bộ.
7. **Nhiều execution trên cùng trang.** Cập nhật một widget không làm thay đổi URL của widget khác.
8. **Response về sai thứ tự.** Response cũ không ghi đè URL mới nhất.
9. **Flow kết thúc.** Trình duyệt xử lý kết quả cuối cùng thay vì tiếp tục gửi event bằng key đã kết thúc.
10. **Response bị mất.** Ứng dụng không tự tăng key hoặc retry lệnh ghi bằng một execution URL đoán.
11. **Execution hết hiệu lực.** Hiển thị hướng bắt đầu lại mà không lộ chi tiết nội bộ.
12. **CSRF và phân quyền.** Request AJAX vẫn chịu kiểm tra bảo mật giống request form thông thường.

Ở cấp tích hợp, kiểm tra response HTML hoặc payload fragment, URL được render, action của form sau khi thay DOM và trạng thái flow ở request tiếp theo. Dùng tab Network của trình duyệt để xác nhận URL request thực tế qua từng lần tương tác.

## 12. Quy trình triển khai

Khi thêm AJAX vào một view-state của Spring Web Flow, thực hiện theo trình tự:

1. Dùng **flowExecutionUrl** làm URL action ban đầu của form hoặc liên kết event.
2. Xác định fragment nào được render sau event và bảo đảm response có form mới hoặc metadata chứa URL execution mới.
3. Nếu thay cả form, xác nhận action mới được giữ trong DOM.
4. Nếu chỉ thay vùng kết quả, đọc URL từ metadata của response và cập nhật các form thuộc đúng execution.
5. Tuần tự hóa các event phụ thuộc cùng execution hoặc kiểm soát response lỗi thời.
6. Xử lý riêng trường hợp flow kết thúc, execution hết hiệu lực và lỗi mạng.
7. Kiểm thử ít nhất hai request AJAX liên tiếp và kiểm tra URL của từng request.
8. Kiểm tra bảo mật, cache và hành vi nhiều tab.

Không lưu key ban đầu trong JavaScript như một hằng số của trang. Sau mỗi request thành công, nguồn URL tiếp theo phải là giá trị do server render trong response hiện hành.

## 13. Ghi nhớ

Mỗi lần AJAX tiếp tục flow có thể làm thay đổi execution key do repository tạo snapshot mới. Nếu trang chỉ thay nội dung mà giữ form action hoặc liên kết cũ, tương tác kế tiếp có thể tiếp tục từ key lỗi thời. Dùng **flowExecutionUrl** do Spring Web Flow cung cấp và đưa giá trị mới vào fragment, form hoặc metadata để đồng bộ phía trình duyệt.

Không tự ghép hoặc tăng execution key. Khi có nhiều request đồng thời, chỉ áp dụng response mới nhất và tránh gửi nhiều event phụ thuộc cùng execution cùng lúc. Khi flow kết thúc hoặc response bị mất, xử lý theo kết quả và cơ chế phục hồi nghiệp vụ; không đoán key tiếp theo. Kiểm thử nhiều tương tác liên tiếp là cách xác nhận giao diện AJAX và trạng thái flow luôn đi cùng nhau.
