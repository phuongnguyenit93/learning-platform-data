# Tính độc lập, lặp lại được và phản hồi nhanh của bộ kiểm thử

> Phạm vi: xây dựng và vận hành bộ kiểm thử cho ứng dụng Spring Boot sao cho mỗi phép thử đáng tin, kết quả ổn định giữa các lần chạy và lỗi được phát hiện đủ sớm để lập trình viên sửa ngay trong vòng phản hồi ngắn.

## 1. Ba thuộc tính cần đạt và cách nhận biết

Một bộ kiểm thử tốt phải trả lời được ba câu hỏi:

1. **Độc lập (independence):** Chạy riêng một test, chạy cả lớp, đổi thứ tự chạy hoặc chạy ở máy khác có giữ nguyên kết quả không? Test A không được cần “test B đã tạo dữ liệu” hoặc để lại trạng thái khiến test C hỏng.
2. **Lặp lại được (repeatability/determinism):** Khi mã và đầu vào không đổi, một test có cho cùng kết quả qua nhiều lần chạy không? Kết quả không nên phụ thuộc giờ thực, dữ liệu còn sót, seed ngẫu nhiên, tốc độ máy hay dịch vụ mạng bất thường.
3. **Phản hồi nhanh (fast feedback):** Khi vừa đưa lỗi vào mã, người viết nhận tín hiệu thất bại đúng chỗ trong thời gian đủ ngắn để sửa dễ dàng không? Test nhanh nhưng báo sai, hoặc báo lỗi quá mơ hồ, đều tạo phản hồi kém.

Ba thuộc tính liên quan nhau: tách phụ thuộc giúp chạy song song an toàn; đầu vào ổn định làm thất bại đáng tin; chia đúng tầng giúp chạy phần rẻ trước. Tuy nhiên, **nhanh không biện minh cho test thiếu kiểm chứng**, và “100% xanh” không có nghĩa là độc lập nếu kết quả phụ thuộc thứ tự.

| Thuộc tính | Dấu hiệu đạt | Dấu hiệu cảnh báo |
|---|---|---|
| Độc lập | Mỗi test tự tạo tiền điều kiện, tự xử lý tài nguyên; chạy lẻ vẫn đạt | Chỉ đạt khi chạy toàn bộ suite; dùng dữ liệu do test khác tạo |
| Lặp lại được | Cùng mã và cấu hình cho cùng kỳ vọng; thất bại tái hiện được | Lúc xanh lúc đỏ; chạy lại thì “tự khỏi” |
| Phản hồi nhanh | Unit test chạy rất nhanh; thay đổi nhỏ nhận lỗi rõ và sớm | Mọi kiểm thử đều khởi động Spring context, DB và mạng; CI chậm |

## 2. Độc lập: mỗi test là một thí nghiệm hoàn chỉnh

Mẫu tư duy **Arrange – Act – Assert**:

- **Arrange:** Tự chuẩn bị tất cả đầu vào và trạng thái mà phép thử cần.
- **Act:** Gọi một hành vi cụ thể của hệ thống.
- **Assert:** Kiểm tra kết quả quan sát được và tác động phụ có liên quan.

Một test nên không phụ thuộc *chạy trước*, *chạy sau* hoặc *chạy cùng* test khác. Trong JUnit Jupiter, thứ tự mặc định có tính xác định nhưng không hiển nhiên; nó không phải hợp đồng để ghép các phép thử thành kịch bản theo thứ tự. Nếu quy trình nghiệp vụ thực sự gồm nhiều bước liên tiếp, thường nên kiểm thử cả quy trình trong **một** test tích hợp có các bước Arrange/Act/Assert rõ ràng.

### 2.1. Các nguồn chia sẻ trạng thái thường gặp

- **Biến `static`, singleton, cache, collection dùng chung:** một test thêm dữ liệu rồi test khác đọc thấy. Ưu tiên khởi tạo đối tượng mới trong từng test; nếu cần test Spring bean có trạng thái, reset đúng trạng thái hoặc thiết kế lại bean.
- **Cơ sở dữ liệu:** bản ghi của test trước còn tồn tại; ID tự tăng hoặc bản ghi thứ tự ngẫu nhiên làm assert sai. Dùng fixture độc lập, khóa nhận dạng riêng, rollback khi phù hợp, hoặc cleanup có kiểm chứng.
- **File, thư mục, cổng mạng, message queue, cache Redis:** test tranh tên tài nguyên hoặc để dữ liệu rác. Cấp namespace riêng và đóng tài nguyên sau khi dùng; ưu tiên thư mục tạm của JUnit cho file.
- **Thay đổi cấu hình toàn cục:** timezone JVM, locale mặc định, system properties, clock toàn cục, static mock. Hạn chế thay đổi; nếu buộc phải thay, hoàn nguyên trong `finally`/teardown và tránh chạy song song với test khác dùng cấu hình ấy.
- **Tài nguyên bên ngoài:** cùng tài khoản thật, endpoint thật, tài nguyên chung trên môi trường QA. Dùng fake/mock cho unit test và môi trường test cô lập cho phép thử tích hợp.

**Ví dụ phản mẫu** (đoạn rút gọn, không phải lớp chạy độc lập):

```java
static int createdOrders = 0;

@Test
void createsOrder() {
    createdOrders++;
    assertEquals(1, createdOrders);
}

@Test
void seesOrderFromPreviousTest() {
    assertEquals(1, createdOrders);
}
```

Test thứ hai phụ thuộc test thứ nhất; chạy lẻ sẽ sai, chạy lặp hoặc đổi thứ tự cũng dễ sai. Sửa bằng cách tạo trạng thái cần thiết ngay trong từng test. Nếu thật sự muốn kiểm tra luồng “tạo rồi đọc”, đưa cả hai thao tác vào **cùng một test**.

### 2.2. Vòng đời fixture

JUnit Jupiter mặc định tạo một instance của lớp test cho từng phương thức test; đây là hỗ trợ tốt cho trường *instance*, nhưng **không tự reset static field, database hoặc singleton của Spring**. `@BeforeEach` hữu ích để chuẩn bị dữ liệu mới; `@AfterEach` hoặc `try-with-resources` dùng khi cần giải phóng tài nguyên. Không biến teardown thành “chữa cháy” bằng cách xóa bừa toàn bộ database chung.

Với Spring Boot:

- **Unit test:** tự tạo class cần thử và fake/mock phụ thuộc, không khởi động `ApplicationContext` khi không cần.
- **Slice test:** dùng phạm vi phù hợp như `@WebMvcTest` cho web MVC hoặc `@DataJpaTest` cho JPA; chỉ tải các thành phần liên quan.
- **Integration test:** dùng `@SpringBootTest` khi thật sự cần kiểm tra phối hợp cấu hình, nhiều bean hoặc luồng xuyên tầng.

**Lưu ý giao dịch:** `@DataJpaTest` thường chạy trong transaction và rollback sau mỗi test; kiểm tra cấu hình thực tế trước khi tin vào hành vi đó. Trong `@SpringBootTest(webEnvironment = RANDOM_PORT)`, HTTP server xử lý yêu cầu ở thread/transaction khác với thread của test; `@Transactional` gắn trên test **không đảm bảo rollback** những lần ghi DB do request ở server thực hiện. Với trường hợp này, cần seed/cleanup riêng hoặc database cô lập.

## 3. Lặp lại được: kiểm soát mọi thứ có thể làm kết quả thay đổi

Một test quyết định hành vi phải phụ thuộc vào đầu vào được kiểm soát, không phụ thuộc hoàn cảnh không liên quan.

### 3.1. Thời gian, múi giờ và lịch

Không để logic nghiệp vụ gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()` ở nơi cần kiểm thử mốc thời gian. Inject `java.time.Clock`, dùng `Clock.fixed(...)` trong test để xác định chính xác “hiện tại”. Dùng mốc ISO-8601 với offset/UTC rõ ràng; kiểm thử ranh giới *trước*, *đúng tại*, *sau* deadline. Chỉ đổi timezone/locale khi chính đó là hành vi được kiểm thử.

### 3.2. Ngẫu nhiên, thứ tự dữ liệu và môi trường

- Nếu cần chuỗi ngẫu nhiên để kiểm thử, cấp seed cố định cho test quyết định hành vi; assert trên tính chất nghiệp vụ thay vì một giá trị ngẫu nhiên bất kỳ. Không chia sẻ một đối tượng `Random` mutable giữa nhiều test.
- Đừng giả định `SELECT` không có `ORDER BY` trả về thứ tự ổn định. Khi nghiệp vụ yêu cầu thứ tự, yêu cầu truy vấn sắp xếp; khi không yêu cầu thứ tự, assert theo tập hợp.
- Ghim hoặc quản lý phiên bản phụ thuộc, schema migration, cấu hình test và image container; tránh dữ liệu dùng chung với hệ thống thật.
- Không dựa vào tốc độ CPU, số luồng, thời điểm chạy CI hoặc kết nối Internet để xác định kết quả.

### 3.3. Không dùng độ trễ cố định làm phép đồng bộ

**Phản mẫu:** gửi event bất đồng bộ, `Thread.sleep(1000)` rồi assert. Máy nhanh có thể xanh, CI tải nặng có thể đỏ; tăng lên 10 giây làm suite chậm mà vẫn không bảo đảm.

**Thay thế:** đợi điều kiện quan sát được với timeout hữu hạn (ví dụ thư viện Awaitility, cơ chế đồng bộ thích hợp, hoặc API kiểm tra trạng thái). Đặt timeout cho toàn bộ việc chờ, thông báo lỗi cho biết điều kiện chưa đạt, và không nuốt lỗi khi hết hạn. Nếu kiểm thử yêu cầu đồng hồ giả, dùng scheduler/clock điều khiển được thay vì chờ thời gian thực.

### 3.4. Phụ thuộc ngoài và test data

- Unit test đối với HTTP client: thay server ngoài bằng stub/fake có phản hồi xác định; kiểm tra request quan trọng, timeout và đường lỗi.
- Integration test đối với database/queue: dùng tài nguyên cô lập như container test với dữ liệu khởi tạo rõ ràng. Testcontainers giúp chạy dịch vụ thật theo image đã chọn, nhưng **container chạy chung không đồng nghĩa dữ liệu test độc lập**.
- Không gọi API sản xuất hay gửi email thật trong suite mặc định. Chế độ kiểm thử end-to-end với tài nguyên bên ngoài phải có môi trường và vòng đời riêng.

## 4. Ví dụ thực hành Java 17+ / JUnit Jupiter: kiểm soát Clock

Giả sử service kiểm tra mã truy cập hết hạn khi thời điểm hiện tại **lớn hơn hoặc bằng** deadline. Hai file sau chạy được trong một dự án Java/Spring Boot có JUnit Jupiter trên test classpath.

**File `src/main/java/com/example/testing/ExpiryPolicy.java`:**

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(deadline);
        return !clock.instant().isBefore(deadline);
    }
}
```

**File `src/test/java/com/example/testing/ExpiryPolicyTest.java`:**

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ExpiryPolicyTest {
    private final Instant now = Instant.parse("2026-01-01T10:00:00Z");
    private final ExpiryPolicy policy =
            new ExpiryPolicy(Clock.fixed(now, ZoneOffset.UTC));

    @Test
    void beforeDeadlineIsValid() {
        assertFalse(policy.isExpired(now.plusSeconds(1)));
    }

    @Test
    void exactlyAtDeadlineIsExpired() {
        assertTrue(policy.isExpired(now));
    }

    @Test
    void afterDeadlineIsExpired() {
        assertTrue(policy.isExpired(now.minusSeconds(1)));
    }
}
```

Trong Spring Boot Gradle project đã cấu hình quản lý dependency, bảo đảm có JUnit Jupiter và JUnit Platform (thường từ `spring-boot-starter-test`):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy lớp test bằng Gradle Wrapper từ thư mục dự án:

```bash
./gradlew test --tests com.example.testing.ExpiryPolicyTest
```

Trên Windows PowerShell dùng `.\gradlew.bat test --tests com.example.testing.ExpiryPolicyTest`. Kết quả mong đợi: **3 test thành công**, Gradle hoàn thành task `test`; thông điệp console chính xác có thể khác theo Gradle/plugin nên không giả định một dòng stdout cụ thể.

**Vì sao ví dụ đạt ba tiêu chí?** Mỗi test khởi tạo đối tượng và clock riêng, không dùng state chung, không cần Spring context/DB/mạng; thời điểm không đổi nên assert ranh giới ổn định; kết quả có ngay sau khi chạy unit test. Logic sản xuất vẫn dùng clock thực khi ứng dụng inject `Clock.systemUTC()`; test inject clock cố định để kiểm soát đầu vào.

## 5. Spring Boot: chọn mức test đủ để bắt lỗi

| Mức test | Mục tiêu chính | Cách làm thường gặp | Tốc độ tương đối |
|---|---|---|---|
| Unit | Luật nghiệp vụ, biến đổi, boundary, nhánh lỗi | JUnit + object thật, stub/mock phụ thuộc; không load Spring | Rất nhanh |
| Slice | Một lớp tích hợp hẹp, mapping/validation/JPA query | `@WebMvcTest`, `@DataJpaTest` theo nhu cầu | Trung bình |
| Integration | Nhiều bean, transaction, kết nối DB/queue, config | `@SpringBootTest` và hạ tầng test cô lập | Chậm hơn |
| End-to-end | Hành vi người dùng hoặc đường đi dịch vụ thực | Chạy ứng dụng và những thành phần thiết yếu | Tốn kém nhất |

Phân loại theo **mức phối hợp cần chứng minh**, không theo sở thích annotation. Ví dụ, không nên đặt `@SpringBootTest` lên 200 test tính toán số học chỉ vì dự án dùng Spring Boot. Ngược lại, mock hết repository và HTTP client trong test mà mục tiêu là xác nhận cấu hình kết nối thật cũng chưa đủ.

### 5.1. Tái sử dụng Spring context đúng cách

Spring TestContext có cache `ApplicationContext` cho các test có cùng cấu hình trong cùng tiến trình, nên gom những test có cấu hình tương thích giúp giảm thời gian khởi động. Việc đổi profile, properties, bean override, dynamic properties hoặc cấu hình context có thể tạo khóa cache khác. Dùng `@DirtiesContext` khi test thực sự làm hỏng context; lạm dụng annotation này làm tải context lại và khiến suite chậm.

**Không sửa state chỉ để giữ cache.** Context reuse tiết kiệm thời gian, nhưng fixture DB/singleton vẫn phải sạch giữa các test. Cách tối ưu thường là dùng context không đổi cộng với dữ liệu test độc lập, chứ tạo lại context cho từng test.

### 5.2. Database và Testcontainers

Khi cần độ trung thực với PostgreSQL/MySQL thật, Testcontainers có thể khởi tạo DB trong container; pin image version và áp dụng migration như môi trường dự kiến. Container khai báo `static` bằng JUnit extension thường dùng chung cho các test method trong lớp, giúp giảm chi phí startup. Tuy vậy, dữ liệu giữa các method vẫn chia sẻ nếu không reset. Chọn một chiến lược rõ ràng:

1. Mỗi test chuẩn bị dữ liệu với khóa riêng, cleanup đúng dữ liệu mình tạo; hoặc
2. Transaction rollback nếu tất cả thao tác thuộc cùng transaction được Spring test quản lý; hoặc
3. Tạo schema/database độc lập cho nhóm test khi chạy song song hoặc dùng server thật.

Không bật parallel cho Testcontainers JUnit 5 extension một cách mặc định: khả năng phối hợp lifecycle và tài nguyên chia sẻ cần được xác minh riêng; tài liệu Testcontainers cảnh báo extension này chưa hỗ trợ chạy song song một cách tổng quát.

## 6. Tối ưu phản hồi: thời gian phát hiện lỗi quan trọng hơn số lượng test

Một vòng phản hồi hiệu quả thường có các tầng:

1. **Trong IDE / mỗi lần sửa nhỏ:** chạy unit test liên quan và các kiểm tra tĩnh rẻ.
2. **Trước khi push / trong pull request:** chạy toàn bộ unit test, slice test cần thiết, rồi integration test quan trọng.
3. **Nightly / trước phát hành:** chạy end-to-end, tải lớn hoặc các bài tích hợp chậm ít thay đổi.

Nếu một bài test chạy 5 giây nhưng sai lệch ngẫu nhiên, 10 lần chạy lại không giúp đội phát triển nhanh hơn. Ưu tiên **tín hiệu thất bại đáng tin và chẩn đoán được**, sau đó giảm thời gian thực thi.

Các đòn bẩy hiệu quả:

- Giữ unit test không phụ thuộc Spring context, file, DB, network.
- Chỉ load context phù hợp với phạm vi được kiểm tra; tận dụng cache và hạn chế cấu hình không cần thiết.
- Seed fixture tối thiểu, tránh tạo dữ liệu lớn ở mỗi test khi không kiểm tra dữ liệu lớn.
- Tránh `sleep` cố định; dùng điều kiện chờ có timeout.
- Phân nhóm test chậm bằng JUnit `@Tag("integration")` hoặc cơ chế task/source set của build, có quy tắc CI rõ ràng; không đơn giản loại test chậm khỏi mọi pipeline.
- Cân nhắc chạy song song khi mọi test đã độc lập và hạ tầng đủ khả năng; đo lại vì tranh chấp CPU, DB hoặc container có thể khiến tổng thời gian tăng.

### 6.1. Parallel execution là bước sau, không phải bước đầu

JUnit Jupiter mặc định chạy tuần tự. Bật cấu hình dưới đây trong `src/test/resources/junit-platform.properties` là một lựa chọn để chạy **các lớp** đồng thời nhưng giữ **các method trong mỗi lớp** tuần tự:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

Chỉ bật khi không có static state/DB/port/cache dùng chung gây xung đột. Với tài nguyên chung bất khả kháng, `@ResourceLock` có thể bảo vệ tài nguyên được khai báo, nhưng lock chỉ tuần tự hóa truy cập, không làm phép thử vốn lệ thuộc dữ liệu trở nên độc lập. So sánh thời gian và độ ổn định trước/sau thay đổi; đặc biệt kiểm tra giới hạn kết nối DB và vòng đời container.

## 7. Nhận diện và xử lý flaky test

**Flaky test** là test có kết quả khác nhau giữa các lần chạy khi mã và điều kiện mong muốn không đổi. Một vài nguồn thường gặp:

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý thực chất |
|---|---|---|
| Đỏ khi chạy cả suite, xanh khi chạy lẻ | State/fixture chia sẻ, giả định thứ tự | Tìm resource ghi chung, tạo fixture riêng, dọn đúng scope |
| Chỉ đỏ trên CI | Timing, timezone, tài nguyên thiếu, cấu hình khác | Cố định clock/locale, ghi rõ môi trường, đợi theo điều kiện |
| Thỉnh thoảng timeout | `sleep`, scheduler, dịch vụ bên ngoài, quá tải | Điều kiện chờ có timeout, stub external, cô lập tài nguyên |
| Dữ liệu trả về đảo thứ tự | Không có ORDER BY, assert theo index | Sắp xếp khi nghiệp vụ yêu cầu hoặc so sánh như tập hợp |
| Thất bại khi parallel | Static mutable state, port cố định, transaction/data tranh chấp | Cô lập nguồn chia sẻ rồi mới bật parallel |
| Test Spring lúc nhanh lúc rất chậm | Cache miss, context reload, container start, profiling khác nhau | Theo dõi context cache, giảm biến thể config, đo cold/warm riêng |

Quy trình điều tra thực tế: ghi lại seed/input, profile, timezone, JDK, DB/image version, thread và lỗi đầy đủ; chạy lại **một test**, **cả lớp** và **cả suite**, thay đổi thứ tự hoặc chạy lặp đủ lần để khoanh vùng. JUnit `@RepeatedTest(20)` có thể giúp tái hiện một số lỗi nhưng không chứng minh test độc lập; môi trường lặp lại vẫn cần được kiểm soát. Khi fix, tạo regression test thể hiện nguyên nhân; không chỉ tăng timeout, retry vô hạn hay xóa assert để làm CI xanh.

## 8. Một ví dụ thiết kế trước và sau

Giả sử test tạo đơn hàng gọi API thật, đọc `LocalDate.now()`, lưu vào database dùng chung, rồi mong bản ghi cuối cùng trong bảng là đơn của mình. Test ấy phụ thuộc mạng, đồng hồ, dữ liệu test khác và thứ tự DB; chạy rất chậm và dễ flaky.

Thiết kế lại theo mục tiêu kiểm chứng:

- **Luật hết hạn/giảm giá:** trích ra service nhận `Clock`, repository interface và input; unit test với clock cố định, fake repository, assert chính xác từng boundary.
- **HTTP contract:** dùng slice web, request/response và validation xác định; kiểm thử authorization bằng cấu hình test thích hợp.
- **Persistence:** test repository trên database test riêng, fixture theo từng test; kiểm tra nội dung bản ghi và trường khóa, không đoán “dòng cuối”.
- **Đường đi đầy đủ:** chỉ có số ít test tích hợp thực sự đi qua server, DB và các adapter cần thiết; seed/cleanup có chiến lược, timeout rõ ràng và cổng ngẫu nhiên khi phù hợp.

Kết quả là các lỗi tính toán xuất hiện gần như ngay lập tức, lỗi mapping/database vẫn có chỗ bắt, còn end-to-end không phải gánh mọi trường hợp biên.

## 9. Bộ tiêu chí tự đánh giá khi review test hoặc CI

Dùng những câu hỏi sau để xác nhận chất lượng của **từng phép thử** và **cả suite**:

- Test có pass khi chạy một mình? Có pass khi chạy lặp và khi đổi thứ tự các test cùng nhóm?
- Có static/singleton state, DB, file, topic, cache, system properties hoặc tài nguyên môi trường chia sẻ mà test đang ngầm dựa vào?
- Fixture có được tạo trong Arrange, có tên/ID riêng và cleanup rõ? Trường hợp rollback có thật sự bao phủ thread/transaction liên quan?
- Thời gian, timezone, locale, ngẫu nhiên, thứ tự kết quả và phản hồi từ bên ngoài có được kiểm soát?
- Có `Thread.sleep`, retry vô hạn, assert mơ hồ, hoặc bỏ qua lỗi để test xanh?
- Test ở đúng tầng? Có khởi động context/container/network chỉ để kiểm tra một phép tính?
- Khi thất bại, thông báo chỉ ra hành vi, input và expected/actual đủ để sửa? Có giữ log hữu ích nhưng không ghi bí mật?
- PR CI phản hồi đủ sớm? Đã đo riêng thời gian cold start, warm run, tỷ lệ flaky và nhóm test chậm?
- Parallel chỉ được kích hoạt sau khi kiểm chứng state và resource lifecycle đủ độc lập?

**Nguyên tắc vận hành:** một kết quả thất bại phải có ý nghĩa. Nếu một test thường xuyên “đỏ giả”, cả nhóm sẽ mất niềm tin vào bộ kiểm thử; nếu một test nhanh nhưng bỏ qua lỗi quan trọng, phản hồi cũng mất giá trị. Mục tiêu là **độc lập để đáng tin, quyết định để lặp lại được, phân tầng để phản hồi sớm**.

## Tài liệu tham khảo

- Spring Boot — [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html), gồm context cache và các test slice.
- Spring Framework — [Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html).
- JUnit Jupiter — [Parallel Execution](https://docs.junit.org/5.13.1/user-guide/index.html#writing-tests-parallel-execution) và [Test Execution Order](https://docs.junit.org/5.13.1/user-guide/index.html#writing-tests-test-execution-order).
- Testcontainers — [JUnit Jupiter Extension](https://java.testcontainers.org/test_framework_integration/junit_5/).