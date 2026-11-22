# Trì hoãn truy cập dịch vụ ngoài và nạp bí mật tới giai đoạn phù hợp

Ứng dụng Spring Boot thường cần kết nối database, message broker, API bên ngoài hoặc dịch vụ quản lý bí mật. Những dependency này có thể chưa sẵn sàng khi Spring tạo ApplicationContext, có thể thay đổi trong lúc ứng dụng được checkpoint, hoặc có credential hết hạn trong thời gian tiến trình tạm dừng. Nếu truy cập chúng quá sớm, ứng dụng có thể khởi động chậm, thất bại khi tạo bean hoặc lưu một kết nối và secret đã cũ vào checkpoint.

Với CRaC, cần chọn đúng thời điểm cho từng hành động: tạo bean và kiểm tra cấu trúc ứng dụng khi khởi động; truy cập dịch vụ khi thật sự cần hoặc tại bước readiness được thiết kế rõ ràng; nạp credential ngay trước khi tạo kết nối phụ thuộc vào credential đó; đóng hoặc tạm dừng tài nguyên trước checkpoint; và làm mới thông tin cần thiết sau restore.

Trì hoãn truy cập không có nghĩa là che giấu lỗi vô thời hạn. Ứng dụng vẫn cần quyết định dependency nào bắt buộc để phục vụ request, dependency nào có thể khởi tạo khi dùng lần đầu và điều gì xảy ra nếu dịch vụ hoặc secret store chưa sẵn sàng.

## 1. Các giai đoạn vòng đời trong Spring Boot và CRaC

Spring Boot có nhiều giai đoạn khởi tạo. Một số callback chạy khi bean được tạo; một số chạy sau khi ApplicationContext đã refresh; một số chỉ chạy khi bean lazy được yêu cầu lần đầu.

~~~text
JVM khởi động
    |
    v
Đọc environment và system properties
    |
    v
SpringApplication tạo ApplicationContext
    |
    v
Tạo eager singleton và dependency
    |
    v
Constructor / @PostConstruct / init callback
    |
    v
ApplicationContext refresh
    |
    v
SmartLifecycle và các bước lifecycle liên quan
    |
    v
ApplicationRunner / CommandLineRunner
    |
    v
ApplicationReadyEvent và nhận traffic
    |
    v
Chuẩn bị checkpoint / CRaC beforeCheckpoint
    |
    v
Checkpoint image
    |
    v
Restore / CRaC afterRestore
    |
    v
Xác minh dependency và readiness
    |
    v
Tiếp tục nhận traffic
~~~

Các điểm cần phân biệt:

| Giai đoạn | Việc phù hợp | Việc cần cân nhắc |
|---|---|---|
| Constructor và field initialization | Lưu dependency, kiểm tra tham số cục bộ, tạo object không có side effect | Không nên gọi secret store hoặc remote API nếu không cần thiết |
| @PostConstruct / init callback | Kiểm tra invariant của bean, chuẩn bị trạng thái nội bộ | Tránh kết nối mạng hoặc tải secret có thể hết hạn nếu bean chưa cần dùng |
| ApplicationContext refresh | Hoàn tất cấu trúc container và khởi tạo bean eager | Dependency bắt buộc có thể được kiểm tra ở đây nếu chính sách yêu cầu fail-fast |
| ApplicationRunner / CommandLineRunner | Chạy bước chuẩn bị startup có chủ đích | Chạy trong startup thông thường; không nên coi đây là callback tự chạy lại sau CRaC restore |
| Lần sử dụng đầu tiên | Khởi tạo lazy dependency khi có nhu cầu thật | Cần readiness, timeout và xử lý lỗi để request đầu tiên không bị treo bất ngờ |
| CRaC afterRestore | Làm mới secret, kết nối và trạng thái phụ thuộc thời gian | Không giả định toàn bộ quy trình khởi động Spring được chạy lại |

Checkpoint/restore không giống việc tạo một JVM mới rồi chạy lại SpringApplication. Các object trong ApplicationContext có thể được khôi phục từ checkpoint; constructor, @PostConstruct và ApplicationRunner không tự động được gọi lại chỉ vì tiến trình được restore. Thành phần sở hữu tài nguyên cần tham gia lifecycle CRaC hoặc dùng cơ chế tích hợp CRaC được Spring Boot phiên bản đó hỗ trợ.

## 2. Vì sao nên trì hoãn truy cập dịch vụ ngoài?

Việc tạo một bean không nhất thiết phải mở kết nối mạng. Nếu constructor hoặc init callback gọi remote service, các vấn đề sau có thể xảy ra:

- Spring startup phụ thuộc vào thời điểm database, broker hoặc dịch vụ cấu hình sẵn sàng.
- Một dịch vụ không thiết yếu có thể làm cả ApplicationContext không khởi động được.
- Việc tạo checkpoint có thể lưu client hoặc connection đang mở mà không được chuẩn bị đúng.
- Kết nối được tạo trước checkpoint có thể timeout hoặc bị peer đóng trong thời gian tiến trình tạm dừng.
- DNS, endpoint, chứng thư hoặc quyền truy cập có thể thay đổi trước khi restore.
- Một secret được tải lúc khởi động có thể hết hạn hoặc bị xoay vòng trước khi ứng dụng tiếp tục hoạt động.

Một bean nên mô tả cách sử dụng dependency và cách tạo nó. Hành động truy cập mạng nên nằm ở một bước có chủ đích, chẳng hạn khi dependency thực sự được dùng, trong một startup preflight hoặc trong callback phục hồi sau restore.

### Phân biệt khởi tạo object với kết nối dịch vụ

Một client factory có thể được tạo mà chưa mở socket. Ngược lại, một số thư viện kết nối ngay trong constructor hoặc trong bước initialize. Hãy đọc hợp đồng của thư viện để biết chính xác thời điểm kết nối được tạo.

Ví dụ, một factory chỉ giữ cấu hình:

~~~java
public final class RemoteClientFactory {
    public RemoteClient create(SecretMaterial secret) {
        return RemoteClient.connect(secret);
    }
}
~~~

Việc tạo RemoteClientFactory có thể hoàn toàn cục bộ. Lệnh create mới là nơi lấy credential và tạo kết nối. Cách phân chia này giúp Spring khởi tạo cấu trúc bean mà chưa cần gọi dịch vụ ngoài.

## 3. Dùng ObjectProvider để lấy dependency khi cần

Spring cung cấp ObjectProvider để trì hoãn việc lấy một bean tới thời điểm ứng dụng gọi getObject(). Đây là cách rõ ràng để tránh yêu cầu một dependency lazy ngay trong constructor của một eager singleton.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public final class ReportService {
    private final ObjectProvider<RemoteReportClient> clients;

    public ReportService(ObjectProvider<RemoteReportClient> clients) {
        this.clients = clients;
    }

    public Report loadReport(String reportId) {
        RemoteReportClient client = clients.getObject();
        return client.fetch(reportId);
    }
}
~~~

Ở đây, ReportService có thể được tạo trong startup mà chưa yêu cầu RemoteReportClient. Khi loadReport được gọi, Spring mới resolve bean RemoteReportClient. Nếu bean đó thực hiện kết nối trong quá trình khởi tạo, kết nối sẽ được trì hoãn tới lần resolve này.

ObjectProvider cũng có các phương thức như getIfAvailable() hoặc getIfUnique() cho trường hợp dependency là tùy chọn. Không nên dùng các phương thức này để âm thầm bỏ qua dependency bắt buộc; nếu không có client mà nghiệp vụ không thể tiếp tục, hãy báo lỗi rõ ràng.

### ObjectProvider và @Lazy

@Lazy có thể trì hoãn việc tạo bean cho tới khi nó được yêu cầu. Tuy nhiên, có một điểm dễ bỏ sót: nếu một eager singleton cần bean lazy trong constructor, Spring vẫn phải cung cấp dependency để hoàn tất singleton. Khi đó bean lazy có thể được tạo ngay trong startup.

Có thể dùng @Lazy ở injection point để Spring tạo proxy trì hoãn việc resolve target:

~~~java
import org.springframework.context.annotation.Lazy;
@Service
public final class LazyReportService {
    private final RemoteReportClient client;

    public LazyReportService(@Lazy RemoteReportClient client) {
        this.client = client;
    }

    public Report load(String id) {
        return client.fetch(id);
    }
}
~~~

ObjectProvider thường thể hiện rõ hơn thời điểm dependency được lấy và cho phép kiểm soát việc có yêu cầu bean hay không. @Lazy phù hợp khi muốn dùng dependency qua proxy như một object thông thường. Cả hai cách đều chỉ trì hoãn khởi tạo bean; chúng không tự quản lý credential rotation, reconnect, timeout hoặc CRaC lifecycle.

Không nên bật lazy initialization toàn cục chỉ để né lỗi kết nối. Cách đó có thể chuyển lỗi startup thành lỗi ở request đầu tiên và khiến dependency bắt buộc chưa được kiểm tra khi ứng dụng báo ready. Nên áp dụng lazy có chọn lọc cho dependency thực sự có thể trì hoãn.

## 4. Chọn thời điểm truy cập dịch vụ theo mức độ bắt buộc

Không phải mọi dependency đều nên được khởi tạo ở cùng một thời điểm.

| Loại dependency | Thời điểm phù hợp | Chính sách khi không sẵn sàng |
|---|---|---|
| Database bắt buộc để xử lý mọi request | Startup preflight hoặc trước readiness; tạo lại kết nối sau restore | Không nhận traffic nghiệp vụ khi database chưa sẵn sàng |
| Payment gateway chỉ dùng ở một số chức năng | Khi chức năng thanh toán được gọi hoặc trong readiness riêng cho chức năng đó | Từ chối/giới hạn chức năng phụ thuộc, giữ phần còn lại hoạt động nếu nghiệp vụ cho phép |
| Dịch vụ báo cáo tùy chọn | Khi người dùng yêu cầu báo cáo hoặc theo job riêng | Trả trạng thái unavailable có kiểm soát, retry có giới hạn |
| Secret store | Khi cần lấy secret để tạo client hoặc làm mới credential | Không tạo client phụ thuộc nếu chưa có secret hợp lệ |
| Message broker consumer | Khi ứng dụng đã sẵn sàng nhận message và sau restore | Chưa resume consumer cho tới khi kết nối và subscription hợp lệ |

Với dependency bắt buộc, trì hoãn không có nghĩa là không kiểm tra. Ứng dụng có thể kiểm tra kết nối trong startup gate hoặc trước khi mở traffic. Với dependency tùy chọn, lazy initialization có thể giảm thời gian startup và tránh làm cả ứng dụng phụ thuộc vào một dịch vụ không thiết yếu.

Hãy phân biệt liveness và readiness. Liveness cho biết process còn hoạt động; readiness cho biết instance có thể nhận loại công việc mà nó được giao. Một process có thể sống nhưng chưa sẵn sàng vì chưa tải secret hoặc chưa kết nối được database.

## 5. Nạp bí mật đúng lúc

Secret thường bao gồm password database, API token, private key, certificate hoặc credential của broker. Secret có thể được cung cấp qua environment, file mount, workload identity, Vault/secret manager hoặc dịch vụ nội bộ.

Nạp secret quá sớm có thể:

- Làm startup phụ thuộc vào secret store ngay cả khi client chưa cần dùng.
- Giữ credential trong heap lâu hơn mức cần thiết.
- Đưa secret cũ vào checkpoint image.
- Dùng token đã hết hạn sau khi tiến trình được restore.
- Tiếp tục dùng password cũ sau khi secret đã được xoay vòng.

Nạp secret quá muộn mà không có readiness cũng có thể làm request đầu tiên thất bại hoặc chờ quá lâu. Vì vậy, thời điểm lấy secret nên gắn với thời điểm tạo hoặc làm mới client phụ thuộc vào nó.

### Phân biệt bootstrap identity và application secret

Để đọc secret từ secret manager, ứng dụng thường cần một cơ chế xác thực ban đầu, ví dụ workload identity, cloud role, service account hoặc credential do nền tảng cấp.

Hai loại thông tin này có vai trò khác nhau:

- **Bootstrap identity:** giúp ứng dụng chứng minh danh tính với secret manager.
- **Application secret:** credential mà ứng dụng lấy từ secret manager để kết nối database, broker hoặc API.

Không nên tạo vòng phụ thuộc: cần password database để kết nối secret manager, trong khi password database lại chỉ có thể lấy từ chính secret manager. Hãy dùng identity bootstrap do nền tảng cung cấp hoặc một cơ chế khởi tạo độc lập được bảo vệ phù hợp.

Sau restore, bootstrap identity cũng có thể hết hạn hoặc cần refresh. SecretProvider cần xác minh danh tính hiện tại trước khi đọc application secret.

### Không giữ secret lâu hơn mức cần thiết

Nên hạn chế số nơi lưu bản sao secret:

- Tránh log secret hoặc toàn bộ cấu hình có chứa secret.
- Tránh lưu secret vào static field hoặc singleton không có nhu cầu rõ ràng.
- Không đưa secret vào exception message.
- Dùng kiểu dữ liệu và API của secret provider để hạn chế bản sao không cần thiết.
- Đóng hoặc xóa buffer mutable theo hợp đồng của thư viện khi đã sử dụng xong.

Java String là bất biến và không thể chủ động ghi đè nội dung của nó. Việc chuyển secret thành String có thể làm tăng số bản sao và thời gian tồn tại trong heap. Nếu thư viện hỗ trợ, cân nhắc char[] hoặc kiểu secret có vòng đời rõ ràng. Tuy nhiên, xóa một buffer không bảo đảm mọi bản sao đã được tạo ở bên trong thư viện cũng bị xóa.

Checkpoint image có thể chứa secret đã được đọc vào heap. Hãy bảo vệ quyền truy cập, lưu trữ và phân phối checkpoint image như một artifact có thể chứa thông tin xác thực.

## 6. Thiết kế SecretProvider và client factory

Tách việc lấy secret khỏi việc sử dụng client giúp ứng dụng có thể refresh credential và tạo lại kết nối khi cần.

~~~java
public interface SecretProvider {
    SecretMaterial load() throws Exception;
}

public interface SecretMaterial extends AutoCloseable {
    char[] credential();

    @Override
    void close();
}

public interface RemoteClient extends AutoCloseable {
    void send(String payload) throws Exception;

    @Override
    void close() throws Exception;
}

public interface RemoteClientFactory {
    RemoteClient connect(SecretMaterial secret) throws Exception;
}
~~~

SecretProvider chịu trách nhiệm xác thực với secret store và trả về secret còn hiệu lực. RemoteClientFactory nhận secret để tạo client. Các interface này là hợp đồng do ứng dụng định nghĩa; implementation thực tế phụ thuộc nền tảng và thư viện.

Một điểm quan trọng là factory nên tạo client sau khi nhận secret hợp lệ. Không nên đọc secret trong constructor của một bean chỉ vì Spring đang tạo bean đó.

## 7. Ví dụ: Resource trì hoãn kết nối và nạp lại secret sau restore

Ví dụ sau dùng ObjectProvider để chỉ lấy SecretProvider và RemoteClientFactory khi thật sự cần mở client. Resource được đăng ký sớm với CRaC, nhưng việc kết nối và nạp application secret được trì hoãn.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.beans.factory.ObjectProvider;

public final class RemoteClientManager implements Resource {
    private final ObjectProvider<SecretProvider> secretProviders;
    private final ObjectProvider<RemoteClientFactory> factories;

    private RemoteClient client;
    private boolean reopenAfterRestore;

    public RemoteClientManager(
            ObjectProvider<SecretProvider> secretProviders,
            ObjectProvider<RemoteClientFactory> factories) {
        this.secretProviders = secretProviders;
        this.factories = factories;

        // Đăng ký manager; chưa tải secret và chưa mở kết nối.
        Core.getGlobalContext().register(this);
    }

    public synchronized void send(String payload) throws Exception {
        RemoteClient active = client;
        if (active == null) {
            active = openClient();
        }
        active.send(payload);
    }

    private RemoteClient openClient() throws Exception {
        SecretProvider provider = secretProviders.getObject();
        RemoteClientFactory factory = factories.getObject();

        try (SecretMaterial secret = provider.load()) {
            RemoteClient created = factory.connect(secret);
            client = created;
            return created;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        reopenAfterRestore = client != null;

        if (client != null) {
            client.close();
            client = null;
        }
    }

    // Được checkpoint coordinator gọi nếu lần chuẩn bị checkpoint bị hủy
    // và tiến trình hiện tại tiếp tục chạy thay vì được restore.
    public synchronized void resumeAfterCheckpointFailure()
            throws Exception {
        if (reopenAfterRestore && client == null) {
            openClient();
            reopenAfterRestore = false;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        if (reopenAfterRestore) {
            openClient();
            reopenAfterRestore = false;
        }
    }
}
~~~

Trong ví dụ:

- RemoteClientManager được tạo và đăng ký với global context nhưng chưa truy cập secret store.
- ObjectProvider trì hoãn việc lấy SecretProvider và RemoteClientFactory.
- Lần đầu gọi send mới lấy secret và tạo client.
- beforeCheckpoint đóng client nếu nó đã được sử dụng.
- afterRestore tạo client mới bằng secret được tải lại từ provider, thay vì dựa vào credential cũ.
- Nếu client chưa từng được mở trước checkpoint, manager không cần tạo kết nối chỉ để checkpoint; lần sử dụng đầu tiên sau restore sẽ mở client.

Ví dụ giả định factory tiêu thụ hoặc sao chép credential cần thiết trong lúc connect và không giữ tham chiếu tới SecretMaterial đã đóng. Implementation thực tế phải tuân theo hợp đồng của SDK; nếu client cần secret lâu dài, hãy dùng API credential provider/refresh của SDK hoặc một cơ chế quản lý credential có vòng đời rõ ràng.

Đoạn mã cũng giả định ứng dụng đã ngừng admission và drain các lời gọi send trước khi beforeCheckpoint đóng client. synchronized chỉ bảo vệ các lời gọi đi qua cùng manager; nó không dừng thread khác đang giữ trực tiếp một tham chiếu tới client hoặc gọi adapter ngoài manager.

Nếu quá trình chuẩn bị checkpoint bị hủy sau khi beforeCheckpoint đã đóng client, tiến trình ban đầu có thể tiếp tục chạy mà không có afterRestore. Bộ điều phối checkpoint cần gọi một đường phục hồi như resumeAfterCheckpointFailure(), xác minh client đã hoạt động rồi mới mở lại admission. Nếu việc mở lại thất bại, giữ ứng dụng ở trạng thái chưa sẵn sàng.

### Đăng ký manager trong Spring Boot

Có thể tạo manager như một bean eager để nó đăng ký Resource từ startup, trong khi các dependency thực sự truy cập mạng vẫn được trì hoãn:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RemoteClientConfiguration {
    @Bean
    RemoteClientManager remoteClientManager(
            ObjectProvider<SecretProvider> secretProviders,
            ObjectProvider<RemoteClientFactory> factories) {
        return new RemoteClientManager(secretProviders, factories);
    }
}
~~~

Manager được tạo trong quá trình khởi tạo ApplicationContext và đăng ký với CRaC. SecretProvider và RemoteClientFactory chỉ được resolve khi openClient gọi getObject(). Hãy bảo đảm chính các bean đó không bị một thành phần eager khác yêu cầu trước thời điểm mong muốn.

Nếu manager cũng được đánh dấu @Lazy, nó có thể chưa được tạo và chưa đăng ký Resource trước checkpoint. Chỉ dùng cách đó nếu có cơ chế bảo đảm manager được khởi tạo trước khi CRaC bắt đầu checkpoint.

Trong một ứng dụng dùng Spring Boot CRaC integration, hãy kiểm tra tài liệu của đúng phiên bản Spring Boot để biết các Resource được phát hiện, đăng ký và điều phối thế nào. Tránh đăng ký hai lần hoặc tự đóng một client mà framework/thư viện đã quản lý lifecycle.

## 8. Nên tải secret ở startup, lần dùng đầu hay afterRestore?

Không có một thời điểm duy nhất phù hợp cho mọi secret. Chọn theo vòng đời của dependency:

| Trường hợp | Thời điểm lấy secret | Lý do |
|---|---|---|
| Credential bắt buộc để mọi request hoạt động | Startup gate hoặc trước readiness; làm mới sau restore | Xác nhận instance không ready nếu không thể truy cập dependency bắt buộc |
| Credential cho chức năng ít dùng | Lần đầu chức năng được gọi, có cache/TTL phù hợp | Không trì hoãn startup vì dependency tùy chọn |
| Token ngắn hạn | Ngay trước khi tạo client hoặc trước khi token hết hạn | Giảm nguy cơ checkpoint giữ token đã hết hạn |
| Credential có rotation | Qua provider có thể refresh; kiểm tra version/expiry sau restore | Không tiếp tục dùng secret cũ sau khi nguồn đã xoay vòng |
| Secret chỉ dùng để tạo client lâu dài | Khi tạo hoặc làm mới client | Giới hạn thời gian secret tồn tại trong ứng dụng |
| Secret dùng cho nhiều client | Qua provider/cache có TTL và chính sách invalidation | Tránh nhiều lần truy cập secret store không cần thiết nhưng vẫn xử lý rotation |

Nếu một dependency là bắt buộc để ứng dụng phục vụ traffic, có thể tải secret và tạo client trước readiness. Việc này vẫn là truy cập ngoài có chủ đích, với timeout và fail-fast rõ ràng. Nếu dependency tùy chọn, lazy access có thể phù hợp hơn.

Không nên lấy secret mới trong mọi request nếu secret store có độ trễ hoặc giới hạn rate. Dùng cache có TTL, version hoặc refresh-ahead khi phù hợp; bảo đảm cache không vượt quá thời hạn credential và có thể được invalidated sau restore.

## 9. Startup runner, ApplicationReadyEvent và SmartLifecycle

Spring Boot cung cấp nhiều hook lifecycle, nhưng chúng có mục đích khác nhau:

- Constructor và @PostConstruct phù hợp cho khởi tạo cục bộ, kiểm tra tham số và invariant.
- ApplicationRunner và CommandLineRunner phù hợp cho bước chuẩn bị startup có chủ đích sau khi ApplicationContext được tạo.
- ApplicationReadyEvent cho biết startup thông thường đã hoàn tất và ứng dụng sắp nhận traffic.
- SmartLifecycle quản lý thành phần có start/stop theo lifecycle của ApplicationContext.
- CRaC Resource hoặc integration tương ứng quản lý hành động trước checkpoint và sau restore.

Không nên dùng ApplicationReadyEvent như một callback thay thế afterRestore. Restore một checkpoint không đồng nghĩa chạy lại SpringApplication và phát lại toàn bộ sự kiện startup. Nếu cần tải lại secret hoặc mở lại client sau restore, hãy nối hành động đó với CRaC lifecycle.

SmartLifecycle có thể hữu ích để start/stop consumer hoặc listener trong vòng đời ApplicationContext. Tuy nhiên, việc một bean triển khai SmartLifecycle không tự chứng minh nó sẽ nhận callback sau restore. Nếu dùng cùng CRaC, cần có integration hoặc Resource điều phối rõ ràng.

## 10. Readiness, timeout và xử lý lỗi

Trì hoãn dependency làm thay đổi thời điểm lỗi xuất hiện. Nếu không thiết kế readiness, ứng dụng có thể báo ready trong khi client chưa được tạo và request đầu tiên mới phát hiện secret store hoặc remote service không hoạt động.

Hãy phân loại dependency:

- **Bắt buộc:** nếu không có dependency này thì request nghiệp vụ không thể thành công. Chỉ mở readiness sau khi kết nối và credential đã được xác minh.
- **Tùy chọn:** chức năng phụ thuộc có thể trả lỗi có kiểm soát hoặc bị vô hiệu hóa, trong khi phần còn lại vẫn phục vụ.
- **Có thể phục hồi:** retry có backoff và giới hạn thời gian, đồng thời giữ trạng thái chưa sẵn sàng cho chức năng tương ứng.

Mỗi lần truy cập ngoài cần timeout kết nối và timeout thao tác. Không để một callback afterRestore chờ vô hạn khi secret store hoặc dịch vụ từ xa không phản hồi. Retry nên có giới hạn, backoff và jitter để tránh nhiều instance cùng tạo tải đột biến sau restore.

Nếu nạp secret thất bại:

1. Không tạo client với credential rỗng hoặc credential cũ đã hết hiệu lực.
2. Giữ dependency ở trạng thái unavailable.
3. Báo lỗi có ngữ cảnh nhưng không chứa giá trị secret.
4. Không mở readiness cho chức năng phụ thuộc.
5. Cho phép retry theo chính sách vận hành.

Nếu client đã tạo nhưng bước xác thực hoặc handshake thất bại, đóng client dở dang và giải phóng tài nguyên. Không công bố client một phần cho các thread khác.

## 11. Thứ tự phục hồi các dependency

Một client có thể phụ thuộc vào secret provider, DNS, TLS trust material, connection pool hoặc một cấu hình động. Sau restore, cần khôi phục theo thứ tự phụ thuộc:

~~~text
Restore tiến trình
       |
       v
Khôi phục bootstrap identity
       |
       v
Kết nối secret/config provider
       |
       v
Nạp và xác minh secret hiện tại
       |
       v
Tạo lại remote client / connection pool
       |
       v
Health check và readiness
       |
       v
Resume consumer / nhận traffic
~~~

Không nên dựa vào thứ tự callback giữa nhiều Resource độc lập nếu CRaC runtime hoặc framework không bảo đảm thứ tự đó. Khi có phụ thuộc, dùng một Resource điều phối có chủ sở hữu rõ ràng hoặc cơ chế lifecycle có thứ tự. Nếu thư viện đã có CRaC integration, ưu tiên hướng dẫn của thư viện và tránh callback trùng lặp.

Trước checkpoint, thứ tự dừng thường đi ngược với thứ tự khởi động: ngừng traffic và consumer, drain request, đóng client, rồi đóng nguồn cấu hình/secret client nếu chúng cần đóng. Không đóng secret provider trước khi client phụ thuộc đã hoàn tất bước chuẩn bị cần thiết.

## 12. Cấu hình Spring Boot và secret trong environment

Spring Boot có thể bind environment variable hoặc system property vào @ConfigurationProperties khi ApplicationContext khởi tạo. Object cấu hình đã bind có thể tồn tại trong heap sau checkpoint.

Ví dụ:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "remote.service")
public record RemoteServiceProperties(
        String endpoint,
        String username,
        String password) {}
~~~

Đây là cấu hình snapshot tại thời điểm binding. Nếu secret hoặc endpoint thay đổi bên ngoài trong thời gian tiến trình tạm dừng, object properties đã bind không tự cập nhật. Nếu cần rotation, nên dùng SecretProvider hoặc cơ chế refresh chính thức có version và lifecycle rõ ràng.

Không nên coi việc cập nhật environment của container là cách refresh environment trong process đã chạy hoặc đã được restore. Environment thường được cung cấp khi process khởi chạy. Nếu cần credential mới, đọc từ secret provider hoặc tạo process mới theo chính sách triển khai.

Nếu dùng @ConfigurationProperties để bind secret, hãy bảo đảm object không bị log bởi toString(), actuator endpoint hoặc diagnostic dump. Với record, toString() mặc định có thể in các field; tránh dùng record chứa secret nếu kết quả có thể bị ghi log. Có thể tách secret khỏi properties thông thường hoặc tùy biến cách biểu diễn để che giá trị nhạy cảm.

## 13. Những hiểu nhầm thường gặp

**“Đánh dấu bean @Lazy là mọi truy cập mạng đều được trì hoãn.”**

Không chắc chắn. Bean có thể được yêu cầu bởi một eager singleton hoặc một bước startup khác. @Lazy trì hoãn việc tạo bean cho tới khi được resolve; nó không tự quản lý mọi side effect bên trong bean. Dùng ObjectProvider nếu muốn kiểm soát rõ thời điểm resolve.

**“Constructor hoặc @PostConstruct là nơi tốt để kết nối mọi dịch vụ.”**

Không phải lúc nào cũng vậy. Những callback này chạy trong quá trình tạo bean và có thể khiến toàn bộ ApplicationContext phụ thuộc vào dịch vụ ngoài. Chỉ làm ở đây khi đó là điều kiện startup bắt buộc và có timeout/fail-fast rõ ràng.

**“ApplicationRunner sẽ chạy lại sau restore.”**

Không. Runner thuộc startup thông thường của Spring Boot. Restore không tự khởi tạo lại ApplicationContext. Dùng CRaC Resource hoặc integration phù hợp để phục hồi tài nguyên.

**“Secret đã bind vào ConfigurationProperties sẽ tự cập nhật khi secret store rotation.”**

Không tự động. Bean đã bind là snapshot trong heap. Cần provider/refresh mechanism và cập nhật client phụ thuộc.

**“Có thể dùng secret cũ nếu client object vẫn còn.”**

Không bảo đảm. Token có thể hết hạn, password có thể bị xoay vòng hoặc quyền có thể bị thu hồi. Sau restore, xác minh credential và tạo lại client khi cần.

**“Rollback hoặc đóng client sẽ xóa mọi side effect.”**

Không đúng. Gửi email, publish message hoặc ghi dữ liệu bên ngoài có thể đã hoàn tất. Không gọi adapter gây side effect trong warmup hoặc lifecycle preparation nếu không có chính sách rõ ràng.

**“Chỉ cần reconnect sau restore là đủ.”**

Kết nối mới vẫn có thể cần secret mới, cấu hình mới, TLS handshake, subscription hoặc quyền sở hữu lease. Phục hồi cần xét toàn bộ dependency chain.

## 14. Kiểm thử việc trì hoãn và nạp lại secret

Nên kiểm thử trên đúng Spring Boot version, JDK/CRaC runtime, secret provider và thư viện client đang dùng:

- Khởi động ApplicationContext và xác nhận bean manager được tạo mà chưa gọi secret store.
- Gọi chức năng lần đầu và xác nhận secret chỉ được nạp tại thời điểm dự kiến.
- Làm secret store chậm hoặc không sẵn sàng để kiểm tra timeout và trạng thái readiness.
- Thay đổi credential trong lúc tiến trình đã checkpoint rồi restore; xác nhận client mới dùng secret hiện tại.
- Làm credential cũ hết hạn hoặc bị thu hồi và xác nhận không tiếp tục dùng client cũ.
- Làm remote service không sẵn sàng trong afterRestore và xác nhận ứng dụng không mở traffic quá sớm.
- Kiểm tra callback close/reopen không chạy trùng và không rò rỉ connection.
- Kiểm tra dependency tùy chọn không làm hỏng những chức năng độc lập.
- Kiểm tra log, exception, actuator và checkpoint artifact không để lộ secret ngoài phạm vi cho phép.
- Thực hiện nhiều chu kỳ checkpoint/restore để phát hiện manager chưa đăng ký, client cũ còn sống hoặc secret cache không được refresh.

Đừng chỉ kiểm tra rằng ApplicationContext khởi động thành công. Cần xác nhận cả thời điểm gọi secret provider, thời điểm mở connection, hành vi khi restore và trạng thái readiness trước khi nhận request.

## 15. Kết luận

Trong Spring Boot, constructor, @PostConstruct, ApplicationRunner, ApplicationReadyEvent, SmartLifecycle và CRaC Resource phục vụ những giai đoạn khác nhau. Không nên đặt mọi truy cập dịch vụ ngoài và việc nạp secret vào thời điểm tạo bean. Hãy trì hoãn việc resolve dependency bằng ObjectProvider hoặc cơ chế lazy có kiểm soát, rồi nạp credential ngay trước khi tạo hoặc làm mới client.

Với CRaC, cần nhớ ApplicationContext được khôi phục cùng trạng thái tiến trình; các hook startup thông thường không tự chạy lại. Thành phần sở hữu remote client nên đóng trước checkpoint và làm mới secret, tạo kết nối sau restore theo đúng dependency order. Readiness chỉ được mở khi credential và các dịch vụ bắt buộc đã được xác minh, còn checkpoint image và log phải được bảo vệ như nơi có thể chứa thông tin nhạy cảm.
