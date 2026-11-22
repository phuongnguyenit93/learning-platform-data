# Validator không trạng thái và an toàn khi dùng đồng thời trong Spring

## 1. Vì sao một Spring Validator cần an toàn khi dùng đồng thời?

Trong ứng dụng Spring MVC, nhiều request HTTP có thể đang được xử lý trên các thread khác nhau. Một lớp được đánh dấu `@Component` mặc định là **singleton trong Spring container**: cùng một đối tượng bean có thể được nhiều controller, binder và request tham chiếu. Nếu bean này triển khai `org.springframework.validation.Validator`, phương thức `validate(Object, Errors)` có thể bị gọi gần như đồng thời với những đối tượng đầu vào khác nhau.

Mục tiêu của một **validator không trạng thái (stateless validator)** là biến mỗi lần kiểm tra thành một phép xử lý độc lập: đọc đối tượng đầu vào hiện tại, tính toán quy tắc và ghi lỗi vào đối tượng `Errors` của **chính lần gọi đó**. Không giữ dữ liệu đang kiểm tra hay đối tượng `Errors` trong field dùng chung.

Ví dụ: Request A kiểm tra khoảng thời gian `start=2, end=5`, còn request B kiểm tra `start=8, end=3`. Cùng một instance `IntervalValidator` có thể phục vụ cả hai. Kết quả mong muốn: A hợp lệ, B có lỗi ở `end`. Nếu validator giữ `currentForm` hoặc `currentErrors` trong field, thread A có thể vô tình sử dụng trạng thái mà thread B vừa ghi, dẫn tới thông báo sai hoặc trộn lỗi giữa hai người dùng.

Bài này tập trung vào `Spring Validator`, interface `supports(Class<?>)` / `validate(Object, Errors)`, cách đăng ký trong Spring MVC, cách thiết kế stateless, kiểm thử đồng thời và những giới hạn cần nhớ. Ví dụ dùng **Java 17+ và Spring Framework 6.x / Spring Boot 3.x**.

## 2. Hợp đồng `org.springframework.validation.Validator`

Spring cung cấp interface (rút gọn ý nghĩa) với hai phương thức:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

- `supports(Class<?>)` cho Spring biết validator có khả năng kiểm tra loại đối tượng nào. Nó phải đưa ra câu trả lời nhất quán với kiểu dữ liệu và không cần sửa trạng thái của bean.
- `validate(Object target, Errors errors)` kiểm tra **target của lần gọi hiện tại**, dùng `errors.reject(...)` cho lỗi đối tượng hoặc `errors.rejectValue(...)` cho lỗi một field. Phương thức thường không trả về giá trị; kết quả nằm trong `Errors`.
- `Errors` là nơi tích lũy thông tin lỗi của một lượt validation. Trong MVC, `BindingResult` mở rộng `Errors` và còn chứa thông tin binding, rejected value, field error.
- Spring `Validator` khác với `jakarta.validation.Validator` của Bean Validation, dù `LocalValidatorFactoryBean` có thể kết nối hai hệ thống. Đừng nhầm hai interface này khi khai báo import.

Đoạn interface phía trên dùng để minh họa hợp đồng, không phải source code định nghĩa lại interface của Spring. Một lớp thực tế chỉ cần `implements Validator`.

Dòng xử lý phổ biến:

~~~text
HTTP request A                   HTTP request B
     |                                |
  Bind A                           Bind B
     |                                |
Errors A                         Errors B
     |                                |
     +---------> cùng bean <----------+
                  Validator
                     |
          validate(target, errors)
          dùng biến cục bộ mỗi lần
                     |
                kết quả riêng
         Errors A          Errors B
~~~

**Điểm then chốt:** dùng chung **mã quy tắc và cấu hình chỉ đọc** là được; **đầu vào, biến tạm, kết quả lỗi của từng request** phải độc lập. Điều này cũng áp dụng khi validator được gọi từ service hoặc batch job thay vì MVC.

## 3. “Không trạng thái” không có nghĩa là “không được có field”

Một validator stateless vẫn có thể có các field biểu diễn **cấu hình không đổi** hoặc **dependency an toàn khi dùng đồng thời**:

~~~java
public final class QuantityValidator implements Validator {
    private final int maxQuantity;

    public QuantityValidator(int maxQuantity) {
        if (maxQuantity <= 0) {
            throw new IllegalArgumentException("maxQuantity phải dương");
        }
        this.maxQuantity = maxQuantity;
    }

    // supports(...) và validate(...) dùng maxQuantity ở chế độ chỉ đọc.
}
~~~

Đây là đoạn **minh họa một phần**; cần triển khai hai phương thức của `Validator` để thành lớp biên dịch đầy đủ. `maxQuantity` có thể là cấu hình được injection một lần. Sau khi bean được khởi tạo, mọi request chỉ đọc giá trị ấy.

Phân biệt ba loại trạng thái:

| Trạng thái | Ví dụ | Có nên giữ trong validator singleton? |
| --- | --- | --- |
| Cấu hình bất biến | `private final int maxQuantity`, tập mã hợp lệ bất biến | Có, nếu không bị thay đổi sau khi khởi tạo |
| Dependency chia sẻ | Service/Repository/cache được thiết kế thread-safe | Có điều kiện: phải xem bản thân dependency và cách dùng |
| Trạng thái theo request | `currentUser`, `lastInput`, `currentErrors`, `StringBuilder` tích lũy lỗi | Không |

`final` bảo vệ việc **gán lại tham chiếu**, chứ không biến nội dung của một `ArrayList` hoặc `HashMap` thành bất biến. Ví dụ `private final Map<String, Rule> rules = new HashMap<>()` vẫn cho phép thay đổi map. Nếu chỉ muốn tra cứu cấu hình, tạo bản sao bất biến khi khởi tạo bằng `Map.copyOf(...)` hoặc `Set.copyOf(...)`, và bảo đảm các phần tử bên trong cũng được dùng an toàn.

Không có một annotation `@Component`, `@Service` hay `@Scope("singleton")` nào tự bảo đảm thread safety. Singleton mô tả **vòng đời/chia sẻ instance**, còn thread safety là tính chất của implementation và dependencies.

## 4. Phản ví dụ: lưu `Errors` và target vào field

Đoạn dưới đây **cố ý sai** để thấy nguyên nhân race condition:

~~~java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class UnsafeIntervalValidator implements Validator {
    private Errors currentErrors;
    private IntervalForm currentForm;

    @Override
    public boolean supports(Class<?> clazz) {
        return IntervalForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        currentForm = (IntervalForm) target;
        currentErrors = errors;

        if (currentForm.getStart() > currentForm.getEnd()) {
            currentErrors.rejectValue(
                    "end", "interval.order",
                    "Điểm kết thúc phải >= điểm bắt đầu"
            );
        }
    }
}
~~~

Đây là **fragment dùng cùng `IntervalForm` được định nghĩa ở mục 6**, chỉ dành cho phân tích; không đăng ký lớp này làm bean thực tế.

Một lịch thực thi có thể xảy ra:

~~~text
Thread A: currentForm = formA
Thread A: currentErrors = errorsA
                   [tạm dừng]
Thread B: currentForm = formB
Thread B: currentErrors = errorsB
Thread B: kiểm tra formB, ghi errorsB
Thread A: tiếp tục, đọc currentForm (nay là formB)
Thread A: ghi vào currentErrors (nay là errorsB)
~~~

Kết quả là `errorsA` có thể không nhận được lỗi đáng lẽ phải có, trong khi `errorsB` nhận lỗi trùng hoặc sai ngữ cảnh. Không cần có hàng nghìn request mới gặp vấn đề: chỉ cần hai lần gọi chồng thời điểm đủ tạo interleaving bất lợi.

Lỗi tương tự xảy ra nếu giữ các field `lastCheckedUsername`, `currentLocale`, `requestId`, `List<FieldError> pendingErrors`, bộ đệm `StringBuilder`, bộ formatter không thread-safe, hoặc một bean có thuộc tính mutable để truyền ngầm dữ liệu giữa các lần gọi.

Giải pháp mặc định là **xóa trạng thái theo request khỏi bean** và dùng biến cục bộ trong phương thức. Thêm `synchronized` để “chữa cháy” không giải quyết bản chất thiết kế và có thể làm mọi request phải xếp hàng; hơn nữa những method khác đọc/ghi field chung vẫn có thể bỏ qua khóa.

## 5. Thiết kế validator đúng: cấu hình `final`, biến cục bộ, `Errors` của caller

Một implementation phù hợp có thể có dạng:

~~~java
@Override
public void validate(Object target, Errors errors) {
    IntervalForm form = (IntervalForm) target;
    Integer start = form.getStart();
    Integer end = form.getEnd();

    if (start == null || end == null) {
        return;
    }
    if (end < start) {
        errors.rejectValue("end", "interval.order",
                "Điểm kết thúc không được nhỏ hơn điểm bắt đầu");
    }
}
~~~

Trong đoạn này, `form`, `start`, `end` và tham số `errors` là **biến cục bộ/tham số invocation**. Mỗi thread có stack frame riêng, nên những biến đó không ghi đè lên nhau. Lớp validator không lưu `form` hoặc `errors` dưới dạng field.

Lưu ý: biến cục bộ có thể chứa **tham chiếu đến một đối tượng chia sẻ**. Vì vậy, chỉ dùng biến cục bộ chưa đủ nếu mã bên trong vẫn ghi vào singleton, static map, cache không an toàn hoặc một entity chia sẻ. Ngoài ra, đối tượng đầu vào phải thuộc một request hoặc được quản lý riêng; **không dùng lại cùng một DTO mutable cho các request**.

Các quy tắc thiết kế thực tế:

1. `supports` dựa trên loại class, không dựa vào “đối tượng cuối cùng đã kiểm tra”.
2. `validate` đọc `target` và ghi **duy nhất** vào `Errors` được truyền vào lần gọi hiện tại.
3. Các giá trị cấu hình ổn định nên là `final` hoặc immutable snapshot.
4. Nếu cần truy vấn service hoặc DB, đánh giá tính an toàn của service, transaction và side effect độc lập với stateless validator.
5. Kết quả validation cần có cùng ý nghĩa với cùng input và cùng snapshot quy tắc. Nếu quy tắc phụ thuộc thời gian hoặc trạng thái hệ thống, làm rõ sự phụ thuộc ấy và viết test kiểm soát đồng hồ/snapshot.

## 6. Ví dụ Spring Boot hoàn chỉnh

Ví dụ một endpoint nhận khoảng số với các ràng buộc:

- `label` không được trống.
- `start` và `end` bắt buộc là số nguyên.
- `end` phải lớn hơn hoặc bằng `start`.
- Độ dài khoảng `end - start` tối đa là 30.

Hai ràng buộc đầu phù hợp Bean Validation; hai ràng buộc sau dùng custom Spring `Validator`. Một instance validator có thể được mọi request dùng chung vì không có mutable field theo request.

Dự án cần Java 17+, Spring MVC và Bean Validation provider. Với Gradle trong Spring Boot 3.x, các dependency chính là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Project được khởi tạo qua Spring Initializr đã có plugin, repositories và cấu hình Java thích hợp. Các file Java dưới đây ở package `com.example.validation`.

### 6.1. Bootstrap ứng dụng — `ValidationApplication.java`

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
~~~

### 6.2. DTO theo từng request — `IntervalForm.java`

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class IntervalForm {
    @NotBlank
    private String label;

    @NotNull
    private Integer start;

    @NotNull
    private Integer end;

    public IntervalForm() {}

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public Integer getStart() {
        return start;
    }

    public void setStart(Integer start) {
        this.start = start;
    }

    public Integer getEnd() {
        return end;
    }

    public void setEnd(Integer end) {
        this.end = end;
    }
}
~~~

Đây là JavaBean theo request, không phải state dùng chung trong validator. Khi Spring tạo `@ModelAttribute`, nó có thể dùng constructor rỗng và setter để bind form fields. Các annotation `@NotBlank` và `@NotNull` thuộc Jakarta Bean Validation.

Dùng `Integer` thay vì `int` giúp phân biệt rõ dữ liệu bị thiếu (`null`) với giá trị `0` do người dùng thực sự gửi. Cũng nên kiểm tra lỗi chuyển kiểu như `start=abc`, vì conversion xảy ra trước kiểm tra quy tắc khoảng số.

### 6.3. Validator singleton an toàn — `IntervalValidator.java`

~~~java
package com.example.validation;

import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public final class IntervalValidator implements Validator {
    private static final int MAX_SPAN = 30;

    @Override
    public boolean supports(Class<?> clazz) {
        return IntervalForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        IntervalForm form = (IntervalForm) target;
        Integer start = form.getStart();
        Integer end = form.getEnd();

        if (start == null || end == null) {
            return; // @NotNull báo lỗi thiếu giá trị.
        }

        if (end < start) {
            errors.rejectValue(
                    "end",
                    "interval.order",
                    "Điểm kết thúc không được nhỏ hơn điểm bắt đầu"
            );
            return;
        }

        long span = (long) end - start;
        if (span > MAX_SPAN) {
            errors.rejectValue(
                    "end",
                    "interval.tooLong",
                    "Khoảng số không được dài hơn 30"
            );
        }
    }
}
~~~

Phân tích thread safety:

- `MAX_SPAN` là hằng số; không có instance field bị ghi khi `validate` chạy.
- `form`, `start`, `end`, `span` là các biến của một lần gọi, không chia sẻ qua request.
- `errors` được truyền từ binder hiện tại; mã chỉ gọi `errors.rejectValue(...)` trên chính tham số này.
- Không có bộ đếm toàn cục, cache mutable, current user hoặc last result.
- Phép trừ dùng kiểu `long` để tránh integer overflow khi client gửi giá trị rất lớn.

`supports` dùng `IntervalForm.class.isAssignableFrom(clazz)`, vì vậy nó hỗ trợ `IntervalForm` và các subtype phù hợp. Phương thức `validate` có thể ép kiểu an toàn trong các lượt gọi Spring kiểm tra đúng loại được hỗ trợ; khi tự gọi thủ công, caller phải bảo đảm truyền đúng target.

Việc trả về ngay khi `start` hoặc `end` là `null` giúp custom validator không ném `NullPointerException` trên input thiếu. Constraint `@NotNull` kiểm tra phần dữ liệu này; trách nhiệm của `IntervalValidator` là quan hệ giữa hai số.

### 6.4. Controller cấu hình validator — `IntervalController.java`

~~~java
package com.example.validation;

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
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IntervalController {
    private final IntervalValidator intervalValidator;

    public IntervalController(IntervalValidator intervalValidator) {
        this.intervalValidator = intervalValidator;
    }

    @InitBinder("intervalForm")
    void configureBinder(WebDataBinder binder) {
        binder.addValidators(intervalValidator);
    }

    @PostMapping(
            path = "/intervals",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("intervalForm") IntervalForm form,
            BindingResult errors
    ) {
        if (errors.hasErrors()) {
            var messages = errors.getFieldErrors().stream()
                    .map(e -> Map.of(
                            "field", e.getField(),
                            "code", Objects.toString(e.getCode(), "invalid"),
                            "message", Objects.toString(
                                    e.getDefaultMessage(), "Không hợp lệ")
                    ))
                    .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", messages));
        }

        return ResponseEntity.ok(Map.of(
                "label", form.getLabel(),
                "start", form.getStart(),
                "end", form.getEnd()
        ));
    }
}
~~~

Các điểm quan trọng của luồng:

1. Spring đăng ký `IntervalValidator` là một singleton bean mặc định; constructor injection cung cấp tham chiếu ổn định cho controller.
2. Mỗi lần bind model attribute, Spring tạo/cấu hình `WebDataBinder` phù hợp với request và gọi `@InitBinder("intervalForm")`. `binder.addValidators(intervalValidator)` **đăng ký** validator hiện có, không tạo một trường `Errors` dùng chung.
3. Spring bind dữ liệu vào `IntervalForm` của request hiện tại.
4. `@Valid` trên tham số kích hoạt validation; các annotation `@NotBlank`/`@NotNull` được xử lý bởi Bean Validation, còn custom `IntervalValidator` bổ sung quy tắc tương quan.
5. `BindingResult` **đặt ngay sau** `@ModelAttribute` để controller có thể tự kiểm tra và phản hồi lỗi. Mỗi lượt request có kết quả lỗi riêng.

Dùng `addValidators(...)` để **bổ sung** vào validator đã cấu hình mặc định. `setValidator(...)` thay thế validator trên binder và có thể khiến Bean Validation thông thường không còn chạy nếu cấu hình không đúng mục đích.

### 6.5. Gửi request và đọc kết quả

Chạy ứng dụng trong project đã cấu hình:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Với Spring Boot mặc định, endpoint thử nghiệm nằm tại `http://localhost:8080/intervals`.

Request hợp lệ:

~~~bash
curl -i -X POST http://localhost:8080/intervals -H "Content-Type: application/x-www-form-urlencoded" --data "label=demo&start=5&end=20"
~~~

Phản hồi kỳ vọng là **HTTP 200**, JSON có cùng nội dung (thứ tự key không cố định):

~~~json
{"label":"demo","start":5,"end":20}
~~~

Request có thứ tự sai:

~~~bash
curl -i -X POST http://localhost:8080/intervals -H "Content-Type: application/x-www-form-urlencoded" --data "label=demo&start=20&end=5"
~~~

Kỳ vọng **HTTP 400**, danh sách `errors` có field `end` và mã lỗi liên quan `interval.order`. Mã chính xác được Spring phân cấp theo object/field trong `BindingResult`, nên code client không nên chỉ dựa vào một message cố định.

Request có khoảng lớn hơn mức cho phép:

~~~bash
curl -i -X POST http://localhost:8080/intervals -H "Content-Type: application/x-www-form-urlencoded" --data "label=demo&start=5&end=40"
~~~

Kỳ vọng HTTP 400 với lỗi `interval.tooLong`. Request `label=&start=5&end=20` sẽ được Bean Validation đánh dấu `label` trống. Request `start=abc` gây lỗi chuyển kiểu ở bước data binding; không nên gọi đó là lỗi tương quan do `IntervalValidator` phát hiện.

## 7. Tại sao `Errors` và `BindingResult` không nên được lưu trong bean?

`Errors` là **đối tượng đầu ra của một phép kiểm tra**. Kể cả khi `Validator` có thể gọi đồng thời, `Errors` của từng lần gọi **không phải kho dữ liệu dùng chung**. Với MVC, binder quản lý `BindingResult` tương ứng với đối tượng đầu vào đang bind.

Sai:

~~~java
@Component
public class SharedErrorsHolder {
    private Errors lastErrors;

    public void remember(Errors errors) {
        this.lastErrors = errors;
    }
}
~~~

Đoạn này minh họa một thiết kế nguy hiểm: `Errors` của request A bị thay bởi request B. Đây không phải class cần có trong ứng dụng mẫu.

Đúng: chỉ truyền `Errors` vào `validate`; lấy `hasErrors()`, `getFieldErrors()` ngay trong handler/service xử lý invocation đó. Muốn tổng hợp thống kê như số lần validation thất bại, dùng hệ thống metric thread-safe và không ghi những giá trị nhạy cảm vào label. **Metric là trách nhiệm quan sát hệ thống**, không phải nơi chứa input/kết quả của từng request.

Nếu cần trả nhiều lỗi cho một field, gọi `rejectValue` nhiều lần trên `Errors` cùng invocation. Không cần xây dựng `List<String> sharedMessages` trong validator để gom lỗi.

## 8. Kiểm thử thực sự với nhiều thread

Unit test một request chỉ chứng minh quy tắc đúng cho một trường hợp. Để kiểm tra lỗi trạng thái dùng chung, có thể gọi **cùng một instance validator** từ nhiều task, nhưng mỗi task tự tạo input và `BindingResult`.

Ví dụ dưới đây dùng JUnit 5 và Spring Test dependency đã thêm trong project. Tệp `src/test/java/com/example/validation/IntervalValidatorConcurrencyTest.java`:

~~~java
package com.example.validation;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;

import static org.junit.jupiter.api.Assertions.assertTrue;

class IntervalValidatorConcurrencyTest {

    @Test
    void sameValidatorCanBeUsedByParallelCalls() throws Exception {
        IntervalValidator validator = new IntervalValidator();
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch startGate = new CountDownLatch(1);
        List<Future<Boolean>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < 200; i++) {
                final int index = i;
                Callable<Boolean> caseTask = () -> {
                    startGate.await();

                    IntervalForm form = new IntervalForm();
                    form.setLabel("case-" + index);
                    form.setStart(100);
                    form.setEnd(index % 2 == 0 ? 99 : 101);

                    BeanPropertyBindingResult result =
                            new BeanPropertyBindingResult(
                                    form, "intervalForm");

                    validator.validate(form, result);
                    boolean expectError = index % 2 == 0;
                    return result.hasFieldErrors("end") == expectError;
                };
                futures.add(pool.submit(caseTask));
            }

            startGate.countDown();

            for (Future<Boolean> future : futures) {
                assertTrue(future.get(10, TimeUnit.SECONDS));
            }
        } finally {
            startGate.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests com.example.validation.IntervalValidatorConcurrencyTest
~~~

Lệnh tương ứng trên Windows là `gradlew.bat test --tests com.example.validation.IntervalValidatorConcurrencyTest`.

Test có **200 lời gọi** dùng chung một instance `IntervalValidator` và pool 8 thread. Task với index chẵn có `end=99 < start=100` nên phải có lỗi `end`; task với index lẻ có `end=101` nên không có lỗi `end`. Mỗi task tự tạo `IntervalForm` và `BeanPropertyBindingResult`, phản ánh cách tách trạng thái theo lần gọi.

**Giới hạn chứng minh:** chạy xanh nhiều lần là bằng chứng hữu ích, không phải chứng minh toán học rằng implementation có thread safety tuyệt đối. Test có thể bỏ sót race ít xuất hiện; cần review toàn bộ mutable field, object graph, dependency và code path. Unit test này cũng **chỉ gọi custom Validator trực tiếp**; nó không khởi chạy MVC, kiểm tra `@InitBinder` hoặc chạy Bean Validation. Các kiểm thử đó thuộc mức tích hợp.

## 9. Kiểm thử tích hợp Spring MVC

`MockMvc` giúp xác minh custom validator được Spring đăng ký và kích hoạt đúng lúc. Với ví dụ trên, thêm tệp `src/test/java/com/example/validation/IntervalControllerTest.java`:

~~~java
package com.example.validation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(IntervalController.class)
class IntervalControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void acceptsValidInterval() throws Exception {
        mvc.perform(post("/intervals")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("label", "demo")
                    .param("start", "5")
                    .param("end", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.start").value(5))
                .andExpect(jsonPath("$.end").value(20));
    }

    @Test
    void rejectsInvalidIntervalOrder() throws Exception {
        mvc.perform(post("/intervals")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("label", "demo")
                    .param("start", "20")
                    .param("end", "5"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value("end"));
    }

    @Test
    void rejectsBlankLabelByBeanValidation() throws Exception {
        mvc.perform(post("/intervals")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("label", "")
                    .param("start", "5")
                    .param("end", "20"))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Lưu ý với `@WebMvcTest`:** test slice này cần có bean `IntervalValidator` trong context. `@WebMvcTest(IntervalController.class)` không bảo đảm quét tùy ý tất cả `@Component`; trong project thực, thêm `@Import(IntervalValidator.class)` lên test class (import `org.springframework.context.annotation.Import`), hoặc cấu hình bean trong slice. Với test trên, **phải bổ sung `@Import(IntervalValidator.class)`** trước khi chạy độc lập; ví dụ khai báo class ở mục này thể hiện phần thân test và các assertion.

Để có một cấu hình hoàn chỉnh, phần khai báo test class là:

~~~java
@WebMvcTest(IntervalController.class)
@Import(IntervalValidator.class)
class IntervalControllerTest {
    // Các field và phương thức test đã trình bày ở trên.
}
~~~

Đây là đoạn **thay thế ba dòng khai báo class**, không phải class thứ hai cần dán thêm nguyên khối. Khi dán source chạy thật, đặt `@Import(IntervalValidator.class)` trên class `IntervalControllerTest` duy nhất, thêm import vừa nêu.

Chạy:

~~~bash
./gradlew test --tests com.example.validation.IntervalControllerTest
~~~

Ở dự án có Spring Security starter, cấu hình CSRF/auth của test cần xử lý theo đúng chính sách bảo mật; ví dụ tối thiểu trong module chỉ khai báo Spring Web/Validation/Test.

Ngoài ra, test song song ở mức HTTP có thể phát hiện việc vô tình lưu `BindingResult` vào field của controller hoặc interceptor. Tránh thiết kế controller singleton mutable theo request dù validator bản thân đã stateless.

## 10. Dependency của validator cũng phải an toàn

Một validator trông “không có mutable field” nhưng lại gọi sang một service không thread-safe **vẫn có thể không an toàn**. Ví dụ `validator.validate` gọi phương thức cập nhật `HashMap` dùng chung của một helper singleton mà không đồng bộ. Race condition có thể xuất hiện trong helper, dù lớp validator chỉ có `private final Helper helper`.

Cần rà soát:

| Dependency / hành vi | Vấn đề có thể gặp | Cách xử lý |
| --- | --- | --- |
| `HashMap` / `ArrayList` mutable dùng chung | Race, dữ liệu lỗi, `ConcurrentModificationException` | Dữ liệu cấu hình bất biến; dùng concurrent collection đúng ngữ nghĩa nếu cần |
| `SimpleDateFormat` trong field | Mutable và không bảo đảm thread-safe | Dùng `java.time.format.DateTimeFormatter` bất biến hoặc tạo formatter theo invocation |
| `StringBuilder` dùng lại | Trộn thông báo giữa request | Khai báo biến cục bộ hoặc tạo mới |
| Bộ nhớ đệm `lastResult` | Lẫn output theo request và stale data | Không cache per-request ở validator; nếu bắt buộc cache, thiết kế key, expiry và cấu trúc thread-safe |
| Service dùng mutable state theo user | Có thể lẫn user khi gọi đồng thời | Truyền ngữ cảnh tường minh; service không giữ `currentUser` dùng chung |
| I/O hoặc DB query | Có độ trễ, trạng thái thay đổi trong lúc kiểm tra | Dùng API thread-safe, transaction/boundary phù hợp; không giả định validation bảo đảm invariant cuối cùng |

Trong Spring, constructor injection và field `final` là lựa chọn tốt cho dependency ổn định. Tuy nhiên, cần kiểm tra dependency có quy tắc thread safety riêng: ví dụ Spring Data Repository được thiết kế để chia sẻ, còn một đối tượng xử lý với buffer thay đổi có thể cần tạo mới theo lượt gọi.

Nếu validator phải kiểm tra mã sản phẩm tồn tại trong DB, nó có thể gọi service chỉ đọc một cách an toàn, nhưng kết quả có thể thay đổi ngay sau validation. Quy tắc **tính duy nhất, số dư, quyền sở hữu, giới hạn tồn kho** cần được bảo vệ thêm trong transaction hoặc bằng constraint thích hợp ở tầng lưu trữ. Validation ở request chỉ là một lớp phản hồi sớm cho người dùng.

## 11. Stateless và thread-safe là hai khái niệm liên quan nhưng khác nhau

**Stateless**: instance không ghi nhớ trạng thái của từng lần gọi. Với input, config và dependency snapshot xác định, lần gọi độc lập với request trước đó.

**Thread-safe**: hành vi vẫn đúng khi nhiều thread gọi đồng thời theo cách được API cho phép.

Một validator thuần chỉ đọc input độc lập và cấu hình bất biến rồi ghi vào `Errors` riêng thường có thể dùng an toàn như singleton. Nhưng chỉ vì không có field mutable trong source file **chưa đủ để kết luận** thread safety nếu dependency nội bộ hoặc các tham chiếu input được chia sẻ và sửa cùng lúc.

Ngược lại, một lớp có thể thread-safe nhờ khóa hoặc cấu trúc đồng bộ mà vẫn stateful. Trong phần lớn validation của MVC, ta **không cần lưu trạng thái đó**, nên stateless thường đơn giản hơn, giảm chi phí đồng bộ và dễ kiểm thử.

**Tránh dùng `ThreadLocal` để cất `Errors` hoặc request hiện tại**. Servlet container tái sử dụng thread; nếu quên `remove()`, dữ liệu có thể rò giữa request. Luồng async cũng có thể chuyển sang thread khác. Truyền input và `Errors` tường minh qua tham số là cách tự nhiên của Spring `Validator`.

## 12. Những câu hỏi thực tế khi đăng ký và sử dụng

**Có nên tạo `new Validator()` cho mỗi request để được an toàn?** Không cần nếu validator đã stateless. Singleton tiết kiệm khởi tạo, dễ injection, còn mỗi request vẫn có DTO và `BindingResult` riêng. Tạo mới mỗi lần chỉ có lý do khi implementation thực sự sở hữu trạng thái riêng và được thiết kế như vậy.

**`@InitBinder` có phải nơi chạy validation không?** Không. Nó là điểm cấu hình `WebDataBinder` **trước binding**. Gắn validator bằng `addValidators` ở đó; `@Valid` hoặc `@Validated` trên handler yêu cầu validation. Nếu tự sử dụng `DataBinder` trong Java code, cần gọi `binder.validate()` sau `binder.bind(...)`.

**Có thể đăng ký validator toàn ứng dụng không?** Có. MVC hỗ trợ cấu hình global validator bằng `WebMvcConfigurer#getValidator()`; cấu hình cục bộ `@InitBinder` (trong `@Controller` hoặc `@ControllerAdvice`) thường thích hợp nếu quy tắc dành cho DTO cụ thể. Khi dùng global validator, cần đảm bảo `supports` phù hợp với những kiểu được kiểm tra và không vô tình thay thế Bean Validation cần thiết.

**`supports` có được phép truy vấn DB hoặc ghi cache không?** Về mặt thiết kế, không nên. Nó trả lời câu hỏi tương thích *class*, nên nên là phép kiểm tra nhanh, ổn định, không side effect. Truy vấn nghiệp vụ thuộc `validate` hoặc service thích hợp, tùy yêu cầu.

**Có nên mutate target để “sửa” input?** `Validator` được dùng để **báo lỗi**, không phải bộ chuẩn hóa dữ liệu. Nếu muốn trim/canonicalize, dùng converter, formatter, binder hoặc bước chuẩn hóa riêng trước validation. Mutate DTO trong validator khiến thứ tự validator và kiểm thử khó dự đoán, đặc biệt với dữ liệu chia sẻ.

**Validator có bảo đảm lỗi trả về ổn định theo thứ tự không?** Không nên dựa vào thứ tự giữa nhiều validator hoặc các constraint Jakarta khác nhau. API nên trả field + mã lỗi có ý nghĩa, và test nên tìm đúng lỗi cần thiết, không suy luận rằng mọi request phải có mảng lỗi đúng một thứ tự duy nhất.

**Các constraint Jakarta có tự động thread-safe không?** Bean Validation provider quản lý đời sống các `ConstraintValidator` theo quy tắc của mình; nếu tự triển khai `ConstraintValidator`, cũng nên tránh mutable state theo mỗi lần `isValid` và dùng cấu hình chỉ đọc từ `initialize`. Đó là interface khác với Spring `Validator`, nhưng nguyên tắc không trộn dữ liệu invocation vẫn tương tự.

## 13. Checklist review một validator singleton

Trước khi đưa validator vào controller phục vụ nhiều request, có thể tự kiểm tra:

1. Lớp có field mutable như `currentErrors`, `currentForm`, `lastResult`, buffer hoặc request-specific collection không? Nếu có, bỏ hoặc chuyển thành biến cục bộ.
2. Các field `final` chứa object mutable không? Nếu có, chúng có được dùng bất biến hoặc có cơ chế thread-safe rõ ràng không?
3. `supports` có hoàn toàn dựa trên kiểu class, không cần nhớ lần kiểm tra trước không?
4. `validate` có dùng `target` và `errors` được truyền trong chính lời gọi không, và có tránh sửa input ngoài mục đích validation không?
5. Dependency (service, cache, formatter, DB access) có an toàn khi gọi đồng thời không?
6. Đầu vào DTO và `BindingResult` có được tạo/điều phối riêng cho từng request không?
7. Khi lỗi chuyển kiểu hoặc một field `null`, validator có thể chạy mà không tạo lỗi runtime không?
8. Có test rule cơ bản, test request Spring MVC và test gọi chung instance trên nhiều thread không?
9. Nếu quy tắc phụ thuộc trạng thái DB hoặc phân quyền, tầng nghiệp vụ/transaction có thực thi lại invariant bắt buộc không?
10. Các lỗi được trả cho đúng request, đúng field và không để lộ dữ liệu nhạy cảm không?

## 14. Tổng kết

Một Spring `Validator` phù hợp để chia sẻ giữa nhiều request khi nó chỉ chứa cấu hình/dependency an toàn và dùng **biến cục bộ cùng `Errors` được truyền vào** để xử lý dữ liệu của từng lời gọi. Bean singleton của Spring là mô hình sử dụng phổ biến cho loại validator này, với điều kiện cả validator lẫn dependency không chia sẻ mutable state theo request.

Giữ cho `supports` thuần, `validate` không lưu trạng thái, cấu hình bất biến, `BindingResult` độc lập và có kiểm thử đồng thời sẽ giảm nguy cơ trộn lỗi, dữ liệu và kết quả giữa những request chạy song song.

### Tài liệu tham khảo

- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring Framework — Java Bean Validation và DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
