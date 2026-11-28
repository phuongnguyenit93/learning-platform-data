# Record không có component và ý nghĩa của tập giá trị rỗng

## 1. Record không có component là gì?

Một record thường khai báo các component trong record header, ví dụ `record Point(int x, int y)`. Tuy nhiên, Java cũng cho phép header rỗng:

```java
record RefreshRequested() {}
```

`RefreshRequested` là một record hợp lệ dù không mang component nào. Tính năng record được hoàn thiện trong **Java 16** (JEP 395), và cú pháp header rỗng vẫn là một phần ổn định của Java hiện đại.

Một record không có component vẫn là class và vẫn có các đặc tính chung của record:

- Là kiểu tham chiếu, tạo instance bằng `new`.
- Ngầm định là `final` và trực tiếp kế thừa `java.lang.Record`.
- Có canonical constructor không tham số.
- Không có field component và không có accessor component.
- Có `equals()`, `hashCode()` và `toString()` theo quy tắc record.
- Có thể triển khai interface và khai báo phương thức, thành viên `static` hợp lệ.

Điểm đặc biệt nằm ở ngữ nghĩa giá trị mặc định: vì record không có component để so sánh, hai instance của **cùng một record class** bằng nhau theo `equals()` do compiler cung cấp. Record vẫn có thể tự override `equals()`, nhưng khi đó phải giữ đúng hợp đồng của phương thức này. Đây là cách biểu diễn một giá trị không mang dữ liệu, đôi khi được gọi là *unit-like value*.

Mục tiêu bài học:

- Viết đúng cú pháp record header rỗng.
- Hiểu các thành viên vẫn được cung cấp dù không có component.
- Giải thích vì sao các instance cùng kiểu record rỗng bằng nhau theo `equals()`.
- Nhận diện tình huống phù hợp để dùng record rỗng.
- Phân biệt record rỗng với enum singleton và class thông thường.
- Kết hợp record rỗng với interface và pattern matching `instanceof` đã ổn định từ Java 16.

## 2. Cú pháp: dấu ngoặc tròn vẫn bắt buộc

Khai báo record không có component vẫn phải có cặp ngoặc tròn trong header:

```java
record EmptyResult() {}
record RefreshRequested() {}
record NoPayloadCommand() {}
```

Dạng `record EmptyResult() {}` là hợp lệ. Không được bỏ hẳn phần header:

```java
// Không hợp lệ: record declaration vẫn phải có record header.
// record EmptyResult {}
```

Với record thông thường, component nằm giữa cặp ngoặc tròn. Với record rỗng, phần giữa để trống. Body có thể để trống hoặc chứa các thành viên hợp lệ như constructor, phương thức instance, phương thức `static`, hằng số `static` và kiểu lồng.

## 3. Những thành viên nào được sinh khi header rỗng?

Xét:

```java
record EmptyResult() {}
```

Record này không có component, nên Java không tạo field component hay accessor component. Tuy vậy, các thành viên cơ bản của record vẫn tồn tại:

| Thành viên | Với `EmptyResult()` |
| --- | --- |
| Field component | Không có field instance nào được sinh từ component. |
| Canonical constructor | Constructor không tham số `EmptyResult()`. |
| Accessor component | Không có accessor vì không có component. |
| `equals(Object)` | So sánh theo ngữ nghĩa giá trị của record. |
| `hashCode()` | Có triển khai nhất quán với `equals()`. |
| `toString()` | Biểu diễn tên record; thường có dạng `EmptyResult[]`. |

Canonical constructor không tham số được cung cấp ngầm định. Có thể tạo instance bằng:

```java
EmptyResult first = new EmptyResult();
EmptyResult second = new EmptyResult();
```

Không có phương thức như `first.value()` hay `first.name()` vì header không khai báo component. Nếu cần dữ liệu để đọc, so sánh hoặc xử lý, hãy khai báo component tương ứng thay vì cố thêm field instance vào body.

### Record rỗng vẫn không được thêm field instance tùy ý

Quy tắc của record giới hạn trạng thái instance vào các component trong header. Khi header rỗng, record không có trạng thái instance được khai báo:

```java
// Không hợp lệ: không thể thêm field instance ngoài record component.
// record EmptyResult() {
//     private int internalState;
// }
```

Có thể khai báo thành viên `static` vì chúng thuộc class, không phải trạng thái riêng của từng instance:

```java
record RefreshRequested() {
    static final String COMMAND_NAME = "refresh";

    String description() {
        return "Yêu cầu làm mới dữ liệu";
    }
}
```

Phương thức instance có thể cung cấp hành vi, nhưng không thể lưu thêm trạng thái instance bằng field riêng. Trong ví dụ, mọi instance của `RefreshRequested` đều trả về cùng một mô tả.

## 4. Canonical constructor không tham số

Với `record RefreshRequested() {}`, canonical constructor có chữ ký không tham số:

```java
RefreshRequested()
```

Trình biên dịch cung cấp constructor này nếu ta không tự khai báo. Vì không có component, không có tham số để gán và cũng không có accessor cần sinh.

Nếu cần khai báo constructor tường minh, có thể viết:

```java
record RefreshRequested() {
    RefreshRequested() {
        // Không có component để kiểm tra hoặc gán.
    }
}
```

Compact canonical constructor cũng có thể viết với header rỗng:

```java
record RefreshRequested() {
    RefreshRequested {
        // Phần thân compact constructor.
    }
}
```

Trong thực tế, không cần khai báo constructor chỉ để lặp lại constructor rỗng mặc định. Vì record không có dữ liệu đầu vào, việc kiểm tra giá trị component cũng không có ý nghĩa. Hãy chỉ thêm constructor khi có lý do khởi tạo rõ ràng; không dùng constructor để tạo side effect tùy tiện mỗi lần một giá trị stateless được tạo.

## 5. Ngữ nghĩa equals mặc định: các instance cùng record class đều bằng nhau

Đây là đặc điểm quan trọng nhất của record không có component.

Với triển khai `equals()` mặc định, hai instance bằng nhau nếu chúng thuộc cùng record class và các component tương ứng bằng nhau. Với tập component rỗng, không có cặp component nào cần so sánh. Điều kiện về component được thỏa mãn một cách hiển nhiên (*vacuously true*).

```java
record RefreshRequested() {}
record CancelRequested() {}

RefreshRequested first = new RefreshRequested();
RefreshRequested second = new RefreshRequested();
CancelRequested cancel = new CancelRequested();

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
System.out.println(first.equals(cancel)); // false
```

Giải thích:

- `first` và `second` là hai object riêng biệt được tạo bằng hai lần gọi `new`, nên `==` là `false`.
- Chúng cùng thuộc record class `RefreshRequested`, và không có component nào khác nhau, nên `equals()` là `true`.
- `cancel` thuộc record class khác, nên không bằng `RefreshRequested`, dù cả hai đều không có component.

Vì vậy, record rỗng vẫn là object có identity riêng, nhưng equality mặc định của nó dựa trên kiểu record chứ không dựa trên identity. Kết luận này áp dụng khi dùng `equals()` do compiler sinh; nếu tự override `equals()`, record có thể định nghĩa quy tắc bình đẳng khác, miễn tuân thủ hợp đồng Java.

### hashCode và toString

Nếu hai instance cùng kiểu record rỗng bằng nhau, hợp đồng Java yêu cầu chúng có cùng `hashCode()`:

```java
RefreshRequested a = new RefreshRequested();
RefreshRequested b = new RefreshRequested();

System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a); // Biểu diễn dạng văn bản của record
```

Không dựa vào một con số `hashCode()` cụ thể. Java không cam kết giá trị số đó là một hằng số cố định qua các phiên bản hoặc lần chạy. Chỉ dựa vào hợp đồng rằng hai object bằng nhau phải có cùng mã băm.

`toString()` mặc định vẫn được cung cấp dù không có component; biểu diễn thường có dạng `RefreshRequested[]`. Không dùng chuỗi này làm giao thức lưu trữ hoặc trao đổi dữ liệu.

## 6. Khi nào record rỗng hữu ích?

Record rỗng phù hợp khi kiểu dữ liệu đại diện cho một giá trị có ý nghĩa nhưng không cần mang payload.

### Tín hiệu hoặc command không có dữ liệu đầu vào

Một số thao tác chỉ cần biểu diễn ý định, chẳng hạn yêu cầu làm mới cache hoặc yêu cầu tải lại cấu hình:

```java
interface Command {
    String name();
}

record RefreshCache() implements Command {
    @Override
    public String name() {
        return "refresh-cache";
    }
}

record ReloadConfiguration() implements Command {
    @Override
    public String name() {
        return "reload-configuration";
    }
}
```

Hai record có thể được truyền qua cùng interface `Command`. Không cần thêm một component giả chỉ để phân biệt loại command; bản thân kiểu record đã mang thông tin loại.

### Kết quả không mang payload

Một API nội bộ đôi khi cần biểu diễn kết quả thành công mà không có dữ liệu trả về:

```java
record OperationCompleted() {}

OperationCompleted result = new OperationCompleted();
```

Tuy nhiên, nếu API cần phân biệt thành công, thất bại, mã lỗi hoặc thông điệp, hãy biểu diễn những thông tin đó bằng component hoặc một kiểu kết quả có cấu trúc. Không nên dùng record rỗng để che giấu trạng thái mà caller thực sự cần biết.

### Giá trị đánh dấu trong mô hình dữ liệu

Record rỗng có thể biểu diễn một loại trạng thái hoặc tín hiệu không chứa thuộc tính bổ sung. Khi dùng trong mô hình nhiều loại thông điệp, mỗi record rỗng là một kiểu riêng và có thể triển khai cùng interface.

Cần phân biệt tín hiệu cùng loại với các lần xảy ra sự kiện riêng biệt. Nếu mỗi lần xảy ra cần một identity hoặc thời điểm riêng, hãy thêm component như `eventId` hoặc `occurredAt`. Nếu không có component, mọi instance cùng kiểu record sẽ bằng nhau theo `equals()`.

## 7. Dùng record rỗng qua interface và pattern matching instanceof

Record có thể triển khai interface dù không có component. Đây là cách hữu ích để nhóm các loại command hoặc thông điệp:

```java
interface AppCommand {
    String description();
}

record RefreshCache() implements AppCommand {
    @Override
    public String description() {
        return "Làm mới cache";
    }
}

record StopService() implements AppCommand {
    @Override
    public String description() {
        return "Dừng dịch vụ";
    }
}

public class Demo {
    static void handle(AppCommand command) {
        if (command instanceof RefreshCache refresh) {
            System.out.println(refresh.description());
        } else if (command instanceof StopService stop) {
            System.out.println(stop.description());
        }
    }

    public static void main(String[] args) {
        handle(new RefreshCache());
        handle(new StopService());
    }
}
```

Pattern matching cho `instanceof` được hoàn thiện trong Java 16 (JEP 394), vì vậy ví dụ trên không cần bật preview. Biến pattern `refresh` hoặc `stop` có kiểu cụ thể sau khi kiểm tra thành công.

Do record không có component, pattern ở đây kiểm tra **kiểu thông điệp**, không trích xuất dữ liệu từ header. Nếu cần đọc payload, hãy dùng record có component.

Không nhầm cú pháp `instanceof` ổn định trong Java 16 với pattern matching cho `switch`, vốn được hoàn thiện ở phiên bản Java sau. Bài này chỉ sử dụng tính năng `instanceof` đã chính thức từ Java 16.

## 8. Record rỗng khác enum singleton như thế nào?

Một record rỗng và một enum chỉ có một hằng đều có thể đại diện cho một tín hiệu không mang dữ liệu, nhưng semantics của chúng khác nhau.

```java
record RefreshRequested() {}

enum RefreshSignal {
    INSTANCE
}
```

| Đặc điểm | Record rỗng | Enum singleton |
| --- | --- | --- |
| Số instance | Có thể tạo nhiều instance bằng `new`. | Một hằng `INSTANCE` cho mỗi enum constant. |
| Equality mặc định | Hai instance cùng record class bằng nhau theo component rỗng. | Các enum constant dùng identity; cùng constant luôn là cùng instance. |
| Constructor công khai | Canonical constructor theo mức truy cập của record. | Không thể gọi constructor enum từ bên ngoài để tạo constant mới. |
| Mở rộng kiểu | Có thể triển khai interface. | Enum cũng có thể triển khai interface. |
| Ý nghĩa thường gặp | Một giá trị stateless có semantics record. | Một lựa chọn hữu hạn hoặc singleton duy nhất. |

Nếu yêu cầu là **chỉ có đúng một instance** và cần identity duy nhất, enum singleton thường diễn đạt ý định rõ hơn:

```java
enum RefreshSignal {
    INSTANCE
}
```

Nếu yêu cầu là một kiểu giá trị stateless có thể được tạo như record và tham gia mô hình dữ liệu chung, record rỗng là lựa chọn hợp lệ. Không nên dùng record rỗng với kỳ vọng nó tự giới hạn số instance thành một.

## 9. Record rỗng khác class thông thường không có field

Có thể khai báo một class không có field, nhưng class đó không tự nhận semantics của record:

```java
final class EmptyMarker {
}
```

Một class thường kế thừa `Object` nếu không khai báo superclass, có `equals()` và `hashCode()` mặc định theo identity. Hai instance của `EmptyMarker` thường không bằng nhau nếu không override `equals()`.

Ngược lại:

```java
record EmptyMarkerRecord() {}
```

hai instance của cùng `EmptyMarkerRecord` bằng nhau theo quy tắc record vì tập component rỗng. Record cũng có canonical constructor và `toString()` được cung cấp theo quy tắc record.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Giá trị stateless, bình đẳng theo kiểu record | Record rỗng. |
| Duy nhất một instance có identity cố định | Enum singleton. |
| Object không có field nhưng cần identity/equality tùy chỉnh | Class thông thường. |
| Thông điệp không payload nhưng có nhiều loại | Các record rỗng triển khai chung interface. |
| Sự kiện từng lần phát sinh phải phân biệt | Record có `eventId` hoặc timestamp, hay class theo semantics identity phù hợp. |

## 10. Những lỗi thường gặp

1. **Bỏ cặp ngoặc tròn:** record không có component vẫn phải viết `record Empty()`.
2. **Mong đợi accessor:** không có component thì không có accessor component.
3. **Nghĩ mọi instance là cùng một object:** `new Empty()` tạo object mới; `==` vẫn so sánh identity.
4. **Nhầm equality với identity:** các instance cùng record class rỗng bằng nhau theo `equals()`, dù tham chiếu khác nhau.
5. **Dùng record rỗng cho sự kiện cần phân biệt từng lần xảy ra:** thêm ID hoặc thời gian nếu mỗi lần phát sinh là một giá trị khác.
6. **Kỳ vọng record rỗng là singleton:** dùng enum nếu cần một instance duy nhất.
7. **Thêm field instance trong body:** trạng thái instance của record phải được mô tả bằng component; header rỗng không cho phép thêm field instance.
8. **Thêm component giả để phân biệt loại command:** cân nhắc dùng kiểu record riêng hoặc interface thay vì payload không có ý nghĩa.

## 11. Bài tập thực hành

1. Khai báo `record NoOperation() {}`. Tạo hai instance và dự đoán kết quả của `==`, `equals()` và `hashCode()`.
2. Khai báo hai record rỗng khác tên, ví dụ `record Start() {}` và `record Stop() {}`. Kiểm tra vì sao hai instance thuộc hai kiểu khác nhau không bằng nhau.
3. Tạo interface `Command` và hai record rỗng triển khai interface đó. Dùng pattern matching `instanceof` để xử lý từng command.
4. So sánh `record EmptyValue() {}` với `enum EmptyValue { INSTANCE }`. Trường hợp nào cần đúng một instance?
5. Thiết kế lại một record rỗng thành record có component `eventId` để phân biệt hai lần phát sinh cùng loại sự kiện.
6. Giải thích vì sao một record rỗng không thể thêm field instance vào body nhưng vẫn có thể khai báo hằng số `static`.

## Ghi nhớ

Record không có component vẫn phải có header với cặp ngoặc tròn, ví dụ `record RefreshRequested() {}`. Java cung cấp canonical constructor không tham số cùng các phương thức record, nhưng không tạo field hay accessor component. Với `equals()` mặc định, mọi instance của cùng record class đều bằng nhau; chúng vẫn là những object riêng biệt nên `==` có thể là `false`. Record rỗng hữu ích cho tín hiệu, command hoặc giá trị stateless; nếu cần một instance duy nhất hãy cân nhắc enum singleton, còn nếu mỗi sự kiện phải phân biệt theo lần phát sinh thì hãy thêm component định danh. Đây là cú pháp và semantics ổn định của record từ Java 16, tiếp tục áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java API – java.lang.Record](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html)
- [OpenJDK JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394)
