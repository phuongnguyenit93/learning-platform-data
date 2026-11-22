# Lộ trình học Java Object Contract với một đối tượng giá trị xuyên suốt

## 1. Mục tiêu và bối cảnh

Trong Java, mọi lớp thông thường đều kế thừa các hành vi nền tảng từ `java.lang.Object`. Khi một lớp biểu diễn **giá trị** (value object), hai instance khác địa chỉ bộ nhớ có thể mang cùng một ý nghĩa nghiệp vụ. Vì vậy, phải xác định rõ khái niệm “bằng nhau”, cách đưa đối tượng vào cấu trúc băm, cách mô tả đối tượng và (nếu cần) cách sắp xếp.

Bài học dùng duy nhất một tình huống xuyên suốt: `OrderKey` là khóa đơn hàng gồm **mã cửa hàng** (`tenant`) và **số đơn hàng** (`number`). Chẳng hạn `new OrderKey(" shop ", 42)` và `new OrderKey("SHOP", 42)` cùng xác định một đơn hàng sau khi chuẩn hóa mã cửa hàng. `OrderKey` là value object: giá trị các trường quyết định danh tính logic của nó; object không đổi sau khi được tạo.

Sau bài này, người học cần có thể:
- Phân biệt `==` (cùng tham chiếu) với `equals` (bằng nhau về giá trị theo hợp đồng của lớp).
- Phát biểu và kiểm tra hợp đồng `equals`/`hashCode`, giải thích tại sao `HashMap` và `HashSet` phụ thuộc vào cả hai.
- Thiết kế `toString` phục vụ quan sát/gỡ lỗi nhưng không nhầm nó với định dạng lưu trữ ổn định.
- Viết `Comparable`/`Comparator` phù hợp với định nghĩa bằng nhau; hiểu rủi ro khi thứ tự tự nhiên không nhất quán với `equals`.
- Giữ value object bất biến, kiểm tra đầu vào, tránh thay đổi khóa sau khi đưa vào collection.

## 2. Lộ trình đề xuất và tiêu chí hoàn thành

| Chặng | Câu hỏi cần trả lời | Thực hành trên `OrderKey` | Dấu hiệu đã hiểu |
|---|---|---|---|
| 0. Nền tảng | Object, tham chiếu, instance, giá trị, bất biến khác nhau thế nào? | Tạo hai instance riêng có cùng dữ liệu | Giải thích được tại sao `a == b` là `false` |
| 1. Equality | Khi nào hai đơn hàng là “cùng khóa”? | Chọn cặp trường `tenant` và `number` cho `equals` | Kiểm tra đủ 5 tính chất của `equals` |
| 2. Hashing | Vì sao lookup bằng đối tượng khác vẫn tìm được? | Ghi đè `hashCode` đồng bộ với `equals` | `HashSet` loại trùng, `HashMap` tra cứu thành công |
| 3. Representation | Log cho biết gì về đối tượng? | Ghi đè `toString` với thông tin rõ ràng | Đọc log mà không cần biết địa chỉ bộ nhớ |
| 4. Ordering | Sắp xếp các khóa theo quy tắc nào? | So sánh `tenant` rồi `number` với `Comparable` | `TreeSet` không làm mất khóa khác nhau |
| 5. Immutability | Khóa thay đổi sau khi hash sẽ ra sao? | Trường `private final`, chuẩn hóa đầu vào, không setter | Giá trị băm không đổi trong suốt vòng đời |
| 6. Tích hợp và kiểm thử | Hợp đồng hoạt động trong collection thật không? | Chạy chương trình cuối bài và bài tập biến thể | Dự đoán, giải thích đúng toàn bộ output |

**Thứ tự thực hành:** bắt đầu bằng hai tham chiếu khác nhau; thêm equality; ngay sau đó thêm hashing; kiểm tra bằng `HashSet`/`HashMap`; cải thiện cách in đối tượng; cuối cùng mới bổ sung natural ordering và kiểm tra `TreeSet`. Không cần học thuộc mọi phương thức của `Object` cùng lúc.

## 3. Các hợp đồng cần nắm

### 3.1. `==` và `equals`

Với hai biến kiểu tham chiếu, `a == b` hỏi chúng có trỏ tới **cùng một object** hay không. `a.equals(b)` hỏi lớp định nghĩa “bằng nhau” như thế nào. `Object.equals` mặc định tương đương so sánh danh tính tham chiếu; một value object thường cần ghi đè.

Hợp đồng `equals` với các tham chiếu khác `null`:
1. **Phản xạ:** `x.equals(x)` luôn `true`.
2. **Đối xứng:** `x.equals(y)` và `y.equals(x)` cho cùng kết quả.
3. **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` đều đúng thì `x.equals(z)` đúng.
4. **Nhất quán:** khi dữ liệu tham gia so sánh không đổi, gọi lại cho cùng kết quả.
5. **Với null:** `x.equals(null)` luôn `false`.

Đối với `OrderKey`, toàn bộ định nghĩa “bằng nhau” là `tenant` chuẩn hóa bằng nhau **và** `number` bằng nhau. Không dùng tên biến, địa chỉ bộ nhớ, `toString` hoặc chỉ một trường để suy đoán sự bằng nhau.

### 3.2. `hashCode`

Nếu `x.equals(y)` là `true` thì **bắt buộc** `x.hashCode() == y.hashCode()`. Chiều ngược lại không đúng: hai object khác nhau vẫn có thể trùng mã băm (collision). Giá trị băm của một object phải nhất quán khi các dữ liệu dùng bởi `equals` không thay đổi.

`HashMap`/`HashSet` dùng mã băm để định hướng tìm bucket và dùng equality để phân biệt khóa/phần tử trong bucket. Ghi đè `equals` mà bỏ `hashCode` khiến hai value object bằng nhau có thể có hash khác nhau, dẫn tới hành vi tìm kiếm/loại trùng sai. Vì thế **luôn ghi đè chúng cùng nhau**, dựa trên cùng bộ thuộc tính. `Objects.hash(tenant, number)` dễ đọc cho ví dụ; code nhạy hiệu năng có thể dùng phép kết hợp hash cụ thể sau khi đo đạc.

### 3.3. `toString`

`toString` của `Object` thường cho chuỗi dạng tên lớp và mã băm dạng hex; đây không phải danh sách thuộc tính nghiệp vụ. Ghi đè `toString` để phục vụ log và debug, ví dụ `OrderKey[tenant=SHOP, number=42]`. Không dùng `toString` làm cơ sở so sánh hay khóa dữ liệu, không coi định dạng này là API serialization. Tránh in thông tin nhạy cảm trong object thực tế.

### 3.4. `Comparable`, `Comparator` và tính nhất quán

`Comparable<T>` đặt **thứ tự tự nhiên** cho một lớp thông qua `compareTo` (âm/0/dương khi nhỏ hơn/bằng về thứ tự/lớn hơn). `Comparator<T>` diễn tả một cách sắp xếp bên ngoài, tiện khi cần nhiều tiêu chí khác nhau.

Với value object dùng trong `TreeSet` hoặc làm khóa `TreeMap`, nên thiết kế:

`a.compareTo(b) == 0` ⇔ `a.equals(b)`.

Các collection có thứ tự dùng kết quả so sánh bằng 0 để xác định phần tử/khóa tương đương theo thứ tự. Nếu quy tắc này không nhất quán với `equals`, `TreeSet` và `HashSet` có thể cho số phần tử khác nhau. Ví dụ quen thuộc: `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` nhưng hai số này có `equals` là `false` vì scale khác nhau. Đây là điểm cần cân nhắc khi chọn value object hoặc comparator.

## 4. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`ObjectContractDemo.java`** với nội dung sau. Chương trình dùng một lớp value object `final` lồng bên trong để có thể biên dịch toàn bộ bằng một tệp. Java 17 hỗ trợ pattern matching với `instanceof` được dùng ở đây.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ObjectContractDemo {
    public static void main(String[] args) {
        OrderKey first = new OrderKey("  shop  ", 42L);
        OrderKey sameValue = new OrderKey("SHOP", 42L);
        OrderKey next = new OrderKey("shop", 43L);

        System.out.println("==: " + (first == sameValue));
        System.out.println("equals: " + first.equals(sameValue));
        System.out.println("hashCode equal: "
                + (first.hashCode() == sameValue.hashCode()));

        Set<OrderKey> unique = new HashSet<>(
                List.of(first, sameValue, next));
        System.out.println("HashSet size: " + unique.size());

        Map<OrderKey, String> status = new HashMap<>();
        status.put(first, "paid");
        System.out.println("HashMap lookup: " + status.get(sameValue));

        Set<OrderKey> sorted = new TreeSet<>(
                List.of(next, sameValue, first));
        System.out.println("TreeSet: " + sorted);
        System.out.println("compareTo == 0: "
                + (first.compareTo(sameValue) == 0));
        System.out.println("toString: " + first);
    }

    public static final class OrderKey implements Comparable<OrderKey> {
        private final String tenant;
        private final long number;

        public OrderKey(String tenant, long number) {
            String normalized = Objects.requireNonNull(tenant, "tenant")
                    .strip()
                    .toUpperCase(Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("tenant is blank");
            }
            if (number <= 0) {
                throw new IllegalArgumentException(
                        "number must be positive");
            }
            this.tenant = normalized;
            this.number = number;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof OrderKey that)) {
                return false;
            }
            return number == that.number && tenant.equals(that.tenant);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenant, number);
        }

        @Override
        public String toString() {
            return "OrderKey[tenant=" + tenant
                    + ", number=" + number + "]";
        }

        @Override
        public int compareTo(OrderKey other) {
            Objects.requireNonNull(other, "other");
            int byTenant = tenant.compareTo(other.tenant);
            return byTenant != 0
                    ? byTenant
                    : Long.compare(number, other.number);
        }
    }
}
```

Chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac --release 17 ObjectContractDemo.java
java ObjectContractDemo
```

Output dự kiến (thứ tự in của `TreeSet` đã được cố định bởi `compareTo`; không phụ thuộc thứ tự của `HashSet`):

```text
==: false
equals: true
hashCode equal: true
HashSet size: 2
HashMap lookup: paid
TreeSet: [OrderKey[tenant=SHOP, number=42], OrderKey[tenant=SHOP, number=43]]
compareTo == 0: true
toString: OrderKey[tenant=SHOP, number=42]
```

Giải thích theo thứ tự:
- `first` và `sameValue` là hai object khác nhau nên `==` trả về `false`. Constructor đã chuẩn hóa khoảng trắng và chữ hoa bằng `Locale.ROOT`, vì vậy `equals` trả về `true`.
- Khi `equals` là `true`, hai object này buộc có cùng `hashCode`; phần tử trùng được `HashSet` gộp, còn `next` với `number=43` là khóa khác. Kết quả tập hợp có 2 phần tử.
- `HashMap` có thể lấy giá trị đã lưu với `first` bằng khóa `sameValue`, minh họa lookup theo giá trị.
- `TreeSet` dùng `compareTo`: so sánh `tenant` trước, `number` sau. Hai object cùng khóa cho `compareTo` bằng 0, nên tập hợp có một khóa 42 và một khóa 43.
- Chuỗi hiển thị do `toString` chủ động quyết định; không dùng output này để thực hiện logic equality.

### Vì sao ví dụ là một value object hợp lệ?

**Bất biến:** Lớp được khai báo `final`, hai trường `private final`, không có setter. `String` là kiểu bất biến, `long` là primitive nên caller không thể thay đổi dữ liệu bên trong qua tham chiếu rò rỉ. Chuẩn hóa và kiểm tra ngay trong constructor ngăn trạng thái không hợp lệ.

**Bình đẳng có ngữ nghĩa:** `equals` dựa trên đúng hai trường quyết định ý nghĩa của khóa. Nhánh `this == other` là tối ưu nhanh; phép `instanceof OrderKey` an toàn ở đây vì lớp `final` không có subclass gây phá đối xứng.

**Hashing phù hợp:** `hashCode` dùng cùng `tenant`, `number`; cả hai bất biến nên hash ổn định sau khi đưa object vào `HashMap`.

**Sắp xếp phù hợp:** `compareTo` xét cả hai trường, cùng thứ tự ý nghĩa với `equals`; dùng `Long.compare` tránh lỗi khi tự trừ hai số `long` rồi ép về `int`.

**Biên đầu vào rõ ràng:** `null` tenant làm phát sinh `NullPointerException` từ `requireNonNull`; chuỗi rỗng sau `strip` và số đơn không dương bị từ chối bằng `IllegalArgumentException`. Quy tắc chuẩn hóa chữ hoa phải phù hợp miền nghiệp vụ thực tế; ví dụ giả định mã cửa hàng không phân biệt hoa/thường.

## 5. Các lỗi thường gặp và cách phát hiện

| Sai lầm | Hậu quả quan sát được | Cách xử lý |
|---|---|---|
| Chỉ ghi đè `equals` | `HashSet`/`HashMap` có thể không nhận ra hai khóa bằng nhau | Ghi đè `hashCode` với cùng các trường |
| `hashCode` tính thêm trường không có trong `equals` | Hai object bằng nhau có thể có hash khác nhau | Dùng cùng nguồn dữ liệu quyết định equality |
| Khóa có setter làm thay đổi trường tham gia hash | Tra cứu có thể thất bại sau khi đưa khóa vào map/set | Dùng value object bất biến; không thay đổi khóa |
| So sánh chuỗi bằng `==` | So sánh tham chiếu thay vì nội dung | Dùng `String.equals` hoặc `Objects.equals` khi có thể null |
| `compareTo` chỉ xét `tenant`, bỏ `number` | Hai đơn khác số có thể bị `TreeSet` gộp thành một | Đưa toàn bộ trường khóa vào quy tắc so sánh |
| Dùng phép trừ trong `compareTo` số nguyên | Có thể overflow và trả sai dấu | Dùng `Integer.compare`/`Long.compare` |
| Tự động sinh `toString` chứa mật khẩu/token | Dữ liệu nhạy cảm có thể lộ trong log | Chỉ đưa trường cần thiết, che thông tin nhạy cảm |
| Dùng lớp có kế thừa tự do rồi thêm trường equality ở subclass | Có nguy cơ phá đối xứng/bắc cầu | Ưu tiên value object `final` hoặc một thiết kế equality nhất quán |
| So sánh `double`/`BigDecimal` mà chưa chọn chính sách chuẩn hóa | Khác biệt về NaN, -0.0, scale hoặc rounding dễ gây bất ngờ | Định nghĩa miền giá trị, chuẩn hóa và kiểm thử các biên |

**Phân biệt hai mục đích:** Băm để tìm phần tử nhanh và thứ tự để sắp xếp là hai hợp đồng riêng. `hashCode` không cần tăng theo thứ tự; `compareTo` không quyết định bucket băm.

## 6. Tự kiểm thử và mở rộng ví dụ

Sau khi chạy chương trình, thực hiện tuần tự các bài tập sau; luôn dự đoán trước kết quả rồi kiểm tra:
1. Tạo `a = new OrderKey("Shop", 42)`, `b = new OrderKey(" SHOP ", 42)` và `c = new OrderKey("SHOP", 43)`. Kiểm tra `a.equals(b)`, `b.equals(a)`, `a.equals(c)`, `a.equals(null)`, `a.equals(a)`.
2. Tạo `d = new OrderKey("shop", 42)`. Kiểm tra chuỗi `a.equals(b)`, `b.equals(d)`, `a.equals(d)` để quan sát tính bắc cầu; thêm kiểm tra hash khi bằng nhau.
3. Tạm bỏ `hashCode` trong một bản thử **riêng** của lớp rồi quan sát `HashSet`/`HashMap`; trả lại code đúng sau thí nghiệm. Đây là cách thấy lỗi hợp đồng, không phải một triển khai được chấp nhận.
4. Trong bản thử riêng, sửa `compareTo` chỉ so `tenant`, giữ nguyên `equals`. So số phần tử của `HashSet` và `TreeSet` khi thêm khóa 42 và 43; giải thích vì sao kết quả khác nhau.
5. Thử `new OrderKey(null, 1)`, `new OrderKey("   ", 1)`, `new OrderKey("shop", 0)`; xác định lỗi được phát ra và lý do.
6. Viết kiểm thử tự động cho identity, 5 tính chất của `equals`, đồng nhất hash, behavior của `HashMap`/`HashSet`/`TreeSet` và thứ tự so sánh. Các kiểm thử chỉ cần các giá trị mẫu cố định; với lớp phức tạp hơn, dùng nhiều mẫu và property-based testing.

Một bộ test tối thiểu (có thể chuyển sang JUnit) nên có:

| Assertion | Kết quả cần đúng |
|---|---|
| `a != b` và `a.equals(b)` | Hai instance khác nhau nhưng cùng giá trị |
| `a.equals(null) == false` | Không bằng null |
| `a.equals(b) == b.equals(a)` | Đối xứng |
| `a.equals(b) && b.equals(d) && a.equals(d)` | Bắc cầu |
| `a.equals(b)` kéo theo `a.hashCode() == b.hashCode()` | Hợp đồng hash |
| `map.put(a, "ok"); map.get(b)` trả `"ok"` | Tra cứu theo giá trị |
| `a.compareTo(b) == 0` và `a.compareTo(c) < 0` | Thứ tự nhất quán |
| `new HashSet<>(List.of(a,b,c)).size() == 2` | Loại trùng đúng |

## 7. Liên hệ các cơ chế khác của Java và hướng học tiếp

- **`record` (Java 16+)** phù hợp với nhiều value object vì compiler tự cung cấp `equals`, `hashCode`, `toString` theo các component; record không tự cung cấp `Comparable`. Nếu cần chuẩn hóa input, hãy dùng compact constructor và kiểm chứng kết quả equality trên giá trị đã chuẩn hóa.
- **`Objects.equals`, `Objects.hash`, `Objects.requireNonNull`** giúp biểu đạt rõ null handling và các hợp đồng, nhưng không tự chọn đúng thuộc tính nghiệp vụ thay cho người thiết kế.
- **`Arrays.equals`/`Arrays.hashCode`** (hoặc phiên bản `deepEquals`/`deepHashCode` cho cấu trúc lồng thích hợp) cần được cân nhắc nếu value object có mảng: `array.equals` mặc định so tham chiếu.
- **`Object.getClass`** giúp kiểm tra lớp runtime; **`clone`** có hợp đồng riêng và thường không cần thiết với value object bất biến. **`finalize`** đã bị loại khỏi hướng thiết kế Java hiện đại (deprecated for removal), không dùng để quản lý tài nguyên. Các phương thức `wait`/`notify` liên quan phối hợp thread, không phải nền tảng của equality.
- Khi tiến tới lớp entity có danh tính vòng đời, collection mutable, ORM hoặc quan hệ kế thừa phức tạp, hãy xác định lại identity/equality theo quy tắc của mô hình đó; không bê nguyên định nghĩa value object sang mọi trường hợp.

**Tiêu chí hoàn thành bài:** có thể tự xây dựng `OrderKey` từ yêu cầu nghiệp vụ, giải thích từng ghi đè, chạy đúng ví dụ và dự đoán được khác biệt giữa `HashSet`, `HashMap`, `TreeSet` khi một hợp đồng bị vi phạm.