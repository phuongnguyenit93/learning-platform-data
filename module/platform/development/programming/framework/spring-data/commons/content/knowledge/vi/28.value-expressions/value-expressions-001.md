# Value expression, SpEL và property placeholder

Trong Spring Data Commons, **value expression** là cách biểu diễn một giá trị bằng chuỗi có thể chứa phần văn bản cố định, property placeholder và biểu thức SpEL. Khi được đánh giá trong một ngữ cảnh cụ thể, chuỗi này tạo ra giá trị mà cơ chế tích hợp sẽ sử dụng.

Ví dụ, một ứng dụng có thể mô tả tên tài nguyên như sau:

```text
orders-${app.stage:local}-#{#tenantId}
```

Nếu thuộc tính `app.stage` có giá trị `dev` và biến SpEL `tenantId` có giá trị `acme`, kết quả mong đợi là:

```text
orders-dev-acme
```

Bài học thuộc chương **Biểu thức giá trị** của module **SPRING_DATA_COMMONS**. Trọng tâm là hiểu abstraction dùng chung, phân biệt dữ liệu cấu hình với dữ liệu trong ngữ cảnh thực thi, và nhận biết giới hạn khi áp dụng vào repository, truy vấn, projection hoặc ánh xạ của từng kho dữ liệu.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Cú pháp thường gặp | Nguồn tạo ra giá trị |
| --- | --- | --- |
| Văn bản cố định | `orders` | Chính nội dung đã khai báo |
| Property placeholder | `${app.stage:local}` | Thuộc tính cấu hình; `local` là giá trị mặc định |
| SpEL trong template | `#{#tenantId}` | Biểu thức được tính từ evaluation context |
| Value expression kết hợp | `orders-${app.stage:local}-#{#tenantId}` | Kết hợp các phần trên bằng abstraction của Spring Data Commons |

**SpEL** là Spring Expression Language. Nó cung cấp ngôn ngữ truy cập thuộc tính, phép toán, điều kiện, gọi phương thức và những khả năng khác tùy evaluation context.

**Property placeholder** dùng để tra cứu thuộc tính cấu hình. Nó không phải một biểu thức SpEL được viết bằng cú pháp khác.

**Value expression** là lớp biểu diễn có thể kết hợp những cơ chế đó. Không nên xem mọi chuỗi có ký tự `$` hoặc `#` trong ứng dụng là một value expression: phải có một thành phần chủ động phân tích và đánh giá chuỗi ấy.

Ví dụ, chuỗi này chỉ là dữ liệu nếu không được chuyển cho cơ chế hỗ trợ:

```java
String raw = "orders-${app.stage:local}";
System.out.println(raw); // orders-${app.stage:local}
```

Việc viết chuỗi giống cú pháp expression không tự kích hoạt Spring.

## 2. Property placeholder: lấy dữ liệu cấu hình

### 2.1. Tra cứu thuộc tính theo khóa

Giả sử cấu hình ứng dụng chứa:

```properties
app.stage=dev
billing.currency=VND
```

Các placeholder tương ứng là:

```text
${app.stage}
${billing.currency}
```

Trong ngữ cảnh được cung cấp `Environment` phù hợp, chúng có thể tạo ra `dev` và `VND`.

`Environment` là abstraction cấu hình của Spring. Những nguồn thuộc tính nào tồn tại, nguồn nào ưu tiên và khóa nào có thể tìm được phụ thuộc vào ứng dụng đã thiết lập environment đó như thế nào. Khi chạy trong Spring Boot, Boot bổ sung quy tắc nạp cấu hình; parser của Spring Data Commons không tự thay thế toàn bộ cơ chế cấu hình của Boot.

### 2.2. Giá trị mặc định

Dạng thông dụng là:

```text
${property.key:defaultValue}
```

Ví dụ:

```text
${app.stage:local}
${billing.currency:VND}
```

Khi không tìm được thuộc tính tương ứng, giá trị sau dấu `:` có thể được dùng làm mặc định.

Cần phân biệt hai tình huống:

- **Không tồn tại thuộc tính:** có thể dùng giá trị mặc định.
- **Thuộc tính tồn tại nhưng là chuỗi rỗng:** không nên mặc định rằng cơ chế fallback sẽ coi nó như một thuộc tính bị thiếu.

Một mặc định hợp lý cho môi trường phát triển chưa chắc hợp lý cho cấu hình production. Với giá trị bắt buộc như định danh kho dữ liệu, ứng dụng nên kiểm tra cấu hình khi khởi động thay vì để một mặc định che giấu lỗi triển khai.

### 2.3. Placeholder không làm phép tính

Xét:

```text
${limits.page-size:20}
```

Phần `limits.page-size` là khóa thuộc tính, còn `20` là văn bản mặc định. Đây không phải yêu cầu chạy phép tính hoặc tạo số nguyên Java ngay lập tức.

Nếu một API đích cần `int`, bước chuyển đổi kiểu thuộc về cơ chế tiêu thụ kết quả hoặc mã ứng dụng. Không suy ra kiểu cuối cùng chỉ từ việc nội dung nhìn giống một con số.

Tương tự:

```text
${2 + 3}
```

là yêu cầu tìm một khóa thuộc tính có tên tương ứng, không mang nghĩa tính `2 + 3`.

### 2.4. Khóa cấu hình không phải biến SpEL

Hai biểu thức sau dùng hai không gian tên khác nhau:

```text
${tenant.id}
#{#tenantId}
```

- `${tenant.id}` tra cứu cấu hình qua nguồn thuộc tính.
- `#{#tenantId}` tra cứu biến `tenantId` trong evaluation context của SpEL.

Có thuộc tính `tenant.id` không đồng nghĩa có biến `tenantId`. Ngược lại, gọi `setVariable("tenantId", ...)` không tự tạo thuộc tính cấu hình `tenant.id`.

## 3. SpEL: tính giá trị trong một evaluation context

### 3.1. Biểu thức và dấu phân định template

Khi dùng theo dạng template trong bài này, phần SpEL được đặt trong `#{...}`:

```text
#{2 + 3}
#{#tenantId}
#{#basePrice * #quantity}
```

Nội dung bên trong là biểu thức SpEL. Dấu `#{...}` giúp parser nhận ra vùng cần tính toán giữa các phần văn bản khác.

Điều này khác với việc dùng trực tiếp parser SpEL cho một biểu thức thuần:

```java
new SpelExpressionParser().parseExpression("2 + 3");
```

Parser SpEL thuần không mặc nhiên xử lý một chuỗi hỗn hợp như `orders-${app.stage}-#{#tenantId}` theo cùng cách với `ValueExpressionParser`. Cú pháp template, cú pháp biểu thức thuần và cú pháp của annotation tích hợp cần được phân biệt rõ.

### 3.2. Biến, root object và bean

| Dạng truy cập | Ý nghĩa | Điều kiện cần |
| --- | --- | --- |
| `#tenantId` | Biến tên `tenantId` | Context đã đăng ký biến đó |
| `customerId` | Thuộc tính của root object | Root object có thuộc tính có thể đọc |
| `#root.customerId` | Truy cập root object tường minh | Có root object phù hợp |
| `@tenantPolicy` | Bean được tra cứu theo tên | Context đã được cấu hình bean resolver |

Ví dụ sau đăng ký biến:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("tenantId", "acme");
```

Trong context đó, `#tenantId` có thể được dùng. Tuy nhiên, nó chưa tự cung cấp bean resolver, đối tượng người dùng đang đăng nhập hoặc các biến chuyên biệt của một repository.

Không mặc định rằng những tên như `principal`, `target`, `args`, `entityName` hay `environment` có sẵn ở mọi nơi. Những tên này có thể được một cơ chế tích hợp bổ sung theo quy ước riêng, hoặc phải được đăng ký rõ ràng.

### 3.3. Điều kiện và xử lý null

SpEL hỗ trợ những phép tính nhỏ giúp tạo giá trị:

```text
#{#priority ? 'express' : 'standard'}
#{#contact?.email ?: 'unknown'}
```

Ở ví dụ thứ hai:

- `?.` tránh truy cập thuộc tính trực tiếp khi `contact` là `null`.
- `?:` cung cấp giá trị thay thế theo ngữ nghĩa Elvis của SpEL.

Đây là fallback trong biểu thức, khác với fallback của `${property:default}`. Hai cơ chế có nguồn dữ liệu và quy tắc xử lý riêng.

Không dùng biểu thức dài để chứa cả một quy trình nghiệp vụ. Nếu phải kiểm tra nhiều quyền, gọi dịch vụ hoặc phối hợp nhiều nguồn dữ liệu, một phương thức Java có tên rõ ràng sẽ dễ kiểm tra và bảo trì hơn.

### 3.4. Kiểu kết quả

Một expression chỉ chứa phép tính có thể trả về đối tượng theo kiểu của kết quả tính toán:

```text
#{2 + 3}
```

Trong ví dụ này, kết quả là số nguyên. Khi có văn bản bao quanh:

```text
batch-#{2 + 3}
```

kết quả là chuỗi `batch-5`.

Không ép kiểu toàn bộ kết quả thành `String` một cách máy móc. Hãy xác định API đích cần chuỗi, số, boolean hay một kiểu khác; kiểm tra khả năng trả về `null` nếu biểu thức cho phép.

## 4. Value expression: ghép cấu hình và biểu thức

Một value expression có thể gồm nhiều đoạn:

```text
orders-${app.stage:local}-#{#tenantId}
```

Ta có thể đọc thành:

1. Giữ nguyên văn bản `orders-`.
2. Lấy thuộc tính `app.stage`, với mặc định `local`.
3. Giữ nguyên dấu `-`.
4. Đánh giá biến SpEL `tenantId`.
5. Kết hợp kết quả thành tên tài nguyên.

Đây là cách phân tích để hiểu nội dung, không phải cam kết rằng mọi tích hợp Spring đều chạy một pipeline thay thế chuỗi theo đúng thứ tự như trên.

Đặc biệt, không xây dựng thiết kế dựa trên giả định rằng kết quả của placeholder sẽ tự được phân tích lại như mã SpEL, hoặc kết quả SpEL sẽ tự trở thành một placeholder mới. Nếu cần kết quả lồng nhau, phải xem đúng hợp đồng của parser và cơ chế tích hợp đang dùng.

Dữ liệu cấu hình nên tiếp tục là dữ liệu. Tránh những cách ghép như sau để tạo mã biểu thức động từ cấu hình:

```text
#{'${tenant.input}'}
```

Với nhu cầu thông thường, hãy cung cấp cấu hình và biến qua các kênh riêng, rồi dùng các đoạn expression độc lập. Cách này cũng tránh việc dấu nháy hoặc nội dung đặc biệt trong cấu hình làm thay đổi cấu trúc biểu thức.

## 5. Các abstraction trong Spring Data Commons

Các API phục vụ mô hình này nằm trong package `org.springframework.data.expression` ở những phiên bản Spring Data Commons có hỗ trợ value expression.

| Abstraction | Trách nhiệm |
| --- | --- |
| `ValueExpressionParser` | Phân tích chuỗi khai báo thành `ValueExpression` |
| `ValueExpression` | Biểu diễn đã phân tích, có thể được đánh giá với context phù hợp |
| `ValueEvaluationContext` | Mang environment và evaluation context cần cho việc đánh giá |
| Spring `Environment` | Cung cấp thuộc tính cấu hình cho phần placeholder |
| SpEL `EvaluationContext` | Cung cấp biến, root object và các khả năng truy cập khi tính SpEL |

Có hai giai đoạn cần phân biệt:

```text
Chuỗi khai báo
     |
     | parse
     v
ValueExpression
     |
     | evaluate với environment + evaluation context
     v
Giá trị kết quả
```

**Parse** xử lý cấu trúc của khai báo. **Evaluate** tính giá trị với dữ liệu cụ thể.

Một biểu thức có thể đúng cú pháp nhưng vẫn thất bại khi đánh giá vì thiếu biến, không tìm được thuộc tính, truy cập sai kiểu hoặc gọi phương thức không được context cho phép.

### 5.1. Ví dụ Java đầy đủ

Ví dụ dưới đây chủ động tạo environment và context. Nó giúp quan sát API Commons mà không phụ thuộc vào một kho dữ liệu cụ thể.

```java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class ValueExpressionDemo {

    public static void main(String[] args) {
        StandardEnvironment environment = new StandardEnvironment();

        Map<String, Object> properties = Map.of(
                "app.stage", "dev",
                "billing.currency", "VND"
        );

        environment.getPropertySources().addFirst(
                new MapPropertySource("lessonProperties", properties)
        );

        StandardEvaluationContext spelContext =
                new StandardEvaluationContext();
        spelContext.setVariable("tenantId", "acme");
        spelContext.setVariable("quantity", 3);

        ValueEvaluationContext evaluationContext =
                ValueEvaluationContext.of(environment, spelContext);

        ValueExpressionParser parser = ValueExpressionParser.create();

        ValueExpression resourceName = parser.parse(
                "orders-${app.stage:local}-#{#tenantId}"
        );

        Object resourceNameValue = resourceName.evaluate(evaluationContext);
        System.out.println(resourceNameValue);

        ValueExpression quantityExpression = parser.parse("#{#quantity + 2}");
        Object quantityValue = quantityExpression.evaluate(evaluationContext);
        System.out.println(quantityValue);

        ValueExpression currencyExpression = parser.parse(
                "currency=${billing.currency:USD}"
        );
        System.out.println(currencyExpression.evaluate(evaluationContext));
    }
}
```

Kết quả mong đợi:

```text
orders-dev-acme
5
currency=VND
```

Dự án cần có Spring Data Commons với các API trên và các thư viện Spring tương thích. Nếu đang dùng Spring Boot, nên để dependency management của dự án quản lý bộ phiên bản Spring thay vì chọn riêng từng JAR theo ví dụ.

Đây là ví dụ minh họa nội dung; cần biên dịch và chạy trong dự án thực hành với phiên bản dependency thực tế trước khi đưa vào ứng dụng.

### 5.2. Vì sao truyền cả hai loại context?

Trong ví dụ:

```java
ValueEvaluationContext.of(environment, spelContext)
```

- `environment` giải quyết `${app.stage:local}` và `${billing.currency:USD}`.
- `spelContext` giải quyết `#tenantId` và `#quantity`.

Đưa environment vào `ValueEvaluationContext` không đồng nghĩa environment trở thành một biến SpEL tên `environment`.

Nếu muốn dùng:

```text
#{#environment.getProperty('app.stage')}
```

thì với `StandardEvaluationContext` do ta tạo thủ công, phải đăng ký biến tương ứng:

```java
spelContext.setVariable("environment", environment);
```

Còn `@environment` là cú pháp truy cập bean. Nó cần bean resolver và bean có tên phù hợp. Biến và bean là hai cơ chế khác nhau, dù có thể trỏ đến cùng một đối tượng.

### 5.3. Thời điểm đánh giá thuộc về bên sử dụng

Parser không quyết định rằng một expression luôn được tính một lần lúc khởi động hay luôn được tính cho từng lần gọi repository.

Bên tích hợp có thể đánh giá khi tạo metadata, khi khởi tạo bean, khi tạo truy vấn hoặc khi xử lý một lời gọi cụ thể. Vì vậy:

- Không mặc định rằng thay đổi cấu hình sẽ làm mọi giá trị đã được tính trước đó tự cập nhật.
- Không mặc định rằng expression dùng dữ liệu request sẽ được tính lại ở mọi annotation.
- Với cấu hình tenant hoặc security, phải biết context nào được dùng và tại thời điểm nào.

## 6. Áp dụng vào Spring Data: cùng ngôn ngữ, khác hợp đồng tích hợp

Spring Data Commons cung cấp abstraction chung. Các module lưu trữ quyết định vị trí nào chấp nhận expression, dữ liệu nào có sẵn và kết quả được đưa vào đâu.

| Vị trí | Cần xác định trước khi dùng |
| --- | --- |
| Annotation ánh xạ | Thuộc tính annotation có hỗ trợ placeholder hoặc SpEL không; lúc nào tên tài nguyên được tính |
| Truy vấn khai báo | Module có hỗ trợ expression trong query không; cú pháp binding và context là gì |
| Projection | Projection có dùng SpEL không; `target`, đối số và bean được cung cấp thế nào |
| Repository tự mở rộng | Ai tạo context, ai kiểm soát template và ai chuyển kết quả cho store |
| Auditing | Ai cung cấp auditor và thời gian; không mặc định annotation auditing sẽ đọc mọi expression |

Không lấy một đoạn dùng được với MongoDB rồi suy ra nó dùng được trong JPQL, JDBC, Elasticsearch hoặc Redis. Những nơi đó có ngôn ngữ truy vấn và mô hình ánh xạ khác nhau.

### 6.1. Truy vấn khai báo và binding tham số

Ví dụ riêng cho Spring Data JPA dưới đây minh họa một biểu thức SpEL ở vị trí tham số của JPQL:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
            select o
            from PurchaseOrder o
            where o.tenantId = :#{#tenantId.trim()}
              and o.status = :status
            """)
    List<PurchaseOrder> findForTenant(
            @Param("tenantId") String tenantId,
            @Param("status") OrderStatus status
    );
}
```

Ví dụ giả định entity có tên JPQL `PurchaseOrder`, có các thuộc tính `tenantId`, `status`, và `OrderStatus` là enum của ứng dụng. Các annotation, `JpaRepository` và `@Param` dùng theo API Spring Data JPA/Spring Data tương ứng.

Ở đây:

- `:#{...}` là cú pháp expression trong vị trí binding mà Spring Data JPA hỗ trợ.
- `#tenantId` liên hệ với tên tham số khai báo bằng `@Param`.
- `trim()` tạo giá trị tham số trước khi truyền cho truy vấn.
- `:status` là named parameter thông thường.

Ví dụ giúp thấy ranh giới giữa expression và binding; trong mã ứng dụng, nếu chuẩn hóa tenant là một quy tắc chung thì nên thực hiện ở lớp Java có trách nhiệm rõ ràng.

Nếu chỉ cần so sánh tenant nguyên trạng, ưu tiên dạng đơn giản:

```java
@Query("""
        select o
        from PurchaseOrder o
        where o.tenantId = :tenantId
        """)
List<PurchaseOrder> findForTenant(@Param("tenantId") String tenantId);
```

Không cần expression cho mọi tham số. Derived query như `findByTenantId(...)` cũng có thể đáp ứng trường hợp đơn giản.

Binding một giá trị không có nghĩa có thể binding mọi thành phần cấu trúc của truy vấn. Tên bảng, tên entity, tên thuộc tính và hướng sắp xếp phải tuân theo cơ chế mà store hỗ trợ; không thay chúng bằng chuỗi từ người dùng rồi xem đó là một tham số dữ liệu bình thường.

Tenant dùng để phân quyền phải được xác định từ nguồn đã xác thực. Việc có `#tenantId` trong expression không tự chứng minh người gọi được phép truy cập tenant đó.

### 6.2. Projection có SpEL

Trong cơ chế projection của Spring Data, một open projection có thể dùng `@Value` để tính thuộc tính:

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonSummary {

    String getFirstName();

    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Ví dụ giả định nguồn projection có `firstName` và `lastName`. Trong ngữ cảnh projection này, `target` là đối tượng nguồn mà cơ chế projection cung cấp.

Không suy ra rằng `target` có sẵn trong `StandardEvaluationContext` của ví dụ Java trước đó. Cũng không suy ra rằng mọi tính năng placeholder của `ValueExpressionParser` đều được bật tại mọi chỗ dùng `@Value`.

Expression có thể làm việc xác định các thuộc tính cần đọc trở nên khó hơn. Không mặc định open projection giữ nguyên các khả năng tối ưu truy vấn của closed projection; còn phải xét module và cách trả dữ liệu.

Với phép ghép tên đơn giản, có thể cân nhắc default method dựa trên các accessor sẵn có. Khi logic cần thêm dependency hoặc nhiều quy tắc, một thành phần Java riêng thường dễ kiểm tra hơn.

### 6.3. Derived query, phân trang và sắp xếp

Các abstraction quen thuộc khác vẫn có hợp đồng riêng:

- `findByStatusAndTenantId(...)` được phân tích theo quy tắc tên phương thức của derived query; không phải một template SpEL.
- `Pageable` biểu diễn yêu cầu phân trang và sắp xếp; không tự trở thành evaluation context.
- `Sort` mô tả thuộc tính và chiều sắp xếp theo khả năng của module; không phải nơi chèn biểu thức tùy ý.
- Query by Example xây dựng điều kiện từ probe và matcher; không nên xem nó là một ngôn ngữ expression tự do.

Nắm đúng ranh giới giúp lựa chọn abstraction nhỏ nhất đủ giải quyết bài toán.

### 6.4. Auditing và giá trị tính toán

Các annotation như `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate` và `@LastModifiedDate` thuộc cơ chế auditing. Auditor thường được cung cấp qua `AuditorAware` hoặc abstraction tương ứng cho reactive, còn thời gian có cơ chế cung cấp riêng.

Việc đặt một chuỗi có `${...}` hoặc `#{...}` vào trường entity không tự làm trường đó trở thành auditor, thời điểm tạo hay dữ liệu mặc định khi lưu. Muốn phối hợp expression với auditing, phải có một tích hợp được hỗ trợ hoặc mã Java chủ động đánh giá và chuyển giá trị vào đúng cơ chế.

## 7. Thiết kế context và quản lý metadata

Khi xây dựng repository fragment hoặc một thành phần dùng chung có hỗ trợ expression, cần xác định hợp đồng rõ ràng:

1. **Ai sở hữu template?** Template nên do mã ứng dụng hoặc cấu hình tin cậy kiểm soát.
2. **Những tên nào được công bố?** Ví dụ chỉ công bố `tenantId`, `region`, `operation`.
3. **Nguồn thuộc tính nào được sử dụng?** Dùng environment do ứng dụng kiểm soát, tránh tự tạo nguồn cấu hình khác với phần còn lại.
4. **Kết quả có ý nghĩa gì?** Đó là giá trị tham số, tên tài nguyên hay dữ liệu hiển thị.
5. **Khi nào đánh giá?** Theo cấu hình, theo repository invocation hay theo một thao tác cụ thể.
6. **Kết quả được kiểm tra thế nào?** Kiểm tra kiểu, null, tập ký tự hoặc danh sách giá trị hợp lệ trước khi chuyển cho store.

Các quyết định này tạo thành metadata của hợp đồng expression: chuỗi khai báo, các tên được cung cấp, kiểu kết quả kỳ vọng và chính sách context. Chúng không thay thế mapping metadata của entity, metadata repository hoặc schema của kho dữ liệu.

Ví dụ, `tenantId` dùng để tạo tên collection có thể phải tuân theo danh sách ký tự được cho phép và giới hạn đặt tên của store. Một phép tính SpEL thành công chưa đủ để chứng minh tên đó hợp lệ hoặc đã được cấp quyền.

Nên giữ danh sách tên biến ổn định. Đổi từ `#tenantId` sang `#tenant` là thay đổi hợp đồng đối với tất cả template đang dựa vào tên cũ, dù Java vẫn biên dịch.

## 8. Cache và khả năng chạy đồng thời

Phân tích và đánh giá là hai loại công việc khác nhau:

```text
Cùng template + context tenant A -> kết quả của A
Cùng template + context tenant B -> kết quả của B
```

Có thể cân nhắc tái sử dụng expression đã parse theo hợp đồng của thư viện. Tuy nhiên, cache giá trị cuối cùng chỉ theo chuỗi template sẽ sai khi kết quả phụ thuộc tenant, đối số phương thức, người dùng hoặc cấu hình đang dùng.

Ví dụ, với:

```text
orders-#{#tenantId}
```

nếu cache kết quả đầu tiên `orders-acme` rồi dùng cho mọi lời gọi, request của tenant khác có thể bị định tuyến nhầm.

Các nguyên tắc thực hành:

- Tách phần khai báo có thể tái sử dụng khỏi dữ liệu theo lời gọi.
- Không dùng chung một `StandardEvaluationContext` có biến mutable rồi liên tục đổi `tenantId` giữa các request đồng thời.
- Tạo hoặc cung cấp context theo vòng đời phù hợp; với reactive, lấy dữ liệu từ cơ chế context được framework hỗ trợ.
- Nếu cache kết quả, khóa cache phải bao quát mọi dữ liệu ảnh hưởng và có chính sách hết hiệu lực phù hợp.

Không mặc định `ThreadLocal` của mã đồng bộ sẽ truyền đúng tenant hoặc principal xuyên suốt một pipeline reactive.

## 9. Giới hạn quyền của expression

SpEL có thể làm nhiều hơn việc thay thế văn bản. Với context đầy đủ, nó có khả năng truy cập thuộc tính, gọi phương thức và sử dụng các cơ chế phân giải khác.

Vì vậy, không nhận nguyên một expression tùy ý từ request rồi đánh giá bằng `StandardEvaluationContext` có quyền truy cập rộng.

Nên tách hai loại đầu vào:

| Đầu vào | Cách xử lý thông thường |
| --- | --- |
| Template do ứng dụng sở hữu | Parse theo hợp đồng đã công bố |
| Giá trị tenant, trạng thái, từ khóa từ người dùng | Truyền như dữ liệu qua biến hoặc query parameter |
| Tên cột hoặc trường sắp xếp do người dùng chọn | Ánh xạ qua danh sách thuộc tính được cho phép |
| Chính sách nghiệp vụ phức tạp | Thực hiện trong Java hoặc thành phần có trách nhiệm rõ ràng |

Nếu nhu cầu chỉ là đọc một số thuộc tính và biến, có thể cân nhắc evaluation context hạn chế hơn, chẳng hạn `SimpleEvaluationContext` khi phù hợp. Đây là lựa chọn thiết kế cần cấu hình và kiểm chứng, không phải một cam kết rằng mọi biểu thức từ người dùng đều trở nên an toàn.

Ngoài ra, tránh để expression thực hiện side effect như ghi dữ liệu, gửi thông báo hoặc thay đổi trạng thái bean. Một expression có thể được đánh giá vào thời điểm hoặc với tần suất khác dự kiến; giữ nó như phép tính giúp hành vi dễ dự đoán hơn.

## 10. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Chuỗi `${app.stage}` còn nguyên | Chuỗi chưa đi qua cơ chế hỗ trợ hoặc resolver không giải quyết được | Kiểm tra thành phần thực sự đọc giá trị, environment và chính sách placeholder |
| Không tìm được thuộc tính cấu hình | Sai khóa, thiếu nguồn thuộc tính hoặc khác profile | Kiểm tra các property source thực tế của environment |
| SpEL trả `null` hoặc lỗi khi đọc biến | Chưa đăng ký biến hoặc truyền sai context | Đối chiếu tên biến và vòng đời context |
| `#tenantId` dùng được nhưng `tenantId` không dùng được | Một bên là biến, một bên là thuộc tính root object | Chọn cú pháp đúng với dữ liệu đã cung cấp |
| Không tìm được bean khi dùng `@policy` | Chưa có bean resolver hoặc tên bean không đúng | Dùng tích hợp có hỗ trợ hoặc cấu hình resolver có chủ đích |
| Expression đúng ở projection nhưng lỗi ở query | Hai ngữ cảnh công bố các tên khác nhau | Dùng đúng tập biến và cú pháp của module tích hợp |
| Lỗi ép kiểu khi lấy kết quả | Expression trả số hoặc object nhưng mã gọi giả định là chuỗi | Kiểm tra kiểu kết quả và cơ chế chuyển đổi |
| Các tenant dùng chung một kết quả | Cache thiếu khóa context hoặc dùng chung context mutable | Tách context và kiểm tra chiến lược cache |
| Thay đổi cấu hình nhưng giá trị không đổi | Kết quả đã được tính hoặc cache ở giai đoạn trước | Xác định thời điểm đánh giá và chính sách cập nhật |
| Truy vấn không hợp lệ dù expression tính được | Kết quả không đáp ứng cú pháp hoặc giới hạn store | Kiểm tra tích hợp truy vấn và ràng buộc của kho dữ liệu |

Khi ghi log, ưu tiên tên template, vị trí khai báo và loại lỗi. Không đưa toàn bộ dữ liệu context hoặc các thuộc tính bí mật vào thông báo lỗi chỉ để dễ chẩn đoán.

## 11. Bài thực hành

### 11.1. Tạo tên tài nguyên theo môi trường và tenant

Dùng ví dụ `ValueExpressionDemo` làm điểm bắt đầu.

Yêu cầu:

1. Giữ template `orders-${app.stage:local}-#{#tenantId}`.
2. Tạo context riêng cho tenant `acme` và `beta`.
3. Đánh giá cùng một expression đã parse với từng context.
4. Bỏ thuộc tính `app.stage` khỏi nguồn cấu hình để quan sát mặc định.
5. Kiểm tra kết quả trước khi coi nó là tên tài nguyên hợp lệ.

Kết quả kỳ vọng khi environment có `app.stage=dev`:

```text
orders-dev-acme
orders-dev-beta
```

Khi không có `app.stage` trong bất kỳ nguồn thuộc tính nào của environment dùng cho bài thực hành:

```text
orders-local-acme
orders-local-beta
```

Lưu ý `StandardEnvironment` còn có các nguồn hệ thống; xóa một khóa trong `MapPropertySource` tự tạo chưa chắc khiến khóa đó biến mất khỏi toàn bộ environment.

### 11.2. So sánh kiểu kết quả

Đánh giá các khai báo sau và ghi nhận giá trị cùng kiểu Java thực tế:

```text
#{10 + 5}
count-#{10 + 5}
${limits.page-size:20}
```

Giải thích vì sao một giá trị nhìn giống số trong placeholder không tự có cùng kiểu với kết quả phép toán số nguyên của SpEL.

### 11.3. Thiết kế một hợp đồng expression nhỏ

Giả sử repository fragment cần tạo nhãn log theo template:

```text
${app.stage:local}:#{#tenantId}:#{#operation}
```

Hãy mô tả:

- Nguồn đáng tin cậy của `tenantId`.
- Các giá trị hợp lệ của `operation`.
- Nơi lưu template và thời điểm parse.
- Context được tạo cho mỗi thao tác như thế nào.
- Vì sao không cache nhãn cuối cùng chỉ theo template.

Nhãn log không thay thế bộ lọc tenant trong truy vấn và cũng không tạo ra kiểm tra phân quyền.

## 12. Điểm cần ghi nhớ

- `${...}` lấy giá trị cấu hình; `#{...}` đánh giá SpEL trong template.
- Value expression có thể kết hợp văn bản cố định, placeholder và SpEL.
- `ValueExpressionParser` xử lý khai báo; `ValueEvaluationContext` cung cấp dữ liệu cần để đánh giá.
- Biến SpEL, thuộc tính root object, bean và khóa environment là các cách truy cập khác nhau.
- Tính đúng của expression phụ thuộc context, thời điểm đánh giá, kiểu kết quả và cơ chế tích hợp.
- Khả năng dùng expression trong query, projection hoặc mapping phải được xét theo từng module Spring Data.
- Giữ đầu vào người dùng ở dạng dữ liệu, kiểm soát template và tách context theo lời gọi khi có dữ liệu tenant hoặc người dùng.