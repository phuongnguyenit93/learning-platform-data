# Mutation cập nhật resource

Trong Spring for GraphQL, mutation là nhóm operation dùng để thay đổi trạng thái dữ liệu phía server. Một thao tác cập nhật resource thường nhận định danh của đối tượng cùng dữ liệu cần thay đổi, kiểm tra quyền và quy tắc nghiệp vụ, lưu thay đổi trong transaction rồi trả về resource sau cập nhật.

Spring for GraphQL ánh xạ field thuộc root type Mutation vào method Java bằng **@MutationMapping**. Thiết kế mutation cần làm rõ thao tác cập nhật toàn bộ hay cập nhật một phần, cách xử lý field bị bỏ qua hoặc gửi null, cách báo lỗi và cách bảo đảm dữ liệu nhất quán khi nhiều request cập nhật cùng lúc.

## 1. Mutation cập nhật resource là gì?

GraphQL phân biệt ba loại root operation:

- **Query** dùng để đọc dữ liệu.
- **Mutation** dùng để thay đổi trạng thái dữ liệu.
- **Subscription** dùng để nhận các sự kiện hoặc kết quả được phát ra theo thời gian.

Một mutation cập nhật resource thường có các bước:

1. Nhận ID hoặc khóa định danh resource.
2. Nhận dữ liệu đầu vào mô tả các thay đổi.
3. Xác thực người dùng và kiểm tra quyền trên resource.
4. Tải resource hiện tại từ repository.
5. Kiểm tra dữ liệu và quy tắc nghiệp vụ.
6. Áp dụng thay đổi và lưu trong transaction.
7. Trả resource mới hoặc GraphQL error theo hợp đồng API.

Ví dụ resource Book có các thuộc tính id, title và description. Client muốn đổi title của một quyển sách:

~~~graphql
type Book {
    id: ID!
    title: String!
    description: String
}

type Mutation {
    updateBook(id: ID!, title: String!): Book!
}
~~~

Operation:

~~~graphql
mutation RenameBook($id: ID!, $title: String!) {
    updateBook(id: $id, title: $title) {
        id
        title
        description
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42",
    "title": "Spring for GraphQL"
}
~~~

Mutation không chỉ trả về thông báo thành công. Client có thể chọn ngay các field của resource sau khi cập nhật, giúp giao diện đồng bộ với trạng thái server.

## 2. Thiết kế schema cho update mutation

Khi resource có nhiều thuộc tính, nên gom dữ liệu cập nhật vào input object thay vì tạo một argument riêng cho từng thuộc tính.

Các đoạn SDL trong bài tập trung vào phần khai báo Mutation; schema hoàn chỉnh của ứng dụng vẫn cần một query root, thường là type Query.

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input UpdateBookInput {
    title: String
    description: String
    status: BookStatus
}

type Book {
    id: ID!
    title: String!
    description: String
    status: BookStatus!
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Ở đây:

- id xác định resource cần cập nhật.
- input gom các thuộc tính có thể thay đổi.
- title, description và status là nullable để client có thể không gửi field hoặc gửi null tùy quy tắc cập nhật.
- updateBook trả về Book sau khi cập nhật.

Việc để field trong input nullable không có nghĩa ứng dụng phải chấp nhận mọi giá trị null. Schema cho phép biểu diễn trạng thái đầu vào; service sẽ quyết định field nào được phép xóa, field nào bắt buộc có giá trị và field nào không được thay đổi.

### Vì sao tách ID khỏi input?

Có thể đưa id vào UpdateBookInput, nhưng tách id thành argument thường giúp ý nghĩa rõ hơn:

~~~graphql
type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

id là định danh resource mà thao tác nhắm tới. input mô tả các thay đổi. Cách tách này cũng giúp tái sử dụng input object cho các thao tác có ngữ nghĩa tương tự mà không buộc mọi input phải chứa ID.

Nếu API cần version, tenant hoặc một điều kiện cập nhật bổ sung, hãy đưa vào schema có chủ đích và xác định nguồn dữ liệu đáng tin cậy. Không sử dụng ID do client gửi như bằng chứng về quyền sở hữu resource.

## 3. Cập nhật toàn bộ và cập nhật một phần

GraphQL không tự định nghĩa mutation là PUT hay PATCH. Ý nghĩa của thao tác phụ thuộc vào schema và quy tắc nghiệp vụ mà server triển khai.

**Cập nhật toàn bộ** yêu cầu client cung cấp đầy đủ các thuộc tính cần thiết cho phiên bản resource mới. Những field bắt buộc có thể được khai báo non-null:

~~~graphql
input ReplaceBookInput {
    title: String!
    description: String
    status: BookStatus!
}

type Mutation {
    replaceBook(id: ID!, input: ReplaceBookInput!): Book!
}
~~~

Với kiểu này, client phải gửi title và status. Server có thể thay toàn bộ phần dữ liệu mà input đại diện.

**Cập nhật một phần** chỉ thay đổi những field client gửi. Field bị bỏ qua giữ nguyên giá trị hiện tại; field được gửi null có thể mang nghĩa xóa giá trị nếu nghiệp vụ cho phép.

~~~graphql
input UpdateBookInput {
    title: String
    description: String
    status: BookStatus
}
~~~

Ví dụ, chỉ đổi title:

~~~json
{
    "title": "New title"
}
~~~

Nếu gửi:

~~~json
{
    "description": null
}
~~~

thì có thể hiểu là xóa description. Quy ước này phải được tài liệu hóa và kiểm thử. Không nên để client phải đoán ý nghĩa của null.

Với input dành cho partial update, tránh đặt default value cho các field mà server cần biết chính xác client có gửi hay không. Default có thể làm field bị bỏ qua trở thành một giá trị mặc định trong quá trình GraphQL xử lý input, khiến ứng dụng không còn phân biệt được ý định của client.

## 4. Phân biệt field bị bỏ qua và field có giá trị null

Đây là điểm quan trọng nhất khi triển khai partial update.

Xét input:

~~~graphql
input UpdateBookInput {
    title: String
    description: String
}
~~~

Hai request sau mang ý nghĩa khác nhau:

Không gửi description:

~~~json
{
    "title": "New title"
}
~~~

Gửi description với null:

~~~json
{
    "title": "New title",
    "description": null
}
~~~

Quy ước thường dùng:

| Trạng thái input | Ý nghĩa trong partial update |
| --- | --- |
| Field bị bỏ qua | Giữ nguyên giá trị hiện tại. |
| Field có giá trị | Cập nhật sang giá trị mới. |
| Field được gửi null | Xóa giá trị nếu field cho phép null; nếu không thì từ chối. |

Nếu bind input vào Java record với thuộc tính String thông thường, cả field bị bỏ qua và field gửi null có thể cùng trở thành Java null. Khi đó service không biết client muốn giữ nguyên hay xóa dữ liệu.

Spring for GraphQL cung cấp **ArgumentValue<T>** để giữ sự khác biệt này. Wrapper cho biết argument hoặc field input bị bỏ qua hay được gửi tường minh.

~~~java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> description,
        ArgumentValue<BookStatus> status
) {
}
~~~

Trong service hoặc controller, kiểm tra trạng thái trước khi đọc value:

~~~java
if (!input.title().isOmitted()) {
    String title = input.title().value();

    if (title == null || title.isBlank()) {
        throw new InvalidBookInputException("Title must not be blank");
    }

    book.rename(title);
}

if (!input.description().isOmitted()) {
    book.changeDescription(input.description().value());
}
~~~

Ở ví dụ này:

- title bị bỏ qua thì không thay đổi.
- title có chuỗi hợp lệ thì đổi title.
- title được gửi null bị từ chối bởi quy tắc nghiệp vụ.
- description bị bỏ qua thì giữ nguyên.
- description được gửi null thì xóa description.

ArgumentValue cũng hữu ích cho field trong input object lồng nhau. Hãy kiểm thử binding với phiên bản Spring for GraphQL mà dự án sử dụng để bảo đảm DTO phản ánh đúng cấu trúc input.

## 5. Ánh xạ mutation bằng @MutationMapping

Spring for GraphQL dùng @MutationMapping để nối method Java với field cùng tên trên root type Mutation.

Schema:

~~~graphql
type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Controller:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookService;
import com.example.catalog.book.UpdateBookInput;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input) {
        return bookService.update(id, input);
    }
}
~~~

Các điểm chính:

- @Controller đăng ký class với Spring.
- @MutationMapping ánh xạ method updateBook tới Mutation.updateBook.
- @Argument("id") lấy ID resource.
- @Argument("input") bind input object vào Java DTO.
- Giá trị method trả về được GraphQL engine hoàn thành theo selection set client yêu cầu.

Nếu tên method khác tên field SDL, chỉ rõ tên bằng thuộc tính name:

~~~java
@MutationMapping(name = "updateBook")
public Book applyBookChanges(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {
    return bookService.update(id, input);
}
~~~

@MutationMapping là cách viết chuyên biệt cho field của root Mutation. Nếu schema dùng một tên root mutation tùy chỉnh, có thể dùng @SchemaMapping với typeName tương ứng.

## 6. Triển khai cập nhật trong service và transaction

Controller nên nhận dữ liệu và chuyển cho service. Service tải resource hiện tại, kiểm tra quy tắc nghiệp vụ, áp dụng thay đổi và lưu.

Ví dụ service:

~~~java
package com.example.catalog.book;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public Book update(String id, UpdateBookInput input) {
        BookEntity entity = bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));

        if (!input.title().isOmitted()) {
            String title = input.title().value();

            if (title == null || title.isBlank()) {
                throw new InvalidBookInputException(
                        "Title must not be blank");
            }

            entity.setTitle(title);
        }

        if (!input.description().isOmitted()) {
            entity.setDescription(input.description().value());
        }

        if (!input.status().isOmitted()) {
            BookStatus status = input.status().value();

            if (status == null) {
                throw new InvalidBookInputException(
                        "Status must not be null");
            }

            entity.setStatus(status);
        }

        BookEntity saved = bookRepository.save(entity);
        return BookMapper.toModel(saved);
    }
}
~~~

Đây là ví dụ minh họa; BookEntity, repository, mapper và exception cần được định nghĩa theo mô hình của ứng dụng.

@Transactional đặt ở service giúp thao tác tải, kiểm tra và lưu resource nằm trong cùng transaction. Nếu một bước thất bại và exception làm transaction rollback theo cấu hình, thay đổi chưa hoàn tất sẽ không được commit một phần.

Một số lưu ý:

- Không mở transaction chỉ để bao quanh việc parse GraphQL document; transaction nên bao quanh thao tác nghiệp vụ cần tính nguyên tử.
- Chọn rollback policy phù hợp nếu ứng dụng dùng checked exception.
- Không giữ transaction mở trong lúc chờ một tác vụ từ xa kéo dài nếu không cần thiết.
- Không trả entity JPA trực tiếp nếu việc đó làm lộ quan hệ hoặc dữ liệu nội bộ; có thể chuyển sang DTO/output model.
- Với nhiều resource liên quan, xác định rõ ranh giới transaction và thứ tự cập nhật.

## 7. Validation đầu vào và quy tắc nghiệp vụ

GraphQL kiểm tra kiểu dữ liệu và cấu trúc input trước khi gọi resolver. Tuy nhiên, schema không thể thay thế validation nghiệp vụ.

Ví dụ, SDL có thể khai báo:

~~~graphql
input UpdateBookInput {
    title: String
    description: String
}
~~~

GraphQL xác nhận title là String hoặc null, nhưng không tự biết title có được phép rỗng hay dài quá 200 ký tự hay không.

Service cần kiểm tra:

~~~java
private void validateTitle(String title) {
    if (title == null || title.isBlank()) {
        throw new InvalidBookInputException("Title must not be blank");
    }

    if (title.length() > 200) {
        throw new InvalidBookInputException("Title is too long");
    }
}
~~~

Các quy tắc thường cần kiểm tra khi cập nhật:

- Resource có tồn tại không.
- Người dùng có quyền cập nhật resource không.
- Có ít nhất một field thay đổi hay không.
- Field có giá trị null có được phép xóa không.
- Chuỗi có rỗng hoặc vượt giới hạn không.
- Trạng thái mới có hợp lệ với trạng thái hiện tại không.
- Resource có đang ở trạng thái khóa hoặc đã hoàn tất không.
- Giá trị tham chiếu như authorId có tồn tại và được phép sử dụng không.

Có thể kết hợp Jakarta Bean Validation với constraint như @NotBlank, @Size, @Min và @Max. Với partial update, cần chú ý constraint chỉ áp dụng cho field thực sự được gửi; validation trên DTO thông thường có thể chưa diễn đạt đủ ngữ nghĩa omitted/null. Quy tắc cuối cùng vẫn cần được thực thi ở service.

## 8. Xử lý resource không tồn tại và lỗi cập nhật

Khi ID không tồn tại, service có thể ném exception nghiệp vụ:

~~~java
BookEntity entity = bookRepository.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
~~~

Spring for GraphQL cho phép chuyển exception thành GraphQL error bằng @GraphQlExceptionHandler.

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .message("Không tìm thấy sách")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleInvalidInput(
            InvalidBookInputException exception) {
        return GraphqlErrorBuilder.newError()
                .message(exception.getMessage())
                .errorType(ErrorType.BAD_REQUEST)
                .build();
    }
}
~~~

Client có thể nhận response có errors khi cập nhật thất bại. Nếu field mutation được khai báo non-null, lỗi thực thi có thể lan truyền null lên root data. Vì vậy, cần thiết kế nullability và error contract nhất quán.

Không trả stack trace, SQL, tên bảng hoặc thông tin nội bộ trong error message. Log chi tiết ở server; response chỉ nên chứa thông tin cần thiết để client xử lý.

Phân biệt các trường hợp:

| Trường hợp | Cách xử lý thường dùng |
| --- | --- |
| ID không tồn tại | NOT_FOUND hoặc kết quả nullable theo hợp đồng API. |
| Input sai quy tắc | BAD_REQUEST hoặc lỗi validation có mã rõ ràng. |
| Không có quyền cập nhật | FORBIDDEN hoặc UNAUTHORIZED theo tình huống. |
| Xung đột phiên bản | CONFLICT hoặc mã lỗi nghiệp vụ tương ứng. |
| Database hoặc dịch vụ gặp sự cố | INTERNAL_ERROR với thông điệp an toàn. |

Không chuyển mọi exception thành BAD_REQUEST hoặc NOT_FOUND. Phân loại đúng giúp client biết có nên sửa input, đăng nhập lại, yêu cầu quyền hay thử lại sau.

## 9. Bảo mật mutation cập nhật resource

Mutation có thể thay đổi dữ liệu quan trọng, vì vậy phải kiểm tra quyền ở server. Không được tin ID, ownerId hoặc tenantId mà client gửi như bằng chứng về quyền sở hữu.

Có thể dùng Spring Security method security:

~~~java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_UPDATE')")
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {
    return bookService.updateForCurrentUser(id, input);
}
~~~

Ngoài quyền chung BOOK_UPDATE, service cần kiểm tra người dùng hiện tại có quyền sửa chính quyển sách được chỉ định hay không. Ví dụ, người dùng chỉ được sửa sách thuộc tenant hoặc nhóm mà họ quản lý.

Một số nguyên tắc:

- Lấy user identity từ security context phía server.
- Kiểm tra quyền trên resource sau khi tải resource.
- Chỉ cho phép thay đổi những field được nghiệp vụ cho phép.
- Không bind trực tiếp mọi field của entity từ client.
- Không cho client tự đặt role, owner hoặc trạng thái nội bộ nếu họ không có quyền.
- Không để error message tiết lộ dữ liệu nhạy cảm.

Đặc biệt, input object không nên phản chiếu toàn bộ entity persistence. Tạo UpdateBookInput chỉ gồm các field client được phép cập nhật giúp giảm nguy cơ mass assignment.

## 10. Xử lý cập nhật đồng thời và optimistic locking

Hai client có thể cùng đọc một resource rồi gửi mutation cập nhật gần như đồng thời. Nếu server không kiểm soát, lần ghi sau có thể ghi đè thay đổi của lần ghi trước.

Một cách xử lý là optimistic locking. Với JPA, entity có thể dùng trường version:

~~~java
@Entity
public class BookEntity {

    @Id
    private String id;

    @Version
    private Integer version;

    private String title;
}
~~~

Schema có thể yêu cầu client gửi version mà họ đã đọc:

~~~graphql
input UpdateBookInput {
    title: String
    expectedVersion: Int!
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

DTO của mutation cần có thêm thuộc tính expectedVersion tương ứng với input schema. Service so sánh version client đã đọc với version hiện tại trước khi áp dụng thay đổi:

~~~java
if (!Objects.equals(entity.getVersion(), input.expectedVersion())) {
    throw new BookVersionConflictException(id);
}
~~~

Phép so sánh này phát hiện client đang cập nhật trên dữ liệu cũ. Annotation @Version của JPA vẫn cần thiết để xử lý cuộc đua có thể xảy ra sau phép so sánh nhưng trước lúc ghi xuống database. Nếu resource đã được một request khác cập nhật trước, thao tác lưu có thể thất bại với optimistic locking exception.

Ứng dụng nên chuyển xung đột đó thành GraphQL error có ý nghĩa, ví dụ mã RESOURCE_VERSION_CONFLICT. Client có thể tải lại resource và quyết định áp dụng thay đổi trên phiên bản mới.

Không nên chỉ dựa vào việc đọc version rồi so sánh trong Java nếu thao tác đọc và ghi không được bảo vệ bởi cơ chế concurrency phù hợp; hai request vẫn có thể vượt qua phép so sánh cùng lúc. Dùng optimistic locking ở database hoặc một cơ chế đồng bộ hóa tương ứng để bảo đảm tính đúng đắn.

Các field top-level của một mutation operation được GraphQL thực thi tuần tự trong cùng operation. Điều đó không ngăn hai HTTP request độc lập cập nhật cùng resource đồng thời. Transaction và concurrency control vẫn cần thiết.

## 11. Mutation response và dữ liệu client nhận được

Một mutation thường trả resource sau khi cập nhật để client có thể cập nhật cache hoặc giao diện.

~~~graphql
mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
    updateBook(id: $id, input: $input) {
        id
        title
        description
        status
    }
}
~~~

Client chỉ nhận các field được chọn. Nếu response cần thêm thông tin như thời điểm cập nhật hoặc version mới, có thể mở rộng output type hoặc trả một payload riêng:

~~~graphql
type UpdateBookPayload {
    book: Book!
    updatedAt: String!
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): UpdateBookPayload!
}
~~~

Payload hữu ích khi mutation cần trả nhiều thông tin ngoài resource, chẳng hạn version, warning hoặc kết quả phụ. Không cần tạo payload riêng nếu chỉ trả một object là đủ.

Mutation response không tự động cập nhật cache phía client. Client cần dùng dữ liệu trả về để cập nhật cache hoặc thực hiện query tải lại theo chiến lược của framework.

## 12. Kiểm thử update mutation bằng GraphQlTester

Spring for GraphQL cung cấp GraphQlTester để kiểm thử operation và response.

Ví dụ test cập nhật title:

~~~java
@Test
void updatesBookTitle() {
    graphQlTester.document("""
            mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
                updateBook(id: $id, input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("id", "book-42")
        .variable("input", Map.of("title", "New title"))
        .execute()
        .path("updateBook.title")
        .entity(String.class)
        .isEqualTo("New title");
}
~~~

Ngoài trường hợp thành công, cần kiểm thử các trường hợp:

- ID không tồn tại.
- Input không có field nào được gửi.
- Field bị bỏ qua giữ nguyên dữ liệu.
- Field nullable được gửi null sẽ xóa giá trị theo quy ước.
- Field không được phép null bị gửi null thì bị từ chối.
- Title rỗng hoặc quá dài.
- Enum hoặc trạng thái chuyển đổi không hợp lệ.
- Người dùng không có quyền cập nhật resource.
- Hai request cập nhật cùng version tạo xung đột đúng cách.
- Lỗi persistence không làm lưu một phần dữ liệu.

### Kiểm thử omitted và null riêng biệt

Trường hợp bỏ qua description:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("title", "New title");
~~~

Trường hợp gửi description null:

~~~java
Map<String, Object> input = new HashMap<>();
input.put("description", null);
~~~

Hai map có cấu trúc khác nhau. Dùng chúng trong test riêng để xác nhận ArgumentValue phân biệt được omitted và explicit null, đồng thời service giữ nguyên hoặc xóa dữ liệu đúng quy ước.

Test slice có thể dùng @GraphQlTest cùng mock service hoặc test bean. Với kiểm thử tích hợp, dùng @SpringBootTest và database test để xác nhận transaction, rollback và optimistic locking.

## 13. Các lỗi thường gặp khi triển khai update mutation

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Mutation không được tìm thấy | Schema chưa khai báo field hoặc method không được mapping đúng. | Kiểm tra type Mutation và @MutationMapping. |
| Argument input không bind được | Tên hoặc kiểu DTO không khớp SDL. | Đối chiếu @Argument, input object và Java record/class. |
| Field bị bỏ qua lại bị ghi thành null | DTO không phân biệt omitted với explicit null. | Dùng ArgumentValue<T> hoặc cơ chế binding giữ trạng thái hiện diện. |
| Không thể xóa giá trị nullable | Service bỏ qua cả explicit null. | Kiểm tra isOmitted() rồi xử lý value() == null như thao tác xóa. |
| Field bắt buộc bị xóa | Schema cho phép null nhưng service chưa validate. | Kiểm tra quy tắc nghiệp vụ trước khi lưu. |
| Resource không tồn tại nhưng trả lỗi chung | Exception không được phân loại. | Dùng exception nghiệp vụ và GraphQL exception handler. |
| Cập nhật mất dữ liệu của request khác | Không có concurrency control. | Dùng optimistic locking hoặc cơ chế khóa phù hợp. |
| Một phần thay đổi đã được lưu khi thao tác lỗi | Transaction không bao phủ toàn bộ cập nhật. | Đặt transaction ở service và xác định rollback policy. |
| Client gửi field nội bộ để thay đổi | Input phản chiếu entity quá rộng. | Tạo input DTO chỉ chứa field được phép cập nhật. |
| Mutation thành công nhưng UI vẫn cũ | Client không cập nhật cache từ response. | Chọn field trả về và cập nhật cache hoặc tải lại resource. |

Khi debug, kiểm tra schema trước, sau đó kiểm tra argument binding và trạng thái omitted/null. Tiếp theo xem validation, quyền truy cập, transaction và kết quả persistence. Nếu lỗi chỉ xảy ra khi nhiều người dùng cập nhật đồng thời, kiểm tra version và concurrency control.

## 14. Quy trình thiết kế một update mutation

Khi bổ sung thao tác cập nhật resource, hãy đi theo trình tự:

1. Xác định resource và field nào được phép thay đổi.
2. Chọn ngữ nghĩa thay toàn bộ hay cập nhật một phần.
3. Khai báo UpdateInput với nullability và default phù hợp.
4. Quy định rõ omitted, explicit null và giá trị mới có ý nghĩa gì.
5. Ánh xạ field bằng @MutationMapping và bind argument bằng @Argument.
6. Dùng ArgumentValue nếu cần phân biệt omitted và null.
7. Tải resource hiện tại, kiểm tra quyền và validation trong service.
8. Thực hiện cập nhật trong transaction.
9. Dùng optimistic locking hoặc cơ chế phù hợp nếu có cập nhật đồng thời.
10. Trả resource hoặc payload theo hợp đồng GraphQL.
11. Ánh xạ exception sang GraphQL error an toàn.
12. Kiểm thử thành công, lỗi, omitted/null, authorization và concurrency.

## 15. Những điểm cần ghi nhớ

- Mutation là operation dùng để thay đổi trạng thái dữ liệu; @MutationMapping ánh xạ method Java vào field của root Mutation.
- Input object gom các field có thể cập nhật; ID xác định resource cần thay đổi.
- GraphQL không tự quyết định update là thay toàn bộ hay partial update; schema và nghiệp vụ phải định nghĩa rõ.
- Với partial update, field bị bỏ qua thường giữ nguyên, còn explicit null có thể xóa giá trị nếu được phép.
- ArgumentValue<T> giúp phân biệt omitted và null khi bind input trong Spring for GraphQL.
- Service nên kiểm tra resource, validation, authorization và lưu thay đổi trong transaction.
- Optimistic locking giúp phát hiện cập nhật đồng thời và tránh ghi đè âm thầm.
- Exception cần được chuyển thành GraphQL error có mã và thông điệp phù hợp.
- Input DTO chỉ nên chứa field mà client được phép cập nhật.
- GraphQlTester có thể kiểm tra cả response và khác biệt giữa omitted/null.

Mutation cập nhật resource là nơi schema GraphQL gặp trực tiếp quy tắc nghiệp vụ và tính nhất quán dữ liệu. Khi thiết kế rõ ngữ nghĩa update, giữ được khác biệt giữa field bị bỏ qua và null, đồng thời kiểm tra quyền, transaction và concurrency ở server, ứng dụng Spring for GraphQL sẽ có API cập nhật dễ hiểu và đáng tin cậy.

