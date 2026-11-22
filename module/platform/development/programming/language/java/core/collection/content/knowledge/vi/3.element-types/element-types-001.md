# Generic trong `Collection<E>` và `Map<K,V>`

## 1. Vì sao collection cần generics?

Giả sử một nhóm dữ liệu dùng để lưu tên người. Mã xử lý mong đợi mỗi phần tử là chuỗi để gọi `length()` hoặc `toUpperCase()`. Nếu nhóm đó nhận lẫn số nguyên, lỗi có thể chỉ xuất hiện khi đọc và ép kiểu.

Generics giúp diễn đạt điều kiện về **kiểu dữ liệu** ngay trong khai báo:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Collection<String> names = new ArrayList<>();
names.add("Lan");
// names.add(123); // Không biên dịch: Integer không phù hợp String.

String first = names.iterator().next(); // Không cần ép kiểu thủ công.
```

Với map, cần biểu đạt hai phía của một ánh xạ:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Map<String, Integer> stock = new HashMap<>();
stock.put("BOOK", 10);
// stock.put(123, 10);     // Sai kiểu khóa.
// stock.put("PEN", "ten"); // Sai kiểu giá trị.

Integer quantity = stock.get("BOOK");
```

Generics cho phép dùng cùng một API collection cho nhiều loại dữ liệu, trong khi trình biên dịch kiểm tra tính nhất quán của mỗi cách sử dụng.

Trong bài này, cần phân biệt:

- Tham số kiểu: ký hiệu trong khai báo generic, như `E`, `K`, `V`.
- Đối số kiểu: kiểu được truyền vào khi sử dụng, như `String`, `Integer`.
- Kiểu được tham số hóa: toàn bộ kiểu như `Collection<String>`.
- Đối tượng cài đặt: chẳng hạn một `ArrayList<String>` hoặc `HashMap<String, Integer>`.

Bài dùng Java 17 và tập trung vào generics trong collection/map, không yêu cầu tự xây dựng một thư viện cấu trúc dữ liệu.

## 2. Đọc E, K và V đúng ý nghĩa

### 2.1. E là kiểu phần tử

Trong tên `Collection<E>`, `E` thường được hiểu là “element”. Khi thay `E` bằng `String`, các thao tác liên quan tới phần tử được kiểm tra với kiểu tương ứng.

Ví dụ các chữ ký API, được rút gọn để đọc:

```java
// Phác thảo chữ ký, không phải chương trình độc lập.
interface Collection<E> extends Iterable<E> {
    boolean add(E element);
    Iterator<E> iterator();
}
```

Với `Collection<String>`:

- `add` nhận một tham chiếu phù hợp với `String`.
- `iterator` trả `Iterator<String>`.
- `next` trên iterator trả kiểu `String` tại nơi sử dụng có kiểm tra kiểu.

`List<E>`, `Set<E>`, `Queue<E>` và các cài đặt liên quan tiếp tục truyền kiểu phần tử qua hệ thống API. [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

### 2.2. K và V là hai tham số độc lập

Trong `Map<K, V>`:

- `K`: kiểu khóa (key).
- `V`: kiểu giá trị (value).

`Map<String, Integer>` diễn đạt “tra một giá trị `Integer` bằng khóa dạng `String`”. Khóa và giá trị không bắt buộc có cùng kiểu. Có thể dùng `Map<String, String>` nếu cả hai phía đều là chuỗi; đó là lựa chọn cụ thể, không phải giới hạn của `Map`.

Một số chữ ký:

```java
// Phác thảo chữ ký, không phải khai báo đầy đủ của Map.
V put(K key, V value);
V get(Object key);
Set<K> keySet();
Collection<V> values();
Set<Map.Entry<K, V>> entrySet();
```

`put` dùng `K` và `V` để kiểm tra dữ liệu được đưa vào. `get` trả `V` nhưng đối số truy vấn là `Object`. Đừng tự sửa chữ ký trong suy nghĩ thành `get(K)`. [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 2.3. Chữ E, K, V là quy ước đặt tên

Các chữ này không phải từ khóa với quyền năng riêng. Chúng là tên tham số kiểu trong phạm vi khai báo. `T` cũng thường được dùng cho một kiểu tổng quát.

Không viết `Collection<E>` trong mã sử dụng nếu `E` chưa được khai báo trong phạm vi tương ứng. Khi sử dụng bình thường, truyền kiểu thật:

```java
Collection<String> words = new ArrayList<>();
Map<Long, String> userNames = new HashMap<>();
```

Hai dòng trên là các khai báo minh họa trong phương thức hoặc trường dữ liệu, cần import các kiểu trong `java.util`.

Xem [Generic Types](https://docs.oracle.com/javase/tutorial/java/generics/types.html) để đối chiếu tham số kiểu với đối số kiểu.

## 3. Kiểu phần tử và lớp cài đặt là hai quyết định khác nhau

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> first = new ArrayList<>();
List<String> second = new LinkedList<>();
```

Hai đối tượng có lớp cài đặt khác nhau nhưng cùng được nhìn qua hợp đồng `List<String>`.

- `List` biểu đạt danh sách và API được sử dụng.
- `String` biểu đạt kiểu phần tử.
- `ArrayList` hoặc `LinkedList` quyết định cách cài đặt và nhiều đặc tính khi chạy.

Đổi lớp cài đặt không tự đổi phần tử từ `String` sang một kiểu khác. Đổi đối số kiểu cũng không chỉ là đổi cách lưu: `List<String>` và `List<Integer>` là hai kiểu tham số hóa khác nhau ở thời điểm kiểm tra mã.

Tương tự:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Map<String, Integer> counts = new LinkedHashMap<>();
```

`Map` xác định mô hình khóa–giá trị; `String, Integer` xác định hai kiểu dữ liệu; `LinkedHashMap` quyết định thêm các đặc tính như thứ tự duyệt theo chèn trong cấu hình mặc định.

Generic không tự quy định tính không trùng, thứ tự, khả năng sửa hay tính an toàn nhiều luồng. Những thuộc tính đó vẫn phải đọc từ hợp đồng giao diện, cài đặt và cách tạo đối tượng.

## 4. Diamond và suy luận kiểu

### 4.1. Không cần lặp lại đối số kiểu ở hai vế

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> names = new ArrayList<>();
Map<String, Integer> counts = new HashMap<>();
```

`<>` được gọi là diamond. Trình biên dịch suy luận các đối số kiểu cho constructor từ ngữ cảnh.

Có thể viết dài hơn:

```java
List<String> names = new ArrayList<String>();
```

Nhưng trong tình huống này phần `String` ở vế phải là lặp lại không cần thiết. Diamond không tắt generics và không làm mất kiểm tra kiểu.

### 4.2. var không suy luận từ các lần thêm về sau

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
var values = new ArrayList<>();
values.add("text");
values.add(99);

System.out.println(values); // [text, 99]
```

Ở đây không có kiểu đích `List<String>` và constructor không nhận dữ liệu giúp ràng buộc kiểu. Kết quả suy luận là `ArrayList<Object>`. Lần thêm `"text"` sau đó không làm biến thành `ArrayList<String>`.

Nếu muốn phần tử là chuỗi:

```java
// Hai lựa chọn khai báo minh họa; cần import java.util.*.
List<String> explicitContract = new ArrayList<>();
var explicitArgument = new ArrayList<String>();
```

`var` vẫn là suy luận kiểu tĩnh cho biến cục bộ; nó không có nghĩa biến nhận mọi kiểu động. [Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html)

Đọc kỹ cả kiểu đích, đối số constructor và đối số kiểu trước khi kết luận compiler đã suy luận điều gì.

## 5. Kiểu tham chiếu, boxing và null

Đối số kiểu generic phải là kiểu tham chiếu. Không viết:

```java
// Ví dụ cố ý không biên dịch.
// Collection<int> numbers;
// Map<String, double> prices;
```

Dùng wrapper:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Collection<Integer> numbers = new ArrayList<>();
numbers.add(10); // Autoboxing int thành Integer.

Integer boxed = numbers.iterator().next();
int primitive = boxed; // Unboxing Integer thành int.
```

Các đối số kiểu cũng có thể là kiểu mảng hoặc kiểu tham số hóa khác, vì chúng là kiểu tham chiếu. Ví dụ `List<int[]>` là hợp lệ; `int[]` là một kiểu mảng tham chiếu, khác với kiểu nguyên thủy `int`.

Generics không mã hóa bảo đảm khác `null` trong Java thông thường:

- `Collection<String>` có thể nhận `null` về mặt kiểm tra kiểu.
- Cài đặt có thể cho hoặc không cho `null`.
- Unboxing một `Integer` là `null` gây `NullPointerException`.
- Giá trị `null` không trở thành một đối tượng `String` hay `Integer`.

Xem [Restrictions on Generics](https://docs.oracle.com/javase/tutorial/java/generics/restrictions.html) về giới hạn đối số nguyên thủy. Chính sách chấp nhận giá trị cụ thể vẫn là một lớp hợp đồng riêng.

## 6. Vì sao `Collection<Integer>` không phải `Collection<Number>`?

`Integer` là kiểu con của `Number`, nhưng quan hệ đó không tự lan vào tham số kiểu:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Collection<Integer> integers = new ArrayList<>();
// Collection<Number> numbers = integers; // Không biên dịch.
```

Nếu phép gán này được phép, mã qua biến `numbers` có thể thêm `Double` vào cùng đối tượng. Khi mã khác đọc collection đó như chỉ chứa `Integer`, giả định ban đầu bị phá vỡ.

Đó là lý do các tham số kiểu này có tính bất biến (invariance). Không dùng ép kiểu để lách lỗi rồi coi dữ liệu đã an toàn.

Điều vẫn hợp lệ là quan hệ kế thừa giữ nguyên đối số kiểu:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
ArrayList<Integer> implementation = new ArrayList<>();
List<Integer> list = implementation;
Collection<Integer> collection = list;
```

Các biến đang cùng giữ loại phần tử `Integer`.

Quy tắc cũng áp dụng độc lập cho hai phía map:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Map<String, Integer> source = new HashMap<>();
// Map<Object, Number> target = source; // Không biên dịch.

Map<Object, Number> copy = new HashMap<>();
copy.putAll(source); // Sao chép dữ liệu vào đối tượng khác có kiểu phù hợp.
```

Phép gán và sao chép phần tử không phải cùng một hành động. `putAll` được thiết kế nhận nguồn có khóa/giá trị là kiểu con phù hợp. [Generics, Inheritance, and Subtypes](https://docs.oracle.com/javase/tutorial/java/generics/inheritance.html)

## 7. `Collection<Object>`, `Collection<?>` và raw Collection

Ba cách viết này không tương đương:

| Kiểu | Ý nghĩa | Đọc phần tử | Thêm phần tử khác null |
| --- | --- | --- | --- |
| `Collection<Object>` | Collection có kiểu phần tử là `Object` | Nhận `Object` | Có thể thêm tham chiếu của các kiểu phù hợp với `Object` nếu đối tượng hỗ trợ |
| `Collection<?>` | Collection của một kiểu chưa biết | Nhận `Object` | Không tự thêm một kiểu cụ thể vì không biết kiểu thật |
| `Collection` raw | Bỏ đối số kiểu trong tương tác mã cũ | Nhận `Object` | Có thể tạo lời gọi unchecked, làm mất bảo đảm kiểu |

`Collection<Object>` không phải “biến nhận mọi collection”. Nó không nhận gán từ `Collection<String>` vì invariance.

`Collection<?>` có thể tham chiếu `Collection<String>` hoặc `Collection<Integer>` để thực hiện thao tác không cần biết kiểu cụ thể:

```java
// Đoạn khai báo phương thức; cần import java.util.Collection.
static void printElements(Collection<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Không được gọi `values.add("A")` trong phương thức đó, vì `values` có thể thực tế là collection của `Integer`.

Tuy nhiên, `?` không tự tạo một view bất biến. Những thao tác như `clear` hoặc `remove(Object)` vẫn có thể được gọi nếu đối tượng hỗ trợ. `add(null)` có thể hợp lệ về kiểu, nhưng chính sách `null` của đối tượng vẫn có thể từ chối. Đừng dùng wildcard như từ đồng nghĩa với “không thể thay đổi”.

Tham khảo [Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/wildcards.html).

## 8. Wildcard khi đọc từ nguồn và ghi vào đích

### 8.1. extends: nhận nguồn thuộc một kiểu con chưa biết

Một hàm tính tổng không cần sửa các phần tử thành kiểu khác; nó chỉ cần đọc mỗi phần tử dưới dạng `Number`:

```java
// Đoạn khai báo phương thức; cần import java.util.Collection.
static double sum(Collection<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

Có thể truyền `Collection<Integer>`, `Collection<Double>` hoặc `Collection<Number>`. Hợp đồng của ví dụ yêu cầu nguồn và các phần tử khác `null`.

Không thêm `Double` vào `values`: kiểu thật có thể là `Integer`. `? extends Number` có nghĩa “một kiểu cụ thể nào đó là Number hoặc kiểu con của Number”, không phải “mọi loại Number đều được ghi vào đây”. [Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html)

### 8.2. super: nhận đích có thể chứa kiểu cần ghi

```java
// Đoạn khai báo phương thức; cần import java.util.Collection.
static void appendIntegers(Collection<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

Hàm có thể nhận `Collection<Integer>`, `Collection<Number>` hoặc `Collection<Object>`. Cả ba đều có thể giữ các `Integer` được thêm vào, miễn đối tượng hỗ trợ thao tác và các ràng buộc khác.

Khi đọc qua biến `destination`, kiểu an toàn tổng quát là `Object`. Không thể khẳng định mọi phần tử đã có là `Integer`: một `Collection<Number>` có thể chứa `Double` trước đó. [Lower Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

### 8.3. Áp dụng vừa đủ

Quy tắc nhớ thường dùng là PECS: nguồn cung cấp phần tử dùng `extends`, đích nhận phần tử dùng `super`.

Nó hỗ trợ thiết kế tham số, không phải lệnh buộc mọi biến hay mọi giá trị trả về phải dùng wildcard. Một API trả `List<String>` thường dễ dùng hơn một giá trị trả `List<? extends String>` không có lý do cụ thể.

Wildcard giải quyết quan hệ kiểu tại lời gọi. Nó không tự cấp quyền sửa, không bỏ giới hạn `null` và không làm thao tác nguyên tử.

## 9. Generic method liên kết kiểu giữa đầu vào và kết quả

Nếu cần bảo toàn quan hệ kiểu, có thể khai báo tham số kiểu của phương thức:

```java
// Đoạn khai báo phương thức; cần import java.util.*.
static <T> List<T> copyOfElements(Collection<? extends T> source) {
    return new ArrayList<>(source);
}
```

Đọc từ trái sang phải:

- `<T>` khai báo tham số kiểu của riêng phương thức.
- `List<T>` là kiểu kết quả.
- Nguồn cung cấp phần tử kiểu `T` hoặc kiểu con của `T`.
- Kết quả là danh sách mới có thể chứa `T`.

Ví dụ:

```java
// Đoạn minh họa trong phương thức, với copyOfElements đã khai báo.
Collection<Integer> source = List.of(1, 2, 3);
List<Number> result = copyOfElements(source);
result.add(2.5);
```

Ngữ cảnh đích góp phần cho suy luận kiểu `T` là `Number`. Nguồn `Integer` phù hợp, và danh sách mới giữ các tham chiếu phần tử đó. Thêm `Double` vào `result` không sửa collection nguồn.

Không phải mỗi lần gọi đều tạo ra một lớp hay một bản phương thức riêng cho `Integer` và `Number` ở runtime. Đây là cơ chế kiểm tra và suy luận kiểu của mã generic.

Xem [Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html).

## 10. Generic trong các view của Map

Với `Map<String, Integer> counts`:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Set<String> keys = counts.keySet();
Collection<Integer> values = counts.values();
Set<Map.Entry<String, Integer>> entries = counts.entrySet();
```

Ba kiểu kết quả diễn đạt ba góc nhìn:

- `keySet`: các khóa không trùng theo hợp đồng map.
- `values`: các giá trị có thể trùng, nên không phải `Set<V>`.
- `entrySet`: các entry giữ cả khóa và giá trị với đúng hai kiểu.

Duyệt entry:

```java
// Đoạn minh họa với counts đã được khởi tạo.
for (Map.Entry<String, Integer> entry : counts.entrySet()) {
    String word = entry.getKey();
    Integer count = entry.getValue();
    System.out.println(word + "=" + count);
}
```

`Map.Entry<K, V>` tiếp tục mang quan hệ kiểu của map. Không cần ép kết quả `getKey` thành `String` hoặc `getValue` thành `Integer`. [Map.Entry API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html)

Các view này gắn với map nguồn, không mặc nhiên là bản sao. Generics mô tả kiểu phần tử, không thay đổi quan hệ nguồn–view hay mức hỗ trợ các thao tác sửa.

### get nhận Object có nghĩa gì?

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Map<String, Integer> values = new HashMap<>();
values.put("A", 1);

Integer found = values.get("A"); // 1
Integer absent = values.get(123); // null với HashMap trong ví dụ này.
```

Việc `get(123)` biên dịch không làm `123` trở thành khóa hợp lệ để `put` vào `Map<String, Integer>`. Truy vấn và đưa dữ liệu vào có chữ ký khác nhau. Một cài đặt khác có thể đưa ra ràng buộc hoặc ngoại lệ khác cho đối số truy vấn.

`get` có thể trả `null` khi thiếu khóa; một số map còn cho giá trị `null`. Vì vậy, gán trực tiếp vào `int` có thể gây `NullPointerException` khi unboxing. Kiểu `V` không loại bỏ trường hợp không có kết quả.

## 11. Kiểu lồng nhau: đọc từ ngoài vào trong

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Map<String, List<Integer>> scores = new LinkedHashMap<>();
scores.put("An", List.of(8, 9));

List<Integer> studentScores = scores.get("An");
Integer first = studentScores.get(0);
```

Ý nghĩa:

1. Map có khóa `String`.
2. Mỗi giá trị là một `List<Integer>`.
3. Mỗi phần tử trong danh sách là `Integer`.

Không được viết `scores.put("An", 8)`: giá trị cần là cả danh sách. Cũng không được dùng `List<String>` làm giá trị.

Mỗi tầng có hợp đồng riêng. Map sửa được không có nghĩa danh sách giá trị sửa được; ở đây `List.of` không hỗ trợ thêm phần tử. Map không có khóa cũng có thể làm `scores.get(...)` trả `null` trước khi tới thao tác danh sách.

Khi khai báo lồng nhau quá dài hoặc khó gắn với ý nghĩa nghiệp vụ, cân nhắc tạo một kiểu dữ liệu có tên, chẳng hạn bản ghi điểm của học viên. Đừng dùng `Map<String, Object>` để né thiết kế rồi phân tán ép kiểu khắp ứng dụng.

## 12. Raw type, type erasure và giới hạn runtime

### 12.1. Raw type làm yếu kiểm tra kiểu

```java
// Minh họa cố ý không an toàn trong một phương thức.
// Cần import java.util.*; có cảnh báo raw/unchecked.
List<String> words = new ArrayList<>();
List raw = words;
raw.add(123);

// String first = words.get(0); // ClassCastException khi đọc thành String.
```

Lỗi có thể xuất hiện xa nơi chèn dữ liệu sai. Dùng generics xuyên suốt giúp đưa lỗi về gần chỗ viết mã hơn.

Không đổi `List<String>` thành raw `List` chỉ để một phương thức chấp nhận nhiều loại danh sách. Dùng tham số kiểu hoặc wildcard đúng mục đích. [Raw Types](https://docs.oracle.com/javase/tutorial/java/generics/rawTypes.html)

### 12.2. Không có một lớp ArrayList riêng cho mỗi đối số kiểu

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(words.getClass().equals(numbers.getClass())); // true
```

Với type erasure, các cách sử dụng này dựa trên cùng lớp runtime. Compiler kiểm tra ràng buộc generic và thêm các phép chuyển kiểu cần thiết tại nơi phù hợp.

Điều đó không có nghĩa mọi thông tin generic đều bị xóa khỏi mọi metadata hoặc generics “không có tác dụng”. Nó có nghĩa đối tượng `ArrayList` thông thường không giữ một lớp runtime riêng chứng minh tham số phần tử là `String` hay `Integer`. [Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html)

### 12.3. Kiểm tra cấu trúc khác kiểm tra từng phần tử

Với một nguồn chưa biết được khai báo bằng `Object`:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
Object candidate = List.of("A", "B");

if (candidate instanceof List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
// candidate instanceof List<String> không dùng được để chứng minh
// một Object bất kỳ là danh sách chỉ chứa String.
```

`instanceof List<?>` kiểm tra đây là một đối tượng thuộc họ danh sách, không xác minh toàn bộ nội dung là `String`. Nếu dữ liệu đến từ nguồn ngoài, cần kiểm tra và chuyển đổi từng phần tử để tạo kết quả có hợp đồng mong muốn.

Tương tự, không tạo mảng bằng `new List<String>[10]`. Những giới hạn liên quan tới kiểu không hiện thực đầy đủ ở runtime được giải thích trong [Non-Reifiable Types](https://docs.oracle.com/javase/tutorial/java/generics/nonReifiableVarargsType.html).

Bài không dùng unchecked cast như một cách “xác minh” dữ liệu: ép kiểu không duyệt từng phần tử để làm dữ liệu an toàn.

## 13. Chương trình hoàn chỉnh

Lưu thành `GenericCollectionMapDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class GenericCollectionMapDemo {
    private static <T> List<T> copyOfElements(
            Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    private static void appendIntegers(
            Collection<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    private static double sum(Collection<? extends Number> values) {
        double total = 0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    private static Map<String, Integer> countWords(
            Collection<String> words) {
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String word : words) {
            counts.merge(word, 1, Integer::sum);
        }
        return counts;
    }

    public static void main(String[] args) {
        Collection<String> words =
                new ArrayList<>(List.of("java", "map", "java"));
        String first = words.iterator().next();
        System.out.println("First word: " + first);

        Map<String, Integer> counts = countWords(words);
        System.out.println("Counts: " + counts);
        for (Map.Entry<String, Integer> entry : counts.entrySet()) {
            System.out.println(entry.getKey() + "=" + entry.getValue());
        }
        System.out.println("Keys: " + counts.keySet());
        System.out.println("Values: " + counts.values());

        Collection<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = copyOfElements(integers);
        numbers.add(2.5);
        System.out.println("Numbers: " + numbers);
        System.out.println("Sum: " + sum(numbers));

        List<Object> destination = new ArrayList<>();
        appendIntegers(destination);
        System.out.println("Destination: " + destination);

        Map<String, List<Integer>> scores = new LinkedHashMap<>();
        scores.put("An", List.of(8, 9));
        scores.put("Binh", List.of(7, 10));
        System.out.println("Nested: " + scores);
        int firstScore = scores.get("An").get(0);
        System.out.println("First score of An: " + firstScore);

        var inferredObjects = new ArrayList<>();
        inferredObjects.add("text");
        inferredObjects.add(99);
        System.out.println("Diamond with var: " + inferredObjects);

        List<String> strings = new ArrayList<>();
        List<Integer> otherIntegers = new ArrayList<>();
        System.out.println("Same runtime class: "
                + strings.getClass().equals(otherIntegers.getClass()));

        Collection<?> unknown = List.of("A", "B");
        for (Object value : unknown) {
            System.out.println("Unknown element: " + value);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked GenericCollectionMapDemo.java
java GenericCollectionMapDemo
```

Mã đã được kiểm tra với `--release 17` trên JDK mới hơn, không có cảnh báo unchecked. Các đoạn cố ý không biên dịch hoặc raw type trong phần giải thích không nằm trong chương trình này.

Stdout:

```text
First word: java
Counts: {java=2, map=1}
java=2
map=1
Keys: [java, map]
Values: [2, 1]
Numbers: [1, 2, 3, 2.5]
Sum: 8.5
Destination: [10, 20]
Nested: {An=[8, 9], Binh=[7, 10]}
First score of An: 8
Diamond with var: [text, 99]
Same runtime class: true
Unknown element: A
Unknown element: B
```

### Giải thích kết quả

- `Collection<String>` làm iterator trả `String` mà không cần ép kiểu thủ công.
- Hàm đếm dùng `Map<String, Integer>`: từ là khóa, số lần xuất hiện là giá trị.
- `merge(word, 1, Integer::sum)` đặt `1` nếu chưa có giá trị; nếu có giá trị phù hợp trong ví dụ, cộng thêm `1`. Kết quả là `java=2` và `map=1`.
- `entrySet`, `keySet` và `values` truyền đúng kiểu dữ liệu của map ra ngoài.
- `copyOfElements` tạo danh sách `Number` mới từ nguồn `Integer`. Sau khi thêm `2.5`, tổng là `8.5`.
- Đích `List<Object>` nhận được các `Integer` từ hàm có tham số `? super Integer`.
- Map lồng nhau giữ danh sách điểm; hai lần `get` đi qua hai tầng kiểu.
- `var` kết hợp `new ArrayList<>()` trong ngữ cảnh này tạo `ArrayList<Object>`, nên có cả chuỗi và số.
- Hai `ArrayList` tham số hóa khác nhau vẫn có cùng lớp runtime.
- `Collection<?>` cho duyệt dưới dạng `Object` mà không cần biết đối số kiểu cụ thể.

Chương trình dùng `LinkedHashMap` để thứ tự in theo chèn có thể đối chiếu; không dựa vào thứ tự không được cam kết của `HashMap`. [LinkedHashMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

## 14. Những điều generics không tự bảo đảm

| Mong đợi | Generics có tự bảo đảm không? | Cần thêm điều gì? |
| --- | --- | --- |
| Phần tử đúng kiểu qua lời gọi có kiểm tra kiểu | Có, trong phạm vi các quy tắc kiểu của chương trình | Tránh raw type và unchecked cast không an toàn |
| Phần tử khác `null` | Không | Chính sách và kiểm tra đầu vào |
| Collection sửa được | Không | Hợp đồng đối tượng/factory |
| Phần tử không trùng | Không | Chọn mô hình `Set` hoặc quy tắc nghiệp vụ |
| Thứ tự duyệt ổn định | Không | Giao diện/cài đặt có bảo đảm thích hợp |
| Nhiều luồng truy cập an toàn | Không | Đồng bộ và cấu trúc concurrent phù hợp |
| Các phần tử so sánh được | Không chỉ nhờ cùng một kiểu cha | `Comparable` hoặc comparator phù hợp |
| Giá trị nghiệp vụ hợp lệ | Không | Kiểu dữ liệu và validation |
| Bản sao sâu | Không | Thiết kế sao chép phần tử riêng |
| Nguồn ngoài được xác minh sau một cast | Không | Kiểm tra/chuyển đổi dữ liệu có chủ đích |

Generics là một lớp bảo đảm quan trọng, nhưng không thay thế toàn bộ hợp đồng dữ liệu.

## 15. Lỗi thường gặp

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Viết `Collection<E>` khi `E` chưa được khai báo | `E` không tự có sẵn | Truyền kiểu thật hoặc khai báo tham số kiểu |
| Viết `List<int>` | Generic không nhận kiểu nguyên thủy | Dùng `Integer` |
| Gán `List<Integer>` sang `List<Number>` | Tham số kiểu bất biến | Dùng wildcard hoặc tạo bản sao phù hợp |
| Dùng `Collection<Object>` để nhận mọi collection | Không nhận `Collection<String>` | Dùng `Collection<?>` nếu chỉ cần quan sát |
| Dùng raw `Map` để né lỗi kiểu | Mất liên kết kiểu khóa–giá trị | Khai báo `Map<K, V>` phù hợp |
| Coi `? extends Number` cho thêm mọi `Number` | Kiểu thật có thể hẹp hơn | Dùng nguồn chỉ đọc kiểu Number; chọn `super` cho đích |
| Coi `? super Integer` đọc ra chắc chắn là `Integer` | Nguồn có thể giữ dữ liệu của kiểu cha | Đọc dưới dạng `Object` nếu chưa có bảo đảm khác |
| Cho rằng `?` tạo tính bất biến | Wildcard không ngăn mọi thao tác sửa | Chọn quyền sửa theo hợp đồng riêng |
| Dùng `var x = new ArrayList<>()` rồi kỳ vọng `String` | Không có ngữ cảnh ràng buộc đó | Nêu đối số kiểu hoặc kiểu đích |
| Coi `get(123)` biên dịch nghĩa `123` là khóa được `put` | Chữ ký truy vấn dùng `Object` | Phân biệt API truy vấn và API đưa dữ liệu vào |
| Dùng cast để chứng minh mọi phần tử đúng kiểu | Cast không xác minh nội dung từng phần tử | Chuyển đổi/kiểm tra tại ranh giới nguồn |

## 16. Tự kiểm tra và thực hành

### Câu hỏi

1. Trong `Collection<String>`, đâu là tham số kiểu và đâu là đối số kiểu?
2. `Map<String, List<Integer>>` có kiểu khóa và giá trị là gì?
3. Vì sao `Collection<Integer>` không gán trực tiếp được cho `Collection<Number>`?
4. `Collection<Object>` khác `Collection<?>` ở khả năng nhận gán và thêm phần tử thế nào?
5. Khi nào dùng `? extends Number`, khi nào dùng `? super Integer`?
6. `var x = new ArrayList<>();` trong ví dụ không có ngữ cảnh bổ sung suy luận kiểu gì?
7. Vì sao `Map.get` có thể nhận đối số không cùng `K` mà vẫn biên dịch?
8. `List<String>` có bảo đảm không có `null` và sửa được không?
9. Tại sao raw type làm lỗi có thể xuất hiện muộn?
10. Hai `ArrayList` có đối số kiểu khác nhau có cần lớp runtime khác nhau không?

### Bài tập

- Thêm một lời gọi sai kiểu vào chương trình hoàn chỉnh, biên dịch và giải thích lỗi trước khi bỏ lời gọi đó.
- Viết hàm in mọi phần tử bằng `Collection<?>`; kiểm tra với danh sách chuỗi và tập số nguyên.
- Cho hàm `sum` nhận `List<Integer>` rồi `List<Double>` mà không đổi chữ ký.
- Cho `appendIntegers` nhận `List<Integer>`, `List<Number>` và `List<Object>`; giải thích vì sao đều phù hợp về kiểu.
- Viết hàm sao chép map có chữ ký `static <K, V> Map<K, V> copyMap(Map<? extends K, ? extends V> source)`, trả một `LinkedHashMap` mới.
- Tạo `Map<String, List<Integer>>` cho hai học viên và duyệt bằng `Map.Entry` mà không ép kiểu.
- Bật `-Xlint:unchecked` trong một bài thử raw type, xác định ranh giới tạo cảnh báo và sửa để không còn cảnh báo.

### Gợi ý đối chiếu

1. `E` là tham số trong khai báo `Collection<E>`; `String` là đối số được truyền khi sử dụng.
2. Khóa `String`, giá trị `List<Integer>`; bên trong danh sách là `Integer`.
3. Nếu cho gán, mã có thể đưa phần tử kiểu Number khác Integer vào cùng đối tượng.
4. `Collection<Object>` giữ Object, còn `Collection<?>` quan sát một kiểu chưa biết; không phải cùng một kiểu.
5. Dùng `extends` cho nguồn cần đọc như Number; `super` cho đích cần nhận Integer.
6. `ArrayList<Object>`.
7. Chữ ký là `get(Object)`; điều đó không đổi kiểu khóa nhận bởi `put`.
8. Không; đó là các thuộc tính hợp đồng khác.
9. Bỏ qua kiểm tra kiểu có thể cho phần tử sai lọt vào rồi bị phát hiện lúc đọc.
10. Không; các đối số kiểu này được xử lý qua cơ chế type erasure.
