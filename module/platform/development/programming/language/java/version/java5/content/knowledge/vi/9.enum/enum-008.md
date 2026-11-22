# Phân biệt name(), toString() và ordinal()

## 1. Ba phương thức trả lời ba câu hỏi khác nhau

Với một hằng enum, ta thường cần:

- Tên khai báo dùng để nhận diện trong mã nguồn.
- Văn bản dùng khi hiển thị hoặc ghi log.
- Vị trí của hằng trong thứ tự khai báo hiện tại.

Ba nhu cầu này tương ứng với `name()`, `toString()` và `ordinal()`, nhưng chúng không phải ba cách thay thế lẫn nhau.

Ví dụ với hằng `IN_PROGRESS` có nhãn `"In progress"`:

| Phương thức | Ví dụ kết quả | Ý nghĩa |
| --- | --- | --- |
| `name()` | `"IN_PROGRESS"` | Tên hằng đúng như khai báo |
| `toString()` | `"In progress"` nếu được ghi đè như vậy | Biểu diễn văn bản của đối tượng |
| `ordinal()` | `1` nếu hằng đứng thứ hai | Chỉ số bắt đầu từ 0 trong khai báo |

Nếu enum không ghi đè `toString()`, kết quả mặc định của nó bằng tên hằng. Sự trùng nhau ở trường hợp mặc định không có nghĩa `name` và `toString` luôn cùng mục đích.

Các hành vi này vẫn áp dụng trong Java hiện nay. Chương trình minh họa chạy với JDK 17 trở lên.

## 2. name(): tên khai báo chính xác, không phải nhãn tùy biến

Xét:

```java
enum PlainMode {
    FAST,
    SAFE
}
```

`PlainMode.FAST.name()` trả `"FAST"`. Kết quả giữ đúng tên trong khai báo; không tự chuyển thành chữ thường, không thêm khoảng trắng và không dịch ngôn ngữ.

`name()` là phương thức `final` của `Enum`. Enum hoặc một thân lớp riêng của hằng không thể ghi đè nó để trả một nhãn khác.

### Tên chính xác không có nghĩa bất biến qua mọi lần sửa mã

Nếu lập trình viên đổi tên hằng trong mã nguồn, `name()` ở phiên bản mới cũng đổi.

Vì vậy, có thể dùng tên khai báo làm một phần hợp đồng ngoài chương trình **nếu chủ đích chọn như vậy**. Khi đó, đổi tên hằng không còn là một thao tác chỉ ảnh hưởng nội bộ; phải đánh giá dữ liệu và bên sử dụng đang dựa vào tên cũ.

Không nên nói “name() luôn an toàn để lưu vĩnh viễn” mà không nêu hợp đồng tương thích. Điểm mạnh của nó là tên chính xác theo khai báo, không phải một lời hứa rằng mọi lần tái cấu trúc sẽ giữ nguyên tên.

Quy tắc của phương thức nằm trong [Enum.name](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#name()).

## 3. toString(): biểu diễn văn bản có thể được ghi đè

Mặc định:

```java
PlainMode.FAST.toString().equals(PlainMode.FAST.name())
```

là `true`.

Nhưng enum có thể ghi đè:

```java
@Override
public String toString() {
    return displayName;
}
```

Đây là một phương thức minh họa bên trong enum đã có trường `displayName`. Nó không phải chương trình độc lập.

Khi đó, `name()` có thể vẫn là `"IN_PROGRESS"` nhưng `toString()` trả `"In progress"`.

### In trực tiếp thường đi qua biểu diễn văn bản

Các cách như nối enum vào chuỗi hoặc in một tham chiếu enum khác `null` sẽ dùng biểu diễn văn bản của nó:

```java
System.out.println("status = " + TicketStatus.IN_PROGRESS);
```

Trong chương trình phía sau, dòng này sẽ sử dụng nhãn `In progress` do `toString` cung cấp, không tự gọi `name` để lấy tên khai báo.

Nếu cần tên chính xác trong một dòng chẩn đoán, hãy gọi `name()` rõ ràng. Nếu cần một mã giao tiếp, hãy xuất đúng trường mã theo hợp đồng đó.

### Không dùng toString làm khóa ngầm chỉ vì nó đang đẹp và dễ đọc

`toString` có thể:

- Được sửa để dễ đọc hơn.
- Dùng nhãn khác tên khai báo.
- Có cùng văn bản ở nhiều hằng nếu người viết chọn như vậy.
- Không mang toàn bộ thông tin cần để phân biệt các giá trị ở một giao thức.

Một nhãn giao diện có thể cần thay theo ngôn ngữ. Không nên để việc chỉnh câu chữ hiển thị vô tình đổi giá trị máy đọc đang lưu hoặc trao đổi.

Hợp đồng tùy biến nằm ở [Enum.toString](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#toString()).

Nếu ứng dụng cần nhiều dạng hiển thị, một phương thức riêng như `displayName(language)` hoặc một lớp ánh xạ nhãn có thể rõ hơn việc bắt `toString` đảm nhiệm tất cả tình huống.

## 4. ordinal(): vị trí khai báo bắt đầu từ 0

Với:

```java
enum Stage {
    OPEN,
    IN_PROGRESS,
    CLOSED
}
```

kết quả là:

- `OPEN.ordinal() == 0`.
- `IN_PROGRESS.ordinal() == 1`.
- `CLOSED.ordinal() == 2`.

`ordinal()` là `final`. Nó không phải một trường mã mà ta có thể ghi đè để đặt `OPEN = 100` hoặc `CLOSED = 900`.

Truyền một số vào constructor enum cũng không đổi ordinal. Ví dụ `OPEN(100)` chỉ truyền `100` vào một tham số constructor do ta định nghĩa; ordinal vẫn được xác định từ thứ tự khai báo.

### Ordinal không tự là mã nghiệp vụ

Nếu thêm một hằng trước `IN_PROGRESS`, ordinal của nó thay đổi.

Ví dụ:

```text
Truoc: OPEN, IN_PROGRESS, CLOSED
             ordinal = 1

Sau:   OPEN, WAITING, IN_PROGRESS, CLOSED
                      ordinal = 2
```

Nếu đã lưu số `1` để nói “đang xử lý”, một phiên bản đọc theo thứ tự mới có thể hiểu nó thành `WAITING`.

Do đó, không dùng ordinal như một mã định danh lâu dài chỉ vì nó có sẵn và là số nguyên. Nó phù hợp với câu hỏi vị trí trong khai báo hiện tại và được các cấu trúc chuyên cho enum sử dụng trong cơ chế nội bộ.

Hợp đồng vị trí được nêu trong [Enum.ordinal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#ordinal()).

### Thứ tự tự nhiên không phải thứ tự nhãn

Thứ tự tự nhiên mà `Enum.compareTo` cung cấp dựa trên thứ tự khai báo các hằng. Đổi `toString` hoặc đổi nhãn không tự đổi thứ tự tự nhiên.

Nếu muốn sắp xếp theo nhãn, độ ưu tiên hay một mã miền, phải chọn một tiêu chí sắp xếp riêng. Không đồng nhất vị trí khai báo với mọi thứ tự có ý nghĩa trong nghiệp vụ.

## 5. valueOf đọc name, không đọc toString

Mỗi enum có phương thức `valueOf(String)` tương ứng với kiểu enum:

```java
TicketStatus status = TicketStatus.valueOf("IN_PROGRESS");
```

Nó tra tên khai báo chính xác.

Không có quy tắc tự động rằng:

```java
TicketStatus.valueOf(status.toString())
```

luôn khôi phục được hằng cũ.

Nếu `toString()` trả `"In progress"`, chuỗi đó không phải tên `IN_PROGRESS` nên `valueOf` sẽ ném `IllegalArgumentException`.

Các điểm cần nhớ:

- Phân biệt chữ hoa/chữ thường.
- Không tự bỏ khoảng trắng đầu và cuối.
- Không đọc một trường mã riêng do ứng dụng định nghĩa.
- Tên không khớp hằng nào gây `IllegalArgumentException`.
- Đầu vào `null` gây `NullPointerException` theo hợp đồng của API.

Ngược lại, với một hằng khác `null` và cùng khai báo enum hiện tại:

```java
TicketStatus.valueOf(status.name()) == status
```

là quan hệ khôi phục theo tên mà ta mong đợi.

`values()` và `valueOf` là những thành viên được khai báo ngầm cho enum theo [JLS: Enum Members](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.3).

## 6. Chương trình đầy đủ: tên, nhãn, vị trí và mã riêng

Ta chọn bốn thông tin rõ ràng:

- `name()` là tên trong mã nguồn.
- `displayName` là nhãn.
- `ordinal()` là vị trí hiện tại.
- `code` là mã trao đổi riêng mà ví dụ chủ đích giữ theo hợp đồng.

Lưu thành `EnumRepresentationsDemo.java`:

```java
import java.util.Objects;

public class EnumRepresentationsDemo {
    enum PlainMode {
        FAST,
        SAFE
    }

    enum TicketStatus {
        OPEN("open", "Open"),
        IN_PROGRESS("in-progress", "In progress"),
        CLOSED("closed", "Closed");

        private final String code;
        private final String displayName;

        TicketStatus(String code, String displayName) {
            this.code = code;
            this.displayName = displayName;
        }

        public String code() {
            return code;
        }

        public String displayName() {
            return displayName;
        }

        @Override
        public String toString() {
            return displayName;
        }

        public static TicketStatus fromCode(String code) {
            Objects.requireNonNull(code, "code");
            for (TicketStatus status : values()) {
                if (status.code.equals(code)) {
                    return status;
                }
            }
            throw new IllegalArgumentException("unknown status code: " + code);
        }
    }

    enum SchemaBefore {
        OPEN,
        IN_PROGRESS,
        CLOSED
    }

    enum SchemaAfter {
        OPEN,
        WAITING,
        IN_PROGRESS,
        CLOSED
    }

    public static void main(String[] args) {
        System.out.println("default toString equals name = "
                + PlainMode.FAST.toString().equals(PlainMode.FAST.name()));

        for (TicketStatus status : TicketStatus.values()) {
            System.out.println(status.name()
                    + " | " + status.toString()
                    + " | " + status.ordinal()
                    + " | " + status.code());
        }

        TicketStatus current = TicketStatus.IN_PROGRESS;
        System.out.println("implicit print = " + current);
        System.out.println("name round trip = "
                + (TicketStatus.valueOf(current.name()) == current));
        System.out.println("code round trip = "
                + (TicketStatus.fromCode(current.code()) == current));

        try {
            TicketStatus.valueOf(current.toString());
        } catch (IllegalArgumentException exception) {
            System.out.println("valueOf rejects display label");
        }

        try {
            TicketStatus.valueOf("in_progress");
        } catch (IllegalArgumentException exception) {
            System.out.println("valueOf requires exact declared name");
        }

        try {
            TicketStatus.fromCode("unknown");
        } catch (IllegalArgumentException exception) {
            System.out.println("unknown code rejected");
        }

        int storedOrdinal = SchemaBefore.IN_PROGRESS.ordinal();
        System.out.println("stored old ordinal = " + storedOrdinal);
        System.out.println("same index in new schema = "
                + SchemaAfter.values()[storedOrdinal].name());
        System.out.println("new ordinal of IN_PROGRESS = "
                + SchemaAfter.IN_PROGRESS.ordinal());

        System.out.println("parsed constant identity = "
                + (TicketStatus.valueOf("IN_PROGRESS")
                        == TicketStatus.IN_PROGRESS));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror EnumRepresentationsDemo.java
java EnumRepresentationsDemo
```

Stdout:

```text
default toString equals name = true
OPEN | Open | 0 | open
IN_PROGRESS | In progress | 1 | in-progress
CLOSED | Closed | 2 | closed
implicit print = In progress
name round trip = true
code round trip = true
valueOf rejects display label
valueOf requires exact declared name
unknown code rejected
stored old ordinal = 1
same index in new schema = WAITING
new ordinal of IN_PROGRESS = 2
parsed constant identity = true
```

Hai enum `SchemaBefore` và `SchemaAfter` chỉ mô phỏng hai phiên bản khai báo để quan sát tác động của chèn hằng. Chương trình không sửa một enum đã được nạp trong lúc chạy.

## 7. Những kết quả quan trọng trong chương trình

### 7.1. Mặc định giống nhau nhưng không bị ràng buộc luôn giống nhau

`PlainMode` không ghi đè `toString`, nên kết quả đầu là `true`.

`TicketStatus` ghi đè `toString` để trả `displayName`. Dòng `IN_PROGRESS | In progress | 1 | in-progress` cho thấy bốn dạng thông tin khác nhau của cùng một hằng.

Không lấy sự trùng nhau ở enum đơn giản làm giả định chung cho mọi enum.

### 7.2. In ngầm dùng nhãn

`"implicit print = " + current` dùng `toString` đã ghi đè, nên in `In progress`.

Nếu đổi nhãn sang một cách diễn đạt khác, dòng này sẽ đổi theo. `current.name()` vẫn trả tên khai báo nếu tên hằng không đổi.

### 7.3. Hai cách parse có hai hợp đồng khác nhau

`valueOf(current.name())` tra tên khai báo.

`fromCode(current.code())` tra trường mã riêng bằng thuật toán do ứng dụng viết.

Cả hai khôi phục đúng hằng trong ví dụ, nhưng không vì thế có thể đổi tùy tiện đầu vào của hai phương thức. `"IN_PROGRESS"` là tên; `"in-progress"` là mã.

### 7.4. Cùng ordinal không có nghĩa cùng trạng thái qua phiên bản

Giá trị `1` từ `SchemaBefore.IN_PROGRESS` trỏ tới `WAITING` nếu đọc bằng chỉ số của `SchemaAfter`.

Đây là một thay đổi ngữ nghĩa có thể xảy ra dù số lưu không hỏng, vẫn nằm trong phạm vi và vẫn đọc được một hằng hợp lệ.

Vì vậy, chỉ kiểm tra chỉ số nằm trong mảng `values()` là chưa đủ chứng minh dữ liệu persisted giữ đúng nghĩa. Phải chọn một định danh có hợp đồng tương thích.

## 8. Mã riêng phải có hợp đồng riêng

Một trường `code` không tự trở thành ổn định chỉ vì nó là `String` hoặc có từ khóa `final`. Ta phải quyết định và giữ các quy tắc:

- Mỗi hằng có mã duy nhất trong tập mã được công bố.
- Mã không bị đổi theo nhãn.
- Không tái sử dụng mã cũ cho một nghĩa khác nếu dữ liệu cũ còn tồn tại.
- Tên hằng có thể được tái cấu trúc theo chính sách riêng trong khi mã giữ nguyên, nếu đó là mục tiêu thiết kế.
- Đầu vào không nhận diện được có một chính sách rõ ràng.

Ví dụ `fromCode`:

```java
public static TicketStatus fromCode(String code) {
    Objects.requireNonNull(code, "code");
    for (TicketStatus status : values()) {
        if (status.code.equals(code)) {
            return status;
        }
    }
    throw new IllegalArgumentException("unknown status code: " + code);
}
```

Đây là phương thức trong chương trình, không dùng `toString` và không suy ra mã từ ordinal.

Các mã của ví dụ được khai báo tường minh và khác nhau. Nếu tập mã lớn hoặc quy tắc cấu hình phức tạp hơn, có thể xây một bảng tra có kiểm tra trùng mã. Dù dùng vòng lặp hay Map, điều quan trọng là tính duy nhất và chính sách tương thích được giữ.

### Đầu vào chưa biết không nên tự biến thành hằng đầu

Có thể chọn báo lỗi, trả một kết quả vắng mặt hoặc một giá trị `UNKNOWN` được thiết kế riêng. Mỗi lựa chọn có ý nghĩa khác nhau.

Không mặc định trả `values()[0]` khi parse thất bại, vì một giá trị không nhận diện được có thể bị biến thành `OPEN` và được xử lý như dữ liệu hợp lệ.

Ví dụ của bài chọn từ chối bằng `IllegalArgumentException`. Nó không cố bao phủ mọi chính sách tương thích của một hệ thống thực tế.

## 9. Có thể dùng name làm mã bên ngoài không?

Có, nếu API hoặc định dạng dữ liệu chủ đích quy định tên enum là giá trị trao đổi.

Khi đó cần hiểu hệ quả:

- Đổi tên hằng có thể làm dữ liệu hoặc client cũ không còn parse được bằng `valueOf`.
- Cần kiểm tra tác động của việc xóa hoặc đổi nghĩa một hằng.
- Nhãn hiển thị vẫn nên được quản lý theo nhu cầu riêng.
- Không tự thêm `toLowerCase` hoặc thay dấu gạch dưới mà không xem đó là một quy tắc mã mới.

Mã riêng hữu ích khi muốn tách tên trong mã nguồn khỏi định danh giao thức. Nhưng không cần thêm một trường mã chỉ để nó sao chép lại tên nếu không có yêu cầu tách biệt nào.

Điểm cần giữ là **quyết định rõ ràng**. `name` không phải nhãn tùy biến; `toString` không phải mã mặc định cho mọi giao thức; `ordinal` không phải định danh lâu dài tự nhiên.

## 10. Không mặc định thư viện sẽ dùng phương thức nào

Một thư viện ghi JSON, ánh xạ cơ sở dữ liệu hoặc đọc cấu hình có thể có quy tắc riêng:

- Dùng tên enum.
- Dùng số.
- Dùng một annotation hoặc bộ chuyển đổi.
- Dùng một trường mã do người dùng cung cấp.

Không suy ra “đã ghi đè toString thì mọi dữ liệu JSON hay lưu trữ sẽ dùng nhãn mới”.

Cần xem hợp đồng và cấu hình thực tế của thư viện đang dùng. Nếu giá trị bên ngoài phải là `code`, hãy ánh xạ rõ vào `code` và kiểm chứng dữ liệu đầu ra, thay vì phụ thuộc một giả định ngầm về `toString`.

Tương tự, sửa `toString` để làm màn hình đẹp hơn không nên được coi là thao tác chắc chắn không ảnh hưởng nơi khác. Hãy xem những bên đang gọi biểu diễn văn bản đó và chúng cần nhãn hay định danh.

## 11. Không dùng ordinal để suy ra quy tắc nghiệp vụ

Các mẫu như:

```java
boolean alreadyStarted = status.ordinal() >= 1;
```

có thể đang giấu một quy tắc như “trạng thái đã bắt đầu”. Nhưng thứ tự khai báo không tự chứng minh quy tắc ấy.

Có thể diễn đạt rõ bằng một phương thức miền hoặc một tập trạng thái được định nghĩa theo ý nghĩa. Nếu cần độ ưu tiên, khai báo một trường ưu tiên theo hợp đồng thay vì vô tình mượn thứ tự mã nguồn.

Tương tự, constructor `CLOSED(90)` không làm `ordinal()` trả `90`. Nếu `90` là một giá trị miền, truy cập nó qua một phương thức riêng.

Ordinal vẫn có vai trò hợp lệ trong những thuật toán gắn trực tiếp với tập hằng của cùng một khai báo đang chạy. Điểm cần tránh là biến vị trí triển khai thành một ý nghĩa miền không được công bố hoặc một mã lưu trữ dài hạn.

## 12. Thay đổi nào tác động tới thông tin nào?

| Thay đổi | name() | toString() trong ví dụ dùng nhãn riêng | ordinal() |
| --- | --- | --- | --- |
| Đổi tên hằng nhưng giữ nhãn và vị trí | Đổi | Có thể giữ nguyên | Giữ nếu vị trí không đổi |
| Đổi nhãn displayName | Giữ | Đổi | Giữ |
| Chèn một hằng trước hằng hiện tại | Giữ tên cũ | Giữ nếu nhãn không đổi | Tăng theo vị trí mới |
| Sắp xếp lại các hằng | Giữ tên | Giữ nếu nhãn không đổi | Đổi theo khai báo |
| Đổi trường code | Không tự đổi | Không tự đổi nếu vẫn trả nhãn | Không tự đổi |

Bảng nói về quan hệ của ví dụ, không hứa mọi cách ghi đè `toString` đều chỉ phụ thuộc nhãn. Một phần triển khai khác có thể dùng các dữ liệu khác; phải đọc đúng hợp đồng của enum đó.

Nếu không ghi đè `toString`, đổi tên hằng cũng đổi kết quả mặc định của `toString`.

## 13. Những lỗi thường gặp

### Parse nhãn bằng valueOf

`valueOf("In progress")` không tự tìm hằng `IN_PROGRESS`. Dùng đúng tên khai báo hoặc viết bộ ánh xạ theo mã/nhãn nếu thật sự có hợp đồng phù hợp.

### Lưu ordinal rồi thêm hằng vào giữa

Số cũ có thể trỏ tới một hằng khác trong phiên bản mới. Đây là lỗi thay đổi nghĩa, không nhất thiết gây ngoại lệ.

### Dùng toString làm khóa rồi chỉnh nhãn

Nhãn bị đổi có thể làm một bộ tra cứu hoặc dữ liệu bên ngoài không còn khớp. Tách nhãn và mã nếu hai bên có yêu cầu thay đổi khác nhau.

### Nghĩ name không bao giờ đổi

`name` phản ánh tên khai báo. Khi tên khai báo đổi, tên trả về đổi. Nếu tên là hợp đồng công khai, cần quản lý tương thích.

### Nghĩ ordinal là số truyền vào constructor

Constructor nhận dữ liệu do ứng dụng định nghĩa. Ordinal vẫn là chỉ số khai báo, bắt đầu từ `0`.

### Dựa vào nhãn để so sánh cùng hằng

Hai nhãn có thể giống nhau hoặc đổi theo yêu cầu hiển thị. Muốn kiểm tra cùng hằng enum, so sánh hằng theo kiểu enum phù hợp; trong trường hợp thông thường, `==` diễn tả trực tiếp yêu cầu đó.

## 14. Thực hành tự kiểm tra

### Bài 1: Mặc định

Nếu một enum không ghi đè `toString`, `FAST.name()` và `FAST.toString()` có cùng văn bản không?

**Đáp án:** có trong hành vi mặc định của Enum. Nhưng một enum khác có thể ghi đè `toString`.

### Bài 2: Nhãn và tên

`IN_PROGRESS` có `toString()` trả `"In progress"`. `valueOf("In progress")` có trả nó không?

**Đáp án:** không. `valueOf` tra tên khai báo chính xác `"IN_PROGRESS"`.

### Bài 3: Vị trí

Một hằng đang có ordinal `1`. Chèn một hằng trước nó có thể giữ ordinal `1` không?

**Đáp án:** không đối với chính vị trí mới của nó; ordinal được tính theo thứ tự khai báo và sẽ dịch theo số hằng được chèn trước.

### Bài 4: Constructor

`OPEN(100)` có làm `OPEN.ordinal()` bằng `100` không?

**Đáp án:** không. `100` là đối số constructor; ordinal của hằng đầu vẫn là `0`.

### Bài 5: Đổi tên

Nếu dùng `name` làm giá trị API, đổi tên hằng có luôn là thao tác nội bộ không?

**Đáp án:** không. Nó có thể thay giá trị API và cần được đánh giá theo hợp đồng tương thích.

### Bài 6: Mã riêng

Vì sao ví dụ dùng `code` và `fromCode` thay vì parse `toString`?

**Đáp án:** để định danh máy đọc được có hợp đồng riêng với nhãn hiển thị, đồng thời không phụ thuộc vị trí khai báo.

Hãy dùng `name` để hỏi tên khai báo, `toString` cho biểu diễn văn bản theo hợp đồng của enum và `ordinal` cho vị trí trong khai báo hiện tại. Khi cần một định danh đi qua ranh giới hệ thống hoặc tồn tại lâu dài, hãy chủ động chọn và giữ hợp đồng cho định danh đó.
