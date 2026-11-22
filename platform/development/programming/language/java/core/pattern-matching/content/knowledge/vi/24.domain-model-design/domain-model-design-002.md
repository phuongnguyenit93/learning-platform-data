# Chọn record cho dữ liệu bất biến trong thiết kế domain model (Java 21+)

## 1. Bài toán thiết kế: đối tượng đại diện cho *giá trị* hay *thực thể*?

Trong Java, `record` là một cách khai báo **lớp mang dữ liệu với tập trạng thái được xác định từ các component**. Khi thiết kế domain model, câu hỏi quan trọng không phải “có bao nhiêu field?”, mà là: **đối tượng này được nhận diện bởi giá trị của nó hay bởi danh tính và vòng đời riêng?**

Ví dụ: tọa độ `Point(2, 3)`, khoảng thời gian, mã khách hàng, dòng đơn hàng và ảnh chụp trạng thái đơn hàng thường được xem là **value object**. Hai giá trị có cùng thành phần và cùng bất biến nghiệp vụ có thể được coi là tương đương. Với dạng này, record thường biểu diễn ý định rất tốt.

Ngược lại, `Customer` hoặc `Order` trong hệ thống giao dịch có thể là **entity**: nó giữ danh tính ổn định (ID), có lịch sử chuyển trạng thái, phiên bản đồng thời, quan hệ ORM và vòng đời nghiệp vụ. Hai entity có cùng tên, địa chỉ hiện tại chưa chắc là cùng thực thể. Dùng record làm entity trực tiếp có thể làm mờ ý nghĩa danh tính và cản trở một số cơ chế persistence.

**Mục tiêu bài học:** biết chọn khi nào dùng record, hiểu giới hạn bất biến của record, thiết kế constructor có invariant, phòng mutable component, cân nhắc equality và chọn một mô hình phù hợp với pattern matching.

Phiên bản: `record` là tính năng chuẩn từ **Java 16** (JEP 395); ví dụ Java 17 có thể dùng record và compact constructor. Ví dụ về **record patterns trong `switch`** ở bài dùng cú pháp chuẩn **Java 21+** (JEP 440 và 441), không cần `--enable-preview`.

## 2. Một record thực sự mang lại điều gì?

Khai báo ngắn gọn:

```java
record Point(int x, int y) {}
```

Compiler cung cấp cấu trúc tương đương về ý nghĩa với một lớp mang hai component `int`, gồm:

- Hai trường trạng thái tương ứng với component, kiểu `private final`.
- Constructor chuẩn (canonical constructor) nhận `x` và `y`.
- Các accessor `x()` và `y()`, không phải JavaBean getter `getX()`/`getY()`.
- `equals(Object)` và `hashCode()` dựa trên các component, cùng `toString()` biểu diễn trạng thái.
- Lớp record là `final`; nó không kế thừa lớp ứng dụng bất kỳ (record kế thừa `java.lang.Record`), nhưng **có thể implement interface**.

Cách dùng:

```java
Point first = new Point(2, 3);
Point second = new Point(2, 3);

System.out.println(first.x());          // 2
System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false (hai đối tượng mới)
```

**Ý nghĩa:** record thuận tiện cho **value semantics**: so sánh nội dung thay vì địa chỉ tham chiếu. Tuy nhiên Java không tự suy ra quan hệ domain từ mọi field. `equals` mặc định chỉ so sánh các component theo cơ chế equality của Java, không biết quy tắc nghiệp vụ như “hai mã khách hàng khác chữ hoa/thường vẫn như nhau”.

### Record không đồng nghĩa với tất cả các kiểu bất biến

`record` là lớp tham chiếu, không phải primitive hay cơ chế *deep freeze*. Các tham chiếu component được lưu trong final fields, nhưng **đối tượng mà chúng trỏ tới vẫn có thể thay đổi**. Constructor của record cũng không tự động từ chối `null`, số âm, chuỗi trống hoặc dữ liệu nghiệp vụ sai. Tác giả domain model vẫn phải xác định bất biến và cách bảo vệ chúng.

## 3. Bảng quyết định: chọn record hay class?

| Loại dữ liệu | Thường nên dùng | Lý do |
| --- | --- | --- |
| Điểm, khoảng giá trị, kích thước, tọa độ | `record` | Giá trị được quyết định bởi các component; ít trạng thái |
| Mã định danh kiểu `CustomerId`, `ProductCode` | `record` | Tạo kiểu domain rõ nghĩa, đặt validation/normalization ở constructor |
| DTO nhập/xuất, thông điệp, kết quả tính toán | `record` nếu framework hỗ trợ | Thường là một snapshot rõ các thành phần; accessor và equality thuận tiện |
| Dòng đơn hàng, tham số cấu hình bất biến | `record` nếu component được bảo vệ | Tốt cho dữ liệu mang giá trị và truyền qua nhiều tầng xử lý |
| Entity có identity, lifecycle, lịch sử, version | Thường là `class` với thiết kế identity rõ | Equality theo trạng thái không luôn đồng nghĩa equality theo danh tính |
| Đối tượng phải thay đổi trạng thái nhiều lần bằng phương thức | `class` hoặc mô hình chuyển trạng thái tạo bản mới | Record không có mutable instance state bổ sung; dùng record để mô tả trạng thái tĩnh |
| Đối tượng cần kế thừa class khác hoặc proxy subclass | Không phù hợp với `record` | Record là `final` và chỉ kế thừa `Record` |
| Đối tượng chứa cấu trúc mutable lớn/cyclic | Cân nhắc kỹ | Phải làm defensive copy và định nghĩa equality phù hợp |

Đây là **hướng dẫn thiết kế**, không phải luật “mọi entity đều cấm record” hay “mọi DTO đều bắt buộc record”. Một entity được **đại diện bằng record snapshot để đọc dữ liệu** vẫn rất hợp lý, dù entity gốc trong persistence dùng class. Quyết định phụ thuộc vào hợp đồng truy cập, vòng đời và công cụ sử dụng.

**Câu hỏi chốt:** người dùng domain có kỳ vọng `new Value(a, b).equals(new Value(a, b))` là true không? Nếu có, state được định nghĩa bởi các component và không cần thay đổi sau khi tạo, record là ứng viên tốt.

## 4. Bất biến nông và bất biến sâu

### 4.1. Component primitive hoặc immutable có sẵn

```java
record Point(int x, int y) {}
record CustomerId(String value) {}
```

`int` là primitive và `String` là immutable. Nếu constructor không cho phép trạng thái sai và record không chứa tham chiếu mutable khác, dữ liệu bên trong có thể được xem là bất biến theo kỳ vọng thông thường. Bạn không thể gọi `point.setX(10)` vì record không tự sinh setter, và component `x` của record không thể được gán lại sau khi xây dựng.

Nhưng record **không tự kiểm tra** rằng `CustomerId.value` là chuỗi hợp lệ. Muốn coi nó là value object tin cậy, phải thiết kế invariant.

### 4.2. Component danh sách: `final` không bảo vệ đối tượng đích

Ví dụ **có nguy cơ thay đổi từ bên ngoài**:

```java
record UnsafeOrder(java.util.List<String> lines) {}

// Minh họa trong phương thức:
var source = new java.util.ArrayList<String>();
source.add("BOOK");
var order = new UnsafeOrder(source);

source.add("PEN");           // Thay đổi danh sách nằm trong record!
order.lines().add("RULER"); // Accessor trả chính danh sách mutable.
```

Mặc dù field `lines` là final, nội dung danh sách có thể thay đổi. Hành vi của `equals`/`hashCode` cũng có thể thay đổi theo thời gian do component mutable, gây lỗi khó tìm nếu dùng record làm khóa trong `HashMap` hoặc phần tử `HashSet`.

**Cách bảo vệ:**

```java
record OrderLines(java.util.List<String> lines) {
    OrderLines {
        lines = java.util.List.copyOf(
            java.util.Objects.requireNonNull(lines, "lines"));
    }
}
```

`List.copyOf` tạo một danh sách **không cho phép sửa qua accessor** và không chịu ảnh hưởng bởi các thao tác thêm/xóa trên danh sách nguồn sau khi tạo record. Nó cũng không chấp nhận phần tử `null`. Với component là `String`, mỗi phần tử bất biến, nên đây là một mô hình khá an toàn.

**Giới hạn quan trọng:** `List.copyOf` không biến một phần tử mutable thành immutable. Nếu `List<Customer>` chứa các đối tượng `Customer` có setter, phần tử đó vẫn có thể bị thay đổi thông qua tham chiếu giữ ở nơi khác. Để đạt bất biến sâu hơn, phải dùng element type bất biến (ví dụ các record thành phần an toàn), hoặc tạo bản sao phòng vệ cho từng phần tử theo hợp đồng domain.

### 4.3. Component mảng: cần cẩn trọng cả accessor lẫn equality

```java
record UnsafeBytes(byte[] data) {}
```

Mảng Java mutable. `new UnsafeBytes(source)` giữ cùng tham chiếu; `data()` trả mảng đó. Ngoài ra, mặc định equality của record **không so sánh nội dung hai mảng**: mảng dùng equality theo tham chiếu nếu không có logic riêng.

Nếu buộc phải dùng mảng làm value object, có thể viết:

```java
record Bytes(byte[] data) {
    Bytes {
        data = java.util.Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Bytes b
            && java.util.Arrays.equals(data, b.data);
    }

    @Override
    public int hashCode() {
        return java.util.Arrays.hashCode(data);
    }
}
```

Constructor sao chép dữ liệu lúc nhận; accessor sao chép lúc trả; `equals/hashCode` áp dụng nội dung mảng theo cùng một chính sách. Cần cân nhắc chi phí sao chép và kích thước dữ liệu. Nếu có thể, dùng một kiểu component đã có value semantics và tính bất biến phù hợp sẽ đơn giản hơn.

Một chi tiết đáng nhớ: **defensive copy, null validation và equality là ba trách nhiệm khác nhau**. Chỉ gắn nhãn record không làm thay chúng.

## 5. Canonical constructor và invariant nghiệp vụ

Một record value object hữu ích khi trạng thái **hợp lệ ngay lúc được tạo**. Ví dụ mã khách hàng không được rỗng:

```java
record CustomerId(String value) {
    CustomerId {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("CustomerId is blank");
        }
    }
}
```

Đây là **compact canonical constructor**. Trong thân constructor, biến `value` chính là tham số tương ứng component. Bạn có thể kiểm tra và chuẩn hóa tham số; compiler gán tham số sau xử lý cho field cuối cùng của record khi constructor kết thúc bình thường.

Các nguyên tắc:

1. **Kiểm tra cấu trúc:** không null, không rỗng, kiểu và miền giá trị được phép.
2. **Chuẩn hóa có chủ đích:** `strip()`, chuẩn hóa case hoặc làm tròn chỉ khi domain yêu cầu và có quy tắc rõ.
3. **Bảo vệ mutable input:** `List.copyOf`, copy map/set hoặc bản sao có defensive strategy tương ứng.
4. **Không để đối tượng tồn tại trong trạng thái nửa hợp lệ:** ném exception ngay khi invariant thất bại.
5. **Giữ nhất quán với equals:** sau normalization, hai input mang cùng nghĩa có thể cho hai record bằng nhau.

Ví dụ với giá tiền tính theo đơn vị nhỏ nhất:

```java
record Money(long minorUnits, String currency) {
    Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        currency = java.util.Objects.requireNonNull(currency, "currency")
            .strip()
            .toUpperCase(java.util.Locale.ROOT);
        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }
    }
}
```

Ở đây `minorUnits` được định nghĩa là số nguyên không âm, và mã currency phải là ba chữ cái A–Z. **Kiểm tra định dạng ba chữ cái không khẳng định đây là mã ISO 4217 hợp lệ**; nếu hệ thống cần tính hợp lệ thật sự, phải bổ sung danh mục/kiểm tra riêng. Chính sách không cho âm cũng là **quy tắc ứng dụng này**, không phải hạn chế bắt buộc của mọi kiểu `Money`.

Dùng `long` đơn vị nhỏ nhất loại bỏ sai số nhị phân từ `double` trong một số bài toán số tiền đơn giản. Với tiền tệ có đơn vị nhỏ nhất khác nhau, quy tắc làm tròn/phần thập phân phức tạp hoặc nghiệp vụ đa tiền tệ, hãy dùng domain type thích hợp và cân nhắc `BigDecimal` cùng chính sách scale rõ ràng.

## 6. Chương trình Java 21 hoàn chỉnh: value object, snapshot và record pattern

Tạo tệp **`ImmutableRecordDomainDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class ImmutableRecordDomainDemo {

    // Value object mang định danh có chuẩn hóa.
    record CustomerId(String value) {
        CustomerId {
            value = Objects.requireNonNull(value, "value").strip();
            if (value.isEmpty()) {
                throw new IllegalArgumentException("CustomerId is blank");
            }
        }
    }

    // Thành phần bất biến của một snapshot đơn hàng.
    record LineItem(String sku, int quantity) {
        LineItem {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("SKU is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
        }
    }

    // Snapshot: không giữ danh sách mutable từ caller.
    record OrderSnapshot(CustomerId customer, List<LineItem> lines) {
        OrderSnapshot {
            customer = Objects.requireNonNull(customer, "customer");
            lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Order must have lines");
            }
        }

        int totalUnits() {
            int total = 0;
            for (LineItem item : lines) {
                total = Math.addExact(total, item.quantity());
            }
            return total;
        }
    }

    // Một giá trị tiền không âm theo chính sách demo.
    record Money(long minorUnits, String currency) {
        Money {
            if (minorUnits < 0) {
                throw new IllegalArgumentException("Negative amount");
            }
            currency = Objects.requireNonNull(currency, "currency")
                .strip()
                .toUpperCase(Locale.ROOT);
            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid currency code");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency())) {
                throw new IllegalArgumentException("Different currencies");
            }
            return new Money(
                Math.addExact(minorUnits, other.minorUnits()),
                currency);
        }
    }

    // Record patterns dùng để chọn nhánh theo hình dạng domain.
    static String describe(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case OrderSnapshot(CustomerId(var id), var lines)
                    when lines.size() >= 2 ->
                "Đơn nhiều dòng: " + id;

            case OrderSnapshot(CustomerId(var id), var lines) ->
                "Đơn một dòng: " + id;

            case Money(var amount, var currency) ->
                "Tiền: " + amount + " " + currency;

            default -> "Loại khác";
        };
    }

    public static void main(String[] args) {
        List<LineItem> source = new ArrayList<>();
        source.add(new LineItem(" BOOK ", 2));

        CustomerId customer = new CustomerId("  C-01  ");
        OrderSnapshot snapshot = new OrderSnapshot(customer, source);

        // Thay đổi collection đầu vào sau khi tạo snapshot.
        source.add(new LineItem("PEN", 3));

        System.out.println("Khách: " + snapshot.customer().value());
        System.out.println("Số dòng snapshot: " + snapshot.lines().size());
        System.out.println("Tổng số món: " + snapshot.totalUnits());

        OrderSnapshot sameValue = new OrderSnapshot(
            new CustomerId("C-01"),
            List.of(new LineItem("BOOK", 2)));
        System.out.println("Equals theo giá trị: "
            + snapshot.equals(sameValue));

        Money total = new Money(1000, " usd ")
            .plus(new Money(250, "USD"));
        System.out.println("Cộng tiền: "
            + total.minorUnits() + " " + total.currency());

        System.out.println(describe(snapshot));
        System.out.println(describe(new OrderSnapshot(
            customer,
            List.of(new LineItem("BOOK", 2),
                    new LineItem("PEN", 3)))));
        System.out.println(describe(total));
        System.out.println(describe(null));

        try {
            snapshot.lines().add(new LineItem("PAD", 1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("Không thể sửa danh sách snapshot");
        }

        try {
            new LineItem(" ", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối dòng không hợp lệ");
        }
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 ImmutableRecordDomainDemo.java
java ImmutableRecordDomainDemo
```

Kết quả mong đợi:

```text
Khách: C-01
Số dòng snapshot: 1
Tổng số món: 2
Equals theo giá trị: true
Cộng tiền: 1250 USD
Đơn một dòng: C-01
Đơn nhiều dòng: C-01
Tiền: 1250 USD
Không có dữ liệu
Không thể sửa danh sách snapshot
Từ chối dòng không hợp lệ
```

### Phân tích các quyết định thiết kế

- `CustomerId("  C-01  ")` chuẩn hóa thành `"C-01"` trong compact constructor; hai `CustomerId` với cùng giá trị chuẩn hóa có equality theo component.
- `LineItem(" BOOK ", 2)` trở thành SKU `"BOOK"`, số lượng phải dương. Mỗi `LineItem` chỉ có `String` và `int`, thích hợp để nằm trong danh sách bất biến.
- `OrderSnapshot` dùng `List.copyOf`. Việc thêm `"PEN"` vào danh sách `source` sau đó **không** thay đổi `snapshot.lines()`, nên số dòng vẫn là `1` và tổng số món là `2`.
- `snapshot.equals(sameValue)` là `true` vì `customer` và `lines` có component equality phù hợp, danh sách so sánh theo thứ tự/phần tử, và `LineItem` cũng so sánh theo các component.
- `Money.plus` kiểm tra cùng loại tiền và dùng `Math.addExact` để ném lỗi nếu cộng số nguyên bị overflow, thay vì âm thầm làm sai kết quả. Hàm tạo một record mới, không thay đổi record cũ.
- `describe` dùng nested record pattern `OrderSnapshot(CustomerId(var id), var lines)`. Biến `id` đã có kiểu `String`, `lines` đã có kiểu `List<LineItem>`, dùng được trong guard `when` và thân nhánh. Hai nhánh OrderSnapshot phải được xếp từ guard cụ thể tới nhánh tổng quát.
- `case null` xử lý selector null; `default` xử lý kiểu khác. Record pattern chỉ khớp khi đối tượng và các record lồng cần thiết không-null.
- Lệnh `snapshot.lines().add(...)` ném `UnsupportedOperationException` vì accessor trả danh sách không cho sửa. Constructor cũng chặn `LineItem` sai invariant.

**Đây là một chương trình minh họa domain snapshot**, không phải hệ thống đơn hàng hoàn chỉnh. Nó chưa có persistence, transaction, đồng bộ cạnh tranh, giảm giá, thuế, điều kiện địa lý hay chính sách hoàn tiền.

## 7. Value semantics, equality và các cạm bẫy

Một record điển hình có `equals`/`hashCode` được sinh từ các component, điều rất hữu ích khi:

- Dùng `CustomerId` làm khóa map hoặc trong một tập giá trị.
- So sánh hai `Point` hoặc hai kết quả tính toán độc lập.
- Phát hiện nội dung snapshot không thay đổi.

Tuy nhiên, **value semantics của record là theo các component**, không tự hiểu danh tính nghiệp vụ:

```java
record CustomerView(String id, String name) {}

CustomerView a = new CustomerView("C-01", "An");
CustomerView b = new CustomerView("C-01", "Anh");

// Không bằng nhau vì name khác,
// dù có thể cùng một customer entity id trong hệ thống.
System.out.println(a.equals(b)); // false
```

Nếu chỉ ID quyết định identity, không nên mặc định dùng toàn bộ component state làm equality cho entity. Có thể giữ domain entity bằng class hoặc viết value-object riêng như `CustomerId`.

### Những trường hợp cần quyết định equality kỹ hơn

1. **Mảng:** equality mặc định của mảng là tham chiếu; cân nhắc wrapper/copy/deep comparison.
2. **Collection:** `List.equals` dùng equality theo phần tử và thứ tự; danh sách có thứ tự khác nhau có thể không bằng nhau. Nếu nghiệp vụ xem các item không có thứ tự, cần mô hình phù hợp.
3. **`BigDecimal`:** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` vì scale khác nhau, dù `compareTo` có thể cho bằng nhau. Nếu dùng `BigDecimal` trong record Money, thiết kế normalization/scale theo chính sách tiền tệ.
4. **Mutable component:** state thay đổi làm hash/equality của record thay đổi theo; nguy hiểm nếu làm khóa `HashMap`.
5. **Normalization:** hai chuỗi khác hình thức có thể được coi là cùng giá trị nếu chuẩn hóa nhất quán trong constructor. Không chuẩn hóa tùy tiện khi business cần giữ phân biệt.

Đừng ghi đè `equals`/`hashCode` để “giấu” một field tuỳ tiện rồi quên giữ hợp đồng equality, hashCode và ý nghĩa của record. Nếu equality theo các component không phản ánh chính xác value của kiểu, hãy đánh giá lại thành phần hoặc lựa chọn `class`.

## 8. Record, entity và snapshot: phân tách trách nhiệm

Trong domain model, có thể cùng lúc có:

- **Entity:** `Order` mang ID, version, trạng thái xử lý, hành vi chuyển trạng thái và invariant theo giao dịch.
- **Value objects:** `Money`, `CustomerId`, `LineItem`, `Address` bất biến theo hợp đồng.
- **Snapshot hoặc DTO:** `OrderSnapshot` lấy trạng thái của entity tại một thời điểm để trả về API, render UI, caching hoặc chuyển giữa các tầng.

Ví dụ kiến trúc khái niệm:

```text
Order (entity / class)
    ├── id: OrderId                 (value object / record)
    ├── total: Money                (value object / record)
    ├── lines: List<LineItem>       (immutable elements)
    └── state transitions: place(), cancel(), fulfill()
                  |
                  | tạo ảnh chụp khi đọc
                  v
OrderSnapshot (record)
    ├── id
    ├── items (unmodifiable snapshot list)
    └── status (value or enum)
```

Nếu một framework ORM yêu cầu constructor không tham số, subclass proxy, setter hoặc cơ chế thay field, một `record` thường không phù hợp để làm entity trực tiếp. Nhưng nhiều hệ thống vẫn dùng record ở **projection/read model**, DTO hoặc query result. Cần kiểm tra hỗ trợ chính thức của framework/phiên bản đang dùng, thay vì giả định tất cả công cụ đều hoạt động giống nhau.

**Record không cấm phương thức hành vi.** Một record có thể chứa các phương thức tính toán và phương thức trả bản sao mới, miễn là thiết kế giữ ý nghĩa value object. Ví dụ `Money.plus` ở chương trình chính là hành vi domain, không phải chỉ một cấu trúc dữ liệu “trơ”.

## 9. Sử dụng record patterns mà không làm mất tính bất biến

Java 21 cho phép kiểm tra và **deconstruct** một record:

```java
if (value instanceof Money(var amount, var currency)) {
    System.out.println(amount + " " + currency);
}
```

Pattern này lấy component ra thành biến. Nó không sửa record. Với nested record pattern:

```java
case OrderSnapshot(CustomerId(var id), var lines)
        when lines.size() >= 2 ->
    "Đơn nhiều dòng: " + id;
```

Trình tự đọc:

1. Selector phải là một `OrderSnapshot` không-null.
2. Component `customer` phải là `CustomerId` không-null vì có `CustomerId(...)`.
3. `var id` nhận `String value` nằm trong CustomerId.
4. `var lines` nhận `List<LineItem>`; guard `when` dùng danh sách đó để kiểm tra số dòng.
5. Khi tất cả pattern khớp và guard đúng, nhánh được chọn.

**Điểm tinh tế:** record pattern không tự làm dữ liệu “an toàn hơn”. Nếu một record có component mutable và accessor trả trực tiếp tham chiếu, `var list` trong pattern cũng có thể nhận cùng tham chiếu mutable. Để có value model tin cậy, tính bất biến phải được bảo vệ ở **thiết kế kiểu và constructor**, không dựa vào việc deconstruction.

Với record bất biến an toàn, pattern matching là cách tự nhiên để truy cập dữ liệu mà không cần cast hay gọi nhiều accessor lồng nhau.

## 10. Khi nào dùng record sẽ gây khó khăn?

### 10.1. Domain cần thay đổi trạng thái tại chỗ

```java
// Record không có setter làm thay đổi component final.
record Counter(int count) {
    Counter next() {
        return new Counter(Math.addExact(count, 1));
    }
}
```

Cách này **hợp lệ** nếu miền bài toán cần các snapshot đếm mới. Nhưng nếu counter phải thay đổi liên tục, đồng bộ nhiều thread, hoặc giữ identity của một đối tượng sống lâu, một class chứa trạng thái có thể phù hợp hơn.

### 10.2. Nhiều component thay đổi cấu trúc theo thời gian

Record mang một hợp đồng dữ liệu rõ. Thêm, xóa, đổi kiểu hoặc đổi thứ tự component là thay đổi API/constructor, pattern deconstruction và equality/toString có thể bị ảnh hưởng. Với public API, phải quản lý backward compatibility và serialization có chủ đích.

Không phải vì record ngắn mà có thể tùy tiện thêm component. Một component mới có thể làm thay đổi ý nghĩa `equals` và lời gọi `new Record(...)` hiện có; những pattern `Record(...)` cũng phải được cập nhật cho số component mới.

### 10.3. Dữ liệu rất lớn hoặc nested mutable graph

Copy phòng vệ toàn bộ mỗi lần tạo record có thể tốn chi phí đáng kể. Nếu graph có chu kỳ, có tài nguyên mở (socket, stream), hay cần lifecycle phức tạp, record không tự giải quyết quản lý tài nguyên. Đánh giá mô hình dữ liệu, ownership và chi phí sao chép trước khi chọn.

### 10.4. Mô hình hoá bằng getter/setter của framework

Một số framework mặc định nhận biết JavaBean bằng `getName()`/`setName()` hoặc cần constructor không tham số. Record dùng accessor tên `name()` và final components. Nếu thư viện chưa hỗ trợ record tốt, hãy dùng DTO adapter/class hoặc cấu hình adapter tương thích, không bẻ cong value object để thỏa một API không phù hợp.

## 11. Những lỗi phổ biến

| Lỗi hoặc hiểu nhầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| “Record luôn immutable sâu” | Final reference không đóng băng List, array hoặc object được tham chiếu | Dùng immutable component, defensive copy, không lộ mutable state |
| “Record không bao giờ cần constructor” | Không có validation mặc định cho null, số âm, chuỗi rỗng | Compact canonical constructor để bảo vệ invariant |
| “`List.copyOf` làm mọi phần tử immutable” | Chỉ tạo danh sách unmodifiable/snapshot, không deep-copy mutable element | Dùng value object phần tử hoặc copy riêng |
| “Có array component thì hai record cùng bytes sẽ `equals`” | Array equality mặc định dựa vào tham chiếu | Thiết kế content equality và defensive copy hoặc thay component |
| Dùng `record Customer(id, name)` rồi so entity bằng mọi field | Entity identity thường khác snapshot/value equality | Phân biệt entity với value object/read model |
| Dùng `record` để thay state mutable liên tục bằng setter | Component final, không có setter generated | Dùng class/state machine hoặc trả record mới có chủ đích |
| Dùng `double` cho số tiền mà không chính sách precision | Floating-point có sai số nhị phân | Chọn đơn vị nhỏ nhất hoặc BigDecimal với quy tắc domain |
| Cộng hai `Money` khác currency | Hai đại lượng khác đơn vị không thể cộng tùy tiện | Kiểm tra currency, quy đổi có tỷ giá/nguồn riêng khi cần |
| Tưởng record patterns tự validate business | Pattern chủ yếu kiểm tra cấu trúc/kiểu và tách dữ liệu | Constructor bảo vệ invariant; guard kiểm tra quy tắc theo ngữ cảnh |
| `case` tổng quát đứng trước `case` có guard | Nhánh cụ thể có thể bị dominance | Đặt nhánh đặc thù trước nhánh bao phủ rộng |
| Không kiểm tra nullable component | Bất biến nông không tự cấm null | `Objects.requireNonNull` và kiểm tra null khi cần |
| Thay đổi component trong record public API tùy ý | Ảnh hưởng constructor, accessors, patterns, equality | Quản lý tương thích và migration có kiểm thử |

## 12. Checklist khi chọn record cho một domain type

Trước khi tạo kiểu mới, hãy trả lời:

1. **Identity:** hai instance có cùng các component thì nên bằng nhau không? Nếu không, có đang mô hình hóa entity thay vì value object?
2. **State:** có cần mutate tại chỗ hay mỗi thay đổi nên cho ra một giá trị mới?
3. **Invariant:** kiểu có thể từ chối null, blank, số âm, currency sai, danh sách rỗng tại constructor không?
4. **Component types:** các component có thật sự immutable không? Có List, Map, Set, array, Date cũ hoặc object có setter không?
5. **Ownership:** nếu nhận collection từ caller, có tạo snapshot copy và không lộ mutable reference qua accessor không?
6. **Equality/hash:** mỗi component có equality đúng với ngữ nghĩa domain không? Có array hoặc BigDecimal scale không?
7. **API constraints:** framework, persistence, serialization và public constructor đang đòi gì?
8. **Readability:** record giúp người đọc thấy state rõ hơn không, hay component quá nhiều và nested pattern quá sâu?
9. **Behavior:** có thể đặt các phương thức thuần và phương thức trả giá trị mới trong record không?
10. **Testing:** đã test equality, hashCode, normalization, defensive copy, null, biên và exception chưa?

Nếu câu trả lời cho identity/value semantics, bất biến và ownership đều rõ, record là lựa chọn mạnh. Nếu phải dùng hàng loạt workaround để giữ mutable lifecycle hoặc bảo toàn danh tính phức tạp, nên xem lại thiết kế.

## 13. Bài tập thực hành

**Bài 1 — Phân loại entity/value object.** Chọn `record` hay `class` cho: `GeoPoint`, `Money`, `OrderId`, `OrderSnapshot`, `OrderEntity` có trạng thái thanh toán cập nhật, và `ConnectionPool`. Giải thích bằng equality, identity, trạng thái và tài nguyên.

**Bài 2 — Sửa lỗi bất biến.** Với `record Tags(List<String> values) {}`, viết compact constructor sao cho caller thay đổi List ban đầu không làm `Tags` thay đổi và accessor không cho thêm phần tử. Gợi ý: dùng `Objects.requireNonNull` và `List.copyOf`.

**Bài 3 — Phần tử mutable.** Đổi component thành `List<MutableAddress>`, trong đó `MutableAddress` có setter. Vì sao `List.copyOf` chưa đủ? Hãy đề xuất immutable `Address` record hoặc copy per element.

**Bài 4 — Equality với array.** Xét hai instance `new UnsafeBytes(new byte[]{1,2})`. Mặc định chúng có bằng nhau không? Đáp án: thông thường **không**, vì hai mảng là hai đối tượng khác nhau. Hãy áp dụng thiết kế `Bytes` ở mục 4 và test equality/hashCode.

**Bài 5 — Domain invariant.** Mở rộng `Money` bằng kiểm tra không chấp nhận currency code trống; thử truyền `"usd"`, `" USD "`, `"ZZ"` và `null`. Chỉ ra khác nhau giữa kiểm tra định dạng `[A-Z]{3}` và kiểm tra một currency có thật.

**Bài 6 — Pattern matching.** Thêm một nhánh `case Money(var amount, var currency) when amount == 0 -> "Miễn phí"` trước case Money tổng quát. Giải thích vì sao thứ tự quan trọng và vì sao record pattern không làm `Money` mutable.

**Bài 7 — Kiểm tra snapshot.** Với chương trình chính, thử thêm một `LineItem` vào danh sách `source` sau khi tạo `OrderSnapshot`, rồi đọc `snapshot.totalUnits()` và `source.size()`. Dự đoán sự khác nhau. Nếu thay `LineItem` bằng một class mutable, bộ test nào cần bổ sung để bảo vệ tính bất biến?

## 14. Tổng kết

**Chọn `record` khi domain type có ý nghĩa như một giá trị được định nghĩa bởi các component, với invariant và khả năng bất biến được thiết kế rõ ràng.** Record giúp giảm boilerplate, cung cấp value equality theo component và kết hợp tự nhiên với record patterns Java 21; nhưng nó **không** tự tạo deep immutability, không tự kiểm tra dữ liệu và không thay thế mọi entity hay stateful service.

Thiết kế record tốt thường đi cùng ba điều: **component phù hợp**, **canonical constructor bảo vệ invariant**, và **không rò rỉ mutable state**. Sau đó mới tận dụng equality và deconstruction để viết code dễ đọc, dễ kiểm thử và an toàn hơn.

### Tài liệu tham khảo

- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 API — List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
