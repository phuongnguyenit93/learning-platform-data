# Mutation xóa resource

Trong GraphQL, mutation xóa resource là một command yêu cầu server loại bỏ hoặc đánh dấu không còn hoạt động một tài nguyên, ví dụ xóa sách, hủy đơn nháp hoặc gỡ một địa chỉ giao hàng. Với Spring for GraphQL, field trong root type `Mutation` được ánh xạ tới method Java bằng `@MutationMapping`; method thường ủy quyền thao tác cho service để kiểm tra quyền, bảo vệ ràng buộc dữ liệu và thực hiện thay đổi trong transaction.

Thiết kế một mutation xóa cần trả lời rõ ba câu hỏi: tài nguyên nào được xóa, điều kiện nào cho phép xóa và client nhận được thông tin gì sau khi thao tác hoàn tất. Việc xóa một dòng dữ liệu thường đơn giản về mặt code, nhưng có thể ảnh hưởng đến quan hệ, lịch sử, audit và các quy trình nghiệp vụ khác.

## 1. Khai báo mutation xóa trong schema SDL

Giả sử ứng dụng thư viện cho phép xóa một cuốn sách theo ID. Schema tối thiểu:

```graphql
type Mutation {
    deleteBook(id: ID!): Boolean!
}
```

Field `deleteBook` nhận ID bắt buộc và trả về một Boolean khác null. Một hợp đồng như vậy có thể đủ nếu client chỉ cần biết thao tác thành công hay thất bại. Tuy nhiên, Boolean không cho biết ID nào đã bị xóa, vì sao tài nguyên không thể xóa hoặc client cần cập nhật danh sách nào.

Với API thực tế, một payload thường hữu ích hơn:

```graphql
type Mutation {
    deleteBook(id: ID!): DeleteBookPayload!
}

type DeleteBookPayload {
    deleted: Boolean!
    deletedId: ID
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
}
```

Payload này luôn được trả về nếu command được xử lý theo các kết quả nghiệp vụ dự kiến. Khi xóa thành công, `deleted` là `true`, `deletedId` chứa ID vừa xóa và `userErrors` rỗng. Khi resource không tồn tại hoặc không thỏa điều kiện xóa, `deleted` là `false`, `deletedId` là null và `userErrors` mô tả vấn đề an toàn để client xử lý.

`DeleteBookPayload!` cam kết mutation luôn trả về payload. Vì vậy, không trả null từ resolver cho trường hợp thất bại dự kiến; hãy tạo payload có trạng thái rõ ràng. Lỗi ngoài dự kiến như database không khả dụng hoặc lỗi lập trình vẫn có thể đi qua GraphQL error channel.

## 2. Client gửi mutation operation

Client gọi mutation bằng operation có tên và chọn các field cần dùng từ payload:

```graphql
mutation DeleteBook($id: ID!) {
    deleteBook(id: $id) {
        deleted
        deletedId
        userErrors {
            code
            message
        }
    }
}
```

Variables:

```json
{
  "id": "book-42"
}
```

Response khi xóa thành công:

```json
{
  "data": {
    "deleteBook": {
      "deleted": true,
      "deletedId": "book-42",
      "userErrors": []
    }
  }
}
```

Response khi không tìm thấy sách:

```json
{
  "data": {
    "deleteBook": {
      "deleted": false,
      "deletedId": null,
      "userErrors": [
        {
          "code": "BOOK_NOT_FOUND",
          "message": "Không tìm thấy sách cần xóa."
        }
      ]
    }
  }
}
```

Client có thể dựa vào `deleted` để cập nhật giao diện, dùng `deletedId` để loại item khỏi cache hoặc danh sách và hiển thị lỗi từ `userErrors`. Không nên để client suy luận thành công chỉ từ việc HTTP request trả status thành công; GraphQL có thể trả response HTTP thành công nhưng trong body vẫn có `errors` hoặc kết quả nghiệp vụ thất bại.

## 3. Ánh xạ mutation với @MutationMapping

Spring for GraphQL ánh xạ method controller vào field cùng tên trên root type `Mutation` bằng `@MutationMapping`.

```java
package com.example.graphql.book;

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
    public DeleteBookPayload deleteBook(@Argument("id") String id) {
        return bookService.deleteBook(id);
    }
}
```

Method `deleteBook` được ánh xạ vào field `Mutation.deleteBook`. `@Argument("id")` lấy ID do client gửi. Dùng `String` cho ID giúp thể hiện rõ rằng GraphQL `ID` được truyền qua API như một giá trị định danh; service có thể chuyển đổi sang kiểu khóa nội bộ nếu hệ thống dùng UUID hoặc kiểu số.

Nếu tên method khác tên field, có thể chỉ định rõ tên:

```java
@MutationMapping(name = "deleteBook")
public DeleteBookPayload remove(@Argument("id") String id) {
    return bookService.deleteBook(id);
}
```

Controller chỉ nhận input và gọi service. Không nên đặt toàn bộ logic kiểm tra quyền, quan hệ dữ liệu và transaction trong controller vì cùng nghiệp vụ có thể được gọi từ REST endpoint, job nền hoặc quy trình nội bộ khác.

## 4. Đặt quy tắc xóa trong service và transaction

Ví dụ đơn giản với Spring Data JPA:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<BookEntity, String> {
}
```

DTO payload:

```java
import java.util.List;

public record UserError(String code, String message) {}

public record DeleteBookPayload(
    boolean deleted,
    String deletedId,
    List<UserError> userErrors
) {}
```

Service:

```java
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;
    private final BookAuthorizationService authorizationService;

    public BookService(
            BookRepository bookRepository,
            BookAuthorizationService authorizationService) {
        this.bookRepository = bookRepository;
        this.authorizationService = authorizationService;
    }

    @Transactional
    public DeleteBookPayload deleteBook(String id) {
        BookEntity book = bookRepository.findById(id).orElse(null);

        if (book == null) {
            return new DeleteBookPayload(
                false,
                null,
                List.of(new UserError(
                    "BOOK_NOT_FOUND",
                    "Không tìm thấy sách cần xóa."
                ))
            );
        }

        authorizationService.checkCanDelete(book);
        bookRepository.delete(book);

        return new DeleteBookPayload(true, id, List.of());
    }
}
```

`@Transactional` đặt ranh giới transaction cho việc tải resource, kiểm tra điều kiện và xóa dữ liệu. Nếu thao tác xóa vi phạm ràng buộc database hoặc phát sinh lỗi trong lúc commit, transaction có thể rollback và lỗi được chuyển lên GraphQL execution. Với code thực tế, cần điều chỉnh kiểu ID, entity và repository theo mô hình dữ liệu của ứng dụng.

Không nên gọi `deleteById(id)` một cách mù quáng nếu nghiệp vụ cần kiểm tra quyền hoặc điều kiện xóa trên entity. Tải resource trước cho phép service kiểm tra chủ sở hữu, trạng thái, quan hệ và ghi audit phù hợp trước khi thay đổi dữ liệu.

## 5. Kiểm tra quyền trước khi xóa

Biết ID của resource không có nghĩa người dùng có quyền xóa resource đó. Server phải lấy danh tính từ security context đã xác thực và kiểm tra quyền trên chính đối tượng được tải.

Ví dụ service authorization:

```java
@Service
public class BookAuthorizationService {

    public void checkCanDelete(BookEntity book) {
        // Lấy principal hiện tại từ security context.
        // Kiểm tra vai trò hoặc quyền sở hữu resource.
        // Ném AccessDeniedException nếu không được phép.
    }
}
```

Đây là phần minh họa vị trí đặt kiểm tra; nội dung cụ thể phụ thuộc cách ứng dụng cấu hình Spring Security và mô hình quyền. Không nhận `ownerId` từ client rồi tin giá trị đó để quyết định quyền xóa. Client có thể sửa variables và gọi trực tiếp GraphQL endpoint.

Với dữ liệu nhạy cảm, cần cân nhắc việc phân biệt `NOT_FOUND` và `FORBIDDEN`. Nếu tiết lộ rằng một ID tồn tại nhưng người dùng không có quyền truy cập có thể làm lộ dữ liệu, API có thể trả cùng một kết quả không tìm thấy cho cả hai trường hợp. Chính sách này phải nhất quán với mô hình bảo mật của hệ thống.

Không dùng directive, alias hoặc việc ẩn nút xóa trên giao diện làm cơ chế authorization. Quyền phải được thực thi phía server ở resolver/service hoặc data access boundary phù hợp.

## 6. Phân biệt hard delete và soft delete

Xóa resource có thể mang hai ý nghĩa khác nhau.

| Cách xóa | Hành vi | Phù hợp khi |
| --- | --- | --- |
| Hard delete | Xóa bản ghi khỏi database hoặc nguồn dữ liệu chính | Resource có thể loại bỏ vĩnh viễn và không cần phục hồi |
| Soft delete | Đánh dấu resource đã xóa, ví dụ `deletedAt` hoặc `status = DELETED` | Cần audit, phục hồi, lưu lịch sử hoặc đáp ứng chính sách lưu trữ |

Hard delete không tự động xóa an toàn mọi dữ liệu liên quan. Foreign key có thể ngăn thao tác, cascade có thể xóa thêm dữ liệu, còn các bản ghi audit hoặc lịch sử có thể cần được giữ lại. Hãy xem xét ràng buộc và vòng đời của các resource liên quan trước khi chọn cascade.

Soft delete cần được áp dụng nhất quán trong truy vấn đọc. Nếu chỉ cập nhật `deletedAt` nhưng các query thông thường vẫn trả về resource đã xóa, client có thể tiếp tục nhìn thấy dữ liệu không còn hợp lệ. Cần xác định cách lọc mặc định, quyền xem bản ghi đã xóa, khả năng khôi phục và cách xử lý unique constraint.

Ví dụ service soft delete:

```java
@Transactional
public DeleteBookPayload softDeleteBook(String id) {
    BookEntity book = bookRepository.findById(id).orElse(null);
    if (book == null || book.isDeleted()) {
        return new DeleteBookPayload(
            false,
            null,
            List.of(new UserError("BOOK_NOT_FOUND", "Không tìm thấy sách cần xóa."))
        );
    }

    authorizationService.checkCanDelete(book);
    book.markDeleted();
    return new DeleteBookPayload(true, id, List.of());
}
```

Đoạn code giả định entity có phương thức `isDeleted()` và `markDeleted()` để cập nhật trạng thái. Với soft delete, repository không gọi `delete`; thay đổi được lưu qua transaction khi entity được quản lý.

## 7. Xử lý resource không tồn tại và lỗi nghiệp vụ

API cần quyết định rõ điều gì xảy ra khi client yêu cầu xóa một ID không tồn tại. Hai kiểu hợp đồng thường gặp:

**Trả payload kết quả nghiệp vụ:** trả `deleted: false` cùng `userErrors` như ví dụ trước. Cách này hữu ích khi không tìm thấy resource là một kết quả dự kiến mà giao diện cần xử lý.

**Trả GraphQL error:** ném exception nghiệp vụ và dùng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` để chuyển thành GraphQL error có mã ổn định. Cách này phù hợp khi API coi việc không tìm thấy là lỗi thực thi của command.

Không nên vừa trả payload thất bại vừa thêm GraphQL error cho cùng một lỗi dự kiến nếu không có lý do rõ ràng. Hãy chọn một error contract nhất quán để client không phải xử lý hai nguồn lỗi cho một tình huống.

Lỗi hệ thống ngoài dự kiến như database timeout, mất kết nối hoặc lỗi lập trình thường nên đi qua GraphQL `errors`. Response có thể chứa `data` một phần tùy vị trí field và nullability. Thông điệp trả cho client không được tiết lộ SQL, stack trace, đường dẫn file hoặc thông tin hạ tầng.

Nếu dùng payload, nên có mã lỗi ổn định như `BOOK_NOT_FOUND`, `BOOK_CANNOT_BE_DELETED` hoặc `BOOK_HAS_ACTIVE_LOANS`. Client có thể dựa vào `code` để quyết định hành động; message dành cho người dùng có thể thay đổi theo ngôn ngữ.

## 8. Kiểm tra ràng buộc quan hệ và điều kiện nghiệp vụ

Một resource có thể đang được tham chiếu bởi các dữ liệu khác. Ví dụ:

- Sách đang nằm trong đơn mượn chưa trả.
- Danh mục đang được sản phẩm sử dụng.
- Người dùng đang sở hữu đơn hàng chưa hoàn tất.
- Tệp đang được một quy trình xử lý tham chiếu.

Trước khi xóa, service phải kiểm tra các điều kiện nghiệp vụ này. Không nên chỉ dựa vào việc database có cho phép xóa hay không; foreign key là lớp bảo vệ cuối cùng, không thay thế thông báo nghiệp vụ rõ ràng.

Ví dụ:

```java
if (loanRepository.existsActiveLoanForBook(id)) {
    return new DeleteBookPayload(
        false,
        null,
        List.of(new UserError(
            "BOOK_HAS_ACTIVE_LOANS",
            "Không thể xóa sách đang có lượt mượn chưa hoàn tất."
        ))
    );
}
```

Kiểm tra quan hệ phải nằm trong cùng ranh giới nhất quán phù hợp với thao tác xóa. Nếu có thể xảy ra cập nhật đồng thời, chỉ kiểm tra trước rồi xóa có thể chưa đủ. Cân nhắc transaction isolation, khóa hoặc constraint ở database tùy mức độ quan trọng của invariant.

## 9. Retry, idempotency và xóa lặp

Client có thể gửi lại mutation khi timeout hoặc mất kết nối, kể cả khi server đã thực hiện xóa nhưng response chưa đến được client. Vì vậy, cần định nghĩa hành vi khi cùng một command được gửi nhiều lần.

Với thao tác xóa đơn giản, có thể chọn một trong hai hợp đồng:

- Lần đầu xóa thành công; lần tiếp theo trả `BOOK_NOT_FOUND`.
- Nếu resource đã không tồn tại, xem trạng thái mong muốn đã đạt được và trả kết quả thành công theo chính sách idempotent của API.

Hai cách đều có thể hợp lý tùy nghiệp vụ. Điều quan trọng là client biết kết quả có thể lặp lại như thế nào. Với thao tác xóa kéo theo hoàn tiền, gửi thông báo hoặc phát sự kiện có tác dụng phụ, cần cơ chế idempotency key hoặc xử lý event chống trùng để retry không tạo tác động lặp.

GraphQL không tự cung cấp idempotency cho mutation. Tên operation, alias hoặc việc field mutation được thực thi tuần tự không ngăn client gửi lại request.

## 10. Mutation tuần tự không có nghĩa toàn operation là một transaction

Các field mutation cấp cao nhất trong cùng một GraphQL operation được thực thi tuần tự theo thứ tự xuất hiện. Ví dụ:

```graphql
mutation {
    removeDraft: deleteBook(id: "book-1") {
        deleted
    }
    removeOldCopy: deleteBook(id: "book-2") {
        deleted
    }
}
```

Field thứ hai được thực thi sau field thứ nhất. Tuy nhiên, GraphQL không tự bọc cả operation trong một transaction database. Nếu field thứ nhất xóa thành công và field thứ hai thất bại, thay đổi đầu tiên không tự động rollback.

Nếu nghiệp vụ yêu cầu nhiều bước phải nguyên tử, nên thiết kế một mutation command duy nhất, ví dụ `deleteCollection`, rồi thực hiện các thao tác trong cùng transaction/service workflow. Transaction boundary thuộc tầng nghiệp vụ và persistence, không được suy ra từ từ khóa `mutation`.

## 11. Trả về payload snapshot sau khi xóa

Một lựa chọn khác là trả về chính object vừa xóa:

```graphql
type Mutation {
    deleteBook(id: ID!): Book
}
```

Điều này có thể thuận tiện cho client, nhưng cần lưu ý: sau khi xóa, GraphQL runtime vẫn phải resolve các field mà client chọn trên object trả về. Nếu các field đó tiếp tục truy vấn database hoặc phụ thuộc quan hệ đã bị xóa, response có thể thất bại hoặc phát sinh truy vấn không cần thiết.

Với command xóa, payload snapshot thường rõ ràng hơn:

```graphql
type DeleteBookPayload {
    deleted: Boolean!
    deletedId: ID
    deletedTitle: String
    userErrors: [UserError!]!
}
```

Service có thể giữ lại ID và tiêu đề trước khi xóa rồi trả về các giá trị đó. Client nhận đủ thông tin để cập nhật giao diện mà không cần resolve lại entity đã bị xóa.

Chỉ đưa vào payload những thông tin thực sự cần thiết. Không trả lại toàn bộ entity nếu có thể chứa dữ liệu nhạy cảm hoặc các field không còn phù hợp sau thao tác.

## 12. Kiểm thử mutation xóa với GraphQlTester

`GraphQlTester` cho phép thực thi mutation và xác minh payload. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookMutationController.class)
class BookMutationControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void deletesBookAndReturnsPayload() {
        graphQlTester.document("""
                mutation DeleteBook($id: ID!) {
                    deleteBook(id: $id) {
                        deleted
                        deletedId
                        userErrors {
                            code
                        }
                    }
                }
                """)
            .variable("id", "book-42")
            .execute()
            .path("deleteBook.deleted")
            .entity(Boolean.class)
            .isEqualTo(true);
    }
}
```

Ví dụ giả định test context cung cấp `BookService` mock hoặc test bean trả payload thành công cho ID `book-42`. Nên bổ sung test cho resource không tồn tại, không đủ quyền, resource còn quan hệ bị chặn xóa, lỗi database và retry.

Với integration test, cần xác minh dữ liệu thực sự bị xóa hoặc được đánh dấu soft delete trong database, transaction rollback khi lỗi và các truy vấn đọc không còn trả resource đã xóa theo chính sách. Test controller đơn lẻ chỉ xác nhận mapping và response, không chứng minh persistence đã thay đổi đúng.

## 13. Những lỗi thường gặp khi thiết kế mutation xóa

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `deleteById` mà không kiểm tra quyền | Có thể xóa resource của người khác | Tải resource và kiểm tra authorization trước |
| Trả Boolean cho nghiệp vụ nhiều trạng thái | Client không biết nguyên nhân thất bại | Dùng payload với code lỗi ổn định |
| Trả null cho payload non-null | GraphQL phát sinh non-null execution error | Luôn trả payload hợp lệ cho kết quả dự kiến |
| Không kiểm tra foreign key và quan hệ | Xóa thất bại hoặc làm mất dữ liệu liên quan | Xác định quy tắc cascade và invariant |
| Xóa vật lý khi cần audit/restore | Không thể phục hồi hoặc truy vết đầy đủ | Cân nhắc soft delete và audit log |
| Tin mutation tuần tự là transaction | Một phần thao tác có thể đã commit khi bước sau lỗi | Đặt transaction trong service nghiệp vụ |
| Không định nghĩa hành vi retry | Client không biết xử lý kết quả lặp | Quy định idempotency và chống tác dụng phụ trùng |
| Trả entity đã xóa với nhiều field liên quan | Resolver con có thể truy cập dữ liệu không còn tồn tại | Trả payload snapshot tối thiểu |
| Chỉ kiểm thử response | Không biết database có thay đổi đúng hay không | Bổ sung integration test persistence và rollback |

## 14. Checklist trước khi công bố mutation xóa

- Field có tên thể hiện rõ resource và hành động xóa?
- ID có kiểu bắt buộc và được kiểm tra định dạng ở tầng phù hợp?
- Schema đã xác định payload, nullability và error contract?
- Service có kiểm tra resource tồn tại và quyền trên resource đó?
- Điều kiện nghiệp vụ, quan hệ và foreign key đã được xem xét?
- Đã quyết định hard delete hay soft delete?
- Transaction bao phủ các thay đổi cần nhất quán?
- Hành vi khi request được retry hoặc xóa lặp đã rõ ràng?
- Payload chỉ chứa thông tin cần thiết và an toàn sau khi xóa?
- Có test cho thành công, not found, forbidden, conflict và rollback?

Mutation xóa resource trong Spring for GraphQL bắt đầu từ field trong root type `Mutation` và được ánh xạ bằng `@MutationMapping`. Resolver nên chuyển command tới service để kiểm tra quyền, điều kiện nghiệp vụ và thực hiện xóa trong transaction. Một payload có trạng thái và mã lỗi rõ ràng giúp client cập nhật giao diện dễ dàng, trong khi việc lựa chọn hard delete hay soft delete, xử lý retry và bảo vệ quan hệ dữ liệu giúp thao tác an toàn trong vận hành thực tế.
