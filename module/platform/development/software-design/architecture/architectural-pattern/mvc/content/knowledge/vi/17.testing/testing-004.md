# Kiểm thử dữ liệu trình bày và quyết định chọn View

Trong ứng dụng MVC, Controller không chỉ tiếp nhận request mà còn quyết định phản hồi sẽ được trình bày như thế nào. Với một request đọc dữ liệu, Controller hoặc lớp điều phối có thể chọn View chi tiết, View danh sách, trang rỗng hoặc trang không tìm thấy. Dữ liệu đưa vào View thường đã được chuyển thành DTO hoặc ViewModel để giao diện không phụ thuộc trực tiếp vào Entity và quy tắc nghiệp vụ.

Kiểm thử phần này cần trả lời hai câu hỏi: dữ liệu nào được cung cấp cho giao diện và ứng dụng đã chọn đúng View cho kết quả xử lý hay chưa? Một bài kiểm thử chỉ xác nhận Service được gọi chưa chứng minh Controller chọn đúng template. Một bài kiểm thử chỉ xác nhận tên View cũng chưa chứng minh template thực sự kết xuất HTML đúng và an toàn.

Trong MVC, nên kiểm thử theo các ranh giới: mapper tạo dữ liệu trình bày, Controller chọn View và đưa dữ liệu vào Model, ViewResolver tìm template, template engine kết xuất nội dung, cuối cùng trình duyệt nhận phản hồi phù hợp.

## 1. Dữ liệu trình bày trong MVC

Dữ liệu trình bày là phần thông tin được chuẩn bị cho một màn hình hoặc một dạng phản hồi cụ thể. Nó có thể gồm dữ liệu nghiệp vụ đã chọn lọc, nhãn hiển thị, chuỗi định dạng, trạng thái giao diện và các quyền hiển thị hành động.

Ví dụ trang chi tiết đơn hàng có thể cần:

- Mã đơn hàng.
- Tên khách hàng.
- Nhãn trạng thái đã dịch.
- Ngày tạo theo múi giờ người xem.
- Tổng tiền đã định dạng theo Locale.
- Cờ cho biết có thể hiển thị nút hủy đơn hay không.

Trang không cần nhận toàn bộ Entity đơn hàng, đối tượng thanh toán, thông tin nội bộ hoặc dữ liệu xác thực.

### 1.1. Phân biệt Entity, DTO và ViewModel

| Kiểu dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Entity/Domain Model | Trạng thái và quy tắc nghiệp vụ | **Order**, **OrderLine** |
| Projection/query result | Lấy đúng các trường cần truy vấn | **OrderDetailProjection** |
| DTO | Trao đổi dữ liệu qua ranh giới tầng hoặc API | **OrderDetailResponse** |
| ViewModel | Chuẩn bị dữ liệu cho một màn hình cụ thể | **OrderDetailView** |

Không phải dự án nào cũng cần đủ bốn kiểu. Một ứng dụng nhỏ có thể dùng DTO làm ViewModel. Tuy nhiên, cần giữ ý nghĩa rõ ràng: dữ liệu trình bày được thiết kế theo nhu cầu giao diện, còn Entity bảo vệ trạng thái và quy tắc miền nghiệp vụ.

### 1.2. ViewModel là một hợp đồng có thể kiểm thử

Ví dụ:

~~~java
public record OrderDetailView(
    String orderNumber,
    String customerName,
    String statusLabel,
    String createdAtText,
    String totalText,
    boolean canCancel
) {}
~~~

Hợp đồng này mô tả đúng dữ liệu trang chi tiết cần. Khi kiểm thử, có thể xác nhận mapper tạo đủ trường, định dạng đúng và không đưa dữ liệu nội bộ vào ViewModel.

Không nên đưa trực tiếp những trường như **paymentToken**, **internalNote** hoặc thông tin xác thực vào ViewModel chỉ vì Entity đang có sẵn chúng.

## 2. Những quyết định cần kiểm thử

Một request MVC thường có một số nhánh kết quả. Mỗi nhánh có thể yêu cầu View, status code và dữ liệu khác nhau.

| Tình huống | View hoặc phản hồi mong đợi | Dữ liệu cần kiểm tra |
|---|---|---|
| Tìm thấy tài nguyên | **orders/detail** | ViewModel chi tiết |
| Danh sách có dữ liệu | **orders/list** | Items, metadata phân trang |
| Danh sách rỗng | **orders/list** | Items rỗng và trạng thái rỗng |
| Không tìm thấy tài nguyên | **errors/404** | Thông tin lỗi an toàn, status 404 |
| Dữ liệu biểu mẫu không hợp lệ | View biểu mẫu ban đầu | Giá trị đã nhập và lỗi theo trường |
| Gửi biểu mẫu thành công | Redirect sang GET | URL đích và flash message |
| Không đủ quyền | Trang 403 hoặc response phù hợp | Không lộ dữ liệu tài nguyên |
| Lỗi hệ thống | Trang lỗi chung hoặc API error | Không lộ stack trace |

Không phải mọi ứng dụng đều dùng đúng các tên View trên. Điều cần kiểm thử là hợp đồng đã thiết kế: kết quả nào dẫn đến phản hồi nào và phản hồi đó chứa những dữ liệu gì.

### 2.1. Tách quyết định nghiệp vụ khỏi quyết định trình bày

Service xác định đơn hàng có tồn tại, người dùng có quyền xem hoặc thao tác có hợp lệ hay không. Controller chuyển kết quả đó thành View hoặc HTTP response.

Ví dụ, Service có thể trả về **Optional<OrderDetailView>** cho truy vấn chi tiết. Controller chọn View chi tiết nếu có dữ liệu và chọn trang 404 nếu không có. Quy tắc “đơn hàng đã giao không được hủy” vẫn phải nằm trong nghiệp vụ; View chỉ quyết định có hiển thị nút hủy theo khả năng đã được xác định hay không.

Kiểm thử nên xác nhận Controller ánh xạ kết quả đúng, đồng thời có kiểm thử riêng cho Service để bảo đảm quy tắc nghiệp vụ không bị đặt nhầm vào template.

## 3. Kiểm thử ViewModel và mapper

Mapper thường chuyển projection hoặc dữ liệu nghiệp vụ thành cấu trúc dành cho giao diện. Đây là nơi phù hợp cho unit test vì có thể kiểm tra đầu vào và đầu ra mà không cần khởi động Spring MVC.

### 3.1. Kiểm tra ánh xạ trường

Ví dụ mapper đơn giản:

~~~java
public class OrderViewMapper {

    public OrderDetailView toDetailView(OrderDetailProjection source) {
        return new OrderDetailView(
            source.orderNumber(),
            source.customerName(),
            statusLabel(source.status()),
            source.createdAtText(),
            source.totalText(),
            source.canCancel()
        );
    }

    private String statusLabel(OrderStatus status) {
        return switch (status) {
            case PENDING -> "Đang chờ";
            case PAID -> "Đã thanh toán";
            case SHIPPED -> "Đang giao";
            case CANCELLED -> "Đã hủy";
        };
    }
}
~~~

Bài kiểm thử nên xác nhận từng trường được ánh xạ đúng, đặc biệt các trường dễ nhầm như mã trạng thái, tên hiển thị và quyền hành động.

~~~java
@Test
void mapsOrderProjectionToDetailView() {
    OrderDetailProjection source = new OrderDetailProjection(
        "ORD-1001",
        "Nguyễn An",
        OrderStatus.PAID,
        "19/11/2026 15:30",
        "1.250.000 ₫",
        false
    );

    OrderDetailView actual = mapper.toDetailView(source);

    assertThat(actual).isEqualTo(new OrderDetailView(
        "ORD-1001",
        "Nguyễn An",
        "Đã thanh toán",
        "19/11/2026 15:30",
        "1.250.000 ₫",
        false
    ));
}
~~~

Đây là unit test cho hợp đồng ánh xạ. Nếu ViewModel dùng chuỗi đã định dạng, cần có kiểm thử riêng cho Locale và múi giờ thay vì chỉ kiểm tra rằng chuỗi không rỗng.

### 3.2. Kiểm thử Locale và múi giờ

Cùng một thời điểm có thể hiển thị khác nhau theo Locale và ZoneId. Ví dụ Instant lưu trong database có thể được trình bày theo giờ Việt Nam ở một màn hình và theo giờ UTC ở một API.

Mapper nên nhận Locale và múi giờ tường minh hoặc dùng một abstraction cung cấp ngữ cảnh đã xác định. Tránh phụ thuộc ngầm vào timezone mặc định của máy chạy test.

Ví dụ:

~~~java
public String formatCreatedAt(
        Instant instant,
        Locale locale,
        ZoneId zoneId) {

    DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM)
            .withLocale(locale);

    return instant.atZone(zoneId).format(formatter);
}
~~~

Khi kiểm thử:

- Chọn một Instant cố định, không dùng thời điểm hiện tại.
- Chọn Locale cụ thể như **vi-VN**.
- Chọn ZoneId cụ thể như **Asia/Ho_Chi_Minh**.
- Xác nhận ngày/giờ thuộc múi giờ mong muốn.
- Không để kết quả phụ thuộc timezone của máy developer hoặc CI.

Dữ liệu ngày giờ được định dạng có thể thay đổi nhẹ giữa phiên bản JDK do bộ dữ liệu Locale. Nếu hợp đồng yêu cầu chuỗi chính xác, hãy cố định môi trường và định dạng mẫu rõ ràng. Nếu chỉ cần hành vi, kiểm tra các thành phần quan trọng thay vì so sánh toàn bộ chuỗi theo một snapshot dễ vỡ.

### 3.3. Kiểm thử tiền tệ và số

Dữ liệu tiền nên giữ kiểu số chính xác và mã tiền tệ trong tầng nghiệp vụ. ViewModel mới chuyển thành chuỗi theo Locale.

Các trường hợp cần kiểm tra:

- Giá trị 0 và giá trị âm nếu nghiệp vụ cho phép.
- Giá trị lớn, có nhiều chữ số.
- Mã tiền tệ khác nhau.
- Locale dùng dấu phân cách thập phân khác nhau.
- Không chuyển tiền qua **double** nếu cần độ chính xác thập phân.

Không nên kiểm thử bằng cách so sánh một chuỗi định dạng duy nhất trong mọi JDK nếu định dạng không phải hợp đồng cố định. Với định dạng do sản phẩm quy định, kiểm thử chính xác chuỗi; với định dạng Locale mặc định, kiểm tra quy tắc và ký hiệu quan trọng.

### 3.4. Kiểm thử trạng thái rỗng và giá trị thiếu

ViewModel cần quy định rõ cách biểu diễn dữ liệu thiếu:

- Tên khách hàng không có: dùng nhãn phù hợp hoặc giá trị thay thế.
- Danh sách rỗng: giữ collection rỗng, không dùng **null**.
- Ảnh đại diện không có: dùng placeholder.
- Ngày chưa xác định: hiển thị trạng thái chưa có dữ liệu.
- Quyền thao tác không có: mặc định không cho phép.

Unit test nên xác nhận các trường hợp null/empty được xử lý theo hợp đồng. Đừng để template tự đoán mọi trường có thể null rồi phát sinh lỗi khi render.

## 4. Kiểm thử quyết định chọn View ở Controller

Controller nhận kết quả từ Service và chọn View logic. Đây là trách nhiệm quan trọng của MVC và có thể kiểm thử mà không cần render HTML thật.

### 4.1. Controller ví dụ

~~~java
@Controller
@RequestMapping("/orders")
public class OrderPageController {

    private final OrderQueryService queryService;

    public OrderPageController(OrderQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{id}")
    public ModelAndView detail(@PathVariable UUID id) {
        Optional<OrderDetailView> found = queryService.findDetail(id);

        if (found.isEmpty()) {
            ModelAndView missing = new ModelAndView("errors/404");
            missing.setStatus(HttpStatus.NOT_FOUND);
            return missing;
        }

        ModelAndView page = new ModelAndView("orders/detail");
        page.addObject("order", found.get());
        return page;
    }
}
~~~

Controller không tự truy vấn database hoặc tự xây HTML. Nó gọi Service, sau đó quyết định View và dữ liệu trình bày.

### 4.2. Kiểm thử nhánh tìm thấy tài nguyên

Với JUnit 5, Mockito và MockMvc standalone:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderPageControllerTest {

    @Mock
    private OrderQueryService queryService;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        OrderPageController controller =
            new OrderPageController(queryService);

        mockMvc = MockMvcBuilders
            .standaloneSetup(controller)
            .build();
    }

    @Test
    void choosesDetailViewWhenOrderExists() throws Exception {
        UUID id = UUID.fromString(
            "b5e1b9d0-71c5-4c77-9c10-6f8d7a4c0001"
        );

        OrderDetailView expected = new OrderDetailView(
            "ORD-1001",
            "Nguyễn An",
            "Đã thanh toán",
            "19/11/2026 15:30",
            "1.250.000 ₫",
            false
        );

        when(queryService.findDetail(id))
            .thenReturn(Optional.of(expected));

        mockMvc.perform(get("/orders/{id}", id))
            .andExpect(status().isOk())
            .andExpect(view().name("orders/detail"))
            .andExpect(model().attribute("order", expected));

        verify(queryService).findDetail(id);
    }
}
~~~

Bài kiểm thử xác nhận ba điều: route được gọi đúng, Controller chọn tên View mong đợi và Model chứa ViewModel đúng. Nó không kiểm tra template có tồn tại hay HTML có được render thành công hay không.

### 4.3. Kiểm thử nhánh không tìm thấy

~~~java
@Test
void choosesNotFoundViewWhenOrderDoesNotExist() throws Exception {
    UUID id = UUID.fromString(
        "b5e1b9d0-71c5-4c77-9c10-6f8d7a4c0002"
    );

    when(queryService.findDetail(id)).thenReturn(Optional.empty());

    mockMvc.perform(get("/orders/{id}", id))
        .andExpect(status().isNotFound())
        .andExpect(view().name("errors/404"))
        .andExpect(model().attributeDoesNotExist("order"));

    verify(queryService).findDetail(id);
}
~~~

Kiểm thử này bảo đảm tài nguyên không tồn tại không vô tình trả View chi tiết với Model rỗng. Nó cũng xác nhận status code đúng với nội dung trang lỗi.

### 4.4. Kiểm thử các nhánh chọn View khác

Một Controller có thể có nhiều kết quả:

- Trang danh sách khi truy vấn thành công.
- Trang chi tiết khi tìm thấy bản ghi.
- Trang 404 khi không tìm thấy.
- Trang 403 khi chính sách yêu cầu hiển thị trang cấm truy cập.
- Trả lại form khi validation thất bại.
- Redirect sau khi thao tác ghi thành công.

Nên viết test riêng cho mỗi nhánh có ý nghĩa. Không cần kiểm tra mọi tổ hợp tham số nếu chúng không làm thay đổi quyết định View; hãy tập trung vào các điều kiện làm thay đổi phản hồi.

## 5. Kiểm thử Model được đưa vào View

Tên View đúng nhưng Model sai vẫn tạo ra trang lỗi hoặc hiển thị dữ liệu không chính xác. Cần kiểm tra:

- Tên thuộc tính trong Model.
- Kiểu dữ liệu của thuộc tính.
- Giá trị của từng trường.
- Collection rỗng và metadata phân trang.
- Cờ quyền hiển thị hành động.
- Không có Entity hoặc trường nhạy cảm không được phép xuất hiện.

### 5.1. Kiểm tra thuộc tính bắt buộc

Với MockMvc, có thể kiểm tra thuộc tính Model:

~~~java
mockMvc.perform(get("/orders/{id}", id))
    .andExpect(status().isOk())
    .andExpect(model().attributeExists("order"))
    .andExpect(model().attribute("order", expectedView));
~~~

Nếu View cần nhiều thuộc tính độc lập như **pageTitle**, **breadcrumbs** và **canEdit**, hãy xác nhận các thuộc tính đó tồn tại và có giá trị đúng. Tránh kiểm tra quá nhiều chi tiết nội bộ không thuộc hợp đồng View.

### 5.2. Kiểm tra dữ liệu không bị lộ

Có thể xác nhận Model chỉ chứa ViewModel đã chọn lọc:

~~~java
mockMvc.perform(get("/orders/{id}", id))
    .andExpect(model().attribute(
        "order",
        instanceOf(OrderDetailView.class)
    ))
    .andExpect(model().attributeDoesNotExist(
        "entity",
        "paymentToken",
        "internalNote"
    ));
~~~

Trong thực tế, các trường nhạy cảm có thể nằm bên trong một object. Kiểm tra kiểu ViewModel và các trường công khai của nó; không chỉ kiểm tra tên thuộc tính cấp cao nhất.

Không nên đưa Entity vào Model rồi trông chờ template không hiển thị trường nhạy cảm. Dữ liệu không cần cho View không nên được truyền tới View.

### 5.3. Kiểm tra dữ liệu phân trang

Với trang danh sách, kiểm thử:

- **items** có đúng số phần tử.
- **number** và **size** phản ánh trang đã chuẩn hóa.
- **totalElements** và **totalPages** đúng theo hợp đồng.
- **hasNext**/**hasPrevious** nhất quán.
- Link điều hướng giữ filter và sort.
- Danh sách rỗng có metadata hợp lệ.

Đừng chỉ kiểm tra rằng thuộc tính **orders** tồn tại. Một trang có thể render nhưng vẫn hiển thị sai số trang hoặc link dẫn tới bộ lọc khác.

## 6. Kiểm thử form, validation và redirect

Form có những quyết định View riêng. Khi dữ liệu không hợp lệ, ứng dụng thường trả lại View biểu mẫu cùng lỗi. Khi thành công, ứng dụng thường dùng Post/Redirect/Get.

### 6.1. Validation thất bại trả lại form

Ví dụ Controller:

~~~java
@PostMapping
public String create(
        @Valid @ModelAttribute("form") CreateOrderForm form,
        BindingResult bindingResult,
        Model model) {

    if (bindingResult.hasErrors()) {
        return "orders/new";
    }

    orderCommandService.create(form);
    return "redirect:/orders";
}
~~~

Bài kiểm thử cần xác nhận:

- View trả lại là **orders/new**.
- Model có form và BindingResult.
- Thông báo lỗi gắn đúng trường.
- Giá trị người dùng đã nhập được giữ lại theo chính sách.
- Service ghi dữ liệu không được gọi khi validation thất bại.

Ví dụ:

~~~java
mockMvc.perform(post("/orders")
        .param("customerEmail", "not-an-email")
        .param("quantity", "0"))
    .andExpect(status().isOk())
    .andExpect(view().name("orders/new"))
    .andExpect(model().attributeHasFieldErrors(
        "form", "customerEmail", "quantity"
    ));

verify(orderCommandService, never()).create(any());
~~~

Đoạn mã giả định form có validation constraint tương ứng và controller được cấu hình để bind lỗi. Test phải dùng đúng tên trường và quy tắc thực tế của ứng dụng.

### 6.2. Thành công dùng redirect

Khi POST thành công, kiểm thử URL redirect và status:

~~~java
mockMvc.perform(post("/orders")
        .param("customerEmail", "an@example.test")
        .param("quantity", "2"))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/orders"));
~~~

Nếu dùng flash message, kiểm tra flash attribute được đưa vào redirect. Không nên chỉ xác nhận Controller trả chuỗi bắt đầu bằng **redirect:** nếu hành vi HTTP là điều người dùng thực sự nhận.

### 6.3. Phân biệt View lỗi với lỗi kỹ thuật

Validation thất bại có thể trả form với status 200 trong một số ứng dụng SSR, còn lỗi tài nguyên không tồn tại thường cần status 404. Cần xác định rõ status code theo hợp đồng của sản phẩm. Không dùng cùng một View lỗi chung cho mọi trường hợp nếu giao diện cần hướng dẫn người dùng khác nhau.

## 7. Kiểm thử template và HTML được render thực tế

Kiểm thử tên View chưa chứng minh ViewResolver tìm được template hoặc template engine kết xuất thành công. Cần một lớp kiểm thử tích hợp sử dụng cấu hình MVC và template engine thật.

### 7.1. MockMvc standalone và kiểm thử tích hợp khác nhau

| Cách kiểm thử | Có thể xác nhận | Không tự xác nhận |
|---|---|---|
| Gọi trực tiếp Controller | Giá trị trả về và Model | Route, filter, resolver |
| MockMvc standaloneSetup | Mapping, status, tên View, Model | Cấu hình ViewResolver/template engine thực tế |
| MockMvc với ApplicationContext | MVC config, ViewResolver và nhiều thành phần tích hợp | Hành vi đầy đủ của trình duyệt |
| Browser/E2E test | HTML hiển thị, CSS/JS và điều hướng thực tế | Mọi nhánh nghiệp vụ nội bộ |

Dùng unit test và standalone MockMvc cho các nhánh Controller nhanh, dễ cô lập. Dùng integration test để xác nhận template thật được tìm thấy và render. Dùng E2E cho những hành trình quan trọng mà DOM và hành vi trình duyệt ảnh hưởng kết quả.

### 7.2. Ví dụ kiểm thử HTML với cấu hình ứng dụng

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderPageRenderingTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void rendersOrderDetailHtml() throws Exception {
        UUID existingOrderId = TestOrderFixtures.PAID_ORDER_ID;

        mockMvc.perform(get("/orders/{id}", existingOrderId))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_HTML
            ))
            .andExpect(content().string(
                containsString("ORD-1001")
            ))
            .andExpect(content().string(
                containsString("Đã thanh toán")
            ));
    }
}
~~~

Test cần có dữ liệu fixture trong test database hoặc một nguồn dữ liệu tích hợp đã được chuẩn bị. Không phụ thuộc vào dữ liệu của môi trường phát triển hoặc production.

### 7.3. Kiểm tra nội dung quan trọng, tránh snapshot quá mong manh

Có thể kiểm tra:

- Tiêu đề trang và mã tài nguyên.
- Trạng thái và thông tin chính.
- Link điều hướng có URL đúng.
- Trạng thái rỗng hoặc thông báo lỗi.
- Các trường không được phép không xuất hiện.
- HTML có cấu trúc và thuộc tính truy cập cần thiết.

Tránh so sánh toàn bộ HTML theo một chuỗi dài nếu thứ tự thuộc tính, khoảng trắng hoặc markup có thể thay đổi mà không ảnh hưởng trải nghiệm. Snapshot hữu ích cho một số giao diện phức tạp, nhưng cần được rà soát có chủ đích khi cập nhật.

### 7.4. Kiểm tra escaping và XSS

Template phải escape dữ liệu động theo ngữ cảnh. Với Thymeleaf, **th:text** escape văn bản theo mặc định; **th:utext** cho phép chèn nội dung HTML và cần được dùng rất thận trọng.

Giả sử tên khách hàng chứa:

~~~text
<script>alert(1)</script>
~~~

Khi render dưới dạng văn bản, HTML phải biểu diễn các dấu ngoặc theo dạng đã escape, không thực thi script. Integration test nên xác nhận payload xuất hiện như văn bản hoặc không được chèn vào markup thực thi.

Không nên chỉ kiểm tra HttpOnly hay CSP rồi bỏ qua escaping trong template. Những biện pháp đó bổ sung cho nhau.

## 8. Kiểm thử ViewResolver và cấu hình template

ViewResolver ánh xạ tên View logic sang tài nguyên trình bày. Lỗi prefix, suffix, thứ tự resolver hoặc tên template có thể chỉ xuất hiện khi render thật.

Các trường hợp cần kiểm tra:

- **orders/detail** tìm đúng template chi tiết.
- **orders/list** tìm đúng template danh sách.
- View lỗi 404/403 có template tương ứng.
- Fragment dùng chung được tìm thấy.
- Layout được áp dụng đúng.
- Template thiếu hoặc lỗi cú pháp được phát hiện trong kiểm thử tích hợp.
- Không có resolver ưu tiên sai khiến một tên View được xử lý bởi công nghệ khác.

Nếu ứng dụng có nhiều ViewResolver, cần kiểm thử các tên View thuộc từng resolver và thứ tự ưu tiên. Đừng chỉ kiểm tra một template đại diện rồi giả định toàn bộ resolver đều đúng.

Một cách tổ chức tốt là giữ tên View logic ổn định, cấu hình prefix/suffix tập trung và tránh tạo tên View động từ dữ liệu người dùng. Không cho client gửi trực tiếp tên template để Controller phân giải; điều đó có thể dẫn đến truy cập View ngoài dự kiến.

## 9. Kiểm thử quyết định HTML, JSON và redirect

Một số ứng dụng cung cấp cả HTML và JSON. Cần xác định rõ endpoint nào trả View và endpoint nào trả dữ liệu qua message converter.

Ví dụ:

- **GET /orders/42** trả HTML cho trang chi tiết.
- **GET /api/orders/42** trả JSON cho client.
- **POST /orders** thành công redirect về trang danh sách.
- **POST /api/orders** trả JSON hoặc status theo hợp đồng API.

Kiểm thử cần xác nhận status, Content-Type và nội dung phản hồi. Không mặc định mọi handler đều đi qua ViewResolver.

Nếu dùng content negotiation theo header **Accept**, hãy kiểm thử các giá trị được hỗ trợ và phản hồi khi không có representation phù hợp. Với Spring MVC, handler trả tên View và handler dùng **@ResponseBody** có đường xử lý khác nhau; cần kiểm tra đúng cấu hình thực tế.

Không nên chọn View dựa trên chuỗi **Accept** tự phân tích thủ công trong từng Controller. Dùng cơ chế content negotiation của framework hoặc tách endpoint rõ ràng để hợp đồng dễ hiểu.

## 10. Kiểm thử phân quyền ảnh hưởng đến dữ liệu trình bày

Một View có thể hiển thị hoặc ẩn nút theo quyền. Tuy nhiên, việc ẩn nút chỉ là quyết định trình bày, không phải kiểm soát truy cập.

Ví dụ ViewModel có trường:

~~~java
public record OrderDetailView(
    String orderNumber,
    String statusLabel,
    boolean canCancel
) {}
~~~

Test cần xác nhận **canCancel** đúng với quyền và trạng thái. Nhưng phải có test riêng để xác nhận request hủy đơn bị từ chối ở Service hoặc security layer khi người dùng không có quyền, kể cả khi tự gửi request.

Các tình huống nên kiểm thử:

- Người dùng có quyền xem: nhận đúng dữ liệu được phép.
- Người dùng không có quyền: không nhận ViewModel chứa dữ liệu riêng tư.
- Người dùng có quyền xem nhưng không có quyền hủy: trang hiển thị chi tiết nhưng không hiển thị nút hủy.
- Request hủy gửi trực tiếp vẫn bị từ chối nếu không đủ quyền.
- Không để dữ liệu của tenant khác xuất hiện trong Model hoặc HTML.

## 11. Kiểm thử lỗi và trạng thái giao diện

Một View tốt phải xử lý trạng thái không thành công rõ ràng. Cần kiểm thử cả status HTTP và nội dung trình bày.

| Trường hợp | Status/điều hướng | Nội dung cần xác nhận |
|---|---|---|
| Không tìm thấy | 404 | Trang không tìm thấy, không có dữ liệu chi tiết |
| Không đủ quyền | 403 hoặc 404 theo chính sách | Không tiết lộ tài nguyên |
| Validation lỗi | Trả lại form | Lỗi đúng trường và giữ dữ liệu hợp lệ |
| Xung đột phiên bản | 409/412 hoặc trang xung đột | Hướng dẫn tải lại/giải quyết |
| Lỗi hệ thống | 500/503 | Thông báo chung, không lộ stack trace |
| Danh sách rỗng | 200 | Trạng thái rỗng và hướng dẫn phù hợp |
| Session hết hạn | 401 hoặc redirect login | Thông báo hoặc luồng đăng nhập rõ |

Không dùng status 200 cho mọi lỗi chỉ vì có một trang HTML để hiển thị. Status code là một phần hợp đồng với browser, crawler, proxy và client tự động.

## 12. Kiểm thử View có thể truy cập và dễ sử dụng

Kiểm thử dữ liệu và tên View vẫn chưa đủ để xác nhận giao diện dễ sử dụng. Với các trang quan trọng, cần kiểm tra cấu trúc và hành vi:

- Mỗi trang có tiêu đề chính dễ nhận biết.
- Form có label gắn với input.
- Lỗi validation được liên kết với trường tương ứng.
- Trạng thái hiện tại được thể hiện bằng văn bản, không chỉ bằng màu.
- Link và nút có tên dễ hiểu.
- Bảng có header phù hợp.
- Thành phần điều hướng có nhãn.
- Thông báo cập nhật dùng vùng live phù hợp khi cần.
- Nội dung vẫn đọc được khi phóng to hoặc dùng bàn phím.

Có thể kiểm tra một số thuộc tính DOM bằng browser automation. Không nên viết assertion chỉ dựa vào class CSS nội bộ nếu mục tiêu là xác nhận hành vi người dùng.

## 13. Ma trận kiểm thử tổng hợp

| Tầng | Mục tiêu | Công cụ/cách làm |
|---|---|---|
| Mapper/ViewModel | Ánh xạ, định dạng, null/empty, quyền hiển thị | JUnit, AssertJ |
| Controller | Route, Model, tên View, status, redirect | MockMvc standalone |
| Security boundary | Quyền truy cập và không rò dữ liệu | Spring Security Test |
| ViewResolver/template | Template tồn tại, fragment/layout render | MockMvc với ApplicationContext |
| HTML output | Nội dung, escaping, link, trạng thái | MockMvc integration |
| Browser | DOM, điều hướng, responsive, bàn phím | Browser automation/E2E |

Một bộ kiểm thử hiệu quả không cần kiểm tra cùng một điều ở mọi tầng. Mapper test xác nhận ánh xạ; Controller test xác nhận lựa chọn View; integration test xác nhận template; E2E test xác nhận hành trình người dùng.

### 13.1. Ma trận tình huống tối thiểu

| Tình huống | Dữ liệu Model | View/Response | Kiểm tra bổ sung |
|---|---|---|---|
| Chi tiết tồn tại | OrderDetailView hợp lệ | **orders/detail** | HTML render đúng |
| Chi tiết không tồn tại | Không có order | **errors/404**, 404 | Không lộ dữ liệu |
| Danh sách có dữ liệu | Items và metadata | **orders/list** | Link phân trang |
| Danh sách rỗng | Items rỗng | **orders/list** | Empty state |
| Form không hợp lệ | Form và BindingResult | **orders/new** | Lỗi theo trường |
| Form hợp lệ | Không cần Model form cũ | Redirect | PRG và flash message |
| Không có quyền | Không đưa dữ liệu riêng tư | 403/404 | Direct request bị chặn |
| Nội dung chứa HTML độc hại | ViewModel có text không tin cậy | View tương ứng | Output được escape |

## 14. Những lỗi kiểm thử thường gặp

### Chỉ kiểm tra Service được gọi

Test xác nhận Service được gọi chưa chứng minh Controller chọn đúng View, status hoặc Model. Hãy kiểm tra kết quả HTTP và view name.

### Chỉ kiểm tra tên View

Tên View đúng chưa chứng minh template tồn tại hoặc render được. Bổ sung integration test với ViewResolver và template engine thật.

### Kiểm tra HTML quá chi tiết

So sánh toàn bộ HTML có thể làm test hỏng vì thay đổi khoảng trắng hoặc markup không ảnh hưởng hành vi. Ưu tiên kiểm tra nội dung và cấu trúc có ý nghĩa.

### Dùng Entity làm dữ liệu kiểm thử trình bày

Test phụ thuộc vào Entity lớn và quan hệ persistence khiến việc thiết lập fixture phức tạp. Dùng projection/ViewModel hoặc fixture builder phù hợp với tầng đang kiểm thử.

### Bỏ qua Locale và múi giờ

Test chạy trên máy có timezone khác có thể cho kết quả khác. Đặt Locale và ZoneId tường minh, dùng thời điểm cố định.

### Chỉ kiểm tra nút đã bị ẩn

Nút ẩn không chứng minh request được bảo vệ. Cần test authorization ở server cho chính endpoint thực hiện hành động.

### Không kiểm tra dữ liệu nhạy cảm

Trang có thể hiển thị đúng thông tin cần nhưng đồng thời đưa thêm trường nội bộ vào Model hoặc HTML. Kiểm tra ViewModel và response để xác nhận dữ liệu được giới hạn.

### Mock toàn bộ MVC trong integration test

Nếu mock ViewResolver hoặc template engine, test không thể phát hiện lỗi template thực tế. Chỉ mock những dependency ngoài phạm vi; giữ cấu hình trình bày thật ở bài kiểm thử render.

## 15. Quy trình thiết kế bộ kiểm thử

1. Xác định ViewModel hoặc DTO mà màn hình cần.
2. Liệt kê các nhánh kết quả làm thay đổi View, status hoặc redirect.
3. Viết unit test cho mapper và quy tắc định dạng.
4. Viết Controller test để xác nhận tên View và thuộc tính Model.
5. Kiểm thử validation, lỗi và redirect theo hợp đồng HTTP.
6. Chạy integration test với ViewResolver và template engine thật.
7. Kiểm tra escaping, dữ liệu nhạy cảm và quyền truy cập.
8. Dùng E2E cho các hành trình giao diện quan trọng.
9. Khi template hoặc ViewModel thay đổi, cập nhật đúng lớp test liên quan.
10. Giữ test tập trung vào hợp đồng người dùng nhìn thấy, tránh phụ thuộc chi tiết triển khai không cần thiết.

## Kết luận

Kiểm thử dữ liệu trình bày và quyết định chọn View cần bao phủ cả dữ liệu được truyền sang giao diện lẫn phản hồi mà Controller lựa chọn. Unit test cho mapper xác nhận ViewModel đúng; MockMvc xác nhận route, Model, status và tên View; integration test xác nhận ViewResolver cùng template engine render HTML thật; E2E kiểm tra hành trình người dùng. Khi kiểm thử đúng ranh giới, ứng dụng MVC tránh hiển thị sai dữ liệu, chọn nhầm trang, làm lộ thông tin hoặc chỉ phát hiện lỗi template khi đã triển khai.

