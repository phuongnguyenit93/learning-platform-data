# Custom scalar

GraphQL có một hệ kiểu dữ liệu rõ ràng để mô tả dữ liệu vào và dữ liệu ra của API. Năm scalar dựng sẵn gồm **Int**, **Float**, **String**, **Boolean** và **ID** đáp ứng nhiều trường hợp phổ biến. Tuy nhiên, ứng dụng thực tế thường có những giá trị mang ý nghĩa chuyên biệt như ngày lịch, thời điểm, UUID, tiền tệ hoặc dữ liệu có định dạng riêng. Khi các kiểu dựng sẵn không mô tả đủ hợp đồng dữ liệu, GraphQL cho phép định nghĩa **custom scalar**.

Custom scalar là một kiểu dữ liệu lá trong schema. Client sử dụng nó như một giá trị đơn, không truy vấn field con như với object type. Server quy định cách đọc giá trị đầu vào, kiểm tra tính hợp lệ, chuyển đổi sang kiểu nội bộ và tuần tự hóa kết quả trả về. Trong Spring for GraphQL, custom scalar thường được triển khai bằng **GraphQLScalarType** của GraphQL Java và đăng ký vào **RuntimeWiring**.

## Scalar dựng sẵn và nhu cầu custom scalar

GraphQL định nghĩa năm scalar chuẩn:

| Scalar | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Int** | Số nguyên có dấu 32-bit | 42 |
| **Float** | Số thực | 19.95 |
| **String** | Chuỗi ký tự | "Spring" |
| **Boolean** | Giá trị đúng hoặc sai | true |
| **ID** | Định danh, thường được truyền dưới dạng chuỗi | "book-101" |

Các scalar này có quy tắc tuần tự hóa và kiểm tra kiểu đã được GraphQL quy định. Chẳng hạn, ID phù hợp với mã định danh nhưng không diễn tả được định dạng UUID; String có thể chứa ngày tháng nhưng schema không thể hiện rõ chuỗi đó phải theo định dạng nào.

Giả sử API quản lý sách có ngày xuất bản. Nếu khai báo field là String, các giá trị sau đều có thể là chuỗi hợp lệ về mặt GraphQL:

~~~text
2025-04-18
18/04/2025
April 18, 2025
not-a-date
~~~

Nhưng chúng có ý nghĩa khác nhau hoặc không hợp lệ theo nghiệp vụ. Schema với kiểu Date biểu đạt ý định rõ hơn:

~~~graphql
scalar Date

type Book {
  id: ID!
  title: String!
  publishedOn: Date!
}
~~~

Custom scalar không tự định nghĩa mọi quy tắc nghiệp vụ của ứng dụng. Nó định nghĩa hình dạng wire format và cách chuyển đổi dữ liệu. Ví dụ, scalar Date có thể quy định client phải gửi chuỗi ISO-8601 yyyy-MM-dd, nhưng việc ngày đó có nằm trong khoảng được phép xuất bản hay không vẫn là validation nghiệp vụ ở service.

## Custom scalar hoạt động như thế nào?

Một scalar thường tham gia vào hai luồng:

- **Input:** client gửi giá trị qua biến hoặc viết trực tiếp trong GraphQL document. Server kiểm tra và chuyển giá trị đó thành kiểu Java nội bộ.
- **Output:** resolver trả về giá trị Java. Server kiểm tra và tuần tự hóa nó thành giá trị có thể gửi trong GraphQL response.

GraphQL Java định nghĩa các thao tác coercion thông qua interface Coercing. Ba phương thức quan trọng là:

| Phương thức | Hướng dữ liệu | Khi nào được gọi |
| --- | --- | --- |
| **serialize** | Java sang GraphQL response | Khi field trả về giá trị scalar |
| **parseValue** | Giá trị biến đầu vào sang Java | Khi operation dùng variables, thường đến từ JSON request |
| **parseLiteral** | Literal trong GraphQL document sang Java | Khi client ghi trực tiếp giá trị trong operation |

Ví dụ hai cách truyền ngày:

~~~graphql
query BooksByDate($date: Date!) {
  books(publishedAfter: $date) {
    id
    title
  }
}
~~~

Variables:

~~~json
{
  "date": "2025-04-18"
}
~~~

Trong trường hợp này GraphQL Java gọi parseValue để chuyển chuỗi trong variables thành kiểu Java mà scalar quy định.

Client cũng có thể truyền literal trực tiếp:

~~~graphql
query {
  books(publishedAfter: "2025-04-18") {
    id
    title
  }
}
~~~

Với cách viết này, GraphQL Java gọi parseLiteral. Khi resolver trả về một LocalDate, phương thức serialize chuyển ngày đó thành chuỗi yyyy-MM-dd trong response.

## Chọn định dạng và kiểu Java nội bộ

Trước khi viết scalar, hãy quyết định rõ định dạng dữ liệu được trao đổi giữa client và server. Một số lựa chọn thường gặp:

| Custom scalar | Wire format thường dùng | Kiểu Java có thể dùng |
| --- | --- | --- |
| **Date** | yyyy-MM-dd | LocalDate |
| **DateTime** | ISO-8601 có offset hoặc UTC | OffsetDateTime hoặc Instant |
| **UUID** | Chuỗi UUID chuẩn | UUID |
| **BigDecimal** | Chuỗi thập phân để giữ độ chính xác | BigDecimal |
| **Long** | Số nguyên ngoài phạm vi Int 32-bit | Long |

Định dạng phải nhất quán ở cả input và output. Với ngày lịch, LocalDate thường phù hợp vì không mang thông tin múi giờ. Với thời điểm trên dòng thời gian, hãy chọn Instant hoặc OffsetDateTime và quy định rõ offset hoặc cách chuẩn hóa UTC. Không nên dùng LocalDateTime cho một thời điểm toàn cầu nếu API không có quy tắc múi giờ đi kèm.

Với tiền tệ hoặc số thập phân cần độ chính xác, BigDecimal phù hợp hơn double. Nếu wire format dùng JSON number, một số client JavaScript có thể mất độ chính xác với số lớn hoặc số thập phân dài; dùng chuỗi có định dạng rõ ràng có thể an toàn hơn, nhưng client phải tuân thủ hợp đồng đó.

Không tạo custom scalar chỉ để đổi tên một kiểu mà không có quy tắc bổ sung. Nếu String hoặc ID đã biểu đạt đúng hợp đồng và không cần coercion riêng, dùng scalar dựng sẵn sẽ đơn giản hơn.

## Triển khai scalar Date bằng GraphQL Java

Ví dụ sau định nghĩa scalar Date dùng java.time.LocalDate. Scalar chấp nhận chuỗi ISO-8601 dạng yyyy-MM-dd cho cả variables và literal; output chỉ chấp nhận LocalDate.

~~~java
import graphql.language.StringValue;
import graphql.schema.Coercing;
import graphql.schema.CoercingParseLiteralException;
import graphql.schema.CoercingParseValueException;
import graphql.schema.CoercingSerializeException;
import graphql.schema.GraphQLScalarType;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public final class DateScalar {

    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ISO_LOCAL_DATE;

    private DateScalar() {
    }

    public static GraphQLScalarType create() {
        return GraphQLScalarType.newScalar()
                .name("Date")
                .description("Ngày lịch theo định dạng ISO-8601 yyyy-MM-dd")
                .coercing(new Coercing<LocalDate, String>() {

                    @Override
                    public String serialize(Object dataFetcherResult) {
                        if (dataFetcherResult instanceof LocalDate date) {
                            return FORMATTER.format(date);
                        }
                        throw new CoercingSerializeException(
                                "Date chỉ có thể serialize từ LocalDate");
                    }

                    @Override
                    public LocalDate parseValue(Object input) {
                        if (!(input instanceof String value)) {
                            throw new CoercingParseValueException(
                                    "Date input phải là chuỗi yyyy-MM-dd");
                        }
                        try {
                            return LocalDate.parse(value, FORMATTER);
                        } catch (DateTimeParseException ex) {
                            throw new CoercingParseValueException(
                                    "Date không hợp lệ; dùng định dạng yyyy-MM-dd");
                        }
                    }

                    @Override
                    public LocalDate parseLiteral(Object input) {
                        if (!(input instanceof StringValue stringValue)) {
                            throw new CoercingParseLiteralException(
                                    "Date literal phải là một chuỗi");
                        }
                        try {
                            return LocalDate.parse(stringValue.getValue(), FORMATTER);
                        } catch (DateTimeParseException ex) {
                            throw new CoercingParseLiteralException(
                                    "Date không hợp lệ; dùng định dạng yyyy-MM-dd");
                        }
                    }
                })
                .build();
    }
}
~~~

Các kiểu exception cho biết lỗi xảy ra ở hướng nào:

- **CoercingParseValueException** dành cho input đến từ variables.
- **CoercingParseLiteralException** dành cho literal không đúng kiểu hoặc không đúng định dạng.
- **CoercingSerializeException** dành cho giá trị resolver trả về không thể chuyển thành wire format.

Thông báo lỗi nên nói rõ định dạng mong đợi nhưng không chứa dữ liệu nhạy cảm hoặc chi tiết nội bộ. Đoạn code dùng các phương thức Coercing dạng cơ bản để dễ theo dõi; tùy phiên bản GraphQL Java được Spring Boot quản lý, API có thể cung cấp thêm overload nhận GraphQLContext, Locale và CoercedVariables. Khi triển khai, cần đối chiếu chữ ký API của phiên bản GraphQL Java trong dự án và ưu tiên overload theo phiên bản đó nếu cần context hoặc locale.

## Đăng ký custom scalar trong Spring for GraphQL

Khai báo scalar Date trong SDL chỉ thông báo cho schema rằng có một scalar tên Date. GraphQL runtime vẫn cần biết cách coercion của scalar đó. Trong Spring for GraphQL, có thể đăng ký GraphQLScalarType bằng bean RuntimeWiringConfigurer:

~~~java
import graphql.schema.GraphQLScalarType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    GraphQLScalarType dateScalar() {
        return DateScalar.create();
    }

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer(
            GraphQLScalarType dateScalar) {
        return wiringBuilder -> wiringBuilder.scalar(dateScalar);
    }
}
~~~

Spring Boot tự phát hiện bean RuntimeWiringConfigurer và áp dụng cấu hình này khi xây dựng GraphQL runtime. Nếu ứng dụng có nhiều custom scalar, có thể đăng ký từng scalar trong cùng một configurer hoặc tách thành các configurer nhỏ theo nhóm trách nhiệm. Tên scalar trong SDL phải trùng với tên của GraphQLScalarType.

Schema có thể sử dụng scalar Date ở cả output field và argument:

~~~graphql
scalar Date

type Query {
  books(publishedAfter: Date): [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedOn: Date!
}
~~~

Resolver nhận kiểu Java LocalDate vì scalar đã chuyển đổi input trước khi phương thức được gọi:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument LocalDate publishedAfter) {
        return bookService.findPublishedAfter(publishedAfter);
    }
}
~~~

Khi service trả về các object Book có field publishedOn kiểu LocalDate, scalar Date sẽ serialize chúng thành chuỗi ISO-8601 trong response. Nhờ vậy, controller và service làm việc với kiểu Java có ý nghĩa rõ ràng thay vì phải truyền chuỗi ngày xuyên suốt ứng dụng.

## Luồng xử lý input và output

Sơ đồ dưới đây tóm tắt vị trí của custom scalar trong quá trình thực thi:

~~~mermaid
flowchart TD
    A["Client GraphQL request"] --> B{"Input được truyền theo cách nào?"}
    B -->|"JSON variables"| C["parseValue"]
    B -->|"Literal trong document"| D["parseLiteral"]
    C --> E["Kiểu Java nội bộ"]
    D --> E
    E --> F["Resolver / Service"]
    F --> G["Giá trị Java trả về"]
    G --> H["serialize"]
    H --> I["GraphQL response"]
~~~

Scalar xử lý chuyển đổi kiểu ở biên GraphQL. Nó không nên truy cập database, gọi HTTP hoặc thực hiện nghiệp vụ. Việc giữ coercing thuần túy giúp quy tắc định dạng dễ kiểm thử, dự đoán được và có thể tái sử dụng ở nhiều field.

## Kiểm thử custom scalar

Nên kiểm tra riêng ba phương thức coercion và kiểm tra tích hợp qua GraphQL operation:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Serialize một LocalDate hợp lệ | Chuỗi ISO-8601 yyyy-MM-dd |
| Serialize object không phải LocalDate | Lỗi serialization |
| Parse variable là ngày hợp lệ | Nhận được LocalDate tương ứng |
| Parse variable sai định dạng | Lỗi input coercion |
| Parse literal dạng string hợp lệ | Nhận được LocalDate tương ứng |
| Parse literal không phải string hoặc sai ngày | Lỗi literal coercion |

Ví dụ kiểm thử qua GraphQlTester:

~~~java
graphQlTester.document("""
        query Books($after: Date) {
            books(publishedAfter: $after) {
                id
                publishedOn
            }
        }
        """)
    .variable("after", "2025-04-18")
    .execute()
    .path("books[0].publishedOn")
    .entity(String.class)
    .isEqualTo("2025-04-20");
~~~

Test này đi qua parseValue khi nhận variable và serialize khi trả field publishedOn. Để kiểm tra parseLiteral, hãy viết một operation có giá trị Date trực tiếp trong document thay vì truyền qua variables. Cũng cần có test cho chuỗi sai như 2025-02-30, chuỗi sai định dạng như 18/04/2025, giá trị null nếu field cho phép null, và giá trị null ở field non-null.

Khi kiểm tra lỗi qua GraphQlTester, cần xác minh operation có lỗi coercion và resolver không được gọi với input không hợp lệ. Điều này bảo đảm dữ liệu sai bị chặn ngay tại biên GraphQL, trước khi đi vào tầng nghiệp vụ.

## Thiết kế custom scalar an toàn và ổn định

Một custom scalar là một phần của hợp đồng công khai. Khi đã có client sử dụng, thay đổi wire format có thể làm hỏng tương thích. Ví dụ đổi Date từ yyyy-MM-dd sang dd/MM/yyyy sẽ khiến client cũ gửi dữ liệu không còn hợp lệ. Hãy xác định format ngay từ đầu, ghi rõ mô tả scalar trong schema và giữ format ổn định.

Một số nguyên tắc nên áp dụng:

1. **Kiểm tra chặt input.** Chỉ chấp nhận đúng kiểu và định dạng đã công bố; không âm thầm chuyển số, object hoặc chuỗi tùy ý thành giá trị hợp lệ.
2. **Serialize một kiểu Java xác định.** Tránh chấp nhận nhiều kiểu nội bộ không liên quan vì có thể tạo response không nhất quán.
3. **Dùng định dạng chuẩn.** ISO-8601 phù hợp với ngày và thời điểm; UUID nên theo dạng chuẩn; decimal cần quy định rõ precision và scale.
4. **Tách coercion khỏi validation nghiệp vụ.** Scalar kiểm tra hình dạng và chuyển đổi kiểu; service kiểm tra các quy tắc như ngày xuất bản không nằm trong tương lai hoặc số tiền nằm trong hạn mức.
5. **Không nhầm scalar với object.** Nếu client cần truy vấn các thuộc tính con như amount và currency, hãy cân nhắc object type Money thay vì một scalar opaque.
6. **Đặt tên và mô tả rõ.** Tên DateTime, UUID hoặc Money cần có hợp đồng định dạng cụ thể để client hiểu cách sử dụng.
7. **Kiểm thử cả input lẫn output.** Chỉ kiểm tra parse mà bỏ serialize có thể khiến dữ liệu đọc được nhưng response lại không đúng format.

Custom scalar hữu ích khi một giá trị có định dạng và quy tắc coercion riêng cần được chia sẻ nhất quán trên nhiều field. Trong Spring for GraphQL, SDL công bố tên scalar, GraphQL Java định nghĩa cách parse và serialize, còn RuntimeWiringConfigurer kết nối scalar đó vào runtime. Khi giữ ranh giới này rõ ràng, schema biểu đạt được kiểu dữ liệu chuyên biệt mà resolver và service vẫn làm việc với các kiểu Java phù hợp.
