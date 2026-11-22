# Batch mapping type name

Trong Spring for GraphQL, `@BatchMapping` đăng ký một resolver theo lô cho field của GraphQL object type. Thuộc tính `typeName` xác định **GraphQL type chứa field cần resolve**. Đây là thông tin giúp Spring biết batch method đang xử lý field của kiểu nào, đặc biệt khi tên class Java không trùng với tên type trong schema hoặc khi cần ánh xạ tường minh.

Ví dụ, field `author` thuộc GraphQL type `Book` được biểu diễn bằng `@BatchMapping(typeName = "Book", field = "author")`. Method nhận danh sách các object nguồn `Book`, tải các tác giả trong một lần gọi và trả kết quả ánh xạ lại cho từng cuốn sách.

## 1. `typeName` xác định GraphQL type cha

Giả sử schema có quan hệ giữa sách và tác giả:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Field `author` nằm bên trong object type `Book`. Vì vậy, khi đăng ký batch resolver cho field này, `typeName` là `Book`:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    // Tải tác giả cho nhiều sách trong một lần.
}
```

Có thể đọc annotation theo cấu trúc:

- `typeName = "Book"`: GraphQL object type sở hữu field.
- `field = "author"`: field cần được batch resolve trên type đó.
- `List<Book> books`: các object nguồn mà field `author` cần được resolve.
- `Map<Book, Author>`: kết quả ghép từng object nguồn với giá trị của field tương ứng.

Do đó, `typeName` là tên kiểu cha trong SDL. Nó không phải tên kiểu trả về `Author`, không phải tên Java package và cũng không phải tên controller.

## 2. Khai báo `@BatchMapping` với typeName tường minh

Ví dụ đầy đủ với Java record:

```java
public record Book(
    String id,
    String title,
    Long authorId
) {}

public record Author(
    String id,
    String name
) {}
```

Batch controller:

```java
package com.example.graphql.book;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<Long> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

        Map<Long, Author> authorsById =
            authorService.findMapByIds(authorIds);

        Map<Book, Author> result = new LinkedHashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

`AuthorService.findMapByIds` ở đây đại diện cho một phương thức tải nhiều tác giả theo danh sách ID và trả về map `authorId -> Author`. Batch method sau đó xây map `Book -> Author` để Spring for GraphQL ghép kết quả với từng source object.

Đoạn code dùng `LinkedHashMap` để giữ thứ tự khi đọc và cho phép giá trị null nếu một tác giả không tồn tại. Tuy vậy, quan trọng nhất với kết quả dạng map là key phải khớp đúng source object được đưa vào batch. Field `author` trong schema đang nullable, nên một sách không có tác giả có thể nhận null theo hợp đồng này.

## 3. Phân biệt typeName và field

Hai thuộc tính `typeName` và `field` giải quyết hai phần khác nhau của mapping:

| Thuộc tính | Xác định | Ví dụ |
| --- | --- | --- |
| `typeName` | GraphQL type chứa field | `Book` |
| `field` | Tên field trên GraphQL type đó | `author` |

Kết hợp hai giá trị tạo ra địa chỉ mapping `Book.author`. Có thể hình dung nó tương tự đường dẫn type/field trong schema:

```text
Book
 ├── id
 ├── title
 └── author  <-- batch mapping
```

Nếu chỉ khai báo `typeName = "Book"` và bỏ `field`, Spring suy ra tên field từ tên method. Nếu method tên `author`, mapping là `Book.author`.

```java
@BatchMapping(typeName = "Book")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Nếu method tên khác field trong SDL, cần khai báo `field` tường minh:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Trong ví dụ thứ hai, tên method `loadAuthors` không phải tên GraphQL field. `field = "author"` mới là giá trị quyết định mapping.

## 4. Khi nào Spring có thể suy luận typeName?

`typeName` là thuộc tính tùy chọn. Nếu không khai báo, Spring for GraphQL có thể suy luận GraphQL type từ kiểu source trong tham số collection của batch method.

Ví dụ:

```java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Vì source type là `Book`, Spring có thể suy ra type chứa field là `Book`; tên method `author` được dùng để suy ra field. Đây là cách viết ngắn khi tên kiểu Java phù hợp với tên GraphQL type.

Việc suy luận thuận tiện trong trường hợp đơn giản, nhưng không phải lúc nào tên Java cũng giống tên GraphQL. Nếu model Java là `BookEntity`, `BookView` hoặc một lớp domain khác trong khi SDL dùng `Book`, cần khai báo `typeName` rõ ràng để tránh Spring suy ra tên type không tồn tại trong schema.

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookEntity, AuthorView> author(List<BookEntity> books) {
    return authorService.findByBookEntities(books);
}
```

Ở đây `BookEntity` là kiểu Java của source object; `Book` là tên GraphQL type chứa field. Hai tên không cần giống nhau, vì annotation đã xác định mapping một cách tường minh.

## 5. `typeName` không phải kiểu Java trả về

Một nhầm lẫn thường gặp là lấy tên class của giá trị trả về làm `typeName`. Điều này sai vì `typeName` chỉ đến object type sở hữu field.

Với schema:

```graphql
type Book {
    id: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Mapping đúng:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

`Book` là type cha chứa field `author`; `Author` là kiểu giá trị của field. Nếu viết `typeName = "Author"`, Spring sẽ tìm field `author` trên type `Author`, tức mapping sai vị trí so với SDL.

Hãy luôn xác định mapping bằng cách nhìn vào nơi field được khai báo trong SDL. Field nằm trong block `type X { ... }` thì `typeName` phải chỉ tới `X`.

## 6. Nhiều type có field cùng tên

Một schema có thể khai báo nhiều object type với field trùng tên. Ví dụ cả `Book` và `Magazine` đều có field `publisher`:

```graphql
type Book {
    id: ID!
    publisher: Publisher
}

type Magazine {
    id: ID!
    publisher: Publisher
}
```

Hai field cùng tên nhưng có thể cần cách tải dữ liệu khác nhau. `typeName` giúp phân biệt rõ:

```java
@BatchMapping(typeName = "Book", field = "publisher")
public Map<Book, Publisher> bookPublishers(List<Book> books) {
    return publisherService.findForBooks(books);
}

@BatchMapping(typeName = "Magazine", field = "publisher")
public Map<Magazine, Publisher> magazinePublishers(List<Magazine> magazines) {
    return publisherService.findForMagazines(magazines);
}
```

Mặc dù cả hai method cùng xử lý field `publisher`, mapping được xác định bởi cặp type/field: `Book.publisher` và `Magazine.publisher`. Đây là lý do nên khai báo `typeName` tường minh khi controller xử lý nhiều GraphQL type hoặc khi các field cùng tên có logic riêng.

## 7. Type name phải khớp tên trong SDL

GraphQL type name phân biệt chữ hoa/chữ thường. Nếu SDL khai báo `type Book`, annotation phải dùng đúng `"Book"`, không phải `"book"` hoặc `"BOOK"`.

Ví dụ:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    author: Author
}
```

Mapping:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Nếu annotation dùng `typeName = "book"`, mapping không trỏ đến GraphQL type đã khai báo. Tương tự, nếu đổi tên type trong SDL nhưng quên cập nhật annotation, resolver có thể không được gắn vào field mong đợi.

Khi schema được chia thành nhiều file, hãy tìm định nghĩa type thực tế trong SDL được nạp. Tên file hoặc tên package Java không quyết định `typeName`.

## 8. Kết quả batch phải khớp với source objects

`typeName` giúp chọn đúng GraphQL field, nhưng không thay đổi hợp đồng dữ liệu đầu vào và đầu ra của batch method.

Với `@BatchMapping`, method thường nhận một danh sách source object. Có thể trả về:

- `Map<Source, Value>`: map mỗi source object với kết quả tương ứng.
- `List<Value>`: danh sách kết quả theo đúng thứ tự của danh sách source đầu vào.

Ví dụ trả list:

```java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    List<Long> ids = books.stream()
        .map(Book::authorId)
        .toList();
    return authorService.findInSameOrder(ids);
}
```

Nếu dùng `List<Value>`, service phải trả kết quả theo đúng thứ tự của `books`. Không giả định câu truy vấn `WHERE id IN (...)` tự giữ thứ tự của input IDs. Nếu không thể bảo đảm thứ tự, dùng map hoặc xây lại list theo danh sách đầu vào.

Với `Map<Source, Value>`, key phải là source object tương ứng chứ không phải tùy ý dùng ID, trừ khi chữ ký/adapter được thiết kế riêng cho key đó. `@BatchMapping` ánh xạ kết quả trở lại các parent object; sai key có thể khiến field trả null.

## 9. Dùng typeName với DTO hoặc entity có tên khác

Trong kiến trúc nhiều lớp, Java class thường có hậu tố để phân biệt persistence entity, domain model và API view:

```java
public record BookView(
    String id,
    Long authorId
) {}

public record AuthorView(
    String id,
    String name
) {}
```

SDL vẫn có thể giữ tên ngắn và ổn định:

```graphql
type Book {
    id: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Khai báo tường minh:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookView, AuthorView> author(List<BookView> books) {
    return authorService.findViewsForBooks(books);
}
```

`typeName` giúp tách hợp đồng GraphQL khỏi tên class Java. Nhờ đó, có thể đổi `BookView` thành một DTO khác mà không cần đổi tên type công khai trong SDL, miễn mapping vẫn được cập nhật phù hợp.

## 10. Phân biệt @BatchMapping và @SchemaMapping về typeName

Hai annotation cùng mô tả field thuộc một GraphQL type, nhưng cách thực thi khác nhau:

| Annotation | Tham số source | Kết quả thường gặp | Mục đích |
| --- | --- | --- | --- |
| `@SchemaMapping` | Một source object, ví dụ `Book` | Một `Author` hoặc kiểu async tương ứng | Resolve field riêng cho một parent |
| `@BatchMapping` | Danh sách source object, ví dụ `List<Book>` | `Map<Book, Author>` hoặc `List<Author>` | Gom việc resolve field cho nhiều parent |

Ví dụ mapping đơn:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

Ví dụ batch mapping:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> authors(List<Book> books) {
    return authorService.findByBooks(books);
}
```

Trong cả hai trường hợp, `typeName = "Book"` đều chỉ type cha chứa field `author`. Khác biệt là batch mapping nhận nhiều parent và xử lý dữ liệu theo lô nhằm giảm N+1.

Không đăng ký đồng thời cả hai method cho cùng cặp `Book.author` nếu không có chủ đích rõ ràng. Hãy chọn một cơ chế resolve cho field đó để tránh mapping trùng.

## 11. Type name và interface hoặc union

Interface và union cho phép field xuất hiện trên các kiểu dữ liệu đa hình, nhưng cần phân biệt nơi field được khai báo trong schema.

Nếu field được khai báo trên một interface:

```graphql
interface Publication {
    id: ID!
    publisher: Publisher
}

type Book implements Publication {
    id: ID!
    publisher: Publisher
}
```

Field `publisher` thuộc interface `Publication`; một mapping cho field được khai báo trên interface cần dùng đúng GraphQL type sở hữu field theo schema và runtime wiring của ứng dụng. Nếu thay vào đó schema khai báo field riêng trên từng object type, mỗi mapping phải chỉ rõ object type tương ứng.

Union không khai báo field chung, vì vậy không có field trực tiếp trên union để gắn batch mapping. Client phải dùng fragment để truy cập field của các object type thành viên; mapping batch cần nhắm tới field trên object type cụ thể hoặc interface tương ứng.

Trong các schema đa hình phức tạp, hãy kiểm tra SDL và cách runtime type resolution trước khi quyết định `typeName`. Đừng suy luận `typeName` chỉ từ class Java trả về hoặc từ kiểu collection.

## 12. Kiểm thử typeName và batch mapping

Nên kiểm tra cả mapping đúng type/field và việc kết quả được ghép về đúng parent. Ví dụ dùng `GraphQlTester`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest({BookQueryController.class, BookBatchController.class})
class BookBatchMappingTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void resolvesAuthorForBookType() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
```

Ví dụ giả định test context cung cấp `BookService` và `AuthorService` mock hoặc test bean với dữ liệu tương ứng. Test xác minh field `Book.author` được resolve. Có thể dùng Mockito để xác nhận batch service nhận nhiều ID trong một lần gọi, thay vì gọi riêng cho từng sách.

Nên có thêm test khi:

- Java source class có tên khác GraphQL `typeName`.
- Method name khác field và dùng `field` tường minh.
- Hai GraphQL type có cùng tên field nhưng hai batch mapping riêng.
- Batch result là Map và có source không có value tương ứng.
- Batch result là List và thứ tự đầu ra cần được bảo đảm.
- SDL đổi tên type hoặc field.
- Mapping được khai báo trên interface hoặc object type cụ thể.

## 13. Lỗi thường gặp khi cấu hình typeName

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field không được batch resolve | `typeName` không trùng tên type trong SDL | Kiểm tra đúng tên GraphQL type và chữ hoa/chữ thường |
| Field bị ánh xạ vào sai nơi | Dùng tên kiểu trả về thay vì kiểu cha | Xác định block SDL chứa field rồi dùng tên block đó |
| Spring suy ra type không tồn tại | Tên Java source class khác tên GraphQL type | Khai báo `typeName` tường minh |
| Method không khớp field | Tên method khác field nhưng bỏ `field` | Chỉ định `field` rõ ràng |
| Hai mapping cùng xử lý một field | Có `@SchemaMapping` và `@BatchMapping` trùng type/field | Chọn một resolver phù hợp |
| Field trả null không mong đợi | Map key không phải source object hoặc list sai thứ tự | Ghép lại kết quả theo đúng source objects |
| Một field cùng tên ở nhiều type bị nhầm | Không phân biệt type cha | Khai báo `typeName` cho từng mapping |

Khi chẩn đoán, hãy mở SDL và xác định field nằm trong type nào trước. Sau đó so sánh cặp `typeName`/`field` trong annotation, kiểm tra source parameter của batch method và xác minh controller có được Spring phát hiện. Cách này thường tìm ra lỗi nhanh hơn việc sửa service hoặc thay đổi DataLoader một cách ngẫu nhiên.

## 14. Checklist chọn typeName

- Đã xác định chính xác GraphQL type chứa field cần batch resolve?
- `typeName` có khớp tên type trong SDL, bao gồm chữ hoa/chữ thường?
- Có thể suy luận an toàn từ source type của tham số collection không?
- Java source class có tên khác GraphQL type không; nếu có đã khai báo tường minh chưa?
- `field` có trùng tên field trong type đó hay cần khai báo rõ?
- Đã phân biệt type cha với kiểu value trả về chưa?
- Khi nhiều type có field trùng tên, mỗi mapping đã xác định đúng `typeName` chưa?
- Kết quả Map dùng đúng source object làm key hoặc List giữ đúng thứ tự source?
- Có mapping trùng với `@SchemaMapping` hoặc batch resolver khác không?
- Test đã xác minh đúng cặp type/field và kết quả cho nhiều parent chưa?

`typeName` trong `@BatchMapping` xác định GraphQL type sở hữu field cần batch resolve. Spring có thể suy luận tên type từ source type của method trong trường hợp tên Java và tên SDL phù hợp; khi dùng DTO/entity có tên khác, nhiều type có field trùng nhau hoặc muốn mapping rõ ràng, hãy khai báo `typeName` tường minh. Kết hợp đúng `typeName`, `field` và kết quả Map/List tương ứng với source objects giúp batch resolver được gắn đúng vị trí trong schema và trả dữ liệu chính xác cho từng parent.
