# List.of, Set.of, Map.of và Map.ofEntries

Khi danh sách trạng thái, tập quyền hoặc bảng tra cứu đã được xác định ngay lúc xây dựng, viết một loạt `add` và `put` dễ làm ý định bị chìm trong thao tác khởi tạo. Các phương thức `List.of`, `Set.of`, `Map.of` và `Map.ofEntries` cho phép ghi trực tiếp dữ liệu cần có và trả về vật chứa không sửa được.

Điều quan trọng không chỉ là cú pháp ngắn. Mỗi phương thức diễn đạt một hợp đồng về thứ tự, phần tử trùng, `null` và quyền sửa. Chọn sai hợp đồng có thể làm chương trình ném ngoại lệ ngay khi tạo dữ liệu, hoặc làm một kiểm thử phụ thuộc vào thứ tự duyệt không được bảo đảm.

Các phương thức này có từ **Java 9**. Toàn bộ chương trình trong bài dùng mức Java 17, không cần thư viện ngoài. Người học cần biết ý nghĩa cơ bản của `List`, `Set`, `Map`, kiểu tham số và ngoại lệ. [Các bổ sung của JDK 9](https://docs.oracle.com/javase/9/whatsnew/).

## 1. Chọn ý nghĩa dữ liệu trước khi chọn lời gọi

Xét một công cụ quản lý tác vụ:

- Các bước `"receive"`, `"validate"`, `"store"` có thứ tự. Lặp một bước có thể có ý nghĩa. Đây là dữ liệu dạng list.
- Các quyền `"READ"`, `"WRITE"` là thành viên của một tập. Thứ tự khai báo không nhất thiết là thứ tự hiển thị. Đây là dữ liệu dạng set.
- Mã trạng thái `"NEW"` tương ứng một nhãn hiển thị. Mỗi mã phải ánh xạ tới một giá trị. Đây là dữ liệu dạng map.

Đoạn sau là mã minh họa trong một phương thức có đủ import:

~~~java
List<String> pipeline = List.of("receive", "validate", "store");
Set<String> permissions = Set.of("READ", "WRITE");
Map<String, String> labels = Map.of(
        "NEW", "Mới",
        "DONE", "Hoàn tất"
);
~~~

Đừng dùng set chỉ để làm các phần tử “không sửa được” nếu thứ tự và lặp lại còn quan trọng. List cũng có thể không sửa được. Ngược lại, đừng dùng list thay cho tập quyền rồi để những phần tử trùng gây hiểu nhầm về dữ liệu.

Map không phải là một list chứa các cặp theo thứ tự tham số. Cú pháp `"NEW", "Mới", "DONE", "Hoàn tất"` mô tả các ánh xạ, không tạo cam kết rằng `"NEW"` sẽ được duyệt trước `"DONE"`.

Các phương thức là **phương thức tạo tĩnh** (static factory methods) trên giao diện. Chúng tạo và trả một đối tượng thỏa hợp đồng của giao diện; chương trình không cần biết lớp triển khai bên trong. Hãy lưu kết quả bằng kiểu `List<E>`, `Set<E>` hoặc `Map<K,V>` phù hợp.

## 2. Bảng hợp đồng cần nhớ

| Cách tạo | Dữ liệu đầu vào | Trùng lặp | `null` khi tạo | Thứ tự kết quả |
| --- | --- | --- | --- | --- |
| `List.of(e1, e2, ...)` | Các phần tử | Cho phép phần tử bằng nhau | Không cho phần tử `null` | Giữ thứ tự các đối số |
| `Set.of(e1, e2, ...)` | Các phần tử | Từ chối phần tử trùng bằng `IllegalArgumentException` | Không cho phần tử `null` | Không có cam kết về thứ tự duyệt |
| `Map.of(k1, v1, k2, v2, ...)` | Các cặp khóa–giá trị xen kẽ | Từ chối khóa trùng; giá trị có thể trùng | Không cho khóa hoặc giá trị `null` | Không có cam kết về thứ tự duyệt |
| `Map.ofEntries(entry1, entry2, ...)` | Các `Map.Entry` | Từ chối khóa trùng; giá trị có thể trùng | Không cho entry, khóa hoặc giá trị `null` | Không có cam kết về thứ tự duyệt |

Kết quả của cả bốn cách tạo đều **không sửa được qua API vật chứa**: không thêm, xóa hoặc thay thế phần tử/ánh xạ. Riêng các đối tượng phần tử, khóa và giá trị có thể vẫn sửa được nếu kiểu của chúng cho phép.

Cần đọc hai cột “trùng” và “thứ tự” cùng nhau. Set không có phần tử trùng không đồng nghĩa set đã được sắp xếp. Map không có khóa trùng không đồng nghĩa khóa đầu tiên trong lời gọi là khóa đầu tiên khi duyệt.

Tài liệu Java 17 mô tả riêng các bảo đảm của [list không sửa được](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable), [set không sửa được](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable) và [map không sửa được](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

## 3. `List.of`: một dãy có thứ tự, cho phép lặp lại

### Cú pháp từ rỗng đến nhiều phần tử

~~~java
List<String> empty = List.of();
List<String> single = List.of("ready");
List<String> repeated = List.of("start", "retry", "retry", "finish");
~~~

Ở list cuối, hai lần `"retry"` là hai vị trí trong dãy. Không có bước loại trùng. `get(0)` là `"start"` và thứ tự dãy theo đúng thứ tự đối số.

Java cung cấp các overload với số đối số cố định từ 0 đến 10 và một dạng nhận số đối số thay đổi (varargs). Vì vậy **`List.of` không bị giới hạn ở 10 phần tử**:

~~~java
List<Integer> months = List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);
~~~

Không cần biết overload nào được chọn để dùng đúng hợp đồng list. Cũng không nên suy ra một ngưỡng hiệu năng hoặc cấu trúc lưu trữ ổn định từ số lượng overload.

### Không hỗ trợ cả thêm, xóa lẫn thay phần tử

Với list do `List.of` tạo, `add` và `remove` bị từ chối; `set` cũng bị từ chối. Đây không phải list “chỉ cố định kích thước nhưng còn cho thay ô”.

Đoạn sau là **ví dụ thao tác sẽ ném ngoại lệ**, không phải cách cập nhật list:

~~~java
List<String> steps = List.of("draft", "review");
steps.set(0, "editing"); // UnsupportedOperationException
~~~

Một thuật toán sắp xếp tại chỗ hay `replaceAll` cũng là thao tác sửa. Nếu cần các thao tác ấy, tạo bản làm việc có hợp đồng sửa được, hoặc xây dựng kết quả mới bằng một phép biến đổi.

### Kiểu phần tử của kết quả rỗng cần được đặt trong ngữ cảnh

~~~java
List<String> declared = List.of();
var inferred = List.of();
List<String> explicit = List.<String>of();
~~~

`declared` lấy kiểu phần tử từ kiểu đích. Trong ví dụ `var`, không có kiểu đích cụ thể như `List<String>`, nên không nên giả định trình biên dịch tự biết đó là list chuỗi chỉ vì dự định của người viết.

Có thể ghi kiểu rõ khi một API hoặc biểu thức phức tạp cần nó. Kiểu đích giải quyết vấn đề kiểu dữ liệu; nó không đổi quyền sửa kết quả.

## 4. `Set.of`: khai báo một tập thành viên hợp lệ

### Lỗi trùng là lỗi dữ liệu đầu vào

~~~java
Set<String> states = Set.of("NEW", "RUNNING", "DONE");
~~~

Cách khai báo này phù hợp khi mỗi thành viên chỉ được nêu một lần. Nếu danh sách đối số có hai giá trị bằng nhau, lời gọi ném `IllegalArgumentException` thay vì lặng lẽ giữ lại một.

~~~java
Set<String> invalid = Set.of("NEW", new String("NEW"));
// IllegalArgumentException: hai chuỗi bằng nhau theo equals.
~~~

Ví dụ cố ý sai ở trên giúp phân biệt `Set.of` với một quy trình thu thập dữ liệu rồi loại trùng. Nếu đầu vào người dùng thực sự có thể lặp và yêu cầu là gộp lặp, hãy dùng quy trình thích hợp cho yêu cầu đó; đừng chọn một phương thức từ chối trùng rồi coi ngoại lệ là sự cố bất ngờ.

### Trùng được xác định theo bình đẳng giá trị

Hai đối tượng khác nhau về tham chiếu vẫn có thể là phần tử trùng. Ngược lại, cùng `hashCode` chưa đủ làm hai phần tử trùng nếu chúng không bằng nhau theo `equals`.

Chương trình hoàn chỉnh sẽ dùng `"Aa"` và `"BB"`: hai chuỗi này có cùng mã băm nhưng không bằng nhau, nên một set gồm hai chuỗi vẫn hợp lệ. Kết quả không được suy ra chỉ bằng so sánh mã băm.

Nếu dùng một lớp tự viết làm phần tử, hợp đồng `equals`/`hashCode` của lớp phải đúng. Đừng thay đổi trạng thái tham gia so sánh khi đối tượng đang là phần tử set; tính không sửa được của set ngoài không ngăn sửa chính đối tượng ấy.

### Không phải tập sắp xếp hay tập giữ thứ tự chèn

`Set.of("z", "a", "m")` không cam kết duyệt theo `z, a, m`, cũng không cam kết `a, m, z`. Trong một lần chạy có thể tình cờ thấy một trong các thứ tự ấy.

Nếu đầu ra cho người dùng cần sắp xếp, thực hiện sắp xếp rõ ràng. Ví dụ trong chương trình dùng `new TreeSet<>(colors)` chỉ để **tạo biểu diễn in có thứ tự** cho dữ liệu chuỗi. Điều đó không thay hợp đồng của set gốc.

Nếu thứ tự chính là ý nghĩa của dữ liệu, cân nhắc dùng list hoặc một cấu trúc giữ thứ tự có hợp đồng rõ. Không thể suy ra thứ tự nghiệp vụ bằng cách đọc lần duyệt đầu tiên của `Set.of`.

Giống `List.of`, `Set.of` có dạng varargs nên cũng hỗ trợ hơn 10 phần tử, miễn các phần tử không trùng và không `null`.

## 5. `Map.of`: đọc theo từng cặp khóa–giá trị

### Cú pháp xen kẽ phải được nhóm cho dễ đọc

~~~java
Map<String, Integer> retries = Map.of(
        "network", 3,
        "database", 2,
        "validation", 0
);
~~~

Mỗi khóa đứng ngay trước giá trị của nó. Kết quả có ba ánh xạ. `get("network")` trả 3.

Hãy xuống dòng theo từng cặp. Với lời gọi dài trên một dòng, việc ghép nhầm khóa–giá trị vẫn có thể biên dịch nếu các tham số có kiểu tương thích nhưng ý nghĩa dữ liệu đã sai.

Giới hạn của `Map.of` là **tối đa 10 cặp**, không phải 10 đối số đơn lẻ. Nó có các overload cho 0 đến 10 ánh xạ; không có dạng varargs nhận một dãy tùy ý `k1, v1, k2, v2, ...`. Nhu cầu 11 cặp cần `Map.ofEntries` hoặc một cách xây dựng khác.

### Giá trị trùng được; khóa trùng không được

~~~java
Map<String, Integer> aliases = Map.of("one", 1, "single", 1);
~~~

Map có hai khóa khác nhau cùng trỏ tới giá trị bằng 1. Đây là dữ liệu hợp lệ.

Nhưng đoạn cố ý sai sau ném `IllegalArgumentException`:

~~~java
Map<String, Integer> invalid = Map.of("x", 1, "x", 2);
~~~

Nó không thực hiện quy tắc “ghi sau thắng” như hai lời gọi `put` thông thường trên nhiều map sửa được. Ngay cả `Map.of("x", 1, "x", 1)` vẫn có khóa trùng và bị từ chối, dù hai giá trị giống nhau.

Cách tạo này hữu ích để phát hiện lỗi bảng tra cứu khai báo: một mã bị gõ lặp sẽ không âm thầm đè ánh xạ trước.

### Không có khóa là chuyện khác với khóa có giá trị `null`

Map này không cho giá trị `null`. `get` với một khóa hợp lệ nhưng không có mặt vẫn trả `null` theo hợp đồng thông thường của map.

Do đó `map.get("missing") == null` không chứng minh map đã lưu một giá trị `null`. Trong chương trình minh chứng, đó là dấu hiệu không có ánh xạ cho chuỗi `"missing"`.

Cũng không suy từ việc cấm lưu khóa `null` thành lời hứa rằng mọi phép hỏi bằng `null` sẽ trả `false` hoặc `null`. Các thao tác truy vấn phần tử/khóa không hợp lệ có quy tắc riêng và có thể ném ngoại lệ. Nếu đầu vào tra cứu có thể `null`, xử lý điều kiện ấy rõ trước khi tra.

## 6. `Map.ofEntries` và vai trò của `Map.entry`

### Mỗi cặp trở thành một đối số có cấu trúc

~~~java
Map<String, Integer> thresholds = Map.ofEntries(
        Map.entry("low", 10),
        Map.entry("medium", 20),
        Map.entry("high", 30)
);
~~~

`Map.entry(k, v)` tạo một đối tượng `Map.Entry<K,V>` chứa cặp khóa–giá trị. Tạo entry chưa tạo map và cũng chưa thêm cặp vào một map đang tồn tại.

`Map.ofEntries` nhận các entry, lấy khóa và giá trị của chúng để tạo map không sửa được. Nó dùng varargs nên hỗ trợ số entry lớn hơn 10; giới hạn thực tế vẫn là tài nguyên và giới hạn nền tảng thông thường, không có lời hứa “vô hạn”.

Có thể dùng import tĩnh cho các bảng lớn:

~~~java
import static java.util.Map.entry;
~~~

Khi đã có import này, viết `entry("low", 10)` trong `Map.ofEntries`. Đây là lựa chọn cách viết; `Map.entry` đầy đủ thường dễ nhận diện hơn với người mới.

### Entry đầu vào không là nơi lưu ánh xạ sau đó

`Map.ofEntries` lấy khóa và giá trị, không lưu chính các entry đầu vào. Vì vậy thay giá trị của một entry sửa được sau khi tạo không phải cách cập nhật map kết quả. [API Map.ofEntries, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#ofEntries(java.util.Map.Entry...)).

Ví dụ minh họa:

~~~java
AbstractMap.SimpleEntry<String, Integer> sourceEntry =
        new AbstractMap.SimpleEntry<>("limit", 3);

Map<String, Integer> result = Map.ofEntries(sourceEntry);
sourceEntry.setValue(9);
~~~

Sau đó `sourceEntry.getValue()` là 9 nhưng `result.get("limit")` vẫn là 3. Đó là thay một tham chiếu giá trị trong entry nguồn; map đã lấy cặp tham chiếu trước đó.

Nếu giá trị là một list sửa được, map và entry nguồn vẫn có thể cùng giữ tham chiếu tới list ấy. Việc không giữ chính entry không có nghĩa nhân bản sâu đối tượng khóa và giá trị.

### `Map.entry` không cho `setValue`

Entry do `Map.entry` tạo không sửa được, từ chối khóa hoặc giá trị `null` và không tự gắn với map nào. `entry.setValue(...)` ném `UnsupportedOperationException`.

Cần phân biệt hợp đồng của một entry cụ thể với bản thân giao diện `Map.Entry`. Giao diện cũng được dùng cho nhiều entry có nguồn gốc và quyền sửa khác nhau; không thể nhìn kiểu `Map.Entry` rồi kết luận tất cả đều hỗ trợ hay đều từ chối `setValue`. [Giao diện Map.Entry, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

Một chi tiết khi cần tuần tự hóa: entry do `Map.entry` tạo **không hỗ trợ tuần tự hóa**. Điều đó không ngăn map do `Map.ofEntries` tạo hỗ trợ tuần tự hóa khi các khóa và giá trị đáp ứng hợp đồng tương ứng, vì map không giữ các entry đầu vào. Đừng suy khả năng của đối tượng trung gian sang đối tượng kết quả.

## 7. `null` và trùng lặp: xác định lỗi ở đúng tầng

### Dùng kiểu rõ trong ví dụ `null`

~~~java
List.of("ok", (String) null);
Set.of("ok", (String) null);
Map.of("x", (Integer) null);
Map.entry("x", (Integer) null);
~~~

Tất cả các lời gọi trên là ví dụ cố ý sai và ném `NullPointerException`. Ép kiểu trong ví dụ giúp thể hiện rõ vị trí dữ liệu `null` đang được kiểm tra.

Với varargs còn có sự khác nhau giữa “một phần tử `null`” và “cả mảng tham số là `null`”:

~~~java
List.of((String) null);    // Một phần tử null.
List.of((String[]) null);  // Mảng varargs null.
~~~

Cả hai đều không hợp lệ. Không dùng một lời gọi trần như `List.of(null)` để giải thích số phần tử nếu còn chưa xác định overload và kiểu mà trình biên dịch chọn.

### `Map.ofEntries` có nhiều vị trí có thể `null`

Đầu vào không hợp lệ có thể là:

- Chính mảng entry là `null`.
- Một phần tử entry trong mảng là `null`.
- Một entry không `null` nhưng chứa khóa hoặc giá trị `null`.

`Map.entry` đã từ chối `null` ngay khi tạo cặp. Để minh chứng việc `Map.ofEntries` cũng kiểm tra nội dung entry đến từ nơi khác, chương trình dùng `SimpleEntry` có khóa `null` và xác nhận lỗi tại bước tạo map.

Trong biểu thức `Map.ofEntries(Map.entry("x", null))`, lỗi đã có thể phát sinh trong `Map.entry` trước khi lời gọi ngoài được thực hiện. Khi đọc stack trace, phân biệt đúng nơi xây dựng dữ liệu sẽ giúp chẩn đoán dễ hơn.

Nếu dữ liệu có đồng thời nhiều lỗi, chẳng hạn vừa trùng vừa có `null`, không nên viết kiểm thử bắt buộc một thứ tự phát hiện lỗi mà hợp đồng không quy định. Thử từng ràng buộc với dữ liệu chỉ vi phạm ràng buộc đang kiểm tra.

### Đây không phải bước làm sạch dữ liệu tự động

Các factory này thích hợp để khẳng định dữ liệu đã có hình dạng hợp lệ. Chúng không tự thay `null` bằng chuỗi rỗng, không tự gộp khóa lặp và không tự chọn giá trị “đúng” khi có xung đột.

Nếu đầu vào đến từ biểu mẫu hay tệp cấu hình, hãy kiểm tra và báo lỗi với ngữ cảnh nghiệp vụ trước khi tạo cấu trúc cuối. `NullPointerException` hoặc `IllegalArgumentException` từ factory không thay thế một thông báo dễ hiểu như “mã trạng thái DONE được khai báo hai lần”.

## 8. Mảng, varargs và phần tử thật sự của collection

### Truyền mảng tham chiếu để lấy nhiều phần tử

~~~java
String[] codes = {"a", "b"};
List<String> list = List.of(codes);
Set<String> set = Set.of(codes);
~~~

Trong cách gọi này, mảng cung cấp các phần tử cho factory. List có hai chuỗi theo thứ tự mảng. Set cũng chứa hai chuỗi, với điều kiện không trùng. Nếu mảng có `null` hoặc phần tử trùng khi tạo set, các ràng buộc vẫn áp dụng.

Kết quả không là view ghi xuyên tới các ô của mảng đầu vào. Đổi `codes[0]` sau đó không đổi phần tử của list/set đã tạo. Chương trình minh chứng sẽ kiểm tra điểm này trực tiếp.

Đây là một khác biệt quan trọng với `Arrays.asList(codes)`: list của `Arrays.asList` dựa trên mảng và còn hỗ trợ thay phần tử. [API Arrays.asList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### Muốn một phần tử là chính mảng thì phải nói rõ

~~~java
List<String[]> oneArray = List.<String[]>of(codes);
~~~

Ở đây list chỉ có **một phần tử** và phần tử ấy là đối tượng mảng `codes`. Đổi `codes[0]` sẽ được quan sát qua `oneArray.get(0)[0]` vì mảng là phần tử được chia sẻ.

Không có mâu thuẫn với ví dụ trước: hai lời gọi đã chọn hai mô hình dữ liệu khác nhau. Một lời gọi lấy các chuỗi làm phần tử; lời gọi còn lại lấy mảng làm phần tử.

Cách truyền mảng và ghi tham số kiểu rõ được nêu trong API `List.of(E...)` và `Set.of(E...)`. Java giải quyết overload theo kiểu biểu thức và các pha xác định phương thức áp dụng; không phải dựa vào ý muốn ngầm của người viết. [Quy tắc gọi phương thức trong JLS 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.2).

### Mảng kiểu nguyên thủy không tự thành nhiều wrapper

~~~java
List<int[]> numbers = List.of(new int[]{3, 4});
~~~

List có một phần tử `int[]`, không phải hai `Integer`. Một đối tượng `int[]` không phải `Integer[]` và factory không tự đi vào mảng để boxing từng số.

Để khai báo dãy các số nguyên dạng wrapper, dùng `List.of(3, 4)`. Để chuyển dữ liệu từ mảng nguyên thủy đã tồn tại, chọn một bước chuyển đổi rõ ràng; không đoán kiểu phần tử từ dấu ngoặc của mảng.

Cũng cần lưu ý khi truyền một collection sẵn có:

~~~java
List<String> existing = new ArrayList<>(List.of("a", "b"));
List<List<String>> oneList = List.of(existing);
~~~

`oneList` có một phần tử là list `existing`; `of` không phải thao tác “bung” mọi collection. Khi mục tiêu là tạo bản không sửa được từ các phần tử của một collection đã có, `copyOf` là họ API khác cần xem xét. Hãy xác định đúng kiểu phần tử trước khi chọn.

## 9. Chương trình hoàn chỉnh kiểm tra hợp đồng

Lưu mã vào **`CollectionFactoriesDemo.java`**. Chương trình không in trực tiếp set/map có thứ tự duyệt không được bảo đảm. Các dòng in có thứ tự dùng `TreeSet` hoặc `TreeMap` cho khóa và phần tử chuỗi; các phép kiểm tra khác dùng `size`, `get`, `contains` hoặc `equals`.

Hàm `rejects` xác nhận đúng loại ngoại lệ mong đợi. Nếu một thao tác bất ngờ thành công hoặc ném sai loại, chương trình dừng bằng `AssertionError`. Nó không dựa vào nội dung thông báo ngoại lệ vì thông báo không phải điều cần kiểm chứng ở đây.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionFactoriesDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + " wrong exception", ex);
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("empty.sizes="
                + List.of().size() + "/"
                + Set.of().size() + "/"
                + Map.of().size() + "/"
                + Map.ofEntries().size());

        List<String> levels = List.of("low", "high", "low");
        System.out.println("list=" + levels);
        System.out.println("list.index1=" + levels.get(1));
        rejects("list.add", UnsupportedOperationException.class,
                () -> levels.add("medium"));
        rejects("list.set", UnsupportedOperationException.class,
                () -> levels.set(0, "medium"));

        Set<String> colors = Set.of("red", "blue", "green");
        System.out.println("set.sorted=" + new TreeSet<>(colors));
        System.out.println("set.containsGreen=" + colors.contains("green"));
        rejects("set.add", UnsupportedOperationException.class,
                () -> colors.add("black"));
        System.out.println("set.hashCollision.size="
                + Set.of("Aa", "BB").size());

        Map<String, Integer> limits = Map.of("small", 2, "large", 4);
        System.out.println("map.sorted=" + new TreeMap<>(limits));
        System.out.println("map.small=" + limits.get("small"));
        System.out.println("map.missing=" + limits.get("missing"));
        System.out.println("map.sameValues.size="
                + Map.of("one", 1, "single", 1).size());
        rejects("map.put", UnsupportedOperationException.class,
                () -> limits.put("small", 9));
        rejects("map.keySet.remove", UnsupportedOperationException.class,
                () -> limits.keySet().remove("small"));
        Map.Entry<String, Integer> fromMap =
                limits.entrySet().iterator().next();
        rejects("map.entry.setValue", UnsupportedOperationException.class,
                () -> fromMap.setValue(9));

        Map<String, Integer> many = Map.ofEntries(
                Map.entry("k01", 1),
                Map.entry("k02", 2),
                Map.entry("k03", 3),
                Map.entry("k04", 4),
                Map.entry("k05", 5),
                Map.entry("k06", 6),
                Map.entry("k07", 7),
                Map.entry("k08", 8),
                Map.entry("k09", 9),
                Map.entry("k10", 10),
                Map.entry("k11", 11));
        System.out.println("ofEntries.size=" + many.size());
        System.out.println("ofEntries.k11=" + many.get("k11"));

        Map.Entry<String, Integer> pair = Map.entry("limit", 3);
        rejects("entry.setValue", UnsupportedOperationException.class,
                () -> pair.setValue(9));
        AbstractMap.SimpleEntry<String, Integer> seed =
                new AbstractMap.SimpleEntry<>("limit", 3);
        Map<String, Integer> captured = Map.ofEntries(seed);
        seed.setValue(9);
        System.out.println("seed.value=" + seed.getValue());
        System.out.println("ofEntries.captured=" + captured.get("limit"));

        rejects("list.null", NullPointerException.class,
                () -> List.of("ok", (String) null));
        rejects("set.null", NullPointerException.class,
                () -> Set.of("ok", (String) null));
        rejects("map.nullKey", NullPointerException.class,
                () -> Map.of((String) null, 1));
        rejects("map.nullValue", NullPointerException.class,
                () -> Map.of("x", (Integer) null));
        rejects("entry.nullValue", NullPointerException.class,
                () -> Map.entry("x", (Integer) null));
        rejects("ofEntries.nullEntry", NullPointerException.class,
                () -> Map.<String, Integer>ofEntries(
                        (Map.Entry<String, Integer>) null));
        rejects("ofEntries.nullKey", NullPointerException.class,
                () -> Map.ofEntries(
                        new AbstractMap.SimpleEntry<String, Integer>(null, 1)));
        rejects("set.duplicate", IllegalArgumentException.class,
                () -> Set.of("red", new String("red")));
        rejects("map.duplicateKey", IllegalArgumentException.class,
                () -> Map.of("x", 1, new String("x"), 1));
        rejects("ofEntries.duplicateKey", IllegalArgumentException.class,
                () -> Map.ofEntries(Map.entry("x", 1), Map.entry("x", 2)));

        String[] codes = {"a", "b"};
        List<String> expanded = List.of(codes);
        Set<String> expandedSet = Set.of(codes);
        List<String[]> oneArray = List.<String[]>of(codes);
        codes[0] = "changed";
        System.out.println("array.expandedList=" + expanded);
        System.out.println("array.expandedSet.sorted="
                + new TreeSet<>(expandedSet));
        System.out.println("array.singleElement.size=" + oneArray.size());
        System.out.println("array.singleElement.value="
                + Arrays.toString(oneArray.get(0)));
        List<int[]> primitiveArray = List.of(new int[]{3, 4});
        System.out.println("primitive.size=" + primitiveArray.size());
        System.out.println("primitive.first.length="
                + primitiveArray.get(0).length);

        System.out.println("list.eleven.size="
                + List.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11).size());
        System.out.println("set.eleven.size="
                + Set.of(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11).size());

        List<String> steps = new ArrayList<>(List.of("draft"));
        Map<String, List<String>> nested = Map.of("steps", steps);
        steps.add("published");
        System.out.println("nested.value=" + nested.get("steps"));
        rejects("nested.map.put", UnsupportedOperationException.class,
                () -> nested.put("steps", List.of("other")));

        List<String> editable = new ArrayList<>(levels);
        editable.add("medium");
        System.out.println("editable=" + editable);
        System.out.println("original=" + levels);
        System.out.println("list.valueEquality="
                + levels.equals(List.of("low", "high", "low")));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 CollectionFactoriesDemo.java
java CollectionFactoriesDemo
~~~

Cần JDK 17 trở lên để biên dịch với lệnh này. `--release 17` giới hạn cú pháp và API ở mức 17. Mã đã được biên dịch theo lệnh ấy và chạy trên OpenJDK 24.0.2, thoát thành công với stdout chính xác sau:

~~~text
empty.sizes=0/0/0/0
list=[low, high, low]
list.index1=high
list.add=UnsupportedOperationException
list.set=UnsupportedOperationException
set.sorted=[blue, green, red]
set.containsGreen=true
set.add=UnsupportedOperationException
set.hashCollision.size=2
map.sorted={large=4, small=2}
map.small=2
map.missing=null
map.sameValues.size=2
map.put=UnsupportedOperationException
map.keySet.remove=UnsupportedOperationException
map.entry.setValue=UnsupportedOperationException
ofEntries.size=11
ofEntries.k11=11
entry.setValue=UnsupportedOperationException
seed.value=9
ofEntries.captured=3
list.null=NullPointerException
set.null=NullPointerException
map.nullKey=NullPointerException
map.nullValue=NullPointerException
entry.nullValue=NullPointerException
ofEntries.nullEntry=NullPointerException
ofEntries.nullKey=NullPointerException
set.duplicate=IllegalArgumentException
map.duplicateKey=IllegalArgumentException
ofEntries.duplicateKey=IllegalArgumentException
array.expandedList=[a, b]
array.expandedSet.sorted=[a, b]
array.singleElement.size=1
array.singleElement.value=[changed, b]
primitive.size=1
primitive.first.length=2
list.eleven.size=11
set.eleven.size=11
nested.value=[draft, published]
nested.map.put=UnsupportedOperationException
editable=[low, high, low, medium]
original=[low, high, low]
list.valueEquality=true
~~~

### Những dòng nào chứng minh điều gì?

**`empty.sizes`** xác nhận cả bốn factory dùng được cho dữ liệu rỗng. Không cần tạo rồi làm rỗng một vật chứa sửa được để có kết quả rỗng.

**Nhóm `list`** xác nhận list giữ thứ tự và phần tử lặp, có truy cập theo chỉ số nhưng không cho thêm hoặc thay phần tử.

**Nhóm `set`** dùng biểu diễn sắp xếp riêng để stdout ổn định. `set.hashCollision.size=2` cho thấy đụng mã băm không tự biến hai chuỗi khác nhau thành phần tử trùng.

**Nhóm `map`** xác nhận ánh xạ, giá trị lặp hợp lệ và việc khóa vắng trả `null`. Cả `put`, xóa qua `keySet` và `setValue` trên entry của map đều không mở một đường sửa kết quả.

**Nhóm `ofEntries`** tạo 11 ánh xạ. Giá trị cuối được truy vấn bằng khóa nên không phụ thuộc khóa ấy nằm ở đâu trong lần duyệt.

**`seed.value` và `ofEntries.captured`** tách việc sửa entry nguồn khỏi map đã tạo. Dữ liệu ở đây là `String` và `Integer`; không có đối tượng giá trị sửa được lồng bên trong làm kết quả bị nhập nhằng.

**Các dòng ngoại lệ** kiểm tra từng vi phạm riêng. Hai chuỗi khác tham chiếu nhưng bằng nhau vẫn tạo lỗi trùng. Khóa trùng bị từ chối cả khi giá trị giống nhau và khi giá trị khác nhau.

**Nhóm `array`** xác nhận hai cách hiểu khác nhau của mảng: lấy các chuỗi thành nhiều phần tử, hoặc giữ chính mảng làm một phần tử. Chỉ trường hợp sau tiếp tục quan sát phép gán vào mảng sau tạo.

**Hai dòng `eleven`** ngăn nhầm giới hạn của `Map.of` sang `List.of` hoặc `Set.of`. Cả hai collection đều tạo được 11 phần tử.

**Nhóm `nested`** xác nhận map không sửa được vẫn có thể chứa list sửa được. Sửa list nguồn thể hiện qua cùng đối tượng giá trị; `put` trên map vẫn bị chặn.

**Các dòng cuối** cho thấy khi cần chỉnh sửa, tạo `ArrayList` mới sẽ cho một bản làm việc riêng ở tầng list. `equals` kiểm tra bình đẳng giá trị của hai list; chương trình không dự đoán hai factory có trả cùng đối tượng hay không.

## 10. “Không sửa được” có những giới hạn nào?

### Không làm bất biến sâu các đối tượng bên trong

~~~java
List<StringBuilder> notes =
        List.of(new StringBuilder("draft"));

notes.get(0).append("-edited");
~~~

Đây là mã minh họa hợp lệ. List vẫn giữ cùng một phần tử ở cùng vị trí, còn phần tử `StringBuilder` đổi trạng thái.

Với map, `map.get(key).add(...)` có thể sửa một list giá trị dù `map.put(...)` bị chặn. Với set hay khóa map, sửa dữ liệu tham gia `equals`/`hashCode` còn có thể phá giả định tra cứu.

Nếu mục tiêu là dữ liệu cấu hình ổn định, dùng kiểu lá bất biến hoặc chuyển dữ liệu sửa được sang biểu diễn đã chốt trước khi đưa vào factory. Các phương thức tạo không tự duyệt mọi tầng để sao chép đối tượng.

Tài liệu về collection không sửa được phân biệt quyền sửa vật chứa với trạng thái các phần tử và với view trên nguồn. [Định nghĩa trong Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

### Không bảo đảm một lớp triển khai hoặc một định danh đối tượng

Không ép kiểu kết quả `List.of` sang `ArrayList`, không kiểm tra tên lớp nội bộ và không dùng nó làm điều kiện nghiệp vụ.

Các kết quả này có ngữ nghĩa dựa trên giá trị (value-based). Hãy dùng `equals` để so nội dung theo hợp đồng của list/set/map. Không dựa vào `==`, `System.identityHashCode` hay việc factory “luôn trả đối tượng mới”.

Cũng không dùng kết quả factory làm đối tượng khóa đồng bộ. Nếu cần một khóa, tạo đối tượng khóa riêng có quyền sở hữu rõ ràng. Bảo đảm của dữ liệu không phải một cơ chế cấp phát khóa cho chương trình.

### Không biến khởi tạo dữ liệu thành một giao dịch đồng thời

Nếu các đối số là tham chiếu tới đối tượng đang được luồng khác sửa, factory vẫn chỉ nhận những tham chiếu ấy. Nếu dữ liệu được thu thập qua nhiều lần đọc, những lần đọc đó không tự trở thành một bản chụp nguyên tử chỉ vì bước cuối gọi `ofEntries`.

Dùng dữ liệu đã ổn định hoặc một giao thức đọc phù hợp với nguồn. Phần trọng tâm của các factory là tạo cấu trúc với hợp đồng rõ, không cung cấp cơ chế điều phối các luồng.

### Không làm dữ liệu trở thành hằng số biên dịch

Một trường `static final List<String>` có thể giữ một list do factory tạo, nhưng đối tượng list vẫn được khởi tạo khi chạy. Đây không phải một “collection literal” mới trong cú pháp ngôn ngữ và cũng không phải hằng số chuỗi/số được trình biên dịch xử lý như constant expression.

`final` chỉ ngăn gán lại biến sau khởi tạo. Quyền sửa vật chứa đến từ factory; khả năng bất biến sâu còn phụ thuộc dữ liệu bên trong.

## 11. Các lựa chọn thực tế và lỗi chuyển đổi thường gặp

### Tạo dữ liệu khai báo đã biết

Các factory phù hợp cho dữ liệu như danh sách chế độ, tập mã được hỗ trợ, bảng ánh xạ hằng và dữ liệu đầu vào cố định của thí nghiệm. Chúng thể hiện ngay ý định không sửa vật chứa và phát hiện một số sai sót ngay lúc xây dựng. [Hướng dẫn sử dụng factory của Oracle](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html).

Ví dụ một tập mã hợp lệ nên từ chối việc khai báo nhầm hai lần cùng mã; một danh sách bước xử lý có thể cần giữ phần tử lặp. Hợp đồng dữ liệu quyết định nên dùng set hay list.

### Cần cập nhật sau đó

~~~java
List<String> work = new ArrayList<>(List.of("draft", "review"));
work.add("publish");
~~~

Bản `ArrayList` hỗ trợ chỉnh sửa. Với map, có thể xây dựng một map sửa được từ dữ liệu gốc khi yêu cầu cho phép cập nhật.

Đừng thay các đoạn đang dùng `ArrayList`/`HashMap` bằng `of` chỉ vì cú pháp ngắn hơn mà bỏ qua các lần cập nhật phía sau. Các lần gọi `add`, `sort`, `removeIf`, `put`, `compute` hoặc cập nhật qua view đều cần được đánh giá theo hợp đồng mới.

Nếu muốn dữ liệu thay đổi theo phiên bản mà không sửa bản cũ, hãy tạo giá trị mới và thay tham chiếu sở hữu theo cách phù hợp. Không bắt `UnsupportedOperationException` rồi âm thầm coi thao tác cập nhật đã thành công.

### Cần thứ tự cho set hoặc map

Nếu dữ liệu phải hiển thị theo thứ tự khai báo, đừng khởi đầu bằng `Map.of` rồi hi vọng `new LinkedHashMap<>(thatMap)` khôi phục thứ tự các đối số. Bản sao chỉ có thể giữ thứ tự mà nó quan sát từ map đầu vào, không biết thứ tự các đối số trong mã nguồn.

Cách giữ thứ tự chèn phải được xây dựng từ đầu bằng các lần chèn có thứ tự vào một `LinkedHashMap`, rồi áp dụng quyền đọc phù hợp nếu cần. [Hợp đồng thứ tự của LinkedHashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Nếu yêu cầu là thứ tự khóa, sắp xếp theo khóa một cách rõ ràng. Nếu yêu cầu là một chuỗi bước, dùng list. Ba yêu cầu “có cùng ánh xạ”, “giữ thứ tự chèn” và “sắp xếp theo khóa” không thay thế nhau.

### Cần chuyển dữ liệu đã có

`List.of(existingList)` giữ list ấy làm một phần tử. `Set.of(existingSet)` cũng không tự chuyển thành tập các thành viên của set đầu vào. Họ `copyOf` dành cho một nhu cầu khác: lấy dữ liệu từ collection/map đã tồn tại để tạo kết quả không sửa được.

Đừng suy ra mọi ràng buộc của `copyOf` từ `of`. Chẳng hạn, một API chuyển đổi tập hợp có thể có cách xử lý phần tử trùng khác với một factory khai báo set từ nhiều đối số. Khi chuyển đổi dữ liệu, đọc đúng hợp đồng phương thức được gọi.

### Cần hiểu lỗi ngay khi chương trình khởi tạo

Một bảng `static final` có khóa trùng hoặc `null` có thể làm việc khởi tạo lớp thất bại trước khi phần xử lý nghiệp vụ chạy. Khi đó cần đọc nguyên nhân bên trong lỗi khởi tạo để tìm đúng factory và cặp dữ liệu lỗi.

Đừng chỉ nhìn một lỗi bên ngoài rồi kết luận JVM hoặc thư viện bị hỏng. Một bảng tra cứu được kiểm tra ở bước tạo chính là nơi nên phát hiện dữ liệu khai báo không hợp lệ.

## 12. Thực hành có đáp án

### Bài 1 — Giữ một lần lặp hay báo lỗi?

Xét hai lời gọi:

~~~java
List<String> attempts = List.of("read", "retry", "retry");
Set<String> actions = Set.of("read", "retry", "retry");
~~~

**Câu hỏi:** Lời gọi nào thành công? Nếu mục tiêu là mô tả lần lượt những gì đã xảy ra, chọn cấu trúc nào?

**Đáp án:** List thành công và có 3 phần tử theo thứ tự. Set ném `IllegalArgumentException` vì `"retry"` bị khai báo trùng. Nhật ký diễn biến cần giữ thứ tự và số lần xuất hiện nên phù hợp với list; dùng set sẽ làm mất ý nghĩa ngay cả khi một quy trình khác cho phép tự loại trùng.

### Bài 2 — Có cùng giá trị không có nghĩa là trùng khóa

~~~java
Map<String, Integer> a = Map.of("small", 1, "tiny", 1);
Map<String, Integer> b = Map.of("small", 1, "small", 1);
~~~

**Câu hỏi:** Map nào hợp lệ? Có phải map thứ hai chọn một trong hai cặp không?

**Đáp án:** `a` hợp lệ với 2 ánh xạ. `b` không được tạo mà ném `IllegalArgumentException`. `Map.of` kiểm tra trùng khóa; nó không dùng quy tắc “giá trị giống nhau thì bỏ qua cặp lặp” và không chọn một cặp làm kết quả.

### Bài 3 — Có 11 ánh xạ thì viết thế nào?

Một bảng cần ánh xạ từ `"A01"` đến `"A11"` sang số tương ứng.

**Câu hỏi:** Có thể gọi `Map.of` với 11 cặp không? Dùng factory nào trong phạm vi bài để khai báo đủ?

**Đáp án:** `Map.of` không có overload nhận 11 cặp; đây là vấn đề khớp phương thức khi biên dịch, không phải lỗi kích thước lúc chạy. Dùng `Map.ofEntries` và 11 lời gọi `Map.entry`. Không chia thành hai map rồi tưởng rằng chúng tự được nối. `List.of` và `Set.of` không có cùng giới hạn 10 vì có dạng varargs phần tử.

### Bài 4 — Mảng được đọc thành phần tử hay giữ nguyên?

~~~java
String[] values = {"x", "y"};
List<String> a = List.of(values);
List<String[]> b = List.<String[]>of(values);
values[0] = "X";
~~~

**Câu hỏi:** Kích thước và dữ liệu nhìn thấy của mỗi list là gì?

**Đáp án:** `a` có kích thước 2, vẫn chứa `"x"` và `"y"`. `b` có kích thước 1; phần tử ấy là cùng mảng, nên `b.get(0)[0]` là `"X"`. Đừng in thẳng mảng rồi dự đoán chuỗi mặc định; dùng `Arrays.toString` nếu cần hiển thị các ô.

### Bài 5 — Mảng số nguyên có hai số

~~~java
var values = List.of(new int[]{8, 9});
~~~

**Câu hỏi:** Có phải đây là `List<Integer>` kích thước 2 không? Nếu muốn hai phần tử số nguyên wrapper thì viết thế nào?

**Đáp án:** Không. Đó là list có một phần tử `int[]`. Dùng `List.of(8, 9)` để có hai phần tử `Integer`. Đưa một mảng nguyên thủy làm đối số không yêu cầu Java tự bung các ô rồi boxing từng ô.

### Bài 6 — Sửa entry nguồn có cập nhật map không?

~~~java
AbstractMap.SimpleEntry<String, Integer> pair =
        new AbstractMap.SimpleEntry<>("count", 5);

Map<String, Integer> counts = Map.ofEntries(pair);
pair.setValue(6);
~~~

**Câu hỏi:** `counts.get("count")` bằng bao nhiêu? Nếu `pair` được tạo bằng `Map.entry` thì `setValue` làm gì?

**Đáp án:** Map vẫn trả 5, vì nó lấy khóa/giá trị từ entry lúc tạo và không giữ entry đó làm chỗ lưu ánh xạ. Nếu dùng `Map.entry`, `setValue` bị từ chối bằng `UnsupportedOperationException`. Trong cả hai trường hợp, không dùng entry đầu vào làm giao diện cập nhật map kết quả.

### Bài 7 — Có thể viết một stdout cố định thế này không?

Một kiểm thử in trực tiếp `Set.of("c", "a", "b")` rồi khẳng định chuỗi phải là `[c, a, b]`. Kiểm thử khác in trực tiếp `Map.of("z", 1, "a", 2)` rồi khẳng định khóa `z` phải đứng đầu.

**Câu hỏi:** Hai kiểm thử dựa vào hợp đồng nào bị thiếu? Sửa cách kiểm tra ra sao?

**Đáp án:** Các factory set/map không bảo đảm thứ tự duyệt ấy. Kiểm tra tập thành viên hoặc ánh xạ bằng `equals`/`contains`/`get` và kích thước. Nếu thực sự cần chuỗi có thứ tự, sắp xếp rõ trước khi in; dữ liệu chuỗi có thể dùng bản `TreeSet`/`TreeMap` như chương trình trong bài. Nếu thứ tự chèn là yêu cầu sản phẩm, chọn cấu trúc giữ thứ tự ngay từ lúc xây dựng.

### Bài 8 — Vì sao map “chỉ đọc” vẫn đổi dữ liệu nhìn thấy?

~~~java
List<String> modes = new ArrayList<>(List.of("fast"));
Map<String, List<String>> config = Map.of("modes", modes);
modes.add("safe");
~~~

**Câu hỏi:** `config.get("modes")` chứa gì? Lời gọi `config.put("modes", List.of("other"))` có được hỗ trợ không? Nếu cần giá trị cấu hình ổn định thì thay điểm nào?

**Đáp án:** Giá trị list biểu diễn `[fast, safe]` vì list ấy được chia sẻ. `put` trên map bị từ chối. Nếu mô hình chỉ chứa các chuỗi, chốt list giá trị bằng `List.copyOf(modes)` **tại thời điểm cần lưu** rồi đưa vào map không sửa được; nếu đã biết sẵn các chế độ, có thể dùng `Map.of("modes", List.of("fast"))`. Khi phần tử còn chứa đối tượng sửa được, phải bảo vệ cả tầng đó, không chỉ bọc map ngoài.

Một lời gọi factory đúng cần thống nhất ba điều: hình dạng dữ liệu là dãy, tập hay ánh xạ; các đối số thỏa chính sách về `null` và trùng; người dùng kết quả hiểu rõ quyền sửa cùng bảo đảm về thứ tự. Cú pháp ngắn chỉ hữu ích khi ba điều ấy đã rõ.
