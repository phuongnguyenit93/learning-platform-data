# Đọc annotation và dữ liệu cấu hình liên quan trong advice AOP

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, *advice* là hành vi bổ sung chạy tại các **join point** được *pointcut* lựa chọn. Ngoài tên phương thức, đối số, đối tượng đích và kết quả thực thi, advice có thể cần đọc **annotation** hoặc **dữ liệu cấu hình** để biết *tại sao điểm đó được áp dụng chính sách* và *phải áp dụng chính sách như thế nào*.

Ví dụ, nhiều phương thức nghiệp vụ đều cần audit, nhưng mỗi phương thức cần tên sự kiện hoặc mức ghi nhận khác nhau. Thay vì viết riêng logic audit ở từng phương thức, có thể dùng annotation để khai báo metadata:

```java
// Minh họa ý tưởng, chưa phải tệp Java độc lập.
@AuditEvent(name = "document.published", includeResult = false)
String publish(String documentId);
```

Một advice được kích hoạt tại phương thức phù hợp có thể đọc metadata này để xác định **tên sự kiện** và **có cho phép ghi thông tin kết quả hay không**. Đồng thời, một cấu hình riêng có thể bật/tắt audit ở một số thao tác, đặt giới hạn kích thước bản ghi hoặc chọn nơi xuất sự kiện.

**Mấu chốt:** Annotation là *metadata được khai báo trong mã*, cấu hình là *nguồn chính sách/giá trị bổ sung*, còn advice là *nơi sử dụng dữ liệu ấy để thực hiện hành vi*. Ba thứ liên quan nhưng không đồng nghĩa. Việc một annotation xuất hiện trên mã **không tự động** khiến advice chạy; cơ chế AOP vẫn phải có pointcut phù hợp, truy cập được metadata và thực sự áp dụng advice vào đường thực thi.

> Bài này nói về **AOP nói chung**, gồm kiến thức nền tảng và các giới hạn nâng cao trong Java. Java Reflection được dùng để giải thích cách đọc annotation, còn các quy tắc phối hợp annotation với cấu hình được xây dựng tường minh. Không có một ngôn ngữ pointcut, thứ tự ưu tiên cấu hình hay cơ chế tự đọc annotation nào là bắt buộc cho mọi công cụ AOP.

## 1. Annotation và cấu hình đóng vai trò gì trong advice?

Một aspect audit có thể cần bốn nhóm dữ liệu:

| Nhóm dữ liệu | Ví dụ | Vai trò |
| --- | --- | --- |
| **Metadata tĩnh của join point** | Phương thức `publish(String)`, kiểu khai báo | Xác định điểm được can thiệp |
| **Annotation trên code** | `@AuditEvent(name="document.published")` | Mô tả ý định/chính sách của API |
| **Cấu hình liên quan** | `audit.enabled=true`, danh sách thao tác loại trừ | Điều chỉnh chính sách mà không phải sửa logic audit |
| **Ngữ cảnh lượt gọi** | `documentId`, kết quả, exception, trace ID | Cung cấp dữ liệu động để advice xử lý |

Các nguồn có vòng đời khác nhau:

- Annotation thông thường gắn với class/method/parameter được biên dịch. Thay đổi metadata này thường cần thay code và build/reload thành phần tương ứng.
- Cấu hình có thể được nạp từ file, biến môi trường, kho cấu hình hoặc giá trị tạo lúc khởi động; khả năng cập nhật động là đặc tính triển khai, không tự có.
- Đối số/kết quả/ngoại lệ là dữ liệu **mỗi lần gọi**.
- Một số dữ liệu ngữ cảnh gắn với thread/task và không tự động lan qua các ranh giới bất đồng bộ.

**Đọc được annotation** không bảo đảm aspect đã **được kích hoạt**. **Đọc được cấu hình** không bảo đảm kết quả **an toàn nghiệp vụ**. Cả hai còn cần quy tắc chọn, thực thi và kiểm thử.

## 2. Phân biệt pointcut dùng annotation và advice đọc annotation

Có hai việc rất dễ lẫn:

**A. Chọn join point bằng annotation.** Một pointcut có thể biểu diễn ý tưởng “chỉ chọn những method được đánh dấu bởi annotation X”, nếu cơ chế AOP có khả năng matching annotation ở loại join point đó.

**B. Đọc giá trị annotation trong advice.** Sau khi lời gọi được chọn, advice đọc thuộc tính như `name`, `includeResult` hoặc `level` để biết cách xử lý.

```text
Source code
  @AuditEvent(name = "document.published")
  publish(String id)
       |
       +--> Pointcut: có chọn method này không?
                    |
                    +--> Advice: đọc name, includeResult ...
                                  |
                                  +--> Audit sink / metric / tracing
```

Một pointcut có thể chọn theo **tên/chữ ký phương thức** rồi advice tự đọc annotation như dữ liệu tùy chọn. Ngược lại, một pointcut dựa trên annotation có thể thực hiện việc chọn trước khi advice chạy. Cơ chế nào hiệu quả và chính xác phụ thuộc engine.

Nếu pointcut quá rộng mà advice tự kiểm tra annotation rồi bỏ qua thao tác, advice **vẫn có thể được gọi** trên mọi join point được chọn rộng đó, gây overhead và rủi ro. Nếu pointcut chọn bằng annotation nhưng advice lại tìm annotation ở một vị trí metadata khác, có thể xảy ra tình huống pointcut khớp còn advice đọc `null`.

### Ví dụ tình huống không đồng bộ về nơi tìm metadata

- Điểm gọi được viết qua một **interface method có annotation**.
- Implementation override method đó nhưng **không lặp lại annotation**.
- Engine cung cấp cho advice `Method` của implementation.
- Advice chỉ gọi `implementationMethod.getDeclaredAnnotation(...)`.

Khi đó advice có thể nhận `null` dù annotation có mặt trên interface method. Đây là vấn đề **quy tắc resolve metadata**, không phải bằng chứng annotation bị mất khỏi code nguồn.

## 3. Annotation Java thực sự là gì?

Annotation là metadata gắn vào phần tử của chương trình. Ta định nghĩa một annotation type bằng `@interface`:

```java
// Khai báo minh họa, được đặt ở phạm vi type thích hợp.
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface AuditEvent {
    String name();
    boolean includeResult() default false;
}
```

Đây là đoạn khai báo minh họa, **chưa có các import cho annotation API và chưa có main()**.

Các chi tiết quan trọng:

- `@Retention` quyết định annotation được giữ tới giai đoạn nào. `RUNTIME` cho phép Reflection đọc khi chương trình chạy.
- `@Target` quy định annotation có thể gắn ở đâu, chẳng hạn class, method, parameter, field hoặc type-use tùy khai báo.
- `name()` là phần tử bắt buộc: nơi dùng annotation phải cung cấp giá trị.
- `includeResult() default false` có giá trị mặc định nếu không khai báo tường minh.
- Annotation là **metadata**, không phải lời gọi hàm, interceptor hay việc đăng ký aspect.

Annotation element có những kiểu được Java cho phép như primitive, `String`, `Class`, enum, annotation và mảng của các kiểu hợp lệ; không thể khai báo phần tử annotation là một object nghiệp vụ tùy ý. Giá trị annotation được xác định theo cơ chế khai báo/biên dịch Java, không phải một biểu thức tùy ý được chạy theo từng invocation.

### `SOURCE`, `CLASS` và `RUNTIME`

| Retention | Đặc điểm chính | Reflection runtime thông thường đọc được? |
| --- | --- | --- |
| `SOURCE` | Metadata dành cho xử lý ở source | Không |
| `CLASS` | Ghi vào class file nhưng không yêu cầu JVM giữ để Reflection runtime truy xuất | Không theo Reflection runtime thông thường |
| `RUNTIME` | Được lưu để có thể truy xuất qua Reflection khi chạy | Có, tại phần tử được hỗ trợ |

**Lưu ý:** Một công cụ AOP áp dụng weaving lúc biên dịch hoặc phân tích bytecode có thể sử dụng metadata `CLASS` theo cách khác Reflection runtime. Vì vậy, câu hỏi “annotation có đọc được không?” phải đi kèm câu hỏi **“đọc bằng cơ chế nào, ở giai đoạn nào?”**.

## 4. Đọc annotation từ Method bằng Reflection

Java cung cấp `java.lang.reflect.Method` và các API annotation tương ứng:

```java
// Đoạn minh họa đặt trong nơi có biến Method method.
AuditEvent direct = method.getDeclaredAnnotation(AuditEvent.class);
AuditEvent visible = method.getAnnotation(AuditEvent.class);
Annotation[] allDirect = method.getDeclaredAnnotations();
```

Các API phục vụ mục tiêu khác nhau:

- `getDeclaredAnnotation(AuditEvent.class)`: lấy annotation được khai báo trực tiếp tại phần tử này, hoặc `null`.
- `getAnnotation(AuditEvent.class)`: tìm annotation theo semantics của API `AnnotatedElement`, chú ý quy tắc inherited annotation chỉ áp dụng ở những trường hợp Java quy định.
- `getDeclaredAnnotations()`: liệt kê annotation được khai báo trực tiếp.
- `getAnnotationsByType(...)`: hữu ích khi annotation được khai báo dạng **repeatable**, có semantics container/inheritance thích hợp.
- `getParameterAnnotations()`: cho biết annotation gắn với từng tham số hình thức của method.
- `getAnnotatedReturnType()`: API dành cho metadata annotation ở **type-use** của kiểu trả về, khác annotation đặt trực tiếp trên method.

Khi đã có instance annotation:

```java
if (direct != null) {
    String eventName = direct.name();
    boolean includeResult = direct.includeResult();
}
```

Đó là cách đọc **metadata**, chưa nói gì về việc advice chạy ở join point nào. Code sản xuất phải xác định xử lý thế nào nếu annotation vắng mặt hoặc trả giá trị không phù hợp chính sách.

### Method annotation khác parameter annotation

```java
// Ví dụ khái niệm, không phải tệp Java độc lập.
@AuditEvent(name = "document.saved")
void save(@Sensitive String secret, String publicId);
```

Annotation `@AuditEvent` nằm trên **method**; `@Sensitive` nằm trên **parameter**. Đọc bằng `method.getAnnotation(AuditEvent.class)` sẽ không tự đọc `@Sensitive`. Muốn hiểu tham số nào cần ẩn, phải đọc `method.getParameterAnnotations()` hoặc metadata khác theo đúng `@Target` và `@Retention`.

Tên biến tham số, metadata của annotation tham số và **giá trị đối số runtime** cũng là ba dữ liệu riêng. Việc tham số được đánh dấu nhạy cảm không có nghĩa advice được phép in giá trị của nó ra log.

## 5. Annotation trên interface và implementation

Trong AOP có proxy, lời gọi thường đi qua interface. Với Java Dynamic Proxy, `InvocationHandler` nhận một `Method` của interface proxy. Nhưng phần logic thực thi nằm trong **implementation object** có thể có annotation khác.

```java
// Mã minh họa, thiếu phần khai báo annotation.
interface DocumentApi {
    @AuditEvent(name = "api.publish")
    String publish(String id);
}

class DocumentService implements DocumentApi {
    @Override
    @AuditEvent(name = "service.publish")
    public String publish(String id) {
        return "done:" + id;
    }
}
```

Hai vị trí annotation có thể mang ý nghĩa khác nhau:

1. **Interface method:** metadata của contract API.
2. **Implementation method:** metadata của một implementation cụ thể.

Một advice nên lựa chọn quy tắc rõ ràng, ví dụ:

- Ưu tiên annotation trực tiếp trên **implementation method** nếu có.
- Nếu không có, sử dụng annotation trên **interface method**.
- Nếu cả hai không có, có thể xét annotation ở **class** hoặc cấu hình mặc định nếu đó là contract thiết kế.

Đây là **quy tắc do ứng dụng quyết định**, không phải “quy tắc ưu tiên annotation” được Java hoặc mọi engine AOP cung cấp sẵn. Các hệ thống có thể chọn interface làm nguồn chính để bảo vệ contract thay vì cho implementation override.

### Lấy implementation Method sao cho đúng

Nếu có `Method interfaceMethod` và `Object target`, một cách đơn giản đối với public method:

```java
Method implementationMethod = target.getClass().getMethod(
        interfaceMethod.getName(),
        interfaceMethod.getParameterTypes());
```

`getMethod(...)` tra cứu public method có tên và danh sách kiểu tham số phù hợp, bao gồm method public được kế thừa. Điều này thuận tiện cho interface proxy trong ví dụ đơn giản. Nhưng code tổng quát cần tính đến method không public, class ẩn, bridge, generic erasure, covariant return, module access và việc cùng signature xuất hiện ở nhiều cấp hierarchy.

**Không phải mọi implementation method đều có thể lấy bằng `getDeclaredMethod(...)` trên concrete class.** Một method có thể được kế thừa từ superclass; `getDeclaredMethod` chỉ xét method khai báo trực tiếp trên lớp được hỏi.

## 6. Annotation method có tự động được “kế thừa” khi override không?

**Không nên giả định annotation đặt trên method ở superclass/interface sẽ tự xuất hiện trên method override.**

Trong Java, `@Inherited` chỉ tạo cơ chế tìm kiếm kế thừa cho **annotation trên class**, theo quy tắc áp dụng với superclass, **không làm annotation trên method hay interface tự được kế thừa cho method override**.

Ví dụ:

```java
// Ví dụ minh họa:
class Parent {
    @AuditEvent(name = "parent.work")
    public void work() { }
}

class Child extends Parent {
    @Override
    public void work() { }
}
```

Dù `Parent.work` được đánh dấu, việc hỏi annotation trực tiếp trên `Child.work` có thể trả `null`. Một thư viện AOP có thể tự xây quy tắc tìm ngược method ở superclass hoặc interface; **đó là hành vi của resolver/tool**, không phải Java tự sao chép annotation vào override.

### Quy tắc với class-level annotation

Nếu annotation type được đánh dấu thêm `@Inherited` và được gắn vào một class cha, `Class.getAnnotation(...)` trên class con có thể nhìn thấy annotation đó khi class con không khai báo annotation tương ứng, theo quy tắc Java. Nhưng:

- Không áp dụng như vậy cho annotation ở method.
- Không tự lan từ annotation gắn trên interface sang implementing class qua cơ chế `@Inherited`.
- `getDeclaredAnnotation(...)` trên class con vẫn chỉ xét annotation **được khai báo trực tiếp**.
- Resolver tùy chỉnh có thể quyết định xử lý khác và phải có test cho lựa chọn đó.

**Kết luận:** Luôn xác định nơi metadata được gắn và nơi advice đọc nó. “Annotation tồn tại đâu đó trong hierarchy” không đồng nghĩa “Reflection tại method hiện tại tự trả về annotation”.

## 7. Annotation ở class, method, parameter và return type

Trong một hệ thống lớn, cùng một concern có thể có nhiều cấp:

| Nơi khai báo | Ý nghĩa ví dụ | Lưu ý |
| --- | --- | --- |
| **Class/type** | Mặc định audit cho mọi thao tác của service | Dễ quá rộng; nên có cơ chế loại trừ |
| **Method** | Tên event, cấp log, có ghi kết quả không | Chi tiết hơn nhưng có thể khác ở override |
| **Parameter** | Dữ liệu nào nhạy cảm, vai trò từng đối số | Metadata khác giá trị runtime |
| **Return type-use** | Ràng buộc dữ liệu đầu ra | Phải dùng đúng reflection API type-use |
| **Annotation lặp lại** | Nhiều policy trên cùng phần tử | Cần `@Repeatable` và API đọc thích hợp |

Ví dụ một class có mặc định và method override metadata:

```java
// Mã ý tưởng: giả định annotation type cho phép @Target(TYPE, METHOD).
@AuditEvent(name = "default.operation")
class ReportService {
    @AuditEvent(name = "report.export", includeResult = false)
    public String export(String id) {
        return "exported:" + id;
    }

    public String status() {
        return "READY";
    }
}
```

Một resolver có thể chọn **method-level override class-level**. Nhưng nếu yêu cầu là “các operation không có annotation không được audit”, thì **không nên tự động dùng class default**. Phải diễn tả policy mong muốn rõ ràng, thay vì suy ra từ vị trí annotation.

### Annotation vắng mặt là trường hợp bình thường

`getAnnotation(...)` có thể trả `null`. Advice cần quyết định:

- **Không áp dụng hành vi** nếu annotation thiếu.
- **Dùng default ở class**.
- **Dùng default từ cấu hình**.
- **Báo lỗi cấu hình** nếu metadata bắt buộc nhưng không có.

Không ép gọi `tag.name()` khi `tag == null`. Một lỗi `NullPointerException` từ advice có thể khiến nghiệp vụ thất bại dù target vốn không có lỗi.

## 8. Đọc dữ liệu cấu hình liên quan: nên nằm ở đâu?

Annotation thường tiện để thể hiện **ý định ổn định của API**, còn cấu hình phù hợp với những giá trị có thể thay đổi theo môi trường hoặc deployment, chẳng hạn:

- Bật/tắt một chính sách observability.
- Chọn sink hoặc phạm vi xuất log/audit.
- Ngưỡng kích thước event cho phép ghi.
- Danh sách operation được loại trừ.
- Quy tắc sampling metric/tracing.
- Mapping tên event sang một category do đơn vị vận hành quản lý.

Nhưng “cấu hình ngoài” không bắt buộc là đọc file trong mỗi advice. Có thể **nạp một snapshot cấu hình vào bộ nhớ**, cung cấp qua một service cấu hình, hoặc đọc từ môi trường tại một thời điểm được xác định.

### Đường dữ liệu mẫu

```text
Annotation trên method/class       Cấu hình ngoài
    |                                   |
    +------ metadata resolver           |
                    |                    |
                    +--- policy merger --+
                               |
                         ResolvedPolicy
                               |
                       Advice tại join point
                               |
                        Audit/metric/tracing
```

**Annotation reader** nên chịu trách nhiệm tìm metadata. **Configuration provider** chịu trách nhiệm cung cấp các giá trị được xác thực. **Policy resolver** chịu trách nhiệm ghép chúng và áp quy tắc ưu tiên. **Advice** sử dụng policy cuối để làm một hành vi có contract rõ ràng. Chia trách nhiệm như vậy giúp code kiểm thử được và tránh một interceptor phải tự biết mọi kiểu nguồn cấu hình.

## 9. Xác định thứ tự ưu tiên metadata và cấu hình

Không có thứ tự ưu tiên phổ quát. Một chính sách thiết kế có thể là:

1. **Cấu hình an toàn cấp toàn cục:** vô hiệu hóa một concern, giới hạn dữ liệu được phép ghi hoặc danh sách operation bị cấm ghi.
2. **Annotation trên implementation method:** điều chỉnh behavior cụ thể của implementation.
3. **Annotation trên interface method:** thể hiện API contract.
4. **Annotation trên class:** mặc định của một nhóm method.
5. **Default nội bộ:** hành vi rõ ràng khi không có nguồn nào đưa giá trị.

Trong một hệ thống khác, API contract có thể **không cho implementation override** một phần cấu hình bảo mật. Vì vậy thứ tự không chỉ là kỹ thuật; nó thể hiện quyền sở hữu chính sách.

### Ví dụ về conflict

```text
Interface method: @AuditEvent(name = "api.operation")
Implementation:   @AuditEvent(name = "impl.operation")
Class:            @AuditEvent(name = "class.default")
Config:           audit.enabled = false
```

Nếu cấu hình bật/tắt có quyền ưu tiên, advice **không ghi audit** bất kể annotation nêu tên event gì. Nếu enabled=true và method implementation có annotation, resolver có thể chọn `impl.operation`. Nhưng chính sách này là **lựa chọn thiết kế đã công bố**, không thể suy ra từ annotation Java.

### Không ghép bằng sự tình cờ

Tránh kiểu:

```java
// Pseudocode thể hiện một lựa chọn dễ mơ hồ.
String name = methodTag != null ? methodTag.name()
            : classTag != null ? classTag.name()
            : externalConfig.get("name");
```

Cần trả lời: `name=""` có nghĩa là “dùng giá trị mặc định” hay “tên event rỗng hợp lệ”? `null` biểu thị thiếu, lỗi đọc hay intentional disable? Một Boolean cấu hình `false` là false thật, không phải “không có cấu hình”. Thứ tự phải được diễn đạt thành một rule có test, không dựa vào truthiness hoặc chuỗi rỗng không được định nghĩa.

## 10. Ví dụ Java 17+ chạy được: advice đọc annotation và cấu hình

Ví dụ dưới đây dùng **Java Dynamic Proxy** như một cơ chế interception nhỏ. Nó kết hợp:

- Annotation `@AuditTag` trên **interface method**, **implementation method** và **implementation class**.
- Một cấu hình `Map<String,Boolean>` điều khiển enable/disable ở ranh giới method.
- Resolver có thứ tự: **implementation method → interface method → implementation class**.
- Advice đọc `value()` và `includeResult()` để quyết định thông tin audit.
- Nhánh thành công và lỗi, có truyền tiếp exception gốc.

Đây là **bài tập Java SE độc lập**, không phải triển khai một ngôn ngữ pointcut AOP hoàn chỉnh. Handler được gọi bởi proxy cho các lời gọi qua interface; việc chọn policy được thực hiện bên trong handler. Cơ chế AOP khác có thể lọc annotation ngay tại pointcut trước khi advice chạy.

Lưu toàn bộ thành tệp **`AnnotationAdviceDemo.java`** bằng UTF-8:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;

public class AnnotationAdviceDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ ElementType.TYPE, ElementType.METHOD })
    @interface AuditTag {
        String value();
        boolean includeResult() default false;
    }

    interface Operations {
        @AuditTag("api-publish")
        String publish(String id);

        @AuditTag("api-execute")
        String execute(String id);

        String status();

        String ping();
    }

    @AuditTag("class-default")
    static final class OperationsImpl implements Operations {
        @Override
        @AuditTag(value = "impl-publish", includeResult = true)
        public String publish(String id) {
            System.out.println("target publish " + id);
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("bad id");
            }
            return "PUB:" + id;
        }

        @Override
        public String execute(String id) {
            System.out.println("target execute " + id);
            return "EXEC:" + id;
        }

        @Override
        public String status() {
            System.out.println("target status");
            return "READY";
        }

        @Override
        public String ping() {
            System.out.println("target ping");
            return "PONG";
        }
    }

    static AuditTag resolveAnnotation(
            Method interfaceMethod, Object target) throws Exception {
        Method implementationMethod = target.getClass().getMethod(
                interfaceMethod.getName(),
                interfaceMethod.getParameterTypes()
        );

        AuditTag tag =
                implementationMethod.getDeclaredAnnotation(AuditTag.class);

        if (tag == null) {
            tag = interfaceMethod.getDeclaredAnnotation(AuditTag.class);
        }

        if (tag == null) {
            tag = target.getClass().getDeclaredAnnotation(AuditTag.class);
        }

        return tag;
    }

    static Object invoke(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Operations withAdvice(
            Operations target, Map<String, Boolean> enabledByMethod) {
        return (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] { Operations.class },
                (proxy, method, args) -> {
                    AuditTag tag = resolveAnnotation(method, target);

                    boolean enabled = enabledByMethod.getOrDefault(
                            method.getName(), true
                    );

                    if (!enabled || tag == null) {
                        return invoke(method, target, args);
                    }

                    System.out.println("[audit:before] " + tag.value());

                    try {
                        Object result = invoke(method, target, args);

                        String line = "[audit:after] " + tag.value();
                        if (tag.includeResult()) {
                            line += " result=" + result;
                        }

                        System.out.println(line);
                        return result;
                    } catch (Throwable error) {
                        System.out.println(
                                "[audit:error] " + tag.value() + " "
                                + error.getClass().getSimpleName()
                                + ":" + error.getMessage()
                        );
                        throw error;
                    }
                }
        );
    }

    public static void main(String[] args) {
        Operations target = new OperationsImpl();

        // Cấu hình tắt audit cho status, vẫn giữ nghiệp vụ hoạt động.
        Map<String, Boolean> config = Map.of("status", false);
        Operations service = withAdvice(target, config);

        System.out.println("caller " + service.publish("P-1"));
        System.out.println("caller " + service.execute("E-2"));
        System.out.println("caller " + service.status());
        System.out.println("caller " + service.ping());

        try {
            service.publish("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("caller error " + error.getMessage());
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 AnnotationAdviceDemo.java
java AnnotationAdviceDemo
```

**Standard output chính xác:**

```text
[audit:before] impl-publish
target publish P-1
[audit:after] impl-publish result=PUB:P-1
caller PUB:P-1
[audit:before] api-execute
target execute E-2
[audit:after] api-execute
caller EXEC:E-2
target status
caller READY
[audit:before] class-default
target ping
[audit:after] class-default
caller PONG
[audit:before] impl-publish
target publish bad
[audit:error] impl-publish IllegalArgumentException:bad id
caller error bad id
```

### 10.1. Tại sao `publish` chọn metadata ở implementation?

`publish(String)` được đánh dấu ở cả interface với `"api-publish"` và implementation với `"impl-publish"`. Resolver đọc annotation **trực tiếp trên implementation method trước** nên chọn `"impl-publish"`.

Giá trị `includeResult=true` của implementation khiến advice in `result=PUB:P-1` ở nhánh thành công. Khi `publish("bad")` ném ngoại lệ, advice in `[audit:error]` và chuyển tiếp lỗi gốc; không có dòng success giả.

### 10.2. Tại sao `execute` chọn annotation interface?

`OperationsImpl.execute` không có annotation method trực tiếp. Resolver chuyển sang `Operations.execute`, tìm `@AuditTag("api-execute")`. Vì `includeResult` không được khai báo ở annotation này, nó nhận **giá trị mặc định `false`** và advice không in kết quả.

Điểm này minh họa một vấn đề quan trọng: annotation trên **interface method** không tự được “kế thừa” vào implementation method; chính resolver trong ví dụ **chủ động tìm cả hai vị trí**.

### 10.3. Tại sao `status` không audit dù class có annotation?

`OperationsImpl` có annotation class-level `@AuditTag("class-default")`. Nhưng cấu hình `Map.of("status", false)` làm `enabled=false` nên handler **gọi target mà không xuất audit**.

Một annotation mô tả default không được phép “ghi đè” cấu hình tắt trong chính sách ví dụ này. `status()` vẫn chạy và trả `READY`.

### 10.4. Tại sao `ping` dùng class-level default?

`ping` không có annotation trên method implementation hoặc interface, nên resolver chọn annotation trên class. Cấu hình không có khóa `"ping"`, và `getOrDefault("ping", true)` cho phép audit. Advice in event `"class-default"`.

**Chú ý:** Việc class annotation mặc định áp dụng cho method không được đánh dấu là **quy tắc của resolver ví dụ**, không phải Java tự tạo annotation trên mọi method.

### 10.5. Vì sao phải gỡ `InvocationTargetException`?

`Method.invoke` có thể bọc ngoại lệ do target ném bằng `InvocationTargetException`. Hàm `invoke` của ví dụ lấy `getCause()` để advice và caller nhận đúng `IllegalArgumentException("bad id")` thay vì xử lý nhầm lỗi wrapper như lỗi nghiệp vụ mới.

### 10.6. Giới hạn cố ý của demo

- Cấu hình chỉ theo **tên phương thức**: nếu có overload cùng tên, chúng sẽ chia sẻ một cờ enable. Ứng dụng lớn cần key ổn định bao gồm type/signature hoặc policy identifier.
- Resolver dùng `getMethod(...)` cho **public method**; không giải quyết đầy đủ interface hierarchy, method bridge, visibility khác hoặc generic specialization.
- Cấu hình là `Map` bất biến dùng để minh họa, không có cơ chế reload động.
- Không có cache annotation; resolver dùng Reflection ở mỗi invocation.
- Không có annotation lặp, meta-annotation hoặc tham số được đánh dấu nhạy cảm.
- Dòng `includeResult=true` chỉ nên được dùng cho dữ liệu được phép ghi; ví dụ cố ý dùng chuỗi `PUB:P-1` không chứa bí mật.
- Handler chỉ nhận lời gọi **qua proxy**, không can thiệp lời gọi trực tiếp target hoặc self-invocation bên trong target.
- Sử dụng tên “audit” trong demo không biến stdout thành một hệ thống audit bất biến, bền vững hoặc chịu lỗi.

## 11. Giá trị mặc định và cấu hình bên ngoài là hai cấp default khác nhau

Có ít nhất ba kiểu default:

1. **Default của annotation element**, ví dụ `includeResult() default false`. Java dùng giá trị này khi annotation đã tồn tại nhưng phần tử đó bị lược bỏ.
2. **Default khi không có annotation**, do resolver của ứng dụng xác định.
3. **Default khi không có khóa cấu hình**, ví dụ `enabledByMethod.getOrDefault(name, true)`.

Chúng rất khác nhau. Nếu method **không có annotation**, không thể gọi `tag.includeResult()` để nhận `false`; trước hết resolver phải quyết định có tạo một policy mặc định hay không. Nếu cấu hình có khóa `false`, nó khác trường hợp khóa không tồn tại.

### Thiết kế “unset” rõ ràng

Một mô hình chính sách có thể phân biệt:

```text
ENABLED
DISABLED
UNSPECIFIED
```

`UNSPECIFIED` nghĩa là “chuyển sang cấp mặc định kế tiếp”, không đồng nghĩa `false`. Với các cờ có ảnh hưởng bảo mật, cách hợp nhất nên có **fail-closed semantics** nơi cần thiết, thay vì vô tình coi dữ liệu đọc lỗi như cờ cho phép.

Nếu cấu hình yêu cầu một số nguyên `maxRecordBytes`, phải kiểm tra `> 0`, giới hạn hợp lý và cách xử lý overflow. Annotation cho phép một số giá trị tại compile time nhưng không tự chứng minh giá trị đó hợp lệ với chính sách nghiệp vụ.

## 12. Annotation lặp lại và annotation gián tiếp

Một số bài toán cho phép nhiều policy trên cùng method. Java hỗ trợ **repeatable annotation** thông qua `@Repeatable(Container.class)`. Khi đó API `getAnnotationsByType(...)` thường là đường phù hợp để nhận các instance cùng type, thay vì tự giả định một `getAnnotation(...)` luôn thấy từng phần tử bên trong container.

Ví dụ ở mức ý tưởng:

```java
// Ký pháp minh họa ý định, giả định định nghĩa @Tag
// đã hỗ trợ @Repeatable và target phù hợp.
@Tag("metrics")
@Tag("audit")
void process();
```

Nếu advice cần cả hai tag, resolver phải xử lý chúng theo rule rõ: **AND hay OR**, thứ tự ưu tiên, có chấp nhận trùng tên không, xung đột xử lý thế nào. Không ngầm chọn phần tử đầu tiên chỉ vì thứ tự API trả về thuận tiện.

### Meta-annotation

Một annotation khác có thể được đánh dấu bởi một annotation mang ý nghĩa chính sách. Nhưng Java Reflection **không mặc nhiên diễn giải đệ quy mọi meta-annotation thành policy của method**. Nếu công cụ AOP cung cấp matching meta-annotation, phải biết chính xác ngữ nghĩa của nó; nếu tự xây resolver, cần tự duyệt annotation type và xác định giới hạn độ sâu, chu kỳ và ngoại lệ.

Đừng tự nhận mọi annotation “tương đương nhau” chỉ vì tên giống nhau hoặc có cùng một meta-annotation trong hierarchy.

## 13. Annotation ở constructor, field và parameter không giống method annotation

AOP có thể hỗ trợ nhiều loại join point, tùy engine:

- Method call/execution.
- Constructor call/execution hoặc initialization.
- Field read/write.
- Những điểm khác do công cụ hỗ trợ.

Nếu một annotation gắn với **field**, việc tìm `method.getAnnotation(...)` không truy ra field annotation. Nếu gắn với **constructor**, phải dùng reflection `Constructor`. Nếu gắn với **parameter**, phải đọc annotation của tham số theo đúng vị trí.

```java
// Minh họa annotation trên parameter:
void publish(@Sensitive String token, String publicId);
```

Advice muốn che token cần biết **parameter index**, kiểu và giá trị thực tế; chỉ biết tên method không đủ. Việc `@Sensitive` có mặt cũng không có nghĩa nên đọc hoặc ghi token vào audit; ngược lại, nó có thể là lý do phải **bỏ qua/ẩn dữ liệu**.

### Parameter name khác parameter annotation

Java Reflection có thể đọc tên tham số với điều kiện class file chứa metadata phù hợp, chẳng hạn khi biên dịch với `-parameters`. Tên tham số không có mặt hoặc bị biến đổi không làm parameter annotation tự mất đi; chúng là các loại metadata khác nhau. Một policy nghiêm ngặt nên ưu tiên index/type/annotation tường minh hơn suy luận ý nghĩa bảo mật chỉ từ tên `password` hay `token`.

## 14. Generic methods, bridge methods và overload: đọc đúng Method nào?

Một trong những khó khăn nâng cao của AOP annotation là **metadata method tại runtime không luôn trùng điều người đọc thấy trong source**.

### 14.1. Overload

```java
void save(String id);
void save(int id);
```

Hai method có cùng tên nhưng chữ ký khác nhau. Nếu dùng cấu hình chỉ theo key `"save"`, không phân biệt được chúng. Một cấu hình theo method nên cân nhắc **declaring type + name + ordered parameter types**, hoặc một identifier ổn định khai báo riêng.

### 14.2. Generics và type erasure

```java
interface Consumer<T> {
    void accept(T value);
}

class StringConsumer implements Consumer<String> {
    public void accept(String value) { }
}
```

Trong bytecode, compiler có thể sinh bridge method để bảo đảm overriding sau erasure. `getDeclaredMethods()` có thể nhìn thấy những method compiler sinh ra. API `Method.isBridge()` và `Method.isSynthetic()` hỗ trợ phân tích.

Một engine AOP có thể ánh xạ bridge method tới method người dùng hoặc áp dụng advice ở nhiều nơi; không có một kết luận phổ quát. Resolver tự viết cần tránh việc vô tình dùng annotation từ bridge method thay vì method nghiệp vụ tương ứng khi điều đó trái contract.

### 14.3. Covariant return

Override có thể trả subtype của kiểu trả về superclass. Java Reflection có thể cho thấy nhiều descriptor/bridge trong một số trường hợp. Nếu muốn resolve annotation trên implementation, cần hiểu method thực chạy và hierarchy thay vì chỉ chọn method đầu tiên có tên trùng.

### 14.4. ClassLoader và module boundary

Class và annotation cùng tên nhưng được nạp bởi class loader khác nhau không nhất thiết là cùng `Class<?>`. Reflection, proxy và truy cập method không public còn chịu giới hạn module/access. Nếu resolver không thể truy cập phần tử cần thiết, **không nên tự coi exception như “không có annotation”** mà im lặng bỏ qua một policy bắt buộc.

## 15. Cấu hình động, cache và việc làm mới policy

Reflection để đọc annotation thường có thể được tối ưu bằng cache theo `Method`, target class hoặc một khóa nhận diện chính xác. Nhưng dữ liệu trong cache phải phản ánh **semantics thực tế**.

### 15.1. Cái gì có thể cache?

- **Annotation metadata tĩnh:** thường phù hợp để cache theo cặp `(targetClass, methodSignature)` trong vòng đời class tương ứng.
- **Policy đã merge với cấu hình bất biến:** có thể cache cùng phiên bản cấu hình.
- **Giá trị của request hiện tại:** **không nên** cache chỉ theo method nếu giá trị thay đổi mỗi lượt gọi.
- **Trace ID/identity theo thread:** không nên cache vào một object interceptor dùng chung cho nhiều request.

### 15.2. Invalidating cache khi cấu hình thay đổi

Nếu cấu hình cho phép reload, `ResolvedPolicy` cũ có thể không còn chính xác. Một thiết kế có thể:

1. Nạp và validate **snapshot bất biến** của cấu hình.
2. Gắn số phiên bản/generation cho snapshot.
3. Tính policy theo annotation và **snapshot hiện tại**.
4. Cache kết quả theo **method + target type + config version**, hoặc bỏ cache merge và đọc cấu hình đã được chuẩn bị.
5. Khi thay config, thay snapshot một cách nguyên tử/nhất quán, không sửa nhiều giá trị rời rạc giữa những invocation.

Một lời gọi có thể bắt đầu khi phiên bản cấu hình A còn hiệu lực và kết thúc khi B đã được công bố. Hệ thống phải định nghĩa **snapshot tại đầu invocation** hay tra lại từng bước. Nếu audit cần tính nhất quán, dùng một policy snapshot cho toàn bộ lượt gọi thường dễ hiểu hơn.

### 15.3. Thread safety của cache

Một aspect/interceptor có thể được dùng đồng thời bởi nhiều thread. Map mutable không đồng bộ chứa kết quả resolve có thể gây race nếu được cập nhật không an toàn. Sử dụng cache thread-safe hoặc khởi tạo snapshot bất biến; tránh giữ `currentMethod`, `currentAnnotation` hoặc `currentRequestId` trong trường instance dùng chung để “giảm chi phí tra cứu”.

### 15.4. Chi phí lớn không phải chỉ từ Reflection

Ngay cả khi metadata được cache, log, serialize result, đọc cấu hình từ mạng hoặc phân tích object graph trong mỗi lời gọi vẫn có thể rất tốn kém. Chỉ đưa thông tin cần thiết vào audit; đo overhead thật trong đường chạy tần suất cao, không suy đoán mọi reflection đều là nút thắt hiệu năng.

## 16. Bảo mật: annotation không biến policy thành quyền truy cập

Annotation có thể gắn nhãn một phương thức là “được audit” hoặc “chứa dữ liệu nhạy cảm”. Nhưng nếu cơ chế AOP chỉ áp dụng advice ở đường gọi qua proxy, **đường gọi trực tiếp target hoặc self-invocation có thể bỏ qua** logic ấy.

Điều này đặc biệt nguy hiểm nếu một annotation được dùng như **bằng chứng ủy quyền duy nhất**. Nguyên tắc:

- **Chính sách bắt buộc** phải được thực thi tại ranh giới không thể bỏ qua đối với các đường thao tác liên quan.
- Annotation là metadata để **mô tả**, không tự kiểm tra danh tính hoặc quyền.
- External config là dữ liệu đầu vào cần được **xác thực về tính toàn vẹn và nguồn đáng tin cậy**.
- Không tin giá trị config/annotation chỉ vì nó có dạng đúng. Một cờ “allowAll” sai nơi là lỗi bảo mật dù kiểu Boolean hợp lệ.
- Không dùng metadata nằm trong nguồn bên ngoài chưa xác thực như thể nó là annotation đáng tin của code đã được kiểm soát.

### Lưu kết quả có thể tiết lộ dữ liệu

Annotation như `includeResult=true` chỉ thể hiện ý định. Trước khi in hoặc lưu kết quả, advice phải xét:

- Return value có chứa mật khẩu, token, PII hoặc dữ liệu kinh doanh nhạy cảm không?
- Có cần ẩn, rút gọn hoặc chỉ lấy mã trạng thái không?
- Kết quả là object mutable có `toString()` chứa dữ liệu không mong muốn không?
- Việc gọi `toString()` có side effect, chậm hoặc ném lỗi không?
- Audit sink có yêu cầu độ bền, idempotency hay quy tắc redaction đặc biệt không?

**Một annotation cho phép log không chứng minh dữ liệu có thể công bố**. Nên ưu tiên dữ liệu được phép ghi rõ ràng và hạn chế log toàn bộ object.

## 17. Nếu annotation hoặc cấu hình đọc không được, advice nên làm gì?

Câu trả lời phụ thuộc vào mức độ quan trọng của concern.

**Với logging/metric phụ trợ**, có thể áp dụng fallback được xác định từ trước, bỏ qua một trường không bắt buộc hoặc ghi lỗi quan sát một cách kiểm soát để nghiệp vụ tiếp tục. Cũng cần tránh vòng lặp khi chính hệ thống logging bị lỗi.

**Với policy bắt buộc**, việc “không đọc được metadata” có thể là lý do **từ chối thao tác** theo nguyên tắc fail-closed, hoặc từ chối khởi động ứng dụng. Không nên lén dùng default cho phép tất cả nếu config bị thiếu, sai định dạng hoặc lỗi truy cập.

Các trạng thái phải phân biệt:

| Tình huống | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Annotation không có | Có thể là bình thường | Theo policy default |
| Annotation có nhưng phần tử dùng default | Metadata hợp lệ | Dùng default đã khai báo |
| Cấu hình không có khóa | Không được chỉ định tại cấp này | Dùng precedence/fallback định nghĩa |
| Cấu hình có `false` | Một giá trị tường minh | Không được coi là missing |
| Cấu hình sai kiểu/sai miền | Lỗi cấu hình | Validate, báo lỗi rõ |
| Reflection không có quyền truy cập | Hạn chế runtime/module | Không đồng nhất với thiếu annotation |
| Nguồn cấu hình tạm thời không khả dụng | Lỗi hạ tầng | Áp dụng chính sách retry/fallback/fail-closed được công bố |
| Metadata mâu thuẫn | Không rõ quyền ưu tiên | Giải quyết bằng rule hoặc báo lỗi |

### Lỗi từ advice có thể che lỗi target

Nếu advice đang xử lý exception target mà bản thân việc đọc cấu hình/serialize error lại ném exception khác, caller có thể thấy lỗi advice thay cho lỗi nghiệp vụ. Hãy thiết kế ranh giới xử lý lỗi phụ đúng mức độ quan trọng. Với audit bắt buộc, lỗi audit có thể cần làm thao tác thất bại; với metric phụ trợ, có thể cần cô lập lỗi. **Quyết định phải tường minh**, không dựa vào một `catch (Exception)` nuốt mọi lỗi.

## 18. Annotation và dữ liệu cấu hình có thể được đọc ở thời điểm nào?

Trong một hệ thống AOP, việc đọc metadata/cấu hình có thể xảy ra:

- **Khi khởi tạo aspect:** đọc một snapshot chung.
- **Khi resolver được yêu cầu lần đầu:** resolve method, cache kết quả.
- **Mỗi lần invocation:** đọc metadata và ngữ cảnh mới.
- **Khi cấu hình reload:** tính lại policy.
- **Khi class được load/weave:** phân tích annotation trong bytecode.
- **Khi build:** chọn những điểm có annotation rồi đưa advice vào artifact.

Mỗi thời điểm có trade-off. **Chọn tĩnh tại build/load** có thể giảm chi phí lookup runtime, nhưng không tự hỗ trợ đổi annotation không rebuild. **Chọn động tại invocation** linh hoạt nhưng cần quản lý hiệu năng và tính nhất quán của cấu hình.

Một annotation `RUNTIME` cho phép Reflection đọc khi chương trình chạy; nó **không bắt buộc engine phải đọc mỗi invocation**. Tương tự, external config có thể là một snapshot khởi động thay vì giá trị thay đổi tức thì.

## 19. Context propagation và async: annotation không mất, ngữ cảnh có thể mất

Annotation trên method là metadata của mã; đổi thread không tự xóa annotation. Nhưng advice còn có thể kết hợp nó với dữ liệu **theo request** như trace ID hoặc user context, vốn có thể gắn vào thread.

Nếu method `publish` được chạy qua executor:

- Annotation của `publish` có thể được resolve như trước.
- `ThreadLocal` của caller **không tự truyền** sang worker.
- Config snapshot có thể là chung hoặc thay đổi giữa lúc submit và execute.
- Nếu advice đọc config/trace tại **execution** thay vì lúc **submit**, nó có thể thấy dữ liệu khác.
- Một callback xử lý future có thể chạy trên thread khác và cần propagation riêng.

Điều này cho thấy **metadata tĩnh**, **runtime config snapshot** và **context mỗi invocation** cần được quản lý như ba lớp khác nhau. Không nên cache cả chúng thành một “policy” theo method rồi dùng lại vô hạn.

## 20. Multi-aspect composition và precedence

Giả sử có `AuditAspect`, `TimingAspect` và `AccessAspect`. Mỗi aspect có thể đọc annotation khác nhau hoặc chia sẻ một metadata resolver. Khi cùng khớp một join point, thứ tự advice có thể quyết định:

- Audit nhìn thấy input ban đầu hay input đã được around advice chuẩn hóa?
- Timing có bao gồm thời gian đọc cấu hình và ghi audit không?
- AccessAspect chặn trước khi AuditAspect bắt đầu hay AuditAspect ghi cả yêu cầu bị từ chối?
- Một around bên ngoài recover lỗi thì AuditAspect ở bên trong quan sát outcome gì?

**Pointcut** quyết định những điểm được chọn; **precedence** quyết định thứ tự các advice. Annotation chứa `priority=...` có thể là một nguồn cấu hình cho ordering nếu công cụ/ứng dụng định nghĩa như vậy, nhưng nó **không tự tạo một thứ tự chạy** trong mọi engine AOP.

### Tránh resolver phụ thuộc vòng tròn

Nếu đọc config của AuditAspect lại kích hoạt một method đang bị AuditAspect chọn, có thể xuất hiện vòng gọi đệ quy. Hãy tách hạ tầng metadata/config khỏi tập join point của chính aspect khi cần, hoặc áp dụng guard có semantics đúng. Đừng dựa vào một flag toàn cục mutable thiếu thread safety để “tắt đệ quy”.

## 21. Thiết kế một metadata resolver có thể kiểm thử

Một resolver tốt thường có hợp đồng rõ:

```text
Input:
    - join point kind / method metadata
    - target type
    - current config snapshot

Output:
    - resolved policy (hoặc no-policy / validation error)
```

Điều cần ghi trong tài liệu thiết kế:

1. Loại join point nào được hỗ trợ: call, execution, proxy invocation?
2. Có lấy annotation từ interface, implementation, superclass, class default không?
3. Thứ tự ưu tiên các nguồn là gì?
4. Có xử lý override, inherited methods, default methods và bridge methods không?
5. Khi annotation missing, dùng fallback hay bỏ qua?
6. Cấu hình có thể disable annotation không? Có thể tăng quyền/chính sách được không?
7. Config key có phân biệt overload không?
8. Khi reload cấu hình, cache được invalidated thế nào?
9. Dữ liệu request/thread có bao giờ bị cache nhầm cùng metadata tĩnh không?
10. Nếu lỗi đọc metadata hoặc config, fail-open hay fail-closed theo concern nào?
11. Cấu hình và annotation có chứa thông tin nhạy cảm không?
12. Làm sao quan sát được policy cuối mà **không log dữ liệu bí mật**?

Có thể biểu diễn kết quả resolve bằng một **record bất biến** trong Java để tránh cập nhật nửa chừng:

```java
// Java 17+, minh họa dạng dữ liệu, chưa là tệp chạy độc lập.
record ResolvedAuditPolicy(
        boolean enabled,
        String eventName,
        boolean includeResult
) { }
```

Thay vì để advice tự đọc ba nguồn ở nhiều thời điểm khác nhau, resolver tạo một policy nhất quán cho invocation. Điều này cũng làm unit test dễ hơn: input xác định thì output xác định.

## 22. Ma trận kiểm thử cần có

| Trường hợp | Kết quả/thuộc tính cần xác minh |
| --- | --- |
| Annotation nằm trên implementation method | Resolver chọn đúng giá trị và precedence |
| Annotation chỉ nằm trên interface method | Resolver không bỏ lọt metadata hợp lệ |
| Annotation chỉ nằm trên class | Default được áp dụng hoặc bỏ qua đúng contract |
| Method có annotation khác class | Có chọn đúng cấp ưu tiên không? |
| Method không có annotation ở đâu | Không ném NPE; fallback đúng |
| Annotation thiếu một phần tử có default | Đọc đúng giá trị mặc định |
| Cấu hình có `false` | Thực sự disable, không coi như missing |
| Cấu hình không có khóa | Dùng default được tài liệu hóa |
| Config sai kiểu/ngoài miền | Báo lỗi hoặc áp fallback đúng chính sách |
| Hai overload cùng tên | Config key có đủ thông tin phân biệt không? |
| Inherited/overridden method | Đọc đúng method/interface/superclass |
| Repeatable annotation | Đọc đủ các giá trị bằng API thích hợp |
| Generic bridge method | Không đọc nhầm hoặc áp advice trùng ngoài ý muốn |
| Target throw | Advice ghi đúng nhánh error và truyền lỗi theo contract |
| Call trực tiếp target | Kiểm chứng giới hạn proxy/weaving |
| Cấu hình reload | Có cập nhật cache và policy nhất quán không? |
| Nhiều thread | Không lẫn ngữ cảnh hoặc policy snapshot |
| Async callback | Metadata đúng; request context không bị giả định tự truyền |
| Annotation đánh dấu dữ liệu nhạy cảm | Không ghi lộ nội dung bị cấm |
| Lỗi Audit sink | Có tuân thủ contract thành công/thất bại không? |

### Ba mức kiểm thử

- **Unit test resolver:** Với metadata và cấu hình giả lập, xác minh trường hợp ưu tiên, vắng mặt, lỗi và default.
- **Integration test AOP:** Gọi qua cơ chế interception/weaving thực tế, xác nhận advice có chạy đúng đường và đúng dữ liệu.
- **Contract test nghiệp vụ:** Kết quả/exception của target phải được bảo toàn hoặc biến đổi đúng chính sách, không có side effect phát sinh do đọc metadata.

Chỉ unit test `getAnnotation(...) != null` là **chưa đủ** để chứng minh pointcut chọn đúng hoặc advice có quyền can thiệp trên mọi đường thực thi.

## 23. Các lỗi thường gặp

1. **Tưởng có annotation là advice tự chạy.** Vẫn cần pointcut và cơ chế AOP áp dụng đúng join point.
2. **Đọc annotation ở implementation trong khi annotation chỉ nằm trên interface.** Có thể nhận `null` dù metadata tồn tại.
3. **Tin `@Inherited` tự áp dụng cho method/interface.** Quy tắc kế thừa Java không hoạt động như vậy.
4. **Không dùng `@Retention(RUNTIME)` nhưng lại đòi Reflection runtime đọc.** Kết quả có thể không có annotation.
5. **Đọc method annotation thay vì parameter annotation.** Metadata có thể nằm ở phần tử khác.
6. **Coi annotation element default là default khi không có annotation.** Đây là hai trường hợp khác.
7. **Không phân biệt config `false` và key không tồn tại.** Dễ bật chính sách ngoài ý muốn.
8. **Ưu tiên annotation và config không nhất quán.** Hai implementation có thể xử lý xung đột khác nhau.
9. **Dùng config key chỉ là tên method.** Overload có thể bị gộp ngoài ý định.
10. **Bỏ qua bridge/generic/inherited method.** Reflection có thể phản ánh metadata khác code nguồn.
11. **Cache policy gộp cả request context.** Dữ liệu request cũ có thể rò sang request mới.
12. **Đọc file/mạng trong mọi advice trên đường nóng.** Gây overhead, timeout hoặc làm lỗi nghiệp vụ.
13. **Coi không đọc được config như cho phép tất cả.** Rất rủi ro với policy bắt buộc.
14. **Log toàn bộ result vì `includeResult=true`.** Có thể lộ thông tin nhạy cảm.
15. **Cho rằng proxy bao phủ direct call/self-invocation.** Chúng có thể bypass advice.
16. **Tưởng config thay đổi sẽ tức thì cập nhật cache.** Phải thiết kế invalidation/snapshot.
17. **Nhầm metadata từ caller với target runtime.** Interface/call/implementation có thể dẫn đến các Method khác nhau.
18. **Gán annotation là tính năng riêng của một công cụ.** Đây là Java metadata; cách AOP dùng nó phụ thuộc engine.

## 24. Bài tập thực hành

1. Chạy `AnnotationAdviceDemo.java` và giải thích lý do `publish` chọn `"impl-publish"`, `execute` chọn `"api-execute"`, còn `ping` chọn `"class-default"`.
2. Xóa annotation khỏi `OperationsImpl.publish`. Dự đoán tên audit nào được chọn và điều kiện `includeResult` thay đổi ra sao.
3. Đổi cấu hình thành `Map.of("status", true, "ping", false)`. Dự đoán chính xác những dòng audit xuất hiện/biến mất.
4. Bỏ annotation khỏi cả implementation và interface của `execute`. Resolver có tìm class default không? Nếu yêu cầu chỉ audit method được đánh dấu, cần sửa rule thế nào?
5. Thêm hai overload `publish(String)` và `publish(int)`, rồi giải thích vì sao cấu hình chỉ key theo tên method không phân biệt được chúng.
6. Chuyển annotation class-level từ implementation sang interface type. Resolver dùng `target.getClass().getDeclaredAnnotation(...)` còn thấy annotation không? Cần thêm nhánh nào nếu muốn hỗ trợ interface type annotation?
7. Thêm annotation trên superclass method và override method ở subclass không khai báo annotation. Dùng Reflection quan sát `getDeclaredAnnotation` của hai method.
8. Dùng `@Inherited` trên một annotation type có `@Target(TYPE)`; kiểm tra behavior của `Class.getAnnotation` trên subclass so với một implementation của interface.
9. Thêm phần tử `String[] tags() default {};` vào annotation và đọc nó trong advice. Xác định cách xử lý khi mảng trống.
10. Thiết kế một `ResolvedAuditPolicy` bất biến và unit test precedence giữa config disable, implementation, interface, class default.
11. Xây cache theo `Method` và target type, rồi thiết kế cách làm mới khi config version tăng. Vì sao không cache một trace ID theo method?
12. Thêm annotation parameter đánh dấu dữ liệu nhạy cảm; kiểm tra vị trí tham số bằng `getParameterAnnotations()` và tạo log đã che dữ liệu.
13. Mô phỏng cấu hình sai kiểu, thiếu khóa và `false` tường minh; phân biệt ba kết quả policy.
14. Cho target ném ngoại lệ, xác nhận advice không ghi success giả và không mất Throwable gốc.
15. Gọi trực tiếp `target.publish(...)` ngoài proxy và mô tả vì sao handler không có log.
16. Lập bảng test ít nhất năm ca *metadata phải được dùng* và năm ca *không nên dùng*, gồm interface, override, inherited, generic/bridge và disable config.

**Tự kiểm tra:** Vì sao annotation có `RUNTIME` vẫn chưa đủ để advice chạy? Annotation trên interface method có mặc nhiên xuất hiện ở implementation method không? `@Inherited` có giúp kế thừa annotation method không? `getDeclaredAnnotation` khác `getAnnotation` ở trường hợp nào? Vì sao cấu hình `false` không phải “không có cấu hình”? Khi nào cần cache policy, và cache key nào an toàn khi cùng method xử lý nhiều request?

## Kết luận

**Advice có thể dùng annotation và cấu hình để ra quyết định chính sách nhất quán, nhưng phải đọc đúng nguồn metadata và đúng thời điểm.** Annotation trên interface, implementation, class, parameter hay type-use là những dữ liệu khác nhau; Java retention, inheritance, Reflection và generic/bridge method quyết định cách truy xuất. Cấu hình bổ sung quyền điều chỉnh nhưng phải có **thứ tự ưu tiên, default, validation và lifecycle** rõ ràng. Một thiết kế vững thường tách **metadata resolver**, **configuration provider**, **policy merging** và **advice**, kiểm thử cả metadata lẫn đường interception thật, quản lý cache/reload, đồng thời bảo vệ dữ liệu nhạy cảm và các chính sách bắt buộc ở ranh giới đáng tin cậy.