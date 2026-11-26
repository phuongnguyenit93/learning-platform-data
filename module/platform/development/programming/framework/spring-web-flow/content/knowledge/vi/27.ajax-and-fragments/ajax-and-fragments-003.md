# Render toàn view và render một phần trong Spring Web Flow

## Mục tiêu học tập

Spring Web Flow mô hình hóa các hành trình web nhiều bước bằng **state**, **event**, **transition** và **subflow**. Mỗi `view-state` thường chờ người dùng thao tác trước khi flow tiếp tục. Trong chương **Ajax và phân mảnh**, câu hỏi quan trọng là: khi một event được gửi đến server, ứng dụng nên **hiển thị lại cả màn hình** hay chỉ **cập nhật một vùng giao diện**?

Bài này giải thích cơ chế **full view rendering** và **partial rendering (fragment rendering)** trong Spring Web Flow, bao gồm:

- Phân biệt hai cách render theo **phạm vi cập nhật giao diện**, không nhầm với việc chuyển state.
- Dùng `view-state`, transition không có `to`, `<render fragments="..."/>` và `<on-render>` để triển khai lọc/phân trang.
- Hiểu các điều kiện cần có ở tầng template, Spring MVC/JSF và Ajax handler để fragment thực sự xuất hiện trên trang.
- Phân biệt Ajax request ở cùng `view-state` với Ajax request **chuyển sang view-state khác**, cùng ý nghĩa của `mode=embedded`.
- Xử lý form binding, validation, message, session hết hạn, request gửi trùng và các vấn đề bảo mật.
- Xây dựng ma trận kiểm thử cho cả render đầy đủ, render một phần và chuyển bước.

## 1. Hai cách render phục vụ hai nhu cầu khác nhau

Giả sử trang tìm kiếm sản phẩm trong quy trình đặt hàng hiển thị các vùng:

```text
┌──────────────────────────────────────────────┐
│ Thanh điều hướng, trạng thái người dùng       │
├──────────────────────────────────────────────┤
│ Bộ lọc sản phẩm                              │
├──────────────────────────────────────────────┤
│ Danh sách kết quả + phân trang               │
├──────────────────────────────────────────────┤
│ Thông báo và tổng số sản phẩm                │
└──────────────────────────────────────────────┘
```

Người dùng mở màn hình lần đầu: server cần tạo **toàn bộ trang**. Nhưng khi nhấn “Trang tiếp”, phần cần thay đổi thường chỉ là **danh sách kết quả** và có thể cả thông báo tổng số. Việc tải lại thanh điều hướng, layout và những vùng không liên quan làm giao diện nhấp nháy hoặc phải tải nhiều nội dung hơn.

| Tiêu chí | Render toàn view | Render một phần (fragment) |
| --- | --- | --- |
| Phạm vi kết quả | Toàn bộ nội dung view theo cấu hình renderer | Chỉ một hoặc nhiều fragment được chọn |
| Trải nghiệm điển hình | Mở flow, chuyển màn hình, làm mới trang | Phân trang, lọc danh sách, cập nhật thông báo |
| HTTP | Thường là điều hướng trình duyệt hoặc response render đầy đủ | Thường là Ajax request, sau đó client thay vùng DOM |
| Khả năng cần tải layout | Có | Thường không tải lại toàn layout |
| State của flow | Có thể mới vào `view-state` hoặc render lại state cũ | Thường giữ nguyên `view-state` và xử lý event nội bộ |
| Dữ liệu/tác vụ phía server | Render action và truy vấn vẫn có thể chạy | Render action và truy vấn **vẫn có thể chạy**, không tự tiết kiệm công sức phía server |
| Điều kiện tích hợp | Có view resolver/renderer phù hợp | Cần thêm khả năng nhận diện Ajax và **render chính xác fragment** |

**Phân biệt quan trọng:** “render một phần” mô tả **nội dung phản hồi cập nhật giao diện**, còn “giữ nguyên state” mô tả **điều hướng của flow**. Hai chuyện thường đi cùng nhưng không hoàn toàn tương đương.

## 2. Full view rendering: render đầy đủ một màn hình

`view-state` xác định nơi ứng dụng hiển thị giao diện và chờ một event:

```xml
<view-state id="searchProducts" view="catalog/search">
    <transition on="chooseProduct" to="reviewProduct" />
</view-state>
```

Khi flow vào `searchProducts`, Web Flow giải quyết view logic `catalog/search` theo cấu hình, chuẩn bị dữ liệu, rồi trả giao diện cho trình duyệt. Khi event `chooseProduct` được xử lý thành công, flow chuyển đến `reviewProduct`; một view-state khác có thể được render tiếp theo.

Một lần render đầy đủ thường diễn ra như sau:

```mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant F as Spring Web Flow
    participant V as View renderer
    U->>F: Mở flow / điều hướng sang view-state
    F->>F: Chọn state và chạy render actions
    F->>V: Render view
    V-->>F: Nội dung view đầy đủ
    F-->>U: HTTP response / redirect rồi render
    Note over U,F: Người dùng thao tác; request render đã kết thúc
```

Trong chế độ thông thường, Spring Web Flow ưu tiên cơ chế **Post/Redirect/Get (PRG)** khi chuyển tới view-state mới: server có thể trả redirect rồi trình duyệt thực hiện GET để lấy view. Điều này giúp hành vi Refresh/Back rõ ràng hơn khi điều hướng nhiều bước.

Tuy nhiên, **full view** không đồng nghĩa với một state mới. Một `view-state` cũng có thể được render lại đầy đủ nếu:

- Request tới cùng state nhưng không có yêu cầu fragment.
- Một event được xử lý xong mà không chỉ định partial render.
- Binding/validation không thành công và màn hình hiện tại cần hiển thị lại lỗi.
- Client thực hiện một GET/refresh thích hợp để lấy lại cả trang.

Nếu người dùng chỉ chuyển trang kết quả trong cùng màn hình, có thể thiết kế luồng cập nhật một phần thay vì tạo state mới cho từng số trang.

## 3. Partial rendering: chỉ làm mới fragment

Một **fragment** là vùng giao diện mà công nghệ view có khả năng nhận diện và render độc lập. Ví dụ `resultsPanel` chỉ chứa bảng kết quả và nút phân trang. Với Ajax request, server có thể trả HTML của fragment và phía client thay phần tương ứng trên trang đã mở.

```text
Trang hiện tại                              Sau event nextPage
─────────────────────────────              ─────────────────────────────
Header: không đổi                          Header: không đổi
Bộ lọc: không đổi                          Bộ lọc: không đổi
resultsPanel: Trang 1       ──────────>    resultsPanel: Trang 2
Thông báo: không đổi                       Thông báo: không đổi
Footer: không đổi                          Footer: không đổi
```

Trong Spring Web Flow, cách diễn đạt phổ biến là khai báo `<render>` bên trong một transition:

```xml
<view-state id="searchProducts" view="catalog/search">
    <transition on="nextPage">
        <evaluate expression="searchCriteria.nextPage()" />
        <render fragments="resultsPanel" />
    </transition>
</view-state>
```

Ý nghĩa:

1. Flow đang ở state `searchProducts`.
2. Trình duyệt gửi event `nextPage`.
3. Transition **không có thuộc tính `to`**, nên đây là một event handler ở **cùng state**.
4. `<evaluate>` thay đổi số trang của `searchCriteria`.
5. `<render fragments="resultsPanel" />` đề nghị renderer trả lại fragment `resultsPanel` sau khi xử lý event.
6. Với Ajax integration tương thích, phía client nhận fragment và cập nhật vùng tương ứng.

Đây là cú pháp fragment rendering được mô tả trong tài liệu Spring Web Flow. **Chỉ thêm `<render>` vào XML chưa đủ để bất kỳ template engine và bất kỳ đoạn JavaScript nào cũng tự cập nhật DOM.** Tầng view phải biết fragment đó là gì và tầng Ajax phải hiểu phản hồi.

### Render nhiều fragment cùng lúc

Khi thao tác phân trang cũng thay đổi tổng số kết quả hoặc thông báo:

```xml
<transition on="nextPage">
    <evaluate expression="searchCriteria.nextPage()" />
    <render fragments="resultsPanel,messagesPanel" />
</transition>
```

Các ID fragment được phân tách bởi **dấu phẩy**. Hai tên phải khớp với các đơn vị được view technology nhận diện. Với Tiles, fragment có thể tương ứng **attribute của Tiles definition**; với JSF, nó có thể là **component ID/client ID**; với cơ chế template tùy chỉnh, nó phụ thuộc cách server phân giải fragment.

Không nên mặc định rằng cứ có `<div id="resultsPanel">` trong một file HTML thì mọi `ViewResolver` sẽ tự tách và trả đúng fragment đó.

## 4. Ví dụ hoàn chỉnh: lọc và phân trang trong cùng `view-state`

Giả sử bước đầu của flow đặt hàng cho phép người dùng lọc sản phẩm, xem các trang kết quả rồi chọn một sản phẩm để chuyển sang bước xác nhận.

### 4.1. Định nghĩa flow

```xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.springframework.org/schema/webflow
                          https://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <on-start>
        <evaluate expression="catalogFlowService.newCriteria()"
                  result="flowScope.searchCriteria" />
    </on-start>

    <view-state id="searchProducts"
                view="catalog/search"
                model="searchCriteria">

        <binder>
            <binding property="keyword" />
            <binding property="categoryId" />
        </binder>

        <on-render>
            <evaluate expression="catalogFlowService.search(searchCriteria)"
                      result="viewScope.products" />
        </on-render>

        <!-- Áp dụng bộ lọc nhưng vẫn ở màn hình tìm kiếm. -->
        <transition on="applyFilter">
            <evaluate expression="searchCriteria.resetPage()" />
            <render fragments="resultsPanel,messagesPanel" />
        </transition>

        <!-- Hai event phân trang không cần bind lại ô lọc. -->
        <transition on="nextPage" bind="false">
            <evaluate expression="searchCriteria.nextPage()" />
            <render fragments="resultsPanel" />
        </transition>

        <transition on="previousPage" bind="false">
            <evaluate expression="searchCriteria.previousPage()" />
            <render fragments="resultsPanel" />
        </transition>

        <!-- Khi đã chọn sản phẩm, flow chuyển sang màn hình khác. -->
        <transition on="chooseProduct" to="reviewSelection" />

        <transition on="cancel" to="cancelled" bind="false" />
    </view-state>

    <view-state id="reviewSelection" view="catalog/review">
        <transition on="back" to="searchProducts" />
        <transition on="confirm" to="completed" />
    </view-state>

    <end-state id="completed" />
    <end-state id="cancelled" />
</flow>
```

Đây là mẫu XML tập trung vào cơ chế render. Để chạy thật, dự án cần cấu hình flow, bean `catalogFlowService`, lớp `SearchCriteria`, các view, fragment renderer/Ajax integration, validation và cách chọn sản phẩm. `reviewSelection` ở đây chỉ minh họa điều hướng; ứng dụng thực tế phải có logic ghi lựa chọn và kiểm tra nghiệp vụ trước khi xác nhận.

### 4.2. Ý nghĩa của dữ liệu trong ví dụ

`catalogFlowService.newCriteria()` tạo một đối tượng tìm kiếm, được giữ trong `flowScope` vì người dùng có thể đi sang màn hình xem lại rồi quay về. Có thể hình dung model như sau:

```java
import java.io.Serializable;

public class SearchCriteria implements Serializable {
    private static final long serialVersionUID = 1L;

    private String keyword;
    private Long categoryId;
    private int page = 0;

    public void nextPage() {
        page++;
    }

    public void previousPage() {
        page = Math.max(0, page - 1);
    }

    public void resetPage() {
        page = 0;
    }

    // Getter/setter cho các thuộc tính cần bind và đọc từ service.
}
```

Model có thể được mở rộng bằng `pageSize`, `sort`, bộ lọc giá và validation. Trong ứng dụng thật, service cần giới hạn số trang hợp lệ, giới hạn số phần tử mỗi trang và không cho client đặt giá trị truy vấn tùy ý không được kiểm tra.

Kết quả truy vấn được ghi vào `viewScope.products`, vì dữ liệu này chỉ phục vụ màn hình tìm kiếm. Khi rời state để sang `reviewSelection`, view scope của `searchProducts` kết thúc; nếu quay lại, render action có thể truy vấn lại. Nếu danh sách lớn, nên giữ DTO/projection gọn nhẹ thay vì nguyên object graph JPA.

### 4.3. Vì sao sử dụng `<on-render>`?

```xml
<on-render>
    <evaluate expression="catalogFlowService.search(searchCriteria)"
              result="viewScope.products" />
</on-render>
```

`<on-render>` chạy **trước khi render view** trong các tình huống:

- Vừa vào `searchProducts` lần đầu.
- Event handler yêu cầu **render lại toàn view**.
- Event handler yêu cầu **render một hoặc nhiều fragment**.

Vì vậy, khi `nextPage()` tăng số trang, lời gọi `search(...)` lấy dữ liệu trang mới trước khi `resultsPanel` được render lại. Nếu chỉ đặt truy vấn trong `<on-entry>`, nó **không tự chạy lại** sau mỗi event phân trang ở cùng state.

Lựa chọn `<on-render>` cũng có hệ quả: **partial rendering vẫn có thể truy vấn database, chạy service và tốn CPU**. Partial rendering chủ yếu giảm vùng giao diện/response phải cập nhật; nó không tự rút ngắn mọi thao tác ở server. Không nên đặt lệnh tạo đơn hàng, gửi email, trừ tiền hoặc ghi dữ liệu không thể lặp lại trong `<on-render>`, vì nó có thể chạy nhiều lần.

### 4.4. Vì sao một số transition không có `to`?

So sánh:

```xml
<!-- Cùng một view-state, xử lý sự kiện rồi render fragment. -->
<transition on="nextPage" bind="false">
    <evaluate expression="searchCriteria.nextPage()" />
    <render fragments="resultsPanel" />
</transition>

<!-- Rời state hiện tại để tới state khác. -->
<transition on="chooseProduct" to="reviewSelection" />
```

Transition `nextPage` là một **event handler**: logic flow không rời `searchProducts`, nên `viewScope` của state này vẫn tồn tại. Transition `chooseProduct` làm flow sang `reviewSelection`; trạng thái mới được render theo cơ chế điều hướng tương ứng.

**Không nên tạo một state riêng cho “Trang 1”, “Trang 2”, “Trang 3”** nếu chúng đều là cùng một màn hình có dữ liệu khác nhau. Dùng một state với bộ dữ liệu như `SearchCriteria` giúp flow definition dễ đọc hơn.

## 5. Template phải hỗ trợ fragment thực sự

Phần XML:

```xml
<render fragments="resultsPanel" />
```

là **ý định chọn vùng render** của Spring Web Flow. Để server trả đúng nội dung và client áp dụng nó, cần một **contract fragment** thống nhất giữa view technology, server và thư viện Ajax.

### 5.1. Ví dụ ý tưởng giao diện

Một view đầy đủ có thể được tổ chức thành những phần:

```html
<main id="catalogPage">
  <section id="filterPanel">
    <!-- Form nhập keyword và categoryId -->
  </section>

  <section id="messagesPanel" aria-live="polite">
    <!-- Thông báo và lỗi liên quan đến thao tác -->
  </section>

  <section id="resultsPanel" aria-live="polite">
    <!-- Danh sách sản phẩm + nút phân trang -->
  </section>
</main>
```

Đây là **mô hình DOM** để người học dễ hình dung các vùng cập nhật. Nó **không phải** một bộ template tự động thực hiện fragment extraction. `id` trong HTML cần được ánh xạ thành tên fragment theo cách mà resolver hoặc view renderer cụ thể hỗ trợ.

### 5.2. Với Spring MVC và Tiles

Tài liệu chính thức của Spring Web Flow mô tả cách tích hợp fragment với **Tiles** thông qua những view class hỗ trợ Ajax. Trong mô hình Tiles, fragment được xác định từ **thuộc tính trong Tiles definition**.

Ví dụ cấu trúc định nghĩa (minh họa):

```xml
<definition name="catalog/search" template="/WEB-INF/layouts/main.jsp">
    <put-attribute name="body" value="catalog.body" />
</definition>

<definition name="catalog.body" template="/WEB-INF/catalog/index.jsp">
    <put-attribute name="filterPanel" value="/WEB-INF/catalog/filter.jsp" />
    <put-attribute name="resultsPanel" value="/WEB-INF/catalog/results.jsp" />
    <put-attribute name="messagesPanel" value="/WEB-INF/catalog/messages.jsp" />
</definition>
```

Khi view infrastructure được cấu hình đúng cho Ajax/Tiles, `resultsPanel` có thể là tên fragment dùng trong `<render fragments="resultsPanel"/>`. Tài liệu Web Flow 3.x minh họa các lớp như `AjaxUrlBasedViewResolver` và `FlowAjaxTiles3View` cho trường hợp Tiles 3.

**Cảnh báo về phiên bản:** đây là cách tích hợp được mô tả trong tài liệu Web Flow, gắn với hệ sinh thái Tiles/Spring JavaScript trước đây. Không nên hiểu Tiles là lựa chọn mặc định cho mọi dự án Spring MVC mới. Trước khi dùng, phải xác nhận dependency và phiên bản Spring/Servlet tương thích.

### 5.3. Với template engine khác

Một ứng dụng dùng Thymeleaf, JSP composition, template tự xây dựng hoặc thư viện frontend hiện đại có thể hỗ trợ render từng khối, nhưng cần **bộ phân giải view/fragment và định dạng response tương ứng**.

Nếu server chỉ render HTML đầy đủ và trả nguyên trang, một client tự viết `fetch(...)` sẽ **không tự hiểu** `<render fragments="...">`. Bạn cần một trong các hướng tích hợp:

- Dùng adapter/view technology có sẵn khả năng render fragment của Web Flow.
- Viết renderer/adapter tương thích để lấy fragment và trả response theo contract client hiểu được.
- Thiết kế endpoint phần giao diện riêng, đồng thời giữ rõ ranh giới giữa endpoint đó và event/state của Web Flow.

Điều quan trọng là tránh dùng hai cơ chế render không tương thích rồi cho rằng chỉ cần đặt cùng tên `id` là hoạt động.

## 6. Gửi Ajax event mà vẫn tiếp tục đúng flow execution

Mỗi event của Web Flow cần xác định **flow execution hiện tại**. Với Spring MVC view thông thường, framework có thể cung cấp URL tiếp tục flow, thường qua biến `flowExecutionUrl`. Event có thể gửi bằng tham số `_eventId` hoặc tên nút `_eventId_<eventName>`.

Ví dụ form minh họa trong view JSP:

```html
<form id="catalogForm" action="${flowExecutionUrl}" method="post">
    <input name="keyword" type="search" />
    <select name="categoryId">
        <option value="">Tất cả</option>
        <!-- Các lựa chọn category được render phía server -->
    </select>
    <button type="submit" name="_eventId_applyFilter">
        Áp dụng
    </button>
    <button type="submit" name="_eventId_nextPage">
        Trang tiếp
    </button>
</form>
```

Trong request **thông thường**, form có thể làm browser điều hướng và nhận trang đầy đủ. Nếu muốn **Ajax**, client phải gửi event qua cơ chế thư viện Ajax tương thích với Web Flow, kèm URL execution hiện hành, form data thích hợp và CSRF token.

Ví dụ **mã minh họa giao thức Ajax**, chưa phải adapter hoàn chỉnh:

```javascript
async function sendFlowEvent(form, eventName) {
  const data = new FormData(form);
  data.set("_eventId", eventName);

  const response = await fetch(form.action, {
    method: "POST",
    body: data,
    credentials: "same-origin",
    headers: {
      "X-Requested-With": "XMLHttpRequest"
    }
  });

  if (!response.ok) {
    throw new Error("Request cập nhật flow thất bại");
  }

  // Từ đây cần adapter phù hợp với contract trả về của server:
  // - parse response fragment hoặc thông tin redirect,
  // - xác định element đích,
  // - thay nội dung an toàn,
  // - cập nhật flow execution URL/key nếu response yêu cầu.
  // Không mặc định response.text() là HTML duy nhất của resultsPanel.
  return response;
}
```

Đoạn `fetch` trên **không thể tự vận hành end-to-end chỉ bằng việc thêm `X-Requested-With`**. Việc nhận diện Ajax phụ thuộc `AjaxHandler` được cấu hình; nội dung response cũng phụ thuộc view technology. Nếu dự án dùng thư viện Ajax khác Spring JavaScript, thường cần kết nối thư viện đó qua `AjaxHandler` hoặc adapter tương đương.

Với ứng dụng có giao diện cần hoạt động khi JavaScript bị tắt, nên cho phép form gửi request thường và nhận full view như **phương án dự phòng**, sau đó bổ sung Ajax như một cải tiến trải nghiệm.

### Lưu ý về Spring JavaScript cũ

Tài liệu Web Flow đưa ra ví dụ `Spring.AjaxEventDecoration` và `SpringJavascriptAjaxHandler`. Tuy nhiên, bản 3.x ghi rõ module **`spring-js-resources` là module legacy, chỉ giữ để tương thích ngược và không còn được khuyến nghị cho dự án mới**. Khi học các ví dụ cũ, hãy hiểu nguyên lý event/fragment; khi triển khai mới, xác minh giải pháp Ajax/renderer được hỗ trợ ở phiên bản đang dùng.

## 7. `AjaxHandler`, redirect và chế độ embedded

### 7.1. Server nhận ra Ajax request bằng cách nào?

Spring Web Flow có API `org.springframework.js.AjaxHandler` để tích hợp hành vi Ajax, đặc biệt khi cần quyết định **có redirect hay không** sau request. Tài liệu nêu `SpringJavascriptAjaxHandler` làm cấu hình mặc định trong hệ sinh thái Spring JavaScript; có thể dùng implementation khác khi tích hợp thư viện frontend khác.

Điều đó giải thích vì sao hai request cùng event có thể tạo kết quả khác nhau ở tầng response:

| Request | Flow xử lý | Phản hồi giao diện |
| --- | --- | --- |
| POST thường `nextPage` | Event handler, vẫn trong `searchProducts` | Có thể render toàn view để trình duyệt hiển thị |
| Ajax `nextPage` có fragment renderer phù hợp | Event handler, vẫn trong `searchProducts` | Có thể render và trả `resultsPanel` |
| POST thường `chooseProduct` | Chuyển sang `reviewSelection` | Thường redirect rồi render view kế tiếp |
| Ajax `chooseProduct` khi không chạy embedded | Chuyển state | Có thể cần xử lý redirect/toàn trang |
| Ajax trong flow `mode=embedded` | Có thể chuyển state | Có thể tránh flow execution redirect để cập nhật vùng flow nhúng |

**Điểm cần nhớ:** `AjaxHandler` giúp Web Flow nhận diện request và xử lý redirect phù hợp; view renderer quyết định **fragment nào được trả** và client cần hiểu **cách cập nhật giao diện**. Hai trách nhiệm này cần kết nối với nhau.

### 7.2. Chuyển state thường có redirect

Trong chế độ mặc định:

```xml
<transition on="nextPage">
    <render fragments="resultsPanel" />
</transition>
```

không rời `view-state`; Ajax partial rendering rất phù hợp. Ngược lại:

```xml
<transition on="chooseProduct" to="reviewSelection" />
```

chuyển sang state mới. Tài liệu Spring Web Flow 3.x cho biết **việc vào view-state mới thường được theo sau bởi client-side redirect** trong chế độ bình thường. Do đó, không nên giả định client có thể thay một fragment nhỏ ngay khi có chuyển màn hình mới.

### 7.3. `mode=embedded` dành cho flow nhúng

Nếu flow được hiển thị bên trong một vùng của trang lớn hoặc trong hộp thoại, chuyển state mà reload cả trang có thể làm mất nội dung ngoài vùng flow. Spring Web Flow hỗ trợ **embedded mode** để tránh flow execution redirect khi xử lý **Ajax request**.

Ví dụ khởi chạy flow từ URL:

```text
/checkout?mode=embedded
```

Tham số `mode=embedded` được truyền khi **khởi chạy flow**; không cần lặp lại thủ công ở mọi request nếu đã vào embedded mode đúng cách.

Với một flow con, tài liệu còn minh họa truyền input:

```xml
<subflow-state id="editDelivery" subflow="deliveryFlow">
    <input name="mode" value="'embedded'" />
</subflow-state>
```

Embedded mode **không tự xây dựng component frontend**, không tự chọn HTML fragment và không bỏ qua quản lý flow execution. Nó giải quyết phần **redirect** khi flow vận hành bằng Ajax trong một vùng nhúng. Client/rendering vẫn cần tích hợp tương thích.

## 8. Validation: lỗi có thể cần render nhiều vùng

Giả sử người dùng áp dụng bộ lọc nhưng nhập dữ liệu không hợp lệ, ví dụ `minPrice` lớn hơn `maxPrice`. Form binding/validation có thể ngăn transition hoặc làm view render lại với message.

```xml
<view-state id="searchProducts" model="searchCriteria">
    <transition on="applyFilter">
        <evaluate expression="searchCriteria.resetPage()" />
        <render fragments="resultsPanel,messagesPanel" />
    </transition>
</view-state>
```

Nếu validation thành công, transition có thể chạy và yêu cầu cập nhật cả hai fragment. Nếu validation thất bại **trước khi transition chạy**, đừng mặc định `<render>` trong transition vẫn được thực hiện: tùy flow/view integration, framework có thể render lại view hiện tại để hiển thị lỗi.

Vì vậy, thiết kế cần trả lời:

1. Lỗi field nằm trong `filterPanel`, nhưng response chỉ cập nhật `resultsPanel` thì người dùng nhìn thấy lỗi ở đâu?
2. Khi transition bị chặn bởi validation, đường render lỗi có gửi đủ `messagesPanel` và form controls hay không?
3. Nếu lỗi xảy ra ngay lúc service truy vấn, có hiển thị nội dung cũ hay thông báo tải lại?
4. Khi Ajax lỗi, có phương án gửi request thường để nhận toàn bộ màn hình không?

Một quyết định thiết kế hữu ích là cập nhật cùng lúc **vùng form có lỗi** và **vùng message** khi áp dụng bộ lọc, thay vì chỉ render bảng kết quả.

Ví dụ ở template:

```html
<section id="filterPanel">
  <!-- Các field, nhãn và lỗi field -->
</section>

<section id="messagesPanel" role="status" aria-live="polite">
  <!-- Thông báo thành công hoặc lỗi -->
</section>

<section id="resultsPanel">
  <!-- Kết quả -->
</section>
```

Như ở mục 5, `id` này chỉ minh họa **vùng DOM cần cập nhật**, còn tên fragment phía server phải được view technology map đúng. Phần `aria-live` hỗ trợ thông báo động; với lỗi quan trọng, cân nhắc di chuyển focus tới vùng lỗi hoặc cung cấp hướng dẫn có thể đọc bằng bàn phím và screen reader.

## 9. Tính nhất quán dữ liệu khi có nhiều Ajax request

Ajax khiến người dùng dễ gửi nhiều event liên tiếp. Ví dụ:

```text
T0: Người dùng nhấn nextPage (yêu cầu A: từ trang 1 → 2)
T1: Nhấn tiếp nextPage (yêu cầu B: từ trang 2 → 3)
T2: Response B về trước response A
```

Nếu client đơn giản thay DOM khi mỗi response về, kết quả **trang cũ có thể xuất hiện đè lên trang mới**. Repository của Web Flow có cơ chế quản lý execution và locking, nhưng không thể thay thế toàn bộ logic phối hợp response ở client.

Một số hướng xử lý:

- Vô hiệu hóa tạm nút chuyển trang khi đang tải, hoặc giới hạn số request cùng lúc.
- Gắn mã yêu cầu/phiên bản dữ liệu với tương tác để chỉ áp dụng response mới nhất.
- Hủy request cũ ở client nếu thư viện hỗ trợ, nhưng vẫn phải biết request đã tới server hay chưa.
- Giữ `flowExecutionUrl` và execution key đồng bộ với response/redirect hợp lệ; không gửi lại key cũ một cách tùy tiện.
- Nếu event có side effect nghiệp vụ, dùng idempotency và transaction ở service; **không đặt tác vụ ghi trong render action**.

Đặc biệt, nếu người dùng mở nhiều tab của cùng một flow execution, việc cập nhật đồng thời có thể gây conflict hoặc snapshot cũ. Hãy quyết định rõ chính sách trải nghiệm cho tab cũ: yêu cầu refresh, giải thích phiên hết hạn hoặc khởi chạy flow mới.

## 10. Bảo mật và dữ liệu nhạy cảm

Render một phần **không làm giảm yêu cầu bảo mật** so với render cả trang. Một request cập nhật fragment vẫn là HTTP request có thể bị gửi thủ công.

| Rủi ro | Biện pháp nên áp dụng |
| --- | --- |
| Gửi event trái phép | Kiểm tra quyền trên state/transition và tại service |
| Sửa tham số form ngoài phạm vi | Binder whitelist + validation phía server |
| CSRF trên POST Ajax | Gửi token theo cơ chế Spring Security đã cấu hình |
| XSS trong fragment HTML | Escape dữ liệu theo ngữ cảnh template; không chèn HTML tùy ý từ input |
| Lộ dữ liệu khi trả fragment | Kiểm tra quyền truy cập dữ liệu trước khi render, không dựa vào việc “nút bị ẩn” |
| Flow execution key cũ hoặc bị đánh cắp | Chính sách session, xử lý expiration, không ghi log key nhạy cảm đầy đủ |
| Render fragment riêng có dữ liệu bí mật | Thiết lập cache và chính sách HTTP phù hợp, không mặc định cache chung |

Không dùng `innerHTML` để đổ trực tiếp nội dung không đáng tin nếu không có cơ chế đảm bảo nội dung HTML an toàn và response đến từ nguồn đã xác thực. Với fragment do server render, server vẫn cần escaping và template controls đúng ngữ cảnh.

## 11. Đánh đổi hiệu năng: giảm HTML tải về chưa chắc giảm truy vấn

Partial rendering có thể cải thiện trải nghiệm vì chỉ cập nhật một vùng DOM và thường giảm số byte truyền qua mạng. Tuy nhiên, nó không tự động giảm mọi chi phí xử lý:

| Chi phí | Render toàn view | Render một phần |
| --- | --- | --- |
| HTML gửi về | Toàn trang | Thường nhỏ hơn |
| Số vùng DOM bị thay thế | Nhiều, có thể cả trang | Vùng được chọn |
| `<on-render>` | Chạy | **Vẫn chạy** |
| Truy vấn trong `catalogFlowService.search(...)` | Có thể chạy | **Vẫn có thể chạy** |
| Vòng đời transaction service | Theo lời gọi service | Theo lời gọi service, không tự khác |
| Độ phức tạp client/server | Thường đơn giản hơn | Cần thêm fragment contract, Ajax/redirect và xử lý lỗi |

Ví dụ với catalog có 100.000 sản phẩm, chỉ thay `resultsPanel` không có nghĩa `search(...)` tự dùng pagination trong SQL. Service cần dùng truy vấn phân trang, lấy đúng trường cần hiển thị, đặt kích thước trang hợp lý và tránh tải toàn bộ collection vào session.

Nên dùng `<on-render>` cho hành động **đọc dữ liệu và chuẩn bị giao diện**, có thể lặp lại. Nếu có công việc tốn kém, có thể tối ưu/caching có kiểm soát; cần bảo đảm cache không làm lộ kết quả giữa người dùng hoặc che mất thay đổi quan trọng về quyền truy cập.

## 12. Các lỗi thường gặp và cách chẩn đoán

### 12.1. Bấm Trang tiếp nhưng trang bị reload toàn bộ

Hãy kiểm tra request có thật sự là Ajax được `AjaxHandler` nhận diện không, event có khớp `nextPage` không và view technology có hỗ trợ fragment không. Chỉ dùng `<render fragments="resultsPanel"/>` khi HTML form vẫn submit bình thường **không bảo đảm** trình duyệt tự thay một vùng DOM.

### 12.2. Server trả full HTML nhưng client cố nhét vào `resultsPanel`

Kiểm tra resolver và response contract. Nếu fragment không được trích xuất, toàn bộ layout HTML có thể bị nhúng vào vùng bảng kết quả. Không xử lý bằng cách cắt chuỗi HTML tùy tiện; cần view renderer hoặc protocol fragment phù hợp.

### 12.3. Fragment ID không tìm thấy

`resultsPanel` trong XML có thể không tương ứng với ID được renderer hỗ trợ. Với Tiles, kiểm tra tên attribute; với JSF, kiểm tra client ID và naming container; với template engine khác, kiểm tra fragment mapping. Phân biệt **ID HTML trên client** với **định danh fragment phía server**.

### 12.4. Kết quả không thay đổi dù `nextPage()` đã chạy

Kiểm tra `<on-render>` có chạy sau event không, service có dùng `searchCriteria.page` không và liệu dữ liệu trong `viewScope.products` đã được cập nhật chưa. Nếu chỉ truy vấn trong `<on-entry>`, có thể kết quả không đổi khi chỉ render lại cùng state.

### 12.5. Message validation biến mất

Kiểm tra vùng chứa message có nằm trong danh sách fragment không. Nếu validation ngăn transition, xác nhận cơ chế xử lý lỗi có render form/messages phù hợp. Không chỉ kiểm tra response HTTP 200; phải kiểm tra người dùng nhìn thấy lỗi hay không.

### 12.6. Ajax chuyển màn hình nhưng mất nội dung trang cha

Nếu flow được nhúng trong modal hoặc một vùng trang, hãy xem xét `mode=embedded` và cách client xử lý response khi chuyển `view-state`. Ở chế độ mặc định, việc vào state mới thường redirect, có thể gây reload trang ngoài vùng flow.

### 12.7. Request Ajax báo execution không tồn tại

Nguyên nhân có thể là session timeout, execution key lỗi/cũ, flow đã hoàn thành hoặc snapshot bị loại. Client cần xử lý luồng hết hạn và cho bắt đầu lại hoặc khôi phục bản nháp nghiệp vụ; không tự giả lập key.

### 12.8. Hai thao tác liên tiếp làm giao diện nhảy lùi

Kiểm tra thứ tự request/response và cách client áp dụng kết quả. Cân nhắc disable nút, hủy request cũ hoặc chỉ áp dụng response mới nhất; với thao tác ghi phải kết hợp kiểm tra concurrency/idempotency ở service.

### 12.9. Cập nhật fragment mà mất event binding

Khi thay một phần DOM, listener JavaScript đã gắn trực tiếp vào node cũ có thể mất theo. Dùng event delegation hoặc khởi tạo lại widget/listener có kiểm soát sau khi cập nhật. Đây là vấn đề vòng đời DOM ở client, không phải lỗi của `view-state`.

## 13. Kiểm thử full view và partial rendering

Nên kiểm thử hai lớp riêng biệt:

1. **Logic flow:** event nào ở cùng state, event nào chuyển state, action nào chạy, `viewScope`/`flowScope` thay đổi thế nào.
2. **Tích hợp HTTP/view/client:** Ajax request có được nhận diện không, fragment có đúng định dạng không, DOM có được thay đúng vùng không, redirect/validation/session lỗi được xử lý ra sao.

| Kịch bản | Kỳ vọng ở flow | Kỳ vọng ở giao diện |
| --- | --- | --- |
| Mở trang tìm kiếm lần đầu | Vào `searchProducts` | Render full view với bộ lọc và kết quả |
| Ajax `nextPage` | Vẫn ở `searchProducts`; page tăng | Chỉ vùng `resultsPanel` được cập nhật |
| Ajax `previousPage` | Vẫn ở state; page giảm có kiểm soát | Kết quả đúng trang; không thay layout ngoài vùng |
| Ajax `applyFilter` hợp lệ | Bộ lọc được bind, page reset | Fragment kết quả và message cập nhật |
| Form `applyFilter` không có JavaScript | Vẫn xử lý event phù hợp | Có thể sử dụng phương án render đầy đủ |
| `applyFilter` dữ liệu sai | Validation ngăn xử lý không hợp lệ | Lỗi field/message nhìn thấy rõ |
| Event `chooseProduct` | Chuyển `reviewSelection` | Điều hướng sang view mới, xử lý redirect đúng |
| Flow embedded chuyển state bằng Ajax | Chuyển state theo quy tắc | Vùng flow nhúng cập nhật mà không reload toàn trang cha |
| Fragment ID sai | Logic có thể chạy | Báo lỗi rendering có thể chẩn đoán |
| `on-render` có truy vấn | Chạy ở full và partial | Kết quả phù hợp tiêu chí/trang |
| Session/flow hết hạn | Không resume execution cũ | Thông báo hết hạn và hướng phục hồi |
| Hai request Ajax liên tiếp | Không làm hỏng flow state | Không áp dụng response cũ đè response mới |
| Event trái phép hoặc CSRF thiếu | Server từ chối | Không để lộ fragment hoặc dữ liệu nhạy cảm |

**Lưu ý:** `AbstractXmlFlowExecutionTests` hoặc test flow tương tự có thể giúp khẳng định state/event, nhưng **không đủ** để khẳng định fragment HTML đã được `ViewResolver` và browser cập nhật đúng. Phần đó cần kiểm thử tích hợp MVC/view và, nếu có, kiểm thử trình duyệt.

### Gợi ý kiểm thử bằng HTTP

Trong môi trường chạy thử:

1. Gửi request mở flow, xác định view được render và execution URL hợp lệ.
2. Gửi request tiếp tục flow với event `nextPage`, Ajax indicator đúng loại mà ứng dụng hỗ trợ và CSRF token hợp lệ.
3. Kiểm tra response không chứa toàn bộ layout ngoài fragment khi ứng dụng đã cấu hình partial rendering.
4. Kiểm tra dữ liệu trang 2 thực sự xuất hiện và `searchProducts` vẫn là state hiện tại.
5. Gửi request không dùng Ajax cho cùng event để xác nhận phương án full render (nếu dự án hỗ trợ progressive enhancement).
6. Gửi event chuyển state để kiểm tra redirect hoặc embedded behavior theo cấu hình.

Các header/parameter cụ thể phụ thuộc `AjaxHandler` và công nghệ view của dự án; không nên viết test dựa trên giả định mọi frontend đều dùng cùng một header Ajax.

## 14. Bài tập thực hành

Bạn xây dựng flow đăng ký khóa học có một màn hình `selectCourse`. Trên màn hình:

- `filterPanel` chứa bộ lọc danh mục và từ khóa.
- `courseList` chứa danh sách khóa học và phân trang.
- `messagePanel` hiển thị lỗi nếu không có khóa học phù hợp.
- Event `nextPage` và `previousPage` chỉ thay kết quả và không rời state.
- Event `applyFilter` đặt lại trang đầu và cần cập nhật cả danh sách lẫn thông báo.
- Event `chooseCourse` chuyển sang `reviewEnrollment`.

**Yêu cầu:**

1. Viết `view-state` với `<on-render>` truy vấn danh sách dựa trên model.
2. Viết transition không có `to` cho hai event phân trang và đặt `<render fragments="courseList"/>`.
3. Viết transition `applyFilter` với `<render fragments="courseList,messagePanel"/>`.
4. Viết transition có `to="reviewEnrollment"` khi người dùng chọn khóa học.
5. Giải thích phải cấu hình gì để request Ajax thực sự chỉ trả fragment, và phải làm gì khi form validation lỗi.
6. Bổ sung kiểm thử xác nhận browser vẫn hoạt động khi JavaScript không chạy hoặc execution đã hết hạn.

Gợi ý cấu trúc:

```xml
<view-state id="selectCourse" view="enrollment/select"
            model="courseCriteria">
    <on-render>
        <evaluate expression="courseCatalog.search(courseCriteria)"
                  result="viewScope.courses" />
    </on-render>

    <transition on="nextPage" bind="false">
        <evaluate expression="courseCriteria.nextPage()" />
        <render fragments="courseList" />
    </transition>

    <transition on="previousPage" bind="false">
        <evaluate expression="courseCriteria.previousPage()" />
        <render fragments="courseList" />
    </transition>

    <transition on="applyFilter">
        <evaluate expression="courseCriteria.resetPage()" />
        <render fragments="courseList,messagePanel" />
    </transition>

    <transition on="chooseCourse" to="reviewEnrollment" />
</view-state>
```

Đây là khung phần flow; người học cần bổ sung model, service, valid template/fragment và Ajax integration tương ứng với ứng dụng thực tế.

## 15. Ghi nhớ

- **Full view rendering** trả toàn bộ view, phù hợp khi mở flow hoặc chuyển sang một màn hình khác; chế độ thường có thể dùng redirect theo Post/Redirect/Get.
- **Partial rendering** chỉ yêu cầu cập nhật một số fragment, thường dùng khi Ajax event vẫn ở cùng `view-state`.
- Transition không có `to` là **event handler**; `<render fragments="fragmentA,fragmentB" />` chọn những fragment cần render lại.
- `<on-render>` chạy **cả khi render đầy đủ lẫn khi render fragment**; không đặt lệnh ghi có tác dụng phụ không thể lặp trong đó.
- `AjaxHandler`, view resolver/renderer và frontend phải dùng **một contract phản hồi tương thích**. Một HTML `id` hoặc header `X-Requested-With` đơn lẻ không bảo đảm partial rendering.
- `mode=embedded` hỗ trợ flow nhúng tránh redirect khi chuyển state bằng Ajax; nó không thay thế renderer hay client update logic.
- Binding, validation, bảo mật, quản lý execution key và xử lý session vẫn phải đúng ngay cả khi chỉ làm mới một góc màn hình.

### Tài liệu tham khảo

- [Spring Web Flow 3.0.2 Reference Guide — Rendering Views](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#rendering-views): `view-state`, `on-render`, event handler và `<render fragments>`.
- [Spring Web Flow 3.0.2 Reference Guide — Spring MVC Integration](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#spring-mvc-integration): form event và embedded flow.
- [Spring Web Flow 3.0.2 Reference Guide — Spring JavaScript Quick Reference](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#spring-javascript-quick-reference): Ajax handler, fragment rendering với Tiles và ghi chú `spring-js-resources` legacy.
- [Spring Web Flow 3.0.2 Reference Guide — JSF Integration](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/#jsf-integration): partial rendering qua JSF Ajax và danh sách component ID.
