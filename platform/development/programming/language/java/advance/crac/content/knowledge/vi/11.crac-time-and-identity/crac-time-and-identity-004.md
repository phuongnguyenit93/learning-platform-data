# Thời hạn yêu cầu, phiên đăng nhập và token hết hạn

Một ứng dụng Java có thể được checkpoint sau khi khởi động và warm-up, rồi được restore nhiều giây, nhiều phút hoặc lâu hơn. Trong thời gian tiến trình không chạy, thế giới bên ngoài vẫn tiếp tục thay đổi: request hết deadline, session bị thu hồi, access token hết hạn, refresh token bị rotate, lease phân tán hết TTL và certificate có thể tới thời điểm hết hiệu lực.

Vì vậy, trạng thái thời gian được lưu trong heap không thể luôn được xem là còn hợp lệ sau restore. Một object vẫn tồn tại không có nghĩa thời hạn của nó được kéo dài theo thời gian tiến trình ngừng chạy.

Khi tích hợp CRaC (Coordinated Restore at Checkpoint), ứng dụng cần xác định rõ semantics của từng loại thời hạn:

- Thời gian tuyệt đối tiếp tục trôi qua trong lúc checkpoint.
- Khoảng thời gian được đo trong một lần thực thi của tiến trình.
- Thời hạn do hệ thống bên ngoài quản lý.
- Thời hạn có chủ ý tạm dừng trong thời gian ứng dụng không hoạt động.

Bài này trình bày cách quản lý deadline, session và token để ứng dụng không tiếp tục sử dụng trạng thái đã hết hạn sau checkpoint/restore.

## 1. Thời gian vẫn trôi qua khi ứng dụng được checkpoint

Checkpoint lưu trạng thái của tiến trình tại một thời điểm. Nó không đóng băng đồng hồ của hệ điều hành, máy chủ database, máy chủ xác thực hoặc dịch vụ từ xa.

Ví dụ:

1. Ứng dụng nhận access token có thời hạn đến 10:30.
2. Ứng dụng tạo checkpoint lúc 10:20.
3. Image được giữ trong kho 25 phút.
4. Instance được restore lúc 10:45.
5. Object token trong heap vẫn tồn tại, nhưng token đã hết hạn.

Nếu ứng dụng chỉ kiểm tra biến boolean như tokenLoaded hoặc authenticated, nó có thể tiếp tục gọi API bằng token cũ. Dịch vụ từ xa sẽ từ chối request hoặc yêu cầu xác thực lại.

Tương tự, một request có deadline 10:25 không nên tiếp tục chạy sau khi restore lúc 10:45. Một session có idle timeout 30 phút có thể đã bị hệ thống xác thực hoặc session store thu hồi. Một lease có TTL 60 giây có thể đã được cấp cho tiến trình khác.

CRaC không tự gia hạn các thời hạn đó. Ứng dụng cần đánh giá lại chúng bằng thời gian hiện tại và trạng thái có thẩm quyền từ hệ thống liên quan.

## 2. Phân biệt thời gian tuyệt đối và thời gian đơn điệu

Java có hai khái niệm thời gian thường được dùng cho hai mục đích khác nhau.

### 2.1 Wall-clock time: thời điểm theo lịch

Các API như Instant.now() hoặc Clock.systemUTC() cung cấp thời điểm theo đồng hồ hệ thống, thường biểu diễn theo UTC.

Ví dụ:

~~~java
Instant expiresAt = Instant.parse("2026-11-13T10:30:00Z");

if (!Instant.now().isBefore(expiresAt)) {
    // Deadline đã tới hoặc đã qua.
}
~~~

Thời điểm tuyệt đối phù hợp với:

- Token có trường exp.
- Session expiration do server quy định.
- Deadline request được truyền giữa các service.
- Thời hạn hợp đồng, lease hoặc reservation có mốc kết thúc tuyệt đối.
- Timestamp được lưu trong database hoặc message.

Instant có thể được lưu trong checkpoint image vì nó là một giá trị thời điểm theo epoch. Sau restore, so sánh Instant với thời gian hiện tại sẽ cho biết thời hạn đã qua hay chưa, với điều kiện đồng hồ hệ thống được đồng bộ và semantics của deadline được xác định đúng.

### 2.2 Monotonic time: đo khoảng thời gian

System.nanoTime() được thiết kế để đo elapsed time trong JVM. Giá trị trả về không phải timestamp theo lịch và không có mốc epoch có ý nghĩa.

~~~java
long started = System.nanoTime();

// Thực hiện một thao tác.

long elapsedNanos = System.nanoTime() - started;
~~~

Nên dùng nanoTime() cho:

- Đo latency.
- Timeout nội bộ trong một lần thực thi.
- Tính khoảng thời gian giữa hai sự kiện.
- Tránh ảnh hưởng của việc wall clock bị điều chỉnh trong lúc đo.

Không nên lưu một giá trị nanoTime rồi xem nó như timestamp có thể so sánh với đồng hồ của một máy khác hoặc một môi trường thực thi khác. Origin của nanoTime là tùy ý; chỉ hiệu số giữa các lần đọc trong cùng ngữ cảnh thực thi mới có ý nghĩa theo hợp đồng API.

Khi ứng dụng restore trên host khác, không được giả định origin monotonic clock của host đích giống host nguồn. Ngay cả khi restore trên cùng host, cần kiểm tra semantics của runtime và không dùng một giá trị nanoTime đã lưu như thời hạn tuyệt đối.

### 2.3 Chuyển deadline thành dữ liệu có thể lưu

Một cách an toàn là lưu thời điểm hết hạn tuyệt đối, sau đó tính lại thời gian còn lại sau restore:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class Deadline {

    private final Instant expiresAt;

    public Deadline(Instant expiresAt) {
        this.expiresAt = expiresAt;
    }

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }

    public Duration remaining(Clock clock) {
        Duration duration =
                Duration.between(clock.instant(), expiresAt);

        return duration.isNegative()
                ? Duration.ZERO
                : duration;
    }
}
~~~

Nếu deadline đã qua trong lúc checkpoint, remaining() trả về Duration.ZERO. Ứng dụng có thể từ chối công việc hoặc đánh dấu nó hết hạn thay vì tiếp tục xử lý.

Đối với timeout cần đo chính xác trong một lần chạy, có thể chuyển thời gian còn lại thành nanoTime deadline sau khi restore:

~~~java
Duration remaining = deadline.remaining(clock);

if (remaining.isZero()) {
    throw new TimeoutException("Request deadline expired");
}

long localDeadline =
        System.nanoTime() + remaining.toNanos();
~~~

Giá trị localDeadline chỉ dùng trong lần thực thi hiện tại. Không lưu nó để dùng qua checkpoint tiếp theo.

### 2.4 Không dùng Duration một mình làm thời hạn lâu dài

Duration chỉ biểu diễn độ dài một khoảng thời gian. Ví dụ, Duration.ofMinutes(15) không cho biết 15 phút bắt đầu từ khi nào.

Nếu chỉ lưu Duration vào heap rồi restore sau 40 phút, ứng dụng không thể biết thời gian checkpoint có cần được tính vào 15 phút đó hay không.

Hãy lưu một trong hai dạng tùy semantics:

- Thời điểm tuyệt đối expiresAt nếu thời gian tiếp tục trôi qua trong lúc checkpoint.
- Thời gian còn lại remaining nếu nghiệp vụ chủ ý tạm dừng đồng hồ trong lúc checkpoint.

Đừng dùng một dạng cho cả hai chính sách.

## 3. Quyết định semantics của deadline

Trước khi viết code, hãy xác định thời gian checkpoint có được tính vào thời hạn hay không.

| Loại thời hạn | Thường có tính thời gian checkpoint? | Cách lưu phù hợp |
|---|---|---|
| Deadline của HTTP request | Có | Instant deadline được truyền xuyên service |
| Access token exp | Có | Thời điểm hết hạn tuyệt đối từ token hoặc token response |
| Refresh token expiration | Có | Thời hạn do authorization server quản lý |
| Session idle timeout | Có, theo hoạt động được server ghi nhận | Session store/server là nguồn có thẩm quyền |
| Distributed lease TTL | Có | Hạn lease và fencing token từ hệ thống cấp lease |
| Reservation hoặc payment authorization | Có | Thời hạn tuyệt đối từ dịch vụ nghiệp vụ |
| Tạm dừng một tác vụ nội bộ khi bảo trì | Có thể không | Lưu remaining duration và khởi động lại có chủ ý |
| Thời gian đo latency | Không áp dụng như deadline | nanoTime trong một lần đo |

Ví dụ, deadline thanh toán thường không được kéo dài chỉ vì một instance được checkpoint. Nếu một giao dịch phải hoàn tất trước một thời điểm, thời điểm đó vẫn giữ nguyên.

Ngược lại, một tác vụ batch nội bộ có thể được thiết kế để tạm dừng khi hệ thống ngừng chạy. Trong trường hợp đó, ứng dụng có thể lưu thời gian còn lại trước checkpoint rồi tạo lại timer sau restore. Đây là chính sách nghiệp vụ phải được lựa chọn rõ ràng.

## 4. Deadline của request và tác vụ đang chạy

Một request phân tán thường đi qua nhiều service. Nếu mỗi service tự tạo timeout mới, tổng thời gian xử lý có thể vượt quá deadline của client.

Ví dụ:

~~~text
Client deadline: 12:00:05
  -> API Gateway
  -> Order Service
  -> Payment Service
  -> Inventory Service
~~~

Mỗi service cần dùng deadline còn lại, không tự cấp một khoảng timeout đầy đủ mới.

### 4.1 Truyền absolute deadline

Có thể truyền deadline dưới dạng timestamp UTC trong header nội bộ, chẳng hạn một header do hệ thống định nghĩa:

~~~text
X-Request-Deadline: 2026-11-13T12:00:05Z
~~~

Tên header này chỉ là ví dụ; cần dùng một quy ước thống nhất trong hệ thống. Khi nhận request, service chuyển timestamp thành Instant và tính thời gian còn lại bằng Clock.

~~~java
Instant deadline = Instant.parse(deadlineHeader);
Duration remaining = Duration.between(clock.instant(), deadline);

if (remaining.isNegative() || remaining.isZero()) {
    throw new TimeoutException("Request deadline expired");
}
~~~

Nếu service được restore sau khi deadline đã qua, request phải bị từ chối hoặc kết thúc theo quy tắc của API. Không được tự đặt deadline mới từ thời điểm restore, vì điều đó kéo dài thời hạn mà client đã yêu cầu.

### 4.2 Lưu deadline cùng công việc

Nếu ứng dụng có queue nội bộ hoặc workflow đang chờ, hãy lưu deadline cùng metadata công việc:

~~~java
public record PendingWork(
        String workId,
        Instant deadline,
        String idempotencyKey) {
}
~~~

Sau restore, worker kiểm tra deadline trước khi lấy công việc:

~~~java
if (!clock.instant().isBefore(work.deadline())) {
    markExpired(work.workId());
    return;
}

process(work);
~~~

Việc kiểm tra phải diễn ra ngay trước side effect quan trọng. Một lần kiểm tra khi đưa công việc vào queue không đủ nếu công việc có thể nằm chờ lâu.

### 4.3 Hủy công việc đã hết hạn

Nếu request đã hết deadline, ứng dụng cần:

- Ngừng các bước chưa bắt đầu.
- Hủy downstream call nếu client hoặc thư viện hỗ trợ cancellation.
- Không gửi lại thao tác ghi đã hết hạn chỉ vì worker vừa resume.
- Giải phóng tài nguyên và cập nhật trạng thái workflow.
- Trả lỗi phù hợp nếu còn kênh phản hồi.

Không phải mọi thao tác đã gửi tới service bên ngoài đều có thể hủy. Nếu một payment request có thể đã được xử lý trước checkpoint, hãy truy vấn trạng thái hoặc dùng idempotency key trước khi thử lại. Timeout của client không chứng minh thao tác ở server đã thất bại.

### 4.4 Không tiếp tục request chỉ vì thread được restore

Thread có thể tiếp tục từ trạng thái đã checkpoint, nhưng deadline nghiệp vụ có thể đã hết. Trước khi thực hiện một bước I/O hoặc side effect sau restore, cần xác nhận request còn hợp lệ.

Với request dài, có thể chọn không checkpoint khi còn request đang chạy: chuyển readiness sang false, drain request, rồi mới tạo ảnh. Nếu ứng dụng cho phép lưu workflow đang dở, hãy lưu trạng thái bền vững và khôi phục workflow từ trạng thái đó theo deadline gốc.

## 5. Session đăng nhập và idle timeout

Session đăng nhập có thể được quản lý trong bộ nhớ ứng dụng, trong database, Redis, một identity provider hoặc một dịch vụ session riêng.

Checkpoint image chỉ lưu trạng thái tiến trình Java. Nó không đóng băng session store bên ngoài.

### 5.1 Session có thể hết hạn khi tiến trình ngừng chạy

Giả sử một session có idle timeout 30 phút. Ứng dụng checkpoint sau 5 phút không hoạt động và restore sau 40 phút.

Nếu session store bên ngoài vẫn chạy, session có thể đã hết hạn và bị xóa. Một object session trong heap hoặc một cookie trong request không chứng minh session còn hợp lệ.

Sau restore, ứng dụng nên:

- Kết nối lại session store.
- Kiểm tra session ID còn tồn tại và chưa bị thu hồi.
- Kiểm tra idle timeout và absolute expiration.
- Xác minh session chưa bị logout hoặc revoke.
- Chỉ chấp nhận session nếu server-side state còn hợp lệ.

Không nên tự tạo lại session chỉ vì object session đã có trong heap.

### 5.2 Idle timeout và absolute timeout khác nhau

| Loại timeout | Ý nghĩa | Ví dụ |
|---|---|---|
| Idle timeout | Hết hạn nếu không có hoạt động trong một khoảng thời gian | 30 phút không có request hợp lệ |
| Absolute timeout | Hết hạn tại một thời điểm, bất kể hoạt động | Session kết thúc sau 12 giờ |
| Sliding expiration | Hạn được dời khi có hoạt động hợp lệ | Mỗi request hợp lệ cập nhật thời điểm hết hạn |
| Revocation | Session bị thu hồi chủ động | Người dùng logout hoặc quản trị viên khóa tài khoản |

Nếu session được checkpoint trong heap với lastAccessedTime cũ, sau restore không nên đặt lastAccessedTime thành thời gian hiện tại chỉ để giữ session sống. Làm như vậy có thể vô tình gia hạn session và phá vỡ chính sách bảo mật.

Sliding expiration chỉ nên được cập nhật bởi một hoạt động người dùng hợp lệ theo quy tắc của hệ thống, không phải bởi việc tiến trình được restore.

### 5.3 Cookie không phải là session

Cookie có thể chứa session ID, token hoặc thông tin định danh. Thời hạn cookie ở browser và thời hạn session ở server là hai chính sách khác nhau.

- Cookie có thể vẫn còn ở browser trong khi session server đã hết hạn.
- Session server có thể còn tồn tại trong khi cookie đã hết hạn hoặc bị xóa.
- Restore ứng dụng không làm browser tự nhận cookie mới.
- Một session ID bị revoke không trở nên hợp lệ chỉ vì nó còn trong heap.

Ứng dụng cần xác minh trạng thái session ở nơi quản lý có thẩm quyền.

### 5.4 Không checkpoint một session state không nhất quán

Nếu session store được cập nhật đồng thời với object session trong heap, checkpoint có thể chụp ở giữa một thay đổi. Hãy đồng bộ các thao tác session hoặc chỉ checkpoint tại điểm an toàn.

Với session store bên ngoài, sau restore nên đọc lại trạng thái cần thiết thay vì tin rằng bản cache trong heap luôn mới nhất. Nếu session state có thể thay đổi bởi nhiều instance, server-side store phải là nguồn dữ liệu chuẩn.

## 6. Access token và thời hạn exp

Access token thường được dùng để gọi API hoặc truy cập tài nguyên. Token có thể là JWT hoặc opaque token. Dù định dạng khác nhau, thời hạn do authorization server hoặc resource server quy định.

### 6.1 JWT exp

Trong JWT, claim exp biểu diễn thời điểm token hết hạn theo NumericDate, tức số giây tính từ Unix epoch theo quy ước UTC.

Một resource server không được chấp nhận token tại hoặc sau thời điểm hết hạn, ngoại trừ một khoảng leeway nhỏ nếu chính sách cho phép để xử lý clock skew.

Các claim thời gian thường gặp:

| Claim | Ý nghĩa |
|---|---|
| iat | Thời điểm token được phát hành |
| nbf | Token không hợp lệ trước thời điểm này |
| exp | Token hết hạn tại thời điểm này |
| auth_time | Thời điểm người dùng xác thực, nếu issuer cung cấp |

Sau restore, cần kiểm tra cả exp và nbf nếu ứng dụng tự xác thực JWT. Tuy nhiên, nếu token được xác minh ở resource server, server vẫn là nơi quyết định cuối cùng.

### 6.2 OAuth expires_in

Với OAuth 2.0, token response thường có trường expires_in biểu diễn thời lượng access token còn hiệu lực tính bằng giây kể từ khi token response được tạo.

Khi nhận response, ứng dụng nên chuyển thời lượng thành một thời điểm hết hạn tuyệt đối:

~~~java
Instant receivedAt = clock.instant();
Instant expiresAt = receivedAt.plusSeconds(expiresIn);
~~~

Có thể trừ một safety margin để tránh bắt đầu request ngay sát thời điểm token hết hạn:

~~~java
Instant refreshAt = expiresAt.minusSeconds(30);
~~~

Margin phụ thuộc latency, clock skew và chính sách issuer. Không nên hard-code một con số cho mọi hệ thống.

Nếu chỉ lưu expiresIn=3600 vào image rồi restore sau 50 phút và lại bắt đầu đếm 3600 giây từ đầu, ứng dụng đã vô tình gia hạn token thêm 50 phút. Hãy lưu expiresAt hoặc lấy trạng thái token mới từ token provider sau restore.

### 6.3 Kiểm tra token trước khi sử dụng

Một client có thể kiểm tra thời hạn trước khi gửi request:

~~~java
public boolean needsRefresh(
        Instant expiresAt,
        Clock clock,
        Duration refreshSkew) {

    return !clock.instant()
            .plus(refreshSkew)
            .isBefore(expiresAt);
}
~~~

Nếu token đã hết hạn hoặc gần hết hạn, hãy refresh theo giao thức của issuer. Nếu refresh thất bại, không gửi request bằng token cũ và không đánh dấu client đã authenticated.

Không dựa vào một boolean như authenticated=true được checkpoint từ trước. Trạng thái xác thực cần được đánh giá theo token và server-side policy hiện tại.

### 6.4 Opaque token

Opaque token không chứa claim exp mà client có thể tự đọc. Client thường nhận expires_in trong token response hoặc phải hỏi authorization server/resource server để biết trạng thái.

Không cố phân tích opaque token như JWT. Dùng metadata do issuer trả về và xử lý phản hồi 401/invalid_token theo chuẩn của hệ thống.

## 7. Refresh token và rotation sau restore

Refresh token thường có vòng đời dài hơn access token. Nó được dùng để yêu cầu access token mới, nhưng có thể bị revoke, hết hạn hoặc rotate.

### 7.1 Refresh token có thể đã hết hạn hoặc bị thu hồi

Nếu checkpoint image chứa refresh token, token đó có thể không còn hợp lệ khi restore vì:

- Đã tới absolute expiration.
- Người dùng đã logout hoặc revoke consent.
- Quản trị viên đã thu hồi phiên.
- Issuer đã rotate refresh token.
- Chính sách phát hiện reuse đã kích hoạt.
- Credential hoặc client registration đã thay đổi.

Ứng dụng nên xem refresh token như credential cần xác minh lại với authorization server. Không giả định refresh token trong heap luôn còn dùng được.

### 7.2 Refresh token rotation và nhiều bản restore

Một rủi ro đặc biệt xuất hiện khi một image được restore thành nhiều instance.

Giả sử image chứa refresh token R1. Hai instance A và B được restore từ cùng image:

~~~text
Checkpoint image chứa R1
       /          \
      v            v
 Instance A     Instance B
      |            |
 Refresh R1     Refresh R1
      |            |
 Issuer cấp R2   Issuer thấy R1 đã dùng
      |            |
 Thành công      Có thể phát hiện reuse/revoke family
~~~

Với refresh token rotation, authorization server có thể cấp token mới mỗi lần sử dụng và vô hiệu hóa token cũ. Một số issuer còn phát hiện việc dùng lại token cũ và thu hồi cả token family.

Do đó, hai replica restore cùng một refresh token có thể tạo race condition và làm mất khả năng refresh của cả nhóm.

Các cách thiết kế phù hợp:

- Không đặt refresh token dùng chung trong image được nhân bản.
- Mỗi instance lấy credential riêng sau restore bằng workload identity hoặc cơ chế cấp credential của nền tảng.
- Dùng một token broker hoặc một thành phần duy nhất sở hữu refresh token và đồng bộ việc refresh.
- Nếu issuer hỗ trợ, dùng cơ chế refresh có kiểm soát concurrency và lưu token rotation mới một cách nguyên tử.
- Xử lý invalid_grant hoặc reuse detection bằng quy trình xác thực lại, không retry vô hạn với token cũ.

Cần xem chính sách cụ thể của authorization server. Không phải mọi issuer đều triển khai rotation hoặc reuse detection giống nhau.

### 7.3 Lưu token rotation an toàn

Khi refresh thành công và issuer trả refresh token mới, ứng dụng phải cập nhật trạng thái token theo cách nguyên tử. Nếu crash giữa lúc issuer đã rotate nhưng ứng dụng chưa lưu token mới, token cũ có thể không dùng lại được.

Nếu token được lưu ở một kho bên ngoài, hãy dùng cơ chế cập nhật có version hoặc compare-and-set để tránh ghi đè token mới bằng token cũ từ một instance khác.

Không log access token, refresh token hoặc authorization header. Checkpoint image chứa heap nên có thể chứa credential; cần kiểm soát quyền truy cập, mã hóa, thời hạn lưu và quy trình xóa image cũ theo chính sách bảo mật.

## 8. Clock skew và nguồn thời gian

Các service có thể chạy trên nhiều host với đồng hồ không hoàn toàn giống nhau. Nếu issuer và client lệch giờ, token có thể bị xem là chưa hợp lệ hoặc đã hết hạn sớm.

### 8.1 Đồng bộ thời gian hệ thống

Dùng cơ chế đồng bộ thời gian của nền tảng, thường là NTP hoặc dịch vụ time synchronization của cloud. Sau restore trên host khác, cần bảo đảm host đích có đồng hồ được đồng bộ.

Không tự điều chỉnh đồng hồ ứng dụng để làm token hợp lệ. Nếu có clock skew, hãy xử lý theo chính sách leeway được issuer và resource server hỗ trợ.

### 8.2 Leeway phải có giới hạn

Một khoảng leeway nhỏ có thể giúp xử lý chênh lệch đồng hồ khi kiểm tra exp hoặc nbf. Nhưng leeway quá lớn kéo dài thời gian token được chấp nhận và làm suy yếu chính sách hết hạn.

Nếu server là nơi xác thực JWT, hãy dùng cấu hình thống nhất giữa các resource server. Nếu client cần refresh sớm, dùng refresh skew riêng để tránh gửi token ở sát thời điểm hết hạn.

### 8.3 Không dùng timestamp local làm nguồn có thẩm quyền cho mọi session

Nếu session hoặc token được quản lý bởi dịch vụ bên ngoài, trạng thái bên ngoài là nguồn có thẩm quyền. Timestamp local có thể dùng để tối ưu quyết định refresh, nhưng server vẫn có thể từ chối token hoặc session đã revoke.

Hãy xử lý các phản hồi như 401, invalid_token, invalid_grant hoặc session_not_found theo đúng giao thức. Một lần kiểm tra thời hạn local thành công không đảm bảo trạng thái server chưa thay đổi.

## 9. Distributed lease, lock và reservation

Thời hạn không chỉ xuất hiện trong authentication. Ứng dụng có thể giữ lease để xử lý job, làm leader hoặc bảo vệ tài nguyên dùng chung.

Ví dụ, một worker nhận lease có TTL 60 giây. Sau 10 giây, tiến trình được checkpoint trong 5 phút. Khi restore, lease đã hết hạn và có thể đã được worker khác nhận.

Không được tiếp tục thao tác chỉ vì object Lease trong heap vẫn ghi state=ACTIVE.

### 9.1 Kiểm tra lease và reacquire

Sau restore:

1. Đọc lại lease từ hệ thống cấp lease.
2. Kiểm tra expiresAt hoặc TTL hiện tại.
3. Xác minh owner và fencing token.
4. Nếu lease hết hạn, dừng công việc.
5. Nếu cần tiếp tục, reacquire lease bằng thao tác nguyên tử.
6. Chỉ thực hiện side effect sau khi quyền sở hữu được xác minh.

### 9.2 Fencing token

Lease có thể hết hạn nhưng worker cũ vẫn tiếp tục chạy nếu nó không biết mình đã mất quyền sở hữu. Fencing token giúp hệ thống đích từ chối thao tác từ owner cũ.

Mỗi lần cấp lease, hệ thống tăng một token hoặc generation. Tài nguyên được bảo vệ ghi nhận token mới nhất và từ chối request có token cũ.

Sau restore, không dùng fencing token đã checkpoint nếu lease đã hết hạn hoặc được cấp lại. Hãy lấy token hiện tại từ lease service trước khi tiếp tục.

### 9.3 Reservation và payment authorization

Reservation ghế, kho hàng hoặc payment authorization có thể hết hạn trong khi image đang được giữ. Ứng dụng cần hỏi dịch vụ nghiệp vụ về trạng thái hiện tại trước khi xác nhận hoặc tiếp tục.

Một object Reservation trong heap không phải bằng chứng rằng hàng hóa vẫn được giữ. Dùng idempotency key và truy vấn trạng thái để tránh tạo reservation hoặc payment mới ngoài ý muốn.

## 10. Scheduler, timer và tác vụ định kỳ

Một ScheduledExecutorService hoặc scheduler có thể giữ các tác vụ với delay và trạng thái nội bộ. Không nên mặc định mọi timer sẽ có semantics mong muốn khi tiến trình checkpoint rồi restore.

### 10.1 Lưu thời điểm chạy, không chỉ lưu delay

Nếu một báo cáo phải chạy lúc 02:00 UTC, lưu Instant của lần chạy tiếp theo. Sau restore, tính lại thời gian còn lại:

~~~java
Duration delay = Duration.between(
        clock.instant(),
        nextRunAt);

if (delay.isNegative() || delay.isZero()) {
    runOrSkipAccordingToPolicy();
} else {
    scheduler.schedule(
            this::runJob,
            delay.toMillis(),
            TimeUnit.MILLISECONDS);
}
~~~

Nếu job đã quá hạn, quyết định chạy bù, bỏ qua hoặc gộp nhiều lần chạy tùy nghiệp vụ. Không tự động chạy tất cả các lần bị bỏ lỡ nếu chúng có side effect.

### 10.2 Tránh chạy job hai lần

Nếu scheduler đã lưu job state trong heap và sauRestore lại đăng ký cùng job, ứng dụng có thể chạy hai bản. Hãy quản lý registration bằng một owner rõ ràng, hủy hoặc rebuild scheduler theo lifecycle và dùng job ID/lease để ngăn chạy trùng giữa nhiều replica.

### 10.3 Fixed rate và fixed delay

- fixedRate cố gắng giữ nhịp theo lịch.
- fixedDelay tính khoảng nghỉ sau khi lần chạy trước kết thúc.

Sau checkpoint, nhiều lần chạy theo fixedRate có thể đã bị bỏ lỡ. Hãy quyết định có catch up hay bỏ qua. Với fixedDelay, cần xác định thời điểm lần chạy trước thực sự hoàn tất và liệu thời gian checkpoint có được tính vào delay tiếp theo hay không.

Không để logic thời gian ngầm của scheduler quyết định chính sách nghiệp vụ.

## 11. Quản lý thời hạn trong CRaC Resource

Resource callback có thể giúp ứng dụng chuẩn bị trước checkpoint và xác minh lại sau restore. Không phải mọi token hoặc deadline đều cần một Resource riêng; nên có một thành phần quản lý lifecycle cho từng nhóm phụ thuộc.

Ví dụ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CredentialResource implements Resource {

    private final Clock clock;
    private final TokenProvider tokenProvider;
    private final AtomicReference<AccessToken> token =
            new AtomicReference<>();

    public CredentialResource(
            Clock clock,
            TokenProvider tokenProvider) {
        this.clock = clock;
        this.tokenProvider = tokenProvider;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        // Không gia hạn token chỉ để checkpoint.
        // Có thể dừng refresh task và lưu trạng thái không nhạy cảm.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        AccessToken current = token.get();

        if (current == null
                || !clock.instant().isBefore(current.expiresAt())) {
            token.set(tokenProvider.acquireOrRefresh());
        } else {
            tokenProvider.validateOrRefreshIfNeeded(current);
        }
    }
}
~~~

AccessToken và TokenProvider ở đây là kiểu abstraction của ứng dụng. Trong thực tế, không nên tự viết refresh protocol nếu thư viện OAuth/OIDC đã quản lý rotation, concurrency và error handling. Ví dụ chỉ minh họa rằng sau restore cần kiểm tra thời hạn và lấy credential hợp lệ.

Nếu token provider cần network, callback afterRestore có thể thất bại do dịch vụ xác thực chưa sẵn sàng. Khi đó, ứng dụng phải giữ readiness false hoặc dùng một cơ chế phục hồi bất đồng bộ có kiểm soát nếu runtime/framework cho phép. Không được giả vờ xác thực thành công.

### 11.1 Không chờ network vô hạn trong callback

Các callback phải có timeout hữu hạn. Nếu authorization server không phản hồi, một callback reconnect có thể làm restore kéo dài vô hạn hoặc thất bại.

Dùng connect timeout, request timeout, retry có giới hạn và backoff. Nếu ứng dụng cho phép khởi động ở chế độ chưa ready rồi phục hồi sau, hãy triển khai lifecycle rõ ràng thay vì giữ callback chờ mãi.

### 11.2 Tránh side effect không idempotent trong callback

Không tạo session mới, đăng ký webhook mới hoặc phát hành credential mới trong afterRestore nếu thao tác đó có thể lặp khi restore retry hoặc nhiều instance cùng restore.

Nếu cần tạo credential per-instance, hãy dùng idempotency key hoặc workload identity của instance. Lưu metadata định danh của instance theo cách không bị chia sẻ nhầm giữa các replica.

## 12. Kiểm thử thời gian mà không cần chờ thật

Dùng Clock injection để kiểm thử deadline và token expiry một cách xác định. Clock.fixed() cho phép mô phỏng thời điểm hiện tại.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock checkpointTime = Clock.fixed(
        Instant.parse("2026-11-13T10:00:00Z"),
        ZoneOffset.UTC);

Clock restoreTime = Clock.fixed(
        Instant.parse("2026-11-13T10:45:00Z"),
        ZoneOffset.UTC);

Instant expiresAt =
        Instant.parse("2026-11-13T10:30:00Z");

boolean validAtCheckpoint =
        checkpointTime.instant().isBefore(expiresAt);

boolean validAfterRestore =
        restoreTime.instant().isBefore(expiresAt);

// validAtCheckpoint = true
// validAfterRestore = false
~~~

Có thể viết test cho các trường hợp:

- Token còn hạn trước checkpoint nhưng hết hạn sau restore.
- Request deadline đã qua trong thời gian checkpoint.
- Session bị revoke trong khi ứng dụng không chạy.
- Refresh token bị rotate bởi một instance khác.
- Lease hết hạn và được cấp lại cho worker mới.
- Scheduler có nhiều lần chạy bị bỏ lỡ.
- Đồng hồ local lệch so với issuer.
- Một credential vẫn còn hạn nhưng đã bị revoke.

Đối với code dùng nanoTime(), hãy tách phần tính toán thời gian khỏi logic nghiệp vụ và dùng abstraction clock/ticker để test. Không dùng Clock.fixed() để giả lập nanoTime trực tiếp; hai loại clock có semantics khác nhau.

## 13. Các tình huống vận hành cần xử lý

| Tình huống sau restore | Hành vi phù hợp |
|---|---|
| Request deadline còn hạn | Tính thời gian còn lại và tiếp tục nếu workflow hỗ trợ |
| Request deadline đã qua | Hủy hoặc đánh dấu expired; không tạo deadline mới |
| Access token gần hết hạn | Refresh theo chính sách và concurrency control |
| Access token đã hết hạn | Không gửi token cũ; refresh hoặc xác thực lại |
| Refresh token bị revoke | Yêu cầu re-authentication hoặc cấp credential mới |
| Session server đã hết hạn | Từ chối session và yêu cầu đăng nhập lại |
| Session còn hạn nhưng đã logout/revoke | Tôn trọng trạng thái revoke của server |
| Lease đã hết hạn | Reacquire và lấy fencing token mới |
| Reservation đã hết hạn | Truy vấn trạng thái và thực hiện lại theo idempotency |
| Scheduled job đã quá giờ | Chạy bù, bỏ qua hoặc gộp theo chính sách |
| Clock skew lớn | Giữ trạng thái chưa xác định và xử lý theo nguồn thời gian có thẩm quyền |

Một ứng dụng nên có trạng thái rõ ràng cho từng dependency: VALID, EXPIRED, REVOKED, REFRESHING hoặc UNKNOWN. Trạng thái UNKNOWN không nên được xem là VALID. Nếu chưa thể xác minh do network lỗi, hãy giữ readiness false cho chức năng phụ thuộc credential đó.

## 14. Những sai lầm thường gặp

### Lưu expiresIn rồi đếm lại từ đầu sau restore

expiresIn là thời lượng tại thời điểm nhận token. Nếu restore sau khi thời lượng đã trôi qua, bắt đầu lại từ đầu sẽ kéo dài hiệu lực giả tạo. Hãy lưu expiresAt.

### Dùng nanoTime làm timestamp

nanoTime không phải epoch time. Không lưu giá trị này như một thời hạn có thể so sánh trên host khác hoặc sau một vòng đời thực thi khác.

### Tin boolean authenticated đã checkpoint

Token có thể hết hạn hoặc bị revoke. Xác minh lại credential sau restore và trước khi dùng.

### Gia hạn session chỉ vì restore

Restore không phải hoạt động của người dùng. Không cập nhật lastAccessedTime hoặc sliding expiration chỉ vì tiến trình chạy lại.

### Dùng chung refresh token trong image nhân bản

Nhiều instance có thể đồng thời dùng một refresh token đã rotate. Dùng credential per-instance hoặc một token owner có concurrency control.

### Tiếp tục giữ lease cũ

Lease có thể hết hạn trong lúc checkpoint. Revalidate ownership và fencing token trước side effect.

### Chạy lại mọi scheduler task

Các job đã quá hạn không nhất thiết phải chạy tất cả. Xác định catch-up policy và bảo đảm không chạy trùng.

### Dùng đồng hồ local làm nguồn xác thực cuối cùng

Clock skew, revocation và thay đổi server-side có thể làm trạng thái local lỗi thời. Dịch vụ có thẩm quyền vẫn quyết định token/session/lease có hợp lệ hay không.

### Log token hoặc session secret

Checkpoint image và log đều có thể chứa dữ liệu nhạy cảm. Không ghi credential vào log, và bảo vệ image theo chính sách truy cập, mã hóa và retention.

## 15. Quy trình triển khai

Khi đưa ứng dụng Java có deadline, session và token vào CRaC, có thể áp dụng trình tự sau:

**Bước 1 — Kiểm kê thời hạn.** Tìm request timeout, workflow deadline, session TTL, access/refresh token, lease, reservation và scheduler.

**Bước 2 — Chọn semantics.** Xác định thời gian checkpoint có được tính vào mỗi thời hạn hay không. Ưu tiên deadline tuyệt đối cho request, token và lease do hệ thống bên ngoài quản lý.

**Bước 3 — Tách wall clock và monotonic clock.** Dùng Instant/Clock cho thời điểm hết hạn và nanoTime cho đo elapsed time trong một lần thực thi. Không lưu nanoTime deadline qua restore.

**Bước 4 — Tái xác minh trạng thái bên ngoài.** Sau restore, kiểm tra session store, token issuer, lease service và reservation service. Không coi object trong heap là nguồn sự thật cuối cùng.

**Bước 5 — Xử lý refresh có kiểm soát.** Quản lý rotation, concurrency, idempotency và credential per-instance. Tránh chia sẻ refresh token trong image được restore thành nhiều replica.

**Bước 6 — Khôi phục scheduler và workflow.** Tính lại thời gian còn lại từ deadline gốc; quyết định rõ chạy bù, bỏ qua hoặc tiếp tục.

**Bước 7 — Giữ readiness đúng trạng thái.** Không nhận traffic hoặc thực hiện side effect phụ thuộc credential cho tới khi thời hạn và quyền sở hữu được xác minh.

**Bước 8 — Kiểm thử thời gian.** Dùng Clock cố định để mô phỏng thời gian trôi qua, đồng thời thử restore thật trên môi trường mục tiêu và các tình huống revoke/rotation.

**Bước 9 — Quan sát và truy vết.** Ghi timestamp, checkpoint ID, instance ID, token issuer hoặc session reference không nhạy cảm, kết quả refresh và nguyên nhân hết hạn. Không log secret.

## Tài liệu tham khảo

- [Java API — Instant](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Instant.html): thời điểm tuyệt đối theo epoch.
- [Java API — Clock](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Clock.html): nguồn thời gian có thể thay thế khi kiểm thử.
- [Java API — System.nanoTime()](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime()): đo thời gian đã trôi qua bằng đồng hồ đơn điệu.
- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và vòng đời ứng dụng.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): quản lý Resource qua beforeCheckpoint và afterRestore.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): NumericDate và các claim iat, nbf, exp.
- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): expires_in, access token và refresh token.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, replay detection và bảo vệ token.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics của request, response và timeout ở tầng HTTP.

