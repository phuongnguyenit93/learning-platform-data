# removeIf và xử lý điều kiện xóa

Khi cần xóa tất cả phần tử không còn hợp lệ, ta có thể mô tả việc cần làm bằng một điều kiện: xóa đơn đã hủy, xóa chuỗi rỗng, xóa mục hết hạn hoặc xóa số chẵn. `removeIf` diễn đạt trực tiếp kiểu thao tác đó: **kiểm tra từng phần tử bằng một điều kiện và loại các phần tử thỏa điều kiện khỏi collection đang được gọi**.

Điểm cần nắm ngay từ đầu là chiều của điều kiện:

- Điều kiện trả `true`: phần tử thuộc diện cần xóa.
- Điều kiện trả `false`: phần tử được giữ lại.

Đây là thao tác sửa dữ liệu tại chỗ. Nó khác với tạo một danh sách kết quả bằng cách lọc stream. Bài này thuộc phần hợp đồng chung của Java Collections Framework; các ví dụ dùng Java 17 trở lên.

## 1. Hợp đồng của removeIf

Chữ ký được khai báo trong `Collection<E>`:

```java
default boolean removeIf(Predicate<? super E> filter)
```

Đây là chữ ký API, không phải một chương trình độc lập.

`Predicate<T>` biểu diễn một phép kiểm tra nhận một giá trị kiểu `T` và trả `boolean`. Lambda như `n -> n % 2 == 0` là một cách viết predicate cho số chẵn.

`? super E` cho phép nhận một predicate xử lý được phần tử kiểu `E` hoặc một kiểu cha phù hợp. Chẳng hạn, một `Predicate<Object>` có thể dùng để kiểm tra các phần tử của `Collection<String>`. Không cần ép kiểu tùy tiện để viết điều kiện thông thường.

Nếu phương thức hoàn tất bình thường:

| Tình huống | Kết quả |
| --- | --- |
| Có ít nhất một phần tử bị xóa | Trả `true` |
| Không xóa phần tử nào | Trả `false` |

Giá trị trả về **không phải số lượng phần tử đã xóa**, cũng không phải kết quả predicate của phần tử cuối. Nếu collection rỗng hoặc không có phần tử thỏa điều kiện, một collection có hỗ trợ thao tác có thể hoàn tất và trả `false`.

Predicate `null` không hợp lệ. Ngoại lệ phát sinh trong quá trình kiểm tra hoặc xóa được truyền ra bên gọi; hợp đồng chung không hứa hẹn hoàn tác mọi thay đổi đã xảy ra. [Java 17: Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate))

## 2. Xóa mọi phần tử khớp, không chỉ lần đầu

Ví dụ trong một phương thức:

```java
List<Integer> numbers =
        new ArrayList<>(List.of(1, 2, 2, 3, 4));

boolean changed = numbers.removeIf(n -> n % 2 == 0);

System.out.println(changed); // true
System.out.println(numbers); // [1, 3]
```

Cần import `List` và `ArrayList` từ `java.util`.

Cả hai lần xuất hiện của `2` và phần tử `4` đều bị xóa. Với danh sách này, các phần tử còn lại giữ thứ tự tương đối ban đầu.

Nếu gọi tiếp:

```java
boolean changedAgain = numbers.removeIf(n -> n > 10);
System.out.println(changedAgain); // false
System.out.println(numbers);      // [1, 3]
```

Không có số nào lớn hơn 10 nên không thay đổi.

`removeIf` không thêm, thay thế hoặc biến đổi giá trị phần tử. Nếu cần chuyển mỗi giá trị sang một giá trị mới, phải chọn thao tác khác như `List.replaceAll` hoặc ánh xạ bằng stream.

### Phân biệt với các thao tác xóa khác

| Nhu cầu | Cách diễn đạt |
| --- | --- |
| Xóa một lần xuất hiện của một giá trị | `remove(value)` |
| Xóa các phần tử thuộc một tập giá trị | `removeAll(values)` |
| Chỉ giữ các phần tử thuộc một tập giá trị | `retainAll(values)` |
| Xóa theo thuộc tính hoặc điều kiện tính toán | `removeIf(predicate)` |
| Xóa toàn bộ | `clear()` |

Ví dụ `removeIf(n -> n == 2)` trên một danh sách số nguyên không có `null` xóa mọi số 2. Nó tránh sự nhập nhằng giữa `List<Integer>.remove(int index)` và `remove(Object value)`, vì điều kiện xóa được mô tả rõ. Tuy nhiên, `n == 2` có unboxing và sẽ gây lỗi nếu gặp `null`; chính sách `null` cần được thiết kế riêng.

## 3. Cơ chế mặc định và quyền sửa collection

### 3.1. Cách triển khai mặc định sử dụng iterator

Có thể hình dung cách triển khai mặc định của `Collection.removeIf` qua mã minh họa:

```java
boolean changed = false;
Iterator<E> iterator = collection.iterator();

while (iterator.hasNext()) {
    E element = iterator.next();
    if (filter.test(element)) {
        iterator.remove();
        changed = true;
    }
}
return changed;
```

Đây là mã mô tả thuật toán, đã lược bước kiểm tra predicate khác `null`; nó không phải chương trình hoàn chỉnh để sao chép trực tiếp.

Lưu ý chữ **mặc định**: một lớp có thể ghi đè phương thức bằng cách xử lý phù hợp với cấu trúc riêng. Không suy ra mọi collection đều xóa từng phần tử bằng iterator, hoặc đều có cùng chi phí và hành vi khi predicate lỗi.

`Iterator.remove()` là thao tác tùy chọn. Với cách triển khai mặc định, nếu iterator không hỗ trợ xóa thì khi cần xóa phần tử phù hợp, `UnsupportedOperationException` có thể được ném. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove())

### 3.2. Không xóa bằng collection ngay trong for-each

Đoạn sau là một cách viết dễ gây lỗi:

```java
// Không dùng cách này để xóa trong lúc duyệt ArrayList.
for (Integer number : numbers) {
    if (number % 2 == 0) {
        numbers.remove(number);
    }
}
```

Vòng `for-each` sử dụng cơ chế duyệt. Sửa cấu trúc bằng đường gọi khác trong lúc đang duyệt có thể làm iterator mất hiệu lực và gây `ConcurrentModificationException` hoặc dẫn đến xử lý không như mong đợi. Không coi việc “một lần chạy không ném lỗi” là chứng minh đúng.

Với điều kiện chỉ phụ thuộc phần tử và trạng thái tham chiếu ổn định, dùng:

```java
numbers.removeIf(number -> number % 2 == 0);
```

Nếu cần điều khiển quá trình duyệt từng bước và iterator hỗ trợ xóa, có thể dùng `iterator.remove()` sau `next()`. Đó là trường hợp khác với gọi `numbers.remove` từ bên ngoài iterator.

### 3.3. Có List không đồng nghĩa có quyền xóa

Các danh sách có thể khác khả năng sửa:

| Nguồn tạo | Khả năng liên quan đến xóa |
| --- | --- |
| `new ArrayList<>(...)` | Hỗ trợ xóa phần tử |
| `Arrays.asList(...)` | Danh sách kích thước cố định; không hỗ trợ xóa làm đổi kích thước |
| `List.of(...)` | Không cho sửa nội dung qua API của danh sách |
| `Collections.unmodifiableList(source)` | View không cho sửa; nguồn bên dưới vẫn có thể đổi qua tham chiếu khác |
| `CopyOnWriteArrayList` | Có hỗ trợ `removeIf`, dù iterator của nó không hỗ trợ `remove` |

`Arrays.asList` không phải `java.util.ArrayList` thông thường. Nó cho thay phần tử bằng `set` nhưng không cho giảm số phần tử. Khi cần xóa, có thể chủ động tạo bản có thể sửa:

```java
List<String> editable =
        new ArrayList<>(Arrays.asList("old", "keep", "old"));

editable.removeIf("old"::equals);
System.out.println(editable); // [keep]
```

Đây là đoạn minh họa trong một phương thức, cần import các lớp tương ứng. [Java 17: Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...))

Không dùng predicate luôn `false` để thử xem một collection có sửa được hay không. Với thao tác không hỗ trợ, trường hợp không tạo thay đổi có thể vẫn bị từ chối tùy hợp đồng. Hãy biết rõ nguồn tạo và quyền sửa dữ liệu.

## 4. Thiết kế điều kiện xóa đúng ý nghĩa

### 4.1. Đặt tên theo điều kiện xóa

So sánh hai cách đặt tên:

```java
Predicate<Order> shouldDelete =
        order -> order.status() == Status.CANCELLED;

orders.removeIf(shouldDelete);
```

và:

```java
Predicate<Order> shouldKeep =
        order -> order.status() != Status.CANCELLED;

orders.removeIf(shouldKeep); // Sai ý định: đang xóa các đơn cần giữ.
```

Đây là các đoạn minh họa; `Order`, `Status` và `orders` do ứng dụng định nghĩa.

Tên như `expired`, `cancelled` hoặc `shouldDelete` giúp đối chiếu chiều điều kiện. Nếu đã có predicate mô tả “giữ”, phải đổi chiều bằng `negate()` khi dùng làm điều kiện xóa.

### 4.2. Xử lý null trước khi gọi phương thức trên phần tử

Nếu danh sách có thể chứa `null`, điều kiện sau không an toàn:

```java
names.removeIf(name -> name.isBlank());
```

Nó ném `NullPointerException` khi gặp `null`. Trước hết hãy quyết định `null` thuộc diện xóa hay giữ.

Xóa cả `null` lẫn chuỗi trắng:

```java
names.removeIf(name -> name == null || name.isBlank());
```

Giữ `null`, chỉ xóa chuỗi trắng không null:

```java
names.removeIf(name -> name != null && name.isBlank());
```

Chỉ xóa `null`:

```java
names.removeIf(Objects::isNull);
```

Các đoạn cần biến `names` đã được tạo và import `java.util.Objects` cho ví dụ cuối.

Toán tử `||` và `&&` có đánh giá ngắn mạch. Ở trường hợp thứ nhất, nếu `name == null` đúng thì không gọi `isBlank`. Đảo thứ tự thành `name.isBlank() || name == null` không còn bảo vệ được.

Một trường bên trong đối tượng cũng có thể là `null`. Chặn `item != null` chưa đủ nếu sau đó gọi `item.owner().isBlank()` mà `owner()` vẫn có thể trả `null`.

### 4.3. Ghép nhiều điều kiện có chủ đích

`Predicate` có các phương thức ghép:

- `a.and(b)`: cả hai điều kiện cùng đúng.
- `a.or(b)`: ít nhất một điều kiện đúng.
- `a.negate()`: đảo kết quả.

Ví dụ với dữ liệu đã được làm sạch `null`:

```java
Predicate<String> longName = name -> name.length() > 3;
Predicate<String> startsWithM = name -> name.startsWith("M");

names.removeIf(longName.and(startsWithM));
```

Điều kiện này xóa tên dài hơn 3 ký tự **và** bắt đầu bằng `M`. Nó không xóa mọi tên bắt đầu bằng `M` và cũng không xóa mọi tên dài.

`and` và `or` đánh giá ngắn mạch theo thứ tự. Nếu điều kiện trước đã quyết định kết quả, điều kiện sau không được gọi. Nếu một predicate ném ngoại lệ, ngoại lệ được truyền ra, không được tự chuyển thành `false`. [Java 17: Predicate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html)

### 4.4. Cố định mốc tham chiếu của một đợt xử lý

Giả sử muốn xóa nhiệm vụ đã lưu trữ hoặc hết hạn trước ngày chốt:

```java
record Task(String id, LocalDate expiresOn, boolean archived) {}

LocalDate cutoff = LocalDate.of(2025, 1, 1);

Predicate<Task> shouldDelete = task ->
        task.archived()
        || (task.expiresOn() != null
            && task.expiresOn().isBefore(cutoff));

tasks.removeIf(shouldDelete);
```

Đây là minh họa cần import `LocalDate`, `Predicate` và một danh sách `tasks` không chứa phần tử `null`. Ở đây `expiresOn == null` được quy ước là không có ngày hết hạn.

Điều kiện dùng “trước ngày chốt”, nên nhiệm vụ có ngày hết hạn đúng `cutoff` chưa bị xóa vì ngày. Nếu muốn “đến hết ngày chốt”, phải diễn đạt điều kiện bao gồm ngày bằng.

Không gọi đồng hồ hoặc tải trạng thái thay đổi liên tục cho từng phần tử nếu yêu cầu nghiệp vụ là xét tất cả theo cùng một mốc. Tính mốc một lần làm kết quả dễ kiểm thử và giải thích hơn. Với thời điểm chính xác hoặc múi giờ, chọn kiểu thời gian và quy tắc phù hợp; không tự đổi mọi bài toán sang ngày địa phương.

## 5. Giữ predicate tập trung vào việc kiểm tra

Một predicate dễ kiểm soát thường:

- Chỉ đọc phần tử và các giá trị tham chiếu đã được chuẩn bị.
- Trả `true` hoặc `false` theo quy tắc rõ.
- Không tự thêm/xóa phần tử trong chính collection đang được xử lý.
- Không sửa thuộc tính được dùng để quyết định cho những phần tử khác.
- Không thực hiện giao dịch bên ngoài như gửi tin, trừ tiền hoặc xóa bản ghi từ xa.

Ví dụ cần tránh:

```java
// Minh họa một cách viết sai: predicate lại sửa chính danh sách đang xóa.
items.removeIf(item -> {
    items.add(replacement);
    return item.isExpired();
});
```

`items`, `replacement` và kiểu phần tử trong đoạn trên chỉ minh họa tình huống. Sửa cấu trúc ngay trong predicate có thể làm quá trình duyệt thất bại hoặc vi phạm yêu cầu của cách triển khai. Không dựa vào kiểu ngoại lệ cụ thể như một cơ chế điều khiển hợp lệ.

Một điều kiện cần gọi dịch vụ mạng để biết có xóa hay không cũng khiến thời gian xử lý và lỗi khó dự đoán. Khi phù hợp, chuẩn bị dữ liệu tham chiếu trước, kiểm tra tính hợp lệ rồi đánh giá điều kiện trong bộ nhớ.

Nếu cần ghi lại những mục bị loại, nên thiết kế quá trình phân loại hoặc tạo kết quả riêng. Đừng dựa vào số lần hoặc thứ tự predicate được gọi như một cơ chế kiểm toán chung cho mọi collection.

## 6. Ngoại lệ và trạng thái xóa dở dang

### 6.1. Không có bảo đảm giao dịch trong hợp đồng chung

Giả sử predicate xóa số chẵn nhưng ném lỗi khi gặp 3. Một cách triển khai mặc định có thể đã xóa 2 trước khi chạm đến 3. Ngoại lệ kết thúc phương thức, nhưng không tự đưa 2 trở lại.

Do đó:

- Khi phương thức ném ngoại lệ, không có giá trị `boolean` được trả cho lần gọi đó.
- Không được kết luận collection không đổi chỉ vì không nhận được `true`.
- Không tự thử lại nếu predicate đã có tác động bên ngoài hoặc yêu cầu phải xử lý chính xác một lần.

Một lớp cụ thể có thể xử lý khác, chẳng hạn đánh dấu trước rồi mới sửa dữ liệu. Điều đó không tạo một bảo đảm hoàn tác áp dụng cho tất cả `Collection`.

Chương trình cuối bài tạo một collection nhỏ dùng triển khai mặc định để quan sát xóa dở dang. Nó không lấy hành vi lỗi riêng của `ArrayList` để suy ra hợp đồng chung.

### 6.2. Khi cần “tất cả hoặc không có gì”

Nếu yêu cầu là chỉ công bố kết quả khi mọi điều kiện đều đánh giá thành công, có thể:

1. Tạo một collection kết quả riêng.
2. Đánh giá điều kiện và đưa các phần tử cần giữ vào kết quả.
3. Nếu tất cả thành công, thay tham chiếu do thành phần sở hữu quản lý.

Đây vẫn cần thiết kế phù hợp với các bên đang giữ tham chiếu và với truy cập đồng thời. Tạo bản sao không tự tạo giao dịch với cơ sở dữ liệu hoặc dịch vụ bên ngoài; bản sao thường chỉ chứa lại các tham chiếu phần tử.

Không xem `clear()` rồi `addAll(result)` trên collection dùng chung là một thao tác nguyên tử. Nếu nhiều bên phải cùng quan sát một trạng thái nhất quán, phải có cơ chế công bố hoặc đồng bộ riêng.

## 7. Xóa tại chỗ hay tạo kết quả mới?

Hai đoạn có chiều điều kiện khác nhau:

```java
numbers.removeIf(isEven); // Xóa phần tử isEven == true.
```

```java
List<Integer> kept = numbers.stream()
        .filter(isEven.negate()) // Giữ phần tử isEven == false.
        .toList();
```

Đây là minh họa với `Predicate<Integer> isEven` đã được định nghĩa.

| Đặc điểm | `removeIf` | `stream().filter(...).toList()` |
| --- | --- | --- |
| Đối tượng bị thay đổi | Collection đích | Không sửa cấu trúc nguồn qua thao tác lọc |
| `true` của điều kiện | Xóa | Giữ |
| Kết quả | `boolean` cho biết có xóa không | Một danh sách kết quả |
| Yêu cầu quyền xóa nguồn | Có | Không |
| Tham chiếu phần tử | Phần tử giữ lại vẫn là các đối tượng đó | Kết quả thường vẫn tham chiếu các đối tượng nguồn |

Trong Java 17, danh sách do `Stream.toList()` trả về không hỗ trợ sửa. Nếu cần danh sách kết quả có thể sửa, hãy tạo `ArrayList` rõ ràng hoặc dùng cách thu thập phù hợp. Không nhầm `toList()` với một cam kết tạo `ArrayList`. [Java 17: Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())

Lựa chọn theo quyền sở hữu: nếu phương thức được giao nhiệm vụ làm sạch một collection có thể sửa, `removeIf` thường diễn đạt trực tiếp. Nếu bên gọi cần giữ dữ liệu gốc hoặc nhiều nơi đang dùng nó, một kết quả mới có thể phù hợp hơn.

## 8. Xóa trên view và trên Map

`Map` không có `removeIf` trực tiếp như `Collection`, nhưng các view của nó là collection.

Ví dụ xóa mục hết hàng:

```java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("book", 0);
stock.put("pen", 2);
stock.put("case", 0);

stock.entrySet().removeIf(entry -> entry.getValue() == 0);

System.out.println(stock); // {pen=2}
```

Cần import `Map` và `LinkedHashMap`. Dữ liệu minh họa bảo đảm giá trị tồn kho không phải `null`.

`entrySet()` là view gắn với map; xóa entry qua view làm mất ánh xạ tương ứng trong map. Nó không phải bản sao độc lập.

Các hướng thường gặp:

```java
map.keySet().removeIf(keyRule);
map.values().removeIf(valueRule);
map.entrySet().removeIf(entryRule);
```

Đây là các dạng sử dụng, không phải chương trình độc lập. Nếu điều kiện cần cả khóa và giá trị, dùng `entrySet` giúp diễn đạt trực tiếp hơn.

Một giá trị có thể xuất hiện ở nhiều khóa. `map.values().removeIf(v -> condition)` có thể làm mất nhiều ánh xạ nếu nhiều giá trị thỏa điều kiện.

Tương tự, `subList` của một danh sách là một view. Xóa trên `subList` có thể xóa cả phần tử trong danh sách gốc. Luôn kiểm tra xem đối tượng đang giữ là dữ liệu riêng hay một lớp nhìn vào dữ liệu khác. [Java 17: Map views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#entrySet()), [List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int))

## 9. Đồng thời và chi phí thực thi

### 9.1. removeIf không làm collection thông thường thành cấu trúc đồng thời

Không gọi `removeIf` trên một `ArrayList` đang bị luồng khác sửa mà không có cơ chế phối hợp.

Ngay cả với cấu trúc hỗ trợ truy cập đồng thời, cần đọc hợp đồng cụ thể. Không suy ra toàn bộ lần gọi `removeIf` là một giao dịch cho mọi phần tử, hoặc toàn bộ predicate nhìn thấy cùng một ảnh chụp bất biến.

`CopyOnWriteArrayList` là ví dụ quan trọng về việc lớp có thể ghi đè hành vi: iterator của nó không cho xóa, nhưng bản thân danh sách hỗ trợ `removeIf`. Vì vậy, không kết luận khả năng của `removeIf` chỉ từ khả năng của iterator. Chi phí sao chép khi sửa cũng khiến lựa chọn này phù hợp hơn với mô hình đọc nhiều, sửa ít. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

### 9.2. Tính cả chi phí điều kiện lẫn chi phí xóa

Nếu phải xét `n` phần tử, predicate được đánh giá trong quá trình xử lý số phần tử đó. Một điều kiện đơn giản khác xa điều kiện gọi mạng hoặc tìm trong một danh sách lớn mỗi lần.

Ví dụ:

```java
items.removeIf(item -> blockedIds.contains(item.id()));
```

Nếu `blockedIds` là một danh sách có `m` phần tử và thường phải duyệt dài để tìm, riêng phần kiểm tra có thể dẫn tới chi phí gần `n × m`. Một tập tra cứu được xây dựng trước có thể giảm chi phí trung bình nếu phù hợp với quy tắc bằng nhau và dữ liệu không đổi trong đợt xử lý.

Mặt khác, việc xóa phụ thuộc cấu trúc: liên kết nút, dịch chuyển dữ liệu, gom phần tử hoặc sao chép có chi phí khác nhau. Một lớp có thể tối ưu xóa hàng loạt. Không khẳng định mọi `removeIf` đều O(n), cũng không mặc định nó luôn nhanh hơn mọi vòng lặp thủ công.

Khi dữ liệu lớn, đo với kiểu collection, tỷ lệ khớp và predicate đại diện cho thực tế. Độ rõ của quy tắc vẫn quan trọng hơn việc rút ngắn lambda bằng mọi giá.

## 10. Chương trình Java 17 hoàn chỉnh

Lưu mã sau vào `RemoveIfDemo.java`:

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Predicate;

public class RemoveIfDemo {
    static final class IterableBag<E> extends AbstractCollection<E> {
        private final List<E> data;

        IterableBag(List<E> source) {
            data = new ArrayList<>(source);
        }

        @Override
        public Iterator<E> iterator() {
            return data.iterator();
        }

        @Override
        public int size() {
            return data.size();
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 2, 3, 4));
        boolean changed = numbers.removeIf(n -> n % 2 == 0);
        System.out.println("removed even = " + changed);
        System.out.println("numbers = " + numbers);
        System.out.println("removed above 10 = " + numbers.removeIf(n -> n > 10));

        List<String> names = new ArrayList<>(
                Arrays.asList(null, "", "  ", "Lan", "Minh"));
        names.removeIf(name -> name == null || name.isBlank());
        System.out.println("names = " + names);

        Predicate<String> longName = name -> name.length() > 3;
        Predicate<String> startsWithM = name -> name.startsWith("M");
        names.removeIf(longName.and(startsWithM));
        System.out.println("after composed rule = " + names);

        List<Integer> original = new ArrayList<>(List.of(1, 2, 3, 4));
        List<Integer> kept = original.stream().filter(n -> n % 2 != 0).toList();
        System.out.println("original = " + original);
        System.out.println("filtered copy = " + kept);

        Map<String, Integer> stock = new LinkedHashMap<>();
        stock.put("book", 0);
        stock.put("pen", 2);
        stock.put("case", 0);
        stock.entrySet().removeIf(entry -> entry.getValue() == 0);
        System.out.println("stock = " + stock);

        try {
            Arrays.asList(1, 2, 3).removeIf(n -> n % 2 == 0);
        } catch (UnsupportedOperationException expected) {
            System.out.println("fixed-size removal is unsupported");
        }

        try {
            numbers.removeIf(null);
        } catch (NullPointerException expected) {
            System.out.println("null predicate is invalid");
        }

        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>(List.of("active", "stale"));
        listeners.removeIf("stale"::equals);
        System.out.println("listeners = " + listeners);

        IterableBag<Integer> bag = new IterableBag<>(List.of(1, 2, 3, 4));
        try {
            bag.removeIf(n -> {
                if (n == 3) {
                    throw new IllegalStateException("stop at 3");
                }
                return n % 2 == 0;
            });
        } catch (IllegalStateException expected) {
            System.out.println("predicate failure = " + expected.getMessage());
        }
        System.out.println("bag after failure = " + bag);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RemoveIfDemo.java
java RemoveIfDemo
```

Stdout:

```text
removed even = true
numbers = [1, 3]
removed above 10 = false
names = [Lan, Minh]
after composed rule = [Lan]
original = [1, 2, 3, 4]
filtered copy = [1, 3]
stock = {pen=2}
fixed-size removal is unsupported
null predicate is invalid
listeners = [active]
predicate failure = stop at 3
bag after failure = [1, 3, 4]
```

Cách kiểm chứng từng phần:

1. Danh sách số xóa mọi số chẵn, kể cả phần tử trùng. Kết quả trả về là `true`; lần tìm số lớn hơn 10 không xóa gì nên là `false`.
2. Điều kiện có kiểm tra `null` ở trước làm sạch được cả phần tử `null` lẫn chuỗi trắng.
3. `and` xóa `"Minh"` vì đồng thời dài hơn 3 và bắt đầu bằng `M`.
4. Stream tạo danh sách giữ số lẻ; danh sách `original` vẫn còn đủ 4 phần tử.
5. Xóa qua `entrySet` thay đổi chính map tồn kho.
6. Danh sách kích thước cố định không hỗ trợ việc xóa phần tử 2.
7. Predicate `null` bị từ chối.
8. `CopyOnWriteArrayList.removeIf` vẫn hoạt động dù iterator của lớp không hỗ trợ xóa.
9. `IterableBag` kế thừa `AbstractCollection`, chỉ cung cấp iterator và kích thước. Nó dùng thuật toán `removeIf` mặc định. Phần tử 2 đã bị xóa trước lúc predicate ném lỗi tại 3, nên sau lỗi còn `[1, 3, 4]`.

Lớp nhỏ `IterableBag` ở đây chỉ để làm rõ hợp đồng và trạng thái khi lỗi; không phải đề xuất viết một collection mới thay cho các lớp JDK trong ứng dụng thông thường.

## 11. Lỗi thường gặp

| Lỗi | Cách hiểu đúng |
| --- | --- |
| Viết điều kiện giữ vào `removeIf` | `true` nghĩa là xóa; đảo điều kiện khi cần |
| Cho rằng trả `true` là xóa đúng một phần tử | Nó chỉ nói có thay đổi, có thể đã xóa nhiều phần tử |
| Dùng predicate gọi phương thức trên phần tử có thể `null` | Đặt quy tắc và kiểm tra `null` trước |
| Coi `Arrays.asList` là danh sách có thể thêm/xóa | Nó có kích thước cố định |
| Coi view là bản sao | Xóa có thể truyền xuống dữ liệu gốc |
| Xóa hoặc thêm lại vào collection từ predicate | Có thể phá hợp đồng duyệt và gây lỗi |
| Predicate vừa kiểm tra vừa gửi thông báo/giao dịch | Lỗi hoặc thử lại có thể để lại tác động không thể hoàn tác |
| Coi ngoại lệ nghĩa là chưa có gì bị xóa | Hợp đồng chung có thể để lại thay đổi dở dang |
| Coi phương thức trên collection đồng thời là giao dịch toàn bộ | Phải kiểm tra bảo đảm cụ thể và bất biến cần giữ |
| Giả định iterator không xóa được thì `removeIf` cũng không được | Lớp có thể ghi đè phương thức để hỗ trợ |

## 12. Tự luyện

1. Danh sách `[1, 2, 2, 3]` gọi `removeIf(n -> n == 2)`. Còn gì và trả gì?  
   **Đáp án:** còn `[1, 3]`, trả `true`.

2. Danh sách có `null`, `""` và `"A"`. Viết điều kiện xóa hai phần tử đầu mà không gây lỗi.  
   **Đáp án:** `value -> value == null || value.isBlank()`.

3. Đã có predicate `shouldKeep`. Muốn xóa những phần tử không cần giữ thì truyền gì?  
   **Đáp án:** `shouldKeep.negate()`, với giả định predicate hợp lệ cho mọi phần tử.

4. Tại sao `removeIf` trên `Arrays.asList(1, 2, 3)` không thể xóa số 2?  
   **Đáp án:** danh sách đó không hỗ trợ thay đổi kích thước.

5. Predicate đã xóa một phần tử rồi ném lỗi ở phần tử tiếp theo. Có thể dựa vào hợp đồng chung để khẳng định dữ liệu được hoàn tác không?  
   **Đáp án:** không. Phải kiểm tra bảo đảm của cách triển khai và thiết kế quy trình riêng nếu cần tính nguyên tử.

Một điều kiện xóa tốt diễn đạt rõ đối tượng nào phải bị loại, xử lý đủ dữ liệu biên và không tạo thêm tác động khó kiểm soát. Trước khi gọi `removeIf`, xác nhận cả quy tắc điều kiện lẫn quyền sửa collection đang nắm giữ.
