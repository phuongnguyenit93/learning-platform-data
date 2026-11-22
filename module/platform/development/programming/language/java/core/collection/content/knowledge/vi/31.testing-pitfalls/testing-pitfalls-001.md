# Kiểm thử collection rỗng, một phần tử, phần tử trùng và null

## 1. Kiểm thử điều gì khi một phương thức nhận collection?

Một phương thức có thể chạy đúng với `["A", "B", "C"]` nhưng vẫn lỗi khi nhận danh sách rỗng, chỉ một phần tử, giá trị lặp lại hoặc phần tử `null`. Những trường hợp này không chỉ là dữ liệu “ít gặp”. Chúng kiểm tra các giả định mà mã thường vô tình dựa vào:

- Luôn có phần tử đầu tiên hoặc cuối cùng.
- Vòng lặp luôn chạy ít nhất một lần.
- Hai giá trị bằng nhau luôn là cùng một đối tượng.
- Mọi phần tử đều khác `null`.
- Kết quả có thể bị sắp xếp lại mà không ảnh hưởng yêu cầu.
- Hàm được phép sửa trực tiếp collection đầu vào.

Một ca kiểm thử có giá trị cần xác định **đầu vào, hành động và kết quả mong đợi theo hợp đồng**. Chỉ chạy mã rồi thấy “không có exception” chưa đủ chứng minh rằng phần tử, thứ tự, số lần xuất hiện và tác dụng phụ đều đúng.

Bài này đi từ bốn nhóm dữ liệu biên đến một chương trình Java có thể chạy độc lập, sau đó chuyển cùng các ý tưởng sang kiểm thử JUnit 5.

## 2. Viết hợp đồng trước khi viết kết quả mong đợi

### 2.1. Không có một đáp án chung cho mọi collection

Xét đầu vào `["A", "A", null]`. Một hàm có thể:

- Giữ nguyên cả ba phần tử.
- Bỏ phần tử `null`, nhưng giữ hai lần `"A"`.
- Bỏ `null` và chỉ giữ lần xuất hiện đầu của `"A"`.
- Từ chối đầu vào chứa `null` bằng một exception đã quy định.

Các lựa chọn này đều có thể hợp lệ trong những bài toán khác nhau. Bài kiểm thử không được tự quyết định chính sách thay cho hợp đồng của hàm.

Trước khi lập dữ liệu, hãy trả lời:

| Khía cạnh | Câu hỏi cần làm rõ |
| --- | --- |
| Collection đầu vào | Có được truyền `null` không, hay chỉ được truyền collection không null? |
| Rỗng | Trả kết quả rỗng, giá trị mặc định hay báo lỗi nghiệp vụ? |
| Phần tử null | Giữ lại, bỏ qua, chuyển thành giá trị khác hay từ chối? |
| Phần tử trùng | Giữ đủ số lần xuất hiện, loại trùng hay cộng dồn? |
| Thứ tự | Giữ thứ tự đầu vào, sắp xếp hay không có bảo đảm? |
| Tác dụng phụ | Có được sửa nguồn không? Kết quả có dùng chung cấu trúc với nguồn không? |
| Khả năng sửa đổi | Kết quả có cho phép thêm/xóa hay phải không thể sửa đổi? |

Không phải hợp đồng nào cũng cần mọi dòng, nhưng những dòng liên quan phải rõ trước khi viết assertion.

### 2.2. Hợp đồng mẫu dùng trong bài

Ta sẽ kiểm thử hàm:

```text
distinctNonNull(Collection<String> source) -> List<String>
```

Hàm mẫu có hợp đồng cụ thể:

1. `source == null` bị từ chối bằng `NullPointerException`.
2. Collection rỗng tạo ra danh sách rỗng.
3. Phần tử `null` bị bỏ qua.
4. Giá trị trùng được xác định theo `String.equals()` và chỉ giữ một lần.
5. Kết quả giữ thứ tự gặp lần đầu khi duyệt nguồn.
6. Không sửa collection nguồn.
7. Kết quả là một danh sách mới có thể thêm/xóa phần tử; thay đổi cấu trúc nguồn và kết quả không lan sang nhau.
8. Không cắt khoảng trắng và không đổi hoa/thường. `"A"`, `"a"`, `""` và `" "` là các giá trị khác nhau.

Đây là chính sách của ví dụ, không phải quy tắc bắt buộc cho mọi hàm xử lý collection. Nếu nguồn là `HashSet` không bảo đảm thứ tự duyệt, hàm cũng không thể tạo ra bảo đảm “thứ tự chèn ban đầu” mà nguồn không cung cấp. Các ca kiểm tra thứ tự trong bài dùng nguồn `List` có thứ tự rõ ràng.

## 3. Nhóm rỗng: không có phần tử vẫn là một trạng thái hợp lệ

### 3.1. Phân biệt collection rỗng với collection bằng null

```text
[]      : có đối tượng collection, kích thước bằng 0
null    : không có tham chiếu tới đối tượng collection
[null]  : có collection, kích thước bằng 1, phần tử duy nhất là null
```

Ba đầu vào này kiểm tra ba điều khác nhau. Không gộp chúng thành một ca mang tên “không có dữ liệu” nếu hợp đồng phân biệt chúng.

Với hàm mẫu:

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| `[]` | `[]` |
| `null` | Ném `NullPointerException` |
| `[null]` | `[]` vì chính sách bỏ qua phần tử null |

### 3.2. Những lỗi mà ca rỗng thường phát hiện

- Gọi `get(0)` trước khi kiểm tra kích thước.
- Khởi tạo kết quả từ phần tử đầu, nhưng không có nhánh xử lý rỗng.
- Trả `null` thay vì collection rỗng trong khi hợp đồng yêu cầu collection.
- Tính trung bình bằng cách chia cho kích thước bằng `0`.
- Trả danh sách rỗng không thể sửa đổi ở nhánh rỗng, trong khi nhánh có dữ liệu trả danh sách có thể sửa đổi và hợp đồng yêu cầu tính nhất quán.

Đối với hàm mẫu, kiểm tra `result.isEmpty()` là chưa đủ cho toàn bộ hợp đồng. Ta còn cần biết `result` không null, có thể thêm phần tử và việc thêm không thay đổi nguồn.

Không nên gọi mọi thao tác phá hủy lên mọi collection rỗng rồi giả định đều thành công. Khả năng sửa đổi phụ thuộc loại collection và hợp đồng riêng của nó.

## 4. Nhóm một phần tử: kiểm tra biên vòng lặp và nhánh khởi tạo

Dữ liệu chỉ một phần tử giúp tìm các lỗi như:

- Vòng lặp dùng `i < size - 1` nên bỏ qua phần tử cuối.
- Bắt đầu duyệt ở chỉ số `1` nên không xử lý phần tử nào.
- Mã luôn truy cập phần tử kế tiếp dù không tồn tại.
- Nhánh “không có gì để loại trùng” trả trực tiếp nguồn, làm nguồn và kết quả dùng chung cấu trúc.

Với hợp đồng mẫu, `List.of("A")` phải tạo kết quả `["A"]`. Tuy vậy, chỉ so sánh nội dung chưa phát hiện việc hàm trả lại nguyên danh sách nguồn.

Nếu hợp đồng yêu cầu kết quả mới, hãy kiểm tra hành vi sau khi thay đổi cấu trúc:

1. Gọi hàm với nguồn một phần tử.
2. Thêm phần tử vào kết quả.
3. Xác nhận nguồn vẫn chỉ có phần tử ban đầu.

Kiểm tra tham chiếu khác nhau có thể bổ sung, nhưng hành vi sửa đổi độc lập mới thể hiện rõ mục đích của yêu cầu. Không kiểm tra danh tính đối tượng khi hợp đồng chỉ hứa giá trị tương đương.

## 5. Nhóm trùng: số lượng, vị trí và khái niệm bằng nhau

### 5.1. Dùng cả phần tử trùng liền nhau và cách nhau

Chỉ thử `["A", "A"]` có thể bỏ sót thuật toán chỉ loại các giá trị trùng kề nhau. Hãy thêm trường hợp như:

```text
Nguồn:   ["B", "A", "B", "C", "A"]
Kết quả: ["B", "A", "C"]
```

Trường hợp này cùng lúc kiểm tra:

- Loại trùng dù hai lần xuất hiện không đứng cạnh nhau.
- Không bỏ nhầm giá trị khác.
- Giữ thứ tự lần xuất hiện đầu, thay vì sắp xếp thành `["A", "B", "C"]`.

Nếu hợp đồng yêu cầu giữ mọi lần xuất hiện, kỳ vọng phải khác. Ví dụ một hàm sao chép danh sách phải giữ `["A", "A"]`, không được tự chuyển thành tập hợp.

### 5.2. Trùng về giá trị không nhất thiết trùng tham chiếu

Một kiểm thử chỉ dùng chuỗi literal có thể vô tình không phát hiện mã dùng `==` để so sánh chuỗi. Tạo hai đối tượng riêng nhưng bằng nhau về giá trị:

```java
String first = new String("A");
String second = new String("A");
```

Đây là dữ liệu minh họa phục vụ kiểm thử sự khác biệt giữa tham chiếu và giá trị, không phải cách khởi tạo chuỗi cần dùng thường xuyên trong mã ứng dụng.

Với hợp đồng mẫu, cả hai chỉ tạo một giá trị `"A"` trong kết quả. Với lớp tự định nghĩa, cần kiểm tra `equals()` và `hashCode()` phù hợp nếu dùng collection dựa trên băm. Nếu miền dữ liệu dùng quy tắc khác, chẳng hạn so sánh không phân biệt hoa/thường, hãy đưa quy tắc đó vào hợp đồng và dữ liệu kiểm thử.

### 5.3. Không có quy tắc trùng duy nhất cho List, Set và Map

| Cấu trúc | “Trùng” cần kiểm tra theo điều gì? |
| --- | --- |
| `List` thông thường | Có thể giữ nhiều phần tử bằng nhau; thứ tự và số lần xuất hiện đều quan trọng |
| `HashSet` | Phần tử bằng nhau không tạo thêm phần tử; cần hợp đồng `equals/hashCode` đúng |
| `Map` thông thường | Khóa không trùng; hai khóa khác nhau vẫn có thể ánh xạ tới cùng một giá trị |
| `TreeSet`/`TreeMap` | Việc xác định cùng vị trí khóa/phần tử dựa trên phép so sánh thứ tự; cần kiểm tra quy tắc so sánh của miền dữ liệu; xem [tài liệu TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html) |

Không dùng `toString()` để biến mọi collection thành một chuỗi rồi so sánh. Điều đó dễ gắn kiểm thử với cách hiển thị hoặc thứ tự không được bảo đảm, thay vì ngữ nghĩa cần kiểm tra.

## 6. Nhóm null: kiểm tra đúng tầng và đúng API

### 6.1. Chọn cách tạo dữ liệu cho phép chứa null

Đoạn sau không tạo được một danh sách chứa `null`:

```java
List<String> input = List.of("A", null, "B");
```

`List.of` từ chối phần tử `null`, nên exception xuất hiện ngay khi chuẩn bị đầu vào, trước khi hàm cần kiểm thử được gọi. `List.of` vẫn cho phép phần tử trùng; quy tắc trùng và quy tắc null là hai chuyện riêng. [Tài liệu List của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

Để tạo nguồn chứa null cho ví dụ, có thể dùng:

```java
List<String> input = new ArrayList<>(
        Arrays.asList("A", null, "B", null));
```

Đoạn minh họa cần import `java.util.List`, `java.util.ArrayList` và `java.util.Arrays`. `Arrays.asList` cho phép phần tử null nhưng có kích thước cố định; bọc bằng `new ArrayList<>(...)` tạo danh sách có thể thêm/xóa. Nếu chỉ đọc dữ liệu, không phải lúc nào cũng cần lớp bọc này.

Với một phần tử null, có thể dùng `Collections.singletonList(null)` có tham số kiểu phù hợp hoặc tạo danh sách rồi `add(null)`. Hãy tránh biểu thức varargs `Arrays.asList(null)` không rõ ý định: null có thể được hiểu là tham chiếu mảng varargs. `Arrays.asList((String) null)` diễn tả rõ một phần tử kiểu String bằng null.

### 6.2. Thử vị trí null có ý nghĩa

Tùy thuật toán, chọn những trường hợp có khả năng kích hoạt nhánh khác nhau:

- Null ở đầu: `[null, "A"]`.
- Null ở giữa: `["A", null, "B"]`.
- Null ở cuối: `["A", null]`.
- Chỉ có null: `[null]` hoặc `[null, null]`.
- Null xen với giá trị trùng: `[null, "A", null, "A", "B"]`.

Không nhất thiết liệt kê mọi hoán vị. Hãy chọn đại diện cho các giả định của mã, rồi bổ sung trường hợp kết hợp khi các yếu tố có thể tương tác.

### 6.3. Chính sách null phụ thuộc triển khai

`HashSet` cho phép phần tử null, nhưng chỉ có tối đa một phần tử null trong tập hợp. `HashMap` cho phép khóa null và giá trị null. Hai đặc tính này không được suy ra cho mọi `Set` hoặc mọi `Map`. [Tài liệu HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [tài liệu HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

`Set.of` từ chối null và từ chối phần tử trùng khi tạo tập hợp. `Map.of` từ chối khóa/giá trị null và khóa trùng khi tạo map. Khác với `HashMap.put`, truyền khóa trùng vào `Map.of` không phải yêu cầu ghi đè giá trị cũ. [Tài liệu Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [tài liệu Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

`ArrayDeque` không cho phép phần tử null. Khi kiểm thử hàng đợi, còn cần tách trạng thái rỗng khỏi chính sách phần tử; chẳng hạn `poll()` trả null khi không có phần tử để lấy. [Tài liệu ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

### 6.4. Map: giá trị null khác với không có khóa

Với một `HashMap` có thể chứa giá trị null:

```text
get("known")   -> null, dù khóa "known" có ánh xạ
get("missing") -> null, vì không có khóa "missing"
```

Nếu yêu cầu cần phân biệt hai trạng thái, kiểm tra cả `containsKey()`. Chỉ `assertNull(map.get(key))` không phân biệt được chúng.

Đối với số dạng wrapper, một phần tử `Integer` null còn có thể gây `NullPointerException` khi được mở hộp để cộng hoặc so sánh bằng toán tử số. Kiểm thử cần đi qua thao tác sử dụng phần tử, không chỉ xác nhận collection chứa được null.

## 7. Ma trận kiểm thử cho hàm mẫu

Kết quả mong đợi dưới đây được viết từ hợp đồng ở mục 2, trước khi xem triển khai.

| Ca | Nguồn | Kỳ vọng | Lỗi có thể phát hiện |
| --- | --- | --- | --- |
| Rỗng | `[]` | `[]` | Truy cập phần tử đầu không tồn tại |
| Một phần tử | `["A"]` | `["A"]` | Bỏ phần tử duy nhất |
| Trùng liền nhau | `["A", "A"]` | `["A"]` | Không loại trùng |
| Trùng cách nhau | `["B", "A", "B", "C", "A"]` | `["B", "A", "C"]` | Chỉ loại trùng liền nhau; sai thứ tự |
| Null xen kẽ | `[null, "A", null, "B", "A"]` | `["A", "B"]` | Gọi phương thức trên null; sai chính sách kết hợp |
| Chỉ null | `[null, null]` | `[]` | Giữ null ngoài hợp đồng |
| Hai đối tượng bằng giá trị | Hai `new String("A")` | `["A"]` | Dùng `==` thay `equals()` |
| Không tự chuẩn hóa | `["", " ", "", "a", "A"]` | `["", " ", "a", "A"]` | Tự cắt khoảng trắng hoặc đổi hoa/thường |
| Cả nguồn null | `null` | `NullPointerException` | Nhầm nguồn null với nguồn rỗng |
| Nguồn và kết quả | Sửa cấu trúc từng bên sau khi gọi | Hai bên độc lập | Trả nguyên nguồn hoặc trả một view |

Để dễ chẩn đoán, các ca đầu nên tập trung vào một quy tắc. Sau đó dùng dữ liệu kết hợp để phát hiện lỗi tương tác. Một ca chứa tất cả yếu tố không thay thế tốt cho các ca có mục tiêu rõ ràng.

## 8. Chương trình Java 17+ tự chạy các kiểm tra

Chương trình dưới đây không cần thư viện bên ngoài. Nó dùng hàm kiểm tra ném `AssertionError` khi sai, nên không phụ thuộc việc bật tùy chọn `-ea` của từ khóa `assert` trong Java.

`LinkedHashSet` lưu các giá trị chưa gặp theo thứ tự duyệt đầu tiên; kết quả được chuyển sang một `ArrayList` mới. Việc triển khai ngắn không thay cho các kiểm tra về hợp đồng. [Tài liệu LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

Lưu thành `CollectionBoundaryDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class CollectionBoundaryDemo {
    private static int passed;

    static List<String> distinctNonNull(Collection<String> source) {
        Objects.requireNonNull(source, "source");
        Set<String> unique = new LinkedHashSet<>();
        for (String value : source) {
            if (value != null) {
                unique.add(value);
            }
        }
        return new ArrayList<>(unique);
    }

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static void expectThrows(String label,
                                     Class<? extends Throwable> expected,
                                     Runnable action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (!expected.isInstance(actual)) {
                throw new AssertionError(label + ": wrong exception", actual);
            }
            passed++;
            return;
        }
        throw new AssertionError(label + ": expected " + expected.getSimpleName());
    }

    public static void main(String[] args) {
        checkEquals("empty", List.of(), distinctNonNull(List.of()));
        checkEquals("singleton", List.of("A"), distinctNonNull(List.of("A")));
        checkEquals("adjacent duplicates", List.of("A"),
                distinctNonNull(List.of("A", "A")));
        checkEquals("separated duplicates and order", List.of("B", "A", "C"),
                distinctNonNull(List.of("B", "A", "B", "C", "A")));
        checkEquals("nulls and duplicates", List.of("A", "B"),
                distinctNonNull(Arrays.asList(null, "A", null, "B", "A")));
        checkEquals("only nulls", List.of(),
                distinctNonNull(Arrays.asList((String) null, (String) null)));
        checkEquals("equal values in separate objects", List.of("A"),
                distinctNonNull(List.of(new String("A"), new String("A"))));
        checkEquals("no extra normalization", List.of("", " ", "a", "A"),
                distinctNonNull(List.of("", " ", "", "a", "A")));
        expectThrows("null source", NullPointerException.class,
                () -> distinctNonNull(null));

        List<String> source = new ArrayList<>(Arrays.asList("A", null, "A", "B"));
        List<String> before = new ArrayList<>(source);
        List<String> result = distinctNonNull(source);
        checkEquals("source unchanged by call", before, source);
        checkEquals("result content", List.of("A", "B"), result);
        result.add("C");
        checkEquals("result is mutable", List.of("A", "B", "C"), result);
        checkEquals("result mutation does not change source", before, source);
        source.add("D");
        checkEquals("source mutation does not change result",
                List.of("A", "B", "C"), result);
        List<String> emptyResult = distinctNonNull(List.of());
        emptyResult.add("X");
        checkEquals("empty result is also mutable", List.of("X"), emptyResult);

        expectThrows("List.of rejects null", NullPointerException.class,
                () -> List.of("A", (String) null));
        expectThrows("Set.of rejects duplicates", IllegalArgumentException.class,
                () -> Set.of("A", "A"));
        expectThrows("Map.of rejects duplicate keys", IllegalArgumentException.class,
                () -> Map.of("A", 1, "A", 2));
        expectThrows("ArrayDeque rejects null", NullPointerException.class,
                () -> new ArrayDeque<String>().add(null));

        Set<String> nullableSet = new HashSet<>(
                Arrays.asList("A", "A", null, "B", null));
        checkEquals("HashSet removes duplicates including null", 3, nullableSet.size());
        checkEquals("HashSet contains null", true, nullableSet.contains(null));

        Map<String, String> nullableMap = new HashMap<>();
        nullableMap.put(null, "fallback");
        nullableMap.put("known", null);
        checkEquals("HashMap null key", "fallback", nullableMap.get(null));
        checkEquals("present null value", null, nullableMap.get("known"));
        checkEquals("missing key lookup", null, nullableMap.get("missing"));
        checkEquals("known key exists", true, nullableMap.containsKey("known"));
        checkEquals("missing key does not exist", false,
                nullableMap.containsKey("missing"));

        System.out.println("PASS: " + passed + " checks");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CollectionBoundaryDemo.java
java CollectionBoundaryDemo
```

Stdout khi tất cả kiểm tra đạt:

```text
PASS: 26 checks
```

Nếu một kiểm tra sai, chương trình dừng bằng `AssertionError`, thay vì vẫn in dòng PASS. Những kiểm tra API ở phần sau `main` được tách về ý nghĩa với kiểm tra hàm mẫu: chúng xác nhận cách chuẩn bị dữ liệu và sự khác biệt giữa các collection cụ thể.

Việc bắt `Throwable` ở đây chỉ nằm trong một tiện ích kiểm thử nhỏ để kiểm tra kiểu lỗi được ném; không phải lời khuyên bắt mọi lỗi trong mã nghiệp vụ rồi bỏ qua. Thông báo exception của JVM không được dùng làm điều kiện đạt vì nội dung thông báo có thể khác giữa môi trường.

## 9. Chuyển cùng ma trận sang JUnit 5

Trong dự án đã có JUnit Jupiter, dùng kiểm thử tham số hóa để giữ một cấu trúc assertion và cung cấp nhiều cặp nguồn/kỳ vọng. `@MethodSource` thuận tiện khi mỗi ca có collection phức tạp hoặc chứa null; kiểm thử ngoại lệ nên nằm trong một phương thức có mục tiêu riêng. [Hướng dẫn JUnit 5 về MethodSource](https://docs.junit.org/5.10.2/user-guide/#writing-tests-parameterized-tests-sources-MethodSource)

Đoạn dưới là lớp kiểm thử minh họa cho môi trường có `junit-jupiter-api`, `junit-jupiter-params` và engine JUnit Jupiter khi chạy. Nó không phải chương trình độc lập chạy bằng lệnh `java` ở mục 8. Đặt cùng package với `CollectionBoundaryDemo` hoặc điều chỉnh khả năng truy cập của hàm trong mã thực tế.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class CollectionBoundaryTest {
    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of(List.of(), List.of()),
                Arguments.of(List.of("A"), List.of("A")),
                Arguments.of(List.of("B", "A", "B", "C"), List.of("B", "A", "C")),
                Arguments.of(Arrays.asList(null, "A", null, "A"), List.of("A")),
                Arguments.of(Arrays.asList((String) null, (String) null), List.of()));
    }

    @ParameterizedTest
    @MethodSource("cases")
    void followsValueContract(List<String> input, List<String> expected) {
        List<String> before = new ArrayList<>(input);
        List<String> actual = CollectionBoundaryDemo.distinctNonNull(input);
        assertEquals(expected, actual);
        assertEquals(before, input);
    }

    @Test
    void rejectsNullCollection() {
        assertThrows(NullPointerException.class,
                () -> CollectionBoundaryDemo.distinctNonNull(null));
    }
}
```

`assertEquals` với hai `List` kiểm tra nội dung theo thứ tự, nên phù hợp với hợp đồng giữ thứ tự. Các ca về khả năng sửa đổi và tính độc lập cấu trúc cần được chuyển thành kiểm thử riêng tương tự phần chương trình đầy đủ, thay vì nghĩ rằng bảng tham số trên đã bao phủ toàn bộ hợp đồng.

Nếu dùng `@NullSource`, cần nhớ nó cung cấp tham số null cho phương thức kiểm thử; nó không tự tạo ra một danh sách có một phần tử null. Hai trường hợp phải có dữ liệu nguồn khác nhau.

## 10. Chọn assertion theo ngữ nghĩa cần bảo vệ

### 10.1. List: nội dung, thứ tự và số lần xuất hiện

Nếu kết quả là danh sách có thứ tự, so sánh trực tiếp với một `List` kỳ vọng. Chỉ kiểm tra `size()` không phát hiện thay nhầm phần tử hoặc đảo thứ tự. Chỉ kiểm tra `contains()` không phát hiện thừa một bản sao hay mất một lần xuất hiện.

Ví dụ `["A", "A", "B"]` và `["A", "B", "B"]` có cùng kích thước và cùng tập giá trị, nhưng không có cùng số lần xuất hiện. Đừng chuyển cả hai sang `Set` rồi kết luận chúng tương đương nếu số lần lặp thuộc hợp đồng.

### 10.2. Set: không dựa vào thứ tự khi không được bảo đảm

Với tập hợp không có bảo đảm thứ tự, so sánh tập phần tử bằng `Set.equals()`. Không đòi `HashSet` in ra đúng một chuỗi theo thứ tự tình cờ thấy trên máy.

Nếu hợp đồng yêu cầu thứ tự duyệt, phải chọn collection có bảo đảm phù hợp và kiểm tra thứ tự duyệt riêng. `Set.equals()` tự nó không kiểm tra thứ tự.

### 10.3. Map: kiểm tra ánh xạ, không chỉ tập giá trị

Hai map có thể có cùng tập giá trị nhưng ghép chúng với khóa khác nhau. So sánh map hoặc kiểm tra từng ánh xạ cần thiết. Khi null được phép, thêm `containsKey()` nếu cần phân biệt thiếu khóa với khóa có giá trị null.

Đối với việc chèn lại cùng khóa, kiểm tra cả giá trị cuối, kích thước và giá trị cũ trả về nếu chúng thuộc hành vi cần bảo vệ. Không nhầm “trùng giá trị” với “trùng khóa”.

### 10.4. Ngoại lệ: khoanh vùng đúng hành động

Một kiểm thử “có NullPointerException” có thể đạt vì lỗi ở giai đoạn chuẩn bị dữ liệu, chứ không phải vì hàm cần kiểm thử đã từ chối nguồn.

Hãy tạo dữ liệu hợp lệ cho mục tiêu kiểm thử trước, rồi bao chính lời gọi cần kiểm tra trong `assertThrows`. Chỉ đặt thao tác tạo dữ liệu bên trong vùng kỳ vọng ngoại lệ khi chính factory đó là đối tượng đang được kiểm thử, như các kiểm tra `List.of` trong chương trình mẫu.

Không bắt exception rồi chỉ in ra thông báo. Nếu lỗi không xuất hiện hoặc sai loại, kiểm thử phải thất bại rõ ràng.

## 11. Những lỗi thiết kế kiểm thử thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ thử danh sách nhiều giá trị khác nhau | Bỏ sót nhánh rỗng, singleton, trùng và null | Lập các nhóm dữ liệu đại diện trước |
| Dùng `List.of` để tạo dữ liệu chứa null | Lỗi trước khi gọi hàm cần kiểm thử | Dùng cách tạo dữ liệu có chính sách null phù hợp |
| Chỉ kiểm tra kích thước | Không phát hiện sai phần tử/thứ tự | Kiểm tra nội dung theo ngữ nghĩa kết quả |
| Dùng `Set` để so mọi kết quả danh sách | Làm mất thông tin số lần xuất hiện và thứ tự | Giữ dạng `List` khi hợp đồng là danh sách |
| Tính expected bằng chính thuật toán đang kiểm thử | Cùng sai mà vẫn đạt | Viết ví dụ expected độc lập từ hợp đồng |
| Dùng chung một collection có thể sửa đổi cho nhiều ca | Ca trước làm thay đổi dữ liệu của ca sau | Tạo nguồn mới cho mỗi ca khi có khả năng bị sửa |
| Chỉ kiểm tra collection chấp nhận null | Bỏ sót lỗi khi sử dụng phần tử null | Chạy cả thao tác xử lý liên quan |
| Ép mọi hàm coi null như rỗng | Che lỗi vi phạm hợp đồng hoặc mất phân biệt nghiệp vụ | Giữ chính sách null đã quy định |
| Yêu cầu một loại triển khai cụ thể ngoài hợp đồng | Kiểm thử vỡ khi thay triển khai tương đương | Kiểm tra hành vi và bảo đảm đã công bố |

Một bản sao đầu vào bằng `new ArrayList<>(source)` đủ ghi lại cấu trúc và các tham chiếu để kiểm tra ví dụ String trong bài. Với phần tử có thể thay đổi, bản sao nông không giúp phát hiện mọi thay đổi bên trong đối tượng; cần chụp trạng thái giá trị cần bảo vệ hoặc dùng dữ liệu bất biến phù hợp.

## 12. Tự kiểm tra và bài tập

### Câu 1: Một hàm trả danh sách rỗng cho đầu vào null có luôn đúng không?

Không. Nó đúng khi hợp đồng quy định null tương đương không có phần tử. Hàm mẫu trong bài yêu cầu từ chối null, nên trả danh sách rỗng sẽ sai dù không có exception.

### Câu 2: Hàm loại trùng trả `["A", "B", "C"]` cho `["B", "A", "B", "C"]` có đạt không?

Không đạt hợp đồng mẫu vì đã đổi thứ tự gặp lần đầu. Nó có thể đạt một hợp đồng khác yêu cầu kết quả được sắp xếp. Assertion phải theo hợp đồng đang kiểm thử.

### Câu 3: `map.get(key) == null` có chứng minh không có khóa không?

Không đối với map cho phép giá trị null. Cần kiểm tra `containsKey(key)` nếu sự khác biệt đó có ý nghĩa.

### Câu 4: Kiểm thử dùng List.of("A", null) rồi thấy NullPointerException đã kiểm tra được hàm xử lý null chưa?

Chưa. Factory đã thất bại trước khi hàm nhận dữ liệu. Hãy tạo nguồn chứa null bằng API phù hợp và khoanh assertion quanh đúng hành động.

### Bài thực hành

1. Thêm ca một phần tử null, null chỉ ở đầu và null chỉ ở cuối cho hàm mẫu; viết kết quả kỳ vọng trước khi chạy.
2. Đổi hợp đồng mẫu thành “giữ cả phần tử null nhưng loại trùng”, rồi xác định chính xác các ca nào phải thay kỳ vọng. Không sửa kỳ vọng chỉ vì nhìn thấy kết quả mới từ chương trình.
3. Viết các ca cho hàm đếm số lần xuất hiện, trong đó `["A", "A", "B"]` phải thể hiện số đếm `A=2`, `B=1`; quyết định chính sách null trước.
4. Tạo một kiểm thử mà đầu vào chỉ một phần tử, sửa kết quả sau khi gọi, rồi xác nhận nguồn độc lập theo hợp đồng.

Bốn nhóm dữ liệu biên là điểm xuất phát để tìm giả định ẩn. Một bộ kiểm thử đáng tin còn bảo vệ nội dung, thứ tự, số lần xuất hiện, chính sách null và tác dụng phụ mà người gọi thực sự được hứa.
