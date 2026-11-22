# Cơ chế hình thành khóa từ keyspace và định danh trong Redis Repository

Khi dùng **Spring Data Redis Repository**, lập trình viên thường thao tác với một đối tượng Java qua `save()`, `findById()` và `deleteById()`, không cần tự ghép chuỗi tên khóa trước mỗi lệnh Redis. Tuy nhiên, Redis vẫn lưu dữ liệu tại các **khóa vật lý** cụ thể. Spring Data Redis xác định khóa của một entity bằng hai thông tin chính: **keyspace** (không gian tên của loại entity) và **định danh** (`id`) của từng bản ghi.

Hiểu rõ cơ chế này giúp giải thích vì sao gọi `findById("u-100")` lại đọc được `customers:u-100`, vì sao hai entity có cùng id vẫn có thể được lưu riêng, cũng như vì sao quét khóa có tiền tố `customers` đôi khi xuất hiện cả những khóa mà ứng dụng không tạo trực tiếp.

## 1. Keyspace và định danh là gì?

**Keyspace** trong ngữ cảnh Redis Repository là tên logic dành cho một nhóm đối tượng cùng kiểu, tương tự một *namespace* hoặc tiền tố lưu trữ. **Định danh** là giá trị phân biệt từng đối tượng trong nhóm đó. Một khóa entity thường được tạo theo quy ước:

```text
Redis key = <keyspace> + ":" + <id>
```

Ví dụ:

| Keyspace | ID | Khóa entity trong Redis |
|---|---|---|
| `customers` | `u-100` | `customers:u-100` |
| `customers` | `u-101` | `customers:u-101` |
| `orders` | `u-100` | `orders:u-100` |
| `sessions` | `8e23` | `sessions:8e23` |

Từ bảng trên rút ra hai điều:

- **Cùng keyspace, khác id:** hai entity độc lập, ví dụ `customers:u-100` và `customers:u-101`.
- **Cùng id, khác keyspace:** vẫn là hai khóa vật lý khác nhau, ví dụ `customers:u-100` và `orders:u-100`.

Đối với một kiểu entity, **cặp (keyspace, id)** mới xác định địa chỉ của entity trong Redis. `id` không nhất thiết phải duy nhất trên toàn bộ Redis server, nhưng phải ổn định và duy nhất trong keyspace của loại dữ liệu đang lưu.

> Đây là cơ chế đặt khóa của **Spring Data Redis Repository**. Redis server bản thân không biết “entity”, “repository” hay `@Id`; với Redis, `customers:u-100` đơn giản là một tên khóa gồm các byte.

## 2. Cấu hình keyspace bằng `@RedisHash`

Ví dụ xây dựng entity khách hàng:

```java
package example.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String fullName;

    private String email;

    public Customer() {
    }

    public Customer(String id, String fullName, String email) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Trong ví dụ này:

- `@RedisHash("customers")` chỉ rõ **keyspace** là `customers`.
- `@Id` chỉ rõ thuộc tính `id` là **định danh entity** của Spring Data.
- `id = "u-100"` dẫn tới khóa logic `customers:u-100`.
- Các thuộc tính khác như `fullName` và `email` được ánh xạ vào dữ liệu của entity; chúng **không tự động thay đổi tên khóa chính**.

`@RedisHash` không phải tên của một Redis Hash đã có sẵn. Annotation này cung cấp thông tin ánh xạ cho Spring Data Redis: khi ghi một `Customer`, repository lưu nội dung entity dưới khóa được hình thành từ keyspace và id, thông thường ở kiểu dữ liệu Redis **HASH**.

Về mặt ý tưởng:

```text
Customer Java object
  id       = "u-100"
  fullName = "Nguyễn An"
  email    = "an@example.test"
         |
         v
@RedisHash("customers") + @Id("u-100")
         |
         v
Khóa chính trong Redis: customers:u-100
Kiểu Redis: HASH
Một số field: fullName, email, ... (có thể kèm metadata kiểu Java)
```

Các tên field vật lý, metadata như `_class` và cách chuyển đổi giá trị phụ thuộc vào cấu hình `RedisConverter`/mapping. Sơ đồ thể hiện quy tắc đặt **khóa entity**, không cam kết mọi byte của nội dung HASH đều giống nhau trên mọi cấu hình.

### Nếu không khai báo `@RedisHash("...")` thì sao?

Spring Data Redis có cơ chế xác định keyspace thông qua metadata của entity và cấu hình mapping. Nếu không ấn định một keyspace tường minh, tên được suy ra có thể gắn với tên kiểu Java hoặc quy ước của cấu hình hiện hành. Với dữ liệu cần sống qua nhiều lần refactor class/package, nên **khai báo một keyspace rõ ràng, ổn định** để tránh đổi tên khóa vật lý ngoài ý muốn.

Ngoài `@RedisHash`, dự án có thể cấu hình keyspace cho entity qua `KeyspaceConfiguration` và `@EnableRedisRepositories`. Đây là cách phù hợp khi muốn gom quy ước đặt namespace vào cấu hình thay vì gắn trực tiếp lên class. Dù khai báo theo cách nào, khi chạy thực tế cần có **một quy tắc keyspace nhất quán** cho từng kiểu entity.

## 3. `@Id`: thuộc tính nào được dùng để tạo khóa?

Repository xác định id qua metadata của Spring Data, điển hình là `org.springframework.data.annotation.Id`. Khi save:

```java
Customer customer = new Customer(
        "u-100",
        "Nguyễn An",
        "an@example.test"
);

customerRepository.save(customer);
```

Kết quả chính cần hiểu:

```text
keyspace  = "customers"
entity id = "u-100"
Redis key = "customers:u-100"
```

Kiểu `String` rất tiện để minh họa, nhưng định danh có thể là kiểu khác nếu mapping của ứng dụng hỗ trợ chuyển đổi nó sang biểu diễn dùng làm khóa. Ví dụ id số `42` thường tạo hậu tố tương ứng `42`; còn đối tượng id phức hợp nên có quy tắc chuyển đổi rõ ràng thay vì trông chờ `toString()` mặc định.

### ID được cấp từ đâu?

Có hai hướng thông dụng:

1. **Ứng dụng cấp id trước khi lưu**, như `"u-100"`, mã nghiệp vụ, UUID được sinh ở tầng service hoặc định danh của hệ thống khác.
2. **Spring Data Redis cấp id cho entity mới** trong trường hợp kiểu id và đường mapping hỗ trợ sinh tự động (ví dụ trường `String` chưa có giá trị thường có thể nhận UUID). Luôn dùng giá trị id đã được trả về/gắn vào entity sau `save()`, thay vì tự dự đoán tên khóa sẽ sinh.

Ví dụ với `String id` chưa được gán:

```java
Customer customer = new Customer(
        null,
        "Trần Bình",
        "binh@example.test"
);

Customer saved = customerRepository.save(customer);
String assignedId = saved.getId();

System.out.println("Repository ID: " + assignedId);
System.out.println("Expected key: customers:" + assignedId);
```

Kết quả `assignedId` mới là nguồn xác thực để tìm lại entity:

```java
customerRepository.findById(assignedId);
```

Không nên suy ra id từ `fullName` hoặc `email` nếu các trường này có thể đổi. Việc chọn định danh ổn định là quyết định thiết kế dữ liệu; Spring Data Redis chỉ thực thi cách ánh xạ đã được cấu hình.

## 4. Repository thực hiện `save()`, `findById()` và `deleteById()` như thế nào?

Khai báo repository:

```java
package example.redis;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {
}
```

Khi dự án đã cấu hình kết nối Redis và bật Redis repositories, Spring Data tạo implementation cho interface trên. Mối quan hệ giữa lời gọi Java và khóa chính có thể hình dung như sau:

| Lời gọi repository | Entity/id | Khóa chính được nhắm tới |
|---|---|---|
| `save(customer)` | `customer.id = "u-100"` | `customers:u-100` |
| `findById("u-100")` | `"u-100"` | `customers:u-100` |
| `existsById("u-100")` | `"u-100"` | `customers:u-100` |
| `deleteById("u-100")` | `"u-100"` | `customers:u-100` |

Ví dụ một vòng đời đầy đủ:

```java
Customer first = new Customer(
        "u-100", "Nguyễn An", "an@example.test");

// Tạo hoặc ghi lại entity có cùng khóa chính.
customerRepository.save(first);

Customer loaded = customerRepository.findById("u-100")
        .orElseThrow();

loaded.setFullName("Nguyễn An Bình");
customerRepository.save(loaded);

boolean stillExists = customerRepository.existsById("u-100");

customerRepository.deleteById("u-100");
```

Việc cập nhật `fullName` không đổi `id`, nên repository vẫn nhắm đến khóa `customers:u-100`. Nếu hai request lưu hai object `Customer` với cùng keyspace và id, chúng cùng tác động đến **một khóa logic**; đây không phải hai bản ghi khác nhau. Khi cần chống ghi đè do cập nhật đồng thời, phải thiết kế cơ chế đồng bộ hoặc kiểm soát phiên bản tương ứng, không thể dựa vào tên khóa để tự bảo đảm tính nhất quán.

### Thay đổi ID khác với thay đổi thuộc tính bình thường

Giả sử entity cũ nằm tại `customers:u-100`, sau đó ứng dụng sửa `id` thành `u-200` và gọi `save()`. Địa chỉ lưu mới là `customers:u-200`; thao tác đó không nên được hiểu như lệnh **RENAME** tự động xóa khóa cũ. Tùy đường thao tác, khóa cũ có thể còn tồn tại hoặc dữ liệu phụ trợ chưa được dọn như mong đợi.

Vì vậy, thông thường:

- Chọn id một lần khi tạo entity; giữ nó **bất biến** trong các lần cập nhật nghiệp vụ.
- Nếu thật sự cần đổi id, xây dựng quy trình chuyển dữ liệu rõ ràng: đọc khóa cũ, lưu dữ liệu với id mới, cập nhật các tham chiếu liên quan, xóa id cũ và xử lý lỗi giữa các bước.
- Không xem `setId(...)` trên một object đã lưu như thao tác đổi tên khóa Redis có tính nguyên tử.

## 5. Keyspace không chỉ xuất hiện trong tên khóa của HASH

Một điểm dễ gây ngạc nhiên: Redis Repository còn có thể duy trì **khóa phụ** để quản lý các entity trong cùng keyspace và phục vụ truy vấn chỉ mục. Bởi vậy, sau khi lưu một `Customer`, bạn có thể thấy nhiều khóa bắt đầu bằng `customers`, dù chỉ lưu một object.

Ví dụ ở mức khái niệm:

```text
customers:u-100          → HASH chứa dữ liệu Customer u-100
customers:u-101          → HASH chứa dữ liệu Customer u-101
customers                → SET hỗ trợ theo dõi entity của keyspace
customers:email:...      → khóa chỉ mục phụ, nếu có @Indexed tương ứng
```

Các tên khóa chỉ mục, kiểu dữ liệu, thành viên trong SET và metadata thực tế phụ thuộc vào kiểu entity, serializer, phiên bản thư viện và cấu hình. Quy tắc quan trọng là **khóa entity chính** và **khóa phục vụ repository** không phải một.

### Tại sao có khóa `customers` dù entity nằm ở `customers:u-100`?

Spring Data Redis Repository dùng thông tin keyspace để hỗ trợ các thao tác như `findAll()` hoặc `count()` mà không phải tùy tiện quét toàn bộ Redis server bằng `KEYS *`. Một cách phổ biến là duy trì một Redis **SET** gắn với keyspace để theo dõi các entity đã lưu.

Do vậy:

```text
HGETALL customers:u-100  → đọc HASH của một entity
TYPE customers           → có thể là SET quản lý keyspace
SMEMBERS customers       → xem thành viên trong SET quản lý keyspace
```

Một lệnh `HSET customers:u-999 ...` thực hiện thủ công chỉ tạo/sửa HASH, **không bảo đảm** đã cập nhật các cấu trúc quản lý mà repository cần. Hậu quả là `findById("u-999")` có thể xử lý khác với `findAll()`, hoặc truy vấn theo chỉ mục không thấy entity. Muốn duy trì đầy đủ mô hình repository, hãy ghi dữ liệu qua repository hoặc triển khai nhất quán mọi cấu trúc phụ theo đúng hợp đồng mapping.

### Chỉ mục phụ khi dùng `@Indexed`

Ví dụ muốn tìm khách hàng theo email:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    private String fullName;

    @Indexed
    private String email;

    // Constructor, getter và setter tương tự ví dụ trước.
}
```

Repository có thể khai báo:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}
```

`@Indexed` báo cho Spring Data Redis duy trì cấu trúc truy vấn phụ cho thuộc tính `email`. Một khóa index có thể chứa thông tin về keyspace, tên field và giá trị field, và SET chỉ mục tham chiếu đến các entity phù hợp. Chính vì vậy khi dùng `SCAN MATCH customers*`, kết quả không chỉ gồm các khóa HASH của khách hàng.

**Keyspace không đồng nghĩa với bảng quan hệ.** Redis Repository xây dựng một số cấu trúc dữ liệu nhằm cung cấp API gần với Spring Data; nó không biến Redis thành RDBMS có ràng buộc khóa ngoại, truy vấn tùy ý hay transaction xuyên nhiều khóa theo mặc định.

## 6. Kiểm tra cách tạo khóa bằng `redis-cli`

Giả sử đã gọi:

```java
customerRepository.save(new Customer(
        "u-100", "Nguyễn An", "an@example.test"));
```

Có thể quan sát trong môi trường thực hành:

```bash
# Kiểm tra khóa chính có kiểu gì.
redis-cli TYPE customers:u-100

# Đọc các field trong HASH.
redis-cli HGETALL customers:u-100

# Xem TTL của entity key.
redis-cli TTL customers:u-100

# Xem loại cấu trúc hỗ trợ tại chính tên keyspace.
redis-cli TYPE customers

# Nếu TYPE customers trả "set", có thể xem thành viên.
redis-cli SMEMBERS customers

# Khảo sát các khóa mang tiền tố; dùng SCAN để tránh chặn như KEYS.
redis-cli SCAN 0 MATCH 'customers*' COUNT 100
```

Lệnh `SCAN` chỉ trả một phần kết quả tại mỗi bước. Khi cursor khác `0`, phải gọi tiếp với cursor mới đến khi kết thúc. Mẫu `customers*` là *pattern matching*, không phải truy vấn repository và không phân biệt khóa HASH chính với SET/khóa phụ. Vì thế luôn dùng `TYPE` để nhận diện đối tượng trước khi đọc.

Nếu Redis chạy dưới **Cluster**, lệnh quan sát một node chỉ thấy các khóa hiện thuộc node đó. Trái lại, một thao tác `findById()` với khóa xác định thường được client cluster-aware định tuyến đến slot chứa khóa. Không kết luận rằng khóa bị mất chỉ vì `SCAN` trên một node chưa thấy nó.

## 7. Tại sao không thể tùy tiện ghép `id` vào keyspace của type khác?

So sánh hai repository:

```java
@RedisHash("customers")
class Customer {
    @Id String id;
    // ...
}

@RedisHash("orders")
class Order {
    @Id String id;
    // ...
}
```

Với cùng `id = "42"`, Spring Data Redis định tuyến các entity đến:

```text
Customer(id="42") → customers:42
Order(id="42")    → orders:42
```

Hai khóa độc lập, vì chúng có keyspace khác nhau. Nếu cả hai class cùng `@RedisHash("shared")`, cùng id `42` thì cùng nhắm đến khóa `shared:42`. Metadata kiểu entity và dữ liệu HASH có thể va chạm; việc đặt tên repository/class khác nhau **không tạo vùng lưu trữ độc lập** khi dùng chung keyspace.

Vì vậy, khi thiết kế:

- Dành keyspace riêng cho những loại entity cần tách biệt dữ liệu.
- Chỉ dùng chung keyspace nếu đã chủ đích thiết kế chung định dạng và cơ chế quản lý.
- Đặt keyspace ổn định, nhất quán giữa các phiên bản dịch vụ cùng truy cập dữ liệu.
- Với nhiều ứng dụng cùng kết nối một Redis, cân nhắc thêm tiền tố hệ thống hoặc môi trường như `billing:customers`, `test:customers` nếu thực sự cùng chia sẻ server; kiểm soát xung đột tên là trách nhiệm của ứng dụng.

Tên keyspace là một phần của **hợp đồng lưu trữ dữ liệu**, tương tự tên bảng trong database ở khía cạnh tương thích khi triển khai. Đổi `@RedisHash("customers")` thành `@RedisHash("clients")` khiến repository mới tìm các id dưới prefix mới, trong khi các khóa cũ vẫn có tên `customers:...`. Đổi annotation không tự động migrate dữ liệu.

## 8. Dấu hai chấm trong ID và keyspace: tên khóa được tạo ra có ý nghĩa gì?

Dấu `:` là quy ước dễ đọc để ngăn cách các thành phần của tên khóa. Redis không coi nó là một cấu trúc phân cấp có schema.

Ví dụ:

```text
keyspace = "customers"
id       = "tenant-a:u-100"

key = "customers:tenant-a:u-100"
```

Khóa này vẫn là **một Redis key**; Redis không tự hiểu `tenant-a` là bảng con hay tự tạo quan hệ giữa `tenant-a` và `u-100`. Tuy nhiên, nếu hệ thống có nhiều nơi tự ghép hoặc tách chuỗi khóa, id chứa dấu phân cách có thể làm logic parse bị nhầm.

Một số nguyên tắc hữu ích:

| Vấn đề | Gợi ý |
|---|---|
| ID chứa dấu `:` | Có thể dùng nếu hệ thống định nghĩa rõ, nhưng đừng parse khóa bằng cách chỉ `split(":")` rồi giả định luôn có đúng hai phần |
| Email hoặc URL làm ID | Cân nhắc vấn đề đổi giá trị, độ dài, ký tự đặc biệt, thông tin nhạy cảm trong key và xung đột |
| ID có cấu trúc `tenant + user` | Định nghĩa cách chuẩn hóa/escape hoặc định danh ổn định, tránh nhiều định dạng cùng biểu diễn một thực thể |
| Đổi tên prefix của entity | Cần chiến lược chuyển dữ liệu và chỉ mục phụ tương ứng |
| Nhiều team hoặc nhiều môi trường dùng chung Redis | Đặt namespace rõ ràng để tránh đụng khóa |

Không nên dùng `id` thay cho mọi thuộc tính truy vấn. Nếu cần tìm theo `email`, `phone` hoặc `status`, hãy thiết kế chỉ mục phù hợp, hay một nguồn dữ liệu chuyên truy vấn; không phải cứ đặt hết các trường vào tên key là Redis Repository sẽ tự sinh truy vấn theo chúng.

## 9. Liên hệ giữa keyspace, ID và hash slot trong Redis Cluster

Trong Redis Cluster, **tên khóa vật lý** là đầu vào để Redis tính hash slot (0–16383). Ví dụ:

```text
customers:u-100 ── hash slot ──> primary A
customers:u-101 ── hash slot ──> primary C
customers       ── hash slot ──> primary B
```

Sơ đồ chỉ minh họa: các slot và primary cụ thể do thuật toán hash và topology hiện hành quyết định. Cùng tiền tố `customers:` **không có nghĩa** hai khóa sẽ nằm cùng một primary. Khóa quản lý keyspace `customers` cũng có thể ở slot khác với các khóa entity `customers:<id>`.

Điều này quan trọng vì một lần `save()` của repository có thể cần ghi:

1. HASH chính của entity;
2. cấu trúc quản lý các entity trong keyspace;
3. các index phụ của thuộc tính `@Indexed`;
4. metadata liên quan đến TTL, nếu được bật.

Các khóa phụ có thể thuộc nhiều hash slot. **Đừng suy ra** từ một lời gọi `repository.save()` rằng tất cả các thay đổi vật lý đó là một lệnh Redis nguyên tử trên toàn cluster. Giới hạn `CROSSSLOT`, transaction, pipelining và các thao tác nhiều khóa phụ thuộc vào từng API, cách triển khai và cấu hình Redis Cluster.

Một cách phổ biến của Redis để ép các tên khóa liên quan vào cùng slot là dùng *hash tag* trong dấu `{...}`. Tuy nhiên, đưa cùng một tag cố định vào mọi khóa của cả keyspace sẽ dồn dữ liệu vào một slot, gây mất cân bằng tải. Không đổi quy ước đặt khóa của Redis Repository hoặc thêm hash tag trên diện rộng nếu chưa xem xét nhu cầu phân tán và các cấu trúc index của nó.

## 10. TTL có thay đổi cách hình thành khóa không?

Không. TTL quyết định thời gian tồn tại của **khóa entity**, không phải thành phần dùng để ghép `keyspace:id`.

Ví dụ đặt TTL mặc định cho entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 300)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    // Constructor, getter và setter.
}
```

Với id `s-10`, khóa entity vẫn mang tên `sessions:s-10`; `timeToLive = 300` (giây) chỉ đặt thời hạn sống cho khóa đó. Có thể quan sát:

```bash
redis-cli TTL sessions:s-10
```

Với một số cấu hình Spring Data Redis, TTL còn liên quan đến listener cho sự kiện hết hạn, cập nhật chỉ mục và các bản sao tạm (*shadow copy/phantom copy*) dùng cho sự kiện. Do đó, ngay cả khi HASH chính hết hạn, những khóa phụ liên quan có thể vẫn xuất hiện trong một khoảng thời gian hoặc cần cơ chế dọn dẹp. Không suy ra mọi metadata của repository biến mất đúng cùng một mili giây với khóa entity chính.

Nếu dùng `@TimeToLive` trên thuộc tính của entity để cấp TTL động, cách tính thời gian hết hạn có thể thay đổi theo từng instance, nhưng công thức đặt **khóa chính** từ keyspace và id vẫn giữ nguyên.

## 11. Những lỗi thường gặp khi suy luận tên khóa

### Lỗi 1: “ID là `u-100`, vì sao `GET u-100` không có dữ liệu?”

Repository lưu entity với keyspace `customers` nên khóa chính là `customers:u-100`. Ngoài ra, dữ liệu entity thường được lưu trong HASH, vì thế `GET customers:u-100` không phù hợp với kiểu dữ liệu đó; dùng `HGETALL` khi cần quan sát bằng Redis CLI, và dùng `findById("u-100")` trong ứng dụng.

### Lỗi 2: “Đổi tên class thì dữ liệu không còn được tìm thấy”

Cần kiểm tra keyspace thực tế trước và sau khi đổi. Nếu keyspace được khai báo cố định qua `@RedisHash("customers")`, việc đổi tên Java class thường không thay đổi tiền tố chính; tuy nhiên metadata kiểu Java bên trong HASH có thể vẫn cần xem xét. Nếu để hệ thống suy ra keyspace từ metadata loại entity, việc đổi tên/namespace có thể dẫn đến tên khóa khác. Di chuyển dữ liệu phải xử lý cả khóa chính lẫn các khóa phụ của repository.

### Lỗi 3: “`findById()` tìm được nhưng `findAll()` hoặc `findByEmail()` thiếu dữ liệu”

Kiểm tra bản ghi có được ghi bằng repository hay bằng lệnh Redis thủ công. Chỉ tạo HASH chính chưa chắc đã tạo/cập nhật tập quản lý keyspace và index. Nếu TTL hoặc ghi/xóa ngoài repository làm cấu trúc phụ không đồng bộ, kết quả duyệt/tìm qua index cũng có thể khác với đọc trực tiếp theo ID.

### Lỗi 4: “`SCAN MATCH customers*` trả nhiều khóa hơn số khách hàng”

Pattern tìm khóa là thao tác ở cấp Redis keyspace vật lý: nó có thể lấy cả HASH entity, SET quản lý keyspace và index phụ. Cần xem `TYPE` từng khóa hoặc dùng API repository thích hợp để thao tác với entity.

### Lỗi 5: “Hai class cùng ID và cùng `@RedisHash` gây ghi đè nhau”

Hai class độc lập về mặt Java vẫn có thể cùng địa chỉ Redis nếu chúng dùng chung keyspace và id. Cần thay đổi cách đặt namespace hoặc đảm bảo chúng thật sự chia sẻ một mô hình lưu trữ có chủ đích.

### Lỗi 6: “Đặt `id` mới rồi `save()` thì khóa cũ phải tự biến mất”

Với quy tắc ghép keyspace/id, id mới xác định một địa chỉ mới. Việc xóa dữ liệu cũ là bước nghiệp vụ riêng, không thể suy ra chỉ từ lệnh save object đã đổi id.

## 12. Ví dụ đầy đủ: từ đối tượng Java đến khóa Redis

Giả sử hệ thống có hai loại dữ liệu:

```java
@RedisHash("customers")
class Customer {
    @Id String id;
    String name;
}

@RedisHash("orders")
class Order {
    @Id String id;
    String customerId;
}
```

Khi lưu:

```text
Customer{id="42", name="Mai"}
    → customers:42

Order{id="42", customerId="42"}
    → orders:42

Order{id="43", customerId="42"}
    → orders:43
```

`orders:42` và `orders:43` có thể chứa thuộc tính `customerId = "42"`, nhưng Redis Repository **không tự tạo khóa ngoại** tới `customers:42`. Thuộc tính tham chiếu chỉ là dữ liệu của Order, trừ khi ứng dụng xây dựng cơ chế tham chiếu hoặc index riêng.

Nếu xóa `customers:42`, Redis không tự xóa `orders:42` hoặc `orders:43`; ngược lại, xóa `orders:42` không ảnh hưởng đến `customers:42`. Quy tắc hình thành khóa phân biệt địa chỉ lưu trữ, chứ không mã hóa quan hệ nghiệp vụ hay xóa liên đới.

Để tìm tất cả order của một khách hàng, cần cấu trúc truy vấn phù hợp (ví dụ một secondary index ở thuộc tính `customerId`, nếu mô hình/phiên bản hỗ trợ yêu cầu) thay vì suy diễn rằng mọi order mang cùng `customerId` được đặt chung dưới một khóa Redis.

## 13. Những quyết định thiết kế nên chốt từ đầu

| Quyết định | Tác động đến khóa và repository |
|---|---|
| Tên keyspace của entity | Quyết định tiền tố vật lý và khả năng tương thích dữ liệu sau khi nâng cấp |
| Kiểu và nguồn cấp ID | Quyết định phần hậu tố, khả năng truy xuất lại entity, xung đột định danh |
| Quy ước phân cách/chuẩn hóa ID | Tránh nhầm lẫn khi gỡ lỗi, đổi định dạng hoặc phối hợp nhiều dịch vụ |
| Có nhiều entity dùng chung keyspace không | Ảnh hưởng nguy cơ ghi đè và xung đột metadata |
| Có cần `findAll()` hoặc tìm theo thuộc tính không | Quyết định cấu trúc phụ và chỉ mục mà repository phải duy trì |
| Có dùng TTL hoặc Redis Cluster không | Ảnh hưởng vòng đời khóa phụ, phân bổ slot, hiệu năng và tính nhất quán |
| Có tác vụ ghi Redis thủ công song song repository không | Cần thống nhất việc quản lý HASH, tập keyspace và index |

Một quy ước đơn giản, bền vững cho bài toán thông thường là đặt **keyspace tường minh theo loại entity**, sử dụng **ID bất biến và duy nhất trong keyspace**, quản lý lifecycle thông qua repository, và chỉ thao tác trực tiếp trên khóa vật lý khi hiểu rõ những metadata phụ mà Spring Data Redis tạo ra.

## 14. Tự kiểm tra kiến thức

1. Entity khai báo `@RedisHash("products")` và `@Id String id = "p-5"`. Khóa chính là gì?  
   **Đáp án:** `products:p-5`.
2. Một `Customer` và một `Order` đều có id `"42"`, tương ứng keyspace `customers` và `orders`. Có đè nhau không?  
   **Đáp án:** Không, vì khóa vật lý là `customers:42` và `orders:42`.
3. Tại sao `SCAN MATCH customers*` có thể tìm thấy khóa không phải HASH khách hàng?  
   **Đáp án:** Repository có thể tạo SET quản lý keyspace, index và metadata phụ cùng prefix.
4. Vì sao tự `HSET customers:u-100` rồi gọi `findAll()` chưa chắc có kết quả mong đợi?  
   **Đáp án:** Lệnh HSET thủ công không đồng bộ chắc chắn những cấu trúc phụ do repository quản lý.
5. Đổi `@RedisHash("customers")` thành `@RedisHash("clients")` có tự chuyển dữ liệu không?  
   **Đáp án:** Không; đó là hai namespace vật lý khác nhau, cần quy trình migration nếu muốn giữ dữ liệu cũ.
6. `@RedisHash(timeToLive = 300)` có biến khóa `sessions:s-10` thành `sessions:300:s-10` không?  
   **Đáp án:** Không; TTL ảnh hưởng thời gian sống, không trở thành một phần của tên khóa.

## 15. Kết luận

Redis Repository hình thành **khóa chính của entity** từ **keyspace** và **định danh** theo quy tắc phổ biến `<keyspace>:<id>`. `@RedisHash` xác lập không gian tên, còn `@Id` xác lập giá trị phân biệt từng entity. Đó là lý do `findById(id)` có thể truy cập đúng dữ liệu mà ứng dụng không phải tự xây chuỗi tên khóa.

Vì repository còn duy trì tập quản lý và chỉ mục phụ, việc hiểu tên khóa chính mới chỉ là điểm bắt đầu. Khi cần gỡ lỗi, thay đổi keyspace, dùng TTL, triển khai Redis Cluster hoặc trộn thao tác Redis thủ công với repository, phải tính đến **toàn bộ những khóa vật lý liên quan** và vòng đời của chúng.

## Tài liệu tham khảo

- [Spring Data Redis Reference — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): cách ánh xạ entity, keyspace và các thành phần hỗ trợ repository.
- [Spring Data Redis Reference — Keyspaces](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/keyspaces.html): khai báo `@RedisHash` và cấu hình keyspace.
- [Spring Data Redis Reference — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): chuyển đổi đối tượng Java sang Redis Hash.
- [Spring Data Redis Reference — Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): các chỉ mục phụ dùng trong truy vấn repository.
- [Spring Data Redis Reference — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): TTL, sự kiện hết hạn và hệ quả với dữ liệu repository.
- [Redis — Data types](https://redis.io/docs/latest/develop/data-types/): phân biệt Redis Hash, Set và các loại giá trị của khóa.
