# Tạo kết quả bằng Health.Builder với chi tiết có ý nghĩa chẩn đoán

Một kết quả `DOWN` báo rằng một điều kiện sức khỏe không đạt, nhưng chưa giúp người vận hành biết cần kiểm tra gì. Ngược lại, một phản hồi chứa hàng trăm trường cũng chưa chắc hữu ích nếu thiếu thông tin về phép kiểm tra, ngưỡng và nguyên nhân.

`Health.Builder` giúp tạo kết quả gồm **trạng thái** và **ngữ cảnh chẩn đoán**. Mục tiêu của bài là xây dựng kết quả có thể giải thích được: đã kiểm tra điều gì, quan sát thấy gì, vì sao chọn trạng thái đó và những thông tin nào nên được công bố.

Ví dụ dùng Java 21 và Spring Boot Actuator 3.3.x. Chương trình thực hành cố định thư viện Actuator 3.3.0 để người học có thể đối chiếu chính xác hành vi được minh họa.

## 1. Health, Builder và phép kiểm tra có quan hệ gì?

Một `Health` biểu diễn tình trạng của một thành phần hoặc hệ thống con. Hai phần cần quan tâm là:

- `status`: trạng thái như UP, DOWN, OUT_OF_SERVICE hoặc UNKNOWN.
- `details`: bản đồ dữ liệu bổ sung có khóa kiểu `String`, giá trị kiểu `Object`.

`Health.Builder` là đối tượng dùng trong quá trình tạo kết quả. Các phương thức nối tiếp nhau trả về Builder; `build()` trả về `Health`. [API Health của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

Luồng thiết kế nên là:

```text
Thu thập quan sát
        ↓
Đánh giá quan sát theo chính sách của thành phần
        ↓
Chọn trạng thái
        ↓
Thêm chi tiết giải thích cho quyết định
        ↓
build() → Health
```

Builder không tự kiểm tra kết nối, đo dung lượng hay xác minh nghiệp vụ. Nó biểu diễn kết quả mà mã của ứng dụng đã đánh giá.

Ví dụ đơn giản, đặt trong một phương thức có thể trả về `Health`:

```java
return Health.down()
        .withDetail("target", "archive-store")
        .withDetail("check", "write-capacity")
        .withDetail("reasonCode", "LOW_CAPACITY")
        .withDetail("freeMiB", 40L)
        .withDetail("requiredMiB", 100L)
        .build();
```

Đây là đoạn thân phương thức, không phải chương trình Java độc lập. Với dữ liệu trên, người đọc biết thành phần lưu trữ chưa đạt ngưỡng 100 MiB vì chỉ còn 40 MiB, thay vì chỉ nhận một nhãn DOWN.

## 2. Chọn trạng thái theo ý nghĩa, không theo lượng thông tin

| Cách tạo/chuyển trạng thái | Ý nghĩa của thao tác | Cách dùng trong một chính sách ví dụ |
| --- | --- | --- |
| `Health.up()` hoặc `builder.up()` | Đặt trạng thái UP | Quan sát đáp ứng điều kiện đã xác định |
| `Health.down()` hoặc `builder.down()` | Đặt trạng thái DOWN | Điều kiện cần thiết không đạt |
| `Health.outOfService()` hoặc `builder.outOfService()` | Đặt OUT_OF_SERVICE | Thành phần chủ động ngừng cung cấp dịch vụ trong thời gian bảo trì |
| `Health.unknown()` hoặc `builder.unknown()` | Đặt UNKNOWN | Chưa đủ quan sát hợp lệ để kết luận theo chính sách |
| `Health.status(...)` hoặc `builder.status(...)` | Đặt trạng thái được chỉ định | Trạng thái chuẩn hoặc trạng thái tùy chỉnh có ý nghĩa đã được định nghĩa |

Các phương thức trên đặt giá trị trạng thái; việc chọn trạng thái nào là trách nhiệm của mã đánh giá. Ví dụ bảo trì và quan sát không hợp lệ trong bảng là chính sách minh họa của ứng dụng, không phải luật suy luận tự động của Builder. [Các phương thức Health.Builder](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.Builder.html).

### Các điểm cần tránh nhầm

**Có details không có nghĩa là UP.** Một kết quả có nhiều thông tin chẩn đoán vẫn có thể là DOWN hoặc UNKNOWN.

**Đổi trạng thái không tự xóa details.** Nếu một Builder đã chứa nguyên nhân thất bại, gọi `up()` không tự loại bỏ nguyên nhân đó. Việc sử dụng lại Builder qua nhiều nhánh hoặc nhiều lần kiểm tra dễ tạo kết quả tự mâu thuẫn.

**Thêm một khóa tên status không đổi trạng thái thật.** Ví dụ `withDetail("status", "DOWN")` chỉ thêm dữ liệu trong details. Muốn đổi trạng thái, phải dùng phương thức trạng thái. Nên tránh khóa gây nhầm với cấu trúc bao ngoài.

**Builder mặc định chưa phải UP.** Trong phiên bản được thực hành, `new Health.Builder().build()` cho trạng thái UNKNOWN. Mỗi đường trả kết quả nên chọn trạng thái có chủ đích.

**Trạng thái tùy chỉnh cần chính sách đi kèm.** `Health.status("DEGRADED")` tạo được kết quả có mã đó, nhưng không tự định nghĩa mức nghiêm trọng khi tổng hợp hoặc mã HTTP mong muốn. Cần thiết kế các chính sách này khi sử dụng trạng thái tùy chỉnh.

## 3. Chi tiết nào thực sự giúp chẩn đoán?

Chi tiết tốt giải thích được quyết định bằng dữ liệu có giới hạn, có đơn vị và có liên hệ với phép kiểm tra.

| Câu hỏi của người vận hành | Chi tiết có thể cung cấp | Ví dụ |
| --- | --- | --- |
| Đang nói đến thành phần nào? | Bí danh ổn định của đích kiểm tra | `target: archive-store` |
| Đã thực hiện phép kiểm tra gì? | Tên phép kiểm tra | `check: write-capacity` |
| Vì sao có trạng thái này? | Mã nguyên nhân có ý nghĩa ổn định | `reasonCode: LOW_CAPACITY` |
| Quan sát cụ thể là bao nhiêu? | Giá trị đo hoặc quan sát | `freeMiB: 40` |
| Điều kiện mong muốn là gì? | Ngưỡng hoặc điều kiện đối chiếu | `requiredMiB: 100` |
| Phép kiểm tra mất bao lâu? | Thời gian thực sự đo được | `durationMillis: 18` |
| Kết quả lấy từ lúc nào? | Thời điểm kiểm tra khi cần thiết | `checkedAt` ở dạng thời gian có múi giờ |
| Có dùng kết quả lưu tạm không? | Tuổi kết quả hoặc dấu hiệu nguồn dữ liệu | `observationAgeMillis` nếu thực sự có lưu tạm |

Các tên như `target`, `check` và `reasonCode` trong bài là quy ước do ví dụ chọn, không phải các trường bắt buộc của Spring Boot.

### So sánh trước và sau

Thông tin quá chung:

```json
{
  "status": "DOWN",
  "details": {
    "message": "Something is wrong"
  }
}
```

Thông tin có thể đối chiếu:

```json
{
  "status": "DOWN",
  "details": {
    "target": "archive-store",
    "check": "write-capacity",
    "reasonCode": "LOW_CAPACITY",
    "freeMiB": 40,
    "requiredMiB": 100
  }
}
```

Phản hồi thứ hai hỗ trợ kiểm tra dung lượng và ngưỡng cấu hình. Nó không tuyên bố đã xác định được mọi nguyên nhân gốc, chẳng hạn vì sao dung lượng giảm nhanh.

### Giữ đơn vị và kiểu dữ liệu nhất quán

Nên dùng số cho đại lượng số:

```java
.withDetail("freeMiB", 40L)
.withDetail("requiredMiB", 100L)
```

Hạn chế gộp số và đơn vị vào một câu khó xử lý tự động như `"about 40 MB left"`. Đồng thời phân biệt MiB với MB: MiB dùng 1.048.576 byte, MB dùng 1.000.000 byte. Tên trường và cách chuyển đổi phải thống nhất.

Không thêm một `durationMillis` cố định chỉ để phản hồi có vẻ đầy đủ. Chỉ công bố dữ liệu thời gian nếu đã đo đúng phần việc muốn mô tả. Khi đo khoảng thời gian trong Java, có thể dùng chênh lệch `System.nanoTime()` rồi chuyển đổi đơn vị.

## 4. Dùng withDetail và withDetails đúng mục đích

`withDetail(key, value)` thêm hoặc thay thế một giá trị theo khóa. `withDetails(map)` bổ sung một tập chi tiết; khóa trùng được thay bằng giá trị của map đưa vào.

Ví dụ đoạn mã:

```java
Health health = Health.up()
        .withDetail("retryCount", 1)
        .withDetails(Map.of(
                "retryCount", 2,
                "reasonCode", "PROBE_OK"))
        .build();
```

Giá trị cuối của `retryCount` là số 2. `withDetails` không xóa mọi khóa đã tồn tại; các khóa khác vẫn được giữ. Vì vậy, tránh để nhiều lớp mã cùng ghi một khóa nhưng hiểu khác ý nghĩa của nó.

Một số quy tắc hữu ích:

- Chọn tên trường ổn định và diễn đạt đúng nghĩa.
- Dùng `String`, số, boolean và cấu trúc nhỏ có thể chuyển thành JSON rõ ràng.
- Với dữ liệu nhóm, chỉ đưa vào map/list chứa dữ liệu đã chọn lọc.
- Tránh đưa cả entity, bean dịch vụ, request hoặc đối tượng kết nối vào details.
- Không đưa `null` vào `withDetail`; phương thức này kiểm tra khóa và giá trị khác null trong phiên bản thực hành. Nếu chưa có quan sát, có thể bỏ trường và dùng mã nguyên nhân phù hợp.
- Không công bố một số 0 giả thay cho “chưa đo được”. Hai trường hợp này mang ý nghĩa chẩn đoán khác nhau.

Việc tham số có kiểu `Object` không có nghĩa mọi đối tượng Java đều thích hợp để đưa ra endpoint. Một đối tượng phức tạp có thể chứa thông tin không cần công bố, quan hệ vòng hoặc dữ liệu thay đổi sau khi đã tạo kết quả.

## 5. withException không tự chuyển trạng thái sang DOWN

Hai đoạn sau khác nhau:

```java
Health noted = Health.up()
        .withException(new IllegalStateException("probe failed"))
        .build();

Health failed = Health.down(
        new IllegalStateException("probe failed")).build();
```

Trong Actuator 3.3.0:

- `noted` vẫn có trạng thái UP.
- `failed` có trạng thái DOWN.
- Cả hai có thể chứa detail khóa `error` được tạo từ tên lớp exception và thông điệp của nó.

`withException(...)` ghi thông tin lỗi, còn `down(exception)` kết hợp việc đặt DOWN và ghi thông tin lỗi. Chuỗi `error` không phải toàn bộ stack trace. [Triển khai Health và Builder của Boot 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/Health.java).

Điều này quan trọng khi viết:

```java
Health.Builder builder = Health.up();
```

Nếu nhánh lỗi sau đó chỉ gọi `withException(ex)`, trạng thái có thể vẫn là UP. Cần đặt trạng thái theo chính sách trước khi trả kết quả.

### Khi nên dùng mã lỗi đã chọn lọc

Thông điệp exception có thể chứa tên máy, đường dẫn hoặc nội dung từ hệ thống bên ngoài. Nếu chưa kiểm soát được nội dung đó, có thể xây dựng kết quả chẩn đoán bằng mã nguyên nhân ổn định.

Ví dụ dưới đây chỉ minh họa cách biểu diễn một timeout đã được phát hiện; Builder không tự tạo timeout:

```java
return Health.down()
        .withDetail("target", "archive-store")
        .withDetail("check", "write-probe")
        .withDetail("reasonCode", "PROBE_TIMEOUT")
        .withDetail("timeoutMillis", 200L)
        .build();
```

`timeoutMillis` cần là giới hạn thực tế của phép kiểm tra, không phải một con số phỏng đoán. Thông tin lỗi đầy đủ có thể được ghi vào log được kiểm soát quyền truy cập theo chính sách của hệ thống.

## 6. Chương trình chạy được với thư viện Actuator thật

Ví dụ sau mô phỏng kết quả quan sát dung lượng, rồi sử dụng trực tiếp `Health.Builder`. Nó không đo dung lượng thật và không khởi chạy máy chủ web.

Các quy tắc của phép đánh giá trong ví dụ:

1. Nếu đang bảo trì, trả OUT_OF_SERVICE với nguyên nhân MAINTENANCE.
2. Nếu số liệu không hợp lệ, trả UNKNOWN với nguyên nhân INVALID_OBSERVATION.
3. Nếu còn ít nhất lượng dung lượng yêu cầu, trả UP.
4. Nếu chưa đạt ngưỡng, trả DOWN cùng giá trị quan sát và ngưỡng.

Ở hai nhánh đầu, ví dụ không công bố số dung lượng như thể đó là quan sát hợp lệ vừa được kiểm chứng.

### 6.1. Cấu trúc dự án

Chuẩn bị JDK 21 và Gradle 8.5, sau đó tạo:

```text
health-builder-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/HealthBuilderDemo.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'health-builder-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-actuator'
}

application {
    mainClass = 'HealthBuilderDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

BOM giữ các phiên bản phụ thuộc theo tập phiên bản của Boot 3.3.0. Plugin `application` đủ để chạy chương trình console sử dụng API Actuator; dự án này chưa cấu hình một ứng dụng web.

### 6.2. Mã Java đầy đủ

Tệp `src/main/java/HealthBuilderDemo.java`:

```java
import java.util.Map;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;

public class HealthBuilderDemo {
    record CapacitySnapshot(
            long freeMiB,
            long requiredMiB,
            boolean maintenanceMode) {
    }

    static Health evaluate(CapacitySnapshot snapshot) {
        Health.Builder builder = new Health.Builder()
                .withDetail("target", "archive-store")
                .withDetail("check", "write-capacity");

        if (snapshot.maintenanceMode()) {
            return builder.outOfService()
                    .withDetail("reasonCode", "MAINTENANCE")
                    .build();
        }

        if (snapshot.freeMiB() < 0 || snapshot.requiredMiB() <= 0) {
            return builder.unknown()
                    .withDetail("reasonCode", "INVALID_OBSERVATION")
                    .build();
        }

        builder.withDetails(Map.of(
                "freeMiB", snapshot.freeMiB(),
                "requiredMiB", snapshot.requiredMiB()));

        if (snapshot.freeMiB() >= snapshot.requiredMiB()) {
            return builder.up()
                    .withDetail("reasonCode", "SUFFICIENT_CAPACITY")
                    .build();
        }

        return builder.down()
                .withDetail("reasonCode", "LOW_CAPACITY")
                .build();
    }

    static void report(String name, Health health) {
        Map<String, Object> details = health.getDetails();
        System.out.printf(
                "%s | status=%s | reason=%s | freeMiB=%s | requiredMiB=%s%n",
                name,
                health.getStatus().getCode(),
                details.get("reasonCode"),
                details.getOrDefault("freeMiB", "n/a"),
                details.getOrDefault("requiredMiB", "n/a"));
    }

    public static void main(String[] args) {
        HealthIndicator healthy =
                () -> evaluate(new CapacitySnapshot(250, 100, false));

        report("healthy", healthy.health());
        report("low-capacity",
                evaluate(new CapacitySnapshot(40, 100, false)));
        report("maintenance",
                evaluate(new CapacitySnapshot(250, 100, true)));
        report("invalid-observation",
                evaluate(new CapacitySnapshot(-1, 100, false)));

        Health noted = Health.up()
                .withException(new IllegalStateException("probe failed"))
                .build();
        Health failed = Health.down(
                new IllegalStateException("probe failed")).build();

        System.out.println("withException.status="
                + noted.getStatus().getCode());
        System.out.println("withException.error="
                + noted.getDetails().get("error"));
        System.out.println("downException.status="
                + failed.getStatus().getCode());
        System.out.println("emptyBuilder.status="
                + new Health.Builder().build().getStatus().getCode());

        Health merged = Health.up()
                .withDetail("retryCount", 1)
                .withDetails(Map.of("retryCount", 2))
                .build();
        System.out.println("merged.retryCount="
                + merged.getDetails().get("retryCount"));

        Health.Builder reused = Health.up().withDetail("attempt", 1);
        Health first = reused.build();
        reused.down().withDetail("attempt", 2);
        Health second = reused.build();

        System.out.println("reuse.first.status="
                + first.getStatus().getCode());
        System.out.println("reuse.first.attempt="
                + first.getDetails().get("attempt"));
        System.out.println("reuse.second.status="
                + second.getStatus().getCode());
    }
}
```

Chương trình có một biến kiểu `HealthIndicator` để minh họa hợp đồng trả `Health` của một lần đánh giá. Trong ứng dụng Spring Boot, indicator cần được đăng ký thành bean nếu muốn được hạ tầng health phát hiện.

### 6.3. Chạy chương trình

Tại thư mục dự án:

```shell
gradle -q run --console=plain
```

Nếu dự án đã có Gradle Wrapper, trong PowerShell có thể dùng:

```powershell
.\gradlew.bat -q run --console=plain
```

Trên Linux/macOS:

```shell
./gradlew -q run --console=plain
```

Gradle giải quyết dependency và thiết lập classpath cho chương trình. Nếu gọi trực tiếp `javac` hoặc `java`, người học phải cung cấp classpath có Actuator cùng các thư viện cần thiết; chỉ có JDK không đủ để biên dịch các import Spring.

Stdout của chương trình, không tính thông báo tải dependency hoặc thông báo của Gradle:

```text
healthy | status=UP | reason=SUFFICIENT_CAPACITY | freeMiB=250 | requiredMiB=100
low-capacity | status=DOWN | reason=LOW_CAPACITY | freeMiB=40 | requiredMiB=100
maintenance | status=OUT_OF_SERVICE | reason=MAINTENANCE | freeMiB=n/a | requiredMiB=n/a
invalid-observation | status=UNKNOWN | reason=INVALID_OBSERVATION | freeMiB=n/a | requiredMiB=n/a
withException.status=UP
withException.error=java.lang.IllegalStateException: probe failed
downException.status=DOWN
emptyBuilder.status=UNKNOWN
merged.retryCount=2
reuse.first.status=UP
reuse.first.attempt=2
reuse.second.status=DOWN
```

### 6.4. Đọc kết quả có giới hạn

**healthy:** có 250 MiB, yêu cầu 100 MiB, nên chính sách chọn UP và ghi SUFFICIENT_CAPACITY.

**low-capacity:** có 40 MiB, yêu cầu 100 MiB, nên chọn DOWN. Hai trường số cho phép người vận hành đối chiếu quyết định.

**maintenance:** chính sách ưu tiên bảo trì, chọn OUT_OF_SERVICE. `n/a` chỉ là cách chương trình console biểu diễn trường không có; mã không đưa chuỗi `n/a` vào đối tượng Health.

**invalid-observation:** số liệu âm không được xem là phép đo hợp lệ, nên chọn UNKNOWN. Ví dụ không coi nó như một quan sát bình thường rồi báo thiếu dung lượng.

Các dòng tiếp theo kiểm chứng những điểm độc lập: `withException` giữ nguyên trạng thái, Builder mặc định UNKNOWN, khóa trùng bị thay thế và nguy cơ sử dụng lại Builder.

## 7. Vì sao nên tạo Builder mới cho mỗi lần đánh giá?

Builder là đối tượng có trạng thái đang thay đổi. Một indicator thường được gọi nhiều lần, và các yêu cầu health có thể đến đồng thời. Đặt Builder trong field dùng chung làm dữ liệu của nhiều lần đánh giá có thể trộn lẫn.

Trong chương trình mục 6, mỗi lần gọi evaluate tạo một Builder cục bộ, đánh giá dữ liệu rồi trả kết quả ngay từ nhánh tương ứng. Không lưu Builder vào field dùng chung và không tiếp tục sửa nó sau khi đã trả Health.

### Giới hạn cần biết trong phiên bản thực hành

Javadoc mô tả Builder dùng để tạo `Health` bất biến. Tuy nhiên, ở triển khai Boot 3.3.0, map details trong kết quả được bọc bằng một view không cho sửa trực tiếp trên map của Builder, thay vì sao chép tách rời.

Vì vậy, sau khi tạo `first`, việc sửa `reused` trong ví dụ làm `first.getDetails().get("attempt")` đọc ra 2, dù `first` vẫn giữ trạng thái UP. Chương trình đã in rõ hành vi này.

Không diễn giải `build()` thành cam kết sao chép sâu mọi dữ liệu. Sau khi tạo kết quả, hãy ngừng sửa Builder và tránh đưa các đối tượng còn thay đổi vào details. Khi nâng phiên bản thư viện, kiểm tra lại nếu mã dựa vào một chi tiết triển khai như trên.

Đây cũng là lý do nên giữ Builder cục bộ trong một lần gọi, tạo dữ liệu chẩn đoán nhỏ và có giá trị ổn định, rồi trả kết quả ngay.

### Khi framework cấp Builder sẵn

Nếu dùng `AbstractHealthIndicator`, phương thức `doHealthCheck(Health.Builder builder)` nhận Builder do lớp cha cung cấp. Cập nhật Builder đó theo từng nhánh; lớp cha quản lý việc tạo kết quả. Không thay Builder được cấp bằng một Builder khác rồi bỏ quên kết quả.

Lớp cha cũng có cơ chế xử lý exception thành DOWN; điều này cần phù hợp với chính sách kiểm tra của ứng dụng. [AbstractHealthIndicator trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.html).

## 8. Tạo details và được phép xem details là hai việc khác nhau

Builder có thể tạo đủ thông tin trong `Health.getDetails()`, nhưng phản hồi HTTP còn phụ thuộc cấu hình hiển thị, nhóm health và quyền của người gọi.

Ví dụ cấu hình cho ứng dụng web đã có Actuator và cơ chế xác thực phù hợp:

```yaml
management:
  endpoint:
    health:
      show-components: when-authorized
      show-details: when-authorized
      roles:
        - ACTUATOR
```

Cấu hình này chưa tự tạo tài khoản hoặc gán vai trò. Cần phối hợp với cấu hình bảo mật của ứng dụng. [Thông tin health và quyền hiển thị trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Nếu một indicator được đăng ký dưới tên `archiveStore` và người gọi được phép xem, phần phản hồi của thành phần có thể như sau:

```json
{
  "status": "DOWN",
  "components": {
    "archiveStore": {
      "status": "DOWN",
      "details": {
        "target": "archive-store",
        "check": "write-capacity",
        "reasonCode": "LOW_CAPACITY",
        "freeMiB": 40,
        "requiredMiB": 100
      }
    }
  }
}
```

Đây là ví dụ phản hồi có thành phần và chi tiết được hiển thị, giả sử trạng thái tổng hợp là DOWN. Nó không phải stdout của chương trình console ở mục 6.

Ở endpoint gốc, chi tiết của một indicator thường nằm trong `components.<tên-thành-phần>.details`. Truy vấn trực tiếp một thành phần có cấu trúc khác. [Cấu trúc HTTP của health endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

Vì vậy, khi không thấy một detail trên HTTP, trước hết phân biệt: mã chưa tạo trường đó, trường nằm ở đường dẫn khác, hay chính sách hiển thị đang ẩn nó.

## 9. Giữ chi tiết hữu ích mà không công bố quá mức

Mục tiêu là đủ thông tin để xác định bước kiểm tra tiếp theo, không sao chép toàn bộ trạng thái nội bộ vào phản hồi.

### Nên ưu tiên

- Bí danh đích kiểm tra thay cho URL đầy đủ có thông tin xác thực.
- Mã nguyên nhân ổn định thay cho một thông điệp tùy ý khó so sánh.
- Giá trị quan sát và ngưỡng có cùng đơn vị.
- Thời gian đo có phạm vi rõ ràng.
- Thông tin về nguồn và độ mới của quan sát khi cần phân biệt dữ liệu mới với kết quả lưu tạm.

### Cần loại bỏ hoặc kiểm soát

- Mật khẩu, access token, khóa API và chuỗi kết nối chứa bí mật.
- Nội dung request, bản ghi nghiệp vụ hoặc dữ liệu người dùng.
- Toàn bộ stack trace và thông điệp lỗi chưa được chọn lọc.
- Đối tượng dịch vụ, entity hoặc cấu trúc lớn chỉ vì Builder chấp nhận kiểu Object.
- Số liệu không được quan sát nhưng được điền để phản hồi có vẻ đầy đủ.

Không nên mặc định rằng khóa có tên password hoặc token trong custom health sẽ tự được che. Hãy lựa chọn dữ liệu ngay khi xây dựng details và kiểm tra phản hồi dành cho từng nhóm người gọi.

## 10. Kiểm tra nội dung chẩn đoán theo từng nhánh

Với một phép kiểm tra thật, cần kiểm tra cả trạng thái lẫn nội dung giải thích.

| Nhánh | Điều cần xác nhận |
| --- | --- |
| Đạt điều kiện | UP đi cùng mã nguyên nhân và quan sát thực sự đạt ngưỡng |
| Không đạt điều kiện | DOWN đi cùng giá trị quan sát và điều kiện không đạt |
| Bảo trì | Trạng thái và nguyên nhân diễn đạt đúng chính sách bảo trì |
| Quan sát không hợp lệ | Không biến “chưa biết” thành số liệu hợp lệ hoặc một kết quả UP giả |
| Timeout | Mã nguyên nhân và giới hạn thời gian đúng với phép kiểm tra |
| Exception | Trạng thái được đặt đúng; dữ liệu lỗi công bố đã được kiểm soát |
| Gọi lại sau khi phục hồi | Không còn dữ liệu lỗi giữ lại từ lần gọi trước |
| Nhiều lời gọi đồng thời | Không dùng chung Builder hay dữ liệu chẩn đoán còn thay đổi |

Một kết quả tốt phải nhất quán nội bộ. Ví dụ DOWN với `reasonCode=SUFFICIENT_CAPACITY` hoặc UP nhưng chỉ chứa lỗi nghiêm trọng cần giải thích vì sao, thường là dấu hiệu một nhánh đã đổi trạng thái nhưng giữ details cũ.

Ngoài ra, phép kiểm tra phải có chi phí và giới hạn thời gian phù hợp. Ghi thêm `timeoutMillis` vào details không tự làm một thao tác mạng bị chặn kết thúc sau thời gian đó; cần cấu hình timeout ở chính thao tác hoặc client đang sử dụng.

## 11. Lỗi phổ biến và hướng sửa

| Lỗi | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Chỉ trả `Health.down().build()` cho mọi lỗi | Khó biết điều kiện nào không đạt | Thêm check, nguyên nhân và quan sát có giá trị |
| Chỉ gọi `withException(ex)` trên Builder UP | Có thể trả UP cùng error | Chọn trạng thái lỗi có chủ đích |
| Quên chọn trạng thái | Có thể trả UNKNOWN ngoài ý muốn | Kiểm tra mọi đường trả kết quả |
| Tưởng `withDetails` xóa sạch map cũ | Giữ lại thông tin từ nhánh khác | Tạo Builder mới và quản lý rõ khóa |
| Sử dụng lại Builder qua nhiều lần kiểm tra | Dữ liệu cũ hoặc dữ liệu trộn lẫn | Giữ Builder trong phạm vi một lần đánh giá |
| Dùng chuỗi “40” nhưng không nêu đơn vị | Khó diễn giải và xử lý tự động | Giữ kiểu số, ghi đơn vị vào tên trường |
| Trả message exception không kiểm soát | Có thể lộ thông tin nội bộ | Dùng mã nguyên nhân và log được kiểm soát |
| Bật show-details để “sửa” kết quả thiếu trường | Chưa chắc mã đã tạo trường đó | Kiểm tra Health trong mã trước, rồi kiểm tra quyền hiển thị |
| Định nghĩa trạng thái tùy chỉnh nhưng bỏ chính sách tổng hợp | Phản hồi tổng thể có thể không như mong muốn | Thiết kế thứ tự mức nghiêm trọng và ánh xạ HTTP |

## 12. Thực hành

Thay dữ liệu đầu vào trong chương trình mục 6, rồi dự đoán trạng thái và details trước khi chạy.

1. Dùng `freeMiB=100`, `requiredMiB=100`, không bảo trì. Kiểm tra điều kiện tại đúng ngưỡng.
2. Dùng `freeMiB=99`, `requiredMiB=100`. Xác nhận mã nguyên nhân và hai giá trị số.
3. Dùng `requiredMiB=0`. Giải thích vì sao ví dụ coi cấu hình này là quan sát không hợp lệ.
4. Bật bảo trì đồng thời đặt dung lượng âm. Xác định nhánh nào được ưu tiên theo thứ tự hiện tại.
5. Đổi nhánh lỗi sang chỉ gọi `withException` sau `Health.up()`. Quan sát trạng thái và giải thích vì sao đó có thể là kết quả sai chính sách.
6. Loại bỏ phần cố ý sử dụng lại Builder trong main; giữ cách tạo Builder cục bộ trong `evaluate`.
7. Thiết kế ba đến năm trường chẩn đoán cho một phép kiểm tra kết nối có timeout. Ghi rõ trường nào là quan sát, trường nào là cấu hình và trường nào là mã nguyên nhân.

Đối chiếu các trường hợp biên:

- Bài 1: UP với SUFFICIENT_CAPACITY vì ví dụ dùng điều kiện lớn hơn hoặc bằng.
- Bài 2: DOWN với LOW_CAPACITY, giữ số 99 và ngưỡng 100.
- Bài 3: UNKNOWN với INVALID_OBSERVATION theo hợp đồng của ví dụ.
- Bài 4: OUT_OF_SERVICE với MAINTENANCE vì nhánh bảo trì được xét trước.
- Bài 5: trạng thái có thể vẫn là UP nếu không có thao tác đổi trạng thái.

Khi hoàn thiện một kết quả Health, hãy đọc nó như người đang xử lý sự cố: có biết thành phần và phép kiểm tra không, có thể đối chiếu quyết định với quan sát không, và có biết giới hạn của kết luận không? Những câu hỏi đó giúp details trở thành dữ liệu chẩn đoán thay vì một tập trường được thêm cho đủ.
