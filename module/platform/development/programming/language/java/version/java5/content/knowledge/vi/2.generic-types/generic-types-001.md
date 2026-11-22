# Generics và vấn đề an toàn kiểu khi tái sử dụng mã

## 1. Tái sử dụng được chưa có nghĩa là giữ đúng kiểu

Giả sử cần một hộp lưu một giá trị. Ta muốn dùng cùng một cơ chế cho chuỗi, số hoặc một đối tượng nghiệp vụ, thay vì viết lại một lớp gần giống nhau cho từng loại.

Một thiết kế nhận `Object` có thể chứa nhiều loại đối tượng, nhưng khi lấy lại, người gọi chỉ biết kết quả có kiểu `Object`. Nếu người gọi cần `String`, họ phải ép kiểu và tự chịu trách nhiệm về giả định đó.

**Vấn đề:** cơ chế lưu có thể tái sử dụng, nhưng quan hệ “đưa kiểu nào vào thì lấy kiểu đó ra” chưa được diễn tả trong chữ ký.

Generics đưa quan hệ đó vào hệ thống kiểu:

```java
Box<String> title;
Box<Integer> count;
```

Cùng một định nghĩa `Box<T>` có thể phục vụ nhiều kiểu, còn mỗi cách sử dụng vẫn giữ thông tin kiểu cụ thể để trình biên dịch kiểm tra.

Đó là ý nghĩa chính của **an toàn kiểu khi tái sử dụng mã**: tổng quát hóa phần cơ chế nhưng không buộc mọi nơi sử dụng phải mất hợp đồng kiểu của dữ liệu.

## 2. Những từ cần phân biệt

| Thuật ngữ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Kiểu tổng quát, thường gọi generic type | `Box<T>` | Định nghĩa có tham số kiểu |
| Tham số kiểu | `T` trong khai báo `class Box<T>` | Tên đại diện cho một kiểu ở định nghĩa |
| Đối số kiểu | `String` trong `Box<String>` | Kiểu cụ thể được chọn khi dùng |
| Kiểu được tham số hóa | `Box<String>` | Một cách dùng generic type với đối số kiểu |
| Phương thức generic | `<T> T first(List<T> values)` | Phương thức khai báo tham số kiểu riêng |
| An toàn kiểu | Không cho đưa `Integer` vào nơi yêu cầu `String` | Bảo vệ các quan hệ kiểu theo hợp đồng |

`T` không phải một biến chứa đối tượng `Class` lúc chạy. Nó là tên trong định nghĩa kiểu, được trình biên dịch dùng để kiểm tra quan hệ giữa các phần của API.

Các tên `T`, `E`, `K`, `V` thường dùng cho type, element, key và value. Đó là quy ước đặt tên; ý nghĩa thực tế phải xem chữ ký và tài liệu.

Theo [đặc tả kiểu của Java hiện hành](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.5), kiểu được tham số hóa là một phần của mô hình kiểu tĩnh. Kiến thức này vẫn áp dụng khi viết Java hiện đại, dù nền tảng generics có từ Java 5.

## 3. Vì sao chỉ dùng Object không diễn tả đủ hợp đồng?

Một hộp minh họa:

```java
final class ObjectBox {
    private final Object value;

    ObjectBox(Object value) {
        this.value = value;
    }

    Object value() {
        return value;
    }
}
```

`ObjectBox` có thể chứa chuỗi hoặc số. Việc đó không sai nếu mục đích thật sự là chứa giá trị tùy loại và nơi dùng biết cách phân loại. `Object` vẫn là kiểu hợp lệ trong Java hiện đại.

Nhưng nếu ý định là một hộp mà kiểu đầu vào phải được giữ rõ ở đầu ra, chữ ký này làm mất quan hệ:

```java
ObjectBox box = new ObjectBox(42);
String text = (String) box.value();
```

Phép ép kiểu nói với chương trình “hãy coi đối tượng này là `String`”. Nó không biến một `Integer` thành chuỗi. Kết quả là `ClassCastException` lúc chạy.

Trình biên dịch không thấy lỗi thiết kế ở đây vì `value()` chỉ hứa trả `Object`; phép ép kiểu từ `Object` sang `String` là một khả năng cần kiểm tra lúc chạy.

Đối chiếu này nhằm giải thích một giới hạn vẫn hiện hành của chữ ký `Object`, không phải khuyến khích viết API mới bằng các cơ chế mất kiểm tra kiểu. Nếu API biết quan hệ kiểu cần giữ, hãy mô tả nó ngay.

## 4. Generics giữ cùng một T ở các vị trí liên quan

Thiết kế lại:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}
```

Khi dùng `Box<String>`, chữ ký được hiểu ở mức kiểm tra kiểu là:

- Constructor nhận giá trị phù hợp `String`.
- Trường giá trị được sử dụng theo `String`.
- `value()` trả `String`.

Khi dùng `Box<Integer>`, cùng cơ chế áp dụng cho `Integer`. Không phải viết thêm một lớp hộp số có cùng thuật toán.

```java
Box<String> title = new Box<>("Generics");
String text = title.value();
```

Không cần một phép ép kiểu do người dùng viết khi lấy giá trị. Quan trọng hơn, đầu vào sai bị phát hiện sớm:

```java
// Khong bien dich:
Box<String> invalid = new Box<>(42);
```

Dấu `<>` ở vế tạo đối tượng là diamond, được bổ sung sau Java 5. Nó giúp suy luận đối số kiểu, không thay đổi mục tiêu của generics: giữ quan hệ kiểu rõ ràng. Trong bài, mã chạy với Java 17+ và dùng các tiện ích hiện đại phù hợp.

### 4.1. T không có nghĩa “chấp nhận mọi kiểu tại mọi lời gọi”

Một `Box<String>` không đổi thành `Box<Integer>` chỉ vì lần sau muốn cất số. Kiểu đã chọn ràng buộc cách dùng cụ thể đó.

Tính tổng quát nằm ở định nghĩa có thể được dùng với nhiều đối số kiểu, còn tính an toàn nằm ở mỗi cách sử dụng vẫn tuân thủ đối số kiểu đã chọn.

### 4.2. Không tự động cho T mọi phương thức của mọi đối tượng

Trong định nghĩa `Box<T>` không có giới hạn, ta không thể gọi `value.length()` như thể mọi `T` đều là `String`. Phần cài đặt phải đúng với các kiểu được phép bởi chữ ký.

Nếu một thuật toán cần thao tác đặc biệt, API có thể cần giới hạn kiểu, một giao diện khả năng hoặc một hàm được truyền vào. Không dùng ép kiểu tùy tiện bên trong để giả vờ một thuật toán hỗ trợ mọi `T`.

Bài tập trung vào lý do và hợp đồng cơ bản; giới hạn kiểu và truyền hành vi là bước thiết kế tiếp theo khi nhu cầu thật sự xuất hiện.

## 5. Phương thức generic tái sử dụng một quan hệ

Xét hàm lấy phần tử đầu:

```java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("Empty list");
    }
    return values.get(0);
}
```

`<T>` trước kiểu trả về khai báo tham số kiểu của chính phương thức. Cùng `T` xuất hiện ở `List<T>` và kết quả trả về, nên chữ ký nói rằng phần tử đầu có kiểu liên quan tới kiểu phần tử của danh sách.

```java
String firstName = first(List.of("An", "Binh"));
Integer firstScore = first(List.of(8, 9));
```

Cùng một mã lấy phần tử phục vụ hai loại dữ liệu mà không trả một `Object` buộc mỗi người gọi tự ép kiểu.

Điều generics không nói ở chữ ký cơ bản này là danh sách có rỗng hay không. Chương trình phải kiểm tra và quyết định báo lỗi, trả `Optional<T>` hoặc một hợp đồng khác. Kiểu tổng quát và tính hợp lệ nghiệp vụ là hai lớp trách nhiệm khác nhau.

Không khai báo `<T>` chỉ để có một chữ T trong API. Nó có giá trị khi các vị trí kiểu được nối với nhau hoặc khi thuật toán được ràng buộc theo một kiểu có ý nghĩa.

## 6. Chương trình Java 17+ đầy đủ

Lưu thành `GenericReuseSafetyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class GenericReuseSafetyDemo {
    static final class ObjectBox {
        private final Object value;

        ObjectBox(Object value) {
            this.value = value;
        }

        Object value() {
            return value;
        }
    }

    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = Objects.requireNonNull(value);
        }

        T value() {
            return value;
        }
    }

    static <T> T first(List<T> values) {
        Objects.requireNonNull(values);
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        return values.get(0);
    }

    public static void main(String[] args) {
        ObjectBox unknown = new ObjectBox(42);
        try {
            String wrongAssumption = (String) unknown.value();
            System.out.println(wrongAssumption);
        } catch (ClassCastException ex) {
            System.out.println("Object assumption -> "
                    + ex.getClass().getSimpleName());
        }

        Box<String> title = new Box<>("Generics");
        Box<Integer> count = new Box<>(3);
        String heading = title.value();
        int number = count.value();
        System.out.println("typed title = " + heading);
        System.out.println("typed count = " + number);

        List<String> names = List.of("An", "Binh");
        List<Integer> scores = List.of(8, 9);
        String firstName = first(names);
        int firstScore = first(scores);
        System.out.println("first name = " + firstName);
        System.out.println("first score = " + firstScore);

        List<Object> mixed = List.of("text", 7);
        System.out.println("explicit mixed list = " + mixed);

        List<String> mutable = new ArrayList<>(List.of("generics"));
        Box<List<String>> collectionBox = new Box<>(mutable);
        mutable.add("type safety");
        System.out.println("same referenced list = "
                + collectionBox.value());

        List<String> nullableElements = new ArrayList<>();
        nullableElements.add(null);
        System.out.println("generic list can contain null = "
                + (nullableElements.get(0) == null));

        System.out.println("same runtime class = "
                + title.getClass().equals(count.getClass()));

        try {
            new Box<String>(null);
        } catch (NullPointerException ex) {
            System.out.println("Box null policy -> "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked GenericReuseSafetyDemo.java
java GenericReuseSafetyDemo
```

Stdout:

```text
Object assumption -> ClassCastException
typed title = Generics
typed count = 3
first name = An
first score = 8
explicit mixed list = [text, 7]
same referenced list = [generics, type safety]
generic list can contain null = true
same runtime class = true
Box null policy -> NullPointerException
```

Chương trình gồm cả tình huống ép kiểu sai có chủ đích và các cách sử dụng đúng:

- `ObjectBox` minh họa nơi một giả định kiểu chỉ bị phát hiện lúc chạy.
- `Box<String>` và `Box<Integer>` giữ kết quả đúng kiểu tại nơi gọi.
- `first` dùng lại cùng một thuật toán cho hai loại danh sách.
- Các dòng sau chứng minh những điều generics không tự bảo đảm.

`Objects.requireNonNull` trong constructor `Box` là **chính sách bổ sung của lớp**, không phải tính năng tự động của `T`. Vì thế, đầu vào `null` bị từ chối ở lớp này, trong khi một `ArrayList<String>` vẫn có thể chấp nhận phần tử `null`.

`List.of` là API được thêm sau nền tảng generics; nó được dùng trong ví dụ hiện đại để tạo dữ liệu. Không suy rằng mọi API trong chương trình có cùng mốc với Java 5.

## 7. Kiểm chứng lỗi kiểu ở thời điểm biên dịch

Sau khi có tệp chương trình chính, tạo tệp riêng `RejectWrongType.java`:

```java
public class RejectWrongType {
    public static void main(String[] args) {
        GenericReuseSafetyDemo.Box<String> box =
                new GenericReuseSafetyDemo.Box<>(42);
    }
}
```

Chạy:

```shell
javac --release 17 RejectWrongType.java
```

Đây là phép thử **dự kiến thất bại**. Mã chương trình chính đã được biên dịch trước và các tệp nằm cùng thư mục.

Lý do lỗi: vế trái yêu cầu `Box<String>` nhưng đối số `42` cần một kiểu phù hợp với `Integer` sau boxing. Trình biên dịch không thể suy ra một `T` thỏa cả hợp đồng đã nêu.

Thông báo có thể khác theo phiên bản hoặc ngôn ngữ trình biên dịch, nhưng ý cốt lõi là các ràng buộc kiểu không tương thích. Không cần chạy chương trình lỗi để biết nó vi phạm hợp đồng.

Đừng “sửa” phép thử bằng việc xóa đối số kiểu hoặc ép qua một kiểu không được kiểm tra. Mục tiêu là giữ kiểm tra sớm, không chỉ làm tệp nguồn biên dịch bằng mọi giá.

## 8. List<Object> không có nghĩa “danh sách của một kiểu bất kỳ”

Một `List<Object>` có thể nhận nhiều đối tượng khác loại:

```java
List<Object> values = new ArrayList<>();
values.add("text");
values.add(7);
```

Đây là hợp đồng rõ ràng nếu yêu cầu thật sự là danh sách các giá trị được nhìn dưới kiểu `Object`. Nó không tự mâu thuẫn về kiểu.

Ngược lại, một `List<String>` hứa rằng người gọi lấy phần tử theo `String`. Không thể tự coi nó là một `List<Object>` có quyền thêm số:

```java
List<String> names = new ArrayList<>();
// List<Object> objects = names; // Khong bien dich.
```

Nếu phép gán đó được cho phép, nơi dùng `objects` có thể thêm `Integer` vào chính danh sách mà nơi dùng `names` tin là chuỗi. Java ngăn đường phá vỡ hợp đồng này.

Quan hệ `String` là kiểu con của `Object` không kéo theo `List<String>` là kiểu con của `List<Object>`. Đây là điểm thiết yếu khi đọc tính an toàn của API generic.

Nếu cần một hàm nhận nhiều loại danh sách theo một vai trò cụ thể, có thể dùng wildcard phù hợp. Chẳng hạn một hàm chỉ đọc các giá trị số có thể cân nhắc `List<? extends Number>`. Nhưng phải học đúng quyền đọc/ghi của wildcard; không thay mọi `List<T>` bằng wildcard mà không biết mối liên hệ kiểu cần giữ.

## 9. An toàn kiểu không phải mọi loại an toàn

### 9.1. Không tự loại bỏ null

`List<String>` nói về kiểu phần tử theo hợp đồng, không mặc định nói mọi phần tử đều khác `null`. [List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html) có nhiều hiện thực với những chính sách khác nhau; chẳng hạn `ArrayList` và các factory không cho `null` có thể khác ở điểm này.

Nếu thuật toán gọi `name.length()`, phải xác định đầu vào có cho `null` không và thực thi chính sách tương ứng. Generics không tự làm phép gọi đó luôn an toàn.

Trong chương trình, `Box` từ chối giá trị `null` bằng kiểm tra lúc chạy. Đây là một ràng buộc có chủ đích của lớp.

### 9.2. Không tự tạo bất biến sâu

`Box<List<String>>` có thể giữ tham chiếu tới một danh sách có thể sửa. `final` trên trường hộp chỉ ngăn gán trường đó sang một tham chiếu khác; nó không ngăn đối tượng danh sách thay đổi.

Vì chương trình thêm `"type safety"` vào cùng danh sách, giá trị đọc qua hộp cũng thấy phần tử mới. Không có lỗi kiểu: cả hai phần tử đều là chuỗi.

Nếu cần ảnh chụp không đổi cấu trúc, lớp phải sao chép hoặc dùng cấu trúc phù hợp theo hợp đồng. Nếu phần tử bên trong cũng có thể sửa, việc chặn sửa cấu trúc danh sách vẫn chưa tự làm mọi phần tử bất biến.

### 9.3. Không tự tạo an toàn nhiều luồng

Một `List<String>` hoặc một lớp generic tùy biến không tự an toàn khi nhiều luồng cùng sửa. Tham số kiểu và bảo đảm đồng bộ là hai vấn đề riêng.

Không suy “kiểm tra kiểu mạnh” đồng nghĩa “mọi cách truy cập đều đúng”. Cần chọn cách sở hữu dữ liệu, bất biến hoặc cơ chế đồng bộ theo bài toán.

### 9.4. Không thay ràng buộc nghiệp vụ

`Box<Integer>` có thể chứa một số âm nếu lớp không cấm. `List<String>` có thể chứa chuỗi rỗng nếu API chấp nhận.

Nếu kiểu dữ liệu đang biểu diễn tuổi, số lượng hoặc mã đơn, các ràng buộc phạm vi và định dạng vẫn phải được kiểm tra hoặc đưa vào một kiểu miền phù hợp. Generics giữ loại dữ liệu; nó không suy ra toàn bộ ý nghĩa nghiệp vụ của một `Integer` hoặc `String`.

## 10. Thông tin kiểu lúc biên dịch và lúc chạy

Java triển khai generics với cơ chế xóa kiểu theo đặc tả. Trong ví dụ:

```java
Box<String> title = new Box<>("Generics");
Box<Integer> count = new Box<>(3);
```

hai đối tượng có cùng lớp chạy `Box`. Dòng `same runtime class = true` chứng minh điều đó với chương trình này.

Không nên hiểu `Box<String>` và `Box<Integer>` là hai lớp JVM độc lập được sinh riêng cho từng đối số kiểu.

Tuy nhiên, “xóa kiểu” cũng không có nghĩa mọi thông tin khai báo generic biến mất ở mọi nơi. Một số thông tin chữ ký có thể được lưu để công cụ hoặc reflection đọc theo hợp đồng. Điều không được giả định là mỗi đối tượng luôn mang một nhãn đầy đủ cho mọi đối số kiểu của nó.

Một vài hệ quả khi thiết kế:

- Không kiểm tra một đối tượng tùy ý bằng `instanceof List<String>`.
- Không trực tiếp tạo `new T()` chỉ từ tên tham số kiểu không ràng buộc.
- Không dùng generics như một cơ chế xác thực tự động cho dữ liệu từ JSON, cơ sở dữ liệu hoặc một nguồn không đáng tin.
- Không nghĩ một phép ép kiểu không được kiểm tra có thể thay việc xác thực phần tử thật.

Bài này không đi sâu mọi quy tắc xóa kiểu. Điểm quan trọng là bảo đảm kiểu được hình thành chủ yếu qua cách khai báo và sử dụng đúng hợp đồng, không nhờ một nhãn kiểm tra toàn bộ dữ liệu tự động lúc chạy.

## 11. Dùng generics ở đâu trong thiết kế tái sử dụng?

### 11.1. Khi thuật toán không phụ thuộc loại dữ liệu cụ thể

`Box<T>` chỉ giữ và trả cùng một giá trị. `first(List<T>)` chỉ chọn phần tử. Cả hai không cần biết đây là tên người hay điểm số.

Đây là nơi tham số kiểu có ý nghĩa: cơ chế chung thật sự dùng được cho nhiều loại dữ liệu, còn chữ ký giữ quan hệ kiểu của từng nơi dùng.

### 11.2. Khi nhiều vai trò kiểu cần được liên hệ

Ví dụ một cấu trúc `Map<K, V>` phân biệt kiểu khóa và kiểu giá trị. Nếu dùng một `Object` chung cho cả hai, người gọi dễ đảo vai trò mà chữ ký không diễn tả.

Một API của ứng dụng cũng có thể cần hai tham số kiểu nếu có hai vai trò thật sự độc lập. Không đặt một `T` cho mọi thứ chỉ vì chúng đều là đối tượng.

Ngược lại, nếu đầu vào và đầu ra phải là cùng một kiểu liên quan, dùng cùng tham số kiểu giúp trình biên dịch giữ quan hệ đó. Nếu tách thành hai tham số kiểu không liên hệ, API có thể không còn hứa điều người gọi cần.

### 11.3. Khi không nên tổng quát hóa

Nếu một thuật toán chỉ đúng cho một miền cụ thể như số tiền hoặc ngày nghiệp vụ, việc đổi hết thành `T` có thể che yêu cầu thay vì tăng tái sử dụng.

Câu hỏi nên đặt là “cơ chế nào thực sự giống nhau giữa các kiểu?” chứ không phải “làm thế nào thêm `<T>` vào lớp này?”. Một lớp generic không cần thiết có thể làm chữ ký phức tạp mà không bảo vệ thêm quan hệ hữu ích.

## 12. Cách đọc một API generic

Với một chữ ký chưa quen, đọc theo các bước:

1. Xác định các tham số kiểu được khai báo ở lớp hay phương thức.
2. Tìm nơi từng tham số xuất hiện ở đầu vào.
3. Tìm nơi nó xuất hiện ở kết quả.
4. Xác định quan hệ mà API đang giữ.
5. Đọc giới hạn kiểu hoặc wildcard nếu có.
6. Đọc riêng chính sách `null`, rỗng, sửa đổi dữ liệu và lỗi nghiệp vụ.

Ví dụ `<T> T first(List<T> values)`:

- `T` thuộc phương thức.
- Đầu vào là danh sách có phần tử theo `T`.
- Đầu ra là một `T` lấy từ danh sách đó.
- Chữ ký chưa nói cách xử lý danh sách rỗng hoặc phần tử `null`.
- Phần hiện thực/tài liệu phải bổ sung hai điều cuối.

Cách đọc này hữu ích với thư viện hiện đại như collection, kết quả tác vụ, pipeline dữ liệu hoặc các kiểu kết quả. Không cần thuộc lòng từng chữ cái; cần thấy quan hệ giữa các vị trí.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `Object` dù cần giữ một quan hệ kiểu rõ | Người gọi phải tự ép kiểu | Diễn tả quan hệ bằng tham số kiểu |
| Nghĩ `T` là một kiểu tự đổi ở mỗi thao tác trên cùng đối tượng | Hiểu sai ràng buộc của `Box<String>` | Phân biệt định nghĩa tổng quát và cách dùng cụ thể |
| Gọi phương thức riêng của `String` trên `T` bất kỳ | Cài đặt không đúng với mọi kiểu cho phép | Nêu khả năng cần thiết bằng thiết kế kiểu phù hợp |
| Gán `List<String>` sang `List<Object>` | Có thể phá quyền ghi và hợp đồng phần tử | Hiểu quan hệ kiểu của container |
| Coi generic type là bảo đảm không có `null` | Có thể lỗi ở nơi gọi phương thức | Chọn và thực thi chính sách `null` |
| Coi trường `final` làm mọi dữ liệu bên trong bất biến | Đối tượng tham chiếu vẫn bị sửa | Kiểm soát sao chép và tính có thể thay đổi |
| Bỏ cảnh báo hoặc dùng ép kiểu tùy tiện để hết lỗi | Làm mất bảo đảm ban đầu | Sửa quan hệ kiểu hoặc xác thực dữ liệu |
| Thêm `<T>` cho thuật toán chỉ đúng với một miền | Chữ ký tổng quát giả | Giữ kiểu miền hoặc ràng buộc phù hợp |
| Nghĩ generics tự kiểm tra mọi dữ liệu nhập lúc chạy | Lọt dữ liệu sai từ nguồn ngoài | Xác thực tại biên theo schema/hợp đồng |
| Nhầm API tiện ích hiện đại với mốc generics | Sai nguồn gốc tính năng | Tách cơ chế Java 5 với API bổ sung sau |

## 14. Tự kiểm chứng và thực hành

1. Trong `Box<T>`, chỉ ra ba vị trí cùng dùng `T` và giải thích quan hệ mà chúng giữ.
2. Chạy ví dụ và giải thích vì sao ép kiểu của `ObjectBox` lỗi lúc chạy, còn phép thử `Box<String>` nhận số lỗi lúc biên dịch.
3. Dùng `first` với danh sách một kiểu nghiệp vụ do bạn tự định nghĩa. Không thêm ép kiểu ở nơi lấy kết quả.
4. Thử danh sách rỗng với `first` và xác định hợp đồng hiện tại. Sau đó thiết kế một biến thể trả kết quả tùy chọn nếu nhu cầu thật sự muốn tránh ngoại lệ.
5. So sánh `List<Object>` có nhiều loại phần tử với `List<String>`. Giải thích vì sao cách đầu có thể đúng chủ đích nhưng không thay được cách sau khi cần hợp đồng chuỗi.
6. Thử một danh sách chứa `null` và phân biệt chính sách của collection với bảo đảm của generics.
7. Tạo `Box<List<String>>` rồi sửa danh sách gốc. Nếu muốn ảnh chụp không đổi cấu trúc, thiết kế một kiểu phù hợp và nêu rõ độ sâu bảo đảm.
8. Giải thích vì sao `title.getClass()` và `count.getClass()` bằng nhau trong chương trình nhưng trình biên dịch vẫn phân biệt `Box<String>` với `Box<Integer>`.
9. Nhìn một API có hai tham số kiểu như `Map<K, V>` và mô tả vai trò riêng của từng tham số.
10. Chọn một lớp đang định viết generic và trả lời cơ chế nào thật sự dùng lại được, quan hệ kiểu nào cần bảo vệ và ràng buộc nghiệp vụ nào còn phải kiểm tra riêng.

Generics giúp tái sử dụng mã mà vẫn giữ quan hệ kiểu tại nơi sử dụng. Lợi ích lớn nhất là biến một phần giả định của người gọi thành hợp đồng được trình biên dịch kiểm tra; các chính sách về dữ liệu thiếu, bất biến, đồng thời và nghiệp vụ vẫn cần được thiết kế rõ ràng bên cạnh hợp đồng đó.
