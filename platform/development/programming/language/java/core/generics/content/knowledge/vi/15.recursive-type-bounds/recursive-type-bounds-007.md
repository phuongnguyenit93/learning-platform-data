# Khi giới hạn đệ quy làm API khó dùng và cách đơn giản hóa

## Mục tiêu

Giới hạn kiểu đệ quy (*F-bounded polymorphism*), thường viết `<T extends Self<T>>`, giúp một số API biểu đạt quan hệ với chính kiểu cụ thể của đối tượng. Tuy nhiên, áp dụng giới hạn này ở quá nhiều lớp, phương thức và interface có thể khiến API khó gọi, khó mở rộng và khó xử lý tập hợp đa hình.

Sau bài này, bạn có thể:

- Nhận ra lúc nào giới hạn đệ quy thực sự bảo vệ một quan hệ kiểu cần thiết, và lúc nào nó chỉ làm chữ ký khó đọc.
- Phân biệt nhu cầu **đọc thuộc tính**, **biến đổi trả về đúng kiểu**, **so sánh** và **xây dựng đối tượng** để chọn ràng buộc phù hợp.
- Đơn giản hóa API bằng interface nhỏ, `Comparator<? super T>`, `Comparable<? super T>`, callback (`UnaryOperator<T>`), wildcard hoặc overload có chủ đích.
- Hiểu giới hạn của “self type” trong Java, tránh raw type, ép kiểu không kiểm soát và giả định sai về kế thừa.

## 1. F-bound giải quyết vấn đề nào?

Một interface có thể muốn phương thức trả về đúng kiểu cài đặt:

```java
interface SelfNamed<S extends SelfNamed<S>> {
    String label();
    S rename(String newName);
}

record Task(String label) implements SelfNamed<Task> {
    @Override
    public Task rename(String newName) {
        return new Task(newName);
    }
}
```

Đây là ví dụ minh họa, có thể đặt các khai báo ở cấp top-level trong cùng tệp hoặc lồng trong một lớp. `Task` cung cấp kiểu `S = Task`; vì thế lời gọi `new Task("A").rename("B")` được kiểm tra và suy luận trả về `Task`.

Một hàm dùng chung thường được viết:

```java
static <S extends SelfNamed<S>> S renameStrong(S value, String newName) {
    return value.rename(newName);
}
```

Chữ ký thể hiện được hai yêu cầu: tham số phải tuân theo hợp đồng `SelfNamed<S>`, và kết quả có kiểu `S`. Đây là lý do chính đáng để dùng F-bound **nếu người gọi thực sự cần quan hệ cùng kiểu ấy**.

Nhưng F-bound được thiết kế cho một quan hệ kiểu chuyên biệt, không phải quy tắc mặc định của mọi API hướng đối tượng. Khi tác vụ chỉ cần tên, thứ tự hiển thị hoặc callback từ người gọi, ràng buộc tự tham chiếu thường là thừa.

## 2. Các dấu hiệu API đã trở nên khó dùng

### 2.1. Chữ ký quá sâu so với nhu cầu thực tế

Giả sử chức năng chỉ hiển thị danh sách nhãn, nhưng API lại nhận:

```java
// Ví dụ minh họa bên trong một lớp:
static <S extends SelfNamed<S>> void printLabels(
        java.util.List<S> items) {
    for (S item : items) {
        System.out.println(item.label());
    }
}
```

API này yêu cầu mọi phần tử cùng một kiểu `S` tự tham chiếu, dù thao tác chỉ gọi `label()`. Nó không thuận tiện khi giao diện cần hiển thị hỗn hợp `Task`, `Signal` hoặc các đối tượng khác đều có nhãn. Nếu `S` chỉ xuất hiện ở đây mà không dùng cho kiểu trả về hoặc một phép toán phụ thuộc cùng kiểu, giới hạn đệ quy không đem lại giá trị thực tế.

Một hợp đồng nhỏ phù hợp hơn:

```java
interface Labelled {
    String label();
}

static void printLabels(
        java.util.List<? extends Labelled> items) {
    for (Labelled item : items) {
        System.out.println(item.label());
    }
}
```

Đoạn này là mẫu khai báo minh họa: đặt phương thức trong một lớp, cho các kiểu đối tượng triển khai `Labelled`. Mẫu mới chấp nhận `List<Task>`, `List<Signal>`, hoặc một `List<Labelled>` chứa cả hai. Wildcard `? extends Labelled` thể hiện rằng phương thức **đọc** phần tử thỏa mãn `Labelled` mà không cần biết subtype cụ thể.

### 2.2. Người gọi có biến kiểu rộng hoặc tập hợp không đồng nhất

Giới hạn đệ quy dễ gây khó xử khi code ở ranh giới hệ thống chỉ biết một interface tổng quát:

```java
SelfNamed<?> item = new Task("Draft");
// renameStrong(item, "Done"); // Không khớp được quan hệ S extends SelfNamed<S>.
System.out.println(item.label()); // Đọc thuộc tính vẫn hợp lệ.
```

Đoạn này chỉ minh họa trong ngữ cảnh đã khai báo `SelfNamed`, `Task` và `renameStrong` ở trên. Wildcard nói rằng tồn tại một tham số kiểu chưa biết; nó **không nói** bản thân kiểu tham chiếu rộng `SelfNamed<?>` là một `S` cụ thể thỏa `S extends SelfNamed<S>`. Vì vậy, không nên buộc lớp giao diện, logger hay serializer phải khôi phục thông tin subtype mà nó không thực sự cần.

Trong những trường hợp này, thiết kế dễ dùng hơn là tách chức năng đọc ra interface không generic (`Labelled`), hoặc đưa thao tác phụ thuộc subtype về nơi còn biết kiểu cụ thể.

### 2.3. F-bound “rò rỉ” qua nhiều tầng

Ví dụ một tầng repository chỉ cần lấy nhãn, nhưng interface repository lại định nghĩa `Repository<T extends SelfNamed<T>>`, rồi service dùng `Service<T extends SelfNamed<T>>`, controller tiếp tục dùng `Controller<T extends SelfNamed<T>>`. Cả ba tầng phải mang theo ràng buộc dù chỉ một tác vụ nội bộ cần tự kiểu. Mỗi lớp mới kéo theo khai báo generic dài, lỗi suy luận kiểu khó đọc và thêm phụ thuộc vào cơ chế `SelfNamed`.

Hãy hỏi: **Tầng này có thực sự gọi `rename(...)` theo cùng S, so sánh hai S, hoặc trả lại S không?** Nếu không, hãy cho tầng đó phụ thuộc vào interface nhỏ nhất phù hợp, hoặc chỉ tham số hóa `<T>` nếu cần giữ kiểu truyền qua.

### 2.4. Kế thừa, subclass và kiểu so sánh không đồng nhất

Giới hạn kiểu quá chặt như `<T extends Comparable<T>>` có thể loại các subtype hợp lệ mà chỉ triển khai `Comparable<Base>` thông qua lớp cha. Đây không nhất thiết là lý do bỏ generic; đôi khi chỉ cần ràng buộc chính xác hơn: `<T extends Comparable<? super T>>`. Phần 5 minh họa rõ.

## 3. Chọn thiết kế dựa trên việc API thực sự cần làm

| Nhu cầu | Chữ ký dễ dùng | Có cần F-bound? |
| --- | --- | --- |
| Đọc nhãn/thông tin chung | `void print(List<? extends Labelled> items)` | Không; dùng interface khả năng nhỏ. |
| Giữ nguyên kiểu truyền qua một phép biến đổi do người gọi cung cấp | `<T> T transform(T value, UnaryOperator<T> op)` | Không; callback chịu trách nhiệm tạo `T`. |
| So sánh theo luật do người gọi quyết định | `<T> T greater(T a, T b, Comparator<? super T> cmp)` | Không; thứ tự nằm trong comparator. |
| So sánh theo thứ tự tự nhiên của đối tượng | `<T extends Comparable<? super T>> T max(...)` | Cần bound trên `Comparable`, nhưng thường nên cho phép `? super T`. |
| Gọi một phương thức tự kiểu và bảo toàn đúng kiểu kết quả | `<S extends SelfNamed<S>> S rename(S value, ...)` | Có thể cần F-bound. |
| Cài đặt chính sách generic theo loại enum | `<E extends Enum<E>> ...` | Có; phù hợp với ràng buộc thư viện Java. |
| Một builder cụ thể, không cần hệ phân cấp builder | `final class UserBuilder { UserBuilder name(...); }` | Không; kiểu trả về cụ thể đã đủ. |

Đừng thay toàn bộ F-bound bằng `Object`, raw type hay cast: chúng làm mất kiểm tra kiểu. Cách đơn giản hóa tốt là thay **hợp đồng quá mạnh** bằng hợp đồng vẫn biểu đạt đủ hành vi cần thiết.

## 4. Ví dụ Java 17 hoàn chỉnh: nhiều chiến lược trong một chương trình

**Tệp `SimplerBoundsDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.function.UnaryOperator;

public class SimplerBoundsDemo {
    interface Labelled {
        String label();
    }

    interface SelfNamed<S extends SelfNamed<S>> extends Labelled {
        S rename(String newName);
    }

    record Task(String label, int urgency) implements SelfNamed<Task> {
        @Override
        public Task rename(String newName) {
            return new Task(newName, urgency);
        }
    }

    record Signal(String label, int level) implements SelfNamed<Signal> {
        @Override
        public Signal rename(String newName) {
            return new Signal(newName, level);
        }
    }

    static <S extends SelfNamed<S>> S strongRename(S item, String name) {
        return item.rename(name);
    }

    static List<String> labels(List<? extends Labelled> values) {
        List<String> result = new ArrayList<>();
        for (Labelled value : values) {
            result.add(value.label());
        }
        return result;
    }

    static <T> T transform(T value, UnaryOperator<T> operation) {
        return operation.apply(value);
    }

    static <T> T greater(T left, T right, Comparator<? super T> order) {
        return order.compare(left, right) >= 0 ? left : right;
    }

    static class Document implements Comparable<Document> {
        final int rank;

        Document(int rank) {
            this.rank = rank;
        }

        @Override
        public int compareTo(Document other) {
            return Integer.compare(rank, other.rank);
        }
    }

    static final class SignedDocument extends Document {
        SignedDocument(int rank) {
            super(rank);
        }
    }

    static <T extends Comparable<? super T>> T maxNatural(
            List<? extends T> values) {
        return Collections.max(values);
    }

    public static void main(String[] args) {
        Task draft = new Task("Draft", 3);
        Signal signal = new Signal("Disk", 8);

        System.out.println(strongRename(draft, "Released").label());
        System.out.println(labels(List.of(draft, signal)));

        Task updated = transform(draft, t -> t.rename("Reviewed"));
        System.out.println(updated.label());

        Task chosen = greater(
                draft,
                new Task("Urgent", 7),
                Comparator.comparingInt(Task::urgency));
        System.out.println(chosen.label());

        SignedDocument result = maxNatural(
                List.of(new SignedDocument(2), new SignedDocument(5)));
        System.out.println(result.rank);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 SimplerBoundsDemo.java
java SimplerBoundsDemo
```

**Stdout (đã kiểm chứng khi chạy):**

```text
Released
[Draft, Disk]
Reviewed
Urgent
5
```

Phân tích:

1. `strongRename` vẫn dùng F-bound vì phải gọi `rename` và giữ kết quả dưới đúng kiểu `Task`.
2. `labels` bỏ ràng buộc tự tham chiếu. Nó đọc danh sách có cả `Task` lẫn `Signal`, vì cả hai triển khai `Labelled`. Kết quả là `[Draft, Disk]`.
3. `transform` không biết đối tượng có những phương thức nào; `UnaryOperator<T>` được truyền vào từ chỗ biết `Task`, vì vậy kết quả vẫn được suy luận thành `Task`. Phép biến đổi có thể thay đổi tham chiếu và không có cam kết bất biến trừ khi kiểu/callback tự đảm bảo.
4. `greater` dùng `Comparator<? super T>` để người gọi chọn tiêu chí xếp hạng. Với `Task`, ta dùng `urgency`; không phải buộc `Task` khai báo `Comparable<Task>`.
5. `SignedDocument` kế thừa `Comparable<Document>` qua `Document`. Giới hạn `Comparable<? super T>` cho phép so sánh các `SignedDocument` dựa trên quan hệ với lớp cha `Document`. Giá trị lớn nhất có `rank = 5`.

Chú ý trong mã: `List.of(...)` tạo danh sách không sửa được; `labels` chỉ đọc. Đừng suy ra từ `List<? extends Labelled>` rằng có thể thêm bất kỳ `Labelled` nào vào danh sách: kiểu phần tử thực tế có thể hẹp hơn.

## 5. Nới ràng buộc natural ordering mà không bỏ an toàn kiểu

Nếu `Document implements Comparable<Document>` và `SignedDocument extends Document`, thì `SignedDocument` kế thừa `Comparable<Document>`; nó **không** tự động là `Comparable<SignedDocument>`. Một bound `<T extends Comparable<T>>` có thể quá chặt khi thuật toán cần trả đúng `SignedDocument`.

Chữ ký chuẩn thường nên là:

```java
static <T extends Comparable<? super T>> T maxNatural(
        List<? extends T> values) {
    return java.util.Collections.max(values);
}
```

`Comparable<? super T>` cho phép cách so sánh nhận một supertype của `T`, còn `List<? extends T>` cho phép đọc phần tử tương thích. Đây là một **nới lỏng có kiểm soát** chứ không phải bỏ F-bound hoặc dùng raw `Comparable`. Ví dụ chạy ở mục 4 đã chứng minh lời gọi với `List<SignedDocument>` và giữ kết quả là `SignedDocument`.

Nếu cần nhiều thứ tự khác nhau, không có natural order, hoặc tiêu chí thuộc ngữ cảnh caller, chọn `Comparator<? super T>` và **bỏ hẳn ràng buộc Comparable khỏi T**. Trọng tâm lựa chọn thiết kế ở đây là biết khi nào *nới bound* và khi nào *đưa hành vi vào strategy*, thay vì tái phân tích chi tiết quan hệ kế thừa so sánh.

## 6. Tách chức năng đọc và chức năng tự kiểu

Một interface vừa chứa thông tin hiển thị vừa chứa thao tác trả về subtype thường khiến tầng chỉ đọc phải gánh ràng buộc tự tham chiếu. Tách thành hai vai trò:

```java
interface Labelled {
    String label();
}

interface SelfNamed<S extends SelfNamed<S>> extends Labelled {
    S rename(String newName);
}
```

API hiển thị chỉ tham chiếu `Labelled`:

```java
static String display(Labelled value) {
    return value.label();
}
```

API thao tác trả lại subtype mới cần `SelfNamed<S>`:

```java
static <S extends SelfNamed<S>> S renameAndReturn(
        S value, String newName) {
    return value.rename(newName);
}
```

Các phương thức minh họa trên được đặt bên trong lớp và các interface khai báo ở cùng scope phù hợp.

Ưu điểm là quan hệ kiểu phức tạp nằm ở đúng chỗ cần nó. Một component chỉ nhận `Labelled` không cần hiểu F-bound, generic capture, hay kiểu cụ thể của thao tác `rename`. Nếu sau này thêm `Signal`, phần hiển thị có thể tiếp tục hoạt động mà không thay đổi chữ ký.

Nếu việc đổi tên thực tế là **tác vụ riêng của ứng dụng** chứ không phải hành vi bản chất của đối tượng, có thể bỏ `SelfNamed` khỏi domain model và truyền một `UnaryOperator<T>` từ tầng chịu trách nhiệm. Điều này giúp một model không phải triển khai interface chỉ để phục vụ một tiện ích bên ngoài.

## 7. Dùng callback để giữ T mà không tự ràng buộc

Ví dụ hàm `transform` trong chương trình:

```java
static <T> T transform(T value, java.util.function.UnaryOperator<T> operation) {
    return operation.apply(value);
}
```

Người gọi quyết định biến đổi:

```java
Task task = new Task("Draft", 3);
Task reviewed = transform(task, value -> value.rename("Reviewed"));
```

Đoạn gọi trên nằm trong lớp `SimplerBoundsDemo`, nơi `Task` và `transform` đã được định nghĩa. Trình biên dịch suy luận `T = Task`. Hàm `transform` không buộc mọi loại dữ liệu phải triển khai một interface generic nào.

Có thể dùng các dạng callback khác theo đúng hướng dữ liệu:

- `Function<? super T, ? extends R>` khi đọc một T để tạo ra R, như ánh xạ domain object thành DTO.
- `Consumer<? super T>` khi chỉ xử lý T mà không có kết quả.
- `Predicate<? super T>` khi lọc/kiểm tra T.
- `Comparator<? super T>` khi so sánh hai T.
- `UnaryOperator<T>` khi biến đổi và trả về cùng kiểu T.

Không phải callback lúc nào cũng thay cho F-bound. Nếu hợp đồng cốt lõi thực sự đòi hỏi mọi implementation phải cung cấp `rename`, để compiler kiểm tra hợp đồng đó là giá trị của interface. Callback phù hợp khi hành vi có thể được cung cấp từ bên ngoài hoặc thay đổi theo ngữ cảnh.

## 8. Đừng dùng F-bound làm lời bảo đảm rằng `S` chính là receiver

`interface SelfNamed<S extends SelfNamed<S>>` chỉ đòi `S` đáp ứng quan hệ `SelfNamed<S>`. Nó không cấm một lớp khác triển khai `SelfNamed<Task>` nếu `Task` là đối số hợp lệ.

```java
// Với Task(String label) implements SelfNamed<Task> ở mục 1:
record Alias(String label) implements SelfNamed<Task> {
    @Override public Task rename(String value) {
        return new Task(value);
    }
}
```

`Alias` có thể trả `Task` đúng chữ ký, nhưng không thành `SelfNamed<Alias>`; vì vậy không thể dùng `Alias` như `S=Alias` trong `renameStrong(S,...)`. Muốn hợp đồng mạnh hơn, cần thiết kế class/constructor, các lớp `final`/`sealed`, hoặc factory kiểm soát và kiểm thử riêng. Tương tự, `return (S)this` trong một base generic là cast unchecked, không tự an toàn.

Khi mục tiêu chỉ là đọc một `label()` hoặc chuyển đổi theo callback do caller cung cấp, giao diện `Labelled` hay `UnaryOperator<T>` ở các mục trước đơn giản hơn mà không hứa “self type” thiếu bằng chứng. Trường hợp self-type sai kiểu, lớp cháu kế thừa `S` đã cố định và ngoại lệ do erasure được chứng minh đầy đủ ở bài về giới hạn của F-bound.

## 9. Builder: trường hợp thường bị lạm dụng F-bound

Trong thư viện framework có nhiều builder kế thừa, F-bound có thể giữ kiểu builder ở những lời gọi nối chuỗi. Nhưng với một builder cụ thể, có thể chỉ cần:

```java
final class UserBuilder {
    private String name;

    UserBuilder name(String value) {
        this.name = value;
        return this;
    }

    String buildName() {
        return name;
    }
}
```

Đây là đoạn mã minh họa khai báo lớp độc lập. Với `new UserBuilder().name("An").buildName()`, kiểu trả về cụ thể đã đủ để gọi nối chuỗi, không cần tạo `Builder<B extends Builder<B>>`.

Chỉ bổ sung F-bound cho hệ builder khi có **yêu cầu kế thừa builder thật sự**, ví dụ phương thức ở lớp cha phải trả về kiểu builder lớp con để tiếp tục gọi phương thức của lớp con. Khi đó phải đánh giá rủi ro cast, ràng buộc subclass và thiết kế constructor/protected method. Nhiều API có thể tránh sự phức tạp bằng composition hoặc các builder độc lập.

## 10. Xử lý wildcard/capture và lỗi suy luận kiểu

Một số lỗi compiler thường gặp khi dùng giới hạn đệ quy:

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `inference variable ... has incompatible bounds` | Trình biên dịch không thể tìm một T đáp ứng đồng thời các ràng buộc kiểu. | Kiểm tra T có thật sự cần xuất hiện ở tất cả tham số; tách tác vụ đọc ra interface nhỏ. |
| `capture of ?` hoặc `CAP#1` | Wildcard giữ một kiểu chưa biết; compiler không được giả định hai wildcard là cùng một kiểu. | Duy trì T có tên qua cùng phương thức generic nếu thực sự cần quan hệ; hoặc chỉ dùng thao tác không phụ thuộc subtype. |
| `List<Child>` không khớp `List<Parent>` | Generic collection của Java **bất biến** (*invariant*), dù `Child extends Parent`. | Chỉ đọc: `List<? extends Parent>`; nếu cần thêm Parent thì phải xem xét API nhận `List<? super Parent>` và cách tiêu thụ. |
| `Comparable<Child>` không khớp với implement kế thừa `Comparable<Parent>` | Bound quá chặt trong khi phép so sánh nhận một supertype phù hợp. | Dùng `Comparable<? super Child>` hoặc một `Comparator`. |
| Cảnh báo `rawtypes`/`unchecked` | Bỏ tham số generic, hoặc dùng cast để vượt lỗi suy luận kiểu. | Thiết kế lại giới hạn, overload hay callback; tránh tắt cảnh báo vì mục tiêu “cho chạy”. |

Một cách làm hữu ích: **bắt đầu từ thao tác đang cần**, không bắt đầu từ ràng buộc tổng quát nhất. Nếu phương thức chỉ cần `label()`, dùng `Labelled`. Nếu nó chỉ so sánh, nhận comparator. Nếu nó phải gọi `S rename(...)` và giữ trả về `S`, F-bound có thể là lựa chọn phù hợp.

Khi cần xử lý một danh sách nhiều subtype nhưng mỗi phần tử có phép biến đổi riêng, đừng gom tất cả vào một tham số kiểu S rồi ép kiểu từng phần tử. Có thể để từng thành phần tạo/cập nhật đối tượng ở nơi còn giữ kiểu cụ thể, sau đó đưa kết quả về lớp hiển thị theo một interface chung. Đây là phân chia trách nhiệm giúp API dễ kiểm thử và không phụ thuộc vào việc đánh lừa compiler.

## 11. Cách refactor một API phức tạp

Giả sử một interface được dùng ở nhiều module:

```java
interface Entity<E extends Entity<E>> {
    String id();
    E refresh();
}
```

Nếu phần lớn người gọi chỉ cần `id()`, có thể cải tiến theo các bước:

1. **Kiểm kê nhu cầu của caller:** caller nào chỉ đọc `id()`, caller nào cần `refresh()` và nhận đúng E, caller nào chỉ chuyển đối tượng qua các tầng.
2. **Rút hợp đồng nhỏ:** thêm `Identified { String id(); }` rồi cho `Entity<E> extends Identified`. Các API chỉ đọc chuyển sang nhận `Identified` hoặc `List<? extends Identified>`.
3. **Giữ giới hạn tự kiểu tại điểm cần thiết:** chức năng `refresh` vẫn có thể dùng `<E extends Entity<E>> E reload(E value)`. Với những tình huống refresh do service điều khiển, cân nhắc `<T> T refresh(T value, UnaryOperator<T> strategy)`.
4. **Điều chỉnh so sánh riêng:** nếu API chọn thực thể “tốt nhất”, dùng `Comparator<? super T>` thay vì ép mọi entity phải có `Comparable<Entity<?>>` hoặc một bound đệ quy.
5. **Đánh giá tính tương thích:** overload nhận interface rộng hơn thường thuận tiện, nhưng Java có type erasure; hai overload chỉ khác `List<Entity<?>>` và `List<Identified>` có thể đụng tên sau xóa kiểu. Khi đó đổi tên phương thức hoặc dùng chữ ký thật sự phân biệt. Kiểm thử lại mã gọi hiện hữu trước khi phát hành thư viện.

Các khai báo/phương thức ở mục này là **mẫu thiết kế minh họa**, không ghép nguyên văn với chương trình `SimplerBoundsDemo` để chạy. Tư tưởng cốt lõi: chỉ giữ ràng buộc phức tạp ở những điểm mà nó bảo vệ hành vi hoặc quan hệ kiểu có ý nghĩa.

## 12. Khi nào nên giữ F-bound?

**Nên giữ** khi API cần một trong những điều sau:

- Tương tác giữa hai giá trị **cùng một kiểu cụ thể**, như `Comparable<T>`.
- Phương thức trên chính model tạo/trả về loại subtype được khai báo qua tham số S; kết quả phải giữ kiểu đó qua các lớp generic.
- Hợp đồng gắn với enum cụ thể: `<E extends Enum<E>>` làm việc với `EnumSet<E>`, `EnumMap<E, V>` hoặc `Enum.valueOf(Class<E>, ...)`.
- Một thư viện có phân cấp kiểu được kiểm soát, đã chấp nhận chi phí triển khai và kiểm tra tính hợp lệ của self-type.

**Nên đơn giản hóa** khi thao tác chỉ cần đọc dữ liệu chung, thực hiện transform tùy biến, so sánh theo tiêu chí bên ngoài, cung cấp builder độc lập, hoặc chỉ chuyển một đối tượng có kiểu T đi qua service mà không sử dụng hành vi F-bound.

Đừng dùng độ dài chữ ký làm tiêu chí duy nhất: một ràng buộc dài nhưng chứng minh được bất biến quan trọng vẫn tốt hơn API ngắn phải ép kiểu không an toàn. Ngược lại, một ràng buộc không đóng góp bảo đảm nào cần được loại khỏi bề mặt công khai.

## 13. Bài tập và đáp án

**Bài 1.** Một bảng UI chỉ cần hiện `id()` của `List<Order>` và `List<Customer>`. Có nên yêu cầu cả hai implements `Entity<E extends Entity<E>>`?

**Đáp án:** Không cần nếu cả hai chỉ dùng chung `id()`. Tách `Identified` và nhận `List<? extends Identified>` ở lớp hiển thị.

**Bài 2.** Vì sao `<T extends Comparable<T>>` có thể quá chặt khi subtype thừa hưởng `Comparable<Parent>`?

**Đáp án:** Subtype không nhất thiết triển khai `Comparable<Subtype>`. `Comparable<? super T>` diễn đạt đúng nhu cầu: phép so sánh có thể nhận một kiểu cha của T.

**Bài 3.** Cần hàm trả về đúng T sau khi người gọi quyết định cách sửa. Có bắt buộc phải dùng `T extends Self<T>` không?

**Đáp án:** Không. `<T> T transform(T value, UnaryOperator<T> op)` giữ T và cho người gọi cung cấp hành vi.

**Bài 4.** `interface Self<T extends Self<T>>` có bảo đảm rằng `class A implements Self<A>` và ngăn mọi biến thể khác không?

**Đáp án:** Không. Một lớp có thể chọn một T khác nếu T đáp ứng bound; muốn thiết kế self-type vững hơn phải kiểm soát cách triển khai, cấu trúc lớp và logic liên quan.

**Bài 5.** Một builder final duy nhất có phương thức `name(...)` trả lại chính builder. Có cần `Builder<B extends Builder<B>>`?

**Đáp án:** Thường không. Trả về trực tiếp kiểu builder cụ thể là đủ và làm API dễ đọc hơn.

---

**Kết luận:** F-bound hữu ích khi sự phụ thuộc giữa kiểu hiện tại và kiểu tham số/trả về là phần thiết yếu của hợp đồng. Để API Java dễ sử dụng, hãy giữ ràng buộc đó ở nơi cần bảo toàn cùng kiểu; với các thao tác đọc, so sánh, chuyển đổi và xây dựng đối tượng đơn giản, ưu tiên interface nhỏ, wildcard phù hợp và callback có kiểu rõ ràng.
