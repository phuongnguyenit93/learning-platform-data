# Phân biệt kiểm thử chức năng, hợp đồng, bảo mật và hiệu năng trong Spring Boot

## 1. Bốn loại kiểm thử trả lời bốn câu hỏi khác nhau

Khi một API Spring Boot trả về HTTP 200, điều đó chưa đủ để kết luận hệ thống hoạt động đúng. API có thể trả sai số tiền, thay đổi cấu trúc JSON khiến ứng dụng khác bị lỗi, tiết lộ dữ liệu cho người không có quyền hoặc phản hồi quá chậm dưới tải. Bốn hướng kiểm thử giải quyết bốn rủi ro tương ứng:

- **Kiểm thử chức năng (functional testing):** Hệ thống có thực hiện đúng quy tắc nghiệp vụ và kết quả mong đợi với các đầu vào, trạng thái cụ thể không?
- **Kiểm thử hợp đồng (contract testing):** Các bên giao tiếp có tuân thủ giao diện đã cam kết, chẳng hạn phương thức HTTP, đường dẫn, trường dữ liệu, kiểu dữ liệu, mã trạng thái và cách xử lý lỗi không?
- **Kiểm thử bảo mật (security testing):** Hệ thống có xác thực, phân quyền, bảo vệ dữ liệu và chống những cách truy cập hoặc đầu vào không hợp lệ không?
- **Kiểm thử hiệu năng (performance testing):** Với tải, dữ liệu và môi trường xác định, hệ thống có đạt mục tiêu thời gian đáp ứng, thông lượng, tỷ lệ lỗi và sử dụng tài nguyên không?

Chúng bổ sung cho nhau; cùng một endpoint có thể cần cả bốn. Phân loại theo **rủi ro và điều khẳng định**, không chỉ theo tên công cụ hoặc cấp độ kiểm thử.

| Khía cạnh | Chức năng | Hợp đồng | Bảo mật | Hiệu năng |
|---|---|---|---|---|
| Câu hỏi cốt lõi | Kết quả nghiệp vụ đúng chứ? | Bên gọi và bên cung cấp có hiểu đúng giao diện chứ? | Ai được phép làm gì, dữ liệu có an toàn chứ? | Hệ thống đáp ứng thế nào dưới tải? |
| Đối tượng xác nhận | Quy tắc, nhánh xử lý, trạng thái, dữ liệu | Request/response, schema, status, khả năng tương thích | Authentication, authorization, dữ liệu nhạy cảm, lỗ hổng, cấu hình | Độ trễ, throughput, lỗi, CPU, bộ nhớ, connection pool |
| Ví dụ lỗi | Tổng tiền bị tính sai | Đổi tên trường amountVnd thành amount | Người dùng xem được đơn của người khác | p95 tăng từ 200 ms lên 3 s khi số người dùng tăng |
| Công cụ thường dùng trong Java/Spring | JUnit 5, AssertJ, MockMvc, Testcontainers | OpenAPI validation/diff, Pact, Spring Cloud Contract | Spring Security Test, OWASP ZAP, SAST/SCA, kiểm thử xâm nhập được cấp phép | k6, Gatling, JMeter, Micrometer/Prometheus |
| Kết quả nên đánh giá | Assertions của nghiệp vụ đúng | Contract đã công bố được xác minh cho các bên sử dụng | Không có đường truy cập trái phép; các kiểm soát hoạt động | Đạt SLO theo kịch bản tải đã định nghĩa |

**Ví dụ xuyên suốt:** GET /api/orders/42 phải trả JSON gồm id, status, amountVnd cho người có quyền VIEWER. Đơn 42 đã thanh toán, số tiền là 120000 VND. Một bài kiểm thử chức năng so giá trị; kiểm thử hợp đồng xác nhận hình dạng thông điệp; kiểm thử bảo mật xác nhận người không đủ quyền bị từ chối; kiểm thử hiệu năng đo phản hồi khi nhiều yêu cầu đồng thời. Chỉ kiểm tra HTTP 200 không chứng minh ba điều còn lại.

## 2. Kiểm thử chức năng: đúng nghiệp vụ

**Mục tiêu:** Đối chiếu hành vi thực tế với yêu cầu: đầu vào hợp lệ, biên, đầu vào sai, trạng thái thiếu dữ liệu, đường lỗi và quy tắc chuyển trạng thái.

Với GET /api/orders/{id}, các trường hợp cần nghĩ đến gồm:
1. ID tồn tại: HTTP 200, id đúng, status và amountVnd đúng với dữ liệu nguồn.
2. ID không tồn tại: HTTP 404; không trả nhầm đơn khác.
3. Tham số không hợp lệ: ứng dụng từ chối theo hợp đồng đầu vào thay vì phát sinh lỗi 500 không kiểm soát.
4. Có thay đổi trạng thái nghiệp vụ: giá trị trả về phản ánh đúng trạng thái sau thao tác cập nhật, nếu API có hỗ trợ.

**Cấp độ kiểm thử không đồng nghĩa với loại kiểm thử.** Unit test kiểm tra hàm hoặc service cô lập, web slice test kiểm tra controller và HTTP mapping, integration test kiểm tra kết nối database/queue/hạ tầng thật hoặc Testcontainers, còn end-to-end test đi qua một luồng nghiệp vụ. Cả bốn cấp độ đều có thể kiểm thử chức năng. Chọn cấp độ thấp nhất vẫn chứng minh được rủi ro; bổ sung kiểm thử tích hợp cho hành vi phụ thuộc transaction, serialization, mapping, cấu hình hoặc truy vấn thực.

Độ tin cậy đến từ assertion có ý nghĩa. Chỉ assert “không ném exception” hoặc “HTTP 200” thường bỏ sót lỗi tính toán. Với API trả đơn hàng, phải kiểm tra chính xác trường nghiệp vụ quan trọng, đầu vào biên và lỗi mong đợi.

## 3. Kiểm thử hợp đồng: đúng giao diện giữa các thành phần

**Hợp đồng (contract)** là quy ước mà bên cung cấp (provider) và bên sử dụng (consumer) dựa vào để trao đổi. Nó có thể gồm:
- Đường dẫn, HTTP method, query/path/header bắt buộc, định dạng body.
- HTTP status, Content-Type, JSON schema: tên trường, kiểu, required/optional, ràng buộc giá trị.
- Cấu trúc lỗi, cách phân trang, chuẩn ngày giờ, quy tắc tương thích phiên bản.
- Với message/event: tên topic, schema, key, trường bắt buộc và cách diễn giải sự kiện.

Ví dụ một phần OpenAPI mô tả hình dạng response; đây là **tài liệu hợp đồng**, chưa phải bài kiểm thử tự động:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders/{id}:
    get:
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                type: object
                required: [id, status, amountVnd]
                properties:
                  id: { type: integer, format: int64 }
                  status: { type: string }
                  amountVnd: { type: integer, format: int64 }
        '404':
          description: Order not found
~~~

Hai chiến lược phổ biến:

**Schema/API contract:** Provider phát hành OpenAPI hoặc schema; CI so sánh mô tả với endpoint chạy thật, kiểm tra request/response, đồng thời phát hiện thay đổi phá vỡ tương thích (breaking change). Một assertion JSONPath kiểm tra trường có tồn tại mới là bước kiểm tra hình dạng cơ bản; nó **không tự động là xác minh đầy đủ OpenAPI**.

**Consumer-driven contract (CDC):** Consumer mô tả các tương tác mình thực sự cần, ví dụ “gọi GET với ID hợp lệ, nhận HTTP 200 và các trường id/status/amountVnd đúng kiểu”. Hợp đồng được chia sẻ; provider chạy verification với những hợp đồng của các consumer hiện có (ví dụ qua Pact hoặc Spring Cloud Contract). Cách này phát hiện sớm thay đổi khiến consumer đang sử dụng API bị vỡ mà không cần dựng toàn bộ hệ thống end-to-end trong mỗi lần chạy.

**Các thay đổi cần đánh giá:** Xóa/đổi tên trường required, đổi kiểu số sang chuỗi, đổi mã trạng thái hoặc biến tham số request tùy chọn thành bắt buộc thường là breaking change. Thêm trường response tùy chọn thường tương thích với consumer có khả năng bỏ qua trường lạ, nhưng không nên giả định mọi consumer đều như vậy. Thêm giá trị enum cũng có thể phá code consumer xử lý danh sách cố định. Kiểm thử hợp đồng nhằm phát hiện tương thích giao tiếp; nó không chứng minh số tiền tính đúng theo nghiệp vụ.

## 4. Kiểm thử bảo mật: đúng quyền và kiểm soát tấn công

Phân biệt ba lớp:
- **Authentication:** Yêu cầu đến từ ai, đã chứng thực danh tính chưa? Với một API chỉ chấp nhận Basic/Bearer, request chưa đăng nhập thường nhận 401.
- **Authorization:** Danh tính đó có được phép thực hiện hành động trên **tài nguyên cụ thể** không? Đã đăng nhập nhưng thiếu quyền thường nhận 403.
- **Bảo vệ dữ liệu và bề mặt tấn công:** Kiểm soát dữ liệu đầu vào/đầu ra, lỗi rò rỉ thông tin, IDOR/BOLA, SQL injection, XSS, CSRF khi phù hợp với mô hình xác thực, cấu hình CORS, bí mật, TLS và thư viện phụ thuộc.

Ví dụ: quyền VIEWER cho phép truy cập một số đơn hàng theo phạm vi được cấp. Test chỉ kiểm tra role VIEWER **chưa đủ** nếu ứng dụng có nhiều tenant: một VIEWER của tenant A phải không được xem đơn của tenant B. Đây là lỗi phân quyền mức đối tượng, kể cả khi request qua xác thực và trả HTTP 200.

Nên kết hợp nhiều cách: test bảo mật bằng Spring Security Test (401/403, rule truy cập, CSRF trên phương thức ghi nếu dùng cookie/session), integration test qua filter chain và cơ chế token/session thật, SAST/SCA trong pipeline, DAST có phạm vi được phê duyệt, kiểm tra cấu hình và kiểm thử xâm nhập chuyên sâu khi cần. **@WithMockUser mô phỏng người dùng trong SecurityContext**: rất hữu ích để kiểm tra phân quyền, nhưng không xác minh việc phát hành, chữ ký, hết hạn hay thu hồi JWT hoặc chu trình đăng nhập thật.

Không kết luận API an toàn chỉ từ một test 401/403. Bảo mật bao gồm nhiều lớp, phụ thuộc threat model và bối cảnh triển khai.

## 5. Kiểm thử hiệu năng: đúng mức dịch vụ trong điều kiện xác định

Một request phản hồi trong 100 ms trên máy lập trình không nói lên hiệu năng khi hàng trăm người cùng dùng. Performance test phải xác định **workload** (tần suất, số người dùng ảo, pha tăng tải, tỷ lệ endpoint, kích thước dữ liệu, tỷ lệ đọc/ghi), **môi trường** (CPU, RAM, database, cache, mạng), **ngưỡng** và **cách quan sát**.

Chỉ số quan trọng:
- **Latency:** p50 mô tả trung vị, p95/p99 phản ánh phần đuôi chậm; trung bình có thể che những request rất chậm.
- **Throughput:** requests/second hoặc giao dịch/giây thực tế, không đồng nghĩa với số virtual users (VUs).
- **Error rate:** 5xx, timeout, lỗi nghiệp vụ theo định nghĩa, thất bại kết nối; phân biệt lỗi do script/auth với lỗi backend.
- **Saturation:** CPU, heap/GC, threads, database connection pool, queue lag, I/O; tìm điểm nghẽn khi tải tăng.

Các kiểu bài thử:
- **Load test:** Đo ở mức tải sử dụng dự kiến.
- **Stress test:** Tăng vượt mức dự kiến để tìm giới hạn và quan sát cách suy giảm/khôi phục.
- **Spike test:** Tăng hoặc giảm tải đột ngột.
- **Soak/endurance test:** Chạy tải duy trì để nhận diện rò rỉ tài nguyên hoặc tích tụ độ trễ.

Ngưỡng ví dụ: tại workload đã mô tả, p95 dưới 300 ms và tỷ lệ request thất bại dưới 1%. Đây chỉ là **tiêu chí minh họa**; SLO thực tế phải xuất phát từ mục tiêu sản phẩm và đường cơ sở đo được. Đo sau giai đoạn warm-up phù hợp, giữ dữ liệu và hạ tầng đủ nhất quán để so sánh, lặp chạy khi cần và kết hợp metric/tracing để tìm nguyên nhân. Kết quả đo trên máy đơn lẻ không đại diện cho môi trường sản xuất.

## 6. Ví dụ Spring Boot 3.3.x / Java 17+: ba góc nhìn trên một API

Ví dụ nhỏ này có thể chạy bằng Maven và Java 17 trở lên. Dữ liệu đơn hàng được cố định để minh họa assertion; trong hệ thống thật hãy thay bằng service/repository và dùng integration test cho truy cập dữ liệu. Tạo cấu trúc:

~~~text
pom.xml
src/main/java/demo/testing/TestingApplication.java
src/test/java/demo/testing/OrderApiTest.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>testing-example</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
~~~

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/orders")
class OrderController {
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> getOrder(@PathVariable long id) {
        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }
        Map<String, Object> order = new LinkedHashMap<>();
        order.put("id", 42L);
        order.put("status", "PAID");
        order.put("amountVnd", 120_000L);
        return ResponseEntity.ok(order);
    }
}

@Configuration
class ApiSecurity {
    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**").hasRole("VIEWER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình trên dùng Spring Security 6, chỉ cho role VIEWER vào /api/orders/** và mở HTTP Basic để request chưa xác thực nhận thử thách 401. Mã ví dụ không có logic đa tenant hoặc database; vì thế nó không chứng minh bảo mật mức đối tượng hay độ đúng của phép tính đơn hàng thực tế. CSRF vẫn theo mặc định của Spring Security; endpoint GET là thao tác đọc.

**src/test/java/demo/testing/OrderApiTest.java**

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "VIEWER")
    void functional_returnsCorrectBusinessValues() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("PAID"))
            .andExpect(jsonPath("$.amountVnd").value(120000));
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void functional_unknownIdReturns404() throws Exception {
        mvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void contract_responseHasExpectedShape() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").isNumber())
            .andExpect(jsonPath("$.status").isString())
            .andExpect(jsonPath("$.amountVnd").isNumber());
    }

    @Test
    void security_missingAuthenticationReturns401() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "GUEST")
    void security_wrongRoleReturns403() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn test
~~~

**Cách đọc kết quả:** Hai test functional kiểm tra giá trị và nhánh 404. Test contract_responseHasExpectedShape chỉ kiểm tra cấu trúc response của provider ở mức cơ bản; muốn gọi là kiểm thử hợp đồng đầy đủ, cần xác minh endpoint với OpenAPI/schema hoặc Pact/contract của consumer trong CI. Hai test security xác nhận luồng 401/403 qua filter chain với MockMvc, nhưng @WithMockUser không thử HTTP Basic credentials thật. Các test này không đo hiệu năng.

Để nâng cấp bài kiểm tra, thêm test với dữ liệu đơn hàng thật trong database riêng (ví dụ Testcontainers), test endpoint bằng credential/token thử nghiệm thật, kiểm thử IDOR nếu có quan hệ sở hữu đơn và bước verify OpenAPI hoặc CDC. Tránh dùng dữ liệu khách hàng hoặc secret sản xuất trong fixture.

## 7. Ví dụ đo tải bằng k6

Đây là script **độc lập với Maven/JUnit**, chạy bằng công cụ k6 đã cài đặt. Nó đo GET /api/orders/42 ở 20 virtual users trong 30 giây; không chứng minh thông lượng cố định vì VUs và requests/second khác nhau.

**perf-orders.js**

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
    vus: 20,
    duration: '30s',
    thresholds: {
        http_req_failed: ['rate<0.01'],
        http_req_duration: ['p(95)<300'],
    },
};

export default function () {
    const baseUrl = __ENV.BASE_URL || 'http://localhost:8080';
    const headers = __ENV.AUTH_HEADER
        ? { Authorization: __ENV.AUTH_HEADER }
        : {};
    const response = http.get(baseUrl + '/api/orders/42', { headers });
    check(response, { 'HTTP 200': r => r.status === 200 });
}
~~~

~~~bash
k6 run perf-orders.js
~~~

**Điều kiện chạy:** Ứng dụng phải đang chạy, BASE_URL trỏ đến đúng môi trường thử nghiệm và AUTH_HEADER được thiết lập bằng credential thử nghiệm hợp lệ cho quyền VIEWER (với cấu hình ví dụ là header Basic). Không lưu mật khẩu/token vào file script hoặc log. Nếu thiếu thông tin xác thực, request sẽ nhận 401 và bài đo thất bại do thiết lập test; không được kết luận server có lỗi hiệu năng từ kết quả đó.

Ngưỡng p95 dưới 300 ms và failed request dưới 1% chỉ là minh họa. Với hệ thống thật cần mô hình tải sát sử dụng (tỷ lệ đọc/ghi, kích thước dữ liệu, caching, warm-up, thời gian đo, tỷ lệ arrival), môi trường tương ứng, SLO và phân tích CPU/DB/GC cùng kết quả k6. Script này không bao gồm stress/spike/soak; mỗi mục tiêu cần kịch bản riêng.

## 8. Chọn kiểm thử và cổng chất lượng trong CI/CD

| Thời điểm | Kiểm thử ưu tiên | Điều kiện qua cổng (ví dụ) |
|---|---|---|
| Lúc sửa logic nghiệp vụ, mỗi pull request | Unit/web/integration functional | Các quy tắc và nhánh lỗi quan trọng có assertion, toàn bộ test phải pass |
| Khi API/event thay đổi, mỗi pull request | OpenAPI/schema diff và provider/consumer contract verification | Không phá consumer hiện hành; breaking change được xử lý qua version/migration có chủ đích |
| Mỗi pull request và định kỳ | Security unit/integration, dependency scan, secret scan; DAST theo môi trường phù hợp | Không xuất hiện truy cập trái phép hoặc phát hiện nghiêm trọng chưa xử lý theo chính sách |
| Trước release và khi có thay đổi tải/hạ tầng | Load test với dữ liệu và môi trường đủ đại diện | Đạt p95/p99, error rate, throughput, saturation theo SLO đã ghi rõ |
| Theo lịch và khi điều tra sự cố | Soak, stress, spike, security chuyên sâu | Biết điểm giới hạn, hành vi khôi phục, rò rỉ tài nguyên và các rủi ro mới |

Tách test nhanh, ổn định khỏi bài thử tốn thời gian. Không nên chạy load test dài trên cùng môi trường chia sẻ đang bị nhiều pipeline khác tác động rồi coi kết quả là chuẩn. Contract verification có thể chạy rất nhanh trong PR; DAST và performance thường cần môi trường riêng. Hạn chế test giả định vào dữ liệu thay đổi ngẫu nhiên, phụ thuộc thời gian thực hoặc dịch vụ bên ngoài không kiểm soát.

## 9. Những nhầm lẫn thường gặp

1. **“Trả HTTP 200 nên đúng.”** 200 chỉ là tín hiệu HTTP; body có thể sai nghiệp vụ, không theo contract hoặc phản hồi quá chậm.
2. **“Functional test và contract test là một.”** Một response có thể đúng schema nhưng sai amountVnd; ngược lại kết quả nghiệp vụ đúng với test hiện tại vẫn có thể đổi field làm client cũ bị vỡ.
3. **“Unit test là functional; integration test là contract.”** Unit/integration/end-to-end mô tả phạm vi thực thi, còn functional/contract/security/performance mô tả điều được kiểm chứng.
4. **“Có @WithMockUser là đã bảo mật toàn diện.”** Nó hỗ trợ kiểm tra authorization rule; vẫn cần thử authentication thật, object-level authorization, lỗi cấu hình và các lớp phòng vệ khác.
5. **“20 VUs tức là 20 request/giây.”** VUs mô phỏng người dùng lặp giao dịch; tốc độ phụ thuộc response time và think time. Muốn kiểm soát arrival rate phải dùng mô hình tương ứng.
6. **“p95 tốt thì mọi request đều nhanh.”** Vẫn còn 5% request chậm hơn ngưỡng p95; cần xem p99, timeout, lỗi và tác động đến người dùng.
7. **“Kết quả benchmark máy local đại diện production.”** Hệ thống thật khác về mạng, pool kết nối, dữ liệu, dependency, autoscaling và tải đồng thời; cần định nghĩa điều kiện đo rõ ràng.
8. **“Kiểm thử hợp đồng thay thế hết end-to-end.”** Contract giảm nguy cơ lệch giao diện; không đảm bảo workflow nhiều dịch vụ, dữ liệu hoặc cấu hình vận hành kết hợp đúng.

## 10. Cách tự chọn loại kiểm thử từ một yêu cầu

Với thay đổi “API xem đơn hàng”:
- Nếu mục tiêu là đơn đã thanh toán phải trả **amountVnd = 120000** → viết **functional test** cho dữ liệu và nghiệp vụ.
- Nếu mục tiêu là ứng dụng di động vẫn nhận được **id/status/amountVnd đúng schema và status** → viết **contract test**, tốt nhất verify hợp đồng consumer đang dùng.
- Nếu mục tiêu là chỉ người có quyền và đúng phạm vi sở hữu mới xem được đơn → viết **security test** cho 401, 403 và truy cập chéo tenant/owner.
- Nếu mục tiêu là p95 dưới ngưỡng đã thống nhất ở tải phục vụ thực tế → viết **performance test** với workload, môi trường và metric xác định.

**Nguyên tắc áp dụng:** Bắt đầu từ rủi ro cần chứng minh, viết assertion/metric tương ứng, chọn cấp độ và công cụ vừa đủ, rồi kết hợp các loại kiểm thử để giảm những khoảng trống mà từng loại riêng lẻ không bao phủ.