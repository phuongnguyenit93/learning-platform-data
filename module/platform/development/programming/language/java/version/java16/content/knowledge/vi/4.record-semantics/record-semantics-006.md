# Phân biệt equality theo giá trị và identity của instance record

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Ngữ nghĩa record  
**Áp dụng:** Java 16 trở lên, bao gồm Java hiện đại.

Record được thiết kế để biểu diễn dữ liệu bằng các component có tên và có thể tự sinh `equals(Object)`, `hashCode()` và `toString()`. Với `equals` mặc định, hai record cùng lớp và có các component bằng nhau được xem là bằng nhau về **giá trị**. Tuy nhiên, record vẫn là đối tượng Java: mỗi instance vẫn có **identity** riêng và toán tử `==` vẫn kiểm tra hai tham chiếu có trỏ đến đúng cùng một đối tượng hay không.

Phân biệt hai khái niệm này giúp chọn đúng cách so sánh, tránh lỗi khi dùng record trong collection, và hiểu những API cố ý làm việc theo identity như `IdentityHashMap` hoặc `System.identityHashCode`.

## 1. Value equality và object identity là gì?

Hai khái niệm trả lời hai câu hỏi khác nhau:

- **Value equality (bằng nhau theo giá trị):** hai đối tượng có đại diện cho cùng dữ liệu theo quy tắc `equals` hay không?
- **Object identity (đồng nhất đối tượng):** hai biến tham chiếu có cùng trỏ đến một instance cụ thể hay không?

Ví dụ:

```java
record Point(int x, int y) {}

Point first = new Point(3, 5);
Point second = new Point(3, 5);
Point alias = first;

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true

System.out.println(first == alias);       // true
System.out.println(first.equals(alias));  // true
```

`first` và `second` là hai instance được tạo độc lập. Chúng không đồng nhất vì hai tham chiếu khác nhau, nhưng bằng nhau theo giá trị vì cùng lớp record `Point` và cùng component `x`, `y`. `alias` chỉ là một tham chiếu khác cùng trỏ đến instance của `first`, nên cả identity và value equality đều đúng.

Có thể mô tả bằng hình dung sau:

```text
first  ─────┐
            ├────> Point instance A (x=3, y=5)
alias  ─────┘

second ──────────> Point instance B (x=3, y=5)

A == B          : false
A.equals(B)     : true
```

Hai đối tượng có cùng nội dung không có nghĩa chúng là một đối tượng.

## 2. `==` và `equals` có vai trò khác nhau

Đối với kiểu tham chiếu:

- `a == b` kiểm tra hai tham chiếu có cùng chỉ đến một đối tượng hay không.
- `a.equals(b)` gọi phương thức `equals` của đối tượng bên trái để kiểm tra bình đẳng theo hợp đồng của lớp đó.

Với record không ghi đè `equals`, compiler cung cấp implementation so sánh cùng lớp record và các component. Vì vậy record mặc định phù hợp với cách so sánh theo giá trị:

```java
record UserId(String value) {}

UserId idFromRequest = new UserId("u-100");
UserId idFromDatabase = new UserId("u-100");

if (idFromRequest.equals(idFromDatabase)) {
    System.out.println("Cùng mã người dùng");
}

if (idFromRequest == idFromDatabase) {
    System.out.println("Cùng một instance");
} else {
    System.out.println("Hai instance riêng biệt");
}
```

Trong ứng dụng nghiệp vụ, hai ID được tạo từ hai nguồn khác nhau thường cần được so sánh theo giá trị. Dùng `==` trong tình huống đó sẽ cho kết quả sai với mục đích kiểm tra mã định danh.

Không nên dùng `==` để thay thế `equals` chỉ vì record có các component `final` hoặc được dùng như value object. `final` ngăn thay thế giá trị trường sau khi khởi tạo; nó không biến hai instance thành cùng identity.

## 3. Hai record cùng giá trị nhưng khác lớp vẫn không bằng nhau

`equals` mặc định của record yêu cầu đối tượng bên phải thuộc chính xác cùng lớp record tại runtime. Các component giống nhau không đủ để làm hai kiểu record khác nhau bằng nhau:

```java
record CustomerId(String value) {}
record OrderId(String value) {}

CustomerId customer = new CustomerId("42");
OrderId order = new OrderId("42");

System.out.println(customer.value().equals(order.value())); // true
System.out.println(customer.equals(order));                  // false
```

Đây là điểm có ích trong thiết kế domain: mã khách hàng và mã đơn hàng có thể cùng biểu diễn bằng chuỗi nhưng mang ý nghĩa khác nhau. Record giúp giữ ranh giới kiểu; phép so sánh giá trị không vô tình gộp hai khái niệm nghiệp vụ.

Một record cũng có thể triển khai interface. Hai instance của hai record khác nhau cùng triển khai một interface vẫn không tự động bằng nhau theo `equals` mặc định. Kiểu khai báo của biến không thay đổi lớp runtime của đối tượng.

## 4. Record vẫn có identity như mọi object Java

Record là một dạng class đặc biệt, không phải primitive type. Vì vậy các thao tác kiểm tra identity vẫn có ý nghĩa:

```java
record Coordinate(int x, int y) {}

Coordinate a = new Coordinate(1, 2);
Coordinate b = new Coordinate(1, 2);

System.out.println(a == b); // false
System.out.println(a.equals(b)); // true

System.out.println(System.identityHashCode(a));
System.out.println(System.identityHashCode(b));
```

`System.identityHashCode` trả về mã băm identity của một đối tượng, không phụ thuộc implementation `hashCode()` mà lớp ghi đè. Hai instance khác nhau có thể nhận cùng mã băm identity vì va chạm vẫn có thể xảy ra. Do đó, mã băm identity không phải ID duy nhất và không thay thế phép so sánh `==`.

Nếu hai biến trỏ đến cùng một instance, lời gọi `System.identityHashCode` cho đối tượng đó trong cùng lần chạy sẽ trả về cùng giá trị. Không có bảo đảm rằng hai instance khác nhau luôn có giá trị khác nhau.

### Identity không đồng nghĩa với địa chỉ bộ nhớ

Không nên hiểu identity là một địa chỉ vật lý có thể đọc hoặc lưu lại. JVM có thể quản lý, di chuyển hoặc tối ưu hóa cách lưu trữ đối tượng. Java cung cấp các phép toán identity ở mức ngôn ngữ và API; ứng dụng không nên suy luận địa chỉ bộ nhớ từ `==` hoặc `identityHashCode`.

## 5. Collection nào so sánh theo giá trị, collection nào theo identity?

Các collection thông thường như `HashMap` và `HashSet` dùng hợp đồng `equals`/`hashCode`. Vì vậy hai record khác instance nhưng bằng nhau theo giá trị được xem là cùng một khóa hoặc phần tử.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

record ProductKey(String sku, int revision) {}

ProductKey first = new ProductKey("SKU-7", 1);
ProductKey second = new ProductKey("SKU-7", 1);

Set<ProductKey> set = new HashSet<>();
set.add(first);
set.add(second);
System.out.println(set.size()); // 1

Map<ProductKey, String> map = new HashMap<>();
map.put(first, "Product A");
map.put(second, "Updated label");
System.out.println(map.size()); // 1
System.out.println(map.get(first)); // Updated label
```

Hai khóa `ProductKey` bằng nhau theo giá trị. Lần `put` thứ hai thay giá trị ánh xạ cho khóa tương đương, nên `HashMap` vẫn có một entry.

`IdentityHashMap` là ngoại lệ có chủ đích: nó so sánh khóa bằng identity (`==`), không dùng `equals` để xác định hai khóa giống nhau.

```java
import java.util.IdentityHashMap;
import java.util.Map;

record ProductKey(String sku, int revision) {}

ProductKey first = new ProductKey("SKU-7", 1);
ProductKey second = new ProductKey("SKU-7", 1);

Map<ProductKey, String> byIdentity = new IdentityHashMap<>();
byIdentity.put(first, "First instance");
byIdentity.put(second, "Second instance");

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
System.out.println(byIdentity.size());    // 2
System.out.println(byIdentity.get(first));  // First instance
System.out.println(byIdentity.get(second)); // Second instance
```

Đây là khác biệt chủ đích của API:

| Collection | Cách xác định khóa/phần tử trùng | Hai record khác instance nhưng `equals` là `true` |
| --- | --- | --- |
| `HashMap`, `HashSet` | `hashCode()` kết hợp `equals()` | Được xem là cùng khóa/phần tử. |
| `LinkedHashMap`, `LinkedHashSet` | Cùng hợp đồng equality với các collection hash tương ứng | Được xem là cùng khóa/phần tử. |
| `TreeMap`, `TreeSet` | Thứ tự do `Comparator` hoặc `Comparable` xác định | Được xem là cùng khóa/phần tử nếu so sánh cho kết quả `0`. |
| `IdentityHashMap` | So sánh tham chiếu bằng `==` | Được xem là hai khóa khác nhau. |

Với collection có thứ tự như `TreeMap`/`TreeSet`, tiêu chí trùng là kết quả so sánh bằng `0`; tiêu chí này cần nhất quán với `equals` nếu muốn collection tuân thủ đầy đủ hợp đồng `Set`/`Map`.

## 6. Khi nào nên quan tâm đến identity?

Trong phần lớn mô hình dữ liệu, record được dùng để diễn tả một giá trị. So sánh bằng `equals` là lựa chọn tự nhiên khi cần biết hai dữ liệu có cùng nội dung hay không.

Identity hữu ích khi bài toán thực sự cần phân biệt từng instance, ví dụ:

- Theo dõi từng node/object riêng trong một đồ thị có thể chứa nhiều node cùng dữ liệu.
- Ghi nhận việc đã thăm đúng instance nào khi duyệt cấu trúc đối tượng có chu trình.
- Duy trì metadata gắn với vòng đời của một object cụ thể.
- Dùng `IdentityHashMap` trong một số công cụ framework, bộ chuyển đổi object graph hoặc cơ chế sao chép/tuần tự hóa cần nhận biết tham chiếu.

Ví dụ: hai node có cùng nhãn nhưng vẫn là hai node khác nhau trong đồ thị:

```java
record NodeLabel(String value) {}

NodeLabel leftNode = new NodeLabel("shared");
NodeLabel rightNode = new NodeLabel("shared");

System.out.println(leftNode.equals(rightNode)); // true
System.out.println(leftNode == rightNode);      // false
```

Nếu bài toán chỉ cần tập hợp các nhãn duy nhất, `HashSet` là phù hợp. Nếu bài toán cần ghi nhận đã thăm từng instance node, dùng `IdentityHashMap` hoặc một cấu trúc identity-based tương ứng. Cần chọn theo ý nghĩa dữ liệu, không theo việc một API có vẻ tiện hơn.

Thông thường không cần dùng record làm node có identity riêng. Nếu identity của một thực thể là trọng tâm nghiệp vụ (ví dụ một phiên làm việc, kết nối, tiến trình hoặc entity có vòng đời), một class thông thường với ID riêng có thể thể hiện ý nghĩa đó rõ hơn.

## 7. Identity trong đồng bộ hóa và khóa

Mỗi object Java có monitor riêng; `synchronized(object)` khóa monitor gắn với **instance cụ thể**. Việc hai record bằng nhau theo `equals` không khiến chúng dùng chung monitor:

```java
record LockKey(String name) {}

LockKey first = new LockKey("cache");
LockKey second = new LockKey("cache");

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false

// synchronized(first) và synchronized(second) dùng hai monitor khác nhau.
```

Đừng dùng record được tạo mới ở nhiều nơi làm khóa đồng bộ chỉ vì chúng có cùng component. Hai luồng có thể khóa hai monitor khác nhau và không bảo vệ cùng một vùng dữ liệu.

Nếu cần đồng bộ hóa, hãy dùng một lock object ổn định, có vòng đời và quyền sở hữu rõ ràng, chẳng hạn một trường `private final Object lock = new Object()` trong đối tượng quản lý. Không nên khóa trên một record value được tái tạo theo nội dung.

## 8. Có thể tùy chỉnh `equals` để chuyển từ value equality sang identity không?

Java cho phép khai báo tường minh `equals(Object)` và `hashCode()` trong record, nhưng việc tùy chỉnh phải giữ hợp đồng `Object` và bất biến sao chép của record: nếu tạo một record mới bằng cách truyền kết quả các accessor của record cũ vào canonical constructor, record mới phải bằng record cũ theo `equals`. Một `equals` chỉ kiểm tra `this == other` sẽ vi phạm bất biến này vì bản sao là instance khác. Vì vậy không thể biến record thành kiểu identity-equality thuần túy bằng cách ghi đè `equals`.

Record được thiết kế để component xác định giá trị biểu diễn. Nếu ứng dụng cần identity equality làm ý nghĩa chính, hãy cân nhắc dùng class thông thường kế thừa hành vi `Object.equals`/`Object.hashCode` hoặc dùng một collection identity-based tại nơi cần thiết. Nếu chỉ cần một thuật toán cụ thể phân biệt instance, có thể giữ record bình thường và dùng `==` hoặc `IdentityHashMap` tại đúng vị trí đó.

Tách rõ hai nhu cầu:

- Muốn hai đối tượng cùng dữ liệu được xem là một giá trị: giữ `equals`/`hashCode` mặc định của record.
- Muốn phân biệt hai instance cụ thể dù nội dung giống nhau: dùng `==`, `IdentityHashMap` hoặc một class có identity semantics phù hợp.

## 9. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Hai record có cùng component thì `==` trả về `true`. | **Sai** | `==` kiểm tra cùng instance, không so sánh component. |
| Hai record cùng lớp và component bằng nhau thì `equals` mặc định có thể trả về `true` dù là hai instance khác nhau. | **Đúng** | Đây là value equality. |
| Record không có identity vì được thiết kế làm value object. | **Sai** | Record vẫn là object Java và vẫn có identity. |
| `System.identityHashCode` là mã duy nhất của instance. | **Sai** | Identity hash có thể va chạm. |
| `HashMap` và `IdentityHashMap` xem hai record bằng nhau theo cùng cách. | **Sai** | `HashMap` dùng `equals`/`hashCode`; `IdentityHashMap` dùng `==`. |
| Hai record bằng nhau theo `equals` thì dùng chung monitor `synchronized`. | **Sai** | Monitor gắn với từng instance. |
| Nếu cần identity trong một thuật toán, có thể dùng `IdentityHashMap`. | **Đúng** | Đây là collection chuyên biệt cho so sánh tham chiếu. |

## 10. Checklist lựa chọn equality

Trước khi chọn cách so sánh record, hãy xác định:

1. Bài toán hỏi hai dữ liệu có cùng giá trị hay hai biến có cùng tham chiếu?
2. Có cần gộp các instance khác nhau nhưng có component bằng nhau trong `Set` hoặc `Map` không?
3. Có cần phân biệt các node/object riêng biệt dù dữ liệu giống nhau không?
4. Collection đang dùng equality thông thường, comparator hay identity?
5. Có đang dùng record làm monitor đồng bộ hóa hoặc khóa identity không? Nếu có, vòng đời instance đã ổn định chưa?
6. Component có `equals` theo đúng ý nghĩa nghiệp vụ hay không?

**Ghi nhớ:** Record mặc định cung cấp value equality qua `equals`, nhưng không xóa identity của object. `==` kiểm tra cùng instance; `equals` kiểm tra bình đẳng theo giá trị component. `HashMap`/`HashSet` dùng equality thông thường, còn `IdentityHashMap` dùng identity. Chọn cơ chế phù hợp với câu hỏi mà thuật toán thực sự cần trả lời.

## Tài liệu chính thức

- [Java SE 26 API — `java.lang.Record`, hợp đồng `equals` và `hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html).
- [Java SE 26 API — `java.util.IdentityHashMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IdentityHashMap.html).
- [Java SE 26 API — `java.lang.System.identityHashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)).
- [Java Language Specification, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records, tính năng chính thức trong Java 16](https://openjdk.org/jeps/395).
