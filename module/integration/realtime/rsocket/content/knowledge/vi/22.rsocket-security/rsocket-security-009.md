# Truyền danh tính khi nhiều người dùng chung một kết nối dịch vụ

Trong kiến trúc microservice, một ứng dụng web hoặc API gateway có thể mở một kết nối RSocket duy nhất tới dịch vụ phía sau rồi dùng kết nối đó để phục vụ nhiều người dùng cuối. Kết nối được chia sẻ giúp giảm số socket và chi phí thiết lập phiên, nhưng tạo ra một yêu cầu bảo mật quan trọng: server phải biết request hiện tại được thực hiện thay mặt cho người dùng nào.

Không thể đặt danh tính của một người dùng vào frame SETUP rồi dùng danh tính đó cho mọi request nếu nhiều người cùng chia sẻ kết nối. SETUP thuộc phạm vi kết nối; danh tính người dùng phải được gửi và xác thực theo từng request. RSocket cho phép đưa token vào metadata của từng tương tác, và Spring Security có thể xác thực token đó để tạo Authentication riêng cho request.

Bài này xây dựng mô hình hai lớp: xác thực dịch vụ ở thời điểm mở kết nối nếu cần, sau đó truyền access token của từng người dùng trong metadata của mỗi request. Server dùng principal đã xác thực để áp dụng quyền và truy cập đúng dữ liệu của người dùng.

## 1. Bài toán nhiều người dùng trên một kết nối

Giả sử một web application nhận request từ Alice và Bob. Thay vì mỗi người dùng mở một kết nối RSocket riêng tới Order Service, web application duy trì một RSocketRequester dùng chung. Các request từ Alice và Bob được multiplex qua cùng một phiên.

~~~mermaid
flowchart TD
    A[Alice] --> GW[Web application / API gateway]
    B[Bob] --> GW
    GW -->|Một kết nối RSocket dùng chung| RS[Order Service]
    RS --> AUTH[Spring Security xác thực từng request]
    AUTH --> SVC[Business service]
    SVC --> DA[Phạm vi dữ liệu Alice]
    SVC --> DB[Phạm vi dữ liệu Bob]
~~~

Nếu gateway gửi access token của Alice trong SETUP, kết nối sẽ mang danh tính Alice ở cấp phiên. Khi Bob gửi request qua cùng requester, server có thể tiếp tục nhìn thấy Alice là danh tính của kết nối. Đây là lỗi thiết kế có thể dẫn tới truy cập chéo dữ liệu.

Trong mô hình chia sẻ kết nối:

- Danh tính của ứng dụng/gateway có thể được xác thực một lần ở SETUP để giới hạn ai được phép mở phiên.
- Danh tính người dùng cuối được gửi trong metadata của từng request.
- Server xác thực token của request và dùng Authentication tương ứng khi kiểm tra quyền.
- Không lưu một userId hoặc Principal duy nhất trong trạng thái kết nối rồi dùng lại cho mọi người dùng.

## 2. Phân biệt SETUP metadata và request metadata

RSocket có metadata ở hai phạm vi cần phân biệt:

| Vị trí metadata | Phạm vi | Dùng cho |
|---|---|---|
| SETUP metadata | Toàn bộ kết nối | Danh tính dịch vụ gọi, quyền mở phiên, thông tin client hoặc cấu hình kết nối |
| Request metadata | Một tương tác/stream | Danh tính người dùng đang thực hiện request, route và dữ liệu bảo mật gắn với request |

SETUP được gửi khi thiết lập một phiên RSocket mới. Metadata trong frame này phù hợp với danh tính của thành phần sở hữu kết nối, chẳng hạn gateway hoặc service account.

Request metadata được gửi cùng frame khởi tạo từng tương tác như REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_CHANNEL hoặc REQUEST_FNF. Một request có thể mang token của Alice, request tiếp theo trên cùng kết nối mang token của Bob. Hai request vẫn được xác thực độc lập.

Với Spring, request metadata thường được mã hóa dưới dạng composite metadata để chứa nhiều entry, chẳng hạn route và thông tin xác thực. MIME type xác thực được dùng cho token phải khớp với extension mà Spring Security đang cấu hình.

## 3. Luồng xử lý danh tính theo từng request

~~~mermaid
sequenceDiagram
    participant U1 as Alice
    participant U2 as Bob
    participant G as Gateway
    participant S as RSocket service
    U1->>G: HTTP request với access token Alice
    U2->>G: HTTP request với access token Bob
    Note over G,S: Gateway duy trì một RSocket connection
    G->>S: SETUP metadata: service token (nếu cần)
    G->>S: REQUEST profile.me + auth metadata Alice
    S->>S: Xác thực token Alice
    S-->>G: Response thuộc Alice
    G->>S: REQUEST profile.me + auth metadata Bob
    S->>S: Xác thực token Bob
    S-->>G: Response thuộc Bob
~~~

Gateway lấy access token từ ngữ cảnh xác thực của từng request HTTP, rồi gắn token đó vào metadata của đúng tương tác RSocket. Token không được giữ trong một biến mutable dùng chung cho toàn bộ requester.

Server kiểm tra chữ ký, issuer, audience, thời hạn và quyền của token. Khi request được xử lý, handler sử dụng principal đã xác thực để xác định dữ liệu cần truy cập. Giá trị userId trong payload có thể là tham số nghiệp vụ, nhưng không được dùng thay cho danh tính đã xác thực.

## 4. Cấu hình Spring Security cho RSocket

Spring Security hỗ trợ xác thực JWT trong RSocket thông qua Bearer Token Authentication Metadata Extension. Khi bật jwt trong RSocketSecurity, Spring cấu hình converter để đọc bearer token từ metadata và dùng ReactiveJwtDecoder xác thực token.

Ví dụ cấu hình server:

Các dependency cần có gồm RSocket server, Spring Security và OAuth 2.0 Resource Server để xác thực JWT:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket
    ) {
        rsocket
            .authorizePayload(authorize -> authorize
                .setup().hasAuthority("SCOPE_rsocket.connect")
                .route("profile.me").hasAuthority("SCOPE_profile.read")
                .anyRequest().authenticated()
                .anyExchange().permitAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
            "https://identity.example.com"
        );
    }
}
~~~

Trong ví dụ:

- Token dịch vụ gửi ở SETUP cần có authority SCOPE_rsocket.connect để được phép mở phiên.
- Token người dùng gửi trong request tới profile.me cần có authority SCOPE_profile.read.
- Các request khác yêu cầu người gọi đã được xác thực.
- ReactiveJwtDecoder lấy cấu hình khóa và issuer từ Identity Provider; URL ví dụ cần được thay bằng issuer thực tế.

Các authority SCOPE_... được Spring ánh xạ mặc định từ claim scope hoặc scp trong JWT. Nếu hệ thống dùng claim hoặc quy tắc authority tùy chỉnh, cần cấu hình converter tương ứng. Phải kiểm tra dependency và API của phiên bản Spring Security trong dự án vì cách tổ chức DSL có thể thay đổi giữa các phiên bản.

Với Spring Boot có cấu hình RSocket Security auto-configuration, interceptor bảo mật được tích hợp vào RSocket server khi các dependency phù hợp có mặt. Nếu tự tạo RSocket server ngoài auto-configuration, cần đăng ký SecuritySocketAcceptorInterceptor vào SocketAcceptor của server.

## 5. Gửi token của từng người dùng trong request metadata

Client cần dùng MIME type xác thực của RSocket Bearer Token Authentication. Trong Spring Security, giá trị MIME type được lấy từ WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.

~~~java
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import io.rsocket.metadata.WellKnownMimeType;

public final class RSocketAuthMetadata {

    private RSocketAuthMetadata() {
    }

    public static final MimeType AUTHENTICATION_MIME_TYPE =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
        );
}
~~~

Các đoạn code tiếp theo giả định hằng số AUTHENTICATION_MIME_TYPE đã được import tĩnh từ lớp RSocketAuthMetadata.

Giả sử sharedRequester là một RSocketRequester được tạo một lần và tái sử dụng cho các request tới dịch vụ. Mỗi lời gọi nhận token của người dùng hiện tại:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public class ProfileClient {

    private final RSocketRequester sharedRequester;

    public ProfileClient(RSocketRequester sharedRequester) {
        this.sharedRequester = sharedRequester;
    }

    public Mono<ProfileDto> findMyProfile(String userAccessToken) {
        return sharedRequester
            .route("profile.me")
            .metadata(userAccessToken, AUTHENTICATION_MIME_TYPE)
            .retrieveMono(ProfileDto.class);
    }
}
~~~

Điểm quan trọng là metadata được gắn trên RequestSpec của từng lần gọi. RSocketRequester dùng chung không bị đổi danh tính khi Alice hoặc Bob gửi request. Hãy lấy userAccessToken từ security context của request hiện tại, sau khi gateway đã xác thực người dùng.

Nếu dùng Spring Framework phiên bản mới, builder có thể cung cấp requester qua tcp(...) hoặc webSocket(...). Ở các phiên bản cũ hơn, API kết nối có thể là connectTcp(...) hoặc connectWebSocket(...) và trả về Mono<RSocketRequester>. Khác biệt đó không làm thay đổi nguyên tắc: token người dùng phải được đặt bằng metadata(...) trên từng request.

## 6. Xác thực danh tính dịch vụ ở SETUP và người dùng ở từng request

Một hệ thống có thể cần kiểm tra cả hai danh tính:

1. Dịch vụ gateway có được phép mở kết nối tới RSocket server hay không?
2. Người dùng cuối nào đang yêu cầu thao tác cụ thể và họ có quyền gì?

Khi đó, gateway có thể gửi service token trong SETUP:

~~~java
RSocketRequester sharedRequester = RSocketRequester.builder()
    .setupMetadata(
        serviceAccessToken,
        AUTHENTICATION_MIME_TYPE
    )
    .tcp("rsocket.internal", 7000);
~~~

Sau đó từng request vẫn mang token người dùng:

~~~java
Mono<ProfileDto> aliceProfile =
    sharedRequester.route("profile.me")
        .metadata(aliceAccessToken, AUTHENTICATION_MIME_TYPE)
        .retrieveMono(ProfileDto.class);

Mono<ProfileDto> bobProfile =
    sharedRequester.route("profile.me")
        .metadata(bobAccessToken, AUTHENTICATION_MIME_TYPE)
        .retrieveMono(ProfileDto.class);
~~~

Service token và user token có mục đích khác nhau. Service token chỉ chứng minh thành phần gateway được phép mở phiên. Nó không thay thế user token và không được dùng làm danh tính của Alice hoặc Bob khi truy cập dữ liệu người dùng.

Nếu kiến trúc không cần xác thực riêng ứng dụng mở kết nối, có thể bỏ setupMetadata(...) và chỉ yêu cầu xác thực ở từng request. Ngược lại, nếu kết nối chỉ phục vụ một người dùng duy nhất và không được chia sẻ, xác thực ở SETUP có thể phù hợp. Chọn phạm vi xác thực theo mô hình sở hữu kết nối thực tế.

## 7. Lấy danh tính đã xác thực trong handler

Sau khi Spring Security xác thực request metadata, handler nên dựa vào principal đã được xác thực để xác định người dùng. Ví dụ:

~~~java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ProfileController {

    private final ProfileService profileService;

    public ProfileController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @MessageMapping("profile.me")
    public Mono<ProfileDto> currentUser(Principal principal) {
        return profileService.findBySubject(principal.getName());
    }
}
~~~

Principal ở đây là danh tính gắn với request đã được Spring Security xác thực. Handler không nhận userId do client tự khai báo rồi tin tưởng giá trị đó. Nếu API cần truy cập hồ sơ của người khác, phải có route và quy tắc authorization rõ ràng, chẳng hạn kiểm tra scope hoặc quan hệ quản trị.

Đối với hệ thống đa tenant, tenant cần được lấy từ claim đã được xác thực hoặc được kiểm tra bằng một chính sách server-side. Không cho phép client đổi tenant chỉ bằng cách gửi một trường tenantId trong payload.

## 8. Không để danh tính người dùng rò rỉ giữa các request

Một lỗi thường gặp là lưu người dùng hiện tại vào field của bean hoặc session object gắn với kết nối:

~~~java
// Không nên: một requester dùng chung nhưng userId bị ghi đè giữa các request.
class SharedConnectionState {
    private String currentUserId;
}
~~~

Khi Alice và Bob gửi request đồng thời, một request có thể ghi đè currentUserId trong lúc request kia đang xử lý. Kết quả là dữ liệu của người dùng này có thể được xử lý dưới danh tính người dùng khác.

Các nguyên tắc an toàn:

- Không lưu userId, Authentication hoặc access token hiện tại vào field mutable dùng chung của requester, controller singleton hoặc connection registry.
- Không gắn user token riêng vào SETUP metadata của một kết nối phục vụ nhiều người.
- Gửi token trong metadata của từng request và để Spring Security tạo SecurityContext theo tương tác.
- Dùng Principal/Authentication trong pipeline xử lý request thay vì ThreadLocal tự quản lý.
- Nếu phải truyền ngữ cảnh qua tác vụ bất đồng bộ, dùng cơ chế Reactor Context/Spring Security hỗ trợ thay vì sao chép danh tính vào biến toàn cục.
- Tách dữ liệu theo subject và tenant đã được xác thực ở tầng service/repository.

RSocket multiplex nhiều stream trên một kết nối. Các request có thể chạy xen kẽ hoặc đồng thời, vì vậy mọi trạng thái gắn với người dùng phải thuộc phạm vi request hoặc reactive context tương ứng.

## 9. Xử lý token hết hạn và thay đổi danh tính

Token có thể hết hạn trong khi kết nối RSocket vẫn còn hoạt động. Điều này không nhất thiết yêu cầu đóng kết nối hoặc tạo requester mới. Request tiếp theo có thể gửi token mới trong metadata:

~~~java
Mono<ProfileDto> refreshAndFindProfile(
    String refreshedUserAccessToken
) {
    return sharedRequester
        .route("profile.me")
        .metadata(
            refreshedUserAccessToken,
            AUTHENTICATION_MIME_TYPE
        )
        .retrieveMono(ProfileDto.class);
}
~~~

Nếu token hết hạn hoặc không hợp lệ, server từ chối request tương ứng. Gateway có thể yêu cầu refresh token hoặc thực hiện token exchange theo chính sách của Identity Provider rồi gửi request tiếp theo bằng token mới.

Không nên tự động retry một request bị 401/unauthorized bằng cùng token đã hết hạn. Cần phân biệt lỗi xác thực, lỗi phân quyền, lỗi mạng và lỗi nghiệp vụ. Khi người dùng đăng xuất hoặc phiên bị thu hồi, gateway phải ngừng gửi request thay mặt người đó và xóa token khỏi ngữ cảnh người dùng.

Nếu gateway truyền token người dùng sang dịch vụ phía sau, token phải có audience phù hợp với dịch vụ nhận. Không chuyển tiếp một access token chỉ dành cho API khác. Trong một số hệ thống, token exchange hoặc on-behalf-of flow phù hợp hơn việc chuyển tiếp nguyên token từ client.

## 10. Bảo vệ metadata và dữ liệu định danh

Bearer token là credential. Bất kỳ thành phần nào đọc được metadata trên đường truyền đều có thể có khả năng sử dụng token đó trong thời gian còn hiệu lực. Vì vậy:

- Dùng TLS cho transport TCP hoặc WSS cho WebSocket khi đi qua mạng không tin cậy.
- Không ghi access token, refresh token hoặc toàn bộ authentication metadata vào log.
- Không đưa token vào route, query string hoặc phần data payload hiển thị cho handler nghiệp vụ.
- Giới hạn quyền và audience của token theo đúng dịch vụ cần gọi.
- Dùng token thời hạn ngắn và cơ chế thu hồi/refresh phù hợp.
- Không coi service token là quyền thay mặt cho mọi người dùng nếu chưa có chính sách delegation rõ ràng.

Metadata xác thực phải được xử lý bởi tầng security interceptor. Không tự parse token trong controller rồi tự quyết định danh tính nếu ứng dụng đã dùng Spring Security; cách đó dễ tạo hai cơ chế xác thực không nhất quán.

## 11. Kiểm thử không rò rỉ danh tính giữa các người dùng

Kiểm thử quan trọng nhất là gửi đồng thời request của hai người dùng qua cùng một RSocketRequester và xác nhận mỗi request nhận đúng dữ liệu của chủ thể tương ứng.

Ví dụ ở mức client:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<ProfileDto> alice = profileClient.findMyProfile(aliceToken);
Mono<ProfileDto> bob = profileClient.findMyProfile(bobToken);

StepVerifier.create(Mono.zip(alice, bob))
    .assertNext(pair -> {
        assertEquals("alice", pair.getT1().subject());
        assertEquals("bob", pair.getT2().subject());
    })
    .verifyComplete();
~~~

Trong integration test, hãy tạo hai JWT khác subject và scope, rồi gửi request đồng thời qua cùng requester. Ngoài trường hợp thành công, cần kiểm tra:

1. Request không có authentication metadata bị từ chối.
2. Token sai chữ ký, issuer hoặc audience bị từ chối.
3. Token hết hạn không thể truy cập route yêu cầu xác thực.
4. Token hợp lệ nhưng thiếu scope không được phép gọi route bị giới hạn.
5. Alice không thể lấy dữ liệu Bob bằng cách sửa userId trong payload.
6. Request của Alice và Bob chạy đồng thời nhưng không bị trộn principal hoặc tenant.
7. Service token hợp lệ được phép mở SETUP, nhưng không thể thay thế token người dùng ở request.
8. Token mới sau refresh có thể được dùng trên kết nối đang mở nếu phiên và chính sách bảo mật vẫn hợp lệ.

Nên ghi nhận subject đã được xác thực, route, kết quả authorization và correlation ID trong log bảo mật. Không ghi token thô. Các metric có thể đếm số request bị từ chối theo nguyên nhân mà không tiết lộ credential.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Đặt user token vào SETUP cho requester dùng chung | Mọi request có thể mang danh tính người mở kết nối | Đưa user token vào metadata của từng request |
| Tin userId trong payload | Người dùng có thể giả danh người khác | Dùng Principal/Authentication đã xác thực |
| Lưu currentUserId trong field singleton | Request đồng thời có thể ghi đè danh tính | Giữ identity trong request security context |
| Dùng chung service token cho mọi người dùng | Mất dấu người dùng cuối và quyền cá nhân | Dùng token delegation hoặc token người dùng per-request |
| Gửi token không đúng audience | Dịch vụ nhận token không dành cho mình | Kiểm tra aud hoặc dùng token exchange |
| Không kiểm tra scope ở route | Người dùng đã xác thực có thể gọi thao tác vượt quyền | Khai báo authorizePayload theo route/authority |
| Log toàn bộ metadata | Credential có thể bị lộ qua log | Mask hoặc loại bỏ token khỏi log |

## 13. Quy tắc chọn phạm vi danh tính

Hãy bắt đầu bằng câu hỏi ai sở hữu kết nối RSocket:

- Nếu mỗi kết nối chỉ thuộc về một người dùng, có thể xác thực người dùng tại SETUP và dùng danh tính đó trong phiên.
- Nếu một service/gateway chia sẻ kết nối cho nhiều người dùng, xác thực service ở SETUP nếu cần và gửi danh tính người dùng ở từng request.
- Nếu cần cả hai lớp, dùng service token có quyền mở kết nối và user token có quyền nghiệp vụ riêng; server phải kiểm tra cả điều kiện cấp kết nối lẫn điều kiện cấp request.

Không có một cách truyền danh tính phù hợp cho mọi mô hình. Ranh giới đúng là phạm vi mà credential đại diện: credential của chủ sở hữu kết nối thuộc SETUP, còn credential của người dùng thực hiện tương tác thuộc request metadata.

## 14. Kết luận

Khi nhiều người dùng chia sẻ một kết nối RSocket tới dịch vụ phía sau, không thể dùng một user principal cố định cho toàn bộ phiên. Hãy gửi token của từng người dùng trong authentication metadata của mỗi request, để Spring Security xác thực và tạo danh tính tương ứng cho tương tác đó.

Có thể bổ sung service token trong SETUP để kiểm soát thành phần được phép mở kết nối. Sau đó, handler dùng Principal đã xác thực để truy cập dữ liệu và áp dụng quyền theo subject/tenant. Tránh trạng thái người dùng mutable ở phạm vi kết nối, bảo vệ token bằng TLS và kiểm thử các request đồng thời để bảo đảm không xảy ra rò rỉ danh tính giữa người dùng.
