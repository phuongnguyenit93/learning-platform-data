# Kiểm tra chữ ký generic bằng các trường hợp biên dịch hợp lệ và không hợp lệ

## 1. Chữ ký generic là một hợp đồng có thể kiểm tra

Một API generic không chỉ cần biên dịch được phần triển khai. Nó còn cần:

- Chấp nhận những cách dùng mà thiết kế muốn hỗ trợ.
- Từ chối những cách dùng vi phạm quan hệ kiểu.
- Giữ đủ thông tin kiểu cho nơi gọi, gồm cả kiểu trả về.
- Không dựa vào cast unchecked để làm các ví dụ có vẻ hợp lệ.

Vì nhiều quy tắc generic được kiểm tra trước khi chương trình chạy, kiểm thử lúc chạy không đủ để xác nhận hợp đồng này. Cần những chương trình nhỏ mà kết quả mong đợi chính là **biên dịch thành công** hoặc **bị từ chối tại một lời gọi cụ thể**.

Một ca không hợp lệ là một thành công của bộ kiểm tra khi trình biên dịch từ chối nó vì đúng lý do đã dự kiến. Đừng đặt các ca này vào cùng lượt biên dịch với chương trình phải chạy bình thường.

Bài dùng `javac` của một JDK hiện đại, đặt mức ngôn ngữ/API mục tiêu là Java 17 bằng `--release 17`. Các tùy chọn được mô tả trong [tài liệu javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).

## 2. Viết ma trận kỳ vọng trước khi chạy trình biên dịch

Giả sử API có ba khả năng:

1. Chép thêm phần tử từ nguồn sang đích phù hợp kiểu.
2. Lấy phần tử đầu và giữ quan hệ kiểu trả về.
3. Tìm phần tử lớn nhất theo thứ tự tự nhiên, kể cả khi khả năng so sánh được kế thừa từ kiểu cha.

Ma trận cần kiểm tra:

| Trường hợp | Kỳ vọng | Quan hệ được kiểm tra |
| --- | --- | --- |
| `List<Integer>` → đích `List<Integer>` | Biên dịch được | Cùng kiểu |
| `List<Integer>` → đích `List<Number>` | Biên dịch được | Đích nhận được kiểu nguồn |
| `List<Integer>` → đích `List<Object>` | Biên dịch được | Đích rộng hơn vẫn dùng được |
| `first(List<Integer>)` gán vào `Integer` | Biên dịch được | Giữ kiểu phần tử |
| `first(List<Integer>)` gán vào `Number` | Biên dịch được | Kết quả dùng được như kiểu cha |
| Tìm max của `Manager` kế thừa `Comparable<Employee>` | Biên dịch được | Cận `Comparable<? super T>` |
| `List<Number>` → đích `List<Integer>` | Bị từ chối | Không ghi mọi Number vào danh sách Integer |
| `first(List<String>)` gán vào `Integer` | Bị từ chối | Không hứa kiểu trả về không liên quan |
| Tìm max tự nhiên của kiểu không `Comparable` | Bị từ chối | Ràng buộc so sánh phải được thỏa mãn |

Ma trận giúp phát hiện hai dạng lỗi thiết kế khác nhau:

- Nếu ca hợp lệ bị từ chối, chữ ký có thể quá chặt.
- Nếu ca không hợp lệ biên dịch được mà không cần cảnh báo, chữ ký có thể làm mất ràng buộc cần giữ hoặc kỳ vọng ban đầu cần được xem lại.

Kết quả phải được giải thích từ quan hệ kiểu, không chỉ điều chỉnh kỳ vọng cho khớp trình biên dịch.

## 3. API được kiểm tra

Lưu tệp `GenericApi.java`:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.NoSuchElementException;

public final class GenericApi {
    private GenericApi() {}

    public static <T> void appendAll(Collection<? extends T> source,
                                      Collection<? super T> destination) {
        destination.addAll(source);
    }

    public static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new NoSuchElementException("List must be nonempty");
        }
        return values.get(0);
    }

    public static <T extends Comparable<? super T>> T maxNatural(
            Collection<? extends T> values) {
        return Collections.max(values);
    }
}
```

Đọc ba chữ ký:

- `appendAll`: nguồn cung cấp giá trị đọc được như `T`; đích nhận được `T`.
- `first`: `T` nối kiểu phần tử nguồn với kiểu trả về.
- `maxNatural`: phần tử phải so sánh được với `T` hoặc kiểu cha của `T`.

`maxNatural` dùng [Collections.max](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#max(java.util.Collection)) để không trộn bài kiểm tra chữ ký với một thuật toán tìm max mới.

Các hàm có điều kiện lúc chạy riêng. `appendAll` yêu cầu đích hỗ trợ thêm phần tử; ví dụ dùng nguồn và đích riêng, không sửa đồng thời. `first` yêu cầu danh sách không rỗng. Chữ ký generic không tự bảo đảm những điều kiện này.

## 4. Các trường hợp phải biên dịch được

Lưu tệp `PositiveCases.java` cùng thư mục:

```java
import java.util.ArrayList;
import java.util.List;

public class PositiveCases {
    static class Employee implements Comparable<Employee> {
        final int level;
        Employee(int level) { this.level = level; }
        @Override
        public int compareTo(Employee other) {
            return Integer.compare(level, other.level);
        }
    }

    static final class Manager extends Employee {
        Manager(int level) { super(level); }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2);
        List<Integer> same = new ArrayList<>();
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();
        GenericApi.appendAll(source, same);
        GenericApi.appendAll(source, numbers);
        GenericApi.appendAll(source, objects);

        Integer firstInteger = GenericApi.first(source);
        Number firstNumber = GenericApi.first(source);
        Manager best = GenericApi.maxNatural(List.of(new Manager(1), new Manager(3)));
        System.out.println("same = " + same);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("first integer = " + firstInteger);
        System.out.println("first as Number = " + firstNumber);
        System.out.println("manager level = " + best.level);
    }
}
```

Những phép gán có kiểu tường minh là một phần của phép kiểm tra:

```java
Integer firstInteger = GenericApi.first(source);
Number firstNumber = GenericApi.first(source);
Manager best = GenericApi.maxNatural(List.of(new Manager(1), new Manager(3)));
```

Chúng xác nhận API cho nơi gọi giữ được kiểu mong muốn. Nếu chỉ dùng `var` hoặc bỏ kết quả trả về, một thay đổi làm kết quả trở nên quá rộng có thể khó nhận ra hơn.

Trường hợp `Manager` cũng quan trọng: nếu thay cận thành `T extends Comparable<T>` trong một chữ ký quá chặt, lớp con có thể bị loại dù khả năng so sánh với kiểu cha là đủ cho thuật toán.

### Biên dịch và chạy trên PowerShell

Ở thư mục chứa các tệp:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d out GenericApi.java PositiveCases.java
if ($LASTEXITCODE -ne 0) { throw "Positive compilation failed" }
java -cp out PositiveCases
if ($LASTEXITCODE -ne 0) { throw "Positive execution failed" }
```

Kết quả chuẩn:

```text
same = [1, 2]
numbers = [1, 2]
objects = [1, 2]
first integer = 1
first as Number = 1
manager level = 3
```

`-Xlint:all` bật các nhóm cảnh báo; `-Werror` khiến cảnh báo làm lượt biên dịch thất bại. Nhờ đó, một lời gọi chỉ “thành công” vì có phép chuyển đổi unchecked không bị xem nhầm là bằng chứng an toàn kiểu.

Mức cảnh báo cần được chọn phù hợp dự án. Với các tệp nhỏ ở bài này, chúng biên dịch sạch với các tùy chọn trên. Đừng thêm `@SuppressWarnings` để biến một ca generic đáng lẽ không an toàn thành ca thành công.

## 5. Ca bị từ chối thứ nhất: nguồn rộng hơn đích

Lưu tệp `WrongDestination.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WrongDestination {
    static void rejected() {
        List<Number> source = List.of(1.5);
        List<Integer> destination = new ArrayList<>();
        GenericApi.appendAll(source, destination);
    }
}
```

Lời gọi ở dòng 8 phải bị từ chối. Nguồn có kiểu tĩnh `List<Number>`, có thể cung cấp một `Double`; đích chỉ nhận `Integer`.

Có thể hình dung các điều kiện đặt lên `T`:

```text
Number phải phù hợp với T
T phải ghi được vào Integer
```

Không có cách chọn `T` thỏa mãn quan hệ đó cho hai biến đã khai báo.

Việc ghi rõ biến nguồn là `List<Number>` rất quan trọng. Nếu chỉ dùng một biểu thức tạo danh sách ngay trong lời gọi, suy luận kiểu có thể chọn đối số kiểu theo ngữ cảnh khác với điều người viết đang muốn kiểm tra. Ca kiểm tra nên cố định đúng giả thiết đầu vào của hợp đồng.

## 6. Ca bị từ chối thứ hai: kết quả không phù hợp

Lưu tệp `WrongReturn.java`:

```java
import java.util.List;

public class WrongReturn {
    static void rejected() {
        List<String> names = List.of("Java");
        Integer value = GenericApi.first(names);
    }
}
```

Lời gọi ở dòng 6 phải bị từ chối. `first` nhận `List<String>`, nên không thể hứa trả một giá trị phù hợp để gán vào `Integer`.

Ca này kiểm tra cả đầu vào lẫn ngữ cảnh đích của lời gọi generic. Chỉ kiểm tra rằng `first(names)` có thể xuất hiện như một câu lệnh sẽ không chứng minh rằng quan hệ kiểu trả về đã được giữ chính xác.

Ngữ cảnh đích có thể tham gia suy luận kiểu, nhưng nó không biến những ràng buộc không tương thích thành hợp lệ. Cơ chế suy luận được đặc tả trong [JLS Chương 18](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html).

## 7. Ca bị từ chối thứ ba: thiếu khả năng so sánh tự nhiên

Lưu tệp `WrongNaturalOrder.java`:

```java
import java.util.List;

public class WrongNaturalOrder {
    record Ticket(int priority) {}

    static void rejected() {
        Ticket best = GenericApi.maxNatural(List.of(new Ticket(1), new Ticket(2)));
    }
}
```

Lời gọi ở dòng 7 phải bị từ chối. Record `Ticket` có trường số không có nghĩa nó tự thực hiện `Comparable<Ticket>`. Thuật toán không thể tự quyết định rằng cần so sánh theo `priority`.

Nếu nghiệp vụ muốn chọn vé theo độ ưu tiên, có thể thiết kế một overload nhận `Comparator<? super T>` hoặc dùng một thuật toán thư viện có comparator. Đừng bỏ ràng buộc khỏi `maxNatural` chỉ để làm ca này biên dịch được, vì thân hàm vẫn cần một quy tắc so sánh hợp lệ.

## 8. Biên dịch từng ca không hợp lệ riêng biệt

Sau khi nhóm hợp lệ đã biên dịch thành công và có `GenericApi.class` trong `out`, chạy từng lệnh riêng:

```powershell
javac --release 17 -Xlint:all -Werror -Xdiags:verbose -encoding UTF-8 -cp out -d out WrongDestination.java
```

```powershell
javac --release 17 -Xlint:all -Werror -Xdiags:verbose -encoding UTF-8 -cp out -d out WrongReturn.java
```

```powershell
javac --release 17 -Xlint:all -Werror -Xdiags:verbose -encoding UTF-8 -cp out -d out WrongNaturalOrder.java
```

Mỗi lệnh trong ví dụ phải trả mã thoát `1` và báo lỗi tại lời gọi được đánh dấu ở trên. Đây là kết quả dự kiến của các ca không hợp lệ, không phải lỗi cần “sửa” bằng cast.

Thông báo thường mô tả những ràng buộc không tương thích, chẳng hạn không thể áp dụng `appendAll` cho `List<Number>` và `List<Integer>`, hoặc biến suy luận `T` có các cận mâu thuẫn. Nội dung chẩn đoán đầy đủ có thể khác theo JDK, ngôn ngữ hiển thị và tùy chọn compiler; không dùng toàn bộ chuỗi thông báo như một chuẩn bất biến.

Không dùng `javac *.java` trong thư mục chứa cả các ca cố tình sai rồi mong toàn bộ lượt biên dịch thành công. Liệt kê đúng nhóm tệp của từng phép kiểm tra.

## 9. Không phải mọi lượt biên dịch thất bại đều chứng minh hợp đồng đúng

Ví dụ một ca đáng lẽ bị từ chối vì kiểu có thể thất bại vì:

- Chưa biên dịch `GenericApi` hoặc đặt sai classpath.
- Thiếu import, sai tên tệp hoặc thiếu dấu ngoặc.
- Gọi sai tên phương thức.
- Dùng một JDK hoặc `--release` không phù hợp với cú pháp đang kiểm tra.
- Không ghi được thư mục đầu ra.

Nếu chỉ kiểm tra “mã thoát khác 0”, những lỗi này có thể làm ca kiểm tra báo thành công giả.

Với bộ ví dụ này, cần đối chiếu:

| Tệp | Vị trí lời gọi | Nguyên nhân phải xuất hiện trong chẩn đoán |
| --- | --- | --- |
| `WrongDestination.java` | Dòng 8 | Quan hệ nguồn `Number` và đích `Integer` không thỏa chữ ký `appendAll` |
| `WrongReturn.java` | Dòng 6 | Kiểu nguồn `String` không phù hợp kết quả yêu cầu `Integer` |
| `WrongNaturalOrder.java` | Dòng 7 | `Ticket` không thỏa cận `Comparable<? super T>` |

Dòng và cột là thông tin định vị của phiên bản tệp hiện tại; phải cập nhật nếu sửa tệp. Không nên cố giữ nguyên hàng loạt dòng trống chỉ để một số dòng cũ tiếp tục khớp.

Một kiểm tra tự động đáng tin cần vừa xác nhận nhóm hợp lệ thành công, vừa xác nhận nhóm không hợp lệ có chẩn đoán lỗi đúng tại biểu thức mục tiêu. Khi công cụ hỗ trợ đối tượng chẩn đoán có cấu trúc, có thể dùng loại lỗi, nguồn và vị trí thay vì so khớp nguyên văn thông báo.

## 10. Tổ chức để có thể đưa vào CI

Có thể tách nguồn theo ý nghĩa:

```text
api/       → các lớp API được kiểm tra
positive/  → các chương trình phải biên dịch được
negative/  → các chương trình phải bị từ chối
```

Quy trình CI tương ứng:

1. Ghi nhận phiên bản `javac`, mức `--release`, classpath và các tùy chọn cảnh báo.
2. Biên dịch API và các ca hợp lệ vào thư mục đầu ra dành cho lượt kiểm tra.
3. Nếu nhóm hợp lệ thất bại, dừng và báo lỗi thiết lập hoặc hợp đồng bị thu hẹp ngoài ý muốn.
4. Biên dịch từng ca không hợp lệ riêng, giữ chẩn đoán cùng tên ca.
5. Một ca không hợp lệ biên dịch được phải làm bộ kiểm tra thất bại.
6. Một ca thất bại vì lỗi thiết lập hoặc lỗi khác với mục tiêu cũng phải được báo là không đạt.

Khi tự động hóa bằng `javax.tools.JavaCompiler`, có thể lấy các `Diagnostic` có cấu trúc. Khi dùng công cụ kiểm tra biên dịch chuyên dụng, phải cấu hình cùng phiên bản Java và classpath thực tế. Bài không cần thư viện bổ sung; `javac` là đủ để thực hành nguyên tắc.

`--release 17` đặt mức ngôn ngữ, API chuẩn và class file mục tiêu phù hợp; nó không có nghĩa đang chạy chính trình biên dịch JDK 17. Nếu phải hỗ trợ nhiều compiler/JDK, cần chạy các lượt tương ứng thay vì chỉ đổi `--release` rồi coi mọi hành vi chẩn đoán giống hệt nhau.

Không thêm tệp cố tình sai vào source set sản phẩm hoặc bộ biên dịch thông thường mà không có một bước kiểm tra riêng hiểu kỳ vọng bị từ chối của chúng.

## 11. Giữ giả thiết của ca kiểm tra đủ rõ

### Dùng kiểu biến và kết quả tường minh khi đó là điều cần kiểm tra

`Manager best = ...` kiểm tra API giữ được kiểu lớp con. `var best = ...` có thể vẫn biên dịch dù một sửa đổi làm kiểu trả về rộng hơn điều thiết kế muốn.

### Mỗi ca không hợp lệ chỉ nên nhắm một quan hệ chính

Một tệp chứa nhiều lỗi có thể làm chẩn đoán dây chuyền che mất nguyên nhân. Ba tệp sai trong bài được tách để mỗi ca có một lời gọi cần bị từ chối.

### Không biến ca không hợp lệ thành hợp lệ bằng thay đổi giả thiết

Đổi `List<Number>` thành `List<Integer>` trong ca nguồn–đích sẽ tạo một bài toán khác, không chứng minh API từ chối ghi số bất kỳ vào danh sách số nguyên.

### Xét suy luận kiểu thay vì chỉ nhìn tên `T`

Một `T` xuất hiện ở nhiều tham số không nhất thiết yêu cầu mọi đối tượng có cùng lớp thực tế. Trình biên dịch có thể chọn một kiểu cha chung nếu ràng buộc cho phép. Kỳ vọng từ chối phải dựa trên quan hệ generic đầy đủ, gồm tính bất biến của container và ngữ cảnh trả về.

### Không để cảnh báo mất an toàn kiểu bị bỏ qua

Một cast unchecked hoặc kiểu thô có thể làm một lời gọi “qua được compiler” mà đã phá bảo đảm của API. Các ca hợp lệ nên thành công sạch theo chính sách cảnh báo đã chọn.

## 12. Kiểm tra biên dịch và kiểm thử lúc chạy bổ sung cho nhau

Các ca trong bài xác nhận giới hạn kiểu, không chứng minh toàn bộ hành vi API:

| Vấn đề | Cần loại bằng chứng nào? |
| --- | --- |
| Có chép `Integer` sang đích `Number` được không? | Kiểm tra biên dịch |
| Có từ chối chép `Number` sang đích `Integer` không? | Ca biên dịch bị từ chối |
| Kết quả `first` có giữ kiểu phần tử không? | Phép gán có kiểu tường minh khi biên dịch |
| Thứ tự phần tử sau sao chép có đúng không? | Kiểm thử lúc chạy |
| Đích không hỗ trợ thêm phần tử thì xảy ra gì? | Hợp đồng và kiểm thử lúc chạy |
| Nguồn rỗng, `null`, phần tử `null` được xử lý ra sao? | Hợp đồng và kiểm thử lúc chạy |

Hệ thống kiểu chứng minh một số quan hệ trước khi chạy. Nó không thay thế việc kiểm tra trạng thái dữ liệu và khả năng của đối tượng cụ thể khi thực thi.

## 13. Tự kiểm tra

**Câu 1.** Một ca không hợp lệ báo “không tìm thấy GenericApi” có được xem là đã kiểm tra ràng buộc generic thành công không?

Không. Nó thất bại vì thiết lập không đúng, chưa tới quan hệ kiểu cần kiểm tra.

**Câu 2.** Vì sao phải giữ các ca hợp lệ khi đã có nhiều ca bị từ chối?

Một chữ ký quá chặt có thể từ chối cả trường hợp cần hỗ trợ. Chỉ kiểm tra việc từ chối không chứng minh API đủ linh hoạt.

**Câu 3.** Vì sao nên dùng `Manager best = ...` thay vì chỉ bỏ qua kết quả của hàm max?

Phép gán xác nhận kết quả vẫn mang kiểu lớp con mà hợp đồng muốn giữ, không chỉ xác nhận lời gọi có thể xuất hiện.

**Câu 4.** Có nên so khớp nguyên văn toàn bộ lỗi `javac` giữa mọi JDK không?

Không. Cần tập trung vào lỗi đúng quan hệ kiểu, nguồn và vị trí mục tiêu. Cách diễn đạt chẩn đoán có thể thay đổi.

**Câu 5.** Các ca biên dịch có chứng minh `appendAll` làm việc với mọi đối tượng `Collection` không?

Không. Generic bảo đảm tương thích kiểu; đích vẫn có thể không hỗ trợ thêm, dữ liệu có thể vi phạm điều kiện về `null`, hoặc có sửa đổi đồng thời. Các vấn đề đó cần hợp đồng và bằng chứng lúc chạy riêng.
