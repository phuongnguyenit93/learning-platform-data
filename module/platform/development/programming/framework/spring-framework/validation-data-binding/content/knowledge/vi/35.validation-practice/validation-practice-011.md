# Đối chiếu kết quả với Javadoc và tài liệu đúng phiên bản Spring

## 1. Bài thực hành: khi kết quả chạy khác ví dụ trên mạng

Trong Spring Framework, một tên phương thức tồn tại trong Javadoc chưa đủ để kết luận nó có hành vi như ta tưởng. Cần biết **phiên bản thực đang chạy**, **lớp/cơ chế đang xử lý request**, **điều kiện áp dụng** và **mức bảo đảm của tài liệu**.

Ví dụ trong module Spring Framework – validation/data-binding:

- Bạn gửi form có `approved=true` nhưng thấy field bị bỏ qua. Có phải `@Valid` đã chặn nó?
- Gọi `DataBinder#setAllowedFields("name")`, nhận `getSuppressedFields()` chứa `"approved"`, nhưng `hasErrors()` vẫn false. Có phải bug?
- Bật `setDeclarativeBinding(true)` rồi gọi `bind(...)`, các setters không được gọi. Điều này có áp dụng luôn cho constructor binding hay không?
- Đổi `setAutoGrowCollectionLimit(4)` mà một List nhận từ constructor vẫn lớn hơn 4. Vì sao?
- `@Valid @RequestBody` sinh `MethodArgumentNotValidException`, còn `@Min` đặt trực tiếp trên `@RequestParam` lại sinh `HandlerMethodValidationException`. Vì sao?
- Mã trên blog nói “method đó chưa có”, nhưng project của bạn lại compile được. Blog đã dùng Spring Framework 5.3, 6.0, 6.1, 6.2 hay 7.0?

Mục tiêu thực hành là tạo **bằng chứng tái hiện được**, rồi đối chiếu với **Javadoc và Reference Guide đúng phiên bản**. Ta không chọn tài liệu chỉ vì nó đứng đầu kết quả tìm kiếm; cũng không tuyên bố một kết quả thử nghiệm ngẫu nhiên là hợp đồng ổn định của Spring.

Sau bài này, bạn có thể:
1. Xác định Spring Boot và Spring Framework **resolved versions**, tránh nhầm hai hệ phiên bản.
2. Đọc chính xác chữ ký, `Since`, default, precondition, scope, warning và exception của một API trong Javadoc theo đúng **patch**.
3. Sử dụng Reference Guide **đúng major/minor** và biết khi nào bản hiển thị đã dịch sang patch mới hơn.
4. Viết unit test `DataBinder` để kiểm tra `allowedFields`, `suppressedFields`, `declarativeBinding` và lỗi conversion.
5. Viết MockMvc tests cho `@ModelAttribute`, `@RequestBody`, Bean Validation và handler method validation.
6. Phân biệt **điều Javadoc cam kết** với kết quả phụ thuộc version/configuration/implementation.
7. Lập bảng traceability: **nhận định → tài liệu → phiên bản → test → kết quả thực tế → quyết định**.
8. Ghi báo cáo có thể dùng trong pull request hoặc khi nâng cấp Spring.

**Phạm vi:** Java 17+, Spring Boot **3.5.6** và Spring Framework **6.2.11** làm baseline cố định của project mẫu; Spring MVC Servlet stack, Jakarta Validation, Spring Test. Không sử dụng snippet API của Spring Framework 7 để kết luận cho project chạy Spring 6.

## 2. Quy tắc số một: Boot version khác Framework version

### 2.1. Hai version numbers không giống nhau

Một `pom.xml` có:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
</parent>
```

**Không** có nghĩa `org.springframework.validation.DataBinder` thuộc “Spring Framework 3.5.6”. Spring Boot quản lý một bộ dependencies, trong đó các module Spring Framework có phiên bản riêng.

Với artifact gốc của **Spring Boot 3.5.6**, Maven Central ghi:
- `org.springframework:spring-core:6.2.11`.
- `org.springframework:spring-web:6.2.11`.
- `org.springframework:spring-webmvc:6.2.11`.

Nguồn kiểm tra:
- [Maven Central — spring-boot-starter-web 3.5.6](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-web/3.5.6).
- [Spring Framework 6.2.11 release announcement](https://spring.io/blog/2025/09/11/spring-framework-6-2-11-available%20now/), nêu phiên bản này được dùng với Boot 3.5.6.
- [Spring Boot 3.5.6 release announcement](https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now/).

Đây là **baseline chính thức**. Một ứng dụng thật có thể override `spring-framework.version`, dùng BOM khác, áp dependency management riêng, đóng gói nhiều jars hoặc chịu xung đột classpath. Vì vậy vẫn phải xác minh phiên bản **thực resolved và loaded**.

### 2.2. Cách kiểm tra Maven resolved versions

Tại thư mục project:

```bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework
mvn help:evaluate -Dexpression=spring-framework.version -DforceStdout
mvn help:effective-pom -Doutput=target/effective-pom.xml
```

Kiểm tra:
- `mvn -version`: Maven và Java runtime version.
- `dependency:tree`: những `org.springframework:*` jars được resolve, scope và đường dependency mang vào.
- `help:evaluate`: property `spring-framework.version` trong effective Maven model nếu được cung cấp.
- `effective-pom`: dependency management và plugin configuration thực sự sau inheritance/profiles.

**Đừng tự bịa output đầy đủ** của `dependency:tree`. Một **trích dẫn minh họa** cần tìm trong project baseline là:

```text
org.springframework:spring-core:jar:6.2.11
org.springframework:spring-web:jar:6.2.11
org.springframework:spring-webmvc:jar:6.2.11
```

Cây dependencies đầy đủ sẽ có thêm scope, parent path và thứ tự khác nhau. Khi báo cáo lỗi, đính kèm output thực tế của chính project chạy test.

Đối với Windows PowerShell, khi shell xử lý dấu hoặc property arguments không như mong muốn, có thể đặt một `-D...` vào dấu ngoặc kép:

```powershell
mvn dependency:tree "-Dincludes=org.springframework"
mvn help:evaluate "-Dexpression=spring-framework.version" "-DforceStdout"
```

### 2.3. Gradle không dùng lệnh Maven

Với project Gradle, dùng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Windows có thể dùng `gradlew.bat`. Đừng đọc POM Maven rồi kết luận dự án Gradle cũng nhận chính xác versions đó nếu có platforms, resolutionStrategy, constraints hoặc dependency locking riêng.

### 2.4. Kiểm tra runtime version

Spring cung cấp:

```java
import org.springframework.core.SpringVersion;

System.out.println(SpringVersion.getVersion());
```

Trong bản build Maven mẫu, kết quả dự kiến là:

```text
6.2.11
```

`SpringVersion.getVersion()` có thể trả null trong một số môi trường chạy không có implementation version metadata. Đối với ứng dụng Maven đóng gói jars chuẩn của ví dụ, test assert đúng **6.2.11**. Nếu một dự án tự repackaging/shading không giữ metadata, cần kiểm tra zusätzlich `Package.getImplementationVersion()`, `CodeSource` và file jar thực tế.

**Nguyên tắc:** phiên bản resolved ở build và phiên bản class thực sự loaded trong runtime cần nhất quán; nếu lệch, phải điều tra classpath, plugin, container hoặc multiple classloaders.

## 3. Chọn đúng nguồn tài liệu — thứ tự ưu tiên

Một quy trình review có thể dùng thứ tự:

1. **Javadoc theo patch đúng**: chữ ký, tham số, return, `Since`, defaults, preconditions, giới hạn.
2. **Reference Guide đúng nhánh**: cách các API ghép với nhau trong Spring MVC, Servlet/WebFlux, validation và data binding.
3. **Release notes/change log theo release/tag**: API thay đổi và bug fix giữa patches.
4. **Source code tại tag đúng**: khi docs chưa giải thích một edge case, xác minh implementation chính xác.
5. **Minimal reproduction tests** dùng dependency versions đã xác minh.
6. Blog/Stack Overflow/video: nguồn tham khảo và giả thuyết, **không** thay bằng chứng versioned.

Không được đảo thứ tự để “lấy test pass rồi tìm một đoạn blog hợp ý”.

### 3.1. Javadoc exact patch 6.2.11

Các đường dẫn cụ thể:

- [DataBinder — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/DataBinder.html)
- [BindingResult — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/BindingResult.html)
- [FieldError — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/FieldError.html)
- [WebDataBinder — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [HandlerMethodValidationException — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [ResponseEntityExceptionHandler — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)

Trên trang Javadoc, kiểm tra banner ghi **Spring Framework 6.2.11 API**, không phải chỉ nhìn phần cuối URL. Với mỗi method, đọc **Method Details**, không chỉ Method Summary.

**Tính chính xác về đường link:** Nếu một trang Javadoc cụ thể tạm không được công cụ tìm kiếm lập chỉ mục, hãy mở index Javadoc của chính release [6.2.11](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/) rồi duyệt theo package. Không tự chuyển qua “current” và âm thầm đổi patch.

### 3.2. Reference Guide nhánh 6.2 có thể được cập nhật theo patch mới hơn

Các đường dẫn:

- [Spring Framework — Data Binding, nhánh 6.2](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework — @InitBinder, nhánh 6.2](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — @ModelAttribute, nhánh 6.2](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC validation, nhánh 6.2](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Spring MVC MockMvc](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html)

**Bẫy:** `/reference/6.2/...` cố định **minor series**, nhưng phần đầu trang có thể hiển thị một **6.2.x patch mới hơn**. Tại thời điểm đối chiếu cho ví dụ này, một số trang nhánh 6.2 đang hiển thị 6.2.19 trong khi baseline Maven là **6.2.11**.

Vì thế:
- Dùng Reference Guide 6.2 để hiểu **kiến trúc và khuyến nghị**.
- Dùng Javadoc **6.2.11** để kiểm tra API contract đúng binary.
- Khi có mâu thuẫn nghi ngờ do fix giữa patches, đối chiếu source tag `v6.2.11` và release notes, sau đó chạy test baseline.
- Không ghi “Reference Guide nhánh 6.2 chính là snapshot 6.2.11” nếu banner hiển thị patch khác.

### 3.3. Source tại Git tag chính xác

- [Spring Framework source tag v6.2.11](https://github.com/spring-projects/spring-framework/tree/v6.2.11).
- [Spring Boot source tag v3.5.6](https://github.com/spring-projects/spring-boot/tree/v3.5.6).

Ví dụ tra `DataBinder`:
1. Vào tag `v6.2.11`, không dùng nút “main” mặc định.
2. Chọn module `spring-context` và package `org.springframework.validation`.
3. Đọc `DataBinder.java`, method `setDeclarativeBinding` và flow của `bind(PropertyValues)`/`construct(ValueResolver)`.
4. Nếu behavior phụ thuộc MVC, theo call-site trong `spring-webmvc`.
5. Nếu muốn trích điều gì là **public contract**, vẫn lấy Javadoc làm gốc; implementation chỉ làm sáng tỏ behavior của đúng tag.

**Khi so sánh patches** 6.2.11 với 6.2.19, dùng Git diff giữa tags và changelog thay vì suy đoán rằng khác patch = khác semantics.

## 4. Cách đọc một Javadoc method theo checklist

Với bất kỳ API nào, ghi lại:

| Trường | Câu hỏi cụ thể |
| --- | --- |
| Class/package/module | API thuộc `spring-context`, `spring-web` hay `spring-webmvc`? |
| Declaration | Tên, visibility, argument types, generics, annotations? |
| `Since` | Method xuất hiện từ Framework version nào? |
| Defaults | Giá trị mặc định có thể khác kỳ vọng không? |
| Applies to | Setter/property, constructor, form, JSON, Servlet hay WebFlux? |
| Preconditions | Có cần target object, conversion service, validator, model attribute name? |
| Return/side effects | Thay state trên binder, target, BindingResult hay exception? |
| Exceptions | Argument conversion, binding, method validation hay exception từ user constructor? |
| Security | Có cảnh báo exposed object graph hoặc mass assignment? |
| “See Also” | API nào cần đọc cùng để hiểu ngữ cảnh? |
| Version links | Javadoc đúng patch, Guide đúng minor, source tag đúng release? |
| Test evidence | Test nào chứng minh ý đang nêu và có thể chạy lại? |

Ví dụ không đủ tốt:

> “`setAutoGrowCollectionLimit(4)` bảo đảm mọi List nhận từ request có tối đa bốn phần tử.”

Nhận định này quá rộng. Javadoc **6.2.11** nói đây là giới hạn cho auto-grow của collection khi **setter/field property binding**, đồng thời ghi rõ nó **không áp dụng** cho `construct(ValueResolver)`. Cần sửa thành:

> “`setAutoGrowCollectionLimit(4)` giới hạn auto-grow array/collection trong đường `bind(PropertyValues)`; không được dùng nó như một quota tổng quát cho constructor binding hoặc request body.”

Đây là ví dụ điển hình của **đọc cả đoạn "Used for..."**, không chỉ phần summary.

## 5. Đối chiếu cụ thể 1: `setAllowedFields` và suppressed fields

### 5.1. Javadoc 6.2.11 nói gì?

`DataBinder#setAllowedFields(String... allowedFields)`:
- Đăng ký patterns của các fields được phép bind.
- Mặc định cho phép các fields.
- Có mục đích tránh modifications không mong muốn từ dữ liệu HTTP do client cung cấp.

`BindingResult#getSuppressedFields()`:
- Trả về danh sách fields bị suppress trong quá trình binding.

**Không có lời cam kết** rằng mọi field bị suppress phải trở thành `FieldError`. Nếu ứng dụng cần **reject** request chứa field ngoài allowlist, phải kiểm tra suppressed fields riêng.

### 5.2. Mô hình thử nghiệm

Một JavaBean:

```java
public class AuditForm {
    private String name;
    private Integer seats;
    private boolean approved;
    // getters và setters
}
```

Một binder:

```java
AuditForm form = new AuditForm();
DataBinder binder = new DataBinder(form, "auditForm");
binder.setAllowedFields("name", "seats");

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Mai");
values.add("seats", "2");
values.add("approved", "true");

binder.bind(values);
```

Đây là đoạn trích từ project đầy đủ ở phần 12. Kỳ vọng:
- `form.getName()` là `Mai`.
- `form.getSeats()` là Integer 2.
- `form.isApproved()` vẫn false.
- `getSuppressedFields()` chứa `approved`.
- `hasErrors()` có thể false nếu các giá trị đã được bind hợp lệ.

**Suy luận đúng:** Allowlist hoạt động và có dấu vết suppression. **Suy luận sai:** Bean Validation đã từ chối `approved`; riêng `@Valid`/`@NotBlank` không phải cơ chế đặt field allowlist.

### 5.3. So khớp Javadoc → test → kết luận

| Nhận định | Tài liệu 6.2.11 | Test cần chạy | Kết luận kỳ vọng |
| --- | --- | --- | --- |
| Mặc định `DataBinder` có thể gọi setter không được liệt kê | `setAllowedFields`: default all fields | Test bind `approved=true` khi không có allowlist | `approved=true` |
| Allowed-fields chặn property ngoài danh sách | `setAllowedFields` + `bind` | Bind name,seats,approved với allowlist | Approved vẫn false |
| Field bị chặn ghi vào result | `BindingResult#getSuppressedFields` | Assert suppressed array chứa approved | Có suppressed field |
| Suppression không nhất thiết là validation error | `BindingResult` và `FieldError` là kết cấu khác | Assert `hasErrors()==false` cho input còn lại hợp lệ | Có thể true với suppression nhưng không có FieldErrors |
| Chuyển sai kiểu tạo binding error | `DataBinder` lỗi `typeMismatch` | Bind `seats=abc` | FieldError.bindingFailure=true |

Không tự dùng các rows này như **kết quả Maven đã chạy**. Đó là **expected assertions**; evidence thật chỉ xuất hiện sau khi thực thi test suite.

## 6. Đối chiếu cụ thể 2: `setDeclarativeBinding(true)`

### 6.1. Phiên bản và phạm vi

Javadoc `DataBinder#setDeclarativeBinding(boolean)` trong **6.2.11**:
- `Since: 6.1`.
- Default là `false`.
- `true` giới hạn binding vào constructor arguments qua `construct(...)`, và vào properties được phép khi có `allowedFields`.

Nghĩa là:
- Chỉ gọi `setDeclarativeBinding(true)` rồi `bind(PropertyValues)` trên một mutable bean, **không** khai báo `allowedFields`, thường **không thực hiện** property binding.
- Nếu khai báo `setAllowedFields("name")`, property binding cho name có thể tiếp tục.
- Khi khai báo constructor argument tên `approved`, `allowedFields` **không phải** bộ lọc chung cho argument đó.

### 6.2. Hai test phải tách riêng

```java
// A: declarative binding nhưng không có allowedFields
binder.setDeclarativeBinding(true);
binder.bind(values);
// Property setters không được gọi theo cơ chế đã mô tả.

// B: declarative binding + explicit property allowlist
binder.setDeclarativeBinding(true);
binder.setAllowedFields("name");
binder.bind(values);
// Chỉ setter/property name được phép.
```

**Đừng dùng một thử nghiệm constructor binding rồi kết luận cả `bind(PropertyValues)` có hành vi giống vậy.** Các phương thức có đầu vào và phạm vi khác nhau.

### 6.3. Khác biệt với tài liệu 5.3/6.0

`setDeclarativeBinding` có `Since 6.1`. Một bài blog Spring 5.3 không đề cập API này không chứng minh API **không tồn tại** trong 6.2.11. Ngược lại, nếu project thực đang dùng 6.0.x, việc copy method từ Javadoc 6.2 sẽ gây compile error.

Khi thấy `cannot find symbol: setDeclarativeBinding`:
1. Kiểm tra import đúng `org.springframework.validation.DataBinder`/`org.springframework.web.bind.WebDataBinder`.
2. Kiểm tra effective Framework version.
3. Kiểm tra IDE compile classpath so với Maven build classpath.
4. Mở **Javadoc của chính version resolved**, tìm `Since`.
5. Không sửa bằng cách khai báo method giả cùng tên trên DTO.

## 7. Đối chiếu cụ thể 3: `setAutoGrowCollectionLimit`

### 7.1. Điều được tài liệu cam kết

Trong Javadoc 6.2.11:
- `DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` là **256**.
- `setAutoGrowCollectionLimit(int)` điều chỉnh giới hạn auto-growing của array/collection.
- `setAutoGrowNestedPaths(boolean)` điều chỉnh việc tự khởi tạo nested path null.
- **Cả hai** được Javadoc ghi chú dùng cho **setter/field injection qua `bind(PropertyValues)`**, **không** áp dụng cho constructor binding qua `construct(ValueResolver)`.

Đây là **giới hạn phạm vi API chính thức**, không chỉ một nhận định từ source implementation.

### 7.2. Test đơn giản

```java
DataBinder binder = new DataBinder(new AuditForm());

assertEquals(
        DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT,
        binder.getAutoGrowCollectionLimit());

assertEquals(256, binder.getAutoGrowCollectionLimit());
```

Test này chứng minh default trên bản baseline. Nó **không** chứng minh mọi HTTP body/Map/List đều bị giới hạn bởi 256.

### 7.3. Vì sao nên phân biệt “default” với “bảo mật”

Một giới hạn auto-grow:
- Không phải kích thước tối đa của tất cả collections trong Java object.
- Không phải số parameter tối đa của Servlet container.
- Không phải kích thước JSON request body.
- Không phải giới hạn số Map keys.
- Không thay thế allowlist, quota, input schema hoặc authorization.
- Không tự giới hạn các collection được tạo bằng constructor binding.

Khi thực hành với index rất lớn, dùng **giá trị nhỏ được kiểm soát**, không tạo request hàng triệu phần tử trong CI hoặc máy dùng chung. Bài này ưu tiên chứng minh **phạm vi documented**, không chạy stress test thiếu bảo vệ.

## 8. Đối chiếu cụ thể 4: Validation trong MVC

### 8.1. Theo Reference Guide Spring MVC 6.2

Hai đường thường gặp:
- Bean Validation áp dụng riêng cho `@ModelAttribute`/`@RequestBody` có `@Valid` mà **không có direct method constraint** yêu cầu method validation: có thể tạo `MethodArgumentNotValidException` nếu không có `BindingResult` để xử lý.
- Constraint đặt **trực tiếp** trên handler parameter, ví dụ `@RequestParam("page") @Min(1) int page`: Spring MVC 6.1+ có built-in **method validation**, thường tạo `HandlerMethodValidationException`.

Javadoc `HandlerMethodValidationException` 6.2.11 nói status **400** khi input validation fail, status **500** khi **return value** không hợp lệ.

**Lưu ý:** Một controller có class-level `@Validated` có thể đi qua AOP method validation. Để quan sát built-in MVC 6.1+ như bài này, không đặt `@Validated` lên controller class. Với handler có nhiều constraints và argument resolvers khác nhau, exception routing có thể khác; test thực tế quyết định expected contract.

### 8.2. Vì sao không chỉ assert HTTP 400

Một test chỉ assert 400 không phân biệt:
- Thiếu query parameter.
- Query text không convert được thành Integer.
- `@Min(1)` trực tiếp vi phạm.
- `@Valid @RequestBody` DTO vi phạm constraint.
- JSON body không đọc được.
- Form property binding trả `FieldError`.

Cần kết hợp:
1. `MockMvc` và resolved exception type khi mục đích là xác nhận **framework path**.
2. HTTP status và JSON error code khi mục đích là xác nhận **public API contract**.
3. Javadoc/Reference Guide đúng version để giải thích vì sao path đó xảy ra.

### 8.3. Validation failures khác binding failures

Trong `DataBinder`, `BindingResult.FieldError.isBindingFailure()` phân biệt lỗi setter/conversion với constraint error. Ví dụ:
- `seats=abc`: String→Integer conversion fail; lỗi `typeMismatch`.
- `seats=0`: parse thành Integer 0, nhưng `@Min(1)` fail khi validator chạy.
- `approved=true` ngoài `allowedFields`: suppression; không nhất thiết có `FieldError`.

Khi viết README hoặc PR, không dùng “validation failed” cho tất cả trường hợp 400; mô tả chính xác giai đoạn.

## 9. Đọc `@ModelAttribute` và `@RequestBody` theo đúng stack

### 9.1. Spring MVC form/query

`@ModelAttribute` trong MVC có thể dùng constructor binding, property binding hoặc kết hợp. `@InitBinder` có thể cấu hình `WebDataBinder` cho named model attribute. Form/query values thường đi qua `ConversionService`/formatters.

Một negative test suppression được thực hiện với:

```java
@InitBinder("auditForm")
void bindAuditForm(WebDataBinder binder) {
    binder.setAllowedFields("name", "seats");
}
```

Đây là cấu hình **property binding allowlist**, không phải Jakarta Validation constraint và không phải JSON deserializer schema.

### 9.2. `@RequestBody` JSON

`@RequestBody` thường được đọc bằng Jackson qua `HttpMessageConverter`. `@Valid` vẫn có thể áp validation sau deserialize, nhưng `WebDataBinder#setAllowedFields` **không** kiểm soát Jackson field deserialization theo cách property binding của form.

Một thay đổi ví dụ như:

```java
public record AuditPayload(
        @NotBlank String title,
        @NotNull @Min(1) Integer quantity) {}
```

được Jackson tạo từ JSON:

```json
{"title":"Book","quantity":2}
```

Lỗi `{"quantity":{"not":"an integer"}}` xảy ra ở **JSON decoding**, khác `@Min(1)` khi quantity là 0. Trước khi áp “cách sửa của @ModelAttribute” sang JSON, kiểm tra đúng tài liệu `@RequestBody` và test ở tầng Jackson.

## 10. Thiết kế bảng đối chiếu có thể audit

Mẫu bảng kết quả cho một nhóm:

| ID | Claim | Version thực | Evidence link | Test & input | Expected | Observed | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DB-01 | Default property binder có thể nhận setter approved | 6.2.11 | `DataBinder#setAllowedFields` | approved=true, không allowlist | approved true | Ghi sau khi chạy | PENDING |
| DB-02 | Allowlist suppress approved | 6.2.11 | `DataBinder#setAllowedFields` | approved=true, allowlist name,seats | approved false, suppressed | Ghi sau khi chạy | PENDING |
| DB-03 | Suppression không tự tạo FieldError | 6.2.11 | `BindingResult#getSuppressedFields` | values hợp lệ + approved=true | hasErrors false | Ghi sau khi chạy | PENDING |
| DB-04 | Declarative binding tắt property binding ngoài allowedFields | 6.2.11 | `DataBinder#setDeclarativeBinding` | declarative=true, no allowlist | target chưa đổi | Ghi sau khi chạy | PENDING |
| DB-05 | Auto-grow default là 256 | 6.2.11 | `DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` | new DataBinder | 256 | Ghi sau khi chạy | PENDING |
| MV-01 | Invalid `@Valid @RequestBody` dùng argument validation | 6.2.11 | MVC validation Guide | title="" | MethodArgumentNotValidException/400 | Ghi sau khi chạy | PENDING |
| MV-02 | Direct `@Min` dùng method validation | 6.2.11 | HandlerMethodValidationException Javadoc | page=0 | 400 | Ghi sau khi chạy | PENDING |
| MV-03 | Invalid return value là server error | 6.2.11 | HandlerMethodValidationException Javadoc | broken return null | 500 | Ghi sau khi chạy | PENDING |
| JV-01 | Malformed JSON không phải Bean Validation | 6.2.11 | `HttpMessageConverter`/Jackson path | malformed JSON | HttpMessageNotReadable/400 | Ghi sau khi chạy | PENDING |

**PENDING** là nhãn minh họa **bên trong tài liệu thực hành**, không phải tiến độ của worker hoặc trạng thái Sheet. Khi học viên chạy Maven, ghi output thật vào bản báo cáo riêng, không sửa Javadoc để khớp giả thuyết.

### 10.1. Mỗi claim phải có điều kiện đủ

Không viết: “`HandlerMethodValidationException` luôn được ném khi có `@Valid`.”

Nên viết:
- “Với Spring MVC 6.2.11, trong controller **không có class-level @Validated**, direct `@Min` trên handler parameter dùng built-in method validation; test `/audit/page?page=0` xác nhận exception path.”
- “Với `@Valid @RequestBody` không có direct method constraint khác, request JSON được decode thành DTO rồi validate; test `/audit/json` với title blank xác nhận argument validation path.”

Có **scope + version + setup + input** giúp kết luận có thể tái hiện.

### 10.2. Phân biệt ba loại kết luận

1. **Documented contract:** Javadoc nói rõ, ví dụ `Since: 6.1` hoặc auto-grow áp dụng cho property binding.
2. **Verified behavior under setup:** test của bạn pass khi chạy Boot3.5.6 + Spring6.2.11 với config cụ thể.
3. **Implementation detail:** quan sát source/call stack hiện tại nhưng không có public guarantee cho mọi patch.

Đừng nâng level (3) thành một promise public API chỉ vì test pass.

## 11. Quy trình khi “tài liệu nói một đằng, test chạy một nẻo”

### Bước 1 — Ghi lại hypothesis bằng một câu kiểm chứng được

Ví dụ:

> “Với Framework 6.2.11, khi `setDeclarativeBinding(true)` mà không có `allowedFields`, gọi `DataBinder.bind(...)` trên JavaBean không ghi vào setters.”

Không viết “Spring binding bị lỗi”.

### Bước 2 — Khóa môi trường và inputs

Ghi:
- Java vendor và version, Maven/Gradle version.
- Boot parent/BOM version.
- `dependency:tree` resolved Framework modules.
- `SpringVersion.getVersion()` runtime.
- Test context: MVC Servlet, WebFlux, no context hoặc full ApplicationContext.
- DTO types/annotations, input field paths, locale, charset và timezone nếu liên quan.

### Bước 3 — Chọn Javadoc của đúng patch

Với `DataBinder`, link `.../docs/6.2.11/javadoc-api/...`. Đọc Method Details của `setDeclarativeBinding`, `bind`, `setAllowedFields` và `getBindingResult`; không dừng ở một chữ ký method.

### Bước 4 — So Reference Guide cho đúng thế hệ

Chọn Spring 6.2 Reference, xác nhận banner patch đang hiển thị. Nếu nó đang hiện 6.2.19, ghi chú “reference của series 6.2; exact Javadoc/source kiểm bằng 6.2.11”.

### Bước 5 — Tạo minimal reproduction

Tách:
- **Pure DataBinder test**: không ApplicationContext, kiểm tra API behavior độc lập MVC.
- **MockMvc integration**: xác nhận argument resolver/validator/advice thực tế.
- **Build/runtime evidence**: xác nhận dependency metadata.

Nếu chỉ chạy MockMvc, khó biết lỗi nằm ở binder hay MVC configuration. Nếu chỉ gọi DataBinder, không biết Spring MVC thực sự chọn đường binding nào.

### Bước 6 — Ghi actuals, không điều chỉnh expected cho pass

Nếu test fail:
1. Copy assertion failure, resolved exception type và dữ liệu debug đã sanitize.
2. Đối chiếu runtime version, dependency conflicts và annotation imports.
3. Truy tìm source call path tại tag.
4. Nếu behavior khác documented contract, tạo reproducible issue/test tối thiểu và liên hệ maintainers.
5. Nếu Javadoc của patch đã nói rõ khác giả thuyết, **sửa giả thuyết và code**, không sửa framework.

### Bước 7 — Ghi verdict có phạm vi

- **PASS:** behavior và docs trùng nhau trong điều kiện đã ghi.
- **EXPECTED DIFFERENCE:** docs scope khác setup (ví dụ constructor vs property).
- **VERSION MISMATCH:** đang đọc wrong major/minor/patch.
- **BLOCKED:** thiếu dependency tree, không chạy được test hoặc thiếu logs.
- **POSSIBLE FRAMEWORK DEFECT:** đã tối giản repro, đúng patch và vẫn mâu thuẫn với documented contract.

Một failure đơn lẻ không đủ để kết luận Spring có defect.

## 12. Dự án Java 17 + Spring Boot 3.5.6 để tự tái hiện

Dự án mẫu cố ý nhỏ và tập trung vào các điều cần đối chiếu với Javadoc. Nó không phụ thuộc database, login hay external API. Phần production/demo có:
- Một mutable input bean để quan sát property binding và suppression.
- Một JSON request record để quan sát Bean Validation qua Jackson.
- Một controller dùng `@InitBinder`, `@ModelAttribute`, `@RequestParam @Min` và `@RequestBody`.
- Một `ResponseEntityExceptionHandler` để ổn định error envelope.
- Ba JUnit test classes cho version/Javadoc API, raw DataBinder và MockMvc.

**Không có chuyện “Spring Framework 6.2.11 = Spring Boot 6.2.11”.** Maven parent là Boot 3.5.6, các Spring Framework jars resolved là 6.2.11 theo dependency management của release này.

### 12.1. Cấu trúc

```text
spring-version-evidence/
├── pom.xml
├── src/main/java/demo/verify/
│   ├── VersionEvidenceApplication.java
│   ├── AuditForm.java
│   ├── AuditPayload.java
│   ├── AuditError.java
│   ├── AuditController.java
│   └── AuditAdvice.java
└── src/test/java/demo/verify/
    ├── VersionEvidenceTest.java
    ├── DataBinderEvidenceTest.java
    └── MvcEvidenceTest.java
```

### 12.2. `pom.xml` — nguyên vẹn, không override Spring Framework

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>spring-version-evidence</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-validation` là điều kiện quan trọng để test `@Valid` và `@Min` chạy qua Jakarta Validation provider. Không thêm trực tiếp `spring-webmvc:7.x` vào project. Khi nâng cấp, sửa một nơi là Boot parent/BOM rồi chạy lại cả dependency tree và test suite.

### 12.3. `VersionEvidenceApplication.java`

```java
package demo.verify;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VersionEvidenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionEvidenceApplication.class, args);
    }
}
```

### 12.4. `AuditForm.java` — bean mutable để quan sát data binding

```java
package demo.verify;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class AuditForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(1)
    private Integer seats;

    // Cố ý expose để test chứng minh over-posting risk.
    private boolean approved;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public boolean isApproved() {
        return approved;
    }

    public void setApproved(boolean approved) {
        this.approved = approved;
    }
}
```

**Production note:** Input DTO thật không nên có setter `approved`. Tệp này có nó **cố ý** để so sánh default property binding và allowlisted binding. Ứng dụng thực nên tách server-owned state khỏi request input ngay từ thiết kế lớp.

### 12.5. `AuditPayload.java` — JSON DTO

```java
package demo.verify;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AuditPayload(
        @NotBlank String title,
        @NotNull @Min(1) Integer quantity) {
}
```

Record được Jackson tạo từ JSON. `@Valid` trên handler argument kích hoạt Bean Validation sau khi đọc body. Điều này **khác** `DataBinder#setAllowedFields` cho form.

### 12.6. `AuditError.java` — hợp đồng response tối giản

```java
package demo.verify;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

import java.util.List;

public record AuditError(
        String code,
        List<String> fields) {

    public static AuditError simple(String code) {
        return new AuditError(code, List.of());
    }

    public static AuditError fromBindingResult(BindingResult errors) {

        boolean bindingFailure = errors.getFieldErrors()
                .stream()
                .anyMatch(FieldError::isBindingFailure);

        List<String> fields = errors.getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new AuditError(
                bindingFailure
                        ? "BINDING_ERROR"
                        : "VALIDATION_ERROR",
                fields);
    }
}
```

Hợp đồng demo không phản chiếu raw rejected values, exception messages hoặc stack traces. Nếu có object-level errors trong ứng dụng thật, cần map `getGlobalErrors()`; ví dụ này chỉ khai báo field-level Jakarta constraints.

### 12.7. `AuditController.java` — các đường MVC tách biệt

```java
package demo.verify;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.core.SpringVersion;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestController
@RequestMapping("/audit")
public class AuditController {

    @InitBinder("auditForm")
    void restrictForm(WebDataBinder binder) {
        binder.setAllowedFields("name", "seats");
    }

    @GetMapping("/version")
    public Map<String, String> version() {
        return Map.of(
                "springFramework",
                Objects.toString(
                        SpringVersion.getVersion(), "unknown"));
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("auditForm") AuditForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(AuditError.simple("SUPPRESSED_FIELDS"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(AuditError.fromBindingResult(errors));
        }

        return ResponseEntity.ok(Map.of(
                "name", form.getName(),
                "seats", form.getSeats(),
                "approved", form.isApproved()));
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> json(
            @Valid @RequestBody AuditPayload payload) {

        return ResponseEntity.ok(Map.of(
                "title", payload.title(),
                "quantity", payload.quantity()));
    }

    @GetMapping("/limit")
    public Map<String, Integer> limit(
            @RequestParam("limit") Integer limit) {

        return Map.of("limit", limit);
    }

    @GetMapping("/page")
    public Map<String, Integer> page(
            @RequestParam("page") @Min(1) int page) {

        return Map.of("page", page);
    }

    @NotNull
    @GetMapping("/broken-return")
    public String brokenReturn() {
        // Fixture cố ý vi phạm return-value contract.
        return null;
    }
}
```

**Chú thích testability:**
- `@InitBinder("auditForm")` chỉ nhắm đúng model attribute name của form.
- `BindingResult` nằm **ngay sau** `AuditForm`.
- `getSuppressedFields()` kiểm tra riêng trước `hasErrors()`.
- `/json` dùng `@Valid @RequestBody`, không có direct method constraint trên parameter.
- `/page` dùng direct `@Min(1)` và không đặt class-level `@Validated`.
- `/broken-return` là fixture test **cố tình sai**, không dùng trong production. Javadoc `HandlerMethodValidationException` xác định lỗi return value thành HTTP 500.

Nếu dùng Spring Security, phải cung cấp authenticated test request phù hợp thay vì vô hiệu hóa security chỉ để biến 401/403 thành 400. Project demo không khai báo Spring Security dependency.

### 12.8. `AuditAdvice.java` — đọc đúng chữ ký `ResponseEntityExceptionHandler`

```java
package demo.verify;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.List;

@RestControllerAdvice
public class AuditAdvice extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> reply(
            HttpHeaders headers,
            HttpStatusCode status,
            AuditError body) {

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                AuditError.fromBindingResult(ex.getBindingResult()));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                AuditError.simple("BODY_UNREADABLE"));
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                new AuditError(
                        "MISSING_PARAMETER",
                        List.of(ex.getParameterName())));
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (status.is5xxServerError()) {
            return reply(headers, status,
                    AuditError.simple("SERVER_CONVERSION_ERROR"));
        }

        String field =
                ex instanceof MethodArgumentTypeMismatchException mismatch
                        ? mismatch.getName()
                        : "parameter";

        return reply(headers, status,
                new AuditError("TYPE_MISMATCH", List.of(field)));
    }

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                AuditError.simple(
                        ex.isForReturnValue()
                                ? "RETURN_VALIDATION_ERROR"
                                : "METHOD_VALIDATION_ERROR"));
    }
}
```

Chính xác với Spring Framework 6.2.11, các override dạng trên nhận `HttpStatusCode` và `WebRequest`. Nếu copy một method signature từ major khác mà IDE báo “method does not override or implement a method from a supertype”, hãy kiểm:
1. Import exception đúng package.
2. Javadoc `ResponseEntityExceptionHandler` của **resolved Spring Framework patch**.
3. `@Override` cùng chữ ký, thứ tự args và visibility.
4. Không tự thêm một `@ExceptionHandler` trùng với mapping đã có ở superclass.

**Vì sao không ép mọi thứ về 400?** `HandlerMethodValidationException` phân biệt input vs return value. Demo bảo toàn `status` do Spring chuyển vào, tránh biến lỗi server thành lỗi client.

## 13. Bằng chứng JUnit: phiên bản và API signatures

### 13.1. `VersionEvidenceTest.java`

```java
package demo.verify;

import org.junit.jupiter.api.Test;
import org.springframework.core.SpringVersion;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class VersionEvidenceTest {

    @Test
    void runtimeSpringFrameworkVersionMatchesManagedBaseline() {
        assertEquals("6.2.11", SpringVersion.getVersion());
    }

    @Test
    void dataBinderApisExistWithDocumentedSignatures()
            throws Exception {

        assertNotNull(DataBinder.class.getMethod(
                "setDeclarativeBinding", boolean.class));
        assertNotNull(DataBinder.class.getMethod(
                "setAllowedFields", String[].class));
        assertNotNull(DataBinder.class.getMethod(
                "setAutoGrowCollectionLimit", int.class));
        assertNotNull(BindingResult.class.getMethod(
                "getSuppressedFields"));
    }

    @Test
    void exceptionHandlerOverrideSignatureMatchesExactPatch()
            throws Exception {

        assertNotNull(
                ResponseEntityExceptionHandler.class
                        .getDeclaredMethod(
                                "handleHandlerMethodValidationException",
                                HandlerMethodValidationException.class,
                                HttpHeaders.class,
                                HttpStatusCode.class,
                                WebRequest.class));
    }
}
```

**Giới hạn của reflection tests:** Chúng chứng minh method có mặt và đúng signature trên loaded classes. Chúng **không** chứng minh implementation đúng mọi trường hợp, không chứng minh bug không tồn tại và không đảm bảo source docs được công bố như thế nào. Những việc đó cần unit/MockMvc tests tiếp theo.

### 13.2. Có cần assert runtime version exact ở mọi project?

Với **bài thực hành cố định baseline**, yes — test fail sớm khi BOM bị nâng/override, buộc bạn cập nhật bằng chứng Javadoc. Với production liên tục upgrade, có thể:
- In runtime version vào test report.
- So major/minor theo policy của tổ chức.
- Dùng dependency locking hoặc SBOM để pin lại resolved artifacts.
- Cập nhật version-specific tests theo một PR nâng cấp có chủ đích.

Không nên giữ expected `"6.2.11"` mãi khi chủ động nâng Boot và Framework. Đó là baseline của bài, không phải security recommendation chạy patch cũ vô hạn.

## 14. Bằng chứng JUnit: `DataBinder` trực tiếp, không MVC

### 14.1. `DataBinderEvidenceTest.java`

```java
package demo.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DataBinderEvidenceTest {

    private static MutablePropertyValues values() {
        MutablePropertyValues data = new MutablePropertyValues();
        data.add("name", "Mai");
        data.add("seats", "2");
        data.add("approved", "true");
        return data;
    }

    @Test
    void defaultPropertyBindingCanSetASetter() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");

        binder.bind(values());

        assertEquals("Mai", form.getName());
        assertEquals(Integer.valueOf(2), form.getSeats());
        assertTrue(form.isApproved());
    }

    @Test
    void allowlistPreventsUnexpectedSetterMutation() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setAllowedFields("name", "seats");

        binder.bind(values());

        assertEquals("Mai", form.getName());
        assertEquals(Integer.valueOf(2), form.getSeats());
        assertFalse(form.isApproved());
        assertEquals("approved",
                binder.getBindingResult()
                        .getSuppressedFields()[0]);
    }

    @Test
    void suppressedFieldDoesNotAutomaticallyRegisterError() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setAllowedFields("name", "seats");

        binder.bind(values());

        assertEquals(1,
                binder.getBindingResult()
                        .getSuppressedFields().length);
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void declarativeModeWithoutAllowedFieldsSkipsSetters() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setDeclarativeBinding(true);

        binder.bind(values());

        assertNull(form.getName());
        assertNull(form.getSeats());
        assertFalse(form.isApproved());
    }

    @Test
    void declarativeModeWithAllowlistPermitsOnlySelectedProperties() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("name", "seats");

        binder.bind(values());

        assertEquals("Mai", form.getName());
        assertEquals(Integer.valueOf(2), form.getSeats());
        assertFalse(form.isApproved());
        assertEquals(1,
                binder.getBindingResult()
                        .getSuppressedFields().length);
    }

    @Test
    void autoGrowDefaultMatchesExactJavadoc() {
        DataBinder binder = new DataBinder(new AuditForm());

        assertEquals(256, binder.getAutoGrowCollectionLimit());
        assertEquals(
                DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT,
                binder.getAutoGrowCollectionLimit());
    }

    @Test
    void wrongIntegerValueProducesBindingFieldError() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setAllowedFields("name", "seats");

        MutablePropertyValues data = new MutablePropertyValues();
        data.add("name", "Mai");
        data.add("seats", "abc");

        binder.bind(data);

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("seats"));
        assertNotNull(binder.getBindingResult()
                .getFieldError("seats"));
        assertTrue(binder.getBindingResult()
                .getFieldError("seats").isBindingFailure());
        assertEquals("typeMismatch",
                binder.getBindingResult()
                        .getFieldError("seats").getCode());
    }
}
```

Các unit tests này **không tạo Spring ApplicationContext**. Chúng là bằng chứng cho `DataBinder`, không phải cho toàn bộ pipeline Jackson, argument resolvers hay Servlet container.

Bản mẫu không gọi `binder.validate()`, không đăng ký Bean Validation provider vào binder thủ công. Vì thế test `suppressedFieldDoesNotAutomaticallyRegisterError` không kiểm tra các `@NotBlank`/`@Min`: nó chỉ nói suppression **không tự sinh error** trong một bind thành công. Validation được kiểm tra qua MockMvc.

## 15. Bằng chứng MockMvc: điều gì thật sự xảy ra trong Spring MVC?

### 15.1. `MvcEvidenceTest.java`

```java
package demo.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcEvidenceTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder form() {
        return post("/audit/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Mai")
                .param("seats", "2");
    }

    @Test
    void versionEndpointShowsRuntimeFrameworkVersion()
            throws Exception {

        mvc.perform(get("/audit/version"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.springFramework")
                        .value("6.2.11"));
    }

    @Test
    void validFormIsBoundThroughWebDataBinder() throws Exception {
        mvc.perform(form())
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Mai"))
                .andExpect(jsonPath("$.seats").value(2))
                .andExpect(jsonPath("$.approved").value(false));
    }

    @Test
    void nonAllowlistedPropertyIsSuppressed()
            throws Exception {

        mvc.perform(form().param("approved", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"));
    }

    @Test
    void wrongFormTypeIsBindingErrorNotConstraintError()
            throws Exception {

        mvc.perform(form().param("seats", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.fields[*]",
                        hasItem("seats")));
    }

    @Test
    void zeroSeatsIsValidationError() throws Exception {
        mvc.perform(form().param("seats", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.fields[*]",
                        hasItem("seats")));
    }

    @Test
    void blankNameIsValidationError() throws Exception {
        mvc.perform(form().param("name", "  "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.fields[*]",
                        hasItem("name")));
    }

    @Test
    void validJsonDtoIsDeserializedThenUsed() throws Exception {
        mvc.perform(post("/audit/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Book","quantity":2}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Book"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void invalidJsonDtoUsesArgumentValidation() throws Exception {
        mvc.perform(post("/audit/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"","quantity":2}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void malformedJsonUsesMessageReadingError() throws Exception {
        mvc.perform(post("/audit/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"))
                .andExpect(result -> assertInstanceOf(
                        HttpMessageNotReadableException.class,
                        result.getResolvedException()));
    }

    @Test
    void missingQueryParameterUsesPresenceError()
            throws Exception {

        mvc.perform(get("/audit/limit"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(result -> assertInstanceOf(
                        MissingServletRequestParameterException.class,
                        result.getResolvedException()));
    }

    @Test
    void wrongQueryTypeUsesConversionError() throws Exception {
        mvc.perform(get("/audit/limit")
                        .param("limit", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentTypeMismatchException.class,
                        result.getResolvedException()));
    }

    @Test
    void validDirectMethodConstraintPasses() throws Exception {
        mvc.perform(get("/audit/page").param("page", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1));
    }

    @Test
    void directMinTriggersHandlerMethodValidation()
            throws Exception {

        mvc.perform(get("/audit/page").param("page", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }

    @Test
    void returnConstraintFailureIsServerError()
            throws Exception {

        mvc.perform(get("/audit/broken-return"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("RETURN_VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }
}
```

Khi test `/audit/page?page=0` pass, bạn có bằng chứng **MVC 6.2.11** đang sử dụng `HandlerMethodValidationException` trong cấu hình không có class-level `@Validated`. Nó **không** chứng minh các service method validation qua AOP cũng ném đúng exception đó.

Khi test `/audit/json` với blank title pass, bạn có bằng chứng `@Valid @RequestBody` và validation provider hoạt động trong project. Nó không tự chứng minh `@InitBinder#setAllowedFields` đã giới hạn JSON fields.

Khi test `/audit/form` gửi `approved=true` pass với mã `SUPPRESSED_FIELDS`, bạn có bằng chứng controller đã **quyết định từ chối** sau khi đọc `getSuppressedFields()`. Spring `DataBinder` chỉ cung cấp suppression metadata; chính sách trả HTTP 400 do ứng dụng tạo.

## 16. Chạy, lưu bằng chứng và báo cáo phiên bản

### 16.1. Chạy lệnh

Tại `spring-version-evidence`:

```bash
java -version
mvn -version
mvn dependency:tree -Dincludes=org.springframework
mvn test
```

Chạy riêng một class:

```bash
mvn -Dtest=VersionEvidenceTest test
mvn -Dtest=DataBinderEvidenceTest test
mvn -Dtest=MvcEvidenceTest test
```

Chạy server:

```bash
mvn spring-boot:run
```

**Bản Markdown này chưa thực thi Maven.** Những assertions trong code là **kỳ vọng của sample với pinned dependency baseline**. Chỉ xem đây là “PASSED” sau khi chạy `mvn test` và kiểm tra report thực, không dự đoán console output là bằng chứng.

JUnit tests theo listing:
- `VersionEvidenceTest`: 3 phương thức `@Test`.
- `DataBinderEvidenceTest`: 7 phương thức `@Test`.
- `MvcEvidenceTest`: 14 phương thức `@Test`.
- **Tổng cộng: 24 test methods**.

Khi chạy Maven Surefire, xem `target/surefire-reports` để biết tổng số tests được discover, failures, errors, skips. Nếu project thêm test, tổng số sẽ thay đổi; đừng dùng con số trong bài làm KPI cố định.

### 16.2. Thử bằng curl

```bash
curl -i 'http://localhost:8080/audit/version'
curl -i 'http://localhost:8080/audit/limit?limit=abc'
curl -i 'http://localhost:8080/audit/page?page=0'
```

Với version baseline, route đầu trả JSON:

```json
{"springFramework":"6.2.11"}
```

Form hợp lệ:

```bash
curl -i -X POST \
  'http://localhost:8080/audit/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Mai' \
  --data-urlencode 'seats=2'
```

Kỳ vọng 200 với dữ liệu:

```json
{"name":"Mai","seats":2,"approved":false}
```

Form có field bị chặn:

```bash
curl -i -X POST \
  'http://localhost:8080/audit/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Mai' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'approved=true'
```

Kỳ vọng 400:

```json
{"code":"SUPPRESSED_FIELDS","fields":[]}
```

JSON vi phạm constraint:

```bash
curl -i -X POST \
  'http://localhost:8080/audit/json' \
  -H 'Content-Type: application/json' \
  -d '{"title":"","quantity":2}'
```

Kỳ vọng 400 với `code="VALIDATION_ERROR"` và `fields` chứa `title`. Lỗi JSON malformed trả `BODY_UNREADABLE`, không phải lỗi `@NotBlank`.

### 16.3. Evidence log đề xuất sau khi chạy

```text
Project: spring-version-evidence
Java: <ghi output java -version>
Boot parent: 3.5.6
Resolved Spring Framework: <ghi output dependency:tree>
Runtime SpringVersion: <ghi GET /audit/version>
Javadoc exact patch: Spring Framework 6.2.11
Reference Guide series: 6.2 (banner patch: <ghi lúc review>)
Test command: mvn test
Surefire result: <tests/failures/errors/skips thực tế>
Verdict: <PASS/FAILED/INVESTIGATE>
Source tag: v6.2.11
```

Phần `<...>` là **mẫu điền khi tự thực hành**, không phải output chương trình, không phải các ô Google Sheet khác và không phải lời khẳng định tests đã chạy. Khi tạo báo cáo thật, không lưu source IP/password/credentials từ máy CI.

## 17. Khi kết quả không khớp tài liệu: xử lý từng trường hợp

### 17.1. `NoSuchMethodError` dù IDE compile được

Có thể compile dùng Spring 6.2 API nhưng runtime đang load jar cũ. Kiểm tra:
- `mvn dependency:tree` và effective POM.
- Fat jar contents và container classpath nếu deploy.
- `SpringVersion.getVersion()` ở runtime thật.
- `CodeSource` của class, ví dụ `DataBinder.class.getProtectionDomain().getCodeSource().getLocation()` (nếu security policy cho phép).
- Runtime startup scripts, plugin loader, tests và shading.

`NoSuchMethodError` thường là linkage/classpath mismatch, không tự kết luận method bị xóa khỏi framework.

### 17.2. `@Override` báo compile error

Có thể copy chữ ký từ Javadoc của patch khác hoặc import nhầm `HttpStatus` thay `HttpStatusCode`. Với `ResponseEntityExceptionHandler`, kiểm tra **method signature từng parameter**, đặc biệt các biến thể trên từng major/minor. Javadoc 6.2.11 của demo cho `handleHandlerMethodValidationException` dùng:
- `HandlerMethodValidationException`.
- `HttpHeaders`.
- `HttpStatusCode`.
- `WebRequest`.

Không bỏ `@Override` để “né lỗi”: điều đó có thể biến một override dự định thành method overload không bao giờ được framework gọi.

### 17.3. `getSuppressedFields()` rỗng dù request có field lạ

Có thể là:
- Đang constructor binding, không dùng property field allowlist.
- `@InitBinder` không khớp model attribute name.
- Đang dùng `@RequestBody` JSON qua Jackson.
- Client gửi field không có setter và binder ignore unknown fields.
- Đã bật declarative binding nên property bind không chạy.
- Field path có chuẩn hóa/case pattern khác dự đoán.

Chạy pure `DataBinder` test trước; sau đó so controller binding setup. Đừng dùng `getSuppressedFields` như “bộ phát hiện mọi unknown key” cho mọi input path.

### 17.4. `@Valid` không có tác dụng

Kiểm tra:
- `spring-boot-starter-validation` và provider thực tế.
- Annotation import `jakarta.validation.Valid` (Spring Boot3/Spring Framework6).
- Constraint annotations đặt trên field/record components đúng.
- Có `BindingResult` ngay sau argument và controller bỏ qua errors không?
- Có direct method constraint chuyển đường handling không?
- Test context có auto-config validator không?

Đừng mang `javax.validation.*` từ ví dụ Spring Boot2 sang Boot3 khi code cần `jakarta.validation.*`.

### 17.5. `@Min` ném exception khác dự đoán

Nếu dùng `@Validated` ở controller class, AOP proxy-based validation có thể thay đổi path. Nếu Spring Framework version thấp hơn 6.1, built-in method validation chưa giống baseline. Đối chiếu Guide 6.2, Javadoc `HandlerMethodValidationException` 6.2.11 và test với controller signature nhỏ nhất.

### 17.6. Test reflection pass nhưng HTTP test fail

Chữ ký method tồn tại không bảo đảm:
- Bean được Spring MVC đăng ký.
- Validation provider có trên classpath.
- Filter/security chặn request trước controller.
- Formatters/converters sẵn sàng.
- Global advice được quét.
- Error status/schema giống kỳ vọng.

Reflection là **API presence evidence**, MockMvc là **runtime integration evidence**.

### 17.7. Patch mới hơn giải thích hành vi khác

Nếu Spring Boot được nâng lên 3.5.x patch mới hơn, version resolved có thể là Spring 6.2.x patch mới. Hãy:
1. Ghi phiên bản cũ và mới.
2. Xem release notes/bug fixes, không suy “minor giống nhau thì behavior chắc chắn giống nhau”.
3. Mở Javadoc và source tag của patch mới.
4. Chạy regression suite trên cả baseline cũ và mới nếu có khả năng.
5. Cập nhật statement/test nếu thay đổi được chứng minh là có chủ đích.
6. Đừng đổi compiler target chỉ để vượt lỗi import Java API do copy từ Spring 7.

## 18. Các sai lầm thường gặp khi tra tài liệu

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gõ “Spring DataBinder Javadoc” và mở trang latest | Latest có thể khác binary đang chạy | Chỉ dùng `docs/6.2.11/javadoc-api` cho baseline |
| Thấy Boot 3.5.6 thì tra Framework 3.5.6 | Hai hệ release khác nhau | Lấy resolved version từ dependency tree |
| Dùng Guide `/reference/6.2` rồi khẳng định đó là 6.2.11 | Series docs có thể hiển thị patch 6.2.x mới | Ghi banner patch và dùng exact Javadoc |
| Copy phương thức `setDeclarativeBinding` từ 6.2 vào app 6.0 | API `Since 6.1` | Kiểm tra Since |
| Bỏ qua “used for setter/field injection” | Áp giới hạn auto-grow vào constructor sai phạm vi | Đọc Method Details của 6.2.11 |
| Nhìn `hasErrors()==false` và nói không có unknown input | Suppression được báo riêng | Đọc `getSuppressedFields` |
| Nhìn 400 rồi gắn nhãn “@Valid lỗi” | 400 có thể là conversion/JSON/method validation | Xem resolved exception và FieldError |
| Dùng Spring WebFlux docs cho MockMvc Servlet | Hai stack có exception/validation paths khác | Chọn mục MVC, không Reactive |
| Bỏ `@Override` cho hết compile lỗi | Có thể mất handler override | Đọc exact signature |
| Chỉ chạy unit test mà bỏ MockMvc | Không kiểm tra MVC pipeline | Thêm web-layer tests |
| Chỉ chạy MockMvc mà bỏ DataBinder unit tests | Khó khoanh vùng lỗi | Có cả hai tầng |
| Thấy Java record immutable rồi nghĩ binder không thể over-post | Constructor args vẫn do client điều khiển | DTO chỉ chứa public input fields |
| Copy `javax.validation.` từ Boot2 | Spring6/Boot3 dùng Jakarta | Chuyển sang `jakarta.validation` |
| Tự thay `spring-framework.version` cho compile được | Có thể phá Boot-managed compatibility | Tránh override nếu không có lý do/test |
| Đoán compiler/plugin version | Effective build có inheritance/override | Đọc effective POM |
| Chạy test nhưng không lưu môi trường | Không thể tái hiện trên CI | Ghi Java/Maven/Boot/Framework |
| Gọi observed behavior là public guarantee | Có thể chỉ là implementation detail | Phân loại claim theo mức bằng chứng |
| Đưa raw exception message ra API | Có thể lộ request values, internal details | Dùng machine error codes ổn định |

## 19. Checklist thực hành cuối bài

1. Đã xác định Maven hay Gradle?
2. Đã ghi đúng Boot parent/BOM version?
3. Đã lấy resolved Spring Framework version từ dependency tree?
4. Đã so runtime `SpringVersion.getVersion()`?
5. Đã mở Javadoc đúng **major.minor.patch**?
6. Đã ghi `Since` của từng API đang bàn?
7. Đã kiểm tra exact signature và package import?
8. Đã đọc defaults và “applies to/used for” trong Method Details?
9. Đã tách property binding khỏi constructor binding?
10. Đã tách form/query binder khỏi JSON/Jackson?
11. Đã tách Bean Validation khỏi conversion errors?
12. Đã kiểm tra `BindingResult.getSuppressedFields()` riêng?
13. Đã xác định `@InitBinder` attribute name khớp model?
14. Đã ghi class-level `@Validated` có/không?
15. Đã so đúng MVC stack thay vì WebFlux?
16. Đã kiểm tra exception status input 400 vs return 500?
17. Đã viết pure `DataBinder` unit test cho method scope?
18. Đã viết MockMvc tests cho HTTP behavior?
19. Đã assert error code/field, không chỉ status?
20. Đã lưu build/runtime versions khi test chạy?
21. Đã so Reference Guide series banner patch?
22. Đã kiểm tra release notes nếu Javadoc/test không khớp?
23. Đã đọc source **tag đúng** nếu cần phân tích sâu?
24. Đã tránh override BOM chỉ để “làm ví dụ chạy”?
25. Đã ghi kết quả actuals chứ không mạo nhận test đã chạy?
26. Đã xác định phạm vi kết luận và những điểm chưa được chứng minh?
27. Đã có một test khi nâng cấp để phát hiện API signature drift?
28. Đã tránh để example-only vulnerable DTO lọt vào production?

## 20. Bài tập mở rộng

1. Nâng Spring Boot **chỉ trong một nhánh thử nghiệm**, chạy `dependency:tree` và ghi version mới, không phỏng đoán.
2. Thay Javadoc link của `DataBinder` từ 6.2.11 sang version mới thực resolved; so `Since` và scope của ba methods.
3. Viết một test khác cho `setAutoGrowNestedPaths(false)` ở property binding; nêu input nested null và kỳ vọng.
4. Tạo constructor-binding record chứa List, kiểm tra vì sao `setAutoGrowCollectionLimit` không phải quota cho cơ chế constructor.
5. Thêm `@BindParam` vào constructor argument trên Spring6.2, tra `Since` và test alias form, không nhầm Jackson.
6. Thử chuyển `@Valid @RequestBody` thành handler có direct `@Min` khác, quan sát validation exception path.
7. Thêm `@Validated` ở controller class **trong test configuration riêng** và so AOP vs MVC built-in validation.
8. Viết test Bean Validation nested object với `@NotNull @Valid` và ghi exact error path.
9. Đổi `setAllowedFields` từ `"name"` thành wildcard quá rộng, tìm input có thể over-post.
10. Thêm strict HTTP form parameter allowlist rồi so với `getSuppressedFields`; đừng coi chúng tương đương.
11. Viết test `ResponseEntityExceptionHandler` trả ProblemDetail RFC 9457 thay custom AuditError.
12. So `@RequestBody` unknown JSON properties với `@ModelAttribute` unknown form fields, đọc rõ docs hai stacks.
13. Thêm Gradle build dùng dependency insight, so resolved dependency với bản Maven.
14. Tạo bảng API signature diff khi nâng Framework 6.x lên 7.x để biết chỗ cần compile-fix.
15. Kiểm thử real HTTP server bên cạnh MockMvc nếu lỗi chỉ xuất hiện với proxy/container.
16. Dùng `javap` trên dependency jar thực tế để xác nhận chữ ký bytecode khi Javadoc, IDE và runtime khác nhau.
17. So Javadoc `DataBinder#setIgnoreUnknownFields(false)` với constructor binding; chứng minh giới hạn documented.
18. Dùng source tag để tìm method body của `shouldNotBindPropertyValues()` và phân loại đó là internal implementation hay public contract.
19. Thêm SBOM/dependency locking vào pipeline, báo cáo version drift định kỳ.
20. Thiết kế CI job chạy test trên baseline cũ và candidate upgrade, xuất bảng PASS/FAIL kèm commit/tag.

**Kết luận:** Một kết quả Spring chỉ được giải thích đáng tin khi đã trả lời **“Chạy phiên bản nào, API thuộc stack nào, Javadoc exact patch nói gì, Reference Guide nhánh nào, test tái hiện ra sao?”**. Baseline thực hành Spring Boot 3.5.6 dùng Spring Framework 6.2.11; hãy kiểm bằng dependency tree và runtime. Sau đó đọc **Method Details** (defaults, `Since`, phạm vi constructor/property), viết DataBinder unit tests và MockMvc integration tests, ghi evidence thay vì suy đoán. Đây là quy trình có thể tái sử dụng cho bất kỳ vấn đề binding/validation nào khi nâng Spring.

## 21. Nguồn đối chiếu chính thức và versioned

1. [Maven Central — Spring Boot starter-web 3.5.6 dependencies](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-web/3.5.6).
2. [Spring Framework 6.2.11 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/DataBinder.html).
3. [Spring Framework 6.2.11 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/BindingResult.html).
4. [Spring Framework 6.2.11 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html).
5. [Spring Framework 6.2.11 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html).
6. [Spring Framework 6.2 Reference — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html).
7. [Spring Framework 6.2 Reference — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html).
8. [Spring Framework 6.2 Reference — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html).
9. [Spring Framework 6.2 Reference — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html).
10. [Spring Framework 6.2.11 official release](https://spring.io/blog/2025/09/11/spring-framework-6-2-11-available%20now/).
11. [Spring Framework source v6.2.11](https://github.com/spring-projects/spring-framework/tree/v6.2.11).
12. [Spring Boot source v3.5.6](https://github.com/spring-projects/spring-boot/tree/v3.5.6).
13. [Spring Boot 3.5 — Build Systems](https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html).
14. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
15. [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).