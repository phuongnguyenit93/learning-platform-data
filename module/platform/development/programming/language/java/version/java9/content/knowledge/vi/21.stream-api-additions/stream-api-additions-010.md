# Kiểm chứng kết quả khi nguồn rỗng, vô hạn hoặc không có thứ tự

## Mục tiêu

Sau bài học này, bạn có thể:

- Dự đoán kết quả của các terminal operation khi Stream không có phần tử.
- Nhận biết operation nào có thể kết thúc sớm trên nguồn vô hạn và điều kiện để nó thực sự kết thúc.
- Giải thích vì sao một pipeline trên nguồn vô hạn có thể chạy mãi dù operation có vẻ đơn giản.
- Phân biệt encounter order với thứ tự thực tế khi xử lý song song hoặc gọi \`unordered()\`.
- Viết kiểm thử dựa trên các bảo đảm của Stream API thay vì giả định một kết quả không được đặc tả.

## 1. Ba dạng nguồn cần kiểm chứng

Kết quả của Stream phụ thuộc vào dữ liệu nguồn, encounter order và cách pipeline được thực thi. Khi kiểm thử, hãy phân biệt ba trường hợp:

1. **Nguồn rỗng:** không có phần tử nào được phát ra. Ví dụ \`Stream.empty()\` hoặc một collection rỗng.
2. **Nguồn vô hạn:** có thể tiếp tục phát ra phần tử mà không có điểm kết thúc tự nhiên. Ví dụ \`Stream.iterate(...)\` hoặc \`Stream.generate(...)\`.
3. **Nguồn không có thứ tự (unordered):** Stream không cam kết encounter order. Điều này có thể đến từ nguồn vốn không có thứ tự như một số collection, hoặc từ việc gọi \`unordered()\` trên pipeline.

Ba thuộc tính này độc lập. Một nguồn vô hạn có thể có encounter order, chẳng hạn \`Stream.iterate\`; một nguồn vô hạn khác có thể không có encounter order, chẳng hạn \`Stream.generate\`. Một Stream rỗng có thể xuất phát từ một pipeline ordered hoặc unordered.

## 2. Kết quả khi Stream rỗng

Một Stream rỗng không gọi action của \`forEach\` và không có phần tử để tìm, so sánh hoặc gộp. Các terminal operation vẫn trả về kết quả hợp lệ theo hợp đồng API.

| Operation | Kết quả với Stream rỗng | Lý do |
|---|---|---|
| \`count()\` | \`0\` | Không có phần tử |
| \`findFirst()\` | \`Optional.empty()\` | Không có phần tử đầu tiên |
| \`findAny()\` | \`Optional.empty()\` | Không có phần tử nào để chọn |
| \`min(...)\`, \`max(...)\` | \`Optional.empty()\` | Không có giá trị cực trị |
| \`reduce(BinaryOperator)\` | \`Optional.empty()\` | Không có phần tử đầu vào để gộp |
| \`reduce(identity, accumulator)\` | Trả về \`identity\` | Không có bước tích lũy nào |
| \`anyMatch(predicate)\` | \`false\` | Không có phần tử thỏa điều kiện |
| \`allMatch(predicate)\` | \`true\` | Không có phần tử vi phạm điều kiện |
| \`noneMatch(predicate)\` | \`true\` | Không có phần tử thỏa điều kiện |
| \`forEach(action)\` | Không gọi action | Không có phần tử |
| \`collect(toList())\` | List rỗng | Collector nhận không có phần tử |

### 2.1. Vì sao allMatch và noneMatch trả về true?

Đây là quy tắc logic thường gọi là *vacuous truth* (đúng một cách hiển nhiên khi không có phản ví dụ):

- \`allMatch(p)\` chỉ sai khi tìm thấy ít nhất một phần tử làm \`p\` sai. Stream rỗng không có phản ví dụ, nên kết quả là \`true\`.
- \`noneMatch(p)\` chỉ sai khi tìm thấy một phần tử làm \`p\` đúng. Stream rỗng không có phần tử như vậy, nên kết quả là \`true\`.
- \`anyMatch(p)\` cần ít nhất một phần tử làm \`p\` đúng. Stream rỗng không thể cung cấp phần tử đó, nên kết quả là \`false\`.

Không nên thay các kết quả này bằng cách suy luận rằng “không có dữ liệu thì tất cả đều false”. Hãy áp dụng đúng ý nghĩa logic của từng operation.

### 2.2. reduce có và không có identity

Hai overload có ý nghĩa khác nhau:

~~~java
Optional<Integer> noIdentity =
        Stream.<Integer>empty().reduce(Integer::sum);

int withIdentity =
        Stream.<Integer>empty().reduce(42, Integer::sum);
~~~

Kết quả là \`Optional.empty()\` và \`42\`. Overload có identity luôn có giá trị khởi đầu để trả về; overload không có identity phải biểu diễn trường hợp không có phần tử bằng \`Optional\`.

Identity phải thực sự là phần tử trung hòa của accumulator. Ví dụ, \`0\` là identity của phép cộng số nguyên, còn \`1\` là identity của phép nhân. Chọn sai identity sẽ làm sai kết quả cả với Stream không rỗng.

## 3. Nguồn vô hạn và short-circuit

Một Stream vô hạn không có điểm kết thúc tự nhiên. Pipeline chỉ có thể trả kết quả nếu có operation có thể dừng mà không cần đọc hết nguồn, hoặc có intermediate operation giới hạn lượng phần tử được yêu cầu.

Các nguồn phổ biến:

~~~java
Stream<Integer> increasing =
        Stream.iterate(1, n -> n + 1);

Stream<Integer> repeated =
        Stream.generate(() -> 7);
~~~

\`iterate(seed, next)\` phát ra chuỗi có thứ tự encounter order: 1, 2, 3, ... Trong ví dụ trên, \`generate\` phát ra các giá trị 7 và được đặc tả là unordered.

### 3.1. Các operation có thể kết thúc sớm

Một số terminal operation là short-circuiting:

- \`anyMatch\` có thể dừng ngay khi tìm thấy phần tử thỏa predicate.
- \`allMatch\` có thể dừng ngay khi tìm thấy phần tử không thỏa predicate.
- \`noneMatch\` có thể dừng ngay khi tìm thấy phần tử thỏa predicate.
- \`findFirst\` và \`findAny\` có thể dừng khi tìm được một phần tử.
- \`limit(n)\` giới hạn số phần tử đi qua phần còn lại của pipeline.

Ví dụ, nguồn tăng dần vô hạn vẫn có thể tìm phần tử 100:

~~~java
int value = Stream.iterate(1, n -> n + 1)
        .filter(n -> n == 100)
        .findFirst()
        .orElseThrow();
~~~

Khi tìm được 100, \`findFirst\` có thể kết thúc mà không cần đọc phần còn lại của nguồn.

Tương tự, \`anyMatch(n -> n == 1000)\` trên nguồn này có thể trả về \`true\`; \`allMatch(n -> n < 1000)\` có thể trả về \`false\` khi gặp 1000.

### 3.2. Short-circuit không đồng nghĩa luôn kết thúc

Operation short-circuit chỉ có thể dừng khi điều kiện dừng thực sự xảy ra. Nếu không có phần tử nào kích hoạt điều kiện, pipeline có thể chạy mãi:

~~~java
// Nguồn vô hạn không có số âm.
// findFirst không bao giờ tìm được kết quả.
Stream.iterate(1, n -> n + 1)
        .filter(n -> n < 0)
        .findFirst();

// Không có phần tử nào bằng -1.
// anyMatch không bao giờ có thể trả false.
Stream.iterate(1, n -> n + 1)
        .anyMatch(n -> n == -1);

// Mọi phần tử đều dương, nhưng allMatch phải chờ
// một phản ví dụ hoặc kết thúc nguồn.
Stream.iterate(1, n -> n + 1)
        .allMatch(n -> n > 0);
~~~

Ba đoạn trên là ví dụ minh họa không nên chạy trực tiếp trong chương trình kiểm thử vì chúng không có bảo đảm hoàn tất. \`noneMatch(n -> n < 0)\` trên cùng nguồn cũng không thể xác nhận kết quả \`true\` bằng cách đọc hữu hạn phần tử.

### 3.3. Giới hạn nguồn trước khi dùng terminal operation

Với nguồn vô hạn, hãy tạo một pipeline có giới hạn rõ ràng nếu mục tiêu là lấy một mẫu hữu hạn:

~~~java
List<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .collect(Collectors.toList());

List<Integer> repeatedValues = Stream.generate(() -> 7)
        .limit(3)
        .collect(Collectors.toList());
~~~

Hai kết quả lần lượt là \`[1, 2, 3, 4, 5]\` và \`[7, 7, 7]\`.

Vị trí của \`limit\` làm thay đổi ý nghĩa:

~~~java
// Lấy 5 phần tử đầu rồi sắp xếp 5 phần tử đó.
Stream.iterate(1, n -> n + 1)
        .limit(5)
        .sorted();

// Sắp xếp toàn bộ nguồn vô hạn trước khi lấy 5 phần tử:
// không thể hoàn tất.
Stream.iterate(1, n -> n + 1)
        .sorted()
        .limit(5);
~~~

\`sorted\` cần quan sát toàn bộ đầu vào để xác định thứ tự toàn cục. Vì vậy, \`sorted().limit(5)\` không thể tạo ra năm phần tử đầu tiên từ một nguồn vô hạn tổng quát. Đặt \`limit\` trước \`sorted\` tạo pipeline hữu hạn, nhưng kết quả chỉ là năm phần tử đầu được sắp xếp, không phải năm phần tử nhỏ nhất của toàn nguồn.

Các terminal operation cần tiêu thụ toàn bộ nguồn như \`count\`, \`forEach\`, \`toArray\`, \`collect\`, \`reduce\`, \`min\` và \`max\` thường không thể kết thúc trên nguồn vô hạn. Không dùng chúng với nguồn vô hạn nếu không có giới hạn hữu hạn ở phía trước.

## 4. Encounter order và Stream không có thứ tự

**Encounter order** là thứ tự mà Stream xác định các phần tử xuất hiện từ nguồn. Một số nguồn có thứ tự rõ ràng, chẳng hạn List; một số nguồn như HashSet không cam kết thứ tự duyệt ổn định.

Gọi \`unordered()\` yêu cầu pipeline bỏ ràng buộc encounter order nếu có. Method này:

- Không xáo trộn phần tử theo một thuật toán ngẫu nhiên.
- Không sắp xếp phần tử.
- Không thay đổi giá trị của phần tử.
- Cho phép implementation chọn cách xử lý không cần giữ thứ tự, đặc biệt hữu ích trong một số pipeline song song.

Sau khi bỏ encounter order, code không được dựa vào vị trí cụ thể của phần tử trong kết quả.

### 4.1. findFirst và findAny

- \`findFirst()\` trả phần tử đầu tiên theo encounter order nếu Stream có thứ tự.
- Nếu Stream không có encounter order, \`findFirst()\` có thể trả về bất kỳ phần tử nào.
- \`findAny()\` được thiết kế để trả về một phần tử bất kỳ; ngay cả trên Stream có thứ tự, không nên giả định nó luôn trả phần tử đầu.

Trong xử lý song song, \`findFirst\` có thể cần phối hợp nhiều nhánh để bảo đảm phần tử đầu tiên theo encounter order. Nếu yêu cầu nghiệp vụ chỉ cần một phần tử phù hợp bất kỳ, \`findAny\` có thể cho implementation nhiều tự do hơn.

### 4.2. forEach và forEachOrdered

~~~java
List<Integer> values = List.of(1, 2, 3, 4, 5);

values.parallelStream().forEach(System.out::println);
~~~

\`forEach\` không bảo đảm thứ tự gọi action trên Stream song song. Nếu cần thực hiện action theo encounter order, dùng:

~~~java
values.parallelStream().forEachOrdered(System.out::println);
~~~

\`forEachOrdered\` bảo đảm thứ tự encounter khi nguồn có thứ tự. Nếu trước đó đã gọi \`unordered()\`, không còn encounter order để khôi phục.

### 4.3. limit, skip và distinct trên unordered stream

Với Stream có thứ tự, \`limit(3)\` chọn ba phần tử đầu theo encounter order. Với Stream unordered, \`limit(3)\` chỉ cần chọn một tập hợp ba phần tử phù hợp; không có cam kết đó là ba phần tử cụ thể nào.

Tương tự, \`skip(n)\` trên unordered stream không có ý nghĩa “bỏ đúng n phần tử đầu” theo một thứ tự ổn định. \`distinct()\` vẫn loại phần tử trùng theo \`equals\`, nhưng thứ tự các phần tử còn lại không được đảm bảo nếu pipeline unordered.

Trong một pipeline song song, nếu thứ tự không quan trọng, bỏ ràng buộc bằng \`unordered()\` trước \`limit\`, \`skip\` hoặc \`distinct\` có thể giúp implementation giảm công việc phối hợp. Chỉ làm vậy khi kết quả bất kỳ đáp ứng đúng yêu cầu nghiệp vụ.

## 5. Kiểm thử đúng theo bảo đảm API

Một test đáng tin cậy cần kiểm tra điều mà API cam kết, không kiểm tra chi tiết triển khai tình cờ quan sát được.

### Với nguồn rỗng

- Kiểm tra \`count == 0\`.
- Kiểm tra \`findFirst\` và \`findAny\` là empty.
- Kiểm tra \`anyMatch == false\`, \`allMatch == true\`, \`noneMatch == true\`.
- Kiểm tra reduce không identity trả empty và reduce có identity trả identity.
- Kiểm tra action của \`forEach\` không được gọi.

### Với nguồn vô hạn

- Giới hạn nguồn trong test bằng \`limit\` khi cần kiểm tra một prefix.
- Chọn predicate chắc chắn đạt điều kiện short-circuit ở một vị trí hữu hạn.
- Không chạy terminal operation toàn phần trên nguồn vô hạn.
- Không giả định một short-circuit operation sẽ kết thúc nếu điều kiện dừng không bao giờ xảy ra.
- Đặt timeout cho test kiểm tra nguy cơ treo; tốt hơn là thiết kế test hữu hạn ngay từ đầu.

### Với nguồn unordered hoặc parallel

- Không so sánh một list kết quả với thứ tự cố định nếu API không bảo đảm thứ tự.
- Kiểm tra kích thước, tập giá trị hoặc quan hệ bất biến thay vì vị trí cụ thể.
- Với \`findAny\`, kiểm tra Optional có giá trị và giá trị thuộc miền hợp lệ.
- Chỉ dùng \`forEachOrdered\` khi thứ tự encounter có ý nghĩa.
- Không dựa vào thứ tự in log của \`forEach\` trong stream song song.

## 6. Ví dụ hoàn chỉnh có thể chạy

Tạo file **StreamEdgeCasesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamEdgeCasesDemo {

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // 1. Nguồn rỗng.
        Stream<Integer> empty = Stream.empty();

        require(empty.count() == 0, "empty count");
        require(Stream.<Integer>empty().findFirst().isEmpty(),
                "empty findFirst");
        require(Stream.<Integer>empty().findAny().isEmpty(),
                "empty findAny");
        require(!Stream.<Integer>empty().anyMatch(n -> n > 0),
                "empty anyMatch");
        require(Stream.<Integer>empty().allMatch(n -> n > 0),
                "empty allMatch");
        require(Stream.<Integer>empty().noneMatch(n -> n > 0),
                "empty noneMatch");
        require(Stream.<Integer>empty().reduce(Integer::sum).isEmpty(),
                "empty reduce without identity");
        require(Stream.<Integer>empty().reduce(42, Integer::sum) == 42,
                "empty reduce with identity");

        List<Integer> emptyList = Stream.<Integer>empty()
                .collect(Collectors.toList());
        require(emptyList.isEmpty(), "empty collector");

        // 2. Nguồn tăng dần vô hạn, nhưng predicate đạt điều kiện hữu hạn.
        int firstHundred = Stream.iterate(1, n -> n + 1)
                .filter(n -> n == 100)
                .findFirst()
                .orElseThrow();
        require(firstHundred == 100, "infinite findFirst");

        boolean foundThousand = Stream.iterate(1, n -> n + 1)
                .anyMatch(n -> n == 1000);
        require(foundThousand, "infinite anyMatch");

        boolean allBelowThousand = Stream.iterate(1, n -> n + 1)
                .allMatch(n -> n < 1000);
        require(!allBelowThousand, "infinite allMatch stops at counterexample");

        List<Integer> prefix = Stream.iterate(1, n -> n + 1)
                .limit(5)
                .collect(Collectors.toList());
        require(prefix.equals(List.of(1, 2, 3, 4, 5)),
                "bounded infinite prefix");

        List<Integer> generated = Stream.generate(() -> 7)
                .limit(3)
                .collect(Collectors.toList());
        require(generated.equals(List.of(7, 7, 7)),
                "bounded generated stream");

        // 3. Stream có encounter order được xử lý song song.
        List<Integer> values = List.of(1, 2, 3, 4, 5);

        Optional<Integer> first = values.parallelStream().findFirst();
        require(first.orElseThrow() == 1, "ordered findFirst");

        List<Integer> orderedTraversal = new ArrayList<>();
        values.parallelStream().forEachOrdered(orderedTraversal::add);
        require(orderedTraversal.equals(values), "forEachOrdered");

        // 4. Bỏ encounter order: chỉ kiểm tra các bảo đảm còn lại.
        Optional<Integer> arbitrary =
                values.parallelStream().unordered().findAny();
        require(arbitrary.isPresent() && values.contains(arbitrary.get()),
                "unordered findAny must belong to source");

        List<Integer> arbitraryThree = values.parallelStream()
                .unordered()
                .limit(3)
                .collect(Collectors.toList());
        require(arbitraryThree.size() == 3,
                "unordered limit size");
        require(values.containsAll(arbitraryThree),
                "unordered limit members");

        System.out.println(
                "empty: count=0, any=false, all=true, none=true");
        System.out.println(
                "empty: reduce=empty, identityReduce=42, collected=[]");
        System.out.println(
                "infinite: firstMatch=100, anyMatch(1000)=true, prefix="
                        + prefix);
        System.out.println(
                "unordered: findAnyPresent=true, limitSize="
                        + arbitraryThree.size()
                        + ", orderedTraversal=" + orderedTraversal);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out StreamEdgeCasesDemo.java
java -cp out StreamEdgeCasesDemo
~~~

Output chính xác:

~~~text
empty: count=0, any=false, all=true, none=true
empty: reduce=empty, identityReduce=42, collected=[]
infinite: firstMatch=100, anyMatch(1000)=true, prefix=[1, 2, 3, 4, 5]
unordered: findAnyPresent=true, limitSize=3, orderedTraversal=[1, 2, 3, 4, 5]
~~~

Giá trị cụ thể do \`findAny\` chọn không được in ra; test chỉ xác nhận nó có giá trị thuộc nguồn. Ba phần tử mà unordered \`limit(3)\` chọn cũng có thể khác nhau giữa các lần chạy. Test kiểm tra đúng kích thước và membership thay vì cố định thứ tự.

## 7. Lỗi thường gặp

### Cho rằng allMatch trên nguồn vô hạn luôn trả true nếu các phần tử đang thấy đều thỏa

Không thể suy ra toàn bộ nguồn vô hạn chỉ từ một prefix hữu hạn. Nếu không có phản ví dụ và nguồn không kết thúc, operation không thể xác nhận kết quả.

### Gọi sorted trước limit trên nguồn vô hạn

\`sorted\` cần dữ liệu toàn cục. Hãy xác định rõ muốn sắp xếp toàn nguồn hay chỉ sắp xếp một prefix hữu hạn.

### Giả định findAny luôn giống findFirst

\`findAny\` không cam kết phần tử đầu. Trong xử lý song song, kết quả có thể phụ thuộc vào nhánh nào tìm được phần tử trước.

### Kiểm tra thứ tự của unordered stream

Sau \`unordered()\`, thứ tự cụ thể không thuộc hợp đồng. Test nên kiểm tra tập phần tử, kích thước hoặc predicate của kết quả.

### Nghĩ unordered() sẽ xáo trộn dữ liệu

Method này chỉ gỡ ràng buộc encounter order. Nó không phải thao tác shuffle và không bảo đảm kết quả ngẫu nhiên.

### Chạy terminal operation toàn phần trên nguồn vô hạn

\`count\`, \`collect\`, \`reduce\`, \`forEach\`, \`min\`, \`max\` hoặc \`sorted\` có thể không bao giờ hoàn tất. Hãy giới hạn nguồn hoặc dùng điều kiện short-circuit có thể đạt được.

### Dùng Stream nhiều lần

Stream chỉ được tiêu thụ một lần. Muốn kiểm tra nhiều operation, hãy tạo Stream mới từ nguồn hoặc tạo supplier cung cấp Stream mới; không tái sử dụng cùng một instance đã đóng.

## 8. Checklist

- [ ] Đã xác định nguồn có rỗng, hữu hạn hay vô hạn.
- [ ] Đã kiểm tra đúng quy tắc empty cho match, find, reduce và collect.
- [ ] Đã xác định operation có short-circuit hay phải tiêu thụ toàn nguồn.
- [ ] Predicate trên nguồn vô hạn có điều kiện dừng đạt được trong hữu hạn bước.
- [ ] Đã đặt \`limit\` đúng vị trí và hiểu ý nghĩa của pipeline.
- [ ] Đã xác định Stream có encounter order hay không.
- [ ] Không giả định thứ tự cho \`findAny\`, \`forEach\` hoặc unordered \`limit\`.
- [ ] Test unordered/parallel kiểm tra membership và invariant thay vì một thứ tự tình cờ.
- [ ] Mỗi Stream instance chỉ được tiêu thụ một lần.

