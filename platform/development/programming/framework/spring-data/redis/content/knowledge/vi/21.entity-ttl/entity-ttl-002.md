# Dùng @TimeToLive cho thời hạn thay đổi theo từng thực thể

## 1. Vấn đề: không phải thực thể nào cũng hết hạn cùng lúc

Một hệ thống Spring Boot lưu các mã truy cập tạm thời trong Redis:

- Mã xác nhận đăng nhập thường chỉ dùng được trong **90 giây**.
- Mã liên kết thiết bị có thể tồn tại **10 phút**.
- Quyền truy cập được cấp tạm thời cho một tác vụ có thể kéo dài **1 giờ**.

Cả ba đều là các đối tượng Java cùng loại, nhưng thời hạn của chúng khác nhau. Nếu gắn một thời hạn cố định lên cả lớp, ta khó biểu diễn quy tắc riêng của từng đối tượng.

Spring Data Redis Repository cho phép khai báo thời gian sống của một thực thể bằng annotation `@TimeToLive`. Thay vì quyết định TTL chỉ ở cấp loại dữ liệu, ta có thể **gán TTL cho từng instance** tại lúc lưu.

~~~text
Ứng dụng Spring Boot                       Redis
┌──────────────────────────┐               ┌─────────────────────────┐
│ AccessGrant A            │  save(A)      │ access-grants:A         │
│ ttlSeconds = 90          ├──────────────>│ Redis Hash, TTL ≈ 90 s  │
└──────────────────────────┘               └─────────────────────────┘
┌──────────────────────────┐               ┌─────────────────────────┐
│ AccessGrant B            │  save(B)      │ access-grants:B         │
│ ttlSeconds = 600         ├──────────────>│ Redis Hash, TTL ≈ 600 s │
└──────────────────────────┘               └─────────────────────────┘
┌──────────────────────────┐               ┌──────────────────────────┐
│ AccessGrant C            │  save(C)      │ access-grants:C          │
│ ttlSeconds = 3600        ├──────────────>│ Redis Hash, TTL ≈ 3600 s │
└──────────────────────────┘               └──────────────────────────┘
~~~

**TTL (Time To Live)** là khoảng thời gian còn lại trước khi một khóa hết hạn. Redis quản lý TTL ở **cấp khóa**, không phải từng trường bên trong Hash. Đối tượng do Repository lưu thường được ánh xạ thành Redis Hash; khi khóa hết hạn, toàn bộ Hash đó không còn khả dụng.

Bài học này tập trung vào thời hạn linh hoạt cho **thực thể do Spring Data Redis Repository quản lý**. Nếu ứng dụng dùng `RedisTemplate` để lưu trực tiếp, TTL có thể được đặt bằng các thao tác của Template, nhưng cơ chế đó không tự sử dụng `@TimeToLive`.

## 2. Phân biệt thời hạn cố định và thời hạn theo thực thể

### 2.1. TTL cố định bằng @RedisHash

Với chính sách mọi bản ghi có cùng thời hạn:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "access-grants", timeToLive = 600)
public class AccessGrant {

    @Id
    private String id;

    private String accountId;

    // Constructor, getter, setter...
}
~~~

Giá trị `timeToLive = 600` ở đây là **600 giây**, dùng làm cấu hình chung cho loại thực thể. Cách này hợp lý khi mọi khóa trong keyspace đều cùng một quy tắc hết hạn.

Nhưng nếu mã xác nhận một lần chỉ có hiệu lực 90 giây, còn một mã khác cần 600 giây, cấu hình cố định trở nên kém linh hoạt.

### 2.2. TTL linh hoạt bằng @TimeToLive

Với `@TimeToLive`, một **thuộc tính số** hoặc **phương thức** trên thực thể có thể cung cấp thời hạn khi Repository lưu đối tượng:

~~~java
@RedisHash("access-grants")
public class AccessGrant {

    @Id
    private String id;

    @TimeToLive
    private Long ttlSeconds;

    // Những thuộc tính khác...
}
~~~

Mỗi instance mang một giá trị riêng:

~~~java
new AccessGrant("A", "account-1", 90L);
new AccessGrant("B", "account-2", 600L);
new AccessGrant("C", "account-3", 3600L);
~~~

Khi lưu, Spring Data Redis sử dụng giá trị TTL tương ứng để đặt thời gian hết hạn cho khóa của thực thể. **`@TimeToLive` ưu tiên hơn cấu hình thời hạn khác** trên cùng loại thực thể, chẳng hạn `@RedisHash(timeToLive = ...)`.

| Đặc điểm | `@RedisHash(timeToLive = ...)` | `@TimeToLive` |
|---|---|---|
| Vị trí khai báo | Trên lớp thực thể | Trên thuộc tính số hoặc phương thức |
| TTL cho từng đối tượng | Chung theo cấu hình lớp | Có thể khác nhau giữa các instance |
| Giá trị được cung cấp | Hằng số trong annotation | Giá trị thuộc tính hoặc kết quả phương thức |
| Đơn vị mặc định | Giây | Giây |
| Khi cần thời gian đặc thù | Phải thay đổi cách thiết kế | Đặt TTL tương ứng trên đối tượng |
| Khi đọc qua Repository | Không tự tạo một trường TTL trên đối tượng | Thuộc tính được annotation có thể nhận **TTL thực tế còn lại** từ Redis |

Không nên áp dụng `@TimeToLive` lên **cả thuộc tính lẫn phương thức trong cùng một lớp**. Hãy chọn một cách duy nhất để tránh cơ chế xác định TTL mơ hồ.

## 3. Ví dụ đầy đủ: TTL trên thuộc tính

### 3.1. Khai báo thực thể

~~~java
package com.example.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("access-grants")
public class AccessGrant {

    @Id
    private String id;

    private String accountId;

    private String purpose;

    @TimeToLive
    private Long ttlSeconds;

    public AccessGrant() {
    }

    public AccessGrant(
            String id,
            String accountId,
            String purpose,
            long ttlSeconds) {

        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException(
                    "TTL phải là số giây dương"
            );
        }

        this.id = id;
        this.accountId = accountId;
        this.purpose = purpose;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getAccountId() {
        return accountId;
    }

    public void setAccountId(String accountId) {
        this.accountId = accountId;
    }

    public String getPurpose() {
        return purpose;
    }

    public void setPurpose(String purpose) {
        this.purpose = purpose;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }

    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

Các thành phần chính:

1. `@RedisHash("access-grants")` xác định keyspace của thực thể, thường dẫn tới tên khóa kiểu `access-grants:<id>`.
2. `@Id` chỉ ra định danh dùng để xây dựng khóa.
3. `@TimeToLive` đánh dấu thuộc tính dùng xác định thời gian hết hạn.
4. `Long ttlSeconds` cho phép mỗi instance mang một TTL riêng.
5. Constructor minh họa việc **kiểm tra TTL dương trước khi lưu**. Nếu có nhiều đường tạo hoặc cập nhật đối tượng, cần bảo đảm những đường đó cũng áp dụng quy tắc nghiệp vụ phù hợp.

Không cần tự lưu các thời điểm hết hạn vào một bảng riêng chỉ để Redis biết khi nào xóa khóa. Khi Repository đặt TTL, Redis sẽ quản lý việc hết hạn ở cấp khóa.

### 3.2. Khai báo Repository

~~~java
package com.example.redis;

import org.springframework.data.repository.CrudRepository;

public interface AccessGrantRepository
        extends CrudRepository<AccessGrant, String> {
}
~~~

Trong một dự án Spring Boot có Spring Data Redis và kết nối Redis đã được cấu hình, Repository này cung cấp những thao tác như `save`, `findById` và `deleteById`.

Nếu cần bật rõ tính năng Repository:

~~~java
package com.example.redis;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        basePackageClasses = AccessGrantRepository.class
)
public class RedisRepositoryConfiguration {
}
~~~

Annotation `@EnableRedisRepositories` chỉ cần được khai báo khi cơ chế cấu hình ứng dụng chưa kích hoạt Repository tương ứng; tránh cấu hình lặp lại không cần thiết.

### 3.3. Tạo các đối tượng có TTL khác nhau

~~~java
package com.example.redis;

import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class AccessGrantService {

    private final AccessGrantRepository repository;

    public AccessGrantService(AccessGrantRepository repository) {
        this.repository = repository;
    }

    public AccessGrant issueLoginCode(String accountId) {
        return repository.save(new AccessGrant(
                UUID.randomUUID().toString(),
                accountId,
                "LOGIN_CODE",
                90L
        ));
    }

    public AccessGrant issueDeviceLink(String accountId) {
        return repository.save(new AccessGrant(
                UUID.randomUUID().toString(),
                accountId,
                "DEVICE_LINK",
                600L
        ));
    }

    public AccessGrant issueTemporaryAccess(String accountId) {
        return repository.save(new AccessGrant(
                UUID.randomUUID().toString(),
                accountId,
                "TEMPORARY_ACCESS",
                3600L
        ));
    }
}
~~~

Mỗi lần gọi `save(...)`, Repository ánh xạ đối tượng sang dữ liệu Redis và đặt thời hạn theo instance được lưu. Sau khi Redis nhận lệnh đặt TTL, đồng hồ thời gian hết hạn bắt đầu chạy.

Các con số trên là ví dụ của quy tắc nghiệp vụ. Trong hệ thống thật, thời hạn cần được xác định theo yêu cầu sản phẩm và chính sách bảo mật, rồi được truyền vào đối tượng khi tạo.

### 3.4. Quan sát Redis sau khi lưu

Giả sử một bản ghi có id `g-90` và TTL 90 giây, còn bản ghi khác có id `g-600` và TTL 600 giây:

~~~redis
TYPE access-grants:g-90
TTL access-grants:g-90

TYPE access-grants:g-600
TTL access-grants:g-600
~~~

Kết quả minh họa:

~~~text
TYPE access-grants:g-90   → hash
TTL access-grants:g-90    → 86

TYPE access-grants:g-600  → hash
TTL access-grants:g-600   → 594
~~~

Các giá trị 86 và 594 chỉ minh họa thời gian đã trôi qua từ lúc lưu. TTL thực tế giảm theo thời gian, nên không nên kiểm tra bằng cách đòi hỏi nó luôn bằng đúng 90 hoặc 600.

### 3.5. Sau khi hết hạn, Repository trả về gì?

~~~java
var result = repository.findById("g-90");

if (result.isPresent()) {
    System.out.println("Grant vẫn còn hiệu lực ở mức lưu trữ");
} else {
    System.out.println("Không còn tìm thấy grant");
}
~~~

Khi khóa đã hết hạn và Redis xem khóa là không tồn tại, `findById` trả về `Optional.empty()`.

Tuy nhiên, **việc khóa còn tồn tại không tự bảo đảm mọi điều kiện nghiệp vụ**. Với quyền truy cập nhạy cảm, ứng dụng có thể vẫn phải xác minh trạng thái tài khoản, mục đích của grant, việc thu hồi quyền và các ràng buộc khác.

## 4. Điểm dễ nhầm: đọc lại @TimeToLive nhận thời gian còn lại

Thuộc tính gắn `@TimeToLive` có ý nghĩa đặc biệt khi Repository đọc một thực thể đã lưu. Spring Data Redis có thể đọc giá trị TTL thực tế của khóa bằng lệnh `TTL` hoặc `PTTL` rồi nạp vào thuộc tính đó.

Giả sử:

~~~java
repository.save(new AccessGrant(
        "g-101", "account-7", "LOGIN_CODE", 300L
));
~~~

Hai phút sau:

~~~java
AccessGrant grant = repository.findById("g-101")
        .orElseThrow();

System.out.println(grant.getTtlSeconds());
~~~

Giá trị in ra có thể gần **180**, chứ không còn là **300**. Tùy thời điểm lấy mẫu và độ phân giải đơn vị, giá trị có thể khác một chút.

~~~text
Thời điểm tạo t0              t0 + 120 giây              t0 + 300 giây
      |                             |                            |
      v                             v                            v
  save(ttl=300)          findById(...), ttl≈180             Khóa hết hạn
      |                             |
      +-------------- TTL giảm -----+----------------------------+
~~~

Đây là sự khác biệt quan trọng giữa:

- **TTL ban đầu của nghiệp vụ:** thời hạn đã cấp lúc tạo đối tượng, chẳng hạn 300 giây.
- **TTL hiện tại của Redis:** thời gian còn lại tại thời điểm đọc, chẳng hạn 180 giây.

Nếu muốn báo cáo hoặc ghi nhận **thời hạn được cấp ban đầu**, hãy lưu thông tin đó trong một thuộc tính nghiệp vụ riêng, ví dụ `originalLifetimeSeconds` hoặc `issuedAt` và `expiresAt`. Đừng dùng trường `@TimeToLive` để suy luận chắc chắn TTL gốc sau khi đọc lại.

### 4.1. Ý nghĩa của TTL âm

Trong Redis, lệnh:

~~~redis
TTL some-key
~~~

thường trả về:

| Giá trị | Ý nghĩa |
|---|---|
| Số nguyên dương | Số giây còn lại trước khi khóa hết hạn |
| `-1` | Khóa tồn tại nhưng **không được đặt thời hạn hết hạn** |
| `-2` | Khóa **không tồn tại** |

Theo cơ chế ánh xạ của Spring Data Redis, thuộc tính `@TimeToLive` được đọc lại có thể nhận `-1` khi khóa không có thời hạn. Đối với khóa không còn tồn tại, Repository thường không dựng được đối tượng để trả về; người gọi nhận `Optional.empty()` thay vì một đối tượng có `ttlSeconds = -2`.

Khi kiểm tra trạng thái trong mã Java, không nên mặc định rằng mọi giá trị `ttlSeconds <= 0` đều mang cùng một ý nghĩa.

### 4.2. Tại sao việc đọc lại quan trọng khi lưu lần nữa?

Xét trình tự:

1. Lưu đối tượng với `ttlSeconds = 300`.
2. Sau 120 giây, gọi `findById(...)`; thuộc tính nhận giá trị khoảng `180`.
3. Sửa một thuộc tính nghiệp vụ rồi gọi `repository.save(grant)`.

Khi lưu lại, `@TimeToLive` vẫn tham gia quyết định TTL. Trong trường hợp này, TTL được áp dụng từ giá trị còn lại của đối tượng vừa đọc, không phải tự động trở về thời hạn gốc 300 giây.

Ngược lại, nếu ứng dụng giữ **một đối tượng Java cũ** còn trường `ttlSeconds = 300` rồi đem `save(...)` thêm lần nữa sau 120 giây, nó có thể đặt lại thời hạn khoảng 300 giây tính từ lần lưu mới. Việc này **gia hạn ngoài ý muốn** nếu chính sách nghiệp vụ định nghĩa ngày hết hạn cố định.

**Quy tắc:** trước mỗi lần lưu lại một thực thể có TTL, hãy xác định rõ mình muốn:

- Giữ thời điểm hết hạn ban đầu.
- Gia hạn thêm một khoảng thời gian mới.
- Thay đổi chính sách và đặt một TTL khác.

Không nên để việc ghi lại đối tượng vô tình quyết định chính sách gia hạn.

## 5. Chủ động gia hạn hoặc rút ngắn TTL

Có những tình huống cần thay đổi thời hạn sau khi đã tạo thực thể.

### 5.1. Gia hạn bằng Repository

Ví dụ, nghiệp vụ cho phép gia hạn phiên liên kết thiết bị thêm mười phút:

~~~java
public void renewDeviceLink(
        AccessGrantRepository repository,
        String id) {

    AccessGrant grant = repository.findById(id)
            .orElseThrow(() ->
                    new IllegalArgumentException("Grant không tồn tại"));

    if (!"DEVICE_LINK".equals(grant.getPurpose())) {
        throw new IllegalArgumentException(
                "Chỉ cho phép gia hạn grant liên kết thiết bị"
        );
    }

    grant.setTtlSeconds(600L);
    repository.save(grant);
}
~~~

Trong ví dụ này, sau lần lưu mới, hệ thống đặt thời hạn mới theo giá trị 600 giây. Chính sách gia hạn cần được kiểm tra quyền và điều kiện nghiệp vụ trước khi áp dụng.

### 5.2. Rút ngắn TTL

Nếu hệ thống cần thu hẹp hiệu lực còn 30 giây:

~~~java
grant.setTtlSeconds(30L);
repository.save(grant);
~~~

Việc rút ngắn TTL bằng thao tác ghi lại toàn bộ thực thể cũng có tác động tới nội dung và metadata do Repository quản lý. Nếu chỉ muốn điều chỉnh TTL vật lý, có thể cân nhắc lệnh Redis `EXPIRE` qua một API thích hợp; khi đó vẫn cần hiểu hệ quả đối với bản sao phụ, sự kiện hết hạn và chỉ mục của Repository.

### 5.3. Thu hồi ngay lập tức khác với đặt TTL

Nếu một grant cần vô hiệu hóa ngay:

~~~java
repository.deleteById(id);
~~~

Xóa chủ động và để khóa **tự hết hạn** không hoàn toàn giống nhau về sự kiện, quá trình dọn chỉ mục và ý nghĩa nghiệp vụ. Tùy ứng dụng, vẫn cần xử lý các thao tác đã diễn ra trước thời điểm thu hồi.

## 6. @TimeToLive trên phương thức: tính TTL khi lưu

Có những thực thể không muốn giữ một trường TTL tương đối mà muốn dựa vào **thời điểm hết hạn tuyệt đối**. Ví dụ, một ưu đãi có thời điểm kết thúc không đổi dù được lưu lại nhiều lần.

Spring Data Redis cho phép `@TimeToLive` trên phương thức. Dưới đây là một lớp **khác** với `AccessGrant` ở trên, minh họa phương án này.

~~~java
package com.example.redis;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("temporary-offers")
public class TemporaryOffer {

    @Id
    private String id;

    private String description;

    // Thời điểm hết hạn tuyệt đối, số giây Unix epoch.
    private long expiresAtEpochSeconds;

    public TemporaryOffer() {
    }

    public TemporaryOffer(
            String id,
            String description,
            long expiresAtEpochSeconds) {
        this.id = id;
        this.description = description;
        this.expiresAtEpochSeconds = expiresAtEpochSeconds;
    }

    @TimeToLive
    public long getTimeToLive() {
        return expiresAtEpochSeconds
                - Instant.now().getEpochSecond();
    }

    public String getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }

    public long getExpiresAtEpochSeconds() {
        return expiresAtEpochSeconds;
    }
}
~~~

Khi Repository lưu đối tượng, phương thức `getTimeToLive()` tính thời gian còn lại dựa trên thời điểm tuyệt đối.

~~~text
expiresAt = 10:30:00
    |
    +-- save lúc 10:20:00  -> TTL khoảng 600 giây
    |
    +-- save lúc 10:25:00  -> TTL khoảng 300 giây
    |
    +-- qua 10:30:00      -> thời hạn nghiệp vụ đã kết thúc
~~~

**Lưu ý quan trọng:** hàm trên có thể trả `0` hoặc số âm nếu ưu đãi đã hết hạn. Đây là tín hiệu để tầng dịch vụ **không tiếp tục lưu một ưu đãi đã hết hạn**. Không dựa vào các giá trị TTL không dương để điều khiển nghiệp vụ, vì chúng có ý nghĩa đặc biệt và việc xử lý có thể khác TTL dương.

Ví dụ kiểm tra trước khi lưu:

~~~java
public TemporaryOffer createOffer(
        TemporaryOffer offer,
        TemporaryOfferRepository repository) {

    if (offer.getTimeToLive() <= 0L) {
        throw new IllegalArgumentException(
                "Ưu đãi đã hết hạn"
        );
    }

    return repository.save(offer);
}
~~~

Repository tương ứng:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface TemporaryOfferRepository
        extends CrudRepository<TemporaryOffer, String> {
}
~~~

Giữa thời điểm kiểm tra và lúc Redis đặt TTL vẫn có một khoảng thời gian trôi qua. Với thời hạn rất sát thời điểm hiện tại hoặc yêu cầu chính xác nghiêm ngặt, cần thêm quy tắc từ chối/đồng bộ thích hợp; không coi đoạn mã minh họa là giải pháp khóa chặt thời gian.

### Chọn thuộc tính hay phương thức?

| Nhu cầu | `@TimeToLive` trên thuộc tính | `@TimeToLive` trên phương thức |
|---|---|---|
| Cấp TTL riêng khi tạo đối tượng | Rất trực tiếp | Có thể thực hiện |
| Đọc TTL còn lại vào đối tượng | Có, Spring Data Redis đọc TTL/PTTL | Không hoạt động như một trường được nạp lại với cùng ý nghĩa |
| Gia hạn phiên theo một khoảng thời gian mới | Gán lại giá trị rồi `save` | Thay đổi dữ liệu đầu vào để phương thức tính lại |
| Giữ thời điểm hết hạn tuyệt đối khi lưu lại | Phải quản lý riêng, tránh reset ngoài ý muốn | Phù hợp nếu phương thức tính từ `expiresAt` |
| Tránh trộn TTL hiện tại với TTL gốc | Cần tách trường nghiệp vụ | Có thể giữ thời điểm hết hạn tuyệt đối |

Hai cách là **hai phương án riêng**, không đặt cả annotation trên field và method của một lớp.

## 7. Đơn vị thời gian: giây, mili giây và sai lệch do làm tròn

Đơn vị mặc định của `@TimeToLive` là **giây**. Với nghiệp vụ cần độ phân giải nhỏ hơn, annotation có tùy chọn `unit`:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.TimeToLive;

@TimeToLive(unit = TimeUnit.MILLISECONDS)
private Long ttlMillis;
~~~

Ví dụ:

~~~text
ttlMillis = 1500  →  thời hạn mục tiêu 1,5 giây
ttlSeconds = 90   →  thời hạn mục tiêu 90 giây
~~~

Redis hỗ trợ cả thao tác đặt TTL theo giây và mili giây; khi đọc lại, Spring Data Redis có thể sử dụng `TTL` hoặc `PTTL` tương ứng. Vì vậy, đơn vị phải nhất quán giữa tên trường, dữ liệu truyền vào và annotation.

Không được lấy giá trị `Duration.toMillis()` rồi gán vào một thuộc tính `@TimeToLive` mặc định đơn vị giây; ví dụ `1500` có thể bị hiểu thành **1500 giây** thay vì 1,5 giây.

Khi chuyển từ `Duration` sang số nguyên, hãy làm rõ:

- Đơn vị đầu vào của chính sách nghiệp vụ.
- Độ phân giải chấp nhận được.
- Cách làm tròn khi thời gian còn lại không đủ một đơn vị.
- Giá trị lớn nhất được cho phép.

Nếu TTL gần bằng 0, chuyển đổi từ mili giây sang giây bằng phép chia nguyên có thể cho kết quả `0` và làm mất ý nghĩa của thời hạn mong muốn. Nên kiểm tra và xử lý trường hợp này có chủ đích.

## 8. Vòng đời của khóa và các cơ chế bên trong Spring Data Redis

### 8.1. @TimeToLive đặt thời hạn lên khóa Redis

Một đối tượng Repository thường được lưu dưới Redis Hash:

~~~text
access-grants:g-101
    id         -> g-101
    accountId  -> account-7
    purpose    -> LOGIN_CODE
    ...
~~~

TTL không phải một field Redis Hash độc lập. Ở mức Redis, thời hạn được gắn với **chính khóa** `access-grants:g-101`.

Các lệnh kiểm tra phù hợp:

~~~redis
TYPE access-grants:g-101
TTL access-grants:g-101
PTTL access-grants:g-101
~~~

`PTTL` trả mili giây; `TTL` trả giây. Đừng nhầm `HGETALL` với nguồn TTL thực tế: nội dung Hash không phải nơi Redis lưu bộ đếm thời gian hết hạn.

### 8.2. Có thể tồn tại bản sao phụ sau khi khóa chính hết hạn

Spring Data Redis Repository hỗ trợ sự kiện hết hạn `RedisKeyExpiredEvent`. Với cấu hình thông thường và TTL dương, cơ chế Repository có thể lưu thêm một **bản sao phụ (shadow copy / phantom copy)**, có thời điểm hết hạn muộn hơn khoảng **5 phút** so với khóa chính. Mục đích là cho phép sự kiện hết hạn mang theo dữ liệu của thực thể ngay cả khi khóa chính đã biến mất.

~~~text
Tạo grant                         Hết hạn chính        Bản sao phụ hết hạn
    |                                  |                         |
    v                                  v                         v
    +----------------------------------+-------------------------+
       TTL của khóa chính                      ~5 phút thêm

    Redis Hash chính: tồn tại -------X
    Shadow copy:      tồn tại ---------------------------X
~~~

Điều này có một vài hệ quả:

- Dung lượng lưu trữ thực tế có thể lớn hơn dự đoán chỉ từ một khóa chính.
- Cần hiểu cơ chế sự kiện nếu muốn theo dõi hoặc dọn chỉ mục khi khóa hết hạn.
- Tùy nhu cầu, Spring Data Redis có cấu hình tắt shadow copy; khi đó dữ liệu có sẵn trong sự kiện hết hạn sẽ bị giới hạn.
- **Không xem RedisKeyExpiredEvent là một hàng đợi sự kiện bền vững.**

Thông tin này áp dụng cho **Redis Repository**. Nếu một đoạn mã trực tiếp gọi `RedisTemplate.opsForValue().set(key, value, Duration)` thì không nên suy luận rằng nó tự tạo bản sao phụ theo cùng cơ chế.

### 8.3. Sự kiện hết hạn có thể không đến ứng dụng

Redis phát thông báo hết hạn qua cơ chế keyspace notification/Pub/Sub khi được cấu hình. Pub/Sub không lưu giữ thông điệp để phát lại.

Nếu một instance ứng dụng bị dừng, chưa khởi động listener hoặc mất kết nối đúng lúc khóa hết hạn, sự kiện có thể bị bỏ lỡ. Trong hệ thống nhiều instance, cũng không thể mặc định rằng chỉ một instance sẽ xử lý sự kiện.

Điều này đặc biệt quan trọng với **chỉ mục phụ** do Repository quản lý. Một đối tượng gốc có thể đã hết hạn nhưng những mục trong Set dùng làm chỉ mục phụ vẫn còn nếu quy trình dọn phụ thuộc vào sự kiện bị bỏ lỡ.

Do đó:

- Dựa vào TTL của Redis để xác định việc khóa gốc còn tồn tại hay không.
- Dùng sự kiện hết hạn để cập nhật trạng thái phụ hoặc tối ưu dọn dẹp khi chấp nhận được tính chất không bảo đảm giao hàng.
- Nếu nghiệp vụ cần xử lý bắt buộc, chính xác một lần hoặc có khả năng chạy lại, thiết kế một cơ chế công việc bền vững riêng.
- Theo dõi tình trạng listener và quy tắc cấu hình `notify-keyspace-events` trong môi trường triển khai.
- Không coi việc Redis đã xóa khóa và việc ứng dụng đã xử lý sự kiện là cùng một thời điểm.

Trong một số dịch vụ Redis được quản lý, lệnh cấu hình `CONFIG` bị hạn chế; cần cấu hình thông báo theo khả năng của hạ tầng thay vì giả định ứng dụng luôn tự bật được chúng.

## 9. Những lỗi dễ gặp khi dùng TTL động

### Lỗi 1: Nhầm đơn vị của @TimeToLive

~~~java
// Truyền 90000 nhưng annotation mặc định dùng giây!
@TimeToLive
private Long ttlSeconds = 90_000L;
~~~

Nếu ý định là 90 giây, phải dùng `90L` với đơn vị giây hoặc dùng `90_000L` cùng `unit = TimeUnit.MILLISECONDS`.

### Lỗi 2: Nhầm TTL còn lại với thời hạn được cấp ban đầu

~~~java
AccessGrant loaded = repository.findById(id).orElseThrow();
Long ttl = loaded.getTtlSeconds();
~~~

`ttl` là **thời hạn thực tế còn lại tại lúc đọc**. Nếu cần đối chiếu chính sách đã cấp lúc đầu, phải lưu thông tin nghiệp vụ riêng.

### Lỗi 3: Vô tình gia hạn khi lưu lại một đối tượng cũ

~~~java
AccessGrant cachedJavaObject = originalWith300Seconds;

// ... ứng dụng giữ object này một khoảng thời gian ...

repository.save(cachedJavaObject);
~~~

Nếu `ttlSeconds` của object vẫn bằng 300 thì lần lưu sau có thể áp dụng lại 300 giây. Nên lưu thời điểm hết hạn tuyệt đối nếu yêu cầu là “hết hạn vào đúng lúc X”, hoặc luôn tính lại TTL trước khi lưu.

### Lỗi 4: Đánh dấu cả getter và field bằng @TimeToLive

~~~java
// Không dùng cả hai annotation trong cùng một lớp.
@TimeToLive
private Long ttlSeconds;

@TimeToLive
public Long getTimeToLive() {
    return ttlSeconds;
}
~~~

Chọn **một điểm định nghĩa TTL** duy nhất.

### Lỗi 5: Cho rằng cập nhật giá trị Java sẽ tự đổi TTL trong Redis

~~~java
grant.setTtlSeconds(600L);
~~~

Đoạn này chỉ sửa đối tượng trong bộ nhớ của JVM. Muốn thay đổi dữ liệu và thời hạn trên Redis qua Repository, phải thực hiện thao tác lưu tương ứng, chẳng hạn `repository.save(grant)`.

### Lỗi 6: Nhầm khóa hết hạn với sự kiện bắt buộc phải đến

`repository.findById(id)` có thể không tìm thấy khóa đã hết hạn, nhưng listener ứng dụng không nhất thiết đã nhận được `RedisKeyExpiredEvent`. Không dùng sự kiện hết hạn như nguồn bảo đảm duy nhất cho một nghiệp vụ cần xử lý chắc chắn.

### Lỗi 7: Dùng TTL để che giấu quy tắc bảo mật

Một token tồn tại trong Redis không có nghĩa token chắc chắn còn hợp lệ ở mọi điều kiện. Khi cần, ứng dụng vẫn phải kiểm tra chủ thể, phạm vi quyền, trạng thái bị thu hồi và thời hạn nghiệp vụ. TTL giúp loại bỏ dữ liệu theo thời gian, nhưng không thay thế toàn bộ quy tắc xác thực và phân quyền.

### Lỗi 8: Quét toàn bộ keyspace để đếm thực thể còn hiệu lực

Khi dùng TTL động, Redis đã quản lý hạn dùng của khóa. Việc liên tục gọi `KEYS access-grants:*` để đếm hoặc kiểm kê có thể gây tải lớn khi số khóa tăng. Nên dùng mô hình truy vấn/chỉ mục hoặc số liệu vận hành phù hợp, thay vì quét mọi khóa trong luồng request.

## 10. Thực hành: quan sát hai TTL độc lập

Thực hiện trên Redis phát triển, dùng repository và lớp `AccessGrant` đã khai báo ở phần trên.

### Bước 1: Tạo hai grant

~~~java
AccessGrant shortGrant = repository.save(
        new AccessGrant("short-1", "acc-1", "LOGIN_CODE", 30L)
);

AccessGrant longGrant = repository.save(
        new AccessGrant("long-1", "acc-1", "DEVICE_LINK", 180L)
);
~~~

### Bước 2: Kiểm tra khóa

~~~redis
TYPE access-grants:short-1
TYPE access-grants:long-1

TTL access-grants:short-1
TTL access-grants:long-1
~~~

Kết quả dự kiến ngay sau khi lưu là hai Redis Hash, một có thời hạn còn lại gần 30 giây và một gần 180 giây.

### Bước 3: Đọc lại qua Repository

~~~java
AccessGrant loadedShort = repository
        .findById("short-1")
        .orElseThrow();

System.out.println(loadedShort.getTtlSeconds());
~~~

Kết quả của `getTtlSeconds()` có thể nhỏ hơn 30 vì thời gian đã trôi qua.

### Bước 4: Quan sát khóa hết hạn

Sau khi khoảng thời gian tương ứng trôi qua, kiểm tra:

~~~redis
EXISTS access-grants:short-1
TTL access-grants:short-1

EXISTS access-grants:long-1
TTL access-grants:long-1
~~~

Khóa ngắn có thể đã biến mất trong khi khóa dài vẫn còn. Redis quyết định sự tồn tại dựa trên thời điểm hết hạn và quá trình kiểm tra/làm sạch khóa; thời điểm phát sự kiện hết hạn tới ứng dụng có thể khác.

### Bước 5: Thử thay đổi TTL

Trước khi khóa `long-1` hết hạn:

~~~java
AccessGrant grant = repository.findById("long-1")
        .orElseThrow();

grant.setTtlSeconds(300L);
repository.save(grant);
~~~

Sau đó kiểm tra:

~~~redis
TTL access-grants:long-1
~~~

TTL gần 300 giây cho thấy thời hạn đã được đặt lại từ lần lưu mới. Thực hành trên cần được hoàn thành trước khi khóa hết hạn, vì sau đó `findById` có thể trả `Optional.empty()`.

## 11. Khi nào nên chọn @TimeToLive?

| Tình huống | Cách tiếp cận |
|---|---|
| Mọi đối tượng cùng loại luôn hết hạn sau 15 phút | Có thể dùng `@RedisHash(timeToLive = 900)` |
| Mỗi mã xác nhận có TTL được cấp riêng | `@TimeToLive` trên thuộc tính số |
| Thời điểm hết hạn phải cố định, dù thực thể được lưu lại | Tính TTL từ `expiresAt`, thường phù hợp với `@TimeToLive` trên phương thức và kiểm tra thời hạn trước khi lưu |
| Cần biết thời gian Redis còn giữ đối tượng | Đọc thực thể có field `@TimeToLive` hoặc hỏi Redis bằng `TTL`/`PTTL` |
| Chỉ lưu giá trị cache bằng `RedisTemplate.opsForValue()` | Đặt TTL trong `set(key, value, Duration)`; annotation Repository không tự áp dụng |
| Cần thực hiện nghiệp vụ quan trọng đúng lúc hết hạn | Dùng cơ chế lịch biểu/hàng đợi bền vững phù hợp; không chỉ dựa vào Redis Pub/Sub expiry event |

## 12. Câu hỏi tự kiểm tra

**1.** Hai thực thể cùng lớp có thể có TTL khác nhau bằng `@TimeToLive` không?

Có. Mỗi instance có thể mang giá trị TTL riêng và Repository dùng giá trị đó khi lưu.

**2.** Nếu `@RedisHash(timeToLive = 600)` nhưng đối tượng có field `@TimeToLive = 90`, thời hạn nào được ưu tiên?

`@TimeToLive` trên thuộc tính được ưu tiên khi có giá trị hợp lệ, cho phép TTL theo từng instance.

**3.** Lưu với TTL 300 giây rồi đọc lại sau khoảng 100 giây, field `@TimeToLive` thường mang giá trị bao nhiêu?

Gần 200 giây. Spring Data Redis có thể nạp **thời gian còn lại**, không giữ nguyên 300 giây đã cấp ban đầu.

**4.** Có được đặt `@TimeToLive` trên cả field lẫn method của cùng một lớp không?

Không nên. Chỉ áp dụng trên một thuộc tính số hoặc một phương thức để xác định TTL rõ ràng.

**5.** Khi Redis đã hết hạn khóa, có chắc ứng dụng nhận được `RedisKeyExpiredEvent` không?

Không. Thông báo sử dụng cơ chế keyspace notification/Pub/Sub, có thể mất khi listener không hoạt động hoặc mất kết nối.

**6.** Redis còn giữ một Hash sau 60 giây có nghĩa mọi field trong Hash đều còn 60 giây riêng lẻ?

Không. TTL thuộc về **khóa Redis**, áp dụng cho cả Hash; các field không có TTL độc lập theo cơ chế này.

**7.** Khi nào nên dùng thời điểm tuyệt đối `expiresAt` thay vì chỉ lưu TTL tương đối?

Khi đối tượng phải hết hạn tại một thời điểm nghiệp vụ cố định và việc lưu lại không được tự động gia hạn thời điểm hết hạn đó.

## 13. Ghi nhớ

- `@TimeToLive` là cơ chế của **Spring Data Redis Repository** để thiết lập TTL linh hoạt cho từng thực thể.
- Annotation có thể nằm trên **một thuộc tính số** hoặc **một phương thức**, mặc định dùng **giây**; có thể cấu hình đơn vị bằng `unit`.
- Với annotation trên thuộc tính, khi đọc lại qua Repository, giá trị nhận được biểu diễn **TTL đang còn trên Redis**, không nhất thiết là TTL ban đầu.
- Mỗi lần `save(...)` có thể ảnh hưởng đến TTL. Xác định rõ nghiệp vụ muốn **gia hạn**, **rút ngắn** hay **giữ thời điểm hết hạn tuyệt đối**.
- TTL được quản lý ở **cấp khóa Redis**. Sự kiện hết hạn và bản sao phụ của Repository có giới hạn riêng; không nên dùng Pub/Sub expiry event làm cơ chế bảo đảm xử lý nghiệp vụ bắt buộc.

### Tài liệu tham khảo

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/3.5/redis/redis-repositories/expirations.html).
- [Spring Data Redis API — @TimeToLive](https://docs.spring.io/spring-data-redis/reference/api/java/org/springframework/data/redis/core/TimeToLive.html).
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/).
