# Tùy chỉnh IdGenerator bằng generatorClass hoặc generatorRef

## Mục tiêu bài học

Khi lưu node entity bằng Spring Data Neo4j (SDN), ứng dụng cần một định danh để nhận diện node trong những lần đọc và cập nhật tiếp theo. Với các trường hợp đơn giản, cơ chế sinh ID mặc định có thể đủ dùng. Khi hệ thống cần mã nghiệp vụ, UUID hoặc một quy tắc sinh ID riêng, SDN cho phép khai báo bộ sinh tùy chỉnh thông qua `@GeneratedValue`.

Bài học này giải thích cách triển khai `IdGenerator<T>`, cách gắn generator vào trường `@Id` bằng `generatorClass` hoặc `generatorRef`, và cách lựa chọn giữa hai cách cấu hình. Bạn cũng sẽ biết cách bảo vệ tính duy nhất của ID, kiểm thử generator và tránh những lỗi thường gặp khi chạy ứng dụng trên nhiều instance.

## 1. Vai trò của IdGenerator trong Spring Data Neo4j

Một node thường có các thuộc tính nghiệp vụ như tên, email hoặc trạng thái. Ngoài những thuộc tính đó, ứng dụng cần một định danh ổn định để tìm đúng node. Trong SDN, trường được đánh dấu `@Id` là trường định danh của entity. `@GeneratedValue` yêu cầu SDN sinh giá trị cho trường này khi tạo entity mới mà ứng dụng chưa cung cấp ID.

Ví dụ entity dùng ID chuỗi:

```java
@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue
    private String id;

    private String name;

    // Constructor, getter và setter được lược bỏ.
}
```

Khi cần quy tắc riêng, ta triển khai `org.springframework.data.neo4j.core.schema.IdGenerator<T>`. Generator nhận nhãn chính của node và entity đang được lưu, sau đó trả về giá trị có kiểu tương thích với trường ID.

```java
public interface IdGenerator<T> {

    T generateId(String primaryLabel, Object entity);
}
```

Trong đó:

- `T` là kiểu giá trị ID mà generator trả về, ví dụ `String`, `Long` hoặc kiểu phù hợp khác.
- `primaryLabel` là nhãn chính mà SDN dùng cho node entity.
- `entity` là object entity đang được xử lý; generator có thể đọc dữ liệu cần thiết từ object này nếu quy tắc sinh ID phụ thuộc vào dữ liệu nghiệp vụ.

Generator tùy chỉnh thay thế cách sinh ID mặc định cho trường được khai báo. Nó không tạo thêm một loại node hay relationship mới. Giá trị trả về được dùng làm định danh của entity và được SDN lưu theo chiến lược ID đã cấu hình.

## 2. Viết một IdGenerator tùy chỉnh

Một trường hợp phổ biến là sinh UUID dạng chuỗi. UUID phù hợp khi nhiều ứng dụng hoặc nhiều instance có thể tạo node đồng thời mà không cần xin số thứ tự từ một bộ đếm dùng chung.

```java
import java.util.UUID;

import org.springframework.data.neo4j.core.schema.IdGenerator;

public class CustomerIdGenerator implements IdGenerator<String> {

    @Override
    public String generateId(String primaryLabel, Object entity) {
        return "CUS-" + UUID.randomUUID();
    }
}
```

Generator trên trả về mã có tiền tố `CUS-`, theo sau là UUID. Tiền tố giúp ID dễ nhận biết khi quan sát log hoặc trao đổi giữa các hệ thống. UUID cung cấp phần ngẫu nhiên có xác suất va chạm rất thấp; nếu hệ thống yêu cầu bảo đảm duy nhất ở tầng dữ liệu, vẫn cần tạo uniqueness constraint trong Neo4j.

Tham số `primaryLabel` hữu ích khi một generator được dùng chung cho nhiều loại entity. Ví dụ, generator có thể chọn tiền tố dựa trên nhãn chính. Hãy chuẩn hóa quy tắc chuyển nhãn thành tiền tố và xử lý trường hợp nhãn không nằm trong danh sách hỗ trợ.

```java
public class LabelBasedIdGenerator implements IdGenerator<String> {

    @Override
    public String generateId(String primaryLabel, Object entity) {
        String prefix = switch (primaryLabel) {
            case "Customer" -> "CUS";
            case "Order" -> "ORD";
            default -> "NODE";
        };

        return prefix + "-" + UUID.randomUUID();
    }
}
```

Đoạn mã dùng switch expression của Java hiện đại. Nếu dự án dùng phiên bản Java cũ hơn, hãy thay bằng `switch` statement hoặc các nhánh `if` tương ứng.

Nên giữ generator đơn giản, nhanh và có thể dự đoán. Tránh thực hiện thao tác mạng, truy vấn database riêng hoặc thay đổi trạng thái nghiệp vụ trong `generateId`. Việc sinh ID nên hoàn tất nhanh và không tạo ra side effect khó phục hồi nếu transaction lưu node thất bại.

## 3. Đăng ký generator bằng generatorClass

Cách thứ nhất là chỉ định trực tiếp class triển khai `IdGenerator` trong annotation `@GeneratedValue`:

```java
@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue(generatorClass = CustomerIdGenerator.class)
    private String id;

    private String name;

    // Constructor, getter và setter được lược bỏ.
}
```

SDN dùng class được khai báo để tạo generator. Cách này phù hợp với bộ sinh độc lập, không cần các dependency do Spring quản lý. Hãy cung cấp constructor mà cơ chế khởi tạo của framework có thể sử dụng và không thiết kế generator này dựa vào constructor injection của Spring.

Ưu điểm của `generatorClass` là cấu hình nằm ngay tại entity, dễ nhìn thấy generator nào đang áp dụng. Nhược điểm là class generator khó nhận các dependency từ Spring như service, cấu hình hoặc client bên ngoài. Nếu generator cần những dependency đó, hãy cân nhắc đăng ký nó thành bean và dùng `generatorRef`.

Có thể tái sử dụng một class generator cho nhiều entity nếu quy tắc sinh ID giống nhau. Tuy nhiên, hãy kiểm tra nhãn và kiểu ID để tránh tạo mã không phù hợp với entity đích.

## 4. Đăng ký generator bằng generatorRef

Cách thứ hai là đăng ký generator thành Spring bean, rồi tham chiếu bean bằng tên trong `@GeneratedValue`. Cách này hữu ích khi generator cần cấu hình hoặc dependency được Spring quản lý.

Đăng ký bean:

```java
@Configuration
public class IdGeneratorConfiguration {

    @Bean("customerIdGenerator")
    public IdGenerator<String> customerIdGenerator() {
        return new CustomerIdGenerator();
    }
}
```

Entity tham chiếu bean đó:

```java
@Node("Customer")
public class Customer {

    @Id
    @GeneratedValue(generatorRef = "customerIdGenerator")
    private String id;

    private String name;

    // Constructor, getter và setter được lược bỏ.
}
```

Tên trong `generatorRef` phải khớp với tên bean đã đăng ký trong Spring ApplicationContext. Nếu bean được khai báo bằng `@Component("customerIdGenerator")`, tên tham chiếu cũng phải đúng như vậy.

Khi generator cần dependency, có thể đăng ký chính implementation đó bằng component scanning. Đây là cách đăng ký thay thế cho factory method ở ví dụ trước; không đăng ký đồng thời hai bean cùng tên:

```java
@Component("customerIdGenerator")
public class CustomerIdGenerator implements IdGenerator<String> {

    private final CustomerCodePolicy codePolicy;

    public CustomerIdGenerator(CustomerCodePolicy codePolicy) {
        this.codePolicy = codePolicy;
    }

    @Override
    public String generateId(String primaryLabel, Object entity) {
        return codePolicy.createCustomerId();
    }
}
```

Trong ví dụ này, `CustomerCodePolicy` là thành phần nghiệp vụ do ứng dụng cung cấp. Generator lấy mã theo chính sách được tiêm vào, còn SDN chỉ cần tìm đúng bean theo tên tham chiếu. Nếu chọn factory method thay cho `@Component`, hãy khai báo tham số `CustomerCodePolicy` trên method `@Bean` rồi truyền nó vào constructor của generator.

Một bean generator thường được dùng chung trong application context. Vì vậy, hãy thiết kế nó stateless hoặc bảo đảm thread-safe. Không lưu bộ đếm tăng dần trong một biến instance thông thường vì nhiều request có thể gọi đồng thời và nhiều application instance có thể chạy song song.

## 5. So sánh generatorClass và generatorRef

Hai thuộc tính đều cho phép SDN dùng một triển khai `IdGenerator` tùy chỉnh, nhưng cách cung cấp generator khác nhau:

| Tiêu chí | `generatorClass` | `generatorRef` |
|---|---|---|
| Cách cấu hình | Truyền class trong annotation | Truyền tên bean Spring |
| Nguồn tạo instance | Framework khởi tạo class generator | Spring quản lý bean |
| Dependency injection | Không phù hợp với constructor injection của Spring | Hỗ trợ dependency injection |
| Cấu hình | Gắn trực tiếp với entity | Khai báo bean ở cấu hình Spring |
| Phù hợp khi | Generator đơn giản, tự đủ | Generator cần service, policy hoặc cấu hình |
| Điều cần kiểm tra | Khả năng khởi tạo class | Tên bean và bean type |

Chọn `generatorClass` cho generator đơn giản như UUID hoặc quy tắc tự chứa. Chọn `generatorRef` khi muốn tận dụng Spring dependency injection, cấu hình theo môi trường hoặc thay thế implementation qua cấu hình bean.

Trên một trường ID, hãy cấu hình một cách tham chiếu generator rõ ràng. Không khai báo hai chiến lược cùng lúc cho một trường vì chúng biểu diễn hai cách chọn generator khác nhau và làm cấu hình trở nên mơ hồ.

## 6. Kiểu ID, tính duy nhất và ràng buộc trong Neo4j

Kiểu generic của generator phải tương thích với kiểu trường ID. Ví dụ:

```java
@Id
@GeneratedValue(generatorClass = CustomerIdGenerator.class)
private String id;
```

phải đi cùng generator triển khai `IdGenerator<String>`. Nếu trường ID là `Long`, generator cần trả về `Long` và phải có quy tắc tạo giá trị phù hợp.

Không nên nhầm ID nghiệp vụ do ứng dụng sinh với internal ID của Neo4j. Internal ID là chi tiết quản lý node của database; ứng dụng thường nên dùng mã nghiệp vụ ổn định như UUID khi cần công khai định danh, đồng bộ dữ liệu hoặc tham chiếu node từ hệ thống khác. Không nên dùng internal ID như một mã nghiệp vụ lâu dài.

Generator không thay thế ràng buộc duy nhất trong database. Ví dụ, để bảo đảm `Customer.id` không trùng trong các node mang nhãn `Customer`, có thể tạo uniqueness constraint:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer) REQUIRE c.id IS UNIQUE;
```

Constraint giúp Neo4j từ chối dữ liệu vi phạm tính duy nhất ngay cả khi có lỗi trong generator, dữ liệu được ghi bởi một ứng dụng khác hoặc nhiều request cạnh tranh. Tạo constraint phù hợp với phiên bản Neo4j và dữ liệu hiện có trước khi đưa thay đổi vào môi trường production.

Nếu generator dùng tiền tố theo loại node, vẫn nên có constraint riêng cho từng nhãn và thuộc tính tương ứng. Tiền tố giúp giảm nguy cơ trùng giữa các miền ID, nhưng không phải cơ chế bảo đảm duy nhất.

## 7. Khi nào generator được gọi và những điểm cần lưu ý

Generator tùy chỉnh phục vụ việc tạo ID cho entity mới. Với entity đã có ID, SDN sử dụng định danh hiện có để nhận diện entity theo chiến lược mapping. Do đó, không nên tự ý thay đổi ID của một entity đã được lưu như thể đó là thuộc tính thông thường.

Một số điểm cần kiểm soát:

- **Giá trị trả về:** Không trả về `null`, chuỗi rỗng hoặc giá trị không đúng kiểu trường ID.
- **Tính duy nhất:** Chọn thuật toán phù hợp với số lượng node và số instance; tạo uniqueness constraint để database bảo vệ dữ liệu.
- **Tính ổn định:** ID đã phát hành phải giữ nguyên trong vòng đời node. Không sinh ID mới mỗi lần cập nhật.
- **Tính đồng thời:** Không dựa vào biến đếm trong bộ nhớ nếu ứng dụng có nhiều thread hoặc nhiều instance.
- **Hiệu năng:** Tránh gọi dịch vụ ngoài hoặc thực hiện công việc tốn thời gian trong generator.
- **Phạm vi:** Nếu generator dùng chung cho nhiều entity, hãy kiểm tra `primaryLabel` và kiểu ID của từng entity.
- **Cấu hình Spring:** Với `generatorRef`, xác minh bean tồn tại, đúng tên và triển khai đúng `IdGenerator<T>`.

Nếu yêu cầu ID tăng tuần tự hoặc cấp phát theo một miền nghiệp vụ, hãy dùng một cơ chế cấp phát có tính nguyên tử và dùng chung giữa các instance. Một biến `AtomicLong` trong một process không thể bảo đảm không trùng sau khi ứng dụng khởi động lại hoặc khi có nhiều instance.

## 8. Kiểm thử IdGenerator và entity mapping

Có thể kiểm thử generator độc lập để xác nhận giá trị trả về hợp lệ:

```java
class CustomerIdGeneratorTest {

    private final CustomerIdGenerator generator =
            new CustomerIdGenerator();

    @Test
    void shouldGenerateCustomerId() {
        String id = generator.generateId("Customer", new Customer());

        assertNotNull(id);
        assertTrue(id.startsWith("CUS-"));
    }

    @Test
    void shouldGenerateDifferentIdsForDifferentCalls() {
        String first = generator.generateId("Customer", new Customer());
        String second = generator.generateId("Customer", new Customer());

        assertNotEquals(first, second);
    }
}
```

Với generator dựa trên UUID, kiểm thử không trùng trong hai lần gọi là kiểm tra hành vi cơ bản; nó không phải chứng minh toán học rằng không thể va chạm.

Ngoài unit test, nên có integration test với Neo4j để kiểm tra toàn bộ luồng:

1. Lưu một entity mới có trường `@Id` và `@GeneratedValue`.
2. Xác nhận SDN gán ID theo generator đã cấu hình.
3. Đọc lại entity bằng repository và xác nhận dữ liệu được tìm thấy bằng ID đó.
4. Lưu nhiều entity và xác nhận ID không bị trùng.
5. Kiểm tra uniqueness constraint từ database khi có dữ liệu xung đột.
6. Với `generatorRef`, khởi tạo application context để xác nhận bean name và dependency injection hoạt động.

Nếu thay đổi từ generator mặc định sang ID nghiệp vụ, hãy xem xét dữ liệu đã tồn tại và chiến lược migration. Việc thêm generator mới không tự động chuyển đổi ID của những node cũ.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Generator không được tìm thấy | Tên `generatorRef` không khớp tên bean | Kiểm tra tên bean trong cấu hình Spring và annotation |
| Không khởi tạo được generator class | Class không đáp ứng yêu cầu khởi tạo của framework | Dùng class generator tự đủ hoặc chuyển sang bean qua `generatorRef` |
| Sai kiểu ID | Generic của `IdGenerator<T>` không khớp trường ID | Đồng bộ kiểu trả về và kiểu trường |
| ID bị trùng khi tải cao | Thuật toán sinh ID dựa trên trạng thái cục bộ hoặc miền giá trị nhỏ | Dùng UUID hoặc cơ chế cấp phát phân tán có tính nguyên tử; thêm uniqueness constraint |
| ID thay đổi khi cập nhật | Generator được gọi hoặc gán lại không đúng vòng đời | Chỉ sinh ID cho entity mới và giữ ID ổn định |
| Generator thực hiện nhiều thao tác ngoài | Logic sinh ID phụ thuộc dịch vụ bên ngoài hoặc database khác | Tách việc cấp phát ID khỏi side effect nghiệp vụ |
| Dùng internal ID làm mã công khai | Nhầm chi tiết lưu trữ với định danh nghiệp vụ | Dùng ID ứng dụng ổn định nếu cần tham chiếu từ bên ngoài |

## 10. Tự kiểm tra

1. `IdGenerator<T>` nhận những tham số nào trong phương thức `generateId`?
2. Khi nào nên chọn `generatorClass` thay vì `generatorRef`?
3. Vì sao generator cần dependency từ Spring thường phù hợp với `generatorRef`?
4. Nếu trường ID có kiểu `String`, generator nên triển khai `IdGenerator` với kiểu generic nào?
5. Vì sao dùng bộ đếm trong bộ nhớ có thể tạo ID trùng khi triển khai nhiều instance?
6. Generator có thay thế được uniqueness constraint của Neo4j không?
7. Khi một entity đã có ID và được cập nhật, vì sao không nên sinh lại ID cho nó?

Hãy thử triển khai một generator UUID bằng `generatorClass`, sau đó chuyển sang bean có tên bằng `generatorRef`. Lưu nhiều entity qua repository, đọc lại bằng ID và kiểm tra constraint trong Neo4j để xác nhận chiến lược định danh hoạt động đúng.
