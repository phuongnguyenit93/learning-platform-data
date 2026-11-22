# Ảnh hưởng của `save` đến nội dung Hash hiện có trong Redis Repository

## 1. Vấn đề: `save` có giữ nguyên các field cũ không?

Khi sử dụng **Spring Data Redis Repository**, một entity thường được lưu thành Redis Hash có khóa dạng `<keyspace>:<id>`. Phương thức `repository.save(entity)` hỗ trợ lưu entity mới hoặc lưu lại entity đã có ID.

Điểm dễ gây nhầm lẫn là: **lưu lại entity hiện có không tương đương với việc cập nhật riêng các field thay đổi của Hash**. Khi thay thế một entity đã tồn tại, cơ chế Redis Repository mặc định **xóa nội dung Hash cũ rồi tạo lại Hash từ các thuộc tính được ánh xạ của entity đang lưu**. Những field chỉ tồn tại trong Redis nhưng không xuất hiện trong dữ liệu được ánh xạ mới sẽ mất.

Ví dụ ngắn:

```text
Trước save:
profiles:42
  id          = 42
  displayName = Minh
  email       = minh@example.test
  externalTag = VIP       <- field được thêm trực tiếp vào Redis

Entity đem save:
  id          = 42
  displayName = Minh mới
  email       = null

Sau repository.save(entity):
profiles:42
  _class      = ...Profile
  id          = 42
  displayName = Minh mới

email       -> không còn field trong Hash
externalTag -> không còn field trong Hash
```

Đây là hành vi của **Redis Repository và cơ chế ánh xạ object-to-hash**, không phải quy tắc chung cho mọi thao tác Redis. Lệnh Redis `HSET` tự nó chỉ ghi đè các field được chỉ định, trong khi `repository.save` thực hiện công việc ở mức entity và có thể phát nhiều lệnh Redis.

## 2. Redis Repository chuyển entity thành Hash như thế nào?

Spring Data Redis dùng `RedisConverter` (thường là `MappingRedisConverter`) để chuyển thuộc tính Java sang những field của Redis Hash.

Xét entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("profiles")
public class Profile {

    @Id
    private String id;

    private String displayName;
    private String email;

    public Profile() {
    }

    public Profile(String id, String displayName, String email) {
        this.id = id;
        this.displayName = displayName;
        this.email = email;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface ProfileRepository extends CrudRepository<Profile, String> {
}
```

Lệnh:

```java
repository.save(new Profile("42", "Minh", "minh@example.test"));
```

tạo Hash ở keyspace `profiles` với ID `42`, tương ứng Redis key `profiles:42`. Dạng biểu diễn thông thường:

```text
HGETALL profiles:42

_class      = com.example.Profile
id          = 42
displayName = Minh
email       = minh@example.test
```

Tên đầy đủ trong `_class` tùy package Java và cấu hình type mapping. Nếu sử dụng `@TypeAlias`, giá trị phân biệt kiểu có thể khác. Field `_class` là metadata do mapper quản lý, không phải thuộc tính người dùng tự thêm.

Với thuộc tính phức tạp, mapper có thể trải phẳng ra các field như `address.city`, `address.country`. Với collection và map, tên field cũng có thể chứa đường dẫn và chỉ số. Vì thế việc “thay toàn bộ Hash” ảnh hưởng cả các field lồng nhau: phần tử hoặc thuộc tính không còn được ánh xạ cũng không được giữ lại.

## 3. Cơ chế khi `save` một entity đã tồn tại

Tài liệu Spring Data Redis minh họa trường hợp **replace existing** bằng chuỗi thao tác đại ý:

```redis
DEL   profiles:42
HMSET profiles:42 _class com.example.Profile id 42 displayName "Minh mới"
```

Đây là **sơ đồ lệnh minh họa**; danh sách lệnh cụ thể và cách gửi lệnh có thể khác theo phiên bản Spring Data Redis, mapper, index và TTL. Điều cần hiểu là Hash cũ bị loại bỏ để tránh giữ các field không còn được biểu diễn trong entity mới, sau đó Hash được ghi lại.

Repository còn có thể cập nhật các cấu trúc phụ trợ, chẳng hạn set chứa ID của keyspace và các secondary index cho thuộc tính `@Indexed`. Bởi vậy một lần `save` không nhất thiết là một lần `HSET` và không nên xem nó là thao tác cập nhật field nguyên tử của Redis.

So sánh hai thao tác:

| Thao tác | Cách tác động đến Redis Hash | Các field không được đề cập |
| --- | --- | --- |
| `HSET profiles:42 displayName "Minh mới"` | Ghi riêng field `displayName` | Vẫn giữ nếu Hash tồn tại |
| `repository.save(profile)` với ID đã tồn tại | Ghi lại biểu diễn đầy đủ của entity | Có thể bị xóa nếu không nằm trong kết quả ánh xạ |
| `PartialUpdate` cho một property | Cập nhật có chủ đích một phần dữ liệu do Redis Repository quản lý | Những property không nằm trong update thường được giữ |
| `repository.deleteById("42")` | Xóa entity khỏi Redis Repository | Toàn bộ Hash của entity bị xóa |

Điều này khác mô hình tư duy thường gặp ở SQL ORM: không nên suy luận rằng gọi `save` chỉ tạo câu lệnh tương đương `UPDATE ... SET displayName = ...`.

## 4. Minh họa chi tiết: field tự thêm bị mất

Giả sử đã tạo một profile bằng repository. Một dịch vụ khác hoặc công cụ quản trị thêm field không được ánh xạ:

```redis
HSET profiles:42 externalTag "VIP"
HSET profiles:42 reviewStatus "APPROVED"
HGETALL profiles:42
```

Hash có thể chứa:

```text
_class      = com.example.Profile
id          = 42
displayName = Minh
email       = minh@example.test
externalTag = VIP
reviewStatus= APPROVED
```

Sau đó ứng dụng gọi:

```java
Profile p = repository.findById("42").orElseThrow();
p.setDisplayName("Minh mới");
repository.save(p);
```

Dù ứng dụng đã đọc entity trước, `findById` chỉ dựng đối tượng từ các thuộc tính mà mapper biết. `externalTag` và `reviewStatus` không trở thành property của `Profile`, nên không được tự động mang theo vào lần `save` tiếp theo.

Kết quả kỳ vọng:

```text
_class      = com.example.Profile
id          = 42
displayName = Minh mới
email       = minh@example.test

externalTag  -> đã mất
reviewStatus -> đã mất
```

**Hệ quả:** nhiều thành phần ghi vào cùng Redis Hash bằng hai cơ chế khác nhau (Repository và `HashOperations`/`redis-cli`) có thể vô tình xóa dữ liệu của nhau. Một field “phụ trợ” vẫn là dữ liệu cần được thiết kế quyền sở hữu rõ ràng.

### Field thuộc entity nhưng có giá trị `null`

Ngay cả khi field được định nghĩa trong class, nó cũng có thể biến mất nếu giá trị không được mapper đưa vào Hash mới.

```java
repository.save(new Profile("42", "Minh mới", null));
```

Với mapping mặc định cho các property đơn giản, `email = null` không được tạo thành field `email` trong Hash mới. Do Hash cũ đã bị xóa, giá trị email trước đó không còn.

Điều này rất quan trọng với DTO cập nhật thiếu dữ liệu:

```java
// Ví dụ KHÔNG phù hợp cho yêu cầu chỉ sửa displayName:
Profile p = new Profile(request.id(), request.displayName(), null);
repository.save(p);
```

Nếu `null` được dùng để diễn đạt “người dùng không gửi email”, thì dùng `save` như trên có thể gây mất email. Ứng dụng phải phân biệt “không gửi thuộc tính” và “muốn xóa thuộc tính”.

### Property `@Transient` hoặc thuộc tính không được mapping

Một trường đánh dấu `@Transient` không được lưu bằng cơ chế ánh xạ thông thường. Nếu trước đó có field cùng tên được thêm trực tiếp vào Hash, lần `save` kế tiếp cũng có thể xóa nó. Đổi tên property, thay đổi converter, bỏ field khỏi class hoặc đổi cấu trúc class lồng nhau có thể có tác động tương tự.

## 5. Hash cũ, TTL và các cấu trúc hỗ trợ chịu ảnh hưởng gì?

| Thành phần | Ảnh hưởng cần quan tâm khi lưu lại entity |
| --- | --- |
| Field được mapping và có giá trị | Được ghi lại từ object hiện tại, có thể ghi đè giá trị cũ. |
| Field được mapping nhưng không còn sinh ra giá trị | Không xuất hiện trong Hash mới; giá trị cũ không được giữ chỉ vì trước đây tồn tại. |
| Field ghi thủ công, không được mapping | Bị mất khi Hash được tái tạo. |
| Nested field hoặc phần tử của collection | Những đường dẫn không còn được mapper sinh ra sẽ biến mất. |
| Secondary index `@Indexed` | Repository cập nhật các set/index phụ trợ theo trạng thái entity mới; không nên tự sửa riêng field được index bằng `HSET` rồi mong index tự đồng bộ. |
| TTL của Redis key | Việc xóa Hash cũ cũng xóa TTL gắn với key cũ. Hash mới có TTL hay không phụ thuộc chính sách TTL mà Repository áp dụng khi lưu. |
| Các thay đổi của request/worker khác | Có thể mất nếu worker đó ghi trước, sau đó một entity cũ được `save` lại. |

### Phân tích TTL

Redis gắn thời gian sống với **key**, không gắn riêng cho từng field của Hash. Khi key cũ bị `DEL`, thời hạn cũ mất theo. Sau khi Repository tạo key mới:

- Nếu entity có chính sách hết hạn qua `@RedisHash(timeToLive = ...)` hoặc `@TimeToLive`, Repository có thể thực thi `EXPIRE` để đặt thời hạn cho bản được lưu.
- Nếu không có chính sách TTL tương ứng, không thể kỳ vọng thời hạn do một công cụ bên ngoài từng đặt trên key cũ sẽ tự được bảo toàn.
- Nếu `@TimeToLive` nằm trên property được đọc từ Redis, property có thể phản ánh TTL/PTTL hiện còn. Cần hiểu rõ đơn vị và giá trị mà mapper dùng trước khi save lại; không mặc nhiên cho rằng một lần save luôn giữ nguyên chính xác thời điểm hết hạn ban đầu.

Ví dụ thử trong môi trường riêng:

```redis
EXPIRE profiles:42 120
TTL profiles:42
```

Sau một lần `repository.save` với entity **không có TTL được cấu hình**, kiểm tra lại:

```redis
TTL profiles:42
```

Thông thường, khi key mới được tạo mà không áp dụng thời hạn, kết quả là `-1` (key tồn tại nhưng không có expiration). Nếu key không tồn tại, `TTL` trả `-2`. Khi đã khai báo chính sách TTL cho entity, kết quả phụ thuộc thời hạn mới được tính và áp dụng.

**Không đồng nhất TTL của Redis Repository với TTL của Spring Cache.** Hai abstraction có cơ chế lưu khác nhau, nên hãy kiểm tra đúng đường ghi đang sử dụng.

### Secondary index

Nếu entity có:

```java
@Indexed
private String email;
```

Repository có thể tạo index theo keyspace/giá trị field và quản lý tập phụ trợ để dọn index cũ khi thay thế entity. Khi `email` thay đổi từ `a@example.test` sang `b@example.test`, index cũ cần được gỡ và index mới được tạo để truy vấn chính xác.

Việc cập nhật trực tiếp `HSET profiles:42 email ...` không tự kích hoạt cơ chế sửa index của Repository. Khi đó kết quả đọc bằng ID có thể khác kết quả tìm kiếm qua finder dựa trên index. Dùng `save` hoặc `PartialUpdate` khi cần duy trì đồng bộ những cấu trúc Repository quản lý.

## 6. Chọn đúng cách cập nhật theo yêu cầu

### Cách A — Repository sở hữu toàn bộ Hash: đọc, sửa, `save`

Phù hợp khi toàn bộ dữ liệu của key là các property đã mapping và ứng dụng chấp nhận thay thế toàn bộ trạng thái entity.

```java
Profile p = repository.findById("42")
        .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy profile"));

p.setDisplayName("Minh mới");
repository.save(p);
```

Với cách này, các field đã mapping và đọc lên đối tượng sẽ được lưu lại. Tuy nhiên, các field thủ công ngoài mapper vẫn không được giữ. Cách này cũng không tự bảo vệ khỏi cập nhật đồng thời của hai worker.

Chọn cách này khi thay thế toàn bộ entity là mục tiêu rõ ràng, và một thành phần thống nhất chịu trách nhiệm sở hữu Hash.

### Cách B — `PartialUpdate`: chỉ sửa property cần thay đổi

Spring Data Redis cung cấp `PartialUpdate` để biểu đạt thao tác đặt hoặc xóa từng thuộc tính mà không cần tải và ghi lại toàn bộ entity. Thao tác này đi qua cơ chế `RedisKeyValueTemplate.update(...)`, có hỗ trợ bảo trì index và một số metadata liên quan khi cập nhật.

Ví dụ:

```java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

// redisKeyValueTemplate được inject từ Spring configuration.
PartialUpdate<Profile> update =
        new PartialUpdate<Profile>("42", Profile.class)
                .set("displayName", "Minh mới");

redisKeyValueTemplate.update(update);
```

Để xóa chủ động một property:

```java
PartialUpdate<Profile> update =
        new PartialUpdate<Profile>("42", Profile.class)
                .del("email");

redisKeyValueTemplate.update(update);
```

Trong hai trường hợp này, ý định cập nhật rõ ràng hơn so với việc tạo một object thiếu thuộc tính rồi `save`. `PartialUpdate` cũng hỗ trợ thao tác với các property phức tạp, nhưng có giới hạn: cập nhật đường dẫn lồng nhau có thể không hoạt động với property dùng custom conversion; đặt lại cả một map có thể thay thế nội dung map cũ. Nếu muốn điều chỉnh TTL, phải chủ động xem xét cơ chế `refreshTtl(...)` và metadata hết hạn của entity.

Dùng `PartialUpdate` khi dữ liệu thuộc quyền sở hữu Redis Repository nhưng nghiệp vụ chỉ thay đổi một vài field. Không giả định thao tác partial update là cơ chế kiểm soát phiên bản hoặc khóa chống ghi đè khi có tranh chấp đồng thời.

### Cách C — `HashOperations`: cập nhật trường trực tiếp

Nếu một nhóm dữ liệu được thiết kế như Redis Hash do chính `RedisTemplate` quản lý, có thể cập nhật một field trực tiếp:

```java
String key = "profile-aux:42";
stringRedisTemplate.opsForHash().put(key, "reviewStatus", "APPROVED");
```

Lệnh này tương ứng với `HSET` và chỉ cập nhật field đã chọn, không xóa các field khác trong key. Tuy nhiên, thao tác thông qua `HashOperations` **không tự duy trì các secondary index của Redis Repository**, không áp dụng lifecycle callback của entity và không tự xử lý TTL theo annotation của Repository.

Không nên dùng `HSET` như một giải pháp để “giữ hộ” field nằm trong Hash mà sau đó Repository còn `save`. Một lần save tương lai vẫn có thể xóa field ấy.

### Cách D — Tách dữ liệu phụ trợ sang Redis key riêng

Khi hai thành phần có quyền sở hữu và vòng đời khác nhau, một thiết kế rõ ràng là:

```text
profiles:42            # Hash do ProfileRepository quản lý
profile-aux:42          # Hash phụ trợ do một thành phần khác quản lý
```

Như vậy, `repository.save(profile)` thay thế `profiles:42` nhưng không đụng tới `profile-aux:42`. Cần định nghĩa rõ cách dọn key phụ khi profile bị xóa, TTL tương ứng và quyền truy cập giữa các thành phần.

Nếu field phụ thực sự là một phần của domain entity, phương án khác là **thêm nó vào mô hình được ánh xạ** (ví dụ một `Map<String, String>`). Tuy vậy, phải đọc và giữ đúng dữ liệu động trong object đem save; những mục map không còn trong object vẫn có thể mất ở lần thay Hash tiếp theo.

### Bảng quyết định

| Nhu cầu | Cách nên cân nhắc | Điều phải kiểm soát |
| --- | --- | --- |
| Thay toàn bộ trạng thái entity | `repository.save` | Hash và dữ liệu mapping là một nguồn sở hữu thống nhất. |
| Chỉ đổi một trường entity | `PartialUpdate` | Index, TTL, custom converter và thao tác đồng thời. |
| Chỉ cập nhật Hash thuần do `RedisTemplate` sở hữu | `HashOperations.put/putAll` | Tự quản lý index, TTL, validation và schema nếu cần. |
| Dịch vụ khác cần lưu metadata độc lập | Key phụ trợ theo namespace riêng | Quan hệ vòng đời, xóa dữ liệu và tính nhất quán. |
| Cần bảo đảm không mất cập nhật đồng thời | Cơ chế version/CAS hoặc thao tác nguyên tử phù hợp | Conflict handling và retry có giới hạn. |

## 7. Vì sao `save` còn có thể gây mất cập nhật đồng thời?

Giả sử profile ban đầu:

```text
displayName = Minh
email       = old@example.test
```

Hai tác vụ đọc cùng một phiên bản:

```text
T1 đọc Profile(id=42, displayName=Minh, email=old@example.test)
T2 đọc Profile(id=42, displayName=Minh, email=old@example.test)

T1 đổi displayName = Minh mới
T2 đổi email       = new@example.test

T1 gọi repository.save(...)
T2 gọi repository.save(...) sau đó
```

Lần `save` của T2 có thể tạo lại toàn Hash bằng object cũ của T2, dẫn đến:

```text
displayName = Minh                 # thay đổi của T1 bị mất
email       = new@example.test
```

Dù cả T1 và T2 chỉ sửa một property trong Java, cả hai đều gửi **trạng thái entity** để lưu lại. Đây là dạng *lost update*. Ngoài ra, Repository có thể cần nhiều lệnh để quản lý hash/index; không nên coi `save` là một phép compare-and-swap hoặc giao dịch bảo vệ mọi bước.

Cách phòng tránh tùy nhu cầu:

- Ưu tiên các thao tác partial/atomic theo từng field khi nghiệp vụ cho phép; điều này giảm vùng ghi đè nhưng không giải quyết mọi xung đột logic.
- Nếu cần điều kiện “chỉ cập nhật khi dữ liệu chưa bị thay đổi”, dùng thiết kế optimistic concurrency phù hợp: đọc phiên bản hiện tại, kiểm tra và cập nhật nguyên tử qua Redis `WATCH`/`MULTI`/`EXEC` hoặc Lua script do ứng dụng quản lý, kèm chính sách retry/conflict.
- Nếu nhiều trường phải thay đổi cùng nhau, thiết kế một lệnh nguyên tử hoặc một protocol thống nhất; không trộn tùy ý một nửa bước ở Repository và một nửa ở `RedisTemplate`.
- Giữ thời gian sống của object đọc lên ngắn, tránh lưu lại entity cũ từ bộ nhớ sau nhiều phút khi các writer khác đã thay đổi nó.

Redis Repository là abstraction tiện lợi để lưu entity, không tự biến mọi lần `save` thành patch an toàn khi có nhiều writer.

## 8. Quan sát hành vi trong môi trường thử nghiệm

Bài thực hành sau dành cho Redis thử nghiệm hoặc một namespace không chứa dữ liệu thật.

**Bước 1 — Lưu entity và quan sát Hash:**

```java
repository.save(new Profile("demo-1", "An", "an@example.test"));
```

```redis
HGETALL profiles:demo-1
TYPE profiles:demo-1
TTL profiles:demo-1
```

Kỳ vọng `TYPE` là `hash`; `HGETALL` có các trường mapper ghi.

**Bước 2 — Thêm một field thủ công và quan sát:**

```redis
HSET profiles:demo-1 externalTag "manual"
HGETALL profiles:demo-1
```

**Bước 3 — Gọi save với cùng ID:**

```java
repository.save(new Profile("demo-1", "An đã đổi tên", "an@example.test"));
```

```redis
HGETALL profiles:demo-1
HEXISTS profiles:demo-1 externalTag
```

Kỳ vọng `HEXISTS` trả `0` bởi field `externalTag` không có trong entity đã được mapper ghi lại.

**Bước 4 — Kiểm tra tình huống field null:**

```java
repository.save(new Profile("demo-1", "An", null));
```

```redis
HEXISTS profiles:demo-1 email
```

Kỳ vọng `0` với cách mapping thông thường: giá trị `null` không tạo field mới và Hash cũ đã được thay thế.

**Bước 5 — Quan sát cách cập nhật riêng một field:**

```java
PartialUpdate<Profile> update =
        new PartialUpdate<Profile>("demo-1", Profile.class)
                .set("displayName", "An - partial update");
redisKeyValueTemplate.update(update);
```

So sánh `HGETALL` trước/sau để thấy thay đổi có chủ đích. Khi thử với entity có `@Indexed` hay `@TimeToLive`, quan sát thêm kết quả finder và `TTL` để phân biệt metadata với field Hash.

Trong thử nghiệm tự động, nên dùng Redis riêng (ví dụ Testcontainers), namespace/ID cố định của test, dọn dữ liệu thử nghiệm sau mỗi case và không chạy thao tác xóa rộng trên instance dùng chung.

## 9. Những hiểu lầm phổ biến

**“`save` chỉ update các property đã sửa.”**  
Không đúng với Redis Repository mặc định khi thay thế entity đã tồn tại. Entity được chuyển thành biểu diễn Hash mới; các field Hash không còn nằm trong biểu diễn này bị mất.

**“Đã gọi `findById` rồi mới `save` thì field thêm thủ công sẽ được giữ.”**  
Không bảo đảm. `findById` tái tạo object theo mapping, không đưa mọi field lạ trong Hash vào object.

**“Dùng `@Transient` cho field phụ sẽ bảo vệ field đó khỏi bị ghi đè.”**  
Ngược lại, field bị loại khỏi mapping sẽ không được Repository ghi lại vào Hash sau khi thay thế.

**“Thêm field bằng `HSET` là an toàn vì `HSET` không xóa field khác.”**  
Mệnh đề về riêng `HSET` là đúng, nhưng một lần `repository.save` trong tương lai có thể tái tạo toàn bộ Hash và xóa field thêm thủ công.

**“`save` giữ nguyên TTL vì chỉ có dữ liệu field thay đổi.”**  
Không thể dựa vào giả định đó: Hash cũ có thể bị `DEL`, làm mất TTL cũ, rồi chính sách TTL của Repository quyết định hạn mới.

**“Đổi `save` sang `PartialUpdate` bảo đảm chống mọi lost update.”**  
Không. Partial update giảm khả năng ghi đè những field không liên quan, nhưng các phép cập nhật đồng thời lên cùng field hay ràng buộc liên trường vẫn cần chính sách nhất quán/đồng bộ.

## 10. Nguyên tắc thiết kế khi dùng Redis Repository

1. Xác định rõ **ai sở hữu mỗi Hash**. Nếu Repository sở hữu `profiles:42`, tránh ghi field thủ công vào cùng key.
2. Dùng `save` khi muốn thay thế toàn bộ entity; dùng `PartialUpdate` hoặc thiết kế khác khi chỉ muốn sửa vài property.
3. Không dùng DTO thiếu field để dựng entity rồi `save` nếu `null` có nghĩa “không thay đổi”.
4. Khi thay đổi schema hoặc custom converter, xét tác động tới những field không còn được sinh ra; cần kế hoạch di chuyển dữ liệu nếu chúng quan trọng.
5. Đối với property `@Indexed`, đi qua abstraction biết cách cập nhật index; tránh để dữ liệu Hash và index lệch nhau.
6. Kiểm tra lại TTL sau đường ghi, nhất là khi có kết hợp `@TimeToLive`, thời hạn đặt thủ công và nhiều cơ chế truy cập Redis.
7. Thiết kế cơ chế tránh lost update nếu nhiều tác vụ cùng ghi entity có chung ID.
8. Quan sát `HGETALL`, `HEXISTS` và `TTL` trên môi trường thử nghiệm để hiểu tác động thực tế trước khi dùng với dữ liệu quan trọng.

**Ghi nhớ:** `repository.save(entity)` của Spring Data Redis Repository thể hiện ý định **lưu lại biểu diễn đầy đủ của entity**, và với entity đã tồn tại nó có thể **xóa Hash cũ rồi tạo lại từ mapping**. Muốn giữ dữ liệu ngoài entity hoặc chỉ sửa một field, phải chọn mô hình sở hữu Hash và API cập nhật tương ứng.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Repositories Anatomy](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/anatomy.html): minh họa thao tác `DEL`, ghi lại Hash và cập nhật secondary index khi thay thế entity.
- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): quy tắc mapping và lưu ý rằng field không được ánh xạ sẽ mất khi Hash được tạo lại.
- [Spring Data Redis — Repository Usage / Partial Updates](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html): `CrudRepository` và `PartialUpdate`.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): `@RedisHash(timeToLive)`, `@TimeToLive` và tác động lên expiration.
