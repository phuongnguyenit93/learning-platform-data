# Vai trò của Java 10 trong ngôn ngữ và thư viện Java hiện đại

## 1. Java 10 để lại điều gì cho Java hiện nay?

Java 10 phát hành tháng 3/2018, nằm trong nhịp phát hành tính năng sáu tháng một lần. Java 10 không phải phiên bản hỗ trợ dài hạn (LTS); khi xây dựng ứng dụng thực tế, hãy chọn một bản JDK hiện còn được nhà cung cấp hỗ trợ và đáp ứng yêu cầu của dự án. Tuy nhiên, các cải tiến hữu ích xuất hiện từ Java 10 vẫn nằm trong Java hiện đại và thường được dùng trong code Java 17, 21, 25 hoặc mới hơn.

Điểm cần hiểu: **vai trò của Java 10 là đưa một số khả năng vào ngôn ngữ, thư viện chuẩn và cách đánh số phiên bản; không có nghĩa ngày nay phải chạy ứng dụng trên JDK 10**.

| Khả năng xuất hiện ở Java 10 | Giá trị còn áp dụng |
| --- | --- |
| Suy luận kiểu biến cục bộ với `var` (JEP 286) | Giảm lặp lại tên kiểu trong những khai báo ngắn, rõ nghĩa mà vẫn được kiểm tra kiểu khi biên dịch. |
| `List.copyOf`, `Set.copyOf`, `Map.copyOf` | Tạo bản sao collection không cho thay đổi cấu trúc từ dữ liệu đang có; hữu ích ở ranh giới API và cấu hình. |
| `Collectors.toUnmodifiableList/Set/Map` | Kết thúc một luồng xử lý Stream bằng collection không cho sửa đổi. |
| `Optional.orElseThrow()` không đối số | Trích giá trị bắt buộc từ `Optional`, hoặc ném `NoSuchElementException` khi không có giá trị. |
| Quy ước đánh số phiên bản theo thời gian (JEP 322) | Giải thích các con số phiên bản và lựa chọn bản JDK đang được bảo trì. |

Phạm vi của bài là các kiến thức **vẫn có giá trị sử dụng**. Một số API gần giống được đưa ra trước Java 10, như `List.of`/`Set.of`/`Map.of` (Java 9), hoặc sau Java 10, như `Stream.toList()` (Java 16). Cần phân biệt nguồn gốc của chúng để hiểu đúng lịch sử API.

## 2. `var`: suy luận kiểu cục bộ, vẫn là Java định kiểu tĩnh

### 2.1 Cơ chế

Trước Java 10, ta thường lặp tên kiểu ở vế trái và vế phải:

~~~java
Map<String, List<Integer>> groups = new HashMap<String, List<Integer>>();
~~~

Từ Java 10 có thể viết (ví dụ khai báo bên trong một phương thức):

~~~java
var groups = new HashMap<String, List<Integer>>();
~~~

**Trình biên dịch** suy luận kiểu của `groups` là `HashMap<String, List<Integer>>` ngay tại khai báo. Từ đó Java tiếp tục kiểm tra kiểu chặt chẽ như khi ta viết tên kiểu tường minh. `var` không tạo biến kiểu động, không tương đương `var` trong JavaScript và không làm cho kiểu biến đổi theo giá trị gán sau này.

~~~java
var count = 10;          // suy luận int
count = 20;              // hợp lệ
// count = "hai mươi";   // lỗi biên dịch: String không gán được cho int

var name = "Java";       // suy luận String
name = null;             // hợp lệ về kiểu, dù cần cân nhắc nguy cơ NullPointerException
// var unknown = null;   // lỗi: không suy luận được kiểu chỉ từ null
~~~

`var` là **tên kiểu được dành riêng** cho các vị trí cú pháp phù hợp, không phải từ khóa tổng quát có thể thay thế mọi tên kiểu.

### 2.2 Dùng `var` ở đâu?

Có thể dùng `var` cho biến cục bộ có giá trị khởi tạo, biến trong vòng lặp `for` thông thường, phần tử của `for-each` và tài nguyên được khai báo trong `try-with-resources`:

~~~java
var values = List.of("A", "B");  // List.of được giới thiệu từ Java 9

for (var index = 0; index < values.size(); index++) {
    System.out.println(values.get(index));
}

for (var value : values) {
    System.out.println(value);
}

try (var reader = java.nio.file.Files.newBufferedReader(
        java.nio.file.Path.of("input.txt"))) {
    System.out.println(reader.readLine());
}
~~~

Đây là **ví dụ cú pháp đặt trong thân phương thức**. Phần `try` cần một tệp `input.txt` tồn tại khi chạy; nó chỉ minh họa phạm vi dùng `var`, không phải chương trình độc lập để chạy ngay.

Các vị trí **không dùng được** `var` bao gồm trường của lớp (field), tham số phương thức thông thường, kiểu trả về của phương thức, khai báo thiếu giá trị khởi tạo, giá trị khởi tạo chỉ là `null` hoặc lambda chưa có kiểu đích:

~~~java
// Những khai báo sau cố ý SAI để minh họa giới hạn:
// private var id = 1;                 // field: không được
// public var find() { return 1; }     // kiểu trả về: không được
// void process(var input) {}          // tham số phương thức: không được
// var item;                           // thiếu initializer
// var item = null;                    // không đủ dữ liệu suy luận kiểu
// var fn = x -> x + 1;                // lambda thiếu target type
~~~

Trong Java 11, `var` còn được hỗ trợ ở tham số của **lambda được suy luận kiểu** (JEP 323), nhưng đó là thay đổi của Java 11, không phải Java 10. Chẳng hạn `(var a, var b) -> a + b` chỉ có ý nghĩa khi biểu thức lambda được đặt trong ngữ cảnh có kiểu hàm phù hợp.

### 2.3 Quy tắc sử dụng để code dễ đọc

- Dùng `var` khi vế phải làm kiểu hiển nhiên: `var names = new ArrayList<String>();`, `var input = Files.newBufferedReader(path);`.
- Dùng kiểu tường minh khi kiểu là thông tin quan trọng để đọc code: `List<String> names = loadNames();` có thể rõ hơn `var names = loadNames();` nếu chưa biết phương thức trả về gì.
- Không để `var` che khuất một kiểu quá cụ thể: `var items = new ArrayList<String>();` suy luận `ArrayList<String>`, trong khi `List<String> items = new ArrayList<>();` thể hiện rõ ý đồ lập trình theo interface.
- Chỉ dùng toán tử diamond `<>` khi ngữ cảnh cung cấp đủ kiểu. `var items = new ArrayList<>();` thường suy luận `ArrayList<Object>`, **không** tự suy ra `ArrayList<String>` theo ý định của người viết.
- Chú ý kiểu literal: `var total = 1;` là `int`, còn `var total = 1L;` là `long`. Chọn kiểu chủ đích khi phép tính cần độ rộng cụ thể.

Quy tắc thực tế: **ưu tiên sự rõ ràng tại nơi khai báo hơn việc tiết kiệm vài ký tự**.

## 3. Bản sao collection không cho sửa đổi: `copyOf`

### 3.1 Ba factory method xuất hiện từ Java 10

- `List.copyOf(Collection<? extends E>)` trả về một `List<E>` không cho thêm, xóa hay thay thế phần tử.
- `Set.copyOf(Collection<? extends E>)` trả về một `Set<E>` không cho sửa đổi và không có phần tử trùng nhau.
- `Map.copyOf(Map<? extends K, ? extends V>)` trả về một `Map<K,V>` không cho thêm, xóa hoặc thay đổi ánh xạ key/value.

Điểm chung: dữ liệu đầu vào không được `null` và **không được chứa phần tử `null`**; với `Map`, cả key lẫn value đều không được `null`. Vi phạm thường gây `NullPointerException`. Kết quả không cho thay đổi cấu trúc; thao tác như `add`, `remove` hoặc `put` sẽ bị từ chối, thông thường bằng `UnsupportedOperationException`.

Ví dụ:

~~~java
List<String> mutable = new ArrayList<>(List.of("red", "blue"));
List<String> snapshot = List.copyOf(mutable);
mutable.add("green");

// mutable:  [red, blue, green]
// snapshot: [red, blue]
// snapshot.add("yellow"); // UnsupportedOperationException
~~~

`List.copyOf` bảo toàn thứ tự duyệt của collection đầu vào. `Set.copyOf` loại phần tử trùng theo quy tắc của `Set`; nếu nhiều phần tử được coi là bằng nhau, phần tử đại diện được chọn không xác định. **Không dựa vào thứ tự duyệt** của `Set.copyOf` hoặc `Map.copyOf` vì API không cam kết thứ tự đó.

### 3.2 Khác biệt quan trọng: bản sao và view

`Collections.unmodifiableList(source)` tạo một **view chỉ đọc** nhìn vào danh sách nguồn. Nếu nguồn thay đổi qua tham chiếu khác, view cũng phản ánh thay đổi. Ngược lại, `List.copyOf(source)` tạo một snapshot về thành phần tại thời điểm gọi, nên thay đổi cấu trúc của danh sách nguồn sau đó không xuất hiện trong snapshot.

~~~java
// Ví dụ nằm trong thân phương thức:
var source = new ArrayList<>(List.of("A"));
var view = Collections.unmodifiableList(source);
var snapshot = List.copyOf(source);
source.add("B");

System.out.println(view);      // [A, B]
System.out.println(snapshot);  // [A]
~~~

Một chi tiết cần nhớ: **không cho sửa đổi collection không đồng nghĩa với bất biến sâu (deep immutability)**. Nếu các phần tử là đối tượng có thể thay đổi, cả source và snapshot vẫn có thể cùng tham chiếu đến một đối tượng đã đổi trạng thái. Hãy ưu tiên phần tử bất biến, bản sao phòng vệ phù hợp hoặc mô hình dữ liệu bất biến khi cần bất biến từ đầu đến cuối.

Không kiểm tra `source == snapshot` để xác định có sao chép hay không: triển khai được phép tái sử dụng một collection đã không cho sửa đổi. Ý nghĩa hợp đồng của API là tính không thể thay đổi cấu trúc và sự độc lập cần thiết với nguồn có thể sửa đổi, không phải luôn phải tạo đối tượng mới.

### 3.3 Trường hợp nên áp dụng

- Trả collection từ public API mà không để caller sửa trực tiếp dữ liệu nội bộ.
- Chốt tập quyền, danh mục hoặc cấu hình sau khi đọc/kiểm tra dữ liệu.
- Truyền một snapshot của tập đầu vào giữa các lớp, tránh bị tác động khi danh sách gốc tiếp tục được thay đổi.
- Tạo các giá trị chia sẻ đọc nhiều, cập nhật hiếm, với các phần tử có ngữ nghĩa phù hợp.

Ngược lại, nếu danh sách cần thêm/xóa liên tục, giữ `ArrayList`, `HashSet` hoặc `HashMap` có thể sửa đổi cho phần xử lý đó; chốt snapshot ở ranh giới hợp lý.

## 4. Thu kết quả Stream thành collection không cho sửa đổi

Java 10 bổ sung trong `java.util.stream.Collectors`:

| Collector | Kết quả | Lưu ý |
| --- | --- | --- |
| `Collectors.toUnmodifiableList()` | `List` không sửa đổi, giữ thứ tự gặp phần tử nếu Stream có thứ tự. | Không chấp nhận `null`. |
| `Collectors.toUnmodifiableSet()` | `Set` không sửa đổi. | Không chấp nhận `null`, loại phần tử trùng, không cam kết thứ tự duyệt. |
| `Collectors.toUnmodifiableMap(keyMapper, valueMapper)` | `Map` không sửa đổi. | Không chấp nhận key/value `null`; key trùng gây `IllegalStateException`. |
| `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` | `Map` không sửa đổi và chủ động xử lý key trùng. | Hàm gộp phải phù hợp ngữ nghĩa dữ liệu; kết quả cuối không chứa `null`. |

Ví dụ tổng hợp tần suất chuỗi, xử lý key trùng bằng `Integer::sum`:

~~~java
var counts = List.of("A", "B", "A").stream()
        .collect(Collectors.toUnmodifiableMap(
                value -> value,
                value -> 1,
                Integer::sum));
// counts.get("A") == 2; counts.get("B") == 1
~~~

Nếu bỏ `Integer::sum`, dữ liệu chứa hai phần tử `"A"` sẽ khiến overload hai tham số ném `IllegalStateException`. Đừng mặc định `toMap` hay `toUnmodifiableMap` tự quyết định bản ghi nào thắng khi key trùng.

Phân biệt các API dễ nhầm:

- `Collectors.toList()` **không cam kết** kết quả sửa đổi được hay không; nếu cần chắc chắn không sửa đổi thì dùng `toUnmodifiableList()`.
- `Stream.toList()` được bổ sung sau đó, từ **Java 16**: trực tiếp trả về danh sách không cho sửa đổi, nhưng có khác biệt về xử lý `null` so với `Collectors.toUnmodifiableList()`. Đừng thay hai API một cách máy móc khi luồng dữ liệu có thể chứa `null`.
- `List.of(...)` (Java 9) thích hợp khi biết ngay các phần tử lúc tạo; `List.copyOf(existing)` (Java 10) thích hợp khi đã có một collection; `collect(toUnmodifiableList())` thích hợp ở cuối pipeline Stream.

## 5. `Optional.orElseThrow()` không đối số

`Optional<T>` biểu diễn khả năng có hoặc không có giá trị. Từ Java 10, ta có thể gọi trực tiếp `optional.orElseThrow()`:

~~~java
var first = List.of("java", "api").stream()
        .filter("api"::equals)
        .findFirst()
        .orElseThrow();
// first == "api"
~~~

Nếu `Optional` rỗng, phương thức ném `NoSuchElementException`. Điều này phù hợp khi ứng dụng **yêu cầu chắc chắn có dữ liệu** và sự vắng mặt là tình huống bất thường. Nếu thiếu dữ liệu là hợp lệ, dùng `map`/`flatMap`, `ifPresent`, `orElse` hoặc `orElseGet` theo nghiệp vụ thay vì ném lỗi không cần thiết.

Khi cần một lỗi có thông điệp nghiệp vụ, overload nhận supplier được dùng:

~~~java
// Đoạn minh họa trong thân phương thức:
String role = Optional.ofNullable(config.get("role"))
        .orElseThrow(() -> new IllegalArgumentException("Missing role"));
~~~

Ở đây `config` được giả định là một `Map<String, String>` đã khai báo. Overload có supplier đã tồn tại trước Java 10; **phần Java 10 bổ sung chính là `orElseThrow()` không đối số**. Đây cũng là lựa chọn có tên diễn đạt rõ ý định hơn `Optional.get()` khi bắt buộc phải lấy giá trị.

## 6. Ví dụ thực hành tổng hợp — chạy từ Java 10 trở lên

Tạo tệp **`Java10RoleDemo.java`** sau. Chương trình chỉ dùng ngôn ngữ và API sẵn có ở Java 10 (cùng một số API cơ bản đã xuất hiện từ trước), nên có thể biên dịch/chạy bằng JDK hiện đại.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class Java10RoleDemo {
    public static void main(String[] args) {
        var mutable = new ArrayList<>(List.of("java", "api", "java"));
        var snapshot = List.copyOf(mutable);

        mutable.add("new"); // không thay đổi snapshot
        System.out.println("Snapshot: " + snapshot);

        var frequencies = snapshot.stream()
                .collect(Collectors.toUnmodifiableMap(
                        word -> word,
                        word -> 1,
                        Integer::sum));
        System.out.println("Java count: " + frequencies.get("java"));

        var unique = Set.copyOf(snapshot);
        System.out.println("Unique count: " + unique.size());

        var selected = snapshot.stream()
                .filter("api"::equals)
                .findFirst()
                .orElseThrow();
        System.out.println("Selected: " + selected);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 10+:

~~~bash
javac Java10RoleDemo.java
java Java10RoleDemo
~~~

Kết quả chuẩn, không phụ thuộc vào thứ tự duyệt `Set` hay `Map`:

~~~text
Snapshot: [java, api, java]
Java count: 2
Unique count: 2
Selected: api
~~~

Giải thích theo trình tự:

1. `var` suy luận kiểu các biến cục bộ mà không làm mất tính kiểm tra kiểu khi biên dịch.
2. `List.copyOf` giữ một snapshot gồm ba phần tử, ngay cả khi `mutable` được thêm `"new"` sau đó.
3. `Collectors.toUnmodifiableMap` tạo bảng đếm không sửa đổi; `Integer::sum` xử lý từ `"java"` xuất hiện hai lần.
4. `Set.copyOf` loại trùng, do đó số phần tử duy nhất là 2.
5. `findFirst().orElseThrow()` lấy `"api"`, hoặc sẽ ném lỗi nếu không tìm được.

Nếu cần tạo bytecode tương thích với môi trường Java 10 từ JDK mới hơn, có thể sử dụng `javac --release 10 Java10RoleDemo.java` **khi phiên bản `javac` đang dùng hỗ trợ đích `10`**. Tùy chọn `--release` kiểm tra cả API và mức ngôn ngữ của phiên bản đích; chỉ sử dụng cú pháp `var` trong IDE không đủ để chứng minh cả ứng dụng tương thích Java 10 nếu thư viện khác đòi JDK mới hơn.

## 7. Java 10 và cách quản lý phiên bản trong thực tế

JEP 322 điều chỉnh sơ đồ phiên bản cho mô hình phát hành theo thời gian. Một chuỗi phiên bản JDK có thể biểu diễn bằng `FEATURE.INTERIM.UPDATE.PATCH` (không nhất thiết in đủ các thành phần bằng 0). Ví dụ về mặt ý nghĩa: `21` là mức phát hành tính năng; `21.0.2` biểu thị một bản cập nhật của nhánh tính năng 21.

Khi chương trình thật sự cần kiểm tra phiên bản môi trường đang chạy, hãy dùng API có cấu trúc thay vì tách chuỗi `java.version` thủ công:

~~~java
int runningFeature = Runtime.version().feature();
System.out.println("Running feature version: " + runningFeature);
~~~

Đây là đoạn minh họa đặt trong một phương thức; kết quả phụ thuộc JDK đang chạy nên không có một dòng stdout cố định cho mọi máy.

Trong dự án thực tế:

1. **Chọn JDK được hỗ trợ và nhận cập nhật bảo mật** theo nhà cung cấp, thay vì giữ bản Java 10 đã cũ chỉ vì bài học nói về Java 10.
2. **Tách phiên bản chạy, phiên bản nguồn và đích biên dịch**: dự án dùng JDK mới để build có thể cần `--release` phù hợp nếu phải chạy trên nền tảng cũ; đồng thời xác minh phiên bản của dependencies.
3. **Phân biệt xuất xứ tính năng**: Java 10 đưa vào `var` cho biến cục bộ và các factory/collector nêu trên; Java 9 có `List.of` và module system; Java 11 mở rộng cú pháp `var` cho lambda; Java 16 bổ sung `Stream.toList()`.
4. **Ưu tiên đọc Javadoc của JDK mục tiêu** khi đánh giá hành vi API và điều kiện tương thích, thay vì suy đoán từ tên phương thức.

Như vậy, phần còn được dùng rộng rãi của Java 10 là **cách viết code rõ hơn, xử lý dữ liệu an toàn hơn ở ranh giới collection, và hiểu đúng vòng đời phiên bản JDK**.

## 8. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận/lỗi | Cách hiểu và xử lý đúng |
| --- | --- |
| “`var` có thể đổi kiểu trong lúc chạy.” | Kiểu được suy luận ngay khi biên dịch và giữ nguyên; chỉ giá trị tương thích với kiểu đó mới gán được. |
| “`var` dùng được cho mọi trường, tham số và kiểu trả về.” | Java 10 chỉ hỗ trợ những vị trí cục bộ theo quy tắc ngôn ngữ; chữ `var` không thay thế toàn bộ khai báo kiểu. |
| “`var list = new ArrayList<>()` chắc chắn là `List<String>`.” | Không có ngữ cảnh xác định `String`: kiểu suy luận thường là `ArrayList<Object>`; viết generic rõ ràng. |
| “`List.copyOf` là deep copy và làm bất biến mọi phần tử.” | Nó chặn sửa đổi cấu trúc collection, không tự sao chép sâu đối tượng bên trong. |
| “`Collections.unmodifiableList` luôn là snapshot.” | Đây thường là view phản ánh thay đổi của collection nguồn; dùng `List.copyOf` khi cần snapshot. |
| “Các `copyOf` chấp nhận `null`.” | Các factory method này từ chối `null` ở đầu vào/phần tử (hoặc key/value), cần làm sạch dữ liệu trước. |
| “`Set.copyOf` giữ nguyên mọi phần tử và thứ tự duyệt.” | Nó loại phần tử trùng và không cam kết thứ tự; đừng dựa vào thứ tự trong logic. |
| “`toUnmodifiableMap` tự chọn giá trị khi trùng key.” | Overload không có hàm gộp ném `IllegalStateException`; cung cấp `mergeFunction` nếu cần xử lý trùng. |
| “`Optional.orElseThrow()` trả về `null` khi thiếu.” | Nó ném `NoSuchElementException`; chọn phương án mặc định hoặc ngoại lệ nghiệp vụ khi thích hợp. |
| “Cần cài JDK 10 mới được dùng tính năng của Java 10.” | Những tính năng được duy trì ở các bản Java mới; chọn JDK còn được hỗ trợ cho ứng dụng. |

## 9. Tự kiểm tra kiến thức

**Câu 1.** Với `var number = 1;`, câu lệnh `number = 1L;` có hợp lệ không?

**Đáp án:** Không; `number` suy luận là `int`, không thể gán giá trị `long` cho `int` mà không chuyển kiểu tường minh.

**Câu 2.** Tạo `var snapshot = List.copyOf(source);` rồi thêm phần tử vào `source`, `snapshot` có tự tăng kích thước không?

**Đáp án:** Không, khi `source` là collection có thể thay đổi, `snapshot` độc lập đối với thay đổi cấu trúc sau thời điểm sao chép. Nhưng nếu phần tử là đối tượng mutable, trạng thái bên trong phần tử vẫn có thể thay đổi.

**Câu 3.** Khi biến Stream thành `Map` mà có hai phần tử cùng key, cần làm gì để có một kết quả có chủ đích?

**Đáp án:** Dùng `Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)` với quy tắc gộp rõ ràng (như `Integer::sum` cho bài toán đếm); nếu không, overload không có hàm gộp sẽ ném lỗi.

**Câu 4.** Vì sao mã Java có `List.of` không tự chứng minh `List.of` là tính năng Java 10?

**Đáp án:** `List.of` có từ Java 9; Java 10 đưa vào `List.copyOf` và các collector `toUnmodifiable...`. Cần tách biệt phiên bản giới thiệu từng API.

## 10. Tài liệu chính thống để tra cứu sâu hơn

- [Oracle — Java Language Changes: Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html).
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps (JDK 25)](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html).
- [Oracle — Collectors API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html).
- [Oracle — Optional API (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html).
- [OpenJDK — JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286).
- [OpenJDK — JEP 322: Time-Based Release Versioning](https://openjdk.org/jeps/322).

Các liên kết được đưa vào để tìm quy định gốc và Javadoc của những API còn sử dụng, không phải danh sách tính năng cũ cần áp dụng lại.