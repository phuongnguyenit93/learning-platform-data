# Kiểm thử HealthIndicator và InfoContributor độc lập

Khi dịch vụ kho phản hồi bình thường, chỉ báo sức khỏe cần trả `UP`. Nếu dịch vụ kho không liên lạc được, chỉ báo cần trả `DOWN` cùng lý do phù hợp. Thành phần đóng góp thông tin có nhiệm vụ khác. Nó thêm phiên bản phát hành vào dữ liệu mà Actuator sẽ tổng hợp. Cả hai hành vi có thể được kiểm tra bằng cách khởi tạo lớp bằng `new`, gọi phương thức và đối chiếu đối tượng trả về hoặc dữ liệu được thêm vào.

| Thành phần | Gọi trực tiếp | Điều cần xác nhận |
| --- | --- | --- |
| `HealthIndicator` | `health()` | Giá trị `Status` và nội dung `Health.getDetails()` ứng với từng kết quả của phép kiểm tra phụ thuộc. |
| `InfoContributor` | `contribute(builder)` | Khóa, kiểu dữ liệu, giá trị được thêm vào `Info.Builder` và việc giữ nguyên các mục đã có với khóa khác. |

Khi chạy trong ứng dụng, Actuator phát hiện các thành phần được đăng ký dưới dạng bean. Trong kiểm thử đơn vị, chính bài kiểm thử tạo các thành phần và truyền dữ liệu đầu vào. Cách này cho phép tái tạo từng nhánh mà không cần khởi động Spring, mở cổng HTTP hoặc gọi dịch vụ kho. [HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html) · [Thành phần mở rộng của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## Chuẩn bị dự án mẫu

Ví dụ dùng Java 17 trở lên, Gradle, Spring Boot Actuator 3.3.0 và JUnit Jupiter. Tạo `build.gradle` trong một thư mục thử nghiệm riêng. Danh mục phiên bản của Spring Boot (BOM) cung cấp các phiên bản phụ thuộc tương ứng. Tác vụ `test` chạy các kiểm thử qua JUnit Platform.

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-actuator'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed'
    }
}
```

## Kiểm thử HealthIndicator

Tách phần kết nối dịch vụ kho thành `InventoryProbe` và truyền qua constructor. Lớp chỉ báo chỉ chuyển kết quả kiểm tra thành `Health`. Chính sách của ví dụ là trả `UP` khi kết nối được, `DOWN` với lý do `unreachable` khi phép kiểm tra trả `false` và `DOWN` với lý do `probe_failed` khi xảy ra lỗi I/O.

**`src/main/java/demo/actuator/InventoryHealthIndicator.java`**

```java
package demo.actuator;

import java.io.IOException;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public final class InventoryHealthIndicator implements HealthIndicator {

    @FunctionalInterface
    public interface InventoryProbe {
        boolean isReachable() throws IOException;
    }

    private final InventoryProbe probe;

    public InventoryHealthIndicator(InventoryProbe probe) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        try {
            if (probe.isReachable()) {
                return Health.up().build();
            }
            return Health.down().withDetail("reason", "unreachable").build();
        } catch (IOException failure) {
            return Health.down().withDetail("reason", "probe_failed").build();
        }
    }
}
```

Mỗi ca dùng một phép kiểm tra giả được xác định trước. Hai lambda đầu trả ngay `true` hoặc `false`. Lambda thứ ba ném `SocketTimeoutException` để mô phỏng hết thời gian chờ mà không cần ngủ hay chờ mạng. So sánh toàn bộ map chi tiết giúp phát hiện cả việc trả sai lý do lẫn việc vô tình đưa thông điệp ngoại lệ chứa địa chỉ nội bộ vào kết quả.

**`src/test/java/demo/actuator/InventoryHealthIndicatorTest.java`**

```java
package demo.actuator;

import java.net.SocketTimeoutException;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InventoryHealthIndicatorTest {

    @Test
    void returnsUpWhenTheProbeSucceeds() {
        var indicator = new InventoryHealthIndicator(() -> true);

        Health result = indicator.health();

        assertEquals(Status.UP, result.getStatus());
        assertEquals(Map.of(), result.getDetails());
    }

    @Test
    void returnsDownWhenTheProbeReportsUnreachable() {
        var indicator = new InventoryHealthIndicator(() -> false);

        Health result = indicator.health();

        assertEquals(Status.DOWN, result.getStatus());
        assertEquals(Map.of("reason", "unreachable"), result.getDetails());
    }

    @Test
    void returnsDownWithASafeReasonWhenTheProbeTimesOut() {
        var indicator = new InventoryHealthIndicator(() -> {
            throw new SocketTimeoutException("private endpoint: inventory.internal");
        });

        Health result = indicator.health();

        assertEquals(Status.DOWN, result.getStatus());
        assertEquals(Map.of("reason", "probe_failed"), result.getDetails());
    }
}
```

Dùng `Status.UP` và `Status.DOWN` để đối chiếu kết quả ở tầng Java. Việc tổng hợp chỉ báo, quyết định mức hiển thị chi tiết và ánh xạ trạng thái sang mã HTTP nằm ở tầng endpoint. Các quy tắc đó cần kiểm thử với cấu hình ứng dụng khi chúng là một phần của yêu cầu. [Cấu hình Health endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health)

## Kiểm thử InfoContributor

`contribute` bổ sung dữ liệu vào builder do bên gọi truyền vào. Ví dụ dùng khóa cấp cao `inventory`, với một map lồng chứa `release`. Lớp nhận phiên bản phát hành qua constructor, nên bài kiểm thử kiểm soát được giá trị mà không phải đọc cấu hình từ môi trường.

**`src/main/java/demo/actuator/InventoryInfoContributor.java`**

```java
package demo.actuator;

import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;

public final class InventoryInfoContributor implements InfoContributor {

    private final String release;

    public InventoryInfoContributor(String release) {
        this.release = release;
    }

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("inventory", Map.of("release", release));
    }
}
```

Khởi tạo `Info.Builder` thật và điền trước một mục mô phỏng dữ liệu do thành phần khác cung cấp. Gọi `contribute`, sau đó gọi `build().getDetails()` để kiểm tra dữ liệu cuối cùng. So sánh các map kiểm tra được cấu trúc lồng, giá trị và mục đã có mà không phụ thuộc thứ tự các khóa. Đặt khóa cấp cao riêng cho mỗi thành phần để tránh hai thành phần ghi cùng một mục. [Cách đóng góp dữ liệu cho Info endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info.writing-custom-info-contributors)

**`src/test/java/demo/actuator/InventoryInfoContributorTest.java`**

```java
package demo.actuator;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InventoryInfoContributorTest {

    @Test
    void addsInventoryMetadataWithoutOverwritingOtherEntries() {
        var contributor = new InventoryInfoContributor("2026.11");
        Info.Builder builder = new Info.Builder()
            .withDetail("application", Map.of("name", "store"));

        contributor.contribute(builder);

        assertEquals(
            Map.of(
                "application", Map.of("name", "store"),
                "inventory", Map.of("release", "2026.11")
            ),
            builder.build().getDetails()
        );
    }
}
```

## Chạy và đọc kết quả

Từ thư mục chứa `build.gradle`, chạy lệnh sau.

```bash
gradle test
```

Kỳ vọng ba ca của `InventoryHealthIndicatorTest` và một ca của `InventoryInfoContributorTest` đều đạt. Kiểm thử thứ ba của chỉ báo chứng minh cách lớp **xử lý** ngoại lệ hết thời gian chờ. Để kiểm tra client thật có áp dụng đúng thời gian chờ đã cấu hình, hãy kiểm thử client ở tầng tích hợp.

Khi kết nối hai thành phần với ứng dụng thực tế, các kiểm thử bổ sung có thể xác nhận bean được phát hiện, chỉ báo xuất hiện dưới đúng tên hoặc đúng nhóm health, và dữ liệu được công bố đúng cấu hình ở `/actuator/health` hoặc `/actuator/info`. Nếu kiểm thử độc lập thất bại, bắt đầu từ logic chuyển đổi trong thành phần. Nếu chỉ kiểm thử endpoint thất bại, kiểm tra cách đăng ký bean và cấu hình endpoint trước khi sửa các quy tắc đã được kiểm chứng ở tầng Java.
