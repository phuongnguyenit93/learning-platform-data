# AfterConvertCallback cho dữ liệu dẫn xuất sau khi tải

Trong **Spring Data Relational JDBC**, một aggregate thường được ánh xạ từ các hàng trong database thành object Java trước khi repository trả kết quả cho ứng dụng. Có những thông tin chỉ cần tồn tại trong object sau khi tải, chẳng hạn nhãn hiển thị được suy ra từ trạng thái, một mô tả ngắn được ghép từ các thuộc tính đã có hoặc một giá trị hỗ trợ cho quá trình trình bày.

**`AfterConvertCallback`** là lifecycle callback được Spring Data JDBC gọi sau khi dữ liệu relational đã được chuyển thành aggregate. Callback nhận aggregate vừa được tạo, có thể bổ sung dữ liệu dẫn xuất và phải trả về aggregate để Spring Data tiếp tục sử dụng kết quả đó.

Một cách dùng phổ biến là kết hợp callback với thuộc tính `@Transient`: thuộc tính được giữ trong object Java nhưng không được ánh xạ thành cột database. Bài học này trình bày thời điểm callback chạy, cách đăng ký, cách cập nhật aggregate mutable hoặc immutable, cách kiểm tra và những giới hạn cần cân nhắc.

## 1. Vị trí của AfterConvertCallback trong vòng đời đọc

Khi repository đọc một aggregate, Spring Data JDBC lấy dữ liệu từ database và dùng mapping infrastructure để chuyển dữ liệu thành object domain. Sau khi quá trình chuyển đổi hoàn tất, `AfterConvertCallback` có thể can thiệp vào aggregate trước khi kết quả được trả về cho code gọi.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Repository đọc dữ liệu"] --> B["JDBC thực thi SELECT"]
    B --> C["Spring Data JDBC nhận các hàng"]
    C --> D["Mapping chuyển dữ liệu thành aggregate"]
    D --> E["AfterConvertCallback.onAfterConvert()"]
    E --> F["Aggregate sau callback"]
    F --> G["Repository trả kết quả cho caller"]
~~~

Callback phù hợp khi giá trị dẫn xuất cần được thiết lập ngay sau khi aggregate được mapping, trước khi service hoặc controller sử dụng object.

### 1.1. Callback này chạy ở chiều đọc

Tên `AfterConvert` mô tả đúng thời điểm: sau khi Spring Data chuyển dữ liệu relational thành object Java.

Nó không phải hook dành cho:

- Chuẩn bị aggregate trước khi ghi xuống database.
- Chỉnh dữ liệu ngay trước câu INSERT hoặc UPDATE.
- Xử lý sau khi aggregate đã được lưu.
- Thực thi SQL tùy chỉnh thay cho repository.

Các thao tác ghi có lifecycle callback riêng, chẳng hạn `BeforeConvertCallback`, `BeforeSaveCallback` và `AfterSaveCallback`. Chọn callback theo đúng thời điểm cần can thiệp.

### 1.2. Callback làm việc với aggregate đã được chuyển đổi

`AfterConvertCallback<T>` nhận kiểu aggregate `T` và trả về một object `T`:

~~~java
public interface AfterConvertCallback<T> extends EntityCallback<T> {
    T onAfterConvert(T aggregate);
}
~~~

Trong ứng dụng, thường chỉ cần triển khai interface cho aggregate cụ thể. Spring Data gọi callback trong quá trình mapping; không cần gọi thủ công từ service.

Callback này thuộc package:

~~~java
org.springframework.data.relational.core.mapping.event.AfterConvertCallback
~~~

## 2. Khi nào nên dùng dữ liệu dẫn xuất sau khi tải?

Giả sử `PurchaseOrder` lưu trạng thái dưới dạng enum:

~~~java
public enum OrderStatus {
    DRAFT,
    SUBMITTED,
    CANCELLED
}
~~~

Database chỉ lưu mã trạng thái, còn ứng dụng muốn có một nhãn mô tả đơn giản:

| Trạng thái | Nhãn dẫn xuất |
|---|---|
| `DRAFT` | Bản nháp |
| `SUBMITTED` | Đã gửi |
| `CANCELLED` | Đã hủy |

Nhãn này có thể được tính từ thuộc tính `status` sau khi aggregate được tải. Nếu không cần lưu nhãn vào database, có thể đặt nó trong thuộc tính `@Transient`.

Các trường hợp phù hợp khác:

- Tạo chuỗi mô tả ngắn từ những thuộc tính đã có trên aggregate.
- Tính một giá trị hỗ trợ hiển thị không cần lưu trữ.
- Chuẩn bị một thuộc tính phụ mà nhiều consumer của aggregate đều cần.
- Chuẩn hóa một giá trị trong object sau khi mapping, nếu quy tắc đó ổn định và không cần truy vấn thêm dữ liệu.

Không nên dùng callback chỉ vì có thể làm được. Nếu giá trị có thể tính trực tiếp bằng getter hoặc domain method đơn giản, hãy cân nhắc cách đó trước. Callback hữu ích khi cần một bước xử lý tập trung sau khi Spring Data đã dựng aggregate.

## 3. Đánh dấu thuộc tính dẫn xuất bằng @Transient

`@Transient` của Spring Data đánh dấu property không thuộc persistence mapping. Property vẫn có thể tồn tại trong object Java và được code sử dụng, nhưng Spring Data JDBC không ánh xạ nó thành cột cần đọc hoặc ghi.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private OrderStatus status;

    @Transient
    private String statusLabel;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public String getStatusLabel() {
        return statusLabel;
    }

    public void setStatusLabel(String statusLabel) {
        this.statusLabel = statusLabel;
    }
}
~~~

Property `statusLabel` không cần cột `status_label` trong bảng `purchase_orders`. Callback sẽ gán giá trị cho property này sau khi Spring Data JDBC tạo object.

Phân biệt hai ý:

- `@Transient` quyết định property không được persistence mapping quản lý.
- `AfterConvertCallback` quyết định khi nào và bằng cách nào property đó được gán giá trị sau khi đọc.

Chỉ thêm `@Transient` không tự tính giá trị. Chỉ thêm callback mà không đánh dấu property phù hợp có thể khiến Spring Data cố ánh xạ property đó như dữ liệu lưu trữ.

## 4. Triển khai AfterConvertCallback

Callback có thể được khai báo thành Spring bean bằng `@Component` hoặc đăng ký qua một cấu hình bean.

~~~java
import org.springframework.data.relational.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
        aggregate.setStatusLabel(toLabel(aggregate.getStatus()));
        return aggregate;
    }

    private String toLabel(OrderStatus status) {
        if (status == null) {
            return "Chưa xác định";
        }

        return switch (status) {
            case DRAFT -> "Bản nháp";
            case SUBMITTED -> "Đã gửi";
            case CANCELLED -> "Đã hủy";
        };
    }
}
~~~

Điểm quan trọng:

1. Generic type `PurchaseOrder` xác định aggregate mà callback xử lý.
2. Method `onAfterConvert` nhận aggregate đã được mapping.
3. Callback tính nhãn từ dữ liệu đã có trong aggregate.
4. Callback trả lại aggregate đã được bổ sung giá trị.

Vì callback là Spring bean, Spring Data có thể phát hiện và gọi nó trong lifecycle mapping. Không cần gọi `onAfterConvert()` trực tiếp trong repository hoặc service.

### 4.1. Vì sao phải trả về aggregate?

Callback có thể thay đổi object hiện tại rồi trả lại chính object đó:

~~~java
@Override
public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
    aggregate.setStatusLabel(toLabel(aggregate.getStatus()));
    return aggregate;
}
~~~

Hoặc tạo và trả về một instance mới, điều này hữu ích khi aggregate bất biến:

~~~java
@Override
public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
    return aggregate.withStatusLabel(toLabel(aggregate.getStatus()));
}
~~~

Nếu callback tạo object mới nhưng lại trả về object cũ, thay đổi sẽ không xuất hiện trong kết quả mà Spring Data tiếp tục sử dụng. Luôn trả về instance chứa dữ liệu dẫn xuất cuối cùng.

## 5. Làm việc với aggregate bất biến

Không phải domain model nào cũng có setter. Với class bất biến, có thể tạo một bản sao chứa thuộc tính dẫn xuất.

Ví dụ minh họa:

~~~java
public final class PurchaseOrder {

    private final Long id;
    private final String orderNumber;
    private final OrderStatus status;
    private final String statusLabel;

    public PurchaseOrder(
            Long id,
            String orderNumber,
            OrderStatus status,
            String statusLabel) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
        this.statusLabel = statusLabel;
    }

    public PurchaseOrder withStatusLabel(String label) {
        return new PurchaseOrder(
            id,
            orderNumber,
            status,
            label
        );
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public String getStatusLabel() {
        return statusLabel;
    }
}
~~~

Callback:

~~~java
@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
        String label = switch (aggregate.getStatus()) {
            case DRAFT -> "Bản nháp";
            case SUBMITTED -> "Đã gửi";
            case CANCELLED -> "Đã hủy";
        };

        return aggregate.withStatusLabel(label);
    }
}
~~~

Đây là phác thảo về cách trả instance mới; constructor, creator và mapping metadata của aggregate bất biến cần phù hợp với cấu hình Spring Data JDBC của ứng dụng. Nếu dùng `@Transient` trên property bất biến, hãy xác nhận annotation được đặt đúng trên property mà mapping context loại khỏi persistence mapping.

Không cần chuyển toàn bộ domain model sang mutable chỉ để sử dụng callback. Chọn cách cập nhật phù hợp với cách aggregate đang được thiết kế.

## 6. Đăng ký callback với Spring

Trong ứng dụng Spring Boot có component scanning, callback được phát hiện như các bean khác:

~~~java
@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {
    // ...
}
~~~

Nếu không dùng component scanning ở package chứa callback, có thể đăng ký bằng `@Bean`:

~~~java
@Configuration
public class OrderCallbackConfiguration {

    @Bean
    PurchaseOrderAfterConvertCallback purchaseOrderAfterConvertCallback() {
        return new PurchaseOrderAfterConvertCallback();
    }
}
~~~

Không cần đăng ký callback vào `JdbcCustomConversions`. Converter và entity callback là hai extension point khác nhau:

| Extension point | Mục đích |
|---|---|
| `AfterConvertCallback` | Xử lý aggregate sau khi dữ liệu đã được chuyển thành object |
| `JdbcCustomConversions` | Chuyển đổi giá trị giữa kiểu domain và kiểu JDBC |

Nếu callback không được gọi, hãy kiểm tra bean có nằm trong application context và có được component scanning hoặc cấu hình `@Bean` phát hiện hay không.

## 7. Callback được gọi khi nào?

Callback được gọi trong những đường đọc mà Spring Data JDBC thực hiện việc chuyển dữ liệu thành aggregate tương ứng. Ví dụ, các thao tác repository đọc aggregate như tìm theo ID hoặc truy vấn danh sách có thể đi qua mapping lifecycle này.

Điều quan trọng là callback gắn với **quá trình chuyển đổi aggregate**, không gắn với tên method cụ thể. Nếu code dùng `JdbcTemplate` để chạy SQL và tự ánh xạ `ResultSet` thành DTO, Spring Data JDBC không tự gọi `AfterConvertCallback` cho kết quả đó.

### 7.1. Không nhầm AfterConvert với AfterSave

`AfterConvertCallback` phục vụ lúc đọc. Nếu cần phản ứng sau khi aggregate được lưu, hãy xem callback dành cho lifecycle ghi như `AfterSaveCallback`.

Ví dụ phân biệt:

| Nhu cầu | Lifecycle phù hợp |
|---|---|
| Gán `statusLabel` sau khi tải aggregate | `AfterConvertCallback` |
| Chuẩn bị aggregate trước khi chuyển thành dữ liệu ghi | `BeforeConvertCallback` |
| Điều chỉnh dữ liệu trước khi lưu | `BeforeSaveCallback` |
| Thực hiện xử lý sau khi lưu | `AfterSaveCallback` |

Không dùng `AfterConvertCallback` để phát thông báo “đơn hàng vừa được tạo”. Một aggregate có thể được convert nhiều lần trong các lần đọc; đọc lại không có nghĩa là có sự kiện nghiệp vụ mới.

### 7.2. Không giả định callback chạy trên mọi object Java

Callback này thuộc Spring Data Relational mapping. Nó không tự chạy khi:

- Ứng dụng tự gọi constructor `new PurchaseOrder(...)`.
- Một mapper khác tạo object từ JSON.
- `JdbcTemplate` tự ánh xạ kết quả thành DTO.
- Một test tạo object trực tiếp mà không đi qua repository hoặc mapping infrastructure.

Nếu muốn cùng logic được áp dụng ở nhiều đường tạo object, hãy cân nhắc domain factory, domain method hoặc một mapper/service dùng chung thay vì phụ thuộc hoàn toàn vào callback.

## 8. Callback và thứ tự thực thi

Ứng dụng có thể có nhiều callback cho cùng lifecycle hoặc nhiều callback liên quan đến các aggregate khác nhau. Khi cần kiểm soát thứ tự, Spring hỗ trợ quy tắc ordering qua `Ordered` hoặc annotation `@Order`.

Ví dụ:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(100)
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {
    // ...
}
~~~

Khi có nhiều callback, hãy đặt thứ tự rõ nếu callback sau phụ thuộc kết quả callback trước. Giá trị order thấp hơn có độ ưu tiên chạy trước theo quy tắc ordering của Spring.

Tuy nhiên, tránh tạo chuỗi callback dài với nhiều thay đổi phụ thuộc lẫn nhau. Nếu việc làm giàu dữ liệu trở nên phức tạp, một service chuyên biệt sau khi repository trả kết quả có thể dễ hiểu và dễ kiểm soát hơn.

## 9. Không biến callback thành nơi truy vấn thêm cho từng aggregate

Một cám dỗ thường gặp là inject repository khác vào callback để tra cứu dữ liệu liên quan:

~~~java
// Không nên dùng cho danh sách lớn nếu mỗi lần callback đều truy vấn DB.
@Component
public class PurchaseOrderAfterConvertCallback
        implements AfterConvertCallback<PurchaseOrder> {

    private final CustomerRepository customers;

    public PurchaseOrderAfterConvertCallback(CustomerRepository customers) {
        this.customers = customers;
    }

    @Override
    public PurchaseOrder onAfterConvert(PurchaseOrder aggregate) {
        Customer customer = customers.findById(aggregate.getCustomerId())
            .orElseThrow();
        aggregate.setCustomerName(customer.getName());
        return aggregate;
    }
}
~~~

Nếu repository tải 100 đơn và callback truy vấn một khách hàng cho từng đơn, ứng dụng có thể phát sinh khoảng 100 query bổ sung. Đây là vấn đề **N+1 query**.

Với dữ liệu liên quan từ bảng khác, hãy cân nhắc:

- Viết một query đọc chuyên biệt JOIN các bảng và trả DTO.
- Lấy danh sách ID rồi truy vấn tất cả dữ liệu liên quan bằng một câu `IN`.
- Dùng một query service để làm giàu danh sách sau khi repository trả kết quả.
- Đưa dữ liệu thực sự thuộc aggregate vào mapping aggregate nếu quan hệ đó đúng với ranh giới domain.

Callback phù hợp nhất với dữ liệu có thể tính từ aggregate vừa tải. Nếu cần I/O hoặc truy vấn khác, hãy đo số query và cân nhắc chuyển phần làm giàu sang một read service có thể batch.

## 10. Callback nên có tính xác định và ít tác dụng phụ

Một callback được gọi như một phần của quá trình đọc dữ liệu. Do đó, cùng một aggregate đầu vào nên tạo ra kết quả dẫn xuất có thể dự đoán.

Nên:

- Tính giá trị từ những property đã được tải.
- Dùng hàm chuyển đổi thuần hoặc dịch vụ không có side effect.
- Trả về aggregate đã được bổ sung dữ liệu.
- Giữ callback ngắn và dễ kiểm thử.
- Xử lý rõ trường hợp property null hoặc dữ liệu cũ không hợp lệ.

Tránh:

- Gửi email hoặc gọi HTTP khi một aggregate được đọc.
- Ghi database khác như một tác dụng phụ của việc tải.
- Tạo event nghiệp vụ mỗi lần repository đọc object.
- Dùng thời gian hiện tại hoặc locale toàn cục để tạo giá trị có thể thay đổi ngoài ý muốn.
- Đặt quyết định phân quyền hoặc kiểm tra quyền truy cập trong callback.

Ví dụ, `statusLabel` phụ thuộc ngôn ngữ người dùng. Nếu callback dùng locale mặc định của server, cùng một aggregate có thể nhận nhãn khác với ngôn ngữ của request. Trong trường hợp này, hãy để presentation layer hoặc mapper nhận locale tường minh và tạo DTO phù hợp.

## 11. Giá trị dẫn xuất trong callback có được lưu xuống database không?

Không, nếu property được đánh dấu `@Transient`. Callback chỉ thay đổi object đang nằm trong bộ nhớ.

Ví dụ:

~~~java
@Transient
private String statusLabel;
~~~

Sau khi `AfterConvertCallback` gán `statusLabel`, code có thể đọc:

~~~java
PurchaseOrder order = orders.findById(id).orElseThrow();
System.out.println(order.getStatusLabel());
~~~

Nhưng giá trị này không tạo ra cột và không được ghi vào database như một phần mapping của aggregate.

Nếu sau đó aggregate được lưu lại, Spring Data JDBC tiếp tục bỏ qua property `@Transient`. Muốn lưu giá trị, phải thiết kế property persistent và schema tương ứng, hoặc lưu một dữ liệu khác theo đúng mô hình domain.

Không dùng `@Transient` cho dữ liệu cần tồn tại lâu dài hoặc cần được truy vấn trực tiếp từ database.

## 12. Kiểm tra callback bằng integration test

Unit test có thể kiểm tra hàm tính nhãn, nhưng integration test mới xác nhận Spring Data JDBC đã phát hiện callback và gọi nó trong quá trình đọc aggregate.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.context.annotation.Import;

@DataJdbcTest
@Import(PurchaseOrderAfterConvertCallback.class)
class PurchaseOrderAfterConvertCallbackTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void derivesStatusLabelAfterLoadingAggregate() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("SO-100", OrderStatus.SUBMITTED)
        );

        PurchaseOrder loaded = orders.findById(saved.getId())
            .orElseThrow();

        assertEquals(OrderStatus.SUBMITTED, loaded.getStatus());
        assertEquals("Đã gửi", loaded.getStatusLabel());
    }
}
~~~

Ví dụ giả định aggregate có factory `create`, repository và schema tương ứng. Điều chỉnh constructor, ID generation, package và cấu hình test theo dự án.

Test cần đọc lại aggregate qua repository. Object được tạo trực tiếp trong test hoặc object đầu vào của `save` không chứng minh `AfterConvertCallback` đã chạy, vì callback thuộc giai đoạn sau khi dữ liệu được chuyển đổi khi đọc.

### 12.1. Kiểm tra property transient không được ghi

Có thể xác nhận database không có cột `status_label` và callback vẫn gán được giá trị khi đọc. Điều này kiểm tra hai trách nhiệm độc lập:

1. Mapping bỏ qua property transient.
2. Callback bổ sung property trong bộ nhớ sau khi convert.

Nếu test cần xác minh SQL, dùng query kiểm tra dữ liệu lưu hoặc SQL logging trong môi trường test. Không cần thêm cột database chỉ để làm cho test callback chạy.

## 13. So sánh AfterConvertCallback với các lựa chọn khác

| Cách | Khi phù hợp | Lưu ý |
|---|---|---|
| Getter/domain method | Giá trị tính thuần từ các property hiện có | Không cần lưu state dẫn xuất |
| `AfterConvertCallback` | Cần bổ sung property sau khi Spring Data JDBC dựng aggregate | Được gọi trên đường mapping đọc |
| `AfterLoadCallback` | Cần hook ở giai đoạn load khác trong lifecycle relational | Kiểm tra chính xác hợp đồng callback theo version |
| DTO mapper/query service | Làm giàu dữ liệu cho một màn hình hoặc API | Có thể nhận locale, user context và batch data rõ ràng |
| SQL projection/DTO query | Giá trị cần JOIN, aggregate function hoặc tính ngay trong database | Kiểm soát query và tập cột rõ ràng |
| `AfterSaveCallback` | Cần xử lý sau khi aggregate được lưu | Không phải callback sau khi đọc |

Một giá trị đơn giản như nhãn từ enum có thể được tính bằng getter. Nếu nhiều consumer cần một property được chuẩn bị sau mapping, callback có thể giảm lặp code. Nếu giá trị phụ thuộc vào request hoặc dữ liệu từ nhiều bảng, DTO mapper/query service thường phù hợp hơn.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Callback không chạy | Bean không được Spring phát hiện | Dùng `@Component` trong component scan hoặc khai báo `@Bean` |
| Giá trị dẫn xuất không xuất hiện | Callback không trả aggregate đã thay đổi | Trả về instance chứa giá trị mới |
| Spring cố ánh xạ cột cho property phụ | Thiếu `@Transient` | Đánh dấu property không thuộc persistence mapping |
| Giá trị chỉ có sau khi đọc lại | Nhầm `AfterConvertCallback` với callback sau save | Dùng đúng lifecycle; callback này chạy khi convert dữ liệu đọc |
| Callback không chạy khi tự tạo object | Object không đi qua Spring Data mapping | Gọi domain factory/method hoặc mapper dùng chung |
| Query tăng đột biến | Callback truy vấn repository cho từng aggregate | Batch dữ liệu hoặc dùng query DTO có JOIN |
| Nhãn không đúng ngôn ngữ request | Callback dùng locale mặc định/toàn cục | Tạo nhãn ở presentation mapper với locale tường minh |
| Callback phát event lặp | Đọc aggregate bị nhầm là sự kiện nghiệp vụ | Chỉ dùng callback cho chuyển đổi object, không dùng để phát sự kiện nghiệp vụ |
| Giá trị transient biến mất sau lần tải tiếp theo | Property chỉ tồn tại trong bộ nhớ của instance hiện tại | Tính lại sau mỗi lần convert hoặc dùng DTO phù hợp |
| Dữ liệu null làm callback lỗi | Không xử lý trạng thái/property null | Xác định quy tắc fallback hoặc báo dữ liệu không hợp lệ |

## 15. Bài tập thực hành

### Bài 1 — Tạo nhãn trạng thái

1. Tạo aggregate `PurchaseOrder` có `id`, `orderNumber` và `status`.
2. Thêm property `statusLabel` được đánh dấu `@Transient`.
3. Viết `PurchaseOrderAfterConvertCallback`.
4. Ánh xạ từng `OrderStatus` sang nhãn tương ứng.
5. Đọc aggregate qua repository và kiểm tra nhãn.

### Bài 2 — Callback với aggregate bất biến

1. Chuyển aggregate sang thiết kế bất biến.
2. Thêm method `withStatusLabel`.
3. Tạo callback trả về instance mới.
4. Xác nhận repository nhận được instance sau callback.

### Bài 3 — So sánh callback với getter

1. Tính `statusLabel` trực tiếp bằng getter.
2. Tạo phiên bản dùng `AfterConvertCallback`.
3. So sánh độ phức tạp và khả năng kiểm thử.
4. Chọn cách phù hợp khi giá trị chỉ phụ thuộc enum trạng thái.

### Bài 4 — Phát hiện N+1

1. Tạo callback thử truy vấn `CustomerRepository` cho mỗi đơn hàng.
2. Đọc một danh sách nhiều đơn.
3. Quan sát số query phát sinh.
4. Chuyển phần làm giàu sang một query batch hoặc DTO JOIN.
5. So sánh số query và thời gian thực thi.

### Bài 5 — Kiểm tra ranh giới lifecycle

1. Tạo aggregate mới và gọi `save`.
2. Đọc lại bằng `findById`.
3. Quan sát thời điểm callback chạy.
4. Tự tạo object bằng constructor và xác nhận callback không tự chạy.
5. Thử `JdbcTemplate` với `RowMapper` và xác nhận đường mapping đó không tự kích hoạt callback của Spring Data JDBC.

## 16. Kết luận

`AfterConvertCallback` là lifecycle hook của Spring Data JDBC được gọi sau khi dữ liệu relational đã được chuyển thành aggregate. Callback nhận aggregate, có thể bổ sung giá trị dẫn xuất rồi trả về instance mà ứng dụng sẽ nhận. Kết hợp với `@Transient`, callback cho phép giữ một property hỗ trợ trong object Java mà không tạo cột hoặc ghi property đó xuống database.

Đăng ký callback như một Spring bean và triển khai `AfterConvertCallback<T>` cho aggregate cần xử lý. Giữ logic ngắn, xác định và chủ yếu dựa trên dữ liệu đã tải. Nếu cần dữ liệu từ bảng khác, truy vấn thêm hoặc context như locale/người dùng, hãy cân nhắc DTO mapper hay query service để tránh N+1 và tác dụng phụ khó dự đoán.

Hãy nhớ rằng callback này thuộc đường đọc và chuyển đổi aggregate. Nó không chạy khi code tự tạo object hoặc tự ánh xạ SQL bằng `JdbcTemplate`, cũng không thay thế callback của lifecycle ghi. Chọn đúng hook giúp việc bổ sung dữ liệu sau khi tải rõ ràng và dễ kiểm soát.
