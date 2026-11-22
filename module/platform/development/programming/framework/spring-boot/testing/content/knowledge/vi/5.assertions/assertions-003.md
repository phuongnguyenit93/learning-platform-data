# AssertJ: fluent assertions và thông điệp lỗi dễ đọc

## 1. AssertJ dùng để làm gì?

**AssertJ** là thư viện assertion cho Java, cung cấp API dạng **fluent**: bắt đầu bằng `assertThat(actual)` rồi nối các phép kiểm tra có ý nghĩa, chẳng hạn `isEqualTo(...)`, `containsExactly(...)`, `hasSize(...)`, `isPresent()`, `hasMessageContaining(...)`. Trong ứng dụng Spring Boot, AssertJ thường có sẵn trong dependency kiểm thử `spring-boot-starter-test`.

Mục tiêu của assertion là biến kết quả quan sát được thành một **hợp đồng kiểm chứng rõ ràng**: điều gì phải đúng, với dữ liệu nào, và nếu sai thì thông tin thất bại có đủ để tìm nguyên nhân không. AssertJ nổi bật ở ba điểm:

1. **Dễ đọc theo kiểu câu:** `assertThat(receipt.totalQuantity()).isEqualTo(5)` gần với phát biểu “tổng số lượng phải bằng 5”.
2. **Assertion đặc thù cho kiểu dữ liệu:** String, number, collection, map, optional, exception, file, date/time… có các phương thức thích hợp thay vì chỉ so sánh boolean chung chung.
3. **Chẩn đoán thất bại hữu ích:** thông báo mặc định thường hiển thị expected/actual và sự khác biệt; ta có thể thêm bối cảnh bằng `as(...)`, hoặc gom nhiều vi phạm bằng soft assertions.

**AssertJ không phải test runner.** JUnit Jupiter vẫn chịu trách nhiệm phát hiện và chạy phương thức `@Test`, quản lý lifecycle và công bố kết quả; AssertJ cung cấp các phép khẳng định bên trong test. Chúng phối hợp được với nhau, không cạnh tranh nhau.

### 1.1. Nhìn nhanh cấu trúc một fluent assertion

```java
assertThat(actual)
    .as("mô tả bối cảnh nghiệp vụ")
    .isNotNull()
    .isEqualTo(expected);
```

Đây là **đoạn minh họa cú pháp**, không phải chương trình Java độc lập. Ý nghĩa:

- `assertThat(actual)` khởi tạo đối tượng assertion phù hợp kiểu của `actual`.
- `as(...)` đặt mô tả xuất hiện trong thông báo khi assertion thất bại; nên đứng **trước** các phép kiểm tra.
- `isNotNull()` kiểm tra tiền đề quan trọng nếu bạn muốn thông báo null rõ ràng.
- `isEqualTo(expected)` kiểm tra bằng nhau; nếu thất bại, AssertJ ném `AssertionError` và test bị đánh dấu failed.

Những lời gọi liên tiếp thường trả về đối tượng assertion để nối tiếp. Nhưng **đừng nối cho dài chỉ vì có thể**: mỗi bước cần thể hiện một điều kiện có giá trị, và khi thất bại phải dễ biết bước nào sai.

## 2. Chuẩn bị AssertJ trong dự án Spring Boot

Trong dự án Spring Boot hiện đại, dependency test chuẩn thường đã bao gồm JUnit Jupiter, AssertJ và các công cụ kiểm thử liên quan. Dùng phiên bản do Spring Boot dependency management quản lý để các thư viện tương thích.

**Gradle (Groovy DSL, phần liên quan trong `build.gradle`):**

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven (phần dependency trong `pom.xml`):**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Các ví dụ trên giả định dự án đã có Spring Boot plugin/parent hoặc cách quản lý dependency phù hợp, cùng repository cần thiết. Không chèn lại `spring-boot-starter-test` nếu dự án đã khai báo; cũng không tự gắn một phiên bản AssertJ riêng nếu chưa có nhu cầu xác định và kiểm tra tương thích.

Trong lớp test, thông thường import:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertSoftly;
```

Cần phân biệt `org.assertj.core.api.Assertions` với `org.junit.jupiter.api.Assertions`. JUnit có các phương thức như `assertEquals(expected, actual)`; AssertJ dùng `assertThat(actual).isEqualTo(expected)`, tức **thứ tự đối số và phong cách khác nhau**. Không trộn thứ tự expected/actual khi chuyển code từ JUnit.

Để xác minh dependency bằng build tool, bạn có thể chạy Gradle test task hoặc Maven test goal. Nếu IDE báo `Cannot resolve symbol assertThat`, hãy kiểm tra test dependency, import và đồng bộ build thay vì chỉ thêm JAR bằng tay vào IDE.

## 3. So sánh JUnit assertions và AssertJ theo ý định

Giả sử có biến `actualName` là String do code đang kiểm thử trả về.

| Ý định | JUnit Jupiter | AssertJ |
|---|---|---|
| Bằng nhau | `assertEquals("Alice", actualName)` | `assertThat(actualName).isEqualTo("Alice")` |
| Không null | `assertNotNull(actualName)` | `assertThat(actualName).isNotNull()` |
| Chứa chuỗi | `assertTrue(actualName.contains("lic"))` | `assertThat(actualName).contains("lic")` |
| Danh sách đúng thứ tự | `assertIterableEquals(expected, actual)` | `assertThat(actual).containsExactly("A", "B")` |
| Ngoại lệ | `assertThrows(IllegalArgumentException.class, action)` | `assertThatThrownBy(action).isInstanceOf(IllegalArgumentException.class)` |

Một số so sánh chỉ tương đương khi **đúng kiểu dữ liệu và bộ giá trị**. Ví dụ `assertIterableEquals` và `containsExactly` đều kiểm tra thứ tự, nhưng thông báo/overload khác nhau. Chọn assertion theo hợp đồng thực sự cần chứng minh, không vì số dòng ngắn nhất.

**Phản mẫu:**

```java
assertThat(users.size() > 0).isTrue();
```

Nếu thất bại, bạn chủ yếu thấy một boolean false. Trong test thích hợp hơn:

```java
assertThat(users)
    .as("danh sách người dùng trả về từ dịch vụ")
    .isNotEmpty();
```

Ở đây AssertJ biết đối tượng là collection, cho thông báo liên quan trực tiếp đến collection và điều kiện cần kiểm tra.

## 4. Ví dụ chạy được: service nhỏ và bộ test JUnit Jupiter dùng AssertJ

Ví dụ sử dụng **Java 17+**, không cần khởi động Spring context. Service tạo phiếu gồm mã, danh sách dòng hàng và tổng số lượng. Bài học tập trung vào câu assertion; không dùng mock, database hay mạng để che lấp kỹ thuật đang học.

### 4.1. Mã nguồn sản phẩm

Tạo **`src/main/java/com/example/testing/assertj/ReceiptService.java`**:

```java
package com.example.testing.assertj;

import java.util.List;
import java.util.Objects;

public final class ReceiptService {

    public record Item(String sku, int quantity) {}

    public record Receipt(
            String id,
            List<Item> items,
            int totalQuantity
    ) {}

    public Receipt create(String rawId, List<Item> items) {
        if (rawId == null || rawId.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("items must not be empty");
        }

        int total = 0;
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.sku() == null || item.sku().isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (item.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            total = Math.addExact(total, item.quantity());
        }

        return new Receipt(rawId.trim(), List.copyOf(items), total);
    }
}
```

Ý nghĩa của service:

- Mã phiếu không được null/rỗng và được trim.
- Danh sách dòng hàng không được null/rỗng; SKU không được rỗng, số lượng phải dương.
- `Math.addExact` ném `ArithmeticException` nếu cộng vượt giới hạn `int`.
- `List.copyOf` lưu một bản sao bất biến về cấu trúc của danh sách dòng hàng.
- Java `record` cung cấp `equals/hashCode` theo thành phần: phù hợp minh họa sự khác biệt giữa so sánh giá trị và tham chiếu.

### 4.2. Bộ test có các assertion dễ đọc

Tạo **`src/test/java/com/example/testing/assertj/ReceiptServiceTest.java`**:

```java
package com.example.testing.assertj;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;

import com.example.testing.assertj.ReceiptService.Item;
import com.example.testing.assertj.ReceiptService.Receipt;

import static org.assertj.core.api.Assertions.assertSoftly;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

class ReceiptServiceTest {
    private final ReceiptService service = new ReceiptService();

    private Receipt sample() {
        return service.create(" R-01 ", List.of(
                new Item("BOOK", 2),
                new Item("PEN", 3)
        ));
    }

    @Test
    void createsReceiptWithFluentAssertions() {
        Receipt receipt = sample();

        assertThat(receipt.id())
                .as("mã phiếu sau khi chuẩn hóa")
                .isEqualTo("R-01");

        assertThat(receipt.totalQuantity())
                .as("tổng số lượng của phiếu %s", receipt.id())
                .isEqualTo(5)
                .isPositive();
    }

    @Test
    void preservesLineOrderWhenRequired() {
        Receipt receipt = sample();

        assertThat(receipt.items())
                .as("các dòng hàng của phiếu %s", receipt.id())
                .hasSize(2)
                .extracting(Item::sku)
                .containsExactly("BOOK", "PEN");
    }

    @Test
    void comparesWithoutOrderWhenOrderIsNotPartOfContract() {
        assertThat(sample().items())
                .extracting(Item::quantity)
                .containsExactlyInAnyOrder(3, 2);
    }

    @Test
    void recordsProvideValueEquality() {
        Receipt expected = new Receipt(
                "R-01",
                List.of(new Item("BOOK", 2), new Item("PEN", 3)),
                5
        );

        assertThat(sample()).isEqualTo(expected);
    }

    @Test
    void checksExceptionTypeAndMessage() {
        assertThatThrownBy(() -> service.create(
                "   ",
                List.of(new Item("BOOK", 1))
        ))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("id must not be blank");
    }

    @Test
    void checksCodeThatShouldNotThrow() {
        assertThatCode(() -> service.create(
                "R-02",
                List.of(new Item("PEN", 1))
        )).doesNotThrowAnyException();
    }

    @Test
    void collectsRelatedChecksWithSoftAssertions() {
        Receipt receipt = sample();

        assertSoftly(softly -> {
            softly.assertThat(receipt.id())
                    .as("mã phiếu")
                    .isEqualTo("R-01");
            softly.assertThat(receipt.totalQuantity())
                    .as("tổng số lượng")
                    .isEqualTo(5);
            softly.assertThat(receipt.items())
                    .as("số dòng hàng")
                    .hasSize(2);
        });
    }

    @Test
    void supportsOptionalDecimalAndTolerance() {
        assertThat(Optional.of("READY")).contains("READY");

        assertThat(new BigDecimal("10.00"))
                .isEqualByComparingTo(new BigDecimal("10.0"));

        assertThat(0.1 + 0.2)
                .isCloseTo(0.3, within(1e-10));
    }
}
```

**Cách chạy** từ thư mục dự án (chọn build tool mà dự án đang dùng):

```bash
# Gradle Wrapper: chạy riêng lớp test
./gradlew test --tests "com.example.testing.assertj.ReceiptServiceTest"

# Maven Wrapper: cùng lớp test với Surefire
./mvnw -Dtest=ReceiptServiceTest test
```

Trên Windows PowerShell, dùng `.\gradlew.bat test --tests "com.example.testing.assertj.ReceiptServiceTest"` hoặc `.\mvnw.cmd "-Dtest=ReceiptServiceTest" test`. Tên class và package phải giống hệt file đã tạo; `ReceiptServiceTest` cần có JUnit Jupiter trên test runtime classpath.

**Kỳ vọng:** lớp có **8 phương thức `@Test`**, cả 8 thành công nếu đặt trong dự án Java 17+ với dependency/cấu hình tương ứng. Test không chủ động ghi stdout. Console hiển thị số lượng và báo cáo theo Gradle/Maven/JUnit version, nên không khẳng định một dòng log cố định. Nếu muốn đối chiếu báo cáo, Gradle thường tạo `build/reports/tests/test/index.html`, Maven Surefire thường tạo `target/surefire-reports/`.

### 4.3. Đọc ý nghĩa của từng test

- `createsReceiptWithFluentAssertions` dùng `as(...)` để nói **thuộc tính nào** đang được kiểm tra; nếu sai, bạn thấy bối cảnh phiếu và expected/actual.
- `preservesLineOrderWhenRequired` dùng `extracting(Item::sku)` để kiểm tra đúng thứ tự SKU, thay vì assert cả object rồi khó biết trường nào sai.
- `comparesWithoutOrderWhenOrderIsNotPartOfContract` dùng `containsExactlyInAnyOrder`, vì mục tiêu chỉ là các giá trị và số lần xuất hiện; không áp đặt thứ tự giả tạo.
- `recordsProvideValueEquality` dùng equality của record; nếu thay `Receipt` bằng class không override `equals`, kết quả `isEqualTo` có thể khác.
- `checksExceptionTypeAndMessage` mô tả hợp đồng khi đầu vào sai: không chỉ “có ném lỗi” mà còn đúng loại và thông điệp cần công bố.
- `checksCodeThatShouldNotThrow` thích hợp để chứng minh hành vi không ném exception; nếu cần kiểm tra **giá trị trả về**, tốt hơn hãy lấy giá trị rồi assert trên kết quả như các test trước.
- `collectsRelatedChecksWithSoftAssertions` báo nhiều vi phạm trong một lượt khi các phép kiểm tra độc lập với nhau.
- `supportsOptionalDecimalAndTolerance` thể hiện các assertion riêng cho kiểu dữ liệu và cách tránh lỗi so sánh số thực.

## 5. Viết fluent assertion đúng với hợp đồng nghiệp vụ

### 5.1. Chọn assertion đặc thù cho kiểu dữ liệu

Đừng biến mọi kết quả thành boolean để assert. Lấy ví dụ trên các biến đã được khai báo trong một test:

```java
assertThat(name).startsWith("A").endsWith("Z");
assertThat(amount).isPositive().isLessThan(100);
assertThat(items).isNotEmpty().hasSize(3);
assertThat(statusById).containsEntry("R-01", "PAID");
assertThat(maybeId).contains("R-01");
```

Đây là **các đoạn minh họa**, không phải chương trình độc lập; giả định `name` là String, `amount` là số, `items` là collection, `statusById` là map và `maybeId` là `Optional<String>`.

Các phương thức nói rõ “cần đúng điều gì”. Ví dụ `containsEntry` nói rằng một key phải map đến value cụ thể; `isPositive` thể hiện ngữ nghĩa lớn hơn 0; `contains("R-01")` trên `Optional` đòi hỏi optional có giá trị đúng bằng chuỗi đó.

Tránh chuỗi assertion lặp thừa, chẳng hạn `isNotEmpty().hasSize(3)`: `hasSize(3)` đã kéo theo không rỗng. Chỉ giữ thêm `isNotEmpty` nếu nó có ý nghĩa tài liệu hoặc thông báo riêng trong test cụ thể.

### 5.2. Phân biệt equality, identity và deep comparison

- `isEqualTo(expected)` thông thường dựa trên so sánh bằng nhau theo semantics của kiểu, nhiều object dựa vào `equals`. Record tự sinh `equals` theo component.
- `isSameAs(expected)` kiểm tra **cùng đối tượng tham chiếu**; hữu ích khi identity chính là hợp đồng, chẳng hạn một singleton phải được trả về nguyên vẹn.
- `usingRecursiveComparison().isEqualTo(expected)` so sánh sâu các trường/đối tượng lồng nhau, hữu ích cho DTO không có `equals` phù hợp. Hãy hiểu và cấu hình đúng cách xử lý collection, ignored fields và comparator nếu cần.

**Đoạn minh họa** trong ngữ cảnh đã có `actualReceipt` và `expectedReceipt`:

```java
assertThat(actualReceipt)
        .usingRecursiveComparison()
        .isEqualTo(expectedReceipt);
```

Không xem recursive comparison là giải pháp mặc định. Nếu chỉ muốn kiểm tra `status` và `totalQuantity`, assert riêng hai trường sẽ nói rõ hợp đồng và ít bị tác động bởi những trường mới không liên quan. Ngược lại, nếu mục tiêu là xác minh toàn bộ DTO, deep comparison có thể phát hiện thiếu sót mà các assert rời rạc bỏ qua. Không bỏ qua `id`, `timestamp` hay field quan trọng chỉ để làm test xanh.

### 5.3. Kỳ vọng chính xác hay chấp nhận một phần?

Giả sử API trả danh sách SKU `["BOOK", "PEN", "RULER"]`. Những assertion này **khác nhau**:

| Assertion | Hợp đồng |
|---|---|
| `contains("BOOK", "PEN")` | Có những phần tử được nêu; vẫn cho phép phần tử khác |
| `containsExactly("BOOK", "PEN")` | Đúng số lượng và thứ tự hai phần tử, không có phần tử thừa |
| `containsExactlyInAnyOrder("PEN", "BOOK")` | Chính xác các phần tử và số lần xuất hiện; không yêu cầu thứ tự |
| `containsOnly("BOOK", "PEN")` | Chỉ chứa các giá trị cho phép; không dùng để kiểm chứng chính xác số lần lặp |
| `doesNotContain("RULER")` | Chỉ cấm một giá trị, không nói các phần tử còn lại có đủ không |

Hãy quyết định nghiệp vụ có yêu cầu **thứ tự**, **tập giá trị chính xác**, **số lần xuất hiện** và **không có dữ liệu thừa** hay không. Dùng `contains` trong hợp đồng yêu cầu chính xác có thể để lọt lỗi; dùng `containsExactly` khi database/API không hứa thứ tự có thể tạo flaky test.

## 6. Làm thông điệp thất bại dễ hiểu với `as(...)`

### 6.1. Bối cảnh + expected/actual là bộ ba hữu ích

Khi một test thất bại, người đọc muốn biết:

1. **Bối cảnh:** đối tượng, định danh, request hay điều kiện đang kiểm tra.
2. **Kỳ vọng:** hệ thống phải trả điều gì.
3. **Giá trị thực tế:** hệ thống đã trả điều gì và khác tại đâu.

AssertJ có thể cung cấp expected/actual và diff cho nhiều loại assertion; bạn bổ sung phần bối cảnh bằng `as("...")`:

```java
assertThat(receipt.totalQuantity())
        .as("tổng số lượng của phiếu %s", receipt.id())
        .isEqualTo(5);
```

Nếu tổng số lượng trả về 4, thông báo thất bại sẽ có mô tả tương tự “tổng số lượng của phiếu R-01” cùng expected 5 và actual 4; **cách hiển thị chính xác tùy phiên bản AssertJ, IDE và test runner**. Nên đọc phần diff của runner thay vì dựa vào chuỗi render cố định.

### 6.2. Đặt `as(...)` trước phép kiểm tra

**Đúng:**

```java
assertThat(receipt.id())
        .as("id của phiếu trả về")
        .startsWith("R-");
```

**Sai về vị trí mô tả:**

```java
assertThat(receipt.id())
        .startsWith("R-")
        .as("id của phiếu trả về");
```

Nếu `startsWith` đã thất bại, Java không thực thi đến `as` ở sau. Vì vậy mô tả không có cơ hội xuất hiện. Hãy thêm mô tả ngay sau `assertThat(actual)`, trước assertion có khả năng thất bại.

### 6.3. Khi nào dùng `withFailMessage(...)`?

AssertJ có phương thức cấu hình thông điệp lỗi tùy chỉnh, ví dụ `withFailMessage(...)`. Nó có thể **thay thế thông điệp mặc định giàu expected/actual**. Chỉ dùng khi bạn thực sự cần một dạng thông báo đặc biệt và tự cung cấp đủ thông tin.

**Lựa chọn nên ưu tiên:**

```java
assertThat(total)
        .as("tổng tiền đơn %s", orderId)
        .isEqualTo(expectedTotal);
```

**Cẩn trọng với:**

```java
assertThat(total)
        .withFailMessage("sai tổng tiền")
        .isEqualTo(expectedTotal);
```

Mẫu sau có thể đánh mất chi tiết đối chiếu mà thư viện vốn cung cấp. Nếu muốn rút ngắn, hãy viết bối cảnh cô đọng bằng `as`. Không đưa secret, token, password hoặc toàn bộ dữ liệu cá nhân nhạy cảm vào mô tả assertion/log CI.

### 6.4. Mỗi phép kiểm tra có một câu chuyện rõ ràng

Nếu một assertion chain kiểm tra mã, trạng thái, số lượng, tên người mua và ngày hết hạn cùng lúc, lỗi có thể khó nhận ra ý định của từng phần. Tách thành các assertion ngắn, mỗi cái có mô tả phù hợp, thường dễ bảo trì hơn:

```java
assertThat(receipt.id())
        .as("mã phiếu")
        .isEqualTo("R-01");

assertThat(receipt.totalQuantity())
        .as("tổng số lượng")
        .isEqualTo(5);
```

Không sao chép một thông điệp chung “result should be correct” cho mọi phép thử. Thông điệp nên bổ sung bối cảnh mà expression không thể hiện rõ, ví dụ mã đơn, vai trò người dùng, trạng thái nghiệp vụ, hoặc tham số đã kích hoạt nhánh lỗi.

## 7. Assertions với collection: đọc đúng thứ tự và thuộc tính

Collections là một trong những nơi AssertJ giúp nhiều nhất: bạn có thể assert cấu trúc thay vì thủ công duyệt và so boolean.

### 7.1. Kiểm tra toàn bộ, thứ tự và phần tử con

Giả sử `receipt` thuộc loại `ReceiptService.Receipt` của ví dụ:

```java
assertThat(receipt.items())
        .as("danh sách SKU của phiếu %s", receipt.id())
        .extracting(ReceiptService.Item::sku)
        .containsExactly("BOOK", "PEN");
```

`extracting(...)` chuyển list object thành list giá trị trường cần kiểm tra. Nhờ đó khi thất bại, bạn biết **SKU** nào thừa/thiếu/sai thứ tự, thay vì phải đọc cả object dump.

Nếu thứ tự không là hợp đồng:

```java
assertThat(receipt.items())
        .extracting(ReceiptService.Item::sku)
        .containsExactlyInAnyOrder("PEN", "BOOK");
```

Nếu chỉ cần bảo đảm “ít nhất một dòng SKU BOOK”:

```java
assertThat(receipt.items())
        .extracting(ReceiptService.Item::sku)
        .contains("BOOK");
```

Đó là ba hợp đồng khác nhau. Đừng vô thức chọn hàm vì cách viết quen thuộc.

### 7.2. Lọc và kiểm tra theo đặc tính

AssertJ hỗ trợ lọc iterable theo predicate và kiểm tra các phần tử sau lọc. **Đoạn minh họa** từ ví dụ:

```java
assertThat(receipt.items())
        .filteredOn(item -> item.quantity() >= 3)
        .extracting(ReceiptService.Item::sku)
        .containsExactly("PEN");

assertThat(receipt.items())
        .allSatisfy(item ->
                assertThat(item.quantity()).isPositive());
```

- `filteredOn` xác nhận tập kết quả sau quy tắc lọc; hãy dùng nếu logic lọc chính là điều bạn muốn chứng minh.
- `allSatisfy` áp một tập kiểm tra lên **mọi** phần tử. Với điều kiện “phải có ít nhất một phần tử”, cần kiểm tra tính không rỗng trước: một predicate đúng với mọi phần tử của **collection rỗng** không chứng minh collection có phần tử.
- Khi biết cụ thể phần tử nào cần kiểm tra, assertion trực tiếp trên list và từng trường có thể đơn giản hơn chuỗi filter dài.

### 7.3. Tránh assertion phụ thuộc index khi nghiệp vụ không yêu cầu index

Nếu repository query không có `ORDER BY`, không được dựa vào thứ tự kết quả tình cờ của DB. Test nên so sánh tập các thuộc tính:

```java
assertThat(actualIds)
        .containsExactlyInAnyOrder("R-01", "R-02");
```

Đoạn này giả định `actualIds` là list/String collection. Nếu nghiệp vụ yêu cầu sắp xếp theo ngày tạo hoặc độ ưu tiên, thì phải kiểm tra thứ tự cụ thể và bảo đảm production query/service thật sự có quy tắc sắp xếp.

## 8. AssertJ cho exception: loại lỗi, thông điệp và code không ném lỗi

Kiểm thử ngoại lệ không chỉ là “code này đỏ”. Nó cần chứng minh hệ thống **từ chối đầu vào sai theo hợp đồng**.

### 8.1. Loại exception và thông điệp

```java
assertThatThrownBy(() -> service.create(
        "",
        List.of(new ReceiptService.Item("BOOK", 1))
))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("id must not be blank");
```

- Nếu code **không ném exception**, assertion này thất bại.
- Nếu ném loại khác, `isInstanceOf` thất bại.
- Nếu đúng loại nhưng thông điệp khác, `hasMessage` thất bại.
- Khi thông điệp có phần động hợp lệ, dùng `hasMessageContaining("...")` hay biểu thức kiểm tra phù hợp thay vì khớp toàn chuỗi cố định.

Không dùng `try/catch` rồi bỏ trống `catch` hoặc nuốt mọi exception: cách đó có thể làm test xanh dù hành vi sai. Với nhiều lớp exception, nên assert đúng loại đang là public contract; không cố khóa vào implementation detail mà code có quyền thay đổi.

### 8.2. Kiểm tra đường không ném lỗi

```java
assertThatCode(() -> service.create(
        "R-02",
        List.of(new ReceiptService.Item("PEN", 1))
))
        .doesNotThrowAnyException();
```

Assertion này chỉ chứng minh code không ném exception. Nếu kết quả service trả sai dữ liệu nhưng không ném lỗi, test vẫn xanh. Khi method trả giá trị quan trọng, kiểm tra thêm đầu ra:

```java
ReceiptService.Receipt result = service.create(
        "R-02",
        List.of(new ReceiptService.Item("PEN", 1))
);

assertThat(result.id()).isEqualTo("R-02");
assertThat(result.totalQuantity()).isEqualTo(1);
```

Hai đoạn trên là ví dụ cùng chủ đề, **không cần đưa cả hai vào một test** nếu không có giá trị bổ sung; chọn cách nào phù hợp với hợp đồng đang muốn bảo đảm.

## 9. Soft assertions: xem nhiều lỗi liên quan trong một lượt

Các assertion thông thường là **hard assertions**: gặp assertion đầu tiên thất bại, method test dừng ở đó. Khi cần kiểm tra nhiều trường độc lập của một DTO hoặc một phản hồi lớn, chỉ thấy lỗi trường đầu sẽ làm phải sửa/chạy lặp nhiều lần.

AssertJ cung cấp **soft assertions** để thu thập lỗi rồi báo cùng lúc:

```java
assertSoftly(softly -> {
    softly.assertThat(receipt.id())
            .as("mã phiếu")
            .isEqualTo("R-01");

    softly.assertThat(receipt.totalQuantity())
            .as("tổng số lượng")
            .isEqualTo(5);

    softly.assertThat(receipt.items())
            .as("số dòng hàng")
            .hasSize(2);
});
```

Biến `receipt` là instance của `ReceiptService.Receipt` trong ví dụ. Với `assertSoftly(...)`, thư viện thực hiện việc kết thúc và tổng hợp lỗi khi thoát lambda, kể cả khi có nhiều assertion thất bại.

**Khi hữu ích:** kiểm tra cùng một dữ liệu sau khi Arrange và Act đã thành công; mỗi trường có thể được đánh giá độc lập, và muốn xem hết các chênh lệch trong một lượt.

**Khi không phù hợp:** assertion sau phụ thuộc tiền đề của assertion trước, ví dụ `result` có thể null rồi bạn gọi `result.id()`; lỗi `NullPointerException` sẽ ngắt luồng trước khi AssertJ tổng hợp được các trường sau. Hãy bảo đảm tiền đề bằng hard assertion hoặc thiết kế test sao cho giá trị cần kiểm tra tồn tại.

Cũng không nên dùng soft assertions để gom nhiều **hành vi độc lập** vào một method quá lớn; một test nên vẫn có mục tiêu nghiệp vụ thống nhất.

## 10. Những kiểu dữ liệu cần lưu ý riêng

### 10.1. Optional: giá trị có/không có

```java
assertThat(Optional.of("ACTIVE")).contains("ACTIVE");
assertThat(Optional.<String>empty()).isEmpty();
```

`contains("ACTIVE")` trên `Optional` kiểm tra optional có mặt và giá trị bằng chuỗi kỳ vọng. Nó khác với `contains("ACT")` trên String (kiểm tra substring). Do đó hãy dựa vào **kiểu của actual** khi đọc API.

### 10.2. BigDecimal: scale khác nhau

Trong Java, `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là false vì `equals` xét cả scale; tuy vậy `compareTo` coi chúng bằng nhau về giá trị số.

Nếu hợp đồng cần so **giá trị số**, có thể dùng:

```java
assertThat(new BigDecimal("10.00"))
        .isEqualByComparingTo(new BigDecimal("10.0"));
```

Nếu nghiệp vụ yêu cầu đúng scale/cách biểu diễn (ví dụ dữ liệu tiền tệ được chuẩn hóa hai chữ số thập phân), hãy assert riêng scale/representation theo yêu cầu. Không thay `isEqualTo` bằng `isEqualByComparingTo` mà chưa hiểu hợp đồng.

### 10.3. Double/float: độ lệch do biểu diễn nhị phân

`0.1 + 0.2` không nhất thiết bằng chính xác `0.3` theo `double`. Với phép tính số thực có sai số cho phép, dùng khoảng lệch có ý nghĩa:

```java
assertThat(0.1 + 0.2)
        .isCloseTo(0.3, within(1e-10));
```

Cần import static `org.assertj.core.api.Assertions.within`. Ngưỡng `1e-10` ở đây chỉ phù hợp với ví dụ nhỏ. Ngưỡng thực tế phải lấy từ sai số được phép của nghiệp vụ/thuật toán; không nới ngưỡng vô căn cứ để che lỗi.

Với tiền tệ cần chính xác thập phân, ưu tiên `BigDecimal` và quy tắc rounding rõ ràng thay vì `double` khi tính giá trị.

### 10.4. String: loại so sánh đúng ý định

Các kiểm tra phổ biến gồm `isEqualTo`, `isBlank`, `contains`, `startsWith`, `endsWith`, `matches`. Đừng dùng `contains` khi hợp đồng yêu cầu chính xác cả chuỗi; cũng đừng chỉ `isNotNull` khi cần xác minh thông điệp lỗi.

Lưu ý Unicode, chuẩn hóa dấu, chữ hoa/thường, locale và khoảng trắng. Khi nghiệp vụ có chuẩn hóa, hãy xác định rõ phần nào thuộc trách nhiệm production code và phần nào là kỳ vọng của test; đừng vô tình trim/lowercase **cả actual và expected trong test** để che lỗi chuẩn hóa.

### 10.5. Map: khóa và giá trị

Khi kiểm tra phản hồi tổng hợp hoặc tham số cấu hình, dùng `containsEntry(key, value)` để chỉ ra cặp kỳ vọng; `containsKeys(...)` chỉ kiểm tra khóa, chưa chứng minh giá trị đúng. Với map không có thứ tự, đừng dựa vào thứ tự iterator để so với list nếu hợp đồng không nói thứ tự.

## 11. Kết hợp AssertJ với kiểm thử Spring Boot

AssertJ không yêu cầu Spring context: nó hoạt động trong **unit test thuần Java**, slice test và integration test. Chọn phạm vi test theo điều cần chứng minh.

### 11.1. Unit test service: dùng object thật và fake/mock phụ thuộc khi cần

Nếu mục tiêu là luật nghiệp vụ nhỏ, cứ kiểm tra trực tiếp service như `ReceiptServiceTest` ở trên. Không thêm `@SpringBootTest` chỉ để gọi `assertThat`; khởi động context làm test tốn thời gian và bổ sung điểm thất bại ngoài mục tiêu.

Với service có repository, có thể dùng Mockito mock repository để cô lập logic. AssertJ vẫn kiểm tra result; Mockito dùng cho setup/verification về tương tác **khi tương tác là một phần hợp đồng**. Đừng nhầm assertion kết quả với verification số lần gọi mock: hai thứ kiểm chứng các mặt khác nhau.

### 11.2. Web MVC test: phân biệt HTTP contract và assertion đối tượng

Trong `@WebMvcTest` với MockMvc, cú pháp `andExpect(status().isOk())`, `jsonPath(...)` là cơ chế matcher của Spring MVC test, không phải AssertJ. Vẫn có thể dùng AssertJ cho những giá trị đã trích xuất:

**Đoạn minh họa, phụ thuộc controller và MockMvc setup của dự án:**

```java
MvcResult result = mockMvc.perform(get("/api/receipts/R-01"))
        .andExpect(status().isOk())
        .andReturn();

assertThat(result.getResponse().getContentType())
        .as("content type endpoint chi tiết phiếu")
        .contains("application/json");
```

Đoạn này **không độc lập để biên dịch/chạy**: cần khai báo `mockMvc`, các static imports Spring MVC, controller route và test context phù hợp. Nó minh họa ý định: dùng matcher để xác minh HTTP contract, AssertJ để viết assertion bổ sung có bối cảnh. Đừng chỉ assert response status 200 rồi bỏ qua payload quan trọng.

### 11.3. Data JPA test: kiểm chứng dữ liệu trả về

Trong repository integration test, có thể:

```java
assertThat(repository.findByStatus(Status.PAID))
        .extracting(Order::getId)
        .containsExactlyInAnyOrder("R-01", "R-02");
```

Đây là **đoạn minh họa** với repository, enum và entity giả định đã được dự án khai báo. Ý nghĩa là kiểm chứng tập ID của bản ghi có trạng thái `PAID`; không đòi thứ tự khi query không quy định thứ tự. Test phải tự chuẩn bị dữ liệu, cleanup/rollback theo transaction thực tế; AssertJ không có chức năng cô lập database.

### 11.4. Test context: phân biệt assertion fail với Spring startup fail

Nếu `@SpringBootTest` báo `Failed to load ApplicationContext`, thông thường context chưa được khởi tạo nên **assertion của test chưa có cơ hội chạy**. Điều tra bean/configuration/profile/database trước, không thêm `as(...)` hay thay assertion để “sửa” lỗi startup.

## 12. Lỗi phổ biến và cách sửa

| Phản mẫu | Vì sao có vấn đề | Cách viết/điều tra tốt hơn |
|---|---|---|
| `assertThat(list.isEmpty()).isFalse()` | Lỗi chỉ nói boolean | `assertThat(list).isNotEmpty()` |
| `assertThat(actual).contains(expected)` khi cần đúng danh sách | Phần tử thừa có thể lọt | `containsExactly` hoặc `containsExactlyInAnyOrder` |
| `as(...)` đặt sau `isEqualTo(...)` | Mô tả không xuất hiện nếu fail trước đó | Đặt `as(...)` ngay sau `assertThat(actual)` |
| Thay mọi thông báo bằng `withFailMessage("sai")` | Mất diff expected/actual | Ưu tiên `as(...)` và assertion đặc thù |
| `assertThat(object).isEqualTo(other)` nhưng class không có value equality | So sánh có thể dựa identity | Khẳng định trường cần thiết, định nghĩa `equals`, hoặc recursive comparison có chủ đích |
| Assert whole DTO toString | Fail khó truy dấu trường khác biệt | `extracting`, `satisfies`, hoặc recursive comparison phù hợp |
| `assertThatThrownBy(...)` chỉ `isInstanceOf(Exception.class)` | Quá rộng, nhiều lỗi sai vẫn pass | Kiểm tra loại exception nghiệp vụ và message/code khi cần |
| Soft assertions trên object có thể null | Có thể ném NPE giữa các soft check | Hard assert tiền đề hoặc chia test |
| Assert collection theo index khi DB không bảo đảm thứ tự | Flaky khi thứ tự query thay đổi | `containsExactlyInAnyOrder` hay sort theo hợp đồng |
| So `BigDecimal("10.0")` bằng `BigDecimal("10.00")` nhưng chỉ cần numeric equality | Scale khiến `equals` false | `isEqualByComparingTo` nếu hợp đồng bỏ qua scale |
| So `double` bằng exact equality cho phép tính có làm tròn | Sai số nhị phân làm test fail | `isCloseTo(..., within(tolerance))` |
| Chỉ `doesNotThrowAnyException` cho function có output | Return sai vẫn có thể pass | Assert giá trị trả về và các side effects liên quan |

### 12.1. Nguyên tắc tránh test “xanh giả”

Đừng cố làm assertion nhẹ hơn để tránh thất bại. Ví dụ, nếu response phải có chính xác 3 dòng, thay `hasSize(3)` bằng `isNotEmpty()` sẽ làm test dễ xanh nhưng đánh mất hợp đồng chính. Nếu API phải trả `PAID`, dùng `isIn(PAID, DRAFT)` chỉ vì test dao động là dấu hiệu chưa làm rõ behavior.

Khi test flaky, kiểm tra fixture, đồng hồ, database, thứ tự chạy, network, cấu hình và luồng bất đồng bộ. AssertJ cho thông điệp tốt hơn nhưng không tự giải quyết tính độc lập và tính quyết định của test.

### 12.2. “Thông điệp lỗi dễ đọc” không có nghĩa là dài

So sánh hai mô tả:

- `as("test of business logic handling the object, validating the returned result")`: chung chung và dài.
- `as("trạng thái đơn %s sau khi thanh toán", orderId)`: có thông tin nghiệp vụ và định danh cụ thể.

Nên đưa **điều kiện nghiệp vụ + đối tượng liên quan** vào mô tả, tránh copy cả input lớn. Phần expected/actual nên để assertion chuyên biệt cung cấp.

## 13. Bài tập luyện viết và checklist review

### Bài tập 1: thay boolean bằng assertion đặc thù

Cho đoạn test có một `List<String> ids`:

```java
assertThat(ids.size() == 2).isTrue();
assertThat(ids.contains("R-01")).isTrue();
```

Hãy viết lại theo hai hợp đồng khác nhau:

- Chỉ cần có đúng 2 phần tử **và** chứa `R-01`.
- Cần chính xác hai ID `R-01`, `R-02` và không quan tâm thứ tự.

**Đáp án tham khảo** (hai trường hợp thay thế, không cộng gộp):

```java
assertThat(ids).hasSize(2).contains("R-01");

// Nếu tập ID phải chính xác và không có thứ tự:
assertThat(ids).containsExactlyInAnyOrder("R-01", "R-02");
```

Quan sát: điều kiện thứ hai mạnh hơn; nếu chỉ cần tập chính xác, không cần assert lại `hasSize(2)`.

### Bài tập 2: cải thiện thông báo lỗi

Cho `Receipt receipt` và câu:

```java
assertThat(receipt.totalQuantity() == 5).isTrue();
```

Hãy thay bằng assertion hiển thị expected/actual và mã phiếu. **Đáp án:**

```java
assertThat(receipt.totalQuantity())
        .as("tổng số lượng của phiếu %s", receipt.id())
        .isEqualTo(5);
```

Cách viết mới báo rõ lỗi ở trường nào; không làm mất tính mạnh của phép kiểm tra.

### Bài tập 3: test nhánh ngoại lệ

Service phải từ chối dòng hàng có số lượng 0 bằng `IllegalArgumentException` với message `quantity must be positive`. **Đáp án:**

```java
assertThatThrownBy(() -> service.create(
        "R-03",
        List.of(new ReceiptService.Item("PEN", 0))
))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("quantity must be positive");
```

Với implementation ở phần 4, điều kiện này được kiểm tra sau khi mã phiếu và danh sách hợp lệ, nên test đi đúng nhánh cần xác minh.

### Checklist

- [ ] Assertion bắt đầu từ **actual thực tế** và nêu expected theo đúng hợp đồng.
- [ ] Dùng phương thức đặc thù cho kiểu (String/number/list/map/optional/exception) thay vì giảm mọi thứ thành boolean.
- [ ] Với collection, xác định thứ tự, số lần xuất hiện và việc có cho phép phần tử thừa hay không.
- [ ] Với object, đã hiểu `equals`, identity và trường hợp cần deep comparison.
- [ ] Mô tả `as(...)` đứng trước phép kiểm tra; nêu bối cảnh hữu ích, không chứa bí mật.
- [ ] Không ghi đè thông báo mặc định nếu không có lý do rõ ràng.
- [ ] Ngoại lệ được kiểm tra đúng loại và thông điệp/code khi đó là hợp đồng.
- [ ] Soft assertions chỉ gom các điều kiện độc lập, không che tiền đề null hoặc làm test quá lớn.
- [ ] Các so sánh BigDecimal, floating point, Optional và collection đúng semantics.
- [ ] Test chạy được bằng JUnit Jupiter/build tool; assertion fail khi cố tình đưa sai đầu ra (sanity check khi cần).
- [ ] Test không phụ thuộc dữ liệu của test khác, database dùng chung hoặc thứ tự ngẫu nhiên để pass.

## 14. Tóm tắt kiến thức cốt lõi

AssertJ giúp viết test như các phát biểu kiểm chứng về dữ liệu: **`assertThat(actual)` + điều kiện cụ thể**, kèm **`as(...)`** để gắn ngữ cảnh khi thất bại. Một assertion tốt phải có **độ mạnh đúng hợp đồng**: đủ nghiêm để bắt lỗi thực sự, nhưng không ràng buộc thứ tự hoặc chi tiết triển khai mà nghiệp vụ không yêu cầu.

Với Spring Boot, hãy dùng AssertJ trong test thuần JUnit, test slice và integration test khi cần kiểm tra object/result. JUnit vẫn chạy test; Mockito/mock hoặc database test quản lý phụ thuộc; AssertJ giúp giải thích kết quả và chênh lệch. Khi thất bại, người đọc nên nhận ra ngay **đối tượng nào, điều kiện nào, expected gì, actual gì**, không phải đoán từ một boolean false.

## Tài liệu tham khảo

- [AssertJ — Documentation](https://assertj.github.io/doc/) — fluent assertions, collection assertions, exception assertions, soft assertions và mô tả thất bại.
- [AssertJ Core — API Documentation](https://javadoc.io/doc/org.assertj/assertj-core) — chữ ký API và overload theo version đang dùng.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/) — starter test và cách kiểm thử ứng dụng Spring Boot.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/) — JUnit Jupiter, test lifecycle và cách chạy test.
