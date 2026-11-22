# Giữ API annotation ổn định khi tái sử dụng Spring AOP aspect giữa các module

## 1. Vấn đề cần giải quyết

Khi nhiều module Spring dùng chung một aspect, annotation mà developer đặt lên service chính là **API công khai giữa module nghiệp vụ và hạ tầng AOP**. Ví dụ module đặt hàng dùng `@TrackedOperation("checkout")`, module thanh toán dùng `@TrackedOperation("charge")`; cả hai mong aspect nhận diện cùng một contract dù triển khai logging, metrics hoặc tracing thay đổi. Nếu đổi package, tên annotation, tên thuộc tính hay ý nghĩa thuộc tính một cách tùy tiện, source code có thể không biên dịch, code đã biên dịch có thể lỗi lúc chạy hoặc advice có thể ngừng áp dụng mà không báo lỗi rõ ràng.

Mục tiêu: module sử dụng annotation chỉ phụ thuộc vào **contract ổn định**, còn Spring AOP aspect và cách đăng ký bean có thể được cập nhật riêng; mọi thay đổi contract được kiểm tra và phát hành có kiểm soát. Trọng tâm ở đây là cách Spring AOP phát hiện và áp dụng annotation trong ứng dụng đa module.

## 2. Tách contract annotation khỏi Spring aspect

Một cách tổ chức với Java 17+/Spring Boot 3.x:

```text
operation-contract/            # JAR API: annotation công khai, không cần Spring
  com/example/contract/TrackedOperation.java

operation-spring/              # JAR runtime: @Aspect và Spring Boot auto-configuration
  com/example/spring/TrackedOperationAspect.java
  com/example/spring/TrackedOperationAutoConfiguration.java
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

checkout-app/                   # ứng dụng Spring Boot dùng annotation
  com/example/checkout/CheckoutService.java
  com/example/checkout/CheckoutApplication.java

billing-app/                    # một ứng dụng khác cũng có thể dùng cùng contract
```

Quan hệ phụ thuộc: `operation-spring → operation-contract`; từng ứng dụng phụ thuộc vào `operation-contract` để biên dịch và `operation-spring` để bật hành vi AOP. Ứng dụng cần `spring-boot-starter-aop` trong runtime (hoặc cấu hình Spring AOP tương đương). `operation-contract` là JAR nhỏ chỉ chứa contract; không đặt `@Aspect`, `@Component`, logger hay bean cấu hình vào JAR này.

Điểm ổn định là **fully qualified class name** (FQCN) của annotation cùng các phần tử và ngữ nghĩa của nó. Tên implementation `TrackedOperationAspect`, loại sink hoặc cách xuất log là chi tiết nội bộ của module Spring.

## 3. Khai báo contract cho proxy-based Spring AOP

Tệp `operation-contract/src/main/java/com/example/contract/TrackedOperation.java`:

```java
package com.example.contract;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedOperation {
    String value();
    String category() default "business";
}
```

- `RUNTIME` là điều kiện để Spring AOP có thể đọc annotation tại runtime. Đổi sang `CLASS` hoặc `SOURCE` sẽ khiến advice dựa vào `@annotation` không còn nhận ra annotation trong runtime thông thường.
- `METHOD` xác định lời hứa công khai: annotation áp dụng cho method. Nếu sau này muốn hỗ trợ cả class, phải đồng thời thiết kế pointcut phù hợp; thêm `TYPE` vào `@Target` **không tự động** khiến `@annotation` áp dụng cho mọi method trong class.
- `value()` là tên thao tác nghiệp vụ bắt buộc và cần giữ ngữ nghĩa nhất quán; `category()` có giá trị mặc định để code cũ dùng `@TrackedOperation("checkout")` tiếp tục hoạt động.
- `@Documented` hỗ trợ tài liệu JavaDoc, không phải điều kiện kích hoạt AOP. Không tự thêm `@Inherited` để mong annotation trên method được kế thừa: `@Inherited` của Java chỉ có ý nghĩa với annotation đặt trên class, không giải quyết proxy hoặc method override.

Nếu các module được phát hành độc lập, công bố contract trong artifact có phiên bản rõ ràng; giữ package `com.example.contract` và tên phần tử ổn định qua các bản nâng cấp tương thích.

## 4. Aspect Spring dùng chính contract đã công bố

Tệp `operation-spring/src/main/java/com/example/spring/TrackedOperationAspect.java`:

```java
package com.example.spring;

import com.example.contract.TrackedOperation;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TrackedOperationAspect {

    @Around(value = "@annotation(tracked)", argNames = "tracked")
    public Object record(ProceedingJoinPoint joinPoint,
                         TrackedOperation tracked) throws Throwable {
        try {
            Object result = joinPoint.proceed();
            System.out.printf(
                    "[track] %s category=%s status=SUCCESS%n",
                    tracked.value(), tracked.category());
            return result;
        } catch (Throwable error) {
            System.out.printf(
                    "[track] %s category=%s status=FAILURE type=%s%n",
                    tracked.value(), tracked.category(),
                    error.getClass().getSimpleName());
            throw error;
        }
    }
}
```

`@annotation(tracked)` là pointcut Spring AOP đối với method execution được proxy xử lý và có annotation tương ứng; `tracked` còn được bind vào advice để lấy thuộc tính từ contract. `joinPoint.proceed()` gọi logic nghiệp vụ đúng một lần và trả nguyên kết quả; khi lỗi, advice ném lại đúng `Throwable` ban đầu để không làm thay đổi hợp đồng lỗi của service. `argNames` giúp việc bind annotation rõ ràng, không lệ thuộc vào thông tin tên tham số của compiler.

Ví dụ dùng `System.out` nhằm thấy kết quả trực tiếp; trong sản phẩm thực tế, thay bằng logger, metrics hoặc một sink chuyên trách. Tránh log tham số chứa mật khẩu/dữ liệu nhạy cảm. Việc in `SUCCESS` tại lúc method trả về **không chứng minh giao dịch `@Transactional` đã commit**: thời điểm advice chạy phụ thuộc vào thứ tự interceptor. Nếu yêu cầu audit bền vững sau commit, thiết kế theo transaction/event riêng và kiểm tra thứ tự advice.

## 5. Đăng ký aspect ở đúng ranh giới module

Spring Boot 3.x có thể auto-configure aspect từ JAR `operation-spring`, không bắt từng ứng dụng quét thủ công package của library. Tệp `operation-spring/src/main/java/com/example/spring/TrackedOperationAutoConfiguration.java`:

```java
package com.example.spring;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class TrackedOperationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(TrackedOperationAspect.class)
    TrackedOperationAspect trackedOperationAspect() {
        return new TrackedOperationAspect();
    }
}
```

Tệp resource **đúng đường dẫn** `operation-spring/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` chứa duy nhất dòng:

```text
com.example.spring.TrackedOperationAutoConfiguration
```

Đóng gói JAR phải giữ resource này. Khi ứng dụng có dependency `operation-spring` và `spring-boot-starter-aop`, Spring Boot nạp auto-configuration và có cơ chế tạo Spring AOP proxy. Aspect được quản lý như một Spring bean, còn module nghiệp vụ chỉ cần import annotation từ `operation-contract`.

Điều kiện sử dụng: hai JAR phải cùng phiên bản contract tương thích; không trộn các bản chứa **hai class annotation khác FQCN** rồi mong `@annotation` tự hiểu chúng là một. Khi library cần cho phép vô hiệu hóa tính năng, bổ sung property có tên ổn định cùng `@ConditionalOnProperty`, công bố default và kiểm tra ứng dụng cũ trước khi đổi default. Nếu không dùng Boot auto-configuration, ứng dụng có thể `@Import` một `@Configuration` khai báo aspect; chọn một cơ chế nhất quán để tránh tạo hai bean/advice tương đương.

## 6. Ứng dụng sử dụng annotation mà không biết chi tiết aspect

Tệp `checkout-app/src/main/java/com/example/checkout/CheckoutService.java`:

```java
package com.example.checkout;

import com.example.contract.TrackedOperation;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @TrackedOperation("checkout")
    public String checkout() {
        return "OK";
    }
}
```

Tệp `checkout-app/src/main/java/com/example/checkout/CheckoutApplication.java`:

```java
package com.example.checkout;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CheckoutService service) {
        return args -> System.out.println(service.checkout());
    }
}
```

Đây là các file Java cho ví dụ đa module; chúng chạy trong dự án Spring Boot đã cấu hình dependency và plugin build tương ứng, không phải chương trình có thể chạy bằng `javac` thuần túy vì sử dụng Spring và AspectJ. Khi Gradle của dự án đã thiết lập Boot và module path như trên, có thể chạy `./gradlew :checkout-app:bootRun` (Windows: `gradlew.bat :checkout-app:bootRun`).

Bên cạnh các dòng khởi động của Spring Boot, với cấu hình proxy hợp lệ sẽ thấy hai dòng do ví dụ sinh ra, theo đúng thứ tự:

```text
[track] checkout category=business status=SUCCESS
OK
```

Module `billing-app` có thể chỉ đặt `@TrackedOperation("charge")` và dùng các dependency tương ứng; không cần sao chép source `TrackedOperationAspect` hay tạo một annotation trùng tên trong package khác.

## 7. Các thay đổi contract: an toàn hay phá vỡ tương thích?

| Thay đổi | Rủi ro với các module sử dụng | Cách xử lý |
| --- | --- | --- |
| Giữ FQCN, chữ ký `value()`, `@Retention(RUNTIME)`, `@Target(METHOD)` và ngữ nghĩa | Thường tương thích | Có thể nâng implementation aspect riêng |
| Thêm phần tử `String category() default "business"` | Code dùng annotation trước đó vẫn có giá trị hợp lệ | Test lại hành vi khi default mới được áp dụng |
| Thêm phần tử **không** có default | Các lần biên dịch source annotation cũ bị lỗi thiếu phần tử; runtime với class cũ cũng có thể lỗi khi đọc | Coi là breaking change; thiết kế default hoặc major version |
| Đổi `value()` thành `operation()` hoặc xóa phần tử | Source dùng tên cũ hỏng; aspect và binary cũ có thể lỗi | Giữ alias cũ trong giai đoạn chuyển tiếp hoặc phát hành major version |
| Đổi package hoặc tên `TrackedOperation` | FQCN mới là một annotation khác; pointcut cũ không match | Có giai đoạn chấp nhận cả annotation cũ và mới, sau đó migrate có kiểm soát |
| Đổi `RUNTIME` thành `CLASS`; thu hẹp `@Target` | AOP không nhận diện hoặc source ngừng biên dịch | Không thay nếu vẫn cam kết chức năng cũ |
| Đổi giá trị default, ý nghĩa của `value`, tên operation được ghi nhận | Có thể không lỗi biên dịch nhưng đổi logs/metrics/tracing hoặc dashboard | Xem là thay đổi hành vi API, test và thông báo migration |
| Chỉ đổi implementation logging, sink, nội bộ advice | Annotation của caller không cần thay | Kiểm tra tương thích observable behavior và thứ tự advice |

Ngay cả khi một thay đổi hợp lệ về mặt binary Java, tương thích **hành vi Spring AOP** vẫn cần kiểm thử: aspect có thể đổi pointcut, điều kiện đăng ký bean hoặc thứ tự advisor mà không làm compile lỗi. Không xem việc build thành công là bằng chứng aspect còn thực thi.

### Chiến lược phát hành/migration

1. Xuất bản `operation-contract` như một API có phiên bản, ghi rõ vị trí đặt annotation, ý nghĩa từng thuộc tính, default và phạm vi áp dụng.
2. Ưu tiên **bổ sung phần tử tùy chọn có default**; không đổi hay xóa phần tử đang được caller dùng. Nếu cần thay nghĩa, đặt tên mới có ý nghĩa rõ và đánh dấu phần tử cũ `@Deprecated` trong thời gian chuyển đổi.
3. Khi buộc đổi annotation FQCN, duy trì annotation cũ và thêm handler rõ ràng cho cả hai trong phiên bản chuyển tiếp; kiểm tra tránh ghi nhận sự kiện hai lần nếu một method gắn cả hai. Chỉ bỏ đường cũ tại phiên bản major với hướng dẫn migration.
4. Với ứng dụng độc lập, khóa/căn chỉnh phiên bản `operation-contract` giữa compile classpath và runtime classpath; phát hành aspect Spring kèm dải phiên bản contract được hỗ trợ.
5. Giữ test tương thích với một ứng dụng dùng annotation theo cú pháp cũ; không chỉ test consumer sau khi đã sửa theo API mới.

## 8. Bẫy Spring AOP dễ làm nhầm thành lỗi API

Spring AOP dựa trên proxy, nên giữ nguyên annotation contract vẫn chưa đủ nếu lời gọi không đi qua proxy:

- **Self-invocation:** `this.checkout()` từ method khác trong cùng bean không đi qua proxy Spring AOP. Đưa thao tác cần intercept sang bean riêng hoặc gọi từ một bean bên ngoài.
- **Đối tượng không do Spring quản lý:** tự `new CheckoutService()` sẽ không có AOP proxy.
- **Final/private method và proxy:** private method không được Spring AOP intercept; final method không thể được CGLIB subclass proxy override. Với JDK dynamic proxy, lời gọi phải đi qua interface của proxy. Ưu tiên public method được gọi qua Spring bean.
- **Đặt annotation ở interface/implementation:** vị trí annotation và loại proxy có thể ảnh hưởng matching. Thống nhất quy ước đặt `@TrackedOperation` trên public method của concrete service trong ví dụ này và có integration test nếu ứng dụng dùng interface-based proxy.
- **`@annotation` và `@within`/`@target`:** `@annotation` dùng cho annotation của method được match; nếu mở rộng contract cho annotation ở class, phải viết pointcut tương ứng và xác định khi cả class và method cùng gắn annotation thì ưu tiên cái nào.
- **Đăng ký thiếu runtime:** dependency contract cho phép compile nhưng không tự bật aspect. Kiểm tra JAR auto-configuration, starter AOP, bean aspect và thực tế proxy. Nếu ứng dụng không có starter AOP, annotation trở thành metadata thuần và không tạo hành vi mong đợi.
- **Nhiều aspect/advisor:** cùng một method có thể có `@Transactional`, `@Async` và nhiều advice. Khi timing, transaction hoặc kết quả sau commit là phần contract, phải kiểm tra thứ tự với `@Order`/cấu hình advisor và hành vi runtime thực tế.

## 9. Checklist kiểm thử khi nâng phiên bản shared aspect

Kiểm thử tích hợp nên khởi động Spring context của một ứng dụng thật, inject service từ context và gọi qua bean proxy. Các trường hợp tối thiểu: method được annotate đi qua advice đúng một lần; method không annotate không bị ghi nhận; thuộc tính mặc định `category="business"` được đọc đúng; giá trị custom đi qua pointcut binding; kết quả trả về không đổi; ngoại lệ gốc được ném lại; hoạt động qua hai module consumer khác nhau; cấu hình bật/tắt (nếu public API hỗ trợ) nhất quán; bản consumer dùng cú pháp annotation cũ vẫn chạy sau khi nâng JAR.

Có thể bổ sung test Spring bằng `AopUtils.isAopProxy(service)` để phát hiện thiếu proxy, nhưng kiểm tra proxy **chưa đủ**: cần assert sự kiện/log/metric từ advice để chứng minh pointcut thật sự match. Nếu output là log, dùng appender/sink giả trong test thay vì phụ thuộc chuỗi startup log của Boot. Đối với phần tử annotation mới, dùng test giữ nguyên source caller cũ và kiểm tra default.

## 10. Quy tắc áp dụng thực tế

- **Contract ổn định:** FQCN, `@Retention`, `@Target`, phần tử, default và ý nghĩa của annotation được coi là API có phiên bản.
- **Spring runtime thay đổi có kiểm soát:** aspect, pointcut, bean registration, thứ tự advisor và khả năng proxy được kiểm thử ở cấp tích hợp.
- **Consumer độc lập:** code nghiệp vụ chỉ import một annotation từ artifact dùng chung; không phụ thuộc vào tên hoặc cách khởi tạo aspect.
- **Migration rõ ràng:** thêm thuộc tính có default khi có thể; hỗ trợ song song có thời hạn nếu đổi tên/package; không đổi ngữ nghĩa âm thầm.

Giữ các ranh giới này giúp nhiều Spring module tái sử dụng một annotation mà không phải đồng loạt sửa source mỗi khi triển khai aspect thay đổi.
