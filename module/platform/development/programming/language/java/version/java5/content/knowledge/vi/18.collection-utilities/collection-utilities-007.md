# Collections.frequency để đếm phần tử theo equals

`Collections.frequency(collection, target)` trả về số phần tử trong collection bằng với giá trị cần tìm theo quy tắc `equals`, có xử lý riêng cho `null`.

Đây là một phép **đếm số lần xuất hiện**, không phải phép kiểm tra có/không, không phải tìm chỉ số và cũng không tự sắp xếp hay thay đổi collection.

Ví dụ ngắn:

```java
List<String> words = List.of("java", "spring", "java");
int count = Collections.frequency(words, "java"); // 2
```

Đoạn này giả định đã import `java.util.List` và `java.util.Collections`, nằm trong một phương thức.

## 1. Chữ ký và cách đọc hợp đồng

Chữ ký API:

```java
public static int frequency(Collection<?> c, Object o)
```

Đây là mô tả phương thức thư viện, không phải khai báo hoàn chỉnh để chép nguyên vào một lớp.

| Thành phần | Ý nghĩa |
| --- | --- |
| `c` | Collection được duyệt để đếm |
| `o` | Giá trị mục tiêu cần so với từng phần tử |
| Kết quả `int` | Số lần khớp; bằng 0 nếu không có |

Mỗi phần tử `e` được tính nếu điều kiện theo hợp đồng tương đương `Objects.equals(o, e)`.

Có thể hiểu:

- Nếu `o == null`, đếm các phần tử `e == null`.
- Nếu `o != null`, dùng phép bằng nhau từ giá trị mục tiêu để so với phần tử.
- Mỗi vị trí được duyệt phù hợp làm số đếm tăng một lần.

Hai phần tử là cùng một đối tượng được lưu hai lần vẫn được tính hai lần nếu cả hai lần xuất hiện đều khớp. Tần suất gắn với các phần tử mà collection đang chứa, không phải chỉ số đối tượng riêng biệt trong bộ nhớ.

`Collection<?>` cho phép đọc collection có kiểu phần tử bất kỳ. Đối số mục tiêu là `Object`, nên Java không buộc nó có cùng kiểu generic với collection tại lời gọi. Nếu chọn nhầm kiểu mục tiêu, lời gọi vẫn có thể biên dịch nhưng không khớp phần tử nào.

## 2. Dùng equals, không dùng ==

Hai đối tượng `String` riêng có cùng nội dung vẫn có thể được đếm chung:

```java
List<String> values = List.of("java", new String("java"));
int count = Collections.frequency(values, "java"); // 2
```

`String.equals` so nội dung chuỗi. Không cần các tham chiếu phải giống nhau.

Ngược lại, `"java"` và `"Java"` khác nhau theo `String.equals`, nên không tự được gom thành một nhóm. `frequency` không có tham số comparator hoặc chế độ bỏ phân biệt hoa/thường.

Nếu muốn đếm theo tiêu chí khác như mã sản phẩm, chuỗi chuẩn hóa hoặc độ dài tên, cần một quy tắc riêng: trích khóa rồi đếm, hoặc duyệt với điều kiện rõ ràng. Không sửa `equals` của kiểu chỉ để đáp ứng một báo cáo cục bộ nếu thay đổi đó làm sai ý nghĩa bằng nhau của toàn bộ mô hình.

### Với lớp tự định nghĩa

Nếu một lớp không override `equals`, nó thường dùng so sánh định danh kế thừa từ `Object`. Hai đối tượng có các trường nhìn giống nhau không tự được coi là cùng giá trị.

Một record được tạo `equals` theo các thành phần của nó. Ví dụ record một thành phần `Category(String code)` sẽ coi hai giá trị code giống nhau là bằng nhau.

Việc đếm không cần gọi `hashCode` để so từng phần tử, nhưng kiểu đối tượng vẫn cần đáp ứng hợp đồng `equals/hashCode` nếu còn dùng với các collection băm.

## 3. Null mục tiêu và null collection khác nhau

`frequency` cho phép giá trị mục tiêu là `null`:

```java
List<String> values = Arrays.asList("java", null, null);
int missing = Collections.frequency(values, null); // 2
```

Đoạn này giả định đã import `Arrays` cùng các kiểu liên quan. `Arrays.asList` được dùng vì danh sách này chấp nhận các giá trị null.

Phân biệt:

| Trường hợp | Kết quả |
| --- | --- |
| Collection có hai phần tử null, tìm null | `2` |
| Collection rỗng, tìm bất kỳ mục tiêu nào | `0` |
| Collection không có null, tìm null | `0` |
| Chính đối số collection bằng null | `NullPointerException` |

Không dùng `List.of("java", null)` để chuẩn bị ví dụ đếm null: `List.of` từ chối null ngay khi tạo danh sách, trước khi `frequency` được gọi.

Nếu API của ứng dụng muốn xem collection null như collection rỗng, đó phải là một quyết định của API bao ngoài. `Collections.frequency` không tự áp dụng quy ước đó.

## 4. Chương trình kiểm chứng hoàn chỉnh

Ví dụ chạy trên Java 17+, có chuỗi, null, kiểu bao số, record, mảng và một tập có comparator riêng.

Lưu thành `CollectionFrequencyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.TreeSet;

public class CollectionFrequencyDemo {
    record Category(String code) {
    }

    public static void main(String[] args) {
        List<String> words = Arrays.asList(
                "java", new String("java"), "Java", null, "java", null);

        System.out.println("java: "
                + Collections.frequency(words, "java"));
        System.out.println("Java: "
                + Collections.frequency(words, "Java"));
        System.out.println("null: "
                + Collections.frequency(words, null));
        System.out.println("absent: "
                + Collections.frequency(words, "kotlin"));

        List<Integer> numbers = List.of(1, 1, 2);
        System.out.println("Integer 1: "
                + Collections.frequency(numbers, 1));
        System.out.println("Long 1: "
                + Collections.frequency(numbers, 1L));

        List<Category> categories = List.of(
                new Category("A"), new Category("A"), new Category("B"));
        System.out.println("Category A: "
                + Collections.frequency(categories, new Category("A")));

        int[] row = {1, 2};
        List<int[]> arrays = new ArrayList<>();
        arrays.add(row);
        arrays.add(row);
        arrays.add(new int[] {1, 2});
        System.out.println("same array reference: "
                + Collections.frequency(arrays, row));
        System.out.println("new equal-content array: "
                + Collections.frequency(arrays, new int[] {1, 2}));

        TreeSet<String> insensitive =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        insensitive.add("java");
        System.out.println("set contains JAVA: "
                + insensitive.contains("JAVA"));
        System.out.println("frequency JAVA: "
                + Collections.frequency(insensitive, "JAVA"));

        try {
            Collections.frequency(null, "java");
        } catch (NullPointerException e) {
            System.out.println("null collection: NullPointerException");
        }

        System.out.println("words unchanged: " + words);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CollectionFrequencyDemo.java
java CollectionFrequencyDemo
```

Stdout:

```text
java: 3
Java: 1
null: 2
absent: 0
Integer 1: 2
Long 1: 0
Category A: 2
same array reference: 2
new equal-content array: 0
set contains JAVA: true
frequency JAVA: 0
null collection: NullPointerException
words unchanged: [java, java, Java, null, java, null]
```

### Những kết quả cần giải thích

`"java"` được đếm ba lần, bao gồm chuỗi được tạo thành đối tượng riêng. `"Java"` chỉ được đếm một lần do khác chữ hoa/thường.

Literal `1` được boxing thành `Integer`, nên khớp hai phần tử của `List<Integer>`. Literal `1L` được boxing thành `Long`; `Long.equals` không tự coi một `Integer` có cùng giá trị số là bằng nó, nên kết quả là 0.

Hai `Category("A")` là hai đối tượng nhưng bằng nhau theo hợp đồng của record một thành phần. Giá trị mục tiêu mới cũng có thể khớp cả hai.

Ở cuối, nội dung `words` không thay đổi. Phương thức thực hiện truy vấn đếm, không loại trùng, xóa hay sắp xếp danh sách.

## 5. Mảng là phần tử: không tự so sánh sâu

Trong chương trình, cùng tham chiếu `row` được lưu hai lần, nên tìm `row` cho kết quả 2.

Mảng mới `new int[] {1, 2}` có cùng dữ liệu nhưng là đối tượng khác. Mảng không override `Object.equals` để so sánh nội dung, nên tìm mảng mới cho kết quả 0.

`frequency` không tự chuyển sang `Arrays.equals` hoặc `Arrays.deepEquals` khi thấy phần tử là mảng.

Nếu mục tiêu nghiệp vụ là đếm hàng có cùng dữ liệu số, có thể duyệt với phép so sánh mảng thích hợp:

```java
int[] target = {1, 2};
int count = 0;
for (int[] candidate : arrays) {
    if (Arrays.equals(target, candidate)) {
        count++;
    }
}
```

Đoạn này giả định `arrays` là danh sách mảng đã có và được đặt trong một phương thức. Với dữ liệu của chương trình gốc, kết quả theo nội dung sẽ là 3. Đây là tiêu chí khác với `frequency(arrays, target)`.

Nếu thường xuyên cần đếm theo giá trị mảng, nên có một kiểu giá trị với `equals/hashCode` phù hợp và cách bảo vệ dữ liệu khỏi thay đổi ngoài ý muốn.

## 6. Comparator của collection không thay hợp đồng frequency

Trong chương trình, `TreeSet` dùng `String.CASE_INSENSITIVE_ORDER`. Với dữ liệu lưu là `"java"`:

- `contains("JAVA")` dùng quy tắc của tập sắp thứ tự và có thể trả `true`.
- `frequency(set, "JAVA")` vẫn đếm theo `equals`; `"JAVA".equals("java")` là `false`, nên kết quả là 0.

Sự khác biệt không có nghĩa `frequency` đã đổi comparator hoặc làm mất phần tử. Hai thao tác đang trả lời câu hỏi theo hai cơ chế khác nhau.

`TreeSet` với comparator không nhất quán với `equals` cần được dùng cẩn thận vì quan hệ coi là trùng của nó không khớp hoàn toàn với hợp đồng bằng nhau chung của `Set`. Ví dụ ở đây chủ động dùng sự khác biệt để học cách đọc API.

Với một tập tuân thủ đúng hợp đồng bằng nhau theo `equals`, tần suất một giá trị thường chỉ là 0 hoặc 1 vì tập không giữ các phần tử trùng theo quan hệ đó. Với danh sách, tần suất có thể lớn hơn 1.

## 7. Chỉ một truy vấn hay bảng tần suất?

`frequency` duyệt collection để đếm, nên với n phần tử và chi phí `equals` xem như hằng, một lần gọi có chi phí `O(n)` và không cần tạo bảng đếm.

Nó phù hợp khi muốn biết số lần xuất hiện của một hoặc vài giá trị.

Nếu cần đếm k mục tiêu bằng k lần gọi, tổng công việc có thể là `O(n * k)`. Không nên gọi `frequency` cho mỗi phần tử rồi tưởng rằng toàn bộ báo cáo chỉ duyệt nguồn một lần.

Để tạo bảng tần suất, có thể duyệt một lần:

```java
// Minh họa trong một phương thức, đã import các kiểu tương ứng.
Map<String, Integer> counts = new LinkedHashMap<>();
for (String word : words) {
    counts.merge(word, 1, Integer::sum);
}
```

`LinkedHashMap` giữ thứ tự khóa theo lần xuất hiện đầu và hỗ trợ khóa null. Với dữ liệu `words` của chương trình, bảng có các mục `java=3`, `Java=1`, `null=2`.

Thiết kế bảng đếm dùng thêm bộ nhớ theo số giá trị khác nhau và dựa vào cả `equals` lẫn `hashCode` của khóa. Đó là đánh đổi khác với một truy vấn tần suất đơn lẻ.

## 8. Độ đúng phụ thuộc dữ liệu trong khi duyệt

Hợp đồng `equals` cần nhất quán, đối xứng và đáp ứng các quy tắc bằng nhau thông thường. Nếu một kiểu tự định nghĩa `equals` bất đối xứng hoặc ném lỗi với một loại đối số thông thường, phép đếm có thể trở nên khó hiểu hoặc thất bại.

Không dựa vào việc đảo chiều so sánh để sửa một `equals` sai. Hãy sửa hợp đồng của kiểu dữ liệu.

Với dữ liệu hoặc collection thay đổi đồng thời:

- `frequency` không tự tạo một ảnh chụp bất biến.
- Collection fail-fast có thể báo lỗi nếu cấu trúc bị sửa trong khi duyệt.
- Collection đồng thời có quy tắc duyệt riêng; kết quả không mặc nhiên là số lượng tại một thời điểm duy nhất.
- Thay đổi trường tham gia `equals` trong lúc đếm cũng có thể làm kết quả không phản ánh một trạng thái ổn định.

Nếu cần thống kê nhất quán, hãy có hợp đồng đồng bộ hoặc tạo ảnh chụp dữ liệu phù hợp trước khi đếm. Không chỉ chọn hàm tiện ích mà bỏ qua cách dữ liệu được cập nhật.

## 9. Cách áp dụng ngắn gọn

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Đếm một giá trị theo equals | `Collections.frequency` |
| Chỉ biết có ít nhất một phần tử | Xem hợp đồng `contains` hoặc điều kiện kiểm tra phù hợp |
| Đếm không phân biệt hoa/thường | Chuẩn hóa theo chính sách hoặc duyệt với điều kiện riêng |
| Đếm theo một thuộc tính | Trích khóa hoặc dùng điều kiện theo thuộc tính |
| Đếm mảng theo nội dung | Dùng phép so sánh mảng phù hợp |
| Tạo tần suất cho mọi giá trị | Bảng đếm một lần duyệt |
| Đếm trên dữ liệu đang thay đổi | Xác định quy tắc nhất quán trước |

Điều quan trọng nhất là quyết định “hai phần tử được coi là cùng một giá trị” nghĩa là gì. `frequency` cung cấp sẵn câu trả lời theo `equals`, không tự suy luận tiêu chí nghiệp vụ.

## 10. Tự kiểm tra

1. Hai String khác tham chiếu nhưng cùng nội dung có được đếm chung không?
2. Tìm null trong collection hợp lệ có làm `frequency` ném lỗi chỉ vì mục tiêu là null không?
3. Vì sao tìm `1L` trong `List<Integer>` có thể biên dịch nhưng trả 0?
4. Đếm một mảng mới có cùng dữ liệu với các phần tử mảng cũ có tự dùng deep equals không?
5. Comparator của `TreeSet` có được `frequency` dùng làm tiêu chí đếm không?
6. Gọi `frequency` cho n giá trị, mỗi lần trên danh sách n phần tử, có thể tốn bao nhiêu công việc?

Đáp án:

1. Có, theo `String.equals`.
2. Không; nó đếm các phần tử null.
3. Mục tiêu có kiểu `Long`, không bằng các `Integer`; tham số mục tiêu của API là `Object`.
4. Không.
5. Không; phương thức đếm theo `equals`.
6. Có thể ở bậc `O(n²)`, nếu các phép bằng nhau có chi phí hằng.

## Tài liệu đối chiếu

Xem hợp đồng [Collections.frequency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#frequency(java.util.Collection,java.lang.Object)), quy tắc [Object.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object)) và lưu ý về thứ tự nhất quán với equals của [TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).
