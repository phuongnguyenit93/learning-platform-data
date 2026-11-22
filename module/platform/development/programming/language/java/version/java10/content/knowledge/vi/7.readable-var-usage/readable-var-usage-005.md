# Lựa chọn kiểu tường minh khi kiểu của lời gọi không rõ trong Java 10+

## 1. Vấn đề: `var` hợp lệ nhưng người đọc khó nhận ra kiểu nào?

Từ Java 10, `var` cho phép **suy luận kiểu của biến cục bộ** từ biểu thức khởi tạo. Đây là kiểm tra kiểu tại **thời điểm biên dịch**: biến vẫn có một kiểu tĩnh cụ thể và Java vẫn báo lỗi nếu gán giá trị không phù hợp.

```java
var result = service.findById(id); // Kiểu của result là gì?
```

Dòng trên có thể biên dịch hoàn toàn chính xác, nhưng **không đủ thông tin ngay tại chỗ** để người đọc biết `result` là `Customer`, `Optional<Customer>`, `CompletableFuture<Customer>` hay một kiểu khác. Muốn biết, họ phải mở khai báo của `service.findById` hoặc dựa vào công cụ IDE.

Nếu chữ ký trả về là `Optional<Customer>`, khai báo tường minh nói rõ điều đó:

```java
Optional<Customer> result = service.findById(id);
```

Hai ví dụ này là **đoạn minh họa**, giả sử lớp `Customer`, biến `service`, `id` và phương thức `findById` đã được định nghĩa. Điều quan trọng là lựa chọn **cách thể hiện thông tin kiểu**, không phải `var` khiến Java suy luận sai: nếu lời gọi thực sự trả về `Optional<Customer>` thì biến `var` cũng nhận đúng kiểu đó.

**Nguyên tắc thực hành:** Khi một lời gọi phương thức, factory hoặc chuỗi lời gọi che khuất kiểu kết quả, khai báo kiểu tường minh thường giúp đọc và bảo trì mã tốt hơn. Khi kiểu đã hiện rõ trong biểu thức, `var` có thể làm mã gọn mà vẫn dễ hiểu.

## 2. Kiểu của `var` dựa vào chữ ký phương thức, không dựa vào tên hay dữ liệu runtime

Giả sử một API có chữ ký:

```java
static Map<String, List<Integer>> loadScores() {
    // ... tạo và trả về Map<String, List<Integer>>
}
```

Đây là **mã rút gọn để nêu chữ ký**, chưa phải phương thức biên dịch độc lập. Trong một phương thức khác:

```java
var scores = loadScores();
```

Kiểu tĩnh của `scores` là **`Map<String, List<Integer>>`**, do đó là kiểu được khai báo sau khi phân giải lời gọi `loadScores()`. Không quan trọng implementation thực tế trả về `LinkedHashMap` hoặc `HashMap`: `var` không dùng `getClass()` để quyết định kiểu.

Cách viết tường minh:

```java
Map<String, List<Integer>> scores = loadScores();
```

Khi biểu thức khởi tạo đã có kiểu cụ thể, khai báo tường minh **thường không thay đổi giá trị và hành vi runtime**; nó làm rõ **hợp đồng tĩnh** của biến ngay tại vị trí sử dụng. Với các lời gọi generic phụ thuộc vào kiểu đích, kiểu tường minh **còn có thể ảnh hưởng kết quả suy luận type argument**; trường hợp đó được trình bày ở phần 5.

Tên phương thức chỉ là gợi ý, không thay thế chữ ký:

- `getItems()` có thể trả về `List<Item>`, `Stream<Item>` hoặc `Iterable<Item>`.
- `findItem()` có thể trả về `Item`, `Optional<Item>` hoặc một wrapper nghiệp vụ.
- `load()` có thể trả về một đối tượng, một collection, một kiểu tham số generic hoặc kết quả bất đồng bộ.

**Không suy diễn kiểu chỉ từ tên phương thức.** Khi cần tính chính xác, xem chữ ký, Javadoc hoặc thông tin kiểu do IDE hiển thị.

## 3. Khi nào nên chọn kiểu tường minh?

### 3.1. Tên phương thức không nói rõ cấu trúc kết quả

```java
// Giả định API có các chữ ký tương ứng:
Map<String, List<Order>> grouped = repository.loadGrouped();
Optional<Customer> customer = repository.findCustomer(customerId);
CompletableFuture<List<Order>> orders = client.fetchOrders();
```

Đây là **đoạn minh họa**, cần định nghĩa `Order`, `Customer`, `repository`, `client`, `customerId` và các import để chạy. Kiểu được viết bên trái cho biết người đọc phải xử lý kết quả như thế nào: map theo nhóm, giá trị tùy chọn, hay tác vụ trả về danh sách trong tương lai.

Với `var grouped = repository.loadGrouped();`, thông tin ấy nằm ở nơi khác. Người đọc khó phân biệt **cấu trúc dữ liệu** với **hành vi của lời gọi** nếu chỉ nhìn dòng khai báo.

### 3.2. Kiểu generic nhiều tầng ảnh hưởng cách xử lý

```java
Optional<List<String>> names = findNames();
```

Người đọc biết ngay kết quả có thể vắng mặt (`Optional`) và, nếu có, chứa một `List<String>`. Khi đổi sang `var names = findNames();`, mã vẫn type-safe nhưng cần xem khai báo `findNames()` mới nhận ra cả hai tầng kiểu.

Không nhất thiết phải kéo dài kiểu vô hạn. Nếu kiểu lặp lại nhiều lần hoặc tên API đã cực kỳ rõ, có thể chọn `var`. Tiêu chí là người đọc có hiểu nhanh **kiểu và ý nghĩa của dữ liệu** ở ngữ cảnh hiện tại không.

### 3.3. Muốn thể hiện abstraction mà biến phải tuân theo

Ví dụ:

```java
List<String> names = new ArrayList<>();
names = new LinkedList<>(); // hợp lệ: cả hai triển khai List<String>
```

Ngược lại:

```java
var names = new ArrayList<String>(); // kiểu tĩnh: ArrayList<String>
// names = new LinkedList<String>(); // lỗi: LinkedList<String> không phải ArrayList<String>
```

Điểm khác biệt xuất phát từ **kiểu tĩnh**: Java suy luận `ArrayList<String>` khi thấy biểu thức `new ArrayList<String>()`. Nó không tự chọn `List<String>` chỉ vì người lập trình muốn phụ thuộc vào interface.

Nếu hợp đồng bạn muốn bảo toàn là `List`, `Map`, `Collection` hoặc một interface nghiệp vụ, kiểu tường minh có thể diễn đạt chủ ý thiết kế. Nếu cần các phương thức riêng của implementation, kiểu cụ thể cũng có thể là lựa chọn đúng.

### 3.4. Khi khai báo là ranh giới mà người khác sẽ đọc hoặc sửa

Ở đầu phương thức, ngay sau một lời gọi service/repository/client, kiểu tường minh có thể tiết kiệm thời gian truy tìm chữ ký. Ví dụ:

```java
Map<String, List<Integer>> groupedIds = loadScores();
```

Khi bảo trì, kiểu tường minh giúp dễ nhận ra rằng mỗi khóa ánh xạ đến **một danh sách số nguyên**, tránh các giả định mơ hồ như “đây là một map có giá trị đơn”. Viết tường minh là lựa chọn về khả năng đọc mã, không phải yêu cầu bắt buộc của compiler đối với lời gọi trên.

## 4. Khi nào `var` vẫn là lựa chọn rõ ràng?

Không phải lời gọi nào cũng cần kiểu tường minh. Xét các biểu thức đủ tự mô tả:

```java
var ids = new ArrayList<Integer>();           // ArrayList<Integer> hiện rõ
var byName = new HashMap<String, Long>();      // HashMap<String, Long> hiện rõ
var names = List.of("An", "Bình");             // List<String> dễ suy ra từ các giá trị
var count = 10;                                // int rõ ràng
var message = "Ready";                         // String rõ ràng
```

Đặc biệt, khi kiểu dài bị lặp nguyên vẹn giữa hai vế, `var` loại bỏ trùng lặp:

```java
HashMap<String, List<Integer>> groups =
        new HashMap<String, List<Integer>>();

var groups2 = new HashMap<String, List<Integer>>();
```

Dòng thứ hai ngắn hơn mà vẫn thể hiện đầy đủ kiểu tại nơi khai báo. Tuy nhiên, nếu việc công khai interface `Map<String, List<Integer>>` là quan trọng, có thể ưu tiên:

```java
Map<String, List<Integer>> groups = new HashMap<>();
```

Đừng biến “dùng `var` cho mọi chỗ hợp lệ” hoặc “không bao giờ dùng `var`” thành luật cứng. Mục tiêu là **diễn đạt đúng ý nghĩa và giúp người đọc hiểu dữ liệu nhanh**.

## 5. Trường hợp đặc biệt: kiểu tường minh có thể ảnh hưởng suy luận generic

Đây là điểm kỹ thuật rất đáng lưu ý. Với một số lời gọi generic, **kiểu đích** ở bên trái dấu `=` là một phần ngữ cảnh suy luận. Khi dùng `var`, biểu thức khởi tạo không nhận target type từ kiểu khai báo bên trái.

### 5.1. Phương thức factory rỗng

```java
List<String> names = Collections.emptyList();   // List<String>
var unknownNames = Collections.emptyList();     // List<Object>
var explicitNames = Collections.<String>emptyList(); // List<String>
```

Các dòng này cần `import java.util.Collections;` và `import java.util.List;`.

- Dòng 1: `List<String>` làm kiểu đích, nên lời gọi generic có thể suy luận tham số kiểu `T = String`.
- Dòng 2: Không có đối số phần tử và không có kiểu đích cho biểu thức, nên lời gọi suy luận `T = Object`; biến có kiểu `List<Object>`.
- Dòng 3: Type witness `<String>` cung cấp kiểu trực tiếp cho lời gọi; `var` suy luận `List<String>`.

Cả ba giá trị đều là danh sách rỗng, nhưng **kiểu tĩnh** khác nhau. `Collections.emptyList()` trả về danh sách không thể thêm phần tử; dùng type witness không thay đổi hợp đồng đó.

Tương tự:

```java
Optional<String> a = Optional.empty(); // Optional<String>
var b = Optional.empty();              // Optional<Object>
var c = Optional.<String>empty();      // Optional<String>

List<Integer> x = List.of();           // List<Integer>
var y = List.of();                     // List<Object>
var z = List.<Integer>of();            // List<Integer>
```

Với lời gọi không có thông tin đủ để suy luận, kiểu tường minh hoặc type witness giúp tránh `Object` ngoài ý muốn.

### 5.2. Diamond `<>` khi khởi tạo collection

```java
List<String> words = new ArrayList<>(); // List<String>
var unknownWords = new ArrayList<>();   // ArrayList<Object>
var knownWords = new ArrayList<String>(); // ArrayList<String>
```

Trong `List<String> words = new ArrayList<>()`, kiểu đích giúp constructor suy luận phần tử là `String`. Với `var unknownWords = new ArrayList<>()`, không có ngữ cảnh nào chọn `String`, nên suy luận `Object`.

```java
var unknownWords = new ArrayList<>();
unknownWords.add("A");
unknownWords.add(123); // hợp lệ vì kiểu phần tử đã là Object
```

Lệnh `add("A")` không khiến compiler quay lại sửa kiểu từ `Object` thành `String`. Kiểu của biến được chốt tại khai báo.

Tuy vậy, diamond **không phải lúc nào** cũng suy ra `Object`:

```java
var copy = new ArrayList<>(List.of("A", "B")); // ArrayList<String>
```

Ở đây, đối số constructor cung cấp thông tin `String`. Cần xét **toàn bộ lời gọi và chữ ký API**, không kết luận chỉ từ việc có diamond.

### 5.3. Khi viết kiểu tường minh mà lời gọi không tương thích

```java
// List<String> bad = Collections.<Integer>emptyList(); // lỗi kiểu
List<String> good = Collections.<String>emptyList();   // hợp lệ
```

Kiểu tường minh không phải phép ép kiểu tùy ý. Trình biên dịch vẫn bắt lỗi khi type argument của kết quả không thể gán cho biến. Mọi ràng buộc generic và tính invariant của `List<T>` vẫn được áp dụng.

## 6. Không nhầm kiểu biểu thức với lớp đối tượng ở runtime

Giả sử API trả về một kiểu tổng quát:

```java
static Number readNumber() {
    return Integer.valueOf(7);
}
```

Trong một phương thức:

```java
var number = readNumber(); // kiểu tĩnh: Number
Number alsoNumber = readNumber(); // cũng là Number

var concrete = Integer.valueOf(7); // kiểu tĩnh: Integer
```

Đối tượng thực tế ở dòng đầu có thể là `Integer`, nhưng kiểu của lời gọi `readNumber()` theo chữ ký là `Number`. Vì thế `var number` và `Number alsoNumber` đều được kiểm tra theo `Number`.

Nếu có hai overload:

```java
static String describe(Number x) { return "Number"; }
static String describe(Integer x) { return "Integer"; }
```

Thì:

```java
var number = readNumber();       // Number
var concrete = Integer.valueOf(7); // Integer
System.out.println(describe(number));   // Number
System.out.println(describe(concrete)); // Integer
```

Đây là các đoạn minh họa cần đặt trong một lớp/phương thức thích hợp. Chọn overload dựa trên **kiểu tĩnh ở compile time**, không dựa vào lớp runtime của đối tượng.

Tương tự, nếu lời gọi API trả về `Map<String, List<Integer>>`, dù implementation đang là `LinkedHashMap`, `var result = loadScores()` vẫn có kiểu `Map<String, List<Integer>>`. Khi chọn kiểu tường minh, hãy ghi **kiểu đúng theo hợp đồng API**; đừng đoán kiểu từ đối tượng cụ thể.

## 7. Chuỗi lời gọi dài, tên biến và độ rõ ràng

Một chain có nhiều bước có thể che khuất kiểu kết quả:

```java
var grouped = items.stream()
        .filter(Item::active)
        .collect(Collectors.groupingBy(Item::category));
```

Giả sử `Item` có các phương thức tương ứng và `items` là một collection thích hợp. Đoạn trên minh họa, chưa phải chương trình độc lập.

Nếu cấu trúc kết quả quan trọng cho logic bên dưới, khai báo kiểu đích có thể làm rõ:

```java
Map<String, List<Item>> grouped = items.stream()
        .filter(Item::active)
        .collect(Collectors.groupingBy(Item::category));
```

Trong ví dụ này giả sử `category()` trả về `String`. Ngoài việc giúp người đọc, kiểu đích còn có thể tham gia vào suy luận generic cho biểu thức phía phải.

Ngược lại, nếu ý nghĩa của tên biến rất rõ và kiểu cụ thể chỉ là chi tiết tạm thời, `var` vẫn phù hợp. Mức độ rõ ràng phải được đánh giá trong bối cảnh: lời gọi có dễ tra chữ ký không, kiểu có quan trọng cho logic không, và có nhiều kiểu kết quả khác nhau dễ nhầm hay không.

Một cách cải thiện khác là **đặt tên phương thức/biến chính xác**. Kiểu tường minh và tên tốt bổ sung cho nhau; thay `get()` bằng tên như `loadGroupedOrders()` thường giúp ngay cả khi giữ `var`.

## 8. Các biểu thức cần kiểu đích: tường minh là bắt buộc hoặc hữu ích

Bên cạnh lời gọi generic, một số biểu thức Java cần target type để được kiểm tra kiểu đúng:

```java
Runnable task = () -> System.out.println("Done");
// var task = () -> System.out.println("Done"); // không biên dịch

Comparator<String> order = String::compareTo;
// var order = String::compareTo; // không biên dịch

String missing = null;
// var missing = null; // không biên dịch: không suy luận được kiểu từ null
```

Các dòng trên cần `import java.util.Comparator;`. `Runnable` thuộc `java.lang`.

Đây là các trường hợp khác với `var result = someMethod()`. Lời gọi phương thức có thể đã có kiểu trả về, còn lambda, method reference hoặc literal `null` đơn lẻ không cung cấp đủ kiểu độc lập cho `var`.

Cũng cần nhớ rằng **`var` chỉ dùng ở những vị trí ngôn ngữ cho phép**, như biến cục bộ có khởi tạo, enhanced `for` và một số tham số lambda từ Java 11; không thể dùng để thay kiểu trả về phương thức hoặc kiểu trường của lớp. Nếu cần khai báo kiểu trong API công khai, viết kiểu tường minh.

## 9. Ví dụ Java 17+ đầy đủ, chạy được

Lưu thành tệp `ClearTypesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class ClearTypesDemo {

    static Map<String, List<Integer>> loadScores() {
        var values = new LinkedHashMap<String, List<Integer>>();
        values.put("core", List.of(10, 20));
        return values;
    }

    static Optional<List<String>> findNames() {
        return Optional.of(List.of("An", "Binh"));
    }

    static Number readNumber() {
        return Integer.valueOf(7);
    }

    static String describe(Integer x) {
        return "Integer";
    }

    static String describe(Number x) {
        return "Number";
    }

    public static void main(String[] args) {
        Map<String, List<Integer>> scores = loadScores();
        Optional<List<String>> names = findNames();

        var inferredScores = loadScores(); // cũng là Map<String, List<Integer>>
        var number = readNumber();         // Number, không phải Integer

        var rawEmpty = Collections.emptyList();        // List<Object>
        List<String> typedEmpty = Collections.emptyList(); // List<String>
        var hintedEmpty = Collections.<String>emptyList(); // List<String>

        var noHint = new ArrayList<>(); // ArrayList<Object>
        noHint.add("Java");
        noHint.add(10);

        List<String> withTarget = new ArrayList<>();
        withTarget.add("Java");

        System.out.println("scores=" + scores);
        System.out.println("names=" + names.orElse(List.of()));
        System.out.println("inferred.size=" + inferredScores.size());
        System.out.println("overload=" + describe(number));
        System.out.println("empty sizes=" + rawEmpty.size()
                + "," + typedEmpty.size() + "," + hintedEmpty.size());
        System.out.println("noHint=" + noHint + ", withTarget=" + withTarget);
    }
}
```

Biên dịch và chạy:

```bash
javac ClearTypesDemo.java
java ClearTypesDemo
```

Đầu ra:

```text
scores={core=[10, 20]}
names=[An, Binh]
inferred.size=1
overload=Number
empty sizes=0,0,0
noHint=[Java, 10], withTarget=[Java]
```

**Giải thích chương trình:**

- `scores` và `names` dùng kiểu tường minh để công khai cấu trúc kết quả của các phương thức có tên tương đối ngắn.
- `inferredScores` dùng `var` nhưng có cùng kiểu `Map<String, List<Integer>>` với `scores` do `loadScores()` trả về kiểu đó.
- `number` có kiểu `Number` và chọn overload `describe(Number)`. Giá trị runtime là một `Integer` không làm thay đổi điều này.
- `rawEmpty` được suy ra là `List<Object>`, trong khi `typedEmpty` và `hintedEmpty` có kiểu `List<String>`.
- `noHint` có kiểu `ArrayList<Object>` nên chứa được cả chuỗi và số nguyên; `withTarget` là `List<String>` nhờ kiểu đích tường minh.
- `loadScores()` dùng `LinkedHashMap` để thứ tự in kết quả ổn định theo thứ tự thêm khóa, giúp đối chiếu stdout dễ dàng.

## 10. Checklist chọn kiểu cho một dòng khai báo

Trước khi quyết định viết `var`, có thể tự hỏi:

1. **Chỉ nhìn biểu thức bên phải có biết được kiểu quan trọng không?** `new ArrayList<String>()` khá rõ, nhưng `client.fetch()` hoặc `repository.find()` thường không.
2. **Kiểu generic có nhiều tầng hoặc có ý nghĩa nghiệp vụ không?** Nếu có, viết `Optional<List<Order>>` hoặc `Map<Key, List<Value>>` có thể tiết kiệm công tra cứu.
3. **Có cần bộc lộ interface/supertype thay cho implementation không?** Nếu có, dùng `List<T>`, `Map<K,V>` hoặc interface nghiệp vụ tường minh.
4. **Lời gọi generic có dựa vào target type để suy luận không?** Với `Collections.emptyList()` hoặc `new ArrayList<>()` không có thông tin khác, kiểu tường minh giúp tránh suy luận `Object` ngoài ý muốn.
5. **Có biểu thức nào cần target type về mặt cú pháp không?** Lambda, method reference, literal `null` là những trường hợp tiêu biểu.
6. **Người bảo trì có cần mở định nghĩa API để đoán kiểu ở dòng này không?** Nếu có, cân nhắc làm rõ ngay tại nơi khai báo.

Tránh dùng kiểu tường minh như một thói quen máy móc khi biểu thức đã thể hiện rõ kiểu và phần lặp chỉ làm dòng dài thêm. Cũng tránh lạm dụng `var` chỉ để giảm số ký tự trong các dòng gọi API khó hiểu.

## 11. Lỗi thường gặp

| Cách hiểu hoặc cách viết | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `var data = service.load();` rồi đoán `data` là `List<String>` | Tên phương thức không xác định kiểu. | Xem chữ ký; khai báo `List<String> data` nếu đúng API và giúp làm rõ. |
| Nghĩ `var` là kiểu động | Sai: `var` là suy luận kiểu tĩnh lúc biên dịch. | Kiểm tra kiểu thực của biểu thức khởi tạo. |
| Nghĩ `var result = loadScores()` suy ra `LinkedHashMap` từ implementation | Kiểu lời gọi theo chữ ký là `Map<String, List<Integer>>`. | Dựa vào kiểu trả về khai báo của phương thức. |
| `var empty = Collections.emptyList();` rồi coi là `List<String>` | Thiếu target type và đối số cụ thể. | `List<String> empty = Collections.emptyList();` hoặc `var empty = Collections.<String>emptyList();`. |
| `var names = new ArrayList<>();` rồi mong `names.add("An")` chọn `String` | Generic đã suy ra `Object` ở khai báo. | `var names = new ArrayList<String>();` hoặc `List<String> names = new ArrayList<>();`. |
| `var a = new ArrayList<String>();` rồi muốn gán `LinkedList<String>` | Biến có kiểu cụ thể `ArrayList<String>`. | Khai báo interface `List<String> a = new ArrayList<>();`. |
| `var action = () -> ...` | Lambda cần target type là functional interface. | Khai báo `Runnable action = () -> ...;` hoặc interface phù hợp. |

## 12. Bài tập tự kiểm tra

Cho các phương thức (đã khai báo và biên dịch hợp lệ) sau:

```java
static Map<String, List<Integer>> getIndex() { /* implementation */ return Map.of(); }
static Optional<String> findTitle() { /* implementation */ return Optional.empty(); }
static Number read() { return Integer.valueOf(5); }
```

Trong một phương thức có `import java.util.*;`, xét:

```java
var a = getIndex();
var b = findTitle();
var c = read();
var d = Collections.emptyList();
List<String> e = Collections.emptyList();
var f = new ArrayList<>();
```

**Câu hỏi:** Kiểu tĩnh của các biến là gì? Những dòng nào nên cân nhắc viết tường minh để người đọc hiểu nhanh hợp đồng dữ liệu?

**Đáp án:**

- `a`: `Map<String, List<Integer>>`; `b`: `Optional<String>`; `c`: `Number`. Ba biến đều đúng về kiểu, nhưng kiểu tường minh giúp người đọc nhận ra cấu trúc hoặc abstraction nếu tên phương thức chưa đủ rõ.
- `d`: `List<Object>`; `e`: `List<String>`. Với danh sách rỗng, kiểu đích tường minh ở `e` còn tác động đến suy luận generic.
- `f`: `ArrayList<Object>`. Nếu cần danh sách chuỗi, nên viết `List<String> f = new ArrayList<>();` hoặc `var f = new ArrayList<String>();`.

Lưu ý: các phương thức trong câu hỏi là đoạn minh họa cần đặt trong một lớp và import kiểu liên quan; dấu `return Map.of()` và `return Optional.empty()` hợp lệ nhờ kiểu trả về tường minh làm target type cho factory generic.

**Ghi nhớ:** `var` hoạt động theo **kiểu thật của biểu thức**, còn kiểu tường minh là công cụ diễn đạt hợp đồng và, trong một số lời gọi generic, cung cấp **ngữ cảnh suy luận**. Khi tên lời gọi không cho biết rõ loại kết quả, việc hiện kiểu tại vị trí khai báo giúp người đọc hiểu và sửa mã tự tin hơn.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): thiết kế và phạm vi sử dụng `var`, bao gồm suy luận từ biểu thức khởi tạo.
- [Java Language Specification, `14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1): khai báo biến cục bộ có `var`.
- [Java Language Specification, `15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): kiểu của lời gọi phương thức và generic inference.
- [Java Language Specification, `15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.9): biểu thức `new` và diamond.
