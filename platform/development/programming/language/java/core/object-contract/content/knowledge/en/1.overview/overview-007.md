# Hậu quả khi một lớp phá vỡ hợp đồng trong thư viện chuẩn Java

Khi đưa đối tượng vào `HashMap`, `HashSet`, `TreeMap`, `TreeSet` hoặc các thuật toán sắp xếp, thư viện chuẩn **tin vào các hợp đồng** mà lớp công bố qua `equals`, `hashCode`, `Comparable` và `Comparator`. Nếu lớp cài đặt sai, mã thư viện vẫn có thể chạy đúng theo thiết kế nhưng kết quả quan sát được sẽ sai kỳ vọng: không tìm lại được phần tử, lưu các phần tử trùng về mặt logic, mất dữ liệu khi chèn, thứ tự sai hoặc thuật toán sắp xếp báo lỗi.

Mấu chốt là phân biệt ba tình huống: **thật sự vi phạm hợp đồng**, **thay đổi trạng thái khóa sau khi lưu**, và **hai API dùng quy tắc xác định tương đương khác nhau nhưng đều hợp lệ**.

## 1. Những hợp đồng mà thư viện dựa vào

| Thành phần | Quy tắc thiết yếu | Nơi chịu ảnh hưởng |
| --- | --- | --- |
| `Object.equals(Object)` | Phản xạ, đối xứng, bắc cầu, nhất quán khi thông tin so sánh không đổi; `x.equals(null)` là `false` | `List.contains`, `remove`, `HashSet`, khóa `Map`, xử lý trùng lặp |
| `Object.hashCode()` | Nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()`; hash ổn định khi dữ liệu dùng để xác định bằng nhau không đổi | `HashMap`, `HashSet`, `LinkedHashMap`, `LinkedHashSet` |
| `Comparable.compareTo` / `Comparator.compare` | Kết quả so sánh có dấu nhất quán, phản đối xứng về dấu, có tính bắc cầu và nhất quán khi trả về `0` | `TreeSet`, `TreeMap`, `Arrays.sort`, `List.sort`, `Collections.sort` |
| Quy tắc khóa của `Map` | Không thay đổi dữ liệu ảnh hưởng đến `equals`/`hashCode` của khóa trong lúc nó đang là khóa | Tra cứu, xóa, cập nhật mục trong bản đồ |

### Đối với `equals` và `hashCode`

- `x.equals(x)` phải là `true` (phản xạ).
- `x.equals(y)` phải có cùng kết quả với `y.equals(x)` (đối xứng).
- Nếu `x.equals(y)` và `y.equals(z)` đều đúng thì `x.equals(z)` phải đúng (bắc cầu).
- Khi dữ liệu dùng để so sánh không đổi, các lần gọi `equals` phải nhất quán; `equals(null)` phải trả `false`.
- **Chiều bắt buộc** là `equals == true` kéo theo **cùng hash code**. Chiều ngược lại không bắt buộc: hai đối tượng khác nhau có thể có cùng hash code (va chạm hash).

Việc cài `equals` mà bỏ quên `hashCode`, hoặc để hai phương thức dùng tập thuộc tính khác nhau, rất dễ phá vỡ chiều bắt buộc trên. `HashMap` dùng hash để chọn vị trí tìm kiếm và dùng `equals` để xác định khóa tương đương trong phần phù hợp; nó không thể tự sửa một quy tắc so sánh mâu thuẫn.

### Đối với `Comparable`/`Comparator`

Một thứ tự hợp lệ phải đủ nhất quán để các thuật toán sắp xếp và cấu trúc cây hoạt động. Ví dụ, nếu so sánh cho biết `a < b` và `b < c` thì không thể đồng thời cho `a > c`. Nếu `compare(a,b) == 0` thì dấu so sánh của `a` và `b` với một `c` phải nhất quán. Vi phạm có thể gây thứ tự vô lý; trong một số trường hợp `List.sort`/`Arrays.sort` ném `IllegalArgumentException: Comparison method violates its general contract!`, nhưng **không phải mọi dữ liệu đầu vào đều kích hoạt lỗi**.

Việc `compare(a,b) == 0` trong khi `!a.equals(b)` **không tự động vi phạm hợp đồng `Comparator`**. Tuy nhiên, với `SortedSet` và `SortedMap`, nó thay đổi khái niệm “trùng nhau”; nếu cần phù hợp đầy đủ với hợp đồng chung của `Set`/`Map` thì thứ tự nên nhất quán với `equals`, hoặc sự khác biệt phải được hiểu và ghi rõ.

## 2. Hậu quả cụ thể

### 2.1. `HashSet` có thể chứa hai đối tượng vốn phải được coi là bằng nhau

Giả sử `a.equals(b) == true` nhưng `a.hashCode() != b.hashCode()`. Hai phần tử có thể đi vào hai nhóm hash khác nhau. Khi đó `HashSet.add(a)` rồi `add(b)` có thể làm kích thước tăng lên `2`, mặc dù theo định nghĩa `equals` của lớp, chúng là một giá trị logic.

Vấn đề tương tự xuất hiện ở khóa `HashMap`: `get`, `containsKey`, `remove` hoặc `put` dùng một đối tượng tương đương mới có thể không truy cập đúng mục đã lưu. Các lớp thư viện này không có nghĩa vụ dò toàn bộ bảng để bù cho `hashCode` sai.

### 2.2. Khóa mutable có thể trở nên “không tìm thấy” sau khi chèn

Ngay cả khi `equals` và `hashCode` được viết **đúng với trạng thái hiện tại**, thay đổi thuộc tính tham gia hai phương thức sau `map.put(key, value)` vẫn nguy hiểm. Bản đồ đã sắp xếp khóa dựa trên hash tại lúc chèn; sau khi đổi trạng thái, việc tìm với hash mới có thể thất bại. Mục vẫn tồn tại trong bản đồ và vẫn chiếm bộ nhớ, nhưng API tra cứu thông thường có thể không tìm được.

Đây là **vi phạm giả định sử dụng khóa ổn định**, không nhất thiết là vi phạm hợp đồng `hashCode`: hợp đồng cho phép hash thay đổi khi dữ liệu dùng bởi `equals` thay đổi.

### 2.3. `TreeSet`/`TreeMap` có thể làm mất mục theo góc nhìn `equals`

`TreeSet` và `TreeMap` dùng kết quả so sánh (`compareTo` hoặc `Comparator`) để tìm vị trí và quyết định hai khóa có tương đương hay không: `compare(a,b) == 0` được xử lý như một khóa đã có. Vì thế:

- `TreeSet.add` có thể trả `false` cho một phần tử mà `equals` xem là khác.
- `TreeMap.put` với khóa so sánh bằng `0` có thể **thay giá trị của khóa cũ** thay vì thêm mục mới.
- `contains`, `remove` và phạm vi sắp xếp phản ánh quy tắc so sánh, nên có thể khác suy nghĩ dựa trên `equals`.

Không được vội kết luận thư viện làm mất dữ liệu vì lỗi: trước tiên phải kiểm tra chính xác quy tắc bằng nhau mà cấu trúc dữ liệu đang dùng.

### 2.4. Lỗi có thể lan sang tầng nghiệp vụ

Với định danh tài khoản, hàng đợi công việc, cache hoặc bộ lọc chống trùng, lỗi hợp đồng có thể làm dữ liệu trùng không được loại bỏ; truy vấn cache bỏ lỡ; chức năng xóa không xóa được phần tử kỳ vọng; thống kê kích thước sai; hoặc một khóa bị ghi đè theo quy tắc sắp xếp. Đầu ra đôi lúc thay đổi theo thứ tự thao tác, tập dữ liệu và trạng thái đối tượng, nên lỗi khó tái hiện nếu chỉ thử một trường hợp thuận lợi.

## 3. Ví dụ Java 17+: ba hiện tượng khác nhau

Tệp `ContractConsequencesDemo.java` dưới đây chạy độc lập, cố ý chứa hai lớp khóa thiết kế sai hoặc sử dụng sai để quan sát hậu quả. Trường hợp `BigDecimal` ở cuối là **khác biệt được tài liệu Java công bố**, không phải bug của `BigDecimal`.

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ContractConsequencesDemo {
    // SAI: equals so sánh id, hashCode lại phụ thuộc vào hint độc lập.
    static final class BadKey {
        final String id;
        final int hint;

        BadKey(String id, int hint) {
            this.id = id;
            this.hint = hint;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BadKey that && Objects.equals(id, that.id);
        }

        @Override
        public int hashCode() {
            return hint;
        }
    }

    // Đúng theo trạng thái hiện tại, nhưng không an toàn khi dùng làm khóa rồi sửa id.
    static final class MutableKey {
        String id;

        MutableKey(String id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey that && Objects.equals(id, that.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    public static void main(String[] args) {
        BadKey a = new BadKey("X", 1);
        BadKey b = new BadKey("X", 2);
        Set<BadKey> brokenSet = new HashSet<>();
        brokenSet.add(a);
        brokenSet.add(b);

        System.out.println(a.equals(b));                   // true
        System.out.println(a.hashCode() == b.hashCode());   // false
        System.out.println(brokenSet.size());               // 2

        MutableKey key = new MutableKey("A");
        Map<MutableKey, String> map = new HashMap<>();
        map.put(key, "stored");
        System.out.println(map.get(key));                   // stored
        key.id = "B";
        System.out.println(map.get(key));                   // null
        System.out.println(map.size());                     // 1

        List<BigDecimal> numbers = List.of(
                new BigDecimal("1.0"),
                new BigDecimal("1.00")
        );
        System.out.println(new HashSet<>(numbers).size());  // 2
        System.out.println(new TreeSet<>(numbers).size());  // 1
        System.out.println(numbers.get(0).equals(numbers.get(1)));   // false
        System.out.println(numbers.get(0).compareTo(numbers.get(1))); // 0
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ContractConsequencesDemo.java
java ContractConsequencesDemo
```

Kết quả chuẩn:

```text
true
false
2
stored
null
1
2
1
false
0
```

Giải thích từng nhóm:

1. Hai `BadKey` có cùng `id` nên `equals` trả `true`, nhưng hash code khác `1` và `2`. `HashSet` lưu được cả hai: lớp `BadKey` đã phá vỡ hợp đồng, không phải `HashSet`.
2. `MutableKey` ban đầu có `id = "A"` nên tìm được chuỗi `stored`. Sau khi đổi thành `"B"`, mã hash của chuỗi đổi; `HashMap.get(key)` không tìm thấy mục cũ, dù `size()` vẫn bằng `1`. Ví dụ dùng chuỗi `"A"`/`"B"` để đầu ra xác định trên `HashMap` của Java chuẩn.
3. `BigDecimal("1.0")` và `BigDecimal("1.00")` khác nhau theo `equals` vì khác scale, nhưng `compareTo` trả `0` do cùng giá trị số. `HashSet` coi là hai phần tử; `TreeSet` coi là một theo thứ tự tự nhiên. Đây là hành vi có chủ đích, cho thấy chọn cấu trúc dữ liệu cũng là chọn tiêu chí tương đương.

## 4. Những kiểu lỗi thường gặp khi tự cài đặt

### Overload nhầm `equals` thay vì override

```java
// SAI: chỉ tạo overload, không ghi đè Object.equals(Object).
public boolean equals(UserId other) {
    return other != null && value.equals(other.value);
}
```

`HashSet`/`HashMap` gọi chữ ký `equals(Object)`. Nếu lớp chỉ có `equals(UserId)`, chúng vẫn có thể dùng phương thức kế thừa từ `Object` (so sánh định danh tham chiếu), khiến hai giá trị cùng mã vẫn bị xem là khác nhau. Dùng `@Override` và khai báo đúng `public boolean equals(Object other)` để trình biên dịch phát hiện lỗi chữ ký.

### Bỏ qua đối xứng hoặc bắc cầu khi kế thừa

Một lớp cha cho phép mọi lớp con cùng `id` bằng nhau, nhưng lớp con lại bắt buộc thêm `region`, có thể tạo `parent.equals(child) == true` trong khi `child.equals(parent) == false`. Thêm nhiều đối tượng còn có thể phá tính bắc cầu. Các cấu trúc dùng `equals` không thể định nghĩa một tập hợp nhất quán khi quan hệ “bằng nhau” tự mâu thuẫn.

Khi thiết kế value object, ưu tiên giá trị bất biến, lớp `final` hoặc mô hình so sánh có chiến lược kế thừa rõ ràng. Tránh sửa `equals` theo cách làm hai phía bất đồng.

### Comparator dùng phép trừ hoặc dùng dữ liệu biến đổi

```java
// Nguy hiểm: a - b có thể tràn số nguyên.
Comparator<Integer> bad = (a, b) -> a - b;

// Đúng và tránh tràn:
Comparator<Integer> good = Integer::compare;
```

Đây là mảnh mã minh họa, không phải chương trình Java độc lập. Phép trừ số nguyên có thể tràn khiến dấu sai và làm thứ tự không nhất quán. Một `Comparator` đọc thuộc tính mutable đang thay đổi trong khi đối tượng ở `TreeSet`/`TreeMap` cũng có thể khiến thao tác tra cứu hoặc thứ tự cây không còn phù hợp với hiện trạng.

### Nhầm `toString` với danh tính đối tượng

`Object.toString()` phục vụ biểu diễn văn bản, gỡ lỗi và logging; nó không thay `equals`/`hashCode`. Hai đối tượng có cùng chuỗi `toString()` không mặc nhiên bằng nhau, và bản thân chuỗi hiển thị không nhất thiết ổn định hoặc duy nhất. Đừng lấy định dạng log làm tiêu chí khóa nếu chưa xác định rõ ngữ nghĩa.

## 5. Cách thiết kế và phòng tránh

1. **Xác định danh tính logic trước khi viết code.** Với `UserId`, có thể chỉ `id` tham gia bằng nhau; với đối tượng miền nghiệp vụ, phải quyết định rõ có đưa phiên bản, trạng thái, loại đối tượng hoặc trường hợp kế thừa vào hay không.
2. **Cài `equals` và `hashCode` cùng một tập thuộc tính.** Cập nhật cả hai khi thay đổi định nghĩa bằng nhau. Dùng `Objects.equals`, `Objects.hash` khi phù hợp; hash code có va chạm vẫn đúng về ngữ nghĩa, dù có thể ảnh hưởng hiệu năng.
3. **Ưu tiên khóa bất biến.** Ví dụ `record UserId(String value) {}` ở Java 17 tự sinh `equals`/`hashCode` theo thành phần `value`. Nhưng record không tự làm cho đối tượng tham chiếu bên trong bất biến: nếu thành phần là mảng hay collection mutable, vẫn cần thiết kế sao cho so sánh và hash ổn định. Với mảng, `equals`/`hashCode` sinh bởi record dùng ngữ nghĩa tham chiếu của mảng, không tự so sánh sâu các phần tử.
4. **Chọn quy tắc sắp xếp có chủ đích.** Khi dùng `TreeSet`/`TreeMap`, kiểm tra ý nghĩa của `compare == 0`. Nếu hai đối tượng khác nhau theo danh tính nghiệp vụ phải cùng tồn tại, comparator cần khóa phân biệt đủ mạnh, ví dụ so sánh thêm mã định danh ổn định. Nếu cố ý gộp theo một giá trị, phải chấp nhận semantics của sorted set/map.
5. **Không thay đổi thuộc tính ảnh hưởng đến thứ tự/khóa sau khi chèn.** Muốn cập nhật, hãy loại bỏ theo trạng thái cũ trước, tạo giá trị mới hoặc cập nhật lúc đối tượng chưa nằm trong collection, rồi chèn lại; với khóa map không thể tra cứu, có thể cần xây dựng lại cấu trúc từ nguồn dữ liệu tin cậy.
6. **Kiểm thử hợp đồng, không chỉ một lệnh `put/get`.** Tạo ít nhất ba đối tượng đại diện cho cùng giá trị, giá trị khác, lớp cha/con hoặc trạng thái khác nếu có. Kiểm tra phản xạ, đối xứng, bắc cầu, `equals(null)`, chiều kéo theo giữa `equals` và `hashCode`, cùng việc tìm/xóa bằng một đối tượng tương đương mới. Với comparator, kiểm tra ba phần tử, thứ tự đảo và trường hợp bằng `0`, đặc biệt các số ở biên.

Một phép thử rất quan trọng: nếu `a.equals(b)` trả `true` thì **bắt buộc** `a.hashCode() == b.hashCode()`. Phép thử chiều ngược lại (`hashCode` bằng nhau suy ra `equals`) là **sai** và không nên viết.

## 6. Checklist chẩn đoán khi collection hoạt động lạ

| Hiện tượng | Kiểm tra đầu tiên | Cách xử lý có định hướng |
| --- | --- | --- |
| `HashSet` giữ hai phần tử tưởng là trùng | `equals` có thật sự override `Object.equals`? Hash của hai đối tượng bằng nhau khi `equals` đúng? | Sửa quan hệ bằng nhau và hàm hash; dựng lại set sau khi sửa |
| `HashMap.get`/`remove` không thấy khóa từng chèn | Khóa có bị sửa trường tham gia `equals`/`hashCode` sau `put`? | Dùng khóa bất biến; khôi phục hoặc dựng lại map từ dữ liệu nguồn |
| `TreeSet` bỏ phần tử hoặc `TreeMap` ghi đè giá trị | `compareTo`/`Comparator.compare` có trả `0` cho hai khóa muốn phân biệt? | Thiết kế comparator thể hiện đúng danh tính cần lưu |
| Kết quả sort bất thường hoặc thỉnh thoảng ném `IllegalArgumentException` | Comparator có bắc cầu, phản đối xứng về dấu và nhất quán khi trả `0`? Có tràn số hoặc trạng thái thay đổi? | Dùng phép so sánh an toàn, khóa sắp xếp ổn định, bổ sung kiểm thử bộ ba |
| `HashSet` và `TreeSet` có kích thước khác nhau | `equals` và thứ tự tự nhiên có cùng định nghĩa tương đương? Ví dụ `BigDecimal` | Xác định nhu cầu nghiệp vụ: so theo scale hay chỉ giá trị số |

**Kết luận:** Collection của Java dựa trên hợp đồng do **lớp phần tử/khóa hoặc comparator** cung cấp. Vi phạm hợp đồng làm lộ lỗi ở thao tác tưởng như vô can (`contains`, `get`, `add`, `remove`, `sort`). Cách phòng ngừa là định nghĩa một quan hệ bằng nhau hợp lệ, sinh hash tương thích, giữ khóa ổn định và hiểu rõ tiêu chí tương đương riêng của collection có thứ tự.
