# Thay đổi API query, fragment metadata và value expression

## 1. Phạm vi và mốc phiên bản

Trong module **SPRING_DATA_COMMONS**, các abstraction Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing tạo nên nền tảng dùng chung cho nhiều Spring Data store. Khi nâng phiên bản, phần khai báo repository của ứng dụng và phần mở rộng hạ tầng query có mức độ chịu ảnh hưởng khác nhau. Bài này tập trung vào ba điểm giao nhau: API tạo query, metadata của lời gọi fragment và cơ chế value expression.

Mục tiêu là đọc được cảnh báo deprecated, biết nơi cần sửa trong một extension và hiểu dữ liệu nào chỉ có tại thời điểm repository đang được gọi. Các ví dụ chọn **Spring Data Commons 3.4 làm mốc API**, đồng thời chỉ ra một số thay đổi bắt đầu từ 3.3. Đây là mốc để học và đối chiếu chữ ký, không phải khẳng định về phiên bản mới nhất.

| Mốc | Điểm cần nhận biết |
| --- | --- |
| 3.3 | Có `ValueExpression`, `ValueExpressionParser` và `ValueExpressionQueryRewriter`; các API chỉ xử lý SpEL cũ bắt đầu được thay thế. |
| 3.4 | API query chuyển sang cách cung cấp value evaluation context; bổ sung metadata cho lời gọi repository và marker dành cho fragment. |
| Khi nâng sang dòng khác | Đối chiếu Javadoc đúng phiên bản đích và dependency thực tế; deprecated không tự cho biết API đã bị xóa ở bản nào. |

Các mốc deprecated và API thay thế được ghi trong [danh sách deprecated của Commons 3.4](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/deprecated-list.html). Mốc ra đời của parser và biểu thức có tại [ValueExpressionParser](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/expression/ValueExpressionParser.html) và [ValueExpression](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/expression/ValueExpression.html).

## 2. Phân biệt API ứng dụng và SPI hạ tầng query

Xét một repository ứng dụng:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

interface CourseRepository extends CrudRepository<Course, Long> {
    List<Course> findByPublishedTrueOrderByTitleAsc();
}
```

`Course` là domain type đã được ánh xạ theo store của ứng dụng. Ở đây người viết ứng dụng mô tả điều kiện và thứ tự qua tên phương thức. Họ không trực tiếp tạo parser hay query lookup strategy.

Ở phía hạ tầng, các thành phần làm những việc khác:

| Thành phần | Trách nhiệm |
| --- | --- |
| `QueryMethod` | Mô tả phương thức query, tham số và thông tin kiểu kết quả. |
| `QueryLookupStrategy` | Tìm hoặc tạo `RepositoryQuery` cho phương thức repository. |
| `RepositoryQuery` | Đại diện query có thể thực thi khi nhận giá trị đối số. |
| `ValueExpressionDelegate` | Cung cấp parser và cơ chế tạo context cho biểu thức trong query. |
| Fragment implementation | Hiện thực hành vi bổ sung, được ghép vào repository. |

Có thể hình dung một nhánh xử lý query như sau:

```text
Khai báo repository
  -> metadata phương thức
  -> QueryLookupStrategy
  -> RepositoryQuery của store
  -> đối số của lần gọi hiện tại
  -> evaluate biểu thức và bind giá trị nếu query có biểu thức
  -> thực thi qua store
```

Sơ đồ này mô tả trách nhiệm, không khẳng định mọi store tạo và thực thi query tại cùng một thời điểm. Một fragment có implementation riêng cũng không nhất thiết đi qua cơ chế tạo finder query.

Khi cảnh báo nâng cấp trỏ vào `RepositoryFactorySupport` hoặc một evaluation context provider, hãy tìm ở custom factory, thư viện tích hợp và extension. Chỉ đổi tên các phương thức `findBy...` sẽ không xử lý được vấn đề nằm ở SPI. Vai trò của các lớp query được tổng hợp trong [package repository.query](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/query/package-summary.html).

## 3. Thay đổi API query: từ SpEL context đến value context

### 3.1. Vì sao context cần rộng hơn?

Một query có thể cần cả giá trị tính bằng SpEL lẫn cấu hình lấy từ `Environment`. Chỉ cung cấp đối tượng `EvaluationContext` của SpEL chưa diễn đạt đầy đủ hai nguồn dữ liệu đó.

Ví dụ nghiệp vụ: danh mục khóa học dùng cấu hình `catalog.locale=vi`, đồng thời nhận `category` từ tham số phương thức. Cấu hình và đối số có vòng đời khác nhau. Query infrastructure phải giữ được thông tin nguồn cấu hình, nhưng vẫn tính giá trị tham số theo từng lần gọi.

Những chuyển đổi đáng chú ý trong dòng API này:

| API cũ | Hướng thay thế |
| --- | --- |
| `QueryMethodEvaluationContextProvider` | `QueryMethodValueEvaluationContextAccessor` |
| `ExtensionAwareQueryMethodEvaluationContextProvider` | `QueryMethodValueEvaluationContextAccessor` |
| `ReactiveQueryMethodEvaluationContextProvider` | `QueryMethodValueEvaluationContextAccessor`, có hỗ trợ provider reactive phù hợp |
| `SpelQueryContext`, `SpelEvaluator` | `ValueExpressionQueryRewriter` |
| `getQueryLookupStrategy(Key, QueryMethodEvaluationContextProvider)` | Overload nhận `ValueExpressionDelegate` |
| `setEvaluationContextProvider(QueryMethodEvaluationContextProvider)` | Overload nhận `org.springframework.data.spel.EvaluationContextProvider` |

Đây là chuyển đổi về trách nhiệm và kiểu dữ liệu, không phải thay hàng loạt import bằng tên mới. Các quan hệ thay thế nằm trong [Javadoc deprecated 3.4](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/deprecated-list.html).

### 3.2. Chữ ký custom factory cần được xem lại

Đối với một subclass tùy biến `RepositoryFactorySupport`, phần thay đổi chữ ký có thể được biểu diễn như sau. Đây chỉ là diff chữ ký; phần thân phải phù hợp với factory và store đang tích hợp:

```diff
 protected Optional<QueryLookupStrategy> getQueryLookupStrategy(
     QueryLookupStrategy.Key key,
-    QueryMethodEvaluationContextProvider evaluationContextProvider)
+    ValueExpressionDelegate valueExpressionDelegate)
```

Giữ `@Override` trên phương thức triển khai để compiler phát hiện chữ ký không khớp với phiên bản đích. Sau đó kiểm tra cách phần thân chuyển delegate xuống query implementation. Nếu phần thân bỏ qua delegate rồi tự dựng một SpEL context rỗng, việc đổi chữ ký chưa bảo toàn hành vi.

Overload cũ bị deprecated từ 3.4. Chữ ký mới được mô tả trong [RepositoryFactorySupport](https://www.springframework.org/spring-data/commons/docs/3.4.11/api/org/springframework/data/repository/core/support/RepositoryFactorySupport.html).

### 3.3. Vai trò của accessor và delegate

`QueryMethodValueEvaluationContextAccessor` tạo `ValueEvaluationContextProvider` dựa trên mô tả `Parameters` của query method. Provider tiếp tục dùng giá trị đối số thực tế để tạo context cho một lần thực thi. Accessor cũng hỗ trợ biến thể reactive nếu evaluation context provider bên dưới là reactive. Không nên suy rằng chỉ đổi kiểu khai báo là đã chuyển xong việc lấy context reactive. Xem [Javadoc của accessor](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/query/QueryMethodValueEvaluationContextAccessor.html).

`ValueExpressionDelegate` ghép parser với context accessor. Nó có thể parse biểu thức và tạo provider cho bộ tham số của một query method. Provider đó gắn với chính bộ tham số đã dùng để tạo nó, vì vậy không nên dùng provider của phương thức A cho phương thức B.

Khi framework đã truyền delegate có cấu hình ứng dụng xuống extension, nên sử dụng delegate đó. `ValueExpressionDelegate.create()` tạo cấu hình mặc định với `StandardEnvironment` và evaluation context không có extension; nó không thay thế một cách tương đương cho context của ứng dụng đã đăng ký thêm chức năng. Các đặc điểm này được mô tả tại [ValueExpressionDelegate](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/query/ValueExpressionDelegate.html).

## 4. Value expression: cú pháp, parse và evaluate

### 4.1. Ba dạng đầu vào

Value expression kết hợp khả năng tính toán của SpEL với property placeholder:

| Đầu vào | Cách hiểu |
| --- | --- |
| `#{#kind}` | Lấy biến `kind` từ SpEL evaluation context. |
| `${catalog.region:vn}` | Lấy cấu hình `catalog.region`, dùng `vn` làm giá trị mặc định. |
| `catalog-${catalog.region:vn}-#{#kind}` | Ghép literal, placeholder và SpEL thành một giá trị. |

Đây là cú pháp biểu thức ở mức Commons. Khi đặt vào query, store còn quyết định tiền tố và cách bind. Hỗ trợ biểu thức trong mapping annotation cũng phụ thuộc module; không thể suy rằng mọi annotation JPA hỗ trợ vì Commons có parser. Phạm vi này được giải thích trong [Value Expressions Fundamentals](https://docs.spring.io/spring-data/commons/reference/value-expressions.html).

### 4.2. Ví dụ độc lập với database

Ví dụ dưới dùng API có ở mốc 3.4 và không cần annotation query của store. `ValueExpressionParser.create()` không nhận đối số có từ 3.4; khi đối chiếu 3.3 cần kiểm tra overload nhận `ValueParserConfiguration`.

```java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class ValueExpressionExample {

    private static final ValueExpression RESOURCE_NAME =
            ValueExpressionParser.create().parse(
                    "catalog-${catalog.region:vn}-#{#kind}");

    public static void main(String[] args) {
        var environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(
                new MapPropertySource("demo", Map.of("catalog.region", "sg")));

        var bookContext = new StandardEvaluationContext();
        bookContext.setVariable("kind", "book");

        var courseContext = new StandardEvaluationContext();
        courseContext.setVariable("kind", "course");

        Object bookResource = RESOURCE_NAME.evaluate(
                ValueEvaluationContext.of(environment, bookContext));
        Object courseResource = RESOURCE_NAME.evaluate(
                ValueEvaluationContext.of(environment, courseContext));

        System.out.println(bookResource);   // catalog-sg-book
        System.out.println(courseResource); // catalog-sg-course
    }
}
```

Điểm cần quan sát là cùng một biểu thức đã parse được dùng với hai context. Tên vùng lấy từ `Environment`; loại tài nguyên lấy từ biến SpEL. Đối tượng biểu thức không tự chứa lựa chọn `book` hay `course` của một lần sử dụng.

Parser tạo biểu thức để evaluate nhiều lần. `ValueExpression.evaluate(...)` trả về `Object`, nên code gọi phải xử lý kiểu kết quả phù hợp thay vì mặc định mọi biểu thức đều trả về chuỗi. Ví dụ trên tạo chuỗi do có phần template literal. Hợp đồng evaluate được ghi tại [ValueExpression](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/expression/ValueExpression.html), còn các overload tạo parser có tại [ValueExpressionParser](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/expression/ValueExpressionParser.html).

### 4.3. Cache biểu thức và cache kết quả là hai quyết định khác nhau

Biểu thức đã parse có thể tái sử dụng an toàn giữa các luồng; việc evaluate vẫn cần context phù hợp cho lần gọi. Khuyến nghị cache biểu thức được nêu trong [tài liệu value expressions](https://docs.spring.io/spring-data/commons/reference/value-expressions.html).

Trong ví dụ, có thể giữ `RESOURCE_NAME` làm hằng dùng chung. Nếu thay vào đó chỉ tính một lần rồi cache kết quả `catalog-sg-book`, lần gọi dành cho khóa học sẽ nhận sai tài nguyên. Tương tự, giữ một `StandardEvaluationContext` mutable làm field rồi thay `kind` liên tục sẽ làm các lần gọi đồng thời chia sẻ dữ liệu.

Một thiết kế rõ ràng là giữ template đã parse ở phạm vi dùng chung, còn dữ liệu phụ thuộc đối số nằm trong context của lần evaluate. Nếu thật sự cần cache kết quả, khóa cache phải phản ánh mọi đầu vào ảnh hưởng đến kết quả và có chính sách hết hạn tương ứng.

Chỉ parse template từ nguồn được ứng dụng tin cậy. Giá trị người dùng nhập nên đi qua tham số, thay vì trở thành mã biểu thức mới.

## 5. Value expression trong query được bind như thế nào?

`ValueExpressionQueryRewriter` nhận biết biểu thức trong query, thay chúng bằng bind variable và lưu liên hệ giữa biến được sinh ra với biểu thức tương ứng. Biến thể evaluator dùng metadata tham số và đối số hiện tại để tính giá trị. Hợp đồng này có tại [ValueExpressionQueryRewriter](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/org/springframework/data/repository/query/ValueExpressionQueryRewriter.html).

Ví dụ sau chỉ minh họa cấu trúc SQL và marker; khi dùng thực tế phải chọn `@Query` cùng cú pháp được store hỗ trợ:

```sql
select * from course_record
where locale = :${catalog.locale:vi}
  and category = :#{#category}
```

Một cách biểu diễn kết quả xử lý là:

```text
Template query
  locale = :${catalog.locale:vi}
  category = :#{#category}

Query dùng bind variable, tên chỉ để minh họa
  locale = :generated_0
  category = :generated_1

Giá trị của một lần gọi
  generated_0 -> "vi"
  generated_1 -> "backend"
```

Tên bind variable thực tế do hạ tầng tích hợp quyết định. Ví dụ giả định `category` đã được đưa vào evaluation context; việc truy cập theo tên còn tùy cách framework nhận biết tên tham số hoặc annotation khai báo tham số. Không mặc định biến `#category` tồn tại trong mọi context tự dựng.

Trong kịch bản này, biểu thức cung cấp **giá trị** cho điều kiện. Không dùng bind value để thay tên bảng, tên cột hoặc từ khóa sắp xếp. Nếu cần chọn trường sort động, nên dùng abstraction `Sort` phù hợp với store hoặc một tập lựa chọn được kiểm soát.

Ví dụ cũng cho thấy hai giai đoạn cần giữ riêng trong extension: query template có thể được phân tích trước, còn giá trị `category` phải được tính lại theo đối số. Dùng dữ liệu của lần gọi đầu tiên để hoàn tất query dùng chung sẽ khiến những lần gọi sau có thể dùng sai bộ lọc.

## 6. Fragment metadata: hiểu repository đang gọi mình

### 6.1. Bài toán tái sử dụng

Giả sử có một fragment dùng cho cả `CourseRepository` và `BookRepository`. Fragment có thể cần biết domain type để chọn bộ chuyển đổi, cấu hình tìm kiếm hoặc namespace của tài nguyên bên ngoài. Nếu gắn cứng `Course.class` trong implementation dùng chung, fragment sẽ không còn phục vụ đúng repository dành cho sách.

Từ 3.4, `RepositoryMethodContext` cung cấp metadata repository cùng phương thức đang được gọi. Context là thông tin của lời gọi hiện tại. `getMethod()` phản ánh phương thức trên repository interface, không nhất thiết là đối tượng `Method` của implementation nhận lời gọi. Các điều kiện sử dụng được mô tả tại [RepositoryMethodContext](https://docs.spring.io/spring-data/data-commons/docs/current/api/org/springframework/data/repository/core/RepositoryMethodContext.html).

### 6.2. Khai báo fragment và implementation

Các đoạn mã dưới tương ứng với các kiểu Java riêng trong cùng package được repository scanning phát hiện. `Course` tiếp tục là domain type của ứng dụng.

```java
public interface DomainTypeFragment<T> {
    Class<?> repositoryDomainType();
}
```

```java
import org.springframework.data.repository.core.RepositoryMethodContext;
import org.springframework.data.repository.core.support.RepositoryMetadataAccess;

public class DomainTypeFragmentImpl<T>
        implements DomainTypeFragment<T>, RepositoryMetadataAccess {

    @Override
    public Class<?> repositoryDomainType() {
        RepositoryMethodContext context = RepositoryMethodContext.getContext();
        return context.getMetadata().getDomainType();
    }
}
```

```java
import org.springframework.data.repository.CrudRepository;

public interface CourseRepository
        extends CrudRepository<Course, Long>, DomainTypeFragment<Course> {
}
```

Với fragment được ghép đúng vào repository, lời gọi `courseRepository.repositoryDomainType()` đi qua repository proxy sẽ trả về `Course.class`. Nếu một `BookRepository` tương tự dùng `DomainTypeFragment<Book>`, implementation có thể dựa vào metadata để nhận `Book.class` mà không cần một nhánh hard-code theo từng repository.

`RepositoryMetadataAccess` là marker dành cho **implementation fragment**. Khi composition có fragment mang marker này, hạ tầng bật khả năng cung cấp invocation metadata cho repository tương ứng. Nên đặt marker trên implementation như trong ví dụ. Xem [RepositoryMetadataAccess](https://docs.spring.io/spring-data/data-commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryMetadataAccess.html).

### 6.3. Cách bật metadata và chi phí

Invocation metadata không được expose mặc định vì có thêm chi phí interception. Ngoài marker, có thể cấu hình factory bean bằng `setExposeMetadata(true)`. Nếu dùng `BeanPostProcessor`, nên chọn đúng repository cần tính năng này thay vì bật cho toàn bộ repository theo thói quen. Hai cách cấu hình được trình bày tại [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html).

Không cần bật metadata chỉ vì một repository có fragment. Ví dụ fragment đã được truyền đầy đủ cấu hình, hoặc hành vi không phụ thuộc repository nào gọi nó, có thể hoạt động mà không cần truy cập context.

### 6.4. Vòng đời context

Lời gọi sau không có repository proxy bao quanh:

```java
var fragment = new DomainTypeFragmentImpl<Course>();
fragment.repositoryDomainType();
```

Trường hợp này không đáp ứng điều kiện của `RepositoryMethodContext.getContext()`. Phương thức sẽ ném `IllegalStateException` nếu không có context hoặc repository chưa expose metadata. Điều kiện đó thuộc hợp đồng API, không phải dấu hiệu domain type chưa được ánh xạ. Xem [Javadoc getContext](https://docs.spring.io/spring-data/data-commons/docs/current/api/org/springframework/data/repository/core/RepositoryMethodContext.html).

Factory expose metadata qua `ThreadLocal`, theo [RepositoryFactorySupport](https://www.springframework.org/spring-data/commons/docs/3.4.11/api/org/springframework/data/repository/core/support/RepositoryFactorySupport.html). Vì vậy, không suy rằng context tự theo một tác vụ chạy trên executor khác hoặc phần xử lý reactive được defer đến sau khi lời gọi ban đầu kết thúc.

Nếu thao tác về sau chỉ cần domain type, hãy lấy `Class<?>` tại thời điểm context hợp lệ rồi truyền dữ liệu đó vào tác vụ. Không giữ invocation context trong field của một singleton. Một fragment dùng chung có thể phục vụ nhiều repository và nhiều lời gọi đồng thời.

Cũng cần tách bạch hai khái niệm: `RepositoryMetadata` mô tả repository; `RepositoryMethodContext` là lối vào metadata của lời gọi hiện tại. Nó không phải auditing context và không tự cung cấp danh tính người dùng hay tenant đang đăng nhập.

## 7. Liên hệ với AOT

Trong chương “Phiên bản và AOT”, ba thay đổi trên có hệ quả thực tế đối với cách thiết kế extension. AOT không biến metadata của lần gọi thành dữ liệu có sẵn ở mọi nơi, cũng không biến một biểu thức phụ thuộc đối số thành hằng số.

Với ví dụ khóa học, có thể nhận biết sớm query template và kiểu `Course`, nhưng giá trị `category` của yêu cầu tiếp theo vẫn là dữ liệu runtime. Do đó, thiết kế nên giữ ranh giới giữa thông tin có thể chuẩn bị trước và dữ liệu phải cung cấp theo lần gọi.

| Thông tin | Cách sử dụng phù hợp trong thiết kế ví dụ |
| --- | --- |
| Chuỗi template biểu thức do lập trình viên khai báo | Parse và tái sử dụng biểu thức khi phù hợp. |
| Kiểu repository, kiểu domain và phương thức được khai báo | Giữ đủ thông tin kiểu để hạ tầng có thể phân tích. |
| Đối số `category` | Cấp lại qua context mỗi lần thực thi. |
| Invocation context của fragment | Chỉ truy cập trong phạm vi lời gọi có expose metadata. |
| Tên kiểu được ghép từ chuỗi hoặc reflection tùy biến | Xác định nhu cầu runtime hints theo phiên bản và đường chạy thực tế. |

Bảng này là hướng suy luận thiết kế, không phải cam kết rằng mọi fragment hoặc mọi SpEL expression đều tương thích native image. Nếu extension có mục tiêu native, cần kiểm chứng đường gọi repository, biểu thức, reflection và dependency của chính store trong quy trình build phù hợp. Một lần chạy thành công trên JVM chưa xác nhận đường chạy native.

## 8. Trình tự migration trong một ứng dụng có extension

Xét một thư viện nội bộ có custom repository factory, fragment tìm kiếm đa domain và query đọc cấu hình vùng. Có thể xử lý thay đổi theo thứ tự sau:

1. **Xác định bộ phiên bản dùng cùng nhau.** Ghi nhận Commons, module store và thư viện extension trong dependency thực tế; dùng bộ quản lý dependency của ứng dụng để giữ chúng tương thích.
2. **Phân loại nơi sử dụng API.** Tách khai báo repository ứng dụng khỏi custom factory, provider và query rewriter để sửa đúng lớp.
3. **Đổi điểm tích hợp query.** Dùng chữ ký nhận `ValueExpressionDelegate` theo phiên bản đích và truyền tiếp cấu hình cần thiết cho implementation.
4. **Giữ đúng nguồn dữ liệu.** Đảm bảo `Environment`, context extension và đối số phương thức vẫn đến được nơi evaluate.
5. **Bật fragment metadata có chọn lọc.** Đặt `RepositoryMetadataAccess` ở implementation cần nó hoặc cấu hình factory tương ứng.
6. **Xem lại vòng đời dữ liệu.** Tái sử dụng biểu thức đã parse; không chia sẻ kết quả phụ thuộc lần gọi hay invocation context mutable.
7. **Kiểm chứng hành vi ở quy trình dự án.** Gọi hai repository khác domain, thay đổi đối số và cấu hình, rồi kiểm tra đường native nếu đó là mục tiêu triển khai.

Một dấu hiệu sửa chưa đủ là compiler hết cảnh báo nhưng query không còn nhận property từ ứng dụng. Một dấu hiệu khác là fragment chạy tốt khi gọi qua repository, nhưng test gọi trực tiếp implementation lại lỗi context. Hai tình huống này cần kiểm tra cấu hình và đường gọi tương ứng.

## 9. Nhận diện lỗi theo triệu chứng

| Triệu chứng | Khả năng cần xem xét | Điểm đối chiếu |
| --- | --- | --- |
| `@Override` không còn khớp | Chữ ký factory thay đổi hoặc dependency đích khác dự kiến | Javadoc của đúng `RepositoryFactorySupport` đang dùng. |
| `NoSuchMethodError` khi khởi động | Các artifact Commons, store hoặc extension không cùng bộ tương thích | Dependency được resolve trong ứng dụng thực tế. |
| Query mất giá trị cấu hình sau migration | Tự tạo default delegate làm mất `Environment` ứng dụng | Delegate và accessor được truyền vào query implementation. |
| Không tìm thấy biến trong biểu thức | Context chưa chứa biến hoặc tên tham số chưa được nhận biết | Cách tạo context, tên biến và cơ chế khai báo tham số của store. |
| Fragment ném `IllegalStateException` | Gọi ngoài repository invocation hoặc chưa expose metadata | Composition, marker, factory và thời điểm gọi `getContext()`. |
| Hai repository nhận cùng một domain type sai | Lưu metadata của lần gọi trước trong field dùng chung | Vòng đời fragment và vị trí đọc metadata. |
| Giá trị bộ lọc không đổi giữa các lần gọi | Cache kết quả evaluate thay cho template | Khóa cache và thời điểm đưa đối số vào context. |

Các triệu chứng trong bảng là hướng khoanh vùng, không phải kết luận chắc chắn chỉ từ tên exception. Ví dụ `NoSuchMethodError` vẫn cần nhìn chữ ký thiếu và artifact chứa caller để xác định thành phần bị lệch.

Sau bài này, điều cần giữ khi đọc một migration là chuỗi trách nhiệm: factory chọn cách tạo query; delegate cung cấp parser và context factory; context mang dữ liệu cho lần evaluate; fragment chỉ đọc invocation metadata khi lời gọi repository đang cung cấp nó. Hiểu từng ranh giới giúp extension tiếp tục phục vụ đúng repository và đúng bộ đối số sau khi đổi phiên bản.