
# Thay đổi enum, annotation và metadata được công cụ bên ngoài đọc

Trong một hệ thống Java, API không chỉ là những class và method được gọi trực tiếp từ mã nguồn. Nhiều thành phần còn được **đọc như dữ liệu**: tên hằng số enum được gửi qua JSON, annotation được framework quét bằng reflection, thông tin generic được công cụ sinh mã phân tích, hoặc các attribute trong class file được plugin, serializer và bộ tạo schema sử dụng.

Vì vậy, một thay đổi tưởng như nhỏ—đổi tên enum constant, thêm phần tử annotation, chuyển retention policy, xóa metadata khi đóng gói JAR—có thể làm consumer gặp lỗi dù dự án chính vẫn biên dịch và chạy các unit test thông thường. Trong bối cảnh **Java Advance Compatibility Migration**, cần đánh giá không chỉ source và binary compatibility mà cả **tính tương thích của dữ liệu, reflection, schema và công cụ bên ngoài**.

Bài học này cung cấp cách phân loại thay đổi, ví dụ Java cụ thể và quy trình xác minh khi tiến hóa API có enum, annotation và metadata.

## 1. API được sử dụng bằng cách gọi và API được đọc như dữ liệu

Hãy xét bốn dạng consumer:

1. **Consumer mã nguồn**: một module import class, gọi method, so sánh enum constant và được biên dịch lại khi nâng dependency.
2. **Consumer nhị phân**: một JAR đã biên dịch từ phiên bản cũ, chạy với phiên bản thư viện mới mà không compile lại.
3. **Consumer runtime động**: framework dùng reflection, classpath scanning, annotation processing, service loading hoặc class loader để khám phá kiểu và metadata.
4. **Consumer bên ngoài JVM**: hệ thống khác nhận JSON, database lưu giá trị enum, bộ tạo OpenAPI/JSON Schema hay một chương trình đọc class file.

Những consumer này không có cùng tiêu chí tương thích.

| Loại hợp đồng | Dữ liệu mà consumer phụ thuộc | Thay đổi có thể gây sự cố |
|---|---|---|
| Source API | Tên class, enum constant, method và annotation element | Đổi tên constant hoặc thay signature |
| Binary API | Symbolic reference, descriptor và field trong class file | Xóa enum constant mà bytecode cũ vẫn tham chiếu |
| Runtime reflection | Annotation, retention, target, tên và giá trị phần tử | Chuyển RUNTIME sang CLASS hoặc đổi annotation element |
| Dữ liệu lưu trữ | Tên, ordinal hoặc mã đại diện enum | Sắp xếp lại enum khi database lưu ordinal |
| Hợp đồng giao tiếp | JSON value, schema enum, payload message | Đổi giá trị JSON hoặc thêm enum value chưa được consumer hỗ trợ |
| Metadata của công cụ | Signature, MethodParameters, annotation attributes, service files | Shading/minification loại bỏ metadata cần thiết |

**Điểm mấu chốt:** “Build thành công” chỉ chứng minh một tập ràng buộc ở thời điểm build. Nó không xác minh mọi consumer runtime, database hay dịch vụ tích hợp.

~~~mermaid
flowchart TD
    A["Thay đổi API Java"] --> B["Source và binary consumer"]
    A --> C["Reflection / framework"]
    A --> D["Dữ liệu và giao thức"]
    A --> E["Class file / JAR metadata"]
    B --> F["Đánh giá tương thích đa lớp"]
    C --> F
    D --> F
    E --> F
    F --> G["Migration và kiểm thử phù hợp"]
~~~

## 2. Enum mang nhiều hợp đồng hơn danh sách hằng số

Enum Java là một kiểu tham chiếu với tập instance được khai báo trước, có thể có field, constructor, method, interface và logic riêng theo từng constant.

Ví dụ:

~~~java
public enum PaymentStatus {
    CREATED,
    AUTHORIZED,
    SETTLED,
    FAILED
}
~~~

Consumer có thể dùng enum theo nhiều cách:

~~~java
PaymentStatus status = PaymentStatus.AUTHORIZED;

String name = status.name();
int position = status.ordinal();

PaymentStatus parsed = PaymentStatus.valueOf("AUTHORIZED");

for (PaymentStatus candidate : PaymentStatus.values()) {
    System.out.println(candidate);
}
~~~

Mỗi cách tạo một điểm phụ thuộc khác nhau:

- **Truy cập trực tiếp** `PaymentStatus.AUTHORIZED` phụ thuộc field enum constant có tên tương ứng.
- **`name()` và `valueOf()`** phụ thuộc tên khai báo, phân biệt chữ hoa/chữ thường.
- **`ordinal()`** phụ thuộc vị trí khai báo, bắt đầu từ 0.
- **`values()`** trả về các constant theo thứ tự khai báo.
- **`toString()`** có thể bị override nên không nhất thiết bằng `name()`.
- **`switch`** phụ thuộc tập case và chiến lược xử lý giá trị chưa biết.
- **Serializer, ORM, code generator** có thể chọn tên, vị trí hoặc metadata khác làm dạng biểu diễn.

Do đó, khi chỉnh sửa enum phải hỏi: **ai đang đọc enum này và họ đọc thuộc tính nào?**

### 2.1. Tên constant là một hợp đồng

Ví dụ đổi:

~~~java
enum PaymentStatus {
    CREATED, AUTHORIZED, SETTLED
}
~~~

thành:

~~~java
enum PaymentStatus {
    CREATED, APPROVED, SETTLED
}
~~~

Nếu consumer cũ gọi `PaymentStatus.AUTHORIZED`, nó có thể không compile khi xây dựng lại. Nếu bytecode cũ vẫn tham chiếu đến field bị xóa, JVM có thể phát sinh `NoSuchFieldError`.

Một hệ thống nhận chuỗi `"AUTHORIZED"` rồi gọi `PaymentStatus.valueOf(...)` sẽ nhận `IllegalArgumentException` khi constant đó không còn.

Đổi tên một enum constant không phải “chỉnh sửa label” đơn thuần; nó có thể phá vỡ cả **binary API** lẫn **wire/data contract**.

### 2.2. `ordinal()` không phải ID bền vững

Với enum:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}
~~~

các ordinal lần lượt là 0, 1, 2. Nếu thêm `URGENT` vào đầu:

~~~java
enum Priority {
    URGENT, LOW, MEDIUM, HIGH
}
~~~

ordinal cũ đều bị dịch. Database lưu `0` với ý nghĩa LOW sẽ có thể bị hiểu thành URGENT khi dùng phiên bản mới.

Điều này nguy hiểm với:

- ORM lưu enum theo ordinal.
- Cache hoặc message payload lưu giá trị số của `ordinal()`.
- Mảng, bitmask, mapping hoặc file cấu hình dùng index làm ý nghĩa nghiệp vụ.
- Bộ tạo schema coi vị trí khai báo là số định danh.

**Không dùng ordinal làm mã lưu trữ hoặc mã giao tiếp bền vững.** Ordinal chủ yếu phục vụ cấu trúc bên trong theo thứ tự khai báo.

### 2.3. `name()` ổn định hơn ordinal nhưng vẫn là hợp đồng đổi tên

Khi serializer lưu tên constant, thêm hoặc sắp xếp lại các constant không làm tên cũ đổi. Tuy nhiên, đổi tên vẫn phá vỡ dữ liệu lưu trước đó.

Ví dụ một bảng chứa `"AUTHORIZED"`. Nếu Java enum được đổi thành `APPROVED`, mapper chỉ biết tên mới có thể không đọc được bản ghi cũ.

Bởi vậy, dùng `EnumType.STRING` trong ORM thường an toàn hơn lưu ordinal khi cần chèn hoặc sắp xếp lại enum, nhưng vẫn cần migration khi **đổi tên** constant. “Dùng STRING” không thay thế kế hoạch tương thích dữ liệu.

### 2.4. `toString()` có thể phục vụ hiển thị, không nhất thiết là key

~~~java
enum PaymentStatus {
    CREATED, AUTHORIZED;

    @Override
    public String toString() {
        return this == CREATED ? "Chờ xử lý" : "Đã xác thực";
    }
}
~~~

`name()` luôn phản ánh tên khai báo; `toString()` ở đây trả về chuỗi hiển thị có thể thay đổi theo ngôn ngữ hoặc yêu cầu UX. Nếu một hệ thống dùng `toString()` để ghi dữ liệu bền vững, việc đổi văn bản hiển thị sẽ trở thành breaking change.

Nên tách **mã máy đọc** khỏi **nhãn người dùng**.

## 3. Ma trận thay đổi enum và rủi ro

| Thay đổi | Source/binary consumer | Dữ liệu hoặc công cụ bên ngoài |
|---|---|---|
| Thêm constant mới | Thường giữ reference cũ; có thể phá vỡ logic giả định tập enum cố định | Consumer cũ có thể không đọc được giá trị mới; schema cần cập nhật |
| Xóa constant | Source cũ lỗi; bytecode cũ có thể gặp `NoSuchFieldError` | Tên cũ trong DB/JSON không còn parse được |
| Đổi tên constant | Gần như tương đương xóa tên cũ và thêm tên mới | Cần alias hoặc migration dữ liệu |
| Đổi thứ tự constant | Các reference theo tên thường còn | `ordinal()`, thứ tự UI và mapping theo index thay đổi |
| Thêm field/method vào enum | Thường không làm mất member cũ | Reflection/scanner có thể nhìn thấy metadata mới |
| Đổi mã wire riêng của constant | Không nhất thiết đổi binary API | Là breaking change với consumer dùng mã đó |
| Đổi annotation trên constant | Không nhất thiết đổi descriptor của enum | Serializer, ORM hoặc schema generator có thể đổi kết quả |
| Đổi logic `toString()` | Bytecode vẫn gọi được method | Log, serialization tùy chỉnh hoặc UI có thể đổi |
| Đổi constructor nội bộ của enum | Consumer ngoài thường không gọi constructor trực tiếp | Công cụ bytecode/reflection có thể phụ thuộc cấu trúc implementation |

Cách đánh giá cần dựa trên **đường sử dụng** chứ không chỉ kiểu thay đổi.

### 3.1. Thêm enum constant không luôn là thay đổi vô hại

Giả sử phiên bản cũ:

~~~java
enum JobState {
    NEW, RUNNING, DONE
}
~~~

Consumer có `switch` bao phủ cả ba constant. Phiên bản mới thêm `CANCELLED`.

Một consumer có `switch statement` kèm `default` có thể xử lý giá trị mới theo nhánh mặc định. Nhưng mã nguồn dùng **switch expression** không có `default` thường dựa trên tính đầy đủ của tập enum khi compile; chạy bytecode cũ với một constant mới có thể gặp lỗi runtime khi không có nhánh phù hợp. Loại exception cụ thể có thể phụ thuộc phiên bản Java và cách compiler sinh bytecode (ví dụ `IncompatibleClassChangeError` hoặc `MatchException`).

Ngay cả khi không lỗi kỹ thuật, logic vẫn có thể sai:

~~~java
switch (state) {
    case NEW:
        enqueue();
        break;
    case RUNNING:
        monitor();
        break;
    case DONE:
        archive();
        break;
    default:
        archive(); // CANCELLED có thực sự nên archive?
}
~~~

Nhánh `default` ngăn một số lỗi nhưng không đảm bảo ngữ nghĩa đúng. Khi mở rộng enum được public API, cần kiểm tra tất cả consumer dùng `switch`, mapping, whitelist và validation.

### 3.2. Đổi enum constant có thân class riêng

Enum constant có thể override method:

~~~java
enum Transport {
    ROAD {
        @Override
        int capacity() { return 100; }
    },
    AIR {
        @Override
        int capacity() { return 1000; }
    };

    abstract int capacity();
}
~~~

Compiler có thể tạo class phụ cho constant có thân riêng. Công cụ quét class file có thể nhìn thấy các class này, nhưng tên và cấu trúc class sinh là chi tiết triển khai. Consumer không nên phụ thuộc tên synthetic subclass hoặc thứ tự class trong JAR.

## 4. Thiết kế mã enum ổn định cho dữ liệu và giao thức

Khi enum được lưu vào DB, cache, event hay API response, nên khai báo một mã ổn định do ứng dụng kiểm soát.

~~~java
import java.util.Arrays;
import java.util.Optional;

public enum OrderState {
    CREATED("created"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderState(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static Optional<OrderState> fromCode(String input) {
        if (input == null) {
            return Optional.empty();
        }
        return Arrays.stream(values())
                .filter(value -> value.code.equals(input))
                .findFirst();
    }
}
~~~

Điểm thiết kế:

- `code` không phụ thuộc thứ tự khai báo.
- Mã được cam kết duy trì khi tên constant thay đổi vì lý do nội bộ.
- `fromCode` cho phép xử lý giá trị không được nhận diện thay vì ném lỗi mù.
- Có thể thêm alias trong giai đoạn migration, nhưng cần quy định cách ghi ra mã mới và cách đọc mã cũ.
- Mã phải có quy tắc không trùng và được mô tả trong schema/tài liệu API.

Không tự động dùng `UNKNOWN` cho mọi dữ liệu lạ nếu logic nghiệp vụ cần phân biệt lỗi dữ liệu với trường hợp mới hợp lệ. Có thể dùng `Optional.empty()`, một kiểu kết quả phân biệt known/unknown hoặc luồng xử lý riêng.

### 4.1. Chiến lược đọc cũ, ghi mới

Giả sử dữ liệu cũ lưu `"authorized"` nhưng mã mới muốn dùng `"approved"`. Một chiến lược chuyển tiếp là:

1. Trong phiên bản chuyển tiếp, **đọc được cả hai mã**.
2. Khi ghi mới, luôn ghi `"approved"`.
3. Thống kê dữ liệu và request còn dùng mã cũ.
4. Migrate dữ liệu trong DB và các message tồn đọng nếu cần.
5. Chỉ bỏ alias sau khi xác minh mọi consumer và dữ liệu cũ đã chuyển đổi.

Ví dụ:

~~~java
public static Optional<OrderState> fromCode(String input) {
    if ("authorized".equals(input) || "approved".equals(input)) {
        return Optional.of(PAID);
    }
    return Arrays.stream(values())
            .filter(value -> value.code.equals(input))
            .findFirst();
}
~~~

Đây là ví dụ minh họa; tên trạng thái phải phản ánh đúng nghiệp vụ thực tế. Không hợp nhất hai trạng thái khác nghĩa chỉ để tránh lỗi parse.

### 4.2. JSON, ORM và schema

Với JSON, serializer có thể mặc định xuất tên enum, nhưng thư viện và cấu hình khác nhau có thể dùng `toString()`, annotation, custom serializer hoặc mã số. Cần xác định chính xác **representation đang được phát hành**.

Với JPA/Hibernate, cần đọc cách enum được mapping:

- `EnumType.STRING`: thường lưu tên enum.
- `EnumType.ORDINAL`: lưu vị trí số.
- `AttributeConverter` hoặc mapping tùy chỉnh: có thể lưu mã ổn định.

Với OpenAPI/JSON Schema, thêm enum value có thể khiến schema mới hợp lệ nhưng client generated từ schema cũ không nhận diện được. Cần kiểm tra chiến lược xử lý unknown enum của từng client. Với giao thức dùng mã số (như protobuf), mã số là hợp đồng riêng, không phải Java ordinal.

### 4.3. Java serialization

Cơ chế serialization chuẩn của Java xử lý enum theo tên constant, không coi thứ tự ordinal là định danh được lưu. Vì vậy, thêm hoặc sắp xếp lại constant khác với xóa/đổi tên trong bối cảnh serialization chuẩn.

Tuy nhiên, nhiều ứng dụng không dùng Java Object Serialization mà dùng JSON, database hoặc binary protocol riêng. Không áp dụng quy tắc của Java Serialization một cách máy móc cho những định dạng khác.

## 5. Annotation cũng là API có consumer riêng

Annotation Java có thể cung cấp metadata cho framework, compiler và công cụ bên ngoài.

Ví dụ một annotation công khai:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface EndpointRole {
    String value();
    boolean audited() default true;
}
~~~

Consumer có thể:

- Đọc `EndpointRole` bằng reflection.
- Quét class file bằng ASM mà không nạp class.
- Dùng annotation processor để sinh source.
- Dùng plugin build để sinh tài liệu hoặc code.
- Dùng framework runtime để đăng ký route, quyền hoặc dependency.
- Dùng schema generator để xuất API contract.

Nếu thay annotation mà chỉ chạy unit test logic nghiệp vụ, rất dễ bỏ sót tác động đến những consumer trên.

### 5.1. Annotation element là method đặc biệt

Khai báo:

~~~java
public @interface EndpointRole {
    String value();
    boolean audited() default true;
}
~~~

định nghĩa các element `value` và `audited`. Ở mức class file, chúng tương ứng với method của annotation interface.

Giá trị mặc định được lưu như metadata của khai báo annotation, không nhất thiết được ghi lại trên từng vị trí sử dụng.

Ví dụ:

~~~java
@EndpointRole("admin")
public class AdminEndpoint {
}
~~~

Annotation này không chỉ rõ `audited`. Khi đọc metadata, consumer thường nhận giá trị mặc định `true` từ annotation definition.

Nếu thư viện đổi default thành `false`, mã nguồn sử dụng annotation không thay đổi, nhưng hành vi runtime hoặc output của công cụ có thể thay đổi. Đó là một **behavioral change** dù không cần sửa từng nơi gắn annotation.

### 5.2. Annotation trên enum constant nằm ở field tương ứng

Ví dụ:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ExternalCode {
    String value();
}

enum DeliveryState {
    @ExternalCode("queued")
    QUEUED,

    @ExternalCode("dispatched")
    DISPATCHED
}
~~~

Một công cụ Java Reflection đọc annotation của constant qua field:

~~~java
import java.lang.reflect.Field;

public class DeliveryMetadata {
    public static String externalCode(DeliveryState state)
            throws NoSuchFieldException {
        Field field = DeliveryState.class.getField(state.name());
        ExternalCode annotation = field.getAnnotation(ExternalCode.class);
        return annotation != null ? annotation.value() : state.name();
    }
}
~~~

Không nên nhầm metadata của **field enum constant** với annotation ở cấp **class enum**. Thay đổi `@Target` hoặc xóa `@ExternalCode` khỏi constant có thể làm serializer/schema generator đổi kết quả dù enum constant vẫn còn và code gọi tên constant vẫn chạy.

## 6. Retention, target và các meta-annotation quan trọng

### 6.1. Retention quyết định ai đọc được annotation

Ba giá trị của `RetentionPolicy`:

| Retention | Metadata tồn tại ở đâu? | Consumer thường dùng |
|---|---|---|
| SOURCE | Source; không được giữ trong class file | Compiler plugin, annotation processor đọc source |
| CLASS | Được lưu trong class file nhưng không được Java Reflection expose như runtime annotation | ASM, class-file scanner, build tool |
| RUNTIME | Lưu trong class file và có thể đọc bằng reflection ở runtime | Framework DI, ORM, web/security framework |

Nếu không khai báo `@Retention`, annotation mặc định có `RetentionPolicy.CLASS`.

Ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Audit {
    String action();
}
~~~

Nếu đổi retention từ RUNTIME sang CLASS:

- Class file vẫn có thể chứa annotation theo dạng runtime-invisible.
- `Method.getAnnotation(Audit.class)` sẽ không còn thấy annotation đó.
- Framework phụ thuộc reflection có thể ngừng đăng ký hoặc áp dụng logic audit.
- Một công cụ quét class file trực tiếp vẫn có thể thấy annotation, tùy cách nó đọc metadata.

Nếu đổi CLASS sang SOURCE, annotation không còn trong class file; class-file scanner cũng không thể tìm nó trong artifact đã biên dịch.

**Không đánh giá retention chỉ bằng việc build có thành công hay không.** Hãy kiểm chứng đúng cơ chế đọc mà consumer đang dùng.

### 6.2. Target thay đổi phạm vi sử dụng hợp lệ

`@Target` quy định annotation có thể áp dụng ở đâu:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface ExportedApi {
}
~~~

Ví dụ thay TARGET từ `TYPE` sang `METHOD` có thể khiến source cũ gắn annotation trên class không còn compile được. Source của consumer không đổi nhưng annotation definition đã thay hợp đồng.

Các target đáng chú ý gồm `TYPE`, `FIELD`, `METHOD`, `PARAMETER`, `CONSTRUCTOR`, `TYPE_USE`, `TYPE_PARAMETER`, `RECORD_COMPONENT` và `ANNOTATION_TYPE`, tùy phiên bản Java.

Với annotation trên type use, metadata có thể nằm trong `RuntimeVisibleTypeAnnotations` hoặc `RuntimeInvisibleTypeAnnotations`. Công cụ chỉ đọc annotation thông thường có thể bỏ sót type-use annotations.

### 6.3. Inherited không có nghĩa được kế thừa khắp nơi

`@Inherited` chủ yếu ảnh hưởng đến việc tra cứu annotation trên **class** qua `Class.getAnnotation` khi annotation type mang meta-annotation này. Nó không tự làm annotation của method, field hoặc interface được kế thừa theo cùng cách.

Ví dụ:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Tracked {
}
~~~

Framework nào tự đi qua hierarchy hoặc interface có thể có cách quét khác reflection mặc định. Khi đổi `@Inherited`, phải kiểm tra cơ chế tra cứu thực tế của framework.

### 6.4. Repeatable annotation và container

Với `@Repeatable`, một annotation có thể xuất hiện nhiều lần:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
~~~

Consumer dùng `getAnnotationsByType(Role.class)` có thể nhận các annotation lặp, trong khi code chỉ gọi `getAnnotation(Role.class)` có hành vi khác khi annotation được đóng trong container. Khi chuyển annotation từ non-repeatable sang repeatable, phải kiểm tra:

- Container annotation type và tên element `value`.
- Retention và target của annotation và container.
- Cách framework đọc trực tiếp, đọc container hoặc gọi `getAnnotationsByType`.
- Dữ liệu đã biên dịch từ phiên bản cũ.
- Công cụ quét class file có nhận diện đúng container hay không.

### 6.5. Documented và metadata phục vụ tài liệu

`@Documented` ảnh hưởng đến cách annotation được đưa vào tài liệu Javadoc, chứ không trực tiếp cấp chức năng runtime. Tuy vậy, công cụ sinh tài liệu/API catalog có thể dựa trên kết quả đó, nên thay đổi vẫn cần được xem xét khi tài liệu là đầu ra được tích hợp bên ngoài.

## 7. Tiến hóa annotation element và khả năng tương thích

Annotation element có các kiểu giá trị cho phép như primitive, String, Class, enum, annotation khác hoặc mảng một chiều của những kiểu đó. Chúng có thể có default value.

### 7.1. Thêm element có default thường thuận lợi hơn

Phiên bản 1:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Route {
    String path();
}
~~~

Phiên bản 2 thêm element:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Route {
    String path();
    boolean secure() default true;
}
~~~

Các nơi sử dụng cũ chưa có `secure` có thể tiếp tục đọc được nhờ default. Tuy nhiên, default mới còn ảnh hưởng hành vi runtime—ví dụ mọi route cũ trở thành secure—nên vẫn cần review nghiệp vụ.

### 7.2. Thêm element không có default có thể làm annotation cũ thiếu giá trị

Phiên bản 2:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Route {
    String path();
    String owner(); // Không có default
}
~~~

Consumer source dùng `@Route(path = "/users")` phải cung cấp `owner` khi compile lại. Class file đã biên dịch bằng annotation version cũ có thể vẫn chứa annotation instance thiếu element này; khi framework đọc `owner()`, có thể phát sinh `IncompleteAnnotationException`.

Cách chuyển tiếp thường an toàn hơn:

1. Thêm element với default phù hợp.
2. Cập nhật các annotation usage sang giá trị tường minh.
3. Kiểm tra các artifact cũ và công cụ đọc annotation.
4. Chỉ cân nhắc bỏ default hoặc bắt buộc mới trong một breaking release đã công bố.

### 7.3. Đổi tên hoặc xóa element

Ví dụ đổi `path()` thành `value()`:

~~~java
// Cũ
String path();

// Mới
String value();
~~~

Source annotation usage cũ cần sửa. Bytecode consumer đã biên dịch gọi accessor `path()` có thể gặp lỗi liên kết nếu method này không còn. Metadata annotation được biên dịch trước đó cũng có thể chứa element tên `path` mà annotation type mới không còn định nghĩa.

Nếu muốn chuyển tiếp, giữ element cũ (có thể deprecate), thêm element mới và quy định rõ trường nào được ưu tiên. Không nên xóa trong một minor release nếu đã cam kết binary compatibility.

### 7.4. Đổi kiểu element

Ví dụ:

~~~java
// Cũ
String timeout();

// Mới
long timeout();
~~~

Đây không chỉ là đổi cách viết metadata. Descriptor method của annotation thay đổi, các usage cũ có dạng giá trị khác và code reader cũ có thể không liên kết hoặc không diễn giải được.

Khi kiểu giá trị lưu trong annotation khác với kiểu mà definition mới kỳ vọng, có thể gặp `AnnotationTypeMismatchException` lúc đọc element. Các lỗi khác phụ thuộc chính xác vào thay đổi và cơ chế đọc.

Với enum-valued annotation:

~~~java
public @interface Retry {
    RetryMode mode() default RetryMode.NORMAL;
}
~~~

nếu một constant `RetryMode.NORMAL` bị xóa nhưng metadata cũ vẫn nhắc đến nó, quá trình đọc element có thể gặp `EnumConstantNotPresentException`. Nếu class được nhắc trong metadata không còn tồn tại, có thể gặp `TypeNotPresentException`.

**Đừng dự đoán chỉ một exception duy nhất cho mọi thay đổi annotation.** Cần kiểm tra bytecode thực tế và điểm reader truy cập metadata.

### 7.5. Đổi default là thay đổi hành vi

Ví dụ:

~~~java
public @interface Retry {
    int attempts() default 3;
}
~~~

đổi thành:

~~~java
public @interface Retry {
    int attempts() default 5;
}
~~~

Các usage ghi rõ `attempts = 3` không bị đổi giá trị, nhưng usage bỏ qua element có thể nhận giá trị mới khi reader dùng annotation definition mới. Không có compile error bắt buộc, song hệ thống có thể chạy nhiều lần hơn, thay đổi latency hoặc load.

Với API annotation được dùng trong production, default value cũng là **hợp đồng công khai**.

## 8. Class-file metadata mà công cụ bên ngoài đọc

Một số công cụ không chạy ứng dụng mà đọc file `.class`, `.jar` hoặc bytecode. Vì vậy, metadata có thể bị ảnh hưởng ngay ở bước biên dịch, shading, obfuscation hoặc packaging.

| Metadata/attribute | Thông tin | Consumer tiêu biểu |
|---|---|---|
| `RuntimeVisibleAnnotations` | Annotation runtime trên class/member | Reflection, framework runtime |
| `RuntimeInvisibleAnnotations` | Annotation có trong class file nhưng không visible bằng core reflection | Scanner ASM, plugin |
| `RuntimeVisibleTypeAnnotations` | Annotation trên vị trí type use | Phân tích nullability, static/runtime tooling |
| `Signature` | Generic type information | Java Reflection generic API, IDE, serializer |
| `MethodParameters` | Tên và cờ của tham số | DI, binding, reflection |
| `AnnotationDefault` | Default value của annotation element | Annotation reader |
| `Record` | Thành phần record | Reflection, serializer, schema generator |
| `PermittedSubclasses` | Các subclass được phép của sealed class | Compiler, runtime/tooling |
| `InnerClasses` và `EnclosingMethod` | Quan hệ class lồng nhau | Reflection/tooling |
| `NestHost` và `NestMembers` | Nest membership | JVM và bytecode tools |
| `Module` trong `module-info.class` | Thông tin JPMS module | Module resolver và analyzer |

Danh sách này không bao quát mọi attribute. Ý nghĩa và sự hiện diện phụ thuộc phiên bản JDK, kiểu class và cờ compiler.

### 8.1. Generic Signature khác method descriptor

Ví dụ:

~~~java
public List<String> names() {
    return List.of();
}
~~~

Method descriptor ở JVM có thể là:

~~~text
()Ljava/util/List;
~~~

Generic argument `String` không nằm trong descriptor nhưng có thể được lưu ở `Signature` attribute. Nếu công cụ đóng gói loại bỏ `Signature`, JVM vẫn có thể gọi method, nhưng framework dùng `getGenericReturnType()` hoặc công cụ sinh schema có thể mất thông tin `List<String>`.

Vì vậy, “bytecode vẫn chạy” không đủ để chứng minh metadata consumer không bị ảnh hưởng.

### 8.2. Tên tham số có thể là dữ liệu đầu vào của framework

Ví dụ:

~~~java
public User findUser(long userId) {
    return repository.find(userId);
}
~~~

Một framework web có thể dùng tên tham số `userId` khi binding request, nhưng class file không bắt buộc luôn có tên đó. Khi cần phản chiếu tên tham số bằng `java.lang.reflect.Parameter`, Java compiler thường cần bật `-parameters` để phát sinh metadata thích hợp.

Ví dụ:

~~~bash
javac -parameters -d out src/com/example/UserController.java
~~~

Nếu refactor build bỏ cờ `-parameters`, method descriptor vẫn giữ `(J)Lcom/example/User;`, nhưng framework dựa vào tên tham số có thể không còn binding đúng.

Chú ý: một số framework có cơ chế thay thế như annotation tường minh, Kotlin metadata hoặc debug information; không được giả định tất cả đều cần cùng một cờ.

### 8.3. Record, sealed và phiên bản class file

Record và sealed class có metadata/attribute phù hợp để JVM, reflection và compiler hiểu cấu trúc kiểu. Công cụ đọc bytecode cũ có thể không hiểu class file version hoặc attribute mới. Một migration JDK có thể yêu cầu nâng ASM/Byte Buddy hoặc công cụ tương tự, ngay cả khi mã nghiệp vụ không đổi.

Đây là **tool compatibility** riêng với source và runtime compatibility.

### 8.4. Metadata bên ngoài class file

Một artifact Java còn có metadata ở cấp JAR và build:

- `META-INF/MANIFEST.MF`: Main-Class, Multi-Release và các entry khác.
- `META-INF/services/...`: cấu hình `ServiceLoader`.
- `module-info.class`: thông tin requires/exports/opens/provides của JPMS.
- Tệp cấu hình reflection/resource/proxy cho native-image, nếu dự án dùng.
- Metadata riêng của thư viện hoặc ngôn ngữ, ví dụ annotation Kotlin metadata.
- Metadata đóng gói, schema, descriptor của framework hoặc annotation processor output.

Đổi tên implementation class mà không cập nhật `META-INF/services` có thể khiến `ServiceLoader` không nạp được provider. Shading đổi package class nhưng bỏ quên file service là lỗi thường gặp; code compile không đảm bảo plugin discovery hoạt động.

### 8.5. Obfuscation, shading và minimization

Các bước build có thể:

- Đổi tên class, method hoặc field.
- Loại bỏ annotation hoặc class-file attribute.
- Hợp nhất hoặc làm mất service files.
- Loại các class chỉ được nạp động vì công cụ tưởng chúng không được tham chiếu.
- Thay đổi manifest hoặc module descriptor.
- Đóng gói nhiều phiên bản metadata không nhất quán.

Cần cấu hình keep rules và transformation rules dựa trên các consumer thực tế, rồi xác minh **artifact cuối cùng**, không chỉ output trước đóng gói.

## 9. Cùng một thay đổi có thể khác nhau ở từng loại tương thích

### 9.1. Ví dụ: đổi thứ tự enum

~~~java
// Trước
enum Phase { START, PROCESS, FINISH }

// Sau
enum Phase { FINISH, START, PROCESS }
~~~

Các lời gọi tới `Phase.START` và `Phase.name()` vẫn có thể hoạt động. Tuy nhiên:

- Ordinal thay đổi.
- Thứ tự `values()` thay đổi.
- UI chọn giá trị theo thứ tự khai báo có thể khác.
- Dữ liệu persist theo ordinal bị giải nghĩa sai.
- Test/snapshot phụ thuộc thứ tự có thể thất bại.

Đây là ví dụ thay đổi **không nhất thiết phá binary linkage**, nhưng vẫn phá **data/behavioral compatibility**.

### 9.2. Ví dụ: đổi retention

~~~java
// Cũ
@Retention(RetentionPolicy.RUNTIME)
@interface Track {}

// Mới
@Retention(RetentionPolicy.CLASS)
@interface Track {}
~~~

Mã được biên dịch có thể vẫn tham chiếu tới annotation type. Nhưng `getAnnotation(Track.class)` có thể trả về `null`; framework đăng ký handler bằng reflection có thể ngừng hoạt động. Class-file scanner chuyên dụng có thể vẫn thấy metadata.

Đây là ví dụ thay đổi **metadata visibility contract**.

### 9.3. Ví dụ: đổi default annotation element

~~~java
@interface Export {
    boolean enabled() default true;
}
~~~

Đổi default sang `false` có thể khiến các class dùng `@Export` mà không ghi element không còn được xuất, dù không có lỗi compiler hoặc linker.

Đây là ví dụ thay đổi **behavioral contract**.

### 9.4. Ví dụ: xóa enum constant mà annotation vẫn tham chiếu

~~~java
enum RetryMode { FAST, NORMAL, SAFE }

@interface RetryPolicy {
    RetryMode value();
}

@RetryPolicy(RetryMode.SAFE)
class Task {}
~~~

Nếu phiên bản mới xóa `SAFE` nhưng vẫn có artifact annotation cũ, framework có thể gặp lỗi khi đọc metadata. Trong khi đó, code không trực tiếp gọi `RetryMode.SAFE` có thể compile mà vẫn gặp lỗi khi scan class.

Đây là lý do cần kiểm tra **artifact đã biên dịch cũ** và toàn bộ classpath, không chỉ source hiện tại.

## 10. Khảo sát consumer thực tế

Để đánh giá thay đổi, lập bản đồ các điểm mà enum/annotation/metadata được sử dụng.

### 10.1. Tìm trong source

Các gợi ý tìm kiếm:

~~~bash
rg -n "enum |@interface |@Retention|@Target|@Repeatable|@Inherited" src
rg -n "name\(\)|ordinal\(\)|valueOf\(|values\(\)" src
rg -n "EnumType\.ORDINAL|EnumType\.STRING|AttributeConverter" src
rg -n "getAnnotation|getAnnotationsByType|getDeclaredAnnotations" src
rg -n "getGenericType|getGenericReturnType|getParameters" src
rg -n "ServiceLoader|META-INF/services|module-info" .
~~~

Các lệnh trên chỉ là mẫu; thay đường dẫn theo cấu trúc dự án. Khi đọc kết quả, phân biệt code sản phẩm, test, build logic và generated source.

Tìm kiếm chuỗi không phát hiện mọi hành vi vì một thư viện có thể đọc metadata nội bộ. Vì vậy, cần kiểm tra dependency và tài liệu framework mà ứng dụng đang dùng.

### 10.2. Xem class file đã phát hành

Các lệnh hữu ích:

~~~bash
jar tf library.jar
javap -classpath library.jar -v -p com.example.OrderState
javap -classpath library.jar -v -p com.example.EndpointRole
~~~

Kết quả `javap -v` có thể cho thấy:

- Enum constants như field, metadata và flags.
- Method của annotation type.
- `AnnotationDefault`.
- Runtime-visible/runtime-invisible annotations.
- `Signature` và `MethodParameters`.
- Record hoặc module metadata khi có.

Nếu ứng dụng dùng executable JAR chứa nested JAR, công cụ có thể cần trích xuất dependency hoặc chỉ định classpath đúng. Không nên kết luận “không có annotation” nếu công cụ chưa quét đúng artifact.

### 10.3. Xác minh từ phía framework/tool

Lập danh sách công cụ thực sự đọc metadata:

| Consumer | Câu hỏi xác minh |
|---|---|
| Spring hoặc DI framework | Quét annotation ở runtime hay build time? |
| Hibernate/JPA | Enum được lưu theo tên, ordinal hay converter? |
| Jackson hoặc serializer khác | JSON value xuất từ name, toString, annotation hay custom codec? |
| OpenAPI/JSON Schema generator | Enum value và annotation default được phát ra thế nào? |
| Annotation processor | Đọc source, classpath hay generated metadata? |
| ASM/Byte Buddy/plugin | Có hỗ trợ class file version mới không? |
| ServiceLoader | Service file và provider class có tồn tại sau shading không? |
| Client generated từ schema | Có xử lý enum value chưa biết không? |

Không nên khẳng định framework luôn có một hành vi mặc định duy nhất mà không kiểm tra **version và cấu hình thực tế**.

## 11. Quy trình thay đổi an toàn

### Bước 1. Định nghĩa hợp đồng trước khi sửa

Ghi lại các phần của API được công bố:

- Tên và mã enum.
- Giá trị JSON, DB hoặc message.
- Annotation type, element, default, retention, target.
- Các metadata attribute mà công cụ đọc.
- Classpath/module path và service registration.

Đánh dấu rõ đâu là implementation detail, đâu là public contract và đâu là dữ liệu lâu dài.

### Bước 2. Thu thập bằng chứng phiên bản cũ

Lưu artifact phiên bản cũ cùng checksum. Xuất các kết quả:

- `javap -v` của enum và annotation công khai.
- Snapshot OpenAPI/JSON Schema nếu có.
- Dữ liệu ví dụ từ DB hoặc message.
- Danh sách service files và manifest.
- Kết quả quét của các framework quan trọng.

Từ đó có baseline để so sánh với artifact mới.

### Bước 3. Phân loại thay đổi

Gắn mỗi thay đổi vào một hoặc nhiều nhóm:

| Nhóm | Ví dụ |
|---|---|
| Source-breaking | Xóa constant, đổi tên annotation element |
| Binary-breaking | Xóa static field enum mà consumer cũ tham chiếu |
| Metadata-breaking | RUNTIME thành CLASS, xóa Signature hoặc MethodParameters |
| Data-breaking | Đổi mã wire, sắp xếp lại enum được lưu ordinal |
| Behavioral-breaking | Đổi default annotation element hoặc nghĩa của enum |
| Tool-breaking | Bytecode mới vượt khả năng của scanner/transformer cũ |

Một thay đổi có thể thuộc nhiều nhóm cùng lúc.

### Bước 4. Chọn migration có đường lui

Ưu tiên các kỹ thuật:

- Thêm API mới trong khi giữ API cũ một thời gian.
- Deprecate tên/element cũ trước khi xóa.
- Đọc cả dữ liệu cũ và mới, nhưng chỉ ghi định dạng mới.
- Dùng mã enum ổn định thay ordinal.
- Thêm annotation element với default rõ ràng.
- Giữ retention/target khi còn consumer phụ thuộc.
- Cập nhật schema và code generation theo phiên bản.
- Nâng bytecode tools và giữ đúng class-file attributes.
- Thực hiện migration dữ liệu có kiểm soát và khả năng rollback.

### Bước 5. Kiểm thử ma trận consumer cũ và mới

Một ma trận tham khảo:

| Producer/Library | Consumer/Reader | Mục tiêu |
|---|---|---|
| Cũ | Cũ | Baseline đã biết |
| Mới | Mới | Chức năng mới hoạt động |
| Mới | Cũ | Consumer cũ đọc được schema/enum value mới hay có fallback? |
| Cũ | Mới | Consumer mới vẫn đọc được dữ liệu/metadata cũ? |

Tùy hệ thống, producer là service phát JSON, thư viện chứa enum, hoặc artifact mang annotation; consumer là client, framework, compiler hay chương trình đọc class file.

Cần kiểm tra cả **binary consumer cũ không compile lại** và **source consumer compile lại** khi đánh giá public Java API.

### Bước 6. Thử trên artifact phát hành thật

Sau khi build:

1. Định danh artifact bằng SHA-256.
2. Dùng đúng JDK và runtime configuration trong ma trận hỗ trợ.
3. Đọc metadata từ JAR đã đóng gói, không chỉ output directory.
4. Khởi động framework và kích hoạt chức năng dùng enum/annotation.
5. Chạy schema generation hoặc code generation thực tế.
6. Kiểm thử dữ liệu cũ, dữ liệu mới và giá trị chưa biết.
7. Kiểm tra consumer đã compile với thư viện cũ.

### Bước 7. Công bố và triển khai theo thứ tự

Nếu producer mới có thể phát enum value mà consumer cũ không hiểu, cần nâng consumer hoặc triển khai khả năng bỏ qua/định tuyến unknown value **trước** khi producer bắt đầu phát giá trị mới.

Với database, việc chuyển từ ordinal sang code ổn định có thể cần giai đoạn dual-read/dual-write hoặc script migrate; thứ tự rollout phải dựa vào loại dữ liệu và yêu cầu rollback. Không nên đổi format tại một điểm nếu nhiều phiên bản ứng dụng đang đọc ghi cùng kho dữ liệu.

## 12. Một số lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Khả năng liên quan | Hướng kiểm tra |
|---|---|---|
| `NoSuchFieldError` | Bytecode cũ tham chiếu enum constant đã bị xóa/đổi tên | `javap` consumer, JAR thực nạp, tên field |
| `IllegalArgumentException: No enum constant ...` | `valueOf()` nhận tên không tồn tại | Dữ liệu JSON/DB/config, spelling và alias |
| `EnumConstantNotPresentException` | Annotation element tham chiếu enum constant không còn | Annotation metadata cũ, enum definition mới |
| `IncompleteAnnotationException` | Annotation usage cũ thiếu element mới không có default | `AnnotationDefault` và metadata các class cũ |
| `AnnotationTypeMismatchException` | Loại giá trị annotation element không khớp definition | Descriptor element và class-file annotation values |
| `TypeNotPresentException` | Metadata tham chiếu kiểu không còn resolve được | Classpath/module path và annotation values |
| Reflection trả `null` | Retention/target/đường quét thay đổi | RuntimeVisibleAnnotations và cách scanner hoạt động |
| DI hoặc route không được đăng ký | Annotation/parameter metadata bị loại khi build | Retention, `-parameters`, shading và framework log |
| JSON parse lỗi khi có trạng thái mới | Client enum không hỗ trợ unknown value | JSON payload, schema và decoder version |
| DB hiển thị trạng thái sai | Ordinal mapping bị lệch | Dữ liệu thô, thứ tự enum và ORM mapping |
| Service không được tìm thấy | Mất `META-INF/services` hoặc provider bị đổi tên | Nội dung JAR, service file và class loader |
| Tool bytecode báo lỗi class version | Scanner không hiểu class file mới | Phiên bản ASM/Byte Buddy và JDK target |

Một triệu chứng có thể có nhiều nguyên nhân. Ví dụ `NoSuchFieldError` không phải lúc nào cũng do enum; nó cũng có thể do field thông thường bị xóa hoặc classpath có JAR sai phiên bản.

## 13. Checklist khi review thay đổi enum

- [ ] Enum có được dùng trong API công khai, JSON, DB, event, config hay schema không?
- [ ] Có consumer dùng `ordinal()` hoặc vị trí `values()` làm định danh không?
- [ ] Việc thêm constant có ảnh hưởng `switch`, validation, mapping hoặc logic mặc định không?
- [ ] Việc xóa/đổi tên có consumer nhị phân cũ tham chiếu hay không?
- [ ] Giá trị wire có mã ổn định độc lập với `name()` và `toString()` không?
- [ ] Dữ liệu lưu trữ cũ có đọc được sau upgrade không?
- [ ] Consumer cũ xử lý được enum value mới hoặc có chính sách rollout rõ ràng không?
- [ ] Annotation trên constant có bị thêm/xóa/đổi giá trị không?
- [ ] Schema/documentation và generated client đã được cập nhật chưa?
- [ ] Đã thử tình huống unknown value và dữ liệu lịch sử chưa?

## 14. Checklist khi review annotation và metadata

- [ ] `@Retention` có giữ đúng cơ chế đọc (source, class file hay reflection) không?
- [ ] `@Target` còn cho phép những vị trí sử dụng cũ không?
- [ ] Các element mới có default phù hợp không?
- [ ] Có element nào bị xóa, đổi tên, đổi type hoặc đổi default không?
- [ ] `@Repeatable` và container annotation có được reader hỗ trợ không?
- [ ] `@Inherited` có thay đổi kết quả lookup trên class hierarchy không?
- [ ] Annotation trên enum constant có được đọc từ field đúng cách không?
- [ ] Các attribute `Signature`, `MethodParameters`, annotation và record metadata còn trong JAR không?
- [ ] Shading, obfuscation và minimization có keep rules cần thiết không?
- [ ] `META-INF/services`, manifest và `module-info.class` đã được kiểm tra chưa?
- [ ] Bytecode scanner và plugin có hỗ trợ class-file version mới không?
- [ ] Đã chạy thử chính framework/tool phiên bản thực tế với artifact mới chưa?

## 15. Ví dụ tổng hợp: thay đổi enum được annotation điều khiển

Giả sử một thư viện công khai:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface WireName {
    String value();
}

public enum ShipmentState {
    @WireName("queued")
    QUEUED,

    @WireName("in_transit")
    IN_TRANSIT,

    @WireName("delivered")
    DELIVERED
}
~~~

Một công cụ sinh schema đọc enum constant và annotation `@WireName` để tạo tập giá trị:

~~~json
{
  "type": "string",
  "enum": ["queued", "in_transit", "delivered"]
}
~~~

Nhóm quyết định đổi tên Java constant `IN_TRANSIT` thành `SHIPPING` và thêm `RETURNED`.

Các tác động tách biệt:

1. **Java source**: module gọi `ShipmentState.IN_TRANSIT` phải chuyển đổi hoặc được cung cấp cơ chế tương thích.
2. **Binary consumer**: bytecode cũ tham chiếu constant field có thể gặp `NoSuchFieldError` nếu tên cũ bị xóa.
3. **Schema**: nếu `SHIPPING` vẫn giữ `@WireName("in_transit")`, wire value cũ có thể được duy trì; `RETURNED` cần wire name mới.
4. **Consumer cũ**: phải biết xử lý `"returned"` trước khi producer bắt đầu phát giá trị này.
5. **Reflection tool**: phải đọc annotation ở field; nếu retention đổi sang CLASS thì reader dùng reflection sẽ không còn thấy nó.
6. **Database**: nếu trước đây lưu Java name hoặc ordinal, cần migration độc lập với schema JSON.
7. **Generated code**: phải sinh lại client/schema và chạy test tương thích hai chiều.

Một rollout an toàn có thể là: triển khai reader hỗ trợ giá trị mới, cập nhật dữ liệu/schema, rồi mới cho phép producer phát giá trị mới. Nếu Java constant cũ là public binary API, cần giữ compatibility layer hoặc công bố breaking release theo chính sách thư viện.

## Kết luận

Enum, annotation và metadata trong class file là một phần của hợp đồng Java khi có framework hoặc công cụ bên ngoài đọc chúng. Thêm enum constant có thể không làm hỏng field reference cũ nhưng vẫn gây lỗi logic, schema và dữ liệu. Đổi retention hoặc annotation default có thể làm framework thay đổi hành vi mà không xuất hiện compile error. Xóa `Signature`, `MethodParameters` hoặc service metadata có thể khiến artifact chạy được nhưng mất khả năng reflection, binding hoặc discovery.

Muốn tiến hóa API an toàn, phải **xác định consumer thực tế**, phân biệt source/binary/metadata/data compatibility, ghi baseline artifact, thử cả consumer cũ và mới, và công bố chiến lược migration. Kiểm chứng phải thực hiện trên artifact cuối cùng cùng cấu hình runtime và công cụ mà hệ thống thực sự sử dụng.

