# Xử lý phần tử Set trùng hoặc khóa Map trùng trong Java

## 1. Phân biệt phần tử của Set và khóa của Map

Set là collection chỉ giữ một phần tử trong mỗi nhóm phần tử được xem là bằng nhau theo quy tắc so sánh của Set. Khi thêm một phần tử đã tồn tại, Set không tạo bản sao thứ hai.

Map lưu các cặp khóa và giá trị. Mỗi khóa chỉ ánh xạ tới một giá trị tại một thời điểm. Khi đưa một khóa đã có vào Map, thao tác cập nhật thường thay thế giá trị cũ bằng giá trị mới. Giá trị của nhiều khóa khác nhau vẫn có thể trùng nhau.

Các API tạo collection có quy tắc xử lý trùng khác nhau:

- **Set.of(...)** từ chối phần tử trùng và ném **IllegalArgumentException**.
- **Map.of(...)** và **Map.ofEntries(...)** từ chối khóa trùng và ném **IllegalArgumentException**.
- **Set.add(element)** trả về **false** nếu Set đã chứa phần tử tương đương.
- **Map.put(key, value)** thay giá trị của khóa đã có và trả về giá trị trước đó.
- **Set.copyOf(collection)** loại bỏ trùng theo quy tắc Set; một phần tử đại diện được giữ lại.
- **Collectors.toMap(...)** không có merge function sẽ ném **IllegalStateException** nếu nhiều phần tử tạo ra cùng một khóa.

Vì vậy, cần chọn hành vi phù hợp với mục đích: từ chối dữ liệu trùng, bỏ qua bản trùng, ghi đè giá trị, gộp dữ liệu hoặc nhóm nhiều giá trị dưới cùng một khóa.

## 2. Set.of từ chối phần tử trùng

**Set.of** là factory method có từ Java 9. Phương thức này tạo một Set không thể thay đổi và yêu cầu các phần tử đầu vào không trùng nhau:

~~~java
Set<String> languages = Set.of("Java", "Kotlin");

// Ném IllegalArgumentException vì "Java" xuất hiện hai lần.
Set<String> invalid = Set.of("Java", "Kotlin", "Java");
~~~

Việc kiểm tra trùng dựa trên quan hệ bằng nhau của phần tử. Nếu hai đối tượng được xem là bằng nhau, chúng không thể cùng xuất hiện trong Set được tạo bằng **Set.of**. Ngoài lỗi trùng, factory này cũng từ chối **null** bằng **NullPointerException**.

Khi dữ liệu đầu vào có thể chứa phần tử trùng và mục tiêu là giữ một bản đại diện, hãy dùng một Set có thể thay đổi hoặc **Set.copyOf** sau khi xác định rõ chính sách dữ liệu. Không nên gọi **Set.of** trực tiếp trên dữ liệu chưa được kiểm tra nếu trùng lặp là tình huống có thể xảy ra.

## 3. Set.add báo kết quả khi gặp phần tử đã tồn tại

Với Set có thể thay đổi như **HashSet**, phương thức **add** không ném lỗi chỉ vì phần tử đã có:

~~~java
Set<String> languages = new HashSet<>();

boolean first = languages.add("Java");
boolean second = languages.add("Java");

System.out.println(first);
System.out.println(second);
System.out.println(languages.size());
~~~

Kết quả:

~~~text
true
false
1
~~~

Giá trị trả về cho biết Set có thay đổi hay không:

- **true**: phần tử được thêm mới.
- **false**: Set đã có phần tử tương đương nên không thêm bản sao.

Có thể dùng kết quả này để phát hiện trùng ngay tại nơi nhập dữ liệu:

~~~java
if (!languages.add(input)) {
    System.out.println("Phần tử đã tồn tại");
}
~~~

Cách này hữu ích khi muốn loại trùng mà vẫn tiếp tục xử lý các phần tử còn lại. Nếu cần báo lỗi hoặc từ chối toàn bộ dữ liệu đầu vào khi phát hiện trùng, hãy kiểm tra kết quả **add** và chủ động quyết định cách xử lý.

## 4. Map.of và Map.ofEntries từ chối khóa trùng

Map không thể lưu hai ánh xạ độc lập cho cùng một khóa. Các factory method **Map.of** và **Map.ofEntries** yêu cầu khóa không trùng:

~~~java
Map<String, Integer> versions = Map.of(
    "Java", 17,
    "Kotlin", 2
);

// Ném IllegalArgumentException vì khóa "Java" bị lặp.
Map<String, Integer> invalid = Map.of(
    "Java", 17,
    "Kotlin", 2,
    "Java", 21
);
~~~

Với **Map.ofEntries**, quy tắc tương tự áp dụng cho các entry:

~~~java
Map<String, Integer> versions = Map.ofEntries(
    Map.entry("Java", 17),
    Map.entry("Kotlin", 2)
);

// Ném IllegalArgumentException vì hai entry có cùng khóa.
Map<String, Integer> invalid = Map.ofEntries(
    Map.entry("Java", 17),
    Map.entry("Java", 21)
);
~~~

Các factory này cũng từ chối khóa hoặc giá trị **null**. Khi có khóa trùng, chúng ném **IllegalArgumentException**; khi có khóa hoặc giá trị **null**, chúng ném **NullPointerException**.

Khóa phải duy nhất, nhưng giá trị không cần duy nhất:

~~~java
Map<String, Integer> scores = Map.of(
    "An", 10,
    "Binh", 10
);
~~~

Ví dụ trên hợp lệ vì hai khóa khác nhau có thể cùng ánh xạ tới giá trị 10.

## 5. Map.put thay thế giá trị của khóa đã có

Với Map có thể thay đổi như **HashMap**, **put** cập nhật ánh xạ khi khóa đã tồn tại. Phương thức trả về giá trị trước đó; nếu khóa chưa có, kết quả thường là **null**:

~~~java
Map<String, Integer> versions = new HashMap<>();

Integer previousFirst = versions.put("Java", 17);
Integer previousSecond = versions.put("Java", 21);

System.out.println(previousFirst);
System.out.println(previousSecond);
System.out.println(versions.get("Java"));
~~~

Kết quả:

~~~text
null
17
21
~~~

Lần gọi đầu thêm khóa Java với giá trị 17. Lần gọi thứ hai thay giá trị thành 21 và trả về giá trị cũ là 17. Map vẫn chỉ có một ánh xạ cho khóa Java.

Nếu cần phân biệt rõ khóa chưa tồn tại với khóa tồn tại nhưng đang ánh xạ tới **null** trong Map cho phép null, hãy dùng **containsKey** trước khi cập nhật. Với các Map factory như **Map.of**, giá trị null không được phép nên tình huống này không phát sinh.

## 6. Set.copyOf xử lý phần tử trùng bằng cách giữ một phần tử

**Set.copyOf** có từ Java 10. Phương thức nhận một Collection và tạo Set không thể thay đổi. Nếu collection nguồn có nhiều phần tử bằng nhau, kết quả chỉ giữ một phần tử đại diện trong mỗi nhóm trùng:

~~~java
List<String> source = List.of("Java", "Kotlin", "Java");
Set<String> unique = Set.copyOf(source);

System.out.println(unique.size());
System.out.println(unique.contains("Java"));
~~~

Kết quả:

~~~text
2
true
~~~

Đây là khác biệt quan trọng giữa **Set.of** và **Set.copyOf**:

| API | Khi đầu vào có phần tử trùng |
|---|---|
| **Set.of(...)** | Ném **IllegalArgumentException** |
| **Set.copyOf(collection)** | Giữ một phần tử đại diện, loại phần tử trùng |

Không nên phụ thuộc vào việc chính xác đối tượng nào trong nhóm bằng nhau sẽ được giữ lại. Nếu các đối tượng bằng nhau nhưng mang thêm thông tin phụ khác nhau, hãy xác định chính sách chọn đối tượng trước khi tạo Set.

**Set.copyOf** cũng từ chối phần tử **null**. Nếu collection nguồn có null, phương thức ném **NullPointerException**, không tự lọc null.

## 7. Collectors.toMap và cách giải quyết khóa trùng trong Stream

Khi chuyển một Stream thành Map, nhiều phần tử có thể tạo ra cùng một khóa. Overload hai tham số của **Collectors.toMap** không tự chọn giá trị thắng:

~~~java
List<String> languages = List.of("Java", "Kotlin", "Java");

Map<String, Integer> lengths = languages.stream()
    .collect(Collectors.toMap(
        Function.identity(),
        String::length
    ));
~~~

Đoạn mã trên ném **IllegalStateException** vì hai phần tử Java tạo ra cùng khóa Java. Đây là lỗi tại lúc collect, khác với **IllegalArgumentException** của **Map.of**.

Nếu có chính sách gộp, hãy dùng overload có merge function:

~~~java
Map<String, Integer> counts = languages.stream()
    .collect(Collectors.toMap(
        Function.identity(),
        language -> 1,
        Integer::sum
    ));
~~~

Kết quả Map có Java bằng 2 và Kotlin bằng 1. Merge function nhận giá trị cũ và giá trị mới rồi trả về giá trị cần lưu. Một số chính sách thường dùng:

~~~java
// Giữ giá trị xuất hiện đầu tiên.
(oldValue, newValue) -> oldValue

// Giữ giá trị xuất hiện sau cùng.
(oldValue, newValue) -> newValue

// Gộp bằng phép cộng.
Integer::sum
~~~

Nếu cần kiểm soát kiểu Map được tạo, overload bốn tham số cho phép truyền thêm Map supplier:

~~~java
Map<String, Integer> counts = languages.stream()
    .collect(Collectors.toMap(
        Function.identity(),
        language -> 1,
        Integer::sum,
        LinkedHashMap::new
    ));
~~~

**LinkedHashMap** giữ thứ tự duyệt theo thứ tự chèn. Nếu thứ tự không phải yêu cầu, có thể dùng overload ba tham số đơn giản hơn.

## 8. Khi cần giữ tất cả giá trị có cùng khóa

Nếu các phần tử trùng khóa đều có ý nghĩa và không nên bỏ hoặc ghi đè, hãy nhóm chúng thành một danh sách bằng **Collectors.groupingBy**:

~~~java
List<String> events = List.of("login", "purchase", "login");

Map<String, List<String>> grouped = events.stream()
    .collect(Collectors.groupingBy(Function.identity()));
~~~

Kết quả là Map có một khóa cho mỗi loại sự kiện, còn danh sách giá trị giữ các lần xuất hiện. Đây là cách phù hợp khi cần đếm, tổng hợp hoặc xử lý toàn bộ bản ghi thuộc cùng một nhóm.

Một lựa chọn khác là tự duyệt và dùng **computeIfAbsent** để thêm từng phần tử vào danh sách theo khóa. Cách này hữu ích khi cần thêm logic riêng trong quá trình nhóm.

## 9. Quy tắc xác định hai phần tử hoặc hai khóa là trùng

Cách xác định trùng phụ thuộc vào loại Set hoặc Map:

- **HashSet** và **HashMap** dựa trên **hashCode()** và **equals()**. Hai đối tượng bằng nhau theo **equals** phải có cùng **hashCode**.
- **TreeSet** và **TreeMap** dựa trên thứ tự tự nhiên hoặc Comparator. Nếu phép so sánh trả về 0, cấu trúc xem hai phần tử hoặc khóa là tương đương cho mục đích lưu trữ.
- Các Set và Map factory dùng quy tắc bằng nhau của hợp đồng Set/Map; không nên dựa vào identity của đối tượng để xác định trùng.

Ví dụ, TreeSet không phân biệt hai chuỗi chỉ khác chữ hoa/thường khi dùng comparator không phân biệt hoa thường:

~~~java
Set<String> names = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

System.out.println(names.add("Java"));
System.out.println(names.add("JAVA"));
System.out.println(names.size());
~~~

Kết quả:

~~~text
true
false
1
~~~

Dù hai chuỗi khác nhau theo **String.equals**, comparator trả về 0 nên TreeSet không thêm phần tử thứ hai. TreeMap có hành vi tương tự với khóa: comparator quyết định hai khóa có cùng vị trí khóa hay không.

Với lớp tự định nghĩa dùng trong HashSet hoặc làm khóa HashMap, cần triển khai **equals** và **hashCode** nhất quán. Nếu hai đối tượng bằng nhau nhưng có hash code khác nhau, cấu trúc băm có thể không nhận diện chúng là cùng một phần tử hoặc khóa như mong đợi.

## 10. Ví dụ chạy được

Chương trình sau kiểm tra các hành vi quan trọng: factory từ chối trùng, Set.add bỏ qua bản trùng, Map.put thay giá trị, Set.copyOf gộp phần tử trùng, Stream toMap yêu cầu merge function và TreeSet tuân theo Comparator.

**Tệp DuplicateCollectionsDemo.java:**

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.function.Function;
import java.util.stream.Collectors;

public class DuplicateCollectionsDemo {
    private static void expectIllegalArgument(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected IllegalArgumentException: " + label);
        } catch (IllegalArgumentException expected) {
            System.out.println(label + ": rejected");
        }
    }

    private static void expectIllegalState(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected IllegalStateException: " + label);
        } catch (IllegalStateException expected) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        expectIllegalArgument("Set.of duplicate", () -> Set.of("Java", "Java"));
        expectIllegalArgument("Map.of duplicate key",
                () -> Map.of("Java", 17, "Java", 21));
        expectIllegalArgument("Map.ofEntries duplicate key", () -> Map.ofEntries(
                Map.entry("Java", 17), Map.entry("Java", 21)));

        Set<String> set = new HashSet<>();
        System.out.println("Set.add first: " + set.add("Java"));
        System.out.println("Set.add duplicate: " + set.add("Java"));
        Set<String> copied = Set.copyOf(List.of("Java", "Java"));
        System.out.println("Set.copyOf duplicate count: " + copied.size());

        Map<String, Integer> map = new HashMap<>();
        System.out.println("Map.put first previous: " + map.put("Java", 17));
        System.out.println("Map.put duplicate previous: " + map.put("Java", 21));
        System.out.println("Map.put final value: " + map.get("Java"));

        List<String> languages = List.of("Java", "Kotlin", "Java");
        expectIllegalState("Collectors.toMap duplicate key", () -> languages.stream()
                .collect(Collectors.toMap(Function.identity(), String::length)));
        Map<String, Integer> merged = languages.stream().collect(Collectors.toMap(
                Function.identity(), String::length, Integer::sum));
        System.out.println("toMap merged Java: " + merged.get("Java"));
        System.out.println("toMap merged Kotlin: " + merged.get("Kotlin"));

        Set<String> caseInsensitive = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        System.out.println("TreeSet first: " + caseInsensitive.add("Java"));
        System.out.println("TreeSet case variant: " + caseInsensitive.add("JAVA"));
        System.out.println("TreeSet size: " + caseInsensitive.size());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all DuplicateCollectionsDemo.java
java DuplicateCollectionsDemo
~~~

Kết quả chuẩn:

~~~text
Set.of duplicate: rejected
Map.of duplicate key: rejected
Map.ofEntries duplicate key: rejected
Set.add first: true
Set.add duplicate: false
Set.copyOf duplicate count: 1
Map.put first previous: null
Map.put duplicate previous: 17
Map.put final value: 21
Collectors.toMap duplicate key: rejected
toMap merged Java: 8
toMap merged Kotlin: 6
TreeSet first: true
TreeSet case variant: false
TreeSet size: 1
~~~

## 11. Chọn cách xử lý theo yêu cầu dữ liệu

| Yêu cầu | Cách dùng |
|---|---|
| Dữ liệu trùng là lỗi và cần phát hiện ngay khi tạo | **Set.of**, **Map.of**, **Map.ofEntries** |
| Bỏ qua phần tử Set đã tồn tại | Kiểm tra kết quả **Set.add** |
| Cập nhật giá trị của khóa đã có | **Map.put** |
| Tạo Set không thể thay đổi và chấp nhận đầu vào trùng | **Set.copyOf** |
| Gộp giá trị khi Stream tạo ra khóa trùng | **Collectors.toMap** với merge function |
| Giữ tất cả phần tử có cùng khóa | **Collectors.groupingBy** |
| Xác định trùng theo thứ tự tùy chỉnh | **TreeSet** hoặc **TreeMap** với Comparator phù hợp |

Trước khi chọn API, hãy trả lời ba câu hỏi: dữ liệu trùng có hợp lệ không, nếu hợp lệ thì bản nào được giữ, và nếu nhiều giá trị cùng khóa thì cần ghi đè, gộp hay giữ tất cả? Chính sách rõ ràng giúp tránh mất dữ liệu ngoài ý muốn.

## 12. Ghi nhớ

Set chỉ giữ một phần tử theo quy tắc so sánh của nó; Map chỉ giữ một ánh xạ cho mỗi khóa. **Set.of**, **Map.of** và **Map.ofEntries** từ chối trùng bằng **IllegalArgumentException**. **Set.add** trả về false khi phần tử đã có, còn **Map.put** thay giá trị cũ và trả lại giá trị trước. **Set.copyOf** giữ một đại diện của các phần tử trùng. Khi tạo Map từ Stream, hãy cung cấp merge function nếu muốn giải quyết khóa trùng, hoặc dùng **groupingBy** nếu cần giữ tất cả giá trị trong nhóm.
