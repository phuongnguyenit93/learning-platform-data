# Ánh xạ enum theo tên, mã nghiệp vụ hoặc kiểu riêng của cơ sở dữ liệu

## 1. Vì sao cần chọn cách lưu enum?

Trong Java, enum biểu diễn một tập hợp giá trị hữu hạn, có tên và có thể gắn thêm dữ liệu nghiệp vụ. Ví dụ, trạng thái đơn hàng có thể gồm PENDING, PAID, SHIPPED và CANCELLED.

Khi lưu entity bằng Spring Data Relational R2DBC, thuộc tính enum phải được chuyển thành một giá trị mà database và R2DBC driver có thể ghi nhận. Khi đọc dữ liệu, giá trị trong database lại phải được chuyển về đúng hằng enum trong Java.

Có ba hướng thiết kế thường gặp:

1. **Lưu theo tên enum:** lưu tên hằng Java dưới dạng chuỗi, ví dụ PAID.
2. **Lưu theo mã nghiệp vụ:** mỗi hằng enum có một mã ổn định riêng, ví dụ PAID có mã P.
3. **Lưu theo kiểu riêng của database:** dùng kiểu số hoặc native enum type của hệ quản trị, với converter hoặc codec tương ứng.

Mỗi lựa chọn ảnh hưởng đến khả năng đổi tên code, tương thích dữ liệu cũ, khả năng chuyển database và cách kiểm soát dữ liệu không hợp lệ. Không nên chọn chỉ vì cách nào viết ít code nhất; hãy xem giá trị được lưu có phải là một phần của hợp đồng dữ liệu lâu dài hay không.

## 2. Enum trong Java và cột trong database

Ví dụ enum đơn giản:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

Entity:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    private OrderStatus status;
}
~~~

Theo cơ chế chuyển đổi mặc định của Spring Data Relational, enum thường được lưu dưới dạng chuỗi tên hằng enum. Với ví dụ trên, giá trị trong cột status có thể là PENDING, PAID, SHIPPED hoặc CANCELLED.

Khi đọc chuỗi tương ứng, Spring Data chuyển nó về hằng enum. Việc chuyển đổi mặc định dựa trên tên enum, nên tên trong database phải khớp với tên hằng Java.

Một schema minh họa:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
~~~

Ở đây, VARCHAR chứa tên enum. Để bảo vệ dữ liệu trước các luồng ghi khác, có thể thêm CHECK constraint:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_status
CHECK (status IN ('PENDING', 'PAID', 'SHIPPED', 'CANCELLED'));
~~~

Câu lệnh DDL và cú pháp constraint có thể cần điều chỉnh theo hệ quản trị. Điểm quan trọng là mapping enum và schema phải thống nhất về kiểu cột và tập giá trị được phép.

## 3. Lưu enum theo tên hằng Java

### 3.1. Cách hoạt động

Với enum không có converter tùy chỉnh, Spring Data Relational mặc định chuyển enum sang dạng chuỗi tên hằng. Về mặt ý nghĩa, việc chuyển đổi tương đương:

~~~java
String storedValue = status.name();
OrderStatus status = OrderStatus.valueOf(storedValue);
~~~

name() trả về chính xác tên hằng được khai báo trong enum. valueOf() tìm hằng có tên khớp chính xác với chuỗi đầu vào. Việc so khớp phân biệt chữ hoa và chữ thường.

Ví dụ:

| Hằng enum Java | Giá trị chuỗi lưu trong database |
|---|---|
| PENDING | PENDING |
| PAID | PAID |
| SHIPPED | SHIPPED |
| CANCELLED | CANCELLED |

Với enum đơn giản, đây thường là cách dễ triển khai nhất. Không cần viết converter riêng nếu tên hằng Java chính là giá trị muốn lưu.

### 3.2. Ví dụ entity và repository

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}

@Table("orders")
public class Order {
    @Id
    private Long id;

    private OrderStatus status;
}

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

Repository có thể đọc và ghi entity như các kiểu thuộc tính khác:

~~~java
Mono<Order> findOrder(Long id) {
    return orderRepository.findById(id);
}
~~~

Khi lưu một Order có status là PAID, Spring Data chuyển enum thành chuỗi PAID theo quy ước mặc định. Khi đọc, chuỗi đó được chuyển lại thành OrderStatus.PAID.

Không cần gọi name() hoặc valueOf() thủ công ở mọi thao tác repository. Việc chuyển đổi thuộc tính được thực hiện trong mapping/conversion layer.

### 3.3. Ưu điểm

- Code ngắn và dễ hiểu.
- Giá trị trong database có thể đọc trực tiếp mà không cần bảng tra mã.
- Dễ kiểm tra dữ liệu bằng SQL.
- Không phụ thuộc thứ tự khai báo các hằng enum.
- Phù hợp khi tên enum là mã lưu trữ được chấp nhận lâu dài.

### 3.4. Nhược điểm cần cân nhắc

Tên enum trở thành một phần của dữ liệu đã lưu. Nếu đổi tên hằng Java, dữ liệu cũ trong database có thể không còn chuyển đổi được.

Ví dụ, phiên bản đầu có:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Database đang chứa PAID. Sau đó code đổi tên PAID thành PAYMENT_COMPLETED:

~~~java
public enum OrderStatus {
    PENDING,
    PAYMENT_COMPLETED,
    CANCELLED
}
~~~

Khi đọc một hàng cũ có status = PAID, cơ chế chuyển đổi theo tên không tìm thấy hằng PAID và có thể phát sinh lỗi chuyển đổi. Một thay đổi tưởng như chỉ là đổi tên code đã trở thành thay đổi dữ liệu.

Nếu cần đổi tên, hãy lập kế hoạch migration dữ liệu và thời điểm triển khai code. Không nên chỉ sửa tên hằng enum rồi triển khai ngay khi database còn chứa giá trị cũ.

### 3.5. Không nên lưu ordinal chỉ vì enum có thứ tự

Java cung cấp ordinal() để lấy vị trí khai báo của một hằng enum, bắt đầu từ 0:

~~~java
OrderStatus.PENDING.ordinal(); // 0
OrderStatus.PAID.ordinal();    // 1
OrderStatus.SHIPPED.ordinal(); // 2
~~~

Không nên dùng ordinal làm mã lưu trữ bền vững. Nếu thêm một hằng vào giữa hoặc đổi thứ tự khai báo, ordinal của các hằng phía sau thay đổi. Dữ liệu số cũ có thể bị diễn giải thành trạng thái khác mà không báo lỗi.

Ví dụ, database đang lưu số 1 để biểu diễn PAID. Nếu thêm PROCESSING vào trước PAID, ordinal 1 có thể trở thành PROCESSING. Hệ thống có nguy cơ đọc sai trạng thái mà vẫn chạy bình thường.

Nếu nghiệp vụ cần mã số, hãy gán mã rõ ràng cho từng hằng và viết converter. Mã số nghiệp vụ phải độc lập với vị trí khai báo trong enum.

## 4. Lưu enum theo mã nghiệp vụ ổn định

### 4.1. Vì sao nên có mã riêng?

Trong nhiều hệ thống, tên enum Java chỉ là tên dùng trong code. Giá trị lưu trữ có thể là một mã nghiệp vụ được quy định bởi hệ thống khác, ví dụ:

- PENDING được lưu là P.
- PAID được lưu là A.
- SHIPPED được lưu là S.
- CANCELLED được lưu là X.

Mã này có thể ngắn, ổn định và không phụ thuộc tên hằng Java. Nhờ vậy, đội phát triển có thể đổi tên hằng để code rõ nghĩa hơn mà không nhất thiết phải đổi dữ liệu đang lưu.

Mã nghiệp vụ thường xuất hiện trong tích hợp hệ thống, dữ liệu kế thừa, giao thức trao đổi hoặc schema đã được nhiều ứng dụng sử dụng. Trong trường hợp đó, mã cần được xem như một phần của hợp đồng dữ liệu.

### 4.2. Khai báo enum có mã riêng

~~~java
public enum OrderStatus {

    PENDING("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        if (code == null) {
            return null;
        }

        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }

        throw new IllegalArgumentException(
            "Mã OrderStatus không hợp lệ: " + code
        );
    }
}
~~~

Ở đây:

- Tên hằng Java là PENDING, PAID, SHIPPED và CANCELLED.
- Mã lưu trữ là P, A, S và X.
- fromCode() chuyển mã trong database thành enum.
- getCode() cung cấp giá trị cần ghi xuống database.

Mỗi mã phải duy nhất trong enum. Nếu hai hằng có cùng code, việc đọc ngược sẽ trở nên mơ hồ. Trong dự án lớn, có thể kiểm tra tính duy nhất của code trong static initializer hoặc một unit test.

### 4.3. Tạo converter đọc và ghi

Spring Data Relational sử dụng hệ thống conversion để chuyển đổi giữa kiểu trong domain model và kiểu dữ liệu đơn giản mà driver hỗ trợ. Có thể khai báo converter riêng cho hai chiều.

Converter đọc: từ String trong database sang OrderStatus.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStatusReadConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Converter ghi: từ OrderStatus sang String.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWriteConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source == null ? null : source.getCode();
    }
}
~~~

Hai annotation có ý nghĩa:

- @ReadingConverter đánh dấu converter được dùng khi đọc dữ liệu từ store về kiểu domain.
- @WritingConverter đánh dấu converter được dùng khi ghi kiểu domain xuống store.

Việc đánh dấu chiều chuyển đổi đặc biệt hữu ích khi cả hai kiểu đều là kiểu đơn giản hoặc có nhiều converter có thể áp dụng. Nó giúp Spring Data phân biệt converter đọc với converter ghi.

### 4.4. Đăng ký converter trong cấu hình R2DBC

Nếu cấu hình dự án kế thừa AbstractR2dbcConfiguration, có thể đăng ký các converter bằng getCustomConverters():

~~~java
@Configuration
public class DatabaseConfiguration
        extends AbstractR2dbcConfiguration {

    @Override
    protected List<Object> getCustomConverters() {
        return List.of(
            new OrderStatusReadConverter(),
            new OrderStatusWriteConverter()
        );
    }

    // Cung cấp ConnectionFactory theo cấu hình của dự án.
}
~~~

Ví dụ trên chỉ minh họa phần đăng ký converter; lớp cấu hình thực tế còn phải cung cấp ConnectionFactory theo cách dự án đang sử dụng.

Nếu dự án dùng cấu hình Spring Boot hoặc tự khai báo R2dbcCustomConversions, hãy đăng ký cùng các converter trong R2dbcCustomConversions tương ứng với dialect. Tránh tạo nhiều bộ conversion riêng không được mapping context sử dụng.

Sau khi đăng ký, repository và các API mapping entity có thể dùng converter này khi đọc/ghi thuộc tính OrderStatus.

### 4.5. Schema lưu mã nghiệp vụ

Với mã P, A, S, X, cột có thể dùng VARCHAR:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status_code VARCHAR(1) NOT NULL,
    CONSTRAINT ck_orders_status_code
        CHECK (status_code IN ('P', 'A', 'S', 'X'))
);
~~~

Entity ánh xạ tên cột:

~~~java
@Table("orders")
public class Order {
    @Id
    private Long id;

    @Column("status_code")
    private OrderStatus status;
}
~~~

Khi lưu OrderStatus.PAID, converter ghi chuỗi A vào status_code. Khi đọc A, converter trả về OrderStatus.PAID.

Cần đồng bộ cả ba phần:

1. Enum Java định nghĩa mã.
2. Converter chuyển đổi hai chiều.
3. Schema chấp nhận đúng các mã đó.

Nếu enum thêm trạng thái mới nhưng CHECK constraint chưa cho phép mã mới, database sẽ từ chối thao tác ghi. Nếu migration cho phép mã mới nhưng code chưa biết đọc mã đó, thao tác đọc có thể lỗi chuyển đổi.

## 5. Mã nghiệp vụ dạng số

Không bắt buộc mã riêng phải là chuỗi. Nếu hợp đồng dữ liệu yêu cầu mã số, có thể dùng Integer hoặc Short.

Ví dụ:

~~~java
public enum PaymentStatus {
    CREATED(10),
    AUTHORIZED(20),
    SETTLED(30),
    DECLINED(90);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    public int getCode() {
        return code;
    }

    public static PaymentStatus fromCode(Integer code) {
        if (code == null) {
            return null;
        }

        for (PaymentStatus status : values()) {
            if (status.code == code) {
                return status;
            }
        }

        throw new IllegalArgumentException(
            "Mã PaymentStatus không hợp lệ: " + code
        );
    }
}
~~~

Converter đọc từ Integer:

~~~java
@ReadingConverter
public class PaymentStatusReadConverter
        implements Converter<Integer, PaymentStatus> {

    @Override
    public PaymentStatus convert(Integer source) {
        return PaymentStatus.fromCode(source);
    }
}
~~~

Converter ghi sang Integer:

~~~java
@WritingConverter
public class PaymentStatusWriteConverter
        implements Converter<PaymentStatus, Integer> {

    @Override
    public Integer convert(PaymentStatus source) {
        return source == null ? null : source.getCode();
    }
}
~~~

Schema:

~~~sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    status_code INTEGER NOT NULL,
    CONSTRAINT ck_payments_status_code
        CHECK (status_code IN (10, 20, 30, 90))
);
~~~

Các mã 10, 20, 30 và 90 được gán tường minh. Chúng không phải ordinal. Thứ tự khai báo enum có thể thay đổi mà mã lưu trữ vẫn giữ nguyên.

Nếu database dùng SMALLINT, chọn kiểu Java và converter phù hợp với phạm vi số. Ví dụ có thể dùng Short thay cho Integer. Cần kiểm tra kiểu bind mà driver hỗ trợ cho cột thực tế.

## 6. Dùng kiểu enum riêng của database

Một số hệ quản trị cung cấp kiểu enum native. Thay vì lưu giá trị trong VARCHAR hoặc INTEGER, cột được khai báo bằng kiểu enum do database quản lý.

Ví dụ PostgreSQL:

~~~sql
CREATE TYPE order_status AS ENUM (
    'PENDING',
    'PAID',
    'SHIPPED',
    'CANCELLED'
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status order_status NOT NULL
);
~~~

Ưu điểm:

- Database biết tập giá trị hợp lệ của kiểu.
- Cột thể hiện rõ miền giá trị trong schema.
- Các thao tác SQL có thể dùng trực tiếp các nhãn enum.
- Không phải lặp lại CHECK constraint ở từng bảng nếu cùng dùng một kiểu native.

Tuy nhiên, native enum gắn với hệ quản trị và có thể làm việc chuyển database khó hơn. Cách thêm, đổi tên hoặc xóa nhãn enum khác nhau giữa các database và phiên bản.

### 6.1. Converter và driver codec không phải lúc nào cũng thay thế nhau

Có thể viết converter để chuyển enum Java sang String, nhưng điều đó chưa chắc đủ để ghi vào một cột native enum.

R2DBC driver chịu trách nhiệm bind giá trị tham số theo kiểu mà database hiểu. Với PostgreSQL native enum, driver có thể cần codec hoặc cấu hình riêng để nhận biết kiểu enum tùy chỉnh. Nếu tham số được bind như VARCHAR trong khi database chờ kiểu order_status, câu lệnh có thể gặp lỗi không tương thích kiểu hoặc cần cast rõ ràng.

Vì vậy, khi dùng native enum:

1. Kiểm tra tài liệu của R2DBC driver đang dùng về kiểu enum tùy chỉnh.
2. Xác định driver cần codec đăng ký cho kiểu database hay không.
3. Kiểm tra cách tham số được bind trong INSERT/UPDATE.
4. Kiểm tra kết quả đọc được chuyển về kiểu Java như thế nào.
5. Viết integration test với chính database và driver triển khai.

Không nên giả định @Column hoặc một Converter<String, OrderStatus> tự động cấu hình codec ở tầng driver. Mapping của Spring Data và codec của R2DBC driver là hai lớp khác nhau.

### 6.2. Native enum có phù hợp với mọi dự án không?

Native enum có thể phù hợp khi:

- Dự án cam kết dùng một hệ quản trị cụ thể.
- Tập giá trị ít thay đổi và cần được database bảo vệ trực tiếp.
- Đội vận hành quen với migration của kiểu enum native.
- Driver R2DBC hỗ trợ tốt việc bind và đọc kiểu đó.

VARCHAR kèm CHECK thường linh hoạt hơn khi cần hỗ trợ nhiều database hoặc thường xuyên mở rộng schema. Mã nghiệp vụ trong VARCHAR/INTEGER phù hợp khi giá trị lưu là hợp đồng tích hợp ổn định, không nhất thiết trùng tên enum Java.

## 7. So sánh các cách lưu enum

| Cách lưu | Giá trị ví dụ | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|---|
| Tên enum | PAID | Đơn giản, dễ đọc, không cần converter riêng | Đổi tên hằng có thể làm hỏng dữ liệu cũ |
| Ordinal | 1 | Gọn, biểu diễn số | Phụ thuộc thứ tự khai báo; dễ diễn giải sai |
| Mã nghiệp vụ dạng chuỗi | A | Ổn định với tên code Java, phù hợp tích hợp | Cần converter và quản lý tập mã |
| Mã nghiệp vụ dạng số | 20 | Gọn, có thể khớp hợp đồng hệ thống cũ | Cần converter và tài liệu hóa ý nghĩa mã |
| Native enum database | PAID với kiểu order_status | Database kiểm soát tập giá trị | Phụ thuộc database và driver codec |

Một cách chọn thực tế:

- Dùng tên enum nếu tên hằng Java có thể được giữ ổn định và database chỉ phục vụ ứng dụng này.
- Dùng mã nghiệp vụ nếu giá trị lưu đã là một hợp đồng cần tồn tại độc lập với tên code Java.
- Dùng native enum khi muốn tận dụng kiểu dữ liệu riêng của database và chấp nhận phụ thuộc hệ quản trị.
- Không dùng ordinal làm mã lưu trữ lâu dài.

## 8. Xử lý mã không hợp lệ hoặc không còn được hỗ trợ

Dữ liệu trong database có thể đến từ phiên bản ứng dụng cũ, script quản trị, hệ thống tích hợp hoặc thao tác thủ công. Vì vậy, converter cần có chiến lược rõ ràng khi gặp giá trị không biết.

Ví dụ, database chứa status_code = Z nhưng enum hiện tại không định nghĩa mã Z. Nếu fromCode() ném IllegalArgumentException, lỗi chuyển đổi sẽ đi vào reactive pipeline như lỗi đọc dữ liệu. Tùy lớp mapping và driver, lỗi có thể được bọc trong exception khác.

Có hai hướng xử lý:

### 8.1. Từ chối mã không hợp lệ

~~~java
public static OrderStatus fromCode(String code) {
    for (OrderStatus status : values()) {
        if (status.code.equals(code)) {
            return status;
        }
    }

    throw new IllegalArgumentException(
        "Mã trạng thái không được hỗ trợ: " + code
    );
}
~~~

Phù hợp khi mọi mã lưu trữ phải được ứng dụng hiểu. Lỗi giúp phát hiện dữ liệu sai hoặc thiếu migration sớm.

### 8.2. Có hằng UNKNOWN nếu nghiệp vụ cho phép

~~~java
public enum OrderStatus {
    PENDING("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X"),
    UNKNOWN("?");

    // code và fromCode được định nghĩa theo quy tắc của ứng dụng
}
~~~

Nếu chọn fallback UNKNOWN, cần quyết định rõ:

- UNKNOWN có được phép ghi xuống database không?
- Khi đọc mã lạ, ứng dụng có được tiếp tục xử lý hay chỉ hiển thị?
- Có cần log/metric để đội vận hành phát hiện mã mới không?
- Những thao tác nghiệp vụ nào phải bị chặn khi trạng thái không rõ?

Không nên tự động chuyển mọi mã lạ thành PENDING hoặc một trạng thái mặc định có ý nghĩa nghiệp vụ. Cách đó có thể khiến ứng dụng xử lý sai đơn hàng hoặc thanh toán mà không nhận ra dữ liệu đã bất thường.

## 9. Đổi tên enum và thay đổi mã cần migration

### 9.1. Đổi tên hằng khi lưu theo tên

Giả sử dữ liệu cũ chứa PAID và code muốn đổi thành PAYMENT_COMPLETED. Cần chuyển dữ liệu:

~~~sql
UPDATE orders
SET status = 'PAYMENT_COMPLETED'
WHERE status = 'PAID';
~~~

Sau đó triển khai code mới có hằng PAYMENT_COMPLETED. Trình tự triển khai cần được cân nhắc nếu nhiều phiên bản ứng dụng cùng chạy trong thời gian rollout.

Một quy trình an toàn hơn khi có nhiều instance:

1. Triển khai phiên bản trung gian có thể đọc cả PAID và PAYMENT_COMPLETED.
2. Chuyển dữ liệu cũ sang giá trị mới bằng migration.
3. Bắt đầu ghi giá trị mới sau khi các instance tương thích đã được triển khai.
4. Khi chắc chắn không còn dữ liệu hoặc instance dùng PAID, loại bỏ hỗ trợ mã cũ.

Chi tiết phụ thuộc chiến lược triển khai, khả năng tương thích ngược và cách converter được thiết kế.

### 9.2. Đổi mã nghiệp vụ

Nếu enum có code riêng, đổi tên hằng Java không nhất thiết cần migration:

~~~java
public enum OrderStatus {
    WAITING_FOR_PAYMENT("P"),
    PAID("A"),
    SHIPPED("S"),
    CANCELLED("X");
}
~~~

Nếu WAITING_FOR_PAYMENT vẫn giữ code P, dữ liệu hiện tại có thể tiếp tục đọc được. Nhưng nếu thay code P thành N, database và các hệ thống tích hợp đang dùng P cần được chuyển đổi có kế hoạch.

Mã nghiệp vụ cần được quản lý như hợp đồng dữ liệu: không tái sử dụng mã cũ cho ý nghĩa mới, không đổi mã tùy tiện và cần ghi nhận migration khi thay đổi.

### 9.3. Thêm trạng thái mới

Khi thêm REFUNDED với mã R:

- Thêm hằng enum và converter nhận mã R.
- Cập nhật CHECK constraint để cho phép R, hoặc cập nhật native enum type.
- Triển khai code đọc được R trước khi có luồng ghi R.
- Chỉ bắt đầu ghi R sau khi các phiên bản ứng dụng đang chạy có thể đọc được mã đó.

Nếu code mới ghi R nhưng một instance cũ vẫn đọc cùng bảng và không biết R, instance cũ có thể lỗi khi truy vấn hàng mới. Đây là lý do phải xem xét tương thích giữa các phiên bản trong rollout.

## 10. Enum trong database không quyết định JSON API

Giá trị enum được lưu xuống database và giá trị enum được trả về trong JSON API là hai việc riêng biệt.

Ví dụ, một enum có thể được lưu bằng code A nhưng API trả về chuỗi PAID hoặc một object gồm code và label. Cách serialize JSON thường do Jackson hoặc thư viện web khác quyết định, không phải R2DBC converter.

Ví dụ enum:

~~~java
public enum OrderStatus {
    PENDING("P", "Chờ thanh toán"),
    PAID("A", "Đã thanh toán");

    private final String code;
    private final String label;

    OrderStatus(String code, String label) {
        this.code = code;
        this.label = label;
    }

    public String getCode() {
        return code;
    }

    public String getLabel() {
        return label;
    }
}
~~~

Converter R2DBC có thể chỉ lưu code. API có thể trả code, tên enum hoặc DTO riêng tùy hợp đồng endpoint. Không nên giả định rằng việc thêm converter database tự thay đổi JSON serialization.

Nếu API công khai dùng mã ổn định, hãy thiết kế DTO hoặc cấu hình JSON riêng để hợp đồng API được quản lý độc lập với cách lưu dữ liệu.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Enum mặc định luôn lưu ordinal | Spring Data Relational mặc định chuyển enum theo tên chuỗi; ordinal không nên dùng làm mã bền vững |
| Đổi tên hằng enum chỉ ảnh hưởng code Java | Nếu lưu theo tên, dữ liệu cũ có thể không chuyển đổi được |
| Có field code trong enum thì Spring tự lưu field đó | Cần converter đọc và ghi để dùng mã riêng |
| Chỉ cần converter ghi | Cần converter đọc tương ứng để chuyển dữ liệu database về enum |
| @Enumerated của JPA là cách cấu hình enum trong R2DBC | Spring Data Relational dùng conversion service và custom converters; không dựa vào JPA mapping annotation |
| @Column quyết định kiểu enum native | @Column chỉ chỉ định tên cột; kiểu và codec do schema/driver quyết định |
| Converter String sang enum tự cấu hình PostgreSQL native enum | Driver có thể cần codec hoặc cấu hình kiểu riêng |
| Mã không biết có thể tự chuyển thành trạng thái mặc định | Cần chính sách rõ ràng: từ chối, UNKNOWN hoặc xử lý tương thích có kiểm soát |
| Giá trị enum database quyết định JSON API | Database conversion và JSON serialization là hai lớp riêng |

## 12. Quy trình thiết kế enum mapping

Khi thêm thuộc tính enum vào entity, hãy đi theo các bước:

1. Xác định enum chỉ dùng nội bộ hay giá trị lưu là một hợp đồng với hệ thống khác.
2. Nếu tên hằng Java ổn định, cân nhắc dùng mapping mặc định dạng String.
3. Nếu cần mã nghiệp vụ, gán code tường minh cho từng hằng; không dùng ordinal.
4. Chọn kiểu cột phù hợp: VARCHAR, INTEGER/SMALLINT hoặc native enum.
5. Nếu dùng code riêng, viết converter cho cả chiều đọc và ghi.
6. Đăng ký converter trong R2dbcCustomConversions hoặc cấu hình AbstractR2dbcConfiguration phù hợp.
7. Nếu dùng native enum, kiểm tra codec và cách bind của R2DBC driver.
8. Thêm CHECK constraint hoặc native type để database bảo vệ tập giá trị hợp lệ khi phù hợp.
9. Xác định cách xử lý mã lạ và dữ liệu cũ.
10. Viết migration cho thay đổi mã, tập giá trị hoặc kiểu cột.
11. Kiểm tra thao tác insert, select, update và giá trị không hợp lệ với database/driver thật.
12. Xem xét tương thích khi nhiều phiên bản ứng dụng cùng chạy trong rollout.

## 13. Bài tập tự kiểm tra

### Bài 1: Mapping mặc định

Một enum có các hằng NEW, PROCESSING và DONE. Nếu dùng mapping mặc định của Spring Data Relational, giá trị được lưu thường là gì?

Gợi ý: Các chuỗi NEW, PROCESSING và DONE. Không phải 0, 1, 2 theo ordinal.

### Bài 2: Đổi tên hằng

Database đang lưu PROCESSING. Bạn đổi tên hằng Java thành IN_PROGRESS. Điều gì có thể xảy ra?

Gợi ý: Cơ chế chuyển đổi theo tên không tìm thấy PROCESSING và phát sinh lỗi khi đọc. Cần migration hoặc converter tương thích với giá trị cũ.

### Bài 3: Mã nghiệp vụ

Một hệ thống đối tác quy định trạng thái PAID phải được lưu thành mã A. Hãy nêu các phần cần triển khai.

Gợi ý: Enum có code A, converter đọc String sang enum, converter ghi enum sang String, đăng ký cả hai converter, và schema có cột phù hợp cùng CHECK constraint nếu cần.

### Bài 4: Mã số

Bạn muốn lưu trạng thái bằng 10, 20, 30. Vì sao không nên dùng ordinal?

Gợi ý: Ordinal phụ thuộc vị trí khai báo. Hãy gán mã số tường minh vào enum và dùng Converter<Enum, Integer> cùng Converter<Integer, Enum>.

### Bài 5: Native enum

Database dùng PostgreSQL native enum nhưng converter đã chuyển enum Java thành String. Vì sao vẫn có thể gặp lỗi khi ghi?

Gợi ý: Driver có thể bind tham số dưới kiểu VARCHAR trong khi cột yêu cầu kiểu native enum. Cần kiểm tra codec hoặc cấu hình driver và thử với database thực tế.

### Bài 6: Giá trị lạ

Database chứa mã trạng thái Z nhưng enum hiện tại không biết mã này. Nên làm gì?

Gợi ý: Quyết định rõ có từ chối dữ liệu hay ánh xạ sang UNKNOWN. Không tự chuyển sang một trạng thái nghiệp vụ khác. Ghi nhận lỗi hoặc metric để phát hiện dữ liệu ngoài hợp đồng.

## 14. Ghi nhớ khi ánh xạ enum trong Spring Data Relational R2DBC

- Enum mặc định thường được lưu theo tên hằng dưới dạng chuỗi.
- Đổi tên hằng có thể làm dữ liệu cũ không đọc được nếu database vẫn lưu tên cũ.
- Mã nghiệp vụ riêng giúp tách hợp đồng lưu trữ khỏi tên enum Java.
- Dùng @ReadingConverter và @WritingConverter để chuyển đổi hai chiều.
- Đăng ký converter trong R2dbcCustomConversions hoặc cấu hình Spring Data R2DBC tương ứng.
- Không dùng ordinal làm mã lưu trữ bền vững; hãy gán mã tường minh nếu cần số.
- Native enum type phụ thuộc database và R2DBC driver; converter không thay thế codec của driver.
- Dùng CHECK constraint hoặc kiểu native để kiểm soát tập giá trị ở database khi phù hợp.
- Xác định cách xử lý mã lạ, migration và tương thích khi triển khai nhiều phiên bản.
- Cách lưu enum trong database độc lập với cách enum được serialize thành JSON API.

Khi thiết kế enum, hãy xác định giá trị nào thực sự được lưu và ai phụ thuộc vào giá trị đó. Nếu tên enum là hợp đồng đủ ổn định, mapping mặc định giúp code đơn giản. Nếu mã lưu cần tồn tại độc lập với tên Java hoặc được chia sẻ với hệ thống khác, hãy dùng mã nghiệp vụ và converter rõ ràng. Với native enum, cần kiểm tra cả schema lẫn khả năng bind/đọc của driver R2DBC.

