# Xây mutation có input validation

Một mutation tốt cần bảo vệ dữ liệu ngay tại ranh giới API, kiểm tra quy tắc nghiệp vụ trước khi ghi dữ liệu và trả lỗi đủ rõ để client sửa yêu cầu. Với Spring for GraphQL, ta kết hợp ràng buộc kiểu trong GraphQL SDL, Jakarta Bean Validation trên input Java và kiểm tra nghiệp vụ trong service.

Bài thực hành xây mutation `createMember` nhận tên, email và tuổi. Mutation chỉ gọi service khi dữ liệu hợp lệ. Các ví dụ dùng Java record và namespace `jakarta.validation`, phù hợp với ứng dụng Spring Boot 3 trở lên có Spring for GraphQL.

## 1. Xác định các lớp kiểm tra

Luồng xử lý có bốn lớp, mỗi lớp giải quyết một loại vấn đề:

1. **GraphQL SDL** kiểm tra cấu trúc của operation: field có tồn tại không, kiểu dữ liệu có đúng không, field bắt buộc có bị thiếu hoặc nhận `null` không.
2. **Bean Validation** kiểm tra nội dung của từng giá trị: chuỗi không được rỗng, email đúng định dạng, tuổi nằm trong giới hạn.
3. **Service/domain** kiểm tra quy tắc phụ thuộc nghiệp vụ hoặc trạng thái hiện tại: email đã được sử dụng chưa, người gọi có quyền tạo thành viên trong nhóm này không.
4. **Database** duy trì các ràng buộc cuối cùng như unique constraint và foreign key. Kiểm tra trước ở service giúp thông báo thân thiện; ràng buộc ở database vẫn cần thiết để xử lý các request đồng thời.

Không nên dồn cả bốn lớp vào resolver. Resolver nhận input đã được bind và hợp lệ về cấu trúc, sau đó điều phối tới service.

## 2. Thêm dependency cần thiết

Với Gradle và Spring Boot dependency management, thêm các starter sau; để BOM của Spring Boot quản lý phiên bản tương thích:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
```

`spring-boot-starter-validation` đưa Jakarta Bean Validation provider vào ứng dụng. Nếu thiếu provider, các annotation như `@NotBlank` vẫn biên dịch được khi API có mặt nhưng không có bộ thực thi để kiểm tra chúng lúc chạy.

## 3. Khai báo input và mutation trong SDL

Tạo hoặc cập nhật schema tại `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    member(id: ID!): Member
}

type Member {
    id: ID!
    fullName: String!
    email: String!
    age: Int!
}

input CreateMemberInput {
    fullName: String!
    email: String!
    age: Int!
}

type Mutation {
    createMember(input: CreateMemberInput!): Member
}
```

`input` là kiểu dành cho dữ liệu client gửi vào; không dùng output type `Member` làm input. `CreateMemberInput!` yêu cầu client truyền object input, còn dấu `!` trên từng field yêu cầu giá trị của field đó không được thiếu hoặc `null`.

SDL không thể biểu đạt mọi quy tắc nội dung. Ví dụ, `email: String!` vẫn chấp nhận chuỗi rỗng và `age: Int!` vẫn chấp nhận số âm. Các điều kiện đó sẽ được kiểm tra bằng Bean Validation.

Trong ví dụ, field mutation trả về `Member` có thể null. Khi resolver phát sinh lỗi validation, GraphQL có thể trả `createMember: null` cùng phần tử trong `errors`. Nếu đổi kiểu trả về thành `Member!`, lỗi tại field này có thể lan truyền null lên cấp cha theo quy tắc non-null của GraphQL.

## 4. Tạo input model với Jakarta Bean Validation

Tạo record `CreateMemberInput`:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateMemberInput(
        @NotBlank(message = "Họ tên không được để trống")
        @Size(max = 100, message = "Họ tên không được dài quá 100 ký tự")
        String fullName,

        @NotBlank(message = "Email không được để trống")
        @Email(message = "Email không đúng định dạng")
        @Size(max = 254, message = "Email không được dài quá 254 ký tự")
        String email,

        @NotNull(message = "Tuổi là bắt buộc")
        @Min(value = 18, message = "Thành viên phải từ 18 tuổi")
        @Max(value = 120, message = "Tuổi không được lớn hơn 120")
        Integer age
) {}
```

Một vài điểm cần phân biệt:

- `@NotNull` chỉ từ chối `null`; nó không từ chối chuỗi rỗng.
- `@NotBlank` từ chối `null`, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng. Annotation này dành cho `CharSequence`.
- `@Email` kiểm tra định dạng cơ bản. Nó không xác nhận hộp thư tồn tại, người dùng sở hữu hộp thư hay email chưa được đăng ký.
- `@Size` giới hạn độ dài; nó không thay thế `@NotBlank`.
- Dùng `Integer` thay cho `int` để mô hình Java vẫn biểu diễn được `null`, giúp `@NotNull` có ý nghĩa khi input được gọi từ đường đi khác hoặc khi SDL thay đổi.

Giới hạn `18..120` chỉ là quy tắc minh họa. Trong ứng dụng thực tế, hãy chọn giới hạn theo nghiệp vụ và chính sách dữ liệu của hệ thống.

## 5. Gắn validation vào tham số `@Argument`

Resolver dùng `@MutationMapping` để ánh xạ vào field `createMember` trong SDL:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MemberGraphQlController {

    private final MemberService memberService;

    public MemberGraphQlController(MemberService memberService) {
        this.memberService = memberService;
    }

    @MutationMapping
    public Member createMember(
            @Argument("input") @Valid CreateMemberInput input) {
        return memberService.create(input);
    }
}
```

`@Argument("input")` lấy object từ argument `input` của mutation. `@Valid` yêu cầu Spring for GraphQL chạy Bean Validation trên object đã bind. Nếu có constraint vi phạm, quá trình gọi resolver dừng lại và Spring GraphQL phát sinh `BindException`; lời gọi `memberService.create` không được thực hiện.

Đặt constraint trên input model giúp các quy tắc định dạng gắn với dữ liệu đầu vào và có thể được kiểm tra độc lập. Không cần tự gọi `Validator.validate` trong từng resolver nếu đã dùng cơ chế `@Valid` này.

## 6. Chuyển lỗi validation thành GraphQL error dễ hiểu

Có thể gom xử lý lỗi vào `@ControllerAdvice` để các resolver dùng chung một cách phản hồi:

```java
import graphql.GraphqlErrorBuilder;
import graphql.GraphQLError;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.stream.Collectors;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBindException(BindException exception) {
        String details = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .distinct()
                .collect(Collectors.joining("; "));

        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.BAD_REQUEST)
                .message("Dữ liệu đầu vào không hợp lệ: " + details)
                .build();
    }
}
```

`@GraphQlExceptionHandler` cho phép Spring GraphQL chuyển exception phát sinh trong data fetcher thành `GraphQLError`. `ErrorType.BAD_REQUEST` phân loại lỗi đầu vào; thông điệp chỉ chứa tên field và nội dung constraint đã định nghĩa. Không đưa stack trace, câu SQL, thông tin cấu hình hoặc dữ liệu nhạy cảm vào thông điệp gửi client.

GraphQL thường biểu diễn lỗi thực thi trong mảng `errors` của response. Không nên giả định mọi lỗi resolver sẽ được thể hiện bằng một HTTP status riêng; client cần đọc cả `data` và `errors` theo giao thức GraphQL.

Lỗi do GraphQL không parse được document, sai tên field hoặc sai kiểu scalar thường được phát hiện trước khi resolver chạy. Những lỗi đó không phải `BindException` từ Bean Validation và không đi qua handler này.

## 7. Đặt quy tắc nghiệp vụ trong service

Bean Validation phù hợp với điều kiện độc lập trên input. Các điều kiện cần truy cập repository, trạng thái hệ thống hoặc quyền của người dùng thuộc service/domain:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Service
public class MemberService {

    private final MemberRepository memberRepository;

    public MemberService(MemberRepository memberRepository) {
        this.memberRepository = memberRepository;
    }

    @Transactional
    public Member create(CreateMemberInput input) {
        if (memberRepository.existsByEmailIgnoreCase(input.email())) {
            throw new DuplicateEmailException("Email đã được sử dụng");
        }

        Member member = new Member(
                null,
                input.fullName().trim(),
                input.email().trim().toLowerCase(Locale.ROOT),
                input.age()
        );

        return memberRepository.save(member);
    }
}
```

Đây là phần minh họa cách phân lớp; `Member`, `MemberRepository` và `DuplicateEmailException` là các kiểu domain/repository của ứng dụng cần được định nghĩa tương ứng. Quy tắc email duy nhất cũng phải có unique constraint ở database. Hai request đồng thời có thể cùng vượt qua `existsByEmailIgnoreCase`, vì vậy truy vấn kiểm tra trước không thay thế được ràng buộc lưu trữ và cách xử lý vi phạm constraint.

Nếu muốn trả lỗi nghiệp vụ như email trùng, hãy ánh xạ `DuplicateEmailException` sang một GraphQL error có mã ổn định hoặc trả một mutation payload chứa `userErrors`. Không nên giả mạo lỗi này thành lỗi Bean Validation.

## 8. Gửi mutation từ GraphQL client

Dùng biến GraphQL để tách operation khỏi dữ liệu:

```graphql
mutation CreateMember($input: CreateMemberInput!) {
    createMember(input: $input) {
        id
        fullName
        email
        age
    }
}
```

Variables hợp lệ:

```json
{
  "input": {
    "fullName": "Nguyễn Minh An",
    "email": "an@example.com",
    "age": 24
  }
}
```

Khi request hợp lệ, GraphQL gọi resolver, Spring bind input, Bean Validation kiểm tra các constraint, sau đó service tạo thành viên và resolver trả object `Member`.

## 9. Quan sát response khi input không hợp lệ

Thử gửi email sai định dạng và tuổi nhỏ hơn giới hạn:

```json
{
  "input": {
    "fullName": "An",
    "email": "khong-phai-email",
    "age": 16
  }
}
```

Với handler ở mục 6, response có dạng minh họa:

```json
{
  "data": {
    "createMember": null
  },
  "errors": [
    {
      "message": "Dữ liệu đầu vào không hợp lệ: email: Email không đúng định dạng; age: Thành viên phải từ 18 tuổi",
      "extensions": {
        "classification": "BAD_REQUEST"
      },
      "path": ["createMember"]
    }
  ]
}
```

Đây là hình dạng minh họa; thứ tự các field error và các extension phụ thuộc phiên bản thư viện cùng cấu hình. Điều cần kiểm tra là response có lỗi được phân loại phù hợp, field mutation không trả dữ liệu thành công và service không ghi dữ liệu.

## 10. Kiểm thử qua GraphQlTester

Unit test cho constraint có ích, nhưng integration test qua `GraphQlTester` còn xác nhận SDL, argument binding, `@Valid` và exception handler phối hợp đúng.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@GraphQlTest(MemberGraphQlController.class)
@Import(GraphQlValidationAdvice.class)
class MemberGraphQlControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    MemberService memberService;

    @Test
    void rejectsInvalidEmailAndAgeBeforeCallingService() {
        graphQlTester.document("""
                mutation {
                    createMember(input: {
                        fullName: "An"
                        email: "khong-phai-email"
                        age: 16
                    }) {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors)
                        .anyMatch(error -> error.getMessage().contains("email")
                                && error.getMessage().contains("age")));

        verifyNoInteractions(memberService);
    }
}
```

`@MockitoBean` có trong Spring Framework 6.2 trở lên. Với phiên bản Spring Boot/Spring Framework cũ hơn, dùng cơ chế mock bean tương ứng của phiên bản dự án, chẳng hạn `@MockBean` nếu còn được hỗ trợ. Nếu test slice không tự tìm thấy schema, kiểm tra schema nằm dưới `src/main/resources/graphql/` hoặc cấu hình schema location của ứng dụng.

Nên bổ sung test cho các trường hợp: tên rỗng, tên vượt quá 100 ký tự, email rỗng, tuổi bằng 17, tuổi bằng 18, tuổi vượt 120 và input hợp lệ. Với trường hợp hợp lệ, mock service trả về `Member` rồi xác nhận response có dữ liệu mong đợi.

## 11. Phân biệt lỗi SDL với lỗi Bean Validation

Hai nhóm lỗi xảy ra ở các thời điểm khác nhau:

| Tình huống | Nơi phát hiện | Resolver có chạy không? |
|---|---|---|
| Thiếu `input` trong mutation | GraphQL kiểm tra operation | Không |
| `age` nhận chuỗi thay vì `Int` | GraphQL kiểm tra/coerce scalar | Không |
| `email` nhận `null` khi SDL khai báo `String!` | GraphQL kiểm tra input | Không |
| `email` là chuỗi rỗng | `@NotBlank` | Có bắt đầu bind; service không được gọi |
| `email` sai định dạng | `@Email` | Có bắt đầu bind; service không được gọi |
| `age` nhỏ hơn 18 | `@Min(18)` | Có bắt đầu bind; service không được gọi |
| Email đã được tài khoản khác dùng | Service/domain và database | Có |

Nếu GraphQL từ chối request trước resolver, handler `BindException` ở mục 6 không xử lý lỗi đó. Hãy kiểm tra response GraphQL và test đúng lớp chịu trách nhiệm cho từng tình huống.

## 12. Validate input lồng nhau

Khi input chứa object con, cần đặt `@Valid` trên component lồng nhau để validation đi tiếp vào object đó:

```java
public record AddressInput(
        @NotBlank(message = "Thành phố không được để trống")
        String city,

        @NotBlank(message = "Mã quốc gia không được để trống")
        @Size(min = 2, max = 2, message = "Mã quốc gia phải có 2 ký tự")
        String countryCode
) {}

public record CreateMemberInput(
        @NotBlank @Size(max = 100) String fullName,
        @NotBlank @Email @Size(max = 254) String email,
        @NotNull @Min(18) @Max(120) Integer age,
        @NotNull @Valid AddressInput address
) {}
```

SDL tương ứng cần có `AddressInput` và field `address: AddressInput!`. `@Valid` kích hoạt kiểm tra các constraint của `AddressInput`; nếu thiếu annotation này, constraint trên `city` và `countryCode` có thể không được duyệt khi validate object cha. Với collection input, dùng `List<...>` và cascade validation cho từng phần tử theo cấu trúc model.

## 13. Giữ authorization tách biệt khỏi validation

Input hợp lệ không đồng nghĩa người gọi được phép thực hiện mutation. Ví dụ, `groupId` có định dạng đúng vẫn có thể thuộc về nhóm mà người dùng hiện tại không được quản lý. Hãy lấy danh tính từ security context, kiểm tra quyền ở lớp phù hợp và kiểm tra quyền truy cập tới từng tài nguyên trong service/domain.

Không nhận `ownerId`, `createdBy` hoặc vai trò đặc quyền từ client rồi tin trực tiếp các giá trị đó. Nếu API cần một ID do client gửi, service phải xác minh người gọi được phép thao tác trên tài nguyên tương ứng. Validation giải quyết chất lượng dữ liệu; authorization giải quyết quyền thực hiện hành động.

## 14. Những lỗi triển khai thường gặp

- **Chỉ khai báo `String!` rồi nghĩ chuỗi luôn có nội dung.** `!` chỉ loại `null`; thêm `@NotBlank` để từ chối chuỗi rỗng/khoảng trắng.
- **Quên `@Valid` trên `@Argument`.** Constraint có thể được khai báo đầy đủ nhưng không được kích hoạt ở đường xử lý resolver.
- **Dùng `@NotBlank` cho số.** Chọn constraint theo kiểu dữ liệu, chẳng hạn `@NotNull`, `@Min` và `@Max` cho `Integer`.
- **Đặt truy vấn database trong custom validator cho mọi trường hợp.** Điều đó dễ làm validation phụ thuộc hạ tầng và không giải quyết được race condition. Quy tắc phụ thuộc trạng thái thường phù hợp hơn trong service/domain.
- **Chỉ kiểm tra dữ liệu ở client.** Client có thể bị bỏ qua hoặc bị giả mạo; server phải tự kiểm tra.
- **Trả exception thô cho client.** Chuyển exception thành lỗi GraphQL có thông điệp an toàn và mã phân loại ổn định.
- **Cho rằng lỗi nào cũng đi qua `BindException`.** Lỗi parse, schema validation, scalar coercion, authorization và lỗi nghiệp vụ có nguồn phát sinh khác nhau; cần xử lý theo đúng loại.
- **Dùng validation thay cho constraint database.** Kiểm tra trước khi lưu không bảo vệ được dữ liệu trước các request đồng thời hoặc đường ghi khác.

## 15. Bài tập hoàn thiện

Từ mutation `createMember`, hãy hoàn thiện các yêu cầu sau:

1. Bổ sung field `phoneNumber` với quy tắc không để trống và giới hạn độ dài hợp lý. Chọn constraint phù hợp với định dạng số điện thoại mà hệ thống hỗ trợ.
2. Thêm `AddressInput` và cascade validation cho `city`, `countryCode`.
3. Viết integration test chứng minh email sai định dạng và tuổi ngoài giới hạn đều bị từ chối trước khi gọi service.
4. Tạo trường hợp email trùng trong service; ánh xạ lỗi nghiệp vụ thành GraphQL error có mã ổn định, đồng thời đặt unique constraint ở database.
5. Thử gửi request thiếu `email` hoặc truyền `age` sai kiểu để quan sát lỗi do GraphQL xử lý trước resolver.

Khi hoàn thành, có thể tự trả lời các câu hỏi kiểm tra:

- Vì sao `String!` không thay thế được `@NotBlank`?
- `@Valid` đóng vai trò gì trên tham số `@Argument`?
- Vì sao kiểm tra email trùng trong service vẫn cần unique constraint ở database?
- Lỗi nào được xử lý bởi `@GraphQlExceptionHandler` cho `BindException`, và lỗi nào được GraphQL phát hiện trước resolver?
- Vì sao validation thành công chưa chứng minh người dùng có quyền chạy mutation?
