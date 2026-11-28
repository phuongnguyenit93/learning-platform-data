# Thay đổi lớp principal, SecurityContext và module hỗ trợ tuần tự hóa

Spring Session lưu `HttpSession` hoặc `WebSession` vào kho dữ liệu như Redis hoặc JDBC. Trong ứng dụng dùng Spring Security, session thường chứa `SecurityContext`, `Authentication`, principal và authorities. Khi nâng cấp ứng dụng, thay đổi package hoặc tên lớp principal, thay đổi cấu trúc `Authentication`, hoặc thay serializer có thể khiến instance mới không đọc được session được ghi bởi phiên bản cũ.

Đây là vấn đề tương thích dữ liệu tồn tại qua nhiều lần deploy. Một rolling deployment có thể đồng thời chạy phiên bản N và N+1 trên cùng session store. Instance mới phải đọc được dữ liệu cũ trong thời gian chuyển tiếp; instance cũ cũng có thể phải đọc dữ liệu mới nếu load balancer chuyển request theo cả hai chiều. Nếu không có kế hoạch, lỗi `ClassNotFoundException`, `InvalidClassException`, lỗi Jackson type resolution hoặc lỗi chuyển đổi có thể khiến người dùng bị mất phiên hoặc request xác thực thất bại.

## 1. Vì sao principal và SecurityContext nằm trong dữ liệu session?

Với xác thực dựa trên session, Spring Security lưu trạng thái xác thực để request tiếp theo không phải nhập lại credential. `SecurityContext` chứa `Authentication`; đối tượng này thường tham chiếu tới principal, authorities và thông tin xác thực khác.

Một principal có thể là:

- `UserDetails` do ứng dụng tự định nghĩa.
- Một đối tượng principal từ thư viện identity.
- `Jwt` hoặc principal được tạo từ OIDC/OAuth2 login.
- Một DTO chứa subject ID, tenant và một số thuộc tính tối thiểu.

Nếu principal tùy chỉnh được lưu vào session, dữ liệu của nó có thể được serialize cùng SecurityContext. Ví dụ:

```java
public final class PortalPrincipal implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String subjectId;
    private final String tenantId;
    private final List<String> authorities;

    public PortalPrincipal(
            String subjectId,
            String tenantId,
            List<String> authorities) {
        this.subjectId = subjectId;
        this.tenantId = tenantId;
        this.authorities = List.copyOf(authorities);
    }

    public String getSubjectId() { return this.subjectId; }
    public String getTenantId() { return this.tenantId; }
    public List<String> getAuthorities() { return this.authorities; }
}
```

Đây là ví dụ principal gọn. Không nên đưa toàn bộ entity người dùng, quan hệ ORM, mật khẩu, access token hoặc dữ liệu hồ sơ không cần thiết vào principal. Principal được lưu trong session nên được xem là một phần schema dữ liệu bền vững trong suốt TTL của session.

## 2. Thay đổi class có thể làm session cũ không đọc được

Khi dùng Java native serialization, stream thường chứa tên lớp đầy đủ (fully qualified class name), metadata và dữ liệu field. Các thay đổi sau có thể phá tương thích:

- Đổi package hoặc đổi tên lớp principal.
- Chuyển lớp sang module/artifact khác và không còn class cũ trên classpath.
- Thay kiểu field, ví dụ `Long` thành `String`.
- Xóa field hoặc thay đổi ý nghĩa của field.
- Thay đổi `serialVersionUID`.
- Thay đổi class của `Authentication`, `GrantedAuthority` hoặc một object lồng bên trong.
- Instance cũ và mới chạy các dependency Spring Security khác nhau không tương thích.

Lỗi thường gặp gồm `ClassNotFoundException`, `InvalidClassException`, `NotSerializableException` hoặc lỗi deserialize do field/type không phù hợp. Đổi tên package là thay đổi đặc biệt dễ gây lỗi: class mới có thể có cùng field nhưng serializer vẫn tìm class theo tên cũ.

Với JSON serializer có type metadata, tên type cũng có thể được lưu trong payload. Nếu payload ghi type `com.old.auth.PortalPrincipal` nhưng phiên bản mới chỉ còn `com.new.security.PortalPrincipal`, deserializer có thể không tìm thấy type cũ hoặc từ chối type đó.

Không giả định session cũ tự được chuyển sang class mới chỉ vì code đã compile thành công. Cần kiểm thử bằng payload được tạo từ phiên bản trước.

## 3. Vai trò của serialVersionUID

Với Java serialization, `serialVersionUID` giúp xác định tính tương thích giữa phiên bản class khi deserialize. Nếu class không khai báo rõ, JVM có thể tính giá trị mặc định từ cấu trúc lớp; thay đổi method, field hoặc chi tiết class có thể làm giá trị tính toán đổi ngoài dự kiến.

Khai báo UID rõ ràng:

```java
public final class LegacyPrincipal implements Serializable {

    private static final long serialVersionUID = 1L;

    private String username;
    private List<String> roles;
}
```

Giữ nguyên UID không bảo đảm mọi thay đổi đều an toàn. Nó chỉ tránh một số mismatch về version; thay đổi field type hoặc semantics vẫn có thể gây lỗi hoặc tạo dữ liệu không hợp lệ. Ngược lại, đổi UID có chủ ý thường khiến stream cũ bị từ chối, có thể là lựa chọn đúng nếu không thể chuyển đổi an toàn.

Với mỗi thay đổi class được serialize, cần đánh giá:

- Field mới có giá trị mặc định hợp lệ khi đọc stream cũ không?
- Field bị xóa có được bỏ qua an toàn không?
- Field đổi kiểu có converter/migration rõ ràng không?
- Invariant của principal có còn được bảo đảm không?
- Có cần giữ class cũ làm compatibility shim trong thời gian TTL không?

Không hạ hoặc cố định `serialVersionUID` một cách máy móc để ép deserialize. Mục tiêu là đọc đúng dữ liệu cũ, không chỉ làm exception biến mất.

## 4. Principal nên là DTO ổn định, không phải domain entity

Một cách giảm rủi ro nâng cấp là tách principal lưu trong session khỏi domain entity và model persistence. Domain entity thường thay đổi theo schema nghiệp vụ, ORM mapping hoặc module. Principal session nên nhỏ và có contract ổn định.

Ví dụ:

```java
public final class SessionPrincipalV1 implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String subject;
    private final String tenant;
    private final List<String> authorityNames;

    public SessionPrincipalV1(
            String subject,
            String tenant,
            List<String> authorityNames) {
        this.subject = Objects.requireNonNull(subject);
        this.tenant = Objects.requireNonNull(tenant);
        this.authorityNames = List.copyOf(authorityNames);
    }

    public String getSubject() { return this.subject; }
    public String getTenant() { return this.tenant; }
    public List<String> getAuthorityNames() { return this.authorityNames; }
}
```

DTO này tránh tham chiếu tới `UserEntity`, Hibernate proxy, repository hoặc service bean. Nếu ứng dụng cần hồ sơ đầy đủ, dùng `subject` để tải từ nguồn chính và kiểm tra quyền ở thời điểm truy cập.

Một DTO ổn định vẫn cần versioning. Có thể dùng tên type có version hoặc field `schemaVersion`, nhưng phải định nghĩa cách đọc phiên bản cũ. Không đổi `SessionPrincipalV1` thành class khác rồi hy vọng serializer tự suy ra quan hệ giữa chúng.

## 5. Tương thích class principal khi đổi package

Giả sử phiên bản N có:

```java
package com.acme.security;

public class PortalPrincipal implements Serializable {
    private static final long serialVersionUID = 1L;
    private String userId;
}
```

Phiên bản N+1 chuyển class sang `com.acme.identity.PortalPrincipal`. Nếu session được lưu bằng Java serialization, stream cũ vẫn tham chiếu `com.acme.security.PortalPrincipal`. Chỉ thêm class mới không đủ.

Các chiến lược có thể chọn:

1. **Giữ lớp cũ tạm thời:** giữ class cũ trong artifact tương thích để instance mới đọc được session cũ; chuyển đổi sang model mới khi đọc hoặc theo batch.
2. **Compatibility adapter:** giữ type cũ làm wrapper/DTO chỉ phục vụ deserialize, sau đó ánh xạ sang principal mới đã validate.
3. **Versioned JSON type mapping:** nếu serializer hỗ trợ type alias/migration an toàn, ánh xạ type cũ sang DTO mới bằng allowlist và converter tường minh.
4. **Đổi namespace và yêu cầu đăng nhập lại:** nếu session cũ không cần được bảo toàn hoặc không thể chuyển đổi an toàn, tạo vùng session mới và invalidate phiên cũ theo kế hoạch.

Không tạo một class cùng tên cũ nhưng có semantics khác chỉ để deserialize thành công. Sau khi đọc, phải xác thực lại subject, tenant và authorities theo chính sách hiện hành.

## 6. Thay đổi SecurityContext và Authentication

`SecurityContext` là abstraction chứa `Authentication`. Thay đổi cách tạo hoặc lưu Authentication có thể ảnh hưởng dữ liệu session:

- Đổi loại token authentication đang sử dụng.
- Thay custom `Authentication` class bằng implementation khác.
- Thay principal type hoặc authorities collection.
- Thêm field không serializable vào token.
- Thay cách lưu details như IP, session metadata hoặc tenant context.
- Nâng Spring Security khiến module hỗ trợ serialization hoặc type metadata thay đổi.

Không nên tự serialize một object `SecurityContext` tùy ý nếu ứng dụng không kiểm soát các object lồng bên trong. Kiểm thử toàn bộ graph: context, authentication, principal, authorities và details.

Khi tạo context trong code, tiếp tục dùng API Spring Security thay vì tự giả lập cấu trúc nội bộ:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

Đoạn code chỉ minh họa tạo context trong luồng ứng dụng; nó không thay thế authentication flow, không phải hướng dẫn ghi trực tiếp vào Redis/JDBC. Spring Security quản lý lifecycle và persistence qua `SecurityContextRepository` cùng tích hợp Spring Session.

Không dùng session migration để nâng quyền hoặc tự đặt `authenticated=true`. Dữ liệu deserialize thành công vẫn cần được xác thực theo nguồn tin cậy và policy hiện hành.

## 7. Authorities và custom GrantedAuthority

Authorities thường được lưu cùng Authentication. `SimpleGrantedAuthority` là implementation phổ biến. Nếu ứng dụng dùng custom `GrantedAuthority`, class đó và các field lồng bên trong cũng phải tương thích serializer.

Một authority nhỏ có thể được biểu diễn bằng chuỗi role/scope đã chuẩn hóa. Tránh lưu cả entity permission, policy graph hoặc toàn bộ danh sách quyền không cần thiết. Nếu quyền có thể thay đổi nhanh, cần xác định thời điểm làm mới authorities hoặc thu hồi session/context cũ.

Khi đổi cấu trúc authority, ví dụ từ `List<String>` sang custom object, cần migration hoặc converter. Không cast dữ liệu cũ sang kiểu mới mà không kiểm tra. Một lỗi mapping authority có thể dẫn tới mất quyền hợp lệ hoặc cấp quyền sai.

## 8. Module hỗ trợ tuần tự hóa của Spring Security

Khi dùng JSON serialization cho session, Jackson cần biết cách xử lý các kiểu của Spring Security như `SecurityContext`, `Authentication` và một số implementation principal/authority. Spring Security cung cấp các Jackson modules để đăng ký serializer/deserializer phù hợp cho những kiểu được hỗ trợ.

Với Spring Session Redis, ví dụ cấu hình thường gặp là cung cấp bean serializer có tên `springSessionDefaultRedisSerializer` và đăng ký các module do `SecurityJackson2Modules` cung cấp:

```java
@Configuration
class SessionRedisSerializationConfiguration {

    @Bean("springSessionDefaultRedisSerializer")
    RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModules(
                SecurityJackson2Modules.getModules(
                        getClass().getClassLoader()));
        return new GenericJackson2JsonRedisSerializer(mapper);
    }
}
```

Các package, constructor và bean contract có thể thay đổi theo phiên bản Spring Security/Spring Data Redis. Đối chiếu tài liệu của dependency đang dùng. Đặc biệt, nếu tự cấu hình `ObjectMapper`, cần xác nhận type metadata cần thiết được cấu hình theo serializer đang chọn; không sao chép một cấu hình Jackson tổng quát mà chưa kiểm tra round-trip cho SecurityContext.

Không bật polymorphic default typing rộng với mọi class chỉ để deserialize session. Nếu serializer cần type metadata, dùng validator/allowlist phù hợp, giới hạn các package/type được phép và kiểm thử payload không hợp lệ. Redis là kho nội bộ nhưng dữ liệu vẫn cần được coi là đầu vào có thể bị thay đổi nếu credential hoặc quyền truy cập kho bị lộ.

## 9. Các module Jackson khác cho kiểu dữ liệu của ứng dụng

Principal có thể chứa kiểu Java ngoài các kiểu Security. Ví dụ:

- `java.time.Instant`/`LocalDate`: cần hỗ trợ Java Time của Jackson nếu serializer dùng JSON.
- `Optional` hoặc kiểu JDK 8: có thể cần module JDK 8.
- Kotlin data class: cần module Kotlin tương thích.
- Constructor parameter names: cần cách ánh xạ constructor phù hợp nếu DTO immutable.
- Custom value object: cần serializer/deserializer hoặc creator rõ ràng.

Chỉ đăng ký module cần thiết. Một module Jackson không tương thích phiên bản có thể làm ObjectMapper khởi tạo lỗi hoặc deserialize khác mong đợi. Giữ phiên bản Jackson do Spring Boot dependency management quản lý trừ khi có lý do rõ ràng để override.

Kiểm thử các giá trị null, collection rỗng, field mới, field bị thiếu, enum không còn tồn tại và timezone. Một payload có thể deserialize được nhưng mang semantics sai nếu giá trị mặc định thay đổi.

## 10. Redis serializer và JDBC conversion là hai cấu hình khác nhau

Không giả định bean serializer Redis cũng được Spring Session JDBC sử dụng. Redis repository thường nhận `RedisSerializer<Object>` theo contract riêng. JDBC repository có cơ chế chuyển đổi/serialize attributes qua `ConversionService` và converter của implementation.

Với Redis, kiểm tra:

- Bean serializer có đúng tên và được repository nhận không.
- ObjectMapper có module Spring Security và module kiểu dữ liệu ứng dụng cần thiết không.
- Type metadata/allowlist có an toàn không.
- Các instance dùng cùng serializer trong giai đoạn rolling deploy không.

Với JDBC, kiểm tra:

- `JdbcIndexedSessionRepository` đang dùng conversion service nào.
- Converter serialize/deserialize attributes có được cấu hình thống nhất trên mọi instance không.
- Schema column có đủ khả năng lưu payload mới không.
- Bản ghi cũ có thể được đọc bởi converter mới không.
- Transaction và migration có giữ session metadata cùng attributes nhất quán không.

Một số phiên bản cung cấp bean/conversion service extension point cho JDBC với tên contract cụ thể. Hãy dùng API đúng phiên bản và test bằng database thật trong integration test. Đừng chỉ đổi Redis serializer rồi cho rằng JDBC đã đổi theo.

## 11. Tương thích khi nâng cấp Spring Security

Nâng Spring Security có thể thay đổi:

- Package hoặc class implementation của một số kiểu authentication.
- Jackson module và serializer/deserializer được cung cấp.
- Cấu trúc principal do OAuth2/OIDC login tạo ra.
- Cách lưu/đọc SecurityContext.
- Kiểu authorities hoặc details được serialize.
- Dependency Jackson và các module phụ thuộc.

Hãy xem serialized SecurityContext là dữ liệu có version và kiểm thử giữa phiên bản cũ/mới. Không chỉ chạy unit test với context mới được tạo bởi cùng phiên bản mới; cần fixture được tạo bằng ứng dụng phiên bản cũ.

Nếu Spring Security thay đổi cấu trúc nội bộ, không nên tự phụ thuộc vào class implementation nội bộ nếu API không cam kết. Giữ principal của ứng dụng là DTO ổn định và để framework quản lý SecurityContext qua public API.

## 12. Chiến lược rolling deployment N và N+1

Khi A chạy phiên bản N và B chạy phiên bản N+1 cùng đọc một session store, mọi payload do N+1 ghi có thể được N đọc trong thời gian rollout. Một chiến lược an toàn thường dùng quy trình expand–migrate–contract:

1. **Expand:** phiên bản N được bổ sung khả năng đọc schema cũ và schema mới, nhưng vẫn ghi format cũ.
2. **Deploy compatibility:** triển khai phiên bản trung gian trên toàn bộ instance, bảo đảm mọi node đọc được cả hai format.
3. **Switch writes:** chuyển writer sang format mới sau khi không còn node chỉ đọc format cũ.
4. **Migrate/drain:** chuyển đổi session còn sống hoặc chờ TTL cũ hết hạn.
5. **Contract:** gỡ code đọc format cũ sau khi xác nhận không còn payload cũ.

Nếu không thể duy trì tương thích, chọn namespace version mới hoặc invalidate session và yêu cầu đăng nhập lại. Đây có thể là phương án đơn giản, an toàn hơn việc cố deserialize một object graph không đáng tin cậy.

Không triển khai node N+1 ghi principal class mới trong khi node N vẫn nhận request và cần đọc cùng session, trừ khi N có thể đọc format mới.

## 13. Bảng quyết định cho thay đổi principal

| Thay đổi | Rủi ro | Chiến lược thường phù hợp |
|---|---|---|
| Thêm field tùy chọn | Giá trị thiếu ở payload cũ | Default hợp lệ, test old-to-new và new-to-old |
| Xóa field không còn dùng | Code cũ có thể cần field | Giữ field trong thời gian chuyển tiếp hoặc version schema |
| Đổi kiểu field | Deserialize hoặc semantics sai | Converter/migration tường minh |
| Đổi package/class name | Class/type cũ không tìm thấy | Compatibility shim, alias có kiểm soát hoặc reauthentication |
| Đổi `serialVersionUID` | Java stream cũ bị từ chối | Chỉ đổi khi chủ ý invalidation hoặc đã có migration |
| Đổi Authentication implementation | SecurityContext không tương thích | Dùng mapping qua DTO/API ổn định, test security modules |
| Đổi Jackson/Security module | Payload type metadata thay đổi | Versioned serializer và fixture compatibility |
| Chuyển Java serialization sang JSON | Format hoàn toàn khác | Dual-read converter hoặc namespace mới/reauth |

## 14. Chuyển đổi dữ liệu session cũ

Có ba hướng phổ biến:

### 14.1. Giữ tương thích và chuyển đổi khi đọc

Giữ class cũ hoặc converter đọc payload cũ. Khi session được tải, ánh xạ principal cũ sang DTO mới, kiểm tra subject/tenant/authorities rồi lưu lại theo format mới. Cách này giảm logout hàng loạt nhưng cần xử lý concurrency và đảm bảo mọi request không ghi ngược format cũ.

### 14.2. Chạy migration theo batch

Một job đọc session cũ, chuyển đổi principal/attributes và ghi lại session. Job phải:

- Xử lý theo batch có giới hạn tải.
- Bỏ qua session đã hết hạn hoặc đã bị thu hồi.
- Giữ nguyên session ID và expiry nếu chính sách cho phép.
- Cập nhật attributes và index liên quan một cách nhất quán.
- Có checkpoint, retry idempotent và log không chứa payload nhạy cảm.
- Tránh ghi đè snapshot mới hơn do request đang chạy.

Migration batch không đơn giản nếu repository không có API liệt kê mọi session hoặc nếu dữ liệu được cập nhật đồng thời. Không quét keyspace Redis hoặc bảng production bằng một job không có giới hạn và kế hoạch rollback.

### 14.3. Invalidate session và yêu cầu đăng nhập lại

Nếu principal cũ chứa dữ liệu nhạy cảm, format không an toàn hoặc không thể chuyển đổi đáng tin cậy, có thể đổi namespace/schema version và để session cũ hết hạn hoặc xóa theo quy trình. Người dùng đăng nhập lại tạo SecurityContext mới.

Đây là lựa chọn có tác động UX nhưng dễ kiểm soát hơn việc chấp nhận payload không thể xác minh. Cần thông báo rõ, đánh giá ảnh hưởng phiên quản trị/phiên đang xử lý và có kế hoạch rollback.

## 15. Không migrate bằng cách deserialize mọi object tùy ý

Migration job có quyền đọc và deserialize lượng lớn dữ liệu session. Nếu kho có payload bị sửa, deserialize có thể tạo object ngoài dự kiến hoặc kích hoạt gadget chain tùy serializer và classpath.

Các nguyên tắc:

- Chỉ deserialize từ kho được bảo vệ và kiểm tra nguồn dữ liệu.
- Ưu tiên DTO/JSON schema có allowlist type.
- Không bật polymorphic typing toàn cục thiếu validator.
- Chạy migration với quyền đọc/ghi tối thiểu, trong môi trường kiểm soát.
- Giới hạn số session và kích thước payload mỗi batch.
- Validate principal subject, tenant, authorities và version trước khi ghi.
- Không ghi payload/session ID/token nguyên vẹn vào log.
- Có thể dừng job an toàn và tiếp tục từ checkpoint.

Không dùng `ObjectInputStream` trực tiếp trên dữ liệu tùy ý mà không có kiểm soát class filter và trust boundary. Nếu vẫn dùng Java serialization cho dữ liệu session, cần bảo vệ kho, giới hạn class được deserialize theo khả năng nền tảng và giảm tối đa object graph.

## 16. Kiểm thử round-trip và fixture của phiên bản cũ

Một bài test serializer cơ bản phải xác minh round-trip:

```java
byte[] bytes = serializer.serialize(securityContext);
Object restored = serializer.deserialize(bytes);

assertThat(restored).isInstanceOf(SecurityContext.class);
SecurityContext context = (SecurityContext) restored;
assertThat(context.getAuthentication().getName()).isEqualTo("user-42");
```

Đoạn code là khung minh họa; serializer có thể trả `null` cho input null và generic type/API khác nhau theo thư viện. Quan trọng là kiểm tra principal, authorities, authenticated state và các field cần thiết sau deserialize, không chỉ assert object khác null.

Tạo fixture bytes/JSON từ build phiên bản N và lưu trong test resources. Trong build N+1, đọc fixture đó bằng serializer mới. Đồng thời kiểm thử N+1 ghi payload mà phiên bản tương thích cũ có thể đọc nếu rolling deployment cần hỗ trợ chiều ngược lại.

Không tạo fixture cũ bằng class mới rồi đổi tên file thành “legacy”. Fixture phải được tạo bởi artifact cũ hoặc từ dữ liệu đã xác nhận trong môi trường test. Không dùng session production thật làm fixture.

## 17. Ma trận kiểm thử tương thích

| Writer | Reader | Kết quả cần xác minh |
|---|---|---|
| Phiên bản N | N | Baseline cũ |
| Phiên bản N | N+1 | Phiên bản mới đọc session cũ |
| Phiên bản N+1 | N | Cần đạt nếu rollout cho phép node cũ đọc dữ liệu mới |
| Phiên bản N+1 | N+1 | Baseline mới |
| Java serializer cũ | Serializer mới | Có converter/migration hoặc chủ ý reject |
| JSON type cũ | JSON type mới | Alias/schema mapping đúng và an toàn |
| Principal cũ | Principal DTO mới | Subject/tenant/authority được ánh xạ đúng |
| SecurityContext cũ | Spring Security mới | Authentication được khôi phục với đúng semantics |

Test thêm các trường hợp lỗi:

- Class cũ không còn trên classpath.
- `serialVersionUID` mismatch.
- Field type đổi.
- Authority class không còn tồn tại.
- Jackson type ID không được allowlist.
- Field bắt buộc bị thiếu hoặc có giá trị không hợp lệ.
- Payload bị cắt hoặc hỏng.
- Session hết hạn trong lúc migration.
- Hai request đồng thời sửa session khi migration chạy.

Kỳ vọng có thể là chuyển đổi thành công hoặc từ chối session và yêu cầu xác thực lại; không chấp nhận khôi phục Authentication sai.

## 18. Kiểm thử qua Spring Session repository thật

Unit test serializer chưa đủ để xác minh repository. Cần integration test với Redis hoặc JDBC tương ứng:

1. Khởi chạy repository với serializer/conversion service production-like.
2. Tạo session và lưu `SecurityContext` cùng principal phiên bản cũ.
3. Đóng context hoặc tạo instance mới dùng classpath phiên bản mới.
4. Đọc session theo cùng ID.
5. Xác minh principal, authorities, expiry và attributes được giữ đúng.
6. Cập nhật session từ instance mới rồi đọc lại bằng instance tương thích khác.
7. Kiểm tra logout/delete và index principal vẫn hoạt động.
8. Kiểm tra payload không tương thích được xử lý an toàn, không biến lỗi deserialize thành anonymous một cách im lặng nếu store thực sự lỗi.

Với Redis, test đúng namespace và serializer bean. Với JDBC, test conversion service, bảng attributes, column type và transaction. Testcontainers giúp dùng backend thật trong CI.

## 19. Tích hợp SpringSessionBackedSessionRegistry sau thay đổi principal

Nếu ứng dụng dùng `SpringSessionBackedSessionRegistry` để quản lý số phiên đồng thời, principal index phải tiếp tục được duy trì sau migration. Việc thay principal class có thể ảnh hưởng cách `Authentication.getName()` hoặc `IndexResolver` lấy principal name.

Sau khi nâng cấp, xác minh:

- Principal name trước và sau migration có cùng semantics.
- `findByPrincipalName` tìm được các session đã đăng nhập.
- Logout một session xóa index membership.
- Đổi principal không để lại index cũ.
- Concurrent session control đếm đúng session qua nhiều instance.
- Session cũ bị từ chối hoặc chuyển đổi theo chính sách.

Không đổi username format hoặc normalization trong cùng lần thay principal nếu chưa có kế hoạch cập nhật index. Nếu đổi subject format, cần migration index hoặc chấp nhận phiên cũ không còn được tìm thấy và yêu cầu đăng nhập lại.

## 20. Thay đổi classpath và module hỗ trợ tuần tự hóa

Trong dự án nhiều module, principal hoặc converter có thể được chuyển sang module mới. Cần kiểm tra:

- Module chứa class principal có mặt trong runtime classpath của mọi instance.
- Dependency scope không chỉ có trong test hoặc compile nhưng thiếu khi chạy.
- Module chứa Jackson/Spring Security serialization support tương thích với Spring Security version.
- Không có hai phiên bản class cùng tên trong classpath.
- Application classloader có thể load type được payload tham chiếu.
- Native image/AOT hoặc module system có reflection/configuration cần thiết nếu ứng dụng dùng chúng.

Lỗi `ClassNotFoundException` trong deserialize có thể do class đã đổi tên hoặc dependency không được đóng gói. Đừng xử lý bằng cách thêm mọi module tùy tiện; xác định class cụ thể trong exception và kiểm tra dependency tree/artifact thực tế.

## 21. Thay đổi schema khi chuyển principal sang DTO

Một migration có thể chuyển từ principal chứa `UserDetails` đầy đủ sang DTO gọn:

```text
Old session:
  SecurityContext
    Authentication
      principal = LegacyUserDetails
        username
        passwordHash
        email
        profile
        roles

New session:
  SecurityContext
    Authentication
      principal = SessionPrincipalV1
        subject
        tenant
        authorityNames
```

Converter phải xác định các field mới từ dữ liệu cũ, loại bỏ field không còn cần và không đưa password hash/email/profile sang DTO mới nếu không cần. Authorities cần được xác minh lại theo nguồn chính nếu có khả năng thay đổi từ lúc session được tạo.

Không chỉ copy `roles` cũ sang authority mới mà không kiểm tra tenant, trạng thái tài khoản và phiên bản policy. Session migration là chuyển đổi cấu trúc, không phải xác thực lại người dùng; khi mức tin cậy không đủ, invalidate session là lựa chọn an toàn hơn.

## 22. Khi nào nên yêu cầu đăng nhập lại?

Yêu cầu người dùng đăng nhập lại có thể là lựa chọn đúng khi:

- Principal cũ không thể được xác minh hoặc ánh xạ an toàn.
- Authentication token class đã thay đổi semantics.
- Authority mapping hoặc tenant boundary thay đổi.
- Serializer cũ không an toàn hoặc payload có nguy cơ bị sửa.
- Không thể chạy hai phiên bản tương thích trong rolling deployment.
- Session đã quá cũ và có thể chờ TTL tự hết.

Nếu chỉ thay field không nhạy cảm và có converter đã kiểm thử, migration có thể giữ phiên. Nếu thay đổi ảnh hưởng tới quyền hoặc danh tính, ưu tiên reauthentication hoặc xác minh lại qua identity provider.

Không xóa toàn bộ session một cách bất ngờ để xử lý lỗi deserialize mà không có kế hoạch truyền thông, đánh giá tác động và xác minh rằng thao tác chỉ nhắm đúng namespace/môi trường.

## 23. Chẩn đoán lỗi deserialize sau deploy

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ClassNotFoundException` | Class principal/token cũ không còn trong runtime classpath | Kiểm tra tên class trong payload và artifact runtime; giữ shim hoặc migrate |
| `InvalidClassException` | `serialVersionUID` hoặc cấu trúc class không tương thích | Kiểm tra UID/field diff; fixture test và converter |
| `NotSerializableException` | Principal/authority mới chứa field không serializable | Loại field hoặc tạo DTO/serializer phù hợp |
| Jackson invalid type ID | Type metadata trỏ tới class cũ hoặc không allowlist | Type alias/converter an toàn hoặc invalidate session |
| Unknown property/missing creator | DTO constructor/field/schema thay đổi | Cấu hình mapper có kiểm soát và version schema |
| SecurityContext rỗng sau nâng cấp | Serializer module hoặc repository integration sai | Kiểm tra SecurityJackson2Modules, bean serializer và filter chain |
| Chỉ một instance lỗi | Dependency/classpath/serializer config lệch giữa node | So sánh artifact, config và runtime modules |
| Session đọc được nhưng authorities sai | Mapping role/scope hoặc principal converter sai | Kiểm tra authorization semantics và source of truth |

Không log payload session hoặc SecurityContext để chẩn đoán. Ghi class exception, type ID đã làm sạch, serializer version, application version và correlation ID. Bảo vệ session ID và token khỏi log.

## 24. Quy trình nâng cấp an toàn

1. Kiểm kê principal, Authentication, authorities và mọi object lồng trong SecurityContext được lưu.
2. Xác định serializer của Redis hoặc conversion service của JDBC.
3. Thu thập fixture session được tạo bởi phiên bản hiện tại trong môi trường test.
4. Xác định class/package/field/type/module nào thay đổi.
5. Chọn compatibility shim, converter, batch migration, namespace mới hoặc reauthentication.
6. Nếu rolling deployment, triển khai khả năng đọc cả format cũ và mới trước khi đổi writer.
7. Đăng ký Spring Security Jackson modules và module dữ liệu cần thiết theo serializer.
8. Hạn chế type deserialization và kiểm soát classpath/runtime dependency.
9. Chạy ma trận writer-reader N/N+1 với Redis/JDBC thật.
10. Kiểm tra principal name index, concurrent session registry, logout và expiry.
11. Theo dõi lỗi deserialize, session miss, authentication failure và tỷ lệ đăng nhập lại.
12. Chỉ gỡ class/converter cũ sau khi TTL cũ đã hết hoặc migration xác nhận không còn payload cũ.

## 25. Checklist trước khi phát hành

| Kiểm tra | Điều kiện đạt |
|---|---|
| Principal | Nhỏ, ổn định, không phụ thuộc entity/service |
| SecurityContext | Authentication và authorities có thể serialize/deserialize |
| Java serialization | UID và class compatibility được kiểm tra nếu sử dụng |
| Jackson | Spring Security modules và module kiểu dữ liệu đã đăng ký |
| Type safety | Không bật polymorphic typing rộng thiếu validator |
| Redis | Đúng `springSessionDefaultRedisSerializer` và mọi node dùng cùng format |
| JDBC | Conversion service/converter và schema tương thích |
| Rolling deployment | Node N/N+1 đọc được payload cần thiết trong giai đoạn chuyển tiếp |
| Migration | Có converter/checkpoint hoặc kế hoạch reauthentication rõ ràng |
| Security | Subject/tenant/authorities được xác minh, không nâng quyền qua migration |
| Tests | Có fixture cũ, round-trip, repository integration và lỗi deserialize |
| Observability | Theo dõi deserialize failures mà không log payload nhạy cảm |

## 26. Tài liệu chính thức để đối chiếu

API và module serialization có thể thay đổi theo phiên bản Spring Session, Spring Security và Spring Data Redis. Đối chiếu tài liệu đúng dòng dependency:

- [Spring Session — Redis configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [Spring Security — Jackson support](https://docs.spring.io/spring-security/reference/features/integrations/jackson.html)
- [Spring Security — SecurityContext persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Data Redis — Serialization](https://docs.spring.io/spring-data/redis/reference/redis/template.html)

Principal, Authentication và SecurityContext là một phần dữ liệu session khi ứng dụng dùng xác thực dựa trên phiên. Đổi class, package, field, serializer hoặc module hỗ trợ tuần tự hóa có thể làm session cũ không đọc được hoặc khôi phục sai authorities. Hãy giữ principal gọn và ổn định, đăng ký module Spring Security phù hợp với serializer, kiểm thử fixture từ phiên bản cũ và triển khai theo chiến lược tương thích N/N+1. Nếu không thể chứng minh dữ liệu cũ được chuyển đổi an toàn, invalidate session và yêu cầu xác thực lại là lựa chọn rõ ràng hơn việc chấp nhận một SecurityContext không đáng tin.
