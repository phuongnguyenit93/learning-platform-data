# Thực hành: So sánh HashSet và TreeSet với BigDecimal hoặc Comparator theo một khóa

## 1. Mục tiêu của bài thực hành

Hai tập hợp `HashSet` và `TreeSet` đều triển khai giao diện `Set`: không chứa hai phần tử được coi là trùng nhau theo **quy tắc xác định tính duy nhất** của từng triển khai. Tuy nhiên, chúng có thể cho kết quả khác nhau khi dữ liệu có nhiều cách định nghĩa “bằng nhau”.

Sau bài này, bạn cần có thể:

- Giải thích vì sao `HashSet<BigDecimal>` và `TreeSet<BigDecimal>` có thể giữ **số lượng phần tử khác nhau** với cùng dữ liệu đầu vào.
- Dự đoán `add()`, `contains()` và số lượng phần tử từ `equals()/hashCode()` hoặc `compareTo()/Comparator`.
- Thực hành với `Comparator` chỉ so sánh **một khóa** của đối tượng: hai object khác nhau về các thuộc tính còn lại vẫn có thể bị `TreeSet` coi là một phần tử.
- Phân biệt **định danh theo toàn bộ giá trị đối tượng** và **định danh theo khóa nghiệp vụ**; chọn chiến lược nhất quán cho bài toán thực tế.
- Tránh các lỗi do bất nhất giữa cách sắp xếp và `equals()`, do thay đổi khóa trong tập hợp và do giả định thứ tự của `HashSet`.

Bài tập thuộc chủ đề **Java core – object-contract**, nhấn mạnh hợp đồng `equals`/`hashCode` và quan hệ của chúng với thứ tự so sánh. Không cần hệ cơ sở dữ liệu, framework hay thư viện bên ngoài.

## 2. Điểm khác biệt cốt lõi: “trùng nhau” được quyết định ở đâu?

| Thuộc tính | `HashSet<E>` | `TreeSet<E>` |
| --- | --- | --- |
| Cấu trúc bên dưới | `HashMap` dựa trên hash | Cấu trúc cây có thứ tự dựa trên `TreeMap` |
| Cách xác định phần tử trùng | `equals()`, với `hashCode()` phù hợp để tìm vị trí | Kết quả `compareTo() == 0` hoặc `Comparator.compare(a, b) == 0` |
| Thứ tự duyệt | Không bảo đảm thứ tự | Theo natural ordering hoặc comparator |
| Chi phí tìm/thêm/xóa điển hình | Trung bình O(1) nếu băm tốt; trường hợp xấu có thể cao hơn | O(log n) |
| Cho phép `null` | Có thể lưu một `null` | Natural ordering không nhận `null`; comparator tùy định nghĩa |
| Ràng buộc quan trọng | Hai object `equals()==true` phải có `hashCode()` bằng nhau | Thứ tự so sánh nên nhất quán với `equals()` nếu muốn tuân thủ đầy đủ hợp đồng `Set` |

**`HashSet`:** về ý nghĩa, trước hết một phần tử mới phải có `hashCode()` giúp tìm vị trí thích hợp; nếu có phần tử khác bằng nhau theo `equals()`, thao tác `add()` không đưa thêm một phần tử duy nhất mới vào tập hợp. Không nên hiểu là “chỉ cần cùng hash là trùng”: **hash collision không đồng nghĩa equals**.

**`TreeSet`:** việc thêm, tìm kiếm và xóa dựa vào phép so sánh. Kết quả **0** là “tương đương cho tập hợp có thứ tự” dù `equals()` của hai object trả về `false`. Comparator làm việc theo một khóa có thể biến nhiều đối tượng khác nhau thành cùng một lớp tương đương.

Trong ví dụ bất kỳ: nếu `compare(a,b) == 0` nhưng `!a.equals(b)`, `TreeSet` có thể giữ một trong hai, còn `HashSet` vẫn giữ cả hai (giả sử hashCode/equals của chúng đúng hợp đồng).

### Kết quả boolean của `add()` có ý nghĩa gì?

`set.add(element)` trả về `true` nếu tập hợp thay đổi do thêm phần tử mới, hoặc `false` nếu phần tử đã được coi là tồn tại. Với `TreeSet`, `false` có thể có nghĩa “**đã có phần tử cùng khóa so sánh**”, không phải “đã có đúng object có mọi thuộc tính giống nhau”.

`TreeSet` không tự ghi đè object cũ bằng object mới khi comparator trả về 0. Theo luồng thêm lần lượt, phần tử được giữ là phần tử của lần thêm thành công trước đó, trừ khi bạn chủ động xóa/thay thế.

## 3. BigDecimal: bằng nhau về số học khác bằng nhau theo equals()

`BigDecimal` vừa triển khai `Comparable<BigDecimal>` vừa có `equals()` và `hashCode()` của riêng nó. Với `BigDecimal`, phần **scale** (số chữ số thập phân biểu diễn) là yếu tố quan trọng.

Hai số sau có giá trị số học bằng nhau:

~~~java
BigDecimal a = new BigDecimal("2.0");  // unscaled=20, scale=1
BigDecimal b = new BigDecimal("2.00"); // unscaled=200, scale=2
~~~

Tuy nhiên:

- `a.equals(b)` là **false** vì cả giá trị và scale phải phù hợp theo quy tắc `BigDecimal.equals()`.
- `a.compareTo(b)` là **0** vì thứ tự tự nhiên của `BigDecimal` so sánh **giá trị số học**; hai dạng biểu diễn cùng một giá trị có thể tương đương.
- `HashSet` coi hai đối tượng trên **khác nhau** theo `equals()`.
- `TreeSet` dùng natural ordering của `BigDecimal` nên coi hai đối tượng là **cùng một phần tử theo thứ tự so sánh**.

Đây là một ngoại lệ được công bố trong tài liệu Java: natural ordering của `BigDecimal` **không nhất quán với equals**. Không có lỗi trong Java hay trong hai tập hợp; vấn đề là hai định nghĩa tính duy nhất khác nhau.

## 4. Chương trình Java 17 chạy được: so sánh cả hai tình huống

Chương trình dưới đây gồm hai phần:

1. Thêm `BigDecimal("2.0")` và `BigDecimal("2.00")` vào cả `HashSet` và `TreeSet`.
2. Thêm hai `Product` cùng `sku` nhưng khác `name`; thử `TreeSet` chỉ so sánh `sku` và một comparator có khóa phụ `name`.

Lưu **toàn bộ** chương trình vào file **SetComparisonDemo.java**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class SetComparisonDemo {

    record Product(String sku, String name) { }

    public static void main(String[] args) {
        compareBigDecimals();
        compareProducts();
    }

    private static void compareBigDecimals() {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        Set<BigDecimal> hash = new HashSet<>();
        Set<BigDecimal> tree = new TreeSet<>();

        System.out.println("=== BigDecimal ===");
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.compareTo(b): " + a.compareTo(b));

        System.out.println("HashSet add(a): " + hash.add(a));
        System.out.println("HashSet add(b): " + hash.add(b));
        System.out.println("TreeSet add(a): " + tree.add(a));
        System.out.println("TreeSet add(b): " + tree.add(b));

        System.out.println("HashSet size: " + hash.size());
        System.out.println("TreeSet size: " + tree.size());
        System.out.println("TreeSet values: " + tree);
    }

    private static void compareProducts() {
        Product a = new Product("SKU-1", "Notebook");
        Product b = new Product("SKU-1", "Notebook Pro");

        Set<Product> hash = new HashSet<>();
        Set<Product> treeBySku =
                new TreeSet<>(Comparator.comparing(Product::sku));
        Set<Product> treeBySkuAndName = new TreeSet<>(
                Comparator.comparing(Product::sku)
                        .thenComparing(Product::name));

        System.out.println("=== Product ===");
        System.out.println("a.equals(b): " + a.equals(b));

        hash.add(a);
        hash.add(b);
        System.out.println("HashSet size: " + hash.size());

        System.out.println("TreeSet by SKU add(a): " + treeBySku.add(a));
        System.out.println("TreeSet by SKU add(b): " + treeBySku.add(b));
        System.out.println("TreeSet by SKU size: " + treeBySku.size());
        System.out.println("TreeSet by SKU first: "
                + ((TreeSet<Product>) treeBySku).first());
        System.out.println("TreeSet by SKU contains(b): "
                + treeBySku.contains(b));

        treeBySkuAndName.add(a);
        treeBySkuAndName.add(b);
        System.out.println("TreeSet by SKU+name size: "
                + treeBySkuAndName.size());
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 SetComparisonDemo.java
java SetComparisonDemo
~~~

Đầu ra dự kiến (không in trực tiếp `HashSet` vì thứ tự duyệt của nó không được bảo đảm):

~~~text
=== BigDecimal ===
a.equals(b): false
a.compareTo(b): 0
HashSet add(a): true
HashSet add(b): true
TreeSet add(a): true
TreeSet add(b): false
HashSet size: 2
TreeSet size: 1
TreeSet values: [2.0]
=== Product ===
a.equals(b): false
HashSet size: 2
TreeSet by SKU add(a): true
TreeSet by SKU add(b): false
TreeSet by SKU size: 1
TreeSet by SKU first: Product[sku=SKU-1, name=Notebook]
TreeSet by SKU contains(b): true
TreeSet by SKU+name size: 2
~~~

### Đọc kết quả `BigDecimal`

- `HashSet add(b): true`: hai số khác scale nên không bằng nhau theo `BigDecimal.equals()`. `HashSet` tăng lên 2 phần tử.
- `TreeSet add(b): false`: `b.compareTo(a) == 0`; cây đã có một phần tử tương đương theo thứ tự tự nhiên.
- `TreeSet values: [2.0]`: tập giữ object đầu tiên (`a`) đã thêm thành công. Nếu đảo thứ tự thêm `b` rồi `a`, phần tử đại diện có thể hiển thị `2.00`.
- Không dùng khác biệt kích thước trên để kết luận một tập hợp “đúng” còn tập hợp kia “sai”. Phải xem yêu cầu nghiệp vụ coi scale có quan trọng hay không.

### Đọc kết quả `Product`

`record Product(String sku, String name)` tự sinh `equals()` và `hashCode()` xét **cả hai thành phần**. Vì `name` khác nhau, `a.equals(b) == false`, nên `HashSet` giữ cả hai.

Comparator `Comparator.comparing(Product::sku)` lại chỉ xem `sku`. Hai sản phẩm cùng SKU có `compare(a,b) == 0` dù tên khác. Vì vậy `TreeSet` theo SKU chỉ giữ bản ghi thêm trước; `contains(b)` có thể trả về **true** ngay cả khi object `b` chưa từng được giữ làm phần tử trong cây. `contains()` hỏi có **phần tử cùng lớp so sánh** hay không.

Khi thêm `thenComparing(Product::name)`, tên trở thành khóa phụ; hai sản phẩm có cùng SKU nhưng tên khác sẽ được sắp thành hai vị trí, nên kích thước là 2.

**Lưu ý phạm vi:** Comparator theo SKU+name phù hợp với `equals()` do record này chỉ gồm hai trường `String` không null và hai kiểu chuỗi dùng thứ tự tự nhiên nhất quán với equals. Nếu record có thêm trường thuộc hợp đồng equals, comparator chỉ theo SKU+name **không còn chắc** nhất quán với equals.

## 5. Thực hành có chủ đích: dự đoán trước khi chạy

### Bài 1 — nhiều cách biểu diễn của cùng một số

Cho:

~~~java
BigDecimal x = new BigDecimal("10.0");
BigDecimal y = new BigDecimal("10.00");
BigDecimal z = new BigDecimal("9.0");
~~~

Nếu thêm lần lượt `x, y, z` vào hai tập hợp trống:

| Kiểm tra | `HashSet<BigDecimal>` | `TreeSet<BigDecimal>` |
| --- | --- | --- |
| Thêm `x` | `true` | `true` |
| Thêm `y` | `true` | `false` |
| Thêm `z` | `true` | `true` |
| Kích thước | 3 | 2 |
| Thứ tự duyệt | Không cam kết | Tăng dần về giá trị số học |

**Tại sao?** `x.equals(y) == false` nhưng `x.compareTo(y) == 0`; còn `z` có giá trị nhỏ hơn và khác cả hai theo mọi tiêu chí trên.

### Bài 2 — comparator chỉ xét một khóa

Xét các bản ghi:

~~~java
record Employee(String departmentId, String fullName) { }

Employee first = new Employee("D01", "An");
Employee second = new Employee("D01", "Binh");

Set<Employee> staff = new TreeSet<>(
        Comparator.comparing(Employee::departmentId));
~~~

Nếu thêm `first` rồi `second`:

- `staff.size()` là **1**, vì comparator chỉ xét `departmentId`.
- Phần tử còn lại mang tên **An**, vì `first` được thêm trước.
- `staff.contains(second)` trả về **true** theo comparator, mặc dù `second` không được lưu làm object đại diện.

**Câu hỏi:** Nếu yêu cầu là “không có hai nhân viên cùng phòng ban”, đã đủ chưa?

Về tập khóa, comparator đáp ứng phép loại trùng theo department ID. Nhưng về **mô hình nghiệp vụ**, giữ chỉ một nhân viên cho mỗi phòng có thể làm mất dữ liệu và không mô tả đúng quan hệ giữa phòng ban và nhân viên. Nên cân nhắc `Map<String, Employee>` nếu thật sự chỉ có một người đại diện cho mỗi mã phòng, hoặc `Map<String, List<Employee>>` nếu mỗi phòng có nhiều người. Comparator không thể tự quyết định chính sách mất dữ liệu là đúng.

## 6. Chọn tiêu chí đồng nhất theo mục đích nghiệp vụ

Trước khi chọn `HashSet`, `TreeSet` hay `Map`, cần xác định **đơn vị duy nhất**.

### Trường hợp A — phân biệt cả biểu diễn thập phân

Ví dụ hệ thống kiểm tra dữ liệu đầu vào muốn phân biệt người dùng nhập `2.0` với `2.00` để giữ độ chính xác hiển thị hoặc scale theo quy tắc dữ liệu. `HashSet<BigDecimal>` phù hợp hơn nếu muốn phản ánh trực tiếp `equals` của `BigDecimal`; nhớ rằng “phù hợp” ở đây là vì **định nghĩa danh tính bao gồm scale**.

### Trường hợp B — cùng giá trị số học phải được coi là trùng

Nếu `2.0` và `2.00` phải đại diện cho cùng một giá trị:

- `TreeSet<BigDecimal>` theo natural ordering loại trùng dựa trên `compareTo() == 0` và đồng thời sắp xếp số học.
- Nếu cần cấu trúc hash, có thể **chuẩn hóa** giá trị trước khi thêm, ví dụ `value.stripTrailingZeros()` (với chính sách chuẩn hóa được áp dụng thống nhất). Các biểu diễn `2.0` và `2.00` sau chuẩn hóa trở nên `equals() == true`.

Đoạn minh họa trong phương thức Java có `import java.math.BigDecimal`, `import java.util.Set` và `import java.util.HashSet`:

~~~java
Set<BigDecimal> canonical = new HashSet<>();
canonical.add(new BigDecimal("2.0").stripTrailingZeros());
canonical.add(new BigDecimal("2.00").stripTrailingZeros());
System.out.println(canonical.size()); // 1
~~~

Cẩn thận: `stripTrailingZeros()` có thể đổi scale thành **số âm** và đổi cách hiển thị của một số, ví dụ một số nguyên lớn có các chữ số 0 cuối. Nếu định dạng xuất dữ liệu là yêu cầu nghiệp vụ, không được chỉ dựa vào `toString()` của bản đã chuẩn hóa; cần tách giá trị số học và định dạng hiển thị.

### Trường hợp C — tiền tệ có scale cố định

Nếu dữ liệu tiền luôn phải có đúng hai chữ số thập phân, có thể định nghĩa chính sách chuyển về scale 2:

~~~java
BigDecimal amount = new BigDecimal("2.0")
        .setScale(2, java.math.RoundingMode.UNNECESSARY);
System.out.println(amount.toPlainString()); // 2.00
~~~

Dùng `RoundingMode.UNNECESSARY` sẽ ném `ArithmeticException` nếu phải làm tròn để đạt scale yêu cầu. Trong ứng dụng thật, chính sách làm tròn cần được xác định theo loại tiền, quy tắc nghiệp vụ và nguồn dữ liệu. **Không tự làm tròn im lặng** chỉ để khớp khóa.

### Trường hợp D — chỉ duy nhất theo mã nghiệp vụ

Nếu dữ liệu có `id` hoặc `sku` làm khóa duy nhất, `TreeSet<>(Comparator.comparing(Entity::id))` có thể đảm bảo một đại diện cho mỗi khóa, đồng thời sắp tăng theo khóa. Nhưng quan hệ này có thể **không nhất quán với `equals()` của Entity**.

Một `Map<Key, Value>` thường thể hiện ý nghĩa “mỗi khóa có một giá trị” rõ ràng hơn. Ví dụ:

~~~java
Map<String, String> latestNameBySku = new java.util.HashMap<>();
latestNameBySku.put("SKU-1", "Notebook");
latestNameBySku.put("SKU-1", "Notebook Pro");
System.out.println(latestNameBySku.get("SKU-1")); // Notebook Pro
~~~

Trong một phương thức Java, đoạn này cần `import java.util.Map`; `put` đã chủ động chọn chính sách ghi đè giá trị trước bằng giá trị sau. Nếu **không** muốn ghi đè, dùng `putIfAbsent` hoặc xử lý xung đột một cách tường minh.

## 7. “Comparator nhất quán với equals” nghĩa là gì?

Một thứ tự được gọi là **consistent with equals** khi với mọi `a, b` hợp lệ, điều kiện `compare(a,b) == 0` tương đương với `a.equals(b) == true`.

Trong bài này có hai ví dụ **không** thỏa mãn:

- `BigDecimal("2.0")` và `BigDecimal("2.00")`: `compareTo == 0` nhưng `equals == false`.
- Hai `Product` cùng SKU, khác tên: comparator theo SKU trả 0 nhưng record equals trả false.

Theo hợp đồng `SortedSet`/`Set`, thứ tự của sorted set nên nhất quán với equals nếu muốn sorted set tuân thủ **đầy đủ** hợp đồng chung của `Set`. `TreeSet` vẫn hoạt động xác định khi comparator không nhất quán; nhưng một số thao tác kiểm tra bằng nhau giữa các tập hợp, `contains` hay luồng xử lý kết hợp `HashSet` và `TreeSet` có thể khiến người dùng bất ngờ. Đừng giả định hai tập hợp trên có thể thay thế cho nhau ở mọi vị trí chỉ vì cả hai đều là `Set`.

Không cố sửa `BigDecimal.equals()` (đây là kiểu thư viện bất biến). Nếu cần chính sách so sánh khác, áp dụng chiến lược chuẩn hóa, wrapper/domain value object hoặc collection phù hợp.

### Comparator có khóa phụ để tránh mất dữ liệu ngoài ý muốn

Khi muốn tất cả bản ghi được giữ nếu khác nhau ở các trường có ý nghĩa, hãy bổ sung khóa phụ bằng `thenComparing()`:

~~~java
Comparator<Product> bySkuThenName =
        Comparator.comparing(Product::sku)
                .thenComparing(Product::name);
~~~

Đoạn này sử dụng `Product` đã định nghĩa ở chương trình chính và `import java.util.Comparator`.

Nhưng tránh bổ sung khóa phụ chỉ để “không còn trùng” một cách máy móc: nếu chính sách muốn **một sản phẩm trên một SKU**, khóa phụ `name` sẽ làm thay đổi quy tắc nghiệp vụ và có thể không còn đáp ứng yêu cầu.

## 8. Tác động của equals/hashCode tới HashSet

Đối tượng đưa vào `HashSet` phải tuân thủ hợp đồng:

1. `equals` phản xạ, đối xứng, bắc cầu và nhất quán trong lúc các thuộc tính dùng để so sánh không đổi.
2. Nếu `a.equals(b)` là `true`, `a.hashCode() == b.hashCode()` bắt buộc đúng.
3. Hai đối tượng **không bằng nhau** vẫn có thể trùng mã hash; `HashSet` tiếp tục dùng `equals()` khi cần.
4. Khi override `equals()`, hầu như luôn cần override `hashCode()` để duy trì hợp đồng.

Record tạo `equals()/hashCode()` theo các thành phần một cách tự động, nên ví dụ `Product` đã có hợp đồng đồng nhất theo `sku` **và** `name`. Tuy nhiên record có thể chứa thành phần mutable; đừng tự động cho rằng mọi record đều bất biến sâu.

Nếu muốn danh tính của `Product` chỉ dựa vào SKU trong **mọi** cấu trúc, hãy thiết kế một lớp/value object có `equals/hashCode` phù hợp với chính sách đó; không chỉ thay `Comparator` ở một điểm dùng `TreeSet`.

## 9. Tránh thay đổi khóa khi phần tử đang nằm trong Set

Đây là lỗi nguy hiểm với cả hai triển khai, đặc biệt khi đối tượng có trường mutable:

- Với `HashSet`, thay đổi trường tham gia `hashCode()/equals()` có thể làm đối tượng rơi vào bucket không khớp khi tra cứu, khiến `contains()/remove()` không hoạt động như mong đợi.
- Với `TreeSet`, thay đổi trường mà comparator dùng để xếp thứ tự có thể phá cấu trúc thứ tự của cây; tìm kiếm hoặc thêm mới có thể cho kết quả khó hiểu.
- Sửa trường không ảnh hưởng đến equality/comparator có thể vẫn an toàn về tính duy nhất và thứ tự, nhưng cần xét bất biến nghiệp vụ và đồng thời.

**Nguyên tắc:** dùng khóa bất biến cho phần tử trong tập hợp; nếu bắt buộc đổi khóa, nên **remove trước khi sửa, rồi add lại** theo một luồng xử lý có kiểm soát, hoặc sử dụng mô hình dữ liệu khác phù hợp. Không nên thay đổi khóa lén lút qua tham chiếu bên ngoài khi phần tử vẫn đang nằm trong collection.

## 10. Một số khác biệt và giới hạn cần quan sát

### Thứ tự và hiệu năng

`HashSet` không đảm bảo thứ tự duyệt, kể cả khi chạy chương trình nhiều lần có vẻ cho ra một thứ tự ổn định. Không viết test kiểm tra chuỗi in trực tiếp của `HashSet` theo một thứ tự cụ thể.

`TreeSet` cung cấp các thao tác có thứ tự từ `NavigableSet` như `first()`, `last()`, `lower()`, `floor()`, `ceiling()`, `higher()`. Chúng dựa trên comparator hoặc natural ordering; nếu comparator chỉ xét SKU, tất cả hành vi tìm phần tử gần nhất cũng là theo SKU.

`HashSet` thường có thao tác cơ bản trung bình O(1) khi phân phối hash tốt; `TreeSet` là O(log n). Tính duy nhất đúng với yêu cầu và độ ổn định của khóa quan trọng hơn chọn cấu trúc chỉ theo tốc độ.

### Comparator và null

`TreeSet` với natural ordering thường không chấp nhận `null`. Comparator tự định nghĩa có thể xử lý null bằng `Comparator.nullsFirst(...)` hoặc `nullsLast(...)` theo chính sách; tuy nhiên dữ liệu nullable cũng cần được kiểm soát để tránh comparator không xác định. `HashSet` có thể chứa đúng một giá trị `null`.

### Lỗi ClassCastException, so sánh thiếu tính bắc cầu

Nếu đối tượng không triển khai `Comparable` và bạn tạo `new TreeSet<>()` không truyền comparator, thao tác thêm phần tử có thể ném `ClassCastException`. Tương tự, comparator không chấp nhận kiểu được cung cấp cũng gây lỗi so sánh.

Comparator nên xác định thứ tự hợp lệ, nhất quán, đặc biệt về phản xạ, đối xứng dấu và tính bắc cầu theo hợp đồng `Comparator`. Một comparator không bắc cầu có thể làm cấu trúc sắp xếp vận hành không đúng kỳ vọng. Tránh comparator kiểu `return a.someInt - b.someInt;` vì có nguy cơ tràn số nguyên; ưu tiên `Comparator.comparingInt(...)` hoặc `Integer.compare(...)`.

### BigDecimal và giá trị double

Để nhập giá trị thập phân chính xác theo chuỗi, dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` theo nhu cầu; cẩn thận với `new BigDecimal(0.1)` vì chuyển trực tiếp từ biểu diễn nhị phân của `double` có thể tạo giá trị thập phân dài không như người nhập kỳ vọng. Điều này là vấn đề biểu diễn số, **khác** vấn đề equals/compareTo và scale nhưng dễ khiến bài thực hành thêm khó hiểu nếu nhập sai dữ liệu.

## 11. Bảng lỗi thực hành và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách giải quyết |
| --- | --- | --- |
| `HashSet<BigDecimal>` có 2, `TreeSet<BigDecimal>` có 1 | `equals` xét scale, `compareTo` xét giá trị số học | Chọn rõ định nghĩa trùng và áp dụng nhất quán |
| `TreeSet<Product>` mất phần tử khác tên | Comparator chỉ xét SKU | Nếu cần giữ cả hai, thêm khóa phụ; nếu cần duy nhất theo SKU, mô tả chính sách rõ |
| `tree.contains(b) == true` dù object `b` không được lưu | Có phần tử khác được comparator coi tương đương | Hiểu `contains` theo lớp so sánh, không theo object identity |
| So sánh kết quả in `HashSet` bị fail ngẫu nhiên | Không có thứ tự duyệt cam kết | Chỉ assert kích thước/membership hoặc chủ động sắp trước khi in |
| `HashSet` không tìm được object sau khi đổi ID | Thay đổi trường dùng trong equals/hashCode | Khóa bất biến hoặc remove-sửa-add có kiểm soát |
| `TreeSet` tìm sai sau khi đổi khóa sắp xếp | Cây không tự tái sắp xếp sau đột biến | Tránh sửa khóa khi object còn trong tập |
| `TreeSet` ném `ClassCastException` | Thiếu natural ordering/comparator phù hợp | Cung cấp Comparator đúng kiểu |
| Chuẩn hóa `BigDecimal` làm hiển thị khác | `stripTrailingZeros` có thể đổi scale | Tách chính sách giá trị và định dạng hiển thị |

## 12. Checklist kiểm tra một bài toán Set

Khi cần loại phần tử trùng, hãy trả lời theo đúng thứ tự:

1. **“Trùng” có nghĩa gì?** Trùng mọi trường, trùng ID, trùng giá trị số học hay trùng biểu diễn thập phân?
2. **Hợp đồng equals/hashCode là gì?** Hai phần tử nào được coi là bằng nhau theo object?
3. **Comparator hoặc compareTo xét gì?** Khi nào so sánh trả về 0?
4. **Hai quy tắc có nhất quán không?** Nếu không, liệu ứng dụng có chấp nhận sự khác biệt ở `add()`/`contains()`/kết hợp collection?
5. **Có cần thứ tự sắp xếp không?** Nếu không, `HashSet` có thể đơn giản hơn; nếu có, `TreeSet` là lựa chọn nhưng phải chốt comparator.
6. **Khóa có bất biến trong thời gian nằm trong Set không?** Nếu không, cần thiết kế lại cách cập nhật.
7. **Cần một đại diện cho mỗi khóa hay cần giữ toàn bộ bản ghi?** Với một giá trị trên một khóa, `Map<K,V>` thường diễn đạt ý định rõ hơn.

### Tự trả lời

- `HashSet` có dùng `compareTo()` của `BigDecimal` để quyết định trùng không? **Không**.
- `TreeSet` có luôn gọi `equals()` để quyết định trùng không? **Không**; nó dựa vào phép so sánh.
- `BigDecimal("2.0").compareTo(BigDecimal("2.00")) == 0` có suy ra `equals() == true` không? **Không**.
- Nếu comparator chỉ xét `sku`, thêm hai bản ghi cùng SKU nhưng khác tên có giữ cả hai không? **Không**; phần tử được thêm sau bị coi là trùng.
- Nếu thêm khóa phụ `name` thì đã luôn nhất quán với `equals()` chưa? **Chỉ khi** các trường so sánh đủ bao quát hợp đồng `equals` và comparator của từng thành phần nhất quán với equals.

**Kết luận kiến thức:** `HashSet` và `TreeSet` khác nhau ở **hợp đồng xác định tính duy nhất**, không chỉ ở thứ tự hay hiệu năng. Với `BigDecimal` hoặc comparator theo một khóa, hãy xác định trước “bằng nhau” là theo biểu diễn, giá trị số học hay khóa nghiệp vụ. Khi chính sách ấy rõ ràng, thao tác `add()`, `contains()`, kích thước và cách bảo toàn dữ liệu sẽ dự đoán được.

## Tài liệu chính thức để tra cứu

- [Java SE 21 — HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html)
- [Java SE 21 — TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html)
- [Java SE 21 — SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html)
- [Java SE 21 — Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html)
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)