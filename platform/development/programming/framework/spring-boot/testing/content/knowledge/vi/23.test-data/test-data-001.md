# Fixture, object builder và dữ liệu có ý nghĩa theo từng tình huống

## 1. Vì sao test data là một phần của thiết kế kiểm thử?

Nhiều bài kiểm thử Java/Spring Boot bắt đầu bằng cách tạo một object chứa 15–30 fields, điền vài chuỗi ngẫu nhiên rồi gọi service. Sau một thời gian, hàng trăm test lặp lại cùng đoạn dựng data; khi DTO đổi constructor, cả suite lỗi. Tệ hơn, dữ liệu mặc định không có ý nghĩa có thể làm một test **PASS dù logic nghiệp vụ sai**.

Ví dụ, khi kiểm phí vận chuyển miễn phí từ 100.00, dùng giỏ hàng có subtotal 1000.00 chỉ chứng minh một trường hợp rất xa ranh giới. Một lỗi so sánh `> 100` thay vì `>= 100` sẽ không bị phát hiện. Dữ liệu `99.99`, `100.00` và `100.01` mới phân biệt được quy tắc.

Bài học này hướng dẫn ba kỹ thuật có liên quan:

- **Fixture**: dữ liệu hoặc cấu trúc đối tượng được chuẩn bị để test có một điểm xuất phát nhất quán.
- **Test Data Builder**: builder có mặc định hợp lệ, cho phép ghi rõ những thuộc tính cần thay đổi cho từng tình huống.
- **Scenario-specific data**: bộ dữ liệu được chọn **vì nó phân biệt kết quả nghiệp vụ**, không chỉ “có đủ object để chạy”.

Chúng ta sẽ áp dụng trong Java 17 và Spring Boot 3.5 với JUnit Jupiter, AssertJ, Mockito, `@WebMvcTest`, `@DataJpaTest` và một full-context HTTP test. Nội dung cũng đề cập `@Sql`, Testcontainers, Clock, random seed, data isolation, privacy và những anti-pattern phổ biến.

### Mục tiêu sau bài

1. Phân biệt **fixture factory**, **Object Mother**, **Test Data Builder**, **builder production** và **database seed fixture**.
2. Tạo **một default hợp lệ, tối giản**, rồi override đúng fields có ý nghĩa trong tên test.
3. Dùng giá trị ở **ranh giới và hai phía của ranh giới**, không dùng dữ liệu tùy tiện.
4. Giữ fixture **deterministic**, cô lập giữa các tests, không chia sẻ mutable object.
5. Biết khi nào test phải tạo **invalid object** thay vì để builder chặn invalid case.
6. Dùng `@ParameterizedTest`/`@CsvSource`/`@MethodSource` để lập bảng kịch bản dễ đọc.
7. Kiểm API JSON bằng request fixture serialize bằng Jackson, không tự ghép JSON string cho happy path.
8. Kiểm JPA mapping với persisted fixture, `flush`/`clear` và rollback mặc định.
9. Hiểu fixture không tự thay thế integration infrastructure: H2 khác PostgreSQL và in-memory list khác database thật.
10. Tránh test data chứa thông tin cá nhân/secret production; dùng synthetic fixtures.

**Nguyên tắc cốt lõi:** Fixture phải làm rõ **Given**. Một test tốt không chỉ tạo dữ liệu đủ chạy, mà tạo dữ liệu khiến sai khác của business rule trở nên quan sát được.

## 2. Thuật ngữ và ranh giới

### 2.1. Fixture là gì?

Trong ngôn ngữ testing, *test fixture* có thể chỉ toàn bộ **trạng thái đầu vào/môi trường được chuẩn bị** cho một test: object graph, database rows, files, clock, fake gateway hoặc configuration. Trong bài này, ta tập trung vào **dữ liệu** và cách dựng nó.

Một fixture có thể là:

~~~java
Cart cart = new Cart(
        "customer-001",
        CustomerTier.REGULAR,
        List.of(new CartLine(
                "BOOK-001", 2, new BigDecimal("50.00"))),
        null);
~~~

Đoạn code giả định các records `Cart`, `CartLine`, enum `CustomerTier` ở project mục 8. Nó có ý nghĩa khi muốn chứng minh giỏ hàng **đúng ngưỡng 100.00**. Nhưng nếu lặp 10 dòng đó trong mọi test, độ nhiễu sẽ lớn.

### 2.2. Fixture factory

Factory dùng các phương thức có tên theo tình huống:

~~~java
Cart defaultCart = CartFixtures.validCart();
Cart below = CartFixtures.belowShippingThreshold();
Cart at = CartFixtures.atShippingThreshold();
~~~

Tác dụng: tên method giải thích ý nghĩa dữ liệu, đồng thời tránh lặp constructor. Nhưng nếu tạo hàng trăm factory methods kết hợp mọi field, số phương thức bùng nổ và khó bảo trì.

### 2.3. Object Mother

*Object Mother* là cách tổ chức các factory methods cung cấp những object điển hình cho domain: `aRegularCustomer()`, `aVipCustomer()`, `anUnpaidOrder()`, v.v.

Điểm mạnh: đọc test như mô tả câu chuyện. Điểm yếu: dễ xuất hiện một lớp `TestData` quá lớn, có hàng chục method phụ thuộc lẫn nhau và không ai biết field ngầm nào đang được điền.

### 2.4. Test Data Builder

Builder xuất phát từ **một object hợp lệ**, cho phép override theo kịch bản:

~~~java
Cart cart = CartFixtures.aCart()
        .withCustomerId("customer-002")
        .vip()
        .withLine(CartFixtures.line(
                "BOOK-002", 2, "60.00"))
        .build();
~~~

Dữ liệu mặc định nằm trong builder, còn bài test hiển thị **đúng những đặc tính đang cần**: khách VIP, subtotal 120.00. Khi default validity không còn phù hợp, builder phải được sửa tập trung.

### 2.5. Builder production khác builder test

Builder ở production thường hỗ trợ:
- Construction API cho domain entity/DTO.
- Business invariants/validation.
- Optional fields và immutable object.
- API chính thức được production gọi.

**Test Data Builder** hỗ trợ:
- Mặc định hợp lệ để giảm nhiễu.
- Override nhanh một thuộc tính.
- Có thể tạo *invalid test data* để kiểm validation.
- Không làm production model phình to chỉ để phục vụ tests.

Nếu dùng Lombok `@Builder`/`@SuperBuilder` trong production, vẫn có thể dùng cho test; nhưng phải xem mặc định hợp lệ, required fields, inheritance và constructor invariants. Không thêm Lombok vào một project chỉ vì fixture đơn giản có hai fields.

### 2.6. Database seed không phải object fixture

`new PurchaseRecord(...)` trong memory khác với một row **đã được INSERT và query được từ database**. Với `@DataJpaTest`, hãy `saveAndFlush`, `TestEntityManager.persistAndFlush` hoặc chạy `@Sql` rồi kiểm lại từ persistence context mới. Chỉ gọi constructor không kiểm được JPA mapping, transaction, constraints hoặc query methods.

## 3. Thiết kế dữ liệu có ý nghĩa theo business rule

### 3.1. Một kịch bản là một sự khác biệt quan sát được

Giả sử sản phẩm có quy tắc:

- Subtotal = tổng `unitPrice × quantity`.
- Phí vận chuyển **15.00** nếu subtotal **nhỏ hơn 100.00**.
- Phí vận chuyển **0.00** khi subtotal **từ 100.00 trở lên**.
- Khách `VIP` được giảm **10% subtotal**, làm tròn tới 2 chữ số thập phân.
- Coupon `SAVE10` giảm thêm **10.00**, nhưng tổng giảm không vượt subtotal.
- Giá, quantity, customerId và coupon phải hợp lệ.
- Total = subtotal − discount + shipping.

Với quy tắc trên, các fixtures sau có ý nghĩa:

| Tình huống | Dữ liệu | Phát hiện lỗi |
| --- | --- | --- |
| Dưới ngưỡng | Subtotal 99.99 | Không được miễn phí ship |
| Đúng ngưỡng | Subtotal 100.00 | Phát hiện `>` thay vì `>=` |
| Trên ngưỡng | Subtotal 100.01 | Kiểm nhánh miễn phí ship |
| VIP | Subtotal 120.00, tier VIP | Giảm đúng 12.00 |
| Coupon | Subtotal 120.00, SAVE10 | Giảm 10.00, total 110.00 |
| VIP + coupon | Subtotal 120.00, VIP, SAVE10 | Giảm gộp 22.00, total 98.00 |
| Coupon lớn hơn subtotal | Subtotal 5.00, SAVE10 | Discount cap 5.00, không âm |
| Quantity không hợp lệ | Quantity 0 | Kiểm validation thay vì phép nhân bình thường |
| Giá âm | Unit price -1.00 | Không tạo tổng tiền sai |
| Coupon không tồn tại | BADCODE | Reject input theo contract |
| Không có lines | Empty list | Không xử lý cart rỗng như order hợp lệ |

Một fixture có subtotal 1000.00, tier REGULAR, coupon null **không thể** thay cho cả bảng trên.

### 3.2. Quy tắc “một biến có chủ ý”

Khi muốn kiểm khách VIP, giữ các biến khác ổn định:
- Cùng subtotal.
- Cùng quantity và SKU.
- Cùng coupon null.
- Chỉ đổi tier REGULAR ↔ VIP.

Khi muốn kiểm ngưỡng phí ship, giữ tier REGULAR, coupon null và quantity 1, chỉ đổi unitPrice giữa 99.99, 100.00, 100.01.

Đây là cách cô lập nguyên nhân. Nếu cùng lúc đổi tier, coupon, quantity, SKU và date, test fail sẽ khó biết business rule nào bị hỏng.

### 3.3. Value có ý nghĩa hơn magic number

Tên `oneHundredAndOne()` thường kém rõ hơn `atFreeShippingThreshold()`. Một giá trị test nên có ý nghĩa theo business vocabulary:

~~~java
Cart atThreshold = CartFixtures.atShippingThreshold();
Quote result = pricing.quote(atThreshold);
assertThat(result.shipping())
        .isEqualByComparingTo("0.00");
~~~

Test đọc được như requirement. Nếu rule đổi từ 100.00 thành 150.00, factory nên thay theo quyết định review, **không tự cập nhật expected hàng loạt** khi chưa hiểu contract mới.

### 3.4. Null, empty, missing và zero

Những trường hợp này khác nhau:

| Giá trị | Khả năng ý nghĩa |
| --- | --- |
| `null` coupon | Không áp dụng coupon |
| `""` coupon | Người dùng gửi chuỗi rỗng; có thể invalid |
| `"BADCODE"` | Coupon không tồn tại |
| `quantity=0` | Input không hợp lệ |
| `unitPrice=0.00` | Có thể hợp lệ với hàng tặng hoặc bị cấm theo domain |
| `lines=[]` | Cart rỗng, cần xử lý rõ |
| JSON thiếu `couponCode` | Jackson có thể truyền null; cần biết contract |
| JSON có `"couponCode":null` | Property hiện diện nhưng null |

Fixture “happy path” nên tránh null tùy tiện ở required fields; **negative fixtures** nên tạo trường hợp invalid một cách chủ động để test đúng validation boundary.

## 4. Test data phải deterministic, cô lập và an toàn

### 4.1. Deterministic

Cùng input, cùng code, cùng dependency/configuration phải tạo cùng kết quả test. Tránh:
- `LocalDateTime.now()` trực tiếp trong expected.
- `UUID.randomUUID()` nếu sau đó so ID với một hằng cố định.
- `new Random()` không có seed trong test cần reproducibility.
- Dữ liệu lấy từ internet hoặc production DB.
- Kết quả phụ thuộc thứ tự chạy JUnit methods.

Dùng `Instant.parse("2026-01-15T08:00:00Z")` hoặc inject `Clock.fixed(...)` khi business logic phụ thuộc thời gian.

### 4.2. Clock.fixed

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-15T08:00:00Z"),
        ZoneOffset.UTC);

Instant createdAt = Instant.now(fixed);
assertThat(createdAt)
        .isEqualTo(Instant.parse("2026-01-15T08:00:00Z"));
~~~

Đây là snippet trong một test có imports `java.time.Clock`, `Instant`, `ZoneOffset` và AssertJ. Không dùng giờ hệ điều hành làm expected nếu logic chỉ cần mốc cố định. Với các nghiệp vụ deadline/expiry, kiểm trước, đúng lúc, sau deadline.

### 4.3. Random có seed và property testing

Đối với test-based examples, chọn fixtures cố định, dễ đọc. Nếu muốn sinh hàng trăm trường hợp, cân nhắc property-based testing bằng jqwik hoặc QuickTheories với seed có thể tái hiện và constraints đúng.

~~~java
Random random = new Random(12345L);
int quantity = random.nextInt(1, 11);
~~~

Snippet minh họa Java 17. Seed làm chuỗi random reproducible, nhưng với một test có requirement cụ thể như phí ship ở 100.00, **dữ liệu ranh giới cố định tốt hơn random**. Không sinh tên/ID có khả năng trùng trong các parallel integration tests mà không có namespace an toàn.

### 4.4. Không chia sẻ mutable fixture

Sai:

~~~java
static final List<CartLine> SHARED_LINES =
        new ArrayList<>();

@BeforeEach
void setUp() {
    SHARED_LINES.add(...);  // các test tiếp theo có thể tích lũy state
}
~~~

Đây là anti-pattern. Fixture nên tạo **instance mới cho mỗi test**; builder được tạo mới mỗi lần. Với JPA entity, tuyệt đối tránh chia sẻ cùng managed entity qua tests: ID, persistence context, lazy proxy và dirty checking khiến state khó đoán.

### 4.5. Immutable snapshot

Java records thích hợp làm request/result DTO. Với field list, record compact constructor nên copy:

~~~java
public record Cart(
        String customerId,
        CustomerTier tier,
        List<CartLine> lines,
        String couponCode) {

    public Cart {
        lines = List.copyOf(lines);
    }
}
~~~

`List.copyOf` giúp ngăn caller mutate danh sách sau khi tạo cart, nhưng không deep-copy những phần tử mutable. Trong project, `CartLine` cũng là record với `BigDecimal` immutable nên graph ổn định.

### 4.6. Không dùng dữ liệu production

Fixture không được chứa PII, mật khẩu thật, token thật, card number thật hoặc database dump chưa được ẩn danh. Tạo synthetic customers, test SKU, email domain ví dụ (nếu có). Có thể dùng định danh `customer-test-001`, không cần thông tin cá nhân thật để phát hiện bug của tổng tiền.

## 5. Khi nào chọn fixture factory, builder hay @Sql?

| Cần kiểm | Cách tạo dữ liệu | Lý do |
| --- | --- | --- |
| Một hàm Java thuần | `CartFixtures.aCart().build()` | Không cần Spring context |
| Nhiều business scenarios | Named factory + builder override | Tên rõ + ít trùng code |
| MVC controller nhận JSON | Serialize request fixture với ObjectMapper | Kiểm HTTP/Jackson, không ghép text |
| Controller behavior khi service trả result | `@MockitoBean` service + result fixture | Giữ đúng MVC slice |
| JPA entity mapping | Entity fixture + `persistAndFlush`/`clear` | Kiểm persisted state |
| Nhiều rows có quan hệ khóa ngoại | Builder graph hoặc `@Sql` scripts | Dễ thấy quan hệ; kiểm constraint |
| Dữ liệu chuẩn lớn/versioned | `@Sql`/test resource JSON/CSV/LDIF | Review diff như contract |
| PostgreSQL-specific SQL/query | Testcontainers PostgreSQL + schema thật | H2 không tương đương |
| Test thời gian/expiry | Clock.fixed / injectable Clock | Không phụ thuộc wall clock |
| Complex valid/invalid inputs | Builder riêng cho negative cases | Không làm vỡ default fixture |
| Dữ liệu có hàng nghìn biến thể | Parameterized/property tests | Phủ không gian lớn, reproducible |

Không phải mọi object đều cần builder. Một record hai trường có constructor rõ ràng thường dễ đọc hơn một builder 80 dòng. Chọn abstraction để **giảm nhiễu và làm nổi bật requirement**, không phải để tối đa hóa số helper classes.

## 6. Sử dụng fixtures cho Arrange–Act–Assert

Một test có cấu trúc tốt:

~~~java
@Test
void vipGetsTenPercentDiscount() {
    // Arrange: chỉ làm rõ điều kiện cần test
    Cart cart = CartFixtures.vipEligible();

    // Act: gọi hệ thống đang kiểm
    Quote actual = pricing.quote(cart);

    // Assert: kiểm business result
    assertThat(actual.discount())
            .isEqualByComparingTo("12.00");
}
~~~

So với:

~~~java
@Test
void test1() {
    String a = "X";
    int b = 2;
    BigDecimal c = new BigDecimal("60.00");
    // nhiều fields khác không liên quan...
    assertThat(pricing.quote(new Cart(...)).discount())
            .isEqualByComparingTo("12.00");
}
~~~

Bản đầu dễ xác định Given/When/Then và quy tắc đang được kiểm. Bản thứ hai đòi người đọc phải tính ngược từ `b * c` và đoán ý nghĩa.

### 6.1. Assertions không nên nhắc lại algorithm

Nếu expected được tính bằng **chính code/thuật toán production**, test có thể lặp bug:

~~~java
// Không nên cho test ranh giới:
BigDecimal expected = cartSubtotal(cart)
        .multiply(VIP_RATE);
assertThat(pricing.quote(cart).discount())
        .isEqualByComparingTo(expected);
~~~

Nếu `cartSubtotal` trong test và production cùng sai theo một cách, assertion không phát hiện. Với kịch bản đơn giản, dùng expected cụ thể và giải thích tại sao: 120.00 × 10% = 12.00.

### 6.2. Một test có thể assert nhiều điều, nhưng phải cùng một behavior

Một test định giá có thể kiểm `subtotal`, `discount`, `shipping` và `total` cùng lúc vì chúng mô tả cùng một quote. Nhưng đừng trộn assertions email, repository, HTTP headers, DB transactions trong một test unit đang kiểm một hàm tính giá. Những boundary đó nên có test riêng.

## 7. Project Spring Boot hoàn chỉnh: Java 17 và Maven

### 7.1. Mục tiêu của project

Ta sẽ triển khai ứng dụng báo giá một giỏ hàng. Rules như phần 3:
- Regular subtotal 40.00 → shipping 15.00 → total 55.00.
- Regular subtotal 99.99 → shipping 15.00 → total 114.99.
- Regular subtotal 100.00 → shipping 0.00.
- VIP subtotal 120.00 → discount 12.00 → total 108.00.
- Coupon `SAVE10` trên subtotal 120.00 → discount 10.00 → total 110.00.
- VIP + coupon trên subtotal 120.00 → discount 22.00 → total 98.00.
- Nếu coupon lớn hơn subtotal, discount được cap ở subtotal (không âm).
- Input invalid bị ném `IllegalArgumentException` ở service layer.

Cùng repo chứa entity `PurchaseRecord` để minh họa JPA persisted fixture, nhưng quote service **không phụ thuộc repository**. Ta cố tình tách để so sánh fixture thuần Java và fixture database, không lôi JPA vào tính giá đơn giản.

### 7.2. Cây file

~~~text
fixture-builder-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/fixturelab/
│   ├── FixtureLabApplication.java
│   ├── CustomerTier.java
│   ├── CartLine.java
│   ├── Cart.java
│   ├── Quote.java
│   ├── CheckoutPricingService.java
│   ├── QuoteController.java
│   ├── PurchaseRecord.java
│   └── PurchaseRecordRepository.java
└── src/test/java/com/example/fixturelab/
    ├── support/
    │   ├── CartFixtures.java
    │   └── PurchaseRecordFixtures.java
    ├── CartFixturesTest.java
    ├── CheckoutPricingServiceTest.java
    ├── QuoteControllerJsonTest.java
    ├── PurchaseRecordRepositoryTest.java
    └── QuoteHttpIntegrationTest.java
~~~

Mọi file Java production nằm trong `com.example.fixturelab`; hai fixture helpers ở `com.example.fixturelab.support`. Chúng nằm trong `src/test/java`, **không đóng gói vào artifact production**. Không có static global mutable entity.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>fixture-builder-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
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

Spring Boot parent/BOM quản lý Spring Framework, JUnit Jupiter, AssertJ, Mockito, Jackson, Hibernate. `@MockitoBean` trong ví dụ thuộc Spring Framework 6.2 và hoạt động với Boot 3.5. Không thêm `@MockBean` đời cũ chỉ để né sửa import.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:fixture_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

`create-drop` phù hợp cho bài lab H2, không dùng trong production. `@DataJpaTest` có thể thay datasource bằng embedded DB khác theo auto-configuration, nhưng cùng mục tiêu: một database cô lập trong test.

### 7.5. FixtureLabApplication.java

~~~java
package com.example.fixturelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FixtureLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(FixtureLabApplication.class, args);
    }
}
~~~

### 7.6. CustomerTier.java

~~~java
package com.example.fixturelab;

public enum CustomerTier {
    REGULAR,
    VIP
}
~~~

Enum này hiện rõ hai nhánh business. Không đặt field `isVip` boolean lẫn `CustomerTier` để tránh contradictory test input.

### 7.7. CartLine.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;

public record CartLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {
}
~~~

Record cố tình **không chặn invalid input trong constructor**. Mục tiêu là cho phép fixture tạo line với quantity 0 hoặc price âm để kiểm validation tại `CheckoutPricingService`. Nếu production domain dùng validated value objects (constructor ném ngay), test invalid phải kiểm **chính constructor đó** hoặc HTTP binding/validation, chứ không ép builder vượt qua invariant bất khả thi.

### 7.8. Cart.java

~~~java
package com.example.fixturelab;

import java.util.List;

public record Cart(
        String customerId,
        CustomerTier tier,
        List<CartLine> lines,
        String couponCode) {

    public Cart {
        lines = List.copyOf(lines);
    }
}
~~~

Compact constructor bảo vệ khỏi việc mutation danh sách bên ngoài làm thay đổi fixture sau khi build. `List.copyOf` không chấp nhận null list/null elements; do đó case `lines=null` được reject ngay tại record construction thay vì service. Một test cần kiểm missing/null JSON có thể dùng raw JSON input/HTTP binding test theo contract, không nhất thiết buộc object builder tạo một record bất hợp lệ.

### 7.9. Quote.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;

public record Quote(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal shipping,
        BigDecimal total) {
}
~~~

Kết quả là một value object; dùng `BigDecimal` cho tiền thay vì `double`. Khi so giá trị numeric, AssertJ `isEqualByComparingTo` tránh nhầm scale của `19.9` và `19.90` nếu scale không phải contract.

### 7.10. CheckoutPricingService.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Service;

@Service
public class CheckoutPricingService {

    private static final BigDecimal FREE_SHIPPING_AT =
            new BigDecimal("100.00");
    private static final BigDecimal SHIPPING_FEE =
            new BigDecimal("15.00");
    private static final BigDecimal VIP_RATE =
            new BigDecimal("0.10");
    private static final BigDecimal COUPON_VALUE =
            new BigDecimal("10.00");

    public Quote quote(Cart cart) {
        if (cart == null || cart.customerId() == null
                || cart.customerId().isBlank()) {
            throw new IllegalArgumentException(
                    "customerId must be present");
        }
        if (cart.tier() == null) {
            throw new IllegalArgumentException(
                    "tier must be present");
        }
        if (cart.lines().isEmpty()) {
            throw new IllegalArgumentException(
                    "cart must contain at least one line");
        }

        BigDecimal subtotal = BigDecimal.ZERO;
        for (CartLine line : cart.lines()) {
            if (line == null || line.sku() == null
                    || line.sku().isBlank()) {
                throw new IllegalArgumentException(
                        "sku must be present");
            }
            if (line.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (line.unitPrice() == null
                    || line.unitPrice().signum() < 0
                    || line.unitPrice().scale() > 2) {
                throw new IllegalArgumentException(
                        "unitPrice must be non-negative with at most 2 decimals");
            }
            subtotal = subtotal.add(
                    line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity())));
        }

        if (cart.couponCode() != null
                && !"SAVE10".equals(cart.couponCode())) {
            throw new IllegalArgumentException(
                    "unsupported coupon");
        }

        BigDecimal vipDiscount = cart.tier() == CustomerTier.VIP
                ? subtotal.multiply(VIP_RATE).setScale(
                        2, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;
        BigDecimal couponDiscount =
                "SAVE10".equals(cart.couponCode())
                        ? COUPON_VALUE : BigDecimal.ZERO;

        BigDecimal discount = vipDiscount.add(couponDiscount)
                .min(subtotal)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal shipping =
                subtotal.compareTo(FREE_SHIPPING_AT) >= 0
                        ? BigDecimal.ZERO : SHIPPING_FEE;

        BigDecimal total = subtotal.subtract(discount)
                .add(shipping)
                .setScale(2, RoundingMode.HALF_UP);

        return new Quote(
                subtotal.setScale(2, RoundingMode.HALF_UP),
                discount,
                shipping.setScale(2, RoundingMode.HALF_UP),
                total);
    }
}
~~~

Business decisions cố ý đủ nhỏ để expected values được tính độc lập bằng tay:
- Ngưỡng shipping áp trên **subtotal trước discount**.
- VIP giảm 10% subtotal và được round HALF_UP.
- Coupon có thể cộng với VIP discount.
- Tổng discount không vượt subtotal.
- Mọi kết quả tiền hiển thị scale 2; không tính floating point.

Trong production, cần định nghĩa currency, tax, exchange rate, shipping rules và coupon eligibility rõ ràng; đây là lab để học fixture/branch testing, không phải checkout engine hoàn chỉnh.

### 7.11. QuoteController.java

~~~java
package com.example.fixturelab;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final CheckoutPricingService pricing;

    public QuoteController(CheckoutPricingService pricing) {
        this.pricing = pricing;
    }

    @PostMapping
    public Quote quote(@RequestBody Cart cart) {
        return pricing.quote(cart);
    }
}
~~~

Controller nhận JSON ánh xạ thành `Cart` qua Jackson. Ví dụ không thêm handler cho invalid request; unit tests kiểm invalid inputs trực tiếp ở service, còn API có thể trả status mặc định nếu exception chưa được map. Để API thật trả 400 có error contract chuẩn, bổ sung `@RestControllerAdvice` hoặc bean validation rồi test riêng.

### 7.12. PurchaseRecord.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @Column(name = "reference_code", length = 80)
    private String referenceCode;

    @Column(name = "customer_id", nullable = false, length = 80)
    private String customerId;

    @Column(name = "order_total", nullable = false,
            precision = 12, scale = 2)
    private BigDecimal total;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseRecord() {
        // JPA constructor
    }

    public PurchaseRecord(
            String referenceCode,
            String customerId,
            BigDecimal total,
            String status,
            Instant createdAt) {
        this.referenceCode = referenceCode;
        this.customerId = customerId;
        this.total = total;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getCustomerId() {
        return customerId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

JPA entity là **mutable/persistence-managed model** khác Java record `Cart`. Không chia sẻ cùng managed instance giữa tests. Dùng assigned `referenceCode` để fixture có identity rõ và test không phụ thuộc database-generated sequences.

### 7.13. PurchaseRecordRepository.java

~~~java
package com.example.fixturelab;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRecordRepository
        extends JpaRepository<PurchaseRecord, String> {

    List<PurchaseRecord> findByStatus(String status);
}
~~~

`findByStatus` là derived query; JPA test sẽ kiểm persistence mapping và query thực tế. Không thể chứng minh query chạy chỉ bằng cách mock repository trả một `List`.

## 8. Test fixtures trong src/test/java

### 8.1. CartFixtures.java

`src/test/java/com/example/fixturelab/support/CartFixtures.java`:

~~~java
package com.example.fixturelab.support;

import java.math.BigDecimal;
import java.util.List;

import com.example.fixturelab.Cart;
import com.example.fixturelab.CartLine;
import com.example.fixturelab.CustomerTier;

public final class CartFixtures {

    private CartFixtures() {
    }

    public static CartLine line(
            String sku, int quantity, String unitPrice) {
        return new CartLine(
                sku, quantity, new BigDecimal(unitPrice));
    }

    public static CartBuilder aCart() {
        return new CartBuilder();
    }

    public static Cart validCart() {
        return aCart().build();
    }

    public static Cart belowShippingThreshold() {
        return aCart()
                .withLine(line("BOOK-001", 1, "99.99"))
                .build();
    }

    public static Cart atShippingThreshold() {
        return aCart()
                .withLine(line("BOOK-001", 2, "50.00"))
                .build();
    }

    public static Cart vipEligible() {
        return aCart()
                .vip()
                .withLine(line("BOOK-001", 2, "60.00"))
                .build();
    }

    public static Cart couponEligible() {
        return aCart()
                .withLine(line("BOOK-001", 2, "60.00"))
                .withCouponCode("SAVE10")
                .build();
    }

    public static Cart invalidQuantity() {
        return aCart()
                .withLine(line("BOOK-001", 0, "40.00"))
                .build();
    }

    public static final class CartBuilder {

        private String customerId = "customer-test-001";
        private CustomerTier tier = CustomerTier.REGULAR;
        private List<CartLine> lines = List.of(
                line("BOOK-001", 1, "40.00"));
        private String couponCode;

        private CartBuilder() {
        }

        public CartBuilder withCustomerId(String value) {
            this.customerId = value;
            return this;
        }

        public CartBuilder withTier(CustomerTier value) {
            this.tier = value;
            return this;
        }

        public CartBuilder vip() {
            return withTier(CustomerTier.VIP);
        }

        public CartBuilder withLine(CartLine value) {
            this.lines = List.of(value);
            return this;
        }

        public CartBuilder withLines(CartLine... values) {
            this.lines = List.of(values);
            return this;
        }

        public CartBuilder withCouponCode(String value) {
            this.couponCode = value;
            return this;
        }

        public Cart build() {
            return new Cart(
                    customerId,
                    tier,
                    List.copyOf(lines),
                    couponCode);
        }
    }
}
~~~

**Tại sao cách này tốt?**
- `aCart()` trả **builder mới** mỗi lần, không có static mutable instance.
- Default có customer, tier, một line hợp lệ, coupon null.
- Named scenarios cho những case phổ biến nhất; không tạo mọi tổ hợp.
- `withLine` thay toàn bộ lines, tránh cũ cộng mới bất ngờ.
- `withLines` cho multi-line scenario khi cần; empty varargs tạo empty list để kiểm validation.
- `build()` trả Cart với defensive copy. Nếu builder tiếp tục được chỉnh, object đã build không tự đổi.
- `invalidQuantity()` chủ động tạo quantity 0 để test validation. Builder không được phép ép quantity thành 1 nếu test đang cần kiểm invalid input.
- Money values dùng chuỗi truyền vào `BigDecimal`, không dùng `new BigDecimal(0.1)` vì lỗi floating-point representation.

**Một giới hạn có chủ đích:** Các fields customerId, SKU được cố định. Khi integration test chạy song song với persisted data, hãy override identity bằng giá trị riêng theo test (hoặc tạo namespace), không dùng mọi test cùng record key mặc định.

### 8.2. PurchaseRecordFixtures.java

`src/test/java/com/example/fixturelab/support/PurchaseRecordFixtures.java`:

~~~java
package com.example.fixturelab.support;

import java.math.BigDecimal;
import java.time.Instant;

import com.example.fixturelab.PurchaseRecord;

public final class PurchaseRecordFixtures {

    private PurchaseRecordFixtures() {
    }

    public static PurchaseBuilder aPurchase() {
        return new PurchaseBuilder();
    }

    public static final class PurchaseBuilder {

        private String referenceCode = "fixture-default-001";
        private String customerId = "customer-test-001";
        private BigDecimal total = new BigDecimal("100.00");
        private String status = "NEW";
        private Instant createdAt =
                Instant.parse("2026-01-15T08:00:00Z");

        private PurchaseBuilder() {
        }

        public PurchaseBuilder withReferenceCode(String value) {
            this.referenceCode = value;
            return this;
        }

        public PurchaseBuilder withCustomerId(String value) {
            this.customerId = value;
            return this;
        }

        public PurchaseBuilder withTotal(String value) {
            this.total = new BigDecimal(value);
            return this;
        }

        public PurchaseBuilder withStatus(String value) {
            this.status = value;
            return this;
        }

        public PurchaseBuilder withCreatedAt(Instant value) {
            this.createdAt = value;
            return this;
        }

        public PurchaseRecord build() {
            return new PurchaseRecord(
                    referenceCode,
                    customerId,
                    total,
                    status,
                    createdAt);
        }
    }
}
~~~

Với database fixtures:
- `referenceCode` cần override riêng khi insert nhiều rows trong cùng test.
- `createdAt` là fixed instant, không gọi wall clock.
- `total` dùng BigDecimal string.
- Không giả lập “đã persist” bằng một entity mới; test phải `persistAndFlush` hoặc repository `saveAndFlush`.
- Builder không tự mở transaction, không gọi repository và không giữ static EntityManager. **Fixture construction** khác **fixture persistence**.
- Không cố đưa business validation vào tất cả builder fields; một số negative tests cần tạo dữ liệu thiếu, invalid status hoặc null để kiểm validation/constraint.

## 9. Kiểm builder và fixture độc lập

### 9.1. CartFixturesTest.java

`src/test/java/com/example/fixturelab/CartFixturesTest.java`:

~~~java
package com.example.fixturelab;

import org.junit.jupiter.api.Test;

import static com.example.fixturelab.support.CartFixtures.aCart;
import static com.example.fixturelab.support.CartFixtures.line;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CartFixturesTest {

    @Test
    void defaultFixtureIsValidAndPredictable() {
        Cart cart = aCart().build();

        assertThat(cart.customerId())
                .isEqualTo("customer-test-001");
        assertThat(cart.tier())
                .isEqualTo(CustomerTier.REGULAR);
        assertThat(cart.lines()).hasSize(1);
        assertThat(cart.lines().get(0).unitPrice())
                .isEqualByComparingTo("40.00");
        assertThat(cart.couponCode()).isNull();
    }

    @Test
    void changesToOneBuilderDoNotChangeAnotherFixture() {
        Cart special = aCart()
                .vip()
                .withCouponCode("SAVE10")
                .build();

        Cart standard = aCart().build();

        assertThat(special.tier())
                .isEqualTo(CustomerTier.VIP);
        assertThat(special.couponCode())
                .isEqualTo("SAVE10");

        assertThat(standard.tier())
                .isEqualTo(CustomerTier.REGULAR);
        assertThat(standard.couponCode()).isNull();
    }

    @Test
    void buildingThenOverridingDoesNotMutateOldCart() {
        var builder = aCart();
        Cart original = builder.build();

        Cart changed = builder
                .withLine(line("BOOK-002", 2, "60.00"))
                .build();

        assertThat(original.lines().get(0).sku())
                .isEqualTo("BOOK-001");
        assertThat(original.lines().get(0).quantity())
                .isEqualTo(1);

        assertThat(changed.lines().get(0).sku())
                .isEqualTo("BOOK-002");
        assertThat(changed.lines().get(0).quantity())
                .isEqualTo(2);
    }

    @Test
    void builtCartDoesNotExposeMutableList() {
        Cart cart = aCart().build();

        assertThatThrownBy(() ->
                cart.lines().add(line("EXTRA", 1, "1.00")))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

Kiểm fixture helper không phải mục tiêu của mọi project, nhưng với một builder được dùng trong hàng trăm tests, vài assertions đơn giản có thể giúp phát hiện **shared-state bug**, sai default hoặc mutation leakage.

### 9.2. Vì sao không dùng một static Cart singleton?

Nếu `static final Cart` là record chứa các thành phần immutable, nó có thể an toàn về mặt mutation; nhưng trong test cần override linh hoạt thì object builder mới dễ kiểm soát hơn. Nếu `static final PurchaseRecord ENTITY` lại là JPA entity mutable, sharing còn nguy hiểm hơn do trạng thái managed/detached/ID và persistence context.

**Default recommendation:** static **factory method**, không static **mutable entity instance**.

## 10. Unit tests dùng fixture có ý nghĩa

### 10.1. CheckoutPricingServiceTest.java

`src/test/java/com/example/fixturelab/CheckoutPricingServiceTest.java`:

~~~java
package com.example.fixturelab;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static com.example.fixturelab.support.CartFixtures.aCart;
import static com.example.fixturelab.support.CartFixtures.atShippingThreshold;
import static com.example.fixturelab.support.CartFixtures.belowShippingThreshold;
import static com.example.fixturelab.support.CartFixtures.couponEligible;
import static com.example.fixturelab.support.CartFixtures.invalidQuantity;
import static com.example.fixturelab.support.CartFixtures.line;
import static com.example.fixturelab.support.CartFixtures.validCart;
import static com.example.fixturelab.support.CartFixtures.vipEligible;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CheckoutPricingServiceTest {

    private final CheckoutPricingService pricing =
            new CheckoutPricingService();

    @Test
    void defaultCartHasPaidShipping() {
        Quote result = pricing.quote(validCart());

        assertThat(result.subtotal())
                .isEqualByComparingTo("40.00");
        assertThat(result.discount())
                .isEqualByComparingTo("0.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("15.00");
        assertThat(result.total())
                .isEqualByComparingTo("55.00");
    }

    @Test
    void belowThresholdStillPaysShipping() {
        Quote result = pricing.quote(
                belowShippingThreshold());

        assertThat(result.subtotal())
                .isEqualByComparingTo("99.99");
        assertThat(result.shipping())
                .isEqualByComparingTo("15.00");
        assertThat(result.total())
                .isEqualByComparingTo("114.99");
    }

    @Test
    void exactlyAtThresholdGetsFreeShipping() {
        Quote result = pricing.quote(atShippingThreshold());

        assertThat(result.subtotal())
                .isEqualByComparingTo("100.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("0.00");
        assertThat(result.total())
                .isEqualByComparingTo("100.00");
    }

    @ParameterizedTest(name = "subtotal {0} gives shipping {1}")
    @CsvSource({
            "99.99, 15.00, 114.99",
            "100.00, 0.00, 100.00",
            "100.01, 0.00, 100.01"
    })
    void shippingBoundaryOnBothSides(
            String price,
            String expectedShipping,
            String expectedTotal) {
        Cart cart = aCart()
                .withLine(line("BOOK-001", 1, price))
                .build();

        Quote result = pricing.quote(cart);

        assertThat(result.shipping())
                .isEqualByComparingTo(expectedShipping);
        assertThat(result.total())
                .isEqualByComparingTo(expectedTotal);
    }

    @Test
    void vipGetsTenPercentOfSubtotal() {
        Quote result = pricing.quote(vipEligible());

        assertThat(result.subtotal())
                .isEqualByComparingTo("120.00");
        assertThat(result.discount())
                .isEqualByComparingTo("12.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("0.00");
        assertThat(result.total())
                .isEqualByComparingTo("108.00");
    }

    @Test
    void couponChangesOnlyTheExpectedRule() {
        Quote result = pricing.quote(couponEligible());

        assertThat(result.discount())
                .isEqualByComparingTo("10.00");
        assertThat(result.total())
                .isEqualByComparingTo("110.00");
    }

    @Test
    void vipAndCouponCanBeCombined() {
        Cart cart = aCart()
                .vip()
                .withLine(line("BOOK-001", 2, "60.00"))
                .withCouponCode("SAVE10")
                .build();

        Quote result = pricing.quote(cart);

        assertThat(result.discount())
                .isEqualByComparingTo("22.00");
        assertThat(result.total())
                .isEqualByComparingTo("98.00");
    }

    @Test
    void couponCannotMakeSubtotalNegative() {
        Cart cart = aCart()
                .withLine(line("GIFT", 1, "5.00"))
                .withCouponCode("SAVE10")
                .build();

        Quote result = pricing.quote(cart);

        assertThat(result.discount())
                .isEqualByComparingTo("5.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("15.00");
        assertThat(result.total())
                .isEqualByComparingTo("15.00");
    }

    @Test
    void invalidQuantityIsRejected() {
        assertThatThrownBy(() ->
                pricing.quote(invalidQuantity()))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("quantity");
    }

    @Test
    void negativeUnitPriceIsRejected() {
        Cart cart = aCart()
                .withLine(line("BOOK-001", 1, "-1.00"))
                .build();

        assertThatThrownBy(() -> pricing.quote(cart))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unitPrice");
    }

    @Test
    void unknownCouponIsRejected() {
        Cart cart = aCart()
                .withCouponCode("NOT-A-COUPON")
                .build();

        assertThatThrownBy(() -> pricing.quote(cart))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unsupported coupon");
    }

    @Test
    void emptyCartIsRejected() {
        Cart cart = aCart().withLines().build();

        assertThatThrownBy(() -> pricing.quote(cart))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("at least one line");
    }
}
~~~

Đây là **pure unit test**: không khởi động Spring, Hibernate, MockMvc, server hay H2. `CheckoutPricingService` không có state/dependencies nên `new` là đủ. Dữ liệu và expected values được chọn để **phát hiện các nhánh sai**.

### 10.2. Tại sao @CsvSource hữu ích?

Các dòng `99.99`/`100.00`/`100.01` có cùng logic assertion, chỉ khác input/expected. Parameterized test tránh ba methods lặp y hệt, đồng thời IDE/test report cho biết case nào fail.

Không lạm dụng `@CsvSource` cho object graph phức tạp khó đọc. Khi mỗi case có nhiều lines, status và customer tier, dùng `@MethodSource` trả `Stream<Arguments>` với **tên scenario rõ** hoặc named fixture methods.

### 10.3. Khi cần @MethodSource

~~~java
static Stream<Arguments> cases() {
    return Stream.of(
        arguments("below threshold",
                CartFixtures.belowShippingThreshold(), "15.00"),
        arguments("at threshold",
                CartFixtures.atShippingThreshold(), "0.00")
    );
}

@ParameterizedTest(name = "{0}")
@MethodSource("cases")
void shippingCases(String name, Cart cart, String expected) {
    assertThat(pricing.quote(cart).shipping())
            .isEqualByComparingTo(expected);
}
~~~

Đây là **mẫu mở rộng**, không phải file runnable độc lập: cần imports `Stream`, `Arguments`, `MethodSource`, `ParameterizedTest` và field `pricing`. Chọn `@MethodSource` khi data dạng object không thể biểu diễn gọn trong CSV. Mỗi item nên được tạo mới hoặc immutable để tránh state rò rỉ.

## 11. MockMvc slice: fixture phải qua wire format

### 11.1. Vì sao không mock cả controller và JSON?

Một unit test mock controller return `Quote` có thể kiểm Java method nhưng không chứng minh endpoint có route, HTTP Content-Type hay Jackson field names đúng. Để kiểm HTTP contract, dùng `@WebMvcTest(QuoteController.class)` với controller thật, JSON mapper thật, mock business service qua `@MockitoBean`.

### 11.2. QuoteControllerJsonTest.java

`src/test/java/com/example/fixturelab/QuoteControllerJsonTest.java`:

~~~java
package com.example.fixturelab;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;

import static com.example.fixturelab.support.CartFixtures.atShippingThreshold;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerJsonTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    CheckoutPricingService pricing;

    @Test
    void serializesMeaningfulCartAndChecksReturnedJson()
            throws Exception {
        Cart input = atShippingThreshold();

        Quote expected = new Quote(
                new BigDecimal("100.00"),
                new BigDecimal("0.00"),
                new BigDecimal("0.00"),
                new BigDecimal("100.00"));

        when(pricing.quote(any(Cart.class)))
                .thenReturn(expected);

        String response = mvc.perform(
                post("/api/quotes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsBytes(input)))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.subtotal").isNumber())
                .andExpect(jsonPath("$.discount").isNumber())
                .andExpect(jsonPath("$.shipping").isNumber())
                .andExpect(jsonPath("$.total").isNumber())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode tree = mapper.readTree(response);
        assertThat(tree.path("shipping").decimalValue())
                .isEqualByComparingTo("0.00");
        assertThat(tree.path("total").decimalValue())
                .isEqualByComparingTo("100.00");

        ArgumentCaptor<Cart> captured =
                ArgumentCaptor.forClass(Cart.class);
        verify(pricing).quote(captured.capture());

        assertThat(captured.getValue().customerId())
                .isEqualTo(input.customerId());
        assertThat(captured.getValue().tier())
                .isEqualTo(CustomerTier.REGULAR);
        assertThat(captured.getValue().lines())
                .hasSize(1);
        assertThat(captured.getValue()
                .lines().get(0).unitPrice())
                .isEqualByComparingTo("50.00");
    }
}
~~~

**Điều test này kiểm:**
- `@WebMvcTest` nạp controller + MVC/Jackson slice, không cần JPA full context.
- `@MockitoBean` thay service trong Spring context, còn JSON mapping là thật.
- Jackson serialize **chính fixture Cart**: tránh hard-code một JSON happy path không tương ứng Java model.
- `ArgumentCaptor` kiểm request đã được deserialized đúng trước khi chuyển cho service.
- Kết quả JSON được parse bằng `JsonNode`, không so raw string với whitespace/object key order.
- Giá trị tiền so theo `BigDecimal`, không ép kiểu string/double.
- Không suy test này chứng minh pricing algorithm; service **đã mock**. Unit test ở mục 10 kiểm business logic, full HTTP integration ở mục 13 kiểm hai tầng kết hợp.

Nếu test cần kiểm invalid JSON/missing field/raw input, có thể gửi literal JSON riêng vì đó là **wire-level error scenario**, không phải happy path business fixture.

## 12. @DataJpaTest: tạo fixture và đọc lại từ database

### 12.1. Tại sao không chỉ assert object đã build?

`PurchaseRecordFixtures.aPurchase().build()` trả Java object với fields chính xác, nhưng mọi getter vẫn trả đúng ngay cả khi annotations `@Column` sai hoặc repository query không hoạt động. Cần persist/read qua database.

Trong Spring Boot 3.5, `@DataJpaTest`:
- Scan JPA entities và repositories, không toàn bộ service/controllers.
- Thường thay DataSource bằng embedded DB nếu có H2 trên classpath.
- Bật transaction và **rollback mặc định sau test**.
- Có thể inject `TestEntityManager`.
- Không chứng minh PostgreSQL-specific constraints nếu đang dùng H2.

### 12.2. PurchaseRecordRepositoryTest.java

`src/test/java/com/example/fixturelab/PurchaseRecordRepositoryTest.java`:

~~~java
package com.example.fixturelab;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static com.example.fixturelab.support.PurchaseRecordFixtures.aPurchase;
import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class PurchaseRecordRepositoryTest {

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    PurchaseRecordRepository repository;

    @Test
    void persistsAndReloadsAllImportantFields() {
        PurchaseRecord fixture = aPurchase()
                .withReferenceCode("fixture-db-001")
                .withCustomerId("customer-db-001")
                .withTotal("119.90")
                .withStatus("NEW")
                .build();

        entityManager.persistAndFlush(fixture);
        entityManager.clear();

        PurchaseRecord stored = repository
                .findById("fixture-db-001")
                .orElseThrow();

        assertThat(stored.getReferenceCode())
                .isEqualTo("fixture-db-001");
        assertThat(stored.getCustomerId())
                .isEqualTo("customer-db-001");
        assertThat(stored.getTotal())
                .isEqualByComparingTo("119.90");
        assertThat(stored.getStatus())
                .isEqualTo("NEW");
        assertThat(stored.getCreatedAt())
                .isEqualTo(Instant.parse(
                        "2026-01-15T08:00:00Z"));
    }

    @Test
    void derivedQueryUsesRealDatabaseRows() {
        repository.saveAndFlush(aPurchase()
                .withReferenceCode("fixture-paid-001")
                .withStatus("PAID")
                .build());

        entityManager.clear();

        List<PurchaseRecord> paid =
                repository.findByStatus("PAID");

        assertThat(paid)
                .extracting(PurchaseRecord::getReferenceCode)
                .containsExactly("fixture-paid-001");
    }

    @Test
    void missingReferenceIsEmpty() {
        assertThat(repository.findById("not-present"))
                .isEmpty();
    }
}
~~~

**Tại sao `persistAndFlush` rồi `clear` có ích?**
- `persistAndFlush` gửi SQL xuống database trong test transaction.
- `clear` xóa managed entities khỏi JPA first-level cache.
- Query sau đó phải materialize một entity từ database để kiểm mapping thực tế, thay vì chỉ trả lại object có sẵn trong persistence context.
- `@DataJpaTest` mặc định rollback nên các row fixture thường không tồn tại sau test, tránh thứ tự tests ảnh hưởng lẫn nhau.

**Cảnh báo:** `flush` vẫn **không phải commit**. Nếu logic của test phụ thuộc `@TransactionalEventListener(AFTER_COMMIT)`, deferred constraints hay một connection khác nhìn thấy row, cần thiết kế commit/integration test riêng với `@Commit`/`TestTransaction` và cleanup. Không dùng JPA test default rollback rồi tuyên bố đã kiểm commit.

### 12.3. Factory + persistence helper: đừng trộn trách nhiệm quá mức

Một helper kiểu:

~~~java
PurchaseRecord persistPurchase(
        PurchaseRecordRepository repository,
        String referenceCode) {
    return repository.saveAndFlush(
            aPurchase().withReferenceCode(referenceCode).build());
}
~~~

Đây là snippet, không thuộc runnable project. Nó có ích nếu rất nhiều tests cùng phải persist valid row, nhưng cần **nói rõ side effect** trong tên method. Tránh `aPurchase()` âm thầm gọi database — tên nghe như chỉ tạo object thuần Java mà lại có I/O.

### 12.4. @Sql khi fixture lớn

Spring TestContext hỗ trợ `@Sql` để seed dữ liệu từ scripts:

~~~java
@Test
@Sql("/sql/purchase-fixture.sql")
void reportsPurchasedOrders() {
    // Kiểm query trên committed/uncommitted fixture tùy config.
}
~~~

Đây là snippet tùy chọn: muốn chạy phải tạo `src/test/resources/sql/purchase-fixture.sql` đúng schema. `@Sql` không tự bảo đảm dữ liệu ở transaction riêng; default semantics phụ thuộc active test transaction, `DataSource`/`PlatformTransactionManager` và `@SqlConfig`. Với transactional `@DataJpaTest`, seed scripts thường tham gia test transaction rồi rollback cùng test.

Khi cần commit seed độc lập:

~~~java
@Sql(
    scripts = "/sql/purchase-fixture.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
~~~

Snippet trên cần imports `@Sql` và `@SqlConfig` cùng file resource thật. `ISOLATED` có thể để lại committed rows; phải cleanup trong transaction độc lập, không dùng `@DirtiesContext` như database cleanup.

### 12.5. Quan hệ khóa ngoại và persistence order

Với JPA entity graph có Purchase + Lines + Customer:
- Thiết lập đúng owning side.
- Dùng `cascade` có chủ đích; đừng gắn `CascadeType.ALL` lên mọi association chỉ để seed test nhanh.
- Chú ý `orphanRemoval`, foreign key, NOT NULL/UNIQUE constraints.
- Với identity-generated IDs, gọi `persist`/`flush` đúng thứ tự.
- Đặt test data rõ **quan hệ nào là bắt buộc**; không để builder ngầm thêm nhiều child entities không liên quan.
- Dùng test DB cô lập cho các scenarios cần commit thật hoặc kiểm lock/isolation.

## 13. Full HTTP test: fixture đi qua cả controller và service

### 13.1. QuoteHttpIntegrationTest.java

`src/test/java/com/example/fixturelab/QuoteHttpIntegrationTest.java`:

~~~java
package com.example.fixturelab;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static com.example.fixturelab.support.CartFixtures.vipEligible;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteHttpIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void vipFixtureHasExpectedEndToEndQuote()
            throws Exception {
        Cart input = vipEligible();

        String body = mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(input)))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);

        assertThat(root.path("subtotal").decimalValue())
                .isEqualByComparingTo("120.00");
        assertThat(root.path("discount").decimalValue())
                .isEqualByComparingTo("12.00");
        assertThat(root.path("shipping").decimalValue())
                .isEqualByComparingTo("0.00");
        assertThat(root.path("total").decimalValue())
                .isEqualByComparingTo("108.00");
    }
}
~~~

Test này dùng controller thật + pricing service thật + Jackson HTTP layer thật, nhưng **không mở TCP socket** vì MockMvc là mock servlet request. Nó kiểm dữ liệu meaningful fixture đã sống qua serialization/deserialization và business calculation. Vì pricing không đụng JPA, test không tạo committed row; với service thật ghi DB thì cần chuẩn bị/cleanup tương ứng.

### 13.2. Vì sao không dùng @SpringBootTest cho mọi test?

Pure pricing test rất nhanh và kiểm nhiều boundary. MVC slice kiểm routing/JSON với service mock. Full-context test kiểm một đường liên kết chính. Nếu dùng full context cho mọi invalid quantity/coupon/threshold case, suite sẽ chậm và failure messages khó tách nguyên nhân.

Một lựa chọn tốt:
- 10+ pure unit cases cho business.
- 1–3 MVC slice cases cho JSON contract.
- Vài JPA slice cases cho persisted mappings.
- Một số full-context cases cho cross-layer critical paths.

Số lượng thực tế do rủi ro và complexity, không có chỉ tiêu số test cứng.

## 14. Chạy project và đọc kết quả

### 14.1. Lệnh Maven

Với JDK 17+, Maven và dependency repository:

~~~bash
mvn -q clean test

mvn -q -Dtest=CartFixturesTest test
mvn -q -Dtest=CheckoutPricingServiceTest test
mvn -q -Dtest=QuoteControllerJsonTest test
mvn -q -Dtest=PurchaseRecordRepositoryTest test
mvn -q -Dtest=QuoteHttpIntegrationTest test
~~~

Các class được thiết kế chạy với Spring Boot 3.5.16 và Java 17. Khi Maven thành công, process trả exit code `0`; test reports ở `target/surefire-reports`. **Chưa thực thi Maven trong quá trình biên soạn bài này**, nên phải kiểm build thực tế trên JDK/OS/dependency setup của dự án trước khi coi đây là đã được chạy.

### 14.2. Chạy app để xem response

~~~bash
mvn spring-boot:run
~~~

Terminal khác:

~~~bash
curl -X POST "http://localhost:8080/api/quotes" \
     -H "Content-Type: application/json" \
     -d '{"customerId":"customer-test-001","tier":"REGULAR","lines":[{"sku":"BOOK-001","quantity":2,"unitPrice":50.00}],"couponCode":null}'
~~~

Response JSON dự kiến (object key order/whitespace không phải contract):

~~~json
{
  "subtotal": 100.00,
  "discount": 0.00,
  "shipping": 0.00,
  "total": 100.00
}
~~~

Khi app chưa có handler lỗi domain, request invalid có thể nhận server error status mặc định; đây là giới hạn của lab, không phải khuyến nghị thiết kế REST API. Trong sản phẩm thực, map validation failures thành 400 kèm error DTO theo hợp đồng.

### 14.3. Tại sao không ghi stdout chính xác?

Lệnh `mvn -q clean test` không có một log cố định trên mọi môi trường. Plugin versions, Hibernate SQL logging, OS, JDK và Maven cache ảnh hưởng output. Outcome đáng tin là exit code, Surefire reports, assertions. Với pure unit test, đọc từng named test result thay vì suy từ số dòng console.

## 15. Fixture theo từng loại test

### 15.1. Unit test: ít phụ thuộc nhất

- Tạo cart builder trong memory.
- Không giả lập repository nếu thuật toán không gọi repository.
- Không cần `@SpringBootTest`.
- Dùng data tại ranh giới, invalid input, cấu trúc nhiều lines.
- Expected values được tính độc lập, dễ kiểm review.

### 15.2. MVC slice: fixture là JSON contract

- Tạo request bằng builder, serialize với ObjectMapper để khớp model.
- Giữ controller/Jackson thật, mock service collaborator qua `@MockitoBean`.
- Kiểm HTTP status, Content-Type, JSON fields/types và data passed into service.
- Với malformed JSON/wrong enum/missing required fields, dùng raw JSON deliberately.
- Không cho DTO fixture thay thế test serialization cần kiểm; test phải thực sự send JSON qua MockMvc.

### 15.3. JPA slice: persisted state phải có thật

- Tạo JPA entity fixture mới.
- Save/persist rồi flush trước khi kiểm constraints quan trọng.
- `EntityManager.clear()` nếu muốn chứng minh mapping đọc từ database, tránh first-level cache false positive.
- Test query method thật trên test database.
- Biết `@DataJpaTest` rollback mặc định; đừng thử chứng minh commit-phase events bằng rollback test.
- Khi cần PostgreSQL-specific behavior, dùng Testcontainers và `@AutoConfigureTestDatabase(replace = NONE)`.

### 15.4. Full integration: nhiều lớp có thể cần data khác nhau

Ở full context, helper có thể cần tạo customer, order, lines, payment, outbox. Phân biệt:
- **Entity builder** tạo object.
- **Persistence fixture** ghi entities, có transaction.
- **External fake** giả lập broker/payment/email, có outcome.
- **Scenario** mô tả business state như `anOrderReadyForCapture()`.

Không để một helper mặc định gửi message thật hoặc gọi production provider.

### 15.5. Contract/golden fixtures

Một JSON file lớn có thể hữu ích khi kiểm ổn định response schema. Nhưng tránh snapshot mù:
- Có đường review diff khi contract thay đổi.
- Không overwrite golden file tự động chỉ vì test fail.
- Scrub dynamic UUID/date/PII và secrets.
- Kiểm những property quan trọng bằng explicit assertions.
- Phân biệt strict vs lenient JSON compare (extra fields, array order).

## 16. Các anti-pattern và cách cải thiện

### 16.1. “Fixture khổng lồ biết tất cả”

Một class `TestFixtureManager` chứa builder cho 40 aggregates, đọc file, mở database, gửi Kafka và reset Redis thường biến Given thành một hành động ẩn. Sửa bằng cách tách helpers theo domain/boundary (`CartFixtures`, `PurchaseRecordFixtures`, `FakePaymentGateway`).

### 16.2. Default không hợp lệ

Một builder mặc định `customerId=null`, `quantity=0` bắt mọi test phải override các required fields. Khi thêm field mới, tests lỗi hàng loạt. Sửa: default luôn hợp lệ cho kịch bản phổ biến; negative cases override riêng.

### 16.3. Builder che giấu invalid data

Một builder tự thay quantity 0 thành 1 sẽ làm test “quantity 0 phải bị reject” không bao giờ đi tới validation. Cho phép tạo invalid fixture khi đúng boundary; chỉ production constructor mới giữ invariant theo domain design.

### 16.4. Shared mutable singleton

`static final List<OrderLine> lines = new ArrayList<>()` hoặc `static PurchaseRecord shared` dễ gây order-dependent tests. Dùng factory tạo instance mới, immutable records và List.copyOf.

### 16.5. Giá trị ngẫu nhiên không cần thiết

Random UUID/date trong test snapshot khiến expected khó tái hiện. Chỉ dùng random khi cần uniqueness/coverage, với seed/injected generator và logged seed khi fail. Đối với test ranh giới, fixed values rõ hơn.

### 16.6. Dữ liệu quá “đẹp”

Chỉ test một order có một line và giá tròn 100.00 có thể bỏ sót:
- Nhiều lines/duplicate SKU.
- Unicode, dấu cách, ký tự đặc biệt.
- Decimal rounding 0.01.
- Empty list.
- Max/min allowed size.
- Missing required fields.
- JSON null vs field absent.
- Records ở ranh giới thời gian.

Thêm các cases **theo risk**, không sinh hàng nghìn arbitrary combinations vô nghĩa.

### 16.7. Fixture trả expected calculation từ production helper

Nếu test dùng cùng method tính subtotal với production để sinh expected total, lỗi formula có thể bị sao chép. Dùng scenario numeric example được tính độc lập; assert constants giải thích được.

### 16.8. Fixture tự persist mà tên không nói rõ

Method `aCustomer()` nhưng ngầm save DB tạo side effect khó thấy. Đặt tên `persistCustomer()` hoặc tách `CustomerFixtures.aCustomer()` và repository.save vào Arrange. Rõ ranh giới I/O.

### 16.9. JPA entity chưa flush nhưng test báo PASS

Một assertion chỉ trên Java getter sau `save` không kiểm SQL constraints/mapping. Dùng `persistAndFlush`/`clear` ở test cần đọc state từ DB; xác định commit-time constraints riêng.

### 16.10. Coi @DirtiesContext là database cleanup

`@DirtiesContext` chỉ loại cached Spring application context; không bảo đảm xóa rows của PostgreSQL/shared test DB. Dùng rollback mặc định khi phù hợp, cleanup scripts trong transaction mới hoặc database/container ephemeral.

### 16.11. Dựa vào thứ tự chạy JUnit

Test A seed dữ liệu, test B tìm nó mà không tự Arrange; khi JUnit chạy riêng hoặc parallel, B fail. Mỗi test phải tự tạo dữ liệu cần thiết hoặc dùng lifecycle fixture có scope rõ và isolation.

### 16.12. Test external system bằng production dump

Đưa dump production vào CI có thể vi phạm bảo mật và làm tests phụ thuộc dữ liệu thay đổi. Dùng synthetic fixtures/sanitized datasets được phê duyệt. Đừng bao gồm secrets hoặc thông tin cá nhân trong Markdown, log, snapshot.

### 16.13. Toàn bộ tests dùng @SpringBootTest

Full context cho pure logic thường làm suite chậm, kéo database/network không liên quan và che thiếu dependency injection. Dùng unit và slices ở phần lớn nhánh, full integration ở cross-layer paths quan trọng.

### 16.14. Mọi data fixture dùng builder phức tạp

Nếu cần tạo `new Money("USD", "10.00")`, builder 20 setters không giúp gì. Ưu tiên constructor/value object rõ cho data nhỏ. Builder đáng giá khi có nhiều optional fields, graph phức tạp và defaults hợp lệ.

### 16.15. Test API chỉ so raw JSON string

Whitespace và thứ tự key trong JSON object thường không thuộc contract. Dùng Jackson/JSON-aware matchers. Nhưng khi test HTTP request missing field hay malformed JSON, raw JSON literal là dữ liệu test có chủ đích và hoàn toàn hợp lý.

## 17. Khi dữ liệu phát triển: quản lý version và giảm coupling

### 17.1. Builder không nên sao chép toàn bộ database schema

Tập trung vào field được business/test cần. Nếu DTO production thêm field optional, fixture helper nên có default phù hợp nhưng không tự cho tất cả test cập nhật thêm assertion về field đó. Cần xác định field nào là contract.

### 17.2. Tách test support khỏi main artifact

Đặt fixtures trong `src/test/java` của module đó. Nếu nhiều modules cần dùng chung, có thể tạo test-fixtures artifact/module (Gradle java-test-fixtures hoặc Maven test-jar được cấu hình), nhưng không vô tình expose test dependencies ra runtime production.

### 17.3. Scenario names phải nói ngôn ngữ nghiệp vụ

Tốt:
- `atShippingThreshold()`.
- `vipEligible()`.
- `anExpiredSubscription()`.
- `anInvoiceWithUnpaidBalance()`.
- `aCustomerWithoutAddress()` (negative case).

Kém:
- `sample1()`, `bigObject()`, `fullEntity()`, `testDataForMethod3()`.

Tên nên mô tả điều kiện thật. Nếu thay business rule, một tên sai có thể nguy hiểm hơn một constructor dài vì test reviewer bị hướng sai.

### 17.4. Default nên bị review như code production

Một fixture default không nên đổi âm thầm khi business rule thay đổi. Thay default chỉ khi nó vẫn là trạng thái hợp lệ/thông thường; với scenario buộc giữ điều kiện cũ để kiểm backward compatibility, dùng named factory cố định.

### 17.5. Avoid fixture dependency chain

Một factory `approvedOrder()` gọi `pendingOrder()`, rồi `orderWithCustomer()`, rồi `customerWithAddress()`, rồi DB helper khiến thay đổi nhỏ lan khắp suite. Cần giữ chain ngắn, explicit overrides và đơn vị fixture có trách nhiệm hẹp.

### 17.6. Testcontainers và production-like data

Khi query phụ thuộc PostgreSQL/MySQL/Cassandra semantics, embedded H2 có thể không đủ. Testcontainers cung cấp instance tạm, nhưng bạn vẫn phải:
- Tạo schema/migrations.
- Ghi test data có chủ đích.
- Chọn uniqueness/isolation theo test.
- Cleanup committed fixtures hoặc bỏ container.
- Kiểm container image/version khớp production behavior.

Testcontainers không tự thay thế fixture design; một database thật với dữ liệu vô nghĩa vẫn tạo tests yếu.

## 18. Những vấn đề nâng cao

### 18.1. Test thời điểm hết hạn

Với rule “voucher hết hạn tại 12:00:00Z”, dùng:
- `11:59:59.999Z`.
- `12:00:00Z`.
- `12:00:00.001Z`.

Inject Clock để không phụ thuộc thời gian chạy. Test ở UTC và offset conversion khi contract yêu cầu; không dùng `LocalDateTime.now()` rồi chờ race.

### 18.2. Currency, rounding và precision

Nếu giá là `BigDecimal`:
- Dùng `new BigDecimal("0.10")` thay vì `new BigDecimal(0.1)`.
- Khi so numeric value, `isEqualByComparingTo` phù hợp nếu scale không phải contract.
- Nếu API bắt buộc hai chữ số, có thể kiểm JSON serialization/format riêng.
- Quy tắc rounding phải explicit, ví dụ `RoundingMode.HALF_UP` trong lab.
- Test edgecases giá 0, 0.01, nhiều lines, số lớn/overflow constraints.

### 18.3. Stable ordering

Một list từ repository không có `ORDER BY` không cam kết thứ tự. Test data có thể chứa đúng hai rows nhưng assertion `containsExactly(...)` sai mục tiêu nếu thứ tự không thuộc business contract. Dùng `containsExactlyInAnyOrder(...)` hoặc sắp xếp bằng query rõ. Trong project JPA, `findByStatus("PAID")` chỉ có một row nên không kiểm sort.

### 18.4. Concurrency và uniqueness

Với tests chạy song song trong chung database:
- Dùng per-test data namespace hoặc separate schema/container.
- Không gọi `repository.deleteAll()` trong một test nếu test khác đang dùng DB.
- Không hard-code key có thể trùng ở hai parallel test classes.
- Có thể dùng `UUID.randomUUID()` cho uniqueness nhưng giữ ID sinh ra trong test-local variable và không assert exact literal.
- Không coi static counter là đủ nếu chạy nhiều JVM/test workers.

### 18.5. Testing invalid input ở boundary hợp lý

Nếu production record constructor kiểm invariants, fixture invalid sẽ fail khi Arrange. Test cần **đặt assertion quanh constructor** hoặc dùng raw HTTP input để kiểm bean validation; không viết test mong service xử lý object không thể xây dựng. Trong lab, `CartLine` không tự validate để service có thể kiểm branch trực tiếp.

### 18.6. Data snapshots và migration

Một snapshot JSON/SQL có thể giúp regression lớn nhưng:
- Cần review khi schema thay đổi.
- Không được tự chấp nhận mọi snapshot diff.
- Không chứa session tokens, environment-specific URLs/credentials.
- Có version hợp đồng.
- Phân biệt field biến động (timestamps/IDs) với field bắt buộc.
- Đừng chỉ dùng snapshot toàn payload nếu business decision thực chất phụ thuộc một field nhỏ.

## 19. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Hàng loạt tests fail sau khi thêm field vào DTO | Fixture copy constructor khắp nơi | Gom valid defaults vào builder/factory |
| Test pass dù shipping threshold sai | Dùng subtotal cách xa ngưỡng | Dùng 99.99/100.00/100.01 |
| Test fail phụ thuộc thứ tự | Static mutable fixture/test data còn tồn tại | New instance + rollback/cleanup |
| Date test flaky vào nửa đêm | `now()`/timezone hệ điều hành | Inject `Clock.fixed` |
| Duplicate key JPA khi chạy parallel | Dùng cùng assigned ID | Per-test namespace/database isolation |
| Entity getter PASS nhưng query fail production | Chưa persist/flush/clear | Test repository với DB thật |
| Test @DataJpaTest không tải service | Slice giới hạn component scan | `@Import` có chọn lọc hoặc test boundary khác |
| @WebMvcTest thiếu service | Controller collaborator không có bean | `@MockitoBean` service |
| JSON request test fail mapping | Raw JSON/DTO keys/enum không khớp | ObjectMapper serialize valid fixture, raw JSON cho invalid |
| BigDecimal equality fail | Scale khác 19.9/19.90 | `isEqualByComparingTo` nếu chỉ cần numeric |
| H2 test pass nhưng PostgreSQL fail | SQL dialect/constraint khác | Testcontainers engine tương ứng |
| @Sql seed không được cleanup | Isolated/committed SQL fixture | Cleanup script/transaction rõ |
| List fixture bị mutate | Trả mutable reference | `List.copyOf`/new builder per test |
| Test invalid quantity không tới service | Builder tự sửa/constructor validate sớm | Kiểm đúng validation boundary |
| Parameterized test khó đọc | CSV chứa object graph rối | `@MethodSource` với named fixtures |
| Golden file diff hàng loạt | Dynamic ID/date hoặc snapshot quá rộng | Deterministic data, selective assertions |
| CI lộ PII | Dùng production dump/test logs | Synthetic fixtures và scrub logs |
| Service unit test chậm bất thường | `@SpringBootTest` không cần thiết | Plain JUnit/Mockito |
| Fixture helper gọi DB ngoài ý muốn | Construction và persistence bị trộn | Tách factory và persist helper |

Debug theo thứ tự: **Given** có thật sự đúng scenario? Fixture có tạo object mới? Test gọi SUT hay mock chính SUT? Boundary là pure object/MVC/JPA/full context? Expected được tính độc lập? Database transaction và cleanup có đúng? Chỉ sau đó mới sửa code production.

## 20. Bài tập

1. Viết một test cho shipping threshold chỉ dùng subtotal 1000.00; sau đó cố ý đổi comparison từ `>=` sang `>`. Vì sao test cũ không phát hiện? Thêm 100.00.
2. Thêm scenario `99.99` và `100.01` bằng `@CsvSource`, kiểm kết quả.
3. Viết `aVipCart()` bằng builder, không copy cả constructor.
4. Kiểm default builder tạo object hợp lệ, không chia sẻ mutable list.
5. Thử build Cart rồi sửa builder; chứng minh Cart cũ không đổi.
6. Tạo invalid quantity 0 và negative price; test lỗi ở CheckoutPricingService.
7. Viết test VIP + SAVE10 với subtotal 120.00 và expected total 98.00.
8. Dùng `@MethodSource` cho nhiều object graphs, ghi tên mỗi scenario trong test display name.
9. Thêm injectable Clock cho rule voucher expiry, kiểm trước/đúng/sau mốc hết hạn.
10. Tạo `PurchaseRecordFixtures` default valid và override status PAID để test `findByStatus`.
11. Trong JPA slice, gọi `persistAndFlush` và `clear`; giải thích vì sao không tương đương commit.
12. Seed row bằng `@Sql`, phân biệt default transaction participation và `ISOLATED`.
13. Kiểm JSON request fixture qua `MockMvc` + `ObjectMapper`, dùng captor kiểm Cart được deserialize đúng.
14. Thử mock CheckoutPricingService trong `@WebMvcTest` rồi giải thích test không kiểm pricing algorithm.
15. Viết một full-context test dùng real pricing service và một scenario có subtotal 120.00.
16. Thêm một JPA entity có foreign key, thiết kế builder graph rõ owning side/cascades.
17. Chạy tests song song với fixed assigned ID, quan sát collision và thiết kế isolation.
18. Tạo một snapshot chứa dynamic timestamp, refactor thành Clock.fixed và selective assertions.
19. So sánh Object Mother với Test Data Builder khi model tăng từ 4 lên 20 fields.
20. Review một fixture chứa dữ liệu production và thay nó bằng synthetic values an toàn.

## 21. Checklist review fixture

- [ ] Tên fixture diễn đạt scenario nghiệp vụ cụ thể?
- [ ] Default object hợp lệ cho happy path?
- [ ] Test chỉ override field đang kiểm thay vì thay đổi nhiều biến?
- [ ] Có data ngay dưới/đúng/trên các ngưỡng quan trọng?
- [ ] Có invalid/null/empty/duplicate cases ở boundary phù hợp?
- [ ] Expected được tính độc lập, không sao chép thuật toán production?
- [ ] Mỗi test được tạo instance mới hoặc dùng immutable object?
- [ ] Không có static mutable entity/list chia sẻ giữa tests?
- [ ] List/map fields được defensive copy nếu cần?
- [ ] Builder không “sửa hộ” invalid data đang cần kiểm?
- [ ] Dùng BigDecimal string/precision/rounding đúng contract?
- [ ] Clock/UUID/random có deterministic strategy khi cần?
- [ ] Unit test không tải Spring context vô ích?
- [ ] MVC slice dùng ObjectMapper fixture và giữ controller/Jackson thật?
- [ ] `@MockitoBean` chỉ mock collaborator, không mock SUT?
- [ ] JPA slice persist/flush/clear khi cần chứng minh mapping?
- [ ] `@DataJpaTest` rollback mặc định đã được hiểu?
- [ ] Committed DB fixtures có cleanup hoặc ephemeral database?
- [ ] `@Sql` scripts và transaction scope rõ?
- [ ] Test không dựa vào JUnit method order?
- [ ] Tests chạy parallel có unique IDs/isolation?
- [ ] Không dùng production secrets/PII trong fixtures?
- [ ] Snapshot/golden files được review có chủ đích?
- [ ] Có test command và Surefire report để xác nhận thực tế?

**Kết luận:** Fixture tốt không phải object có nhiều field nhất, mà là dữ liệu **làm rõ điều kiện của một phép kiểm**. Dùng Test Data Builder với default hợp lệ, named scenario factories cho những case quan trọng và fixtures mới cho từng test. Chọn các giá trị ranh giới đủ nhạy để phát hiện bug; giữ identity/time/money deterministic. Ở unit test, object fixture đủ; ở MVC, phải đi qua JSON mapping; ở JPA, phải thực sự persist/query để kiểm schema và repository. Dữ liệu có ý nghĩa và phạm vi đúng giúp test vừa ít brittle vừa phát hiện lỗi thật.

## 22. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — DataJpaTest API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Framework 6.2 — @MockitoBean/@MockitoSpyBean: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework 6.2 — TestContext Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — @Sql, SQL script execution: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- JUnit 5 User Guide — Parameterized Tests: https://docs.junit.org/current/user-guide/#writing-tests-parameterized-tests
- AssertJ — Core assertions guide: https://assertj.github.io/doc/
- Spring Data JPA — Repositories and Testing: https://docs.spring.io/spring-data/jpa/reference/
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Java 17 — Records (JLS): https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
