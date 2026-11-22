# Tạo Set bằng Set.of

Từ Java 9, interface `Set` cung cấp các phương thức factory tĩnh `Set.of(...)` để tạo một tập hợp nhỏ, có sẵn các phần tử và không cho phép thay đổi cấu trúc sau khi tạo. API này vẫn được hỗ trợ trong các phiên bản Java hiện đại, bao gồm Java 17 và Java 21.

`Set.of` phù hợp khi tập hợp là một tập giá trị cố định như quyền truy cập, trạng thái, tên ngày trong tuần hoặc danh sách mã được phép. Cú pháp ngắn gọn, thể hiện rõ ý định và tránh phải tạo một `HashSet` rồi thêm từng phần tử.

## 1. Cú pháp và các overload

Có thể tạo Set rỗng, Set một phần tử hoặc Set chứa nhiều phần tử:

~~~java
import java.util.Set;

Set<String> empty = Set.of();
Set<String> one = Set.of("READ");
Set<String> permissions = Set.of("READ", "WRITE", "EXPORT");
Set<Integer> levels = Set.of(1, 2, 3, 4);
~~~

API có các overload nhận từ 0 đến 10 phần tử và một overload varargs cho số lượng phần tử lớn hơn. Trình biên dịch chọn overload phù hợp dựa trên số đối số tại vị trí gọi.

Kiểu phần tử thường được suy luận từ các đối số hoặc từ kiểu đích:

~~~java
Set<String> names = Set.of("An", "Bình", "Chi");
var codes = Set.of("VN", "JP", "SG");
~~~

Trong ví dụ đầu, kiểu phần tử là `String`. Trong ví dụ thứ hai, `var` suy luận kiểu biến `codes` thành `Set<String>`.

Nếu cần tạo một tập hợp từ mảng, có thể truyền các phần tử qua varargs:

~~~java
String[] values = {"RED", "GREEN", "BLUE"};
Set<String> colors = Set.of(values);
~~~

Lời gọi trên truyền các phần tử của mảng vào factory. Nếu mảng có phần tử trùng nhau hoặc chứa `null`, việc tạo Set sẽ thất bại theo các quy tắc ở phần sau.

## 2. Set được tạo ra là unmodifiable

Set trả về từ `Set.of` là **unmodifiable Set**. Sau khi tạo, không thể thêm, xóa hoặc thay thế phần tử bằng các phương thức sửa đổi của Set.

~~~java
Set<String> roles = Set.of("ADMIN", "EDITOR");

roles.add("VIEWER"); // UnsupportedOperationException
~~~

Lệnh `add` ném `UnsupportedOperationException`. Các thao tác sửa đổi khác như `remove`, `clear`, `removeAll`, `retainAll` hoặc `addAll` cũng không phải cách để cập nhật Set này.

Cần phân biệt hai khái niệm:

- **Unmodifiable:** người gọi không thể sửa cấu trúc tập hợp thông qua API của nó.
- **Mutable:** tập hợp cho phép thêm hoặc xóa phần tử sau khi tạo.

`Set.of` tạo Set unmodifiable. Nếu nghiệp vụ cần cập nhật tập hợp, hãy tạo một bản sao mutable, chẳng hạn:

~~~java
import java.util.HashSet;
import java.util.Set;

Set<String> fixedRoles = Set.of("ADMIN", "EDITOR");
Set<String> editableRoles = new HashSet<>(fixedRoles);

editableRoles.add("VIEWER");
~~~

Ở đây `fixedRoles` vẫn không thay đổi; `editableRoles` là một `HashSet` mới có thể cập nhật độc lập.

Unmodifiable chỉ bảo vệ cấu trúc của Set. Nếu phần tử bên trong là đối tượng mutable, trạng thái của chính đối tượng đó vẫn có thể thay đổi. Vì vậy đây không phải cơ chế deep copy hay deep immutability.

## 3. Không chấp nhận phần tử trùng lặp

Set không lưu các phần tử trùng nhau. Tuy nhiên, factory `Set.of` không âm thầm loại bỏ phần tử trùng lặp trong danh sách đối số. Nếu có hai phần tử bằng nhau theo `equals`, lời gọi sẽ ném `IllegalArgumentException`.

~~~java
Set<String> values = Set.of("A", "B", "A");
// IllegalArgumentException
~~~

Điều này giúp phát hiện sớm dữ liệu đầu vào có vấn đề. Nếu dữ liệu ban đầu có thể chứa phần tử trùng và mục tiêu là loại bỏ trùng lặp, hãy dùng một cách tạo Set có chủ đích như:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

List<String> input = List.of("A", "B", "A");
Set<String> uniqueValues = new HashSet<>(input);
~~~

Khi dùng `HashSet`, các phần tử trùng lặp được hợp nhất theo quy tắc của Set. Thứ tự duyệt của `HashSet` cũng không được đảm bảo.

Với đối tượng tự định nghĩa, cần triển khai `equals` và `hashCode` đúng hợp đồng để xác định phần tử trùng lặp nhất quán.

## 4. Không chấp nhận null

`Set.of` không cho phép phần tử `null`. Nếu bất kỳ đối số phần tử nào là `null`, lời gọi sẽ ném `NullPointerException`.

~~~java
Set<String> values = Set.of("A", null);
// NullPointerException
~~~

Quy tắc này áp dụng cho cả overload nhiều đối số và overload varargs. Hãy kiểm tra hoặc chuẩn hóa dữ liệu đầu vào trước khi gọi factory nếu nguồn dữ liệu có thể chứa `null`.

Nếu nghiệp vụ cho phép `null`, cần chọn một triển khai Set phù hợp với yêu cầu đó và xác định rõ ý nghĩa của giá trị `null`; không thể dùng `Set.of` để biểu diễn trường hợp này.

## 5. Không có cam kết về thứ tự duyệt

`Set` biểu diễn tập hợp, không phải danh sách. `Set.of` không cam kết thứ tự phần tử khi duyệt bằng vòng lặp, iterator hoặc stream.

~~~java
Set<String> codes = Set.of("VN", "JP", "SG");

for (String code : codes) {
    System.out.println(code);
}
~~~

Không được dựa vào thứ tự đầu ra của đoạn code trên. Thứ tự có thể khác giữa các lần chạy hoặc các phiên bản triển khai. Nếu ứng dụng cần thứ tự ổn định, hãy dùng cấu trúc có hợp đồng về thứ tự, ví dụ `List.of` cho một danh sách cố định hoặc `LinkedHashSet` khi cần một Set có thứ tự chèn.

Không nên chuyển Set thành chuỗi rồi so sánh kết quả dựa trên thứ tự hiển thị. Khi kiểm tra nội dung, hãy dùng `contains`, `size` hoặc so sánh Set theo ngữ nghĩa tập hợp.

## 6. Ví dụ chạy được với Java 17+

Tạo file **SetOfDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Set;

public class SetOfDemo {
    public static void main(String[] args) {
        Set<String> empty = Set.of();
        Set<String> single = Set.of("READ");
        Set<String> permissions = Set.of("READ", "WRITE", "EXPORT");

        System.out.println(empty.size());
        System.out.println(single.contains("READ"));
        System.out.println(permissions.contains("WRITE"));
        System.out.println(permissions.size());

        try {
            permissions.add("ADMIN");
        } catch (UnsupportedOperationException exception) {
            System.out.println("unmodifiable");
        }

        try {
            Set.of("READ", "WRITE", "READ");
        } catch (IllegalArgumentException exception) {
            System.out.println("duplicate rejected");
        }

        try {
            Set.of("READ", null);
        } catch (NullPointerException exception) {
            System.out.println("null rejected");
        }

        Set<String> editable = new HashSet<>(permissions);
        editable.add("ADMIN");
        System.out.println(editable.contains("ADMIN"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SetOfDemo.java
java SetOfDemo
~~~

Kết quả stdout:

~~~text
0
true
true
3
unmodifiable
duplicate rejected
null rejected
true
~~~

Kết quả không phụ thuộc thứ tự duyệt của Set vì chương trình chỉ in kích thước, kết quả kiểm tra thành viên và thông báo sau khi bắt exception.

## 7. Set.of, HashSet và Set.copyOf

| Cách tạo | Khả năng sửa đổi | Xử lý phần tử trùng | Mục đích |
|---|---|---|---|
| `Set.of(a, b, c)` | Unmodifiable | Ném `IllegalArgumentException` | Tạo tập giá trị cố định trực tiếp từ đối số |
| `new HashSet<>(collection)` | Mutable | Tự loại bỏ trùng | Tạo tập hợp có thể cập nhật từ dữ liệu có sẵn |
| `Set.copyOf(collection)` | Unmodifiable | Chỉ giữ một phần tử trong các phần tử trùng | Tạo bản Set unmodifiable từ Collection |

Một số điểm cần nhớ khi chọn API:

- Dùng `Set.of` khi danh sách đối số đã biết và phải không có phần tử trùng hoặc `null`.
- Dùng `new HashSet<>(collection)` khi cần một Set mutable và muốn loại bỏ phần tử trùng.
- Dùng `Set.copyOf(collection)` khi đã có Collection và muốn tạo Set unmodifiable. API này không có cùng chính sách duplicate với `Set.of`: phần tử trùng trong Collection nguồn được gộp lại.
- Cả `Set.of` và `Set.copyOf` đều không cho phép phần tử `null`.

## 8. Đặc tính value-based

Các Set được tạo bởi factory tĩnh như `Set.of` là value-based. Hãy sử dụng chúng theo giá trị nội dung thay vì dựa vào danh tính đối tượng.

Không nên:

- So sánh hai kết quả factory bằng `==` để kết luận chúng có cùng nội dung.
- Dùng `System.identityHashCode` làm định danh nội dung.
- Dùng chính instance Set làm monitor để đồng bộ hóa bằng `synchronized`.

Hãy dùng `equals` để so sánh nội dung và các API của Set để kiểm tra thành viên. Factory có thể tái sử dụng instance phù hợp hoặc tạo instance khác; code không nên phụ thuộc vào lựa chọn đó.

## 9. Lỗi thường gặp

**Gọi add hoặc remove để cập nhật Set.of**

Các thao tác sửa đổi ném `UnsupportedOperationException`. Hãy tạo `HashSet` mới nếu cần thay đổi tập hợp.

**Truyền dữ liệu có phần tử trùng**

`Set.of` ném `IllegalArgumentException`; nó không tự loại bỏ trùng lặp. Nếu muốn loại trùng, tạo `HashSet` từ Collection.

**Truyền null**

`Set.of` ném `NullPointerException`. Xác thực đầu vào hoặc chọn cấu trúc khác nếu `null` có ý nghĩa trong nghiệp vụ.

**Giả định thứ tự theo thứ tự truyền vào**

Set không đảm bảo thứ tự duyệt. Nếu cần thứ tự, chọn `List` hoặc một Set có hợp đồng thứ tự phù hợp.

**Cho rằng unmodifiable đồng nghĩa với deep immutable**

Set không cho thêm hoặc xóa phần tử, nhưng đối tượng mutable nằm bên trong vẫn có thể đổi trạng thái. Cân nhắc tính bất biến của cả phần tử nếu cần dữ liệu ổn định.

## 10. Checklist sử dụng

Trước khi dùng `Set.of`, xác nhận:

- Tập hợp được tạo từ một số lượng giá trị đã biết tại thời điểm gọi.
- Không có phần tử `null`.
- Không có hai phần tử bằng nhau theo `equals`.
- Ứng dụng không cần thêm hoặc xóa phần tử sau khi tạo.
- Ứng dụng không phụ thuộc vào thứ tự duyệt.
- Code không dựa vào identity của instance Set.

`Set.of` là factory hiện đại, gọn và rõ nghĩa để tạo Set unmodifiable. Hãy dùng nó cho dữ liệu cố định, đồng thời chọn `HashSet`, `LinkedHashSet` hoặc `List` khi yêu cầu về khả năng sửa đổi hay thứ tự khác đi.
