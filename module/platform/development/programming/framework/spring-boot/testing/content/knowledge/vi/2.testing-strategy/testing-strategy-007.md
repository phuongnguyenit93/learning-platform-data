# Viết kiểm thử hồi quy trước hoặc cùng lúc sửa lỗi trong Spring Boot

## 1. Tại sao sửa lỗi phải đi cùng kiểm thử hồi quy?

Một lỗi đã được sửa có thể quay lại trong lần refactor, thay đổi cấu hình, nâng cấp thư viện hoặc bổ sung chức năng sau đó. **Kiểm thử hồi quy (regression test)** ghi lại hành vi đúng bằng đầu vào và assertion cụ thể, để các lần chạy test sau phát hiện nếu hành vi đó bị phá vỡ.

Giả sử người dùng phát hiện **mã giảm giá vẫn được chấp nhận đúng tại thời điểm hết hạn**. Lập trình viên đổi điều kiện trong service và thấy vấn đề biến mất. Nhưng nếu không giữ một test về trường hợp `now == expiresAt`, việc sửa logic ở lần sau có thể vô tình làm lỗi tái diễn.

Viết regression test trước hoặc ngay trong lúc sửa lỗi giúp nhóm đạt bốn kết quả:

1. **Tái hiện lỗi theo cách có thể lặp lại:** Chuyển triệu chứng từ mô tả hoặc log thành một phép kiểm tra.
2. **Xác nhận fix có hiệu quả:** Test thất bại vì hành vi sai trước fix và đạt sau fix.
3. **Ngăn lỗi cũ quay lại:** Regression test được giữ trong codebase và chạy lại trong CI.
4. **Làm rõ hợp đồng nghiệp vụ:** Assertion cho biết hệ thống phải làm gì tại những tình huống dễ bị bỏ sót, nhất là điều kiện biên và đường đi lỗi.

Đây là một thực hành sửa lỗi dựa trên bằng chứng, không đồng nghĩa bắt buộc mọi đội phải áp dụng đầy đủ Test-Driven Development cho toàn bộ tính năng. Điểm cốt lõi là **chứng minh test mới thực sự bắt được bug được báo và tiếp tục bảo vệ hành vi sau khi sửa**.

## 2. Xác định chính xác lỗi trước khi viết test

Không nên lấy kết quả đang sai làm expected value. Hãy tách rõ:

| Thành phần | Ví dụ |
|---|---|
| Triệu chứng | Mã giảm giá được chấp nhận ngay tại thời điểm hết hạn |
| Input/trạng thái tái hiện | `now == expiresAt` |
| Kết quả đang có | `canRedeem(...)` trả `true` |
| Kết quả đúng theo hợp đồng | `canRedeem(...)` phải trả `false` |
| Phạm vi nguyên nhân nghi ngờ | Phép so sánh thời gian trong service |
| Test thích hợp đầu tiên | JUnit unit test trên logic thời hạn |
| Ranh giới có thể cần kiểm tra thêm | Controller, timezone, persistence hoặc Security nếu bug liên quan |

Bằng chứng tối thiểu của bug report nên mô tả phiên bản/commit, đầu vào, bước tái hiện, kết quả thực tế, kết quả mong đợi và điều kiện môi trường quan trọng (profile, timezone, database, quyền truy cập). Không đưa token, mật khẩu hay dữ liệu khách hàng thật vào test fixture.

**Xác nhận yêu cầu trước khi khóa nó bằng test.** Với ví dụ trên, quy tắc là mã có hiệu lực khi `now < expiresAt`. Nếu nghiệp vụ thực tế quy định thời điểm hết hạn vẫn được dùng, đó là một hợp đồng khác và test cũng phải khác. Một regression test sai có thể giữ một lỗi lâu dài.

## 3. Quy trình RED → GREEN → REGRESSION

### Bước 1. Tái hiện bằng trường hợp nhỏ nhất

Chọn đúng lớp xảy ra lỗi: service logic, controller/validation, Spring context, repository/database, Security hay HTTP client. Nếu lỗi là biểu thức so sánh thời gian trong service, bắt đầu bằng unit test thuần JUnit sẽ nhanh và dễ xác định hơn việc tải toàn bộ Spring context.

Tái hiện được qua màn hình hoặc Postman là một bước hữu ích, nhưng nên chuyển thành test tự động khi có thể. Test phải chứa đầu vào, thao tác và assertion rõ ràng.

### Bước 2. Viết test cho hành vi đúng và chạy trước fix

Với phiên bản còn bug, test mới phải **đỏ vì đúng nguyên nhân**. Ví dụ, assertion thông báo kết quả mong đợi là `false` nhưng thực tế là `true` ở ngưỡng hết hạn.

Phân biệt các trạng thái:
- **RED hợp lệ:** Test chạy được và assertion phát hiện hành vi sai cần sửa.
- **RED không hợp lệ:** Test không biên dịch, thiếu bean, database không khởi động hoặc fixture sai; chưa có bằng chứng bắt được lỗi nghiệp vụ.
- **GREEN ngay từ đầu:** Test có thể chưa đi qua nhánh lỗi, đang chạy trên mã đã fix hoặc dùng môi trường không tái hiện được. Cần điều tra trước khi coi là regression test đạt yêu cầu.

Nếu test chỉ thất bại ngẫu nhiên, hãy cô lập nguyên nhân không ổn định thay vì tuyên bố đã tái hiện.

### Bước 3. Sửa nguyên nhân rồi chạy lại test

Thay đổi mã production để thỏa hợp đồng đã xác nhận. **Không nới lỏng expected value hay xóa assertion để ép test xanh.** Khi test đỏ hợp lệ trước fix và xanh sau fix, nhóm có bằng chứng cụ thể cho chính tình huống đó.

Nhìn lại root cause: cùng một phép so sánh sai có thể nằm ở nhiều đường đi. Một fix chỉ điều chỉnh output để test xanh nhưng không sửa nguyên nhân có thể để sót bug.

### Bước 4. Chạy test liên quan và CI

Sau khi test mới xanh, chạy các test khác của service/module và những test tích hợp chịu ảnh hưởng. Pipeline CI nên chạy suite phù hợp trước merge; nếu nhóm cấu hình branch protection, test thất bại có thể chặn merge. Test mới nên được commit cùng fix và giữ để ngăn lỗi hồi quy trong tương lai.

## 4. Ví dụ Java 17+: tái hiện và sửa lỗi điều kiện biên

### 4.1. Giả định nghiệp vụ

Trong ứng dụng Spring Boot, mã ưu đãi chỉ được dùng **trước** hạn, không được dùng đúng hoặc sau hạn. Service có phương thức `canRedeem(Instant expiresAt)`. Để kiểm thử thời gian một cách quyết định, service nhận `java.time.Clock` qua constructor thay vì gọi thời gian hệ thống không kiểm soát trực tiếp.

Ban đầu, service có logic sai:

```java
return !Instant.now(clock).isAfter(expiresAt);
```

Điều kiện này tương đương `now <= expiresAt`. Khi `now` bằng `expiresAt`, nó trả `true`, trong khi hợp đồng yêu cầu `false`.

### 4.2. Viết test hồi quy trước khi sửa

Tệp `src/test/java/com/example/testing/CouponValidityServiceTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CouponValidityServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-03-01T10:00:00Z");

    private final CouponValidityService service =
            new CouponValidityService(Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void acceptsCouponBeforeExpiry() {
        assertTrue(service.canRedeem(NOW.plusMillis(1)));
    }

    @Test
    void rejectsCouponAtExactExpiry() {
        assertFalse(service.canRedeem(NOW));
    }

    @Test
    void rejectsCouponAfterExpiry() {
        assertFalse(service.canRedeem(NOW.minusMillis(1)));
    }
}
```

Ba test bảo vệ ba phía của ranh giới:
- **Chưa hết hạn:** `expiresAt` sau `NOW` một mili giây; kết quả là `true`.
- **Đúng lúc hết hạn:** `expiresAt == NOW`; kết quả là `false`.
- **Đã hết hạn:** `expiresAt` trước `NOW` một mili giây; kết quả là `false`.

Với implementation lỗi `!now.isAfter(expiresAt)`, test `rejectsCouponAtExactExpiry` sẽ **thất bại** vì giá trị thực tế `true` khác giá trị mong đợi `false`. Hai test còn lại đạt. Điều này giúp xác định lỗi ở điểm bằng ngưỡng, thay vì chỉ biết “test bị lỗi”.

### 4.3. Sửa implementation mà không sửa assertion

Tệp `src/main/java/com/example/testing/CouponValidityService.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Service;

@Service
public class CouponValidityService {

    private final Clock clock;

    public CouponValidityService(Clock clock) {
        this.clock = clock;
    }

    public boolean canRedeem(Instant expiresAt) {
        return Instant.now(clock).isBefore(expiresAt);
    }
}
```

Biểu thức `isBefore(expiresAt)` đúng khi và chỉ khi thời điểm hiện tại **nhỏ hơn** thời điểm hết hạn. Đúng tại hạn hoặc sau hạn sẽ trả về `false`.

Ứng dụng cần cung cấp bean `Clock` để Spring khởi tạo service. Tệp `src/main/java/com/example/testing/TimeConfiguration.java`:

```java
package com.example.testing;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
```

Ba lớp trên là ví dụ Java hoàn chỉnh trong package `com.example.testing`. Giả định chúng nằm trong dự án Spring Boot dùng Java 17+, có dependency `spring-boot-starter-test`, được component scan bao phủ và có cấu trúc source Maven/Gradle chuẩn. Unit test khởi tạo service trực tiếp nên không cần khởi động Spring context. Ứng dụng lúc chạy thật dùng `Clock.systemUTC()`, còn test dùng `Clock.fixed(...)` để tái hiện kết quả ổn định mà không cần `Thread.sleep`.

### 4.4. Chạy kiểm thử

Nếu dự án có Gradle wrapper:

```bash
./gradlew test --tests "com.example.testing.CouponValidityServiceTest"
```

Trên Windows PowerShell: `.\gradlew.bat test --tests "com.example.testing.CouponValidityServiceTest"`.

Nếu dự án có Maven wrapper:

```bash
./mvnw -Dtest=CouponValidityServiceTest test
```

Trên Windows PowerShell: `.\mvnw.cmd -Dtest=CouponValidityServiceTest test`.

Các lệnh giả định dự án đã cấu hình JUnit Jupiter (thường đi kèm starter test) và wrapper phù hợp. **Trước fix:** case `rejectsCouponAtExactExpiry` phải thất bại ở assertion. **Sau fix:** cả ba case phải đạt. Không giả định một đoạn stdout cố định vì log phụ thuộc phiên bản Gradle/Maven, plugin và cấu hình runner; nên xem test report hoặc kết quả của chính lần chạy thực tế.

Giới hạn của ví dụ: ba unit test bảo vệ quy tắc thời hạn. Chúng chưa chứng minh HTTP endpoint, serialization, database, Security filter hoặc múi giờ ở đầu vào hoạt động đúng. Nếu bug thực tế nằm tại các ranh giới đó thì cần bổ sung test thích hợp.

## 5. Nếu viết test đồng thời hoặc sau khi sửa lỗi thì sao?

Trong tình huống incident hoặc bugfix gấp, nhóm có thể sửa code và viết test ngay trong cùng một chu kỳ. Để test hồi quy vẫn đáng tin:

1. Ghi rõ đầu vào và expected result của bug **trước khi quên điều kiện tái hiện**.
2. Thêm test cho ca gây bug; chọn dữ liệu và dependency có thể kiểm soát.
3. Nếu an toàn và khả thi, chạy test trên phiên bản chưa fix trong nhánh riêng hoặc tạm tái hiện đúng logic lỗi trong môi trường kiểm tra rồi hoàn nguyên, nhằm xác minh test đỏ vì bug.
4. Chạy test trên phiên bản đã fix và kiểm tra xanh; chạy suite liên quan và CI.
5. Commit test cùng fix; ghi rõ trong PR nếu **không thể** xác minh trạng thái đỏ trước fix.

Không sửa hệ thống đang triển khai chỉ để chứng minh test đỏ; dùng nhánh và môi trường test an toàn. Nếu không tái hiện được trạng thái cũ, test xanh sau fix vẫn hữu ích, nhưng **chưa chứng minh nó chắc chắn bắt được lỗi ban đầu**. Đây là giới hạn cần công khai khi review, không nên che bằng tuyên bố “đã có regression test” không kèm bằng chứng.

Một mô tả PR gọn có thể nêu: “Trước fix, mã dùng được tại `now == expiresAt`. Thêm `rejectsCouponAtExactExpiry` chứng minh assertion fail trên logic cũ; đổi sang `isBefore`; test mới và suite liên quan pass.” Chỉ khẳng định những bước thực sự đã kiểm chứng.

## 6. Chọn lớp kiểm thử đúng trong Spring Boot

Không phải bug nào cũng nên được giữ bằng test `@SpringBootTest` nạp toàn bộ ứng dụng. Hãy bắt đầu ở ranh giới thấp nhất vẫn tái hiện nguyên nhân, sau đó bổ sung kiểm tra ở mức cao hơn nếu cần.

| Vị trí lỗi | Test nên ưu tiên | Hành vi cần kiểm chứng |
|---|---|---|
| Tính toán, điều kiện, quy tắc state trong service | Unit test JUnit 5, Mockito khi cần cô lập phụ thuộc | Giá trị trả về, ngoại lệ, nhánh biên |
| Controller, JSON, request validation, HTTP status | Web slice với `@WebMvcTest` và `MockMvc` | Mapping, response body, status, thông điệp lỗi |
| Bean injection, Spring profile, cấu hình, chuỗi service | `@SpringBootTest` hoặc integration test phù hợp | Context và phối hợp thành phần thật |
| Repository, JPA mapping, SQL, transaction | `@DataJpaTest` hoặc integration test với database phù hợp | Query, constraint, dữ liệu lưu, transaction |
| Xác thực và phân quyền | Test đi qua security chain tương ứng | 401/403/200 theo hợp đồng truy cập |
| HTTP client, message queue, database ngoài | Contract/integration test với stub hoặc môi trường kiểm thử | Payload, timeout, lỗi, retry, idempotency |
| Luồng nghiệp vụ từ đầu đến cuối | End-to-end test ở môi trường có kiểm soát | Hành vi người dùng quan sát được |

Ví dụ, nếu bug là request thiếu dữ liệu nhưng controller trả 200 thay vì 400, test service trực tiếp không đi qua validation sẽ không bảo vệ đúng lỗi. Cần gửi request bằng `MockMvc` hoặc HTTP test và assert status/body. Ngược lại, với lỗi `<` so với `<=`, unit test nhanh đã đủ để bảo vệ phép so sánh; có thể thêm integration test nếu con đường nhận và chuyển đổi thời gian ở API cũng có rủi ro.

Lưu ý khi chọn annotation:
- `@SpringBootTest` nạp application context, nhưng mặc định **không** khởi chạy HTTP server thật. Nếu cần HTTP server ngẫu nhiên, cấu hình `webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT`.
- `@WebMvcTest` là một lát cắt MVC, không tự nạp tất cả bean/service của ứng dụng; cung cấp collaborator hoặc test bean phù hợp với phiên bản Spring Boot/Spring Framework của dự án.
- Với JPA, database in-memory có thể xử lý SQL khác PostgreSQL/MySQL. Dùng Testcontainers hoặc database thử nghiệm gần production khi lỗi phụ thuộc ngữ nghĩa DB thật.
- Với Security, đừng vô hiệu hóa filter trong test nếu bug liên quan đến phân quyền: cách đó có thể làm test xanh trong khi lỗ hổng vẫn tồn tại.

## 7. Thiết kế regression test bền vững

### 7.1. Assert hành vi, tránh khóa chặt cách triển khai

Test nên quan sát hợp đồng: giá trị trả về, response, trạng thái lưu, event phát đi hoặc ngoại lệ. Không assert số lần gọi hàm helper nội bộ khi số lần gọi không phải yêu cầu nghiệp vụ. Một test phụ thuộc quá sâu vào cấu trúc nội bộ sẽ đỏ sau refactor hợp lệ và mất giá trị cảnh báo.

### 7.2. Kiểm tra đúng trường hợp biên liên quan đến bug

Một lỗi `>`/`>=` hoặc `<`/`<=` thường được chặn tốt bằng ca **trước – đúng – sau ngưỡng**. Với lỗi nhập liệu, kiểm tra dữ liệu hợp lệ, bất hợp lệ và giá trị biên. Với lỗi transaction, kiểm tra hành vi khi thành công lẫn khi một bước thất bại. Chỉ thêm các ca thực sự giúp bảo vệ hợp đồng.

### 7.3. Loại bỏ các nguồn gây test flaky

- Với thời gian: inject `Clock`, dùng mốc cố định; không dựa vào thời điểm máy thực.
- Với async: dùng cơ chế chờ theo điều kiện có timeout hợp lý thay vì ngủ một khoảng bất kỳ.
- Với database: tạo fixture độc lập, kiểm soát state và hiểu việc rollback/commit của test.
- Với network: stub giả lập giao tiếp khi phù hợp; integration test dùng môi trường riêng có thể tái tạo.
- Với concurrency: tạo điều kiện tranh chấp có kiểm soát và xác minh invariant của dữ liệu; test chạy tuần tự không chứng minh an toàn đồng thời.
- Với mock: không mock chính class đang chứa bug hoặc tự định nghĩa output đúng rồi cho rằng production code đã được kiểm tra.

### 7.4. Tên test và lỗi thất bại phải dễ hiểu

Tên như `rejectsCouponAtExactExpiry` cho biết hoàn cảnh và kết quả mong đợi. Assertion nên cho thấy sai lệch cụ thể. Nếu một test cần chuẩn bị nhiều dependency không liên quan, xem lại phạm vi và tách setup bằng factory/fixture rõ ràng. Đừng gộp quá nhiều hành vi độc lập trong cùng một test chỉ để giảm số lượng test case.

## 8. Cân nhắc thêm test ở những ranh giới thường che giấu lỗi

**Lỗi múi giờ hoặc kiểu thời gian:** Java `Instant` biểu thị một thời điểm tuyệt đối; `LocalDateTime` không chứa timezone. Nếu controller parse dữ liệu thời gian sai, một unit test chỉ dùng `Instant` có thể vẫn xanh. Thêm test ở nơi chuyển đổi input theo hợp đồng API.

**Lỗi transaction:** Một test service dùng mock repository có thể không phát hiện transaction rollback sai. Kiểm tra dữ liệu được lưu sau hành vi thất bại trong môi trường database phù hợp. Chú ý test mặc định rollback transaction có thể che khuất vấn đề cần quan sát lúc commit.

**Lỗi đồng thời:** Hai yêu cầu đổi cùng trạng thái đơn hàng hoặc cùng sử dụng mã một lần có thể gây race condition. Test tuần tự thường không tái hiện; cần test nhiều luồng hoặc integration với constraint/isolation thích hợp. Không giả định một lock trong JVM giải quyết được hệ thống chạy nhiều instance.

**Lỗi cấu hình chỉ xuất hiện trên môi trường nhất định:** Một test context với profile mặc định không chứng minh profile khác hoạt động. Khi bug phụ thuộc profile, property, database hoặc bean điều kiện, hãy đưa cấu hình liên quan vào regression test.

**Lỗi HTTP và Security:** Nếu bug là trả sai HTTP status hoặc vượt qua kiểm tra quyền, test phải đi qua MVC/Security filter chain thực tế. Test dùng mock toàn bộ security có thể tránh mất ổn định nhưng không kiểm chứng lỗi phân quyền.

## 9. Các lỗi phổ biến khi viết test hồi quy

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chỉ chạy test trên mã đã fix | Không biết test có bắt bug cũ hay không | Xác minh RED trên logic cũ khi có thể |
| Đổi expected value cho khớp output sai | Hợp thức hóa bug | Dựa vào yêu cầu nghiệp vụ |
| Chỉ kiểm tra `contextLoads()` | Context xanh không chứng minh hành vi đúng | Thêm assertion cho đường đi lỗi |
| Mock component chứa bug | Test xác minh mock, không xác minh logic thật | Dùng implementation thật của phần đang sửa |
| Bỏ qua điều kiện biên | Test xanh ở trường hợp bình thường, bug vẫn còn | Kiểm tra gần và ngay ngưỡng |
| Dùng thời gian thật, dữ liệu chia sẻ, mạng ngoài | Suite chạy thiếu ổn định | Cố định input và cô lập phụ thuộc |
| Chỉ chạy test mới, không chạy test khác | Fix có thể phá chức năng lân cận | Chạy test liên quan và CI |
| Xóa regression test sau khi fix | Không còn cảnh báo khi lỗi quay lại | Giữ test trong suite |
| Bắt đầu bằng full-context test cho logic rất nhỏ | Suite chậm, khó định vị nguyên nhân | Chọn cấp độ nhỏ nhất đủ tái hiện |
| Kết luận quá rộng từ một test xanh | Bỏ sót lỗi API, DB, Security và cấu hình | Ghi rõ phạm vi được kiểm chứng |

## 10. Checklist trước khi đóng bugfix hoặc merge PR

- [ ] Hành vi mong đợi đã được xác nhận; có bước tái hiện tối thiểu và bằng chứng bug.
- [ ] Test mới kiểm tra đúng tình huống lỗi, với expected result từ hợp đồng chứ không từ implementation hiện tại.
- [ ] Đã quan sát test **đỏ vì đúng bug trên phiên bản chưa sửa** khi điều kiện cho phép; nếu chưa, đã ghi rõ giới hạn.
- [ ] Fix khắc phục nguyên nhân và test mới chuyển sang xanh mà không làm yếu assertion.
- [ ] Những ca biên liên quan đã được kiểm tra; đã cân nhắc test API, database, Security hoặc Spring context nếu lỗi liên quan đến các tầng đó.
- [ ] Test độc lập, có thể lặp lại, không cần phụ thuộc ngẫu nhiên vào giờ chạy, thứ tự test hoặc hệ thống bên ngoài.
- [ ] Đã chạy các test liên quan và CI; kết quả báo cáo phản ánh lần chạy thật.
- [ ] Test và fix được giữ cùng codebase, để refactor và nâng cấp sau này vẫn có cảnh báo hồi quy.

**Kết luận:** Viết kiểm thử hồi quy trước hoặc cùng lúc sửa lỗi biến sự cố đã xảy ra thành một phép kiểm tra lâu dài. Bằng chứng mạnh nhất là **RED đúng nguyên nhân → GREEN sau fix**, với assertion phản ánh hợp đồng, cấp độ kiểm thử đúng vị trí lỗi và bộ test đủ ổn định để tiếp tục bảo vệ Spring Boot ở những lần thay đổi tiếp theo.