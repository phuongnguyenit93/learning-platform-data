# Thông báo trong Cluster và phạm vi nút phát sự kiện

## 1. Vấn đề: tại sao đã SUBSCRIBE nhưng vẫn bỏ lỡ sự kiện?

Giả sử một ứng dụng Spring Boot dùng **Redis Cluster** để lưu hàng triệu khóa phiên đăng nhập có TTL. Khi phiên hết hạn, ứng dụng muốn nhận thông báo để cập nhật bộ đếm phiên hoạt động hoặc dọn dữ liệu phụ.

Ở Redis standalone, nhóm phát triển có thể thử:

```redis
CONFIG SET notify-keyspace-events Ex
PSUBSCRIBE __keyevent@0__:expired
```

Sau đó tạo một khóa có TTL:

```redis
SET session:42 active EX 3
```

Khi Redis thực sự xóa khóa vì hết hạn, subscriber đang kết nối có thể nhận được sự kiện `expired`.

Tuy nhiên, nếu ứng dụng chuyển sang **Redis Cluster** mà vẫn chỉ lắng nghe một nút, nó có thể nhận sự kiện của một số khóa nhưng không nhận những sự kiện khác:

```text
                      Spring Boot
                    "lắng nghe Redis"
                            |
                            v
              PSUBSCRIBE trên node A
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
     Primary A         Primary B         Primary C
     slot 0..N         slot ...          slot ...
          |                 |                 |
     key session:1     key session:2     key session:3
          |                 |                 |
     expired event     expired event     expired event
          |                 |                 |
          +----> App       [không đến A]    [không đến A]
```

**Nguyên nhân chính:** keyspace/keyevent notifications của Redis có **phạm vi nút (node-local)**. Redis không tự phát tán các thông báo này từ mọi nút tới một subscriber chỉ kết nối với một nút của Cluster.

Vì vậy, khi sử dụng thông báo khóa với Spring Data Redis, cần phân biệt rõ:

1. **Nút nào sở hữu khóa và thực hiện thay đổi gây ra sự kiện?**
2. **Nút nào đang phát thông báo?**
3. **Kết nối của listener đang SUBSCRIBE tới nút nào?**
4. **Cơ chế listener có bao phủ các nút liên quan khi topology thay đổi không?**

Bài học này tập trung vào **thông báo khóa trong Redis Cluster**, cách kiểm tra phạm vi phát sự kiện và các hệ quả vận hành khi kết hợp Redis với Spring Data Redis.

## 2. Keyspace notification và keyevent notification là gì?

Redis có cơ chế **keyspace notifications** dựa trên Pub/Sub. Khi một lệnh hoặc quá trình nội bộ làm thay đổi trạng thái khóa, Redis có thể phát sự kiện nếu cấu hình tương ứng được bật.

Có hai dạng kênh quan trọng.

### 2.1. Keyspace channel: kênh mang tên khóa

Mẫu kênh:

```text
__keyspace@<db>__:<key>
```

Ví dụ:

```text
__keyspace@0__:session:42
```

Nếu khóa `session:42` hết hạn, message gửi tới kênh này có thể là tên sự kiện:

```text
expired
```

Sơ đồ:

```text
Channel: __keyspace@0__:session:42
Message: expired
```

**Keyspace notification** phù hợp khi muốn theo dõi những loại sự kiện xảy ra trên một khóa hoặc nhóm khóa.

Đăng ký với Redis CLI:

```redis
PSUBSCRIBE __keyspace@0__:session:*
```

Phần `*` là mẫu tên kênh Pub/Sub, không phải lệnh quét toàn bộ các khóa Redis.

### 2.2. Keyevent channel: kênh mang tên sự kiện

Mẫu kênh:

```text
__keyevent@<db>__:<event>
```

Ví dụ:

```text
__keyevent@0__:expired
```

Message là tên khóa:

```text
session:42
```

Sơ đồ:

```text
Channel: __keyevent@0__:expired
Message: session:42
```

**Keyevent notification** hữu ích khi ứng dụng muốn nhận tất cả những khóa vừa phát sinh một loại sự kiện, chẳng hạn `expired`.

Đăng ký:

```redis
PSUBSCRIBE __keyevent@0__:expired
```

### 2.3. So sánh hai dạng

| Đặc điểm | Keyspace | Keyevent |
|---|---|---|
| Cấu trúc channel | `__keyspace@0__:session:42` | `__keyevent@0__:expired` |
| Message cho sự kiện hết hạn | `expired` | `session:42` |
| Câu hỏi phù hợp | Chuyện gì xảy ra với khóa này? | Những khóa nào vừa gặp sự kiện này? |
| Cờ cấu hình cần bật | `K` và loại sự kiện | `E` và loại sự kiện |
| Có lưu lịch sử sự kiện không? | Không | Không |
| Có tự phát từ mọi node của Cluster không? | Không | Không |

Cả hai là **thông báo Pub/Sub tức thời**, không phải bản ghi tồn tại lâu dài trong Redis.

## 3. Bật thông báo bằng notify-keyspace-events

Redis thường **tắt keyspace notifications theo mặc định** để tránh chi phí không cần thiết. Cấu hình được điều khiển bởi tham số:

```redis
CONFIG GET notify-keyspace-events
```

Một số cờ thông dụng:

| Cờ | Ý nghĩa |
|---|---|
| `K` | Phát sự kiện theo dạng keyspace channel |
| `E` | Phát sự kiện theo dạng keyevent channel |
| `g` | Các sự kiện thao tác khóa tổng quát như `del`, `expire`, `rename` |
| `$` | Các sự kiện liên quan thao tác trên Redis String |
| `h` | Các sự kiện liên quan thao tác trên Redis Hash |
| `x` | Sự kiện khóa thực sự hết hạn (`expired`) |
| `e` | Sự kiện khóa bị loại bởi eviction (`evicted`) |
| `A` | Bí danh bật phần lớn nhóm loại sự kiện thông thường; không thay thế `K` hoặc `E` |

**Ví dụ:** chỉ cần sự kiện khóa hết hạn theo dạng keyevent:

```redis
CONFIG SET notify-keyspace-events Ex
```

Ý nghĩa:

- `E`: dùng kênh `__keyevent@...__:<event>`.
- `x`: bật sự kiện `expired`.

Nếu muốn dạng keyspace cho khóa hết hạn:

```redis
CONFIG SET notify-keyspace-events Kx
```

Nếu muốn cả hai:

```redis
CONFIG SET notify-keyspace-events KEx
```

Không nên bật mọi loại sự kiện khi chỉ cần một loại, vì lượng thông báo và chi phí vận hành có thể tăng khi ứng dụng ghi/xóa khóa với tần suất cao.

### 3.1. Phải phân biệt expired, expire, del và evicted

Các sự kiện có ý nghĩa khác nhau:

| Sự kiện | Tình huống |
|---|---|
| `expire` | Một thao tác đặt thời hạn cho khóa, tùy lệnh và cấu hình |
| `expired` | Redis thực sự xóa khóa vì hết hạn |
| `del` | Khóa bị xóa bởi thao tác xóa hoặc tác động tương ứng |
| `evicted` | Redis loại khóa do chính sách quản lý bộ nhớ |

Chẳng hạn:

```redis
EXPIRE session:42 60
```

đặt thời hạn cho khóa. Nó không đồng nghĩa Redis đã phát ngay `expired`.

Tương tự:

```redis
DEL session:42
```

là xóa chủ động, không phải khóa chờ tới hạn tự hết hạn. Nếu nghiệp vụ cần nhận cả hai loại, phải bật các nhóm sự kiện thích hợp và đăng ký đúng channel.

### 3.2. Cấu hình phải áp dụng ở nút có phát sự kiện

Trong Redis standalone:

```text
Redis server duy nhất
  notify-keyspace-events = Ex
  subscriber đăng ký tại server đó
```

Trong Redis Cluster:

```text
Primary A: notify-keyspace-events = Ex
Primary B: notify-keyspace-events = Ex
Primary C: notify-keyspace-events = Ex
```

`CONFIG SET` trên **một nút** không tự động cấu hình toàn bộ nút khác. Nếu chỉ cấu hình A, khóa do B hoặc C quản lý có thể không tạo ra thông báo mong muốn.

Đối với môi trường production, nên quản lý cấu hình bằng công cụ triển khai và kiểm tra cấu hình trên **các nút liên quan**. Thay đổi động bằng `CONFIG SET` không nhất thiết được lưu bền vững qua restart; cách duy trì cấu hình phụ thuộc Redis deployment, file cấu hình hoặc nhà cung cấp dịch vụ quản lý.

Một số dịch vụ Redis được quản lý có thể hạn chế lệnh `CONFIG`, nên cần sử dụng tham số cấu hình được nhà cung cấp hỗ trợ. Không mặc định ứng dụng có quyền tự bật thông báo khi khởi động.

## 4. Redis Cluster chia khóa theo slot và nút nào phát sự kiện?

### 4.1. Cluster phân phối khóa theo hash slot

Redis Cluster phân chia không gian khóa thành **16.384 hash slot**, phân bổ cho các primary. Với một khóa, slot được tính từ tên khóa, có xét hash tag nếu được sử dụng.

Ví dụ:

```text
Cluster gồm ba primary

Primary A                Primary B                Primary C
Slots: một vùng           Slots: một vùng           Slots: một vùng
      |                         |                         |
  session:user-1            session:user-2            session:user-3
```

Các vùng slot thực tế phụ thuộc cấu hình Cluster, không nên suy luận từ tên khóa rằng `session:user-1` chắc chắn thuộc A.

Có thể hỏi Redis:

```redis
CLUSTER KEYSLOT session:user-1
```

Để xem phân bố slot và các nút:

```redis
CLUSTER SHARDS
```

Hoặc:

```redis
CLUSTER SLOTS
```

Các lệnh này hỗ trợ xác định **primary đang chịu trách nhiệm cho slot**. Redis Cluster client có thể tự định tuyến lệnh truy cập khóa đến đúng node sở hữu slot.

### 4.2. Thao tác thay đổi khóa diễn ra tại node sở hữu khóa

Giả sử `session:user-2` thuộc một slot của Primary B:

```text
Spring Boot
    |
    | SET session:user-2 active EX 30
    v
Redis Cluster client
    |
    | định tuyến tới owner của slot
    v
Primary B
    |
    | Lưu khóa và quản lý TTL
    v
Redis thực sự xóa khóa vì hết hạn
    |
    v
Primary B phát "__keyevent@0__:expired"
    |
    v
Subscriber nối trực tiếp với B có thể nhận
```

Nếu ứng dụng chỉ đăng ký trên Primary A, **không có bảo đảm** sự kiện từ B sẽ được chuyển tới kết nối ấy.

Đây là giới hạn quan trọng của **keyspace notifications trong Cluster**: chúng gắn với nút phát sự kiện chứ không phải một “kênh thông báo toàn cụm” tự động.

### 4.3. Sự kiện hết hạn xuất hiện lúc Redis xóa khóa

Redis có cơ chế hết hạn thụ động và chủ động. Khi thời gian TTL đã về 0, sự kiện `expired` không nhất thiết được phát đúng vào mili giây mà khóa đạt hạn.

Một ví dụ:

```text
T0: SET session:user-2 EX 30
T0 + 30 s: thời hạn logic kết thúc
T0 + 30 s hoặc muộn hơn: Redis phát hiện và xóa khóa
                             |
                             v
                       phát expired
```

Với khóa ít được truy cập, thông báo có thể xuất hiện muộn hơn mốc TTL danh nghĩa. Không dùng thời điểm nhận `expired` như một đồng hồ lịch biểu chính xác.

Khóa có thể bị xóa chủ động (`DEL`), bị eviction hoặc mất do thao tác quản trị, và những tình huống ấy không nhất thiết tạo ra **cùng loại** thông báo `expired`.

## 5. Phạm vi nút phát sự kiện: điều gì được và không được bảo đảm?

### 5.1. Chỉ subscribe một node là không đủ để theo dõi toàn Cluster

Mô hình sau dễ gây hiểu nhầm:

```text
Application listener
         |
         | PSUBSCRIBE __keyevent@0__:expired
         v
      Node A
         |
         +-- nhận sự kiện do A phát

Node B ------ sự kiện B không tự chuyển cho listener trên A
Node C ------ sự kiện C không tự chuyển cho listener trên A
```

Ngay cả khi ứng dụng có một `RedisConnectionFactory` cấu hình **cluster-aware** để đọc/ghi khóa, điều đó **không tự chứng minh** listener đang nhận tất cả keyspace notifications từ mọi node.

Một driver hoặc phiên bản thư viện có thể có cách đăng ký Pub/Sub riêng. Muốn khẳng định bao phủ toàn Cluster, phải xác minh cụ thể kết nối subscribe, danh sách node được đăng ký và hành vi khi topology đổi. Không coi một endpoint Cluster là một subscription toàn cụm nếu chưa xác nhận điều đó.

### 5.2. Sự kiện không được phát lại khi mất kết nối

Keyspace notifications dựa trên Redis Pub/Sub, có tính chất **fire-and-forget**:

- Redis không lưu một hàng đợi thông báo hết hạn cho subscriber tạm offline.
- Redis không cung cấp ACK theo từng thông báo để biết listener đã xử lý xong.
- Khi node mất kết nối, những thông báo phát trong khoảng gián đoạn có thể mất.
- Reconnect giúp nhận **thông báo tương lai**, không làm xuất hiện lại thông báo cũ.

Do đó, ngay cả khi subscribe mọi primary, ứng dụng cũng **không có bảo đảm nhận đủ 100% sự kiện** khi có restart, mất mạng, chuyển đổi primary hoặc quá tải.

### 5.3. Không có thứ tự sự kiện toàn Cluster

Một khóa trên A và một khóa trên B có thể hết hạn gần cùng thời điểm. Thứ tự listener nhận thông báo phụ thuộc việc Redis thực thi, thời điểm phát hiện hết hạn, mạng và lịch xử lý callback.

Không nên suy ra:

```text
Nhận expired keyA trước keyB
=> keyA nhất định hết hạn trước keyB theo thời gian nghiệp vụ
```

Nếu cần sắp xếp có thứ tự hoặc xử lý sự kiện bền vững trên nhiều thực thể, cần giao thức/nguồn dữ liệu khác phù hợp hơn.

### 5.4. Node mới hoặc failover làm thay đổi nơi phát sự kiện

Khi Cluster reshard, thêm primary hoặc failover:

```text
Trước thay đổi:
  slot X -> Primary A
  key K -> A
  listener đang subscribe A

Sau failover/resharding:
  slot X -> Primary D
  key K -> D
  listener chỉ subscribe A
```

Sự kiện mới của khóa có thể xuất hiện trên nút đang quản lý khóa **sau thay đổi**. Hệ thống subscriber phải:

1. Biết danh sách primary hiện tại.
2. Đăng ký trên primary mới khi topology thay đổi.
3. Duy trì kết nối/đăng ký trong lúc các nút phục hồi.
4. Ngừng đăng ký những node không còn phù hợp.
5. Chấp nhận rằng thời gian chuyển đổi có thể gây mất hoặc trùng thông báo đối với ứng dụng.

Việc đăng ký nhiều nút có thể phải thay đổi động; danh sách node cố định trong file cấu hình chỉ phù hợp khi topology cố định hoặc dùng để minh họa.

## 6. Khác biệt giữa keyspace notifications và Redis Pub/Sub thông thường

Redis Cluster hỗ trợ các cơ chế Pub/Sub, nhưng **không nên lấy hành vi phát một message tùy ý bằng `PUBLISH` để suy luận rằng keyspace notifications tự lan qua toàn Cluster**.

| Cơ chế | Mục đích | Cần hiểu về Cluster |
|---|---|---|
| `PUBLISH` / `SUBSCRIBE` thông thường | Ứng dụng tự phát thông điệp tới kênh | Có cơ chế phân phối Pub/Sub theo mô hình Redis Cluster |
| `SPUBLISH` / `SSUBSCRIBE` (sharded Pub/Sub) | Phát Pub/Sub theo shard, từ Redis 7 | Có quy tắc shard/slot cho kênh riêng |
| Keyspace / keyevent notification | Redis tự phát sự kiện do thay đổi khóa | **Thông báo mang phạm vi nút phát**; không được tự động broadcast như một message ứng dụng toàn cụm |
| Redis Streams | Lưu entry và cho consumer đọc/xác nhận | Là dữ liệu lưu trữ, có cách đọc và quản lý khác Pub/Sub |

Ví dụ:

```redis
PUBLISH app:session-events "user-2 signed out"
```

là message **ứng dụng chủ động gửi**.

Ngược lại:

```text
__keyevent@0__:expired  ->  session:user-2
```

là **sự kiện nội bộ Redis tự phát** khi khóa thực sự hết hạn và cấu hình cho phép.

Đừng xây dựng một listener chỉ vì thử `PUBLISH` qua Cluster thấy hoạt động rồi kết luận nó sẽ nhận mọi `expired` trên tất cả primary.

## 7. Redis Cluster chỉ hỗ trợ database 0

Redis Cluster không cho các client tùy chọn nhiều logical database bằng `SELECT` như một Redis standalone. Trong Redis Cluster, thông thường sử dụng **database 0**.

Vì vậy, tên kênh thông báo thường là:

```text
__keyspace@0__:some:key
__keyevent@0__:expired
```

Nếu một ứng dụng lấy cấu hình từ Redis standalone với:

```text
__keyevent@1__:expired
```

thì áp dụng nguyên xi vào Cluster sẽ không đúng. Cần kiểm tra kiến trúc và channel.

Không nên dùng “database index” như cơ chế tách tenant trong Cluster. Có thể dùng namespace khóa và cơ chế phân quyền phù hợp, nhưng tên kênh thông báo vẫn có thể tiết lộ tên khóa nếu nhiều thành phần cùng nghe.

## 8. Kiểm chứng thực tế bằng redis-cli trên từng primary

Cách tốt nhất để hiểu phạm vi nút là **tạo một khóa tại node sở hữu slot và lắng nghe từ hai nút khác nhau**.

Giả sử Redis Cluster phát triển có ba primary với cổng ví dụ `7000`, `7001`, `7002`. Đây là topology minh họa; thay địa chỉ/cổng bằng thông tin môi trường thực.

### Bước 1: Xem topology

Từ một node bất kỳ trong Cluster:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS
```

Và kiểm tra slot của một khóa:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT demo:session:42
```

Xác định **primary sở hữu slot** của `demo:session:42` từ kết quả topology. Không đoán theo đuôi `42`.

### Bước 2: Bật thông báo trên từng primary

Trên môi trường phát triển cho phép `CONFIG`:

```bash
redis-cli -p 7000 CONFIG SET notify-keyspace-events Ex
redis-cli -p 7001 CONFIG SET notify-keyspace-events Ex
redis-cli -p 7002 CONFIG SET notify-keyspace-events Ex
```

Kiểm tra từng nơi:

```bash
redis-cli -p 7000 CONFIG GET notify-keyspace-events
redis-cli -p 7001 CONFIG GET notify-keyspace-events
redis-cli -p 7002 CONFIG GET notify-keyspace-events
```

Các lệnh `CONFIG SET` **phải được thực thi trên từng node** cần cấu hình, và chỉ thực hiện khi có quyền cấu hình Redis. Nếu môi trường có replica, topology của chúng cũng cần được xem xét cho failover; không mặc định một lần cấu hình trên primary sẽ tồn tại đúng cách sau mọi chuyển đổi.

Không chạy lệnh này lên production mà chưa đánh giá chi phí sự kiện và quy trình quản lý cấu hình.

### Bước 3: Mở subscriber trực tiếp trên từng primary

Terminal A:

```bash
redis-cli -p 7000 PSUBSCRIBE '__keyevent@0__:expired'
```

Terminal B:

```bash
redis-cli -p 7001 PSUBSCRIBE '__keyevent@0__:expired'
```

Terminal C:

```bash
redis-cli -p 7002 PSUBSCRIBE '__keyevent@0__:expired'
```

**Không dùng một kết nối duy nhất** tới node 7000 để kết luận đã bao phủ cả cụm. Mỗi cửa sổ ở ví dụ trên kết nối trực tiếp đến một node khác nhau.

### Bước 4: Tạo khóa có TTL qua cluster-aware client

Terminal D:

```bash
redis-cli -c -p 7000 SET demo:session:42 active EX 3
```

Tùy slot, Redis Cluster có thể chuyển hướng lệnh tới node sở hữu. `-c` cho phép redis-cli theo các chuyển hướng cần thiết.

Sau khi Redis thực sự xóa khóa vì hết hạn, quan sát ba cửa sổ subscribe.

**Kỳ vọng:** thông báo xuất hiện tại kết nối của node phát sự kiện tương ứng, thay vì được nhân bản tự động lên tất cả cửa sổ subscribe.

### Bước 5: Lặp lại với khóa thuộc slot khác

Dùng `CLUSTER KEYSLOT` để tìm khóa thuộc một primary khác. Có thể thử tên:

```text
demo:session:43
demo:session:44
demo:session:45
```

nhưng phải **kiểm tra slot thực tế** trước, không được giả định rằng tên khác chắc chắn nằm ở primary khác.

Tạo TTL trên một khóa đã xác định thuộc node khác, rồi so sánh cửa sổ nhận sự kiện. Bài tập cho thấy **nút phát có thể thay đổi theo owner của khóa**.

### Bước 6: Thử DEL để phân biệt event

Trên một khóa chưa hết hạn:

```bash
redis-cli -c -p 7000 SET demo:session:manual active EX 120
redis-cli -c -p 7000 DEL demo:session:manual
```

Nếu subscriber chỉ theo dõi `expired`, đừng kỳ vọng `DEL` tạo thông điệp `expired`. Muốn quan sát `del`, cấu hình phải có các cờ tương ứng và subscriber phải nghe channel dành cho sự kiện đó.

### Bước 7: Ghi lại kết quả

| Khóa thử nghiệm | Hash slot | Primary sở hữu | Nút phát thông báo quan sát được |
|---|---:|---|---|
| `demo:session:42` | Đo bằng lệnh | Xác định từ Cluster | Ghi kết quả |
| `demo:session:43` | Đo bằng lệnh | Xác định từ Cluster | Ghi kết quả |
| `demo:session:44` | Đo bằng lệnh | Xác định từ Cluster | Ghi kết quả |

Không điền số slot hoặc tên primary nếu chưa lấy từ Redis Cluster thật. Điểm cần quan sát là **mối liên hệ giữa owner của khóa và nút phát sự kiện**.

## 9. Spring Data Redis: lắng nghe sự kiện với RedisMessageListenerContainer

Spring Data Redis cung cấp `RedisMessageListenerContainer` để quản lý đăng ký Pub/Sub và chuyển message tới một `MessageListener`.

### 9.1. Listener đọc keyevent expired

```java
package com.example.redis.notifications;

import java.nio.charset.StandardCharsets;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class ExpiredKeyListener implements MessageListener {

    private static final Logger log =
            LoggerFactory.getLogger(ExpiredKeyListener.class);

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
                message.getChannel(),
                StandardCharsets.UTF_8
        );

        String expiredKey = new String(
                message.getBody(),
                StandardCharsets.UTF_8
        );

        if (!expiredKey.startsWith("session:")) {
            return;
        }

        log.info(
                "Nhận thông báo khóa hết hạn: channel={}, key={}",
                channel, expiredKey
        );

        // Chỉ thực hiện tác vụ ngắn và an toàn khi lặp.
        // Không coi thông báo này là bằng chứng đã chạy
        // nghiệp vụ bền vững.
    }
}
```

Với keyevent channel `__keyevent@0__:expired`, **body chứa tên khóa**. Nếu dùng keyspace channel như `__keyspace@0__:session:*`, body thường là **tên sự kiện**, nên cách giải mã và định tuyến phải đổi tương ứng.

Đừng lấy `message.getBody()` và cho rằng luôn là JSON hoặc giá trị của khóa đã hết hạn.

### 9.2. Ví dụ một container lắng nghe một kết nối

```java
package com.example.redis.notifications;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class RedisKeyEventConfig {

    @Bean
    public RedisMessageListenerContainer keyEventContainer(
            RedisConnectionFactory connectionFactory,
            ExpiredKeyListener listener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
                listener,
                new PatternTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

Trong Redis standalone, cấu hình này minh họa cách đơn giản để nhận `expired`.

**Trong Redis Cluster:** đoạn code trên **chưa chứng minh** đã subscribe đủ tất cả primary. Tính năng cluster, cách lựa chọn kết nối subscription và việc phân phối qua node phụ thuộc client/driver và phiên bản. Cần đo/quan sát kết nối tới từng node, không suy luận từ việc `RedisConnectionFactory` biết Redis Cluster là listener tự bao phủ toàn Cluster.

### 9.3. Ví dụ ghép container với từng node riêng

Để thấy rõ yêu cầu “mỗi node có subscription riêng”, có thể cấu hình những `RedisConnectionFactory` kết nối trực tiếp đến các node được nêu tên.

Ví dụ **một primary** trên môi trường phát triển:

```java
package com.example.redis.notifications;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class Node7000NotificationConfig {

    @Bean("node7000ConnectionFactory")
    public LettuceConnectionFactory node7000ConnectionFactory() {
        return new LettuceConnectionFactory(
                new RedisStandaloneConfiguration(
                        "redis-node-7000", 7000
                )
        );
    }

    @Bean("node7000KeyEventListener")
    public RedisMessageListenerContainer node7000KeyEventListener(
            @Qualifier("node7000ConnectionFactory")
            RedisConnectionFactory connectionFactory,
            ExpiredKeyListener listener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
                listener,
                new PatternTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

Điểm quan trọng không phải chính tên node 7000, mà là **kết nối Pub/Sub được gắn với node cụ thể**. Khi cấu hình các node khác, cần có container/kết nối subscription phù hợp cho từng primary.

Đây là **ví dụ mô tả một node**, không phải cấu hình Cluster production hoàn chỉnh. Nó chưa tự:

- Phát hiện primary mới khi reshard hoặc failover.
- Xóa kết nối tới node không còn phục vụ slot.
- Theo dõi trạng thái đăng ký và tự bù sự kiện bị mất.
- Giải quyết quyền truy cập/TLS/cấu hình trên môi trường được quản lý.
- Bảo đảm mỗi sự kiện chỉ được xử lý một lần.

Không đồng thời đăng ký cùng một node từ nhiều container không cần thiết rồi giả định mọi callback chỉ chạy một lần. Nếu vì chuyển đổi topology có hai subscription chồng lấp, handler cần an toàn với việc nhận thông báo trùng.

### 9.4. Phương án thiết kế cho Cluster thực

Đối với hệ thống cần theo dõi đầy đủ các node, nên có một thành phần quản lý subscription:

```text
Redis Cluster topology
          |
          v
  Topology Discovery
  (CLUSTER SHARDS/SLOTS hoặc API của driver)
          |
          v
   Danh sách primary đang hoạt động
          |
          v
 +--------+---------+---------+
 |                  |         |
 v                  v         v
Subscriber A    Subscriber B  Subscriber C
    |               |             |
    +---------------+-------------+
                    |
                    v
             ExpiredKeyListener
                    |
                    v
               Metric/log
```

Thành phần quản lý này cần:

1. Lấy danh sách primary hiện tại.
2. Kết nối và subscribe trên **từng primary cần theo dõi**.
3. Kiểm tra cấu hình notifications trên những node đó.
4. Theo dõi trạng thái kết nối, lỗi subscription và lần nhận cuối.
5. Làm mới danh sách subscription khi topology thay đổi.
6. Giới hạn tài nguyên, xử lý callback an toàn và tránh xử lý trùng trong giai đoạn chuyển đổi.

Có thể xây dựng bằng cơ chế quản lý connection của Redis client tương thích với phiên bản Spring Data Redis đang dùng, hoặc sử dụng các listener connection gắn node một cách có chủ đích. Cần xác minh rằng thư viện đang dùng **thực sự đăng ký từng node**, chứ không chỉ tự động định tuyến các thao tác dữ liệu như `GET`/`SET`.

## 10. Quan hệ với Spring Data Redis Repository và RedisKeyExpiredEvent

Spring Data Redis Repository có hỗ trợ TTL của thực thể, ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionEntry {

    @Id
    private String id;

    @TimeToLive
    private Long ttlSeconds;
}
```

Repository có thể sử dụng keyspace notifications để phát sự kiện tầng Spring, chẳng hạn `RedisKeyExpiredEvent`, khi nhận thông báo hết hạn từ Redis.

Tuy nhiên, cần phân biệt:

```text
Redis key hết hạn trên node thực sự quản lý khóa
                     |
                     v
Redis phát thông báo (nếu đã bật)
                     |
                     v
Listener của Spring có nhận được không?
                     |
             +-------+------+
             |              |
            Có            Không
             |              |
             v              v
 RedisKeyExpiredEvent    Không có sự kiện
 có thể được phát        ở ứng dụng
 trong ApplicationContext
```

Repository mapping và `@TimeToLive` **không biến keyspace notifications thành một cơ chế bảo đảm phát toàn Cluster**.

Một số cơ chế Repository còn dùng **shadow copy/phantom copy** giữ bản sao phụ tạm thời để có thể xây dựng event chứa dữ liệu thực thể sau khi khóa chính đã hết hạn. Nhưng điều đó vẫn phụ thuộc vào việc nhận được thông báo ban đầu; bản sao phụ không tự bảo đảm rằng mọi node, mọi instance hay mọi khoảng offline đều có event.

Vì vậy:

- Không dùng `RedisKeyExpiredEvent` như cơ chế duy nhất để xử lý nghiệp vụ không được mất.
- Khi chạy Cluster, phải tìm hiểu phạm vi subscription mà cấu hình Repository/driver thực sự sử dụng.
- Nếu event không đến, cần kiểm tra **cấu hình từng node, topology và listener connection**, không chỉ annotation `@TimeToLive`.
- Theo dõi chi phí bộ nhớ nếu dùng shadow copy trên lượng thực thể TTL lớn.

## 11. Có thể đọc nội dung khóa sau khi nhận expired không?

Với keyevent expired:

```text
Channel: __keyevent@0__:expired
Body:    session:42
```

Thông báo thường chỉ mang **tên khóa**, không mang JSON hoặc nội dung Hash trước khi hết hạn.

Nếu gọi:

```redis
GET session:42
```

sau khi nhận sự kiện, khóa đã bị Redis xem là hết hạn và thường không còn tồn tại.

Điều này ảnh hưởng thiết kế:

- Nếu chỉ cần ghi log tên khóa hoặc xóa một trạng thái phụ đã biết cách tìm, message có thể đủ.
- Nếu cần thông tin như `userId`, `orderId`, `paymentId`, tên khóa phải mang đủ định danh hoặc hệ thống phải lưu metadata ở nơi khác.
- Nếu cần tác dụng nghiệp vụ dựa trên payload cũ, không nên dựa vào `GET` sau `expired`.
- Nếu cần sự kiện bền vững chứa dữ liệu đầy đủ, phải tạo event nghiệp vụ riêng và gửi tới cơ chế lưu trữ phù hợp.

Với Redis Hash, việc gọi `HGETALL` sau khi khóa hết hạn cũng không khôi phục được nội dung đã bị xóa.

## 12. Khi failover và resharding xảy ra

### 12.1. Failover thay đổi primary

Giả sử:

```text
Trước failover:
  A là primary của slot X
  A có replica R
  Listener subscribe A

Sau failover:
  R được nâng thành primary mới
  A ngừng phục vụ slot X
```

Một subscription chỉ gắn địa chỉ A có thể tiếp tục kết nối với node sai vai trò hoặc mất kết nối. Những sự kiện mới của khóa slot X có thể được phát từ R.

Hệ thống cần **phát hiện thay đổi vai trò**, subscribe primary mới và kiểm tra cờ `notify-keyspace-events` đã được cấu hình đúng. Không nên cho rằng kết nối Pub/Sub tự động di chuyển giống cách cluster client xử lý `MOVED`/`ASK` khi truy cập dữ liệu.

### 12.2. Resharding thay đổi owner của khóa

Khi slot được di chuyển từ Primary A sang B:

```text
Trước:
  slot X -> A
  sự kiện khóa K -> A

Sau:
  slot X -> B
  sự kiện khóa K -> B
```

Nếu listener chỉ lắng nghe A, nó có thể bỏ lỡ các sự kiện sau resharding.

### 12.3. Giới hạn khi kết nối chuyển đổi

Ngay cả khi quản lý subscription tự động tốt, giữa lúc phát hiện thay đổi topology và lúc kết nối mới subscribe có thể có một khoảng trống. Thông báo được phát trong khoảng trống có thể **không thể phục hồi** từ Pub/Sub.

Nếu cần không mất sự kiện, phải bổ sung nguồn sự thật và cơ chế xử lý bền vững thay vì trông chờ việc kết nối lại luôn tức thời.

## 13. Trùng sự kiện và cách xử lý an toàn

Một hệ thống có nhiều Spring Boot instance có thể cùng subscribe từng primary:

```text
Primary B phát expired:session:42
            |
      +-----+------+
      |            |
      v            v
 Spring App 1  Spring App 2
      |            |
 xử lý event    xử lý event
```

**Pub/Sub là fan-out:** những subscriber đang đăng ký đều có thể nhận cùng một thông báo.

Với một số mục tiêu, đây chính là điều mong muốn. Ví dụ mọi instance đều có local cache và cần xóa local cache của mình.

Nhưng nếu event làm tăng một bộ đếm chung hoặc gửi email, xử lý cùng một thông báo ở nhiều instance có thể gây tác dụng lặp.

Một số hướng giải quyết:

- Thiết kế callback **idempotent**, ví dụ xóa local cache theo key.
- Nếu một công việc chỉ được xử lý một lần, dùng cơ chế phân công công việc hoặc idempotency bền vững.
- Không coi một keyevent Redis là một ID sự kiện duy nhất có thể tin cậy trong mọi lần cập nhật. Tên khóa và tên loại event không tự tạo unique event ID.
- Không dùng `SETNX` chống trùng đơn giản để thay thế giao dịch bền vững nếu nghiệp vụ quan trọng và lỗi giữa các bước có thể gây mất xử lý.

**Tình huống quan trọng:** listener bị mất một thông báo thì không thể “sửa” bằng cách bảo đảm mỗi thông báo đã nhận chỉ xử lý một lần. Tránh mất và tránh trùng là **hai vấn đề khác nhau**.

## 14. Vận hành nhiều node: cấu hình, quan sát, cảnh báo

### 14.1. Kiểm tra cấu hình trên từng node

Một quy trình vận hành nên kiểm tra:

```text
Node A: notify-keyspace-events có Ex?
Node B: notify-keyspace-events có Ex?
Node C: notify-keyspace-events có Ex?
Node mới sau failover: cấu hình có đúng?
```

Nếu chỉ một node chưa bật `Ex`, bạn có thể thấy **tỷ lệ nhận expired thấp hoặc không đều theo slot**, dù listener của ứng dụng chạy bình thường.

### 14.2. Các metric đáng có

| Metric | Giúp trả lời |
|---|---|
| Số node primary dự kiến | Cụm hiện có bao nhiêu nơi phát thông báo cần theo dõi? |
| Số subscription đang hoạt động | Ứng dụng đã kết nối đủ chưa? |
| Số sự kiện nhận theo node | Node nào đang phát và node nào im lặng bất thường? |
| Số reconnect/subscription errors | Có gián đoạn kết nối không? |
| Độ trễ xử lý callback | Listener có bị nghẽn không? |
| Số handler failures | Có lỗi nghiệp vụ khi xử lý sự kiện không? |
| Số sự kiện theo loại `expired`, `del`, `evicted` | Có nhận đúng loại mong muốn không? |
| Số instance cùng xử lý event | Có fan-out hoặc xử lý lặp ngoài ý muốn không? |
| Sai lệch giữa trạng thái nguồn và trạng thái phụ | Có dấu hiệu event bị mất không? |

Không được chỉ nhìn `subscriber connected = true` để kết luận “đã bao phủ mọi slot”.

### 14.3. Khả năng quan sát từ Redis

Một vài lệnh hỗ trợ điều tra:

```redis
CONFIG GET notify-keyspace-events
CLUSTER SHARDS
CLUSTER NODES
PUBSUB NUMPAT
INFO clients
INFO stats
```

`PUBSUB NUMPAT` phản ánh số lượng pattern subscriptions mà Redis ghi nhận theo phạm vi hoạt động của lệnh/nút. Nó **không** chứng minh mọi loại keyevent được nhận đủ và xử lý nghiệp vụ thành công.

Cần đo ở **ứng dụng** vì Redis không biết handler Spring đã thực hiện xong tác vụ hay chưa.

### 14.4. Đừng dùng keyspace notifications thay cho kiểm kê dữ liệu

Không nên xây bộ đếm “số phiên đang hoạt động” chỉ bằng cách:

```text
+1 khi tạo session
-1 khi nhận expired
```

và cho rằng nó luôn đúng. Một event có thể bị mất, trùng qua nhiều instance hoặc khóa có thể bị xóa theo lý do khác. Nếu bộ đếm là quyết định nghiệp vụ, cần thiết kế nguồn dữ liệu nhất quán và quy trình đối soát.

Thay vì quét `KEYS *` trên production để kiểm kê một cách tùy tiện, có thể dùng cấu trúc dữ liệu phụ, thống kê có giới hạn, quy trình đối soát theo batch hoặc lưu thông tin hợp lệ ở database.

## 15. Những tình huống không nên dùng event làm nguồn sự thật

### 15.1. Tác vụ quan trọng phải chạy đúng lúc hết hạn

Một ví dụ: “khi lệnh thanh toán hết hạn sau 15 phút, phải hoàn tiền chắc chắn”. Sự kiện `expired` là tín hiệu **không bền vững** và không phát đúng thời điểm TTL tuyệt đối, nên không đủ để bảo đảm quy trình hoàn tiền.

Lựa chọn phù hợp hơn có thể gồm:

- Lưu `expiresAt` trong database.
- Dùng công việc lịch biểu hoặc hàng đợi bền vững.
- Worker định kỳ tìm những bản ghi quá hạn chưa xử lý.
- Thực hiện tác dụng nghiệp vụ idempotent và lưu trạng thái đã hoàn tất.
- Dùng Redis keyevent như tín hiệu tăng tốc, không phải điều kiện bắt buộc duy nhất.

### 15.2. Nhiều dịch vụ cần nhận thông báo khi đang offline

Pub/Sub thông thường không giữ lịch sử. Nếu dịch vụ cần đọc lại khi bật lên, nên xem xét Redis Streams hoặc một message broker/queue có lưu thông điệp và cơ chế xác nhận phù hợp.

### 15.3. Phân tích theo thứ tự sự kiện xuyên Cluster

Event từ các node khác nhau không có một thứ tự tổng thể có thể tin cậy cho mọi tác vụ. Nếu quyết định phụ thuộc thứ tự toàn hệ thống, cần có phiên bản/trình tự nghiệp vụ trong nguồn dữ liệu hoặc một cơ chế sắp xếp riêng.

### 15.4. Cần lấy lại giá trị cũ của khóa

Sau expired, payload đã biến mất. Nếu nghiệp vụ cần payload, đừng thiết kế phải `GET` nó sau khi nhận keyevent; hãy lưu metadata hoặc phát event nghiệp vụ trước khi xóa dữ liệu.

## 16. So sánh một số phương án thiết kế

| Giải pháp | Ưu điểm | Giới hạn |
|---|---|---|
| Subscribe một node | Đơn giản để thử nghiệm | Bỏ lỡ keyevents phát từ node khác trong Cluster |
| Subscribe mọi primary | Bao phủ các node đang phát khi kết nối ổn định | Không có replay/ACK; cần xử lý failover, resharding |
| Spring `RedisMessageListenerContainer` | Quản lý listener qua Spring | Phạm vi Cluster cần được xác minh ở driver/cấu hình |
| Spring Data Redis Repository expiry events | Tích hợp TTL với ánh xạ thực thể | Vẫn phụ thuộc Redis notifications; không bảo đảm đầy đủ toàn cụm |
| Redis Streams | Lưu event và hỗ trợ đọc lại/consumer group | Cần producer chủ động ghi sự kiện, retention và retry |
| Database + job đối soát | Nguồn sự thật và xử lý bền vững | Độ phức tạp, độ trễ theo chu kỳ, chi phí truy vấn |
| Kết hợp notifications + job đối soát | Có thể phản ứng nhanh và tự sửa khi bỏ lỡ | Phải thiết kế idempotency và giám sát cả hai đường |

Một kiến trúc thường phù hợp với việc xử lý quan trọng:

```text
Database (expiresAt, processingState)
               |
               +------> Redis TTL
               |             |
               |        keyevent (tín hiệu nhanh)
               |             |
               v             v
         Scheduled job   Listener online
               |             |
               +------v------+
                      |
               Idempotent handler
                      |
             Cập nhật processingState
```

Nếu notification bị mất, job đối soát vẫn có thể xử lý phần công việc quá hạn. Nếu nhận được notification, handler có thể bắt đầu sớm hơn. **Database/nguồn có thẩm quyền quyết định trạng thái**, không phải việc ứng dụng có nghe thấy keyevent hay không.

## 17. Bài tập thực hành

### Bài tập A: Phân biệt keyspace và keyevent

Bật:

```redis
CONFIG SET notify-keyspace-events KEx
```

Mở hai subscriber trên cùng node:

```redis
PSUBSCRIBE __keyspace@0__:demo:*
```

và:

```redis
PSUBSCRIBE __keyevent@0__:expired
```

Tạo khóa:

```redis
SET demo:session:42 active EX 3
```

Quan sát: keyspace channel có **body là `expired`**, keyevent channel có **body là tên khóa**.

### Bài tập B: Cấu hình thiếu trên một primary

Trong Redis Cluster dành cho thử nghiệm, bật `Ex` chỉ trên một primary và mở subscriber trực tiếp ở các primary. Tạo các khóa thuộc nhiều slot. Quan sát rằng những node không bật cấu hình sẽ không phát thông báo như mong muốn.

Sau đó bật cấu hình đúng trên các primary còn lại và lặp lại. Đừng thực hiện thay đổi cấu hình kiểu này trên production nếu chưa được phê duyệt vận hành.

### Bài tập C: Subscription thiếu một node

Bật thông báo trên mọi primary nhưng chỉ subscribe một node. Tạo khóa thuộc một primary khác bằng cluster-aware `redis-cli -c`. Quan sát việc không nhận đủ keyevents qua subscriber đơn lẻ.

Thêm subscription trực tiếp tới node còn lại và lặp lại.

### Bài tập D: Phân biệt expired và del

Theo dõi riêng kênh expired. Tạo khóa có TTL dài rồi chủ động xóa bằng `DEL`. Xác định vì sao listener chỉ nghe `expired` không nhận thông báo `expired` cho thao tác này.

Nếu muốn thấy `del`, mở cấu hình và channel phù hợp trong môi trường thử nghiệm.

### Bài tập E: Listener mất kết nối

Cho ứng dụng listener dừng, để một số khóa hết hạn, rồi khởi động lại. Quan sát rằng Pub/Sub không phát lại những expired events đã xảy ra khi listener offline. Từ đó đề xuất phương án đối soát dựa trên `expiresAt` nếu tác vụ quan trọng.

### Bài tập F: Thay đổi topology

Trong Cluster thử nghiệm có khả năng reshard/failover, quan sát danh sách primary trước và sau thao tác. Kiểm tra rằng hệ thống subscription đã chuyển sang node mới. Không sử dụng quy trình này để gây failover tùy tiện trên production.

## 18. Câu hỏi tự kiểm tra

**1. Redis Cluster có tự chuyển keyevent notification từ mọi node về một subscriber kết nối tới node A không?**

Không. Keyspace/keyevent notifications mang phạm vi nút phát; một subscription chỉ ở A không bảo đảm nhận được sự kiện từ B hoặc C.

**2. Tên channel `__keyevent@0__:expired` cho biết điều gì?**

Đây là kênh keyevent cho sự kiện `expired` trên logical database 0. Body thường là tên khóa vừa bị Redis xóa do hết hạn.

**3. Tên channel `__keyspace@0__:session:42` khác gì?**

Đây là kênh theo khóa `session:42`; body mang tên sự kiện, chẳng hạn `expired`.

**4. Chỉ `CONFIG SET notify-keyspace-events Ex` ở một node có đủ cho Cluster không?**

Không. Cần bật trên các node phát sự kiện tương ứng và theo dõi cấu hình khi có primary mới hoặc failover.

**5. Ứng dụng dùng cluster-aware RedisConnectionFactory, vậy listener chắc chắn nhận hết mọi expired event?**

Không thể suy ra như vậy. Cần xác minh thực tế những node được subscribe và cách driver xử lý Pub/Sub trong topology cụ thể.

**6. Event `expired` được phát đúng tại mili giây TTL đạt 0 không?**

Không được bảo đảm. Redis phát khi thực sự xóa khóa hết hạn, có thể trễ hơn mốc TTL.

**7. Tại sao không nên gọi GET để lấy payload sau khi nhận expired?**

Khóa đã bị xóa hoặc được xem là hết hạn; thông báo keyevent thường chỉ có tên khóa, không có nội dung cũ.

**8. Khi failover chuyển slot sang node mới, listener phải lưu ý điều gì?**

Cần cập nhật danh sách primary và đăng ký trên node mới, đồng thời chấp nhận khả năng mất sự kiện trong khoảng chuyển đổi.

**9. Nhiều Spring Boot instance cùng subscribe có thể nhận cùng thông báo không?**

Có. Pub/Sub phát cho subscriber đang đăng ký; handler cần an toàn khi chạy lặp hoặc dùng cơ chế phân công khác nếu chỉ được xử lý một lần.

**10. Khi nào nên dùng Redis Streams hoặc database job thay cho việc chỉ dựa vào keyspace notifications?**

Khi công việc quan trọng không được mất, cần retry/ACK, phải xử lý khi subscriber offline hoặc có yêu cầu đối soát bền vững.

## 19. Ghi nhớ

- **Keyspace/keyevent notifications là Redis Pub/Sub phát trực tiếp**, không có lịch sử, ACK hay phát lại khi listener offline.
- Trong **Redis Cluster**, thông báo khóa có **phạm vi node-local**; subscriber chỉ ở một node không tự nhận toàn bộ sự kiện của cụm.
- **Bật `notify-keyspace-events` trên các node liên quan**, và kiểm tra mỗi node sau failover/resharding.
- **`__keyspace@0__:<key>` mang message là tên sự kiện**; **`__keyevent@0__:<event>` mang message là tên khóa**.
- **TTL đạt hạn không đồng nghĩa event xuất hiện đúng lúc đó**. `expired`, `del` và `evicted` là các loại sự kiện khác nhau.
- Với Spring Data Redis, dùng **`RedisMessageListenerContainer`** để quản lý listener, nhưng phải **xác minh phạm vi kết nối/subscription thực tế trong Cluster**.
- Nếu cần xử lý không mất dữ liệu, dùng notifications làm tín hiệu hỗ trợ và kết hợp nguồn sự thật, job đối soát hoặc cơ chế thông điệp bền vững phù hợp.

### Tài liệu tham khảo

- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/).
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- [Redis — Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/).
- [Redis — CONFIG SET](https://redis.io/docs/latest/commands/config-set/).
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/).
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/).
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html).
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html).
