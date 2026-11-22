# Xử lý ngoại lệ và trạng thái suy giảm trong kiểm tra sức khỏe

## 1. Ngoại lệ của phép kiểm tra nói lên điều gì?

Khi một phép kiểm tra sức khỏe gặp lỗi, cần phân biệt **không sử dụng được thành phần đang kiểm tra** với **không hoàn thành được chính phép kiểm tra**. Một kết nối bị từ chối, thời gian chờ bị vượt, cấu hình sai và luồng bị ngắt không phải cùng một sự kiện. Chuyển tất cả thành `UP` sẽ che lỗi; chuyển tất cả thành “toàn bộ ứng dụng đã chết” lại có thể làm mất khả năng phục vụ vẫn còn tồn tại.

Ví dụ, một cửa hàng dùng dịch vụ gợi ý sản phẩm bên ngoài. Khi dịch vụ này lỗi, cửa hàng vẫn có thể hiển thị danh sách phổ biến đã được chuẩn bị sẵn. Chức năng gợi ý cá nhân hóa suy giảm nhưng trang mua hàng vẫn hoạt động. Ngược lại, nếu cả dịch vụ chính và dữ liệu dự phòng đều không dùng được, ta không còn bằng chứng để nói chức năng đó vẫn phục vụ được.

Bài này dùng **Java 21 và Spring Boot 3.3.0** để xây dựng chính sách sau:

- `UP`: phép kiểm tra đường chính thành công.
- `DEGRADED`: đường chính gặp lỗi có thể xử lý, nhưng đường dự phòng thực sự sẵn sàng theo hợp đồng của ứng dụng.
- `DOWN`: cả hai đường không đáp ứng, hoặc phép kiểm tra gặp lỗi mà không thể kết luận đang phục vụ an toàn.

`DEGRADED` là status tùy chỉnh trong ví dụ, **không phải status dựng sẵn mà Actuator tự hiểu**. Cần cấu hình cả cách tổng hợp và mã HTTP của nó.

## 2. Ba lớp quyết định cần tách rõ

```text
Kết quả hoặc ngoại lệ của phép thử
    → Health của một thành phần
    → trạng thái tổng hợp của endpoint hoặc nhóm health
    → mã HTTP được công bố
```

| Lớp quyết định | Câu hỏi cần trả lời |
| --- | --- |
| Indicator | Lỗi này có nghĩa gì đối với khả năng phục vụ của thành phần? |
| `StatusAggregator` | Khi nhiều thành phần có status khác nhau, status nào đại diện cho kết quả tổng? |
| `HttpCodeStatusMapper` | Status cuối cùng được biểu diễn bằng mã HTTP nào? |

Một indicator có thể trả `DEGRADED` đúng, nhưng endpoint tổng vẫn trả `UP` nếu bộ tổng hợp không biết status mới. Ngược lại, JSON chứa status đúng nhưng công cụ chỉ nhìn HTTP có thể bỏ qua cảnh báo suy giảm nếu chính sách trả `200`.

Các chi tiết như `reason=DEPENDENCY_TIMEOUT` giúp chẩn đoán; bản thân chuỗi `reason` không tham gia xếp mức độ nghiêm trọng. Chính trường `status` mới đi vào cơ chế tổng hợp.

## 3. Cơ chế xử lý ngoại lệ mặc định và giới hạn của nó

### Cài đặt trực tiếp HealthIndicator

Nếu tự cài đặt `HealthIndicator.health()`, ứng dụng phải tự quyết định cách xử lý lỗi. Interface không tự bao lời gọi trong một `try/catch` để chuyển mọi exception thành `DOWN`. Không nên dựa vào một lớp HTTP bên ngoài để biến một exception bị bỏ lọt thành phản hồi health có cấu trúc.

### Kế thừa AbstractHealthIndicator

`AbstractHealthIndicator` tạo `Health.Builder` cho từng lần gọi, chạy `doHealthCheck(...)`, bắt `Exception` thoát ra và tạo `DOWN` bằng `builder.down(ex)`. Nó cũng có cơ chế ghi cảnh báo khi kết quả giữ exception. Cơ chế này phù hợp khi exception thoát ra thực sự nên được hiểu là `DOWN`. Xem [mã AbstractHealthIndicator của Spring Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.java).

Lớp cha không thay ứng dụng quyết định đường dự phòng có đủ dùng hay không. Nó cũng không:

- đặt timeout hoặc tự ngắt một lời gọi đang treo;
- tự phục hồi cờ ngắt luồng khi bắt `InterruptedException`;
- tự hiểu một status mới như `DEGRADED`;
- bảo đảm thông điệp exception an toàn để công bố.

`Exception` và `Error` khác nhau. Không dùng `catch (Throwable)` chỉ để luôn tạo một JSON health: lỗi nghiêm trọng như `OutOfMemoryError` không nên bị biến thành một lần kiểm tra bình thường đã được xử lý thành công.

Trong ví dụ dưới đây, ta cài đặt trực tiếp `HealthIndicator` để phân loại lỗi, giữ cờ ngắt và chỉ trả các mã lý do đã kiểm soát.

## 4. Định nghĩa trạng thái suy giảm theo khả năng phục vụ

Trạng thái suy giảm cần có bằng chứng rõ ràng. “Đã bắt được exception” không phải bằng chứng rằng ứng dụng vẫn phục vụ được.

| Tình huống | Status của ví dụ | Lý do |
| --- | --- | --- |
| Đường chính kiểm tra thành công | `UP` | Chưa cần đường dự phòng. |
| I/O hoặc timeout ở đường chính; dự phòng sẵn sàng | `DEGRADED` | Vẫn phục vụ được theo cơ chế dự phòng đã được chấp nhận. |
| I/O hoặc timeout; dự phòng không sẵn sàng | `DOWN` | Không còn đường phục vụ được xác nhận. |
| Cấu hình phép kiểm tra không hợp lệ | `DOWN` | Cần sửa cấu hình, không coi như một lỗi kết nối tạm thời thông thường. |
| Phép kiểm tra dự phòng tự phát sinh lỗi | `DOWN` | Không thể xác nhận dự phòng còn hoạt động. |
| Luồng bị ngắt | `DOWN` | Phép kiểm tra bị gián đoạn; giữ tín hiệu ngắt cho mã bên ngoài. |
| Exception ngoài các loại đã nhận diện | `DOWN` | Không đủ cơ sở để tuyên bố thành phần đang phục vụ. |

Đây là **chính sách của thành phần gợi ý trong bài**. Không áp dụng máy móc cho chức năng bắt buộc như xác nhận thanh toán. Với một chức năng không có đường dự phòng hợp lệ, lỗi ở đường chính có thể phải dẫn ngay tới `DOWN`.

Trong hệ thống thật, tín hiệu “dự phòng sẵn sàng” phải phản ánh dữ liệu hoặc cơ chế dự phòng đang dùng: có dữ liệu, dữ liệu còn hạn, đã được kiểm tra tính hợp lệ và đáp ứng phần chức năng được cam kết. Một biến cấu hình `true` không chứng minh tất cả những điều đó.

## 5. Ví dụ đầy đủ: phân loại exception và trả Health an toàn

Tạo một dự án Maven độc lập. Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>health-failure-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.1. Indicator

Tệp `src/main/java/learning/healthfailure/RecommendationHealthIndicator.java`:

```java
package learning.healthfailure;

import java.io.IOException;
import java.net.SocketTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.Objects;
import java.util.concurrent.TimeoutException;
import java.util.function.BooleanSupplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.Status;

public final class RecommendationHealthIndicator implements HealthIndicator {

    public static final Status DEGRADED = new Status("DEGRADED");

    @FunctionalInterface
    public interface Probe {
        void verify() throws Exception;
    }

    public static final class ProbeMisconfiguredException extends Exception {
        public ProbeMisconfiguredException(String message) {
            super(message);
        }
    }

    private final Probe primary;
    private final BooleanSupplier fallbackReady;

    public RecommendationHealthIndicator(Probe primary, BooleanSupplier fallbackReady) {
        this.primary = Objects.requireNonNull(primary, "primary");
        this.fallbackReady = Objects.requireNonNull(fallbackReady, "fallbackReady");
    }

    @Override
    public Health health() {
        try {
            primary.verify();
            return result(Status.UP, "PRIMARY_READY", "NOT_NEEDED");
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return result(Status.DOWN, "CHECK_INTERRUPTED", "NOT_CHECKED");
        }
        catch (ProbeMisconfiguredException ex) {
            return result(Status.DOWN, "PROBE_MISCONFIGURED", "NOT_CHECKED");
        }
        catch (HttpTimeoutException | SocketTimeoutException | TimeoutException ex) {
            return afterPrimaryFailure("DEPENDENCY_TIMEOUT");
        }
        catch (IOException ex) {
            return afterPrimaryFailure("DEPENDENCY_IO_FAILURE");
        }
        catch (Exception ex) {
            return result(Status.DOWN, "UNEXPECTED_CHECK_FAILURE", "NOT_CHECKED");
        }
    }

    private Health afterPrimaryFailure(String reason) {
        try {
            return fallbackReady.getAsBoolean()
                    ? result(DEGRADED, reason, "READY")
                    : result(Status.DOWN, reason, "NOT_READY");
        }
        catch (RuntimeException ex) {
            return result(Status.DOWN, "FALLBACK_CHECK_FAILED", "UNKNOWN");
        }
    }

    private static Health result(Status status, String reason, String fallback) {
        return Health.status(status)
                .withDetail("reason", reason)
                .withDetail("fallback", fallback)
                .build();
    }
}
```

### 5.2. Vì sao các nhánh được viết như vậy?

**Bắt timeout trước IOException.** `HttpTimeoutException` và `SocketTimeoutException` thuộc nhánh `IOException`, còn `java.util.concurrent.TimeoutException` là một checked exception khác. Nếu bắt `IOException` trước, phần phân loại timeout cụ thể sẽ không còn đúng như thiết kế; Java cũng không cho đặt nhánh catch cho lớp con sau nhánh đã bắt lớp cha đó. Đối chiếu [HttpTimeoutException](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpTimeoutException.html) và [TimeoutException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeoutException.html).

**Khôi phục cờ ngắt.** Khi đã bắt `InterruptedException` và không ném tiếp, ví dụ gọi `Thread.currentThread().interrupt()` để giữ tín hiệu cho tầng gọi. Nó không thử lại, không kiểm tra thêm dự phòng và không coi gián đoạn là bằng chứng rằng tài nguyên bên ngoài đã hỏng. Xem [hợp đồng InterruptedException trong Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InterruptedException.html).

**Lỗi cấu hình có nhánh riêng.** `ProbeMisconfiguredException` là hợp đồng do ví dụ định nghĩa. Adapter thật có thể dùng nó khi xác định cấu hình của phép kiểm tra không hợp lệ. Không được suy đoán mọi HTTP `4xx` hoặc mọi exception thư viện đều cùng loại; cần hiểu giao thức và client trước khi ánh xạ.

**Lỗi khi kiểm tra dự phòng cũng phải được xử lý.** Exception phát sinh bên trong một khối `catch` không tự chạy sang các khối `catch` ngang hàng của cùng `try`. Vì vậy, `afterPrimaryFailure` có xử lý riêng cho lỗi từ `BooleanSupplier`, thay vì để lỗi dự phòng thoát ra ngoài `health()`.

**Không công bố thông điệp exception.** Các nhánh chỉ tạo `reason` và `fallback` từ tập giá trị đã kiểm soát. Chúng không gọi `withDetail("error", ex.getMessage())`, không đính kèm token, URL nội bộ hoặc đối tượng exception vào kết quả. Mã ví dụ không triển khai hệ thống log; trong ứng dụng thật vẫn cần chẩn đoán nội bộ có kiểm soát truy cập và giới hạn tần suất.

**Không retry trong indicator.** Một lần gọi health chỉ thử đường chính một lần và chỉ đọc tín hiệu dự phòng khi cần. Cơ chế khôi phục, tải lại dữ liệu hoặc gọi nghiệp vụ dự phòng thực tế thuộc thành phần sở hữu chức năng, không nằm trong phép quan sát này.

## 6. Chạy kiểm tra mà không cần dịch vụ mạng

Tệp `src/main/java/learning/healthfailure/HealthFailureDemo.java`:

```java
package learning.healthfailure;

import java.io.IOException;
import java.net.http.HttpTimeoutException;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.Status;

import learning.healthfailure.RecommendationHealthIndicator.Probe;
import learning.healthfailure.RecommendationHealthIndicator.ProbeMisconfiguredException;

public class HealthFailureDemo {

    public static void main(String[] args) {
        check("primary", () -> {}, () -> true, Status.UP, "PRIMARY_READY");
        check("ioWithFallback", () -> { throw new IOException("internal IO diagnostic"); },
                () -> true, RecommendationHealthIndicator.DEGRADED, "DEPENDENCY_IO_FAILURE");
        check("timeoutWithFallback", () -> { throw new TimeoutException("internal timeout"); },
                () -> true, RecommendationHealthIndicator.DEGRADED, "DEPENDENCY_TIMEOUT");
        check("httpTimeoutWithFallback", () -> { throw new HttpTimeoutException("internal timeout"); },
                () -> true, RecommendationHealthIndicator.DEGRADED, "DEPENDENCY_TIMEOUT");
        check("noFallback", () -> { throw new IOException("internal IO diagnostic"); },
                () -> false, Status.DOWN, "DEPENDENCY_IO_FAILURE");
        check("misconfigured", () -> { throw new ProbeMisconfiguredException("internal config"); },
                () -> true, Status.DOWN, "PROBE_MISCONFIGURED");
        check("unexpected", () -> { throw new IllegalStateException("internal bug"); },
                () -> true, Status.DOWN, "UNEXPECTED_CHECK_FAILURE");
        check("fallbackFailure", () -> { throw new IOException("internal IO diagnostic"); },
                () -> { throw new IllegalStateException("internal fallback bug"); },
                Status.DOWN, "FALLBACK_CHECK_FAILED");

        try {
            check("interrupted", () -> { throw new InterruptedException("test interruption"); },
                    () -> true, Status.DOWN, "CHECK_INTERRUPTED");
            if (!Thread.currentThread().isInterrupted()) {
                throw new AssertionError("Interrupt flag was lost");
            }
            System.out.println("interruptFlag=true");
        }
        finally {
            Thread.interrupted();
        }

        Set<Status> statuses = Set.of(Status.UP, RecommendationHealthIndicator.DEGRADED);
        Status defaultAggregate = new SimpleStatusAggregator().getAggregateStatus(statuses);
        Status configuredAggregate = new SimpleStatusAggregator(
                "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UP", "UNKNOWN").getAggregateStatus(statuses);
        if (!Status.UP.equals(defaultAggregate)
                || !RecommendationHealthIndicator.DEGRADED.equals(configuredAggregate)) {
            throw new AssertionError("Unexpected aggregation");
        }

        var mapper = new SimpleHttpCodeStatusMapper(Map.of(
                "DOWN", 503, "OUT_OF_SERVICE", 503, "DEGRADED", 200));
        int code = mapper.getStatusCode(configuredAggregate);
        if (code != 200 || mapper.getStatusCode(Status.DOWN) != 503) {
            throw new AssertionError("Unexpected HTTP mapping");
        }
        System.out.println("defaultAggregate=" + defaultAggregate.getCode());
        System.out.println("configuredAggregate=" + configuredAggregate.getCode());
        System.out.println("configuredHttp=" + code);
    }

    private static void check(String name, Probe primary, BooleanSupplier fallback,
            Status expected, String expectedReason) {
        AtomicInteger calls = new AtomicInteger();
        Probe counted = () -> {
            calls.incrementAndGet();
            primary.verify();
        };
        Health result = new RecommendationHealthIndicator(counted, fallback).health();
        if (!expected.equals(result.getStatus())
                || !expectedReason.equals(result.getDetails().get("reason"))
                || calls.get() != 1
                || result.getDetails().containsKey("error")) {
            throw new AssertionError("Unexpected result for " + name + ": " + result);
        }
        System.out.println(name + "=" + result.getStatus().getCode() + " (" + expectedReason + ")");
    }
}
```

Đây là chương trình chạy đầy đủ. Những lambda cố ý ném exception để kiểm tra chính sách; chúng không thực hiện I/O và không mô phỏng thời gian chờ thực tế. Vì vậy, kiểm tra không phụ thuộc một máy chủ bên ngoài có đang chạy hay không.

Tại thư mục chứa `pom.xml`, xác nhận Maven dùng JDK 21 rồi biên dịch và lấy classpath:

```shell
mvn -version
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

Chạy trên PowerShell:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.healthfailure.HealthFailureDemo
```

Hoặc chạy trên Linux/macOS:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.healthfailure.HealthFailureDemo
```

Maven đã biên dịch các tệp Java cùng thư viện phụ thuộc. Không chạy `javac RecommendationHealthIndicator.java` đơn lẻ khi chưa cung cấp classpath Actuator.

Stdout chính xác của chương trình là:

```text
primary=UP (PRIMARY_READY)
ioWithFallback=DEGRADED (DEPENDENCY_IO_FAILURE)
timeoutWithFallback=DEGRADED (DEPENDENCY_TIMEOUT)
httpTimeoutWithFallback=DEGRADED (DEPENDENCY_TIMEOUT)
noFallback=DOWN (DEPENDENCY_IO_FAILURE)
misconfigured=DOWN (PROBE_MISCONFIGURED)
unexpected=DOWN (UNEXPECTED_CHECK_FAILURE)
fallbackFailure=DOWN (FALLBACK_CHECK_FAILED)
interrupted=DOWN (CHECK_INTERRUPTED)
interruptFlag=true
defaultAggregate=UP
configuredAggregate=DEGRADED
configuredHttp=200
```

Lệnh `Thread.interrupted()` trong `finally` chỉ dọn tín hiệu của **luồng main do chương trình kiểm tra sở hữu**, sau khi đã xác minh cờ được giữ. Nó không phải hướng dẫn để mã indicator xóa cờ ngắt của luồng phục vụ request. Trong indicator, cờ vẫn được khôi phục bằng `interrupt()`.

## 7. Vì sao DEGRADED có thể biến mất ở kết quả tổng?

`SimpleStatusAggregator` mặc định chỉ xếp hạng các status quen thuộc của nó. Với tập `{UP, DEGRADED}` mà `DEGRADED` chưa có trong thứ tự, kết quả mặc định có thể là `UP`; nếu không có status nào được nhận diện, kết quả là `UNKNOWN`. Không thể suy ra rằng status mới tự đứng giữa `UP` và `DOWN` chỉ từ ý nghĩa tiếng Anh của tên đó. Xem [mã SimpleStatusAggregator](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Để dùng chính sách trong bài, cấu hình thứ tự từ nghiêm trọng hơn tới ít nghiêm trọng hơn:

```properties
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
```

Khi đó:

| Status các thành phần | Kết quả tổng theo thứ tự trên |
| --- | --- |
| `UP`, `DEGRADED` | `DEGRADED` |
| `DOWN`, `DEGRADED` | `DOWN` |
| `OUT_OF_SERVICE`, `DEGRADED` | `OUT_OF_SERVICE` |

Đây không phải bỏ phiếu theo số lượng. Mười indicator `UP` không lấn át một indicator `DOWN` khi `DOWN` đứng trước trong thứ tự.

Không thêm status tùy chỉnh vào một module rồi quên những consumer đang đọc status đó: công cụ giám sát, health group, probe và dashboard có thể có những giả định khác nhau. Một health group có chính sách riêng cũng cần được kiểm tra riêng, thay vì mặc định suy ra từ endpoint tổng.

## 8. Ánh xạ HTTP phải thể hiện đúng quyết định vận hành

Ví dụ chọn **HTTP 200 cho DEGRADED** vì đường dự phòng vẫn đáp ứng phần chức năng được chấp nhận. Công cụ giám sát muốn báo suy giảm phải đọc JSON hoặc có tín hiệu riêng; chỉ kiểm tra “HTTP có thành công không” sẽ không nhận ra chất lượng chức năng đã giảm.

```properties
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=200
```

Cần giữ cả hai dòng `down` và `out-of-service`. Trong Spring Boot 3.3, khi cấu hình mapping tùy chỉnh, các mapping mặc định của hai status này không tự được giữ nguyên. Chỉ thêm `degraded=200` có thể khiến các status lỗi còn lại rơi vào mã mặc định `200` nếu chưa được khai báo lại. Đối chiếu [quy định ánh xạ status của health endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

Nếu yêu cầu của một endpoint là “suy giảm thì không nhận thêm lưu lượng”, có thể chọn `degraded=503` cho endpoint hoặc nhóm được thiết kế cho mục đích đó. Quyết định này không nên được dùng tùy tiện cho mọi phép kiểm tra: việc tách máy ra khỏi lưu lượng phải giúp hệ thống phục hồi, không tạo một sự cố dây chuyền vì một dịch vụ tùy chọn tạm lỗi.

`UNKNOWN` cũng không mặc nhiên là lỗi HTTP. Với mapping mặc định, nó không tự trở thành `503`. Nếu thiếu bằng chứng phải làm hệ thống ngừng nhận việc, cần biểu đạt điều đó bằng chính sách status và HTTP rõ ràng.

## 9. Quan sát cùng chính sách trong ứng dụng Spring Boot

Tệp `src/main/java/learning/healthfailure/HealthFailureApplication.java`:

```java
package learning.healthfailure;

import java.io.IOException;
import java.util.concurrent.TimeoutException;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import learning.healthfailure.RecommendationHealthIndicator.Probe;
import learning.healthfailure.RecommendationHealthIndicator.ProbeMisconfiguredException;

@SpringBootApplication
public class HealthFailureApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthFailureApplication.class, args);
    }

    @Bean
    RecommendationHealthIndicator recommendationHealthIndicator(
            @Value("${demo.primary:io}") String mode,
            @Value("${demo.fallback-ready:true}") boolean fallbackReady) {
        Probe probe = switch (mode) {
            case "up" -> () -> {};
            case "io" -> () -> { throw new IOException("simulated IO failure"); };
            case "timeout" -> () -> { throw new TimeoutException("simulated timeout"); };
            case "misconfigured" -> () -> {
                throw new ProbeMisconfiguredException("simulated invalid probe configuration");
            };
            default -> throw new IllegalArgumentException("Unsupported demo mode");
        };
        return new RecommendationHealthIndicator(probe, () -> fallbackReady);
    }
}
```

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
management.endpoint.health.status.order=down,out-of-service,degraded,up,unknown
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.degraded=200
```

Các giá trị `demo.*` chỉ tạo tình huống học tập, không triển khai dịch vụ gợi ý hoặc cơ chế dự phòng thật. Khi tích hợp thật, thay các nguồn tín hiệu mô phỏng bằng phép kiểm tra và bằng chứng dự phòng đúng phạm vi. Indicator không tự xây dựng khả năng dự phòng chỉ vì nó có thể trả `DEGRADED`.

Tên bean là `recommendationHealthIndicator`, nên tên contributor mặc định là `recommendation`. Chạy:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.healthfailure.HealthFailureApplication"
```

Ở terminal khác:

```shell
curl -i http://127.0.0.1:8080/actuator/health/recommendation
curl -i http://127.0.0.1:8080/actuator/health
```

Trên Windows có thể dùng `mvn.cmd` và `curl.exe`. Với tình huống mặc định `demo.primary=io` và dự phòng sẵn sàng, nhánh recommendation trả HTTP `200` với phần thân:

```json
{
  "status": "DEGRADED",
  "details": {
    "reason": "DEPENDENCY_IO_FAILURE",
    "fallback": "READY"
  }
}
```

Thứ tự khóa và khoảng trắng JSON không quan trọng. Ở endpoint tổng, các thành phần khác vẫn tham gia; nếu một thành phần khác `DOWN` thì status tổng theo cấu hình này sẽ là `DOWN`.

Dừng ứng dụng rồi thử không có dự phòng:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.healthfailure.HealthFailureApplication" "-Dspring-boot.run.arguments=--demo.fallback-ready=false"
```

Nhánh recommendation chuyển thành `DOWN`, `fallback=NOT_READY` và HTTP `503`. Thay bằng đối số `--demo.primary=up` để quan sát `UP`, hoặc `--demo.primary=timeout` để quan sát `reason=DEPENDENCY_TIMEOUT` khi vẫn có dự phòng.

Ví dụ hiển thị details đầy đủ trên loopback để học. Ở môi trường vận hành, quyền truy cập và chính sách `show-details` phải phù hợp; các trường health tùy chỉnh không nên chứa bí mật ngay từ đầu.

## 10. Timeout, gián đoạn và kiểm tra chậm là ba chuyện khác nhau

**Timeout** nghĩa là một thao tác có hạn chót và không hoàn tất trong thời gian cho phép. Bắt `TimeoutException` chỉ xử lý một tín hiệu timeout đã phát sinh; bản thân khối `catch` không thiết lập thời gian chờ cho `primary.verify()`.

**Gián đoạn luồng** là tín hiệu hợp tác để thao tác đang chặn hoặc đang làm việc dừng lại theo hợp đồng. Khi đã bắt `InterruptedException`, không retry ngay, không xóa tín hiệu rồi báo `UP` và không giả định mạng bên ngoài đã hỏng.

**Kiểm tra chậm** là điều quan sát được về thời lượng. Thuộc tính `management.endpoint.health.logging.slow-indicator-threshold` điều chỉnh ngưỡng ghi cảnh báo của Actuator, không tự hủy lời gọi hoặc chuyển nó sang một status khác.

Khi viết adapter có I/O thực tế, cần xác định thời gian chờ của client, thời gian chờ kết nối, thời gian chờ thao tác và tổng chi phí của phép kiểm tra. Không giả định một timeout ở lớp bọc có thể tự dừng công việc bên dưới.

Ví dụ `Future.get(timeout)` có thể ném `TimeoutException`, nhưng tác vụ được chờ vẫn có thể tiếp tục chạy. Kể cả gọi `cancel(true)`, việc dừng còn phụ thuộc tác vụ và client có tôn trọng ngắt hay không. Tạo một executor mới mỗi lần health rồi bỏ tác vụ chạy nền sẽ làm giám sát tạo thêm tải và rò rỉ tài nguyên.

Nếu adapter bọc lỗi trong `CompletionException` hoặc `ExecutionException`, cần giải bọc có kiểm soát rồi phân loại nguyên nhân theo hợp đồng của adapter. Khối catch cho `IOException` không tự bắt một IOException đang nằm bên trong một wrapper khác. Với chuỗi reactive, tín hiệu lỗi cần được xử lý trong chuỗi, chẳng hạn bằng `onErrorResume`, thay vì chỉ đặt `try/catch` quanh bước tạo publisher.

## 11. Giữ kết quả hữu ích mà không che nguyên nhân

Kết quả công bố và dữ liệu chẩn đoán nội bộ có mục đích khác nhau:

| Nơi sử dụng | Thông tin phù hợp |
| --- | --- |
| Health công bố | Status, mã lý do ổn định, trạng thái dự phòng và các số đo không nhạy cảm. |
| Log nội bộ có kiểm soát | Loại lỗi, thời điểm, thành phần, mã tương quan và nguyên nhân cần để điều tra. |
| Metrics | Tần suất thất bại, thời lượng phép thử, số lần suy giảm và thời gian phục hồi. |

Tránh hai cực đoan: trả toàn bộ stack trace ra endpoint hoặc nuốt mọi lỗi khiến người vận hành chỉ thấy `DOWN` mà không có cách điều tra. Trong hệ thống thật, cần bổ sung chẩn đoán nội bộ phù hợp, tránh ghi cùng một stack trace cho mỗi lần polling và tránh biến lỗi dự kiến thành một luồng log không giới hạn.

Không dùng `Health.down(ex)` khi chưa xem xét nội dung exception có thể đi vào details và các kênh hiển thị khác. Cũng không cho rằng cơ chế che giá trị của `/env` tự động xử lý mọi chuỗi do mình đưa vào custom health.

Sau một lỗi tạm thời, lần kiểm tra tiếp theo có thể trở lại `UP` nếu đường chính thành công. Đừng giữ một cờ “đã từng lỗi” vĩnh viễn rồi quên thiết kế điều kiện xóa. Nếu cần cơ chế chống dao động, dùng một chính sách có trạng thái, ngưỡng và cửa sổ thời gian rõ ràng; `HealthIndicator` không tự cung cấp các điều kiện đó chỉ vì có nhiều lần polling.

## 12. Tự kiểm chứng chính sách thay vì chỉ thử đường thành công

Trước khi dùng trong vận hành, cần có bằng chứng cho từng lớp:

- **Phân loại:** timeout, I/O, cấu hình sai, lỗi bất ngờ và lỗi của đường dự phòng đi vào nhánh dự kiến.
- **Ngắt luồng:** cờ ngắt được giữ; không phát sinh retry hoặc I/O phụ sau khi bị ngắt.
- **Tác dụng phụ:** probe chỉ quan sát, không gửi giao dịch thật, không làm mới dữ liệu và không tạo tài nguyên không được quản lý.
- **Độ kín của dữ liệu:** details không chứa exception message, token hoặc dữ liệu người dùng; đường log nội bộ vẫn đủ để điều tra.
- **Tổng hợp:** `UP + DEGRADED` cho `DEGRADED`; `DOWN + DEGRADED` vẫn cho `DOWN` theo thứ tự đã chọn.
- **HTTP:** xác minh `DOWN=503`, `OUT_OF_SERVICE=503`, và `DEGRADED` đúng chính sách sau khi thêm mapping tùy chỉnh.
- **Phục hồi:** cùng thành phần có thể chuyển từ lỗi sang `UP` khi bằng chứng thay đổi; trạng thái cũ không bị giữ nhầm.
- **Chi phí thật:** kiểm tra thời gian và khả năng hủy với client I/O thật; các lambda ném exception trong bài chưa chứng minh điều này.

Nếu JSON có `DEGRADED` nhưng công cụ giám sát vẫn báo khỏe, hãy kiểm tra công cụ đang đọc trường nào và HTTP có được chọn là `200` hay không. Nếu nhánh riêng là `DEGRADED` nhưng endpoint tổng là `UP`, hãy kiểm tra thứ tự status. Nếu request treo dù đã có catch timeout, hãy kiểm tra thao tác bên dưới có thực sự được cấu hình timeout không.

Xử lý ngoại lệ đúng trong health không chỉ là tránh một exception thoát ra ngoài. Nó cần chuyển bằng chứng thành trạng thái có ý nghĩa, giữ đúng tín hiệu gián đoạn, mô tả suy giảm trung thực và làm cho cả kết quả tổng lẫn HTTP phản ánh chính sách đã chọn.
