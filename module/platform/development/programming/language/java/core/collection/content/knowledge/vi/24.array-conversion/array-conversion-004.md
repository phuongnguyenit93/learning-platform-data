# toArray(), toArray(T[]) và toArray(IntFunction)

## 1. Từ collection sang mảng: phải chọn cả kiểu lẫn nơi chứa dữ liệu

Một thư viện có thể trả về `List<String>`, trong khi API tiếp theo lại nhận `String[]`. Cả hai đều biểu diễn nhiều phần tử, nhưng hợp đồng của chúng khác nhau: collection quản lý số lượng phần tử theo cách triển khai của nó; một đối tượng mảng có độ dài cố định và có kiểu thành phần được kiểm tra lúc chạy.

Các phương thức `toArray` là cầu nối theo chiều **collection → mảng**. Chúng đưa các phần tử vào mảng kết quả, không chuyển chuỗi thành số, không sắp xếp dữ liệu và không tự sao chép sâu các đối tượng phần tử.

Trước khi chọn cách gọi, cần trả lời ba câu hỏi:

1. API nhận kết quả cần `Object[]`, `String[]`, `Number[]` hay một kiểu mảng khác?
2. Có muốn cung cấp một mảng đã cấp phát để tái sử dụng không?
3. Có cần mảng kết quả chỉ có đúng số ô chứa phần tử, hay chấp nhận một bộ đệm lớn hơn?

Hai khái niệm đặc biệt quan trọng:

- **Kiểu khai báo của biến:** kiểu mà trình biên dịch nhìn thấy, chẳng hạn `Object[]`.
- **Kiểu thành phần lúc chạy** (runtime component type): loại đối tượng mà mảng thực tế có thể chứa. Một biến `Object[]` vẫn có thể đang trỏ tới đối tượng `String[]`.

Đổi kiểu khai báo hoặc ép kiểu một tham chiếu không tạo lại đối tượng mảng với kiểu thành phần mới. Đây là nguồn gốc của nhiều lỗi khi dùng `toArray`.

Bài học lần lượt xét kiểu mảng, cách tái sử dụng bộ đệm, hàm tạo mảng, rồi đến quyền sở hữu và chia sẻ tham chiếu của dữ liệu kết quả.

## 2. Ba dạng gọi và cách chọn

Các chữ ký dưới đây thuộc `Collection<E>`; đây là khai báo API rút gọn, không phải chương trình chạy độc lập:

```java
Object[] toArray();
<T> T[] toArray(T[] array);
default <T> T[] toArray(IntFunction<T[]> generator);
```

Dạng dùng `IntFunction` có từ Java 11. Các chương trình trong bài dùng API phù hợp Java 17 và lệnh biên dịch `--release 17`.

| Dạng gọi | Bên gọi cung cấp | Kiểu mảng kết quả | Trường hợp thường dùng |
| --- | --- | --- | --- |
| `items.toArray()` | Không có đối số | `Object[]` | Chỉ cần một mảng đối tượng tổng quát |
| `items.toArray(new String[0])` | Mảng mẫu có kiểu `String[]` | Cùng kiểu mảng lúc chạy với mảng đối số | Cần mảng chuỗi; cách viết cũng dùng được trước Java 11 |
| `items.toArray(buffer)` | Một mảng có sẵn | Cùng kiểu mảng lúc chạy với `buffer` | Chủ động cung cấp nơi chứa, chấp nhận quy tắc tái sử dụng |
| `items.toArray(String[]::new)` | Hàm tạo mảng chuỗi | Kiểu mảng do hàm tạo cung cấp | Muốn diễn đạt trực tiếp kiểu mảng trên Java 11+ |

Tên `T` trong hai phương thức có kiểu là tham số kiểu của **phương thức**, không phải một cách viết lại bắt buộc của `E` trong `Collection<E>`. Vì vậy, chọn một kiểu mảng đích không tương thích với phần tử có thể vẫn biên dịch, rồi thất bại lúc chạy.

Một collection chuỗi có thể được đưa vào mảng `Object[]` hoặc `CharSequence[]`. Ngược lại, một collection số chứa cả `Integer` và `Double` không thể được lưu đầy đủ trong `Integer[]`. Phải xét các phần tử thực tế và loại đối tượng mà mảng đích chấp nhận.

[Hợp đồng `Collection.toArray`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray()) xác định kiểu kết quả, thứ tự và các quy tắc nhận mảng/hàm tạo mảng.

## 3. toArray(): kết quả thật sự là Object[]

Khi gọi không đối số, kiểu lúc chạy của mảng kết quả là `Object[]`, kể cả khi tất cả phần tử đều là `String`. Mảng có số ô bằng số phần tử được trả về và không phải mảng lưu trữ nội bộ mà collection giữ để phản ánh các lần sửa ô của kết quả.

Đoạn sau chỉ minh họa ý tưởng, không phải chương trình độc lập:

```java
List<String> words = List.of("red", "blue");
Object[] objects = words.toArray();

// Van bien dich, nhung that bai luc chay:
String[] strings = (String[]) objects;
```

Phép ép kiểu kiểm tra xem đối tượng đang có có phải `String[]` hay không. Nó không duyệt từng ô để thấy mọi phần tử là chuỗi, rồi thay mảng `Object[]` bằng một mảng chuỗi mới. Kết quả vì vậy là `ClassCastException`.

Nếu API tiếp theo nhận `String[]`, yêu cầu tạo đúng loại mảng ngay từ đầu bằng `toArray(new String[0])` hoặc `toArray(String[]::new)`. Thêm phép ép kiểu để tránh sửa lời gọi không giải quyết được vấn đề.

Với `Object[]` nhận từ `toArray()`, sửa một ô của mảng không thay chính ô tương ứng trong cấu trúc collection. Tuy nhiên, đối tượng mà ô trỏ tới vẫn có thể được chia sẻ; phần về sao chép nông sẽ phân biệt hai loại thay đổi này.

## 4. toArray(T[]): mảng đối số vừa là nơi chứa, vừa mang thông tin kiểu

Đặt:

- `n` là số phần tử cần đưa ra mảng.
- `m` là độ dài mảng đối số `array`.
- Các phần tử có kiểu phù hợp để lưu vào mảng đó.

Phần phân tích này giả sử không có đường sửa đồng thời làm thay đổi dữ liệu trong lúc chuyển đổi và lời gọi hoàn tất thành công.

| Quan hệ kích thước | Mảng được trả về | Độ dài kết quả | Điều cần nhớ |
| --- | --- | --- | --- |
| `m < n` | Mảng mới, cùng kiểu lúc chạy với mảng đối số | `n` | Phải dùng giá trị trả về; mảng đã truyền vào chưa đủ chỗ |
| `m == n` | Chính mảng đối số | `m` | Tất cả các ô chứa phần tử của collection |
| `m > n` | Chính mảng đối số | `m` | Ô ở chỉ số `n` được đặt thành `null` sau phần dữ liệu |

Mảng không thể tăng độ dài tại chỗ. Khi quá nhỏ, phương thức tạo một mảng khác rồi trả về tham chiếu mới. Do đó, cách gọi cần giữ kết quả:

```java
// Doan minh hoa: buffer da duoc khai bao la String[].
buffer = names.toArray(buffer);
```

Nếu chỉ gọi `names.toArray(buffer)` rồi bỏ giá trị trả về, mã có thể có vẻ đúng khi `buffer` đủ lớn nhưng đọc nhầm bộ đệm cũ khi collection có thêm phần tử.

### 4.1. Mảng độ dài 0 vẫn cung cấp thông tin kiểu

Trong `names.toArray(new String[0])`, mảng rỗng không có nhiệm vụ tự chứa được mọi phần tử. Nó cung cấp loại mảng cần tạo. Nếu collection không rỗng, mảng kết quả mới có độ dài phù hợp; kiểu lúc chạy vẫn là `String[]`.

Không được diễn giải `new String[0]` thành “chỉ lấy 0 phần tử”. `toArray` đưa ra toàn bộ phần tử theo hợp đồng của collection.

Nếu collection rỗng và mảng đối số cũng rỗng, không cần thêm chỗ chứa: mảng đối số có thể được trả về đúng theo nhánh đủ chỗ. Điều này khác với việc mặc nhiên cho rằng mọi dạng `toArray` luôn tạo một đối tượng mảng mới.

### 4.2. Null sau dữ liệu không phải độ dài mảng mới

Ví dụ, collection có hai chuỗi nhưng mảng đích có năm ô. Sau khi gọi thành công, hai ô đầu chứa dữ liệu, ô thứ ba là `null` và độ dài mảng vẫn là năm.

Không có cam kết rằng toàn bộ phần đuôi sẽ được xóa trắng. Trong ví dụ dùng `ArrayList` bên dưới, các ô sau dấu `null` vẫn giữ giá trị cũ. Vì thế, duyệt toàn bộ `result.length` như thể tất cả đều là phần tử của collection có thể xử lý nhầm dữ liệu cũ.

Nếu collection được biết chắc không chứa `null`, dấu `null` ngay sau vùng dữ liệu có thể giúp nhận biết điểm kết thúc. Nếu collection cho phép `null`, tìm `null` đầu tiên không phải cách xác định số phần tử hợp lệ.

Trường hợp collection rỗng cũng cần chú ý: với mảng đích còn chỗ, ô `0` được đặt thành `null`; các phần tử cũ ở vị trí sau đó có thể vẫn còn.

### 4.3. Quy tắc kiểu dựa trên mảng thực tế

Biến `Number[]` có thể trỏ tới `new Integer[0]`. Truyền biến này vào `toArray` không yêu cầu phương thức tạo `Number[]` rộng hơn. Kiểu mảng thực tế vẫn là `Integer[]`, nên một phần tử `Double` không thể được chứa trong kết quả ấy.

Cần phân biệt:

```java
// Doan minh hoa hai doi tuong mang co kieu luc chay khac nhau.
Number[] wide = new Number[0];
Number[] narrow = new Integer[0];
```

Cùng kiểu khai báo `Number[]` không có nghĩa hai mảng có cùng khả năng chứa phần tử. [Quy tắc mảng của Java](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5) giải thích phép kiểm tra khi lưu đối tượng vào mảng.

## 5. Chương trình: Quan sát các nhánh kích thước

Chương trình sau dùng `ArrayList` để thứ tự dữ liệu xác định. Các biến `small`, `exact` và `large` lần lượt kiểm tra mảng nhỏ hơn, bằng và lớn hơn số phần tử.

Tệp `ToArrayOverloadsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ToArrayOverloadsDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Minh"));

        Object[] objects = names.toArray();
        System.out.println("plainType=" + objects.getClass().getTypeName());
        System.out.println("plain=" + Arrays.toString(objects));
        try {
            String[] invalid = (String[]) objects;
            throw new AssertionError("Cast unexpectedly succeeded: " + invalid.length);
        } catch (ClassCastException expected) {
            System.out.println("plainCast=ClassCastException");
        }

        String[] small = {"old"};
        String[] grown = names.toArray(small);
        System.out.println("smallReused=" + (grown == small));
        System.out.println("smallAfter=" + Arrays.toString(small));
        System.out.println("grown=" + Arrays.toString(grown));

        String[] exact = new String[2];
        String[] exactResult = names.toArray(exact);
        System.out.println("exactReused=" + (exactResult == exact));
        System.out.println("exact=" + Arrays.toString(exact));

        String[] large = {"x0", "x1", "x2", "x3", "x4"};
        String[] largeResult = names.toArray(large);
        System.out.println("largeReused=" + (largeResult == large));
        System.out.println("large=" + Arrays.toString(large));

        String[] zeroResult = names.toArray(new String[0]);
        String[] generated = names.toArray(String[]::new);
        System.out.println("zeroType=" + zeroResult.getClass().getTypeName());
        System.out.println("generated=" + Arrays.toString(generated));

        generated[0] = "changed";
        names.set(1, "owner");
        System.out.println("namesAfter=" + names);
        System.out.println("arrayAfter=" + Arrays.toString(generated));

        String[] emptyTarget = {"old0", "old1", "old2"};
        String[] emptyResult = List.<String>of().toArray(emptyTarget);
        System.out.println("emptyReused=" + (emptyResult == emptyTarget));
        System.out.println("emptyTarget=" + Arrays.toString(emptyTarget));

        List<String> withNull = Arrays.asList(null, "x");
        String[] nullableTarget = {"a", "b", "c", "d"};
        withNull.toArray(nullableTarget);
        System.out.println("nullable=" + Arrays.toString(nullableTarget));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 ToArrayOverloadsDemo.java
java ToArrayOverloadsDemo
```

Đầu ra:

```text
plainType=java.lang.Object[]
plain=[Lan, Minh]
plainCast=ClassCastException
smallReused=false
smallAfter=[old]
grown=[Lan, Minh]
exactReused=true
exact=[Lan, Minh]
largeReused=true
large=[Lan, Minh, null, x3, x4]
zeroType=java.lang.String[]
generated=[Lan, Minh]
namesAfter=[Lan, owner]
arrayAfter=[changed, Minh]
emptyReused=true
emptyTarget=[null, old1, old2]
nullable=[null, x, null, d]
```

### 5.1. Đọc kết quả theo ba loại thông tin

`plainType=java.lang.Object[]` giải thích tại sao ép mảng này thành `String[]` thất bại. Loại đối tượng mảng chưa từng trở thành mảng chuỗi chỉ vì nội dung là hai chuỗi.

`smallReused=false` cho thấy mảng một ô không được trả về làm nơi chứa kết quả hai phần tử. Trong thí nghiệm này, `small` vẫn giữ `"old"`, còn dữ liệu nằm trong `grown`. Đây là lý do phải giữ giá trị trả về.

`exactReused=true` và `largeReused=true` cho thấy phương thức có thể ghi vào chính mảng được cung cấp khi đủ chỗ. Trong mảng lớn, `x2` bị thay bằng dấu `null` ở ngay sau dữ liệu; `x3` và `x4` vẫn còn.

`namesAfter` và `arrayAfter` chứng minh việc thay một ô của mảng kết quả và thay một phần tử trong list không làm hai cấu trúc trở thành một khung nhìn sống của nhau trong ví dụ này.

Cuối cùng, `nullable=[null, x, null, d]` chứa hai giá trị `null` có vai trò khác nhau: ô đầu là phần tử thực sự của collection, ô thứ ba là dấu kết thúc sau hai phần tử. Chỉ đọc tới `null` đầu tiên sẽ bỏ mất phần tử `"x"`.

## 6. Lỗi kiểu trong ba cách chuyển sang mảng

`toArray()` tạo `Object[]`; nếu ép chính đối tượng mảng ấy thành `String[]`, lời ép gây `ClassCastException`. Với hai overload nhận mảng hoặc hàm tạo mảng, hệ thống còn phải kiểm tra từng phần tử có lưu được vào **kiểu thành phần thực** của mảng đích hay không. Nếu không, `ArrayStoreException` xuất hiện.

Ví dụ minh họa trong một phương thức có các import `Collection` và `List`:

```java
Collection<Number> values = List.of(1, 2.5);
Number[] accepted = values.toArray(Number[]::new); // [1, 2.5]
// Cả hai lời gọi sau đều gây ArrayStoreException:
values.toArray(new Integer[0]);
values.toArray(Integer[]::new);
```

`Number[]` nhận được cả `Integer` và `Double`, còn `Integer[]` không chứa được `Double`. Generics không loại bỏ kiểm tra lưu trữ lúc chạy. Ngay cả biến `Number[]` cũng có thể đang giữ một đối tượng `Integer[]` và bị từ chối khi ghi `Double`. Chi tiết về covariance, kiểu mảng thực và kết quả chép dở được phân tích trong bài chuyên đề `ArrayStoreException` tiếp theo.

Cần phân biệt thêm các trường hợp sau:

| Tình huống | Kết quả hoặc yêu cầu |
| --- | --- |
| `(String[]) list.toArray()` | `ClassCastException`, vì kiểu thực là `Object[]` |
| `toArray(new Integer[0])` với dữ liệu chứa `Double` | `ArrayStoreException` lúc lưu phần tử |
| `toArray((String[]) null)` hoặc `toArray((IntFunction<String[]>) null)` | `NullPointerException`; ép kiểu ở đây chỉ để phân giải overload |
| `toArray(null)` không kèm kiểu khi có cả hai overload | Lời gọi nhập nhằng tại thời điểm biên dịch |
| Chuyển `List<Integer>` sang `int[]` | Cần luồng `IntStream`/phép tháo hộp riêng; `Collection.toArray` trả mảng tham chiếu |

Nếu phép chuyển đổi thất bại, không coi bộ đệm được cung cấp là kết quả hoàn chỉnh hoặc mặc định nó đã được hoàn tác. `toArray` sao chép các tham chiếu, không tự chuyển `Integer[]` thành `int[]` và không tự kiểm tra chính sách `null` cho bước tháo hộp.

## 7. toArray(IntFunction): giao trách nhiệm tạo mảng cho một hàm

`IntFunction<R>` là giao diện hàm nhận một số `int` và trả về `R`. Với `toArray`, `R` là `T[]`: hàm nhận độ dài được yêu cầu rồi tạo một mảng có kiểu và độ dài ấy.

Hai cách viết tương đương về ý định tạo mảng chuỗi:

```java
// Doan minh hoa, names la mot Collection<String>.
String[] first = names.toArray(String[]::new);
String[] second = names.toArray(length -> new String[length]);
```

Cú pháp `String[]::new` là tham chiếu tới thao tác tạo mảng. Việc điền phần tử từ collection vào mảng vẫn do `toArray` thực hiện; hàm tạo chỉ cung cấp mảng.

[`IntFunction.apply(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntFunction.html) giải thích loại đầu vào và kết quả của giao diện này. Một lambda không có tham số như `() -> new String[0]` không đáp ứng hình dạng hàm nhận `int` mà overload yêu cầu.

### 7.1. Đối số nhận được không mặc nhiên là size()

Cách triển khai mặc định được công bố trong `Collection` gọi hàm tạo với `0`, sau đó chuyển mảng nhận được vào `toArray(T[])`. Có thể hình dung bằng đoạn minh họa cơ chế sau:

```java
// Mo hinh rut gon cua default method, khong phai chuong trinh doc lap.
return toArray(generator.apply(0));
```

Với hàm `String[]::new`, bước đầu tạo mảng chuỗi rỗng; phương thức nhận mảng sẽ cấp phát đủ chỗ nếu cần. Như vậy, có collection ba phần tử nhưng hàm tạo mặc định vẫn nhận `0` là hành vi được giải thích rõ, không phải lỗi.

Một lớp collection có thể ghi đè phương thức mặc định. Vì thế:

- Hàm tạo nên dùng đúng độ dài nhận được, không dựa vào một số lượng phần tử đã chụp từ bên ngoài.
- Không viết hàm tạo chỉ đúng khi đối số luôn bằng `0` hoặc luôn bằng `size()`.
- Không dựa vào số lần gọi hay tác dụng phụ của hàm tạo như một phần của nghiệp vụ.
- Hàm tạo không nên sửa collection đang được chuyển đổi.

[Đặc tả phương thức mặc định](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)) mô tả rõ lời gọi với `0`. Chương trình tiếp theo dùng một lớp kế thừa phương thức mặc định để quan sát đúng trường hợp này.

### 7.2. Khác với việc gọi qua Stream

`collection.toArray(String[]::new)` gọi API trên collection. `collection.stream().toArray(String[]::new)` tạo một luồng rồi gọi phép kết thúc của `Stream`.

Chúng có thể cho cùng dãy phần tử trong một tình huống đơn giản nhưng có hợp đồng thực thi và cơ chế triển khai riêng. Không lấy quan sát “hàm tạo nhận 0” ở default method của `Collection` để suy ra hàm tạo của mọi luồng, đặc biệt khi có xử lý song song, phải được gọi giống hệt.

Nếu chỉ cần chuyển collection thành mảng có kiểu, lời gọi trực tiếp diễn đạt đủ ý định. Nếu cần lọc hoặc biến đổi phần tử trước, một chuỗi thao tác trên luồng có thể đáp ứng thêm nhu cầu ấy; chính bước biến đổi mới giải thích việc sử dụng luồng.

[API `Stream.toArray(IntFunction)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toArray(java.util.function.IntFunction)) có mô tả riêng cho việc tạo các mảng phục vụ kết quả của luồng.

## 8. Quyền sở hữu mảng và sao chép nông

Có ba đối tượng cần phân biệt:

1. Collection chứa các tham chiếu phần tử.
2. Mảng kết quả có các ô chứa tham chiếu.
3. Những đối tượng phần tử mà cả hai cấu trúc có thể cùng trỏ tới.

Tạo một mảng mới không có nghĩa tạo lại mọi đối tượng phần tử. Nếu một phần tử là đối tượng có thể thay đổi, sửa trạng thái của đối tượng ấy qua mảng vẫn có thể được quan sát khi đọc qua collection.

Ngược lại, thay một ô trong một mảng mới bằng tham chiếu khác chỉ thay ô của mảng đó. Nó không tự gọi `set` hay `add` trên collection. Việc collection tăng số phần tử về sau cũng không làm mảng đã có tăng độ dài.

Đây là **sao chép nông** (shallow copy) theo góc nhìn cấu trúc chứa các tham chiếu, không phải sao chép sâu toàn bộ đồ thị đối tượng.

### 8.1. Cung cấp mảng có sẵn không xóa các quan hệ chia sẻ đã tồn tại

Với `toArray()`, collection phải cung cấp một mảng mới an toàn cho bên gọi sửa các ô.

Với `toArray(T[])`, bên gọi chủ động cung cấp một mảng. Nếu mảng ấy đủ chỗ, chính nó được trả về. Phương thức không tự làm cho mảng đó độc lập với tất cả thành phần khác vốn đang sử dụng nó.

Ví dụ đặc biệt đáng chú ý:

- `Arrays.asList(backing)` tạo list được hậu thuẫn bởi `backing`.
- Gọi `list.toArray(backing)` với chính mảng gốc có thể trả về `backing`.
- Kết quả vẫn chia sẻ các ô mảng với list theo quan hệ đã tồn tại từ trước.

Nếu muốn một mảng mới riêng biệt trong tình huống này, truyền hàm tạo mảng mới như `String[]::new` hoặc một mảng đích mới phù hợp. Ngay cả khi các ô mảng đã tách biệt, các đối tượng phần tử vẫn có thể được chia sẻ.

[API `Arrays.asList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)) quy định list được hậu thuẫn bởi mảng đầu vào. Đọc cả hợp đồng nguồn lẫn đích giúp tránh suy luận rằng một lời gọi chuyển đổi tự xóa mọi quan hệ chia sẻ.

### 8.2. Chương trình: Ba lớp chia sẻ và hàm tạo mặc định

`Counter` là đối tượng có một trường thay đổi được. Phần đầu chương trình phân biệt sửa đối tượng `Counter` với thay ô mảng chứa tham chiếu tới `Counter`.

Phần sau dùng `Arrays.asList` để kiểm tra quan hệ với mảng gốc. Cuối cùng, lớp kế thừa `AbstractCollection` chỉ cung cấp `iterator` và `size`, giữ lại cách triển khai mặc định của overload nhận hàm tạo. Việc ghi lại đối số độ dài trong ví dụ chỉ phục vụ quan sát, không phải tác dụng phụ cần dùng trong ứng dụng.

Tệp `ToArrayOwnershipDemo.java`:

```java
import java.util.AbstractCollection;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Iterator;
import java.util.List;

public class ToArrayOwnershipDemo {
    private static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return Integer.toString(value);
        }
    }

    public static void main(String[] args) {
        List<Counter> counters = new ArrayList<>(
                List.of(new Counter(1), new Counter(2)));
        Counter[] captured = counters.toArray(Counter[]::new);
        System.out.println("sameElement=" + (captured[0] == counters.get(0)));

        captured[0].value = 10;
        captured[1] = new Counter(99);
        counters.add(new Counter(3));
        System.out.println("collection=" + counters);
        System.out.println("captured=" + Arrays.toString(captured));
        System.out.println("capturedLength=" + captured.length);

        String[] backing = {"left", "right"};
        List<String> backedList = Arrays.asList(backing);
        String[] detached = backedList.toArray(String[]::new);
        detached[0] = "copy";
        backing[1] = "owner";
        System.out.println("backing=" + Arrays.toString(backing));
        System.out.println("detached=" + Arrays.toString(detached));
        System.out.println("backedList=" + backedList);

        String[] alreadyAliased = backedList.toArray(backing);
        System.out.println("suppliedBackingReused=" + (alreadyAliased == backing));
        alreadyAliased[0] = "shared";
        System.out.println("afterAliasedWrite=" + backedList);

        Collection<Integer> inheritedDefault = new AbstractCollection<>() {
            private final List<Integer> values = List.of(3, 4, 5);

            @Override
            public Iterator<Integer> iterator() {
                return values.iterator();
            }

            @Override
            public int size() {
                return values.size();
            }
        };

        List<Integer> requestedLengths = new ArrayList<>();
        Integer[] result = inheritedDefault.toArray(length -> {
            requestedLengths.add(length);
            return new Integer[length];
        });
        System.out.println("defaultRequests=" + requestedLengths);
        System.out.println("defaultResult=" + Arrays.toString(result));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ToArrayOwnershipDemo.java
java ToArrayOwnershipDemo
```

Đầu ra:

```text
sameElement=true
collection=[10, 2, 3]
captured=[10, 99]
capturedLength=2
backing=[left, owner]
detached=[copy, right]
backedList=[left, owner]
suppliedBackingReused=true
afterAliasedWrite=[shared, owner]
defaultRequests=[0]
defaultResult=[3, 4, 5]
```

### 8.3. Giải thích những kết quả có vẻ trái ngược

`sameElement=true` cho thấy `captured[0]` và phần tử đầu của collection cùng trỏ tới một đối tượng. Sửa trường `value` qua `captured[0]` làm collection nhìn thấy `10`.

Thay `captured[1]` bằng một `Counter(99)` lại không thay phần tử thứ hai trong collection. Collection vẫn thấy `2`, còn mảng thấy `99`. Khi collection được thêm phần tử `3`, mảng vẫn có độ dài hai.

Ở ví dụ chuỗi, `detached` được tạo bằng hàm tạo mảng mới. Thay `detached[0]` không đổi `backing[0]`. Thay `backing[1]` được nhìn thấy qua `backedList`, nhưng `detached[1]` vẫn là `"right"`.

Sau đó `suppliedBackingReused=true` xác nhận khi chính `backing` được cung cấp làm mảng đích, phương thức trả về mảng đang hậu thuẫn list. Ghi `"shared"` qua kết quả lúc này được nhìn thấy trong list. Sự khác nhau đến từ đối tượng mảng đã được chọn làm nơi chứa, không phải từ việc `String` có tự thay đổi hay không.

Cuối cùng, `defaultRequests=[0]` khớp với cách triển khai mặc định đã mô tả. Mảng kết quả vẫn chứa đủ ba phần tử. Đối số đưa cho hàm tạo và độ dài mảng trả về cuối cùng không bắt buộc bằng nhau trong cơ chế mặc định này.

[`AbstractCollection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) là lớp triển khai khung, hữu ích để quan sát phần cơ chế mặc định mà không phải tự xây dựng toàn bộ collection.

## 9. Áp dụng đúng hợp đồng trong mã thực tế

### 9.1. Chọn theo mục tiêu của API nhận kết quả

| Nhu cầu | Cách viết có thể chọn | Điều phải kiểm tra thêm |
| --- | --- | --- |
| API nhận mảng đối tượng tổng quát | `collection.toArray()` | Có thực sự cần `Object[]` không? |
| API nhận mảng chuỗi trên Java 11+ | `collection.toArray(String[]::new)` | Các phần tử phải lưu được trong `String[]` |
| API nhận mảng chuỗi, cần cách viết tương thích trước Java 11 | `collection.toArray(new String[0])` | Luôn giữ mảng trả về |
| Muốn tái sử dụng một bộ đệm | `buffer = collection.toArray(buffer)` | Chấp nhận mảng có thể còn dư ô và các quan hệ chia sẻ sẵn có |
| API cần `int[]` từ `Collection<Integer>` | Biến đổi/tháo hộp rõ ràng, chẳng hạn `mapToInt` | Có chính sách cho `null` và dữ liệu không hợp lệ |

Nếu API phía sau yêu cầu một mảng chỉ chứa đúng `n` phần tử về mặt độ dài vật lý, không nên truyền một bộ đệm lớn hơn rồi mặc nhiên coi `result.length` là kích thước collection. Chọn mảng mới có kích thước phù hợp giúp hợp đồng giữa hai API đơn giản hơn.

Ngược lại, khi API được thiết kế để nhận bộ đệm và độ dài dữ liệu riêng, việc tái sử dụng mảng lớn có thể phù hợp. Độ dài dữ liệu cần được quản lý rõ ràng; dấu `null` không thay thế được độ dài đó khi `null` cũng là dữ liệu hợp lệ.

### 9.2. Thứ tự đi theo collection, không tự được sắp xếp

Nếu collection cam kết thứ tự duyệt, `toArray` phải giữ thứ tự tương ứng. Một `List` cung cấp thứ tự dãy phần tử, nên các chương trình trong bài có đầu ra xác định.

Một collection không có cam kết thứ tự không trở thành có thứ tự chỉ vì đã chuyển thành mảng. Ví dụ, không dùng kết quả của một `HashSet` để khẳng định phần tử ở chỉ số `0` luôn là phần tử nhỏ nhất hay được thêm đầu tiên.

Tương tự, việc đầu hàng đợi ưu tiên có ý nghĩa ưu tiên không có nghĩa toàn bộ iterator hoặc mảng kết quả của `PriorityQueue` đã được sắp xếp. [API `PriorityQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html) phân biệt rõ truy cập phần tử đầu với thứ tự duyệt. Nếu API đích cần một dãy đã sắp xếp, bước sắp xếp phải được thực hiện có chủ ý theo quy tắc phù hợp.

### 9.3. Map không có toArray trực tiếp

`Map` không phải là một `Collection`. Muốn xuất khóa, giá trị hoặc các cặp ánh xạ, phải chọn collection view tương ứng.

Đoạn sau minh họa hai lựa chọn khác nhau, không phải chương trình chạy độc lập:

```java
// scores la Map<String, Integer>.
String[] keys = scores.keySet().toArray(String[]::new);
Integer[] values = scores.values().toArray(Integer[]::new);
```

Cần chọn đúng ý nghĩa dữ liệu cho API đích. Nếu quan hệ khóa–giá trị phải được giữ cùng nhau, xuất hai mảng riêng qua hai lời gọi không tự tạo ra một bản chụp nguyên tử của các cặp ánh xạ khi map có thể thay đổi giữa hai lần gọi.

### 9.4. Mảng kết quả không chứng minh tính nguyên tử khi có sửa đồng thời

Các quy tắc kích thước ở phần trước mô tả một lần chuyển đổi hợp lệ, không mặc nhiên bổ sung một chính sách đồng bộ cho collection.

Ví dụ, gọi `size()` để cấp phát mảng rồi mới gọi `toArray` là hai thao tác riêng. Collection có thể thay đổi giữa chúng nếu có đường sửa đồng thời. Đừng suy luận rằng kích thước đã đọc là số phần tử chính xác của một thời điểm chung với mọi dữ liệu được đưa ra mảng.

Cần tuân thủ chính sách truy cập của loại collection cụ thể hoặc sử dụng cơ chế phối hợp thích hợp cho thao tác xuất dữ liệu. Một mảng nhận được thành công không tự chứng minh rằng toàn bộ dữ liệu nghiệp vụ liên quan đã được chụp ở cùng một thời điểm.

Với collection không cho phép sửa như `List.of`, `toArray` vẫn là thao tác đọc hợp lệ. Mảng mới nhận được có thể cho sửa các ô; điều đó không cấp quyền sửa cấu trúc của list nguồn.

### 9.5. Chi phí và những kết luận hiệu năng cần tránh

Thông thường, xuất `n` phần tử cần đưa `n` tham chiếu vào mảng đích. Với mảng mới đủ chứa dữ liệu, bộ nhớ cho các ô mảng tăng theo số phần tử; các đối tượng phần tử không vì thế được tạo bản sao sâu.

Một mảng đã cấp phát đủ chỗ có thể giảm nhu cầu tạo mảng kết quả mới. Tuy nhiên, còn phải tính chi phí quản lý bộ đệm, số ô dư, các tham chiếu cũ còn được giữ và loại collection đang dùng.

Không có kết luận phổ quát rằng `new T[0]`, `new T[size()]` hay dạng tham chiếu tạo mảng luôn nhanh nhất trên mọi JDK và mọi collection. Cách triển khai, tối ưu của JVM, kích thước dữ liệu và cách đo đều ảnh hưởng đến kết quả. Một đoạn mã đo thời gian quá ngắn hoặc bỏ qua kết quả có thể đo tối ưu của trình biên dịch nhiều hơn là chi phí chuyển đổi thực tế.

Ưu tiên cách viết diễn đạt đúng kiểu mảng và quyền sở hữu cần có. Chỉ chọn một cách phức tạp hơn vì hiệu năng sau khi có số đo phù hợp với đường chạy thực sự.

### 9.6. Quan sát nội dung mảng bằng công cụ đúng

Các ví dụ dùng `Arrays.toString` để hiển thị các ô mảng. In thẳng đối tượng mảng bằng `System.out.println(array)` thường hiển thị dạng nhận diện của đối tượng, không phải dãy phần tử dễ đọc.

Tương tự, khi cần so sánh nội dung hai mảng một chiều, dùng phép so sánh phù hợp như `Arrays.equals` thay vì coi `array1.equals(array2)` là so sánh từng ô. Chuyển đổi đúng nhưng quan sát/so sánh sai cách có thể khiến quá trình kiểm tra đưa ra kết luận sai.

## 10. Thực hành để tự kiểm tra

### Bài 1: Giữ kết quả khi mảng quá nhỏ

Tạo list ba chuỗi và mảng đích một ô. Gọi `toArray` một lần có giữ kết quả, một lần bỏ kết quả.

**Điểm cần giải thích:** mảng không tăng độ dài tại chỗ. Kết quả đầy đủ nằm trong mảng được trả về khi bộ đệm chưa đủ. Mã bỏ kết quả chỉ có vẻ hoạt động nếu vô tình rơi vào nhánh tái sử dụng.

### Bài 2: Phân biệt dấu null với dữ liệu null

Tạo collection có ba phần tử, trong đó phần tử thứ hai là `null`. Cung cấp mảng năm ô đã có giá trị cũ, rồi quan sát toàn bộ mảng.

**Điểm cần giải thích:** có một `null` thuộc dữ liệu và một `null` ngay sau ba phần tử. Không được dùng vị trí `null` đầu tiên để đo kích thước dữ liệu. Các ô ngoài vùng dữ liệu không tự trở thành phần tử mới của collection.

### Bài 3: Thay kiểu khai báo nhưng giữ kiểu mảng thực tế

Khai báo `Number[] buffer = new Integer[0]`, rồi thử xuất một collection chứa `Integer` và `Double` vào `buffer`. Sau đó thay bằng `new Number[0]`.

**Điểm cần giải thích:** giới hạn lưu trữ nằm ở đối tượng mảng thực tế. Kiểu khai báo rộng hơn không biến mảng số nguyên thành mảng số tổng quát.

### Bài 4: Tách thay ô khỏi sửa đối tượng phần tử

Dùng một list đối tượng có trường thay đổi được. Nhận mảng bằng hàm tạo mới, sửa trường qua một ô rồi thay ô khác bằng đối tượng mới.

**Điểm cần giải thích:** sửa trạng thái của đối tượng đang được chia sẻ khác với thay một tham chiếu trong cấu trúc chứa. `toArray` không tự sao chép sâu các phần tử.

### Bài 5: Truy tìm vì sao kết quả vẫn chia sẻ ô với list

Dùng `Arrays.asList(backing)`, rồi so sánh kết quả của `toArray(backing)` với `toArray(String[]::new)`.

**Điểm cần giải thích:** ở lời gọi đầu, bên gọi đã cung cấp chính mảng đang hậu thuẫn list và nó đủ chỗ, nên tái sử dụng giữ lại quan hệ chia sẻ. Ở lời gọi thứ hai, hàm tạo cấp mảng mới. Dù các ô đã tách biệt, loại phần tử vẫn quyết định liệu trạng thái đối tượng có thể được chia sẻ hay không.

### Bài 6: Giải thích đối số 0 của hàm tạo

Chạy phần `inheritedDefault` trong chương trình thứ ba. Thử thay dữ liệu bằng một list rỗng và một list nhiều phần tử hơn, nhưng vẫn tạo mảng theo độ dài mà lambda nhận.

**Điểm cần giải thích:** phương thức mặc định của `Collection` dùng mảng được tạo từ đối số `0` để đi tiếp vào overload nhận mảng. Không cần tự lấy `size()` bên ngoài hàm tạo để “sửa” cơ chế này.

Một cách chọn lời gọi vững chắc là đọc theo thứ tự: **kiểu mảng API đích cần → mảng thực tế được tạo/cung cấp → quy tắc kích thước → khả năng chia sẻ tham chiếu → chính sách thứ tự và truy cập của collection**.
