# Thiết kế API nhận SequencedSet khi thứ tự là một phần của hợp đồng

Khi một phương thức cần xử lý các phần tử theo đúng encounter order và đồng thời không muốn phần tử trùng lặp, kiểu tham số **SequencedSet<E>** diễn đạt hợp đồng rõ hơn **Set<E>**. Từ Java 21, SequencedSet là interface chuẩn của Java Collections Framework, cung cấp thứ tự duyệt xác định cùng các thao tác ở hai đầu.

Chọn đúng kiểu tham số giúp người gọi hiểu dữ liệu cần có đặc tính gì, còn người viết API biết mình được phép dựa vào những bảo đảm nào. Tuy vậy, SequencedSet chỉ bảo đảm có encounter order; nó không tự bảo đảm thứ tự đó là thứ tự chèn, thứ tự tăng dần hay collection có thể thay đổi. Những điều này cần được xác định riêng trong hợp đồng của API.

## 1. Khi nào nên nhận SequencedSet?

Hãy chọn SequencedSet khi cả hai điều sau đều là một phần của yêu cầu:

- Phần tử phải duy nhất theo quy tắc của Set.
- Thứ tự gặp phần tử phải được giữ lại và có ý nghĩa đối với kết quả hoặc hành vi của phương thức.

Ví dụ, một API tạo breadcrumb, chuỗi bước xử lý, danh sách nhãn duy nhất theo thứ tự hiển thị hoặc các ưu tiên đã được xếp thứ tự có thể cần SequencedSet.

~~~java
import java.util.SequencedSet;

class PipelineView {
    static void printStages(SequencedSet<String> stages) {
        for (String stage : stages) {
            System.out.println(stage);
        }
    }
}
~~~

Vòng lặp duyệt theo encounter order của collection. Nếu caller truyền một SequencedSet có thứ tự A, B, C thì API nhận và xử lý theo A, B, C.

Không nên chọn SequencedSet chỉ vì muốn có một collection hiện đại. Nếu phương thức không quan tâm đến thứ tự, Set là hợp đồng phù hợp hơn. Nếu thứ tự quan trọng nhưng phần tử trùng lặp được phép, hãy cân nhắc SequencedCollection hoặc List.

## 2. Chọn kiểu tham số theo đúng hợp đồng

Các interface trong Java Collections Framework biểu đạt những yêu cầu khác nhau:

| Kiểu tham số | Bảo đảm chính | Dùng khi |
|---|---|---|
| **Collection<E>** | Tập hợp phần tử, không cam kết encounter order hay tính duy nhất | Chỉ cần duyệt hoặc xử lý các phần tử |
| **Set<E>** | Phần tử duy nhất, không cam kết encounter order | Cần loại trùng nhưng thứ tự không có ý nghĩa |
| **SequencedCollection<E>** | Có encounter order, cho phép phần tử trùng | Thứ tự quan trọng nhưng trùng lặp vẫn hợp lệ |
| **SequencedSet<E>** | Có encounter order và phần tử duy nhất | Cần cả thứ tự lẫn tính duy nhất |
| **List<E>** | Có thứ tự, cho phép trùng và truy cập theo vị trí | Chỉ số, vị trí hoặc thao tác theo index là một phần hợp đồng |
| **SortedSet<E>** | Set có thứ tự theo natural ordering hoặc Comparator | Thứ tự sắp xếp là một phần hợp đồng |

**SequencedSet** là lựa chọn phù hợp khi API cần một tập hợp có thứ tự nhưng không cần truy cập theo index. Nó không thay thế List trong trường hợp vị trí số học, phần tử trùng lặp hoặc cập nhật tại index là quan trọng.

### Đừng nhận Set rồi giả định có thứ tự

Một phương thức nhận Set không được phép giả định thứ tự duyệt ổn định. HashSet không cam kết encounter order. Nếu thứ tự là yêu cầu bắt buộc, hãy nhận SequencedSet ngay tại ranh giới API:

~~~java
import java.util.SequencedSet;

class NavigationApi {
    static String firstAndLast(SequencedSet<String> items) {
        if (items.isEmpty()) {
            return "Danh sách rỗng";
        }
        return items.getFirst() + " -> " + items.getLast();
    }
}
~~~

Chuyển một HashSet sang LinkedHashSet không thể khôi phục thứ tự ban đầu vì HashSet vốn không cung cấp thứ tự đó. Nếu API phải nhận đầu vào chưa có thứ tự, cần quy định cách sắp xếp hoặc cách tạo thứ tự trước khi gọi phương thức.

## 3. Encounter order không đồng nghĩa với insertion order

SequencedSet cam kết một encounter order, nhưng interface không quy định nguồn gốc của thứ tự đó. Implementation có thể duy trì thứ tự chèn hoặc thứ tự sắp xếp:

~~~java
import java.util.LinkedHashSet;
import java.util.SequencedSet;
import java.util.TreeSet;

class OrderSources {
    static void showOrders() {
        SequencedSet<Integer> insertionOrder = new LinkedHashSet<>();
        insertionOrder.add(30);
        insertionOrder.add(10);
        insertionOrder.add(20);

        SequencedSet<Integer> sortedOrder = new TreeSet<>();
        sortedOrder.add(30);
        sortedOrder.add(10);
        sortedOrder.add(20);

        System.out.println(insertionOrder); // [30, 10, 20]
        System.out.println(sortedOrder);    // [10, 20, 30]
    }
}
~~~

Nếu API chỉ yêu cầu giữ nguyên thứ tự mà caller cung cấp, SequencedSet là đủ. Nếu API yêu cầu thứ tự chèn, hãy ghi rõ điều đó trong tài liệu phương thức và yêu cầu caller cung cấp encounter order tương ứng. Nếu API yêu cầu thứ tự tăng dần theo một Comparator, hãy cân nhắc nhận **SortedSet<E>** để thể hiện rõ hợp đồng sắp xếp.

Không nên mô tả một tham số SequencedSet chung chung là "theo thứ tự thêm vào" nếu phương thức vẫn chấp nhận TreeSet. Kiểu interface không thể xác nhận thứ tự đó bắt nguồn từ thao tác thêm phần tử.

## 4. Dùng wildcard khi API chỉ đọc phần tử

Nếu phương thức chỉ duyệt và đọc dữ liệu, tham số **SequencedSet<? extends E>** cho phép caller truyền một set của E hoặc một kiểu con của E. Đây là cách khai báo linh hoạt cho API chỉ tiêu thụ phần tử:

~~~java
import java.util.SequencedSet;
import java.util.function.Consumer;

class SequenceReader {
    static <E> void visit(
            SequencedSet<? extends E> values,
            Consumer<? super E> action
    ) {
        for (E value : values) {
            action.accept(value);
        }
    }
}
~~~

Với tham số này, phương thức có thể đọc từng phần tử như một E và chuyển nó cho Consumer<? super E>. Ví dụ, một SequencedSet<Integer> có thể được truyền vào phương thức xử lý Number.

~~~java
import java.util.LinkedHashSet;
import java.util.SequencedSet;
import java.util.List;

class SequenceReaderExample {
    static void run() {
        SequencedSet<Integer> codes =
                new LinkedHashSet<>(List.of(10, 20, 30));

        SequenceReader.visit(codes, (Number value) ->
                System.out.println(value.doubleValue()));
    }
}
~~~

Wildcard giúp API không đòi hỏi caller phải dùng đúng một type argument E. Tuy nhiên, **? extends E không biến collection thành immutable hoặc read-only ở cấp runtime**. Phương thức vẫn có thể gọi remove(Object) hoặc clear(); cam kết không thay đổi đầu vào vẫn phải được nêu và tuân thủ trong thiết kế.

## 5. Quy định rõ API có được thay đổi đầu vào không

SequencedSet không phải interface chỉ đọc. Nó có các phương thức thêm, xóa và lấy phần tử ở hai đầu. Nhưng không phải implementation nào cũng hỗ trợ thay đổi; ví dụ một wrapper unmodifiable có thể ném UnsupportedOperationException.

Nếu phương thức có chủ đích lấy bỏ phần tử đầu, hãy thể hiện hành vi đó rõ trong tên, tài liệu và kiểu tham số:

~~~java
import java.util.NoSuchElementException;
import java.util.SequencedSet;

class WorkQueueApi {
    // Yêu cầu: caller truyền một SequencedSet có thể thay đổi.
    static <E> E takeNext(SequencedSet<E> queue) {
        if (queue.isEmpty()) {
            throw new NoSuchElementException("Không còn phần tử");
        }
        return queue.removeFirst();
    }
}
~~~

Phương thức này làm thay đổi collection do caller sở hữu. Tài liệu API cần nói rõ phần tử đầu sẽ bị xóa, set rỗng dẫn đến exception nào và đầu vào phải hỗ trợ mutation. Nếu caller truyền một set không sửa đổi được, thao tác xóa sẽ thất bại bằng UnsupportedOperationException.

Nếu API không có lý do nghiệp vụ để thay đổi collection của caller, hãy giữ hợp đồng chỉ đọc và tránh gọi các phương thức mutation. Không nên xóa phần tử chỉ để thuận tiện cho thuật toán nội bộ rồi để caller bất ngờ nhận collection đã thay đổi.

## 6. Trả về SequencedSet và quyết định quyền sở hữu dữ liệu

Khi phương thức trả về SequencedSet, tài liệu API cần xác định:

- Thứ tự kết quả được tạo ra như thế nào.
- Kết quả có thể thay đổi hay không.
- Caller có thể thay đổi dữ liệu nội bộ của đối tượng cung cấp kết quả hay không.
- Kết quả có phải view gắn với collection khác hay một bản sao độc lập.

Nếu muốn trả về snapshot không cho caller sửa đổi, có thể sao chép dữ liệu rồi bọc bằng **Collections.unmodifiableSequencedSet**:

~~~java
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.SequencedSet;

class SequenceSnapshots {
    static <E> SequencedSet<E> snapshot(
            SequencedSet<? extends E> source
    ) {
        SequencedSet<E> copy = new LinkedHashSet<>(source);
        return Collections.unmodifiableSequencedSet(copy);
    }
}
~~~

Bản sao LinkedHashSet giữ encounter order của source tại thời điểm sao chép. Wrapper unmodifiable ngăn caller thay đổi set qua tham chiếu được trả về. Vì bản sao không còn chia sẻ cấu trúc với source, thay đổi source sau đó không làm thay đổi snapshot.

Ngược lại, chỉ gọi **Collections.unmodifiableSequencedSet(source)** tạo một view không sửa đổi trên chính source. Nếu code khác vẫn sửa source, view sẽ quan sát được những thay đổi đó. View unmodifiable không đồng nghĩa với snapshot độc lập.

## 7. Không nhầm SequencedSet với SortedSet

SequencedSet chỉ yêu cầu encounter order xác định. Nó không yêu cầu các phần tử phải được sắp xếp theo Comparable hoặc Comparator.

Nếu API cần các thao tác theo thứ tự sắp xếp, chẳng hạn lấy phần tử nhỏ nhất/lớn nhất theo comparator hoặc truy vấn một khoảng, hãy cân nhắc **SortedSet<E>** hoặc **NavigableSet<E>**:

- SortedSet biểu đạt thứ tự sắp xếp và cung cấp comparator cùng các thao tác đầu/cuối.
- NavigableSet bổ sung truy vấn phần tử gần nhất, ceiling/floor và các view theo khoảng.
- SequencedSet phù hợp khi cần encounter order nhưng không yêu cầu quan hệ sắp xếp.

Từ Java 21, SortedSet mở rộng SequencedSet. Vì vậy, một SortedSet có thể được truyền cho API nhận SequencedSet. Điều ngược lại không đúng: không thể giả định mọi SequencedSet đều là SortedSet.

## 8. Ví dụ thiết kế một API theo thứ tự hiển thị

Giả sử ứng dụng cần render các bước duy nhất theo đúng thứ tự caller đã chọn. API chỉ đọc đầu vào và giữ nguyên thứ tự:

~~~java
import java.util.SequencedSet;

class WorkflowRenderer {
    static String render(SequencedSet<? extends CharSequence> stages) {
        StringBuilder result = new StringBuilder();

        for (CharSequence stage : stages) {
            if (result.length() > 0) {
                result.append(" -> ");
            }
            result.append(stage);
        }

        return result.toString();
    }
}
~~~

Caller có thể truyền LinkedHashSet nếu thứ tự thêm vào chính là thứ tự hiển thị:

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedSet;

class WorkflowExample {
    static void run() {
        SequencedSet<String> stages =
                new LinkedHashSet<>(List.of("Draft", "Review", "Publish"));

        String output = WorkflowRenderer.render(stages);
        System.out.println(output); // Draft -> Review -> Publish
    }
}
~~~

Nếu caller truyền TreeSet, renderer sẽ nhận thứ tự sắp xếp của TreeSet. Điều này đúng với hợp đồng "giữ encounter order của đầu vào". Nếu sản phẩm yêu cầu riêng thứ tự Draft, Review, Publish, API cần nêu rõ nguồn thứ tự và caller cần chọn implementation phù hợp.

## 9. Checklist thiết kế API với SequencedSet

- [ ] Thứ tự gặp phần tử thực sự là một phần của kết quả hoặc hành vi API.
- [ ] Tính duy nhất của Set cũng là yêu cầu của dữ liệu.
- [ ] Dùng SequencedCollection hoặc List nếu phần tử trùng lặp được phép.
- [ ] Dùng Set nếu thứ tự không quan trọng.
- [ ] Phân biệt encounter order với thứ tự chèn và thứ tự sắp xếp.
- [ ] Ghi rõ phương thức chỉ đọc hay có thay đổi collection đầu vào.
- [ ] Không giả định mọi SequencedSet đều mutable.
- [ ] Dùng wildcard extends cho API chỉ tiêu thụ kiểu E khi phù hợp.
- [ ] Nếu trả về dữ liệu, xác định rõ kết quả là view, snapshot hay collection có thể thay đổi.
- [ ] Dùng SortedSet hoặc NavigableSet khi thứ tự comparator và truy vấn theo khoảng là hợp đồng.
- [ ] Không chuyển một Set không có thứ tự thành SequencedSet rồi tuyên bố đã giữ được thứ tự ban đầu.

## Tài liệu tham khảo

- [Java SE 21 API: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html)
- [Java SE 21 API: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API: Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html)
- [Java SE 21 API: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html)
- [Java SE 21 API: NavigableSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html)
- [JEP 431: Sequenced Collections](https://openjdk.org/jeps/431)
