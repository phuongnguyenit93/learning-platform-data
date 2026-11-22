# Ưu tiên khóa bất biến trong HashMap và HashSet

## 1. Vì sao nên dùng khóa bất biến?

Với các cấu trúc dựa trên băm như `HashMap`, `HashSet` và `LinkedHashMap`, cách an toàn nhất là dùng **khóa bất biến** (*immutable key*): những dữ liệu quyết định `equals()` và `hashCode()` của khóa không thay đổi trong suốt thời gian khóa nằm trong cấu trúc.

Điểm cốt lõi là khóa được **tra cứu lại** bằng mã băm và tính bằng nhau của nó:

1. Khi đưa khóa `k` vào `HashMap`, bản đồ xác định vị trí lưu trữ từ `k.hashCode()`, sau đó dùng `equals()` để phân biệt các khóa tương ứng khi cần.
2. Nếu thông tin dùng trong `hashCode()` của chính `k` thay đổi sau khi thêm, vị trí đã lưu **không được tự động cập nhật** để khớp với mã băm mới.
3. Lần gọi `map.get(k)`, `map.containsKey(k)`, `map.remove(k)` hoặc tra cứu bằng một khóa khác bằng nhau theo giá trị **có thể không tìm được mục đã lưu**.
4. `HashSet` cũng có nguy cơ tương tự: `add`, `contains` và `remove` phụ thuộc vào ngữ nghĩa băm của phần tử.

Đây là **lý do ưu tiên khóa bất biến**, chứ Java không cấm hoàn toàn khóa có trường thay đổi. Điều bắt buộc đối với một khóa đang nằm trong bảng băm là **những thông tin tham gia so sánh bằng nhau và tính mã băm phải giữ ổn định**. Một đối tượng vẫn có thể có trường thay đổi phục vụ ghi log, số lần truy cập hoặc giao diện nếu các trường đó không tham gia `equals()`/`hashCode()` và không làm thay đổi ý nghĩa khóa.

### Phân biệt hai hợp đồng

- **Hợp đồng giữa `equals()` và `hashCode()`:** nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()`. Các mã băm bằng nhau không bắt buộc dẫn đến `equals()` bằng nhau.
- **Tính ổn định khi khóa đã được lưu:** nếu thuộc tính quyết định sự bằng nhau của khóa bị sửa đổi sau khi đưa vào bảng băm, việc tra cứu có thể sai. Một cặp `equals()`/`hashCode()` dù nhất quán ở từng thời điểm cũng **không đủ** để bảo đảm khóa có thể thay đổi an toàn.

Mã băm không phải địa chỉ bộ nhớ hoặc mã định danh duy nhất. Đối tượng có thể va chạm băm; vấn đề nguy hiểm ở đây là **thay đổi các giá trị liên quan đến băm và bằng nhau sau khi lưu khóa**, không phải bản thân va chạm.

## 2. “Bất biến” có nghĩa gì?

Một khóa *bất biến thực sự* không cho phép quan sát sự thay đổi ở trạng thái dùng để định nghĩa giá trị của nó sau khi tạo. Ví dụ:

- Khóa `String` có nội dung không thay đổi; Java đã cung cấp `equals()` và `hashCode()` nhất quán.
- Một `record` chứa các giá trị `String` hoặc kiểu bất biến khác thường là lựa chọn đơn giản cho khóa nhiều trường.
- Một lớp `final` có các trường `private final`, không có setter và không làm rò rỉ tham chiếu đến dữ liệu có thể sửa thường phù hợp để làm khóa.

**Lưu ý:** `final` chỉ ngăn gán lại biến hoặc trường tham chiếu, không làm đối tượng được tham chiếu bất biến. Ví dụ `private final List<String> parts` vẫn có thể bị thay đổi qua `parts.add(...)` nếu danh sách là loại có thể sửa. Khi đó `List.equals()`/`List.hashCode()` cũng thay đổi theo các phần tử, dẫn đến rủi ro như khóa thông thường bị sửa.

Java `record` giúp thành phần của record là `final` và tự sinh `equals()`/`hashCode()` từ các thành phần, nhưng **chỉ bất biến ở mức nông** (*shallow immutability*). Với thành phần kiểu `List`, `Set`, mảng hay một đối tượng mutable khác, phải cân nhắc sao chép phòng vệ (*defensive copy*) và kiểm soát tham chiếu bị lộ ra ngoài.

### Khi khóa chỉ cần “bất biến về mặt hiệu lực”

Một đối tượng không nhất thiết hoàn toàn bất biến mới có thể làm khóa: nó có thể có trạng thái phụ thay đổi, miễn những thuộc tính tham gia `equals()` và `hashCode()` giữ nguyên khi khóa nằm trong `Map` hoặc `Set`. Tuy nhiên, kiểu bất biến toàn diện thường dễ kiểm tra, dễ chia sẻ và ít rủi ro hơn.

## 3. Ví dụ hoàn chỉnh với Java 17+

Chương trình dưới đây minh họa ba trường hợp: sửa thuộc tính khóa sau khi lưu, dùng `record` có thành phần bất biến, và sao chép danh sách mutable để tạo khóa ổn định.

Tạo tệp **`ImmutableKeyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ImmutableKeyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void changeId(int newId) {
            this.id = newId;
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof MutableKey key && id == key.id);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    record OrderKey(String tenant, String orderNumber) {
        OrderKey {
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(orderNumber);
        }
    }

    record PartsKey(List<String> parts) {
        PartsKey {
            parts = List.copyOf(parts); // Tạo bản sao không cho sửa.
        }
    }

    public static void main(String[] args) {
        Map<MutableKey, String> fragile = new HashMap<>();
        MutableKey mutable = new MutableKey(1);
        fragile.put(mutable, "stored");
        System.out.println("hash before mutation: " + mutable.hashCode());

        mutable.changeId(2);
        System.out.println("hash after mutation: " + mutable.hashCode());
        System.out.println("lookup after mutation: " + fragile.get(mutable));

        mutable.changeId(1);
        System.out.println("lookup after restoring id: "
                + fragile.get(mutable));

        OrderKey first = new OrderKey("shop", "ORD-01");
        OrderKey equivalent = new OrderKey("shop", "ORD-01");

        Map<OrderKey, String> orders = new HashMap<>();
        orders.put(first, "paid");
        System.out.println("record keys equal: "
                + first.equals(equivalent));
        System.out.println("record lookup: " + orders.get(equivalent));

        Set<OrderKey> uniqueOrders = new HashSet<>();
        uniqueOrders.add(first);
        uniqueOrders.add(equivalent);
        System.out.println("record set size: " + uniqueOrders.size());

        List<String> external = new ArrayList<>(List.of("north", "retail"));
        PartsKey safe = new PartsKey(external);
        Map<PartsKey, String> segments = new HashMap<>();
        segments.put(safe, "active");

        external.set(0, "south");
        System.out.println("snapshot contents: " + safe.parts());
        System.out.println("snapshot lookup: "
                + segments.get(new PartsKey(List.of("north", "retail"))));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
~~~

Đầu ra tiêu biểu trên **OpenJDK 17+**:

~~~text
hash before mutation: 1
hash after mutation: 2
lookup after mutation: null
lookup after restoring id: stored
record keys equal: true
record lookup: paid
record set size: 1
snapshot contents: [north, retail]
snapshot lookup: active
~~~

**Giải thích cụ thể:**

1. `MutableKey` dùng `id` để thực hiện cả `equals()` và `hashCode()`. Ban đầu `id = 1`, sau `changeId(2)` mã băm thành `2`. Trong cách triển khai `HashMap` của OpenJDK 17 với bảng mặc định, thao tác tra cứu tìm ở vùng tương ứng với mã băm mới, trong khi khóa được lưu tại vị trí của mã cũ: `get(mutable)` cho `null`.
2. Khi đổi `id` về `1`, mã băm tương ứng với khóa lúc chèn nên lời gọi trong ví dụ lại tìm được `"stored"`. **Đừng sử dụng việc “đổi lại rồi tìm lại” làm giải pháp ứng dụng.** Java API không cam kết mọi biểu hiện chi tiết trong ví dụ đối với mọi cách triển khai bảng băm, và sửa đổi khóa còn có thể gây xung đột ngữ nghĩa với khóa khác.
3. `OrderKey` là record gồm hai chuỗi bất biến. Hai record khác tham chiếu nhưng có cùng `tenant` và `orderNumber` được xem là bằng nhau, có mã băm bằng nhau, nên `HashMap` tra cứu được và `HashSet` chỉ giữ một phần tử logic.
4. `PartsKey` nhận một danh sách từ bên ngoài nhưng dùng `List.copyOf(parts)` trong compact constructor. Sau khi `external` bị sửa, bản chụp trong khóa vẫn giữ `[north, retail]` và tra cứu bằng khóa tương đương vẫn thành công. Các phần tử ở đây là `String` bất biến.

Không nên hiểu rằng mọi lời gọi `get` với khóa bị thay đổi đều **bắt buộc** trả về `null`. Kết quả quan sát phụ thuộc mã băm mới, va chạm và triển khai cấu trúc băm; quy tắc chung là **hành vi tra cứu không còn được bảo đảm** khi dữ liệu liên quan đến so sánh khóa thay đổi.

## 4. Mẫu thiết kế khóa bất biến thông dụng

### Trường hợp 1: record chỉ chứa thành phần bất biến

~~~java
// Đoạn minh họa, không phải một tệp chạy độc lập.
record CustomerKey(String tenantId, long customerNumber) {
    CustomerKey {
        java.util.Objects.requireNonNull(tenantId);
    }
}
~~~

Java tự tạo `equals()` và `hashCode()` theo cả hai thành phần. Một cặp khóa có cùng `tenantId` và `customerNumber` sẽ bằng nhau và có mã băm bằng nhau. Cả `String` và `long` đều không gây nguy cơ bị sửa qua tham chiếu.

### Trường hợp 2: lớp thông thường với `private final`

~~~java
// Đoạn minh họa dùng riêng, không phải chương trình độc lập.
final class CustomerKey {
    private final String tenantId;
    private final long customerNumber;

    CustomerKey(String tenantId, long customerNumber) {
        this.tenantId = java.util.Objects.requireNonNull(tenantId);
        this.customerNumber = customerNumber;
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof CustomerKey key
                    && customerNumber == key.customerNumber
                    && tenantId.equals(key.tenantId));
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(tenantId, customerNumber);
    }
}
~~~

Tính bất biến của những trường tham gia `equals()`/`hashCode()` giúp giá trị băm ổn định. Không cần ghi đè `toString()` để bảo đảm hợp đồng băm; phương thức hiển thị khác với tính bằng nhau.

### Trường hợp 3: khóa chứa collection hoặc mảng

Cần **sao chép phòng vệ khi nhận dữ liệu**, đồng thời không trả ra tham chiếu mutable nội bộ qua getter.

- Với `List<String>`: `List.copyOf(source)` tạo danh sách không cho sửa và bảo toàn thứ tự, đồng thời từ chối `null` trong danh sách và phần tử `null`. Bản thân các `String` đã bất biến.
- Với `Set<String>`: `Set.copyOf(source)` phù hợp nếu thứ tự không tham gia ý nghĩa khóa. Với `Map` có thể dùng `Map.copyOf(source)` khi dữ liệu phù hợp.
- Với mảng `byte[]` hoặc `int[]`: sao chép bằng `array.clone()` ở đầu vào, trả về bản sao từ accessor. Vì `array.equals()` và `array.hashCode()` mặc định so sánh theo danh tính, nếu cần bình đẳng theo nội dung, tự triển khai cặp `Arrays.equals(...)` và `Arrays.hashCode(...)` nhất quán. Với mảng nhiều chiều, cân nhắc `Arrays.deepEquals(...)` và `Arrays.deepHashCode(...)`.
- **Sao chép nông không đủ** nếu phần tử cũng có thể thay đổi. Ví dụ `List<MutableItem>` sao chép bằng `List.copyOf` vẫn chứa các `MutableItem` cũ; sửa trường của phần tử có thể làm thay đổi `List.equals()` và `List.hashCode()`. Hãy chuyển từng phần tử về giá trị bất biến hoặc sao chép sâu phù hợp với mô hình dữ liệu.

Không thay thế việc sao chép phòng vệ bằng mỗi từ khóa `final`: tham chiếu được giữ cố định nhưng nội dung bên trong vẫn có thể thay đổi.

## 5. “Map bất biến” có đồng nghĩa “khóa bất biến” không?

**Không.** Có ba khái niệm riêng:

| Khái niệm | Bảo đảm chính | Điều không được tự động bảo đảm |
| --- | --- | --- |
| Khóa bất biến | Trạng thái xác định tính bằng nhau và mã băm của khóa ổn định | Bản đồ không bị chỉnh sửa |
| `Map.of(...)` hoặc `Map.copyOf(...)` | Không cho thêm, xóa hoặc thay thế mục qua bản đồ trả về | Đối tượng khóa/giá trị bên trong đều bất biến |
| `Collections.unmodifiableMap(map)` | Chặn phép sửa thông qua view trả về | Bản đồ gốc ngừng thay đổi hoặc đối tượng khóa bất biến |

Ví dụ tạo `Map.of(mutableKey, value)` không khiến `mutableKey` trở thành bất biến. Ngay cả bản đồ không cho sửa cấu trúc vẫn có thể gặp vấn đề khi trạng thái xác định `hashCode()`/`equals()` của khóa bị thay đổi từ bên ngoài.

Tương tự, việc đổi **giá trị** `map.put(key, newValue)` trong bản đồ có thể sửa được là bình thường; điều cần ổn định là **khóa**, đặc biệt các thuộc tính dùng để tính băm và so sánh khóa.

## 6. Nếu dữ liệu nghiệp vụ buộc phải thay đổi?

Không phải mọi đối tượng nghiệp vụ đều nên bất biến hoàn toàn. Thường nên tách **danh tính ổn định của khóa** khỏi **trạng thái có thể cập nhật**:

- Dùng mã ổn định như `orderId`, `customerId` hoặc cặp `tenantId` + `entityId` để làm khóa.
- Lưu đối tượng nghiệp vụ có trạng thái thay đổi ở **giá trị** của `Map`, thay vì đưa toàn bộ trạng thái thay đổi vào `hashCode()` của khóa.
- Nếu chính tiêu chí định danh khóa thay đổi (chẳng hạn chuyển mã), dùng thao tác có kiểm soát: xóa mục theo **khóa cũ còn hợp lệ**, tạo khóa bất biến mới rồi chèn lại. Cần xử lý va chạm khóa và tính nguyên tử của thao tác khi ứng dụng yêu cầu.

Ví dụ mô hình:

~~~java
// Đoạn minh họa, cần đặt trong một phương thức có map và dữ liệu phù hợp.
record ProductKey(String sku) {}

Map<ProductKey, String> names = new java.util.HashMap<>();
ProductKey oldKey = new ProductKey("SKU-01");
names.put(oldKey, "Widget");

String name = names.remove(oldKey); // Xóa bằng khóa cũ còn hợp lệ.
names.put(new ProductKey("SKU-02"), name); // Tạo khóa mới bất biến.
~~~

Đối với ứng dụng nhiều luồng, bản thân khóa bất biến **không biến `HashMap` thành thread-safe**. Nếu nhiều luồng cùng chỉnh sửa bản đồ, cần đồng bộ hoặc cấu trúc phù hợp như `ConcurrentHashMap`, bên cạnh việc giữ khóa ổn định.

## 7. Lỗi thường gặp và cách tránh

1. **Sửa trường tham gia `hashCode()` sau khi `put`.** Bảng băm không tự di chuyển mục đã lưu; hãy dùng khóa bất biến hoặc giữ các trường đó ổn định.
2. **Dùng `final List` rồi gọi `add`/`remove`.** `final` chỉ cố định tham chiếu. Dùng bản sao không cho sửa, và bảo đảm phần tử thích hợp.
3. **Tin rằng record luôn bất biến sâu.** Record có thành phần là `List`, mảng hoặc đối tượng mutable vẫn có thể để lộ trạng thái qua accessor; cần defensive copy và ngữ nghĩa `equals()`/`hashCode()` đúng.
4. **Đặt trường ngẫu nhiên hoặc số lần cập nhật trong `hashCode()` nhưng không trong `equals()`.** Hai khóa `equals()` bằng nhau có thể nhận mã băm khác, vi phạm hợp đồng.
5. **Dùng `System.identityHashCode()` để “chữa” khóa thay đổi theo giá trị.** Mã băm danh tính bỏ qua `hashCode()` ghi đè và không tương thích với ngữ nghĩa bình đẳng theo giá trị khi hai thể hiện khác nhau được xem là bằng nhau.
6. **Nghĩ rằng chỉ cần mã băm không đổi là đủ.** Nếu `equals()` thay đổi trong thời gian lưu khóa, khóa vẫn có thể có hành vi tra cứu bất ngờ. Hãy giữ nguyên cả những dữ liệu tham gia định nghĩa bằng nhau.
7. **Tự động sử dụng khóa bất biến để giải quyết đa luồng.** Độ ổn định khóa giúp tránh một nhóm lỗi logic, còn thao tác đồng thời trên map phải được kiểm soát riêng.

### Checklist khi thiết kế và kiểm thử

- Xác định rõ các trường tham gia `equals()` và `hashCode()`.
- Các trường đó có thể thay đổi hoặc bị thay đổi gián tiếp qua tham chiếu không?
- Nếu khóa chứa collection hoặc mảng, constructor và getter đã xử lý defensive copy đúng cách chưa?
- Tạo hai thể hiện khóa cùng dữ liệu: `equals()` trả về `true` và mã băm bằng nhau chứ?
- Khi thêm một khóa rồi tra cứu bằng thể hiện tương đương mới, `HashMap.get` và `HashSet.contains` có đúng không?
- Đã tránh sửa dữ liệu xác định bằng nhau khi khóa đang có mặt trong cấu trúc băm chưa?
- Nếu cần đổi định danh, có quy trình xóa khóa cũ và chèn khóa mới đúng thứ tự không?

## 8. Câu hỏi tự kiểm tra

**Câu 1.** `record Key(List<String> parts) {}` có bảo đảm khóa bất biến chỉ vì `parts` là thành phần của record không?

**Đáp án:** Không. Record bất biến ở mức tham chiếu thành phần; nếu danh sách truyền vào có thể sửa, giá trị băm của record có thể đổi khi nội dung danh sách đổi. Nên sao chép phòng vệ và dùng phần tử bất biến.

**Câu 2.** Lớp có trường `private final String id` và trường `int viewCount` tăng dần. Có thể dùng làm khóa không?

**Đáp án:** Có thể, nếu `equals()` và `hashCode()` chỉ dựa vào `id` và mọi dữ liệu liên quan đến định nghĩa khóa vẫn ổn định. Đó là khóa *bất biến về mặt hiệu lực*, dù đối tượng có trạng thái phụ thay đổi.

**Câu 3.** Nếu một khóa đã bị sửa khiến `map.get(key)` thất bại, gọi `map.put(key, value)` để cập nhật có chắc sửa lỗi không?

**Đáp án:** Không. Lần `put` có thể chèn một mục mới theo mã băm mới, để lại mục cũ khó truy cập và làm hỏng tính nhất quán logic của bản đồ. Thiết kế đúng là tránh sửa khóa khi đang được lưu; nếu cần đổi định danh, xóa bằng khóa cũ hợp lệ và thêm khóa mới.

**Câu 4.** `Map.of(...)` có làm đối tượng khóa mutable trở thành immutable không?

**Đáp án:** Không. `Map.of` bảo vệ cấu trúc bản đồ trả về khỏi bị thay đổi, không đóng băng trạng thái các đối tượng được truyền vào.

**Ghi nhớ:** Hãy **ưu tiên khóa bất biến**, đặc biệt trong `HashMap` và `HashSet`. Điều cần bảo vệ là tính ổn định của các dữ liệu dùng trong `equals()` và `hashCode()` từ lúc thêm khóa đến lúc xóa. Với trạng thái mutable trong khóa, phải chủ động sao chép phòng vệ và ngăn các tham chiếu bên ngoài thay đổi ý nghĩa khóa.
