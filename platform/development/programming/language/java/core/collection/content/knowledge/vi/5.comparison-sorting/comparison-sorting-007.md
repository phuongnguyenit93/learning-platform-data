# Tính ổn định của sắp xếp List và cách xử lý phần tử đồng hạng

Khi sắp xếp một danh sách theo điểm, mức ưu tiên hoặc ngày tạo, nhiều phần tử có thể có cùng khóa. Lúc đó có hai câu hỏi riêng:

1. Các nhóm khóa khác nhau phải đứng theo thứ tự nào?
2. Bên trong một nhóm đồng hạng, phần tử nào đứng trước?

**Sắp xếp ổn định (stable sort)** giải quyết câu hỏi thứ hai bằng cách giữ thứ tự tương đối mà những phần tử đồng hạng đã có trước lần sắp xếp.

Tính ổn định có ích khi thứ tự đầu vào mang ý nghĩa, chẳng hạn thứ tự tiếp nhận hồ sơ. Nhưng nó không tự biến một nguồn không có thứ tự xác định thành kết quả hoàn toàn xác định, và cũng không tự tạo tiêu chí phụ còn thiếu của nghiệp vụ.

## 1. Đồng hạng theo quy tắc so sánh

Giả sử danh sách gồm các bản ghi:

| Vị trí ban đầu | Mã | Hạng dùng để sắp xếp |
| --- | --- | --- |
| 0 | C | 2 |
| 1 | D | 1 |
| 2 | A | 2 |
| 3 | B | 1 |
| 4 | E | 2 |

Quy tắc là hạng nhỏ hơn đứng trước:

~~~java
// Entry là kiểu có phương thức rank() trả int.
Comparator<Entry> byRank = Comparator.comparingInt(Entry::rank);
~~~

D và B đồng hạng vì:

~~~java
byRank.compare(d, b) == 0
~~~

C, A và E cũng đồng hạng với nhau theo comparator này.

Các bản ghi có thể khác mã, khác đối tượng và không `equals` nhau. “Đồng hạng” ở đây chỉ có nghĩa comparator trả `0` theo tiêu chí đang dùng.

Sau một lần sắp xếp ổn định tăng dần theo hạng:

~~~text
Trước: C:2, D:1, A:2, B:1, E:2
Sau:   D:1, B:1, C:2, A:2, E:2
~~~

Hai nhóm được sắp lại theo hạng. Bên trong nhóm `1`, D vẫn trước B. Bên trong nhóm `2`, C vẫn trước A, A vẫn trước E.

Không có điều kiện mã phải tăng theo bảng chữ cái. Nếu yêu cầu mã tăng dần khi đồng hạng, đó là một tiêu chí bổ sung, cần được biểu đạt riêng.

## 2. Định nghĩa chính xác của tính ổn định

Gọi các phần tử trước sort là `x0, x1, ..., xn-1`. Với comparator `c`, nếu:

~~~text
i < j
và c.compare(xi, xj) == 0
~~~

thì một phép sort ổn định giữ lần xuất hiện `xi` trước lần xuất hiện `xj` trong kết quả.

Định nghĩa nói về **thứ tự tương đối**:

- Hai phần tử có thể chuyển sang chỉ số mới.
- Giữa chúng có thể thay đổi khoảng cách.
- Nhưng phần tử đứng trước trong cặp đồng hạng vẫn đứng trước sau sort.

Với dữ liệu trên, D chuyển từ chỉ số `1` sang `0`; B từ `3` sang `1`. Thứ tự tương đối D trước B được giữ, dù chỉ số đều thay đổi.

Tính ổn định cũng áp dụng cho các lần xuất hiện trong danh sách có phần tử lặp. Trong thực tế, cần dữ liệu có nhãn hoặc định danh riêng để quan sát rõ hai phần tử cùng khóa; nếu chỉ in `[1, 1, 2]`, sẽ khó thấy liệu hai số `1` đã đổi chỗ nội bộ hay chưa.

### Không nhầm “stable” với các thuộc tính khác

| Thuộc tính | Câu hỏi nó trả lời |
| --- | --- |
| Sắp xếp đúng theo comparator | Kết quả có tuân theo quan hệ thứ tự không? |
| Sắp xếp ổn định | Các phần tử so sánh bằng nhau có giữ thứ tự tương đối trước sort không? |
| Không thay đổi nguồn | Thao tác có sửa danh sách đầu vào không? |
| Kết quả xác định theo dữ liệu | Cùng tập dữ liệu có đủ quy tắc để chọn một thứ tự cụ thể không? |
| An toàn khi nhiều luồng cùng truy cập | Có quy tắc đồng bộ và cấu trúc phù hợp để tránh xung đột không? |

Một phép sort có thể vừa ổn định vừa thay đổi danh sách tại chỗ. Tính ổn định cũng không thay thế việc đồng bộ giữa các luồng.

## 3. Cam kết của API sắp xếp List

`List.sort(comparator)` có cam kết ổn định. Một triển khai đúng hợp đồng không được đổi thứ tự tương đối của các phần tử mà comparator xem là bằng nhau. Đây là yêu cầu API, không chỉ là một kết quả tình cờ của một thuật toán hiện tại. Xem [List.sort trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

~~~java
// values phải là danh sách hỗ trợ thay đổi thứ tự phần tử.
values.sort(byRank);
~~~

`Collections.sort(list, comparator)` cũng cam kết ổn định; biến thể dùng thứ tự tự nhiên có cam kết tương ứng. Xem [Collections.sort trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#sort(java.util.List,java.util.Comparator)).

~~~java
Collections.sort(values, byRank);
~~~

Hai cách gọi không có nghĩa giữ nguyên nguồn. Nếu cần giữ nguồn, tạo một danh sách mới:

~~~java
List<Entry> sorted = new ArrayList<>(source);
sorted.sort(byRank);
~~~

Cách này tạo một danh sách chứa các tham chiếu phần tử từ nguồn; không tự sao chép sâu từng đối tượng.

### Danh sách có hỗ trợ sort không?

Một danh sách không cho sửa đổi như kết quả `List.of(...)` không trở thành có thể sửa chỉ vì thao tác sort được cam kết ổn định.

~~~java
List<Integer> fixed = List.of(3, 1, 2);

// fixed.sort(Comparator.naturalOrder());
// Nếu chạy, lời gọi thay đổi này ném UnsupportedOperationException.
~~~

Không nên đồng nhất “kích thước cố định” với “không cho thay phần tử”. Ví dụ `Arrays.asList(...)` tạo danh sách có kích thước cố định nhưng hỗ trợ thay thế và sắp xếp; sự thay đổi phản ánh về mảng phía sau. Tính ổn định và khả năng chỉnh sửa là hai vấn đề độc lập cần đọc từ hợp đồng tương ứng.

## 4. compare bằng 0 không phải equals

Xét kiểu:

~~~java
// Khai báo kiểu dùng trong bài.
record Entry(String id, int rank) {}
~~~

Hai đối tượng:

~~~java
Entry first = new Entry("C", 2);
Entry second = new Entry("A", 2);
~~~

Record `equals` xét cả mã và hạng, nên hai đối tượng khác nhau. Comparator chỉ xét hạng vẫn trả `0`.

Khi sort ổn định theo hạng, C và A được xem là đồng hạng dù không `equals`. C đứng trước A nếu trước sort C đã đứng trước A.

### Ví dụ với BigDecimal

`BigDecimal` cho thấy sự phân biệt này với một kiểu có sẵn:

~~~java
BigDecimal first = new BigDecimal("1.0");
BigDecimal second = new BigDecimal("1.00");

System.out.println(first.equals(second));    // false
System.out.println(first.compareTo(second)); // 0
~~~

Hai giá trị có cùng độ lớn số học nhưng khác scale. Nếu sắp danh sách theo thứ tự tự nhiên, tính ổn định xét kết quả `compareTo == 0`, không xét `equals`.

Trong chương trình hoàn chỉnh ở dưới, thứ tự đầu vào của `1.0` và `1.00` được giữ; tương tự với `2.00` và `2.0`.

Không cần biến comparator thành `equals` mới sử dụng được cho sort danh sách. Tuy nhiên, nếu dùng cùng comparator cho `TreeSet` hoặc `TreeMap`, kết quả `0` còn ảnh hưởng tới ý nghĩa trùng phần tử hoặc tương đương khóa; đó là trách nhiệm phải xem xét riêng.

## 5. Stable sort giữ thứ tự nào?

Nó giữ thứ tự **ngay trước lời gọi sort đó**, không phải một lịch sử gốc mà chương trình không lưu.

Ví dụ:

1. Nhận dữ liệu theo thứ tự C, D, A, B, E.
2. Một thao tác khác sắp hoặc đảo danh sách.
3. Sau đó mới sort theo hạng.

Tính ổn định tại bước 3 bảo toàn thứ tự đồng hạng của danh sách sau bước 2.

Nếu nghiệp vụ muốn “đồng hạng thì ai đến trước đứng trước”, phải bảo đảm có thông tin đáng tin cậy về thứ tự tiếp nhận:

- Duy trì thứ tự tiếp nhận trong nguồn đầu vào của lần sort.
- Hoặc lưu một trường số thứ tự tiếp nhận, rồi dùng trường đó làm tiêu chí phụ.
- Nếu dùng thời điểm, xác định cách xử lý nhiều bản ghi cùng thời điểm.

Không tự coi mã định danh hoặc vị trí hiện tại là thời điểm tiếp nhận nếu mô hình dữ liệu không cam kết điều đó.

### Nguồn không cam kết thứ tự

Nếu tạo danh sách từ `HashSet` hoặc một truy vấn không có quy tắc thứ tự rõ ràng, đầu vào có thể có thứ tự khác giữa các lần xử lý.

Stable sort theo hạng sẽ giữ thứ tự đồng hạng mà nó nhận được trong từng lần. Nó không thể phục hồi lịch sử chèn đã mất hoặc tự đoán quy tắc sắp xếp mong muốn.

Không gọi sự thay đổi đó là “List.sort không ổn định” khi mỗi lần đầu vào khác nhau. Để kiểm tra tính ổn định, phải so với đúng dãy trước lần sort đang xét.

## 6. Chọn chính sách xử lý đồng hạng

Có ít nhất ba chính sách hợp lý, tùy yêu cầu:

| Chính sách | Khi phù hợp | Cách biểu đạt |
| --- | --- | --- |
| Giữ thứ tự hiện tại trong nhóm đồng hạng | Nguồn đã có trình tự có ý nghĩa và cần bảo toàn | Dùng comparator tiêu chí chính cùng stable sort. |
| Dùng tiêu chí phụ có ý nghĩa | Cần quy tắc rõ, độc lập với thứ tự đầu vào trong các nhóm hòa | Ghép `thenComparing` theo đúng thứ bậc. |
| Giữ cùng hạng nhưng tách quy tắc hiển thị | Các phần tử cần được xem là ngang hạng về nghiệp vụ nhưng vẫn cần trình tự trình bày | Dùng khóa phụ cho hiển thị, vẫn tính đồng hạng từ tiêu chí nghiệp vụ chính. |

### Giữ thứ tự hiện tại

~~~java
List<Entry> result = new ArrayList<>(source);
result.sort(Comparator.comparingInt(Entry::rank));
~~~

Không thêm tiêu chí mã nếu thứ tự trước sort là điều cần bảo toàn trong nhóm đồng hạng. Thêm mã sẽ thay đổi chính sách.

### Sắp mã tăng dần trong cùng hạng

~~~java
Comparator<Entry> displayOrder =
        Comparator.comparingInt(Entry::rank)
                .thenComparing(Entry::id);
~~~

Với nguồn C:2, D:1, A:2, B:1, E:2, kết quả trở thành:

~~~text
B:1, D:1, A:2, C:2, E:2
~~~

C và A không còn đồng hạng **theo comparator đầy đủ**, vì mã đã phân biệt chúng. Do đó việc A đứng trước C không vi phạm tính ổn định của sort.

Tính ổn định được áp dụng sau khi đã xét toàn bộ comparator, không chỉ khóa đầu tiên mà người viết chương trình đang chú ý.

### Cùng hạng nghiệp vụ không nhất thiết có cùng vị trí hiển thị

Hai thí sinh cùng điểm có thể phải cùng nhận hạng `1`, dù màn hình sắp tên tăng dần để dễ đọc. Nếu tính đồng hạng bằng comparator đã thêm tên hoặc ID, có thể vô tình biến hai người cùng điểm thành hai hạng khác nhau.

Hãy tách:

- Quy tắc xác định ngang hạng nghiệp vụ.
- Quy tắc chọn trình tự hiển thị.
- Quy tắc gán số hạng, nếu cần.

Sort không tự tính bảng xếp hạng kiểu `1, 1, 3` hoặc `1, 1, 2`. Những quy tắc đó là một bước xử lý khác.

## 7. Thứ tự giảm dần và bẫy reverse sau sort

Muốn hạng lớn hơn đứng trước nhưng giữ thứ tự tương đối trong nhóm đồng hạng:

~~~java
List<Entry> descending = new ArrayList<>(source);
descending.sort(byRank.reversed());
~~~

Từ dữ liệu mẫu, kết quả:

~~~text
C:2, A:2, E:2, D:1, B:1
~~~

Trong nhóm hạng `2`, C vẫn trước A trước E. Trong nhóm hạng `1`, D vẫn trước B.

Một cách tưởng tương đương là sort tăng rồi đảo cả danh sách:

~~~java
List<Entry> reversed = new ArrayList<>(source);
reversed.sort(byRank);
Collections.reverse(reversed);
~~~

Kết quả:

~~~text
E:2, A:2, C:2, B:1, D:1
~~~

`Collections.reverse` đảo cả trình tự của từng nhóm đồng hạng. Phép sort ban đầu vẫn ổn định; một thao tác khác sau đó đã đổi thứ tự tương đối.

Vì vậy:

~~~text
sort bằng comparator đảo chiều
~~~

không tương đương về chính sách đồng hạng với:

~~~text
sort bằng comparator ban đầu rồi reverse toàn bộ kết quả
~~~

Cần xác định muốn đổi chiều các nhóm hay muốn đảo mọi phần tử.

Khi có nhiều tiêu chí, vị trí `reversed()` cũng quan trọng. Đặt sau toàn bộ chuỗi comparator sẽ đảo cả tiêu chí chính lẫn tiêu chí phụ; đặt ngay sau comparator chính chỉ đảo phần chính đã tạo trước đó.

## 8. Sắp xếp nhiều lượt dựa trên tính ổn định

Giả sử muốn hạng tăng dần, trong cùng hạng thì mã tăng dần.

Một comparator biểu đạt trực tiếp:

~~~java
Comparator<Entry> order =
        Comparator.comparingInt(Entry::rank)
                .thenComparing(Entry::id);

values.sort(order);
~~~

Cũng có thể dùng nhiều lượt sort ổn định, từ tiêu chí ít quan trọng hơn đến tiêu chí quan trọng hơn:

~~~java
values.sort(Comparator.comparing(Entry::id));  // Tiêu chí phụ trước.
values.sort(Comparator.comparingInt(Entry::rank)); // Tiêu chí chính sau.
~~~

Lượt cuối tạo nhóm theo hạng. Do ổn định, trong nhóm cùng hạng nó giữ thứ tự mã đã hình thành ở lượt trước.

Không đổi hai dòng tùy ý:

~~~java
values.sort(Comparator.comparingInt(Entry::rank));
values.sort(Comparator.comparing(Entry::id));
~~~

Lần cuối lúc này ưu tiên mã trên toàn bộ danh sách. Nó không tự hiểu “chỉ sắp mã trong các nhóm đồng hạng”.

Kỹ thuật nhiều lượt dựa vào:

- Tính ổn định của các phép sort dùng để bảo toàn thứ tự phụ.
- Thứ tự áp dụng từ khóa ít quan trọng đến quan trọng.
- Dữ liệu và comparator không đổi ý nghĩa giữa các lượt.

Một chuỗi `thenComparing` thường giúp người đọc thấy thứ bậc rõ hơn. Biết kỹ thuật nhiều lượt vẫn hữu ích để hiểu stable sort thực sự bảo toàn thông tin nào.

## 9. Cần thứ tự gốc thì phải lưu trước khi làm mất nó

Trong một số luồng xử lý, danh sách đã trải qua nhiều lần biến đổi nhưng vẫn cần quay về chính sách “cùng hạng thì theo vị trí lúc tiếp nhận”.

Có thể gắn vị trí vào từng lần xuất hiện trước khi thay đổi thứ tự:

~~~java
// Minh họa các khai báo trong một lớp; Entry đã được định nghĩa.
record IndexedEntry(Entry value, int originalPosition) {}

List<IndexedEntry> tagged = new ArrayList<>();
for (int i = 0; i < source.size(); i++) {
    tagged.add(new IndexedEntry(source.get(i), i));
}

Comparator<IndexedEntry> order =
        Comparator.comparingInt(
                (IndexedEntry entry) -> entry.value().rank()
        ).thenComparingInt(IndexedEntry::originalPosition);

tagged.sort(order);
~~~

`originalPosition` chỉ có ý nghĩa đối với dãy `source` đã chọn ở thời điểm gắn nhãn. Nó không tự trở thành ID của thực thể hoặc số thứ tự toàn hệ thống.

Cách làm còn phân biệt được các lần xuất hiện khi cùng một đối tượng được đưa vào nguồn nhiều lần. Nếu chỉ gắn vị trí bằng một `Map<Entry, Integer>`, các phần tử `equals` nhau hoặc cùng đối tượng có thể bị gộp thông tin vị trí.

Nếu miền nghiệp vụ đã có số thứ tự tiếp nhận ổn định, nên dùng trường nghiệp vụ đó thay vì tạo lại từ một nguồn đã bị xáo trộn.

## 10. Đồng hạng tại ranh giới lấy N phần tử

Một quy tắc “lấy N phần tử đầu sau sort” chưa nói phải làm gì khi ranh giới cắt ngang nhóm đồng hạng.

Ví dụ đã sort theo hạng:

~~~text
D:1, B:1, C:2, A:2, E:2
~~~

Nếu lấy đúng `1` phần tử:

- Chính sách giới hạn đúng số lượng trả D.
- Chính sách lấy cả nhóm đồng hạng với phần tử cuối được chọn trả D và B.

Cả hai có thể hợp lý, nhưng phải được chỉ rõ.

Nếu dùng mã làm tiêu chí phụ để hiển thị mà vẫn muốn bao gồm mọi phần tử đồng hạng nghiệp vụ, cần xác định nhóm ở ranh giới theo comparator hạng chính, không theo comparator hiển thị đầy đủ. Nếu comparator đầy đủ phân biệt mọi ID, sẽ không còn nhóm hòa theo nó.

Với chính sách gồm cả nhóm ranh giới:

1. Sort theo quy tắc hiển thị được chọn.
2. Chọn ranh giới của số lượng ban đầu, nếu có dữ liệu.
3. Tiếp tục lấy các phần tử cùng hạng nghiệp vụ với phần tử ranh giới.
4. Xử lý rõ trường hợp N bằng `0`, N lớn hơn kích thước và đầu vào rỗng.

Tính ổn định hỗ trợ giữ một thứ tự trong nhóm; nó không tự lựa chọn chính sách phân trang, giới hạn số lượng hay trao hạng.

## 11. Chương trình hoàn chỉnh

Lưu thành **StableListSortDemo.java**. Ví dụ dùng các bản ghi có mã khác nhau để quan sát được thứ tự nội bộ của từng nhóm.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class StableListSortDemo {
    record Entry(String id, int rank) {}

    public static void main(String[] args) {
        List<Entry> source = List.of(
                new Entry("C", 2),
                new Entry("D", 1),
                new Entry("A", 2),
                new Entry("B", 1),
                new Entry("E", 2)
        );

        Comparator<Entry> byRank = Comparator.comparingInt(Entry::rank);

        List<Entry> ascending = new ArrayList<>(source);
        ascending.sort(byRank);
        System.out.println("Stable ascending = " + ids(ascending));

        List<Entry> usingCollections = new ArrayList<>(source);
        Collections.sort(usingCollections, byRank);
        System.out.println("Collections.sort = " + ids(usingCollections));

        List<Entry> descending = new ArrayList<>(source);
        descending.sort(byRank.reversed());
        System.out.println("Stable descending = " + ids(descending));

        List<Entry> reversedAfterSort = new ArrayList<>(ascending);
        Collections.reverse(reversedAfterSort);
        System.out.println("Ascending then reverse = "
                + ids(reversedAfterSort));

        List<Entry> explicitTieBreak = new ArrayList<>(source);
        explicitTieBreak.sort(byRank.thenComparing(Entry::id));
        System.out.println("Rank then id = " + ids(explicitTieBreak));

        List<Entry> multiPass = new ArrayList<>(source);
        multiPass.sort(Comparator.comparing(Entry::id));
        multiPass.sort(byRank);
        System.out.println("Id first, then stable rank = " + ids(multiPass));

        List<Entry> anotherInput = List.of(
                new Entry("B", 1),
                new Entry("D", 1),
                new Entry("E", 2),
                new Entry("A", 2),
                new Entry("C", 2)
        );
        List<Entry> anotherSorted = new ArrayList<>(anotherInput);
        anotherSorted.sort(byRank);
        System.out.println("Different input, rank only = "
                + ids(anotherSorted));
        anotherSorted.sort(byRank.thenComparing(Entry::id));
        System.out.println("Different input, rank then id = "
                + ids(anotherSorted));

        List<BigDecimal> amounts = new ArrayList<>(List.of(
                new BigDecimal("2.00"),
                new BigDecimal("1.0"),
                new BigDecimal("2.0"),
                new BigDecimal("1.00")
        ));
        amounts.sort(Comparator.naturalOrder());
        System.out.println("BigDecimal stable natural order = " + amounts);
        System.out.println("1.0 equals 1.00 = "
                + new BigDecimal("1.0").equals(new BigDecimal("1.00")));
        System.out.println("1.0 compareTo 1.00 = "
                + new BigDecimal("1.0").compareTo(new BigDecimal("1.00")));

        System.out.println("Original = " + ids(source));
    }

    private static List<String> ids(List<Entry> values) {
        List<String> result = new ArrayList<>();
        for (Entry value : values) {
            result.add(value.id());
        }
        return result;
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 StableListSortDemo.java
java StableListSortDemo
~~~

Stdout:

~~~text
Stable ascending = [D, B, C, A, E]
Collections.sort = [D, B, C, A, E]
Stable descending = [C, A, E, D, B]
Ascending then reverse = [E, A, C, B, D]
Rank then id = [B, D, A, C, E]
Id first, then stable rank = [B, D, A, C, E]
Different input, rank only = [B, D, E, A, C]
Different input, rank then id = [B, D, A, C, E]
BigDecimal stable natural order = [1.0, 1.00, 2.00, 2.0]
1.0 equals 1.00 = false
1.0 compareTo 1.00 = 0
Original = [C, D, A, B, E]
~~~

### Giải thích kết quả

**Stable ascending** và **Collections.sort**

Cùng tạo dãy D, B, C, A, E. Đây là hai nhóm hạng tăng dần, với thứ tự tương đối gốc được giữ trong mỗi nhóm.

**Stable descending**

C, A, E đứng trước D, B. Comparator đảo chiều nhóm nhưng các phần tử cùng hạng vẫn hòa nhau theo comparator đảo chiều, nên thứ tự trong nhóm được giữ.

**Ascending then reverse**

Kết quả đảo thành E, A, C, B, D. Thao tác đảo diễn ra sau sort và đảo luôn thứ tự nội bộ các nhóm.

**Rank then id**

Mã được dùng để giải quyết hòa, nên nhóm hạng `1` là B, D; nhóm hạng `2` là A, C, E. Đây là một yêu cầu khác với chỉ giữ trình tự đầu vào.

**Id first, then stable rank**

Sort mã trước rồi sort ổn định theo hạng cho cùng kết quả như comparator ghép. Thông tin thứ tự mã được giữ trong các nhóm của lần sort cuối.

**Different input, rank only**

Nguồn khác đã đặt B trước D và E trước A trước C. Stable sort đúng phải bảo toàn các trình tự đó trong nhóm, nên khác kết quả sort cùng tập bản ghi từ nguồn ban đầu.

**Different input, rank then id**

Khi thêm mã làm tiêu chí phụ, hai nguồn khác thứ tự nhưng chứa cùng các bản ghi cho cùng kết quả B, D, A, C, E trong ví dụ này.

**BigDecimal**

`1.0` trước `1.00`; `2.00` trước `2.0`, đúng theo thứ tự trước sort của các nhóm `compareTo == 0`. Dòng `equals` cho thấy hai số cùng độ lớn không nhất thiết `equals` nhau khi scale khác.

**Original**

Các phép sort dùng các bản sao có thể chỉnh sửa. Dữ liệu nguồn vẫn giữ C, D, A, B, E. Điều này đến từ cách tạo bản sao, không đến từ tính ổn định.

## 12. Kiểm thử tính ổn định đúng cách

Kiểm thử chỉ có các khóa khác nhau không thể phát hiện việc các phần tử đồng hạng bị đổi chỗ. Cần chủ động tạo dữ liệu có:

- Nhiều nhóm đồng hạng.
- Các phần tử cùng nhóm nằm xen kẽ với nhóm khác.
- Nhãn riêng để theo dõi từng lần xuất hiện.
- Trình tự nhãn không tự trùng với thứ tự mã tăng dần.

Dữ liệu C:2, D:1, A:2, B:1, E:2 trong bài được chọn để thấy rõ điều đó. Nếu dùng A:1, B:1, C:2, D:2 thì việc vô tình thêm tiêu chí mã có thể vẫn cho cùng kết quả, khiến kiểm thử bỏ sót lỗi chính sách.

Một kiểm tra đầy đủ cần tách ít nhất ba thuộc tính:

1. **Nội dung được bảo toàn:** không mất, không thêm hoặc lặp sai số lần phần tử.
2. **Thứ tự chính đúng:** hai phần tử kề nhau tuân theo comparator.
3. **Tính ổn định đúng:** với các phần tử so sánh bằng nhau, thứ tự tương đối trước sort được giữ.

Với các phần tử mang vị trí gốc riêng, sau sort có thể gom các phần tử bằng nhau theo comparator và kiểm tra vị trí gốc tăng dần trong từng nhóm.

Không viết kiểm thử ổn định bằng cách luôn yêu cầu ID tăng dần nếu comparator không xét ID. Đó là kiểm thử một quy tắc nghiệp vụ khác.

Cũng cần dữ liệu biên: đầu vào rỗng, một phần tử, tất cả đồng hạng, không có phần tử đồng hạng, và phần tử `null` nếu comparator lẫn danh sách cho phép. Comparator `nullsFirst` hoặc `nullsLast` quyết định vị trí `null`; sort ổn định không tự thêm khả năng xử lý `null` cho một comparator đang cấm nó.

## 13. Giới hạn và những suy luận không nên có

### Comparator sai thì stable sort không sửa được

Nếu comparator trừ hai số bị tràn, đổi kết quả theo thời gian hoặc không có tính bắc cầu, kết quả không có cơ sở để đáp ứng ý nghĩa mong muốn.

Một thuật toán có thể phát hiện một số vi phạm và ném ngoại lệ, nhưng việc không có ngoại lệ không chứng minh comparator hợp lệ. Khóa so sánh nên ổn định trong thời gian sort và quy tắc phải nhất quán.

### Ổn định không có nghĩa giữ nguyên chỉ số

Chỉ có thứ tự tương đối của cặp đồng hạng được giữ. Chỉ số thay đổi là hành vi bình thường của sắp xếp; không lưu chỉ số như định danh lâu dài của một thực thể.

### Ổn định không phải thuộc tính chung của mọi cấu trúc có thứ tự

Không từ cam kết của `List.sort` suy ra mọi thuật toán hoặc cấu trúc khác đều xử lý hòa theo cách tương tự. Chẳng hạn, không dựa vào `PriorityQueue` để tự giữ FIFO giữa mọi phần tử cùng mức ưu tiên; nếu cần FIFO trong nhóm, phải có chính sách và tiêu chí thích hợp.

### Ổn định không duy trì mãi trạng thái đã sort

Sau sort, thêm phần tử mới vào cuối hoặc thay đổi khóa trong đối tượng có thể khiến dãy không còn đúng thứ tự. `List` không tự sắp xếp lại mỗi khi dữ liệu thay đổi.

### Ổn định không khắc phục dữ liệu nguồn thay đổi

Nếu các bản ghi hoặc tập dữ liệu thay đổi giữa các lần đọc, kết quả có thể thay đổi dù comparator đầy đủ và phép sort đều đúng. Khi cần một báo cáo tái lập, phải xác định cả ảnh chụp dữ liệu và phiên bản quy tắc, không chỉ thêm một lời gọi sort.

## 14. Lỗi thường gặp

| Hiểu nhầm | Cách hiểu cần giữ |
| --- | --- |
| Stable sort không thay đổi vị trí phần tử | Nó giữ thứ tự tương đối trong nhóm đồng hạng; chỉ số vẫn có thể đổi. |
| Đồng hạng nghĩa là `equals` nhau | Với sort, đồng hạng được quyết định bởi comparator hoặc thứ tự tự nhiên. |
| Stable sort luôn tạo kết quả giống nhau từ cùng một tập dữ liệu | Nếu nguồn có trình tự khác nhau và còn nhóm hòa, kết quả trong nhóm có thể khác. |
| Thêm ID vẫn phải giữ thứ tự cũ của mọi phần tử cùng điểm | Sau khi thêm ID, các phần tử khác ID có thể không còn hòa theo comparator đầy đủ. |
| Sort tăng rồi reverse tương đương sort giảm ổn định | Reverse đảo cả thứ tự nội bộ các nhóm. |
| Sort chính rồi sort phụ là sắp nhiều tiêu chí | Lần sort cuối tác động toàn bộ dãy; muốn dùng nhiều lượt ổn định phải áp dụng từ phụ đến chính. |
| Dùng TreeSet thay cho List đã sort sẽ giữ mọi phần tử | Comparator trả `0` trong TreeSet có thể làm những phần tử bị xem là cùng một vị trí. |
| `limit(N)` hoặc lấy N phần tử sẽ tự bao gồm mọi người cùng hạng | Chính sách ở ranh giới phải được thiết kế riêng. |

## 15. Thực hành

1. Tự viết kết quả tăng và giảm ổn định cho dãy `X:3, A:1, B:3, C:1, D:3`.
2. Thêm tiêu chí mã tăng dần. Chỉ rõ các cặp trước đây đồng hạng nhưng nay không còn hòa theo comparator đầy đủ.
3. So sánh sort giảm trực tiếp với sort tăng rồi reverse; khoanh những cặp cùng hạng bị đảo.
4. Tạo hai nguồn có cùng tập bản ghi nhưng khác trình tự trong nhóm hạng. Kiểm chứng stable sort theo hạng cho các kết quả khác nhau nhưng đều đúng.
5. Chọn chính sách “hạng bằng nhau thì theo thứ tự tiếp nhận”. Thiết kế nguồn dữ liệu hoặc trường số thứ tự để giữ được ý nghĩa đó qua nhiều bước xử lý.
6. Với yêu cầu lấy ba phần tử đầu, tạo dữ liệu có nhóm đồng hạng cắt ngang vị trí thứ ba. Viết rõ hai kết quả theo chính sách giới hạn đúng số lượng và chính sách bao gồm cả nhóm.
7. Viết kiểm tra tính ổn định dùng vị trí gốc riêng của từng lần xuất hiện, rồi thử dữ liệu có các đối tượng `equals` nhau hoặc cùng đối tượng xuất hiện nhiều lần.

Trước mỗi yêu cầu sắp xếp có đồng hạng, hãy xác định thế nào là hòa, cần giữ trình tự nào trong nhóm và có cần một quy tắc hiển thị phụ hay không. Tính ổn định của `List.sort` là công cụ để thực hiện chính sách đã chọn, không thay thế việc chọn chính sách.
