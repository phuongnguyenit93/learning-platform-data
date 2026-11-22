# Versioning bằng schema evolution

GraphQL API thường dùng một schema có thể tiến hóa liên tục thay vì tạo endpoint riêng cho từng phiên bản. Khi hợp đồng thay đổi theo hướng bổ sung, client cũ vẫn tiếp tục truy vấn những field mà nó biết; client mới có thể chọn thêm field mới. Cách tiếp cận này giúp API phát triển mà không buộc mọi client nâng cấp cùng lúc.

Tuy nhiên, schema evolution chỉ an toàn khi hiểu tác động của từng thay đổi lên query, mutation, input, output và code được sinh từ schema. Xóa field, thêm argument bắt buộc, thay đổi nullability hoặc thay đổi tập giá trị enum có thể khiến client đang hoạt động gặp lỗi validation hoặc lỗi xử lý dữ liệu.

Trong Spring for GraphQL, schema SDL là hợp đồng công khai, còn controller và application service triển khai hành vi của hợp đồng đó. Bài này trình bày cách tiến hóa schema, đánh dấu field cũ bằng `@deprecated`, triển khai giai đoạn chuyển đổi, nhận diện breaking changes và tổ chức quy trình phát hành.

## 1. GraphQL versioning khác REST versioning như thế nào?

Với REST, nhiều hệ thống duy trì các endpoint như `/api/v1/books` và `/api/v2/books`. GraphQL thường giữ một endpoint ổn định, ví dụ `/graphql`, trong khi schema được mở rộng theo thời gian.

Client chỉ yêu cầu những field có trong selection set. Vì vậy, khi server thêm field mới vào type `Book`, query cũ không tự động nhận thêm field đó và response cũ vẫn giữ shape mà client đã yêu cầu.

Ví dụ, schema ban đầu:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Sau đó server bổ sung field `publishedAt`:

~~~graphql
type Book {
    id: ID!
    title: String!
    publishedAt: String
}
~~~

Client cũ vẫn có thể gửi:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Client mới có thể chọn thêm field:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
        publishedAt
    }
}
~~~

Hai client có thể hoạt động trên cùng schema. Đây là lợi thế chính của schema evolution: thay đổi được triển khai theo nhu cầu của client, thay vì đồng loạt đổi phiên bản endpoint.

GraphQL không cấm việc duy trì nhiều phiên bản schema. Nếu một thay đổi không thể tương thích, hệ thống vẫn có thể cung cấp endpoint hoặc schema riêng trong thời gian chuyển đổi. Tuy nhiên, nên coi đó là phương án cho thay đổi lớn thực sự, vì mỗi schema cần được duy trì, kiểm thử và vận hành.

## 2. Nguyên tắc additive change

Một thay đổi mang tính bổ sung (additive change) mở rộng khả năng của schema mà không làm query hợp lệ trước đó trở nên không hợp lệ.

Các thay đổi thường an toàn:

- Thêm field mới vào object type hoặc query root.
- Thêm argument mới có thể bỏ qua hoặc có default value phù hợp.
- Thêm input field tùy chọn vào input object.
- Thêm mutation mới mà vẫn giữ mutation cũ.
- Thêm type mới mà không làm thay đổi ý nghĩa của type hiện tại.

Ví dụ, bổ sung bộ lọc tùy chọn:

~~~graphql
type Query {
    books(
        term: String!
        category: String
        limit: Int = 20
    ): [Book!]!
}
~~~

Client cũ chỉ truyền `term` vẫn hợp lệ. Client mới có thể truyền thêm `category` và `limit`.

Đối với input object:

~~~graphql
type Query {
    books(input: BookSearchInput!): [Book!]!
}

input BookSearchInput {
    term: String!
    category: String
    publishedAfter: String
}
~~~

Client cũ chỉ gửi `term` vẫn hợp lệ vì hai field mới có thể vắng mặt. Resolver cần xác định rõ ý nghĩa khi field bị bỏ qua, được gửi là `null`, hoặc có giá trị cụ thể nếu contract cần phân biệt ba trạng thái đó.

Không phải mọi thay đổi nhìn giống bổ sung đều an toàn. Thêm argument bắt buộc, thêm input field non-null không có default, hoặc thêm một giá trị enum output mà client xử lý bằng switch exhaustive có thể phá client hiện tại. Phải xét cả schema lẫn cách client sinh và xử lý code.

## 3. Nhận diện breaking change

Một breaking change khiến query cũ không còn hợp lệ, hoặc khiến client cũ không còn xử lý đúng response và hành vi API.

| Thay đổi | Tác động với client | Đánh giá |
| --- | --- | --- |
| Thêm output field mới | Client cũ không chọn field đó nên response không đổi | Thường an toàn |
| Thêm argument tùy chọn | Query cũ vẫn gọi field được | Thường an toàn |
| Thêm argument bắt buộc | Query cũ thiếu argument và không còn hợp lệ | Breaking |
| Thêm input field tùy chọn | Input cũ vẫn hợp lệ | Thường an toàn |
| Thêm input field non-null không có default | Input cũ thiếu field bắt buộc | Breaking |
| Xóa field hoặc argument đang dùng | Query cũ không còn hợp lệ | Breaking |
| Xóa enum value được client gửi | Mutation/query cũ có thể không còn hợp lệ | Breaking |
| Thay đổi scalar hoặc kiểu trả về | Client có thể không parse hoặc deserialize được | Có thể breaking |
| Đổi field nullable thành non-null | Thay đổi contract nullability và kiểu sinh ra | Cần đánh giá client |
| Đổi field non-null thành nullable | Client phải xử lý thêm khả năng `null` | Có thể breaking |
| Thay đổi default value | Query bỏ qua argument có thể đổi hành vi | Có thể breaking |
| Thêm member vào union | Client xử lý exhaustive có thể chưa biết member mới | Có thể breaking |
| Thay đổi ý nghĩa nghiệp vụ của field | Query vẫn hợp lệ nhưng kết quả thay đổi | Breaking về hành vi |

Nullability là một phần quan trọng của hợp đồng. `Book` và `Book!` không có cùng ý nghĩa: một field nullable có thể trả `null`, trong khi field non-null cam kết có giá trị hoặc làm lỗi lan lên parent theo quy tắc GraphQL. Việc thay đổi dấu `!` cần được đánh giá với client codegen, logic xử lý null và semantics thực tế của dữ liệu.

Thêm giá trị vào enum output cũng cần thận trọng. GraphQL query cũ vẫn có thể hợp lệ, nhưng client sinh enum thành kiểu đóng hoặc dùng switch exhaustive có thể lỗi khi server trả giá trị mới. Ngược lại, thêm giá trị enum dùng trong input thường không ảnh hưởng client cũ nếu client không gửi giá trị mới. Hãy đánh giá riêng enum input và enum output.

Ngoài schema, thay đổi quy tắc authorization, thứ tự mặc định, cách phân trang, ý nghĩa đơn vị tiền tệ hoặc quy tắc lọc cũng có thể phá client dù schema diff không phát hiện được. Contract bao gồm cả semantics, không chỉ SDL.

## 4. Deprecate field trước khi xóa

Không nên xóa field cũ ngay khi đã có tên field mới. GraphQL hỗ trợ directive `@deprecated` để đánh dấu field hoặc enum value không còn được khuyến nghị sử dụng.

Ví dụ đổi tên `Query.book` thành `Query.bookById`:

~~~graphql
type Query {
    book(id: ID!): Book
        @deprecated(reason: "Use bookById instead.")

    bookById(id: ID!): Book
}
~~~

Hai field có cùng kiểu trả về và cùng ý nghĩa. Field cũ vẫn hoạt động trong giai đoạn chuyển đổi. Client mới dùng `bookById`; client cũ tiếp tục dùng `book`.

Directive `@deprecated` có thể được đọc qua introspection. Tooling, IDE và tài liệu sinh từ schema có thể hiển thị field cũ cùng lý do deprecation. Tuy nhiên, directive không tự chặn request và không tự chuyển client sang field mới. Việc migration vẫn cần phối hợp giữa server và chủ sở hữu client.

Nên ghi reason ngắn, cụ thể và có hành động tiếp theo. Với API có nhiều client, reason có thể chỉ rõ field thay thế, tài liệu migration hoặc mốc dự kiến ngừng hỗ trợ.

Không dùng deprecation cho field vẫn là lựa chọn chính thức và không có kế hoạch thay thế. Deprecation là tín hiệu vòng đời API, vì vậy cần theo dõi và có chính sách gỡ bỏ rõ ràng.

## 5. Triển khai field cũ và mới trong Spring for GraphQL

Schema SDL khai báo cả hai field trong thời gian chuyển đổi. Controller có thể ánh xạ cả hai field về cùng application service để giữ hành vi nhất quán.

~~~java
package com.example.books.graphql;

import com.example.books.application.Book;
import com.example.books.application.BookNotFoundException;
import com.example.books.application.BookService;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }

    @QueryMapping(name = "bookById")
    public Book findBookById(@Argument String id) {
        return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Cả hai resolver gọi cùng một service method. Nhờ đó, quyền truy cập, cách tìm kiếm, xử lý not-found và quy tắc nghiệp vụ không bị sao chép thành hai implementation độc lập.

Trong giai đoạn chuyển đổi, có thể thêm log hoặc metric riêng cho field cũ để biết client nào còn sử dụng. Tránh ghi toàn bộ query variables hoặc dữ liệu nhạy cảm chỉ để đo usage. Nên gắn nhận diện client thông qua thông tin xác thực hoặc metadata đáng tin cậy nếu hệ thống có hỗ trợ.

Khi field mới thay đổi cả semantics, không nên chỉ đổi tên resolver rồi dùng chung implementation một cách máy móc. Cần xác định rõ khác biệt nghiệp vụ và kiểm thử contract cho cả hai field.

## 6. Quy trình expand, migrate, contract

Một cách triển khai có kiểm soát là chia thay đổi thành ba giai đoạn.

~~~mermaid
flowchart TD
    A[Current schema and clients] --> B[EXPAND]
    B --> C[Add new field or input]
    C --> D[Deploy server supporting old and new]
    D --> E[MIGRATE]
    E --> F[Move clients to new contract]
    F --> G[Measure old field usage]
    G --> H{Old usage is zero for agreed window?}
    H -- No --> E
    H -- Yes --> I[CONTRACT]
    I --> J[Remove deprecated field]
    J --> K[Publish updated schema]
~~~

**Expand — mở rộng schema**

- Thêm field, argument tùy chọn hoặc input field mới.
- Triển khai resolver và kiểm thử contract mới.
- Giữ field cũ để query hiện tại tiếp tục hoạt động.
- Đưa schema mới vào tài liệu và công bố cách sử dụng.

**Migrate — chuyển client**

- Cập nhật từng client sang field mới.
- Kiểm tra codegen và query đã lưu (persisted operations).
- Theo dõi usage của field cũ theo client và operation.
- Xác nhận các phiên bản ứng dụng còn được hỗ trợ đã chuyển đổi.

**Contract — thu gọn schema**

- Chỉ gỡ field cũ khi usage đã về 0 trong khoảng thời gian thống nhất.
- Xem xét client ít hoạt động, ứng dụng mobile cũ, job định kỳ và tích hợp đối tác.
- Công bố thời điểm ngừng hỗ trợ trước khi triển khai.
- Chạy schema diff và contract test sau khi xóa.

Không nên coi một vài ngày không có traffic là bằng chứng field không còn được dùng. Một client có thể chỉ chạy theo tháng, theo quý hoặc chỉ hoạt động trong tình huống khẩn cấp. Thời gian chờ phải phù hợp với vòng đời thật của client.

## 7. Theo dõi usage và xác định thời điểm xóa

Schema có thể cho biết field nào deprecated, nhưng không tự cho biết ai còn gọi field đó. Cần bổ sung quan sát ở runtime.

Các dữ liệu hữu ích gồm:

- Tên operation và loại operation (`query`, `mutation`, `subscription`).
- Tên field hoặc field coordinate đang được thực thi.
- Client/application ID từ nguồn xác thực đáng tin cậy.
- Số lần gọi thành công, lỗi và thời điểm gọi gần nhất.
- Phiên bản ứng dụng nếu client gửi metadata đã được xác thực hoặc kiểm soát.

Có thể dùng GraphQL instrumentation, observation, log có cấu trúc hoặc persisted operation registry để thu thập dữ liệu. Tránh lưu raw query, argument hoặc response không cần thiết vì chúng có thể chứa thông tin nhạy cảm.

Một field chỉ nên được xóa khi có đủ bằng chứng:

1. Các client đã công bố đều dùng field thay thế.
2. Không còn traffic của field cũ trong khoảng thời gian phù hợp với lịch hoạt động.
3. Các persisted operations và batch jobs đã được cập nhật.
4. Chủ sở hữu tích hợp bên ngoài đã được thông báo.
5. Có kế hoạch rollback hoặc khôi phục schema nếu phát hiện client bị bỏ sót.

Nếu không thể xác định client nào gọi field cũ, cần thận trọng hơn. Có thể tiếp tục giữ field deprecated hoặc triển khai cảnh báo trước khi xóa.

## 8. Thiết kế thay đổi input và mutation

Mutation thường có nhiều client cùng gửi input. Khi mở rộng input object, ưu tiên field tùy chọn và quy định rõ default behavior.

Ví dụ input cũ:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}
~~~

Có thể bổ sung field tùy chọn:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    language: String
}
~~~

Client cũ vẫn gửi hai field ban đầu. Client mới có thể gửi `language`. Application service cần xác định giá trị mặc định khi `language` không được gửi.

Tránh thêm field non-null bắt buộc vào input object đang được nhiều client sử dụng:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    language: String!
}
~~~

Sau thay đổi này, input cũ thiếu `language` không còn hợp lệ. Nếu cần một dữ liệu bắt buộc mới, hãy cân nhắc thêm một field nullable trước, áp dụng default hoặc tạo mutation mới có contract mới trong giai đoạn migration.

Không nên đổi tên input field bằng cách xóa tên cũ ngay. Nếu schema và phiên bản GraphQL Java đang dùng hỗ trợ deprecation cho input value, có thể đánh dấu input field hoặc argument cũ; nếu không, giữ hai field trong một khoảng chuyển tiếp và xử lý ưu tiên rõ ràng ở application layer. Cần tránh trường hợp client gửi cả hai giá trị khác nhau mà server không có quy tắc xác định.

## 9. Enum, interface và union cần chính sách riêng

Các kiểu composite và enum có thể gây breaking change ngay cả khi query document vẫn validate.

**Enum**

~~~graphql
enum BookFormat {
    PRINT
    EBOOK
    AUDIOBOOK
}
~~~

Nếu server thêm `PODCAST` vào enum được trả về, client có enum sinh từ schema cũ có thể không biết cách xử lý giá trị đó. Client nên có nhánh fallback cho giá trị không nhận diện được, hoặc server cần kế hoạch versioning riêng nếu client không thể mở rộng.

Nếu một enum value không còn được dùng, hãy đánh dấu deprecated trước:

~~~graphql
enum BookFormat {
    PRINT
    EBOOK
    AUDIOBOOK @deprecated(reason: "Use DIGITAL instead.")
    DIGITAL
}
~~~

**Interface**

Thêm field vào interface mở rộng contract mà các type implement phải đáp ứng. Resolver và object type liên quan cần được cập nhật. Việc thay đổi hoặc xóa field hiện có có thể phá query chọn field trên interface.

**Union**

Thêm member vào union có thể ảnh hưởng client dùng inline fragment và xử lý exhaustive theo `__typename`. Client nên có nhánh xử lý type chưa biết để chịu được schema evolution tốt hơn.

~~~graphql
union SearchResult = Book | Author | Publisher
~~~

Khi thêm `Publisher`, client cũ có thể vẫn validate query, nhưng code xử lý kết quả phải có fallback cho một `__typename` mới. Đừng đánh giá compatibility chỉ bằng việc GraphQL document có qua validation hay không.

## 10. Quản lý schema contract trong CI/CD

Schema SDL nên được quản lý như một API contract có review và lịch sử thay đổi. Mỗi pull request sửa schema nên có bước kiểm tra tác động lên client.

Một quy trình CI có thể gồm:

1. Build hoặc lấy schema SDL mới từ source.
2. So sánh với schema của phiên bản đã phát hành.
3. Phân loại thay đổi thành additive, deprecated, dangerous hoặc breaking theo chính sách của tổ chức.
4. Yêu cầu review bổ sung nếu có breaking change.
5. Chạy contract test cho các operation quan trọng.
6. Xuất schema mới cùng migration note khi phát hành.

Schema diff tự động giúp phát hiện xóa field, thay đổi kiểu, argument bắt buộc mới hoặc thay đổi enum. Tuy nhiên, công cụ diff không thể tự hiểu mọi thay đổi semantics, authorization hoặc business rule. Review API vẫn cần kiểm tra tác động hành vi.

Với persisted query hoặc operation registry, nên kiểm tra tập query đang được client sử dụng với schema mới. Một field bị xóa có thể khiến operation đã lưu thất bại validation ngay khi client gửi lại.

## 11. Kiểm thử compatibility

Nên kiểm thử cả contract cũ và mới trong thời gian migration. Ví dụ, dùng `ExecutionGraphQlServiceTester` để tạo `GraphQlTester` chạy trực tiếp qua Spring `ExecutionGraphQlService`, không cần dựng HTTP client:

~~~java
package com.example.books.graphql;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

@SpringBootTest
class BookSchemaEvolutionTests {

    @Autowired
    ExecutionGraphQlService graphQlService;

    @Test
    void oldAndNewQueryFieldsReturnTheSameBook() {
        GraphQlTester graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);

        String oldId = graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .get();

        String newId = graphQlTester.document("""
                query {
                    bookById(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("bookById.id")
            .entity(String.class)
            .get();

        assertThat(oldId).isEqualTo(newId);
    }
}
~~~

Ví dụ này giả định fixture `book-42` đã được nạp và service trả cùng một bản ghi cho cả hai resolver. Test chứng minh hành vi của field cũ và mới nhất quán trong giai đoạn migration.

Ngoài ra, nên có test cho:

- Query cũ vẫn validate và thực thi sau khi thêm field mới.
- Client có thể sử dụng field mới.
- Input cũ vẫn hợp lệ khi chỉ bổ sung field tùy chọn.
- Field deprecated vẫn hoạt động trước khi bị gỡ.
- Query cũ thất bại đúng cách sau khi field bị xóa trong một schema version mới.
- Enum/union client có fallback cho giá trị hoặc type chưa biết.
- Authorization và nullability giữ đúng contract.

Đối với client quan trọng, có thể lưu operation đại diện làm consumer contract test. Khi thay schema, chạy lại toàn bộ operation này để phát hiện lỗi validation trước khi deploy.

## 12. Khi nào cần phiên bản schema riêng?

Có những thay đổi không thể triển khai bằng additive evolution, chẳng hạn đổi ý nghĩa của field, thay đổi mô hình dữ liệu cốt lõi hoặc thay đổi semantics khiến client cũ không thể tiếp tục hoạt động.

Khi đó, có thể duy trì hai schema trong một khoảng thời gian:

- Endpoint/schema cũ tiếp tục phục vụ client chưa migration.
- Endpoint/schema mới chứa contract mới.
- Hai schema có lịch ngừng hỗ trợ và kế hoạch chuyển client rõ ràng.
- Logic nghiệp vụ dùng chung nên được đặt trong application service để tránh fork toàn bộ domain logic.

Không nên thêm argument kiểu `version: 1` vào mọi query hoặc mutation. Cách đó làm client phải chọn version ở từng field, khiến schema phức tạp và khó kết hợp dữ liệu giữa các field.

Cũng không nên tạo phiên bản schema mới chỉ vì muốn đổi tên một field. Với thay đổi có thể additive, thêm field mới, deprecate field cũ và migration theo usage thường đơn giản hơn.

## 13. Lỗi thường gặp khi tiến hóa GraphQL schema

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query cũ đột nhiên lỗi validation | Field hoặc argument đã bị xóa/đổi tên | Khôi phục field hoặc triển khai giai đoạn deprecation |
| Mutation cũ không gửi đủ input | Thêm input field non-null bắt buộc | Dùng field tùy chọn/default hoặc mutation mới |
| Client lỗi khi nhận enum mới | Client codegen xử lý enum như tập giá trị đóng | Thêm fallback hoặc có kế hoạch contract riêng |
| Client không còn phân biệt được null | Thay đổi nullability | Đánh giá semantics và generated types trước khi đổi |
| Field mới và field cũ trả khác dữ liệu | Hai resolver có business logic riêng | Dùng chung application service và contract test |
| Xóa field nhưng đối tác vẫn lỗi | Chỉ kiểm tra traffic nội bộ | Theo dõi client bên ngoài, job định kỳ và persisted operations |
| Schema diff không phát hiện lỗi | Chỉ thay đổi semantics hoặc authorization | Bổ sung consumer contract và integration test |
| Field deprecated tồn tại quá lâu | Không có owner và điều kiện gỡ bỏ | Gán owner, usage metric và sunset criteria |

## 14. Checklist trước mỗi lần phát hành schema

- Thay đổi này có thể được triển khai theo hướng additive không?
- Query và mutation cũ có tiếp tục validate không?
- Argument hoặc input field mới có bắt buộc không?
- Nullability có thay đổi không?
- Enum hoặc union có thêm giá trị/type mà client phải xử lý không?
- Field cũ đã được đánh dấu `@deprecated` với lý do rõ ràng chưa?
- Resolver cũ và mới có dùng chung nghiệp vụ cần thiết không?
- Có metric để biết client nào còn sử dụng field cũ không?
- Persisted operations và client codegen đã được kiểm tra chưa?
- CI có schema diff và contract test không?
- Có lịch thông báo, sunset và rollback phù hợp không?

Schema evolution giúp GraphQL API phục vụ nhiều thế hệ client trên cùng một contract đang phát triển. Hãy ưu tiên bổ sung field và input tùy chọn, đánh dấu field cũ bằng `@deprecated`, giữ hai contract cùng hoạt động trong giai đoạn migration và chỉ xóa khi usage đã được xác minh. Với thay đổi không thể tương thích, hãy công bố schema version riêng có vòng đời rõ ràng. Spring for GraphQL cung cấp resolver và runtime để triển khai contract; trách nhiệm giữ compatibility vẫn thuộc về thiết kế schema, quy trình phát hành và kiểm thử consumer.

## Tài liệu tham khảo

- [GraphQL Specification — Type System and Deprecation](https://spec.graphql.org/)
- [GraphQL — Schema and Queries](https://graphql.org/learn/schema/)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)

