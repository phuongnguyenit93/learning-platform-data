# Kiểm thử endpoint tùy chỉnh cho tham số hợp lệ, thiếu và sai kiểu

Giả sử endpoint Actuator `jobpreview` cho xem trước danh sách tác vụ, với `limit` là số mục tối đa cần lấy. `limit=2` là yêu cầu hợp lệ, `limit=abc` không chuyển được sang `Integer`, còn `limit=21` chuyển được nhưng vượt giới hạn của ví dụ. Hai đầu vào sau đều có thể trả `400`, song lỗi xảy ra ở hai chỗ khác nhau. Thiết kế ca kiểm thử theo từng chỗ giúp xác định khi nào Actuator từ chối trước khi gọi phương thức, và khi nào phương thức đã nhận giá trị rồi tự từ chối.

## Theo dõi giá trị từ yêu cầu đến phương thức

1. **Ánh xạ thao tác.** Spring Boot 3.3 tìm bean endpoint và công bố thao tác đọc `@ReadOperation` qua `GET` nếu endpoint được mở qua HTTP. Ví dụ dùng `@WebEndpoint(id = "jobpreview")` vì phản hồi có mã trạng thái HTTP riêng. Với tiền tố mặc định `/actuator`, đường dẫn là `/actuator/jobpreview`.
2. **Gắn tên và chuyển kiểu.** Actuator lấy giá trị truy vấn theo tên tham số Java, ở đây là `limit`, rồi chuyển sang kiểu đích. Java cần được biên dịch với `-parameters` để tên có mặt lúc chạy. Tham số của thao tác là bắt buộc theo mặc định, kể cả khi dùng kiểu bao `Integer`. Nếu yêu cầu thiếu tham số bắt buộc hoặc giá trị không chuyển được, Actuator trả `400 Bad Request` trước khi gọi phương thức.
3. **Kiểm tra ý nghĩa.** Sau khi nhận số nguyên, phương thức kiểm tra `limit` nằm trong đoạn từ 1 đến 20. Nó trả `400` kèm mã lỗi JSON nếu giá trị nằm ngoài khoảng. Với bộ chuyển đổi mặc định trong ví dụ, tham số có mặt nhưng giá trị là chuỗi rỗng được chuyển thành `null`. Phương thức xử lý trường hợp đó riêng trước khi so sánh số để tránh lỗi khi mở hộp `Integer`.

## Ma trận kiểm thử

Gửi tất cả yêu cầu tới cùng một thao tác `GET /actuator/jobpreview`.

| Đầu vào | Kết quả | Điểm cần xác nhận |
| --- | --- | --- |
| `limit=2` | `200`, JSON có `limit: 2` và hai tác vụ đầu tiên | Đúng đường dẫn, đúng tham số, chuyển kiểu thành công và lấy đúng dữ liệu. |
| `limit=1`, `limit=20` | `200` | Hai đầu mút của khoảng đều hợp lệ. Khi danh sách ngắn hơn giới hạn, trả tối đa số mục hiện có. |
| Bỏ hẳn `limit` | `400` | Thiếu tham số bắt buộc. |
| `limit=` | `400`, `error: "limit_empty"` | Tham số được gửi với giá trị rỗng. Ví dụ xử lý giá trị sau chuyển đổi bằng nhánh riêng. |
| `limit=abc`, `limit=2.5`, `limit=2147483648` | `400` | Chuỗi chữ, số có phần thập phân và số vượt giới hạn `Integer` đều bị từ chối khi chuyển kiểu. |
| `limit=0`, `limit=21` | `400`, `error: "limit_out_of_range"` | Cả hai đều là số nguyên hợp lệ về kiểu và bị từ chối bởi quy tắc của endpoint. |

## Ví dụ chạy được với Spring Boot 3.3 và MockMvc

Tạo một dự án Gradle riêng, chạy bằng JDK 17 trở lên với bản Gradle tương thích. Trong `settings.gradle`, đặt `rootProject.name = 'job-preview-endpoint-test'`. Dự án dùng plugin `java` và BOM của Spring Boot để chọn phiên bản thư viện, nên cấu hình `-parameters` một cách tường minh.

Tệp `build.gradle`

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tệp `src/main/java/demo/preview/PreviewApplication.java`

```java
package demo.preview;

import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PreviewApplication {

    @Bean
    JobPreviewEndpoint jobPreviewEndpoint() {
        return new JobPreviewEndpoint();
    }

    @WebEndpoint(id = "jobpreview")
    static class JobPreviewEndpoint {

        private static final List<String> JOBS = List.of("import", "archive", "refresh");

        @ReadOperation
        public WebEndpointResponse<Map<String, Object>> preview(Integer limit) {
            if (limit == null) {
                return new WebEndpointResponse<>(Map.of("error", "limit_empty"),
                        WebEndpointResponse.STATUS_BAD_REQUEST);
            }
            if (limit < 1 || limit > 20) {
                return new WebEndpointResponse<>(Map.of("error", "limit_out_of_range"),
                        WebEndpointResponse.STATUS_BAD_REQUEST);
            }
            return new WebEndpointResponse<>(Map.of(
                    "limit", limit,
                    "jobs", JOBS.subList(0, Math.min(limit, JOBS.size()))));
        }
    }
}
```

Tệp `src/test/java/demo/preview/JobPreviewEndpointTest.java`

```java
package demo.preview;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.contains;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = PreviewApplication.class,
        properties = "management.endpoints.web.exposure.include=jobpreview"
)
@AutoConfigureMockMvc
class JobPreviewEndpointTest {

    private static final String PATH = "/actuator/jobpreview";

    @Autowired
    MockMvc mvc;

    @Test
    void returnsAtMostTheRequestedNumberOfJobs() throws Exception {
        mvc.perform(get(PATH).param("limit", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.limit").value(2))
                .andExpect(jsonPath("$.jobs", contains("import", "archive")));
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 20})
    void acceptsBothBoundsOfTheBusinessRange(int limit) throws Exception {
        mvc.perform(get(PATH).param("limit", Integer.toString(limit)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.limit").value(limit));
    }

    @Test
    void rejectsMissingLimit() throws Exception {
        mvc.perform(get(PATH))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsAnExplicitlyEmptyLimit() throws Exception {
        mvc.perform(get(PATH).param("limit", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("limit_empty"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"abc", "2.5", "2147483648"})
    void rejectsValuesThatCannotBeConvertedToInteger(String raw) throws Exception {
        mvc.perform(get(PATH).param("limit", raw))
                .andExpect(status().isBadRequest());
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 21})
    void rejectsIntegersOutsideTheBusinessRange(int limit) throws Exception {
        mvc.perform(get(PATH).param("limit", Integer.toString(limit)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("limit_out_of_range"));
    }
}
```

Chạy từ thư mục dự án.

```bash
gradle test --tests demo.preview.JobPreviewEndpointTest
```

Kết quả kiểm chứng với Java 17, Spring Boot 3.3.0 và JUnit Platform là **10 ca đạt, 0 ca thất bại**. Mỗi giá trị của `@ValueSource` được chạy thành một ca riêng. Có thể xem báo cáo Gradle tại `build/reports/tests/test/index.html` sau khi chạy tác vụ trên.

`@SpringBootTest` nạp cấu hình Actuator, còn `@AutoConfigureMockMvc` gửi yêu cầu mô phỏng qua đường xử lý Spring MVC trong context đó. Nhờ vậy, bài kiểm tra được đường dẫn, chuyển kiểu và mã trạng thái của thao tác mà không cần mở cổng mạng. Việc gọi thẳng `preview(2)` chỉ kiểm tra xử lý sau khi đã có một `Integer`. Với yêu cầu xác minh cả cổng quản trị riêng hoặc cấu hình máy chủ, dùng thêm ca `RANDOM_PORT` gửi HTTP tới cổng thực.

## Đọc kết quả và mở rộng ca kiểm thử

- **Bắt đầu bằng ca hợp lệ.** Kiểm tra cả `200` và trường JSON thể hiện giá trị đã nhận. Nếu ca này ra `404`, kiểm tra endpoint đã được đăng ký thành bean, đã bật, đã mở qua HTTP và đúng tiền tố. Nếu thao tác bị chặn bởi xác thực hoặc phân quyền, cấu hình thông tin xác thực phù hợp cho ca kiểm tra tham số.
- **So sánh nội dung theo nguồn sinh lỗi.** Với lỗi chuyển kiểu hoặc thiếu tham số, hợp đồng Spring Boot trong bài là mã `400`. Với lỗi do ứng dụng định nghĩa, kiểm tra thêm `$.error` để phân biệt các nguyên nhân. Kiểm tra từng trường JSON giúp tránh phụ thuộc vào thứ tự khóa. Với thao tác ghi có tác dụng phụ, có thể kiểm tra trạng thái nghiệp vụ hoặc dùng đối tượng thay thế để xác nhận đầu vào bị từ chối trước khi cập nhật dữ liệu.
- **Tham số tùy chọn cần ca riêng.** Nếu hợp đồng cho phép bỏ `limit`, khai báo `@Nullable Integer limit` và xác định giá trị mặc định trong phương thức. Sau đó kiểm tra riêng ca bỏ tham số, ca chuỗi rỗng và ca sai kiểu. `@Nullable` cho phép thiếu giá trị, còn yêu cầu gửi một chuỗi không chuyển được vẫn là lỗi chuyển kiểu.
- **Với thao tác ghi, kiểm tra đúng dạng đầu vào.** `@WriteOperation` dùng `POST` và có thể lấy từng tham số đơn giản từ thuộc tính ở gốc JSON. Nếu hợp đồng yêu cầu JSON, đặt `Content-Type: application/json` và kiểm tra từng ca thiếu thuộc tính hoặc gửi giá trị không chuyển được. Một body JSON sai cú pháp là một ca riêng vì yêu cầu có thể bị từ chối ngay ở bước đọc body.

## Tài liệu đối chiếu

- [Spring Boot 3.3 · Khai báo endpoint, nhận tham số và mã phản hồi](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 · API WebEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html)
- [Spring Boot 3.3 · API WebEndpointResponse](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html)
- [Spring Boot 3.3 · Kiểm thử với môi trường web mô phỏng](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)