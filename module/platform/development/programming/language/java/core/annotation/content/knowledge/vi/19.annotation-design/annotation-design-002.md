# Thiết kế tên gọi thể hiện đúng ý nghĩa siêu dữ liệu trong Java Annotation

## 1. Tại sao tên annotation là một phần của hợp đồng thiết kế?

Annotation trong Java là **siêu dữ liệu (metadata)** gắn với các khai báo hoặc vị trí sử dụng kiểu. Khi một người đọc `@MaintainedBy(team = "catalog")` trên một class, họ kỳ vọng annotation trả lời câu hỏi **“ai duy trì thành phần này?”**. Khi gặp `@RequiresPermission("catalog.read")` trên một method, họ kỳ vọng annotation biểu thị **“method này yêu cầu quyền gì?”**.

Tên annotation không chỉ để mã biên dịch được. Tên đó là một phần API giúp người đọc, công cụ kiểm tra, framework và những người bảo trì dự án diễn giải **ý nghĩa được khai báo**. Một tên mơ hồ có thể dẫn đến logic xử lý sai ngay cả khi cấu trúc Java và kiểu phần tử đều hợp lệ.

Ví dụ:

~~~java
@MaintainedBy(team = "catalog")
class CatalogRepository {}

@RequiresPermission("catalog.read")
void listCatalog() {}
~~~

Đây là **mã minh họa cách đặt tên**, chưa phải chương trình độc lập. Hai annotation có hai loại ý nghĩa khác nhau:

- `MaintainedBy` mô tả một **thuộc tính/quan hệ hiện có**: thành phần được nhóm nào duy trì.
- `RequiresPermission` mô tả **điều kiện/chính sách mong muốn** để thực hiện một hành động.

Cả hai chỉ là **metadata**. Java không tự quản lý nhóm sở hữu class hoặc chặn truy cập method. Những hành vi ấy cần công cụ, framework hoặc mã ứng dụng **tiêu thụ annotation**. Tên tốt phải giúp người sử dụng nhận ra được phân biệt này, thay vì hàm ý rằng chỉ gắn annotation đã khiến JVM thực thi chính sách.

**Mục tiêu bài học:** thiết kế tên annotation type, tên các element bên trong, tên package và ý nghĩa hợp đồng sao cho người đọc không phải đoán metadata nói về **đối tượng nào, thuộc tính nào, điều kiện nào và hiệu lực của nó tới đâu**.

## 2. Tên phải mô tả sự thật hoặc ý định của metadata, không hứa hành vi không có

So sánh các tên giả định:

| Tên | Người đọc thường hiểu | Đánh giá khi thiết kế |
| --- | --- | --- |
| `@MaintainedBy(team = "search")` | Thành phần được nhóm `search` duy trì | Cụ thể về quan hệ sở hữu/bảo trì |
| `@OwnedBy("search")` | Nhóm hoặc cá nhân sở hữu thành phần | Gọn nếu “owner” đã có định nghĩa trong dự án |
| `@RequiresPermission("orders.write")` | Lời gọi có yêu cầu quyền này | Tốt để khai báo chính sách; phải có bộ thực thi |
| `@Audited` | Thành phần được theo dõi audit | Dễ hiểu ở cấp ý định, nhưng cần biết công cụ có ghi audit hay chỉ đánh dấu |
| `@AuditEvent("DELETE_ORDER")` | Metadata chỉ ra sự kiện audit | Rõ hơn khi công cụ đọc nó như mô tả event |
| `@Info("...")` | Một thông tin bất kỳ | Quá rộng nếu API được dùng cho nghiệp vụ cụ thể |
| `@Data` | “Dữ liệu” không biết loại gì | Rất mơ hồ ngoài một framework có hợp đồng đã biết |
| `@RunFast` | JVM sẽ làm code chạy nhanh | Dễ gây kỳ vọng sai nếu chỉ là nhãn không có thực thi |
| `@Safe` | Thành phần luôn an toàn | Khẳng định quá rộng, khó xác thực và thiếu phạm vi |
| `@Validated` | Đã được xác thực/kiểm tra | Chỉ phù hợp khi thực sự mô tả trạng thái đã kiểm tra, không phù hợp để yêu cầu kiểm tra |
| `@RequiresValidation` | Cần được kiểm tra | Phù hợp hơn cho một yêu cầu chưa thực hiện |

Câu hỏi nên đặt ra trước khi chọn tên: **annotation đang “mô tả một thực tế”, “yêu cầu một chính sách”, “đánh dấu một quy trình”, hay “truyền cấu hình cho công cụ”?** Những loại này cần từ vựng khác nhau.

Ví dụ, nếu một công cụ sẽ kiểm tra rằng method đã được review, `@ReviewedBy("qa")` chỉ nên dùng khi metadata biểu diễn kết quả review đã hoàn tất; nếu nó là yêu cầu giao cho đội QA thực hiện, `@ReviewRequired` hoặc `@ReviewOwner("qa")` sẽ trung thực hơn.

Một annotation `@Immutable` có ý nghĩa rất mạnh: người đọc có thể hiểu object không thể thay đổi. Nếu annotation chỉ do nhóm phát triển gắn bằng tay và không có cơ chế chứng minh/kiểm tra, cần ghi tài liệu rõ đây là **cam kết thiết kế do tác giả khai báo**, không phải thuộc tính được Java tự cưỡng chế.

## 3. Dùng từ loại và cấu trúc tên nhất quán

Java annotation type là một loại interface đặc biệt, vì vậy thông thường tuân thủ **UpperCamelCase** như tên type Java. Java không bắt buộc hậu tố `Annotation`.

Có thể chọn cấu trúc theo loại ý nghĩa:

| Loại metadata | Kiểu tên gợi ý | Ví dụ |
| --- | --- | --- |
| Thuộc tính/quan hệ đã được khai báo | Danh từ, tính từ hoặc cụm phân từ | `@Deprecated`, `@Documented`, `@MaintainedBy` |
| Điều kiện trước khi thực hiện | `Requires...`, `AllowedFor...`, `AccessPolicy...` | `@RequiresPermission`, `@RequiresReview` |
| Chế độ hoặc tùy chọn xử lý | Danh từ chỉ cấu hình/chính sách | `@RetryPolicy`, `@CachePolicy` |
| Vai trò của thành phần trong hệ thống | Danh từ hoặc danh từ ghép | `@Endpoint`, `@Handler` |
| Yêu cầu sinh mã/kiểm tra lúc biên dịch | `Generate...`, `Check...`, `Enforce...` | `@GenerateMapper`, `@CheckNaming` |
| Dữ liệu xác định nguồn hoặc chủ sở hữu | `...By`, `...Owner`, `...Source` | `@CreatedBy`, `@ModuleOwner` |

Đây là **khuyến nghị đặt tên theo ngữ nghĩa**, không phải danh sách từ khóa mà Java yêu cầu. Những annotation công khai đã có hợp đồng riêng, ví dụ `@Override`, `@FunctionalInterface` hay các annotation của thư viện, nên tuân thủ contract của chính chúng chứ không đổi tên để ép theo khuôn.

### 3.1. Đừng biến mọi tên thành động từ yêu cầu JVM thực thi

`@Validate`, `@Encrypt`, `@Delete` nghe như lệnh được thực thi tức thì. Khi annotation chỉ mô tả metadata cho công cụ sẽ chạy sau, tên như `@RequiresValidation`, `@EncryptionPolicy` hoặc `@DeletionRule` thường phân biệt được **ý định khai báo** với **hành vi hiện thực**.

Tuy nhiên, một framework có định nghĩa rõ `@Transactional` hoặc `@Cacheable` có thể dùng tên mô tả hành vi vì tài liệu khẳng định framework sẽ xử lý những annotation này khi đúng điều kiện. **Tên không sai tự thân**; sai là khi ý nghĩa mà tên hứa hẹn không khớp với cơ chế thực tế hoặc không được giải thích.

### 3.2. Phân biệt trạng thái và yêu cầu

Ví dụ:

~~~java
@ReviewedBy("alice")
class ReleasedChange {}

@ReviewRequired
class PendingChange {}
~~~

Hai khai báo trên mang **nghĩa khác nhau**: một bên nói “đã được review bởi ai”, một bên nói “cần review”. Nếu dự án dùng chung `@Reviewed` cho cả hai, người đọc hoặc processor không thể biết trạng thái có hoàn tất chưa.

Tương tự, `@Encrypted` mô tả trạng thái dữ liệu đã mã hóa; `@EncryptWith("AES-GCM")` nghe như chỉ thị cho công cụ thực hiện mã hóa. Nếu công cụ không thực thi yêu cầu, tên phải được diễn giải đúng là **chỉ dẫn metadata**, không phải kết quả thực thi đã được bảo đảm.

## 4. Tên element bên trong annotation cũng phải nói rõ ý nghĩa

Annotation type chứa những **elements** dạng phương thức không tham số. Một ví dụ thiết kế:

~~~java
@interface RetryPolicy {
    int maxAttempts() default 3;
    long delayMillis() default 200;
}
~~~

- `maxAttempts` nói về **tổng số lần thử tối đa**; khác với `maxRetries` (số lần *thử lại* sau lần thử đầu).
- `delayMillis` bao gồm **đơn vị mili giây**. Nếu chỉ viết `delay`, người sử dụng phải tra tài liệu để biết giây, mili giây hay nanosecond.
- Giá trị mặc định cần tương thích với ý nghĩa element: `maxAttempts() default 3` và `delayMillis() default 200` không đồng nghĩa retry đã được Java tự bật.
- Kiểu `int` và `long` đảm bảo dữ liệu có kiểu số, nhưng compiler không tự xác nhận ràng buộc nghiệp vụ như `maxAttempts >= 1`. Công cụ sử dụng metadata phải kiểm tra nếu đó là contract.

Các tên element tốt thường tuân thủ **lowerCamelCase**, sử dụng danh từ/cụm từ mô tả giá trị, thêm đơn vị khi có ý nghĩa và tránh tên quá rộng như `data()`, `name()`, `flag()` nếu tồn tại cách cụ thể hơn.

### 4.1. Khi nào dùng value()?

Java cho phép cú pháp ngắn khi element tên đúng là `value`:

~~~java
@interface RequiresPermission {
    String value();
}

@RequiresPermission("catalog.read")
class CatalogReader {}
~~~

`@RequiresPermission("catalog.read")` là dạng rút gọn của `@RequiresPermission(value = "catalog.read")`. Cú pháp này phù hợp khi annotation có **một giá trị chính hiển nhiên** và tên annotation đủ rõ để hiểu giá trị đó là gì.

Không nên lạm dụng `value()` nếu annotation mang nhiều trường metadata hoặc giá trị chính dễ gây nhầm. Ví dụ:

~~~java
@interface MaintainedBy {
    String team();
}

@MaintainedBy(team = "catalog")
class CatalogService {}
~~~

`team = "catalog"` rõ hơn `value = "catalog"` khi có thể tồn tại các ý niệm khác như tên người, đơn vị nghiệp vụ hoặc repository sở hữu.

Nếu có nhiều elements với ý nghĩa gần nhau, hãy dùng tên minh bạch:

~~~java
@interface ApiLifecycle {
    String introducedIn();
    String deprecatedSince() default "";
}
~~~

`introducedIn` và `deprecatedSince` tránh nhập nhằng hơn hai element tên `from`/`until` nếu hệ thống cần quản lý vòng đời API. Chuỗi rỗng ở đây chỉ là một **quy ước dữ liệu phải được tài liệu hóa**; Java annotation không chấp nhận `null` làm giá trị mặc định.

### 4.2. Đặt tên boolean phản ánh một mệnh đề kiểm chứng được

Ví dụ:

~~~java
@interface ExportPolicy {
    boolean publicApi() default false;
    boolean requiresApproval() default true;
}
~~~

Các tên boolean có thể đọc thành câu khẳng định và thể hiện rõ giá trị `true`/`false`. Một tên `flag()` hoặc `state()` không cho biết `true` có nghĩa gì.

Một boolean `secure()` cũng thường quá rộng: “secure” về vận chuyển, xác thực, phân quyền, mã hóa hay dữ liệu? Hãy tách thành những điều kiện cụ thể nếu yêu cầu nghiệp vụ cho phép.

### 4.3. Tên và kiểu phải nhất quán với ý nghĩa

Nếu metadata là mức độ truy cập có hữu hạn lựa chọn, dùng enum thay vì chuỗi tự do có thể rõ và an toàn hơn:

~~~java
enum Exposure { INTERNAL, PARTNER, PUBLIC }

@interface ApiExposure {
    Exposure level() default Exposure.INTERNAL;
}
~~~

Nếu metadata là danh sách thẻ phân loại, `String[] tags() default {}` diễn đạt đúng kiểu mảng; nếu là một tag duy nhất, `String tag()` hợp lý hơn. Không đặt `tags()` nhưng lại mô tả trong tài liệu rằng chỉ được có đúng một giá trị mà không giải thích lý do.

Một annotation element chỉ được dùng các kiểu hợp lệ theo Java: primitive, `String`, `Class` phù hợp, enum, annotation type và mảng **một chiều** của những kiểu đó. Không thể dùng tùy ý `List<String>` hay `Map<String, String>` như element type; thiết kế tên và cấu trúc phải nằm trong ràng buộc này.

## 5. Phạm vi ý nghĩa phải khớp với @Target

Tên annotation đưa ra một thông điệp, nhưng **`@Target` mới quy định những vị trí hợp lệ để gắn**. Thiết kế phải nhất quán giữa hai thứ.

| Tên/ý nghĩa dự định | Target thường hợp lý | Vì sao |
| --- | --- | --- |
| `@MaintainedBy` cho toàn bộ một class | `ElementType.TYPE` | Mô tả chủ sở hữu khai báo kiểu |
| `@RequiresPermission` cho lời gọi method | `ElementType.METHOD` | Chính sách gắn với thao tác |
| `@ColumnName` cho một field | `ElementType.FIELD` | Mô tả mapping field |
| `@ParameterAlias` cho tham số | `ElementType.PARAMETER` | Mô tả từng parameter declaration |
| `@NonNullValue` cho vị trí sử dụng kiểu | `ElementType.TYPE_USE` | Metadata thuộc type-use; đọc bằng API tương ứng |
| `@ModuleOwner` cho JPMS module | `ElementType.MODULE` | Mô tả toàn module ở `module-info.java` |

Bảng này là gợi ý thiết kế; một annotation có thể có **nhiều target** khi cùng ngữ nghĩa áp dụng được ở nhiều vị trí. Nhưng đừng mở rộng target chỉ để annotation “dùng được ở mọi nơi”. Nếu `@RequiresPermission` đặt trên class và method, hãy định nghĩa rõ kết hợp hai cấp: class policy là mặc định? Method policy bổ sung hay ghi đè? Không có quy tắc hợp nhất nghiệp vụ tự động do Java đưa ra.

Nếu không khai báo `@Target`, một annotation có thể được dùng trên nhiều **declaration contexts** theo quy tắc Java; điều đó **không** có nghĩa tự động hỗ trợ mọi `TYPE_USE`. Với metadata có ý nghĩa chính xác, nên khai báo target rõ ràng để compiler ngăn việc gắn sai chỗ.

Một thiết kế khó hiểu là `@ParameterFormat` chỉ có target `TYPE` nhưng tài liệu yêu cầu dùng trên tham số. Compiler sẽ từ chối; đổi tên thôi không giải quyết được, phải sửa contract target.

## 6. Retention và ý nghĩa mà tên hứa hẹn

`@Retention` quyết định annotation tồn tại đến giai đoạn nào. Ý nghĩa tên nên khớp với **nơi metadata thực sự được tiêu thụ**.

| Retention | Dùng khi | Điều cần nhớ |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Compiler, annotation processor, lint/check lúc biên dịch | Lần sử dụng annotation không được lưu trong class file đích |
| `RetentionPolicy.CLASS` | Công cụ xử lý class file sau biên dịch | Được lưu trong bytecode, nhưng Java reflection thông thường không nhìn thấy |
| `RetentionPolicy.RUNTIME` | Framework/reflection phải đọc metadata khi chương trình chạy | Có thể truy xuất qua `AnnotatedElement` đúng đích, không tự kích hoạt hành vi |

Ví dụ, nếu `@RequiresPermission` được một runtime interceptor dùng để chặn thao tác, annotation nên có `@Retention(RUNTIME)`. Nếu `@GenerateAdapter` chỉ để annotation processor sinh source trong `javac`, `@Retention(SOURCE)` thường đủ.

Một tên `@RuntimeValidated` mà có retention `SOURCE` và không có bước nào tạo validator runtime sẽ gây kỳ vọng sai. Ngược lại, chỉ đổi retention từ `SOURCE` sang `RUNTIME` không khiến validation tự được thực hiện.

**Quan hệ tên–target–retention–consumer tạo thành một hợp đồng nhất quán.** Không thể đánh giá tên một cách độc lập với cơ chế đang đọc annotation.

## 7. Ví dụ Java 17+ hoàn chỉnh: metadata rõ nghĩa và bộ tiêu thụ tường minh

Ví dụ gồm hai annotation:

- `@MaintainedBy(team = ...)` mô tả **nhóm duy trì một class**, không làm thay đổi hành vi của class.
- `@RequiresPermission("...")` mô tả **quyền cần để gọi method**. Chương trình demo chủ động đọc metadata và chỉ gọi method nếu quyền được cấp khớp với yêu cầu.

Lưu **toàn bộ đoạn dưới đây** vào tệp `MetadataNamingDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface MaintainedBy {
    String team();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequiresPermission {
    String value();
}

@MaintainedBy(team = "catalog")
final class CatalogApi {
    @RequiresPermission("catalog.read")
    public String list() {
        return "books";
    }

    @RequiresPermission("catalog.write")
    public String update() {
        return "updated";
    }
}

public class MetadataNamingDemo {
    private static void attempt(String methodName, String grantedPermission)
            throws ReflectiveOperationException {
        Method method = CatalogApi.class.getDeclaredMethod(methodName);
        RequiresPermission requirement =
                method.getAnnotation(RequiresPermission.class);
        boolean allowed = requirement != null
                && grantedPermission.equals(requirement.value());

        System.out.println(methodName + ": " + (allowed ? "allowed" : "denied"));
        if (allowed) {
            System.out.println(method.invoke(new CatalogApi()));
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MaintainedBy owner = CatalogApi.class.getAnnotation(MaintainedBy.class);
        System.out.println("owner=" + owner.team());
        attempt("list", "catalog.read");
        attempt("update", "catalog.read");
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp, với JDK 17 trở lên:

~~~bash
javac --release 17 MetadataNamingDemo.java
java MetadataNamingDemo
~~~

**Stdout chính xác:**

~~~text
owner=catalog
list: allowed
books
update: denied
~~~

Kết quả đã được kiểm tra bằng cách biên dịch `javac --release 17` và chạy chương trình trên JDK tương thích Java 17.

### 7.1. Giải thích thiết kế tên qua đầu ra

1. `CatalogApi` được đánh dấu `@MaintainedBy(team = "catalog")`. Reflection đọc annotation trên **class** và in `owner=catalog`. Java không tự thông báo đội này hay kiểm tra chủ sở hữu có hợp lệ.
2. Method `list()` được đánh dấu `@RequiresPermission("catalog.read")`. Code `attempt` lấy `Method` và gọi `getAnnotation(RequiresPermission.class)`. Vì quyền cấp là `catalog.read`, điều kiện so sánh đạt và chương trình gọi method, in `books`.
3. Method `update()` yêu cầu `catalog.write`, nhưng quyền đang cấp chỉ là `catalog.read`; hàm `attempt` **không gọi** method đó, in `update: denied`.
4. Sự từ chối xảy ra vì **logic Java trong `attempt` tự đọc và xử lý metadata**, chứ không phải `@RequiresPermission` có khả năng tự chặn một lời gọi trực tiếp. Nếu người dùng gọi thẳng `new CatalogApi().update()`, annotation không tự can thiệp.
5. `@Target(TYPE)` và `@Target(METHOD)` ngăn sử dụng hai annotation này ở những vị trí không phù hợp theo thiết kế.
6. `@Retention(RUNTIME)` là điều kiện cần để reflection đọc metadata. Dùng `SOURCE` cho `RequiresPermission` trong demo sẽ làm `getAnnotation(...)` không nhìn thấy annotation runtime.

**Lưu ý bảo mật:** đây là ví dụ nhằm chứng minh **ngữ nghĩa tên annotation và bước tiêu thụ tường minh**, **không phải một cơ chế phân quyền production**. Phân quyền thực tế cần định danh người dùng, xác thực, nguồn quyền đáng tin cậy, cơ chế bao phủ mọi đường gọi và chính sách mặc định từ chối. Không coi annotation alone là tường lửa bảo vệ method. Demo từ chối khi annotation không tồn tại (`requirement == null`) để minh họa một chính sách cụ thể; hệ thống thật phải mô tả rõ cách xử lý method không được gắn annotation.

## 8. Đặt tên phù hợp với cấp độ khái niệm

### 8.1. Tên chỉ tính chất, không đánh lừa về khả năng đảm bảo

`@ThreadSafe` có thể là một cam kết thiết kế rằng kiểu được tác giả xác định là thread-safe; gắn annotation **không khiến class có synchronization**. `@NotNull` hoặc `@NonNull` có thể là quy ước cho bộ kiểm tra tĩnh/runtime trong một framework; Java Core không tự chặn việc gán null chỉ vì annotation tồn tại.

Nếu một team chưa có hệ thống nào tiêu thụ annotation, hãy ghi rõ nó dùng để **tài liệu hóa** hay dành cho **công cụ dự kiến**. Không nên mang một tên khẳng định mạnh như `@Validated` nếu chỉ là nhãn “nên xác thực”.

### 8.2. Tên cần xác định đối tượng ngữ nghĩa

Một annotation có tên `@Sensitive` trên field dễ khiến người đọc hỏi: dữ liệu nhạy cảm về bảo mật, quyền riêng tư hay mức độ ưu tiên? Trong miền dữ liệu cá nhân, `@ContainsPersonalData` có thể diễn đạt chính xác hơn nếu contract là đánh dấu dữ liệu cá nhân. Nếu mục tiêu là yêu cầu che log, `@RedactInLogs` (kèm bộ xử lý) là một chính sách khác.

Đừng dùng cùng tên `@Sensitive` cho cả “dữ liệu chứa thông tin cá nhân”, “yêu cầu mã hóa” và “không được ghi log” rồi để mọi consumer tự diễn giải khác nhau. Tách những khái niệm mà lifecycle và công cụ xử lý khác biệt.

### 8.3. Tên chỉ hành vi phải chỉ đúng ai thực thi

`@Cacheable` thường được framework dùng để quyết định có cache hay không. Nhưng trong ứng dụng không có caching interceptor, annotation với tên đó chỉ là metadata. Khi thiết kế API của bạn, tài liệu nên ghi rõ **processor/interceptor/tool nào đọc**, khi nào xử lý, target nào được hỗ trợ, và khi nào annotation có thể bị bỏ qua.

Một tên tốt làm cho việc viết tài liệu ngắn hơn, **không thay thế tài liệu về hành vi thực thi**.

## 9. Package, tên công khai và khả năng tìm kiếm

Annotation type là một Java type nên tuân quy tắc đặt tên và package bình thường.

- **Tên type:** dùng `UpperCamelCase`; chẳng hạn `RequiresPermission`, `MaintainedBy`, `ApiExposure`. Không bắt buộc tên phải bắt đầu bằng `@` trong khai báo: dấu `@` chỉ xuất hiện khi sử dụng annotation; khai báo dùng `@interface`.
- **Tên element:** dùng `lowerCamelCase`, ví dụ `team()`, `expiresAt()`, `maxAttempts()`.
- **Package:** thường dùng chữ thường phân cấp theo miền sở hữu, ví dụ `com.example.catalog.annotation` hoặc `com.example.security.policy`. Tránh `com.example.annotations` quá rộng khi có nhiều loại metadata độc lập, nếu cấu trúc dự án đủ lớn để phân tách hợp lý.
- **Tên dễ tìm:** khác biệt đủ rõ với những annotation phổ biến của framework khác. Hai annotation `com.alpha.Policy` và `com.beta.Policy` cùng simple name nhưng có contract khác nhau sẽ gây nhầm khi import; tên như `AccessPolicy` và `RetentionPolicy` diễn đạt miền rõ hơn.
- **API công khai:** đặt annotation vào package có thể sử dụng từ những module/consumer phù hợp, công bố JavaDoc và xem xét tương thích tên/element về lâu dài.

Đối với JPMS, một annotation type được khai báo `public` chưa chắc được module khác import nếu module chứa nó **không export package** hoặc consumer **không đọc được module**. Khả năng truy cập tên metadata cũng là một phần của API, nhưng `@Target` và `@Retention` không thay cho `requires`/`exports`.

### 9.1. Có nên thêm hậu tố Annotation?

Không có quy tắc Java nào bắt buộc `@AuditAnnotation` hay `@PermissionAnnotation`. Tên `@RequiresPermission` thường tự cho thấy vai trò metadata khi đặt trước method, trong khi hậu tố `Annotation` có thể làm tên dài nhưng không bổ sung ngữ nghĩa.

Nếu dự án đã có một public class `Policy` và cần tránh trùng với annotation type cùng tên, nên chọn tên mang ý nghĩa cụ thể `AccessPolicy` hoặc `PolicyMarker` dựa trên contract thật, không tự động thêm hậu tố `Annotation` cho toàn bộ API.

## 10. Đặt tên cho annotation lặp và annotation chứa

Một annotation **repeatable** có thể gắn nhiều lần vào một khai báo. Tên annotation thành phần nên thể hiện **một đơn vị metadata**, còn container thường dùng tên tập hợp hợp lý.

Ví dụ minh họa (chưa có `main`):

~~~java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Repeatable(RequiredPermissions.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequiresPermission {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequiredPermissions {
    RequiresPermission[] value();
}

class AdminApi {
    @RequiresPermission("orders.read")
    @RequiresPermission("orders.write")
    public void reconcile() {}
}
~~~

`RequiresPermission` biểu diễn một yêu cầu quyền; `RequiredPermissions` là container gồm nhiều phần tử. Java yêu cầu cấu trúc `value()` của container là mảng của annotation thành phần. Chọn tên container sao cho người đọc hiểu đó là **tập hợp**, nhưng **ngữ nghĩa kết hợp** vẫn phải do công cụ xác định.

Ví dụ, hai `@RequiresPermission` có nghĩa **phải có tất cả quyền** hay **chỉ cần một quyền**? `@Repeatable` không tự xác định logic AND/OR. Nếu sản phẩm cần policy chỉ một trong nhiều quyền, có thể thiết kế metadata riêng như `@RequiresAnyPermission` và một element mảng; nếu muốn tất cả quyền, `@RequiresAllPermissions` làm ý nghĩa rõ hơn. Hai lựa chọn có yêu cầu triển khai khác nhau.

**Bài học về tên:** chỉ dùng số nhiều `RequiredPermissions` chưa đủ để trả lời cách bộ xử lý kết hợp điều kiện. Tên mức cao và tài liệu phải nói rõ **quy tắc ghép** nếu công cụ tiêu thụ metadata.

## 11. Thiết kế default và giá trị hợp lệ phù hợp với tên

Giả sử:

~~~java
@interface RateLimit {
    int requestsPerMinute() default 60;
    boolean enabled() default true;
}
~~~

Nội dung này chỉ minh họa khai báo, không có `main`.

- `requestsPerMinute` chứa cả **đơn vị thời gian**, giúp tránh hiểu sai 60 lần mỗi giây.
- `enabled` là trạng thái cấu hình: mặc định `true`. Nhưng không có logic nào tự đếm request nếu ứng dụng không cài đặt.
- Nếu mục tiêu là giới hạn tổng request trong một cửa sổ động, từ `PerMinute` có thể quá cứng; lúc đó nên thiết kế riêng kiểu dữ liệu/element cho đơn vị và cửa sổ thời gian.
- Dùng `default` khi có một giá trị chung có ý nghĩa. Nếu **không tồn tại mặc định an toàn** cho một thuộc tính (ví dụ chủ sở hữu hoặc permission bắt buộc), hãy để element **không có `default`** để compiler buộc nơi gắn annotation phải cung cấp.
- Các ràng buộc không được kiểm tra chỉ nhờ tên: `@RateLimit(requestsPerMinute = -5)` vẫn có giá trị kiểu `int`; công cụ tiêu thụ cần kiểm tra hợp lệ theo nghiệp vụ.

Đừng dùng chuỗi sentinel `"none"` hoặc `""` nếu ý nghĩa của chúng có thể bị nhầm với một giá trị thực. Annotation không hỗ trợ literal `null` như giá trị element/default. Nếu cần trạng thái “không có”, hãy thiết kế sentinel/enum có contract rõ ràng.

## 12. Tên annotation cần bền vững trước thay đổi và tương thích API

Khi annotation type là API công khai, đổi tên `@Owner` thành `@MaintainedBy` không chỉ là sửa wording. Mọi source đang import, dùng annotation hoặc processor đang quét tên cũ có thể cần sửa; metadata trong các class file đã biên dịch có thể còn tham chiếu đến type cũ. Vì vậy:

1. **Chọn ngữ nghĩa đủ ổn định trước khi phát hành.** Đừng đặt tên dựa trên nickname dự án hay một chi tiết implementation ngắn hạn nếu contract sẽ được tái sử dụng.
2. **Tránh mở rộng âm thầm một tên cũ thành ý nghĩa mới.** Nếu `@ReviewedBy` từng có nghĩa review đã hoàn tất, đừng sửa consumer để hiểu nó là review cần làm mà không có chính sách chuyển đổi.
3. **Đổi tên hoặc thay đổi element có thể phá source compatibility.** Consumer gọi `@MaintainedBy(team = "...")` không tương thích với định nghĩa mới chỉ có `ownerTeam()`.
4. **Thêm element bắt buộc mới** có thể khiến các nơi dùng cũ không biên dịch lại được. Nếu thêm element có giá trị mặc định, cần cân nhắc ảnh hưởng hành vi tới các nơi dùng không truyền giá trị.
5. **Default có thể đổi giá trị quan sát được** với nơi dùng không ghi tường minh, vì mặc định gắn với định nghĩa annotation type và được áp dụng khi đọc metadata. Đây là thay đổi contract dù source code không đổi.
6. **Thay đổi `@Target` hoặc `@Retention`** làm thay đổi nơi annotation hợp lệ hoặc cách processor/reflection nhìn thấy metadata; nó không chỉ là sửa tên.
7. Khi giới thiệu tên mới, cần có kế hoạch migration và thử nghiệm với compiler, annotation processor, runtime framework hoặc tài liệu công khai liên quan.

Một số tên annotation đã mang nghĩa quen thuộc trong Java, ví dụ `@Override` (kiểm tra override ở compile time) hoặc `@Deprecated` (đánh dấu API không khuyến khích dùng). Khi tự thiết kế metadata, nên **học cách tên thể hiện vai trò rõ ràng**, không định nghĩa lại cùng một tên cho một nghĩa hoàn toàn khác trong package của mình nếu sẽ gây hiểu lầm.

## 13. Chất lượng tài liệu của annotation là một phần của tên gọi

Tên rõ ràng nhất cũng cần JavaDoc khi annotation chứa quy tắc nghiệp vụ. Ví dụ:

~~~java
/**
 * Declares the permission required to invoke the annotated method.
 *
 * <p>This annotation has no effect unless an authorization
 * component explicitly reads and enforces it.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface RequiresPermission {
    /** Permission identifier understood by the authorization component. */
    String value();
}
~~~

Đây là **đoạn minh họa API**. Muốn biên dịch riêng cần các import `java.lang.annotation.Retention`, `RetentionPolicy`, `Target` và `ElementType`, đồng thời đặt public annotation trong tệp `RequiresPermission.java` phù hợp.

Một hợp đồng tốt nên trả lời:

- Annotation mô tả **ai/cái gì** và áp dụng ở **cấp nào**?
- Element nào là bắt buộc, kiểu dữ liệu và đơn vị của từng element?
- Giá trị nào là hợp lệ và mặc định của chúng có ý nghĩa gì?
- Metadata được đọc ở **compile time, class file hay runtime**?
- Component/processor/framework nào tiêu thụ nó? Nếu component đó không được bật, annotation có hiệu lực gì?
- Nếu nhiều annotation cùng/khác kiểu xuất hiện, thứ tự và quy tắc kết hợp là gì?
- Có kế thừa metadata từ superclass không? `@Inherited` chỉ có ý nghĩa đặc biệt với một số tra cứu annotation **trên class**, không tự làm method/field annotation kế thừa.
- Metadata có yêu cầu bảo mật hoặc hiệu suất nào? Có chứa dữ liệu nhạy cảm không?

Đừng đưa mật khẩu, token hoặc bí mật thật vào annotation element với lý do “chỉ là metadata”; với retention `CLASS` hoặc `RUNTIME`, các giá trị có thể tồn tại trong bytecode và được các công cụ phân tích quan sát.

## 14. Phản ví dụ: cải thiện tên theo ngữ nghĩa

### Tình huống A — giới hạn xử lý

**Mơ hồ:**

~~~java
@Fast(5)
void fetch() {}
~~~

Con số `5` là mili giây, mức ưu tiên, số luồng hay số lần retry? `Fast` là lời hứa về tốc độ hay yêu cầu áp dụng chính sách?

**Rõ hơn:**

~~~java
@RetryPolicy(maxAttempts = 5, delayMillis = 200)
void fetch() {}
~~~

Ví dụ thứ hai mô tả **chính sách retry** và đơn vị, không hứa method luôn chạy nhanh. Đây là mã minh họa, chỉ biên dịch nếu những annotation types đã được khai báo tương ứng và target phù hợp.

### Tình huống B — quy định về log

**Mơ hồ:**

~~~java
@Sensitive
String secret;
~~~

Nếu mục đích là không ghi giá trị field ra log, có thể dùng `@RedactInLogs` kèm tài liệu rằng logger/serializer cụ thể phải tiêu thụ annotation. Nhưng nếu mục đích là định danh dữ liệu cá nhân, tên `@ContainsPersonalData` diễn đạt một **thuộc tính dữ liệu** khác. Không có tên duy nhất đúng cho cả hai nghĩa.

### Tình huống C — trạng thái kiểm duyệt

**Mơ hồ:**

~~~java
@Review
class PaymentChange {}
~~~

Nếu annotation nói quá trình review đã xong, `@ReviewedBy(team = "risk")` cụ thể hơn. Nếu annotation yêu cầu review, `@RequiresReview(team = "risk")` cụ thể hơn. Hai tên dẫn đến hai kiểu kiểm tra khác nhau, tránh nhầm giữa **sự kiện đã hoàn thành** và **chính sách cần thực hiện**.

### Tình huống D — quyền truy cập

**Mơ hồ:**

~~~java
@Security("admin")
void deleteOrder() {}
~~~

Tên `Security` không nói rõ giá trị `admin` là username, role, permission, group hay mức bảo vệ. Nếu contract yêu cầu role, dùng `@RequiresRole("admin")`; nếu yêu cầu một permission cụ thể, dùng `@RequiresPermission("orders.delete")`. Hai mô hình phân quyền khác nhau; chọn tên theo dữ liệu thực tế được xác minh.

## 15. Checklist chọn tên annotation trong code review

Trước khi phát hành một annotation mới, đánh giá:

1. **Một câu định nghĩa:** có thể mô tả rõ annotation trong một câu mà không dùng chính tên của nó để giải thích không?
2. **Sự thật hay yêu cầu:** tên có nói đúng annotation đang ghi nhận **trạng thái**, **chính sách**, **khả năng**, hay **đầu vào cấu hình**?
3. **Không hứa quá mức:** người đọc có hiểu nhầm Java tự thực thi một hành vi không có implementation không?
4. **Target hợp nghĩa:** annotation type khai báo `@Target` đúng class, method, field, parameter, type-use, package hoặc module?
5. **Retention hợp consumer:** compile-time checker/bytecode tool/runtime framework có đọc được annotation theo `@Retention` không?
6. **Element rõ:** tên element dùng lowerCamelCase, đơn vị cụ thể, boolean có mệnh đề rõ và giá trị mặc định có lý do?
7. **value() có đáng dùng:** annotation chỉ có một giá trị trung tâm hiển nhiên hay cần tên element tường minh?
8. **Package hợp miền:** annotation đặt trong package sở hữu đúng nghiệp vụ, dễ import và không gây xung đột/nhập nhằng với annotation khác?
9. **Kế thừa và lặp:** có cần `@Inherited` hay `@Repeatable` không, và nếu có thì semantic của việc kế thừa/kết hợp đã được định nghĩa?
10. **Tính ổn định:** public consumers có phụ thuộc tên/type/element không; nếu đổi tên thì migration như thế nào?
11. **Khả năng xác thực:** phần tử nào có thể được compiler kiểm tra theo kiểu, phần tử nào cần framework/processer kiểm tra quy tắc nghiệp vụ?
12. **Ví dụ chứng minh:** có ví dụ hợp lệ và trường hợp annotation không được tiêu thụ để xác nhận điều gì thực sự xảy ra không?

**Kết luận:** Tên annotation tốt phải biểu đạt **nghĩa của metadata** thay vì chỉ trông như một lệnh gọi phương thức. Chọn tên theo **sự thật, quan hệ, điều kiện hay cấu hình** mà annotation công bố; đặt tên element rõ đơn vị và vai trò; giữ `@Target`, `@Retention`, package và bộ xử lý nhất quán với lời hứa đó. Trong Java, **metadata không tự làm phát sinh hành vi**: tên chuẩn xác giúp con người và công cụ hiểu hợp đồng, còn logic tiêu thụ mới quyết định hệ thống thực hiện điều gì.
