# Vì sao Map thuộc framework nhưng không kế thừa Collection?

**`Map` thuộc Java Collections Framework vì nó là một thành phần của hệ thống API tổ chức và xử lý dữ liệu của Java. Nó không kế thừa `Collection` vì hợp đồng của một ánh xạ khóa–giá trị khác hợp đồng của một nhóm phần tử.**

Cần tách hai quan hệ:

- **Thuộc framework:** cùng tham gia một hệ thống các interface, lớp triển khai, thuật toán và quy ước.
- **Kế thừa interface:** một kiểu cam kết thực hiện đầy đủ hợp đồng của interface cha.

Không có quy tắc rằng mọi thành phần trong Java Collections Framework đều phải nằm dưới interface `Collection`. Nhánh `Map` tồn tại song song với nhánh `Collection`, rồi kết nối với nhánh này qua các view như `keySet()`, `values()` và `entrySet()`.

## 1. Hai mô hình dữ liệu khác nhau ở đâu?

### 1.1. Collection nhìn dữ liệu như các phần tử

Với `Collection<E>`, đơn vị được xử lý là phần tử kiểu `E`.

Ví dụ về một nhóm mã sản phẩm:

```text
["pen", "book", "bag"]
```

Những câu hỏi tự nhiên là:

- Nhóm này có bao nhiêu phần tử?
- Có phần tử `"book"` không?
- Có thể thêm hoặc xóa một phần tử không?
- Duyệt qua các phần tử bằng cách nào?

Các interface con bổ sung ngữ nghĩa cụ thể. `List` có vị trí và thứ tự danh sách; `Set` thể hiện tập không có phần tử trùng; `Queue` phục vụ cách xử lý theo chính sách hàng đợi.

### 1.2. Map nhìn dữ liệu như quan hệ khóa–giá trị

Với `Map<K, V>`, đơn vị nghiệp vụ là một **ánh xạ** từ khóa kiểu `K` sang giá trị kiểu `V`.

Ví dụ số lượng tồn kho:

```text
"pen"  -> 10
"book" -> 3
"bag"  -> 3
```

Những câu hỏi tự nhiên chuyển thành:

- Số lượng ứng với mã `"pen"` là bao nhiêu?
- Mã `"book"` đã có ánh xạ chưa?
- Cập nhật số lượng cho một mã bằng cách nào?
- Xóa ánh xạ ứng với khóa nào?

Trong một map, mỗi khóa chỉ có tối đa một giá trị hiện tại. Nhiều khóa khác nhau có thể ánh xạ tới các giá trị bằng nhau. Ở ví dụ trên, hai giá trị `3` không vi phạm hợp đồng của map.

Một giá trị cũng có thể là một đối tượng chứa nhiều phần tử, chẳng hạn `Map<String, List<String>>`. Khi đó mỗi khóa vẫn ánh xạ tới **một đối tượng List**, không làm thay đổi hợp đồng của `Map`.

Đặc điểm khóa–giá trị và vị trí của `Map` trong framework được mô tả trong [API Map của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 2. Vì sao không dùng Collection<Map.Entry<K, V>> làm cha?

Có thể biểu diễn một cặp khóa–giá trị bằng `Map.Entry<K, V>`. Từ đó, ta hoàn toàn có thể tạo một collection chứa các cặp. Nhưng **chứa các cặp dữ liệu** chưa đồng nghĩa với **thực hiện hợp đồng của map**.

### 2.1. Một tập các cặp chưa bảo đảm khóa duy nhất

Xét hai cặp:

```text
("pen", 10)
("pen", 12)
```

Đối với hai `Map.Entry` thông thường, khác giá trị thì hai cặp này không bằng nhau. Do đó một `HashSet<Map.Entry<String, Integer>>` có thể giữ đồng thời cả hai cặp.

Đối với một map, lần lượt gọi:

```java
map.put("pen", 10);
map.put("pen", 12);
```

sẽ tạo một ánh xạ hiện tại cho `"pen"` với giá trị `12`, không phải hai ánh xạ cùng khóa.

Đoạn trên minh họa các lệnh trong một phương thức, với `map` là một `Map<String, Integer>` cho phép cập nhật.

Sự khác nhau nằm ở **quy tắc nhận diện và cập nhật phần tử**, không nằm ở việc Java có lưu được hai giá trị trong một đối tượng hay không. Cũng không thể giải thích đơn giản bằng “`Collection` có một tham số kiểu còn `Map` có hai”, vì `E` hoàn toàn có thể là một kiểu cặp.

### 2.2. Các thao tác cốt lõi cần hợp đồng riêng

| Nhu cầu | Hợp đồng Collection | Hợp đồng Map |
| --- | --- | --- |
| Thêm dữ liệu | `add(E)` yêu cầu đưa phần tử vào nhóm | `put(K, V)` tạo hoặc thay ánh xạ cho khóa |
| Hỏi dữ liệu có mặt | `contains(Object)` hỏi về một phần tử | `containsKey(Object)` và `containsValue(Object)` hỏi hai phía khác nhau |
| Tra cứu theo khóa | Không có thao tác chung tương đương | `get(Object)` trả giá trị ứng với khóa |
| Xóa dữ liệu | `remove(Object)` xóa phần tử phù hợp | `remove(Object)` xóa ánh xạ theo khóa |
| Kích thước | Số phần tử | Số ánh xạ khóa–giá trị |
| Duyệt | Từng phần tử kiểu `E` | Cần chọn duyệt khóa, giá trị hay cặp |

Nếu giả sử một map có phương thức `add(entry)`, chỉ tên gọi đó chưa nói rõ điều gì xảy ra khi khóa đã tồn tại: từ chối cặp mới, giữ hai cặp hay thay giá trị cũ? `Map.put` có hợp đồng riêng để bên sử dụng biết hành vi phải chờ đợi.

Tương tự, `contains(x)` trên một map sẽ cần xác định `x` được hiểu là khóa, giá trị hay một cặp đầy đủ. API `Map` làm rõ ý định bằng các phương thức riêng.

### 2.3. Xung đột chữ ký cho thấy đây không chỉ là đổi cây kế thừa

Một khác biệt cụ thể trong API hiện có:

```java
// Chữ ký minh họa, không phải một lớp hoặc chương trình độc lập:

// Trong Collection<E>:
boolean remove(Object element);

// Trong Map<K, V>:
V remove(Object key);
```

Hai phương thức có cùng tên và cùng danh sách kiểu tham số, nhưng một bên trả `boolean`, bên kia trả `V`.

Với `Collection`, kết quả trả lời câu hỏi “nhóm có thay đổi do xóa phần tử không?”. Với `Map`, kết quả là giá trị trước đó gắn với khóa, hoặc `null` theo hợp đồng của phương thức.

Không thể chỉ thêm `extends Collection<...>` vào `Map` hiện có rồi giữ nguyên hai hợp đồng này: Java không phân biệt hai phương thức chỉ bằng kiểu trả về, và `boolean` không tương thích với kiểu tham chiếu `V`.

Đây là một biểu hiện rõ của khác biệt ngữ nghĩa giữa hai interface. Mục tiêu của thiết kế API là cung cấp hợp đồng rõ ràng cho mô hình dữ liệu, thay vì buộc hai mô hình vào chung một interface vì cùng “chứa nhiều thứ”.

Có thể đối chiếu chữ ký trong [API Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)) và [API Map.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#remove(java.lang.Object)).

## 3. Map nằm ở đâu trong framework?

Sơ đồ rút gọn sau thể hiện các nhánh interface quen thuộc trong Java 17:

```text
Java Collections Framework
│
├── Nhánh nhóm phần tử
│   └── Collection<E> extends Iterable<E>
│       ├── List<E>
│       ├── Set<E>
│       └── Queue<E>
│           └── Deque<E>
│
└── Nhánh ánh xạ
    └── Map<K, V>
        └── SortedMap<K, V>
            └── NavigableMap<K, V>
```

Đây là sơ đồ phân nhóm và kế thừa được rút gọn, không phải danh sách đầy đủ mọi interface của framework.

Một số lớp triển khai:

| Interface sử dụng | Ví dụ lớp triển khai |
| --- | --- |
| `List<E>` | `ArrayList<E>`, `LinkedList<E>` |
| `Set<E>` | `HashSet<E>`, `LinkedHashSet<E>` |
| `Deque<E>` | `ArrayDeque<E>`, `LinkedList<E>` |
| `Map<K, V>` | `HashMap<K, V>`, `LinkedHashMap<K, V>` |
| `NavigableMap<K, V>` | `TreeMap<K, V>` |

Việc `HashMap` triển khai `Map` đã đặt nó vào nhánh ánh xạ của framework. Nó không cần và không có quan hệ kế thừa `Collection`.

Framework còn có những tiện ích hỗ trợ cả hai nhánh. Ví dụ, lớp `Collections` có các phương thức `unmodifiableCollection` và `unmodifiableMap`. Vì vậy, **Java Collections Framework**, **interface Collection** và **lớp Collections** là ba tên ở ba phạm vi khác nhau.

Xem cấu trúc chung trong [Collections Framework Overview của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/doc-files/coll-overview.html).

## 4. Ba view kết nối Map với Collection

Một map có thể được nhìn từ ba góc độ mà không cần biến chính nó thành một `Collection`:

| Phương thức | Kiểu trả về | Phần dữ liệu nhìn thấy |
| --- | --- | --- |
| `keySet()` | `Set<K>` | Tập khóa |
| `values()` | `Collection<V>` | Nhóm giá trị |
| `entrySet()` | `Set<Map.Entry<K, V>>` | Tập cặp khóa–giá trị |

### 4.1. Vì sao keySet là Set?

Khóa trong một map không lặp theo quy tắc khóa của map đó. Một view kiểu `Set<K>` thể hiện đúng đặc điểm này.

### 4.2. Vì sao values chỉ là Collection?

Giá trị có thể trùng nhau. Nếu `"book"` và `"bag"` đều có số lượng `3`, `values()` phải phản ánh đủ hai lần xuất hiện đó.

Nếu biến kết quả thành một `Set<V>`, những giá trị bằng nhau có thể bị gộp, làm mất thông tin rằng chúng thuộc những ánh xạ khác nhau.

### 4.3. Vì sao entrySet là Set?

Một entry chứa khóa và giá trị của một ánh xạ. Vì mỗi khóa có tối đa một ánh xạ, tập entry của một map không chứa hai cặp trùng nhau.

Chiều suy luận ngược lại không đúng: một `Set<Map.Entry<K, V>>` bất kỳ vẫn có thể chứa hai cặp cùng khóa nhưng khác giá trị. Chính map chịu trách nhiệm bảo đảm tính duy nhất của khóa; việc kết quả có kiểu `Set` không thay map thực hiện ràng buộc đó.

### 4.4. View là đối tượng liên kết với map gốc

Các collection trả về là **khung nhìn (view)** được map gốc hỗ trợ. Khi nội dung map thay đổi, các view phản ánh nội dung hiện tại đó; không cần gọi lại `keySet()` chỉ để nhận biết khóa vừa được thêm.

Ở hướng ngược lại, một số thao tác sửa được hỗ trợ trên view tác động lên map. Chẳng hạn, xóa một khóa qua `keySet().remove(key)` sẽ xóa cả ánh xạ tương ứng nếu map và view hỗ trợ xóa.

Điều này không có nghĩa view có thể sửa tùy ý:

- Ba view chuẩn này không hỗ trợ thêm bằng `add` hoặc `addAll`.
- Xóa qua `values()` là xóa ánh xạ tương ứng với giá trị bị loại bỏ. Nếu nhiều ánh xạ có giá trị bằng nhau, `remove(value)` chỉ loại một ánh xạ phù hợp; không nên dùng nó thay cho việc chọn chính xác một khóa.
- `Map.Entry.setValue` là thao tác tùy chọn. Entry lấy từ map không cho sửa có thể từ chối nó.
- Entry do `Map.entry(k, v)` tạo không cho sửa bằng `setValue`.

Hành vi và giới hạn của entry được quy định trong [API Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

## 5. Ví dụ Java hoàn chỉnh

Chương trình sau cho thấy sự khác nhau giữa một tập các cặp và map, sau đó kiểm chứng ba view.

Lưu vào **MapFrameworkDemo.java**:

```java
import java.util.Collection;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class MapFrameworkDemo {
    public static void main(String[] args) {
        Set<Map.Entry<String, Integer>> pairs = new HashSet<>();
        pairs.add(Map.entry("pen", 10));
        pairs.add(Map.entry("pen", 12));

        Map<String, Integer> sameKey = new LinkedHashMap<>();
        sameKey.put("pen", 10);
        sameKey.put("pen", 12);

        System.out.println("Pair set size: " + pairs.size());
        System.out.println("Map size for same key: " + sameKey.size());
        System.out.println("Current pen value: " + sameKey.get("pen"));

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("pen", 10);
        stock.put("book", 3);
        stock.put("bag", 3);

        Set<String> keys = stock.keySet();
        Collection<Integer> values = stock.values();
        Set<Map.Entry<String, Integer>> entries = stock.entrySet();

        System.out.println("Initial map: " + stock);
        Integer old = stock.put("pen", 12);
        System.out.println("Previous pen value: " + old);
        System.out.println("After update: " + stock);
        System.out.println("Keys: " + keys);
        System.out.println("Values: " + values);
        System.out.println("Entries: " + entries);

        stock.put("eraser", 2);
        System.out.println("Keys after put: " + keys);

        values.remove(2);
        System.out.println("After values.remove: " + stock);

        keys.remove("book");
        System.out.println("After keys.remove: " + stock);

        Map.Entry<String, Integer> first = entries.iterator().next();
        first.setValue(15);
        System.out.println("After entry.setValue: " + stock);

        try {
            keys.add("ruler");
        } catch (UnsupportedOperationException ex) {
            System.out.println("keySet.add: " + ex.getClass().getSimpleName());
        }

        Map<String, Integer> copy = new LinkedHashMap<>(stock);
        stock.put("pen", 99);
        System.out.println("Map after later change: " + stock);
        System.out.println("Independent map copy: " + copy);
    }
}
```

Biên dịch và chạy bằng JDK có hỗ trợ Java 17:

```shell
javac --release 17 -encoding UTF-8 MapFrameworkDemo.java
java MapFrameworkDemo
```

Stdout:

```text
Pair set size: 2
Map size for same key: 1
Current pen value: 12
Initial map: {pen=10, book=3, bag=3}
Previous pen value: 10
After update: {pen=12, book=3, bag=3}
Keys: [pen, book, bag]
Values: [12, 3, 3]
Entries: [pen=12, book=3, bag=3]
Keys after put: [pen, book, bag, eraser]
After values.remove: {pen=12, book=3, bag=3}
After keys.remove: {pen=12, bag=3}
After entry.setValue: {pen=15, bag=3}
keySet.add: UnsupportedOperationException
Map after later change: {pen=99, bag=3}
Independent map copy: {pen=15, bag=3}
```

### 5.1. Đối chiếu kết quả

**Ba dòng đầu** so sánh hai mô hình:

- Tập `pairs` giữ hai entry khác nhau: `("pen", 10)` và `("pen", 12)`.
- Map `sameKey` chỉ có một khóa `"pen"`, giá trị hiện tại là `12`.

**Lần cập nhật `stock.put("pen", 12)`** trả lại giá trị cũ `10`. Khóa đã có nên map vẫn có ba ánh xạ.

**View `values` in `[12, 3, 3]`**, bảo toàn việc hai khóa khác nhau cùng có giá trị `3`.

**Sau khi thêm `"eraser"`**, biến `keys` đã lấy từ trước vẫn nhìn thấy khóa mới. Đây là bằng chứng view không phải bản sao tách rời.

**Xóa qua view** tác động lên map:

- `values.remove(2)` xóa ánh xạ `"eraser" -> 2`. Giá trị `2` được chọn vì chỉ xuất hiện một lần trong dữ liệu này.
- `keys.remove("book")` xóa ánh xạ ứng với `"book"`.
- Entry đầu của `LinkedHashMap` lúc này là entry của `"pen"`; `setValue(15)` cập nhật giá trị trong map.

**`keySet.add` bị từ chối** bằng `UnsupportedOperationException`, cho thấy việc kết quả là `Set` không bảo đảm mọi thao tác của set đều được hỗ trợ.

**Hai dòng cuối** phân biệt view với bản sao cấu trúc: `new LinkedHashMap<>(stock)` tạo một map riêng chứa các ánh xạ tại thời điểm sao chép. Cập nhật ánh xạ của map gốc sau đó không cập nhật ánh xạ của map bản sao.

`LinkedHashMap` ở ví dụ được tạo bằng constructor mặc định, giữ thứ tự thêm khóa. Cập nhật giá trị của khóa đã có không chuyển vị trí của khóa đó. Không nên dùng thứ tự stdout này làm bảo đảm cho một `HashMap` bất kỳ; xem [API LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

## 6. Áp dụng khi viết API và duyệt dữ liệu

### 6.1. Chọn view theo dữ liệu thực sự cần

Nếu phương thức chỉ cần các giá trị, có thể truyền `map.values()` cho tham số `Collection<V>`. Nếu cần cả khóa lẫn giá trị, dùng `entrySet()`. Nếu cần tra cứu hoặc cập nhật theo khóa, giữ tham số kiểu `Map<K, V>`.

Đoạn minh họa sau nằm trong một phương thức có biến `stock`:

```java
for (Map.Entry<String, Integer> entry : stock.entrySet()) {
    System.out.println(entry.getKey() + " has " + entry.getValue());
}

stock.forEach((key, value) ->
        System.out.println(key + " has " + value));
```

Hai cách đều xử lý các ánh xạ. `Map.forEach` nhận thao tác với cả khóa và giá trị; sự tồn tại của phương thức này không làm `Map` kế thừa `Iterable`.

Không thể viết vòng `for-each` trực tiếp lên một biến chỉ có kiểu `Map`:

```java
// Không biên dịch: Map không phải Iterable.
// for (var item : stock) {
// }
```

Dùng `stock.entrySet()`, `stock.keySet()` hoặc `stock.values()` tùy mục tiêu.

### 6.2. Không ép kiểu để tạo quan hệ kế thừa không tồn tại

Đây là phép gán không hợp lệ:

```java
// Map<String, Integer> stock = new LinkedHashMap<>();
// Collection<?> data = stock; // Không biên dịch.
```

Thay vì ép kiểu vòng qua `Object`, hãy chọn đúng view. `stock.entrySet()` có kiểu `Set<Map.Entry<String, Integer>>`, nên có thể được sử dụng như một `Collection<Map.Entry<String, Integer>>`.

Chuyển đổi view là chọn một cách nhìn dữ liệu; ép kiểu không biến một map thành đối tượng tuân theo hợp đồng `Collection`.

### 6.3. Phân biệt sao chép cấu trúc với sao chép sâu

Bản sao bằng `new LinkedHashMap<>(stock)` có cấu trúc ánh xạ riêng. Tuy nhiên, nó không tự nhân bản các đối tượng khóa và giá trị.

Trong ví dụ, `String` và `Integer` không cho sửa giá trị nội tại, nên sự khác nhau dễ quan sát. Nếu giá trị là một `List` có thể sửa và hai map cùng giữ tham chiếu đến list đó, thay đổi nội dung list có thể nhìn thấy từ cả hai map.

Nếu cần dữ liệu tách rời hoàn toàn, phải xác định chính sách sao chép cho từng loại đối tượng, không suy ra từ constructor sao chép map.

## 7. Lỗi thường gặp

| Cách hiểu hoặc thao tác sai | Vấn đề | Cách tiếp cận phù hợp |
| --- | --- | --- |
| “Không kế thừa Collection thì không thuộc JCF” | Nhầm quan hệ kế thừa với phạm vi framework | Nhìn hai nhánh Collection và Map |
| “Map chỉ là một Set các cặp” | Set các cặp có thể giữ cùng khóa với các giá trị khác nhau | Dùng Map để thể hiện ràng buộc theo khóa |
| “values() là Set vì map không có khóa trùng” | Khóa duy nhất không làm giá trị duy nhất | Giữ kiểu Collection cho nhóm giá trị |
| “Lấy keySet rồi lưu lại là đã chụp dữ liệu” | View vẫn gắn với map gốc | Tạo bản sao khi cần dữ liệu theo thời điểm |
| “Có kiểu Set thì keySet.add chắc chắn dùng được” | Thao tác thêm không được hỗ trợ | Thêm ánh xạ qua Map.put |
| “Xóa value là cách xóa một mã cụ thể” | Nhiều khóa có thể cùng giá trị | Xóa theo khóa nếu ý định gắn với mã |
| “Mọi entry đều hỗ trợ setValue” | Có entry không cho sửa | Kiểm tra hợp đồng của nguồn entry |
| “Map nào cũng in theo thứ tự đã thêm” | Mỗi lớp triển khai có bảo đảm riêng | Chọn lớp theo yêu cầu thứ tự |

Khi đang duyệt các view, cũng không nên tùy tiện thêm hoặc xóa cấu trúc map bằng đường khác. Hành vi phụ thuộc hợp đồng của map và iterator; với các map thông thường, đó có thể là nguồn lỗi `ConcurrentModificationException`. Nếu cần xóa trong lúc duyệt, chọn thao tác được hỗ trợ như `Iterator.remove()` và tuân thủ hợp đồng, thay vì dựa vào việc một lần chạy thử không báo lỗi.

## 8. Bài tập tự kiểm tra

1. Viết hai câu phân biệt “`Map` thuộc framework” và “`Map` kế thừa `Collection`”.
2. Với hai cặp `("A", 1)` và `("A", 2)`, dự đoán kích thước của một `HashSet<Map.Entry<String, Integer>>` và một map được cập nhật lần lượt bằng hai cặp đó.
3. Giải thích vì sao `values()` không có kiểu trả về `Set<V>`.
4. Trong chương trình, thay `keys.remove("book")` bằng `stock.remove("book")`. View `keys` sau đó có còn khóa đó không?
5. Tạo `Map<String, List<String>>`, sao chép bằng constructor của `LinkedHashMap`, rồi sửa list giá trị. Giải thích khác biệt giữa sửa ánh xạ và sửa đối tượng đang được ánh xạ.
6. Đối chiếu hai chữ ký `remove(Object)`: vì sao không thể ghép trực tiếp các hợp đồng hiện có vào một quan hệ kế thừa chỉ bằng thay đổi phần khai báo?

Mục tiêu là giải thích được lựa chọn mô hình và dự đoán đúng tác động của view, thay vì chỉ ghi nhớ câu “Map không extends Collection”.
