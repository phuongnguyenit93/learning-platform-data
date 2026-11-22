# Loại bỏ rồi thêm lại dữ liệu khi nghiệp vụ thật sự cần đổi khóa

Một đối tượng Java đôi khi được dùng làm **phần tử của `HashSet`** hoặc **khóa của `HashMap`**. Nếu `equals()` và `hashCode()` dựa trên một thuộc tính nghiệp vụ như `customerId`, việc thay đổi thuộc tính này **khi đối tượng còn nằm trong collection** có thể làm mất khả năng tra cứu, xóa hoặc ngăn trùng lặp đúng cách.

Khi yêu cầu nghiệp vụ thực sự cần đổi khóa, trình tự an toàn ở cấp collection là:

1. Xác định và kiểm tra **khóa cũ** khi collection vẫn đang hoạt động bình thường.
2. Kiểm tra khóa mới hợp lệ và không va chạm với khóa đang tồn tại.
3. **Loại bỏ phần tử hoặc entry bằng khóa cũ**, trước khi thay đổi dữ liệu có ảnh hưởng tới `equals()`/`hashCode()`.
4. Thay đổi khóa trên đối tượng đã tháo ra, hoặc tạo đối tượng khóa mới.
5. **Thêm lại** bằng khóa mới và xác nhận tra cứu theo khóa mới hoạt động.

Đây là cách xử lý có điều kiện khi **thực sự phải đổi khóa**. Trong thiết kế thông thường, ưu tiên một định danh ổn định, bất biến; nếu nghiệp vụ chỉ đổi tên hiển thị hoặc trạng thái, không cần và không nên động tới khóa dùng cho `equals()`/`hashCode()`.

## 1. Vì sao không được thay đổi khóa ngay trong collection?

Với `HashSet` và `HashMap`, Java dựa trên `hashCode()` để xác định vùng lưu/tra cứu, rồi dùng `equals()` để nhận biết hai phần tử hoặc khóa bằng nhau. Giả sử:

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return customerId.equals(other.customerId);
}

@Override
public int hashCode() {
    return customerId.hashCode();
}
~~~

Đây là **mảnh mã nằm trong lớp `Customer`**, không phải chương trình độc lập. Hai phương thức đều dựa trên `customerId`.

Khi thêm một `Customer("C-01")` vào `HashSet`, cấu trúc sẽ dùng hash ứng với `"C-01"`. Nếu sau đó đổi chính đối tượng ấy thành `"C-02"` ngay trong set, hash được tính khi tra cứu có thể khác hash dùng lúc chèn. Collection không tự động tái định vị phần tử mỗi khi trường của object thay đổi. Vì vậy, `contains` hoặc `remove` có thể không tìm thấy phần tử, và các quy tắc không trùng lặp có thể bị phá.

Ví dụ thao tác **sai về thứ tự**:

~~~java
// Đoạn minh họa; giả định customer đã nằm trong customers.
customer.changeId("C-02"); // SAI: sửa khóa trong khi còn ở HashSet.
customers.remove(customer); // Có thể không tìm thấy bằng hash mới.
~~~

Lệnh `remove` sau khi thay đổi không được đảm bảo sẽ sửa được tình huống này. Ngay cả nếu một bộ giá trị tình cờ vẫn tra cứu thành công, code vẫn phụ thuộc hành vi không bảo đảm của collection.

**Thứ tự đúng:**

~~~java
// Đoạn minh họa; thực tế cần kiểm tra điều kiện trước đó.
boolean removed = customers.remove(customer); // Khi ID vẫn là "C-01".
if (!removed) {
    throw new IllegalStateException("Old key not found");
}
customer.changeId("C-02");                     // Giờ mới đổi khóa.
customers.add(customer);                       // Hash lại theo khóa mới.
~~~

Với `HashSet`, `remove` phải xảy ra **trước** khi sửa một trường ảnh hưởng tới quan hệ bằng nhau. Với `HashMap`, ta dùng `remove(oldKey)` rồi `put(newKey, value)`. Hai thao tác này không tự tạo ra một giao dịch nguyên tử; xử lý cạnh tranh và lỗi giữa chừng được bàn ở phần sau.

## 2. Phân biệt đổi khóa với sửa thuộc tính bình thường

Không phải mọi thay đổi trạng thái của đối tượng đều nguy hiểm.

| Dữ liệu đổi | Tham gia `equals()`/`hashCode()`? | Tác động khi object ở trong collection |
| --- | --- | --- |
| `customerId` là khóa bằng nhau | Có | Phải xử lý chuyển khóa an toàn hoặc thiết kế khóa bất biến |
| `displayName` chỉ để hiển thị | Không | Có thể sửa mà không cần tháo khỏi hash collection vì hash và quan hệ bằng nhau không đổi |
| `status` bị loại khỏi phép bằng nhau | Không | Có thể cập nhật như dữ liệu thường; cần xét đồng bộ nếu đa luồng |
| Nội dung một trường mảng hoặc đối tượng lồng nhau dùng trong mã băm | Có | Cũng là đổi khóa logic dù tham chiếu trường không đổi |
| `hashCode()` dựa vào trường mà `equals()` bỏ qua | Thiết kế sai | Phải sửa hợp đồng `equals()`/`hashCode()` trước; remove/add không chữa được sự không nhất quán này |

Một thuộc tính được khai báo `final` cũng **chưa đủ** bảo đảm bất biến sâu nếu nó trỏ tới đối tượng mutable (ví dụ mảng hay collection). Điều quan trọng là **giá trị tham gia bằng nhau và băm không đổi** trong khoảng thời gian đối tượng làm khóa.

Nếu khóa được tạo từ giá trị chuẩn hóa (ví dụ mã viết hoa được chuẩn hóa trước khi lưu), hãy xác định **giá trị chuẩn hóa** nào thay đổi; đừng dựa vào thay đổi bề ngoài không ảnh hưởng khóa.

## 3. Ví dụ Java 17 hoàn chỉnh: chuyển khóa an toàn trong `HashSet` và `HashMap`

Tạo tệp **`KeyChangeDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class KeyChangeDemo {

    // Ví dụ có chủ đích cho phép sửa ID; trong thiết kế thực tế,
    // ID bất biến thường dễ quản lý hơn.
    static final class Customer {
        private String id;
        private final String displayName;

        Customer(String id, String displayName) {
            this.id = Objects.requireNonNull(id, "id");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        void changeId(String newId) {
            id = Objects.requireNonNull(newId, "newId");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Customer other)) {
                return false;
            }
            return id.equals(other.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    // Một record Java 17: khóa String được lưu bất biến.
    record AccountKey(String id) {
        AccountKey {
            Objects.requireNonNull(id, "id");
        }
    }

    static void changeCustomerId(
            Set<Customer> customers, Customer target, String newId) {
        Objects.requireNonNull(newId, "newId");

        // Tiền điều kiện: collection hiện đang hợp lệ.
        if (!customers.contains(target)) {
            throw new IllegalArgumentException("Customer not found");
        }
        if (target.id.equals(newId)) {
            return;
        }

        // Kiểm tra va chạm với ID mới trước khi xóa ID cũ.
        if (customers.contains(new Customer(newId, "probe"))) {
            throw new IllegalArgumentException("New customer ID exists");
        }

        if (!customers.remove(target)) {
            throw new IllegalStateException("Cannot remove old ID");
        }
        target.changeId(newId);
        if (!customers.add(target)) {
            throw new IllegalStateException("Cannot add new ID");
        }
    }

    static <V> void moveMapKey(
            Map<AccountKey, V> map, AccountKey oldKey, AccountKey newKey) {
        Objects.requireNonNull(oldKey, "oldKey");
        Objects.requireNonNull(newKey, "newKey");

        if (oldKey.equals(newKey)) {
            return;
        }
        if (!map.containsKey(oldKey)) {
            throw new IllegalArgumentException("Old map key missing");
        }
        if (map.containsKey(newKey)) {
            throw new IllegalArgumentException("New map key exists");
        }

        // Chuyển cả mapping, kể cả khi giá trị được lưu là null.
        V value = map.remove(oldKey);
        map.put(newKey, value);
    }

    public static void main(String[] args) {
        Set<Customer> customers = new HashSet<>();
        Customer lan = new Customer("C-01", "Lan");
        customers.add(lan);
        customers.add(new Customer("C-03", "Binh"));

        System.out.println("before old: "
                + customers.contains(new Customer("C-01", "check")));

        changeCustomerId(customers, lan, "C-02");

        System.out.println("after old: "
                + customers.contains(new Customer("C-01", "check")));
        System.out.println("after new: "
                + customers.contains(new Customer("C-02", "check")));
        System.out.println("set size: " + customers.size());

        try {
            changeCustomerId(customers, lan, "C-03");
        } catch (IllegalArgumentException ex) {
            System.out.println("collision blocked");
        }
        System.out.println("after rejected: "
                + customers.contains(new Customer("C-02", "check")));

        Map<AccountKey, String> statuses = new HashMap<>();
        statuses.put(new AccountKey("A-10"), "OPEN");
        moveMapKey(
                statuses, new AccountKey("A-10"), new AccountKey("A-20"));

        System.out.println("map old key: "
                + statuses.containsKey(new AccountKey("A-10")));
        System.out.println("map new value: "
                + statuses.get(new AccountKey("A-20")));
        System.out.println("map entries: " + statuses.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac KeyChangeDemo.java
java KeyChangeDemo
~~~

**Đầu ra dự kiến trên Java 17+:**

~~~text
before old: true
after old: false
after new: true
set size: 2
collision blocked
after rejected: true
map old key: false
map new value: OPEN
map entries: 1
~~~

Giải thích từng phần:

- Trước thay đổi, `Customer("C-01")` có thể được tìm bằng một bản thể hiện khác cùng ID.
- `changeCustomerId` xác minh ID mới `"C-02"` chưa tồn tại, **xóa `lan` khi `lan.id` vẫn là `"C-01"`**, sau đó mới đổi `id` và thêm lại. Bởi vậy, tra cứu ID cũ là `false` và ID mới là `true`.
- Set vẫn có hai khách hàng (`"C-02"` và `"C-03"`). Lần thử đổi sang `"C-03"` bị từ chối trước khi xóa hay sửa, nên `lan` vẫn ở `"C-02"`.
- Với `Map`, `AccountKey` là record chứa `String` không đổi. Thay vì sửa khóa đang lưu, ta xóa mapping `"A-10"`, giữ giá trị `"OPEN"` rồi thêm mapping `"A-20"`. Entry cũ biến mất; entry mới chứa cùng giá trị, và kích thước map giữ nguyên.
- `moveMapKey` dùng `containsKey` để phân biệt **không có mapping** với **mapping có value `null`**; chỉ nhìn `remove(...) == null` là không đủ cho trường hợp này.

**Phạm vi của ví dụ:** code chạy đơn luồng, trên `HashSet`/`HashMap` thông thường với dữ liệu hợp lệ; nó minh họa **trình tự của collection trong bộ nhớ**, chưa phải thao tác giao dịch có khôi phục khi lỗi hoặc có nhiều tác nhân cập nhật đồng thời.

## 4. Những tiền điều kiện cần kiểm tra trước khi chuyển khóa

Một thao tác đổi khóa tốt thường cần kiểm tra đầy đủ trước khi tháo entry cũ:

1. **Khóa cũ tồn tại:** phần tử/entry phải đang ở trong collection với `equals()`/`hashCode()` nhất quán. Nếu cấu trúc đã hỏng bởi việc sửa khóa trước đó, `contains` và `remove` không phải cơ chế sửa chữa đáng tin cậy.
2. **Khóa mới hợp lệ:** kiểm tra định dạng, độ dài, quy tắc chuẩn hóa và ràng buộc nghiệp vụ trước khi xóa dữ liệu cũ. Không để một validation ném lỗi sau khi đã tháo phần tử.
3. **Khóa mới chưa bị chiếm:** `Set.add(...)` có thể trả `false` vì trùng; `Map.put(...)` có thể ghi đè giá trị cũ. Không nên âm thầm coi những tình huống ấy là cập nhật thành công.
4. **Không đổi nghĩa phép bằng nhau giữa chừng:** quy tắc `equals()`, `hashCode()` và cách biểu diễn khóa phải thống nhất. Khóa khác dưới dạng chuỗi nhưng bằng nhau sau chuẩn hóa vẫn là một xung đột logic.
5. **Phần tử có đang bị tham chiếu ở nơi khác?** Nếu cùng object làm khóa ở nhiều `HashSet`/`HashMap`, việc tháo khỏi một nơi rồi sửa ID có thể làm hỏng **những nơi còn lại**. Cần thay khóa ở mọi cấu trúc có liên quan hoặc ưu tiên tạo khóa bất biến mới.

Trường hợp `newKey.equals(oldKey)`, phương thức chuyển khóa có thể **không làm gì** vì danh tính logic không đổi. Chỉ khi chính khóa theo định nghĩa bằng nhau thay đổi mới cần quy trình chuyển khóa.

## 5. Ba chiến lược và lúc nên dùng

### Chiến lược A — Ưu tiên: khóa bất biến, tạo khóa mới

Đặt một `String`, `UUID`, `record` hoặc giá trị bất biến khác làm khóa `Map`; nếu nghiệp vụ đổi mã thì tạo key mới và chuyển entry. Với `Set` lưu object giá trị bất biến, có thể xóa object theo khóa cũ rồi thêm object mới.

Ưu điểm: không có đối tượng khóa nào bị sửa lén trong khi các collection khác đang sử dụng nó; rõ ràng hơn với việc truyền dữ liệu qua các lớp hoặc luồng xử lý.

Ví dụ với `Map`:

~~~java
// Giả sử oldKey, newKey là các khóa bất biến đã kiểm tra.
// Phải kiểm tra tồn tại và xung đột theo quy tắc nghiệp vụ.
V saved = map.remove(oldKey);
map.put(newKey, saved);
~~~

Đây là **mã giả ở mức phương thức generic**, không phải một chương trình Java độc lập; xem `moveMapKey` ở ví dụ chạy được để thấy đầy đủ kiểm tra đầu vào và không làm mất mapping chứa `null`.

### Chiến lược B — Đối tượng mutable trong `HashSet`, bắt buộc remove → mutate → add

Nếu thiết kế cũ cho phép thay ID trên một object đã được chia sẻ tham chiếu, hãy giữ đúng thứ tự **xóa khi còn ID cũ → sửa ID → thêm lại**. Cần kiểm soát nơi nào khác cũng giữ object đó làm key. Việc thay đổi khóa bên trong một object mutable tiềm ẩn rủi ro lớn hơn tạo object/key mới và nên được cô lập trong phương thức nghiệp vụ duy nhất.

### Chiến lược C — Không đổi khóa collection nếu chỉ đổi thông tin hiển thị

Nếu `customerId` là định danh không thay đổi, còn tên, email liên hệ hoặc trạng thái giao diện được cập nhật độc lập, giữ nguyên khóa. Khi đó không cần remove/add chỉ vì giá trị không tham gia bằng nhau thay đổi; việc thao tác thừa còn làm tăng nguy cơ mất phần tử do lỗi giữa chừng.

**Lưu ý:** `Map` phân biệt *khóa* (`key`) và *giá trị* (`value`). Sửa thuộc tính của value thường không đổi cách tra cứu map miễn thuộc tính ấy không phải một phần của key và không có chỉ mục phụ dựa trên nó.

## 6. Vì sao remove/add chưa tự động bảo đảm tính nguyên tử?

Trong một `HashMap` thông thường, chuỗi `remove(oldKey)` rồi `put(newKey, value)` có khoảng thời gian mapping chưa hiện diện dưới khóa nào. Với `HashSet` có object mutable, trình tự remove → mutate → add cũng có giai đoạn phần tử tạm thời bị tháo khỏi set. Nếu thao tác bị lỗi hoặc có luồng khác đọc giữa chừng, chương trình có thể quan sát trạng thái không đầy đủ.

Các vấn đề cần xử lý ở **cấp nghiệp vụ**:

- **Đồng thời:** `HashMap` và `HashSet` không tự thread-safe. Hai lời gọi đổi khóa cùng lúc có thể vượt qua kiểm tra va chạm rồi ghi đè nhau. Nếu có truy cập cạnh tranh, cần một cơ chế đồng bộ bảo vệ **toàn bộ bước kiểm tra + chuyển khóa**, hoặc cấu trúc/thiết kế khác với ngữ nghĩa cập nhật nguyên tử rõ ràng. Chỉ thay collection bằng `ConcurrentHashMap` không biến chuỗi `remove` rồi `put` độc lập thành một giao dịch nguyên tử.
- **Lỗi ở giữa:** kiểm tra trước tất cả điều kiện có thể kiểm tra giúp giảm rủi ro; với quy trình thực tế có I/O, callback hoặc ràng buộc khác, cần cơ chế rollback hoặc thay thế nguyên tử được thiết kế rõ ràng. Mã ví dụ không cố tuyên bố xử lý được mọi ngoại lệ sau khi remove.
- **Cơ sở dữ liệu:** nếu mã nghiệp vụ còn là khóa duy nhất trong database, cập nhật ở bộ nhớ phải phối hợp với transaction, unique constraint và mọi tham chiếu liên quan. Remove/add trong Java không tự cập nhật foreign key, chỉ mục hay dữ liệu của phiên làm việc khác.
- **Khóa được dùng ở nhiều nơi:** trong hệ thống có cache, index hoặc những collection khác, chuyển khóa cần cập nhật từng nơi theo chính sách nhất quán; không thể chỉ sửa một `HashSet` rồi coi toàn hệ thống đã hoàn tất.

Với `TreeSet` hoặc `TreeMap`, việc sửa trường tham gia `Comparator`/`compareTo` cũng có thể làm hỏng thứ tự cây, dù `hashCode()` không được sử dụng. Ý tưởng tháo khi còn khóa cũ, thay khóa, thêm lại vẫn có ích; nhưng phải kiểm tra quy tắc sắp thứ tự và định nghĩa trùng khóa theo comparator.

## 7. Nếu khóa đã bị thay đổi khi object còn ở trong set/map?

Sau khi lỡ đổi thuộc tính ảnh hưởng đến `equals()`/`hashCode()`, **không dựa vào `contains(mutableKey)` hoặc `remove(mutableKey)` để khôi phục**, vì chính đường tra cứu theo hash có thể đã sai.

Trong một cấu trúc in-memory mà bạn kiểm soát độc quyền, có thể tìm đúng phần tử qua iteration rồi gọi `Iterator.remove()` để tháo nó; sau đó mới tái lập dữ liệu với khóa hợp lệ. Ví dụ khôi phục một instance cụ thể:

~~~java
// Minh họa; chỉ dùng khi kiểm soát độc quyền Set,
// đồng thời biết chính xác tham chiếu object cần tháo.
var iterator = customers.iterator();
while (iterator.hasNext()) {
    if (iterator.next() == target) {
        iterator.remove();
        break;
    }
}
// Kiểm tra hậu điều kiện, giải quyết xung đột nếu có,
// rồi mới thêm target bằng trạng thái khóa đã xác thực.
~~~

`Iterator.remove()` loại bỏ **phần tử vừa được iterator trả về**, không dựa trên việc tìm lại object theo hash mới. Nhưng đây là **biện pháp sửa chữa tình huống hỏng**, không phải luồng bình thường; phải tránh sửa collection đồng thời khi đang duyệt, xác nhận object thực sự được tìm thấy và xử lý những chỉ mục khác có thể đã bị hỏng. Một cách rõ ràng hơn trong nhiều trường hợp là **tái xây dựng collection từ dữ liệu nguồn đáng tin**, theo bộ khóa đã được xác thực.

Với `Map`, có thể cân nhắc duyệt `entrySet().iterator()` và remove đúng entry trong tình huống tương tự, hoặc xây lại map. Tránh áp dụng một thủ thuật recovery nếu hệ thống có nhiều nơi giữ khóa cùng object mà chưa biết trạng thái của chúng.

## 8. Checklist thực hành

Trước khi cho phép đổi một khóa nghiệp vụ, tự kiểm tra:

- [ ] Thuộc tính định đổi có thực sự tham gia `equals()`/`hashCode()` hoặc comparator không?
- [ ] Nếu chỉ là thông tin hiển thị, có thể cập nhật bình thường mà không thay khóa không?
- [ ] Có thể thiết kế khóa bất biến và thay bằng instance mới thay vì sửa object đang được dùng làm key không?
- [ ] Đã xác nhận khóa cũ tồn tại, khóa mới hợp lệ, chưa bị chiếm và tuân thủ cùng quy tắc chuẩn hóa chưa?
- [ ] Mọi `remove` có diễn ra **khi khóa cũ vẫn còn nguyên** không?
- [ ] Sau thay đổi, đã kiểm tra `contains/get` theo khóa cũ và khóa mới, số phần tử/entry, và xung đột bị từ chối chưa?
- [ ] Có nơi khác giữ object làm key, có truy cập đồng thời hoặc có database cần transaction không?
- [ ] Nếu một bước thất bại, có phương án đảm bảo không mất mapping/không để object ở trạng thái nửa cập nhật không?

**Ghi nhớ:** Khi một object đang tham gia cấu trúc dựa trên `hashCode()` hoặc phép sắp thứ tự, đổi trường quyết định khóa có thể khiến collection không còn tìm đúng phần tử. Nếu nghiệp vụ thực sự yêu cầu đổi khóa, hãy **xóa theo khóa cũ trước, chuyển sang khóa mới sau, rồi thêm lại và xác minh**. Ưu tiên các khóa bất biến và xử lý tính nguyên tử ở cấp thích hợp khi bài toán không còn đơn luồng.