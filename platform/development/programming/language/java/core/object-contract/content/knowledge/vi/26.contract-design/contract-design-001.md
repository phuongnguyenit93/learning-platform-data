# Xác định ý nghĩa bằng nhau trước khi sinh mã (Java)

**Chủ đề: Thiết kế hợp đồng đối tượng.** Trước khi IDE sinh phương thức `equals()` và `hashCode()`, trước khi chọn Lombok hoặc Java `record`, câu hỏi quan trọng là **hai đối tượng khi nào được coi là bằng nhau trong miền nghiệp vụ?** Code được sinh có thể biên dịch chính xác nhưng vẫn phản ánh sai ý nghĩa nếu chọn nhầm field.

## 1. Ba loại equality cần phân biệt

| Khái niệm | Câu hỏi | Java thường thể hiện | Ví dụ |
| --- | --- | --- | --- |
| **Reference identity** | Hai tham chiếu cùng trỏ đến một instance? | `a == b` | Hai biến tham chiếu cùng một đối tượng |
| **Value equality** | Hai instance biểu diễn cùng một giá trị? | `equals()` theo các thành phần của giá trị | Hai tọa độ có cùng x/y |
| **Entity identity** | Hai instance cùng đại diện một thực thể qua thời gian? | `equals()` theo ID ổn định hoặc dùng reference identity theo mô hình | Cùng khách hàng trước/sau khi đổi tên |

Còn **so sánh theo thứ tự hoặc theo một tiêu chí** như giá, ngày tạo, độ gần tương đối thường có API riêng: `Comparator`, `compareTo()` hoặc phương thức chuyên dụng. Không nên tự biến những tiêu chí phụ thành equality mặc định.

Với kiểu tham chiếu, `==` hỏi hai biến có giữ *cùng instance* hay không; `equals()` dùng quy tắc của lớp. Với primitive, `==` so sánh giá trị primitive. Nếu class không override `Object.equals()`, mặc định equality cũng là reference identity.

~~~java
String a = new String("Java");
String b = new String("Java");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Không phải class nào cũng cần override `equals()`. Một request context, controller hoặc resource holder có thể giữ reference identity là hợp lý. Với value object, thường cần so sánh nội dung; với entity, thường cần định danh ổn định theo vòng đời.

## 2. Viết hợp đồng bằng lời trước khi chọn field

Hãy viết một câu có thể đưa vào test:

> Hai `ProductKey` bằng nhau khi cùng `sku` và cùng `market`, với so sánh phân biệt chữ hoa/thường.

> Hai `Customer` bằng nhau khi có cùng `customerId` bất biến, dù tên hiển thị thay đổi.

Sau đó trả lời tuần tự:

1. **Đây là value object, entity hay object so sánh bằng reference?**
2. **Field nào thật sự tham gia equality?** Đừng lẫn định danh với mô tả, timestamp, cache, trạng thái hiển thị hoặc kết quả tính toán.
3. **Field đó có thể đổi không?** Nếu được dùng làm khóa `HashMap` hay phần tử `HashSet`, dữ liệu quyết định equality/hash phải giữ ổn định trong thời gian nằm trong collection.
4. **Có cần chuẩn hóa dữ liệu không?** Hai mã khác chữ hoa/thường, hai số `BigDecimal` khác scale, chuỗi có dấu/whitespace hoặc mã tiền tệ cần quy tắc miền cụ thể.
5. **ID chưa được cấp thì sao?** Hai entity mới cùng `id == null` không đương nhiên là cùng entity.
6. **Có subclass, ORM proxy, collection, mảng hoặc liên kết vòng không?** Chúng ảnh hưởng đến tính đối xứng, tính ổn định, chi phí và đệ quy.
7. **Nhu cầu so sánh có nhiều mục đích không?** Nếu chỉ cần sắp xếp hoặc tìm kiếm theo tiêu chí, dùng comparator/phương thức riêng, tránh ép mọi quy tắc vào `equals()`.

Một bảng quyết định trước khi sinh mã:

| Kiểu | Tham gia equality | Không tham gia | Điều kiện |
| --- | --- | --- | --- |
| `ProductKey` | `sku`, `market` | Không có | Component bất biến |
| `Customer` | `customerId` | `displayName`, `lastViewedAt` | UUID có từ khi tạo và không đổi |
| `Money` | `amount`, `currency` sau chuẩn hóa đã công bố | Biểu diễn văn bản lúc nhập | Giá trị bất biến |
| `RequestContext` | Reference identity | Field trạng thái | Không override `equals()` |

Bảng này là **quyết định cho các lớp minh họa**, không phải quy tắc cho tất cả class trùng tên. Ví dụ email có thể đổi hoặc được tái sử dụng, không tự động là business ID bất biến.

## 3. Luật của `Object.equals()` và `hashCode()`

Hợp đồng `equals()` yêu cầu:

- **Phản xạ:** `x.equals(x) == true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` cùng kết quả.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)`.
- **Nhất quán:** nếu thành phần so sánh không đổi, các lần gọi có cùng kết quả.
- **Với null:** `x.equals(null) == false`.

Hợp đồng băm yêu cầu:

- Nếu `x.equals(y) == true` thì **`x.hashCode() == y.hashCode()`**.
- Nếu các thành phần equality không đổi, hash code phải nhất quán theo hợp đồng.
- Hai hash giống nhau **không** đồng nghĩa hai object bằng nhau; collision là hợp lệ.

Khi override `equals()` thì phải triển khai `hashCode()` phù hợp. Ví dụ hai instance bằng nhau theo email nhưng giữ `Object.hashCode()` mặc định có thể nhận hash khác nhau, khiến `HashSet` phát hiện trùng sai hoặc `HashMap` không tìm được khóa. Không dùng sự trùng hash để kết luận equality.

`Objects.equals(a, b)` xử lý null an toàn; `Objects.hash(field1, field2)` tiện tạo hash. Nhưng tiện ích không thay thế yêu cầu chọn đúng **cùng bộ thành phần** cho equality và hash.

## 4. Ví dụ Java 17 chạy độc lập

Ví dụ có ba hợp đồng riêng:
- `ProductKey` là value object, record so sánh toàn bộ component `sku` và `market`.
- `Customer` là entity có UUID bất biến, thay tên không làm thay đổi định danh.
- `Money` là value object có chính sách chuẩn hóa số tiền và mã tiền tệ được quy định trước.

Lưu vào tệp **`EqualityDesignDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

public class EqualityDesignDemo {

    record ProductKey(String sku, String market) {
        ProductKey {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(market, "market");
        }
    }

    static final class Customer {
        private final UUID customerId;
        private String displayName;

        Customer(UUID customerId, String displayName) {
            this.customerId = Objects.requireNonNull(customerId, "customerId");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        void rename(String newName) {
            displayName = Objects.requireNonNull(newName, "newName");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            return other instanceof Customer that
                    && customerId.equals(that.customerId);
        }

        @Override
        public int hashCode() {
            return customerId.hashCode();
        }
    }

    record Money(BigDecimal amount, String currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
            if (currency.isBlank()) {
                throw new IllegalArgumentException("currency is blank");
            }
            amount = amount.stripTrailingZeros();
            currency = currency.trim().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        ProductKey p1 = new ProductKey("SKU-7", "VN");
        ProductKey p2 = new ProductKey("SKU-7", "VN");
        ProductKey p3 = new ProductKey("SKU-7", "US");

        Set<ProductKey> keys = new HashSet<>();
        keys.add(p1);
        keys.add(p2);
        keys.add(p3);

        System.out.println("ProductKey p1 equals p2: " + p1.equals(p2));
        System.out.println("ProductKey p1 equals p3: " + p1.equals(p3));
        System.out.println("Unique product keys: " + keys.size());

        UUID id1 = UUID.fromString("00000000-0000-0000-0000-000000000001");
        UUID id2 = UUID.fromString("00000000-0000-0000-0000-000000000002");

        Customer a = new Customer(id1, "Minh");
        Customer sameId = new Customer(id1, "Minh Nguyen");
        Customer otherId = new Customer(id2, "Minh");

        System.out.println("Same customer ID: " + a.equals(sameId));
        System.out.println("Different customer ID: " + a.equals(otherId));

        Map<Customer, String> statuses = new HashMap<>();
        statuses.put(a, "active");
        System.out.println("Lookup by same ID: " + statuses.get(sameId));

        a.rename("Minh updated");
        System.out.println("Lookup after rename: " + statuses.get(a));

        Money m1 = new Money(new BigDecimal("1.0"), "usd");
        Money m2 = new Money(new BigDecimal("1.00"), "USD");
        System.out.println("Normalized money equal: " + m1.equals(m2));
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac EqualityDesignDemo.java
java EqualityDesignDemo
~~~

Stdout chính xác:

~~~text
ProductKey p1 equals p2: true
ProductKey p1 equals p3: false
Unique product keys: 2
Same customer ID: true
Different customer ID: false
Lookup by same ID: active
Lookup after rename: active
Normalized money equal: true
~~~

**Giải thích:**

- Record `ProductKey` tạo equality và hash dựa trên cả hai component. `p1` và `p2` là hai instance nhưng cùng giá trị; `HashSet` chỉ lưu một đại diện cho chúng, cộng thêm `p3`.
- `Customer` chỉ so sánh `customerId`. Cùng ID nhưng khác tên vẫn bằng nhau; cùng tên nhưng khác ID thì không. Đổi tên không ảnh hưởng hash của khóa đã nằm trong `HashMap`.
- `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` thường là `false` vì xét cả scale, dù `compareTo() == 0`. Constructor `Money` chủ động chuẩn hóa amount với `stripTrailingZeros()` và currency bằng chữ hoa, nên hai giá trị minh họa bằng nhau. Nếu scale có ý nghĩa với nghiệp vụ, không được áp dụng chuẩn hóa này.

Quy tắc phân biệt hoa/thường của `ProductKey` và việc cấp UUID khi tạo `Customer` là những quyết định **được nêu rõ trước khi code**, không phải giá trị mặc định bắt buộc của Java.

## 5. Sai lầm khi lựa chọn field

### Đưa mọi field của entity vào equality

Nếu `Customer` so sánh cả tên, timestamp cập nhật và trạng thái hiển thị, hai bản thể hiện cùng khách hàng sau một lần đổi tên có thể bị coi khác entity. Đây là lỗi nếu domain đã xác định identity bằng ID.

Ngược lại, với value object tọa độ, bỏ qua trục y sẽ khiến hai giá trị khác nhau bị coi là một. Không có quy tắc “lúc nào cũng chỉ so sánh ID” hoặc “lúc nào cũng chọn tất cả field”.

### Field quyết định hash có thể đổi

Khi thêm một khóa vào `HashSet`, collection chọn vị trí dựa trên hash hiện tại. Sau đó sửa field tham gia `hashCode()`, collection không tự di chuyển phần tử; `contains()` hoặc `remove()` có thể thất bại dù object vẫn đang nằm trong set.

~~~java
// MÃ MINH HỌA; MutableKey cần được định nghĩa riêng.
// Giả sử equals/hashCode dùng trường name có thể sửa.
Set<MutableKey> set = new HashSet<>();
MutableKey key = new MutableKey("before");
set.add(key);
key.setName("after"); // Hash có thể đổi; collection không tự rehash.
~~~

Đoạn này **không phải chương trình độc lập**. Hướng xử lý là dùng khóa bất biến hoặc tách định danh ổn định; khi thực sự phải đổi khóa, quản lý remove/reinsert theo hợp đồng. Không tùy tiện bỏ field khỏi equality để che triệu chứng.

### Entity chưa có ID và ID do database cấp

Đoạn sau **sai với hai entity mới độc lập đều có ID null**:

~~~java
// ĐOẠN CẢNH BÁO — không phải implementation dùng trực tiếp.
return Objects.equals(this.id, other.id);
~~~

Vì `Objects.equals(null, null)` là `true`, hai đối tượng mới có thể bị coi là một. Hơn nữa, khi database gán ID sau khi persist, hash code phụ thuộc ID có thể thay đổi, gây vấn đề cho hash collection.

Cần chốt chính sách cho entity transient, persisted, detached, proxy. Có thể cấp UUID bất biến ngay lúc tạo, dùng reference identity trong giai đoạn transient với hợp đồng nhất quán, hoặc tách value object làm business key. Với JPA/Hibernate, phải thử đúng behavior của proxy/lifecycle, không áp dụng một công thức equality theo ID cho mọi entity.

### Kế thừa làm mất đối xứng

Giả sử `Point` so sánh x/y và chấp nhận `instanceof Point`; `ColorPoint extends Point` thêm màu. Khi đó có thể xảy ra:

~~~text
point.equals(colorPoint) == true
colorPoint.equals(point) == false
~~~

Đây là vi phạm **đối xứng**. Các hướng thiết kế gồm value class `final`/`record`, composition, hoặc hợp đồng equality xuyên subclass được chứng minh nhất quán. `getClass()` chỉ chấp nhận cùng concrete class; `instanceof` chấp nhận subtype nhưng có thể gặp lỗi khi subclass bổ sung field. ORM proxy khiến lựa chọn này cần được thử với framework thật.

### So sánh quan hệ hai chiều một cách máy móc

Nếu một entity tham chiếu entity khác rồi có cạnh quay lại, code tự sinh so sánh đệ quy toàn bộ quan hệ có thể tràn stack, lazy-load nhiều dữ liệu hoặc chạy rất chậm. Hợp đồng entity có thể chỉ xét ID; nếu nghiệp vụ đòi structural equality của đồ thị, cần thuật toán riêng xử lý chu trình và quan hệ tham chiếu dùng chung.

## 6. Khi phép so sánh riêng phù hợp hơn `equals()`

**Comparator:** Hai sản phẩm khác ID có thể cùng giá; comparator theo giá trả `0` dù `equals()` trả `false`. `TreeSet` và `TreeMap` xác định phần tử/khóa trùng nhau bằng kết quả comparator, nên có thể có logic uniqueness khác `HashSet`. Nếu cần nhóm sản phẩm theo giá, nên dùng comparator hay phép nhóm riêng và ghi rõ ý nghĩa.

**So sánh gần đúng:** Với số thực, `Math.abs(a - b) < epsilon` thường không bắc cầu: a gần b, b gần c nhưng a không gần c. Vì thế không dùng tolerance ngẫu nhiên để cài `Object.equals()`. Cung cấp `approximatelyEquals(other, tolerance)` hoặc chính sách lượng tử hóa/canonicalization ổn định khi cần làm khóa.

**Mảng và collection:** `Objects.equals(arrayA, arrayB)` thường so sánh tham chiếu mảng. Record chứa component mảng cũng không tự so sánh nội dung phần tử. Nếu domain yêu cầu theo phần tử, dùng `Arrays.equals()/Arrays.deepEquals()` và `Arrays.hashCode()/Arrays.deepHashCode()` tương ứng, đồng thời kiểm soát khả năng sửa mảng. Record có field final không tự làm các đối tượng bên trong deep-immutable.

**Chuỗi và chuẩn hóa:** `"ABC"` có bằng `"abc"` không là quyết định của domain. Mã, username, email, khoảng trắng, Unicode, locale cần chính sách phù hợp từng trường hợp. Nếu muốn chuẩn hóa chữ hoa/thường cho mã kỹ thuật, nên dùng locale phù hợp như `Locale.ROOT`, không dựa vào locale máy chạy mặc định.

## 7. Chọn công cụ sau khi định nghĩa equality

| Cơ chế | Phù hợp | Kiểm tra bắt buộc |
| --- | --- | --- |
| IDE Generate `equals()`/`hashCode()` | Class thường, đã chốt field | Field, null, kế thừa, array, dữ liệu mutable |
| Lombok `@EqualsAndHashCode` | Giảm mã lặp | Include/exclude, `callSuper`, proxy và kế thừa |
| Java `record` | Value object với component phù hợp | Mặc định **tất cả** component tham gia equality; component có thể trỏ tới mutable object |
| Tự viết | Entity ID, chuẩn hóa hoặc quy tắc riêng | Đồng bộ equals/hash, đối xứng, bắc cầu, vòng đời |
| Không override | Cần reference identity | Đảm bảo người gọi API không kỳ vọng value equality |

Ví dụ `record EmployeeRecord(String id, String name)` mặc định coi cả ID và name là một phần giá trị. Nếu domain định nghĩa “cùng nhân viên ngay cả khi đổi tên”, record này không nhất thiết phù hợp làm entity, dù code tự sinh đúng. Có thể dùng `EmployeeId` làm record value object và class riêng cho entity.

## 8. Kiểm thử từ hợp đồng đã chọn

Sau khi sinh hoặc viết mã, cần kiểm tra:

1. `x.equals(x)`, `x.equals(null)` và các trường hợp giá trị null hợp lệ.
2. Tính đối xứng và bắc cầu trên các bộ đối tượng mẫu.
3. Hai đối tượng bằng nhau có hash code bằng nhau.
4. Value object khác một component có nghĩa phải không bằng nhau.
5. Entity cùng ID khác tên vẫn bằng nhau nếu ID là hợp đồng; khác ID cùng tên thì không.
6. `HashSet` khử trùng đúng và `HashMap` tra cứu được bằng một instance tương đương.
7. Đổi trường được phép đổi không phá tra cứu.
8. Kiểm tra transient/persisted/proxy, BigDecimal scale, Unicode, array hoặc cycle nếu có trong mô hình.
9. Kiểm tra comparator nếu kết quả `0` không nhất thiết đồng nghĩa với equals.

Assertion minh họa (đặt trong mã kiểm thử có hai biến `a`, `b` được chuẩn bị):

~~~java
if (a.equals(b) && a.hashCode() != b.hashCode()) {
    throw new AssertionError("Equal objects must have equal hashes");
}
~~~

Kiểm tra này chỉ bắt một loại vi phạm; vẫn cần test các cặp **không** bằng nhau, đối xứng, bắc cầu và tính ổn định.

## 9. Checklist trước khi nhấn Generate

- [ ] Viết một câu “Hai đối tượng kiểu X bằng nhau khi…” theo nghĩa nghiệp vụ.
- [ ] Xác định value equality, entity identity hay reference identity.
- [ ] Chọn đúng field tham gia; giải thích field loại trừ.
- [ ] Xác định null, ID chưa cấp, chuẩn hóa, mutable field, inheritance/proxy và collection.
- [ ] Giữ các thành phần quyết định equality/hash ổn định khi dùng object làm khóa.
- [ ] Chọn IDE, Lombok, record, viết tay hoặc giữ mặc định đúng nhu cầu.
- [ ] Kiểm thử hợp đồng Object và ứng dụng thực tế trong map/set.

**Nguyên tắc:** `equals()` mô tả **ý nghĩa của sự bằng nhau**; `hashCode()` phải nhất quán với ý nghĩa đó. Chỉ sinh mã sau khi hợp đồng đã được xác định.