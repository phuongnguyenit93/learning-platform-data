# Giữ ví dụ đồng bộ với API khi đổi tên method, chữ ký hoặc hành vi ngoại lệ

## 1. Ví dụ trong tài liệu cũng là một phần của hợp đồng API

Khi một thư viện Java đổi tên method, thêm tham số, thay kiểu trả về hoặc thay đổi ngoại lệ có thể phát sinh, mọi ví dụ và lời giải thích liên quan đều cần được rà soát. Một trang Javadoc vẫn có thể được sinh thành công dù đoạn code ví dụ đã gọi method cũ, mô tả sai tham số hoặc hứa một loại ngoại lệ mà implementation không còn ném.

Để tránh tình trạng đó, hãy xem các phần sau là một nhóm cần thay đổi cùng nhau:

1. **Khai báo API:** tên method, tham số, kiểu trả về, throws và hành vi thực tế.
2. **Documentation comment:** mô tả, @param, @return, @throws, @deprecated, @since và các liên kết {@link}.
3. **Ví dụ:** snippet inline, external snippet, README hoặc ví dụ trong test.
4. **Kiểm thử:** test xác nhận hành vi bình thường, đầu vào biên và loại ngoại lệ.
5. **Hướng dẫn chuyển đổi:** API cũ còn dùng được bao lâu, API thay thế và khác biệt ngữ nghĩa.

DocLint có thể phát hiện nhiều tham chiếu và tag không khớp với khai báo. Compiler phát hiện ví dụ gọi method hoặc truyền tham số sai kiểu. Test phát hiện hành vi và ngoại lệ thực tế khác với mô tả. Mỗi công cụ kiểm tra một phần; cần kết hợp chúng để giữ tài liệu đúng sau khi API thay đổi.

Bài này thuộc phần **Kiểm chứng tài liệu** của mô-đun **JAVA_VERSION_JAVA18**. Các ví dụ dùng cú pháp Java hiện đại và Javadoc vẫn được hỗ trợ trên JDK hiện hành. Trọng tâm là quy trình tiến hóa API, duy trì tương thích và đồng bộ code sample khi method hoặc hợp đồng ngoại lệ thay đổi.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện ảnh hưởng của việc đổi tên method, thay kiểu tham số và kiểu trả về.
- Phân biệt source compatibility, binary compatibility và tương thích hành vi.
- Duy trì method cũ bằng adapter được đánh dấu deprecated khi cần lộ trình chuyển đổi.
- Cập nhật @param, @return, @throws, @deprecated và {@link} theo API mới.
- Viết test cho ngoại lệ checked và unchecked, kể cả thay đổi về điều kiện phát sinh.
- Biên dịch external snippet cùng API và kiểm tra Javadoc trong CI.
- Dùng công cụ kiểm tra API compatibility để phát hiện thay đổi có thể phá vỡ client.

## 2. Một ví dụ API trước khi thay đổi

Giả sử thư viện hóa đơn cung cấp ReceiptService. Ở phiên bản 1, người gọi tạo biên nhận bằng create(customerId, amount). API mặc định sử dụng USD.

Receipt.java:

```java
package com.example.billing;

import java.math.BigDecimal;
import java.util.Currency;

public record Receipt(
        String customerId,
        BigDecimal amount,
        Currency currency
) {
}
```

ReceiptService.java phiên bản 1:

```java
package com.example.billing;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public final class ReceiptService {
    private static final Currency USD = Currency.getInstance("USD");

    private ReceiptService() {
    }

    /**
     * Tạo biên nhận bằng USD cho khách hàng.
     *
     * @param customerId mã khách hàng, không được null hoặc rỗng
     * @param amount số tiền phải lớn hơn 0
     * @return biên nhận được tạo
     * @throws NullPointerException nếu customerId hoặc amount là null
     * @throws IllegalArgumentException nếu customerId rỗng hoặc amount không dương
     */
    public static Receipt create(String customerId, BigDecimal amount) {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(amount, "amount");
        if (customerId.isBlank()) {
            throw new IllegalArgumentException("customerId must not be blank");
        }
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        return new Receipt(customerId, amount, USD);
    }
}
```

External snippet được đặt cạnh package source trong snippet-files:

```text
src/main/java/com/example/billing/
├── Receipt.java
├── ReceiptService.java
└── snippet-files/
    └── ReceiptExample.java
```

ReceiptExample.java:

```java
package com.example.billing;

import java.math.BigDecimal;

public final class ReceiptExample {
    private ReceiptExample() {
    }

    public static void main(String[] args) {
        // @start region=create
        Receipt receipt = ReceiptService.create(
                "ACME",
                new BigDecimal("125.00")
        );
        System.out.println(receipt.amount() + " " + receipt.currency());
        // @end region=create
    }
}
```

Trong ReceiptService.java, Javadoc tham chiếu ví dụ:

```java
/**
 * Dịch vụ tạo biên nhận.
 *
 * <p>Ví dụ:</p>
 * {@snippet class=ReceiptExample region=create}
 */
```

Hợp đồng phiên bản 1 có thể tóm tắt như sau:

| Thành phần | Hợp đồng |
| --- | --- |
| Method | create(String, BigDecimal) |
| Kết quả | Receipt có currency là USD |
| customerId | Không được null hoặc blank; giữ nguyên khoảng trắng đầu/cuối nếu không blank |
| amount | Không được null và phải lớn hơn 0 |
| Ngoại lệ | NullPointerException cho null; IllegalArgumentException cho giá trị không hợp lệ |

Hãy lưu ý chi tiết khoảng trắng. Phiên bản 1 giữ nguyên chuỗi " ACME "; đây là hành vi quan sát được của API. Khi phiên bản sau bắt đầu chuẩn hóa bằng strip(), thay đổi đó có thể ảnh hưởng client dù chữ ký method không đổi.

## 3. Phiên bản mới: đổi tên method và bổ sung tham số

Giả sử phiên bản 2 muốn dùng tên issue và cho phép người gọi chọn currency. Đồng thời, API mới chuẩn hóa customerId bằng strip().

Khai báo mới:

```java
/**
 * Tạo biên nhận theo currency được chỉ định.
 *
 * <p>Mã khách hàng được loại bỏ khoảng trắng ở hai đầu trước khi lưu.</p>
 *
 * @param customerId mã khách hàng, không được null hoặc blank
 * @param amount số tiền phải lớn hơn 0
 * @param currency đơn vị tiền tệ, không được null
 * @return biên nhận đã chuẩn hóa mã khách hàng
 * @throws NullPointerException nếu một trong các tham số là null
 * @throws IllegalArgumentException nếu customerId rỗng sau khi chuẩn hóa hoặc amount không dương
 * @since 2.0
 */
public static Receipt issue(
        String customerId,
        BigDecimal amount,
        Currency currency
) {
    return createInternal(customerId, amount, currency, true);
}
```

Để giữ tương thích cho client cũ, có thể giữ method create như một adapter. Adapter tiếp tục dùng USD và giữ nguyên cách xử lý khoảng trắng của phiên bản 1:

```java
/**
 * @deprecated Từ phiên bản 2.0, dùng
 * {@link #issue(String, BigDecimal, Currency)} để chọn currency rõ ràng.
 * Method này tiếp tục dùng USD và giữ nguyên mã khách hàng như trước.
 */
@Deprecated(since = "2.0", forRemoval = false)
public static Receipt create(String customerId, BigDecimal amount) {
    return createInternal(
            customerId,
            amount,
            Currency.getInstance("USD"),
            false
    );
}

private static Receipt createInternal(
        String customerId,
        BigDecimal amount,
        Currency currency,
        boolean normalizeCustomerId
) {
    Objects.requireNonNull(customerId, "customerId");
    Objects.requireNonNull(amount, "amount");
    Objects.requireNonNull(currency, "currency");

    String effectiveCustomerId = normalizeCustomerId
            ? customerId.strip()
            : customerId;

    if (effectiveCustomerId.isBlank()) {
        throw new IllegalArgumentException("customerId must not be blank");
    }
    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }
    return new Receipt(effectiveCustomerId, amount, currency);
}
```

Trong ví dụ này, adapter cũ vẫn có cùng tên, tham số và hành vi cũ. Method mới cung cấp chức năng mới và chuẩn hóa mã khách hàng. Việc giữ lại adapter giúp client có thời gian chuyển đổi; nó cũng cần được kiểm thử vì một adapter sai có thể âm thầm đổi hành vi của người dùng cũ.

### 3.1. Khi nào nên giữ adapter?

Giữ method cũ nếu thư viện có client bên ngoài và chính sách tương thích yêu cầu một giai đoạn chuyển đổi. Adapter nên:

- Gọi logic dùng chung để tránh hai implementation dần lệch nhau.
- Giữ hành vi cũ nếu cam kết tương thích yêu cầu như vậy.
- Có @Deprecated annotation và Javadoc @deprecated giải thích API thay thế.
- Liên kết trực tiếp tới method mới bằng {@link}.
- Có test xác nhận adapter vẫn hoạt động như hợp đồng cũ.

Nếu method cũ không thể duy trì an toàn hoặc giữ lại gây nhầm lẫn nghiêm trọng, hãy coi việc xóa nó là thay đổi breaking, nêu rõ trong release notes và tăng major version theo chính sách versioning của dự án.

### 3.2. Dùng @Deprecated đúng cách

@Deprecated(since = "2.0", forRemoval = false) đánh dấu API không còn được khuyến nghị. forRemoval = false nói rằng hiện chưa có ý định xóa API. Khi đã có kế hoạch loại bỏ trong một phiên bản tương lai, có thể đặt forRemoval = true và nêu thời điểm/lộ trình trong tài liệu.

Javadoc @deprecated phải giải thích lý do, phiên bản bắt đầu deprecated và method thay thế. Nên có {@link} tới API mới. Annotation và tag cần đi cùng nhau để compiler, IDE và trang API hiển thị cùng một thông tin.

## 4. Đổi tên method hoặc thay chữ ký ảnh hưởng thế nào?

Đổi tên method, đổi kiểu tham số, thêm hoặc xóa tham số thường tạo ra một method signature mới. Client biên dịch từ source cũ sẽ không còn tìm được khai báo cũ nếu method đó bị xóa. Binary đã biên dịch trước đó cũng có thể không liên kết được với thư viện mới.

| Thay đổi | Source client | Binary client đã biên dịch | Việc cần làm |
| --- | --- | --- | --- |
| Đổi tên create thành issue rồi xóa create | Không biên dịch nếu còn gọi create | Có thể gặp NoSuchMethodError khi liên kết method cũ | Giữ adapter hoặc phát hành breaking change có lộ trình |
| Thêm tham số vào create | Lời gọi cũ không khớp chữ ký | Method cũ không còn descriptor tương ứng | Giữ overload cũ nếu cần tương thích |
| Đổi kiểu tham số BigDecimal thành long | Cần sửa lời gọi và dữ liệu | Chữ ký cũ không còn | Thêm overload/adapter nếu chuyển đổi được |
| Đổi kiểu trả về | Có thể làm assignment hoặc lời gọi không còn hợp lệ | Thay đổi method descriptor; binary cũ có thể không liên kết | Thêm method mới với tên khác hoặc thiết kế migration |
| Chỉ đổi tên tham số customerId thành accountId | Lời gọi theo vị trí vẫn biên dịch | Không ảnh hưởng binary cũ | Cập nhật @param và ví dụ; kiểm tra nếu dùng reflection parameter names |
| Chỉ thêm overload | Thường vẫn biên dịch, nhưng có thể gây mơ hồ cho một số lời gọi khi recompile | Binary cũ tiếp tục gọi overload đã được chọn lúc compile | Kiểm tra các lời gọi có null/lambda/method reference |

Java không cho phép overload chỉ khác kiểu trả về. Khi thay kiểu trả về, không thể giữ hai method cùng tên và cùng tham số chỉ để phục vụ client cũ và mới.

### 4.1. Source compatibility và binary compatibility

Hai khái niệm này khác nhau:

- **Source compatibility:** source client có thể được biên dịch lại với phiên bản thư viện mới mà không cần sửa hay không.
- **Binary compatibility:** file .class client đã biên dịch có thể tiếp tục liên kết và chạy với phiên bản thư viện mới hay không.

Ví dụ, thêm một overload thường không phá binary cũ vì lời gọi method đã được phân giải khi compile. Tuy nhiên, khi compile lại source, overload mới có thể làm một lời gọi trở nên mơ hồ. Ngược lại, xóa method public cũ có thể khiến binary cũ lỗi khi JVM tìm method mà nó tham chiếu.

JLS mô tả các quy tắc tiến hóa binary ở Chương 13. Với thư viện được phân phối cho nhiều client, hãy kiểm tra cả hai dạng tương thích thay vì chỉ chạy test trong repository của thư viện.

### 4.2. Cập nhật @param và @return

Khi chữ ký đổi, rà lại tất cả tag:

```java
/**
 * Tạo biên nhận theo currency được chỉ định.
 *
 * @param customerId mã khách hàng sau khi loại bỏ khoảng trắng ở hai đầu
 * @param amount số tiền phải lớn hơn 0
 * @param currency currency dùng cho biên nhận
 * @return biên nhận chứa mã khách hàng đã chuẩn hóa, số tiền và currency
 */
public static Receipt issue(
        String customerId,
        BigDecimal amount,
        Currency currency
) {
    // ...
}
```

Nếu đổi tên tham số trong source, tên trong @param phải đổi theo. Nếu thêm tham số, cần thêm @param tương ứng. Nếu kiểu trả về chuyển từ void sang một giá trị, bổ sung @return; nếu method chuyển thành void, xóa mô tả @return cũ.

DocLint có thể phát hiện tag @param không khớp tên tham số, thiếu @param hoặc @return trong các trường hợp thuộc phạm vi kiểm tra. Nhưng nó không thể quyết định mô tả tham số có còn đúng nghĩa nghiệp vụ hay không; người sửa API phải rà nội dung.

## 5. Đồng bộ hợp đồng ngoại lệ

Ngoại lệ là một phần quan trọng trong cách client sử dụng API. Khi implementation thay đổi điều kiện ném exception, cần cập nhật đồng thời:

- throws clause nếu là checked exception.
- Javadoc @throws để giải thích điều kiện phát sinh.
- Test xác nhận loại exception và điều kiện kích hoạt.
- Ví dụ hoặc hướng dẫn xử lý lỗi nếu client cần thay đổi.

### 5.1. Checked exception và unchecked exception

**Checked exception** được compiler kiểm tra. Nếu lời gọi có thể ném một checked exception, caller phải bắt nó hoặc khai báo tiếp trong throws. **Unchecked exception** như IllegalArgumentException và NullPointerException không cần khai báo để compiler chấp nhận lời gọi.

Điều này dẫn đến hai lưu ý:

1. Thêm checked exception vào throws có thể làm source client không biên dịch lại được vì caller chưa bắt hoặc khai báo exception mới.
2. Thay đổi throws clause không làm binary cũ mất liên kết; JLS quy định các thay đổi trong throws clause không phá binary compatibility vì chúng được kiểm tra ở compile time. Tuy vậy, hành vi runtime vẫn có thể thay đổi nếu implementation bắt đầu ném một exception mới.

Unchecked exception không được compiler kiểm tra, nhưng nếu nó là một phần hợp đồng của API thì vẫn nên mô tả bằng @throws và kiểm thử. Đừng dựa vào DocLint để tự phát hiện mọi thay đổi về unchecked exception; công cụ không thể suy ra đầy đủ hành vi runtime từ thân method.

### 5.2. Ví dụ thêm checked exception

Giả sử phiên bản mới thêm thao tác ghi biên nhận ra file:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

/**
 * Ghi biên nhận vào file đích.
 *
 * @param receipt biên nhận cần ghi
 * @param destination đường dẫn file đích
 * @throws NullPointerException nếu receipt hoặc destination là null
 * @throws IOException nếu không thể ghi dữ liệu
 */
public static void write(
        Receipt receipt,
        Path destination
) throws IOException {
    Objects.requireNonNull(receipt, "receipt");
    Objects.requireNonNull(destination, "destination");
    Files.writeString(destination, receipt.toString(), StandardCharsets.UTF_8);
}
```

Caller phải xử lý IOException:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Path;

try {
    ReceiptService.write(receipt, Path.of("receipt.txt"));
} catch (IOException e) {
    // Báo lỗi lưu trữ hoặc thử lại theo chính sách của ứng dụng.
    throw new UncheckedIOException(e);
}
```

Khi thêm IOException, hãy cập nhật mô tả @throws, ví dụ gọi method và test đường dẫn không thể ghi. Nếu API trước đó không có checked exception này, việc thêm nó là thay đổi source contract cần thông báo cho client.

### 5.3. Kiểm thử loại và điều kiện ngoại lệ

Với JUnit Jupiter, dùng assertThrows để xác nhận đúng exception:

```java
package com.example.billing;

import java.math.BigDecimal;
import java.util.Currency;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class ReceiptServiceTest {
@Test
void issueRejectsBlankCustomerId() {
    assertThrows(
            IllegalArgumentException.class,
            () -> ReceiptService.issue(
                    "   ",
                    new BigDecimal("10.00"),
                    Currency.getInstance("USD")
            )
    );
}

@Test
void issueRejectsNullCurrency() {
    assertThrows(
            NullPointerException.class,
            () -> ReceiptService.issue(
                    "ACME",
                    new BigDecimal("10.00"),
                    null
            )
    );
}

@Test
void issueRejectsNonPositiveAmount() {
    assertThrows(
            IllegalArgumentException.class,
            () -> ReceiptService.issue(
                    "ACME",
                    BigDecimal.ZERO,
                    Currency.getInstance("USD")
            )
    );
}
}
```

Nếu message của exception là một phần hợp đồng được công bố, có thể kiểm tra message riêng. Nếu message chỉ phục vụ chẩn đoán nội bộ, tránh khóa test vào nguyên văn message vì điều đó làm thay đổi wording trở thành breaking change không cần thiết.

### 5.4. Kiểm thử hành vi khi giữ method cũ

Adapter cũ phải có test riêng để chứng minh nó vẫn giữ hành vi trước migration:

```java
@SuppressWarnings("deprecation")
@Test
void deprecatedCreatePreservesLegacyCustomerId() {
    Receipt receipt = ReceiptService.create(
            " ACME ",
            new BigDecimal("10.00")
    );

    assertEquals(" ACME ", receipt.customerId());
    assertEquals("USD", receipt.currency().getCurrencyCode());
}

@Test
void issueNormalizesCustomerId() {
    Receipt receipt = ReceiptService.issue(
            " ACME ",
            new BigDecimal("10.00"),
            Currency.getInstance("USD")
    );

    assertEquals("ACME", receipt.customerId());
}
```

Hai test này làm rõ khác biệt có chủ ý giữa API cũ và API mới. Nếu adapter cũ vô tình gọi logic chuẩn hóa mới, test sẽ phát hiện hành vi cũ đã thay đổi.

## 6. Cập nhật Javadoc, liên kết và ví dụ sau khi đổi API

Khi method thay đổi, tìm tất cả vị trí phụ thuộc vào chữ ký cũ:

- {@link #create(String, BigDecimal)} và @see.
- External snippet dùng ReceiptService.create(...).
- Snippet inline hoặc hybrid snippet.
- @param, @return, @throws.
- README, package documentation, hướng dẫn migration và test fixture.

Ví dụ Javadoc mới có thể liên kết cả API thay thế và adapter:

```java
/**
 * Dịch vụ tạo biên nhận.
 *
 * <p>Để chọn đơn vị tiền tệ, dùng
 * {@link #issue(String, BigDecimal, Currency)}.
 * API cũ {@link #create(String, BigDecimal)} vẫn được giữ để hỗ trợ
 * client đang chuyển đổi.</p>
 */
public final class ReceiptService {
    // ...
}
```

### 6.1. Cập nhật external snippet

Sau khi đổi ví dụ từ create sang issue, file snippet phải được sửa cùng lúc:

```java
package com.example.billing;

import java.math.BigDecimal;
import java.util.Currency;

public final class ReceiptExample {
    private ReceiptExample() {
    }

    public static void main(String[] args) {
        // @start region=issue
        Receipt receipt = ReceiptService.issue(
                "ACME",
                new BigDecimal("125.00"),
                Currency.getInstance("USD")
        );
        System.out.println(receipt.amount() + " " + receipt.currency());
        // @end region=issue
    }
}
```

Nếu Javadoc vẫn tham chiếu region=create trong khi file chỉ còn region=issue, Javadoc sẽ báo không tìm thấy region. Nếu file vẫn có region cũ nhưng bên trong gọi method đã xóa, Javadoc có thể trích nội dung mà không phát hiện lỗi compile. Đưa file snippet vào bước biên dịch là cách bắt lỗi thứ hai.

### 6.2. Biên dịch API và external snippet cùng nhau

Với cấu trúc package ở phần 2, lệnh sau biên dịch source API và ví dụ:

```bash
mkdir -p build/example-classes

javac --release 18 -encoding UTF-8 -d build/example-classes \
  src/main/java/com/example/billing/Receipt.java \
  src/main/java/com/example/billing/ReceiptService.java \
  src/main/java/com/example/billing/snippet-files/ReceiptExample.java

java -cp build/example-classes com.example.billing.ReceiptExample
```

Khi API đổi chữ ký, compiler sẽ báo nếu ví dụ vẫn gọi method cũ hoặc truyền thiếu tham số. Đây là phép kiểm tra source thực tế; chỉ sinh Javadoc không thay thế được nó.

### 6.3. Chạy Javadoc và DocLint

```bash
javadoc --release 18 \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  -Xdoclint:all -Werror \
  --source-path src/main/java \
  -d build/docs \
  com.example.billing
```

DocLint giúp bắt các vấn đề như:

- @param không còn khớp tên tham số.
- Thiếu @param hoặc @return trong comment cần được kiểm tra.
- {@link} trỏ tới method hoặc kiểu không tồn tại.
- @throws mô tả type không hợp lệ hoặc tài liệu khai báo chưa hoàn chỉnh theo quy tắc DocLint.

DocLint không chứng minh mô tả về ngoại lệ khớp với implementation. Chỉ test thực thi mới xác nhận điều kiện và loại exception mà method thực sự ném.

## 7. Tổ chức kiểm thử để ví dụ không lệch khỏi API

Một chiến lược thực tế nên có các lớp kiểm tra riêng:

| Lớp kiểm tra | Mục đích | Công cụ |
| --- | --- | --- |
| Compile API | Source API hợp lệ và không có lỗi kiểu. | javac, Maven Compiler hoặc Gradle Java Plugin |
| Compile snippet | Mọi external snippet được quảng bá là Java có thể biên dịch. | javac hoặc source set riêng trong build tool |
| Unit test | Hành vi bình thường, biên và exception khớp hợp đồng. | JUnit Jupiter |
| Smoke test ví dụ | Ví dụ được mô tả là chạy được thực sự chạy được. | java hoặc task chạy ví dụ |
| Javadoc/DocLint | Tag, link, snippet region và markup hợp lệ. | javadoc -Xdoclint:all -Werror |
| API compatibility | Phát hiện thay đổi public API ảnh hưởng client cũ. | Revapi hoặc công cụ tương đương |

External snippet trong snippet-files không mặc nhiên là một source set được Maven hoặc Gradle biên dịch. Hãy cấu hình build để đưa chúng vào bước compile/test, hoặc dùng một test source riêng có cùng lời gọi API. Nếu không có bước đó, snippet có thể lỗi dù Javadoc vẫn sinh HTML.

### 7.1. API compatibility checker

Với thư viện public, có thể thêm công cụ so sánh API hiện tại với artifact đã phát hành. Revapi Maven Plugin hỗ trợ kiểm tra thay đổi API trong build và cho phép cấu hình mức tương thích cần chấp nhận. Một lệnh kiểm tra có thể được gọi trong pipeline:

```bash
./mvnw -B -ntp verify revapi:check
```

Hãy cấu hình baseline artifact và chính sách severity của Revapi theo quy tắc versioning của dự án. Một thay đổi API có thể được cho phép nếu đây là major release; điều quan trọng là CI phải làm rõ thay đổi nào đang được chấp nhận và vì sao.

API compatibility checker không thay thế compile client, test hành vi, Javadoc hoặc migration guide. Nó tập trung vào khác biệt cấu trúc API và các quy tắc tương thích mà công cụ hỗ trợ.

## 8. Quy trình xử lý một thay đổi API trong pull request

Khi đổi method, tham số hoặc ngoại lệ, làm theo thứ tự:

1. **Xác định hợp đồng cũ.** Ghi lại chữ ký, kiểu trả về, ngoại lệ, giá trị biên và hành vi quan sát được.
2. **Đánh giá mức tương thích.** Kiểm tra source, binary và hành vi; quyết định có cần overload hoặc deprecated adapter.
3. **Sửa API.** Đặt tên method, tham số, kiểu trả về và validation mới.
4. **Sửa Javadoc.** Đồng bộ mô tả, @param, @return, @throws, @deprecated, @since và link.
5. **Sửa ví dụ.** Cập nhật snippet inline/external và các lời gọi API ở README hoặc hướng dẫn.
6. **Cập nhật test.** Test API mới, adapter cũ, exception và mọi thay đổi hành vi.
7. **Biên dịch ví dụ.** Đưa external snippet vào compile/test để phát hiện lời gọi cũ hoặc kiểu dữ liệu sai.
8. **Sinh Javadoc.** Bật DocLint và coi warning theo chính sách dự án.
9. **Kiểm tra API diff.** Chạy Revapi hoặc công cụ tương đương nếu thư viện có client bên ngoài.
10. **Viết migration note.** Nêu API cũ, API mới, khác biệt ngữ nghĩa và lộ trình deprecated/removal.

### Checklist review

- [ ] Tất cả call site trong source và test dùng đúng chữ ký mới.
- [ ] Không còn {@link} hoặc @see trỏ tới method đã xóa.
- [ ] Tên trong @param khớp tên tham số.
- [ ] Mô tả @return phản ánh đúng kiểu và ý nghĩa kết quả.
- [ ] @throws mô tả các exception quan trọng cùng điều kiện phát sinh.
- [ ] Checked exception mới đã được xử lý ở caller và trong ví dụ.
- [ ] Unchecked exception có ý nghĩa hợp đồng đã được ghi và có test.
- [ ] External snippet đã được biên dịch, không chỉ được Javadoc trích.
- [ ] Adapter deprecated có test xác nhận hành vi cũ.
- [ ] Khác biệt source/binary compatibility đã được đánh giá.
- [ ] Release note/migration guide nêu rõ thay đổi hành vi.
- [ ] Javadoc/DocLint và API compatibility check đạt.

## 9. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ đổi method trong implementation | Snippet và link vẫn gọi method cũ | Tìm tất cả call site, link và tài liệu tham chiếu |
| Chỉ chạy Javadoc | External snippet có thể được trích dù gọi method không còn tồn tại | Biên dịch snippet trong CI |
| Chỉ cập nhật @param | Mô tả nghiệp vụ, @return hoặc exception có thể đã sai | Rà toàn bộ hợp đồng method |
| Xóa method cũ ngay khi đổi tên | Source client lỗi compile; binary cũ có thể lỗi liên kết | Giữ adapter deprecated nếu cần migration |
| Adapter gọi method mới nhưng đổi hành vi cũ ngoài ý muốn | Client cũ vẫn compile nhưng kết quả thay đổi | Test riêng hành vi adapter |
| Nghĩ throws là một phần của binary descriptor | Đánh giá sai loại tương thích | Phân biệt compile-time checking với binary compatibility |
| Không ghi unchecked exception vì compiler không bắt buộc | Người dùng không biết điều kiện lỗi quan trọng | Ghi @throws và kiểm thử |
| Coi DocLint là kiểm tra ngữ nghĩa | Tài liệu có thể hợp lệ về cú pháp nhưng sai hành vi | Đối chiếu Javadoc với test và implementation |
| Thêm overload mà không kiểm tra source call site | Một số lời gọi có thể trở nên mơ hồ khi biên dịch lại | Compile client mẫu và kiểm tra null/lambda/method reference |

## 10. Tài liệu tham khảo chính thức

- [Java Language Specification, Chapter 13 — Binary Compatibility (JDK 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html): tác động của đổi tên method, đổi kiểu tham số, kiểu trả về, overload và throws clause đối với binary cũ.
- [Java Language Specification, Chapter 11 — Exceptions (JDK 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-11.html): checked exception, unchecked exception và kiểm tra exception ở compile time.
- [Javadoc Documentation Comment Specification for the Standard Doclet (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): quy tắc @param, @return, @throws, @deprecated, {@link} và documentation comment.
- [Deprecated (Java SE 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Deprecated.html): ý nghĩa since và forRemoval, khuyến nghị liên kết tới API thay thế.
- [Revapi Maven Plugin](https://revapi.org/revapi-maven-plugin/index.html): kiểm tra thay đổi API trong Maven build.
- [How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html): hướng dẫn viết mô tả method, @throws và migration text cho API deprecated.

**Ghi nhớ:** Khi API đổi, hãy cập nhật cùng lúc khai báo, Javadoc, ví dụ, test và hướng dẫn migration. Compiler xác nhận chữ ký; test xác nhận hành vi và ngoại lệ; Javadoc/DocLint xác nhận liên kết và tag; API compatibility checker giúp đánh giá ảnh hưởng tới client đã phát hành. Giữ adapter deprecated khi cần lộ trình tương thích và kiểm thử riêng để bảo đảm adapter không làm thay đổi hợp đồng cũ ngoài dự kiến.
