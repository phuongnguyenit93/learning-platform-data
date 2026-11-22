# UUID scalar trong GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao GraphQL không có scalar UUID dựng sẵn và khi nào nên công bố một scalar UUID.
- Phân biệt UUID với scalar ID và String của GraphQL.
- Khai báo custom scalar UUID trong SDL và sử dụng nó ở field, argument và input object.
- Đăng ký scalar UUID vào GraphQL runtime bằng Spring for GraphQL.
- Bind giá trị UUID vào kiểu java.util.UUID trong controller và service.
- Hiểu vai trò của parse literal, parse variable và serialize output.
- Kiểm tra UUID không hợp lệ, nullability và lỗi coercion.
- Thiết kế, kiểm thử và bảo vệ API sử dụng UUID một cách nhất quán.

## 1. UUID là gì và vì sao cần scalar riêng?

UUID (Universally Unique Identifier) là định danh có độ dài 128 bit, thường được biểu diễn dưới dạng chuỗi hexadecimal có dấu gạch nối:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Dạng văn bản phổ biến gồm 36 ký tự: 32 chữ số hexadecimal và 4 dấu gạch nối theo nhóm 8-4-4-4-12. UUID thường được dùng làm định danh cho user, order, product, event hoặc một tài nguyên cần nhận diện duy nhất.

GraphQL có năm scalar dựng sẵn: Int, Float, String, Boolean và ID. GraphQL không định nghĩa scalar UUID dựng sẵn. Nếu schema cần công bố rõ một giá trị phải tuân theo định dạng UUID, ứng dụng cần định nghĩa custom scalar.

Ví dụ:

~~~graphql
scalar UUID

type User {
    id: UUID!
    displayName: String!
}
~~~

Khai báo scalar UUID tạo ra một kiểu dữ liệu có tên UUID trong schema. Tuy nhiên, chỉ khai báo SDL chưa đủ để GraphQL runtime biết cách đọc, kiểm tra và chuyển đổi giá trị UUID. Ứng dụng phải đăng ký scalar implementation tương ứng.

Một scalar UUID có thể đảm nhiệm ba việc:

- Nhận giá trị đầu vào từ GraphQL literal hoặc variables.
- Kiểm tra và chuyển giá trị thành kiểu mà ứng dụng sử dụng, thường là java.util.UUID.
- Chuyển giá trị Java thành dạng chuỗi chuẩn khi trả response.

## 2. Phân biệt UUID, ID và String

Ba kiểu này có thể đều được biểu diễn dưới dạng chuỗi trong JSON, nhưng ý nghĩa hợp đồng khác nhau.

| Kiểu GraphQL | Ý nghĩa | Có kiểm tra định dạng UUID không? |
| --- | --- | --- |
| ID | Định danh của một đối tượng; định dạng nội bộ có thể do server quyết định | Không |
| String | Văn bản thông thường | Không |
| UUID | Định danh phải tuân theo định dạng UUID mà scalar quy định | Có, nếu coercing implementation thực hiện kiểm tra |

Ví dụ schema dùng ID:

~~~graphql
type Query {
    user(id: ID!): User
}
~~~

ID phù hợp khi client chỉ cần truyền một định danh opaque. Giá trị có thể là UUID, số được chuyển thành chuỗi, slug hoặc một mã định danh khác. GraphQL không tự kiểm tra rằng giá trị đó có dạng UUID.

Nếu hợp đồng API yêu cầu định danh phải là UUID, có thể dùng:

~~~graphql
type Query {
    user(id: UUID!): User
}
~~~

Khi đó, một chuỗi không phải UUID sẽ bị từ chối ở bước coercion của scalar trước khi resolver được gọi.

Dùng String chỉ vì UUID được truyền qua JSON dưới dạng chuỗi sẽ làm mất thông tin kiểu trong schema. Client không thể biết từ schema rằng giá trị đó phải tuân theo quy tắc UUID.

### 2.1. Khi nào nên dùng từng kiểu?

Chọn ID khi định danh là một chi tiết opaque của API và server muốn giữ quyền thay đổi định dạng trong tương lai.

Chọn UUID khi định dạng UUID là một phần có chủ đích của hợp đồng công khai, ví dụ nhiều hệ thống cần trao đổi cùng loại định danh hoặc client muốn ánh xạ kiểu này sang UUID của ngôn ngữ lập trình.

Chọn String khi giá trị là văn bản, không phải định danh theo hợp đồng UUID.

Không nên đổi tất cả field ID thành UUID chỉ vì database hiện tại dùng UUID làm primary key. Schema GraphQL nên phản ánh hợp đồng mà client cần biết, không nhất thiết phản chiếu kiểu lưu trữ của database.

## 3. Định nghĩa UUID scalar trong SDL

GraphQL SDL khai báo custom scalar bằng từ khóa scalar:

~~~graphql
"""
Định danh 128 bit được biểu diễn dưới dạng chuỗi UUID chuẩn.
"""
scalar UUID
~~~

Sau đó, có thể dùng scalar UUID ở bất kỳ vị trí nào chấp nhận một input hoặc output scalar.

### 3.1. Dùng UUID làm output field

~~~graphql
type User {
    id: UUID!
    displayName: String!
    email: String!
}
~~~

Field id trả về UUID không null. Khi response được serialize, giá trị UUID thường xuất hiện dưới dạng chuỗi:

~~~json
{
    "data": {
        "user": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "displayName": "An Nguyen",
            "email": "an@example.com"
        }
    }
}
~~~

### 3.2. Dùng UUID làm argument

~~~graphql
type Query {
    user(id: UUID!): User
    usersByIds(ids: [UUID!]!): [User!]!
}
~~~

Field user nhận một UUID. Field usersByIds nhận danh sách UUID không null; danh sách và từng phần tử đều không được null.

Client có thể gọi:

~~~graphql
query {
    user(id: "550e8400-e29b-41d4-a716-446655440000") {
        id
        displayName
    }
}
~~~

UUID literal được đặt trong dấu ngoặc kép vì biểu diễn đầu vào là chuỗi. Scalar implementation sẽ parse chuỗi đó thành giá trị UUID.

### 3.3. Dùng UUID trong input object

~~~graphql
input CreateUserInput {
    externalId: UUID
    displayName: String!
}

type Mutation {
    createUser(input: CreateUserInput!): User!
}
~~~

Client gửi variables:

~~~json
{
    "input": {
        "externalId": "550e8400-e29b-41d4-a716-446655440000",
        "displayName": "An Nguyen"
    }
}
~~~

JSON không có kiểu UUID riêng, vì vậy UUID được truyền dưới dạng JSON string. GraphQL runtime dùng scalar UUID đã đăng ký để coercion giá trị trước khi chuyển dữ liệu đầu vào đến resolver.

### 3.4. Nullability vẫn áp dụng như các scalar khác

Có thể khai báo:

- UUID: giá trị có thể null.
- UUID!: giá trị bắt buộc, không được null.
- [UUID!]!: danh sách bắt buộc và từng UUID trong danh sách cũng bắt buộc.

Custom scalar không thay đổi quy tắc nullability của GraphQL. Nếu field được khai báo UUID! nhưng resolver trả null, GraphQL xử lý lỗi theo quy tắc non-null propagation.

## 4. Định dạng UUID và quy tắc kiểm tra

UUID có nhiều phiên bản được tiêu chuẩn hóa. Các phiên bản thường gặp gồm UUID v1, v4 và v7. Mỗi phiên bản có cách tạo giá trị khác nhau, nhưng đều dùng cùng dạng biểu diễn UUID tiêu chuẩn.

Ví dụ:

~~~text
550e8400-e29b-41d4-a716-446655440000
f47ac10b-58cc-4372-a567-0e02b2c3d479
018f1f2e-7b3c-7cc1-9f3a-123456789abc
~~~

Một scalar UUID tổng quát thường kiểm tra chuỗi có phải dạng UUID hợp lệ về mặt cú pháp hay không. Nếu nghiệp vụ chỉ cho phép một số version cụ thể, chẳng hạn UUID v4, cần bổ sung quy tắc kiểm tra version riêng.

Phân biệt hai mức kiểm tra:

- **Kiểm tra cú pháp:** giá trị có thể được parse thành UUID hay không.
- **Kiểm tra nghiệp vụ:** UUID có thuộc đối tượng hiện có, có đúng tenant, có đúng loại định danh hoặc có đáp ứng chính sách version của ứng dụng hay không.

Parse thành công không chứng minh rằng đối tượng tồn tại hoặc người dùng có quyền truy cập nó.

### 4.1. Chữ hoa và chữ thường

Chữ hexadecimal trong chuỗi UUID có thể xuất hiện ở dạng chữ hoa hoặc chữ thường. UUID.toString() của Java thường tạo biểu diễn chữ thường chuẩn hóa.

Ví dụ hai chuỗi sau biểu diễn cùng một UUID:

~~~text
550E8400-E29B-41D4-A716-446655440000
550e8400-e29b-41d4-a716-446655440000
~~~

Ứng dụng nên thống nhất dạng serialize trong response, thường là chuỗi canonical do scalar implementation tạo ra. Không nên dùng so sánh chuỗi thô ở tầng nghiệp vụ khi hai giá trị có thể khác chữ hoa/chữ thường nhưng cùng một UUID.

### 4.2. UUID không hợp lệ

Các giá trị sau không có dạng UUID chuẩn:

~~~text
550e8400-e29b-41d4-a716
not-a-uuid
550e8400_e29b_41d4_a716_446655440000
~~~

Scalar cần từ chối các giá trị không parse được và tạo lỗi coercion rõ ràng. Không nên âm thầm biến chuỗi sai định dạng thành UUID mặc định hoặc trả về null, vì điều đó che giấu lỗi đầu vào và làm sai hợp đồng API.

## 5. Cài đặt UUID scalar trong Spring for GraphQL

Có hai hướng thường dùng:

1. Dùng thư viện custom scalar đã được triển khai và kiểm thử.
2. Tự viết Coercing khi có quy tắc UUID riêng mà thư viện hiện có không đáp ứng.

Với UUID tiêu chuẩn, thư viện graphql-java-extended-scalars cung cấp scalar UUID có sẵn. Đây là lựa chọn phù hợp để tránh tự viết lại logic parse và serialize phổ biến.

### 5.1. Thêm dependency graphql-java-extended-scalars

Với Maven:

~~~xml
<dependency>
    <groupId>com.graphql-java</groupId>
    <artifactId>graphql-java-extended-scalars</artifactId>
    <version>compatible-version</version>
</dependency>
~~~

Khai báo phiên bản thư viện tương thích với phiên bản GraphQL Java mà Spring Boot đang quản lý.

Với Gradle:

~~~groovy
dependencies {
    implementation("com.graphql-java:graphql-java-extended-scalars:compatible-version")
}
~~~

Không nên tự nâng riêng GraphQL Java chỉ để cài extended scalars. Hãy kiểm tra dependency management của Spring Boot và chọn bản extended scalars tương thích với GraphQL Java đang được resolve trong dự án.

### 5.2. Đăng ký scalar bằng RuntimeWiringConfigurer

Spring for GraphQL cung cấp RuntimeWiringConfigurer để bổ sung scalar vào runtime wiring.

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer uuidScalarConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.UUID);
    }
}
~~~

Trong ví dụ:

- ExtendedScalars.UUID là scalar implementation được thư viện cung cấp.
- RuntimeWiringConfigurer bổ sung scalar vào GraphQL runtime.
- Tên scalar được đăng ký phải khớp với tên UUID trong SDL.

Khi runtime được xây dựng, GraphQL engine có thể dùng scalar này để parse input và serialize output.

Không cần tự tạo một resolver cho scalar UUID. Scalar coercing chịu trách nhiệm chuyển đổi giá trị; resolver của field vẫn chịu trách nhiệm xử lý nghiệp vụ như tìm user hoặc tạo order.

### 5.3. Nếu tự triển khai Coercing

GraphQL Java biểu diễn custom scalar thông qua GraphQLScalarType và Coercing. Một coercing implementation cần xử lý ba hướng chuyển đổi:

| Phương thức | Dữ liệu đầu vào | Vai trò |
| --- | --- | --- |
| parseValue | Giá trị từ variables, thường là JSON string | Kiểm tra và chuyển thành UUID |
| parseLiteral | Giá trị literal trong GraphQL document | Kiểm tra AST node và chuyển thành UUID |
| serialize | Giá trị Java trả về từ resolver | Chuyển UUID thành chuỗi response |

Luồng chuyển đổi:

~~~mermaid
flowchart TD
    A["GraphQL variable hoặc literal"] --> B["parseValue / parseLiteral"]
    B --> C{"UUID hợp lệ?"}
    C -->|Không| D["Coercion error"]
    C -->|Có| E["java.util.UUID"]
    E --> F["Resolver / service"]
    F --> G["Giá trị UUID trả về"]
    G --> H["serialize"]
    H --> I["Chuỗi UUID trong response"]
~~~

Khi tự viết coercing:

- Chỉ chấp nhận kiểu đầu vào mà API công bố, thường là chuỗi.
- Parse bằng thư viện UUID chuẩn của Java.
- Chuyển lỗi parse thành exception coercion phù hợp của GraphQL Java.
- Không để parseLiteral và parseValue áp dụng hai quy tắc khác nhau.
- serialize nên xử lý kiểu UUID mà resolver thực sự trả về.
- Không đưa stack trace hoặc chi tiết nội bộ vào thông báo lỗi công khai.

Chữ ký của các phương thức Coercing có thể khác nhau giữa các phiên bản GraphQL Java. Một số phiên bản mới truyền thêm GraphQLContext, Locale và CoercedVariables. Khi tự cài đặt, hãy dùng đúng chữ ký của phiên bản GraphQL Java mà dự án đang quản lý. Nếu chỉ cần UUID chuẩn, ExtendedScalars.UUID thường giúp tránh phần tương thích API này.

## 6. Sử dụng UUID trong controller và Java domain

Khi scalar parse thành java.util.UUID, controller có thể nhận trực tiếp kiểu Java này qua @Argument.

Schema:

~~~graphql
scalar UUID

type User {
    id: UUID!
    displayName: String!
}

type Query {
    user(id: UUID!): User
}
~~~

Controller:

~~~java
import java.util.UUID;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class UserController {

    private final UserService userService;

    UserController(UserService userService) {
        this.userService = userService;
    }

    @QueryMapping
    User user(@Argument("id") UUID id) {
        return userService.findById(id);
    }
}
~~~

Client operation:

~~~graphql
query FindUser($id: UUID!) {
    user(id: $id) {
        id
        displayName
    }
}
~~~

Variables:

~~~json
{
    "id": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Scalar coercing chuyển JSON string thành UUID trước khi resolver sử dụng argument. Service có thể làm việc với UUID trực tiếp thay vì lặp lại logic parse chuỗi.

### 6.1. Dùng UUID trong input object

Schema:

~~~graphql
input CreateUserInput {
    externalId: UUID
    displayName: String!
}

type Mutation {
    createUser(input: CreateUserInput!): User!
}
~~~

Java record:

~~~java
import java.util.UUID;

public record CreateUserInput(
        UUID externalId,
        String displayName) {
}
~~~

Controller:

~~~java
@MutationMapping
User createUser(@Argument("input") CreateUserInput input) {
    return userService.create(input);
}
~~~

Việc bind thành công phụ thuộc scalar coercing trả về kiểu Java tương thích và cấu trúc DTO phù hợp với input object. Với thư viện extended scalars, hãy xác nhận kiểu Java mà scalar UUID trả về theo phiên bản thư viện đang dùng.

### 6.2. UUID trong entity và repository

Nếu domain model dùng UUID:

~~~java
public record User(
        UUID id,
        String displayName) {
}
~~~

Repository/service có thể nhận cùng kiểu:

~~~java
interface UserRepository {
    Optional<User> findById(UUID id);
}
~~~

~~~java
@Service
class UserService {

    private final UserRepository userRepository;

    UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    User findById(UUID id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id));
    }
}
~~~

Cách dùng cùng một kiểu UUID từ GraphQL boundary đến domain giúp giảm chuyển đổi chuỗi qua lại. Nếu hệ thống persistence dùng kiểu khác, việc chuyển đổi nên được đặt ở repository hoặc adapter tương ứng.

## 7. UUID ở input và output có cùng quy tắc không?

Một scalar có thể áp dụng coercion cho cả input và output, nhưng cần xem riêng hai chiều.

### 7.1. Input coercion

Input đến từ hai nguồn:

- Variables, thường là JSON string.
- Literal trong GraphQL document, cũng là string literal.

Ví dụ variables:

~~~json
{
    "id": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Ví dụ literal:

~~~graphql
query {
    user(id: "550e8400-e29b-41d4-a716-446655440000") {
        displayName
    }
}
~~~

Cả hai cần được kiểm tra theo cùng quy tắc UUID.

### 7.2. Output serialization

Resolver có thể trả về java.util.UUID. Scalar chuyển giá trị đó thành chuỗi để đưa vào response:

~~~json
{
    "data": {
        "user": {
            "id": "550e8400-e29b-41d4-a716-446655440000"
        }
    }
}
~~~

Nếu resolver trả về một kiểu không được scalar hỗ trợ, serialization có thể thất bại khi GraphQL thực thi field. Hãy giữ kiểu trả về nhất quán trong domain và scalar implementation.

### 7.3. Không biến scalar thành nơi truy vấn database

Scalar chỉ kiểm tra và chuyển đổi biểu diễn của một giá trị. Nó không nên truy vấn database để xác minh UUID có tồn tại hay không.

Ví dụ:

- Scalar xác minh chuỗi có thể parse thành UUID.
- Resolver hoặc service tìm user theo UUID.
- Service áp dụng quy tắc nghiệp vụ và quyền truy cập.

Giữ đúng ranh giới này giúp scalar có thể tái sử dụng ở nhiều field mà không phụ thuộc vào database hoặc service cụ thể.

## 8. Kiểm thử UUID scalar

Cần kiểm thử cả trường hợp hợp lệ và không hợp lệ ở mức GraphQL execution.

### 8.1. Kiểm thử UUID hợp lệ

Ví dụ dùng GraphQlTester đã được cấu hình cho ứng dụng:

~~~java
graphQlTester.document("""
        query FindUser($id: UUID!) {
            user(id: $id) {
                id
                displayName
            }
        }
        """)
        .variable("id", "550e8400-e29b-41d4-a716-446655440000")
        .execute()
        .path("user.id")
        .entity(String.class)
        .isEqualTo("550e8400-e29b-41d4-a716-446655440000");
~~~

Test xác minh variable UUID được coercion và response được serialize thành chuỗi như mong đợi.

### 8.2. Kiểm thử UUID sai định dạng

~~~java
graphQlTester.document("""
        query FindUser($id: UUID!) {
            user(id: $id) {
                id
            }
        }
        """)
        .variable("id", "not-a-uuid")
        .execute()
        .errors()
        .verify();
~~~

Test xác minh giá trị không phải UUID bị từ chối trong quá trình coercion. Nếu cần kiểm tra chi tiết hơn, có thể kiểm tra error message hoặc error classification theo hợp đồng lỗi mà ứng dụng công bố.

### 8.3. Kiểm thử literal

Ngoài variables, cần kiểm tra scalar parse literal:

~~~graphql
query {
    user(id: "550e8400-e29b-41d4-a716-446655440000") {
        id
    }
}
~~~

Một scalar chỉ parse variables nhưng không parse literal đúng cách sẽ tạo ra hành vi không nhất quán giữa hai kiểu operation. Khi dùng extended scalars, thư viện đã cung cấp logic coercion cho các đường này; test tích hợp giúp xác minh việc đăng ký scalar đã được áp dụng.

### 8.4. Các trường hợp nên có trong test

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| UUID hợp lệ qua variable | Resolver nhận UUID và response trả chuỗi UUID |
| UUID hợp lệ qua literal | Operation được thực thi |
| Chuỗi sai định dạng | Coercion error |
| Number truyền vào UUID scalar | Bị từ chối nếu scalar yêu cầu string |
| Argument UUID! bị thiếu | Validation/coercion error |
| Argument UUID! nhận null | Coercion error |
| Field output trả UUID | Serialize thành chuỗi |
| Field output trả kiểu không hỗ trợ | Serialization error |
| UUID hợp lệ nhưng không có user | Resolver/service xử lý trường hợp không tìm thấy |

Không nên gộp lỗi định dạng UUID với lỗi không tìm thấy đối tượng. Hai trường hợp xảy ra ở hai tầng khác nhau và cần được quan sát, xử lý riêng.

## 9. Xử lý lỗi và thông điệp coercion

Khi UUID không hợp lệ, scalar nên phát sinh lỗi coercion để GraphQL runtime báo rằng input không đáp ứng kiểu đã khai báo.

Ví dụ thông báo có thể nêu:

~~~text
Invalid UUID value
~~~

Thông báo lỗi công khai nên đủ để client biết dữ liệu đầu vào sai. Không đưa stack trace, tên package nội bộ hoặc thông tin hệ thống vào message.

Nếu UUID hợp lệ về cú pháp nhưng không tồn tại trong hệ thống, đây là lỗi nghiệp vụ của resolver hoặc service. Ứng dụng có thể ánh xạ exception thành GraphQL error bằng DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler.

Ví dụ phân biệt:

| Tình huống | Tầng phát hiện |
| --- | --- |
| "not-a-uuid" | Scalar coercion |
| UUID đúng định dạng nhưng không có user | Resolver/service |
| UUID có user nhưng người gọi không có quyền | Authorization |
| Database không truy cập được | Infrastructure/service error |

Phân loại đúng giúp API trả lỗi phù hợp và log có đủ thông tin để điều tra mà không làm lộ dữ liệu nội bộ.

## 10. Bảo mật khi dùng UUID làm định danh

UUID thường khó đoán hơn một số định danh tuần tự, nhưng không phải cơ chế authorization.

Không được giả định rằng người dùng có thể truy cập tài nguyên chỉ vì họ biết UUID của tài nguyên đó. Resolver hoặc service vẫn phải kiểm tra quyền.

Ví dụ:

~~~java
@QueryMapping
User user(@Argument("id") UUID id) {
    User user = userService.findById(id);
    authorizationService.checkCanViewUser(user);
    return user;
}
~~~

Ngoài ra:

- Không xem UUID là secret hoặc access token.
- Không đưa UUID nhạy cảm vào log nếu không cần thiết.
- Không cho phép client tự chọn tenant hoặc owner UUID mà không kiểm tra quyền.
- Giới hạn kích thước list UUID để tránh request quá lớn.
- Dùng parameter binding trong truy vấn persistence.
- Xác định rõ UUID version và cách sinh UUID nếu có yêu cầu bảo mật hoặc phân tán cụ thể.

UUID v4 thường được tạo ngẫu nhiên; UUID v7 có cấu trúc hỗ trợ sắp xếp theo thời gian. Việc chọn version phụ thuộc yêu cầu hệ thống, nhưng scalar kiểm tra cú pháp không tự chứng minh nguồn sinh UUID là an toàn.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Unknown type UUID | SDL dùng UUID nhưng chưa khai báo scalar UUID | Thêm khai báo scalar vào schema |
| UUID input bị coercion error | Scalar chưa được đăng ký hoặc chuỗi sai định dạng | Kiểm tra RuntimeWiringConfigurer và giá trị đầu vào |
| ID chấp nhận chuỗi không phải UUID | ID không kiểm tra định dạng UUID | Dùng custom scalar UUID nếu hợp đồng yêu cầu |
| Controller nhận kiểu không mong muốn | Scalar implementation trả về kiểu Java khác DTO mong đợi | Kiểm tra kiểu parseValue và argument binding |
| UUID output serialization thất bại | Resolver trả kiểu mà scalar không hỗ trợ | Trả java.util.UUID hoặc kiểu được scalar hỗ trợ |
| Literal chạy nhưng variables lỗi (hoặc ngược lại) | parseLiteral và parseValue không nhất quán | Kiểm thử cả hai đường coercion |
| Không tìm thấy user dù UUID hợp lệ | UUID không tương ứng bản ghi hiện có | Xử lý ở service/resolver |
| Người dùng đọc được tài nguyên của người khác | Chỉ kiểm tra UUID mà không kiểm tra quyền | Thực hiện authorization theo người dùng và tài nguyên |

## 12. Quy trình đưa UUID scalar vào ứng dụng

Khi thêm UUID scalar vào Spring for GraphQL, hãy thực hiện theo trình tự:

1. **Xác định hợp đồng.** Quyết định API thực sự cần UUID hay chỉ cần một identifier opaque kiểu ID.
2. **Khai báo SDL.** Thêm scalar UUID và dùng ở field, argument hoặc input object phù hợp.
3. **Chọn implementation.** Ưu tiên scalar đã được kiểm thử như ExtendedScalars.UUID nếu không có quy tắc riêng.
4. **Đăng ký runtime wiring.** Dùng RuntimeWiringConfigurer và bảo đảm tên scalar trùng với SDL.
5. **Chọn kiểu Java.** Dùng java.util.UUID xuyên suốt boundary, service và domain khi phù hợp.
6. **Kiểm tra coercion.** Thử literal, variables, UUID hợp lệ, sai định dạng và giá trị null.
7. **Kiểm tra serialization.** Bảo đảm output UUID được chuyển thành chuỗi chuẩn.
8. **Kiểm tra nghiệp vụ.** Phân biệt sai định dạng, không tìm thấy đối tượng và không có quyền.
9. **Kiểm thử tích hợp.** Xác minh scalar đã được đăng ký trong GraphQL runtime của ứng dụng.
10. **Theo dõi tương thích.** Khi nâng cấp GraphQL Java hoặc extended scalars, kiểm tra lại dependency compatibility và test coercion.

## 13. Tổng kết

GraphQL không có scalar UUID dựng sẵn. Khi UUID là một phần của hợp đồng API, hãy khai báo scalar UUID trong SDL và đăng ký một coercing implementation để xử lý input và output. ID phù hợp với định danh opaque; String dành cho văn bản; UUID scalar giúp thể hiện và kiểm tra định dạng UUID rõ ràng.

Trong Spring for GraphQL, có thể dùng graphql-java-extended-scalars với RuntimeWiringConfigurer để đăng ký ExtendedScalars.UUID, sau đó bind vào java.util.UUID bằng @Argument hoặc input DTO. Scalar chỉ chịu trách nhiệm parse, validate hình thức và serialize; việc tìm đối tượng, kiểm tra quyền và xử lý nghiệp vụ vẫn thuộc resolver/service. Kiểm thử cả variables, literal, nullability và output giúp bảo đảm UUID hoạt động nhất quán trong toàn bộ GraphQL API.

