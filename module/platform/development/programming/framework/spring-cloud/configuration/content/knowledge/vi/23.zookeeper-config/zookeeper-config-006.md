# Kết nối Curator, tái kết nối và lỗi đọc cấu hình

Spring Cloud Zookeeper Config dùng Apache Curator để kết nối ZooKeeper và đọc các giá trị cấu hình được tổ chức dưới dạng znodes. Trong môi trường phân tán, kết nối có thể bị gián đoạn do mạng, leader election, server restart hoặc session hết hạn. Ứng dụng cần hiểu vòng đời kết nối, chính sách retry và cách phân biệt lỗi tạm thời với lỗi cấu hình/quyền truy cập để tránh khởi động thất bại ngoài ý muốn hoặc tiếp tục dùng dữ liệu cũ mà không biết.

Curator cung cấp lớp quản lý kết nối và retry cho ZooKeeper. Spring Cloud Zookeeper tích hợp Curator vào quá trình nạp property source; vì vậy, cần kiểm tra cả trạng thái Curator lẫn cách Spring Config Client xử lý khi không đọc được znode.

## 1. Vai trò của Curator trong Spring Cloud Zookeeper Config

Apache Curator là thư viện client cấp cao cho Apache ZooKeeper. Curator quản lý kết nối, session, retry và các thao tác đọc/ghi znode. Spring Cloud Zookeeper dùng Curator để truy cập dữ liệu cấu hình trong ZooKeeper và đưa dữ liệu phù hợp vào Spring `Environment`.

Luồng đọc cấu hình cơ bản:

1. Spring Boot khởi tạo phần tích hợp Spring Cloud Zookeeper Config.
2. Curator tạo kết nối đến một hoặc nhiều ZooKeeper server trong connect string.
3. Client xác thực và truy cập namespace/root path được cấu hình.
4. Spring Cloud Zookeeper tìm các context dùng chung, application và profile.
5. Curator đọc các znode chứa property.
6. Spring chuyển kết quả thành `PropertySource` và đưa vào `Environment`.

Curator chịu trách nhiệm kết nối và thao tác với ZooKeeper; Spring Cloud Zookeeper Config chịu trách nhiệm ánh xạ context cấu hình thành property source. Hai lớp có thể phát sinh lỗi khác nhau, nên log cần giúp xác định lỗi nằm ở kết nối, quyền ZooKeeper, path hay phân tích dữ liệu.

## 2. Dependency và cấu hình kết nối

Thêm starter Config của Spring Cloud Zookeeper vào ứng dụng:

```gradle
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-zookeeper-config'
}
```

Phiên bản dependency nên được quản lý bằng Spring Cloud release train tương thích với Spring Boot của dự án. Starter kéo theo các thành phần Curator cần thiết; thông thường không cần tự tạo một Curator client thứ hai chỉ để đọc cấu hình.

Ví dụ cấu hình client:

```yaml
spring:
  application:
    name: orders-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      config:
        enabled: true
        root: config
        default-context: application
        profile-separator: ","
```

`connect-string` liệt kê các ZooKeeper endpoint mà client có thể kết nối. Cần bảo đảm DNS, route mạng và firewall cho phép workload truy cập các host/cổng đó. Với ZooKeeper ensemble, nên cung cấp danh sách thành viên ổn định thay vì chỉ dựa vào một node có thể trở thành điểm lỗi đơn.

Các thuộc tính bootstrap và Config Data import có thể khác nhau theo thế hệ Spring Cloud Zookeeper. Hãy dùng đúng cơ chế nạp cấu hình được hỗ trợ bởi release train của dự án; phần kết nối Curator và phân loại lỗi vẫn áp dụng cho cả hai cách.

## 3. Connect string, session và timeout

Khi chẩn đoán kết nối, cần phân biệt các khái niệm thời gian:

| Khái niệm | Ý nghĩa | Khi vượt giới hạn |
|---|---|---|
| Connection timeout | Thời gian client chờ thiết lập kết nối đến ZooKeeper server. | Lần kết nối hiện tại thất bại; Curator có thể thử lại theo retry policy. |
| Session timeout | Khoảng thời gian ZooKeeper session có thể mất liên lạc trước khi server xem session hết hạn. Giá trị thực tế được thương lượng với server trong giới hạn server cho phép. | Session có thể chuyển sang trạng thái `LOST`; ephemeral nodes của session cũ bị xóa. |
| Operation timeout | Thời gian chờ một thao tác ZooKeeper hoàn tất theo cơ chế client/API đang dùng. | Thao tác có thể báo timeout dù trạng thái phía server cần được kiểm tra để biết đã thực hiện hay chưa. |
| Retry delay | Khoảng nghỉ trước khi thử lại một thao tác hoặc kết nối. | Tăng thời gian phục hồi nhưng giúp tránh retry dồn dập. |

Connection timeout ngắn không đồng nghĩa session timeout ngắn. Nếu mạng chập chờn trong thời gian ngắn, client có thể mất kết nối nhưng session vẫn còn hiệu lực. Nếu mất liên lạc quá lâu, ZooKeeper có thể hết hạn session và client phải tạo session mới.

Không đặt session timeout quá thấp chỉ để phát hiện lỗi nhanh. Mạng nội bộ có thể có độ trễ trong lúc rolling restart hoặc leader election; timeout quá thấp làm session bị hết hạn thường xuyên, gây mất ephemeral nodes và tạo thêm tải khởi tạo.

## 4. Chính sách retry của Curator

Curator dùng `RetryPolicy` để quyết định có thử lại khi thao tác gặp lỗi tạm thời hay không. Một lựa chọn phổ biến là `ExponentialBackoffRetry`: khoảng nghỉ tăng dần theo số lần thử và bị giới hạn bởi số lần retry/cap cấu hình.

Ví dụ Java minh họa API Curator:

```java
RetryPolicy retryPolicy = new ExponentialBackoffRetry(
    1_000,  // thời gian nghỉ cơ sở, mili giây
    5,      // số lần thử lại tối đa
    10_000  // giới hạn thời gian nghỉ, mili giây
);

CuratorFramework client = CuratorFrameworkFactory.builder()
    .connectString("zk-1:2181,zk-2:2181,zk-3:2181")
    .connectionTimeoutMs(5_000)
    .sessionTimeoutMs(20_000)
    .retryPolicy(retryPolicy)
    .build();

client.start();
```

Đây là ví dụ API Curator độc lập để giải thích retry policy và timeout. Trong ứng dụng Spring Cloud Zookeeper Config, nên sử dụng Curator client do Spring quản lý và cấu hình qua các thuộc tính được phiên bản thư viện hỗ trợ; không tạo thêm client thủ công nếu không có nhu cầu rõ ràng.

Retry có ích với lỗi tạm thời như `ConnectionLoss` hoặc một số timeout mạng. Retry không thể sửa lỗi `NoAuth` do ACL sai, `NoNode` do path không tồn tại hoặc dữ liệu YAML/properties không hợp lệ. Thử lại vô hạn với lỗi cấu hình cố định chỉ làm kéo dài thời gian khởi động và che giấu nguyên nhân.

Khi nhiều instance cùng khởi động, retry đồng loạt có thể tạo thundering herd. Dùng retry có giới hạn, backoff phù hợp và jitter nếu cơ chế hỗ trợ; tránh để tất cả client liên tục dồn request vào ensemble đang phục hồi.

## 5. Trạng thái kết nối của Curator

Curator phát các sự kiện `ConnectionState` để ứng dụng theo dõi vòng đời kết nối:

| Trạng thái | Ý nghĩa vận hành | Hành động cần cân nhắc |
|---|---|---|
| `CONNECTED` | Client đã thiết lập kết nối và session. | Có thể thực hiện thao tác theo quyền được cấp. |
| `SUSPENDED` | Kết nối bị gián đoạn tạm thời; client chưa biết session có còn hiệu lực hay không. | Coi thao tác ghi là không chắc chắn; tránh giả định trạng thái đã được đồng bộ. |
| `RECONNECTED` | Kết nối được khôi phục; session có thể vẫn còn hoặc đã được tái lập tùy quá trình. | Đồng bộ lại trạng thái cần thiết và xác minh watcher/đọc cấu hình. |
| `LOST` | Session đã hết hạn hoặc không thể tiếp tục sử dụng. | Tạo lại các tài nguyên gắn với session, kiểm tra ephemeral nodes và khôi phục đăng ký/watch. |

Có thể quan sát trạng thái bằng `ConnectionStateListener`:

```java
curatorFramework.getConnectionStateListenable()
    .addListener((client, state) -> {
        switch (state) {
            case CONNECTED -> log.info("ZooKeeper connected");
            case SUSPENDED -> log.warn("ZooKeeper connection suspended");
            case RECONNECTED -> log.info("ZooKeeper reconnected");
            case LOST -> log.error("ZooKeeper session lost");
        }
    });
```

Đây là đoạn minh họa quan sát một Curator client. Nếu Spring Cloud Zookeeper đã tạo client, hãy đăng ký listener thông qua cơ chế bean/customizer được phiên bản hỗ trợ thay vì tự tạo client khác.

`SUSPENDED` không chứng minh session đã hết hạn. `LOST` là tín hiệu nghiêm trọng hơn: các ephemeral node gắn với session cũ không còn tồn tại. Nếu ứng dụng dùng Curator recipes hoặc watcher, kiểm tra cách recipe tái đăng ký sau khi session được tạo lại.

## 6. Watcher và tái đăng ký sau reconnect

ZooKeeper watch truyền thống là one-shot: sau khi watch được kích hoạt, client cần đăng ký lại để tiếp tục nhận thay đổi. Curator cung cấp các recipe và cache như `NodeCache`, `PathChildrenCache` (các API cũ) hoặc `CuratorCache` ở phiên bản mới để đơn giản hóa theo dõi và tái đăng ký.

Với Spring Cloud Zookeeper Config, cơ chế watcher có thể theo dõi các context cấu hình và kích hoạt reload/refresh khi znode thay đổi. Khi kết nối bị `SUSPENDED`, client có thể tạm thời không nhận được event. Sau `RECONNECTED`, watcher/recipe cần hoạt động trở lại; sau `LOST`, session mới có thể yêu cầu tạo lại những đăng ký gắn với session cũ.

Không nên tự giả định watcher đã phục hồi chỉ vì log báo `RECONNECTED`. Hãy kiểm tra behavior của phiên bản Spring Cloud Zookeeper/Curator đang dùng và xác minh bằng một thay đổi KV thử nghiệm sau reconnect.

Refresh cũng có giới hạn: watcher phát hiện thay đổi và yêu cầu client nạp lại property source, nhưng không tự thay đổi mọi bean hay tài nguyên startup-only. Với thuộc tính cần restart, vẫn phải thực hiện rollout/restart theo quy trình ứng dụng.

## 7. Các nhóm lỗi đọc cấu hình thường gặp

Lỗi đọc cấu hình có thể được phân thành nhóm kết nối, session, path, quyền và dữ liệu:

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ConnectionLoss` | Mất kết nối giữa thao tác; network, server restart hoặc leader election. | Kiểm tra ensemble/network, retry có giới hạn và đọc lại trạng thái sau reconnect. |
| `OperationTimeout` | Thao tác không hoàn tất trong thời gian cho phép; server tải cao hoặc mạng chậm. | Kiểm tra latency, ensemble health, timeout và số lần retry. |
| `SessionExpired` | Session hết hạn sau thời gian mất liên lạc quá lâu hoặc server không còn chấp nhận session cũ. | Chờ Curator tái lập session, khôi phục watcher/ephemeral state và xác minh lại dữ liệu. |
| `NoNode` | Znode path không tồn tại hoặc context chưa được tạo. | Kiểm tra root, application, profile và quy trình tạo dữ liệu. |
| `NoAuth` | ACL không cho phép đọc path hoặc credential không đúng. | Kiểm tra auth scheme, identity và ACL trên từng path. |
| `BadVersion` | Thao tác có version check nhưng znode đã thay đổi. | Đọc lại version và xử lý xung đột thay vì lặp lại ghi mù. |
| Parse/binding error | Dữ liệu có định dạng sai hoặc kiểu không tương thích. | Kiểm tra giá trị znode và mapping property. |
| Giá trị cũ sau reconnect | Watcher chưa được đăng ký lại, client chưa refresh hoặc cache chưa cập nhật. | Xác minh watch, trigger refresh và đọc lại property source. |

Không phải mọi lỗi ZooKeeper đều nên retry. Lỗi quyền và lỗi path thường cần sửa cấu hình hoặc ACL; retry không làm chúng biến mất.

## 8. Phân biệt lỗi lúc startup và lỗi khi ứng dụng đang chạy

### Lỗi khi startup

Nếu Config Client cần ZooKeeper để nạp cấu hình bắt buộc, việc không kết nối được có thể làm ứng dụng khởi động thất bại. Cần quyết định rõ:

- Cấu hình ZooKeeper là bắt buộc hay có thể bỏ qua trong môi trường đó?
- Có cho phép dùng cấu hình mặc định/local khi ZooKeeper tạm thời không sẵn sàng không?
- Startup timeout và retry có nằm trong ngân sách triển khai không?
- Readiness probe có chỉ báo instance chưa sẵn sàng cho đến khi lấy được cấu hình hợp lệ không?

Không bật chế độ optional chỉ để pipeline khởi động xanh nếu ứng dụng cần secret hoặc endpoint từ ZooKeeper để hoạt động an toàn. Nếu fallback được cho phép, phải xác định chính xác giá trị mặc định và hành vi khi thiếu cấu hình.

### Lỗi khi runtime

Khi kết nối mất sau startup, ứng dụng có thể tiếp tục chạy với giá trị đã nạp trong bộ nhớ. Điều đó không có nghĩa cấu hình mới vẫn được nhận. Cần theo dõi trạng thái Curator, cảnh báo khi mất kết nối kéo dài và xác minh refresh sau khi reconnect.

Nếu ứng dụng dùng giá trị cache hoặc bean đã khởi tạo từ cấu hình, việc đọc lại znode thành công cũng không đảm bảo mọi consumer đã đổi sang giá trị mới. Kiểm tra bean lifecycle và refresh strategy riêng.

## 9. Thiết kế phục hồi và xử lý lỗi đọc

Một quy trình phục hồi có thể gồm:

1. Phân loại lỗi: connection loss, timeout, session expired, no node, no auth hay parse error.
2. Với lỗi mạng tạm thời, để Curator áp dụng retry policy có giới hạn và backoff.
3. Theo dõi `ConnectionState` để biết client đang suspended, reconnected hay lost.
4. Sau reconnect/session mới, xác minh watcher và cache đã hoạt động lại.
5. Đọc lại các context cấu hình cần thiết và xác nhận property source/version hiện tại.
6. Nếu dữ liệu thiếu hoặc quyền sai, sửa path/ACL thay vì retry vô hạn.
7. Nếu cấu hình mới không hợp lệ, giữ instance ở trạng thái không sẵn sàng hoặc rollback theo chính sách; không âm thầm thay bằng giá trị mặc định không an toàn.
8. Ghi nhận thời gian gián đoạn, số lần retry và thời điểm phục hồi để phân tích nguyên nhân.

Với thao tác đọc, retry thường an toàn hơn thao tác ghi. Nếu thao tác ghi bị timeout, client có thể không biết server đã commit hay chưa; cần đọc lại znode/version trước khi gửi lại để tránh ghi trùng hoặc ghi đè dữ liệu mới.

## 10. Bảo mật kết nối và ACL

ZooKeeper có thể bảo vệ dữ liệu bằng ACL và cơ chế xác thực như SASL hoặc digest tùy cấu hình cluster. Client chỉ nên có quyền đọc các context mà ứng dụng cần.

Các nguyên tắc vận hành:

- Không dùng danh tính quản trị ZooKeeper cho Config Client runtime.
- Tách identity theo ứng dụng và môi trường khi yêu cầu bảo mật cần cô lập.
- Cấp quyền read trên root/context cần thiết; chỉ pipeline cấu hình được quyền write.
- Bảo vệ credential bằng secret manager và không ghi credential vào Git.
- Dùng TLS cho client-server connection khi ZooKeeper deployment hỗ trợ và được cấu hình đúng.
- Kiểm soát quyền đọc log vì exception hoặc debug trace có thể tiết lộ path và dữ liệu cấu hình.
- Theo dõi ACL denial như một lỗi authorization, không xử lý bằng cách cấp quyền `world:anyone` rộng hơn.

Nếu ZooKeeper dùng namespace hoặc chroot trong connect string, bảo đảm path mà Spring Cloud Zookeeper tạo ra nằm trong namespace đúng. Chroot không thay thế ACL; nó chỉ giới hạn không gian path mà client nhìn thấy.

## 11. Kiểm tra kết nối và đọc znode

Trước khi kiểm tra Spring, hãy xác nhận ZooKeeper ensemble có thể truy cập từ đúng runtime của ứng dụng. Dùng `zkCli.sh` hoặc công cụ quản trị tương ứng để kiểm tra connect string và path; không chỉ kiểm tra từ laptop phát triển.

Ví dụ mở CLI:

```bash
zkCli.sh -server zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
```

Trong CLI, có thể kiểm tra path:

```text
ls /config
ls /config/orders-service
get /config/orders-service/app.payment.timeout
```

Các path trên là ví dụ theo layout minh họa; dùng đúng root/context và cấu trúc znode của ứng dụng. Nếu CLI không kết nối được từ cùng môi trường mạng, cần xử lý DNS, route, firewall, TLS hoặc auth trước khi điều tra Spring property binding.

Sau đó kiểm tra phía ứng dụng:

1. Xác nhận `spring.cloud.zookeeper.connect-string` đúng.
2. Xác nhận root, default context, application name và profile separator.
3. Kiểm tra Curator connection state và retry logs.
4. Xác nhận ACL cho phép đọc từng path.
5. Kiểm tra property source được tạo và giá trị cuối trong Spring Environment.
6. Thử thay đổi một znode không nhạy cảm để xác minh watcher/reload sau reconnect.

## 12. Theo dõi và kiểm thử sự cố

Nên theo dõi tối thiểu:

- Trạng thái kết nối Curator: connected, suspended, reconnected, lost.
- Số lần retry và thời gian từ khi mất kết nối đến khi phục hồi.
- Tỷ lệ lỗi đọc theo loại exception.
- Thời gian đọc znode và thời gian nạp property source.
- Số lần session expired và watcher được khôi phục.
- Tuổi của cấu hình đang dùng so với phiên bản mong muốn.
- Số instance chưa nhận được cấu hình mới sau một lần cập nhật.

Trong môi trường test, mô phỏng các tình huống:

1. Tạm chặn kết nối đến một ZooKeeper node.
2. Restart một server hoặc thực hiện rolling restart ensemble theo quy trình test.
3. Tạo gián đoạn đủ lâu để kiểm tra session expiration.
4. Xóa một znode cần thiết để xác minh `NoNode` được xử lý như lỗi dữ liệu.
5. Thu hồi ACL read để xác minh `NoAuth` không bị retry vô hạn.
6. Cập nhật znode khi client đang reconnect để kiểm tra watcher có nhận thay đổi sau phục hồi.

Không thực hiện fault injection trên cluster production nếu chưa có kế hoạch và quyền vận hành phù hợp. Các thử nghiệm nên chạy ở môi trường cô lập với dữ liệu không nhạy cảm.

## 13. Lỗi thường gặp và hướng xử lý nhanh

| Triệu chứng | Hướng kiểm tra đầu tiên |
|---|---|
| Startup treo khi ZooKeeper không sẵn sàng | Connect string, timeout, retry count, block-until-connected behavior và startup budget. |
| Kết nối được một lúc rồi mất | Network instability, server restart, session timeout và Curator state transitions. |
| Reconnect thành công nhưng không thấy config update | Watcher/cache re-registration, reload strategy và property source refresh. |
| `NoNode` khi ứng dụng khởi động | Root/context/application/profile path có tồn tại và đúng quy ước không? |
| `NoAuth` | ACL, auth scheme, credential và namespace/chroot. |
| Retry liên tục làm tải tăng | Phân biệt lỗi transient với lỗi cố định; giới hạn retry và dùng backoff. |
| Chỉ một replica bị lỗi | So sánh connect string, DNS, network policy, identity và runtime config của replica đó. |
| Client dùng giá trị cũ sau khi đọc thành công | Kiểm tra property source precedence, refresh event và bean đã capture giá trị lúc startup. |

## 14. Tổng kết

- Spring Cloud Zookeeper Config dùng Apache Curator để kết nối ZooKeeper và đọc znode thành Spring property source.
- `connect-string` phải trỏ đến ensemble có thể truy cập từ runtime; cần phân biệt connection timeout, session timeout, operation timeout và retry delay.
- Curator `RetryPolicy` như `ExponentialBackoffRetry` xử lý lỗi tạm thời với số lần thử và backoff có giới hạn.
- `SUSPENDED` là gián đoạn chưa xác định session; `RECONNECTED` báo kết nối phục hồi; `LOST` báo session cũ đã hết hạn.
- Sau reconnect/session mới, cần xác minh watcher, cache và trạng thái cấu hình đã được khôi phục.
- `ConnectionLoss` và timeout có thể tạm thời; `NoNode`, `NoAuth` và parse error thường cần sửa path, ACL hoặc dữ liệu thay vì retry vô hạn.
- Lỗi startup và lỗi runtime cần chính sách khác nhau; fallback chỉ được dùng khi có thể hoạt động an toàn với cấu hình thiếu.
- Theo dõi Curator state, retry, session expiration, read latency và phiên bản cấu hình để phát hiện client bị stale.
