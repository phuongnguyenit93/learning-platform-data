# ORDERED, SIZED, SUBSIZED, SORTED và DISTINCT trong Java Spliterator

## 1. Bối cảnh: nguồn tùy chỉnh và hợp đồng của Spliterator

Trong Java Stream API, một **Spliterator<T>** là giao diện duyệt và có thể chia nhỏ nguồn dữ liệu để xử lý tuần tự hoặc song song. Nó cung cấp các phương thức như **tryAdvance**, **forEachRemaining**, **trySplit**, **estimateSize** và **characteristics**. Nếu tự xây nguồn Stream bằng **StreamSupport.stream(spliterator, parallel)**, lập trình viên cần mô tả trung thực những đặc tính của nguồn thông qua **bit flags** gọi là *Spliterator characteristics*.

Năm cờ quan trọng trong bài này:

- **ORDERED**: có thứ tự gặp (encounter order) xác định.
- **SIZED**: kích thước nguồn được biết chính xác theo hợp đồng tại những thời điểm được quy định.
- **SUBSIZED**: các spliterator được tạo khi chia nguồn cũng duy trì hợp đồng SIZED và SUBSIZED.
- **SORTED**: phần tử được duyệt theo một thứ tự sắp xếp đã xác định.
- **DISTINCT**: không có hai phần tử được duyệt mà bằng nhau theo quy tắc nhận diện trùng của đặc tính này.

Các cờ này **không phải thao tác xử lý dữ liệu**. Chúng là lời hứa về hành vi nguồn để Stream API có thể đưa ra kết quả đúng và thực hiện tối ưu an toàn.

Ví dụ, một mảng **[5, 1, 5]** có thể có encounter order rất rõ (theo chỉ số) và kích thước chính xác 3, nhưng nó **không SORTED** và **không DISTINCT**. Không được gắn thêm SORTED hoặc DISTINCT chỉ vì muốn Stream chạy nhanh.

### 1.1. Vì sao nguồn tùy chỉnh đặc biệt cần chính xác?

Khi Java cung cấp Spliterator của các collection tiêu chuẩn, phần lớn hợp đồng đã do thư viện thiết lập. Nhưng khi tự tạo Spliterator đọc dữ liệu từ mảng, một khoảng số, một tập kết quả hoặc một cấu trúc riêng, ta phải quyết định:

1. Thứ tự duyệt có được xác định trước không?
2. Kích thước có được biết chính xác không?
3. Nếu chia đôi, hai nguồn con còn có kích thước chính xác không?
4. Phần tử có thật sự được phát theo một thứ tự so sánh ổn định không?
5. Dữ liệu có thể xuất hiện giá trị trùng không?

Nếu câu trả lời thay đổi sau khi nguồn bị lọc, thêm/xóa dữ liệu hoặc chia nhánh, các cờ phải phản ánh đúng hợp đồng ở thời điểm thích hợp. **Khai báo thừa khả năng có thể gây kết quả sai**, chứ không chỉ gây lãng phí tài nguyên.

## 2. Năm đặc tính đặt cạnh nhau

| Đặc tính | Ý nghĩa hứa với caller | Ví dụ phù hợp | Ngộ nhận cần tránh |
| --- | --- | --- | --- |
| **ORDERED** | Có encounter order được định nghĩa | Spliterator duyệt List theo chỉ số | ORDERED không có nghĩa tăng dần |
| **SIZED** | estimateSize cung cấp số phần tử chính xác khi hợp đồng SIZED áp dụng | Snapshot mảng cố định | Không phải chỉ là ước lượng gần đúng |
| **SUBSIZED** | Mọi split tạo ra cũng SIZED và SUBSIZED | Chia dải chỉ số có độ dài biết trước | Có SIZED không tự suy ra SUBSIZED |
| **SORTED** | Duyệt theo natural order hoặc Comparator do Spliterator công bố | Dải int tăng dần | SORTED không tự suy ra DISTINCT |
| **DISTINCT** | Các phần tử không trùng theo equals | Dải số nguyên không lặp | DISTINCT không có nghĩa được sắp xếp |

Hai quan hệ quan trọng:

- **SORTED bao hàm ORDERED**: nếu phần tử được phát theo thứ tự sắp xếp, có một encounter order phù hợp.
- **SUBSIZED bao hàm SIZED**: không thể hứa mỗi split đều có kích thước chính xác khi chính spliterator hiện tại không duy trì SIZED.

Ngược lại:

- ORDERED **không** bao hàm SORTED.
- SIZED **không** bao hàm SUBSIZED.
- SORTED và DISTINCT là **hai khái niệm độc lập**: dữ liệu có thể sắp xếp mà vẫn trùng hoặc không trùng mà vẫn lộn xộn.

Java dùng **các bit của một số int** để biểu diễn những đặc tính này. Cách biểu diễn bit giúp kết hợp nhiều lời hứa trong một giá trị mà không cần một đối tượng metadata riêng.

## 3. Kiểm tra đặc tính bằng hasCharacteristics và characteristics

Một Spliterator cung cấp:

~~~java
int flags = spliterator.characteristics();

boolean ordered =
        spliterator.hasCharacteristics(Spliterator.ORDERED);
~~~

Đây là đoạn minh họa, giả định đã có biến **spliterator** và import **java.util.Spliterator**.

Có thể kiểm tra nhiều cờ cùng lúc:

~~~java
boolean exactOrderedSize = spliterator.hasCharacteristics(
        Spliterator.ORDERED | Spliterator.SIZED);
~~~

Biểu thức trả true khi **cả hai cờ** có mặt. Cần phân biệt **toán tử bitwise OR (|)** dùng để kết hợp flags với **toán tử OR logic (||)** dùng để kết hợp điều kiện boolean.

Tương đương về mặt kiểm tra:

~~~java
int mask = Spliterator.ORDERED | Spliterator.SIZED;

boolean hasBoth =
        (spliterator.characteristics() & mask) == mask;
~~~

Đoạn minh họa cần import Spliterator; toán tử **&** bitwise giữ lại các bit chung.

**Không kiểm tra bằng phép so sánh characteristics() == ORDERED** khi cần biết có ORDERED hay không. Một spliterator hợp lệ thường có **nhiều cờ** cùng lúc, nên giá trị tổng không nhất thiết bằng riêng một cờ.

### 3.1. getExactSizeIfKnown và estimateSize

Hai phương thức dễ nhầm:

- **estimateSize()** trả một giá trị long mô tả số phần tử còn lại ước lượng; nếu nguồn SIZED thì kích thước được biết chính xác theo hợp đồng SIZED.
- **getExactSizeIfKnown()** trả kích thước chính xác dựa vào estimateSize nếu spliterator có **SIZED**; nếu không có SIZED, trả **-1**.

~~~java
long estimate = spliterator.estimateSize();
long exact = spliterator.getExactSizeIfKnown();
~~~

Đây là đoạn minh họa.

**Lưu ý:** estimateSize có thể trả **Long.MAX_VALUE** khi không có giới hạn hoặc không biết kích thước; điều đó **không** có nghĩa nguồn thực sự có chính xác Long.MAX_VALUE phần tử. Không tự diễn giải ước lượng thành chứng cứ để cấp phát một mảng kích thước tương ứng.

## 4. ORDERED: encounter order không phải sorted order

**Encounter order** là thứ tự phần tử được xác định bởi nguồn và các thao tác bảo toàn thứ tự. Một List có thứ tự gặp theo chỉ số; một TreeSet được duyệt theo thứ tự sắp xếp; còn một HashSet không hứa thứ tự gặp ổn định qua các cách chạy.

Ví dụ:

~~~text
Dữ liệu: [9, 2, 9, 4]

Có ORDERED: có thể phải phát theo [9, 2, 9, 4].
Không SORTED: 9 nằm trước 2 không phải tăng dần.
Không DISTINCT: giá trị 9 xuất hiện hai lần.
~~~

Khi Stream có ORDERED:

- **findFirst()** mang nghĩa phần tử đầu tiên theo encounter order, nếu có.
- **limit(n)** trên ordered stream chọn prefix n phần tử.
- **skip(n)** bỏ n phần tử đầu.
- **forEachOrdered()** tôn trọng encounter order của Stream.
- **sorted()** có thể áp đặt một thứ tự mới, khác encounter order nguồn.
- **distinct()** của ordered stream ổn định theo lần gặp đầu tiên đối với các giá trị tương đương theo equals.

**Không được coi ORDERED là yêu cầu phải chạy tuần tự.** Parallel Stream vẫn có thể xuất kết quả theo encounter order cho những terminal operation cần bảo toàn nó, dù các phần việc được xử lý ở nhiều thread.

### 4.1. ORDERED và nguồn được chia

Với một Spliterator ORDERED tự triển khai, **trySplit()** cần tôn trọng cách chia tương thích với encounter order. Thông thường, spliterator được trả về từ trySplit đại diện **prefix** của các phần tử còn lại và spliterator gốc giữ **suffix**.

Ví dụ dải 1..8 được chia ở 5:

~~~text
Before:  [1, 2, 3, 4, 5, 6, 7, 8]
Returned split: [1, 2, 3, 4]
Original remainder: [5, 6, 7, 8]
~~~

Nếu ngẫu nhiên lấy các phần tử đầu-cuối xen kẽ rồi báo ORDERED mà không đáp ứng hợp đồng chia, một parallel terminal operation giữ thứ tự có thể tạo kết quả khác mong muốn.

### 4.2. Khi nào không nên gắn ORDERED?

Nếu cấu trúc nguồn không có thứ tự gặp có ý nghĩa, gắn ORDERED tạo một lời hứa giả. Ví dụ khi lấy dữ liệu từ một tập hợp không xác định thứ tự, thứ tự tình cờ quan sát trong một lần chạy **không phải hợp đồng** cho các lần chạy khác.

Ngược lại, nếu thứ tự nguồn có ý nghĩa nghiệp vụ, đừng tùy tiện gọi **unordered()** để tăng tốc rồi vẫn mong **findFirst()/limit()** chọn đúng những phần tử đầu tiên theo yêu cầu trước đó.

## 5. SIZED: độ lớn chính xác khác với ước lượng gần đúng

**SIZED** nói rằng estimateSize của spliterator cung cấp số phần tử chính xác theo hợp đồng trước khi duyệt hoặc chia. Điều này rất hữu ích khi nguồn là:

- Mảng cố định với số vị trí đã biết.
- Một dải chỉ số [start,end) hữu hạn.
- Một snapshot collection có kích thước cố định trong suốt quá trình duyệt.
- Một cấu trúc tùy chỉnh có thể tính chính xác số phần tử còn lại và cập nhật khi tryAdvance.

Ví dụ nguồn gồm 6 phần tử không có bộ lọc nội bộ:

~~~text
estimateSize() = 6
getExactSizeIfKnown() = 6
SIZED = true
~~~

Nếu nguồn có thể bất ngờ loại phần tử trong khi tryAdvance, hoặc phụ thuộc vào số bản ghi hợp lệ không thể biết trước, **không thể gắn SIZED chỉ vì đã biết số bản ghi gốc**.

### 5.1. Trường hợp không nên khai báo SIZED

Giả sử nguồn đọc từng bản ghi và bỏ những bản ghi bị lỗi. Ban đầu có 100 dòng vật lý, nhưng sau xử lý chỉ có 83 record hợp lệ. Nếu Spliterator chỉ **phát 83 phần tử**, nó không được quảng cáo SIZED=100.

Một nguồn vô hạn hoặc chưa xác định điểm kết thúc có thể không biết số lượng chính xác. Khi đó hãy báo **ước lượng trung thực** và không gắn SIZED. Với nguồn không biết số phần tử, estimateSize thường có thể dùng Long.MAX_VALUE, nhưng caller không nên coi đó là độ dài thật.

**Không suy luận SIZED từ kiểu trả về Collection trong mã nguồn** nếu collection có thể thay đổi trong khi duyệt và chưa có hợp đồng snapshot/binding rõ. Với một số collection chuẩn, Spliterator có cơ chế late-binding hoặc fail-fast; đó là chi tiết hợp đồng của từng nguồn, không được áp dụng tùy tiện cho custom Spliterator.

### 5.2. SIZED và Stream.count()

Nếu nguồn và pipeline giữ được thông tin kích thước chính xác, Stream có thể trả kết quả **count()** mà không cần duyệt mọi phần tử. Vì vậy:

~~~java
long count = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();
~~~

Đây là đoạn minh họa. **count** vẫn là 3, nhưng **không có bảo đảm** action của peek chạy ba lần. Với nguồn có SIZED, Java có thể tối ưu việc đếm khi các thao tác khác không đổi số phần tử.

**Không dùng side effect trong map/peek/filter làm công việc bắt buộc** chỉ vì dự định kết thúc bằng count().

## 6. SUBSIZED: lời hứa mạnh hơn SIZED khi tách nhánh

**SUBSIZED** nghĩa là **mọi Spliterator thu được bằng cách chia từ Spliterator này đều SIZED và SUBSIZED**. Đây là lời hứa rất phù hợp với nguồn có thể chia thành các khoảng chỉ số chính xác.

Ví dụ một mảng tám phần tử được chia đôi:

~~~text
Original size = 8
trySplit() -> prefix size = 4
Original remainder size = 4
Both continue to report exact size.
Each half may split again into sizes 2 + 2.
~~~

Với trường hợp đó, **SIZED|SUBSIZED** cho biết toàn bộ hệ thống nhánh có kích thước biết trước. Nó giúp Stream framework định vị, phân chia công việc và lập kế hoạch cấp phát trong các tình huống thích hợp.

**Có SIZED nhưng không SUBSIZED** là hợp lệ. Chẳng hạn, Spliterator biết tổng số phần tử tại thời điểm đầu nhưng cơ chế tách làm kích thước nhánh không dễ xác định chính xác. Không nên gắn SUBSIZED nếu mỗi nhánh không thể giữ lời hứa.

### 6.1. Tính lại kích thước sau trySplit

Một custom Spliterator phải cập nhật trạng thái nội bộ khi chia nguồn. Nếu trước khi split còn 10 phần tử và trySplit tạo prefix 4 phần tử, spliterator gốc phải ước lượng đúng **6** phần tử còn lại nếu nó tiếp tục báo SIZED.

Không được dùng cùng một giá trị kích thước ban đầu cho **cả hai nhánh**, vì như vậy tổng số phần tử ảo có thể bị nhân đôi. Kiểu lỗi này đôi khi không lộ ở chạy tuần tự nhưng gây hành vi sai khi chuyển sang parallel.

### 6.2. SUBSIZED không có nghĩa các nhánh luôn bằng nhau

Một dải có 7 phần tử có thể chia thành 3 và 4. **SUBSIZED chỉ hứa kích thước mỗi nhánh chính xác**, không hứa hai nhánh bằng nhau hay trySplit phải tạo được split trong mọi hoàn cảnh.

**trySplit()** có thể trả **null** khi không còn cách chia hữu ích, kể cả Spliterator có SUBSIZED. Đây không phải vi phạm hợp đồng.

## 7. SORTED: thứ tự so sánh và getComparator()

**SORTED** là lời hứa phần tử được duyệt theo thứ tự đã quy định. Một Spliterator SORTED cũng phải mang **ORDERED**.

Hai trường hợp:

1. **Thứ tự tự nhiên**: các phần tử có thể được so sánh theo natural ordering. Khi Spliterator báo SORTED và dùng natural order, **getComparator() trả null**.
2. **Comparator tùy chỉnh**: khi Spliterator báo SORTED theo Comparator được chọn, **getComparator() trả Comparator đó**.

Nếu Spliterator **không báo SORTED**, gọi **getComparator()** phải ném **IllegalStateException** theo hợp đồng của phương thức. Với custom Spliterator, phải triển khai getComparator() phù hợp nếu công bố SORTED.

Ví dụ sử dụng trên một Spliterator đã có:

~~~java
if (spliterator.hasCharacteristics(Spliterator.SORTED)) {
    Comparator<? super String> cmp =
            spliterator.getComparator();
    if (cmp == null) {
        System.out.println("Natural ordering");
    } else {
        System.out.println("Custom comparator");
    }
}
~~~

Đây là đoạn minh họa giả định spliterator là Spliterator<String> và đã import Comparator, Spliterator.

**Không tự suy ra getComparator()==null nghĩa là không sắp xếp.** Với một Spliterator SORTED theo natural order, null chính là kết quả hợp lệ.

### 7.1. Sort không có nghĩa các phần tử là duy nhất

Dãy **[1, 1, 2, 3]** có thể:

- **SORTED = true** vì thứ tự tăng không giảm.
- **DISTINCT = false** vì có hai số 1.

Cùng lúc, dãy **[3, 1, 2]** có thể:

- **SORTED = false**.
- **DISTINCT = true** vì ba giá trị khác nhau.

Do đó đừng thay thế SORTED bằng DISTINCT, cũng đừng gắn DISTINCT chỉ vì đã gọi sort.

### 7.2. Comparator phải ổn định

Nếu comparator dựa vào thời gian, random hoặc trường mutable thay đổi trong lúc duyệt, thứ tự có thể không còn ổn định. Khi Spliterator công bố SORTED, caller có quyền dựa vào lời hứa về thứ tự, nên comparator và dữ liệu phải thực sự phù hợp.

**Lưu ý:** Nếu nguồn được sắp xếp bởi một comparator không đồng nhất với equals, hành vi tập hợp và DISTINCT có thể khó suy luận; đừng giả định hai phần tử được coi bằng nhau theo comparator cũng nhất thiết bằng nhau theo equals. Cần xác định chính xác semantics loại trùng theo yêu cầu ứng dụng.

## 8. DISTINCT: dựa vào equals chứ không dựa vào vị trí hay sort

Theo hợp đồng **Spliterator.DISTINCT**, với mọi hai phần tử x và y được phát, **không được tồn tại một cặp mà x.equals(y) trả true** (theo ngữ nghĩa phần tử mà nguồn công bố). Với các object dữ liệu, cần hiểu đúng `equals` và tính ổn định của giá trị.

Ví dụ:

~~~text
["A", "B", "C"]  -> DISTINCT true, SORTED có thể true/false
["A", "B", "A"]  -> DISTINCT false
[1, 2, 3]       -> DISTINCT true
[1, 1, 2]       -> DISTINCT false
~~~

Một tập hợp **Set** về ý định thường loại phần tử trùng, nhưng không nên thiết kế custom Spliterator dựa vào Set hoặc comparator mơ hồ rồi khai báo DISTINCT mà chưa xác nhận **quan hệ equals của các phần tử phát ra**.

### 8.1. Vì sao lời hứa DISTINCT ảnh hưởng hiệu quả?

Nếu nguồn đã cam kết DISTINCT, bước Stream **distinct()** có thể không cần làm thêm công việc nhận diện trùng trong một số trường hợp. Điều này cho phép tối ưu, nhưng cũng tạo nguy cơ: **khai báo DISTINCT sai** có thể khiến một phép distinct downstream không loại hết các phần tử trùng.

Không nên khai báo DISTINCT “để tăng tốc”. Chỉ khai báo khi nguồn thực sự không thể phát hai phần tử bằng nhau.

### 8.2. Equality của phần tử mutable

Nếu một phần tử được phát rồi bị thay đổi các trường tham gia equals/hashCode, quy tắc distinct có thể không còn ổn định. Một nguồn tùy chỉnh nên tránh dữ liệu mutable biến đổi trong lúc duyệt, hoặc cần một hợp đồng snapshot/định danh phù hợp.

**DISTINCT khác UNIQUE KEY trong database:** một truy vấn có thể có primary key khác nhau nhưng trả các object bằng nhau theo equals nếu phương thức equals không xét primary key. Phải phân biệt định danh nghiệp vụ với equality Java.

## 9. Ví dụ Java 17 chạy được: mảng có ORDERED/SIZED/SUBSIZED nhưng không SORTED/DISTINCT

Tạo tệp **ArraySpliteratorFlagsDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class ArraySpliteratorFlagsDemo {
    public static void main(String[] args) {
        int[] input = {4, 2, 4};

        Spliterator.OfInt spliterator =
                Spliterators.spliterator(
                        input, Spliterator.ORDERED);

        System.out.println("ORDERED="
                + spliterator.hasCharacteristics(Spliterator.ORDERED));
        System.out.println("SIZED="
                + spliterator.hasCharacteristics(Spliterator.SIZED));
        System.out.println("SUBSIZED="
                + spliterator.hasCharacteristics(Spliterator.SUBSIZED));
        System.out.println("SORTED="
                + spliterator.hasCharacteristics(Spliterator.SORTED));
        System.out.println("DISTINCT="
                + spliterator.hasCharacteristics(Spliterator.DISTINCT));
        System.out.println("exact="
                + spliterator.getExactSizeIfKnown());

        int[] values = StreamSupport.intStream(spliterator, false)
                .toArray();
        System.out.println("values=" + Arrays.toString(values));
    }
}
~~~

Biên dịch và chạy (JDK 17):

~~~bash
javac ArraySpliteratorFlagsDemo.java
java ArraySpliteratorFlagsDemo
~~~

Stdout:

~~~text
ORDERED=true
SIZED=true
SUBSIZED=true
SORTED=false
DISTINCT=false
exact=3
values=[4, 2, 4]
~~~

**Giải thích:**

- **Spliterators.spliterator(int[], characteristics)** cung cấp một Spliterator theo thứ tự chỉ số, kích thước chính xác và khả năng chia theo vùng mảng; SIZED và SUBSIZED được báo cùng đặc tính nguồn mảng.
- Mảng đầu vào **không được sắp xếp**, và có hai phần tử 4 trùng. Vì vậy không gắn SORTED hay DISTINCT.
- **getExactSizeIfKnown()** trả 3 trước khi tiêu thụ stream.
- StreamSupport nhận Spliterator và tạo **IntStream**; `toArray()` giữ ba giá trị theo encounter order.
- Sau khi stream tiêu thụ Spliterator, không nên tái sử dụng Spliterator đó như thể nó còn nguyên dữ liệu.

**Đặc biệt:** API Spliterators.spliterator nhận một bitmask additionalCharacteristics. Không được truyền SORTED hoặc DISTINCT nếu mảng không đáp ứng; Java không tự quét mảng để chứng minh hai lời hứa ấy.

## 10. Ví dụ Java 17: custom Spliterator cho dải int tăng dần

Một khoảng nguyên **[start,end)**, tức start inclusive và end exclusive, là ví dụ phù hợp để tự triển khai cả năm cờ. Khi start <= end và mỗi số chỉ được phát một lần, dải có:

- ORDERED: từ nhỏ đến lớn.
- SIZED: số lượng còn lại bằng end - cursor.
- SUBSIZED: chia đoạn chỉ số vẫn cho kích thước chính xác.
- SORTED: natural ordering của Integer tăng dần.
- DISTINCT: mỗi số được phát đúng một lần.

Thêm **NONNULL** vì phần tử là int primitive (khi boxed cũng có giá trị không null), và **IMMUTABLE** vì các giới hạn được giữ trong instance độc lập, không đọc từ collection mutable bên ngoài.

Tạo tệp **CustomRangeSpliteratorDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class CustomRangeSpliteratorDemo {
    static final class RangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            this.cursor = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            if (cursor >= fence) {
                return false;
            }
            int current = cursor++;
            action.accept(current);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            long remaining = estimateSize();
            if (remaining < 2L) {
                return null;
            }

            int oldStart = cursor;
            int midpoint = (int) (cursor + remaining / 2L);
            cursor = midpoint;
            return new RangeSpliterator(oldStart, midpoint);
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED
                    | SORTED | DISTINCT | NONNULL | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            return null; // SORTED theo natural ordering.
        }
    }

    public static void main(String[] args) {
        RangeSpliterator remainder = new RangeSpliterator(1, 9);
        Spliterator.OfInt prefix = remainder.trySplit();

        System.out.println("prefix size="
                + prefix.getExactSizeIfKnown());
        System.out.println("remainder size="
                + remainder.getExactSizeIfKnown());

        int[] left = StreamSupport.intStream(prefix, false).toArray();
        int[] right = StreamSupport.intStream(remainder, false).toArray();

        System.out.println("prefix=" + Arrays.toString(left));
        System.out.println("remainder=" + Arrays.toString(right));

        RangeSpliterator all = new RangeSpliterator(1, 9);
        System.out.println("sorted="
                + all.hasCharacteristics(Spliterator.SORTED));
        System.out.println("natural="
                + (all.getComparator() == null));

        int sum = StreamSupport.intStream(
                new RangeSpliterator(1, 9), true).sum();
        System.out.println("parallel sum=" + sum);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CustomRangeSpliteratorDemo.java
java CustomRangeSpliteratorDemo
~~~

Stdout:

~~~text
prefix size=4
remainder size=4
prefix=[1, 2, 3, 4]
remainder=[5, 6, 7, 8]
sorted=true
natural=true
parallel sum=36
~~~

### 10.1. Phân tích trySplit chính xác

Với [1,9), có tám số từ 1 đến 8. **estimateSize()** ban đầu trả 8. **trySplit()** tính midpoint = 1 + 8/2 = 5 và trả một Spliterator mới [1,5). Spliterator gốc chuyển cursor sang 5, nên giữ [5,9).

Hai Spliterator đều có kích thước đúng 4 và đều giữ ORDERED, SIZED, SUBSIZED, SORTED, DISTINCT. Khi duyệt prefix trước remainder, thứ tự gặp toàn bộ là 1..8.

Sau khi chia, mỗi nhánh lại có thể chia tiếp thành các đoạn nhỏ mà vẫn chính xác. Đây là lý do tự nhiên để khai báo SUBSIZED.

### 10.2. Vì sao dùng long cho estimateSize?

Vì chênh lệch giữa hai số int ở hai đầu miền có thể vượt **Integer.MAX_VALUE**. Ép hai toán hạng sang long trước khi trừ:

~~~java
return (long) fence - cursor;
~~~

giúp tính độ dài của một dải trong miền int mà không tràn khi phép trừ xảy ra. Midpoint tính bằng toán học long rồi mới ép sang int, và nằm giữa hai giới hạn hợp lệ.

**Không có phép kiểm tra tự động** rằng caller sử dụng dải quá lớn sẽ phù hợp với bộ nhớ. Ví dụ **toArray()** trên một dải lớn có thể không cấp phát được; các flag chỉ mô tả tính chất, không bảo đảm đủ tài nguyên.

### 10.3. Vì sao phải override getComparator?

Spliterator.OfInt có thể kế thừa hành vi mặc định ném IllegalStateException khi được hỏi Comparator. Một custom Spliterator đã công bố **SORTED** phải cung cấp nghĩa của getComparator. Trong ví dụ natural ordering, trả null.

**Không thay return null bằng một Comparator ngẫu nhiên** chỉ để tránh exception. Nếu công bố natural ordering, hãy chắc chắn nguồn thực sự phát các giá trị theo natural order.

### 10.4. Vì sao custom Spliterator này không sử dụng nguồn mutable ngoài?

Cặp số **cursor/fence** thuộc instance của Spliterator; đây là trạng thái duyệt hợp lệ. **IMMUTABLE** trong ngữ cảnh này nói về nguồn dữ liệu mà Spliterator dựa vào, không phải tuyên bố con trỏ duyệt không bao giờ thay đổi. Spliterator cần cập nhật cursor khi phát hoặc chia phần tử.

Hợp đồng Spliterator không tự làm một instance an toàn để nhiều thread đồng thời gọi tryAdvance hoặc trySplit mà không phối hợp; Stream framework chịu trách nhiệm sử dụng/partition theo hợp đồng. Không nên chia sẻ trực tiếp cùng instance cho nhiều thread và tự ý gọi đồng thời.

## 11. TreeSet: SORTED với comparator tùy chỉnh

Một nguồn SORTED không bắt buộc dùng natural order. **TreeSet** là ví dụ tiêu biểu cho sorted collection có thể nhận Comparator.

Tạo tệp **SortedComparatorDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Spliterator;
import java.util.TreeSet;

public class SortedComparatorDemo {
    public static void main(String[] args) {
        Comparator<String> byLengthThenText =
                Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder());

        TreeSet<String> words = new TreeSet<>(byLengthThenText);
        words.addAll(List.of("pear", "fig", "kiwi", "apple", "fig"));

        Spliterator<String> spliterator = words.spliterator();

        System.out.println("ORDERED="
                + spliterator.hasCharacteristics(Spliterator.ORDERED));
        System.out.println("SORTED="
                + spliterator.hasCharacteristics(Spliterator.SORTED));
        System.out.println("DISTINCT="
                + spliterator.hasCharacteristics(Spliterator.DISTINCT));

        Comparator<? super String> comparator =
                spliterator.getComparator();
        System.out.println("custom=" + (comparator != null));
        System.out.println("words=" + words);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SortedComparatorDemo.java
java SortedComparatorDemo
~~~

Stdout:

~~~text
ORDERED=true
SORTED=true
DISTINCT=true
custom=true
words=[fig, kiwi, pear, apple]
~~~

**Giải thích:**

1. Comparator so độ dài trước, sau đó so theo thứ tự tự nhiên khi bằng độ dài.
2. "fig" (3 ký tự) đứng trước "kiwi" và "pear" (4 ký tự); "kiwi" trước "pear" theo chữ cái; "apple" (5 ký tự) cuối.
3. TreeSet chỉ giữ một bản sao "fig", nên nguồn này có các phần tử riêng biệt theo hợp đồng Set.
4. Spliterator của TreeSet báo SORTED và ORDERED; **getComparator()** trả Comparator đã dùng thay vì null.
5. Nếu dùng TreeSet không truyền comparator và phần tử có natural ordering, getComparator() trả null.

**Lưu ý thiết kế:** TreeSet quyết định các phần tử được coi là trùng bằng quan hệ so sánh. Comparator ở ví dụ dùng độ dài **kèm thứ tự tự nhiên** để tránh việc hai String khác nhau nhưng cùng độ dài bị coi là trùng. Nếu comparator chỉ theo độ dài, các String khác nhau có thể bị loại khỏi TreeSet ngoài ý muốn. Đừng suy ra một bộ dữ liệu đúng chỉ từ việc có cờ SORTED/DISTINCT.

## 12. Các cờ có thể thay đổi qua Stream pipeline

Nguồn có characteristics không đồng nghĩa mọi **Stream trung gian** đều giữ nguyên các cờ ở Spliterator cuối. Mỗi thao tác có thể biến đổi thông tin mà Stream biết.

Ví dụ về ý nghĩa:

| Thao tác | Thông tin bị ảnh hưởng |
| --- | --- |
| **filter(predicate)** | Không thể coi kích thước đầu ra bằng kích thước nguồn nếu số phần tử giữ lại chưa biết |
| **map(mapper)** | Mapper có thể biến các phần tử khác nhau thành cùng giá trị hoặc phá thứ tự sắp xếp |
| **distinct()** | Đầu ra loại trùng theo ngữ nghĩa Stream |
| **sorted()** | Đầu ra có thứ tự sắp xếp theo lời gọi tương ứng |
| **limit/skip** | Số phần tử còn lại thay đổi theo vị trí và có thể ảnh hưởng thông tin chia nhánh |
| **unordered()** | Loại bỏ yêu cầu encounter order của pipeline |

Không nên khẳng định một bộ flags cố định sẽ tồn tại sau mọi thao tác và mọi JDK. Cách an toàn là **đọc hợp đồng API ở vị trí cần dùng** và **kiểm tra characteristics** khi cần viết thuật toán tùy chỉnh dựa trên chúng.

### 12.1. map không tự bảo toàn DISTINCT và SORTED

Giả sử nguồn int **[1,2,3]** vừa SORTED vừa DISTINCT. Mapper **n -> n % 2** biến nó thành **[1,0,1]**: vừa không được sắp tăng, vừa trùng giá trị 1. Do đó việc tự giữ flags SORTED và DISTINCT cho nguồn đã ánh xạ như thể không có biến đổi là **sai**.

Nếu mapper cụ thể bảo toàn thứ tự, ví dụ **n -> n + 1** trong miền không overflow, ta vẫn không nên tự suy ra framework sẽ công bố SORTED vì nó không chứng minh tính đơn điệu của lambda tùy ý. Một wrapper custom Spliterator chỉ nên công bố flags mà chính wrapper bảo đảm đúng.

### 12.2. filter thay đổi số phần tử

Với nguồn SIZED gồm 100 giá trị, **filter(n -> n > 50)** có thể giữ 50 giá trị hoặc một số khác tùy dữ liệu. Khi xây một Spliterator tùy chỉnh có logic lọc bên trong, không thể giữ lời hứa exact size 100 nếu chỉ phát 50 phần tử.

Java Stream có thể tối ưu qua pipeline dựa trên thông tin có thể chứng minh; không dùng số phần tử gốc làm thay thế cho exact size của đầu ra sau lọc.

### 12.3. SORTED không tự động suy ra khi một Collection chứa các giá trị đã sắp

Một ArrayList vô tình đang ở thứ tự tăng dần không có nghĩa Spliterator của ArrayList nhất thiết báo SORTED. Đặc tính là **hợp đồng của nguồn và implementation**, không phải kết quả quét dữ liệu tại runtime.

Nếu cần một nguồn tự định nghĩa luôn sắp xếp, hãy biểu diễn đúng đặc tính và cung cấp comparator phù hợp; nếu chỉ cần sắp xếp một lần, dùng Stream.sorted có thể đơn giản hơn xây custom Spliterator báo SORTED.

## 13. Sai flag ảnh hưởng kết quả thế nào?

### 13.1. Gắn DISTINCT sai

Một custom Spliterator phát **[A, B, A]** nhưng báo DISTINCT. Downstream **distinct()** có thể coi nguồn đã không có trùng và bỏ qua công việc nhận diện. Kết quả có thể vẫn chứa A hai lần dù người dùng kỳ vọng loại trùng.

### 13.2. Gắn SORTED sai

Một nguồn phát **[4,1,3]** nhưng báo SORTED theo natural order. Thuật toán downstream được phép dựa vào lời hứa đó và có thể tối ưu sai. Kết quả của các thao tác yêu cầu order/comparator có thể không đúng. Khi SORTED, getComparator cũng phải nhất quán với thứ tự dữ liệu.

### 13.3. Gắn SIZED sai

Nguồn 10 phần tử nhưng chỉ phát 7, lại báo exact size 10. Các tối ưu như count và một số chiến lược cấp phát có thể sử dụng thông tin không đúng; dữ liệu kết quả có thể không tương ứng thực tế. **Đừng khai báo SIZED nếu con số chỉ là upper bound**.

### 13.4. Gắn SUBSIZED sai

Nguồn ban đầu biết đúng size nhưng các split không biết size hoặc báo sai; bộ chia parallel có thể tin vào các vị trí/độ dài không khớp. Hậu quả có thể chỉ xuất hiện dưới workload song song, khiến lỗi khó tái hiện.

### 13.5. Gắn ORDERED sai

Nếu nguồn không giữ một encounter order xác định, nhưng báo ORDERED, các thao tác như limit/findFirst có thể mang nghĩa sai so với yêu cầu người dùng. Không dùng ORDERED để biến thứ tự ngẫu nhiên thành thứ tự có ý nghĩa.

**Quy tắc kiểm thử:** mỗi bit được công bố phải có bằng chứng từ bất biến của nguồn và hành vi của tryAdvance/trySplit, không chỉ vì người viết muốn tối ưu.

## 14. Những đặc tính khác cần nhận biết

Ngoài năm cờ chính, Spliterator còn một số đặc tính quan trọng:

- **NONNULL**: phần tử không bao giờ null.
- **IMMUTABLE**: cấu trúc dữ liệu nguồn không thể bị sửa trong quá trình duyệt theo hợp đồng Spliterator.
- **CONCURRENT**: nguồn hỗ trợ sửa đổi đồng thời theo hợp đồng được xác định (ví dụ collection concurrent thích hợp).

Các đặc tính này độc lập với phần lớn năm cờ chính. Ví dụ:

- Một nguồn có thể NONNULL nhưng không SORTED.
- Một nguồn IMMUTABLE có thể chứa giá trị trùng, nên không tự DISTINCT.
- Một concurrent collection có thể không đảm bảo snapshot kích thước chính xác, nên không tự SIZED.

**Không lạm dụng IMMUTABLE:** một mảng Java có thể được sửa thông qua một tham chiếu khác. Chỉ vì độ dài mảng cố định không có nghĩa cấu trúc/giá trị nguồn hoàn toàn bất biến theo ngữ nghĩa cần bảo đảm khi duyệt. Dựa trên hợp đồng của API nguồn thay vì gắn thêm IMMUTABLE theo suy đoán.

## 15. Hiệu năng và song song hóa

Các cờ characteristics giúp framework lập kế hoạch, nhưng **không có cờ nào tự làm thuật toán luôn nhanh**.

### 15.1. ORDERED có thể khiến parallel tốn phối hợp

Khi phải giữ phần tử đầu tiên hoặc thứ tự gặp, một số thao tác như **limit**, **skip**, **distinct** có thể cần phối hợp giữa các nhánh song song nhiều hơn. Nếu yêu cầu nghiệp vụ không có thứ tự, có thể tránh ràng buộc order; nhưng nếu có, không nên đánh đổi tính đúng đắn lấy benchmark đẹp.

### 15.2. SUBSIZED giúp phân hoạch chính xác

Khi các split biết kích thước, framework có thể phân bổ công việc và kết quả theo vị trí dễ hơn. Nhưng một custom Spliterator **trySplit không hiệu quả** hoặc tạo các nhánh cực lệch vẫn có thể chạy chậm dù mang SUBSIZED.

### 15.3. SORTED và DISTINCT giúp tránh việc làm lại không cần thiết

Nếu nguồn thực sự sorted/distinct, các thao tác tương ứng có thể giảm công việc. Tuy nhiên điều này phụ thuộc pipeline, loại Stream và implementation; **không cam kết một tốc độ cụ thể**.

### 15.4. StreamSupport với parallel flag

~~~java
IntStream stream = StreamSupport.intStream(
        new RangeSpliterator(0, 1000), true);
~~~

Đây là đoạn minh họa giả định RangeSpliterator có sẵn như ví dụ, cần import StreamSupport và IntStream.

Tham số **true** cho phép parallel pipeline, nhưng không đảm bảo luôn dùng nhiều thread. Một nguồn quá nhỏ hoặc trySplit không hữu dụng có thể không đạt tốc độ mong đợi. Cần cân nhắc overhead chia nhánh, combiner, kích thước dữ liệu và tính thuần của các behavioral parameters.

## 16. Xây nguồn tùy chỉnh bằng StreamSupport: lựa chọn nào?

Java hỗ trợ hai cách thông dụng:

~~~java
Stream<T> fromSpliterator =
        StreamSupport.stream(spliterator, false);
~~~

hoặc:

~~~java
Stream<T> fromSupplier =
        StreamSupport.stream(supplier, characteristics, false);
~~~

Đây là **chữ ký sử dụng minh họa**, giả định các biến/kiểu phù hợp và import StreamSupport, Stream.

- Truyền **Spliterator trực tiếp**: đã có một instance Spliterator, dùng instance ấy cho Stream.
- Truyền **Supplier<Spliterator<T>>** kèm bitmask characteristics: cho phép trì hoãn việc lấy Spliterator đến lúc terminal operation, theo hợp đồng API. Điều này hữu ích khi nguồn phải late-bind hoặc nhạy với thay đổi trước khi bắt đầu duyệt.
- Với bản Supplier, **characteristics khai báo phải phù hợp với Spliterator mà supplier cung cấp**. Cung cấp flags khác thực tế có thể gây hành vi không đúng.

### 16.1. Không dùng Stream đã tiêu thụ

Stream được thiết kế dùng **một lần**. Sau terminal operation như toList, count, sum, không tiếp tục tiêu thụ cùng Stream.

Tương tự, custom Spliterator chứa cursor mutable không nên được chuyển vào nhiều Stream rồi hy vọng mỗi Stream có lại dữ liệu ban đầu. Nếu cần hai lần duyệt, tạo **hai Spliterator mới**, hoặc thiết kế nguồn có cơ chế khởi tạo lại đúng hợp đồng.

## 17. Đọc bảng: chọn flags theo từng trường hợp

| Nguồn dữ liệu | ORDERED | SIZED | SUBSIZED | SORTED | DISTINCT |
| --- | --- | --- | --- | --- | --- |
| Dải số nguyên tăng không lặp [start,end) với split theo khoảng chính xác | Có | Có | Có | Có | Có |
| Mảng [5,1,5] duyệt theo chỉ số | Có | Có | Có | Không | Không |
| List [1,1,2] duyệt theo vị trí | Có | Có nếu snapshot/kích thước theo hợp đồng | Tùy implementation | Không bắt buộc | Không |
| Danh sách String đã được sắp và có trùng | Có | Nếu biết chính xác | Tùy split | Có nếu Spliterator công bố hợp đồng sắp xếp | Không |
| Tập có unique values nhưng không có encounter order | Không cần | Tùy nguồn | Tùy split | Không bắt buộc | Có nếu uniqueness theo equals |
| Dữ liệu phát từ bộ lọc không biết số phần tử hợp lệ | Tùy nguồn | Không | Không | Tùy bất biến | Tùy bất biến |

Bảng là **hướng dẫn xác định hợp đồng cho custom source**, không thay thế việc đọc tài liệu của từng Spliterator từ Java Collections. Đặc tính cụ thể của một implementation có thể phụ thuộc cách nó duyệt và chia nguồn.

Đặc biệt: **“danh sách hiện đang được sắp”** không tự động khiến Spliterator từ List báo SORTED. Nếu cần contract SORTED, phải triển khai hay chọn nguồn phù hợp.

## 18. Kiểm thử custom Spliterator đúng cách

Khi tự cài đặt Spliterator, không chỉ chạy một lần **stream(...,false).toList()** rồi xem như đủ. Bộ test cần bao phủ:

### 18.1. Duyệt tuần tự

- Tạo nguồn biết trước nội dung và thứ tự.
- Duyệt đến hết bằng tryAdvance/forEachRemaining.
- Kiểm tra số phần tử thực nhận, thứ tự, số lần trùng, kết quả sau khi hết.
- Nếu ORDERED, kiểm tra encounter order dự kiến.
- Nếu SORTED, xác minh các cặp liền kề không giảm theo getComparator hoặc natural ordering.

### 18.2. Kích thước

- Trước duyệt, kiểm tra estimateSize, getExactSizeIfKnown.
- Sau một lần tryAdvance, nếu SIZED và số phần tử còn lại được quản lý theo hợp đồng, kiểm tra lại giá trị còn lại.
- Với nguồn không SIZED, kiểm tra getExactSizeIfKnown trả -1.
- Tránh số lượng âm hoặc vượt long.

### 18.3. Chia và ghép lại

- Gọi trySplit đến khi không chia được nữa.
- Duyệt **split trả về trước** rồi đến remainder nếu ORDERED và cần khôi phục encounter order.
- Tổng số phần tử của các nhánh phải bằng nguồn ban đầu, không mất và không lặp phần tử.
- Nếu SUBSIZED, mọi nhánh phải báo SIZED/SUBSIZED và kích thước chính xác.
- Kiểm thử cả nguồn rỗng, 1 phần tử, số lượng lẻ và lớn.

### 18.4. Thuật toán tiêu thụ

- So sánh kết quả StreamSupport tuần tự và song song.
- Thử **toArray**, **count**, **findFirst**, **distinct**, **sorted**, **limit**, **skip**.
- Với nguồn DISTINCT thực sự, kiểm tra phần tử không trùng theo equals.
- Với nguồn SORTED, kiểm tra getComparator và thứ tự thật.
- Không dựa trên thứ tự log của mapper ở parallel stream.

### 18.5. Biên miền dữ liệu

- Với dải int, thử giá trị âm và sát biên Integer.MIN_VALUE/Integer.MAX_VALUE để phát hiện overflow tính midpoint/estimateSize.
- Với nguồn có tài nguyên, kiểm tra vòng đời và exception khi chưa duyệt hết.
- Với dữ liệu mutable, xác định cơ chế snapshot hay concurrent-modification rõ ràng.

**Quan trọng:** một custom Spliterator được báo SUBSIZED nhưng trySplit trả null ở nguồn nhỏ vẫn hoàn toàn hợp lệ; không cần cố chia một phần tử thành hai nhánh.

## 19. Những lỗi phổ biến

| Lỗi | Vấn đề | Cách sửa |
| --- | --- | --- |
| Gắn SORTED cho List chưa sắp | Downstream có thể tin vào thứ tự sai | Chỉ báo SORTED khi phát đúng thứ tự |
| Gắn DISTINCT cho nguồn có duplicate | distinct downstream có thể được tối ưu sai | Kiểm chứng equals uniqueness |
| Coi ORDERED nghĩa là natural ascending | Nhầm encounter order với sorted order | ORDERED chỉ hứa thứ tự gặp |
| Coi SIZED là ước lượng đại khái | Sai kích thước exact và count | Không có exact size thì bỏ SIZED |
| Gắn SUBSIZED dù split không có size thật | Sai phân hoạch song song | Chỉ báo SUBSIZED nếu mọi split phù hợp |
| Không cập nhật cursor/estimateSize sau trySplit | Có thể trùng/mất phần tử hoặc báo size sai | Split không chồng lấp và cập nhật phần dư |
| Gắn SORTED nhưng không triển khai getComparator | Hợp đồng SORTED không được đáp ứng | Trả null cho natural, comparator cho custom |
| Gọi getComparator trên nguồn không SORTED | IllegalStateException | Kiểm tra SORTED trước |
| Gắn IMMUTABLE cho nguồn mutable không có hợp đồng | Có thể gặp thay đổi trong khi duyệt | Xác định snapshot/ownership rõ ràng |
| Đoán flags từ một lần in kết quả | Phụ thuộc dữ liệu ngẫu nhiên | Dựa trên bất biến của nguồn |
| Dùng SUBSIZED như lời hứa chia đều | Không phải ý nghĩa của cờ | Chỉ hứa size chính xác từng split |
| Giữ cờ SORTED/DISTINCT sau map tùy ý | Mapper có thể phá tính chất đó | Đánh giá lại flags sau biến đổi |
| Chia sẻ cùng Spliterator cho nhiều Stream | Cursor dùng một lần | Tạo Spliterator mới mỗi lần |
| Dựa vào count để buộc side effect chạy | Có thể tối ưu không traversal | Không dùng side effect làm nghiệp vụ |
| Chỉ test sequential, bỏ qua parallel | Lỗi split khó lộ | Test cả hai đường xử lý |

## 20. Bài tập tự luyện

### Bài 1: Phân loại một mảng

Nguồn mảng [7, 1, 7, 3] được duyệt theo chỉ số, biết đúng 4 phần tử và chia theo đoạn chỉ số. Hãy xác định năm cờ chính.

**Gợi ý:** ORDERED, SIZED, SUBSIZED có; SORTED và DISTINCT không.

### Bài 2: SORTED nhưng không DISTINCT

Thiết kế một Spliterator phát [1,1,2,3] với natural ordering. Vì sao SORTED có thể đúng nhưng DISTINCT sai? Cần trả gì từ getComparator?

### Bài 3: DISTINCT nhưng không SORTED

Nguồn phát [9,2,7] không có duplicate. Vì sao có thể DISTINCT nhưng chưa SORTED? Nếu nguồn duyệt cố định theo thứ tự ấy, ORDERED có được không?

### Bài 4: Kiểm tra khi chia

Tạo RangeSpliterator(0,7), gọi trySplit rồi kiểm tra hai size. Lặp tiếp trên nhánh prefix. Chứng minh mọi nhánh không chồng lấp và tổng size bằng 7.

### Bài 5: Sai hợp đồng size

Một nguồn báo SIZED=100 nhưng chỉ phát các bản ghi thỏa filter, có 68 bản ghi. Giải thích vì sao **getExactSizeIfKnown()** và **count()** có thể gây hiểu nhầm, đề xuất thay đổi cờ.

### Bài 6: Comparator tùy chỉnh

Tạo TreeSet<String> với comparator theo độ dài rồi chữ cái. Quan sát getComparator không null và thử so thứ tự hai chuỗi cùng độ dài. Nếu comparator chỉ theo độ dài, điều gì xảy ra với hai giá trị khác nhau nhưng cùng độ dài?

### Bài 7: Ordered parallel

Chạy RangeSpliterator(1,101) qua StreamSupport.intStream với parallel false và true; lấy toArray và tính sum. Đối chiếu kết quả nội dung, không đối chiếu thứ tự log từ map hoặc peek.

### Bài 8: Thiết kế nguồn sinh số ngẫu nhiên

Một nguồn sinh random values liên tục không biết số lượng chính xác và có thể lặp số. Trong năm cờ, nên tránh công bố những cờ nào nếu không có thêm hợp đồng? Hãy phân biệt việc có trình tự phát sinh với encounter order được API định nghĩa.

## 21. Ghi nhớ

**ORDERED** hứa encounter order; **SORTED** hứa thứ tự sắp xếp và bao hàm ORDERED, đồng thời cần getComparator đúng. **SIZED** hứa kích thước chính xác theo hợp đồng; **SUBSIZED** mạnh hơn, bảo đảm các split vẫn SIZED và SUBSIZED. **DISTINCT** hứa không có các phần tử trùng theo equals.

Năm cờ **không phải công tắc tăng tốc**. Chúng là mô tả sự thật về Spliterator. Khi làm nguồn Stream tùy chỉnh, các lời hứa ấy ảnh hưởng việc chọn phần tử, đếm, chia việc song song và loại trùng. **Khai báo sai có thể khiến downstream tối ưu dựa trên giả thiết không đúng và trả kết quả sai.**

Trước khi đặt một cờ, hãy hỏi: **“Bất kỳ caller hợp lệ nào cũng có thể dựa vào đặc tính này trong mọi lần duyệt và sau mọi lần trySplit mà vẫn nhận kết quả đúng không?”** Nếu không chứng minh được, đừng công bố cờ đó.