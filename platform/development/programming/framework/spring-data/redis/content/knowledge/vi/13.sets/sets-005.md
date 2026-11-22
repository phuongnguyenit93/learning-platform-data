# Thiết kế danh sách thành viên duy nhất bằng Redis Set

Trong nhiều nghiệp vụ, ứng dụng cần quản lý **một tập thành viên không được trùng lặp**: người dùng tham gia nhóm, người đã đăng ký sự kiện, mã sản phẩm được đánh dấu yêu thích, quyền được gán cho một tài khoản hoặc danh sách những tác vụ đã nhìn thấy. Nếu dùng một danh sách thông thường, ứng dụng phải tự tìm và loại bỏ phần tử trùng; khi nhiều request cùng ghi, kiểm tra rồi thêm bằng hai thao tác riêng còn dễ tạo lỗi đồng thời.

**Redis Set** được thiết kế cho bài toán này: mỗi phần tử (**member**) trong một Set là duy nhất theo biểu diễn mà Redis lưu. Lệnh `SADD` thêm phần tử nếu nó chưa tồn tại, `SISMEMBER` kiểm tra thành viên, `SREM` xóa phần tử, và `SCARD` đếm số member. Spring Data Redis ánh xạ những thao tác đó qua `SetOperations`, thường được lấy từ `StringRedisTemplate.opsForSet()`.

Bài học hướng dẫn cách chọn Redis Set, xác định thế nào là “cùng một thành viên”, tạo API thêm/kiểm tra/xóa an toàn khi nhiều ứng dụng cùng truy cập, thiết kế key và vòng đời dữ liệu, xử lý giới hạn số thành viên, duyệt Set lớn và đánh giá các nhu cầu mà Set không đáp ứng trực tiếp như sắp xếp, phân trang hoặc TTL riêng cho từng phần tử.

## 1. Redis Set là gì?

Một Redis Set là tập hợp các member kiểu chuỗi nhị phân (**binary-safe strings**) nằm dưới một Redis key. Các member không có thứ tự được bảo đảm và mỗi giá trị member chỉ xuất hiện tối đa một lần trong cùng Set.

Giả sử Redis lưu các ID tài khoản tham gia nhóm `42`:

```redis
SADD group:42:members user-101 user-202 user-303
# 3: đã thêm ba member mới

SADD group:42:members user-202
# 0: user-202 đã có trong Set

SISMEMBER group:42:members user-101
# 1: có trong Set

SCARD group:42:members
# 3: số member của Set
```

Mô hình:

```text
Redis key: group:42:members        (type: set)
  ├── user-101
  ├── user-202
  └── user-303

SADD group:42:members user-202
   → Không tạo thêm một bản sao user-202

SADD group:42:members user-404
   → Tập hợp có thêm một thành viên, SCARD trở thành 4
```

**Điểm cốt lõi:** Redis loại bỏ việc trùng lặp ở **cấp member của một Set**. Nếu hai Redis key khác nhau đều có `user-202`, đó không phải trùng lặp trong cùng Set. Nếu hệ thống yêu cầu “mỗi user được phép thuộc đúng một nhóm trên toàn hệ thống”, cần thêm bất biến liên nhóm ở tầng thiết kế dữ liệu hoặc thao tác nguyên tử khác.

### Set khác List và Sorted Set

| Cấu trúc Redis | Member trùng lặp? | Thứ tự | Truy vấn điển hình | Khi nào chọn |
| --- | --- | --- | --- | --- |
| **Set** | Không, với cùng biểu diễn member | Không có thứ tự ổn định | Có thuộc tập? Thêm/xóa? Đếm? Giao/hợp/hiệu? | Danh sách ID duy nhất, kiểm tra membership |
| **List** | Có thể trùng | Có thứ tự theo vị trí trong list | Push/pop hai đầu, đọc theo vị trí | Hàng đợi/danh sách thứ tự được duy trì |
| **Sorted Set** | Member duy nhất | Có thứ tự theo score và quy tắc so sánh khi hòa score | Top N, ranking, range theo score | Vừa cần duy nhất vừa cần xếp hạng/phân trang có thứ tự |
| **Hash** | Field name duy nhất | Không bảo đảm thứ tự field | Field → value, đọc/ghi giá trị theo field | Mỗi ID có dữ liệu/thuộc tính riêng trong cùng key |

Trong Redis List, một thiết kế kiểu “`LPOS` kiểm tra rồi `RPUSH` nếu chưa có” **không nguyên tử**: hai client có thể cùng thấy chưa tồn tại và cùng thêm. Với Set, một lệnh `SADD` đã giải quyết điều kiện duy nhất cho từng member.

Sorted Set cũng có member duy nhất nhưng phải quản lý **score**; nó phù hợp hơn nếu cần lấy các thành viên mới nhất, top điểm hoặc phân trang theo thứ tự. Không nên dùng Sorted Set nếu nghiệp vụ chỉ cần kiểm tra tồn tại và không có score tự nhiên.

## 2. Thế nào được xem là “cùng một thành viên”?

Redis so sánh giá trị member theo dữ liệu được lưu, chứ không hiểu đối tượng Java, tên người dùng hay quy tắc nghiệp vụ. Với `StringRedisTemplate`, member Java String được chuyển thành byte UTF-8. Hai chuỗi có byte khác nhau sẽ được Redis coi là **hai member khác nhau**, trừ trường hợp ứng dụng chuẩn hóa chúng trước khi ghi.

```redis
SADD demo:members user-42
# 1

SADD demo:members USER-42
# 1: khác chữ hoa/chữ thường

SADD demo:members " user-42 "
# 1: có khoảng trắng ở đầu/cuối

SCARD demo:members
# 3
```

Nếu nghiệp vụ cho rằng ba giá trị trên đại diện cùng một user, Redis Set **không tự suy luận được điều đó**.

### Quy tắc định danh nên thiết lập từ đầu

1. **Dùng ID ổn định** thay vì display name. Tên hiển thị có thể đổi, trùng giữa người dùng, hoặc chứa biến thể Unicode.
2. **Chỉ chuẩn hóa theo hợp đồng đã thống nhất.** Ví dụ nếu user ID được thiết kế là UUID chuẩn chữ thường, hãy áp dụng giống nhau ở mọi producer. Không tùy tiện lower-case email hoặc trim một mã nghiệp vụ nếu việc đó có thể thay đổi ý nghĩa định danh.
3. **Giữ nguyên các ký tự có ý nghĩa.** ID `"0012"` và `"12"` có thể là hai ID khác nhau; không ép sang số rồi chuyển lại thành chuỗi nếu không được phép.
4. **Thống nhất serializer.** Một producer Java dùng JDK binary serialization cho member và một producer Python ghi UTF-8 text có thể cùng nhìn thấy “user-42” ở mức code nhưng lưu **byte khác nhau**.
5. **Phân biệt phạm vi duy nhất.** `group:42:members` và `group:43:members` là hai miền membership; trùng user giữa hai nhóm có thể là hành vi hợp lệ.

Ví dụ hàm kiểm tra ID dành cho hệ thống minh họa mà ID chỉ gồm chữ, số, gạch dưới và gạch ngang:

```java
import java.util.Objects;
import java.util.regex.Pattern;

public final class MemberId {
    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private MemberId() {}

    public static String requireValid(String id) {
        Objects.requireNonNull(id, "memberId");
        if (!VALID.matcher(id).matches()) {
            throw new IllegalArgumentException("Invalid memberId");
        }
        return id;
    }
}
```

Quy tắc ký tự ở đây là **ví dụ hợp đồng**, không phải giới hạn của Redis. Nếu hệ thống dùng ULID, UUID, mã khách hàng hoặc định danh từ hệ thống khác, phải thiết kế validator tương ứng. Giá trị đã chuẩn hóa còn cần thống nhất giữa mọi dịch vụ đọc/ghi cùng tập hợp.

## 3. Lệnh Set cần biết và độ phức tạp

| Thao tác | Redis command | Kết quả/ý nghĩa | Độ phức tạp điển hình |
| --- | --- | --- | --- |
| Thêm một member | `SADD key member` | `1` nếu thêm mới, `0` nếu đã có | Trung bình `O(1)` cho mỗi member |
| Thêm nhiều member | `SADD key a b c` | Số member **mới** được thêm | `O(M)` theo số member đầu vào |
| Kiểm tra một member | `SISMEMBER key member` | `1` có, `0` không | Trung bình `O(1)` |
| Kiểm tra nhiều member | `SMISMEMBER key a b c` | Một kết quả 0/1 cho từng member | `O(M)`; cần Redis hỗ trợ lệnh |
| Xóa member | `SREM key member...` | Số member thực sự bị xóa | `O(M)` theo số member yêu cầu |
| Đếm member | `SCARD key` | Số phần tử hiện có | `O(1)` |
| Trả toàn bộ member | `SMEMBERS key` | Toàn bộ tập hợp, không có thứ tự bảo đảm | **`O(N)`** theo cardinality |
| Kiểm tra giao hai/nhiều tập | `SINTER key1 key2...` | Tập member có mặt trong mọi tập | Phụ thuộc số/từng kích thước tập; có thể đắt với tập lớn |
| Hợp của nhiều tập | `SUNION key1 key2...` | Tập member có mặt trong ít nhất một tập | Tăng theo tổng số phần tử cần xét |
| Hiệu tập hợp | `SDIFF key1 key2...` | Member thuộc tập thứ nhất mà không thuộc các tập sau | Phụ thuộc kích thước và số tập |
| Duyệt dần | `SSCAN key cursor ...` | Một phần member cùng cursor tiếp theo | Tổng vòng quét thường tăng theo `N` |
| Lấy ngẫu nhiên, không xóa | `SRANDMEMBER key` | Một member ngẫu nhiên | Thích hợp chọn mẫu, không bảo đảm phân phối nghiệp vụ theo trọng số |
| Lấy ngẫu nhiên, có xóa | `SPOP key` | Xóa và trả một member | Thao tác thay đổi Set; phải phân biệt với chọn mẫu |
| Chuyển member giữa hai Set | `SMOVE source destination member` | Chuyển nếu member tồn tại ở nguồn | Thường `O(1)`, nhưng yêu cầu routing phù hợp trong Cluster |

Trong bảng, `N` là số member của Set đang xét; `M` thường là số member đưa vào một command. Tính “trung bình” có ý nghĩa vì Redis dùng cấu trúc nội bộ tối ưu cho truy vấn membership, nhưng độ trễ thực tế còn phụ thuộc kích thước chuỗi member, mạng, tải CPU và cách Redis biểu diễn Set.

### Lệnh `SADD` bảo đảm điều gì?

Khi hai client đồng thời cùng gửi:

```redis
SADD group:42:members user-999
```

Redis xử lý mỗi command như một thao tác nguyên tử trên Set. Nếu member ban đầu chưa tồn tại thì trong điều kiện bình thường **một** command thêm thành công và nhận `1`, còn command còn lại thấy member đã có và nhận `0`. Không tạo ra hai member giống nhau.

`SADD` là **idempotent về trạng thái membership**: gửi lại cùng lệnh với cùng key/member không tạo thêm một bản sao. Tuy nhiên response bị mất do timeout vẫn có thể làm ứng dụng không chắc lệnh đầu đã thành công hay chưa; không thể suy ra “timeout nghĩa là chưa thêm”.

### Kiểm tra rồi thêm có cần thiết không?

Không cần đoạn code:

```java
if (!Boolean.TRUE.equals(redis.opsForSet()
        .isMember("group:42:members", "user-999"))) {
    redis.opsForSet().add("group:42:members", "user-999");
}
```

Điều kiện `isMember` không thêm ràng buộc nguyên tử và còn tốn thêm round trip. Nếu yêu cầu đơn thuần là đảm bảo duy nhất, hãy **gọi `SADD` trực tiếp** và đọc số phần tử được thêm.

## 4. Thiết kế key cho danh sách thành viên

Với bài toán “những user nào thuộc group này?”, key trực tiếp theo group là lựa chọn tự nhiên:

```text
group:{groupId}:members

group:team-42:members
  user-101
  user-202
  user-303
```

Lưu ý dấu ngoặc nhọn `{groupId}` trong cách trình bày ở đây là **placeholder**, không mặc định là ký tự thực trong key. Trong Redis Cluster, dấu ngoặc nhọn có ý nghĩa **hash tag** nếu xuất hiện trong key thực tế, nên cần phân biệt hai cách viết.

Một thiết kế key nên trả lời:

- **Đối tượng chủ sở hữu Set là gì?** Group, event, resource, tenant hay session?
- **Member là loại định danh nào?** User ID, product ID, permission name hay chuỗi đặc biệt?
- **Một member có được nằm ở nhiều Set không?** Nếu có, đây là quan hệ nhiều-nhiều.
- **Ai là bên ghi và bên xóa?** Nhiều writer có cùng hợp đồng canonical ID không?
- **Tập hợp có giới hạn tối đa không?** Một nhóm có thể có bao nhiêu member?
- **Tập hợp có hết hạn không?** Nếu có, toàn Set hết hạn hay từng membership hết hạn riêng?
- **Cần thứ tự hoặc truy vấn ngược không?** Từ group tìm user là một truy vấn khác với từ user tìm group.

### Một chiều và hai chiều của membership

Mô hình đơn giản:

```text
group:42:members → {user-101, user-202}
group:43:members → {user-101, user-303}
```

Truy vấn “user-101 có trong group 42 không?” có thể gọi `SISMEMBER group:42:members user-101` rất nhanh.

Nhưng truy vấn “user-101 thuộc những group nào?” sẽ khó nếu chỉ có key theo group: ứng dụng không nên quét mọi group để tìm một user. Có thể duy trì **chỉ mục ngược**:

```text
user:user-101:groups → {42, 43}
user:user-202:groups → {42}
user:user-303:groups → {43}
```

Khi user tham gia group, ứng dụng phải cập nhật cả `group:42:members` và `user:user-101:groups`. Đây là **hai Redis key**, vì vậy tính duy nhất trong từng Set không tự bảo đảm hai chỉ mục luôn nhất quán. Nếu một lần ghi thành công và lần khác thất bại, hai chiều có thể lệch nhau.

Các cách giải quyết tùy yêu cầu nghiệp vụ:

1. Chỉ lưu một chiều và truy vấn chiều còn lại từ database chính nếu nhu cầu ngược hiếm.
2. Lưu hai chiều nhưng xác định rõ nguồn sự thật; chấp nhận eventual consistency, retry idempotent và có job đối soát.
3. Nếu bắt buộc cập nhật nguyên tử, dùng transaction/script phù hợp **với tất cả key nằm trong cùng hash slot khi triển khai Redis Cluster**.
4. Với dữ liệu phân quyền hoặc membership cần ràng buộc mạnh và giao dịch nhiều bảng, lưu trạng thái chuẩn trong cơ sở dữ liệu giao dịch rồi dùng Redis Set làm projection/cache có thể an toàn hơn.

Không nên tự thêm hash tag chung cho mọi group chỉ để cho phép multi-key script: điều đó có thể dồn dữ liệu về một Redis Cluster slot và một node, làm mất khả năng phân tải.

## 5. Spring Data Redis: dùng `SetOperations`

Với Spring Boot có `spring-boot-starter-data-redis`, có thể sử dụng `StringRedisTemplate` nếu key/member là chuỗi UTF-8.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Cấu hình Redis cho Spring Boot 3.x trong môi trường thử nghiệm:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Trong container hoặc Kubernetes, `localhost` chỉ tới chính môi trường của process hiện tại; cần chọn host theo topology thật của ứng dụng. Dependency và kết nối chỉ chuẩn bị đường giao tiếp với Redis, không tự khởi động Redis server.

### 5.1. Service quản lý thành viên duy nhất

```java
import java.util.Objects;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMembershipService {

    private final SetOperations<String, String> members;

    public GroupMembershipService(StringRedisTemplate redis) {
        this.members = redis.opsForSet();
    }

    public boolean join(String groupId, String userId) {
        String key = keyFor(groupId);
        String member = MemberId.requireValid(userId);

        Long added = members.add(key, member); // SADD
        if (added == null) {
            throw new IllegalStateException("No SADD result available");
        }
        return added == 1L;
    }

    public boolean isMember(String groupId, String userId) {
        Boolean found = members.isMember(
                keyFor(groupId),
                MemberId.requireValid(userId)
        ); // SISMEMBER
        return Boolean.TRUE.equals(found);
    }

    public boolean leave(String groupId, String userId) {
        Long removed = members.remove(
                keyFor(groupId),
                MemberId.requireValid(userId)
        ); // SREM
        if (removed == null) {
            throw new IllegalStateException("No SREM result available");
        }
        return removed == 1L;
    }

    public long count(String groupId) {
        Long size = members.size(keyFor(groupId)); // SCARD
        return Objects.requireNonNull(size, "No SCARD result available");
    }

    private static String keyFor(String groupId) {
        return "group:" + MemberId.requireValid(groupId) + ":members";
    }
}
```

Trong ví dụ, `MemberId.requireValid` là hàm chuẩn hóa/kiểm tra ID đã giới thiệu ở mục 2. Khi dùng logic thật, nên đặt tên và quy tắc validate rõ theo từng loại `groupId` và `userId`.

Ý nghĩa các giá trị trả về:

- `join(...) == true`: trong lời gọi hoàn tất bình thường, member **mới được thêm** vào Redis Set.
- `join(...) == false`: member đã có trong Set, nên trạng thái cuối vẫn đúng.
- `leave(...) == true`: một member đã bị xóa.
- `leave(...) == false`: member không tồn tại ở thời điểm lệnh xử lý.
- `isMember(...)`: phản ánh trạng thái membership tại thời điểm lệnh kiểm tra.
- `count(...)`: số lượng member hiện có; đây là một snapshot số lượng tại thời điểm truy vấn, không khóa những thay đổi về sau.

Đoạn mã dành cho các lời gọi Spring Data Redis thông thường, không chạy dưới một callback pipeline/transaction nơi một số API có thể trả `null` tạm thời vì kết quả sẽ được xử lý sau. Trong nghiệp vụ quan trọng, lỗi kết nối hoặc timeout phải được xử lý theo chính sách của ứng dụng; không nên biến mọi lỗi Redis thành `false` vì sẽ khiến “không có thành viên” bị nhầm với “không thể kiểm tra”.

### 5.2. Thêm một nhóm member trong một command

```java
Long added = stringRedisTemplate.opsForSet().add(
        "group:42:members",
        "user-101",
        "user-202",
        "user-101"
);
```

Nếu Set ban đầu rỗng thì `added` bằng `2`, vì `user-101` bị lặp trong danh sách đầu vào nhưng chỉ được lưu một lần. Với Redis Set, **kết quả `SADD` là số member mới**, không phải tổng số member sau khi thêm và không phải số tham số đã truyền.

Đối với import lớn, cần chia batch có giới hạn. Một command chứa hàng trăm nghìn member vẫn tạo tải CPU và payload lớn; kết hợp batching/pipelining phù hợp giúp kiểm soát tài nguyên, nhưng tổng số member phải xử lý vẫn còn đó.

## 6. Đọc member: chọn đúng truy vấn thay vì nạp cả Set

Ví dụ một nhóm có một triệu member, ứng dụng chỉ muốn biết `user-101` có trong nhóm không. Tránh đọc toàn bộ danh sách rồi tìm trong Java:

```java
// Không phù hợp khi chỉ cần kiểm tra một member:
Set<String> all = stringRedisTemplate.opsForSet()
        .members("group:42:members"); // SMEMBERS

boolean exists = all != null && all.contains("user-101");
```

`SMEMBERS` có chi phí `O(N)` và trả về **tất cả** member. Với một triệu member, Redis phải tạo phản hồi rất lớn, mạng phải truyền dữ liệu và Java cần cấp phát tập hợp chứa các giá trị đã nhận.

Thay vào đó:

```java
Boolean exists = stringRedisTemplate.opsForSet()
        .isMember("group:42:members", "user-101"); // SISMEMBER
```

Để đếm, dùng `SCARD`:

```java
Long total = stringRedisTemplate.opsForSet()
        .size("group:42:members");
```

Đừng dùng `members(key).size()` chỉ để đếm, bởi cách đó tải toàn bộ Set trong khi Redis đã duy trì cardinality và cung cấp `SCARD`.

### `SMEMBERS` có bao giờ phù hợp?

Có, nếu Set **nhỏ, được giới hạn chặt** và nghiệp vụ thực sự cần toàn bộ member, ví dụ một role chứa tối đa 10 permission hoặc một room có tối đa 30 participant. Khi đó tải toàn bộ có thể đơn giản và rẻ hơn thiết kế phức tạp.

Tuy nhiên cần có giới hạn rõ ràng. Một API “lấy mọi thành viên” hoạt động tốt với 20 phần tử hôm nay có thể trở thành điểm nghẽn khi dữ liệu tăng lên 200.000 phần tử về sau.

### Redis Set không có thứ tự phân trang

`SMEMBERS` trả member **không có thứ tự bảo đảm**. Không nên xây API:

```java
List<String> page = new ArrayList<>(allMembers).subList(0, 20);
```

và gọi đó là “20 thành viên đầu tiên”, vì thứ tự Set không có nghĩa ổn định, chưa kể toàn bộ dữ liệu phải được tải về.

Nếu cần danh sách thành viên **theo thời gian tham gia**, cân nhắc thêm Sorted Set:

```redis
ZADD group:42:joinedAt 1762930000000 user-101
ZADD group:42:joinedAt 1762932000000 user-202
ZRANGE group:42:joinedAt 0 19
```

Sorted Set tự bảo đảm member duy nhất trong chính Sorted Set, đồng thời có score để đọc theo thứ tự. Nếu vẫn giữ cả Set và Sorted Set, phải định nghĩa nguồn sự thật và cách đồng bộ hai cấu trúc; trong một số trường hợp, **chỉ Sorted Set** đã đáp ứng đủ membership và order, không cần lưu trùng.

Đừng mặc định có thể dùng score thời gian để đảm bảo thứ tự tuyệt đối khi nhiều thành viên có timestamp giống nhau: Redis có quy tắc so sánh member khi score hòa; nếu cần thứ tự nghiệp vụ riêng, thiết kế tie-breaker hoặc khóa sắp xếp phù hợp.

## 7. Duyệt Set lớn bằng `SSCAN`

Khi cần xử lý hàng trăm nghìn member trong job bảo trì hoặc export, sử dụng `SSCAN` để chia việc duyệt:

```redis
SSCAN group:42:members 0 COUNT 200
# Redis trả [cursor mới, danh sách member]

SSCAN group:42:members <cursor-moi> COUNT 200
# Tiếp tục đến khi Redis trả cursor 0
```

Một số điểm cần hiểu chính xác:

- `COUNT 200` là **gợi ý** về lượng việc mỗi lần scan, không phải giới hạn cứng số member được trả về.
- Một lượt scan có thể trả **rỗng** nhưng cursor chưa bằng `0`; vẫn phải tiếp tục.
- Toàn bộ vòng duyệt thường có tổng chi phí tăng theo số member; `SSCAN` giúp chia nhỏ thao tác chứ không làm một triệu member thành công việc `O(1)`.
- Với Set thay đổi trong lúc scan, không có snapshot giao dịch. Một member có thể xuất hiện lặp; member được thêm/xóa trong thời gian quét có thể được quan sát tùy thời điểm.
- Một số biểu diễn compact có thể khiến Redis trả phần lớn hoặc toàn bộ member trong một lượt scan, dù đã ghi `COUNT` thấp.
- `MATCH` có thể lọc member theo mẫu, nhưng không làm Redis Set trở thành chỉ mục tìm kiếm theo tiền tố.

### Ví dụ `SetOperations.scan`

```java
import java.util.function.Consumer;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMemberScanner {
    private final StringRedisTemplate redis;

    public GroupMemberScanner(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void forEachMember(
            String groupId,
            Consumer<String> processor
    ) {
        String key = "group:" + MemberId.requireValid(groupId) + ":members";
        ScanOptions options = ScanOptions.scanOptions()
                .count(200)
                .build();

        try (Cursor<String> cursor =
                     redis.opsForSet().scan(key, options)) {
            while (cursor.hasNext()) {
                processor.accept(cursor.next());
            }
        }
    }
}
```

`try-with-resources` bảo đảm đóng cursor/tài nguyên kết nối liên quan. `processor` nên xử lý theo từng member hoặc đưa vào batch có kích thước giới hạn, không giữ tất cả member trong một `List` lớn. Nếu công việc cần chống xử lý lặp, `processor` phải idempotent hoặc có checkpoint/định danh xử lý riêng.

Không dùng `SSCAN` như API “trang 1, 2, 3” ổn định khi Set có thay đổi đồng thời. Cursor là trạng thái duyệt, không phải offset sắp xếp. Nếu cần pagination có thứ tự và cursor bền vững, nên chọn mô hình dữ liệu có thứ tự và chính sách nhất quán tương ứng.

## 8. Tập hợp thành viên và các phép toán Set

Redis Set có lợi thế khi nghiệp vụ cần câu trả lời về **quan hệ tập hợp**:

- User tham gia cả nhóm A **và** nhóm B.
- User thuộc ít nhất một trong hai nhóm.
- User có trong nhóm A nhưng chưa có trong nhóm B.

Giả sử:

```redis
SADD group:A:members u1 u2 u3
SADD group:B:members u2 u3 u4
```

| Câu hỏi | Lệnh | Kết quả logic |
| --- | --- | --- |
| Thành viên chung của A và B | `SINTER group:A:members group:B:members` | `{u2, u3}` |
| Thành viên thuộc A hoặc B | `SUNION group:A:members group:B:members` | `{u1, u2, u3, u4}` |
| Thành viên A không thuộc B | `SDIFF group:A:members group:B:members` | `{u1}` |

Trong Spring Data Redis:

```java
Set<String> both = stringRedisTemplate.opsForSet()
        .intersect("group:A:members", "group:B:members");

Set<String> either = stringRedisTemplate.opsForSet()
        .union("group:A:members", "group:B:members");

Set<String> onlyA = stringRedisTemplate.opsForSet()
        .difference("group:A:members", "group:B:members");
```

Với tập hợp lớn, những lệnh trả **toàn bộ kết quả** có thể tiêu thụ nhiều CPU/mạng/bộ nhớ, kể cả khi câu hỏi nghiệp vụ chỉ là “có giao nhau không?” hoặc “có bao nhiêu thành viên chung?”. Với Redis hỗ trợ, `SINTERCARD` có thể lấy số lượng giao mà không phải gửi danh sách member, và có tùy chọn `LIMIT` để dừng việc đếm ở ngưỡng theo ngữ nghĩa command. Phải kiểm tra phiên bản Redis và cách client hỗ trợ lệnh trước khi dùng.

### Redis Cluster và multi-key Set operations

Trong Redis Cluster, các command nhiều key như `SINTER`, `SUNION`, `SDIFF` hoặc `SMOVE` phải tuân thủ quy tắc hash slot phù hợp; yêu cầu cross-slot thông thường sẽ bị Redis từ chối. Hai key `group:A:members` và `group:B:members` không chắc nằm cùng slot.

Nếu thường xuyên cần giao của những tập thuộc **cùng tenant**, có thể cân nhắc hash tag có kiểm soát:

```text
tenant:{t42}:group:A:members
tenant:{t42}:group:B:members
```

Hai key này được Redis Cluster đưa vào cùng hash slot nhờ `{t42}`. Đổi lại, mọi key cùng hash tag có thể dồn tải về một slot/node. Chọn hash tag theo nhu cầu truy vấn cụ thể, không gộp toàn bộ hệ thống vào một tag.

Nếu các Set nằm ở nhiều node khác nhau và cần phép toán nhiều key, có thể phải thay đổi mô hình dữ liệu, thực hiện tổng hợp có giới hạn phía ứng dụng hoặc xây index/materialized view phù hợp. Những cách này có chi phí và tính nhất quán riêng; không mặc định phép Set trên Redis Cluster sẽ hoạt động xuyên slot.

## 9. Giới hạn số thành viên: `SCARD` rồi `SADD` chưa đủ

Giả sử một nhóm chỉ được có tối đa **100 member**. Một cách viết dễ nhầm:

```java
Long count = redis.opsForSet().size("group:42:members");
if (count != null && count < 100) {
    redis.opsForSet().add("group:42:members", "user-999");
}
```

Vấn đề: `SCARD` và `SADD` là hai command. Nếu nhóm có 99 member và hai request khác nhau cùng kiểm tra, cả hai đều có thể thấy `99` rồi mỗi request thêm một member khác. Kết quả là 101 member, vượt giới hạn.

Trong trường hợp trần 100 là **bất biến nghiệp vụ bắt buộc**, phải thực hiện “đã có member chưa?”, “còn chỗ không?” và “thêm member” trong **một thao tác nguyên tử**.

### 9.1. Lua script thêm thành viên có giới hạn

```lua
-- KEYS[1]: key Set
-- ARGV[1]: member ID
-- ARGV[2]: số thành viên tối đa (số nguyên dương)

if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
    return 0 -- Đã là thành viên: không tăng số lượng
end

if redis.call('SCARD', KEYS[1]) >= tonumber(ARGV[2]) then
    return -1 -- Nhóm đã đầy
end

return redis.call('SADD', KEYS[1], ARGV[1])
-- 1: thêm thành công
```

Redis thực thi Lua script như một đơn vị nguyên tử đối với các command từ client khác trên instance xử lý script. Nhờ vậy hai request không thể cùng “chen” thao tác `SADD` vào giữa lần kiểm tra cardinality và hành động thêm của script này.

Đây là **giải pháp cho một Set**. Nếu cùng lúc cần kiểm tra trạng thái ở database, ghi chỉ mục ngược hoặc gửi sự kiện ra broker, tính nguyên tử không tự mở rộng sang các hệ thống đó.

### 9.2. Gọi script bằng Spring Data Redis

```java
import java.util.List;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class CapacityLimitedGroupService {

    private static final int MAX_MEMBERS = 100;

    private static final RedisScript<Long> ADD_IF_ROOM =
            RedisScript.of(
                    """
                    if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
                        return 0
                    end
                    if redis.call('SCARD', KEYS[1]) >= tonumber(ARGV[2]) then
                        return -1
                    end
                    return redis.call('SADD', KEYS[1], ARGV[1])
                    """,
                    Long.class
            );

    private final StringRedisTemplate redis;

    public CapacityLimitedGroupService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public JoinResult join(String groupId, String userId) {
        String key = "group:" + MemberId.requireValid(groupId) + ":members";
        String member = MemberId.requireValid(userId);

        Long value = Objects.requireNonNull(
                redis.execute(
                        ADD_IF_ROOM,
                        List.of(key),
                        member,
                        Integer.toString(MAX_MEMBERS)
                ),
                "No Redis script result"
        );

        if (value == 1L) return JoinResult.ADDED;
        if (value == 0L) return JoinResult.ALREADY_MEMBER;
        if (value == -1L) return JoinResult.FULL;
        throw new IllegalStateException("Unexpected Redis script result");
    }

    public enum JoinResult {
        ADDED,
        ALREADY_MEMBER,
        FULL
    }
}
```

Script chỉ truy cập một key thông qua `KEYS[1]`, vì vậy không có vấn đề multi-key cross-slot trong Redis Cluster. Java sử dụng text block, phù hợp với Java 17+; `RedisScript.of(...)` cung cấp kiểu kết quả `Long` cho giá trị số nguyên Lua trả về.

Khi member đã có, trả `ALREADY_MEMBER` ngay cả lúc nhóm đã đầy, vì thao tác idempotent đó **không chiếm thêm slot**. Đây là một quyết định nghiệp vụ có chủ đích; nếu business muốn hành vi khác, cần thiết kế API riêng.

### 9.3. Giới hạn không thay thế quy tắc phân quyền

Lua script chỉ thực thi ràng buộc số lượng. Ứng dụng vẫn phải xác định:

- Người gọi có quyền thêm member vào group không?
- Member ID có hợp lệ, đang tồn tại và được phép tham gia không?
- Trường hợp xóa member và thêm lại có cần xử lý sự kiện/thu phí không?
- Nếu Redis chỉ là cache, trạng thái chính trong database có bất biến tương đương hay không?

Redis Set không tự biết những quy tắc đó. Đồng thời, nếu client timeout sau khi script đã được Redis xử lý, caller có thể phải đọc lại membership để xác minh trạng thái trước khi retry hoặc phát sự kiện nghiệp vụ.

## 10. TTL và vòng đời của Set

Redis TTL thông thường áp dụng cho **toàn bộ key Set**, không phải riêng từng member:

```redis
SADD event:42:checkin user-101 user-202
EXPIRE event:42:checkin 86400
TTL event:42:checkin
```

Điều đó có nghĩa cả tập check-in sẽ hết hạn theo TTL của key. Nếu muốn một user hết hạn tư cách thành viên sau 15 phút trong khi những user khác vẫn còn, mô hình Set thông thường **không có TTL riêng cho từng member**.

Các cách thiết kế khác tùy nhu cầu:

| Yêu cầu | Thiết kế cân nhắc |
| --- | --- |
| Một Set tạm hết hạn cùng lúc | Đặt TTL ở key Set |
| Membership duy trì lâu dài | Key không TTL, có quy trình xóa khi rời nhóm |
| Từng member có thời điểm hết hạn riêng | Sorted Set với score là expiration timestamp + kiểm tra/dọn member hết hạn |
| Membership gắn với session TTL riêng | Key riêng theo member/session, có thể kèm chỉ mục nhóm |
| Membership là dữ liệu cốt lõi cần bền vững | Database chính làm nguồn sự thật; Redis phục vụ cache/index theo nhu cầu |

### Gắn TTL khi tạo Set: tránh khoảng trống giữa các lệnh

```redis
SADD event:42:checkin user-101
EXPIRE event:42:checkin 86400
```

Hai command trên **không nguyên tử** với nhau. Nếu ứng dụng crash sau `SADD` nhưng trước `EXPIRE`, Set có thể tồn tại mà không có TTL. Khi vòng đời tạm là yêu cầu bắt buộc, dùng transaction/script phù hợp để tạo/gắn TTL cùng một đơn vị nguyên tử hoặc chọn thiết kế có cơ chế tái áp dụng TTL đáng tin cậy.

Tương tự, mỗi lần gọi `SADD` trên một Set đang tồn tại thường **không tự thay TTL** của key. Cần quyết định chính sách: “hết hạn sau 24 giờ từ lần tạo” khác với “hết hạn sau 24 giờ kể từ lần cập nhật cuối”.

Khi `SREM` xóa member cuối cùng, Set trở nên rỗng và Redis thường loại bỏ key thay vì duy trì một Set rỗng vĩnh viễn. Vì vậy `SCARD key` trả 0 có thể biểu thị chưa từng có Set, Set đã được xóa, đã hết TTL hoặc hiện không còn member. Nếu nghiệp vụ cần phân biệt “group tồn tại nhưng chưa có member” với “group không tồn tại”, cần lưu **metadata group riêng**, không dựa hoàn toàn vào sự tồn tại của key Set.

### Không dùng Set thuần cho membership có deadline per-user nếu không có kiểm soát

Một cách thường dùng cho membership theo thời hạn là Sorted Set:

```redis
ZADD group:42:expiry 1762938000000 user-101
ZADD group:42:expiry 1762939000000 user-202
```

Ứng dụng kiểm tra một user bằng `ZSCORE` và so sánh với thời điểm hiện tại; job bảo trì dùng `ZREMRANGEBYSCORE` loại phần tử quá hạn. **Sự tồn tại của member trong Sorted Set chưa đủ chứng minh còn hiệu lực** nếu job dọn chưa chạy. Phải kết hợp xác minh expiration trong logic đọc hoặc xử lý nguyên tử khi yêu cầu nghiệp vụ bắt buộc.

## 11. Redis Set, bộ nhớ và big key

Một Set chỉ có một Redis key nhưng có thể chứa hàng triệu member. Đếm key bằng `DBSIZE` không giúp đánh giá cardinality của Set lớn; cần quan sát chính Set đó.

Các lệnh:

```redis
TYPE group:42:members
SCARD group:42:members
MEMORY USAGE group:42:members
OBJECT ENCODING group:42:members
TTL group:42:members
```

- `SCARD` cho số member tại thời điểm truy vấn, không cho dung lượng byte tổng.
- `MEMORY USAGE` ước lượng dung lượng bộ nhớ Redis tiêu thụ; với cấu trúc collection, cách lấy mẫu có thể ảnh hưởng chi phí/độ chính xác.
- `OBJECT ENCODING` cho biết biểu diễn nội bộ mà Redis đang dùng, phụ thuộc phiên bản và dữ liệu. Set nhỏ kiểu integer có thể dùng biểu diễn tối ưu khác với Set lớn chứa chuỗi.
- `TTL` giúp xem vòng đời của cả Set, nhưng Set có TTL vẫn có thể rất lớn trước khi hết hạn.

Ví dụ giả định một triệu member ID, mỗi ID trung bình 20 byte: chỉ riêng **nội dung ID thô** đã khoảng 20 MB, chưa kể overhead của Redis, mạng, protocol và bộ nhớ Java. `SMEMBERS` sẽ trả lại lượng dữ liệu lớn đó cho mọi lần gọi; nếu endpoint bị gọi nhiều lần, chi phí có thể tăng đáng kể.

### Khi nào cần chia Set?

Có thể xem xét chia theo:

- **Đối tượng quản lý:** mỗi group/event/tenant một Set.
- **Khoảng thời gian:** `event:42:attendees:2026-11` để giới hạn lịch sử theo giai đoạn, nếu truy vấn chấp nhận chia thời gian.
- **Bucket:** `group:42:members:bucket:00..31` theo hàm băm ổn định của member, khi một Set đơn đã quá lớn hoặc thành hot key.

Với bucket, phép kiểm tra membership phải xác định đúng bucket từ member ID; phép đếm tổng phải tổng hợp nhiều Set, và các phép toán giao/hợp phải tính đến việc dữ liệu đã bị chia. Số bucket, thuật toán băm và quy tắc migration phải ổn định giữa các producer/consumer.

Trong Redis Cluster, **một Set là một key thuộc một hash slot**, nên Redis không tự trải các member của Set lên nhiều node. Chia thành nhiều key có thể giúp phân tải nhưng cũng làm phức tạp cập nhật đa key, quản lý TTL và tính nhất quán.

Không nên chia Set quá sớm khi dữ liệu ít và access pattern đơn giản. Việc tăng số key cũng làm tăng overhead quản lý và số lệnh Redis cần gọi.

## 12. Trường hợp thiết kế hay gặp

### 12.1. Danh sách user yêu thích một sản phẩm

```text
product:sku-42:followers → {u101, u202, u303}
```

Yêu cầu:

- “Người này đã follow chưa?” → `SISMEMBER`.
- “Follow” → `SADD`, kết quả 0/1 giúp biết có thực sự đổi trạng thái không.
- “Unfollow” → `SREM`.
- “Bao nhiêu người follow?” → `SCARD`.

Nếu chỉ hiển thị count và trạng thái của user hiện tại, **không cần `SMEMBERS`**. Nếu danh sách follower cần sắp theo thời gian follow, Set không đủ thông tin; cần một index có score hoặc nguồn truy vấn khác.

### 12.2. Danh sách permission của role

```text
role:editor:permissions → {article:read, article:write, comment:moderate}
```

Set phù hợp vì permission thường không trùng và số lượng vừa phải. API kiểm tra quyền có thể gọi `SISMEMBER`. Tuy nhiên nếu đây là hệ thống phân quyền quan trọng, cần thiết kế quy tắc cập nhật, audit, cache invalidation và dự phòng khi Redis không khả dụng. Không coi một giá trị cache đơn lẻ là cơ chế xác thực/ủy quyền đầy đủ khi nguồn dữ liệu chuẩn nằm nơi khác.

### 12.3. Những message ID đã xử lý

```text
consumer:billing:processed:2026-11-12 → {message-1, message-2, ...}
```

Set có thể hỗ trợ phát hiện ID lặp. Nhưng nếu nghiệp vụ vừa **ghi membership** vừa **thực hiện tác động ngoài Redis** (ví dụ thanh toán, cập nhật database), việc `SADD` thành công không chứng minh tác động ngoài đã hoàn tất. Cần lưu trạng thái xử lý, idempotency key hoặc transaction/outbox ở hệ thống có khả năng bảo đảm phù hợp.

Đối với volume rất lớn và retention dài, duy trì một Set ID mãi mãi có thể gây big key và tốn memory; cân nhắc chia theo thời gian, TTL phù hợp hoặc kho lưu bền vững.

### 12.4. Thành viên phòng chat trực tuyến

```text
room:42:online → {session-a, session-b, session-c}
```

Nếu member đại diện cho user ID, một user có hai thiết bị vẫn chỉ xuất hiện một lần; nếu member đại diện cho **session ID**, mỗi session có thể độc lập. Điều này phải được quyết định trước khi chọn danh sách duy nhất: “một người online” và “một kết nối online” là hai tập hợp có định nghĩa khác nhau.

Redis Set thuần không tự biết session nào đã mất kết nối vì crash. Cần heartbeat/TTL theo session hoặc cơ chế presence phù hợp; chỉ thêm bằng `SADD` khi socket mở không đủ để giữ danh sách online chính xác.

## 13. Di chuyển dữ liệu từ List sang Set

Một hệ thống cũ lưu thành viên dưới List và có thể chứa phần tử trùng:

```redis
RPUSH legacy:group:42:members u1 u2 u1 u3
LRANGE legacy:group:42:members 0 -1
# u1, u2, u1, u3
```

Khi chuyển sang Set:

```redis
SADD group:42:members u1 u2 u1 u3
SCARD group:42:members
# 3
```

Trước khi migration cần xác định:

1. **Thứ tự cũ có ý nghĩa không?** List giữ thứ tự, Set không. Nếu thứ tự quan trọng, cân nhắc Sorted Set hoặc cấu trúc khác.
2. **Duplicate cũ biểu thị điều gì?** Nếu duplicate từng dùng làm số lần tham gia hoặc weight, chuyển thẳng sang Set sẽ làm mất thông tin đó.
3. **ID có cùng định dạng không?** Chuẩn hóa ID trước hoặc trong migration; xử lý các giá trị bẩn có chủ đích.
4. **Producer có tiếp tục ghi List cũ trong lúc di chuyển không?** Nếu có, backfill một lần có thể bỏ sót các thay đổi sau đó; cần giai đoạn dual-write/đối soát hoặc cutover có kiểm soát.
5. **Vòng đời và TTL thế nào?** Không vô tình biến List sắp hết hạn thành Set không TTL.
6. **Khi nào ngừng đọc List?** Chỉ bỏ đường cũ sau khi các consumer và dữ liệu liên quan đã chuyển sang hợp đồng mới.

Với List rất lớn, không nên `LRANGE 0 -1` rồi giữ toàn bộ trong JVM chỉ để chuyển đổi. Dùng batching theo range có giới hạn, ghi `SADD` theo batch, theo dõi tiến độ và xử lý sự thay đổi đồng thời. Nếu List bị thêm/xóa phần tử trong lúc dùng offset, các trang có thể dịch chuyển; cần phương án snapshot/cutover hoặc nguồn sự thật ổn định nếu yêu cầu chính xác tuyệt đối.

## 14. Quan sát và chẩn đoán

Khi membership API chậm hoặc sai kết quả, kiểm tra từ dữ liệu Redis đến Spring Data Redis:

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra phù hợp |
| --- | --- | --- |
| Thêm user nhưng count không tăng | User đã tồn tại trong Set | Kết quả `SADD` có thể bằng 0; xem `SCARD` |
| Cùng user xuất hiện hai lần ở UI | Ứng dụng ghép dữ liệu từ nhiều nguồn, hoặc các ID khác nhau biểu thị cùng người | Kiểm tra canonical ID và cách UI tổng hợp, không kết luận Redis Set tự lưu duplicate |
| `SISMEMBER` trả 0 trong khi producer nói đã ghi | Sai key/namespace, serializer khác, case/space khác, key hết TTL | `TYPE`, `TTL`, kiểm tra byte/encoding và key chính xác |
| `WRONGTYPE` | Một writer đã dùng key đó cho List/Hash/String | `TYPE key`, tách namespace nếu cần |
| Trang danh sách chậm dần | `SMEMBERS` tải toàn Set ngày càng lớn | Đo `SCARD`, response bytes, p95/p99 và thiết kế phân trang khác |
| `SSCAN` trả lặp member | Set thay đổi khi scan, hoặc tính chất scan | Xử lý idempotent, không dùng scan làm snapshot |
| Thao tác giao hai nhóm lỗi trong Cluster | Keys nằm khác hash slot | Xác định key slot/topology, đổi thiết kế/hash tag có kiểm soát |
| Nhóm vượt giới hạn 100 member | `SCARD` rồi `SADD` bằng hai command riêng | Dùng một script có kiểm tra và ghi nguyên tử |
| Set không tồn tại dù group có thật | Set rỗng, TTL hết hoặc chưa được tạo | Lưu metadata group riêng và phân biệt trạng thái |
| Redis memory tăng mạnh | Set chứa quá nhiều member hoặc member value lớn | `SCARD`, `MEMORY USAGE`, theo dõi tăng trưởng theo key |

Một số lệnh dùng khi điều tra:

```redis
TYPE group:42:members
SCARD group:42:members
SISMEMBER group:42:members user-101
TTL group:42:members
MEMORY USAGE group:42:members
INFO commandstats
SLOWLOG GET 10
```

`SLOWLOG` phản ánh thời gian thực thi command trong Redis, không tính đầy đủ thời gian mạng hoặc Java deserialize. Nếu một `SMEMBERS` lớn làm API chậm nhưng không vượt ngưỡng slowlog, vẫn cần đo bytes chuyển về, thời gian chờ connection, heap allocation và GC phía Java.

Trong môi trường sản xuất, tránh dùng `SMEMBERS` trên Set rất lớn chỉ để kiểm tra thử và tránh lệnh quét keyspace `KEYS *` trong đường xử lý bình thường. Công cụ đo cũng tiêu thụ tài nguyên; lên kế hoạch sampling và giới hạn tải.

## 15. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Dùng List rồi kiểm tra tồn tại trước khi push | Race condition giữa nhiều writer, tạo duplicate | Dùng `SADD` cho Set |
| Tưởng Redis Set tự gộp `user-42` và `USER-42` | Một người xuất hiện dưới nhiều member | Chuẩn hóa ID theo hợp đồng chung |
| Gọi `SMEMBERS` để kiểm tra một user | Tải toàn bộ tập hợp, tăng latency và memory | `SISMEMBER` |
| Gọi `SMEMBERS` để đếm | Tải về tất cả rồi `size()` | `SCARD` |
| Dùng Set để phân trang theo thời gian | Không có thứ tự ổn định | Sorted Set/index có thứ tự |
| Dùng `SSCAN COUNT 100` như giới hạn chắc chắn | Một lượt vẫn có thể trả nhiều hơn hoặc trả rỗng | Cursor, giới hạn xử lý và kiểm soát memory |
| Cho rằng `SADD` trả tổng số thành viên | Đếm sai | Kết quả là số member **mới** được thêm |
| Cho rằng `SCARD` rồi `SADD` giữ được max size | Nhiều writer có thể vượt giới hạn | Script/transaction phù hợp |
| Cho rằng TTL áp dụng riêng từng user | Toàn Set hết hạn cùng lúc | Chọn Sorted Set/key riêng cho hạn dùng từng member |
| Lưu Set và reverse index mà không đối soát | Quan hệ hai chiều bị lệch sau lỗi từng phần | Chọn nguồn sự thật, cơ chế cập nhật/khôi phục |
| Coi Redis Set là hàng đợi FIFO | `SPOP` chọn/xóa ngẫu nhiên, không theo FIFO | List hoặc Stream theo yêu cầu hàng đợi |
| Coi Set trong Redis Cluster là phân tán member qua nodes | Một Set là một key trong một slot | Chia key có chủ đích nếu cần phân tải |

## 16. Bài tập tự luyện

**Câu 1.** Lần lượt thực hiện:

```redis
SADD members:a u1 u2
SADD members:a u2 u3
SCARD members:a
```

Hai lệnh `SADD` trả gì? `SCARD` bằng bao nhiêu?

*Gợi ý:* lệnh đầu thêm 2, lệnh sau chỉ thêm mới `u3` nên trả 1; cardinality cuối là 3.

**Câu 2.** Hai service cùng muốn thêm `u9` vào `group:42:members`. Có cần lock Redis trước khi gửi `SADD` để tránh member bị lưu hai lần không?

*Gợi ý:* cùng một member trong cùng Set đã được Redis đảm bảo tính duy nhất bằng tính nguyên tử của `SADD`.

**Câu 3.** Group có một triệu user. API chỉ cần trả “user hiện tại đã tham gia chưa?” và “tổng số thành viên”. Chọn hai Redis command nào?

*Gợi ý:* `SISMEMBER` và `SCARD`, không cần `SMEMBERS`.

**Câu 4.** Một API cần danh sách 20 người tham gia **gần nhất**. Vì sao không dùng `SMEMBERS` hoặc `SSCAN` rồi lấy 20 phần tử đầu?

*Gợi ý:* Set không có thứ tự theo thời gian; cân nhắc Sorted Set với score timestamp và cách xử lý score hòa.

**Câu 5.** Nhóm giới hạn 100 người, hiện có 99 người. Hai request thêm hai user khác nhau cùng lúc. Tại sao cách `SCARD` rồi `SADD` có thể cho ra 101 người?

*Gợi ý:* hai command riêng không tạo một thao tác kiểm tra + thêm nguyên tử; script `SISMEMBER + SCARD + SADD` giải quyết phạm vi một key.

**Câu 6.** Một user có hai session đang hoạt động. Nếu Set online lưu user ID thì `SCARD` là 1 hay 2? Nếu lưu session ID thì sao?

*Gợi ý:* định nghĩa member quyết định ý nghĩa của cardinality.

**Câu 7.** Hệ thống cần membership của mỗi user tự hết hạn sau 30 phút kể từ lần tham gia, trong khi nhóm vẫn tồn tại. Vì sao `EXPIRE group:42:members 1800` chưa đáp ứng đúng?

*Gợi ý:* TTL Redis Set thông thường thuộc toàn key, không phải riêng từng member.

**Câu 8.** Vì sao tạo `group:42:members` và `user:u1:groups` khiến việc join/leave phức tạp hơn? Nếu Redis Cluster đặt hai key ở hai slot khác nhau, tác động là gì?

*Gợi ý:* hai index cần nhất quán, còn multi-key transaction/script trong Cluster có yêu cầu về slot.

## 17. Ghi nhớ

**Redis Set là cấu trúc phù hợp để lưu danh sách thành viên duy nhất khi nghiệp vụ không cần thứ tự.** `SADD` đảm bảo không lưu trùng cùng một member trong một Set; `SISMEMBER` và `SCARD` giúp kiểm tra/đếm hiệu quả mà không tải toàn bộ dữ liệu. Với Spring Data Redis, dùng `StringRedisTemplate.opsForSet()` và thống nhất định danh/serializer giữa các producer để ý nghĩa “duy nhất” được giữ đúng.

Thiết kế tốt không dừng ở việc chọn Set. Cần xác định phạm vi membership, key naming, giới hạn cardinality, nhu cầu truy vấn ngược, TTL và nguồn sự thật. Tránh `SMEMBERS` trên Set lớn, dùng `SSCAN` cho xử lý theo đợt và chọn Sorted Set khi cần thứ tự. Nếu có ràng buộc **tối đa N thành viên**, kiểm tra rồi thêm bằng hai command chưa đủ trong môi trường nhiều writer; phải đặt kiểm tra và thay đổi vào một thao tác nguyên tử phù hợp. Những quyết định này giúp danh sách thành viên duy nhất duy trì đúng ngữ nghĩa khi ứng dụng Spring Boot mở rộng theo dữ liệu và số instance.
