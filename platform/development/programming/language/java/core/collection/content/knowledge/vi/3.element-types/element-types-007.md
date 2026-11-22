# Thiết kế phương thức nhận collection linh hoạt nhưng an toàn kiểu

## 1. “Linh hoạt” cần phục vụ đúng hợp đồng

Một phương thức nhận collection tốt cho phép người gọi truyền các cấu trúc và kiểu phần tử phù hợp mà không phải ép kiểu hoặc tạo bản sao vô ích. Đồng thời, chữ ký phải giúp trình biên dịch chặn những cách sử dụng có thể đưa phần tử sai kiểu vào dữ liệu.

Ví dụ, hàm tính tổng chỉ cần đọc các số. Nhận `ArrayList<Integer>` sẽ ràng buộc cả lớp cài đặt lẫn kiểu số quá hẹp. Nhận raw `Collection` rồi ép từng phần tử lại làm mất bảo đảm kiểu.

Một lựa chọn phù hợp hơn là:

```java
// Phác thảo chữ ký, không phải chương trình độc lập.
static double sum(Iterable<? extends Number> source)
```

Chữ ký nói:

- Thuật toán chỉ cần duyệt nguồn.
- Mỗi phần tử dùng được như `Number`.
- Có thể nhận nguồn của `Integer`, `Double` hoặc `Number`.
- Kết quả có kiểu cố định `double`.

Tuy vậy, chữ ký chưa nói đầy đủ về `null`, quyền sửa nguồn, độ chính xác số học hay truy cập nhiều luồng. Thiết kế phương thức cần kết hợp **quan hệ kiểu**, **hành vi quan sát được** và **quyền sở hữu dữ liệu**.

Bài dùng Java 17, tập trung vào các mẫu thiết kế có thể áp dụng trực tiếp cho collection và map. Cần biết generics, quan hệ kiểu cha–con và các giao diện collection cơ bản.

## 2. Xác định thao tác trước khi chọn tham số

Đừng bắt đầu bằng việc thêm wildcard vào một chữ ký bất kỳ. Trước hết, viết rõ phương thức sẽ làm gì.

| Nhu cầu thực tế | Kiểu tham số nên cân nhắc | Lý do |
| --- | --- | --- |
| Chỉ duyệt phần tử | `Iterable<? extends T>` hoặc `Iterable<?>` | Không đòi hỏi `size`, chỉ số hay khả năng thêm |
| Cần `size`, `contains` hoặc dùng constructor sao chép collection | `Collection<? extends T>` | Đủ API nhóm phần tử |
| Cần truy cập và thay phần tử theo vị trí | `List<T>` | Vị trí là một phần hợp đồng |
| Cần dữ liệu có tính không trùng | `Set<T>` hoặc dạng wildcard phù hợp | Diễn đạt mô hình tập hợp |
| Nhận các phần tử để thêm vào một đích | `Collection<? super T>` | Đích giữ được `T` |
| Tra cứu theo khóa | `Map<K, V>` hoặc wildcard theo vai trò | Cần quan hệ khóa–giá trị |

Nguyên tắc là chọn giao diện **đủ diễn đạt ý nghĩa và thao tác**, không chỉ giao diện có ít phương thức nhất.

Ví dụ, nếu thứ tự danh sách là yêu cầu nghiệp vụ, đổi tham số thành `Collection` rồi ngầm dựa vào chỉ số hoặc thứ tự không được cam kết là làm yếu hợp đồng. Ngược lại, nếu chỉ tính tổng bằng vòng lặp, yêu cầu riêng `ArrayList` không mang lại giá trị.

Nguồn API nền tảng: [Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html), [List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html) và [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 3. Phân vai: nguồn, đích và dữ liệu đọc–ghi

Với mỗi tham số, hỏi:

1. Phương thức chỉ lấy phần tử từ đây?
2. Phương thức đưa phần tử vào đây?
3. Phương thức cần đọc rồi ghi lại cùng kiểu phần tử?
4. Kiểu đó có cần liên kết với kết quả hoặc tham số khác không?

Từ đó chọn:

| Vai trò | Mẫu chữ ký | Điều đã biết |
| --- | --- | --- |
| Quan sát, không cần API riêng của phần tử | `Collection<?>` | Đọc thành `Object` |
| Nguồn cung cấp phần tử dùng được như `T` | `Collection<? extends T>` | Đọc thành `T` |
| Đích nhận phần tử `T` | `Collection<? super T>` | Ghi `T`; đọc tổng quát thành `Object` |
| Cần giữ cùng kiểu phần tử khi đọc–ghi | `Collection<T>` hoặc `List<T>` | Tên `T` liên kết các vị trí kiểu |
| Kết quả giữ quan hệ với nguồn | Phương thức generic `<T>` | Có thể biểu đạt kết quả theo `T` |

Quy tắc nhớ PECS — nguồn cung cấp phần tử dùng `extends`, đích nhận phần tử dùng `super` — hữu ích ở bước này. Nó phải được hiểu theo luồng dữ liệu trong thuật toán.

`extends` không tạo bất biến; `super` cũng không cấp khả năng sửa cho một đối tượng vốn không hỗ trợ thêm. [Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html)

## 4. Nguồn đọc: dùng giới hạn trên đúng nhu cầu

```java
// Đoạn khai báo phương thức; cần import java.util.Objects.
static double sum(Iterable<? extends Number> source) {
    Objects.requireNonNull(source, "source");

    double total = 0;
    for (Number value : source) {
        total += Objects.requireNonNull(value, "element").doubleValue();
    }
    return total;
}
```

Các đầu vào phù hợp:

```java
// Đoạn minh họa trong một phương thức, với sum đã khai báo.
// Cần import java.util.*.
List<Integer> integers = List.of(1, 2, 3);
List<Double> decimals = List.of(0.5, 1.5);

System.out.println(sum(integers)); // 6.0
System.out.println(sum(decimals)); // 2.0
```

Vì sao không dùng `Iterable<Number>`? Generics có tính bất biến: `Iterable<Integer>` không tự thành `Iterable<Number>`. Wildcard giới hạn trên mở đúng phạm vi đầu vào mà vẫn bảo đảm đọc mỗi phần tử như `Number`. [Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html)

Hợp đồng cần ghi thêm:

- Nguồn và các phần tử khác `null`.
- Nguồn rỗng trả `0.0`.
- Phương thức không chủ động sửa nguồn.
- Tính toán bằng `double`, không bảo đảm số thập phân chính xác cho tiền tệ.
- Nguồn phải được duyệt ổn định theo chính sách đồng thời của ứng dụng.

`Objects.requireNonNull` giúp xác định điều kiện đầu vào và vị trí lỗi rõ ràng. Nó không kiểm tra tất cả quy tắc nghiệp vụ của phần tử. [Objects API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String))

## 5. Đích nhận dữ liệu: dùng giới hạn dưới

Nếu phương thức tạo hoặc cung cấp các `Integer` để thêm vào đích, đích có thể là collection của `Integer`, `Number` hoặc `Object`.

```java
// Đoạn khai báo phương thức; cần import java.util.Collection.
static void addDefaults(Collection<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

`Collection<Integer>` trong chữ ký sẽ hạn chế người gọi không cần thiết. `Collection<Object>` cũng không nhận được `Collection<Integer>` vì invariance. `? super Integer` biểu đạt đúng “một đích có thể giữ Integer”.

Tuy vậy, qua biến `destination` chỉ có thể đọc tổng quát như `Object`: một đích `Collection<Number>` có thể đã chứa `Double`.

Hợp đồng của phương thức còn yêu cầu:

- Đích tồn tại.
- Đích hỗ trợ `add`.
- Giá trị thêm đáp ứng các ràng buộc của đích.
- Người gọi cho phép sửa chính đối tượng được truyền vào.

Một `List.of(...)` có thể phù hợp về kiểu nhưng không phù hợp về thao tác. Không thể giải quyết điều đó bằng wildcard khác. [Lower Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

## 6. Liên kết nguồn và đích bằng cùng một T

Khi truyền dữ liệu từ một collection sang collection khác, cần một tham số kiểu đặt tên cho mối quan hệ:

```java
// Phác thảo chữ ký; cần import java.util.Collection.
static <T> void addFrom(
        Collection<? super T> destination,
        Collection<? extends T> source)
```

Đọc chữ ký:

1. Nguồn cung cấp phần tử thuộc `T` hoặc kiểu con.
2. Mỗi phần tử đọc ra có thể dùng như `T`.
3. Đích nhận được `T` vì kiểu phần tử của đích là `T` hoặc kiểu cha phù hợp.

Ví dụ:

```java
// Đoạn minh họa trong một phương thức, với addFrom đã khai báo.
// Cần import java.util.*.
List<Integer> source = List.of(1, 2, 3);
List<Number> destination = new ArrayList<>();

addFrom(destination, source);
```

Các phần tử `Integer` được đưa vào đích chứa `Number` mà không ép kiểu.

Không thể dùng phương thức này để thêm các `Double` vào một `List<Integer>`. Compiler không tìm được `T` thỏa mãn cả nguồn Double lẫn đích Integer; đó là một lời gọi cần bị từ chối.

Không dùng hai wildcard không liên quan rồi giả định chúng cùng một kiểu. Cùng có giới hạn `Number` không bảo đảm một nguồn Integer và một đích Double tương thích.

Các generic method được mô tả trong [Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html).

### 6.1. Chọn chính sách alias trước khi cài đặt

Nguồn và đích có thể là cùng một đối tượng hoặc các view dùng chung dữ liệu. Một vòng lặp vừa duyệt nguồn vừa thêm vào đích có thể làm iterator mất hiệu lực.

Trong bài này, `addFrom` tạo snapshot cấu trúc nguồn trước khi sửa đích:

```java
// Đoạn khai báo phương thức; cần import java.util.*.
static <T> void addFrom(
        Collection<? super T> destination,
        Collection<? extends T> source) {

    Objects.requireNonNull(destination, "destination");
    Objects.requireNonNull(source, "source");

    List<T> snapshot = new ArrayList<>(source);
    for (T value : snapshot) {
        destination.add(value);
    }
}
```

Với một danh sách sửa được, `addFrom(list, list)` sẽ thêm một lượt các phần tử ban đầu, thay vì duyệt một nguồn đang lớn lên.

Đây là quyết định của API mẫu:

- Có chi phí bộ nhớ tỷ lệ với kích thước nguồn.
- Snapshot là bản sao nông, vẫn giữ tham chiếu tới phần tử.
- Nó không biến việc đọc nguồn bị sửa đồng thời thành an toàn.
- Nó không làm toàn bộ quá trình thêm thành giao dịch.
- Đích `Set` vẫn áp dụng quy tắc không giữ trùng của chính nó.
- Đích có thể từ chối `null` hoặc một giá trị theo hợp đồng riêng.

Tên `addFrom` dùng theo nghĩa yêu cầu đích tiếp nhận phần tử. Nó không hứa kích thước đích tăng đúng bằng kích thước nguồn trong mọi cấu trúc.

## 7. Khi cần đọc và ghi cùng kiểu: giữ T

Một thao tác đổi chỗ hai phần tử cần đọc ra rồi ghi lại chính kiểu phần tử của danh sách:

```java
// Đoạn khai báo phương thức; cần import java.util.*.
static <T> void swap(List<T> values, int left, int right) {
    Objects.requireNonNull(values, "values");

    T leftValue = values.get(left);
    T rightValue = values.get(right);
    values.set(left, rightValue);
    values.set(right, leftValue);
}
```

Hai giá trị `T` được đọc từ cùng một `List<T>` và ghi lại vào cùng danh sách. Không cần biết `T` là chuỗi, số hay một kiểu nghiệp vụ.

Hợp đồng:

- Hai chỉ số phải hợp lệ.
- Danh sách phải hỗ trợ `set`.
- Phương thức sửa nguồn.
- Không hứa nguyên tử nếu việc thay phần tử bị lỗi giữa chừng.
- Không hứa cùng chi phí với mọi cài đặt danh sách.

Đọc cả hai phần tử trước khi `set` giúp một chỉ số ngoài phạm vi bị phát hiện trước thay đổi trong cài đặt minh họa. Nó không phải bảo đảm rollback cho mọi ngoại lệ khác.

Danh sách cố định kích thước có thể hỗ trợ `set`; danh sách không cho sửa thì không. Kiểu `List<T>` không mã hóa đầy đủ khác biệt đó.

Nếu API công khai nhận wildcard nhưng thao tác chỉ sắp xếp lại phần tử hiện có, helper capture có thể giúp giữ kiểu an toàn. Không cần dùng raw type để giải quyết.

## 8. Giữ quan hệ giữa nguồn và kết quả

### 8.1. Trả một bản sao có kiểu sử dụng được

```java
// Đoạn khai báo phương thức; cần import java.util.*.
static <T> List<T> editableCopy(Collection<? extends T> source) {
    Objects.requireNonNull(source, "source");
    return new ArrayList<>(source);
}
```

Với kiểu đích phù hợp:

```java
// Đoạn minh họa trong một phương thức, với editableCopy đã khai báo.
List<Integer> source = List.of(1, 2, 3);
List<Number> result = editableCopy(source);
result.add(2.5);
```

`T` liên kết kiểu kết quả với tập kiểu mà nguồn cung cấp được. Ngữ cảnh đích cho phép suy luận `T` là `Number` trong ví dụ này.

Kết quả có hợp đồng rõ:

- Một danh sách mới sửa được.
- Giữ thứ tự duyệt của nguồn.
- Thay cấu trúc kết quả không sửa cấu trúc nguồn.
- Các đối tượng phần tử vẫn được chia sẻ.
- `null` được giữ nếu nguồn chứa và constructor nhận được nó.
- Không cam kết giữ comparator hoặc mọi đặc tính của cấu trúc nguồn.

Constructor của `ArrayList` nhận `Collection<? extends E>` chính là một ví dụ thực tế về nguồn linh hoạt. [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 8.2. Tránh trả wildcard không cần thiết

Trả `List<? extends T>` có thể làm người gọi không thể thêm một giá trị `T` mới dù API định tạo danh sách sửa được. Nếu không có lý do bảo toàn một kiểu con ẩn, trả `List<T>` thường truyền đạt kết quả hữu ích hơn.

Nếu muốn kết quả không cho sửa, chọn cơ chế cụ thể như `List.copyOf` và công bố chính sách `null` cùng mức sao chép. Không dùng wildcard để thay thế cam kết không cho sửa.

Tính linh hoạt ở đầu vào và độ rõ ở đầu ra là hai quyết định liên quan nhưng khác nhau.

## 9. Callback cũng có phía đọc và phía tạo kết quả

Một phương thức chuyển từng phần tử thành giá trị mới có thể dùng:

```java
// Đoạn khai báo phương thức; cần import java.util.* và java.util.function.Function.
static <T, R> List<R> mapToList(
        Iterable<? extends T> source,
        Function<? super T, ? extends R> mapper) {

    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(mapper, "mapper");

    List<R> result = new ArrayList<>();
    for (T value : source) {
        result.add(mapper.apply(value));
    }
    return result;
}
```

Đọc chữ ký `Function<? super T, ? extends R>` theo luồng dữ liệu:

- Callback **nhận** một `T`, nên callback biết xử lý kiểu cha của `T` cũng dùng được.
- Callback **trả** kết quả dùng như `R`, nên trả một kiểu con của `R` cũng phù hợp.

Ví dụ:

```java
// Đoạn minh họa với mapToList đã khai báo.
// Cần import java.util.* và java.util.function.Function.
List<Integer> source = List.of(1, 2, 3);
Function<Number, String> label = number -> "n=" + number;

List<CharSequence> labels = mapToList(source, label);
```

Một hàm nhận `Number` xử lý được các `Integer` từ nguồn. Các `String` mà nó trả dùng được như `CharSequence`.

Hợp đồng callback còn cần nêu:

- Nguồn và callback khác `null`.
- Trong ví dụ, phần tử `null` được truyền cho callback; callback quyết định có xử lý được không.
- Kết quả `null` của callback được `ArrayList` chấp nhận.
- Kết quả giữ thứ tự duyệt của nguồn, không tự tạo bảo đảm thứ tự mà nguồn không có.
- Callback không được làm nguồn mất điều kiện duyệt an toàn.
- Ngoại lệ từ callback được truyền ra; các tác động bên ngoài do callback gây ra không tự hoàn tác.

Đây là mẫu chuyển đổi đơn giản để học chữ ký. Nếu API nghiệp vụ cần cấm `null` hoặc cấm tác dụng phụ, hãy bổ sung quy tắc và kiểm tra phù hợp. [Function API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html)

## 10. Áp dụng độc lập cho khóa và giá trị của Map

Một phương thức tạo bản sao map có thể mở rộng cả hai phía:

```java
// Đoạn khai báo phương thức; cần import java.util.*.
static <K, V> Map<K, V> editableMapCopy(
        Map<? extends K, ? extends V> source) {

    Objects.requireNonNull(source, "source");
    return new LinkedHashMap<>(source);
}
```

Ví dụ:

```java
// Đoạn minh họa với editableMapCopy đã khai báo; cần import java.util.*.
Map<String, Integer> source = new LinkedHashMap<>();
source.put("A", 1);

Map<CharSequence, Number> copy = editableMapCopy(source);
copy.put("B", 2.5);
```

Dữ liệu nguồn có khóa `String` dùng được như `CharSequence` và giá trị `Integer` dùng được như `Number`. Bản sao có kiểu riêng, nên thêm giá trị `Double` vào bản sao không làm hỏng hợp đồng của map nguồn.

Cần công bố:

- Tạo map mới theo thứ tự duyệt của nguồn.
- Không sao chép sâu khóa hoặc giá trị.
- Không giữ mọi đặc tính đặc biệt của nguồn, ví dụ comparator của sorted map.
- Số lượng và thứ tự đầu ra tuân theo hợp đồng nguồn/cài đặt được chọn.
- Không làm an toàn việc giữ khóa có trạng thái thay đổi ảnh hưởng `equals/hashCode`.

Nếu API chỉ đọc giá trị, có thể chỉ mở phía `V` bằng `Map<String, ? extends Number>`. Không cần mở rộng cả khóa khi nghiệp vụ thật sự yêu cầu `String`.

Cơ chế giữ thứ tự và constructor sao chép được mô tả trong [LinkedHashMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

## 11. An toàn kiểu là một phần của hợp đồng

### 11.1. Khả năng sửa và quy tắc phần tử

Một phương thức nhận `Collection<? super T>` vẫn có thể gặp `UnsupportedOperationException` từ một đích không cho sửa.

Một đích khác có thể nhận đúng kiểu generic nhưng cấm `null`, yêu cầu so sánh được hoặc giới hạn giá trị. Không coi “biên dịch được” là bằng chứng mọi dữ liệu đầu vào đều được chấp nhận.

### 11.2. Sở hữu, view và alias

Phương thức cần trả lời:

- Nó sửa đối số hay tạo kết quả mới?
- Nó giữ lại tham chiếu sau khi kết thúc không?
- View có thể phản ánh thay đổi về sau không?
- Được truyền cùng một đối tượng vào hai tham số không?
- Có tạo bản sao cấu trúc trước khi sửa không?

Một chữ ký generic đẹp không thay thế các câu trả lời này.

### 11.3. Ngoại lệ và thay đổi dở dang

Với `addFrom`, một số phần tử có thể đã được thêm trước khi đích từ chối một phần tử tiếp theo. Snapshot nguồn không tạo giao dịch cho đích.

Nếu API đòi “thành công toàn bộ hoặc không thay đổi”, cần thiết kế cơ chế phù hợp: ví dụ xây kết quả mới rồi công bố nó, hoặc dùng khả năng giao dịch do cấu trúc/hệ thống đích cung cấp. Không hứa rollback chung cho một `Collection` bất kỳ.

### 11.4. Đồng thời và hiệu năng

Một phương thức nhận giao diện rộng vẫn phải có giả định rõ:

- Dữ liệu có thể bị sửa đồng thời không?
- Iterator có đặc tính gì?
- Số lần duyệt và bộ nhớ phụ là bao nhiêu?
- Truy cập chỉ số có đang ngầm giả định chi phí hằng số không?

Wildcard không đồng bộ hóa, không chụp snapshot nguyên tử và không ngăn callback sửa dữ liệu.

## 12. Đọc chữ ký JDK để học cách thiết kế

Hai chữ ký rút gọn minh họa:

```java
// Chữ ký API để phân tích, không phải chương trình độc lập.
boolean addAll(Collection<? extends E> source);

static <T> void copy(
        List<? super T> destination,
        List<? extends T> source);
```

- `Collection.addAll` nhận các phần tử từ một nguồn mà mỗi phần tử dùng được như `E`.
- `Collections.copy` liên kết hai danh sách bằng `T`, nguồn `extends` và đích `super`.

Nhưng `Collections.copy` không phải “thêm cuối”: nó thay các vị trí đã tồn tại ở đích, và kích thước đích phải đủ. Một `ArrayList` có capacity lớn nhưng `size()` bằng `0` vẫn chưa có các vị trí để thay.

Điều này cho thấy chữ ký generic cần được đọc cùng **hành vi của phương thức**, không chỉ nhận ra mẫu PECS rồi đoán thuật toán. [Collections.copy API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List))

## 13. Chương trình hoàn chỉnh

Lưu thành `FlexibleCollectionApiDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public final class FlexibleCollectionApiDemo {
    private static double sum(Iterable<? extends Number> source) {
        Objects.requireNonNull(source, "source");
        double total = 0;
        for (Number value : source) {
            total += Objects.requireNonNull(value, "element").doubleValue();
        }
        return total;
    }

    private static <T> List<T> editableCopy(
            Collection<? extends T> source) {
        Objects.requireNonNull(source, "source");
        return new ArrayList<>(source);
    }

    private static <T> void addFrom(
            Collection<? super T> destination,
            Collection<? extends T> source) {
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(source, "source");
        List<T> snapshot = new ArrayList<>(source);
        for (T value : snapshot) {
            destination.add(value);
        }
    }

    private static <T> void swap(List<T> values, int left, int right) {
        Objects.requireNonNull(values, "values");
        T leftValue = values.get(left);
        T rightValue = values.get(right);
        values.set(left, rightValue);
        values.set(right, leftValue);
    }

    private static <T, R> List<R> mapToList(
            Iterable<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(mapper, "mapper");
        List<R> result = new ArrayList<>();
        for (T value : source) {
            result.add(mapper.apply(value));
        }
        return result;
    }

    private static <K, V> Map<K, V> editableMapCopy(
            Map<? extends K, ? extends V> source) {
        Objects.requireNonNull(source, "source");
        return new LinkedHashMap<>(source);
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Double> decimals = List.of(0.5, 1.5);
        System.out.println("Integer sum: " + sum(integers));
        System.out.println("Double sum: " + sum(decimals));

        List<Number> copy = editableCopy(integers);
        copy.add(2.5);
        System.out.println("Editable copy: " + copy);
        System.out.println("Source unchanged: " + integers);

        List<Number> destination = new ArrayList<>();
        addFrom(destination, integers);
        addFrom(destination, decimals);
        System.out.println("Mixed destination: " + destination);

        List<String> same = new ArrayList<>(List.of("a", "b"));
        addFrom(same, same);
        System.out.println("Same source and destination: " + same);

        List<Integer> pair = new ArrayList<>(List.of(10, 20));
        swap(pair, 0, 1);
        System.out.println("Swap: " + pair);

        Function<Number, String> label = number -> "n=" + number;
        List<CharSequence> labels = mapToList(integers, label);
        System.out.println("Mapped: " + labels);

        Map<String, Integer> originalMap = new LinkedHashMap<>();
        originalMap.put("A", 1);
        originalMap.put("B", 2);
        Map<CharSequence, Number> mapCopy = editableMapCopy(originalMap);
        mapCopy.put("C", 2.5);
        System.out.println("Map copy: " + mapCopy);
        System.out.println("Original map: " + originalMap);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked FlexibleCollectionApiDemo.java
java FlexibleCollectionApiDemo
```

Mã đã được kiểm tra theo nền API Java 17 trên JDK mới hơn, không có cảnh báo unchecked.

Stdout:

```text
Integer sum: 6.0
Double sum: 2.0
Editable copy: [1, 2, 3, 2.5]
Source unchanged: [1, 2, 3]
Mixed destination: [1, 2, 3, 0.5, 1.5]
Same source and destination: [a, b, a, b]
Swap: [20, 10]
Mapped: [n=1, n=2, n=3]
Map copy: {A=1, B=2, C=2.5}
Original map: {A=1, B=2}
```

### Giải thích các lời gọi

- `sum` nhận hai kiểu số khác nhau qua nguồn `Iterable<? extends Number>`.
- `editableCopy` tạo `List<Number>` mới từ `List<Integer>`; thêm `2.5` chỉ đổi bản sao.
- `addFrom` nhận đích Number và lần lượt nguồn Integer, Double.
- Snapshot nguồn làm lời gọi nguồn=đích hoàn tất với đúng một lượt dữ liệu ban đầu trong ví dụ danh sách.
- `swap` giữ cùng kiểu `T` khi đọc và ghi vị trí.
- `mapToList` nhận callback `Number -> String`, trong khi nguồn là Integer và kết quả được dùng như danh sách CharSequence.
- `editableMapCopy` mở kiểu khóa/giá trị ở bản sao mà không gán map nguồn sang một kiểu generic không tương thích.

Không có lời gọi raw type hoặc ép collection sang kiểu rộng hơn để vượt kiểm tra của compiler.

## 14. Quy trình thiết kế một phương thức mới

1. **Viết hành vi bằng ngôn ngữ thông thường.** Cần đọc, thêm, thay vị trí, lọc hay tạo bản sao?
2. **Xác định giao diện đủ dùng.** Đừng nhận lớp cụ thể chỉ vì đang dùng nó ở một nơi gọi.
3. **Gán vai trò cho từng tham số.** Nguồn, đích hay đọc–ghi cùng kiểu?
4. **Đặt tên tham số kiểu khi có quan hệ.** Dùng `T`, `K/V` hoặc `T/R` để liên kết các vị trí cần liên kết.
5. **Dùng wildcard đúng phía.** `extends` cho nguồn; `super` cho đích nhận.
6. **Chọn kết quả rõ ràng.** Tài liệu hóa sửa được, không cho sửa, view hay bản sao.
7. **Công bố điều kiện ngoài kiểu.** `null`, alias, optional operation, thứ tự, ngoại lệ, đồng thời.
8. **Kiểm tra lời gọi hợp lệ và lời gọi phải bị chặn.** Không sửa chữ ký bằng raw type chỉ để hết lỗi.
9. **Đọc lại mức tổng quát.** Bỏ tham số kiểu hoặc bound không phục vụ hành vi; giữ các ràng buộc nghiệp vụ có ý nghĩa.

Các quy tắc về parameterized type và wildcard nằm trong [JLS Chapter 4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html).

## 15. Lỗi phổ biến

| Cách thiết kế | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Nhận `ArrayList<T>` dù chỉ duyệt | Ràng buộc lớp cài đặt | Chọn `Iterable` hoặc `Collection` đủ nhu cầu |
| Nhận `Collection<Number>` để đọc mọi nhóm số | Chặn nguồn Integer/Double theo invariance | Dùng `? extends Number` |
| Nhận `Collection<Object>` để chứa đầu vào bất kỳ | Không nhận mọi collection generic | Dùng wildcard hoặc tham số kiểu theo vai trò |
| Dùng raw `Collection` rồi cast từng phần tử | Đẩy lỗi sang lúc chạy | Giữ quan hệ generic xuyên suốt |
| Đích thêm `T` lại khai báo `? extends T` | Không chứng minh được kiểu phần tử cần ghi | Xem lại vai trò đích và dùng `super` |
| Hai tham số wildcard nhưng không có T liên kết | Không bảo đảm truyền phần tử giữa chúng an toàn | Dùng generic method có quan hệ nguồn–đích |
| Trả wildcard dù tạo kết quả có kiểu rõ | Làm người gọi khó sử dụng không cần thiết | Trả `List<T>` hoặc `Map<K,V>` thích hợp |
| Coi wildcard là bất biến | Vẫn có thao tác sửa hoặc alias | Chọn cơ chế sở hữu và hạn chế sửa riêng |
| Duyệt nguồn rồi thêm vào chính nguồn | Có thể làm iterator mất hiệu lực | Quy định cấm alias hoặc snapshot có chủ đích |
| Hứa sao chép nguyên tử cho mọi collection | Đích có thể lỗi sau một số lần thêm | Công bố trạng thái khi lỗi hoặc thiết kế giao dịch riêng |
| Bỏ qua callback side effect | Nguồn có thể bị sửa giữa lúc duyệt | Nêu quy tắc callback và chọn cách duyệt phù hợp |

Raw type chủ yếu phục vụ tương thích mã cũ; không phải công cụ làm API mới tổng quát hơn. [Raw Types](https://docs.oracle.com/javase/tutorial/java/generics/rawTypes.html)

## 16. Tự kiểm tra và thực hành

### Câu hỏi

1. Vì sao một hàm chỉ duyệt không cần nhận `ArrayList`?
2. Vì sao `? extends T` thích hợp cho nguồn cung cấp phần tử?
3. Đích `? super Integer` có thể là `Collection<Number>` không?
4. Tại sao cùng một `T` cần xuất hiện ở cả nguồn lẫn đích của `addFrom`?
5. Snapshot trong `addFrom` giải quyết vấn đề nào và chưa giải quyết vấn đề nào?
6. `List<T>` có bảo đảm hỗ trợ `set` không?
7. Vì sao `Function<? super T, ? extends R>` linh hoạt hơn `Function<T,R>` ở phương thức chuyển đổi?
8. Trả `List<? extends T>` có mặc nhiên làm kết quả không cho sửa không?
9. `Collections.copy` có làm tăng kích thước đích không?
10. Các điều kiện nào cần tài liệu hóa bên cạnh quan hệ generic?

### Bài tập

- Viết hàm chỉ đọc độ dài các `CharSequence`, cho phép nhận danh sách `String` và `StringBuilder`.
- Viết hàm thêm các số nguyên vào `Collection<? super Integer>`; thử đích Integer, Number và Object.
- Thử một lời gọi thêm nguồn Double vào đích Integer bằng `addFrom` và giải thích lỗi biên dịch.
- Cho nguồn và đích là cùng một `ArrayList`, đối chiếu kết quả với chính sách snapshot.
- Thử `swap` với danh sách hỗ trợ `set` và danh sách không cho sửa; phân biệt lỗi kiểu với lỗi hợp đồng lúc chạy.
- Viết Javadoc cho `editableCopy`, nêu rõ tính sửa được, bản sao nông, thứ tự và `null`.
- Dùng `mapToList` để chuyển số nguyên sang một kiểu kết quả được dùng qua giao diện rộng hơn.
- Viết một kiểm tra rằng thêm phần tử vào map sao chép không sửa map nguồn.

### Gợi ý đối chiếu

1. Nó không dùng năng lực riêng của lớp đó, nên có thể nhận giao diện đủ để duyệt.
2. Mỗi phần tử đọc ra dùng được như `T` mà không cần biết kiểu con chính xác.
3. Có; Number giữ được Integer.
4. `T` là cầu nối chứng minh phần tử nguồn được đích chấp nhận.
5. Nó tránh vừa duyệt vừa thay đổi nguồn do alias trong cách cài đặt mẫu; không tạo thread safety, bản sao sâu hoặc giao dịch.
6. Không; đối tượng vẫn có thể từ chối thao tác sửa.
7. Callback có thể nhận kiểu cha của đầu vào và trả kiểu con của kết quả.
8. Không; wildcard không phải cơ chế bất biến.
9. Không; đích phải có sẵn đủ vị trí.
10. Quyền sửa, `null`, alias, thứ tự, quyền sở hữu, trạng thái khi lỗi, callback và đồng thời.
