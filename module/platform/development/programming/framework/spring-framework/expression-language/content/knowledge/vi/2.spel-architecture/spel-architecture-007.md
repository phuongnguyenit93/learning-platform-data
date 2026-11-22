# StandardEvaluationContext với đầy đủ khả năng mở rộng

## 1. Vai trò của EvaluationContext trong SpEL

Spring Expression Language (SpEL) tách việc phân tích biểu thức khỏi việc giải quyết các tham chiếu khi chạy. `ExpressionParser` phân tích chuỗi thành một `Expression`; `Expression` thực thi biểu thức; còn `EvaluationContext` cung cấp môi trường để biểu thức tìm đối tượng, thuộc tính, phương thức, constructor, bean, kiểu dữ liệu và các phép chuyển đổi cần thiết.

`StandardEvaluationContext` là implementation đầy đủ tính năng của `EvaluationContext`. Nó cho phép:

- Chọn đối tượng gốc (root object) mà các tên thuộc tính và phương thức không có tiền tố sẽ được giải quyết trên đó.
- Thay thế hoặc bổ sung cách SpEL đọc/ghi thuộc tính, gọi phương thức, tạo đối tượng và truy cập phần tử theo chỉ số.
- Cung cấp cách tìm bean, tìm kiểu, chuyển đổi giá trị, so sánh và thực hiện phép toán.
- Đăng ký biến và hàm để biểu thức tham chiếu.
- Tùy chỉnh các chiến lược theo mô hình dữ liệu hoặc quy tắc nghiệp vụ của ứng dụng.

Hãy dùng `StandardEvaluationContext` khi biểu thức do ứng dụng hoặc quản trị viên tin cậy định nghĩa và cần toàn bộ khả năng của SpEL. Nếu chỉ cần data binding hoặc lọc dữ liệu với một tập tính năng giới hạn, hãy xem `SimpleEvaluationContext`.

## 2. Tạo context và thiết lập root object

Root object là đối tượng mặc định để SpEL giải quyết các tham chiếu không có tiền tố. Có thể truyền root object qua constructor hoặc thiết lập sau:

```java
Order order = new Order(new BigDecimal("100.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

// Tương đương:
context.setRootObject(order);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("subtotal");

BigDecimal subtotal = expression.getValue(context, BigDecimal.class);
```

Trong ví dụ trên, `subtotal` được đọc từ root object. Khi cần truy cập biến đã đăng ký, dùng tiền tố `#`, ví dụ `#taxRate`. Có thể đổi root object bằng `setRootObject()`, hoặc truyền một root object riêng khi gọi overload tương ứng của `Expression.getValue()`.

Nếu cần cung cấp thêm metadata kiểu cho root object, `setRootObject(Object, TypeDescriptor)` cho phép truyền cả `TypeDescriptor`.

## 3. Các điểm mở rộng

`StandardEvaluationContext` cung cấp sẵn các chiến lược chuẩn. Có thể thêm chiến lược riêng bằng các phương thức `add...`, thay danh sách bằng `set...`, hoặc lấy cấu hình hiện tại qua các phương thức `get...`.

| Thành phần | Vai trò và mặc định thường dùng | Điểm mở rộng |
|---|---|---|
| Root object | Đối tượng mặc định cho tên thuộc tính/phương thức không có tiền tố. | Constructor, `setRootObject()`, `getRootObject()`. |
| Property accessor | Đọc/ghi thuộc tính và field; mặc định dùng `ReflectivePropertyAccessor`. | `addPropertyAccessor()`, `setPropertyAccessors()`, `removePropertyAccessor()`. |
| Method resolver | Tìm phương thức phù hợp để gọi; mặc định dùng `ReflectiveMethodResolver`. | `addMethodResolver()`, `setMethodResolvers()`, `removeMethodResolver()`. |
| Constructor resolver | Tìm constructor để xử lý biểu thức `new`; mặc định dùng `ReflectiveConstructorResolver`. | `addConstructorResolver()`, `setConstructorResolvers()`, `removeConstructorResolver()`. |
| Bean resolver | Giải quyết tham chiếu bean dạng `@beanName`; context tự tạo không có resolver bean được cấu hình sẵn. | `setBeanResolver()`. |
| Type locator | Tìm lớp cho biểu thức tham chiếu kiểu `T(...)`; mặc định dùng `StandardTypeLocator`. | `setTypeLocator()`. |
| Type converter | Chuyển đổi giá trị, bao gồm chuyển đổi khi gán và khi yêu cầu kiểu kết quả; mặc định dùng `StandardTypeConverter`. | `setTypeConverter()`. |
| Type comparator | So sánh hai giá trị; mặc định dùng `StandardTypeComparator`. | `setTypeComparator()`. |
| Operator overloader | Bổ sung cách thực hiện phép toán cho các kiểu dữ liệu ngoài tập kiểu chuẩn; mặc định dùng `StandardOperatorOverloader`. | `setOperatorOverloader()`. |
| Variables và functions | Lưu giá trị để biểu thức truy cập bằng `#name`; đăng ký hàm để gọi bằng `#function(...)`. | `setVariable()`, `setVariables()`, `lookupVariable()`, `registerFunction()`. |
| Index accessor | Tùy chỉnh cách đọc/ghi cấu trúc được truy cập bằng `[index]`; API `IndexAccessor` có từ Spring Framework 6.2. | `addIndexAccessor()`, `setIndexAccessors()`, `removeIndexAccessor()`. |

### 3.1. PropertyAccessor: tùy chỉnh cách đọc và ghi thuộc tính

Property accessor quyết định một thuộc tính có thể được đọc hoặc ghi trên đối tượng đích hay không. Accessor mặc định dựa trên reflection và hỗ trợ các kiểu truy cập thuộc tính Java thông dụng.

Khi cần đọc key của `Map` như một thuộc tính SpEL, có thể thêm `MapAccessor` từ module Spring Context:

```java
Map<String, Object> values = new HashMap<>();
values.put("status", "PAID");

StandardEvaluationContext context =
        new StandardEvaluationContext(values);

context.addPropertyAccessor(new MapAccessor());

String status = parser.parseExpression("status")
        .getValue(context, String.class);
```

Với cấu trúc dữ liệu riêng, triển khai `PropertyAccessor`. Các phương thức chính là `getSpecificTargetClasses()`, `canRead()`, `read()`, `canWrite()` và `write()`. `canRead()`/`canWrite()` xác định accessor có xử lý được thuộc tính trên đối tượng đích hay không; `read()`/`write()` thực hiện thao tác tương ứng.

Ưu tiên `addPropertyAccessor()` khi chỉ cần bổ sung một accessor. `setPropertyAccessors()` thay toàn bộ danh sách hiện có, vì vậy nếu dùng nó, hãy giữ lại các accessor mặc định mà ứng dụng vẫn cần.

### 3.2. MethodResolver và ConstructorResolver

`MethodResolver` quyết định cách SpEL tìm phương thức theo tên và danh sách đối số. `ConstructorResolver` quyết định cách tìm constructor cho biểu thức tạo đối tượng, chẳng hạn `new java.lang.String('hello')`.

Có thể triển khai resolver riêng rồi đăng ký:

```java
context.addMethodResolver(new DomainMethodResolver());
context.addConstructorResolver(new DomainConstructorResolver());
```

Mỗi resolver có thể từ chối xử lý một lời gọi để resolver tiếp theo thử tiếp. Nếu thay danh sách bằng `setMethodResolvers()` hoặc `setConstructorResolvers()`, danh sách cũ sẽ bị thay thế.

Với reflective method resolver, `registerMethodFilter(Class, MethodFilter)` cho phép lọc các phương thức được xem xét cho một kiểu đích. Đây là cách bổ sung để kiểm soát phương thức được phơi bày qua kiểu đó; nó không thay thế việc thiết kế root object và các accessor an toàn.

### 3.3. BeanResolver: tham chiếu bean của Spring

Biểu thức dùng cú pháp `@beanName` cần một `BeanResolver`. Khi tự tạo context bên ngoài cơ chế đánh giá biểu thức đã được Spring cấu hình, có thể nối context với `BeanFactory`:

```java
context.setBeanResolver(new BeanFactoryResolver(beanFactory));

Expression expression =
        parser.parseExpression("@pricingService.currentRate");

BigDecimal rate = expression.getValue(context, BigDecimal.class);
```

`BeanFactoryResolver` nằm trong package `org.springframework.context.expression`. Chỉ cấu hình resolver khi biểu thức thực sự cần truy cập bean; bean có thể mở rộng đáng kể các thao tác mà biểu thức thực hiện được.

### 3.4. TypeLocator: giải quyết kiểu trong T(...)

Type locator tìm lớp được chỉ định trong biểu thức như `T(java.time.Instant)`. Mặc định là `StandardTypeLocator`. Trong ứng dụng có class loader riêng, plugin hoặc môi trường chạy module, nên cấu hình class loader phù hợp:

```java
context.setTypeLocator(
        new StandardTypeLocator(applicationClassLoader));
```

Nếu không tìm thấy một lớp dù lớp đó có trong ứng dụng, hãy kiểm tra class loader mà type locator đang dùng trước khi thay đổi biểu thức.

### 3.5. TypeConverter: chuyển đổi kiểu dữ liệu

SpEL dùng `TypeConverter` để chuyển đổi giá trị trong quá trình đánh giá, chẳng hạn khi gán giá trị vào thuộc tính có kiểu cụ thể hoặc khi gọi `getValue()` với kiểu kết quả mong muốn. `StandardTypeConverter` tích hợp với Spring `ConversionService`, bao gồm các converter mặc định và converter do ứng dụng đăng ký.

Có thể đưa một `ConversionService` tùy chỉnh vào context:

```java
context.setTypeConverter(
        new StandardTypeConverter(conversionService));
```

Cơ chế chuyển đổi của Spring hiểu metadata generic. Ví dụ, khi gán một phần tử vào `List<Boolean>`, SpEL có thể chuyển chuỗi `"false"` thành `Boolean.FALSE` thay vì giữ nguyên chuỗi.

### 3.6. TypeComparator và OperatorOverloader

`TypeComparator` kiểm soát cách so sánh hai giá trị. Dùng `setTypeComparator()` khi kiểu miền nghiệp vụ cần quy tắc so sánh riêng.

`OperatorOverloader` cho phép bổ sung phép toán giữa các kiểu dữ liệu mà SpEL không hỗ trợ sẵn. Ví dụ, ứng dụng có thể định nghĩa cách cộng hai đối tượng tiền tệ hoặc thực hiện phép toán trên một kiểu số miền nghiệp vụ. Triển khai interface `OperatorOverloader` rồi đăng ký bằng `setOperatorOverloader()`.

Chỉ thay hai chiến lược này khi ngữ nghĩa phép so sánh hoặc phép toán mặc định không phù hợp với mô hình dữ liệu của ứng dụng.

### 3.7. Variables và functions

Biến được tham chiếu bằng cú pháp `#name`. Hàm được đăng ký từ một phương thức Java và gọi bằng cú pháp `#functionName(arguments)`. Phương thức dùng làm SpEL function phải là phương thức `static`.

```java
context.setVariable("taxRate", new BigDecimal("0.08"));

Method withTax = PricingFunctions.class.getMethod(
        "withTax", BigDecimal.class, BigDecimal.class);

context.registerFunction("withTax", withTax);

Expression expression =
        parser.parseExpression("#withTax(subtotal, #taxRate)");
```

Hàm có thể gom logic tính toán dùng chung vào một API có tên rõ ràng. Hãy chỉ đăng ký những hàm mà biểu thức cần gọi, vì mọi hàm đã đăng ký đều trở thành một phần khả năng mà biểu thức có thể truy cập.

### 3.8. IndexAccessor (Spring Framework 6.2 trở lên)

Từ Spring Framework 6.2, `IndexAccessor` cung cấp điểm mở rộng riêng cho thao tác truy cập theo chỉ số. Nó phù hợp với cấu trúc không phải array, collection hoặc map tiêu chuẩn, chẳng hạn cây JSON hay cấu trúc dữ liệu miền nghiệp vụ.

Một implementation xác định `canRead()`, `read()`, `canWrite()` và `write()`, sau đó được thêm bằng:

```java
context.addIndexAccessor(new JsonIndexAccessor());
```

Không dùng API này nếu dự án đang chạy Spring Framework trước 6.2. Cú pháp indexing của SpEL vẫn được giữ; accessor quyết định cách ánh xạ index vào cấu trúc đích.

## 4. Ví dụ hoàn chỉnh: root object, variable và function

Ví dụ sau tính tổng tiền sau thuế. Root object cung cấp `subtotal`, variable cung cấp thuế suất, còn function đóng gói phép tính:

```java
public class Order {
    private final BigDecimal subtotal;

    public Order(BigDecimal subtotal) {
        this.subtotal = subtotal;
    }

    public BigDecimal getSubtotal() {
        return subtotal;
    }
}

public final class PricingFunctions {
    private PricingFunctions() {
    }

    public static BigDecimal withTax(
            BigDecimal subtotal, BigDecimal taxRate) {
        return subtotal.multiply(BigDecimal.ONE.add(taxRate));
    }
}

// Phần cấu hình và đánh giá:
ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(new BigDecimal("100.00"));
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("taxRate", new BigDecimal("0.08"));
context.registerFunction(
        "withTax",
        PricingFunctions.class.getMethod(
                "withTax", BigDecimal.class, BigDecimal.class));

Expression totalExpression =
        parser.parseExpression("#withTax(subtotal, #taxRate)");

BigDecimal total =
        totalExpression.getValue(context, BigDecimal.class);

// total = 108.0000
```

Biểu thức kết hợp ba nguồn tham chiếu: `subtotal` lấy từ root object, `#taxRate` lấy từ variable và `#withTax(...)` gọi function đã đăng ký. Có thể thay function bằng method resolver hoặc bean resolver nếu logic cần phụ thuộc vào service của ứng dụng.

## 5. Phân biệt StandardEvaluationContext và SimpleEvaluationContext

| Tiêu chí | StandardEvaluationContext | SimpleEvaluationContext |
|---|---|---|
| Mục tiêu | Đánh giá SpEL đầy đủ tính năng. | Data binding và biểu thức cần giới hạn tính năng. |
| Root object | Có thể cấu hình trực tiếp. | Có thể cấu hình theo builder. |
| Reflection | Các chiến lược chuẩn dùng reflection để truy cập thuộc tính, phương thức và constructor. | Chọn rõ mức hỗ trợ thuộc tính/phương thức và accessor. |
| Type reference, constructor, bean reference | Có thể dùng khi chiến lược tương ứng được cấu hình. | Không hỗ trợ các tính năng này. |
| Mức tùy chỉnh | Cấu hình từng strategy của EvaluationContext. | Builder tập trung vào các khả năng cần bật. |

Chọn `StandardEvaluationContext` khi biểu thức đáng tin cậy cần truy cập đầy đủ SpEL hoặc cần thay đổi nhiều strategy. Chọn `SimpleEvaluationContext` khi bài toán chủ yếu là đọc/ghi dữ liệu và có thể giới hạn rõ các khả năng cần thiết. `SimpleEvaluationContext` chỉ thu hẹp tập tính năng; bản thân nó không phải ranh giới bảo mật tuyệt đối.

## 6. Bảo mật và vòng đời Expression

`StandardEvaluationContext` cho phép biểu thức gọi phương thức, tạo đối tượng, đọc/ghi thuộc tính và tham chiếu bean. Vì vậy, **không dùng StandardEvaluationContext để đánh giá biểu thức đến từ người dùng hoặc hệ thống bên ngoài không đáng tin cậy**. Biểu thức có thể truy cập các đối tượng mà root object, accessor, resolver, variable hoặc function làm lộ ra.

Ngay cả khi dùng `SimpleEvaluationContext`, cần kiểm soát các đối tượng có thể truy cập. Một phương thức không tham số trả về giá trị có thể bị xem như property getter; hình thức tên phương thức không đảm bảo nó không có side effect. Ví dụ, `Queue.poll()` làm thay đổi queue và `File.delete()` xóa file. Nên tạo DTO riêng, ưu tiên bất biến, chỉ phơi bày dữ liệu và thao tác thực sự cần thiết, đồng thời rà soát các đối tượng lồng nhau mà biểu thức có thể đi tới.

SpEL có thể cache accessor, method executor hoặc constructor executor đã giải quyết được trong AST của một `Expression`. Điều này giúp các lần đánh giá tiếp theo nhanh hơn, nhưng có hệ quả về bảo mật:

- Có thể parse một `Expression` một lần rồi đánh giá lặp lại với các root object hoặc context có cấu hình tương đương.
- Tránh thay đổi danh sách accessor/resolver giữa các lần đánh giá nếu không có lý do rõ ràng.
- Nếu cùng một chuỗi biểu thức được chạy với các quyền khác nhau, hãy parse thành các `Expression` riêng cho từng cấu hình quyền.
- Không đánh giá một `Expression` trước bằng context có quyền rộng rồi tái sử dụng chính instance đó trong context bị giới hạn hơn. AST có thể tái sử dụng strategy đã cache từ lần chạy trước.

Cần phân biệt cấu hình context với cấu hình parser. `StandardEvaluationContext` điều khiển việc giải quyết tham chiếu khi đánh giá; `SpelParserConfiguration` điều khiển hành vi parser như auto-grow collection, giới hạn biểu thức và chế độ compiler.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy property | Root object không đúng, tên property sai hoặc thiếu accessor phù hợp. | Kiểm tra root object, getter/field và danh sách property accessor. |
| Không gọi được method | Không có method resolver phù hợp hoặc chữ ký tham số không khớp. | Kiểm tra tên method, kiểu đối số và resolver đã đăng ký. |
| Không tạo được đối tượng bằng `new` | Constructor không phù hợp hoặc constructor resolver đã bị thay thế. | Kiểm tra constructor và danh sách constructor resolver. |
| `@beanName` không được giải quyết | Chưa cấu hình `BeanResolver`. | Đăng ký `BeanFactoryResolver` nếu cần truy cập bean từ context độc lập. |
| `T(MyType)` không tìm thấy lớp | Type locator dùng class loader không nhìn thấy lớp. | Cấu hình `StandardTypeLocator` với class loader của ứng dụng. |
| Gán giá trị sai kiểu | Converter hiện tại không hỗ trợ chuyển đổi mong muốn. | Đăng ký converter trong `ConversionService` rồi cấu hình `StandardTypeConverter`. |
| Accessor mặc định không còn hoạt động | Dùng `setPropertyAccessors()` để thay toàn bộ danh sách. | Bổ sung bằng `addPropertyAccessor()` hoặc đưa accessor mặc định trở lại danh sách. |
| Kết quả khác nhau giữa các context | Expression đã cache strategy từ một lần đánh giá trước. | Dùng Expression riêng khi các context có cấu hình hoặc quyền khác nhau. |

Khi debug, có thể kiểm tra `getRootObject()`, `getPropertyAccessors()`, `getMethodResolvers()`, `getConstructorResolvers()`, `getBeanResolver()`, `getTypeLocator()`, `getTypeConverter()`, `getTypeComparator()`, `getOperatorOverloader()` và `lookupVariable()`. Lỗi phân tích cú pháp thường phát sinh ở `parseExpression()`; lỗi khi giải quyết hoặc thực thi tham chiếu thường phát sinh ở `getValue()` hoặc `setValue()`.

## 8. Ghi nhớ

- `EvaluationContext` là môi trường giải quyết tham chiếu; `StandardEvaluationContext` là implementation đầy đủ và có thể cấu hình sâu.
- Root object phục vụ tham chiếu không có tiền tố; variable/function được gọi qua `#name`.
- Property, method, constructor, bean, type, conversion, comparison và operator đều có strategy tương ứng.
- Dùng `add...` để bổ sung; dùng `set...` khi chủ động thay toàn bộ danh sách strategy.
- `IndexAccessor` có từ Spring Framework 6.2.
- Chỉ đánh giá biểu thức tin cậy bằng `StandardEvaluationContext`; giới hạn cả những đối tượng mà biểu thức có thể truy cập.
- Tái sử dụng Expression với cấu hình quyền tương đương; tạo Expression riêng cho các miền quyền khác nhau.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [MapAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/MapAccessor.html)
- [IndexAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/IndexAccessor.html)
