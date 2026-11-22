# Khai báo collection và generic lồng nhau với toán tử diamond `<>` trong Java

## 1. Vì sao cần generic và toán tử diamond?

Một `Collection` quản lý nhiều phần tử; `Map` quản lý các cặp khóa–giá trị. Khi chương trình cần lưu danh sách tên, bảng điểm theo người hoặc dữ liệu nhiều cấp, điều quan trọng là trình biên dịch phải biết **loại phần tử** ở từng cấp. Đó là vai trò của *generic*:

```java
List<String> names;
Map<String, Integer> ages;
Map<String, List<Integer>> scores;
```

- `List<String>`: mỗi phần tử của danh sách là một `String`.
- `Map<String, Integer>`: khóa là `String`, giá trị là `Integer`.
- `Map<String, List<Integer>>`: khóa là `String`; **mỗi giá trị là một danh sách `Integer`**, không phải một số đơn lẻ.

Để khởi tạo một đối tượng collection, Java cho phép **toán tử diamond `<>`** ở phần gọi constructor, chẳng hạn:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
```

Hai dấu `<` và `>` trống ở `new ArrayList<>()` có nghĩa: **trình biên dịch suy luận đối số kiểu phù hợp từ ngữ cảnh**, ở đây là `String`. Bạn vẫn khai báo kiểu rõ ràng ở vế trái để người đọc biết dữ liệu gì được lưu trong danh sách.

Diamond được đưa vào Java 7 và **vẫn được khuyến nghị sử dụng trong Java hiện đại** khi có ngữ cảnh đủ rõ. Nó giúp khai báo gọn hơn và tránh lặp lại một biểu thức generic dài ở hai vế. Diamond là tiện ích **kiểm tra và suy luận kiểu khi biên dịch**; nó không sinh một kiểu collection mới và không biến generics thành các đối tượng có tham số kiểu riêng tại runtime.

> Điểm cần nhớ: **Diamond áp dụng tại constructor** (`new ArrayList<>()`, `new HashMap<>()`), trong khi tham số kiểu của biến, trường, tham số phương thức và kiểu trả về vẫn phải được biểu diễn đúng theo hợp đồng kiểu dữ liệu.

## 2. Cú pháp khai báo collections đơn giản

Một số khai báo chuẩn sử dụng trong Java 17+:

```java
import java.util.*;

List<String> names = new ArrayList<>();
Set<String> tags = new HashSet<>();
Map<String, Integer> ages = new HashMap<>();
List<Long> ids = new ArrayList<>();
Map<String, Boolean> switches = new LinkedHashMap<>();
```

Đây là **các đoạn lệnh đặt trong phương thức hoặc phần khai báo phù hợp**; để biên dịch độc lập cần đặt vào một lớp Java. Khi viết phần mềm thông thường, nên dùng **kiểu giao diện** `List`, `Set`, `Map` ở vế trái và chọn triển khai `ArrayList`, `HashSet`, `HashMap`, `LinkedHashMap`... ở vế phải. Điều đó cho phép thay triển khai sau này khi yêu cầu thay đổi.

Ví dụ:

```java
List<String> tasks = new ArrayList<>();
tasks.add("Build");
tasks.add("Test");
// tasks.add(100); // Lỗi biên dịch: phần tử Integer không thuộc List<String>
```

`String`, `Integer`, `Long` là kiểu tham chiếu. Generic **không nhận kiểu nguyên thủy** trực tiếp: viết `List<Integer>` thay cho `List<int>`, `Map<String, Long>` thay cho `Map<String, long>`. Khi thêm một `int` vào `List<Integer>`, Java có thể tự đóng hộp (autoboxing) thành `Integer`.

Sự khác nhau giữa vài collection:

| Khai báo | Bảo đảm chính | Lưu ý khi chọn triển khai |
| --- | --- | --- |
| `List<String> list = new ArrayList<>();` | Danh sách theo chỉ số, cho phép phần tử trùng | `ArrayList` thường tiện khi đọc/duyệt theo chỉ số |
| `Set<String> set = new HashSet<>();` | Không chứa các phần tử trùng theo quy tắc `equals`/`hashCode` | `HashSet` không cam kết thứ tự duyệt |
| `Map<String, Integer> map = new HashMap<>();` | Mỗi khóa ánh xạ tới một giá trị | `HashMap` không cam kết thứ tự duyệt |
| `Map<String, Integer> map = new LinkedHashMap<>();` | Ánh xạ khóa–giá trị, giữ thứ tự chèn theo cấu hình mặc định | Hữu ích khi cần in kết quả có thứ tự ổn định |

Lựa chọn triển khai phụ thuộc yêu cầu nghiệp vụ. Diamond không ảnh hưởng đến tính thứ tự, tính thay đổi được, cấu trúc lưu trữ hoặc độ phức tạp của thuật toán.

## 3. Generic lồng nhau: đọc từ ngoài vào trong

### 3.1. Danh sách chứa danh sách

```java
List<List<String>> groups = new ArrayList<>();
```

Diễn giải từng lớp:

1. `List<...>` bên ngoài chứa nhiều **nhóm**.
2. Mỗi nhóm là một `List<String>`.
3. Mỗi phần tử bên trong nhóm là một `String`.

Ví dụ sử dụng:

```java
List<List<String>> groups = new ArrayList<>();
groups.add(new ArrayList<>(List.of("Lan", "Minh")));
groups.add(new ArrayList<>(List.of("An")));

String firstName = groups.get(0).get(0); // "Lan"
int numberOfGroups = groups.size();       // 2
int firstGroupSize = groups.get(0).size(); // 2
```

Đây là ví dụ Java 17+ vì sử dụng `List.of` (có từ Java 9). `List.of("Lan", "Minh")` tạo danh sách **không cho phép sửa cấu trúc**. Constructor `new ArrayList<>(...)` tạo một danh sách mới **có thể sửa**, nhờ vậy có thể gọi `groups.get(0).add("Hoa")`. Không nên lầm `List.of` và `new ArrayList<>(List.of(...))` có cùng khả năng thay đổi.

### 3.2. Map có giá trị là List

```java
Map<String, List<Integer>> scores = new HashMap<>();
```

Cách đọc chính xác:

- `Map` bên ngoài ánh xạ một `String` (tên người) sang một `List<Integer>` (các điểm).
- `List<Integer>` bên trong chứa nhiều `Integer`.
- Trong `new HashMap<>()`, diamond suy luận **cả hai đối số kiểu**: `String` cho khóa và `List<Integer>` cho giá trị.

Đoạn lệnh minh họa:

```java
Map<String, List<Integer>> scores = new HashMap<>();

scores.put("Lan", new ArrayList<>(List.of(9, 10)));
scores.put("Minh", new ArrayList<>(List.of(8)));

List<Integer> lanScores = scores.get("Lan");
int firstScore = lanScores.get(0); // 9
```

Khi dùng `get` với một khóa không tồn tại, kết quả có thể là `null`. Vì vậy, nếu tiếp tục gọi `.add(...)` mà không kiểm tra hoặc khởi tạo giá trị, chương trình có thể ném `NullPointerException`.

Một cách thích hợp để vừa tìm vừa khởi tạo danh sách là `computeIfAbsent`:

```java
scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(7);
```

Nếu chưa có danh sách cho `"Lan"`, lambda tạo `ArrayList` mới rồi lưu vào map; nếu đã có giá trị không null, trả lại danh sách đó để thêm điểm. Ở biểu thức `new ArrayList<>()` bên trong lambda, kiểu phần tử `Integer` được suy luận từ kiểu giá trị `List<Integer>` của `scores`.

### 3.3. Nhiều tầng Map và List

Giả sử cần lưu dữ liệu theo **năm → tên học viên → danh sách điểm**:

```java
Map<String, Map<String, List<Integer>>> scoresByYear
        = new LinkedHashMap<>();
```

Các lớp kiểu có thể hình dung:

```text
Map<String, Map<String, List<Integer>>>
 ├─ khóa ngoài: String                    (năm)
 └─ giá trị ngoài: Map<String, List<Integer>>
     ├─ khóa trong: String                 (học viên)
     └─ giá trị trong: List<Integer>
         └─ phần tử: Integer               (điểm)
```

Thêm một điểm mà không cần viết lại tên kiểu dài ở mỗi constructor:

```java
Map<String, Map<String, List<Integer>>> scoresByYear
        = new LinkedHashMap<>();

scoresByYear
        .computeIfAbsent("2026", year -> new LinkedHashMap<>())
        .computeIfAbsent("Lan", name -> new ArrayList<>())
        .add(9);
```

Biểu thức đầu tiên khởi tạo `Map<String, List<Integer>>` cho năm khi cần; biểu thức thứ hai khởi tạo `List<Integer>` cho học viên; cuối cùng thêm `9` vào danh sách. Mỗi toán tử diamond sử dụng **ngữ cảnh kiểu cụ thể của chính constructor đó**; không phải tất cả `<>` trong cùng dòng đều đại diện một kiểu giống nhau.

Từ Java 7 trở lên, nhiều dấu đóng generic liên tiếp như `>>>` trong `Map<String, Map<String, List<Integer>>>` được phân tích cú pháp bình thường. Trong ngữ cảnh type arguments, đây là dấu đóng ba lớp generic, **không phải** toán tử dịch phải không dấu.

## 4. Ví dụ chạy độc lập với collection lồng nhau

Ví dụ sau sử dụng `List` và `Map` lồng nhau, `LinkedHashMap` để kết quả in có thứ tự xác định, và diamond ở các constructor trực tiếp cũng như trong lambda.

Tạo tệp **`DiamondCollectionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class DiamondCollectionsDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add("Minh");

        Map<String, List<Integer>> scores = new LinkedHashMap<>();
        scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(9);
        scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(10);
        scores.computeIfAbsent("Minh", key -> new ArrayList<>()).add(8);

        List<List<String>> groups = new ArrayList<>();
        groups.add(new ArrayList<>(List.of("Lan", "Minh")));
        groups.add(new ArrayList<>(List.of("An")));

        Map<String, Map<String, List<Integer>>> byYear
                = new LinkedHashMap<>();

        byYear.computeIfAbsent("2026", year -> new LinkedHashMap<>())
              .computeIfAbsent("Lan", key -> new ArrayList<>())
              .add(9);

        System.out.println("names = " + names);
        System.out.println("scores = " + scores);
        System.out.println("groups = " + groups);
        System.out.println("byYear = " + byYear);
        System.out.println("Lan total = " + scores.get("Lan")
                .stream().mapToInt(Integer::intValue).sum());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 DiamondCollectionsDemo.java
java DiamondCollectionsDemo
```

Kết quả chuẩn đã kiểm tra:

```text
names = [Lan, Minh]
scores = {Lan=[9, 10], Minh=[8]}
groups = [[Lan, Minh], [An]]
byYear = {2026={Lan=[9]}}
Lan total = 19
```

Giải thích:

- `names` có kiểu `List<String>`; constructor `new ArrayList<>()` suy luận `String`.
- `scores` có kiểu `Map<String, List<Integer>>`. Mỗi khi thêm điểm, `computeIfAbsent` trả `List<Integer>`, nên chỉ các giá trị có thể chuyển sang `Integer` theo quy tắc kiểu mới được thêm vào.
- `groups` có kiểu `List<List<String>>`; mỗi phần tử của danh sách ngoài thực sự là một danh sách tên.
- `byYear` có ba tầng generic. Hai lambda với diamond được suy luận theo kiểu giá trị của map ở tầng đang truy cập.
- `LinkedHashMap` giữ thứ tự chèn, nên `scores` in `Lan` trước `Minh`; `HashMap` không hứa hẹn thứ tự như vậy.
- `mapToInt(Integer::intValue).sum()` biến các `Integer` thành số nguyên để cộng; `9 + 10 = 19`.

## 5. Diamond suy luận kiểu như thế nào?

Cú pháp:

```java
Map<String, List<Integer>> values = new HashMap<>();
```

cho phép trình biên dịch xác định kiểu cần khởi tạo từ kiểu đích `Map<String, List<Integer>>`. Một cách diễn giải ý nghĩa là: yêu cầu một đối tượng `HashMap` với khóa `String` và giá trị `List<Integer>`.

Suy luận kiểu không chỉ giới hạn ở phép gán biến. Java hiện đại cũng có thể dùng **ngữ cảnh phương thức** hoặc **kiểu trả về**:

```java
// Các đoạn sau được đặt trong một lớp Java với import phù hợp.
static Map<String, List<Integer>> newScoreMap() {
    return new HashMap<>();
}

static void acceptNames(List<String> names) {
    System.out.println(names.size());
}

static void example() {
    acceptNames(new ArrayList<>());
}
```

Ở `return new HashMap<>()`, kiểu trả về giúp suy luận kiểu map. Ở `acceptNames(new ArrayList<>())`, kiểu tham số `List<String>` giúp suy luận kiểu phần tử của `ArrayList`. Cơ chế suy luận có giới hạn và phải thỏa các ràng buộc generic; nếu không đủ ngữ cảnh, đôi khi cần khai báo đối số kiểu rõ hơn.

Một minh chứng kiểm tra kiểu ngay khi biên dịch:

```java
List<String> names = new ArrayList<>();
names.add("Lan");
// names.add(123); // Không biên dịch: Integer không thể thêm vào List<String>
```

Diamond không "bỏ qua" sự an toàn kiểu: trình biên dịch vẫn dùng `List<String>` để kiểm tra phần tử, kiểu tham số và kết quả trả về.

## 6. Cần phân biệt diamond với `var`

`var` là cú pháp khai báo biến cục bộ được hỗ trợ từ Java 10. Nó yêu cầu trình biên dịch suy luận kiểu **của biến** từ biểu thức khởi tạo. Diamond lại suy luận đối số kiểu **của constructor** từ ngữ cảnh. Khi kết hợp cả hai, cần chú ý:

```java
var unknown = new ArrayList<>();
unknown.add("Lan");
unknown.add(42);
```

Ở đây `unknown` được suy luận là `ArrayList<Object>` do không có kiểu phần tử cụ thể từ vế trái. Hai lời gọi `add` đều hợp lệ, nhưng chương trình đã mất ý định rằng danh sách chỉ chứa `String`.

Nếu muốn một danh sách tên có kiểu rõ ràng, chọn một trong hai cách:

```java
List<String> names = new ArrayList<>();   // Rõ kiểu ngay ở khai báo
var otherNames = new ArrayList<String>();  // Cụ thể hóa kiểu ở constructor
```

Cả hai đều là cú pháp còn hiệu lực trong Java hiện đại. Nên ưu tiên cách thứ nhất cho **generic lồng nhau** vì đọc kiểu dữ liệu từ trái sang phải thường dễ kiểm tra hơn:

```java
Map<String, List<Integer>> results = new HashMap<>();
```

Đừng viết `var results = new HashMap<>();` nếu mục đích là một map có khóa và giá trị được ràng buộc chặt chẽ: khi không có ngữ cảnh khác, các tham số kiểu có thể bị suy luận quá rộng (chẳng hạn `Object`).

## 7. Mở rộng: generic lồng nhau và wildcard

Generic trong Java **bất biến (invariant)** theo tham số kiểu. Dù `Integer` là một lớp con của `Number`, `List<Integer>` không tự động được xem là `List<Number>`:

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Lỗi biên dịch
```

Điều này giữ an toàn kiểu: nếu phép gán sai ở trên được chấp nhận, mã có thể thêm một `Double` vào một danh sách được khai báo chỉ cho phép `Integer`.

Nếu chỉ cần **đọc các số** từ một danh sách, có thể dùng wildcard:

```java
List<? extends Number> numbers = new ArrayList<Integer>();
Number first = null;
if (!numbers.isEmpty()) {
    first = numbers.get(0);
}
```

`? extends Number` cho phép làm việc với danh sách một kiểu con nào đó của `Number`, nhưng không được tùy ý `numbers.add(3)` vì trình biên dịch không biết danh sách thực sự lưu kiểu con nào. Trong ví dụ, `new ArrayList<Integer>()` đã có tham số kiểu cụ thể; ta cũng có thể dùng một biến `List<Integer>` rồi gán vào `List<? extends Number>`. Khi thiết kế API để **đọc từ danh sách**, `? extends T` có thể phù hợp; khi cần **ghi giá trị kiểu T vào danh sách**, cân nhắc `? super T` theo quy tắc sử dụng thực tế.

Với generic lồng nhau, đừng đánh đồng các dạng:

```java
List<List<Integer>> a = new ArrayList<>();
List<? extends List<Integer>> b = a;
```

`a` chứa chính xác các giá trị có kiểu phần tử `List<Integer>`; `b` nhìn danh sách ngoài như một loại danh sách có phần tử thuộc một kiểu con không xác định của `List<Integer>`, nên hạn chế thao tác thêm phần tử. Diamond không làm thay đổi quy tắc wildcard hay quan hệ kiểu.

Đối với trường hợp phổ biến là khai báo collections lồng nhau mà toàn bộ phần tử do chương trình kiểm soát, thường chỉ cần tham số kiểu cụ thể như `Map<String, List<Integer>>`; thêm wildcard khi API thực sự cần mức linh hoạt đó.

## 8. Collections thay đổi được và không thay đổi được

Diamond được dùng trong **lệnh gọi constructor**, còn các phương thức tiện ích hiện đại như `List.of`, `Set.of`, `Map.of` không dùng từ khóa `new` hay diamond:

```java
List<String> fixed = List.of("Lan", "Minh");
List<String> editable = new ArrayList<>(fixed);
editable.add("An");
```

- `fixed` là collection không cho phép sửa; thêm phần tử vào đó sẽ ném `UnsupportedOperationException`.
- `editable` là danh sách mới cho phép thêm/xóa, vì dùng constructor `ArrayList`.
- Constructor `new ArrayList<>(fixed)` tạo bản sao danh sách **nông**: nếu phần tử là đối tượng có thể thay đổi, không tự sao chép sâu từng đối tượng.

`List.of` cũng không chấp nhận phần tử `null`. Với generic lồng nhau, hãy xác định rõ từng tầng có cần sửa hay không; ví dụ `List<List<String>>` không đảm bảo mọi danh sách con có thể sửa chỉ vì kiểu ngoài là `List`.

Không có sự khác biệt về **mutability** giữa `new ArrayList<String>()` và `new ArrayList<>()` khi hai biểu thức đã được kiểm tra với cùng kiểu: diamond chỉ giảm phần lặp tham số kiểu trong mã nguồn.

## 9. Lỗi thường gặp và cách khắc phục

| Lỗi hoặc hiểu lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `List<> names = new ArrayList<>();` | Diamond không thay thế khai báo tham số kiểu ở vế trái | `List<String> names = new ArrayList<>();` |
| `new ArrayList<>` | Constructor phải có dấu gọi `()` | `new ArrayList<>()` |
| `List<int> numbers` | Generic không nhận kiểu nguyên thủy | `List<Integer> numbers` |
| `Map<String, List<Integer>> x = new HashMap<String, List<String>>();` | Kiểu giá trị `List<String>` khác `List<Integer>` | Dùng `new HashMap<>()` với khai báo đúng |
| `List<List<String>> groups` rồi thêm `List<Integer>` | Hai tầng kiểu không tương thích | Thêm `List<String>` cho mỗi nhóm |
| `map.get(key).add(value)` khi `key` chưa tồn tại | `get` có thể trả `null` | Khởi tạo bằng `computeIfAbsent` hoặc kiểm tra riêng |
| `var names = new ArrayList<>();` với kỳ vọng `List<String>` | Thiếu ngữ cảnh kiểu, thường suy luận thành `ArrayList<Object>` | Khai báo `List<String> names = new ArrayList<>();` |
| Dùng raw type `List names = new ArrayList();` | Mất thông tin kiểu và có thể gây cảnh báo hoặc lỗi ép kiểu lúc chạy | Dùng `List<String> names = new ArrayList<>();` |
| Coi `HashMap` có thứ tự duyệt cố định | `HashMap` không cam kết thứ tự | Dùng `LinkedHashMap` khi thứ tự chèn là một phần yêu cầu |
| Thêm vào danh sách tạo bởi `List.of` | Danh sách không cho phép thay đổi | Dùng `new ArrayList<>(List.of(...))` |
| Nghĩ rằng `new ArrayList<>(source)` sao chép sâu | Constructor chỉ sao chép phần tử tham chiếu | Sao chép từng phần tử có thể thay đổi khi thật sự cần |

Một lỗi khác trong Java generics là cố tạo **mảng generic** trực tiếp:

```java
// List<String>[] rows = new List<String>[3]; // Lỗi biên dịch
```

Nếu cần một tập các danh sách `String`, thông thường dùng `List<List<String>> rows = new ArrayList<>();` để quản lý linh hoạt. Java áp dụng *type erasure* cho phần lớn thông tin generic khi chạy, vì thế một `List<String>` và một `List<Integer>` đều là `List` ở mức kiểm tra runtime, dù trình biên dịch phân biệt và kiểm tra chúng trong mã nguồn. Không sử dụng `instanceof List<String>` để kiểm tra tham số kiểu đã bị xóa; thay vào đó dùng `instanceof List<?>` khi cần kiểm tra loại container.

## 10. Thiết kế rõ kiểu khi cấu trúc lồng quá sâu

Khả năng khai báo kiểu như:

```java
Map<String, Map<String, List<Integer>>> byYear = new HashMap<>();
```

không có nghĩa lúc nào cũng nên thêm nhiều tầng. Nếu dữ liệu mang các khái niệm nghiệp vụ rõ ràng như **năm, học viên, bản ghi điểm**, có thể tạo lớp hoặc `record` biểu diễn từng khái niệm, giúp tên trường và quy tắc dữ liệu rõ ràng hơn.

Ví dụ Java 17+:

```java
record StudentScores(String student, List<Integer> grades) {}

Map<String, List<StudentScores>> scoresByYear = new HashMap<>();
```

`record` trong ví dụ cung cấp kiểu dữ liệu có tên cho một bản ghi điểm. Bản thân `record` không tự làm danh sách `grades` trở nên bất biến; nếu dữ liệu không được phép thay đổi, cần tạo bản sao bảo vệ, chẳng hạn bằng `List.copyOf` sau khi đã kiểm tra yêu cầu `null`.

Ngoài ra, khi một cấu trúc Map chứa nhiều tầng và có khả năng xuất hiện khóa thiếu, cân nhắc việc xử lý `null`, khởi tạo giá trị và quy tắc cập nhật ở một phương thức có tên rõ ràng, thay vì lặp lại chuỗi `get`/`put` phức tạp trong nhiều vị trí.

## 11. Bài tập và đáp án

**Bài 1.** Khai báo một `Map` ánh xạ mã môn học (`String`) sang danh sách tên học viên (`List<String>`), dùng diamond ở constructor.

**Bài 2.** Cách đọc kiểu `List<Map<String, Set<Integer>>>` là gì? Tham số kiểu nào thuộc danh sách ngoài, map giữa và set trong?

**Bài 3.** Với `Map<String, List<Integer>> scores = new HashMap<>();`, hãy thêm điểm 10 cho khóa `"Lan"`, kể cả khi khóa chưa tồn tại.

**Bài 4.** Vì sao `var data = new ArrayList<>();` không ràng buộc phần tử là `String`? Hãy viết hai cách khai báo ràng buộc phần tử.

**Bài 5.** Cho `List<String> a = List.of("Lan");`. Vì sao `a.add("Minh")` thất bại lúc chạy? Làm sao tạo một danh sách có thể sửa bằng diamond?

**Đáp án:**

1. `Map<String, List<String>> studentsByCourse = new HashMap<>();`.
2. Danh sách ngoài chứa các `Map<String, Set<Integer>>`; mỗi map ánh xạ một `String` sang một `Set<Integer>`; set trong chứa các `Integer` khác nhau.
3. `scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(10);`.
4. `var` suy luận kiểu từ `new ArrayList<>()` khi không có ngữ cảnh phần tử rõ, dẫn đến `ArrayList<Object>`. Dùng `List<String> data = new ArrayList<>();` hoặc `var data = new ArrayList<String>();`.
5. `List.of` trả danh sách không cho phép sửa. Tạo `List<String> b = new ArrayList<>(a);` rồi gọi `b.add("Minh")`.

**Ghi nhớ:** Khai báo đầy đủ kiểu của collection lồng nhau ở vế trái; dùng **diamond `<>`** ở constructor để trình biên dịch suy luận tham số kiểu và tránh lặp cú pháp. Luôn phân biệt kiểu ngoài–kiểu trong, danh sách sửa được–không sửa được, suy luận kiểu với `var` và các ràng buộc generic để mã Java hiện đại vừa gọn vừa an toàn kiểu.