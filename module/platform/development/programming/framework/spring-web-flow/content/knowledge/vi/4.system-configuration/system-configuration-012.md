# Kiểm tra cấu hình bằng một yêu cầu khởi chạy tối giản

Trong chương **Cấu hình hệ thống**, bài này dùng một yêu cầu HTTP nhỏ để xác nhận Spring Web Flow đã được nối đúng với Spring MVC. Mục tiêu là kiểm tra đường đi từ URL khởi chạy, bộ đăng ký định nghĩa flow, bộ thực thi flow đến view đầu tiên. Đây là bước kiểm tra nền tảng cho module **SPRING_WEB_FLOW**: mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow, sau đó mới mở rộng sang form binding, validation, scope, phiên và xử lý lỗi.

Một ứng dụng có thể khởi động thành công nhưng flow vẫn không chạy vì registry không tìm thấy định nghĩa, handler không nhận URL hoặc view resolver không tìm thấy view. Vì vậy, hãy kiểm tra bằng một request thực tế thay vì chỉ dựa vào việc ứng dụng đã khởi động.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Đăng ký một flow XML trong **FlowDefinitionRegistry**.
- Kết nối **FlowExecutor**, **FlowHandlerMapping** và **FlowHandlerAdapter** với Spring MVC.
- Tạo một flow có view-state đầu tiên để kiểm tra đường khởi chạy.
- Gửi **GET /checkout** và nhận biết phản hồi cho biết flow đã được khởi chạy.
- Phân biệt lỗi định tuyến, lỗi nạp flow và lỗi phân giải view.

## Một request khởi chạy kiểm tra những gì?

Với cấu hình mặc định, URL chứa flow ID. Ví dụ, **GET /checkout** yêu cầu Spring Web Flow khởi chạy flow có ID **checkout**.

1. **DispatcherServlet** nhận request.
2. **FlowHandlerMapping** nhận diện URL và chọn flow handler tương ứng.
3. **FlowHandlerAdapter** chuyển request cho **FlowExecutor**.
4. **FlowExecutor** yêu cầu **FlowDefinitionRegistry** tìm định nghĩa flow **checkout**, sau đó tạo một flow execution mới.
5. Flow đi vào state đầu tiên. Trong ví dụ này, đó là một **view-state**.
6. Spring Web Flow tạo URL thực thi có execution key để những request tiếp theo có thể tiếp tục đúng flow execution. View đầu tiên được phân giải và hiển thị theo cấu hình MVC.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant D as DispatcherServlet
    participant M as FlowHandlerMapping
    participant A as FlowHandlerAdapter
    participant R as FlowDefinitionRegistry
    participant E as FlowExecutor
    participant V as ViewResolver

    B->>D: GET /checkout
    D->>M: Tìm handler
    M-->>D: Flow handler cho checkout
    D->>A: Chuyển request
    A->>R: Tìm định nghĩa checkout
    R-->>A: Flow definition
    A->>E: Khởi chạy flow
    E-->>A: Execution tạm dừng tại view-state
    A-->>B: Redirect có execution key
    B->>D: GET URL thực thi
    D->>A: Tiếp tục execution
    A->>V: Phân giải flow/start
    V-->>B: Nội dung view
~~~

Execution key gắn với một flow execution cụ thể. Khi kiểm tra thủ công bằng trình duyệt hoặc **curl**, cần giữ cookie phiên giữa request khởi chạy và request tiếp theo. Nếu mất phiên, ứng dụng có thể không tìm thấy execution tương ứng.

## 1. Chuẩn bị dependency và vị trí flow

Ứng dụng cần có Spring MVC và Spring Web Flow trên classpath. Ví dụ dependency Maven cho Spring Web Flow:

~~~xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow</artifactId>
    <version>${spring-webflow.version}</version>
</dependency>
~~~

Khai báo property hoặc dependency management để cung cấp phiên bản cụ thể. Phiên bản Spring Web Flow phải tương thích với phiên bản Spring Framework/Spring MVC đang dùng; không chọn phiên bản tùy ý chỉ để làm cho dependency được tải xuống.

Trong ví dụ này, đặt flow tại:

~~~text
src/main/webapp/
└── WEB-INF/
    ├── flows/
    │   └── checkout-flow.xml
    └── views/
        └── flow/
            └── start.jsp
~~~

Tên **checkout-flow.xml** được dùng để đăng ký flow ID **checkout** với cấu hình registry bên dưới. Nếu dự án đặt flow trong thư mục khác, **basePath** và location pattern phải khớp với vị trí thực tế.

## 2. Kết nối Spring Web Flow với Spring MVC

Có thể dùng Java configuration thông qua **AbstractFlowConfiguration**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.webflow.config.AbstractFlowConfiguration;
import org.springframework.webflow.definition.registry.FlowDefinitionRegistry;
import org.springframework.webflow.execution.FlowExecutor;
import org.springframework.webflow.mvc.servlet.FlowHandlerAdapter;
import org.springframework.webflow.mvc.servlet.FlowHandlerMapping;

@Configuration
public class WebFlowConfig extends AbstractFlowConfiguration {

    @Bean
    public FlowDefinitionRegistry flowRegistry() {
        return getFlowDefinitionRegistryBuilder()
                .setBasePath("/WEB-INF/flows")
                .addFlowLocationPattern("/**/*-flow.xml")
                .build();
    }

    @Bean
    public FlowExecutor flowExecutor() {
        return getFlowExecutorBuilder(flowRegistry()).build();
    }

    @Bean
    public FlowHandlerMapping flowHandlerMapping() {
        FlowHandlerMapping mapping = new FlowHandlerMapping();
        mapping.setOrder(-1);
        mapping.setFlowRegistry(flowRegistry());
        return mapping;
    }

    @Bean
    public FlowHandlerAdapter flowHandlerAdapter() {
        FlowHandlerAdapter adapter = new FlowHandlerAdapter();
        adapter.setFlowExecutor(flowExecutor());
        return adapter;
    }
}
~~~

Bốn bean đảm nhiệm bốn phần việc liên quan:

| Thành phần | Trách nhiệm |
|---|---|
| **FlowDefinitionRegistry** | Tìm và cung cấp định nghĩa flow theo ID. |
| **FlowExecutor** | Tạo mới, tiếp tục và quản lý việc thực thi flow. |
| **FlowHandlerMapping** | Ánh xạ URL đến flow handler. |
| **FlowHandlerAdapter** | Chuyển request của Spring MVC thành thao tác khởi chạy hoặc tiếp tục flow. |

**mapping.setOrder(-1)** đặt flow handler mapping ở thứ tự ưu tiên cao để URL của flow được xem xét trước các handler mapping có độ ưu tiên thấp hơn. Nếu một controller khác cũng nhận **/checkout**, hãy kiểm tra thứ tự mapping và phạm vi URL để tránh xung đột.

**WebFlowConfig** phải được nạp vào web application context phục vụ **DispatcherServlet**. Đồng thời, ứng dụng cần có cấu hình Spring MVC và view resolver phù hợp. Ví dụ, nếu dùng JSP:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.view.InternalResourceViewResolver;

@Configuration
@EnableWebMvc
public class WebMvcConfig {

    @Bean
    public InternalResourceViewResolver viewResolver() {
        InternalResourceViewResolver resolver =
                new InternalResourceViewResolver();
        resolver.setPrefix("/WEB-INF/views/");
        resolver.setSuffix(".jsp");
        return resolver;
    }
}
~~~

Với cấu hình trên, view name **flow/start** được phân giải thành **/WEB-INF/views/flow/start.jsp**. Nếu dự án dùng Thymeleaf hoặc một view technology khác, hãy giữ nguyên nguyên tắc: view name trong flow phải được bộ phân giải view đang cấu hình xử lý được.

## 3. Tạo flow tối giản

Tạo **checkout-flow.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <view-state id="start" view="flow/start">
        <transition on="continue" to="done"/>
    </view-state>

    <end-state id="done" view="flow/done"/>
</flow>
~~~

State đầu tiên là **start**. Khi flow được khởi chạy, Spring Web Flow đi vào **view-state** này và yêu cầu MVC phân giải view **flow/start**. Transition **continue** minh họa cách một event chuyển flow sang state kết thúc **done**. Event này chưa cần thiết cho phép thử khởi chạy; nó chỉ cho thấy flow có một đường đi tiếp theo hợp lệ.

Tạo view đầu tiên tại **WEB-INF/views/flow/start.jsp**:

~~~jsp
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Spring Web Flow startup check</title>
</head>
<body>
    <h1>Flow checkout đã khởi chạy</h1>
    <p>Ứng dụng đã tìm thấy flow definition và phân giải được view đầu tiên.</p>
</body>
</html>
~~~

Nếu muốn thử transition sau khi phép thử khởi chạy đã thành công, tạo thêm **WEB-INF/views/flow/done.jsp** và gửi event **continue** từ view đầu tiên. Có thể dùng form của Spring MVC/Spring Web Flow để gửi event; khi đó cần kiểm tra thêm tên event, binding và token execution. Những phần đó thuộc bước kiểm tra tương tác tiếp theo, không phải điều kiện để xác nhận request khởi chạy đầu tiên.

## 4. Gửi request khởi chạy

Khởi động ứng dụng và gửi request đến flow ID:

~~~bash
curl -i -c cookies.txt http://localhost:8080/app/checkout
~~~

Thay **/app** bằng context path thực tế của ứng dụng. Với cấu hình mặc định và flow đang dừng ở **view-state**, response đầu tiên thường là một redirect đến URL có execution key. Ví dụ minh họa:

~~~http
HTTP/1.1 302 Found
Location: /app/checkout?execution=e1s1
Set-Cookie: JSESSIONID=...
~~~

Giá trị execution key và session ID thay đổi theo từng lần chạy. Hãy đọc **Location** thực tế trong response, không cố định **e1s1** trong script kiểm thử.

Tiếp tục request đến URL trong header **Location**, đồng thời gửi lại cookie phiên:

~~~bash
curl -i -b cookies.txt "http://localhost:8080/app/checkout?execution=<execution-key>"
~~~

Kết quả mong đợi là nội dung HTML của **start.jsp**. Nếu muốn **curl** tự đi theo redirect, có thể dùng tùy chọn **-L** và giữ cookie bằng **-c cookies.txt -b cookies.txt**; tuy nhiên, gửi riêng request đầu tiên sẽ giúp quan sát rõ status và header **Location**.

## 5. Tự động hóa phép thử bằng MockMvc

Một kiểm thử tích hợp nhỏ giúp phát hiện sớm lỗi ánh xạ URL hoặc khởi chạy flow. Ví dụ dưới đây giả định **WebMvcConfig** và **WebFlowConfig** đã được nạp trong cùng web application context:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(classes = {
        WebMvcConfig.class,
        WebFlowConfig.class
})
@WebAppConfiguration
class CheckoutFlowStartupTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.webAppContextSetup(context).build();
    }

    @Test
    void launchesCheckoutFlow() throws Exception {
        mockMvc.perform(get("/checkout"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location",
                        containsString("execution=")));
    }
}
~~~

Kiểm thử này xác nhận URL được xử lý như một request khởi chạy flow và response chứa execution key theo hành vi redirect mặc định. Nếu ứng dụng tùy biến **FlowUrlHandler**, cách redirect hoặc điểm kết thúc flow, hãy điều chỉnh assertion theo hợp đồng URL thực tế của cấu hình đó.

Có thể mở rộng kiểm thử bằng cách giữ lại **MockHttpSession** giữa request đầu tiên và request tiếp theo, rồi xác nhận view đầu tiên được trả về. Khi kiểm tra chuỗi request, hãy dùng cùng session để mô phỏng trình duyệt; nếu mỗi request tạo một session mới, flow execution có thể không còn được tìm thấy.

## 6. Đọc kết quả và xử lý lỗi thường gặp

| Biểu hiện | Vị trí cần kiểm tra |
|---|---|
| **404 Not Found** tại **/checkout** | **FlowHandlerMapping** chưa được nạp, URL không khớp flow ID, hoặc flow chưa được đăng ký trong registry. |
| Lỗi khi phân tích flow XML | Kiểm tra cú pháp XML, namespace, schema và tên state/transition. |
| **500 Internal Server Error** khi vào view đầu tiên | Kiểm tra view name, prefix/suffix của view resolver, đường dẫn JSP và cấu hình web context. |
| Redirect không có execution key | Xem flow có kết thúc ngay hay không, kiểm tra **FlowHandler**/**FlowUrlHandler** tùy biến và response thực tế. |
| Request tiếp theo báo không tìm thấy execution | Gửi lại cookie phiên, giữ nguyên session và dùng đúng execution key từ response khởi chạy. |
| **/checkout** bị controller khác xử lý | Kiểm tra thứ tự **HandlerMapping**, URL mapping của controller và cấu hình **FlowHandlerMapping**. |

Nên đọc log theo thứ tự từ ngoài vào trong: request có đến **DispatcherServlet** không, handler nào được chọn, flow ID có được resolve không, flow có vào state đầu tiên không, cuối cùng view name có được phân giải không. Cách lần theo này giúp khoanh vùng đúng lớp cấu hình thay vì sửa đồng thời nhiều thành phần.

## 7. Giới hạn của phép thử khởi chạy

Một request khởi chạy thành công chứng minh được đường tích hợp cơ bản giữa Spring MVC và Spring Web Flow: URL được định tuyến, flow definition được tìm thấy, execution được tạo và state đầu tiên có thể được xử lý. Khi view đầu tiên hiển thị được, cấu hình view resolver cũng đã tham gia thành công.

Phép thử này chưa chứng minh form binding, validation, event transition, subflow, phạm vi **viewScope**/**flowScope**/**conversationScope**, hay khả năng phục hồi khi lỗi xảy ra giữa hành trình. Các phần đó cần request và assertion riêng. Đặc biệt, khi kiểm thử nhiều bước, phải giữ session và execution key xuyên suốt các request để kiểm tra đúng một flow execution.

Hãy giữ request **GET /checkout** như một smoke test nhỏ sau mỗi lần thay đổi registry, executor, handler mapping hoặc view resolver. Khi phép thử này ổn định, có thể thêm kiểm thử cho event **continue**, dữ liệu form, validation lỗi và việc gọi subflow để xác nhận toàn bộ hành trình web nhiều bước.
