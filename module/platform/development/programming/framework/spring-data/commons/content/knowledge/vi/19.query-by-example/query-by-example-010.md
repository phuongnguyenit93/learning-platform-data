# Phân biệt đối tượng mẫu của truy vấn với entity được phép ghi

Query by Example (QBE) dùng một đối tượng mẫu, gọi là **probe**, để diễn tả các giá trị cần tìm. Probe thường có cùng kiểu Java với entity mà repository quản lý. Chính sự giống nhau về kiểu này dễ dẫn đến một nhầm lẫn nguy hiểm: đối tượng dùng để tìm kiếm có thể được đưa vào luồng ghi như thể nó là một entity đầy đủ, hợp lệ và đã được cấp quyền cập nhật.

Trong Spring Data Commons, `Example<T>` và `ExampleMatcher` mô tả truy vấn. Chúng không xác nhận tính hợp lệ của một thao tác ghi, không cấp quyền sửa dữ liệu và không biến probe thành một đối tượng chỉ đọc. Bài học này làm rõ ranh giới đó để tổ chức luồng tìm kiếm và luồng ghi qua repository đúng trách nhiệm, có tính đến vòng đời đối tượng của từng store.

## 1. Cùng kiểu Java nhưng khác vai trò

Giả sử repository quản lý `Customer`. Một yêu cầu tìm kiếm chỉ có tên và trạng thái hoạt động có thể được chuyển thành:

```java
Customer probe = new Customer();
probe.setName("Linh");
probe.setActive(Boolean.TRUE);

Example<Customer> example = Example.of(probe);
```

Đối tượng này có thể thiếu định danh, thông tin bắt buộc khi tạo mới, phiên bản dùng cho optimistic locking hoặc những giá trị phải giữ nguyên khi cập nhật. Việc thiếu những thông tin đó có thể hoàn toàn hợp lý đối với một truy vấn.

Trong khi đó, entity đưa vào luồng ghi phải đáp ứng yêu cầu của thao tác cụ thể. Tạo mới và cập nhật cũng có những yêu cầu khác nhau.

| Đối tượng hoặc vai trò | Mục đích | Điều không thể tự suy ra |
| --- | --- | --- |
| DTO bộ lọc | Nhận các tiêu chí tìm kiếm được cho phép | Không phải dữ liệu đủ để tạo hay cập nhật entity |
| Probe kiểu `Customer` | Cung cấp giá trị mẫu cho QBE | Không chứng minh entity hợp lệ để ghi |
| `Example<Customer>` | Kết hợp probe với cách đối sánh | Không cấp quyền ghi và không khóa probe |
| Entity đọc từ repository | Biểu diễn dữ liệu đã đọc theo mapping của store | Không tự chứng minh người gọi được phép sửa |
| Entity chuẩn bị để tạo mới | Chứa trạng thái ban đầu theo nghiệp vụ | Không hợp lệ chỉ vì được khởi tạo bằng `new` |
| Entity được cập nhật có kiểm soát | Chứa thay đổi đã qua kiểm tra phù hợp | Vẫn cần cơ chế ghi và kiểm soát đồng thời của store |

“Được phép ghi” bao gồm ít nhất ba khía cạnh: thao tác được nghiệp vụ cho phép, người gọi có quyền thực hiện và trạng thái đối tượng phù hợp với cơ chế lưu trữ. Compiler không kiểm tra ba điều này chỉ qua kiểu `Customer`.

## 2. `Example` không tạo bản sao sâu và không bảo vệ probe

Có thể xem `Example` như một cấu hình truy vấn gồm probe và matcher. Không được coi `Example.of(...)` là thao tác tạo snapshot sâu của toàn bộ entity.

```java
Customer probe = new Customer();
probe.setCity("Hà Nội");

Example<Customer> example = Example.of(probe);

// Làm thay đổi chính đối tượng mà example giữ tham chiếu.
probe.setCity("Đà Nẵng");
```

Trong API `Example`, `getProbe()` cho phép lấy lại probe. Vì vậy, dù cấu hình `Example` và `ExampleMatcher` có tính bất biến, một probe mutable vẫn có thể bị thay đổi thông qua tham chiếu của nó. Việc thay đổi giá trị trước khi repository dựng truy vấn có thể làm thay đổi tiêu chí thực tế.

Thực hành phù hợp là:

- Tạo probe riêng cho mỗi lần tìm kiếm.
- Hoàn tất việc gán giá trị trước khi tạo và thực thi `Example`.
- Không dùng probe như một đối tượng trạng thái dùng chung giữa các request.
- Không đưa probe sang service tạo mới hoặc cập nhật.
- Chỉ tái sử dụng matcher khi cấu hình và các callback của nó an toàn để dùng chung.

Không nên tìm cách “đánh dấu read-only” bằng cách bọc entity trong `Example`. Abstraction này không có mục đích bảo vệ các setter hay ngăn `save(...)` nhận entity.

## 3. Vì sao `save(probe)` có thể gây hậu quả khác dự định?

Xét đoạn mã:

```java
Customer probe = new Customer();
probe.setCity("Đà Nẵng");

Iterable<Customer> matches = repository.findAll(Example.of(probe));

// Sai trách nhiệm: probe chỉ chứa một tiêu chí tìm kiếm.
repository.save(probe);
```

Lời gọi `save` không biết rằng biến có tên `probe` và được tạo ra cho tìm kiếm. Nó nhận một entity có kiểu phù hợp với repository rồi xử lý theo mapping, cơ chế xác định trạng thái mới và hành vi lưu của implementation.

Các hậu quả có thể gặp gồm:

- Chèn một bản ghi mới chỉ có vài giá trị tìm kiếm.
- Bị từ chối do thiếu trường bắt buộc hoặc vi phạm ràng buộc.
- Cập nhật hay thay thế dữ liệu hiện có nếu đối tượng mang định danh tương ứng.
- Làm mất dữ liệu ở những thuộc tính không có trong biểu mẫu tìm kiếm, tùy cơ chế ghi của store.

Không được giả định rằng thuộc tính `null` trong một entity đưa vào `save(...)` luôn có nghĩa “giữ nguyên giá trị cũ”. `save(...)` không phải một hợp đồng chung cho thao tác PATCH theo các trường khác null. Cách xử lý null, aggregate và các đối tượng liên quan phụ thuộc store cùng mapping.

### 3.1. Có định danh không đồng nghĩa được cấp quyền cập nhật

Định danh là dữ liệu phục vụ nhận diện entity. Nó không chứng minh rằng:

- Bản ghi vẫn tồn tại tại thời điểm ghi.
- Người gọi thuộc đúng phạm vi dữ liệu của bản ghi.
- Người gọi có quyền sửa các thuộc tính đang thay đổi.
- Trạng thái nghiệp vụ hiện tại cho phép cập nhật.
- Đối tượng có phiên bản phù hợp để tránh ghi đè thay đổi đồng thời.

Tương tự, `id == null` không tự chứng minh entity là một yêu cầu tạo mới hợp lệ.

Spring Data có các abstraction và chiến lược để xác định entity mới, bao gồm những cơ chế liên quan đến metadata, định danh, phiên bản hoặc `Persistable.isNew()`. Cách dùng cụ thể thuộc từng module và cấu hình. Không xây quy tắc quyền ghi dựa trên một công thức chung như “có ID thì chắc chắn update được”.

### 3.2. Bỏ qua ID khi đối sánh không xóa ID khỏi entity

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "version");
```

Cấu hình trên chỉ nói rằng các property path đó không tham gia đối sánh QBE. Nó không xóa giá trị `id`, không bỏ phiên bản khỏi đối tượng và không thay đổi cách một lời gọi `save(probe)` sẽ xử lý entity.

Cùng nguyên tắc này áp dụng cho những trường bị bỏ qua khác: “không tham gia truy vấn” là cấu hình đọc, không phải chính sách bảo vệ ghi.

## 4. Cảnh giác khi dùng entity đã đọc làm probe

Một cách tái sử dụng đối tượng có vẻ tiện lợi là đọc entity rồi thay vài trường để dùng làm mẫu:

```java
Customer customer = repository.findById(customerId)
    .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy"));

// Thay đổi một entity đã đọc chỉ để chuẩn bị bộ lọc.
customer.setCity("Đà Nẵng");

Example<Customer> example = Example.of(customer);
```

Cách làm này có hai vấn đề độc lập.

Thứ nhất, probe có thể mang quá nhiều tiêu chí: ID, phiên bản, tên, tenant, trạng thái và các giá trị khác được đọc từ kho dữ liệu. Kết quả tìm kiếm sẽ chịu những thuộc tính có giá trị mà matcher chưa loại bỏ.

Thứ hai, việc gọi setter có thể tác động đến cơ chế theo dõi thay đổi của store.

| Bối cảnh | Điều cần hiểu |
| --- | --- |
| JPA với entity còn managed trong persistence context | Sửa thuộc tính có thể được dirty checking phát hiện và được ghi khi flush hoặc commit, dù không gọi `save` riêng |
| JPA với entity detached | Không có cùng hành vi tự flush của entity managed; đưa entity vào luồng merge hoặc save vẫn có thể mang theo thay đổi ngoài ý muốn |
| Store thường trả về đối tượng materialized như MongoDB | Không suy ra cơ chế dirty checking giống JPA; vẫn có rủi ro nếu đối tượng sửa đổi bị truyền tiếp vào thao tác ghi |
| Module khác hoặc custom repository | Phải hiểu hợp đồng vòng đời và lưu của implementation thực tế |

Đối với JPA, chú ý phạm vi giao dịch và persistence context khi xác định entity còn managed hay không. Chỉ nhìn vào việc “đối tượng vừa được repository trả về” chưa đủ để kết luận trong mọi cấu hình ứng dụng.

Một giao dịch được khai báo `readOnly` cũng không phải cơ chế cấp quyền ghi dùng chung cho mọi store. Hiệu quả của nó phụ thuộc transaction manager, provider và cấu hình; không dùng nó để biện minh cho việc sửa entity nhằm dựng bộ lọc.

Giải pháp rõ ràng hơn là tạo một probe mới từ bộ lọc được cho phép, thay vì biến entity đang dùng cho nghiệp vụ thành đối tượng tìm kiếm.

## 5. Tách bộ lọc, probe và lệnh ghi trong thiết kế

Một luồng dễ kiểm soát có thể tổ chức như sau:

```text
Yêu cầu tìm kiếm
    -> DTO bộ lọc
    -> tạo probe riêng + matcher
    -> Example
    -> repository hỗ trợ QBE
    -> kết quả đọc

Yêu cầu thay đổi dữ liệu
    -> DTO lệnh ghi
    -> kiểm tra quyền và quy tắc nghiệp vụ
    -> tạo entity mới hoặc nạp entity cần sửa
    -> thay đổi những thuộc tính được cho phép
    -> thao tác ghi theo cơ chế của store
```

DTO bộ lọc và DTO lệnh ghi có thể chứa một số trường giống nhau, nhưng không nên bị đồng nhất chỉ để tái sử dụng một lớp.

Ví dụ, `active = null` trong bộ lọc có thể nghĩa là không lọc theo trạng thái. Trong lệnh cập nhật, `active = null` cần một hợp đồng riêng: từ chối, giữ nguyên hay xóa giá trị nếu miền nghiệp vụ cho phép. Không sao chép ngữ nghĩa của QBE sang thao tác ghi.

Việc dùng kiểu DTO riêng cũng giúp giới hạn các trường được nhận từ người dùng. Tuy nhiên, DTO không thay thế kiểm tra quyền, validation hay ràng buộc dữ liệu. Nếu một hàm vẫn sao chép mọi trường từ DTO vào entity một cách thiếu kiểm soát, ranh giới trách nhiệm vẫn bị phá vỡ.

## 6. Ví dụ: dựng probe riêng cho màn hình tìm khách hàng

Ví dụ dưới đây minh họa API chung của Spring Data Commons. Khi sử dụng với store cụ thể, cần bổ sung mapping và các yêu cầu về entity mà module đó quy định.

### 6.1. Entity và các giá trị được phép lọc

Giả sử mô hình `Customer` có các thuộc tính sau:

| Thuộc tính | Kiểu | Vai trò trong ví dụ |
| --- | --- | --- |
| `id` | `String` | Định danh do luồng ghi quản lý |
| `version` | `Long` | Giá trị dành cho cơ chế phiên bản nếu store được cấu hình hỗ trợ |
| `tenantId` | `String` | Phạm vi dữ liệu lấy từ ngữ cảnh tin cậy |
| `name` | `String` | Tiêu chí tìm theo tiền tố |
| `city` | `String` | Tiêu chí đối sánh chính xác |
| `active` | `Boolean` | `null` là không lọc, `true` hoặc `false` là có lọc |

Tên thuộc tính `version` tự nó không kích hoạt optimistic locking. Mapping hoặc annotation tương ứng phải được store hỗ trợ và cấu hình đúng.

Phần Java tối thiểu để hiểu các đoạn mã tiếp theo:

```java
public class Customer {

    private String id;
    private Long version;
    private String tenantId;
    private String name;
    private String city;
    private Boolean active;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public Boolean getActive() { return active; }
    public void setActive(Boolean active) { this.active = active; }
}
```

Các setter dùng để minh họa việc gán probe. Một domain model thực tế có thể hạn chế setter và cung cấp phương thức nghiệp vụ để bảo vệ các bất biến khi ghi.

Bộ lọc chỉ nhận ba giá trị người dùng được phép điều khiển:

```java
public final class CustomerFilter {

    private final String name;
    private final String city;
    private final Boolean active;

    public CustomerFilter(String name, String city, Boolean active) {
        this.name = name;
        this.city = city;
        this.active = active;
    }

    public String getName() { return name; }
    public String getCity() { return city; }
    public Boolean getActive() { return active; }
}
```

Không có `id`, `version` hay `tenantId` trong DTO bộ lọc này. Đây là lựa chọn cho màn hình đang xét, không phải quy tắc rằng mọi truy vấn QBE đều phải bỏ ID. Nếu một trường hợp sử dụng cho phép tìm theo ID, cần thiết kế tiêu chí đó một cách tường minh.

### 6.2. Factory chỉ tạo `Example`, không ghi dữ liệu

```java
import java.util.Objects;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.ExampleMatcher.GenericPropertyMatchers;

public final class CustomerExamples {

    private CustomerExamples() {
    }

    public static Example<Customer> fromFilter(
            CustomerFilter filter,
            String trustedTenantId) {

        Objects.requireNonNull(filter, "filter không được null");

        if (trustedTenantId == null || trustedTenantId.trim().isEmpty()) {
            throw new IllegalArgumentException("Thiếu tenant tin cậy");
        }

        Customer probe = new Customer();
        probe.setTenantId(trustedTenantId);
        probe.setName(trimToNull(filter.getName()));
        probe.setCity(trimToNull(filter.getCity()));
        probe.setActive(filter.getActive());

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnorePaths("id", "version")
            .withIgnoreNullValues()
            .withMatcher("tenantId", GenericPropertyMatchers.exact())
            .withMatcher(
                "name",
                GenericPropertyMatchers.startsWith().ignoreCase()
            )
            .withMatcher("city", GenericPropertyMatchers.exact());

        return Example.of(probe, matcher);
    }

    private static String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
```

Factory có một số đặc điểm có chủ ý:

- Mỗi lần gọi tạo một `Customer` mới, không sửa entity lấy từ repository.
- Chỉ các trường trong danh sách cho phép được sao chép vào probe.
- `Boolean` giữ được ba trạng thái: không lọc, lọc `true` và lọc `false`.
- Những chuỗi trống sau trim được chuyển thành `null`, kết hợp với chính sách bỏ qua null.
- `id` và `version` bị bỏ qua khi đối sánh, đồng thời không được gán từ đầu vào tìm kiếm.
- `tenantId` được yêu cầu từ ngữ cảnh tin cậy và tham gia đối sánh cùng các tiêu chí khác.

Tham số có tên `trustedTenantId` chỉ mô tả hợp đồng. Code gọi phải thực sự lấy nó từ nguồn đáng tin, chẳng hạn ngữ cảnh xác thực của ứng dụng. Đổi tên một tham số người dùng gửi lên thành “trusted” không làm nó trở nên tin cậy.

Không thay `matchingAll()` bằng `matchingAny()` một cách máy móc. Nếu tenant là một tiêu chí QBE bình thường, cách ghép OR có thể tạo ý nghĩa như:

```text
thuộc tenant hiện tại HOẶC có tên bắt đầu bằng "Linh"
```

Điều đó khác hẳn yêu cầu giới hạn dữ liệu theo tenant rồi mới lọc tên. Nếu nghiệp vụ cần nhóm điều kiện phức tạp mà QBE không diễn đạt đúng, phải chọn cơ chế truy vấn khác của store. Kiểm soát phạm vi dữ liệu cần được áp dụng nhất quán trên các đường truy cập, không chỉ trong một factory.

### 6.3. Chỉ chuyển `Example` vào thao tác đọc

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, String>,
                QueryByExampleExecutor<Customer> {
}
```

Cách dùng trong luồng tìm kiếm:

```java
CustomerFilter filter = new CustomerFilter(
    " Linh ",
    "Đà Nẵng",
    Boolean.FALSE
);

Example<Customer> example = CustomerExamples.fromFilter(
    filter,
    currentTenantId
);

Iterable<Customer> customers = repository.findAll(example);
```

`repository` là repository do ứng dụng cung cấp, còn `currentTenantId` đã được xác định từ ngữ cảnh tin cậy. Store phải hỗ trợ QBE và các cách đối sánh được dùng; chỉ khai báo interface không tự bổ sung khả năng cho một implementation chưa hỗ trợ.

Trong ví dụ này, `active = false` là một tiêu chí có chủ ý. Nếu DTO dùng primitive `boolean`, giá trị mặc định `false` có thể vô tình trở thành bộ lọc ngay cả khi người dùng không chọn trạng thái.

Nếu ba tiêu chí tùy chọn đều vắng mặt, truy vấn vẫn còn phạm vi tenant. Nó có thể trả nhiều bản ghi trong tenant đó. Ứng dụng cần quyết định có cho phép tìm rộng như vậy không và dùng phân trang hoặc giới hạn thích hợp theo khả năng của store.

## 7. Luồng cập nhật phải có hợp đồng riêng

Xét một yêu cầu đổi thành phố của khách hàng. Luồng cập nhật cần nhận định danh mục tiêu và giá trị thay đổi qua một lệnh riêng, thay vì tái sử dụng `CustomerFilter` hay lấy probe từ `Example`.

Mã dưới đây minh họa trình tự ở tầng service; các biến `command`, `actor` và `writePolicy` đại diện cho DTO lệnh, ngữ cảnh người gọi và chính sách ghi của ứng dụng:

```java
Customer customer = repository.findById(command.getCustomerId())
    .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy"));

writePolicy.requireCanEdit(actor, customer);

String newCity = validateAndNormalizeCity(command.getNewCity());
customer.setCity(newCity);

Customer saved = repository.save(customer);
```

Ở đây `validateAndNormalizeCity(...)` phải thực thi hợp đồng của lệnh cập nhật, chẳng hạn từ chối thành phố trống nếu nghiệp vụ không cho phép. Không mặc định dùng helper `trimToNull(...)` của bộ lọc, vì hai trường hợp có thể có quy tắc hoàn toàn khác nhau.

Những yêu cầu quan trọng của luồng này gồm:

- Nạp đúng mục tiêu và kiểm tra quyền trên dữ liệu thực tế trước khi sửa.
- Chỉ thay đổi thuộc tính mà lệnh được phép điều khiển.
- Giữ những dữ liệu khác của entity theo quy tắc nghiệp vụ.
- Đặt phạm vi giao dịch phù hợp với store và tính nhất quán cần đạt.
- Dùng cơ chế kiểm soát đồng thời như optimistic locking nếu store hỗ trợ và bài toán yêu cầu.

Đọc entity rồi gọi `save` không tự giải quyết mọi xung đột đồng thời. Một kiểm tra phiên bản đơn thuần ở Java cũng không thay thế điều kiện cập nhật có kiểm soát hoặc cơ chế phiên bản của store.

Hợp đồng `CrudRepository.save(...)` cho phép kết quả trả về khác instance đầu vào. Vì vậy, sử dụng `saved` cho dữ liệu cần trả về hoặc xử lý tiếp, thay vì giả định rằng `customer` luôn được cập nhật đầy đủ định danh, phiên bản và các giá trị do cơ chế lưu tạo ra.

Trong JPA, entity managed còn có thể được đồng bộ bằng dirty checking trong giao dịch. Chi tiết việc có cần lời gọi `save` tường minh ở một luồng cụ thể thuộc thiết kế và cơ chế của module JPA; Spring Data Commons không định nghĩa một vòng đời managed entity chung cho mọi store.

## 8. Kết quả tìm kiếm cũng không tự mang quyền ghi

Probe và kết quả truy vấn là hai nhóm đối tượng khác nhau. Không dùng probe để ghi là chưa đủ nếu code lại sửa trực tiếp mọi entity trả về từ truy vấn mà không có một lệnh nghiệp vụ rõ ràng.

Ví dụ:

```java
for (Customer customer : repository.findAll(example)) {
    customer.setActive(Boolean.FALSE);
}
```

Trong một persistence context JPA còn quản lý các entity này, vòng lặp có thể tạo ra thay đổi được flush. Với store không có cùng cơ chế theo dõi, nó vẫn sửa các đối tượng trong bộ nhớ và có thể bị lưu ở một bước sau.

Nếu màn hình chỉ cần hiển thị, có thể chuyển kết quả sang DTO đầu ra hoặc dùng projection mà store hỗ trợ. Điều đó giảm việc đưa entity có setter xuyên qua nhiều tầng, nhưng không thay thế kiểm soát truy cập tại luồng ghi.

Tương tự, `exists(example)` chỉ trả lời sự tồn tại theo điều kiện truy vấn tại thời điểm thực thi. Nó không cấp quyền sửa, không khóa bản ghi và không bảo đảm một điều kiện duy nhất vẫn còn đúng ở thời điểm ghi. Tính duy nhất cần được bảo vệ bằng cơ chế dữ liệu và giao dịch phù hợp.

## 9. Các nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu phù hợp |
| --- | --- |
| “Probe là entity nên có thể save luôn” | Kiểu Java chỉ giúp repository nhận đối tượng; tính hợp lệ và quyền ghi thuộc luồng ghi |
| “Bọc bằng `Example` sẽ làm đối tượng chỉ đọc” | Example giữ probe để truy vấn, không khóa setter hay cấm save |
| “Bỏ qua trường trong matcher thì trường đó không thể bị ghi” | `withIgnorePaths` chỉ ảnh hưởng điều kiện QBE |
| “Probe thiếu dữ liệu thì save sẽ bỏ qua các trường null” | Save không có ngữ nghĩa PATCH chung như vậy |
| “Không gọi save thì chắc chắn không có ghi dữ liệu” | Có thể sai với entity JPA đang managed và được dirty checking |
| “Đã tìm thấy entity thì người gọi được quyền sửa” | Đọc được dữ liệu không tự cấp quyền cập nhật |
| “Entity có ID là entity cập nhật hợp lệ” | Định danh không thay thế kiểm tra tồn tại, quyền, nghiệp vụ và phiên bản |
| “DTO riêng tự giải quyết toàn bộ vấn đề” | Vẫn phải kiểm soát mapping, quyền, validation và giao dịch |
| “Thêm tenant vào probe là luôn đủ” | Phải giữ đúng cách ghép điều kiện và áp dụng phạm vi trên các đường truy cập liên quan |
| “Mọi Spring Data store theo dõi thay đổi như JPA” | Vòng đời đối tượng và thao tác lưu thuộc implementation của từng store |

## 10. Bài tập đối chiếu ranh giới đọc và ghi

Có thể thực hành trên một store hỗ trợ QBE với bộ dữ liệu nhỏ và những tình huống sau:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Tìm theo tên và `active = null` | Chỉ các tiêu chí được chọn tham gia truy vấn |
| Tìm theo `active = false` | Không nhầm với trạng thái không lọc |
| Đầu vào tìm kiếm có trường ID ngoài DTO được phép | Không có đường sao chép ngầm ID vào probe hoặc lệnh ghi |
| Tạo Example rồi sửa probe trước khi thực thi | Nhận biết Example không tạo bản sao sâu của probe |
| Chạy tìm kiếm bằng probe mới | Không phát sinh thao tác ghi chỉ vì chuẩn bị bộ lọc |
| Sửa entity managed trong một thí nghiệm JPA có kiểm soát | Phân biệt được dirty checking với lời gọi save tường minh |
| Thử cập nhật bản ghi thuộc phạm vi người gọi không được sửa | Luồng ghi từ chối theo chính sách của ứng dụng |
| Hai người cùng cập nhật một bản ghi | Cơ chế xử lý xung đột của store được xác định rõ |

Khi rà soát code, lần theo nơi tạo probe, nơi thực thi `Example` và nơi gọi các thao tác ghi. Probe nên dừng lại ở luồng truy vấn. Một entity chỉ bước vào luồng ghi sau khi được chuẩn bị cho đúng lệnh, đúng quyền và đúng cơ chế lưu trữ; sự trùng kiểu với probe không thay thế những điều kiện đó.