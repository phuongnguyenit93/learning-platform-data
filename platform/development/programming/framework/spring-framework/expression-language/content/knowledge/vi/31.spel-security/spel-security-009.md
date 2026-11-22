# Thiết kế allowlist và kiểm thử các trường hợp vượt quyền

Khi ứng dụng cho phép cấu hình hoặc người dùng cung cấp biểu thức Spring Expression Language (SpEL), cần xác định chính xác biểu thức được phép đọc dữ liệu nào và được phép thực hiện thao tác gì. **Allowlist** là danh sách tường minh những property, method, kiểu Java và hành vi mà biểu thức được quyền sử dụng. Mọi khả năng không nằm trong danh sách đều phải bị từ chối.

Đây là vấn đề bảo mật vì SpEL có thể làm nhiều hơn phép tính hoặc so sánh. Với một EvaluationContext rộng, biểu thức có thể truy cập property, gọi method, tạo object, tham chiếu kiểu Java hoặc bean nếu các cơ chế tương ứng được bật. Nếu chuỗi biểu thức đến từ nguồn không đáng tin cậy, việc đánh giá nó trong context mặc định có thể mở ra quyền truy cập ngoài dự kiến.

Thiết kế an toàn bắt đầu từ việc giới hạn dữ liệu được expose, chọn EvaluationContext có ít khả năng nhất, rồi kiểm thử cả những biểu thức hợp lệ lẫn các trường hợp cố vượt quyền.

## Xác định threat model

Trước khi xây dựng allowlist, hãy làm rõ ai có thể kiểm soát từng thành phần:

- **Expression source:** người dùng có thể nhập hoặc sửa toàn bộ chuỗi SpEL hay chỉ chọn một quy tắc có sẵn?
- **Input values:** người dùng chỉ cung cấp giá trị như số, chuỗi và ngày tháng, còn expression do ứng dụng kiểm soát?
- **Root object:** biểu thức được đánh giá trên DTO giới hạn hay trên object nghiệp vụ có nhiều tham chiếu?
- **EvaluationContext:** context có cung cấp method resolver, type locator, bean resolver hoặc constructor resolver rộng không?
- **Output:** kết quả được hiển thị, dùng để quyết định quyền, ghi database hay truyền sang một hệ thống khác?

Cần phân biệt rõ **dữ liệu đầu vào** và **mã biểu thức**. Nếu người dùng chỉ gửi giá trị như tên, số lượng hoặc ngưỡng, hãy đưa chúng vào biến trong EvaluationContext. Không nối dữ liệu đó trực tiếp vào chuỗi SpEL rồi parse lại.

Ví dụ, cách truyền dữ liệu an toàn và dễ kiểm soát hơn:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimum", minimumFromRequest);
context.setVariable("status", statusFromRequest);

Expression expression =
        parser.parseExpression("amount >= #minimum and state == #status");
~~~

Các giá trị request được truyền như dữ liệu. Chúng không được diễn giải thành cú pháp SpEL. Ngược lại, nếu ghép trực tiếp input vào chuỗi expression, ký tự do người dùng cung cấp có thể thay đổi cấu trúc biểu thức.

## Ưu tiên EvaluationContext có bề mặt truy cập nhỏ

**StandardEvaluationContext** cung cấp nhiều khả năng linh hoạt và mặc định có các cơ chế reflective để truy cập property, gọi method và tạo object. Nó phù hợp với biểu thức do ứng dụng kiểm soát, nhưng cần cấu hình rất cẩn thận nếu expression source không đáng tin cậy.

Nếu chỉ cần đọc property để đánh giá điều kiện, hãy cân nhắc **SimpleEvaluationContext**. Context này được thiết kế cho một tập con tính năng SpEL và không hỗ trợ type reference, constructor invocation hoặc bean reference. Method invocation cũng không được bật mặc định trong cấu hình data binding thông thường.

Ví dụ context chỉ đọc cho data binding:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Context read-only giới hạn việc gán property qua SpEL. Nó không biến object Java thành immutable, không copy collection và không ngăn code Java khác thay đổi object đang được tham chiếu. Vì vậy, vẫn cần dùng root object nhỏ và có vòng đời phù hợp.

Nếu cần allowlist property chính xác hơn, có thể cung cấp PropertyAccessor riêng:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forPropertyAccessors(
                new AllowlistedCriteriaAccessor())
                .build();
~~~

Accessor chỉ nên đọc những property được định nghĩa trong chính sách. Nếu use case không cần method invocation, không bật instance methods và không đăng ký MethodResolver bổ sung.

## Thiết kế root object theo allowlist

Không nên đưa entity, service, repository, application context hoặc object có nhiều tham chiếu vào root object của expression do bên ngoài cung cấp. Những object này có thể mở đường truy cập đến dữ liệu hoặc hành vi không liên quan đến mục đích của biểu thức.

Hãy tạo một DTO nhỏ chỉ chứa các giá trị cần thiết:

~~~java
public final class PricingFacts {
    private final String region;
    private final BigDecimal amount;
    private final boolean active;

    public PricingFacts(
            String region,
            BigDecimal amount,
            boolean active) {
        this.region = region;
        this.amount = amount;
        this.active = active;
    }

    public String getRegion() {
        return region;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Biểu thức có thể kiểm tra các property đã chọn:

~~~java
Expression expression = parser.parseExpression(
        "active == true and amount >= #minimum");

Boolean accepted =
        expression.getValue(context, facts, Boolean.class);
~~~

Root object chỉ chứa dữ liệu cần cho điều kiện. Không đưa method có side effect, service hoặc object quản lý tài nguyên vào DTO. Nếu một property không cần cho biểu thức, tốt nhất không expose nó ngay từ đầu.

DTO nên ưu tiên các kiểu value đơn giản, immutable hoặc có thể copy an toàn. Với collection và Map, chỉ đưa vào những phần tử cần thiết và tránh để biểu thức truy cập object mutable có thể thay đổi trạng thái ứng dụng.

## PropertyAccessor allowlist

**PropertyAccessor** quyết định SpEL có thể đọc hoặc ghi property trên một target hay không. Một accessor allowlist nên kiểm tra cả kiểu target và tên property. Đối với biểu thức chỉ đọc, **canWrite(...)** phải trả về false và **write(...)** phải từ chối thao tác.

Ví dụ rút gọn cho một DTO có hai property được phép:

~~~java
public final class CriteriaAccessor implements PropertyAccessor {

    @Override
    public Class<?>[] getSpecificTargetClasses() {
        return new Class<?>[] { PricingFacts.class };
    }

    @Override
    public boolean canRead(
            EvaluationContext context,
            Object target,
            String name) {
        if (target == null || target.getClass() != PricingFacts.class) {
            return false;
        }

        return "region".equals(name)
                || "amount".equals(name);
    }

    @Override
    public TypedValue read(
            EvaluationContext context,
            Object target,
            String name) throws AccessException {
        if (!canRead(context, target, name)) {
            throw new AccessException("Property is not allowlisted");
        }

        PricingFacts facts = (PricingFacts) target;

        if ("region".equals(name)) {
            return new TypedValue(facts.getRegion());
        }

        if ("amount".equals(name)) {
            return new TypedValue(facts.getAmount());
        }

        throw new AccessException("Unknown property");
    }

    @Override
    public boolean canWrite(
            EvaluationContext context,
            Object target,
            String name) {
        return false;
    }

    @Override
    public void write(
            EvaluationContext context,
            Object target,
            String name,
            Object newValue) throws AccessException {
        throw new AccessException("Read-only access");
    }
}
~~~

Đăng ký accessor này bằng **SimpleEvaluationContext.forPropertyAccessors(...)** để context chỉ sử dụng accessor được cung cấp. Khi dùng StandardEvaluationContext, cần chú ý rằng việc thêm accessor allowlist nhưng vẫn giữ ReflectivePropertyAccessor có thể tạo fallback rộng hơn dự kiến.

Một allowlist chỉ kiểm tra tên property là chưa đủ nếu nó áp dụng cho mọi target type. Hãy kiểm tra cả class đích, kiểu trả về và các property lồng nhau. Nếu cho phép truy cập customer.address.city, mỗi tầng object đều cần có chính sách truy cập phù hợp.

## Method allowlist

Method invocation làm tăng đáng kể khả năng của biểu thức. Một method có thể đọc dữ liệu nhạy cảm, thay đổi trạng thái, truy cập file, mạng hoặc gọi các thành phần khác của ứng dụng.

Nếu không cần gọi method, hãy để method invocation bị tắt. Nếu thật sự cần, chỉ cho phép method thuần, có đầu vào và đầu ra đơn giản, không tạo side effect.

Với StandardEvaluationContext, **MethodResolver** có thể giới hạn lời gọi theo:

- Kiểu chính xác của target object.
- Tên method.
- Số lượng và kiểu đối số.
- Kiểu trả về.
- Các overload được phép cụ thể.

Không nên chỉ allowlist tên method. Hai lớp khác nhau có thể có method cùng tên nhưng hành vi hoàn toàn khác nhau. Một overload cũng có thể nhận kiểu đối số rộng hơn và tạo tác động mà overload khác không có.

Nếu dùng resolver tùy chỉnh, không giữ một ReflectiveMethodResolver rộng làm fallback khi mục tiêu là từ chối mọi method ngoài danh sách. Khi resolver tùy chỉnh trả về null, resolver tiếp theo có thể xử lý lời gọi đó.

## Type reference và ConstructorResolver

Cú pháp **T(...)** cho phép expression tham chiếu đến kiểu Java. Nếu TypeLocator phân giải được kiểu, biểu thức có thể đọc static field hoặc gọi static method. Một số static method có thể thực hiện tác động phụ.

Cú pháp **new ...(...)** cho phép tạo object thông qua constructor. Với StandardEvaluationContext, ReflectiveConstructorResolver mặc định có thể tìm constructor phù hợp.

Nếu expression source không đáng tin cậy, nên từ chối type reference và constructor invocation trừ khi có use case cụ thể. SimpleEvaluationContext không hỗ trợ hai khả năng này. Nếu bắt buộc dùng StandardEvaluationContext, hãy:

- Dùng TypeLocator theo allowlist thay vì cho phép phân giải tùy ý.
- Đăng ký ConstructorResolver chỉ cho các kiểu và constructor được chọn.
- Không để resolver reflective rộng làm fallback ngoài ý muốn.
- Kiểm tra cả đối số và kiểu kết quả.
- Không cho phép tạo object có constructor đọc tài nguyên hoặc tạo side effect.

Package import của StandardTypeLocator chỉ là tiện ích phân giải tên ngắn, không phải cơ chế bảo mật. Chỉ đăng ký một package không đồng nghĩa các kiểu khác đã bị chặn nếu tên đầy đủ vẫn được phân giải.

## Không expose bean hoặc object có quyền rộng

Cú pháp **@beanName** có thể tham chiếu Spring bean nếu EvaluationContext có BeanResolver. Không cấu hình BeanResolver cho biểu thức không cần truy cập bean.

Tránh đưa các service hoặc repository vào variable. Một biến chứa object không chỉ cung cấp dữ liệu; nếu context cho phép method invocation hoặc truy cập property phù hợp, expression có thể sử dụng các khả năng của object đó.

Nếu cần một hàm nghiệp vụ, hãy cân nhắc tính kết quả trong Java rồi truyền giá trị vào context. Nếu bắt buộc expose một function, chỉ đăng ký method tĩnh hoặc wrapper nhỏ đã được kiểm soát và không có quyền truy cập tài nguyên ngoài mục đích.

## Không dựa vào blacklist chuỗi

Không nên cố bảo vệ SpEL bằng cách tìm và loại bỏ một số chuỗi như **Runtime**, **Class**, **getClass**, **new** hoặc **T(**. Blacklist thường bỏ sót cú pháp tương đương, cách viết lồng nhau, property traversal, overload, alias hoặc khả năng khác của ngôn ngữ.

Thay vào đó:

1. Chỉ cho phép những capability cần thiết.
2. Giới hạn root object và các giá trị trong context.
3. Dùng accessor/resolver theo allowlist.
4. Từ chối mọi khả năng không được khai báo.
5. Nếu nghiệp vụ chỉ cần một ngôn ngữ điều kiện nhỏ, cân nhắc xây dựng DSL riêng với grammar giới hạn thay vì nhận SpEL tùy ý.

Không nên dựa vào việc phân tích AST nội bộ của SpEL như một ranh giới bảo mật nếu ứng dụng không kiểm soát chặt phiên bản và toàn bộ node được hỗ trợ. Một blacklist AST chưa đầy đủ cũng có thể bỏ lọt hành vi nguy hiểm.

## Giới hạn template expression và expression injection

Nếu ứng dụng chỉ cần đánh giá expression thuần, hãy dùng **parseExpression(String)**. Không bật template parsing cho dữ liệu người dùng nếu không có nhu cầu rõ ràng.

Template expression cho phép nhúng SpEL giữa văn bản, thường với delimiter **#{** và **}**. Nếu người dùng có thể chèn delimiter vào nội dung template rồi toàn bộ chuỗi được parse như template, phần dữ liệu có thể trở thành mã biểu thức.

Không nối dữ liệu không tin cậy vào expression source. Hãy giữ expression do ứng dụng kiểm soát và đưa input vào bằng variable:

~~~java
context.setVariable("searchText", userSuppliedText);

Expression expression =
        parser.parseExpression("#searchText == #expectedText");
~~~

Trong ví dụ, nội dung userSuppliedText là một giá trị String. Các ký tự giống cú pháp SpEL bên trong giá trị đó không được parse lại thành expression.

Nếu cần cho phép người dùng chỉnh sửa template, phải coi template là mã có thể thực thi. Hãy kiểm soát người được quyền sửa, dùng context hạn chế và escape kết quả theo định dạng đầu ra như HTML. SpEL không tự escape kết quả cho HTML, SQL hoặc shell.

## Kiểm soát chi phí và độ phức tạp

Một biểu thức không cần gọi method nguy hiểm vẫn có thể tiêu tốn nhiều CPU hoặc bộ nhớ nếu nó duyệt collection lớn, tạo kết quả lớn hoặc dùng các thao tác tính toán tốn kém.

Các biện pháp nên áp dụng:

- Giới hạn độ dài expression source.
- Giới hạn kích thước collection và số lượng phần tử được đưa vào context.
- Hạn chế số tầng truy cập property và độ phức tạp của biểu thức.
- Không expose method có thời gian chạy không giới hạn hoặc phụ thuộc mạng.
- Tránh cho phép biểu thức người dùng cung cấp regex hoặc thao tác có thể tạo workload bất thường nếu không có kiểm soát.
- Giới hạn tần suất đánh giá và theo dõi thời gian thực thi.

SpEL không cung cấp một timeout an toàn tổng quát để dừng tùy ý một method đang chạy. Không nên xem việc interrupt một thread là biện pháp sandbox đáng tin cậy. Nếu phải đánh giá biểu thức thực sự không đáng tin cậy với nguy cơ tiêu tốn tài nguyên, cần cách ly trong tiến trình hoặc môi trường có giới hạn tài nguyên phù hợp.

## Kiểm thử allowlist theo hai chiều

Bộ test cần chứng minh cả hai điều:

- Biểu thức được phép hoạt động đúng.
- Biểu thức ngoài allowlist bị từ chối và không tạo side effect.

Không chỉ kiểm tra kết quả Boolean. Cần xác nhận object gốc, collection, bộ đếm side effect và trạng thái ứng dụng không thay đổi sau các lần thử vượt quyền.

### Kiểm thử trường hợp hợp lệ

Ví dụ dùng JUnit:

~~~java
@Test
void evaluatesAllowlistedCondition() {
    PricingFacts facts = new PricingFacts(
            "VN",
            new BigDecimal("120.00"),
            true);

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .build();

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "active == true and amount >= #minimum");

    context.setVariable("minimum", new BigDecimal("100.00"));

    Boolean result =
            expression.getValue(context, facts, Boolean.class);

    assertTrue(result);
}
~~~

Test này xác nhận property được phép đọc và variable đầu vào được dùng đúng. Có thể bổ sung trường hợp ngưỡng cao hơn để xác nhận kết quả false.

### Kiểm thử type reference bị từ chối

Dùng các chuỗi sau làm input kiểm thử trong context giới hạn:

~~~java
"T(java.lang.Runtime)"
"T(java.lang.System).getProperties()"
~~~

Parser có thể chấp nhận cấu trúc expression, nhưng EvaluationContext không hỗ trợ type reference nên evaluation phải bị từ chối. Các chuỗi trên chỉ là dữ liệu test; không đánh giá chúng trong một StandardEvaluationContext rộng.

### Kiểm thử constructor invocation bị từ chối

~~~java
"new java.io.File('sample.txt')"
~~~

Context chỉ đọc không hỗ trợ constructor invocation. Test phải xác nhận biểu thức không tạo object qua constructor. Không cần thực thi hành vi đọc/ghi file để kiểm tra điều này.

### Kiểm thử method invocation bị từ chối

~~~java
"#root.toString()"
"#root.getClass()"
~~~

Nếu policy không cho phép method invocation, các biểu thức gọi method phải thất bại khi evaluate. Kiểm tra trên context thật được dùng trong production; không suy luận từ một context test có cấu hình khác.

### Kiểm thử bean reference bị từ chối

~~~java
"@sensitiveService"
~~~

Nếu context không có BeanResolver hoặc dùng SimpleEvaluationContext, bean reference phải bị từ chối. Không đăng ký service thật chỉ để chạy test từ chối; có thể dùng một bean giả có bộ đếm để xác nhận nó không bị gọi nếu integration test cần kiểm tra đường truy cập.

### Kiểm thử assignment và property write

~~~java
"active = false"
~~~

Trong context read-only, phép gán property phải bị từ chối. Sau khi evaluation thất bại, kiểm tra lại giá trị active của object gốc để bảo đảm trạng thái không đổi.

### Kiểm thử property ngoài allowlist

Nếu DTO hoặc accessor chỉ cho phép region và amount, thử đọc một property khác như internalCode hoặc owner. Evaluation phải thất bại và không được fallback sang reflective accessor.

Đặc biệt, kiểm thử property lồng nhau, Map key, array index và property class. Không chỉ test một tên property trực tiếp; hãy kiểm tra các đường truy cập có thể dẫn đến object khác.

## Ma trận test vượt quyền

Có thể tổ chức test theo nhóm:

| Nhóm | Ví dụ đầu vào | Kết quả mong đợi |
|---|---|---|
| Property hợp lệ | **amount >= #minimum** | Được đánh giá |
| Property ngoài allowlist | **internalCode** | Bị từ chối |
| Property lồng nhau ngoài phạm vi | **owner.account.secret** | Bị từ chối |
| Ghi property | **active = false** | Bị từ chối |
| Method invocation | **#root.getClass()** | Bị từ chối nếu không allowlist |
| Type reference | **T(java.lang.Runtime)** | Bị từ chối |
| Static method | **T(java.lang.System).getProperties()** | Bị từ chối |
| Constructor | **new java.io.File('x')** | Bị từ chối |
| Bean reference | **@sensitiveService** | Bị từ chối |
| Template injection | Nội dung có delimiter **#{...}** | Không được parse lại nếu chỉ là dữ liệu |
| Collection traversal | Selection/projection trên dữ liệu không expose | Bị từ chối hoặc giới hạn theo policy |
| Input quá lớn | Expression vượt giới hạn độ dài | Bị từ chối trước evaluation |

Kết quả mong đợi phải được xác định theo context thực tế. Nếu policy chủ động cho phép một method hoặc collection operation, hãy ghi rõ ngoại lệ và thêm test cho đúng capability đó.

## Kiểm tra không có side effect

Một test bảo mật cần xác nhận trạng thái không đổi, không chỉ xác nhận có exception.

Ví dụ, một DTO test có bộ đếm setter hoặc một collaborator giả có bộ đếm số lần gọi. Trước khi đánh giá biểu thức bị từ chối, lưu trạng thái ban đầu. Sau đó xác nhận:

- Setter không được gọi.
- Method ngoài allowlist không được thực thi.
- Constructor ngoài allowlist không được gọi.
- Collection nguồn không bị thêm, xóa hoặc thay phần tử.
- Bean hoặc service giả không nhận lời gọi.
- Không có event hoặc thay đổi persistence state ngoài dự kiến.

Nếu kiểm thử entity đang được quản lý bởi persistence context, cần xác nhận cả trạng thái trong bộ nhớ và dữ liệu sau transaction theo cách phù hợp. Một phép gán trong bộ nhớ có thể được ORM ghi xuống database khi flush hoặc commit.

## Kiểm thử biến và context isolation

Biến được đưa vào EvaluationContext là dữ liệu, nhưng giá trị của biến vẫn có thể là object có hành vi. Hãy kiểm tra rằng context chỉ nhận kiểu đầu vào đã được chuẩn hóa và không nhận service hoặc object có quyền rộng.

Nếu context được tạo riêng cho từng request, test hai request liên tiếp với hai bộ biến khác nhau để xác nhận không có giá trị bị rò rỉ. Nếu Expression được cache để tái sử dụng, hãy tạo context phù hợp cho mỗi lần đánh giá và không chia sẻ context mutable giữa các luồng khi biến có thể thay đổi.

Cache expression cũng cần gắn với chính sách bảo mật. Không dùng một expression đã parse trong một context rộng rồi tái sử dụng ở một nơi có policy khác mà không xem xét khác biệt quyền truy cập.

## Kiểm thử parser và giới hạn đầu vào

Bên cạnh capability, hãy kiểm tra giới hạn tài nguyên:

- Expression rỗng hoặc chỉ có khoảng trắng.
- Expression vượt giới hạn độ dài.
- Biểu thức có nhiều tầng lồng nhau.
- Collection đầu vào có kích thước vượt giới hạn.
- Biểu thức có nhiều lần selection/projection.
- Giá trị null, kiểu không tương thích và conversion thất bại.
- Template chứa delimiter bất ngờ.
- Các cách viết có khoảng trắng, chữ hoa/thường hoặc ký tự Unicode.

Không nên chỉ kiểm tra blacklist bằng cách thử một vài chuỗi tấn công đã biết. Kiểm thử phải xác nhận toàn bộ policy capability: những gì được phép đều hoạt động, những gì không được phép đều không có đường truy cập thay thế.

## Xử lý lỗi mà không làm lộ nội bộ

Khi biểu thức bị từ chối, ứng dụng nên trả thông báo bên ngoài ngắn gọn, ví dụ **Expression is not permitted** hoặc **Invalid rule**. Không trả stack trace, tên class nội bộ, đường dẫn file, cấu hình bean hoặc chi tiết runtime cho người dùng.

Ở phía server, ghi log loại lỗi, mã rule, định danh request và nhóm capability bị từ chối. Không ghi toàn bộ expression hoặc giá trị biến nếu chúng có thể chứa dữ liệu cá nhân, token hoặc thông tin bí mật.

Tách lỗi parse, lỗi evaluation và lỗi policy giúp vận hành dễ hơn. Tuy nhiên, không nên dùng thông báo lỗi chi tiết như một oracle cho người dùng thử dò cấu trúc nội bộ.

## Checklist triển khai

- Xác định expression source có do người dùng kiểm soát hay chỉ dữ liệu đầu vào được kiểm soát.
- Dùng SimpleEvaluationContext nếu chỉ cần đọc property và không cần các khả năng nâng cao.
- Tạo root DTO nhỏ, chỉ chứa dữ liệu cần thiết.
- Dùng PropertyAccessor allowlist cho property chính xác.
- Không bật method invocation nếu không cần.
- Nếu cần method, allowlist theo target type và chữ ký, không chỉ tên.
- Từ chối type reference, constructor invocation và bean reference trừ khi có yêu cầu cụ thể.
- Không để reflective resolver rộng làm fallback ngoài ý muốn.
- Truyền input bằng variable thay vì nối vào expression source.
- Không parse dữ liệu người dùng như template.
- Giới hạn độ dài, kích thước dữ liệu và chi phí đánh giá.
- Test positive, negative, nested access, mutation, side effect và context isolation.
- Escape/encode kết quả theo định dạng đầu ra.
- Theo dõi và cập nhật test khi nâng phiên bản Spring.

## Kết luận

Thiết kế allowlist cho SpEL cần giới hạn toàn bộ bề mặt mà biểu thức có thể truy cập: root object, property, method, type, constructor, bean và biến. Hãy ưu tiên SimpleEvaluationContext cùng DTO nhỏ khi chỉ cần đọc dữ liệu; nếu cần capability nâng cao, đăng ký accessor và resolver có allowlist rõ ràng, không để fallback reflective mở lại quyền đã từ chối.

Bộ test phải chứng minh biểu thức hợp lệ chạy đúng và các trường hợp vượt quyền đều bị chặn mà không tạo side effect. Đặc biệt, hãy kiểm thử property lồng nhau, method, type reference, constructor, bean reference, assignment, template injection, dữ liệu lớn và việc tái sử dụng context. Nếu nghiệp vụ chỉ cần một ngôn ngữ điều kiện nhỏ, DSL riêng với grammar giới hạn thường dễ bảo vệ hơn việc nhận SpEL tùy ý.
