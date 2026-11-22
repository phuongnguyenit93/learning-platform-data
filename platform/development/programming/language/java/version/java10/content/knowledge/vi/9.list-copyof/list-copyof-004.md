# NullPointerException khi nguồn hoặc phần tử danh sách là `null` với `List.copyOf`

## 1. Mục tiêu và phạm vi

Từ **Java 10**, phương thức `List.copyOf` tạo một danh sách **không thể sửa đổi** (*unmodifiable list*) từ các phần tử của một `Collection`. Phương thức này vẫn là API chuẩn, được dùng rộng rãi trong Java hiện đại. Nhưng nó áp dụng một hợp đồng nghiêm ngặt: **collection nguồn không được là `null` và không phần tử nào của nguồn được là `null`**. Vi phạm một trong hai điều kiện sẽ gây **`NullPointerException` ngay khi gọi `List.copyOf`**.

Bài này tập trung đúng hai trường hợp gây NPE, cách phân biệt, chẩn đoán và xử lý chúng. Sau khi học, bạn sẽ:

- Giải thích được `List.copyOf(Collection<? extends E>)` kiểm tra điều kiện gì, trả về gì và khi nào ném `NullPointerException`.
- Phân biệt **tham chiếu tới collection là `null`** với **collection tồn tại nhưng chứa phần tử `null`**.
- Biết rằng `List.copyOf` tạo snapshot cấu trúc, không tự lọc `null`, không thay `null` bằng giá trị mặc định và không deep-copy phần tử.
- Chọn chính sách thích hợp: **từ chối dữ liệu**, **bỏ phần tử thiếu**, **thay bằng giá trị mặc định**, hoặc **biểu diễn sự vắng mặt rõ ràng**.
- Viết ví dụ Java 17+ chạy được, với stdout đã xác định, đồng thời hiểu giới hạn của validation trong môi trường nhiều luồng.

**Chỉ sử dụng kiến thức còn áp dụng hiện nay:** `List.copyOf` và những API liên quan được giới thiệu từ Java 9/10/16 nhưng vẫn có giá trị trong các JDK mới. Không dùng constructor wrapper hay cách xử lý collection đã lỗi thời.

## 2. Hợp đồng chính xác của `List.copyOf`

Khai báo trong `java.util.List`:

~~~java
static <E> List<E> copyOf(Collection<? extends E> coll)
~~~

Ý nghĩa của các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `<E>` | Kiểu phần tử được suy luận theo generic của Java. |
| `Collection<? extends E>` | Đầu vào có thể là `List`, `Set` hoặc `Collection` phù hợp, **không bắt buộc chính xác là `List`**. |
| `coll` | Đối tượng collection nguồn, bắt buộc **khác `null`**. |
| Kết quả `List<E>` | Danh sách không cho thêm, xóa hoặc thay phần tử thông qua chính kết quả. |
| Thứ tự | Phần tử được lưu theo **thứ tự duyệt** của collection nguồn tại lúc tạo. |
| Chính sách `null` | Nguồn và từng phần tử nguồn đều không được là `null`. |
| Nếu nguồn thay đổi về sau | Snapshot không phản ánh việc thêm, xóa, thay phần tử trong nguồn. |

Theo JavaDoc của `List.copyOf`, hai nguyên nhân ném **`NullPointerException`** là:

1. **`coll == null`**: không có đối tượng collection nguồn để sao chép.
2. **`coll` chứa ít nhất một phần tử `null`**: cấu trúc nguồn tồn tại nhưng không thỏa điều kiện về phần tử.

Đây là lỗi **runtime** khi lời gọi được thực thi. Trình biên dịch thường không thể chứng minh mọi phần tử của collection sẽ luôn không-null; kể cả generic kiểu `List<String>` cũng không tự ngăn `null` được thêm vào một danh sách cho phép `null`.

**Điểm cốt lõi:** `List.copyOf` không phải hàm làm sạch dữ liệu. Nó **từ chối** dữ liệu không hợp lệ theo hợp đồng của mình; code gọi phải quyết định xử lý dữ liệu trước khi sao chép.

## 3. Trường hợp 1: Chính collection nguồn là `null`

### 3.1. Ví dụ

~~~java
import java.util.List;

// Trong phương thức:
List<String> source = null;
var result = List.copyOf(source); // ném NullPointerException
~~~

Biến `source` có kiểu biên dịch `List<String>`, nhưng tại runtime nó không tham chiếu tới đối tượng List nào. `List.copyOf` không có collection để lấy phần tử, nên ném `NullPointerException`.

Phân biệt hai trường hợp:

~~~java
List<String> absent = null;  // không có đối tượng list
List<String> empty = List.of(); // có đối tượng list, kích thước bằng 0

// List.copyOf(absent);       // NullPointerException
var safeEmpty = List.copyOf(empty); // hợp lệ: []
~~~

**Danh sách rỗng không phải danh sách `null`.** `List.copyOf(List.of())` hợp lệ vì collection nguồn tồn tại, dù không chứa phần tử nào.

### 3.2. Khi đầu vào là `null`, nên xử lý thế nào?

Điều này phụ thuộc vào hợp đồng nghiệp vụ.

**Phương án A — thiếu nguồn là lỗi (fail fast):**

~~~java
import java.util.List;
import java.util.Objects;

static List<String> copyRequired(List<String> source) {
    Objects.requireNonNull(source, "source must not be null");
    return List.copyOf(source);
}
~~~

`Objects.requireNonNull` ném `NullPointerException` với thông điệp **do ứng dụng tự đặt**. Nó giúp phân biệt nguyên nhân ở ranh giới API thay vì đợi lỗi không rõ ngữ cảnh. Nếu `source` khác `null` nhưng chứa phần tử `null`, `List.copyOf` **vẫn ném NPE** — kiểm tra nguồn không giải quyết vấn đề phần tử.

**Phương án B — thiếu nguồn được định nghĩa là danh sách rỗng:**

~~~java
static List<String> copyOrEmpty(List<String> source) {
    return source == null ? List.of() : List.copyOf(source);
}
~~~

Chỉ dùng khi nghiệp vụ thực sự định nghĩa **“không cung cấp danh sách” tương đương “danh sách không có phần tử”**. Không dùng cách này để che giấu lỗi dữ liệu hoặc bỏ qua yêu cầu bắt buộc.

**Lưu ý:** biểu thức `source.stream()` khi `source == null` cũng gây NPE, thậm chí trước khi `List.copyOf` được gọi. Nếu muốn dùng Stream để xử lý, phải kiểm tra nguồn trước.

## 4. Trường hợp 2: Collection tồn tại nhưng chứa phần tử `null`

### 4.1. `ArrayList` có thể chứa `null`

~~~java
import java.util.ArrayList;
import java.util.List;

// Trong phương thức:
var source = new ArrayList<String>();
source.add("Java");
source.add(null);      // ArrayList cho phép null
source.add("10");

System.out.println(source); // [Java, null, 10]
// var result = List.copyOf(source); // NullPointerException
~~~

`source` là một đối tượng thật, kích thước bằng 3. Điều kiện đầu vào **không-null** đã thỏa, nhưng phần tử có chỉ số 1 là `null`; `List.copyOf` từ chối toàn bộ phép sao chép.

Nguyên nhân không phải do `String` bị cấm, cũng không phải do `ArrayList` có lỗi. Mỗi API có hợp đồng riêng: `ArrayList` có thể chứa `null`, còn danh sách tạo bởi `List.copyOf` **không chứa `null`**.

### 4.2. Ngay cả unmodifiable view cũng có thể chứa `null`

~~~java
var source = new ArrayList<String>();
source.add("A");
source.add(null);

var view = java.util.Collections.unmodifiableList(source);
System.out.println(view.contains(null)); // true

// List.copyOf(view); // NullPointerException
~~~

`Collections.unmodifiableList(source)` chỉ tạo **view không cho sửa qua view**; nó không tự loại `null` đang có trong nguồn. Bởi vậy **unmodifiable không mặc nhiên có nghĩa null-free**.

Khác biệt:

- `Collections.unmodifiableList(source)`: view có thể phản ánh dữ liệu `null` đã tồn tại trong nguồn.
- `List.copyOf(source)`: không nhận nguồn chứa `null`, dù nguồn là mutable hay unmodifiable view.
- `List.of(...)`: cũng không cho phần tử `null`, nhưng thích hợp khi tạo danh sách từ các phần tử đã có ngay tại chỗ.

### 4.3. Nguồn từ các API khác cũng cần kiểm tra

Không được suy ra “phần tử không-null” chỉ từ kiểu khai báo `List<String>`. Một số nguồn có thể chứa `null`:

~~~java
var fromArray = java.util.Arrays.asList("A", null, "B");
// List.copyOf(fromArray); // NullPointerException

var fromDatabase = new ArrayList<String>();
fromDatabase.add(null);
// List.copyOf(fromDatabase); // NullPointerException
~~~

Đoạn `fromDatabase` chỉ minh họa dữ liệu vào từ nguồn ngoài: với dữ liệu thật, hãy kiểm tra contract của driver, mapper và repository. Không phải database nào cũng trả dữ liệu thiếu bằng phần tử `null`.

**NPE nổ khi gọi `copyOf`, không nhất thiết khi tạo danh sách gốc.** Dữ liệu sai có thể tồn tại trước đó một thời gian và chỉ bị phát hiện tại ranh giới tạo snapshot.

## 5. Phân biệt rõ các tình huống `null`

| Tình huống | Ví dụ | Kết quả `List.copyOf` |
| --- | --- | --- |
| Tham chiếu nguồn `null` | `List<String> xs = null;` | **NPE** |
| Nguồn rỗng hợp lệ | `List<String> xs = List.of();` | Thành công, list rỗng |
| Có một phần tử `null` | `Arrays.asList("A", null)` | **NPE** |
| Có nhiều phần tử `null` | `Arrays.asList(null, "A", null)` | **NPE** |
| Nguồn là view không sửa được nhưng chứa `null` | `Collections.unmodifiableList(listWithNull)` | **NPE** |
| Nguồn là list hợp lệ, không có `null` | `List.of("A", "B")` | Thành công |
| Phần tử là một đối tượng khác `null` nhưng **field** trong đối tượng đó là `null` | `new Entry(null)` trong `List<Entry>` | Thành công; `copyOf` không kiểm tra sâu |
| Phần tử là một list con khác `null`, nhưng list con có phần tử `null` | `List<List<String>>` chứa một list con có `null` | Thành công ở cấp ngoài; không deep-validate |
| Nguồn bị sửa đồng thời trong lúc copy | Một luồng khác sửa `ArrayList` | Không có bảo đảm snapshot nhất quán; phải tự đồng bộ hóa |

Hai dòng cuối rất quan trọng: **kiểm tra `null` của `copyOf` là kiểm tra các phần tử trực tiếp của collection được truyền vào**, không phải kiểm tra toàn bộ cây đối tượng.

## 6. Kiểm tra nguồn và phần tử để có lỗi dễ chẩn đoán

JavaDoc quy định **loại ngoại lệ**, nhưng không cam kết bạn sẽ nhận được thông điệp nào, chỉ số phần tử nào hoặc stack trace cụ thể. Không nên viết test phụ thuộc vào thông điệp NPE do nội bộ JDK tạo ra.

Nếu ứng dụng cần giải thích chính xác lỗi, hãy kiểm tra ở ranh giới nhận dữ liệu:

~~~java
import java.util.List;
import java.util.Objects;

static List<String> checkedCopy(List<String> source) {
    Objects.requireNonNull(source, "source must not be null");

    for (int i = 0; i < source.size(); i++) {
        Objects.requireNonNull(
                source.get(i),
                "element[" + i + "] must not be null"
        );
    }

    return List.copyOf(source);
}
~~~

Hành vi:

- Nếu `source == null`: NPE mang thông điệp do code đặt là `source must not be null`.
- Nếu `source.get(1) == null`: NPE mang thông điệp `element[1] must not be null`.
- Nếu mọi phần tử trực tiếp đều hợp lệ: `List.copyOf` tạo danh sách không cho sửa cấu trúc.

**Đây là validation đơn giản dành cho collection ổn định và một luồng.** Nếu collection nguồn có thể bị luồng khác sửa trong lúc vòng lặp kiểm tra hoặc sao chép, kết quả validation và dữ liệu được copy có thể không nhất quán. Cần có snapshot an toàn hoặc bảo vệ nguồn theo chiến lược concurrency thích hợp, không thể chỉ tin vào bước kiểm tra trước đó.

### 6.1. Khi nên dùng exception nào?

- **`NullPointerException`** là ngoại lệ được chính `List.copyOf` chỉ định khi nguồn hoặc phần tử là `null`.
- **`Objects.requireNonNull(...)`** phù hợp nếu hợp đồng API nói đối số hoặc phần tử bắt buộc không-null, và bạn muốn thông điệp rõ ràng.
- **`IllegalArgumentException`** đôi khi được dùng khi ứng dụng gom nhiều quy tắc validation đầu vào và muốn báo lỗi nghiệp vụ thống nhất; đây là lựa chọn của code ứng dụng, **không phải ngoại lệ mà `List.copyOf` cam kết ném cho `null`**.

Không nên bắt rồi bỏ qua mọi `NullPointerException`. Một NPE có thể xuất phát từ chỗ khác, không chỉ từ `copyOf`. Hãy xử lý tại ranh giới có đủ thông tin để quyết định chính sách dữ liệu.

## 7. Ba chiến lược xử lý `null` trước khi sao chép

Không có cách “tốt nhất” cho mọi hệ thống. Chính sách phải phản ánh dữ liệu.

### Chiến lược A — từ chối phần tử `null`

~~~java
var copied = checkedCopy(source);
~~~

Dùng khi mỗi phần tử là dữ liệu bắt buộc, ví dụ danh sách mã hàng không được thiếu mã. Ưu điểm là phát hiện lỗi sớm, không âm thầm làm thay đổi số lượng hoặc thứ tự các mục.

**Tránh:** tự động biến `null` thành chuỗi rỗng nếu chuỗi rỗng không tương đương “không có mã”.

### Chiến lược B — lọc bỏ phần tử `null`

~~~java
var filtered = List.copyOf(
        source.stream()
              .filter(java.util.Objects::nonNull)
              .toList()
);
~~~

`Stream.toList()` dùng được từ Java 16; ví dụ chạy trên Java 17+. Khi `source` có `["A", null, "B"]`, kết quả là `["A", "B"]`.

**Đánh đổi:** chỉ số và kích thước có thể thay đổi. Đây là lựa chọn phù hợp nếu phần tử `null` có nghĩa **“bỏ qua bản ghi trống”**, không phù hợp nếu vị trí phần tử có ý nghĩa (ví dụ tọa độ trong ma trận, chỉ số dữ liệu gốc, vị trí của hàng CSV).

**Không quên:** phải bảo đảm `source != null` trước khi gọi `source.stream()`; `filter` không tự xử lý việc chính nguồn là `null`.

### Chiến lược C — thay phần tử `null` bằng giá trị mặc định

~~~java
var replaced = List.copyOf(
        source.stream()
              .map(value -> value == null ? "(missing)" : value)
              .toList()
);
~~~

Với `["A", null, "B"]`, kết quả là `["A", "(missing)", "B"]`. Cách này giữ nguyên số lượng và vị trí, nhưng **thay đổi ý nghĩa dữ liệu**. Chỉ dùng nếu `"(missing)"` là giá trị biểu diễn trạng thái hợp lệ theo hợp đồng; nếu chuỗi này có thể trùng một giá trị thật, nên chọn cách biểu diễn dữ liệu có cấu trúc hơn.

### Chiến lược D — biểu diễn sự thiếu vắng thay vì lưu `null`

Ví dụ nếu một vị trí hợp lệ có thể thiếu giá trị và cần giữ nguyên số phần tử:

~~~java
List<java.util.Optional<String>> items = List.of(
        java.util.Optional.of("A"),
        java.util.Optional.empty(),
        java.util.Optional.of("B")
);
~~~

Các **phần tử `Optional`** không phải `null`, nên `List.copyOf(items)` hợp lệ. Người dùng API phải xử lý `Optional.empty()` rõ ràng. Đây là một **lựa chọn mô hình dữ liệu**, không phải quy định bắt buộc phải dùng `Optional` trong mọi collection; cũng cần cân nhắc độ phức tạp cho bên gọi.

**Lưu ý:** `Optional.of(null)` tự ném NPE; nếu dữ liệu đầu vào có thể `null`, dùng `Optional.ofNullable(value)` khi thật sự muốn chuyển nó thành một Optional rỗng.

## 8. `List.copyOf` không deep-copy: một phần tử có field `null` vẫn hợp lệ

Xét một record Java hiện đại:

~~~java
record Entry(String description) {}

var entries = List.of(new Entry(null));
var copied = List.copyOf(entries); // hợp lệ
System.out.println(copied.size()); // 1
~~~

Phần tử trực tiếp của `entries` là **một đối tượng `Entry` khác `null`**. Dù field `description` của đối tượng đó là `null`, `List.copyOf` **không kiểm tra sâu** và không ném NPE vì lý do ấy.

Nếu nghiệp vụ cấm field `description` là `null`, hãy kiểm tra trong constructor của record:

~~~java
import java.util.Objects;

record Entry(String description) {
    public Entry {
        Objects.requireNonNull(description, "description is required");
    }
}
~~~

Đoạn định nghĩa record trên là **một lựa chọn khác** với record minh họa đầu mục, không đặt hai định nghĩa trùng tên trong cùng file. Trách nhiệm kiểm tra tính hợp lệ của phần tử thuộc về chính đối tượng hoặc code nhận dữ liệu, không tự động thuộc về `List.copyOf`.

### 8.1. Trường hợp nested list

~~~java
var inner = new ArrayList<String>();
inner.add(null);

var outer = List.copyOf(List.of(inner));
// Thành công: phần tử trực tiếp của outer là inner, một ArrayList khác null.

System.out.println(outer.get(0).get(0) == null); // true
~~~

Nếu bạn cần danh sách hai cấp **không có `null` ở bất kỳ cấp nào**, phải kiểm tra hoặc tạo copy từng cấp:

~~~java
// Nếu inner chứa null thì dòng này ném NPE:
var safeInner = List.copyOf(inner);
~~~

Tóm lại: `List.copyOf` kiểm tra đầu vào và các phần tử **trực tiếp**. Đừng coi nó là phép deep-validation, deep-copy hoặc deep-freeze.

## 9. So sánh với các API thường bị nhầm

| API | Nhận nguồn `null`? | Nhận phần tử `null`? | Có snapshot cấu trúc không? |
| --- | --- | --- | --- |
| `List.copyOf(coll)` (Java 10+) | **Không — NPE** | **Không — NPE** | Có; nguồn đổi sau đó không phản ánh. |
| `List.of(elements...)` (Java 9+) | Không có tham số Collection; varargs array truyền `null` cũng bị từ chối | **Không — NPE** | Tạo list từ những phần tử truyền vào; không có backing mutable list. |
| `Collections.unmodifiableList(list)` | Không — NPE nếu list reference là `null` | Có thể chứa `null` nếu backing list có | **Không**; là view, phản ánh nguồn. |
| `new ArrayList<>(coll)` | Không — NPE với Collection nguồn `null` | **Có thể** chứa `null` | Sao chép cấu trúc vào list mutable. |
| `Collectors.toUnmodifiableList()` (Java 10+) | Dùng trong Stream pipeline, không nhận Collection trực tiếp | **Không — NPE** nếu kết quả chứa `null` | Tạo list không sửa được từ pipeline. |
| `Stream.toList()` (Java 16+) | Phải có một Stream hợp lệ để gọi | Không phải API có hợp đồng cấm `null` như `List.copyOf` | Tạo list không sửa được từ Stream; không tự biến nó thành `List.copyOf`. |

**Không nên tự động thay `Collections.unmodifiableList(...)` bằng `List.copyOf(...)` trong code cũ nếu dữ liệu có `null` hoặc ứng dụng cần live view:** tuy cả hai kết quả đều không cho cập nhật trực tiếp, hợp đồng về `null` và quan hệ với nguồn **khác nhau**.

### 9.1. Vì sao một danh sách “đã không sửa được” vẫn có thể bị `copyOf` từ chối?

~~~java
var mutable = new ArrayList<String>();
mutable.add(null);

var view = java.util.Collections.unmodifiableList(mutable);
// List.copyOf(view); // NullPointerException
~~~

`view` không cho sửa qua nó nhưng không làm sạch `null`. Hợp đồng `List.copyOf` không nới lỏng chỉ vì input là một `List` unmodifiable theo nghĩa của view.

### 9.2. Vì sao không nên dựa vào identity của kết quả?

Nếu nguồn đã là danh sách unmodifiable phù hợp, triển khai `List.copyOf` có thể tái sử dụng instance. Vì thế code không nên kiểm thử bằng `copy == original` hay giả định mỗi lần gọi `copyOf` tạo một đối tượng khác.

Kiểm tra bằng **nội dung** và khả năng chặn cập nhật:

~~~java
var original = List.of("A", "B");
var copy = List.copyOf(original);

System.out.println(copy.equals(original)); // true
// Không phụ thuộc copy == original.
~~~

Dù reuse hay không, **không có cơ chế nào cho phép giữ phần tử `null` trong kết quả của `List.copyOf`**.

## 10. Thời điểm kiểm tra và tính an toàn khi nhiều luồng cùng truy cập

Một sai lầm phổ biến là kiểm tra nguồn bằng vòng lặp rồi tin rằng `List.copyOf` không thể ném NPE nữa:

~~~java
for (var item : source) {
    java.util.Objects.requireNonNull(item);
}
var result = List.copyOf(source);
~~~

Đối với collection **ổn định**, cách kiểm tra trước giúp báo lỗi gần dữ liệu xấu. Nhưng nếu luồng khác có quyền sửa `source` trong lúc validation hoặc copy, nguồn có thể thay đổi giữa hai bước. Khi đó:

- Phần tử có thể trở thành `null` **sau khi kiểm tra**.
- Kích thước/thứ tự có thể thay đổi.
- Có thể xảy ra hành vi không nhất quán hoặc ngoại lệ khác tùy loại collection và đồng bộ hóa.

**`List.copyOf` không phải cơ chế đồng bộ hóa tự động và không bảo đảm một snapshot nguyên tử từ nguồn đang biến đổi đồng thời.** Nếu yêu cầu nhất quán, hãy đọc từ một trạng thái được bảo vệ phù hợp (khóa, snapshot an toàn, cấu trúc concurrency chuyên dụng, hoặc giao thức chuyển giao ownership). Sau đó mới dùng `copyOf` để chốt kết quả.

Đồng thời, *unmodifiable* không có nghĩa **mọi phần tử đều thread-safe**. Nếu các phần tử là đối tượng mutable, một luồng khác vẫn có thể sửa trạng thái phần tử mà kết quả `copyOf` đang tham chiếu tới.

## 11. Chương trình Java 17+ hoàn chỉnh và stdout đã kiểm chứng

Tạo tệp **`ListCopyOfNullDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class ListCopyOfNullDemo {
    static List<String> checkedCopy(List<String> source) {
        Objects.requireNonNull(source, "source must not be null");

        for (int i = 0; i < source.size(); i++) {
            Objects.requireNonNull(
                    source.get(i),
                    "element[" + i + "] must not be null"
            );
        }
        return List.copyOf(source);
    }

    public static void main(String[] args) {
        List<String> missingSource = null;
        try {
            List.copyOf(missingSource);
        } catch (NullPointerException ex) {
            System.out.println("null source -> NullPointerException");
        }

        var withNull = new ArrayList<String>();
        withNull.add("Java");
        withNull.add(null);
        withNull.add("10");
        try {
            List.copyOf(withNull);
        } catch (NullPointerException ex) {
            System.out.println("null element -> NullPointerException");
        }

        try {
            checkedCopy(withNull);
        } catch (NullPointerException ex) {
            System.out.println("validation -> " + ex.getMessage());
        }

        var filtered = List.copyOf(
                withNull.stream()
                        .filter(Objects::nonNull)
                        .toList()
        );
        var replaced = List.copyOf(
                withNull.stream()
                        .map(value -> value == null ? "(missing)" : value)
                        .toList()
        );
        System.out.println("filtered=" + filtered);
        System.out.println("replaced=" + replaced);

        var view = Collections.unmodifiableList(withNull);
        System.out.println("view contains null=" + view.contains(null));

        var mutable = new ArrayList<>(List.of("A", "B"));
        var snapshot = List.copyOf(mutable);
        mutable.add("C");
        System.out.println("snapshot=" + snapshot);

        var inner = new ArrayList<String>();
        inner.add(null);
        var outer = List.copyOf(List.of(inner));
        System.out.println(
                "nested null=" + (outer.get(0).get(0) == null)
        );
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ListCopyOfNullDemo.java
java ListCopyOfNullDemo
~~~

**Stdout chính xác:**

~~~text
null source -> NullPointerException
null element -> NullPointerException
validation -> element[1] must not be null
filtered=[Java, 10]
replaced=[Java, (missing), 10]
view contains null=true
snapshot=[A, B]
nested null=true
~~~

Giải thích:

1. **`null source`:** `List.copyOf(missingSource)` nhận Collection reference `null`; ném NPE, được `catch` xử lý.
2. **`null element`:** `withNull` là `ArrayList` hợp lệ nhưng có phần tử tại index 1 là `null`; `List.copyOf(withNull)` ném NPE.
3. **`validation`:** `checkedCopy` có thông điệp chính xác do code ứng dụng cung cấp, không phụ thuộc thông điệp NPE nội bộ JDK.
4. **`filtered`:** Stream loại `null`, nên danh sách được copy chỉ còn `[Java, 10]`.
5. **`replaced`:** Mỗi `null` được thay bằng `"(missing)"`, giữ số lượng và thứ tự phần tử.
6. **`view contains null`:** `Collections.unmodifiableList` không tự loại `null` của backing `ArrayList`.
7. **`snapshot`:** danh sách copy không thay đổi khi `mutable` thêm `"C"` sau đó.
8. **`nested null`:** danh sách ngoài chứa **đối tượng danh sách trong khác `null`**, vì thế `List.copyOf` ở cấp ngoài hợp lệ dù bên trong danh sách con có phần tử `null`.

Chương trình dùng các API đang được hỗ trợ. `List.copyOf` cần Java 10+, còn `Stream.toList()` cần Java 16+; yêu cầu chạy **Java 17+** của ví dụ đáp ứng cả hai.

## 12. Lỗi phổ biến và cách chẩn đoán

| Lỗi hoặc giả định sai | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| “List nguồn đã khai báo `List<String>` nên chắc chắn không có `null`.” | Generic type không tự bảo đảm non-null. | Validation hoặc tạo dữ liệu ngay từ API không nhận `null`. |
| “Nguồn là `null` thì `copyOf` tự trả list rỗng.” | `copyOf` không đặt chính sách mặc định. | Dùng `Objects.requireNonNull` hoặc fallback rỗng có chủ đích. |
| “Collection không sửa được luôn không có `null`.” | Unmodifiable view có thể chứa `null` từ nguồn. | Kiểm tra hợp đồng cụ thể của từng API. |
| “Chỉ cần `filter(Objects::nonNull)` là xử lý mọi NPE.” | Nếu chính nguồn `null`, gọi `stream()` đã ném NPE. | Xác định chính sách cho nguồn `null` trước. |
| “Lọc `null` luôn an toàn về nghiệp vụ.” | Lọc làm thay đổi độ dài/vị trí. | Xem xét reject, default, Optional hoặc dữ liệu có cấu trúc. |
| “Có thể dùng `List.copyOf` để sửa dữ liệu chứa `null`.” | Phương thức sẽ từ chối, không làm sạch dữ liệu. | Chuẩn hóa trước khi copy. |
| “`List.copyOf` kiểm tra sâu mọi trường của phần tử.” | Chỉ kiểm tra phần tử trực tiếp; shallow copy. | Validation ở model, record constructor hoặc từng lớp nested. |
| “Bắt mọi NPE rồi trả `List.of()` là ổn.” | Che giấu lỗi và gây mất dữ liệu. | Bắt tại nơi có đủ ngữ nghĩa, hoặc cho lỗi lan truyền. |
| “Dựa vào thông điệp NPE của JDK để tìm index lỗi.” | Thông điệp không thuộc hợp đồng ổn định. | Đặt thông điệp qua validation của ứng dụng. |
| “Đã kiểm tra xong thì copy không thể lỗi khi nguồn bị sửa đa luồng.” | Thay đổi có thể xảy ra giữa validation và copy. | Bảo đảm nguồn ổn định theo chiến lược concurrency. |

## 13. Bài tập thực hành và đáp án

**Bài 1.** Đoán kết quả của:

~~~java
List<String> x = null;
var a = List.copyOf(x);
~~~

**Đáp án:** Biên dịch hợp lệ nhưng ném `NullPointerException` khi chạy vì tham chiếu nguồn `x` là `null`.

**Bài 2.** Đoán kết quả của:

~~~java
var x = new ArrayList<String>();
var a = List.copyOf(x);
System.out.println(a.size());
~~~

**Đáp án:** In `0`. `x` là list rỗng nhưng khác `null`, nên `copyOf` hợp lệ.

**Bài 3.** Đoán kết quả của:

~~~java
var x = new ArrayList<String>();
x.add("A");
x.add(null);
// List.copyOf(x);
~~~

**Đáp án:** Nếu bỏ comment dòng cuối, lời gọi ném NPE do **phần tử `null`**, mặc dù chính list nguồn không `null`.

**Bài 4.** Với `["a", null, "b"]`, nên dùng lọc hay thay mặc định?

**Đáp án:** Nếu mục tiêu chỉ lấy các phần tử có giá trị và không cần giữ vị trí, lọc để được `["a", "b"]`. Nếu cần giữ ba vị trí, phải định nghĩa một đại diện cho dữ liệu thiếu và có thể dùng giá trị mặc định hoặc `Optional.empty()`. Không có quyết định đúng chung cho mọi bài toán.

**Bài 5.** Với `List<List<String>>`, nếu inner list chứa `null` thì `List.copyOf(outer)` có bắt buộc ném NPE không?

**Đáp án:** Không, nếu **các phần tử trực tiếp của outer đều khác `null`**. `copyOf` ở cấp ngoài không kiểm tra sâu các phần tử trong inner list.

**Bài 6.** Vì sao `Collections.unmodifiableList(listWithNull)` có thể được tạo nhưng `List.copyOf(listWithNull)` ném NPE?

**Đáp án:** View từ `Collections` chỉ cấm sửa qua view, không làm sạch dữ liệu; `List.copyOf` có hợp đồng riêng **không cho phần tử `null`**.

**Bài 7.** Làm sao thông báo rõ phần tử nào không hợp lệ khi `List.copyOf` ném NPE?

**Đáp án:** Kiểm tra từng phần tử trước, ví dụ `Objects.requireNonNull(source.get(i), "element[" + i + "] must not be null")`; không phụ thuộc vào thông điệp NPE của JDK. Nếu dữ liệu bị thay đổi đồng thời, còn cần bảo đảm ổn định nguồn.

**Bài 8.** Sau khi `List.copyOf` tạo snapshot hợp lệ, có thể gọi `snapshot.add(null)` hay không?

**Đáp án:** Không; lời gọi cập nhật trên list không cho sửa gây `UnsupportedOperationException`. Đừng nhầm lỗi cố sửa cấu trúc này với `NullPointerException` do đầu vào không hợp lệ tại **lúc tạo** snapshot.

## 14. Checklist trước khi dùng `List.copyOf`

- [ ] Tôi đã phân biệt **nguồn `null`** với **nguồn rỗng**.
- [ ] Hợp đồng dữ liệu nói rõ collection nguồn có bắt buộc tồn tại không.
- [ ] Tôi biết những nơi có thể đưa phần tử `null` vào source.
- [ ] Nếu phần tử `null` không hợp lệ, tôi kiểm tra và báo lỗi gần biên giới dữ liệu.
- [ ] Nếu phần tử `null` được phép theo nghiệp vụ, tôi chọn biểu diễn khác hoặc chuẩn hóa có chủ đích trước khi copy.
- [ ] Tôi hiểu lọc phần tử làm mất vị trí và có thể làm thay đổi ý nghĩa.
- [ ] Tôi không nhầm unmodifiable view với snapshot null-free.
- [ ] Tôi không kỳ vọng `List.copyOf` deep-copy hoặc kiểm tra sâu dữ liệu lồng nhau.
- [ ] Tôi không dựa vào nội dung stack trace/thông điệp NPE của một bản JDK cụ thể.
- [ ] Nếu source bị thay đổi đồng thời, tôi bảo đảm tính nhất quán trước khi sao chép.
- [ ] Tôi phân biệt NPE khi **tạo list** với UnsupportedOperationException khi **cố sửa kết quả**.

## 15. Tài liệu tham khảo chính thức, còn áp dụng

- [Java SE 26 API — `List.copyOf(Collection)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): xác nhận nguồn phải khác `null`, không được có phần tử `null`, ném `NullPointerException` khi vi phạm, snapshot không theo thay đổi nguồn, từ Java 10.
- [Java SE 25 — `List` và Unmodifiable Lists](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): quy tắc `List.of`, `List.copyOf`, các phần tử và thao tác không được phép.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): unmodifiable view so với snapshot, shallow immutability và hành vi collection.
- [Java SE 25 — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): kết quả là view đọc xuyên qua list gốc.
- [Java SE 25 — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html): validation đầu vào với thông điệp NPE chủ động.
- [Dev.java — Collections Factory Methods](https://dev.java/learn/api/collections-and-streams/collections-framework/factory-methods/): ví dụ về `of`/`copyOf` và chính sách `null`.

**Ghi nhớ:** `List.copyOf` ném **`NullPointerException` nếu chính collection nguồn là `null` hoặc chỉ cần một phần tử trực tiếp là `null`**. Hãy giải quyết hai điều kiện này bằng hợp đồng dữ liệu và validation rõ ràng trước khi tạo snapshot; không kỳ vọng `copyOf` tự lọc, sửa hoặc kiểm tra sâu dữ liệu.