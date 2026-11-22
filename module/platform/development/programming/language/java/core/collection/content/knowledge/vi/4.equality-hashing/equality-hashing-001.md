# Vai trò của equals và hashCode trong tìm kiếm và loại trùng

Collection không tự biết “hai khách hàng là cùng một người” hay “hai sản phẩm là cùng một mặt hàng”. Nó cần một quy tắc để quyết định hai đối tượng có được xem là bằng nhau hay không.

Trong Java, `equals` mô tả quan hệ bằng nhau theo giá trị của đối tượng. `hashCode` cung cấp mã băm để những cấu trúc như `HashSet` và `HashMap` tổ chức việc lưu và tìm hiệu quả hơn.

Hai phương thức phối hợp nhưng không thay thế nhau:

- `equals` trả lời **hai giá trị có được coi là bằng nhau không**.
- `hashCode` hỗ trợ **tìm nhóm ứng viên có thể phù hợp**.
- Cùng mã băm không có nghĩa là bằng nhau.
- Nếu bằng nhau theo `equals`, chúng bắt buộc phải có cùng mã băm.

Bài này giải thích các quy tắc qua tìm kiếm trong danh sách, loại trùng trong tập và tra cứu theo khóa trong map. Ví dụ sử dụng Java 17 trở lên.

## 1. Phân biệt cùng đối tượng với cùng giá trị

### 1.1. Toán tử == trên tham chiếu

Với hai tham chiếu đối tượng, `a == b` kiểm tra chúng có cùng trỏ đến một đối tượng hay không.

```java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
```

Hai chuỗi được tạo riêng nhưng có cùng nội dung. `String` đã định nghĩa `equals` theo nội dung nên kết quả khác với `==`.

Không dùng kết quả tình cờ của string pool để suy ra `==` là phép so nội dung chuỗi. Collection cũng không thay `equals` bằng `==` chỉ vì hai phần tử có cùng kiểu.

### 1.2. Lớp tự viết không tự có bình đẳng theo mọi trường

Nếu một lớp chỉ có trường `id` nhưng không ghi đè `equals`, hai đối tượng khác nhau có cùng `id` vẫn dùng quy tắc mặc định từ `Object`: bằng nhau khi cùng đối tượng.

Ví dụ minh họa:

```java
final class PlainKey {
    private final String id;

    PlainKey(String id) {
        this.id = id;
    }
}
```

Với hai lần `new PlainKey("C7")`, nội dung trường giống nhau không tự tạo bình đẳng giá trị. Nếu đưa cả hai vào `HashSet`, tập có thể giữ cả hai vì chúng không bằng nhau theo quy tắc của lớp.

Trước khi chọn cấu trúc loại trùng, phải xác định **loại trùng theo điều gì**: toàn bộ giá trị, mã ổn định, cặp mã tổ chức–mã khách hàng hay một tiêu chí khác. Đây là một quyết định mô hình dữ liệu.

## 2. Hợp đồng phải giữ giữa equals và hashCode

### 2.1. Equals phải là một quan hệ nhất quán

Với các tham chiếu không `null`, những tính chất cần giữ gồm:

| Tính chất | Yêu cầu |
| --- | --- |
| Phản xạ | `x.equals(x)` đúng |
| Đối xứng | `x.equals(y)` và `y.equals(x)` đồng ý |
| Bắc cầu | Nếu x bằng y và y bằng z thì x bằng z |
| Nhất quán | Không đổi kết quả khi dữ liệu tham gia so sánh không đổi |
| So với null | `x.equals(null)` sai |

Nếu đối xứng hoặc bắc cầu bị phá, việc tìm hoặc loại trùng có thể phụ thuộc cách truy vấn được thực hiện. Không thiết kế `equals` như một phép “gần giống” tùy tình huống nếu quan hệ ấy không đáp ứng các tính chất trên.

### 2.2. HashCode phải phù hợp với bình đẳng

Quy tắc quan trọng nhất:

```text
a.equals(b) == true
        ⇒
a.hashCode() == b.hashCode()
```

Chiều ngược lại không đúng. Hai đối tượng không bằng nhau vẫn có thể có cùng mã băm.

Mã băm phải nhất quán trong một lần chạy khi thông tin dùng cho bình đẳng không đổi. Hợp đồng chung không buộc mã băm của mọi loại đối tượng phải giống nhau giữa các lần khởi động ứng dụng.

Vì vậy, khi ghi đè `equals`, thông thường phải ghi đè `hashCode` tương ứng. Không dùng mã băm như một mã định danh duy nhất, địa chỉ bộ nhớ hoặc dấu vân tay bảo mật. Nó chỉ là một số `int` phục vụ hợp đồng băm. [Java 17: hợp đồng Object.equals và hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)

## 3. Collection dùng bình đẳng ở đâu?

| Cấu trúc / thao tác | Vai trò của bình đẳng và băm |
| --- | --- |
| `List.contains`, `indexOf`, `remove(value)` | Tìm phần tử theo quan hệ bằng nhau được API quy định |
| `HashSet.add` | Không thêm một phần tử đã có theo bình đẳng |
| `HashSet.contains`, `remove` | Dùng cơ chế băm để tìm, rồi xác định phần tử phù hợp |
| `HashMap.put`, `get`, `containsKey` | Tìm theo bình đẳng và mã băm của khóa |
| `HashMap.containsValue` | Hỏi bình đẳng của giá trị; mã băm khóa không biến thành chỉ mục cho giá trị |
| `TreeSet`, khóa của `TreeMap` | Dùng thứ tự tự nhiên hoặc comparator để xác định vị trí và tương đương |

Không phải mọi collection đều dựa vào băm. Thay `ArrayList` bằng `HashSet` có thể làm một lỗi `hashCode` lộ ra dù phép tìm trong danh sách trước đó vẫn có vẻ đúng.

Hợp đồng của `contains` thường được diễn đạt bằng phép so sánh giá trị, nhưng cách triển khai không bắt buộc gọi `equals` lần lượt cho mọi phần tử. Nó có thể loại bớt ứng viên bằng thông tin băm trước. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 4. Tìm trong List không có nghĩa là loại trùng

Giả sử `CustomerKey` được định nghĩa bằng nhau theo `id`:

```java
CustomerKey first = new CustomerKey("C7");
CustomerKey another = new CustomerKey("C7");

List<CustomerKey> list =
        new ArrayList<>(List.of(first, another));

System.out.println(list.size()); // 2
System.out.println(list.contains(new CustomerKey("C7"))); // true
```

Đây là đoạn minh họa; lớp `CustomerKey` được định nghĩa đầy đủ trong chương trình cuối bài.

Danh sách giữ hai phần tử bằng nhau vì `List` cho phép giữ các lần xuất hiện trùng. `contains` chỉ trả lời có ít nhất một phần tử phù hợp hay không.

Khi gọi `remove(new CustomerKey("C7"))`, danh sách có thể xóa một lần xuất hiện phù hợp theo hợp đồng `remove(Object)`; nó không tự xóa hết mọi phần tử cùng mã.

Cần phân biệt ba nhu cầu:

- **Tìm:** có phần tử phù hợp không?
- **Đếm:** có bao nhiêu lần xuất hiện?
- **Loại trùng:** giữ một đại diện theo quy tắc đã chọn.

Cùng một quy tắc `equals` có thể tham gia cả ba, nhưng cấu trúc và thao tác quyết định kết quả cuối.

## 5. HashSet phối hợp băm với equals thế nào?

Có thể đọc cơ chế ở mức khái niệm:

```text
Giá trị cần thêm hoặc tìm
        ↓
Lấy mã băm để định hướng tìm kiếm
        ↓
Xét các ứng viên trong vùng liên quan
        ↓
Dùng quan hệ bằng nhau để xác định khớp
        ↓
Có khớp: dùng phần tử hiện có
Không khớp: chưa có giá trị tương ứng
```

Đây là mô hình để hiểu vai trò, không phải mô tả cấu trúc riêng của mọi phiên bản JDK. Không cần biết kích thước bảng hay ngưỡng chuyển cấu trúc nội bộ để viết `equals`/`hashCode` đúng.

Với hai khóa bằng nhau:

```java
Set<CustomerKey> unique = new HashSet<>();

System.out.println(unique.add(new CustomerKey("C7"))); // true
System.out.println(unique.add(new CustomerKey("C7"))); // false
System.out.println(unique.size());                     // 1
```

Lần thêm thứ hai không tạo thêm phần tử. Giá trị `false` của `add` cho biết tập không thay đổi do đã có phần tử tương ứng.

Tập cũng không tự hợp nhất dữ liệu nghiệp vụ. Nếu hai đối tượng được định nghĩa bằng nhau theo mã nhưng có thông tin hiển thị khác nhau, gọi `add` lần nữa không phải một lệnh cập nhật các trường của phần tử cũ. Nếu cần “mã → hồ sơ mới nhất”, một `Map` hoặc quy trình cập nhật rõ ràng có thể diễn đạt đúng hơn. [Java 17: HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

## 6. Va chạm mã băm không làm mất giá trị khác nhau

`"Aa"` và `"BB"` là ví dụ ngắn có cùng mã băm theo quy tắc của `String`:

```java
String left = "Aa";
String right = "BB";

System.out.println(left.equals(right)); // false
System.out.println(left.hashCode());    // 2112
System.out.println(right.hashCode());   // 2112
```

Khi thêm vào `HashSet`:

```java
Set<String> values = new HashSet<>(List.of(left, right));
System.out.println(values.size()); // 2
```

Hai chuỗi có cùng hash nhưng không bằng nhau, nên vẫn là hai giá trị. Cấu trúc băm được thiết kế để xử lý va chạm, không phải chỉ giữ một phần tử cho mỗi số nguyên hash. [Java 17: String.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode())

Một `hashCode` luôn trả cùng hằng số cho mọi đối tượng có thể vẫn đáp ứng điều kiện “bằng nhau thì cùng hash”. Tuy nhiên, nó làm giảm khả năng phân tán và có thể gây hiệu năng tìm kiếm kém.

Ngược lại, một hàm tạo hash rất đa dạng nhưng cho hai đối tượng bằng nhau ra hai hash khác nhau là **sai hợp đồng**, không phải một tối ưu hóa chấp nhận được.

### Hai vấn đề cần tách riêng

| Vấn đề | Tính đúng đắn | Hiệu năng |
| --- | --- | --- |
| Có va chạm giữa hai giá trị không bằng nhau | Được phép | Nhiều va chạm có thể làm tăng công tìm kiếm |
| Hai giá trị bằng nhau có hash khác nhau | Vi phạm hợp đồng | Không thể chỉ xem là chậm hơn |
| Hash phân bố tốt và nhất quán với equals | Đáp ứng nền tảng cần thiết | Hỗ trợ tra cứu hiệu quả hơn |

Không cần đòi một hàm hash không va chạm; điều đó cũng không thể bảo đảm cho mọi tập giá trị không giới hạn khi kết quả chỉ có số lượng hữu hạn.

## 7. HashMap dùng quy tắc của khóa

Ví dụ một bảng hồ sơ theo mã khách hàng:

```java
Map<CustomerKey, String> customers = new HashMap<>();

customers.put(new CustomerKey("C7"), "old");
String previous =
        customers.put(new CustomerKey("C7"), "updated");

System.out.println(previous); // old
System.out.println(customers.size()); // 1
System.out.println(customers.get(new CustomerKey("C7"))); // updated
```

Dù mỗi lần gọi tạo một đối tượng khóa mới, bình đẳng theo `id` cùng hash nhất quán giúp map tìm đúng ánh xạ đã có.

Lần `put` thứ hai thay giá trị của cùng khóa logic, không tạo thêm một ánh xạ. Không cần giữ đúng tham chiếu khóa ban đầu để tra cứu.

Cần phân biệt:

- `containsKey(key)` hỏi về bình đẳng của khóa.
- `containsValue(value)` hỏi về bình đẳng của giá trị.
- Giá trị được phép trùng giữa nhiều khóa.
- Khi map cho phép giá trị `null`, `get(key) == null` chưa đủ để kết luận không có khóa.

Không suy diễn rằng map phải thay cả đối tượng khóa được lưu bằng đối tượng truyền vào sau, hoặc phải giữ một nhận dạng tham chiếu cụ thể ngoài những gì API bảo đảm. Điều cần dựa vào là ánh xạ theo khóa logic. [Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

## 8. Viết một kiểu khóa đúng theo miền dữ liệu

Ví dụ chỉ cần nhận biết khách hàng theo `id` trong một phạm vi đã xác định:

```java
static final class CustomerKey {
    private final String id;

    CustomerKey(String id) {
        this.id = Objects.requireNonNull(id);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        return other instanceof CustomerKey key
                && id.equals(key.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Đây là một lớp lồng có thể đặt trong lớp bao ngoài; cần import `java.util.Objects`.

Các quyết định trong ví dụ:

1. `id` không được `null`; constructor kiểm tra ngay.
2. Lớp là `final`, tránh phát sinh một hệ lớp con tự mở rộng nghĩa bình đẳng.
3. `equals` có đúng chữ ký `equals(Object)`, không phải một overload chỉ nhận `CustomerKey`.
4. Hai khóa bằng nhau khi cùng mã.
5. Hash lấy từ chính mã nên hai khóa bằng nhau có cùng hash.
6. Trường `id` là final và là `String` bất biến, giúp quy tắc ổn định trong lúc làm khóa.

`@Override` giúp phát hiện nhầm chữ ký. Nếu lỡ viết `equals(CustomerKey other)`, đó không phải ghi đè phương thức `Object.equals(Object)`; collection có thể vẫn sử dụng hành vi không như dự định.

Không xem mẫu này là quy tắc “mọi lớp đều phải so theo id”. Một kiểu giá trị tọa độ có thể so cả hai thành phần; một khóa nhiều tổ chức cần thêm mã tổ chức.

### Nhiều trường phải có cùng nghĩa ở cả hai phương thức

Với khóa gồm `tenantId` và `customerId`, hai khách hàng cùng mã ở hai tổ chức không được loại trùng với nhau.

Một biểu diễn ngắn trong Java 17:

```java
record TenantCustomerKey(String tenantId, String customerId) {}
```

Các phương thức bình đẳng và băm được sinh mặc định dựa trên các thành phần record. Hai record khác tổ chức sẽ khác nhau.

Record phù hợp khi chính các thành phần khai báo là nghĩa giá trị cần có. Nó không tự bảo đảm mọi đối tượng được tham chiếu bên trong đều bất biến. Nếu thành phần là một danh sách có thể sửa, phải xét tác động đến bình đẳng và băm. [Java 17: Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html)

## 9. Chọn đúng dữ liệu tham gia bình đẳng

Trước khi viết mã, trả lời:

- Hai đối tượng cùng mã nhưng khác tên có được coi là cùng khóa không?
- Mã có duy nhất trong toàn hệ thống hay chỉ trong một tổ chức?
- Giá trị có phân biệt hoa thường không?
- Khoảng trắng hoặc định dạng đầu vào có được chuẩn hóa không?
- Một trường có thể thay đổi sau khi đối tượng được lưu không?
- Một đối tượng mới tạo chưa có mã ổn định phải được xử lý thế nào?

Đừng tùy tiện dùng tên hiển thị, email có thể đổi hoặc mã chưa được cấp làm định danh duy nhất. Nếu yêu cầu là so sánh không phân biệt hoa thường, phải thiết kế cả bước chuẩn hóa và hash phù hợp; đổi riêng `equals` mà giữ hash theo chuỗi gốc dễ phá hợp đồng.

`hashCode` có thể sử dụng ít thông tin hơn `equals` mà vẫn hợp lệ, miễn hai đối tượng bằng nhau luôn cùng hash. Tuy nhiên, bỏ quá nhiều thông tin có thể làm tăng va chạm. Một lựa chọn dễ kiểm tra là xây hash từ các thành phần giá trị bất biến đã dùng để xác định bình đẳng.

Nếu chỉ một chức năng cần loại trùng theo tiêu chí riêng, chưa chắc nên thay `equals` toàn bộ lớp dùng ở nhiều nơi. Có thể tạo kiểu khóa riêng hoặc ánh xạ ra khóa phù hợp cho chức năng ấy. Thay bình đẳng của lớp là thay ý nghĩa tìm kiếm và loại trùng ở mọi collection đang dựa vào nó.

## 10. Không đổi thông tin khóa khi đang ở cấu trúc băm

Giả sử một khóa có `hashCode` phụ thuộc mã khách hàng. Sau khi đưa vào `HashMap`, chương trình đổi mã.

Vị trí lưu đã được xác định theo trạng thái cũ, trong khi lần tìm sau tính từ trạng thái mới. Khi đó, hành vi tìm kiếm hoặc loại bỏ có thể không còn được bảo đảm theo cách ta mong muốn.

Một lỗi như vậy dễ gây cảm giác nghịch lý: duyệt vẫn thấy đối tượng, nhưng tra cứu bằng giá trị mong đợi không tìm thấy. Không viết bài kiểm thử bắt buộc một output cụ thể cho mọi trường hợp đã làm thay đổi khóa theo cách vi phạm điều kiện sử dụng.

Các hướng thiết kế:

- Dùng khóa giá trị bất biến, tách khỏi hồ sơ thường xuyên thay đổi.
- Không đưa những trường có thể đổi vào bình đẳng khóa.
- Nếu thật sự phải đổi danh tính khóa, xóa bằng trạng thái cũ trước, rồi đưa lại vào bằng khóa mới với quy trình phù hợp.
- Với hệ thống dùng chung nhiều nơi, ưu tiên một phép cập nhật có kiểm soát thay vì cho sửa trường trực tiếp.

`final` trên tham chiếu tới một đối tượng có thể sửa chưa đủ: nếu hash phụ thuộc nội dung đối tượng bên trong, nội dung ấy vẫn có thể đổi. Cần xét toàn bộ dữ liệu tham gia tính bình đẳng.

## 11. Giới hạn: không phải mọi loại trùng đều do hashCode

`TreeSet` dùng thứ tự tự nhiên hoặc comparator để tìm và phân biệt phần tử. Hai phần tử so sánh bằng 0 được xem là tương đương trong tập cây.

Nếu comparator chỉ xét tên sản phẩm, hai sản phẩm khác mã nhưng cùng tên có thể bị xem là một giá trị, dù `equals` coi chúng khác nhau. Sửa `hashCode` không giải quyết chuyện đó, vì tập cây không dựa vào hash để xác định vị trí.

Để tuân thủ đầy đủ hợp đồng `Set` dựa trên bình đẳng, thứ tự cần nhất quán với `equals`. Vì vậy, khi chẩn đoán “tại sao mất phần tử khi loại trùng”, trước hết xác định cấu trúc đang dùng là tập băm hay tập cây. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

Tương tự, một thao tác tìm theo predicate tự viết có thể xét thuộc tính khác với `equals`. Không gọi mọi phép khớp dữ liệu là cùng một quan hệ bình đẳng.

## 12. Chương trình Java 17 hoàn chỉnh

Lưu vào `EqualityHashDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class EqualityHashDemo {
    static final class PlainKey {
        private final String id;

        PlainKey(String id) {
            this.id = id;
        }
    }

    static final class CustomerKey {
        private final String id;

        CustomerKey(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            return other instanceof CustomerKey key
                    && id.equals(key.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    record TenantCustomerKey(String tenantId, String customerId) {}

    public static void main(String[] args) {
        PlainKey plainA = new PlainKey("C7");
        PlainKey plainB = new PlainKey("C7");
        Set<PlainKey> plainSet = new HashSet<>(List.of(plainA, plainB));
        System.out.println("plain equals = " + plainA.equals(plainB));
        System.out.println("plain set size = " + plainSet.size());

        CustomerKey first = new CustomerKey("C7");
        CustomerKey sameValue = new CustomerKey("C7");
        System.out.println("same reference = " + (first == sameValue));
        System.out.println("value equals = " + first.equals(sameValue));
        System.out.println("same hash = "
                + (first.hashCode() == sameValue.hashCode()));

        List<CustomerKey> list =
                new ArrayList<>(List.of(first, sameValue));
        System.out.println("list size = " + list.size());
        System.out.println("list contains fresh key = "
                + list.contains(new CustomerKey("C7")));

        Set<CustomerKey> unique = new HashSet<>();
        System.out.println("first add = " + unique.add(first));
        System.out.println("equal add = " + unique.add(sameValue));
        System.out.println("unique size = " + unique.size());
        System.out.println("set contains fresh key = "
                + unique.contains(new CustomerKey("C7")));

        Map<CustomerKey, String> customers = new HashMap<>();
        customers.put(first, "old");
        String previous = customers.put(sameValue, "updated");
        System.out.println("previous map value = " + previous);
        System.out.println("map size = " + customers.size());
        System.out.println("lookup with fresh key = "
                + customers.get(new CustomerKey("C7")));

        String left = "Aa";
        String right = "BB";
        Set<String> collisions = new HashSet<>(List.of(left, right));
        System.out.println("collision values equal = " + left.equals(right));
        System.out.println("left hash = " + left.hashCode());
        System.out.println("right hash = " + right.hashCode());
        System.out.println("collision set size = " + collisions.size());
        System.out.println("collision lookup = "
                + collisions.contains(new String("BB")));

        Set<TenantCustomerKey> scoped = new HashSet<>();
        scoped.add(new TenantCustomerKey("T1", "C7"));
        scoped.add(new TenantCustomerKey("T2", "C7"));
        System.out.println("tenant-scoped size = " + scoped.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EqualityHashDemo.java
java EqualityHashDemo
```

Stdout:

```text
plain equals = false
plain set size = 2
same reference = false
value equals = true
same hash = true
list size = 2
list contains fresh key = true
first add = true
equal add = false
unique size = 1
set contains fresh key = true
previous map value = old
map size = 1
lookup with fresh key = updated
collision values equal = false
left hash = 2112
right hash = 2112
collision set size = 2
collision lookup = true
tenant-scoped size = 2
```

Cách đọc minh chứng:

1. `PlainKey` không ghi đè bình đẳng nên hai đối tượng khác nhau cùng mã vẫn là hai phần tử của tập.
2. `CustomerKey` có bình đẳng giá trị: khác tham chiếu nhưng bằng nhau và cùng hash.
3. Danh sách giữ cả hai lần xuất hiện, nhưng tìm được bằng một khóa mới cùng giá trị.
4. Tập băm chỉ thêm khóa logic lần đầu; lần thêm tương đương trả `false`.
5. Map thay giá trị khi dùng khóa logic đã có, rồi tra được bằng một đối tượng mới.
6. Hai chuỗi va chạm hash vẫn là hai phần tử riêng và đều tra được.
7. Khóa record có thêm phạm vi tổ chức giữ hai khách hàng cùng mã cục bộ ở hai tổ chức khác nhau.

Chương trình không in trực tiếp thứ tự của `HashSet` hoặc `HashMap`, nên stdout không phụ thuộc thứ tự duyệt mà các lớp đó không cam kết. Nó cũng không dựa vào mã hash mặc định hoặc địa chỉ của đối tượng để tạo kết quả cố định.

## 13. Các lỗi phổ biến cần kiểm tra

| Lỗi | Tác động hoặc cách sửa |
| --- | --- |
| So chuỗi bằng `==` | Chỉ kiểm tra tham chiếu; dùng bình đẳng nội dung khi đó là yêu cầu |
| Ghi đè `equals` nhưng giữ hash không phù hợp | Tập/map băm có thể không tìm hoặc loại trùng đúng; sửa đồng thời hợp đồng |
| Chỉ ghi đè `hashCode` để “cùng mã thì cùng người” | Hash không tự định nghĩa bình đẳng; cần `equals` tương ứng |
| Coi cùng hash là cùng giá trị | Va chạm hợp lệ; vẫn phải phân biệt bằng nhau |
| Dùng mọi trường tự động mà không xét nghiệp vụ | Tên hoặc trạng thái đổi có thể làm danh tính giá trị đổi ngoài ý muốn |
| Đổi trường tham gia hash trong lúc làm khóa | Có thể làm lệch quan hệ giữa vị trí lưu và trạng thái tìm |
| Viết `equals(MyType)` thay `equals(Object)` | Tạo overload; dùng `@Override` để phát hiện |
| Bình đẳng bất đối xứng giữa lớp cha và lớp con | Kết quả khớp trở nên không nhất quán; thiết kế ranh giới bình đẳng rõ |
| Coi `HashSet.add` khóa trùng là cập nhật hồ sơ | Tập không tự hợp nhất các trường |
| Coi hash là ID lưu bền hoặc bảo mật | Không duy nhất và không có bảo đảm chung phù hợp mục tiêu đó |

## 14. Cách kiểm chứng một lớp làm khóa

Một bộ kiểm tra có giá trị nên bao gồm:

1. Cùng một đối tượng bằng chính nó.
2. Hai đối tượng có cùng giá trị định danh bằng nhau ở cả hai chiều.
3. Các đối tượng nối tiếp cùng định danh đáp ứng bắc cầu.
4. Hai đối tượng bằng nhau có cùng hash.
5. Hai khóa khác nhau không bị gộp chỉ vì va chạm hash.
6. Tra cứu trong `HashSet` và `HashMap` bằng một đối tượng mới cùng giá trị thành công.
7. Gán giá trị mới cho cùng khóa logic giữ đúng số ánh xạ cần có.
8. Các thành phần phạm vi như tổ chức hoặc môi trường tham gia bình đẳng nếu nghiệp vụ yêu cầu.
9. Dữ liệu dùng làm khóa không thể bị sửa ngoài kiểm soát.

Không kiểm tra “hai đối tượng không bằng nhau bắt buộc khác hash”: đó không phải hợp đồng. Cũng không kiểm tra một giá trị hash cụ thể trừ khi chính kiểu đó có quy tắc công khai cần xác nhận, như ví dụ chuỗi trong bài.

## 15. Tự luyện

1. Hai đối tượng không bằng nhau nhưng cùng hash. `HashSet` có bắt buộc chỉ giữ một không?  
   **Đáp án:** không. Va chạm không tạo bình đẳng; tập vẫn có thể giữ cả hai.

2. Hai đối tượng bằng nhau nhưng hash khác nhau. Điều gì sai?  
   **Đáp án:** lớp đã vi phạm hợp đồng `equals`–`hashCode`.

3. Vì sao `List` có thể chứa hai khóa bằng nhau mà `contains` vẫn trả `true` khi tìm bằng khóa mới?  
   **Đáp án:** danh sách cho phép nhiều lần xuất hiện; tìm kiếm và loại trùng là hai thao tác khác nhau.

4. Hai khách hàng cùng mã ở hai tổ chức bị gộp khi đưa vào tập. Cần kiểm tra gì?  
   **Gợi ý:** bình đẳng khóa có bao gồm phạm vi tổ chức cần thiết hay không.

5. Khi đã dùng record làm khóa, có còn phải xét tính thay đổi của thành phần không?  
   **Đáp án:** có. Record không tự đóng băng đối tượng được tham chiếu bên trong.

Một cấu trúc tìm kiếm hay loại trùng chỉ đúng khi quan hệ giá trị của phần tử được thiết kế đúng. Hãy xác định bình đẳng trước, giữ hash nhất quán với nó và bảo vệ sự ổn định của dữ liệu đang làm khóa.
