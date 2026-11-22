# `List<Integer>`, `Collection<Integer>` và quan hệ theo khai báo kế thừa

## Mục tiêu

Sau bài này, bạn cần phân biệt được hai ý độc lập: **quan hệ kế thừa giữa các kiểu khai báo** và **quan hệ giữa các đối số kiểu trong generics**. Từ đó, bạn giải thích được vì sao một `List<Integer>` gán được cho `Collection<Integer>`, nhưng không gán được cho `Collection<Number>`, đồng thời biết khi nào nên dùng wildcard.

## 1. Quan hệ kiểu bắt đầu từ khai báo API

Trong `java.util`, các giao diện khai báo quan hệ như sau (rút gọn chỉ để thấy phần kế thừa):

```java
interface Iterable<T> {
    // ...
}

interface Collection<E> extends Iterable<E> {
    // ...
}

interface List<E> extends Collection<E> {
    // ...
}
```

Đây là **sơ đồ khai báo minh họa**, không phải mã nguồn đầy đủ để thay thế các interface của JDK. Với cùng một kiểu tham số `T`, chuỗi quan hệ là:

```text
List<T>  <:  Collection<T>  <:  Iterable<T>
  ^
  |
ArrayList<T> (implements List<T>)
```

Ký hiệu `A <: B` nghĩa là `A` là subtype (kiểu con) của `B`. `ArrayList<E>` triển khai `List<E>`, còn `List<E>` kế thừa `Collection<E>`. Khi thay đồng nhất `E = Integer`, ta nhận được:

- `ArrayList<Integer>` là subtype của `List<Integer>`.
- `List<Integer>` là subtype của `Collection<Integer>`.
- `Collection<Integer>` là subtype của `Iterable<Integer>`.

Vì vậy, **phép gán hướng lên (upcast) hợp lệ**:

```java
List<Integer> list = new ArrayList<>();
Collection<Integer> collection = list;
Iterable<Integer> iterable = collection;
```

Java kiểm tra quan hệ này tại **thời điểm biên dịch** thông qua khai báo `extends`/`implements`. Cùng đối tượng `ArrayList` được tham chiếu qua các kiểu tĩnh khác nhau; không có bản sao danh sách nào được tạo ra khi gán.

Đổi kiểu tham chiếu làm thay đổi **những phương thức có thể gọi qua biến**: `collection.add(1)` và `collection.size()` có trong `Collection`, nhưng `collection.get(0)` không biên dịch vì `get(int)` thuộc `List`. Đối tượng thực tế vẫn là danh sách. Ngược chiều, không thể tự động gán một `Collection<Integer>` cho `List<Integer>`, vì một collection bất kỳ cũng có thể là `Set<Integer>`.

## 2. Ví dụ Java 17+ chạy độc lập

Lưu mã dưới tên **`GenericInheritanceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class GenericInheritanceDemo {
    private static void appendForty(Collection<? super Integer> target) {
        target.add(40);
    }

    public static void main(String[] args) {
        List<Integer> list = new ArrayList<>(List.of(10, 20));

        Collection<Integer> collection = list; // upcast hợp lệ
        Iterable<Integer> iterable = collection;

        collection.add(30); // sửa chính đối tượng mà list đang tham chiếu
        System.out.println(list);
        System.out.println(iterable.iterator().next());

        Collection<? extends Number> readableNumbers = list;
        Number first = readableNumbers.iterator().next();
        System.out.println(first);

        Collection<Number> destination = new ArrayList<>();
        appendForty(destination);
        System.out.println(destination);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac GenericInheritanceDemo.java
java GenericInheritanceDemo
```

Kết quả chính xác:

```text
[10, 20, 30]
10
10
[40]
```

Giải thích: `collection` và `list` cùng trỏ tới một `ArrayList<Integer>` nên thêm `30` qua `collection` cũng hiện ra khi in `list`. Biến `iterable` chỉ bộc lộ API của `Iterable`, nhưng vẫn duyệt chính đối tượng đó. Wildcard `? extends Number` cho phép đọc phần tử dưới kiểu `Number`; wildcard `? super Integer` cho phép hàm thêm `Integer` vào collection có kiểu phần tử là `Integer` hoặc một siêu kiểu của nó.

**Lưu ý về mutability:** ví dụ dùng `new ArrayList<>(List.of(...))` để tạo danh sách thay đổi được. Nếu tham chiếu trỏ trực tiếp đến `List.of(10, 20)`, lời gọi `add` sẽ ném `UnsupportedOperationException`, dù phép gán `List<Integer> → Collection<Integer>` vẫn hoàn toàn hợp lệ. Quan hệ subtype không bảo đảm khả năng sửa dữ liệu.

## 3. Generics bất biến: thay đối số kiểu không tạo quan hệ kế thừa mới

`Integer` kế thừa `Number`, nhưng **`List<Integer>` không phải subtype của `List<Number>`** và **`Collection<Integer>` không phải subtype của `Collection<Number>`**. Đây là tính **invariance** (bất biến) của kiểu generic Java.

Những dòng sau cố ý minh họa **lỗi biên dịch**; không thêm chúng vào chương trình chạy ở trên:

```java
List<Integer> integers = new ArrayList<>();

// Không biên dịch:
Collection<Number> wrong1 = integers;
List<Number> wrong2 = integers;
Collection<Object> wrong3 = integers;
```

Tại sao phải cấm? Giả sử `Collection<Number> wrong1 = integers` được chấp nhận, lệnh `wrong1.add(3.14)` sẽ hợp lệ theo kiểu tĩnh `Collection<Number>`, nhưng lại đưa `Double` vào một `List<Integer>`. Java ngăn nguy cơ đó ngay tại thời điểm biên dịch.

Hãy tách rõ hai phép suy luận:

1. **Thay kiểu khai báo dọc theo chuỗi kế thừa, giữ nguyên đối số kiểu:** `List<Integer> → Collection<Integer>`: hợp lệ.
2. **Thay đối số kiểu `Integer` thành `Number` trong kiểu generic cụ thể:** `Collection<Integer> → Collection<Number>`: không hợp lệ.

Việc `Integer <: Number` **không** tự động kéo theo `G<Integer> <: G<Number>` với `G` là `List`, `Collection` hay lớp generic bất biến khác.

## 4. Wildcard biểu đạt quan hệ kiểu rộng hơn

Khi phương thức chỉ cần đọc các phần tử như `Number` hoặc chỉ cần nhận các giá trị `Integer`, bạn có thể khai báo wildcard thay vì đòi một `Collection<Number>` cố định.

### `? extends Number`: nguồn đọc

```java
static void printFirst(Collection<? extends Number> values) {
    Number first = values.iterator().next();
    System.out.println(first);
}
```

Phương thức này nhận được `List<Integer>`, `List<Double>`, `Collection<Number>` và các collection có kiểu phần tử là subtype của `Number`. Có thể đọc phần tử ra kiểu `Number`. Tuy nhiên, không thể gọi `values.add(42)` vì compiler không biết kiểu phần tử thực là `Integer`, `Double` hay subtype nào khác. Đừng hiểu `Collection<? extends Number>` là `Collection<Number>`: chúng mang các ràng buộc khác nhau.

### `? super Integer`: đích ghi

```java
static void addAnswer(Collection<? super Integer> values) {
    values.add(42);
}
```

Phương thức nhận được `Collection<Integer>`, `Collection<Number>` và `Collection<Object>`, bởi tất cả đều có khả năng chứa một `Integer`. Ngược lại, khi lấy phần tử từ `Collection<? super Integer>`, compiler chỉ có thể đảm bảo kiểu `Object`, do kiểu phần tử thực có thể là `Integer`, `Number` hoặc `Object`.

Gợi nhớ quy tắc **PECS** (*Producer Extends, Consumer Super*): nơi cung cấp dữ liệu để đọc thường dùng `? extends`; nơi nhận dữ liệu để ghi thường dùng `? super`. Nếu cần đọc và ghi chính xác `Integer`, dùng `Collection<Integer>`.

Cần phân biệt thêm: `Collection<? extends Number>` có thể **tham chiếu** một `List<Integer>`, nhưng điều đó không làm biến `Collection<Number>` nhận được `List<Integer>`. Wildcard là kiểu đích khác, mang giới hạn thao tác khác.

## 5. Bảng kiểm tra phép gán

| Nguồn (biểu thức) | Kiểu biến đích | Kết quả | Lý do |
| --- | --- | --- | --- |
| `ArrayList<Integer>` | `List<Integer>` | Hợp lệ | `ArrayList<E> implements List<E>` |
| `List<Integer>` | `Collection<Integer>` | Hợp lệ | `List<E> extends Collection<E>` |
| `Collection<Integer>` | `Iterable<Integer>` | Hợp lệ | `Collection<E> extends Iterable<E>` |
| `Collection<Integer>` | `List<Integer>` | Không tự động | Collection có thể là Set |
| `List<Integer>` | `Collection<Number>` | Không hợp lệ | Đối số generic bất biến |
| `List<Integer>` | `List<Number>` | Không hợp lệ | Đối số generic bất biến |
| `List<Integer>` | `Collection<? extends Number>` | Hợp lệ | Phần tử đọc được dưới kiểu Number |
| `List<Integer>` | `Collection<? super Integer>` | Hợp lệ | Có thể thêm Integer |
| `List<Number>` | `Collection<? super Integer>` | Hợp lệ | Number là supertype của Integer |

Các hàng mô tả **kiểm tra kiểu khi gán**, không bảo đảm rằng mọi đối tượng nhận được đều hỗ trợ thao tác sửa đổi. Việc `add` chạy thành công còn phụ thuộc implementation cụ thể.

## 6. Chọn kiểu tham số phương thức theo nhu cầu

Một hàm chỉ cần duyệt, đếm hoặc kiểm tra thành viên không nên đòi `List<Integer>` khi `Collection<Integer>` đã đủ; nhờ vậy hàm có thể chấp nhận cả `ArrayList` và `HashSet` chứa `Integer`:

```java
static boolean containsForty(Collection<Integer> values) {
    return values.contains(40);
}
```

Nếu hàm chỉ đọc các số không phụ thuộc chính xác kiểu số, mở rộng chữ ký sang `Collection<? extends Number>`. Nếu cần dùng chỉ mục hoặc giữ thứ tự truy cập bằng `get(index)`, `List<Integer>` mới phản ánh đúng yêu cầu API. Nếu hàm chỉ cần phép lặp, `Iterable<Integer>` còn tổng quát hơn.

Ví dụ khác biệt giữa hướng lên và hướng xuống (các dòng lỗi được chú thích):

```java
List<Integer> list = new ArrayList<>(List.of(1, 2));
Collection<Integer> view = list; // hợp lệ
// List<Integer> notGuaranteed = view; // không biên dịch

// Chỉ ép kiểu hướng xuống khi biết đối tượng thực sự là List:
if (view instanceof List<?>) {
    List<Integer> restored = (List<Integer>) view;
    System.out.println(restored.get(0)); // 1
}
```

Ở ví dụ cuối, chính `list` khởi tạo `view` nên đối tượng thực sự là một `List`. Đừng ép kiểu một `Collection` bất kỳ sang `List`; với `HashSet`, ép kiểu như vậy sẽ thất bại tại runtime. Không nên dùng cast để né tính bất biến của các đối số generic.

## 7. Những nhầm lẫn thường gặp

- **“`Integer extends Number`, vậy `Collection<Integer> extends Collection<Number>`.”** Sai: quan hệ kế thừa của đối số kiểu không được tự động truyền vào generic bất biến.
- **“`List<Integer>` và `Collection<Integer>` là hai collection khác nhau sau phép gán.”** Sai: upcast chỉ thay kiểu tĩnh của tham chiếu; hai biến có thể cùng trỏ một đối tượng.
- **“`Collection<Integer>` dùng được mọi phương thức của `List<Integer>`.”** Sai: gọi phương thức phụ thuộc kiểu tham chiếu tại compile time; `Collection` không có `get(index)`.
- **“Gán được `List<Integer>` cho `Collection<Integer>` nên chắc chắn thêm được phần tử.”** Sai: các implementation không sửa được vẫn có thể ném `UnsupportedOperationException`.
- **“Cứ dùng `Collection<Number>` để nhận mọi list số.”** Sai: dùng `Collection<? extends Number>` nếu đọc nhiều kiểu số, hoặc `Collection<? super Integer>` nếu cần thêm `Integer`.

## Kết luận cần ghi nhớ

Quan hệ **`List<E> extends Collection<E>`** cho phép `List<Integer> → Collection<Integer>` vì **giữ nguyên `E = Integer`** trên tuyến kế thừa. Tính **bất biến** lại ngăn `List<Integer> → Collection<Number>` dù `Integer extends Number`. Khi API cần nhận các kiểu phần tử khác nhau, wildcard `? extends` hoặc `? super` diễn đạt chính xác khả năng đọc/ghi và giúp trình biên dịch bảo toàn an toàn kiểu.
