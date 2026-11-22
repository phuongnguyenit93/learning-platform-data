# Thuộc tính tính toán với @Value và biểu thức SpEL

Trong Spring Data REST, projection cho phép định nghĩa cách một entity được trình bày cho client. Ngoài việc chọn các thuộc tính có sẵn, interface projection còn có thể cung cấp thuộc tính tính toán bằng annotation @Value và biểu thức SpEL (Spring Expression Language).

Ví dụ, entity Customer lưu firstName và lastName riêng biệt, nhưng API có thể trả thêm displayName được ghép từ hai trường đó. displayName không cần là một cột trong cơ sở dữ liệu; Spring Data tính giá trị từ đối tượng đích khi tạo projection.

## 1. Thuộc tính tính toán trong projection là gì?

Một projection interface mô tả các thuộc tính mà client được nhìn thấy trong representation. Với getter thông thường, Spring Data lấy giá trị từ property tương ứng trên entity. Với getter có @Value, Spring đánh giá biểu thức SpEL để tạo ra giá trị trả về.

Ví dụ entity:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private Integer age;
    private boolean active;

    // getters and setters
}
~~~

Ta muốn API cung cấp displayName và statusLabel dù entity không khai báo hai property này:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "customerSummary", types = Customer.class)
public interface CustomerSummary {

    String getFirstName();

    String getLastName();

    @Value("#{target.firstName + ' ' + (target.lastName ?: '')}")
    String getDisplayName();

    @Value("#{target.active ? 'Đang hoạt động' : 'Ngừng hoạt động'}")
    String getStatusLabel();
}
~~~

Trong ví dụ:

- getFirstName() và getLastName() đọc property có sẵn trên Customer.
- getDisplayName() ghép tên và họ thành một chuỗi.
- getStatusLabel() chuyển giá trị boolean active thành nhãn dễ đọc.
- target là đối tượng Customer đang được projection trình bày.

Các getter do @Value định nghĩa là computed properties. Chúng được tính từ đối tượng đích khi projection được sử dụng; không tạo cột mới và không tự ghi giá trị tính toán vào cơ sở dữ liệu.

## 2. Hiểu target trong biểu thức SpEL

Trong biểu thức SpEL của projection, target tham chiếu tới đối tượng nguồn mà projection đang bọc. Có thể truy cập property của entity bằng cú pháp property:

~~~java
@Value("#{target.firstName}")
String getFirstNameFromTarget();
~~~

Biểu thức này tương đương với việc đọc getter firstName của Customer. Khi cần kết hợp nhiều thuộc tính, có thể dùng toán tử nối chuỗi:

~~~java
@Value("#{target.firstName + ' ' + target.lastName}")
String getFullName();
~~~

Nếu lastName có thể null, biểu thức nên xử lý trường hợp đó. SpEL hỗ trợ toán tử Elvis:

~~~java
@Value("#{target.firstName + ' ' + (target.lastName ?: '')}")
String getDisplayName();
~~~

Toán tử ?: dùng giá trị bên phải khi biểu thức bên trái là null. Nếu domain có quy tắc xử lý chuỗi rỗng hoặc tên thiếu phức tạp hơn, hãy biểu diễn quy tắc đó rõ ràng trong biểu thức hoặc chuyển logic sang một bean chuyên trách.

SpEL cũng hỗ trợ toán tử điều kiện:

~~~java
@Value("#{target.age >= 18 ? 'Adult' : 'Minor'}")
String getAgeGroup();
~~~

Biểu thức đọc age, so sánh với 18 và trả về một trong hai nhãn. Kiểu giá trị được trả về cần tương thích với kiểu getter; ví dụ trên trả về String nên getter khai báo String.

## 3. Công bố projection trong Spring Data REST

Spring Data REST có thể phát hiện projection được đánh dấu @Projection nếu interface nằm trong package của domain type hoặc một package con theo quy tắc tìm kiếm projection của framework.

Ví dụ repository:

~~~java
@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Giả sử CustomerSummary được đặt trong package phù hợp và có tên projection là customerSummary. Client có thể yêu cầu projection khi đọc collection hoặc item:

~~~http
GET /api/customers?projection=customerSummary
~~~

Hoặc:

~~~http
GET /api/customers/42?projection=customerSummary
~~~

Response sẽ sử dụng cấu trúc projection thay vì representation mặc định của entity. Ví dụ minh họa:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "displayName": "An Nguyen",
  "statusLabel": "Đang hoạt động",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/customers/42"
    }
  }
}
~~~

Các liên kết và cấu trúc HAL cụ thể còn phụ thuộc cấu hình Spring Data REST, nhưng những thuộc tính displayName và statusLabel được lấy từ biểu thức SpEL trong projection.

Nếu projection không xuất hiện, hãy kiểm tra tên trong @Projection, package chứa interface, kiểu domain được khai báo trong types và cách client truyền tham số projection.

## 4. Dùng excerptProjection làm projection mặc định cho collection

Nếu muốn collection resource sử dụng một projection làm excerpt mặc định, có thể khai báo excerptProjection trên repository:

~~~java
@RepositoryRestResource(
    path = "customers",
    excerptProjection = CustomerSummary.class
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Excerpt projection được dùng để trình bày các phần tử nhúng trong collection resource. Điều này giúp collection trả về một representation gọn và nhất quán mà client không phải truyền projection mỗi lần.

Cần phân biệt excerpt projection với việc chọn projection rõ ràng qua tham số projection. excerptProjection đặt representation mặc định cho phần tử được nhúng trong collection; client vẫn có thể yêu cầu một projection khác nếu projection đó được công bố và cấu hình cho phép.

Không nên đưa quá nhiều dữ liệu hoặc phép tính nặng vào excerpt projection của collection lớn, vì biểu thức có thể được đánh giá cho từng phần tử được trả về.

## 5. Gọi bean Spring từ biểu thức SpEL

Ngoài việc đọc thuộc tính của target, SpEL có thể gọi bean Spring thông qua tên bean. Cách này hữu ích khi logic tính toán cần dùng một formatter hoặc thành phần chuyên biệt.

Ví dụ bean:

~~~java
@Component("customerLabelFormatter")
public class CustomerLabelFormatter {

    public String format(Customer customer) {
        return customer.getFirstName() + " " + customer.getLastName();
    }
}
~~~

Projection có thể gọi bean đó:

~~~java
@Value("#{@customerLabelFormatter.format(target)}")
String getDisplayName();
~~~

Trong biểu thức:

- @customerLabelFormatter tham chiếu bean theo tên trong Spring context.
- format(target) gọi phương thức của bean và truyền entity nguồn.
- Kết quả trả về được dùng làm giá trị của getDisplayName().

Cách này tách logic định dạng ra khỏi interface projection và có thể tái sử dụng. Tuy nhiên, bean được gọi trong quá trình tạo representation, nên phương thức nên có tính xác định, nhanh và không gây side effect. Tránh gọi dịch vụ từ xa, ghi dữ liệu hoặc thực hiện tác vụ tốn thời gian trong getter của projection.

Với logic nghiệp vụ phức tạp, cần transaction, kiểm tra quyền hoặc truy vấn dữ liệu bổ sung, service layer thường là nơi phù hợp hơn. Projection nên tập trung vào việc định hình dữ liệu đầu ra.

## 6. Open projection và ảnh hưởng tới tối ưu truy vấn

Projection chỉ dùng accessor thông thường, ví dụ getFirstName() và getLastName(), thường được gọi là closed projection. Spring Data biết chính xác những property nào được yêu cầu và trong một số trường hợp có thể tối ưu truy vấn để chỉ lấy các trường cần thiết.

Khi dùng @Value để tính property, projection trở thành open projection. SpEL có thể truy cập bất kỳ property nào trên target, vì vậy Spring Data không thể luôn xác định trước toàn bộ dữ liệu cần thiết để tính kết quả. Cơ hội tối ưu việc chỉ lấy các cột được sử dụng có thể bị hạn chế.

Ví dụ:

~~~java
public interface CustomerNameView {

    String getFirstName();

    String getLastName();
}
~~~

Đây là projection đóng vì chỉ yêu cầu hai property đã biết.

Trong khi đó:

~~~java
public interface CustomerDisplayView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

là open projection vì biểu thức SpEL được đánh giá trên target. Khi dùng JPA, không nên mặc định rằng query chỉ chọn đúng hai cột firstName và lastName; việc lấy dữ liệu phụ thuộc cách Spring Data xây dựng truy vấn và cách projection được sử dụng.

Nếu cần tối ưu truy vấn cho tập dữ liệu lớn, hãy cân nhắc DTO/class-based projection hoặc query trả về đúng các cột cần thiết. Dùng @Value khi lợi ích của thuộc tính tính toán trong representation đáng giá so với giới hạn tối ưu truy vấn.

## 7. Truy cập quan hệ và vấn đề lazy loading

SpEL có thể truy cập property lồng nhau trên target. Ví dụ, nếu Customer có quan hệ với Address:

~~~java
@Value("#{target.address.city}")
String getCity();
~~~

Biểu thức này đọc city từ Address. Nhưng nếu address là quan hệ lazy, việc đánh giá getter có thể kích hoạt truy vấn bổ sung khi tạo representation.

Nếu projection được dùng cho nhiều khách hàng trong một collection, việc truy cập quan hệ lazy cho từng phần tử có thể gây N+1 queries. Với biểu thức gọi bean hoặc duyệt collection, chi phí còn có thể lớn hơn nếu mỗi lần đánh giá phát sinh truy vấn riêng.

Một số lưu ý:

- Chỉ truy cập các quan hệ thực sự cần cho response.
- Xác định fetch strategy và query phù hợp với cách projection được dùng.
- Theo dõi SQL khi trả về collection lớn.
- Tránh gọi repository lặp lại từ SpEL hoặc formatter cho từng entity.
- Với dữ liệu tổng hợp phức tạp, cân nhắc query projection hoặc service tạo DTO có kiểm soát.

SpEL giúp biểu diễn ngắn gọn, nhưng không làm cho truy cập dữ liệu trở nên miễn phí. Mọi property hoặc method được gọi vẫn có thể có chi phí runtime.

## 8. Giới hạn và bảo mật của computed properties

Computed property chỉ là một cách tạo representation. Nó không phải cơ chế phân quyền và không bảo đảm các trường khác của entity được bảo vệ ở mọi endpoint.

Nếu Customer có thông tin nhạy cảm như email cá nhân, số điện thoại hoặc dữ liệu nội bộ, hãy định nghĩa projection chỉ chứa các trường được phép công bố. Đồng thời, kiểm soát các repository resource, projection khác và endpoint tùy chỉnh có thể trả về cùng entity.

Không nên dùng SpEL để bỏ qua kiểm tra quyền trong service. Nếu một giá trị chỉ được phép hiển thị cho một nhóm người dùng, hãy thực hiện kiểm tra quyền ở tầng bảo mật hoặc service và thiết kế representation phù hợp cho từng vai trò.

Cũng cần tránh biểu thức truy cập trực tiếp các trường bí mật chỉ vì chúng có trên target. Một projection công khai có thể khiến computed property trở thành dữ liệu được gửi tới client.

## 9. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy computed property | Projection không được phát hiện hoặc client không chọn đúng tên projection. | Kiểm tra @Projection, package, types và tham số projection. |
| SpEL báo lỗi khi serialize | Property không tồn tại, tên getter sai hoặc biểu thức không tương thích kiểu trả về. | Kiểm tra property trên target và kiểu getter. |
| Giá trị hiển thị là null hoặc có chữ null | Property nguồn có thể null và biểu thức chưa xử lý trường hợp đó. | Dùng Elvis hoặc điều kiện trong SpEL. |
| Response chậm khi lấy collection | Biểu thức truy cập quan hệ lazy hoặc gọi bean gây truy vấn cho từng entity. | Giảm truy cập quan hệ, tối ưu query hoặc dùng DTO projection. |
| Không tối ưu được cột truy vấn | @Value tạo open projection và Spring Data không biết đầy đủ property cần đọc trước. | Cân nhắc closed projection hoặc DTO/class-based projection. |
| Dữ liệu không mong muốn bị công bố | Projection hoặc endpoint khác vẫn trả về property nhạy cảm. | Xác định rõ representation công khai và cấu hình quyền truy cập. |

## 10. Quy trình kiểm tra

Sau khi khai báo projection có @Value, có thể kiểm tra theo trình tự:

1. Khởi động ứng dụng và xác nhận repository Customer được Spring Data REST công bố.
2. Gọi GET /api/customers để xem collection resource.
3. Gọi GET /api/customers/42?projection=customerSummary.
4. Xác nhận displayName được ghép từ firstName và lastName.
5. Thử một Customer có lastName null để kiểm tra biểu thức Elvis.
6. Thay đổi active và xác nhận statusLabel phản ánh trạng thái tương ứng.
7. Gọi collection với projection hoặc excerptProjection và kiểm tra số lần truy vấn SQL.
8. Nếu SpEL truy cập quan hệ, kiểm tra lazy loading và truy vấn bổ sung.
9. Kiểm tra representation bằng tài khoản có quyền khác nhau để bảo đảm computed property không tiết lộ dữ liệu ngoài chính sách.

@Value và SpEL cho phép bổ sung thuộc tính tính toán vào interface projection mà không cần lưu các giá trị đó thành cột riêng. Hãy dùng target để đọc dữ liệu nguồn, xử lý null rõ ràng, và giữ biểu thức nhẹ. Khi phép tính phức tạp hoặc ảnh hưởng lớn tới truy vấn, chuyển logic sang bean chuyên trách, service hoặc DTO projection để kiểm soát hiệu năng và quyền truy cập.
