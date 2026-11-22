# Record và đối tượng bất biến dùng constructor binding trong Spring MVC

## 1. Bài toán: tạo đối tượng đầu vào mà không cần setter

Trong ứng dụng Spring MVC, một HTTP request thường mang dữ liệu dạng chuỗi: `display-name=Mai`, `age=25`, `address.city=Hue`. Controller cần một đối tượng Java có kiểu rõ ràng để xử lý dữ liệu. Cách JavaBean truyền thống là gọi constructor rỗng rồi gán từng thuộc tính bằng setter. Tuy nhiên, với **Java record** hoặc lớp bất biến, các giá trị được đặt ngay lúc khởi tạo và không có setter.

**Constructor binding** giải quyết bài toán đó: Spring tìm constructor dữ liệu phù hợp, lấy các giá trị request theo tên tham số, chuyển kiểu, rồi gọi constructor để tạo đối tượng. Với record Java 17+, canonical constructor được suy ra từ các thành phần record nên đặc biệt phù hợp để biểu diễn dữ liệu đầu vào.

Kết quả cần đạt sau bài học:

- Phân biệt constructor binding với property/setter binding.
- Viết một record và một immutable class làm `@ModelAttribute`.
- Hiểu cách tên tham số, `@BindParam`, chuyển kiểu, dữ liệu lồng nhau và validation phối hợp.
- Xử lý lỗi qua `BindingResult` và tránh gán những trường ngoài ý muốn.
- Phân biệt constructor binding của MVC form với JSON deserialization của `@RequestBody`.

Phạm vi minh họa chính: **Java 17+, Spring Framework 6.1/6.2 (Spring Boot 3.x), Spring MVC Servlet**. Một số cơ chế trong các phiên bản khác có thay đổi nhỏ; hãy kiểm tra API đúng phiên bản của dự án.

## 2. Hai con đường binding và lựa chọn kiểu đối tượng

Giả sử client gửi form:

~~~text
display-name=Mai
age=25
address.city=Hue
address.street=Le Loi
~~~

Với **property binding**, ứng dụng thường có JavaBean khả biến:

~~~java
public class ProfileBean {
    private String displayName;
    private Integer age;

    public ProfileBean() {}

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { this.displayName = value; }

    public Integer getAge() { return age; }
    public void setAge(Integer value) { this.age = value; }
}
~~~

Ở đây Spring có thể tạo `ProfileBean` rồi gọi setter tương ứng. Đoạn mã chỉ minh họa JavaBean, chưa phải ứng dụng hoàn chỉnh.

Với **constructor binding**, có thể khai báo một record:

~~~java
public record ProfileInput(String displayName, Integer age) {}
~~~

Spring xác định tham số constructor `displayName` và `age`, chuyển `"25"` thành `Integer`, rồi tạo `new ProfileInput("Mai", 25)`. Không cần constructor rỗng hay setter. Record có accessor `displayName()` và `age()` chứ không tự sinh `getDisplayName()` hoặc `setDisplayName()`.

| Đặc điểm | JavaBean khả biến | Record / lớp bất biến |
| --- | --- | --- |
| Khởi tạo điển hình | Constructor rỗng rồi gọi setter | Constructor nhận dữ liệu |
| Cập nhật sau khởi tạo | Có thể đổi thuộc tính | Không đổi được thành phần `final` qua setter |
| Định nghĩa đầu vào được phép | Có thể gồm nhiều setter | Thể hiện ngay trong chữ ký constructor |
| Khả năng bị bind nhầm thuộc tính | Cần kiểm soát setter/allowed fields | Hạn chế thông qua tham số constructor; vẫn phải xem đối tượng lồng nhau |
| Validation | Dùng `@Valid`/`@Validated` | Cũng dùng `@Valid`/`@Validated` |

Điểm quan trọng: **record không tự động biến toàn bộ cấu trúc thành bất biến sâu**. Một record chứa `List` khả biến vẫn có thể trả ra danh sách để người khác sửa. Mục 8 sẽ xử lý vấn đề này.

## 3. Spring MVC gọi constructor ở bước nào?

Khi một handler có tham số `@ModelAttribute` và chưa có đối tượng tương ứng trong model, Spring MVC có thể tạo đối tượng từ default constructor hoặc primary/data constructor. Với record, canonical constructor là đường phù hợp.

~~~text
Request params / form fields / URI variables / headers
                          |
                          v
     Giải quyết @ModelAttribute và lấy/tạo binder
                          |
                          v
     @InitBinder cấu hình WebDataBinder nếu có
                          |
                          v
     Tìm data constructor và tên các tham số
                          |
                          v
     Tìm giá trị đầu vào, chuyển kiểu từng tham số
                          |
                          v
     Gọi constructor tạo record/immutable object
                          |
                          v
     Property binding nếu vẫn được cho phép
                          |
                          v
     @Valid / @Validated (khi được yêu cầu)
                          |
                          v
     BindingResult -> controller hoặc MVC exception
~~~

Đây là luồng khái niệm; không nên coi nó là cam kết rằng mọi handler đều bắt buộc khởi tạo đối tượng mới. Một `@ModelAttribute` có thể đã tồn tại trong model/session hoặc được lấy từ converter, khi đó cơ chế lấy đối tượng khác với lần tạo bằng constructor.

Đối với `DataBinder` lõi, Spring phân biệt rõ:

- **Constructor binding:** ánh xạ dữ liệu đầu vào tới *tham số constructor*, có thể đệ quy tạo các đối tượng con.
- **Property binding:** gán giá trị vào các *property có thể ghi*, ví dụ setter.
- **Type conversion:** đổi chuỗi request thành `Integer`, `LocalDate`, enum hoặc kiểu khác nhờ `ConversionService` / formatter.
- **Validation:** kiểm tra ràng buộc sau khi binding, khi có trigger như `@Valid`.

Spring MVC thông thường áp dụng cả constructor và property binding. Việc dùng record đơn giản không có setter giúp giới hạn các thành phần có thể bị thay đổi, nhưng không nên mặc định rằng toàn bộ bước property binding đã bị vô hiệu hóa. Phần 9 chỉ cách cấu hình constructor-only rõ ràng.

## 4. Ví dụ hoàn chỉnh: form request vào record bất biến

Tạo ứng dụng Spring Boot 3.x với Java 17 trở lên từ Spring Initializr và chọn các dependency **Spring Web** và **Validation**. Với Gradle Groovy, các dependency chính trong `build.gradle` là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Project do Spring Initializr sinh ra đã quản lý phiên bản plugin Spring Boot và cấu hình Java; không tự thêm phiên bản thư viện con trái với BOM của dự án.

### 4.1. File `src/main/java/com/example/binding/BindingApplication.java`

~~~java
package com.example.binding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingApplication.class, args);
    }
}
~~~

### 4.2. File `src/main/java/com/example/binding/CreateProfileForm.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.BindParam;

public record CreateProfileForm(
        @BindParam("display-name")
        @NotBlank String displayName,

        @NotNull @Min(18) Integer age,

        @Valid @NotNull Address address
) {
    public record Address(
            @NotBlank String city,
            String street
    ) {}
}
~~~

Trong DTO này:

1. `displayName` là tên thành phần Java; `@BindParam("display-name")` yêu cầu constructor binding đọc input tên `display-name`.
2. `age` có kiểu `Integer` nên bộ chuyển đổi có thể đổi `"25"` thành số `25`. `@NotNull` ngăn tuổi bị thiếu; `@Min(18)` kiểm tra giới hạn.
3. `address` có kiểu là record lồng nhau. Từ `address.city=Hue` và `address.street=Le Loi`, constructor binding có thể tạo `Address("Hue", "Le Loi")`, rồi truyền vào constructor của `CreateProfileForm`.
4. `@Valid` tại thành phần `address` yêu cầu validation đi tiếp vào đối tượng con; `@NotNull` đòi đối tượng con phải tồn tại. `@NotBlank` trên `city` bảo vệ trường bắt buộc.

Cả `CreateProfileForm` và `Address` đều không có setter. Dữ liệu sau khi khởi tạo được đọc qua `form.displayName()`, `form.age()`, `form.address().city()`.

### 4.3. File `src/main/java/com/example/binding/ProfileController.java`

~~~java
package com.example.binding;

import jakarta.validation.Valid;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    @InitBinder("form")
    void configureFormBinder(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("form") CreateProfileForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            var messages = errors.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "code", Objects.toString(error.getCode(), "invalid"),
                            "message", Objects.toString(
                                    error.getDefaultMessage(), "Không hợp lệ")
                    ))
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", messages));
        }

        return ResponseEntity.ok(Map.of(
                "displayName", form.displayName(),
                "age", form.age(),
                "city", form.address().city()
        ));
    }
}
~~~

`@InitBinder("form")` chỉ cấu hình binder cho model attribute mang tên `form`. Lệnh `setDeclarativeBinding(true)` bật chế độ trong đó constructor binding luôn được dùng, còn setter binding chỉ có hiệu lực nếu cấu hình `allowedFields` tương ứng. Ví dụ này không khai báo `allowedFields`, vì vậy input được dựng theo constructor. Không thêm setter để lách đặc điểm bất biến của record.

`@Valid` trên `@ModelAttribute("form")` yêu cầu Bean Validation chạy sau khi đối tượng được bind. `BindingResult errors` phải **đứng ngay sau** tham số được bind/validate. Nếu có lỗi, controller trả HTTP 400; nếu thành công, trả HTTP 200 và dữ liệu đầu vào đã chuyển kiểu.

### 4.4. Chạy và thử request

Tại thư mục gốc dự án có Gradle Wrapper, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Với project được tạo bằng Maven, dùng lệnh Maven tương ứng.

Gửi form hợp lệ trong terminal có `curl`:

~~~bash
curl -i -X POST http://localhost:8080/profiles -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "display-name=Mai" --data-urlencode "age=25" --data-urlencode "address.city=Hue" --data-urlencode "address.street=Le Loi"
~~~

HTTP status kỳ vọng là **200 OK**. Body JSON có nội dung tương đương (thứ tự thuộc tính JSON không được đảm bảo):

~~~json
{"displayName":"Mai","age":25,"city":"Hue"}
~~~

Thử giá trị có thể chuyển kiểu nhưng không hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/profiles -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "display-name=" --data-urlencode "age=17" --data-urlencode "address.city="
~~~

Kết quả kỳ vọng **400 Bad Request**, các field được báo lỗi tương ứng với `displayName`, `age`, `address.city`. Tên mã lỗi và lời nhắn có thể khác theo validator provider, message source và locale, nên không giả định mảng lỗi có thứ tự cố định.

Thử lỗi chuyển kiểu của tham số constructor:

~~~bash
curl -i -X POST http://localhost:8080/profiles -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "display-name=Mai" --data-urlencode "age=abc" --data-urlencode "address.city=Hue"
~~~

`age=abc` không thể đổi thành `Integer`. Đây là **binding/conversion error**, có thể được phản ánh trong `BindingResult` (thường có mã `typeMismatch`), chứ không phải `@Min(18)` đã chạy trên chuỗi `abc`. Tùy tình huống khởi tạo và cách xử lý lỗi, Spring có thể chuyển lỗi thành exception nếu controller không khai báo `BindingResult` phù hợp.

## 5. Vì sao tên constructor parameter quan trọng?

Constructor binding không tìm setter; nó phải xác định cặp **tên đầu vào → tham số constructor**. Theo mặc định, tên lấy từ thông tin tham số lưu trong bytecode. Với record, canonical constructor biểu diễn rõ thứ tự và tên các thành phần. Với class Java thông thường, hãy biên dịch kèm metadata tên tham số, thường là cờ `-parameters`, nếu muốn Spring khớp theo tên; Spring Boot build tooling thường hỗ trợ cấu hình này.

Với Gradle, có thể khai báo minh bạch:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}
~~~

Đoạn Groovy này bổ sung vào `build.gradle` nếu build hiện tại chưa bật cờ tương ứng; không cần lặp lại nếu project đã cấu hình.

Tên trên HTTP đôi khi không hợp lệ theo quy ước tên Java (ví dụ `display-name`). Dùng `@BindParam` ở constructor parameter hoặc field tương ứng để ánh xạ:

~~~java
public record SearchForm(
        @BindParam("search-text") String text,
        Integer page
) {}
~~~

Ở đây `search-text=java` đi vào `text`, còn `page=2` đi vào `page`. `@BindParam` là annotation **dành cho Spring DataBinder constructor binding**, không tự đổi tên key JSON khi dùng Jackson. Nếu một endpoint nhận JSON và muốn key `search-text`, cần cấu hình riêng cho JSON, chẳng hạn `@JsonProperty("search-text")`.

Cần lưu ý rằng nhiều constructor hoặc constructor phụ trên immutable class có thể khiến cách chọn constructor không rõ ràng. Nên thiết kế một data constructor duy nhất, public khi thích hợp; record canonical constructor là lựa chọn thuận tiện.

## 6. Không dùng record vẫn có thể tạo lớp bất biến

Không bắt buộc phải chọn record. Một class `final` có thuộc tính `private final` và constructor đầy đủ tham số cũng dùng constructor binding:

~~~java
package com.example.binding;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.BindParam;

public final class CreateTeamForm {
    private final String teamName;
    private final Integer size;

    public CreateTeamForm(
            @BindParam("team-name") String teamName,
            Integer size
    ) {
        this.teamName = teamName;
        this.size = size;
    }

    @NotBlank
    public String getTeamName() {
        return teamName;
    }

    @NotNull
    public Integer getSize() {
        return size;
    }
}
~~~

Đây là tệp Java độc lập có thể biên dịch trong project đã thêm các dependency nêu ở mục 4; để dùng trong handler, khai báo `@Valid @ModelAttribute CreateTeamForm form` và `BindingResult` đúng vị trí. Nó không có constructor rỗng/setter. `@BindParam("team-name")` ánh xạ `team-name` tới `teamName`.

Đặt ràng buộc Bean Validation trên getter là một cách hợp lệ để kiểm tra trạng thái đối tượng sau khởi tạo; cũng có thể đặt constraint ở field. Cấu hình `@Valid` vẫn cần để kích hoạt validation khi handler nhận form.

Chọn record khi dữ liệu thuần và muốn ít boilerplate. Chọn class bất biến khi cần kiểm soát API, thêm hành vi nội tại, hoặc có ràng buộc thiết kế không phù hợp record.

## 7. Nested object, collection và formatter trong constructor binding

Constructor binding không chỉ áp dụng cho những trường đơn giản. Spring có thể dựng đối tượng lồng nhau từ đường dẫn field:

~~~java
public record AddressInput(String city, String district) {}

public record ContactInput(String name, AddressInput address) {}
~~~

Với các request parameter `name=Lan`, `address.city=DaNang`, `address.district=HaiChau`, Spring có thể tạo `ContactInput("Lan", new AddressInput("DaNang", "HaiChau"))`.

Nó cũng hỗ trợ collection, map và array qua khóa có chỉ số, ví dụ:

~~~java
public record LineInput(String sku, Integer quantity) {}

public record BasketInput(java.util.List<LineInput> items) {}
~~~

Các trường `items[0].sku=BOOK`, `items[0].quantity=2`, `items[1].sku=PEN`, `items[1].quantity=3` biểu diễn hai phần tử. Đây là **định nghĩa kiểu và ví dụ key**, không phải ứng dụng MVC hoàn chỉnh; để đánh giá dữ liệu lồng nhau, thêm annotation Bean Validation phù hợp (ví dụ `@Valid` trên collection/element, `@Size` để ràng buộc số lượng).

Không mặc định rằng số phần tử, độ sâu hay kích thước input bên ngoài luôn an toàn. Cần giới hạn các collection được phép nhận, kích thước request, và kiểm soát việc bind trường nhạy cảm.

Đối với tham số có kiểu ngày tháng, có thể dùng formatter:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public record VisitForm(
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate visitDate
) {}
~~~

Đoạn này mô tả việc dùng `2026-11-02` làm giá trị form tương ứng. `LocalDate` là kiểu dữ liệu, còn `@DateTimeFormat` giúp Spring chọn định dạng chuyển đổi. Khi input sai định dạng, lỗi thuộc giai đoạn conversion/binding, trước validation nghiệp vụ.

## 8. Record bất biến nông: bảo vệ collection và dữ liệu lồng nhau

Trong Java, các component field của record là `final`, nhưng **`final` chỉ cố định tham chiếu**, không làm đối tượng phía trong trở nên bất biến. Ví dụ `record Filters(List<String> tags) {}` vẫn có thể chứa `ArrayList` bị sửa sau khi tạo record.

Có thể dùng defensive copy trong compact canonical constructor. Đoạn Java thuần sau **biên dịch và chạy độc lập trên Java 17+**, không cần Spring.

Tệp `RecordCopyDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordCopyDemo {
    record Filters(List<String> tags) {
        Filters {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        var original = new ArrayList<>(List.of("java"));
        var filters = new Filters(original);

        original.add("spring");
        System.out.println(filters.tags());

        try {
            filters.tags().add("mvc");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Danh sách không thể sửa");
        }
    }
}
~~~

Chạy:

~~~bash
javac RecordCopyDemo.java
java RecordCopyDemo
~~~

Stdout chính xác:

~~~text
[java]
Danh sách không thể sửa
~~~

`List.copyOf` tạo snapshot bất biến của danh sách, nên việc thay đổi `original` không tác động lên `filters.tags()`. Nó cũng từ chối phần tử `null`; hãy xác định quy tắc xử lý `null` phù hợp khi dựng DTO từ dữ liệu bên ngoài.

Một record có trường kiểu JavaBean khả biến vẫn cần xem xét: tuy không gán lại được tham chiếu, client vẫn có thể đổi trạng thái đối tượng con. Nếu muốn bảo toàn tính bất biến sâu, dùng các đối tượng lồng nhau bất biến và bản sao bảo vệ phù hợp.

Không nên đưa logic phức tạp hoặc ném exception bất ngờ vào constructor để thay thế toàn bộ validation. Ví dụ ném `IllegalArgumentException` khi tuổi nhỏ hơn 18 có thể làm thất bại khởi tạo trước khi Bean Validation ghi lỗi vào `BindingResult`. Với lỗi nhập liệu thông thường, dùng constraint như `@Min` và xử lý `BindingResult` để có thông báo theo field.

## 9. Kiểm soát setter binding và tránh mass assignment

HTTP request là đầu vào **không tin cậy**. Một entity như `UserEntity` có thể chứa các trường `role`, `enabled`, `ownerId`; bind trực tiếp entity đó từ request sẽ tạo nguy cơ client gửi thêm thuộc tính ngoài dự kiến.

Thiết kế an toàn nên dùng **DTO đầu vào riêng**, với constructor chỉ bao gồm các giá trị mà client được phép cung cấp. Sau validation, service ánh xạ DTO sang đối tượng domain và tự điền các giá trị thuộc quyền server.

Vì Spring MVC mặc định hỗ trợ cả constructor và property binding, có thể yêu cầu chỉ dùng constructor binding cho một model attribute:

~~~java
@InitBinder("form")
void configureFormBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
~~~

Đoạn trên là fragment trong controller; import `org.springframework.web.bind.annotation.InitBinder` và `org.springframework.web.bind.WebDataBinder`. `setDeclarativeBinding(true)` có nghĩa:

- Constructor binding tiếp tục hoạt động cho những tham số mà constructor khai báo.
- Setter/property binding chỉ hoạt động khi có danh sách `allowedFields` được khai báo rõ.
- Bật chế độ này **không thay thế** validation, phân quyền, kiểm soát kiểu dữ liệu hoặc quy tắc nghiệp vụ.

Nếu cần áp dụng cho nhiều controller, có thể cấu hình thông qua `@ControllerAdvice` và `@InitBinder`, nhưng phải kiểm tra tác động lên những form khác đang dùng property binding. Trường hợp vẫn cần setter, khai báo `binder.setAllowedFields("firstName", "lastName")` để giới hạn rõ các trường được ghi.

Ví dụ gửi `role=ADMIN` đến `CreateProfileForm` ở mục 4: thành phần `role` không tồn tại trong data constructor và binder được cấu hình declarative, nên controller không dùng nó để thay đổi role. **Trường dư không nhất thiết bị tự động báo 400**; nếu API yêu cầu từ chối input không khai báo, cần bổ sung chính sách xác thực request riêng.

Không dùng record hay final class như một cơ chế ủy quyền. Một DTO bất biến vẫn có thể chứa trường nhạy cảm nếu lập trình viên đưa trường đó vào constructor; quyền ghi các trường ấy phải được kiểm soát từ thiết kế API và tầng nghiệp vụ.

## 10. Validation và `BindingResult` với constructor binding

Constructor binding chịu trách nhiệm **tạo đối tượng có kiểu**, còn Bean Validation chịu trách nhiệm **kiểm tra ràng buộc sau binding**. Gắn constraint lên record component chưa đủ để tự động thực hiện ở mọi handler. Với `@ModelAttribute`, khai báo `@Valid` hoặc `@Validated` trên tham số controller:

~~~java
@PostMapping("/example")
public String handle(
        @Valid @ModelAttribute("form") CreateProfileForm form,
        BindingResult errors
) {
    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "success";
}
~~~

Đây là **fragment** của controller dùng render view MVC, không thay thế ví dụ `@RestController` ở mục 4.

Hai dạng lỗi cần phân biệt:

| Input | Giai đoạn / kết quả |
| --- | --- |
| `age=25` | Chuyển chuỗi thành `Integer 25`; đạt `@Min(18)`. |
| `age=17` | Constructor binding có thể thành công; Bean Validation phát hiện nhỏ hơn 18. |
| `age=abc` | Chuyển kiểu sang `Integer` thất bại; lỗi binding/conversion, thường có mã `typeMismatch`. |
| `display-name=` | Tham số chuỗi được đọc, `@NotBlank` phát hiện trống. |
| Thiếu `address.city` | Đối tượng con hoặc thuộc tính của nó không đầy đủ; `@NotNull` và `@NotBlank` giúp ghi lỗi phù hợp khi validation được chạy. |

`BindingResult` có thể chứa `FieldError` và `ObjectError`. Có thể đọc `errors.getFieldErrors()`, `errors.getFieldError("age")`, `errors.hasFieldErrors("address.city")` và `errors.hasErrors()`. Tùy lỗi, `getRejectedValue()` có thể cung cấp giá trị request không hợp lệ; đừng đưa dữ liệu nhạy cảm vào log hoặc phản hồi công khai.

`BindingResult` cần đứng ngay sau tham số mà nó mô tả. Nếu thiếu đối số này, Spring MVC thường chuyển lỗi validation của `@ModelAttribute` thành `MethodArgumentNotValidException`; trong handler có method validation áp dụng cho các ràng buộc đặt trực tiếp trên tham số, ngoại lệ có thể là `HandlerMethodValidationException`. Không nên bắt chung mọi lỗi HTTP 400 rồi coi tất cả là lỗi constructor.

Lưu ý đặc biệt: constructor có thể tự ném exception khi dữ liệu không phù hợp (ví dụ `Objects.requireNonNull(...)` hoặc invariant). Khi đó đối tượng có thể chưa được tạo và luồng xử lý khác với lỗi constraint đi qua `BindingResult`. Chỉ đặt invariant không thể vi phạm trong constructor; đối với lỗi dữ liệu người dùng dự kiến gặp, ưu tiên hệ thống validator.

## 11. Khác biệt với `@RequestBody` và JSON

Cùng là record Java, nhưng hai cách nhận request đi qua các cơ chế khác nhau.

- **`@ModelAttribute` + form/query:** Spring MVC sử dụng cơ chế `WebDataBinder` để tạo model attribute, constructor binding và (nếu bật) property binding.
- **`@RequestBody` + JSON:** `HttpMessageConverter`, thường dùng Jackson, deserialize JSON thành record bằng khả năng ánh xạ constructor của thư viện JSON. Đây **không phải** luồng constructor binding của `DataBinder` đối với request parameters.

Ví dụ fragment handler nhận JSON:

~~~java
@PostMapping(path = "/json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> createJson(
        @Valid @RequestBody CreateProfileForm request,
        BindingResult errors
) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Dữ liệu không hợp lệ");
    }
    return ResponseEntity.ok("accepted");
}
~~~

Đây là đoạn minh họa thuộc một controller có import tương ứng. JSON thông thường:

~~~json
{
  "displayName": "Mai",
  "age": 25,
  "address": {
    "city": "Hue",
    "street": "Le Loi"
  }
}
~~~

Chú ý `@BindParam("display-name")` ở DTO không tự khiến Jackson tìm key `"display-name"`; muốn đổi tên property JSON, dùng cơ chế annotation/naming strategy của Jackson, chẳng hạn `@JsonProperty`.

Nếu JSON sai cú pháp hoặc không thể deserialize, Spring thường báo `HttpMessageNotReadableException` trước validation. Nếu JSON tạo được đối tượng nhưng vi phạm constraint và không có `BindingResult` tại chỗ, thường phát sinh `MethodArgumentNotValidException`. Phân biệt đúng hai giai đoạn giúp chọn mã lỗi và thông báo trả về.

## 12. Kiểm thử constructor binding thay vì chỉ kiểm thử constructor Java

Tạo unit test gọi `new CreateProfileForm(...)` chỉ chứng minh constructor hoạt động; nó **không chứng minh** Spring ánh xạ tên field, xử lý `@BindParam`, khởi tạo nested record, chuyển kiểu và chạy validation. Dùng `MockMvc` để đi qua Spring MVC:

Tệp `src/test/java/com/example/binding/ProfileControllerTest.java`:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void bindNestedImmutableRecordsSuccessfully() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("display-name", "Mai")
                    .param("age", "25")
                    .param("address.city", "Hue")
                    .param("address.street", "Le Loi"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Mai"))
                .andExpect(jsonPath("$.age").value(25))
                .andExpect(jsonPath("$.city").value("Hue"));
    }

    @Test
    void rejectBusinessConstraintViolations() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("display-name", "")
                    .param("age", "17")
                    .param("address.city", ""))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectConstructorArgumentConversionError() throws Exception {
        mvc.perform(post("/profiles")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("display-name", "Mai")
                    .param("age", "not-a-number")
                    .param("address.city", "Hue"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy qua Gradle Wrapper:

~~~bash
./gradlew test --tests com.example.binding.ProfileControllerTest
~~~

Trên Windows: `gradlew.bat test --tests com.example.binding.ProfileControllerTest`. Ba test phân biệt: (1) constructor binding + nested record + đổi tên tham số; (2) lỗi constraint; (3) lỗi conversion. Nếu cấu hình MVC hoặc phiên bản Spring khác, nên kiểm tra phản hồi và ngoại lệ thực tế thay vì giả định mọi lỗi có cùng JSON.

Có thể bổ sung ca kiểm thử gửi `role=ADMIN` để xác nhận DTO không dùng trường này và việc phân quyền được quyết định bởi service. Nếu cấu hình cho phép property binding có chủ ý, cần kiểm thử cả những field nằm ngoài `allowedFields`.

## 13. Các lỗi thường gặp

1. **Cho rằng record phải có constructor rỗng.** Record không cần setter hoặc no-args constructor trong luồng constructor binding. Spring tạo object bằng canonical/data constructor khi đủ điều kiện.
2. **Thiếu metadata tên tham số cho class thường.** Nếu không có tên runtime và không khai báo `@BindParam`, Spring không có căn cứ đáng tin cậy để khớp request field với constructor argument. Kiểm tra `-parameters` và cấu hình build.
3. **Dùng tên request không khớp tên Java.** `display-name` và `displayName` là hai key khác nhau; cấu hình `@BindParam` đúng nơi, rồi kiểm thử request thực.
4. **Nhầm constructor binding form với JSON.** `@BindParam` không phải `@JsonProperty` và `@RequestBody` đi qua message converter.
5. **Cho rằng record bất biến sâu.** `List`, `Map` hoặc đối tượng con mutable vẫn có thể bị sửa; cân nhắc defensive copy và DTO lồng nhau bất biến.
6. **Bỏ `@Valid`/`BindingResult`.** Constraint trên record chỉ được chạy khi validation được kích hoạt; đặt `BindingResult` liền kề đối tượng để controller xử lý lỗi.
7. **Dùng kiểu primitive cho mọi input bắt buộc.** Với form có thể thiếu giá trị, `Integer` + `@NotNull` thường mô tả lỗi rõ hơn `int` nhận giá trị mặc định hoặc lỗi conversion tùy ngữ cảnh.
8. **Ném exception nghiệp vụ tùy ý trong constructor.** Một constructor không tạo được instance không tương đương với Bean Validation có danh sách `FieldError`. Dùng constraint cho lỗi input dự kiến và dành invariant constructor cho quy tắc cấu trúc thực sự.
9. **Bind trực tiếp entity có trường nhạy cảm.** Constructor binding giúp giới hạn bề mặt đầu vào nhưng không thay thế DTO riêng, phân quyền và kiểm soát field được phép.
10. **Bật `setDeclarativeBinding(true)` trên toàn ứng dụng mà không kiểm tra form khác.** Form dựa trên setter có thể ngừng nhận dữ liệu nếu chưa khai báo `allowedFields`; áp dụng cấu hình theo phạm vi dự kiến.

## 14. Checklist áp dụng

Khi thiết kế một đối tượng đầu vào dạng record hoặc immutable class cho Spring MVC:

- Chọn DTO dành riêng cho HTTP input; liệt kê đúng những thành phần client được phép gửi.
- Dùng một data constructor rõ ràng; với class thường bảo đảm metadata tên tham số hoặc `@BindParam`.
- Định nghĩa đúng kiểu (`Integer`, `LocalDate`, record lồng nhau, collection) và formatter khi cần.
- Áp dụng Bean Validation trên thành phần/field/getter, cùng `@Valid`/`@Validated` trên handler; thêm `@Valid` cho những đối tượng con cần validation đệ quy.
- Đặt `BindingResult` ngay sau `@ModelAttribute` nếu controller cần tự trả lỗi.
- Cân nhắc `setDeclarativeBinding(true)` để chỉ dùng constructor, và kiểm soát riêng property binding khi được cho phép.
- Bảo vệ collection mutable bằng bản sao, kiểm soát kích thước/depth của dữ liệu và không bind thẳng entity nhạy cảm.
- Kiểm thử qua HTTP/MockMvc cả dữ liệu hợp lệ, thiếu field, sai kiểu, sai constraint và field bổ sung.

**Ghi nhớ:** constructor binding dựng đối tượng từ các tham số do constructor định nghĩa; record là một cách ngắn gọn để thể hiện đối tượng đầu vào bất biến. Trong Spring MVC, lựa chọn này cần đi cùng validation, xử lý lỗi, quy tắc chuyển kiểu và giới hạn field để tạo API dễ hiểu và an toàn.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — `@ModelAttribute` và constructor binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — MVC Data Binding và Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
