# Assert errors với GraphQlTester

GraphQL response có thể chứa cả `data` và `errors`. Vì vậy, kiểm thử một operation không chỉ là kiểm tra giá trị trả về; test còn cần xác nhận lỗi nào xuất hiện, lỗi gắn với field nào, có mã phân loại phù hợp hay không và những field khác có giữ được partial data hay không. Spring for GraphQL cung cấp `GraphQlTester` với API `errors()` để kiểm tra các tình huống này.

`errors()` cho phép xác nhận response không có lỗi hoặc đọc danh sách `ResponseError` để kiểm tra các lỗi mong đợi. Với lỗi được xem là một phần của contract, nên assert các thuộc tính có cấu trúc như `path` và `extensions.code`, thay vì chỉ so sánh toàn bộ message. Message thường thay đổi theo cách diễn đạt hoặc ngôn ngữ; path và error code thường ổn định hơn cho client.

Sau bài này, bạn có thể:

- Hiểu `GraphQlTester.Errors` và các cách assert errors.
- Xác nhận một operation không có GraphQL error.
- Kiểm tra lỗi mong đợi bằng `satisfy(...)`.
- Assert message, path, error code và metadata trong extensions.
- Phân biệt request error với execution error.
- Kiểm tra partial data và null propagation khi có lỗi.
- Xác nhận nhiều lỗi, alias và list index.
- Tổ chức helper để assertion lỗi nhất quán giữa các test.

## 1. GraphQL response có thể có data và errors

Một response thành công thường có `data`:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

Khi một field gặp lỗi trong quá trình execution, GraphQL vẫn có thể trả các field khác:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "path": ["book", "author"],
      "extensions": {
        "code": "UPSTREAM_UNAVAILABLE"
      }
    }
  ]
}
```

Trong ví dụ, `book.title` vẫn có dữ liệu nhưng `book.author` bị lỗi. Test cần xác nhận cả hai điều: lỗi có xuất hiện đúng như mong đợi và field `title` vẫn được trả về.

Không nên coi mọi response có `errors` là thất bại hoàn toàn. Cũng không nên bỏ qua `errors` chỉ vì `data` có mặt. Hai phần này mô tả hai khía cạnh của cùng một execution result.

## 2. GraphQlTester.Errors là gì?

Sau khi thực thi operation, `GraphQlTester.Response.errors()` trả về API `GraphQlTester.Errors` để kiểm tra danh sách GraphQL errors.

```java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "missing") {
                title
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).isNotEmpty();
});
```

`errors()` không phải là exception Java mà là cách truy cập lỗi trong GraphQL response. Đây là điểm khác biệt quan trọng: execution error thường được biểu diễn trong response `errors`, không nhất thiết làm lời gọi `execute()` ném exception như lỗi kết nối hoặc lỗi transport.

Các cách kiểm tra phổ biến:

- `verify()`: xác nhận response không còn GraphQL errors chưa được xử lý.
- `satisfy(...)`: nhận toàn bộ danh sách lỗi để viết assertion tùy ý.
- `expect(...)`: khai báo lỗi mong đợi; test thất bại nếu không có lỗi nào khớp predicate.
- `filter(...)`: bỏ qua những lỗi có thể chấp nhận; predicate không bắt buộc phải khớp ít nhất một lỗi.

Khi test cần xác nhận một lỗi cụ thể và các thuộc tính của nó, `satisfy(...)` là cách trực tiếp, dễ đọc.

## 3. Xác nhận response không có lỗi

Với một query được kỳ vọng thành công hoàn toàn, gọi `verify()`:

```java
@Test
void loadsBookWithoutErrors() {
    graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                }
            }
            """)
        .execute()
        .errors()
        .verify();
}
```

`verify()` làm test thất bại nếu response chứa GraphQL errors chưa được xử lý. Sau đó, nếu cần, có thể tiếp tục kiểm tra data trên response trong cùng assertion chain bằng cách giữ response ở biến riêng.

Ví dụ kiểm tra cả không có lỗi và giá trị field:

```java
@Test
void loadsBookTitle() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "book-42") {
                    title
                }
            }
            """)
        .execute();

    response.errors().verify();
    response.path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL in Practice");
}
```

Nên dùng `verify()` khi hợp đồng của operation yêu cầu không có lỗi. Nếu operation được thiết kế để trả partial data và một số lỗi dự kiến, hãy kiểm tra các lỗi đó rõ ràng thay vì gọi `verify()` một cách máy móc.

## 4. Kiểm tra lỗi mong đợi bằng satisfy

Giả sử service ném `BookNotFoundException` và exception handler ánh xạ thành message `Book not found` cùng code `BOOK_NOT_FOUND`.

```java
@Test
void reportsBookNotFound() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                    title
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
                .isEqualTo("Book not found");
    });
}
```

`satisfy(...)` cho phép dùng AssertJ để kiểm tra toàn bộ danh sách. Assertion `hasSize(1)` bảo đảm test không bỏ sót lỗi phụ ngoài lỗi mong đợi.

Nếu message là nội dung công khai nhưng không phải contract ổn định, có thể kiểm tra một phần hoặc ưu tiên kiểm tra `extensions.code`. Tránh so sánh stack trace hay message nội bộ phụ thuộc database, framework hoặc môi trường.

## 5. Assert error code trong extensions

Ứng dụng thường đưa mã lỗi ổn định vào `extensions`, ví dụ:

```json
{
  "message": "Book not found",
  "extensions": {
    "code": "BOOK_NOT_FOUND"
  }
}
```

Test kiểm tra code:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
```

`extensions` là map metadata. Chỉ assert những key mà API cam kết cung cấp. Không nên khóa test vào timestamp, trace ID hoặc metadata thay đổi theo mỗi lần chạy trừ khi test đang xác minh chính những giá trị đó.

Error code giúp client chọn hành động mà không cần phân tích `message`. Ví dụ `BOOK_NOT_FOUND`, `FORBIDDEN` hoặc `UPSTREAM_UNAVAILABLE` có thể được dùng làm contract máy đọc được.

## 6. Assert path của field bị lỗi

`path` chỉ ra field trong response tree nơi execution error phát sinh. Ví dụ query:

```graphql
query {
    book(id: "book-42") {
        author {
            name
        }
    }
}
```

Nếu resolver của `name` lỗi, path có thể là `["book", "author", "name"]`.

```java
response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error -> {
        assertThat(error.getParsedPath())
                .containsExactly("book", "author", "name");
    });
});
```

Các segment trong path có thể là chuỗi field response key hoặc số nguyên chỉ số list. Hãy giữ nguyên kiểu dữ liệu khi assert. Không chuyển index thành chuỗi.

Trong Spring for GraphQL, lỗi nhận được trong `GraphQlTester.Errors` có kiểu `ResponseError`. Dùng `getParsedPath()` để lấy danh sách segment đã parse với kiểu `String` và `Integer`; `getPath()` trả về biểu diễn dạng chuỗi.

Path là một phần hữu ích của error contract khi client cần đánh dấu đúng field bị lỗi trong giao diện hoặc phân tích lỗi theo nhánh response.

## 7. Alias ảnh hưởng đến path

GraphQL alias đổi response key. Path dùng alias, không dùng tên field trong schema.

Query:

```graphql
query {
    featured: book(id: "book-42") {
        writer: author {
            name
        }
    }
}
```

Nếu `name` lỗi, path là:

```json
["featured", "writer", "name"]
```

Test:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getParsedPath())
                    .containsExactly("featured", "writer", "name"));
});
```

Nếu query đổi alias, assertion path cũng phải đổi theo. Không dùng `book.author.name` khi response key thực tế là `featured.writer.name`.

## 8. Assert path có list index

Khi field nằm trong một phần tử list, path chứa index bắt đầu từ `0`.

```graphql
query {
    books {
        author {
            name
        }
    }
}
```

Nếu `name` của tác giả thuộc cuốn sách thứ hai lỗi, path có thể là:

```json
["books", 1, "author", "name"]
```

Test:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getParsedPath())
                    .containsExactly("books", 1, "author", "name"));
});
```

Nên tạo fixture có ít nhất hai phần tử để xác nhận index đúng. Test chỉ có một phần tử luôn nhận index `0` và có thể không phát hiện lỗi khi server gán nhầm item.

## 9. Assert nhiều lỗi trong cùng response

Một operation có thể phát sinh nhiều execution errors, ví dụ hai field độc lập cùng gọi các service khác nhau và cả hai đều thất bại.

```graphql
query Dashboard {
    profile {
        displayName
    }
    recommendations {
        id
    }
    notifications {
        id
    }
}
```

Test có thể kiểm tra số lượng lỗi và tập error code:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(2);

    assertThat(errors)
            .extracting(error -> error.getExtensions().get("code"))
            .containsExactlyInAnyOrder(
                    "RECOMMENDATIONS_UNAVAILABLE",
                    "NOTIFICATIONS_UNAVAILABLE");
});
```

Khi thứ tự lỗi không phải một phần của contract, dùng assertion không phụ thuộc thứ tự. Nếu thứ tự quan trọng với ứng dụng, cần xác định rõ GraphQL execution/transport có bảo đảm thứ tự đó hay không trước khi viết test.

Không chỉ assert `errors().isNotEmpty()` nếu test cần xác nhận đúng loại lỗi. Một lỗi validation hoặc authorization bất ngờ cũng có thể làm assertion quá rộng này pass.

## 10. Phân biệt request error và execution error

Request error xảy ra trước khi GraphQL thực thi resolver, ví dụ query gọi field không tồn tại hoặc variable không hợp lệ. Execution error xảy ra khi resolver đang chạy.

| Loại | Ví dụ | Path |
| --- | --- | --- |
| Parse error | SDL document/query sai cú pháp | Thường không có |
| Validation error | Gọi field không tồn tại | Thường không có |
| Variable coercion error | Gửi chuỗi vào `Int!` | Thường không có |
| Execution error | Service lỗi khi resolve `book.author` | Thường có path |

Test validation error:

```java
@Test
void rejectsUnknownField() {
    graphQlTester.document("""
            query {
                book(id: "book-42") {
                    titel
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertThat(errors).anySatisfy(error ->
                    assertThat(error.getMessage())
                            .contains("Cannot query field"));
            assertThat(errors.get(0).getParsedPath()).isEmpty();
        });
}
```

Không nên bắt buộc mọi error phải có path. Request error thường chưa có field execution cụ thể để gắn path.

## 11. Kiểm tra null propagation cùng errors

Khi field non-null phát sinh lỗi, GraphQL đẩy null lên parent gần nhất có thể nhận null. Error path vẫn chỉ field ban đầu.

Giả sử schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    title: String!
    author: Author
}

type Author {
    name: String!
}
```

Nếu `Author.name` lỗi, object `Author` trở thành null; vì `Book.author` nullable, object `Book` vẫn còn. Test có thể kiểm tra:

```java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getParsedPath())
                    .containsExactly("book", "author", "name"));
}).path("book", book -> {
    book.path("title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL in Practice");
    book.path("author").valueIsNull();
});
```

Test phải khớp nullability thực tế trong SDL. Nếu `Query.book` cũng non-null, lỗi có thể lan lên root và `data` trở thành null; khi đó không thể đọc `book.title`.

## 12. Assert partial data và lỗi dự kiến

Một test tốt cho partial data xác nhận cả ba điều:

1. Lỗi mong đợi xuất hiện.
2. `path` và `extensions.code` chỉ đúng field bị lỗi.
3. Các field độc lập vẫn có dữ liệu.

Ví dụ:

```java
@Test
void returnsBookTitleWhenAuthorLookupFails() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "book-42") {
                    title
                    author {
                        name
                    }
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).singleElement().satisfies(error -> {
            assertThat(error.getExtensions())
                    .containsEntry("code", "AUTHOR_UNAVAILABLE");
            assertThat(error.getParsedPath())
                    .containsExactly("book", "author");
        });
    }).path("book", book -> {
        book.path("title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL in Practice");
        book.path("author").valueIsNull();
    });
}
```

Ví dụ giả định resolver của `author` ném lỗi trực tiếp, field `author` nullable và exception handler cung cấp code `AUTHOR_UNAVAILABLE`. Nếu lỗi xảy ra sâu hơn tại `Author.name`, path sẽ có thêm segment `name`.

## 13. Khai báo errors mong đợi hoặc bỏ qua lỗi có thể chấp nhận

Khi test yêu cầu một lỗi cụ thể phải xuất hiện, dùng `expect(...)`:

```java
response.errors()
        .expect(error -> "BOOK_NOT_FOUND".equals(
                error.getExtensions().get("code")))
        .verify();
```

`expect(...)` đánh dấu lỗi khớp predicate là lỗi được dự kiến, yêu cầu ít nhất một lỗi phải khớp và sau đó `verify()` vẫn làm test thất bại nếu còn lỗi không mong đợi.

`filter(...)` có semantics khác: nó bỏ qua lỗi khớp predicate nếu lỗi đó xuất hiện, nhưng không yêu cầu lỗi phải xuất hiện. Cách này phù hợp với warning/notification có thể có hoặc không:

```java
response.errors()
        .filter(error -> "DEPRECATION_NOTICE".equals(
                error.getExtensions().get("code")))
        .verify();
```

Trong ví dụ, `verify()` xác nhận không còn lỗi nào ngoài nhóm `DEPRECATION_NOTICE` đã được cho phép. Nếu cần khẳng định `BOOK_NOT_FOUND` thật sự có mặt, hãy dùng `expect(...)` hoặc `satisfy(...)` với assertion rõ ràng.

Nếu mục tiêu là kiểm tra đầy đủ danh sách lỗi, `satisfy(...)` rõ ràng hơn vì callback nhận danh sách để assert số lượng, code và path. Tránh dùng filter để che mọi lỗi bằng một predicate quá rộng như `error -> true`.

## 14. Phân biệt expected errors và unexpected errors

Một số test cố ý tạo lỗi. Điều đó không có nghĩa test nên bỏ qua mọi error. Hãy định nghĩa rõ lỗi nào được mong đợi và bảo đảm lỗi ngoài dự kiến vẫn làm test thất bại.

Ví dụ, operation có thể chấp nhận `BOOK_NOT_FOUND`, nhưng không chấp nhận `INTERNAL_ERROR` hoặc `FORBIDDEN`:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
```

Assertion số lượng cùng code làm test chặt chẽ hơn so với chỉ kiểm tra có ít nhất một lỗi. Nếu response có thêm lỗi bất ngờ, test sẽ thất bại.

Với query trả nhiều nhánh độc lập, có thể assert tập code mong đợi bằng `containsExactlyInAnyOrder`. Điều này vừa cho phép nhiều lỗi dự kiến, vừa không bỏ qua lỗi lạ.

## 15. Tạo helper assertion dùng lại

Nếu nhiều test cần kiểm tra cùng một error code, có thể tạo helper nhỏ:

```java
import org.springframework.graphql.ResponseError;

static void assertSingleGraphQlError(
        GraphQlTester.Response response,
        String expectedCode,
        List<?> expectedPath) {

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        ResponseError error = errors.get(0);
        assertThat(error.getExtensions())
                .containsEntry("code", expectedCode);
        assertThat(error.getParsedPath()).containsExactlyElementsOf(expectedPath);
    });
}
```

Sử dụng:

```java
assertSingleGraphQlError(
        response,
        "AUTHOR_UNAVAILABLE",
        List.of("book", "author"));
```

Helper nên giữ assertion cụ thể và không che mất context khi test thất bại. Nếu message lỗi cần được kiểm tra ở một số test, thêm tham số hoặc viết assertion riêng ở test đó thay vì biến helper thành một framework tổng quát khó hiểu.

## 16. Assert classification và error type

Spring for GraphQL có thể phân loại lỗi bằng `ErrorType`, ví dụ `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND` hoặc `INTERNAL_ERROR`. Ứng dụng có thể dùng classification này cùng error code riêng trong `extensions`.

Khi classification là một phần của contract, có thể kiểm tra:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).singleElement().satisfies(error -> {
        assertThat(error.getErrorType())
                .isEqualTo(ErrorType.NOT_FOUND);
        assertThat(error.getExtensions())
                .containsEntry("code", "BOOK_NOT_FOUND");
    });
});
```

Nếu dự án không cam kết `ErrorType` cụ thể với client, hãy kiểm tra `extensions.code` hoặc message public đã thống nhất. Không cần khóa test vào chi tiết implementation của exception resolver nếu đó không phải contract.

## 17. Assert lỗi authorization

Khi method security từ chối một field trong lúc GraphQL execution, response có thể có GraphQL error với code `FORBIDDEN`:

```java
@Test
@WithMockUser(authorities = "PROFILE_READ")
void deniesBookRead() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                books {
                    id
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).singleElement().satisfies(error -> {
            assertThat(error.getExtensions())
                    .containsEntry("code", "FORBIDDEN");
        });
    });
}
```

Test cần bật method security trong Spring context và cấu hình exception handler để ánh xạ access denied thành code dự kiến. Nếu request bị chặn ở HTTP security filter trước khi GraphQL execution bắt đầu, `ExecutionGraphQlServiceTester` không kiểm tra được response HTTP 401/403; cần test qua HTTP transport.

## 18. Assert errors trong mutation

Mutation có thể thất bại do validation, conflict, thiếu quyền hoặc lỗi dependency. Test nên phân biệt GraphQL execution error với lỗi nghiệp vụ nằm trong payload.

Nếu API dùng GraphQL errors:

```java
response.errors().satisfy(errors -> {
    assertThat(errors).singleElement().satisfies(error -> {
        assertThat(error.getExtensions())
                .containsEntry("code", "ORDER_CONFLICT");
    });
});
```

Nếu API biểu diễn lỗi nghiệp vụ bằng `userErrors` trong payload, response có thể không có GraphQL errors:

```java
response.errors().verify()
        .path("createOrder.userErrors[0].code")
        .entity(String.class)
        .isEqualTo("COUPON_EXPIRED");
```

Không assert `errors()` cho một lỗi nghiệp vụ được thiết kế là payload rồi kết luận server sai. Hãy test theo contract đã chọn và giữ cách biểu diễn nhất quán.

## 19. Kiểm tra lỗi trong list và nhiều nested field

Một response có thể chứa nhiều lỗi ở những phần tử khác nhau. Ví dụ một query trả danh sách sách, nhưng hai resolver tác giả lỗi ở index khác nhau.

```java
import org.springframework.graphql.ResponseError;

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(2);
    assertThat(errors)
            .extracting(ResponseError::getParsedPath)
            .containsExactlyInAnyOrder(
                    List.of("books", 0, "author"),
                    List.of("books", 2, "author"));
});
```

Assertion này kiểm tra tập path không phụ thuộc thứ tự. Nếu thứ tự lỗi là điều test cần xác minh, dùng `containsExactly(...)` và bảo đảm thứ tự đó là một phần của hành vi được cam kết.

Với alias trong list:

```graphql
query {
    catalog: books {
        writer: author {
            name
        }
    }
}
```

Path tương ứng có thể là `["catalog", 1, "writer", "name"]`. Test nên assert đúng response key thay vì tên schema field.

## 20. Kiểm tra request errors không có path

Request error như field validation error hoặc variable coercion error xảy ra trước khi resolver chạy. Path thường không có giá trị.

```java
@Test
void reportsValidationErrorWithoutPath() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "book-42") {
                    unknownField
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).isNotEmpty();
        assertThat(errors).allSatisfy(error ->
                assertThat(error.getParsedPath()).isEmpty());
    });
}
```

Không áp dụng assertion path bắt buộc cho tất cả error. Với execution error, path thường có; với request error, path có thể vắng mặt. Test cần phản ánh giai đoạn lỗi.

Nếu cần xác nhận resolver không chạy, dùng mock/spy service và verify không có invocation. Chỉ kiểm tra path null chưa chứng minh resolver không được gọi.

## 21. Phân biệt GraphQL errors với lỗi transport

`GraphQlTester.Errors` kiểm tra lỗi nằm trong GraphQL response. Lỗi transport như timeout, connection refused, TLS handshake failure hoặc HTTP response không thể parse thành GraphQL response có thể được biểu diễn bằng exception từ client/tester thay vì phần tử `errors`.

| Loại lỗi | Nơi kiểm tra |
| --- | --- |
| Resolver ném exception | `response.errors()` |
| Query validation error | `response.errors()` |
| Variable coercion error | `response.errors()` |
| Field authorization trong execution | `response.errors()` |
| HTTP 503 trước GraphQL response | HTTP/client exception hoặc transport response |
| Connection timeout | Reactor/client exception |
| WebSocket disconnect | WebSocket client/test lifecycle |

Không dùng `errors()` để kiểm tra lỗi mạng nếu chưa có GraphQL response. Với HTTP tester, có thể cần assert status code và body riêng. Với execution tester, transport không nằm trong phạm vi test.

## 22. Những lỗi thường gặp khi assert errors

- **Chỉ kiểm tra `isNotEmpty()`:** một lỗi bất kỳ cũng làm test pass, kể cả lỗi không mong đợi.
- **So sánh message quá chi tiết:** message có thể thay đổi theo ngôn ngữ hoặc implementation.
- **Không kiểm tra số lượng lỗi:** lỗi phụ có thể bị bỏ qua.
- **Bắt buộc mọi error có path:** request errors thường không có path.
- **Dùng schema field name thay alias trong path:** path dùng response key.
- **Chuyển list index thành string:** path segment index là số nguyên.
- **Bỏ qua partial data:** một field lỗi không đồng nghĩa toàn bộ data thất bại.
- **Nhầm null với error:** nullable field có thể null mà không có GraphQL error.
- **Dùng GraphQL errors để assert lỗi payload nghiệp vụ:** `userErrors` có thể là data bình thường.
- **Dùng errors() để kiểm tra timeout/HTTP failure:** đó là lỗi transport, không phải GraphQL error.
- **Lọc bỏ lỗi quá rộng:** filter có thể che giấu lỗi ngoài dự kiến.
- **Chỉ test execution error:** cần test request validation/coercion và transport ở tầng phù hợp.

## 23. Quy trình assert GraphQL errors

Khi viết test cho một operation có thể phát sinh lỗi, hãy thực hiện:

1. Xác định operation được kỳ vọng không có lỗi hay có lỗi dự kiến.
2. Nếu không có lỗi, gọi `response.errors().verify()`.
3. Nếu có lỗi, dùng `satisfy(...)` để kiểm tra số lượng và thuộc tính.
4. Assert `extensions.code` nếu error code là một phần của API contract.
5. Assert `path` theo response key, alias và list index thực tế.
6. Chỉ assert `locations` khi cần kiểm tra vị trí trong document.
7. Phân biệt request error không có path với execution error có path.
8. Kiểm tra partial data và null propagation theo SDL.
9. Không bỏ qua lỗi ngoài dự kiến khi dùng filter hoặc helper.
10. Test lỗi transport ở HTTP/WebSocket/client layer thay vì `errors()`.

`GraphQlTester.Errors` giúp kiểm tra GraphQL errors một cách có cấu trúc. `verify()` phù hợp với operation được kỳ vọng thành công hoàn toàn; `satisfy(...)` phù hợp khi test cần xác nhận lỗi mong đợi bằng số lượng, code, path hoặc classification. Kết hợp assertion errors với data, null propagation và phân biệt request/execution/transport error sẽ giúp test phát hiện đúng lỗi mà vẫn bảo vệ hành vi partial data của GraphQL.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [Spring for GraphQL — GraphQlTester.Errors API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html)
- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
