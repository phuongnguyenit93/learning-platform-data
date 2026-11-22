# Giới hạn sử dụng cho instance ID, khóa bảo mật và định danh bền vững

## 1. Giá trị ngẫu nhiên không giải quyết mọi loại định danh

Spring Boot cung cấp `RandomValuePropertySource` để đưa giá trị ngẫu nhiên vào cấu hình. Các placeholder như `${random.uuid}`, `${random.int}` hoặc `${random.value}` hữu ích khi ứng dụng cần một giá trị tạm thời trong lúc khởi động, ví dụ một ID cho phiên chạy, dữ liệu kiểm thử hoặc một giá trị mặc định dùng trong môi trường phát triển.

Tuy nhiên, ba nhu cầu sau có yêu cầu khác nhau:

- **Instance ID:** nhận diện một lần chạy hoặc một instance đang đăng ký trong service registry. ID có thể thay đổi khi instance được tạo lại, nhưng phải phân biệt được các instance đang tồn tại đồng thời.
- **Khóa bảo mật:** bảo vệ dữ liệu hoặc xác thực một giao dịch. Khóa cần nguồn ngẫu nhiên an toàn, đủ entropy, được lưu trữ, phân quyền, backup và rotation theo vòng đời riêng.
- **Định danh bền vững:** nhận diện cùng một bản ghi hoặc thực thể qua nhiều lần restart, deploy và di chuyển dữ liệu. Giá trị phải được tạo một lần và lưu lại.

Dùng một placeholder ngẫu nhiên cho cả ba mục đích dễ tạo ra lỗi: registry nhìn một tiến trình restart như một instance mới, ciphertext cũ không thể giải mã sau khi key thay đổi, hoặc một bản ghi nhận ID khác nhau mỗi lần ứng dụng khởi động.

Bài học thuộc chương **Giá trị ngẫu nhiên** của module **SPRING_CLOUD_CORE**. Module tập trung vào Spring Cloud Commons, Spring Cloud Context, cấu hình ngoài, tương thích Spring Boot, refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử/vận hành các abstraction chung.

Sau bài này, người học có thể:

- Đọc và giới hạn cách dùng các placeholder `random.*` của Spring Boot.
- Giải thích vì sao giá trị ngẫu nhiên lúc khởi động không phải định danh bền vững.
- Chọn instance ID phù hợp với vòng đời của process, container hoặc Pod.
- Phân biệt ID ngẫu nhiên với token/khóa cần chống đoán.
- Sinh key material bằng CSPRNG và quản lý nó qua secret manager hoặc KMS.
- Thiết kế ID dữ liệu có tính duy nhất thực tế và được lưu bền vững.
- Đánh giá collision, entropy, restart, scale-out, rotation và khôi phục.
- Viết kiểm thử cho tính ổn định hoặc thay đổi ID đúng theo yêu cầu.

## 2. RandomValuePropertySource của Spring Boot

### 2.1. Các placeholder được hỗ trợ

Spring Boot đăng ký `RandomValuePropertySource` trong `Environment`. Tài liệu hiện hành mô tả các giá trị chính:

| Placeholder | Kết quả |
| --- | --- |
| `${random.value}` | Một giá trị ngẫu nhiên dạng chuỗi/bytes theo implementation |
| `${random.int}` | Một số nguyên ngẫu nhiên |
| `${random.long}` | Một số nguyên 64-bit ngẫu nhiên |
| `${random.uuid}` | Một UUID ngẫu nhiên |
| `${random.int(10)}` | Số nguyên trong khoảng từ 0 đến 10, không bao gồm 10 |
| `${random.int[1024,65536]}` | Số nguyên từ 1024 đến 65535 |
| `${random.long[1000,9000]}` | Số nguyên dài từ 1000 đến 8999 |

Cú pháp giới hạn có dạng `OPEN min,max CLOSE`. Ký tự mở và đóng có thể là dấu ngoặc tròn hoặc vuông; giá trị lớn nhất luôn là **exclusive**. Nếu chỉ truyền một giới hạn, Spring Boot dùng 0 làm cận dưới và giá trị đó làm cận trên.

Ví dụ cấu hình YAML:

```yaml
app:
  diagnostics:
    boot-id: "${random.uuid}"
    sample-bucket: "${random.int[0,100]}"
    temporary-value: "${random.value}"
```

Tương đương trong properties:

```properties
app.diagnostics.boot-id=${random.uuid}
app.diagnostics.sample-bucket=${random.int[0,100]}
app.diagnostics.temporary-value=${random.value}
```

Trong YAML, nên đặt placeholder có dấu ngoặc hoặc ký tự đặc biệt trong dấu nháy để parser xử lý như scalar. Với `random.int[0,100]`, các giá trị có thể nhận là 0 đến 99.

### 2.2. Giá trị được sinh khi property được đọc

`RandomValuePropertySource` là một nguồn thuộc tính sinh giá trị khi được truy vấn. Nó không phải kho dữ liệu có khả năng ghi lại giá trị đã sinh qua lần chạy sau.

Vì vậy:

- Một giá trị được bind vào bean cấu hình lúc startup thường giữ trong bean đó cho đến khi bean được tạo lại hoặc cấu hình được bind lại.
- Khi process khởi động lại và property được resolve lại, giá trị ngẫu nhiên có thể khác.
- Không giả định hai lần resolve cùng biểu thức `${random.uuid}` ở hai vị trí khác nhau sẽ nhận cùng một UUID.
- Không dùng giá trị random như một giá trị mặc định cần giữ ổn định qua restart nếu chưa lưu nó vào nơi bền vững.

Nếu nhiều thành phần phải dùng cùng một giá trị, hãy tạo một nguồn sở hữu rõ ràng rồi truyền giá trị đó qua bean/configuration hoặc lưu vào một kho có vòng đời phù hợp. Không để từng thành phần tự resolve một placeholder ngẫu nhiên độc lập rồi mong đợi chúng trùng nhau.

### 2.3. Random placeholder không phải hợp đồng lưu trữ

Ví dụ:

```yaml
app:
  encryption:
    key: "${random.value}"
```

Ứng dụng có thể khởi động với một giá trị mới ở lần chạy tiếp theo. Nếu giá trị này được dùng để mã hóa dữ liệu rồi không được lưu lại, ứng dụng có thể mất khả năng giải mã dữ liệu đã tạo ở lần chạy trước.

Tương tự:

```yaml
app:
  customer:
    id: "${random.uuid}"
```

Đây chỉ là một giá trị cấu hình được resolve trong vòng đời ứng dụng. Nó không tự tạo một customer record, không ghi ID vào database và không bảo đảm customer giữ nguyên ID qua lần restart.

Cần quyết định rõ giá trị có vòng đời theo **lần resolve cấu hình**, **lần chạy process**, **vòng đời instance**, hay **vòng đời dữ liệu**. Các vòng đời này không giống nhau.

## 3. Dùng random value cho instance ID

### 3.1. Service ID và instance ID là hai khái niệm khác nhau

Trong service discovery, cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Service ID | Tên logic của dịch vụ | `inventory-service` |
| Instance ID | Định danh một instance đã đăng ký | `inventory-service:pod-7f9c` |
| Network address | Địa chỉ để kết nối đến instance | `10.0.4.12:8080` |
| Process ID | PID của tiến trình trên một host | `18432` |
| Deployment identity | Định danh do nền tảng triển khai cấp | Pod UID, task ID hoặc VM ID |

Nhiều instance có cùng service ID nhưng cần có instance ID riêng để registry phân biệt registration. Spring Cloud Commons cung cấp abstraction `ServiceRegistry` và `Registration`; cách tạo và diễn giải instance ID cụ thể phụ thuộc registry provider như Eureka, Consul hoặc Zookeeper.

### 3.2. Khi nào UUID ngẫu nhiên phù hợp?

Một UUID ngẫu nhiên có thể phù hợp cho **một lần chạy instance** khi các điều kiện sau đúng:

- Mỗi lần khởi động được xem là một registration mới.
- Các instance đang chạy đồng thời cần ID khác nhau.
- Registry hỗ trợ cập nhật, deregister hoặc hết hạn registration cũ.
- Hệ thống không cần giữ cùng instance ID qua lần restart.
- ID không được dùng làm định danh của service hoặc dữ liệu nghiệp vụ.

Ví dụ cấu hình một ID ứng dụng:

```yaml
spring:
  application:
    name: inventory-service

app:
  instance:
    id: "${INSTANCE_ID:${random.uuid}}"
```

Ở đây, nền tảng triển khai có thể cấp `INSTANCE_ID`. Khi biến này không được cung cấp, Spring Boot resolve UUID ngẫu nhiên làm giá trị dự phòng. Thuộc tính `app.instance.id` là cấu hình do ứng dụng tự định nghĩa; Spring Cloud Commons không tự động sử dụng thuộc tính này cho mọi registry. Ứng dụng phải ánh xạ nó vào cấu hình hoặc `Registration` của provider đang dùng.

### 3.3. Khi nào nên dùng định danh do nền tảng cấp?

Trong môi trường container/orchestrator, nền tảng thường có một định danh phù hợp hơn cho vòng đời instance:

- Kubernetes Pod UID hoặc một tổ hợp namespace và Pod UID.
- ECS task ARN hoặc task ID.
- VM/instance ID do cloud provider cấp.
- Host identity kết hợp port khi mô hình triển khai bảo đảm cặp đó là duy nhất.
- Deployment ordinal khi ứng dụng có stateful replica với danh tính ổn định.

Ví dụ với Consul Discovery, có thể ánh xạ ID do nền tảng cấp vào thuộc tính provider-specific:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        instance-id: "${INSTANCE_ID:${HOSTNAME:${random.uuid}}}"
```

Đây là cấu hình riêng cho Consul. Với Eureka hoặc provider khác, tên thuộc tính và semantics có thể khác. Cần đọc tài liệu provider thay vì giả định một thuộc tính instance ID dùng chung cho mọi implementation.

Nếu dùng `HOSTNAME` làm fallback, hãy xác nhận hostname thực sự duy nhất trong phạm vi registry. Một hostname ngắn có thể trùng giữa namespace, cluster hoặc môi trường khác nhau. Pod UID hoặc task ID thường thể hiện vòng đời instance rõ ràng hơn.

### 3.4. Rủi ro khi random ID thay đổi sau restart

Giả sử một instance đăng ký với ID `inventory-service:4f...`. Sau restart, `${random.uuid}` tạo ID mới. Registry có thể nhìn thấy registration mới trong khi registration cũ chưa được xóa hoặc chưa hết lease.

Hậu quả có thể gồm:

- Hai registration cùng trỏ đến một địa chỉ trong giai đoạn chuyển tiếp.
- Registration cũ còn tồn tại cho đến khi health check hoặc TTL loại bỏ.
- Dashboard và log khó liên kết một instance trước/sau restart.
- Cơ chế deregistration cần tìm đúng registration cũ.
- Một consumer có thể tạm thời nhận địa chỉ stale nếu cache chưa cập nhật.

Vì vậy, hãy phối hợp ID với lifecycle registration: đăng ký khi instance sẵn sàng, deregister khi shutdown nếu có thể, cấu hình lease/health check phù hợp và theo dõi propagation của registry. Không dùng random ID để che giấu việc quản lý registration chưa hoàn chỉnh.

### 3.5. Không dùng instance ID làm service ID hoặc định danh dữ liệu

Service ID cần ổn định để consumer gọi dịch vụ bằng tên logic. Nếu mỗi process tự sinh một service ID ngẫu nhiên, consumer không thể biết tên nào cần gọi và registry sẽ xuất hiện nhiều service logic rời rạc.

Instance ID chỉ nhận diện một registration. Nó không nên thay thế:

- `spring.application.name` hoặc service name.
- ID của customer, order, payment hoặc tài nguyên nghiệp vụ.
- ID của một cluster hoặc tenant có vòng đời dài hơn instance.
- Secret/token dùng để xác thực request.

## 4. Không dùng random placeholder làm khóa bảo mật dài hạn

### 4.1. Vì sao random value trong cấu hình không đủ?

Tài liệu Spring Boot mô tả `RandomValuePropertySource` là tiện ích để đưa giá trị ngẫu nhiên vào cấu hình, ví dụ secret hoặc test value. Tuy nhiên, placeholder không quản lý vòng đời khóa.

Một khóa mã hóa cần được giữ ổn định trong suốt thời gian dữ liệu được bảo vệ bởi khóa đó còn cần đọc. Nếu khóa mới được sinh mỗi lần khởi động:

1. Process A tạo key K1.
2. Ứng dụng mã hóa dữ liệu bằng K1.
3. Process A kết thúc.
4. Process B khởi động và resolve key K2.
5. Dữ liệu cũ vẫn cần K1, nhưng ứng dụng hiện chỉ có K2.

Nếu không có bản K1 được lưu an toàn và cơ chế chọn key version, dữ liệu cũ có thể không giải mã được.

Ngay cả khi implementation của một phiên bản Spring Boot sử dụng nguồn ngẫu nhiên an toàn, điều đó vẫn không biến `RandomValuePropertySource` thành KMS, secret manager hay kho khóa bền vững.

### 4.2. Random integer không có đủ không gian khóa

Không dùng các biểu thức như:

```yaml
security:
  api-key: "${random.int[0,1000000]}"
  encryption-key: "${random.long}"
```

Một số nguyên trong một triệu giá trị chỉ có khoảng 20 bit không gian tìm kiếm. Một số nguyên 64-bit cũng không đáp ứng mặc định yêu cầu của một khóa mã hóa hiện đại, đồng thời biểu diễn số học có thể làm mất các bit đầu hoặc gây vấn đề khi chuyển kiểu.

Khóa cần được tạo theo thuật toán và kích thước mà giao thức yêu cầu, bằng nguồn CSPRNG phù hợp. Không chọn độ dài chỉ vì chuỗi trông dài hoặc khó đọc.

### 4.3. Dùng SecureRandom để tạo key material

Trong Java, `java.security.SecureRandom` cung cấp bộ sinh số giả ngẫu nhiên có tính chất mật mã. Ví dụ sau minh họa tạo một khóa AES 256-bit:

```java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyGeneration {

    private KeyGeneration() {
    }

    public static SecretKey newAes256Key()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, new SecureRandom());
        return generator.generateKey();
    }
}
```

Đoạn code minh họa thao tác tạo key material. Trong hệ thống production, hãy thực hiện việc provision khóa theo quy trình quản lý khóa: lưu key vào KMS/HSM hoặc secret manager, gắn version/alias, giới hạn danh tính được sử dụng khóa và bảo đảm backup/recovery.

Không gọi hàm tạo khóa ở mỗi lần khởi động nếu ứng dụng cần tiếp tục giải mã dữ liệu đã mã hóa trước đó. Ứng dụng nên lấy đúng key version từ kho khóa theo policy của mình.

### 4.4. Sinh token ngẫu nhiên khác với tạo encryption key

Một bearer token hoặc token đặt lại mật khẩu cần khó đoán, nhưng không nhất thiết là khóa AES. Hãy dùng CSPRNG để sinh đủ byte ngẫu nhiên rồi mã hóa dạng biểu diễn phù hợp:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class TokenGenerator {

    private static final SecureRandom RANDOM = new SecureRandom();

    private TokenGenerator() {
    }

    public static String newToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
```

Token 32 byte có 256 bit dữ liệu ngẫu nhiên trước khi mã hóa Base64URL. Token cần có expiry, giới hạn mục đích, cơ chế single-use nếu phù hợp và được lưu an toàn. Với token xác thực dạng bearer, có thể chỉ lưu hash của token ở server để giảm rủi ro khi database bị đọc.

Không dùng UUID như một security capability. UUID chủ yếu là định danh; RFC 9562 cảnh báo không được giả định UUID khó đoán hoặc dùng việc sở hữu UUID làm bằng chứng quyền truy cập. Nếu possession của một chuỗi cho phép thực hiện hành động nhạy cảm, hãy tạo token bảo mật đúng cách.

### 4.5. Không tự seed bằng thời gian hoặc dữ liệu dễ đoán

Tránh các cách sau cho secret:

```java
Random random = new Random(System.currentTimeMillis());
String token = Long.toHexString(random.nextLong());
```

Thời gian hiện tại, PID, hostname, MAC address hoặc một số đếm không cung cấp entropy đủ lớn và có thể bị suy đoán. Cũng không gọi `SecureRandom.setSeed(System.currentTimeMillis())` để thay thế nguồn entropy. `SecureRandom` có cơ chế tự seed theo provider; nếu cần chính sách đặc biệt, hãy cấu hình và đánh giá provider theo chuẩn bảo mật của môi trường.

Dùng `SecureRandom` mặc định cho nhu cầu ứng dụng thông thường hoặc chọn provider/algorithm cụ thể theo chính sách tổ chức. Không tự chọn một thuật toán chỉ vì tên nghe có vẻ mạnh; phải kiểm tra provider hỗ trợ và yêu cầu nền tảng.

## 5. Định danh bền vững phải được lưu lại

### 5.1. UUID ngẫu nhiên có thể làm primary key, nếu được tạo một lần

UUIDv4 có thể là định danh thực thể thực tế tốt khi được tạo một lần lúc tạo bản ghi rồi lưu trong database. Java cung cấp:

```java
UUID id = UUID.randomUUID();
```

Ví dụ entity:

```java
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
class Order {

    @Id
    private UUID id = UUID.randomUUID();

    protected Order() {
    }

    UUID getId() {
        return id;
    }
}
```

Điều quan trọng là UUID được gán khi tạo entity mới và được lưu cùng bản ghi. Khi đọc bản ghi ở lần chạy sau, ứng dụng lấy ID từ database; không sinh lại ID chỉ vì process khởi động.

Cần có unique constraint hoặc primary key constraint trong database. UUID làm xác suất collision rất thấp trong thực tế, nhưng không biến xác suất thành bảo đảm toán học tuyệt đối. Database vẫn là nơi thực thi tính duy nhất cho dữ liệu đã lưu.

### 5.2. Không dùng random placeholder cho ID bản ghi

Ví dụ dưới đây không phù hợp nếu mục tiêu là định danh một order:

```yaml
app:
  order:
    id: "${random.uuid}"
```

Đây là một giá trị cấu hình dùng chung trong process/context, không phải một ID được tạo cho từng order. Nhiều order có thể vô tình dùng chung giá trị đó; lần restart tiếp theo lại resolve một giá trị khác.

ID bản ghi nên được tạo tại đúng ranh giới tạo bản ghi:

- Trong application/domain layer khi tạo entity.
- Trong database bằng sequence/identity/default phù hợp.
- Trong một ID service chuyên dụng nếu kiến trúc phân tán cần điều phối tập trung.
- Bằng một thuật toán ID phân tán đã được chọn và kiểm thử rõ ràng.

### 5.3. Chọn loại ID theo yêu cầu

| Loại ID | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Database sequence/identity | Tăng tuần tự, cần database cấp ID | Dữ liệu nằm trong một database hoặc cần số thứ tự |
| UUIDv4 | Ngẫu nhiên, không cần phối hợp giữa node, có tính duy nhất thực tế cao | ID phân tán, không cần thứ tự thời gian |
| UUIDv7 | Có phần timestamp và phần ngẫu nhiên/counter, hỗ trợ sắp xếp gần theo thời gian | Cần ID phân tán và locality/index ordering; chấp nhận lộ thông tin thời gian |
| Snowflake-like ID | Thường kết hợp timestamp, node ID và sequence | Hệ thống cần ID có thứ tự và kiểm soát worker/node identity |
| ID do nền tảng cấp | Gắn với vòng đời Pod/task/VM | Nhận diện instance triển khai |
| ID ngẫu nhiên lưu một lần | Tạo bằng CSPRNG rồi ghi vào kho dữ liệu | Thực thể cần opaque ID nhưng phải bền vững |

RFC 9562 định nghĩa UUIDv4 và UUIDv7 cùng các quy tắc tạo UUID. UUIDv7 đặt timestamp Unix milliseconds ở phần đầu và dùng các bit còn lại cho entropy/counter theo cấu hình. UUID có thứ tự thời gian có thể hỗ trợ index locality, nhưng timestamp cũng tiết lộ gần đúng thời điểm tạo.

Java `UUID.randomUUID()` tạo UUID phiên bản 4. Nếu ứng dụng cần UUIDv7, hãy dùng thư viện tương thích RFC 9562 hoặc cơ chế ID đã được nền tảng hỗ trợ; không tự ghép timestamp và random bits nếu chưa kiểm tra version/variant và quy tắc chuẩn.

### 5.4. Định danh tất định từ dữ liệu ổn định

Một số hệ thống cần cùng một đầu vào luôn tạo cùng một ID, ví dụ ánh xạ external reference sang internal key. Đó là bài toán deterministic identifier, không phải random identifier.

Có thể dùng namespace/name-based UUID theo chuẩn phù hợp hoặc lưu bảng mapping. Cần chọn canonicalization, namespace và thuật toán rõ ràng; thay đổi cách chuẩn hóa đầu vào có thể tạo ID khác. Hash/UUID name-based không phải chữ ký xác thực và không nên chứa dữ liệu cá nhân nhạy cảm trong giá trị có thể suy ra.

Nếu dữ liệu đầu vào có entropy thấp hoặc dễ đoán, hash đơn thuần không che giấu nó. Dùng mapping có kiểm soát hoặc keyed construction khi cần bảo vệ tính bí mật.

## 6. Collision và giới hạn tính duy nhất

### 6.1. Birthday bound

Với không gian có `b` bit ngẫu nhiên và số lượng giá trị được sinh là `n`, xác suất có ít nhất một collision khi `n` nhỏ so với không gian có thể xấp xỉ:

[
p approx rac{n(n-1)}{2^{b+1}}
]

Xác suất tăng theo bình phương số lượng giá trị. Vì thế, giảm số bit ngẫu nhiên hoặc dùng một dải số nhỏ có thể làm collision xuất hiện nhanh hơn nhiều so với trực giác.

UUIDv4 có 128 bit tổng cộng, trong đó các bit version và variant được dành riêng; còn 122 bit ngẫu nhiên. Xác suất collision của UUIDv4 rất thấp với số lượng ID thông thường, nhưng không bằng 0.

### 6.2. Ràng buộc duy nhất vẫn cần thiết

Không dùng xác suất thay cho ràng buộc dữ liệu. Với ID được lưu trong database:

- Đặt primary key hoặc unique constraint.
- Xử lý lỗi duplicate key như một trường hợp có thể xảy ra.
- Nếu thuật toán cho phép, tạo ID mới và retry có giới hạn khi gặp collision.
- Ghi nhận metric/log cho lỗi trùng ID để phát hiện lỗi generator hoặc dữ liệu bị replay.
- Không ghi đè bản ghi cũ khi ID trùng.

Với ID phân tán ở nhiều database hoặc nhiều region, xác định rõ phạm vi uniqueness: một bảng, một database, toàn hệ thống hay nhiều tổ chức. Nếu hậu quả collision rất nghiêm trọng, cần thêm cơ chế phối hợp hoặc registry trung tâm thay vì chỉ dựa vào random bits.

### 6.3. Random integer rất dễ trùng khi không gian nhỏ

Ví dụ `${random.int[0,100]}` chỉ có 100 khả năng. Khi nhiều instance cùng khởi động, việc trùng giá trị là bình thường. Đây có thể là bucket lấy mẫu hoặc số chọn ngẫu nhiên, nhưng không phù hợp làm instance ID hoặc primary key.

Không nên dùng random port trong production như một định danh duy nhất nếu không có cơ chế bind socket và công bố port thực tế. Nếu cần port tạm thời trong test, hãy để hệ điều hành cấp port trống rồi đọc port đã bind.

## 7. Thiết kế theo vòng đời

### 7.1. Bảng quyết định

| Nhu cầu | Giá trị phù hợp | Nơi lưu/nguồn sở hữu | Điều cần tránh |
| --- | --- | --- | --- |
| ID của một lần boot để trace log | UUID ngẫu nhiên | Log context hoặc startup metadata | Dùng nó làm ID của service |
| ID instance ngắn hạn | Pod UID/task ID; UUID nếu cần fallback | Platform metadata hoặc registry registration | Không deregister/expire registration cũ |
| Tên dịch vụ | Tên cấu hình ổn định | `spring.application.name` hoặc service catalog | Random service name mỗi lần boot |
| Encryption key | Key từ CSPRNG/KMS | KMS, HSM, Vault hoặc secret manager | Sinh lại bằng `${random.value}` mỗi restart |
| Bearer token/reset token | Token đủ entropy từ SecureRandom | Client nhận một lần; server lưu hash/expiry | UUID hoặc random integer làm quyền truy cập |
| Primary key của entity | UUID/sequence/ID service | Database | Placeholder trong application.yml |
| ID liên kết giữa nhiều hệ thống | ID bền vững hoặc mapping đã lưu | Database/catalog có version | Tạo random lại mỗi lần đồng bộ |
| Test fixture | Random value có seed/fixture được kiểm soát khi cần tái lập | Test setup | Phụ thuộc random không cố định khiến test flaky |

### 7.2. Chọn nơi lưu theo vòng đời

Hãy hỏi giá trị cần tồn tại bao lâu:

- **Trong một lần đọc cấu hình:** placeholder ngẫu nhiên có thể đủ.
- **Trong một process:** bind vào bean hoặc giữ trong application state.
- **Trong vòng đời một instance:** lấy ID từ platform hoặc registration provider.
- **Qua restart/deploy:** lưu vào database, secret manager hoặc metadata bền vững.
- **Qua nhiều dịch vụ/region:** dùng ID scheme và ràng buộc uniqueness có phạm vi rõ ràng.

Không lưu khóa bảo mật trong application.yml chỉ để có thể tái sử dụng. Lưu key material trong kho khóa, còn ứng dụng chỉ nhận quyền sử dụng đúng key/version qua workload identity.

## 8. Kiểm thử và vận hành

### 8.1. Kiểm thử random property

Không assert một giá trị cụ thể của `${random.uuid}` hoặc `${random.int}`. Thay vào đó, kiểm tra:

- UUID có parse được và đúng format mong muốn.
- Integer nằm trong khoảng min-inclusive/max-exclusive.
- Giá trị được bind vào đúng property/type.
- Giá trị có thể thay đổi giữa hai lần tạo context nếu bài test đang xác minh tính ephemeral.
- Test không phụ thuộc vào thứ tự ngẫu nhiên giữa các test case.

Ví dụ kiểm tra UUID:

```java
UUID bootId = UUID.fromString(environment.getRequiredProperty("app.diagnostics.boot-id"));
assertThat(bootId).isNotNull();
```

Nếu cần kiểm thử deterministic, inject một ID cố định qua test property source thay vì cố gắng dự đoán kết quả random.

### 8.2. Kiểm thử instance registration

Một integration test cho service registry nên:

1. Khởi động instance với service ID ổn định.
2. Xác nhận instance ID có mặt trong registration.
3. Khởi động thêm instance thứ hai và xác nhận ID không trùng trong cùng registry.
4. Dừng instance thứ nhất và xác nhận deregistration/lease expiry.
5. Khởi động lại và kiểm tra semantics ID: giữ nguyên nếu dùng platform identity ổn định, hoặc đổi nếu chủ đích là ID theo process.
6. Kiểm tra registry không còn trả endpoint cũ sau thời gian propagation dự kiến.

Đừng chỉ kiểm tra property `app.instance.id`; cần xác nhận provider thực sự dùng giá trị đó khi đăng ký.

### 8.3. Kiểm thử key lifecycle

Với encryption key:

- Mã hóa một fixture bằng key version K1.
- Khởi động lại ứng dụng và xác nhận vẫn lấy đúng K1 để giải mã fixture.
- Tạo K2 theo quy trình rotation.
- Xác nhận dữ liệu mới dùng K2 và dữ liệu cũ vẫn đọc được trong giai đoạn chuyển tiếp.
- Thu hồi K1 chỉ sau khi dữ liệu/backup được xử lý theo policy.
- Kiểm tra quyền truy cập KMS/secret manager và audit log.

Không in key bytes, plaintext secret hoặc bearer token vào test log. Dùng fixture giả lập, không đưa key production vào unit test.

### 8.4. Kiểm thử ID bền vững

Với entity ID:

- Tạo entity và lưu database.
- Đóng context hoặc restart process.
- Đọc lại entity và xác nhận ID không đổi.
- Thử insert ID trùng và xác nhận unique constraint từ chối.
- Với ID phân tán, kiểm tra import/replay và dữ liệu từ nhiều node.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Instance ID đổi sau mỗi restart | Dùng `${random.uuid}` làm fallback hoặc giá trị chính | Quyết định ID theo process hay platform; dùng Pod/task/VM identity nếu cần ổn định |
| Registry còn instance cũ | Không deregister hoặc lease/health timeout quá dài | Kiểm tra shutdown hook, registration lifecycle và TTL |
| Nhiều property có UUID khác nhau | Mỗi lần resolve placeholder có thể sinh giá trị mới | Tạo một bean sở hữu ID hoặc truyền cùng một giá trị đã resolve |
| Ciphertext cũ không giải mã sau restart | Encryption key được sinh lại ở startup | Lấy key version ổn định từ KMS/Vault và lập kế hoạch rotation |
| Random integer bị trùng | Không gian giá trị quá nhỏ | Dùng ID scheme có đủ không gian và unique constraint |
| UUID bị dùng làm token truy cập | Nhầm ID với security capability | Sinh bearer token bằng CSPRNG, expiry và single-use policy |
| ID bản ghi thay đổi khi deploy | ID được tạo từ cấu hình runtime thay vì được lưu | Tạo ID lúc tạo entity và lưu trong database |
| Test lúc pass lúc fail | Test phụ thuộc vào random order hoặc collision giả định | Inject deterministic fixture và kiểm tra invariant |
| Các node dùng chung một instance ID | Giá trị cấu hình được copy giữa replica | Dùng identity riêng theo pod/task/VM hoặc generator phân tán |
| Key rotation làm mất dữ liệu cũ | Thu hồi key cũ trước khi re-encrypt hoặc bảo đảm đọc key version cũ | Dùng key versioning và kiểm thử migration/restore |

## 10. Checklist lựa chọn và vận hành

Trước khi đưa một giá trị ngẫu nhiên vào production, hãy xác nhận:

1. Giá trị này nhận diện lần resolve, process, instance hay thực thể dữ liệu?
2. Có cần giữ nguyên sau restart hoặc deploy không?
3. Có cần duy nhất giữa các replica, cluster hoặc region không?
4. Phạm vi collision có được xác định và chấp nhận không?
5. Nếu là instance ID, registry provider thực sự sử dụng property nào?
6. Có cơ chế deregister, health check hoặc lease expiry cho registration cũ không?
7. Nếu là key/token, nguồn tạo có phải CSPRNG và có đủ entropy không?
8. Key có được lưu trong KMS/HSM/Vault/secret manager thay vì sinh lại mỗi startup không?
9. Có key version, rotation, backup và recovery không?
10. Nếu là ID dữ liệu, giá trị có được lưu bền vững và có unique constraint không?
11. Có dùng UUID như bearer token hoặc security capability không?
12. Test có kiểm tra invariant thay vì phụ thuộc giá trị random cụ thể không?
13. Log có vô tình in key, token hoặc dữ liệu nhạy cảm không?
14. Tài liệu provider và phiên bản Spring Boot đang dùng có khớp với cấu hình thực tế không?

## 11. Tài liệu tham khảo chính thức

- [Spring Boot — Externalized Configuration, Configuring Random Values](https://docs.spring.io/spring-boot/reference/features/external-config.html): cú pháp `random.value`, `random.int`, `random.long`, `random.uuid` và giới hạn range.
- [RandomValuePropertySource API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/env/RandomValuePropertySource.html): các kiểu giá trị được sinh và cách cấu hình property source.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `ServiceRegistry`, `Registration`, auto-registration và discovery.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): các cấu hình service discovery và provider-specific instance metadata.
- [Java SecureRandom Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureRandom.html): bộ sinh số ngẫu nhiên mạnh về mặt mật mã, seeding và thread safety.
- [Java UUID Javadoc](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/UUID.html): `UUID.randomUUID()` tạo UUID phiên bản 4 bằng CSPRNG.
- [RFC 9562 — Universally Unique Identifiers](https://www.rfc-editor.org/rfc/rfc9562.html): UUIDv4, UUIDv7, collision resistance, unguessability và giới hạn dùng UUID làm security capability.

**Ghi nhớ:** Random placeholder của Spring Boot tiện cho giá trị tạm thời trong cấu hình. Instance ID phải phù hợp với vòng đời registration; khóa bảo mật phải có CSPRNG và key management; định danh dữ liệu phải được tạo một lần, lưu bền vững và được database hoặc cơ chế phối hợp thực thi tính duy nhất.
