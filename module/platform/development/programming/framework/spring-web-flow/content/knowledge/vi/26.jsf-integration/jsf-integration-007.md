# Tham chiếu dữ liệu các scope bằng EL của Faces

## 1. Kết hợp Faces EL với dữ liệu của Spring Web Flow

Khi dùng **Spring Web Flow với JavaServer Faces (JSF)**, Facelets đảm nhiệm phần giao diện component, còn Web Flow điều khiển hành trình qua các view-state, event và transition. Một màn hình có thể được render nhiều lần qua các postback; người dùng nhập dữ liệu, bấm nút, xem kết quả rồi chuyển sang bước tiếp theo. Vì vậy, đối tượng mà component JSF đọc/ghi cần có vòng đời phù hợp với hành trình đó.

Trong Facelets, **Expression Language (EL)** thường xuất hiện dưới dạng:

```xhtml
<h:inputText value="#{searchCriteria.keyword}"/>
<h:outputText value="#{booking.confirmationNumber}"/>
```

Với JSF thuần, những tên như `searchCriteria` và `booking` thường là managed bean do JSF hoặc CDI quản lý. Khi tích hợp Spring Web Flow, biến do flow quản lý và bean do Spring quản lý cũng có thể được truy cập qua Faces EL. Web Flow tích hợp các scope `view`, `flow`, `flash` và `conversation` thông qua EL resolver của JSF.

Điều này cho phép đặt model ở đúng vòng đời của quy trình:

- Dữ liệu của cả hành trình nằm trong `flowScope`.
- Dữ liệu chỉ thuộc màn hình hiện tại nằm trong `viewScope`.
- Thông báo cần hiển thị ở lần render kế tiếp nằm trong `flashScope`.
- Dữ liệu cần chia sẻ giữa flow cha và subflow nằm trong `conversationScope`.

Bạn có thể tham chiếu biến trực tiếp theo tên, chẳng hạn `#{searchCriteria.keyword}`. Nếu cần tránh trùng tên thì chỉ rõ `#{flowScope.searchCriteria}`.

## 2. EL resolver tìm biến như thế nào?

### 2.1. Dùng tên biến trực tiếp

Giả sử flow khai báo:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="searchCriteria"
         class="com.example.catalog.SearchCriteria"/>

    <view-state id="search" view="catalog/search.xhtml"/>
</flow>
```

Trong Facelets của view `catalog/search.xhtml`, có thể viết:

```xhtml
<h:form id="searchForm">
    <h:outputLabel for="keyword" value="Từ khóa"/>
    <h:inputText id="keyword"
                 value="#{searchCriteria.keyword}"/>
    <h:commandButton value="Tìm kiếm" action="search"/>
</h:form>
```

Không cần viết `#{flowScope.searchCriteria.keyword}` vì Web Flow variable resolver tìm biến trong các scope có sẵn. Cách viết ngắn này giúp view ít phụ thuộc vào vị trí lưu model. Nếu sau này chuyển biến từ flow scope sang view scope, biểu thức `#{searchCriteria.keyword}` vẫn có thể giữ nguyên, miễn là tại thời điểm render chỉ có một biến cùng tên phù hợp.

### 2.2. Chỉ rõ scope khi cần

Nếu có các biến trùng tên hoặc muốn làm rõ vòng đời dữ liệu, hãy chỉ rõ scope:

```xhtml
<h:inputText value="#{flowScope.searchCriteria.keyword}"/>
<h:outputText value="#{viewScope.resultCount}"/>
<h:outputText value="#{conversationScope.checkout.customerName}"/>
<h:outputText value="#{flashScope.notice}"/>
```

Các tên `flowScope`, `viewScope`, `flashScope` và `conversationScope` ở đây là các scope của **Spring Web Flow** được tích hợp vào Faces EL. Chúng không phải tên bean mà bạn phải tự khai báo trong `faces-config.xml`.

### 2.3. Quy tắc tìm kiếm khi không ghi scope

Khi dùng một tên biến không có prefix, Web Flow tìm trong các scope theo thứ tự:

1. `requestScope`
2. `flashScope`
3. `viewScope`
4. `flowScope`
5. `conversationScope`

Ví dụ, nếu cả `viewScope.searchCriteria` và `flowScope.searchCriteria` cùng tồn tại, biểu thức `#{searchCriteria}` có thể resolve tới biến ở view scope trước. Đây là lý do nên tránh khai báo hai biến cùng tên trong nhiều scope nếu không thật sự cần.

Khi có nguy cơ trùng tên, viết rõ:

```xhtml
<h:inputText value="#{flowScope.searchCriteria.keyword}"/>
<h:outputText value="#{viewScope.searchCriteria.keyword}"/>
```

Tên biến trực tiếp phù hợp cho model chính có một vị trí lưu rõ ràng. Scope prefix phù hợp khi muốn đọc đúng một biến trong các scope chồng lấp hoặc khi code review cần thấy ngay vòng đời dữ liệu.

## 3. Phân biệt scope của Web Flow và scope chuẩn của JSF

JSF và Spring Web Flow cùng có khái niệm request/view/flash, nhưng chúng phục vụ những cơ chế quản lý khác nhau. Trong tích hợp Web Flow, cần hiểu đối tượng nào đang được truy cập.

| Tên | Ý nghĩa trong JSF/Web Flow | Vòng đời và mục đích |
| --- | --- | --- |
| `flowScope` | Scope của flow session trong Web Flow | Tồn tại từ khi flow bắt đầu đến khi flow kết thúc |
| `viewScope` | Scope của view-state trong Web Flow | Được tạo khi vào view-state và hủy khi rời state |
| `flashScope` | Flash scope của Web Flow | Dữ liệu được giữ đến lần render view kế tiếp rồi được dọn |
| `conversationScope` | Scope của top-level flow trong Web Flow | Dùng chung giữa flow cha và các subflow; kết thúc khi top-level flow kết thúc |
| `requestScope` | JSF có implicit request map; flow definition cũng có request scope riêng | Chỉ dùng cho dữ liệu tạm trong request; không phù hợp cho model nhiều bước |
| `sessionScope` | Scope chuẩn của JSF/Servlet | Tồn tại trong HTTP session, có thể dài hơn một flow |
| `applicationScope` | Scope chuẩn của JSF/Servlet | Dùng cho dữ liệu ứng dụng dùng chung, thường không chứa model theo người dùng |
| `flash` | Flash object chuẩn của JSF | Cơ chế flash của Faces, có quy tắc riêng với Web Flow flash scope |

### 3.1. flowScope không phải sessionScope

`flowScope` gắn với một flow execution. Người dùng có thể mở nhiều flow độc lập trong cùng HTTP session; mỗi flow có dữ liệu riêng. `sessionScope` của JSF lại gắn với toàn bộ session của người dùng.

Không đưa model của một quy trình đặt hàng vào session scope chỉ để giữ dữ liệu qua nhiều màn hình. Khi flow kết thúc, dữ liệu flow scope được dọn theo vòng đời flow; dữ liệu session scope có thể còn lại và ảnh hưởng một quy trình mới nếu không tự dọn.

### 3.2. conversationScope không phải CDI conversation scope

`conversationScope` của Spring Web Flow bắt đầu cùng top-level flow và được chia sẻ với các subflow trong conversation đó. Đây là cơ chế của Web Flow, không phải CDI conversation context.

Ví dụ flow `checkout` gọi subflow `selectAddress`. Nếu cả hai cần đọc cùng một đối tượng `checkoutContext`, có thể đặt nó trong conversation scope. Nếu dữ liệu chỉ cần truyền từ cha sang con hoặc từ con về cha một lần, input/output mapping của subflow thường rõ ràng hơn.

### 3.3. viewScope của Web Flow không phải một view-state khác

`viewScope` của Web Flow gắn với **một view-state**. Nó tồn tại qua các postback hoặc event nội trang khi flow vẫn ở state đó, và bị hủy khi flow chuyển sang state khác.

JSF cũng có view map thông qua `UIViewRoot.getViewMap()` và cơ chế bean `@ViewScoped`. Hai cơ chế có thể cùng xuất hiện trong ứng dụng JSF, nhưng không nên giả định chúng có cùng chủ sở hữu hoặc cùng thời điểm hủy. Khi model cần sống theo view-state của flow, ưu tiên khai báo biến bằng `<var>` bên trong `<view-state>` để Web Flow quản lý vòng đời.

### 3.4. requestScope cần được dùng cẩn thận trong Facelets

Trong flow definition, `requestScope` là scope tạm của Web Flow. Trong JSF, `requestScope` cũng là implicit map chuẩn đại diện cho request attributes của Servlet. Web Flow có biến EL `flowRequestContext`, qua đó có thể truy cập RequestContext của flow một cách tường minh khi cần phân biệt hai ngữ cảnh.

Không dùng request scope làm nơi giữ model qua nhiều postback hoặc state. Nếu cần một biến chỉ thuộc màn hình, dùng `viewScope`; nếu cần tồn tại qua nhiều bước, dùng `flowScope`. Với request attribute của Servlet, `#{requestScope.someAttribute}` là cách truy cập chuẩn của JSF. Trong flow definition, `requestScope` luôn chỉ scope request của Web Flow.

Nếu cần truy cập rõ request scope của Web Flow từ Faces EL mà không nhầm với implicit request map của JSF, có thể đi qua biến context của flow:

```xhtml
<h:outputText value="#{flowRequestContext.requestScope.notice}"/>
```

Tương tự, `#{flash}` của JSF và `#{flashScope.notice}` của Web Flow không nên được coi là cùng một map. Chọn đúng cơ chế mà ứng dụng đang sử dụng và kiểm thử hành vi sau redirect/render.

## 4. Khai báo flow variable để Facelets sử dụng

### 4.1. Biến cấp flow

Khai báo `<var>` ở cấp flow để tạo biến trong flow scope:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="searchCriteria"
         class="com.example.catalog.SearchCriteria"/>

    <view-state id="search" view="catalog/search.xhtml">
        <transition on="search" to="results"/>
    </view-state>

    <view-state id="results" view="catalog/results.xhtml"/>
</flow>
```

Facelets có thể dùng biến trực tiếp:

```xhtml
<h:form>
    <h:inputText id="keyword"
                 value="#{searchCriteria.keyword}"/>
    <h:inputText id="category"
                 value="#{flowScope.searchCriteria.category}"/>
    <h:commandButton value="Tìm" action="search"/>
</h:form>
```

`searchCriteria` tồn tại qua request tìm kiếm, request hiển thị kết quả và những lần người dùng quay lại view trong cùng flow execution. Khi flow kết thúc, biến không còn thuộc flow đó.

### 4.2. Biến chỉ thuộc một view-state

Nếu model chỉ cần trong màn hình tìm kiếm và không cần giữ sau khi chuyển sang state khác, khai báo `<var>` bên trong view-state:

```xml
<view-state id="search" view="catalog/search.xhtml">
    <var name="suggestions"
         class="com.example.catalog.SearchSuggestions"/>

    <transition on="search" to="results"/>
</view-state>
```

Trong Facelets:

```xhtml
<h:panelGroup id="suggestions">
    <h:outputText value="#{suggestions.summary}"/>
</h:panelGroup>
```

Biến này thuộc view scope của state `search`. Khi flow chuyển tới `results`, view scope của `search` được hủy. Nếu `suggestions` cần dùng ở state kết quả, hãy chuyển dữ liệu cần thiết sang flow scope trước khi rời state, hoặc nạp lại từ service.

### 4.3. Chỉ rõ scope trong flow definition và Facelets

Flow definition dùng biểu thức EL chuẩn không cần dấu `#{...}`:

```xml
<on-render>
    <evaluate expression="catalogService.findSuggestions(searchCriteria)"
              result="viewScope.suggestions"/>
</on-render>
```

Facelets lại dùng cú pháp EL của JSF:

```xhtml
<h:outputText value="#{viewScope.suggestions.summary}"/>
```

Không nhầm hai ngữ cảnh:

- Trong flow XML, `expression="..."` là standard expression của Web Flow.
- Trong Facelets, thuộc tính component chứa biểu thức EL có dạng `#{...}`.

## 5. Dùng flowScope trong form JSF

### 5.1. JSF component cập nhật trực tiếp model của flow

Trong JSF, component đọc/ghi model qua value expression:

```xhtml
<h:form id="bookingForm">
    <h:messages id="messages"/>

    <h:outputLabel for="guestName" value="Tên khách"/>
    <h:inputText id="guestName"
                 value="#{flowScope.booking.guestName}"
                 required="true"/>
    <h:message for="guestName"/>

    <h:outputLabel for="email" value="Email"/>
    <h:inputText id="email"
                 value="#{flowScope.booking.email}"
                 required="true"/>
    <h:message for="email"/>

    <h:commandButton id="review"
                     value="Xem lại"
                     action="review"/>
</h:form>
```

Flow cần có biến `booking` trong flow scope:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="booking" class="com.example.booking.Booking"/>

    <view-state id="enterDetails" view="booking/details.xhtml">
        <transition on="review" to="reviewBooking"/>
    </view-state>

    <view-state id="reviewBooking" view="booking/review.xhtml"/>
</flow>
```

JSF xử lý input theo lifecycle tiêu chuẩn: decode request, convert/validate component, cập nhật model values rồi phát action event. Khi component validation thất bại, action event điều hướng flow thường không được thực thi trong request đó; view được render lại cùng lỗi component.

### 5.2. Không trộn hai cơ chế binding

Với view công nghệ Spring MVC thông thường, Web Flow có thể binding request parameters vào model qua thuộc tính `model` của view-state. Với JSF, **standard JSF component lifecycle** thực hiện binding và validation. Không giả định Web Flow sẽ tự binding lại các field JSF như khi xử lý một MVC form view.

Hãy để component JSF liên kết với model bằng `value="#{...}"`, và để event action của component khớp với transition trong flow. Ví dụ:

```xml
<view-state id="enterDetails" view="booking/details.xhtml">
    <transition on="review" to="reviewBooking"/>
</view-state>
```

```xhtml
<h:commandButton value="Xem lại" action="review"/>
```

Tên action `review` là event mà Web Flow nhận để chọn transition `on="review"`.

### 5.3. Validation cấp component và validation cấp model

JSF có thể kiểm tra field ngay tại component bằng `required`, converter hoặc validator. Khi cần kiểm tra quy tắc liên quan nhiều field, có thể gọi method của model trong transition và truyền `messageContext`:

```xml
<view-state id="enterDetails" view="booking/details.xhtml">
    <transition on="review" to="reviewBooking">
        <evaluate expression="flowScope.booking.validate(messageContext)"/>
    </transition>
</view-state>
```

Model hoặc service có thể thêm lỗi vào `MessageContext`; các message này được tích hợp để hiển thị cùng message của Faces trong view. Cách này giúp domain model không phải phụ thuộc trực tiếp vào `FacesContext`.

`MessageContext` là nơi trao đổi thông báo validation; việc có message không tự thay thế quy tắc điều hướng của flow. Nếu dữ liệu không hợp lệ, transition cần có cơ chế quyết định giữ người dùng ở view hiện tại hoặc đi tới state sửa lỗi theo đúng kết quả validation.

## 6. Dùng viewScope cho dữ liệu nội trang và Ajax

### 6.1. Một view-state có thể xử lý nhiều request

JSF thường có nhiều hành động diễn ra ngay trong một màn hình: đổi trang bảng, lọc kết quả, mở rộng một vùng hoặc tải fragment. Những request này có thể vẫn ở cùng một view-state.

Ví dụ view `reviewHotels` cần giữ tiêu chí tìm kiếm và trang hiện tại:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <var name="searchCriteria"
         class="com.example.booking.SearchCriteria"/>

    <view-state id="reviewHotels" view="hotels/review.xhtml">
        <on-render>
            <evaluate expression="bookingService.findHotels(searchCriteria)"
                      result="viewScope.hotels"
                      result-type="dataModel"/>
        </on-render>

        <transition on="next">
            <evaluate expression="searchCriteria.nextPage()"/>
        </transition>

        <transition on="select" to="reviewHotel">
            <set name="flowScope.hotel" value="hotels.selectedRow"/>
        </transition>
    </view-state>

    <view-state id="reviewHotel" view="hotels/detail.xhtml"/>
</flow>
```

Ví dụ giả định subflow `addressSelection` kết thúc ở end-state `addressSelected` và khai báo output có tên `address`. Khi đó parent đọc được `currentEvent.attributes.address` trong transition tương ứng.

Trong Facelets:

```xhtml
<h:form id="hotelResults">
    <h:dataTable id="hotels"
                 value="#{hotels}"
                 var="hotel"
                 rendered="#{hotels.rowCount gt 0}">
        <h:column>
            <f:facet name="header">Khách sạn</f:facet>
            <h:outputText value="#{hotel.name}"/>
        </h:column>
        <h:column>
            <f:facet name="header">Thành phố</f:facet>
            <h:outputText value="#{hotel.city}"/>
        </h:column>
        <h:column>
            <h:commandLink value="Chi tiết" action="select"/>
        </h:column>
    </h:dataTable>

    <h:commandButton value="Trang tiếp" action="next"/>
</h:form>
```

Khi event `next` xảy ra mà transition không có `to`, flow vẫn ở state `reviewHotels`. `searchCriteria.nextPage()` thay đổi trang; `on-render` chạy lại và nạp trang kết quả mới vào view scope. Khi người dùng chọn một dòng, DataModel theo dõi dòng được chọn; transition `select` lấy `hotels.selectedRow` và chuyển đối tượng cần dùng sang `flowScope.hotel`.

### 6.2. Vì sao dùng DataModel thay cho List thuần?

`result-type="dataModel"` chuyển kết quả `List` sang JSF DataModel do Spring Faces cung cấp. DataModel này hỗ trợ:

- Tương thích với `h:dataTable`.
- Lưu trạng thái phù hợp với flow view qua các postback.
- Truy cập dòng được chọn thông qua `selectedRow`.
- Theo dõi lựa chọn một dòng với `OneSelectionTrackingListDataModel`.

`FacesConversionService` đăng ký `DataModelConverter` với alias `dataModel`. Vì vậy `result-type="dataModel"` trong flow XML có thể dùng converter này. Nếu cần theo dõi nhiều dòng được chọn, Spring Faces cung cấp `ManySelectionTrackingListDataModel`; ứng dụng phải đăng ký converter phù hợp.

Không nên giữ một danh sách rất lớn trong view scope chỉ để render bảng. Hãy truy vấn theo trang và chỉ nạp phần dữ liệu cần hiển thị.

### 6.3. Ajax event vẫn thuộc view-state

JSF có thể gửi Ajax postback và render lại một phần component tree. Web Flow vẫn nhận action event từ component và xử lý transition của view-state. Ví dụ:

```xhtml
<h:form id="hotelSearch">
    <h:inputText value="#{searchCriteria.city}"/>
    <h:commandButton value="Lọc" action="filter">
        <f:ajax execute="@form" render="results messages"/>
    </h:commandButton>

    <h:panelGroup id="results">
        <h:dataTable value="#{hotels}" var="hotel">
            <h:column>
                <h:outputText value="#{hotel.name}"/>
            </h:column>
        </h:dataTable>
    </h:panelGroup>
    <h:messages id="messages"/>
</h:form>
```

Flow có thể xử lý event `filter` ngay trong state, cập nhật tiêu chí rồi render lại dữ liệu:

```xml
<view-state id="reviewHotels" view="hotels/review.xhtml">
    <on-render>
        <evaluate expression="bookingService.findHotels(searchCriteria)"
                  result="viewScope.hotels"
                  result-type="dataModel"/>
    </on-render>
    <transition on="filter">
        <evaluate expression="searchCriteria.resetPage()"/>
    </transition>
</view-state>
```

Với Ajax request, Web Flow phối hợp qua `JsfFlowHandlerAdapter` và `JsfAjaxHandler`. Nếu thư viện component có quy tắc riêng về partial execute/render, hãy kiểm tra request đó thực sự gửi event nào và những component nào được xử lý.

## 7. Dùng flashScope cho thông báo sau hành động

`flashScope` của Web Flow thích hợp với dữ liệu ngắn hạn cần hiển thị trong view kế tiếp:

```xml
<action-state id="saveProfile">
    <evaluate expression="profileService.save(flowScope.profile)"/>
    <set name="flashScope.notice"
         value="'Đã lưu hồ sơ thành công'"/>
    <transition on="success" to="profileSaved"/>
</action-state>

<view-state id="profileSaved" view="profile/saved.xhtml"/>
```

Facelets:

```xhtml
<h:panelGroup rendered="#{not empty flashScope.notice}">
    <h:outputText value="#{flashScope.notice}"/>
</h:panelGroup>
```

Flash scope của Web Flow được dọn sau mỗi lần view render. Vì vậy nếu người dùng refresh hoặc tiếp tục một request khác sau khi thông báo đã render, không nên kỳ vọng thông báo còn nguyên.

Đối với thông báo validation, hãy dùng JSF `FacesMessage` hoặc Web Flow `MessageContext` theo tích hợp; không dùng flash scope để thay thế message lifecycle của component.

## 8. Dùng conversationScope khi flow cha và subflow cần dữ liệu chung

Conversation scope tồn tại từ khi top-level flow bắt đầu đến khi top-level flow kết thúc. Các subflow thuộc conversation có thể đọc cùng dữ liệu.

Flow cha:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="customerId" type="long" required="true"/>

    <on-start>
        <evaluate expression="checkoutService.createContext(customerId)"
                  result="conversationScope.checkoutContext"/>
    </on-start>

    <subflow-state id="chooseAddress" subflow="addressSelection">
        <input name="customerId"
               value="conversationScope.checkoutContext.customerId"/>
        <transition on="addressSelected" to="reviewOrder">
            <evaluate
                expression="conversationScope.checkoutContext.setAddress(currentEvent.attributes.address)"/>
        </transition>
    </subflow-state>

    <view-state id="reviewOrder" view="checkout/review.xhtml"/>
</flow>
```

Ví dụ giả định subflow `addressSelection` kết thúc ở end-state `addressSelected` và khai báo output có tên `address`. Khi đó parent đọc được `currentEvent.attributes.address` trong transition tương ứng.

Facelets trong flow con có thể đọc dữ liệu conversation nếu cần:

```xhtml
<h:outputText value="#{conversationScope.checkoutContext.customerName}"/>
```

Tuy nhiên, chia sẻ scope không phải cách duy nhất để trao đổi dữ liệu. Nếu subflow chỉ cần `customerId` và trả `address`, dùng input/output mapping sẽ làm hợp đồng giữa hai flow rõ ràng hơn. Dùng conversation scope khi nhiều bước trong cùng conversation thật sự cần đọc/ghi cùng một context.

Theo mặc định, conversation scope được lưu trong HTTP session. Đối tượng cần tồn tại qua execution snapshot hoặc session replication nên có khả năng serialize. Không lưu `FacesContext`, `HttpServletRequest`, `EntityManager`, stream hoặc tài nguyên phụ thuộc thread vào conversation scope.

## 9. Kết hợp biến flow với Spring bean có scope

### 9.1. Dùng flow variable khi model thuộc riêng flow

Khai báo `<var>` trong flow là lựa chọn tự nhiên khi model chỉ phục vụ một hành trình:

```xml
<var name="booking"
     class="com.example.booking.Booking"/>
```

Spring Web Flow quản lý vòng đời biến này. Trong Facelets, có thể dùng `#{booking}` hoặc `#{flowScope.booking}`.

### 9.2. Dùng Spring scoped bean khi cần AOP hoặc khả năng của container

Nếu model cần Spring AOP, proxy hoặc các tính năng khác của ApplicationContext, có thể khai báo Spring bean với Web Flow scope:

```xml
<bean id="searchCriteria"
      class="com.example.catalog.SearchCriteria"
      scope="flow"/>
```

Bean được khởi tạo lười khi được truy cập lần đầu qua EL. Trong Facelets:

```xhtml
<h:inputText value="#{searchCriteria.keyword}"/>
```

Không khai báo đồng thời flow variable và Spring scoped bean cùng tên nếu không có lý do rõ ràng. Khi resolver tìm tên `searchCriteria`, hai đối tượng cùng tên có thể khiến người đọc khó xác định model nào đang được cập nhật.

### 9.3. Managed bean JSF cũ và Spring bean

Web Flow có hỗ trợ tích hợp để tham chiếu JSF managed bean cũ trong các ứng dụng đang chuyển đổi. Tuy nhiên, với thiết kế mới, nên ưu tiên:

- Flow variable cho model thuộc vòng đời flow.
- Spring bean cho service và dependency nghiệp vụ.
- Spring scoped bean khi cần một object do container quản lý với scope của Web Flow.

Tránh duy trì hai hệ thống managed bean cùng sở hữu một model nghiệp vụ. Nếu ứng dụng vẫn dùng bean khai báo trong `faces-config.xml`, hãy kiểm tra cấu hình flow builder services và EL resolver của phiên bản đang dùng.

## 10. Cấu hình để Faces EL nhìn thấy Web Flow scopes

### 10.1. Cấu hình XML

Web Flow cần cấu hình JSF-specific flow builder services và listener quản lý FacesContext:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xmlns:faces="http://www.springframework.org/schema/faces"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/webflow-config
         https://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd
         http://www.springframework.org/schema/faces
         https://www.springframework.org/schema/faces/spring-faces.xsd">

    <webflow:flow-executor id="flowExecutor">
        <webflow:flow-execution-listeners>
            <webflow:listener ref="facesContextListener"/>
        </webflow:flow-execution-listeners>
    </webflow:flow-executor>

    <webflow:flow-registry id="flowRegistry"
                           flow-builder-services="flowBuilderServices"
                           base-path="/WEB-INF">
        <webflow:flow-location-pattern value="**/*-flow.xml"/>
    </webflow:flow-registry>

    <faces:flow-builder-services id="flowBuilderServices"/>

    <bean id="facesContextListener"
          class="org.springframework.faces.webflow.FlowFacesContextLifecycleListener"/>

    <faces:resources/>

    <bean class="org.springframework.faces.webflow.JsfFlowHandlerAdapter">
        <property name="flowExecutor" ref="flowExecutor"/>
    </bean>
</beans>
```

`FlowFacesContextLifecycleListener` tạo một FacesContext phù hợp trong suốt một Web Flow request rồi giải phóng sau khi request được xử lý. `faces:flow-builder-services` cấu hình view factory và conversion cho môi trường JSF. `JsfFlowHandlerAdapter` thay adapter Web Flow mặc định để xử lý Ajax theo cách phù hợp với JSF.

### 10.2. Cấu hình Java

Có thể dùng lớp cấu hình chuyên cho Faces:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.faces.config.AbstractFacesFlowConfiguration;
import org.springframework.faces.webflow.FlowFacesContextLifecycleListener;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;
import org.springframework.webflow.executor.FlowExecutor;

@Configuration
public class FacesWebFlowConfiguration
        extends AbstractFacesFlowConfiguration {

    @Bean
    public FlowExecutor flowExecutor() {
        return getFlowExecutorBuilder(flowRegistry())
                .addFlowExecutionListener(
                        new FlowFacesContextLifecycleListener())
                .build();
    }

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder()
                .setBasePath("/WEB-INF")
                .addFlowLocationPattern("**/*-flow.xml")
                .build();
    }
}
```

`AbstractFacesFlowConfiguration` cung cấp cấu hình phù hợp cho JSF integration. Trong ứng dụng đã có `FlowExecutor` và `FlowDefinitionRegistry`, hãy bổ sung Faces integration vào cấu hình hiện hữu thay vì tạo hai executor khác nhau.

### 10.3. Bootstrap JSF và đường đi request

Với Spring Web Flow 3.0:

- JSF 4.0 trở lên được yêu cầu.
- `FacesServlet` vẫn cần được khai báo để JSF bootstrap, dù request chạy Web Flow thường được dispatch qua Spring MVC `DispatcherServlet`.
- Facelets thường dùng file `.xhtml` và context parameter `jakarta.faces.DEFAULT_SUFFIX`.
- Request flow được xử lý qua `JsfFlowHandlerAdapter`.

Ví dụ khai báo suffix:

```xml
<context-param>
    <param-name>jakarta.faces.DEFAULT_SUFFIX</param-name>
    <param-value>.xhtml</param-value>
</context-param>
```

Đừng trỏ request flow qua một đường servlet khác với đường đã cấu hình `JsfFlowHandlerAdapter`; nếu request không đi qua Web Flow JSF integration, flow EL resolver và FacesContext lifecycle có thể không hoạt động như mong đợi.

## 11. EL trong Facelets và EL trong flow definition

Hai nơi dùng biểu thức có cú pháp khác nhau:

| Vị trí | Cú pháp | Ví dụ |
| --- | --- | --- |
| Facelets component | JSF EL có dấu `#{...}` | `value="#{flowScope.booking.guestName}"` |
| Flow XML `expression` | Standard expression, không bọc dấu | `bookingService.load(bookingId)` |
| Flow XML `result` | Tên scope và biến đích | `flowScope.booking` |
| Flow XML `value` | Biểu thức nguồn | `flowScope.booking.id` |
| Flow XML template expression | Ghép văn bản tĩnh và biểu thức bằng dấu phân cách | `view="booking-#{externalContext.locale}.xhtml"` |

Ví dụ:

```xml
<on-render>
    <evaluate expression="bookingService.load(bookingId)"
              result="flowScope.booking"/>
</on-render>
```

```xhtml
<h:outputText value="#{flowScope.booking.confirmationNumber}"/>
```

Không thêm `#{ }` vào `expression` của flow XML nếu thuộc tính đó yêu cầu standard expression. Ngược lại, không bỏ `#{...}` khỏi value expression của Facelets component.

## 12. Phân biệt request parameter với biến trong scope

JSF có implicit object `param`, còn Web Flow có biến `requestParameters`. Cả hai đều giúp đọc dữ liệu client gửi, nhưng chúng không phải model của flow:

```xhtml
<h:outputText value="#{param.campaign}"/>
```

Trong flow XML:

```xml
<set name="flowScope.campaignCode"
     value="requestParameters.campaign"/>
```

Giá trị từ URL hoặc form parameter vẫn là dữ liệu không đáng tin cậy. Hãy validate định dạng, kiểm tra quyền và chỉ chuyển vào flow scope khi flow thực sự cần giữ nó qua các request.

Với dữ liệu do người dùng nhập trong JSF form, nên binding vào model đã được khai báo:

```xhtml
<h:inputText value="#{flowScope.booking.campaignCode}"/>
```

Không đọc lại request parameter để thay thế giá trị model đã được JSF convert/validate. Cách đó có thể bỏ qua conversion, validation và quy tắc binding của component.

## 13. Lưu ý về serialization và tài nguyên

Flow execution thường được lưu snapshot để hỗ trợ resume và browser back. Vì vậy các object trong flow scope, view scope hoặc conversation scope có thể cần serializable theo repository mặc định.

Khi dùng Faces EL để tham chiếu dữ liệu, cần tránh lưu:

- `FacesContext`, `UIComponent`, `UIViewRoot` hoặc đối tượng gắn với một lần render.
- `HttpServletRequest`, `HttpServletResponse`, `ExternalContext` hoặc đối tượng request runtime.
- `EntityManager`, Hibernate Session, JDBC Connection, stream hoặc file handle.
- Object graph quá lớn hoặc chứa proxy lazy không thể khôi phục sau khi context đóng.
- Dữ liệu bí mật không cần giữ trong flow snapshot.

Ưu tiên DTO serializable, ID và dữ liệu nhỏ có ý nghĩa rõ ràng. Nếu cần truy vấn lại, lưu ID và gọi service ở lần render tiếp theo thay vì giữ toàn bộ entity graph.

## 14. Lỗi thường gặp khi tham chiếu scope trong Faces EL

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `#{searchCriteria.keyword}` trả null | Biến chưa được khai báo hoặc chưa được tạo trong scope hiện tại | Khai báo `<var>` ở flow hoặc view-state và kiểm tra state đang render |
| EL lấy nhầm object cùng tên | Nhiều scope có biến trùng tên | Dùng prefix như `#{flowScope.searchCriteria}` |
| `#{flowScope.booking}` không resolve | Request không đi qua JSF/Web Flow integration hoặc Faces resolver chưa được cấu hình | Kiểm tra `JsfFlowHandlerAdapter`, flow builder services và listener FacesContext |
| Model mất khi chuyển sang view khác | Model được đặt trong view scope | Chuyển dữ liệu cần giữ sang flow scope trước transition |
| Model của hai flow bị dùng chung | Lưu nhầm trong session/application scope hoặc singleton mutable bean | Dùng flow scope hoặc conversation scope phù hợp |
| Thông báo biến mất sau lần render | Flash scope đã được dọn theo vòng đời | Ghi lại thông báo ở action phù hợp hoặc dùng message context |
| Bảng không biết dòng nào được chọn | Dùng List thuần hoặc không có selection tracking model | Dùng `result-type="dataModel"` và kiểm tra converter |
| `selectedRow` null | Event không đến từ row action hoặc DataModel không ghi nhận selection | Kiểm tra component action và selection tracking |
| Ajax không cập nhật dữ liệu | Component không nằm trong vùng execute hoặc render | Kiểm tra `f:ajax execute`/`render` và event transition |
| `ClassCastException` sau postback | EL binding hoặc converter trả kiểu không như mong đợi | Kiểm tra property type, converter và model |
| Dữ liệu lỗi sau khi resume flow | Đối tượng trong scope không thể serialize/restore | Dùng DTO serializable hoặc lưu ID để nạp lại |
| Hai biến cùng tên gây hành vi khó đoán | Resolver tìm biến theo thứ tự scope | Đặt tên khác nhau hoặc tham chiếu scope tường minh |

### Quy trình chẩn đoán

1. Xác định request có thực sự được xử lý bởi `JsfFlowHandlerAdapter` không.
2. Kiểm tra flow đang ở view-state nào.
3. Xác định biến được khai báo bằng `<var>` ở cấp flow hay trong view-state.
4. Kiểm tra biến có trùng tên ở scope khác không.
5. Thử EL có prefix để xác định resolver đang đọc scope nào.
6. Kiểm tra component JSF có chạy đủ lifecycle và cập nhật model không.
7. Nếu lỗi chỉ xuất hiện sau postback hoặc resume, kiểm tra serialization và view-state snapshot.

## 15. Kiểm thử việc tham chiếu scope

Nên kiểm thử vòng đời thực tế thay vì chỉ kiểm tra EL không báo lỗi.

| Kịch bản | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Flow variable | Mở flow và render Facelets | `#{searchCriteria}` đọc được biến đã khai báo ở flow scope |
| Binding form | Nhập từ khóa rồi gửi event | Giá trị được JSF cập nhật vào model trước khi transition xử lý |
| View variable | Gửi nhiều postback trong cùng view-state | Biến view scope vẫn còn |
| Rời view-state | Chuyển sang state khác | Biến chỉ thuộc view scope cũ được dọn |
| Flow scope | Chuyển qua nhiều view-state và quay lại | Model flow scope vẫn tồn tại |
| Conversation scope | Parent gọi subflow | Cả parent và child đọc được dữ liệu conversation đã chia sẻ |
| Flash scope | Ghi thông báo và render view tiếp theo | View kế tiếp đọc được; lần render sau không giả định còn dữ liệu |
| Tên trùng scope | Khai báo hai biến cùng tên trong view và flow scope | Prefix đọc đúng biến dự kiến |
| DataModel | Render bảng, chọn một dòng rồi phát event | `selectedRow` trả đúng object đã chọn |
| Ajax postback | Gửi event nội trang và render fragment | View-state hiện tại và view scope được giữ |
| Resume snapshot | Tiếp tục flow sau request mới | Các object trong scope được khôi phục đúng |

Với flow XML, có thể dùng `AbstractXmlFlowExecutionTests` để kiểm tra state, event và action. Để kiểm tra Facelets EL và JSF component lifecycle, cần thêm integration test chạy cấu hình Faces thật hoặc test trên container tương thích. Unit test flow không tự chứng minh component JSF đã binding đúng.

## 16. Bài tập thực hành

Xây dựng flow tìm kiếm khách sạn có ba màn hình:

1. `criteria`: người dùng nhập thành phố và ngày nhận/trả phòng.
2. `results`: hiển thị bảng kết quả, hỗ trợ chuyển trang và chọn khách sạn.
3. `details`: hiển thị khách sạn đã chọn và cho phép xác nhận.

Yêu cầu:

- Khai báo `searchCriteria` ở flow scope để giữ điều kiện tìm kiếm qua nhiều view-state.
- Khai báo `hotels` ở view scope của state `results`.
- Trong `on-render`, gọi service tìm kiếm và dùng `result-type="dataModel"`.
- Trong Facelets, bind form qua `#{searchCriteria.city}` và `#{searchCriteria.checkIn}`.
- Dùng `h:dataTable` với `#{hotels}` và event `select` để chọn dòng.
- Trong transition `select`, chuyển `hotels.selectedRow` sang `flowScope.selectedHotel`.
- Hiển thị `#{flowScope.selectedHotel.name}` ở view `details`.
- Ghi một thông báo vào `flashScope` khi người dùng xác nhận thành công.
- Viết test cho postback trong cùng view-state, chuyển view-state, lựa chọn dòng và resume flow.

**Tiêu chí đạt:** giải thích được vì sao tiêu chí tìm kiếm ở flow scope, kết quả bảng ở view scope, cách Facelets EL tìm biến không prefix, cách prefix scope để tránh trùng tên và cách DataModel giữ dòng được chọn qua postback.

## 17. Ghi nhớ

- Web Flow tích hợp các scope `view`, `flow`, `flash` và `conversation` với Faces EL qua resolver của JSF.
- Biến flow có thể được tham chiếu trực tiếp như `#{searchCriteria.keyword}`; dùng `#{flowScope.searchCriteria.keyword}` khi cần xác định rõ scope.
- Khi không ghi prefix, resolver tìm theo thứ tự request, flash, view, flow rồi conversation; tránh khai báo các biến cùng tên ở nhiều scope.
- `viewScope` của Web Flow gắn với một view-state, tồn tại qua postback của state và bị hủy khi rời state.
- `flowScope` giữ model qua nhiều view-state; `conversationScope` chia sẻ dữ liệu giữa top-level flow và subflow.
- `flashScope` của Web Flow được dọn sau khi view render; không đồng nhất nó với JSF `flash`.
- JSF component lifecycle chịu trách nhiệm conversion, validation và cập nhật model; Web Flow nhận action event để chọn transition.
- `result-type="dataModel"` hỗ trợ `h:dataTable` và theo dõi dòng được chọn qua `selectedRow`.
- Dùng DTO/ID serializable trong scope; không giữ FacesContext, request, connection hoặc tài nguyên runtime trong flow snapshot.
- Spring Web Flow 3.0 yêu cầu JSF 4.0 trở lên; cấu hình Faces flow builder services, `FlowFacesContextLifecycleListener` và `JsfFlowHandlerAdapter` để tích hợp đầy đủ.

### Tài liệu tham khảo

- [Spring Web Flow 3.0 Reference Guide – JSF Integration](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#jsf-integration): tích hợp Facelets, flow variables, scoped Spring beans, DataModel và JSF events.
- [Spring Web Flow 3.0 Reference Guide – Variable Scopes](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#variable-scopes): vòng đời flow, view, request, flash và conversation scope.
- [Spring Web Flow 3.0 Reference Guide – Scope Searching Algorithm](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#scope-searching-algorithm): thứ tự tìm biến khi không chỉ rõ scope.
- [FlowELResolver Javadoc](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/faces/webflow/FlowELResolver.html): EL resolver dành cho biểu thức đặc thù của Web Flow trong JSF.
- [ImplicitFlowVariableELResolver Javadoc](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/webflow/expression/el/ImplicitFlowVariableELResolver.html): các biến implicit như `flowScope`, `viewScope`, `flashScope` và `conversationScope`.
- [Spring Web Flow 3.0.1 – FlowBuilderServicesBuilder](https://docs.spring.io/spring-webflow/docs/3.0.1/api/org/springframework/faces/config/FlowBuilderServicesBuilder.html): cấu hình flow builder services dành cho JSF.
