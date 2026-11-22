# Hoán đổi phần tử của `List<?>` bằng phương thức hỗ trợ

## Mục tiêu

Một `List<?>` có thể là `List<String>`, `List<Integer>` hoặc danh sách của một kiểu phần tử bất kỳ mà mã đang gọi không biết chính xác. Bạn vẫn có thể **đọc** phần tử dưới kiểu `Object`, nhưng thử đọc một phần tử rồi đưa lại vào `list.set(...)` ngay trong phương thức nhận `List<?>` có thể bị trình biên dịch từ chối. Đây là một tình huống tiêu biểu của **wildcard capture** (bắt giữ wildcard).

Sau bài học, bạn sẽ:

1. Giải thích được vì sao `List<?>` không tương đương `List<Object>` và tại sao việc hoán đổi trực tiếp gặp lỗi biên dịch.
2. Viết được phương thức hỗ trợ generic `<T> void swapCaptured(List<T>, int, int)` để compiler giữ mối liên hệ giữa phần tử lấy ra và phần tử ghi lại.
3. Dùng phương thức công khai `swap(List<?>, int, int)` mà không cần cast hay raw type.
4. Biết khi nào nên dùng API chuẩn `Collections.swap(List<?>, int, int)`.
5. Phân biệt **đúng kiểu khi biên dịch** với **cho phép thay phần tử tại runtime** và xử lý các trường hợp chỉ số, danh sách không sửa được.

## 1. Vấn đề: `get` đọc được nhưng `set` lại bị chặn

Xem đoạn mã sau. Đây là **ví dụ cố ý chứa lỗi biên dịch**, không phải chương trình để chạy:

```java
import java.util.List;

class BrokenSwap {
    static void swap(List<?> list, int i, int j) {
        Object saved = list.get(i);
        list.set(i, list.get(j)); // lỗi kiểu
        list.set(j, saved);       // lỗi kiểu
    }
}
```

`list.get(i)` gọi được vì một phần tử của kiểu tham chiếu bất kỳ đều có thể được quan sát dưới kiểu `Object`. Tuy nhiên, `list.set(i, element)` cần một **đối số tương thích với kiểu phần tử chính xác `E`** của chính danh sách.

`List<?>` có nghĩa kiểu phần tử là **một kiểu chưa biết**, không phải “chứa thoải mái mọi `Object`”. Giả sử danh sách thực tế là `List<Integer>`: nếu compiler cho phép truyền mọi `Object` vào `set`, ta có thể thay một số nguyên bằng `String` và phá vỡ hợp đồng kiểu của nguồn.

Bạn có thể nghĩ `list.get(j)` và `list.set(i, ...)` đều nói tới cùng list, nên phần tử vừa lấy ra đương nhiên đúng kiểu. Ý tưởng về mặt thuật toán là đúng; nhưng ở biểu thức trực tiếp, compiler không chứng minh được mối liên hệ kiểu cần thiết giữa các lần sử dụng wildcard ấy. Thông báo lỗi của `javac` thường có dạng “`Object cannot be converted to CAP#1`” hoặc nhắc tới các kiểu `capture of ?`.

Không nên sửa vấn đề bằng cách khai báo `Object saved` rồi ép kiểu, bởi `Object` đã làm mất thông tin “giá trị này đến từ đúng kiểu phần tử của danh sách”.

## 2. Wildcard capture: đặt tên cho kiểu chưa biết bằng `T`

Giải pháp là chuyển phần thao tác đọc–ghi vào một **generic helper method**:

```java
static void swap(List<?> list, int i, int j) {
    swapCaptured(list, i, j);
}

private static <T> void swapCaptured(List<T> list, int i, int j) {
    T saved = list.get(i);
    list.set(i, list.get(j));
    list.set(j, saved);
}
```

Đây là đoạn minh họa chữ ký và thân phương thức; ví dụ chạy độc lập bên dưới bổ sung kiểm tra chỉ số và xử lý `i == j`.

Cơ chế diễn ra ở **compile time**:

1. Khi gọi `swapCaptured(list, i, j)`, compiler **bắt giữ** dấu `?` của đối số `List<?>` như một kiểu nội bộ chưa biết, thường được mô tả là `CAP#1`.
2. Compiler suy luận `T` trong một lần gọi helper chính là kiểu bắt giữ ấy. Vì vậy trong toàn bộ thân `swapCaptured`, `list` có kiểu nhất quán `List<T>`.
3. `list.get(i)` trả ra `T`, nên `T saved = ...` hợp lệ.
4. `list.set(i, list.get(j))` nhận đúng một `T` từ **cùng danh sách**; `list.set(j, saved)` cũng nhận đúng `T`.
5. Caller chỉ thấy `List<?>` và có thể gọi `swap` với nhiều loại danh sách mà không cần biết `T` là gì.

**Lưu ý:** helper **không tìm ra hoặc kiểm tra kiểu phần tử thật tại runtime**. Nó giúp compiler chứng minh sự thống nhất kiểu tại một vị trí cụ thể. Do generic type erasure, Java cũng không sinh một phiên bản máy riêng của helper cho từng kiểu `T`.

### Sơ đồ quan hệ trong một lần gọi

```text
Caller:
    List<?> values        -- wildcard chưa biết --
             |
             | swapCaptured(values, i, j)
             v
Generic helper:
    List<T> list           -- T = capture của ? --
             |
     T first = get(i)      -- đọc T --
             |
     set(i, get(j))        -- ghi T vào List<T> --
     set(j, first)         -- ghi T vào List<T> --
```

Tất cả thao tác vẫn thực hiện trên **chính đối tượng list của caller**. Không hề sao chép danh sách hay biến list thành `List<Object>`.

## 3. Cài đặt hoàn chỉnh trên Java 17+

Phiên bản thực tế nên kiểm tra đối tượng và chỉ số trước khi đụng tới dữ liệu, đồng thời coi việc đổi một vị trí với chính nó là thao tác không cần thay phần tử.

Tạo tệp tên **`WildcardSwapDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class WildcardSwapDemo {
    public static void swap(List<?> values, int i, int j) {
        Objects.requireNonNull(values, "values");
        Objects.checkIndex(i, values.size());
        Objects.checkIndex(j, values.size());
        swapCaptured(values, i, j);
    }

    private static <T> void swapCaptured(List<T> values, int i, int j) {
        if (i == j) {
            return;
        }
        T saved = values.get(i);
        values.set(i, values.get(j));
        values.set(j, saved);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));
        List<?> unknown = names;
        swap(unknown, 0, 2);
        System.out.println("names: " + names);

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        swap(numbers, 0, 1);
        System.out.println("numbers: " + numbers);

        Collections.swap(unknown, 0, 1);
        System.out.println("Collections.swap: " + names);

        List<String> fixed = Arrays.asList("red", "blue");
        swap(fixed, 0, 1);
        System.out.println("fixed-size: " + fixed);

        List<String> immutable = List.of("x", "y");
        try {
            swap(immutable, 0, 1);
        } catch (UnsupportedOperationException e) {
            System.out.println("immutable: unsupported");
        }

        List<String> one = new ArrayList<>(List.of("only"));
        swap(one, 0, 0);
        System.out.println("same index: " + one);

        try {
            swap(one, 0, 1);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("invalid index: " + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp với JDK 17 trở lên:

```bash
javac WildcardSwapDemo.java
java WildcardSwapDemo
```

**Đầu ra chuẩn:**

```text
names: [Chi, Binh, An]
numbers: [20, 10, 30]
Collections.swap: [Binh, Chi, An]
fixed-size: [blue, red]
immutable: unsupported
same index: [only]
invalid index: IndexOutOfBoundsException
```

### Đọc kết quả từng bước

- `names` thực sự là `List<String>` chứa `[An, Binh, Chi]`; biến `unknown` kiểu `List<?>` cùng trỏ tới danh sách. `swap(unknown, 0, 2)` đổi phần tử ở vị trí `0` và `2`, nên kết quả `[Chi, Binh, An]`.
- `swap(numbers, 0, 1)` áp dụng cùng một phương thức cho `List<Integer>` và tạo `[20, 10, 30]`; mã không cần biết trước `T` là `Integer` hay `String`.
- `Collections.swap(unknown, 0, 1)` là API chuẩn của JDK, đổi hai vị trí đầu thành `[Binh, Chi, An]`.
- `Arrays.asList("red", "blue")` tạo danh sách **kích thước cố định** nhưng hỗ trợ `set`, vì vậy vẫn hoán đổi được hai giá trị.
- `List.of("x", "y")` tạo danh sách **không cho sửa**; gọi `set` bên trong helper ném `UnsupportedOperationException`, dù chữ ký generic hoàn toàn hợp lệ.
- Khi `i == j`, helper tự trả về sau khi hai chỉ số đã được xác nhận hợp lệ. Với `[only]`, nội dung giữ nguyên.
- `Objects.checkIndex(1, one.size())` ném `IndexOutOfBoundsException` vì danh sách một phần tử chỉ có chỉ số hợp lệ là `0`.

Ví dụ hoàn chỉnh này dùng import chính xác từ `java.util`. `Objects.checkIndex` có từ Java 9, vì vậy chạy được trên Java 17.

## 4. Vì sao helper là giải pháp đúng về kiểu?

Trong `swapCaptured`, ta khai báo:

```java
private static <T> void swapCaptured(List<T> values, int i, int j) {
    T saved = values.get(i);
    values.set(i, values.get(j));
    values.set(j, saved);
}
```

Kiểu `T` biểu thị **cùng một kiểu phần tử cho cả ba thao tác**. Compiler kiểm tra:

| Biểu thức | Kiểu được compiler nhìn thấy | Ý nghĩa |
| --- | --- | --- |
| `values` | `List<T>` | Danh sách có kiểu phần tử `T` |
| `values.get(i)` | `T` | Đọc đúng kiểu của danh sách |
| `T saved` | `T` | Lưu giá trị không mất thông tin kiểu |
| `values.set(i, values.get(j))` | `T` truyền vào `set(int, T)` | Ghi phần tử cùng kiểu |
| `values.set(j, saved)` | `T` truyền vào `set(int, T)` | Phục hồi giá trị cũ tại vị trí kia |

Tương phản với phương thức chỉ nhận `List<?>`, nếu bạn viết `Object saved = list.get(i)`, biểu thức `saved` chỉ còn kiểu tĩnh `Object`. Một `List<Integer>` không cho phép compiler coi mọi `Object` là `Integer`. Vì vậy **giữ kiểu `T` xuyên suốt phép hoán đổi** là mấu chốt.

Không cần ràng buộc kiểu `<T extends Number>` vì thuật toán hoán đổi không thực hiện phép toán số học hay cần tính chất nào của `Number`. Nó chỉ vận chuyển phần tử qua hai vị trí cùng danh sách. Đây là lý do helper **không giới hạn** chạy với kiểu dữ liệu cụ thể.

Nếu một ngày cần xử lý kiểu cụ thể, chẳng hạn tính toán trên `Number`, hãy thêm bound vì **nhu cầu xử lý** chứ không phải vì bản thân việc swap cần bound.

## 5. `Collections.swap`: khi nào nên dùng sẵn API chuẩn?

JDK đã có phương thức:

```java
public static void swap(List<?> list, int i, int j)
```

Đây là **chữ ký API** được trích ở dạng tối giản; phương thức thực sự thuộc lớp `java.util.Collections`. Bạn có thể gọi trực tiếp:

```java
List<String> words = new ArrayList<>(List.of("left", "right"));
List<?> view = words;
Collections.swap(view, 0, 1);
System.out.println(words); // [right, left]
```

Đoạn code trên minh họa các lệnh trong phương thức đã import `List`, `ArrayList`, `Collections`.

Điều đáng chú ý là chính API chuẩn cũng công khai nhận `List<?>`. Điều đó **không có nghĩa mọi phần tử đều là `Object`**, mà thể hiện rằng thao tác đổi vị trí **không phụ thuộc vào kiểu phần tử cụ thể**. Người dùng API được hưởng lợi từ tính tổng quát mà không phải viết hoặc nhìn thấy cơ chế bắt giữ wildcard bên trong.

**Trong ứng dụng thực tế, nếu chỉ cần hoán đổi hai vị trí, ưu tiên `Collections.swap`.** Tự viết helper là cách học capture và hữu ích khi một thuật toán tùy chỉnh khác cần liên kết các giá trị lấy từ cùng một kiểu generic.

`Collections.swap` có thể ném `IndexOutOfBoundsException` nếu chỉ số không hợp lệ, và `UnsupportedOperationException` nếu danh sách không hỗ trợ `set`. Nó không biến các danh sách immutable thành mutable.

## 6. Hoán đổi là thay phần tử, không phải thay kích thước

Một phép swap thông thường giữ nguyên số phần tử và chỉ thay giá trị tại hai vị trí. Do đó nó cần khả năng **lấy `get` và thay `set`** chứ không cần `add` hoặc `remove` để thay đổi kích thước.

| Loại danh sách | Thay bằng `set` | Swap được khi chỉ số hợp lệ? | Ghi chú |
| --- | --- | --- | --- |
| `new ArrayList<>(...)` | Có | Có | Có thể thay phần tử theo chỉ số |
| `new LinkedList<>(...)` | Có | Có | Truy cập theo chỉ số có thể tốn thời gian |
| `Arrays.asList(...)` | Có | Có | Kích thước cố định nhưng hỗ trợ thay phần tử |
| `List.of(...)` | Không | Không | Danh sách không cho sửa |
| `List.copyOf(...)` | Không | Không | Danh sách không cho sửa |
| `Collections.unmodifiableList(...)` | Không qua wrapper | Không qua wrapper | Có thể phản ánh thay đổi nguồn từ alias khác |

Vì vậy, hai khái niệm cần tách:

- **Type-safety:** helper bảo đảm không đưa sai kiểu phần tử vào danh sách.
- **Mutability:** implementation quyết định có chấp nhận `set` hay không.

Một lời gọi như `swap(List.of("a", "b"), 0, 1)` **biên dịch được**; đến runtime mới ném `UnsupportedOperationException`. Còn `swap(Arrays.asList("a", "b"), 0, 1)` thực hiện thành công vì nó không cần thay đổi kích thước.

Đối với `Collections.unmodifiableList(source)`, alias `source` có thể vẫn mutable; wrapper chỉ chặn thao tác thay qua chính wrapper. Wildcard và unmodifiable wrapper là hai cơ chế khác nhau.

## 7. Kiểm soát chỉ số và cùng một vị trí

Cài đặt mẫu gọi:

```java
Objects.checkIndex(i, values.size());
Objects.checkIndex(j, values.size());
```

Đây là các lệnh minh họa trong phương thức. Với một list có `size() == n`, chỉ số hợp lệ thỏa `0 <= index < n`. Kiểm tra cả hai trước khi bắt đầu đổi sẽ cho lỗi rõ ràng nếu có chỉ số âm hoặc vượt giới hạn, đồng thời tránh trường hợp sửa vị trí đầu rồi mới phát hiện vị trí thứ hai không hợp lệ.

Nếu `i == j`, hai phần tử vốn ở cùng một vị trí, nên việc swap không thay đổi kết quả. Helper minh họa **trả về sớm** để không phải gọi `get/set` khi không cần thiết, nhưng vẫn kiểm tra tính hợp lệ của chỉ số trước đó. Lựa chọn này còn khiến một danh sách không hỗ trợ `set` có thể chấp nhận trường hợp cùng chỉ số vì không phải thực hiện thao tác thay đổi nào; đừng suy rộng đặc điểm đó cho mọi implementation swap khác.

Nếu danh sách rỗng, không có chỉ số hợp lệ để swap hai phần tử. Hai tham số chỉ số **không âm** cũng chưa đủ; phải nhỏ hơn `size()` hiện tại.

Các kiểm tra trên không bảo đảm an toàn nếu một luồng khác đang thay đổi cấu trúc danh sách đồng thời. Cần cơ chế đồng bộ khi truy cập chia sẻ.

## 8. Không dùng raw type hoặc cast để né wildcard capture

Một giải pháp hấp tấp là cast `List<?>` về `List<Object>`, hoặc dùng raw `List` để ép lời gọi `set` biên dịch:

```java
// Ví dụ cố ý KHÔNG an toàn, không nên sử dụng:
@SuppressWarnings({"rawtypes", "unchecked"})
static void unsafe(List<?> values, int index) {
    List raw = values;
    raw.set(index, "some text");
}
```

Đây là phương thức minh họa về lỗi thiết kế. Nếu `values` thực sự trỏ tới `List<Integer>`, cách làm này có thể đặt một `String` vào danh sách mà code còn lại tin rằng chỉ chứa `Integer`. Chương trình có thể gặp `ClassCastException` khi đọc về sau.

Helper `<T>` tránh được vấn đề ấy vì:

1. Không thay đổi kiểu phần tử thực của list.
2. Chỉ chuyển chính các giá trị được đọc từ `List<T>` vào lại `List<T>`.
3. Không cần `@SuppressWarnings("unchecked")`.
4. Compiler kiểm tra toàn bộ các phép `set` theo một `T` nhất quán.

Điểm quan trọng: **không phải mọi helper nhận `List<T>` đều an toàn**, mà an toàn đến từ cách dùng `T`. Nếu truyền các giá trị không liên quan qua raw type hoặc cast không kiểm tra, bạn vẫn có thể phá ràng buộc kiểu.

## 9. Capture dành cho một danh sách, đừng ghép hai wildcard khác nhau

Hai biến cùng khai báo `List<?>` **không bảo đảm chúng có cùng kiểu phần tử**:

```java
List<?> left = List.of("a", "b");
List<?> right = List.of(1, 2);

// Không được giả định phần tử từ left ghi được vào right,
// hoặc ngược lại.
```

`left` có thể chứa `String` trong khi `right` chứa `Integer`. Vì vậy, một phương thức hỗ trợ nhận **một** `List<T>` là đủ để hoán đổi **hai vị trí của chính danh sách đó**. Nếu muốn hoán đổi phần tử giữa hai list khác nhau, phải thiết kế ràng buộc kiểu cho cả hai list: hai wildcard độc lập không chứng minh được phần tử của list này tương thích với list kia.

Một ví dụ về chữ ký cần quan hệ chung, chỉ mang tính minh họa:

```java
static <T> void exchange(List<T> a, int i, List<T> b, int j) {
    T saved = a.get(i);
    a.set(i, b.get(j));
    b.set(j, saved);
}
```

Phương thức trên đòi **cả hai list được chấp nhận dưới cùng `T`** và đều phải hỗ trợ `set`. Nó không phải giải pháp tổng quát cho hai `List<?>` độc lập; không nên tự ép chúng thành một kiểu chung để tránh lỗi compiler. Khi bài toán chỉ là swap nội bộ một list, dùng `swap(List<?>)` đơn giản hơn và chính xác hơn.

## 10. Độ phức tạp và giới hạn của thuật toán

Helper thực hiện tối đa hai lần `get` và hai lần `set`, cùng một số phép kiểm tra hằng số:

- Với `ArrayList`, truy cập theo chỉ số thường O(1), nên swap theo hai chỉ số là O(1) thời gian.
- Với `LinkedList`, truy cập vị trí theo chỉ số thường cần duyệt các node, chi phí có thể tới O(n) đối với danh sách dài.
- Helper chỉ lưu một tham chiếu `T saved`, nên dùng O(1) bộ nhớ phụ.
- Hoán đổi **không sao chép sâu** phần tử; nó chỉ thay những tham chiếu nằm ở hai vị trí.

Nếu một implementation cho phép `set` ở vị trí đầu nhưng từ chối hoặc lỗi ở lần `set` tiếp theo, phương thức không cam kết tính nguyên tử/rollback. Với các list mutable bình thường, hai lần `set` thực hiện thành công; nhưng không nên quảng bá helper như một giao dịch bất khả phân.

Khi phần tử bản thân là đối tượng mutable, swap chỉ thay thứ tự tham chiếu tới các đối tượng đó; trạng thái nội tại của đối tượng không thay đổi. Nếu hai vị trí cùng tham chiếu đến cùng một đối tượng, swap không tạo sự khác biệt quan sát được.

Không có một generic wildcard nào tự tạo ra khả năng thread-safe. Nếu list được chia sẻ giữa các luồng, phải tuân thủ hợp đồng đồng bộ của collection được dùng.

## 11. Những hiểu lầm thường gặp

**“`List<?>` luôn không cho sửa.”** Sai. Wildcard hạn chế khả năng đưa một giá trị có kiểu chưa biết vào list qua biến, nhưng helper generic vẫn có thể thực hiện `set` với phần tử lấy ra từ chính list, nếu implementation hỗ trợ.

**“Có thể đổi `List<?>` thành `List<Object>` cho dễ.”** Sai. `List<String>` không phải subtype của `List<Object>`. Raw/cast không kiểm tra có thể phá an toàn kiểu.

**“`List<?>.get(...)` trả về `Object` nên ghi `Object` ấy trở lại chắc chắn hợp lệ.”** Về mặt logic, giá trị từ cùng list đúng kiểu; nhưng biểu thức `Object` không giữ được quan hệ kiểu đó để compiler chứng minh. Generic helper tạo `T` nhất quán cho cả lần đọc và lần ghi.

**“Helper `<T>` biến list thành `List<T>` mới.”** Sai. Nó không tạo list, không copy, không sửa kiểu runtime; `T` là biến kiểu phục vụ kiểm tra compile time.

**“`Collections.swap` nhận `List<?>` nên đổi được cả `List.of`.”** Sai. Chữ ký nhận được nhiều loại generic, nhưng đối tượng immutable vẫn từ chối `set`.

**“Danh sách kích thước cố định không thể swap.”** Không đúng trong mọi trường hợp. `Arrays.asList` không cho thêm/xóa làm đổi kích thước, nhưng vẫn hỗ trợ thay thế bằng `set`.

**“Swap hai vị trí ở hai `List<?>` cũng dùng cùng helper này.”** Không thể mặc nhiên, vì hai wildcard có thể bắt giữ hai kiểu phần tử hoàn toàn khác nhau.

## 12. Tự kiểm tra

**Câu 1.** Tại sao `swap(List<?> list, ...)` gọi được với cả `List<Integer>` và `List<String>`?

Vì mọi `List<T>` đều có thể được tham chiếu qua `List<?>`. Trong lần gọi helper, compiler bắt giữ một kiểu phần tử nhất quán cho riêng danh sách đó.

**Câu 2.** Trong helper, vì sao dùng `T saved` tốt hơn `Object saved`?

Vì `T saved` giữ đúng kiểu phần tử của `List<T>` để truyền lại vào `set(int, T)`. Với `Object`, compiler không thể coi đó là `T` một cách tổng quát.

**Câu 3.** Với `List<?> view = Arrays.asList("x", "y")`, `swap(view, 0, 1)` có chạy được không?

Có. `Arrays.asList` hỗ trợ `set` và swap không thay đổi kích thước, nên kết quả là `[y, x]`.

**Câu 4.** Với `List<?> view = List.of("x", "y")` thì sao?

Biên dịch được, nhưng tại runtime phương thức cố `set` và ném `UnsupportedOperationException`.

**Câu 5.** Có phải `Collections.swap` yêu cầu `List<Object>`?

Không. Chữ ký công khai là `swap(List<?>, int, int)`; nó chấp nhận list có kiểu phần tử bất kỳ.

**Câu 6.** Nếu danh sách có 3 phần tử, `swap(list, 0, 3)` cho kết quả gì?

`Objects.checkIndex(3, 3)` ném `IndexOutOfBoundsException` trước khi dữ liệu được thay, vì các chỉ số hợp lệ chỉ là `0`, `1`, `2`.

**Câu 7.** Nếu `swap(list, 1, 1)` và vị trí `1` hợp lệ, helper ở ví dụ chính có thay phần tử không?

Không. Sau khi xác minh hai chỉ số, helper thấy `i == j` và trở về mà không thực hiện `get/set`.

## Ghi nhớ

`List<?>` lưu một **kiểu phần tử chưa biết**, nên không được tùy ý đưa giá trị `Object` vào qua `set`. **Wildcard capture** giúp một generic helper `<T>` giữ cùng kiểu `T` giữa `get` và `set`, từ đó hoán đổi phần tử của chính danh sách mà không cần raw type hay cast. Khi chỉ cần chức năng này trong chương trình, có thể dùng trực tiếp `Collections.swap(List<?>, int, int)`. Dù dùng cách nào, danh sách thực tế vẫn phải hỗ trợ thay thế phần tử, chỉ số phải hợp lệ và generics không tự bảo đảm tính nguyên tử hay đồng bộ.
