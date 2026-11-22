# Kiểm tra lỗi kiểu tại thời điểm biên dịch

## 1. Generic giúp phát hiện nhầm kiểu trước khi chạy

Giả sử một danh sách tên chỉ được phép chứa chuỗi. Khi khai báo `List<String>`, ta cung cấp cho trình biên dịch một hợp đồng: thao tác thêm phải nhận giá trị tương thích với `String`, còn thao tác đọc phần tử được kiểm tra với kiểu trả về `String`.

Nhờ đó, những nhầm lẫn như thêm một số vào danh sách tên hoặc gán tên đọc ra cho một biến `Integer` có thể bị chặn khi biên dịch. Lỗi xuất hiện gần vị trí vi phạm hợp đồng, trước khi chương trình xử lý dữ liệu thật.

Đây là **kiểm tra kiểu tĩnh** (static type checking): trình biên dịch dùng kiểu của biến, biểu thức, tham số và kết quả trả về để kiểm tra mã nguồn. Nó không cần chạy chương trình rồi quan sát các đối tượng trong danh sách.

```java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
```

Đoạn trên cần các import `java.util.List` và `java.util.ArrayList`, cùng một thân phương thức chứa các câu lệnh. Chương trình độc lập đầy đủ nằm ở mục 4.

Với biến `names`, `names.add(42)` bị từ chối vì số nguyên không tương thích với hợp đồng thêm chuỗi. Ngược lại, `names.get(0)` có kiểu tĩnh `String`, nên gán kết quả vào một biến `Integer` cũng bị từ chối.

Generic bảo vệ **quan hệ kiểu dữ liệu**, còn khả năng danh sách rỗng, phần tử bằng `null`, tên trùng nhau hoặc tên không hợp lệ vẫn cần xử lý theo quy tắc của ứng dụng.

## 2. Trình biên dịch kiểm tra những điểm nào?

| Điểm kiểm tra | Ví dụ hợp lệ | Điều cần khớp |
| --- | --- | --- |
| Tạo đối tượng generic | `new Box<String>("Java")` | Đối số hàm tạo phù hợp với kiểu đã chọn |
| Truyền dữ liệu vào | `box.set("Generics")` với `Box<String>` | Giá trị đầu vào tương thích với tham số |
| Đọc dữ liệu ra | `String text = box.get()` | Kiểu kết quả tương thích với biến nhận |
| Gọi phương thức | `first(names)` nhận `List<String>` | Kiểu đối số tương thích với chữ ký phương thức |
| Đối số kiểu có giới hạn | `asDouble(7)` với `<N extends Number>` | Kiểu suy luận thỏa mãn giới hạn |
| Gán tham chiếu | `List<String> x = new ArrayList<String>()` | Có quan hệ kiểu cho phép phép gán |
| Thân lớp/phương thức generic | `value.doubleValue()` với `N extends Number` | Thao tác được cho phép bởi giới hạn của biến kiểu |

Kiểm tra diễn ra cả ở nơi **định nghĩa** API lẫn nơi **sử dụng** API. Nếu khai báo `class Box<T>` không đặt giới hạn đặc biệt, thân lớp không được tự gọi `length()` trên một biến `T` chỉ vì một nơi sử dụng sẽ chọn `Box<String>`. `T` có thể là kiểu khác; trình biên dịch chỉ cho phép những thao tác được hợp đồng khai báo bảo đảm.

Tương tự, một phương thức `<N extends Number>` có thể gọi `doubleValue()` trên `N` vì giới hạn `Number` bảo đảm có phương thức ấy. Không thể truyền một chuỗi `"7"` vào rồi kỳ vọng trình biên dịch tự đổi nội dung chuỗi thành số.

Đối chiếu cơ sở kiểu tĩnh và thành viên của kiểu tham số hóa tại [JLS §4 và §4.5.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.2).

## 3. Kiểu tĩnh quyết định hợp đồng, không phải dự đoán ý định

### 3.1. Một lớp con của kiểu phần tử không làm đổi kiểu hộp

`String` là kiểu con của `Object`, nhưng `List<String>` không là kiểu con của `List<Object>`. Phép gán từ biến `List<String>` sang biến `List<Object>` bị từ chối.

Nếu cho phép phép gán ấy, biến thứ hai sẽ có quyền thêm một `Integer` vào cùng danh sách mà biến đầu tiên hứa chỉ chứa chuỗi. Việc từ chối bảo vệ hợp đồng của danh sách. Đây là tính bất biến (invariance) giữa các lần tham số hóa dùng những đối số kiểu cụ thể khác nhau.

Muốn danh sách chứa nhiều kiểu tham chiếu, có thể chọn `List<Object>` ngay từ đầu. Lúc ấy thêm chuỗi và số đều phù hợp, nhưng đọc phần tử chỉ được bảo đảm là `Object`; không thể mặc định gán trực tiếp kết quả đọc vào một biến `String`.

### 3.2. Suy luận kiểu không thay thế việc chọn đúng hợp đồng

```java
List<String> names = new ArrayList<>();
var mixed = new ArrayList<>();
```

Dòng đầu cung cấp kiểu đích để suy luận đối số của `ArrayList` là `String`. Dòng thứ hai không có ngữ cảnh chọn `String`; trong trường hợp này biến `mixed` có kiểu `ArrayList<Object>`. Vì vậy `mixed.add(42)` có thể biên dịch, dù người viết thầm muốn danh sách chỉ chứa tên.

Trình biên dịch kiểm tra hợp đồng thực sự được khai báo hoặc suy luận. Nó không đọc tên biến hay ý định trong đầu người viết. Khi kiểu phần tử là yêu cầu quan trọng, hãy thể hiện rõ yêu cầu ấy trong khai báo.

### 3.3. Một đối tượng có kiểu cụ thể không tự làm biến tham chiếu cụ thể hơn

```java
Object text = "Java";
// int length = text.length(); // Lỗi biên dịch nếu bỏ dấu chú thích
```

Đối tượng lúc chạy là một chuỗi, nhưng biểu thức `text` có kiểu tĩnh `Object`. Không thể gọi `length()` qua kiểu đó. Với generic cũng vậy: tập thao tác được phép phải suy ra từ kiểu tĩnh, không phải từ điều ta biết riêng về một giá trị trong lần chạy dự kiến.

## 4. Chương trình hợp lệ chạy đầy đủ

Lưu thành `CompileTimeSafetyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CompileTimeSafetyDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    static String first(List<String> values) {
        return values.get(0);
    }

    static <N extends Number> double asDouble(N value) {
        return value.doubleValue();
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Binh");
        System.out.println("first=" + first(names));

        Box<String> title = new Box<>("Java");
        title.set("Generics");
        String text = title.get();
        System.out.println("title=" + text);

        System.out.println("number=" + asDouble(7));

        List<Object> mixed = new ArrayList<>();
        mixed.add("book");
        mixed.add(2);
        Object item = mixed.get(1);
        System.out.println("mixed=" + mixed);
        System.out.println("item=" + item);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 -Xlint:all -Werror CompileTimeSafetyDemo.java
java CompileTimeSafetyDemo
```

Stdout:

```text
first=An
title=Generics
number=7.0
mixed=[book, 2]
item=2
```

Các kiểu được giữ xuyên suốt đường dữ liệu: `first` nhận danh sách chuỗi và trả chuỗi; `Box<String>` nhận/lưu/trả chuỗi; `asDouble` nhận một giá trị có kiểu thỏa mãn `Number` sau đóng hộp. Với `List<Object>`, việc có nhiều kiểu phần tử là hợp đồng được chọn có chủ ý.

`-Xlint:all` bật các nhóm cảnh báo của `javac`; `-Werror` khiến bước biên dịch thất bại nếu có cảnh báo. Đây là lựa chọn kiểm tra của bài thực hành, giúp tránh bỏ qua các cảnh báo an toàn kiểu. Nó không biến mọi lỗi chỉ xảy ra lúc chạy thành lỗi biên dịch.

## 5. Thực hành các lỗi bị từ chối khi biên dịch

Tạo tệp **riêng** `TypeErrorsDemo.java`. Đây là ví dụ cố ý sai, không ghép vào chương trình hợp lệ ở mục 4:

```java
import java.util.ArrayList;
import java.util.List;

public class TypeErrorsDemo {
    static String first(List<String> values) {
        return values.get(0);
    }

    static <N extends Number> double asDouble(N value) {
        return value.doubleValue();
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add(42);                       // A: sai kieu phan tu
        Integer firstName = names.get(0);    // B: sai kieu bien nhan
        String result = first(List.of(1, 2));// C: sai doi so phuong thuc
        double number = asDouble("7");       // D: khong thoa gioi han
    }
}
```

Chạy lệnh sau để quan sát chẩn đoán:

```shell
javac --release 17 -Xlint:all -Xdiags:verbose TypeErrorsDemo.java
```

Lệnh thất bại vì các vi phạm kiểu sau. Không chạy `java TypeErrorsDemo` sau bước biên dịch thất bại.

- **A — Đầu vào không tương thích:** `List<String>.add` cần một `String` tương thích; giá trị `42` không đáp ứng điều đó. Tự đóng hộp tạo `Integer`, không tạo `String`.
- **B — Biến nhận không tương thích:** `names.get(0)` có kiểu tĩnh `String`, không thể gán cho `Integer`.
- **C — Hợp đồng đối số không khớp:** `first` yêu cầu `List<String>`, còn các số `1`, `2` trong `List.of` không tạo thành danh sách chuỗi tương thích với yêu cầu này.
- **D — Không thỏa mãn giới hạn:** kiểu của `"7"` là `String`, không thỏa mãn điều kiện `N extends Number`.

Thông báo cụ thể có thể khác theo phiên bản JDK hoặc ngôn ngữ hiển thị. Các từ như `required`, `found`, `incompatible types`, `inference variable` hoặc `bounds` giúp lần về hợp đồng bị vi phạm. Chẩn đoán phức tạp không có nghĩa lỗi nằm ở bộ suy luận; thường cần nhìn lại kiểu mong muốn và kiểu thực tế.

Cách sửa phải xuất phát từ ý nghĩa dữ liệu: nếu danh sách thật sự chứa tên thì cung cấp chuỗi; nếu dữ liệu thật sự là số thì chọn một mô hình số phù hợp. Không đổi toàn bộ thành `Object` hoặc thêm ép kiểu chỉ để làm thông báo biến mất.

## 6. Phân biệt lỗi biên dịch, cảnh báo và lỗi lúc chạy

| Tình huống | Kết quả mặc định | Ý nghĩa |
| --- | --- | --- |
| Thêm số vào `List<String>` | Lỗi biên dịch | Vi phạm hợp đồng kiểu có thể chứng minh từ mã nguồn |
| Ép `Object` thành `List<String>` mà không chứng minh được kiểu phần tử | Cảnh báo ép kiểu không được kiểm tra đầy đủ | Trình biên dịch không có đủ bảo đảm cho toàn bộ kiểu tham số hóa |
| Lấy phần tử ở vị trí không tồn tại | Có thể lỗi lúc chạy | Chỉ số phụ thuộc dữ liệu/trạng thái danh sách |
| Mở hộp `Integer` bằng `null` sang `int` | Có thể lỗi lúc chạy | Đúng kiểu tham chiếu không có nghĩa giá trị khác `null` |
| Truyền chuỗi sai định dạng vào `Integer.valueOf` | Có thể lỗi lúc chạy | Kiểu đầu vào là `String` hợp lệ nhưng nội dung không biểu diễn số |

### 6.1. Cảnh báo `unchecked` cần được xử lý

Ví dụ sau cố ý dùng ép kiểu không an toàn để thấy giới hạn bảo đảm. Lưu riêng thành `UncheckedCastDemo.java`:

```java
import java.util.List;

public class UncheckedCastDemo {
    public static void main(String[] args) {
        Object source = List.of(42);
        List<String> names = (List<String>) source;
        String first = names.get(0);
        System.out.println(first);
    }
}
```

Với lệnh:

```shell
javac --release 17 -Xlint:unchecked UncheckedCastDemo.java
java UncheckedCastDemo
```

Trình biên dịch báo cảnh báo `unchecked cast` ở phép ép từ `Object` sang `List<String>`, nhưng nếu không dùng `-Werror` thì vẫn cho phép tạo mã chạy. Khi chạy ví dụ này, chương trình không có stdout thành công; nó ném `ClassCastException` khi lấy phần tử đầu tiên làm `String`, vì phần tử thực tế là `Integer`.

Phép ép kiểu không đi qua từng phần tử để biến danh sách số thành danh sách chuỗi hoặc chứng minh toàn bộ phần tử là chuỗi. Một số thông tin đối số kiểu không sẵn có để JVM kiểm tra trực tiếp theo cách đó; cơ chế xóa kiểu (type erasure) là lý do cần phân biệt kiểm tra kiểu tĩnh với kiểm tra lúc chạy.

Có thể kiểm tra lại với chế độ chặn cảnh báo:

```shell
javac --release 17 -Xlint:unchecked -Werror UncheckedCastDemo.java
```

Lần này bước biên dịch thất bại vì có cảnh báo. Thêm `@SuppressWarnings("unchecked")` chỉ tắt chẩn đoán được chọn; nó không kiểm tra dữ liệu và không làm phép ép trở nên an toàn.

Cách xử lý khi nhận dữ liệu kiểu `Object` là kiểm tra cấu trúc thực tế và chuyển từng phần tử sang một danh sách mới đúng kiểu, hoặc thiết kế API đầu vào trả về kiểu cụ thể ngay từ đầu. Không dùng phép ép cả danh sách làm công cụ chuyển đổi dữ liệu.

Đối chiếu phép chuyển kiểu không được kiểm tra đầy đủ tại [JLS §5.1.6.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.6.2), và các tùy chọn cảnh báo tại [tài liệu lệnh javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).

### 6.2. Biên dịch thành công không bảo đảm chương trình đúng mọi mặt

Generic không chứng minh rằng danh sách có phần tử trước khi gọi `get(0)`, số tiền dương, người dùng có quyền xem dữ liệu hay một hàm chuyển đổi không ném ngoại lệ. Kiểu là một lớp hợp đồng quan trọng, nhưng chỉ là một phần của tính đúng đắn.

Vì vậy cần kết hợp khai báo kiểu chính xác với kiểm tra điều kiện đầu vào, xử lý trường hợp rỗng/`null` phù hợp và kiểm thử hành vi. Một kiểm thử chạy qua vài dữ liệu cũng không thay thế kiểm tra kiểu cho mọi nơi sử dụng API.

## 7. Cách đọc và sửa một chẩn đoán generic

1. **Xác định biểu thức bị chỉ ra.** Đó là giá trị đang truyền vào, kết quả đang gán hay một đối số kiểu không thỏa mãn giới hạn?
2. **Đọc kiểu yêu cầu từ khai báo.** Ví dụ phương thức nhận `List<String>` hoặc tham số kiểu yêu cầu `N extends Number`.
3. **Tìm kiểu tĩnh của biểu thức thực tế.** Theo dõi cả kiểu được suy luận từ `<>`, `var`, hàm generic và đối số truyền vào.
4. **Kiểm tra quan hệ cần có.** Đừng tự suy ra `List<String>` là kiểu con của `List<Object>`, hoặc tự coi hai tham số `T`, `U` độc lập là cùng kiểu.
5. **Sửa hợp đồng hoặc dữ liệu theo ý nghĩa.** Giữ kiểu hẹp khi nghiệp vụ yêu cầu kiểu hẹp; chỉ mở rộng kiểu khi mô hình dữ liệu thực sự cho phép.
6. **Biên dịch lại và đọc cảnh báo còn lại.** Dùng thử nghiệm tối giản nếu chẩn đoán lan qua nhiều lời gọi; không dựa vào lớp `.class` cũ từ lần biên dịch trước.

Việc biên dịch thất bại không phải một bước chạy thử thất bại. Không cần chờ người dùng mở màn hình hoặc chương trình đọc tệp rồi mới phát hiện các lỗi kiểu mà `javac` đã xác định được.

## 8. Tự kiểm tra

1. Vì sao `List<String>` có thể ngăn việc thêm `42` mà chưa cần chạy chương trình?
2. Với `Box<String>`, gán `box.get()` cho `Integer` lỗi ở thời điểm nào?
3. `var items = new ArrayList<>(); items.add(42);` biên dịch được có phải generic bị bỏ qua không?
4. `@SuppressWarnings("unchecked")` có làm một phép ép kiểu kiểm tra từng phần tử không?
5. Một chương trình dùng generic và không có cảnh báo còn có thể ném `IndexOutOfBoundsException` không?

Đáp án:

1. Kiểu tham số của thao tác thêm đã được xác định theo đối số `String`; giá trị số không tương thích với hợp đồng đó.
2. Khi biên dịch, vì kết quả được kiểm tra theo kiểu `String`.
3. Không. Kiểu được suy luận trong trường hợp này là `ArrayList<Object>`, nên thêm số phù hợp với hợp đồng thực tế.
4. Không. Nó chỉ tắt nhóm cảnh báo được chọn, không thêm kiểm tra dữ liệu hay chuyển đổi phần tử.
5. Có. Chỉ số nằm ngoài giới hạn là vấn đề dữ liệu/trạng thái lúc chạy, không bị loại bỏ chỉ bởi kiểu phần tử.

Khi thiết kế một API generic, hãy làm cho kiểu đầu vào, kiểu lưu trữ và kiểu đầu ra thể hiện đúng quan hệ dữ liệu. Hợp đồng càng chính xác thì trình biên dịch càng có cơ sở chặn nhầm lẫn trước khi mã được chạy.
