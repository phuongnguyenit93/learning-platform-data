# Error filter

Khi kiểm thử GraphQL API bằng Spring for GraphQL, response có thể chứa cả `data` và `errors`. Một số test chủ động tạo ra lỗi hoặc kiểm tra field có thể thất bại trong khi các field khác vẫn trả dữ liệu. Nếu dùng `GraphQlTester` và gọi `verify()` trực tiếp, mọi GraphQL error chưa được khai báo là expected đều làm assertion thất bại.

**Error filter** là cơ chế của `GraphQlTester` để đánh dấu một số response error là đã được dự kiến, từ đó cho phép test tiếp tục kiểm tra phần dữ liệu còn lại. Spring for GraphQL cung cấp ba cách xử lý error trong một response: `filter(...)`, `expect(...)` và `satisfy(...)`. Ngoài ra, builder có `errorFilter(...)` để áp dụng predicate chung cho mọi request của tester.

Bài học tập trung vào phạm vi và cách dùng các API này, cách viết predicate đủ hẹp để không che giấu regression, và cách kiểm thử partial data cùng GraphQL errors.

## 1. Vì sao cần Error filter?

GraphQL có thể trả dữ liệu một phần nếu một field gặp lỗi nhưng các field khác vẫn thực thi được.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    recommendation: Recommendation
}

type Recommendation {
    id: ID!
    reason: String!
}
~~~

Giả sử `book` và `title` lấy dữ liệu thành công, nhưng dịch vụ gợi ý tạm thời không khả dụng. Response có thể tương tự:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring for GraphQL",
            "recommendation": null
        }
    },
    "errors": [
        {
            "message": "Recommendation service is unavailable",
            "path": ["book", "recommendation"],
            "extensions": {
                "code": "RECOMMENDATION_UNAVAILABLE"
            }
        }
    ]
}
~~~

Một test chỉ muốn xác nhận `book.title` vẫn có thể đọc được cần xử lý error ở field `recommendation`. Nếu không khai báo error đó là expected, bước xác minh response có thể thất bại trước khi test đi tới path dữ liệu.

Ví dụ:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .filter(error ->
                "book.recommendation".equals(error.getPath())
                        && "RECOMMENDATION_UNAVAILABLE".equals(
                                error.getExtensions().get("code"))
        )
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Error filter giúp test xác định rõ lỗi nào được chấp nhận trong ngữ cảnh test đó. Các lỗi không khớp predicate vẫn là lỗi chưa được xử lý và khiến `verify()` thất bại.

## 2. Error filter hoạt động ở phía kiểm thử

Cần phân biệt hai việc:

- **Server error handling:** resolver, `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler` quyết định cách exception trở thành GraphQL error.
- **Test error filtering:** `GraphQlTester` quyết định error nào được xem là expected khi xác minh response.

`filter(...)` không xóa error khỏi response do server trả về, không sửa `data`, không ngăn resolver phát sinh exception và không thay đổi hành vi của API đối với client thật. Nó chỉ điều chỉnh cách `GraphQlTester` xác minh response trong test hiện tại.

Do đó, không dùng Error filter như một cách sửa lỗi server. Nếu production API phát ra lỗi ngoài dự kiến, cần sửa resolver, service hoặc error mapping. Filter chỉ phù hợp khi test đã biết một lỗi cụ thể có thể xuất hiện và muốn tập trung kiểm tra phần response khác.

## 3. Chuẩn bị GraphQlTester

Các API error filter thuộc `spring-graphql-test`. Thêm dependency trong test scope:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Boot dependency management có thể quản lý phiên bản tương thích. Không cần khai báo version riêng nếu dự án đã dùng Spring Boot dependency management.

`GraphQlTester` cung cấp workflow kiểm thử chung. Có thể tạo tester từ các extension khác nhau:

| Tester | Phạm vi |
| --- | --- |
| `ExecutionGraphQlServiceTester` | Gọi trực tiếp execution service ở server-side |
| `WebGraphQlTester` | Kiểm thử `WebGraphQlHandler` và interceptor chain |
| `HttpGraphQlTester` | Kiểm thử qua HTTP |
| `WebSocketGraphQlTester` | Kiểm thử qua WebSocket |
| `RSocketGraphQlTester` | Kiểm thử qua RSocket |

Cách xử lý `errors()` là API chung, nên cùng một predicate có thể tái sử dụng ở nhiều loại tester. Phần tạo tester phụ thuộc transport cần kiểm thử.

## 4. Vòng đời kiểm tra errors trong một response

Một request test thường có dạng:

~~~java
graphQlTester.document(document)
        .execute()
        .errors()
        .filter(error -> /* predicate */)
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Các bước:

1. `document(...)` cung cấp GraphQL document.
2. `execute()` gửi request và nhận response.
3. `errors()` mở phần khai báo cách xử lý các GraphQL errors trong response.
4. `filter(...)`, `expect(...)` hoặc `satisfy(...)` xử lý error theo mục tiêu test.
5. `verify()` xác minh không còn error ngoài dự kiến.
6. `path(...)` chuyển sang kiểm tra dữ liệu trong phần `data`.

Phải khai báo việc xử lý errors trước khi đi vào `path(...)`. Nếu test đi thẳng đến một data path trong khi response có error chưa được xử lý, `GraphQlTester` sẽ không tự bỏ qua error đó.

## 5. Dùng errors().filter(...) để bỏ qua lỗi đã biết

`filter(Predicate<ResponseError>)` đánh dấu các error khớp predicate là expected và bỏ qua chúng khi `verify()` hoặc khi test đi tới data path.

Ví dụ:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .filter(error -> error.getMessage()
                .equals("Recommendation service is unavailable"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Trong ví dụ này, error có đúng message được chỉ định sẽ không làm `verify()` thất bại. Nếu response không có error đó, test vẫn có thể thành công; `filter(...)` không yêu cầu predicate phải khớp ít nhất một error.

Đặc điểm này phù hợp khi lỗi có thể xuất hiện hoặc không xuất hiện tùy dữ liệu test, trong khi mục tiêu chính là xác minh phần response khác. Nếu test cần khẳng định lỗi phải xảy ra, hãy dùng `expect(...)`.

## 6. Dùng errors().expect(...) khi lỗi bắt buộc phải xuất hiện

`expect(Predicate<ResponseError>)` cũng đánh dấu error khớp predicate là expected. Khác với `filter(...)`, `expect(...)` yêu cầu phải có ít nhất một error khớp; nếu không có, assertion thất bại.

Ví dụ kiểm tra dịch vụ recommendation bị lỗi đúng như kịch bản:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                "book.recommendation".equals(error.getPath())
                        && "RECOMMENDATION_UNAVAILABLE".equals(
                                error.getExtensions().get("code"))
        )
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Test này kiểm tra đồng thời:

- Phải có ít nhất một error mang mã `RECOMMENDATION_UNAVAILABLE` tại path `book.recommendation`.
- Error khớp được xem là expected.
- Các error khác không khớp predicate vẫn làm `verify()` thất bại.
- Field `book.title` vẫn phải trả đúng dữ liệu.

`expect(...)` không tự khẳng định chỉ có đúng một error khớp. Nếu cần kiểm tra số lượng chính xác, hãy dùng `satisfy(...)` và assertion trên danh sách errors.

## 7. Dùng errors().satisfy(...) để kiểm tra toàn bộ danh sách

`errors().satisfy(Consumer<List<ResponseError>>)` cho phép kiểm tra trực tiếp danh sách errors bằng AssertJ hoặc assertion library khác.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                recommendation {
                    id
                }
            }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertThat(errors).hasSize(1);
            assertThat(errors.get(0).getPath())
                    .isEqualTo("book.recommendation");
            assertThat(errors.get(0).getExtensions())
                    .containsEntry("code", "RECOMMENDATION_UNAVAILABLE");
        })
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Sau khi consumer chạy, `satisfy(...)` xem toàn bộ errors đã được kiểm tra và đánh dấu chúng là filtered. Vì vậy test có thể tiếp tục đi tới data path.

Điều này rất hữu ích khi cần kiểm tra nhiều thuộc tính của error như path, message, code và số lượng. Tuy nhiên, vì tất cả errors đều được xem là đã xử lý, consumer phải assertion đầy đủ. Nếu chỉ kiểm tra một error nhưng bỏ sót error khác, test có thể vô tình chấp nhận response sai.

## 8. So sánh filter, expect và satisfy

| API | Điều kiện để test tiếp tục | Có yêu cầu error phải xuất hiện? | Phù hợp khi |
| --- | --- | --- | --- |
| `filter(predicate)` | Các error khớp predicate được bỏ qua; error khác vẫn phải xử lý | Không | Error đã biết có thể xuất hiện hoặc không |
| `expect(predicate)` | Error khớp được chấp nhận; error không khớp vẫn bị phát hiện | Có, ít nhất một error khớp | Test chủ đích kiểm tra một lỗi cụ thể |
| `satisfy(consumer)` | Consumer assertion trên danh sách; toàn bộ errors được xem là đã xử lý | Tùy assertion viết trong consumer | Cần kiểm tra số lượng hoặc nhiều thuộc tính của errors |

Có thể ghi nhớ theo mục tiêu:

- Muốn bỏ qua một lỗi tùy chọn: dùng `filter`.
- Muốn chứng minh một lỗi cụ thể đã xảy ra: dùng `expect`.
- Muốn kiểm tra toàn bộ danh sách: dùng `satisfy`.

Không dùng `satisfy` chỉ để tránh assertion lỗi. Consumer nên kiểm tra rõ ràng những error mà test chấp nhận.

## 9. Đọc ResponseError để viết predicate chính xác

Predicate nhận một đối tượng `ResponseError`. Interface này cung cấp các thông tin quan trọng:

| Method | Ý nghĩa |
| --- | --- |
| `getMessage()` | Message mô tả lỗi |
| `getPath()` | Path dạng chuỗi của field gây lỗi; trả chuỗi rỗng nếu lỗi không gắn với field |
| `getParsedPath()` | Path dạng danh sách segment, field name là chuỗi và list index là số nguyên |
| `getLocations()` | Vị trí trong GraphQL document nếu lỗi gắn với source location |
| `getErrorType()` | Classification của lỗi theo GraphQL Java |
| `getExtensions()` | Metadata bổ sung, có thể chứa error code hoặc classification |

Ví dụ response error có thể được kiểm tra theo path và code:

~~~java
import org.springframework.graphql.ResponseError;

private static boolean isRecommendationUnavailable(ResponseError error) {
    return "book.recommendation".equals(error.getPath())
            && "RECOMMENDATION_UNAVAILABLE".equals(
                    error.getExtensions().get("code"));
}
~~~

Sử dụng trong test:

~~~java
graphQlTester.document(document)
        .execute()
        .errors()
        .expect(MyGraphQlErrorPredicates::isRecommendationUnavailable)
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Predicate có thể được đặt trong helper class để dùng lại giữa các test. Hãy giữ helper cụ thể theo error code và field path để người đọc hiểu chính xác lỗi nào được chấp nhận.

## 10. Ưu tiên path và extensions.code thay vì chỉ so sánh message

Message thường được viết cho người phát triển đọc, có thể thay đổi khi chỉnh sửa câu chữ, localization hoặc cách format exception. Vì vậy, nếu server công bố mã lỗi ổn định trong `extensions`, nên ưu tiên so sánh mã đó.

Ví dụ predicate đủ cụ thể:

~~~java
import org.springframework.graphql.ResponseError;

import java.util.function.Predicate;

private static Predicate<ResponseError> recommendationUnavailable() {
    return error ->
            "book.recommendation".equals(error.getPath())
                    && "RECOMMENDATION_UNAVAILABLE".equals(
                            error.getExtensions().get("code"));
}
~~~

Dùng:

~~~java
.errors()
.expect(recommendationUnavailable())
.verify()
~~~

Nếu chỉ kiểm tra message:

~~~java
.errors()
.filter(error -> error.getMessage().contains("unavailable"))
.verify()
~~~

predicate có thể vô tình khớp với lỗi từ field khác hoặc một lỗi mới có message tương tự. Điều này làm test bỏ qua regression mà không nhận ra.

Kết hợp nhiều thuộc tính để xác định đúng error:

- Path xác định field bị lỗi.
- `extensions.code` xác định loại lỗi nghiệp vụ.
- Error classification có thể giúp phân biệt nhóm lỗi tổng quát.
- Message chỉ nên dùng khi nội dung message chính là hợp đồng cần kiểm tra.

## 11. Hiểu đúng error path

`ResponseError.getPath()` trả path của field trong **response**, không phải đường dẫn class Java hay tên resolver. Path có thể chứa index của list và tên alias mà client đã chọn.

Ví dụ query:

~~~graphql
query {
    book(id: "book-42") {
        suggested: recommendation {
            id
        }
    }
}
~~~

Nếu field recommendation gây lỗi, path trong response có thể là:

~~~json
{
    "path": ["book", "suggested"]
}
~~~

Vì query dùng alias `suggested`, predicate phải so sánh với `book.suggested`, không phải `book.recommendation`.

Với list, path có thể chứa index:

~~~json
{
    "path": ["books", 1, "author", "biography"]
}
~~~

`getPath()` biểu diễn dạng chuỗi, ví dụ `books[1].author.biography`. Nếu cần kiểm tra từng segment mà không phụ thuộc cách format chuỗi, dùng `getParsedPath()`.

Không phải mọi GraphQL error đều có path. Parse error hoặc một số request-level error có thể không gắn với field cụ thể; khi đó path rỗng. Không nên dùng predicate chỉ kiểm tra path của field để lọc request-level errors.

## 12. Dùng error classification và extensions

Ngoài `extensions.code`, có thể kiểm tra classification tổng quát của error.

Ví dụ:

~~~java
import org.springframework.graphql.ResponseError;
import org.springframework.graphql.execution.ErrorType;

private static boolean isNotFoundAtBookField(ResponseError error) {
    return "book".equals(error.getPath())
            && ErrorType.NOT_FOUND.equals(error.getErrorType());
}
~~~

Classification giúp phân biệt nhóm lỗi như `NOT_FOUND`, `FORBIDDEN` hoặc `BAD_REQUEST`, tùy cách server tạo error. Mã trong `extensions.code` thường mô tả trường hợp nghiệp vụ cụ thể hơn, ví dụ `BOOK_NOT_FOUND` hoặc `BOOK_VERSION_CONFLICT`.

Không giả định mọi server error đều có cùng classification hoặc custom code. Predicate phải dựa trên error contract thực tế mà API công bố.

Ví dụ response:

~~~json
{
    "errors": [
        {
            "message": "Không tìm thấy sách",
            "path": ["book"],
            "extensions": {
                "classification": "NOT_FOUND",
                "code": "BOOK_NOT_FOUND"
            }
        }
    ]
}
~~~

Có thể kiểm tra cả code và path để bảo đảm test chỉ chấp nhận đúng tình huống dự kiến:

~~~java
.errors()
.expect(error ->
        "book".equals(error.getPath())
                && "BOOK_NOT_FOUND".equals(
                        error.getExtensions().get("code")))
.verify()
~~~

## 13. Đăng ký errorFilter toàn cục trên Builder

Nếu một loại error được xem là expected trong nhiều test thuộc cùng một tester, có thể đăng ký predicate ngay ở builder bằng `errorFilter(...)`.

Ví dụ với `WebGraphQlTester`:

~~~java
import org.springframework.graphql.ResponseError;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

import java.util.function.Predicate;

Predicate<ResponseError> expectedRecommendationWarning =
        error -> "book.recommendation".equals(error.getPath())
                && "RECOMMENDATION_UNAVAILABLE".equals(
                        error.getExtensions().get("code"));

WebGraphQlTester graphQlTester =
        WebGraphQlTester.builder(handler)
                .errorFilter(expectedRecommendationWarning)
                .build();
~~~

Predicate được đăng ký trên builder sẽ áp dụng cho tất cả request được thực hiện bằng tester đó. Có thể cấu hình tương tự với builder của các loại `GraphQlTester` khác.

Sau đó, test không cần khai báo lại filter ở từng response:

~~~java
graphQlTester.document(document)
        .execute()
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

Chỉ dùng filter toàn cục khi cùng một error thực sự được xem là expected trong mọi test sử dụng tester đó. Nếu lỗi chỉ hợp lệ trong một operation hoặc một kịch bản cụ thể, đặt `errors().filter(...)` tại test tương ứng để phạm vi được giới hạn.

Không cấu hình predicate quá rộng như:

~~~java
.errorFilter(error -> true)
~~~

Cách này làm mọi GraphQL error đều bị bỏ qua trong tất cả request của tester, khiến test có thể vẫn xanh dù API phát sinh lỗi nghiêm trọng.

## 14. Kết hợp filter và expect trong cùng response

Có thể thêm nhiều điều kiện xử lý error trước khi gọi `verify()`. Ví dụ một query có một warning tùy chọn có thể bỏ qua, đồng thời bắt buộc phải có lỗi quyền truy cập ở một field khác:

~~~java
graphQlTester.document("""
        query {
            dashboard {
                title
                recommendations {
                    id
                }
                privateNotes
            }
        }
        """)
        .execute()
        .errors()
        .filter(error ->
                "dashboard.recommendations".equals(error.getPath())
                        && "RECOMMENDATIONS_UNAVAILABLE".equals(
                                error.getExtensions().get("code")))
        .expect(error ->
                "dashboard.privateNotes".equals(error.getPath())
                        && "FORBIDDEN".equals(
                                error.getExtensions().get("code")))
        .verify()
        .path("dashboard.title")
        .entity(String.class)
        .isEqualTo("My dashboard");
~~~

Ý nghĩa:

- Recommendation error được bỏ qua nếu xuất hiện; filter không yêu cầu nó phải có mặt.
- Forbidden error bắt buộc phải xuất hiện; nếu không có, `expect(...)` làm test thất bại.
- Các error khác không khớp điều kiện vẫn bị `verify()` phát hiện.

Khi kết hợp nhiều predicate, hãy đặt tên helper theo ý nghĩa nghiệp vụ và tránh lặp các biểu thức điều kiện dài trong nhiều test.

## 15. Error filter và executeAndVerify()

Với mutation không có response data cần kiểm tra, `GraphQlTester` có helper `executeAndVerify()` để thực thi và xác minh response không có GraphQL error.

Ví dụ:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-42")
        }
        """)
        .executeAndVerify();
~~~

`executeAndVerify()` phù hợp khi mục tiêu là khẳng định operation hoàn tất mà không có error. Nếu test cần chấp nhận hoặc kiểm tra một error cụ thể, hãy dùng `execute()` rồi khai báo `errors().filter(...)`, `errors().expect(...)` hoặc `errors().satisfy(...)`.

Không dùng `executeAndVerify()` cho một kịch bản cố ý trả GraphQL error mà không có cơ chế error filter phù hợp, vì helper này được thiết kế để xác minh không có error.

## 16. Các lỗi thường gặp khi dùng Error filter

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test vẫn thất bại ở `verify()` | Predicate không khớp error thực tế hoặc còn error khác | Kiểm tra message, path, extensions và danh sách errors |
| Test pass dù error không xuất hiện | Dùng `filter(...)` trong khi cần xác nhận error phải có | Đổi sang `expect(...)` |
| Test bỏ qua quá nhiều lỗi | Predicate chỉ kiểm tra một message chung hoặc dùng `error -> true` | Kết hợp path với error code cụ thể |
| Filter không áp dụng khi đọc data path | Gọi `path(...)` trước khi xử lý `errors()` | Xử lý errors trước khi gọi `path(...)` |
| Test không bắt được lỗi tại alias | Predicate dùng tên schema field thay cho response alias | Kiểm tra `getPath()` thực tế hoặc `getParsedPath()` |
| `satisfy(...)` làm test không phát hiện error khác | Consumer đã đánh dấu toàn bộ errors là filtered nhưng chỉ assertion một phần | Kiểm tra đầy đủ danh sách và số lượng errors |
| Filter toàn cục che giấu regression | Builder áp dụng predicate cho mọi request | Chỉ cấu hình error thực sự chung; ưu tiên filter cục bộ |
| Filter không bắt parse/coercion error | Error không có field path hoặc predicate chỉ nhắm execution error | Kiểm tra request-level error riêng; không bỏ qua rộng rãi |
| Filter không xử lý lỗi HTTP/network | Error filter chỉ nhận `ResponseError` từ GraphQL response | Kiểm tra transport exception và HTTP status ở tầng client |
| Message thay đổi làm test thất bại | Predicate phụ thuộc câu chữ không ổn định | Ưu tiên `extensions.code` và path |

## 17. Quy trình chọn Error filter cho một test

Khi response có GraphQL errors, hãy xác định mục tiêu của test trước:

1. Xác định test cần kiểm tra dữ liệu, một lỗi cụ thể hay toàn bộ danh sách errors.
2. Nếu không chấp nhận GraphQL error nào, dùng `execute()` và `errors().verify()` hoặc `executeAndVerify()`.
3. Nếu một error có thể xuất hiện và được phép bỏ qua, dùng `filter(predicate)`.
4. Nếu test bắt buộc phải nhận một error, dùng `expect(predicate)`.
5. Nếu cần kiểm tra số lượng, path, message và extensions của tất cả errors, dùng `satisfy(consumer)`.
6. Viết predicate dựa trên path và `extensions.code` khi API có cung cấp mã lỗi ổn định.
7. Xử lý errors trước khi đi tới `path(...)`.
8. Giữ filter toàn cục cho các lỗi chung thực sự; dùng filter cục bộ cho kịch bản riêng.
9. Kiểm tra rằng error ngoài dự kiến vẫn khiến test thất bại.
10. Không dùng filter để che lỗi server hoặc lỗi transport.

## 18. Những điểm cần ghi nhớ

- Error filter là cơ chế xác minh response của `GraphQlTester`, không phải server error handler.
- `errors().filter(...)` bỏ qua error khớp predicate nhưng không yêu cầu error phải xuất hiện.
- `errors().expect(...)` yêu cầu ít nhất một error khớp và vẫn phát hiện error ngoài dự kiến.
- `errors().satisfy(...)` cho phép kiểm tra toàn bộ danh sách và đánh dấu tất cả errors đã được xử lý.
- `Builder.errorFilter(...)` áp dụng predicate cho mọi request của tester.
- `ResponseError` cung cấp message, path, parsed path, locations, error type và extensions.
- Ưu tiên kiểm tra path cùng `extensions.code` thay vì chỉ dựa vào message.
- Path dùng alias và list index theo response.
- Phải xử lý errors trước khi kiểm tra data path.
- Predicate rộng hoặc filter toàn cục thiếu kiểm soát có thể che giấu regression.

Error filter giúp viết test GraphQL chính xác hơn khi response có partial data hoặc những lỗi đã được dự kiến. Khi chọn đúng giữa `filter`, `expect` và `satisfy`, đồng thời giới hạn predicate theo path và mã lỗi, test vừa kiểm tra được dữ liệu hợp lệ vừa tiếp tục phát hiện những lỗi ngoài dự kiến.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQlTester.Errors API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html)
- [ResponseError API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/ResponseError.html)

