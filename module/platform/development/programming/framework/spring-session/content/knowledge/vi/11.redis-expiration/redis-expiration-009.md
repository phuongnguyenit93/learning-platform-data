# Khôi phục sau mất kết nối listener hoặc thay đổi nút Redis

Spring Session có thể dựa vào Redis keyspace notifications để nhận biết session bị xóa hoặc hết hạn và phát các sự kiện vòng đời như SessionDeletedEvent hay SessionExpiredEvent. Các thông báo này được truyền qua Redis Pub/Sub. Nếu listener mất kết nối, Redis đổi primary hoặc ứng dụng khởi động lại trong lúc thông báo được phát, listener có thể bỏ lỡ sự kiện.

Điều cần nhớ khi thiết kế phục hồi là keyspace notification không phải hàng đợi bền vững. Redis không lưu lại thông báo để gửi bù cho subscriber vừa kết nối lại. Vì vậy, cần khôi phục subscription, kiểm tra lại trạng thái session trong repository và đối soát những tác vụ phụ trợ có thể bị bỏ lỡ. Bản thân TTL của session vẫn được Redis áp dụng; mất event không đồng nghĩa session hết hạn trở lại hợp lệ.

## 1. Redis keyspace notification và giới hạn khi listener ngắt kết nối

Redis có thể phát thông báo khi một key bị xóa hoặc hết hạn. Với key-event notification, channel có dạng:

~~~text
__keyevent@0__:expired
__keyevent@0__:del
~~~

Spring Session Redis có thể đăng ký nhận các thông báo cần thiết để phát application event. Cấu hình Redis thường cần bật nhóm event tương ứng, ví dụ:

~~~text
notify-keyspace-events Egx
~~~

Trong đó E bật key-event notification, g bao gồm lệnh generic như DEL, và x bao gồm sự kiện key hết hạn. Tên channel và tập event thực tế phụ thuộc database, repository và phiên bản thư viện.

Pub/Sub có đặc điểm quan trọng:

- Redis gửi thông báo đến các subscriber đang lắng nghe tại thời điểm phát.
- Subscriber mất kết nối không có offset hoặc vị trí để yêu cầu phát lại thông báo cũ.
- Thông báo có thể bị mất trong lúc listener ngắt mạng, reconnect hoặc chuyển node.
- Redis expiration không nhất thiết phát thông báo đúng thời điểm TTL chạm 0; quá trình xử lý expiration có thể trễ.

Do đó, listener nhận được một event không phải là bằng chứng rằng tất cả event đều đã được nhận. Số lượng event quan sát được cũng không phải nguồn dữ liệu tuyệt đối để tính số session đang tồn tại.

## 2. Phân biệt trạng thái session và event phụ trợ

Session được lưu trong Redis với TTL. Khi key hết hạn, Redis không còn giữ dữ liệu session đó. Khi request tiếp theo mang session ID cũ đến ứng dụng, repository không tìm thấy session hợp lệ và ứng dụng phải xử lý như phiên đã hết hạn.

Event là tín hiệu để ứng dụng thực hiện công việc phụ trợ, chẳng hạn:

- Cập nhật số liệu tổng hợp về số phiên hết hạn.
- Dọn một bản ghi phụ trợ gắn với session.
- Ghi nhận một sự kiện audit không chứa session ID thô.
- Thông báo cho thành phần khác rằng người dùng cần xác thực lại ở request sau.

Nếu listener bị ngắt, TTL của session vẫn có hiệu lực. Những việc có thể bị chậm hoặc bỏ lỡ là các hành động phụ trợ chỉ được kích hoạt bởi event.

| Thành phần | Điều xảy ra khi listener mất kết nối |
| --- | --- |
| TTL của session trong Redis | Vẫn được Redis quản lý nếu dữ liệu và cấu hình Redis còn nguyên |
| Request dùng session ID đã hết hạn | Repository không tìm thấy session hợp lệ |
| SessionExpiredEvent | Có thể không được phát trong ApplicationContext nếu notification bị bỏ lỡ |
| Bản ghi phụ trợ của ứng dụng | Có thể còn tồn tại cho đến khi được đối soát hoặc dọn theo cách khác |
| Metric đếm event | Có thể thấp hơn số session thực sự hết hạn |

Không dùng event làm cơ chế duy nhất để thu hồi quyền truy cập quan trọng hoặc thực hiện giao dịch tài chính. Quyết định cho phép request phải dựa trên session và quyền hiện tại được kiểm tra ở backend.

## 3. Điều gì xảy ra khi listener bị ngắt?

Một số nguyên nhân thường gặp:

- Redis restart, failover hoặc chuyển primary.
- Mạng giữa ứng dụng và Redis bị gián đoạn.
- Kết nối Pub/Sub bị server hoặc proxy đóng.
- Redis ACL thay đổi và tài khoản ứng dụng không còn quyền subscribe.
- Redis managed service thay đổi endpoint hoặc topology.
- Ứng dụng khởi động lại trong lúc có key hết hạn.
- Listener callback xử lý quá lâu hoặc bị lỗi liên tục, khiến hệ thống listener khó theo kịp.

Luồng lỗi khái quát:

~~~mermaid
flowchart TD
    A["Redis phát keyspace notification"] --> B{"Listener đang subscribe?"}
    B -->|Có| C["Spring Session nhận notification"]
    C --> D["Phát SessionDeletedEvent / SessionExpiredEvent"]
    B -->|Không| E["Notification không được lưu để phát lại"]
    E --> F["Listener reconnect"]
    F --> G["Nhận notification mới"]
    F --> H["Đối soát trạng thái session và dữ liệu phụ trợ"]
~~~

Khi kết nối trở lại, listener có thể nhận những thông báo mới từ thời điểm subscribe lại. Nó không thể tự yêu cầu Redis gửi toàn bộ event đã phát trong khoảng gián đoạn.

## 4. Khôi phục subscription trong Spring

Spring Data Redis cung cấp RedisMessageListenerContainer để quản lý subscription, kết nối và đăng ký listener. Container có cơ chế khôi phục khi kết nối subscription gặp lỗi. Với listener do ứng dụng tự quản lý, có thể cấu hình khoảng thời gian thử kết nối lại và dùng một connection factory hỗ trợ topology đang triển khai.

Ví dụ một listener riêng của ứng dụng nhận notification hết hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import java.nio.charset.StandardCharsets;

@Configuration
class AuxiliaryRedisListenerConfiguration {

    @Bean
    MessageListener expiryListener() {
        return (Message message, byte[] pattern) -> {
            String expiredKey =
                new String(message.getBody(), StandardCharsets.UTF_8);
            // Chỉ cập nhật dữ liệu phụ trợ; không ghi key hoặc session ID vào log.
            handleExpiredAuxiliaryRecord(expiredKey);
        };
    }

    private static void handleExpiredAuxiliaryRecord(String expiredKey) {
        // Tìm và dọn bản ghi phụ trợ theo cách idempotent.
    }

    @Bean
    RedisMessageListenerContainer auxiliaryListenerContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener expiryListener) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setRecoveryInterval(5_000L);
        container.addMessageListener(
            expiryListener,
            new ChannelTopic("__keyevent@0__:expired")
        );
        return container;
    }
}
~~~

Đây là ví dụ cho listener phụ trợ do ứng dụng tự đăng ký. Spring Session có thể tự cấu hình listener container nội bộ để theo dõi các sự kiện session; không tạo thêm container chỉ để thay thế cơ chế nội bộ đó. Nếu cần tùy chỉnh cấu hình của Spring Session, hãy dùng điểm mở rộng được hỗ trợ bởi phiên bản dependency đang chạy.

setRecoveryInterval quy định khoảng chờ giữa các lần thử phục hồi của container. Chọn khoảng thời gian phù hợp với khả năng chịu tải và thời gian phục hồi mong muốn. Khoảng thử quá ngắn có thể tạo nhiều lần reconnect khi Redis đang lỗi; khoảng quá dài làm thời gian gián đoạn tăng.

Một container reconnect thành công chưa đủ để chứng minh toàn bộ chức năng đã phục hồi. Cần xác nhận subscription thực sự được đăng ký lại trên node đang nhận ghi, listener không còn lỗi ACL và một session thử nghiệm có thể phát event đến handler.

## 5. Kiểm tra cấu hình Redis và quyền subscribe

Khi listener không nhận được event, kiểm tra Redis trước khi thay đổi mã ứng dụng:

~~~bash
redis-cli CONFIG GET notify-keyspace-events
~~~

Với Redis cho phép cấu hình động và tài khoản có quyền phù hợp, có thể kiểm tra hoặc bật cấu hình trong môi trường thử nghiệm:

~~~bash
redis-cli CONFIG SET notify-keyspace-events Egx
~~~

Không phải Redis managed service nào cũng cho phép CONFIG GET hoặc CONFIG SET. Một số nhà cung cấp quản lý tham số qua console hoặc parameter group. Trong trường hợp đó, kiểm tra trạng thái cấu hình ở cấp dịch vụ và quyền Pub/Sub được cấp cho user của ứng dụng.

Nếu Spring Session được cấu hình để không tự thay đổi Redis, có thể dùng ConfigureRedisAction.NO_OP:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.ConfigureRedisAction;

@Configuration
class SessionRedisConfiguration {

    @Bean
    ConfigureRedisAction configureRedisAction() {
        return ConfigureRedisAction.NO_OP;
    }
}
~~~

NO_OP chỉ ngăn ứng dụng chạy lệnh cấu hình Redis lúc khởi động. Nó không tự bật keyspace notifications. Quản trị viên hoặc cấu hình dịch vụ vẫn phải bật đúng nhóm event. Đồng thời, tài khoản Redis cần có quyền subscribe vào channel phù hợp và quyền đọc/ghi key session theo repository.

## 6. Khi Redis đổi primary hoặc topology thay đổi

Trong môi trường có replica và failover, một node đang giữ kết nối subscription có thể bị thay thế. Kết nối cũ có thể bị đóng hoặc vẫn trỏ đến node không còn là primary. Connection factory và client Redis cần nhận biết topology mới để kết nối lại đúng endpoint.

Các điểm cần kiểm tra:

- Ứng dụng kết nối qua endpoint ổn định của Sentinel, cluster client hoặc dịch vụ managed, thay vì cố định vào địa chỉ của một node có thể bị thay thế.
- Redis connection factory và client driver có cơ chế phát hiện failover hoặc refresh topology phù hợp với môi trường.
- Listener container có thể mở lại subscription sau khi connection factory chuyển sang node phù hợp.
- ACL, TLS, username/password và quyền Pub/Sub giống nhau trên các node hoặc endpoint mà ứng dụng có thể kết nối.
- Redis keyspace notifications được bật trên các node có thể phát keyspace event liên quan.

Với Redis Sentinel, client thường dùng cấu hình Sentinel để tìm primary hiện tại. Khi failover, cần xác nhận connection factory có phát hiện primary mới và các kết nối đang hoạt động được tạo lại. Với Redis Cluster, keyspace notification gắn với node xử lý key; hành vi subscribe và phân phối notification phụ thuộc topology, client và dịch vụ cung cấp. Không giả định subscription trên một node sẽ tự nhận event cho mọi shard.

Một số dịch vụ Redis quản lý có endpoint proxy hoặc endpoint cluster riêng. Hãy theo tài liệu của nhà cung cấp để cấu hình subscription và kiểm tra event trên đúng node. Một bài kiểm thử với Redis đơn lẻ không chứng minh listener hoạt động đúng sau failover hoặc trong cluster.

## 7. Failover có thể làm mất dữ liệu session không?

Mất kết nối listener và mất dữ liệu session là hai sự cố khác nhau. Khi Redis failover, dữ liệu được phục hồi từ replica hoặc cơ chế HA. Tính nhất quán cuối cùng phụ thuộc cấu hình replication, persistence, failover và dịch vụ Redis.

Nếu một lần ghi session chưa kịp replicate trước khi primary lỗi, failover có thể làm mất một số cập nhật gần nhất tùy topology và chính sách durability. Nếu key session vẫn tồn tại, TTL và repository tiếp tục quản lý nó. Nếu dữ liệu session bị mất, request mang ID cũ sẽ không tìm thấy session và người dùng có thể cần đăng nhập lại.

Không tự động tạo session mới trong listener recovery để thay thế session bị mất. Việc tạo session là trách nhiệm của luồng request và chính sách xác thực. Sau failover:

1. Xác nhận primary hoặc cluster đã ổn định.
2. Kiểm tra kết nối đọc/ghi và trạng thái TTL.
3. Kiểm tra listener đã subscribe lại.
4. Gửi request thử với session còn tồn tại để xác nhận repository đọc được.
5. Gửi request với session ID đã hết hạn hoặc bị xóa để xác nhận ứng dụng xử lý đúng.
6. Đối soát các dữ liệu phụ trợ có thể đã bỏ lỡ event.

Nếu dữ liệu session bị mất do sự cố Redis, xử lý theo chính sách nghiệp vụ và bảo mật: yêu cầu xác thực lại khi cần, không phục hồi session cũ một cách mù quáng từ dữ liệu backup đã lỗi thời.

## 8. Đối soát sau khi listener hoạt động trở lại

Vì Redis Pub/Sub không phát lại event cũ, reconnect chỉ khôi phục khả năng nhận event mới. Muốn xử lý phần việc bị bỏ lỡ, cần một bước reconciliation (đối soát) độc lập với subscription.

Có thể thiết kế theo các hướng:

### Kiểm tra trạng thái khi có request

Với dữ liệu phụ trợ gắn với session, trước khi sử dụng dữ liệu đó trong một request, kiểm tra session tương ứng còn tồn tại và hợp lệ qua repository hoặc lớp dịch vụ quản lý phiên. Nếu không còn session, dọn dữ liệu phụ trợ theo cách idempotent.

### Đối soát theo chỉ mục nghiệp vụ

Nếu ứng dụng duy trì bảng hoặc kho riêng cho các tác vụ gắn với phiên, hãy lưu session reference, thời điểm hết hạn dự kiến và trạng thái xử lý. Một job định kỳ có thể tìm các bản ghi quá hạn, xác minh session còn tồn tại bằng API repository được hỗ trợ, rồi dọn bản ghi phụ trợ. Cần xử lý trường hợp session được gia hạn hoặc cập nhật thời hạn trong lúc job chạy.

### Đối soát theo người dùng

Với FindByIndexNameSessionRepository, ứng dụng có thể tìm các session theo principal name. Cách này phù hợp khi đối soát trạng thái phiên của một người dùng hoặc thu hồi phiên theo người dùng. Không phải API này cung cấp danh sách toàn bộ session của toàn hệ thống; cần thiết kế chỉ mục nghiệp vụ nếu cần tổng hợp trên diện rộng.

Không dựa vào tên key nội bộ của Spring Session để tự viết truy vấn hoặc xóa dữ liệu nếu chưa có hợp đồng được hỗ trợ cho phiên bản đang dùng. Không dùng KEYS trên Redis production để quét toàn bộ key vì thao tác có thể chặn server. Nếu có yêu cầu quét key, cần thiết kế scan theo lô, giới hạn tốc độ và hiểu rõ cấu trúc key của phiên bản cụ thể.

Một reconciliation job nên:

- Có thể chạy lặp mà không tạo tác dụng phụ sai.
- Chia lô nhỏ, có giới hạn tốc độ và timeout.
- Ghi metric số bản ghi đã kiểm tra, đã dọn và lỗi.
- Hỗ trợ nhiều instance cùng chạy bằng cơ chế claim/lock hoặc phân vùng công việc nếu cần tránh xử lý trùng.
- Có thể chạy lại sau khi lỗi mà không làm mất dữ liệu hợp lệ.

## 9. Thiết kế tác vụ listener idempotent

Trong lúc failover hoặc reconnect, cùng một thay đổi có thể được quan sát lại qua nhiều đường xử lý hoặc nhiều instance. Handler nên idempotent, nghĩa là xử lý lặp cùng một sự kiện không làm trạng thái sai.

Ví dụ một bản ghi phụ trợ có trạng thái:

~~~text
ACTIVE -> CLEANED
~~~

Handler có thể thực hiện cập nhật có điều kiện chỉ khi trạng thái còn ACTIVE. Nếu event đến lần thứ hai, bản ghi đã là CLEANED, nên lần xử lý sau không tạo thêm tác dụng phụ.

Một số nguyên tắc:

- Dùng khóa nghiệp vụ hoặc event identifier ổn định để chống trùng nếu có.
- Dùng cập nhật có điều kiện hoặc thao tác xóa an toàn khi bản ghi đã không còn.
- Không gửi email, phát hành hóa đơn hoặc thực hiện giao dịch không thể đảo ngược trực tiếp chỉ từ một keyspace notification.
- Với tác vụ quan trọng, ghi yêu cầu xử lý vào hàng đợi bền vững hoặc outbox trước khi thực hiện.
- Có retry với backoff và dead-letter cho tác vụ thất bại.

Application event trong Spring không tự cung cấp bảo đảm exactly-once. @Async cũng không làm cho event trở nên bền vững: nếu tiến trình dừng sau khi nhận event nhưng trước khi hoàn thành công việc, tác vụ có thể bị mất.

## 10. Quy trình phục hồi sau sự cố

Một quy trình vận hành có thể thực hiện theo thứ tự:

1. **Xác định phạm vi:** listener nào mất kết nối, Redis node nào đổi vai trò, thời điểm bắt đầu và kết thúc gián đoạn.
2. **Ổn định Redis:** xác nhận primary/cluster healthy, replication và endpoint đã ổn định.
3. **Xác nhận cấu hình:** kiểm tra keyspace notifications, ACL Pub/Sub, TLS và credential.
4. **Khôi phục subscription:** kiểm tra listener container reconnect hoặc khởi động lại thành phần listener theo cơ chế được hỗ trợ.
5. **Kiểm tra event mới:** tạo một session thử nghiệm, xóa hoặc cho hết hạn trong môi trường kiểm thử và xác nhận listener nhận đúng event.
6. **Đối soát phần bị bỏ lỡ:** chạy reconciliation job để dọn hoặc cập nhật dữ liệu phụ trợ theo trạng thái session thực tế.
7. **Đánh giá dữ liệu session:** xác nhận các session còn hợp lệ vẫn được đọc và những session bị mất/hết hạn không còn được chấp nhận.
8. **Ghi nhận nguyên nhân:** lưu thời gian gián đoạn, số event dự kiến bị bỏ lỡ, kết quả đối soát và biện pháp ngăn tái diễn.

Không xóa toàn bộ session chỉ vì listener bị lỗi. Việc đó có thể đăng xuất hàng loạt người dùng mà không giải quyết được nguyên nhân subscription. Chỉ thu hồi phiên theo chính sách bảo mật hoặc khi có bằng chứng dữ liệu session đã bị xâm phạm.

## 11. Kiểm thử listener disconnect và Redis failover

Nên kiểm thử trong môi trường staging hoặc môi trường tích hợp có Redis tương đương production. Các kịch bản hữu ích:

| Kịch bản | Cách tạo tình huống | Kết quả cần xác nhận |
| --- | --- | --- |
| Listener mất kết nối | Tạm dừng container hoặc chặn kết nối subscription | Container thử reconnect; event trong thời gian mất kết nối không được giả định sẽ replay |
| Session hết hạn khi listener dừng | Tạo session TTL ngắn rồi ngắt listener | Session không còn hợp lệ sau TTL; tác vụ phụ trợ được reconciliation xử lý |
| Redis restart | Restart Redis trong môi trường thử nghiệm | Client kết nối lại, repository hoạt động và listener subscribe lại |
| Sentinel failover | Chuyển primary có kiểm soát | Connection factory nhận primary mới và listener hoạt động lại |
| Cluster topology change | Chuyển slot hoặc thay node theo quy trình thử nghiệm | Subscription trên các node cần thiết được phục hồi |
| ACL thay đổi | Thu hồi quyền Pub/Sub rồi cấp lại | Lỗi được quan sát, cảnh báo và listener phục hồi sau khi quyền hợp lệ |
| Event trùng | Gọi lại handler với cùng dữ liệu | Tác vụ phụ trợ không bị thực hiện hai lần |
| Listener chậm | Giả lập callback xử lý lâu | Có metric backlog/lỗi; Redis notification thread không bị nghẽn kéo dài |

Với mỗi bài test, ghi lại cả trạng thái session trong repository lẫn trạng thái tác vụ phụ trợ. Chỉ kiểm tra log listener là chưa đủ: một event không được log có thể do notification mất, listener chưa subscribe hoặc handler lỗi sau khi nhận.

## 12. Giám sát và cảnh báo

Theo dõi các tín hiệu sau:

- Trạng thái kết nối Redis của ứng dụng và listener container.
- Số lần reconnect, thời gian từ lúc mất kết nối đến khi subscribe lại.
- Lỗi authentication, ACL, TLS và lỗi subscribe.
- Số event nhận được theo loại, số handler lỗi và thời gian xử lý.
- Độ trễ xử lý event expiration; Redis có thể phát thông báo trễ so với TTL.
- Số lượng bản ghi phụ trợ quá hạn được reconciliation tìm thấy và dọn.
- Số request không tìm thấy session trong repository.
- Số phiên và chỉ mục trước/sau failover nếu có cơ chế đo phù hợp.

Đặt cảnh báo khi listener không hoạt động quá ngưỡng, reconnect lặp liên tục, reconciliation backlog tăng hoặc tỷ lệ request mất session bất thường. Không ghi session ID hay cookie vào log để hỗ trợ điều tra; dùng request ID và mã tương quan không nhạy cảm.

## 13. Nguyên tắc phục hồi

- Coi Redis keyspace notification là tín hiệu Pub/Sub có thể mất, không phải event log bền vững.
- Phân biệt session TTL trong repository với các tác vụ phụ trợ do event kích hoạt.
- Dùng listener container và connection factory có hỗ trợ reconnect/topology của Redis đang triển khai.
- Sau reconnect hoặc failover, xác nhận subscription thực sự hoạt động bằng kiểm thử event mới.
- Đối soát phần việc có thể bị bỏ lỡ bằng repository hoặc chỉ mục nghiệp vụ được hỗ trợ.
- Thiết kế listener và reconciliation idempotent, có retry và giám sát.
- Không xóa hàng loạt session chỉ vì listener mất kết nối.
- Với giao dịch cần bảo đảm xử lý, dùng hàng đợi bền vững hoặc outbox thay vì dựa duy nhất vào Pub/Sub.

Khi listener mất kết nối hoặc Redis đổi node, Spring Session có thể tiếp tục dựa vào TTL và repository để xác định session còn hợp lệ hay không, nhưng event phát trong khoảng gián đoạn có thể không được nhận lại. Phục hồi đầy đủ cần khôi phục subscription trên topology mới, kiểm tra khả năng nhận event mới và đối soát dữ liệu phụ trợ theo trạng thái session thực tế. Cách thiết kế này giúp các instance Spring xử lý ổn định ngay cả khi Redis hoặc đường truyền gặp gián đoạn.
