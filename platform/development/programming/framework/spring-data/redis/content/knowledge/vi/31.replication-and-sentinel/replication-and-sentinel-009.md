# Kiểm thử failover, reconnect và thời gian phục hồi trong Spring Data Redis

Trong hệ thống dùng Redis làm cache, lưu trạng thái phiên, bộ đếm hoặc dữ liệu nghiệp vụ, một Redis **primary** (trong tài liệu và cấu hình cũ thường gọi là *master*) có thể ngừng hoạt động vì tiến trình bị lỗi, máy chủ mất điện, mạng bị chia cắt hoặc thao tác bảo trì. **Replication** tạo các bản sao dữ liệu trên replica; **Redis Sentinel** giám sát primary, bầu chọn và thực hiện failover khi cần. Spring Data Redis sử dụng client kết nối tới Redis, thường là Lettuce, để làm việc với topology đó.

Cấu hình Sentinel thành công chưa đủ để khẳng định hệ thống có tính sẵn sàng cao. Cần **kiểm thử failover**, quan sát client **reconnect và tìm primary mới**, đồng thời đo thời gian mà ứng dụng thực sự không thể phục vụ thao tác Redis. Các phép thử phải trả lời được:

1. Sentinel phát hiện primary mất khả năng phục vụ và chuyển vai trò replica thành primary mới trong điều kiện nào?
2. Client Spring Data Redis có tìm lại địa chỉ primary mới sau failover, hay tiếp tục gửi lệnh ghi đến endpoint cũ?
3. Trong giai đoạn chuyển đổi, API phát những lỗi gì: timeout, connection error, `READONLY`, hay phản hồi không nhất quán?
4. Bao lâu sau sự cố, ứng dụng có thể **ghi và đọc xác nhận được** trên primary mới?
5. Có bao nhiêu lệnh ghi được ứng dụng nhận là thành công nhưng **không còn dữ liệu** sau khi chuyển primary?
6. Sau khi primary cũ quay trở lại, topology và ứng dụng có tiếp tục ổn định hay không?

Bài này xây dựng quy trình kiểm thử có thể lặp lại trên một cụm thử nghiệm Redis Sentinel, tích hợp Spring Data Redis và đo cả **thời gian phục hồi (RTO quan sát)** lẫn **khả năng mất dữ liệu (RPO quan sát)**.

> **Phạm vi:** Redis Sentinel cho mô hình một primary với các replica. Redis Cluster có cơ chế định tuyến và failover khác; không suy luận rằng các lệnh, sự kiện hoặc chỉ số của Cluster giống Sentinel. Không thực hiện thao tác phá tiến trình hay thay đổi quorum trên production khi chưa có kế hoạch vận hành được phê duyệt.

## 1. Kiến trúc replication và Sentinel

Một topology cơ bản:

```text
                        Spring Boot application
                        StringRedisTemplate
                                |
                                | hỏi Sentinel: primary của "mymaster" ở đâu?
                                v
                   +------------+------------+
                   |            |            |
                Sentinel 1   Sentinel 2   Sentinel 3
                  :26379       :26380       :26381
                   |            |            |
                   +------------+------------+
                                |
                      Quan sát và bầu chọn
                                |
                      Redis primary :6379
                         /          \
                        / replication \
                       v               v
                  Replica A        Replica B
                    :6380            :6381
```

Vai trò của từng thành phần:

| Thành phần | Nhiệm vụ |
|---|---|
| Redis primary | Nhận các lệnh ghi, phục vụ lệnh đọc theo cấu hình |
| Redis replica | Sao chép dữ liệu từ primary; có thể được Sentinel chọn để thăng cấp |
| Redis Sentinel | Giám sát primary/replica, xác định lỗi, phối hợp bầu chọn, thông báo thay đổi địa chỉ |
| `RedisConnectionFactory` | Cung cấp kết nối Redis cho Spring Data Redis |
| Lettuce/Jedis | Redis client triển khai kết nối, reconnect và xử lý lệnh |
| `RedisTemplate`/`StringRedisTemplate` | API đồng bộ của ứng dụng |
| `ReactiveRedisTemplate` | API reactive khi ứng dụng dùng Reactor/WebFlux |

### 1.1. Replication không phải đồng bộ giao dịch

Trong cấu hình Redis replication phổ biến, dữ liệu được sao chép **bất đồng bộ** từ primary sang replica:

```text
Client             Primary              Replica
  | SET k v --------> |                     |
  | <----- OK --------|                     |
  |                   | ---- replication -->|
```

Phản hồi `OK` từ primary **không mặc nhiên chứng minh** replica đã nhận và lưu lệnh đó. Nếu primary chết ngay sau khi trả `OK`, replica được thăng cấp có thể chưa có một số dữ liệu mà client đã được báo thành công.

Do đó phải đo cả **availability** và **data loss**. Failover hoạt động không đồng nghĩa không mất một lần ghi nào.

### 1.2. Sentinel là cơ chế giám sát và điều phối, không lưu dữ liệu ứng dụng

Sentinel không phải nơi lưu các value của Redis. Nó biết topology và tham gia chọn primary mới. Ứng dụng vẫn thực hiện `GET`, `SET`, `INCR` trên các Redis data node.

Sentinel không biến Redis thành cơ sở dữ liệu có giao dịch phân tán hoặc consensus-based commit. Cấu hình ba Sentinel giúp tăng khả năng ra quyết định về failover, nhưng **không sửa bản chất replication bất đồng bộ**.

## 2. Quá trình failover gồm nhiều giai đoạn

Khi primary không thể liên lạc, chuỗi sự kiện thường có những giai đoạn:

```text
t0     Primary mất khả năng phục vụ
        |
        v
t1     Một Sentinel đánh dấu subjectively down (+sdown)
        |
        v
t2     Đủ Sentinel xác nhận objectively down (+odown)
        |
        v
t3     Sentinel leader được chọn; replica phù hợp được đề cử
        |
        v
t4     Replica được thăng cấp làm primary mới
        |
        v
t5     Các replica còn lại được cấu hình theo primary mới
        |
        v
t6     Client nhận biết topology thay đổi và reconnect/reroute
        |
        v
t7     Thao tác ghi/đọc nghiệp vụ bắt đầu thành công ổn định
```

Các mốc trên là **mô hình quan sát**, không phải cam kết Redis luôn cung cấp đúng bảy sự kiện theo một thời gian cố định. Một số bước có thể trùng hoặc thay đổi thứ tự quan sát qua log, tùy phiên bản, trạng thái mạng và thứ tự các Sentinel nhìn thấy sự cố.

### 2.1. Subjectively down và objectively down

- **SDOWN (*subjectively down*):** một Sentinel riêng lẻ cho rằng instance không còn phản hồi theo tiêu chí giám sát.
- **ODOWN (*objectively down*):** đủ Sentinel đồng ý rằng primary đã lỗi theo quorum được cấu hình, cho phép đi tiếp quy trình failover phù hợp.
- **Bầu leader và cho phép failover:** ngoài quorum phát hiện lỗi, việc thực hiện failover cần sự ủy quyền theo cơ chế đa số Sentinel để tránh các quyết định cạnh tranh.

Nếu chỉ có một Sentinel hoạt động hoặc các Sentinel bị chia cắt, có thể **không có failover tự động** dù Redis primary thật sự đã chết. Vì vậy, kiểm thử phải xác nhận số Sentinel hoạt động và khả năng liên lạc giữa chúng, không chỉ số Redis replica còn sống.

### 2.2. Failover có thể không thành công

Một số nguyên nhân:

- Không còn replica đủ điều kiện để thăng cấp.
- Replica quá xa dữ liệu hoặc bị cấu hình không được phép ưu tiên.
- Không đạt quorum/đa số Sentinel do mất kết nối.
- Quá trình thăng cấp gặp lỗi hoặc mất kết nối tiếp.
- Mạng hai chiều giữa các node, Sentinel và client không đồng nhất.
- Tài nguyên máy chủ quá tải, gây timeout giám sát.
- Bảo mật/TLS/authentication khiến node không thực hiện lệnh chuyển vai trò.

Hãy xem failover là **một quy trình cần kiểm chứng**, không phải chức năng có thể chỉ bật bằng một dòng cấu hình rồi bỏ qua.

## 3. Hai chỉ số trọng tâm: RTO và RPO

### 3.1. RTO – thời gian ứng dụng không phục vụ được thao tác mong muốn

**Recovery Time Objective (RTO)** là mục tiêu thời gian phục hồi được hệ thống đặt ra. Khi kiểm thử, ta đo một **thời gian phục hồi quan sát được** theo định nghĩa thao tác thành công.

Ví dụ:

```text
t0: tiêm lỗi bằng cách dừng Redis primary
t1: lời gọi SET đầu tiên thất bại
t2: Sentinel công bố primary mới
t3: probe SET + GET trên Spring Data Redis thành công bền vững
```

Có thể dùng:

```text
Observed recovery duration = t3 - t0
Observed user-visible unavailability = t3 - t1
```

Hai giá trị khác nhau:

- `t3 - t0` đo từ **thời điểm gây sự cố** đến lúc phục hồi.
- `t3 - t1` đo cửa sổ từ khi **ứng dụng bắt đầu nhìn thấy lỗi** tới lần thành công trở lại.

Phải ghi rõ định nghĩa trong báo cáo, vì nếu lệnh đầu tiên xảy ra rất lâu sau `t0`, chỉ số dựa trên `t1` sẽ không phản ánh toàn bộ thời gian hệ thống gặp sự cố.

Một lệnh `PING` thành công không đủ để chứng minh luồng nghiệp vụ ghi đã phục hồi: nó có thể chạy trên một replica, hoặc kết nối vẫn chưa trỏ tới primary mới. **Probe nên chứa phép ghi và phép đọc xác nhận**, qua đúng connection factory/template mà ứng dụng dùng thực tế.

### 3.2. RPO – số dữ liệu đã được báo thành công nhưng bị mất

**Recovery Point Objective (RPO)** mô tả mục tiêu giới hạn mất dữ liệu có thể chấp nhận. Trong phép thử, thay vì chỉ đếm thời gian, nên ghi lại từng write đã được phía ứng dụng nhận là thành công, rồi đối chiếu với primary sau failover.

Ví dụ:

```text
Trước sự cố:
    SET ha:test:run-1:seq:100 ... -> OK
    SET ha:test:run-1:seq:101 ... -> OK
    SET ha:test:run-1:seq:102 ... -> OK

Sau failover:
    key seq:100 vẫn còn
    key seq:101 vẫn còn
    key seq:102 không còn

Observed acknowledged-write loss = 1
```

Trong phép thử không dùng TTL và không chủ động xóa các key này. Nếu có TTL hoặc eviction, việc key biến mất không thể được gán ngay cho replication loss.

**RTO và RPO không giống nhau:** hệ thống có thể phục hồi ghi rất nhanh nhưng vẫn mất các ghi cuối cùng, hoặc không mất ghi nào nhưng chờ failover quá lâu.

### 3.3. Ghi lại đường cơ sở

Trước khi tiêm lỗi, đo:

- Latency p50/p95/p99 của GET/SET.
- Throughput ghi/đọc ổn định.
- Số Redis node và Sentinel đang healthy.
- Replication offset/lag và trạng thái liên kết.
- Tần suất timeout của application.
- Connection/reconnect metric của Redis client.

Không có đường cơ sở, khó biết sau failover latency cao là do chính failover hay do hệ thống đã quá tải từ trước.

## 4. Môi trường kiểm thử cần có gì?

Một môi trường thực hành hợp lý:

- **1 Redis primary**.
- **2 Redis replica**, đặt trên node hoặc container riêng.
- **3 Sentinel**, mỗi Sentinel là một tiến trình độc lập.
- **1 ứng dụng Spring Boot** kết nối qua Sentinel.
- **1 bộ phát load/probe** thực hiện đọc/ghi có mã định danh.
- **1 nơi ghi nhận kết quả bên ngoài Redis đang kiểm thử**, ví dụ file log cục bộ hoặc hệ thống đo đạc, để không mất nhật ký kiểm thử cùng Redis.
- Đồng hồ được đồng bộ tương đối giữa các máy khi cần ghép log từ nhiều nguồn.

Mô hình tối thiểu cho demo có thể chạy trên một laptop. Tuy nhiên, mọi thành phần cùng một máy **không mô phỏng được mất máy chủ vật lý, chia vùng mạng hoặc sự cố nguồn điện**. Nó chỉ kiểm tra được một phần cơ chế failover khi tiến trình Redis dừng.

### 4.1. Phân biệt demo và kịch bản production

| Môi trường | Có thể kiểm tra | Không thể suy ra |
|---|---|---|
| Tất cả tiến trình trên localhost | Cơ chế chuyển primary và client reconnect cơ bản | Tính chịu lỗi nhiều máy/AZ |
| Docker Compose một máy | Khởi động topology có kiểm soát, dừng container | Chịu lỗi hạ tầng vật lý thật |
| Nhiều VM/AZ thử nghiệm | Mạng, quorum, leader election, failover sát thực tế hơn | Không bảo đảm giống tải production |
| Staging có cấu hình tương tự production | Gần với behavior ứng dụng, auth/TLS, monitoring | Không thay thế kiểm thử theo thời gian trên production có kiểm soát |
| Redis managed service | Kiểm thử failover theo API nhà cung cấp | Không mặc nhiên điều khiển trực tiếp Sentinel hoặc xem đủ log nội bộ |

**Không làm `SHUTDOWN`, `DEBUG SEGFAULT`, `kill -9`, network partition hoặc thay đổi quorum trên production chỉ để “thử cho biết”.** Chỉ thực hiện sau khi xác nhận môi trường thử nghiệm, người sở hữu và phạm vi ảnh hưởng.

## 5. Dựng một Redis Sentinel lab cục bộ

Ví dụ này mô tả **các file cấu hình tối thiểu** cho một lab chỉ lắng nghe loopback. Dùng các port khác nhau:

```text
Primary Redis:    127.0.0.1:6379
Replica A:        127.0.0.1:6380
Replica B:        127.0.0.1:6381

Sentinel 1:       127.0.0.1:26379
Sentinel 2:       127.0.0.1:26380
Sentinel 3:       127.0.0.1:26381

Sentinel master name: mymaster
Quorum: 2
```

Các tiến trình sẽ tạo hoặc cập nhật những file cấu hình/runtime của chính chúng. Mỗi Sentinel cần quyền ghi cấu hình của nó; không dùng chung một file Sentinel cho ba tiến trình.

### 5.1. Primary config

File `redis-primary.conf`:

```conf
bind 127.0.0.1
port 6379
protected-mode yes

# Lab: bỏ persistence để đơn giản hóa;
# KHÔNG sao chép cấu hình này vào production.
save ""
appendonly no
```

**Chỉ dùng cho lab.** Tắt persistence làm thay đổi đặc điểm dữ liệu sau restart; khi kiểm thử RPO production, phải cấu hình persistence tương đương môi trường thật.

### 5.2. Replica A và B

`redis-replica-a.conf`:

```conf
bind 127.0.0.1
port 6380
protected-mode yes

replicaof 127.0.0.1 6379

save ""
appendonly no
```

`redis-replica-b.conf`:

```conf
bind 127.0.0.1
port 6381
protected-mode yes

replicaof 127.0.0.1 6379

save ""
appendonly no
```

Khi khởi động, replica kết nối primary và bắt đầu đồng bộ dữ liệu. Trước khi tiêm lỗi, cần xem `INFO replication` để chắc chắn cả hai ở trạng thái liên kết bình thường.

### 5.3. Sentinel configs

`sentinel-26379.conf`:

```conf
port 26379
bind 127.0.0.1

sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 3000
sentinel failover-timeout mymaster 15000
sentinel parallel-syncs mymaster 1
```

`sentinel-26380.conf` tương tự, chỉ thay port:

```conf
port 26380
bind 127.0.0.1

sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 3000
sentinel failover-timeout mymaster 15000
sentinel parallel-syncs mymaster 1
```

`sentinel-26381.conf`:

```conf
port 26381
bind 127.0.0.1

sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 3000
sentinel failover-timeout mymaster 15000
sentinel parallel-syncs mymaster 1
```

`down-after-milliseconds 3000` chỉ là giá trị **phục vụ thí nghiệm**, không phải khuyến nghị production. Đặt quá thấp có thể khiến Sentinel nhầm một chậm trễ mạng/CPU tạm thời thành primary bị lỗi; đặt quá cao làm thời gian phát hiện lỗi dài hơn.

### 5.4. Khởi động lab

Trên máy cài Redis, mở các phiên terminal riêng và chạy:

```bash
redis-server redis-primary.conf
redis-server redis-replica-a.conf
redis-server redis-replica-b.conf

redis-server sentinel-26379.conf --sentinel
redis-server sentinel-26380.conf --sentinel
redis-server sentinel-26381.conf --sentinel
```

Có thể chạy bằng một script quản lý tiến trình hoặc Docker Compose thay vì sáu terminal; điều quan trọng là **các tiến trình và thư mục/file runtime phải được tách biệt**.

Với Docker, không thể chỉ thay port rồi giữ `127.0.0.1` trong tất cả config: loopback của từng container là riêng biệt. Phải cấu hình hostname/container network và địa chỉ mà Sentinel công bố sao cho **Spring client có thể kết nối được**. Nếu Sentinel trả địa chỉ container nội bộ không thể truy cập từ máy chạy Java, ứng dụng có thể tìm thấy primary nhưng vẫn không reconnect thành công.

Lưu ý không mở các port Redis/Sentinel không có xác thực ra mạng công cộng. Cấu hình ở đây chỉ dành cho loopback/test.

### 5.5. Xác nhận topology ban đầu

Redis CLI:

```bash
redis-cli -p 6379 INFO replication
redis-cli -p 6380 INFO replication
redis-cli -p 6381 INFO replication

redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
redis-cli -p 26379 SENTINEL masters
redis-cli -p 26379 SENTINEL replicas mymaster
redis-cli -p 26379 SENTINEL sentinels mymaster
```

Kỳ vọng:

- Port 6379 có `role:master` (Redis vẫn dùng tên `master` trong nhiều API và trường INFO).
- Port 6380 và 6381 có `role:slave`/replica theo output Redis.
- Cả hai replica có liên kết tới primary.
- Sentinel trả địa chỉ `127.0.0.1` và port `6379` cho `mymaster`.
- Sentinel nhìn thấy các peer Sentinel và những replica dự kiến.

**Không bắt đầu đo failover khi replication ban đầu chưa ổn định**, vì phép đo lúc ấy không phản ánh một cụm HA khỏe mạnh.

## 6. Cấu hình Spring Boot dùng Sentinel

Trong Spring Boot, cấu hình mẫu cho Spring Data Redis có thể là:

```yaml
spring:
  data:
    redis:
      connect-timeout: 2s
      timeout: 3s
      sentinel:
        master: mymaster
        nodes:
          - 127.0.0.1:26379
          - 127.0.0.1:26380
          - 127.0.0.1:26381
```

Nếu server có xác thực, cần cấu hình credentials cho Redis data nodes và Sentinel theo khả năng của phiên bản Spring Boot đang sử dụng. **Sentinel password và Redis data-node password là hai phạm vi xác thực có thể khác nhau**; không mặc định chỉ một property là đủ cho mọi môi trường.

Trong Spring Boot 3.x, `spring.data.redis.*` là prefix quen thuộc. Dự án thuộc phiên bản Boot cũ có thể sử dụng prefix khác; kiểm tra cấu hình của đúng dependency/version dự án.

### 6.1. Ý nghĩa tên `mymaster`

Ở đây:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
```

`mymaster` là **tên master group trong Sentinel**, không phải hostname của Redis server. Các Sentinel phải giám sát cùng một tên phù hợp. Nếu Spring config ghi `mymaster` nhưng Sentinel giám sát `primary-1`, việc tìm primary có thể thất bại.

### 6.2. Vì sao cần nhiều Sentinel endpoint?

Nếu ứng dụng chỉ biết:

```yaml
nodes:
  - 127.0.0.1:26379
```

thì Redis server có thể đã được failover thành công nhưng client không hỏi được topology nếu **Sentinel tại :26379 cũng chết**.

Khai báo nhiều endpoint giúp client có các lựa chọn khác để tìm địa chỉ primary, tùy Redis driver và cơ chế retry. Tuy nhiên, phải bảo đảm mỗi endpoint thực sự truy cập được từ môi trường ứng dụng và có xác thực phù hợp.

**Đừng coi số endpoint trong YAML là bằng chứng client chắc chắn sẽ reconnect nhanh.** Cần thử cả khi Sentinel được cấu hình đầu tiên bị lỗi.

### 6.3. Tránh endpoint Redis cố định ngoài Sentinel

Một lỗi cấu hình điển hình là để application dùng thẳng:

```yaml
spring:
  data:
    redis:
      host: redis-primary-old
      port: 6379
```

và vẫn hy vọng client tự theo dõi Sentinel. Nếu application thực tế tạo connection factory bằng host cố định, nó có thể tiếp tục gửi lệnh tới Redis cũ sau failover.

Khi dùng Sentinel, cần xác nhận **`RedisConnectionFactory` mà template thực sự sử dụng** được khởi tạo từ Sentinel topology, chứ không phải có một bean override khác dùng standalone host/port.

## 7. Cấu hình `LettuceConnectionFactory` chủ động

Spring Data Redis thường sử dụng Lettuce cho kết nối đồng bộ và reactive. Nếu ứng dụng cần khai báo connection factory riêng, có thể dùng `RedisSentinelConfiguration`.

Ví dụ:

```java
package com.example.redis;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class SentinelRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisSentinelConfiguration sentinel =
                new RedisSentinelConfiguration()
                    .master("mymaster")
                    .sentinel("127.0.0.1", 26379)
                    .sentinel("127.0.0.1", 26380)
                    .sentinel("127.0.0.1", 26381);

        LettuceClientConfiguration client =
                LettuceClientConfiguration.builder()
                    .commandTimeout(Duration.ofSeconds(3))
                    .build();

        return new LettuceConnectionFactory(sentinel, client);
    }
}
```

Đây là mẫu minh họa cho các API Spring Data Redis phổ biến. Khi tự định nghĩa bean này, cần cấu hình thêm authentication, TLS, pooling, client resources hoặc replica-read policy nếu môi trường yêu cầu.

**Cẩn thận với Spring Boot auto-configuration:** tự tạo `RedisConnectionFactory` có thể khiến các thiết lập properties của Boot không được áp dụng tự động như trước. Không vừa viết một bean kết nối standalone khác vừa nghĩ tất cả template đều trỏ đến Sentinel.

### 7.1. Lettuce reconnect và Redis Sentinel là hai cơ chế phối hợp

- **Reconnect**: khôi phục kết nối TCP/Redis sau khi một connection bị ngắt.
- **Master discovery**: tìm primary hiện tại qua Sentinel khi vai trò node thay đổi.
- **Command retry**: chính sách ứng dụng/client khi một lệnh thất bại hoặc không rõ đã thực thi.
- **Application recovery**: thời điểm thao tác nghiệp vụ thực sự thành công trở lại.

Chúng có liên quan nhưng **không đồng nhất**. Một TCP connection được mở lại thành công tới **replica cũ** không đủ để lệnh ghi thành công; Redis có thể trả `READONLY`.

Ngược lại, Sentinel đã biết primary mới cũng không bảo đảm những connection cũ trong client ngay lập tức được thay thế. Do đó đo riêng trạng thái Sentinel và kết quả thao tác Spring template là cần thiết.

### 7.2. Read-from-replica làm phép đo phức tạp hơn

Nếu client có cấu hình đọc từ replica nhằm tăng throughput, một phép `GET` thành công sau failover **không chứng minh** lệnh ghi đã phục hồi và cũng không chứng minh dữ liệu mới nhất đã có trên mọi replica.

Với test RTO ghi và RPO, nên xác định rõ dữ liệu được đọc từ **primary mới** hoặc có cơ chế đối chiếu vai trò node, không dùng một GET trên replica có thể stale để kết luận “không mất dữ liệu”.

## 8. Thiết kế probe từ chính ứng dụng Spring Data Redis

Một probe tốt dùng **cùng connection factory, serializer và cách gọi** với service thực tế. Nó ghi một key riêng rồi đọc lại để xác nhận write path và read path.

Ví dụ sử dụng `StringRedisTemplate`:

```java
package com.example.redis;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class RedisFailoverProbe {

    private static final Logger log =
            LoggerFactory.getLogger(RedisFailoverProbe.class);

    private final StringRedisTemplate redis;
    private final String runId = UUID.randomUUID().toString();
    private final AtomicLong sequence = new AtomicLong();

    public RedisFailoverProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Scheduled(fixedDelayString = "${ha.probe.delay-ms:250}")
    public void verifyWriteAndRead() {
        long seq = sequence.incrementAndGet();
        String key = "ha:probe:" + runId + ":" + seq;
        String expected = "probe-" + seq;

        long start = System.nanoTime();

        try {
            Boolean written = redis.opsForValue()
                    .setIfAbsent(key, expected);

            if (!Boolean.TRUE.equals(written)) {
                throw new IllegalStateException(
                    "Probe key unexpectedly exists: " + key
                );
            }

            String actual = redis.opsForValue().get(key);

            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                    "Probe readback mismatch for " + key
                );
            }

            long elapsedMillis =
                    (System.nanoTime() - start) / 1_000_000;

            log.info(
                "REDIS_PROBE_OK run={} seq={} latency_ms={}",
                runId, seq, elapsedMillis
            );
        } catch (Exception ex) {
            long elapsedMillis =
                    (System.nanoTime() - start) / 1_000_000;

            log.warn(
                "REDIS_PROBE_FAIL run={} seq={} latency_ms={} type={}",
                runId,
                seq,
                elapsedMillis,
                ex.getClass().getSimpleName()
            );
        }
    }
}
```

Bật scheduling ở một class cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class ProbeSchedulingConfiguration {
}
```

### 8.1. Vì sao probe dùng key duy nhất?

Nếu chỉ ghi đi ghi lại cùng một key `healthcheck`, một request có thể đọc nhầm dữ liệu cũ và vẫn báo thành công dù lệnh ghi vừa rồi thất bại hoặc bị định tuyến không đúng.

Key gồm `runId` và sequence giúp mỗi lần probe dễ được nhận diện trong log:

```text
ha:probe:<runId>:1
ha:probe:<runId>:2
ha:probe:<runId>:3
```

Với test RPO, các key nên được giữ lại cho đến khi hoàn thành đối chiếu. Vì vậy đoạn ví dụ **không đặt TTL**, chỉ dùng trong lab và phải có bước xóa dữ liệu thử nghiệm sau cùng.

### 8.2. Vì sao dùng `setIfAbsent`?

Probe cần biết một key mới thực sự được tạo. Với key duy nhất, `setIfAbsent` thường trả `true` khi ghi thành công. Nếu trả `false`, có thể đã trùng key hoặc có điều kiện bất thường khác; không đánh dấu probe thành công mù quáng.

Tuy nhiên, `SET NX` không bảo đảm dữ liệu đã được replica nhận, và chuỗi `SET NX` → `GET` vẫn là **hai lệnh**, không phải một transaction.

### 8.3. Giới hạn của probe minh họa

- Chỉ chạy trên môi trường kiểm thử và namespace `ha:probe:*`.
- Việc tạo key không TTL làm dữ liệu tăng dần; cần giới hạn thời gian chạy và cleanup.
- `@Scheduled` với một thread xử lý định kỳ có thể bỏ các thời điểm quan sát trong lúc lời gọi đang timeout. Vì vậy tần suất log chỉ là **độ phân giải đo**, không phải lưu lượng tuyệt đối với interval cố định.
- Khi command timeout xảy ra, ứng dụng không biết chắc Redis đã thực hiện write chưa. `REDIS_PROBE_FAIL` có nghĩa probe chưa xác nhận thành công end-to-end, không phải bằng chứng Redis chưa nhận lệnh.
- `System.nanoTime()` chỉ phù hợp đo **duration nội bộ một JVM**, không dùng làm timestamp chung để so sánh trực tiếp với log Sentinel của máy khác. Muốn ghép timeline, thêm `Instant.now()` và đồng bộ đồng hồ.
- Với production-like test, nên ghi histogram metrics thay vì log một dòng trên mỗi lần gọi dưới tải cao.
- Nếu nhiều instance chạy probe, cần `runId` riêng và nhãn metric không dùng chính `runId` như metric label có cardinality không giới hạn.

## 9. Tiêm lỗi: dừng primary đột ngột

Sau khi xác nhận tất cả node khỏe mạnh và probe đang chạy, có thể tiêm lỗi trên **môi trường thử nghiệm** bằng cách dừng tiến trình Redis primary.

Một phương án trong lab Unix được quản lý tiến trình:

```bash
# Thực hiện trên lab, xác định đúng PID Redis primary :6379.
# Không chạy trên máy chủ production hoặc dùng PID suy đoán.
kill -9 <PID_CUA_PRIMARY_LAB>
```

Nếu chạy bằng Docker Compose hoặc container runtime, nên dừng **đúng container primary thử nghiệm** bằng công cụ quản lý môi trường:

```bash
docker kill <TEN_CONTAINER_PRIMARY_LAB>
```

Không dùng tên container mơ hồ hoặc “kill tất cả Redis”. Trước khi tiêm lỗi phải xác nhận container bị chọn thực sự là primary hiện tại, vì sau một lần failover cổng 6379 **không còn nhất thiết là primary**.

### 9.1. Những gì cần ghi vào timeline

Khi bấm tiêm lỗi, ghi mốc `t0` bên ngoài Redis:

```text
2026-11-13T10:00:00.000Z  INJECTED_PRIMARY_FAILURE
2026-11-13T10:00:00.100Z  REDIS_PROBE_FAIL connection error
2026-11-13T10:00:03.500Z  SENTINEL +sdown
2026-11-13T10:00:03.700Z  SENTINEL +odown
2026-11-13T10:00:04.500Z  SENTINEL +switch-master
2026-11-13T10:00:05.200Z  REDIS_PROBE_OK
```

Đây là dữ liệu **minh họa**, không phải kết quả đo thực tế của Redis hay cam kết các mốc xuất hiện theo thời gian đó.

Ngoài log, ghi lại:

- Redis primary cũ và primary mới.
- ID/kết nối của những Sentinel có tham gia.
- Exception đầy đủ từ Java kèm thời điểm.
- Số lượng request thất bại và thành công.
- Latency p95/p99 của endpoint dùng Redis.
- Replication health sau khi replica được thăng cấp.
- Những key probe được báo thành công trước lỗi có còn tồn tại không.

### 9.2. Khi failover thành công

Kiểm tra từ Sentinel:

```bash
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster
```

Giả sử sau failover nhận:

```text
127.0.0.1
6380
```

Xác nhận vai trò node:

```bash
redis-cli -p 6380 INFO replication
redis-cli -p 6381 INFO replication
```

Kỳ vọng port 6380 có role `master`; replica còn lại theo dõi primary mới. Kết quả chính xác tùy node mà Sentinel thực sự chọn.

**Không hardcode “failover luôn chọn replica A”**. Sentinel lựa chọn dựa trên trạng thái replica, độ trễ replication, ưu tiên và các tiêu chí khác.

### 9.3. Kiểm tra application chứ không chỉ topology

Sau khi Sentinel báo primary mới, tiếp tục quan sát `REDIS_PROBE_OK`.

Một topology có thể đã chuyển thành công mà Spring Data Redis vẫn lỗi trong vài giây vì:

- Client đang chờ command timeout.
- Kết nối cũ chưa được đóng hoặc định tuyến lại.
- Một địa chỉ được Sentinel trả về không truy cập được từ ứng dụng.
- Driver có lỗi xác thực với endpoint mới.
- Pool hết connection, chờ tài nguyên.
- Một replica cũ được gọi nhầm như primary và trả `READONLY`.

Chính thời điểm **application probe phục hồi** mới phản ánh thời gian người dùng thực sự có thể thao tác.

## 10. Tiêm lỗi có kiểm soát: yêu cầu Sentinel failover

Ngoài việc dừng tiến trình, Redis Sentinel hỗ trợ lệnh quản trị yêu cầu failover:

```bash
redis-cli -p 26379 SENTINEL FAILOVER mymaster
```

Đây là một phép thử khác với mất điện hoặc primary đột ngột biến mất:

- Sentinel được yêu cầu chuyển vai trò có chủ đích.
- Primary hiện tại có thể vẫn đang chạy.
- Thời gian và loại lỗi ứng dụng có thể khác so với khi tiến trình bị kill.
- Không dùng kết quả của manual failover để kết luận toàn bộ cơ chế phát hiện SDOWN/ODOWN đã được kiểm thử.

Nên tạo **hai báo cáo riêng**:

1. **Planned failover** (chuyển primary có kiểm soát).
2. **Unplanned failover** (primary mất khả năng phục vụ đột ngột).

Manual failover cũng chỉ thực hiện khi các điều kiện Sentinel và replica cho phép; lỗi từ lệnh quản trị phải được ghi nhận như một phần của thí nghiệm.

## 11. Thử tình huống lỗi Sentinel

Một hệ thống HA có thể mất **Sentinel** mà các Redis data node vẫn đang khỏe mạnh. Đây là tình huống riêng cần thử.

Kịch bản:

1. Xác nhận ba Sentinel đang thấy nhau.
2. Dừng **một Sentinel** trong lab.
3. Giữ primary Redis hoạt động bình thường.
4. Kiểm tra application còn đọc/ghi được.
5. Kiểm tra hai Sentinel còn lại có thể trả địa chỉ primary.
6. Sau đó khởi động lại Sentinel đã dừng.

Kỳ vọng thông thường là **mất một Sentinel không làm Redis data node ngừng phục vụ**. Tuy nhiên, nếu client chỉ được cấu hình hỏi Sentinel đã chết để khám phá topology, việc tạo kết nối mới có thể bị ảnh hưởng.

### 11.1. Quorum và đa số

Với ba Sentinel, quorum 2, mất một Sentinel vẫn có thể còn hai Sentinel hoạt động để phối hợp. Mất hai Sentinel có thể khiến việc failover tự động không còn được ủy quyền đúng cách, dù Redis primary vẫn có thể phục vụ nếu chưa lỗi.

Không đánh đồng:

```text
Redis data node có thể đọc/ghi
```

với:

```text
Sentinel quorum đủ để thực hiện failover mới
```

Hai trạng thái này liên quan nhưng khác nhau.

Thử network partition giữa Sentinel và Redis là kịch bản nâng cao: sự khác biệt về tầm nhìn mạng có thể khiến một phía coi primary lỗi trong khi client khác vẫn truy cập được. Cần dùng công cụ chaos/network có kiểm soát để tránh tạo một thí nghiệm khó khôi phục.

## 12. Kiểm thử khi primary cũ quay lại

Sau failover, một replica đã thành primary mới. Nếu primary cũ được khởi động lại, Sentinel có thể tái cấu hình nó thành **replica của primary mới** sau khi phát hiện topology.

Luồng dự kiến:

```text
Trước lỗi:
  :6379 primary
  :6380 replica
  :6381 replica

Sau lỗi và failover:
  :6379 down
  :6380 primary mới
  :6381 replica của :6380

Sau khi :6379 trở lại:
  :6379 có thể trở thành replica của :6380
  :6380 vẫn primary
  :6381 vẫn replica
```

Điều quan trọng là **primary cũ không tự động được quay trở lại vị trí primary chỉ vì nó khởi động lại**. Việc thay đổi vai trò tiếp theo do cơ chế Sentinel/cấu hình vận hành quyết định.

Kiểm thử:

- Xác nhận chỉ có một primary hợp lệ theo topology đang quản lý.
- Xem `INFO replication` từng node.
- Xem Sentinel có cập nhật danh sách replica không.
- Chạy lại probe ghi/đọc qua Spring Data Redis.
- Đảm bảo application không giữ endpoint cũ như primary.
- Kiểm tra dữ liệu trên primary cũ được đồng bộ lại theo primary mới.
- Không so sánh dữ liệu trong giai đoạn đồng bộ chưa hoàn tất rồi kết luận đã mất vĩnh viễn.

Với dữ liệu quan trọng, cần tính đến việc primary cũ có một số ghi chưa được replica nhận trước khi lỗi; khi nó quay lại và trở thành replica, dữ liệu riêng lẻ trên primary cũ có thể không được dùng làm nguồn chân lý mới.

## 13. Lỗi thường gặp khi client reconnect

### 13.1. Connection refused / reset / timeout

Trong vài giây sau khi primary chết, connection hiện tại có thể bị reset hoặc không phản hồi.

Ví dụ loại lỗi thường thấy ở Java:

```text
RedisConnectionFailureException
RedisCommandTimeoutException
RedisSystemException
```

Các exception cụ thể và lớp bao bọc phụ thuộc Spring Data Redis/driver/version. Không viết handler chỉ dựa vào một message string mà bỏ qua nguyên nhân thực tế.

### 13.2. `READONLY` khi gửi lệnh ghi tới replica

Nếu ứng dụng hoặc một connection cũ tiếp tục gửi `SET` tới node đã bị hạ vai trò thành replica, Redis có thể trả lỗi dạng:

```text
READONLY You can't write against a read only replica
```

Đó là dấu hiệu **định tuyến chưa phù hợp với topology hiện tại**, không phải bằng chứng Redis đã mất mọi dữ liệu. Cần kiểm tra Redis connection factory, Sentinel discovery, config cố định host và tình trạng reconnect.

Không sửa bằng cách bật writable replica bừa bãi; điều đó phá vỡ giả định replication và có thể tạo dữ liệu xung đột.

### 13.3. Một Sentinel trả địa chỉ không truy cập được

Redis Sentinel có thể phát hiện primary mới ở địa chỉ nội bộ:

```text
10.10.0.8:6379
```

Nhưng ứng dụng từ mạng khác chỉ thấy endpoint NAT:

```text
redis.company.example:6379
```

Nếu Lettuce nhận địa chỉ nội bộ không reachable, `get-master-addr-by-name` vẫn có kết quả nhưng kết nối tới primary mới thất bại.

Đây là lỗi thường gặp khi dựng lab Docker, NAT, overlay network hoặc khi Sentinel và app nằm ở các mạng khác nhau. Cần cấu hình announce/endpoint routing và network policy hợp lệ **cho cả Sentinel lẫn Redis data node**.

### 13.4. Authentication/TLS khác nhau giữa các node

Failover có thể chọn replica chưa được cấu hình đầy đủ ACL/TLS hoặc network rule như primary cũ. Khi đó ứng dụng mất kết nối dù topology đã chuyển.

Một phép thử HA có giá trị phải xác minh:

- Credentials áp dụng nhất quán cho các Redis data node.
- Sentinel authentication được xử lý riêng khi cần.
- Certificate/TLS name phù hợp endpoint được công bố.
- Firewall/security group cho phép kết nối tới replica được thăng cấp.

## 14. Timeout và retry: phục hồi kết nối không có nghĩa lệnh ghi an toàn để gửi lại

Giả sử Java gọi:

```java
redis.opsForValue().increment("orders:created");
```

Redis primary có thể đã thực thi `INCR` nhưng client bị timeout **trước khi nhận phản hồi**. Nếu ứng dụng retry cùng `INCR`, bộ đếm có thể tăng hai lần.

```text
Client                   Redis primary
  | -- INCR k ----------> |
  |                       | giá trị tăng
  | X mất kết nối         |
  |                       |
  | -- INCR k (retry) --->| giá trị tăng lần 2
```

Failover làm khoảng kết nối không ổn định rõ hơn, nên rủi ro **unknown outcome** của lệnh ghi càng cần được xem xét.

### 14.1. Phân loại retry

| Lệnh/mô hình | Có thể retry mù quáng? | Vì sao |
|---|---|---|
| `GET` dữ liệu cache | Thường có thể với lỗi tạm thời, theo giới hạn | Không tạo side effect |
| `SET key fixedValue` | Có thể phù hợp nếu giá trị bất biến cho request và không phá cập nhật mới hơn | Ghi đè dữ liệu cũ/mới vẫn có nguy cơ race |
| `INCR` | **Không** | Có thể cộng thêm lần nữa |
| `LPUSH` | **Không** nếu không chống trùng | Có thể thêm phần tử hai lần |
| `XADD *` | **Không** nếu không dùng event ID/idempotency | Có thể tạo hai stream entry khác ID |
| `SET NX` | Phụ thuộc kết quả/ownership token | Retry có thể trả false dù lệnh đầu đã thành công |
| Cache invalidation (`DEL`) | Thường gần idempotent | Nhưng phải xét race với cache refill |
| Ghi DB rồi cập nhật Redis | Không được coi là transaction chung | Hai resource có thể commit khác nhau |

Một retry policy hợp lý cần giới hạn số lần, backoff, loại lỗi được retry và cách phát hiện duplicate/unknown outcome. Không chỉ bật retry vô hạn rồi coi RTO đã được giải quyết.

### 14.2. Command timeout không phải failover timeout

`spring.data.redis.timeout` hoặc `LettuceClientConfiguration.commandTimeout(...)` giới hạn thời gian chờ cho **một lệnh** theo cách client thực hiện. Nó không phải biến cấu hình bắt Sentinel failover trong đúng khoảng đó.

Nếu timeout là 1 giây nhưng Sentinel cần vài giây để promote replica, các request có thể nhận exception tạm thời rồi thành công lại. Cần đo ở application layer và xử lý fallback phù hợp, không giả định connection tự bảo vệ mọi request khỏi lỗi.

## 15. Kịch bản RPO: đối chiếu những write đã ACK

Để kiểm thử khả năng mất dữ liệu, dùng một workload có sequence và **ghi nhật ký ACK ngoài Redis**.

Ví dụ pseudo-flow:

```text
runId = test-20261113-01
seq = 1, 2, 3, ...

for each seq:
    SET ha:rpo:<runId>:<seq> = <seq>
    nếu client nhận success:
        append seq vào local durable ACK log
```

Sau khi tiêm lỗi và ứng dụng phục hồi:

```text
for mỗi seq trong ACK log:
    GET key từ primary hiện tại
    nếu key không tồn tại hoặc value khác:
        đánh dấu acknowledged-write missing/mismatch
```

Một ví dụ Java rút gọn cho phần ghi:

```java
public boolean writeRpoSample(
        StringRedisTemplate redis,
        String runId,
        long seq
) {
    String key = "ha:rpo:" + runId + ":" + seq;
    String value = Long.toString(seq);

    Boolean success = redis.opsForValue()
            .setIfAbsent(key, value);

    return Boolean.TRUE.equals(success);
}
```

Nếu trả `true`, test harness cần **ghi `seq` vào file hoặc nguồn ghi nhật ký bên ngoài Redis** bằng cơ chế chắc chắn của harness. Nếu xảy ra exception hoặc timeout, trạng thái kết quả là **không chắc chắn**, phải ghi riêng thay vì xếp luôn vào nhóm “không thực thi”.

### 15.1. Các bẫy khi đo mất dữ liệu

- Không đặt TTL ngắn trên key RPO test.
- Không chạy eviction policy có thể xóa key vì thiếu memory rồi coi đó là replication loss.
- Không đọc từ một replica chưa đồng bộ xong rồi kết luận key đã mất.
- Không kiểm đếm `SET` trả exception như một ACK thành công.
- Không dùng Redis đang test làm nơi duy nhất lưu ACK log.
- Không chạy một lượng key khổng lồ làm hết RAM rồi phá điều kiện thí nghiệm.
- Không so sánh hai run dùng trùng namespace/sequence.
- Không suy luận `WAIT` hoặc chính sách replica acknowledgment là bảo đảm tuyệt đối của commit bền vững sau mọi failover.

### 15.2. Có thể dùng `WAIT` để giảm nguy cơ mất ghi không?

Redis có lệnh `WAIT` yêu cầu client chờ đến khi một số replica xác nhận đã nhận dữ liệu replication trước đó trên connection tương ứng, trong giới hạn thời gian.

Nó có thể **giảm nguy cơ** mất dữ liệu với một số kịch bản, nhưng:

- Không biến replication Redis thành cơ chế commit consensus.
- Không bảo đảm một replica cụ thể luôn được Sentinel chọn.
- Không bảo đảm dữ liệu được fsync bền vững trong mọi cấu hình.
- Phải xét kết quả trả về số replica đã xác nhận và timeout.
- Cần xác định command sequencing/connection khi triển khai từ framework.

`min-replicas-to-write` cùng `min-replicas-max-lag` cũng có thể hạn chế primary chấp nhận ghi khi không đủ replica theo các điều kiện nhất định, đánh đổi availability. Không thay đổi các setting đó tùy tiện trong bài test chỉ vì muốn “RPO bằng 0”.

## 16. Bảng kiểm thử failover có cấu trúc

Một suite HA không nên chỉ có một lần “kill primary”. Có thể chia thành các trường hợp:

| ID | Tình huống | Quan sát chính |
|---|---|---|
| FT-01 | Dừng primary đột ngột | Phát hiện lỗi, promote replica, RTO app |
| FT-02 | Sentinel manual failover | Hành vi chuyển vai trò có kế hoạch |
| FT-03 | Một Sentinel chết | Client discovery và quorum còn lại |
| FT-04 | Primary cũ khởi động lại | Node cũ thành replica, không có split-brain trong topology |
| FT-05 | Replica gần primary nhất bị trễ | Sentinel chọn replica nào, dữ liệu cuối cùng còn hay mất |
| FT-06 | Lệnh ghi đang bay trong lúc failover | Unknown outcome, duplicate nếu retry |
| FT-07 | Application restart giữa failover | Khả năng boot và tìm primary mới |
| FT-08 | Một địa chỉ Sentinel được cấu hình không truy cập được | Fallback qua Sentinel khác |
| FT-09 | Mạng chậm/packet loss có kiểm soát | False failover, timeout và reconnect |
| FT-10 | Một vùng mạng không thấy quorum | Availability, khả năng không được promote |
| FT-11 | Replica đọc với lag | Stale read khi tách read/write |
| FT-12 | Sentinel endpoint công bố sai mạng | Reconnect thất bại dù đã switch-master |
| FT-13 | Tải ghi/đọc cao trong lúc failover | p99, lỗi, timeout, queue backlog |
| FT-14 | Redis data node có auth/TLS không đồng đều | Phát hiện lỗi cấu hình sau khi promote |
| FT-15 | Kiểm thử RPO bằng ACK log ngoài Redis | Số write đã ACK không còn trên primary mới |

Với các kịch bản network partition, nên sử dụng công cụ điều khiển lỗi được cô lập ở staging. Không coi một lệnh `docker stop` đơn giản đã bao phủ đủ các tình huống mạng.

## 17. Cách tạo tải mà không làm sai phép đo

Nếu chỉ có một probe mỗi 5 giây, RTO đo được có **độ phân giải rất thô**. Nếu probe quá nhanh, bản thân test có thể làm Redis quá tải.

Một kế hoạch hợp lý cho lab:

```text
Warm-up:
    Chạy probe/read-write 30–60 giây.
    Xác nhận latency baseline, replication ổn định.

Steady-state:
    Chạy load read/write có giới hạn.
    Ghi các ACK sequence cần kiểm RPO.

Fault injection:
    Ghi t0; dừng đúng primary hiện tại.
    Không đổi load profile ngay thời điểm tiêm lỗi.

Recovery:
    Tiếp tục probe theo chu kỳ xác định.
    Ghi first sustained success và error rate.

Stabilization:
    Quan sát thêm để chắc chắn không flapping liên tục.
    Kiểm tra replica đã đồng bộ và client không còn định tuyến sai.

Reconciliation:
    Đối chiếu ACK log với primary mới.
    Tổng hợp RTO, RPO, p95/p99, lỗi và timeline.
```

Ở đây “first sustained success” có thể định nghĩa là **N lần probe ghi/đọc liên tiếp thành công trong một cửa sổ nhất định**, ví dụ 10 lần. Nếu chỉ có một thành công đơn lẻ xen giữa nhiều timeout, chưa chắc hệ thống đã phục hồi ổn định.

Nên báo cáo cả:

- Thời điểm **thành công đầu tiên**.
- Thời điểm **khôi phục ổn định** theo tiêu chí đã công bố.
- Tỷ lệ lỗi trong cửa sổ failover.
- Độ trễ những request vẫn thành công.
- Số lần reconnect.
- Số lần retry và duplicate (nếu có).

Không thay đổi tiêu chí “khôi phục” sau khi xem kết quả chỉ để khiến RTO nhìn tốt hơn.

## 18. Đo RTO bằng monotonic clock và ghép timeline

### 18.1. Trong một tiến trình

Nếu tool tiêm lỗi và app probe nằm trong **cùng JVM/process**, có thể dùng `System.nanoTime()` để đo duration. Trong ứng dụng thường không nên để code production tự kill Redis; tốt hơn là harness bên ngoài và app probe ghi metric.

```java
long started = System.nanoTime();

// Một thao tác do test harness kiểm soát.

long elapsedNanos = System.nanoTime() - started;
double elapsedMillis = elapsedNanos / 1_000_000.0;
```

`System.nanoTime()` phù hợp cho khoảng thời gian, không phải timestamp UTC có ý nghĩa giữa các máy.

### 18.2. Giữa các process/máy

Để ghép timeline:

```text
Sentinel log timestamp
Redis server log timestamp
Application log timestamp
Fault injection timestamp
```

sử dụng timestamp đồng bộ bằng NTP/chrony hoặc hệ thống đồng hồ phù hợp. Đồng thời ghi ID của run và endpoint/node.

Ví dụ record đầu ra:

```json
{
  "runId": "ft-01-20261113",
  "scenario": "primary-process-kill",
  "faultAt": "2026-11-13T10:00:00Z",
  "sentinelSwitchAt": "2026-11-13T10:00:04.5Z",
  "firstWriteReadSuccessAt": "2026-11-13T10:00:05.2Z",
  "stableRecoveryAt": "2026-11-13T10:00:06.0Z",
  "observedRecoveryMillis": 6000,
  "acknowledgedWriteLoss": 1,
  "status": "EXAMPLE_ONLY"
}
```

Đây là **định dạng minh họa**, không phải kết quả kiểm thử thật. Trong báo cáo thực tế, `observedRecoveryMillis` phải được tính từ các mốc đo xác nhận; không suy ra bằng cách nhìn một vài dòng log thiếu sự đồng bộ đồng hồ.

## 19. Theo dõi Sentinel và replication khi test

Các Redis CLI command hữu ích:

```bash
# Primary mà Sentinel hiện biết:
redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster

# Trạng thái master group:
redis-cli -p 26379 SENTINEL master mymaster

# Trạng thái replica:
redis-cli -p 26379 SENTINEL replicas mymaster

# Các Sentinel khác:
redis-cli -p 26379 SENTINEL sentinels mymaster

# Vai trò và replication offset tại data node:
redis-cli -p 6379 INFO replication
redis-cli -p 6380 INFO replication
redis-cli -p 6381 INFO replication
```

Với cụm dùng password/ACL/TLS, thêm các tham số xác thực và transport thích hợp cho Redis CLI; không đưa password trực tiếp vào command history hoặc log CI nếu có lựa chọn secrets an toàn hơn.

### 19.1. `INFO replication`

Một vài trường thường hữu ích:

| Trường | Ý nghĩa |
|---|---|
| `role` | Node đang là master/replica |
| `connected_slaves` | Số replica kết nối, theo trường phiên bản |
| `master_repl_offset` | Vị trí replication stream trên primary |
| `master_link_status` | Tình trạng liên kết tới primary khi node là replica |
| `slave_repl_offset` | Vị trí replica theo output Redis |
| `master_last_io_seconds_ago` | Thời gian kể từ I/O với primary trên replica |
| `master_sync_in_progress` | Replica có đang đồng bộ lại không |

Tên trường có thể vẫn dùng `master`/`slave` vì tương thích lịch sử. Không coi sự khác biệt vài byte giữa offset là bằng chứng trực tiếp rằng một số lượng nhất định command bị mất; replication offset đo trong luồng replication, không phải số entry ứng dụng.

### 19.2. Sentinel Pub/Sub event channels

Sentinel phát sự kiện quản trị liên quan tới giám sát, như:

```text
+sdown
+odown
+switch-master
+failover-end
```

Các tên/event chính xác cần đọc theo phiên bản Redis. Có thể xem log của từng Sentinel hoặc subscribe event trong môi trường lab:

```bash
redis-cli -p 26379 PSUBSCRIBE '*'
```

Đây là cách thu sự kiện trong môi trường thử nghiệm, không nên dùng một subscription wildcard không giới hạn làm monitoring production khi chưa đánh giá volume và bảo mật. Các sự kiện Sentinel hỗ trợ ghép timeline, nhưng **không thay thế kết quả probe application**.

## 20. Ghi nhận exception và behavior ở Spring Data Redis

Khi failover xảy ra, Spring Data Redis có thể chuyển exception của driver thành exception thuộc tầng `org.springframework.data.redis.*`. Nên log:

- `exception.getClass().getName()`.
- Root cause chain (trong log an toàn).
- Thao tác (`GET`, `SET`, `INCR`, `EVAL`, Pub/Sub...).
- Thời điểm và duration.
- Số lần retry của ứng dụng.
- Endpoint được driver dùng nếu có thể quan sát an toàn.
- Correlation ID/run ID của phép thử.

Không gắn raw key mang dữ liệu người dùng hoặc credentials vào log ở production. Có thể dùng **tên nhóm thao tác** thay vì key đầy đủ.

### 20.1. Fallback khi Redis chỉ là cache

Nếu Redis là cache cho dữ liệu có thể tái tạo, ứng dụng có thể chọn:

```text
Redis GET thành công -> dùng cache
Redis GET miss       -> gọi nguồn dữ liệu
Redis GET lỗi        -> gọi nguồn dữ liệu, đồng thời ghi metric
```

Nhưng cần lưu ý:

- Mất Redis có thể khiến traffic dồn về database.
- Cache write thất bại không nhất thiết khiến API thất bại nếu cache chỉ là tối ưu.
- Cache invalidation thất bại có thể làm dữ liệu cũ tồn tại sau khi Redis phục hồi.
- Cần hạn chế lượng request fallback, tránh retry storm.
- Các endpoint dùng Redis cho **lock, idempotency, session hoặc counter nghiệp vụ** không thể tự ý bỏ qua Redis như với cache thông thường.

### 20.2. Không chuyển toàn bộ lỗi Redis thành “không tìm thấy”

Sai:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null; // Lỗi kết nối bị trộn với cache miss.
}
```

Nếu phía gọi coi `null` là “đối tượng không tồn tại”, failover Redis có thể bị biến thành hàng loạt 404 sai.

Phải có chính sách rõ: cache miss, lỗi kết nối và lỗi dữ liệu là những trạng thái khác nhau.

## 21. Redis Pub/Sub, Streams và consumer sau failover

Spring Data Redis còn có listener Pub/Sub và Stream consumer. Khi test Sentinel, chỉ đo `StringRedisTemplate` là chưa đủ nếu ứng dụng còn sử dụng các cơ chế này.

### 21.1. Pub/Sub

Pub/Sub không lưu lịch sử cho subscriber offline. Trong lúc primary chuyển vai trò và subscription reconnect, các message được publish khi subscriber không còn đăng ký có thể **bị mất**.

Một số điểm cần test:

- `RedisMessageListenerContainer` có tái đăng ký channel/pattern sau reconnect không?
- Trong khoảng gián đoạn, có message không tới listener không?
- Sau khi khôi phục, listener có nhận event mới ổn định không?
- Nếu đó là thông báo invalidate local cache, có TTL/reconciliation để chịu được sự kiện bị mất không?

Không kỳ vọng Pub/Sub replay các message chỉ vì Sentinel failover thành công.

### 21.2. Redis Streams

Redis Streams lưu entry theo ID và có consumer group/PEL. Tuy nhiên, nó vẫn dùng Redis persistence/replication và chịu rủi ro khi các write cuối chưa được replica nhận.

Cần test thêm:

- Consumer group có tồn tại trên primary mới không?
- Entry đã XADD nhưng chưa replicate có bị mất không?
- Pending entries có còn và được reclaim/ACK không?
- `ReadOffset.lastConsumed()` có tiếp tục nhận entry mới không?
- Consumer có xử lý lặp sau crash/timeout/ACK không?
- Retention có đủ cho downtime hay không?

Redis Streams giúp xử lý pending/retry ở tầng consumer, nhưng không biến replication bất đồng bộ thành zero-data-loss commit.

### 21.3. Lua và transaction trong giai đoạn failover

Nếu ứng dụng gọi Lua script hoặc `MULTI/EXEC`:

- Có thể nhận timeout trong lúc server đã thực hiện một phần hoặc toàn bộ tác vụ nhưng phản hồi bị mất.
- Không nên retry không điều kiện một script có side effect cộng dồn.
- Redis transaction không trải qua hai primary theo kiểu distributed atomic transaction.
- Nếu primary chuyển trong lúc xử lý, cần xem dữ liệu nào đã replicate và business idempotency thế nào.

Đối với thao tác quan trọng, bài test phải có event/operation ID để đối chiếu kết quả sau failover, không chỉ kiểm tra có exception hay không.

## 22. Các dấu hiệu thành công của một bài test HA

Một kịch bản có thể coi là đạt khi **các tiêu chí đã xác định trước** được đáp ứng. Ví dụ:

| Tiêu chí | Ví dụ điều kiện chấp nhận |
|---|---|
| Sentinel quorum | Còn đủ thành viên để quyết định theo topology mong muốn |
| Failover hoàn tất | Sentinel báo primary mới và data node role nhất quán |
| RTO | Thấp hơn ngân sách mà sản phẩm đặt ra |
| Stable recovery | N lần write/read liên tiếp thành công sau chuyển |
| Error rate | Không vượt giới hạn cho phép ở cửa sổ chuyển đổi |
| Latency sau phục hồi | p95/p99 quay lại gần baseline trong cửa sổ đo |
| RPO | Số acknowledged writes mất không vượt mục tiêu chấp nhận |
| Rejoin | Primary cũ trở lại đúng vai trò replica nếu được yêu cầu |
| Không có retry gây duplicate | Side effect được nhận diện đúng bằng operation ID |
| Monitoring | Có timeline/alert và root-cause evidence đầy đủ |

Không nên tự đưa những ngưỡng như “RTO luôn dưới 2 giây” thành lời hứa mặc định. Các giá trị phải xuất phát từ SLA/SLO của hệ thống và điều kiện staging/production tương ứng.

### 22.1. Cần lặp lại nhiều lần

Một phép test thành công không cho thấy phân bố RTO. Thời gian failover phụ thuộc thời điểm Redis bị kill, khoảng giám sát Sentinel, trạng thái replica và load.

Nên chạy nhiều run với cùng kịch bản, thu:

- Min/median/p95/max recovery duration.
- Số lỗi/thời gian lỗi.
- Số lượng acknowledged writes không tìm thấy sau mỗi run.
- Tỷ lệ run không thể promote replica.
- Tần suất “đã switch-master nhưng app chưa reconnect”.
- Ảnh hưởng khi tiến trình cũ rejoin.

Khi so sánh hai cấu hình, giữ điều kiện load/topology tương đương. Một config failover nhanh hơn nhưng thường mất nhiều write hơn chưa chắc là lựa chọn phù hợp.

## 23. Các lỗi cấu hình thường gặp

**Chỉ chạy một Sentinel và gọi đó là HA hoàn chỉnh.** Một Sentinel có thể là single point of failure cho discovery/failover management; cần xem quorum/đa số và topology thực tế.

**Cấu hình hai Sentinel nhưng không hiểu đa số.** Với số Sentinel chẵn và phân vùng mạng, điều kiện ra quyết định có thể khó hơn mong đợi; thường triển khai số lượng lẻ ít nhất ba Sentinel cho môi trường cần HA.

**Dùng một địa chỉ Redis primary cố định trong Java.** Sau failover, node đó có thể trở thành replica hoặc biến mất.

**Ứng dụng truy cập được Sentinel nhưng không truy cập được địa chỉ primary mới.** Thường gặp trong Docker/NAT hoặc network policy.

**Dùng `GET` thành công để kết luận failover ghi đã hoàn tất.** Replica có thể đọc được dữ liệu cũ, còn đường ghi vẫn lỗi.

**Mặc định mọi lệnh `SET` thành công đã được replicate.** Redis replication thường bất đồng bộ.

**Đo RTO bằng thời điểm Sentinel `+switch-master` duy nhất.** Client reconnect và business recovery có thể xảy ra sau đó.

**Dùng `PING` làm business probe duy nhất.** PING không xác nhận write-path, serializer, cache invalidation hoặc transaction.

**Đặt command timeout rất thấp rồi retry vô hạn.** Có thể tạo retry storm và duplicate cho lệnh không idempotent.

**Không giữ ACK log ngoài Redis khi kiểm thử RPO.** Dữ liệu dùng làm bằng chứng có thể mất cùng hệ thống đang kiểm thử.

**Đếm key hết TTL là dữ liệu mất do failover.** Test RPO cần key không TTL và chính sách bộ nhớ phù hợp.

**Bỏ qua sự khác biệt giữa planned và unplanned failover.** Hai kịch bản có timeline và hành vi client khác nhau.

**Không test khi primary cũ quay lại.** Có thể bỏ sót lỗi định tuyến, cấu hình sai vai trò hoặc xung đột dữ liệu trong giai đoạn rejoin.

**Chỉ thử một lần dưới tải rất thấp.** Không đủ thông tin về p95/p99 hoặc sự ổn định khi ứng dụng có traffic thật.

**Coi Sentinel là cơ chế transaction với database.** Failover không giải quyết dual write hoặc atomic commit xuyên hệ thống.

## 24. Quy trình thực hành đầy đủ

Có thể sử dụng quy trình sau làm khung triển khai test trong môi trường staging:

### Bước 1 – Xác nhận cấu hình

Ghi lại version Redis, Sentinel, Spring Boot, Spring Data Redis, Lettuce/Jedis, topology và cách xác thực. Kiểm tra Spring app dùng Sentinel-aware connection factory.

### Bước 2 – Xác nhận sức khỏe ban đầu

Chạy `INFO replication` trên các data node, `SENTINEL get-master-addr-by-name`, `SENTINEL replicas`, `SENTINEL sentinels`. Xác nhận quorum, replica link và key read/write hoạt động.

### Bước 3 – Khởi động quan sát

Bật probe với key riêng, log lỗi và thời gian. Dùng load nền có giới hạn, lưu ACK sequence bên ngoài Redis để đo RPO.

### Bước 4 – Đo baseline

Quan sát latency và success rate trước khi gây lỗi. Bảo đảm không có Redis timeout, replica sync in progress hoặc quá tải bất thường làm nhiễu phép test.

### Bước 5 – Gây một lỗi có chủ đích

Chọn **một** kịch bản, ví dụ dừng primary thử nghiệm. Ghi thời điểm chính xác và node bị ảnh hưởng. Không gây đồng thời nhiều lỗi nếu chưa có mục tiêu kiểm thử nhiều lỗi rõ ràng.

### Bước 6 – Thu thập các mốc failover

Đọc Sentinel log/event, địa chỉ primary mới và trạng thái replication. Không giả định rằng `+switch-master` xuất hiện cùng lúc trên mọi Sentinel.

### Bước 7 – Xác nhận recovery end-to-end

Chờ probe `SET NX` + `GET` qua Spring Data Redis thành công liên tiếp theo định nghĩa đã chọn. Ghi thời điểm thành công đầu tiên và thời điểm phục hồi ổn định.

### Bước 8 – Đối chiếu dữ liệu

Dùng ACK log để đọc lại các key được xác nhận ghi thành công trên primary mới, tính số missing/mismatch. Nếu có failover với lệnh đang timeout, ghi nhóm trạng thái không xác định riêng.

### Bước 9 – Phục hồi topology thử nghiệm

Đưa primary cũ trở lại lab, xem role và replication. Không ép node cũ lên primary bằng tay nếu điều đó phá topology Sentinel.

### Bước 10 – Tổng hợp báo cáo

Một mẫu báo cáo:

```text
Scenario:            FT-01 - sudden primary process failure
Run ID:              ft-01-run-01
Redis/Sentinel:      <versions>
Spring Data/Lettuce: <versions>

Primary before:      <host:port>
Primary after:       <host:port>
Sentinels alive:     3/3
Replicas healthy:    2/2 before injection

Fault timestamp:     <UTC time>
First app failure:   <UTC time>
Sentinel switch:     <UTC time>
First app success:   <UTC time>
Stable app recovery: <UTC time>

Observed RTO:        <duration from fault to stable recovery>
User-visible outage: <duration by probe definition>
Failed operations:   <count>
Client retries:      <count>
p95/p99 after:       <metrics>

Acknowledged writes: <count>
Missing after:       <count>
Unknown outcome:     <count>
RPO observation:     <count or time window>

Rejoin status:       <result>
Overall status:      PASS / FAIL / INCONCLUSIVE
Notes:               <what happened and limitations>
```

Nếu chưa đủ bằng chứng để biết Redis đã mất dữ liệu hay chỉ đang đọc nhầm replica, ghi `INCONCLUSIVE` thay vì kết luận một cách tùy tiện.

## 25. Những lưu ý nâng cao khi đưa test vào CI

### 25.1. Testcontainers và Docker Compose

Có thể dùng Testcontainers hoặc Docker Compose để chạy nhiều Redis và Sentinel container. Nhưng topology Sentinel trong container có đặc điểm quan trọng:

- Sentinel phải nhìn thấy hostname/IP mà Redis data nodes quảng bá.
- Spring app trong test JVM phải truy cập được địa chỉ mà Sentinel trả về.
- Mapping port từ container ra host **không tự sửa** địa chỉ Redis bên trong câu trả lời Sentinel.
- Các network alias và cấu hình announce cần nhất quán.
- Không được coi container khởi động là đồng nghĩa group/replica đã sync xong.

Một test tích hợp tốt có **readiness condition theo vai trò**, không chỉ check TCP port mở. Ví dụ chờ `SENTINEL get-master-addr-by-name mymaster` có kết quả hợp lệ và cả replica báo liên kết bình thường.

### 25.2. Tách test chức năng và test chaos

CI thông thường có thể chạy:

- Test cấu hình Spring bean và connection.
- Test `SET`/`GET` qua Sentinel.
- Manual failover có kiểm soát.
- Xác nhận client tìm primary mới.

Các kịch bản như network partition, mất quorum, failover dưới tải lớn và kill nhiều node nên ở **pipeline kiểm thử chịu lỗi** riêng với tài nguyên cô lập. Không nên làm CI chung trở nên flaky hoặc phá Redis dùng chung cho những job khác.

### 25.3. Đặt timeout tổng thể cho test harness

Nếu failover không xảy ra vì không đủ quorum hoặc topology hỏng, một test không nên đợi vô hạn.

Ví dụ các giới hạn minh họa:

```text
Max wait for baseline healthy:    30 giây
Max wait for failover outcome:    60 giây
Max wait for stable app recovery: 60 giây
Max test execution duration:      5 phút
```

Giá trị phải điều chỉnh theo lab. Khi vượt hạn, test ghi đủ log và trả kết quả **FAIL** hoặc **INCONCLUSIVE** theo định nghĩa, thay vì treo cả suite.

## 26. Kết luận

**Kiểm thử failover, reconnect và thời gian phục hồi** không chỉ là kiểm tra Sentinel có chọn được primary mới hay không. Đó là phép thử nhiều tầng:

1. **Replication:** replica có đủ dữ liệu và đủ điều kiện thăng cấp không?
2. **Sentinel:** các node giám sát có đạt quorum/đa số, phát hiện lỗi và đổi vai trò đúng không?
3. **Spring Data Redis client:** connection factory có tìm lại endpoint primary, reconnect và định tuyến lệnh chính xác không?
4. **Ứng dụng:** request thật có tiếp tục `SET`/`GET` thành công ổn định sau failover không?
5. **Dữ liệu:** những write đã được xác nhận có còn trên primary mới không, và retry có gây duplicate không?

Hai chỉ số cần tách rõ là **RTO quan sát** (thời gian từ sự cố tới ứng dụng phục hồi theo tiêu chí đã định nghĩa) và **RPO quan sát** (mất dữ liệu đã ACK sau failover). Sentinel giúp tăng khả năng phục hồi, nhưng replication bất đồng bộ vẫn có thể làm mất các ghi gần thời điểm sự cố.

Một phương án kiểm thử có giá trị phải dùng topology nhiều Sentinel/replica, đo qua **Spring Data Redis đúng như application đang dùng**, có probe ghi–đọc và ACK log ngoài Redis, quan sát reconnect cùng Sentinel events, kiểm tra cả primary cũ rejoin và lặp lại nhiều run dưới tải phù hợp. Khi đã định nghĩa rõ tiêu chí thành công và thu thập đủ bằng chứng, hệ thống mới có cơ sở thực tế để nói rằng nó đáp ứng mục tiêu sẵn sàng và khả năng phục hồi mong muốn.
