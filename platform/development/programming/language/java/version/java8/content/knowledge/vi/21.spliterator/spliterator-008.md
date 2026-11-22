# Spliterators, AbstractSpliterator và nguồn Stream tự tạo (Java 8)

Java Stream nhận dữ liệu qua một đối tượng **`Spliterator<T>`**: nó biết cách lấy phần tử tiếp theo, có thể chia công việc thành các phần độc lập và mô tả một số đặc tính của nguồn. Khi dữ liệu không đến từ `Collection.stream()` thông thường — ví dụ một `Iterator` của thư viện khác, mảng, bộ đọc từng dòng, nguồn dữ liệu được tạo theo quy tắc riêng — Java cung cấp lớp tiện ích **`java.util.Spliterators`**, lớp nền **`Spliterators.AbstractSpliterator<T>`**, và các hàm **`StreamSupport.stream(...)` / `StreamSupport.intStream(...)`** để xây dựng Stream.

Nội dung dưới đây sử dụng các API Java 8 **vẫn còn áp dụng trong JDK hiện hành**. Mục tiêu là biết chọn factory có sẵn trước khi viết Spliterator tùy biến; nếu cần tự viết, phải bảo đảm **không mất/trùng phần tử khi chia**, khai báo đặc tính đúng và quản lý tài nguyên của nguồn.

## 1. Bốn đối tượng dễ nhầm

| Tên | Vai trò | Ví dụ |
| --- | --- | --- |
| `Spliterator<T>` | Giao diện duyệt và tùy chọn tách nguồn thành nhiều phần | `tryAdvance`, `trySplit`, `estimateSize`, `characteristics` |
| `Spliterators` | Lớp tiện ích với factory và adapter từ iterator/mảng | `spliteratorUnknownSize(iterator, flags)`, `spliterator(array, flags)` |
| `Spliterators.AbstractSpliterator<T>` | Lớp nền giúp tự xây một Spliterator, có sẵn cách chia mặc định theo lô | Kế thừa rồi triển khai `tryAdvance` |
| `StreamSupport` | Tạo Stream từ Spliterator hoặc supplier của Spliterator | `stream(spliterator, false)`, `intStream(ofInt, true)` |

Ví dụ luồng dữ liệu:

```text
Nguồn ngoài Java Collections
       │
       ├─ Iterator / mảng / dữ liệu xác định trước
       │       └─ Spliterators.spliterator...
       │
       ├─ Đầu đọc lần lượt từng dòng
       │       └─ extends AbstractSpliterator<T>
       │
       └─ Nguồn có khả năng chia theo chỉ mục
               └─ implements Spliterator<T> / Spliterator.OfInt
                       │
                       ▼
        StreamSupport.stream(spliterator, parallel)
                       │
              filter / map / ...
                       │
             collect / sum / count
```

**Phân biệt quan trọng:** `Iterator` chủ yếu cho phép duyệt lần lượt, còn `Spliterator` có thể cho biết đặc tính nguồn và **tách phần chưa duyệt** thành nhiều Spliterator. Tuy nhiên, có `trySplit()` không đồng nghĩa việc chạy song song sẽ luôn nhanh hơn.

## 2. Hợp đồng tối thiểu của Spliterator

Một `Spliterator<T>` có các phương thức lõi:

```java
// Chữ ký tóm lược để học API, không phải chương trình Java độc lập.
boolean tryAdvance(Consumer<? super T> action);
Spliterator<T> trySplit();
long estimateSize();
int characteristics();
```

Ý nghĩa chính xác:

1. **`tryAdvance(action)`**: nếu còn phần tử, gọi `action.accept(element)` **đúng một lần** và trả `true`; nếu đã hết, trả `false` và **không gọi** action. Khi action ném exception, exception được truyền ra cho bên gọi.
2. **`trySplit()`**: có thể trả một Spliterator mới quản lý **một phần chưa duyệt** của nguồn; đối tượng hiện tại giữ phần còn lại. Trả `null` nếu không thể hoặc không muốn chia nữa. Hai phần phải **không chồng lấp**, không làm mất phần tử.
3. **`estimateSize()`**: ước lượng số phần tử còn lại, hoặc `Long.MAX_VALUE` khi không biết. Không được tùy tiện công bố kích thước chính xác nếu nguồn còn có thể thay đổi hoặc bộ đếm không đúng.
4. **`characteristics()`**: trả bitmask các cam kết như `ORDERED`, `SIZED`, `SUBSIZED`, `DISTINCT`. Các bit này không chỉ là ghi chú: Stream framework có thể **tối ưu dựa trên chúng**, vì vậy khai báo sai có thể làm kết quả sai.

Các phương thức khác như `forEachRemaining`, `getExactSizeIfKnown`, `hasCharacteristics` và `getComparator` giúp duyệt hoặc tra cứu đặc tính. `getExactSizeIfKnown()` trả kích thước chính xác khi có `SIZED`, nếu không trả `-1L`.

Một Spliterator thường được tạo để **duyệt một lần**. Tương tự, một `Stream` đã qua terminal operation không được tái sử dụng; muốn chạy hai phép tính, tạo Spliterator/Stream mới từ nguồn khi nguồn cho phép.

## 3. Dùng Spliterators factory khi đã có nguồn chuẩn

Đừng viết class tùy biến nếu có thể sử dụng trực tiếp một factory:

| Factory Java 8 | Đầu vào | Khi nên dùng |
| --- | --- | --- |
| `Spliterators.spliterator(array, characteristics)` | Mảng tham chiếu hoặc mảng nguyên thủy có overload tương ứng | Nguồn có kích thước chính xác, chia theo vùng chỉ mục |
| `Spliterators.spliterator(iterator, size, characteristics)` | Iterator và số phần tử **biết chính xác** | Có iterator + số phần tử còn lại đáng tin cậy |
| `Spliterators.spliteratorUnknownSize(iterator, characteristics)` | Iterator **không rõ kích thước** | Cursor/iterator sinh dữ liệu dần |
| `Spliterators.spliterator(collection, characteristics)` | Collection | Khi cần wrapper phù hợp; thường ưu tiên `collection.spliterator()` nếu đã có |
| `Spliterators.emptySpliterator()` | Không có dữ liệu | Muốn Spliterator rỗng |
| `Spliterators.iterator(spliterator)` | Spliterator | Cần adapter ngược trở về Iterator |

Các overload cho kiểu nguyên thủy như `int[]`, `long[]`, `double[]` cung cấp lần lượt `Spliterator.OfInt`, `OfLong`, `OfDouble`. Khi kết hợp với `StreamSupport.intStream`/`longStream`/`doubleStream`, chúng tránh boxing từng giá trị như `Stream<Integer>`.

**Nếu đã có `List<T>`**, cách thông thường là `list.stream()` hoặc `list.parallelStream()`. Lớp `Spliterators` hữu ích nhất khi bạn phải tích hợp nguồn ở mức thấp, không phải thay mọi cách tạo Stream quen thuộc.

### Biết kích thước và không biết kích thước

Khi kích thước chính xác, hãy truyền số lượng **phần tử thực sự còn trong iterator**, không phải một con số dự đoán. Factory có thể gắn `SIZED`/`SUBSIZED` theo hợp đồng nên kích thước khai báo sai có thể khiến tối ưu hóa dựa trên số đếm sai.

Nếu không biết chính xác, dùng `spliteratorUnknownSize`. Nó xóa `SIZED`/`SUBSIZED` khỏi đặc tính, vì framework không thể dựa vào kích thước chính xác. **Không đặt `Long.MAX_VALUE` vào overload nhận `size` chỉ để giả làm unknown size**; hãy chọn đúng factory dành cho unknown.

## 4. Ví dụ 1 — Từ Iterator, mảng và primitive array thành Stream

Tệp **`SpliteratorsFactoriesDemo.java`** (Java 8+):

```java
import java.util.*;
import java.util.stream.*;

public class SpliteratorsFactoriesDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList("alpha", "beta", "gamma");

        // Iterator không biết kích thước tại thời điểm thiết kế adapter.
        Spliterator<String> unknown =
            Spliterators.spliteratorUnknownSize(
                input.iterator(),
                Spliterator.ORDERED | Spliterator.NONNULL);

        System.out.println("unknownExactSize="
            + unknown.getExactSizeIfKnown());
        System.out.println("iteratorValues=" +
            StreamSupport.stream(unknown, false)
                .collect(Collectors.toList()));

        // Ở đây số phần tử còn lại biết chính xác.
        List<Integer> knownInput = Arrays.asList(10, 20, 30);
        Spliterator<Integer> known = Spliterators.spliterator(
            knownInput.iterator(), knownInput.size(),
            Spliterator.ORDERED | Spliterator.NONNULL);

        System.out.println("knownExactSize="
            + known.getExactSizeIfKnown());
        System.out.println("knownValues=" +
            StreamSupport.stream(known, false)
                .collect(Collectors.toList()));

        // Primitive Spliterator.OfInt: không cần boxed Integer.
        int[] numbers = {2, 4, 6};
        Spliterator.OfInt primitive =
            Spliterators.spliterator(numbers, Spliterator.ORDERED);

        System.out.println("primitiveExactSize="
            + primitive.getExactSizeIfKnown());
        System.out.println("primitiveSum=" +
            StreamSupport.intStream(primitive, true).sum());

        Spliterator<String> array = Spliterators.spliterator(
            new String[]{"red", "blue"},
            Spliterator.ORDERED | Spliterator.NONNULL);

        System.out.println("arrayValues=" +
            StreamSupport.stream(array, false)
                .collect(Collectors.toList()));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SpliteratorsFactoriesDemo.java
java SpliteratorsFactoriesDemo
```

Kết quả đã xác minh:

```text
unknownExactSize=-1
iteratorValues=[alpha, beta, gamma]
knownExactSize=3
knownValues=[10, 20, 30]
primitiveExactSize=3
primitiveSum=12
arrayValues=[red, blue]
```

Điểm cần hiểu:

- `unknownExactSize=-1` **không có nghĩa nguồn rỗng**. Nó chỉ có nghĩa không công bố kích thước chính xác; ba phần tử vẫn được duyệt.
- `knownExactSize=3` dùng một kích thước được cung cấp đúng. Nếu iterator đã bị tiêu thụ một phần, bạn phải cung cấp **số phần tử còn lại**, không phải kích thước ban đầu.
- Với mảng nguyên thủy, `Spliterators.spliterator(int[], ...)` tạo `OfInt`; `StreamSupport.intStream(..., true)` tạo primitive Stream có thể chạy song song.
- Cờ `NONNULL` đúng với dữ liệu chuỗi ở ví dụ. **Không tự gắn `NONNULL` cho mảng/iterator có thể chứa null**.
- Lời gọi `StreamSupport.stream(spliterator, false)` tạo Stream tuần tự; đối số `true` yêu cầu chế độ parallel, không bảo đảm tăng tốc.

## 5. Đặc tính Spliterator: chỉ khai báo điều có thể bảo đảm

Bitmask `characteristics` có thể quyết định hành vi tối ưu hóa và chi phí phân chia:

| Đặc tính | Cam kết cần giữ | Ghi nhớ |
| --- | --- | --- |
| `ORDERED` | Các phần tử có **encounter order** được xác định | Với nguồn có thứ tự, `trySplit` cần trả tiền tố theo yêu cầu về order |
| `SIZED` | `estimateSize()` cung cấp số lượng chính xác phần tử còn lại trước khi chia theo hợp đồng | Không dùng khi chỉ biết con số ước lượng |
| `SUBSIZED` | Mọi Spliterator thu được bằng cách chia đều cũng thỏa `SIZED`/`SUBSIZED` | Hữu ích cho phân chia theo chỉ mục, nhưng cam kết mạnh |
| `DISTINCT` | Các phần tử không trùng theo `equals` | Không gắn nếu có thể phát sinh hai phần tử bằng nhau |
| `SORTED` | Phần tử có thứ tự sắp xếp theo tiêu chí xác định | Nếu khai báo, `getComparator()` phải hợp lệ: `null` cho thứ tự tự nhiên hoặc Comparator phù hợp |
| `NONNULL` | Không có phần tử null | Nếu nguồn có thể null, bỏ cờ này |
| `IMMUTABLE` | Nguồn không thể thay đổi cấu trúc trong lúc duyệt | Không gắn cho collection có thể sửa từ bên ngoài |
| `CONCURRENT` | Nguồn cho phép biến đổi đồng thời theo hợp đồng riêng | Không gắn chỉ vì Stream sẽ chạy song song |

Đặc biệt:

- `ORDERED` khác `SORTED`. Một danh sách tên nhập theo thời gian có thứ tự gặp, nhưng không nhất thiết đã sắp theo chữ cái.
- `SIZED` chưa đủ để khẳng định mọi phần sau khi chia có kích thước chính xác; chỉ khai báo `SUBSIZED` nếu **tất cả các nhánh chia** cũng tuân thủ quy tắc đó.
- `DISTINCT` và `SORTED` là mô tả có ý nghĩa về **dữ liệu thực tế**, không phải yêu cầu framework tự loại trùng hoặc tự sắp xếp.
- Nếu đã có characteristic `SORTED`, việc không triển khai `getComparator()` phù hợp có thể làm hỏng các lời gọi kiểm tra thứ tự.
- Với `Spliterators.AbstractSpliterator`, nếu truyền cờ `SIZED`, lớp nền có thể tự bổ sung `SUBSIZED`; vì thế **đừng khai báo SIZED nếu không đáp ứng được hợp đồng chia**.
- Những đặc tính khai báo sai có thể dẫn tới lỗi tinh vi hơn một exception: framework có thể bỏ qua việc duyệt một số phần tử để tính `count()` khi tin rằng kích thước đã biết, hoặc tối ưu các thao tác trung gian dựa trên cờ.

Không phải càng nhiều cờ thì càng tốt. **Ít cờ nhưng đúng** vẫn an toàn hơn nhiều cờ không chính xác. Hãy xem mỗi characteristic là một lời hứa cần được kiểm thử.

## 6. Khi nào kế thừa AbstractSpliterator?

`Spliterators.AbstractSpliterator<T>` là lớp nền dành cho nguồn **chỉ thuận tiện duyệt một phần tử tại một thời điểm**:

```java
// Khung mã minh họa, chưa có dữ liệu nguồn nên không biên dịch độc lập.
final class MySpliterator
        extends Spliterators.AbstractSpliterator<MyItem> {

    MySpliterator() {
        super(Long.MAX_VALUE, Spliterator.ORDERED);
    }

    @Override
    public boolean tryAdvance(Consumer<? super MyItem> action) {
        // Đọc một phần tử từ nguồn rồi gọi action.accept(item).
        // Trả true khi đã phát một phần tử, false khi kết thúc nguồn.
    }
}
```

Ý nghĩa của constructor:

- Tham số `est` là **estimated size**. Nếu thực sự không biết số lượng, dùng `Long.MAX_VALUE`.
- Tham số thứ hai là các `characteristics` thật sự bảo đảm; ví dụ nguồn dòng văn bản tuần tự có thể là `ORDERED | NONNULL`.
- Lớp nền cung cấp `estimateSize()`, `characteristics()` và một chiến lược `trySplit()` mặc định **đệm phần tử theo các lô**. Nó thường tăng kích thước lô ở những lần chia tiếp theo để hỗ trợ xử lý song song trong giới hạn nhất định.
- Bạn vẫn phải triển khai `tryAdvance(Consumer<? super T>)` đúng hợp đồng; đối với mã này, đó là phần đọc nguồn và chuyển phần tử sang downstream.

### Cách chia mặc định có đánh đổi

`AbstractSpliterator.trySplit()` không thể suy ra chỉ mục giữa một nguồn chỉ đọc tuần tự. Nó có thể **gọi tryAdvance nhiều lần**, tích lũy một nhóm phần tử vào mảng rồi trả một Spliterator cho nhóm đó. Từ đó:

- **Ưu điểm:** ít mã cần viết, có cơ chế chia cơ bản ngay cả khi nguồn chỉ đọc lần lượt.
- **Giới hạn:** việc lấy các lô đầu vào vẫn có thể là **nút cổ chai tuần tự**; cấp phát bộ đệm có thể tốn bộ nhớ; dữ liệu rất lớn hoặc I/O chậm không tự nhiên trở nên dễ chia cân bằng.
- **Không có bảo đảm nhanh hơn:** nếu chi phí tạo lô vượt lợi ích xử lý mỗi phần tử, `parallelStream` có thể chậm hơn.
- **Ưu tiên tự viết trySplit** nếu nguồn có ranh giới chia tự nhiên, ví dụ một mảng, một khoảng số nguyên, phân đoạn tệp hoặc các block đã được index.

Người mới thường nghĩ "kế thừa AbstractSpliterator là tự động tối ưu parallel". Thực tế, nó chỉ cho một **default splitting strategy** có những đánh đổi cụ thể.

## 7. Ví dụ 2 — AbstractSpliterator cho nguồn đọc từng dòng

Giả sử dữ liệu đến từ một `BufferedReader`: không biết trước có bao nhiêu dòng, chỉ lấy được dòng tiếp theo thông qua `readLine()`. Ta tạo một Spliterator phát **từng dòng thô**, sau đó Stream tự chuẩn hóa và loại dòng trắng.

Tệp **`AbstractLineSourceDemo.java`** (Java 8+):

```java
import java.io.*;
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class AbstractLineSourceDemo {
    static final class BufferedLineSpliterator
            extends Spliterators.AbstractSpliterator<String> {
        private final BufferedReader reader;

        BufferedLineSpliterator(BufferedReader reader) {
            super(Long.MAX_VALUE,
                Spliterator.ORDERED | Spliterator.NONNULL);
            this.reader = Objects.requireNonNull(reader);
        }

        @Override
        public boolean tryAdvance(Consumer<? super String> action) {
            Objects.requireNonNull(action);
            try {
                String line = reader.readLine();
                if (line == null) return false;

                action.accept(line);
                return true;
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
    }

    public static void main(String[] args) throws IOException {
        try (BufferedReader reader = new BufferedReader(
                new StringReader("alpha\n\n beta \ncharlie\n"))) {

            Spliterator<String> lines =
                new BufferedLineSpliterator(reader);

            System.out.println("exactSize="
                + lines.getExactSizeIfKnown());

            List<String> cleaned =
                StreamSupport.stream(lines, false)
                    .map(String::trim)
                    .filter(s -> !s.isEmpty())
                    .collect(Collectors.toList());

            System.out.println("cleaned=" + cleaned);
        }
    }
}
```

```bash
javac -encoding UTF-8 AbstractLineSourceDemo.java
java AbstractLineSourceDemo
```

```text
exactSize=-1
cleaned=[alpha, beta, charlie]
```

**Giải thích:**

1. `BufferedReader.readLine()` trả về chuỗi không null khi còn dữ liệu, và null khi hết dữ liệu. Vì vậy `NONNULL` là cam kết đúng đối với **những phần tử đã phát ra**.
2. `tryAdvance` gọi `action.accept(line)` **một lần** cho mỗi dòng; dòng rỗng vẫn được phát như chuỗi rỗng. `filter` xử lý dòng rỗng ở pipeline, không làm sai khái niệm "một lần tryAdvance phát một phần tử".
3. Nguồn giữ thứ tự từng dòng, nên khai báo `ORDERED`. Kích thước không biết trước, nên **không khai báo `SIZED`**.
4. `readLine()` có thể ném `IOException` (checked exception), nhưng `tryAdvance` của `Spliterator` không khai báo checked exception. Ở ví dụ, lỗi được bọc vào `UncheckedIOException` để lan ra, **không âm thầm bỏ qua dòng lỗi**.
5. `try (BufferedReader reader = ...)` giúp đóng reader đúng vòng đời. Việc terminal operation hoặc `Stream.close()` xảy ra **không tự bảo đảm** tài nguyên bên ngoài được đóng nếu bạn không gắn lifecycle hoặc tự quản lý đóng.
6. Đầu vào ví dụ dùng `StringReader` để chạy được không cần tệp. Với tệp thật hoặc socket, cần xác định quyền sở hữu, cách báo lỗi và lúc đóng kết nối cho đúng.

**Hạn chế về hiệu năng:** nguồn đọc tuần tự như `BufferedReader` không thật sự phân chia tốt theo địa chỉ/offset. `AbstractSpliterator` có thể đệm từng lô để làm `trySplit()`, nhưng đọc I/O vẫn là phần khó chia; chạy parallel không chắc có lợi. Với file lớn, đôi khi sử dụng API đọc dòng có quản lý tài nguyên thích hợp hoặc xử lý theo block được thiết kế riêng hiệu quả hơn việc tạo một spliterator từ một reader duy nhất.

## 8. Tự triển khai trySplit khi nguồn có thể chia cân bằng

Một nguồn có **ranh giới theo chỉ mục** thường có thể chia tự nhiên mà không phải đọc trước nhiều phần tử. Hãy xét khoảng số nguyên `[startInclusive, endExclusive)`:

```text
Nguồn gốc: [0,1,2,3,4,5,6,7,8,9]    size=10
                        │
                    trySplit()
                        │
             ┌──────────┴──────────┐
        tiền tố trả về         đối tượng gốc còn lại
         [0,1,2,3,4]             [5,6,7,8,9]
              size=5                size=5
```

Để duy trì `ORDERED`, đối tượng do `trySplit()` trả về phải giữ **tiền tố của phần chưa duyệt**, còn đối tượng hiện tại giữ phần sau. Không đảo lại chỉ vì tính tổng sẽ không khác; một pipeline thu vào List có thứ tự có thể cần kết quả chính xác theo encounter order.

Để bảo đảm `SIZED | SUBSIZED`:

- `estimateSize()` luôn đúng số phần tử chưa duyệt của chính Spliterator.
- Tổng kích thước hai phần ngay sau khi tách phải bằng kích thước phần gốc ngay trước khi tách (nếu chưa có thao tác duyệt xen vào).
- Mọi nhánh được chia tiếp cũng phải báo kích thước chính xác.
- Mỗi lời gọi `tryAdvance` thành công làm kích thước còn lại giảm đúng một phần tử.

Nếu không thể đáp ứng những điều trên, **không khai báo SUBSIZED/SIZED** chỉ để tăng tốc.

## 9. Ví dụ 3 — Spliterator.OfInt với trySplit cân bằng

Chương trình dưới đây tự viết `Spliterator.OfInt` cho khoảng số nguyên tăng dần. Đầu ra là primitive `IntStream` nên không cần boxing ở bước phát phần tử; chỉ phần hiển thị dùng `boxed()` để tạo List.

Tệp **`BalancedRangeSpliteratorDemo.java`**:

```java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class BalancedRangeSpliteratorDemo {
    static final class RangeOfInt implements Spliterator.OfInt {
        private int current;
        private final int endExclusive;

        RangeOfInt(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("invalid range");
            }
            this.current = startInclusive;
            this.endExclusive = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (current >= endExclusive) return false;

            action.accept(current++);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int lo = current;
            int mid = lo + (endExclusive - lo) / 2;
            if (mid <= lo) return null;

            current = mid;
            return new RangeOfInt(lo, mid);
        }

        @Override
        public long estimateSize() {
            return (long) endExclusive - current;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED
                | Spliterator.DISTINCT
                | Spliterator.SIZED
                | Spliterator.SUBSIZED
                | Spliterator.NONNULL
                | Spliterator.IMMUTABLE;
        }
    }

    public static void main(String[] args) {
        Spliterator.OfInt right = new RangeOfInt(0, 10);
        Spliterator.OfInt left = right.trySplit();

        if (left == null || left.estimateSize() != 5
                || right.estimateSize() != 5) {
            throw new AssertionError("incorrect split");
        }

        List<Integer> ordered =
            StreamSupport.intStream(new RangeOfInt(0, 10), true)
                .boxed()
                .collect(Collectors.toList());

        List<Integer> expected =
            Arrays.asList(0, 1, 2, 3, 4, 5, 6, 7, 8, 9);

        if (!expected.equals(ordered)) {
            throw new AssertionError(
                "ordered parallel result differs");
        }

        int sum = StreamSupport.intStream(
            new RangeOfInt(0, 10), true).sum();

        if (sum != 45) {
            throw new AssertionError("wrong sum");
        }

        System.out.println("leftSize=" + left.estimateSize());
        System.out.println("rightSize=" + right.estimateSize());
        System.out.println("orderedParallel=" + ordered);
        System.out.println("sum=" + sum);
    }
}
```

```bash
javac -encoding UTF-8 BalancedRangeSpliteratorDemo.java
java BalancedRangeSpliteratorDemo
```

```text
leftSize=5
rightSize=5
orderedParallel=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
sum=45
```

**Phân tích:**

- `RangeOfInt(0,10)` có mười giá trị: 0–9, không gồm 10.
- `trySplit()` tạo `RangeOfInt(lo,mid)` cho **tiền tố**; cập nhật đối tượng hiện tại bắt đầu tại `mid` cho **hậu tố**.
- Khi khoảng chỉ còn không quá một phần tử, `trySplit()` trả null; việc đó là hợp lệ.
- `estimateSize()` dùng phép trừ ép sang `long` sau khi lấy `endExclusive`; với đoạn `int` hợp lệ ở ví dụ, kết quả không âm và chính xác.
- `SIZED | SUBSIZED` là đúng vì mọi nửa của khoảng chỉ mục đều biết số phần tử chính xác.
- `DISTINCT` đúng vì các giá trị nguyên trong cùng khoảng là duy nhất; `NONNULL` đúng vì phần tử là primitive `int`; `IMMUTABLE` đúng vì nguồn là quy tắc khoảng bất biến, không có bộ chứa bên ngoài bị thay đổi.
- Mặc dù các số tăng dần, ví dụ **không khai báo SORTED**; nếu cần khai báo đặc tính này trong một triển khai khác, phải tuân thủ thêm hợp đồng `getComparator()`. Không cần khai báo cờ chỉ để mô tả điều không phục vụ bài toán.
- `StreamSupport.intStream(..., true)` có thể chia nguồn để chạy song song; kết quả `collect(toList())` từ ordered stream vẫn là dãy đúng theo encounter order. Việc tính tổng cũng chính xác ở ví dụ nhỏ.

**Khi nào không cần tự viết class này?** Để tạo chính các số nguyên từ 0 đến 9 trong ứng dụng, **`IntStream.range(0,10)`** sẵn có, đơn giản hơn và có triển khai được tối ưu. Mã tùy biến được trình bày để hiểu đúng hợp đồng chia dữ liệu — không phải đề xuất thay `IntStream.range` bằng code tự viết trong sản phẩm.

## 10. So sánh factory, AbstractSpliterator và tự triển khai

| Tiêu chí | Factory `Spliterators` | `AbstractSpliterator` | Tự implements `Spliterator` |
| --- | --- | --- | --- |
| Số lượng mã | Ít | Trung bình | Nhiều |
| Nguồn điển hình | Mảng, Iterator, Collection | Reader/cursor chỉ lấy lần lượt | Khoảng chỉ mục, các block có ranh giới rõ |
| Cần triển khai `tryAdvance`? | Không | **Có** | **Có** |
| Cần triển khai `trySplit`? | Không, dùng factory | Không bắt buộc, có cách chia theo lô | Cần tự viết nếu muốn nguồn chia được; có thể trả null |
| Có thể dùng parallel? | Có, tùy khả năng chia của nguồn | Có, nhưng batch split có đánh đổi | Có nếu thiết kế tách nguồn đúng |
| Có biết kích thước chính xác? | Tùy factory/nguồn | Tùy `est` và cờ đúng đắn | Tùy hợp đồng nguồn do bạn quản lý |
| Nguy cơ chính | Khai báo size/flags không đúng | `tryAdvance` sai, I/O, batch chậm | Phần chia chồng lấp hoặc thiếu, sai characteristic |

**Quy tắc thực dụng:** bắt đầu từ API cao nhất sẵn có. Nếu `Collection.stream()` giải quyết được bài toán, đừng xuống lớp Spliterator. Nếu nguồn chỉ có Iterator, dùng factory. Nếu nguồn sinh dữ liệu tuần tự, cân nhắc AbstractSpliterator. Chỉ tự viết Spliterator đầy đủ khi có yêu cầu rõ về cách tách, thứ tự, kích thước hoặc hiệu năng.

## 11. Vòng đời nguồn: binding, thay đổi dữ liệu và tài nguyên

### 11.1. Stream không sở hữu mọi tài nguyên bên dưới

`StreamSupport.stream(spliterator, false)` **không tự biết cách đóng** một `BufferedReader`, kết nối mạng hoặc cursor dữ liệu do ứng dụng mở. Nếu nguồn dùng tài nguyên cần đóng, hãy thiết kế rõ ai sở hữu chúng:

- Quản lý bằng `try-with-resources` xung quanh cả quá trình tạo và tiêu thụ Stream, như ví dụ đọc dòng.
- Hoặc, khi phù hợp, liên kết lifecycle của Stream bằng `onClose(...)` với một hành động đóng đúng hợp đồng. Lưu ý Stream không tự đóng chỉ vì terminal operation kết thúc; bên gọi vẫn phải đóng Stream nếu cần kích hoạt close handler.
- Không truyền Stream dùng reader ra khỏi phạm vi `try-with-resources` rồi mới duyệt: reader có thể đã đóng.
- Với tài nguyên có exception lúc đóng, lựa chọn API và chiến lược chuyển/lan truyền lỗi phải rõ ràng. Không bỏ lỗi đóng một cách im lặng.

Một `Spliterator` **không phải** là một `AutoCloseable`. Việc nói "tôi đã tạo Stream từ Spliterator" chưa giải quyết quản lý tài nguyên.

### 11.2. Late-binding và non-interference

Một số Spliterator có tính **late-binding** (chỉ lấy dữ liệu/bắt đầu cố định nguồn lúc bắt đầu duyệt hoặc chia), một số khác liên kết với iterator/cursor cụ thể ngay khi tạo. Không được mặc định mọi factory đều late-binding như nhau.

Khi nguồn **không hỗ trợ sửa đồng thời**, tránh thay đổi cấu trúc dữ liệu từ lúc bắt đầu duyệt đến khi hoàn tất. Không phụ thuộc vào việc mọi vi phạm đều tạo `ConcurrentModificationException`: cơ chế fail-fast là best-effort ở nhiều nguồn, không phải biện pháp đồng bộ.

Nếu nguồn thay đổi trong khi pipeline đang chạy, kết quả có thể không nhất quán trừ khi Spliterator/collection có **hợp đồng CONCURRENT hoặc snapshot** được định nghĩa rõ. `parallel=true` không khiến nguồn mutable tự nhiên trở nên thread-safe.

### 11.3. Dùng Supplier khi cần trì hoãn lấy Spliterator

Java 8 có overload:

```java
// Chữ ký API, không phải chương trình độc lập.
Stream<T> StreamSupport.stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel
);
```

Overload nhận `Supplier` cho phép trì hoãn thời điểm lấy Spliterator cho đến khi terminal operation bắt đầu; hữu ích để thu hẹp cửa sổ có thể phát sinh thay đổi dữ liệu ở một số nguồn. **Bộ characteristics cung cấp phải nhất quán với Spliterator do supplier tạo ra**; nếu không, hành vi có thể không xác định theo hợp đồng.

Vẫn phải thiết kế khả năng dùng một lần của nguồn và vòng đời tài nguyên. Supplier không tự làm nguồn I/O có thể chạy nhiều lần, không làm nó bất biến, và không đóng tài nguyên.

## 12. Kiểm thử Spliterator tự tạo: ưu tiên bất biến của dữ liệu

Với custom `trySplit`, đừng chỉ kiểm tra số phần tử bằng `count()`; còn phải kiểm tra **đúng các phần tử và đúng encounter order** nếu có `ORDERED`.

Ma trận nên có:

| Tình huống | Điều cần kiểm |
| --- | --- |
| Nguồn rỗng | `tryAdvance` trả false, không gọi action; `trySplit` có thể trả null |
| Một phần tử | Chỉ phát một lần, không trùng; sau đó kết thúc |
| Nhiều phần tử | Duyệt tuần tự tạo đủ đúng dữ liệu nguồn |
| Chia một lần | Kết quả tiền tố + hậu tố tái lập toàn bộ nguồn theo thứ tự |
| Chia nhiều tầng | Mọi nhánh không giao nhau, không mất/trùng |
| `SIZED/SUBSIZED` | Mỗi nhánh báo đúng số phần tử còn lại trước và sau khi duyệt |
| Ordered source | `parallel` và `sequential` cho cùng kết quả khi terminal giữ thứ tự |
| Dữ liệu có null | Không khai báo `NONNULL` sai; xử lý/null policy rõ |
| Nguồn bị lỗi | Truyền exception đúng, không nuốt lỗi rồi trả EOF giả |
| Resource-backed | Reader/cursor được đóng cả khi thành công và khi gặp exception |
| Nguồn lớn | Kiểm thử cấp phát, throughput, GC, tính cân bằng của `trySplit` |

Phương pháp kiểm tra cụ thể với ví dụ khoảng số:

1. Tạo `new RangeOfInt(0,10)`.
2. Gọi `trySplit()`, xác minh tiền tố mới có `estimateSize()==5` và đối tượng gốc còn `5`.
3. Duyệt từng phần độc lập: tiền tố phải cho `[0,1,2,3,4]`, phần gốc `[5,6,7,8,9]`.
4. Ghép **theo encounter order** và so với dãy gốc; sau đó lặp lại với nhiều điểm chia hoặc chia nhiều tầng.
5. Chạy Stream tuần tự/sóng song và so kết quả thực, không chỉ số lượng.
6. Thử với khoảng rỗng, một phần tử, khoảng kích thước lẻ và biên dữ liệu để bắt lỗi off-by-one.

**Đừng thử song song bằng cách cho hai luồng cùng gọi tryAdvance trên cùng một Spliterator không CONCURRENT.** Mô hình thường dùng là phân chia trước rồi giao mỗi Spliterator con cho tác vụ riêng. Cần phân biệt **an toàn giữa các nhánh riêng biệt** với **nhiều luồng đồng thời sửa một đối tượng iterator/cursor**.

### Test lỗi khai báo SIZED

Nếu một Spliterator công bố `SIZED` nhưng `estimateSize()` sai, một số terminal operation có thể sử dụng trực tiếp thông tin kích thước mà không duyệt như bạn mong đợi. Vì thế test phải tự đếm số lần `tryAdvance` phát ra dữ liệu khi cần, đồng thời đối chiếu với kích thước được khai báo; không dùng riêng `stream.count()` làm bằng chứng rằng tất cả phần tử thật đã được duyệt.

## 13. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `spliteratorUnknownSize` rồi kỳ vọng báo exact size | `getExactSizeIfKnown()` trả `-1` | Dùng factory biết kích thước chỉ khi số phần tử chính xác |
| Gắn `SIZED` dù nguồn chỉ có số đoán | Stream tối ưu dựa trên số lượng không đúng | Bỏ cờ, báo `Long.MAX_VALUE` nếu không biết |
| Gắn `SORTED` nhưng không đáp ứng `getComparator` | Vi phạm hợp đồng, lỗi khi được hỏi comparator | Triển khai đầy đủ hoặc bỏ cờ |
| Gắn `NONNULL` cho nguồn có thể phát null | Tối ưu/hành vi downstream có thể dựa trên cam kết sai | Bỏ cờ hoặc chuẩn hóa dữ liệu trước |
| `tryAdvance` gọi action hai lần rồi trả true | Một lần gọi không còn tương ứng một phần tử | Chỉ phát đúng một phần tử cho mỗi lần thành công |
| `trySplit` trả hai phần chồng lấp | Bản ghi trùng, tổng sai khi parallel | Cắt đoạn không giao nhau; thử nhiều kích thước |
| `trySplit` bỏ mất một khoảng | Thiếu phần tử khi parallel | Kiểm định hợp của các nhánh bằng nguồn gốc |
| `trySplit` trả phần hậu tố khi có ORDERED | Kết quả ordered có thể sai | Trả tiền tố, giữ phần còn lại ở đối tượng gốc |
| `trySplit` luôn trả null trên nguồn lớn dễ chia | Không tận dụng chia công việc | Viết cách chia cân bằng hoặc dùng factory sẵn có |
| Kế thừa AbstractSpliterator rồi nghĩ parallel chắc nhanh | Batch split tốn đọc trước và cấp phát | Đo hiệu năng, cân nhắc nguồn chia theo chỉ mục |
| Dùng `StreamSupport.stream(readerSpliterator)` mà không đóng reader | Rò rỉ file handle/kết nối | Dùng try-with-resources hoặc lifecycle đóng rõ |
| Chia sẻ một Iterator/cursor mutable qua nhiều thread tự do | Race và dữ liệu không ổn định | Một chủ sở hữu duyệt nguồn, Spliterator chia riêng hoặc đồng bộ đúng hợp đồng |
| Reuse Stream/Spliterator đã tiêu thụ | Không có dữ liệu, có thể ném IllegalStateException cho Stream | Tạo Stream/Spliterator mới từ nguồn có thể tái sử dụng |
| Tự viết nguồn int thay `IntStream.range` khi không cần | Tăng mã và rủi ro lỗi | Ưu tiên API built-in |

## 14. Chọn cách làm theo tình huống thực tế

**Tình huống A — Có một List hay Set đang trong bộ nhớ.** Dùng `collection.stream()` hoặc `collection.parallelStream()`. Không cần adapter nếu không có ràng buộc bổ sung.

**Tình huống B — API thư viện chỉ cho Iterator, kích thước không rõ.** Dùng `Spliterators.spliteratorUnknownSize(iterator, flags)` và `StreamSupport.stream(..., false)` trước. Đánh giá việc parallel thật sự có ích hay không vì iterator chỉ cung cấp một hướng duyệt.

**Tình huống C — API cho Iterator và số phần tử còn lại đã xác minh.** Dùng `Spliterators.spliterator(iterator, actualRemainingSize, flags)`. Không gắn `SIZED` thủ công nếu con số không đáng tin.

**Tình huống D — Đọc file/socket theo dòng.** Dùng một reader cùng chiến lược close rõ ràng; có thể kế thừa `AbstractSpliterator` khi cần tùy biến cách phát phần tử. Nếu chỉ cần đọc các dòng file theo API có sẵn, cân nhắc API cấp cao phù hợp thay vì tự cài đặt Spliterator.

**Tình huống E — Có nhiều block được đánh chỉ mục, phân chia rẻ.** Cân nhắc tự cài đặt `Spliterator` với `trySplit` trả các đoạn không chồng lấp và `estimateSize` chính xác nếu có thể. Test dữ liệu rỗng/lẻ, nhiều cấp chia và order.

**Tình huống F — Dãy số nguyên/long tiêu chuẩn.** Dùng `IntStream.range` / `LongStream.range` khi có thể. Ví dụ `RangeOfInt` chỉ dành để học nguyên lý hoặc cho nguồn có quy tắc thực sự đặc thù.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `Spliterators.spliteratorUnknownSize(iterator, flags)` khác `spliterator(iterator, size, flags)` ở đâu?  
**Trả lời:** Factory thứ nhất không biết exact size và loại bỏ `SIZED/SUBSIZED`; factory thứ hai dựa trên số phần tử còn lại được cung cấp chính xác, có thể công bố kích thước cho framework.

**Câu 2.** Vì sao `AbstractSpliterator` chỉ cần bạn triển khai `tryAdvance` trong nhiều bài toán?  
**Trả lời:** Lớp nền đã có cách tính estimated size/characteristics và chiến lược `trySplit` theo lô. Nhưng điều đó không tự bảo đảm parallel nhanh.

**Câu 3.** `tryAdvance` trả `true` nhưng không gọi action có đúng không?  
**Trả lời:** Không. Mỗi lần trả true nghĩa là đã phát đúng **một** phần tử cho action; trả false khi hết dữ liệu và không gọi action.

**Câu 4.** Trong nguồn ordered, `trySplit` phải trả phần nào?  
**Trả lời:** Tiền tố của các phần tử chưa duyệt; đối tượng gốc giữ phần còn lại. Điều này giúp giữ encounter order khi framework gộp kết quả.

**Câu 5.** Có thể gắn `SUBSIZED` khi chỉ Spliterator gốc biết chính xác kích thước không?  
**Trả lời:** Không. Phải bảo đảm mọi Spliterator con sau các lần chia cũng đáp ứng `SIZED/SUBSIZED`.

**Câu 6.** `StreamSupport.stream(spliterator, true)` có đóng Reader khi xử lý xong không?  
**Trả lời:** Không tự động; quản lý Reader qua try-with-resources hoặc thiết kế close handler và vòng đời Stream rõ ràng.

**Câu 7.** Nguồn chỉ có Iterator lấy dữ liệu lần lượt có nên mặc định chạy song song không?  
**Trả lời:** Không. Việc chia có thể cần đệm và lấy phần tử tuần tự; chỉ dùng parallel khi benchmark cho thấy lợi ích trong workload thực tế.

**Câu 8.** Vì sao mẫu nguồn khoảng số tự tạo không gắn `SORTED` dù các số đang tăng?  
**Trả lời:** Không cần khai báo cờ để hoàn thành mục tiêu ví dụ; khi khai báo `SORTED` phải đáp ứng thêm hợp đồng `getComparator`. Khai báo ít nhưng đúng an toàn hơn gắn thêm cờ tùy tiện.

## Tài liệu chính thức (API vẫn dùng trên JDK hiện đại)

- [Java SE 8 — Spliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterator.html): hợp đồng `tryAdvance`, `trySplit`, `estimateSize`, `characteristics` và nghĩa của các bit.
- [Java SE 8 — Spliterators](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterators.html): các factory cho array, iterator, collection và adapter.
- [Java SE 8 — Spliterators.AbstractSpliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterators.AbstractSpliterator.html): lớp nền cùng chiến lược chia mặc định.
- [Java SE 8 — StreamSupport](https://docs.oracle.com/javase/8/docs/api/java/util/stream/StreamSupport.html): tạo Stream từ Spliterator hoặc supplier.
- [Java SE 8 — java.util.stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html): yêu cầu non-interference, stateless behaviors và parallel execution.

**Kết luận:** `Spliterators` là giải pháp adapter nhanh cho các nguồn chuẩn; `AbstractSpliterator` giúp tạo nguồn duyệt tuần tự mà không tự viết `trySplit`; còn Spliterator tùy biến đầy đủ có giá trị khi **thật sự có cách phân chia tốt**. Đúng đắn luôn đi trước hiệu năng: chỉ khai báo characteristics có thể bảo đảm, cho mỗi phần tử xuất hiện đúng một lần, giữ đúng thứ tự khi đã cam kết, đóng tài nguyên đúng vòng đời, và thử cả tuần tự lẫn song song.