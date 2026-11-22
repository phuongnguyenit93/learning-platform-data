# Spliterator.trySplit và chiến lược chia nguồn trong Java Stream

## 1. Mục tiêu bài học

`Spliterator<T>` là giao diện vừa **duyệt** vừa **phân hoạch** nguồn dữ liệu trong Java Stream API. Đây là API ra đời từ Java 8 và vẫn đang được sử dụng. Trong khi `Iterator` chủ yếu lấy phần tử kế tiếp, `Spliterator` bổ sung khả năng tách phần dữ liệu chưa được tiêu thụ thành một `Spliterator` khác bằng `trySplit()`. Khả năng phân hoạch đó là một nền tảng để xử lý song song.

Bài này tập trung trực tiếp vào `trySplit` và **cách chọn chiến lược chia nguồn**. Kết thúc bài, bạn cần hiểu:

1. `trySplit()` trả về gì, thay đổi spliterator ban đầu như thế nào, khi nào trả `null`.
2. Vì sao `ORDERED` buộc nhánh được tách là một **strict prefix**, còn với nguồn không có thứ tự gặp thì không có yêu cầu prefix.
3. Cách bảo đảm **không mất, không lặp phần tử**, các phần tách không giao nhau, và ước lượng kích thước hợp lệ.
4. Khi nào chia đôi theo chỉ số hiệu quả; khi nào cần chia theo batch, theo node/subtree hoặc không nên chia.
5. Vai trò của `SIZED`, `SUBSIZED`, `estimateSize()` và `characteristics()` khi phân hoạch.
6. Tạo một `Spliterator.OfInt` tùy biến đúng hợp đồng, dùng cùng `StreamSupport.intStream` ở chế độ tuần tự và song song.
7. Kiểm thử trường hợp rỗng, một phần tử, chia nhiều tầng, dữ liệu lớn, và tránh những lỗi thường gặp khi triển khai.

**Phiên bản:** Các giao diện Spliterator/StreamSupport và phương thức `trySplit` vẫn là API hiện hành. Chương trình đầy đủ dùng **Java 17+** để có `List.of` và `Stream.toList()`, không sử dụng API đã lỗi thời.

## 2. Spliterator và ba thao tác cốt lõi

Với `Spliterator<T>`, các phương thức chính để duyệt và tách là:

| Phương thức | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `boolean tryAdvance(Consumer<? super T> action)` | Tiêu thụ tối đa một phần tử còn lại, gọi `action`, trả `true` nếu có phần tử | `false` nghĩa là đã hết |
| `void forEachRemaining(Consumer<? super T> action)` | Tiêu thụ tất cả phần tử còn lại | Với `ORDERED`, giữ encounter order |
| `Spliterator<T> trySplit()` | Tách một phần các phần tử chưa tiêu thụ sang spliterator mới | Trả spliterator mới hoặc `null` |
| `long estimateSize()` | Ước lượng số phần tử **còn lại** | Có thể chính xác, ước lượng hoặc `Long.MAX_VALUE` |
| `int characteristics()` | Báo các đặc tính của nguồn và cách duyệt | Phải trung thực, không “khai đẹp” để tối ưu |

`Spliterator.OfInt`, `OfLong` và `OfDouble` là biến thể cho primitive. Chúng có phiên bản `tryAdvance` nhận `IntConsumer`, `LongConsumer` và `DoubleConsumer` để tránh boxing không cần thiết.

**Mô hình tinh thần quan trọng:** Một Spliterator đại diện cho **phần tử chưa được tiêu thụ**, không phải một collection có thể đọc lại tùy ý. `tryAdvance`, `forEachRemaining` và `trySplit` làm thay đổi vùng công việc còn lại. Không viết code giả định cùng một Spliterator có thể được “reset”.

## 3. Hợp đồng của `trySplit()`

Ví dụ một nguồn có encounter order:

```text
Nguồn chưa duyệt: [1, 2, 3, 4, 5, 6, 7, 8]
                  └──────── Spliterator S ────────┘

Spliterator P = S.trySplit()

P (trả về)      : [1, 2, 3, 4]   // phần prefix
S (sau khi tách): [5, 6, 7, 8]   // phần còn lại

Duyệt P rồi duyệt S: [1, 2, 3, 4, 5, 6, 7, 8]
```

Nếu `trySplit()` trả non-null, **phần tử mà spliterator trả về quản lý không còn thuộc phần do spliterator gốc quản lý**. Không được để hai spliterator cùng duyệt một phần tử, cũng không được bỏ sót phần tử.

### 3.1. Những quy tắc mà API bảo đảm

1. **Trả `null` là hợp lệ:** không còn phần tử, quá ít phần tử, không thể chia, chi phí chia không đáng, nguồn đặc thù, hoặc sau khi đã tiêu thụ một phần. Không có hợp đồng bắt buộc mỗi lời gọi phải tách được.
2. **`ORDERED` ⇒ strict prefix:** nếu spliterator có đặc tính `ORDERED`, nhánh trả về phải phủ phần đầu **liên tiếp theo encounter order** của vùng còn lại; spliterator gốc giữ phần phía sau.
3. **Không `ORDERED`:** có thể trả một tập phần tử khác, không nhất thiết là prefix, miễn phân hoạch đúng tập phần tử chưa duyệt.
4. **Dừng chia với nguồn hữu hạn:** gọi lặp `trySplit()` trên các phần con phải dần kết thúc với `null`; không tạo vô hạn spliterator mang cùng dữ liệu.
5. **Ước lượng kích thước:** với một lần tách non-null, kích thước ước lượng **trước tách** phải lớn hơn hoặc bằng kích thước ước lượng của từng nhánh **sau tách**. Nếu có `SUBSIZED` thì kích thước trước tách phải bằng **tổng kích thước** hai nhánh sau tách.

Lưu ý: **`trySplit()` không tự thực thi song song**. Nó chỉ tạo một phần công việc riêng. Người gọi, chẳng hạn framework Stream, quyết định có giao hai phần đó cho các tác vụ khác nhau hay không.

### 3.2. Nguồn có thứ tự và không có thứ tự

- Với `ArrayList`, mảng hoặc dải chỉ số có thứ tự, cần giữ encounter order nếu công bố `ORDERED`. Bộ chia theo chỉ số thường trả nửa đầu và giữ nửa sau.
- Với một nguồn mà thứ tự gặp không được định nghĩa, ví dụ mô hình tập hợp không thứ tự, việc tạo phân vùng theo cấu trúc nội bộ có thể hợp lệ mà không cố giữ prefix. **Không gắn `ORDERED`** khi không đáp ứng được.
- Ngay cả khi tác vụ xử lý song song, một terminal operation quan tâm thứ tự như `forEachOrdered` vẫn cần được thực hiện theo hợp đồng encounter order nếu nguồn có thứ tự.

**Đừng nhầm:** có thể chia nguồn song song mà vẫn **giữ thứ tự kết quả** khi terminal operation cam kết điều đó. Ngược lại, `forEach` trên parallel stream không cam kết thứ tự gọi action; không dùng thứ tự in log làm tiêu chí đúng/sai.

## 4. Chia nguồn cân bằng: chiến lược nửa trái / nửa phải

Khi nguồn hỗ trợ truy cập theo vị trí O(1) — chẳng hạn mảng hoặc một đoạn mảng — chiến lược đơn giản, thường hiệu quả là **chia đôi theo midpoint**.

Mỗi Spliterator giữ:

- `array`: mảng nguồn dùng chung để **đọc**, không tạo bản sao khi chia.
- `index`: chỉ số phần tử tiếp theo chưa đọc, tính từ đầu đoạn còn lại.
- `fence`: chỉ số biên cuối **không bao gồm**, cố định cho spliterator đó.

Với đoạn `[index, fence)`, tính:

```java
int lo = index;
int mid = lo + (fence - lo) / 2;
if (mid <= lo) {
    return null;
}
index = mid; // spliterator ban đầu giữ [mid, fence)
return new IntSlice(array, lo, mid); // nhánh mới giữ [lo, mid)
```

Đây là **đoạn trích** từ lớp hoàn chỉnh ở mục 8; không phải một phương thức Java độc lập.

Dùng `lo + (fence - lo)/2` thay vì `(lo + fence)/2` giúp tránh cộng hai chỉ số lớn gây overflow `int`. Với `fence - lo` là số phần tử còn lại:

- `0` hoặc `1`: `mid <= lo`, trả `null`.
- `2`: trả một phần tử, giữ một phần tử.
- `8`: trả bốn phần tử, giữ bốn phần tử.
- `9`: trả bốn phần tử, giữ năm phần tử.

Độ phức tạp của `trySplit` theo cách này là **O(1)** về thao tác phân hoạch: chỉ tạo một đối tượng mô tả đoạn, **không copy nội dung mảng**. Chi phí duyệt dữ liệu thực được phân tán sang các tác vụ sau đó.

### 4.1. Chia đệ quy

```text
[1 2 3 4 5 6 7 8]                   S
       /        \
[1 2 3 4]          [5 6 7 8]        nhánh trả về / nhánh gốc
   /   \
[1 2]  [3 4]                        tiếp tục trySplit trên nhánh trái
```

Mỗi nhánh là vùng không giao nhau. Một kế hoạch kiểm thử có thể nối theo thứ tự **prefix của prefix**, phần còn lại của prefix, rồi suffix, để kiểm chứng tất cả phần tử xuất hiện đúng một lần. Framework Stream có thể chọn thứ tự tổ chức tác vụ khác; việc phân hoạch và xử lý dữ liệu vẫn phải tuân thủ hợp đồng.

### 4.2. Vì sao không chia vô hạn đến một phần tử?

Một Spliterator có thể chia đến từng phần tử và vẫn đúng về mặt ngữ nghĩa, nhưng số tác vụ quá nhỏ gây overhead. Framework thường cân nhắc kích thước nguồn và môi trường thực thi để quyết định số lần chia. Nếu bạn tự xây thuật toán fork/join, có thể đặt **ngưỡng xử lý tuần tự** dựa trên chi phí thực tế của mỗi phần tử. Ngưỡng không có một con số đúng cho mọi ứng dụng.

Phương thức `trySplit` **được phép trả `null` sớm** vì lý do hiệu quả; tuy nhiên trả `null` quá sớm với nguồn lớn có thể làm giảm lợi ích song song. Đừng biến `trySplit` thành thao tác sao chép toàn bộ phần dữ liệu chỉ để “tách cho đều”.

## 5. `estimateSize`, `SIZED` và `SUBSIZED`

`estimateSize()` báo kích thước **chưa tiêu thụ**, không phải số phần tử ban đầu của collection. Nó giúp client quyết định khi nào chia thêm.

Ví dụ split theo midpoint:

```text
Trước split:
    S.estimateSize() = 8

Sau split:
    P.estimateSize() = 4
    S.estimateSize() = 4

Vì SUBSIZED:
    8 = 4 + 4
```

Các đặc tính liên quan:

| Đặc tính | Ý nghĩa chuẩn | Cách áp dụng trong ví dụ |
| --- | --- | --- |
| `SIZED` | Kích thước có thể xác định chính xác trong điều kiện nguồn không bị can thiệp như hợp đồng | `fence - index` chính xác cho đoạn mảng |
| `SUBSIZED` | Mọi Spliterator được tách trực tiếp/gián tiếp đều có `SIZED` và `SUBSIZED`; khi split kích thước hai nhánh cộng lại bằng kích thước trước split | Đoạn mảng luôn biết hai biên |
| Không có `SIZED` | Ước lượng có thể không chính xác hoặc là `Long.MAX_VALUE` | Iterator kích thước không biết |
| `getExactSizeIfKnown()` | Trả `estimateSize` nếu có `SIZED`; nếu không trả `-1` | Có thể kiểm tra ngay từ đầu nguồn |

**Điều kiện trung thực:** Nếu một nguồn bị sửa khi duyệt, bạn không thể tiếp tục khẳng định kích thước hoặc thứ tự theo giả định cũ. Với nguồn động mà số phần tử thật không biết chính xác, không tùy tiện gắn `SIZED` hay `SUBSIZED`.

Lưu ý: spliterator có `SIZED` ở cấp gốc **chưa chắc** `SUBSIZED` — ví dụ một cấu trúc cây có số phần tử tổng thể đã biết nhưng không biết kích thước chính xác của mỗi cây con. Chỉ gắn `SUBSIZED` khi mọi nhánh tiếp tục được chia đều có size đúng như hợp đồng.

## 6. Những đặc tính khác ảnh hưởng chiến lược chia

| Characteristic | Khi nào nên công bố | Hệ quả quan trọng |
| --- | --- | --- |
| `ORDERED` | Nguồn thực sự có encounter order | `trySplit` trả strict prefix |
| `DISTINCT` | Các phần tử được bảo đảm khác nhau theo quan hệ bằng nhau phù hợp | Không đúng chỉ vì hiện tại dữ liệu tình cờ không trùng |
| `SORTED` | Nguồn được duyệt theo thứ tự so sánh đã cam kết | Phải bảo đảm đúng comparator và điều kiện liên quan |
| `NONNULL` | Nguồn không thể có phần tử `null` | Primitive `OfInt` không chứa null |
| `IMMUTABLE` | Không thể có structural interference theo ngữ nghĩa nguồn | Không gắn chỉ vì ta **dự định** không sửa mảng |
| `CONCURRENT` | Nguồn có chính sách thay đổi đồng thời phù hợp | Không được dùng để “bật song song” một cách giả tạo |
| `SIZED` | Kích thước chính xác theo hợp đồng | Hỗ trợ lập kế hoạch |
| `SUBSIZED` | Kích thước mọi phần con chính xác, giữ đặc tính khi chia | Hỗ trợ phân hoạch có dự đoán |

Với `IntSlice` sử dụng `int[]` thông thường, những đặc tính được công bố là:

```java
return ORDERED | SIZED | SUBSIZED | NONNULL;
```

Không công bố `SORTED` vì các số trong mảng có thể không được sắp. Không công bố `DISTINCT` vì phần tử có thể trùng. Không công bố `IMMUTABLE` vì mảng Java có thể bị thay đổi. Không công bố `CONCURRENT` vì lớp này có `index` mutable, không được thiết kế để nhiều thread cùng gọi vào **một instance**.

Việc nhiều worker sử dụng **những Spliterator đã tách riêng** không có nghĩa Spliterator ban đầu thread-safe. Theo hợp đồng Java, Spliterator nhìn chung **không bắt buộc thread-safe**; code xử lý song song phải quản lý quyền sở hữu hoặc bàn giao các nhánh sao cho không sử dụng cùng một instance đồng thời.

## 7. Chọn chiến lược chia theo cấu trúc nguồn

### 7.1. Mảng, dải chỉ số và cấu trúc truy cập ngẫu nhiên

**Ưu tiên:** chia ở midpoint, tạo hai đoạn bằng chỉ số không giao nhau.

- Chi phí chia thường O(1), không copy phần tử.
- Dễ giữ encounter order bằng cách trả nửa đầu.
- Dễ biết size chính xác cho `SIZED`, `SUBSIZED`.
- Phù hợp khi khối lượng tính toán giữa các phần tử tương đối đồng đều.

Ví dụ nguồn là `int[]`. **Trong ứng dụng thông thường, ưu tiên `Arrays.spliterator(array)` hoặc `Arrays.stream(array).parallel()` đã có sẵn**. Tự triển khai chỉ khi phải kiểm soát đặc thù về nguồn, giới hạn đoạn hay phép duyệt.

### 7.2. Collection có iterator hoặc danh sách liên kết

Nếu muốn chia một iterator không có truy cập ngẫu nhiên, mỗi lần “nhảy” đến midpoint có thể phải duyệt nhiều phần tử. **Không mặc nhiên sao chép toàn bộ collection sang mảng** trong mỗi lần `trySplit`, vì chi phí phân hoạch có thể lấn át việc xử lý.

Một chiến lược phù hợp là **tách theo batch**:

1. Lấy một lượng hữu hạn phần tử từ iterator vào buffer mới.
2. Trả spliterator duyệt buffer đó.
3. Giữ iterator cùng các phần tử chưa duyệt trong spliterator gốc.
4. Điều chỉnh batch size theo khối lượng dữ liệu và overhead phân phối tác vụ, dừng khi không còn phần tử.

Thư viện JDK đã có các tiện ích như `Spliterators.spliteratorUnknownSize(iterator, characteristics)` hay `Spliterators.AbstractSpliterator` / `AbstractIntSpliterator`, hỗ trợ trường hợp khó phân hoạch. Các helper này có thể cho phép mức độ song song **hạn chế**, không bảo đảm chia đôi hoàn hảo.

Với iterator không biết kích thước, **không gắn `SIZED`** để ép giả vờ chính xác. Chỉ gắn các đặc tính có thể chứng minh từ nguồn.

### 7.3. Cây, trie hoặc cấu trúc có các subtree

Một lựa chọn là tách theo node hoặc subtree độc lập:

- Nếu mỗi subtree có đủ công việc và dễ tách, có thể chia rất nhanh.
- Nếu cây lệch, tách “một nhánh trái / phần còn lại” có thể tạo khối lượng quá mất cân bằng.
- Nếu biết tổng size nhưng không biết size chính xác từng subtree, có thể có `SIZED` ở gốc mà **không có `SUBSIZED`**.
- Nếu nguồn có thứ tự duyệt cụ thể (ví dụ inorder), phải bảo đảm phần được trả về là prefix phù hợp; không được trao ngẫu nhiên một subtree nằm giữa rồi vẫn công bố `ORDERED`.

### 7.4. I/O, cursor, dữ liệu từ mạng hoặc nguồn khó chia

Nếu một cursor chỉ có thể đọc tuần tự, việc tách có thể rất đắt hoặc không khả thi. Một Spliterator **không chia được** vẫn có thể dùng để duyệt đúng. Trả `null` thay vì tạo nhiều đối tượng cùng giữ một cursor gây tranh chấp.

Đừng mặc định rằng `parallelStream()` sẽ giúp tăng tốc cho nguồn I/O này. Nếu mỗi tác vụ cần kết nối/cursor riêng, thiết kế phân hoạch phải tính đến tài nguyên, backpressure, xử lý lỗi và chính sách đóng tài nguyên. Stream API không tự giải quyết những yêu cầu đó.

### 7.5. Công việc của mỗi phần tử không đồng đều

Chia đôi số phần tử chưa chắc chia đôi **thời gian tính toán**. Nếu phần tử có chi phí khác biệt lớn, hãy cân nhắc:

- Bóc các phần việc lớn theo thông tin ước lượng thực tế nếu đã có.
- Thiết kế nhánh nhỏ hơn ở phần có chi phí cao.
- Giảm overhead của split/merge; đo throughput và độ lệch tải thay vì chỉ đo số phần tử.

Tuy nhiên đừng phá hợp đồng `ORDERED` hoặc `SUBSIZED` để tối ưu. Nếu không thể giữ đặc tính đã khai báo, phải sửa chiến lược hay bỏ đặc tính không còn đúng.

## 8. Chương trình Java 17+ hoàn chỉnh: `Spliterator.OfInt` chia đôi theo chỉ số

Chương trình sau tự triển khai `Spliterator.OfInt` trên `int[]` để minh họa đầy đủ hợp đồng `trySplit`. Mảng được giả định **không bị sửa trong quá trình duyệt**. Trong sản phẩm thực tế, `Arrays.spliterator` đã hỗ trợ kịch bản mảng thông thường nên không cần viết lớp này chỉ để duyệt `int[]`.

Tạo tệp **`SplitStrategyDemo.java`**:

```java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class SplitStrategyDemo {
    static final class IntSlice implements Spliterator.OfInt {
        private final int[] array;
        private int index;
        private final int fence;

        IntSlice(int[] array, int origin, int fence) {
            this.array = Objects.requireNonNull(array);
            Objects.checkFromToIndex(origin, fence, array.length);
            this.index = origin;
            this.fence = fence;
        }

        @Override
        public OfInt trySplit() {
            int lo = index;
            int mid = lo + (fence - lo) / 2;
            if (mid <= lo) {
                return null;
            }
            index = mid;
            return new IntSlice(array, lo, mid);
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (index >= fence) {
                return false;
            }
            action.accept(array[index++]);
            return true;
        }

        @Override
        public void forEachRemaining(IntConsumer action) {
            Objects.requireNonNull(action);
            while (index < fence) {
                action.accept(array[index++]);
            }
        }

        @Override
        public long estimateSize() {
            return fence - index;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | NONNULL;
        }
    }

    static void require(boolean okay, String reason) {
        if (!okay) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) {
        int[] data = IntStream.rangeClosed(1, 8).toArray();
        IntSlice root = new IntSlice(data, 0, data.length);

        long originalSize = root.getExactSizeIfKnown();
        Spliterator.OfInt prefix = root.trySplit();
        require(prefix != null, "Split required for 8 elements");

        long leftSize = prefix.estimateSize();
        long rightSize = root.estimateSize();
        List<Integer> left = StreamSupport.intStream(prefix, false)
                .boxed().toList();
        List<Integer> right = StreamSupport.intStream(root, false)
                .boxed().toList();

        require(left.equals(List.of(1, 2, 3, 4)), "Ordered prefix");
        require(right.equals(List.of(5, 6, 7, 8)), "Ordered suffix");
        require(leftSize + rightSize == originalSize, "SUBSIZED sizes");

        System.out.println("sizeBefore=" + originalSize);
        System.out.println("splitSizes=" + leftSize + "+" + rightSize);
        System.out.println("prefix=" + left);
        System.out.println("suffix=" + right);

        // Chia tiếp nhánh đã tách rồi ghép các phần còn lại.
        IntSlice nested = new IntSlice(data, 0, data.length);
        Spliterator.OfInt half = nested.trySplit();
        Spliterator.OfInt quarter = half.trySplit();

        int[] merged = IntStream.concat(
                IntStream.concat(
                        StreamSupport.intStream(quarter, false),
                        StreamSupport.intStream(half, false)),
                StreamSupport.intStream(nested, false)
        ).toArray();
        require(Arrays.equals(data, merged), "Recursive coverage");
        System.out.println("recursiveCoverage=true");

        // Nguồn rỗng và một phần tử không cần chia.
        IntSlice empty = new IntSlice(new int[0], 0, 0);
        IntSlice single = new IntSlice(new int[]{42}, 0, 1);
        boolean emptyNoSplit = empty.trySplit() == null;
        boolean oneNoSplit = single.trySplit() == null;

        int[] holder = new int[1];
        boolean consumed = single.tryAdvance(
                (IntConsumer) x -> holder[0] = x);
        boolean exhausted = !single.tryAdvance(
                (IntConsumer) x -> {});

        require(emptyNoSplit && oneNoSplit && consumed
                && holder[0] == 42 && exhausted, "Empty/single");

        System.out.println("emptyNoSplit=" + emptyNoSplit);
        System.out.println("singleNoSplit=" + oneNoSplit);
        System.out.println("singleAdvance=" + holder[0]
                + ", exhausted=" + exhausted);

        // Dùng nguồn mới cho từng terminal operation.
        int[] large = IntStream.rangeClosed(1, 10_000).toArray();
        long seq = StreamSupport.intStream(
                new IntSlice(large, 0, large.length), false)
                .asLongStream().sum();
        long par = StreamSupport.intStream(
                new IntSlice(large, 0, large.length), true)
                .asLongStream().sum();

        require(seq == 50_005_000L && par == seq,
                "Sequential/parallel sum");
        System.out.println("sequentialSum=" + seq);
        System.out.println("parallelSum=" + par);

        IntSlice inspect = new IntSlice(data, 0, data.length);
        boolean validCharacteristics = inspect.hasCharacteristics(
                Spliterator.ORDERED | Spliterator.SIZED
                | Spliterator.SUBSIZED | Spliterator.NONNULL);
        require(validCharacteristics, "Characteristics");
        System.out.println("validCharacteristics="
                + validCharacteristics);
        System.out.println("ALL TESTS PASSED");
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac SplitStrategyDemo.java
java SplitStrategyDemo
```

**Stdout mong đợi chính xác:**

```text
sizeBefore=8
splitSizes=4+4
prefix=[1, 2, 3, 4]
suffix=[5, 6, 7, 8]
recursiveCoverage=true
emptyNoSplit=true
singleNoSplit=true
singleAdvance=42, exhausted=true
sequentialSum=50005000
parallelSum=50005000
validCharacteristics=true
ALL TESTS PASSED
```

### 8.1. Phân tích kiểu trả về và phần dữ liệu

- `IntSlice implements Spliterator.OfInt`: mỗi phần tử đầu vào là primitive `int`, dùng `IntConsumer` cho `tryAdvance`/`forEachRemaining`.
- `new IntSlice(array, lo, mid)`: nhánh trả về quản lý **[lo, mid)**.
- Sau `index = mid`, nhánh gốc chỉ còn **[mid, fence)**.
- `prefix.estimateSize() + root.estimateSize() == originalSize`: kích thước được bảo toàn cho `SUBSIZED`.
- Hai nhánh dùng chung mảng **chỉ đọc**, nhưng quản lý hai dải chỉ số không giao nhau; vì mảng có thể sửa, ví dụ không công bố `IMMUTABLE`.
- `Objects.checkFromToIndex` kiểm tra phạm vi khởi tạo hợp lệ, tránh đọc vượt giới hạn.

### 8.2. Tại sao có `forEachRemaining` riêng?

`Spliterator.OfInt` có triển khai mặc định của `forEachRemaining` dựa vào `tryAdvance`, nhưng một lớp duyệt mảng có thể viết vòng `while` để duyệt trực tiếp hiệu quả hơn. Cả hai phải tuân thủ cùng quy tắc **tiêu thụ phần còn lại đúng một lần và theo thứ tự** nếu đã báo `ORDERED`.

`tryAdvance` gọi `action.accept(array[index++])` khi còn dữ liệu; với nguồn hết thì trả `false`. `Objects.requireNonNull(action)` giúp kiểm tra đối số null. Không cần tự tạo một `Stream` mới bên trong `tryAdvance`.

### 8.3. Tại sao phải có hai `IntSlice` mới khi so sánh tuần tự/song song?

Một đối tượng Spliterator bị **tiêu thụ** bởi terminal operation. Khi đã truyền nó vào `StreamSupport.intStream(...).sum()`, không được sử dụng lại object để tính tổng lần thứ hai.

Vì vậy chương trình tạo:

```java
new IntSlice(large, 0, large.length)
```

cho cả hai pipeline. Chúng đọc cùng mảng nguồn không bị sửa, nhưng giữ trạng thái duyệt riêng.

### 8.4. Chế độ song song không bảo đảm nhiều thread

Tham số `true` của `StreamSupport.intStream(spliterator, true)` đánh dấu stream có thể thực thi song song. Nó **không bảo đảm** từng nhánh chạy ở thread riêng, không bảo đảm hiệu năng nhanh hơn và không bảo đảm một số lần gọi `trySplit` cụ thể. Kết quả `sum` vẫn phải đúng theo hợp đồng toán học và miền kiểu dữ liệu.

Trong ví dụ, `asLongStream()` được dùng để tổng không phụ thuộc miền `int` nếu sau này nâng số phần tử. Với dữ liệu 1..10.000, kết quả `50_005_000` nằm trong cả `int` và `long`, nhưng `long` cho hợp đồng kết quả rộng hơn.

## 9. Tách bằng cách gọi tay so với để Stream tự quyết định

**Gọi tay** thường để kiểm thử/triển khai thuật toán tùy biến:

```java
Spliterator.OfInt first = new IntSlice(data, 0, data.length);
Spliterator.OfInt prefix = first.trySplit();

if (prefix != null) {
    prefix.forEachRemaining((IntConsumer) System.out::println);
}
first.forEachRemaining((IntConsumer) System.out::println);
```

Đây là **đoạn minh họa trong ngữ cảnh** đã khai báo `IntSlice`, `data` và các import. Với `ORDERED`, đoạn này sẽ in theo encounter order. Nhưng việc gọi `forEachRemaining` hai lần như trên vẫn **chạy tuần tự**, chưa tạo tác vụ song song nào.

**Dùng Stream**:

```java
long sum = StreamSupport.intStream(
        new IntSlice(data, 0, data.length), true)
        .asLongStream()
        .sum();
```

Đây là đoạn minh họa với `IntSlice`, `data` đã có. Framework Stream chịu trách nhiệm quyết định có gọi `trySplit` nhiều lần, chia việc cho ai, và kết hợp kết quả thế nào. Cần bảo đảm `trySplit` đúng hợp đồng; **không** cần tự gọi `trySplit` rồi truyền từng phần vào các `parallelStream()` khác nhau.

Với nguồn phổ biến, **ưu tiên Stream sẵn có**:

```java
long builtIn = Arrays.stream(data).parallel()
        .asLongStream().sum();
```

Một custom Spliterator chỉ có ý nghĩa khi nguồn riêng hoặc chiến lược đọc riêng cần được tích hợp vào Stream API.

## 10. Kiểm thử chiến lược chia nguồn đúng cách

Bộ test tốt không chỉ hỏi “chạy được `parallel()` hay không”, mà xác minh hợp đồng phân hoạch độc lập với lịch luồng.

| Test | Kỳ vọng | Lỗi phát hiện |
| --- | --- | --- |
| Nguồn rỗng | `estimateSize()==0`; `trySplit()==null`; không phần tử nào được phát | Split ảo hoặc trả data rác |
| Một phần tử | `trySplit()==null`; `tryAdvance` lần đầu true, lần tiếp false | Đọc quá biên, lặp phần tử |
| Hai phần tử | Tách được hai nhánh không giao nhau nếu chiến lược cho phép | Off-by-one |
| Số chẵn (8) | Nhánh prefix 4, nhánh gốc 4 | Midpoint/biên sai |
| Số lẻ (9) | Prefix 4, còn lại 5 theo ví dụ | Một phần tử mất hoặc lặp |
| Chia đệ quy | Duyệt mọi nhánh ghép theo encounter order tái tạo dữ liệu ban đầu | Trùng/bỏ phần tử giữa nhiều cấp |
| Kích thước có `SUBSIZED` | `before == prefixSize + remainderSize` | Báo size sai |
| Traversal một nhánh | `tryAdvance` giảm `estimateSize` chính xác với ví dụ `SIZED` | Trạng thái index không cập nhật |
| Nguồn lớn và parallel | Kết quả đúng bằng oracle độc lập | Lỗi phân vùng chỉ lộ khi chia nhiều |
| Dữ liệu lặp/âm | Không bỏ qua, không nhân đôi, không âm thầm đổi thứ tự | Nhầm giá trị với chỉ số |

### 10.1. So sánh theo tập dữ liệu gốc

Với nguồn có thứ tự, sau một lần split, duyệt **nhánh trả về rồi nhánh gốc** phải khớp dữ liệu chưa tiêu thụ trước split:

```text
concat(traverse(returnedPrefix), traverse(originalRemainder))
    == originalRemainingSequence
```

Với nguồn **unordered**, không thể lấy thứ tự để so. Thay vào đó kiểm chứng **multiset** (giá trị cùng số lần xuất hiện), không chỉ `Set` vì `Set` làm mất thông tin dữ liệu trùng.

### 10.2. Đừng chỉ so kết quả tuần tự với song song

Nếu cả hai pipeline đều bỏ sót cùng một phần tử do `tryAdvance` viết sai, so `seq == parallel` vẫn có thể pass. Nên tính **expected độc lập** từ dữ liệu biết trước. Trong ví dụ, công thức tổng `1 + ... + 10_000 = 10_000 × 10_001 / 2 = 50_005_000` là oracle.

### 10.3. Test không nên phụ thuộc chi tiết thực thi

Đừng assert số thread, thứ tự in log từ `parallel().forEach`, số lần framework gọi `trySplit`, hoặc một ngưỡng phân hoạch cụ thể do framework chọn. Những điều này không phải hợp đồng chức năng công khai và có thể thay đổi giữa các JDK/thiết bị.

Nên kiểm thử **một số trường hợp rỗng, nhỏ, lệch, lớn**, và với custom Spliterator nên có test duyệt/tách **trực tiếp**, không phụ thuộc parallel stream kích hoạt đúng nhánh như mong muốn.

## 11. Những lỗi thường gặp khi tự cài `trySplit`

### 11.1. Trả chính `this` thay vì spliterator con

**Sai:** `return this;` từ `trySplit()` mà không phân chia dữ liệu độc lập. Khi nhánh gốc và nhánh trả về là cùng một instance, các tác vụ có thể cùng thay đổi `index`, gây trùng, mất dữ liệu hoặc hành vi không xác định.

**Đúng:** trả một object mới quản lý dải con riêng, cập nhật trạng thái dải còn lại của object gốc.

### 11.2. Không thu hẹp phạm vi ban đầu

**Sai:** tạo `new IntSlice(array, lo, mid)` nhưng quên `index = mid` ở nhánh gốc. Nhánh gốc vẫn đọc cả mảng hoặc cả đoạn cũ, khiến phần prefix bị duyệt hai lần.

**Đúng:** ghi cập nhật ranh giới của nhánh gốc **trước khi trả** con và bảo đảm hai đoạn không giao nhau.

### 11.3. Trả nửa sau dù có `ORDERED`

**Sai:** với `ORDERED`, trả `[5,6,7,8]` từ một nguồn `[1..8]` và để nhánh gốc giữ `[1,2,3,4]`. `trySplit()` phải trả **strict prefix**, tức nửa đầu trong ví dụ.

**Đúng:** trả `[lo, mid)`, nhánh gốc giữ `[mid, fence)`.

### 11.4. Chia sai midpoint hoặc không có điều kiện dừng

Tính sai midpoint có thể tạo nhánh dài bằng nguồn ban đầu, làm `trySplit()` không tiến triển. Với nguồn hữu hạn, phải có điểm dừng. Kiểm tra `mid <= lo` hoặc số phần tử còn lại trước khi tạo con.

Đối với `int[]`, công thức `lo + (fence-lo)/2` dễ kiểm tra và không bị overflow do cộng hai biên lớn.

### 11.5. Khai báo `SUBSIZED` khi size con không chính xác

`SUBSIZED` đòi hỏi mọi spliterator con được tách đều duy trì size và đặc tính tương ứng. Nếu chỉ biết số phần tử ước lượng, không được giả báo `SUBSIZED`. Framework có thể tối ưu dựa trên khai báo này và kết quả có thể không đúng hợp đồng khi số lượng thực khác ước lượng.

### 11.6. Cho nhiều thread thao tác cùng một instance

Một spliterator thường không thread-safe. Sau khi `trySplit`, hai nhánh có trạng thái riêng; mỗi nhánh có thể được một tác vụ nhận. **Không** chia sẻ chính object có `index` mutable cho hai thread cùng gọi `tryAdvance`/`trySplit` nếu không có thiết kế đồng bộ phù hợp.

### 11.7. Thay đổi nguồn khi đang duyệt

Mảng trong `IntSlice` có thể bị code khác sửa nội dung khi Stream đang duyệt. Ví dụ cố ý **không công bố `IMMUTABLE`**. Hãy xử lý nguồn như dữ liệu ổn định hoặc tạo snapshot khi nghiệp vụ cần, không phụ thuộc hành vi khi có sửa đổi đồng thời.

### 11.8. Tách bằng cách copy quá nhiều dữ liệu

Tạo `new ArrayList<>(...)` từ toàn bộ phần còn lại mỗi lần split có thể đẩy chi phí phân hoạch lên rất cao. Với nguồn chỉ số, chỉ tạo **view bằng hai biên**. Với iterator không có random access, batch nhỏ có chủ đích thường hợp lý hơn sao chép toàn bộ liên tục.

### 11.9. Nhầm “được tách” với “chắc chắn chạy nhanh hơn”

Một bộ chia cân bằng không bảo đảm nhanh hơn do các yếu tố như độ nhỏ của phép toán, scheduling overhead, locality, cache contention, blocking I/O và chi phí kết hợp kết quả. Chỉ dùng parallel khi workload và benchmark cho thấy lợi ích.

### 11.10. Tái sử dụng spliterator đã tiêu thụ

Các thao tác terminal trên Stream đã dùng hết Spliterator. Không truyền cùng instance vào hai Stream hoặc cố tính lại từ đầu. Tạo Spliterator mới từ nguồn gốc, hoặc đưa một `Supplier<Spliterator<T>>` tạo instance mới nếu làm test nhiều lượt.

## 12. Quy trình quyết định chiến lược `trySplit`

<escape>**Bước 1 — Xác định nguồn.**</escape> Mảng hoặc đoạn chỉ số? Iterator? Cây? Stream dữ liệu bên ngoài? Một số nguồn đã có spliterator chuẩn của JDK; tránh viết lại nếu không cần.

<escape>**Bước 2 — Xác định thứ tự.**</escape> Nếu có encounter order, `trySplit` phải tách prefix. Nếu không có, khai báo và xử lý unordered trung thực.

<escape>**Bước 3 — Xác định size.**</escape> Có biết size thực của từng phần không? Có thì `SIZED`/`SUBSIZED` theo điều kiện phù hợp. Không thì dùng estimate và bỏ đặc tính không chứng minh được.

<escape>**Bước 4 — Chọn điểm chia.**</escape> Midpoint với truy cập theo chỉ số; batch với iterator; subtree với cây; trả `null` nếu nguồn không thể tách hiệu quả.

<escape>**Bước 5 — Kiểm tra tính độc lập.**</escape> Hai spliterator con không quản lý chung phần tử chưa đọc; không dùng một state cursor chung không đồng bộ.

<escape>**Bước 6 — Đo chi phí thực.**</escape> Chia quá nhỏ tốn overhead; chia lệch có thể làm một worker thành nút cổ chai. Tối ưu bằng benchmark có kiểm soát.

<escape>**Bước 7 — Kiểm thử hợp đồng.**</escape> Empty, singleton, chẵn/lẻ, chia đệ quy, size, thứ tự, nguồn lớn, seq/parallel cùng oracle độc lập.

## 13. Bài tập tự luyện và đáp án

**Bài 1.** Spliterator `ORDERED` bao phủ `[10,20,30,40,50]`. `trySplit` có thể trả `[40,50]` và để nhánh gốc giữ `[10,20,30]` không?

**Đáp án:** **Không.** Nhánh trả về phải là **strict prefix** của phần chưa duyệt. Một phương án đúng là trả `[10,20]` và giữ `[30,40,50]`.

**Bài 2.** Nguồn mảng dài 9 phần tử dùng `mid = lo + (fence-lo)/2`, khi chưa tiêu thụ phần tử nào có size hai nhánh bằng bao nhiêu?

**Đáp án:** `4` và `5`.

**Bài 3.** Nếu `SIZED` có mặt nhưng `SUBSIZED` không có, có chắc mọi nhánh con đều biết size chính xác không?

**Đáp án:** **Không.** `SIZED` của gốc không tự bảo đảm các nhánh con có kích thước chính xác. `SUBSIZED` là lời hứa áp dụng cho cả cây tách.

**Bài 4.** `trySplit()` trả `null` có nghĩa nguồn đã hết mọi phần tử?

**Đáp án:** **Không nhất thiết.** Nó có thể chỉ báo rằng không nên hoặc không thể tách; Spliterator vẫn có thể còn phần tử để duyệt.

**Bài 5.** Có thể cho một `IntSlice` đọc mảng chạy song song dù `IntSlice` không có `CONCURRENT` không?

**Đáp án:** **Có**, nếu framework được phép chia ra các **instance riêng** và nguồn không bị sửa trong khi xử lý; `CONCURRENT` không phải điều kiện để một Spliterator hỗ trợ song song.

**Bài 6.** Khi dùng `StreamSupport.intStream(new IntSlice(data, 0, data.length), true)`, muốn biết Java sẽ tạo chính xác bao nhiêu thread thì nên assert số thread nào?

**Đáp án:** **Không assert số lượng cụ thể.** Đó không phải hợp đồng chức năng; kiểm thử dữ liệu và kết quả.

**Bài 7.** Một `trySplit` trả non-null cho dữ liệu hữu hạn nhưng hai nhánh có tổng size không bằng size trước split trong khi đã báo `SUBSIZED`. Có hợp lệ không?

**Đáp án:** **Không.** Nó vi phạm hợp đồng `SUBSIZED`.

## 14. Checklist ngắn trước khi đưa vào dự án

- [ ] Nếu JDK đã có `Arrays.spliterator` hoặc `collection.spliterator()` phù hợp, ưu tiên sử dụng.
- [ ] `trySplit` trả một phần **không chồng lấn**, không mất phần tử, hữu hạn thì có điểm dừng.
- [ ] Nếu `ORDERED`, phần được trả về là **prefix**, không phải suffix tùy tiện.
- [ ] `estimateSize` phản ánh phần tử **còn lại**; `SIZED`/`SUBSIZED` công bố đúng mức bảo đảm.
- [ ] Các characteristics khác (`SORTED`, `DISTINCT`, `IMMUTABLE`, `CONCURRENT`) không được khai báo khi thiếu chứng cứ.
- [ ] Vùng dữ liệu/tác vụ sau chia là độc lập về quyền tiêu thụ; không chia sẻ state duyệt mutable giữa thread.
- [ ] Chọn chiến lược theo loại nguồn: chia đôi O(1), batching, subtree hoặc không chia.
- [ ] Không sửa dữ liệu nguồn giữa lúc duyệt; mỗi Stream/Spliterator được tiêu thụ một lần.
- [ ] Test trực tiếp split/traversal và test song song với expected độc lập.
- [ ] Chỉ tuyên bố cải thiện hiệu năng khi đã đo đúng workload.

## Tài liệu tham khảo chính thức còn áp dụng

- [Oracle JDK 25 — Spliterator: trySplit, ORDERED, SIZED, SUBSIZED, ước lượng và threading](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html)
- [Oracle JDK 25 — Spliterator.OfInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.OfInt.html)
- [Oracle JDK 25 — Spliterators.AbstractIntSpliterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterators.AbstractIntSpliterator.html)
- [Oracle JDK 25 — Spliterators utility, spliteratorUnknownSize và spliterator cho mảng](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterators.html)
- [Oracle JDK 25 — StreamSupport.intStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/StreamSupport.html)
