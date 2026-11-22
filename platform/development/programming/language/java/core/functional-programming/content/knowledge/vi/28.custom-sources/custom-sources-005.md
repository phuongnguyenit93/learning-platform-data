# `IMMUTABLE`, `CONCURRENT` và `NONNULL` trong `Spliterator` — nguồn Stream tùy chỉnh

## 1. Ba đặc tính này dùng để làm gì?

Một `Stream` có thể lấy phần tử từ `List`, mảng, hàng đợi hoặc một nguồn do ứng dụng tự viết. Khi tạo Stream từ nguồn tùy chỉnh, bạn thường xây dựng một `Spliterator<T>` và truyền nó cho `StreamSupport.stream(...)`.

`Spliterator` không chỉ biết **cách duyệt và chia phần tử**; nó còn công bố các đặc tính (*characteristics*) của nguồn. Trong số đó, ba cờ dễ gây nhầm lẫn là:

- **`Spliterator.IMMUTABLE`**: nguồn không thể bị **thay đổi về cấu trúc** trong quá trình duyệt theo hợp đồng của nguồn.
- **`Spliterator.CONCURRENT`**: nguồn cho phép **thay đổi cấu trúc đồng thời** với việc duyệt mà không cần đồng bộ bên ngoài.
- **`Spliterator.NONNULL`**: các phần tử mà spliterator đưa tới consumer **đều khác `null`**.

Điểm trọng tâm: đây là **cam kết về nguồn và quá trình duyệt**, không phải các tùy chọn bật thêm để tự động tăng tốc. Khai báo cờ không biến một mảng đang bị sửa thành bất biến, không biến `ArrayList` thành cấu trúc thread-safe, và không tự lọc bỏ phần tử `null`.

Ví dụ ngắn:

```java
int flags = Spliterator.ORDERED
        | Spliterator.IMMUTABLE
        | Spliterator.NONNULL;

Spliterator<String> sp = Spliterators.spliterator(
        new String[]{"red", "green", "blue"}, flags);
```

Đoạn mã trên minh họa cách khai báo với các import `java.util.Spliterator` và `java.util.Spliterators`. **Chỉ được khai báo `IMMUTABLE` khi ứng dụng thực sự bảo đảm mảng nguồn không bị sửa về cấu trúc trong thời gian duyệt.** Mảng Java vẫn có thể bị chỉnh sửa (`array[i] = ...`) nếu còn tham chiếu có quyền ghi; `final` trên biến mảng không làm các phần tử thành bất biến. Vì vậy bài sẽ dùng một snapshot riêng và không cho code khác sửa nó.

Sau bài học, bạn có thể phân biệt ba đặc tính trên, chọn cờ đúng cho `Spliterator` tùy chỉnh, làm ví dụ Java 17 chạy độc lập, hiểu ngữ nghĩa của nguồn concurrent/weakly consistent, và kiểm thử **hành vi thực** thay vì chỉ kiểm tra bit cờ.

## 2. Vị trí của `Spliterator` trong pipeline

Một nguồn Stream tùy chỉnh thường đi theo mô hình:

```text
Dữ liệu nguồn (T)
    │
    ▼
Spliterator<T>
    ├── tryAdvance(action): chuyển một phần tử cho action
    ├── forEachRemaining(action): duyệt phần còn lại
    ├── trySplit(): chia công việc thành hai phần nếu có thể
    ├── estimateSize(): ước lượng số phần tử còn lại
    └── characteristics(): công bố tính chất của nguồn
    │
    ▼
StreamSupport.stream(spliterator, parallel)
    │
    ▼
filter → map → sorted → ...
    │
    ▼
terminal operation: toList, count, reduce, collect, ...
```

`StreamSupport.stream(sp, false)` tạo Stream tuần tự; tham số `true` cho phép Stream vận hành song song khi các thao tác và nguồn phù hợp. Việc bật song song **không sửa sai** một spliterator có characteristic được khai báo không đúng, và cũng không bảo đảm chương trình luôn sử dụng nhiều thread hay nhanh hơn.

Một vài hàm quan trọng:

```java
boolean has = sp.hasCharacteristics(Spliterator.NONNULL);

int flags = sp.characteristics();

long estimate = sp.estimateSize();

long exact = sp.getExactSizeIfKnown();
```

`hasCharacteristics(mask)` kiểm tra những bit được chỉ định trong mask; `getExactSizeIfKnown()` chỉ trả về kích thước chính xác khi spliterator có `SIZED`, còn không trả `-1`. Khi làm Stream từ một nguồn động, đừng mặc định kích thước ước lượng luôn là số phần tử cuối cùng được tiêu thụ.

## 3. `IMMUTABLE`: không có sửa đổi cấu trúc của nguồn trong lúc duyệt

`IMMUTABLE` nói rằng **nguồn phần tử không thể bị thay đổi về cấu trúc** (theo hợp đồng của nguồn) trong quá trình duyệt. Những ví dụ về thay đổi cấu trúc: thêm hoặc xóa phần tử, hoặc thay phần tử trong một mảng/dãy khi nguồn coi thao tác ấy là thay đổi cấu trúc.

Nó **không nói** rằng:

- Mỗi object được duyệt phải là immutable object.
- Mọi field của object luôn là `final`.
- Spliterator tự sao chép dữ liệu thành snapshot.
- Không có thread khác trên máy đang hoạt động.
- Có thể đánh dấu cờ trên một `ArrayList` vẫn đang bị thay đổi chỉ vì biến tham chiếu được khai báo `final`.

Ví dụ, `List<Box>` có thể không thay đổi số lượng hoặc vị trí các phần tử trong lúc duyệt, nhưng các `Box` chứa field có thể sửa. `IMMUTABLE` nói về **cấu trúc nguồn**, không khẳng định những `Box` đó bất biến sâu.

### Cách thiết kế dễ kiểm chứng: snapshot đóng gói

Giả sử lớp nguồn tùy chỉnh sao chép các chuỗi từ đầu vào vào mảng **private**, không để lộ mảng và không cung cấp phương thức sửa:

```java
final class SnapshotWords {
    private final String[] values;

    SnapshotWords(List<String> input) {
        values = List.copyOf(input).toArray(String[]::new);
    }

    Spliterator<String> spliterator() {
        return Spliterators.spliterator(
                values,
                Spliterator.ORDERED
                        | Spliterator.IMMUTABLE
                        | Spliterator.NONNULL);
    }
}
```

Đây là trích đoạn; chương trình độc lập phía dưới có đủ import và kiểm thử. `List.copyOf(input)` tạo danh sách không cho sửa cấu trúc và từ chối phần tử `null`; ta lấy các chuỗi sang mảng private để spliterator hoạt động trên dữ liệu ổn định. Không có method trả trực tiếp mảng private; class không sửa mảng sau khi xây dựng. Vì các phần tử là `String` bất biến, ví dụ này còn dễ kiểm tra hơn trường hợp phần tử là object mutable.

Lưu ý rằng `Spliterators.spliterator(array, additionalCharacteristics)` **tin vào những cờ được truyền**; nó không tự kiểm chứng mọi điều kiện về bất biến và non-null của dữ liệu. Nếu thiết kế của bạn vẫn để mã khác giữ tham chiếu tới mảng và thay giá trị trong khi Stream duyệt, bạn đã khai báo cờ sai.

### `IMMUTABLE` không phải “luôn tạo snapshot”

Một spliterator có thể lấy trực tiếp dữ liệu từ một cấu trúc thực sự bất biến. Hoặc nó có thể lấy từ snapshot bất biến mà bạn chủ động tạo trước. Chính **bạn** phải bảo đảm nguồn thực tế đáp ứng điều đã công bố. Cờ không tự biến dữ liệu nguồn thành snapshot.

`List.copyOf` giúp phòng tránh thay đổi cấu trúc qua danh sách trả về, nhưng với List chứa phần tử mutable, các object bên trong vẫn có thể bị thay đổi. Còn `Collections.unmodifiableList(backingList)` chỉ tạo **view không cho sửa qua view**; nếu code khác vẫn có `backingList` và sửa nó, dữ liệu bên dưới vẫn thay đổi. Không nên xem mọi unmodifiable view đều tương đương snapshot độc lập.

## 4. `CONCURRENT`: nguồn cho phép sửa cấu trúc đồng thời

`CONCURRENT` mô tả một nguồn được thiết kế để có thể **thay đổi cấu trúc trong lúc đang duyệt**, mà người dùng không phải khóa toàn bộ nguồn bằng đồng bộ bên ngoài.

Ví dụ trong Java Collections Framework là `ConcurrentLinkedQueue`:

```java
ConcurrentLinkedQueue<String> queue =
        new ConcurrentLinkedQueue<>(List.of("red", "green"));

Spliterator<String> sp = queue.spliterator();

System.out.println(
        sp.hasCharacteristics(Spliterator.CONCURRENT)); // true
```

`ConcurrentLinkedQueue` hỗ trợ thêm/xóa đồng thời, và spliterator của nó **weakly consistent**: không thất bại vì những sửa đổi đồng thời theo cách fail-fast như một số collection thông thường; nó có thể phản ánh một số (hoặc không tất cả) thay đổi xuất hiện khi duyệt. Đừng coi kết quả là ảnh chụp nhất quán tại một thời điểm cố định.

### Concurrent không có nghĩa “mỗi element xuất hiện đúng một lần trong snapshot”

Nếu thread A duyệt `ConcurrentLinkedQueue` và thread B thêm/xóa phần tử, bạn **không được** suy ra danh sách kết quả bằng chính xác tập phần tử ở thời điểm bắt đầu hoặc kết thúc. Kết quả có thể phụ thuộc thời điểm tương tác giữa các thread. Nếu nghiệp vụ cần một snapshot ổn định hoặc độ chính xác giao dịch, hãy thiết kế cơ chế snapshot/đồng bộ phù hợp thay vì chỉ dựa trên cờ `CONCURRENT`.

Nguồn concurrent cũng không đồng nghĩa:

- Mọi object được duyệt đều thread-safe.
- Mọi `Consumer`/lambda hoặc collector cập nhật trạng thái chung đều thread-safe.
- Có thể gọi đồng thời `tryAdvance` trên **cùng một spliterator instance** tùy ý. Theo thiết kế Spliterator, cần tuân thủ hợp đồng chia nhánh và sở hữu quá trình duyệt; cờ này nói về **nguồn**, không phải giấy phép dùng chung đối tượng spliterator giữa nhiều thread.
- Stream tạo ra có encounter order hay không. `CONCURRENT` và `ORDERED` là hai đặc tính riêng.
- Mọi loại concurrent collection có cùng chính sách duyệt, kích thước hoặc thứ tự.

### Không khai báo `CONCURRENT` để “cứu” `ArrayList`

Ví dụ sai:

```java
List<String> data = new ArrayList<>(List.of("a", "b"));
Spliterator<String> wrong = Spliterators.spliterator(
        data, Spliterator.CONCURRENT);
```

Dòng này có thể tạo được spliterator, nhưng **không biến `ArrayList` thành nguồn được phép thay đổi cấu trúc đồng thời một cách an toàn**. Nếu thread khác thêm/xóa, hành vi và mức nhất quán không đáp ứng lời hứa của cờ. Hãy dùng cấu trúc concurrent thật sự hoặc thiết kế snapshot. Không lấy việc code chạy một lần mà không ném lỗi làm bằng chứng đúng.

## 5. `NONNULL`: mọi phần tử chuyển cho consumer đều khác null

Đặc tính `NONNULL` cam kết rằng các phần tử được chuyển qua `tryAdvance` hoặc `forEachRemaining` sẽ **không có giá trị `null`**.

Nó không có nghĩa:

- `Spliterator` object không null (tất nhiên API đã cần một object hợp lệ).
- `List` dùng làm nguồn không thể chứa null chỉ vì generic là `List<String>`.
- Sau khi gọi một lambda `map` bất kỳ, kết quả Stream vẫn chắc chắn non-null.
- `Spliterators.spliterator(...)` sẽ tự phát hiện rồi ném lỗi nếu bạn nói dối về cờ.

Ví dụ **không hợp lệ về mặt hợp đồng**:

```java
String[] values = {"ok", null};

Spliterator<String> incorrect =
        Spliterators.spliterator(
                values, Spliterator.NONNULL);
```

Lời gọi có thể hoàn tất, nhưng spliterator đưa ra phần tử `null` trong lúc duyệt, mâu thuẫn với cờ vừa công bố. Kiểu tham số `String` không thay thế validation.

### Làm nguồn NONNULL một cách có chủ đích

Với danh sách đầu vào, `List.copyOf` từ chối null ngay lúc tạo snapshot:

```java
List<String> safe = List.copyOf(userInput);
```

`safe` không cho phép phần tử null; khi snapshot đó được đóng gói và chỉ được xuất qua một spliterator phù hợp, việc công bố `NONNULL` có cơ sở. Nếu null là dữ liệu đầu vào có ý nghĩa, bạn phải chọn chính sách khác:

1. **Từ chối**: ném lỗi validation kèm vị trí.
2. **Chuẩn hóa**: chuyển null thành giá trị thay thế, nhưng phải tránh nhập nhằng nghiệp vụ.
3. **Cho phép null**: không khai báo `NONNULL`, và yêu cầu các lambda tiếp theo xử lý null rõ ràng.
4. **Lọc null**: chỉ khi hợp đồng cho phép bỏ các phần tử ấy; không dùng lọc để che lỗi nhập liệu.

Ví dụ một nguồn có thể chứa null vẫn có thể sử dụng Stream, miễn các thao tác tiếp theo phù hợp:

```java
List<String> input = Arrays.asList("a", null, "b");

List<String> safe = input.stream()
        .filter(Objects::nonNull)
        .toList();
```

`Stream` không cấm mọi phần tử null theo nguyên tắc chung; tuy nhiên một số terminal operation và collector (như `findFirst`, `findAny`, một số collector kết quả) có quy tắc riêng với null. Việc lựa chọn chính sách phải rõ trước khi dùng.

### `map` có thể tạo null từ nguồn vốn NONNULL

```java
List<String> words = List.of("a", "b");

List<String> mapped = words.stream()
        .map(word -> word.equals("b") ? null : word)
        .toList();

// [a, null]
```

Kết quả vẫn có phần tử `null` dù nguồn ban đầu có hai chuỗi không null. Vì vậy không nên khẳng định một cờ `NONNULL` ban đầu bảo đảm toàn bộ pipeline vẫn không có null sau mọi phép biến đổi. Nếu cần duy trì bảo đảm, hãy có validation tại bước biến đổi, hoặc thiết kế mapper luôn trả giá trị khác null.

## 6. Ba cờ khác nhau ở điểm nào?

| Cờ | Cam kết chính | Không cam kết |
| --- | --- | --- |
| `IMMUTABLE` | Cấu trúc nguồn không thể bị sửa trong khi duyệt | Bất biến sâu của phần tử; snapshot tự động |
| `CONCURRENT` | Cấu trúc nguồn có thể thay đổi đồng thời mà không cần khóa bên ngoài | Kết quả là snapshot; chính xác mọi phần tử vừa thêm; lambda/collector thread-safe |
| `NONNULL` | Từng phần tử được spliterator phát ra khác null | Mapper tiếp theo không tạo null; null tự bị lọc |

`IMMUTABLE` và `CONCURRENT` nêu hai mô hình thay đổi cấu trúc **khác nhau về bản chất**. Đối với một nguồn thực tế, thường bạn chọn một trong hai: nguồn không đổi về cấu trúc khi duyệt, hoặc nguồn cho phép thay đổi đồng thời. **Không nên gắn cả hai chỉ để “có nhiều cờ”**, vì nó làm mơ hồ chính sách sửa đổi thực sự. `NONNULL` là đặc tính độc lập: một nguồn bất biến cũng có thể chứa null nếu API cho phép; một nguồn concurrent có thể cấm null hoặc không, tùy hợp đồng.

Các đặc tính khác như `ORDERED`, `SIZED`, `SUBSIZED`, `DISTINCT`, `SORTED` cần xem xét riêng. Không nên suy ra `IMMUTABLE` đồng nghĩa `SIZED`, hoặc `CONCURRENT` đồng nghĩa `UNORDERED`. Một Stream có thứ tự vẫn có thể được cung cấp từ nguồn concurrent hỗ trợ thứ tự duyệt theo hợp đồng riêng.

## 7. Ví dụ Java 17 hoàn chỉnh: snapshot tùy chỉnh và queue concurrent

Chương trình sau định nghĩa một nguồn `SnapshotWords` tự kiểm soát dữ liệu, tạo spliterator với `IMMUTABLE | NONNULL | ORDERED`, đối chiếu cả Stream tuần tự/song song, kiểm tra hành vi chia nhánh và so sánh với spliterator của `ConcurrentLinkedQueue`.

Lưu thành **`SpliteratorCharacteristicsDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class SpliteratorCharacteristicsDemo {
    static final class SnapshotWords {
        private final String[] values;

        SnapshotWords(List<String> input) {
            Objects.requireNonNull(input, "input");
            // Tạo bản sao độc lập; cấm các phần tử null.
            values = List.copyOf(input).toArray(String[]::new);
        }

        Spliterator<String> spliterator() {
            return Spliterators.spliterator(
                    values,
                    Spliterator.ORDERED
                            | Spliterator.IMMUTABLE
                            | Spliterator.NONNULL);
        }

        Stream<String> stream(boolean parallel) {
            return StreamSupport.stream(spliterator(), parallel);
        }
    }

    static void require(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError("Failed: " + label);
        }
    }

    static void expect(Object wanted, Object actual, String label) {
        if (!Objects.equals(wanted, actual)) {
            throw new AssertionError(
                    label + ": expected=" + wanted
                            + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        SnapshotWords snapshot =
                new SnapshotWords(List.of("red", "green", "blue", "gold"));

        Spliterator<String> sp = snapshot.spliterator();
        require(sp.hasCharacteristics(Spliterator.IMMUTABLE),
                "snapshot immutable");
        require(sp.hasCharacteristics(Spliterator.NONNULL),
                "snapshot nonnull");
        require(sp.hasCharacteristics(Spliterator.ORDERED),
                "snapshot ordered");
        require(sp.hasCharacteristics(Spliterator.SIZED),
                "array source sized");
        require(sp.hasCharacteristics(Spliterator.SUBSIZED),
                "array source subsized");
        require(!sp.hasCharacteristics(Spliterator.CONCURRENT),
                "snapshot not concurrent");
        expect(4L, sp.getExactSizeIfKnown(), "snapshot size");

        // Tạo hai spliterator mới để thử xử lý tuần tự và song song.
        List<String> sequential = snapshot.stream(false).toList();
        List<String> parallel = snapshot.stream(true).toList();

        expect(List.of("red", "green", "blue", "gold"),
                sequential, "sequential contents");
        expect(sequential, parallel, "parallel preserves order");

        // Array spliterator hỗ trợ chia các phần tử còn lại.
        Spliterator<String> root = snapshot.spliterator();
        Spliterator<String> part = root.trySplit();
        require(part != null, "array can split");
        require(part.hasCharacteristics(Spliterator.NONNULL),
                "split retains nonnull");
        require(part.hasCharacteristics(Spliterator.IMMUTABLE),
                "split retains immutable");

        long totalRemaining =
                part.getExactSizeIfKnown() + root.getExactSizeIfKnown();
        expect(4L, totalRemaining, "split partitions size");

        // ConcurrentLinkedQueue là ví dụ nguồn cho phép sửa đồng thời.
        ConcurrentLinkedQueue<String> queue =
                new ConcurrentLinkedQueue<>(
                        List.of("alpha", "beta", "gamma"));

        Spliterator<String> concurrent = queue.spliterator();
        require(concurrent.hasCharacteristics(Spliterator.CONCURRENT),
                "queue concurrent");
        require(concurrent.hasCharacteristics(Spliterator.NONNULL),
                "queue nonnull");
        require(concurrent.hasCharacteristics(Spliterator.ORDERED),
                "queue ordered");
        require(!concurrent.hasCharacteristics(Spliterator.IMMUTABLE),
                "queue is not immutable");
        require(!concurrent.hasCharacteristics(Spliterator.SIZED),
                "queue traversal not sized");

        // Không có writer khác: nội dung duyệt ở đây cố định.
        List<String> queueValues =
                StreamSupport.stream(queue.spliterator(), false).toList();
        expect(List.of("alpha", "beta", "gamma"),
                queueValues, "queue values without concurrent writes");

        // Queue cấm null; NONNULL có cơ sở từ hợp đồng của queue.
        boolean nullRejected = false;
        try {
            queue.add(null);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        require(nullRejected, "queue rejects null");

        // Snapshot được kiểm tra lúc tạo, không phải do cờ tự lọc.
        boolean snapshotNullRejected = false;
        try {
            new SnapshotWords(java.util.Arrays.asList("ok", null));
        } catch (NullPointerException expected) {
            snapshotNullRejected = true;
        }
        require(snapshotNullRejected, "snapshot rejects null");

        // Dù nguồn có NONNULL, map vẫn có thể sinh null.
        List<String> mapped = snapshot.stream(false)
                .map(s -> s.equals("blue") ? null : s)
                .toList();
        expect(java.util.Arrays.asList(
                "red", "green", null, "gold"),
                mapped, "mapper may produce null");

        System.out.println("snapshotImmutable="
                + sp.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("snapshotConcurrent="
                + sp.hasCharacteristics(Spliterator.CONCURRENT));
        System.out.println("snapshotNonnull="
                + sp.hasCharacteristics(Spliterator.NONNULL));
        System.out.println("snapshotSized="
                + sp.hasCharacteristics(Spliterator.SIZED));
        System.out.println("snapshotSize=" + sp.getExactSizeIfKnown());
        System.out.println("snapshotValues=" + sequential);
        System.out.println("parallelValues=" + parallel);
        System.out.println("splitTotalRemaining=" + totalRemaining);
        System.out.println("queueConcurrent="
                + concurrent.hasCharacteristics(Spliterator.CONCURRENT));
        System.out.println("queueImmutable="
                + concurrent.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("queueNonnull="
                + concurrent.hasCharacteristics(Spliterator.NONNULL));
        System.out.println("queueSized="
                + concurrent.hasCharacteristics(Spliterator.SIZED));
        System.out.println("queueValues=" + queueValues);
        System.out.println("nullRejected=" + nullRejected);
        System.out.println("snapshotNullRejected=" + snapshotNullRejected);
        System.out.println("mapped=" + mapped);
        System.out.println("tests=PASS");
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac SpliteratorCharacteristicsDemo.java
java SpliteratorCharacteristicsDemo
```

Stdout kỳ vọng:

```text
snapshotImmutable=true
snapshotConcurrent=false
snapshotNonnull=true
snapshotSized=true
snapshotSize=4
snapshotValues=[red, green, blue, gold]
parallelValues=[red, green, blue, gold]
splitTotalRemaining=4
queueConcurrent=true
queueImmutable=false
queueNonnull=true
queueSized=false
queueValues=[alpha, beta, gamma]
nullRejected=true
snapshotNullRejected=true
mapped=[red, green, null, gold]
tests=PASS
```

### Giải thích đầu ra

- `snapshotImmutable=true`: cờ được công bố hợp lý vì snapshot là mảng private, không có đường sửa dữ liệu sau khi tạo.
- `snapshotNonnull=true`: constructor dùng `List.copyOf` để từ chối null trước khi tạo mảng.
- `snapshotSized=true`, `snapshotSize=4`: `Spliterators.spliterator(array, flags)` bổ sung đặc tính `SIZED` và `SUBSIZED`, với kích thước chính xác của mảng.
- `parallelValues` vẫn theo encounter order vì spliterator công bố `ORDERED` và phép thu thập `toList()` bảo toàn thứ tự của nguồn có thứ tự.
- `splitTotalRemaining=4`: `trySplit()` chia vùng phần tử còn lại thành hai phần không chồng lên nhau. Không phụ thuộc vào kích thước chính xác của từng phần, chỉ kiểm tra tổng không đổi.
- `queueConcurrent=true`: đặc tính này thuộc spliterator từ `ConcurrentLinkedQueue`, nguồn được thiết kế cho sửa đổi đồng thời.
- `queueSized=false`: queue có thể thay đổi trong khi duyệt, không hứa rằng ước lượng là kích thước chính xác theo `SIZED`.
- `queueValues` cố định vì chương trình demo **không** tạo thêm thread thay đổi queue đồng thời. Nếu có mutation concurrent, không được áp dụng kỳ vọng snapshot ở dòng này.
- `mapped` chứa `null` do mapper tạo ra, chứng minh `NONNULL` là cam kết của spliterator nguồn, không phải validation cho toàn pipeline.
- Các kiểm tra ném `AssertionError` ngay nếu điều kiện sai; không phải bật `java -ea`.

## 8. Vì sao snapshot và nguồn concurrent có hợp đồng khác nhau?

Giả sử ứng dụng xuất báo cáo danh sách ID lúc bắt đầu công việc. Nếu danh sách ID không được phép thay đổi trong suốt lượt, snapshot là một thiết kế phù hợp:

```text
List đầu vào có thể được sửa sau đó
         │
         ▼
Copy vào snapshot riêng
         │
         ▼
Spliterator IMMUTABLE | NONNULL | ORDERED
         │
         ▼
Stream xử lý dữ liệu của snapshot
```

Mục đích snapshot là tính **ổn định**: cùng snapshot sẽ có cùng tập phần tử, trừ khi bản thân mapper/nguồn ngoài có trạng thái khác.

Với một queue đang nhận sự kiện:

```text
Producer thread ──add/remove──► ConcurrentLinkedQueue
                                   │
                                   ▼
                           Spliterator CONCURRENT
                                   │
                                   ▼
                            Consumer traversal
```

Mục đích là **cho phép producer và consumer cùng hoạt động**. Kết quả duyệt có thể là một lát cắt động, không phải snapshot giao dịch. Một spliterator concurrent thông thường không phù hợp để tạo bản báo cáo “chính xác mọi phần tử tại đúng thời điểm T” nếu không có thêm cơ chế chụp dữ liệu.

Bạn không nên đánh dấu queue là `IMMUTABLE` chỉ vì trong một lần thử không có producer nào ghi. Cờ mô tả **hợp đồng tổng quát của nguồn**, không phải trạng thái ngẫu nhiên ở một thời điểm.

## 9. `IMMUTABLE` và `CONCURRENT` liên quan thế nào tới việc sửa nguồn?

Khi spliterator không có một trong các cơ chế bảo đảm thích hợp, sửa nguồn trong khi duyệt có thể gây kết quả không xác định theo hợp đồng của nguồn. Nhiều collection không concurrent sử dụng cơ chế **fail-fast** để phát hiện một số thay đổi cấu trúc, nhưng fail-fast thường là best-effort, không phải cách ứng dụng được phép dùng để đồng bộ hoặc kiểm tra an toàn.

Ví dụ nên tránh:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

numbers.stream().forEach(x -> {
    if (x == 2) {
        numbers.add(10); // Thay đổi nguồn khi đang duyệt.
    }
});
```

Đây là phản ví dụ, không phải code cần chạy trong bài demo. Nó có thể ném `ConcurrentModificationException` nhưng ứng dụng không được dựa vào việc exception luôn xảy ra đúng lúc. Cách đúng là đưa kết quả vào collection **khác** hoặc dùng phép biến đổi Stream thuần:

```java
List<Integer> extended = Stream.concat(
        numbers.stream(),
        Stream.of(10))
        .toList();
```

Ở đây `numbers` là danh sách không bị sửa trong lúc Stream đang duyệt. Nếu nhiều thread cần thay đổi nguồn, hãy thiết kế cấu trúc concurrent phù hợp hoặc tạo snapshot theo yêu cầu.

### Cờ `IMMUTABLE` có thay thế khóa không?

Không phải cơ chế khóa. Nó là lời cam kết của nguồn. Nếu thực sự nguồn là bất biến, không cần khóa để bảo vệ các thay đổi cấu trúc **vì các thay đổi đó không được phép xảy ra**. Nếu nguồn vẫn mutable nhưng chỉ “hy vọng” không ai sửa, cờ `IMMUTABLE` không bảo vệ chống race condition. Sự bảo đảm phải đến từ thiết kế sở hữu dữ liệu, sao chép hoặc ràng buộc truy cập, không phải từ việc set bit.

### Cờ `CONCURRENT` có thay thế đồng bộ nghiệp vụ không?

Cũng không. Nó chỉ nói traversal có thể đồng tồn tại với sửa cấu trúc theo chính sách nguồn. Những thao tác nghiệp vụ gồm nhiều bước như “kiểm tra tồn tại rồi xóa” có thể cần tính nguyên tử ở cấp cao hơn. `CONCURRENT` không tự cung cấp transaction, snapshot hoặc đồng bộ giữa các tác vụ gửi mạng, ghi database hay cập nhật nhiều cấu trúc dữ liệu.

## 10. Thiết kế `Spliterator` tùy chỉnh và duy trì đặc tính sau khi split

Khi tự cài đặt interface `Spliterator<T>` thay vì dùng `Spliterators.spliterator(...)`, bạn chịu trách nhiệm triển khai:

```java
boolean tryAdvance(Consumer<? super T> action);

Spliterator<T> trySplit();

long estimateSize();

int characteristics();
```

Một implementation đúng phải giữ lời hứa đã công bố ở **cả spliterator gốc lẫn những phần mà `trySplit` trả ra**. Nếu root hứa `NONNULL`, không được để nhánh con phát `null`. Nếu root hứa `IMMUTABLE`, không được để nhánh con phụ thuộc vào một nguồn có thể sửa cấu trúc trái với hợp đồng. Nếu root công bố `SIZED`/`SUBSIZED`, ước lượng và kích thước phần chia phải đáp ứng đúng quy tắc của các đặc tính ấy.

Ví dụ phác thảo tạo nhánh từ một snapshot mảng:

```java
final class RangeWords implements Spliterator<String> {
    private final String[] values;
    private int index;
    private final int fence;

    RangeWords(String[] values, int start, int end) {
        this.values = values;
        this.index = start;
        this.fence = end;
    }

    @Override
    public boolean tryAdvance(
            java.util.function.Consumer<? super String> action) {
        Objects.requireNonNull(action);
        if (index >= fence) {
            return false;
        }
        action.accept(values[index++]);
        return true;
    }

    @Override
    public Spliterator<String> trySplit() {
        int lo = index;
        int mid = (lo + fence) >>> 1;
        if (lo >= mid) {
            return null;
        }
        index = mid;
        return new RangeWords(values, lo, mid);
    }

    @Override
    public long estimateSize() {
        return fence - index;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL;
    }
}
```

Đây là **đoạn minh họa bổ sung**, chưa phải lớp tự hoạt động độc lập: `RangeWords` cần `Spliterator`, `Objects`, `Consumer` và một mảng nguồn **được bảo vệ khỏi sửa đổi** như ở `SnapshotWords`. Chữ ký constructor không ngăn caller truyền một mảng vẫn có thể bị sửa hoặc chứa null; nếu muốn công bố `IMMUTABLE`/`NONNULL` một cách an toàn, phải tích hợp lớp này với một owner đã kiểm soát snapshot hoặc tự sao chép/validate đầu vào.

Cơ chế `trySplit`: lấy phần `[lo,mid)` cho nhánh mới, nhánh gốc tiếp tục giữ `[mid,fence)`. Chúng không chồng lấp, kích thước ước lượng cộng lại bằng kích thước trước khi chia. Cả hai dùng cùng mảng chỉ để **đọc**. Nếu mảng thật sự không bị sửa và các phần tử non-null, hai nhánh có thể công bố cùng cờ.

Đừng ép `trySplit` phải luôn trả nhánh con. Với nguồn nhỏ, nguồn khó phân chia hoặc chính sách nội bộ riêng, trả `null` là hợp lệ. Tuy nhiên, việc `trySplit` chỉ trả `null` sẽ giới hạn khả năng khai thác song song.

### Tránh overflow khi tính midpoint

Trong đoạn minh họa, `mid = (lo + fence) >>> 1` là một mẫu tính midpoint thường dùng với chỉ số không âm, tương tự cách tính midpoint cho mảng. Có thể dùng `lo + ((fence - lo) >>> 1)` để diễn đạt rõ phần chênh lệch không âm và tránh cộng trực tiếp hai giá trị index lớn. Trong code production, hãy validate `0 <= start <= end <= values.length` và không cho code bên ngoài sửa mảng.

## 11. Thứ tự và kích thước là đặc tính độc lập

Một spliterator có thể công bố nhiều bit:

```java
Spliterator.ORDERED
Spliterator.SIZED
Spliterator.SUBSIZED
Spliterator.IMMUTABLE
Spliterator.NONNULL
```

Với snapshot array, các cờ này hợp lý nếu dữ liệu được kiểm soát:

- `ORDERED`: có encounter order cố định theo vị trí mảng.
- `SIZED`: số phần tử còn lại có thể xác định chính xác.
- `SUBSIZED`: khi split, từng nhánh tiếp tục đáp ứng yêu cầu kích thước chính xác.
- `IMMUTABLE`: cấu trúc snapshot không bị sửa.
- `NONNULL`: không có phần tử `null`.

`ConcurrentLinkedQueue` có thể công bố `ORDERED`, `CONCURRENT`, `NONNULL` nhưng **không** `SIZED`, vì khi có sửa đồng thời, không có hợp đồng đếm chính xác thông qua spliterator tại thời điểm duyệt.

Không suy ra `NONNULL => SIZED`, `IMMUTABLE => SORTED` hoặc `CONCURRENT => UNORDERED`: đây là các tính chất khác nhau. Một snapshot gồm `["z", "a"]` là immutable/non-null nhưng **không sorted** theo thứ tự từ điển. Một queue concurrent vẫn có thể nêu đặc tính thứ tự của chính nó.

### `getExactSizeIfKnown()` khác `estimateSize()`

Với nguồn `SIZED`, `getExactSizeIfKnown()` có thể trả số lượng chính xác phần tử còn lại. Với nguồn không `SIZED`, nó trả `-1`, kể cả khi `estimateSize()` vẫn có một con số ước lượng hoặc giới hạn. Không dùng ước lượng như hợp đồng kiểm tra rằng mọi phần tử đã được xử lý đúng một lần khi có mutation concurrent.

## 12. Tác động tới Stream API và tối ưu hóa

Các cờ của `Spliterator` cho phép thư viện Stream **hiểu thêm về nguồn**. Chúng không phải các directive “bắt buộc chạy nhanh”. JDK có thể dùng một số đặc tính để tối ưu phân chia, giữ thứ tự hoặc lập kế hoạch pipeline, tùy thao tác và triển khai.

Những điều cần tránh:

1. **Không phụ thuộc side effect trong intermediate operation.** Một terminal như `count()` có thể được tối ưu nếu nguồn/pipeline cung cấp đủ thông tin; callback `map`/`peek` không được bảo đảm chạy chỉ để thực hiện side effect.
2. **Không sửa nguồn có cờ IMMUTABLE.** Nếu lời hứa này sai, kết quả có thể sai mà không có cơ chế cảnh báo bắt buộc.
3. **Không coi CONCURRENT là bằng chứng kết quả ổn định.** Dữ liệu có thể xuất hiện/biến mất trong khi duyệt; tùy chính sách nguồn.
4. **Không coi NONNULL là filter.** Phát ra null trong một spliterator công bố NONNULL là lỗi hợp đồng, không phải tình huống Stream tự phải sửa hộ.
5. **Không coi parallel là mục tiêu bắt buộc.** Với dữ liệu nhỏ hoặc nguồn khó split, overhead có thể lớn; cấu trúc nguồn, chi phí mapper và downstream quyết định hiệu năng thực tế.

Một pipeline có `map` trả null có thể cho Stream kết quả chứa null ngay cả khi spliterator nguồn là `NONNULL`. Một pipeline có `filter` có thể thay đổi số lượng phần tử nên đặc tính sized của nguồn không đồng nghĩa mọi pipeline đều biết trước kích thước kết quả. Bạn không nên tự suy đoán các cờ nội bộ của spliterator kết quả sau pipeline mà chưa đọc hợp đồng thao tác tương ứng.

## 13. Những lỗi hay gặp khi công bố characteristic

**Lỗi 1 — đánh dấu `IMMUTABLE` cho mảng vẫn đang bị sửa.** Chỉ khai báo khi có ownership/snapshot đảm bảo cấu trúc không đổi. Việc biến tham chiếu là `final` không đủ.

**Lỗi 2 — nhầm unmodifiable view với snapshot.** `Collections.unmodifiableList` ngăn sửa qua view, không ngăn sửa qua backing list do đối tượng khác nắm giữ.

**Lỗi 3 — đánh dấu `CONCURRENT` cho `ArrayList` hoặc `HashMap` thường.** Set bit không khiến container trở thành concurrent-safe. Chọn cấu trúc phù hợp và chính sách traversal.

**Lỗi 4 — cho rằng `CONCURRENT` có nghĩa mọi consumer thread-safe.** Source có thể concurrent, nhưng side effect trong lambda cập nhật một `ArrayList` bên ngoài vẫn có thể gây data race.

**Lỗi 5 — nhầm `CONCURRENT` với snapshot đúng tại một thời điểm.** Weakly consistent traversal không có nghĩa snapshot giao dịch.

**Lỗi 6 — công bố `NONNULL` khi dữ liệu có thể chứa null.** Generic `String` không cấm null; cần validate hoặc thiết kế loại dữ liệu bảo đảm.

**Lỗi 7 — tin cờ sẽ kiểm chứng dữ liệu giúp mình.** `Spliterators.spliterator(array, flags)` dựa trên characteristic do người gọi cung cấp. Cần tự chứng minh bằng bất biến của nguồn và test.

**Lỗi 8 — nghĩ `IMMUTABLE` đồng nghĩa mọi phần tử immutable.** Danh sách không sửa cấu trúc vẫn có thể chứa object mutable.

**Lỗi 9 — nghĩ `NONNULL` được bảo toàn sau mọi `map`.** Mapper có thể chủ động trả null; downstream phải có chính sách.

**Lỗi 10 — dùng `getExactSizeIfKnown()` như thể mọi nguồn luôn SIZED.** Với nguồn động, có thể trả `-1`; hãy đọc `SIZED` trước.

**Lỗi 11 — split làm mất hoặc lặp phần tử.** `trySplit()` tùy chỉnh phải chia phần không chồng, giữ các cam kết đã công bố và kích thước đúng nếu có `SIZED`/`SUBSIZED`.

**Lỗi 12 — gắn cả `IMMUTABLE` và `CONCURRENT` theo thói quen.** Hai cờ nêu chính sách sửa cấu trúc khác nhau; không dùng như nhóm tùy chọn bật hết.

**Lỗi 13 — dựa vào fail-fast để phát hiện mọi race.** `ConcurrentModificationException` thường chỉ là cố gắng phát hiện lỗi sửa nguồn, không phải cơ chế synchronization.

**Lỗi 14 — không kiểm tra hành vi khi chạy song song.** Một spliterator với `trySplit` sai có thể cho kết quả tuần tự đúng nhưng làm mất/trùng phần tử khi parallel; cần test chia nguồn, so phần tử và tổng kích thước.

## 14. Quy trình thiết kế nguồn tùy chỉnh an toàn

Trước khi triển khai `Spliterator<T>`, hãy trả lời các câu hỏi theo thứ tự:

1. **Nguồn dữ liệu có thay đổi cấu trúc trong lúc duyệt không?** Nếu không thể thay đổi, `IMMUTABLE` có thể phù hợp. Nếu có thể sửa đồng thời mà không cần khóa bên ngoài, cần thiết kế concurrent thực sự và có thể cân nhắc `CONCURRENT`.
2. **Dữ liệu có thể chứa null không?** Nếu có, không công bố `NONNULL` trừ khi chính spliterator lọc/từ chối null theo hợp đồng rõ ràng.
3. **Nguồn có encounter order không?** Nếu có, xem xét `ORDERED`. Nếu không, đừng hứa thứ tự mà dữ liệu không có.
4. **Số phần tử còn lại có biết chính xác không?** Chỉ khi đúng hợp đồng mới công bố `SIZED` và có thể `SUBSIZED`.
5. **Có thể chia nguồn thành các phạm vi độc lập không?** Thiết kế `trySplit` để không mất/trùng phần tử, tránh cùng sửa trạng thái cursor.
6. **Ai sở hữu dữ liệu?** Có tham chiếu mutable bị lộ ra ngoài không? Nếu có, cần defensive copy hoặc cơ chế đồng bộ/ownership rõ.
7. **Hợp đồng khi có thay đổi concurrent là gì?** Weak consistency, snapshot, khả năng nhìn thấy phần tử mới/xóa, quyền lỗi phải được ghi rõ.
8. **Kiểm thử đã kiểm tra hành vi chưa?** Đừng chỉ assert bit cờ; so output tuần tự, parallel, kích thước, split, null và tác động của thay đổi dữ liệu.
9. **Có thật sự cần viết spliterator thủ công?** Với mảng/snapshot hoặc collection chuẩn, ưu tiên spliterator JDK có sẵn thay vì tăng bề mặt lỗi.
10. **Có tác dụng phụ trong mapper/consumer không?** Thiết kế pipeline theo stateless/non-interfering hoặc kiểm soát I/O, thread safety và lỗi theo yêu cầu.

## 15. Bài tập tự luyện

1. Sửa `SnapshotWords` để nhận một `List<String>` mutable, sau đó sửa List gốc sau khi tạo snapshot. Chứng minh Stream snapshot vẫn trả dữ liệu lúc khởi tạo.
2. Thử đưa `null` vào danh sách truyền cho `SnapshotWords`. Giải thích tại sao exception đến từ validation trước khi spliterator hoạt động, không phải vì cờ `NONNULL` tự lọc.
3. Viết một phiên bản `SnapshotWords` dùng `List<Box>` trong đó `Box` có field mutable. Chứng minh việc sửa field không tương đương thêm/xóa phần tử trong nguồn, và nêu rủi ro khi xử lý song song với các Box đang được sửa.
4. Lấy `ConcurrentLinkedQueue.spliterator()` và kiểm tra các cờ `CONCURRENT`, `NONNULL`, `ORDERED`, `SIZED`. Giải thích vì sao `SIZED` không được bảo đảm cho nguồn động này.
5. Với snapshot có 100 phần tử, gọi `trySplit()` liên tiếp và duyệt mỗi nhánh. Kiểm tra mọi phần tử xuất hiện đúng một lần, không mất hoặc lặp.
6. Giả sử một `Spliterator` tự viết công bố `NONNULL`, nhưng `tryAdvance` đôi lúc nhận `null`. Nêu hợp đồng bị phá vỡ và hai cách sửa: validate từ nguồn hoặc bỏ cờ (khi cho phép null).
7. Cho mapper `s -> s.equals("x") ? null : s`, áp dụng lên Stream nguồn NONNULL. Xác định vì sao kết quả có thể có null.
8. Thiết kế một nguồn log luôn nhận thêm dòng đồng thời. Quyết định xem `CONCURRENT` với weakly consistent traversal có phù hợp báo cáo cuối ngày hay cần snapshot nhất quán.
9. Tạo một spliterator `SIZED`/`SUBSIZED` trên phạm vi index, kiểm tra kích thước hai nhánh sau mỗi lần split và sau khi tiêu thụ một phần.
10. Viết một đoạn kiểm thử chuyển đổi `StreamSupport.stream(sp, false)` và `StreamSupport.stream(newSp, true)` từ hai spliterator **mới** cùng snapshot rồi so kết quả. Không dùng lại spliterator đã tiêu thụ.
11. Mô tả vì sao không thể sửa một lỗi concurrency bằng cách chỉ OR thêm `Spliterator.CONCURRENT` vào bitmask.
12. Nêu một ví dụ dữ liệu bất biến nhưng có null theo hợp đồng, và một ví dụ dữ liệu concurrent nhưng không có null; giải thích vì sao `NONNULL` độc lập với hai cờ còn lại.

## 16. Tổng kết

`IMMUTABLE`, `CONCURRENT` và `NONNULL` là ba đặc tính **của nguồn do spliterator mô tả**, không phải phép biến đổi hay cơ chế đồng bộ tự động:

- `IMMUTABLE`: nguồn không bị thay đổi cấu trúc trong khi duyệt; không có nghĩa phần tử bất biến sâu, cũng không tự tạo snapshot.
- `CONCURRENT`: nguồn cho phép sửa cấu trúc đồng thời mà không cần khóa ngoài; không có nghĩa kết quả là snapshot, lambda thread-safe hoặc cùng spliterator có thể bị gọi tùy ý từ nhiều thread.
- `NONNULL`: mọi phần tử nguồn được phát ra đều khác null; không tự cấm mapper tạo null hoặc lọc dữ liệu đầu vào.

Khi xây nguồn tùy chỉnh, việc khai báo cờ chính xác phải xuất phát từ **ownership, khả năng thay đổi, hợp đồng đồng thời và tính hợp lệ dữ liệu**. Nếu đã kiểm soát một snapshot private non-null, có thể công bố `IMMUTABLE | NONNULL`; nếu nguồn thực sự concurrent như `ConcurrentLinkedQueue`, có thể công bố `CONCURRENT | NONNULL` theo hợp đồng của nguồn đó. Hãy kiểm thử cả nguồn rỗng, parallel, split, null và thay đổi concurrent có chủ đích, đồng thời không đưa output phụ thuộc lịch trình thread thành kỳ vọng cố định.

Một spliterator khai báo đúng giúp Stream vận hành trên những giả định chính xác. Một bit cờ khai báo sai có thể tạo ra kết quả khó giải thích và khó phát hiện hơn cả một ngoại lệ rõ ràng.
