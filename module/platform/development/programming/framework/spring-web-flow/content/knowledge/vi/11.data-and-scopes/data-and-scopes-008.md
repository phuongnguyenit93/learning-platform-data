# Phân biệt scope Web Flow với request và session của Servlet

## Bối cảnh và mục tiêu

Bài học thuộc chương **Dữ liệu và scope** của module `SPRING_WEB_FLOW`. Spring Web Flow mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow. Khi người dùng đi qua nhiều màn hình, ứng dụng cần giữ dữ liệu form, kết quả validation và thông tin nghiệp vụ đúng thời điểm; đồng thời phải biết dữ liệu nào chỉ tồn tại trong một request, dữ liệu nào thuộc một flow đang chạy và dữ liệu nào dùng chung trong phiên làm việc của người dùng.

Spring Web Flow cung cấp các scope riêng như request, flash, view, flow và conversation. Servlet API cũng có request attribute và HttpSession attribute. Hai nhóm này có một số khoảng thời gian tồn tại gần nhau, nhưng chúng phục vụ những ngữ cảnh khác nhau. Nhầm lẫn giữa chúng dễ dẫn đến mất dữ liệu khi chuyển state, rò rỉ dữ liệu giữa nhiều flow, xung đột khi mở nhiều tab hoặc giữ thông tin lâu hơn cần thiết.

Sau bài học, bạn có thể:

- Giải thích vòng đời và phạm vi của từng scope do Spring Web Flow cung cấp.
- Phân biệt Web Flow requestScope với Servlet request, và flow/conversation scope với HttpSession.
- Chọn đúng nơi lưu dữ liệu cho form nhiều bước và subflow.
- Truyền dữ liệu giữa flow cha và flow con bằng input/output.
- Tránh xung đột giữa nhiều flow execution và kiểm thử hành vi khi request hoặc session kết thúc.

## 1. Hai hệ thống scope phục vụ hai ngữ cảnh

Spring Web Flow xử lý một hành trình nghiệp vụ qua nhiều request HTTP. Trong mỗi request, framework tạo hoặc khôi phục RequestContext để xử lý event, state và transition. Các biến như `requestScope`, `viewScope`, `flowScope` và `conversationScope` là các vùng dữ liệu mà flow có thể truy cập trong ngữ cảnh đó.

Servlet API cung cấp `HttpServletRequest` cho một request và `HttpSession` cho một phiên người dùng có thể kéo dài qua nhiều request. Servlet request có parameter, header và attribute; session có attribute được chia sẻ giữa các request thuộc cùng phiên.

Có thể tóm tắt sự khác biệt như sau:

| Tiêu chí | Scope của Spring Web Flow | Request/session của Servlet |
| --- | --- | --- |
| Chủ thể quản lý | Flow execution và RequestContext của Spring Web Flow | Servlet container và các đối tượng Servlet API |
| Đơn vị phạm vi | Request, view state, flow session hoặc flow execution | Một HTTP request hoặc một HttpSession |
| Mục tiêu chính | Quản lý dữ liệu theo vòng đời của hành trình flow | Trao đổi dữ liệu trong request và duy trì trạng thái phiên web |
| Phạm vi giữa nhiều flow | Có thể cô lập theo flow session hoặc chia sẻ trong một flow execution | HttpSession thường được dùng chung bởi các request và flow trong cùng phiên người dùng |
| Thời điểm kết thúc | Theo lifecycle của request, view, flow session hoặc root flow execution | Khi request kết thúc, hoặc khi session hết hạn/bị invalidate |
| Cách truy cập | Biến scope trong flow expression và RequestContext | HttpServletRequest, HttpSession hoặc API tích hợp |

Hai hệ thống có thể cùng tồn tại trong một ứng dụng. Ví dụ, một controller Servlet có thể ghi thông báo vào request attribute, trong khi flow đang xử lý giữ bản nháp đơn hàng trong flowScope. Cả hai đều hợp lệ nếu mỗi giá trị được đặt đúng nơi và được đọc trong đúng ngữ cảnh.

Không nên suy ra rằng mọi biến có tên `requestScope` đều là một Servlet request attribute, hoặc `flowScope` là một vùng con của HttpSession có thể truy cập bằng `session.getAttribute`. Hãy dùng API của đúng hệ thống scope; khi cần kết nối hai hệ thống, thực hiện việc chuyển dữ liệu tường minh tại ranh giới tích hợp.

Trong nhóm scope chuẩn của Spring Web Flow không có một `sessionScope` tổng quát tương đương `HttpSession`. `conversationScope` là phạm vi chia sẻ rộng nhất trong một flow execution, nhưng nó vẫn kết thúc khi root flow execution kết thúc. Nếu dữ liệu cần tồn tại ở cấp phiên người dùng và được nhiều flow độc lập sử dụng, hãy truy cập Servlet session qua API tích hợp hoặc lưu dữ liệu trong hồ sơ người dùng.

## 2. Các scope do Spring Web Flow cung cấp

Spring Web Flow cung cấp các scope có vòng đời khác nhau. Phạm vi cụ thể của chúng gắn với quá trình thực thi flow chứ không chỉ với vòng đời của trình duyệt.

| Scope | Vòng đời | Trường hợp sử dụng phù hợp |
| --- | --- | --- |
| `requestScope` | Chỉ trong request hiện tại đang xử lý flow | Dữ liệu tạm chỉ cần trong lần xử lý event hiện tại |
| `flashScope` | Dữ liệu tạm được giữ trong quá trình xử lý flow cho tới điểm pause/render view theo lifecycle | Thông báo hoặc kết quả ngắn hạn cần xuất hiện ở view kế tiếp |
| `viewScope` | Từ lúc vào một view state đến khi rời view state đó | Form backing object, lựa chọn và dữ liệu phục vụ một màn hình |
| `flowScope` | Trong suốt một flow session | Bản nháp hoặc dữ liệu nghiệp vụ riêng của flow hiện tại |
| `conversationScope` | Trong suốt flow execution gốc, chia sẻ giữa các flow session thuộc execution đó | Dữ liệu cần được dùng chung có chủ đích giữa flow cha và các subflow |

### requestScope

`requestScope` phù hợp với dữ liệu chỉ cần trong lần request đang được xử lý. Khi người dùng gửi một event khác ở request tiếp theo, không nên kỳ vọng giá trị cũ còn tồn tại. Ví dụ: một cờ dùng trong action để quyết định nhánh transition hiện tại hoặc một kết quả tính toán chỉ phục vụ lần xử lý đó.

Nó có vòng đời gần với Servlet request, nhưng vẫn là scope của Spring Web Flow trong RequestContext. Nếu cần truyền dữ liệu từ controller vào flow, hãy xác định rõ điểm tích hợp và API được dùng để đọc dữ liệu; đừng dựa vào giả định rằng hai map có cùng namespace.

### flashScope

`flashScope` dành cho dữ liệu ngắn hạn cần đi qua quá trình xử lý hiện tại để hiển thị ở view tiếp theo. Ví dụ, sau khi lưu thành công, flow có thể chuẩn bị thông báo “Đã lưu” để view kế tiếp hiển thị. Dữ liệu flash được framework quản lý và làm sạch theo lifecycle pause/render của flow.

Đây không phải kho lưu dữ liệu nhiều bước. Không đặt toàn bộ form hoặc trạng thái nghiệp vụ vào flashScope với kỳ vọng nó tồn tại xuyên suốt flow.

### viewScope

`viewScope` tồn tại trong thời gian một view state đang hoạt động. Nó thích hợp với model của form, lựa chọn tạm thời hoặc dữ liệu chỉ có ý nghĩa trên màn hình hiện tại. Khi flow rời view state, viewScope tương ứng kết thúc.

Nếu người dùng submit form không hợp lệ và vẫn ở lại cùng view state, dữ liệu phục vụ việc hiển thị lại view có thể tiếp tục được sử dụng theo lifecycle của state. Khi chuyển sang view state khác, không nên trông chờ dữ liệu view cũ tự động còn tồn tại.

### flowScope

`flowScope` tồn tại trong toàn bộ flow session. Đây thường là nơi lưu bản nháp hoặc dữ liệu cần đi qua nhiều state trong cùng một flow, ví dụ thông tin đặt hàng từ bước nhập liệu đến bước xác nhận.

Mỗi flow session có flowScope riêng. Khi flow cha gọi subflow, subflow có flow session và flowScope riêng; biến trong flowScope của cha không tự động trở thành biến trong flowScope của con.

### conversationScope

`conversationScope` tồn tại trong toàn bộ flow execution gốc. Các flow session thuộc cùng execution, bao gồm flow cha và subflow, có thể truy cập dữ liệu chung trong conversationScope.

Scope này hữu ích khi một giá trị thực sự cần được chia sẻ giữa nhiều cấp flow. Tuy nhiên, chia sẻ trực tiếp làm tăng sự phụ thuộc giữa các flow. Nếu chỉ cần chuyển một kết quả từ subflow về cha, input/output của subflow thường thể hiện ý định rõ hơn.

## 3. Servlet request và HttpSession

### Servlet request

Mỗi lần trình duyệt gửi HTTP request, Servlet container tạo một `HttpServletRequest`. Đối tượng này chứa thông tin của request như URL, method, header, parameter và attribute. Request kết thúc sau khi container hoàn tất việc xử lý và trả response.

Có hai khái niệm cần tách biệt:

- **Request parameter** là dữ liệu gửi từ client, thường qua query string hoặc form body. Có thể đọc bằng `getParameter`.
- **Request attribute** là dữ liệu phía server đặt vào request để các thành phần xử lý trong cùng request chia sẻ. Có thể đọc/ghi bằng `getAttribute` và `setAttribute`.

Ví dụ trong controller:

```java
@GetMapping("/booking")
public String showBooking(HttpServletRequest request) {
    request.setAttribute("notice", "Vui lòng kiểm tra thông tin đặt chỗ");
    return "booking";
}
```

Attribute `notice` chỉ tồn tại trong request đang render trang. Nếu người dùng submit form tạo một request mới, attribute đó không tự động tồn tại ở request mới. Nếu cần hiển thị thông báo sau một lần redirect, hãy dùng cơ chế flash attribute của Spring MVC hoặc cơ chế flash phù hợp với flow đang xử lý.

### HttpSession

`HttpSession` là phiên web do Servlet container quản lý. Nó cho phép lưu attribute qua nhiều request thuộc cùng một phiên. Phiên có thể kết thúc khi hết thời gian timeout, khi ứng dụng gọi `invalidate()`, hoặc khi container kết thúc phiên theo chính sách của nó.

Ví dụ:

```java
@PostMapping("/preferences")
public String savePreferences(
        HttpServletRequest request,
        @RequestParam String locale) {

    request.getSession().setAttribute("preferredLocale", locale);
    return "redirect:/profile";
}
```

Giá trị `preferredLocale` có thể được đọc ở request sau trong cùng HttpSession. Các tab của cùng trình duyệt thường gửi cùng session cookie, vì vậy cùng truy cập một vùng session. Điều này thuận tiện cho thông tin dùng chung ở cấp phiên người dùng, nhưng cũng tạo rủi ro khi lưu dữ liệu riêng cho từng wizard hoặc flow execution vào một key cố định.

Ví dụ, nếu hai tab cùng chạy hai flow đặt hàng nhưng cả hai đều ghi `session.setAttribute("currentOrder", ...)`, dữ liệu của tab này có thể ghi đè dữ liệu của tab kia. HttpSession không tự phân vùng dữ liệu theo flow execution.

## 4. So sánh flowScope, conversationScope và HttpSession

Đây là điểm dễ nhầm nhất khi xây dựng wizard nhiều bước:

| Tiêu chí | `flowScope` | `conversationScope` | Servlet `HttpSession` |
| --- | --- | --- | --- |
| Phạm vi | Một flow session | Một flow execution gốc | Một phiên người dùng |
| Qua nhiều request | Có, khi flow session tiếp tục | Có, khi execution tiếp tục | Có, cho đến khi session kết thúc |
| Chia sẻ với subflow | Không tự động; subflow có flowScope riêng | Có, nếu thuộc cùng execution | Có thể được mọi flow trong cùng HttpSession truy cập |
| Cách kết thúc | Khi flow session kết thúc | Khi root flow execution kết thúc | Khi timeout hoặc invalidate |
| Cô lập nhiều wizard | Tách biệt theo flow session | Tách biệt theo execution | Cần tự quản lý key và đồng bộ |
| Ví dụ | Bản nháp địa chỉ của flow address | Mã tương quan hoặc dữ liệu chung giữa checkout và subflow address | Locale người dùng hoặc tùy chọn giao diện |

Một flow execution có thể kéo dài qua nhiều HTTP request. Vì vậy, flowScope và conversationScope có thể giữ dữ liệu qua nhiều request mà không cần lưu trực tiếp vào một key do ứng dụng tự đặt trong HttpSession.

Cấu hình execution repository có thể sử dụng HttpSession để lưu hoặc tra cứu trạng thái flow execution. Điều đó không làm cho HttpSession và các scope của Web Flow trở thành một khái niệm. Repository là cơ chế lưu trữ execution; HttpSession là phiên Servlet; flowScope/conversationScope là vùng dữ liệu có vòng đời do Web Flow định nghĩa.

Khi root flow kết thúc, conversationScope kết thúc theo execution đó, kể cả khi HttpSession của người dùng vẫn còn hiệu lực. Ngược lại, khi HttpSession hết hạn, ứng dụng có thể không còn khả năng khôi phục execution được lưu trong session repository. Cần xử lý trường hợp này như một tình huống hết phiên hoặc execution không còn hợp lệ.

## 5. Chọn scope cho một wizard nhiều bước

Giả sử ứng dụng có flow đặt hàng gồm các bước nhập thông tin, chọn địa chỉ giao hàng, xác nhận và hoàn tất. Một lựa chọn scope hợp lý có thể là:

| Dữ liệu | Scope đề xuất | Lý do |
| --- | --- | --- |
| Lỗi validation của lần submit hiện tại | requestScope hoặc message context phù hợp | Chỉ phục vụ xử lý và hiển thị của request hiện tại |
| Lựa chọn tạm trên màn hình chọn phương thức giao hàng | viewScope | Chỉ có ý nghĩa khi view state này còn hoạt động |
| Bản nháp đơn hàng | flowScope | Cần tồn tại qua nhiều state trong flow checkout |
| Thông tin địa chỉ được subflow trả về | Output của subflow, sau đó lưu vào flowScope của cha | Truyền qua ranh giới flow một cách tường minh |
| Mã tham chiếu cần dùng chung giữa checkout và subflow | conversationScope nếu thật sự cần | Cả hai thuộc cùng flow execution |
| Ngôn ngữ giao diện của người dùng | HttpSession hoặc hồ sơ người dùng | Có ý nghĩa ở cấp phiên/người dùng, không chỉ một flow |
| Thông báo ngắn sau khi chuyển state | flashScope | Chỉ cần hiển thị ở view tiếp theo |

Ví dụ, flow checkout giữ bản nháp đơn hàng trong flowScope:

```xml
<flow>
    <on-start>
        <evaluate expression="bookingService.createDraft()"
                  result="flowScope.booking"/>
    </on-start>

    <view-state id="editBooking" view="booking/edit">
        <transition on="next" to="confirmBooking"/>
    </view-state>

    <view-state id="confirmBooking" view="booking/confirm">
        <transition on="back" to="editBooking"/>
        <transition on="finish" to="completed">
            <evaluate expression="bookingService.confirm(flowScope.booking)"/>
        </transition>
    </view-state>

    <end-state id="completed"/>
</flow>
```

Bản nháp `booking` được giữ qua các state trong cùng flow session. Khi người dùng rời flow và execution kết thúc, flowScope cũng kết thúc. Dịch vụ nghiệp vụ vẫn cần lưu dữ liệu chính thức vào kho lưu trữ phù hợp; flowScope chỉ là nơi giữ trạng thái phục vụ quá trình tương tác.

## 6. Truyền dữ liệu giữa flow cha và subflow

Khi một flow gọi subflow, đừng dùng HttpSession như một hộp trung gian mặc định để chuyển dữ liệu. Hãy khai báo input và output để thể hiện rõ hợp đồng giữa hai flow.

Flow cha truyền mã khách hàng vào subflow:

```xml
<subflow-state id="editAddress" subflow="address">
    <input name="customerId" value="flowScope.customerId"/>

    <transition on="addressSaved" to="confirmOrder">
        <evaluate expression="currentEvent.attributes.address"
                  result="flowScope.shippingAddress"/>
    </transition>
</subflow-state>
```

Flow con nhận input và trả địa chỉ khi kết thúc:

```xml
<flow>
    <input name="customerId" type="long" required="true"/>

    <!-- Các state nhập và xác nhận địa chỉ -->

    <end-state id="addressSaved">
        <output name="address" value="flowScope.address"/>
    </end-state>
</flow>
```

Flow con lưu dữ liệu riêng trong flowScope của nó. Khi kết thúc, output được công bố trong event trả về; flow cha đọc output trong transition và ghi vào flowScope của cha. Đây là cách truyền dữ liệu có ranh giới rõ ràng, giúp hai flow ít phụ thuộc vào tên biến nội bộ của nhau.

Nếu dữ liệu cần được nhiều cấp flow đọc và cập nhật trong cùng execution, conversationScope là một lựa chọn. Tuy nhiên, cần quy định flow nào được phép cập nhật, lúc nào dữ liệu trở thành chính thức và cách xử lý khi một nhánh subflow bị hủy. Tránh để nhiều flow cùng sửa một object dùng chung mà không có quy tắc nhất quán.

## 7. Tương tác với Servlet session từ Spring Web Flow

Có trường hợp ứng dụng cần đọc hoặc ghi một giá trị ở cấp Servlet session, chẳng hạn tùy chọn ngôn ngữ hoặc một thuộc tính phục vụ tích hợp legacy. Spring Web Flow cung cấp ExternalContext để truy cập môi trường web bên ngoài flow.

Trong code xử lý có RequestContext, có thể thao tác với session map của ExternalContext:

```java
Object locale = context.getExternalContext()
                       .getSessionMap()
                       .get("preferredLocale");

context.getExternalContext()
       .getSessionMap()
       .put("preferredLocale", "vi");
```

Đây là dữ liệu ở cấp HttpSession, vì vậy các request và flow khác trong cùng phiên có thể nhìn thấy nó. Chỉ dùng cách này khi dữ liệu thật sự có ý nghĩa ở cấp phiên người dùng. Nếu dữ liệu chỉ thuộc wizard hiện tại, hãy dùng flowScope hoặc conversationScope.

Tương tự, ExternalContext có API làm việc với request hiện tại. Khi dùng request map hoặc session map, cần kiểm tra chính xác hợp đồng của phiên bản Spring Web Flow đang chạy và phân biệt map của ExternalContext với các biến scope trong flow expression. Không lưu đối tượng request/response hoặc dữ liệu chỉ hợp lệ trong một request vào flowScope hay HttpSession.

## 8. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lưu bản nháp wizard vào một key cố định trong HttpSession | Hai tab hoặc hai flow execution có thể ghi đè dữ liệu của nhau | Dùng flowScope; nếu cần chia sẻ giữa subflow, dùng input/output hoặc conversationScope |
| Đặt dữ liệu nhiều bước trong requestScope | Dữ liệu biến mất sau request hiện tại | Chuyển dữ liệu có vòng đời dài hơn sang viewScope hoặc flowScope |
| Dùng viewScope cho dữ liệu cần tồn tại sau khi rời view state | Dữ liệu không còn sau transition | Dùng flowScope hoặc truyền output sang flow cha |
| Nghĩ flowScope của cha tự động nhìn thấy ở subflow | Subflow không tìm thấy dữ liệu mong đợi hoặc dùng nhầm dữ liệu | Khai báo input/output hoặc dùng conversationScope có chủ đích |
| Dùng conversationScope cho mọi dữ liệu | Các flow phụ thuộc ngầm, khó xác định quyền sở hữu và cập nhật | Chỉ chia sẻ dữ liệu thật sự cần thiết; ưu tiên input/output |
| Lưu object lớn hoặc không thể serialize vào session | Tăng bộ nhớ, lỗi khi passivation/replication hoặc lưu trữ execution | Lưu ID và dữ liệu tối thiểu; tải lại object từ service khi cần |
| Giữ dữ liệu nhạy cảm trong HttpSession quá lâu | Tăng phạm vi ảnh hưởng nếu session bị lộ hoặc không được dọn đúng lúc | Giảm dữ liệu lưu, đặt thời hạn và xóa khi không còn cần |
| Cho rằng kết thúc flow cũng đồng nghĩa HttpSession kết thúc | Dữ liệu session vẫn tồn tại ngoài vòng đời flow | Dọn thuộc tính session riêng nếu ứng dụng đã chủ động lưu chúng |

Đặc biệt, không nên lưu `HttpServletRequest`, `HttpServletResponse`, stream, connection hoặc đối tượng gắn với một request vào flowScope hay session. Những đối tượng này có vòng đời ngắn, thường không thể serialize và không phù hợp để khôi phục ở request sau. Hãy lưu dữ liệu thuần, ID hoặc giá trị cần thiết rồi gọi service để lấy tài nguyên mới khi xử lý request tiếp theo.

## 9. Kiểm thử vòng đời scope

Kiểm thử cần chứng minh dữ liệu tồn tại đúng phạm vi và biến mất khi vòng đời kết thúc. Một số ca kiểm thử quan trọng:

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Request kế tiếp | Ghi dữ liệu vào requestScope, gửi request tiếp theo | Giá trị request trước không còn |
| View state tiếp tục | Submit form không hợp lệ và ở lại cùng view state | Dữ liệu view cần thiết vẫn phục vụ việc render lại theo lifecycle |
| Rời view state | Chuyển từ view state A sang B | Dữ liệu riêng của view state A không được coi là dữ liệu sống xuyên flow |
| Nhiều state trong cùng flow | Ghi vào flowScope ở state đầu, đọc ở state sau | Giá trị vẫn tồn tại trong cùng flow session |
| Subflow riêng | Flow cha ghi vào flowScope rồi gọi subflow | Subflow không tự động có biến flowScope riêng của cha |
| Truyền output | Subflow kết thúc và xuất dữ liệu | Flow cha đọc được output từ event và lưu vào scope của cha |
| Conversation | Flow cha và subflow đọc/ghi một giá trị conversationScope | Các flow session cùng execution nhìn thấy giá trị dùng chung theo thiết kế |
| Hai flow execution cùng session | Mở hai wizard trong hai tab | flowScope và conversationScope của hai execution không bị trộn |
| Session hết hạn | Hết hạn HttpSession hoặc xóa execution lưu trong session repository | Ứng dụng xử lý execution không còn hợp lệ và hướng dẫn bắt đầu lại |
| Root flow kết thúc | Hoàn tất hoặc hủy flow gốc | flowScope của session kết thúc và conversationScope của execution được giải phóng theo lifecycle |

Ngoài kiểm thử flow bằng bộ công cụ Spring Web Flow, nên có kiểm thử tích hợp qua Spring MVC để xác minh request mapping, session cookie, repository và hành vi khi nhiều request được gửi liên tiếp. Với ứng dụng hỗ trợ nhiều tab, hãy chạy hai execution song song trong cùng HttpSession để phát hiện lỗi dùng chung key.

## 10. Quy tắc lựa chọn scope

Có thể dùng trình tự câu hỏi sau khi quyết định nơi lưu một giá trị:

1. Giá trị chỉ cần trong lần xử lý request hiện tại? Dùng requestScope hoặc cơ chế request tương ứng.
2. Giá trị chỉ phục vụ view state hiện tại? Dùng viewScope.
3. Giá trị cần qua nhiều state trong một flow session? Dùng flowScope.
4. Giá trị cần được chia sẻ giữa flow cha và subflow trong cùng execution? Ưu tiên input/output; nếu nhiều cấp thực sự cần cùng truy cập, cân nhắc conversationScope.
5. Giá trị có ý nghĩa ở cấp người dùng và cần tồn tại giữa nhiều flow độc lập? Cân nhắc HttpSession hoặc lưu trong hồ sơ người dùng.
6. Giá trị phải tồn tại lâu dài qua nhiều phiên đăng nhập hoặc thiết bị? Lưu ở tầng nghiệp vụ/cơ sở dữ liệu; không dùng flowScope hay HttpSession làm kho dữ liệu lâu dài.

Quyết định này nên dựa trên **ai sở hữu dữ liệu**, **ai cần đọc/ghi**, và **khi nào dữ liệu phải được xóa**. Thời gian tồn tại chỉ là một phần của thiết kế; phạm vi chia sẻ cũng quan trọng không kém.

## 11. Bài tập thực hành

Xây dựng một wizard đặt hàng trong Spring Web Flow gồm flow gốc `checkout` và subflow `address`. Người dùng có thể mở hai tab để thực hiện hai đơn hàng khác nhau.

1. Đặt bản nháp đơn hàng trong flowScope của `checkout`. Giải thích vì sao không lưu vào một key `currentOrder` cố định trong HttpSession.
2. Đặt lựa chọn tạm thời của màn hình nhập địa chỉ trong viewScope của `address`.
3. Truyền `customerId` từ flow cha sang subflow bằng input và trả địa chỉ đã xác nhận bằng output.
4. Tạo một giá trị correlation ID cần dùng chung trong cả checkout và address. So sánh cách dùng conversationScope với việc truyền giá trị qua input/output.
5. Lưu tùy chọn ngôn ngữ trong HttpSession và chứng minh nó có thể được đọc ở request tiếp theo trong cùng phiên.
6. Viết test cho request kế tiếp, rời view state, kết thúc subflow, hai execution chạy song song và session hết hạn.

**Tiêu chí hoàn thành:** người học phân biệt đúng năm scope của Web Flow với Servlet request và HttpSession; chọn được scope cho từng loại dữ liệu; giải thích được vì sao hai wizard trong cùng HttpSession vẫn cần dữ liệu flow riêng; và chứng minh bằng kiểm thử rằng dữ liệu được tạo, chia sẻ và dọn dẹp theo đúng vòng đời.

## Kết luận

Scope của Spring Web Flow quản lý dữ liệu theo vòng đời của request, view state, flow session và flow execution. Servlet request và HttpSession quản lý dữ liệu theo vòng đời của request web và phiên người dùng. requestScope có thời gian tồn tại gần với một Servlet request; flowScope và conversationScope cho phép giữ dữ liệu qua nhiều request nhưng được cô lập theo flow session hoặc execution. HttpSession rộng hơn và có thể được chia sẻ giữa nhiều flow trong cùng phiên. Khi chọn scope dựa trên quyền sở hữu, phạm vi chia sẻ và thời điểm kết thúc, ứng dụng có thể giữ dữ liệu wizard ổn định, tránh xung đột nhiều tab và xử lý subflow rõ ràng.

