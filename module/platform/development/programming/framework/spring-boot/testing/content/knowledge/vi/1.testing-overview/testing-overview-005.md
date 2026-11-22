# Ứng dụng chạy được, Spring context khởi động được và nghiệp vụ đúng là ba bằng chứng khác nhau

Trong kiểm thử Spring Boot, ba câu “đã chạy được”, “test load context đã xanh” và “nghiệp vụ đã đúng” nói về **ba loại bằng chứng có phạm vi khác nhau**. Một bằng chứng có thể đúng trong khi hai bằng chứng còn lại chưa được kiểm chứng, thậm chí đã sai. Bài học này giúp đọc kết quả test chính xác và chọn phép kiểm thử phù hợp với rủi ro cần loại trừ.

## 1. Phân biệt ngay từ câu hỏi cần trả lời

| Bằng chứng | Câu hỏi thật sự được trả lời | Cách quan sát tiêu biểu | Điều chưa thể kết luận |
| --- | --- | --- | --- |
| **Ứng dụng chạy được** (runtime/smoke) | Tiến trình có khởi chạy và phục vụ được hành vi tối thiểu tại môi trường đang thử không? | Chạy JAR/ứng dụng, quan sát tiến trình và gọi một endpoint bằng HTTP | Mọi bean, tuyến xử lý, cấu hình ở môi trường khác hay quy tắc nghiệp vụ đều đúng |
| **ApplicationContext khởi động được** (context-loading) | Spring có dựng được tập bean và cấu hình của *test context* đang chọn không? | `@SpringBootTest`, nạp context và lấy bean bắt buộc | Endpoint đã tiếp nhận yêu cầu qua mạng, quy trình nghiệp vụ cho kết quả đúng, hay cấu hình production giống test |
| **Nghiệp vụ đúng** (behavior/correctness) | Với đầu vào và điều kiện đã chỉ rõ, kết quả và tác động có khớp quy tắc mong đợi không? | Assertion trên giá trị, lỗi, trạng thái dữ liệu và tương tác quan trọng; unit/integration/API test | Mọi nhánh đều đúng nếu chưa kiểm tra; riêng unit test cũng không xác nhận Spring wiring hay HTTP hoạt động |

Ba chiều có thể giao nhau: một HTTP integration test thực sự khởi động web server và gọi một endpoint có thể đem lại bằng chứng về cả khởi động lẫn hành vi **của chính kịch bản đó**. Tuy nhiên không vì thế mà suy rộng thành “toàn bộ hệ thống đúng”.

## 2. “Ứng dụng chạy được” phải gắn với dấu hiệu quan sát cụ thể

Cần phân biệt ba mức dễ bị gọi chung là “run được”:

1. **Biên dịch/đóng gói thành công:** `./gradlew classes` hoặc `./gradlew bootJar` chứng minh các bước build liên quan đã hoàn thành. Đây **chưa phải** bằng chứng tiến trình ứng dụng đã chạy. Lệnh `build` có thể chạy cả test, nhưng độ mạnh của kết luận vẫn phụ thuộc vào test có mặt và đã thực thi.
2. **Tiến trình khởi động:** `./gradlew bootRun` hoặc `java -jar ...` khởi chạy ứng dụng. Với ứng dụng web, log khởi động là một tín hiệu; cần kiểm tra thêm tiến trình còn sống và cổng đã nhận yêu cầu.
3. **Smoke check đầu cuối tối thiểu:** gọi một URL dự kiến, kiểm tra HTTP status và body. Điều này xác nhận đúng đường đi được gọi trong môi trường hiện tại; nó không thay thế test các quy tắc khác.

Ví dụ, `GET /api/prices/after-discount?original=100000&percent=20` trả `200` với body `80000` là bằng chứng endpoint và kịch bản giảm giá 20% đã hoạt động khi chạy. Một endpoint health báo `UP` (nếu dự án có Actuator và được cấu hình phù hợp) chỉ là tín hiệu sức khỏe theo những health indicator đang được bật, không tự chứng minh quy tắc tính giá đúng.

**Đặt câu hỏi đúng:** đã khởi chạy bằng cách nào, ở profile nào, cổng nào, có gọi yêu cầu thật không, và đã quan sát phản hồi gì? “Không thấy exception trong log” là bằng chứng yếu hơn “một request cụ thể cho response mong đợi”.

## 3. “Spring context khởi động được” chứng minh điều gì?

Spring Boot dùng `ApplicationContext` để đọc cấu hình, quét component, áp dụng auto-configuration và tạo/liên kết các bean. Kiểm thử khởi tạo context phát hiện nhiều lỗi như bean cần thiết không tồn tại, xung đột bean, circular dependency không thể giải quyết, property bắt buộc không có hoặc lỗi xảy ra trong quá trình khởi tạo. Lỗi cụ thể phụ thuộc cấu hình đang được nạp.

Một phép kiểm thử thường gặp là:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextStartsTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void requiredPriceServiceIsPresent() {
        assertNotNull(context.getBean(PriceService.class));
    }
}
```

Đây là **minh họa trích đoạn**; phần 5 có lớp hoàn chỉnh với đầy đủ import và dự án ví dụ. `webEnvironment = NONE` yêu cầu khởi động application context **không chạy HTTP server**. Nó phù hợp để kiểm tra wiring của ứng dụng, nhưng không thể chứng minh tuyến HTTP xử lý được request. `@SpringBootTest(webEnvironment = RANDOM_PORT)` còn khởi động embedded web server trên cổng ngẫu nhiên, phục vụ kiểm thử HTTP thật.

Cần ghi rõ phạm vi context:

- `@SpringBootTest` nạp context ứng dụng theo cấu hình test. Nếu dùng test profile, property override, fake server hay cơ sở dữ liệu test, kết quả chỉ trực tiếp đúng với các lựa chọn ấy.
- `@WebMvcTest` chỉ dựng một lát cắt MVC phục vụ controller test; một slice test thành công không tương đương toàn bộ application context thành công.
- `@MockBean` hoặc mock được chèn vào context có thể giúp cô lập thành phần, nhưng cũng có thể che đi lỗi tích hợp với dependency thật. Phải diễn giải bằng chứng theo wiring thật đang được test.
- Việc context nạp được không kiểm tra mọi nhánh logic: một service tính sai 20% thành 10% vẫn có thể được Spring tạo bean bình thường.

## 4. “Nghiệp vụ đúng” cần quy tắc rõ và assertion có ý nghĩa

Giả sử yêu cầu nghiệp vụ của một dịch vụ tính giá là: nhận `original` (số tiền nguyên, không âm) và `percent` (từ 0 đến 100), áp dụng giảm theo phần trăm; số tiền giảm được **làm tròn xuống đến đơn vị nguyên**, giá sau giảm không âm; tham số không hợp lệ phải bị từ chối.

Các tình huống cần kiểm tra gồm ca bình thường (100.000, 20% → 80.000), biên (0%, 100%, tiền bằng 0), làm tròn (99, 10% → 90 vì phần giảm là 9) và input sai (giá âm, phần trăm ngoài khoảng). Assertion phải so sánh với **giá trị độc lập rút ra từ yêu cầu**. Test chỉ gọi method rồi không báo lỗi, hoặc chỉ `assertNotNull(result)`, không đủ để chứng minh công thức đúng.

Unit test chạy trực tiếp lớp Java có thể chứng minh công thức mà không cần Spring context. Integration/API test có thể kiểm tra thêm controller mapping, xử lý HTTP, serialize dữ liệu và các thành phần liên quan. Với ứng dụng có DB, message broker hoặc transaction, cần test đúng thay đổi trạng thái/rollback và setup môi trường tương ứng; một unit test dùng mock không xác nhận tác dụng với DB thật.

## 5. Ví dụ Spring Boot hoàn chỉnh để tự đối chiếu ba loại bằng chứng

Các tệp sau là một ví dụ nhỏ chạy trên **Java 17+**, Spring Boot **3.3.x**, Gradle và JUnit Jupiter. Đặt chúng trong một dự án Spring Boot có Gradle Wrapper; ví dụ này không sử dụng DB, bảo mật hoặc API bên ngoài nên các phép kiểm thử minh họa được tách bạch.

Cấu trúc chính:

```text
settings.gradle
build.gradle
src/main/java/com/example/testing/TestingApplication.java
src/main/java/com/example/testing/PriceService.java
src/main/java/com/example/testing/PriceController.java
src/test/java/com/example/testing/PriceServiceTest.java
src/test/java/com/example/testing/ContextStartsTest.java
src/test/java/com/example/testing/PriceHttpTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'testing-evidence'
```

**`build.gradle`** (Groovy DSL, dành cho dự án ví dụ độc lập):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/testing/TestingApplication.java`**

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
```

**`src/main/java/com/example/testing/PriceService.java`**

```java
package com.example.testing;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public int afterDiscount(int original, int percent) {
        if (original < 0) {
            throw new IllegalArgumentException("original must be non-negative");
        }
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be between 0 and 100");
        }

        long discount = (long) original * percent / 100;
        return (int) (original - discount);
    }
}
```

Phép nhân chuyển sang `long` trước để tránh overflow của `int` ở bước tính phần trăm. Phép chia số nguyên làm tròn xuống phần giảm; kết quả cuối nằm trong khoảng `0..original` vì `percent` đã được kiểm tra.

**`src/main/java/com/example/testing/PriceController.java`**

```java
package com.example.testing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PriceController {
    private final PriceService service;

    public PriceController(PriceService service) {
        this.service = service;
    }

    @GetMapping("/api/prices/after-discount")
    public int afterDiscount(@RequestParam int original, @RequestParam int percent) {
        return service.afterDiscount(original, percent);
    }
}
```

Controller dùng constructor injection: nếu `PriceService` không được Spring đăng ký thành bean thì full context không thể tạo `PriceController`. Đường HTTP trả về một JSON number, chẳng hạn body `80000`. Mã mẫu cố ý chưa định nghĩa ánh xạ `IllegalArgumentException` thành HTTP 400; vì vậy không nên suy ra API đã xử lý đúng lỗi HTTP chỉ từ unit test về input sai.

### 5.1. Kiểm thử nghiệp vụ mà không cần Spring

**`src/test/java/com/example/testing/PriceServiceTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceServiceTest {
    private final PriceService service = new PriceService();

    @Test
    void appliesTwentyPercentDiscount() {
        assertEquals(80_000, service.afterDiscount(100_000, 20));
    }

    @Test
    void acceptsBoundaryPercentages() {
        assertEquals(100_000, service.afterDiscount(100_000, 0));
        assertEquals(0, service.afterDiscount(100_000, 100));
        assertEquals(0, service.afterDiscount(0, 40));
    }

    @Test
    void roundsDownTheDiscount() {
        assertEquals(90, service.afterDiscount(99, 10));
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> service.afterDiscount(-1, 20));
        assertThrows(IllegalArgumentException.class,
                () -> service.afterDiscount(100, -1));
        assertThrows(IllegalArgumentException.class,
                () -> service.afterDiscount(100, 101));
    }
}
```

Đây là **bằng chứng về quy tắc tính giá** trên những tình huống được assert. Nếu bỏ `@Service` khỏi `PriceService`, các unit test này vẫn có thể xanh vì chúng dùng `new PriceService()`; điều đó **không** chứng minh Spring tìm thấy bean.

### 5.2. Kiểm thử khởi động context, chưa gọi HTTP

**`src/test/java/com/example/testing/ContextStartsTest.java`**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextStartsTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void requiredPriceServiceIsPresent() {
        assertNotNull(context.getBean(PriceService.class));
    }
}
```

Test chỉ có thể chạy assertion khi Spring đã tạo xong context. Nếu controller yêu cầu một bean bị thiếu, phép kiểm thử có thể hỏng ngay tại bước khởi tạo trước khi vào test method. Nhưng nếu đổi công thức thành `return original;`, context vẫn có thể khởi động hoàn toàn bình thường: wiring đúng không đồng nghĩa kết quả nghiệp vụ đúng.

### 5.3. Kiểm thử HTTP với web server thật trong test

**`src/test/java/com/example/testing/PriceHttpTest.java`**

```java
package com.example.testing;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PriceHttpTest {
    @LocalServerPort
    private int port;

    @Test
    void returnsTheExpectedPriceThroughHttp() throws Exception {
        String url = "http://localhost:" + port
                + "/api/prices/after-discount?original=100000&percent=20";
        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("80000", response.body());
    }
}
```

Bài test này tự chạy embedded server trên cổng ngẫu nhiên, gửi request HTTP qua loopback, kiểm tra cả status và body. Nó chứng minh wiring web và hành vi **một** kịch bản đầu cuối trong test profile. Nó không thay thế kiểm thử biên, lỗi API, xác thực, tải cao hoặc kiểm thử cấu hình production.

### 5.4. Chạy và đọc bằng chứng

Trong dự án có Gradle Wrapper, dùng:

```bash
./gradlew test
./gradlew bootJar
./gradlew bootRun
```

Trên Windows, dùng `gradlew.bat test`, `gradlew.bat bootJar`, `gradlew.bat bootRun`. `test` chạy các JUnit test (nếu được cấu hình/không bị loại trừ); `bootJar` đóng gói JAR; `bootRun` khởi chạy ứng dụng. Để thử JAR đã đóng gói riêng, chạy `java -jar build/libs/testing-evidence-0.0.1-SNAPSHOT.jar` khi JAR đó tồn tại. Không lấy thành công của `bootJar` làm bằng chứng JAR đã chạy.

Sau khi app web khởi động (cổng mặc định 8080 nếu không bị thay đổi), ở terminal khác gọi:

```bash
curl -i "http://localhost:8080/api/prices/after-discount?original=100000&percent=20"
```

Phản hồi mong đợi có **HTTP status 200** và **response body `80000`**; các HTTP header thực tế có thể khác theo môi trường. Nếu ứng dụng dùng cổng/profile khác, sửa URL tương ứng. Lệnh `curl` là bước smoke/integration thủ công; chạy test tự động không tự thực hiện thao tác này với bản JAR vừa đóng gói.

Có thể chạy riêng từng tầng để biết lỗi nằm ở đâu:

```bash
./gradlew test --tests com.example.testing.PriceServiceTest
./gradlew test --tests com.example.testing.ContextStartsTest
./gradlew test --tests com.example.testing.PriceHttpTest
```

## 6. Tình huống phản chứng: vì sao không thể suy diễn chéo?

| Tình huống | Quan sát có thể xảy ra | Kết luận đúng |
| --- | --- | --- |
| Bỏ `@Service` khỏi `PriceService` | Unit test dùng `new` vẫn xanh; context test và HTTP test thất bại khi Spring không tạo được `PriceController` | Logic đã được test độc lập, nhưng wiring ứng dụng lỗi |
| Đổi phép tính để luôn trả `original` | Context vẫn tạo bean và có thể khởi động web server; unit test 20% và HTTP test body thất bại | Startup được nhưng hành vi tính giá sai |
| Chỉ gọi endpoint health | Server trả tín hiệu healthy | Chưa kiểm tra kết quả `afterDiscount` |
| Chỉ chạy `bootJar` | Tệp JAR được tạo | Chưa có chứng cứ runtime hoặc correctness; cần chạy và test |
| Context test dùng cấu hình giả lập | Context test xanh với mock/test database | Chưa chứng minh kết nối hay hoạt động ở cấu hình thật |
| HTTP test chỉ kiểm tra status 200 | Controller trả 200 dù giá tính sai | Phải assert thêm body/dữ liệu/tác động có nghĩa |

Một test xanh là một mệnh đề có điều kiện: **với thiết lập, input và assertion đã dùng, hành vi được quan sát khớp kỳ vọng**. Không có test nào tự xác nhận mọi trạng thái chưa được quan sát.

## 7. Chiến lược áp dụng khi phát triển và CI

1. **Bắt đầu từ rủi ro nghiệp vụ:** viết unit test nhanh cho quy tắc, điều kiện biên và lỗi đầu vào; đặt tên test theo hành vi.
2. **Xác nhận wiring cần thiết:** dùng context-loading test đủ rộng để phát hiện lỗi khai báo bean/configuration, nhớ profile và dependency được thay thế trong test.
3. **Đi theo một luồng thực:** dùng HTTP integration test để xác nhận entry point, serialization và kết quả nhìn thấy từ ngoài. Với DB hoặc broker, dùng môi trường test thích hợp và assert cả trạng thái sau thao tác.
4. **Xác nhận bản chạy đã đóng gói khi phát hành:** ngoài test suite, khởi chạy artifact/cấu hình dự kiến và smoke check endpoint hoặc readiness trong môi trường phù hợp.
5. **Đọc log và báo cáo theo phép kiểm đã chạy:** phân biệt lỗi compile/build, context initialization, network/HTTP và assertion nghiệp vụ; ghi rõ đầu vào, môi trường và kỳ vọng trước khi kết luận.

**Checklist diễn giải kết quả:** Có tiến trình thật không? Context nào đã nạp và với profile nào? Có request hay phép gọi method nào được thực thi? Assertion đã kiểm tra giá trị/tác động nào? Các biên và đường lỗi quan trọng đã được phủ chưa? Đó là cách biến dòng “BUILD SUCCESSFUL” hoặc “test xanh” thành bằng chứng kỹ thuật có ý nghĩa.

Kết luận cần giữ nguyên: **chạy được** cho thấy một dạng khả dụng vận hành; **context khởi động được** cho thấy một cấu hình Spring có thể được dựng; **nghiệp vụ đúng** chỉ được hỗ trợ bởi những phép so sánh hành vi cụ thể. Muốn tin cậy vào hệ thống, thu thập cả ba loại bằng chứng ở đúng phạm vi rủi ro.
