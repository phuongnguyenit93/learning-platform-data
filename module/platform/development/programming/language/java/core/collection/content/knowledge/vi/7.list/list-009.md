# Chọn List khi cần truy cập chỉ số hoặc giữ phần tử trùng

Chọn collection bắt đầu từ **ý nghĩa của nhóm dữ liệu**, không phải tên lớp quen thuộc.

Nếu dữ liệu là một chuỗi có vị trí cần truy cập, hoặc mỗi lần xuất hiện của cùng một giá trị đều phải được giữ lại, `List<E>` là một lựa chọn cần xét. Tuy nhiên, hai nhu cầu đó còn phải được đặt cạnh yêu cầu về thứ tự, tra cứu, sửa đổi và cách xử lý phần tử.

Bài dùng Java 17. Ba chương trình hoàn chỉnh đã được biên dịch với `--release 17` và chạy để đối chiếu stdout. Các đoạn mã rút gọn khác minh họa thao tác trong một phương thức, không phải tệp chạy độc lập.

Sau bài học, bạn có thể:

- Nhận diện yêu cầu nào thực sự cần vị trí của danh sách.
- Phân biệt một giá trị duy nhất với nhiều lần xuất hiện của giá trị đó.
- Giải thích khi nào Set, Map hoặc hàng đợi mô tả bài toán tốt hơn.
- Chọn lớp triển khai List theo thao tác chủ yếu.
- Tránh dùng chỉ số làm định danh ổn định của dữ liệu.

## 1. List biểu diễn một chuỗi phần tử có vị trí

Xét:

```text
Giá trị:   P1   P2   P1   P3
Chỉ số:     0    1    2    3
```

Ta có thể hỏi:

- Phần tử ở vị trí thứ ba là gì?
- Cần chèn một phần tử trước vị trí nào?
- Có những lần xuất hiện nào của P1 trong chuỗi?
- Nếu đổi chỗ hai phần tử, chuỗi kết quả có còn cùng ý nghĩa không?

List cung cấp hợp đồng truy cập và điều khiển vị trí theo chỉ số. Những lớp thông dụng như ArrayList cho phép các phần tử bằng nhau xuất hiện nhiều lần. Đây là mô hình chuỗi được mô tả trong [List Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

Cần phân biệt ba tính chất:

1. **Có thứ tự:** phần tử có vị trí tương đối trong chuỗi.
2. **Có chỉ số:** có thể gọi các thao tác vị trí như get hoặc set.
3. **Có sắp xếp:** dữ liệu đang theo một quy tắc so sánh như tăng dần.

List có mô hình thứ tự vị trí, nhưng không tự sắp xếp giá trị. Danh sách `[P1, P2, P1, P3]` có thứ tự rõ, dù không được nhóm các mã bằng nhau lại với nhau.

### Thứ tự không chỉ là thứ tự thêm ở cuối

Khi gọi add ở cuối, vị trí thường theo thứ tự thêm. Nhưng chương trình còn có thể:

- Chèn ở giữa.
- Xóa một vị trí.
- Hoán đổi phần tử.
- Sắp xếp lại.
- Thay dữ liệu ở một vị trí.

Vì vậy, nên nói List giữ **chuỗi vị trí hiện tại**, thay vì hiểu rằng nó vĩnh viễn giữ nguyên lịch sử chèn ban đầu.

## 2. Khi nào truy cập chỉ số là yêu cầu thật sự?

Những tình huống thường phù hợp:

| Tình huống | Vì sao vị trí có ý nghĩa? |
| --- | --- |
| Danh sách phát nhạc | Một bài có vị trí phát cụ thể; cùng bài có thể phát lại |
| Các bước trong một quy trình | Bước trước/sau và thao tác đổi vị trí có ý nghĩa |
| Các hàng kết quả theo thứ tự được xác định | Bên sử dụng cần truy cập hoặc trình bày theo vị trí |
| Các dòng trong một tài liệu | Chèn, thay và lấy dòng theo vị trí là thao tác thực |
| Một chuỗi quan sát hoặc lượt quét | Trình tự xuất hiện cần được giữ |

Một phép truy cập minh họa:

```java
String third = scans.get(2);
```

Chỉ số bắt đầu từ 0. Phần tử thứ ba theo cách đếm thông thường nằm ở chỉ số 2.

### Không phải mọi câu hỏi có số đều là chỉ số

“Tìm bản ghi có mã 1002” khác với “lấy phần tử ở vị trí 1002”.

- Mã bản ghi là thuộc tính nhận diện.
- Chỉ số là vị trí hiện tại trong một danh sách.
- Chỉ số có thể đổi khi thêm/xóa hoặc sắp xếp.
- Mã hợp lệ không nhất thiết liên tục hoặc bắt đầu từ 0.

Nếu yêu cầu chính là tra bằng mã, Map thường là mô hình cần xét. List vẫn có thể dùng để trình bày thứ tự, nhưng không nên coi chỉ số là mã nghiệp vụ.

### Nếu chỉ duyệt tuần tự, có thể chưa cần List

Một phương thức chỉ in hoặc xử lý lần lượt các phần tử có thể chỉ cần Iterable hoặc Collection phù hợp. Yêu cầu riêng List chỉ để viết vòng get(index) có thể làm API phụ thuộc vào khả năng không cần thiết.

Chọn List khi thứ tự chuỗi hoặc khả năng vị trí là một phần hợp đồng cần cung cấp, không chỉ vì đó là cấu trúc đầu tiên được học.

## 3. “Giữ trùng” nghĩa là giữ các lần xuất hiện

Giả sử máy quét ghi nhận:

```text
P1, P2, P1, P3
```

Có bốn lượt quét, dù chỉ có ba mã khác nhau.

Hai yêu cầu sau khác nhau:

- **Lưu lịch sử lượt quét:** P1 xuất hiện hai lần, và hai vị trí đều có ý nghĩa.
- **Lưu danh mục mã đã từng thấy:** mỗi mã chỉ cần xuất hiện một lần.

List phù hợp với mô hình thứ nhất. Một Set có thể phù hợp với mô hình thứ hai, nếu quan hệ duy nhất được xác định đúng.

### Trùng theo giá trị không bắt buộc cùng tham chiếu

Một danh sách có thể chứa:

- Hai đối tượng khác nhau nhưng equals nhau.
- Cùng một tham chiếu được thêm vào nhiều vị trí.

Kích thước danh sách đếm các phần tử ở các vị trí, không đếm số đối tượng Java khác nhau đang tồn tại trong bộ nhớ.

Giữ trùng cũng không có nghĩa tự sao chép đối tượng. Nếu thêm cùng một đối tượng khả biến hai lần, hai vị trí có thể cùng tham chiếu tới đối tượng đó.

### Cùng thuộc tính chưa chắc là phần tử bằng nhau

Hai bản ghi có cùng mã sản phẩm nhưng khác mã lần quét, thời gian hoặc dữ liệu khác có thể không equals nhau.

Do đó, trước khi chọn “không trùng”, hãy trả lời:

- Duy nhất theo toàn bộ giá trị đối tượng?
- Duy nhất theo một mã?
- Hay mỗi lần xuất hiện phải được giữ riêng dù có cùng mã?

Tên collection không thể tự quyết định quan hệ nghiệp vụ đó thay bạn.

## 4. Chương trình giữ lượt xuất hiện và truy cập vị trí

Tạo tệp **`ChoosingListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class ChoosingListDemo {
    public static void main(String[] args) {
        String repeated = "P1";
        List<String> scans =
                new ArrayList<>(List.of(repeated, "P2", repeated, "P3"));

        System.out.println("scans = " + scans);
        System.out.println("occurrence count = " + scans.size());
        System.out.println("at index 2 = " + scans.get(2));
        System.out.println("same reference at 0 and 2 = "
                + (scans.get(0) == scans.get(2)));

        Set<String> uniqueCodes = new LinkedHashSet<>(scans);
        System.out.println("unique codes = " + uniqueCodes);
        System.out.println("unique count = " + uniqueCodes.size());

        boolean removed = scans.remove("P1");
        System.out.println("one P1 removed = " + removed);
        System.out.println("remaining scans = " + scans);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ChoosingListDemo.java
java -Dfile.encoding=UTF-8 ChoosingListDemo
```

Stdout đã kiểm chứng:

```text
scans = [P1, P2, P1, P3]
occurrence count = 4
at index 2 = P1
same reference at 0 and 2 = true
unique codes = [P1, P2, P3]
unique count = 3
one P1 removed = true
remaining scans = [P2, P1, P3]
```

### Đọc kết quả

- Danh sách có 4 phần tử vì giữ cả hai lần P1.
- get(2) trả P1 ở lần xuất hiện thứ hai.
- Hai vị trí 0 và 2 giữ cùng tham chiếu trong ví dụ vì chương trình chủ động dùng lại biến repeated.
- LinkedHashSet giữ ba mã duy nhất và trình bày chúng theo thứ tự gặp đầu tiên.
- remove("P1") trên danh sách xóa một lần xuất hiện đầu tiên, nên P1 còn lại vẫn được giữ.

Nếu bài toán phải biết mọi lượt quét, việc chuyển thẳng sang Set đã làm mất một phần thông tin.

### Có thứ tự vẫn chưa chắc thay được List

LinkedHashSet trong ví dụ có thứ tự duyệt rõ, nhưng không cung cấp thao tác get(index) của List và không giữ hai lần P1.

Điều này cho thấy “có thứ tự” không phải tiêu chí duy nhất để hai cấu trúc thay thế nhau.

### Chuyển ngược không phục hồi thông tin đã mất

Tạo một ArrayList mới từ uniqueCodes có thể cho một chuỗi ba mã, nhưng không đủ dữ liệu để biết P1 từng có hai lượt hoặc đã nằm ở vị trí nào trong chuỗi gốc.

Sao chép sang List chỉ thay cấu trúc biểu diễn của dữ liệu đang có; nó không khôi phục những lần xuất hiện đã bị loại.

## 5. Chỉ giữ số lần hay phải giữ cả chuỗi?

Nếu chỉ cần biết:

```text
A xuất hiện 2 lần
B xuất hiện 1 lần
```

một bảng đếm theo giá trị có thể mô tả đúng nhu cầu mà không lưu từng lần thành một vị trí riêng.

Nhưng hai chuỗi:

```text
[A, B, A]
[A, A, B]
```

có cùng bảng đếm mà khác thứ tự.

### Chương trình hoàn chỉnh

Tạo tệp **`SequenceVsCountsDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class SequenceVsCountsDemo {
    public static void main(String[] args) {
        List<String> first = List.of("A", "B", "A");
        List<String> second = List.of("A", "A", "B");

        Map<String, Integer> firstCounts = count(first);
        Map<String, Integer> secondCounts = count(second);

        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("same list values = " + first.equals(second));
        System.out.println("first counts = " + firstCounts);
        System.out.println("second counts = " + secondCounts);
        System.out.println("same counts = " + firstCounts.equals(secondCounts));

        Map<String, List<Integer>> positions = new LinkedHashMap<>();
        for (int index = 0; index < first.size(); index++) {
            positions.computeIfAbsent(
                    first.get(index), key -> new java.util.ArrayList<>()).add(index);
        }
        System.out.println("first positions by value = " + positions);
    }

    private static Map<String, Integer> count(List<String> values) {
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String value : values) {
            counts.merge(value, 1, Integer::sum);
        }
        return counts;
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 SequenceVsCountsDemo.java
java -Dfile.encoding=UTF-8 SequenceVsCountsDemo
```

Stdout đã kiểm chứng:

```text
first = [A, B, A]
second = [A, A, B]
same list values = false
first counts = {A=2, B=1}
second counts = {A=2, B=1}
same counts = true
first positions by value = {A=[0, 2], B=[1]}
```

### Những mô hình được so sánh

**List:**

- Giữ các phần tử ở đúng vị trí.
- Hai chuỗi khác thứ tự không bằng nhau theo List.equals trong ví dụ.

**Map<String, Integer> đếm số lần:**

- Giữ mỗi giá trị cùng số lần xuất hiện.
- Hai bảng đếm bằng nhau, dù các chuỗi ban đầu khác nhau.
- Số đếm không đủ để tái dựng vị trí từng lần.

**Map<String, List<Integer>> giữ vị trí:**

- Nhóm theo giá trị.
- Mỗi nhóm có danh sách chỉ số.
- Ví dụ A có các vị trí 0 và 2, B có vị trí 1.

Cấu trúc ghép cho thấy List và Map có thể cùng tham gia một mô hình. Việc chọn không phải lúc nào cũng là loại bỏ toàn bộ một bên.

Trong ví dụ nhỏ, số lần và chỉ số đều nằm trong phạm vi int. Với dữ liệu quy mô khác, phải chọn kiểu và chính sách số học phù hợp cho bảng đếm.

### Giữ trùng chưa đủ để kết luận phải dùng List

Nếu chỉ xử lý công việc theo đầu hàng đợi, một Queue hoặc Deque phù hợp vẫn có thể giữ nhiều công việc bằng nhau mà không cần hợp đồng truy cập vị trí.

Câu hỏi đúng là: **có cần một chuỗi vị trí để truy cập/sửa, hay chỉ cần quy tắc lấy phần tử tiếp theo?**

## 6. Đối chiếu với các cấu trúc khác

| Yêu cầu chủ yếu | Mô hình cần xét | Điểm cần kiểm tra |
| --- | --- | --- |
| Chuỗi phần tử có vị trí và giữ từng lần xuất hiện | List | Chi phí truy cập và khả năng sửa |
| Tập giá trị duy nhất | Set | Quan hệ duy nhất và chính sách thứ tự |
| Tra giá trị theo khóa | Map | Khóa có duy nhất không; cập nhật trùng khóa có ý nghĩa gì |
| Nhận/xử lý phần tử theo chính sách hàng đợi | Queue hoặc Deque | Thao tác ở đầu/cuối và thứ tự xử lý |
| Chỉ cần số lần của mỗi giá trị | Map giá trị → số lần | Có chấp nhận mất thông tin thứ tự không |
| Mỗi khóa có nhiều giá trị | Map khóa → List giá trị | Thứ tự trong nhóm và thứ tự toàn cục |
| Số vị trí cố định, đặc biệt với dữ liệu nguyên thủy | Mảng | Kích thước, kiểu dữ liệu và thao tác cần có |

### Map có thể chứa các giá trị trùng

Map yêu cầu cách xử lý khóa theo hợp đồng của nó; không có nghĩa các giá trị của mọi khóa đều phải khác nhau.

Nếu dùng mã bài hát làm khóa rồi put cùng mã nhiều lần, một Map đơn giá trị không tự lưu nhiều lượt phát dưới cùng khóa. Muốn nhiều lần dưới một khóa, phải chọn giá trị dạng nhóm hoặc một mô hình khác.

### Nhóm theo khóa có thể làm mất cách đan xen toàn cục

Map<LoạiSựKiện, List<SựKiện>> có thể giữ thứ tự trong mỗi nhóm, nhưng chỉ những danh sách nhóm đó chưa chắc đủ để biết các loại đã đan xen ra sao trong chuỗi toàn cục.

Nếu thứ tự toàn cục quan trọng, cần giữ chuỗi gốc hoặc lưu thông tin vị trí/thời điểm đủ rõ. Ví dụ chương trình đã giữ chỉ số cho từng nhóm là một cách làm thông tin vị trí trở nên tường minh.

### Set không phải cách “làm sạch” luôn đúng

Nếu mỗi lần xuất hiện là một sự kiện thực, loại phần tử bằng nhau có thể xóa thông tin hợp lệ.

Ngược lại, nếu lặp lại là lỗi dữ liệu, việc List giữ được nó không có nghĩa hệ thống nên chấp nhận. Ràng buộc nghiệp vụ cần được kiểm tra rõ thay vì trông chờ cấu trúc tự quyết định.

## 7. Chỉ số không phải định danh ổn định

Giả sử một danh sách quy trình có bước Review ở chỉ số 1. Khi chèn một bước Prepare ở đầu, Review chuyển sang chỉ số 2.

Nếu chương trình đã lưu số 1 để đại diện Review, số đó bây giờ trỏ tới một bước khác.

### Chương trình hoàn chỉnh

Tạo tệp **`PositionIsNotIdDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class PositionIsNotIdDemo {
    public record Step(String id, String text) {
    }

    public static void main(String[] args) {
        Step review = new Step("S20", "Review");
        List<Step> steps = new ArrayList<>(List.of(
                new Step("S10", "Start"),
                review,
                new Step("S30", "Finish")));

        int savedIndex = 1;
        String savedId = steps.get(savedIndex).id();

        steps.add(0, new Step("S05", "Prepare"));

        Map<String, Step> byId = new LinkedHashMap<>();
        for (Step step : steps) {
            byId.put(step.id(), step);
        }

        System.out.println("current ids = "
                + steps.stream().map(Step::id).toList());
        System.out.println("saved index now points to = "
                + steps.get(savedIndex).id());
        System.out.println("review current index = " + steps.indexOf(review));
        System.out.println("saved id = " + savedId);
        System.out.println("lookup by saved id = " + byId.get(savedId).text());
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 PositionIsNotIdDemo.java
java -Dfile.encoding=UTF-8 PositionIsNotIdDemo
```

Stdout đã kiểm chứng:

```text
current ids = [S05, S10, S20, S30]
saved index now points to = S10
review current index = 2
saved id = S20
lookup by saved id = Review
```

### Cách đọc

- savedIndex vẫn là 1, nhưng danh sách đã thay cấu trúc nên vị trí đó hiện chứa S10.
- Review vẫn là bước có id S20.
- indexOf(review) trong trạng thái mới trả 2.
- Map byId được xây từ danh sách hiện tại và tra bằng id đã lưu, nên nhận đúng Review.

Ví dụ giả định id của mỗi Step là duy nhất. Nếu đầu vào cho phép trùng id, cần quy định cách xử lý thay vì để put vô tình thay giá trị cũ.

Map trong chương trình là một chỉ mục được tạo **sau lần chèn**. Nó không tự đồng bộ theo mọi thay đổi tương lai của List. Nếu hệ thống giữ đồng thời cả List và Map, phải thiết kế cách cập nhật để chúng nhất quán.

### Khi vị trí vẫn là dữ liệu đúng

Chỉ số rất phù hợp khi thao tác thật sự là:

- “Đổi phần tử ở hàng thứ ba trong trạng thái hiện tại”.
- “Chèn trước bước đang nằm ở vị trí này”.
- “Lấy phần tử theo vị trí do bộ điều khiển danh sách quản lý”.

Vấn đề là dùng một vị trí thay cho danh tính qua nhiều thay đổi mà không có quy tắc giữ trạng thái.

## 8. Chọn lớp triển khai khi đã chọn List

Hợp đồng chỉ số không đồng nghĩa mọi List truy cập chỉ số nhanh như nhau.

### ArrayList khi truy cập vị trí là thao tác nổi bật

ArrayList dùng mô hình mảng có khả năng tăng dung lượng. get và set có thời gian không tăng theo số phần tử trong mô hình chi phí thông thường; thêm cuối có chi phí hằng số khấu hao. Chèn/xóa giữa thường cần dịch dữ liệu. Xem [ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Vì vậy, với một danh sách cần đọc theo chỉ số, duyệt và thêm cuối, ArrayList thường là điểm bắt đầu hợp lý để đánh giá.

Đó không phải lời hứa rằng nó tốt nhất cho mọi tải hoặc mọi kích thước. Còn phải xét dung lượng, tần suất sửa, phần tử và điều kiện thực thi.

### LinkedList có chỉ số nhưng cần tìm tới vị trí

LinkedList tổ chức các nút liên kết hai chiều; thao tác theo chỉ số phải đi từ đầu hoặc cuối tới vị trí cần thiết. Tài liệu [LinkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) mô tả rõ cách tìm từ đầu gần hơn.

Hệ quả:

- Có phương thức get(index) không có nghĩa truy cập ngẫu nhiên hằng số.
- Nếu đã duyệt tới vị trí bằng ListIterator, chèn/xóa tại đó có thể thao tác trên liên kết đang biết.
- Nếu mỗi lần chèn đều phải tìm theo chỉ số từ đầu hoặc cuối, phải tính cả chi phí tìm vị trí.

Không nên chọn LinkedList chỉ vì thấy yêu cầu “có nhiều lần thêm/xóa”. Cần biết thêm/xóa ở đâu, đã có con trỏ chưa và các thao tác đọc khác diễn ra như thế nào.

### Bảng định hướng

| Mẫu sử dụng | Điều cần ưu tiên |
| --- | --- |
| Nhiều get/set theo chỉ số | Khả năng truy cập vị trí của lớp |
| Chủ yếu duyệt tuần tự | Iterator hoặc enhanced for; tránh tìm lại từng chỉ số không cần thiết |
| Chèn/xóa giữa qua con trỏ đã có | Chi phí chỉnh sửa ở vị trí đó |
| Chủ yếu thao tác hai đầu | Xem cả hợp đồng Deque thay vì chỉ List |
| Đọc nhiều và yêu cầu đồng thời đặc biệt | Chọn chính sách đồng thời riêng, không suy từ List |

Nếu hiệu năng là yêu cầu thực tế, hãy đo trên mẫu dữ liệu và chuỗi thao tác đại diện. Độ phức tạp giúp loại những giả định sai, nhưng không thay thế tất cả điều kiện triển khai.

## 9. Khả năng sửa đổi là một quyết định riêng

Một List có thể đúng về mặt thứ tự và phần tử trùng nhưng không hỗ trợ thao tác bạn sắp làm.

Ví dụ:

```java
List<String> fixedData = List.of("A", "B", "A");
List<String> editable = new ArrayList<>(fixedData);
```

Cả hai giữ ba lần xuất hiện theo thứ tự đó. Khác biệt là:

- fixedData không cho thêm, xóa hoặc thay thế phần tử.
- editable là bản sao cấu trúc có thể sửa qua các thao tác ArrayList hỗ trợ.

Khả năng giữ trùng không phụ thuộc việc danh sách có sửa được hay không.

### Null không phải tiêu chí suy ra từ tên List

Một số List cho phép null, một số nguồn tạo List từ chối nó. Hãy quyết định rõ dữ liệu thiếu được biểu diễn thế nào và kiểm tra hợp đồng của nguồn.

Không dùng “List cho phép trùng” làm suy luận rằng nó cũng cho phép mọi giá trị hoặc mọi thao tác.

### Phần tử khả biến cần chính sách riêng

Danh sách không sửa đổi cấu trúc không tự làm phần tử trở thành bất biến. Ngược lại, một danh sách có thể sửa không bắt buộc phần tử cũng là đối tượng khả biến.

Khi cùng tham chiếu xuất hiện nhiều lần, việc sửa đối tượng đó có thể được nhìn thấy qua nhiều vị trí. Nếu muốn mỗi lần xuất hiện có trạng thái độc lập, hãy tạo các bản ghi/lần xuất hiện riêng hoặc sao chép theo chính sách phù hợp.

## 10. Thiết kế API từ hợp đồng cần có

Trước khi công bố một List cho phần khác sử dụng, nên nói rõ:

- Thứ tự mang ý nghĩa gì.
- Phần tử bằng nhau có được xuất hiện nhiều lần không.
- Bên nhận có quyền thêm/xóa/sửa không.
- Kết quả là bản sao, góc nhìn dùng chung hay đối tượng sống.
- Chỉ số hợp lệ trong phạm vi trạng thái nào.
- Có được nhiều bên cùng sử dụng và sửa không.

### Chỉ yêu cầu khả năng thật sự cần dùng

Nếu một phương thức cần lấy vị trí cụ thể, tham số List có ý nghĩa:

```java
static String valueAt(List<String> values, int index) {
    return values.get(index);
}
```

Đây là một khai báo phương thức minh họa; nó dựa vào List để kiểm tra chỉ số và không tự định nghĩa thêm chính sách dữ liệu thiếu.

Nếu phương thức chỉ đọc lần lượt, Iterable có thể là hợp đồng đủ hẹp hơn. Nếu phương thức cần “mỗi giá trị chỉ xuất hiện một lần”, cần xem Set hoặc kiểm tra riêng thay vì để tham số List tạo kỳ vọng sai.

### Trả List là công bố ý nghĩa thứ tự

Nếu API trả List, bên sử dụng có thể dựa vào chuỗi vị trí. Hãy xác định thứ tự đó có ổn định giữa các lần gọi không và đến từ nguồn nào.

Một danh sách được tạo từ một nguồn không bảo đảm thứ tự không tự có thứ tự nghiệp vụ chỉ vì kết quả mang kiểu List. Nó có một thứ tự cụ thể trong lần tạo, nhưng ý nghĩa và tính lặp lại cần được thiết kế.

### Dữ liệu dùng chung cần quyền sở hữu rõ

Cho nhiều bên sửa cùng một List làm các chỉ số và thứ tự có thể thay đổi ngoài phạm vi dự kiến.

Tùy bài toán, có thể:

- Giữ một bên sở hữu việc sửa.
- Trả bản sao cấu trúc.
- Trả dữ liệu không cho sửa đổi.
- Dùng cơ chế phối hợp hoặc cấu trúc đồng thời phù hợp.

Đừng mặc định ArrayList thông thường an toàn khi nhiều luồng cùng sửa. Cũng không coi mỗi phương thức được bảo vệ riêng là toàn bộ một chuỗi thao tác theo chỉ số tự trở thành nguyên tử.

## 11. Quy trình quyết định ngắn

### Bước 1: xác định một phần tử là gì

Một mã sản phẩm, một lượt quét hay một dòng sự kiện là ba đơn vị khác nhau.

Nếu “một phần tử” chưa được định nghĩa, quy tắc trùng lặp và đếm rất dễ bị sai.

### Bước 2: xác định thông tin cần giữ

Hỏi:

- Có cần thứ tự toàn chuỗi không?
- Có cần giữ từng lần xuất hiện không?
- Có cần truy cập/sửa theo chỉ số không?
- Hay chỉ cần thành viên duy nhất, số lượng hoặc tra bằng khóa?

### Bước 3: chọn hợp đồng

Chọn List, Set, Map, Queue/Deque hoặc cấu trúc ghép theo những câu trả lời trên.

Không ép mọi nhu cầu vào List chỉ vì nó chứa được dữ liệu.

### Bước 4: chọn đối tượng cụ thể

Kiểm tra:

- Chi phí các thao tác chính.
- Khả năng sửa đổi.
- Chính sách null.
- Quan hệ chia sẻ với nguồn.
- Yêu cầu sử dụng đồng thời.

### Bước 5: kiểm chứng bằng dữ liệu làm lộ khác biệt

Một tập thử hữu ích cần có:

- Phần tử ở đầu.
- Phần tử trùng.
- Chuỗi cùng số đếm nhưng khác thứ tự.
- Chèn/xóa trước một vị trí đang được dùng.
- Truy vấn theo mã khác với truy vấn theo vị trí.

Các chương trình trong bài dùng đúng những tình huống này để làm rõ ý nghĩa, thay vì chỉ kiểm tra một danh sách không trùng và không bị sửa.

## 12. Những sai lầm thường gặp

### Chọn List chỉ vì “có nhiều đối tượng”

Mọi collection đều có thể quản lý nhóm dữ liệu theo những mô hình khác nhau. Cần xác định vị trí, trùng lặp, khóa và cách xử lý.

### Chọn Set để bỏ phần trùng mà chưa biết phần trùng có ý nghĩa gì

Hai lượt quét giống mã vẫn có thể là hai sự kiện thật. Loại chúng có thể làm mất dữ liệu hợp lệ.

### Chọn List vì “giữ trùng”, dù chỉ cần số lượng

Nếu không cần từng vị trí hay từng bản ghi, bảng đếm có thể diễn đạt nhu cầu rõ hơn. Ngược lại, số đếm không tái dựng được chuỗi.

### Cho rằng giữ thứ tự nghĩa là luôn sắp tăng dần

List giữ trật tự vị trí mà chương trình đang có. Sort là một thao tác hoặc chính sách riêng.

### Cho rằng mọi List get nhanh như nhau

LinkedList có get(index) nhưng phải tìm vị trí. Xem lớp triển khai và thuật toán duyệt.

### Dùng chỉ số làm khóa lâu dài

Chèn, xóa và sort đều có thể làm vị trí thay đổi. Dùng định danh riêng khi cần nhận diện qua nhiều trạng thái.

### Nghĩ thêm hai lần là tạo hai bản sao đối tượng

List giữ hai tham chiếu ở hai vị trí; đó có thể là cùng một đối tượng. Nếu cần trạng thái mỗi lần riêng, phải mô hình hóa rõ.

### Dùng song song List và Map mà không có cách cập nhật

Hai cấu trúc không tự giữ nhất quán. Chương trình cần một nơi chịu trách nhiệm thêm, xóa và thay dữ liệu tương ứng.

### Suy rằng List phải sửa được

Một List không sửa đổi vẫn có vị trí và có thể giữ trùng. Chọn nguồn tạo phù hợp thao tác cần làm.

## 13. Thực hành

### Bài 1: giữ lượt quét hay giữ mã?

Một thiết bị ghi nhận:

```text
X, Y, X, X, Z
```

Thiết kế riêng cho ba yêu cầu:

1. Hiển thị đầy đủ lịch sử theo thứ tự.
2. Hiển thị các mã đã từng xuất hiện, mỗi mã một lần.
3. Hiển thị số lần của mỗi mã.

Nêu cấu trúc và thông tin nào được giữ hoặc không còn giữ ở mỗi lựa chọn.

### Bài 2: hai chuỗi cùng số đếm

Tạo hai chuỗi có cùng bảng đếm nhưng khác thứ tự. Chứng minh:

- List.equals không xem chúng là cùng chuỗi.
- Bảng đếm có thể bằng nhau.
- Không thể chỉ từ số lần mà suy ra thứ tự gốc.

### Bài 3: mô hình lượt phát

Một danh sách phát cho phép cùng một bài xuất hiện nhiều lần.

Hãy xác định:

- Một phần tử là bài hát hay một lượt phát.
- Khi cần trạng thái riêng cho mỗi lượt, những trường nào cần có.
- Mã bài hát và vị trí phát có khác nhau thế nào.
- Chuyển sang Set theo mã bài sẽ làm mất điều gì.

### Bài 4: chọn lớp theo thao tác

So sánh các tình huống:

- Nhiều lần đọc phần tử tại vị trí bất kỳ.
- Duyệt từ đầu đến cuối mà không cần chỉ số.
- Đã có ListIterator ở giữa và cần chèn/xóa quanh đó.
- Chủ yếu thêm/lấy ở hai đầu.

Giải thích bằng cách tìm vị trí và cập nhật cấu trúc, không chỉ câu “lớp này nhanh hơn”.

### Bài 5: chỉ số và định danh

Mở rộng PositionIsNotIdDemo:

1. Lưu một id và một chỉ số ban đầu.
2. Chèn hoặc xóa trước vị trí đó.
3. Sắp xếp lại danh sách theo text.
4. Đối chiếu phần tử tại chỉ số cũ với bước có id đã lưu.
5. Nếu giữ cả Map và List, mô tả cách làm chúng nhất quán sau mỗi thao tác.

Tiêu chí hoàn thành là chọn cấu trúc theo đúng đơn vị dữ liệu, giữ đủ thông tin về vị trí hoặc lần xuất hiện, và tách rõ thứ tự hiện tại khỏi định danh ổn định.
