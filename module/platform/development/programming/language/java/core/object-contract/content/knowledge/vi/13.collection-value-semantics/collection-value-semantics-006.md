# Tập hợp lồng nhau phụ thuộc `equals()` của từng phần tử

Trong Java, hai collection có cùng **nội dung logic** hay không phụ thuộc trước hết vào quy tắc `equals(Object)` của loại collection ở **từng tầng lồng nhau**, sau đó đến `equals()` của các phần tử cuối cùng. Collection **không tự suy đoán** rằng hai đối tượng cùng một vài thuộc tính, hai mảng có cùng nội dung, hoặc hai danh sách giống nhau nhưng đảo thứ tự phải được coi là bằng nhau.

Ví dụ với kiểu `List<Set<Product>>`:

- Tầng ngoài là `List`: thứ tự **các tập hợp con** có ý nghĩa.
- Mỗi tầng trong là `Set`: thứ tự liệt kê **sản phẩm trong một tập hợp** không có ý nghĩa.
- Mỗi phần tử là `Product`: một cặp sản phẩm có bằng nhau hay không tùy cách lớp `Product` ghi đè `equals(Object)`.
- Nếu các tầng dùng hash (`HashSet` hoặc `HashMap`), cách tính `hashCode()` của phần tử cũng phải nhất quán với `equals()`.

**Ý chính:** `equals()` của collection không thay thế việc thiết kế đúng phép bằng nhau của kiểu phần tử; nó sử dụng phép bằng nhau đã được các kiểu bên trong cung cấp.

## 1. Quy tắc bằng nhau của các collection phổ biến

| Kiểu | Điều kiện hai collection bằng nhau | Thứ tự có ý nghĩa? | Điều quan trọng ở tầng con |
| --- | --- | --- | --- |
| `List<E>` | Cùng số phần tử và từng vị trí tương ứng bằng nhau | **Có** | So sánh phần tử theo `equals()` |
| `Set<E>` | Cùng số phần tử và mỗi phần tử của một set có phần tử bằng nó trong set kia | **Không** | `equals()` định nghĩa trùng phần tử; `hashCode()` phải tương thích với hash set |
| `Map<K,V>` | Cùng tập ánh xạ khóa → giá trị | **Không** phụ thuộc thứ tự chèn | Khóa dùng `equals()/hashCode()` phù hợp; giá trị được so sánh theo `equals()` |
| `Collection<E>` nói chung | Không có một quy tắc `equals()` chung cho mọi implementation | Tùy loại cụ thể | Không tự giả định mọi collection được so theo cùng tiêu chí |

Các hợp đồng của `List`, `Set` và `Map` được định nghĩa trên interface tương ứng; ví dụ một `ArrayList` và một `List.of(...)` có thể bằng nhau nếu thứ tự, kích thước và phần tử tương ứng bằng nhau. Ngược lại, một `List` không trở thành bằng một `Set` chỉ vì chứa các giá trị nhìn giống nhau. `Collection` chỉ là giao diện chung, không áp một phép so giá trị thống nhất lên mọi implementation.

### Ví dụ suy luận từng tầng

Giả sử:

~~~java
List<Set<String>> left = List.of(
    Set.of("A", "B"),
    Set.of("C")
);
List<Set<String>> right = List.of(
    Set.of("B", "A"),
    Set.of("C")
);
~~~

`left.equals(right)` là `true`: hai `List` có hai vị trí tương ứng, trong đó `Set.of("A", "B")` bằng `Set.of("B", "A")` vì set không tính thứ tự.

Nếu hoán đổi **vị trí hai set** của `right` thành `List.of(Set.of("C"), Set.of("A", "B"))`, kết quả sẽ là `false` vì list ngoài có thứ tự.

Nếu tầng ngoài là `Set<List<String>>`, thứ tự của các **list thành viên** không quan trọng, nhưng thứ tự các chuỗi **bên trong mỗi list** vẫn quan trọng:

~~~java
Set<List<String>> a = Set.of(List.of("A", "B"), List.of("C"));
Set<List<String>> b = Set.of(List.of("C"), List.of("A", "B"));
Set<List<String>> c = Set.of(List.of("C"), List.of("B", "A"));

// a.equals(b) == true; a.equals(c) == false.
~~~

Những kết luận trên xuất phát từ hợp đồng của từng tầng, chứ không phải từ việc Java sử dụng một cơ chế “so sánh sâu” riêng biệt.

## 2. Tầng cuối phụ thuộc vào `equals()` của đối tượng

Giả sử `Product` có hai trường:

- `sku`: mã sản phẩm duy nhất theo nghiệp vụ, cố định trong vòng đời đối tượng.
- `displayName`: tên trình bày; hai bản ghi cùng `sku` có thể dùng tên khác nhau nhưng vẫn biểu diễn **cùng sản phẩm**.

Nếu định nghĩa bằng nhau của sản phẩm là “cùng SKU” thì hai bản thể hiện `new Product("P-1", "Bút")` và `new Product("P-1", "Pen")` phải được `Product.equals()` coi là bằng nhau. Khi chúng xuất hiện trong hai list hoặc set tương ứng, collection cũng phải tính chúng như những phần tử bằng nhau.

Đây là cách cài đặt **một quy tắc nghiệp vụ cụ thể**, không phải mặc định cho mọi lớp: với kiểu giá trị khác, tên hoặc những thuộc tính khác có thể là một phần của định nghĩa bằng nhau. Nếu `Product` **không ghi đè `equals()`**, nó sẽ thừa kế `Object.equals()`, vốn so đồng nhất tham chiếu; hai instance được tạo bằng hai lệnh `new` khác nhau thường không bằng nhau dù trường `sku` giống hệt.

Một lớp tự định nghĩa `equals()` cần đồng thời ghi đè `hashCode()`: nếu `a.equals(b)` đúng, `a.hashCode() == b.hashCode()` phải đúng. Điều này đặc biệt quan trọng vì tầng `Set` hoặc khóa `Map` có thể dùng hash ngay cả khi tầng ngoài là `List`.

## 3. Ví dụ Java 17 chạy được: `List<Set<T>>`, `Set<List<T>>` và `Map<String,List<T>>`

Tạo tệp **`NestedCollectionEqualityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class NestedCollectionEqualityDemo {

    static final class Product {
        private final String sku;
        private final String displayName;

        Product(String sku, String displayName) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Product other)) {
                return false;
            }
            return sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    public static void main(String[] args) {
        List<Set<Product>> groupsA = List.of(
            Set.of(new Product("A", "Pen"), new Product("B", "Pencil")),
            Set.of(new Product("C", "Book"))
        );

        List<Set<Product>> groupsB = List.of(
            Set.of(new Product("B", "New name"), new Product("A", "Other name")),
            Set.of(new Product("C", "Renamed"))
        );

        List<Set<Product>> reversedGroups = List.of(
            Set.of(new Product("C", "Book")),
            Set.of(new Product("A", "Pen"), new Product("B", "Pencil"))
        );

        System.out.println("list of sets equal: "
            + groupsA.equals(groupsB));
        System.out.println("list of sets same hash: "
            + (groupsA.hashCode() == groupsB.hashCode()));
        System.out.println("outer list order matters: "
            + groupsA.equals(reversedGroups));

        Set<List<Product>> listsA = Set.of(
            List.of(new Product("A", "Pen"), new Product("B", "Pencil")),
            List.of(new Product("C", "Book"))
        );
        Set<List<Product>> listsB = Set.of(
            List.of(new Product("C", "New")),
            List.of(new Product("A", "Different"), new Product("B", "Different"))
        );
        Set<List<Product>> changedInnerOrder = Set.of(
            List.of(new Product("C", "Book")),
            List.of(new Product("B", "Pencil"), new Product("A", "Pen"))
        );

        System.out.println("set of lists equal: "
            + listsA.equals(listsB));
        System.out.println("inner list order matters: "
            + listsA.equals(changedInnerOrder));

        Map<String, List<Product>> mapA = new LinkedHashMap<>();
        mapA.put("front", List.of(
            new Product("A", "Pen"), new Product("B", "Pencil")));
        mapA.put("back", List.of(new Product("C", "Book")));

        Map<String, List<Product>> mapB = new LinkedHashMap<>();
        mapB.put("back", List.of(new Product("C", "Renamed")));
        mapB.put("front", List.of(
            new Product("A", "Another name"),
            new Product("B", "Another name")));

        Map<String, List<Product>> mapC = new LinkedHashMap<>(mapB);
        mapC.put("front", List.of(
            new Product("B", "Pencil"), new Product("A", "Pen")));

        System.out.println("map insertion order irrelevant: "
            + mapA.equals(mapB));
        System.out.println("map value list order matters: "
            + mapA.equals(mapC));

        List<int[]> arraysA = List.of(new int[] {1, 2});
        List<int[]> arraysB = List.of(new int[] {1, 2});
        System.out.println("array elements equal by content: "
            + arraysA.equals(arraysB));
        System.out.println("nested value lists equal: "
            + List.of(List.of(1, 2)).equals(List.of(List.of(1, 2))));

        List<String> inner = new ArrayList<>(List.of("A"));
        List<List<String>> outer = List.of(inner);
        Set<List<List<String>>> indexed = new HashSet<>();
        indexed.add(outer);
        int before = outer.hashCode();
        inner.add("B");
        System.out.println("nested hash changed after mutation: "
            + (before != outer.hashCode()));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac NestedCollectionEqualityDemo.java
java NestedCollectionEqualityDemo
~~~

**Đầu ra chuẩn:**

~~~text
list of sets equal: true
list of sets same hash: true
outer list order matters: false
set of lists equal: true
inner list order matters: false
map insertion order irrelevant: true
map value list order matters: false
array elements equal by content: false
nested value lists equal: true
nested hash changed after mutation: true
~~~

Giải thích từng nhóm kết quả:

1. Hai `groupsA` và `groupsB` bằng nhau vì từng set ở cùng vị trí chứa các SKU tương đương; thứ tự khai báo bên trong set và `displayName` khác nhau không làm thay đổi kết quả.
2. Khi toàn bộ hai list bằng nhau theo hợp đồng, hash của chúng cũng phải bằng nhau. `List.hashCode()` dựa vào hash của các phần tử, trong ví dụ là các `Set<Product>`.
3. `reversedGroups` đổi thứ tự **hai set trong list ngoài** nên không bằng `groupsA`.
4. `listsA` và `listsB` đều là set chứa hai list bằng nhau; đảo thứ tự liệt kê **hai list trong set ngoài** không ảnh hưởng. Nhưng đổi vị trí `A` và `B` **bên trong một list** làm kết quả thành `false`.
5. Hai `LinkedHashMap` có các entry cùng khóa và các list giá trị tương đương nên bằng nhau, dù được chèn theo thứ tự khác nhau. `mapC` khác `mapA` vì giá trị list của khóa `"front"` đã đảo thứ tự.
6. Hai `int[]` chứa `1, 2` là hai đối tượng mảng khác nhau. Mảng Java không ghi đè `Object.equals()` theo nội dung; `List<int[]>` gọi `equals()` của mảng và cho `false`. Thay mỗi mảng bằng `List<Integer>` cho kết quả bằng nhau theo từng số nguyên.
7. `outer` là một list **không cho sửa cấu trúc trực tiếp**, nhưng nó chứa tham chiếu tới `inner` có thể thay đổi. Khi thêm `"B"` vào `inner`, hash tính qua các tầng của `outer` thay đổi. Việc chèn `outer` vào `HashSet` trước đó tạo ra tình huống nguy hiểm: đường tra cứu theo hash hiện tại có thể không khớp vị trí đã chèn. Ví dụ chỉ in việc hash thay đổi, **không dựa vào một kết quả `contains()` sau khi cấu trúc đã bị làm mất ổn định**.

`displayName` trong `Product` được giữ để làm rõ rằng việc một trường **không thuộc định nghĩa bằng nhau** khác nhau giữa hai instance không làm thay đổi equality của collection.

## 4. `equals()` lan qua các tầng thế nào?

Có thể đọc `List<Set<Product>>` theo sơ đồ:

~~~text
List.equals(otherList)
  ├─ kiểm tra kích thước và vị trí thứ nhất
  │    └─ Set.equals(otherSet)
  │         └─ tìm phần tử tương đương
  │              └─ Product.equals(otherProduct)
  └─ kiểm tra vị trí thứ hai
       └─ Set.equals(otherSet)
            └─ Product.equals(otherProduct)
~~~

Mỗi lớp gọi phương thức bình đẳng theo **hợp đồng của kiểu đối tượng tại tầng đó**. Với `List<List<Product>>`, cả hai tầng list yêu cầu thứ tự. Với `Set<Set<Product>>`, cả hai tầng set bỏ qua thứ tự của các phần tử. Với `Map<Key,List<Set<Product>>>`, map bỏ qua thứ tự entry; value là list nên giữ thứ tự các set; từng set lại không xét thứ tự sản phẩm bên trong.

Điều này dẫn đến hai hệ quả quan trọng:

- **Kiểu chứa khác thì ngữ nghĩa khác:** thay tầng ngoài từ `List` sang `Set` có thể làm mất phân biệt thứ tự, thay một tầng từ `Set` sang `List` có thể khiến thứ tự trở thành một phần của bằng nhau.
- **Kiểu phần tử khác thì ngữ nghĩa khác:** thay `Product` có equality theo SKU bằng một lớp không override `equals()` khiến hai bản thể hiện cùng SKU có thể không còn bằng nhau; đổi cách triển khai `Product.equals()` cũng ảnh hưởng toàn bộ cấu trúc chứa nó.

Không phải mọi đối tượng lồng nhau đều là collection. Nếu phần tử là `LocalDate`, `String`, `BigDecimal`, mảng, một record hay lớp miền, tầng ngoài sử dụng đúng `equals()` do kiểu phần tử đó định nghĩa. Chẳng hạn `BigDecimal("1.0")` và `BigDecimal("1.00")` không bằng nhau theo `BigDecimal.equals()` dù có thể so giá trị số học tương đương bằng `compareTo() == 0`; đặt chúng vào hai list tương ứng **không tự chuyển** sang phép so số học. Hãy chọn và chuẩn hóa kiểu giá trị theo yêu cầu nghiệp vụ trước khi dùng làm phần tử.

## 5. `hashCode()` của cấu trúc lồng nhau phải nhất quán

`List`, `Set` và `Map` đều có quy tắc mã băm gắn với hợp đồng bằng nhau của chúng:

- `List.hashCode()` kết hợp mã băm từng phần tử **theo thứ tự**.
- `Set.hashCode()` lấy tổng mã băm của các phần tử; về bản chất **không phụ thuộc thứ tự**.
- `Map.hashCode()` lấy tổng mã băm của các entry; mỗi entry kết hợp hash của key và value, **không phụ thuộc thứ tự entry**.

Vì thế, một thay đổi ở `hashCode()` của phần tử trong cùng có thể lan ra hash của set, rồi tới list, rồi tới object khác đang chứa list đó.

Giả sử `Product.equals()` chỉ so `sku` nhưng `Product.hashCode()` lại đưa thêm `displayName` vào phép băm. Khi đó, hai `Product` cùng SKU khác tên có thể **bằng nhau nhưng hash khác nhau**. Một `Set<Product>` có thể tra cứu, kiểm tra phần tử trùng và so bằng nhau không còn đúng hợp đồng; hai `List<Set<Product>>` tưởng như cùng giá trị cũng có thể nhận hash khác nhau. Vấn đề bắt nguồn từ `Product` và lan lên collection lồng ngoài.

Cần nhớ điều kiện **một chiều**:

~~~text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
~~~

Chiều ngược lại không bắt buộc: hai phần tử khác nhau được phép trùng hash. Không được dùng `hashCode() == hashCode()` làm bằng chứng rằng hai object hoặc hai collection bằng nhau. Muốn so bằng nhau phải gọi `equals()`.

Với `Map<K,V>`, hash và equality không chỉ phụ thuộc vào key mà còn phụ thuộc vào **value**. Nếu value là collection có thể bị sửa, map nhìn tổng thể có thể đổi `equals()/hashCode()` theo value ngay cả khi các key không đổi. Đây là rủi ro đặc biệt khi chính map (hoặc một collection chứa map) được dùng làm khóa/phần tử trong một cấu trúc hash khác.

## 6. Mảng và null ở tầng phần tử cuối

Một tầng `List` không tự so sâu phần tử `int[]`:

~~~java
List<int[]> a = List.of(new int[] {1, 2});
List<int[]> b = List.of(new int[] {1, 2});
// a.equals(b) == false: hai phần tử là hai mảng riêng.
~~~

Để coi mảng là giá trị, phải chọn cách so sánh theo nội dung (`Arrays.equals`/`Arrays.deepEquals` phù hợp) và một kiểu bọc có `equals/hashCode` tương ứng nếu dùng làm phần tử hoặc khóa băm. Bài về **phần tử mảng trong Collection** có chương trình và kỹ thuật sao chép phòng vệ đầy đủ.

`null` được một số kiểu như `ArrayList`, `HashSet`, `HashMap` chấp nhận và xử lý theo hợp đồng bằng nhau của từng tầng; `List.of`, `Set.of`, `Map.of` từ chối phần tử/khóa/giá trị `null`. Không dùng thứ tự duyệt của `Set` để suy đoán bình đẳng của collection lồng nhau.

## 7. Phần tử mutable có thể đổi cả hash của cấu trúc ngoài

Một collection bên ngoài không cho sửa cấu trúc vẫn có thể giữ tham chiếu đến một collection con sửa được:

~~~java
List<String> inner = new ArrayList<>(List.of("A"));
List<List<String>> outer = List.of(inner);
inner.add("B"); // outer vẫn có một phần tử, nhưng giá trị phần tử đã đổi.
~~~

Nếu `outer` đang là phần tử của `HashSet`, `outer.hashCode()` có thể đổi sau khi chèn, khiến `contains` hoặc `remove` không còn tìm đúng dữ liệu. Với các phần tử `String` bất biến, `List.copyOf(inner)` trước khi lồng giúp tách **cấu trúc** của list con khỏi `inner`; với đối tượng mutable, cần sao chép hoặc chuyển đổi trạng thái phần tử riêng.

Chọn dữ liệu tham gia `equals/hashCode` ổn định trong suốt thời gian làm khóa hoặc phần tử của cấu trúc băm. Bài cuối chương phân biệt kỹ `Collections.unmodifiableXxx`, bản sao nông và bất biến sâu.

## 8. Những lỗi nhận thức thường gặp

| Nhận định dễ nhầm | Điều đúng cần nhớ |
| --- | --- |
| “Hai collection có cùng số phần tử và cùng dữ liệu nhìn thấy thì bằng nhau.” | Còn phụ thuộc loại collection, thứ tự và `equals()` từng phần tử |
| “Set bỏ qua thứ tự nên Set<List<T>> cũng bỏ qua thứ tự trong mỗi list.” | Sai: set ngoài bỏ qua thứ tự các list, **list con vẫn có thứ tự** |
| “Map được chèn theo thứ tự khác sẽ không bằng nhau.” | `Map.equals()` không dựa vào thứ tự chèn; so ánh xạ khóa–giá trị |
| “Các Product có cùng SKU đương nhiên bằng nhau.” | Phải cài đặt `Product.equals()` theo SKU nếu đó là hợp đồng nghiệp vụ |
| “Cứ dùng `equals()`, không cần quan tâm `hashCode()`.” | Sai với hash collections và hash của collection lồng nhau |
| “Mảng có cùng nội dung nên bằng nhau trong List.” | Mảng dùng identity equality nếu không có lớp bọc hoặc chuyển đổi |
| “`List.of(...)` làm mọi thứ bên trong bất biến.” | Chỉ cấu trúc list ngoài không cho sửa; phần tử mutable vẫn có thể đổi |
| “Hai hash giống nhau nghĩa là hai collection bằng nhau.” | Hash trùng có thể do collision; phải kiểm tra `equals()` |

## 9. Checklist thiết kế và kiểm thử

Khi xử lý một kiểu như `List<Set<T>>`, `Set<List<T>>` hoặc `Map<K,List<V>>`:

1. Vẽ ra **từng tầng** và ghi rõ tầng nào giữ thứ tự (list), tầng nào không (set/map).
2. Xác định `equals()` và `hashCode()` của kiểu phần tử/khóa cuối cùng; nếu dùng class tự viết, kiểm tra bằng nhau có đúng nhu cầu nghiệp vụ.
3. Tạo **hai cấu trúc riêng biệt** với cùng dữ liệu logic, không chỉ so object với chính nó.
4. Đổi thứ tự ở tầng `Set` và xác nhận equality không đổi; đổi thứ tự ở tầng `List` và xác nhận equality đổi **khi vị trí các phần tử thực sự khác nhau**.
5. Cho hai object phần tử cùng khóa bằng nhau nhưng khác trường hiển thị; xác nhận collection vẫn bằng nhau và hash cũng bằng nhau.
6. Kiểm tra mảng, `null`, kiểu số có quy tắc `equals()` đặc thù, và các tình huống phần tử mutable theo nhu cầu.
7. Với cấu trúc được lưu làm key trong hash collection, bảo đảm không thay đổi ngầm bất kỳ giá trị lồng sâu nào ảnh hưởng equality hoặc hash.

**Ghi nhớ:** Bằng nhau của collection lồng nhau là kết quả của **nhiều hợp đồng `equals()` được áp dụng nối tiếp**. `List` so theo vị trí, `Set` so theo thành viên, `Map` so theo entry; mỗi tầng sử dụng equality của những object nó chứa. Thiết kế đúng `equals()/hashCode()` của phần tử và giữ giá trị khóa ổn định là điều kiện để cả cấu trúc lồng nhau hoạt động đúng.