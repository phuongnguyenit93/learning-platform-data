# Thiết kế hàm sao chép từ `List<? extends T>` sang `List<? super T>`

## Mục tiêu

Trong Java Generics, một hàm sao chép cần nhận phần tử từ một danh sách nguồn rồi đưa chúng vào một danh sách đích **mà không làm mất an toàn kiểu**. Khi nguồn chứa `Integer` và đích chứa `Number` hoặc `Object`, ta muốn chương trình vẫn biên dịch, dù `List<Integer>` không phải subtype của `List<Number>`.

Chữ ký tổng quát giải quyết yêu cầu ấy là:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source)
```

Đây là **chữ ký minh họa**, phần thân đầy đủ được trình bày ở ví dụ chạy độc lập phía dưới. Bài học giúp bạn:

- Xác định đúng vai trò **nguồn đọc** (producer) và **đích ghi** (consumer) theo quy tắc PECS.
- Giải thích vì sao `List<? extends T>` đọc được phần tử dạng `T`, còn `List<? super T>` nhận được phần tử dạng `T`.
- Tự thiết kế hàm **nối thêm một bản sao các phần tử** theo thứ tự, bảo toàn danh sách nguồn.
- Phân biệt hàm nối thêm với `Collections.copy(destination, source)`, vốn **ghi đè theo chỉ số** và cần dung lượng *hiện có* của đích.
- Biết xử lý trường hợp nguồn và đích chính là một danh sách, các danh sách không sửa được và những giới hạn runtime.

## 1. Bài toán và giới hạn của generics bất biến

Giả sử:

```java
List<Integer> integers = new ArrayList<>(List.of(2, 4));
List<Number> numbers = new ArrayList<>();
```

Ta có `Integer extends Number`, nhưng **không thể gán `List<Integer>` cho `List<Number>`**:

```java
// List<Number> invalid = integers; // lỗi biên dịch
```

Nếu phép gán ấy được chấp nhận, một nơi đang giữ `List<Number>` có thể thêm `Double` vào đối tượng thực là `List<Integer>`. Vì vậy Java giữ `List<Integer>` và `List<Number>` **bất biến theo đối số kiểu** (*invariant*).

Tuy nhiên, đây là nhu cầu hợp lệ:

- **Đọc** số nguyên từ `List<Integer>`.
- **Ghi** từng số nguyên ấy vào `List<Number>`.

Ta không cần coi hai list là cùng kiểu; chỉ cần xác định quan hệ kiểu tại **điểm lấy phần tử** và **điểm đưa phần tử vào**.

## 2. PECS: Producer `extends`, Consumer `super`

Quy tắc **PECS** (*Producer Extends, Consumer Super*) định hướng wildcard theo vai trò tham số:

| Vai trò | Kiểu khai báo | Điều chắc chắn có thể làm |
| --- | --- | --- |
| Nguồn cung cấp `T` | `List<? extends T>` | Đọc phần tử ra biến kiểu `T` |
| Đích nhận `T` | `List<? super T>` | Thêm một giá trị kiểu `T` vào đích |
| Danh sách có kiểu chính xác | `List<T>` | Đọc và thêm giá trị kiểu `T`, nếu implementation cho phép |

### Vì sao `source` dùng `? extends T`?

`List<? extends T>` có kiểu phần tử thực là một subtype **chưa biết chính xác** của `T`. Mọi giá trị lấy ra đều có thể dùng như `T`:

```java
static <T> T firstOf(List<? extends T> source) {
    return source.get(0);
}
```

Đoạn trên là phương thức minh họa, giả định list không rỗng. Trình biên dịch cho phép `source.get(0)` trả về kiểu `T`. Nhưng gọi `source.add(valueOfTypeT)` nhìn chung **không biên dịch**, vì kiểu phần tử thực có thể là một subtype hẹp hơn `T`.

Ví dụ với `T = Number`, nguồn có thể là `List<Integer>` hoặc `List<Double>`. Ghi một `Number` bất kỳ vào danh sách ấy không an toàn.

### Vì sao `destination` dùng `? super T`?

`List<? super T>` có kiểu phần tử thực là `T` hoặc một siêu kiểu chưa biết của `T`. Nếu `T = Integer`, một `Integer` có thể được thêm an toàn vào `List<Integer>`, `List<Number>` hoặc `List<Object>`:

```java
static <T> void addOne(List<? super T> destination, T value) {
    destination.add(value);
}
```

Phương thức này là minh họa riêng, không phải ví dụ Java độc lập. Chiều ngược lại, lấy từ `List<? super T>` chỉ được bảo đảm nhận dưới `Object` vì phần tử đang nằm trong đích có thể được khai báo ở một kiểu rộng hơn `T`.

**Điểm cốt lõi:** hàm sao chép đọc `T` từ producer và ghi chính `T` vào consumer; nó không cần ép kiểu không kiểm tra và không cần `List<Integer>` chuyển thành `List<Number>`.

## 3. Chữ ký hàm sao chép và ý nghĩa từng thành phần

Ta chọn thứ tự tham số **đích trước, nguồn sau**:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source) {

    for (T value : source) {
        destination.add(value);
    }
}
```

Đoạn trên minh họa ý tưởng cơ bản, **chưa xử lý trường hợp nguồn và đích cùng một danh sách**. Phần sau sẽ dùng một bản chụp tạm để an toàn cho tình huống đó.

Phân tích chữ ký:

- `static <T>`: khai báo **type parameter của phương thức**; đây không phải cú pháp so sánh “bé hơn”.
- `void`: hàm thực hiện thao tác sao chép, không trả kết quả.
- `List<? super T> destination`: đích có thể tiếp nhận giá trị kiểu `T`.
- `List<? extends T> source`: nguồn cung cấp các giá trị có thể coi như `T`.
- `T value : source`: phép đọc an toàn; mỗi giá trị nguồn ít nhất tương thích với `T`.
- `destination.add(value)`: phép ghi an toàn; kiểu phần tử của đích là `T` hoặc một siêu kiểu của `T`.

Một ví dụ suy luận kiểu: gọi `appendCopy(numbers, integers)` với `List<Number>` là đích và `List<Integer>` là nguồn. Compiler có thể chọn `T = Integer`: nguồn `List<Integer>` phù hợp `List<? extends Integer>` và đích `List<Number>` phù hợp `List<? super Integer>`. Không phải bản thân `List<Integer>` trở thành `List<Number>`.

Bạn cũng có thể dùng lời gọi chỉ định đối số kiểu:

```java
// Khi đã có numbers và integers như ở trên:
appendCopy(numbers, integers);             // suy luận T
MyUtility.<Integer>appendCopy(numbers, integers); // cú pháp chỉ rõ T,
                                                   // nếu hàm thuộc lớp MyUtility
```

Hai dòng chỉ **minh họa cách gọi**; dòng có `MyUtility` đòi bạn đặt phương thức vào lớp tương ứng. Trong phần lớn trường hợp, để trình biên dịch tự suy luận `T` sẽ gọn và rõ hơn.

## 4. Phiên bản an toàn khi nguồn và đích cùng một danh sách

Một hàm append viết vòng `for-each` trực tiếp trên nguồn thường chạy tốt khi nguồn/đích độc lập. Nhưng nếu cùng một danh sách vừa bị duyệt vừa bị `add`, nhiều implementation như `ArrayList` có thể phát hiện thay đổi cấu trúc và ném `ConcurrentModificationException`. Không nên dựa vào hành vi của việc đồng thời duyệt và thêm vào cùng list.

Một giải pháp dễ kiểm chứng: **chụp tạm các phần tử nguồn trước, rồi mới thay đổi đích**:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source) {
    Objects.requireNonNull(destination, "destination");
    Objects.requireNonNull(source, "source");

    List<T> snapshot = new ArrayList<>(source);
    for (T value : snapshot) {
        destination.add(value);
    }
}
```

Lời gọi `new ArrayList<>(source)` tạo một **danh sách mới chứa các tham chiếu phần tử hiện có**. Nó không clone sâu từng đối tượng phần tử. Bản chụp tạm này làm cho vòng lặp chỉ đọc một cấu trúc ổn định trong khi hàm đang thêm vào đích.

Khi `destination == source`, giả sử dữ liệu đầu là `[7, 8]`, bản chụp chứa đúng `[7, 8]`; thêm hai phần tử ấy vào đối tượng nguồn/đích tạo `[7, 8, 7, 8]`. Hàm hoàn tất mà không vừa duyệt vừa mở rộng chính danh sách đang duyệt.

`Objects.requireNonNull` kiểm tra hai tham số trước thao tác sao chép và báo lỗi `NullPointerException` với tên đối số khi đầu vào null. Hai tham số không-null **không có nghĩa từng phần tử bên trong cũng không-null**; danh sách đích có thể có quy định riêng về phần tử null.

Phiên bản này được sử dụng trong chương trình hoàn chỉnh tiếp theo.

## 5. Ví dụ Java 17+ chạy độc lập

Lưu tệp với tên **`PecCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class PecCopyDemo {
    static <T> void appendCopy(
            List<? super T> destination,
            List<? extends T> source) {
        Objects.requireNonNull(destination, "destination");
        Objects.requireNonNull(source, "source");

        List<T> snapshot = new ArrayList<>(source);
        for (T value : snapshot) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(2, 4));
        List<Number> numbers = new ArrayList<>(List.of(1.5));
        appendCopy(numbers, integers);
        System.out.println("numbers: " + numbers);

        List<Object> objects = new ArrayList<>(List.of("begin"));
        appendCopy(objects, integers);
        System.out.println("objects: " + objects);

        List<Integer> same = new ArrayList<>(List.of(7, 8));
        appendCopy(same, same);
        System.out.println("same: " + same);
        System.out.println("integers unchanged: " + integers);

        List<Number> slots = new ArrayList<>(List.of(-1, -1, -1));
        Collections.copy(slots, integers);
        System.out.println("slots after Collections.copy: " + slots);

        List<Number> tooShort = new ArrayList<>(List.of(-1));
        try {
            Collections.copy(tooShort, integers);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("too short: IndexOutOfBoundsException");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac PecCopyDemo.java
java PecCopyDemo
```

**Stdout chính xác:**

```text
numbers: [1.5, 2, 4]
objects: [begin, 2, 4]
same: [7, 8, 7, 8]
integers unchanged: [2, 4]
slots after Collections.copy: [2, 4, -1]
too short: IndexOutOfBoundsException
```

**Diễn giải các dòng kết quả:**

1. `List<Integer> integers` làm nguồn và `List<Number> numbers` làm đích. `appendCopy` nối `2`, `4` vào sau `1.5`: kết quả `[1.5, 2, 4]`.
2. `List<Object> objects` cũng là đích hợp lệ cho nguồn `List<Integer>`, nên kết quả `[begin, 2, 4]`.
3. `appendCopy(same, same)` chụp hai phần tử nguồn trước khi thêm: `[7, 8]` thành `[7, 8, 7, 8]`; không có lặp vô hạn.
4. `integers` vẫn là `[2, 4]` vì việc sao chép chỉ **đọc** nó, không xóa hay sửa phần tử.
5. `Collections.copy(slots, integers)` khác `appendCopy`: nó thay hai phần tử đầu của đích `[-1, -1, -1]` và để nguyên phần tử còn lại, được `[2, 4, -1]`.
6. `Collections.copy(tooShort, integers)` ném `IndexOutOfBoundsException` vì danh sách đích chỉ có một vị trí, trong khi nguồn có hai phần tử.

Chương trình dùng đúng các import `java.util` và không phụ thuộc framework bên ngoài. `Number` và `Integer` thuộc `java.lang` nên không cần import riêng.

## 6. “Copy” có hai ý nghĩa: nối thêm và ghi đè

Điểm dễ gây sai lệch trong yêu cầu là từ **“sao chép”**. Hai cơ chế đều đọc nguồn và đưa dữ liệu vào đích, nhưng có ngữ nghĩa khác nhau:

| Đặc điểm | `appendCopy(destination, source)` ở trên | `Collections.copy(destination, source)` |
| --- | --- | --- |
| Thao tác lên đích | `add` từng phần tử vào cuối | `set` đè từng vị trí tương ứng |
| Đích ban đầu | Có thể rỗng, miễn cho phép thêm | Phải có ít nhất `source.size()` phần tử |
| Thay đổi kích thước đích | Tăng theo số phần tử nguồn | Giữ nguyên |
| Ví dụ đích `[9, 9, 9]`, nguồn `[1, 2]` | `[9, 9, 9, 1, 2]` | `[1, 2, 9]` |
| Đích mutable thích hợp | List hỗ trợ thêm | List hỗ trợ `set` |
| Khi hai tham số cùng list | Bản chụp tạm giúp append hữu hạn | Không có nhu cầu tăng kích thước |
| Độ phức tạp cơ bản của triển khai mẫu | O(n) thời gian thêm đối với `ArrayList`, O(n) bộ nhớ snapshot | Ghi đè n vị trí, không cần tăng kích thước; chi phí thực tế phụ thuộc implementation |

Chính API chuẩn có chữ ký gần tương tự:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Đây là **chữ ký minh họa** của `java.util.Collections.copy`. Phương thức nhận **destination trước, source sau**. Với `Collections.copy`, số phần tử đang có của đích phải **lớn hơn hoặc bằng** số phần tử nguồn. Gọi `new ArrayList<>(capacity)` chỉ cấp *dung lượng nội bộ*, **không tăng `size()`** của list, vì vậy không đáp ứng điều kiện đó.

Ví dụ sai thường gặp:

```java
List<Number> destination = new ArrayList<>(10);
List<Integer> source = List.of(1, 2);

// Collections.copy(destination, source); // runtime IndexOutOfBoundsException
```

Danh sách `destination` ở đây có `size() == 0` mặc dù capacity ban đầu là 10. Muốn nối thêm hai số, dùng `appendCopy(destination, source)`; muốn ghi đè theo `Collections.copy` thì phải khởi tạo số **phần tử thực** đủ lớn và bảo đảm `set` được hỗ trợ.

Ngược lại, `Arrays.asList(...)` tạo danh sách kích thước cố định nhưng vẫn thường hỗ trợ `set` nên có thể thích hợp với `Collections.copy` nếu đủ phần tử; nó không hỗ trợ `add` làm tăng kích thước, nên `appendCopy` không phù hợp.

## 7. Tại sao không cần ép kiểu hoặc raw type?

Một cách làm nguy hiểm là cố biến nguồn `List<Integer>` thành `List<Number>`, hoặc dùng raw `List` để né kiểm tra kiểu. Ví dụ bên dưới **không nên dùng**:

```java
// Sai hướng; đây là ví dụ về ép kiểu không an toàn:
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(List destination, List source) {
    destination.addAll(source);
}
```

Thao tác raw type có thể làm mất thông tin kiểu, cho phép thêm giá trị không phù hợp vào một danh sách đáng lẽ chỉ chứa một subtype nhất định. Lỗi có thể chỉ xuất hiện ở thời điểm đọc/ép kiểu sau này (`ClassCastException`).

PECS giúp biên dịch viên chứng minh quan hệ hợp lệ mà không cần cast:

- Nguồn: `List<? extends T>` cung cấp một `T`.
- Đích: `List<? super T>` nhận được giá trị `T` ấy.
- Tất cả ràng buộc được kiểm tra tại **compile time**.

Nếu chỉ cần nối thêm dữ liệu và **biết chắc nguồn không bị thay đổi khi đang thao tác** cũng như không trùng đối tượng nguồn/đích, có thể viết ngắn bằng `destination.addAll(source)` trong cùng chữ ký PECS. Bản chụp trong ví dụ chính làm rõ ngữ nghĩa khi tự nối và chi phí sao chép, vì vậy phù hợp cho ví dụ giáo dục.

## 8. Suy luận kiểu `T` trong các trường hợp thực tế

Xét những tổ hợp điển hình:

| Kiểu nguồn | Kiểu đích | `appendCopy(dest, src)` | Giải thích |
| --- | --- | --- | --- |
| `List<Integer>` | `List<Integer>` | Hợp lệ | Cùng kiểu phần tử |
| `List<Integer>` | `List<Number>` | Hợp lệ | Đích chứa được `Integer` |
| `List<Integer>` | `List<Object>` | Hợp lệ | `Object` là siêu kiểu của `Integer` |
| `List<Double>` | `List<Number>` | Hợp lệ | Đích chứa được `Double` |
| `List<Number>` | `List<Object>` | Hợp lệ | `Object` chứa được `Number` |
| `List<Number>` | `List<Integer>` | Không hợp lệ | Nguồn có thể chứa `Double`, đích `Integer` không chứa được |
| `List<Object>` | `List<Number>` | Không hợp lệ | Nguồn có thể chứa kiểu không phải `Number` |
| `List<String>` | `List<Object>` | Hợp lệ | Mọi `String` đều là `Object` |
| `List<Integer>` | `List<String>` | Không hợp lệ | Không có `T` thích hợp đảm bảo an toàn ghi |

Bảng xét **khả năng biên dịch** cho lời gọi. Nó không bảo đảm implementation đích có hỗ trợ `add` tại runtime. Ví dụ `List<Number> numbers = List.of(1, 2)` có kiểu đích phù hợp, nhưng không cho phép thêm phần tử.

Một lỗi suy luận khác là tưởng rằng type argument `T` phải luôn bằng chính xác kiểu của nguồn hoặc đích. Trên thực tế, compiler tìm các ràng buộc thỏa cả phía `extends` và `super`. Không nên yêu cầu caller tự cast hai list về một kiểu chung chỉ để gọi một phương thức có wildcard chuẩn.

## 9. Các rủi ro runtime và giới hạn cần ghi rõ

### 9.1. Đích phải hỗ trợ thao tác thêm

`List<? super T>` chứng minh **kiểu phần tử có thể được nhận**, nhưng không bảo đảm `add` thành công. `List.of(...)`, `List.copyOf(...)` hoặc `Collections.unmodifiableList(...)` từ chối thay đổi; `Arrays.asList(...)` có kích thước cố định.

Do đó, API `appendCopy` phải công bố rằng đích cần là **danh sách thay đổi kích thước được**, chẳng hạn `ArrayList`. Nếu nguồn có `n` phần tử và phép thêm thành công, đích tăng `n` phần tử.

### 9.2. “Copy” ở đây là sao chép tham chiếu phần tử

`new ArrayList<>(source)` và `destination.add(value)` không sao chép sâu trạng thái một đối tượng `T` mutable. Nếu nguồn chứa các đối tượng mutable, nguồn và đích có thể cùng trỏ tới những đối tượng phần tử ấy. Đổi thuộc tính của một đối tượng bên nguồn có thể quan sát được qua phần tử tương ứng ở đích.

Để có **deep copy**, cần quy tắc sao chép từng loại phần tử, ví dụ truyền vào một hàm mapper/copy factory. Không nên gọi `appendCopy` là deep copy.

### 9.3. Không có tính nguyên tử hay đồng bộ tự động

Phiên bản minh họa kiểm tra null trước, tạo bản chụp, rồi lần lượt `add`. Nếu một lời gọi `add` về sau thất bại, các phần tử đã thêm trước đó **có thể vẫn nằm ở đích**. Vì vậy phương thức không hứa “hoặc thành công toàn bộ, hoặc không đổi gì”.

Bản chụp tạm cũng **không tự bảo đảm thread-safety** nếu một luồng khác đồng thời sửa nguồn trong lúc tạo snapshot. Cần cơ chế đồng bộ/quyền sở hữu phù hợp hoặc collection bảo đảm tính nhất quán theo yêu cầu.

### 9.4. `null` và kiểm soát dữ liệu

`Objects.requireNonNull` chỉ cấm **chính hai danh sách tham số** là null. Nếu source chứa một phần tử null, snapshot có thể chứa null và `destination.add(null)` sẽ phụ thuộc vào danh sách đích có chấp nhận null hay không. Muốn không cho dữ liệu null, hãy đặt hợp đồng và kiểm tra riêng.

### 9.5. Bảo toàn thứ tự

Hàm dùng `List` và `for-each`, nên các phần tử được thêm theo thứ tự duyệt của nguồn. Nếu không có luồng khác sửa nguồn trong khi sao chép, thứ tự các phần tử mới trong đích giống thứ tự các phần tử của source lúc tạo snapshot. Đích có thể đã có những phần tử trước đó; hàm không xóa chúng.

## 10. Thiết kế API theo mục đích sử dụng

Nếu cần **nối nguồn vào đích**, đặt tên thể hiện append, chẳng hạn `appendCopy`, `appendFrom` hoặc `appendAll`; dùng chữ ký:

```java
static <T> void appendCopy(
        List<? super T> destination,
        List<? extends T> source)
```

Nếu cần **ghi đè phần đầu danh sách đích**, dùng sẵn:

```java
Collections.copy(destination, source);
```

Khi chỉ cần **tạo list mới độc lập với cấu trúc nguồn**, không nhất thiết phải nhận một danh sách đích:

```java
static <T> List<T> mutableCopy(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

Cách này tạo một `ArrayList<T>` mới, thay vì sửa list của người gọi. Đây cũng là **bản sao nông** đối với các phần tử kiểu tham chiếu. Với đầu vào phù hợp và yêu cầu danh sách không cho sửa, `List.copyOf(source)` là lựa chọn khác, nhưng phương thức ấy không chấp nhận phần tử null và không bảo đảm deep copy.

Nên chọn chữ ký/return type theo mục đích thực tế. Không nhất thiết dùng wildcard nếu API chỉ thao tác với đúng một kiểu cụ thể và không cần nhận các danh sách subtype/supertype khác nhau.

## 11. Những lỗi thường gặp

**Lỗi 1 — Dùng `List<T>` cho cả nguồn và đích.** Việc này quá hạn chế: `List<Integer>` và `List<Number>` không có cùng một đối số kiểu. Nếu chỉ đọc nguồn và chỉ thêm vào đích, `? extends T` và `? super T` cho phép API rộng hơn mà vẫn an toàn.

**Lỗi 2 — Đảo chiều wildcard.** `List<? super T> source` chỉ bảo đảm phần tử đọc ra là `Object`, còn `List<? extends T> destination` không chấp nhận thêm giá trị `T` bất kỳ. Vai trò producer/consumer phải xác định theo hướng dữ liệu.

**Lỗi 3 — Hiểu `Collections.copy` là nối thêm.** Nó ghi đè phần tử theo chỉ số và cần đích có ít nhất bằng số phần tử nguồn. Dung lượng `ArrayList` không đồng nghĩa số phần tử hiện có.

**Lỗi 4 — Duyệt và thêm vào cùng danh sách.** Dùng vòng foreach trực tiếp trên list khi list ấy cũng là đích có thể gây lỗi khi sửa cấu trúc trong lúc duyệt. Tạo snapshot trước khi thêm nếu muốn hỗ trợ tự nối.

**Lỗi 5 — Giả định wildcard biến đích thành mutable.** Generics chứng minh kiểu, không bảo đảm thao tác `add` được implementation hỗ trợ.

**Lỗi 6 — Dùng cast/raw type thay vì wildcard.** Cast có thể che lỗi kiểu đến runtime và làm hỏng ràng buộc phần tử.

**Lỗi 7 — Mong phần tử đích là bản sao độc lập hoàn toàn.** `appendCopy` sao chép tham chiếu, không clone sâu các đối tượng phần tử.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `appendCopy(List<Number>, List<Integer>)` có thể biên dịch dù `List<Integer>` không phải subtype của `List<Number>`?

Vì compiler suy ra `T` phù hợp (chẳng hạn `Integer`) với hai wildcard. Nó lấy một `T` từ `List<? extends T>` rồi thêm chính `T` vào `List<? super T>`.

**Câu 2.** Khi nguồn là `List<Number>` chứa cả `Integer` và `Double`, có thể sao chép sang `List<Integer>` không?

Không; danh sách đích khai báo `Integer` không chứa an toàn mọi phần tử `Number`.

**Câu 3.** `new ArrayList<Number>(100)` có đủ chỗ cho `Collections.copy(dest, source)` với source 3 phần tử không?

Chưa chắc: constructor đó chỉ cấp capacity, `size()` vẫn bằng 0. Cần ít nhất ba phần tử thực đã tồn tại và đích hỗ trợ `set`.

**Câu 4.** Khi gọi `appendCopy(list, list)` với `list = [7, 8]`, phiên bản có snapshot cho kết quả gì?

`[7, 8, 7, 8]`. Snapshot chỉ chụp hai phần tử nguồn trước khi hàm bắt đầu thêm.

**Câu 5.** `List<? super Integer>` đảm bảo đọc phần tử dưới kiểu `Integer` không?

Không. Bởi đích có thể là `List<Number>` hay `List<Object>`, giá trị đọc ra chỉ bảo đảm dưới kiểu `Object`. Trong bài toán này, hàm **không cần đọc từ đích**.

**Câu 6.** Nếu đích là một `List.of(...)`, chữ ký generic có bảo đảm thêm được không?

Không. Compiler có thể chấp nhận quan hệ kiểu, nhưng runtime ném `UnsupportedOperationException` khi cố thay đổi danh sách không hỗ trợ sửa.

## Ghi nhớ

Một hàm sao chép theo PECS có dạng `<T> void copy(List<? super T> destination, List<? extends T> source)`: **nguồn sản xuất `T` nên dùng `extends`, đích tiêu thụ `T` nên dùng `super`**. Trong triển khai cần xác định rõ ngữ nghĩa **nối thêm** hay **ghi đè**; ví dụ `appendCopy` ở bài này nối thêm, chụp nguồn trước để hỗ trợ tự nối, còn `Collections.copy` ghi đè các vị trí sẵn có. Wildcard bảo đảm an toàn kiểu; quyền sửa danh sách, aliasing, deep copy và đồng bộ vẫn là các vấn đề runtime/thiết kế riêng.
