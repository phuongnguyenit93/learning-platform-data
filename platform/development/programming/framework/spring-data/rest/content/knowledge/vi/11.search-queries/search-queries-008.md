# Chuyển đổi enum, ngày giờ và kiểu tham số tùy chỉnh trong Spring Data REST

Các query method được Spring Data REST công bố nhận tham số từ query string của HTTP request. Giá trị trên URL ban đầu luôn là văn bản, trong khi phương thức repository có thể khai báo tham số kiểu enum, ngày giờ hoặc một value object của domain.

Spring Data REST dùng ConversionService để chuyển giá trị request sang kiểu Java mà query method yêu cầu trước khi gọi repository. Nhờ đó, client có thể gửi các giá trị dễ đọc trên URL mà không phải tự chuyển đổi chúng thành kiểu dữ liệu nội bộ.

## 1. Luồng chuyển đổi tham số tìm kiếm

Giả sử repository khai báo một phương thức tìm đơn hàng theo trạng thái và thời điểm tạo:

~~~java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @RestResource(path = "by-status-and-created-after",
                  rel = "byStatusAndCreatedAfter")
    List<Order> findByStatusAndCreatedAtAfter(
        @Param("status") OrderStatus status,
        @Param("createdAfter") OffsetDateTime createdAfter
    );
}
~~~

Client gọi search endpoint:

~~~http
GET /orders/search/by-status-and-created-after?status=PAID&createdAfter=2026-11-11T09%3A30%3A00%2B07%3A00
~~~

Spring Data REST lấy giá trị chuỗi của hai query parameter, chuyển chúng thành OrderStatus và OffsetDateTime, sau đó truyền các đối tượng đã chuyển đổi vào query method.

Có thể hình dung luồng xử lý như sau:

1. Client gửi request GET tới query method resource.
2. Spring Data REST đọc các query parameter và đối chiếu tên với tham số được khai báo bằng @Param.
3. ConversionService chuyển từng giá trị từ dạng request sang kiểu Java tương ứng.
4. Nếu chuyển đổi thành công, Spring Data thực thi query method với các tham số đã có kiểu.
5. Kết quả truy vấn được trả về dưới dạng REST resource theo cấu hình của ứng dụng.

Việc chuyển đổi tham số diễn ra trước khi query method được thực thi. Converter chỉ chịu trách nhiệm tạo giá trị Java phù hợp; nó không thay thế logic truy vấn hoặc quy tắc nghiệp vụ của repository.

## 2. Chuyển đổi tham số enum

Enum phù hợp với các thuộc tính có tập giá trị hữu hạn, ví dụ trạng thái đơn hàng:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Repository có thể nhận trực tiếp enum:

~~~java
List<Order> findByStatus(@Param("status") OrderStatus status);
~~~

Client gửi tên enum trên query string:

~~~http
GET /orders/search/findByStatus?status=PAID
~~~

Spring có converter mặc định để chuyển String thành enum. Với cách chuyển đổi enum thông thường, giá trị đầu vào phải khớp tên constant, bao gồm cả chữ hoa/chữ thường. Ví dụ PAID khớp OrderStatus.PAID, còn paid có thể không khớp.

Nếu muốn API chấp nhận chữ thường, alias hoặc tên thân thiện với người dùng, hãy đăng ký converter riêng. Ví dụ:

~~~java
public class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        String value = source.trim().toLowerCase(Locale.ROOT);

        return switch (value) {
            case "new" -> OrderStatus.NEW;
            case "paid", "payment-confirmed" -> OrderStatus.PAID;
            case "shipped" -> OrderStatus.SHIPPED;
            case "cancelled", "canceled" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unsupported order status: " + source
            );
        };
    }
}
~~~

Sau khi đăng ký converter, các giá trị như paid và payment-confirmed đều có thể được chuyển thành OrderStatus.PAID. Việc chấp nhận alias nào là quyết định của hợp đồng API; nên công bố rõ các giá trị được hỗ trợ và giữ chúng ổn định cho client.

### Enum translation và query parameter

Spring Data REST còn có tính năng enum translation thông qua resource bundle. Tính năng này phục vụ việc hiển thị enum dưới dạng văn bản thân thiện trong representation và xử lý giá trị enum đã được dịch.

Có thể bật tính năng qua cấu hình Spring Boot:

~~~yaml
spring:
  data:
    rest:
      enable-enum-translation: true
~~~

Enum translation và converter của query parameter là hai điểm cấu hình cần phân biệt. Nếu API tìm kiếm cần chấp nhận token riêng như payment-confirmed, hãy định nghĩa và kiểm thử converter cho query method. Không nên giả định rằng nhãn hiển thị trong giao diện luôn là giá trị phù hợp để gửi lên URL.

## 3. Chuyển đổi tham số ngày và giờ

Spring hỗ trợ chuyển chuỗi sang các kiểu ngày giờ của Java Time API. Nên ưu tiên định dạng ISO vì chúng có cấu trúc rõ ràng, dễ trao đổi giữa các hệ thống và tránh nhầm lẫn về thứ tự ngày/tháng.

| Kiểu Java | Ý nghĩa | Ví dụ đầu vào |
|---|---|---|
| LocalDate | Ngày lịch, không có giờ hoặc múi giờ | 2026-11-11 |
| LocalTime | Giờ trong ngày, không có ngày hoặc múi giờ | 09:30:00 |
| LocalDateTime | Ngày và giờ, không chứa múi giờ | 2026-11-11T09:30:00 |
| OffsetDateTime | Ngày giờ kèm độ lệch UTC | 2026-11-11T09:30:00+07:00 |
| Instant | Một thời điểm tuyệt đối trên dòng thời gian UTC | 2026-11-11T02:30:00Z |

Ví dụ repository tìm sự kiện từ một ngày:

~~~java
List<Event> findByEventDate(
    @Param("date") LocalDate date
);
~~~

Request:

~~~http
GET /events/search/findByEventDate?date=2026-11-11
~~~

Ví dụ tìm các đơn hàng được tạo sau một thời điểm:

~~~java
List<Order> findByCreatedAtAfter(
    @Param("createdAfter") Instant createdAfter
);
~~~

Request:

~~~http
GET /orders/search/findByCreatedAtAfter?createdAfter=2026-11-11T02%3A30%3A00Z
~~~

### Chọn đúng kiểu ngày giờ

- Dùng LocalDate khi chỉ quan tâm ngày lịch, chẳng hạn ngày sinh hoặc ngày giao hàng.
- Dùng LocalTime khi chỉ quan tâm giờ trong ngày, chẳng hạn giờ mở cửa.
- Dùng LocalDateTime khi ngày và giờ có ý nghĩa theo lịch địa phương nhưng không cần xác định một thời điểm toàn cầu.
- Dùng OffsetDateTime khi request cần mang theo độ lệch UTC cụ thể.
- Dùng Instant khi cần so sánh thời điểm tuyệt đối, ghi nhận sự kiện hoặc lọc dữ liệu theo dòng thời gian.

Không nên dùng LocalDateTime để thay thế một thời điểm tuyệt đối nếu ứng dụng có nhiều múi giờ. LocalDateTime không chứa thông tin múi giờ hoặc offset, vì vậy cùng một giá trị có thể biểu diễn các thời điểm khác nhau ở các khu vực khác nhau.

### Chú ý ký tự đặc biệt trong URL

Dấu cộng trong offset, ví dụ +07:00, cần được URL encode thành %2B khi đặt trong query string. Nếu gửi dấu cộng thô, một số cách phân tích query string có thể giải mã nó thành dấu cách.

Ví dụ an toàn:

~~~http
GET /events/search/findByStartAt?startAt=2026-11-11T09%3A30%3A00%2B07%3A00
~~~

Client nên dùng URI builder hoặc thư viện HTTP để encode query parameter thay vì tự nối chuỗi URL.

## 4. Dùng định dạng ngày giờ riêng

Nếu API hiện có yêu cầu định dạng khác ISO, chẳng hạn ngày theo mẫu dd-MM-yyyy, có thể đăng ký Converter<String, LocalDate> riêng.

~~~java
public class StringToLocalDateConverter
        implements Converter<String, LocalDate> {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("dd-MM-uuuu", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public LocalDate convert(String source) {
        return LocalDate.parse(source.trim(), FORMAT);
    }
}
~~~

Sau khi đăng ký converter, client có thể gửi:

~~~http
GET /events/search/findByEventDate?date=11-11-2026
~~~

Converter cần xác định rõ định dạng đầu vào. Không nên tự đoán giữa các mẫu như dd-MM-yyyy và MM-dd-yyyy vì một chuỗi như 04-05-2026 có thể được hiểu theo hai cách khác nhau.

Nếu API có thể thiết kế mới, nên giữ định dạng ISO. Chỉ dùng định dạng riêng khi có yêu cầu tương thích hoặc quy ước nghiệp vụ cụ thể.

## 5. Đăng ký converter với RepositoryRestConfigurer

Để converter được sử dụng trong Spring Data REST, đăng ký nó qua phương thức configureConversionService của RepositoryRestConfigurer.

~~~java
@Configuration
public class RepositoryRestConversionConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureConversionService(
            ConfigurableConversionService conversionService) {

        conversionService.addConverter(
            new StringToOrderStatusConverter()
        );

        conversionService.addConverter(
            new StringToLocalDateConverter()
        );
    }
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
~~~

Cách đăng ký này cấu hình ConversionService mà Spring Data REST sử dụng. Chỉ khai báo một Converter bean hoặc đăng ký formatter cho Spring MVC không có nghĩa converter chắc chắn đã được thêm vào ConversionService riêng của Spring Data REST.

Có thể gom nhiều converter vào cùng một RepositoryRestConfigurer. Nên giữ mỗi converter tập trung vào một cặp kiểu nguồn và kiểu đích để dễ đọc, kiểm thử và tái sử dụng.

## 6. Chuyển đổi kiểu tham số tùy chỉnh

Ngoài enum và ngày giờ, query method có thể nhận một value object của domain. Ví dụ hệ thống dùng CustomerCode thay cho String thuần:

~~~java
public final class CustomerCode {

    private final String value;

    public CustomerCode(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Customer code must not be blank"
            );
        }

        this.value = value.trim();
    }

    public String getValue() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (!(other instanceof CustomerCode that)) {
            return false;
        }

        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

Converter chuyển String từ URL thành CustomerCode:

~~~java
public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        return new CustomerCode(source);
    }
}
~~~

Repository có thể khai báo tham số cùng kiểu với thuộc tính domain tương ứng:

~~~java
List<Customer> findByCustomerCode(
    @Param("code") CustomerCode code
);
~~~

Client gửi:

~~~http
GET /customers/search/findByCustomerCode?code=CUS-001
~~~

Spring Data REST chuyển CUS-001 thành CustomerCode rồi truyền đối tượng đó vào query method.

Điều kiện quan trọng là kiểu tham số phải phù hợp với cách Spring Data xây dựng truy vấn. Converter chỉ chuyển đổi dữ liệu request; nó không tự tạo ra ý nghĩa truy vấn cho một đối tượng tùy ý. Nếu muốn truyền một filter gồm nhiều trường không tương ứng trực tiếp với thuộc tính domain, cần có repository query hoặc custom repository implementation xử lý filter đó.

### Converter cho tham số phức hợp

Một query parameter có thể chứa nhiều giá trị, ví dụ một khoảng ngày. Spring Data REST cho phép đăng ký converter từ String[] sang kiểu đối tượng tùy chỉnh:

~~~java
public class DateWindowConverter
        implements Converter<String[], DateWindow> {

    @Override
    public DateWindow convert(String[] values) {
        if (values.length != 2) {
            throw new IllegalArgumentException(
                "Expected start date and end date"
            );
        }

        LocalDate start = LocalDate.parse(values[0]);
        LocalDate end = LocalDate.parse(values[1]);

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                "End date must not be before start date"
            );
        }

        return new DateWindow(start, end);
    }
}
~~~

Client có thể gửi cùng một query parameter nhiều lần:

~~~http
GET /reports/search/findByWindow?window=2026-11-01&window=2026-11-30
~~~

Converter nhận các giá trị chuỗi và tạo DateWindow. Sau đó query method hoặc custom repository logic phải biết cách sử dụng DateWindow để thực hiện nghiệp vụ tìm kiếm. Chỉ đăng ký converter không làm cho Spring Data tự hiểu rằng start và end phải trở thành điều kiện lớn hơn hoặc nhỏ hơn trên một thuộc tính.

## 7. Phân biệt chuyển đổi tham số REST và chuyển đổi persistence

Trong ứng dụng Spring Data, có thể có nhiều lớp chuyển đổi khác nhau:

| Cơ chế | Mục đích |
|---|---|
| Spring Data REST ConversionService | Chuyển query parameter thành kiểu Java của tham số repository |
| Jackson serializer/deserializer | Chuyển đổi dữ liệu JSON khi đọc hoặc ghi representation |
| JPA AttributeConverter | Chuyển đổi giữa kiểu thuộc tính entity và kiểu lưu trong database |
| Spring Data CustomConversions | Chuyển đổi kiểu dữ liệu trong tầng persistence của module Spring Data tương ứng |

Ví dụ, Converter<String, CustomerCode> giúp Spring Data REST tạo CustomerCode từ query parameter. Nếu CustomerCode được lưu vào một cột JPA dưới dạng VARCHAR, ứng dụng có thể cần thêm JPA AttributeConverter<CustomerCode, String> để chuyển đổi giữa CustomerCode và giá trị cột.

Hai converter phục vụ hai luồng khác nhau. Đăng ký converter cho REST không tự động cấu hình cách JPA lưu value object vào database; ngược lại, cấu hình JPA AttributeConverter không bảo đảm query parameter được chuyển thành CustomerCode.

## 8. Xử lý giá trị không hợp lệ

Nếu client gửi một giá trị không thể chuyển đổi, query method không thể được gọi với tham số hợp lệ. Ví dụ:

~~~http
GET /orders/search/findByStatus?status=UNKNOWN
~~~

Hoặc:

~~~http
GET /events/search/findByEventDate?date=31-02-2026
~~~

Các lỗi chuyển đổi thường được trả về như lỗi request không hợp lệ, thường là HTTP 400 Bad Request. Cấu trúc response và thông báo lỗi cụ thể phụ thuộc phiên bản Spring Data REST, Spring Framework và cấu hình xử lý exception của ứng dụng.

Converter nên kiểm tra dữ liệu đầu vào và phát sinh lỗi rõ ràng khi giá trị không hợp lệ. Không nên âm thầm thay một enum lạ bằng trạng thái mặc định hoặc biến một ngày không hợp lệ thành ngày khác, vì điều đó có thể làm truy vấn trả về dữ liệu sai mà client không nhận ra.

Các giá trị cần kiểm tra gồm:

- Enum có thuộc tập giá trị được hỗ trợ hay không.
- Ngày có tồn tại trên lịch hay không.
- Offset và timezone có đúng định dạng không.
- Khoảng thời gian có thứ tự hợp lệ không.
- Value object có đáp ứng quy tắc định dạng và nghiệp vụ hay không.
- Query parameter bắt buộc có bị thiếu hoặc để trống không.

Không nên trả stack trace hoặc thông tin nội bộ của domain ra response công khai. Hãy cung cấp thông báo lỗi phù hợp và ghi chi tiết kỹ thuật vào log phía server theo chính sách của ứng dụng.

## 9. Kiểm thử chuyển đổi tham số

Nên kiểm thử converter riêng và kiểm thử tích hợp qua endpoint Spring Data REST. Kiểm thử converter đơn lẻ xác nhận quy tắc chuyển đổi; kiểm thử HTTP xác nhận converter thực sự được đăng ký vào ConversionService mà query method sử dụng.

Các trường hợp nên kiểm tra:

1. Enum hợp lệ đúng chữ hoa/chữ thường.
2. Enum alias nếu API hỗ trợ alias.
3. Enum không tồn tại hoặc chuỗi rỗng.
4. LocalDate ở định dạng ISO.
5. LocalDate với định dạng tùy chỉnh nếu ứng dụng có đăng ký converter.
6. OffsetDateTime có offset dương, offset âm và giá trị UTC.
7. Query parameter chứa dấu cộng đã được URL encode.
8. Value object hợp lệ và không hợp lệ.
9. Query parameter lặp lại khi converter nhận String[].
10. Giá trị thiếu, null hoặc không đủ số phần tử theo quy tắc của endpoint.

Ví dụ một test tích hợp có thể gửi request tìm đơn hàng với status=PAID và thời điểm createdAfter hợp lệ, sau đó xác nhận repository trả đúng các đơn hàng. Một test khác gửi status=UNKNOWN và xác nhận request bị từ chối với lỗi 4xx thay vì chạy truy vấn bằng một giá trị mặc định.

## 10. Quy trình triển khai

1. Khai báo kiểu tham số cụ thể trong query method thay vì dùng String cho mọi trường hợp.
2. Đặt tên query parameter rõ ràng bằng @Param.
3. Chọn định dạng ổn định cho enum và ngày giờ; ưu tiên ISO cho dữ liệu thời gian.
4. Nếu cần alias hoặc định dạng riêng, viết Converter với source và target type chính xác.
5. Đăng ký converter qua RepositoryRestConfigurer.configureConversionService.
6. Nếu kiểu tùy chỉnh còn được lưu trong database, cấu hình riêng cơ chế chuyển đổi persistence phù hợp.
7. Kiểm thử cả converter lẫn query endpoint thực tế với dữ liệu hợp lệ và không hợp lệ.

## 11. Những điểm cần ghi nhớ

- Query parameter đi vào Spring Data REST dưới dạng chuỗi và được ConversionService chuyển sang kiểu tham số Java của query method.
- Enum có thể được chuyển đổi bằng converter mặc định; dùng custom Converter nếu cần alias hoặc quy tắc không phân biệt hoa thường.
- LocalDate, LocalDateTime, OffsetDateTime và Instant có ý nghĩa thời gian khác nhau; chọn kiểu phù hợp với nghiệp vụ.
- Dùng ISO date/time làm định dạng trao đổi mặc định và URL encode ký tự đặc biệt như dấu cộng trong offset.
- Đăng ký converter riêng qua RepositoryRestConfigurer.configureConversionService.
- Converter chỉ chuyển đổi giá trị; query method hoặc custom repository vẫn phải định nghĩa cách sử dụng tham số đó.
- Chuyển đổi request REST, JSON và persistence là các luồng khác nhau; cấu hình một luồng không tự động cấu hình các luồng còn lại.
- Kiểm thử endpoint thật để xác nhận dữ liệu được chuyển đổi đúng trước khi query được thực thi.

## Nguồn tham khảo

- [Spring Data REST — Repository resources và Query Method Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Data REST — EnumTranslationConfiguration API](https://docs.spring.io/spring-data/rest/reference/5.2/api/java/org/springframework/data/rest/core/config/EnumTranslationConfiguration.html)
