# Dữ liệu ghi ngoài Repository và nguy cơ chỉ mục không đồng bộ

Trong Spring Data Redis, một `RedisRepository` không chỉ lưu nội dung entity vào Redis Hash. Khi entity có thuộc tính được đánh dấu `@Indexed`, framework còn quản lý **các khóa phụ phục vụ truy vấn**; với một số thao tác, nó cũng duy trì tập khóa thuộc một keyspace và metadata phục vụ vòng đời dữ liệu. Những cấu trúc này được cập nhật khi thao tác đi qua cơ chế ánh xạ của **Spring Data Redis Repository**.

Vấn đề xuất hiện khi cùng dữ liệu đó lại được sửa trực tiếp bằng `redis-cli`, Redis command, `RedisTemplate` hoặc một dịch vụ khác. Việc sửa Redis Hash thành công **không có nghĩa** các chỉ mục mà Repository quản lý cũng được cập nhật. Hệ quả có thể là `findById()` đọc thấy giá trị mới, nhưng `findByEmail()` không thấy bản ghi; hoặc truy vấn theo giá trị cũ vẫn trả một bản ghi đã thay đổi.

Bài học này làm rõ điều gì được lưu, khi nào chỉ mục bị lệch, cách quan sát và khôi phục sự nhất quán, cũng như cách tổ chức luồng ghi để hạn chế lỗi.

## 1. Redis Repository quản lý nhiều cấu trúc dữ liệu

Giả sử một ứng dụng lưu khách hàng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    private String name;

    @Indexed
    private String email;

    @Indexed
    private String status;

    public Customer() {}

    public Customer(String id, String name, String email, String status) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.status = status;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
```

Repository tương ứng:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);

    List<Customer> findByStatus(String status);
}
```

Giả sử ứng dụng đã cấu hình Spring Data Redis và kích hoạt cơ chế Redis Repository, lệnh:

```java
customerRepository.save(new Customer(
        "c-100",
        "An",
        "an@example.test",
        "ACTIVE"
));
```

không chỉ làm tồn tại khóa chính `customers:c-100`. Ở mức logic, repository còn có thể quản lý:

| Nhóm dữ liệu | Mục đích | Ví dụ minh họa |
|---|---|---|
| **Hash entity** | Chứa giá trị thuộc tính của một khách hàng | `customers:c-100` |
| **Tập quản lý keyspace** | Hỗ trợ xác định các entity thuộc loại `Customer` | `customers` |
| **Secondary index theo email** | Tìm các entity có email cụ thể | `customers:email:an@example.test` |
| **Secondary index theo status** | Tìm các entity có trạng thái cụ thể | `customers:status:ACTIVE` |
| **Metadata quản lý chỉ mục/vòng đời** | Hỗ trợ cập nhật và dọn quan hệ index khi dữ liệu đổi/xóa | Các khóa phụ do Spring Data quản lý |

Các tên khóa chỉ mục ở bảng phản ánh **quy ước thường gặp** của Spring Data Redis, không phải hợp đồng để ứng dụng tự ghi trực tiếp; biểu diễn thực tế còn phụ thuộc cấu hình mapping, serializer và phiên bản thư viện. Mục tiêu của bảng là phân biệt rõ **Hash chứa dữ liệu** với **các cấu trúc truy vấn phụ**.

Sơ đồ:

```text
            customerRepository.save(customer)
                           |
                 Spring Data mapping
                           |
          +----------------+-----------------+
          |                |                 |
          v                v                 v
     Entity HASH      Keyspace SET     Secondary index SETs
  customers:c-100       customers       customers:email:...
                                       customers:status:...
          |                                  |
          |                         lưu liên hệ đến entity
          +----------------------------------+
```

Redis không tự hiểu annotation `@Indexed`. Chính lớp Spring Data tạo và sử dụng cấu trúc index. Vì vậy Redis server vẫn có thể chấp nhận lệnh `HSET`, `HDEL`, `DEL` hay `EXPIRE` trực tiếp mà không hề biết phải duy trì các chỉ mục của Repository.

## 2. Vì sao truy vấn theo ID và truy vấn theo thuộc tính có thể khác nhau?

`findById("c-100")` đã biết định danh và keyspace, vì thế Repository có thể tạo khóa chính `customers:c-100` rồi nạp Hash tương ứng.

Ngược lại, `findByEmail("an@example.test")` không biết trước ID nào có email đó. Với cơ chế **secondary index** của Redis Repository, luồng tra cứu về cơ bản là:

1. Xác định index dành cho thuộc tính `email` với giá trị `an@example.test`.
2. Tìm những tham chiếu đến entity trong tập index tương ứng.
3. Nạp entity từ các khóa chính mà tập index chỉ đến.

```text
findById("c-100")
    |
    +--> customers:c-100 --> HASH hiện tại

findByEmail("an@example.test")
    |
    +--> index email=an@example.test
               |
               +--> tham chiếu customers:c-100
                         |
                         +--> HASH hiện tại
```

Nếu Hash và index không thống nhất, hai đường đọc có thể trả kết quả khác nhau. Một Redis Hash có thể tồn tại hợp lệ, nhưng **không được index liệt kê**; hoặc index có thể chứa tham chiếu đến khóa đã bị xóa hay thuộc tính đã đổi.

Đây là khác biệt quan trọng giữa:

- **Sự tồn tại vật lý của một Hash:** câu hỏi “Redis còn khóa `customers:c-100` hay không?”.
- **Khả năng tìm kiếm qua Repository:** câu hỏi “Các cấu trúc index của Spring Data có còn trỏ đúng đến entity với điều kiện truy vấn này không?”.

Hai điều kiện cần được kiểm tra riêng khi chẩn đoán lỗi.

## 3. Tình huống điển hình: `HSET` ngoài Repository làm index bị cũ

Giả sử entity ban đầu được tạo bằng Repository:

```java
customerRepository.save(new Customer(
        "c-100", "An", "an@example.test", "ACTIVE"
));
```

Ở thời điểm này, dữ liệu logic là:

```text
customers:c-100 (HASH)
  id     = c-100
  name   = An
  email  = an@example.test
  status = ACTIVE

email index:  an@example.test  --> customers:c-100
status index: ACTIVE           --> customers:c-100
```

Sau đó, một công cụ vận hành sửa thuộc tính email trực tiếp:

```bash
redis-cli HSET customers:c-100 email binh@example.test
```

Lệnh `HSET` trả kết quả thành công nếu Redis chấp nhận cập nhật field. Tuy nhiên, nó **chỉ tác động đến Hash** được chỉ định. Nó không chạy trình ánh xạ Repository, nên không cập nhật quan hệ trong secondary index của Spring Data.

Trạng thái sau thao tác có thể là:

```text
HASH customers:c-100:
  email = binh@example.test       <-- giá trị đã đổi

Index email=an@example.test:
  vẫn chứa customers:c-100        <-- tham chiếu cũ

Index email=binh@example.test:
  không chứa customers:c-100      <-- thiếu tham chiếu mới
```

Từ ứng dụng:

```java
// Nạp thẳng khóa chính; có thể thấy email mới.
Customer byId = customerRepository.findById("c-100")
        .orElseThrow();
System.out.println(byId.getEmail()); // binh@example.test

// Tìm qua index email mới; có thể không tìm thấy c-100.
List<Customer> byNewEmail =
        customerRepository.findByEmail("binh@example.test");

// Tìm qua index email cũ; vẫn có thể còn ứng viên c-100.
List<Customer> byOldEmail =
        customerRepository.findByEmail("an@example.test");
```

**Không nên khẳng định mọi phiên bản/cấu hình luôn trả cùng một kiểu sai lệch**: một số bước đọc có thể bỏ qua khóa không còn tồn tại hoặc áp dụng xử lý bổ sung. Nhưng bản chất là **index cũ không được cập nhật bởi `HSET` thủ công**, và kết quả truy vấn theo index không còn được bảo đảm phản ánh dữ liệu Hash hiện tại.

Nếu thao tác thay đổi một field **không được index**, chẳng hạn `name`, truy vấn qua `email` thường không cần đổi thành viên index chỉ vì `name` đổi. Tuy vậy, luồng ghi thủ công vẫn phải lưu đúng biểu diễn field và xử lý tình huống cạnh tranh với Repository; không thể từ một ví dụ không có lỗi mà kết luận mọi ghi trực tiếp đều an toàn.

## 4. Những thao tác ngoài Repository có thể gây lệch dữ liệu gì?

Không phải mọi lệnh Redis đều gây ra cùng một hậu quả. Cần xét **khóa nào** bị sửa và **metadata nào** đáng lẽ phải đổi cùng.

| Thao tác ngoài Repository | Điều thay đổi trực tiếp | Nguy cơ với Repository |
|---|---|---|
| `HSET customers:c-100 email ...` | Thay giá trị field được `@Indexed` | Index giá trị cũ còn tham chiếu, index giá trị mới thiếu tham chiếu |
| `HDEL customers:c-100 email` | Xóa field được index | Index của email cũ có thể vẫn còn |
| `HSET customers:c-999 ...` tạo Hash mới | Tạo một entity vật lý chưa qua mapping | Tập keyspace/index và metadata cần thiết có thể thiếu; `findAll()` hoặc `findByEmail()` bỏ sót |
| `DEL customers:c-100` hoặc `UNLINK ...` | Xóa Hash chính | Index có thể giữ tham chiếu tới khóa không tồn tại; tập keyspace có thể còn phần tử cũ |
| `EXPIRE customers:c-100 60` | Đặt TTL trực tiếp lên Hash | Vòng đời index/metadata không nhất thiết được đồng bộ như khi đi qua Repository |
| `PERSIST customers:c-100` | Bỏ TTL của Hash | Có thể làm cơ chế xử lý hết hạn hoặc chính sách TTL của entity khác với dự kiến |
| `HSET customers:c-100 name ...` | Thay field không index | Có thể đọc được giá trị mới qua ID, nhưng vẫn có nguy cơ mất cập nhật khi Repository save dữ liệu cũ |
| `RENAME customers:c-100 customers:c-200` | Đổi tên khóa vật lý | ID bên trong entity, tập keyspace, index và tham chiếu có thể giữ địa chỉ cũ |
| Ghi trực tiếp vào tập index | Sửa thành viên index thủ công | Truy vấn thừa/thiếu, khó phân biệt dữ liệu đúng với dữ liệu bị can thiệp |

Các lệnh Redis trên chạy ở cấp **key/value**, không được bảo đảm sẽ cập nhật quy tắc quan hệ giữa các khóa mà Spring Data Redis dùng cho Repository.

### Sử dụng `RedisTemplate` có tránh được vấn đề không?

Không tự động. Ví dụ:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

public class DirectRedisWriter {
    private final StringRedisTemplate template;

    public DirectRedisWriter(StringRedisTemplate template) {
        this.template = template;
    }

    public void changeEmailDirectly() {
        template.opsForHash().put(
                "customers:c-100",
                "email",
                "binh@example.test");
    }
}
```

`StringRedisTemplate` thao tác Redis Hash theo lệnh Redis thông thường, **không gọi `CustomerRepository.save()` và không điều phối index của Repository**. Tương tự, `RedisTemplate.opsForHash()`, Redis CLI, client Lettuce/Jedis độc lập hay một dịch vụ viết trực tiếp đến cùng Hash đều có thể làm lệch index.

Ngoài ra, template thao tác trực tiếp có thể dùng serializer khác với converter của Repository. Khi đó, ngay cả một field chỉ cần sửa đơn giản cũng có thể bị ghi sai kiểu/binary format. Sự tương thích serializer là một yêu cầu riêng, **không thay thế việc duy trì chỉ mục**.

## 5. Ghi và cập nhật đúng cách thông qua Repository

Khi cần thay đổi email của entity thuộc quyền quản lý của `CustomerRepository`, đường đi an toàn về mặt mapping là nạp entity, thay thuộc tính rồi lưu qua Repository:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer changeEmail(String id, String newEmail) {
        Customer customer = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown customer: " + id));

        customer.setEmail(newEmail);
        return repository.save(customer);
    }
}
```

Khi thao tác đi qua Repository, Spring Data Redis biết metadata `@Indexed` của `Customer` và có thể cập nhật các cấu trúc index phù hợp cùng với dữ liệu entity.

> Lưu ý về tính nguyên tử: Việc gọi `repository.save()` không tự động chứng minh mọi cập nhật Hash, index và tập keyspace đều là một giao dịch nguyên tử trước mọi truy cập đồng thời. Riêng Redis Cluster, các khóa vật lý liên quan còn có thể nằm trên những hash slot khác nhau. `@Transactional` ở tầng Spring cũng không nên được gắn vào ví dụ rồi suy ra nó bảo đảm giao dịch Redis nhiều khóa; tính transaction cần được cấu hình và đánh giá riêng.

Ví dụ trên cho thấy **đường ghi sử dụng đúng cơ chế mapping/index của Repository**. Nếu nhiều writer đồng thời sửa cùng một entity, còn phải xử lý nguy cơ *lost update* (mất cập nhật) bằng chính sách phối hợp ghi thích hợp.

### Trường hợp nhiều writer cùng sửa dữ liệu

```text
T0: Service A đọc Customer(email=old, status=ACTIVE)
T1: Service B ghi thẳng HSET status BLOCKED
T2: Service A đổi email rồi repository.save(customer cũ)

Kết quả có thể:
  - status bị ghi đè về ACTIVE,
  - chỉ mục của status lệch ở một thời điểm,
  - dữ liệu cuối cùng phụ thuộc thứ tự và cơ chế ghi.
```

Repository không thể suy ra một giao dịch ngoài luồng đã sửa Hash trong lúc entity đang được giữ trong bộ nhớ ứng dụng. Khi có nhiều hệ thống phải ghi cùng dữ liệu, nên xác định **một nguồn ghi có thẩm quyền** và một giao thức cập nhật thống nhất.

## 6. Khóa được tạo thủ công không đồng nghĩa entity đã được đăng ký với Repository

Một tình huống khác là chương trình import dữ liệu tạo nhiều Hash:

```bash
redis-cli HSET customers:c-900 id c-900 name "Imported User" \
  email imported@example.test status ACTIVE
```

Sau lệnh này, `TYPE customers:c-900` có thể trả `hash` và `HGETALL` cho thấy dữ liệu. Tuy nhiên, đối tượng chưa chắc xuất hiện trong:

- `customerRepository.findAll()`;
- `customerRepository.count()`;
- `customerRepository.findByEmail("imported@example.test")`;
- `customerRepository.findByStatus("ACTIVE")`.

Lý do là lệnh import vừa rồi chỉ tạo Hash, trong khi Repository còn cần các cấu trúc phụ để duyệt và truy vấn. Ngoài ra, khi nạp Hash thủ công, các field bắt buộc/metadata kiểu Java có thể khác định dạng mà converter mong đợi, làm phát sinh lỗi ánh xạ.

Một thao tác import phù hợp hơn khi muốn entity chịu sự quản lý của Repository:

```java
Customer imported = new Customer(
        "c-900",
        "Imported User",
        "imported@example.test",
        "ACTIVE"
);

customerRepository.save(imported);
```

Khi import số lượng lớn, có thể dùng `saveAll(...)` theo batch hợp lý nếu phù hợp tải và phiên bản triển khai; vẫn cần đo hiệu năng. Khối lượng ghi index/tập keyspace khiến chi phí thường cao hơn việc chỉ chạy một lệnh `HSET`, nhưng đó là chi phí duy trì khả năng truy vấn đúng.

## 7. Khóa bị xóa hoặc hết hạn bên ngoài Repository

### Xóa trực tiếp bằng `DEL` hoặc `UNLINK`

```bash
redis-cli DEL customers:c-100
```

Hash `customers:c-100` biến mất, nhưng các tập index từng trỏ đến nó có thể vẫn còn thành viên. Lúc này:

- `findById("c-100")` thường không còn trả entity;
- truy vấn theo email/status vẫn có thể gặp tham chiếu cũ;
- tập keyspace/index có thể phình ra hoặc thống kê sai;
- cách xử lý tham chiếu không tồn tại phụ thuộc đường truy vấn và cấu hình thực tế.

Xóa qua `customerRepository.deleteById("c-100")` cho phép cơ chế Repository xử lý những cấu trúc mà nó sở hữu. Không nên dùng `DEL` thủ công để xóa Hash entity rồi mặc định mọi index đã được làm sạch.

### TTL và cơ chế dọn index

Repository có thể quản lý TTL qua `@RedisHash(timeToLive = ...)` hoặc `@TimeToLive`. Với cấu hình hỗ trợ, Spring Data Redis xử lý sự kiện khóa hết hạn để phục vụ dọn dẹp các cấu trúc index liên quan. Tuy nhiên, cần nhớ:

1. Redis chỉ phát sự kiện hết hạn theo cấu hình *keyspace notifications* và cơ chế sự kiện thực tế; không có cam kết mọi consumer luôn nhận đủ mọi sự kiện.
2. Listener có thể không hoạt động, khởi động muộn hoặc bị gián đoạn; trong Redis Cluster, cấu hình nhận sự kiện và phạm vi node còn cần chú ý.
3. Việc đặt hoặc xóa TTL **trực tiếp** bỏ qua thông tin vòng đời mà Repository có thể cần duy trì.
4. Một số cấu hình dùng bản sao tạm của dữ liệu hết hạn để phục vụ sự kiện, vì vậy có thể có khóa phụ liên quan đến quá trình hết hạn.

Do đó, ngay cả khi ứng dụng chỉ dùng Repository để save, chính sách dọn index sau TTL cũng cần được thiết kế và quan sát. Không giả định rằng `EXPIRE` thủ công cho một Hash đã tạo và cập nhật đầy đủ toàn bộ cơ chế cleanup.

## 8. Nhận diện lệch chỉ mục trong môi trường thực hành

Mục tiêu chẩn đoán là so sánh **dữ liệu trong Hash** và **quan hệ index mà Repository đang dùng**. Ví dụ một bản ghi đã biết ID là `c-100`.

### Bước 1: Đọc khóa chính

```bash
redis-cli TYPE customers:c-100
redis-cli HGETALL customers:c-100
redis-cli HGET customers:c-100 email
redis-cli TTL customers:c-100
```

Các lệnh này xác định Hash tồn tại hay không, giá trị email hiện tại và TTL. Nếu `TYPE` trả kiểu khác `hash`, hãy dừng trước khi suy luận về field; có thể một hệ thống khác đã ghi sai kiểu tại cùng tên khóa.

### Bước 2: Quan sát tên khóa index

Trong môi trường thử nghiệm với keyspace như ví dụ:

```bash
# SCAN chỉ quét node đang kết nối; lặp với cursor đến khi bằng 0.
redis-cli SCAN 0 MATCH 'customers:email:*' COUNT 100
redis-cli SCAN 0 MATCH 'customers:status:*' COUNT 100

# Với một khóa index cụ thể lấy từ kết quả SCAN:
redis-cli TYPE customers:email:an@example.test
redis-cli SMEMBERS customers:email:an@example.test
```

Kết quả tên khóa phụ và thành viên phải được diễn giải theo **cấu hình Spring Data đang chạy**. Ví dụ tên index có thể thay đổi bởi custom mapping hoặc serializer. Không dùng các lệnh trên để ghi/sửa index trong production.

### Bước 3: So sánh với API Repository

```java
Customer direct = customerRepository.findById("c-100")
        .orElse(null);

List<Customer> oldEmail =
        customerRepository.findByEmail("an@example.test");

List<Customer> newEmail =
        customerRepository.findByEmail("binh@example.test");
```

Đối chiếu: Hash có email nào? Index của email nào chứa tham chiếu đến khóa chính? Hai truy vấn Repository trả về ID nào? Nếu Hash và index mâu thuẫn thì đó là dấu hiệu rõ ràng của việc không đồng bộ.

### Bước 4: Phân biệt vấn đề mapping với vấn đề index

Có ít nhất ba loại lỗi khác nhau:

| Quan sát | Hướng điều tra |
|---|---|
| `findById()` nạp sai field hoặc lỗi chuyển đổi | Kiểm tra Hash vật lý, serializer, `RedisConverter` và metadata entity |
| `findById()` đúng nhưng `findByEmail()` bỏ sót ID | Kiểm tra index theo email và lịch sử cập nhật field ngoài Repository |
| `findAll()` thiếu ID dù Hash có tồn tại | Kiểm tra tập keyspace, đường import/ghi trực tiếp và vòng đời khóa |

Không sửa hàng loạt chỉ mục trước khi xác định loại lỗi; nếu serializer hoặc metadata mapping mới là nguyên nhân, tự thêm phần tử vào SET sẽ không giải quyết được.

## 9. Những nguyên nhân thường gây mất đồng bộ trong dự án thật

### 9.1. Lệnh vận hành sửa dữ liệu trực tiếp

Người vận hành chạy `HSET` để “sửa nhanh” email hoặc status. Hash đúng ngay lập tức, nhưng index không nhận được thay đổi. Dự án nên có công cụ sửa dữ liệu đi qua service/repository được quản lý, cùng log người thực hiện và lý do sửa.

### 9.2. Import/migration chỉ ghi Hash

Script import dùng Redis client thuần vì nhanh, không tạo keyspace SET và secondary index. Sau khi import, đọc theo ID có thể chạy, còn truy vấn theo field thất bại. Quy trình import cần dùng repository hoặc bước tái tạo cấu trúc index tương ứng với mapping hiện hành.

### 9.3. Hai ứng dụng dùng chung một keyspace

Ứng dụng A dùng Redis Repository có `@Indexed`, còn B ghi trực tiếp theo cùng quy ước `customers:<id>`. B có thể không biết các khóa phụ mà A đang quản lý. Cần thống nhất **quyền sở hữu dữ liệu và hợp đồng ghi** giữa hai ứng dụng, đặc biệt khi nâng cấp phiên bản độc lập.

### 9.4. Thay đổi annotation hoặc mapping mà không chuyển dữ liệu

Ví dụ trước đây `status` không được index, phiên bản mới bổ sung `@Indexed`. Các Hash cũ không nhất thiết tự có index đúng chỉ vì ứng dụng khởi động với annotation mới. Tương tự, đổi tên field, đổi keyspace hoặc thay converter đòi hỏi kế hoạch backfill/migration.

### 9.5. Xóa/hết hạn nhưng thiếu cơ chế cleanup

Hash hết hạn trong Redis, nhưng listener hoặc luồng cleanup không nhận được sự kiện cần thiết; tập keyspace/index có thể còn tham chiếu cũ. Cần theo dõi kích thước index và có phương án đối soát thay vì xem sự kiện hết hạn như một hàng đợi bền vững, bảo đảm chuyển phát.

### 9.6. Cập nhật đồng thời không có cơ chế phối hợp

Hai writer sửa cùng một Hash hoặc một writer dùng Repository còn writer kia dùng Hash commands. Thứ tự thao tác và dữ liệu đọc trước đó quyết định kết quả cuối cùng; ngay cả việc cập nhật index đúng ở từng lời gọi Repository cũng không tự giải quyết lỗi mất cập nhật do writer khác tạo ra.

## 10. Nguyên tắc phòng tránh khi cần sử dụng Redis Repository

**Nguyên tắc ưu tiên là một đường ghi có thẩm quyền cho entity.** Nếu entity thuộc phạm vi Repository, tạo, cập nhật và xóa qua Repository hoặc service bọc Repository để giữ hợp đồng index.

Ví dụ một cổng ghi ứng dụng:

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerCommands {

    private final CustomerRepository repository;

    public CustomerCommands(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(String id, String name, String email) {
        Customer customer = new Customer(id, name, email, "ACTIVE");
        return repository.save(customer);
    }

    public Customer changeStatus(String id, String status) {
        Customer customer = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown customer: " + id));
        customer.setStatus(status);
        return repository.save(customer);
    }

    public void remove(String id) {
        repository.deleteById(id);
    }
}
```

Các service khác gọi các operation của `CustomerCommands` thay vì tự tạo tên khóa `customers:<id>` rồi `HSET`. Nếu có yêu cầu phức tạp về đồng thời, có thể bổ sung cơ chế phiên bản, optimistic locking thích hợp hoặc điều phối tuần tự ở cấp nghiệp vụ; quyết định cụ thể tùy khả năng thực tế của stack.

Những biện pháp thực tế:

- **Quy định owner của dữ liệu:** thành phần nào được phép thay đổi Hash entity và chỉ mục.
- **Phân quyền Redis:** hạn chế quyền ghi trực tiếp cho tài khoản chỉ phục vụ truy vấn/vận hành, khi phù hợp với kiến trúc triển khai.
- **Đóng gói lệnh ghi:** cung cấp API/service tạo, sửa, xóa thay vì để nhiều hệ thống tự sửa Hash.
- **Có luồng import chuẩn:** chạy qua Repository hoặc quy trình tái tạo chỉ mục đã được kiểm chứng.
- **Theo dõi độ lệch:** ghi nhận số entity, số tham chiếu index bất thường, số lỗi ánh xạ/khóa mất.
- **Thiết kế cho cạnh tranh cập nhật:** trường hợp nhiều writer cần quy tắc phối hợp, tránh đọc cũ rồi ghi đè thay đổi mới.
- **Xem xét TTL và listener:** kiểm tra cấu hình cleanup thực tế, có quy trình đối soát khi sự kiện bị bỏ lỡ.

## 11. Khi một hệ thống khác bắt buộc phải ghi cùng Redis

Trong một số kiến trúc, ETL, batch processor hoặc hệ thống legacy không thể lập tức chuyển sang dùng Spring Data Redis Repository. Khi đó cần chọn một hợp đồng đồng bộ có chủ đích.

| Phương án | Cách vận hành | Đánh đổi |
|---|---|---|
| **Tất cả writer gọi service sở hữu Repository** | Một nơi chịu trách nhiệm lưu Hash và index | Cần API rõ ràng và tính sẵn sàng của service |
| **Writer gửi yêu cầu/event, service Repository xử lý** | Dùng message/stream làm đầu vào, một consumer cập nhật qua Repository | Có độ trễ; cần idempotency, xử lý retry/thứ tự sự kiện |
| **Writer tự cập nhật tất cả cấu trúc theo giao thức thống nhất** | Tự quản Hash, keyspace SET, index, cleanup | Phức tạp và phụ thuộc internal mapping; dễ lệch khi nâng cấp |
| **Tách nguồn dữ liệu và dựng read model riêng** | Writer ghi vào nguồn chuẩn, pipeline tạo index phục vụ đọc | Chấp nhận nhất quán cuối cùng; cần đối soát |

Nếu dùng event/queue, **phát event thành công không tự bảo đảm index đã được cập nhật**. Thiết kế cần ghi nhận lỗi, xử lý lặp, thứ tự theo entity và cơ chế replay/rebuild. Nếu sử dụng transaction hoặc Lua script để duy trì nhiều khóa Redis, đặc biệt trong Redis Cluster, phải tính giới hạn về hash slot và tính nguyên tử của từng lệnh; không tự động có giao dịch xuyên mọi shard.

Một lựa chọn khác là bỏ mô hình secondary index của Redis Repository cho dữ liệu có rất nhiều writer độc lập, thay bằng một thiết kế dữ liệu/truy vấn mà mọi writer đều có thể tuân thủ. Đây là quyết định kiến trúc, không chỉ là đổi vài lệnh Redis.

## 12. Đối soát và khôi phục chỉ mục bị lệch

Khi đã phát hiện dữ liệu sai, mục tiêu là tái lập quan hệ đúng giữa:

```text
  Entity key hiện có
       |
       +--> thuộc tính hiện tại trong Hash
       |
       +--> thành viên của tập keyspace
       |
       +--> quan hệ của các secondary index tương ứng
```

Một quy trình phục hồi có kiểm soát:

1. **Chọn nguồn dữ liệu chuẩn.** Hash hiện tại có phải sự thật nghiệp vụ hay dữ liệu từ database/hệ thống khác mới là nguồn chuẩn? Nếu Hash đã bị ghi sai, rebuild index từ chính Hash sẽ hợp thức hóa dữ liệu sai.
2. **Xác định phạm vi ảnh hưởng.** Keyspace, các field có `@Indexed`, tập entity hoặc khoảng thời gian xảy ra ghi trực tiếp; đo khối lượng trước khi thao tác.
3. **Kiểm soát writer cạnh tranh.** Tạm dừng hoặc điều phối những writer gây lệch để quá trình đối soát không chạy đua với thay đổi liên tục.
4. **Duyệt dữ liệu chính xác theo phạm vi.** Nếu tập keyspace đã thiếu thành viên, không dựa hoàn toàn vào `repository.findAll()` để tìm toàn bộ Hash bị ảnh hưởng. Cần cơ chế quét thực tế các khóa entity (ví dụ `SCAN` theo prefix, xác minh `TYPE`) và loại khỏi danh sách những khóa index/metadata.
5. **Đối chiếu và tái tạo mapping/index theo hợp đồng hiện hành.** Khi có entity đầy đủ và hợp lệ, có thể cân nhắc ghi lại qua Repository để nó xây dựng lại cấu trúc mà nó quản lý. Tuy nhiên, chỉ `save()` lại từng entity **chưa chắc xóa hết mọi tham chiếu index cũ** nếu metadata theo dõi đã sai; cần kiểm tra kết quả và phương án xử lý index stale.
6. **Kiểm tra quan hệ hai chiều.** Entity có email hiện tại thì index tương ứng phải có tham chiếu; index không được còn tham chiếu tới entity đã mất hoặc giá trị không còn phù hợp.
7. **Ghi nhận, đo đạc và chuẩn bị rollback.** Đếm entity đã xử lý, index đã sửa, lỗi chuyển đổi, thay đổi trong quá trình quét; giữ sao lưu/snapshot vận hành phù hợp trước khi sửa hàng loạt.
8. **Đóng lỗ hổng gây lỗi.** Nếu không sửa đường ghi ngoài Repository hoặc cleanup TTL, dữ liệu sẽ sớm lệch trở lại.

Không nên xóa bừa tất cả khóa có prefix `customers*` để “làm sạch index”: mẫu đó có thể bao gồm chính Hash entity và nhiều loại khóa quan trọng. Việc tái tạo index phụ phải biết **đúng tên, kiểu và chủ sở hữu từng khóa**.

### Vì sao `findAll()` không đủ làm nguồn đối soát?

Nếu một importer tự tạo `customers:c-900` nhưng chưa thêm vào tập keyspace mà Repository duy trì, `findAll()` có thể không thấy `c-900`. Chạy:

```java
for (Customer customer : customerRepository.findAll()) {
    customerRepository.save(customer);
}
```

không nhất thiết xử lý được những Hash **đã bị bỏ sót ngay từ bước liệt kê**. Để đối soát dữ liệu nguồn, cần kênh inventory độc lập với chỉ mục nghi ngờ đã sai, cùng biện pháp lọc khóa entity thực sự.

### Vì sao `SCAN` cũng không phải snapshot chính xác?

`SCAN` giúp xử lý khóa theo lô nhỏ, nhưng có thể trả khóa trùng và không đảm bảo tập khóa cố định khi Redis liên tục nhận ghi/xóa. Trong Redis Cluster, mỗi primary có cursor quét riêng, còn slot có thể được di chuyển giữa các node. Vì vậy quy trình rebuild nên thiết kế idempotent, theo dõi khóa bị bỏ sót và cân nhắc chạy lại/đối soát bổ sung hoặc tạm dừng thay đổi dữ liệu để đạt yêu cầu nhất quán.

## 13. Redis Cluster làm bài toán đồng bộ index phức tạp hơn thế nào?

Trong Redis Cluster, các khóa `customers:c-100`, `customers:email:an@example.test` và `customers` được tính hash slot **dựa trên tên khóa vật lý**. Chúng không mặc nhiên nằm trên cùng primary chỉ vì cùng bắt đầu bằng `customers`.

```text
Redis Cluster

Primary A: customers:c-100
Primary B: customers:email:an@example.test
Primary C: customers

(Sơ đồ phân bố chỉ minh họa.)
```

Nếu một writer tự dùng Redis transaction hoặc Lua script để cập nhật nhiều khóa index, Redis Cluster có ràng buộc về các thao tác nhiều khóa khác hash slot. Không nên cho rằng một lệnh hoặc script có thể cập nhật nguyên tử mọi Hash và index trên mọi primary.

Ngoài vấn đề nguyên tử:

- Một lệnh `SCAN` trên một primary không bao phủ cả cluster; muốn inventory đầy đủ phải có chiến lược duyệt các primary.
- Resharding/failover trong lúc đối soát có thể gây xử lý trùng, bỏ sót hoặc cần retry.
- Khi một phần cập nhật Hash/index thành công và phần còn lại thất bại, hệ thống cần cơ chế phục hồi theo giao thức đồng bộ đã lựa chọn.

Vì vậy, **đảm bảo index đúng khi nhiều writer và nhiều slot** phải được xác định ở mức thiết kế, quan sát và xử lý lỗi, không chỉ dựa vào cú pháp `@Indexed`.

## 14. Bài thực hành tái hiện lỗi không đồng bộ

Chỉ thực hiện trong **Redis thử nghiệm riêng**, với entity và Repository như ở đầu bài. Mục tiêu là quan sát được khoảng cách giữa dữ liệu Hash và kết quả tìm qua secondary index.

### Chuẩn bị

Lưu một khách hàng bằng Repository:

```java
customerRepository.save(new Customer(
        "lab-01", "Lab User", "before@example.test", "ACTIVE"
));
```

Quan sát kết quả ban đầu:

```java
System.out.println(
        customerRepository.findById("lab-01").orElseThrow().getEmail());

System.out.println(
        customerRepository.findByEmail("before@example.test").size());
```

### Gây ra thay đổi ngoài Repository

Trong Redis CLI của môi trường thử nghiệm:

```bash
redis-cli HSET customers:lab-01 email after@example.test
redis-cli HGET customers:lab-01 email
```

Tiếp tục đọc:

```java
System.out.println(
        customerRepository.findById("lab-01").orElseThrow().getEmail());

System.out.println(
        customerRepository.findByEmail("before@example.test"));

System.out.println(
        customerRepository.findByEmail("after@example.test"));
```

Điểm cần quan sát là **giá trị field đã đổi nhưng cấu trúc index có thể vẫn thể hiện quan hệ cũ**. Với từng phiên bản/cấu hình, ghi lại dữ liệu Hash, tên các khóa index và ID trả về; không chỉ nhìn một con số `size()` rồi kết luận.

### Khôi phục bằng đường ghi hợp lệ

Trong môi trường lab, có thể thử lưu lại entity qua Repository:

```java
Customer current = customerRepository.findById("lab-01")
        .orElseThrow();
current.setEmail("after@example.test");
customerRepository.save(current);
```

Sau đó kiểm tra lại index cũ và mới. Đây là **thí nghiệm**, không phải lời hứa rằng một lần save sẽ sửa được mọi index stale trong production. Nếu còn tham chiếu sai, cần áp dụng quy trình đối soát/tái tạo cấu trúc phụ theo metadata hiện hành.

Cuối cùng dọn dữ liệu thử nghiệm qua `customerRepository.deleteById("lab-01")` và kiểm tra các khóa phụ liên quan trong môi trường lab.

## 15. Câu hỏi tự đánh giá

**1.** Tại sao `findById("c-100")` đọc được email mới nhưng `findByEmail(emailMới)` không trả entity?  
Vì tìm theo ID đọc Hash chính, còn tìm theo thuộc tính dựa trên secondary index; lệnh ghi ngoài Repository có thể đã đổi Hash mà chưa thêm quan hệ index mới.

**2.** Dùng `StringRedisTemplate.opsForHash().put(...)` trong cùng ứng dụng Spring Boot có tự cập nhật `@Indexed` không?  
Không. Đây là thao tác Hash cấp thấp, không đồng nghĩa với `repository.save()`.

**3.** Chạy `HSET` để tạo một Hash mới có bảo đảm `findAll()` tìm thấy không?  
Không. Tập quản lý keyspace hoặc những metadata khác của Repository có thể chưa được cập nhật.

**4.** Field không đánh dấu `@Indexed` được `HSET` bên ngoài Repository thì có luôn an toàn không?  
Không thể kết luận như vậy: có thể không cần đổi secondary index của field đó, nhưng vẫn có rủi ro serializer, mapping và cập nhật đồng thời.

**5.** Vì sao xóa Hash bằng `DEL` có thể để lại dấu vết trong index?  
Redis chỉ xóa khóa được chỉ định; nó không tự biết những SET phụ chứa tham chiếu tới Hash.

**6.** Tại sao khôi phục chỉ mục không nên chỉ duyệt `repository.findAll()`?  
Vì chính tập quản lý keyspace có thể đã thiếu entity được ghi thủ công; đầu vào của quá trình tái tạo có thể bỏ sót dữ liệu.

**7.** Có thể bảo đảm mọi cập nhật Hash và index nguyên tử trong Redis Cluster chỉ nhờ `@Indexed` không?  
Không. Cần hiểu cách Repository và client thực hiện lệnh trên các slot, cùng cơ chế xử lý cạnh tranh và lỗi; annotation chỉ khai báo nhu cầu index.

## 16. Kết luận

Spring Data Redis Repository duy trì một **mô hình dữ liệu có cấu trúc** trên nền Redis: khóa Hash chính chứa entity, còn những SET/metadata phụ giúp liệt kê và truy vấn theo thuộc tính `@Indexed`. Lệnh ghi trực tiếp vào Hash không tự kích hoạt cơ chế quản lý index. Vì vậy, **Hash đúng chưa chắc truy vấn Repository đúng**.

Khi một entity được quản lý bởi Repository, nên đưa các thao tác tạo, sửa, xóa qua một đường ghi thống nhất có trách nhiệm bảo trì chỉ mục. Nếu có import, TTL, Redis Cluster hoặc writer ngoài Repository, phải có hợp đồng đồng bộ, quan sát và đối soát rõ ràng. Đó là điều kiện để kết quả `findById()`, `findAll()` và `findBy...()` phản ánh cùng một tập dữ liệu logic.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): ánh xạ entity và các cơ chế của Repository.
- [Spring Data Redis — Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): cơ chế secondary index và `@Indexed`.
- [Spring Data Redis — Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries.html): truy vấn dựa trên thuộc tính đã được index.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): TTL, sự kiện hết hạn và dọn dẹp dữ liệu.
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): chuyển đổi object thành Redis Hash.
- [Redis — HSET](https://redis.io/docs/latest/commands/hset/), [HDEL](https://redis.io/docs/latest/commands/hdel/), [DEL](https://redis.io/docs/latest/commands/del/): hành vi lệnh cấp Redis đối với khóa và field.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): giới hạn của thao tác duyệt khóa và cursor.
