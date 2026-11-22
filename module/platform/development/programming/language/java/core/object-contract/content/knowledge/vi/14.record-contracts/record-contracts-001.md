# Hợp đồng record: `equals()`, `hashCode()` và `toString()` được sinh từ các thành phần

## 1. Record giải quyết vấn đề gì?

Một **record** trong Java biểu diễn dữ liệu bằng một danh sách **record components** khai báo ngay trong phần đầu lớp. Với Java 17, thay vì tự viết constructor, các trường lưu giá trị, accessor và những phương thức của `Object` thường cần thiết cho một đối tượng dữ liệu, ta có thể khai báo:

```java
record Product(String sku, int quantity) {}
```

Từ khai báo này, compiler cung cấp các thành phần cần thiết, gồm:

- Hai trường instance tương ứng: `private final String sku` và `private final int quantity`.
- Constructor chuẩn (`canonical constructor`) có tham số theo thứ tự các component: `Product(String sku, int quantity)`.
- Các accessor cùng tên component: `sku()` và `quantity()`, khác với kiểu getter JavaBeans `getSku()`.
- Triển khai `equals(Object)`, `hashCode()` và `toString()` dựa trên **các record components**.

Một record mặc nhiên là `final`, trực tiếp kế thừa `java.lang.Record` và không thể mở rộng một lớp cha khác. Nó có thể implements interface, có phương thức riêng, static members, constructor bổ sung chuyển tiếp tới canonical constructor, và có thể tự cung cấp triển khai của các phương thức được phép ghi đè. Nó không được thêm instance field thông thường ngoài các trường phát sinh từ record components.

Bài học này tập trung vào **hợp đồng của ba phương thức được sinh**: Java dùng các component nào để xác định bằng nhau, cách suy ra hash, cách in object, và giới hạn khi component là một tham chiếu mutable. Record giúp loại bỏ code lặp, nhưng **không biến mọi component thành bất biến sâu**.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Dự đoán `equals`, `hashCode` và `toString` của một record chỉ bằng cách đọc danh sách component.
2. Giải thích vì sao hai record khác instance có thể bằng nhau, còn hai record khác kiểu dù chứa cùng dữ liệu lại không bằng nhau.
3. Chứng minh điều kiện `equals ⇒ hashCode bằng nhau`, phân biệt nó với chiều đảo sai.
4. Giải thích và tái hiện hành vi của record có component là `String`, `List`, array và số thực dấu phẩy động.
5. Dùng compact constructor hoặc canonical constructor để chuẩn hóa, kiểm tra và sao chép dữ liệu khi thích hợp.
6. Biết khi nào được dùng triển khai compiler sinh, và khi nào cần chọn một kiểu/value model khác hoặc tự ghi đè một cách có trách nhiệm.

## 2. Cơ chế cơ bản: các component quyết định giá trị của record

Với:

```java
record Coordinate(int x, int y) {}
```

Các component là `x` và `y`. Hai instance `new Coordinate(3, 5)` và `new Coordinate(3, 5)` khác nhau về tham chiếu, nhưng bằng nhau theo triển khai `equals` của record. `new Coordinate(5, 3)` khác vì các giá trị tương ứng không trùng. Record dùng **tên kiểu record**, số lượng/kiểu component và các giá trị tương ứng; nó không chỉ “so mọi field bằng reflection” một cách tùy tiện.

So với một lớp Java thông thường:

```java
final class CoordinateClass {
    private final int x;
    private final int y;

    CoordinateClass(int x, int y) {
        this.x = x;
        this.y = y;
    }

    // Nếu không override equals/hashCode/toString:
    // equals kế thừa từ Object: so danh tính tham chiếu.
}
```

Đây là đoạn minh họa riêng. Trong một class thường, khai báo `final` và hai trường `final` **không** làm compiler tự viết value equality; còn ở record, các phương thức phù hợp với mô hình component được sinh tự động.

Cần nhớ: **component order có ý nghĩa** vì record có constructor/accessor theo thứ tự đã khai báo, `toString` trình bày theo thứ tự đó và các thành phần tương ứng tham gia so sánh. Không dựa vào một phép hoán vị tên trường tùy ý để kết luận hai record khác loại bằng nhau.

## 3. Hợp đồng `equals(Object)` được sinh

### 3.1. Hai record bằng nhau khi nào?

Đối với hai instance thuộc cùng **lớp record**:
- Các component kiểu tham chiếu được so theo ngữ nghĩa `Objects.equals` (null-safe, và gọi `equals` của đối tượng thành phần khi khác null).
- Các component primitive được so theo ngữ nghĩa giá trị của kiểu tương ứng; riêng `float`/`double` có ngữ nghĩa so sánh nhất quán với `Float.compare`/`Double.compare`, cần chú ý `NaN` và số không có dấu âm.
- Mọi component tương ứng phải bằng nhau; chỉ khác một component là record khác nhau.
- `record.equals(null)` là `false`; `record.equals(record)` luôn `true`.

Nếu hai instance khác lớp record, `equals` của triển khai sinh sẽ không xem chúng bằng nhau, kể cả khi các component có cùng tên và giá trị.

Ví dụ:

```java
record Point(int x, int y) {}
record Location(int x, int y) {}

// Trong một phương thức:
Point p1 = new Point(2, 4);
Point p2 = new Point(2, 4);
Location l = new Location(2, 4);

System.out.println(p1 == p2);  // false
System.out.println(p1.equals(p2)); // true
System.out.println(p1.equals(l));  // false
```

Đây là đoạn ví dụ phân tách để tập trung vào equality; đoạn khai báo record hợp lệ ở phạm vi lớp hoặc cục bộ trong nơi khai báo cho phép, và các câu lệnh cần nằm trong phương thức.

Đừng nhầm equality do record sinh với:
- `==`: so **cùng tham chiếu** cho record là đối tượng Java.
- So riêng `toString`: chỉ là chuỗi hiển thị, không được dùng làm cơ sở định nghĩa equality.
- So khóa nghiệp vụ: record mặc định so **tất cả component**, kể cả component mà domain của bạn có thể muốn bỏ qua.
- So qua kế thừa: record là `final`, không có subclass của chính record đó.

### 3.2. `null` được xử lý thế nào?

Một component kiểu tham chiếu **có thể là null** trừ khi constructor kiểm tra và từ chối. Hai instance cùng kiểu record có component `null` tại cùng vị trí có thể vẫn bằng nhau:

```java
record Note(String text) {}

// Trong một phương thức:
new Note(null).equals(new Note(null))  // true
new Note(null).equals(new Note("x"))   // false
```

Hai biểu thức cuối minh họa kết quả boolean, không phải hai statement Java tự chạy riêng nếu không dùng chúng trong assignment/call. Nếu quy tắc nghiệp vụ không cho null, hãy kiểm tra tại constructor, ví dụ `Objects.requireNonNull(text, "text")`.

**Sự khác biệt với entity có ID tạo sau:** một record đơn giản lưu `id = null` sẽ mặc định coi hai record cùng kiểu và cùng các component bằng nhau. Nếu mỗi instance chưa ID phải có danh tính entity riêng, record dạng “so toàn bộ component” có thể không diễn tả đúng domain. Hãy thiết kế identity riêng thay vì giả định record tự nhận biết vòng đời entity.

### 3.3. Kiểu tham chiếu dùng equality của chính nó

Nếu record chứa `BigDecimal amount`, triển khai `equals` sinh gọi equality của `BigDecimal`. Trong Java:

```java
record Price(java.math.BigDecimal amount) {}

// Trong một phương thức:
Price a = new Price(new java.math.BigDecimal("1.0"));
Price b = new Price(new java.math.BigDecimal("1.00"));
System.out.println(a.equals(b)); // false
```

`BigDecimal.equals` xét cả giá trị số lẫn scale; trong khi `BigDecimal.compareTo` trả `0` cho hai giá trị trên. Record không tự chuẩn hóa `BigDecimal` hoặc thay phép so theo nghiệp vụ. Nếu domain coi hai số đó là tương đương, cần thống nhất chính sách chuẩn hóa (ví dụ tại constructor) hoặc lựa chọn model phù hợp.

Với String, `String.equals` so nội dung, nên hai instance String có cùng nội dung sẽ cho kết quả bằng nhau; `record` không yêu cầu String phải cùng object.

### 3.4. Trường hợp `float`, `double`

Giữ ý nghĩa đặc biệt của số thực:
- Các giá trị `NaN` của cùng component được coi bằng nhau theo logic equality của record.
- `+0.0` và `-0.0` được phân biệt trong equality của component `float`/`double`.
- So sánh này bảo đảm hợp đồng với hash code của record.

Không nên tự mô phỏng record equality của `double` bằng toán tử `==` rồi suy luận sai với `NaN` hoặc signed zero. Khi domain cần định nghĩa “gần bằng nhau” theo sai số số học, đó là bài toán khác với equality dùng cho `HashMap`/`HashSet`, vì tolerance comparison có thể không bắc cầu.

## 4. Hợp đồng `hashCode()` được sinh

Compiler tạo triển khai `hashCode` từ cùng các component dùng bởi `equals`. Điều quan trọng cần kiểm tra là:

**Nếu `a.equals(b)` trả `true` thì `a.hashCode() == b.hashCode()` phải là `true`.**

Chiều ngược không đúng: hash trùng (collision) không chứng minh record bằng nhau. Không có quy tắc “mỗi record có hash riêng”, và không nên dùng hash như ID nghiệp vụ.

Đặc điểm cần hiểu:
- Các component primitive/reference đóng góp vào giá trị hash theo ngữ nghĩa tương ứng; implementation bảo toàn hợp đồng equality.
- Component `null` được xử lý hợp lệ, không cần tự viết hash null-safe.
- Thuật toán kết hợp và **con số hash cụ thể** của record không phải định dạng lưu trữ hay giao thức ổn định mà ứng dụng nên phụ thuộc. Tránh hard-code `hashCode() == 123456` trong test hoặc lưu hash như khóa bền vững.
- Nếu một component là object **mutable**, hash của record có thể thay đổi nếu hash của component đó thay đổi. Các trường record là `final` nhưng object tham chiếu có thể vẫn mutable.

### Dùng record trong `HashSet` và `HashMap`

Record chứa các component bất biến với equality ổn định thường rất tiện làm khóa:

```java
record CustomerKey(String tenant, long id) {}

// Trong một phương thức:
var map = new java.util.HashMap<CustomerKey, String>();
map.put(new CustomerKey("SHOP", 42), "paid");
System.out.println(map.get(new CustomerKey("SHOP", 42))); // paid
```

Hai instance khóa khác tham chiếu nhưng record equality/hash cùng dựa trên `tenant` và `id`, nên map có thể tra theo value.

Ngược lại, record chứa `List` mutable có thể gặp lỗi: sau khi thêm làm khóa, caller sửa list bên ngoài, `hashCode` tính lại từ nội dung đã đổi và lookup có thể không tìm được. Vấn đề nằm ở **trạng thái component mutable**, không phải ở compiler sinh hash sai.

### Hash của record không phải fingerprint duy nhất

Ngay cả với các component immutable, số lượng giá trị hash `int` chỉ có 2³² khả năng trong khi số lượng record có thể lớn hơn rất nhiều. Collision là bình thường, `HashMap` vẫn dùng equality để xử lý. Nếu cần checksum/định danh ổn định giữa hệ thống, phải dùng một thuật toán xác định trên biểu diễn dữ liệu chuẩn hóa, không tận dụng `hashCode()`.

## 5. Hợp đồng `toString()` được sinh

Record cung cấp `toString` hữu ích cho đọc log và gỡ lỗi. Java 17 hiển thị dạng gồm **tên record**, cặp **tên component = giá trị** theo thứ tự khai báo:

```java
record Product(String sku, int quantity) {}

// Trong một phương thức:
System.out.println(new Product("BOOK", 2));
// Product[sku=BOOK, quantity=2]
```

Không cần tự nối chuỗi thủ công khi chỉ muốn biết dữ liệu trong một DTO/value object đơn giản. Khi record chứa record khác hoặc list, `toString` của component được gọi thông qua cách biểu diễn String của object đó.

Giới hạn quan trọng:
- `toString` không phải serializer chuẩn, không thay JSON, CSV, database key hay format truyền dữ liệu.
- Với array, định dạng hiển thị mặc định thường là tên kiểu mảng và identity hash, không tự liệt kê nội dung bằng `Arrays.toString`.
- Với component mutable, `toString` có thể **đổi** sau khi record được tạo dù trường component là `final`.
- Component nhạy cảm như token, mật khẩu, dữ liệu nhận dạng cá nhân có thể vô tình lộ qua log. Khi đó cần cân nhắc một `toString` tùy biến che dữ liệu hoặc tránh log trực tiếp record.
- Không lấy `toString` để quyết định `equals` hoặc băm; hiển thị là trách nhiệm khác với identity.

## 6. Chương trình Java 17 chạy độc lập: ba phương thức sinh và trường hợp biên

Tạo file **`RecordContractDemo.java`** dưới đây. Ví dụ gồm: record có hai component bất biến, record chứa danh sách đã snapshot, record giữ list mutable không phòng vệ, record chứa mảng, và record chứa số thực. Các record được khai báo lồng trong lớp chính để biên dịch bằng **một file**.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class RecordContractDemo {
    record Product(String sku, int quantity) {
        Product {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("blank sku");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("invalid quantity");
            }
        }
    }

    record Cart(String owner, List<Product> items) {
        Cart {
            Objects.requireNonNull(owner, "owner");
            items = List.copyOf(Objects.requireNonNull(items, "items"));
        }
    }

    // Không snapshot: component tham chiếu đến list mutable.
    record OpenBox(List<String> tags) {}

    // Hai array khác tham chiếu không bằng nhau theo record equality.
    record Bytes(byte[] data) {}

    record Reading(double value) {}

    public static void main(String[] args) {
        Product p1 = new Product(" BOOK ", 2);
        Product p2 = new Product("BOOK", 2);
        Product p3 = new Product("PEN", 1);

        System.out.println("same instance: " + (p1 == p2));
        System.out.println("products equal: " + p1.equals(p2));
        System.out.println("hash equal: "
                + (p1.hashCode() == p2.hashCode()));
        System.out.println("product print: " + p1);

        Set<Product> products = new HashSet<>(List.of(p1, p2, p3));
        System.out.println("set size: " + products.size());

        Map<Product, String> stock = new HashMap<>();
        stock.put(p1, "available");
        System.out.println("map lookup: " + stock.get(p2));

        List<Product> source = new ArrayList<>(List.of(p1));
        Cart cart = new Cart("SHOP", source);
        source.add(p3);
        System.out.println("cart items: " + cart.items());
        System.out.println("cart print: " + cart);
        System.out.println("same cart value: "
                + cart.equals(new Cart("SHOP", List.of(p2))));

        boolean editRejected = false;
        try {
            cart.items().add(p3);
        } catch (UnsupportedOperationException expected) {
            editRejected = true;
        }
        System.out.println("cart edit rejected: " + editRejected);

        List<String> mutableTags = new ArrayList<>(List.of("a"));
        OpenBox box = new OpenBox(mutableTags);
        int hashBefore = box.hashCode();
        mutableTags.add("b");
        System.out.println("box tags after edit: " + box.tags());
        System.out.println("box hash changed: "
                + (hashBefore != box.hashCode()));
        System.out.println("box print after edit: " + box);

        Bytes b1 = new Bytes(new byte[] {1, 2});
        Bytes b2 = new Bytes(new byte[] {1, 2});
        System.out.println("arrays as components equal: " + b1.equals(b2));
        System.out.println("array contents equal: "
                + Arrays.equals(b1.data(), b2.data()));

        System.out.println("NaN records equal: "
                + new Reading(Double.NaN).equals(
                        new Reading(Double.NaN)));
        System.out.println("signed zero records equal: "
                + new Reading(+0.0).equals(new Reading(-0.0)));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 RecordContractDemo.java
java RecordContractDemo
```

Kết quả:

```text
same instance: false
products equal: true
hash equal: true
product print: Product[sku=BOOK, quantity=2]
set size: 2
map lookup: available
cart items: [Product[sku=BOOK, quantity=2]]
cart print: Cart[owner=SHOP, items=[Product[sku=BOOK, quantity=2]]]
same cart value: true
cart edit rejected: true
box tags after edit: [a, b]
box hash changed: true
box print after edit: OpenBox[tags=[a, b]]
arrays as components equal: false
array contents equal: true
NaN records equal: true
signed zero records equal: false
```

### Giải thích vì sao những dòng trên đúng

1. `p1` và `p2` được tạo bằng hai lệnh `new` nên `==` trả `false`. Compact constructor `Product` dùng `strip()` chuẩn hóa SKU thành `"BOOK"`; cùng `quantity` nên compiler-generated `equals` trả `true`, hash cũng phải bằng nhau.
2. `HashSet` giữ hai giá trị khác nhau: `Product("BOOK", 2)` và `Product("PEN", 1)`. `HashMap` tìm được chuỗi `"available"` bằng `p2` dù khóa lưu bằng `p1`, minh họa record như value key.
3. `Cart` dùng `List.copyOf` trong compact constructor, nên caller thêm `p3` vào `source` sau khi xây dựng không làm danh sách trong `cart` đổi. List trả từ accessor không cho `add`, vì vậy catch ghi nhận `UnsupportedOperationException`.
4. `Cart` so toàn bộ hai component `owner` và `items`. List equality so nội dung tuần tự, các `Product` được so theo record equality. Vì thế cart tạo từ `p1` bằng cart tạo từ `p2`.
5. `OpenBox` giữ list gốc, không snapshot. Sau khi caller thêm `"b"`, cả accessor, hash và `toString` đều phản ánh nội dung mới. Hash đổi có thể gây lỗi nếu `box` đang nằm trong một hash collection.
6. Hai instance `Bytes` có hai mảng `byte[]` khác tham chiếu. Array không ghi đè `Object.equals` theo nội dung nên record equality trả `false`, còn `Arrays.equals` được gọi tường minh trả `true`.
7. `Reading` dùng quy tắc equality dành cho `double`: hai `NaN` tương đương theo record, còn `+0.0` và `-0.0` khác nhau. Đây là ngữ nghĩa của hợp đồng record, không phải áp dụng trực tiếp toán tử `==` trên các double.

**Độ tin cậy của output:** Chương trình không in hash dưới dạng số vì không nên phụ thuộc vào giá trị cụ thể của `hashCode`. Chỉ in so sánh boolean bảo đảm bởi hợp đồng. Các giá trị text/list cố định nên kết quả không phụ thuộc thứ tự lặp của `HashSet`; chương trình chỉ in `size()`.

## 7. Điều record sinh và điều record không tự làm

| Tính năng | Compiler hỗ trợ | Lưu ý |
|---|---|---|
| Accessor cho từng component | `sku()`, `quantity()` | Không tự tạo getter JavaBeans `getSku()` |
| Constructor chuẩn | Theo thứ tự và kiểu component | Có thể viết compact constructor để kiểm tra/chuẩn hóa |
| `equals` | Dựa trên toàn bộ component | Dùng equality của kiểu tham chiếu; không tự chọn khóa nghiệp vụ |
| `hashCode` | Phù hợp với `equals` | Không thay cho ID ổn định hoặc hash mật mã |
| `toString` | Tên record và tên/giá trị component | Có thể lộ dữ liệu nhạy cảm; không phải serializer |
| Trường tương ứng component | `private final` | Là bất biến **tham chiếu**, không nhất thiết bất biến sâu |
| Sao chép collection hoặc array | **Không** | Cần defensive copy nếu domain đòi trạng thái bất biến |
| Kiểm tra `null`/điều kiện nghiệp vụ | **Không** | Constructor phải tự kiểm tra nếu muốn từ chối |
| Sắp xếp `Comparable` | **Không** | Triển khai `Comparable<T>` hoặc cung cấp `Comparator<T>` riêng |
| Equality theo một phần component | **Không theo mặc định** | Thiết kế model hoặc tự override hợp lệ nếu thật sự cần |

Một record như `record User(String email, String displayName) {}` **so cả hai component**, không mặc định chỉ so email. Nếu ứng dụng chỉ muốn identity theo mã bất biến, cách rõ ràng hơn thường là tạo riêng `UserId`/`UserKey` hoặc quyết định lại mô hình entity; override equality một cách tùy tiện dễ phá kỳ vọng rằng record mang ngữ nghĩa dữ liệu theo toàn bộ components.

## 8. Ranh giới của ví dụ tổng quan

`List.copyOf` có thể chụp cấu trúc danh sách nhưng không sao chép sâu phần tử mutable; mảng làm component vẫn so theo danh tính dù các byte giống nhau. Một record có `final` fields vẫn có thể chứa trạng thái mutable, và dữ liệu ấy có thể tác động tới `equals`, `hashCode`, `toString` hoặc khóa hash. Ví dụ tổng hợp ở trên giúp nhận diện rủi ro; các bài tiếp theo diễn giải từng trường hợp cùng code riêng.

Khi cần chính sách khác mặc định, hãy ưu tiên chọn component và canonical constructor phù hợp: chuẩn hóa dữ liệu trước khi lưu; sao chép phòng vệ đúng cấp; chỉ override `equals` cùng với `hashCode` nếu muốn thay đổi value equality, chẳng hạn so mảng theo nội dung. Có thể override riêng `toString` để tránh log bí mật, nhưng không dùng kết quả in ra làm giao thức. Nếu chỉ một ID xác định danh tính, một record khóa `ProductId` riêng thường rõ hơn việc âm thầm bỏ qua component trong `equals`.

## 9. Bài tập tự kiểm tra

### Bài tập A — Dự đoán kết quả

Cho:

```java
record UserName(String first, String last) {}

UserName u1 = new UserName("An", "Le");
UserName u2 = new UserName("An", "Le");
UserName u3 = new UserName("Le", "An");
```

Hỏi `u1 == u2`, `u1.equals(u2)`, `u1.equals(u3)` và `u1.hashCode() == u2.hashCode()`. Đáp án lần lượt: `false`, `true`, `false`, `true`.

### Bài tập B — Lỗi khi bỏ component

Tạo `record Entry(long id, String status) {}`. Hai record ID `10` nhưng status khác nhau có bằng nhau không? Không: cả `id` và `status` tham gia equality. Nếu nghiệp vụ muốn identity chỉ theo ID, hãy thiết kế `EntryId` riêng hoặc làm rõ vì sao cần entity thay vì value snapshot.

### Bài tập C — Mảng

Tạo hai `record Data(byte[] bytes) {}` với hai mảng `{1, 2}` khác object. Dự đoán `equals` và thử `Arrays.equals`. Giải thích rủi ro khi getter mặc định trả mảng có thể sửa, kể cả `hashCode` của record không đổi theo phần tử mảng.

### Bài tập D — List mutable trong `HashSet`

Tạo `record Tags(List<String> tags) {}`. Thêm object vào `HashSet`, sau đó sửa list nguồn; in hash trước/sau và thử `contains`. Nếu lookup tình cờ vẫn thành công trên một run, giải thích vì sao thay đổi state làm việc sử dụng khóa không còn đáng tin. Sửa record bằng `List.copyOf` và thử lại.

### Bài tập E — Kiểm thử đặc biệt cho số

Tạo `record F(double value) {}` rồi kiểm tra `Double.NaN`, `+0.0` và `-0.0`. So sánh phép `==` trên double với generated `equals` của record và giải thích vì sao kết quả khác nhau.

### Bài tập F — Tùy biến `toString`

Viết `record ApiToken(String owner, String secret)`. Override duy nhất `toString` để không hiện `secret`, nhưng vẫn giữ generated equality/hash xét đầy đủ hai component. Thảo luận khi nào **không nên log cả record** dù đã che một phần.

## 10. Checklist áp dụng

- Đã xác định tất cả record components và ý nghĩa của từng component trong value equality.
- Đã kiểm tra null và chuẩn hóa đầu vào khi domain yêu cầu.
- Đã kiểm tra primitive, reference, `BigDecimal` và số thực theo đúng equality của kiểu thành phần.
- Đã hiểu generated `hashCode` bảo toàn hợp đồng với generated `equals`; không nhầm collision với equality.
- Đã hiểu `toString` chỉ là biểu diễn phục vụ đọc/debug, có thể lộ dữ liệu nhạy cảm.
- Đã kiểm tra component là array, list hoặc mutable object; có defensive copy/snapshot phù hợp nếu cần.
- Đã biết dùng record làm key của `HashMap`/`HashSet` khi dữ liệu tham gia equality/hash ổn định.
- Nếu override `equals`, đã xem xét và kiểm thử lại `hashCode` cùng ngữ nghĩa.
- Đã chạy `RecordContractDemo.java` và giải thích được từng dòng output.

**Ghi nhớ:** Java record sinh `equals()`, `hashCode()` và `toString()` từ các component, giúp biểu diễn dữ liệu có value semantics ngắn gọn. Chất lượng hợp đồng vẫn phụ thuộc **kiểu và ngữ nghĩa của từng component**, chính sách chuẩn hóa, mức độ bất biến và cách object được dùng trong collection.