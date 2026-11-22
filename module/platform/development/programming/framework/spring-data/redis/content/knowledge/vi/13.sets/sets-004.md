# Đếm thành viên và duyệt Set bằng SSCAN

## 1. Bài toán: một Redis Set có bao nhiêu thành viên và duyệt chúng như thế nào?

Redis **Set** là tập hợp các phần tử duy nhất, không có thứ tự cố định. Trong ứng dụng Spring Data Redis, Set thường được dùng để quản lý danh sách người tham gia một nhóm, các định danh đã xử lý, quyền theo nhóm hoặc các thẻ gắn cho một thực thể. Redis tự loại trùng theo giá trị byte của thành viên, nên thêm cùng một phần tử hai lần không làm số lượng thành viên tăng lên.

Giả sử hệ thống lưu các thành viên của một nhóm học Java:

~~~text
Redis key: learning:group:java:members
Redis data type: set

  "user:101"
  "user:205"
  "user:309"
  "user:417"
  ...
~~~

Hai câu hỏi thường xuất hiện:

1. **Nhóm có bao nhiêu thành viên?** Sử dụng Redis command **SCARD**, tương ứng **SetOperations.size(key)** trong Spring Data Redis.
2. **Làm sao xử lý lần lượt tất cả thành viên mà không lấy cả tập rất lớn về RAM trong một lần?** Sử dụng **SSCAN**, tương ứng **SetOperations.scan(key, ScanOptions)**.

Hai thao tác này giải quyết hai mục tiêu khác nhau. **SCARD** trả về số phần tử của một Set tại thời điểm Redis thực hiện lệnh. **SSCAN** duyệt các phần tử theo từng lượt với con trỏ (*cursor*), giúp chia công việc qua nhiều lần gọi Redis. SSCAN không phải phép đếm nhanh, cũng không tạo ra một ảnh chụp dữ liệu bất biến.

## 2. Nhắc lại cấu trúc và tính duy nhất của Redis Set

Một Set có tên **learning:group:java:members** có thể được tạo qua Redis CLI:

~~~redis
SADD learning:group:java:members user:101 user:205 user:309
SCARD learning:group:java:members
~~~

Lần **SADD** đầu có thể trả về **3** nếu cả ba phần tử trước đó chưa tồn tại. **SCARD** trả về **3**.

Tiếp tục:

~~~redis
SADD learning:group:java:members user:205 user:417
SCARD learning:group:java:members
~~~

Vì **user:205** đã có, Redis chỉ thêm **user:417**. Số phần tử lúc này là **4**.

| Command | Mục đích | Kết quả tiêu biểu |
|---|---|---|
| **SADD key member ...** | Thêm một hoặc nhiều phần tử | Số phần tử mới được thêm |
| **SREM key member ...** | Loại bỏ phần tử chỉ định | Số phần tử đã bị loại bỏ |
| **SCARD key** | Đếm số phần tử duy nhất | Số nguyên |
| **SISMEMBER key member** | Kiểm tra một phần tử có trong Set | 1 hoặc 0 |
| **SMEMBERS key** | Lấy toàn bộ phần tử trong một lần gọi | Danh sách không có thứ tự bảo đảm |
| **SSCAN key cursor ...** | Duyệt thành viên qua các lượt | Cursor tiếp theo và một lô phần tử |
| **SPOP key** | Lấy đồng thời xóa phần tử được chọn | Dữ liệu Set bị thay đổi |
| **SRANDMEMBER key** | Lấy mẫu phần tử mà không xóa | Không phải duyệt đầy đủ |

Redis Set không bảo đảm thứ tự như List và không gắn score như Sorted Set. Dù một lần chạy redis-cli có thể hiển thị các thành viên theo một thứ tự nhìn có vẻ ổn định, ứng dụng không nên dựa vào thứ tự ấy khi xử lý logic nghiệp vụ hoặc phân trang.

## 3. Đếm chính xác số thành viên bằng SCARD

### 3.1. Cú pháp và kết quả

~~~redis
SCARD key
~~~

Ví dụ:

~~~redis
DEL demo:members
SADD demo:members alice bob carol
SCARD demo:members
~~~

Kết quả:

~~~text
(integer) 3
~~~

Sau khi xóa một thành viên:

~~~redis
SREM demo:members bob
SCARD demo:members
~~~

Kết quả:

~~~text
(integer) 2
~~~

**SCARD** có độ phức tạp **O(1)** theo mô tả của Redis: lệnh tra cứu số phần tử đang được Redis quản lý, không phải gửi toàn bộ thành viên về ứng dụng rồi đếm.

### 3.2. Key không tồn tại

~~~redis
SCARD group:does-not-exist
~~~

Redis trả về **0**. Về góc độ SCARD, Set không tồn tại và Set có số lượng phần tử bằng 0 đều có kết quả đếm bằng 0. Trên Redis, một Set rỗng thông thường không được giữ lại như một cấu trúc dữ liệu độc lập: khi xóa phần tử cuối cùng, key Set có thể biến mất.

Nếu nghiệp vụ phải phân biệt *“nhóm chưa từng được tạo”* và *“nhóm đang có 0 thành viên”*, chỉ dùng một key Set và SCARD là chưa đủ. Có thể cần thêm key metadata về sự tồn tại của nhóm, và phải xác định cách cập nhật metadata cho nhất quán.

### 3.3. Key có kiểu dữ liệu sai

~~~redis
SET demo:not-a-set hello
SCARD demo:not-a-set
~~~

Redis sẽ trả lỗi **WRONGTYPE**, vì lệnh SCARD chỉ áp dụng cho key chứa Redis **Set**. Đây là lỗi kiểu dữ liệu, khác với kết quả **0** khi key không tồn tại.

Đặc biệt khi nhiều module dùng cùng Redis, nên phân biệt namespace rõ ràng:

~~~text
group:42:members     -> Set
group:42:metadata    -> Hash
group:42:memberCount -> String (chỉ khi cần dữ liệu đếm riêng)
~~~

Không nên để một service dùng **SET** để ghi String vào **group:42:members** trong khi service khác dùng **SADD** trên chính key đó.

### 3.4. SCARD phản ánh thời điểm nào?

Redis xử lý SCARD như một lệnh riêng. Nếu request A gọi SCARD khi Set có 100 thành viên và request B thêm một thành viên ngay sau đó, A có thể nhận 100 trong khi một lệnh SCARD tiếp theo trả 101.

Vì vậy, SCARD đưa ra **con số chính xác tại thời điểm lệnh thực thi**, không phải giá trị bất biến trong suốt quá trình một HTTP request kéo dài. Không nên suy luận rằng dữ liệu sẽ giữ nguyên sau lần đếm đó.

## 4. SCARD trong Spring Data Redis: SetOperations.size()

Spring Data Redis cung cấp **SetOperations<K, V>** qua **RedisTemplate.opsForSet()**:

~~~java
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

// stringRedisTemplate là bean được Spring inject.
SetOperations<String, String> sets =
    stringRedisTemplate.opsForSet();

Long count = sets.size("learning:group:java:members");
~~~

**size(key)** ánh xạ tới Redis **SCARD**. Với template đồng bộ và lời gọi bình thường, kết quả là **Long** tương ứng số thành viên.

Ví dụ service:

~~~java
package com.example.learning.membership;

import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMemberService {
    private final SetOperations<String, String> sets;

    public GroupMemberService(StringRedisTemplate redis) {
        this.sets = redis.opsForSet();
    }

    private String membersKey(String groupId) {
        if (groupId == null || groupId.isBlank()) {
            throw new IllegalArgumentException("groupId is required");
        }
        return "learning:group:" + groupId + ":members";
    }

    public long countMembers(String groupId) {
        Long count = sets.size(membersKey(groupId));
        if (count == null) {
            throw new IllegalStateException(
                "Redis did not return a cardinality result"
            );
        }
        return count;
    }

    public boolean addMember(String groupId, String userId) {
        Long added = sets.add(membersKey(groupId), "user:" + userId);
        return Long.valueOf(1L).equals(added);
    }

    public boolean removeMember(String groupId, String userId) {
        Long removed = sets.remove(membersKey(groupId), "user:" + userId);
        return Long.valueOf(1L).equals(removed);
    }
}
~~~

Ở ví dụ này:

- **countMembers()** dùng SCARD để lấy số phần tử thực.
- **addMember()** trả **true** khi thành viên mới thực sự được thêm, **false** nếu đã có thành viên đó.
- **removeMember()** trả **true** khi một thành viên có tồn tại đã bị xóa.
- Cả thao tác SADD/SREM lẫn SCARD được Redis xử lý theo từng command; không cần đọc toàn bộ Set.

Trong chế độ pipeline hoặc Redis transaction đang xếp hàng lệnh, Spring Data Redis có thể tạm trả **null** cho một số operation cho đến khi kết quả được nhận sau đó. Ví dụ trên dành cho lời gọi đồng bộ bình thường, không đặt bên trong **MULTI** hoặc pipeline.

### Vì sao không dùng members().size()?

~~~java
// Không phù hợp khi chỉ cần số lượng của Set lớn:
long count = sets.members("learning:group:java:members").size();
~~~

**members(key)** tương ứng **SMEMBERS**, tải toàn bộ dữ liệu về Java. Nếu Set có hàng trăm nghìn hoặc hàng triệu phần tử, câu lệnh này tiêu tốn mạng, RAM và thời gian xử lý không cần thiết. **size(key)** dùng SCARD và chỉ trả một số nguyên.

Một nguyên tắc hữu ích: **cần số lượng thì gọi SCARD; cần biết một phần tử có tồn tại thì gọi SISMEMBER; cần duyệt nhiều phần tử thì chọn SSCAN**.

## 5. SSCAN: duyệt Set theo cursor

### 5.1. Cú pháp Redis

~~~redis
SSCAN key cursor [MATCH pattern] [COUNT count]
~~~

Trong đó:

- **key**: tên Redis key chứa Set.
- **cursor**: con trỏ của lượt quét. Bắt đầu bằng **0**.
- **MATCH pattern**: lọc member trả về theo mẫu kiểu *glob* của Redis.
- **COUNT count**: gợi ý lượng công việc Redis thực hiện cho một lượt, không phải hạn mức chính xác của số member trả về.

Mỗi lần gọi SSCAN trả về hai phần:

1. **Next cursor**: giá trị phải truyền vào lượt tiếp theo.
2. **Batch members**: danh sách thành viên tìm thấy ở lượt hiện tại.

Ví dụ:

~~~redis
SADD demo:scan user:1 user:2 user:3 user:4 user:5
SSCAN demo:scan 0 COUNT 2
~~~

Một kết quả minh họa có thể trông như sau:

~~~text
1) "5"
2) 1) "user:2"
   2) "user:4"
~~~

Sau đó tiếp tục với cursor Redis trả về:

~~~redis
SSCAN demo:scan 5 COUNT 2
~~~

Các cursor và phần tử trong ví dụ chỉ minh họa cấu trúc phản hồi. **Không có bảo đảm kết quả thực tế dùng cursor 5, trả đúng hai phần tử hoặc có thứ tự như trên.** Với Set nhỏ dùng representation tối ưu bộ nhớ, Redis thậm chí có thể trả tất cả thành viên ngay lượt đầu và cursor tiếp theo bằng **0**, bất kể COUNT có giá trị nhỏ.

### 5.2. Vòng lặp cursor chuẩn

~~~text
cursor = "0"

do:
    response = SSCAN setKey cursor MATCH pattern COUNT hint
    cursor   = response.nextCursor
    xử lý tất cả response.members
while cursor != "0"
~~~

Quy tắc quan trọng:

- **0 đầu tiên** có nghĩa bắt đầu quét.
- **0 được trả về** có nghĩa vòng quét đó đã kết thúc.
- Cần **xử lý batch vừa nhận** trước khi kết luận hoàn tất, ngay cả khi next cursor là 0.
- **Batch rỗng với next cursor khác 0 không đồng nghĩa đã hết dữ liệu.** Phải tiếp tục gọi SSCAN.
- Cursor không phải offset trang, số thứ tự member hay vị trí có thể tăng bằng cách cộng 1. Chỉ sử dụng cursor **0 ban đầu** hoặc cursor Redis thực sự trả về từ lượt trước.

Không tự tạo cursor ngẫu nhiên hoặc chỉnh sửa cursor để nhảy đến “trang 3”. Theo cơ chế SCAN, con trỏ giữ trạng thái duyệt tối thiểu ở phía client; Redis không cung cấp một tập kết quả có thứ tự ổn định như truy vấn SQL có **ORDER BY** và **LIMIT/OFFSET**.

## 6. SSCAN khác SMEMBERS và SCAN thế nào?

| Đặc điểm | SCARD | SMEMBERS | SSCAN | SCAN |
|---|---|---|---|---|
| Đối tượng | Một Set | Một Set | Một Set | Các **key** trong database |
| Kết quả | Số lượng | Toàn bộ member | Các lô member + cursor | Các lô tên key + cursor |
| Dùng cho Set rất lớn | Rất phù hợp khi chỉ cần đếm | Có nguy cơ response lớn | Phù hợp duyệt theo lượt | Không phải công cụ duyệt member của một Set |
| Có thứ tự ổn định | Không áp dụng | Không | Không | Không |
| Lọc bằng MATCH | Không | Không | Lọc **member** | Lọc **tên key** |
| Có thể trả trùng trong một full scan | Không áp dụng | Một Set mỗi member là duy nhất | Có thể, do đặc tính SCAN | Có thể |

Phân biệt hai lệnh dưới đây:

~~~redis
SCAN 0 MATCH learning:group:* COUNT 100
~~~

Lệnh này tìm **tên Redis key** khớp **learning:group:\*** trong database.

~~~redis
SSCAN learning:group:java:members 0 MATCH user:* COUNT 100
~~~

Lệnh này duyệt **các member bên trong một Set cụ thể**, rồi chỉ trả những member khớp **user:\***.

**SSCAN** không dùng tùy chọn **TYPE** như SCAN; type của key cần quét đã là Set. Nếu key trỏ tới Redis String hoặc Hash, lệnh SSCAN không thể duyệt nó và sẽ gặp lỗi sai data type.

## 7. MATCH: lọc member theo mẫu glob

**MATCH** được Redis dùng để lọc những member được trả về trong khi quét. Mẫu khớp theo quy tắc glob, không phải biểu thức chính quy (regular expression) của Java.

Một vài mẫu:

| MATCH | Ý nghĩa |
|---|---|
| **user:\*** | Member bắt đầu bằng **user:** |
| **\*:premium** | Member có hậu tố **:premium** |
| **user:??** | Member bắt đầu **user:** và có hai ký tự đơn vị khớp glob theo cách Redis so sánh bytes |
| **user:[12]\*** | Member bắt đầu bằng **user:1** hoặc **user:2** |
| **\*** | Mọi member |

Ví dụ:

~~~redis
SADD group:demo user:1 user:2 bot:1 guest:1 user:3
SSCAN group:demo 0 MATCH user:* COUNT 10
~~~

Lệnh trả về các member được Redis tìm thấy trong lượt quét và khớp mẫu **user:\***; muốn duyệt đầy đủ, tiếp tục theo cursor cho đến khi trả về 0.

### MATCH không giới hạn lượng dữ liệu Redis phải kiểm tra

Redis có thể quét một phần cấu trúc bên trong rồi mới lọc theo mẫu. Nếu tỷ lệ member khớp mẫu thấp, nhiều lượt SSCAN có thể trả **batch rỗng** dù trong Set vẫn có member khớp mẫu ở các lượt sau.

Ví dụ Set có một triệu member nhưng chỉ một trăm member bắt đầu bằng **vip:**. Dùng **MATCH vip:\*** không biến Redis Set thành một index truy vấn tiền tố; Redis vẫn phải thực hiện quá trình duyệt để tìm các mục phù hợp.

Nếu ứng dụng thường xuyên hỏi “có bao nhiêu thành viên VIP?” hoặc “liệt kê riêng thành viên VIP”, cân nhắc duy trì **Set riêng cho VIP** hoặc một cấu trúc index được cập nhật cùng lúc với dữ liệu nguồn. Chỉ thêm MATCH sẽ không cung cấp phép đếm theo prefix trong thời gian O(1).

## 8. COUNT là gợi ý xử lý, không phải kích thước trang chính xác

Ví dụ:

~~~redis
SSCAN group:demo 0 COUNT 100
~~~

**COUNT 100** thể hiện mức công việc mong muốn cho mỗi lần quét. Redis có thể trả ít hơn 100, nhiều hơn 100 hoặc **0 phần tử**. Với Set đủ nhỏ và được lưu theo biểu diễn tối ưu, Redis có thể trả toàn bộ thành viên trong một lần gọi.

Các hệ quả quan trọng:

1. **COUNT không tương đương LIMIT 100.**
2. **COUNT 100 không bảo đảm 100 member mỗi batch.**
3. **COUNT nhỏ không bảo đảm response luôn bị giới hạn cứng về bộ nhớ hoặc độ trễ.**
4. **COUNT lớn thường giảm số round trip**, nhưng một lượt có thể phải xử lý nhiều dữ liệu hơn và tăng độ trễ đột biến.
5. **COUNT có thể được điều chỉnh giữa các lượt**, miễn là vẫn dùng cursor Redis trả về theo đúng vòng quét.

Khi chọn COUNT, cần quan sát độ trễ mạng, kích thước member, thời gian xử lý mỗi batch và tài nguyên Redis. Không có một giá trị COUNT tối ưu cho mọi ứng dụng.

Nếu ứng dụng cần đúng tối đa 50 kết quả trả về qua HTTP, **COUNT 50** không tự tạo ra một trang 50 kết quả an toàn và ổn định. Cần thiết kế pagination và thứ tự riêng hoặc giới hạn số phần tử ứng dụng phát ra, đồng thời giải thích giới hạn của cursor traversal.

## 9. Bảo đảm và giới hạn của một full SSCAN

SSCAN được thiết kế để duyệt tăng dần một tập phần tử có thể thay đổi trong thời gian chạy. Nó **không giữ một snapshot cố định** cho toàn bộ vòng duyệt.

Theo semantics của họ lệnh SCAN:

- Khi một phần tử **liên tục tồn tại từ lúc bắt đầu đến lúc kết thúc full iteration**, Redis bảo đảm phần tử ấy xuất hiện ít nhất một lần trong quá trình quét đầy đủ.
- Một phần tử **có thể được trả lại nhiều lần**. Ứng dụng phải chấp nhận xử lý trùng hoặc thiết kế thao tác idempotent.
- Với phần tử **được thêm hoặc bị xóa trong lúc quét**, không có bảo đảm rằng nó sẽ xuất hiện hay không xuất hiện.
- Nếu tập dữ liệu **tăng không giới hạn** trong khi đang quét, một full iteration không được bảo đảm kết thúc trong mọi điều kiện.
- Một lượt **SSCAN** riêng là một command Redis, nhưng **nhiều lượt SSCAN** không hợp thành một giao dịch nguyên tử.

Ví dụ hai request đồng thời:

~~~text
Worker A                           Worker B
--------                           --------
SSCAN members 0
  -> cursor 27
                                   SADD members user:999
SSCAN members 27
  -> cursor 9
                                   SREM members user:101
SSCAN members 9
  -> cursor 0
~~~

Không thể khẳng định từ vòng scan này rằng **user:999** chắc chắn đã được đọc hoặc **user:101** chắc chắn được đọc, vì chúng thay đổi trong lúc duyệt.

### 9.1. Vì sao Set vốn duy nhất nhưng scan vẫn có thể lặp?

Tính duy nhất của Set áp dụng cho **trạng thái dữ liệu tại Redis**. Còn SSCAN là một chuỗi lần đi qua cấu trúc nội bộ bằng cursor. Nếu cấu trúc bảng băm thay đổi kích thước, lộ trình duyệt có thể gặp lại một member đã thấy. Hai khái niệm độc lập:

- **Set không chứa hai bản sao của cùng một member tại cùng thời điểm.**
- **Chuỗi kết quả SSCAN có thể phát cùng một member nhiều lần.**

Nếu mỗi phần tử được dùng để gửi email, tính tiền hoặc tạo tác dụng phụ, không được tự động giả định “duyệt Set nghĩa là xử lý đúng một lần”. Cần cơ chế idempotency hoặc trạng thái xử lý riêng.

### 9.2. Dùng SSCAN để đếm theo mẫu có chính xác không?

Giả sử:

~~~redis
SSCAN members 0 MATCH vip:* COUNT 100
~~~

Nếu cộng **độ dài tất cả batch**, có thể **đếm trùng** cùng một member vì SCAN không hứa duy nhất trong các lượt. Nếu dùng cấu trúc **Set** trong Java để loại trùng, lượng bộ nhớ lại tăng theo số member đã nhìn thấy. Nếu dữ liệu thay đổi trong lúc duyệt, kết quả vẫn không biểu diễn một snapshot đồng nhất.

Để biết **tổng số thành viên**, dùng SCARD. Để biết **số thành viên VIP chính xác trong thời gian thực**, cân nhắc cấu trúc dữ liệu riêng hoặc một cơ chế cập nhật/đếm có tính nhất quán phù hợp; SSCAN + MATCH không thay thế một phép đếm được bảo đảm.

## 10. Duyệt Set trong Spring Data Redis với SetOperations.scan()

### 10.1. API cốt lõi

~~~java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

SetOperations<String, String> sets = stringRedisTemplate.opsForSet();

ScanOptions options = ScanOptions.scanOptions()
    .match("user:*")
    .count(200)
    .build();

try (Cursor<String> cursor =
         sets.scan("learning:group:java:members", options)) {

    while (cursor.hasNext()) {
        String member = cursor.next();
        System.out.println(member);
    }
}
~~~

**SetOperations.scan(key, options)** trả về **Cursor<V>**. Spring Data Redis quản lý việc gửi nhiều command **SSCAN** khi cần để consumer duyệt dần. Ứng dụng chỉ cần lặp qua cursor; không phải tự lấy next cursor dạng chuỗi ở cấp API này.

**Bắt buộc đóng Cursor sau khi dùng** bằng **try-with-resources** hoặc cách đóng tương đương. Cursor có thể giữ connection/tài nguyên liên quan trong suốt vòng duyệt; quên đóng gây rò rỉ tài nguyên, đặc biệt khi vòng quét bị dừng sớm hoặc exception xảy ra.

### 10.2. Tham số ScanOptions

~~~java
ScanOptions options = ScanOptions.scanOptions()
    .match("user:*")
    .count(200)
    .build();
~~~

- **match("user:*")** giới hạn những member được phát ra theo mẫu glob.
- **count(200)** đưa ra gợi ý kích thước công việc Redis cho mỗi lần SSCAN.
- Nếu không cần lọc hay gợi ý COUNT, có thể dùng **ScanOptions.NONE**.

ScanOptions áp dụng cho nhiều command thuộc họ SCAN, nhưng vì ta gọi **opsForSet().scan(key, options)** nên Redis sẽ thực thi **SSCAN**, không phải SCAN duyệt các key của database.

### 10.3. Chỉ xử lý từng phần tử thay vì gom vào List

~~~java
public void processMembers(
        String groupId,
        java.util.function.Consumer<String> consumer) {

    String key = "learning:group:" + groupId + ":members";
    ScanOptions options = ScanOptions.scanOptions()
        .count(256)
        .build();

    try (Cursor<String> cursor = sets.scan(key, options)) {
        while (cursor.hasNext()) {
            consumer.accept(cursor.next());
        }
    }
}
~~~

Trong ví dụ, biến **sets** là **SetOperations<String, String>** đã được inject vào class. Mỗi member được chuyển đến callback, không tích lũy toàn bộ Set vào một List.

Tuy nhiên callback vẫn phải xử lý lỗi và giới hạn tác vụ phù hợp. Nếu callback thực hiện HTTP request chậm hoặc gọi database lâu, vòng scan sẽ kéo dài và có thể giữ tài nguyên lâu hơn mong muốn. Với job khối lượng lớn, thường nên tách **bước lấy batch** và **bước xử lý công việc**, hoặc dùng một hàng đợi/stream có cơ chế xác nhận nếu yêu cầu phân phối công việc.

## 11. Ví dụ service đầy đủ: đếm và duyệt thành viên của một nhóm

Ví dụ dưới đây dùng Redis Set để quản lý ID người dùng. Service có ba nhóm chức năng: thêm/xóa thành viên, đếm bằng SCARD và duyệt bằng SSCAN.

~~~java
package com.example.learning.membership;

import java.util.Objects;
import java.util.function.Consumer;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisGroupMembership {
    private final SetOperations<String, String> sets;

    public RedisGroupMembership(StringRedisTemplate redis) {
        this.sets = redis.opsForSet();
    }

    private String key(String groupId) {
        if (groupId == null || groupId.isBlank()) {
            throw new IllegalArgumentException("groupId is required");
        }
        return "learning:group:" + groupId + ":members";
    }

    public boolean add(String groupId, String memberId) {
        if (memberId == null || memberId.isBlank()) {
            throw new IllegalArgumentException("memberId is required");
        }
        Long added = sets.add(key(groupId), memberId);
        return Long.valueOf(1L).equals(added);
    }

    public boolean remove(String groupId, String memberId) {
        Long removed = sets.remove(key(groupId), memberId);
        return Long.valueOf(1L).equals(removed);
    }

    public long count(String groupId) {
        return Objects.requireNonNull(
            sets.size(key(groupId)),
            "SCARD did not return a value"
        );
    }

    public void forEachMember(
            String groupId,
            Consumer<String> action) {

        ScanOptions options = ScanOptions.scanOptions()
            .count(200)
            .build();

        try (Cursor<String> cursor = sets.scan(key(groupId), options)) {
            while (cursor.hasNext()) {
                action.accept(cursor.next());
            }
        }
    }

    public void forEachMatchingMember(
            String groupId,
            String globPattern,
            Consumer<String> action) {

        ScanOptions options = ScanOptions.scanOptions()
            .match(globPattern)
            .count(200)
            .build();

        try (Cursor<String> cursor = sets.scan(key(groupId), options)) {
            while (cursor.hasNext()) {
                action.accept(cursor.next());
            }
        }
    }
}
~~~

Ví dụ sử dụng:

~~~java
membership.add("java", "user:101");
membership.add("java", "user:205");
membership.add("java", "user:101"); // Không làm tăng số member.

long total = membership.count("java"); // 2, nếu không có update khác.

membership.forEachMatchingMember(
    "java",
    "user:*",
    userId -> System.out.println("Found " + userId)
);
~~~

Biến **membership** đại diện bean **RedisGroupMembership** do Spring quản lý. Với workload thực tế, callback chỉ nên thực hiện thao tác **idempotent** hoặc có cơ chế chống xử lý trùng, vì full scan có thể trả lại cùng một phần tử nhiều lần.

### Vì sao service không trả List toàn bộ Set?

Một method **List<String> getAllMembers()** có thể tiện với nhóm vài chục phần tử, nhưng nếu Set tăng tới hàng triệu member, việc gom toàn bộ List khiến ứng dụng phải giữ toàn bộ dữ liệu trong RAM. Giao diện duyệt theo **Consumer**, **Iterator** hoặc stream/publisher phù hợp hơn với công việc batch.

Nếu HTTP API chỉ cần con số tổng, expose method **count()** là đủ; không cần mở cursor. Nếu UI cần phân trang có thứ tự, không nên hứa rằng SSCAN tạo ra trang dữ liệu ổn định: cần thiết kế khóa sắp xếp/index và ngữ nghĩa paging riêng.

## 12. Duyệt reactive với ReactiveSetOperations.scan()

Trong ứng dụng Spring WebFlux sử dụng Reactor, Spring Data Redis cũng cung cấp API reactive:

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.ScanOptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveMemberReader {
    private final ReactiveStringRedisTemplate redis;

    public ReactiveMemberReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> count(String groupId) {
        return redis.opsForSet().size(
            "learning:group:" + groupId + ":members"
        );
    }

    public Flux<String> scan(String groupId) {
        ScanOptions options = ScanOptions.scanOptions()
            .match("user:*")
            .count(200)
            .build();

        return redis.opsForSet().scan(
            "learning:group:" + groupId + ":members",
            options
        );
    }
}
~~~

Ở đây:

- **size(key)** trả **Mono<Long>** vì kết quả đếm là một giá trị bất đồng bộ.
- **scan(key, options)** trả **Flux<String>**; API reactive tự phát các SSCAN command theo nhu cầu của subscriber.
- Không gọi **block()** trong đường xử lý request WebFlux chỉ để lấy một Long hoặc List.
- Không gọi **subscribe()** thủ công trong controller nếu có thể trả **Mono/Flux** cho framework quản lý vòng đời.

Ví dụ service xử lý từng member theo cách giới hạn concurrency:

~~~java
public Flux<ProcessResult> processReactive(
        String groupId,
        java.util.function.Function<String, Mono<ProcessResult>> processor) {

    return scan(groupId)
        .flatMap(member -> processor.apply(member), 8);
}
~~~

**ProcessResult** là DTO kết quả của nghiệp vụ minh họa. Tham số **8** giới hạn số inner publisher được **flatMap** xử lý đồng thời; đây không phải đảm bảo mỗi SSCAN command chỉ tải tám member. Hãy chọn giới hạn concurrency dựa trên chi phí xử lý, backpressure và khả năng chịu tải của hệ thống downstream.

Nếu yêu cầu kết quả đúng một lần cho mỗi member, tự động gọi **distinct()** trên Flux có thể giữ tập các phần tử đã thấy trong bộ nhớ và làm mất ưu điểm streaming khi Set quá lớn. Cần thiết kế idempotency ở tầng xử lý, thay vì mặc nhiên gom toàn bộ ID vào bộ nhớ.

### Reactive và imperative khác nhau ở vòng đời tài nguyên

Với API imperative, **Cursor** phải được đóng khi kết thúc, thường bằng **try-with-resources**. Với API reactive, subscriber và operator Reactor điều khiển vòng đời subscription; vẫn cần tránh tạo subscription rồi bỏ mặc, chạy đồng thời không giới hạn hoặc giữ Flux không được tiêu thụ.

**Flux** giúp quản lý backpressure ở ứng dụng, nhưng SSCAN vẫn là chuỗi Redis command với số member mỗi batch không cố định. Không hiểu **COUNT** hay backpressure như cam kết tuyệt đối về số phần tử trả về trong một lần quét.

## 13. Đếm nhanh không đồng nghĩa duyệt nhanh

Giả sử Set có **2 triệu thành viên**:

~~~text
learning:group:large:members
  user:1
  user:2
  ...
  user:2000000
~~~

**SCARD** có thể trả số **2.000.000** mà không tải 2 triệu ID về Java. Ngược lại, **SSCAN** vẫn phải thực hiện một **full iteration O(N)** nếu muốn đi qua toàn bộ thành viên. Incremental iteration chỉ chia tổng công việc thành nhiều lượt nhỏ hơn; nó không làm biến mất chi phí O(N) của cả quá trình.

| Mục tiêu | Cách phù hợp | Chi phí/giới hạn |
|---|---|---|
| Hiện tổng số người trong nhóm | SCARD / size() | O(1) mỗi lần đếm |
| Kiểm tra user:101 có là thành viên? | SISMEMBER / isMember() | Truy vấn trực tiếp, không cần duyệt |
| Xuất danh sách thành viên lớn | SSCAN / scan() | Nhiều lượt, tổng chi phí theo N |
| Lọc member có prefix vip: | SSCAN MATCH | Vẫn phải duyệt; MATCH không phải index |
| Lấy toàn bộ thành viên của nhóm rất nhỏ | SMEMBERS / members() | Một response chứa tất cả member |
| Phân trang ổn định theo ngày gia nhập | Cấu trúc dữ liệu/index riêng | Set không mang thứ tự ngày gia nhập |

Đừng dùng SSCAN để giải quyết bài toán mà đã có command trực tiếp. Ví dụ, chỉ để biết **user:101** đã tham gia nhóm chưa:

~~~java
Boolean present = sets.isMember(
    "learning:group:java:members",
    "user:101"
);
~~~

Lệnh này phù hợp hơn việc SSCAN toàn Set rồi tìm chuỗi **user:101** trong Java.

## 14. Xử lý thành viên trùng và thay đổi trong lúc quét

### 14.1. Tác vụ nên idempotent

Ví dụ worker dùng SSCAN để đồng bộ member của Redis Set sang một hệ thống tìm kiếm. Nếu một member xuất hiện hai lần trong scan, lệnh **upsert theo user ID** có thể được thiết kế an toàn khi gọi lại. Ngược lại, thao tác **tăng bộ đếm** hoặc **gửi thông báo** mỗi lần thấy member có thể làm phát sinh hai lần.

~~~text
SSCAN phát "user:101"
       |
       v
Xử lý user:101 lần 1

SSCAN có thể phát "user:101" lần nữa
       |
       v
Xử lý user:101 lần 2
~~~

Nếu nghiệp vụ yêu cầu mỗi người chỉ được nhận một thông báo cho một chiến dịch, hãy dùng **campaign ID + member ID** làm định danh công việc và áp dụng cơ chế xác nhận/idempotency riêng. Dùng Redis Set làm nguồn ID và SSCAN làm cách đọc không cung cấp delivery guarantee.

### 14.2. Không sửa Set đang scan một cách tùy tiện

Một job kiểu:

~~~java
try (Cursor<String> cursor = sets.scan(key, ScanOptions.NONE)) {
    while (cursor.hasNext()) {
        String member = cursor.next();
        sets.remove(key, member);
    }
}
~~~

có thể chạy trong một số trường hợp, nhưng nó vừa thay đổi cấu trúc dữ liệu vừa duyệt dữ liệu, khiến các giới hạn SCAN về member thêm/xóa và kết quả xuất hiện lại trở nên quan trọng. Không nên coi đó là quy trình “lấy đúng một lần tất cả member và xóa sạch” có bảo đảm chặt.

Nếu mục tiêu chỉ xóa toàn bộ Set, **DEL key** rõ ràng hơn. Nếu cần xử lý công việc có trạng thái “đang xử lý/đã hoàn tất”, hãy cân nhắc Redis Stream, queue với cơ chế xác nhận hoặc mô hình lưu trữ tiến trình phù hợp.

### 14.3. Nếu nhất thiết phải có snapshot

SSCAN không cung cấp snapshot. Tùy yêu cầu, có thể:

- Dừng ghi vào Set trong một cửa sổ được kiểm soát rồi thực hiện full iteration, đồng thời vẫn thiết kế xử lý trùng.
- Sao chép hoặc chuyển dữ liệu vào cấu trúc/bản chụp riêng trước khi xử lý, sau khi cân nhắc chi phí bộ nhớ và tính nhất quán.
- Dùng database/truy vấn có snapshot semantics hoặc sắp xếp ổn định nếu đây là yêu cầu thiết yếu.

Không tự thêm nhiều lần gọi SSCAN rồi tuyên bố “đã lấy chính xác tất cả member tại một thời điểm”. Muốn làm việc đó cần cơ chế nhất quán bên ngoài bản thân SSCAN.

## 15. SSCAN có thể dùng cho API phân trang không?

Một frontend có thể muốn URL:

~~~text
GET /groups/java/members?cursor=0&pageSize=50
~~~

Về kỹ thuật, backend có thể chuyển tiếp Redis cursor để quét tiếp. Tuy nhiên **cursor của SSCAN không phải token phân trang ổn định**:

- Thứ tự thành viên không được xác định.
- COUNT không bảo đảm đúng 50 member.
- Những lần quét khác nhau có thể trả lại member trùng.
- Member thêm/xóa trong thời gian user chuyển trang có thể xuất hiện hoặc bị bỏ qua.
- Cursor không thể dùng như page number để nhảy tới trang bất kỳ.

Nếu yêu cầu chỉ là **truyền từng lô dữ liệu để xuất file hoặc chạy batch**, SSCAN có thể phù hợp. Nếu yêu cầu là **trải nghiệm pagination ổn định, sắp xếp theo tên hoặc ngày tham gia**, nên dùng Sorted Set theo score, index trong database hoặc cơ chế snapshot riêng.

Trong trường hợp buộc phải expose Redis cursor cho API nội bộ, nên ghi rõ semantics **best effort**, kiểm soát định dạng cursor, thời hạn sử dụng, quyền truy cập nhóm và không bảo đảm snapshot. Đừng dùng cursor từ một Redis key cho key khác, và đừng để client tùy ý tự chỉnh cursor.

## 16. Redis Cluster: SSCAN chỉ duyệt một Set cụ thể

Redis Cluster chia key theo hash slot. Một Set như **learning:group:java:members** thuộc về một slot và được lưu trên node chịu trách nhiệm cho slot đó.

Khi gọi:

~~~redis
SSCAN learning:group:java:members 0 COUNT 200
~~~

Redis xử lý thành viên của **Set key được chỉ định**. SSCAN không tự quét mọi Set trên mọi master node trong Cluster.

Ứng dụng dùng Spring Data Redis cùng driver hỗ trợ Cluster thường có cơ chế định tuyến tới node chứa key và xử lý redirect tương ứng. Khi topology thay đổi hoặc failover xảy ra giữa nhiều lượt quét, cần chuẩn bị cho lỗi, retry và khả năng phải bắt đầu một vòng duyệt mới; không nên coi cursor là snapshot bất biến vượt qua mọi chuyển đổi cluster.

Nếu mô hình dữ liệu là “mỗi nhóm có một Set riêng” thì:

~~~text
learning:group:java:members   -> một Redis Set key
learning:group:spring:members -> một Redis Set key khác
learning:group:redis:members  -> một Redis Set key khác
~~~

Muốn duyệt **tất cả nhóm**, trước tiên phải có danh sách nhóm hoặc cơ chế quét keyspace phù hợp. **SSCAN** trên một group key chỉ duyệt các member trong nhóm đó.

## 17. Bộ nhớ, độ trễ và vận hành

SSCAN thường phù hợp cho bộ dữ liệu lớn hơn SMEMBERS vì ứng dụng có thể tiêu thụ kết quả từng phần. Tuy nhiên cách gọi và xử lý vẫn quyết định tác động vận hành.

### 17.1. Một số tín hiệu cần quan sát

| Tín hiệu | Ý nghĩa |
|---|---|
| Thời gian cho một SSCAN command | Có batch bị chậm bất thường không |
| Tổng thời gian cho full iteration | Tốc độ hoàn thành job có đáp ứng không |
| Số member đã xử lý | Phát hiện tiến trình job tăng quá nhanh/chậm |
| Lỗi hoặc reconnect Redis | Có phải khởi động lại scan hay phục hồi không |
| Độ trễ của các request Redis khác | Scan có ảnh hưởng dịch vụ trực tuyến không |
| Bộ nhớ heap của worker | Có vô tình gom tất cả member vào List/Set không |
| Tỷ lệ trùng và hành vi idempotent | Có tác dụng phụ lặp lại không |

Khi job duyệt Set khổng lồ, đừng chỉ tăng COUNT thật lớn để giảm số round trip. Có thể cần giới hạn concurrency phía application, chia lô xử lý phù hợp và tránh chạy nhiều full scan cùng lúc trên cùng key.

### 17.2. Ví dụ lựa chọn COUNT có chủ đích

Giả sử service cần duyệt một Set lớn để đồng bộ thành viên:

~~~java
ScanOptions options = ScanOptions.scanOptions()
    .count(500)
    .build();
~~~

**500 chỉ là giá trị thử nghiệm ban đầu.** Có thể điều chỉnh theo kích thước member, độ trễ mạng và thời gian xử lý downstream. Nếu mỗi member cần gọi một API từ xa mất 100 ms, bottleneck nhiều khả năng nằm ở hệ thống được gọi hơn là số lần SSCAN.

### 17.3. Không giữ Cursor qua nhiều HTTP request

Một **Cursor** của Spring Data Redis là đối tượng gắn với vòng đời truy cập dữ liệu. Không lưu nó trong singleton service để nhiều thread cùng dùng, không serialize trực tiếp object Cursor vào response và không giữ nó mở trong nhiều phút chỉ để người dùng bấm “Trang tiếp”.

Nếu cần một job kéo dài, hãy quản lý nó ở tầng worker với vòng đời tài nguyên rõ ràng, hoặc lưu state công việc độc lập. Nếu cần phân trang API ổn định, dùng mô hình dữ liệu phù hợp với pagination.

## 18. Những lỗi thường gặp

### Lỗi 1: Dùng SMEMBERS để lấy số lượng

~~~java
int count = sets.members(key).size();
~~~

Đoạn code lấy toàn bộ Set rồi mới đếm. Với dữ liệu lớn, nó làm tăng sử dụng mạng và bộ nhớ. Thay bằng:

~~~java
Long count = sets.size(key);
~~~

### Lỗi 2: Dừng scan khi batch rỗng

~~~text
SSCAN key 0 MATCH vip:* COUNT 10
  -> cursor="18", members=[]
~~~

Nếu dừng ở đây, có thể bỏ qua các member khớp mẫu xuất hiện trong những lượt sau. Chỉ kết thúc khi **next cursor = 0**.

### Lỗi 3: Xem COUNT là page size

**COUNT 50** không phải cam kết trả đúng 50 phần tử và không cung cấp stable pagination. Đừng dùng nó để đảm bảo response UI có chính xác 50 member.

### Lỗi 4: Quên đóng Cursor

~~~java
Cursor<String> cursor = sets.scan(key, ScanOptions.NONE);
// Duyệt một phần rồi return mà không close: có thể giữ tài nguyên.
~~~

Dùng **try-with-resources** để đóng cả khi vòng duyệt kết thúc sớm hoặc xảy ra exception.

### Lỗi 5: Tin rằng SSCAN không có phần tử trùng

Tập Redis không chứa bản sao member, nhưng kết quả full scan có thể chứa cùng một member hơn một lần. Hãy xử lý idempotent hoặc deduplicate có kiểm soát.

### Lỗi 6: Dùng MATCH để đếm nhanh theo điều kiện

SSCAN MATCH vẫn phải duyệt; số lượng batch cộng dồn có thể đếm trùng và không phải snapshot. Nếu cần phép đếm nhanh theo loại, hãy mô hình hóa tập con hoặc chỉ số đếm riêng.

### Lỗi 7: Nhầm SCAN và SSCAN

~~~redis
SCAN 0 MATCH group:*
~~~

Lệnh này tìm key. Để duyệt member của một Set:

~~~redis
SSCAN group:java:members 0
~~~

### Lỗi 8: Xem SCARD và SSCAN như cùng một ảnh chụp

~~~text
SCARD key -> 1000
SSCAN key ... -> đọc thành viên trong vài giây
~~~

Nếu có request khác SADD/SREM trong khoảng đó, số member quét được có thể không khớp với SCARD ban đầu. Đây là khác biệt về thời điểm quan sát và semantics của scan, không nhất thiết là lỗi serializer.

### Lỗi 9: Không kiểm tra data type và serializer

SetOperations yêu cầu Redis key đang chứa type **set**. Một service khác có thể dùng **SET** vào cùng key hoặc dùng serializer không thống nhất, khiến WRONGTYPE hoặc dữ liệu Java không giải mã được.

### Lỗi 10: Phản hồi HTTP quá lớn dù đã dùng SSCAN

Nếu service scan từng batch nhưng cuối cùng vẫn **collect** toàn bộ member vào một List rồi trả JSON một lần, bộ nhớ và response vẫn tăng theo N. Streaming thực sự chỉ có ích khi tầng tiêu thụ cũng xử lý theo phần nhỏ hoặc có giới hạn rõ.

## 19. Bài tập tự kiểm tra

### Bài 1 — Đếm sau khi thêm trùng

Redis chạy:

~~~redis
DEL exercise:set
SADD exercise:set a b c
SADD exercise:set b c d
SCARD exercise:set
~~~

**Kết quả:** **4**, vì chỉ có a, b, c, d là các member duy nhất.

### Bài 2 — Key chưa tồn tại

~~~redis
SCARD unknown:key
~~~

**Kết quả:** **0**. Nếu key mang type String thay vì Set, lệnh không trả 0 mà gặp lỗi sai kiểu dữ liệu.

### Bài 3 — Batch rỗng nhưng cursor chưa bằng 0

Một lượt:

~~~text
SSCAN key 0 MATCH premium:* COUNT 5
  -> cursor="37"
  -> members=[]
~~~

**Câu hỏi:** Có dừng quét không?

**Giải thích:** Không. Dùng cursor **37** cho lượt tiếp theo và tiếp tục đến khi Redis trả next cursor **0**.

### Bài 4 — COUNT = 10

**Câu hỏi:** Lệnh **SSCAN key 0 COUNT 10** có luôn trả đúng 10 thành viên không?

**Giải thích:** Không. COUNT là gợi ý công việc, không phải giới hạn chính xác. Một số cấu trúc Set nhỏ có thể được trả toàn bộ trong một lượt.

### Bài 5 — Đếm theo tiền tố

Set chứa 100.000 member, trong đó 500 member bắt đầu bằng **vip:**. Có thể dùng **SCARD key** để trực tiếp trả 500 không?

**Giải thích:** Không, SCARD trả tổng số member của Set. **SSCAN MATCH vip:\*** có thể tìm các member phù hợp nhưng không bảo đảm phép đếm nhanh/snapshot. Nếu truy vấn theo tiền tố diễn ra thường xuyên, có thể duy trì một Set riêng cho thành viên VIP.

### Bài 6 — Quét khi có ghi đồng thời

Một job đang dùng SSCAN, trong lúc một request thêm **user:999**. Job có bắt buộc nhìn thấy **user:999** trong lần quét này không?

**Giải thích:** Không. Member được thêm khi scan đang chạy có thể xuất hiện hoặc không. Full scan chỉ có bảo đảm hạn chế cho phần tử tồn tại liên tục từ đầu đến cuối.

### Bài 7 — Đóng cursor

Đoạn nào quản lý tài nguyên tốt hơn?

~~~java
// A:
Cursor<String> cursor = sets.scan(key, options);
while (cursor.hasNext()) {
    handle(cursor.next());
}

// B:
try (Cursor<String> cursor = sets.scan(key, options)) {
    while (cursor.hasNext()) {
        handle(cursor.next());
    }
}
~~~

**Giải thích:** **B** đóng Cursor kể cả khi có lỗi trong handle hoặc vòng lặp kết thúc sớm.

### Bài 8 — Tại sao count() khác số phần tử job xử lý?

**Tình huống:** SCARD trước job trả 10.000. Sau khi full SSCAN, hệ thống ghi nhận 10.008 lần gọi callback.

**Giải thích:** Có thể có member trùng trong kết quả scan, hoặc có cập nhật Set đồng thời. Không nên so sánh cứng hai con số rồi cho rằng Redis đếm sai; cần kiểm soát thời gian quan sát, duplicate và mutation.

### Bài 9 — Chọn đúng lệnh

**Yêu cầu:** API chỉ cần trả **true** nếu **user:100** đang thuộc nhóm **java**.

**Giải thích:** Dùng **SISMEMBER** thông qua **SetOperations.isMember(key, member)**. Không dùng SCARD hay full SSCAN cho phép kiểm tra một member.

### Bài 10 — Bài toán phân trang

**Yêu cầu:** UI hiển thị thành viên mới nhất theo ngày tham gia, cho phép mở trang 1, 2, 3 một cách ổn định.

**Giải thích:** Set và SSCAN không có thứ tự theo ngày và không bảo đảm stable pagination. Cần lưu thông tin thứ tự ở cấu trúc khác (ví dụ Sorted Set hoặc database/index phù hợp).

## 20. Tài liệu tham khảo

- [Redis — SCARD](https://redis.io/docs/latest/commands/scard/)
- [Redis — SSCAN](https://redis.io/docs/latest/commands/sscan/)
- [Redis — SCAN và các bảo đảm của cursor iteration](https://redis.io/docs/latest/commands/scan/)
- [Redis — Sets](https://redis.io/docs/latest/develop/data-types/sets/)
- [Spring Data Redis — SetOperations API](https://docs.spring.io/spring-data-redis/docs/current/api/org/springframework/data/redis/core/SetOperations.html)
- [Spring Data Redis — ReactiveSetOperations API](https://docs.spring.io/spring-data-redis/docs/current/api/org/springframework/data/redis/core/ReactiveSetOperations.html)

## 21. Tổng kết

Với Redis Set, **SCARD** là cách nhanh và trực tiếp để đếm số thành viên duy nhất. Trong Spring Data Redis, thao tác tương ứng là **SetOperations.size(key)**. Nếu chỉ cần số lượng, không tải toàn bộ Set bằng SMEMBERS hay SSCAN rồi đếm ở Java.

**SSCAN** dành cho việc duyệt tăng dần các member của một Set thông qua cursor. Bắt đầu bằng cursor **0**, xử lý batch nhận được, rồi tiếp tục với next cursor cho đến khi Redis trả về **0**. **MATCH** lọc member theo glob; **COUNT** chỉ là gợi ý, không phải page size cố định. Với Spring Data Redis imperative, dùng **SetOperations.scan(key, ScanOptions)** và luôn **đóng Cursor**; với API reactive, dùng **ReactiveSetOperations.scan(...)** để nhận Flux.

Điểm cần nhớ khi đưa vào ứng dụng là **SSCAN không phải snapshot và có thể trả lại member trùng**. Kết quả có thể thay đổi nếu Set bị thêm/xóa trong lúc quét, và một vòng quét không bảo đảm tác dụng phụ được thực hiện đúng một lần. Chọn SCARD cho số lượng, SISMEMBER cho phép kiểm tra thành viên, SSCAN cho công việc duyệt từng phần và cơ chế dữ liệu khác khi cần thứ tự hoặc phân trang ổn định.
