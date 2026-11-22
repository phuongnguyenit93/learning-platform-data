# Bảo vệ resolver bằng Spring Security

Một GraphQL operation có thể yêu cầu nhiều field trong cùng một request. Vì vậy, bảo vệ URL `/graphql` mới chỉ xác thực người gửi request; ứng dụng còn phải kiểm tra người đó được phép gọi resolver nào và đọc field nào. Với Spring for GraphQL, có thể dùng Spring Security method security để áp dụng quy tắc ngay trên các method `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`, `@BatchMapping` và `@SubscriptionMapping`.

Bài thực hành dùng JWT Bearer token, `@EnableMethodSecurity` và `@PreAuthorize` để bảo vệ truy vấn thành viên, field lương và mutation cập nhật. Các ví dụ dùng Spring Boot 3 trở lên, Spring Security 6 trở lên và Spring for GraphQL.

## 1. Hiểu hai lớp bảo vệ của GraphQL

Có hai câu hỏi bảo mật khác nhau:

- **Authentication – xác thực:** request đến từ ai? Ví dụ, token có hợp lệ và chưa hết hạn không?
- **Authorization – phân quyền:** người đó được phép làm gì? Ví dụ, họ có quyền đọc danh sách thành viên, xem lương hay cập nhật email không?

Lớp HTTP bảo vệ endpoint GraphQL và xác thực token trước khi GraphQL thực thi operation. Lớp method security kiểm tra quyền khi từng resolver được gọi. Một query có thể yêu cầu `member { id fullName salary }`; người dùng có quyền đọc thông tin cơ bản nhưng không có quyền xem `salary`. Khi đó resolver của `salary` cần một quy tắc riêng.

Không nên xem việc một query gốc đã được phép là bằng chứng rằng mọi field con đều được phép. Field có thể được lấy từ nhiều query, mutation, fragment hoặc resolver khác nhau. Hãy đặt quy tắc ở đúng điểm thực thi dữ liệu nhạy cảm.

## 2. Thêm dependency

Với Gradle và Spring Boot dependency management:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

`spring-boot-starter-security` cung cấp Spring Security và method security. `spring-boot-starter-oauth2-resource-server` cho phép ứng dụng xác thực JWT Bearer token. `spring-security-test` cung cấp annotation và tiện ích tạo người dùng giả lập trong kiểm thử.

## 3. Bảo vệ endpoint GraphQL bằng JWT

Khai báo issuer của hệ thống phát hành token trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
```

Thay URL minh họa bằng issuer thực tế của hệ thống. Spring Boot cấu hình `JwtDecoder` để kiểm tra chữ ký, thời hạn và issuer theo metadata của nhà cung cấp.

Tạo cấu hình bảo mật:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class GraphQlSecurityConfiguration {

    @Bean
    SecurityFilterChain graphQlSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là cấu hình minh họa cho API stateless chỉ nhận access token trong header `Authorization: Bearer ...`. Trong mô hình này, trình duyệt không tự động đính kèm Bearer token như cookie nên cấu hình tắt CSRF phù hợp với giả định đã nêu. Nếu ứng dụng xác thực bằng session hoặc cookie, hãy giữ bảo vệ CSRF và yêu cầu client gửi CSRF token; không sao chép tùy chọn `csrf.disable()` sang mô hình cookie.

Ví dụ dùng `/graphql` là endpoint mặc định. Nếu ứng dụng đổi `spring.graphql.path`, matcher trong SecurityFilterChain phải đổi theo. `anyRequest().permitAll()` chỉ nhằm làm rõ ví dụ; trong ứng dụng thực tế hãy khai báo chính sách cho các endpoint khác theo yêu cầu của hệ thống.

Khi thiếu hoặc có JWT không hợp lệ, HTTP security filter từ chối request trước khi GraphQL thực thi. Với request đã xác thực nhưng thiếu quyền cho một field, method security sẽ từ chối lời gọi resolver tương ứng.

## 4. Hiểu authority được tạo từ JWT

Theo cấu hình mặc định của resource server, các giá trị trong claim `scope` hoặc `scp` được chuyển thành authority có tiền tố `SCOPE_`. Ví dụ token có claim:

```json
{
  "sub": "user-184",
  "scope": "members:read members:salary:read"
}
```

thì Spring Security tạo các authority `SCOPE_members:read` và `SCOPE_members:salary:read`. Ta sẽ dùng chính các chuỗi này trong `@PreAuthorize`.

`hasAuthority("...")` so sánh authority chính xác. `hasRole("ADMIN")` có quy ước thêm tiền tố `ROLE_`, vì vậy không dùng lẫn hai cách nếu token đang phát hành scope theo chuẩn OAuth2. Nếu hệ thống dùng claim `roles`, `permissions` hoặc cấu trúc riêng, cần cấu hình `JwtAuthenticationConverter` để ánh xạ claim thành `GrantedAuthority` phù hợp.

## 5. Bảo vệ Query và Mutation bằng `@PreAuthorize`

Giả sử schema có query lấy thành viên và mutation cập nhật email:

```graphql
type Query {
    member(id: ID!): Member
}

type Member {
    id: ID!
    fullName: String!
    email: String!
    salary: String
}

input UpdateMemberEmailInput {
    memberId: ID!
    email: String!
}

type Mutation {
    updateMemberEmail(input: UpdateMemberEmailInput!): Member
}
```

Đặt `@PreAuthorize` trên method resolver:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;

record UpdateMemberEmailInput(String memberId, String email) {}

@Controller
public class MemberGraphQlController {

    private final MemberService memberService;

    public MemberGraphQlController(MemberService memberService) {
        this.memberService = memberService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('SCOPE_members:read')")
    public Member member(@Argument("id") String id) {
        return memberService.findById(id);
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('SCOPE_members:write')")
    public Member updateMemberEmail(
            @Argument("input") UpdateMemberEmailInput input) {
        return memberService.updateEmail(input.memberId(), input.email());
    }
}
```

`@EnableMethodSecurity` bật cơ chế method security để `@PreAuthorize` được thực thi. Spring Security kiểm tra biểu thức trước khi method resolver chạy. Nếu authority không thỏa mãn, lời gọi bị từ chối và `memberService` không được gọi.

Quyền đọc và quyền ghi nên tách riêng. Một token có `SCOPE_members:read` không tự động có `SCOPE_members:write`. Tránh chỉ kiểm tra một role rộng như `USER` cho mọi thao tác nếu các thao tác có mức độ nhạy cảm khác nhau.

## 6. Bảo vệ field nhạy cảm bằng `@SchemaMapping`

Query `member` có thể trả về object `Member`; khi client chọn field `salary`, Spring GraphQL gọi resolver riêng của field đó. Ta có thể yêu cầu authority bổ sung:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.security.access.prepost.PreAuthorize;

@SchemaMapping(typeName = "Member", field = "salary")
@PreAuthorize("hasAuthority('SCOPE_members:salary:read')")
public String salary(Member member) {
    return memberService.findSalary(member.id());
}
```

Người dùng có `SCOPE_members:read` nhưng không có `SCOPE_members:salary:read` vẫn có thể đọc các field cơ bản. Khi GraphQL thực thi field `salary`, Spring Security từ chối riêng resolver này. Vì SDL khai báo `salary: String` có thể null, GraphQL có thể trả các field khác trong `Member` cùng lỗi tại `salary`.

Ví dụ response minh họa:

```json
{
  "data": {
    "member": {
      "id": "42",
      "fullName": "Nguyen An",
      "email": "an@example.com",
      "salary": null
    }
  },
  "errors": [
    {
      "message": "Bạn không có quyền truy cập trường này",
      "path": ["member", "salary"],
      "extensions": {
        "classification": "FORBIDDEN"
      }
    }
  ]
}
```

Response trên minh họa trường hợp field resolver bị từ chối và lỗi được ánh xạ ở mục 9. Nếu schema khai báo field nhạy cảm là non-null, ví dụ `salary: String!`, lỗi khiến field trả null có thể lan truyền null lên object cha theo quy tắc GraphQL non-null. Hãy chọn nullability phù hợp với hợp đồng API.

## 7. Kiểm tra quyền trên từng tài nguyên

Authority `SCOPE_members:read` chỉ cho biết người dùng có quyền đọc loại dữ liệu thành viên. Nó chưa chứng minh người đó được đọc mọi thành viên. Ứng dụng đa tenant thường phải kiểm tra người dùng thuộc tenant nào hoặc có quan hệ sở hữu với bản ghi nào.

Có thể kết hợp kiểm tra scope và kiểm tra quyền trên tài nguyên trong cùng biểu thức:

```java
import org.springframework.security.core.parameters.P;

@QueryMapping
@PreAuthorize("hasAuthority('SCOPE_members:read') " +
        "and @memberAuthorization.canRead(authentication, #memberId)")
public Member member(
        @Argument("id") @P("memberId") String id) {
    return memberService.findById(id);
}
```

`@P("memberId")` đặt tên tham số rõ ràng cho biểu thức SpEL, không phụ thuộc việc compiler có lưu tên tham số hay không. Bean `memberAuthorization` được Spring đăng ký với tên tương ứng:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("memberAuthorization")
public class MemberAuthorization {

    private final MemberRepository memberRepository;

    public MemberAuthorization(MemberRepository memberRepository) {
        this.memberRepository = memberRepository;
    }

    public boolean canRead(Authentication authentication, String memberId) {
        return memberRepository.existsByIdAndOwnerSubject(
                memberId, authentication.getName());
    }
}
```

`existsByIdAndOwnerSubject` là ví dụ về phương thức repository cần được định nghĩa theo mô hình dữ liệu. Với JWT, `authentication.getName()` thường lấy subject (`sub`) của token theo cấu hình mặc định. Nếu hệ thống dùng tenant claim hoặc định danh nội bộ khác, hãy ánh xạ và kiểm tra đúng thuộc tính tin cậy đó.

Không nhận `ownerId`, `tenantId` hoặc role đặc quyền từ input rồi dùng trực tiếp để quyết định quyền. Những giá trị đó phải được lấy từ danh tính đã xác thực hoặc được đối chiếu với dữ liệu lưu trữ. Đồng thời, service/domain nên giữ kiểm tra quyền nếu cùng thao tác còn được gọi từ REST API, job hoặc một đường xử lý khác ngoài resolver.

## 8. Bảo vệ các kiểu resolver khác

Method security áp dụng theo method Spring quản lý, vì vậy có thể đặt annotation trên các handler GraphQL khác:

```java
@BatchMapping(typeName = "Team", field = "members")
@PreAuthorize("hasAuthority('SCOPE_members:read')")
public Map<Team, List<Member>> members(List<Team> teams) {
    return memberService.findMembersByTeams(teams);
}

@SubscriptionMapping
@PreAuthorize("hasAuthority('SCOPE_members:events:read')")
public Publisher<MemberEvent> memberEvents() {
    return memberService.memberEvents();
}
```

Đây là ví dụ về vị trí áp dụng; các kiểu `Team`, `MemberEvent` và phương thức service phụ thuộc ứng dụng. Với `@BatchMapping`, hãy kiểm tra quyền trên từng parent hoặc trong service khi batch chứa nhiều tài nguyên thuộc các tenant khác nhau. Một authority chung không thay thế kiểm tra quyền trên từng bản ghi.

Với subscription qua WebSocket, cần xác thực kết nối/handshake và thiết lập danh tính cho phiên GraphQL theo cơ chế WebSocket của ứng dụng. `@PreAuthorize` kiểm tra lúc method subscription được gọi; nếu quyền có thể thay đổi trong thời gian stream tồn tại, hãy cân nhắc kiểm tra lại quyền cho từng sự kiện hoặc trước khi phát dữ liệu nhạy cảm.

## 9. Chuẩn hóa lỗi truy cập bị từ chối

Khi một resolver đã chạy nhưng method security từ chối quyền, GraphQL biểu diễn lỗi thực thi trong mảng `errors`. Có thể dùng `@GraphQlExceptionHandler` để trả thông điệp an toàn và phân loại lỗi `FORBIDDEN`:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlSecurityAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("Bạn không có quyền truy cập trường này")
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` giữ thông tin vị trí và path của field phát sinh lỗi. Thông điệp không tiết lộ tên tenant, sự tồn tại của bản ghi, chính sách nội bộ hoặc chi tiết exception. Có thể bỏ tham số `exception` nếu không cần đọc nội dung của nó.

Request chưa xác thực bị chặn ở HTTP filter thường nhận HTTP 401 trước khi GraphQL chạy. Request đã xác thực nhưng thiếu quyền resolver nhận lỗi GraphQL được phân loại `FORBIDDEN`. Hai tình huống xảy ra ở hai lớp khác nhau; client nên xử lý cả HTTP status lẫn mảng `errors` của GraphQL.

## 10. Kiểm thử method security với `GraphQlTester`

Thêm test để xác nhận người có scope đọc được query và người thiếu scope bị từ chối trước khi service được gọi. `@WithMockUser` thiết lập authentication trong test; `GraphQlTester` thực thi GraphQL trực tiếp nên ví dụ này tập trung vào method security, không kiểm thử JWT filter của HTTP.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@GraphQlTest(MemberGraphQlController.class)
@Import({MemberGraphQlSecurityTest.MethodSecurityTestConfig.class,
        GraphQlSecurityAdvice.class})
class MemberGraphQlSecurityTest {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    MemberService memberService;

    @Test
    @WithMockUser(authorities = "SCOPE_members:read")
    void readerCanExecuteMemberQuery() {
        graphQlTester.document("""
                query {
                    member(id: "42") {
                        id
                        fullName
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isEmpty());

        verify(memberService).findById("42");
    }

    @Test
    @WithMockUser(authorities = "SCOPE_members:basic")
    void userWithoutReadScopeIsDeniedBeforeServiceCall() {
        graphQlTester.document("""
                query {
                    member(id: "42") {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors)
                        .anyMatch(error -> error.getMessage()
                                .contains("không có quyền truy cập")));

        verifyNoInteractions(memberService);
    }

    @TestConfiguration
    @EnableMethodSecurity
    static class MethodSecurityTestConfig {}
}
```

Test thành công ở trên chỉ kiểm tra không có GraphQL error; để xác nhận dữ liệu trả về, hãy cấu hình mock `memberService.findById` trả một `Member` và assert các path tương ứng. Có thể bổ sung test cho field `salary` để chứng minh scope đọc thành viên không tự cấp quyền xem lương.

`@MockitoBean` có trong Spring Framework 6.2 trở lên. Với phiên bản cũ hơn, dùng cơ chế mock bean tương ứng của dự án, chẳng hạn `@MockBean` nếu phiên bản đang dùng hỗ trợ. Để kiểm tra lớp HTTP và JWT thực tế, bổ sung kiểm thử tích hợp bằng MockMvc/WebTestClient với Bearer token hợp lệ, token hết hạn, token sai issuer và request không có token.

## 11. Những lỗi bảo mật thường gặp

- **Chỉ yêu cầu đăng nhập ở `/graphql`.** Người dùng đã xác thực vẫn có thể gọi mutation hoặc field nhạy cảm nếu resolver không có quy tắc authorization.
- **Chỉ bảo vệ query gốc.** Field resolver, batch resolver và mutation khác có thể là đường truy cập tới cùng dữ liệu; đặt quy tắc tại các điểm thực thi tương ứng.
- **Dùng `hasRole` cho scope.** `hasRole` tự thêm `ROLE_`; scope mặc định của resource server có tiền tố `SCOPE_`, nên dùng `hasAuthority` đúng giá trị.
- **Tin ID hoặc tenant do client gửi.** ID hợp lệ không chứng minh người gọi có quyền truy cập bản ghi. Đối chiếu tài nguyên với danh tính đã xác thực.
- **Chỉ kiểm tra quyền trong controller.** Nếu service được gọi từ một API hoặc job khác, đường gọi đó có thể bỏ qua controller. Đặt quy tắc nghiệp vụ quan trọng ở service/domain.
- **Tắt CSRF trong ứng dụng dùng cookie/session.** Trình duyệt tự gửi cookie có thể tạo request ngoài ý muốn. Chỉ dùng cấu hình stateless Bearer token khi giả định xác thực thực sự đáp ứng điều kiện đó.
- **Trả chi tiết exception cho client.** Dùng thông điệp chung, mã lỗi ổn định và log chi tiết ở server theo chính sách bảo vệ dữ liệu.
- **Quên bảo vệ WebSocket subscription.** Kiểm tra cách xác thực handshake/connection và quyền trong suốt thời gian stream hoạt động.

## 12. Bài tập hoàn thiện

Từ `MemberGraphQlController`, hãy thực hiện các yêu cầu sau:

1. Cấu hình resource server xác thực JWT và bảo vệ endpoint `/graphql`.
2. Yêu cầu `SCOPE_members:read` cho query `member` và `SCOPE_members:write` cho mutation cập nhật.
3. Tạo field `salary` chỉ dành cho người có `SCOPE_members:salary:read`.
4. Bổ sung kiểm tra quyền theo owner hoặc tenant của từng member; không tin `ownerId` do client gửi.
5. Chuẩn hóa `AccessDeniedException` thành GraphQL error `FORBIDDEN` và xác nhận response có path của field bị từ chối.
6. Viết test cho người có scope, người thiếu scope và người có scope đọc nhưng không có scope xem lương.

Sau khi hoàn thành, hãy tự trả lời: xác thực request khác phân quyền resolver ở điểm nào; tại sao field con cần quy tắc riêng; `hasAuthority` khác `hasRole` ra sao; và vì sao quyền đọc một loại tài nguyên chưa đủ để cho phép đọc mọi bản ghi thuộc loại đó?
