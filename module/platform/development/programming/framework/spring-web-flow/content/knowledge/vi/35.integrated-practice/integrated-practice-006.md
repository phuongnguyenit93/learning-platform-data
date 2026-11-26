# Tìm kiếm, phân trang và chọn kết quả trong một view-state

Một màn hình tra cứu khách sạn thường cần nhiều thao tác: người dùng nhập từ khóa và bộ lọc, xem danh sách kết quả, chuyển sang trang tiếp theo, quay lại trang trước rồi chọn một khách sạn để xem chi tiết. Nếu mỗi thao tác nhỏ đều chuyển sang một state khác, flow sẽ có rất nhiều state chỉ để cập nhật một vùng giao diện.

Spring Web Flow cho phép xử lý các thao tác này trong **cùng một view-state** bằng những transition không khai báo thuộc tính `to`. Các transition đó là **event handler**: nhận event, chạy action, rồi render lại view hiện tại hoặc một fragment của view. Kết hợp với `viewScope`, `on-render`, `DataModel` và fragment rendering, ta có thể xây dựng một màn hình tìm kiếm có phân trang và chọn kết quả mà không rời state cho tới khi người dùng thực sự chọn một mục để đi tiếp.

Bài thuộc chương **Thực hành tổng hợp** của module `SPRING_WEB_FLOW`. Ví dụ dùng màn hình tìm khách sạn để minh họa flow XML, model tìm kiếm, service phân trang, view JSF và biến thể Spring MVC/JSP. Bài cũng đề cập giới hạn binding, kiểm tra quyền khi chọn kết quả và cách kiểm thử các event trong cùng một state.

## 1. Vì sao giữ tìm kiếm và phân trang trong một view-state?

Một view-state là một bước giao diện: flow render view và chờ event từ người dùng. Trong state đó có thể khai báo nhiều transition:

- `search`: áp dụng từ khóa/bộ lọc và trở về trang đầu.
- `next`: chuyển sang trang kết quả tiếp theo.
- `previous`: quay về trang trước.
- `select`: chọn một dòng kết quả và chuyển sang state chi tiết.
- `clear`: xóa điều kiện tìm kiếm và hiển thị lại danh sách ban đầu.

Các event `search`, `next`, `previous` và `clear` không cần rời state. Chúng cập nhật dữ liệu trong view rồi yêu cầu render lại. Event `select` là điểm chuyển tiếp thật sự: nó lấy mục người dùng chọn, kiểm tra quyền và đưa đối tượng đã xác minh vào flow scope trước khi sang state tiếp theo.

~~~mermaid
flowchart TD
    A["searchResults view-state"] -->|"search"| B["Cập nhật điều kiện + về trang 1"]
    B --> A
    A -->|"next / previous"| C["Thay đổi page number"]
    C --> A
    A -->|"clear"| D["Xóa filter + về trang 1"]
    D --> A
    A -->|"select"| E["Kiểm tra mục được chọn"]
    E -->|"Hợp lệ"| F["reviewSelected view-state"]
    E -->|"Không hợp lệ"| A
~~~

Điểm quan trọng là transition không có thuộc tính `to` **không tạo state mới**. Nó xử lý event rồi render lại view-state hiện tại. Khi event có yêu cầu cập nhật một phần giao diện, có thể dùng `<render fragments="..."/>` để chỉ render fragment của view.

## 2. Phân chia dữ liệu theo scope

Màn hình tìm kiếm có ba nhóm dữ liệu với vòng đời khác nhau:

| Dữ liệu | Ví dụ | Scope phù hợp | Lý do |
|---|---|---|---|
| Điều kiện tìm kiếm và trang hiện tại | keyword, city, sort, page number | `viewScope` | Chỉ cần tồn tại trong suốt màn hình tìm kiếm |
| Kết quả và metadata trang | danh sách khách sạn, tổng trang, hasNext | `viewScope` | Được tải lại trước mỗi lần render |
| Khách sạn đã chọn | khách sạn người dùng muốn xem tiếp | `flowScope` | Cần tồn tại sau khi rời màn hình tìm kiếm |

`viewScope` được tạo khi flow vào view-state và bị hủy khi flow rời state. Đây là nơi phù hợp cho `searchCriteria` và dữ liệu trang kết quả. `flowScope` tồn tại trong suốt flow execution; vì vậy đối tượng được chọn cần được đưa vào đó trước khi chuyển sang state chi tiết.

Không nên lưu toàn bộ kết quả tìm kiếm vào `conversationScope` nếu chỉ một view-state sử dụng. Với mặc định repository, các object lưu trong scope có thể cần khả năng serialize; ưu tiên DTO gọn thay vì entity JPA hoặc object chứa connection/resource.

## 3. Thiết kế model tìm kiếm và kết quả phân trang

Ví dụ dùng ba kiểu:

- `HotelSearchCriteria`: điều kiện tìm kiếm và số trang hiện tại.
- `HotelSearchPage`: một trang kết quả, kèm thông tin có trang trước/trang sau.
- `HotelSummary`: DTO gọn dùng để hiển thị trong bảng.

### 3.1. HotelSearchCriteria

~~~java
package com.example.hotel.search;

public class HotelSearchCriteria {

    private String keyword;
    private String city;
    private String sort = "name";
    private String selectedItemId;
    private int pageNumber;

    public String getKeyword() { return keyword; }
    public void setKeyword(String keyword) { this.keyword = keyword; }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getSort() { return sort; }
    public void setSort(String sort) { this.sort = sort; }

    public String getSelectedItemId() { return selectedItemId; }
    public void setSelectedItemId(String selectedItemId) {
        this.selectedItemId = selectedItemId;
    }

    public int getPageNumber() { return pageNumber; }

    public void setPageNumber(int pageNumber) {
        this.pageNumber = Math.max(0, pageNumber);
    }

    public void firstPage() {
        pageNumber = 0;
        selectedItemId = null;
    }

    public void nextPage(HotelSearchPage currentPage) {
        if (currentPage != null && currentPage.hasNext()) {
            pageNumber++;
            selectedItemId = null;
        }
    }

    public void previousPage() {
        pageNumber = Math.max(0, pageNumber - 1);
        selectedItemId = null;
    }

    public void clear() {
        keyword = null;
        city = null;
        sort = "name";
        pageNumber = 0;
        selectedItemId = null;
    }
}
~~~

`pageNumber` dùng chỉ số bắt đầu từ 0. Người dùng không cần gửi trực tiếp giá trị này qua form; các event `next` và `previous` gọi method trên server để thay đổi trang. Nhờ đó, client không thể tự đặt page size hoặc sort property tùy ý thông qua một hidden field.

### 3.2. HotelSearchPage

~~~java
package com.example.hotel.search;

import java.util.List;

public class HotelSearchPage {

    private final List<HotelSummary> items;
    private final int pageNumber;
    private final int totalPages;

    public HotelSearchPage(
            List<HotelSummary> items,
            int pageNumber,
            int totalPages) {
        this.items = items;
        this.pageNumber = pageNumber;
        this.totalPages = totalPages;
    }

    public List<HotelSummary> getItems() { return items; }
    public int getPageNumber() { return pageNumber; }
    public int getTotalPages() { return totalPages; }

    public boolean hasPrevious() {
        return pageNumber > 0;
    }

    public boolean hasNext() {
        return pageNumber + 1 < totalPages;
    }

    public boolean contains(String hotelId) {
        return items.stream()
            .anyMatch(hotel -> hotel.getId().equals(hotelId));
    }
}
~~~

`totalPages` bằng 0 khi không có kết quả. Với trang đầu tiên, `hasPrevious()` là false; với trang cuối, `hasNext()` là false. Service cần chuẩn hóa page number nếu dữ liệu thay đổi giữa hai request, chẳng hạn khách sạn bị xóa khiến trang cuối không còn tồn tại.

`HotelSummary` chỉ nên chứa dữ liệu cần hiển thị như `id`, `name`, `city`, `rating` và giá tham khảo. Không cần giữ entity đầy đủ trong view scope nếu màn hình chỉ hiển thị một vài trường.

## 4. Service tìm kiếm và điều hướng trang

Flow không nên tự viết câu truy vấn hoặc tính phân trang trong expression. Một service nhận criteria, kiểm tra tham số và trả về `HotelSearchPage`:

~~~java
package com.example.hotel.search;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class HotelSearchService {

    private static final int PAGE_SIZE = 10;

    private static final Set<String> ALLOWED_SORTS =
        new HashSet<>(Arrays.asList("name", "rating", "price"));

    private final HotelRepository hotelRepository;

    public HotelSearchService(HotelRepository hotelRepository) {
        this.hotelRepository = hotelRepository;
    }

    public HotelSearchPage search(HotelSearchCriteria criteria) {
        String keyword = normalize(criteria.getKeyword());
        String city = normalize(criteria.getCity());

        String sort = ALLOWED_SORTS.contains(criteria.getSort())
            ? criteria.getSort()
            : "name";

        int pageNumber = Math.max(0, criteria.getPageNumber());

        HotelSearchPage page = hotelRepository.search(
            keyword,
            city,
            sort,
            pageNumber,
            PAGE_SIZE
        );

        if (page.getTotalPages() == 0) {
            criteria.firstPage();
            return page;
        }

        if (pageNumber >= page.getTotalPages()) {
            criteria.setPageNumber(page.getTotalPages() - 1);
            return hotelRepository.search(
                keyword,
                city,
                sort,
                criteria.getPageNumber(),
                PAGE_SIZE
            );
        }

        return page;
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}
~~~

Đoạn code minh họa service và repository contract; `HotelRepository.search(...)` cần trả một `HotelSearchPage` theo page number và page size. Nếu trang yêu cầu vượt quá trang cuối, service đưa criteria về trang hợp lệ rồi truy vấn lại. `PAGE_SIZE` là cấu hình phía server, không nhận trực tiếp từ request.

Các nguyên tắc quan trọng:

- Chuẩn hóa keyword trước khi truy vấn.
- Chỉ chấp nhận sort key trong allowlist.
- Kiểm tra city/category theo phạm vi dữ liệu mà người dùng được phép xem.
- Giới hạn page size để request không yêu cầu hàng nghìn kết quả.
- Dùng DTO và truy vấn phân trang ở database thay vì tải toàn bộ dữ liệu rồi cắt list trong Java.

### 4.1. Chọn khách sạn phải kiểm tra lại quyền truy cập

Một dòng xuất hiện trong kết quả không có nghĩa client được quyền mở bất kỳ ID nào mà họ gửi lên. Service chọn mục cần xác minh ID tồn tại, người dùng có quyền xem và mục vẫn hợp lệ tại thời điểm chọn:

~~~java
public HotelSummary findSelectableHotel(
        String hotelId,
        HotelSearchPage currentPage,
        String username) {

    if (hotelId == null
            || currentPage == null
            || !currentPage.contains(hotelId)) {
        return null;
    }

    return hotelRepository.findVisibleHotel(hotelId, username);
}
~~~

`currentPage.contains(...)` xác nhận ID thuộc trang đang hiển thị; `findVisibleHotel(...)` phải áp dụng điều kiện quyền truy cập ở server. Không dùng riêng `selectedRow` hoặc hidden field làm căn cứ authorization.

## 5. Khai báo một view-state xử lý tìm kiếm và phân trang

Flow XML dưới đây giữ `searchCriteria`, `page` và `results` trong cùng view-state:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="searchResults"
                view="hotels/search"
                model="searchCriteria">

        <var name="searchCriteria"
             class="com.example.hotel.search.HotelSearchCriteria" />

        <binder>
            <binding property="keyword" />
            <binding property="city" />
            <binding property="sort" />
        </binder>

        <on-render>
            <evaluate
                expression="hotelSearchService.search(searchCriteria)"
                result="viewScope.page" />

            <evaluate
                expression="page.items"
                result="viewScope.results"
                result-type="dataModel" />
        </on-render>

        <!-- Các event handler dưới đây không rời searchResults. -->
        <transition on="search">
            <evaluate expression="searchCriteria.firstPage()" />
            <render fragments="searchForm:resultsPanel" />
        </transition>

        <transition on="next">
            <evaluate expression="searchCriteria.nextPage(page)" />
            <render fragments="searchForm:resultsPanel" />
        </transition>

        <transition on="previous">
            <evaluate expression="searchCriteria.previousPage()" />
            <render fragments="searchForm:resultsPanel" />
        </transition>

        <transition on="clear">
            <evaluate expression="searchCriteria.clear()" />
            <render fragments="searchForm:resultsPanel" />
        </transition>

        <transition on="select" to="reviewSelected">
            <evaluate
                expression="hotelSelectionAction.select(
                    results.selectedRow,
                    page,
                    currentUser,
                    flowRequestContext)" />
        </transition>
    </view-state>

    <view-state id="reviewSelected" view="hotels/selected" />

</flow>
~~~

Có bốn điểm cần chú ý:

1. `searchCriteria` được khai báo bằng `<var>` trong view-state nên thuộc view scope. Nó được tạo khi vào màn hình tìm kiếm và bị hủy khi flow rời màn hình đó.
2. `<on-render>` chạy lúc hiển thị lần đầu và trước các lần render tiếp theo, kể cả partial render. Kết quả service được lưu vào `viewScope.page`; danh sách `page.items` được bọc thành `DataModel` để hỗ trợ chọn dòng trong JSF.
3. Transition `search`, `next`, `previous` và `clear` **không có `to`**. Chúng chỉ cập nhật criteria, yêu cầu render fragment rồi giữ nguyên state `searchResults`.
4. Transition `select` có `to="reviewSelected"`, vì người dùng đã chọn xong một khách sạn và muốn đi tới màn hình tiếp theo.

Tên bean `hotelSearchService` và `hotelSelectionAction` phải được đăng ký trong Spring ApplicationContext. Nếu view dùng Spring MVC/JSP thay vì JSF, cách lấy dòng được chọn sẽ khác; phần sau trình bày biến thể dùng ID được binding.

### 5.1. Vì sao dùng on-render để tải kết quả?

`on-render` gom logic chuẩn bị dữ liệu ngay trước khi view hiển thị. Nhờ vậy, cả lần vào màn hình đầu tiên, tìm kiếm mới và chuyển trang đều đi qua cùng một chỗ tải dữ liệu.

Trình tự một event `next`:

~~~mermaid
sequenceDiagram
    participant User as Người dùng
    participant View as searchResults view
    participant Flow as Spring Web Flow
    participant Service as HotelSearchService
    User->>View: Nhấn Next
    View->>Flow: Event next
    Flow->>Flow: searchCriteria.nextPage(page)
    Flow->>Service: on-render: search(criteria)
    Service-->>Flow: HotelSearchPage mới
    Flow->>View: Render resultsPanel
    View-->>User: Trang kết quả tiếp theo
~~~

Vì `on-render` chạy ở cả lần render toàn trang và fragment, service sẽ được gọi lại sau mỗi event yêu cầu render. Đây là hành vi mong muốn để dữ liệu phản ánh page number mới. Nếu truy vấn tốn kém, tối ưu truy vấn, cache có thời hạn hoặc chỉ render fragment cần thiết; không chuyển việc tải dữ liệu vào getter của DTO.

## 6. Giao diện JSF: bảng kết quả và event

Ví dụ JSF dùng `DataModel` để hiển thị danh sách và cung cấp `selectedRow`:

~~~xhtml
<h:form id="searchForm">

    <h:panelGrid columns="2">
        <h:outputLabel for="keyword" value="Tên khách sạn" />
        <h:inputText id="keyword"
                     value="#{searchCriteria.keyword}" />

        <h:outputLabel for="city" value="Thành phố" />
        <h:inputText id="city"
                     value="#{searchCriteria.city}" />

        <h:outputLabel for="sort" value="Sắp xếp" />
        <h:selectOneMenu id="sort"
                         value="#{searchCriteria.sort}">
            <f:selectItem itemValue="name" itemLabel="Tên" />
            <f:selectItem itemValue="rating" itemLabel="Đánh giá" />
            <f:selectItem itemValue="price" itemLabel="Giá" />
        </h:selectOneMenu>
    </h:panelGrid>

    <h:commandButton value="Tìm kiếm" action="search">
        <f:ajax execute="@form" render="resultsPanel" />
    </h:commandButton>
    <h:commandButton value="Xóa bộ lọc" action="clear">
        <f:ajax execute="@form" render="resultsPanel" />
    </h:commandButton>

    <h:panelGroup id="resultsPanel" layout="block">

        <h:outputText
            value="Trang #{page.pageNumber + 1} / #{page.totalPages}" />

        <h:dataTable value="#{results}" var="hotel">
            <h:column>
                <f:facet name="header">Tên khách sạn</f:facet>
                <h:outputText value="#{hotel.name}" />
            </h:column>

            <h:column>
                <f:facet name="header">Thành phố</f:facet>
                <h:outputText value="#{hotel.city}" />
            </h:column>

            <h:column>
                <f:facet name="header">Đánh giá</f:facet>
                <h:outputText value="#{hotel.rating}" />
            </h:column>

            <h:column>
                <h:commandLink value="Chọn" action="select" />
            </h:column>
        </h:dataTable>

        <h:commandLink value="Trang trước"
                       action="previous"
                       rendered="#{page.hasPrevious}">
            <f:ajax execute="@form" render="resultsPanel" />
        </h:commandLink>

        <h:commandLink value="Trang sau"
                       action="next"
                       rendered="#{page.hasNext}">
            <f:ajax execute="@form" render="resultsPanel" />
        </h:commandLink>

    </h:panelGroup>
</h:form>
~~~

Các command button/link phát event theo action outcome tương ứng với ID transition trong view-state. Khi người dùng chọn một dòng trong `h:dataTable`, `DataModel` xác định `selectedRow` cho event `select`. Cấu hình fragment trong flow phải khớp client ID của vùng cần render; với form có ID `searchForm` và panel có ID `resultsPanel`, ví dụ dùng `searchForm:resultsPanel`.

Nếu không dùng Ajax, có thể bỏ `<render fragments="..."/>` và để SWF render lại toàn bộ view. Nếu dùng Ajax, cấu hình JSF Ajax phù hợp để request chỉ cập nhật vùng kết quả; partial rendering không tự xuất hiện chỉ vì có tên fragment trong XML.

## 7. Chọn dòng và đưa dữ liệu qua flow scope

`DataModel.selectedRow` tiện cho JSF, nhưng không nên coi object đó là bằng chứng quyền truy cập. Trước khi rời màn hình tìm kiếm, action cần xác minh lựa chọn và tải DTO hợp lệ cho người dùng hiện tại.

~~~java
package com.example.hotel.search;

import java.security.Principal;

import org.springframework.binding.message.MessageBuilder;
import org.springframework.webflow.execution.RequestContext;

public class HotelSelectionAction {

    private final HotelAccessService hotelAccessService;

    public HotelSelectionAction(HotelAccessService hotelAccessService) {
        this.hotelAccessService = hotelAccessService;
    }

    public boolean select(
            HotelSummary selectedRow,
            HotelSearchPage currentPage,
            Principal currentUser,
            RequestContext context) {

        if (selectedRow == null
                || currentPage == null
                || !currentPage.contains(selectedRow.getId())
                || currentUser == null) {
            context.getMessageContext().addMessage(
                new MessageBuilder()
                    .error()
                    .defaultText("Hãy chọn một khách sạn hợp lệ.")
                    .build()
            );
            return false;
        }

        HotelSummary selected = hotelAccessService.findVisibleHotel(
            selectedRow.getId(),
            currentUser.getName()
        );

        if (selected == null) {
            context.getMessageContext().addMessage(
                new MessageBuilder()
                    .error()
                    .defaultText("Khách sạn không còn khả dụng.")
                    .build()
            );
            return false;
        }

        context.getFlowScope().put("selectedItem", selected);
        return true;
    }
}
~~~

Transition action trả về `boolean`. Theo cơ chế transition action của Web Flow, `false` ngăn transition đi tới state đích; view hiện tại được render lại và có thể hiển thị message. Khi trả về `true`, object đã kiểm tra được lưu vào `flowScope.selectedItem` để state kế tiếp dùng.

Trong ví dụ, `HotelAccessService.findVisibleHotel(...)` phải thực hiện truy vấn có kiểm tra quyền ở server. `HotelSearchService` và `HotelAccessService` là hai hợp đồng service minh họa; có thể gộp nếu kiến trúc ứng dụng phù hợp, nhưng quy tắc quyền phải được thực thi tại server.

### 7.1. Dữ liệu nào nên đưa sang flowScope?

Nếu state tiếp theo cần dữ liệu mới nhất, hãy tải lại bằng service dựa trên ID và principal:

~~~xml
<view-state id="reviewSelected" view="hotels/selected">
    <on-render>
        <evaluate expression="hotelDetailsService.loadForReview(
                                  flowScope.selectedItem.id,
                                  currentUser)"
                  result="viewScope.hotelDetails" />
    </on-render>
</view-state>
~~~

Không dùng object trong flow scope làm nguồn sự thật cho giá, tình trạng phòng hoặc quyền sở hữu nếu các giá trị đó có thể thay đổi sau khi người dùng tìm kiếm.

## 8. Biến thể Spring MVC/JSP: gửi selectedItemId

`DataModel.selectedRow` là cách thuận tiện khi dùng JSF DataTable. Với Spring MVC/JSP, một cách phổ biến là hiển thị radio button cho từng kết quả và binding `selectedItemId` vào criteria.

Binder cần cho phép property đó:

~~~xml
<binder>
    <binding property="keyword" />
    <binding property="city" />
    <binding property="sort" />
    <binding property="selectedItemId" />
</binder>
~~~

Trong JSP, form gửi event `select` cùng ID của dòng được chọn:

~~~jsp
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>

<form:form method="post"
           action="${flowExecutionUrl}"
           modelAttribute="searchCriteria">

    <form:input path="keyword" />
    <form:input path="city" />

    <button type="submit" name="_eventId_search">Tìm kiếm</button>

    <div id="resultsPanel">
        <c:forEach items="${page.items}" var="hotel">
            <label>
                <form:radiobutton path="selectedItemId" value="${hotel.id}" />
                <c:out value="${hotel.name}" /> -
                <c:out value="${hotel.city}" />
            </label>
        </c:forEach>

        <c:if test="${page.hasPrevious}">
            <button type="submit" name="_eventId_previous">Trang trước</button>
        </c:if>
        <c:if test="${page.hasNext}">
            <button type="submit" name="_eventId_next">Trang sau</button>
        </c:if>
        <button type="submit" name="_eventId_select">Chọn khách sạn</button>
        <form:errors path="selectedItemId" cssClass="error" />
    </div>
</form:form>
~~~

Trong JSP, EL đọc `flowExecutionUrl`, `page.items` và thuộc tính của từng `hotel`. Dùng `<c:out>` cho nội dung văn bản để escape HTML. Event được phát qua tên nút `_eventId_<eventId>`. Dữ liệu `selectedItemId` được binding vào model theo binder.

Transition `select` có thể gọi action kiểm tra ID thuộc trang hiện tại và người dùng có quyền xem, sau đó lưu DTO đã xác minh vào flow scope:

~~~xml
<transition on="select" to="reviewSelected">
    <evaluate expression="hotelSelectionAction.selectById(
        searchCriteria.selectedItemId,
        page,
        currentUser,
        flowRequestContext)" />
</transition>
~~~

Method `selectById(...)` thực hiện cùng quy tắc kiểm tra như action JSF: xác minh ID có trong `page.items`, truy vấn lại quyền của người dùng và chỉ ghi `flowScope.selectedItem` khi hợp lệ. Ví dụ phần thân method:

~~~java
public boolean selectById(
        String hotelId,
        HotelSearchPage currentPage,
        Principal currentUser,
        RequestContext context) {

    if (hotelId == null || currentPage == null
            || !currentPage.contains(hotelId) || currentUser == null) {
        context.getMessageContext().addMessage(
            new MessageBuilder().error()
                .defaultText("Hãy chọn một khách sạn hợp lệ.").build());
        return false;
    }

    HotelSummary selected = hotelAccessService.findVisibleHotel(
        hotelId, currentUser.getName());
    if (selected == null) {
        context.getMessageContext().addMessage(
            new MessageBuilder().error()
                .defaultText("Khách sạn không còn khả dụng.").build());
        return false;
    }

    context.getFlowScope().put("selectedItem", selected);
    return true;
}
~~~

Nếu method trả về `false`, transition không rời `searchResults`. Không dùng hidden field hoặc radio value như căn cứ duy nhất cho quyền truy cập; người dùng có thể sửa request để gửi ID khác.

## 9. Phân trang an toàn và ổn định

Phân trang không chỉ là tăng hoặc giảm số trang. Cần xử lý các trường hợp dữ liệu thay đổi, người dùng gửi event bất thường và truy vấn quá lớn.

| Tình huống | Cách xử lý |
|---|---|
| Đang ở trang đầu, nhận event `previous` | Giữ `pageNumber = 0` |
| Đang ở trang cuối, nhận event `next` | Không tăng page number |
| Bộ lọc thay đổi | Reset về trang đầu |
| Không có kết quả | `items` rỗng, `totalPages = 0`, ẩn điều khiển trang |
| Dữ liệu bị xóa giữa hai request | Clamp page về trang hợp lệ |
| Client gửi sort key lạ | Dùng allowlist hoặc sort mặc định |
| Client gửi page size quá lớn | Dùng page size do server kiểm soát |
| Người dùng chọn ID ngoài trang | Từ chối hoặc tải lại theo chính sách quyền |

Nếu dùng offset pagination trên bảng rất lớn, các trang sâu có thể chậm vì database phải bỏ qua nhiều bản ghi. Khi đó cân nhắc keyset/cursor pagination, nhưng vẫn giữ cùng mô hình event trong view-state: `next` thay cursor, `previous` dùng cursor lịch sử đã lưu.

Một chi tiết khác là thứ tự kết quả phải ổn định. Nếu sort theo rating nhưng nhiều khách sạn cùng rating, thêm ID làm tie-breaker để chuyển trang không lặp hoặc bỏ sót bản ghi khi dữ liệu ít thay đổi.

## 10. Tìm kiếm và phân trang bằng Ajax fragment

Khi danh sách dài hoặc muốn giao diện phản hồi nhanh, chỉ render vùng kết quả thay vì tải lại toàn bộ view. Trong transition, `<render fragments="..."/>` yêu cầu SWF render các fragment đã chỉ định sau khi xử lý event.

~~~xml
<transition on="next">
    <evaluate expression="searchCriteria.nextPage(page)" />
    <render fragments="searchForm:resultsPanel" />
</transition>
~~~

Vùng `searchForm:resultsPanel` là component cần render lại trong view. ID chính xác phụ thuộc view technology và naming container; với JSF, thường cần client ID đầy đủ. Nếu dùng JSP/Ajax handler khác, cấu hình fragment theo cơ chế của view technology tương ứng.

Luồng Ajax:

1. Người dùng bấm Next.
2. View gửi event `next`.
3. Transition tăng page number nếu còn trang.
4. `on-render` truy vấn trang mới và cập nhật `viewScope.page`/`viewScope.results`.
5. SWF render fragment kết quả.
6. Phần còn lại của trang giữ nguyên.

`on-render` được gọi trước render toàn view và partial render. Vì vậy action này phải an toàn khi chạy nhiều lần, không ghi dữ liệu nghiệp vụ hoặc gửi email. Nó chỉ nên tải dữ liệu cần hiển thị.

## 11. Kiểm thử các event trong cùng một view-state

Flow test cần xác minh không chỉ nội dung trang mà cả **state hiện tại** sau từng event. `search`, `next` và `previous` phải giữ state `searchResults`; `select` hợp lệ mới chuyển sang `reviewSelected`.

Ma trận kiểm thử:

| Ca kiểm thử | Event | Kết quả mong đợi |
|---|---|---|
| Vào màn hình lần đầu | Start flow | State `searchResults`, tải trang đầu |
| Tìm theo từ khóa | `search` | Giữ `searchResults`, page number về 0 |
| Tìm theo city | `search` | Kết quả chỉ chứa city phù hợp |
| Chuyển trang | `next` | Giữ state, page number tăng khi `hasNext` |
| Quay lại | `previous` | Giữ state, page number giảm nhưng không dưới 0 |
| Bấm Next ở trang cuối | `next` | Không vượt trang cuối |
| Xóa filter | `clear` | Criteria về mặc định, hiển thị trang đầu |
| Chọn kết quả hợp lệ | `select` | Chuyển `reviewSelected`, flow scope có DTO đã xác minh |
| Không chọn dòng | `select` | Ở lại `searchResults`, có message hướng dẫn |
| ID bị sửa trong request | `select` | Service từ chối, không mở dữ liệu trái quyền |
| Người dùng không có quyền | `select` | Ở lại state tìm kiếm hoặc hiển thị lỗi phù hợp |
| Không có kết quả | `search` | Danh sách rỗng, không lỗi index |
| Refresh view | GET execution URL | Kết quả được tải lại theo criteria trong view scope |

### 11.1. Ví dụ flow execution test

Test support SWF 2.x có thể dùng `AbstractXmlFlowExecutionTests`, `MockExternalContext`, `startFlow(...)` và `resumeFlow(...)`. Ví dụ dưới đây giả định flow XML được nạp bởi test fixture và service tìm kiếm được thay bằng fake:

~~~java
public void testSearchAndPaginationStayInOneViewState() {
    MockExternalContext context = new MockExternalContext();
    startFlow(context);

    assertCurrentStateEquals("searchResults");
    assertEquals(0, fakeHotelSearchService.getLastPageNumber());

    MockExternalContext searchContext = new MockExternalContext();
    searchContext.setEventId("search");
    searchContext.putRequestParameter("keyword", "Da Lat");
    resumeFlow(searchContext);

    assertCurrentStateEquals("searchResults");
    assertEquals(0, fakeHotelSearchService.getLastPageNumber());
    assertEquals("Da Lat", fakeHotelSearchService.getLastKeyword());

    MockExternalContext nextContext = new MockExternalContext();
    nextContext.setEventId("next");
    resumeFlow(nextContext);

    assertCurrentStateEquals("searchResults");
    assertEquals(1, fakeHotelSearchService.getLastPageNumber());

    MockExternalContext previousContext = new MockExternalContext();
    previousContext.setEventId("previous");
    resumeFlow(previousContext);

    assertCurrentStateEquals("searchResults");
    assertEquals(0, fakeHotelSearchService.getLastPageNumber());
}
~~~

Test minh họa các event handler giữ nguyên state. Trong test thật, fake service phải cung cấp ít nhất hai trang để `hasNext()` trả true; mỗi context mới đại diện một request mới. Tên helper và chữ ký test base cần khớp phiên bản Spring Web Flow/test support mà dự án sử dụng.

### 11.2. Kiểm thử selection riêng

Với JSF `DataModel`, kiểm tra action nhận đúng dòng được chọn và chuyển sang state chi tiết. Với JSP, gửi `selectedItemId` như request parameter rồi xác minh binder/action xử lý nó. Trong cả hai trường hợp, test service authorization riêng để bảo đảm ID ngoài phạm vi người dùng bị từ chối.

Không dùng test flow unit để kết luận Ajax fragment, JSF component tree, JSP render, URL execution và Spring Security filter chain đã hoạt động. Các phần đó cần MVC/view integration test tương ứng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bấm Next nhưng không đổi trang | Method `nextPage()` không cập nhật criteria hoặc page hiện tại không có trang tiếp | Kiểm tra `hasNext` và page number |
| Bấm Next làm chuyển sang state khác | Transition có `to` ngoài ý muốn | Bỏ `to` để dùng event handler |
| Kết quả không cập nhật sau tìm kiếm | Không gọi lại service ở `on-render` hoặc fragment không được render | Kiểm tra lifecycle và fragment ID |
| Search chạy hai lần | Gọi service cả trong transition và `on-render` | Để transition chỉ cập nhật criteria; tải dữ liệu ở `on-render` |
| Chọn dòng trả về null | Kết quả không được bọc thành `DataModel` hoặc view không dùng đúng data model | Dùng `result-type="dataModel"` khi cần `selectedRow` |
| JSP không binding được selected ID | Binder chưa cho phép property hoặc tên request không khớp | Thêm `selectedItemId` vào binder |
| Chuyển trang làm mất filter | Criteria bị tạo lại ở mỗi request hoặc đặt sai scope | Giữ criteria trong view scope của state |
| Quay lại màn hình tìm kiếm mất điều kiện | View scope đã bị hủy khi rời state | Dùng flow scope nếu cần giữ filter qua nhiều state |
| Trang cuối không có kết quả | Dữ liệu thay đổi hoặc page number vượt giới hạn | Clamp page number ở service |
| Bảng lặp hoặc bỏ sót dòng giữa các trang | Sort không có tie-breaker ổn định | Thêm khóa duy nhất vào thứ tự sắp xếp |
| Có thể chọn ID ngoài danh sách | Tin request parameter/hidden field | Kiểm tra membership và quyền ở service |
| Ajax tải lại toàn trang | Request không phải Ajax hoặc fragment ID không đúng | Kiểm tra Ajax handler và fragment naming |
| `on-render` gây side effect lặp | Dùng render action để ghi dữ liệu | Chỉ tải dữ liệu trong `on-render`; ghi ở transition/action phù hợp |

## 13. Bài tập thực hành

Xây dựng màn hình tìm kiếm sản phẩm trong một view-state `searchProducts`:

- Bộ lọc gồm keyword, danh mục và trạng thái còn hàng.
- Kết quả hiển thị 10 sản phẩm mỗi trang.
- Người dùng có thể tìm kiếm, sang trang tiếp theo, quay lại và chọn một sản phẩm.
- Khi chọn, flow chuyển tới state `reviewProduct` với DTO sản phẩm đã được service kiểm tra quyền hiển thị.

Yêu cầu:

1. Tạo `ProductSearchCriteria` trong view scope.
2. Tạo `ProductSearchPage` chứa danh sách, số trang và cờ `hasNext`/`hasPrevious`.
3. Tải kết quả trong `on-render`.
4. Khai báo binder allowlist cho đúng các trường filter; không bind page size.
5. Tạo event handler không có `to` cho `search`, `next`, `previous` và `clear`.
6. Dùng `<render fragments="..."/>` để cập nhật vùng kết quả khi chạy Ajax.
7. Thực hiện event `select` để chuyển state; kiểm tra ID và quyền người dùng ở service.
8. Viết flow test chứng minh search/pagination ở cùng state và selection đi sang state chi tiết.
9. Kiểm thử list rỗng, trang cuối, sort không hợp lệ và ID bị giả mạo.
10. Nếu dùng JSP thay cho JSF, triển khai `selectedItemId` binding và so sánh với `DataModel.selectedRow`.

**Tiêu chí hoàn thành:** người học giải thích được vì sao event handler không có `to` giữ nguyên view-state, `on-render` tải dữ liệu vào thời điểm nào, `viewScope` khác `flowScope` ra sao, fragment rendering cập nhật vùng nào, và tại sao selection phải được xác minh ở server. Khi nắm được các điểm này, một màn hình tìm kiếm có thể xử lý nhiều thao tác liên tiếp trong cùng view-state mà flow vẫn giữ cấu trúc rõ ràng.

## Tài liệu tham khảo

- Spring Web Flow 2.5.1 Reference Guide — [Rendering Views](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/views.html): view-state, view scope, on-render, binding, event handlers và fragment rendering.
- Spring Web Flow 2.5.1 Reference Guide — [JSF Integration](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/): DataModel, chọn dòng trong data table và các event tìm kiếm/phân trang.
- Spring Web Flow 2.5.1 Reference Guide — [Testing Flows](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/testing.html): kiểm thử flow definition và flow execution.

*Ghi chú tương thích:* Cú pháp XML và test API trong ví dụ theo Spring Web Flow 2.5.x. `DataModel.selectedRow` là cách chọn dòng phù hợp với view technology hỗ trợ Web Flow DataModel (đặc biệt JSF); với Spring MVC/JSP, dùng binding ID hoặc cơ chế chọn dòng của view. Kiểm tra API, component ID của fragment và cấu hình Ajax theo phiên bản thực tế.
