# Quy tắc không chấp nhận null trong các collection factory của Java

## 1. Ý nghĩa của quy tắc

Trong Java, một số API tạo collection được thiết kế để nhận các phần tử và ánh xạ hợp lệ ngay tại thời điểm tạo. Các API này từ chối giá trị `null` thay vì giữ một phần tử hoặc khóa không có đối tượng tham chiếu.

Quy tắc này đặc biệt quan trọng với các factory method gọn được giới thiệu trong Java 9:

- `List.of(...)` không nhận phần tử `null`.
- `Set.of(...)` không nhận phần tử `null`.
- `Map.of(...)` và `Map.ofEntries(...)` không nhận khóa hoặc giá trị `null`.
- `Map.entry(key, value)` cũng từ chối khóa và giá trị `null`.

Các phương thức `copyOf` được bổ sung trong Java 10 cũng áp dụng quy tắc tương tự:

- `List.copyOf(collection)` từ chối phần tử `null`.
- `Set.copyOf(collection)` từ chối phần tử `null`.
- `Map.copyOf(map)` từ chối khóa hoặc giá trị `null`.

Khi đầu vào vi phạm quy tắc, API ném `NullPointerException`. Vì thế, nếu một collection nguồn có chứa `null`, việc chuyển nó bằng `copyOf` sẽ thất bại tại lúc tạo collection đích.

## 2. Quy tắc theo từng loại collection

### List

`List.of` cho phép tạo danh sách ngắn gọn, giữ thứ tự và cho phép phần tử trùng lặp, nhưng không cho phép `null`:

~~~java
List<String> languages = List.of("Java", "Kotlin");
List<String> invalid = List.of("Java", null); // NullPointerException
~~~

Một danh sách được tạo bằng `List.of` là không thể thay đổi cấu trúc: không thể thêm, xóa hoặc thay thế phần tử. Danh sách này cũng không chấp nhận `null` ngay từ lúc khởi tạo.

`List.copyOf` tạo một danh sách không thể thay đổi từ collection hiện có. Nếu collection nguồn chứa `null`, phương thức ném `NullPointerException`:

~~~java
List<String> source = new ArrayList<>();
source.add("Java");
source.add(null);

List<String> copy = List.copyOf(source); // NullPointerException
~~~

Các phần tử trùng lặp trong List vẫn được giữ nguyên. Quy tắc không nhận `null` không đồng nghĩa với quy tắc loại bỏ phần tử trùng lặp.

### Set

`Set.of` và `Set.copyOf` cũng từ chối `null`. Ngoài ra, `Set.of` từ chối phần tử trùng lặp và ném `IllegalArgumentException` trong trường hợp đó:

~~~java
Set<String> languages = Set.of("Java", "Kotlin");
Set<String> invalidNull = Set.of("Java", null); // NullPointerException
Set<String> invalidDuplicate = Set.of("Java", "Java"); // IllegalArgumentException
~~~

`Set.copyOf` tạo Set không thể thay đổi và không chấp nhận phần tử `null`. Nếu collection nguồn có nhiều phần tử bằng nhau, Set đích chỉ giữ một phần tử đại diện theo quy tắc của Set; điều này khác với lỗi `null`.

### Map

Với Map, cả khóa và giá trị đều phải khác `null`:

~~~java
Map<String, Integer> versions = Map.of(
    "Java", 17,
    "Kotlin", 2
);

Map<String, Integer> invalidKey =
    Map.of(null, 17); // NullPointerException

Map<String, Integer> invalidValue =
    Map.of("Java", null); // NullPointerException
~~~

`Map.ofEntries` cũng không chấp nhận khóa hoặc giá trị `null`. Nếu dùng `Map.entry` để tạo từng cặp, bản thân `Map.entry` đã từ chối `null` ở cả hai vị trí:

~~~java
Map<String, Integer> versions = Map.ofEntries(
    Map.entry("Java", 17),
    Map.entry("Kotlin", 2)
);
~~~

Map được tạo bằng các factory này là không thể thay đổi. Khóa trùng lặp trong `Map.of` hoặc `Map.ofEntries` gây `IllegalArgumentException`; đây là lỗi khác với `NullPointerException` do khóa hoặc giá trị `null`.

`Map.copyOf` cũng kiểm tra cả khóa lẫn giá trị trong Map nguồn. Một Map nguồn cho phép `null`, chẳng hạn `HashMap`, vẫn có thể khiến `Map.copyOf` ném `NullPointerException`.

## 3. copyOf không làm sạch dữ liệu null

Không nên hiểu `copyOf` là phương thức tự lọc phần tử không hợp lệ. Nó tạo collection không thể thay đổi từ dữ liệu nguồn và yêu cầu dữ liệu tuân thủ quy tắc của collection đích.

Ví dụ:

~~~java
List<String> source = Arrays.asList("Java", null, "Kotlin");

// Ném NullPointerException; không tự bỏ phần tử null.
List<String> immutable = List.copyOf(source);
~~~

Nếu nghiệp vụ muốn bỏ qua giá trị `null`, hãy lọc rõ ràng trước khi gọi `copyOf`:

~~~java
List<String> immutable = source.stream()
    .filter(Objects::nonNull)
    .toList();
~~~

`Stream.toList()` có từ Java 16 và trả về List không thể thay đổi. Trong ví dụ trên, phần tử `null` được loại bỏ bởi `filter`, không phải bởi `toList()`. Cần thể hiện rõ bước lọc để người đọc hiểu chính sách dữ liệu của ứng dụng.

Nếu nghiệp vụ cần giữ `null`, không dùng các factory hoặc `copyOf` có quy tắc từ chối `null`; hãy chọn collection phù hợp với yêu cầu đó.

## 4. Không phải mọi collection của Java đều từ chối null

Các collection có thể thay đổi như `ArrayList`, `HashSet` và `HashMap` cho phép `null` theo hợp đồng API của chúng:

- `ArrayList` có thể chứa nhiều phần tử `null`.
- `HashSet` có thể chứa một phần tử `null`.
- `HashMap` cho phép một khóa `null` và nhiều giá trị `null`.

`Arrays.asList` cũng cho phép `null`, nhưng danh sách trả về có kích thước cố định và được hỗ trợ bởi mảng ban đầu. Có thể thay thế phần tử bằng `set`, nhưng không thể thêm hoặc xóa phần tử.

~~~java
List<String> mutable = new ArrayList<>();
mutable.add(null); // Hợp lệ

List<String> fixedSize = Arrays.asList("Java", null); // Hợp lệ
fixedSize.set(1, "Kotlin"); // Hợp lệ
// fixedSize.add("Go"); // UnsupportedOperationException
~~~

Bọc một collection bằng `Collections.unmodifiableList` cũng không tự kiểm tra hoặc loại bỏ `null` đã có. Wrapper chỉ chặn thao tác sửa đổi thông qua wrapper:

~~~java
List<String> source = new ArrayList<>();
source.add(null);

List<String> view = Collections.unmodifiableList(source);
// view vẫn chứa null; view.add("Java") sẽ bị chặn.
~~~

Vì vậy, không thể suy luận rằng một collection không thể thay đổi thì chắc chắn không chứa `null`. Cần kiểm tra API tạo collection cụ thể.

## 5. Phân biệt Optional.of và Optional.ofNullable

`Optional` không phải là List, Set hay Map, nhưng thường được dùng để biểu diễn một giá trị có thể vắng mặt:

- `Optional.of(value)` yêu cầu `value` khác `null`; nếu truyền `null`, nó ném `NullPointerException`.
- `Optional.ofNullable(value)` chấp nhận `null`; nếu giá trị là `null`, nó tạo `Optional.empty()`.

~~~java
Optional<String> required = Optional.of("Java");
Optional<String> empty = Optional.ofNullable(null);

// Optional<String> invalid = Optional.of(null);
// NullPointerException
~~~

Nếu phương thức có thể không tìm thấy dữ liệu, trả về `Optional<T>` thường rõ nghĩa hơn việc dùng `null` làm tín hiệu vắng mặt. Không nên dùng Optional như một cách thay thế cho mọi trường hợp null trong cấu trúc dữ liệu.

## 6. Kiểm tra null ở ranh giới API của ứng dụng

Khi tự viết phương thức hoặc constructor, hãy xác định rõ tham số có bắt buộc khác `null` hay không. Nếu bắt buộc, có thể kiểm tra ngay ở đầu phương thức bằng `Objects.requireNonNull`:

~~~java
import java.util.Objects;

public class UserService {
    public void register(String username) {
        Objects.requireNonNull(username, "username");
        // Xử lý username sau khi đã xác nhận khác null.
    }
}
~~~

Cách này làm hợp đồng phương thức rõ ràng và phát hiện dữ liệu sai gần nơi nó đi vào hệ thống. Nếu `null` là giá trị hợp lệ, hãy xử lý nó có chủ đích thay vì kiểm tra rồi ném lỗi.

Với Map cho phép giá trị `null`, kết quả `get(key)` bằng `null` có thể có hai nghĩa: khóa không tồn tại hoặc khóa tồn tại với giá trị `null`. Khi cần phân biệt, dùng `containsKey(key)`. Với Map được tạo từ `Map.of` hoặc `Map.copyOf`, giá trị `null` không thể xuất hiện nên tình huống này không phát sinh từ dữ liệu được lưu trong Map đó.

## 7. Ví dụ chạy được

Chương trình dưới đây kiểm tra các factory không chấp nhận `null`, sau đó đối chiếu với collection cho phép `null` và cách dùng `Optional.ofNullable`.

**Tệp `NullRejectionDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

public class NullRejectionDemo {
    private static void expectNullPointer(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected NullPointerException: " + label);
        } catch (NullPointerException expected) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        expectNullPointer("List.of element", () -> List.of("Java", (String) null));
        expectNullPointer("Set.of element", () -> Set.of("Java", (String) null));
        expectNullPointer("Map.of key", () -> Map.of((String) null, "Java"));
        expectNullPointer("Map.of value", () -> Map.of("language", (String) null));

        List<String> source = Arrays.asList("Java", null);
        expectNullPointer("List.copyOf element", () -> List.copyOf(source));
        expectNullPointer("Set.copyOf element", () -> Set.copyOf(source));

        Map<String, String> nullKeyMap = new HashMap<>();
        nullKeyMap.put(null, "Java");
        expectNullPointer("Map.copyOf key", () -> Map.copyOf(nullKeyMap));

        Map<String, String> nullValueMap = new HashMap<>();
        nullValueMap.put("language", null);
        expectNullPointer("Map.copyOf value", () -> Map.copyOf(nullValueMap));

        List<String> mutable = new ArrayList<>();
        mutable.add(null);
        System.out.println("ArrayList stores null: " + mutable.contains(null));
        System.out.println("Arrays.asList stores null: "
                + Arrays.asList("Java", null).contains(null));
        System.out.println("Optional.ofNullable(null) is empty: "
                + Optional.ofNullable(null).isEmpty());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all NullRejectionDemo.java
java NullRejectionDemo
~~~

Kết quả chuẩn:

~~~text
List.of element: rejected
Set.of element: rejected
Map.of key: rejected
Map.of value: rejected
List.copyOf element: rejected
Set.copyOf element: rejected
Map.copyOf key: rejected
Map.copyOf value: rejected
ArrayList stores null: true
Arrays.asList stores null: true
Optional.ofNullable(null) is empty: true
~~~

Helper `expectNullPointer` chỉ in kết quả khi thao tác thực sự ném `NullPointerException`. Nếu thao tác không ném lỗi, `AssertionError` sẽ làm chương trình thất bại, vì vậy ví dụ cũng kiểm tra được hành vi mong đợi thay vì chỉ in thông báo giả định.

## 8. Lỗi thường gặp và cách chọn API

| Nhu cầu | API phù hợp | Quy tắc null |
|---|---|---|
| Tạo List không thể thay đổi từ các phần tử biết trước | `List.of` | Từ chối null |
| Tạo Set không thể thay đổi từ các phần tử biết trước | `Set.of` | Từ chối null |
| Tạo Map không thể thay đổi từ các cặp khóa/giá trị | `Map.of`, `Map.ofEntries` | Từ chối null ở khóa và giá trị |
| Tạo bản sao không thể thay đổi từ collection hiện có | `List.copyOf`, `Set.copyOf`, `Map.copyOf` | Từ chối null |
| Cần List có thể thay đổi và cho phép null | `ArrayList` | Cho phép null |
| Cần Map có thể thay đổi và cho phép null | `HashMap` | Cho phép null key/value |
| Biểu diễn một kết quả có thể vắng mặt | `Optional.ofNullable` | Chuyển null thành Optional.empty |

Các lỗi nên tránh:

- Truyền collection có `null` vào `List.copyOf`, `Set.copyOf` hoặc `Map.copyOf` rồi nghĩ rằng phương thức sẽ tự lọc dữ liệu.
- Dùng `List.of` khi dữ liệu đầu vào có thể chứa `null` mà không xác thực hoặc xử lý trước.
- Cho rằng wrapper không thể thay đổi sẽ tự loại bỏ `null`.
- Nhầm `NullPointerException` do null với `IllegalArgumentException` do phần tử trùng trong `Set.of` hoặc khóa trùng trong `Map.of`.
- Dùng `Optional.of` khi đầu vào có thể là null; trường hợp đó cần quyết định rõ nên từ chối bằng `of` hay biểu diễn vắng mặt bằng `ofNullable`.

## 9. Ghi nhớ

Các factory gọn `List.of`, `Set.of`, `Map.of` và các phương thức `copyOf` từ chối `null` để bảo đảm dữ liệu bên trong tuân thủ hợp đồng của chúng. Lỗi được báo bằng `NullPointerException` ngay trong thao tác tạo collection. Các collection như `ArrayList`, `HashSet` và `HashMap` vẫn có thể cho phép null, nên hãy chọn API theo chính sách dữ liệu của ứng dụng. Nếu null có nghĩa là không có giá trị, hãy biểu diễn rõ bằng `Optional.ofNullable` hoặc xử lý nó ở ranh giới API.
