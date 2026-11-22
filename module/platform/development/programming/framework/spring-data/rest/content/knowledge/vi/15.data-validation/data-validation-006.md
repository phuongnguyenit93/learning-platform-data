# Validation cho tạo mới, cập nhật và thay đổi liên kết

## Mục tiêu

Spring Data REST cho phép kiểm tra dữ liệu trước khi repository lưu entity và trước khi thay đổi association. Validation cần được đặt ở phía server để mọi client đều phải tuân theo cùng quy tắc, bất kể request đến từ giao diện web, ứng dụng di động hay công cụ HTTP.

Có ba luồng cần xử lý riêng:

- **Tạo mới:** kiểm tra entity trước khi lưu qua `POST`.
- **Cập nhật:** kiểm tra trạng thái entity trước khi lưu qua `PUT` hoặc `PATCH`.
- **Thay đổi liên kết:** kiểm tra cả resource nguồn và resource đích trước khi thêm, thay thế hoặc gỡ association.

## Các lớp validation

Nên phân biệt bốn nhóm kiểm tra:

1. **Cấu trúc request:** JSON hợp lệ, kiểu dữ liệu đúng, URI association có cú pháp hợp lệ và resource đích tồn tại.
2. **Ràng buộc trên thuộc tính:** trường bắt buộc, độ dài, định dạng, miền giá trị hoặc số lượng.
3. **Quy tắc nghiệp vụ:** ngày kết thúc phải sau ngày bắt đầu, mã đơn hàng phải duy nhất, trạng thái hiện tại có cho phép chuyển sang trạng thái mới hay không.
4. **Quy tắc quan hệ:** hai resource có được phép liên kết hay không, có thuộc cùng tenant không, giới hạn số liên kết, hoặc resource đích có đang ở trạng thái cho phép hay không.

Không nên dựa vào validation ở giao diện để bảo vệ dữ liệu. Client có thể bỏ qua giao diện và gọi trực tiếp REST endpoint.

## Validation khi tạo mới

Khi client gửi `POST` đến collection resource, Spring Data REST phát sự kiện `beforeCreate` trước khi entity mới được lưu. Đây là vị trí phù hợp để kiểm tra các điều kiện chỉ áp dụng lúc tạo, chẳng hạn mã bắt buộc, trạng thái khởi tạo hợp lệ hoặc quy tắc không được tạo trùng.

Ví dụ entity `Order` dùng Bean Validation:

    import jakarta.validation.Valid;
    import jakarta.validation.constraints.NotBlank;
    import jakarta.validation.constraints.NotEmpty;
    import jakarta.validation.constraints.Positive;
    import jakarta.validation.constraints.Size;

    public class Order {
        @NotBlank
        @Size(max = 40)
        private String orderNumber;

        @NotEmpty
        @Valid
        private List<OrderLine> lines;

        @Positive
        private BigDecimal total;

        // getters and setters
    }

`@NotBlank` yêu cầu chuỗi có nội dung; `@Size` giới hạn độ dài; `@NotEmpty` yêu cầu collection không rỗng; `@Positive` yêu cầu số dương; `@Valid` yêu cầu kiểm tra tiếp các phần tử lồng nhau. Với Spring Boot 2 hoặc stack cũ dùng `javax.validation`; ví dụ trên dùng namespace `jakarta.validation` của các phiên bản mới.

Để dùng các annotation này, ứng dụng cần có Bean Validation provider, thường được thêm qua dependency `spring-boot-starter-validation`. Cần bảo đảm validator thực sự được gọi trong luồng lưu của Spring Data REST; chỉ thêm annotation vào entity không thay thế việc cấu hình validator cho repository events.

## Đăng ký validator theo tên bean

Spring Data REST hỗ trợ gắn một Spring `Validator` vào event bằng quy ước tên bean. Tên bắt đầu bằng event, tiếp theo là tên đơn giản của domain type và hậu tố `Validator`.

Ví dụ validator chỉ chạy trước khi tạo `Order`:

    import org.springframework.stereotype.Component;
    import org.springframework.validation.Errors;
    import org.springframework.validation.Validator;

    @Component("beforeCreateOrderValidator")
    public class BeforeCreateOrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Order.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Order order = (Order) target;
            if (order.getLines() == null || order.getLines().isEmpty()) {
                errors.rejectValue(
                    "lines",
                    "order.lines.required",
                    "An order must contain at least one line.");
            }
        }
    }

Spring Data REST nhận ra tiền tố `beforeCreate` và gắn validator này vào sự kiện tạo mới. Tên `Order` trong bean name phải khớp domain type mà validator hỗ trợ.

Nếu muốn dùng Bean Validation provider thông qua Spring Validator, có thể đăng ký `LocalValidatorFactoryBean` với tên event tương ứng. Ví dụ cấu hình hai validator cho cả tạo mới và cập nhật:

    @Configuration
    public class OrderValidationConfiguration {

        @Bean("beforeCreateOrderValidator")
        LocalValidatorFactoryBean validateOrderOnCreate() {
            return new LocalValidatorFactoryBean();
        }

        @Bean("beforeSaveOrderValidator")
        LocalValidatorFactoryBean validateOrderOnSave() {
            return new LocalValidatorFactoryBean();
        }
    }

Các validator được gọi theo event bean name; vì vậy hãy kiểm tra ứng dụng có provider và cấu hình phù hợp với phiên bản Spring đang dùng. Nếu cần quy tắc nghiệp vụ riêng, có thể viết Spring `Validator` tùy chỉnh như ví dụ trên hoặc kết hợp với Bean Validation.

## Validation khi cập nhật

Khi client cập nhật item resource bằng `PUT` hoặc `PATCH`, Spring Data REST phát sự kiện `beforeSave` trước khi lưu entity. Đăng ký validator theo tên `beforeSaveOrderValidator` để kiểm tra trạng thái chuẩn bị được lưu.

Ví dụ:

    @Component("beforeSaveOrderValidator")
    public class BeforeSaveOrderValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Order.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Order order = (Order) target;
            if (order.getStatus() == OrderStatus.SHIPPED
                    && order.getShippingAddress() == null) {
                errors.rejectValue(
                    "shippingAddress",
                    "order.shippingAddress.required",
                    "A shipping address is required before shipping.");
            }
        }
    }

Điều kiện trong ví dụ là quy tắc nghiệp vụ phụ thuộc trạng thái. Nó được kiểm tra khi entity sắp được lưu, vì vậy có thể áp dụng cho cả request thay đổi một thuộc tính và request thay thế representation.

Với `PATCH`, payload thường chỉ chứa các trường muốn thay đổi. Hãy kiểm tra trạng thái entity sau khi thay đổi đã được áp dụng, không yêu cầu mọi trường phải xuất hiện trong JSON patch. Ví dụ client chỉ cập nhật `status`; validator vẫn có thể kiểm tra `shippingAddress` đang có trên entity. Với `PUT`, các trường bị bỏ khỏi representation có thể được xử lý như giá trị bị thay thế tùy cách binding; các ràng buộc bắt buộc cần phản ánh đúng hợp đồng PUT của API.

Không dùng cùng một quy tắc cho create và update một cách máy móc. Một trường có thể bắt buộc khi tạo nhưng bất biến khi cập nhật; một trạng thái có thể hợp lệ lúc khởi tạo nhưng không được phép quay lại sau khi đơn hàng đã giao.

## Validation khi thay đổi association

Thay đổi association có vòng đời riêng. Spring Data REST phát sự kiện `beforeLinkSave` khi liên kết resource nguồn với resource đích. Sự kiện cung cấp cả hai đối tượng: parent và linked object. Đây là nơi phù hợp để kiểm tra quy tắc liên quan đến cặp resource, ví dụ đơn hàng và khách hàng có cùng tenant hay khách hàng có đang hoạt động hay không.

Ví dụ dùng repository event handler:

    import org.springframework.data.rest.core.annotation.HandleBeforeLinkSave;
    import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
    import org.springframework.stereotype.Component;
    import org.springframework.web.server.ResponseStatusException;
    import org.springframework.http.HttpStatus;

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderAssociationHandler {

        @HandleBeforeLinkSave
        public void validateCustomerLink(Order order, Customer customer) {
            if (!order.getTenantId().equals(customer.getTenantId())) {
                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Order and customer must belong to the same tenant.");
            }

            if (!customer.isActive()) {
                throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "An inactive customer cannot be linked to an order.");
            }
        }
    }

Tham số đầu là resource nguồn (`Order`); tham số tiếp theo là resource được liên kết (`Customer`). Loại domain ở tham số đầu giúp Spring Data REST chọn handler tương ứng. Hãy dùng URI association mà API công bố và kiểm tra chính đối tượng đã được phân giải từ URI.

Với thao tác gỡ liên kết, các phiên bản Spring Data REST hiện hành cũng có event `beforeLinkDelete` và annotation `@HandleBeforeLinkDelete`. Có thể áp dụng quy tắc như không cho gỡ khách hàng khỏi đơn hàng đã khóa hoặc không cho bỏ liên kết bắt buộc. Kiểm tra event/annotation có trong phiên bản dependency của ứng dụng trước khi sử dụng vì API event có thể khác giữa các phiên bản.

## Đăng ký validator thủ công

Nếu không muốn dùng quy ước bean name, có thể đăng ký validator trực tiếp thông qua `RepositoryRestConfigurer`:

    @Configuration
    public class RepositoryValidationConfiguration
            implements RepositoryRestConfigurer {

        private final Validator orderCreateValidator;
        private final Validator orderSaveValidator;

        public RepositoryValidationConfiguration(
                @Qualifier("orderCreateValidator") Validator createValidator,
                @Qualifier("orderSaveValidator") Validator saveValidator) {
            this.orderCreateValidator = createValidator;
            this.orderSaveValidator = saveValidator;
        }

        @Override
        public void configureValidatingRepositoryEventListener(
                ValidatingRepositoryEventListener listener) {
            listener.addValidator("beforeCreate", orderCreateValidator);
            listener.addValidator("beforeSave", orderSaveValidator);
        }
    }

Đây là lựa chọn thay thế cho bean name prefix. Không đăng ký cùng một validator nhiều lần qua cả hai cách nếu không muốn logic validation chạy lặp.

## Xử lý lỗi validation

Khi validator phát hiện lỗi, hãy thêm lỗi vào `Errors` bằng `reject` hoặc `rejectValue`. Spring Data REST sẽ dừng thao tác lưu khi validation thất bại và trả error response cho client. Client nên đọc chi tiết lỗi để biết trường hoặc quy tắc nào không đạt.

Ví dụ lỗi ở trường `lines` có thể chỉ ra:

    {
      "errors": [
        {
          "entity": "Order",
          "property": "lines",
          "message": "An order must contain at least one line."
        }
      ]
    }

Cấu trúc response cụ thể phụ thuộc phiên bản Spring Data REST và cấu hình xử lý exception. Hãy kiểm tra status code và body thực tế trong integration test; không để client phụ thuộc vào một thông báo lỗi cố định nếu API chưa cam kết schema lỗi.

Phân biệt validation error với các lỗi khác:

- Dữ liệu sai định dạng hoặc vi phạm quy tắc nghiệp vụ thường được trả như lỗi client (4xx).
- URI association không tồn tại có thể trả `404 Not Found`.
- Vi phạm khóa duy nhất hoặc xung đột dữ liệu có thể phát sinh lỗi database hoặc conflict; cần ánh xạ rõ ràng ở tầng API.
- Lỗi hệ thống như database không sẵn sàng không nên bị chuyển thành thông báo validation chung.

Thông báo cho client nên nêu trường và quy tắc có thể sửa, nhưng không tiết lộ SQL, tên bảng nội bộ, stack trace hoặc dữ liệu nhạy cảm.

## Validation không thay thế database constraint và authorization

Validation ở tầng ứng dụng giúp trả lỗi thân thiện, nhưng không phải lớp bảo vệ duy nhất:

- Dùng `NOT NULL`, `UNIQUE`, foreign key và các constraint phù hợp trong database để bảo vệ tính toàn vẹn dữ liệu.
- Kiểm tra uniqueness trong validator có thể gặp race condition nếu hai request đồng thời cùng kiểm tra trước khi lưu. Database unique constraint vẫn cần thiết; xử lý exception khi commit để trả lỗi conflict phù hợp.
- Dùng Spring Security và authorization để xác định ai được tạo, sửa hoặc liên kết resource. Một association hợp lệ về nghiệp vụ vẫn có thể bị cấm với người gọi không đủ quyền.
- Thực hiện kiểm tra tenant hoặc quyền sở hữu ở server dựa trên danh tính đã xác thực, không tin tenant ID do client tự gửi.
- Đặt logic nghiệp vụ quan trọng trong service/domain layer để các luồng REST khác và các luồng gọi repository nội bộ có thể dùng chung.

## Kiểm tra bằng integration test

Kiểm tra cả ba luồng qua HTTP, không chỉ gọi trực tiếp phương thức validator:

1. `POST` entity thiếu trường bắt buộc: request bị từ chối và không có entity mới được lưu.
2. `POST` entity hợp lệ: nhận response thành công và dữ liệu được lưu.
3. `PUT` hoặc `PATCH` tạo trạng thái không hợp lệ: request bị từ chối và dữ liệu cũ vẫn được giữ.
4. `PATCH` chỉ thay một trường: các trường khác vẫn giữ giá trị và validation chạy trên trạng thái sau cập nhật.
5. Thay association bằng URI hợp lệ nhưng vi phạm quy tắc nghiệp vụ: handler từ chối và liên kết không thay đổi.
6. Thay association hợp lệ: liên kết được lưu và có thể đọc lại từ association resource.
7. Gỡ association bị cấm: handler từ chối và liên kết vẫn còn.
8. Gửi request với người dùng không có quyền: authorization từ chối dù dữ liệu vượt qua validation.

Ví dụ kiểm tra một request tạo mới không hợp lệ bằng MockMvc:

    mockMvc.perform(post("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "orderNumber": "",
                  "total": -10
                }
                """))
        .andExpect(status().is4xxClientError());

Điều chỉnh payload, media type và status mong đợi theo API thực tế. Ngoài status, hãy kiểm tra entity không được lưu, error response có chỉ ra lỗi phù hợp và request hợp lệ vẫn hoạt động.

## Quy trình áp dụng

1. Khai báo constraint cho dữ liệu đơn giản trên entity hoặc value object.
2. Đăng ký validator `beforeCreate<DomainType>` cho quy tắc khi tạo.
3. Đăng ký validator `beforeSave<DomainType>` cho trạng thái sau cập nhật.
4. Dùng `@HandleBeforeLinkSave` và khi cần `@HandleBeforeLinkDelete` để kiểm tra cặp resource khi thay đổi association.
5. Đưa quy tắc dùng chung vào service/domain layer; giữ authorization ở security layer.
6. Giữ constraint database cho tính toàn vẹn và xử lý xung đột khi lưu.
7. Viết integration test cho request hợp lệ, không hợp lệ, PATCH, link và unlink.

Validation của Spring Data REST nên chặn dữ liệu không hợp lệ ngay trước khi lưu hoặc thay đổi liên kết. `beforeCreate`, `beforeSave` và các link event cung cấp đúng điểm can thiệp cho ba luồng; database constraint và authorization tiếp tục bảo vệ tính toàn vẹn và quyền truy cập.