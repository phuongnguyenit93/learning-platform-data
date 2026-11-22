# Phân biệt Redis đơn nút, replication, Sentinel và Cluster

Khi đưa Redis vào ứng dụng Spring Data Redis, bốn thuật ngữ **đơn nút (standalone)**, **replication**, **Sentinel** và **Cluster** thường bị xem như bốn cách triển khai tương đương. Thực tế, chúng giải quyết những nhu cầu khác nhau:

- **Redis đơn nút**: một Redis server nắm toàn bộ dữ liệu và phục vụ cả đọc lẫn ghi.
- **Replication**: sao chép dữ liệu từ một nút primary sang các replica, chủ yếu để dự phòng và phân tải đọc.
- **Redis Sentinel**: giám sát một nhóm primary–replica, phát hiện sự cố và điều phối chuyển đổi primary tự động.
- **Redis Cluster**: phân mảnh khóa ra nhiều primary để mở rộng dung lượng và khả năng xử lý; mỗi primary có thể có replica để tự động thay thế khi lỗi.

Điểm mấu chốt: **replication là cơ chế sao chép, Sentinel là cơ chế quản lý tính sẵn sàng cao, còn Cluster bổ sung cơ chế phân mảnh dữ liệu**. Một hệ thống Sentinel dùng replication; một hệ thống Cluster cũng thường dùng replication. Các thuật ngữ này không phải là bốn mức “nâng cấp” loại trừ lẫn nhau.

## 1. Bức tranh tổng quan

| Tiêu chí | Đơn nút | Replication thuần | Sentinel + replication | Redis Cluster |
|---|---|---|---|---|
| Phân bố dữ liệu | Một server giữ toàn bộ key | Primary và replica giữ bản sao cùng tập key | Primary và replica giữ bản sao cùng tập key | Nhiều primary giữ **các phần key khác nhau** |
| Điểm nhận ghi | Một server | Primary | Primary đang được Sentinel công nhận | Primary sở hữu hash slot của key |
| Khả năng mở rộng ghi | Giới hạn bởi một nút | Vẫn giới hạn bởi primary | Vẫn giới hạn bởi primary | Có thể phân tải ghi qua nhiều primary |
| Khả năng mở rộng đọc | Giới hạn bởi một nút | Có thể đọc từ replica | Có thể đọc từ replica khi client được cấu hình | Có thể đọc từ primary/replica theo cấu hình client |
| Tự động chuyển primary khi lỗi | Không | Không | Có, nếu đủ điều kiện quorum và replica phù hợp | Có, nếu replica và phần lớn primary còn liên lạc |
| Phát hiện địa chỉ primary mới | Không cần | Ứng dụng/cấu hình bên ngoài tự xử lý | Client hỏi Sentinel | Client hiểu sơ đồ slot và chuyển hướng Redis Cluster |
| Thành phần điều phối | Không | Không | Các tiến trình Sentinel riêng | Các Redis node tự trao đổi thông tin Cluster |
| Phù hợp nhất | Phát triển, thử nghiệm, workload nhỏ | Cần bản sao hoặc thêm khả năng đọc | Cần HA cho tập dữ liệu không cần sharding | Cần sharding và HA trên nhiều primary |

**Tính sẵn sàng cao (HA)** nghĩa là hệ thống có thể khôi phục phục vụ sau lỗi nút với ít can thiệp; điều đó **không đồng nghĩa với không mất dữ liệu**. Redis thường sao chép **bất đồng bộ**, nên có thể mất một số ghi mới nhất khi primary hỏng trước khi replica nhận được chúng.

## 2. Redis đơn nút (standalone)

~~~text
Spring Boot / Spring Data Redis
             |
             v
       Redis :6379
       [toàn bộ key]
~~~

Một tiến trình Redis nhận mọi lệnh và chứa toàn bộ không gian khóa, chẳng hạn `user:1`, `product:27` và `cart:5`. Ứng dụng chỉ cần biết một địa chỉ host/port.

Ví dụ:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
# PONG

redis-cli -h 127.0.0.1 -p 6379 SET user:1 "An"
redis-cli -h 127.0.0.1 -p 6379 GET user:1
~~~

**Ưu điểm:** đơn giản, ít tài nguyên, dễ vận hành và dễ gỡ lỗi. **Giới hạn:** một nút là điểm lỗi duy nhất; việc nâng cấp hoặc khởi động lại nút đó có thể khiến dịch vụ tạm ngừng. Dung lượng bộ nhớ và tốc độ xử lý ghi phụ thuộc chủ yếu vào một máy.

Có thể bật RDB hoặc AOF để Redis khôi phục dữ liệu sau khi khởi động lại. Tuy nhiên, **persistence không tự tạo replica, không tự khôi phục khả năng phục vụ trong lúc nút đang hỏng và không thay thế hệ thống backup**.

## 3. Replication: một primary, nhiều bản sao

~~~text
                      ghi
Ứng dụng --------------------------> Primary
                                       |
                            sao chép bất đồng bộ
                              /                \
                             v                  v
                         Replica A          Replica B
                       (đọc tùy chọn)     (đọc tùy chọn)
~~~

Mọi dữ liệu do primary quản lý được truyền đến replica. Redis thường dùng tên **primary/replica**; tài liệu và cấu hình cũ đôi khi dùng **master/slave**. Trong cấu hình mặc định, replica không cho phép ghi trực tiếp.

### Replication diễn ra thế nào?

1. Replica kết nối đến primary bằng cấu hình `replicaof`.
2. Khi đồng bộ lần đầu hoặc không thể đồng bộ tăng dần, replica nhận dữ liệu nền và các thay đổi tiếp theo từ primary.
3. Khi kết nối ổn định, các lệnh làm thay đổi dữ liệu được primary truyền tiếp cho replica.
4. Sau mất kết nối ngắn, cơ chế **PSYNC** có thể đồng bộ phần còn thiếu nếu backlog và lịch sử replication vẫn phù hợp; nếu không, cần đồng bộ đầy đủ.

Ví dụ trên máy sẽ làm replica:

~~~conf
# redis.conf của replica
replicaof 10.0.0.11 6379
replica-read-only yes
~~~

Hoặc thiết lập khi server đang chạy:

~~~bash
redis-cli -h 10.0.0.12 -p 6379 REPLICAOF 10.0.0.11 6379

# Xem role, primary và trạng thái replica
redis-cli -h 10.0.0.11 -p 6379 INFO replication
redis-cli -h 10.0.0.12 -p 6379 INFO replication
~~~

Replica có thể phục vụ truy vấn đọc và giảm tải cho primary, nhưng kết quả đọc **có thể cũ hơn dữ liệu vừa ghi** do độ trễ sao chép. Nếu một request ghi vào primary rồi ngay lập tức đọc ở replica, ứng dụng có thể chưa thấy giá trị mới. Những luồng cần *read-after-write consistency* nên cân nhắc đọc từ primary.

### Khi primary bị lỗi

Replication thuần **không tự bầu primary mới**. Người vận hành hoặc một công cụ bên ngoài phải quyết định replica nào được nâng cấp, ngăn primary cũ tiếp tục nhận ghi và chuyển ứng dụng sang địa chỉ mới. Chẳng hạn, sau khi đã cô lập primary cũ:

~~~bash
# Chỉ là thao tác minh họa cho failover thủ công
redis-cli -h 10.0.0.12 -p 6379 REPLICAOF NO ONE
~~~

Nếu nâng cấp replica trong khi primary cũ còn nhận ghi, có thể xảy ra hai primary cùng phục vụ các thay đổi khác nhau (**split brain**). Do replication bất đồng bộ, replica được nâng cấp cũng có thể thiếu các ghi cuối cùng của primary cũ.

**Khi chọn replication thuần:** cần bản sao phục vụ backup/đọc hoặc một hệ thống khác đã đảm nhiệm việc chuyển đổi primary. Nếu mục tiêu là failover tự động, nên xét Sentinel hoặc Cluster.

## 4. Sentinel: tự động giám sát và chuyển primary

Sentinel **không lưu dữ liệu ứng dụng và không làm proxy chuyển tiếp các lệnh GET/SET**. Sentinel là các tiến trình giám sát, trao đổi đánh giá lỗi, chọn replica lên làm primary và thông báo cấu hình primary mới cho client biết qua cơ chế khám phá dịch vụ.

~~~text
                    Spring Data Redis
                        |
             hỏi Sentinel: primary ở đâu?
                        |
          +-------------+-------------+
          |             |             |
      Sentinel 1    Sentinel 2    Sentinel 3
          \             |             /
           \     theo dõi, bỏ phiếu   /
            \           |            /
                        v
                    Primary A
                   /         \
                Replica B   Replica C

Nếu A lỗi và đủ điều kiện failover:
B (hoặc C) trở thành primary; Sentinel cập nhật thông tin.
~~~

Trong ví dụ, các tiến trình Sentinel cần đặt ở những miền lỗi đủ độc lập để sự cố một máy không làm tất cả Sentinel mất khả năng quyết định. Triển khai **3 Sentinel** với **quorum 2** là một cấu hình phổ biến. Replica và Sentinel có thể chạy trên cùng máy vật lý trong môi trường phù hợp, nhưng cần tính đến mất đồng thời nhiều tiến trình trên một máy.

### Các bước failover

1. Một Sentinel không nhận được phản hồi đúng hạn từ primary và đánh dấu **SDOWN** (*subjectively down*: chính Sentinel đó nghi ngờ lỗi).
2. Đủ số Sentinel đồng ý thì primary được đánh dấu **ODOWN** (*objectively down*). Ngưỡng đồng ý là giá trị **quorum** được cấu hình cho nhóm primary.
3. Các Sentinel bầu một Sentinel điều phối failover. Việc ủy quyền failover còn đòi hỏi **đa số tổng số Sentinel được biết đến**; đạt quorum phát hiện ODOWN chưa đủ để đảm bảo thực hiện được failover.
4. Sentinel điều phối chọn một replica đủ điều kiện, nâng nó thành primary và điều chỉnh các replica còn lại theo primary mới.
5. Client hỗ trợ Sentinel tìm địa chỉ primary mới và kết nối lại.

Ví dụ `sentinel.conf` tối giản cho một Sentinel:

~~~conf
port 26379
sentinel monitor mymaster 10.0.0.11 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000
~~~

Ở đây, `mymaster` là **tên logic** của nhóm primary, `10.0.0.11:6379` là địa chỉ primary ban đầu, `2` là quorum để xác nhận ODOWN. Ba Sentinel được cấu hình giám sát cùng nhóm này; các tham số thời gian là ví dụ minh họa, cần điều chỉnh theo hạ tầng thực tế.

Có thể xem thông tin từ Sentinel:

~~~bash
redis-cli -h sentinel-1 -p 26379 SENTINEL get-master-addr-by-name mymaster
redis-cli -h sentinel-1 -p 26379 SENTINEL replicas mymaster
redis-cli -h sentinel-1 -p 26379 SENTINEL CKQUORUM mymaster
~~~

### Sentinel giải quyết và không giải quyết điều gì?

- **Có:** phát hiện lỗi primary, bầu replica thay thế, cho client tìm primary hiện tại.
- **Không:** chia tập key lên nhiều primary để tăng tổng dung lượng hoặc năng lực ghi.
- **Không đảm bảo:** mọi ghi trước sự cố đều còn nguyên. Primary có thể đã trả kết quả thành công trước khi replica nhận lệnh.
- **Không đảm bảo:** ứng dụng không hề gặp lỗi trong lúc failover. Các kết nối đang mở có thể lỗi, timeout hoặc cần retry.

Sentinel thường là lựa chọn hợp lý khi một primary vẫn đủ sức chứa và xử lý dữ liệu nhưng ứng dụng cần tự động phục hồi sau lỗi nút.

## 5. Redis Cluster: sharding và failover phân tán

Redis Cluster phân dữ liệu thành **16.384 hash slot**, đánh số từ `0` đến `16383`. Mỗi key thuộc một slot, tính theo quy tắc chính:

~~~text
slot = CRC16(key) mod 16384
~~~

Redis Cluster sử dụng phần **hash tag** bên trong cặp ngoặc nhọn hợp lệ nếu key có hash tag (xem phần dưới). Các slot được chia cho nhiều primary; mỗi primary nắm một phần dữ liệu. Replica sao chép dữ liệu của **primary tương ứng**, không phải toàn bộ dữ liệu Cluster.

~~~text
                    Cluster-aware client
                         /    |     \
                        v     v      v
                   Primary A  B       C
                    slots    slots   slots
                    0..5460  5461.. 10923..
                             10922   16383
                       |      |       |
                       v      v       v
                    Replica  Replica  Replica
                       A1      B1      C1
~~~

Các khoảng slot trên chỉ để minh họa một phân bổ ba primary. Khi thêm/bớt nút, Redis có thể **di chuyển slot và key giữa các primary**; số slot vẫn là 16.384.

### Cách client tìm đúng primary

1. Client hỗ trợ Redis Cluster biết một số địa chỉ seed node.
2. Client lấy thông tin phân bổ slot và gửi lệnh đến primary sở hữu slot của key.
3. Khi thông tin slot đã thay đổi, Redis có thể trả **MOVED** để chỉ sang nút sở hữu slot hiện tại.
4. Trong lúc di chuyển slot, Redis có thể trả **ASK** để hướng lệnh tạm thời đến nút nhận; client cần xử lý theo giao thức.
5. Client cập nhật sơ đồ slot và tiếp tục định tuyến.

Vì thế, đưa một client chỉ hiểu standalone vào Redis Cluster thường dẫn đến lỗi chuyển hướng hoặc lệnh không hoạt động như mong đợi. Spring Data Redis cần một driver và cấu hình **Cluster-aware**, ví dụ Lettuce với `spring.data.redis.cluster.nodes`.

### Hash slot và giới hạn thao tác nhiều key

Giả sử có hai key:

~~~text
cart:{user42}:items
cart:{user42}:total
~~~

Cả hai dùng hash tag `{user42}`, nên luôn được tính vào **cùng một slot**. Điều này hữu ích cho lệnh hoặc Lua script cần thao tác nhiều key trên cùng nút.

Ngược lại:

~~~bash
# Lệnh nhiều key trên các slot khác nhau có thể bị Redis Cluster từ chối
MGET user:1 user:2
# (error) CROSSSLOT Keys in request don't hash to the same slot
~~~

Đây là hành vi của lệnh nhiều key **trực tiếp trên Redis Cluster**. Một số API của thư viện có thể tự tách các thao tác để thực thi trên nhiều nút, nhưng không được suy ra rằng việc tách đó sẽ giữ tính nguyên tử. Đối với transaction, script hoặc thao tác nhiều key cần tính nguyên tử, hãy thiết kế key cùng slot và xác nhận giới hạn của API cụ thể.

Không nên dùng **cùng một hash tag cho tất cả key**: làm vậy sẽ dồn dữ liệu và lưu lượng vào một slot, mất lợi thế phân tải của Cluster.

### Ví dụ dựng Cluster

Trên từng Redis node, cấu hình tối thiểu có dạng:

~~~conf
port 6379
cluster-enabled yes
cluster-config-file nodes.conf
cluster-node-timeout 5000
~~~

Sau khi khởi động **6 Redis node** độc lập, ví dụ sau tạo Cluster với 3 primary và một replica cho mỗi primary:

~~~bash
redis-cli --cluster create \
  10.0.0.11:6379 10.0.0.12:6379 10.0.0.13:6379 \
  10.0.0.14:6379 10.0.0.15:6379 10.0.0.16:6379 \
  --cluster-replicas 1
~~~

Thử truy cập bằng chế độ hiểu chuyển hướng Cluster và xem trạng thái:

~~~bash
redis-cli -c -h 10.0.0.11 -p 6379 SET product:42 active
redis-cli -c -h 10.0.0.11 -p 6379 GET product:42

redis-cli -h 10.0.0.11 -p 6379 CLUSTER INFO
redis-cli -h 10.0.0.11 -p 6379 CLUSTER SHARDS
redis-cli --cluster check 10.0.0.11:6379
~~~

Đây là cấu hình minh họa. Khi triển khai thực tế còn phải cân nhắc xác thực, TLS, persistence, phân bố máy/vùng lỗi, địa chỉ node tự quảng bá và mạng phục vụ giao tiếp giữa các Redis node. Mọi địa chỉ node mà Cluster quảng bá phải có thể truy cập từ ứng dụng, nếu không client có thể gặp lỗi sau khi nhận MOVED/đọc sơ đồ slot.

### Khi một primary của Cluster bị lỗi

Replica của primary đó có thể được bầu lên thay thế nếu đủ điều kiện và phần lớn các primary trong Cluster còn liên lạc để ủy quyền failover. Phần slot bị ảnh hưởng có thể tạm gián đoạn trong lúc chuyển đổi. Nếu slot mất primary mà không có replica phù hợp, các key của slot đó không còn phục vụ bình thường; tùy chính sách bao phủ slot, tác động có thể rộng hơn.

Cluster cung cấp khả năng sharding và failover, **không tự biến replication bất đồng bộ thành ghi đồng bộ hay bảo đảm không mất dữ liệu**. Cluster thường phù hợp khi một primary không còn đủ RAM, lưu lượng ghi hoặc nhu cầu phân tách tải, và ứng dụng chấp nhận quy tắc phân mảnh theo slot.

## 6. Cấu hình tương ứng trong Spring Data Redis

Các ví dụ dưới đây minh họa quy ước cấu hình của **Spring Boot 3.x** với Spring Data Redis và Lettuce. Mỗi khối là **một phương án độc lập**; không ghép cả ba khối cấu hình vào cùng một ứng dụng. Hostname chỉ mang tính ví dụ; thay bằng địa chỉ thực tế.

### 6.1. Standalone hoặc replication nhưng chỉ kết nối primary cố định

~~~yaml
spring:
  data:
    redis:
      host: redis-primary.internal
      port: 6379
      timeout: 2s
~~~

Với replication thuần, cấu hình này vẫn trỏ đến một primary cụ thể. Nếu primary thay đổi sau thao tác failover thủ công, ứng dụng cần nhận địa chỉ mới thông qua cập nhật cấu hình hoặc cơ chế bên ngoài.

### 6.2. Sentinel

~~~yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
      timeout: 2s
~~~

`master` là **tên nhóm Redis trong Sentinel**, không phải hostname. Client liên hệ các Sentinel để tìm primary đang hoạt động. Cần cấu hình đúng thông tin xác thực đối với Redis và, nếu được bảo vệ riêng, đối với các Sentinel; tài khoản/mật khẩu Sentinel có thể khác Redis data node.

### 6.3. Redis Cluster

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-1.internal:6379
          - redis-2.internal:6379
          - redis-3.internal:6379
      timeout: 2s
~~~

Danh sách `nodes` là các **seed node** để client khám phá Cluster, không nhất thiết liệt kê mọi node. Client sẽ lấy phân bố slot và cập nhật tuyến truy cập khi Cluster thay đổi. Các seed node cần có thể kết nối được, và các địa chỉ quảng bá của toàn Cluster cũng phải truy cập được từ ứng dụng.

### 6.4. Mã Spring Data Redis có khác nhau không?

Với thao tác **một key**, lập trình viên thường dùng cùng một API bất kể topology:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VisitCounter {
    private final StringRedisTemplate redis;

    public VisitCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(String userId) {
        return redis.opsForValue().increment("visits:" + userId);
    }
}
~~~

Khi thay đổi topology, khác biệt chủ yếu nằm ở **RedisConnectionFactory, driver và địa chỉ khám phá nút**. Tuy nhiên, lựa chọn topology vẫn ảnh hưởng tới hành vi ứng dụng:

- **Đọc từ replica:** mặc định không nên giả định lệnh đọc sẽ được gửi tới replica. Muốn phân tải đọc, cần cấu hình chính sách đọc phù hợp trong Lettuce và chấp nhận khả năng dữ liệu chưa kịp đồng bộ.
- **Retry và timeout:** trong failover, lệnh có thể timeout hoặc kết nối bị ngắt. Retry phải phù hợp tính chất lệnh; với thao tác không idempotent, không thể tự động suy ra lần ghi trước đã thất bại hay thành công.
- **Lệnh nhiều key:** với Cluster cần lưu ý slot, transaction, Lua script và các API có thể thực thi trên nhiều nút.
- **Cache/TTL:** các lệnh cho từng key vẫn có thể hoạt động bình thường, nhưng phải đánh giá hành vi khi failover, sơ đồ slot thay đổi và dữ liệu replica chưa đồng bộ.
- **Bảo mật:** cấu hình xác thực, ACL và TLS theo mô hình hạ tầng; một ví dụ YAML tối giản không đại diện cho cấu hình bảo mật production.

Nếu tự tạo `LettuceConnectionFactory` bằng Java thay vì để Spring Boot tự cấu hình, cần chọn đúng `RedisStandaloneConfiguration`, `RedisSentinelConfiguration` hoặc `RedisClusterConfiguration`. Chỉ đổi danh sách host mà giữ loại cấu hình sai sẽ không đủ.

## 7. Minh họa bốn tình huống hỏng primary

| Tình huống | Redis sẽ xảy ra gì? | Ứng dụng cần làm gì? |
|---|---|---|
| Standalone: Redis server dừng | Không có server khác phục vụ dữ liệu | Chờ sửa/khởi động lại, hoặc chuyển sang hệ thống phục hồi thủ công |
| Replication: primary dừng, replica còn chạy | Replica vẫn có bản sao, nhưng chưa tự nhận vai trò primary | Cô lập primary cũ, nâng replica, cập nhật tuyến ghi; kiểm tra phần dữ liệu chưa đồng bộ |
| Sentinel: primary dừng | Nếu đạt quorum/đa số và có replica thích hợp, Sentinel tự chọn primary mới | Client Sentinel khám phá lại primary, xử lý lỗi kết nối tạm thời |
| Cluster: primary của một nhóm slot dừng | Nếu có replica phù hợp và đủ điều kiện failover, replica tiếp quản slot | Client Cluster cập nhật sơ đồ slot/chuyển hướng, xử lý thời gian gián đoạn |

Hai khái niệm cần phân biệt khi đánh giá phương án:

- **RTO (Recovery Time Objective):** thời gian gián đoạn có thể chấp nhận trước khi dịch vụ hoạt động lại. Sentinel và Cluster giúp tự động hóa phục hồi nhưng không có một thời gian cố định bảo đảm cho mọi hạ tầng.
- **RPO (Recovery Point Objective):** lượng dữ liệu mới nhất có thể mất. Vì replication mặc định bất đồng bộ, cả Sentinel và Cluster đều có rủi ro mất ghi khi failover.

Lệnh `WAIT` có thể yêu cầu primary đợi một số replica xác nhận đã nhận dữ liệu, giúp giảm cửa sổ mất ghi trong một số trường hợp. Tuy nhiên, **`WAIT` không biến Redis thành hệ thống đồng thuận ghi bền vững**; vẫn phải đánh giá persistence, hành vi failover và yêu cầu nhất quán của ứng dụng.

## 8. Chọn mô hình nào cho dự án?

**Trường hợp A — học Redis hoặc ứng dụng nhỏ, chấp nhận downtime:** bắt đầu bằng standalone. Đây cũng là mô hình đơn giản nhất để phát triển và chạy kiểm thử cục bộ.

**Trường hợp B — dữ liệu vẫn vừa một primary nhưng cần thêm nút đọc/bản sao:** dùng replication. Cần thiết kế rõ việc đọc từ replica có thể nhận giá trị cũ và cách chuyển primary khi gặp sự cố.

**Trường hợp C — dữ liệu vẫn vừa một primary và yêu cầu khôi phục tự động:** dùng replication + Sentinel. Bố trí đủ Sentinel ở các miền lỗi độc lập, kiểm tra quorum và dùng kết nối Sentinel-aware từ Spring Data Redis.

**Trường hợp D — dữ liệu hoặc lưu lượng ghi vượt khả năng một primary:** dùng Redis Cluster. Thiết kế key theo slot, dự phòng replica cho mỗi primary, cấu hình client Cluster-aware và đánh giá khả năng chịu lỗi từng nhóm slot.

### Các ngộ nhận cần tránh

1. **“Có replica là tự failover.”** Sai: replication thuần sao chép dữ liệu, không điều phối bầu primary.
2. **“Sentinel làm Redis phân tán dữ liệu.”** Sai: Sentinel giữ topology primary–replica của một tập dữ liệu, không sharding.
3. **“Cluster luôn có bản sao.”** Sai: Cluster có thể chạy nhiều primary mà không có replica; khi đó không có nút để tự tiếp quản primary đã mất.
4. **“Sentinel/Cluster không bao giờ mất ghi.”** Sai: bản sao bất đồng bộ vẫn tạo cửa sổ mất dữ liệu.
5. **“Spring Data Redis tự hiểu mọi topology chỉ bằng host/port.”** Sai: standalone, Sentinel và Cluster cần cấu hình kết nối tương ứng.
6. **“Lệnh nhiều key trong Cluster hoạt động giống standalone.”** Sai: các ràng buộc hash slot và tính nguyên tử phải được tính vào thiết kế.
7. **“Bật AOF/RDB là có HA.”** Sai: persistence để phục hồi dữ liệu của nút; HA cần tổ chức nút và cơ chế chuyển đổi phù hợp.

## 9. Ghi nhớ bằng một sơ đồ quyết định

~~~text
Một Redis primary có đủ RAM và chịu được tải ghi?
 |
 +-- Có --> Cần tự động failover?
 |           |
 |           +-- Không --> Standalone (hoặc replication thuần nếu cần bản sao/đọc)
 |           |
 |           +-- Có ----> Replication + Sentinel
 |
 +-- Không --> Redis Cluster với nhiều primary
               |
               +-- Cần chịu lỗi node --> Bố trí replica cho các primary
~~~

Trong ứng dụng Spring Data Redis, có thể ghi nhớ bằng ba cấu hình khám phá tương ứng: **`host/port` cho standalone**, **`sentinel.master/nodes` cho Sentinel**, và **`cluster.nodes` cho Cluster**. Chọn topology theo khả năng mở rộng, mức gián đoạn chấp nhận được và rủi ro mất dữ liệu; sau đó mới chọn cách cấu hình client, giám sát và xử lý lỗi tương ứng.
