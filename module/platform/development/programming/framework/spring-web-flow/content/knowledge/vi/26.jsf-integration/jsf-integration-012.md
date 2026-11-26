# Nhúng flow vào một trang theo cơ chế được hỗ trợ

Trong chương **Tích hợp JSF**, Spring Web Flow có thể điều phối một hành trình nhiều bước và hiển thị các view của hành trình đó bên trong giao diện JSF của ứng dụng. Cơ chế nhúng flow cho phép một trang chủ chứa một vùng tương tác do flow quản lý, ví dụ vùng chọn địa chỉ, cấu hình sản phẩm hoặc tìm kiếm lịch hẹn. Người dùng tiếp tục làm việc trong trang hiện tại trong khi flow xử lý state, event, validation và dữ liệu của phần tương tác được nhúng.

Module `SPRING_WEB_FLOW` tập trung mô hình hóa hành trình web nhiều bước qua state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên; tích hợp Spring MVC; kiểm thử và phục hồi luồng khi có lỗi. Khi tích hợp JSF, cần hiểu rõ ranh giới giữa trang chủ và flow được nhúng: trang chủ sở hữu bố cục tổng thể, còn flow sở hữu vòng đời thực thi và điều hướng của phần công việc mà nó đảm nhiệm.

## 1. Nhúng flow giải quyết vấn đề gì?

Giả sử trang chỉnh sửa hồ sơ khách hàng có một vùng để tìm và chọn địa chỉ giao hàng. Vùng này có thể cần nhiều bước:

1. Tìm địa chỉ theo mã bưu chính hoặc từ khóa.
2. Chọn một kết quả.
3. Xác nhận địa chỉ và trả lựa chọn cho trang hồ sơ.

Nếu xây dựng toàn bộ bằng các JSF view riêng, trang chủ phải tự quản lý các bước, trạng thái tìm kiếm, validation và kết quả. Nếu nhúng một flow, phần chọn địa chỉ có thể được mô hình hóa thành một flow độc lập. Trang chủ chỉ cần cung cấp dữ liệu đầu vào cần thiết và tiếp nhận kết quả khi flow kết thúc theo hợp đồng tích hợp.

Một flow được nhúng vẫn là một lần thực thi flow có state và execution context riêng. Nó có thể chuyển giữa các state, nhận event, gọi action và kết thúc. Phần giao diện của flow được đặt trong vùng hiển thị của trang chủ theo cơ chế mà Spring Faces/JSF integration hỗ trợ.

Nhúng flow hữu ích khi phần tương tác có ý nghĩa riêng, nhiều bước hoặc có thể tái sử dụng ở nhiều trang. Một hộp thoại chỉ có một trường nhập đơn giản thường không cần thêm flow; component JSF thông thường có thể đủ.

## 2. Phân biệt nhúng flow, include view và subflow

Ba cách tổ chức này có mục đích khác nhau:

| Cơ chế | Điều được tái sử dụng hoặc kết hợp | Có flow execution riêng? | Khi phù hợp |
|---|---|---:|---|
| Include JSF view, ví dụ `ui:include` | Nội dung Facelets và component tree | Không tự tạo flow execution | Chia nhỏ bố cục hoặc tái sử dụng một đoạn giao diện |
| Nhúng flow vào trang | Một hành trình flow hiển thị trong vùng của trang chủ | Có | Một vùng tương tác nhiều bước cần state, event và vòng đời riêng |
| Subflow | Một flow con được gọi như một phần của flow cha | Có flow session con trong execution của flow cha | Chia nhỏ một hành trình lớn thành các phần nghiệp vụ có hợp đồng input/output |

`ui:include` chỉ ghép nội dung view. Nó không tự cung cấp state machine, execution key, transition hay cơ chế kết thúc flow. Subflow là quan hệ điều phối giữa các flow definition trong cùng hành trình cha-con. Nhúng flow vào trang tập trung vào việc đặt một flow execution trong giao diện JSF đang hiển thị.

Không nên dùng include để giả lập một flow nhiều bước bằng các biến view rời rạc. Ngược lại, cũng không cần tạo flow cho mọi đoạn giao diện tĩnh. Chọn cơ chế theo vòng đời và trách nhiệm của phần tương tác.

## 3. Cấu trúc tích hợp JSF và Spring Web Flow

Trong ứng dụng JSF, request đi qua servlet và JSF lifecycle. Spring Faces cung cấp các thành phần tích hợp để flow tham gia vào vòng đời xử lý JSF, duy trì ngữ cảnh cần thiết và phối hợp navigation với flow engine. Một cấu hình JSF thường cần đăng ký `FlowPhaseListener` trong `faces-config.xml` cùng các bean và flow executor mà ứng dụng sử dụng.

Ví dụ đăng ký phase listener:

```xml
<lifecycle>
    <phase-listener>
        org.springframework.faces.webflow.FlowPhaseListener
    </phase-listener>
</lifecycle>
```

Đoạn cấu hình minh họa cách Spring Faces tham gia vào JSF lifecycle. Vị trí và cách cấu hình Spring context, flow registry, flow executor, view handler hoặc navigation handler phụ thuộc phiên bản JSF và Spring Web Flow. Cần dùng đúng artifact Spring Faces tương thích với bộ phiên bản Spring Framework, Spring Web Flow và JSF của ứng dụng.

Khi nhúng flow, component hoặc tag nhúng do bản Spring Faces hỗ trợ đóng vai trò vùng chứa/điểm khởi chạy flow. Nó kết nối flow được chỉ định với trang JSF hiện tại theo giao thức của framework. Không tự tạo execution bằng cách ghép URL, chèn execution key hoặc gọi trực tiếp servlet API trong Facelets.

Ví dụ Facelets dưới đây minh họa ý tưởng sử dụng tag nhúng của Spring Faces; tên namespace, tag và thuộc tính phải được đối chiếu với tag library descriptor của đúng phiên bản đang dùng:

```xhtml
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:h="http://java.sun.com/jsf/html"
      xmlns:ui="http://java.sun.com/jsf/facelets"
      xmlns:flow="http://www.springframework.org/tags/faces">
<h:body>
    <h:form id="customerForm">
        <h:outputText value="Chỉnh sửa hồ sơ khách hàng" />

        <!-- Vùng nhúng flow chọn địa chỉ theo component của Spring Faces. -->
        <flow:embed flowId="address-selection" />
    </h:form>
</h:body>
</html>
```

Đoạn Facelets cho thấy vị trí của vùng flow trong trang chủ. Không coi đây là một component JSF tự định nghĩa hoặc tự thay thế bằng `ui:include`; cú pháp thực tế cần khớp phiên bản Spring Faces được triển khai. Nếu phiên bản đang dùng cung cấp API/component khác cho embedded flow, hãy sử dụng đúng hợp đồng của phiên bản đó thay vì sao chép tag minh họa một cách máy móc.

## 4. Flow được nhúng vẫn có flow definition riêng

Flow definition mô tả các state và event của phần tương tác. Ví dụ flow chọn địa chỉ có thể gồm state tìm kiếm, state xem kết quả và end state trả lựa chọn:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="customerId" />

    <var name="addressSearch" class="com.example.AddressSearchForm" />

    <view-state id="searchAddress"
                view="address/search"
                model="addressSearch">
        <transition on="search" to="loadAddresses" />
        <transition on="cancel" to="cancelled" />
    </view-state>

    <action-state id="loadAddresses">
        <evaluate expression="addressService.search(customerId, addressSearch)"
                  result="flowScope.addresses" />
        <transition on="success" to="chooseAddress" />
        <transition on="empty" to="searchAddress" />
    </action-state>

    <view-state id="chooseAddress" view="address/results">
        <transition on="select" to="selected" />
        <transition on="back" to="searchAddress" />
    </view-state>

    <end-state id="selected">
        <output name="addressId" value="flowScope.selectedAddressId" />
    </end-state>

    <end-state id="cancelled" />
</flow>
```

Ví dụ tập trung vào cấu trúc flow và hợp đồng kết quả. Trong ứng dụng thật, cần bổ sung cách gán `selectedAddressId`, validation, kiểm tra quyền sở hữu địa chỉ, xử lý lỗi dịch vụ và cấu hình view phù hợp. Flow được nhúng không nên tự tin tưởng `customerId` do trang chủ truyền vào; service phải xác minh người dùng hiện tại được phép truy cập khách hàng đó.

Tách flow definition khỏi trang chủ giúp phần chọn địa chỉ có thể được tái sử dụng. Tuy nhiên, flow chỉ nên công bố những input và output mà trang chủ cần; không để trang chủ phụ thuộc vào tên các state nội bộ như `searchAddress` hoặc `chooseAddress` nếu không cần thiết.

## 5. Truyền dữ liệu vào flow và nhận kết quả

Một flow nhúng thường cần dữ liệu đầu vào từ trang chứa nó, ví dụ ID khách hàng hoặc ngữ cảnh nghiệp vụ. Kết quả có thể là ID địa chỉ được chọn, một mã kết quả hoặc một DTO nhỏ. Hãy định nghĩa hợp đồng input/output rõ ràng để trang chủ không phải đọc trực tiếp flow scope nội bộ.

Flow definition có thể khai báo input:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="customerId" />

    <!-- Các state xử lý lựa chọn địa chỉ -->

    <end-state id="selected">
        <output name="addressId" value="flowScope.selectedAddressId" />
    </end-state>
</flow>
```

Trang chủ truyền giá trị vào theo API của component/embedded-flow integration trong phiên bản Spring Faces. Khi flow kết thúc, output được trả qua cơ chế callback hoặc kết quả kết thúc mà tích hợp đó hỗ trợ. Không tự suy đoán tên attribute, method callback hoặc expression của component; chúng cần được lấy từ tài liệu/API đúng phiên bản.

Một hợp đồng kết quả tốt có các đặc điểm:

- Input chỉ gồm dữ liệu tối thiểu để khởi chạy flow.
- Flow kiểm tra quyền và tải dữ liệu thật từ service/repository.
- Output có tên và kiểu ổn định, thường là ID hoặc DTO nhỏ.
- Kết quả hủy, hoàn tất và lỗi được phân biệt rõ.
- Trang chủ không đọc hoặc sửa trực tiếp các biến trong `flowScope` của flow nhúng.

Ví dụ, flow chọn địa chỉ trả `addressId`. Trang chủ dùng ID đó để tải lại địa chỉ theo quyền của người dùng và cập nhật form khách hàng. Cách này tránh giữ một entity detached hoặc một object graph lớn qua ranh giới giữa hai phần giao diện.

## 6. Vòng đời và phạm vi trạng thái

Trang chủ JSF và flow được nhúng có thể cùng tồn tại trong một HTTP session, nhưng không có nghĩa chúng dùng chung mọi trạng thái. Flow execution có scope riêng như `requestScope`, `viewScope`, `flowScope` và `conversationScope` theo cấu hình. Trang JSF có view state riêng được quản lý bởi JSF lifecycle.

| Dữ liệu | Nơi phù hợp | Lý do |
|---|---|---|
| Giá trị hiển thị riêng của trang chủ | Model/bean của trang JSF | Thuộc giao diện và vòng đời view chủ |
| Từ khóa tìm kiếm trong flow nhúng | Model của view state hoặc `flowScope` | Thuộc hành trình chọn địa chỉ |
| Kết quả tìm kiếm cần qua nhiều bước | `flowScope` hoặc repository theo kích thước/vòng đời | Flow cần dùng lại khi chuyển state |
| ID khách hàng đầu vào | Flow input sau khi xác minh quyền | Là dữ liệu khởi tạo hợp đồng flow |
| ID địa chỉ được chọn | Flow output khi kết thúc | Là kết quả trả cho trang chủ |
| Dữ liệu cần tồn tại sau khi flow kết thúc | Kho dữ liệu nghiệp vụ | Flow scope kết thúc theo lifecycle của execution |

Không đặt đối tượng `FacesContext`, `HttpServletRequest`, response hoặc một JPA entity đang được quản lý vào scope dài hạn. Các đối tượng này có vòng đời phụ thuộc request, JSF lifecycle hoặc persistence context. Giữ DTO và ID giúp flow dễ khôi phục và kiểm thử hơn.

Nếu trang chủ mở nhiều vùng flow hoặc người dùng mở cùng trang trong nhiều tab, mỗi flow execution cần được nhận diện độc lập. Không dùng một biến session chung như `currentAddressFlow` để lưu trạng thái có thể bị ghi đè giữa các lần thực thi.

## 7. Điều hướng bên trong vùng nhúng

Các event của flow nhúng phải được gửi tới đúng execution. Link hoặc command component của JSF cần tuân theo cơ chế navigation của Spring Faces/flow integration để giữ execution context. Không dùng một `h:commandButton` thông thường rồi tự chuyển URL sang view state tiếp theo nếu flow phải kiểm soát transition.

Trong các view thuộc flow, dùng component command/navigation được hỗ trợ bởi Spring Faces hoặc cơ chế event mà phiên bản flow integration quy định. Event như `search`, `select`, `back` và `cancel` phải khớp với transition trong flow definition. Khi gửi form, cần bảo đảm request được xử lý trong đúng JSF lifecycle và flow execution.

Nếu một event chỉ cập nhật dữ liệu của vùng nhúng, hãy kiểm tra cách tích hợp hỗ trợ partial processing/rendering. Không mặc định rằng mọi JSF Ajax request đều tương thích với flow execution nếu thiếu phase listener, view state hoặc cơ chế giữ execution key cần thiết.

## 8. Ajax và cập nhật một phần trang

Một lợi ích thường mong muốn khi nhúng flow là chỉ cập nhật vùng tương tác mà không render lại toàn bộ trang. Với JSF Ajax, cần phân biệt:

- **Execute/process:** những component nào được decode, validate và cập nhật model trong request.
- **Render/update:** những component nào được render lại trong response.
- **Flow event:** event nào được chuyển tới flow execution và transition nào sẽ xử lý event đó.

Ajax partial processing của JSF và transition của Spring Web Flow là hai tầng phối hợp. Nếu request chỉ process một phần form, các giá trị cần cho validation hoặc action phải nằm trong vùng được xử lý. Nếu flow chuyển sang state khác, component vùng nhúng cần render lại đúng view tương ứng.

Không render đồng thời cùng một vùng component từ hai cơ chế điều hướng khác nhau. Kiểm tra client ID/naming container của JSF, đặc biệt khi component flow nằm bên trong form hoặc naming container khác. Nếu dùng nhiều form lồng nhau, cần tuân thủ quy tắc HTML/JSF; không đặt một `h:form` bên trong form cha vì HTML form không được lồng nhau hợp lệ.

## 9. Bảo mật khi nhúng flow

Flow nhúng là một phần của giao diện nhưng vẫn nhận dữ liệu từ request và phải tuân thủ các ranh giới bảo mật như mọi endpoint khác.

- Xác minh quyền trên input như `customerId` hoặc `accountId` ở service layer.
- Không coi việc flow xuất hiện trong trang đã chứng minh người dùng có quyền truy cập dữ liệu.
- Giữ CSRF protection và cơ chế bảo vệ postback của JSF/Spring Security theo cấu hình ứng dụng.
- Không đưa execution key hoặc dữ liệu nhạy cảm vào URL, log hoặc HTML tùy tiện.
- Giới hạn form binding bằng DTO và danh sách property được phép.
- Kiểm tra quyền ở từng action có side effect, kể cả event được gửi trực tiếp hoặc lặp lại.
- Khi flow kết thúc hoặc hết hạn, xử lý output và dữ liệu còn lại theo vòng đời được định nghĩa.

Execution key giúp định vị lần thực thi, không phải token xác thực hoặc quyền sở hữu tài nguyên. Người dùng có thể gửi lại một request cũ; service phải bảo đảm thao tác không vượt quyền và side effect quan trọng có tính idempotent.

## 10. Xử lý lỗi và kết thúc flow nhúng

Flow nhúng cần định nghĩa kết quả hoàn tất, hủy và lỗi. Trang chủ phải biết cách tiếp tục khi flow kết thúc bình thường, bị hủy hoặc không thể khôi phục execution.

| Tình huống | Hành vi nên có |
|---|---|
| Người dùng chọn thành công | Flow trả output theo hợp đồng; trang chủ cập nhật model và vùng hiển thị liên quan |
| Người dùng hủy | Flow kết thúc với kết quả hủy; trang chủ giữ dữ liệu cũ hoặc đóng vùng nhúng theo yêu cầu |
| Không tìm thấy kết quả | Flow hiển thị thông báo và cho tìm lại hoặc kết thúc có chủ đích |
| Dịch vụ tìm kiếm timeout | Hiển thị lỗi có thể thử lại; không làm mất toàn bộ trang chủ |
| Flow execution hết hạn | Hiển thị thông báo an toàn và cho khởi chạy lại vùng tương tác |
| Output không hợp lệ hoặc thiếu | Trang chủ kiểm tra hợp đồng và không áp dụng dữ liệu thiếu |

Không giả định flow nhúng luôn kết thúc bằng output thành công. End state có thể có kết quả khác nhau; trang chủ phải phân biệt chúng. Nếu flow bị lỗi ở tầng execution/repository, callback kết thúc bình thường có thể không được gọi. Trang chủ cần có cơ chế hiển thị trạng thái hết hạn hoặc lỗi chung dựa trên khả năng tích hợp của phiên bản.

Các thao tác ghi dữ liệu quan trọng nên nằm trong service/domain layer với transaction. Nếu flow kết thúc nhưng response bị mất, người dùng có thể gửi lại thao tác. Dùng idempotency key hoặc kiểm tra trạng thái nghiệp vụ để tránh tạo bản ghi trùng.

## 11. Kiểm thử flow được nhúng trong JSF page

Kiểm thử cần bao phủ cả flow execution lẫn cách nó được đặt trong JSF lifecycle và trang chủ. Một flow chạy độc lập đúng chưa đủ chứng minh nó nhúng và render đúng trong trang.

| Kịch bản | Điều cần xác minh |
|---|---|
| Render trang chủ lần đầu | Component nhúng khởi tạo/hiển thị flow đúng flow ID |
| Truyền input | Flow nhận đúng ID hoặc dữ liệu đầu vào và service kiểm tra quyền |
| Gửi event trong vùng nhúng | Event được gửi tới đúng execution và transition tương ứng chạy |
| Validation lỗi | Flow giữ view state của vùng nhúng; trang chủ vẫn giữ trạng thái cần thiết |
| Chọn một kết quả | Flow kết thúc với output đúng hợp đồng; trang chủ nhận và xác minh output |
| Hủy flow | Trang chủ xử lý kết quả hủy theo thiết kế |
| Ajax partial request | Chỉ vùng cần thiết được render lại; JSF lifecycle và flow execution vẫn đồng bộ |
| Hai flow nhúng hoặc nhiều tab | Execution và scope không bị trộn |
| Flow hết hạn | Người dùng nhận thông báo và có thể khởi chạy lại an toàn |
| Request giả mạo hoặc lặp | CSRF, authorization và idempotency được áp dụng |

Có thể kiểm thử flow bằng test support của Spring Web Flow để khởi chạy execution, gửi event và kiểm tra state/output. Với JSF integration, cần thêm kiểm thử tích hợp qua servlet/JSF lifecycle hoặc kiểm thử view/component phù hợp với stack của ứng dụng. API test cụ thể phụ thuộc phiên bản JSF và Spring Faces.

Một bộ kiểm thử nên có ít nhất một đường đi thành công, một đường validation thất bại, một đường hủy và một trường hợp flow execution hết hạn. Khi kiểm tra output, xác minh trang chủ chỉ áp dụng ID hoặc DTO hợp lệ và tải lại dữ liệu theo quyền, thay vì tin toàn bộ object được trả về.

## 12. Lỗi tích hợp thường gặp

### Dùng `ui:include` và cho rằng flow đã được nhúng

Include chỉ ghép Facelets. Nó không tự khởi tạo flow execution hoặc điều phối event. Dùng cơ chế embedding do Spring Faces/phiên bản đang triển khai hỗ trợ.

### Tự ghép URL hoặc execution key

Execution key và URL có thể thay đổi theo request và cách repository lưu execution. Dùng component hoặc API flow integration để tạo request đúng execution.

### Dùng chung bean trạng thái giữa nhiều flow

Một bean singleton có field mutable lưu từ khóa hoặc kết quả tìm kiếm có thể làm lẫn dữ liệu giữa người dùng. Dùng flow scope/view scope hoặc bean có scope phù hợp với execution.

### Trả entity hoặc object lớn về trang chủ

Output nên là hợp đồng nhỏ. Trả entity detached có thể mang theo lazy proxy, dữ liệu thừa và ràng buộc persistence. Trả ID hoặc DTO nhỏ rồi tải lại trong service.

### Bỏ qua JSF lifecycle

Nếu flow event được gửi qua component không tham gia cơ chế tích hợp, request có thể không được xử lý đúng phase hoặc mất execution context. Dùng component/phase listener tương thích và kiểm thử postback thực tế.

### Nhầm flow nhúng với subflow

Subflow thuộc một flow cha và kết thúc bằng event/output về cha. Flow nhúng được đặt trong trang JSF để cung cấp một vùng tương tác. Có thể dùng subflow bên trong flow nhúng, nhưng hai khái niệm không thay thế nhau.

### Không xử lý kết quả hủy hoặc hết hạn

Trang chủ chỉ xử lý trường hợp thành công khiến trạng thái giao diện bị treo khi người dùng hủy hoặc execution hết hạn. Định nghĩa rõ mọi kết quả kết thúc và trạng thái phục hồi.

## 13. Checklist trước khi đưa flow vào trang JSF

Trước khi triển khai, hãy xác nhận:

1. Phần tương tác có đủ phức tạp để cần flow execution riêng hay chỉ là một đoạn view tĩnh?
2. Phiên bản Spring Faces đang dùng cung cấp cơ chế/component nhúng nào và tag/API có đúng với phiên bản đó không?
3. `FlowPhaseListener` và các thành phần tích hợp JSF/flow đã được đăng ký đúng chưa?
4. Flow definition có input/output rõ ràng, tối thiểu và ổn định không?
5. Trang chủ có truyền input theo API được hỗ trợ và xác minh output trước khi áp dụng không?
6. Các event trong vùng nhúng có đi qua đúng JSF lifecycle và flow execution không?
7. Naming container, form, client ID và Ajax execute/render có được kiểm tra không?
8. Dữ liệu được lưu trong scope có vòng đời phù hợp và không chia sẻ nhầm giữa các execution không?
9. CSRF, authorization, binding whitelist và idempotency được bảo đảm không?
10. Test đã bao phủ thành công, validation lỗi, hủy, Ajax, nhiều execution và hết hạn chưa?

## Kết luận

Nhúng flow vào trang JSF cho phép một phần giao diện có hành trình nhiều bước được Spring Web Flow quản lý trong khi vẫn nằm trong bố cục trang chủ. Cơ chế nhúng của Spring Faces kết nối flow execution với JSF lifecycle; flow definition giữ state, event, validation và dữ liệu riêng. Trang chủ và flow trao đổi qua hợp đồng input/output, không cần phụ thuộc vào scope nội bộ của nhau.

Hãy phân biệt embedding với `ui:include` và subflow, dùng component/API đúng phiên bản Spring Faces, giữ execution độc lập và truyền dữ liệu tối thiểu. Kiểm thử cả flow lẫn JSF lifecycle, Ajax, bảo mật, hủy và hết hạn sẽ giúp vùng tương tác nhúng hoạt động ổn định mà không làm rối trạng thái của trang chủ.
