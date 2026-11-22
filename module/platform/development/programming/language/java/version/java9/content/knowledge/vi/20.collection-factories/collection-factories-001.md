# Tạo List bằng List.of

Từ Java 9, interface `java.util.List` cung cấp các phương thức factory static `List.of(...)` để tạo danh sách từ những phần tử đã biết. Cách viết ngắn gọn, thể hiện rõ dữ liệu khởi tạo và trả về một danh sách không cho phép thay đổi cấu trúc hoặc thay thế phần tử.

`List.of(...)` phù hợp khi danh sách được dùng như dữ liệu đầu vào, cấu hình, tập giá trị cố định hoặc kết quả mà caller chỉ cần đọc. Hiểu đúng đặc tính của nó giúp tránh lỗi khi mã phía sau cố thêm, xóa hoặc thay thế phần tử.

## 1. Cách tạo List bằng List.of

`List.of(...)` là phương thức static generic được khai báo trong interface `List`. Gọi phương thức qua tên interface:

```java
import java.util.List;

List<String> languages = List.of("Java", "Kotlin", "Scala");
List<Integer> scores = List.of(8, 9, 10);
List<String> empty = List.of();
```

Trình biên dịch suy luận kiểu phần tử từ các đối số hoặc từ kiểu đích của biến. Trong ví dụ trên, kiểu lần lượt là `List<String>`, `List<Integer>` và `List<String>`.

Các dạng gọi thường gặp:

| Cách gọi | Kết quả |
|---|---|
| `List.of()` | Danh sách rỗng |
| `List.of("Java")` | Danh sách có một phần tử |
| `List.of("Java", "Kotlin")` | Danh sách có hai phần tử |
| `List.of(a, b, c, ...)` | Danh sách chứa các đối số theo thứ tự |

API có các overload cho 0 đến 10 phần tử và overload varargs cho số lượng lớn hơn. Caller không cần tự tạo mảng hoặc gọi constructor của một lớp triển khai cụ thể.

`List.of` trả về kiểu interface `List<E>`. Hãy khai báo biến theo abstraction này; không ép kiểu kết quả sang `ArrayList` hoặc phụ thuộc vào tên lớp triển khai nội bộ.

## 2. Đặc tính của danh sách được tạo

### Không cho phép sửa danh sách

Danh sách từ `List.of` là *unmodifiable*. Những thao tác làm thay đổi danh sách đều không được hỗ trợ, kể cả khi thao tác có vẻ không làm thay đổi dữ liệu:

- `add` và `addAll`: thêm phần tử.
- `remove` và `removeAll`: xóa phần tử.
- `set`: thay thế phần tử tại một vị trí.
- `clear`, `replaceAll`, `sort`: các thao tác cập nhật nội dung.

Khi gọi thao tác sửa đổi, danh sách ném `UnsupportedOperationException`. Đừng chờ đến lúc chạy mới phát hiện: nếu nghiệp vụ cần thêm, xóa hoặc sắp xếp tại chỗ, hãy tạo một danh sách mutable riêng.

### Giữ thứ tự và cho phép phần tử trùng nhau

Danh sách giữ thứ tự phần tử theo thứ tự truyền vào. Phần tử trùng lặp được phép:

```java
List<Integer> values = List.of(5, 8, 8, 13);
// [5, 8, 8, 13]
```

`List.of` không tự loại bỏ phần tử trùng như một tập hợp. Nếu yêu cầu nghiệp vụ là các giá trị duy nhất, hãy chọn abstraction phù hợp như `Set`.

### Không chấp nhận null

Mọi phần tử truyền vào phải khác `null`. Nếu có phần tử `null`, quá trình tạo danh sách ném `NullPointerException` ngay tại lời gọi `List.of`:

```java
List<String> values = List.of("Java", null); // Ném NullPointerException
```

Nếu dữ liệu nguồn có thể chứa `null`, hãy xác định quy tắc xử lý trước khi tạo danh sách: từ chối dữ liệu, lọc phần tử null hoặc chuyển đổi sang một giá trị đại diện phù hợp. Không dùng `List.of` khi hợp đồng dữ liệu yêu cầu giữ lại `null`.

### Không phải deep immutable

`List.of` ngăn caller thay đổi cấu trúc danh sách và thay thế tham chiếu phần tử. Nó không làm cho chính các object bên trong trở thành bất biến.

Ví dụ, nếu danh sách chứa các object mutable, caller vẫn có thể gọi setter trên object đó và quan sát trạng thái object thay đổi. Vì vậy, “unmodifiable list” không đồng nghĩa với “toàn bộ object graph bất biến”.

Các danh sách này cũng là value-based. Không dựa vào việc hai lần gọi factory phải trả về cùng một object theo phép so sánh tham chiếu `==`; tránh dùng identity hash code hoặc đồng bộ hóa bằng chính instance của danh sách.

## 3. Ví dụ Java chạy được

Ví dụ sau tạo danh sách tên ngôn ngữ, đọc số phần tử, thử thêm và thay thế phần tử, tạo danh sách có giá trị trùng nhau, danh sách rỗng và kiểm tra trường hợp có `null`.

```java
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình", "Chi");
        System.out.println(names);
        System.out.println(names.size());

        try {
            names.add("Dũng");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Không thể thêm phần tử");
        }

        try {
            names.set(0, "Hà");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Không thể thay thế phần tử");
        }

        List<Integer> scores = List.of(8, 9, 9);
        System.out.println(scores);

        List<String> empty = List.of();
        System.out.println(empty.isEmpty());

        try {
            List.of("Java", null);
        } catch (NullPointerException exception) {
            System.out.println("List.of không chấp nhận null");
        }
    }
}
```

Lưu mã vào tệp `Main.java`. Dùng JDK 17 trở lên để biên dịch và chạy:

```bash
javac Main.java
java Main
```

Kết quả stdout:

```text
[An, Bình, Chi]
3
Không thể thêm phần tử
Không thể thay thế phần tử
[8, 9, 9]
true
List.of không chấp nhận null
```

Phân tích:

1. `List.of("An", "Bình", "Chi")` tạo danh sách theo đúng thứ tự đối số.
2. `size()` và `isEmpty()` là thao tác đọc nên dùng được trên danh sách không cho phép sửa.
3. `add` và `set` đều làm thay đổi danh sách, do đó ném `UnsupportedOperationException`.
4. Danh sách `scores` vẫn giữ cả hai giá trị `9` vì danh sách cho phép phần tử trùng.
5. `List.of()` tạo danh sách rỗng; biến nhận kết quả có kiểu đích `List<String>` nên kiểu phần tử được suy luận là `String`.
6. `List.of("Java", null)` ném `NullPointerException` khi tạo danh sách, không phải khi đọc phần tử.

## 4. Chọn List.of hay cách tạo List khác?

Không phải mọi danh sách đều nên được tạo bằng `List.of`. Hãy chọn theo nguồn dữ liệu và quyền thay đổi cần thiết.

| Nhu cầu | Cách phù hợp | Đặc điểm |
|---|---|---|
| Khai báo danh sách từ các giá trị đã biết, chỉ đọc | `List.of(a, b, c)` | Không cho sửa, không nhận null |
| Cần danh sách mutable để thêm, xóa, thay thế | `new ArrayList<>(List.of(a, b))` | Tạo bản sao có thể sửa |
| Có sẵn một Collection và muốn tạo danh sách không cho sửa | `List.copyOf(collection)` | Có từ Java 10, không nhận null |
| Cần một view không cho sửa trên một List hiện có | `Collections.unmodifiableList(list)` | View phản ánh thay đổi qua list gốc |
| Cần danh sách có kích thước cố định dựa trên mảng | `Arrays.asList(array)` | Có thể dùng `set`; không thể thêm hoặc xóa |

### List.of và Arrays.asList

`Arrays.asList(array)` tạo một danh sách có kích thước cố định và được hỗ trợ bởi mảng truyền vào. Caller có thể thay thế phần tử bằng `set`; thay đổi phần tử trong mảng cũng được phản ánh qua danh sách. Không thể thêm hoặc xóa phần tử.

`List.of(...)` tạo danh sách không cho phép sửa đổi. Cả `set`, thêm và xóa đều không được hỗ trợ. Danh sách không cho phép phần tử `null`.

Chọn `List.of` khi cần một danh sách giá trị cố định, không cần liên kết với mảng nguồn. Chọn `Arrays.asList` khi cần view có kích thước cố định gắn với mảng và muốn thay thế phần tử.

### List.of và List.copyOf

`List.of(a, b, c)` nhận các phần tử riêng lẻ. Nếu đã có một collection và muốn tạo danh sách không cho sửa từ các phần tử của collection đó, dùng `List.copyOf(collection)` (Java 10 trở lên).

`List.of(collection)` có ý nghĩa khác: nó tạo danh sách có một phần tử, chính là object collection được truyền vào. Nó không tự trải các phần tử bên trong collection ra danh sách mới.

Cả `List.of` và `List.copyOf` đều không chấp nhận phần tử `null` và trả về danh sách không cho phép sửa đổi.

### Khi cần danh sách mutable

Nếu cần thay đổi danh sách sau khi tạo, hãy tạo một bản sao mutable:

```java
List<String> fixed = List.of("Java", "Kotlin");
List<String> editable = new ArrayList<>(fixed);

editable.add("Scala");
editable.set(0, "Java 21");

System.out.println(editable);
```

Đoạn mã này cần thêm import `java.util.ArrayList`. Bản `editable` có thể sửa độc lập; thao tác trên nó không thay đổi danh sách `fixed`.

## 5. Những trường hợp dễ nhầm

### Truyền một collection vào List.of

Khi truyền một collection làm một đối số, collection đó trở thành một phần tử của danh sách:

```java
List<String> source = List.of("A", "B");
List<List<String>> wrapped = List.of(source);

System.out.println(wrapped.size()); // 1
System.out.println(wrapped.get(0));  // [A, B]
```

Nếu mục tiêu là tạo danh sách mới gồm các phần tử của `source`, dùng `List.copyOf(source)` hoặc một constructor thích hợp.

### Truyền mảng và varargs

`List.of` có overload varargs. Với mảng tham chiếu như `String[]`, lời gọi `List.of(array)` thường truyền các phần tử mảng như các đối số varargs. Cần đọc kiểu generic và cách overload được chọn để tránh nhầm giữa một phần tử là mảng và một danh sách chứa các phần tử của mảng.

Với mảng nguyên thủy như `int[]`, mảng không tự chuyển thành từng `Integer`. Nếu muốn `List<Integer>`, có thể chuyển qua stream:

```java
int[] numbers = {1, 2, 3};
List<Integer> values = java.util.Arrays.stream(numbers)
        .boxed()
        .toList(); // Java 16+
```

`Stream.toList()` có từ Java 16 và trả về danh sách không cho sửa đổi. Nếu cần danh sách mutable, hãy thu thập vào `ArrayList` hoặc tạo bản sao mutable.

### Không ép kiểu sang lớp triển khai

Không viết mã giả định kết quả là `ArrayList`:

```java
List<String> names = List.of("An", "Bình");
// ArrayList<String> copy = (ArrayList<String>) names; // Sai thiết kế
```

`List.of` chỉ cam kết kiểu trả về `List` và hợp đồng không cho sửa. Hãy lập trình theo interface và không phụ thuộc vào lớp triển khai nội bộ.

## 6. Các lỗi thường gặp

- **Gọi add, remove hoặc set:** danh sách không cho sửa và sẽ ném `UnsupportedOperationException`. Tạo `ArrayList` nếu cần cập nhật.
- **Truyền null:** `List.of` ném `NullPointerException`. Kiểm tra hoặc xử lý null trước khi tạo.
- **Cho rằng phần tử trùng sẽ bị loại:** `List` giữ các phần tử trùng; dùng `Set` nếu cần duy nhất.
- **Nhầm List.of(collection) với List.copyOf(collection):** lời gọi đầu tạo danh sách một phần tử là collection; lời gọi sau sao chép các phần tử của collection.
- **Nhầm unmodifiable với deep immutable:** object mutable bên trong vẫn có thể đổi trạng thái.
- **Dùng Arrays.asList khi cần danh sách có thể thêm/xóa:** danh sách đó chỉ có kích thước cố định; dùng `new ArrayList<>(...)` khi cần mutable.
- **Phụ thuộc vào identity của kết quả factory:** danh sách value-based, không dùng phép so sánh tham chiếu hoặc khóa đồng bộ dựa trên instance.

## 7. Checklist khi sử dụng

- Danh sách chỉ cần đọc sau khi tạo hay cần thêm, xóa, thay thế?
- Các phần tử có thể chứa `null` không?
- Thứ tự và phần tử trùng có được phép không?
- Nguồn là các giá trị rời hay một collection đã tồn tại?
- Caller có đang nhầm danh sách không cho sửa với object bên trong bất biến không?
- Kiểu khai báo có dùng abstraction `List<E>` thay vì phụ thuộc lớp triển khai không?

`List.of` là lựa chọn rõ ràng cho danh sách được khởi tạo từ những giá trị đã biết và không cần sửa đổi. Nắm chắc giới hạn về null, khả năng sửa đổi, thứ tự và generic giúp API dễ đọc, tránh lỗi runtime và giữ đúng ý nghĩa của dữ liệu trong ứng dụng Java hiện đại.
