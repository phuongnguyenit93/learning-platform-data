# Xử lý nhiều sự kiện trên cùng một màn hình

Trong **Spring Web Flow (SWF)**, một `view-state` không chỉ phục vụ một nút Tiếp tục. Cùng một màn hình có thể nhận nhiều sự kiện: tìm kiếm, lọc, sắp xếp, chuyển trang, đặt lại bộ lọc, xem chi tiết hoặc hủy. Mỗi thao tác được gửi thành một **event**; flow xác định transition phù hợp dựa trên state hiện tại.

Bài thuộc chương **View-state** của module `SPRING_WEB_FLOW`. Ta sẽ xây dựng một màn hình tìm kiếm danh mục có nhiều nút thao tác. Một số event chỉ cập nhật dữ liệu và render lại một phần màn hình; một số event điều hướng sang view-state khác. Qua ví dụ này, bạn sẽ biết cách đặt tên event, gửi event từ nhiều nút trong cùng form, dùng nhiều form trên một view, điều khiển binding/validation theo từng event, và kiểm thử toàn bộ đường đi.

Ví dụ sử dụng **Java 17, Spring Framework 6.x, Spring Web Flow 3.x, Spring MVC và Thymeleaf**. Cú pháp event decoding phụ thuộc view technology; phần HTML bên dưới minh họa cách tích hợp Spring MVC/Thymeleaf. Với JSP, FreeMarker hoặc JSF, cơ chế tạo event có thể khác nhưng flow definition vẫn có thể dùng nhiều transition trong cùng `view-state`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao một `view-state` có thể xử lý nhiều event khác nhau.
2. Phân biệt event điều hướng sang state khác với event xử lý ngay tại màn hình.
3. Gửi event từ nhiều nút submit bằng tên `_eventId_<eventId>`.
4. Chọn giữa named submit button, hidden `_eventId` và link phát event.
5. Viết nhiều transition cục bộ trong một `view-state`.
6. Dùng transition không có `to` để giữ nguyên state và render lại view.
7. Cập nhật một hoặc nhiều fragment sau event Ajax.
8. Điều khiển binding và validation theo từng event bằng `bind` và `validate`.
9. Kết hợp `on-render`, `viewScope` và `flowScope` để duy trì dữ liệu.
10. Kiểm thử từng event, dữ liệu postback và trạng thái sau khi xử lý.

Kết quả mong đợi:

~~~mermaid
flowchart TD
    A["view-state: search"] --> B["filter"]
    A --> C["nextPage"]
    A --> D["previousPage"]
    A --> E["reset"]
    A --> F["openItem"]
    B --> G["Render lại kết quả, vẫn ở search"]
    C --> G
    D --> G
    E --> G
    F --> H["view-state: details"]
~~~

Năm event cùng xuất phát từ một màn hình, nhưng chỉ `openItem` rời `search`. Bốn event còn lại thao tác trên dữ liệu hiển thị và giữ người dùng ở cùng view-state.

## 2. Một view-state có thể nhận nhiều event

`view-state` định nghĩa một bước hiển thị giao diện và chờ request tiếp theo. Khi người dùng tương tác, view gửi event về flow. Một state có thể khai báo **một hoặc nhiều phần tử `transition`**, mỗi transition nhận diện event bằng thuộc tính `on`.

Ví dụ:

~~~xml
<view-state id="search" view="catalog/search">
    <transition on="filter"/>
    <transition on="nextPage"/>
    <transition on="previousPage"/>
    <transition on="reset"/>
    <transition on="openItem" to="details"/>
</view-state>
~~~

| Event | Transition | Kết quả |
| --- | --- | --- |
| `filter` | Không có `to` | Xử lý và render lại màn hình tìm kiếm |
| `nextPage` | Không có `to` | Hiển thị trang kết quả tiếp theo |
| `previousPage` | Không có `to` | Hiển thị trang kết quả trước |
| `reset` | Không có `to` | Xóa điều kiện lọc và render lại |
| `openItem` | `to="details"` | Rời màn hình tìm kiếm để xem chi tiết |

Điểm cần nhớ:

- `on` là **tên event** mà view gửi.
- `to` là **ID state đích** trong flow.
- Transition không có `to` là event handler, không làm flow chuyển sang state khác.
- Mỗi transition chỉ được xét khi flow đang ở state chứa transition đó, trừ những transition được khai báo ở cấp global.

Một view có nhiều event không có nghĩa mỗi nút cần một controller riêng. Flow definition giữ các quy tắc điều hướng tập trung, còn view chỉ phát tín hiệu người dùng vừa chọn.

## 3. Chọn event name rõ nghĩa

Event ID là giao ước giữa view và flow XML. Nên đặt tên ngắn, thể hiện hành động và giữ ổn định:

| Hành động trên giao diện | Event ID gợi ý |
| --- | --- |
| Áp dụng điều kiện tìm kiếm | `filter` |
| Chuyển trang kế | `nextPage` |
| Quay về trang trước | `previousPage` |
| Xóa điều kiện tìm kiếm | `reset` |
| Mở một dòng kết quả | `openItem` |
| Quay lại danh sách | `back` |
| Xác nhận lựa chọn | `confirm` |
| Đóng màn hình | `close` |

Không dùng tên state làm event nếu hai khái niệm có ý nghĩa khác nhau. Ví dụ `details` là state đích, còn `openItem` là event người dùng phát ra để yêu cầu mở state đó.

Tên event nên:

- Dùng quy ước nhất quán, chẳng hạn camelCase.
- Mô tả hành động thay vì vị trí của nút.
- Không chứa dữ liệu do người dùng nhập.
- Không trùng với tên field form theo cách gây khó đọc request.
- Không dùng một event chung `submit` cho mọi nút nếu mỗi nút có ý nghĩa nghiệp vụ khác nhau.

## 4. Gửi nhiều event từ cùng một HTML form

Với view Spring MVC, Web Flow hỗ trợ named submit button. Mỗi nút có tên bắt đầu bằng `_eventId_`; phần còn lại của tên là event ID.

~~~html
<form method="post"
      th:action="${flowExecutionUrl}"
      th:object="${criteria}">

    <label for="keyword">Từ khóa</label>
    <input id="keyword" type="search" th:field="*{keyword}">

    <label for="category">Danh mục</label>
    <select id="category" th:field="*{category}">
        <option value="">Tất cả</option>
        <option value="BOOK">Sách</option>
        <option value="COURSE">Khóa học</option>
    </select>

    <button type="submit" name="_eventId_filter" value="filter">
        Áp dụng
    </button>
    <button type="submit" name="_eventId_nextPage" value="nextPage">
        Trang sau
    </button>
    <button type="submit" name="_eventId_previousPage" value="previousPage">
        Trang trước
    </button>
    <button type="submit" name="_eventId_reset" value="reset"
            formnovalidate>
        Đặt lại
    </button>
</form>
~~~

Khi người dùng bấm **Áp dụng**, trình duyệt gửi tham số có tên `_eventId_filter`; Web Flow giải mã event ID thành `filter`. Nếu bấm **Trang sau**, event gửi lên là `nextPage`.

Chỉ submit button được nhấn mới gửi tên/value của nó. Vì vậy, nhiều nút có thể cùng nằm trong một form và cùng dùng một execution URL.

### 4.1. Event ID lấy từ tên, không lấy từ value

Với:

~~~html
<button type="submit" name="_eventId_filter" value="filter">
    Áp dụng
</button>
~~~

Event ID là `filter`, được suy ra từ phần sau `_eventId_` trong **tên parameter**. `value="filter"` giúp HTML rõ ràng nhưng không phải nguồn chính để xác định event trong cách decoding này.

### 4.2. Nút không phải submit sẽ không phát event theo cách này

~~~html
<!-- Nút này không gửi form -->
<button type="button" name="_eventId_filter">Áp dụng</button>
~~~

`type="button"` chỉ là nút giao diện. Nó không gửi request và không tạo event Web Flow nếu không có JavaScript/Ajax riêng thực hiện request. Nếu muốn dùng cơ chế form chuẩn, hãy dùng `type="submit"`.

### 4.3. Không đặt hidden _eventId cố định cùng named button

Có một cách khác là hidden field:

~~~html
<input type="hidden" name="_eventId" value="filter">
~~~

Spring MVC view decoding tìm parameter `_eventId` trước; nếu không có mới tìm parameter bắt đầu bằng `_eventId_`. Vì vậy, nếu form có hidden `_eventId=filter` và đồng thời có named button `_eventId_reset`, hidden field có thể khiến request luôn được giải mã thành `filter`.

**Chọn một cách phát event cho mỗi form.** Với form nhiều nút, dùng named submit button. Với form chỉ có một event, hidden `_eventId` có thể phù hợp.

## 5. Dùng nhiều form độc lập trên cùng view

Không phải mọi thao tác đều cần chung một form. Ví dụ trang danh sách có:

- Một form lọc danh sách.
- Một form riêng cho từng dòng để mở chi tiết.
- Một form riêng để xuất dữ liệu.

Mỗi form có thể gửi một event riêng:

~~~html
<form method="post" th:action="${flowExecutionUrl}"
      th:object="${criteria}">
    <input type="search" th:field="*{keyword}">
    <button type="submit" name="_eventId_filter">Tìm</button>
</form>

<div id="resultsPanel">
    <article th:each="item : ${results}">
        <h2 th:text="${item.name}">Tên mặt hàng</h2>
        <form method="post" th:action="${flowExecutionUrl}">
            <input type="hidden" name="itemId" th:value="${item.id}">
            <button type="submit" name="_eventId_openItem">
                Xem chi tiết
            </button>
        </form>
    </article>
</div>
~~~

Ở ví dụ này, form lọc gửi dữ liệu `criteria`; form dòng kết quả gửi `itemId` và event `openItem`. Transition `openItem` có thể đặt `bind="false"` nếu không muốn request của form dòng kết quả bind lại model tìm kiếm.

Không lồng form HTML bên trong form khác. Nếu cần một nút thao tác trên mỗi dòng, hãy dùng form riêng hoặc cơ chế HTML `form` attribute với ID form phù hợp.

## 6. Ví dụ hoàn chỉnh: màn hình tìm kiếm có năm event

Ta tạo một flow danh mục:

1. Người dùng mở màn hình tìm kiếm.
2. Nhập từ khóa/danh mục rồi bấm Áp dụng.
3. Bấm Trang sau hoặc Trang trước để thay đổi trang kết quả.
4. Bấm Đặt lại để xóa điều kiện tìm kiếm.
5. Bấm Xem chi tiết ở một dòng để chuyển sang màn hình chi tiết.
6. Từ chi tiết, bấm Quay lại để về tìm kiếm.

### 6.1. Flow XML

Tạo `src/main/resources/flows/catalog/catalog-flow.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
        http://www.springframework.org/schema/webflow
        https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="criteria"
         class="com.example.catalog.SearchCriteria"/>

    <view-state id="search"
                view="catalog/search"
                model="criteria">

        <binder>
            <binding property="keyword"/>
            <binding property="category"/>
            <binding property="page"/>
            <binding property="pageSize"/>
        </binder>

        <on-render>
            <evaluate expression="catalogService.search(criteria)"
                      result="viewScope.results"/>
        </on-render>

        <!-- Event 1: bind và validate điều kiện tìm kiếm -->
        <transition on="filter">
            <render fragments="searchSummary,resultsPanel,pager"/>
        </transition>

        <!-- Event 2: giữ binding nhưng bỏ validation -->
        <transition on="nextPage" validate="false">
            <evaluate expression="criteria.nextPage()"/>
            <render fragments="resultsPanel,pager"/>
        </transition>

        <!-- Event 3: giữ binding nhưng bỏ validation -->
        <transition on="previousPage" validate="false">
            <evaluate expression="criteria.previousPage()"/>
            <render fragments="resultsPanel,pager"/>
        </transition>

        <!-- Event 4: không bind dữ liệu form cũ -->
        <transition on="reset" bind="false">
            <evaluate expression="criteria.reset()"/>
            <render fragments="searchForm,searchSummary,resultsPanel,pager"/>
        </transition>

        <!-- Event 5: rời màn hình tìm kiếm để xem chi tiết -->
        <transition on="openItem" to="details" bind="false">
            <evaluate expression="catalogService.findById(requestParameters.itemId)"
                      result="flowScope.selectedItem"/>
        </transition>
    </view-state>

    <view-state id="details" view="catalog/details">
        <transition on="back" to="search" validate="false"/>
    </view-state>
</flow>
~~~

Các transition `filter`, `nextPage`, `previousPage`, `reset` không có `to`, nên chúng xử lý event trong state `search` và render lại view/fragment. Transition `openItem` có `to="details"`, nên flow rời `search` và chuyển sang state chi tiết.

`criteria` là flow variable, sống qua các state trong cùng flow execution. `viewScope.results` chứa dữ liệu kết quả cho view hiện tại và được cập nhật trong mỗi lần render. Khi người dùng quay lại `search`, `on-render` truy vấn lại dữ liệu theo `criteria` hiện tại.

### 6.2. Model tìm kiếm

~~~java
package com.example.catalog;

import java.io.Serializable;

public class SearchCriteria implements Serializable {
    private static final long serialVersionUID = 1L;

    private String keyword;
    private String category;
    private int page = 0;
    private int pageSize = 10;

    public String getKeyword() { return keyword; }
    public void setKeyword(String keyword) { this.keyword = keyword; }

    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }

    public int getPage() { return page; }
    public void setPage(int page) { this.page = Math.max(0, page); }

    public int getPageSize() { return pageSize; }
    public void setPageSize(int pageSize) {
        this.pageSize = Math.max(1, Math.min(pageSize, 100));
    }

    public void nextPage() {
        page++;
    }

    public void previousPage() {
        page = Math.max(0, page - 1);
    }

    public void reset() {
        keyword = null;
        category = null;
        page = 0;
        pageSize = 10;
    }
}
~~~

Đây là model minh họa. Trong ứng dụng thật, server vẫn phải kiểm tra page/pageSize và giới hạn truy vấn. Không tin các giá trị hidden field hoặc input từ client chỉ vì binder đã chuyển chúng vào model.

### 6.3. View tìm kiếm với các event

Tạo `templates/catalog/search.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Tìm kiếm danh mục</title>
</head>
<body>
    <h1>Tìm kiếm danh mục</h1>

    <form id="searchForm" method="post"
          th:action="${flowExecutionUrl}"
          th:object="${criteria}">
        <label for="keyword">Từ khóa</label>
        <input id="keyword" type="search" th:field="*{keyword}">

        <label for="category">Danh mục</label>
        <select id="category" th:field="*{category}">
            <option value="">Tất cả</option>
            <option value="BOOK">Sách</option>
            <option value="COURSE">Khóa học</option>
        </select>

        <button type="submit" name="_eventId_filter">Áp dụng</button>
        <button type="submit" name="_eventId_reset"
                formnovalidate>Đặt lại</button>
    </form>

    <section id="searchSummary">
        <p>Danh sách kết quả phù hợp.</p>
    </section>

    <section id="resultsPanel">
        <article th:each="item : ${results}">
            <h2 th:text="${item.name}">Tên mặt hàng</h2>
            <p th:text="${item.description}">Mô tả</p>

            <form method="post" th:action="${flowExecutionUrl}">
                <input type="hidden" name="itemId" th:value="${item.id}">
                <button type="submit" name="_eventId_openItem">
                    Xem chi tiết
                </button>
            </form>
        </article>
    </section>

    <nav id="pager" aria-label="Phân trang">
        <form method="post" th:action="${flowExecutionUrl}"
              th:object="${criteria}">
            <button type="submit" name="_eventId_previousPage"
                    th:disabled="*{page == 0}">
                Trang trước
            </button>
            <span th:text="*{page + 1}">1</span>
            <button type="submit" name="_eventId_nextPage">
                Trang sau
            </button>
        </form>
    </nav>
</body>
</html>
~~~

Trong ví dụ này, `results` được đưa vào view scope bởi `on-render`. `criteria` là flow variable nên form lọc và form phân trang đều có thể đọc model. Mỗi form có event riêng; form chi tiết gửi thêm `itemId`.

Nếu Spring Security bật CSRF, mỗi POST form cần token hợp lệ. Tích hợp Thymeleaf/Spring Security có thể tự chèn token khi dùng `th:action`; hãy kiểm tra HTML cuối cùng thay vì giả định token luôn có mặt.

### 6.4. View chi tiết

Tạo `templates/catalog/details.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Chi tiết</title>
</head>
<body>
    <h1 th:text="${selectedItem.name}">Tên mặt hàng</h1>
    <p th:text="${selectedItem.description}">Mô tả chi tiết</p>

    <form method="post" th:action="${flowExecutionUrl}">
        <button type="submit" name="_eventId_back">Quay lại kết quả</button>
    </form>
</body>
</html>
~~~

Flow variable `selectedItem` được tạo khi event `openItem` chạy. Trong ứng dụng thật, `catalogService.findById` phải kiểm tra bản ghi tồn tại và người dùng có quyền xem bản ghi đó.

## 7. Transition có target và event handler không có target

Hai loại transition có ý nghĩa khác nhau:

| Đặc điểm | Có `to` | Không có `to` |
| --- | --- | --- |
| Có chuyển state? | Có | Không |
| View-state hiện tại | Bị rời | Được giữ |
| ViewScope | Bị hủy khi rời state | Tiếp tục tồn tại |
| Render | View của state đích | View hiện tại hoặc fragment |
| Ví dụ | `openItem` → `details` | `nextPage`, `reset` |

### 7.1. Event handler

Một transition không có target được gọi là **event handler**:

~~~xml
<transition on="nextPage">
    <evaluate expression="criteria.nextPage()"/>
</transition>
~~~

Event handler thực thi action rồi render lại view hiện tại. Nếu không khai báo `<render fragments="..."/>`, view hiện tại được render lại theo cơ chế view integration.

### 7.2. Khi nào nên giữ nguyên state?

Dùng event handler khi hành động chỉ thay đổi dữ liệu trong cùng màn hình:

- Lọc kết quả.
- Chuyển trang.
- Sắp xếp danh sách.
- Mở/đóng phần nội dung mở rộng.
- Tính lại tổng tiền hoặc bản xem trước.
- Xóa bộ lọc và hiển thị kết quả mặc định.

Nếu hành động cần một màn hình mới, một quy trình xử lý riêng hoặc kết thúc flow, hãy dùng transition có target.

### 7.3. Không dùng self-transition chỉ để render lại

Có thể khai báo transition trỏ về chính state hiện tại, nhưng điều này khác event handler không target: flow rời state rồi vào lại state. ViewScope và lifecycle `on-entry`/`on-render` có thể bị chạy lại theo vòng đời vào state. Nếu chỉ cần cập nhật một phần nội dung, event handler không target thường thể hiện đúng ý định hơn.

## 8. Render fragment sau một event

Khi một event chỉ thay đổi một vùng của màn hình, có thể dùng `<render>` để yêu cầu Web Flow render một hoặc nhiều fragment:

~~~xml
<transition on="nextPage" validate="false">
    <evaluate expression="criteria.nextPage()"/>
    <render fragments="resultsPanel,pager"/>
</transition>
~~~

`fragments` tham chiếu ID phần tử trong view:

~~~html
<section id="resultsPanel">
    <!-- Kết quả tìm kiếm -->
</section>

<nav id="pager">
    <!-- Điều khiển phân trang -->
</nav>
~~~

Tên fragment phải khớp ID trong template. Có thể liệt kê nhiều ID, phân tách bằng dấu phẩy. Cơ chế này thường được dùng với Ajax để chỉ cập nhật vùng cần thiết.

### 8.1. Event Ajax và event submit thông thường

- Với request Ajax được tích hợp đúng, Web Flow có thể trả phần fragment được yêu cầu để client cập nhật.
- Với request không phải Ajax, flow có thể render lại view hiện tại theo cơ chế redirect/render của cấu hình.
- Thêm `<render>` vào XML không tự tạo JavaScript hoặc tự biến một nút thành Ajax request.

Hãy xác minh Ajax handler/view factory của dự án. Nếu đang dùng Thymeleaf, JSP hoặc JSF, cách đánh dấu request Ajax và cách trích fragment có thể khác nhau.

### 8.2. On-render chạy lại khi fragment được render

`on-render` được thực thi ở lần render ban đầu và những lần render tiếp theo, bao gồm refresh/partial re-render. Vì vậy:

- Có thể đặt truy vấn đọc dữ liệu và cập nhật `viewScope`.
- Không nên đặt thao tác ghi, gửi email, trừ tiền hoặc tạo đơn hàng vào `on-render`.
- Action render nên an toàn khi chạy nhiều lần.
- Nếu dữ liệu đã được tính trong transition, cân nhắc lưu kết quả vào scope để tránh truy vấn trùng không cần thiết.

## 9. Điều khiển binding và validation theo từng nút

Khi `view-state` khai báo `model`, Web Flow bind dữ liệu form vào model khi nhận view event. Sau binding, validation được chạy nếu được bật và có validator tương ứng. Mỗi transition có thể thay đổi hai bước này.

| Cấu hình | Binding | Validation | Trường hợp dùng |
| --- | --- | --- | --- |
| Mặc định | Có | Có | Áp dụng bộ lọc hoặc tiếp tục với dữ liệu nhập |
| `bind="false"` | Không | Không | Reset/hủy mà không nhận dữ liệu form hiện tại |
| `validate="false"` | Có | Không | Phân trang hoặc quay lại, vẫn giữ dữ liệu đã nhập |

### 9.1. Filter: bind và validate bình thường

~~~xml
<transition on="filter">
    <render fragments="resultsPanel,pager"/>
</transition>
~~~

Event `filter` cần nhận các field từ form, bind vào `criteria` rồi kiểm tra dữ liệu. Nếu binding/validation thất bại, Web Flow render lại view để người dùng sửa.

### 9.2. Phân trang: bind nhưng bỏ validation

~~~xml
<transition on="nextPage" validate="false">
    <evaluate expression="criteria.nextPage()"/>
    <render fragments="resultsPanel,pager"/>
</transition>
~~~

Người dùng có thể đang nhập từ khóa chưa hoàn chỉnh nhưng vẫn muốn bấm trang kế hoặc quay lại. `validate="false"` bỏ validation cho event này, trong khi dữ liệu form vẫn được bind.

### 9.3. Reset: bỏ binding và validation

~~~xml
<transition on="reset" bind="false">
    <evaluate expression="criteria.reset()"/>
    <render fragments="searchForm,searchSummary,resultsPanel,pager"/>
</transition>
~~~

Nếu không dùng `bind="false"`, các giá trị người dùng vừa nhập có thể được bind trước khi action reset chạy. Với một nút reset có ý nghĩa bỏ toàn bộ dữ liệu form, bỏ binding giúp hành vi rõ ràng hơn.

### 9.4. Chỉ cho phép bind field cần thiết

Nếu không khai báo `<binder>`, các public property của model có thể đủ điều kiện binding. Trong màn hình có nhiều event, điều này đặc biệt đáng chú ý vì mọi event có binding đều có thể nhận request parameters.

Hãy khai báo danh sách property cho phép:

~~~xml
<view-state id="search" model="criteria">
    <binder>
        <binding property="keyword"/>
        <binding property="category"/>
        <binding property="page"/>
        <binding property="pageSize"/>
    </binder>
</view-state>
~~~

Không đưa `ownerId`, `role`, `price`, `approved` hoặc các field đặc quyền vào model form chỉ để tiện hiển thị. `bind="false"`/`validate="false"` không thay thế authorization hay kiểm tra dữ liệu ở service.

## 10. Transition action và thứ tự thực thi

Một transition có thể chứa một hoặc nhiều action trước khi hoàn tất. Action có thể:

- Cập nhật model hoặc criteria.
- Gọi service đọc dữ liệu.
- Kiểm tra điều kiện nghiệp vụ.
- Thêm message vào `messageContext`.
- Trả kết quả cho phép hoặc ngăn transition tiếp tục.

Ví dụ event xác nhận một lựa chọn:

~~~xml
<transition on="confirm" to="completed">
    <evaluate expression="catalogActions.confirmSelection(
        criteria, messageContext)"/>
</transition>
~~~

Một phương thức Java trả `boolean` có thể điều khiển việc transition có tiếp tục hay không:

~~~java
public boolean confirmSelection(
        SearchCriteria criteria,
        MessageContext messages) {
    if (!selectionIsStillAvailable(criteria)) {
        messages.addMessage(new MessageBuilder()
            .error()
            .defaultText("Lựa chọn không còn khả dụng. Hãy chọn lại.")
            .build());
        return false;
    }
    return true;
}
~~~

`true` cho phép transition chạy; `false` ngăn việc rời view-state và view được render lại. Với phương thức trả `String`, các kết quả `success`, `yes` hoặc `true` cho phép transition; giá trị khác ngăn transition.

### 10.1. Nhiều action có thứ tự

Nếu transition khai báo nhiều action, chúng được thực thi theo thứ tự. Nếu một action trả kết quả lỗi, các action còn lại trong chuỗi không được chạy. Khi cần bảo đảm nhiều bước luôn được điều phối cùng nhau, hãy gom chúng vào một method facade thay vì chia thành nhiều action độc lập.

### 10.2. Tránh side effect trong event handler có thể lặp

Các event `filter`, `nextPage`, `previousPage`, `reset` có thể được gửi lại do refresh, retry hoặc người dùng bấm liên tục. Hãy giữ chúng ở mức cập nhật tiêu chí và đọc dữ liệu. Với thao tác ghi như tạo đơn hàng, thanh toán hoặc gửi thông báo, cần transaction và idempotency ở service/database.

## 11. Global transitions khi event dùng chung nhiều màn hình

Nếu một event có cùng ý nghĩa ở mọi view, có thể khai báo `global-transitions`:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <global-transitions>
        <transition on="help" to="help"/>
        <transition on="logout" to="logout"/>
    </global-transitions>

    <view-state id="search" view="catalog/search">
        <transition on="filter"/>
    </view-state>

    <view-state id="details" view="catalog/details">
        <transition on="back" to="search"/>
    </view-state>

    <end-state id="help" view="common/help"/>
    <end-state id="logout"/>
</flow>
~~~

Global transition thường dùng cho menu chung như trợ giúp hoặc đăng xuất. Không dùng global transition chỉ vì hai màn hình có nút cùng tên. Nếu `cancel` ở màn hình tìm kiếm có nghĩa đóng flow, nhưng `cancel` ở màn hình xác nhận có nghĩa quay lại sửa, hãy khai báo transition cục bộ để thể hiện đúng ngữ nghĩa.

Một global transition trong flow chỉ điều hướng flow; nó không tự thay thế logout của Spring Security hoặc xóa session.

## 12. ViewScope và FlowScope khi một màn hình có nhiều event

Một view-state tạo `viewScope` khi được vào và hủy scope đó khi rời state. Scope này phù hợp với dữ liệu phục vụ nhiều request trong cùng màn hình, đặc biệt là Ajax.

| Scope | Vòng đời | Ví dụ |
| --- | --- | --- |
| `requestScope` | Một request | Thông tin tạm cho lần render |
| `viewScope` | Trong một view-state | Kết quả hiển thị, dữ liệu phụ của fragment |
| `flowScope` | Trong một flow execution | Tiêu chí tìm kiếm cần giữ khi mở chi tiết rồi quay lại |
| `conversationScope` | Qua flow cha/subflow liên quan | Dữ liệu chia sẻ trong một quy trình lớn |

Trong ví dụ:

- `criteria` nằm ở flow scope để giữ từ khóa/danh mục khi rời `search` sang `details`.
- `viewScope.results` chứa dữ liệu kết quả cho view hiện tại và được cập nhật trong mỗi lần render.
- `on-render` tải lại `results` theo `criteria` sau mỗi event giữ nguyên view-state.

Nếu khai báo `criteria` bên trong `view-state` bằng `<var>`, nó sẽ sống theo view-state và bị hủy khi chuyển sang state khác. Hãy chọn scope theo vòng đời dữ liệu, không chỉ theo vị trí code.

## 13. Lỗi thường gặp khi xử lý nhiều event

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bấm nút nhưng không có event | Nút `type="button"` hoặc không submit form | Dùng submit button hoặc Ajax request phát event đúng |
| Luôn chạy cùng một event dù bấm nút khác | Có hidden `_eventId` cố định trong form | Chọn một cách phát event; bỏ hidden field khi dùng named buttons |
| Event không khớp transition | Tên `_eventId_...` khác `on="..."` | So khớp chính tả và chữ hoa/thường |
| Event được gửi nhưng không xử lý | State hiện tại không có transition tương ứng | Kiểm tra state và global-transitions |
| Bấm phân trang nhưng bị validation chặn | Transition chưa đặt `validate="false"` | Bỏ validation cho event phân trang nếu phù hợp |
| Reset vẫn giữ dữ liệu vừa nhập | Binding xảy ra trước action reset | Dùng `bind="false"` cho event reset |
| Mở chi tiết làm mất filter | Criteria nằm trong viewScope | Chuyển criteria sang flowScope |
| Ajax trả về cả trang | Request không được nhận diện là Ajax hoặc fragment chưa cấu hình | Kiểm tra AjaxHandler/view factory và ID fragment |
| Fragment không cập nhật | ID trong `render fragments` không khớp HTML | Kiểm tra ID chính xác |
| Truy vấn chạy quá nhiều lần | `on-render` chạy lại mỗi lần render | Giữ action render chỉ đọc và tối ưu truy vấn |
| Một event ghi dữ liệu hai lần | Side effect không idempotent | Bảo vệ ở service/database |
| Field ngoài ý muốn bị bind | Không giới hạn binder | Khai báo allow-list property |
| Transition action sau không chạy | Action trước trả error result | Kiểm tra thứ tự và gom logic vào facade |
| Nút bị disabled nhưng request vẫn gửi được | Chỉ dựa vào trạng thái UI | Kiểm tra lại điều kiện ở server |

### 13.1. Chẩn đoán theo thứ tự

Khi một nút không tạo hành vi mong đợi:

1. Kiểm tra nút có thật sự gửi request hay không.
2. Xem request parameter có `_eventId` hoặc `_eventId_<name>` hay không.
3. Xác nhận view technology giải mã event theo đúng quy ước.
4. Xác định flow đang ở state nào.
5. Kiểm tra state đó có transition `on` khớp event không.
6. Kiểm tra binding và validation có lỗi không.
7. Kiểm tra transition action có trả kết quả ngăn việc tiếp tục không.
8. Nếu state giữ nguyên, kiểm tra `render` và fragment ID.
9. Nếu state đổi, kiểm tra view của state đích và URL execution.

Không sửa template trước khi xác nhận event đã được Web Flow nhận đúng.

## 14. Kiểm thử nhiều event trên cùng view-state

Spring Web Flow cung cấp `AbstractXmlFlowExecutionTests` để kiểm tra flow XML. Có thể dùng `MockExternalContext#setEventId(...)` để phát event và xác nhận state sau khi flow tiếp tục.

### 14.1. Test event giữ nguyên state

Ví dụ khung test:

~~~java
public void testNextPageKeepsSearchState() {
    setCurrentState("search");

    getFlowScope().put("criteria", new SearchCriteria());

    MockExternalContext context = new MockExternalContext();
    context.setEventId("nextPage");
    resumeFlow(context);

    assertCurrentStateEquals("search");
}
~~~

Test này xác nhận `nextPage` là event handler không target. Có thể bổ sung assertion cho `criteria.page` tăng lên và service search được gọi với page mới.

### 14.2. Test event điều hướng sang state khác

~~~java
public void testOpenItemGoesToDetails() {
    setCurrentState("search");

    MockExternalContext context = new MockExternalContext();
    context.setEventId("openItem");
    context.putRequestParameter("itemId", "42");
    resumeFlow(context);

    assertCurrentStateEquals("details");
}
~~~

Đây là minh họa cho event có target. Trong test thực tế, đăng ký stub `catalogService` trong flow builder context để cung cấp item có ID tương ứng.

### 14.3. Ma trận test

| ID | State | Event | Kết quả cần xác minh |
| --- | --- | --- | --- |
| V01 | Start | Mở flow | Vào `search`, render kết quả ban đầu |
| V02 | search | `filter` | Bind model, validate, render kết quả |
| V03 | search | `nextPage` | Tăng page, vẫn ở search |
| V04 | search | `previousPage` | Giảm page, không nhỏ hơn 0 |
| V05 | search | `reset` | Bỏ binding, reset criteria, render lại |
| V06 | search | `openItem` | Chuyển sang details |
| V07 | details | `back` | Trở lại search, giữ criteria |
| V08 | search | Event không tồn tại | Không chuyển state ngoài ý muốn |
| V09 | search | `filter` với dữ liệu sai | Render lỗi, không dùng kết quả sai |
| V10 | search | `nextPage` với field chưa hoàn chỉnh | Bỏ validation nhưng vẫn bind |
| V11 | search | `reset` khi form chưa hợp lệ | Reset vẫn chạy nếu bind=false |
| V12 | search | `filter` gửi hai lần | Không tạo side effect ghi trùng |
| V13 | search | Ajax `nextPage` | Chỉ cập nhật fragment yêu cầu |
| V14 | search | Fragment ID sai | Test phát hiện vùng không được render |
| V15 | search | Hidden `_eventId` và named button cùng tồn tại | Xác định event decoding thực tế, loại cấu hình xung đột |
| V16 | details | Global event `help` | Global transition hoạt động |
| V17 | search | Field ngoài binder | Không bind property ngoài allow-list |
| V18 | search | `on-render` chạy lại | Dữ liệu view được tải đúng và không phát sinh side effect |

### 14.4. Kiểm thử flow và kiểm thử HTTP khác nhau

Flow test kiểm tra state machine và event handling. Để xác nhận trình duyệt/Thymeleaf gửi đúng tham số, cần thêm MVC/HTTP integration test:

- GET start URL và kiểm tra view được render.
- Kiểm tra HTML có đúng named button và action URL.
- POST từng nút và kiểm tra event được giải mã đúng.
- Nếu bật CSRF, gửi token hợp lệ trong test.
- Kiểm tra fragment response với Ajax handler thực tế.
- Kiểm tra dữ liệu form và message sau validation.

## 15. Bài tập thực hành

### Bài A — thêm nút sắp xếp

Thêm nút “Giá tăng dần” và “Giá giảm dần” trên cùng màn hình. Phát event `sortAscending` và `sortDescending`, khai báo hai transition không có `to`, cập nhật `criteria.sort` rồi render lại `resultsPanel`.

**Đạt khi:** cả hai nút giữ nguyên state search và kết quả có thứ tự đúng.

### Bài B — thêm event xóa từ khóa

Thêm nút “Xóa từ khóa” dùng event `clearKeyword`. Dùng `validate="false"` nếu muốn bind dữ liệu khác nhưng bỏ validation, hoặc `bind="false"` nếu muốn bỏ toàn bộ dữ liệu postback rồi xóa keyword bằng action. Giải thích lựa chọn.

**Đạt khi:** các field còn lại có hành vi đúng với ý định của người dùng.

### Bài C — hai form trên một view

Giữ form lọc riêng và thêm form cho mỗi dòng kết quả để mở chi tiết. Xác minh request của form dòng không vô tình bind lại model tìm kiếm.

**Đạt khi:** event `openItem` nhận đúng ID và criteria vẫn được giữ.

### Bài D — fragment Ajax

Chuyển phân trang sang Ajax. Transition `nextPage` không có target, gọi action tăng trang và render `resultsPanel,pager`. Xác minh phần header/layout bên ngoài không bị thay thế.

**Đạt khi:** flow vẫn ở state search và chỉ các fragment được yêu cầu cập nhật.

### Bài E — kiểm thử event name

Đổi tên button `_eventId_filter` thành `_eventId_applyFilter` nhưng chưa đổi XML. Quan sát request và lỗi. Sau đó đồng bộ `on="applyFilter"` và test lại.

**Đạt khi:** giải thích được vì sao event name phải khớp transition.

### Bài F — validation riêng cho từng event

Thêm validator cho `filter`, nhưng cho phép `nextPage` bỏ validation. Kiểm tra trường hợp người dùng đang nhập từ khóa chưa hoàn chỉnh và vẫn bấm trang kế.

**Đạt khi:** binding/validation đúng theo từng transition, không bỏ qua validation cho event cần kiểm tra dữ liệu.

## 16. Checklist khi thiết kế một view có nhiều event

- [ ] Mỗi nút có event ID rõ nghĩa và ổn định.
- [ ] Named submit button dùng đúng prefix `_eventId_`.
- [ ] Form nhiều nút không có hidden `_eventId` cố định gây ghi đè event.
- [ ] Mỗi form dùng đúng `flowExecutionUrl`.
- [ ] Không lồng các HTML form.
- [ ] Mọi event được khai báo ở state hiện tại hoặc global-transitions.
- [ ] Event giữ nguyên màn hình dùng transition không target.
- [ ] Event điều hướng dùng target state hợp lệ.
- [ ] Binding/validation được chọn riêng theo ý nghĩa từng nút.
- [ ] Binder giới hạn property được phép cập nhật.
- [ ] ViewScope và FlowScope đúng vòng đời dữ liệu.
- [ ] `on-render` chỉ làm công việc an toàn khi render nhiều lần.
- [ ] Fragment ID trong XML khớp ID trong template.
- [ ] Ajax integration được cấu hình và kiểm thử thực tế.
- [ ] Transition action có thứ tự rõ và xử lý error result.
- [ ] Side effect được bảo vệ bằng transaction/idempotency.
- [ ] Server kiểm tra quyền và dữ liệu, không dựa vào việc ẩn nút.
- [ ] Có test cho tất cả event, nhánh lỗi và request HTTP thực tế.

## 17. Câu hỏi tự kiểm tra

**1. Một view-state có thể có bao nhiêu transition?** Có thể có nhiều transition, mỗi transition xử lý một event khác nhau.

**2. Named button gửi event bằng cách nào?** Web Flow tìm request parameter có tên bắt đầu bằng `_eventId_` và dùng phần còn lại làm event ID.

**3. Khi nào dùng hidden `_eventId`?** Khi form chỉ phát một event; tránh kết hợp nó với named buttons trong cùng form.

**4. Transition không có `to` làm gì?** Xử lý event nhưng giữ nguyên state, sau đó render lại view hoặc fragment.

**5. `render fragments` nhận giá trị gì?** ID của phần tử trong view cần cập nhật; có thể có nhiều ID phân tách bằng dấu phẩy.

**6. `bind=false` khác `validate=false` thế nào?** `bind=false` bỏ binding và validation; `validate=false` vẫn bind nhưng bỏ validation.

**7. `on-render` có chạy lại khi render fragment không?** Có; render actions được gọi ở lần render ban đầu và các lần refresh/partial re-render.

**8. Khi nào dùng flowScope thay viewScope?** Khi dữ liệu cần tồn tại qua nhiều view-state; viewScope bị hủy khi rời view-state.

**9. Global transition phù hợp với event nào?** Event có cùng ý nghĩa trên mọi view, như help hoặc logout.

**10. Vì sao không đặt thao tác ghi trong on-render?** Vì render có thể chạy nhiều lần do refresh/Ajax, dễ lặp side effect.

## 18. Tài liệu tham khảo

1. [Spring Web Flow 3.0.2 Reference — Defining View Transitions](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — transition actions, global transitions, event handlers và fragment rendering.
2. [Spring Web Flow 3.0.2 Reference — Signaling an Event from a View](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — named HTML button, hidden event parameter và link event.
3. [Spring Web Flow 3.0.2 Reference — Binding to a Model](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — view-to-model binding và validation lifecycle.
4. [Spring Web Flow 3.0.2 Reference — Suppressing Binding and Validation](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — `bind="false"` và `validate="false"`.
5. [Spring Web Flow 3.0.2 Reference — View Scope](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — vòng đời viewScope và biến trong view-state.
6. [Spring Web Flow 3.0.2 Reference — Testing Flows](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — `AbstractXmlFlowExecutionTests`, `MockExternalContext` và kiểm thử event.

**Điểm cần nhớ:** Một `view-state` có thể nhận nhiều event từ nhiều nút hoặc nhiều form. Transition có `to` điều hướng sang state khác; transition không có `to` xử lý event ngay tại màn hình và có thể render lại một hoặc nhiều fragment. Chọn đúng event ID, binding/validation, scope và render lifecycle sẽ giúp một màn hình xử lý nhiều thao tác mà vẫn giữ flow dễ hiểu và dễ kiểm thử.
