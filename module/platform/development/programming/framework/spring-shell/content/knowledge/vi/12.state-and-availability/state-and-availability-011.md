# Kiểm tra trạng thái lại ngay trước thao tác quan trọng

## 1. Trạng thái ứng dụng có thể thay đổi sau khi command được hiển thị

Một command có thể đã được đăng ký nhưng chỉ có ý nghĩa khi ứng dụng ở một trạng thái nhất định. Ví dụ:

- `remote download` chỉ dùng được sau khi kết nối đến máy chủ từ xa.
- `release publish` chỉ được phép khi cửa sổ phát hành đang mở và bản phát hành đã được duyệt.
- `order ship` chỉ thực hiện được khi đơn hàng đã thanh toán và hàng đã được đóng gói.
- `account unlock` chỉ thực hiện được khi tài khoản đang bị khóa và người vận hành có quyền phù hợp.

Nếu command luôn xuất hiện như thể có thể chạy, người dùng sẽ phải thử lệnh rồi mới biết điều kiện chưa thỏa mãn. Spring Shell cung cấp cơ chế **command availability** để biểu thị command hiện có thể thực thi hay không và giải thích lý do khi command chưa khả dụng.

Tuy nhiên, trạng thái được kiểm tra khi hiển thị trợ giúp hoặc trước lúc gọi command có thể thay đổi ngay sau đó. Một cửa sổ phát hành có thể đóng, phiên đăng nhập có thể hết hạn, quyền có thể bị thu hồi hoặc một tiến trình khác có thể chuyển đơn hàng sang trạng thái mới. Vì vậy, availability giúp người dùng hiểu tình trạng hiện tại; service vẫn phải kiểm tra lại điều kiện ngay trước thao tác quan trọng.

## 2. Availability và AvailabilityProvider trong Spring Shell 4.x

Spring Shell 4.x đặt API availability trong package:

~~~java
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;
~~~

`Availability` biểu diễn một trong hai trạng thái:

- `Availability.available()` cho biết command hiện khả dụng.
- `Availability.unavailable(reason)` cho biết command chưa khả dụng và cung cấp lý do.

`AvailabilityProvider` là functional interface mở rộng `Supplier<Availability>`. Vì vậy, có thể triển khai bằng lambda hoặc method reference. Provider được hỏi để xác định trạng thái hiện tại của command; nó không nhận tham số command và không nên thực hiện thay đổi dữ liệu.

Một provider đơn giản:

~~~java
AvailabilityProvider downloadAvailability = () ->
        sessionService.isConnected()
                ? Availability.available()
                : Availability.unavailable("the remote server is not connected");
~~~

Khi command không khả dụng, Spring Shell thông báo command vẫn tồn tại nhưng hiện không thể gọi, kèm lý do provider trả về. Lý do nên là một cụm từ ngắn, viết thường và không có dấu chấm cuối vì framework nối nó sau từ “because”. Ví dụ:

~~~text
shell:>remote download
Command 'remote download' exists but is not currently available because the remote server is not connected.
~~~

Không đưa mật khẩu, token, thông tin kết nối hoặc dữ liệu nhạy cảm vào lý do availability. Đây là thông báo cho người vận hành, không phải nơi ghi log chi tiết.

## 3. Gắn AvailabilityProvider với command khai báo bằng annotation

Trong Spring Shell 4.x, thuộc tính `availabilityProvider` của `@Command` nhận **tên bean** cung cấp availability. Ví dụ, một command phát hành chỉ khả dụng trong thời gian cửa sổ phát hành đang mở:

~~~java
package com.example.release;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReleaseCommands {

    private final ReleaseService releaseService;

    public ReleaseCommands(ReleaseService releaseService) {
        this.releaseService = releaseService;
    }

    @Command(
            name = "release publish",
            description = "Đưa một bản phát hành vào quy trình triển khai",
            group = "Release",
            availabilityProvider = "publishAvailability",
            help = "Chỉ khả dụng trong cửa sổ phát hành và với bản phát hành đã được duyệt.")
    public String publish(
            @Option(longName = "id", required = true,
                    description = "Mã bản phát hành") long releaseId) {

        PublishReceipt receipt = releaseService.publish(releaseId);
        return "Đã tiếp nhận bản phát hành " + receipt.releaseId()
                + " với mã yêu cầu " + receipt.requestId();
    }
}
~~~

Khai báo bean provider:

~~~java
package com.example.release;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

@Configuration
public class ReleaseAvailabilityConfiguration {

    @Bean
    AvailabilityProvider publishAvailability(PublishingWindowQuery windowQuery) {
        return () -> windowQuery.isOpenNow()
                ? Availability.available()
                : Availability.unavailable(
                        "the publishing window is closed; check the release schedule");
    }
}
~~~

Tên phương thức `publishAvailability` cũng là tên bean mặc định, nên khớp với `availabilityProvider = "publishAvailability"`. Provider chỉ đọc trạng thái cửa sổ phát hành. Nó không đặt lịch, không mở cửa sổ và không thay đổi trạng thái bản phát hành.

Với Spring Shell 4.x, `@Command` được đặt trên phương thức của một Spring-managed bean như `@Component` hoặc `@Service`. Khi dùng Spring Boot, command scanning được bật tự động. Thuộc tính `availabilityProvider` là cách cấu hình availability trong mô hình annotation 4.x.

Khi đọc ví dụ Spring Shell 3.x, bạn có thể gặp annotation availability riêng như `@CommandAvailability` hoặc `@ShellMethodAvailability`. Mô hình 4.x đưa cấu hình này vào thuộc tính `availabilityProvider` của `@Command`; hãy dùng API đúng phiên bản của dự án.

## 4. Gắn availability khi tạo command bằng builder

Nếu command được tạo theo API programmatic, gọi `availabilityProvider(...)` trên `Command.Builder`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.availability.Availability;

@Bean
Command releasePublishCommand(
        PublishingWindowQuery windowQuery,
        ReleaseService releaseService) {

    return Command.builder()
            .name("release publish")
            .description("Đưa một bản phát hành vào quy trình triển khai")
            .options(CommandOption.with()
                    .longName("id")
                    .description("Mã bản phát hành")
                    .required(true)
                    .type(Long.class)
                    .build())
            .availabilityProvider(() -> windowQuery.isOpenNow()
                    ? Availability.available()
                    : Availability.unavailable("the publishing window is closed"))
            .execute(context -> {
                String id = context.getOptionByName("id").value();
                PublishReceipt receipt = releaseService.publish(Long.parseLong(id));
                context.outputWriter().println(
                        "Đã tiếp nhận bản phát hành " + receipt.releaseId());
            });
}
~~~

Builder và annotation cùng dùng `AvailabilityProvider` và `Availability`. Chọn cách khai báo phù hợp với cách ứng dụng đang tổ chức command; không cần xây hai command riêng chỉ để hỗ trợ hai kiểu đăng ký.

## 5. Cập nhật trạng thái dùng chung qua service

Nhiều command thường phụ thuộc vào cùng một trạng thái. Ví dụ, `remote download`, `remote upload` và `remote list` đều cần một phiên kết nối hợp lệ. Nên đặt trạng thái và các thao tác chuyển trạng thái trong một service chuyên trách để command và provider cùng đọc một nguồn dữ liệu.

~~~java
package com.example.remote;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Service;

@Service
public class RemoteSessionService {

    private final AtomicReference<RemoteSession> currentSession =
            new AtomicReference<>();

    public boolean isConnected() {
        RemoteSession session = currentSession.get();
        return session != null && session.isLocallyOpen();
    }

    public void connect(String host, String user) {
        // RemoteSession lấy thông tin xác thực từ secure credential provider.
        RemoteSession next = RemoteSession.open(host, user);
        RemoteSession previous = currentSession.getAndSet(next);
        if (previous != null) {
            previous.close();
        }
    }

    public RemoteSession requireUsableSession() {
        RemoteSession session = currentSession.get();
        if (session == null || !session.isLocallyOpen()) {
            throw new RemoteSessionUnavailableException(
                    "the remote session is no longer available; run remote connect again");
        }
        return session;
    }

    public void disconnect() {
        RemoteSession previous = currentSession.getAndSet(null);
        if (previous != null) {
            previous.close();
        }
    }
}
~~~

Các lớp `RemoteSession` và `RemoteSessionUnavailableException` là thành phần của ứng dụng ví dụ. `AtomicReference` bảo đảm việc thay thế và đọc tham chiếu an toàn giữa các luồng, nhưng không giữ session sống trong suốt thao tác sau khi `requireUsableSession()` trả về. Nếu `disconnect()` có thể chạy đồng thời với `download()`, hãy dùng cơ chế lease hoặc khóa vòng đời để không đóng session khi request đang sử dụng nó. `isLocallyOpen()` chỉ kiểm tra trạng thái mà client đang biết; nó không thể bảo đảm máy chủ từ xa vẫn chấp nhận phiên ở thời điểm gửi request.

Các command liên quan có thể chia sẻ service này:

~~~java
package com.example.remote;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommands {

    private final RemoteSessionService sessionService;
    private final RemoteFileService fileService;

    public RemoteCommands(RemoteSessionService sessionService,
            RemoteFileService fileService) {
        this.sessionService = sessionService;
        this.fileService = fileService;
    }

    @Command(name = "remote connect", description = "Kết nối đến máy chủ từ xa")
    public String connect(
            @Option(longName = "host", required = true) String host,
            @Option(longName = "user", required = true) String user) {
        sessionService.connect(host, user);
        return "Đã kết nối đến " + host;
    }

    @Command(name = "remote download",
            description = "Tải tệp từ máy chủ từ xa",
            availabilityProvider = "remoteDownloadAvailability")
    public String download(
            @Option(longName = "path", required = true) String path) {
        return fileService.download(path);
    }

    @Command(name = "remote disconnect", description = "Ngắt kết nối máy chủ từ xa")
    public String disconnect() {
        sessionService.disconnect();
        return "Đã ngắt kết nối";
    }

    @Bean
    AvailabilityProvider remoteDownloadAvailability() {
        return () -> sessionService.isConnected()
                ? Availability.available()
                : Availability.unavailable("the remote server is not connected");
    }
}
~~~

Ví dụ minh họa cách chia sẻ trạng thái trong một ứng dụng shell đơn giản. Trong hệ thống nhiều người dùng, nhiều shell session hoặc nhiều instance ứng dụng, không nên lưu trạng thái đăng nhập của mọi người trong một field singleton như `currentSession`. Hãy lưu phiên theo người dùng/session hoặc dùng kho trạng thái có định danh và cơ chế đồng bộ phù hợp. Nếu dùng mutable state trong bean singleton, cần bảo đảm an toàn luồng.

## 6. Availability không thay thế kiểm tra tại service

Hãy xem một trình tự có thể xảy ra:

1. Người vận hành mở `help`; `publishAvailability` xác nhận cửa sổ phát hành đang mở.
2. Một quản trị viên khác đóng cửa sổ phát hành.
3. Người vận hành gọi `release publish --id=42` dựa trên thông tin vừa thấy.
4. Nếu command chỉ tin kết quả ở bước 1, nó có thể thực hiện thao tác trong lúc cửa sổ đã đóng.

Đây là lỗi **time-of-check to time-of-use (TOCTOU)**: điều kiện đúng ở thời điểm kiểm tra nhưng có thể sai khi sử dụng. Availability không giữ khóa, không mở transaction và không khóa trạng thái cho đến lúc command chạy.

Do đó, command chỉ nên dùng availability để phản hồi sớm và hướng dẫn người dùng. Service phải đọc lại trạng thái có thẩm quyền ngay trước mutation, đồng thời dùng transaction, lock hoặc cập nhật có điều kiện nếu trạng thái có thể bị thay đổi đồng thời.

## 7. Kiểm tra lại và khóa trạng thái trong service

Với thao tác phát hành, service có thể kiểm tra cửa sổ và trạng thái bản phát hành trong cùng transaction. Nếu các điều kiện này được quản lý trong database, repository có thể lấy bản ghi chính sách và bản phát hành bằng pessimistic lock:

~~~java
package com.example.release;

import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReleaseService {

    private final PublishingWindowRepository windowRepository;
    private final ReleaseRepository releaseRepository;
    private final Clock clock;

    public ReleaseService(PublishingWindowRepository windowRepository,
            ReleaseRepository releaseRepository, Clock clock) {
        this.windowRepository = windowRepository;
        this.releaseRepository = releaseRepository;
        this.clock = clock;
    }

    @Transactional
    public PublishReceipt publish(long releaseId) {
        Instant now = clock.instant();

        // Đọc khóa chính sách để cửa sổ không thể bị đổi giữa lúc kiểm tra và cập nhật.
        PublishingWindow window = windowRepository.findCurrentForUpdate()
                .orElseThrow(() -> new PublishingWindowClosedException(
                        "the publishing window is not configured"));

        if (!window.isOpenAt(now)) {
            throw new PublishingWindowClosedException(
                    "the publishing window has closed; check the release schedule");
        }

        Release release = releaseRepository.findByIdForUpdate(releaseId)
                .orElseThrow(() -> new ReleaseNotFoundException(releaseId));

        if (release.getStatus() != ReleaseStatus.APPROVED) {
            throw new ReleaseStateException(
                    "release " + releaseId + " is not approved for publishing");
        }

        release.startPublishing(now);
        releaseRepository.save(release);

        return new PublishReceipt(release.getId(), release.getRequestId());
    }
}
~~~

`findCurrentForUpdate()` và `findByIdForUpdate(...)` là tên phương thức repository minh họa. Với JPA, có thể triển khai bằng `@Lock(LockModeType.PESSIMISTIC_WRITE)` và truy vấn lấy đúng bản ghi cần khóa. Cần bảo đảm mọi luồng cập nhật cửa sổ phát hành cũng tuân theo cùng quy ước khóa; nếu không, việc khóa ở service không bảo vệ được trước một luồng ghi không phối hợp.

Ví dụ này thực hiện một bước chuyển trạng thái bền vững từ `APPROVED` sang `PUBLISHING`. Worker triển khai thực tế có thể xử lý phần công việc bên ngoài sau commit. Không nên giữ database transaction mở trong thời gian dài để chờ một máy chủ triển khai hoặc mạng bên ngoài.

Các kiểu `PublishingWindow`, `PublishingWindowRepository`, `Release`, `ReleaseRepository`, `ReleaseStatus`, `PublishReceipt` và các exception miền là kiểu của ứng dụng ví dụ, cần được định nghĩa trong project. Các exception dùng để rollback mặc định nên kế thừa `RuntimeException`, hoặc transaction phải khai báo `rollbackFor` tương ứng.

## 8. Dùng optimistic locking hoặc cập nhật có điều kiện

Pessimistic lock phù hợp khi cần khóa bản ghi trong lúc đọc và cập nhật. Với hệ thống tải cao hoặc thời gian giữ khóa ngắn, có thể dùng optimistic locking bằng `@Version`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Version;
import java.time.Instant;

@Entity
public class Release {

    @Id
    private Long id;

    private String requestId;

    @Enumerated(EnumType.STRING)
    private ReleaseStatus status;

    @Version
    private long version;

    private Instant publishingStartedAt;

    public Long getId() {
        return id;
    }

    public String getRequestId() {
        return requestId;
    }

    public ReleaseStatus getStatus() {
        return status;
    }

    public void startPublishing(Instant now) {
        if (status != ReleaseStatus.APPROVED) {
            throw new ReleaseStateException("release is not approved");
        }
        status = ReleaseStatus.PUBLISHING;
        publishingStartedAt = now;
    }
}
~~~

Nếu hai tiến trình cùng đọc một phiên bản rồi cùng cập nhật, một transaction sẽ commit trước; transaction còn lại gặp optimistic locking conflict khi ghi. Ứng dụng cần bắt lỗi xung đột ở ranh giới phù hợp, đọc lại trạng thái và trả thông báo “bản phát hành đã được xử lý bởi một tiến trình khác”.

Một cách khác là dùng câu lệnh cập nhật có điều kiện để kiểm tra và chuyển trạng thái trong một thao tác nguyên tử:

~~~sql
UPDATE release
SET status = 'PUBLISHING', version = version + 1
WHERE id = :releaseId
  AND status = 'APPROVED'
  AND version = :expectedVersion;
~~~

Nếu số dòng được cập nhật là `1`, tiến trình đã giành quyền chuyển trạng thái. Nếu là `0`, bản phát hành không còn ở trạng thái mong đợi hoặc phiên bản đã thay đổi; không được tiếp tục triển khai. Đây là cách kiểm tra điều kiện và cập nhật gắn với nhau, giảm khoảng trống giữa hai bước.

Pessimistic lock, optimistic locking và conditional update là các lựa chọn tùy mô hình dữ liệu. Hãy chọn một cơ chế nhất quán với cách mọi tiến trình đọc và cập nhật cùng trạng thái.

## 9. Khi thao tác quan trọng gọi hệ thống bên ngoài

Không phải mọi trạng thái đều nằm trong database của ứng dụng. Ví dụ, một phiên remote có thể bị máy chủ thu hồi, token có thể hết hạn hoặc quyền có thể thay đổi ở hệ thống định danh.

Trong trường hợp đó:

- Availability có thể dùng trạng thái client đã biết để hướng dẫn người dùng.
- Service phải kiểm tra lại session/token ngay trước khi gửi request.
- Máy chủ đích vẫn là nơi có thẩm quyền cuối cùng để xác thực phiên, quyền và điều kiện thực thi.
- Nếu server từ chối vì trạng thái vừa thay đổi, ứng dụng phải chuyển lỗi thành thông báo phù hợp và không giả định thao tác đã thành công.
- Với request có thể được gửi lại, dùng idempotency key hoặc request ID để tránh thực hiện trùng khi kết quả lần gọi trước không rõ ràng.

Ví dụ service tải tệp:

~~~java
@Service
public class RemoteFileService {

    private final RemoteSessionService sessionService;

    public RemoteFileService(RemoteSessionService sessionService) {
        this.sessionService = sessionService;
    }

    public String download(String path) {
        RemoteSession session = sessionService.requireUsableSession();
        // Dùng chính session đã được kiểm tra để gửi request.
        // Máy chủ từ xa vẫn phải xác nhận token/phiên khi nhận request.
        return session.download(path);
    }
}
~~~

Nếu session có thể bị đóng đồng thời, `requireUsableSession()` nên trả về một handle/lease có vòng đời rõ ràng hoặc đồng bộ hóa việc đóng và sử dụng. Chỉ đọc một boolean `connected` rồi sử dụng một object có thể đã bị đóng vẫn tạo ra race condition.

## 10. Availability không phải là phân quyền

Ẩn hoặc đánh dấu command unavailable không phải cơ chế bảo mật. Người dùng có thể gọi service qua một entry point khác, một command khác hoặc một API khác. Quyền truy cập phải được kiểm tra ở service hoặc tầng bảo mật có thẩm quyền.

Ví dụ, provider có thể kiểm tra người dùng hiện tại có vai trò vận hành hay không để hiển thị trạng thái command dễ hiểu. Nhưng `ReleaseService.publish(...)` vẫn phải thực hiện authorization cho người gọi trước khi thay đổi trạng thái. Không dựa vào việc command không xuất hiện trong help để bảo vệ dữ liệu.

Tương tự, availability không thay thế validation tham số. Provider thường kiểm tra trạng thái chung của command; các điều kiện phụ thuộc `releaseId`, `accountId` hoặc option cụ thể phải được kiểm tra lại sau khi tham số được phân tích và trước thao tác nghiệp vụ.

## 11. Viết provider hiệu quả và dễ kiểm thử

Một `AvailabilityProvider` có thể được gọi nhiều lần khi shell cần xác định command có khả dụng hay không. Vì vậy, provider nên:

- Chỉ đọc trạng thái, không cập nhật database, không gửi request làm thay đổi hệ thống và không mở phiên kết nối.
- Trả kết quả nhanh; tránh truy vấn nhiều hệ thống hoặc thao tác mạng dài trên mỗi lần kiểm tra.
- Trả lý do cụ thể, ngắn gọn và có hướng khắc phục.
- Không tiết lộ thông tin bí mật hoặc chi tiết nội bộ.
- Đọc cùng nguồn trạng thái mà service dùng để thực thi, tránh hai bản trạng thái độc lập dễ lệch nhau.
- Xử lý trạng thái chưa xác định một cách thận trọng. Nếu không thể xác nhận điều kiện an toàn, nên trả unavailable với lý do phù hợp thay vì mặc định available.

Không nên cache availability lâu nếu trạng thái có thể đổi nhanh. Nếu bắt buộc cache để giảm tải, hãy xác định TTL, cách invalidation và vẫn kiểm tra lại trạng thái có thẩm quyền trong service trước mutation.

## 12. Kiểm thử availability và kiểm tra lại khi thực thi

Kiểm thử cần xác nhận cả trải nghiệm command lẫn tính an toàn của thao tác.

### Kiểm thử provider

Với cửa sổ phát hành:

- Khi cửa sổ mở, provider trả `Availability.available()`.
- Khi cửa sổ đóng, provider trả `Availability.unavailable(...)` với lý do có thể hiển thị trực tiếp.
- Provider không gọi phương thức ghi dữ liệu hoặc kích hoạt tác dụng phụ.

Ví dụ kiểm thử đơn vị:

~~~java
@Test
void shouldBeUnavailableWhenPublishingWindowIsClosed() {
    when(windowQuery.isOpenNow()).thenReturn(false);

    Availability availability = provider.get();

    assertThat(availability.isAvailable()).isFalse();
    assertThat(availability.reason())
            .contains("publishing window is closed");
    verify(windowQuery).isOpenNow();
}
~~~

### Kiểm thử trạng thái thay đổi giữa availability và invocation

Đây là ca kiểm thử quan trọng nhất:

1. Ban đầu cửa sổ phát hành đang mở; provider trả available.
2. Đóng cửa sổ phát hành trước khi gọi service.
3. Gọi `releaseService.publish(...)`.
4. Xác nhận service đọc trạng thái mới, ném lỗi phù hợp và không chuyển bản phát hành sang `PUBLISHING`.

### Kiểm thử hai tiến trình cùng thực hiện

Gửi hai yêu cầu publish đồng thời cho cùng một bản phát hành. Chỉ một yêu cầu được chuyển trạng thái thành công; yêu cầu còn lại nhận xung đột hoặc lỗi trạng thái. Kiểm tra database chỉ có một lần chuyển trạng thái hợp lệ và chỉ phát sinh một yêu cầu triển khai.

### Kiểm thử remote session hết hạn

Provider có thể trả available khi session còn mở ở phía client. Hãy mô phỏng session hết hạn trước lúc service gửi request và xác nhận service từ chối hoặc máy chủ trả lỗi xác thực; không ghi nhận kết quả tải tệp thành công.

## 13. Quy trình thiết kế command phụ thuộc trạng thái

Khi command chỉ chạy được trong một số trạng thái, hãy triển khai theo trình tự:

1. Xác định các trạng thái cho phép và trạng thái chặn thao tác.
2. Xác định nguồn trạng thái có thẩm quyền: database, session service hay hệ thống bên ngoài.
3. Viết `AvailabilityProvider` chỉ đọc trạng thái và tạo lý do dễ hiểu.
4. Gắn provider với command qua `@Command(availabilityProvider = "...")` hoặc `Command.Builder.availabilityProvider(...)`.
5. Trong service, đọc lại trạng thái ngay trước mutation hoặc request bên ngoài.
6. Dùng transaction, pessimistic lock, optimistic version hoặc conditional update để xử lý thay đổi đồng thời.
7. Kiểm tra quyền ở tầng nghiệp vụ; không dùng availability như cơ chế bảo mật.
8. Kiểm thử cả trạng thái available/unavailable, TOCTOU và hai yêu cầu đồng thời.

## Kết luận

Spring Shell 4.x dùng `Availability` và `AvailabilityProvider` để biểu thị command có thể thực thi hay không, đồng thời giải thích lý do khi command chưa khả dụng. Cơ chế này cải thiện trợ giúp và phản hồi cho người dùng. Trạng thái vẫn có thể thay đổi giữa lúc provider kiểm tra và lúc command thực hiện, nên service phải xác nhận lại điều kiện có thẩm quyền ngay trước thao tác quan trọng. Kết hợp kiểm tra lại với transaction, lock hoặc cập nhật có điều kiện sẽ ngăn thao tác dựa trên trạng thái cũ và giảm nguy cơ thực thi trùng hoặc cập nhật sai.

## Tài liệu tham khảo

- [Spring Shell 4.x – Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html)
- [Spring Shell 4.0.4 API – Availability](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/Availability.html)
- [Spring Shell 4.0.4 API – AvailabilityProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/AvailabilityProvider.html)
- [Spring Shell 4.0.4 API – `@Command`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell – v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
