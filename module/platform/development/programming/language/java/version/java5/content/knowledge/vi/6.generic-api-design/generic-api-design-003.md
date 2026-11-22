# Thiết kế hàm sao chép dữ liệu giữa các collection

## 1. Trước khi chọn kiểu, hãy định nghĩa “sao chép”

Một hàm sao chép giữa các collection cần mô tả ít nhất hai thứ: **quan hệ kiểu phần tử** và **tác động lên dữ liệu đích**.

Cùng nói “copy”, nhưng các thao tác có thể khác nhau:

| Nhu cầu | Tác động |
| --- | --- |
| Thêm các phần tử nguồn vào collection đích | Giữ dữ liệu cũ, thử thêm từng phần tử |
| Thay các vị trí đã có trong một danh sách | Không tăng kích thước danh sách |
| Tạo một collection mới từ nguồn | Tạo cấu trúc chứa mới |
| Tạo cả các đối tượng phần tử mới | Cần quy tắc sao chép sâu hoặc hàm chuyển đổi riêng |

Bài này thiết kế một hàm **thêm các phần tử nguồn vào đích**, rồi đối chiếu với `Collections.copy` của JDK. Hàm minh họa không xóa đích và không xóa nguồn.

Ví dụ mục tiêu:

```text
Nguồn List<Integer>: [1, 2, 2]
Đích List<Number>:   [0.5]

Sau khi thêm:
Đích: [0.5, 1, 2, 2]
```

Các quy tắc generics áp dụng trên Java hiện đại; chương trình hoàn chỉnh chạy với Java 17+.

## 2. Chữ ký phải nối được nguồn và đích

Nguồn cung cấp các giá trị mà thuật toán đọc được như `T`. Đích phải nhận được những giá trị `T` đó:

```java
static <T> int appendAll(
        Collection<? extends T> source,
        Collection<? super T> destination)
```

Đây là chữ ký rút gọn để thảo luận, chưa phải phương thức đầy đủ.

Cách đọc:

- `source` là nguồn cung cấp: dùng `? extends T`.
- `destination` là nơi nhận: dùng `? super T`.
- `T` đặt tên cho kiểu trung gian nối hai phía.

Đó là ứng dụng của PECS: Producer Extends, Consumer Super.

Ví dụ hợp lệ:

```java
List<Integer> integers = List.of(1, 2, 3);
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

appendAll(integers, numbers);
appendAll(integers, objects);
```

Với `T = Integer`, nguồn cung cấp `Integer`; cả `Number` và `Object` đều là kiểu cha nhận được giá trị đó.

Chiều ngược lại không được bảo đảm:

```java
List<Number> mixed = List.of(1, 2.5);
List<Integer> integers = new ArrayList<>();

// appendAll(mixed, integers); // Không biên dịch.
```

Nguồn có thể chứa `Double`, trong khi đích chỉ nhận `Integer`. Hàm sao chép không phải một phép chuyển đổi số và không được dùng cast để ép hợp đồng này qua trình biên dịch.

## 3. Vì sao các chữ ký dễ nghĩ tới lại không phù hợp?

### 3.1. Collection<Object> không đại diện cho mọi collection

```java
// Quá hẹp cho nhu cầu tổng quát:
// void appendAll(Collection<Object> source,
//                Collection<Object> destination)
```

`Collection<Integer>` không gán trực tiếp được cho `Collection<Object>`. Kiểu tổng quát là bất biến: quan hệ kiểu con của phần tử không tự lan thành quan hệ tương ứng giữa các kiểu collection cụ thể.

### 3.2. Hai Collection<T> yêu cầu trùng kiểu quá chặt

```java
// Chữ ký quá chặt:
// <T> void appendAll(Collection<T> source, Collection<T> destination)
```

Chữ ký này không cho phép truyền đồng thời một biến `List<Integer>` và một biến `List<Number>` như hai `Collection<T>` có cùng đối số kiểu chính xác. Trong khi đó, việc đọc từng `Integer` rồi thêm vào danh sách `Number` hoàn toàn an toàn.

Wildcard giúp nới phạm vi đúng theo chiều dữ liệu, thay vì bỏ kiểm tra kiểu.

### 3.3. Hai dấu hỏi độc lập không nối được luồng dữ liệu

```java
// Không đủ quan hệ để cài đặt thao tác thêm phần tử bất kỳ:
// void appendAll(Collection<?> source, Collection<?> destination)
```

Nguồn có thể là `Collection<String>`, đích có thể là `Collection<Integer>`. Hai dấu `?` không cam kết cùng một kiểu, nên không được đọc một `Object` từ nguồn rồi thêm tùy ý vào đích.

Tên `T` trong chữ ký tốt không chỉ để trang trí; nó diễn tả quan hệ giữa hai vị trí chưa biết.

## 4. Chọn hợp đồng sao chép có thể kiểm chứng

Hàm minh họa có các quy tắc sau:

1. Cả hai tham chiếu collection phải khác `null`.
2. Đọc toàn bộ nguồn vào một danh sách tạm trước khi sửa đích.
3. Duyệt các phần tử trong danh sách tạm rồi gọi `destination.add`.
4. Trả về số lần `add` làm thay đổi đích, theo giá trị boolean mà `add` trả về.
5. Không thực hiện hoàn tác nếu một thao tác thêm ném ngoại lệ.
6. Sao chép tham chiếu phần tử, không tự sao chép sâu đối tượng.

### 4.1. Vì sao dùng danh sách tạm?

Nếu vừa duyệt nguồn vừa thêm vào đích, nguồn và đích có thể là cùng một đối tượng:

```java
List<String> values = new ArrayList<>(List.of("a", "b"));
appendAll(values, values);
```

Một vòng lặp trực tiếp trên `values` rồi `add` vào chính nó thường làm hỏng điều kiện duyệt, chẳng hạn gây `ConcurrentModificationException` với `ArrayList`.

Ngoài việc cùng tham chiếu, nguồn và đích còn có thể là hai góc nhìn dùng chung dữ liệu nền, ví dụ nguồn là `subList` của đích. Chỉ kiểm tra `source == destination` không nhận diện hết các quan hệ đó.

Danh sách tạm tách giai đoạn đọc khỏi giai đoạn sửa đích:

```text
nguồn → danh sách tạm chứa các tham chiếu đã đọc → đích
```

Nó cho phép xác định rõ: chỉ xử lý các phần tử được đọc trong giai đoạn đầu. Trường hợp tự sao chép danh sách vì thế chỉ thêm một lần mỗi phần tử ban đầu, không tiếp tục đuổi theo các phần tử vừa thêm.

Danh sách tạm không tạo một ảnh chụp nguyên tử khi luồng khác đang sửa nguồn; nó cũng không bảo đảm an toàn đa luồng. Hợp đồng ở đây giả định không có sửa đổi đồng thời ngoài quá trình sao chép được mô tả.

### 4.2. Vì sao trả về số phần tử được thêm?

Với một `List`, thêm ba phần tử thường làm kích thước tăng ba. Với một `Set`, các phần tử trùng có thể đã tồn tại nên `add` trả `false`.

Do đó, tên kết quả `added` trong bài là số lần thêm thực sự làm thay đổi collection, không phải số lần thử thêm hay số phần tử đã duyệt.

Nếu API chỉ cần biết đích có thay đổi không, một kết quả boolean như `addAll` chuẩn là đủ. Không cần đếm chi tiết nếu nơi gọi không sử dụng thông tin đó.

### 4.3. Chi phí của lựa chọn danh sách tạm

Với nguồn có n phần tử, danh sách tạm cần thêm O(n) ô lưu tham chiếu. Thuật toán đọc nguồn rồi thực hiện n lần thử thêm; thời gian tổng còn phụ thuộc chi phí duyệt nguồn và cách cài đặt `add` của đích. Không nên tuyên bố thời gian O(n) cho mọi `Collection` tùy ý.

Nếu dữ liệu rất lớn và hợp đồng bảo đảm nguồn, đích không dùng chung dữ liệu, có thể chọn một phiên bản duyệt trực tiếp để giảm bộ nhớ phụ. Khi đó phải nêu rõ điều kiện đó thay vì ngầm hứa hỗ trợ cả tự sao chép.

## 5. Chương trình hoàn chỉnh

Lưu thành `CollectionCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class CollectionCopyDemo {
    static <T> int appendAll(
            Collection<? extends T> source,
            Collection<? super T> destination) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(destination, "destination");

        List<T> snapshot = new ArrayList<>(source);

        int added = 0;
        for (T value : snapshot) {
            if (destination.add(value)) {
                added++;
            }
        }
        return added;
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 2);

        List<Number> numbers = new ArrayList<>(List.of(0.5));
        int listAdded = appendAll(source, numbers);
        System.out.println("list added = " + listAdded);
        System.out.println("numbers = " + numbers);

        Set<Number> unique = new LinkedHashSet<>();
        unique.add(2);
        int setAdded = appendAll(source, unique);
        System.out.println("set added = " + setAdded);
        System.out.println("unique = " + unique);

        List<String> self = new ArrayList<>(List.of("a", "b"));
        int selfAdded = appendAll(self, self);
        System.out.println("self added = " + selfAdded);
        System.out.println("self = " + self);

        List<Number> slots =
                new ArrayList<>(List.of(-1, -1, -1, -1));
        Collections.copy(slots, source);
        System.out.println("replaced = " + slots);

        // Không biên dịch nếu bật dòng sau:
        // appendAll(List.of(1.5), new ArrayList<Integer>());
    }
}
```

Biên dịch và chạy với JDK 17+:

```shell
javac --release 17 -Xlint:all CollectionCopyDemo.java
java CollectionCopyDemo
```

Stdout chính xác:

```text
list added = 3
numbers = [0.5, 1, 2, 2]
set added = 1
unique = [2, 1]
self added = 2
self = [a, b, a, b]
replaced = [1, 2, 2, -1]
```

Giải thích:

- `numbers` nhận cả ba phần tử và giữ giá trị `0.5` đã có.
- `unique` đã có số `2`, chỉ thêm mới số `1`. `LinkedHashSet` giữ thứ tự thêm nên in `[2, 1]`.
- Tự sao chép danh sách hoạt động theo hợp đồng danh sách tạm của hàm này.
- `Collections.copy` thay ba vị trí đầu của `slots`; vị trí cuối vẫn là `-1`.

Không có cast trong mã nguồn và không cần cảnh báo chuyển kiểu không được kiểm tra. Quan hệ nguồn–đích được bảo vệ bằng chữ ký tổng quát.

## 6. Đối chiếu với API chuẩn: thêm và thay thế khác nhau

### 6.1. Collection.addAll là thao tác thêm

Một cách thông thường khi đích đã có kiểu phù hợp:

```java
List<Number> destination = new ArrayList<>();
List<Integer> source = List.of(1, 2, 3);

boolean changed = destination.addAll(source);
```

`Collection<E>.addAll` nhận `Collection<? extends E>`, nên danh sách `Number` có thể nhận nguồn `Integer`.

Hãy dùng API sẵn có nếu nó đáp ứng hợp đồng của bài toán. Hàm `appendAll` trong bài có chủ đích bổ sung việc đếm và tạo danh sách tạm trước khi sửa đích.

Không nên suy từ một cách cài đặt cụ thể rằng `collection.addAll(collection)` luôn có hành vi ổn định cho mọi collection. Hợp đồng chung của `Collection.addAll` không bảo đảm trường hợp nguồn bị sửa trong lúc thêm, bao gồm nguồn và đích là cùng collection không rỗng.

### 6.2. Collections.copy là thay thế theo vị trí

Chữ ký chuẩn:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Đây là chữ ký API, không phải phần cài đặt đầy đủ.

Lưu ý thứ tự **đích trước, nguồn sau**, ngược với hàm `appendAll(source, destination)` được đặt trong bài.

`Collections.copy` yêu cầu danh sách đích đã có đủ phần tử để thay thế. Nó không thêm phần tử mới để làm tăng `size`.

```java
List<Integer> source = List.of(1, 2, 3);
List<Number> destination = new ArrayList<>(3);

// destination.size() vẫn là 0.
// Collections.copy(destination, source);
// Ném IndexOutOfBoundsException: đích chưa có đủ vị trí.
```

Tham số `3` của `ArrayList` ở đây là sức chứa ban đầu (capacity), không phải số phần tử. Cách có sẵn ba vị trí, nếu bài toán thật sự cần thay thế, là khởi tạo một danh sách có ba phần tử:

```java
List<Number> destination =
        new ArrayList<>(List.of(-1, -1, -1));

Collections.copy(destination, source);
```

Nếu chỉ cần lấy một bản sao mới, không có lý do bắt đầu từ danh sách chứa các giá trị giữ chỗ; dùng hàm tạo sao chép ở mục tiếp theo sẽ rõ ý hơn.

### 6.3. Tạo collection mới

```java
List<Number> copied = new ArrayList<Number>(source);
```

Hàm tạo nhận nguồn có phần tử thuộc kiểu phù hợp với `Number`. Nó tạo cấu trúc danh sách mới, không sửa một đích đã tồn tại.

Nếu cần một danh sách không cho thay đổi cấu trúc và không có phần tử `null`, có thể dùng `List.copyOf(source)`. Nó không phải công cụ sao chép sâu; API cũng có thể tái sử dụng một danh sách phù hợp đã có, nên không nên dùng nó để đòi một đối tượng collection có danh tính mới.

## 7. Những điều kiểu tổng quát không bảo đảm

### 7.1. Đích có hỗ trợ thao tác sửa hay không

Một `Collection<? super T>` cho biết kiểu phần tử nhận được, không chứng minh `add` được hỗ trợ.

| Đích | Thêm bằng `add` | Thay bằng `set` theo chỉ số |
| --- | --- | --- |
| `ArrayList` có thể sửa | Có | Có |
| Danh sách từ `Arrays.asList` | Không tăng kích thước được | Có |
| Danh sách từ `List.of` | Không | Không |

Bảng nói về các cách cài đặt thông thường nêu tên. Với một interface tùy biến, hãy đọc hợp đồng của đối tượng thực tế. Thao tác không được hỗ trợ có thể ném `UnsupportedOperationException`.

### 7.2. Chính sách phần tử null và các giới hạn dữ liệu

Hàm `appendAll` chặn tham chiếu collection `null`, nhưng không tự loại phần tử `null` trong nguồn. Đích quyết định có nhận phần tử đó hay không.

Một collection có thể có thêm ràng buộc, chẳng hạn phần tử phải so sánh được hoặc thỏa quy tắc riêng. Generics không thay thế mọi kiểm tra lúc chạy của đích.

### 7.3. Tính nguyên tử

Nếu đích chấp nhận hai phần tử đầu rồi ném ngoại lệ ở phần tử thứ ba, hai phần tử đã thêm có thể vẫn còn. Hàm không trả về bình thường và không hoàn tác.

Danh sách tạm chỉ bảo vệ giai đoạn duyệt nguồn khỏi các sửa đổi do hàm thực hiện ở giai đoạn sau; nó không biến toàn bộ thao tác thành một giao dịch.

Nếu cần “thành công tất cả hoặc không thay đổi gì”, phải có thiết kế riêng cho loại đích và cách công bố kết quả. Một vòng lặp tổng quát trên mọi `Collection` không thể tự hứa điều đó.

### 7.4. Thứ tự và phần tử trùng

Nguồn được đọc theo thứ tự duyệt của nó. Danh sách tạm giữ thứ tự đọc đó; đích có thể có quy tắc riêng:

- `List` giữ phần tử trùng và thứ tự thêm.
- `LinkedHashSet` loại trùng và giữ thứ tự thêm.
- `HashSet` không bảo đảm thứ tự duyệt giống thứ tự nguồn.
- Một tập hợp có sắp xếp có thể trình bày phần tử theo bộ so sánh.

Đừng cam kết “đích giống hệt nguồn” khi hợp đồng nhận một `Collection` bất kỳ.

## 8. Sao chép tham chiếu và sao chép sâu

Các hàm đã dùng chỉ sao chép tham chiếu phần tử. Nếu nguồn chứa một `StringBuilder`, hai collection có thể cùng trỏ đến bộ đệm đó:

```java
StringBuilder shared = new StringBuilder("a");
List<StringBuilder> source = List.of(shared);
List<StringBuilder> destination = new ArrayList<>();

appendAll(source, destination);
shared.append("b");

System.out.println(destination.get(0)); // ab
```

Danh sách đích có cấu trúc riêng không có nghĩa các đối tượng phần tử độc lập.

Nếu cần tạo phần tử mới, hãy truyền một hàm có hợp đồng tạo bản sao, chẳng hạn `Function<? super S, ? extends T>`. Với `StringBuilder`, thao tác có thể tạo `new StringBuilder(original.toString())`.

Sao chép sâu một đồ thị đối tượng còn cần quyết định về tham chiếu dùng chung, chu trình và tài nguyên. Một tham số kiểu `T` không tự cung cấp những quy tắc đó.

## 9. Cách lựa chọn API

Trước khi viết hàm mới, xác định lần lượt:

1. Thêm vào đích, thay vị trí hay tạo collection mới?
2. Nguồn cung cấp kiểu gì và đích nhận được kiểu gì?
3. Có cần hỗ trợ nguồn và đích dùng chung dữ liệu không?
4. Giữ phần tử trùng, thứ tự, `null` và trạng thái sửa một phần như thế nào?
5. Sao chép tham chiếu có đủ không, hay cần một quy trình tạo đối tượng mới?
6. API chuẩn đã đáp ứng đủ hợp đồng chưa?

Chọn `Collection` khi chỉ cần duyệt và thêm; chọn `List` khi thuật toán thực sự cần vị trí. Chữ ký tốt kết hợp đúng quan hệ kiểu với một hợp đồng tác động cụ thể, để nơi gọi không phải đoán ý nghĩa của từ “copy”.

## Tài liệu đối chiếu

- [Java Collection API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): `add`, `addAll`, thao tác tùy chọn và các giới hạn.
- [Java Collections.copy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)): sao chép bằng thay thế các vị trí đã tồn tại.
- [Java ArrayList API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html): phân biệt sức chứa và kích thước, hàm tạo nhận collection.
