# Giữ equals(), hashCode() và thứ tự so sánh cùng một mô hình nghiệp vụ

## 1. Vấn đề: cùng một thực thể nghiệp vụ nhưng nhiều đối tượng Java

Trong ứng dụng, dữ liệu của **cùng một đơn hàng** có thể được nạp từ cơ sở dữ liệu nhiều lần hoặc xuất hiện trong những bản snapshot khác nhau. Hai đối tượng Java đó có thể khác địa chỉ bộ nhớ và khác trạng thái hiển thị, nhưng vẫn biểu diễn **cùng một đơn hàng**.

Ví dụ: `Order("shop-A", 42, 1500)` và `Order("shop-A", 42, 1999)` có cùng khóa nghiệp vụ `(tenantId, orderNo) = ("shop-A", 42)`, còn `totalCents` là một thuộc tính có thể thay đổi theo phiên bản dữ liệu.

Nếu hợp đồng của `Order` quy định **định danh nghiệp vụ** là cặp `tenantId + orderNo`, ba cơ chế trong Java phải cùng tôn trọng lựa chọn đó:

- **`equals(Object)`** trả lời “hai đối tượng có đại diện cùng thực thể nghiệp vụ không?”.
- **`hashCode()`** cung cấp mã băm phù hợp với `equals()` để `HashSet`/`HashMap` định vị phần tử/khóa.
- **`compareTo(T)`** (hoặc `Comparator` dành cho bộ sưu tập có thứ tự) cung cấp thứ tự; kết quả **bằng 0** cần biểu thị cùng định danh khi ta muốn `TreeSet`/`TreeMap` có đúng ngữ nghĩa nghiệp vụ của `equals()`.

Ba phương thức không có nhiệm vụ giống nhau. `equals()` xét quan hệ tương đương; `hashCode()` tối ưu tra cứu theo quan hệ ấy; so sánh tạo thứ tự. Chúng phải **nhất quán theo một mô hình danh tính**, nhưng không có yêu cầu rằng hai giá trị `hashCode()` phải bằng nhau khi hai đối tượng khác nhau, hoặc kết quả `compareTo()` phải bằng `hashCode()`.

## 2. Chốt mô hình nghiệp vụ trước khi chọn trường cho các phương thức

Trước khi cài đặt, cần xác định **điều gì làm hai thực thể trở thành cùng một thực thể**. Đây là quyết định nghiệp vụ, không phải quyết định do IDE tự sinh mã.

Với một đơn hàng thuộc nhiều cửa hàng/tenant:

| Trường | Vai trò | Tham gia `equals` | Tham gia `hashCode` | Tham gia thứ tự tự nhiên |
| --- | --- | --- | --- | --- |
| `tenantId` | Một phần khóa nghiệp vụ | Có | Có | Có, so trước |
| `orderNo` | Một phần khóa nghiệp vụ trong tenant | Có | Có | Có, so sau |
| `totalCents` | Giá trị đơn hàng, có thể đổi | Không | Không | Không, nếu thứ tự tự nhiên dựa trên danh tính |
| `status`, `updatedAt` | Trạng thái/metadata | Không | Không | Không, với cùng mô hình định danh |

Không thể chỉ dùng `orderNo` nếu các tenant có thể cùng phát sinh số 42. Ngược lại, thêm `status` vào `equals` sẽ khiến chính đơn hàng đó trở thành “một thực thể khác” mỗi khi trạng thái đổi.

Có hai mô hình phổ biến; không nên trộn lẫn:

1. **Entity identity:** đối tượng đại diện thực thể có định danh ổn định. So sánh theo khóa, ví dụ `tenantId + orderNo`; nhiều snapshot khác nhau vẫn bằng nhau về nghiệp vụ.
2. **Value object:** toàn bộ thuộc tính có ý nghĩa cấu thành giá trị. Hai value object chỉ bằng nhau khi các thành phần được quy định là giá trị tương đương. Với kiểu bất biến, cách này thường tự nhiên; ví dụ hai tọa độ `(x,y)` có cùng cặp giá trị.

Một class `Order` có số tiền, trạng thái và thời điểm cập nhật nhưng danh tính xác định bằng mã đơn hàng thường nên dùng cách thứ nhất. Nếu nghiệp vụ thực sự coi **toàn bộ nội dung** là định danh, cả `equals`, `hashCode` và khóa so sánh phải chuyển sang mô hình giá trị đó, chứ không chỉ đổi một phương thức.

**Chuẩn hóa khóa:** quy tắc về chữ hoa/thường, khoảng trắng, mã tenant và kiểu số phải được xác định thống nhất khi tạo đối tượng. Ví dụ nếu `shop-A` và `SHOP-A` cùng là một tenant theo nghiệp vụ, cần chuẩn hóa cả hai về cùng biểu diễn chuẩn **trước khi lưu khóa**; nếu phân biệt hoa/thường, giữ nguyên. Không để `equals` bỏ qua hoa/thường trong khi `compareTo` vẫn so sánh có phân biệt.

## 3. Những hợp đồng Java bắt buộc phải hiểu

### 3.1. `equals(Object)` là quan hệ tương đương

Đối với các giá trị tham chiếu không null `x`, `y`, `z`, `equals` phải tuân thủ:

- **Phản xạ:** `x.equals(x)` là `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
- **Nhất quán:** khi các thông tin tham gia `equals` không đổi, gọi lặp lại phải cho cùng kết quả.
- **Với null:** `x.equals(null)` luôn là `false`.

Không nên tạo luật “hai đơn hàng giống nhau nếu số tiền chênh nhau dưới một ngưỡng”, vì quan hệ gần nhau theo ngưỡng có thể **không bắc cầu**: A gần B, B gần C, nhưng A không gần C. Cũng phải chú ý tình huống class cha so sánh với `instanceof` còn class con thêm trường: hai chiều so sánh có thể mất đối xứng. Trong ví dụ dưới đây dùng `final class` để khóa ý nghĩa danh tính và tránh vấn đề kế thừa.

### 3.2. `hashCode()` phải dùng cùng danh tính với `equals()`

Quy tắc bắt buộc:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

Chiều ngược **không bắt buộc**: hai đơn hàng khác nhau có thể bị trùng mã băm (hash collision). `HashSet` và `HashMap` vẫn cần `equals` để xác định phần tử/khóa thực sự trùng.

Một `hashCode()` đúng không nhất thiết duy nhất, không phải định danh lưu database, và không cần ổn định qua các lần chạy ứng dụng. Điều cần giữ là nhất quán với `equals` trong cùng quá trình các trường định danh không đổi.

Sai lầm điển hình:

```java
// Minh họa sai: equals chỉ theo khóa, hashCode lại thêm totalCents.
@Override
public int hashCode() {
    return Objects.hash(tenantId, orderNo, totalCents);
}
```

Khi hai snapshot có cùng `tenantId + orderNo` nhưng tổng tiền khác nhau, `equals` có thể là `true` trong khi mã băm có thể khác; trường `totalCents` phải được loại khỏi `hashCode` nếu nó không thuộc định danh.

### 3.3. `Comparable.compareTo` hoặc `Comparator.compare` tạo thứ tự

Với thứ tự tự nhiên theo cùng khóa, mong muốn:

```text
sign(a.compareTo(b)) == 0   <=>   a.equals(b)
```

Trong đó `sign` là dấu âm/0/dương, không có yêu cầu `compareTo` trả chính xác `-1` hoặc `1`. Java **khuyến nghị mạnh** thứ tự tự nhiên nhất quán với `equals`, nhưng ngôn ngữ không ép mọi class phải tuân theo. Khi đặt vào `TreeSet`/`TreeMap`, kết quả so sánh **0** mới là tiêu chí coi hai phần tử/khóa là trùng; vì thế sự không nhất quán có hậu quả rõ rệt.

Thứ tự còn phải đáp ứng tính phản đối xứng theo dấu và bắc cầu:

```text
sign(compare(a, b)) == -sign(compare(b, a))
compare(a, b) > 0 && compare(b, c) > 0  =>  compare(a, c) > 0
```

Cần bảo đảm những phần tử được xem là bằng nhau theo bộ so sánh có quan hệ so sánh đồng nhất với các phần tử thứ ba. Khi so sánh nhiều trường, so lần lượt theo một thứ tự cố định; dùng `String.compareTo`, `Long.compare`, `Integer.compare` hoặc chuỗi `Comparator.thenComparing`, tránh tự viết phép trừ có thể tràn số.

`equals(null)` là `false` nhưng `compareTo(null)` thường ném `NullPointerException`; hai hành vi không mâu thuẫn. Chỉ hỗ trợ null trong `Comparator` riêng khi nghiệp vụ cần, chẳng hạn `Comparator.nullsFirst(...)`.

## 4. Ví dụ hoàn chỉnh Java 17: cùng một khóa cho cả ba cơ chế

Tạo tệp **`BusinessContractDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class BusinessContractDemo {
    static final class Order implements Comparable<Order> {
        private final String tenantId;
        private final long orderNo;
        private final long totalCents;

        Order(String tenantId, long orderNo, long totalCents) {
            this.tenantId = Objects.requireNonNull(tenantId, "tenantId");
            if (tenantId.isBlank() || orderNo <= 0 || totalCents < 0) {
                throw new IllegalArgumentException("Invalid order fields");
            }
            this.orderNo = orderNo;
            this.totalCents = totalCents;
        }

        long totalCents() {
            return totalCents;
        }

        String keyLabel() {
            return tenantId + "/" + orderNo;
        }

        String displayLabel() {
            return keyLabel() + "(" + totalCents + ")";
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Order that)) return false;
            return orderNo == that.orderNo
                    && tenantId.equals(that.tenantId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, orderNo);
        }

        @Override
        public int compareTo(Order other) {
            Objects.requireNonNull(other, "other");
            int byTenant = tenantId.compareTo(other.tenantId);
            if (byTenant != 0) return byTenant;
            return Long.compare(orderNo, other.orderNo);
        }
    }

    public static void main(String[] args) {
        Order first = new Order("shop-A", 42, 1500);
        Order snapshot = new Order("shop-A", 42, 1999);
        Order next = new Order("shop-A", 43, 1000);

        System.out.println("equals: " + first.equals(snapshot));
        System.out.println("hashCodes equal: "
                + (first.hashCode() == snapshot.hashCode()));
        System.out.println("compareTo zero: "
                + (first.compareTo(snapshot) == 0));
        System.out.println("distinct instances: " + (first != snapshot));

        Set<Order> hashed = new HashSet<>(List.of(first, snapshot, next));
        Set<Order> ordered = new TreeSet<>(List.of(first, snapshot, next));
        System.out.println("HashSet size: " + hashed.size());
        System.out.println("TreeSet size: " + ordered.size());
        System.out.println("TreeSet keys: "
                + ordered.stream().map(Order::keyLabel).toList());

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("BigDecimal equals: " + x.equals(y));
        System.out.println("BigDecimal compareTo zero: "
                + (x.compareTo(y) == 0));
        System.out.println("BigDecimal HashSet/TreeSet sizes: "
                + new HashSet<>(List.of(x, y)).size() + "/"
                + new TreeSet<>(List.of(x, y)).size());

        List<Order> display = new ArrayList<>(List.of(next, first));
        display.sort(
                Comparator.comparingLong(Order::totalCents)
                        .reversed()
                        .thenComparing(Comparator.naturalOrder())
        );
        System.out.println("Display by total: "
                + display.stream().map(Order::displayLabel).toList());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BusinessContractDemo.java
java BusinessContractDemo
```

Kết quả:

```text
equals: true
hashCodes equal: true
compareTo zero: true
distinct instances: true
HashSet size: 2
TreeSet size: 2
TreeSet keys: [shop-A/42, shop-A/43]
BigDecimal equals: false
BigDecimal compareTo zero: true
BigDecimal HashSet/TreeSet sizes: 2/1
Display by total: [shop-A/42(1500), shop-A/43(1000)]
```

Giải thích các phần quan trọng:

1. `first` và `snapshot` là **hai đối tượng khác nhau**, tổng tiền cũng khác nhau, nhưng có cùng khóa `shop-A/42`. Theo mô hình được chọn, `equals` phải trả `true`.
2. `hashCode` chỉ băm `tenantId` và `orderNo`. Vì hai instance bằng nhau về nghiệp vụ nên mã băm cũng bằng nhau.
3. `compareTo` so tenant trước, số đơn sau; cùng khóa cho kết quả 0. Với các đơn khác khóa, Java xác lập một thứ tự ổn định, có tính bắc cầu.
4. `HashSet` dùng băm rồi `equals` để loại bản ghi lặp, còn `TreeSet` dùng `compareTo`; **cả hai đều còn hai đơn hàng**.
5. `BigDecimal` là phản ví dụ từ thư viện chuẩn: `1.0` và `1.00` bằng nhau khi so về trị số theo `compareTo`, nhưng `equals` xét cả scale nên là `false`. Vì vậy `HashSet` giữ hai phần tử, `TreeSet` giữ một.
6. Phần cuối **chỉ sắp xếp một `List` phục vụ hiển thị** theo tổng tiền giảm dần. `thenComparing(Comparator.naturalOrder())` cố định thứ tự khi tổng tiền bằng nhau; bộ so sánh hiển thị này không được mặc nhiên dùng làm quy tắc định danh cho `TreeSet`.

Trong ví dụ, `totalCents` là `final` để đầu ra ổn định. Nếu dữ liệu này có thể đổi trong một đối tượng khác, nó vẫn không nên tham gia băm hoặc thứ tự của khóa `TreeSet` khi không thuộc định danh nghiệp vụ.

## 5. Phân biệt thứ tự dùng để xác định trùng với thứ tự dùng để hiển thị

Nhiều màn hình cần sắp xếp theo “đơn đắt nhất trước”, “cập nhật gần nhất trước” hoặc “trạng thái ưu tiên trước”. Đó là **tiêu chí trình bày**, khác với câu hỏi “hai đơn hàng có cùng định danh không?”.

Với các đối tượng `Order` ở phần 4, phương thức so sánh dưới đây phù hợp để sắp xếp một `List<Order>` (đoạn minh họa, không phải chương trình độc lập):

```java
Comparator<Order> byAmountForDisplay =
        Comparator.comparingLong(Order::totalCents)
                .reversed()
                .thenComparing(Comparator.naturalOrder());
```

Nhưng **không sử dụng bộ so sánh ấy cho `TreeSet`** nếu tập hợp cần giữ đúng ý nghĩa “một phần tử cho mỗi khóa đơn hàng”. Hai snapshot cùng đơn `shop-A/42` có thể có tổng tiền khác nhau, khiến bộ so sánh hiển thị trả khác 0 trong khi `equals` là `true`.

Một lỗi khác là chỉ so tổng tiền:

```java
// Minh họa nguy hiểm nếu dùng làm comparator của TreeSet<Order>.
Comparator<Order> amountOnly =
        Comparator.comparingLong(Order::totalCents);
```

Hai **đơn hàng khác khóa** cùng tổng tiền cho kết quả 0, nên `TreeSet` coi chúng là trùng và chỉ giữ một. Thêm tiêu chí phá hòa bằng khóa giúp phân biệt các đơn khác nhau có cùng tổng tiền, nhưng **vẫn chưa bảo đảm** hai snapshot của *cùng một đơn* có tổng tiền khác nhau so ra bằng 0. Vì vậy, muốn sorted set bảo toàn định danh nghiệp vụ, hãy so sánh **trực tiếp theo chính khóa nghiệp vụ**.

| Tình huống | Cách phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| Tra cứu/tránh trùng thực thể theo khóa nghiệp vụ | `HashSet`, `HashMap` với `equals/hashCode` dựa trên khóa | Khóa ổn định, đầy đủ tenant, `equals` và `hashCode` nhất quán |
| Vừa có thứ tự vừa loại trùng theo khóa nghiệp vụ | `TreeSet`, `TreeMap` với so sánh theo cùng khóa | `compare(a,b)==0` khi và chỉ khi `a.equals(b)` |
| Chỉ hiển thị danh sách theo tổng tiền/trạng thái/ngày | `List.sort(Comparator)` | Có thể khác mô hình `equals`; xác định tie-breaker nếu cần thứ tự tất định |
| Muốn sắp xếp giá trị bất biến khác với danh tính entity | Danh sách/view/model riêng, hoặc chỉ số phụ được thiết kế rõ | Không vô tình coi thứ tự hiển thị là quy tắc loại trùng |

**Hệ quả với map:** `HashMap` tìm khóa bằng băm và `equals`; `TreeMap` xác định cùng khóa theo `compareTo` hoặc `Comparator` của nó. Nếu `compare` trả 0 cho hai key khác nhau về `equals`, lệnh `put` khóa thứ hai trong `TreeMap` có thể thay **value của cùng entry**, dù `HashMap` sẽ coi đó là hai key riêng. Một `TreeMap` hoặc `TreeSet` có thứ tự không nhất quán với `equals` có thể hoạt động theo quy tắc comparator của nó, nhưng không đáp ứng đầy đủ hợp đồng `Map`/`Set` thông thường về việc các phần tử/khóa bằng nhau.

Nếu class không có **thứ tự tự nhiên nghiệp vụ rõ ràng**, có thể không implement `Comparable`. Hãy dùng một `Comparator` tường minh tại nơi cần thứ tự, và đặc biệt cân nhắc sự nhất quán với `equals` nếu comparator được sử dụng để định danh trong sorted collection.

## 6. Vì sao BigDecimal và phép chuẩn hóa là trường hợp đáng chú ý?

Theo Java, `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` vì cùng trị số, nhưng `equals` là `false` vì biểu diễn có **scale khác nhau**. Đây là một trường hợp nổi tiếng mà thứ tự tự nhiên không nhất quán với `equals`.

Vì vậy, nếu **tiền** là một phần định danh của value object, hãy quyết định rõ khái niệm bằng nhau:

- Nếu `1.0` và `1.00` **phải là cùng giá trị nghiệp vụ**, chuẩn hóa chúng về biểu diễn nhất quán trước khi lưu trong value object; ví dụ lưu `long cents` khi đồng tiền chỉ dùng hai chữ số thập phân, hoặc chuẩn hóa `BigDecimal` theo quy tắc scale/đồng tiền đã thống nhất.
- Nếu **scale có ý nghĩa nghiệp vụ** (độ chính xác được khai báo hoặc dữ liệu gốc), `BigDecimal.equals` có thể đúng với value object ấy; khi đó không thể dùng riêng `BigDecimal.compareTo` để bảo toàn đúng cùng tập các lớp tương đương.
- Không tùy tiện dùng `stripTrailingZeros()` hoặc `setScale(...)` khi chưa có quy tắc domain: cần cân nhắc scale âm, làm tròn và đơn vị tiền tệ.

Một khi chuẩn hóa, **tất cả đường tạo giá trị** (constructor, parser, mapper, dữ liệu từ DB/API) phải áp dụng cùng quy tắc. Không nên sửa chắp vá bằng cách chỉ bỏ qua scale trong `equals` nhưng giữ `hashCode` mặc định trên một `BigDecimal` chưa chuẩn hóa.

Với `String`, hai mã khác chữ hoa/thường, Unicode normalization hoặc dấu cách cũng có thể tạo bất đồng nếu một phương thức so sánh “thoáng” hơn phương thức khác. Dùng giá trị khóa đã được canonicalize thống nhất.

## 7. Thiết kế khóa bất biến và tránh bẫy thay đổi khi đã ở trong collection

Giả sử `Order` dùng `status` trong `hashCode`, rồi được thêm vào `HashSet`. Sau khi đổi trạng thái, mã băm được tính từ trạng thái mới có thể không còn khớp bucket cũ; `contains(order)` hoặc `remove(order)` có thể không tìm thấy chính phần tử từng được thêm.

Tương tự, khi thứ tự `compareTo` hoặc comparator của `TreeSet` phụ thuộc vào trường mutable đang bị sửa bên ngoài, cấu trúc cây không tự sắp xếp lại. Thao tác `contains`/`remove`, thứ tự duyệt hoặc tính nhất quán có thể sai.

Vì vậy:

1. Chọn **khóa nghiệp vụ ổn định** theo vòng đời thực thể; với thực thể chưa được gán ID bởi database, phải quy định rõ giai đoạn trước/sau khi phát sinh ID và tránh dùng khóa đang thay đổi trong hash/sorted collections.
2. Ưu tiên trường `final` hoặc value object bất biến làm khóa, bảo đảm các lớp mutable lồng trong khóa không bị sửa qua reference khác.
3. Các thuộc tính có thể thay đổi như tổng tiền, trạng thái, thời gian cập nhật chỉ nên là dữ liệu; muốn xếp hạng lại theo chúng, hãy **sort lại danh sách** hoặc xây lại cấu trúc chỉ số phù hợp.
4. Không dùng `System.identityHashCode`, `==` hay địa chỉ bộ nhớ thay cho business identity, trừ khi nghiệp vụ cố ý định nghĩa equality theo **identity đối tượng JVM**.
5. Nếu dùng một khóa tự nhiên như `email`, kiểm tra xem email có thể thay đổi hay tái sử dụng theo nghiệp vụ không. Nếu có, một ID ổn định thường thích hợp hơn cho danh tính entity.

`hashCode` không phải khóa duy nhất trong database. Dữ liệu quan trọng vẫn cần **constraint/unique index** ở hệ thống lưu trữ; việc `equals` đúng trong một JVM không tự ngăn hai transaction khác nhau tạo bản ghi trùng khóa.

## 8. Cách áp dụng với record, giá trị tổng hợp và kế thừa

**Record:** Java 17 có `record` và tự sinh `equals`/`hashCode` theo tất cả component của record, nhưng **không tự sinh `Comparable.compareTo`**. Record phù hợp để gói một khóa nghiệp vụ bất biến:

```java
// Đoạn minh họa độc lập với class Order ở phần 4.
record OrderKey(String tenantId, long orderNo)
        implements Comparable<OrderKey> {
    @Override
    public int compareTo(OrderKey other) {
        int c = tenantId.compareTo(other.tenantId);
        return c != 0 ? c : Long.compare(orderNo, other.orderNo);
    }
}
```

Khi tất cả component `OrderKey` đều được chuẩn hóa và có semantics tương thích giữa `equals` với `compareTo`, record giữ hợp đồng đó ngắn gọn. Bản thân record chỉ làm **reference field là final**, không tự biến đối tượng mutable bên trong thành bất biến; không đưa `List` mutable hay một đối tượng mutable chưa được phòng vệ vào business key.

**Kế thừa:** nếu class cha và con mỗi lớp tự thêm trường định danh theo cách khác, `equals` có thể mất đối xứng, còn `compareTo` có thể không xử lý loại con đúng. Với business key được dùng trong set/map, ưu tiên một kiểu khóa final/record bất biến hoặc một chính sách type/equality rõ ràng áp dụng cho toàn bộ phân cấp. Việc dùng `getClass()` hay `instanceof` phải bám hợp đồng; ví dụ dùng `final class Order` để không có subtype mở rộng identity một phía.

**ID kỹ thuật so với khóa nghiệp vụ:** nếu `OrderKey` là `tenantId + orderNo`, phải thống nhất xem định danh này do database phát sinh hay có sẵn từ domain. Trong tình huống ID chưa tồn tại, không được ngầm dùng các trường tạm thời vào `equals` rồi đổi sang ID khi persist mà không tính tới hậu quả đối với các collection đang giữ phần tử.

## 9. Ma trận kiểm thử cho hợp đồng đồng nhất

Ví dụ dữ liệu kiểm thử của `Order`:

| A | B | `A.equals(B)` | `A.hashCode()==B.hashCode()` | Dấu của `A.compareTo(B)` |
| --- | --- | --- | --- | --- |
| `shop-A/42, 1500` | `shop-A/42, 1999` | `true` | **Phải true** | `0` |
| `shop-A/42, 1500` | `shop-A/43, 1500` | `false` | Không quy định | Âm |
| `shop-A/42, 1500` | `shop-B/42, 1500` | `false` | Không quy định | Âm |
| `shop-B/42, 1500` | `shop-A/42, 1500` | `false` | Không quy định | Dương |

**Không kiểm tra “hash khác nhau” cho những cặp không bằng nhau:** mã băm khác nhau không phải một invariant bắt buộc, còn trùng băm là trường hợp bình thường.

Một checklist kiểm thử có khả năng phát hiện lỗi thật:

- **Phản xạ/đối xứng/bắc cầu:** cùng đối tượng, hai snapshot, ba snapshot cùng business key; `equals(null) == false`.
- **Hàm băm:** mọi cặp `equals == true` đều có `hashCode` bằng nhau; thay `totalCents` ở bản snapshot khác không ảnh hưởng hash của khóa.
- **Thứ tự:** `compare(a,b)==0` khi và chỉ khi `a.equals(b)` theo mô hình này; đổi chiều thì đổi dấu, và các bộ ba khóa tăng dần giữ tính bắc cầu.
- **Bộ sưu tập:** cùng dữ liệu đưa vào `HashSet` và `TreeSet` phải có cùng số **khóa nghiệp vụ**; `HashMap` và `TreeMap` phải tra cứu cùng key nghiệp vụ theo chính sách thống nhất.
- **Phân tách tenant:** cùng `orderNo` nhưng khác `tenantId` không được coi trùng.
- **Dữ liệu biên:** null, chuỗi rỗng, ID âm/0, giá trị số lớn; dùng `Long.compare` để tránh overflow thay vì trừ.
- **Chuẩn hóa:** các biểu diễn khác nhau nhưng nghiệp vụ quy định cùng khóa phải được đưa về cùng dạng ở mọi đường tạo object.
- **Thay đổi state:** thay đổi thuộc tính không thuộc khóa không làm thay đổi tập các thực thể được nhận diện bởi `equals`, `hashCode`, `compareTo`.

Những kiểm tra này tốt hơn việc chỉ chạy IDE-generated `equals` test với một object có tất cả trường giống nhau: chúng xác minh được **ranh giới danh tính** do nghiệp vụ chọn.

## 10. Các lỗi thực tế cần tránh

1. **Chọn trường độc lập cho ba phương thức:** `equals` theo ID, `hashCode` theo toàn bộ field, `compareTo` theo giá tiền. Kết quả là mỗi collection có một khái niệm “trùng” khác nhau.
2. **Dùng phép trừ trong so sánh:** `return (int) (a.orderNo - b.orderNo);` có thể tràn hoặc mất bit. Dùng `Long.compare(a.orderNo, b.orderNo)`.
3. **Thêm tie-breaker không suy xét vào comparator của `TreeSet`:** thêm `totalCents` giúp sắp xếp đẹp hơn nhưng có thể làm hai snapshot cùng ID so ra khác 0. Hãy giữ comparator định danh tách khỏi comparator hiển thị.
4. **Quên khóa kết hợp gồm tenant:** hai đơn trùng `orderNo` giữa các tenant vô tình gộp thành một.
5. **Đưa trường mutable vào hash/order:** sửa nó sau khi đã thêm vào `HashSet`/`TreeSet` có thể làm thao tác lookup/remove không tin cậy.
6. **Cho rằng `compareTo()==0` luôn đồng nghĩa với `equals()==true` ở mọi thư viện:** `BigDecimal` là phản ví dụ; phải hiểu semantics trước khi dùng làm key có thứ tự.
7. **Tưởng record tự sinh mọi hợp đồng:** record tự sinh `equals` và `hashCode` nhưng không tự cung cấp ordering; các component mutable còn có thể phá tính ổn định của key.
8. **Sử dụng comparator hiển thị làm quy tắc uniqueness:** sắp xếp theo giá hay thời điểm cập nhật phù hợp cho danh sách; với sorted set/map cần tính chất trùng theo ý định nghiệp vụ.
9. **Chọn khóa không ổn định khi thực thể chưa có ID:** thay đổi identity giữa lúc đang ở trong map/set có thể gây lỗi khó tìm; thiết kế vòng đời khóa ngay từ đầu.

**Nguyên tắc áp dụng:** trước hết xác định một mô hình danh tính doanh nghiệp chính xác. Với entity `Order` ở bài này, cùng `tenantId + orderNo` phải **bằng nhau qua `equals`**, **có cùng mã băm**, và **so sánh bằng 0** theo thứ tự dùng cho `TreeSet`/`TreeMap`. Mọi thứ tự phục vụ giao diện hoặc báo cáo được diễn đạt bằng comparator riêng trên danh sách; không nên để một tiêu chí hiển thị vô tình thay đổi ý nghĩa “cùng một thực thể”.
