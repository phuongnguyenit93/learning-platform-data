# Đăng ký flow theo tài nguyên, mẫu đường dẫn và định danh trong Spring Web Flow

Ứng dụng dùng **Spring Web Flow (SWF)** có thể chứa nhiều hành trình: đăng ký tài khoản, đặt lịch, thanh toán và đổi thông tin hồ sơ. Mỗi hành trình được mô tả bằng một flow definition, thường viết trong tệp XML. Nhưng **đặt file XML vào dự án chưa đủ** để Spring MVC có thể chạy flow. Ứng dụng phải **đăng ký** các định nghĩa đó, gắn chúng với **flow ID**, rồi kết nối registry với `FlowExecutor` và tầng HTTP.

Trong chương **Cấu hình hệ thống** của module **SPRING_WEB_FLOW**, bài này tập trung vào ba cách quản lý flow definition: **đăng ký từng tài nguyên XML**, **đăng ký bằng mẫu đường dẫn** và **quy định định danh flow tường minh**. Các quyết định này ảnh hưởng trực tiếp tới cách browser truy cập hành trình, cách flow cha gọi subflow, cách phát hiện file cấu hình sai và cách viết kiểm thử. Khi registry được thiết lập đúng, ta mới có nền tảng ổn định để phát triển state, event, transition, form binding, validation, scope, phiên và phục hồi luồng.

> Các ví dụ XML dưới đây minh họa cấu hình theo namespace `spring-webflow-config` của **Spring Web Flow 2.x**. Tính tương thích của phiên bản Spring Framework, Servlet API (`javax`/`jakarta`) và Web Flow cần được kiểm tra trong chính dự án. Không nên coi một đoạn cấu hình dành cho Web Flow 2.x là bằng chứng nó chạy nguyên trạng trên mọi bản Spring Boot.

## 1. Đăng ký flow nghĩa là gì?

Giả sử dự án có các file sau:

~~~text
src/main/webapp/
└── WEB-INF/
    └── flows/
        ├── registration/
        │   └── registration.xml
        ├── booking/
        │   └── booking.xml
        ├── checkout/
        │   └── checkout.xml
        └── shared/
            └── address-check.xml
~~~

Các file này chỉ là **tài nguyên chứa định nghĩa**. Ứng dụng cần cho Spring Web Flow biết file nào có thể được dựng thành flow và **ID nào dùng để gọi flow đó**.

Phân biệt những khái niệm sau:

| Khái niệm | Ví dụ | Trách nhiệm |
|---|---|---|
| Tài nguyên XML | `/WEB-INF/flows/booking/booking.xml` | Chứa các state, event, transition và cấu hình bên trong flow |
| Flow ID | `booking` | Tên logic dùng tra cứu định nghĩa flow |
| `FlowDefinitionRegistry` | Bean `flowRegistry` | Lưu và tìm các flow definition theo ID |
| `FlowExecutor` | Bean `flowExecutor` | Bắt đầu, tiếp tục và kết thúc các lần thực thi flow |
| URL điểm vào | `/booking` | HTTP path được cấu hình để nhận diện flow |
| Execution key | `execution=<opaque-key>` | Tham chiếu một lần thực thi/snapshot cụ thể |

Ví dụ: file `booking.xml` có thể được đăng ký dưới flow ID `booking`, rồi trình duyệt GET `/booking` để bắt đầu. Nhưng tên file, ID và URL **không phải ba tên tự động đồng nhất trong mọi cấu hình**. Registry quyết định ID, còn `FlowHandlerMapping` và `FlowUrlHandler` quyết định cách URL được diễn giải.

~~~mermaid
flowchart TD
    R1["registration.xml"] --> REG["FlowDefinitionRegistry"]
    R2["booking.xml"] --> REG
    R3["checkout.xml"] --> REG
    REG --> EX["FlowExecutor"]
    H["GET /booking"] --> MAP["Spring MVC FlowHandlerMapping"]
    MAP --> ADAPTER["FlowHandlerAdapter"]
    ADAPTER --> EX
    EX --> FLOW["Flow definition booking"]
    FLOW --> STATE["State hiện tại và transition"]
    STATE --> VIEW["Render view / redirect"]
~~~

**Registry lưu các định nghĩa flow; nó không phải nơi lưu một bản nháp của từng người dùng.** Khi một người dùng mở hai tab và bắt đầu hai hành trình `booking` độc lập, cả hai dùng chung flow definition nhưng có thể có **hai flow execution và hai `flowScope` riêng**.

## 2. Ba chiến lược đăng ký và khi nào chọn

| Chiến lược | Cấu hình chính | Khi nào phù hợp? | Cần kiểm tra |
|---|---|---|---|
| Tài nguyên tường minh | `<webflow:flow-location .../>` | Số flow ít, API đường dẫn ổn định, cần kiểm soát chính xác | File có được nạp và ID đúng không? |
| Mẫu đường dẫn | `<webflow:flow-location-pattern .../>` | Nhiều flow theo cùng một quy ước file/thư mục | Pattern khớp những file nào, ID được tạo ra là gì? |
| Định danh tường minh | Thuộc tính `id` của `flow-location` | Muốn tên logic không bị ràng buộc vào tên file | Các URL/subflow references có dùng đúng ID không? |

**Đăng ký bằng tài nguyên** và **định danh tường minh** không loại trừ nhau: ta thường dùng `flow-location` với cả `id` lẫn `path`. Ngược lại, quét bằng pattern giúp giảm số dòng cấu hình nhưng yêu cầu kỷ luật tổ chức file và kiểm thử registry.

Quy tắc chọn thực tế:

1. Bắt đầu với đăng ký **tường minh** nếu chỉ có vài flow quan trọng và yêu cầu kiểm soát URL rõ ràng.
2. Dùng **pattern** khi dự án đã có quy ước đặt tên, cấu trúc thư mục thống nhất và test xác nhận tập flow được tìm thấy.
3. Gán **ID tường minh** cho những flow có hợp đồng URL hoặc được flow khác tham chiếu lâu dài, tránh đổi định danh ngoài ý muốn khi tổ chức lại file.

## 3. Cấu hình XML tối thiểu: flow-registry và flow-executor

Ví dụ dưới đây dùng Spring Beans và namespace của Spring Web Flow:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:webflow="http://www.springframework.org/schema/webflow-config"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/webflow-config
           http://www.springframework.org/schema/webflow-config/spring-webflow-config.xsd">

    <!-- 1. Đăng ký định nghĩa của từng flow. -->
    <webflow:flow-registry id="flowRegistry">
        <webflow:flow-location
            id="registration"
            path="/WEB-INF/flows/registration/registration.xml"/>
        <webflow:flow-location
            id="booking"
            path="/WEB-INF/flows/booking/booking.xml"/>
        <webflow:flow-location
            id="checkout"
            path="/WEB-INF/flows/checkout/checkout.xml"/>
    </webflow:flow-registry>

    <!-- 2. Executor cần registry để tìm định nghĩa. -->
    <webflow:flow-executor
        id="flowExecutor"
        flow-registry="flowRegistry"/>

</beans>
~~~

Trong cấu hình này:

- `id="flowRegistry"` của thẻ `flow-registry` là **tên Spring bean** của registry.
- `id="booking"` trên `flow-location` là **định danh một flow** trong registry; nó không phải tên bean Spring.
- `path="/WEB-INF/flows/booking/booking.xml"` là **đường dẫn tài nguyên XML** trong bối cảnh web application được cấu hình.
- `flow-registry="flowRegistry"` trên executor là **tham chiếu đến bean registry**, không phải tham chiếu đến flow có ID `flowRegistry`.

Hai chữ `id` có phạm vi khác nhau nên rất dễ gây nhầm. Một registry có thể chứa nhiều flow ID, và một executor có thể quản lý nhiều execution của các flow đó.

### 3.1. Kiểm tra vị trí thực tế của tài nguyên

Đường dẫn `/WEB-INF/flows/...xml` có ý nghĩa khi ứng dụng đóng gói các file dưới **web application resources** và resource loader của context truy cập được chúng. Với cấu trúc và đóng gói khác (ví dụ classpath resources trong JAR), cần dùng resource location phù hợp và kiểm tra lại khả năng nạp ở runtime.

Ví dụ nếu dự án đặt XML dưới `src/main/resources/flows`, không nên tiếp tục dùng đường dẫn `/WEB-INF/flows` chỉ vì ví dụ trên dùng nó. Tùy cơ chế resource loader/version, bạn có thể dùng đường dẫn theo classpath, nhưng phải xác nhận cách `flow-location` của phiên bản đang chạy giải quyết resource đó.

**Không lấy một đường dẫn filesystem trên máy phát triển làm đường dẫn production** mà chưa kiểm tra artifact đã đóng gói. File tồn tại trong source tree không chứng minh servlet container hoặc classpath tại runtime nhìn thấy nó.

### 3.2. Vì sao nên có registry ngay cả khi chỉ một flow?

Registry tách rõ khái niệm **tìm định nghĩa** khỏi **thực thi định nghĩa**. Khi thêm `address-check` làm subflow hoặc thêm `checkout`, ta có thể mở rộng tập flow được đăng ký mà không biến controller thành một bảng `if/else` để tìm từng XML.

Ngoài ra, registry là một điểm có thể kiểm tra bằng tự động hóa: đúng bao nhiêu ID, tệp nào được tham chiếu, có định nghĩa nào thiếu không.

## 4. Đăng ký flow theo tài nguyên cụ thể

Giả sử có một flow thanh toán đặc biệt đặt dưới tên file khó đoán:

~~~text
/WEB-INF/flows/checkout/secure-checkout-v2.xml
~~~

Ta có thể chọn một flow ID ổn định:

~~~xml
<webflow:flow-registry id="flowRegistry">
    <webflow:flow-location
        id="checkout"
        path="/WEB-INF/flows/checkout/secure-checkout-v2.xml"/>
</webflow:flow-registry>
~~~

Người dùng và các flow khác có thể tiếp tục gọi flow ID `checkout` theo hợp đồng ứng dụng. Nếu nội bộ đổi tên file thành `checkout-main.xml`, chỉ cần cập nhật `path` (miễn là nội dung và các phụ thuộc vẫn hợp lệ); tên logic `checkout` không nhất thiết thay đổi.

**Ưu điểm của cách khai báo tường minh:**

- Dễ nhìn ra từng flow ID và tài nguyên tương ứng khi review cấu hình.
- Có quyền kiểm soát ID độc lập với vị trí file.
- Không vô tình đăng ký tất cả XML thử nghiệm nằm trong một cây thư mục.
- Dễ viết test registry và kiểm soát tương thích URL khi refactor.
- Phù hợp với flow có ý nghĩa nghiệp vụ quan trọng hoặc được sử dụng từ các flow khác.

**Nhược điểm:** thêm một flow mới đòi hỏi sửa cấu hình đăng ký. Nếu dự án có hàng trăm flow và mọi flow tuân theo một convention rõ ràng, cấu hình tường minh có thể trở nên dài và khó bảo trì.

### 4.1. Không nhầm path tài nguyên với URL công khai

Đường dẫn:

~~~text
/WEB-INF/flows/checkout/secure-checkout-v2.xml
~~~

không phải URL form nên POST tới. Thông thường `WEB-INF` không được phục vụ như tài nguyên công khai cho trình duyệt. Khi registry có ID `checkout` và MVC mapping được cấu hình đúng, điểm vào có thể là:

~~~text
GET /checkout
~~~

Còn các yêu cầu tiếp theo sẽ sử dụng **flow execution URL** do SWF tạo. Đừng đưa đường dẫn XML trực tiếp vào HTML `<form action>`.

## 5. Đăng ký bằng mẫu đường dẫn

Khi nhiều flow có quy ước đặt tên, namespace Web Flow hỗ trợ `flow-location-pattern` để tìm các tệp phù hợp với một mẫu.

Giả sử file cấu hình tổ chức như sau:

~~~text
/WEB-INF/flows/
├── registration/
│   └── registration-flow.xml
├── booking/
│   └── booking-flow.xml
├── checkout/
│   └── checkout-flow.xml
└── shared/
    └── common-config.xml
~~~

Ta chỉ muốn lấy các file kết thúc bằng `-flow.xml`, không lấy `common-config.xml`. Một cấu hình ví dụ:

~~~xml
<webflow:flow-registry id="flowRegistry"
                       base-path="/WEB-INF/flows">
    <webflow:flow-location-pattern
        value="/**/*-flow.xml"/>
</webflow:flow-registry>
~~~

Ở đây:

- `base-path` chỉ ra **vùng cơ sở để tìm tài nguyên** của registry trong cấu hình này.
- `value` là **mẫu đường dẫn tài nguyên**, không phải route wildcard của `@RequestMapping`.
- Phần `**` cho phép quét qua các cấp thư mục theo cơ chế path pattern phù hợp.
- Tên kết thúc `-flow.xml` là **quy ước dự án tự chọn**, không phải đuôi file bắt buộc của Spring Web Flow.

**Chú ý:** cách suy ra **flow ID của từng tài nguyên được pattern tìm thấy** phụ thuộc quy tắc của flow registry builder, vị trí tương đối so với `base-path` và cấu hình thực tế. Đừng vội kết luận `booking-flow.xml` chắc chắn có ID `booking` hoặc `booking-flow` nếu chưa kiểm tra. Dùng test registry hoặc log phù hợp để xác nhận những ID thực sự được đăng ký trước khi thiết kế các URL và subflow references dựa trên chúng.

### 5.1. Pattern quá rộng tạo rủi ro gì?

Ví dụ này có thể quét nhiều hơn mục đích:

~~~xml
<webflow:flow-location-pattern value="/**/*.xml"/>
~~~

Nếu bên dưới vùng quét có XML phục vụ test, metadata, fragment hoặc cấu hình không phải flow definition, việc thử dựng tất cả như flow có thể dẫn đến lỗi build/parsing hoặc đăng ký những flow không mong muốn.

Ngay cả khi tất cả file đều là flow, quét quá rộng còn có thể khiến các flow **nội bộ** bị đăng ký với ID có thể được URL handler nhận diện ngoài dự kiến. Đăng ký một flow **không tự cấp quyền thực thi nghiệp vụ**, nhưng việc đăng ký không chủ đích là rủi ro cấu hình cần hạn chế.

Nên:

1. Dành thư mục riêng cho các XML flow có thể đăng ký.
2. Đặt quy ước tên rõ như `*-flow.xml` nếu phù hợp dự án.
3. Không để fixture/test XML hoặc fragment không phải flow trong vùng scan.
4. Kiểm tra danh sách ID sau khi đăng ký.
5. Đối chiếu URL handling và chính sách bảo mật cho những flow có thể được khởi động từ HTTP.

### 5.2. Pattern với nhiều cấp thư mục

Nếu hai nhóm có file tên giống nhau:

~~~text
/WEB-INF/flows/customer/details-flow.xml
/WEB-INF/flows/admin/details-flow.xml
~~~

cần biết cách registry tạo flow ID. Nếu cơ chế ID làm hai tài nguyên có cùng ID, có thể phát sinh **xung đột định danh**, lỗi đăng ký hoặc hành vi không mong muốn. Không sửa bằng cách thay file bất kỳ cho đến khi xác định rõ quy tắc.

Các phương án:

- Đặt ID tường minh thông qua `flow-location` cho các flow nhạy cảm.
- Điều chỉnh cấu trúc thư mục hoặc convention để các ID phân biệt được theo quy tắc registry.
- Chia vùng scan hoặc registry theo cấu trúc ứng dụng khi cần.
- Bổ sung test kiểm tra **không có ID trùng** và đúng tập flow mong đợi.

## 6. Định danh tường minh: contract ổn định hơn tên file

Tên logic của flow có thể xuất hiện ở nhiều nơi:

- URL do `FlowHandlerMapping` và `FlowUrlHandler` diễn giải.
- Thuộc tính `subflow` trong `subflow-state`.
- Đoạn code hoặc cấu hình tạo URL vào flow.
- Các assertion trong integration/flow tests.
- Tài liệu liên kết nội bộ đến hành trình.

Vì vậy, thay đổi flow ID có thể là **thay đổi contract** dù chỉ sửa một chuỗi ngắn trong XML cấu hình.

Ví dụ muốn dùng ID ngắn và ổn định:

~~~xml
<webflow:flow-location
    id="address-check"
    path="/WEB-INF/flows/shared/address-validation-flow.xml"/>
~~~

Flow cha gọi subflow:

~~~xml
<subflow-state id="verifyAddress" subflow="address-check">
    <input name="address" value="draft.address"/>
    <transition on="verified" to="review"/>
    <transition on="rejected" to="editAddress"/>
</subflow-state>
~~~

Phân biệt:

- `id="verifyAddress"`: **tên state trong flow cha**.
- `subflow="address-check"`: **flow ID được registry dùng để tìm flow con**.
- `address-validation-flow.xml`: **tên tệp XML**, không phải tên state.
- `verified`/`rejected`: **event mà flow con có thể trả về** theo hợp đồng của nó.

**Không cần đổi `subflow="address-check"`** chỉ vì file được chuyển thư mục, miễn là registry vẫn ánh xạ ID đó tới tài nguyên mới.

### 6.1. Khi nào ID tự suy ra từ đường dẫn vẫn chấp nhận được?

Khi dự án kiểm soát một convention lâu dài, mọi flow đều đăng ký theo pattern, registry tests bắt lỗi đổi ID và chưa có liên kết public/subflow quan trọng phụ thuộc vào tên tự sinh, việc suy ID có thể tiết kiệm công sức.

Nhưng với flow đã được dùng bởi người dùng hoặc flow khác, một ID tường minh giúp thay đổi cấu trúc thư mục dễ hơn. **Đổi tên file** lúc này không nhất thiết kéo theo **đổi URL**.

## 7. Kết nối registry với Spring MVC

Đăng ký định nghĩa flow chưa đồng nghĩa HTTP request đã tới được nó. Trong ứng dụng Spring MVC, cần các thành phần phù hợp:

~~~xml
<!-- Sau khi đã tạo flowRegistry và flowExecutor... -->
<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerMapping">
    <property name="flowRegistry" ref="flowRegistry"/>
    <property name="order" value="0"/>
</bean>

<bean class="org.springframework.webflow.mvc.servlet.FlowHandlerAdapter">
    <property name="flowExecutor" ref="flowExecutor"/>
</bean>
~~~

Cách phân công:

| Thành phần | Câu hỏi mà nó giải quyết |
|---|---|
| `FlowDefinitionRegistry` | “Có flow ID `booking` không?” |
| `FlowHandlerMapping` | “Request URL này có tương ứng flow đã đăng ký không?” |
| `FlowHandlerAdapter` | “Spring MVC sẽ chuyển request cho executor như thế nào?” |
| `FlowExecutor` | “Khởi động hay tiếp tục execution nào, state và event tiếp theo là gì?” |

Ví dụ trình tự:

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant MVC as DispatcherServlet
    participant MAP as FlowHandlerMapping
    participant EX as FlowExecutor
    participant REG as FlowRegistry

    C->>MVC: GET /booking
    MVC->>MAP: Tìm handler
    MAP->>REG: Kiểm tra flow ID được phân giải
    REG-->>MAP: Có definition booking
    MAP-->>MVC: FlowHandler booking
    MVC->>EX: Qua FlowHandlerAdapter để launch
    EX->>REG: Lấy definition booking
    REG-->>EX: Flow definition
    EX-->>C: Render state đầu và execution URL
~~~

Sơ đồ mang tính khái niệm; chính xác việc registry được lookup ở thời điểm nào là chi tiết implementation. Điều không thay đổi là **mapping URL** và **execution flow** thuộc những thành phần riêng.

### 7.1. Thứ tự HandlerMapping và xung đột URL

Spring MVC có thể có `@GetMapping("/booking")` trong controller cùng lúc với flow ID `booking`. Khi đó hai handler có thể cùng muốn xử lý URL. Kết quả phụ thuộc thứ tự và khả năng match của các `HandlerMapping`, không phải do Spring tự hiểu “GET thuộc controller, POST thuộc flow”.

Nên phân định rõ:

~~~text
GET /booking             -> Điểm vào Spring Web Flow
GET /booking-information -> Trang giới thiệu bằng MVC controller
POST /api/bookings       -> REST API riêng
~~~

Nếu ứng dụng dùng custom path mapping, các URL sẽ khác; ví dụ trên chỉ mô tả cách **tránh trùng trách nhiệm**.

### 7.2. Context path và servlet mapping

Một request trên trình duyệt:

~~~text
https://example.test/shop/booking
~~~

có thể gồm context path `/shop` và lookup path `/booking`. Nếu `DispatcherServlet` được map dưới một tiền tố hoặc reverse proxy rewrite URL, phần đường dẫn mà `FlowUrlHandler` dùng để lấy flow ID có thể khác.

**Không sửa flow ID chỉ vì có tiền tố context path.** Hãy kiểm tra mapping thực tế trước. URL trong log của proxy, URL servlet nhận và flow ID sau khi phân giải không nhất thiết có cùng dạng.

## 8. FlowUrlHandler liên quan thế nào tới định danh?

`FlowHandlerMapping` phối hợp với cơ chế URL handling của SWF, thường là `DefaultFlowUrlHandler`, để tìm **flow ID** từ request. Cơ chế này còn tham gia tạo URL bắt đầu flow hoặc URL tiếp tục một execution.

Giả sử registry chứa ID `booking` nhưng sản phẩm muốn công bố:

~~~text
/journeys/booking
~~~

Lúc này chỉ đổi tên file `booking.xml` thành `journeys-booking.xml` sẽ **không tự tạo URL mới**. Cần thay đổi routing/URL handler theo một cách nhất quán:

1. URL đầu vào được phân giải về flow ID `booking`.
2. URL mà SWF sinh ra khi tiếp tục vẫn quay về một endpoint được mapping nhận ra.
3. Query parameter/execution key được giữ qua redirect và proxy.
4. Các test HTTP mở được flow và POST sang bước sau thành công.

Nếu **chỉ chiều nhận URL** được tùy biến mà form action vẫn sinh đường dẫn cũ, người dùng có thể vào bước đầu nhưng thất bại khi bấm `next`.

### Không nhầm flow ID với execution key

Ví dụ:

~~~text
/booking?execution=<opaque-key>
~~~

- Phần path giúp xác định flow ID theo URL handler đang dùng.
- Tham số `execution` (hoặc cơ chế tương đương) dùng để tìm một **lần thực thi cụ thể**.
- Các event như `next` và `back` được gửi theo quy ước form/HTTP.

Không đưa execution key vào `id` của `flow-location`; registry lưu definition chung, không lưu một ID mới cho mỗi request.

## 9. Kết hợp flow-location và flow-location-pattern

Có thể xuất hiện nhu cầu:

- Quét các flow tiêu chuẩn nằm trong `/WEB-INF/flows/public`.
- Đăng ký thêm một flow ngoại lệ với tên ID có contract riêng.
- Không đưa các XML fragment hoặc test fixture vào registry.

Về mặt thiết kế, registry có thể cấu hình bằng các cách đăng ký được namespace/phiên bản hỗ trợ. Tuy nhiên, nếu **một file vừa được khai báo tường minh vừa được pattern quét tới**, sẽ tồn tại nguy cơ đăng ký hai lần hoặc xung đột flow ID.

Ví dụ về **phạm vi không chồng lắp**:

~~~text
/WEB-INF/flows/
├── standard/
│   ├── contact-flow.xml
│   └── order-flow.xml
└── special/
    └── secure-checkout.xml
~~~

Cấu hình minh họa:

~~~xml
<webflow:flow-registry id="flowRegistry">
    <webflow:flow-location-pattern
        value="/WEB-INF/flows/standard/*-flow.xml"/>

    <webflow:flow-location
        id="checkout"
        path="/WEB-INF/flows/special/secure-checkout.xml"/>
</webflow:flow-registry>
~~~

Trong ví dụ, pattern chỉ nên khớp hai file ở `standard`, còn đăng ký tường minh nằm ở `special`. **Sau khi áp dụng**, cần kiểm tra danh sách flow ID thực tế; đừng lấy sự khác nhau của tên file làm bằng chứng rằng không có xung đột ID.

Nếu dự án muốn dùng `base-path`, cần xác minh đường dẫn `value` được diễn giải tương đối với base path theo schema/version đang dùng, thay vì trộn tùy ý đường dẫn tương đối và tuyệt đối.

## 10. Tổ chức flow XML theo module và đường dẫn

Ba cấu trúc dự án phổ biến:

### 10.1. Tất cả flow dưới WEB-INF

~~~text
src/main/webapp/WEB-INF/flows/
    registration/registration.xml
    booking/booking.xml
    checkout/checkout.xml
~~~

Thích hợp với ứng dụng WAR dùng servlet web resource loader, đặc biệt khi cấu hình truyền thống của Spring MVC cùng tham chiếu `/WEB-INF/flows`.

### 10.2. Flow dưới classpath resources

~~~text
src/main/resources/flows/
    registration.xml
    booking.xml
~~~

Thích hợp với kiến trúc đóng gói tài nguyên classpath, nếu phiên bản và resource loader cho phép registry nạp theo cách được cấu hình. Kiểm tra đường dẫn classpath sau build, không đưa `src/main/resources` vào URL tài nguyên runtime.

### 10.3. Mỗi module cung cấp một nhóm flow

~~~text
application-web/
    src/main/webapp/WEB-INF/flows/
application-feature-booking/
    src/main/resources/flows/booking/
application-feature-registration/
    src/main/resources/flows/registration/
~~~

Mỗi module có thể có tài nguyên hoặc cấu hình riêng. Điều cần thống nhất là:

- Những flow nào thuộc registry được MVC/FlowExecutor dùng.
- Cách đặt ID tránh trùng nhau giữa feature.
- Cách nạp resource khi các module được đóng gói.
- Contract subflow references giữa các module.
- Kiểm thử bao gồm cả packaging thực tế.

Không nên mặc định một pattern trên `/WEB-INF/flows` có thể quét tài nguyên nằm sâu trong mọi dependency JAR. Đó là **hai vùng resource khác nhau** với cơ chế tìm kiếm phụ thuộc context.

## 11. Những lỗi thường gặp và cách chẩn đoán

### 11.1. File XML tồn tại nhưng flow không được tìm thấy

**Dấu hiệu:** GET điểm vào trả 404 hoặc log cho thấy không tìm được flow ID.

**Kiểm tra:**

- `FlowHandlerMapping` có được đăng ký trong Spring MVC context không?
- URL handler diễn giải request ra flow ID nào?
- Registry có chứa ID đó không?
- Tài nguyên XML có được đưa vào deployment và nạp thành công không?
- Nếu dùng pattern, nó có thật sự match đường dẫn file không?

Không chỉ kiểm tra `File.exists()` ở source tree rồi kết luận lỗi thuộc MVC.

### 11.2. Mở được flow khác nhưng không mở được flow mới thêm

Khả năng cao registry đã được wire đúng, còn file mới không khớp pattern, nằm sai base path hoặc được đăng ký dưới ID khác. Bắt đầu bằng **ID được registry nhận diện** và **tài nguyên mà builder thực sự nạp**.

### 11.3. Flow ID sai do đổi tên thư mục/file

Khi ID được suy từ resource path, việc đổi tên file hoặc vị trí tương đối có thể đổi ID. Một URL cũ hoặc `subflow="..."` cũ sẽ không còn khớp.

Để tránh tái phát, định nghĩa ID tường minh cho những contract quan trọng và viết regression test tra cứu ID này.

### 11.4. Hai flow có ID trùng nhau

Có thể do pattern bao phủ hai file có tên/convention tương tự, hoặc khai báo tường minh cùng ID với một flow tự nhận diện. Kiểm tra cấu hình và cơ chế tạo ID; không nên giả định registry sẽ tự quyết định một flow “thắng” mà không có hậu quả.

### 11.5. Lỗi parse XML hoặc thiếu Spring bean khi dựng flow

Nếu resource được tìm nhưng namespace/schema của XML sai, Spring bean không tồn tại hoặc expression cấu hình không hợp lệ, lỗi phát sinh **sau khi đã tìm thấy tài nguyên**. Cần đọc nguyên nhân trong log để xác định phần parser/builder hoặc dependency.

### 11.6. GET điểm vào đúng, POST tiếp theo thất bại

Đây có thể là lỗi **execution key**, session hoặc form action URL, không phải lỗi ID của registry.

Kiểm tra:

1. Form dùng `flowExecutionUrl` do SWF cấp hay hardcode?
2. Execution key có còn hợp lệ và thuộc session phù hợp không?
3. Request có gửi đúng event như `_eventId_next` không?
4. Reverse proxy có giữ nguyên path và query string không?
5. Security/CSRF có chặn request trước khi tới flow không?

### 11.7. Subflow không được tìm thấy khi chuyển bước

Flow cha có thể đã được đăng ký và chạy nhiều bước rồi mới gặp lỗi tại `subflow-state`. Đối chiếu thuộc tính `subflow` với flow ID trong registry. **Đừng nhầm ID của subflow-state với ID của flow con.**

### 11.8. Pattern quét cả XML không phải flow

Giới hạn glob và phân loại thư mục. Một tệp cấu hình dùng lại cho flow không nên vô tình trở thành public flow definition. Nếu cần flow kế thừa hoặc resource phụ trợ, dùng cơ chế phù hợp cho model resources thay vì scan mọi XML.

## 12. Kiểm thử registry: xác nhận ID thực sự tồn tại

Lỗi định danh thường rất phù hợp với **test tự động** vì có thể phát hiện trước khi vào browser.

Ví dụ một test dùng Spring Test và registry thật của ứng dụng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;

// Cần nạp cấu hình thực tế tạo flowRegistry của dự án.
@SpringJUnitConfig(locations = "classpath:/spring/flow-config.xml")
class FlowRegistryConfigurationTest {

    @Autowired
    private FlowDefinitionRegistry flowRegistry;

    @Test
    void importantFlowIdsAreRegistered() {
        assertTrue(flowRegistry.containsFlowDefinition("registration"));
        assertTrue(flowRegistry.containsFlowDefinition("booking"));
        assertTrue(flowRegistry.containsFlowDefinition("checkout"));
    }

    @Test
    void bookingFlowIdHasExpectedIdentity() {
        assertEquals(
            "booking",
            flowRegistry.getFlowDefinition("booking").getId()
        );
    }
}
~~~

Ví dụ này giả định dự án dùng **JUnit Jupiter/Spring Test tương thích** và file Spring config nằm trên classpath ở vị trí đã nêu. Nếu ứng dụng dùng web resource `/WEB-INF/flows` cần servlet context khi dựng registry, test context phải mô phỏng/nạp đúng web application context; một `@SpringJUnitConfig` thuần có thể không đủ.

**Khi dùng pattern**, nên mở rộng phép thử để xác nhận *danh sách flow ID đúng như dự kiến* thay vì chỉ kiểm tra một ID. Nếu registry API của phiên bản hỗ trợ truy xuất tất cả ID, có thể so sánh với tập tên mong đợi.

Ví dụ minh họa assertion cho danh sách:

~~~java
// Chỉ chạy khi FlowDefinitionRegistry của phiên bản
// đang dùng cung cấp getFlowDefinitionIds().
assertThat(flowRegistry.getFlowDefinitionIds())
    .contains("registration", "booking", "checkout")
    .doesNotContain("test-flow", "common-config");
~~~

Đoạn này sử dụng cú pháp AssertJ để minh họa; thêm import/dependency tương ứng khi áp dụng. Khi dự án chủ động có nhiều flow hơn, assertion cần phù hợp contract cụ thể thay vì khóa cứng tập ID bất biến một cách không cần thiết.

### 12.1. Flow execution test xác minh điều gì?

Một flow execution test nạp đúng XML và gọi `startFlow()`, `signalEvent("next")` sẽ chứng minh định nghĩa có thể chạy và transition liên quan hoạt động trong test harness.

Nhưng nếu test tự nạp XML trực tiếp qua `getResource(...)`, nó **không nhất thiết** chứng minh `FlowHandlerMapping` ngoài runtime có thể mở URL `/booking`. Phần registry/HTTP mapping cần test riêng.

### 12.2. HTTP integration test xác minh điều gì?

Một phép thử qua Spring MVC có thể:

1. GET URL điểm vào flow.
2. Kiểm tra handler/view/redirect đúng với flow dự kiến.
3. Lấy flow execution URL do trang render.
4. POST event `next` với session và CSRF token nếu ứng dụng yêu cầu.
5. Kiểm tra state và dữ liệu đã chuyển, không chỉ HTTP status.
6. Thử URL sai hoặc flow ID không đăng ký để xác nhận phản hồi phù hợp.
7. Thử controller route cạnh đó để chắc chắn flow mapping không chiếm nhầm URL.

**Không hardcode key** như `execution=e1s1`; nó được phát hành theo repository/snapshot thực tế.

## 13. Một ma trận kiểm thử dành cho ba chiến lược

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| R01 | `flow-location` có ID và path đúng | Registry tìm được definition qua ID đó |
| R02 | File XML bị đổi tên nhưng path cũ | Test build/registry phát hiện resource thiếu |
| R03 | Giữ ID, cập nhật đúng path mới | Contract ID vẫn ổn định |
| R04 | Pattern khớp flow mới thêm | Flow được registry đăng ký đúng ID đã xác minh |
| R05 | Pattern không khớp fragment XML | Fragment không bị đăng ký thành flow |
| R06 | Hai file tạo trùng ID | Test/config phát hiện xung đột, không sử dụng kết quả nhập nhằng |
| R07 | Flow cha gọi đúng ID subflow | Subflow được tìm và có transition về cha |
| R08 | Flow cha dùng ID con sai | Test bắt được lỗi lookup subflow |
| R09 | GET điểm vào của flow đã đăng ký | MVC nhận đúng handler, flow bắt đầu được |
| R10 | GET URL không thuộc flow | Không bị mapping flow nhận nhầm |
| R11 | POST dùng URL/key tiếp tục hợp lệ | SWF resume đúng execution |
| R12 | Context path/servlet prefix thay đổi | URL handler vẫn phân giải đúng theo triển khai |
| R13 | CSRF/authorization thiếu | Request bị chặn theo chính sách bảo mật |
| R14 | Sửa tên file trong packaging thực tế | Registry ở môi trường deployment vẫn đọc được resource |

Ma trận này nên được điều chỉnh theo số lượng flow và rủi ro ứng dụng. Đăng ký pattern thường cần nhiều test về **tập tài nguyên được quét và ID được sinh ra** hơn cấu hình tường minh.

## 14. Bảo mật, vòng đời và khả năng mở rộng

Đăng ký flow là bước về cấu hình, không phải biện pháp phân quyền. Nếu flow `admin-review` được registry nhận diện từ URL, người dùng không được phép vẫn phải bị ngăn ở tầng security hoặc service.

### 14.1. Bảo vệ thao tác chứ không chỉ URL

- Sử dụng authentication/authorization phù hợp với endpoint, state/action hoặc logic nghiệp vụ.
- Kiểm tra CSRF cho request thay đổi trạng thái theo chính sách ứng dụng.
- Chỉ cho bind các field được phép ở từng `view-state`.
- Validate dữ liệu và kiểm tra lại quyền khi service ghi dữ liệu.
- Không đặt thông tin nhạy cảm vào URL, message hoặc log không kiểm soát.

### 14.2. Scope và phiên không được giải quyết bởi registry

`FlowDefinitionRegistry` không lưu `draft` của từng người dùng. Khi flow chạy, mỗi execution quản lý scope của nó theo cơ chế SWF. Dùng `flowScope` hoặc `conversationScope` đúng mục đích; tránh một `sessionScope.currentDraft` được dùng cho mọi tab nếu ứng dụng cho phép nhiều form độc lập.

### 14.3. Thêm flow mới không đồng nghĩa tăng vô hạn execution

Registry có thể chứa nhiều định nghĩa flow, nhưng mỗi người dùng có thể tạo nhiều **flow execution**. Giới hạn session/repository, snapshot history, bộ nhớ và timeout cần được thiết kế riêng. Đừng điều chỉnh giới hạn thực thi bằng cách sửa số lượng flow được pattern đăng ký.

### 14.4. Chú ý triển khai đa node và đổi phiên bản

Một lần triển khai có thể thay đổi tập flow ID hoặc file XML giữa các phiên bản ứng dụng. Người dùng đang có execution cũ có thể gặp vấn đề khi resume trên node chạy định nghĩa khác. Cần chính sách triển khai tương thích, session routing và xử lý lỗi execution không còn phục hồi được.

**Không tự động khởi tạo flow mới rồi bỏ qua dữ liệu cũ** mỗi khi key không còn hợp lệ. Nếu có chức năng lưu bản nháp, phải thông báo và phục hồi theo thiết kế rõ ràng.

## 15. Bài tập: đăng ký hệ thống đặt lịch có flow con

Giả sử có ba yêu cầu:

- `appointment`: hành trình đặt lịch chính.
- `address-check`: subflow xác thực địa chỉ.
- `cancel-request`: hành trình yêu cầu hủy lịch, có thể được mở từ trang riêng.

Bố cục file:

~~~text
/WEB-INF/flows/
├── appointment/
│   └── appointment-flow.xml
├── shared/
│   └── address-validation-flow.xml
└── cancellation/
    └── cancel-request-flow.xml
~~~

**Phần A — Khai báo tường minh**

1. Tạo registry với `flow-location id="appointment"` trỏ đến `appointment-flow.xml`.
2. Đăng ký flow con bằng `id="address-check"`, trỏ tới `address-validation-flow.xml`.
3. Đăng ký `cancel-request` theo path tương ứng.
4. Nối registry vào executor và cấu hình `FlowHandlerMapping`/`FlowHandlerAdapter`.
5. Viết test xác nhận ba ID đúng, không phụ thuộc tên file.

**Phần B — Thử quét bằng pattern**

1. Tạo thư mục riêng chứa các file tuân theo `*-flow.xml`.
2. Khai báo `flow-location-pattern` chỉ cho khu vực đó.
3. Xem registry thực tế tạo ID nào; **ghi lại kết quả trước khi sửa URL hoặc subflow reference**.
4. Đặt một file `common-config.xml` vào cây thư mục để kiểm tra pattern có tránh đăng ký nhầm không.
5. Nếu ID sinh ra không phù hợp contract của ứng dụng, chuyển các flow quan trọng sang khai báo ID tường minh hoặc thay đổi convention có kiểm thử.

**Phần C — Bắt lỗi chủ đích**

1. Đổi `path` của `address-check` thành đường dẫn không tồn tại.
2. Quan sát registry/build hoặc execution test báo lỗi; sửa lại đúng file.
3. Đổi `subflow="address-check"` thành ID sai và xem failure xuất hiện ở state nào.
4. Tạo controller `@GetMapping("/appointment")` trùng URL, kiểm tra handler nào được chọn.
5. Test POST `next` qua form execution URL do SWF sinh ra; không hardcode key.

### Câu hỏi ôn tập

**1. `flow-location` và `flow-location-pattern` khác nhau ở điểm nào?** Một cách chỉ rõ tài nguyên; cách kia tìm tài nguyên bằng mẫu, thường theo quy ước tên/thư mục.

**2. `id="flowRegistry"` có phải flow ID không?** Không. Đó là tên bean registry; mỗi `flow-location` có thể có flow ID riêng.

**3. Vì sao file `appointment-flow.xml` không bảo đảm ID sẽ là `appointment` khi dùng pattern?** Vì ID phụ thuộc cơ chế suy ID của registry và cấu trúc đường dẫn; phải kiểm tra thực tế.

**4. Có thể đổi tên file XML mà không đổi URL flow không?** Có thể, nếu giữ ID và cấu hình URL handler ổn định, đồng thời cập nhật đúng tài nguyên path.

**5. Đã đăng ký ID `appointment`, có tự sinh URL `/appointment/review` không?** Không. `review` là state của execution; URL công khai và việc tiếp tục execution do MVC/SWF URL handling quyết định.

**6. Vì sao test `startFlow()` thành công chưa đủ?** Vì nó có thể kiểm tra XML trực tiếp mà chưa kiểm tra registry production, URL mapping, session, execution key hoặc view qua HTTP.

**7. Khi flow cha gọi subflow sai ID, nên sửa state ID hay thuộc tính `subflow`?** Kiểm tra `subflow` và registry; state ID trong flow cha là khái niệm khác.

## 16. Checklist cấu hình registry trước khi bàn giao

- [ ] Đã xác định những flow thực sự cần đăng ký.
- [ ] Mỗi tài nguyên XML được nạp từ vị trí tồn tại trong artifact/runtime.
- [ ] Flow ID của các hành trình public và các subflow quan trọng được xác định rõ.
- [ ] Nếu dùng pattern, quy tắc tên file và base path được mô tả nhất quán.
- [ ] Pattern không quét nhầm fixture, fragment hoặc cấu hình không phải flow.
- [ ] Không có ID trùng hoặc sự chồng lắp không chủ ý giữa pattern và khai báo tường minh.
- [ ] `FlowExecutor` dùng đúng `FlowDefinitionRegistry`.
- [ ] `FlowHandlerMapping` và `FlowHandlerAdapter` được nạp ở Spring MVC context đúng.
- [ ] Controller, REST route và flow không cạnh tranh cùng URL ngoài thiết kế.
- [ ] Flow cha tham chiếu đúng ID của flow con.
- [ ] Form và redirect dùng flow execution URL phù hợp, không dùng path tài nguyên XML.
- [ ] Context path, servlet mapping, proxy và execution key đã được kiểm thử qua HTTP.
- [ ] Security/CSRF/authorization và binder whitelist được áp dụng phù hợp.
- [ ] Có registry test và flow/HTTP integration test cho các đường đi chính.
- [ ] Thay đổi tên file, ID hoặc layout thư mục được xem xét như thay đổi contract có regression test.

**Ghi nhớ:** `FlowDefinitionRegistry` xác định **những flow definition nào tồn tại và chúng có ID gì**; `flow-location` và `flow-location-pattern` là hai cơ chế đăng ký tài nguyên; thuộc tính `id` tường minh giúp giữ hợp đồng logic ổn định khi di chuyển file. Sau đó `FlowHandlerMapping`, `FlowHandlerAdapter` và `FlowExecutor` mới đưa định nghĩa này vào một hành trình HTTP có state, event, dữ liệu và execution riêng. Kiểm tra đúng ranh giới từ resource đến registry rồi tới URL sẽ giúp tránh nhiều lỗi cấu hình khó chẩn đoán.

