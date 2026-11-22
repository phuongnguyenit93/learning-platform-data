# Dùng ngoại lệ để che việc kiểm tra điều kiện đơn giản — sai lầm thường gặp trong Java

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận ra anti-pattern **dùng exception để điều khiển luồng xử lý bình thường** (*exception-driven control flow*), nhất là khi chỉ cần một điều kiện đơn giản.
- Phân biệt **trạng thái dự kiến trong nghiệp vụ** với **vi phạm hợp đồng/lỗi bất thường** cần ném ngoại lệ.
- Thay những khối `try/catch` quá rộng bằng guard clause, điều kiện rõ nghĩa, `Optional`, kết quả có cấu trúc hoặc API thao tác trực tiếp khi thích hợp.
- Biết khi nào việc **bắt exception lại là cách đúng**, chẳng hạn xử lý đầu vào cho `Integer.parseInt()`, thất bại I/O hay vi phạm tiền điều kiện công khai.
- Hiểu rủi ro **check-then-act** và *time-of-check to time-of-use (TOCTOU)*: kiểm tra trước không loại bỏ race condition hoặc ngoại lệ của thao tác thực tế.
- Giữ nguyên thông tin lỗi khi cần chuyển đổi ngoại lệ, tránh bắt `NullPointerException` hoặc `IndexOutOfBoundsException` chỉ để che lỗi lập trình.
- Đánh giá tác động đến hiệu năng, khả năng đọc, chẩn đoán và hợp đồng API một cách cân bằng.

Bài sử dụng Java 17+, tập trung vào Java Core Exception; ví dụ có thể biên dịch/chạy độc lập được ghi rõ tên tệp, lệnh chạy và stdout dự kiến.

## 2. Anti-pattern là gì?

Một chương trình có thể **chủ động thực hiện thao tác mà mình biết thường sẽ thất bại** rồi dựa vào exception để chọn nhánh bình thường, trong khi điều kiện quyết định đã có sẵn và có API để đọc rõ ràng.

Ví dụ: lấy phần tử đầu tiên của một danh sách, chấp nhận danh sách rỗng là trường hợp nghiệp vụ hợp lệ.

Cách viết dựa vào exception:

~~~java
String firstOrDefault(List<String> names) {
    try {
        return names.get(0);
    } catch (IndexOutOfBoundsException e) {
        return "Không có tên";
    }
}
~~~

Đây là **mã minh họa nằm trong lớp có import `java.util.List`**. Nếu danh sách rỗng, `get(0)` ném exception; code bắt nó rồi trả về giá trị mặc định.

Trong trường hợp này, danh sách rỗng là một **trạng thái dữ liệu dự kiến**, không phải sự cố. API của `List` đã cung cấp `isEmpty()`, nên điều kiện có thể biểu đạt trực tiếp:

~~~java
String firstOrDefault(List<String> names) {
    if (names.isEmpty()) {
        return "Không có tên";
    }
    return names.get(0);
}
~~~

Đây cũng là **mã minh họa**, cùng hợp đồng đầu vào như đoạn trước. Cách sau cho người đọc thấy ngay ý định: “Không có phần tử thì dùng giá trị mặc định”. Không phải đọc tên exception và phân tích đường lỗi mới hiểu được hành vi bình thường.

**Điều quan trọng:** câu “đừng dùng ngoại lệ khi chỉ cần kiểm tra điều kiện” không có nghĩa **mọi** ngoại lệ phải bị loại khỏi code. Ngoại lệ vẫn rất có giá trị để báo vi phạm hợp đồng, thất bại I/O, lỗi hạ tầng và những vấn đề người gọi cần xử lý ở tầng thích hợp.

## 3. Phân biệt ba loại tình huống

Một cách thiết kế hữu ích là hỏi: “Trạng thái này có phải một kết quả bình thường mà caller được phép gặp không?”

| Tình huống | Ý nghĩa | Hình thức thường phù hợp |
| --- | --- | --- |
| Danh sách có thể rỗng và đây là điều bình thường | Không có giá trị tại thời điểm tra cứu | `isEmpty()`, `Optional` hoặc kết quả rỗng |
| Map có thể không chứa khóa | Không tìm thấy ánh xạ | `get`, `containsKey`, `getOrDefault` theo ngữ nghĩa null |
| Input người dùng có thể sai định dạng số | Sai cú pháp theo parser được chọn | Bắt **`NumberFormatException` cụ thể** tại ranh giới parse và chuyển thành kết quả validation |
| Hàm yêu cầu số lượng dương theo hợp đồng | Caller vi phạm tiền điều kiện | Guard rồi ném `IllegalArgumentException` có ý nghĩa |
| Mở file có thể thất bại vì quyền truy cập, bị xóa hoặc lỗi thiết bị | Thao tác tài nguyên có thể thất bại độc lập việc kiểm tra trước | Gọi API thực tế và xử lý `IOException` theo hợp đồng |
| Truy cập array sai chỉ số do bug thuật toán | Lỗi lập trình | Sửa thuật toán; không tự động bắt rồi trả giá trị giả |
| Gọi API từ xa gặp timeout | Lỗi bên ngoài và có thể chưa rõ tác dụng phụ đã xảy ra | Timeout/cancellation, retry hoặc báo lỗi theo giao thức, không chỉ kiểm tra “mạng có sẵn” trước |
| Dữ liệu nghiệp vụ thiếu nhưng được phép | Một nhánh thông thường | Return type diễn đạt thiếu dữ liệu, không dùng throw/catch cho mọi trường hợp |

Cách phân loại phụ thuộc **hợp đồng API**. “Không tìm thấy” có thể là trạng thái bình thường của một hàm `find`, nhưng là vi phạm quy trình của hàm `requireExisting`. Hai hàm có thể dùng cách xử lý khác nhau mà đều đúng nếu tên, chữ ký và tài liệu của chúng nhất quán.

## 4. Vì sao try/catch không nên là if/else trá hình?

Một khối `catch` biểu đạt đường xử lý ngoại lệ. Khi biến nó thành nhánh bình thường cho một điều kiện đơn giản, có thể tạo các vấn đề:

1. **Ý định không rõ ràng.** Người đọc phải hiểu exception nào có thể phát sinh mới đoán được nhánh nghiệp vụ.
2. **Dễ che lỗi lập trình.** `catch (NullPointerException)` có thể nuốt NPE từ một lỗi logic khác trong cùng vùng `try`.
3. **Khó bảo trì.** Khi thêm một lời gọi mới vào `try`, nó có thể ném cùng kiểu exception nhưng với nguyên nhân khác.
4. **Sai tầng trách nhiệm.** Exception hạ tầng bị biến thành “không có dữ liệu”, làm caller tưởng thao tác thành công.
5. **Chi phí ở đường nóng.** Việc tạo/throw/catch exception thật sự xảy ra nhiều lần có thể gây overhead do object allocation, stack trace và điều khiển luồng.
6. **Làm méo hệ thống quan sát.** Số lượng exception rất cao có thể làm nhiễu metric và log nếu framework thu thập chúng.
7. **Che mất hợp đồng trạng thái.** Thay vì trả `Optional.empty()` hoặc `false`, code ngầm định “thao tác thất bại sẽ ném IndexOutOfBoundsException”.
8. **Khó phân loại lỗi thật.** Bắt `Exception` hoặc `RuntimeException` rộng có thể làm biến mất lỗi cần điều tra.

Nhưng **không** có quy tắc “viết if luôn nhanh hơn throw” áp dụng cho mọi trường hợp. Nếu lỗi hiếm, một API thiết kế ném ngoại lệ có thể đơn giản và đúng hợp đồng. Việc quyết định tối ưu hiệu năng cần dựa vào workload và đo đạc có kiểm soát.

## 5. Ví dụ đầu tiên: danh sách rỗng là một nhánh hợp lệ

### Cách không nên ưu tiên

~~~java
String firstName(List<String> names) {
    try {
        return names.get(0);
    } catch (IndexOutOfBoundsException ignored) {
        return "Không có tên";
    }
}
~~~

Đây là **mã minh họa không độc lập**. Nó vừa dùng exception làm điều kiện rỗng, vừa dễ tạo ấn tượng rằng tất cả lỗi chỉ số trong `try` đều có thể xem như “không có tên”.

### Cách rõ ràng hơn

~~~java
String firstName(List<String> names) {
    if (names.isEmpty()) {
        return "Không có tên";
    }
    return names.get(0);
}
~~~

Nếu API không muốn cung cấp một chuỗi mặc định có thể bị nhầm với dữ liệu thật, dùng một kiểu trả về diễn đạt “không có”:

~~~java
Optional<String> firstName(List<String> names) {
    return names.isEmpty()
            ? Optional.empty()
            : Optional.ofNullable(names.get(0));
}
~~~

Đây là **mã minh họa** dùng `java.util.Optional`. `Optional.ofNullable` trả empty nếu phần tử đầu tiên là null; điều đó phù hợp chỉ khi hợp đồng muốn coi phần tử null tương đương “không có tên”. Nếu null là một giá trị mang nghĩa khác, cần thiết kế result type chi tiết hơn.

**Không dùng Optional để che mọi vấn đề.** Nếu danh sách bắt buộc phải có phần tử, việc ném exception do vi phạm hợp đồng có thể là đúng. Khi đó nên kiểm tra điều kiện và ném một lỗi có ý nghĩa, thay vì dựa vào `get(0)` để tự phát sinh `IndexOutOfBoundsException` khó hiểu:

~~~java
String requireFirstName(List<String> names) {
    if (names.isEmpty()) {
        throw new IllegalArgumentException(
                "Danh sách tên không được rỗng");
    }
    return names.get(0);
}
~~~

Ba API `firstName`, `findFirstName` và `requireFirstName` có thể cùng tồn tại nếu chúng thực sự biểu đạt **ba hợp đồng khác nhau**. Quan trọng nhất là không biến một nhánh dự kiến thành lỗi hoặc nuốt lỗi không dự kiến.

## 6. Ví dụ Java 17 độc lập: guard, Optional và parse

Lưu tệp **GuardInsteadOfExceptionDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalInt;

public class GuardInsteadOfExceptionDemo {

    static String firstUsingException(List<String> values) {
        try {
            return values.get(0);
        } catch (IndexOutOfBoundsException e) {
            return "EMPTY";
        }
    }

    static String firstUsingGuard(List<String> values) {
        return values.isEmpty() ? "EMPTY" : values.get(0);
    }

    static Optional<String> findCode(Map<String, String> codes, String key) {
        return Optional.ofNullable(codes.get(key));
    }

    static OptionalInt parseUserNumber(String input) {
        try {
            return OptionalInt.of(Integer.parseInt(input));
        } catch (NumberFormatException e) {
            return OptionalInt.empty();
        }
    }

    public static void main(String[] args) {
        List<String> empty = List.of();
        List<String> names = List.of("An", "Bình");
        Map<String, String> codes = Map.of("A", "Alpha");

        System.out.println("Exception-based empty: "
                + firstUsingException(empty));
        System.out.println("Guard empty: " + firstUsingGuard(empty));
        System.out.println("Guard nonempty: " + firstUsingGuard(names));

        System.out.println("Known code: "
                + findCode(codes, "A").orElse("MISSING"));
        System.out.println("Unknown code: "
                + findCode(codes, "B").orElse("MISSING"));

        System.out.println("Parse 42: "
                + parseUserNumber("42").orElse(-1));
        System.out.println("Parse invalid: "
                + parseUserNumber("abc").orElse(-1));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 GuardInsteadOfExceptionDemo.java
java GuardInsteadOfExceptionDemo
~~~

**Stdout chính xác:**

~~~text
Exception-based empty: EMPTY
Guard empty: EMPTY
Guard nonempty: An
Known code: Alpha
Unknown code: MISSING
Parse 42: 42
Parse invalid: -1
~~~

### Phân tích

- Hai hàm lấy phần tử đầu tiên trả cùng kết quả ở ví dụ, nhưng `firstUsingGuard` biểu đạt nhánh rỗng bằng điều kiện có sẵn.
- `Map.get("B")` trả null vì khóa không tồn tại trong map được tạo ở đây; `Optional.ofNullable` chuyển điều đó thành kết quả empty rõ nghĩa.
- `parseUserNumber` **vẫn dùng try/catch** vì `Integer.parseInt` đã công bố `NumberFormatException` là cách báo cú pháp số không hợp lệ. Bắt chính exception này tại ranh giới parse để trả `OptionalInt.empty()` là một lựa chọn hợp lệ.
- Dùng `-1` chỉ để hiển thị trong `main`; một hệ thống có giá trị âm hợp lệ không nên dùng số âm làm sentinel lỗi nếu không có hợp đồng rõ ràng.

**Bài học:** sai lầm không nằm ở sự tồn tại của từ khóa `catch`. Sai lầm là **dùng ngoại lệ che một phép kiểm tra hiển nhiên hoặc nuốt lỗi mà hệ thống cần phân biệt**.

## 7. NullPointerException không phải tín hiệu “không có giá trị” đáng tin cậy

Mẫu nguy hiểm:

~~~java
int lengthOrZero(Map<String, String> values, String key) {
    try {
        return values.get(key).length();
    } catch (NullPointerException e) {
        return 0;
    }
}
~~~

Đây là **mã minh họa** với import `Map`. Trong tình huống khóa không tồn tại, `get(key)` trả null rồi `.length()` ném NPE. Nhưng cùng kiểu NPE có thể đến từ `values == null` hoặc một dòng khác được thêm vào khối `try`. Bắt NPE để trả 0 có thể che một lỗi thiết kế.

Thay bằng kiểm tra chính kết quả:

~~~java
int lengthOrZero(Map<String, String> values, String key) {
    String value = values.get(key);
    return value == null ? 0 : value.length();
}
~~~

Điều này xử lý đúng nếu hợp đồng đã chọn rằng **khóa không tồn tại và giá trị null đều cho độ dài 0**. Nhưng nếu cần phân biệt hai trạng thái, phải xét ngữ nghĩa của map.

### Phân biệt khóa không tồn tại và khóa tồn tại với giá trị null

Một số triển khai `Map` cho phép ánh xạ giá trị null:

~~~java
Map<String, String> values = new HashMap<>();
values.put("present-null", null);
~~~

Đây là **mã minh họa**; cần import `Map` và `HashMap`. Cả `values.get("missing")` lẫn `values.get("present-null")` đều trả null, nhưng:

- `values.containsKey("missing")` là false.
- `values.containsKey("present-null")` là true.

Tương tự, `getOrDefault(key, fallback)` chỉ dùng fallback khi **không có ánh xạ cho khóa**; nếu khóa đang ánh xạ tới null trong map cho phép null, kết quả có thể vẫn là null.

**Lưu ý concurrency:** trên map bị các luồng khác thay đổi, việc gọi `containsKey` rồi `get` không phải một thao tác nguyên tử. Không dùng phép kiểm tra này như bảo đảm rằng giá trị vẫn tồn tại ở lần đọc sau.

## 8. Bắt exception quá rộng có thể che lỗi lập trình

`catch (Exception)` có thể biến lỗi hạ tầng và cả bug thành một fallback nhìn như thành công:

~~~java
String loadName(User user) {
    try {
        return user.profile().displayName();
    } catch (Exception e) {
        return "UNKNOWN"; // Anti-pattern: mất phân biệt nguyên nhân.
    }
}
~~~

Đây là fragment cần class `User` và các phương thức của nó. Nếu không có profile là trạng thái dự kiến, API nên trả kết quả biểu đạt vắng mặt. Nếu NPE phá invariant thì phải sửa bug, không coi là “không có tên”.

**Phạm vi `try` cũng quan trọng:** bắt một `IndexOutOfBoundsException` quanh cả `validateInput()`, `findIndex()` và `items.get(index)` có thể nuốt lỗi cùng loại do phương thức khác gây ra. Thu hẹp đúng thao tác có hợp đồng dự kiến thất bại, hoặc dùng guard như `isEmpty()` khi trường hợp rỗng là bình thường. Với dữ liệu bị chia sẻ đồng thời, check-then-act còn cần giải quyết race theo contract riêng.

## 9. Guard clause có chủ đích khác với né tránh exception

**Guard clause** kiểm tra tiền điều kiện hoặc nhánh nghiệp vụ ở đầu phương thức:

~~~java
void register(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive");
    }
    saveQuantity(quantity);
}
~~~

Đây là **mã minh họa** với `saveQuantity` do ứng dụng định nghĩa. Việc dùng if để **ném exception** là đúng khi `quantity <= 0` vi phạm hợp đồng của phương thức. Guard không nhất thiết luôn trả một giá trị mặc định.

Phân biệt:

- “Nếu danh sách rỗng thì không có gì để hiển thị” là **nhánh dữ liệu dự kiến**; có thể trả danh sách/Optional rỗng.
- “Đặt số lượng âm vào một đơn hàng” có thể là **input không hợp lệ**; ném `IllegalArgumentException` hoặc trả kết quả validation ở boundary.
- “Dữ liệu trong bộ nhớ bị phá invariant” là **lỗi lập trình/trạng thái**; cần ném một lỗi có ý nghĩa thay vì giả vờ thành công.

Code trở nên rõ hơn khi tên phương thức thể hiện hợp đồng: `findById` có thể trả `Optional`, còn `requireById` có thể ném lỗi “không tìm thấy” đã được công bố.

## 10. Java 17: thiết kế hai hợp đồng tìm kiếm khác nhau

Lưu tệp **LookupContractDemo.java**:

~~~java
import java.util.Map;
import java.util.Optional;

public class LookupContractDemo {

    record Item(String id, String name) {
    }

    static Optional<Item> find(
            Map<String, Item> items, String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                    "id must not be blank");
        }
        return Optional.ofNullable(items.get(id));
    }

    static Item require(
            Map<String, Item> items, String id) {
        return find(items, id).orElseThrow(() ->
                new IllegalStateException("Item not found: " + id));
    }

    public static void main(String[] args) {
        Map<String, Item> items =
                Map.of("A", new Item("A", "Notebook"));

        System.out.println("Find A: "
                + find(items, "A").map(Item::name).orElse("MISSING"));
        System.out.println("Find B: "
                + find(items, "B").map(Item::name).orElse("MISSING"));

        try {
            require(items, "B");
        } catch (IllegalStateException e) {
            System.out.println("Require B: " + e.getMessage());
        }

        try {
            find(items, "");
        } catch (IllegalArgumentException e) {
            System.out.println("Blank ID: "
                    + e.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LookupContractDemo.java
java LookupContractDemo
~~~

**Stdout chính xác:**

~~~text
Find A: Notebook
Find B: MISSING
Require B: Item not found: B
Blank ID: IllegalArgumentException
~~~

### Giải thích thiết kế

- `find` trả `Optional.empty()` cho một ID **hợp lệ nhưng không tồn tại**. Đây là nhánh dự kiến của API tìm kiếm.
- ID null/rỗng/trắng được xem là **vi phạm tiền điều kiện**; guard chủ động ném `IllegalArgumentException`.
- `require` biểu đạt hợp đồng khác: caller yêu cầu item phải tồn tại. Nếu không có, phương thức ném lỗi phù hợp thay vì âm thầm trả null.
- Caller không cần catch `NullPointerException` để suy ra “không có item”.
- Trong hệ thống lớn, exception của `require` có thể là một lớp domain riêng như `ItemNotFoundException`; ví dụ dùng JDK exception để không cần thêm nhiều lớp phụ.

Một API HTTP có thể ánh xạ `ItemNotFoundException` thành 404 nếu hợp đồng và quyền truy cập cho phép. Không mặc định mọi `IllegalStateException` ở mọi tầng là lỗi “not found”.

## 11. Parse dữ liệu: tại sao catch NumberFormatException có thể hợp lý?

`Integer.parseInt(String)` không cung cấp kết quả `OptionalInt` trực tiếp: nó trả một `int` hợp lệ hoặc ném `NumberFormatException` nếu cú pháp/miền giá trị không được chấp nhận.

Ở ranh giới nhập liệu, có thể chủ động chuyển cơ chế đó thành kết quả validation:

~~~java
OptionalInt parseOptionalInt(String input) {
    try {
        return OptionalInt.of(Integer.parseInt(input));
    } catch (NumberFormatException e) {
        return OptionalInt.empty();
    }
}
~~~

Đây là **mã minh họa** với import `java.util.OptionalInt`. Việc bắt exception cụ thể tại đây không giống việc gọi `list.get(0)` trên danh sách rỗng chỉ để bắt `IndexOutOfBoundsException`: API parser không cung cấp một phép kiểm tra tương đương đơn giản đảm bảo trùng chính xác mọi quy tắc parse.

**Cẩn thận với tiền kiểm tra tự chế:**

~~~java
if (input.matches("[0-9]+")) {
    return Integer.parseInt(input);
}
~~~

Đây là **mã minh họa chưa hoàn chỉnh**; nó không kiểm tra tràn số nguyên, có thể không chấp nhận dấu âm/dấu cộng mà parser chấp nhận, và có thể đưa ra quy tắc khác parser. Việc kiểm tra regex không bảo đảm `parseInt` sẽ không ném `NumberFormatException`. Nếu muốn hỗ trợ một định dạng hẹp hơn của nghiệp vụ, đó phải là **quy tắc validation có chủ đích**, không phải phỏng đoán thay thế hoàn toàn cho parser.

### Có cần tránh exception nếu tỷ lệ input sai rất cao?

Có thể đáng cân nhắc ở đường xử lý nóng, nhưng đừng vội viết lại thuật toán parse số chỉ để né exception. Những lựa chọn an toàn hơn:

- Xác định hợp đồng dữ liệu trước: định dạng số và phạm vi nào thực sự hợp lệ?
- Dùng một parser có API trả trạng thái/kết quả không ném exception nếu thư viện được chọn có hỗ trợ và phù hợp.
- Đo throughput, allocation và latency với tỷ lệ invalid input giống thực tế.
- Nếu tự viết parser, phải kiểm thử đầy đủ dấu, giới hạn `int`, Unicode, ký tự lạ và các trường hợp biên.
- Không nuốt lỗi ở tầng khác chỉ vì chuỗi input có thể sai.

**Không có quy tắc “mọi parse lỗi đều nên trả Optional.empty()”.** Nếu caller cần biết vì sao số sai (tràn, ký tự không hợp lệ, bắt buộc nhập), một kiểu `ValidationResult` chứa mã lỗi cụ thể có thể phù hợp hơn.

## 12. Khi không nên kiểm tra trước: check-then-act và TOCTOU

Đây là ngoại lệ quan trọng đối với lời khuyên “kiểm tra điều kiện trước, tránh dùng exception”.

Giả sử ứng dụng làm:

~~~java
if (Files.exists(path)) {
    return Files.readString(path);
}
return "";
~~~

Đây là **mã minh họa** với import `java.nio.file.Files`, biến `path` kiểu `Path`, và phương thức có hợp đồng checked exception phù hợp. Kiểm tra tồn tại **không bảo đảm** lời gọi `readString` sau đó thành công:

- File có thể bị xóa/đổi tên giữa hai thao tác.
- Quyền truy cập có thể thay đổi.
- Kiểm tra tồn tại có thể không kết luận được vì các hạn chế I/O.
- Đọc file có thể thất bại vì lỗi đĩa, encoding hoặc tài nguyên.
- Ngữ cảnh file có thể thay đổi giữa việc kiểm tra và sử dụng.

Vì vậy, đối với I/O, một cách thường đúng hơn là **thử thao tác thực tế rồi xử lý exception phù hợp**:

~~~java
try {
    return Files.readString(path);
} catch (NoSuchFileException e) {
    return "";
}
~~~

Đây là **mã minh họa** trong phương thức khai báo/xử lý `IOException` còn lại, với import `Files`, `NoSuchFileException` và `Path`. Nó chỉ đổi **lỗi file không tồn tại** thành kết quả rỗng nếu đó là hợp đồng của ứng dụng; các lỗi I/O khác tiếp tục được báo để tránh che sự cố.

Nếu ứng dụng cần phân biệt file không có với file tồn tại nhưng rỗng, **không dùng chuỗi rỗng làm cả hai trạng thái**. Có thể trả `Optional<String>` hoặc kiểu kết quả có cấu trúc, trong đó đã định nghĩa rõ trường hợp vắng mặt.

**Nguyên tắc:** một precheck không bảo đảm điều kiện vẫn đúng tới lúc sử dụng. Khi bản thân thao tác có thể thất bại do yếu tố bên ngoài, **exception là phần thiết yếu của hợp đồng**, không phải anti-pattern.

## 13. Concurrency: kiểm tra rồi hành động có thể tạo race

Giả sử một `ConcurrentHashMap` lưu các task. Một luồng làm:

~~~java
if (tasks.containsKey("job-1")) {
    Task task = tasks.get("job-1");
    task.run();
}
~~~

Đây là **mã minh họa**, giả định `tasks` là map concurrent và `Task` là kiểu nghiệp vụ. Dù từng phương thức `containsKey` và `get` có thread-safety riêng, thao tác **kiểm tra rồi lấy dữ liệu** chưa chắc nguyên tử: luồng khác có thể xóa khóa ở giữa. Khi ấy `task` có thể null và `task.run()` ném NPE.

Cách hợp lý nếu chỉ cần giá trị ở một thời điểm:

~~~java
Task task = tasks.get("job-1");
if (task != null) {
    task.run();
}
~~~

Đây là **mã minh họa**. Nó tránh cửa sổ giữa `containsKey` và `get`, nhưng không bảo đảm task không bị hủy hay thay đổi ở nơi khác trong khi chạy; các yêu cầu vòng đời riêng vẫn cần cơ chế phối hợp.

Nếu điều kiện và cập nhật **phải nguyên tử trên cùng key**, cân nhắc các thao tác atomic của `ConcurrentHashMap` như `computeIfAbsent`, `compute`, `putIfAbsent` hoặc `remove(key, value)` theo hợp đồng tương ứng. Đừng đặt callback blocking/chậm vào một thao tác atomic nếu nó làm tăng contention hoặc gây rủi ro reentrancy; đọc kỹ hợp đồng của từng phương thức.

### Cơ sở dữ liệu cũng có TOCTOU

Mã kiểu “kiểm tra xem email đã tồn tại chưa, nếu chưa thì chèn” không tránh được hai request cùng vượt qua kiểm tra rồi chèn trùng. Nếu cần duy nhất, cơ sở dữ liệu phải bảo vệ bằng **unique constraint**/transaction hoặc cơ chế đồng bộ phù hợp; ứng dụng xử lý lỗi xung đột theo hợp đồng.

Không có cách nào biến một điều kiện **thay đổi do tác nhân khác** thành bất biến chỉ bằng thêm một câu `if` trước thao tác.

## 14. Ví dụ Java 17 độc lập: minh họa race giữa containsKey và get

Chương trình này dùng hai luồng và `CountDownLatch` để đặt lịch có chủ đích: luồng đọc kiểm tra khóa tồn tại, sau đó luồng ghi xóa khóa **trước** khi luồng đọc gọi `get`. Vì đồng bộ hóa thứ tự đã được thiết lập, stdout không phụ thuộc vào tốc độ scheduler.

Lưu tệp **CheckThenActRaceDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class CheckThenActRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> tasks =
                new ConcurrentHashMap<>();
        tasks.put("job-1", "READY");

        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch removed = new CountDownLatch(1);

        Thread reader = new Thread(() -> {
            boolean existed = tasks.containsKey("job-1");
            checked.countDown();

            try {
                removed.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            String after = tasks.get("job-1");
            System.out.println("Precheck: " + existed);
            System.out.println("Read after removal: " + after);
        }, "reader");

        Thread writer = new Thread(() -> {
            try {
                checked.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } finally {
                // Dù có lỗi khi chờ, giải phóng latch để reader không treo.
                tasks.remove("job-1");
                removed.countDown();
            }
        }, "writer");

        reader.start();
        writer.start();

        reader.join();
        writer.join();

        System.out.println("Final containsKey: "
                + tasks.containsKey("job-1"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CheckThenActRaceDemo.java
java CheckThenActRaceDemo
~~~

**Stdout trong điều kiện không có interrupt ngoài ý muốn:**

~~~text
Precheck: true
Read after removal: null
Final containsKey: false
~~~

### Vì sao kết quả minh họa đúng race?

- Map ban đầu chứa `"job-1" -&gt; "READY"`.
- Reader gọi `containsKey` trước khi phát tín hiệu `checked.countDown()`, nên `existed` là true.
- Writer chỉ thực hiện thao tác xóa sau khi `checked.await()` hoàn tất, rồi báo `removed.countDown()`.
- Reader chỉ gọi `get` sau khi `removed.await()` hoàn tất. Vì khóa đã bị xóa, `get` trả null.
- Kết quả minh họa **một precheck có thể trở nên lỗi thời**, không phải chứng minh `ConcurrentHashMap` không thread-safe.
- `join()` bảo đảm cả hai luồng đã kết thúc trước khi main in trạng thái cuối.

Trong ví dụ, nhánh catch xử lý interrupt bằng khôi phục flag và kết thúc luồng. Đây không phải phần cốt lõi của bài, nhưng tránh việc nuốt yêu cầu hủy. Không dùng bản demo để suy rằng kiểm tra trước luôn nguy hiểm; đối với một danh sách **không bị thay đổi đồng thời**, `isEmpty()` trước `get(0)` là thiết kế bình thường.

## 15. API nào giúp biểu đạt trạng thái không cần exception?

Không có một công cụ duy nhất cho mọi tình huống. Hãy chọn theo ý nghĩa của kết quả.

| Nhu cầu | API/hình thức có thể phù hợp | Lưu ý |
| --- | --- | --- |
| Danh sách rỗng | `isEmpty()` | Nếu danh sách bị thay đổi đồng thời, cần hiểu cơ chế đồng bộ |
| Lấy phần tử đầu theo một stream hữu hạn | `stream().findFirst()` | Không bắt buộc tốt hơn `isEmpty()+get(0)` cho mọi `List` |
| Map không có ánh xạ | `get()`, `containsKey()`, `getOrDefault()` | Xác định ngữ nghĩa null và thay đổi đồng thời |
| Tìm bản ghi tùy chọn | `Optional&lt;T&gt;` | Có thể biểu đạt vắng mặt; không dùng nếu cần nhiều lý do thất bại |
| Kiểm tra tập rỗng | `Collection.isEmpty()` | Không đợi tới lúc iterator ném lỗi |
| Chuỗi null/blank | `value == null`, `String.isBlank()` | `isBlank` chỉ gọi sau khi đã biết không null |
| Chuyển đổi dữ liệu có parser ném lỗi | Bắt loại parse exception cụ thể ở boundary | Tránh tự tái tạo parser không đầy đủ |
| Kiểm tra tham số bắt buộc | Guard, `Objects.requireNonNull()` | Có thể cố ý ném exception do vi phạm hợp đồng |
| Truy cập tệp/tài nguyên | Thử thao tác và xử lý lỗi I/O phù hợp | Precheck không loại bỏ race |
| Kết quả có cả mã lỗi và dữ liệu | Record/Result type do ứng dụng định nghĩa | Tránh nhiều sentinel không phân biệt được |
| Tác vụ async | `CompletableFuture` với completion thành công/thất bại | Future lỗi cần được quan sát, không tự động đổi thành null |

### Optional là hợp đồng, không phải thuốc chữa mọi lỗi

Ví dụ một hàm `find` trả `Optional.empty()` nếu dữ liệu không tồn tại là hợp lý. Nhưng trả empty khi database offline sẽ **che sự khác biệt quan trọng** giữa “không tìm thấy” và “không thể kiểm tra”.

Nếu caller cần biết nhiều trường hợp: không tìm thấy, không được phép, timeout, hạ tầng lỗi, nên dùng result type giàu thông tin hoặc ném ngoại lệ có ý nghĩa theo API. Không gộp tất cả thành empty để code không cần catch.

## 16. Quy tắc “Look Before You Leap” và “Easier to Ask Forgiveness”

Hai phong cách thường được gọi bằng tên tiếng Anh:

- **LBYL — Look Before You Leap:** kiểm tra điều kiện rồi thực hiện thao tác.
- **EAFP — Easier to Ask Forgiveness than Permission:** thử thao tác rồi xử lý thất bại.

Trong Java, không nên áp dụng một khẩu hiệu cho mọi API.

**LBYL thường hợp lý** khi điều kiện là nhánh dữ liệu bình thường, không có race liên quan và check có ý nghĩa trực tiếp: `list.isEmpty()`, `input == null`, `quantity <= 0`.

**EAFP có thể hợp lý** khi API thao tác là nguồn sự thật, rủi ro race khiến precheck không đáng tin, hoặc API chỉ cung cấp exception cho thất bại thực tế: `Files.readString()`, network I/O, parser chuẩn hoặc constraint cơ sở dữ liệu.

**Điều quan trọng là hợp đồng**, không phải sở thích cú pháp. Không dùng exception làm công cụ rẽ nhánh thông thường khi đã có một điều kiện rõ ràng; đồng thời không dùng precheck làm “bùa hộ mệnh” để giả vờ thao tác tài nguyên không thể thất bại.

## 17. Ngoại lệ và hiệu năng: tối ưu đúng chỗ

Việc **ném exception thật sự** có thể tốn chi phí: tạo Throwable, có thể thu thập stack trace, chuyển điều khiển sang catch, và ghi log nếu ứng dụng chọn log. Nếu nó xảy ra ở đường xử lý bình thường hàng nghìn/hàng triệu lần, overhead có thể đáng kể.

Tuy nhiên:

- Chi phí phụ thuộc JVM, loại exception, độ sâu stack, tần suất, JIT và logger.
- Chỉ có khối `try` nhưng không ném lỗi **không đồng nghĩa** với trả chi phí stack trace ở mỗi lần chạy.
- Một JVM có thể tối ưu các mẫu cụ thể; không nên diễn giải rằng mọi đường exception luôn có cùng overhead.
- Đo benchmark có thể bị méo nếu logging ra console trong vòng lặp, không warm-up hoặc không dùng tải thực tế.
- Một phép guard có thể làm tăng việc đọc trạng thái/locking hoặc bị TOCTOU, nên không mặc nhiên nhanh hay đúng hơn mọi thao tác có exception.
- Với ngoại lệ **hiếm**, khả năng chẩn đoán có thể quan trọng hơn chênh lệch thời gian cực nhỏ.

Nếu nghi exception-driven control flow gây vấn đề hiệu năng:

1. Dùng profiler/metrics để xác nhận exception thật sự được ném nhiều lần.
2. Xác định trường hợp đó là trạng thái nghiệp vụ dự kiến hay lỗi hệ thống.
3. Thay API theo ngữ nghĩa thích hợp: điều kiện, Optional, kết quả có cấu trúc hoặc phép toán atomic.
4. Đo lại throughput, allocation rate, p95/p99 latency với cùng workload.
5. Xem lỗi/quan sát có bị che sau thay đổi không.
6. Nếu cần microbenchmark, có thể dùng JMH trong dự án cấu hình riêng; JMH không có sẵn chỉ bằng Java SE.

**Không thay đổi API chỉ vì một benchmark tổng hợp cho thấy câu if nhanh hơn throw.** Chất lượng hợp đồng, concurrency correctness và khả năng chẩn đoán vẫn là tiêu chí quyết định.

## 18. “Không ném exception” không đồng nghĩa xử lý lỗi đúng

Một cách đổi sai là bỏ catch và trả fallback cho mọi tình huống:

~~~java
String fetchProfile() {
    try {
        return remoteService.fetchProfile();
    } catch (RuntimeException ignored) {
        return "UNKNOWN";
    }
}
~~~

Đây là **mã minh họa không độc lập**. Dù có try/catch, vấn đề chính không chỉ là hiệu năng. Nó khiến caller nhận `UNKNOWN` và tưởng hệ thống đã xử lý thành công khi thực tế backend có thể lỗi.

Một cách sửa có chủ đích:

- Nếu không có profile là kết quả nghiệp vụ hợp lệ, trả một giá trị rỗng hoặc Optional khi **thực sự xác nhận không tồn tại**.
- Nếu hạ tầng không trả lời, tạo trạng thái lỗi riêng có thể quan sát, hoặc ném exception tầng API đã giữ cause.
- Nếu muốn dùng cache, phải có chính sách fallback rõ ràng; cân nhắc dữ liệu cũ có an toàn trong ngữ cảnh nghiệp vụ không.
- Nếu hoạt động có side effect, không khuyên retry vô điều kiện khi chưa rõ request trước có thành công không.

**Một API tốt cho caller biết ba câu chuyện khác nhau:** có dữ liệu, không có dữ liệu theo hợp đồng, hoặc không thể xác định kết quả vì lỗi.

## 19. Lỗi thường gặp khi refactor khỏi exception-driven control flow

### 19.1. Biến lỗi thật thành nhánh bình thường

Từ `catch (IOException) { return null; }` sang `if (!Files.exists(path)) return null;` không loại bỏ thất bại của `readString`. Lỗi quyền truy cập, thiết bị và race vẫn phải xử lý.

### 19.2. Kiểm tra null sau khi đã dereference

~~~java
String name = user.getName();
if (user == null) {
    return "UNKNOWN";
}
~~~

Đây là **mã minh họa cố ý sai**: nếu `user == null`, NPE xảy ra trước check. Guard phải đặt **trước** thao tác yêu cầu đối tượng khác null.

### 19.3. Trả sentinel xung đột với giá trị thật

Sử dụng `-1` hoặc chuỗi rỗng cho lỗi có thể gây lẫn với giá trị hợp lệ. Nếu miền giá trị có thể chứa các giá trị đó, dùng `Optional`, record hoặc kiểu kết quả có trạng thái riêng.

### 19.4. Dùng Optional.empty cho mọi loại lỗi

Một lỗi database, timeout hoặc permission bị biến thành “not found” có thể gây ra quyết định nghiệp vụ sai. Optional nên biểu đạt **vắng mặt**, không tự động biểu đạt mọi thất bại.

### 19.5. Bắt NullPointerException rồi tiếp tục

Khối `catch (NullPointerException)` có thể che lỗi lập trình. Nếu null hợp lệ, kiểm tra trực tiếp hoặc thiết kế kiểu dữ liệu phù hợp. Nếu null không hợp lệ, nên sửa invariant hoặc báo lỗi có ý nghĩa.

### 19.6. Bắt IndexOutOfBoundsException cho vòng lặp

~~~java
int i = 0;
try {
    while (true) {
        consume(items.get(i++));
    }
} catch (IndexOutOfBoundsException ignored) {
    // coi là hết danh sách
}
~~~

Đây là **mã minh họa cố ý không khuyến nghị**, với `items` và `consume` có sẵn. Khi vòng lặp biết kích thước, có thể dùng `for (int i=0; i<items.size(); i++)` hoặc for-each theo yêu cầu. Việc dùng exception để báo kết thúc làm khó đọc và có thể nuốt lỗi chỉ số do thao tác khác trong vùng `try`.

### 19.7. Kiểm tra map trước rồi tin kết quả mãi mãi

Trên cấu trúc dữ liệu concurrent, `containsKey` và `get` là hai thao tác. Nếu cần atomicity, phải chọn thao tác/hợp đồng thread-safety phù hợp.

### 19.8. Tự viết parser regex không tương đương API chuẩn

Regex đơn giản có thể không kiểm tra overflow, dấu âm hay phạm vi ký tự; code sau regex vẫn có thể ném `NumberFormatException`. Nên tôn trọng hợp đồng parser và chỉ kiểm tra thêm các ràng buộc riêng của nghiệp vụ.

### 19.9. Refactor làm mất cause

Nếu chuyển một lỗi I/O thành exception tầng API, dùng constructor nhận `Throwable cause`, thay vì chỉ sao chép message. Không biến “không nên dùng exception cho nhánh bình thường” thành “không nên giữ exception ở các đường lỗi thật”.

### 19.10. Thêm guard rải rác không có hợp đồng

Một số phương thức trả null, một số trả empty, một số ném `IllegalArgumentException` cho cùng một điều kiện. Hãy thống nhất tên API, document và kiểu trả về để caller không phải đoán.

### 19.11. Bắt Exception quá rộng

`catch (Exception)` có thể nuốt `InterruptedException` trong một phương thức chờ; tín hiệu hủy bị mất nếu code tiếp tục mà không có chính sách tương ứng. Luôn xem checked exception và cancel contract khi thay đổi vùng catch.

### 19.12. Đánh giá bằng performance trước khi xem correctness

Guard có thể tránh exception nhưng gây race; hoặc nó rẻ hơn một ít mà làm che lỗi. Correctness của hợp đồng là điều kiện tiên quyết trước khi tối ưu.

## 20. Checklist review code

Khi thấy một khối `try/catch` trong đường xử lý thường xuyên, hãy hỏi:

1. Điều kiện gây exception là **trường hợp nghiệp vụ dự kiến** hay **vi phạm hợp đồng/lỗi bất thường**?
2. Có API kiểm tra trực tiếp, rõ nghĩa và đủ an toàn như `isEmpty()` không?
3. Nếu dùng guard, điều kiện có thể thay đổi giữa check và thao tác không?
4. Có cần thao tác atomic, transaction hoặc xử lý thất bại của chính thao tác thay vì precheck không?
5. Khối `try` đã đủ hẹp để catch không nuốt lỗi từ các lệnh khác chưa?
6. Loại exception bắt có cụ thể không, hay đang bắt `Exception`/`RuntimeException` quá rộng?
7. Trường hợp thiếu dữ liệu có thể biểu đạt bằng `Optional` hoặc kiểu kết quả rõ nghĩa không?
8. Null, giá trị sentinel và empty có thể bị nhầm với dữ liệu hợp lệ không?
9. Đầu vào sai cú pháp do parser chuẩn báo có cần chuyển thành lỗi validation ở boundary không?
10. Khi thật sự có lỗi kỹ thuật, code có giữ cause và cung cấp thông tin chẩn đoán đủ không?
11. Thao tác có side effect có bị retry mù quáng khi catch không?
12. Nếu thay đổi code vì hiệu năng, đã đo đúng workload và kiểm tra correctness sau refactor chưa?

## 21. Bài tập tự luyện

### Bài tập 1: thay vòng lặp dùng exception

Viết lại đoạn duyệt danh sách bằng `for-each` hoặc vòng lặp theo index hợp lệ. Chứng minh một danh sách rỗng được xử lý bình thường mà không cần ném lỗi.

~~~java
int i = 0;
try {
    for (;;) {
        System.out.println(items.get(i++));
    }
} catch (IndexOutOfBoundsException e) {
    // Hết phần tử.
}
~~~

Đây là **mã minh họa cố ý cần cải tiến**, với `items` đã có trong ngữ cảnh.

### Bài tập 2: phân biệt “không tìm thấy” và “hệ thống lỗi”

Thiết kế một API lấy tài liệu: tài liệu không tồn tại được phép trả empty, còn lỗi đọc dữ liệu không được bị biến thành empty. Viết các kiểm thử minh họa cả hai nhánh.

### Bài tập 3: check-then-act trên Map

Giải thích vì sao `containsKey` rồi `get` không đảm bảo giá trị còn tồn tại khi map có nhiều writer. Nếu yêu cầu là “đăng ký task nếu chưa có”, hãy tìm hiểu `putIfAbsent` và cách tránh tạo hai task trùng.

### Bài tập 4: parser và kết quả validation

Thiết kế một hàm đọc số tuổi từ chuỗi. Cần phân biệt không nhập, sai định dạng, vượt phạm vi 0–150 và hợp lệ. Xem một `OptionalInt` có đủ biểu diễn tất cả yêu cầu không; nếu không, hãy dùng một record hoặc sealed result type chứa mã trạng thái.

## 22. Tóm tắt

- **Đừng dùng exception như một if/else trá hình** khi điều kiện đơn giản đã mô tả chính xác nhánh dữ liệu bình thường.
- Danh sách rỗng, khóa map không tồn tại hoặc một tra cứu tùy chọn thường có cách biểu đạt rõ hơn: `isEmpty()`, `get`, `Optional` hoặc result type.
- **Exception vẫn có chỗ đứng:** vi phạm hợp đồng, parser chuẩn báo lỗi, thất bại I/O, lỗi hạ tầng và các tình huống không thể bảo đảm bằng precheck.
- **Cẩn thận TOCTOU:** với file, map concurrent và database, kiểm tra trước không phải bảo đảm trạng thái còn đúng ở lúc sử dụng.
- Bắt exception ở **phạm vi hẹp nhất và đúng loại**, giữ nguyên cause khi chuyển lỗi và không dùng fallback che lỗi thật.
- Tối ưu hiệu năng chỉ sau khi hiểu hợp đồng và đo được tác động trên workload thực tế.

**Kết luận:** Việc thay exception-driven control flow bằng điều kiện đơn giản giúp code rõ ý và có thể giảm overhead khi lỗi bị ném thường xuyên. Nhưng điều kiện không thể thay thế cơ chế xử lý exception của mọi thao tác; lựa chọn đúng phải dựa trên **bản chất trạng thái, hợp đồng API và tính nguyên tử của thao tác**.