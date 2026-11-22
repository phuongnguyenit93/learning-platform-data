# Wildcard giới hạn trên khi đọc dữ liệu

## 1. Bài toán: một thuật toán đọc nhiều kiểu phần tử liên quan

Ta muốn tính tổng một nhóm số. Dữ liệu đầu vào có thể là `List<Integer>`, `List<Double>` hoặc một collection chứa các đối tượng `Number`.

Một tham số `Collection<Number>` chưa đáp ứng được tất cả các đầu vào đó:

```java
// Phác thảo chữ ký, không phải chương trình độc lập.
static double sum(Collection<Number> values)
```

`Integer` là kiểu con của `Number`, nhưng `Collection<Integer>` không phải kiểu con của `Collection<Number>`. Nếu cho phép gán như vậy, mã qua tham chiếu `Collection<Number>` có thể thêm một `Double` vào đối tượng vốn được mong đợi chỉ chứa `Integer`.

Wildcard giới hạn trên (upper-bounded wildcard) giải quyết trường hợp thuật toán cần **đọc dữ liệu qua một kiểu chung**, không cần tùy ý chèn phần tử mới vào nguồn:

```java
// Phác thảo chữ ký; cần import java.util.Collection.
static double sum(Collection<? extends Number> values)
```

Cách đọc:

> Nhận một collection có kiểu phần tử cụ thể nào đó là `Number` hoặc một kiểu con của `Number`.

Từ đó, mỗi phần tử đọc ra đều dùng được như `Number`. Ta không cần biết kiểu con chính xác để gọi `doubleValue()`.

Bài sử dụng Java 17. Cần biết generics cơ bản, tính bất biến của tham số kiểu và quan hệ kiểu cha–con. Mục tiêu là hiểu tại sao đọc được, tại sao một số lời gọi ghi không biên dịch và những giới hạn vẫn còn ngoài wildcard.

## 2. Ý nghĩa chính xác của ? extends T

Với:

```java
List<? extends Number> source;
```

`?` đại diện cho **một kiểu chưa biết**, bị ràng buộc bởi giới hạn trên `Number`.

Những đối tượng sau đều có thể được gán cho biến đó:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<Integer> integers = List.of(1, 2);
List<Double> decimals = List.of(0.5, 1.5);
List<Number> mixed = List.<Number>of(1, 2.5);

List<? extends Number> a = integers;
List<? extends Number> b = decimals;
List<? extends Number> c = mixed;
```

Không nên diễn giải `List<? extends Number>` thành “danh sách cho phép thêm mọi loại `Number`”. Điều đó là đặc tính của một `List<Number>` hỗ trợ thêm, không phải của tham chiếu có kiểu phần tử chưa biết.

Có thể hình dung kiểu chưa biết là `CAP`:

```text
CAP là một kiểu cụ thể chưa biết
CAP là Number hoặc kiểu con của Number

đọc CAP -> dùng như Number: an toàn
đưa một Number bất kỳ vào nơi cần CAP: chưa chứng minh được
```

`extends` ở đây bao gồm chính kiểu giới hạn, không chỉ kiểu con nghiêm ngặt. Nó cũng dùng cho giới hạn là giao diện, chẳng hạn `Collection<? extends CharSequence>` có thể nhận collection của `String` hoặc `StringBuilder` phù hợp.

Tham khảo [Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html) và [Wildcards and Subtyping](https://docs.oracle.com/javase/tutorial/java/generics/subtyping.html).

## 3. Đọc dữ liệu an toàn qua giới hạn trên

### 3.1. Đọc ra kiểu Number

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<? extends Number> source = List.of(1, 2, 3);

Number first = source.get(0);
double value = first.doubleValue();

System.out.println(first); // 1
System.out.println(value); // 1.0
```

Không cần ép kiểu `(Number)`. Trình biên dịch biết phần tử thuộc một kiểu không rộng hơn `Number`.

Tương tự với vòng lặp:

```java
// Đoạn minh họa với source đã được khởi tạo.
for (Number number : source) {
    System.out.println(number.doubleValue());
}
```

Có thể dùng những phương thức được công bố trên giới hạn trên, như các phương thức chuyển đổi số của `Number`. Xem [Number API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html).

### 3.2. Không tự đọc thành một kiểu con tùy ý

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<? extends Number> source = List.of(1.5, 2.5);

// Integer first = source.get(0); // Không biên dịch.
Number first = source.get(0);     // Hợp lệ.
```

Giới hạn `Number` không hứa phần tử là `Integer`. Ép kiểu thủ công sang `Integer` có thể chuyển lỗi sang lúc chạy.

Nếu thuật toán thật sự đòi tính chất chỉ có ở `Integer`, cần thiết kế tham số hoặc kiểm tra dữ liệu cho yêu cầu đó. Không dùng wildcard rộng rồi giả định ngầm rằng dữ liệu luôn là một kiểu con cụ thể.

### 3.3. var cũng không khôi phục kiểu con đã bị ẩn

Nếu viết `var first = source.get(0);` với `source` khai báo là `List<? extends Number>`, ta không có cơ sở để coi `first` là `Integer`. Kiểu có thể dùng an toàn vẫn dựa trên giới hạn `Number`.

Suy luận kiểu không phải cơ chế theo dõi “mọi lần chạy thực tế đều dùng Integer” để cho phép một API chưa được hợp đồng bảo đảm.

## 4. Vì sao không được thêm Number, Integer hoặc Double?

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<Integer> integers = new ArrayList<>();
List<? extends Number> source = integers;

// source.add(1);   // Không biên dịch.
// source.add(2.5); // Không biên dịch.
```

`source` có thể trỏ tới một `List<Integer>`. Thêm `Double` rõ ràng không an toàn.

Nhưng tại sao thêm `Integer` cũng bị chặn? Vì cùng kiểu khai báo `List<? extends Number>` cũng có thể đang trỏ tới một `List<Double>` hoặc một kiểu `Number` khác. Tại nơi sử dụng, compiler không biết kiểu chính xác mà `add` cần nhận.

Quy tắc bảo vệ tất cả các giá trị có thể gán theo kiểu khai báo, không chỉ trường hợp khởi tạo mà người viết đang nhìn thấy trong ví dụ.

Tương tự:

```java
// Đoạn minh họa với source kiểu List<? extends Number>.
// source.set(0, 1);              // Không biên dịch.
// source.addAll(List.of(1, 2));  // Không biên dịch.
```

Đổi `add` thành `set` không giải quyết vấn đề: việc thay phần tử vẫn phải đưa vào đúng kiểu chưa biết.

### null là một trường hợp riêng

`null` có thể chuyển sang kiểu tham chiếu chưa biết, nên lời gọi sau hợp lệ về mặt kiểu:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<Integer> backing = new ArrayList<>(List.of(9));
List<? extends Number> source = backing;
source.add(null);

System.out.println(backing); // [9, null]
```

Việc chạy thành công ở đây còn dựa vào `ArrayList` cho thêm và cho `null`. Nếu đối tượng là `List.of(...)`, thao tác sửa bị từ chối. Nếu cài đặt cấm `null`, nó có thể báo lỗi giá trị.

Vì vậy, không dùng câu tuyệt đối “không thể thêm bất cứ thứ gì” để mô tả wildcard. Cần phân biệt kiểm tra kiểu với chính sách của đối tượng.

## 5. Wildcard giới hạn trên không tạo tính bất biến

Một cách nhớ nhanh là dùng `extends` cho nguồn đọc. Nhưng “nguồn để đọc” không phải một cơ chế cấm mọi thay đổi.

| Thao tác qua `List<? extends Number>` | Về kiểm tra kiểu | Điều kiện khi chạy |
| --- | --- | --- |
| `get(index)` và đọc thành `Number` | Được | Chỉ số hợp lệ |
| Duyệt bằng `Number` | Được | Nguồn và phần tử phù hợp với thuật toán |
| `add` một `Integer` hoặc `Double` mới | Không được | Bị chặn trước khi chạy |
| `set` bằng một `Number` tùy ý | Không được | Bị chặn trước khi chạy |
| `remove(index)` hoặc `remove(Object)` | Có thể gọi | Đối tượng phải hỗ trợ xóa |
| `clear()` | Có thể gọi | Đối tượng phải hỗ trợ làm rỗng |
| `add(null)` | Có thể hợp lệ về kiểu | Đối tượng phải cho thêm và cho `null` |
| Sửa qua một tham chiếu khác tới cùng đối tượng | Wildcard không chặn | Phụ thuộc hợp đồng tham chiếu/đối tượng đó |

Ví dụ:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<Integer> original = new ArrayList<>(List.of(1, 2, 3));
List<? extends Number> source = original;

source.remove(0);
System.out.println(original); // [2, 3]

source.clear();
System.out.println(original); // []
```

Các lời gọi xóa không cần cung cấp một phần tử mới thuộc kiểu capture. Chúng vẫn có thể thay đổi dữ liệu nguồn.

Ngoài ra:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = original;

original.add(3);
System.out.println(source); // [1, 2, 3]
```

Phép gán không sao chép danh sách và không tạo wrapper. Hai biến tham chiếu cùng đối tượng.

Nếu phần tử là đối tượng có trạng thái thay đổi, việc đọc tham chiếu còn có thể cho phép gọi các phương thức thay đổi trạng thái được công bố trên kiểu giới hạn. Wildcard không làm bản thân phần tử bất biến.

Để ngăn sửa qua một API, cần thiết kế hợp đồng và cơ chế thích hợp như wrapper không cho sửa hoặc bản sao không cho sửa. Ngay cả wrapper cũng có thể quan sát thay đổi từ nguồn, và bản sao nông vẫn dùng chung các đối tượng phần tử.

Xem [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html), [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) và [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

## 6. Viết một thuật toán đọc thực sự

```java
// Đoạn khai báo phương thức trong một lớp; cần import java.util.Collection.
static double sum(Collection<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

Hợp đồng của ví dụ:

- Nhận nguồn và các phần tử khác `null`.
- Không thêm, xóa hoặc thay phần tử trong nguồn.
- Nguồn rỗng cho kết quả `0.0`.
- Dùng biểu diễn `double` để minh họa, không cam kết tính toán thập phân chính xác cho tiền tệ.
- Không hỗ trợ việc nguồn bị sửa đồng thời ngoài một chính sách đồng bộ thích hợp.

Lời gọi:

```java
// Đặt trong một phương thức, với sum đã khai báo; cần import java.util.*.
System.out.println(sum(List.of(1, 2, 3)));   // 6.0
System.out.println(sum(List.of(0.5, 1.5))); // 2.0
```

Ở đây chọn `Collection` vì chỉ cần duyệt, không cần vị trí. Nếu phương thức cần `get(0)`, `List` mới diễn đạt đủ API cần dùng.

Nếu chỉ cần duyệt và không cần các thao tác collection khác, `Iterable<? extends Number>` cũng có thể là tham số phù hợp. Chọn giao diện theo thao tác thật sự, rồi dùng wildcard theo quan hệ kiểu cần chấp nhận.

Không phải thuật toán đọc nào cũng nên dùng `Number`: một miền nghiệp vụ có thể cần kiểu chính xác hơn hoặc phép tính được định nghĩa riêng.

## 7. Phân biệt với `Collection<Number>`, `Collection<?>` và `Collection<Object>`

| Tham số | Đầu vào điển hình phù hợp | Đọc được chắc chắn như kiểu gì? | Ý nghĩa |
| --- | --- | --- | --- |
| `Collection<Number>` | `Collection<Number>` | `Number` | Có kiểu phần tử Number cụ thể |
| `Collection<? extends Number>` | `Collection<Integer>`, `Collection<Double>`, `Collection<Number>` | `Number` | Kiểu phần tử chưa biết nhưng không rộng hơn Number |
| `Collection<?>` | Collection của nhiều đối số kiểu khác nhau | `Object` | Không có yêu cầu riêng ngoài những gì biết về Object |
| `Collection<Object>` | `Collection<Object>` | `Object` | Collection có kiểu phần tử Object, không phải chỗ nhận mọi collection |

`Collection<?>` cũng có giới hạn trên ngầm định là `Object`. Nếu thuật toán chỉ in phần tử hoặc lấy `size`, nó có thể đủ. Nếu cần gọi `doubleValue`, giới hạn `Number` mang lại thông tin hữu ích.

`Collection<Object>` không nhận gán trực tiếp một `Collection<Integer>`. Không dùng `Object` như cách tránh quy tắc bất biến của generics.

Tương tự, `Collection<? extends Number>` không nhận `Collection<String>`. Nó mở rộng tập đầu vào có kiểm soát, không bỏ kiểm tra kiểu.

Các quy tắc tham số hóa và wildcard nằm trong [JLS Chapter 4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html).

## 8. Wildcard hay tham số kiểu có tên?

### 8.1. Chỉ cần đọc qua một hợp đồng chung: wildcard thường đủ

```java
// Phác thảo chữ ký; cần import java.util.Collection.
static double sum(Collection<? extends Number> values)
```

Phương thức không cần nói “kết quả có cùng kiểu phần tử với đầu vào”. Kết quả luôn là `double`, nên chưa cần đặt tên kiểu chưa biết.

### 8.2. Cần liên kết kiểu với kết quả: dùng T

```java
// Đoạn khai báo phương thức; cần import java.util.List.
static <T extends Number> T firstTyped(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}
```

Với `List<Integer>`, người gọi có thể nhận `Integer` mà không ép kiểu:

```java
// Đặt trong một phương thức, với firstTyped đã khai báo; cần import java.util.List.
Integer first = firstTyped(List.of(10, 20));
```

So sánh với:

```java
// Đoạn khai báo phương thức; cần import java.util.List.
static Number first(List<? extends Number> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}
```

Hợp đồng kết quả thứ hai chỉ hứa `Number`, không giữ quan hệ “chính là kiểu phần tử của đầu vào” cho người gọi.

Tên `T` hữu ích khi cần liên kết nhiều vị trí kiểu: nguồn, đích, kết quả hoặc các đối số có quan hệ. Không thêm tham số kiểu chỉ để làm chữ ký trông tổng quát hơn. [Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html)

### 8.3. Không ưu tiên wildcard ở kiểu trả về nếu không cần

Một API trả `List<? extends Number>` khiến người gọi phải làm việc với kiểu chưa biết. Nếu API tạo một danh sách số mà hợp đồng mong muốn là `List<Number>`, thường nên công bố đúng kiểu đó.

Ngược lại, có API có lý do giữ phần tử theo một họ kiểu; khi ấy wildcard có thể có giá trị. Quyết định nên dựa trên thông tin người gọi cần, không chỉ lặp lại quy tắc “đọc thì extends” vào mọi vị trí trong chữ ký.

## 9. Sao chép nguồn để có một đích với kiểu rõ ràng

Nếu cần nhận nhiều nguồn kiểu con rồi thêm một giá trị `Number` khác, đừng ép nguồn thành `Collection<Number>`. Hãy tạo collection mới:

```java
// Đoạn minh họa trong một phương thức; cần import java.util.*.
List<Integer> original = List.of(1, 2, 3);
Collection<? extends Number> source = original;

List<Number> copy = new ArrayList<>(source);
copy.add(2.5);

System.out.println(original); // [1, 2, 3]
System.out.println(copy);     // [1, 2, 3, 2.5]
```

Constructor `ArrayList(Collection<? extends E>)` đọc phần tử từ nguồn để đặt vào danh sách có kiểu đích `E`. Trong ví dụ `E` là `Number`. Nguồn vẫn giữ hợp đồng của nó. [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Có thể đóng gói quan hệ này:

```java
// Đoạn khai báo phương thức; cần import java.util.*.
static <T> List<T> copySource(Collection<? extends T> source) {
    return new ArrayList<>(source);
}
```

Đây là bản sao cấu trúc và các tham chiếu phần tử, không phải nhân bản sâu. Với phần tử có trạng thái thay đổi, nguồn và bản sao có thể cùng tham chiếu một đối tượng.

Nếu muốn ghi vào một đích đã được cung cấp, đó là bài toán thiết kế tham số đích, thường liên quan `? super T`. Không thay `extends` bằng `super` ở nguồn một cách máy móc: mỗi phía có vai trò khác nhau.

## 10. Wildcard capture và thao tác giữ nguyên kiểu

### 10.1. Thông báo capture of ? nói gì?

Đoạn sau dễ khiến người học bối rối:

```java
// Minh họa có lỗi biên dịch; cần import java.util.List.
static void rewriteFirst(List<? extends Number> values) {
    // values.set(0, values.get(0));
}
```

Nếu bỏ chú thích, compiler có thể báo lỗi liên quan `capture of ? extends Number`. Về mặt ý định, ta đang đọc rồi ghi lại một phần tử. Nhưng kiểu đọc nhìn qua giới hạn không tự được xác nhận là cùng kiểu capture cần cho lời gọi ghi tại vị trí khác.

Không giải quyết bằng raw `List`. Khi thao tác thật sự an toàn vì chỉ dùng lại các phần tử của cùng một danh sách, có thể đặt tên cho capture bằng một helper generic.

### 10.2. Helper giữ cùng một T cho cả đọc và ghi

```java
// Đoạn khai báo hai phương thức trong một lớp; cần import java.util.List.
static void swapFirstTwo(List<? extends Number> values) {
    swapCaptured(values);
}

private static <T extends Number> void swapCaptured(List<T> values) {
    if (values.size() < 2) {
        throw new IllegalArgumentException("need two elements");
    }

    T first = values.get(0);
    values.set(0, values.get(1));
    values.set(1, first);
}
```

Trong helper, kiểu `T` liên kết phần tử đọc và phần tử ghi. Không đưa một `Number` mới tùy ý vào danh sách. Chỉ đổi vị trí hai phần tử vốn thuộc cùng kiểu phần tử đã được capture.

Tuy vậy, phương thức **có sửa nguồn**. Đối tượng phải hỗ trợ `set`; truyền một danh sách không cho sửa vẫn có thể gây `UnsupportedOperationException`. Wildcard capture giải quyết vấn đề chứng minh kiểu, không giải quyết quyền sửa. [Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html)

### 10.3. Hai wildcard không có nghĩa là cùng một kiểu

Nếu nhận hai tham số `List<? extends Number>`, kiểu phần tử chưa biết của mỗi tham số có thể khác nhau: một là `Integer`, một là `Double`.

Không lấy phần tử từ danh sách thứ nhất rồi chèn sang danh sách thứ hai chỉ vì cả hai có cùng giới hạn `Number`. Cùng giới hạn trên không đồng nghĩa cùng capture.

Muốn truyền dữ liệu giữa hai nơi, chữ ký cần diễn đạt quan hệ kiểu an toàn giữa nguồn và đích. Nếu chỉ muốn đọc cả hai, không có vấn đề này.

Capture conversion được mô tả chính xác trong [JLS 5.1.10](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10).

## 11. Áp dụng cho Map và dữ liệu lồng nhau

### 11.1. Chỉ đặt wildcard ở phía cần mở rộng

```java
// Đoạn khai báo phương thức; cần import java.util.Map.
static double sumMappedValues(Map<String, ? extends Number> values) {
    double total = 0;
    for (Number value : values.values()) {
        total += value.doubleValue();
    }
    return total;
}
```

Hàm nhận `Map<String, Integer>` hoặc `Map<String, Double>` vì kiểu giá trị được mở rộng. Kiểu khóa vẫn được yêu cầu là `String`.

Nó không biến thành một map cho phép `put("new", 1.5)`: giá trị cần ghi vẫn thuộc kiểu chưa biết. Đọc kết quả `get` hoặc `values` như `Number` thì an toàn về kiểu, nhưng vẫn phải xét trường hợp `null`.

Nếu chỉ cần các giá trị mà không dùng khóa, có thể nhận `Collection<? extends Number>` và truyền `map.values()`. Chọn tham số theo khả năng thuật toán thật sự cần. [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 11.2. Wildcard bên ngoài không tự làm mọi tầng biến thiên

`List<Integer>` không phải `List<Number>`, nên với dữ liệu lồng nhau phải đọc từng tầng.

Ví dụ ý định “một nhóm gồm các collection, mỗi collection cung cấp Number” có thể được biểu đạt bằng:

```java
// Phác thảo chữ ký, không phải chương trình độc lập.
Collection<? extends Collection<? extends Number>> groups
```

Wildcard ngoài mô tả các collection con; wildcard trong mô tả phần tử số của mỗi collection con.

Không cần dùng chữ ký dài này nếu bài toán chỉ nhận một collection phẳng. Việc lồng wildcard nên xuất phát từ mô hình dữ liệu, không phải một thói quen làm API phức tạp.

## 12. Giới hạn ngoài hệ thống kiểu

Wildcard giới hạn trên không tự xử lý các vấn đề sau:

- **Nguồn `null`:** gọi phương thức trên nguồn vẫn có thể gây `NullPointerException`.
- **Phần tử `null`:** đọc được thành `Number` không bảo đảm gọi `doubleValue` an toàn.
- **Nguồn rỗng:** `get(0)` vẫn cần hợp đồng cho trường hợp không có phần tử.
- **Số học:** chuyển mọi `Number` sang `double` có thể mất độ chính xác.
- **Đồng thời:** tham chiếu khác có thể sửa cấu trúc trong lúc duyệt.
- **Dữ liệu sai kiểu từ raw type:** wildcard không khôi phục bảo đảm đã bị phá vỡ ở ranh giới unchecked.
- **Quyền sở hữu:** nó không tạo bản sao hoặc chuyển quyền sửa nguồn.
- **Bất biến sâu:** nó không khóa trạng thái của các đối tượng phần tử.

Vì vậy, chữ ký là một phần hợp đồng; tài liệu, validation và chính sách vận hành dữ liệu vẫn cần phù hợp.

Không dùng cast từ `List<? extends Number>` sang `List<Number>` để làm `add` biên dịch. Cast không biến một `List<Integer>` thành danh sách có thể an toàn chứa `Double`.

## 13. Chương trình hoàn chỉnh

Lưu thành `UpperBoundedReadDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;

public final class UpperBoundedReadDemo {
    private static double sum(Collection<? extends Number> values) {
        double total = 0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    private static Number first(List<? extends Number> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }
        return values.get(0);
    }

    private static <T> List<T> copySource(
            Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    private static void swapFirstTwo(List<? extends Number> values) {
        swapCaptured(values);
    }

    private static <T extends Number> void swapCaptured(List<T> values) {
        if (values.size() < 2) {
            throw new IllegalArgumentException("need two elements");
        }
        T first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    private static double sumMappedValues(
            Map<String, ? extends Number> values) {
        double total = 0;
        for (Number value : values.values()) {
            total += value.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<Double> decimals = List.of(0.5, 1.5);
        System.out.println("Integer sum: " + sum(integers));
        System.out.println("Double sum: " + sum(decimals));

        List<? extends Number> source = integers;
        Number firstValue = first(source);
        System.out.println("First value: " + firstValue);

        integers.add(4);
        System.out.println("View after alias add: " + source);
        source.remove(0);
        System.out.println("After source remove: " + integers);

        List<Number> copy = copySource(source);
        copy.add(2.5);
        System.out.println("Copy: " + copy);
        System.out.println("Original: " + integers);

        List<Integer> pair = new ArrayList<>(List.of(10, 20));
        swapFirstTwo(pair);
        System.out.println("Captured swap: " + pair);

        List<Integer> toClear = new ArrayList<>(List.of(7, 8));
        Collection<? extends Number> unknownSubtype = toClear;
        unknownSubtype.clear();
        System.out.println("After wildcard clear: " + toClear);

        List<Integer> nullable = new ArrayList<>(List.of(9));
        List<? extends Number> nullAllowedByType = nullable;
        nullAllowedByType.add(null);
        System.out.println("Null insertion: " + nullable);

        Map<String, Integer> counts = Map.of("a", 2, "b", 3);
        System.out.println("Map value sum: " + sumMappedValues(counts));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked UpperBoundedReadDemo.java
java UpperBoundedReadDemo
```

Mã đã được kiểm tra với nền API Java 17 trên JDK mới hơn, không có cảnh báo unchecked. Chương trình không sửa danh sách `List.of`; những thao tác sửa dùng `ArrayList`.

Stdout:

```text
Integer sum: 6.0
Double sum: 2.0
First value: 1
View after alias add: [1, 2, 3, 4]
After source remove: [2, 3, 4]
Copy: [2, 3, 4, 2.5]
Original: [2, 3, 4]
Captured swap: [20, 10]
After wildcard clear: []
Null insertion: [9, null]
Map value sum: 5.0
```

### Giải thích theo các ranh giới cần học

- `sum` đọc được cả nguồn `Integer` lẫn `Double` qua `Number`.
- `first` chỉ trả hợp đồng `Number`, nên biến nhận không tự trở thành `Integer`.
- `source` quan sát phần tử được thêm qua `integers` vì hai tham chiếu cùng trỏ một đối tượng.
- `source.remove(0)` biên dịch và thay đổi nguồn: wildcard không tạo bất biến.
- `copySource` tạo một `List<Number>` mới; thêm `2.5` vào bản sao không đổi cấu trúc nguồn.
- Helper capture đổi hai phần tử trong cùng kiểu `T`, không ép kiểu.
- `clear` qua wildcard vẫn làm rỗng một nguồn sửa được.
- `add(null)` hợp lệ về kiểu và được `ArrayList` chấp nhận; sau đó không đưa danh sách này vào `sum` vốn yêu cầu phần tử khác `null`.
- Wildcard ở phía giá trị của map cho phép đọc map số nguyên qua `Number`.

## 14. Lỗi phổ biến và cách sửa

| Cách làm | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Dùng `Collection<Number>` rồi muốn nhận `List<Integer>` | Không có quan hệ kiểu mong muốn | Dùng `? extends Number` cho nguồn đọc |
| Hiểu `? extends Number` là cho thêm mọi `Number` | Kiểu thật có thể hẹp hơn | Chỉ đọc qua giới hạn hoặc tạo đích có kiểu rõ ràng |
| Đọc thành `Integer` không kiểm tra | Nguồn có thể chứa kiểu Number khác | Dùng API của `Number` hoặc thiết kế yêu cầu kiểu hẹp hơn |
| Coi wildcard là collection bất biến | `remove`, `clear` và alias vẫn có thể sửa | Chọn cơ chế không cho sửa/copy và tài liệu hóa quyền sở hữu |
| Coi `null` là bị chặn bởi wildcard | `null` hợp lệ với kiểu tham chiếu | Kiểm tra chính sách giá trị riêng |
| Dùng raw type để hết lỗi capture | Làm mất bảo đảm kiểu | Dùng helper generic khi quan hệ thật sự an toàn |
| Chuyển phần tử giữa hai wildcard cùng bound | Hai capture có thể khác nhau | Diễn đạt quan hệ nguồn–đích bằng tham số kiểu |
| Dùng wildcard cho mọi kiểu trả về | Đẩy khó khăn không cần thiết sang người gọi | Công bố kiểu kết quả đủ chính xác |
| Cho rằng wildcard xử lý rỗng hoặc `null` | Đây là điều kiện dữ liệu, không phải chỉ kiểu | Nêu và kiểm tra hợp đồng đầu vào |
| Cast nguồn thành `List<Number>` để thêm Double | Có thể làm sai dữ liệu một `List<Integer>` | Tạo bản sao có kiểu đích phù hợp |

## 15. Tự kiểm tra và thực hành

### Câu hỏi

1. `Collection<? extends Number>` có nhận `Collection<Number>` không?
2. Vì sao nó cũng nhận `Collection<Integer>` nhưng không cho `add(1)`?
3. Đọc phần tử thành `Number` khác với ép thành `Integer` thế nào?
4. Có được `clear` qua tham chiếu wildcard không?
5. `add(null)` có bị chặn lúc biên dịch không, và lúc chạy còn phụ thuộc điều gì?
6. Hai tham số `List<? extends Number>` có bắt buộc cùng kiểu phần tử không?
7. Khi nào cần `<T extends Number>` thay vì chỉ wildcard?
8. Helper capture có làm một danh sách không cho sửa trở thành sửa được không?
9. Sao chép sang `List<Number>` khác với cast nguồn sang kiểu đó thế nào?
10. Thuật toán dùng `doubleValue` còn cần công bố những giới hạn dữ liệu nào?

### Bài tập

- Viết hàm đếm số phần tử có giá trị `doubleValue()` dương, nhận `Collection<? extends Number>` và không sửa nguồn.
- Thử truyền `List<Integer>`, `List<Double>` và `List<Number>` vào cùng hàm.
- Thêm một dòng `source.add(1)` vào bài thử để quan sát lỗi biên dịch; giải thích bằng kiểu phần tử chưa biết.
- Chứng minh bằng một ví dụ nhỏ rằng sửa qua alias được quan sát qua biến wildcard.
- Tạo một bản sao `List<Number>` từ nguồn số nguyên rồi thêm một số thập phân vào bản sao.
- Gọi helper đổi chỗ với một `ArrayList`, sau đó thử một danh sách không cho sửa để phân biệt lỗi kiểu và lỗi thao tác.
- Viết hai hàm lấy phần tử đầu: một trả `Number`, một generic trả `T`; đối chiếu kiểu biến nhận tại nơi gọi.
- Với map có khóa `String` và giá trị số nguyên, viết hàm chỉ đọc giá trị qua giới hạn `Number`.

### Gợi ý đối chiếu

1. Có; giới hạn bao gồm chính `Number`.
2. Nhận được một kiểu con cụ thể nhưng không biết nó là kiểu nào tại chỗ ghi.
3. Giới hạn trên bảo đảm dùng được như `Number`; không bảo đảm một kiểu con tùy ý.
4. Có thể gọi về mặt kiểu; đối tượng phải hỗ trợ thao tác.
5. Có thể hợp lệ về kiểu; đối tượng phải hỗ trợ thêm và chấp nhận `null`.
6. Không; một nguồn có thể là `Integer`, nguồn kia là `Double`.
7. Khi cần giữ quan hệ kiểu giữa nhiều vị trí, nhất là kiểu kết quả.
8. Không; nó chỉ giúp chứng minh quan hệ kiểu cho lời gọi.
9. Bản sao có cấu trúc và kiểu đích riêng; cast không thay đổi đối tượng nguồn.
10. Nguồn/phần tử khác `null`, trường hợp rỗng, độ chính xác số học và việc sửa đồng thời.
