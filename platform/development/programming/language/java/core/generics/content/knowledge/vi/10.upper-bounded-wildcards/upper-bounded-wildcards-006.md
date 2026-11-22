# Wildcard `extends` không biến đối tượng nguồn thành bất biến

## Mục tiêu

`List<? extends Number>` thường xuất hiện trong các API **đọc dữ liệu số**, vì nó có thể nhận danh sách các kiểu phần tử như `Integer`, `Double` hoặc `Number`. Dù không thể thêm một giá trị `Number` bất kỳ thông qua tham chiếu đó, danh sách thực tế **vẫn có thể thay đổi**.

Sau bài này, bạn cần giải thích được bốn vấn đề:

1. `? extends Number` ràng buộc kiểu phần tử ở compile time như thế nào?
2. Vì sao sửa danh sách qua một tham chiếu nguồn vẫn làm thay đổi nội dung nhìn qua `List<? extends Number>`?
3. Vì sao `remove` và `clear` có thể gọi được qua wildcard nhưng đôi khi ném `UnsupportedOperationException`?
4. Làm thế nào để phân biệt wildcard, unmodifiable view và immutable snapshot khi thiết kế API?

## 1. Giới hạn của `extends` thuộc về hệ kiểu

Đầu tiên, xem đoạn mã trong một phương thức Java đã import `java.util.List` và `java.util.ArrayList`:

```java
List<Integer> source = new ArrayList<>(List.of(10, 20));
List<? extends Number> view = source;

Number value = view.get(0); // hợp lệ

// view.add(42);             // lỗi biên dịch
// view.add(3.14);           // lỗi biên dịch
// view.set(0, 42);          // lỗi biên dịch
```

Vì `Integer` kế thừa `Number`, `List<Integer>` có thể được **tham chiếu qua** `List<? extends Number>`. Điều này không có nghĩa `List<Integer>` là subtype của `List<Number>`: generics Java bất biến (*invariant*) đối với các đối số kiểu cụ thể.

`? extends Number` nghĩa là kiểu phần tử có một kiểu thực chưa biết và **có upper bound là `Number`**. Trình biên dịch cho phép đọc phần tử ra `Number` vì mọi phần tử hợp lệ của danh sách đều là một `Number`. Nhưng nó không thể cho phép thêm `42` hay `3.14`: nếu danh sách thực tế là `List<Double>` thì `42` không phải `Double`, còn nếu là `List<Integer>` thì `3.14` không phải `Integer`.

Các dòng lỗi đã được chú thích, nên đoạn code trên mang tính minh họa, không phải một chương trình Java độc lập.

Điểm rất quan trọng: **wildcard chỉ thay đổi những thao tác được chấp nhận khi biên dịch trên biến `view`.** Nó không sửa implementation, không tạo bản sao, không đóng băng đối tượng và không tự áp đặt cơ chế đồng bộ.

## 2. Nguồn và wildcard view có thể cùng trỏ tới một đối tượng

Với hai câu lệnh:

```java
List<Integer> source = new ArrayList<>(List.of(10, 20));
List<? extends Number> view = source;
```

mô hình tham chiếu là:

```text
source: List<Integer> ------------+
                                  |
                                  v
                         ArrayList<Integer>
                              [10, 20]
                                  ^
                                  |
view: List<? extends Number> -----+
```

Phép gán `view = source` **không sao chép phần tử**. Nó tạo thêm một biến trỏ đến chính đối tượng `ArrayList<Integer>` đang được `source` giữ.

Nếu sửa qua `source`:

```java
source.add(30);
source.set(0, 99);
System.out.println(view); // [99, 20, 30]
```

thì `view` thấy ngay kết quả khi đọc. Compiler cho phép `source.add(30)` và `source.set(0, 99)` vì biến nguồn có kiểu `List<Integer>` và các giá trị mới đều là `Integer`. Việc `view.add(30)` bị chặn không hề thay đổi quyền sửa danh sách của `source`.

Suy ra: **không thêm được thông qua một tham chiếu không đồng nghĩa không có tham chiếu nào thêm được**.

Một đối tượng còn có thể được truyền qua phương thức, lưu trong field, được nhận bằng constructor hoặc được chia sẻ cho nhiều thành phần. Nếu các tham chiếu khác có quyền sửa và implementation hỗ trợ sửa, dữ liệu nhìn qua `List<? extends Number>` vẫn biến động.

## 3. Ví dụ Java 17+ biên dịch và chạy độc lập

Tạo tệp tên **`ExtendsNotImmutableDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ExtendsNotImmutableDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(List.of(10, 20));
        List<? extends Number> view = source;

        System.out.println("Initially: " + view);

        source.add(30);
        source.set(0, 99);
        System.out.println("After source changes: " + view);

        Number first = view.get(0);
        System.out.println("First as Number: " + first);

        boolean removed = view.remove(Integer.valueOf(20));
        System.out.println("Removed through wildcard: " + removed);
        System.out.println("Source after removal: " + source);

        view.clear();
        System.out.println("Source after clear: " + source);

        List<Integer> backing = new ArrayList<>(List.of(1, 2));
        List<? extends Number> unmodifiable =
                Collections.unmodifiableList(backing);

        try {
            unmodifiable.clear();
        } catch (UnsupportedOperationException e) {
            System.out.println("Wrapper rejects clear");
        }

        backing.add(3);
        System.out.println("Wrapper reflects source: " + unmodifiable);

        List<? extends Number> snapshot = List.copyOf(backing);
        backing.add(4);
        System.out.println("Snapshot: " + snapshot);
        System.out.println("Backing: " + backing);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ExtendsNotImmutableDemo.java
java ExtendsNotImmutableDemo
```

**Stdout:**

```text
Initially: [10, 20]
After source changes: [99, 20, 30]
First as Number: 99
Removed through wildcard: true
Source after removal: [99, 30]
Source after clear: []
Wrapper rejects clear
Wrapper reflects source: [1, 2, 3]
Snapshot: [1, 2, 3]
Backing: [1, 2, 3, 4]
```

**Vì sao chương trình cho kết quả trên?**

- `source` và `view` cùng trỏ tới `ArrayList<Integer>`; do đó `add(30)` và `set(0, 99)` qua `source` làm thay đổi dữ liệu nhìn qua `view`.
- `view.get(0)` đọc được phần tử kiểu `Number` nên biến `first` nhận giá trị `99`.
- `view.remove(Integer.valueOf(20))` hợp lệ vì overload `remove(Object)` chỉ cần một đối tượng để tìm/xóa. `ArrayList` hỗ trợ xóa nên trả về `true`.
- `view.clear()` không nhận phần tử mới, vì vậy nó được phép về mặt kiểu và hoạt động trên `ArrayList`. Do cùng một đối tượng, `source` trở thành `[]`.
- `Collections.unmodifiableList(backing)` tạo wrapper từ chối sửa qua wrapper, nhưng `backing.add(3)` vẫn được phép; kết quả hiển thị qua wrapper trở thành `[1, 2, 3]`.
- `List.copyOf(backing)` tạo snapshot cấu trúc không sửa được từ `backing` đang mutable. Khi thêm `4` vào `backing`, snapshot vẫn chứa `[1, 2, 3]`.

Điểm chung của `view`, `unmodifiable` và `snapshot` là **chúng đều có kiểu `List<? extends Number>`**. Nhưng hành vi khác nhau hoàn toàn tùy đối tượng nền. Đây là bằng chứng trực tiếp rằng wildcard **không phải công cụ bảo đảm tính bất biến**.

## 4. Vì sao vẫn có thể `remove` hoặc `clear` qua `? extends`?

Để hiểu, xem chữ ký rút gọn liên quan của `List<E>` và `Collection<E>`. Đây là **hình dạng API minh họa**, không phải mã source đầy đủ của JDK:

```java
E get(int index);
boolean add(E element);
E set(int index, E element);

boolean remove(Object value);
E remove(int index);
void clear();
```

Dấu wildcard ở `List<? extends Number>` khiến compiler **không biết chính xác `E`**. Những phương thức đưa một giá trị `E` mới vào collection vì thế bị giới hạn:

- `add(E)` phải biết rằng giá trị cần thêm có đúng kiểu `E`.
- `set(int, E)` phải biết rằng giá trị thay thế có đúng kiểu `E`.

Trong khi đó, các phương thức xóa không tạo giá trị phần tử mới:

- `clear()` không nhận tham số kiểu `E`.
- `remove(Object)` nhận `Object` để đối chiếu với phần tử đang có.
- `remove(int)` nhận chỉ số nguyên và trả lại một phần tử kiểu `E`; phần tử trả về có thể được dùng dưới kiểu `Number`.

Ví dụ, hai phương thức dưới đây có thể biên dịch khi đặt trong một lớp đã import `java.util.List`:

```java
static Number takeFirst(List<? extends Number> numbers) {
    return numbers.remove(0);
}

static void empty(List<? extends Number> numbers) {
    numbers.clear();
}
```

Cả hai không hề thêm một `Integer` hay `Double` mới. `takeFirst` yêu cầu phần tử tại chỉ số `0`; nếu danh sách rỗng, `remove(0)` ném `IndexOutOfBoundsException`. Với implementation không hỗ trợ xóa, thao tác có thể ném `UnsupportedOperationException`.

**Đừng nhầm hai overload của `remove`:**

```java
List<Integer> source = new ArrayList<>(List.of(10, 20, 30));
List<? extends Number> view = source;

view.remove(1);                    // xóa tại index 1 (giá trị 20)
view.remove(Integer.valueOf(30));  // xóa giá trị 30
System.out.println(source);       // [10]
```

Lời gọi `remove(1)` chọn `remove(int)`; lời gọi `remove(Integer.valueOf(30))` chọn `remove(Object)`. Đây cũng là đoạn minh họa trong phương thức, cần import `java.util.List` và `java.util.ArrayList`.

## 5. Một số danh sách cho sửa, một số từ chối: phải xem implementation

| Đối tượng được tham chiếu qua `List<? extends Number>` | Gọi `add(Number)` qua wildcard | Gọi `clear()` qua wildcard | Trạng thái thực tế |
| --- | --- | --- | --- |
| `new ArrayList<Integer>()` | Compiler chặn | Biên dịch được và chạy được | Danh sách mutable, alias nguồn có thể thêm/thay/xóa |
| `new LinkedList<Double>()` | Compiler chặn | Biên dịch được và chạy được | Danh sách mutable, alias nguồn có thể thêm/thay/xóa |
| `Arrays.asList(1, 2)` | Compiler chặn | Biên dịch được, nhưng xóa kích thước không được hỗ trợ | Danh sách kích thước cố định; có thể `set` qua tham chiếu có kiểu phù hợp |
| `List.of(1, 2)` | Compiler chặn | Biên dịch được, runtime từ chối | Danh sách không cho sửa |
| `Collections.unmodifiableList(source)` | Compiler chặn | Biên dịch được, runtime từ chối | Wrapper chặn thay đổi qua nó; nguồn có thể vẫn mutable |
| `List.copyOf(source)` | Compiler chặn | Biên dịch được, runtime từ chối | Danh sách không cho sửa, tách khỏi các lần sửa cấu trúc nguồn mutable về sau |

Ở cột `add(Number)`, “compiler chặn” nói về việc thêm một **biểu thức non-null kiểu `Number`** qua `List<? extends Number>`. Bảng cũng không ngụ ý mọi lời gọi `clear()` trên mọi implementation đều thực hiện thành công: Java Collections có các thao tác sửa đổi tùy chọn (*optional operations*), nên runtime có thể ném `UnsupportedOperationException`.

`Arrays.asList` tạo **danh sách kích thước cố định**, không tương đương immutable hoàn toàn. Thay thế giá trị ở một chỉ số đã có bằng `set` có thể thành công qua tham chiếu đúng kiểu. `List.of` lại không cho thay thế, thêm hoặc xóa phần tử.

Với `Collections.unmodifiableList(source)`, wrapper không cho phép sửa **qua nó**, nhưng nội dung wrapper có thể thay đổi nếu bên khác vẫn giữ `source` và sửa danh sách gốc. Đây là view không cho sửa, khác với snapshot độc lập.

## 6. `List<?>`, `List<? extends Number>` và `List<Number>` khác nhau

Những kiểu tham chiếu này khác **quyền đọc/ghi theo kiểu**, không tự quyết định mutability:

- `List<?>`: phần tử chưa biết kiểu, đọc an toàn dưới `Object`.
- `List<? extends Number>`: phần tử có upper bound `Number`, đọc dưới `Number`.
- `List<Number>`: element type khai báo chính xác `Number`; thêm `Integer` hay `Double` hợp kiểu nếu list cho sửa.

```java
List<Integer> original = new ArrayList<>(List.of(1, 2));
List<?> any = original;
List<? extends Number> numbers = original;
Object a = any.get(0);
Number b = numbers.get(0);
// List<Number> invalid = original; // Invariance.
```

Cả `any` và `numbers` trỏ tới **cùng list**. Alias gốc vẫn có thể sửa; wildcard không tạo bản sao hoặc khóa object. Những ngoại lệ liên quan `add(null)` cần phân biệt type checking với chính sách runtime null, được giải thích riêng ở bài chuyên đề.

## 7. Dùng `? extends` đúng mục đích trong API

Giả sử một hàm chỉ cần tính tổng:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number n : values) {
        total += n.doubleValue();
    }
    return total;
}
```

Đây là đoạn phương thức minh họa. Chữ ký này nhận `List<Integer>`, `List<Double>` và các danh sách mang subtype khác của `Number` mà không buộc người gọi chuyển tất cả thành `List<Number>`.

**Producer Extends** trong quy tắc PECS có nghĩa `? extends T` thuận tiện khi API cần **nhận và đọc dữ liệu kiểu `T`**. Quy tắc này không tuyên bố API là read-only theo nghĩa bất biến; các thao tác xóa vẫn có thể khả dụng.

Nếu phương thức chỉ cần duyệt, dùng `Iterable<? extends Number>` còn biểu đạt phạm vi API hẹp hơn; nó không trực tiếp cung cấp `clear()`. Tuy nhiên, giới hạn những phương thức nhìn thấy qua tham chiếu vẫn không khóa đối tượng nền. Một iterator thậm chí có thể có thao tác `remove()` tùy chọn.

Nếu bạn thực sự cần **thêm `Integer`**, kiểu `List<Integer>` hoặc `List<? super Integer>` thường thích hợp hơn:

```java
static void appendInteger(List<? super Integer> destination) {
    destination.add(42);
}
```

`? super Integer` chấp nhận danh sách có kiểu phần tử là `Integer` hoặc siêu kiểu của `Integer` và cho phép thêm `Integer` an toàn. Nó không có nghĩa danh sách thực tế chắc chắn hỗ trợ thêm (ví dụ, một unmodifiable list vẫn có thể từ chối khi chạy).

## 8. Muốn bảo vệ dữ liệu, dùng cơ chế bảo vệ dữ liệu

### Chặn sửa qua kết quả trả về

```java
static List<? extends Number> exposeView(List<Integer> source) {
    return java.util.Collections.unmodifiableList(source);
}
```

Người nhận kết quả không thể sửa qua wrapper. Nhưng bên giữ `source` vẫn có thể sửa; mọi thay đổi từ nguồn có thể xuất hiện khi người nhận đọc wrapper lần sau. Vì thế, wrapper thích hợp cho **chính sách chỉ đọc qua đường truy cập** chứ không tự tạo ảnh chụp dữ liệu.

### Tạo snapshot về cấu trúc danh sách

```java
static List<? extends Number> exposeSnapshot(List<Integer> source) {
    return List.copyOf(source);
}
```

Với `source` là một mutable list, `List.copyOf(source)` tạo danh sách không cho sửa chứa các phần tử hiện tại. Sau này thay đổi kích thước hoặc thay phần tử trong `source` không ảnh hưởng tới cấu trúc snapshot. `List.copyOf` không cho phần tử `null`; nếu đầu vào là danh sách không cho sửa thích hợp, JDK có thể tái sử dụng instance.

**Lưu ý về sao chép nông:** `List.copyOf` không clone sâu từng phần tử. Nếu danh sách chứa đối tượng mutable và có một tham chiếu bên ngoài sửa trạng thái đối tượng đó, sự thay đổi thuộc tính vẫn có thể được quan sát qua snapshot. Muốn snapshot bất biến hoàn toàn cho cả đồ thị đối tượng, phải dùng đối tượng phần tử immutable hoặc sao chép trạng thái phù hợp.

### Thiết kế quyền sở hữu dữ liệu

Đôi khi bạn không cần wrapper nếu API chỉ bộc lộ kết quả tính toán hoặc một cấu trúc đọc đã cố định, nhưng điều đó là quyết định thiết kế dựa trên **quyền sở hữu và giới hạn tham chiếu**. Bản thân wildcard không kiểm soát alias hay lifetime.

Đồng thời, `? extends` không thêm thread-safety. Nếu một luồng thay đổi `ArrayList` khi luồng khác đang duyệt, bạn phải tự thiết kế đồng bộ hoặc chọn collection thích hợp; wildcard không bảo đảm snapshot nhất quán hay ngăn `ConcurrentModificationException`.

## 9. Các sai lầm phổ biến

**“Biến `List<? extends Number>` không gọi được `add(42)` nên đối tượng của nó đã immutable.”** Sai. Điều bị chặn là phép thêm giá trị đó **qua biến với kiểu wildcard**. Một tham chiếu `List<Integer>` khác có thể sửa cùng đối tượng.

**“`? extends Number` đồng nghĩa `List<Number>`.”** Sai. Một danh sách `Integer` có thể được nhìn dưới `List<? extends Number>` nhưng không tự biến thành `List<Number>`; chèn `Double` vào `List<Integer>` là không an toàn kiểu.

**“`? extends` không thể gọi bất kỳ phương thức sửa nào.”** Sai. `remove(Object)`, `remove(int)`, `clear()` không chèn một phần tử `E` tùy ý; vì vậy compiler cho phép gọi và implementation mutable có thể thực hiện thành công.

**“Dùng `Collections.unmodifiableList` sẽ không thấy nguồn đổi nữa.”** Sai. Wrapper theo dõi danh sách nguồn. Để giữ snapshot cấu trúc độc lập với nguồn mutable, hãy tạo bản sao không cho sửa thích hợp.

**“`List.copyOf` biến mọi phần tử thành immutable.”** Sai. Danh sách được sao chép về cấu trúc và giữ tham chiếu tới phần tử; đối tượng phần tử mutable vẫn có thể thay đổi trạng thái từ nơi khác.

**“Wildcard làm dữ liệu an toàn khi nhiều luồng cùng truy cập.”** Sai. Generics xử lý kiểu, không xử lý đồng bộ.

## 10. Tự kiểm tra

**Câu 1.** Với `List<Integer> a = new ArrayList<>(); List<? extends Number> b = a;`, vì sao `a.add(42)` chạy được nhưng `b.add(42)` không biên dịch?

Vì compiler biết chính xác kiểu phần tử của `a` là `Integer`, còn của `b` là một subtype chưa biết của `Number`. Cả hai vẫn trỏ đến cùng một đối tượng.

**Câu 2.** Sau khi `a.add(42)`, `b.size()` có đổi không?

Có, vì danh sách nền chính là đối tượng mà `a` vừa sửa. Phép gán `b = a` không tạo bản sao.

**Câu 3.** `b.clear()` có biên dịch không? Có luôn chạy thành công không?

Biên dịch được. Nó chạy thành công nếu đối tượng nền hỗ trợ `clear`; ví dụ `ArrayList` hỗ trợ, còn `List.of` và unmodifiable wrapper từ chối.

**Câu 4.** `Collections.unmodifiableList(a)` và `List.copyOf(a)` khác nhau ở điểm nào?

Wrapper chặn sửa qua chính nó nhưng có thể thấy các lần sửa `a`; với `a` mutable, `List.copyOf(a)` tạo danh sách không cho sửa lưu cấu trúc phần tử ở thời điểm tạo, không phản ánh lần thêm/xóa sau đó trên `a`.

**Câu 5.** Vì sao `List<? extends Number>` vẫn hữu ích nếu nó không bảo đảm bất biến?

Vì nó cho phép API đọc nhiều loại `List` có phần tử là subtype của `Number`, đồng thời ngăn mã dùng tham chiếu đó thêm nhầm một kiểu phần tử không tương thích. Đó là **an toàn kiểu**, một mục tiêu khác với **bất biến dữ liệu**.

## Kết luận

`? extends Number` diễn đạt “tôi có thể đọc những phần tử thuộc một subtype chưa biết của `Number`”. Nó **không tạo ra một đối tượng bất biến**: tham chiếu nguồn có kiểu cụ thể vẫn sửa được nếu implementation cho phép, và các thao tác xóa không cần chèn phần tử mới cũng có thể gọi được qua wildcard. Muốn bảo vệ trạng thái, phải chọn hợp đồng object phù hợp, wrapper hoặc snapshot, đồng thời quản lý các alias và các đối tượng phần tử mutable.
