# Chọn cấp kiểm thử theo rủi ro và phạm vi cần chứng minh

Một hệ thống có nhiều bài kiểm thử vẫn có thể lỗi nghiêm trọng nếu chúng chỉ chứng minh những điều dễ kiểm tra. Khi chọn cấp kiểm thử (test level), hãy bắt đầu bằng câu hỏi: **Nếu tính năng sai, điều gì gây thiệt hại và ta cần quan sát ranh giới nào để chứng minh nó đúng?** Sau đó mới chọn unit, slice, integration, contract hay end-to-end (E2E).

Bài học này áp dụng cho ứng dụng Spring Boot, nhưng nguyên tắc chọn phạm vi có thể dùng cho hầu hết ứng dụng Java.

## 1. Hai trục quyết định: rủi ro và bằng chứng

**Rủi ro** là khả năng một lỗi xuất hiện kết hợp với hậu quả nếu lỗi xảy ra. Có thể chấm riêng xác suất và mức ảnh hưởng theo thang 1–5 để *xếp ưu tiên tương đối*, không coi tích điểm là xác suất thống kê chính xác. Tác động nên xét cả tiền bạc, bảo mật, dữ liệu, trải nghiệm người dùng, pháp lý và khả năng phục hồi.

**Phạm vi cần chứng minh** (scope of evidence) là phần của hệ thống phải chạy thật để phát hiện loại lỗi đang lo ngại:

- Nếu lo sai công thức chiết khấu, cần chạy **quy tắc nghiệp vụ**.
- Nếu lo sai HTTP status, JSON hay validation, cần chạy **tầng web/MVC**.
- Nếu lo sai truy vấn, mapping JPA, constraint hoặc transaction, cần chạy **ứng dụng với cơ sở dữ liệu tương thích thực tế**.
- Nếu lo hai dịch vụ hiểu thông điệp khác nhau, cần xác minh **hợp đồng API/sự kiện** giữa các bên.
- Nếu lo một hành trình người dùng không hoàn thành sau triển khai, cần chạy **đường đi xuyên các thành phần liên quan**.

Một kiểm thử chỉ mạnh với điều nó thực sự quan sát. Ví dụ, unit test dùng repository mock không chứng minh SQL chạy đúng; HTTP test dùng service mock không chứng minh dữ liệu đã commit.

## 2. Các cấp kiểm thử thường gặp trong Spring Boot

| Cấp / kiểu | Thực thi và cô lập | Điều chứng minh tốt | Giới hạn thường gặp |
|---|---|---|---|
| **Unit** | Một hàm/lớp hoặc nhóm đối tượng nhỏ; không khởi động Spring context, thay thế I/O bằng stub/fake/mock khi cần | Nhánh logic, tính toán, trạng thái, điều kiện biên, xử lý lỗi | Không chứng minh bean wiring, serialization, transaction hay DB thật |
| **Web slice** | Chỉ một lát cắt MVC với **@WebMvcTest**, thường dùng **MockMvc**, mock các service bên dưới | Routing, request/response, validation, exception mapping và security filter được nạp trong slice | Không chứng minh service/repository thật hoặc toàn bộ cấu hình ứng dụng |
| **Persistence slice** | **@DataJpaTest** với entity, repository và JPA liên quan; có thể nối DB thật bằng Testcontainers | Mapping, query, constraint, lazy loading, tương tác JPA trong slice | Không tự chứng minh toàn luồng HTTP và logic giữa các tầng |
| **Integration** | Nhiều bean/thành phần thật, thường với **@SpringBootTest**, DB/message broker/HTTP stub được cấu hình rõ | Wiring, giao dịch, cấu hình, tương tác xuyên tầng, migration, xử lý lỗi tại biên | Chậm hơn, phụ thuộc môi trường, khó xác định nguyên nhân nếu scope quá rộng |
| **Contract** | Kiểm tra schema, yêu cầu và phản hồi, tương thích consumer/provider hoặc sự kiện | Hai bên có chung kỳ vọng về field, kiểu dữ liệu, mã lỗi và phiên bản | Không chứng minh provider đang sẵn sàng hoặc toàn hành trình sản phẩm thành công |
| **E2E** | Đi qua nhiều thành phần như người dùng thật hoặc API client ngoài tiến trình, có thể bao gồm trình duyệt | Hành trình quan trọng từ đầu đến cuối, cấu hình triển khai và kết nối thực tế trong môi trường kiểm thử | Đắt, chậm, dễ nhiễu; một happy path không bao phủ mọi nhánh logic |

**Chú ý:** “Slice” nói về *phần Spring context được nạp*, còn “integration” nói về *ranh giới tương tác được kiểm chứng*. Một **@DataJpaTest** chạy trên PostgreSQL thật là bài kiểm thử tích hợp ở ranh giới persistence dù chỉ nạp một slice. Vì vậy không thể xếp mọi annotation Spring Boot vào một thang cứng.

**Smoke**, regression, security, performance, resilience và load test mô tả mục tiêu kiểm tra, không phải một cấp cố định. Ví dụ, kiểm thử bảo mật có thể ở unit (policy), web slice (401/403) hoặc E2E (đăng nhập và phân quyền xuyên hệ thống).

## 3. Quy trình chọn cấp kiểm thử theo từng thay đổi

### Bước 1 — Viết phát biểu cần chứng minh

Tránh câu mơ hồ “API hoạt động”. Hãy viết điều kiện và quan sát được: “Với giỏ hàng đúng 500.000 VND, phí vận chuyển bằng 0”; “POST với payload thiếu trường bắt buộc trả 400”; “Khi thanh toán thất bại, đơn hàng không được đánh dấu đã trả tiền”.

Dạng **Given – When – Then** giúp nhận ra dữ liệu đầu vào, hành động và kết quả cần kiểm. Trong phần Then, dùng trạng thái quan sát được (giá trị trả về, bản ghi DB, sự kiện, HTTP status), đừng chỉ xác nhận một method mock đã được gọi trừ khi chính tương tác đó là yêu cầu.

### Bước 2 — Xác định lỗi có thể nằm ở biên nào

Tự hỏi: nếu cắt bỏ Spring, SQL, mạng hoặc trình duyệt thì vẫn có thể phát hiện lỗi cần bắt không? Nếu có, bắt đầu ở phạm vi hẹp hơn. Nếu lỗi phụ thuộc một ranh giới thật, phải đưa ranh giới ấy vào test. Chẳng hạn, unit test không thể chứng minh unique constraint ở DB; mock HTTP không thể phát hiện incompatibility của JSON ngoài đời.

### Bước 3 — Đánh giá mức ưu tiên bằng rủi ro

Chấm **xác suất** và **tác động** cho kịch bản, sau đó ưu tiên theo hậu quả và mức dễ xảy ra. Ví dụ minh họa, không phải điểm chuẩn bắt buộc:

| Kịch bản lỗi | Xác suất (1–5) | Tác động (1–5) | Ưu tiên minh họa | Bằng chứng nên có |
|---|---:|---:|---:|---|
| Tính sai phí vận chuyển ở ngưỡng | 4 | 3 | 12 | Unit test nhiều giá trị biên |
| Trùng ghi nhận thanh toán khi client retry | 3 | 5 | 15 | Integration với DB thật, idempotency và tình huống lặp |
| Đổi tên JSON field khiến client cũ lỗi | 3 | 4 | 12 | Contract + web/API test |
| Trang quản trị thiếu chặn quyền | 2 | 5 | 10 | Security web/integration + một hành trình phân quyền |
| Nút phụ bị lệch bố cục | 3 | 1 | 3 | UI/component test có mục tiêu, có thể kiểm tra thủ công |

Rủi ro cao **không đồng nghĩa** “phải viết thật nhiều E2E”. Rủi ro cao thường đòi hỏi nhiều lớp bằng chứng bổ trợ: nhiều case nhanh ở unit, ít case tích hợp tại biên nguy hiểm, và một số luồng E2E đại diện.

### Bước 4 — Chọn phép thử nhỏ nhất đủ phát hiện lỗi

| Muốn chứng minh | Ưu tiên khởi đầu | Khi cần nâng cấp phạm vi |
|---|---|---|
| Công thức, rule, biên số, quyết định nghiệp vụ | Unit | Khi rule còn phụ thuộc DB/transaction/config thực |
| Mapping URL, HTTP status, validation, JSON serialization | Web slice với MockMvc | Khi cần chứng minh security wiring hoặc service và DB thật |
| Custom query, entity mapping, ràng buộc dữ liệu | Persistence slice với DB tương thích production | Khi cần chứng minh transaction và nhiều service cùng tham gia |
| Transaction, retry, idempotency, outbox, migration | Integration với DB/broker thật hoặc Testcontainers | Khi cần xác minh hợp đồng giữa nhiều tiến trình |
| API hoặc event thay đổi nhưng phải tương thích client | Contract hai phía | Khi cần chứng minh deployment và kết nối thực tế |
| Người dùng đặt hàng từ đầu đến xác nhận | E2E cho vài hành trình trọng yếu | Bổ sung unit/integration cho các nhánh lỗi và edge case |

### Bước 5 — Chọn nơi chạy và điều kiện ổn định

Test unit và slice nhanh có thể chạy trên mỗi commit. Integration với Testcontainers nên chạy trong CI cho các thay đổi liên quan; E2E và kiểm thử tải chạy theo mức rủi ro, môi trường và thời gian phản hồi chấp nhận được. Khi lỗi kiểm thử không ổn định, hãy kiểm soát thời gian, dữ liệu test, transaction cleanup, thread và dependency thay vì chỉ tăng retry. Không đặt mục tiêu phần trăm số lượng unit/integration/E2E cứng cho mọi hệ thống.

## 4. Ví dụ xuyên suốt: tính phí và tạo đơn hàng

Giả sử hệ thống bán hàng có các yêu cầu sau:

1. Đơn từ **500.000 VND** được miễn phí giao hàng; thấp hơn phải trả **30.000 VND**. Tổng tiền âm không hợp lệ.
2. API tạo đơn từ chối payload thiếu thông tin bắt buộc với HTTP 400.
3. Hai yêu cầu thanh toán lặp cùng idempotency key không được ghi nhận hai lần.
4. Dịch vụ vận chuyển bên ngoài có thể thay đổi payload; ứng dụng vẫn phải tuân theo schema đã thỏa thuận.
5. Khách hàng có thể tạo đơn và xem trạng thái sau khi hệ thống triển khai.

Từ đây có năm câu hỏi khác nhau, nên có năm kiểu bằng chứng khác nhau. Viết một E2E bao trọn tất cả sẽ khó tái tạo từng biên và có thể không phát hiện lỗi ở một nhánh hiếm. Ngược lại, chỉ dùng unit test sẽ bỏ qua SQL, HTTP và tương thích giữa dịch vụ.

### 4.1. Unit test: bảo vệ business rule ở điểm biên

Ví dụ Java 17 + JUnit Jupiter dưới đây là **hai file đầy đủ**, đặt trong cùng package của một dự án Spring Boot đã có dependency **spring-boot-starter-test**.

File **src/main/java/com/example/orders/ShippingPolicy.java**:

```java
package com.example.orders;

public final class ShippingPolicy {
    public long feeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("subtotalVnd must be >= 0");
        }
        return subtotalVnd >= 500_000 ? 0 : 30_000;
    }
}
```

File **src/test/java/com/example/orders/ShippingPolicyTest.java**:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingPolicyTest {
    private final ShippingPolicy policy = new ShippingPolicy();

    @Test
    void justBelowThresholdPaysFee() {
        assertEquals(30_000, policy.feeVnd(499_999));
    }

    @Test
    void atThresholdIsFree() {
        assertEquals(0, policy.feeVnd(500_000));
    }

    @Test
    void aboveThresholdIsFree() {
        assertEquals(0, policy.feeVnd(500_001));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeVnd(-1));
    }
}
```

Chạy bằng Maven Wrapper tại thư mục gốc dự án:

```bash
./mvnw -Dtest=ShippingPolicyTest test
```

Trên Windows dùng **mvnw.cmd** thay cho **./mvnw**. Kỳ vọng: bốn bài test pass, không có stdout nghiệp vụ bắt buộc. Phần này không khởi động Spring context, không cần database; chạy nhanh và xác nhận đủ ba phía của ngưỡng cùng đầu vào bất hợp lệ.

**Nó chưa chứng minh** controller gọi đúng rule, JSON trả đúng tên field hay dữ liệu lưu thành công. Đó là công việc của các bài test khác.

### 4.2. Web slice: chứng minh giao diện HTTP

Với một **OrderController** có DTO dùng Jakarta Bean Validation, dùng **@WebMvcTest(OrderController.class)** và **MockMvc** để kiểm tra:

- Thiếu trường bắt buộc -> HTTP 400 với cấu trúc lỗi đã cam kết.
- Body hợp lệ -> routing, deserialize, validate và serialize đúng.
- Token/người dùng không đủ quyền -> 401 hoặc 403 theo cấu hình bảo mật đang áp dụng.

Trong slice, service thường được thay bằng mock; ở các phiên bản Spring Framework mới có **@MockitoBean**, còn một số dự án Spring Boot cũ dùng **@MockBean**. Tên annotation và import phải theo phiên bản Spring Boot của dự án. Nếu Spring Security được nạp, yêu cầu POST có thể còn cần CSRF token và authenticated principal trong test; bỏ qua chúng có thể làm test trả 401/403 trước khi tới validation.

Web slice kiểm tra “HTTP hoạt động như hợp đồng” nhưng **không chứng minh** repository thật đã ghi đơn. Vì thế không dùng kết quả MockMvc có service mock để kết luận transaction an toàn.

### 4.3. Persistence/integration: chứng minh tính nhất quán dữ liệu

Với việc ghi đơn hoặc thanh toán, sử dụng **@DataJpaTest** kết nối cơ sở dữ liệu giống production (chẳng hạn PostgreSQL qua Testcontainers), hoặc **@SpringBootTest** khi cần nhiều service/transaction thật. Các tình huống quan trọng:

- Idempotency key trùng lần thứ hai không sinh thêm bản ghi thanh toán.
- Hai request đồng thời không phá unique constraint và không phát sinh trạng thái thanh toán sai.
- Lỗi xảy ra giữa các bước khiến transaction rollback đúng yêu cầu.
- Migration/schema thực tế hỗ trợ query, index và constraint; không dùng H2 để kết luận mọi hành vi PostgreSQL cũng giống hệt.

Dùng Testcontainers khi logic phụ thuộc dialect, transaction isolation, locking hoặc lỗi của hệ quản trị DB. Test phải tự tạo dữ liệu rõ ràng, cách ly trạng thái và dọn dẹp có kiểm soát. Với race condition, cần điều phối đồng thời có chủ đích và assert trạng thái cuối; test tuần tự không chứng minh an toàn đồng thời.

### 4.4. Contract: chứng minh tương thích giữa hệ thống

Khi dịch vụ vận chuyển nhận JSON, hãy đặc tả field bắt buộc/tùy chọn, kiểu dữ liệu, mã trạng thái, lỗi và tương thích version. Consumer contract test xác nhận ứng dụng tạo/đọc đúng các tương tác mà client thật sử dụng; provider verification cần chạy trên provider hoặc artifact tương ứng. Chỉ mock một phản hồi “đẹp” trong unit test **không** chứng minh nhà cung cấp hiện tại còn tuân thủ hợp đồng.

Với Kafka/RabbitMQ, contract gồm cả key, schema, version, ý nghĩa nghiệp vụ và khả năng xử lý message trùng. Contract kiểm tra tính tương thích; integration kiểm tra broker/serialization thực tế và hành vi retry.

### 4.5. E2E: chứng minh hành trình sản phẩm

Giữ ít E2E nhưng chọn hành trình quan trọng: người dùng hợp lệ đăng nhập, tạo đơn, thanh toán bằng sandbox an toàn, rồi nhìn thấy trạng thái đã xác nhận. Nên có thêm một hành trình từ chối quyền nếu hậu quả bảo mật lớn. Chỉ khẳng định những gì môi trường E2E thực sự chạy: nếu gateway thanh toán được stub, test không chứng minh giao dịch thật ở nhà cung cấp.

E2E cần dữ liệu có thể tạo lại, đồng hồ/timeout hợp lý, quan sát log/tracing và dọn dẹp; tránh phụ thuộc thứ tự test hay chờ bằng thời gian sleep cố định. Khi E2E lỗi, bài unit/integration nhỏ giúp tìm nhanh nơi hỏng.

## 5. Thiết kế bộ kiểm thử theo “lớp bằng chứng”

Với rủi ro thanh toán trùng, một bộ kiểm thử có chiều sâu có thể gồm:

| Lớp bằng chứng | Ví dụ assert cụ thể | Điều kiện cần |
|---|---|---|
| Unit | Cùng idempotency key trả quyết định không tạo charge mới theo rule | Không cần Spring context |
| Web/API | Request thiếu key bị từ chối theo contract, response mã lỗi đúng | MVC/security/filter thích hợp |
| DB integration | Ghi hai lần hoặc đồng thời chỉ có một giao dịch thành công và trạng thái hợp lệ | DB thật, constraint và transaction thật |
| Contract | Client/provider cùng hiểu key, status và error response | Contract kiểm tra hai phía |
| E2E đại diện | Retry sau timeout không làm người dùng bị trừ tiền hai lần trong sandbox có hỗ trợ | Luồng deploy/test environment thích hợp |

Bảng này **không** có nghĩa mọi thay đổi đều phải viết đủ năm lớp. Quy tắc chọn là: mỗi lỗi nghiêm trọng phải có ít nhất một phép thử có khả năng phát hiện nó ở đúng biên; bổ sung lớp khác khi rủi ro còn chưa được chứng minh hoặc cần phát hiện hồi quy ở bề mặt khác.

## 6. Lập kế hoạch thực thi trong CI

- **Trong quá trình sửa code / pull request:** chạy unit và slice liên quan để phản hồi nhanh; giữ các test ngắn, độc lập và xác định.
- **Trước khi merge hoặc trong CI:** chạy integration có DB/broker thật cho những module có tác động tới schema, transaction, retry, bảo mật và hợp đồng; contract test khi có giao tiếp liên dịch vụ.
- **Trước hoặc ngay sau triển khai:** smoke các endpoint và hành trình cốt lõi trong môi trường triển khai để bắt cấu hình, migration, routing và dependency lỗi.
- **Theo lịch hoặc khi thay đổi rủi ro cao:** chạy E2E diện rộng, tải, an ninh và phục hồi theo mục tiêu riêng; kết quả phải có người xử lý khi thất bại.

Chiến lược này có thể thay đổi theo tốc độ pipeline và mức độ quan trọng. Ví dụ, ứng dụng thanh toán có thể bắt buộc integration cho mọi pull request; thư viện tính toán thuần có thể chủ yếu dùng unit. Đừng mặc định một tỉ lệ test pyramid là tiêu chuẩn chất lượng.

## 7. Các lỗi lựa chọn cấp kiểm thử thường gặp

1. **Đồng nhất “nhiều test” với “đủ bằng chứng”.** Hàng trăm unit test không thay thế được một test xác nhận transaction hoặc authorization.
2. **Dùng mock ở chính ranh giới cần kiểm.** Nếu đang sợ SQL sai, mock repository sẽ che lỗi; nếu sợ HTTP contract sai, mock luôn HTTP thì không có bằng chứng.
3. **Dùng @SpringBootTest cho mọi rule đơn giản.** Context lớn khiến suite chậm và khó phân tích; dùng unit cho phần thuần logic, mở rộng phạm vi khi có lý do.
4. **Tin rằng slice luôn giống production.** Bean, filter, property hoặc DB có thể bị loại khỏi test slice; cần đọc cấu hình thực tế để biết test đang chạy gì.
5. **Dùng embedded DB khác production cho tính năng phụ thuộc SQL.** H2 có thể khác PostgreSQL về syntax, isolation, constraint và kiểu dữ liệu; chọn DB đúng khi đó là nguồn rủi ro.
6. **Viết E2E quá nhiều nhánh chi tiết.** Dễ flaky và chậm; đặt edge case của rule vào unit, database conflict vào integration, giữ E2E cho journey.
7. **Chỉ dựa vào code coverage.** Coverage đo code được chạy, không đảm bảo assertion đủ mạnh hoặc boundary đúng; nên xem thêm failure modes, mutation testing (khi phù hợp) và giá trị của assertion.
8. **Bỏ qua timeout, retry, time zone và concurrency.** Các lỗi đó thường cần fake clock, contract rõ, container hoặc integration với lịch chạy có kiểm soát.
9. **Không làm rõ trách nhiệm của test.** Một test fail nhưng không ai biết tính năng nào bị phá chứng tỏ tên, dữ liệu và assertion chưa đủ cụ thể.

## 8. Checklist chọn cấp kiểm thử trước khi viết test

- [ ] Đã viết một phát biểu **Given – When – Then** về hành vi phải đúng, có expected result quan sát được.
- [ ] Đã nêu hậu quả nếu sai và xác định biên phát sinh lỗi (logic, HTTP, DB, service, deployment).
- [ ] Đã chọn phạm vi nhỏ nhất có thể **thật sự phát hiện** lỗi này.
- [ ] Với ranh giới rủi ro cao, đã xác định điểm cần dùng dependency thật, Testcontainers, contract hoặc E2E bổ sung.
- [ ] Đã kiểm tra mock/stub không che mất hành vi cần chứng minh.
- [ ] Đã biết test đang dùng những bean/filter/config/DB nào, và những phần nào chưa được chạy.
- [ ] Đầu vào, thời gian, dữ liệu, dependency và dọn dẹp đủ ổn định để test lặp lại đáng tin.
- [ ] Đã đặt test vào nhịp CI phù hợp và biết ai xử lý khi nó thất bại.

**Nguyên tắc ghi nhớ:** chọn test bằng **mệnh đề cần chứng minh và nơi lỗi có thể xuất hiện**, rồi dùng **rủi ro để quyết định độ sâu, số tình huống và thời điểm chạy**. Một bộ kiểm thử tốt có thể giải thích chính xác mỗi test bảo vệ điều gì và điều gì vẫn chưa được chứng minh.
