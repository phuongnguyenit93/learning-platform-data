# `Map.copyOf`: Chữ ký generic của khóa, giá trị và bản đồ nguồn (Java 10+)

## 1. Tổng quan

`Map.copyOf` là phương thức static được bổ sung từ **Java 10**, nằm trong giao diện `java.util.Map`. Nó nhận một bản đồ nguồn và trả về một bản đồ **không thể sửa qua API Map** (*unmodifiable map*) chứa các ánh xạ khóa–giá trị ở thời điểm sao chép.

Ví dụ:

```java
Map<String, Integer> source = Map.of("A", 10, "B", 20);
var copied = Map.copyOf(source);
```

Hai câu lệnh trên giả định có `import java.util.Map;` và được đặt trong phương thức. `copied` có **kiểu tĩnh `Map<String, Integer>`**. Trình biên dịch vẫn kiểm tra đúng kiểu khóa `String` và giá trị `Integer`, dù sử dụng `var`.

Điểm quan trọng nhất của bài không phải cách gọi `copyOf`, mà là **chữ ký generic với hai tham số kiểu `K`, `V` và hai wildcard ở đối số nguồn**. Nhờ đó, Java có thể cho một kết quả có kiểu khóa/giá trị rộng hơn nguồn mà không cần ép kiểu không an toàn.

## 2. Chữ ký chính thức của `Map.copyOf`

```java
static <K, V> Map<K, V> copyOf(Map<? extends K, ? extends V> map)
```

Đây là chữ ký API, không phải đoạn định nghĩa cần tự viết lại.

| Thành phần | Ý nghĩa |
| --- | --- |
| `static` | Gọi bằng `Map.copyOf(...)`, không cần có một đối tượng `Map` để gọi. |
| `<K, V>` | Hai tham số kiểu của chính **phương thức generic**. `K` là kiểu khóa và `V` là kiểu giá trị được chọn cho lời gọi. |
| `Map<K, V>` | Kiểu tĩnh trả về: Map có khóa thuộc `K`, giá trị thuộc `V`. |
| `Map<? extends K, ? extends V>` | Map nguồn có kiểu khóa là một subtype nào đó của `K` và kiểu giá trị là một subtype nào đó của `V`. |
| `map` | Đối số nguồn chứa các ánh xạ cần sao chép. |

Một vài cách diễn đạt tương đương:

- `? extends K`: khóa nguồn đọc ra có thể sử dụng dưới kiểu `K`.
- `? extends V`: giá trị nguồn đọc ra có thể sử dụng dưới kiểu `V`.
- Hai tham số kiểu được **suy luận độc lập**. Nếu khóa là `String`, giá trị là `Integer`, có thể chọn `K=String, V=Integer` hoặc một cặp supertype phù hợp như `K=CharSequence, V=Number`, tùy **ngữ cảnh của lời gọi**.
- `K` và `V` phải là kiểu tham chiếu trong Java generics, ví dụ `Integer`, không phải primitive `int`.

Đừng nhầm `Map<? extends K, ? extends V>` là một kiểu “Map có thể tự đổi khóa và giá trị”. Đây là **ràng buộc lúc biên dịch** trên những đối tượng đã có.

### Minh họa luồng suy luận

```text
Map nguồn: Map<String, Integer>
                  |
                  v
copyOf(Map<? extends K, ? extends V>)
            String <: K
            Integer <: V
                  |
                  v
Chọn K và V theo kiểu nguồn và kiểu đích (nếu có)
                  |
                  v
Kết quả: Map<K, V>
                  |
                  v
Biến var nhận kiểu kết quả đã được suy luận
```

Ký hiệu `<:` có nghĩa “là subtype của”. Trong ví dụ, `String` là subtype của `CharSequence` và `Integer` là subtype của `Number`.

## 3. Tại sao hai wildcard `extends` lại cần thiết?

### 3.1. Generic Java là invariant

`String` triển khai `CharSequence`, còn `Integer` kế thừa `Number`. Tuy nhiên, điều đó **không** làm `Map<String, Integer>` trở thành subtype của `Map<CharSequence, Number>`:

```java
Map<String, Integer> scores = Map.of("An", 10);
// Map<CharSequence, Number> direct = scores; // Lỗi biên dịch.
```

Lý do: nếu phép gán trực tiếp như vậy được phép trên một map có thể sửa, biến `direct` có thể chấp nhận một khóa `StringBuilder` và một giá trị `Double`, làm sai ràng buộc mà biến `scores` đang công bố. Vì thế Java không cho phép cách mở rộng type argument trực tiếp đó.

### 3.2. `Map.copyOf` chấp nhận nguồn hẹp nhờ wildcard

```java
Map<String, Integer> scores = Map.of("An", 10);

Map<CharSequence, Number> widened = Map.copyOf(scores);
```

Đây là **Java hợp lệ**. Khi gọi phương thức, trình biên dịch chọn `K=CharSequence` và `V=Number` theo kiểu đích. Nguồn `Map<String,Integer>` phù hợp với tham số `Map<? extends CharSequence, ? extends Number>`.

Kết quả trả về có kiểu tĩnh `Map<CharSequence,Number>`, trong khi khóa `"An"` vẫn là object `String` và giá trị `10` vẫn là `Integer`. **Không có bước biến đổi object sang lớp khác** khi “mở rộng” type argument.

### 3.3. Có thể mở rộng từng phía độc lập

```java
Map<String, Integer> scores = Map.of("An", 10);

Map<CharSequence, Integer> widerKey = Map.copyOf(scores);
Map<String, Number> widerValue = Map.copyOf(scores);
Map<Object, Object> widerBoth = Map.copyOf(scores);
```

Cả ba cách đều biên dịch được. Ràng buộc đối số nguồn yêu cầu **khóa nguồn phù hợp `K`** và **giá trị nguồn phù hợp `V`**; không bắt buộc mở rộng cả hai phía cùng lúc.

Vì sao không dùng `? super K`, `? super V`? Vì `Map.copyOf` **đọc dữ liệu từ nguồn để tạo kết quả**. Một Map chứa khóa/giá trị thuộc supertype không cho phép kết luận rằng tất cả khóa/giá trị đó đều là subtype `K`/`V`. Nguyên tắc PECS (*Producer Extends, Consumer Super*) giúp nhớ chiều wildcard thích hợp: nguồn đang cung cấp dữ liệu, do đó `extends`.

## 4. `var` và kiểu đích tường minh có thể dẫn đến kết quả khác nhau

### 4.1. `var` lấy kiểu từ biểu thức bên phải

```java
Map<String, Integer> scores = Map.of("An", 10);
var inferred = Map.copyOf(scores); // Map<String, Integer>
```

Khi không có yêu cầu kiểu đích rộng hơn, `K` và `V` được suy ra từ tham số kiểu đã biết của nguồn; `var` nhận kiểu tĩnh của biểu thức trả về. `var` không có nghĩa “không biết kiểu” và không làm Map dùng raw type.

### 4.2. Kiểu ở vế trái cung cấp *target type*

```java
Map<CharSequence, Number> widened = Map.copyOf(scores);
```

Ở đây vế trái cung cấp ngữ cảnh kiểu cho việc suy luận lời gọi `copyOf`. Điều này **khác** với tạo `var inferred` rồi thử gán sau:

```java
var inferred = Map.copyOf(scores);  // Map<String, Integer>
// Map<CharSequence, Number> invalid = inferred; // Lỗi invariance.
```

Tính hợp lệ của `Map<CharSequence,Number> widened = Map.copyOf(scores)` xuất phát từ **suy luận tham số kiểu của lời gọi phương thức**, không xuất phát từ việc `Map<String,Integer>` có thể gán trực tiếp sang Map rộng hơn.

### 4.3. Muốn dùng `var` mà chọn kiểu rộng: *explicit type witness*

```java
var widened = Map.<CharSequence, Number>copyOf(scores);
// Kiểu tĩnh: Map<CharSequence, Number>
```

Phần `<CharSequence, Number>` ngay sau `Map.` chỉ định tường minh `K` và `V` của **lời gọi phương thức generic**. Đây không phải cast và không làm thay đổi object khóa/giá trị.

Trong mã thực tế, có thể chọn một trong hai cách:

```java
Map<CharSequence, Number> a = Map.copyOf(scores);
var b = Map.<CharSequence, Number>copyOf(scores);
```

Cả hai có cùng **kiểu tĩnh** và hợp đồng unmodifiable. Cách đầu thường dễ đọc khi kiểu kết quả là phần quan trọng của API; cách thứ hai hữu ích khi muốn giữ `var` nhưng vẫn quyết định rõ type arguments.

## 5. Nguồn có wildcard: chú ý capture conversion

Một trường hợp nâng cao thường bị viết sai là:

```java
Map<String, ? extends Number> source = Map.of("A", 10);
var copy = Map.copyOf(source);
```

Giá trị của nguồn được khai báo là “một subtype chưa biết của `Number`”, không nhất thiết đúng kiểu `Number`. Khi suy luận kiểu từ nguồn như vậy, Java có thể sử dụng một **capture type**; trong thông báo của compiler nó được mô tả dạng `CAP#1 extends Number`.

Vì generic invariant, **không nên khẳng định** biến `copy` trong câu lệnh `var` đã trở thành `Map<String,Number>`:

```java
Map<String, ? extends Number> source = Map.of("A", 10);
var copy = Map.copyOf(source);

// Map<String, Number> bad = copy;
// Lỗi: kiểu giá trị capture không tự động trở thành Number.
```

Lỗi này đã được kiểm chứng bằng `javac --release 17`: compiler thông báo `Map<String,CAP#1>` không thể gán cho `Map<String,Number>`.

**Cách sửa đúng: cung cấp kiểu đích tại chính lời gọi:**

```java
Map<String, Number> widened = Map.copyOf(source);
```

hoặc chỉ định type witness:

```java
var widened = Map.<String, Number>copyOf(source);
```

Hai cách này đều biên dịch vì kiểu của mỗi giá trị nguồn vẫn là subtype của `Number`. Không được nhầm chúng với phép gán sau khi `var copy` đã chốt kiểu capture.

Wildcard cũng có thể xuất hiện ở cả hai phía:

```java
Map<? extends CharSequence, ? extends Number> source =
        Map.of("A", 10);

Map<CharSequence, Number> result = Map.copyOf(source);
```

Đây là lời gọi hợp lệ, miễn các ràng buộc subtype của khóa và giá trị phù hợp.

**Lưu ý:** wildcard `extends` không tự biến nguồn thành một map bất biến. Dù bạn không thể tùy ý gọi `put` qua một reference có wildcard, object nguồn vẫn có thể bị sửa qua một reference khác nếu nó là map mutable.

## 6. Suy luận khóa–giá trị của `Map.of` kết hợp `Map.copyOf`

Với factory `Map.of`:

```java
var source = Map.of("count", 10); // Map<String, Integer>
var copied = Map.copyOf(source);  // Map<String, Integer>
```

- `"count"` là `String` nên `K` thường được suy ra `String`.
- Literal `10` là `int`, được boxing thành `Integer` để làm generic value, nên `V` là `Integer`.
- `Map.copyOf` nhận đầu vào `Map<String,Integer>` và tiếp tục suy luận kiểu cho Map kết quả.

### Trường hợp map trống

```java
var empty = Map.copyOf(Map.of());
```

Ở ngữ cảnh độc lập này không có khóa/giá trị hoặc kiểu đích cụ thể; kiểu tĩnh của `empty` là `Map<Object,Object>`.

Nếu cần map trống có generic cụ thể:

```java
Map<String, Integer> empty1 = Map.copyOf(Map.of());
var empty2 = Map.<String, Integer>copyOf(Map.of());
```

Cả hai là `Map<String,Integer>`. Nếu không có map nguồn thật sự, `Map.<String,Integer>of()` cũng là lựa chọn ngắn gọn để tạo map trống unmodifiable.

Nhớ rằng `Map<String,int>` **không hợp lệ**: generic Java nhận type argument là **kiểu tham chiếu**, chẳng hạn `Integer`, không phải primitive `int`.

## 7. Chữ ký generic của một helper tự định nghĩa

Chữ ký hai wildcard có thể sử dụng lại cho một phương thức API của ứng dụng:

```java
static <K, V> Map<K, V> snapshot(
        Map<? extends K, ? extends V> source) {
    return Map.copyOf(source);
}
```

Đây là đoạn **phương thức đặt trong một lớp có import `java.util.Map`**, không phải chương trình độc lập.

Sử dụng:

```java
Map<String, Integer> scores = Map.of("A", 10);

var exact = snapshot(scores); // Map<String, Integer>
Map<CharSequence, Number> broad = snapshot(scores);
```

Điều này giúp thiết kế một API tổng quát: phương thức nhận map nguồn với cặp type arguments **có thể hẹp hơn** cặp kiểu đầu ra. Nếu cần giữ kiểu khóa/giá trị chính xác, chọn target type hẹp; nếu một API bên ngoài cần `Map<CharSequence,Number>` thì có thể suy luận kiểu rộng hơn theo target type.

Cần tách rõ hai mục tiêu: **loại dữ liệu mà API công bố** và **đối tượng thực tế mà Map lưu trữ**. Nâng kiểu generic qua helper không clone, cast hay biến đổi các object bên trong.

## 8. Bản sao không sửa được khác bản đồ nguồn như thế nào?

### 8.1. Kết quả không cho `put` hoặc `remove`

```java
Map<String, Integer> source = Map.of("A", 10);
Map<String, Integer> copied = Map.copyOf(source);

// copied.put("B", 20); // Biên dịch được, ném
                         // UnsupportedOperationException khi chạy.
```

Chữ ký `Map<K,V>` **không chứa một dấu hiệu generic nói rằng Map bất biến**. Việc phương thức mutator bị từ chối là **hợp đồng runtime của `copyOf`**, khác với kiểm tra kiểu generic lúc biên dịch.

### 8.2. Sao chép cấu trúc khác với unmodifiable view

```java
var source = new java.util.HashMap<String, Integer>();
source.put("A", 10);

var copy = Map.copyOf(source);
var view = java.util.Collections.unmodifiableMap(source);

source.put("B", 20);

System.out.println(copy.size()); // 1
System.out.println(view.size()); // 2
```

`Map.copyOf` không phản ánh thao tác thêm ánh xạ vào nguồn **sau khi tạo kết quả**. Ngược lại, `Collections.unmodifiableMap` là **view được backing bởi map gốc**: không thể `put` thông qua view nhưng vẫn quan sát được sửa đổi thực hiện từ `source`.

### 8.3. Không deep-copy khóa hoặc giá trị

`Map.copyOf` **không tạo clone** cho mỗi object khóa/giá trị. Nếu một giá trị mutable đổi trạng thái qua reference khác, thay đổi đó vẫn có thể nhìn thấy từ kết quả. Với khóa mutable, việc sửa thuộc tính tham gia `equals`/`hashCode` có thể phá vỡ khả năng tìm kiếm theo khóa. Ưu tiên kiểu khóa có trạng thái ổn định.

Đây là vấn đề **tham chiếu object và mô hình dữ liệu**, độc lập với generic `K`/`V` và hai wildcard `extends`.

### 8.4. Giới hạn khác của hợp đồng

- `Map.copyOf(null)` hoặc nguồn chứa khóa/giá trị `null` sẽ ném `NullPointerException`.
- Kết quả không bảo đảm **thứ tự duyệt** entry, key hoặc value. Không in toàn bộ map để dùng làm đầu ra kiểm thử cố định giữa các JDK.
- Kết quả là **value-based instance**: có thể tái sử dụng map nguồn đã là unmodifiable phù hợp; không dựa vào `copy == source` hay `copy != source`.
- Dùng `Map.equals` hoặc `hashCode` cho so sánh nội dung, không dùng identity như hợp đồng nghiệp vụ hoặc khóa đồng bộ.
- `copyOf` không tạo **atomic snapshot** khi một nguồn mutable thiếu đồng bộ đang bị sửa đồng thời; đồng bộ hóa hoặc quản lý tính nhất quán của nguồn là trách nhiệm của người gọi.
- Không suy luận rằng kết quả có lớp runtime `HashMap` hoặc một class nội bộ cố định từ chữ ký trả về `Map<K,V>`.

Các giới hạn trên không làm thay đổi chữ ký generic; chúng mô tả **hành vi runtime thực sự** của đối tượng mà phương thức trả về.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu nội dung dưới đây vào tệp **`MapCopyGenericDemo.java`**:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class MapCopyGenericDemo {
    static <K, V> Map<K, V> snapshot(
            Map<? extends K, ? extends V> source) {
        return Map.copyOf(source);
    }

    public static void main(String[] args) {
        Map<String, Integer> source = new HashMap<>();
        source.put("A", 10);
        source.put("B", 20);

        var inferred = Map.copyOf(source);
        Map<String, Integer> inferredProof = inferred;

        Map<CharSequence, Number> widened = Map.copyOf(source);

        var explicit = Map.<CharSequence, Number>copyOf(source);
        Map<CharSequence, Number> explicitProof = explicit;

        var throughMethod = snapshot(source);
        Map<String, Integer> methodProof = throughMethod;

        System.out.println("inferredA=" + inferred.get("A"));
        System.out.println("widenedB=" + widened.get("B"));
        System.out.println("explicitA=" + explicit.get("A"));
        System.out.println(
                "methodEquals=" + throughMethod.equals(inferred)
        );

        var view = Collections.unmodifiableMap(source);
        source.put("C", 30);
        System.out.println("copySize=" + inferred.size());
        System.out.println("viewSize=" + view.size());

        try {
            inferred.put("X", 99);
        } catch (UnsupportedOperationException expected) {
            System.out.println("putRejected=true");
        }

        try {
            Map.copyOf(Collections.singletonMap("x", null));
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }

        var empty = Map.copyOf(Map.of());
        Map<Object, Object> emptyProof = empty;
        System.out.println("emptySize=" + empty.size());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 MapCopyGenericDemo.java
java MapCopyGenericDemo
```

**Stdout chính xác:**

```text
inferredA=10
widenedB=20
explicitA=10
methodEquals=true
copySize=2
viewSize=3
putRejected=true
nullRejected=true
emptySize=0
```

Giải thích từng điểm:

1. Các dòng gán `inferredProof`, `explicitProof`, `methodProof` và `emptyProof` giúp **kiểm chứng kiểu tĩnh ngay khi biên dịch**. Nếu kết quả suy luận không tương thích, `javac` sẽ báo lỗi trước khi chương trình chạy.
2. `inferred` có kiểu `Map<String,Integer>`; `widened` và `explicit` là `Map<CharSequence,Number>`; nhưng dữ liệu được tra bằng khóa `"A"`, `"B"` giống nhau.
3. `throughMethod` được suy luận thông qua helper generic và bằng nội dung với `inferred`, nên `methodEquals=true`.
4. `copySize=2` và `viewSize=3` cho thấy `Map.copyOf` bảo toàn snapshot cấu trúc, trong khi `Collections.unmodifiableMap` vẫn theo dõi nguồn.
5. `putRejected=true` chứng minh unmodifiable; `nullRejected=true` chứng minh từ chối giá trị `null`.
6. `emptySize=0` có thể kiểm tra khi chạy; dòng `Map<Object,Object> emptyProof = empty;` chỉ tồn tại để **kiểm tra generic lúc biên dịch**.

Đoạn mã đã được biên dịch bằng `javac --release 17` và chạy bằng JDK hiện hành. Không cần preview feature.

## 10. Các lỗi dễ mắc

**Lỗi A — Nhầm quan hệ subtype của phần tử với subtype của Map.**

```java
Map<String, Integer> source = Map.of("A", 10);
// Map<CharSequence, Number> bad = source; // Sai.
Map<CharSequence, Number> good = Map.copyOf(source); // Đúng.
```

**Lỗi B — Để `var` suy luận xong rồi muốn gán sang generic rộng.**

```java
var copy = Map.copyOf(source); // Map<String,Integer>
// Map<CharSequence,Number> bad = copy; // Sai.
var good = Map.<CharSequence,Number>copyOf(source); // Đúng.
```

**Lỗi C — Bỏ qua wildcard capture của nguồn.**

```java
Map<String, ? extends Number> source = Map.of("A", 10);
var copy = Map.copyOf(source);
// Map<String,Number> bad = copy; // Sai: capture type.
Map<String,Number> good = Map.copyOf(source); // Đúng.
```

Các đoạn trên là những **tình huống riêng biệt**, giả định có import và đặt bên trong phương thức. Không ghép nguyên xi các khai báo trùng tên `source`, `copy` vào một khối duy nhất.

**Lỗi D — Dùng raw type hoặc unchecked cast để cưỡng ép kiểu trả về.** Tránh `Map raw = ...` và cast không kiểm tra; chữ ký wildcard cho phép diễn đạt đa số trường hợp nguồn hẹp hơn đích mà vẫn kiểm tra được lúc biên dịch.

**Lỗi E — Nghĩ `Map.copyOf` trả một Map có thể sửa.** `put`/`remove` bị từ chối ở runtime dù các đối số đúng generic type.

**Lỗi F — Nghĩ wildcard làm clone hoặc tự bảo đảm an toàn luồng.** `? extends` chỉ phục vụ tương thích kiểu; kết quả không deep-copy khóa/giá trị và không tự đồng bộ hóa việc duyệt một nguồn bị sửa đồng thời.

## 11. Bài tập tự kiểm tra

**Câu 1:** Vì sao chữ ký nhận `Map<? extends K, ? extends V>` mà trả về `Map<K,V>`?  
**Đáp án:** Để nhận một map có khóa/giá trị thuộc subtype của các kiểu kết quả `K,V`, cho phép phương thức sao chép dữ liệu mà không yêu cầu hai cặp type arguments khớp hoàn toàn.

**Câu 2:** `Map<String,Integer> s = Map.of("A",1); Map<CharSequence,Number> x = Map.copyOf(s);` có hợp lệ không?  
**Đáp án:** Có. Kiểu đích cho phép suy luận `K=CharSequence` và `V=Number`; khóa nguồn `String` và giá trị `Integer` thỏa các wildcard.

**Câu 3:** `var x = Map.copyOf(Map.of());` có kiểu gì?  
**Đáp án:** Trong ngữ cảnh này là `Map<Object,Object>` vì không có đối số hoặc target type cụ thể cho khóa và giá trị.

**Câu 4:** Sau `var x = Map.copyOf(source)` với nguồn `Map<String, ? extends Number>`, tại sao `Map<String,Number> y=x;` có thể sai?  
**Đáp án:** `var` có thể suy luận kiểu giá trị capture của wildcard; generic invariant không cho gán Map có capture subtype trực tiếp thành `Map<String,Number>`. Sử dụng `Map<String,Number> y = Map.copyOf(source);` để có target typing ngay tại lời gọi.

**Câu 5:** `Map.copyOf` có chuyển `Integer` thành một đối tượng `Number` mới khi trả về `Map<String,Number>` không?  
**Đáp án:** Không. Type widening là quan hệ tĩnh, không tự biến đổi hay deep-copy object.

**Câu 6:** Có thể thay đổi kết quả bằng `put` nếu `K,V` hợp lệ không?  
**Đáp án:** Không. Generic kiểm tra loại khóa/giá trị, còn `Map.copyOf` bảo đảm kết quả không sửa được; `put` sẽ ném `UnsupportedOperationException`.

## 12. Ghi nhớ

1. Chữ ký chính xác là **`static <K,V> Map<K,V> copyOf(Map<? extends K,? extends V> map)`**.
2. `K` và `V` là **kiểu khóa/giá trị của kết quả**; các wildcard `extends` cho phép **nguồn có kiểu hẹp hơn**.
3. Generic Java invariant: không gán trực tiếp `Map<String,Integer>` sang `Map<CharSequence,Number>`, nhưng có thể dùng **`Map.copyOf` cùng target typing**.
4. `var` suy ra kiểu cuối của biểu thức; muốn điều khiển kiểu trả về có thể dùng khai báo đích tường minh hoặc **type witness** `Map.<K,V>copyOf(...)`.
5. Nguồn có wildcard có thể làm kết quả dùng **capture type**; không tự đồng nhất capture với upper bound.
6. `Map.copyOf` trả unmodifiable Map, không nhận `null`, không bảo đảm thứ tự/identity, không deep-copy các object và không tự bảo đảm atomic snapshot khi nguồn đang bị sửa đồng thời.

## Tài liệu tham khảo chính thức

- Java SE 26 API — `Map.copyOf`: chữ ký, tham số generic và bảo đảm của unmodifiable maps: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)
- Java SE 26 API — `Map.of`, `Map.ofEntries` và các quy tắc về khóa/giá trị: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html
- Java Language Specification — Parameterized Types, Subtyping, Capture Conversion, Type Inference: https://docs.oracle.com/javase/specs/jls/se25/html/index.html
- Dev.java — Generics, Wildcards và Type Inference: https://dev.java/learn/generics/
- Java SE 26 API — `Collections.unmodifiableMap`: view được backing bởi nguồn: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)
