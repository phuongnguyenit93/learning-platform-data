# Vòng lặp TDD và lựa chọn điểm áp dụng trong Spring Boot

**Test-Driven Development (TDD)** là cách phát triển phần mềm theo những vòng phản hồi nhỏ: **viết một test mô tả hành vi mong muốn, quan sát test thất bại vì hành vi ấy chưa được đáp ứng, viết lượng mã tối thiểu để test qua, rồi cải thiện thiết kế khi test vẫn xanh**. Trong một dự án Spring Boot, quyết định quan trọng không chỉ là có dùng TDD hay không mà còn là **bắt đầu ở ranh giới nào**: logic thuần, service, HTTP, persistence hay luồng tích hợp.

TDD là chiến lược thiết kế và phản hồi. Nó không tự bảo đảm yêu cầu đúng, thay thế code review hoặc chứng minh tất cả thành phần ngoài ứng dụng hoạt động. Giá trị của TDD đến từ việc nhà phát triển có một ví dụ hành vi kiểm chứng được *trước khi* triển khai, và liên tục dùng test để phát hiện sai lệch.

## 1. Red – Green – Refactor là một vòng lặp, không phải ba giai đoạn lớn

| Pha | Việc cần làm | Tín hiệu để chuyển pha |
| --- | --- | --- |
| **Red** | Chọn **một hành vi** kế tiếp; viết test với input và kết quả quan sát được; chạy test | Test chạy được và **fail đúng lý do**: hành vi mục tiêu chưa có hoặc chưa đúng |
| **Green** | Thực hiện thay đổi nhỏ nhất đủ cho test mới và các test liên quan cùng pass | Test mới xanh, các test cũ liên quan vẫn xanh |
| **Refactor** | Loại lặp, cải thiện tên, tách trách nhiệm hoặc cấu trúc mà **không đổi hành vi** | Bộ test vẫn xanh; thiết kế dễ hiểu hơn |

Một vòng có thể kéo dài vài phút; không cần đặt mục tiêu mọi vòng đều đúng một phút. Tốc độ phù hợp là tốc độ giúp ta nhận biết chính xác **thay đổi nào** làm test chuyển đỏ/xanh.

### Red cần “đỏ có ý nghĩa”

- Test trước tiên phải mô tả một **kết quả công khai**: giá trị trả về, exception, trạng thái lưu trữ, status/body HTTP, event hay hành động gửi tới dependency.
- Thất bại vì assertion mong đợi không khớp thực tế là tín hiệu rõ nhất. Lúc đang định nghĩa API, một lỗi biên dịch tạm thời có thể xuất hiện; hãy đưa code về trạng thái biên dịch được để xác nhận bài test thực sự phát hiện thiếu hành vi.
- Nếu test fail vì container không chạy, secret thiếu, hostname sai, chưa seed database hoặc test khác làm bẩn trạng thái, đó là lỗi môi trường/test setup; **không lấy nó làm bằng chứng Red thành công**.
- Có thể cố tình thay một giá trị kỳ vọng để kiểm tra assertion đủ nhạy, nhưng không để test bị sửa sai và tiếp tục xanh.

### Green cố ý tối thiểu

Trong Green, việc trả hằng số hay thêm một điều kiện đơn giản đôi khi hoàn toàn hợp lý. Một test đơn lẻ thường chỉ đủ yêu cầu cho một trường hợp. **Test tiếp theo** buộc thiết kế tổng quát hóa. Không triển khai sẵn nhiều nhánh chưa có yêu cầu/test để “tiết kiệm vòng”, bởi như vậy mất phản hồi từng bước.

### Refactor không bổ sung nghiệp vụ

Refactor được làm sau khi xanh; đổi tên biến, rút hằng số, làm rõ ranh giới phụ thuộc hoặc bỏ code trùng. Nếu muốn thay đổi kết quả với đầu vào mới, hãy viết test **Red** mới. Đừng trộn một thay đổi nghiệp vụ lớn với refactor khiến khi test đỏ không biết nguyên nhân.

**Một chu kỳ hoàn chỉnh:**

```text
Chọn hành vi nhỏ
       ↓
Viết test mới → RED (fail đúng lý do)
       ↓
Viết mã tối thiểu → GREEN (các test liên quan pass)
       ↓
Refactor → chạy test lại (vẫn GREEN)
       ↓
Chọn hành vi kế tiếp
```

TDD khác với việc triển khai trước rồi viết nhiều test để tăng coverage sau cùng: test viết sau vẫn có thể hữu ích, nhưng không cung cấp cùng phản hồi về API và thiết kế *trước khi* code hình thành.

## 2. Chọn hành vi nhỏ trước khi chọn annotation kiểm thử

Trước mỗi vòng, hãy trả lời ngắn gọn:

1. **Hành vi:** “Khi [điều kiện], hệ thống phải [kết quả quan sát được]”.
2. **Ranh giới:** logic nào phải chạy thật để khẳng định kết quả?
3. **Tín hiệu Red:** cụ thể bài test sẽ fail ra sao nếu chưa có hành vi?
4. **Chi phí chạy:** có cần Spring context, HTTP, database, broker hoặc hệ thống ngoài không?
5. **Bước nhỏ nhất:** điều kiện/edge case nào đủ cho đúng **một** vòng?

Ví dụ với phí vận chuyển: “Khi tổng tiền hàng từ 500.000 VND trở lên, phí vận chuyển là 0 VND”. Đây là quy tắc tính toán, nên bắt đầu với một class Java thật và JUnit thuần. Chưa có lý do phải khởi tạo web server hay truy cập DB.

Ngược lại, “Khi người dùng gửi JSON sai cấu trúc, endpoint trả 400 với body chuẩn” là hợp đồng HTTP. Nếu chỉ test method Java trực tiếp, ta bỏ qua cơ chế parse, binding, validation và exception mapping của Spring. Hành vi đó cần một test web slice/integration phù hợp.

**Không nhất thiết bắt đầu TDD ở controller** chỉ vì người dùng gọi ứng dụng qua REST. Điểm bắt đầu là nơi có thể quan sát đúng hành vi với ranh giới nhỏ và phản hồi đáng tin nhất.

## 3. Ví dụ TDD đầy đủ: chính sách phí vận chuyển

**Yêu cầu nghiệp vụ được thống nhất cho ví dụ:**

- Tổng tiền hàng không âm và nhỏ hơn `500_000` VND: phí `30_000` VND.
- Tổng tiền hàng từ `500_000` VND trở lên: miễn phí vận chuyển (`0` VND).
- Tổng tiền âm: từ chối bằng `IllegalArgumentException`.

Ta tách phép tính này vào `ShippingFeePolicy`, dùng `long` biểu diễn VND nguyên để không đưa sai số dấu phẩy động vào ví dụ. Quy tắc trong ví dụ không cần database, HTTP, Spring bean hay Mockito.

Giả sử project Spring Boot đã cấu hình Gradle và Java 17+. Các file:

```text
src/
├── main/java/example/testing/shipping/ShippingFeePolicy.java
└── test/java/example/testing/shipping/ShippingFeePolicyTest.java
```

Trong dự án Gradle Spring Boot đã có plugin/phiên bản phụ thuộc thích hợp, test cần JUnit Jupiter qua `spring-boot-starter-test`. Phần khai báo liên quan trong `build.gradle` (Groovy DSL) là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đoạn cấu hình này là **phần trích** bổ sung vào dự án Spring Boot đã thiết lập plugin và dependency management/BOM; nó không phải một `build.gradle` độc lập.

### Vòng 1: đúng ngưỡng thì miễn phí

**Red — viết một test trước:**

Tạo `src/test/java/example/testing/shipping/ShippingFeePolicyTest.java`:

```java
package example.testing.shipping;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ShippingFeePolicyTest {
    @Test
    void subtotalAtThresholdHasFreeShipping() {
        ShippingFeePolicy policy = new ShippingFeePolicy();
        assertEquals(0L, policy.feeFor(500_000L));
    }
}
```

Để nhìn thấy assertion fail thay vì dừng ở lỗi thiếu class, tạo khung mã tối thiểu tại `src/main/java/example/testing/shipping/ShippingFeePolicy.java`:

```java
package example.testing.shipping;

public final class ShippingFeePolicy {
    public long feeFor(long subtotalVnd) {
        return -1L; // Chưa thực hiện chính sách
    }
}
```

Chạy:

```bash
./gradlew test --tests example.testing.shipping.ShippingFeePolicyTest
```

Bài test Red vì `expected: 0` và `actual: -1`; ta chưa có hành vi miễn phí ở ngưỡng. Không cần xem độ dài toàn bộ stack trace để nhận biết chính xác nguyên nhân.

**Green — thay duy nhất phần còn thiếu:**

```java
public long feeFor(long subtotalVnd) {
    return 0L;
}
```

Chạy lại test: ca hiện tại pass. Việc trả hằng số **chưa phải chính sách đầy đủ**, nhưng đúng với ca duy nhất hiện có. Đừng tự thêm logic tính phí khác trước vòng kế tiếp.

### Vòng 2: thấp hơn ngưỡng phải thu phí

**Red — thêm một test** vào class test:

```java
@Test
void subtotalJustBelowThresholdHasStandardFee() {
    ShippingFeePolicy policy = new ShippingFeePolicy();
    assertEquals(30_000L, policy.feeFor(499_999L));
}
```

Test mới fail vì bản Green cũ luôn trả `0`. Test tại `499_999` đặc biệt hữu ích vì bắt lỗi sử dụng nhầm `>` thay vì `>=` tại ranh giới.

**Green — tổng quát hóa đúng hai trường hợp:**

```java
public long feeFor(long subtotalVnd) {
    return subtotalVnd >= 500_000L ? 0L : 30_000L;
}
```

Chạy cả hai test; nếu xanh, điều kiện ngưỡng hiện đã được kiểm chứng theo hai phía.

### Vòng 3: dữ liệu âm không hợp lệ

**Red — thêm test**:

```java
@Test
void negativeSubtotalIsRejected() {
    ShippingFeePolicy policy = new ShippingFeePolicy();

    assertThrows(
            IllegalArgumentException.class,
            () -> policy.feeFor(-1L)
    );
}
```

Với code hiện tại, method trả `30_000` mà không ném exception; test mới fail vì không có `IllegalArgumentException`. Thêm static import `org.junit.jupiter.api.Assertions.assertThrows` vào class test.

**Green — thêm kiểm tra đầu vào:**

```java
public long feeFor(long subtotalVnd) {
    if (subtotalVnd < 0L) {
        throw new IllegalArgumentException("subtotalVnd must be >= 0");
    }
    return subtotalVnd >= 500_000L ? 0L : 30_000L;
}
```

Chạy tất cả test vừa tạo. Các ca cũ cần tiếp tục xanh, vì quy tắc từ chối số âm không được làm thay đổi hành vi của dữ liệu hợp lệ.

### Refactor khi đã xanh

Rút các con số có nghĩa nghiệp vụ thành hằng số, giữ nguyên API và kết quả:

**Phiên bản cuối:** `src/main/java/example/testing/shipping/ShippingFeePolicy.java`

```java
package example.testing.shipping;

public final class ShippingFeePolicy {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    public long feeFor(long subtotalVnd) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotalVnd must be >= 0");
        }
        return subtotalVnd >= FREE_THRESHOLD_VND
                ? 0L
                : STANDARD_FEE_VND;
    }
}
```

**Bộ test hoàn chỉnh:** `src/test/java/example/testing/shipping/ShippingFeePolicyTest.java`

```java
package example.testing.shipping;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void subtotalAtThresholdHasFreeShipping() {
        assertEquals(0L, policy.feeFor(500_000L));
    }

    @Test
    void subtotalJustBelowThresholdHasStandardFee() {
        assertEquals(30_000L, policy.feeFor(499_999L));
    }

    @Test
    void subtotalAboveThresholdStillHasFreeShipping() {
        assertEquals(0L, policy.feeFor(750_000L));
    }

    @Test
    void negativeSubtotalIsRejected() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> policy.feeFor(-1L));
        assertEquals("subtotalVnd must be >= 0", error.getMessage());
    }
}
```

Ở bản hoàn chỉnh có bốn test: đúng ngưỡng, ngay dưới ngưỡng, vượt ngưỡng và dữ liệu âm. Chạy từ thư mục có Gradle wrapper:

```bash
./gradlew test --tests example.testing.shipping.ShippingFeePolicyTest
```

Trên Windows:

```powershell
.\gradlew.bat test --tests "example.testing.shipping.ShippingFeePolicyTest"
```

**Kỳ vọng:** cả bốn bài test pass với project có Java và dependencies được cấu hình như trên. Gradle/JUnit không có một stdout cố định chung: cách hiển thị tên test, task, báo cáo và summary phụ thuộc cấu hình project/runner; có thể xem báo cáo test của Gradle để xác nhận từng test.

Có thể chạy **phần tính toán thuần Java** bằng `javac/java` để kiểm chứng kết quả ngay cả khi không chạy JUnit. Tạo file độc lập với bộ test `src/main/java/example/testing/shipping/ShippingFeeDemo.java`:

```java
package example.testing.shipping;

public class ShippingFeeDemo {
    public static void main(String[] args) {
        ShippingFeePolicy policy = new ShippingFeePolicy();
        System.out.println(policy.feeFor(499_999L));
        System.out.println(policy.feeFor(500_000L));
    }
}
```

Từ thư mục project:

```bash
javac -d out src/main/java/example/testing/shipping/ShippingFeePolicy.java src/main/java/example/testing/shipping/ShippingFeeDemo.java
java -cp out example.testing.shipping.ShippingFeeDemo
```

Stdout chính xác:

```text
30000
0
```

Chương trình `main` chỉ minh họa kết quả, **không thay thế test JUnit** hay các bước Red–Green–Refactor. Lợi ích chính của TDD là mỗi yêu cầu mới trở thành test có khả năng phát hiện hồi quy.

### Điều ví dụ chứng minh và chưa chứng minh

Ví dụ chứng minh chính sách tính phí thuần và đầu vào âm. Nó **chưa** chứng minh JSON của endpoint đúng, Spring inject bean đúng, phí được ghi vào DB hoặc transaction rollback. Những hợp đồng đó cần test ở ranh giới rộng hơn nếu chúng là yêu cầu của ứng dụng.

## 4. Điểm áp dụng TDD trong các lớp của Spring Boot

Khi bắt đầu tính năng mới, hãy đặt test ở **lớp hẹp nhất đủ thật** để kiểm chứng hành vi:

| Vị trí cần áp dụng | Chọn test Red đầu tiên | Vì sao phù hợp | Khi nào mở rộng? |
| --- | --- | --- | --- |
| Quy tắc nghiệp vụ, tính toán, parser thuần | JUnit test với class thật, không Spring context | Vòng nhanh, lỗi tập trung, API thiết kế rõ | Khi nghiệp vụ được gọi qua HTTP, persistence, event |
| Application service/orchestration | Service thật với collaborator được điều khiển bằng stub/mock/fake | Kiểm tra quyết định và lệnh gửi ra mà không phụ thuộc môi trường | Khi cần chứng minh wiring, transaction, repository hay HTTP client |
| Controller Spring MVC | `@WebMvcTest` với `MockMvc` | Thử routing, binding, validation, status, JSON ở MVC layer | Khi cần filter/security thực hoặc liên thông DB |
| Controller Spring WebFlux | `@WebFluxTest` với `WebTestClient` | Thử HTTP contract của stack reactive và mã response | Khi cần luồng reactive, security, network hay hạ tầng tích hợp rộng hơn |
| Spring Data JPA/repository | `@DataJpaTest` với DB kiểm thử | Query, mapping, constraint là điều phải chạy thật | Khi phụ thuộc dialect, migration hoặc transaction qua nhiều bean |
| Spring config, AOP, transaction, method security | Spring context/integration test phù hợp | Annotation và proxy chỉ có ý nghĩa khi framework thực sự chạy | Khi cần HTTP thật, nhiều adapter, database/broker |
| Luồng end-to-end giữa các thành phần | `@SpringBootTest` và hạ tầng kiểm thử thích hợp | Chứng minh kết nối giữa các lớp và cấu hình | Khi cần kiểm chứng toàn hệ thống/môi trường phát hành |

Một tính năng có thể dùng **nhiều điểm áp dụng**. Ví dụ chính sách phí vận chuyển có test JUnit cho phép tính, MVC test cho status/JSON, persistence test cho dữ liệu lưu và một integration test cho đường đi quan trọng nhất. Không nên cố dùng một test end-to-end duy nhất để thay mọi mức kiểm thử; khi fail sẽ khó định vị và vòng TDD chậm.

### Logic miền nghiệp vụ: thường là nơi bắt đầu hiệu quả nhất

Nếu hành vi có nhiều trường hợp biên, quyết định, tổ hợp điều kiện hoặc biến đổi dữ liệu, TDD ở domain giúp thiết kế interface gọn: input, output và exception có nghĩa. Ưu tiên constructor injection khi service cần collaborator; đưa clock, random và I/O ra ranh giới rõ để test có tính quyết định.

Một rule như “mức chiết khấu thay đổi theo hạng khách hàng” thường nên được kiểm tra bằng test thuần trước. Không cần tạo Spring container để test một câu `if` hoặc hàm tính toán. Test rõ nghiệp vụ giúp việc thay transport từ MVC sang messaging không kéo theo thay đổi test của domain.

### Service: phù hợp khi hành vi là phối hợp

Ví dụ “nếu kho báo hết hàng, từ chối đặt hàng và không tạo lệnh lưu”. SUT là service thật; stub kết quả của cổng kho, quan sát exception hoặc kết quả và xác minh không gửi lệnh lưu. Vòng TDD có thể lần lượt bổ sung thành công, hết hàng, timeout và idempotency.

Tuy nhiên, `verify(store).save(order)` chỉ xác nhận service **yêu cầu** lưu, chưa chứng minh transaction commit, SQL constraint hay DB thật có dữ liệu. Nếu yêu cầu nằm ở DB, test phải dịch đến ranh giới database.

### HTTP endpoint: khi hợp đồng bên ngoài là mục tiêu

Ví dụ “`GET /shipping/fee?subtotalVnd=500000` trả HTTP 200 và JSON có `feeVnd=0`”. Với Spring MVC, vòng Red có thể bắt đầu từ một request qua `MockMvc`:

```java
mockMvc.perform(get("/shipping/fee")
        .param("subtotalVnd", "500000"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.feeVnd").value(0));
```

Đây là **đoạn minh họa bên trong một method test**, không phải class chạy độc lập. Nó đòi các static import của `MockMvcRequestBuilders.get` và `MockMvcResultMatchers`, bean/controller phù hợp và một `MockMvc` do Spring test cung cấp. Với `@WebMvcTest`, cung cấp collaborator của controller qua cấu hình test hoặc bean mock tương thích phiên bản Spring Boot đang dùng.

Trong Red, test có thể thất bại vì route chưa có hoặc JSON chưa đúng; hãy bảo đảm test context và mock collaborator đã hoạt động trước khi kết luận. Green chỉ cần triển khai endpoint, sau đó thêm vòng riêng cho `400` khi query param sai, lỗi xác thực, headers và validation theo hợp đồng. Gọi trực tiếp `controller.getFee(...)` sẽ không kiểm tra Spring HTTP binding.

**Phạm vi slice quan trọng:** `@WebMvcTest` tập trung vào MVC infrastructure, không tự chứng minh database, messaging và mọi service layer. Nếu Spring Security nằm trên classpath, MVC test có thể còn đi qua security filter; cần cấp authentication hoặc cấu hình filter test đúng với hành vi đang kiểm tra. Đừng tắt security chỉ để ép test xanh khi access control là yêu cầu.

### Persistence: dùng test có database khi yêu cầu nói về database

Với “truy vấn lấy đơn đã thanh toán theo thời gian tăng dần”, Red là test repository có dữ liệu seed và assertion về thứ tự kết quả. Fake repository trong `Map` không chứng minh câu SQL hay cách Spring Data ánh xạ entity.

`@DataJpaTest` hữu ích cho repository JPA. Chọn DB sao cho bằng chứng phù hợp: H2 có thể đủ cho truy vấn chuẩn trong một số dự án, nhưng kiểm tra JSONB, SQL dialect, index, constraint hoặc migration riêng PostgreSQL/MySQL thì nên dùng đúng DB engine (chẳng hạn Testcontainers). Test slice thường chạy trong transaction được rollback sau test; nếu phải chứng minh commit và transaction interaction, cần test tích hợp phù hợp hơn.

### Framework và hạ tầng: mở rộng vòng có chủ đích

Các tính năng dựa vào Spring proxy như `@Transactional`, `@Cacheable` và method security không được chứng minh khi ta chỉ gọi trực tiếp object dựng bằng `new`. TDD ở đây có thể bắt đầu bằng integration test nhỏ tại boundary liên quan; Green thay đổi config/annotation/application code rồi refactor. Vòng sẽ chậm hơn vì có context; tránh đưa toàn bộ bài test đơn giản vào `@SpringBootTest` chỉ để đồng nhất công cụ.

## 5. Quy trình chọn điểm áp dụng cho một feature thực tế

Xét yêu cầu: “Đặt đơn thành công nếu hàng còn, phí đúng, và người dùng có quyền; không tạo đơn nếu kho hết hàng”.

**Bước 1 — chia theo điều có thể quan sát, không chia tùy tiện theo lớp code.**

- Phí vận chuyển đúng tại các ngưỡng → domain unit TDD.
- Kho hết hàng khiến service không yêu cầu lưu đơn → service unit TDD.
- Request thiếu dữ liệu được ánh xạ thành HTTP 400 → MVC slice TDD.
- Người không có quyền bị từ chối theo security chain → security/MVC integration test.
- Đơn được lưu đúng với transaction/constraint → persistence hoặc integration test.

**Bước 2 — chọn vòng có mức phản hồi nhanh nhất cho thay đổi đang thực hiện.** Nếu mới sửa phép tính phí, chạy test policy trước. Khi sửa endpoint contract, chạy MVC test có liên quan. Khi sửa transaction, dùng DB test. Sau các vòng hẹp, chạy các test cấp cao đủ đại diện để phát hiện lỗi kết nối.

**Bước 3 — giữ cùng một định nghĩa thành công tại các ranh giới.** Unit test chứng minh quy tắc, slice test chứng minh chuyển đổi đầu vào/đầu ra, integration test chứng minh các thành phần làm việc cùng nhau. Không suy diễn “test service xanh” thành “toàn bộ REST API đúng”.

**Bước 4 — tái sử dụng test khi refactor.** Nếu tách `ShippingFeePolicy` khỏi service, kết quả đối với các trường hợp đã mô tả không đổi; chạy lại test ở cả policy và ranh giới bao quanh nếu refactor thay wiring.

Một bảng tự hỏi trước khi viết test đầu tiên:

| Câu hỏi | Nếu trả lời “có” |
| --- | --- |
| Hành vi chỉ phụ thuộc input thuần và thuật toán? | Bắt đầu bằng JUnit thuần |
| Cần điều khiển phản hồi từ collaborator nhưng không kiểm tra adapter thật? | Dùng service thật + test double |
| Cần biết `@RequestBody`, `@Valid`, status, JSON hay route chạy đúng? | Bắt đầu tại web slice |
| Cần xác nhận query/mapping/constraint? | Chạy repository với DB kiểm thử |
| Cần xác nhận security filter, proxy, bean wiring, transaction thực? | Dùng Spring context phù hợp |
| Cần chứng minh luồng qua nhiều service hoặc hạ tầng? | Bổ sung integration/contract test, giới hạn số vòng chậm |

## 6. TDD với dependency bên ngoài và tính không ổn định

TDD mất tác dụng nếu mỗi lần chạy phụ thuộc vào mạng, database dùng chung, đồng hồ hệ thống hay thứ tự test. Hãy phân biệt **quyết định của ứng dụng** và **hành vi giao thức của adapter**.

Với payment client:

1. Ở service, Red mô tả “cổng thanh toán trả timeout thì không đánh dấu đơn đã thanh toán”; mock/stub cổng thanh toán trả lỗi có chủ đích. Green là nhánh xử lý nghiệp vụ tối thiểu.
2. Ở HTTP adapter, Red mô tả “HTTP 504 phải được chuyển thành lỗi timeout của cổng thanh toán”; dùng mock HTTP server hoặc test tích hợp có phản hồi được điều khiển. Green là mapping HTTP chính xác.
3. Ở cấp integration, bổ sung test xác minh transaction, event hoặc trạng thái cuối nếu đây là cam kết của hệ thống.

Mỗi lớp có câu hỏi riêng. Nếu mock chính đoạn code cần chứng minh (ví dụ mock `PaymentHttpClient` rồi kết luận serialization của client đúng), test có thể xanh vô nghĩa.

Khi xử lý thời gian, inject `Clock` rồi dùng `Clock.fixed(...)` trong unit test. Khi xử lý tác vụ bất đồng bộ, đợi điều kiện quan sát được qua future, event/test probe hoặc công cụ chuyên dụng có timeout có giới hạn; tránh `Thread.sleep(...)` với thời lượng tùy ý.

Với database integration, cô lập dữ liệu bằng transaction/cleanup có kiểm soát và tránh test phụ thuộc thứ tự chạy. Đối với broker/cache, cân nhắc container riêng hoặc stub hợp đồng ở test hẹp, rồi có một số test rộng thực sự chạy adapter.

## 7. TDD khi chỉnh sửa hệ thống cũ

Không phải codebase nào cũng có cấu trúc dễ test. Khi sửa hành vi cũ có ít hoặc không có test, cần phân biệt hai mục tiêu:

- **Characterization test:** ghi lại hành vi đang tồn tại để bảo vệ phần không định thay đổi. Một hành vi hiện tại có thể sai về nghiệp vụ; characterization test chỉ mô tả thực tế, không chứng minh nó là yêu cầu đúng.
- **Test mới cho yêu cầu:** mô tả hành vi mong muốn *sau thay đổi*; phải Red vì code cũ chưa đáp ứng. Sau đó Green và Refactor.

Ví dụ một service có method dài vừa tính phí vừa gọi database. Trước khi thay công thức, thêm test quan sát các trường hợp cũ cần giữ. Khi có bằng chứng hồi quy, tách phần phép tính ra dependency/class thuần và bắt đầu vòng TDD cho chính sách mới. Đừng refactor đồng thời cả transaction, HTTP contract và nghiệp vụ nếu không có test phân biệt các thay đổi đó.

Nếu test đầu tiên chỉ viết được bằng `@SpringBootTest` nặng và chậm, có thể dùng một vài integration tests tạm thời làm lưới an toàn, sau đó mở đường cho unit tests ở phần logic được tách rõ. Điều quan trọng là **không làm mất hành vi đã được chứng minh** trong lúc cải thiện khả năng kiểm thử.

## 8. Chọn mức độ TDD hợp lý và tổ chức phản hồi

TDD hữu ích nhất khi yêu cầu có **quy tắc cụ thể, nhiều nhánh, dữ liệu biên hoặc thay đổi thường xuyên**: tính giá, phân quyền miền nghiệp vụ, validation, state transitions, idempotency, xử lý ngoại lệ, ánh xạ dữ liệu và HTTP contract. Khi khám phá một giao diện chưa rõ yêu cầu, thử nghiệm framework mới hoặc spike nghiên cứu, có thể cần một đoạn prototype ngắn để hiểu API; sau khi hành vi được làm rõ, chuyển sang vòng test-first cho phần mã sẽ duy trì.

Đừng lấy số test hay phần trăm coverage làm mục tiêu độc lập. Coverage có thể cho thấy đoạn code nào được thực thi, nhưng **không nói assertion có ý nghĩa hay đã chọn đúng trường hợp biên hay chưa**. Một test đúng ngưỡng `500_000` có thể bắt bug `>`/`>=` tốt hơn nhiều test với giá trị tùy ý.

Vòng chạy nên chia theo tốc độ phản hồi:

- **Local/commit nhanh:** JUnit thuần, service unit test, các web slice liên quan đến thay đổi.
- **Bước kiểm tra tích hợp:** repository test, transaction/security test, API/adapter contract test.
- **Pipeline đầy đủ:** test qua nhiều thành phần, container database/broker và những kiểm tra hồi quy quan trọng trước merge/phát hành.

Sự phân chia này không buộc mọi nhóm dùng đúng ba tầng CI. Hãy giữ các test có **chi phí và mục tiêu tương đồng** ở cùng tầng, để một vòng Red–Green–Refactor vẫn chạy nhanh mà phát hành không bỏ sót rủi ro tích hợp.

## 9. Lỗi phổ biến trong TDD Spring Boot

**1. Test luôn xanh trước khi viết code.** Thường do assert thiếu, test không được runner tìm thấy, hoặc mock luôn trả giá trị mong đợi. Hãy chạy lần Red và xác nhận **đúng test mới** fail vì đúng điều kiện, kiểm tra báo cáo tên/đếm test.

**2. Test đỏ do lỗi setup thay vì hành vi.** Context không boot vì bean thiếu, test DB không kết nối hoặc credential sai. Sửa hạ tầng test trước khi bắt đầu Green; nếu không, thay code nghiệp vụ có thể chẳng ảnh hưởng kết quả.

**3. Dùng `@SpringBootTest` cho mỗi phép tính.** Vòng chậm, lỗi phụ thuộc cấu hình. Dùng JUnit thuần với lớp thật khi không cần Spring; test context chỉ dùng khi framework behavior là thứ đang chứng minh.

**4. Mock SUT hoặc mock chính tính năng cần xác minh.** `when(policy.feeFor(...)).thenReturn(0L)` không kiểm tra công thức; nó chỉ kiểm tra stub. Tạo `ShippingFeePolicy` thật, stub những collaborator ngoài phạm vi.

**5. Mỗi test `verify` mọi lời gọi nội bộ.** Những assert này dễ vỡ khi đổi cấu trúc code không ảnh hưởng kết quả. Kiểm tra interaction khi đó là yêu cầu quan trọng (chẳng hạn “không ghi DB khi thất bại” hoặc “không thu tiền hai lần”).

**6. Viết quá nhiều test trước khi có một lần Green.** Nếu thêm hàng chục tình huống trong một Red, khó nhận biết chính xác thay đổi nào khiến hành vi qua test. Chọn một trường hợp điển hình hoặc biên, thực hiện trọn vòng rồi mở rộng.

**7. Refactor khi test vẫn đỏ.** Khi vừa thay nghiệp vụ vừa chuyển cấu trúc, nguyên nhân lỗi khó tách. Đưa code về Green trước, refactor từng bước và chạy lại test.

**8. Đánh đồng unit test với bằng chứng tích hợp.** Mock repository không kiểm tra SQL; gọi trực tiếp controller không kiểm tra HTTP; object được tạo bằng `new` không chứng minh `@Transactional` hoạt động. Đặt test tại đúng ranh giới của lời khẳng định.

**9. Tối ưu để test pass bằng cách bỏ assertion hoặc tắt filter bảo mật.** Test xanh kiểu này làm mất hợp đồng cần bảo vệ. Sửa implementation hoặc test setup theo yêu cầu thực tế; phân biệt lỗi môi trường với lỗi nghiệp vụ.

**10. Test phụ thuộc trạng thái ẩn.** Dữ liệu DB dùng chung, clock thật, random không kiểm soát hay thứ tự chạy gây flakiness. Cô lập input/hạ tầng và dùng test doubles đúng ranh giới.

## 10. Checklist cho mỗi vòng và mỗi điểm áp dụng

Trước **Red**:

- Mô tả được một hành vi bằng đầu vào, điều kiện và kết quả quan sát được?
- Đã chọn ranh giới hẹp nhất đủ chứng minh hành vi (domain/service/MVC/repository/integration)?
- Biết chính xác test sẽ fail vì điều gì nếu tính năng chưa có?
- Test được runner phát hiện, môi trường chạy ổn định và dependency ngoài được kiểm soát?

Trước **Green**:

- Đã quan sát test fail đúng lý do, không phải lỗi container, test discovery hay setup?
- Chỉ triển khai phần nhỏ nhất để đáp ứng hành vi; không che lỗi bằng cách nới assertion?
- Chạy lại test mới và các test cũ liên quan?

Trước **Refactor** và chuyển vòng:

- Bộ test đang xanh?
- Việc đổi tên, tách lớp hoặc loại trùng có bảo toàn output, exception và side effect không?
- Có trường hợp biên mới xứng đáng thành vòng Red tiếp theo?
- Phần nào chưa được chứng minh ở HTTP, persistence, transaction hoặc security cần một test cấp cao bổ sung?

**Ghi nhớ:** TDD là chuỗi **Red có lý do → Green tối thiểu → Refactor khi xanh**, lặp theo từng hành vi. Với Spring Boot, chọn nơi bắt đầu từ **hợp đồng cần chứng minh**: domain khi kiểm tra quyết định, MVC khi kiểm tra HTTP, repository khi kiểm tra dữ liệu và integration khi kiểm tra kết nối/framework. Phản hồi nhanh, assertion có ý nghĩa và ranh giới đúng quan trọng hơn việc dùng nhiều annotation hoặc tăng số test.