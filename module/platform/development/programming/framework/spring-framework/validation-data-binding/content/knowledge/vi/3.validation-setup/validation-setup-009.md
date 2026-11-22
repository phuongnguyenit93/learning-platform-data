# Tra cứu API và hành vi thay đổi theo phiên bản Spring Framework

## 1. Mục tiêu và phạm vi

Khi làm việc với **Spring Framework – Validation & Data Binding**, một ví dụ chạy đúng trong tài liệu phiên bản mới chưa chắc biên dịch hoặc hoạt động giống hệt trong dự án đang dùng phiên bản cũ. Vấn đề không chỉ là một phương thức có tồn tại hay không: phiên bản Framework, Spring Boot, thư viện Bean Validation, bộ chuyển đổi kiểu, cơ chế xử lý tham số MVC và cấu hình ứng dụng đều có thể ảnh hưởng đến kết quả.

Sau bài này, bạn có thể:

1. Xác định **phiên bản Spring Framework thực sự được resolve và chạy**, không nhầm với số phiên bản Spring Boot hoặc phiên bản tài liệu đang mở.
2. Tìm đúng **Reference Documentation**, **Javadoc**, **release notes**, **upgrade guide**, mã nguồn và test ứng với phiên bản cụ thể.
3. Phân biệt **thay đổi chữ ký API** với **thay đổi hành vi khi chạy** qua các cơ chế `DataBinder`, `WebDataBinder`, `ConversionService`, `Validator`, `@ModelAttribute` và method validation.
4. Tự dựng một phép thử nhỏ có đầu vào và đầu ra có thể kiểm chứng trước khi áp dụng kết luận vào ứng dụng thật.
5. Lập danh sách tác động khi nâng cấp từ Spring Framework 5.3 sang 6.x, giữa các nhánh 6.x, hoặc từ 6.x sang 7.x.

Phạm vi tập trung vào **validation và data binding** trong Spring Core/Spring MVC; khi cần, bài học chỉ ra ranh giới với Spring WebFlux và JSON deserialization. Việc Spring Framework 7 bổ sung khả năng **API versioning cho endpoint HTTP** là một tính năng riêng, không phải chủ đề chính ở đây. “Phiên bản API” trong bài này có nghĩa là phiên bản của thư viện và các hợp đồng lập trình Java.

## 2. Phân biệt API, hành vi và môi trường chạy

**API** là phần mã của bạn gọi hoặc triển khai: package, class, interface, method, constructor, annotation, tham số, kiểu trả về, ngoại lệ công khai. Ví dụ `DataBinder.setDeclarativeBinding(boolean)` là một phương thức của Spring.

**Hành vi** là kết quả sau khi gọi API hoặc gửi request: một trường form có được bind không, lỗi vào `BindingResult` hay thành exception, phương thức controller có được gọi không, status HTTP nào được trả, formatter nào áp dụng cho ngày tháng.

**Môi trường** bao gồm JDK, Spring Framework, Spring Boot (nếu sử dụng), Jakarta Validation API/provider, servlet container, dependency graph và cấu hình MVC. Hai dự án có cùng mã controller nhưng khác những thành phần này có thể cho kết quả khác nhau.

Ví dụ điển hình:

- Code gọi `DataBinder.setDeclarativeBinding(true)` sẽ **không biên dịch** nếu compile classpath chứa phiên bản `DataBinder` trước khi API này được thêm ở Spring Framework **6.1**.
- Cùng controller có `@RequestParam @Min(1)` có thể đi qua cơ chế validation khác nhau nếu chạy MVC trước hoặc từ Spring **6.1**, vì Spring MVC 6.1 bổ sung **method validation tích hợp**.
- `@Valid` của ứng dụng Spring 5.x thường import từ `javax.validation.Valid`; khi chuyển lên Spring Framework 6 (hệ Jakarta EE), cần dùng `jakarta.validation.Valid` và thư viện validation tương thích.
- Một lỗi parse JSON trong `@RequestBody` có thể do Jackson/message converter, trong khi lỗi gán thuộc tính ở `@ModelAttribute` đi qua data binding. Đổi `ConversionService` không bảo đảm sửa được lỗi Jackson.

Vì vậy, mỗi kết luận kỹ thuật nên có cấu trúc: **“Trên Spring Framework phiên bản X, với dependency/cấu hình Y và đầu vào Z, quan sát được kết quả K.”** Tránh kết luận chung chỉ từ một bài viết không ghi phiên bản.

## 3. Xác định đúng phiên bản trước khi tra cứu

### 3.1. Spring Boot không phải Spring Framework

Spring Boot cung cấp auto-configuration và một tập dependency được quản lý bằng BOM. Số `spring-boot` và số `spring-framework` **không giống nhau**. Ví dụ, đổi phiên bản Boot có thể kéo theo phiên bản mới của `spring-core`, `spring-context`, `spring-web` và `spring-webmvc`. Không suy ra chính xác một phiên bản Framework chỉ từ tên file cấu hình.

Với dự án **Gradle**, đọc cấu hình đã resolve:

~~~bash
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows dùng `gradlew.bat` thay cho `./gradlew`. Với Gradle multi-project, thêm tên subproject, ví dụ `./gradlew :web-app:dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath`; tên `web-app` ở đây chỉ là minh họa cấu trúc lệnh. Nếu project không có configuration `runtimeClasspath`, xem configuration thực tế của module.

Với **Maven**:

~~~bash
mvn dependency:tree -Dincludes=org.springframework
mvn help:effective-pom
~~~

Mục tiêu là ghi lại **phiên bản được chọn sau dependency management và conflict resolution**. Một khai báo trực tiếp hoặc dependency transitively kéo theo phiên bản khác chưa đủ chứng minh bản thực tế. Nên kiểm tra tính đồng bộ của các artifact Spring; việc trộn nhiều major/minor không tương thích có thể sinh lỗi `NoSuchMethodError`, `ClassNotFoundException` hoặc thay đổi hành vi khó đoán.

Trong ứng dụng đang chạy có Spring Core, có thể dùng:

~~~java
import org.springframework.core.SpringVersion;

System.out.println("Framework=" + SpringVersion.getVersion());
System.out.println("Java=" + Runtime.version());
~~~

Đoạn này là **snippet**, đặt trong một phương thức chạy của ứng dụng. `SpringVersion.getVersion()` thường trả phiên bản của Spring Core đang được nạp; trong một số cách đóng gói đặc biệt nó có thể trả `null`. Khi ấy hãy kiểm tra JAR/classpath thay vì bịa một số phiên bản. Đừng lấy một banner startup làm bằng chứng duy nhất cho tất cả module Spring.

### 3.2. Chốt “hồ sơ phiên bản” cho vấn đề

Trước khi tra cứu, ghi các trường sau:

| Trường | Ví dụ thông tin cần chốt |
| --- | --- |
| Framework | `spring-core`, `spring-context`, `spring-web`, `spring-webmvc` đang ở những phiên bản nào |
| Boot | Có/không; version Boot và BOM thực tế |
| JDK | Java 17, 21 hoặc phiên bản đang chạy; khác với source compatibility nếu có |
| Validation | `jakarta.validation` hay `javax.validation`; provider nào, phiên bản nào |
| Web stack | Spring MVC/Servlet hay WebFlux; dùng `@ModelAttribute`, `@RequestParam` hay `@RequestBody` |
| Đường lỗi | Compile error, lỗi startup, lỗi bind, validation error, exception hay HTTP response |
| Cấu hình | `WebMvcConfigurer`, `@InitBinder`, `@Validated`, custom `Converter`/`Formatter`, `@ControllerAdvice` |

Ví dụ lỗi “`HandlerMethodValidationException` không tồn tại” trước hết phải kiểm tra phiên bản `spring-web` và cơ chế validation đang áp dụng, rồi mới đọc Javadoc. Lỗi “`@Valid` không chạy” cần xác định provider, annotation, parameter type và cách Spring gọi validation.

## 4. Nguồn tra cứu chính thức và cách đọc đúng

### 4.1. Thứ tự tra cứu đáng tin

| Nguồn | Mục đích | Điều cần ghi lại |
| --- | --- | --- |
| **Javadoc đúng phiên bản** | Chữ ký, kế thừa, `@since`, `@Deprecated`, hợp đồng method | Package, module/JAR, tham số, return, exception, since |
| **Reference Documentation của cùng nhánh** | Luồng xử lý, điều kiện áp dụng, mẫu cấu hình | Endpoint, loại binding, thứ tự validation, phạm vi cấu hình |
| **Release Notes / Upgrade Guide** | Breaking changes, tính năng mới, thay đổi mặc định | Version bắt đầu, yêu cầu migration, thay thế được đề xuất |
| **Source code tại tag phát hành** | Hành vi khi Javadoc chưa đủ rõ | Nhánh điều kiện và đường thực thi thực tế |
| **Tests trong source tại tag** | Bằng chứng hành vi, trường hợp biên | Tên test, đầu vào, asserted exception/result |
| **Reproducer chạy đúng dependency** | Xác nhận trong môi trường ứng dụng | Command, Java/Framework/provider, stdout/HTTP response |

Liên kết khởi đầu chính thức:

- [Spring Framework Reference – Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC – `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC – `@InitBinder`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework Javadoc – trang điều hướng](https://docs.spring.io/spring-framework/docs/current/javadoc-api/)
- [Spring Framework 6.x Upgrade Guide](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring Framework release tags](https://github.com/spring-projects/spring-framework/tags)
- [Spring Framework support branches](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions)

Trang `reference` không gắn phiên bản thường hiển thị nhánh được xuất bản hiện tại. Khi xử lý hệ thống cũ, **đọc thêm bản tài liệu lưu trữ đúng phiên bản** nếu có, và dùng Javadoc của chính artifact đã xác định. Không suy diễn rằng đoạn ví dụ ở trang “current” chạy được nguyên dạng trên 5.3 hoặc 6.0.

### 4.2. Đọc Javadoc theo một quy trình cố định

Giả sử cần tìm `org.springframework.validation.DataBinder.setDeclarativeBinding`:

1. Xác nhận tên đầy đủ: `org.springframework.validation.DataBinder`, thuộc Spring `spring-context`. Đừng nhầm `DataBinder` với `WebDataBinder` là subclass phục vụ môi trường web.
2. Mở [DataBinder Javadoc của Spring 6.1.0](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html), tìm `setDeclarativeBinding`.
3. Đọc chữ ký `void setDeclarativeBinding(boolean declarativeBinding)`, mô tả và mục **Since: 6.1**. Đây là bằng chứng trực tiếp về thời điểm API xuất hiện.
4. Đọc **See Also** và các method liên quan như `setAllowedFields`, `construct`, `bind`, `getBindingResult`. Hỏi phương thức tác động tới *constructor binding*, *property binding* hay cả hai.
5. So với Javadoc của phiên bản cũ/chính xác đang dùng. Nếu một API không hiện ra, kiểm tra đúng tên class, package, phiên bản và khả năng method được kế thừa trước khi kết luận “không có”.
6. Nếu thay đổi ảnh hưởng tới lỗi runtime hoặc bảo mật, kiểm tra thêm Reference, release notes và một bài test nhỏ.

Các dấu mốc đáng chú ý trong Javadoc:

- `@since`: thời điểm API được đưa vào; **không tự chứng minh** chi tiết hành vi ở mọi bản vá.
- `@Deprecated` hoặc “Deprecated”: khuyến nghị ngừng sử dụng, có thể kèm `forRemoval` và phương án thay thế. Deprecated **không đồng nghĩa** đã bị xóa ngay.
- Parameters / Returns / Throws: hợp đồng mà người gọi có thể dựa vào.
- Implemented Interfaces / Superclasses: một method có thể được khai báo ở interface hoặc kế thừa từ superclass.
- Nullability, generic type và annotation: có thể thay đổi kiểm tra tĩnh/khả năng dùng Kotlin dù tên method không đổi.

### 4.3. Từ tài liệu đến code và test của tag

Trong GitHub repository `spring-projects/spring-framework`, chọn **tag của release cụ thể** thay vì mặc định nhìn `main`. Với mỗi API, lần lượt:

1. Tìm file Java khai báo method/annotation theo full package.
2. Tìm các nơi gọi method và các unit/integration tests liên quan.
3. So sánh **hai tag cần quan tâm**, ghi rõ phần thay đổi: chữ ký, default, điều kiện, exception, thứ tự xử lý.
4. Xem lịch sử issue/PR khi release note không mô tả đủ vì sao thay đổi.
5. Dùng test của ứng dụng để xác nhận trong stack, vì custom configuration có thể làm kết quả khác test của Spring.

Chỉ dựa vào một dòng diff thường chưa đủ. Ví dụ thêm một phương thức public chưa chắc nó được MVC gọi theo mặc định; cần biết framework/Boot có đăng ký hoặc bật tính năng ấy hay không.

## 5. Bản đồ API cần biết của Validation & Data Binding

| API / annotation | Nhóm / thư viện | Nhiệm vụ cần tra cứu |
| --- | --- | --- |
| `org.springframework.validation.DataBinder` | Spring validation (`spring-context`) | Constructor/property binding, allowed fields, lỗi, validator, chế độ declarative |
| `org.springframework.web.bind.WebDataBinder` | Spring web | Binder mở rộng cho web request; formatter/converter/editor theo phạm vi |
| `org.springframework.validation.BindingResult` | Spring validation | `FieldError`, `ObjectError`, rejected value, suppressed fields |
| `org.springframework.validation.Validator` | Spring validation | `supports`, `validate`; có thể dùng không cần Jakarta Validation |
| `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` | Spring validation + Jakarta | Adapter tích hợp Bean Validation provider vào Spring |
| `jakarta.validation.Valid` / `jakarta.validation.constraints.*` | Jakarta Validation API | Cascade validation và constraint; yêu cầu provider phù hợp |
| `org.springframework.validation.annotation.Validated` | Spring validation | Validation groups và các kịch bản method validation qua AOP |
| `org.springframework.core.convert.ConversionService` | Spring Core | Chuyển kiểu, `canConvert`/`convert` |
| `org.springframework.core.convert.converter.Converter` | Spring Core | Quy tắc chuyển kiểu tùy biến |
| `org.springframework.format.Formatter` | Spring formatting | Parse/print dữ liệu theo locale |
| `org.springframework.web.bind.annotation.ModelAttribute` | Spring Web | Lấy hoặc tạo model object và bind request values |
| `org.springframework.web.bind.annotation.InitBinder` | Spring Web | Cấu hình `WebDataBinder` theo controller/advice |
| `org.springframework.web.servlet.config.annotation.WebMvcConfigurer` | Spring MVC | Đăng ký converter/formatter/validator ở phạm vi MVC |
| `org.springframework.web.bind.MethodArgumentNotValidException` | Spring Web | Lỗi validation/binding của argument theo đường resolver |
| `org.springframework.web.method.annotation.HandlerMethodValidationException` | Spring Web, từ 6.1 | Kết quả lỗi method validation tích hợp của MVC |

Tên lớp chính xác rất quan trọng khi tìm kiếm: `Validator` thuộc Spring và `Validator` thuộc Jakarta có cùng tên ngắn nhưng khác package, hợp đồng và phương thức. `LocalValidatorFactoryBean` thường là cầu nối. Tương tự, formatter của form MVC không phải cùng một thành phần với JSON deserializer.

## 6. Các mốc phiên bản cần kiểm chứng khi nâng cấp

| Dòng Spring Framework | Mốc thay đổi có liên quan | Việc nên xác minh |
| --- | --- | --- |
| **5.3.x** | Thuộc thế hệ trước chuyển đổi Jakarta; hệ sinh thái Bean Validation thường dùng `javax.validation` | Import `javax.*`, provider, Java/runtime, cách bật method validation |
| **6.0.x** | Baseline Java 17; chuyển sang Jakarta EE 9, gồm `jakarta.validation` và `jakarta.servlet` | Đổi import + dependency, container, tương thích Hibernate Validator |
| **6.1.x** | Spring MVC hỗ trợ **method validation tích hợp**; `DataBinder.setDeclarativeBinding` có mặt từ 6.1 | Loại exception, class-level `@Validated`, constructor/property binding, Javadoc `@since` |
| **6.2.x** | Nhánh tính năng cuối của thế hệ 6; các bản vá có thể thay đổi chi tiết xử lý và khắc phục lỗi | So release notes/changelog của bản vá thật; không coi mọi bản 6.x là giống nhau |
| **7.0.x** | Baseline Jakarta EE 11/Bean Validation 3.1, vẫn hỗ trợ Java 17; ưu tiên Jackson 3 và JSpecify nullness | Provider/container đúng thế hệ, integration JSON, nullability, API deprecated/removed |

Bảng này là **điểm xuất phát tra cứu**, không phải bảng tương thích hoàn chỉnh hay lời khẳng định mọi ứng dụng cùng hành vi. Với mỗi lần nâng cấp, đọc ghi chú của **đúng release nguồn và release đích**. Chẳng hạn mốc “6.1 có method validation tích hợp” không có nghĩa mọi kiểu validation đều tự động chạy nếu thiếu Bean Validation provider hoặc cấu hình cần thiết.

### 6.1. Spring 5.3 → 6.0: namespace Validation thay đổi

Ví dụ import của ứng dụng ở thế hệ cũ:

~~~java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
~~~

Khi di chuyển lên Spring Framework 6 và Jakarta Validation tương thích:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
~~~

Việc thay import **chỉ là một phần** của migration: build phải có Jakarta Validation API/provider đúng thế hệ; servlet stack cũng chuyển từ `javax.servlet` sang `jakarta.servlet`. Các class của Spring như `org.springframework.validation.BindingResult` **không** tự đổi package thành `jakarta.*`.

Lỗi hay gặp:

- `package javax.validation does not exist`: compile classpath đã chuyển hệ Jakarta nhưng source vẫn import package cũ.
- `NoClassDefFoundError` hoặc Bean Validation không chạy: thiếu API/provider, hoặc phiên bản provider không tương thích.
- `@Valid` hiện diện nhưng constraint không được kiểm tra: xác nhận annotation đặt đúng chỗ, đối tượng nhận dữ liệu có constraint, provider được phát hiện và MVC/bean validation thực sự được gọi.

Đừng trộn `javax.validation.*` và `jakarta.validation.*` trong cùng một quy trình kỳ vọng chúng tương đương nhị phân.

### 6.2. Spring 6.1: chú ý cả API mới lẫn cơ chế MVC mới

Có hai trường hợp có giá trị học tập cao:

**Trường hợp A: `DataBinder.setDeclarativeBinding(boolean)`.** Javadoc đánh dấu **Since: 6.1**. Khi bật `true`, binder chỉ áp dụng những kiểu binding được chủ động cho phép: constructor binding và property binding theo `allowedFields`. Mục tiêu là hạn chế việc client tự ý gán thuộc tính không thuộc dữ liệu đầu vào hợp lệ. API này khác với `setAllowedFields` vốn có thể cấu hình whitelist thuộc tính ngay cả trong những phiên bản trước.

**Trường hợp B: method validation tích hợp trong Spring MVC.** Trước 6.1, kiểm tra constraint trực tiếp trên tham số phương thức thường cần cách thiết lập khác, chẳng hạn AOP method validation. Từ 6.1, Spring MVC có cơ chế tích hợp cho method argument/return constraints và có thể ném `HandlerMethodValidationException`. Với `@Valid` trên command object thông thường, trong điều kiện phù hợp, validation ở mức tham số riêng lẻ có thể ném `MethodArgumentNotValidException`. Phải kiểm tra chữ ký phương thức vì thêm `@Min` hay `@NotBlank` trực tiếp vào một parameter có thể chuyển cả lời gọi sang đường **method validation**.

### 6.3. Spring 7.0: nâng baseline không đồng nghĩa đổi mọi API binding

Spring Framework 7.0 giữ baseline **Java 17**, đồng thời nâng các ràng buộc nền lên Jakarta EE 11 và Bean Validation 3.1. Với web application, cần kiểm tra servlet container và provider tương thích; ví dụ ứng dụng chạy thư viện Jakarta Validation thế hệ cũ hơn có thể gặp lỗi tích hợp.

Framework 7.0 hỗ trợ Jackson 3 với hệ package `tools.jackson` và deprecate đường Jackson 2. Việc đó đáng quan tâm nếu endpoint dùng `@RequestBody`/`@ResponseBody` JSON, nhưng không được đánh đồng với thay đổi của `DataBinder` cho form hoặc query parameter. Framework cũng chuyển nullness annotation sang JSpecify; dấu hiệu nullable trong Javadoc/tooling có thể khác trước dù method vẫn tồn tại.

Không tự gắn “đã xóa ở Spring 7” cho bất kỳ API nào chỉ vì deprecated ở 6.x: cần đối chiếu release note và Javadoc 7.0. Các thay đổi chính xác về patch-level cũng phải được tra riêng.

## 7. Tình huống 1: kiểm tra API DataBinder theo phiên bản

### 7.1. Câu hỏi kỹ thuật đúng cách

“Ứng dụng chạy Spring 6.0 có thể gọi `setDeclarativeBinding(true)` không? Nếu nâng lên 6.1 thì việc bind các trường form được phép và không được phép thay đổi thế nào?”

Trình tự xác minh:

1. Mở Javadoc `DataBinder` ở bản đã resolve và tìm đúng chữ ký.
2. Với 6.1.0, thấy `setDeclarativeBinding(boolean)` có **Since: 6.1**; không sao chép lời gọi đó vào source code compile trên 6.0.
3. Đọc mô tả: `setDeclarativeBinding(true)` giới hạn property binding theo `allowedFields`; constructor binding vẫn là một đường riêng.
4. Kiểm tra DTO nhận input, danh sách field muốn cho phép, cách binder được cấu hình (`@InitBinder` hay trực tiếp).
5. Gửi cả field hợp lệ lẫn field ngoài danh sách, xem `BindingResult.getSuppressedFields()`. Một field bị suppress không có nghĩa tự động ném exception.
6. Chạy lại phép thử với hai phiên bản, ghi nhận kết quả; nếu có khác biệt, dựa vào code và test của tag để giải thích.

Ví dụ trong một Spring MVC controller trên **Spring 6.1+**:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("registrationForm")
public void restrictInput(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("displayName", "email");
}
~~~

Đây là **snippet trong controller**, không phải file Java độc lập. Khi dùng `@ModelAttribute("registrationForm")`, nó cấu hình binder cho model attribute mang tên đó. `setAllowedFields` kiểm soát property binding theo whitelist; lựa chọn các tham số constructor vẫn cần thiết kế DTO cẩn thận. Đừng bind thẳng vào entity có `role`, `isAdmin` hoặc `balance` rồi tin rằng mỗi validation annotation sẽ ngăn mọi dạng mass assignment.

### 7.2. Thử nghiệm chạy được trên Java 17+

Bài thử dưới đây dùng **Spring Context** trực tiếp, không cần Spring Boot hay web server. Nó kiểm chứng hai mặt:

- API `setDeclarativeBinding(boolean)` có tồn tại trong JAR đang chạy hay không (dùng reflection để bản thân source có thể compile cả với 6.0).
- `DataBinder` xử lý giá trị sai kiểu và field bị chặn bởi `allowedFields` như thế nào.

Tạo file `settings.gradle`:

~~~groovy
rootProject.name = 'spring-binding-api-probe'
~~~

Tạo file `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

def frameworkVersion = providers.gradleProperty('frameworkVersion')
        .orElse('6.2.0')
        .get()

dependencies {
    implementation "org.springframework:spring-context:$frameworkVersion"
}

application {
    mainClass = 'FrameworkApiProbe'
}
~~~

Tạo file `src/main/java/FrameworkApiProbe.java`:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class FrameworkApiProbe {

    public static class RegistrationForm {
        private Integer quantity;
        private String role;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    public static void main(String[] args) {
        boolean hasDeclarativeBinding = Arrays.stream(DataBinder.class.getMethods())
                .anyMatch(FrameworkApiProbe::isDeclarativeBindingSetter);

        RegistrationForm form = new RegistrationForm();
        DataBinder binder = new DataBinder(form);
        binder.setAllowedFields("quantity");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("quantity", "abc");
        input.add("role", "ADMIN");
        binder.bind(input);

        BindingResult result = binder.getBindingResult();
        System.out.println("hasDeclarativeBinding=" + hasDeclarativeBinding);
        System.out.println("quantity=" + form.getQuantity());
        System.out.println("role=" + form.getRole());
        System.out.println("typeMismatch=" + result.hasFieldErrors("quantity"));
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));
    }

    private static boolean isDeclarativeBindingSetter(Method method) {
        return method.getName().equals("setDeclarativeBinding")
                && method.getParameterCount() == 1
                && method.getParameterTypes()[0] == boolean.class;
    }
}
~~~

Chạy với JDK 17+ và Gradle đã cài:

~~~bash
gradle -q run
~~~

Với `frameworkVersion=6.2.0` mặc định, kết quả từ chương trình là:

~~~text
hasDeclarativeBinding=true
quantity=null
role=null
typeMismatch=true
suppressed=[role]
~~~

Giải thích: `quantity=abc` không chuyển thành `Integer` nên tạo field error dạng `typeMismatch`; `role` không nằm trong `allowedFields` nên bị suppress, không được gán. Đây là hai nguyên nhân khác nhau. Sử dụng `BindingResult` cho phép xem cả lỗi chuyển kiểu lẫn trường bị chặn.

Để kiểm tra API tại hai mốc khác:

~~~bash
gradle -q run -PframeworkVersion=6.0.0
gradle -q run -PframeworkVersion=6.1.0
~~~

Kỳ vọng dòng đầu lần lượt là:

~~~text
6.0.0 -> hasDeclarativeBinding=false
6.1.0 -> hasDeclarativeBinding=true
~~~

Đó là **bảng so sánh hai lần chạy**, không phải toàn bộ stdout thực tế ghép thành một lần chạy. Bốn dòng còn lại vẫn là các phép kiểm tra binding của ví dụ. Nếu dùng Gradle Wrapper thì thay `gradle` bằng `./gradlew` trên Linux/macOS hoặc `gradlew.bat` trên Windows.

Phép thử reflection chỉ cho biết chữ ký public đã có mặt. Nó không chứng minh cấu hình web đã bật tính năng. Muốn kiểm tra hoạt động của `setDeclarativeBinding(true)`, tạo thêm một test trên Spring 6.1+ gọi trực tiếp method và thử property binding/constructor binding phù hợp.

## 8. Tình huống 2: lỗi validation thay đổi khi dùng Spring MVC 6.1+

### 8.1. Hai loại validation trong controller

Ví dụ minh họa trong một Spring MVC application có Jakarta Bean Validation provider:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ValidationExampleController {

    public record CreateRequest(@NotBlank String name) {
    }

    @PostMapping("/people")
    public String create(@Valid @RequestBody CreateRequest request) {
        return request.name();
    }

    @GetMapping("/people/page")
    public String page(@RequestParam @Min(1) int page) {
        return "page=" + page;
    }
}
~~~

Đây là **ví dụ tích hợp**, cần ứng dụng host có Spring MVC cùng provider Jakarta Bean Validation. Hai đường xử lý khác nhau:

- `POST /people` với body JSON `{"name":""}`: sau khi JSON được đọc thành `CreateRequest`, `@Valid` kích hoạt validation đối tượng. Nếu method không có constraint trực tiếp khác làm kích hoạt method validation, Spring MVC có thể ném `MethodArgumentNotValidException`.
- `GET /people/page?page=0`: `@Min(1)` gắn trực tiếp vào tham số controller. Trên Spring MVC **6.1+**, method validation tích hợp có thể tạo `HandlerMethodValidationException`; xử lý dựa vào từng parameter thay vì chỉ một DTO.

Nếu controller được đặt `@Validated` **ở cấp class**, method validation có thể đi qua **AOP proxy**. Tài liệu Spring hướng dẫn bỏ class-level `@Validated` khi muốn dùng cơ chế method validation tích hợp của MVC từ 6.1. Tuy nhiên, không được xóa annotation tùy tiện trong mọi service: `MethodValidationPostProcessor` cho các bean dịch vụ ngoài controller là một cơ chế khác và có mục đích riêng.

### 8.2. Vì sao không thể suy ra exception chỉ từ @Valid?

`@Valid` dùng để cascade/đọc constraint trên đối tượng, nhưng **không tự nó là một constraint annotation trực tiếp trên method parameter**. Thêm `@NotNull`, `@Min` hoặc constraint khác ở parameter/method có thể làm đường xử lý chuyển sang method validation; khi ấy cả nested validation của `@Valid` có thể được method validation bao phủ.

Với `@ModelAttribute` hoặc `@RequestBody`, nếu đặt tham số `Errors`/`BindingResult` **ngay sau** đối tượng cần bind, controller có thể tự xử lý các lỗi phù hợp. Nhưng khi có lỗi method validation trên tham số khác không có `Errors` tương ứng, framework vẫn có thể ném `HandlerMethodValidationException`. Không nên viết một `@ExceptionHandler` duy nhất chỉ bắt `MethodArgumentNotValidException` rồi mặc định đã bao phủ mọi kiểu validation.

Bảng câu hỏi trước khi sửa:

| Quan sát | Kiểm tra trước |
| --- | --- |
| `@Valid` không báo lỗi | Provider, constraint, nguồn dữ liệu, annotation trên argument, validation groups |
| Lỗi mới thành `HandlerMethodValidationException` | Có direct constraint trên tham số/return không? Spring MVC có từ 6.1? |
| Exception đi từ AOP thay vì MVC | Controller có class-level `@Validated`? Có `MethodValidationPostProcessor`? |
| Có `BindingResult` nhưng controller không được gọi | Vị trí tham số có ngay sau model attribute không? Có lỗi trên parameter khác? |
| Response khác trước khi nâng cấp | Bắt đúng exception, xem `@ControllerAdvice`, `ResponseEntityExceptionHandler` và error response config |
| `quantity=abc` không tới validation business | Có lỗi conversion/binding `typeMismatch` trước khi validate không? |

Bản thân loại exception là một phần của quan sát. HTTP status và JSON body còn tùy exception resolver / Spring Boot error handling / `@ControllerAdvice`; đừng coi một response mẫu trong tutorial là hợp đồng mặc định cho mọi ứng dụng.

## 9. Tình huống 3: phân biệt DataBinder, Converter và JSON

Đọc đường dữ liệu trước khi quyết định API nào sẽ sửa:

~~~text
Query/Form/Path value
        |
        +-- MVC argument resolver / WebDataBinder
        |          |
        |          +-- ConversionService / Formatter
        |          +-- BindingResult: typeMismatch, rejectedValue, ...
        |          +-- Validator / Jakarta Validation provider
        |
        +-- Controller parameter hoặc @ModelAttribute object

JSON request body
        |
        +-- HttpMessageConverter / JSON mapper
        |          |
        |          +-- Deserialize object (Jackson tùy version/config)
        |          +-- Sau đó có thể validation nếu @Valid/@Validated
        |
        +-- @RequestBody object
~~~

Ví dụ cùng một field `LocalDate orderedOn`:

- Với `@ModelAttribute`, `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)` có thể hướng dẫn Spring formatting xử lý chuỗi ngày ở request.
- Với `@RequestBody` JSON, ngày được đọc bởi Jackson/deserializer. Spring MVC's `FormatterRegistry` không mặc nhiên thay đổi quy tắc của JSON mapper.
- Với `@RequestParam LocalDate`, conversion/formatting của MVC áp dụng dựa vào annotation/cấu hình tương ứng.

Khi thay Framework 6.x bằng 7.0 và hệ sinh thái Jackson cũng thay đổi, hãy lập test riêng cho **JSON body** và **form/query binding**. Không gộp hai lỗi chỉ vì thông báo cùng đề cập tên field.

## 10. Tình huống 4: chẩn đoán một API bị thiếu hoặc deprecated

### 10.1. Lỗi “cannot find symbol” khi nâng cấp

Ví dụ code cũ hoặc code sao chép từ tài liệu mới gọi một method không tồn tại trong bản đang dùng:

~~~text
error: cannot find symbol
  symbol:   method setDeclarativeBinding(boolean)
  location: variable binder of type DataBinder
~~~

Phân tích theo thứ tự:

1. Có đúng class `org.springframework.validation.DataBinder` hay một kiểu trùng tên?
2. `spring-context` trên **compileClasspath** thực tế là phiên bản nào?
3. Javadoc của phiên bản đó có method, đúng chữ ký/độ truy cập không?
4. Có đang nhìn nhầm Javadoc “current” của phiên bản mới hơn?
5. Nếu cần khả năng chỉ có từ 6.1, quyết định nâng **đồng bộ** Framework/Boot hoặc dùng một API tương thích bản cũ (ví dụ `setAllowedFields` cho property whitelist) theo đúng yêu cầu nghiệp vụ.

Lỗi runtime `NoSuchMethodError` có sắc thái khác: **bytecode được biên dịch theo API có method nhưng class thực chạy không có method tương ứng**. Kiểm tra cả compile classpath và runtime classpath; không chỉ đổi import.

### 10.2. Khi thấy @Deprecated

Đọc annotation và lý do deprecation trong Javadoc, sau đó tìm release note/upgrade guide. Phân loại:

- API vẫn chạy nhưng được khuyên chuyển sang hướng khác.
- Một overload không còn phù hợp, có overload mới thay thế.
- API đã bị loại khỏi một major mới và phải sửa source.
- Hợp đồng nullability hoặc default thay đổi nhưng phương thức vẫn còn.

Để so sánh, ghi bảng cụ thể:

| Mục | Bản nguồn | Bản đích | Bằng chứng |
| --- | --- | --- | --- |
| Class/method | Có/không, chữ ký | Có/không, chữ ký | Javadoc của hai artifact |
| Annotation & provider | Package, dependency | Package, dependency | BOM + Javadoc + build |
| Hành vi | Input → expected result | Input → actual result | Test ở hai bản |
| Lỗi | Exception và trường dữ liệu lỗi | Exception và trường dữ liệu lỗi | Stack trace + test |
| Giải pháp | Cấu hình hiện tại | Đổi config/code có mục tiêu | Release notes/upgrade guide |

Khi chưa chạy được test, nói rõ kết luận mới là **kiểm tra tài liệu**, chưa phải bằng chứng thực thi.

## 11. Bộ kiểm thử hồi quy cho validation/data binding

Một thay đổi Framework có thể làm controller vẫn biên dịch nhưng đổi loại lỗi hoặc thay đổi cách bind. Với mỗi migration, tạo các test có cùng input và assertion ở cả hai bản.

### 11.1. Ca kiểm thử tối thiểu

| Ca | Input điển hình | Assertion cần thiết |
| --- | --- | --- |
| Chuyển kiểu thành công | `quantity=12` | Java field là `Integer 12`, không có field error |
| Chuyển kiểu thất bại | `quantity=abc` | Có `typeMismatch`/binding error, không giả định business validator được gọi |
| Validation nghiệp vụ | `quantity=0` với `@Min(1)` | Lỗi constraint, phân biệt với lỗi parse |
| Field bị chặn | `role=ADMIN` khi chỉ cho bind `quantity` | `role` không thay đổi; xem suppressed fields |
| Thiếu tham số bắt buộc | Vắng `@RequestParam` | Missing value/argument error phù hợp |
| DTO rỗng/sai trường | JSON `{"name":""}` với `@NotBlank` | Validation xảy ra khi provider và annotation đúng |
| Direct constraint | `@RequestParam @Min(1) int page`, `page=0` | Loại đường validation theo bản Framework |
| Locale/format | `01/02/2026` theo quy tắc đã chọn | Parse/print chính xác theo format/locale khai báo |
| JSON vs form | Cùng field ngày nhận ở hai loại request | Đúng deserializer/binder cho từng đường |
| Exception handler | Request invalid | Status và error body theo hợp đồng API của ứng dụng |

Chú ý rằng test `@Min` chỉ có ý nghĩa khi đã cấu hình Bean Validation provider và cách kích hoạt validation phù hợp; kết quả “không có lỗi” trong một ứng dụng thiếu provider không chứng minh Framework cố ý bỏ constraint.

### 11.2. Kiểm tra source code và build sau nâng cấp

- Compile lại trên **JDK được hỗ trợ** bởi bản đích.
- Đọc dependency tree để không có nhiều dòng `spring-*` không tương thích.
- Kiểm tra package `javax.validation`/`jakarta.validation` và provider.
- Chạy unit test ở tầng `DataBinder`/`Validator` trước; sau đó test MVC với MockMvc hoặc server thật để xác nhận HTTP status và exception handling.
- Kiểm tra controller có `@Validated` cấp class; nếu mong muốn MVC built-in validation từ 6.1, đọc lại hướng dẫn migration.
- Kiểm tra source DTO và giới hạn field được bind; đặc biệt không cho client tùy ý cập nhật field quyền hạn.
- Tách test `@RequestBody` JSON khỏi `@ModelAttribute` form/query.
- Đọc release notes của cả minor/patch đích và nhật ký issue liên quan trước khi kết luận bug đã được sửa.
- Ghi command, version, input và actual output để lần nâng cấp sau có thể tái hiện.

## 12. Quy trình tra cứu mẫu từ một lỗi thực tế

Tình huống: sau khi cập nhật dependency, endpoint `POST /people` trả response lỗi khác trước. Đừng vội đổi exception handler; hãy thực hiện:

**Bước 1 – Chụp thông tin môi trường.** Ghi phiên bản `spring-webmvc`, `spring-web`, Jakarta Validator provider, Java và Spring Boot BOM. Lấy command kiểm tra dependency và giữ đầu ra có khả năng kiểm chứng.

**Bước 2 – Chụp input + chữ ký controller.** Ghi HTTP method, content type, body/query, annotation trên argument và class; kiểm tra `@Valid`, direct constraint như `@NotBlank`, vị trí `BindingResult`. Phải biết đây là JSON deserialization failure, binding failure hay validation failure.

**Bước 3 – Mở Javadoc đúng phiên bản.** Tìm `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `BindingResult` và method tương ứng. Nếu một class xuất hiện từ 6.1, đừng đưa handler cho class đó vào source compile trên 6.0.

**Bước 4 – Đọc Reference + release notes.** Tài liệu Spring MVC mô tả khi nào validation ở mức argument và khi nào ở mức method; ghi rõ điều kiện về class-level `@Validated`. Nếu ảnh hưởng servlet/container hoặc Jakarta provider, đọc thêm upgrade guide.

**Bước 5 – Viết test đầu vào cố định.** Tạo cùng một request invalid trên bản nguồn và bản đích, ghi nhận exception class, field/parameter errors, HTTP status và response body. Tách test JSON parse error khỏi Bean Validation.

**Bước 6 – Sửa đúng tầng.** Nếu thay đổi là exception validation, cập nhật `@ControllerAdvice`/`ResponseEntityExceptionHandler` hoặc hợp đồng error response. Nếu là input conversion, sửa formatter/converter hoặc định dạng request. Nếu là JSON, kiểm tra cấu hình JSON mapper. Nếu là mass assignment, sửa DTO/allowed fields.

**Bước 7 – Chốt bằng bằng chứng.** Đính kèm version, Javadoc, release note, test và kết quả sau sửa; không ghi “Spring tự đổi behavior” nếu chưa xác định thay đổi cụ thể.

## 13. Những nhầm lẫn phổ biến

**“Tôi đã đọc tài liệu mới nhất nên code phải đúng.”** Tài liệu “current” có thể thuộc nhánh mới hơn dependency. Luôn mở tài liệu/Javadoc của đúng phiên bản và kiểm tra API có mặt từ khi nào.

**“Spring Boot 4 và Spring Framework 4 là một.”** Không. Hai dự án có version độc lập; Spring Boot quản lý một tập thư viện bên dưới. Dùng dependency tree/BOM để xác định Framework.

**“Thêm `@Valid` là đủ để mọi validation hoạt động.”** Chưa chắc. Cần kiểm tra provider, constraints, argument resolver, method-level constraint và cơ chế AOP/MVC tương ứng.

**“Mọi lỗi nhập liệu đều là `MethodArgumentNotValidException`.”** Không. Spring MVC 6.1+ có method validation với `HandlerMethodValidationException`; conversion lỗi, JSON parse lỗi và missing argument còn có những đường xử lý khác.

**“`BindingResult` đặt ở đâu cũng được.”** Không. Trong method signature MVC, khi dùng nó để xử lý lỗi của một model attribute/argument, thường phải đặt ngay sau argument tương ứng; đồng thời cần xét lỗi ở các parameter khác.

**“`setAllowedFields` và `setDeclarativeBinding` hoàn toàn giống nhau.”** Không. `setAllowedFields` khai báo whitelist cho property binding; `setDeclarativeBinding(true)` (6.1+) quyết định chỉ áp dụng những đường binding được khai báo, bao gồm constructor binding và allowed property binding.

**“Một custom Converter xử lý mọi JSON.”** Không. `@RequestBody` JSON đi qua HTTP message converter và JSON mapper; conversion service phục vụ các đường binding phù hợp khác.

**“Deprecated nghĩa là method đã bị xóa.”** Không. Phải kiểm tra deprecation message, lịch trình removal và Javadoc của bản đích.

**“Cùng minor version thì patch không đổi hành vi.”** Không thể bảo đảm. Một bản vá có thể sửa bug hoặc cập nhật behavior. Khi tái hiện lỗi, ghi bản đầy đủ X.Y.Z.

**“Đổi import `javax` thành `jakarta` là đã nâng cấp xong.”** Sai. Runtime, provider, servlet stack, dependency graph và integration tests đều cần tương thích.

## 14. Checklist cuối cùng và tài liệu tham khảo

Với mỗi câu hỏi “API/hành vi này có thay đổi theo phiên bản không?”, hãy trả lời được:

1. **Đúng thư viện nào?** Full package/class/method và artifact chứa nó.
2. **Phiên bản thật là gì?** Dependency được resolve lúc compile và runtime; Boot/JDK/provider đi kèm.
3. **Tài liệu đúng phiên bản chưa?** Javadoc `@since`, deprecation, Reference, release notes, upgrade guide.
4. **Thay đổi thuộc loại nào?** Signature, annotation, default, exception, thứ tự binding/validation, behavior hay dependency.
5. **Bằng chứng runtime là gì?** Input, command, test, actual output ở từng bản.
6. **Đường code nào chịu ảnh hưởng?** `DataBinder`/`@ModelAttribute`, MVC method validation, JSON deserializer hay service-layer validation.
7. **Đã test hồi quy chưa?** Success, mismatch, constraint, field whitelist, HTTP response, locale, JSON/form separation.
8. **Đã ghi giới hạn của kết luận chưa?** Những điều phụ thuộc custom configuration và patch version.

Nguồn chính thức nên đối chiếu cho bài này:

- [Spring Framework – Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework – Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring MVC – Model Attribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC – InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.1.0 DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.x Upgrade Guide](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring Boot – Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Framework GitHub tags](https://github.com/spring-projects/spring-framework/tags)

Nắm được cách tra cứu này giúp bạn điều tra lỗi và nâng cấp Framework có căn cứ: **khóa version, tìm hợp đồng API, đối chiếu thay đổi, thử bằng đầu vào cố định, rồi mới sửa code hoặc cấu hình**.