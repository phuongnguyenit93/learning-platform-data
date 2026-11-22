# Thiết kế Spliterator cho nguồn dữ liệu chia theo lô

## 1. Bài toán và mục tiêu của dự án

Trong module **`JAVA_STREAM_API`**, ta đã dùng pipeline khai báo với nguồn dữ liệu, các thao tác lazy như `filter`, `map` và các terminal operation như `reduce`, `collect`. Ở phần nâng cao, muốn xử lý một nguồn lớn bằng `parallelStream`, ta phải hiểu cách **chia dữ liệu thành những phần công việc có thể xử lý độc lập**.

Giả sử một chương trình nhận 40.000 bản ghi từ một danh sách đã tải sẵn. Nghiệp vụ cần chuyển đổi từng bản ghi, lọc dữ liệu hợp lệ và tính tổng. Ta muốn mỗi lần thử tách nguồn chỉ tạo một **lô tối đa B phần tử** để kiểm soát kích thước phần công việc.

Chúng ta sẽ thiết kế một `Spliterator<T>` tùy chỉnh mang tên `BatchSpliterator<T>`, kết nối nó với `StreamSupport.stream(...)`, rồi kiểm tra:

- Có **đủ tất cả phần tử** không?
- Có **phần tử nào bị lặp** giữa các lô không?
- Nếu nguồn có thứ tự, các lô có bảo toàn **encounter order** không?
- `estimateSize` có chính xác sau mỗi lần tách và tiêu thụ không?
- Kết quả `reduce` / `collect` của stream song song có giống kết quả đúng từ nguồn không?
- Lô lớn, lô nhỏ và chính sách sao chép nguồn ảnh hưởng hiệu năng, bộ nhớ như thế nào?

**Kết quả học tập:** không chỉ biết cài `trySplit`, bạn còn hiểu hợp đồng `ORDERED`, `SIZED`, `SUBSIZED`, cách Stream runtime có thể chia công việc, và cách thiết kế thử nghiệm có khả năng bắt lỗi bỏ sót hoặc xử lý trùng dữ liệu.

Bài thuộc chương **Bài tập nâng cao và dự án**. Đây là bài tích hợp về Spliterator, parallel stream, `filter`, `map`, `reduce`, `collect` và giới hạn về trạng thái, tài nguyên, hiệu năng. Hướng dẫn không giả định việc chạy song song luôn nhanh hơn tuần tự.

## 2. Thế nào là “chia theo lô”?

Một **lô** (*batch*) trong bài này là một **đoạn phần tử liên tiếp** của nguồn có thứ tự. Mỗi lần `trySplit()` thành công sẽ tách một **tiền tố** (*prefix*) có không quá `batchSize` phần tử ra thành spliterator mới.

Ví dụ nguồn:

```text
Nguồn ordered: [1, 2, 3, 4, 5, 6, 7, 8]
batchSize = 3

Spliterator ban đầu: [1, 2, 3, 4, 5, 6, 7, 8]
  ├─ lần tách 1 → [1, 2, 3]     | phần còn lại [4, 5, 6, 7, 8]
  └─ lần tách 2 → [4, 5]        | phần còn lại [6, 7, 8]

Các đoạn cuối: [1, 2, 3] | [4, 5] | [6, 7, 8]
```

Với thuật toán được dùng trong bài, **batchSize là kích thước tối đa của một phần công việc sau khi chia hết**, không có nghĩa mọi lô phải chứa chính xác `batchSize` phần tử. Sự phân chia ở ví dụ chỉ minh họa thuật toán cụ thể; runtime Stream không cam kết sẽ thực hiện đúng hai lần tách.

Cần phân biệt:

1. **Lô để chia việc (`trySplit`):** quyết định mỗi spliterator con sở hữu những phần tử nào.
2. **Phần tử để tiêu thụ (`tryAdvance`):** vẫn cung cấp **từng phần tử** cho pipeline `filter`, `map`.
3. **Lô I/O hoặc lô mạng:** một cơ chế lấy dữ liệu theo nhóm từ cơ sở dữ liệu/dịch vụ, có vòng đời tài nguyên riêng. BatchSpliterator trên `List` của bài này **chưa tự thực hiện truy vấn theo batch**.

### Đặt yêu cầu trước khi viết code

| Yêu cầu | Bất biến cần giữ |
| --- | --- |
| Không mất phần tử | Hợp của tất cả phần tách và phần còn lại đúng bằng tập vị trí ban đầu. |
| Không lặp phần tử | Các vùng chỉ số của hai spliterator con không giao nhau. |
| Giữ thứ tự | Với `ORDERED`, `trySplit` trả tiền tố của vùng chưa duyệt. |
| Biết kích thước | `estimateSize()` bằng số vị trí còn lại trong vùng. |
| Chia hữu hạn | Khi vùng còn tối đa B phần tử, `trySplit()` trả `null`. |
| Không chia sẻ con trỏ | Mỗi spliterator có `index` riêng; chỉ chia sẻ dữ liệu đọc ổn định. |
| Không giấu lỗi | `batchSize` không hợp lệ phải bị từ chối rõ ràng. |

Nếu thiếu một trong các bất biến, lỗi có thể không xuất hiện trên `stream()` tuần tự mà chỉ bộc lộ khi `StreamSupport.stream(spliterator, true)` song song hóa.

## 3. Những phương thức và characteristics phải hiểu

`Spliterator<T>` có các phương thức then chốt:

| API | Hợp đồng |
| --- | --- |
| `boolean tryAdvance(Consumer<? super T> action)` | Phát tối đa một phần tử, trả `true` nếu đã phát, `false` nếu hết. |
| `void forEachRemaining(Consumer<? super T> action)` | Phát tất cả phần tử còn lại. |
| `Spliterator<T> trySplit()` | Thử tách một vùng phần tử để xử lý riêng; trả `null` nếu không chia. |
| `long estimateSize()` | Ước lượng số phần tử chưa tiêu thụ; chính xác khi cam kết `SIZED`. |
| `int characteristics()` | Khai báo đặc tính của nguồn và các phần tách. |

Các cờ quan trọng:

- **`ORDERED`:** nguồn có thứ tự gặp; spliterator được tách phải có quan hệ tiền tố/hậu tố phù hợp.
- **`SIZED`:** số phần tử còn lại được biết chính xác.
- **`SUBSIZED`:** các spliterator từ `trySplit` cũng có `SIZED` và `SUBSIZED`.
- **`NONNULL`:** chỉ dùng khi chắc chắn **không có giá trị `null`**.
- **`DISTINCT`:** chỉ dùng khi biết các phần tử duy nhất theo `equals`.
- **`SORTED`:** chỉ dùng khi dữ liệu thực sự theo comparator phù hợp và spliterator đáp ứng hợp đồng `getComparator()`.
- **`IMMUTABLE`:** chỉ khai báo khi nguồn không thể bị sửa cấu trúc trong lúc duyệt theo hợp đồng phù hợp; không đánh đồng lời hứa “người gọi đừng sửa” với bất biến được đảm bảo.

Không nên bật `CONCURRENT` chỉ vì dùng `parallel()`. `CONCURRENT` có nghĩa nguồn **hỗ trợ thay đổi cấu trúc đồng thời theo hợp đồng**, không phải “có thể xử lý nhiều vùng dữ liệu tách biệt”.

Với thiết kế dùng **một bản sao `ArrayList` riêng, không bị lớp này sửa đổi**, ta chọn tối thiểu:

```java
Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
```

Không khai báo `NONNULL` vì dữ liệu đầu vào có thể có `null`; không khai báo `SORTED` hay `DISTINCT` vì không kiểm chứng những tính chất đó. Chỉ định đúng các cờ đã đủ để Stream runtime nhận biết khả năng chia mà không cần “tối ưu hóa” bằng các tuyên bố sai.

## 4. Chọn biểu diễn vùng [index, fence)

Thay vì tạo list con cho mỗi phép chia, phiên bản đầu dùng các **khoảng chỉ số nửa mở**:

```text
data:  [A, B, C, D, E, F, G, H]
index:  0
fence:  8
vùng sở hữu: [0, 8) = A..H

Sau trySplit:
  phần trả ra:    [0, 3) = A, B, C
  phần còn lại:   [3, 8) = D, E, F, G, H
```

Các trường:

- `data`: danh sách chụp lại từ đầu vào để đọc ổn định.
- `index`: vị trí phần tử tiếp theo của **spliterator hiện tại**.
- `fence`: vị trí kết thúc **không bao gồm**.
- `batchSize`: giới hạn kích thước phần việc sau khi chia.

Bất biến kích thước:

```text
0 <= index <= fence <= data.size()
estimateSize() == fence - index
```

Nếu tách tại vị trí `cut`, ta phải duy trì:

```text
[index_old, fence)
     = [index_old, cut)  +  [cut, fence)

hai phần không chồng lấn, tổng kích thước không đổi
```

**Lựa chọn nguồn `List`:** ta tạo bản sao `ArrayList` bằng `new ArrayList<>(source)`. Điều đó giúp `get(index)` nhanh và không phụ thuộc việc người gọi tiếp tục thêm/xóa phần tử từ danh sách ban đầu sau khi tạo spliterator. Đây chỉ là **bản sao nông**: nếu các phần tử là đối tượng có thể sửa, nội dung của chúng vẫn có thể thay đổi ngoài ý muốn.

Việc sao chép tốn **O(n) bộ nhớ và thời gian khởi tạo**. Với nguồn đã nằm trong `ArrayList` bất biến theo cách sử dụng, spliterator có sẵn có thể hiệu quả hơn. Mục tiêu của phiên bản tùy chỉnh là học **hợp đồng chia lô**, không khẳng định nó tối ưu cho mọi nguồn.

## 5. Cài đặt `BatchSpliterator<T>` hoàn chỉnh (Java 8+)

Đặt chương trình sau vào `BatchDemo.java`. Nó có thể biên dịch và chạy với Java 8 trở lên.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

public class BatchDemo {
    public static final class BatchSpliterator<T>
            implements Spliterator<T> {

        private final List<T> data;
        private int index;
        private final int fence;
        private final int batchSize;

        private BatchSpliterator(
                List<T> data,
                int index,
                int fence,
                int batchSize) {
            this.data = data;
            this.index = index;
            this.fence = fence;
            this.batchSize = batchSize;
        }

        public static <T> BatchSpliterator<T> snapshotOf(
                List<? extends T> source,
                int batchSize) {
            Objects.requireNonNull(source, "source");

            if (batchSize <= 0) {
                throw new IllegalArgumentException(
                    "batchSize phai > 0"
                );
            }

            // Chụp cấu trúc danh sách trước khi chia.
            List<T> snapshot = new ArrayList<>(source);
            return new BatchSpliterator<>(
                snapshot, 0, snapshot.size(), batchSize
            );
        }

        @Override
        public boolean tryAdvance(Consumer<? super T> action) {
            Objects.requireNonNull(action, "action");

            if (index >= fence) {
                return false;
            }

            T value = data.get(index);
            index++;
            action.accept(value);
            return true;
        }

        @Override
        public void forEachRemaining(Consumer<? super T> action) {
            Objects.requireNonNull(action, "action");

            while (index < fence) {
                T value = data.get(index);
                index++;
                action.accept(value);
            }
        }

        @Override
        public Spliterator<T> trySplit() {
            int remaining = fence - index;

            // Vùng <= batchSize là một phần việc cuối.
            if (remaining <= batchSize) {
                return null;
            }

            // Trả tiền tố có tối đa batchSize phần tử.
            // Không tách tất cả vào prefix để phần còn lại
            // vẫn có dữ liệu cho phép chia tiếp.
            int prefixSize = Math.min(
                batchSize, remaining / 2
            );
            int cut = index + prefixSize;

            BatchSpliterator<T> prefix =
                new BatchSpliterator<>(
                    data, index, cut, batchSize
                );

            // Spliterator hiện tại chỉ còn đoạn [cut, fence).
            index = cut;
            return prefix;
        }

        @Override
        public long estimateSize() {
            return fence - index;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED;
        }
    }

    public static void main(String[] args) {
        List<Integer> so = IntStream.rangeClosed(1, 40)
            .boxed()
            .collect(Collectors.toList());

        List<Integer> binhPhuongChan = StreamSupport.stream(
                BatchSpliterator.snapshotOf(so, 7), true)
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());

        long tong = StreamSupport.stream(
                BatchSpliterator.snapshotOf(so, 7), true)
            .mapToLong(Integer::longValue)
            .sum();

        System.out.println(binhPhuongChan.size()); // 20
        System.out.println(binhPhuongChan.get(0)); // 4
        System.out.println(binhPhuongChan.get(19)); // 1600
        System.out.println(tong);                  // 820
    }
}
```

Điểm quan trọng trong mã:

1. `snapshotOf` từ chối lô có kích thước 0 hoặc âm và sao chép danh sách gốc.
2. `tryAdvance` cung cấp một giá trị rồi tăng `index` đúng một lần.
3. `trySplit` chỉ tách khi vùng còn nhiều hơn `batchSize` phần tử; phần mới là **tiền tố**, phần hiện tại trở thành hậu tố.
4. `estimateSize` được tính từ khoảng còn lại, nên giảm sau `tryAdvance` hoặc `trySplit`.
5. Mỗi spliterator con sở hữu `index` / `fence` riêng; chúng chỉ **đọc** cùng một danh sách snapshot.
6. `StreamSupport.stream(..., true)` yêu cầu chế độ song song; nó **không bảo đảm** luôn có nhiều thread thực sự chạy hoặc tạo một tác vụ riêng cho từng lô.

Cả hai pipeline `collect` và `sum` trong `main` tạo **spliterator mới**. Không dùng lại spliterator đã tiêu thụ để chạy terminal operation thứ hai.

### Vì sao `prefixSize = min(batchSize, remaining / 2)`?

Nếu luôn lấy cố định `batchSize` phần tử khi phần còn lại chỉ lớn hơn B một chút, có thể tạo một phần rất lớn và phần chỉ một phần tử. Công thức trên lấy không quá B và không quá nửa số phần tử còn lại, giúp tránh lô cuối quá lệch trong trường hợp gần ngưỡng.

Với `remaining > batchSize >= 1`, `remaining / 2` ít nhất bằng 1, nên `trySplit` luôn tạo hai vùng **không rỗng**. Khi mọi vùng còn tối đa B phần tử, không còn tách thêm.

Ví dụ với tám phần tử và B = 3, các lô cuối có thể là kích thước `3, 2, 3`. Không có cam kết **chính xác B phần tử mỗi lô**, chỉ có cam kết mỗi vùng cuối `<= B`.

## 6. Kiểm thử chia lô mà không cần thread

Trước khi chạy song song, hãy kiểm tra `trySplit` trực tiếp. Đó là cách tốt để tìm lỗi **mất phần tử, lặp phần tử, sai thứ tự và sai estimateSize** mà không bị nhiễu bởi lịch thực thi.

Đặt lớp kiểm thử sau bên cạnh `BatchDemo.java` (mã Java 8+):

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Spliterator;

public class BatchSplitCheck {
    static <T> void tachHet(
            Spliterator<T> current,
            List<Spliterator<T>> leaves) {

        Spliterator<T> prefix = current.trySplit();
        if (prefix == null) {
            leaves.add(current);
            return;
        }

        // Phần prefix phải đứng trước phần còn lại.
        tachHet(prefix, leaves);
        tachHet(current, leaves);
    }

    static void kiemTra(
            List<Integer> source,
            int batchSize) {

        BatchDemo.BatchSpliterator<Integer> root =
            BatchDemo.BatchSpliterator.snapshotOf(
                source, batchSize);

        long initial = root.estimateSize();
        if (initial != source.size()) {
            throw new AssertionError("Sai estimateSize ban dau");
        }

        List<Spliterator<Integer>> leaves = new ArrayList<>();
        tachHet(root, leaves);

        List<Integer> merged = new ArrayList<>();
        long totalSizes = 0L;

        for (Spliterator<Integer> leaf : leaves) {
            long size = leaf.estimateSize();
            if (size < 0 || size > batchSize) {
                throw new AssertionError("Sai kich thuoc lo: " + size);
            }
            totalSizes += size;
            leaf.forEachRemaining(merged::add);
            if (leaf.estimateSize() != 0L) {
                throw new AssertionError("Chua tieu thu het lo");
            }
        }

        if (totalSizes != source.size()) {
            throw new AssertionError("Mat/lap vi tri khi tach");
        }
        if (!merged.equals(source)) {
            throw new AssertionError("Mat/lap/sai thu tu phan tu");
        }
    }

    public static void main(String[] args) {
        kiemTra(Collections.<Integer>emptyList(), 3);
        kiemTra(Collections.singletonList(7), 3);
        kiemTra(Arrays.asList(1, 2, 3), 3);
        kiemTra(Arrays.asList(1, 2, 3, 4), 3);
        kiemTra(Arrays.asList(1, 1, 2, 2, 3, 3, 4), 2);
        kiemTra(Arrays.asList(
            1, 2, 3, 4, 5, 6, 7, 8, 9, 10), 4);

        System.out.println("PASS: split khong mat/lap/sai thu tu");
    }
}
```

Dự kiến:

```text
PASS: split khong mat/lap/sai thu tu
```

Kiểm tra danh sách có phần tử trùng là có chủ ý. Nếu chỉ so sánh `Set` của kết quả, một thuật toán làm mất một phần tử nhưng thêm lại giá trị bằng nhau ở vị trí khác **vẫn có thể vượt kiểm thử**. So sánh nguyên `List` theo thứ tự giúp phát hiện cả số lượng lẫn vị trí.

Hàm `tachHet` dùng đệ quy để minh họa dễ đọc; chỉ sử dụng với dữ liệu kiểm thử nhỏ. Với hàng triệu lô, cần viết kiểm thử lặp bằng cấu trúc quản lý công việc thay vì đệ quy quá sâu.

## 7. Kiểm thử song song: tính đúng trước khi đo hiệu năng

Giữ nguyên `BatchDemo.BatchSpliterator`, có thể kiểm tra thêm các ca tuần tự và song song:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

public class BatchParallelCheck {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static List<Integer> transformed(
            List<Integer> source,
            int batchSize,
            boolean parallel) {

        return StreamSupport.stream(
                BatchDemo.BatchSpliterator.snapshotOf(
                    source, batchSize), parallel)
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());
    }

    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 40)
            .boxed()
            .collect(Collectors.toList());

        List<Integer> expected = source.stream()
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());

        check(transformed(source, 1, false).equals(expected),
            "Sai tuan tu, batch 1");
        check(transformed(source, 1, true).equals(expected),
            "Sai song song, batch 1");
        check(transformed(source, 7, true).equals(expected),
            "Sai song song, batch 7");
        check(transformed(source, 100, true).equals(expected),
            "Sai song song, batch 100");

        List<Integer> empty = Arrays.<Integer>asList();
        check(transformed(empty, 4, true).isEmpty(),
            "Sai voi nguon rong");

        List<Integer> one = Arrays.asList(8);
        check(transformed(one, 4, true)
            .equals(Arrays.asList(64)), "Sai mot phan tu");

        long sum = StreamSupport.stream(
                BatchDemo.BatchSpliterator.snapshotOf(source, 7), true)
            .mapToLong(Integer::longValue)
            .reduce(0L, Long::sum);

        check(sum == 820L, "Sai tong");
        System.out.println("PASS: sequential/parallel dung");
    }
}
```

Chương trình đối chiếu bằng **kết quả mong đợi độc lập** từ pipeline tuần tự trên một `List`, rồi thử nhiều kích thước lô để bắt lỗi biên. Kết quả dự kiến:

```text
PASS: sequential/parallel dung
```

Chỉ quan sát một lần chạy thành công **không chứng minh** mọi đặc tính do spliterator khai báo đều đúng. Với spliterator tự viết, luôn cần xem xét cả hợp đồng phương thức và thử các trường hợp biên, không chỉ so sánh đầu ra.

## 8. Bất biến bảo toàn vị trí sau mỗi lần chia

Gọi `L = [index, fence)` là vùng còn lại. Nếu `trySplit()` trả `P = [index, cut)` thì sau thao tác:

```text
L trước = P sau  ∪  L còn lại sau
P ∩ L còn lại = ∅
|L trước| = |P| + |L còn lại|
```

Với ví dụ `[0, 8)`, tách tại `cut = 3`:

```text
Trước: [0,1,2,3,4,5,6,7]
Prefix: [0,1,2]
Remain: [3,4,5,6,7]
3 + 5 = 8
```

Các lỗi dễ gây sai khi song song:

- **Không cập nhật `index` của phần còn lại:** prefix và phần gốc đọc cùng vị trí → lặp phần tử.
- **Đặt `cut` vượt `fence`:** đọc ngoài phạm vi.
- **Tăng `index` hai lần trong `tryAdvance`:** bỏ sót phần tử.
- **Trả suffix thay vì prefix nhưng vẫn khai `ORDERED`:** có thể đảo thứ tự kết quả khi collector cần giữ encounter order.
- **`estimateSize` không giảm sau `trySplit`:** vi phạm `SIZED`/`SUBSIZED`, có thể phá các tối ưu hóa.
- **Thực hiện một phép chia luôn tạo hai vùng quá nhỏ:** nhiều tác vụ hơn cần thiết.

Vì `trySplit` có thể được gọi khi đã tiêu thụ một phần vùng hiện tại, thuật toán phải dùng **`index` đang còn lại**, không dùng một `origin` bất biến từ lúc tạo spliterator để tính vị trí prefix mới.


## 9. Khi nguồn là `Iterator`: lấy từng lô theo nhu cầu

Phiên bản `BatchSpliterator` ở trên đã sao chép toàn bộ `List` vào bộ nhớ. Nhưng các dự án thực tế có thể đọc dữ liệu từ:

- Một `Iterator<T>` tạo bản ghi tuần tự.
- Một cursor của cơ sở dữ liệu.
- Một luồng dòng văn bản.
- Một API phân trang mà mỗi lần yêu cầu trả một nhóm bản ghi.

Đối với nguồn **không hỗ trợ truy cập ngẫu nhiên** hoặc **không biết tổng số phần tử**, ta cần một chiến lược khác. Một lựa chọn là: khi `trySplit()` được yêu cầu, đọc trước **tối đa B phần tử** từ iterator và trả một spliterator độc lập cho lô vừa đọc.

### 9.1. Mẫu `IteratorBatchSpliterator<T>`

Đoạn sau là lớp Java 8+ có thể đặt vào file `IteratorBatchSpliterator.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.Consumer;

public final class IteratorBatchSpliterator<T>
        implements Spliterator<T> {

    private final Iterator<? extends T> source;
    private final int batchSize;

    public IteratorBatchSpliterator(
            Iterator<? extends T> source,
            int batchSize) {
        this.source = Objects.requireNonNull(source, "source");

        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                "batchSize phai > 0"
            );
        }

        this.batchSize = batchSize;
    }

    @Override
    public boolean tryAdvance(Consumer<? super T> action) {
        Objects.requireNonNull(action, "action");

        if (!source.hasNext()) {
            return false;
        }

        T value = source.next();
        action.accept(value);
        return true;
    }

    @Override
    public Spliterator<T> trySplit() {
        // Lấy trước tối đa batchSize phần tử.
        List<T> batch = new ArrayList<>(batchSize);

        while (batch.size() < batchSize && source.hasNext()) {
            batch.add(source.next());
        }

        // Không còn dữ liệu để tách.
        if (batch.isEmpty()) {
            return null;
        }

        // Spliterator của ArrayList này độc lập với cursor gốc.
        return batch.spliterator();
    }

    @Override
    public long estimateSize() {
        // Iterator tổng quát không biết chính xác số phần tử.
        return Long.MAX_VALUE;
    }

    @Override
    public int characteristics() {
        // Chỉ dùng nếu nguồn Iterator có thứ tự gặp có ý nghĩa.
        return Spliterator.ORDERED;
    }
}
```

Sử dụng với một `List` để kiểm thử trước:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class IteratorBatchExample {
    public static void main(String[] args) {
        List<Integer> source =
            Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8);

        List<Integer> result = StreamSupport.stream(
                new IteratorBatchSpliterator<>(
                    source.iterator(), 3),
                true)
            .map(n -> n * n)
            .collect(Collectors.toList());

        System.out.println(result);
        // [1, 4, 9, 16, 25, 36, 49, 64]
    }
}
```

Với iterator có thứ tự, lô được lấy ra cũng là **tiền tố** của phần chưa đọc. `trySplit` trả spliterator trên `ArrayList` con, nên có thể xử lý lô đó độc lập, trong khi spliterator gốc tiếp tục giữ iterator nguồn.

**Giới hạn quan trọng của phiên bản này:**

1. `Iterator` tổng quát không cho biết tổng số phần tử. Do đó spliterator gốc trả `Long.MAX_VALUE` ở `estimateSize` như một **giá trị ước lượng không biết trước**, **không được khai báo `SIZED` hoặc `SUBSIZED`**.
2. Mỗi lô tách ra có thể dùng bộ nhớ O(B). Nếu runtime tạo nhiều lô trước khi hoàn thành việc xử lý, tổng bộ nhớ vẫn có thể tăng theo số lô đang chờ.
3. `trySplit` **đọc trước phần tử**. Một terminal operation short-circuit như `findAny` hoặc `limit` có thể khiến nguồn đã đọc nhiều phần tử hơn lượng kết quả thực sự cần.
4. `Iterator` dùng chung không tự an toàn khi nhiều thread gọi `next()`. Không cho nhiều caller tự ý cùng gọi `tryAdvance` / `trySplit` của **chính một spliterator**. Phân chia có kiểm soát của Stream runtime là mô hình sử dụng khác với việc tự đồng thời gọi phương thức trên một instance.
5. Lớp giả định iterator có **thứ tự gặp ổn định**. Nếu nguồn là iterator từ `HashSet` không có encounter order được bảo đảm, không nên quảng bá `ORDERED` như một hợp đồng nghiệp vụ.
6. Đây là phiên bản minh họa **không tự đóng tài nguyên I/O**: nếu iterator bọc tệp hoặc kết nối, tầng sở hữu nguồn phải đóng tài nguyên bên ngoài.

### 9.2. So sánh hai cách chia theo lô

| Khía cạnh | `BatchSpliterator` trên snapshot `List` | `IteratorBatchSpliterator` |
| --- | --- | --- |
| Nguồn | `List` được sao chép thành `ArrayList` | `Iterator` tuần tự |
| Khi chia | Tạo vùng chỉ số mới, không sao chép phần tử mỗi lần tách | Đọc trước tối đa B phần tử vào một list |
| Tổng số phần tử | Biết chính xác | Có thể không biết |
| `SIZED` / `SUBSIZED` | Được phép với các vùng chỉ số ổn định | Không được khai trên spliterator gốc tổng quát |
| Chi phí bộ nhớ | O(N) để chụp list ban đầu | O(B) cho mỗi lô đang được giữ |
| Độ phức tạp khi truy cập | `get(index)` của `ArrayList` | Gọi `hasNext()` / `next()` |
| Khả năng cắt ngắn đọc nguồn | Không cần đọc I/O mới; dữ liệu đã nằm trong list | Có thể đã đọc trước nhiều phần tử |
| Phạm vi ứng dụng | Dữ liệu trong bộ nhớ, minh họa các vùng rời nhau | Nguồn tuần tự, chưa biết kích thước, cấp theo lô |

Đây là **hai chiến lược khác nhau**, không phải hai cách viết tương đương về tài nguyên. Nếu nguồn vốn là `ArrayList` ổn định, spliterator tích hợp của JDK thường là lựa chọn đơn giản và có thể nhanh hơn giải pháp tùy chỉnh.

## 10. Kết nối với `StreamSupport.stream` và tính lazy

Chữ ký cần biết:

```java
static <T> Stream<T> stream(
    Spliterator<T> spliterator,
    boolean parallel
)
```

- `parallel = false`: yêu cầu thực thi tuần tự.
- `parallel = true`: yêu cầu thực thi song song, nhưng **không bảo đảm** có một số thread hoặc số lần `trySplit` cố định.
- Stream nhận nguồn từ spliterator; các phép `filter`, `map` thường **chỉ chạy khi terminal operation tiêu thụ**.

Ví dụ với `BatchDemo.BatchSpliterator`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<Integer> source = Arrays.asList(1, 2, 3, 4);

Stream<Integer> pipeline = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .filter(n -> n > 2)
    .map(n -> n * 10);

// Chưa tiêu thụ pipeline.
System.out.println(pipeline.isParallel()); // true

long count = pipeline.count();
System.out.println(count); // 2
```

Không nên chèn các tác dụng phụ nghiệp vụ vào `map` hoặc `peek` rồi kỳ vọng chúng luôn chạy. Với một số pipeline mà kích thước nguồn đã biết, terminal operation như `count()` có thể dùng thông tin `SIZED` để tối ưu hóa và bỏ các bước không ảnh hưởng đến số lượng.

### Lưu ý về `SIZED` sau `filter`

`BatchSpliterator` gốc có `SIZED` vì biết chính xác số **phần tử nguồn còn lại**. Nhưng sau `filter`, số phần tử **đầu ra** thường không biết trước. Stream runtime xử lý thay đổi đặc tính này; **không** nên suy ra `filter(...).count()` sẽ luôn trả ngay kích thước nguồn.

Trong ví dụ trên, `filter(n -> n > 2)` thật sự thay đổi số lượng nên kết quả đúng là 2, không phải 4.

### Hai đường đời khác nhau: nguồn trong bộ nhớ và nguồn I/O

Spliterator trên một bản sao `ArrayList` không giữ tệp hoặc kết nối, nên bản thân nó không đòi hỏi `try-with-resources`. Với nguồn tệp, database hoặc cursor, **phải có hợp đồng sở hữu tài nguyên riêng**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

static long demDongCoChu(
        Path file,
        int batchSize) throws IOException {

    try (Stream<String> lines =
            Files.lines(file, StandardCharsets.UTF_8)) {

        Iterator<String> iterator = lines.iterator();

        return StreamSupport.stream(
                new IteratorBatchSpliterator<>(iterator, batchSize),
                false)
            .filter(s -> !s.trim().isEmpty())
            .count();
    }
}
```

Ở đây `Files.lines` tạo nguồn gắn với I/O; **khối `try` sở hữu và đóng `lines`**. Iterator chỉ được dùng khi nguồn còn mở. Ví dụ cố ý đặt `parallel = false` để không quảng bá việc đọc đĩa qua iterator như một chiến lược song song hóa mặc định.

Nếu ứng dụng cần xử lý CPU song song trên những lô đã đọc, phải đánh giá tốc độ đọc, buffering, số tác vụ, backpressure và chính sách đóng tệp; không chỉ chuyển `false` thành `true` rồi giả định an toàn và nhanh hơn.

## 11. Encounter order, `forEach` và các phép kết thúc

`ORDERED` không nói rằng nhiều thread sẽ gọi callback **theo đúng thứ tự gặp**. Nó nói rằng **nguồn có thứ tự logic** mà một số terminal operation phải tôn trọng.

Ví dụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

List<Integer> source =
    Arrays.asList(7, 3, 5, 1, 9);

List<Integer> output = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .map(n -> n * 10)
    .collect(Collectors.toList());

System.out.println(output); // [70, 30, 50, 10, 90]
```

`Collectors.toList()` giữ encounter order của ordered stream. Nhưng:

```java
StreamSupport.stream(
    BatchDemo.BatchSpliterator.snapshotOf(source, 2),
    true
).forEach(System.out::println);
```

`forEach` không hứa thứ tự in; dùng `forEachOrdered` nếu phải thực hiện hành động cuối theo thứ tự gặp:

```java
StreamSupport.stream(
    BatchDemo.BatchSpliterator.snapshotOf(source, 2),
    true
).forEachOrdered(System.out::println);
```

Khi kết quả cần là danh sách, **`collect` thường phù hợp hơn** việc tự thêm vào `ArrayList` dùng chung trong `forEach`. `forEachOrdered` có thể làm giảm mức đồng thời để tôn trọng thứ tự.

### `findFirst` khác `findAny`

```java
int first = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .filter(n -> n > 2)
    .findFirst()
    .orElse(-1); // 7

int any = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .filter(n -> n > 2)
    .findAny()
    .orElse(-1); // 7, 3, 5 hoặc 9
```

`findFirst` phải tôn trọng phần tử đầu theo encounter order; `findAny` được phép trả phần tử phù hợp bất kỳ. Vì vậy `ORDERED` có thể tạo chi phí phối hợp cho những phép toán cần kết quả đầu tiên.

## 12. Có Spliterator đúng vẫn phải có `reduce` đúng

Thiết kế `trySplit` chính xác không thể sửa một phép giảm sai về đại số. Khi các lô xử lý song song, `reduce` có thể gộp kết quả cục bộ theo nhiều cách.

Ví dụ đúng:

```java
long sum = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .mapToLong(Integer::longValue)
    .reduce(0L, Long::sum);
```

`0L` là identity của phép cộng; `Long::sum` có tính kết hợp trong ngữ nghĩa số nguyên Java (kể cả quy tắc tràn dạng hai bù của Java). Nếu nghiệp vụ không chấp nhận tràn số, vẫn cần chọn miền tính toán hoặc kiểu `BigInteger` phù hợp.

Ví dụ sai:

```java
int wrong = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2),
        true)
    .reduce(0, (a, b) -> a - b);
```

Phép trừ không kết hợp:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Vì vậy không thể dự đoán một kết quả nhất quán giữa mọi cách chia. **Đúng Spliterator** và **đúng accumulator/combiner** là hai điều kiện độc lập.

### Thu thập danh sách đúng cách

Không dùng:

```java
List<Integer> output = new ArrayList<>();

// KHÔNG NÊN: thêm vào ArrayList dùng chung từ nhiều thread.
StreamSupport.stream(
    BatchDemo.BatchSpliterator.snapshotOf(source, 2), true)
    .forEach(output::add);
```

Dùng:

```java
List<Integer> output = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(source, 2), true)
    .collect(Collectors.toList());
```

Collector có cơ chế supplier, accumulator, combiner phù hợp. Nếu muốn một `ArrayList` cụ thể, chọn `Collectors.toCollection(ArrayList::new)`.

### Chia lô không tự làm batch kết quả

`trySplit` trả từng vùng để xử lý, nhưng Stream vẫn là `Stream<T>`, **không phải `Stream<List<T>>`**. Nếu bài toán cần đầu ra là các nhóm B phần tử (để gửi API hoặc ghi batch vào cơ sở dữ liệu), cần một thuật toán/collector riêng để **gộp phần tử thành list**. Không lạm dụng `trySplit` như thao tác tạo batch nghiệp vụ; ranh giới chia có thể thay đổi theo runtime.

## 13. Hiệu năng: chọn `batchSize` như thế nào?

Không có một kích thước lô tối ưu cho mọi workload. Các yếu tố liên quan:

| Khi B rất nhỏ | Khi B rất lớn |
| --- | --- |
| Có thể tạo nhiều vùng/tác vụ hơn cần thiết | Có thể tạo quá ít phần việc để tận dụng nhiều lõi |
| Chi phí `trySplit` và điều phối tăng | Một số worker có thể chờ việc, tải lệch |
| Với nguồn Iterator, cấp phát nhiều list nhỏ | Với nguồn Iterator, mỗi lô giữ nhiều phần tử trong bộ nhớ |
| Có thể chia tải mịn hơn khi chi phí mỗi phần tử lệch nhau | Giảm overhead nếu tác vụ trên mỗi phần tử rất rẻ |

**Không đồng nhất số lô với số thread.** Runtime có thể dừng chia trước ngưỡng B vì kích thước nguồn, chiến lược lập lịch và chi phí đánh giá. Ngược lại, phiên bản Iterator có thể lấy trước các lô khiến bộ nhớ tăng nếu tốc độ đọc nhanh hơn xử lý.

### Khung thí nghiệm đề xuất

1. Xác nhận tính đúng trên dữ liệu nhỏ với B = 1, 2, 7 và B lớn hơn kích thước nguồn.
2. Xây dựng nguồn đủ lớn và xác định công việc **CPU-bound thuần** trên mỗi phần tử.
3. Thử một dải lô, ví dụ B = 64, 256, 1024, 4096, thay vì đoán một giá trị.
4. So sánh với `source.stream()`, `source.parallelStream()` sử dụng spliterator tích hợp và phiên bản tùy chỉnh.
5. Đo throughput/latency, mức dùng CPU, phân bổ bộ nhớ và tần suất GC trên máy thực tế.
6. Dùng benchmark có warm-up và nhiều vòng, ví dụ JMH; không kết luận từ một lần gọi `System.nanoTime()`.

Nếu phép tính rất nhẹ, **chi phí tạo snapshot O(N)** trong `BatchSpliterator.snapshotOf` có thể lớn hơn lợi ích chia lô. Khi nguồn là `ArrayList` sẵn có, `ArrayList.spliterator()` thường là chuẩn so sánh rất quan trọng.

**Thay đổi B không làm phép tính sai trở thành đúng.** Phép `reduce` phải thỏa identity và associativity; các lambda phải stateless/non-interfering, dù chọn lô lớn hay nhỏ.

## 14. Các lỗi thiết kế dễ bỏ sót

| Hiện tượng | Lý do | Cách khắc phục |
| --- | --- | --- |
| Một số phần tử bị xử lý hai lần | `trySplit` tạo prefix nhưng không cập nhật `index` của phần còn lại | Cắt hai đoạn không giao nhau, luôn cập nhật cursor. |
| Mất phần tử cuối | Nhầm khoảng `[index, fence)` với khoảng đóng | Dùng điều kiện `index < fence` và kiểm thử 0, 1, B, B+1 phần tử. |
| Kết quả list song song bị đảo | Tách suffix trước mà vẫn khai `ORDERED` | Trả prefix của vùng chưa duyệt. |
| `count()` cho kết quả không đúng | Khai `SIZED` sai hoặc `estimateSize` không cập nhật | Chỉ khai khi biết kích thước chính xác, kiểm tra sau split/advance. |
| `SUBSIZED` báo sai trên nguồn động | Kích thước các split không ổn định | Bỏ cờ hoặc dùng snapshot/range cố định. |
| `NONNULL` nhưng input có `null` | Khai đặc tính không đúng | Không khai `NONNULL` nếu không kiểm chứng. |
| `batchSize = 0` làm vòng lặp không tiến | Không xác thực tham số | Ném `IllegalArgumentException`. |
| Iterator source bị đọc cạnh tranh | Cùng instance được nhiều thread gọi trực tiếp | Quản lý quyền sở hữu, chỉ tách rồi xử lý các split độc lập. |
| Dùng `List.get(i)` trên `LinkedList` khổng lồ | Truy cập theo chỉ số có thể O(n) | Sao chép thành `ArrayList` hoặc dùng nguồn Iterator phù hợp. |
| Nguồn quá lớn làm hết RAM | Sao chép cả nguồn hoặc tạo nhiều lô chờ | Bounded batching và kiểm soát tài nguyên/backpressure. |
| `findFirst` trên dữ liệu Iterator đọc quá nhiều | `trySplit` lấy trước một lô | Cân nhắc kích thước lô và chiến lược short-circuit. |
| `forEach` ghi sai thứ tự | Thứ tự thực thi không phải encounter order | Dùng `collect`, hoặc `forEachOrdered` khi thích hợp. |
| `reduce` trên phép trừ cho kết quả khác | Phép toán không kết hợp | Đổi thuật toán gộp, không sửa bằng cách đổi batch. |
| Nguồn I/O không được đóng | Spliterator không tự quản lý lifecycle | Dùng `try-with-resources` ở tầng sở hữu stream/connection. |
| Chạy song song nhưng chậm hơn | Overhead split/merge hoặc thao tác quá nhẹ | Benchmark, xem lại B và nguồn; cân nhắc spliterator JDK. |

## 15. Bài tập thực hành theo cấp độ

### Bài 1 — Vẽ các lô

Với nguồn `[1, 2, ..., 10]`, `batchSize = 4` và thuật toán:

```java
if (remaining <= batchSize) return null;
int prefixSize = Math.min(batchSize, remaining / 2);
```

Hãy mô phỏng các lần tách liên tiếp trên **phần còn lại**, ghi kích thước mọi đoạn cuối. Các đoạn đó có bị trùng vị trí không?

### Bài 2 — Sửa lỗi thiếu cập nhật con trỏ

Đoạn sai:

```java
public Spliterator<T> trySplit() {
    int remaining = fence - index;
    if (remaining <= batchSize) return null;

    int cut = index + Math.min(batchSize, remaining / 2);
    return new BatchSpliterator<>(
        data, index, cut, batchSize
    );
}
```

Vì sao mã này có thể làm lặp phần tử? Dòng nào còn thiếu?

### Bài 3 — Khi nào dùng `SIZED`?

Một Spliterator đọc bản ghi từ `Iterator<T>` không biết tổng số phần tử. `estimateSize()` trả `Long.MAX_VALUE`. Có được khai `SIZED | SUBSIZED` như phiên bản dùng snapshot `ArrayList` không? Giải thích.

### Bài 4 — Đảm bảo tính đúng khi song song

Đề xuất tối thiểu năm ca thử giúp phát hiện lỗi cắt lô: nguồn rỗng, một phần tử, đúng B phần tử, B+1 phần tử, có giá trị trùng. Nêu cách dùng `List.equals` thay vì `Set.equals` để phát hiện trùng vị trí.

### Bài 5 — Chuyển đổi pipeline

Sử dụng `BatchDemo.BatchSpliterator.snapshotOf(data, 8)` với danh sách số nguyên có thứ tự. Viết pipeline song song để lọc số dương, nhân 10 và thu thành `List<Integer>` đúng thứ tự gặp. Giải thích vì sao không dùng `parallel().forEach(result::add)`.

### Bài 6 — Đọc lô từ nguồn I/O

Nguồn là `Files.lines(path)`. Ai có trách nhiệm đóng tài nguyên? Nếu dùng `IteratorBatchSpliterator` để đọc trước B dòng mỗi lần tách, `limit(10)` có chắc chắn chỉ đọc 10 dòng của tệp không? Vì sao?

### Bài 7 — Đo hiệu năng

Nêu lý do vì sao phiên bản snapshot trên `ArrayList` có thể chậm hơn spliterator của JDK dù cả hai trả kết quả đúng. Thiết kế thử nghiệm với ít nhất ba kích thước B và hai mức chi phí tính toán cho mỗi phần tử.

## 16. Gợi ý và đáp án tham khảo

**Bài 1.** Lúc đầu còn 10 phần tử, `prefixSize = min(4,5) = 4`, nên tách `[1,2,3,4]`. Còn sáu phần tử `[5,6,7,8,9,10]`, tách thêm `min(4,3) = 3` là `[5,6,7]`. Đoạn cuối `[8,9,10]` có ba phần tử, không tách thêm vì `remaining = 3 <= 4`. Kích thước các lô là `[4,3,3]`; không trùng vị trí.

**Bài 2.** Mã thiếu:

```java
BatchSpliterator<T> prefix =
    new BatchSpliterator<>(data, index, cut, batchSize);

index = cut; // Quan trọng: loại prefix khỏi phần còn lại.
return prefix;
```

Nếu không tăng `index` của instance hiện tại, phần gốc vẫn sở hữu cả đoạn đã tách, có thể phát lại những phần tử mà prefix đã xử lý.

**Bài 3.** Không. Với iterator không biết số phần tử, `Long.MAX_VALUE` chỉ là ước lượng, không phải kích thước chính xác. Spliterator gốc không được khai `SIZED` / `SUBSIZED`. Một `ArrayList` con tạo từ B phần tử cụ thể có thể có những đặc tính kích thước riêng vì bản thân list con đã biết số phần tử.

**Bài 4.** Các ca nên bao gồm `[]`, `[7]`, `[1..B]`, `[1..B+1]`, và danh sách như `[1,1,2,2,3]`. Sau khi tách hết, tiêu thụ các phần prefix theo đúng thứ tự trước phần còn lại; so sánh toàn bộ list kết quả với list nguồn. `Set.equals` chỉ so giá trị duy nhất, không xác nhận số lần xuất hiện và vị trí.

**Bài 5.**

```java
List<Integer> output = StreamSupport.stream(
        BatchDemo.BatchSpliterator.snapshotOf(data, 8),
        true)
    .filter(n -> n > 0)
    .map(n -> n * 10)
    .collect(Collectors.toList());
```

`Collectors.toList()` thu theo encounter order của nguồn ordered. `forEach` trong parallel stream không giữ thứ tự thực thi; việc thêm đồng thời vào `ArrayList` ngoài pipeline còn không an toàn.

**Bài 6.** Tầng tạo `Files.lines` phải đóng stream, thường bằng `try-with-resources`. `IteratorBatchSpliterator.trySplit` có thể đọc trước một lô B dòng; runtime còn có thể tách thêm các lô trước khi `limit(10)` kết thúc. Vì vậy không được cam kết chỉ có 10 dòng được đọc từ tệp, ngay cả khi đầu ra có tối đa 10 dòng.

**Bài 7.** Snapshot tạo bản sao toàn `List`, tốn O(N) bộ nhớ/thời gian; `trySplit` có thể tạo nhiều object và lô quá nhỏ phát sinh overhead. Có thể thử B = 64, 512, 4096 với hai phép tính: (a) phép nhân cộng rất nhẹ và (b) thuật toán CPU-bound độc lập tương đối nặng. So sánh với `source.stream()`, `source.parallelStream()` theo cùng dữ liệu và kết quả; dùng benchmark có warm-up, đo nhiều vòng và theo dõi cấp phát/GC.

## 17. Checklist triển khai trong dự án thực tế

Trước khi đưa một spliterator tùy chỉnh vào hệ thống, kiểm tra:

- [ ] Nguồn có **ordered** thực sự không? Nếu không, không tuyên bố `ORDERED`.
- [ ] `trySplit` trả phần **không giao nhau** với phần hiện tại, không làm rơi phần tử.
- [ ] Nếu có `ORDERED`, phần tách là tiền tố của phần còn lại.
- [ ] `tryAdvance` chỉ phát đúng một phần tử, `forEachRemaining` phát hết phần chưa duyệt.
- [ ] `estimateSize` giảm phù hợp sau khi tiêu thụ và tách; `SIZED` / `SUBSIZED` chỉ khai khi đúng.
- [ ] Không khai `NONNULL` / `DISTINCT` / `SORTED` / `CONCURRENT` nếu không đáp ứng hợp đồng.
- [ ] `batchSize > 0` được kiểm tra và kích thước cuối phù hợp chính sách lô.
- [ ] Nguồn không bị sửa cấu trúc trong quá trình duyệt; nếu dùng snapshot, hiểu giới hạn **sao chép nông**.
- [ ] Không tự gọi cùng spliterator từ nhiều thread; mỗi split có quyền sở hữu trạng thái duyệt riêng.
- [ ] Lambda trong pipeline **stateless**, **non-interfering**.
- [ ] `reduce` và collector dùng identity, accumulator, combiner hợp lệ.
- [ ] Kiểm tra nguồn rỗng, một phần tử, B, B+1, dữ liệu trùng, và kết quả tuần tự/song song.
- [ ] Nếu nguồn gắn với I/O, đã định rõ ai **đóng tài nguyên** và điều gì xảy ra khi short-circuit.
- [ ] Đã đo tốc độ/bộ nhớ so với spliterator có sẵn của Java; không tối ưu theo suy đoán.

## 18. Tổng kết

Tư duy thiết kế một Spliterator chia theo lô có thể tóm tắt:

```text
Nguồn dữ liệu có thứ tự
          |
    BatchSpliterator
          |
        trySplit
      /     |     \
    lô A   lô B   lô C    (vùng chỉ số không giao nhau)
      \     |     /
  map / filter / process
          |
  reduce / collect
          |
       Kết quả
```

Mấu chốt không nằm ở việc “chia được nhiều lô” mà ở **hợp đồng của nguồn và phép ghép kết quả**:

- `trySplit` phải chia đúng, trả tiền tố nếu nguồn ordered và giữ các phần không chồng lấn.
- `estimateSize` cùng `SIZED` / `SUBSIZED` phải chính xác khi được khai báo.
- `StreamSupport.stream(spliterator, true)` cho phép runtime xử lý song song, **không hứa** số tác vụ hoặc tốc độ tăng.
- `reduce` và `collect` phải có phép gộp hợp lệ; Spliterator đúng không cứu được các lambda có trạng thái dùng chung.
- Nguồn Iterator/I/O đòi hỏi cân nhắc **đọc trước**, kích thước không biết trước và quyền sở hữu tài nguyên.
- Đo hiệu năng sau khi đã xác minh đủ **độ phủ phần tử, thứ tự, dữ liệu biên và tính đúng**.

Hoàn thành dự án này, bạn có thể tiếp cận các nguồn dữ liệu lớn bằng Java Stream API có hệ thống hơn: biết khi nào nên dùng spliterator có sẵn, khi nào cần viết bộ chia lô riêng và cách đánh giá an toàn, tài nguyên cũng như hiệu năng trước khi xử lý song song.
