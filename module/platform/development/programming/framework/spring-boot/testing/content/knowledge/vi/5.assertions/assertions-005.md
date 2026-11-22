# So sánh đối tượng theo thuộc tính và recursive comparison trong kiểm thử Spring Boot

## 1. Mục tiêu bài học

Một phép kiểm thử thường cần xác nhận rằng kết quả của service, controller hoặc repository **đúng ở những thuộc tính quan trọng**, chứ không phải cùng tham chiếu bộ nhớ với một đối tượng expected. Khi cấu trúc dữ liệu có đối tượng lồng nhau, danh sách, timestamp, ID sinh tự động hoặc các kiểu có quy tắc bằng nhau đặc biệt như `BigDecimal`, việc chọn phép assertion quyết định độ tin cậy của test.

Sau bài này, bạn có thể:
- Phân biệt `isSameAs`, `isEqualTo`, kiểm từng thuộc tính, `extracting` và `usingRecursiveComparison`.
- Dùng AssertJ để kiểm field/property của một đối tượng; chọn các trường từ danh sách bằng `extracting`, `tuple` và `flatExtracting`.
- So sánh toàn bộ cây đối tượng, kể cả phần tử collection, với báo cáo sai khác ở đường dẫn trường lồng nhau.
- Điều chỉnh rõ ràng những phần cần bỏ qua (ID, timestamp), thứ tự collection, `null`, comparator và loại đối tượng.
- Tránh assertion “xanh giả” khi bỏ qua quá nhiều trường, so sánh nhầm thứ tự, dùng `equals` không đúng nghĩa hoặc so dữ liệu database bằng `BigDecimal.equals`.
- Đưa phép so sánh vào unit/slice/integration test Spring Boot một cách đủ ổn định.

Ngữ cảnh: Java 17+, JUnit Jupiter 5, AssertJ Core 3.27.x (ví dụ Maven dùng Spring Boot 3.5.7 quản lý `assertj-core` 3.27.6). Toàn bộ mã chạy ở phần thực hành là **JUnit test không cần khởi động Spring context**, vì assertion bản chất là kiểm tra giá trị Java. Trong test Spring Boot, cách viết assertion tương tự sau khi nhận kết quả từ `@SpringBootTest`, `@WebMvcTest` hoặc `@DataJpaTest`.

## 2. Năm cách hiểu từ “bằng nhau”

Giả sử service trả về hai đối tượng `OrderView` có nội dung như nhau nhưng được tạo độc lập:

| Cách kiểm | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `assertThat(actual).isSameAs(expected)` | Hai biến trỏ tới **cùng một đối tượng** (`==`) | Contract về identity, cache, singleton, tham chiếu |
| `assertThat(actual).isEqualTo(expected)` | Dùng semantics `equals` của kiểu dữ liệu | Value object/record có `equals` đúng contract |
| `assertThat(actual.getStatus()).isEqualTo("PAID")` | Kiểm trực tiếp một giá trị | Chỉ một thuộc tính là hành vi cần xác nhận |
| `assertThat(actual).extracting(...).isEqualTo(...)` | Chọn thuộc tính từ object hoặc từ nhiều phần tử | Chỉ một/một nhóm field quan trọng, projection dễ hiểu |
| `assertThat(actual).usingRecursiveComparison().isEqualTo(expected)` | Duyệt cấu trúc field và so nội dung lồng nhau | DTO, response snapshot, entity graph cần kiểm **nhiều trường** |

### 2.1. Identity khác equality

```java
record Money(String currency, long minorUnits) {}

Money a = new Money("VND", 50_000);
Money b = new Money("VND", 50_000);

// a == b là false: hai đối tượng được tạo độc lập.
// a.equals(b) là true vì record sinh equals theo components.
// AssertJ:
assertThat(a).isEqualTo(b);
assertThat(a).isNotSameAs(b);
```

Đây là **đoạn minh họa** cần đặt trong phương thức Java và import `org.assertj.core.api.Assertions.assertThat`. `record` sinh sẵn `equals`/`hashCode` theo components; một class Java thông thường không override `equals` thì thừa hưởng `Object.equals`, nên hai instance có field giống nhau vẫn có thể `isNotEqualTo`.

### 2.2. Đừng ép mọi model phải override `equals` vì test

JPA entity thường dùng ID/identity hoặc quy tắc `equals` riêng; DTO có thể dùng Java record, còn object từ REST client có thể không override `equals`. Nếu test chỉ cần kiểm response fields, dùng projection/recursive comparison là phù hợp; không thay đổi semantics `equals` của domain chỉ để làm cho `assertEquals(expected, actual)` “xanh”.

Sự khác nhau quan trọng:
- **`equals` là một phần semantics của kiểu dữ liệu** (có thể chỉ quan tâm ID).
- **Recursive comparison là chính sách của một assertion cụ thể** (có thể quan tâm tất cả field trừ ID/timestamp).
- **Property extraction là lựa chọn rõ ràng một projection** (có thể chỉ so tên và trạng thái).

Không có phép so sánh nào “tốt nhất” cho mọi mục tiêu. Chọn theo contract đang kiểm.

## 3. So sánh theo thuộc tính: trực tiếp, `extracting`, `satisfies`

### 3.1. Trực tiếp qua getter/accessor

Với response record:

```java
record Address(String city, String street) {}
record Buyer(String name, Address address) {}
record OrderView(long id, String status, Buyer buyer) {}

// Mã minh họa nằm trong test method:
var order = new OrderView(101L, "PAID",
        new Buyer("An", new Address("Hà Nội", "Tràng Tiền")));

assertThat(order.status()).isEqualTo("PAID");
assertThat(order.buyer().address().city()).isEqualTo("Hà Nội");
```

Ưu điểm: dễ hiểu, kiểm tra kiểu dữ liệu lúc biên dịch, refactor đổi tên accessor được IDE phát hiện. Nhược điểm: dài nếu hàng chục trường.

### 3.2. Dùng `extracting(Function)`

```java
assertThat(order)
        .extracting(OrderView::status)
        .isEqualTo("PAID");

assertThat(order)
        .extracting(o -> o.buyer().address().city())
        .isEqualTo("Hà Nội");
```

`extracting` không biến object thành chuỗi. Nó **lấy giá trị được chọn** để áp dụng assertion thích hợp. Lambda/method reference được kiểm tra kiểu lúc compile; đây là mặc định tốt khi mô hình có accessor công khai.

### 3.3. Dùng tên field/property dạng chuỗi

```java
assertThat(order)
        .extracting("buyer.address.city")
        .isEqualTo("Hà Nội");

assertThat(order)
        .hasFieldOrPropertyWithValue("status", "PAID");
```

Tên dạng chuỗi cho phép đường dẫn lồng nhau ngắn gọn. AssertJ thử resolve property/field và có thể truy cập field không public theo cấu hình mặc định; nó không phải JSONPath. Với `record`, tên component cũng là tên field trong cấu trúc JVM, dù accessor kiểu `city()` không phải getter JavaBean `getCity()`. Kết quả còn có thể bị ảnh hưởng bởi chính sách reflection/JPMS; lambda thường rõ ràng hơn.

Rủi ro: sai tên `"buyer.adress.city"` chỉ được phát hiện khi test chạy. Sau refactor, compiler không giúp đổi tên string path. Không dùng string-path dài khi accessor có thể diễn đạt contract ngắn gọn.

### 3.4. Nhiều assertion trên cùng một object

```java
assertThat(order).satisfies(o -> {
    assertThat(o.id()).isPositive();
    assertThat(o.status()).isEqualTo("PAID");
    assertThat(o.buyer().name()).isEqualTo("An");
});
```

`satisfies` hợp lý cho 2–4 điều kiện khác loại, chẳng hạn ID mới sinh phải dương, trạng thái đúng và khách hàng đã chuẩn hóa. Khi muốn xem **tất cả lỗi** trong cùng một lượt thay vì dừng ở lỗi đầu tiên, cân nhắc `SoftAssertions` và nhớ gọi `assertAll()`.

### 3.5. Dùng `as(...)` mô tả ý nghĩa thất bại

```java
assertThat(order.status())
        .as("trạng thái đơn hàng %s", order.id())
        .isEqualTo("PAID");
```

Mô tả này đi kèm thông báo assertion khi thất bại, hữu ích khi nhiều object có cấu trúc tương tự. Tránh đưa access token, mật khẩu hoặc dữ liệu nhạy cảm vào label/log.

## 4. Projection trên collection: `extracting`, tuple và thứ tự

Một response trả về danh sách thường cần so **chính các thuộc tính của mỗi phần tử**. Xây dựng đối tượng expected nguyên vẹn có thể dài và vô tình biến test thành bản sao của implementation.

### 4.1. Chọn một thuộc tính

```java
var orders = List.of(
        new OrderView(101L, "PAID", buyer),
        new OrderView(102L, "PENDING", buyer)
);

assertThat(orders)
        .extracting(OrderView::id)
        .containsExactly(101L, 102L);
```

Đây là projection `List<OrderView> → List<Long>` (biểu diễn ý tưởng), rồi assert danh sách ID. `containsExactly` kiểm **đủ phần tử, đúng giá trị, đúng thứ tự**. Nếu API không cam kết thứ tự, dùng `containsExactlyInAnyOrder` thay vì phụ thuộc query tình cờ đang trả theo thứ tự PK.

### 4.2. Chọn nhiều thuộc tính với `tuple`

```java
import static org.assertj.core.api.Assertions.tuple;

assertThat(orders)
        .extracting("id", "status")
        .containsExactly(
                tuple(101L, "PAID"),
                tuple(102L, "PENDING"));
```

Mỗi phần tử sinh ra một `Tuple` chứa các giá trị theo đúng thứ tự các tên trường. Vì dùng string path nên có rủi ro refactor; AssertJ cũng có overload nhận nhiều `Function` để an toàn kiểu hơn:

```java
assertThat(orders)
        .extracting(OrderView::id, OrderView::status)
        .containsExactly(
                tuple(101L, "PAID"),
                tuple(102L, "PENDING"));
```

Đoạn trên là **minh họa bên trong một test có sẵn biến `orders`**. Khi so một vài cột rõ ràng, tuple là lựa chọn thường dễ đọc hơn dựng toàn bộ object và ignore nhiều field.

### 4.3. `extracting` với collection lồng nhau khác `flatExtracting`

Giả sử `OrderView` có `List<Line> lines`:
- `extracting(OrderView::lines)` trên `List<OrderView>` tạo kết quả **mỗi phần tử là một danh sách lines**.
- `flatExtracting(OrderView::lines)` “trải phẳng” nhiều danh sách thành một chuỗi phần tử có thể assert trực tiếp.

```java
// Trong test có biến ordersWithLines:
assertThat(ordersWithLines)
        .flatExtracting(OrderView::lines)
        .extracting(Line::sku)
        .contains("BK-1", "PN-2");
```

Chỉ dùng `flatExtracting` khi mục tiêu thực sự là tập hợp các phần tử con **bất kể thuộc order nào**. Nếu ràng buộc “mỗi đơn hàng phải có các dòng riêng”, flatten sẽ làm mất quan hệ cha–con; khi đó assert từng order hoặc recursive comparison trên cả cây.

### 4.4. Chọn đúng ngữ nghĩa collection

| Assertion | Kiểm điều gì |
| --- | --- |
| `contains(...)` | Có các phần tử được nêu, có thể có phần tử khác |
| `containsOnly(...)` | Chỉ những phần tử được nêu (không khẳng định thứ tự; xem semantics số lần lặp) |
| `containsExactly(...)` | Đúng nội dung, đúng thứ tự, kể cả số lần xuất hiện |
| `containsExactlyInAnyOrder(...)` | Đúng nội dung và số lần xuất hiện; không quan tâm thứ tự |
| `anySatisfy(...)` | Ít nhất một phần tử đáp ứng điều kiện |
| `allSatisfy(...)` | Mọi phần tử đáp ứng điều kiện |

Với REST endpoint có `ORDER BY`/sort parameter được công bố, thứ tự là contract và nên assert bằng `containsExactly`. Với query trả danh sách không có `ORDER BY`, thứ tự không được bảo đảm: không được viết assertion phụ thuộc thứ tự đang thấy trên H2 hoặc CI.

## 5. Recursive comparison: đi sâu theo cây object

`usingRecursiveComparison()` tạo phép so field-by-field sâu, có thể đi vào nhiều tầng lồng nhau và collection. Ví dụ:

```text
OrderView
├── id
├── status
├── buyer
│   ├── name
│   └── address
│       ├── city
│       └── street
├── lines [Line("BK-1"), Line("PN-2")]
│   ├── sku
│   ├── quantity
│   └── price
├── total
├── createdAt
└── traceId
```

Nếu `buyer.address.city` khác giữa actual và expected, recursive comparison có thể báo đường dẫn trường bị sai. AssertJ so sánh cấu trúc sâu thay vì dựa hoàn toàn vào `equals` của object gốc. Tuy nhiên đối với kiểu hệ thống như `java.lang.String`, `BigDecimal`, `Instant`, AssertJ sẽ áp dụng quy tắc so giá trị hoặc comparator phù hợp chứ không mở reflection vào mọi field nội bộ JDK.

### 5.1. So sánh mặc định

```java
assertThat(actual)
        .usingRecursiveComparison()
        .isEqualTo(expected);
```

Khi các trường tương ứng cùng giá trị và collection có thứ tự đúng theo chính sách mặc định, phép kiểm qua. Khi object root khác kiểu nhưng có cấu trúc field phù hợp, recursive comparison có thể vẫn so sánh được (mặc định linh hoạt hơn `equals`). Điều này hữu ích khi so DTO với entity, nhưng cũng dễ che giấu việc so nhầm loại đối tượng. Nếu type chính là một phần contract, có thể thêm `withStrictTypeChecking()` hoặc kiểm `isInstanceOf(...)` riêng.

### 5.2. Bỏ qua các trường biến động, có chủ đích

```java
assertThat(actual)
        .usingRecursiveComparison()
        .ignoringFields("id", "createdAt", "traceId")
        .isEqualTo(expected);
```

Đây là giải pháp khi ID, audit timestamp hoặc correlation ID được sinh tự động nhưng mục tiêu test là quy tắc nghiệp vụ và cấu trúc response. Đường dẫn lồng nhau cũng được hỗ trợ, chẳng hạn `"buyer.address.street"`. Sau khi ignore ID, **vẫn nên có phép kiểm riêng** nếu contract yêu cầu ID phải tồn tại/hợp lệ.

Không sử dụng `ignoringFieldsMatchingRegexes(".*")` hoặc ignore rộng chỉ để test qua: assertion có thể trở thành rỗng. Khi chỉ cần 2–3 thuộc tính, `extracting` thường an toàn và rõ hơn.

### 5.3. Thứ tự collection: mặc định và khi nào bỏ qua

Với `List`, thứ tự các phần tử thường ảnh hưởng kết quả so sâu. Nếu domain xem các dòng hàng là một tập không có thứ tự:

```java
assertThat(actual)
        .usingRecursiveComparison()
        .ignoringCollectionOrderInFields("lines")
        .isEqualTo(expected);
```

`ignoringCollectionOrder()` bỏ qua thứ tự trên **mọi collection** bên trong object; chỉ nên dùng khi domain thực sự không có trật tự ở tất cả các nơi. `ignoringCollectionOrderInFields("lines")` hẹp hơn và bảo vệ các danh sách vẫn cần thứ tự như timeline, bước workflow hoặc kết quả search có sort.

Bỏ qua thứ tự có chi phí tính toán cao hơn; đối chiếu nhiều phần tử có thể cần nhiều phép so cặp (mô tả thông thường là xấp xỉ bậc \(O(n^2)\) trong các trường hợp phổ biến). Với danh sách lớn, nên kiểm một projection có key ổn định hoặc kiểm có phân nhóm, và chỉ dùng cấu hình bỏ thứ tự nơi cần.

### 5.4. `null` không phải “bỏ qua hết trường thiếu”

Các API có ý nghĩa khác nhau:

| Cấu hình | Trường nào bị bỏ qua? | Cảnh báo |
| --- | --- | --- |
| Không cấu hình | `null` vẫn được so với `null`/non-null | Có thể đúng nhất cho contract đầy đủ |
| `ignoringActualNullFields()` | Field có giá trị `null` **ở actual** | Dễ che lỗi service trả thiếu dữ liệu |
| `ignoringExpectedNullFields()` | Field có giá trị `null` **ở expected** | Có thể dùng partial expected, nhưng không kiểm field đó |
| `ignoringActualEmptyOptionalFields()` | Một số `Optional` rỗng **ở actual** | Khác với null; chỉ áp dụng khi có lý do rõ |

Hai phía actual/expected **không đối xứng** khi áp dụng các cấu hình này. `ignoringExpectedNullFields()` đặc biệt hữu ích nếu expected chỉ mô tả một phần response, nhưng nếu chỉ vài trường có ý nghĩa thì `extracting`/`satisfies` thường thể hiện intent rõ hơn.

### 5.5. Comparator tùy biến cho loại dữ liệu đặc biệt

`BigDecimal.equals` phân biệt scale: `new BigDecimal("120.0")` **không bằng** `new BigDecimal("120.00")` theo `equals`, dù hai giá trị bằng nhau về số học. Khi domain chỉ quan tâm giá trị số:

```java
assertThat(new BigDecimal("120.0"))
        .isEqualByComparingTo("120.00");

// Khi total là một field trong object:
assertThat(actual)
        .usingRecursiveComparison()
        .withComparatorForFields(BigDecimal::compareTo, "total")
        .isEqualTo(expected);
```

Đặt comparator đúng trường nếu đơn vị khác nhau có chính sách khác nhau. `withComparatorForType(BigDecimal::compareTo, BigDecimal.class)` tác động lên mọi trường kiểu `BigDecimal` trong phép so; dùng khi cả domain cùng semantics. Với tiền tệ, không được bỏ qua currency hoặc đổi số một cách tùy ý: `100 USD` không bằng `100 VND`.

Với `Instant`/`LocalDateTime` khi có sai số hợp lệ do clock/database precision, cấu hình comparator có tolerance **được định nghĩa theo yêu cầu**; không dùng tolerance lớn một cách ngẫu nhiên. Một số trường như token, hash, version, ID cần so chính xác, không nên so “gần đúng”.

### 5.6. `equals` đã bị override thì sao?

Trong AssertJ 3.27.x, recursive comparison mặc định đi theo field của kiểu ứng dụng ngay cả khi kiểu đó override `equals`; các kiểu Java/JDK có cơ chế so riêng. Nếu **muốn** dùng `equals` đã override cho các field, AssertJ có `usingOverriddenEquals()`. Khi đã chọn cách đó, có thể ép một vài field/type vẫn so sâu bằng `ignoringOverriddenEqualsForFields(...)` hoặc `ignoringOverriddenEqualsForTypes(...)`.

Hãy nêu rõ contract:
- Nếu `Address.equals` chỉ so postcode, việc dùng `equals` có thể bỏ qua khác biệt street.
- Nếu test cần mọi chi tiết địa chỉ, recursive fields là đúng.
- Nếu kiểu là value object với `equals` đã mô tả đầy đủ contract, dùng `isEqualTo` hoặc chủ động `usingOverriddenEquals()` là cách hợp lý.

Tránh các API cũ như `isEqualToComparingFieldByFieldRecursively` khi thư viện hiện có `usingRecursiveComparison()`; API mới cho cấu hình và thông báo sai khác tốt hơn.

### 5.7. Chu trình tham chiếu và JPA proxy

AssertJ recursive comparison có xử lý đồ thị đối tượng có vòng tham chiếu, nhưng không vì thế mà nên đưa **entire entity graph** vào assertion. Với Hibernate/JPA:
- Lazy relationship có thể bị khởi tạo ngoài ý muốn, phát sinh SQL/N+1 hoặc `LazyInitializationException`.
- Hibernate proxy, bidirectional mapping, equals/hashCode của entity và audit fields có thể làm test nặng hoặc khó đọc.
- So DTO projection đã xác định contract thường rõ hơn so mọi field của managed entity.
- Nếu test persistence cần kiểm quan hệ thật, load trạng thái cần thiết trong transaction và assert đúng field/association, tránh dựa vào internal proxy fields.
- Đối tượng chứa stream, socket, thread, lock hoặc bean framework không nên đem so recursive như data model.

## 6. Thực hành tự chạy: Maven + JUnit 5 + AssertJ

Phần này là một **bài hoàn chỉnh, có thể copy chạy**; mọi test đều thành công nếu source và dependency đúng. Ta dùng Java record để thấy rõ dữ liệu lồng nhau, đồng thời phân biệt so theo `equals` và so theo chính sách recursive.

### 6.1. Cấu trúc

```text
assertion-lab/
├── pom.xml
└── src/test/java/com/example/assertions/
    └── OrderComparisonTest.java
```

Maven không cần application class để chạy bộ JUnit thuần. Khi nhúng vào ứng dụng Spring Boot thật, đặt test trong test source set tương ứng; thêm `@SpringBootTest` chỉ khi chính hành vi được kiểm cần context.

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>assertion-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
```

`spring-boot-starter-test` cung cấp JUnit Jupiter và AssertJ ở test classpath. Với Spring Boot parent/BOM, không cần tự pin version AssertJ. Nếu dự án đang dùng Spring Boot/AssertJ khác, kiểm tra dependency tree để xem phiên bản thật:

```bash
mvn dependency:tree -Dincludes=org.assertj:assertj-core
mvn -q -Dtest=OrderComparisonTest test
mvn -q test
```

Test thành công khi Maven exit code 0; log và số dòng stdout phụ thuộc Maven/JDK/máy nên không đặt kỳ vọng một chuỗi stdout cố định.

### 6.3. `src/test/java/com/example/assertions/OrderComparisonTest.java`

```java
package com.example.assertions;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.assertj.core.api.SoftAssertions;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

class OrderComparisonTest {

    record Address(String city, String street) {}
    record Buyer(String name, Address address) {}
    record Line(String sku, int quantity, BigDecimal price) {}

    record OrderView(
            Long id,
            String status,
            Buyer buyer,
            List<Line> lines,
            BigDecimal total,
            Instant createdAt,
            String traceId) {}

    private static OrderView actualOrder() {
        return new OrderView(
                101L,
                "PAID",
                new Buyer("An", new Address("Hà Nội", "Tràng Tiền")),
                List.of(
                        new Line("BK-1", 2, new BigDecimal("50.00")),
                        new Line("PN-2", 1, new BigDecimal("20.00"))),
                new BigDecimal("120.00"),
                Instant.parse("2026-11-08T06:00:00Z"),
                "request-actual");
    }

    private static OrderView sameBusinessData() {
        return new OrderView(
                999L, // khác ID sinh bởi database
                "PAID",
                new Buyer("An", new Address("Hà Nội", "Tràng Tiền")),
                List.of(
                        new Line("BK-1", 2, new BigDecimal("50.00")),
                        new Line("PN-2", 1, new BigDecimal("20.00"))),
                new BigDecimal("120.0"), // khác scale với actual
                Instant.parse("2026-11-08T07:00:00Z"),
                "request-expected");
    }

    @Test
    void checksSelectedProperties() {
        OrderView actual = actualOrder();

        assertThat(actual.status()).isEqualTo("PAID");
        assertThat(actual)
                .extracting(OrderView::status)
                .isEqualTo("PAID");
        assertThat(actual)
                .extracting("buyer.address.city")
                .isEqualTo("Hà Nội");
        assertThat(actual)
                .hasFieldOrPropertyWithValue("status", "PAID");
        assertThat(actual.id()).as("ID được sinh").isPositive();
    }

    @Test
    void projectsListToValuesAndTuples() {
        OrderView paid = actualOrder();
        OrderView pending = new OrderView(
                102L, "PENDING", paid.buyer(), List.of(),
                BigDecimal.ZERO, paid.createdAt(), "request-two");
        List<OrderView> orders = List.of(paid, pending);

        assertThat(orders)
                .extracting(OrderView::id)
                .containsExactly(101L, 102L);

        assertThat(orders)
                .extracting("id", "status")
                .containsExactly(
                        tuple(101L, "PAID"),
                        tuple(102L, "PENDING"));

        assertThat(paid.lines())
                .extracting(Line::sku)
                .containsExactly("BK-1", "PN-2");
    }

    @Test
    void comparesNestedObjectsIgnoringGeneratedFields() {
        OrderView actual = actualOrder();
        OrderView expected = sameBusinessData();

        // Record.equals() thấy ID/time/traceId/BigDecimal scale khác nhau.
        assertThat(actual).isNotEqualTo(expected);

        // Chỉ bỏ qua trường phát sinh, tự định nghĩa scale semantics của total.
        assertThat(actual)
                .usingRecursiveComparison()
                .ignoringFields("id", "createdAt", "traceId")
                .withComparatorForFields(BigDecimal::compareTo, "total")
                .isEqualTo(expected);
    }

    @Test
    void ignoresOrderOnlyForLineItems() {
        OrderView original = actualOrder();

        OrderView reversed = new OrderView(
                original.id(),
                original.status(),
                original.buyer(),
                List.of(original.lines().get(1), original.lines().get(0)),
                original.total(),
                original.createdAt(),
                original.traceId());

        assertThat(reversed)
                .usingRecursiveComparison()
                .ignoringCollectionOrderInFields("lines")
                .isEqualTo(original);
    }

    @Test
    void expectedNullFieldsCanMeanUnspecified() {
        OrderView actual = actualOrder();
        OrderView expected = new OrderView(
                null,
                "PAID",
                actual.buyer(),
                actual.lines(),
                actual.total(),
                null,
                null);

        assertThat(actual)
                .usingRecursiveComparison()
                .ignoringExpectedNullFields()
                .isEqualTo(expected);

        // Vì ID đã bị bỏ qua khỏi recursive comparison,
        // kiểm contract ID độc lập:
        assertThat(actual.id()).isNotNull().isPositive();
    }

    @Test
    void actualNullFieldsCanBeIgnoredButShouldBeIntentional() {
        OrderView complete = actualOrder();
        OrderView incomplete = new OrderView(
                complete.id(),
                complete.status(),
                complete.buyer(),
                complete.lines(),
                complete.total(),
                complete.createdAt(),
                null);

        assertThat(incomplete)
                .usingRecursiveComparison()
                .ignoringActualNullFields()
                .isEqualTo(complete);

        // Đoạn so trên không chứng minh traceId có mặt.
        assertThat(incomplete.traceId()).isNull();
    }

    @Test
    void comparesNumericValueRatherThanBigDecimalScale() {
        BigDecimal one = new BigDecimal("120.0");
        BigDecimal two = new BigDecimal("120.00");

        assertThat(one).isNotEqualTo(two); // BigDecimal.equals tính scale
        assertThat(one).isEqualByComparingTo("120.00");
    }

    @Test
    void softAssertionsCollectIndependentFailures() {
        OrderView actual = actualOrder();

        SoftAssertions softly = new SoftAssertions();
        softly.assertThat(actual.status()).isEqualTo("PAID");
        softly.assertThat(actual.buyer().name()).isEqualTo("An");
        softly.assertThat(actual.lines())
                .extracting(Line::quantity)
                .containsExactly(2, 1);
        softly.assertAll();
    }
}
```

### 6.4. Phân tích từng test và kết quả

| Test | Điều được chứng minh | Điều **chưa** được chứng minh |
| --- | --- | --- |
| `checksSelectedProperties` | Accessor, field/property extraction và assert ID | Toàn bộ graph, tính bền vững DB |
| `projectsListToValuesAndTuples` | Projection của list; số lượng, thứ tự, cặp ID/status | Mọi field của mỗi item |
| `comparesNestedObjectsIgnoringGeneratedFields` | Cấu trúc business tương đương qua nested fields, bất kể ID/time/trace và scale total | ID/time thực sự hợp lệ nếu không assert riêng |
| `ignoresOrderOnlyForLineItems` | Nội dung lines không phụ thuộc thứ tự | Thứ tự lines (vì đã bỏ qua theo chủ đích) |
| `expectedNullFieldsCanMeanUnspecified` | Expected có thể là partial template; ID kiểm riêng | Giá trị createdAt/traceId |
| `actualNullFieldsCanBeIgnoredButShouldBeIntentional` | Cách bỏ qua null ở actual hoạt động; test còn assert null rõ ràng | Không được hiểu là đủ mọi field bắt buộc |
| `comparesNumericValueRatherThanBigDecimalScale` | Hai giá trị số tương đương dù scale khác | Quy định số chữ số thập phân hiển thị/lưu DB |
| `softAssertionsCollectIndependentFailures` | Các điều kiện độc lập và `assertAll()` | Không thay thế phép so sâu nếu toàn bộ graph là contract |

Nhìn vào ví dụ sẽ thấy: **không có một phép recursive duy nhất đủ bảo vệ mọi contract**. Nó mạnh khi cần kiểm nhiều trường; sau khi ignore dynamic fields, vẫn phải assert yêu cầu độc lập.

### 6.5. Thử một assertion cố ý thất bại để học đọc diff

Trong một bản copy của test, thay city trong expected thành `"Huế"` nhưng giữ lại assertion recursive. Chạy:

```bash
mvn -Dtest=OrderComparisonTest#comparesNestedObjectsIgnoringGeneratedFields test
```

Khi expected khác actual ở `buyer.address.city`, test phải **FAIL**. AssertJ thường nêu đường dẫn field và actual/expected (cách trình bày cụ thể phụ thuộc phiên bản). Diễn giải sai khác:

```text
buyer.address.city:
  actual   = "Hà Nội"
  expected = "Huế"
```

Khối trên là **minh họa ý nghĩa diff, không phải stdout nguyên văn**. Sau thực nghiệm, khôi phục `"Hà Nội"` để bộ test trở lại PASS. Khi cần chẩn đoán, đọc đường dẫn field trước khi sửa `equals` hoặc thêm `ignoringFields`.

## 7. Đặt assertion ở đúng chỗ trong Spring Boot

Cách viết AssertJ giống nhau giữa unit và integration, nhưng **đối tượng được quan sát** và ý nghĩa của kết quả khác nhau.

### 7.1. Unit test của service/domain

Nên ưu tiên:
- Giá trị trả về và bất biến nghiệp vụ: status, amount, line quantities, ownership.
- Projection vài field quan trọng: `extracting` hoặc `satisfies`.
- Recursive comparison khi service tạo DTO có cây dữ liệu tương đối ổn định.
- Không assert cả Spring bean, proxy, repository object hoặc internal framework state.

Ví dụ service trả `OrderView`:
```java
// Minh họa bên trong test; service và request được xây dựng theo ứng dụng thật.
OrderView actual = service.createOrder(request);

assertThat(actual.id()).isPositive();
assertThat(actual)
        .usingRecursiveComparison()
        .ignoringFields("id", "createdAt", "traceId")
        .isEqualTo(expectedOrder);
```

Trong code trên `service`, `request`, `expectedOrder` là biến **của dự án thực tế**, không phải phần tiếp nối của file chạy độc lập ở mục 6. Nếu bỏ qua ID vì ID được sinh, hãy giữ kiểm `isPositive()`/`isNotNull()` phù hợp với contract.

### 7.2. Web slice: kiểm contract JSON trước

Với `@WebMvcTest` và `MockMvc`, mục tiêu chính là HTTP status, header, JSON path, validation và exception mapping. Khi chỉ có JSON:

```java
// Minh họa với MockMvc đã được inject trong @WebMvcTest:
mvc.perform(get("/orders/101"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.buyer.address.city").value("Hà Nội"));
```

Đoạn trên cần static import `get`, `status`, `jsonPath` trong lớp test Spring MVC thực tế. Đừng parse JSON thành một object chỉ để recursive comparison nếu 2–3 JSONPath đã nói rõ contract; cũng đừng so tất cả response fields bằng snapshot bất biến nếu API có trace/links/timestamps động.

Khi so JSON snapshot thật sự có giá trị, có thể deserialize về DTO và dùng AssertJ. Nhớ xác định semantics cho missing field, null field, number type và thứ tự array — JSONPath/JSON structural assertions và recursive Java object comparison không phải hoàn toàn tương đương.

### 7.3. Repository/JPA slice: kiểm dữ liệu lưu và tải lại

Với `@DataJpaTest`, lấy entity từ repository sau `flush` và khi cần thì `clear` persistence context để tránh đọc lại chính managed entity đang có trong bộ nhớ. Sau đó so **những field database phải bảo toàn**. Ví dụ:

```java
// Minh họa: repository và entityManager được inject trong JPA test.
repository.saveAndFlush(entity);
entityManager.clear();
var loaded = repository.findById(entity.getId()).orElseThrow();

assertThat(loaded.getStatus()).isEqualTo("PAID");
assertThat(loaded.getLines())
        .extracting(OrderLineEntity::getSku)
        .containsExactlyInAnyOrder("BK-1", "PN-2");
```

Đoạn này là **pattern minh họa**, không chạy độc lập vì entity/repository/EntityManager thuộc dự án. Chỉ dùng `containsExactly` cho lines khi mapping và truy vấn có `@OrderColumn`, `@OrderBy` hoặc contract bảo đảm thứ tự; mặc định quan hệ collection không đồng nghĩa với “theo thứ tự insert”.

Tránh recursive comparison toàn entity graph khi entity có lazy proxy, bidirectional relation, soft-delete flags, version, audit fields hoặc hạ tầng persistence nội bộ. Có thể map sang DTO trước rồi compare, hoặc assert trực tiếp các field/association có ý nghĩa.

### 7.4. Integration test: kết quả quan sát được qua nhiều tầng

Khi `@SpringBootTest` kiểm hành trình tạo order qua controller/service/repository, nên:
1. Gửi request và nhận response.
2. Assert status/headers/contract response.
3. Tải trạng thái từ repository trong một transaction phù hợp.
4. Assert persisted business fields, association và các side effects quan trọng.
5. Chỉ ignore field thực sự không định trước; nếu field có tiêu chuẩn (ID non-null, timestamp nằm trong khoảng), kiểm riêng.

Một recursive comparison của response DTO **không chứng minh** transaction commit, unique constraint, event đã phát hoặc database ghi dữ liệu. Ngược lại, việc loaded entity giống expected không chứng minh controller trả HTTP đúng. Mỗi assertion phải gắn với một ranh giới có thể quan sát.

## 8. Cấu hình nâng cao và những giới hạn cần hiểu

### 8.1. Chỉ so một số field bằng `comparingOnlyFields`

Khi có một object lớn nhưng bạn chỉ muốn một cấu trúc con, thay vì ignore mười trường không liên quan:

```java
assertThat(actual)
        .usingRecursiveComparison()
        .comparingOnlyFields("status", "buyer.address.city")
        .isEqualTo(expected);
```

Cấu hình này giới hạn tập field cần kiểm; chỉ dùng khi **đó chính xác là contract**, vì các field ngoài danh sách sẽ không được phát hiện nếu sai. Chọn `extracting` nếu chỉ có hai scalar và việc truy cập trực tiếp rõ ràng hơn.

### 8.2. Type checking

```java
assertThat(actual)
        .usingRecursiveComparison()
        .withStrictTypeChecking()
        .isEqualTo(expected);
```

Khi cấu trúc expected và actual khác kiểu, chế độ strict có thể từ chối các kiểu không tương thích; nó không yêu cầu mọi field phải “cùng instance”. Nếu cố so JPA Entity với DTO, hãy quyết định rõ cần chứng minh **cùng dữ liệu business** hay **cùng type**. Kiểm DTO projection thường dễ ổn định hơn ép toàn bộ entity graph so strict.

### 8.3. Field comparator và type comparator

Các API thường gặp:
- `withComparatorForFields(comparator, "total")`: chỉ một/vài đường dẫn field cụ thể.
- `withComparatorForType(comparator, SomeType.class)`: áp dụng cho mọi field có kiểu phù hợp theo quy tắc AssertJ.
- `withEqualsForFields(predicate, "field")` và `withEqualsForType(predicate, Type.class)`: tự định nghĩa phép so bằng nhau không nhất thiết tạo comparator thứ tự.

Ví dụ số lượng tiền cần làm tròn đến 2 chữ số thập phân khác với sai số cho nhiệt độ. Comparator phải phản ánh logic domain, không cấu hình dung sai tùy tiện để tránh lỗi.

### 8.4. So sánh collections có phần tử là object mà không có `equals`

Nếu assertion ở mức danh sách chỉ dùng `contains(expectedObject)`, phép so phần tử thông thường có thể dựa vào `equals`. Với POJO không override `equals`, kết quả có thể FAIL dù field giống nhau. Có thể:

```java
assertThat(actualList)
        .usingRecursiveFieldByFieldElementComparator()
        .contains(expectedElement);
```

Đây là **minh họa**: `actualList` và `expectedElement` do test cung cấp. Phép `usingRecursiveFieldByFieldElementComparator()` cấu hình cách so mỗi **phần tử** trong assertion iterable; nó **khác** `assertThat(actualObject).usingRecursiveComparison().isEqualTo(expectedObject)` trên cả graph. Khi cần thông báo chi tiết đường dẫn sai của toàn object, phép recursive comparison ở cấp object thường tốt hơn.

### 8.5. Performance và tính quyết định

- Graph lớn, nhiều quan hệ vòng, collection bỏ thứ tự, custom comparator phức tạp có thể làm test chậm.
- Date/clock, random UUID, auto-generated ID, lazy query và concurrent modifications làm snapshot khó lặp lại.
- Dùng fixed clock, dữ liệu test riêng, SQL có thứ tự rõ, fixture không đổi, và projection ổn định.
- Không dựa vào thứ tự duyệt `HashMap`/`HashSet`; nếu contract không có thứ tự, dùng assertion tương ứng.
- Nếu object lớn chứa dữ liệu nhạy cảm, thông báo diff có thể in cả graph: chọn assertion nhỏ hơn hoặc representation không lộ secret.
- Không nhầm “deep comparison” với clone/copy. Recursive assertion chỉ **đọc và so giá trị** (trừ side effect getter/lazy loading), không tạo bản sao của đối tượng.

## 9. Tình huống lựa chọn assertion theo yêu cầu

| Yêu cầu bài test | Lựa chọn nên bắt đầu | Giải thích |
| --- | --- | --- |
| Kết quả trả status `PAID` | `assertThat(actual.status()).isEqualTo("PAID")` | Một giá trị, rõ contract |
| API trả danh sách có thứ tự bởi `createdAt` | `extracting(...).containsExactly(...)` | Thứ tự là ràng buộc |
| API trả tập ID không bảo đảm thứ tự | `extracting(...).containsExactlyInAnyOrder(...)` | Tránh phụ thuộc thứ tự không công bố |
| DTO lồng buyer/address/lines cần khớp hầu hết trường | `usingRecursiveComparison().isEqualTo(expected)` | Kiểm toàn cấu trúc và diff |
| DTO có ID/timestamp server sinh | Recursive `ignoringFields(...)` + assert ID/time riêng | Không để bỏ qua field che mất contract |
| Entity/DTO khác lớp nhưng chung dữ liệu business | Projection hoặc recursive với type policy rõ | Không ép entity equals theo DTO |
| `BigDecimal("1.0")` vs `BigDecimal("1.00")` cần bằng theo số | `isEqualByComparingTo` hoặc comparator trường | `equals` phân biệt scale |
| Thứ tự `lines` vô nghĩa nhưng `timeline` có nghĩa | `ignoringCollectionOrderInFields("lines")` | Giữ kiểm thứ tự nơi cần |
| Expected là object chỉ khai báo một vài field | `extracting` hoặc `ignoringExpectedNullFields()` | Hạn chế “null = bất kỳ giá trị nào” |
| Một test cần báo mọi lỗi ở nhiều thuộc tính | `SoftAssertions` + `assertAll()` | Thu thập lỗi, không quên bước chốt |
| JPA entity có lazy relationships | Assert scalar/projection, mapping cần thiết | Tránh truy cập graph ngoài transaction |
| REST JSON có 3 field quan trọng | MockMvc `jsonPath` assertion | Contract HTTP rõ ràng |
| Kết quả integration có nhiều side effects | Assertions cho HTTP + persisted state + event | Recursive DTO không thay thế side effect |

## 10. Sai lầm thường gặp và cách sửa

### 10.1. Dùng `isEqualTo` trên POJO không override `equals`

**Triệu chứng:** hai object in ra field giống nhau nhưng assertion FAIL. **Nguyên nhân:** `Object.equals` dựa trên identity. **Khắc phục:** xác định nên là value object (thiết kế `equals`), hay test chỉ cần recursive/projection. Không sửa model một cách cơ học để chiều theo test.

### 10.2. Dùng recursive nhưng bỏ qua quá nhiều field

**Triệu chứng:** test vẫn PASS dù response thiếu amount, currency hoặc status. **Nguyên nhân:** `ignoringFieldsMatchingRegexes` quá rộng hoặc `ignoringExpectedNullFields` che nhiều trường. **Khắc phục:** chỉ ignore ID/audit fields có lý do, kiểm riêng bất biến còn lại; khi chỉ một projection quan trọng, assert trực tiếp.

### 10.3. Nhầm actual và expected khi bỏ qua null

**Triệu chứng:** đảo hai tham số/đối tượng mà test có hành vi khác. **Nguyên nhân:** `ignoringActualNullFields` và `ignoringExpectedNullFields` không đối xứng. **Khắc phục:** giữ quy ước `assertThat(actual) ... isEqualTo(expected)`; đặt tên `actual`/`expected`, test thêm tình huống null không hợp lệ.

### 10.4. Coi thứ tự trả về của repository là cố định

**Triệu chứng:** CI thất bại ngẫu nhiên khi chạy database khác. **Nguyên nhân:** SQL không có `ORDER BY`. **Khắc phục:** nếu contract yêu cầu order, thêm sort vào query và `containsExactly`; nếu không, dùng `containsExactlyInAnyOrder` hoặc ignore collection order **chỉ trong field cần thiết**.

### 10.5. So tiền bằng `equals` mà không để ý scale

**Triệu chứng:** `10.0` và `10.00` bị coi khác. **Khắc phục:** dùng `isEqualByComparingTo` hoặc comparator; nếu scale là contract hiển thị/lưu, giữ so chính xác scale thay vì bỏ qua.

### 10.6. So object graph có JPA proxy/lazy fields

**Triệu chứng:** slow tests, SQL ngoài dự đoán, `LazyInitializationException`. **Khắc phục:** xác định contract cần kiểm, load đúng association, map DTO hoặc dùng assertions cho từng trường persistence cụ thể.

### 10.7. Nhầm `extracting`, `flatExtracting` và recursive comparison

**Triệu chứng:** flatten list làm mất quan hệ giữa order và line; chỉ kiểm SKU mà bỏ sót quantity/tổng tiền. **Khắc phục:** đặt câu hỏi cần kiểm *danh sách giá trị*, *cặp thuộc tính từng phần tử*, hay *cả cây đối tượng*. Chọn projection/tuple khi contract hẹp; chọn recursive khi quan hệ và nhiều trường là contract.

### 10.8. Assertion quá bám vào implementation

**Triệu chứng:** refactor giữ behavior nhưng test hỏng vì field private đổi tên hoặc cấu trúc entity nội bộ thay đổi. **Khắc phục:** ưu tiên API output, public accessor, domain invariant. Recursive comparison trên DTO ổn định hơn trên internal Spring component/entity proxy.

### 10.9. Test PASS nhưng dữ liệu thực tế chưa lưu

**Triệu chứng:** service trả DTO đúng nhưng repository save không xảy ra hoặc transaction rollback. **Nguyên nhân:** chỉ assert return object. **Khắc phục:** thêm integration test kiểm trạng thái DB/event thật theo ranh giới; unit assertion không có trách nhiệm chứng minh hạ tầng.

### 10.10. Quên `assertAll()` của SoftAssertions

**Triệu chứng:** soft assertions không làm test FAIL như mong đợi. **Khắc phục:** dùng `softly.assertAll()` hoặc API phù hợp như `SoftAssertions.assertSoftly(...)` để luôn chốt các phép kiểm.

## 11. Cách đọc lỗi assertion và cải thiện test

Khi recursive comparison FAIL:
1. Xác định **đường dẫn sai**: ví dụ `buyer.address.city`, `lines[1].sku`, `total`.
2. Xem **giá trị actual/expected** và kiểu; với số/tiền kiểm precision/scale.
3. Xem **cấu hình assertion**: có ignore field, ignore order, null policy, type comparator hay strict mode?
4. Kiểm tra **dữ liệu đầu vào** và output theo ranh giới: service bị sai rule, mapping web, SQL hay fixture sai?
5. Sửa code hoặc expected **theo contract**. Chỉ thêm ignore/comparator nếu business thật sự không quan tâm đến khác biệt đó.

Nên viết test theo mô hình Given / When / Then:
- **Given:** expected được dựng từ requirement, không copy trực tiếp actual bằng serializer.
- **When:** gọi đối tượng under test một lần tại boundary có ý nghĩa.
- **Then:** assertion hẹp cho rule quan trọng, recursive khi cần toàn cấu trúc, check riêng các field có policy đặc biệt.

Tránh lấy `actual` rồi tự clone thành `expected` với hầu hết field cùng giá trị: khi implementation sai, expected có thể sao chép luôn lỗi. Xây expected từ các giá trị độc lập và có tên rõ ràng.

## 12. Bài tập tự kiểm tra

1. Một API trả hai đơn hàng, thứ tự không được cam kết. Hãy kiểm cả ID và status từng đơn bằng `extracting("id", "status")` và `containsExactlyInAnyOrder(tuple(...), tuple(...))`. Tại sao `containsExactly` không phù hợp?
2. `OrderView` có `createdAt`, `traceId` thay đổi mỗi request. Viết recursive assertion bỏ qua đúng hai trường, sau đó thêm assertion kiểm `createdAt` non-null hoặc trong khoảng chấp nhận được. Nếu bỏ qua cả `total` thì test đã đánh mất contract nào?
3. List `lines` bị đảo thứ tự. Chạy trước với recursive mặc định, sau với `ignoringCollectionOrderInFields("lines")`. Hãy giải thích lúc nào cả hai test đều hợp lệ cho hai hợp đồng khác nhau.
4. Với `BigDecimal("42.0")` và `BigDecimal("42.00")`, kiểm `equals`, `compareTo` và `isEqualByComparingTo`. Nếu hệ thống yêu cầu đúng 2 chữ số thập phân, có còn nên bỏ qua scale không?
5. Viết test minh họa `ignoringExpectedNullFields()` với expected chỉ có status, rồi cố ý để actual.status sai. Test phải FAIL; tại sao không được đặt status null ở expected?
6. Chuyển một assertion recursive toàn entity graph sang projection từ repository chỉ gồm `id`, `status`, `buyerName`, `total`. So sánh độ rõ và độ ổn định với proxy/lazy loading.

Tiêu chí đạt: có thể giải thích **đang so object nào, field nào, với semantics nào**, và chỉ ra được field đã ignore còn cần test bổ sung hay không.

## 13. Checklist áp dụng trong dự án

- [ ] `actual` là kết quả thực của unit/service/web/repository; `expected` được dựng độc lập từ requirement?
- [ ] Chỉ cần một vài thuộc tính thì đã cân nhắc direct accessor/`extracting` chưa?
- [ ] Nếu cần so toàn cây, `usingRecursiveComparison` có đúng với semantics của DTO/domain không?
- [ ] Có ID/time/trace tự sinh không? Các field này bị ignore ở phạm vi nhỏ nhất và được assert riêng khi cần?
- [ ] Collection có contract thứ tự không? `containsExactly` hay `containsExactlyInAnyOrder` được chọn có chủ đích?
- [ ] Các kiểu `BigDecimal`, date/time, floating-point, currency cần comparator riêng không?
- [ ] Có dùng `ignoringActualNullFields` hoặc `ignoringExpectedNullFields` gây bỏ sót giá trị bắt buộc không?
- [ ] So sánh khác kiểu actual/expected có chủ ý? Có cần `withStrictTypeChecking`?
- [ ] Có JPA proxy/lazy relationship hoặc chu trình làm recursive comparison quá rộng không?
- [ ] Test FAILURE có mô tả rõ phần sai (`as(...)`/field path) và không in secrets?
- [ ] Nếu dùng SoftAssertions, đã gọi `assertAll()`?
- [ ] Assertion đã kiểm behavior tại đúng boundary; không suy diễn DB/HTTP/transaction chỉ từ DTO equality?

**Kết luận thực hành:** kiểm **thuộc tính** khi contract có vài giá trị rõ; kiểm **projection/tuple** khi collection cần các cột ổn định; dùng **recursive comparison** khi phần lớn cấu trúc lồng nhau là contract. Mọi lựa chọn ignore, null, thứ tự, comparator hay type đều phải có lý do nghiệp vụ và được cân nhắc theo khả năng phát hiện lỗi.

## 14. Tài liệu chính thức

- AssertJ Core — tài liệu và phần Extracting / Field by Field Recursive Comparison: https://assertj.github.io/doc/
- AssertJ 3.27.6 — API `RecursiveComparisonAssert`: https://javadoc.io/doc/org.assertj/assertj-core/3.27.6/org/assertj/core/api/RecursiveComparisonAssert.html
- AssertJ 3.27.6 — API `AbstractObjectAssert`: https://javadoc.io/doc/org.assertj/assertj-core/3.27.6/org/assertj/core/api/AbstractObjectAssert.html
- Spring Boot 3.5 — Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
- JUnit 5 — User Guide: https://docs.junit.org/5.11.4/user-guide/
- Java 17 — Record classes: https://docs.oracle.com/en/java/javase/17/language/records.html
