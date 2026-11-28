# Keyspace notifications và cấu hình quyền trên Redis được quản lý

Spring Session có thể lưu phiên trong Redis và duy trì các chỉ mục để tìm phiên theo thuộc tính, chẳng hạn principal name. Với repository Redis có chỉ mục, Redis keyspace notifications giúp Spring Session nhận biết các khóa phiên đã hết hạn hoặc bị xóa để cập nhật dữ liệu phụ trợ và phát sự kiện vòng đời phiên. Khi Redis được cung cấp dưới dạng dịch vụ được quản lý, ứng dụng thường không có quyền thay đổi mọi tham số máy chủ hoặc chạy lệnh quản trị `CONFIG`. Vì vậy, cần phối hợp cấu hình ở phía nhà cung cấp Redis với `ConfigureRedisAction` và quyền ACL dành cho tài khoản ứng dụng.

Phần này tập trung vào hai việc riêng biệt: bật thông báo sự kiện Redis mà Spring Session cần, và cấp đúng quyền để ứng dụng đọc/ghi dữ liệu phiên cũng như đăng ký nhận thông báo. TTL của khóa phiên vẫn do Redis thực thi; keyspace notifications là cơ chế thông báo cho các thành phần đang lắng nghe, không phải cơ chế quyết định phiên có còn hợp lệ hay không.

## 1. Keyspace notifications là gì?

Redis có thể phát thông báo Pub/Sub khi một số sự kiện xảy ra với khóa, ví dụ khóa hết hạn, bị xóa hoặc được thay đổi. Cơ chế này được gọi là *keyspace notifications*. Một subscriber đăng ký kênh phù hợp sẽ nhận được thông báo khi Redis phát sự kiện.

Redis cung cấp hai kiểu tên kênh:

- **Keyspace channel** bắt đầu bằng `__keyspace@<db>__:` và phần sau là tên khóa; payload là loại sự kiện.
- **Keyevent channel** bắt đầu bằng `__keyevent@<db>__:` và phần sau là loại sự kiện; payload là tên khóa.

Ví dụ, khi khóa `spring:session:sessions:abc` hết hạn trong database 0, một keyevent notification có thể được phát trên kênh `__keyevent@0__:expired` với payload là tên khóa. Spring Session Redis đăng ký lắng nghe những thông báo cần thiết để biết khóa phiên đã hết hạn và xử lý dữ liệu liên quan.

Keyspace notifications được điều khiển bởi tham số `notify-keyspace-events`. Giá trị tham số là tập các cờ chỉ định loại kênh và loại sự kiện được phát. Nếu tham số rỗng, Redis không phát keyspace notification.

## 2. Vì sao Spring Session Redis cần thông báo hết hạn?

Redis lưu dữ liệu phiên cùng thời hạn hết hạn. Khi TTL kết thúc, Redis có thể loại bỏ khóa. Tuy nhiên, việc khóa bị xóa khỏi Redis và việc ứng dụng nhận được một sự kiện vòng đời là hai việc khác nhau.

Với repository có chỉ mục như `RedisIndexedSessionRepository`, một phiên có thể liên quan đến nhiều cấu trúc dữ liệu: hash chứa thuộc tính phiên, khóa phục vụ expiration và các chỉ mục để tìm phiên theo principal. Khi phiên hết hạn, Spring Session cần có cơ hội xử lý dữ liệu phụ trợ và thông báo cho ứng dụng.

Keyspace notification hỗ trợ Spring Session:

- Nhận biết khóa hết hạn để xử lý các cấu trúc phụ trợ và chỉ mục liên quan.
- Phát `SessionExpiredEvent` khi repository nhận biết phiên hết hạn theo cơ chế của nó.
- Phát hiện một số thay đổi khóa được cấu hình lắng nghe, ví dụ sự kiện xóa, để hỗ trợ vòng đời phiên.
- Giúp listener của ứng dụng cập nhật số liệu hoặc thực hiện công việc phụ trợ gắn với vòng đời phiên.

Điều này đặc biệt hữu ích khi nhiều instance ứng dụng cùng dùng Redis. Một instance tạo phiên nhưng một instance khác có thể nhận thông báo khi khóa hết hạn; các instance không cần dựa vào bộ nhớ cục bộ để biết trạng thái phiên.

**TTL và notification không đồng nghĩa.** Redis vẫn quản lý TTL của khóa ngay cả khi notification bị tắt. Khi notification không được phát hoặc subscriber không nhận được sự kiện, dữ liệu phiên hết hạn vẫn không nên được chấp nhận như một phiên hợp lệ. Tuy nhiên, việc dọn dẹp chỉ mục phụ trợ hoặc phát sự kiện ứng dụng có thể không diễn ra đúng như mong đợi.

## 3. Các cờ `notify-keyspace-events` cần hiểu

Giá trị thường được Spring Session Redis yêu cầu trong cấu hình tiêu chuẩn là:

```text
notify-keyspace-events Egx
```

Các ký tự có ý nghĩa như sau:

| Cờ | Ý nghĩa |
|---|---|
| `E` | Phát thông báo theo dạng keyevent, trên kênh `__keyevent@<db>__:<event>` |
| `g` | Nhóm sự kiện generic, ví dụ `DEL`, `EXPIRE` và một số thao tác khóa chung |
| `x` | Sự kiện khóa hết hạn (`expired`) |
| `K` | Phát theo dạng keyspace, trên kênh `__keyspace@<db>__:<key>` |
| `$`, `l`, `s`, `h`, `z` | Nhóm sự kiện tương ứng với thao tác trên string, list, set, hash và sorted set |
| `e` | Sự kiện khóa bị eviction do chính sách giới hạn bộ nhớ; khác với hết hạn TTL |
| `A` | Bí danh cho phần lớn nhóm sự kiện thông dụng, không bao gồm mọi loại sự kiện quản trị |

`Egx` bật keyevent notifications cho nhóm generic và expired. Đây là cấu hình thường được tài liệu Spring Session Redis hướng dẫn. Không cần bật toàn bộ `A` chỉ để nhận sự kiện hết hạn nếu ứng dụng không có nhu cầu khác. Bật quá nhiều loại notification có thể tạo thêm tải và lưu lượng Pub/Sub.

Redis phân biệt sự kiện `expired` với `evicted`:

- `expired` xảy ra khi khóa hết hạn theo TTL.
- `evicted` xảy ra khi Redis loại khóa để tuân thủ chính sách `maxmemory`.

Thời điểm notification được phát không nhất thiết trùng chính xác thời điểm TTL về 0. Redis phát sự kiện khi quá trình hết hạn thực sự loại bỏ khóa; cơ chế hết hạn có thể kiểm tra khóa theo chu kỳ hoặc khi khóa được truy cập.

Một session bị evict trước TTL có thể biến mất sớm và làm người dùng bị đăng xuất. Đó là vấn đề dung lượng/chính sách eviction, không phải một timeout đăng nhập có chủ đích. Nếu cần giám sát eviction, có thể cân nhắc bật thêm cờ `e` theo chính sách vận hành và kiểm tra tác động với nhà cung cấp.

## 4. Cấu hình Redis tự quản lý

Với Redis do đội vận hành quản lý trực tiếp, tham số có thể được cấu hình trong file cấu hình Redis:

```text
notify-keyspace-events Egx
```

Hoặc thay đổi lúc chạy bằng lệnh quản trị:

```text
CONFIG SET notify-keyspace-events Egx
```

Lệnh `CONFIG SET` cần quyền quản trị phù hợp và thay đổi có thể không tồn tại sau khi Redis khởi động lại nếu chưa cập nhật file cấu hình hoặc cấu hình triển khai. Khi áp dụng, cần xem giá trị hiện tại trước để không vô tình xóa những cờ notification mà ứng dụng khác đang cần. Giá trị tham số là một tập cờ; cập nhật mới có thể thay thế tập hiện tại.

Trong môi trường production, thay đổi cấu hình nên được quản lý qua quy trình cấu hình hạ tầng, kiểm thử trên môi trường staging và ghi nhận rõ các ứng dụng đang phụ thuộc vào notification.

## 5. Khi Redis được quản lý và lệnh CONFIG bị hạn chế

Các dịch vụ Redis được quản lý thường giới hạn một số lệnh quản trị. Nhà cung cấp có thể chặn `CONFIG GET` hoặc `CONFIG SET`, dù ứng dụng vẫn được phép đọc và ghi dữ liệu. Đây là chính sách phổ biến vì nhà cung cấp chịu trách nhiệm quản lý tham số máy chủ, khả năng sẵn sàng và nâng cấp.

Nếu Spring Session cố tự cấu hình keyspace notifications khi khởi động, lệnh quản trị có thể bị từ chối. Khi đó ứng dụng có thể ghi log lỗi hoặc không khởi tạo được thành phần cấu hình tùy phiên bản và cách cấu hình. Không nên cấp quyền quản trị Redis rộng chỉ để ứng dụng có thể tự đổi tham số máy chủ.

Thay vào đó, cấu hình tham số notification ở lớp quản lý của nhà cung cấp:

1. Xác định tham số hoặc parameter group mà dịch vụ Redis hỗ trợ.
2. Đặt `notify-keyspace-events` theo yêu cầu của Spring Session, thường là `Egx`, đồng thời giữ lại các cờ khác nếu hệ thống đang cần.
3. Áp dụng thay đổi theo quy trình của nhà cung cấp. Một số dịch vụ áp dụng ngay; dịch vụ khác yêu cầu thay parameter group, khởi động lại hoặc failover.
4. Xác minh giá trị hiệu lực bằng giao diện quản trị, API nhà cung cấp hoặc `CONFIG GET` nếu tài khoản được phép.
5. Kiểm tra subscriber của ứng dụng nhận được sự kiện hết hạn trong môi trường thử nghiệm.

Không phải mọi dịch vụ tương thích Redis đều hỗ trợ đầy đủ keyspace notifications hoặc cho phép tùy chỉnh tham số này. Cần kiểm tra tài liệu của đúng dịch vụ, phiên bản engine và chế độ triển khai (standalone, replication hay cluster). Nếu nhà cung cấp không hỗ trợ notification cần thiết, phải đánh giá giới hạn của repository/index và chọn phương án lưu trữ hoặc cơ chế dọn dẹp được hỗ trợ.

## 6. Dùng ConfigureRedisAction.NO_OP

Spring Session có `ConfigureRedisAction` để quyết định cách cấu hình Redis. Cấu hình mặc định có thể thực hiện thao tác thiết lập keyspace notifications. Với Redis được quản lý mà ứng dụng không có quyền `CONFIG`, có thể cung cấp `ConfigureRedisAction.NO_OP` để Spring Session không cố thay đổi tham số máy chủ.

Ví dụ cấu hình Servlet dùng repository Redis có chỉ mục:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.ConfigureRedisAction;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisIndexedHttpSession;

@Configuration
@EnableRedisIndexedHttpSession
public class RedisSessionConfiguration {

    @Bean
    public static ConfigureRedisAction configureRedisAction() {
        return ConfigureRedisAction.NO_OP;
    }
}
```

`NO_OP` chỉ tắt hành động tự cấu hình Redis của Spring Session. Nó **không** bật keyspace notifications và không thay đổi ACL. Đội vận hành phải cấu hình `notify-keyspace-events` ở phía nhà cung cấp trước hoặc cùng thời điểm triển khai ứng dụng.

Nếu tham số notification vẫn rỗng, ứng dụng có thể khởi động và thực hiện một số thao tác đọc/ghi session bình thường nhưng không nhận đủ sự kiện hết hạn để duy trì các hành vi phụ thuộc notification. Vì vậy, không coi việc context khởi động thành công sau khi đặt `NO_OP` là bằng chứng cấu hình Redis đã hoàn chỉnh.

Tên annotation và API cấu hình cần khớp phiên bản Spring Session của dự án. Nếu phiên bản đang dùng dùng annotation Redis HTTP khác để tạo repository có chỉ mục, hãy dùng annotation được phiên bản đó hỗ trợ; điểm quan trọng là repository thực tế phải là implementation có chỉ mục và `ConfigureRedisAction.NO_OP` phải được Spring nhận diện.

## 7. Phân biệt quyền CONFIG với quyền Pub/Sub

Hai nhóm quyền này phục vụ hai mục đích khác nhau:

| Quyền | Mục đích | Khi bị thiếu |
|---|---|---|
| `CONFIG GET` / `CONFIG SET` | Đọc hoặc thay đổi tham số server, bao gồm `notify-keyspace-events` | Spring Session không thể tự cấu hình tham số |
| `PSUBSCRIBE` hoặc lệnh subscribe phù hợp | Đăng ký nhận thông báo qua kênh Pub/Sub | Ứng dụng không nhận được keyspace events |
| Quyền đọc/ghi khóa | Tạo, đọc, cập nhật, đặt TTL và xóa dữ liệu phiên | Các thao tác session thông thường thất bại |
| Quyền truy cập key pattern | Giới hạn những khóa mà user ACL được phép thao tác | Lệnh trên khóa ngoài phạm vi bị từ chối |
| Quyền truy cập channel pattern | Giới hạn kênh Pub/Sub mà user được subscribe/publish | Subscriber không được phép nghe kênh expiration |

Đặt `ConfigureRedisAction.NO_OP` xử lý trường hợp thiếu quyền `CONFIG`; nó không cấp quyền subscribe và không bỏ qua kiểm tra ACL của channel. Tài khoản ứng dụng vẫn cần quyền đọc/ghi các khóa session và đăng ký kênh notification mà repository sử dụng.

## 8. Cấp quyền ACL theo nguyên tắc tối thiểu

Redis ACL có thể giới hạn:

- Lệnh được phép chạy.
- Mẫu tên khóa mà user được truy cập.
- Mẫu kênh Pub/Sub mà user được subscribe hoặc publish.

Với Spring Session, nên tạo một tài khoản riêng cho ứng dụng thay vì dùng tài khoản quản trị. Giới hạn key pattern theo namespace mà ứng dụng dùng, ví dụ `spring:session:*` nếu đó là namespace thực tế. Giới hạn channel pattern theo database và sự kiện cần nhận, ví dụ kênh keyevent expired của database tương ứng.

Ví dụ dưới đây minh họa phạm vi khóa và channel trong cú pháp ACL; đây **không phải** bộ quyền lệnh hoàn chỉnh cho mọi phiên bản Spring Session:

```text
ACL SETUSER spring-session on >REPLACE_WITH_SECRET ~spring:session:* &__keyevent@*__:expired
```

Lệnh này minh họa tên user, key pattern và channel pattern. User mới chưa được cấp các lệnh cần thiết chỉ bởi dòng trên. Quản trị viên phải bổ sung các lệnh đọc/ghi, TTL, thao tác cấu trúc dữ liệu và Pub/Sub đúng theo phiên bản Redis, Spring Data Redis và Spring Session đang chạy. Không sao chép một danh sách lệnh chung mà chưa kiểm tra các thao tác thực tế.

Các điểm cần lưu ý khi cấp ACL:

- Không cấp `+@all`, `~*` hoặc `&*` cho tài khoản ứng dụng nếu không có lý do đặc biệt.
- Không cấp `+@admin` hoặc quyền `CONFIG` chỉ để giải quyết keyspace notifications khi có thể dùng `NO_OP` và cấu hình ở lớp quản trị.
- Cấp quyền subscribe cần thiết, thường bao gồm `PSUBSCRIBE` nếu listener dùng pattern subscription; xác minh bằng cách chạy ứng dụng và quan sát lỗi ACL.
- Channel pattern phải cho phép pattern mà listener thực sự subscribe. Spring Data Redis thường dùng pattern `__keyevent@*__:expired`; ACL cần cho phép pattern subscription đó. Nếu ứng dụng được cấu hình subscribe một channel cụ thể, có thể thu hẹp ACL theo database tương ứng, ví dụ `__keyevent@0__:expired` cho database 0.
- Với Redis Cluster hoặc dịch vụ cluster-managed, xác minh cách nhà cung cấp phân phối Pub/Sub và keyspace notifications giữa các node/shard. Không giả định cấu hình một node đã bao phủ mọi node.
- Dùng secret riêng, xoay vòng mật khẩu và không đặt mật khẩu ACL trong mã nguồn hoặc log.

## 9. Xác định key và channel thực tế

Spring Session thường đặt namespace cho các khóa Redis. Namespace mặc định và cách đặt tên chi tiết có thể thay đổi theo cấu hình hoặc phiên bản. Trước khi giới hạn ACL, hãy xác định namespace ứng dụng đang sử dụng và các cấu trúc khóa mà repository tạo ra.

Ví dụ, nếu namespace là `orders:session`, key pattern cần giới hạn có thể bắt đầu bằng `orders:session:*`, thay vì `spring:session:*`. Cấu hình ACL sai pattern khiến một số lệnh tạo session thành công nhưng lệnh ghi index hoặc xóa khóa bị `NOPERM`.

Với channel notifications, Spring Session Redis có thể đăng ký pattern cho sự kiện hết hạn trên một hoặc nhiều database. Hãy xác minh pattern mà phiên bản thư viện thực sự subscribe. ACL channel pattern quá hẹp có thể làm subscriber bị từ chối; quá rộng lại cho phép user nghe các kênh không cần thiết.

Không bật `MONITOR` trên production chỉ để tìm lệnh ứng dụng: lệnh này có thể tạo lượng dữ liệu lớn, ảnh hưởng hiệu năng và phơi bày thông tin nhạy cảm trong tham số. Ưu tiên log ứng dụng, `ACL LOG`, metric của nhà cung cấp và kiểm thử trong môi trường staging.

## 10. Tác động khi notification không hoạt động

Nếu keyspace notifications bị tắt, bị ACL chặn hoặc subscriber mất kết nối, các hành vi phụ thuộc sự kiện có thể bị ảnh hưởng:

- `SessionExpiredEvent` có thể không được phát đúng như kỳ vọng.
- Chỉ mục principal hoặc dữ liệu phụ trợ liên quan đến phiên hết hạn có thể còn tham chiếu cũ lâu hơn dự kiến, tùy repository và cơ chế cleanup của phiên bản.
- Listener của ứng dụng không nhận được thông báo hết hạn để cập nhật số liệu hoặc dọn dữ liệu phụ trợ.
- Các thao tác tra cứu theo chỉ mục có thể phải xử lý những tham chiếu không còn trỏ đến session hợp lệ.

Tuy vậy, notification bị thiếu không làm cho TTL Redis biến mất. Khóa hết hạn vẫn có thể được Redis loại bỏ theo TTL và repository phải tiếp tục kiểm tra session có tồn tại/hợp lệ khi xử lý request. Không được dùng sự kiện hết hạn làm cơ chế duy nhất để từ chối request; quyết định xác thực phải dựa trên session hợp lệ trong repository.

Redis Pub/Sub là cơ chế thông báo không lưu trữ bền vững. Nếu subscriber ngắt kết nối trong lúc sự kiện được phát, subscriber không có hàng đợi lịch sử để đọc lại sự kiện đã bỏ lỡ. Do đó, không dùng `SessionExpiredEvent` làm nguồn duy nhất cho kiểm toán bắt buộc hoặc nghiệp vụ không được phép mất. Với những nghiệp vụ đó, hãy ghi nhận vào kho dữ liệu bền vững hoặc dùng cơ chế event/outbox riêng.

## 11. Kiểm tra cấu hình và quyền trong môi trường được quản lý

Thực hiện kiểm tra theo từng lớp để khoanh vùng lỗi:

### 11.1. Xác minh tham số notification

- Kiểm tra `notify-keyspace-events` trong console hoặc parameter group của nhà cung cấp.
- Xác nhận các cờ cần thiết, thường là `Egx`, đang có hiệu lực trên đúng cluster/node.
- Nếu có quyền, đọc bằng `CONFIG GET notify-keyspace-events`; nếu lệnh bị chặn, dùng giao diện quản trị hoặc API nhà cung cấp.
- Không chỉ kiểm tra cấu hình mong muốn; phải xác minh cấu hình đã được áp dụng sau restart/failover nếu nhà cung cấp yêu cầu.

### 11.2. Xác minh subscriber

- Khởi động ứng dụng với `ConfigureRedisAction.NO_OP` nếu không có quyền `CONFIG`.
- Kiểm tra log để xác nhận Redis message listener container đã kết nối và subscribe.
- Tạo một phiên thử nghiệm với TTL ngắn trong môi trường test.
- Chờ khóa hết hạn và xác nhận listener nhận được notification hoặc ứng dụng phát sự kiện tương ứng.
- Lặp lại sau khi reconnect/failover để kiểm tra listener tự kết nối lại và tiếp tục nhận sự kiện.

### 11.3. Xác minh ACL

- Dùng user ứng dụng để thực hiện tạo, đọc, cập nhật, đặt timeout và xóa session.
- Xác nhận user có thể subscribe đúng channel expiration.
- Kiểm tra log `NOPERM` và `ACL LOG` nếu có quyền.
- Thử một key ngoài namespace để xác nhận ACL thực sự giới hạn phạm vi.
- Kiểm tra các thao tác index theo principal, không chỉ thao tác đọc/ghi session cơ bản.

## 12. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ứng dụng báo lỗi `CONFIG` khi khởi động | Spring Session cố tự cấu hình tham số nhưng managed Redis chặn lệnh | Cấu hình notification qua nhà cung cấp và khai báo `ConfigureRedisAction.NO_OP` |
| Session đọc/ghi được nhưng không có sự kiện hết hạn | Notification chưa bật hoặc subscriber không có quyền channel | Kiểm tra `notify-keyspace-events`, `PSUBSCRIBE` và ACL channel |
| `NOPERM` trên khóa session | Key pattern ACL không khớp namespace hoặc thiếu lệnh | Xác minh namespace và bổ sung quyền tối thiểu theo lệnh thực tế |
| Listener kết nối nhưng không nhận expired event | Cờ `E`/`x` thiếu, sai database hoặc node/shard chưa được cấu hình | Kiểm tra cờ và phạm vi triển khai của nhà cung cấp |
| Chỉ mục còn tham chiếu session cũ | Sự kiện hết hạn bị bỏ lỡ hoặc cleanup chưa chạy | Kiểm tra notification, phiên bản repository và cơ chế dọn dẹp |
| Một số instance nhận event, instance khác không nhận | Subscriber connection hoặc cấu hình node/cluster không đồng nhất | Kiểm tra từng instance và Pub/Sub topology |
| Session hết hạn sớm bất thường | Redis eviction do áp lực bộ nhớ thay vì TTL mong muốn | Kiểm tra `maxmemory`, eviction policy và sự kiện evicted |
| Sau failover không nhận event | Subscriber chưa reconnect hoặc dịch vụ đổi endpoint/node | Kiểm tra listener container, DNS/endpoints và hành vi failover |

## 13. Checklist triển khai

- Xác định repository thực tế là Redis indexed và namespace khóa đang sử dụng.
- Bật `notify-keyspace-events` theo yêu cầu, thường là `Egx`, tại lớp cấu hình Redis được quản lý.
- Nếu ứng dụng không có quyền `CONFIG`, khai báo `ConfigureRedisAction.NO_OP` để bỏ qua thao tác tự cấu hình.
- Bảo đảm `NO_OP` không bị hiểu nhầm là đã bật notification; xác minh tham số ở Redis/provider.
- Cấp ACL riêng cho ứng dụng: key pattern đúng namespace, channel pattern đúng expiration channel và lệnh cần thiết cho repository.
- Tránh cấp quyền quản trị rộng, `+@all`, `~*` hoặc `&*` khi không cần.
- Kiểm thử tạo, đọc, cập nhật, index theo principal, hết hạn và xóa session bằng chính user ACL production-like.
- Kiểm thử reconnect/failover và nhận sự kiện trên topology thực tế.
- Theo dõi `NOPERM`, lỗi Pub/Sub, độ trễ Redis, memory pressure và eviction.
- Không dùng Pub/Sub expiration event làm nguồn duy nhất cho nghiệp vụ hoặc kiểm toán cần bảo đảm bền vững.

Với Redis được quản lý, Spring Session cần được cấu hình theo ranh giới quyền của nhà cung cấp: nhà vận hành bật keyspace notifications, ứng dụng bỏ qua lệnh `CONFIG` bằng `ConfigureRedisAction.NO_OP` khi cần, và ACL chỉ cấp quyền trên các khóa cùng kênh mà repository sử dụng. Khi kiểm tra riêng TTL, notification, subscriber và ACL, hệ thống có thể duy trì chỉ mục phiên và sự kiện hết hạn mà không phải cấp quyền quản trị Redis cho tiến trình ứng dụng.
