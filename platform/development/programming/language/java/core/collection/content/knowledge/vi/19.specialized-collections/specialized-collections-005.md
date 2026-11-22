# BitSet và khác biệt với Set<Integer>

## 1. Từ tập chỉ số đến một dãy bit

Giả sử một chương trình có các vị trí đánh số từ 0 trở lên và cần ghi nhận vị trí nào đang được chọn. Nếu các vị trí 2 và 5 được chọn, có thể lưu hai số trong `Set<Integer>`. Một cách biểu diễn khác là đặt bit tại chỉ số 2 và 5 thành true, còn các bit khác là false.

`BitSet` là một dãy bit có thể mở rộng khi cần. Mỗi chỉ số nguyên không âm tương ứng một trạng thái boolean. Khi dùng như tập hợp, ta quy ước:

```text
bit i = true  → chỉ số i thuộc tập đang biểu diễn
bit i = false → chỉ số i không thuộc tập đang biểu diễn

Chỉ số: 0 1 2 3 4 5 6 7
Bit:    0 0 1 0 0 1 0 0
Tập:    {2, 5}
```

Số 0 trong hàng Bit nghĩa là false, không có nghĩa phần tử số 0 đang được chọn. Muốn số 0 thuộc tập, phải đặt chính bit ở chỉ số 0 thành true.

BitSet phù hợp với các mặt nạ đánh dấu, tập chỉ số, các nhóm điều kiện có cùng miền đánh số và phép giao/hợp trên nhiều cờ. Tuy nhiên, nó **không triển khai Set hoặc Collection**. Tên có chữ Set không làm nó có cùng kiểu API và hợp đồng với `Set<Integer>`.

Bài học sẽ đi từ cách đánh dấu từng chỉ số, phân biệt ba đại lượng kích thước, đến phép toán tập hợp, phạm vi và chuyển đổi. Các chương trình đầy đủ dùng Java 17 trở lên.

## 2. BitSet và Set<Integer> biểu diễn điều gì?

| Đặc điểm | BitSet | Set<Integer> |
|---|---|---|
| Cách hiểu dữ liệu | Trạng thái bit ở các chỉ số | Tập các đối tượng Integer |
| Miền số | Chỉ số nguyên không âm | Có thể chứa số âm, tùy cách triển khai và ràng buộc ứng dụng |
| Null | Không có phần tử null; chỉ số là int | Có nhận null hay không tùy cách triển khai; HashSet cho phép |
| Đánh dấu có mặt | `set(i)` | `add(i)` |
| Kiểm tra có mặt | `get(i)` | `contains(i)` |
| Bỏ đánh dấu | `clear(i)` | `remove(i)` |
| Đếm phần tử được chọn | `cardinality()` | `size()` |
| Phép toán tập hợp | Có and/or/xor/andNot chuyên cho bit | Dùng thao tác collection hoặc thuật toán phù hợp |
| Thứ tự duyệt | Chỉ số tăng dần qua stream/nextSetBit | Phụ thuộc cách triển khai Set |
| Kiểu Collection/Set | Không | Có |

BitSet không lưu đối tượng Integer riêng cho từng chỉ số được bật. Đó là một lý do nó có thể gọn với miền chỉ số dày. Nhưng cấu trúc đóng gói bit còn phụ thuộc vị trí các chỉ số, không chỉ số lượng phần tử. Hai bit bật rất xa nhau có ý nghĩa chi phí khác với hai bit bật ở gần đầu.

`set`, `clear` và các phép logic sửa trạng thái không trả boolean “tập có thay đổi không” như một số thao tác Set. Chúng có kiểu trả về void. Không thể thay máy móc `set.add(i)` bằng một lời gọi rồi vẫn dùng kết quả boolean của nó.

Đối chiếu hợp đồng chính tại [BitSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html) và [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

## 3. Khởi tạo và thao tác từng bit

### 3.1. Mọi bit ban đầu là false

`new BitSet()` tạo trạng thái chưa có bit true. `new BitSet(128)` yêu cầu không gian ban đầu đủ biểu diễn các chỉ số 0 đến 127, nhưng vẫn chưa bật bit nào.

Số 128 không phải số phần tử đang có và cũng không phải một giới hạn cứng. Có thể đặt bit 130 về sau; BitSet sẽ mở rộng khi cần. Nếu ứng dụng chỉ cho phép 128 vị trí, chính ứng dụng phải giữ giới hạn và kiểm tra chỉ số.

### 3.2. set, clear, flip và get

| Lời gọi | Hiệu ứng |
|---|---|
| `set(i)` | Đặt bit i thành true |
| `set(i, false)` | Đặt bit i thành false |
| `clear(i)` | Đặt bit i thành false |
| `flip(i)` | Đảo false thành true hoặc true thành false |
| `get(i)` | Đọc boolean ở bit i |
| `clear()` | Đặt mọi bit thành false |

Đặt một bit đã true thành true lần nữa không tạo bản sao phần tử. BitSet không đếm số lần một chỉ số được đưa vào. Nếu cần tần suất xuất hiện của từng số, cần cấu trúc lưu số đếm thay vì chỉ một bit có/không.

`get(i)` với chỉ số không âm chưa được đặt trả false, kể cả khi i nằm sau bit true cao nhất hiện tại. Đó không phải dấu hiệu lỗi chỉ số theo miền ứng dụng. Chỉ số âm bị từ chối bằng `IndexOutOfBoundsException`.

## 4. cardinality, length và size không thay thế cho nhau

### 4.1. Ba câu hỏi khác nhau

| Phương thức | Câu hỏi được trả lời | Ví dụ khi bật 2, 5, 100 |
|---|---|---|
| `cardinality()` | Có bao nhiêu bit true? | 3 |
| `length()` | Độ dài logic tới sau bit true cao nhất là bao nhiêu? | 101 |
| `size()` | Bao nhiêu bit không gian hiện được cấu trúc dùng để biểu diễn? | Phụ thuộc phần không gian và cách triển khai |

`length()` bằng chỉ số bit true cao nhất cộng một; nếu không có bit true thì bằng 0. Nó không phải số phần tử được chọn. Xóa bit cao nhất có thể làm length giảm dù chỉ vừa bỏ một phần tử.

`size()` nói về không gian biểu diễn hiện tại, khác với Set.size. Tài liệu nêu đại lượng này liên quan cách triển khai và có thể thay đổi theo cách triển khai. Không dùng nó để đếm phần tử hoặc làm số vị trí nghiệp vụ.

Ví dụ một BitSet tạo với không gian ban đầu cho 128 vị trí nhưng chưa bật bit nào có cardinality 0 và length 0. Ngược lại, chỉ bật bit 100 đã làm length thành 101 nhưng cardinality vẫn là một.

### 4.2. Độ dài miền ứng dụng phải được lưu riêng

Nếu có đúng N ghế, N trang hoặc N cờ, giá trị N vẫn có ý nghĩa ngay cả khi mọi bit đều false. Không thể khôi phục N chỉ từ length vì length khi đó bằng 0.

Số vị trí hợp lệ cũng không tự được xác định bằng size. Cách biểu diễn có thể dành không gian khác với N, và constructor không cấm mở rộng. Phần ví dụ phân bổ vị trí cuối bài sẽ giữ trường limit riêng.

## 5. Chương trình 1: đánh dấu, đọc, đếm và mở rộng

Lưu chương trình đầy đủ vào `BitSetBasicsDemo.java`:

```java
import java.util.BitSet;

public class BitSetBasicsDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet(128);
        System.out.println("initialCardinality=" + bits.cardinality());
        System.out.println("initialLength=" + bits.length());
        System.out.println("capacityAtLeastRequested=" + (bits.size() >= 128));
        bits.set(2);
        bits.set(5);
        bits.set(100);
        bits.set(5);
        System.out.println("selected=" + bits);
        System.out.println("cardinality=" + bits.cardinality());
        System.out.println("length=" + bits.length());
        System.out.println("get3=" + bits.get(3));
        System.out.println("get500=" + bits.get(500));
        bits.clear(100);
        System.out.println("afterClear100=" + bits);
        System.out.println("lengthAfterClear=" + bits.length());
        bits.flip(5);
        bits.flip(7);
        bits.set(130);
        System.out.println("afterFlipAndGrow=" + bits);
        System.out.println("grownLength=" + bits.length());
        bits.clear();
        System.out.println("empty=" + bits.isEmpty());
        System.out.println("emptyLength=" + bits.length());
        System.out.println("emptyCardinality=" + bits.cardinality());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BitSetBasicsDemo.java
java BitSetBasicsDemo
```

Stdout:

```text
initialCardinality=0
initialLength=0
capacityAtLeastRequested=true
selected={2, 5, 100}
cardinality=3
length=101
get3=false
get500=false
afterClear100={2, 5}
lengthAfterClear=6
afterFlipAndGrow={2, 7, 130}
grownLength=131
empty=true
emptyLength=0
emptyCardinality=0
```

### 5.1. Không gian ban đầu không làm tăng số bit true

`initialCardinality=0` và `initialLength=0` xác nhận chưa có chỉ số được chọn. Ví dụ chỉ kiểm tra không gian ban đầu đủ yêu cầu, không chốt một con số size cụ thể làm hợp đồng có thể dựa vào cho mọi cách triển khai.

Bật 2, 5, 100 rồi bật 5 lần nữa vẫn chỉ có `{2, 5, 100}`. Cardinality là 3, length là 101. `get3=false` và `get500=false` đều là những lần đọc hợp lệ ở chỉ số không âm chưa được bật.

### 5.2. Xóa bit cao nhất và mở rộng trở lại

Xóa 100 để lại `{2, 5}`, nên length còn 6, không phải 100 hoặc 2. Đảo bit 5 tắt nó, đảo bit 7 bật nó, rồi đặt 130 làm kết quả `{2, 7, 130}`.

`grownLength=131` cho thấy chỉ số 130 hợp lệ dù constructor ban đầu nhận 128. Nếu 128 là giới hạn của một yêu cầu thực tế, cần chặn trước thao tác set thay vì dựa vào constructor.

Cuối cùng clear làm trạng thái rỗng: isEmpty true, length 0 và cardinality 0. Không nên suy ra từ đó rằng JVM đã lập tức thu hồi toàn bộ phần không gian mà đối tượng từng dùng.

## 6. Phép toán tập hợp trên BitSet

### 6.1. Mỗi chỉ số là một phép tính boolean

Với hai BitSet A và B cùng dùng một hệ đánh số:

| Phép toán | API trên A | Bit i thuộc kết quả khi nào? |
|---|---|---|
| Giao | `A.and(B)` | A và B đều có i |
| Hợp | `A.or(B)` | Ít nhất một trong A, B có i |
| Hiệu đối xứng | `A.xor(B)` | Chính xác một trong hai có i |
| Hiệu A trừ B | `A.andNot(B)` | A có i nhưng B không có i |
| Chỉ hỏi có giao không | `A.intersects(B)` | Trả true nếu có ít nhất một chỉ số cùng được bật |

XOR không phải phép trừ tập hợp: các phần tử chỉ có trong B vẫn xuất hiện trong XOR, nhưng không xuất hiện trong A trừ B. AND NOT không đối xứng; đổi chỗ hai toán hạng có thể cho kết quả khác.

### 6.2. Các phép and/or/xor/andNot sửa chính đối tượng nhận lời gọi

`A.or(B)` sửa A; nó không tạo một BitSet kết quả mới rồi trả ra. B không vì là đối số mà bị đổi theo trong trường hợp A và B là các đối tượng khác nhau.

Nếu cần giữ nguyên hai nguồn, hãy tạo bản sao A trước rồi áp dụng phép logic lên bản sao. Một phép gán tham chiếu `result = A` không tạo bản sao, nên thao tác trên result vẫn có thể làm A thay đổi.

`intersects` phù hợp khi chỉ cần biết có phần tử chung, không cần lưu cả kết quả giao. Nó trả boolean và không sửa hai tập.

## 7. Chương trình 2: giao, hợp, XOR và hiệu

Lưu vào `BitSetAlgebraDemo.java`. Hàm of trong chương trình là hàm hỗ trợ tự viết để đặt các chỉ số; không phải phương thức tĩnh BitSet.of của API Java 17.

```java
import java.util.BitSet;

public class BitSetAlgebraDemo {
    private static BitSet of(int... indices) {
        BitSet result = new BitSet();
        for (int index : indices) {
            result.set(index);
        }
        return result;
    }

    public static void main(String[] args) {
        BitSet a = of(1, 3, 5, 9);
        BitSet b = of(3, 4, 9);
        BitSet intersection = (BitSet) a.clone();
        intersection.and(b);
        BitSet union = (BitSet) a.clone();
        union.or(b);
        BitSet symmetricDifference = (BitSet) a.clone();
        symmetricDifference.xor(b);
        BitSet difference = (BitSet) a.clone();
        difference.andNot(b);

        System.out.println("intersection=" + intersection);
        System.out.println("union=" + union);
        System.out.println("symmetricDifference=" + symmetricDifference);
        System.out.println("difference=" + difference);
        System.out.println("intersects=" + a.intersects(b));
        System.out.println("originalA=" + a);
        System.out.println("originalB=" + b);
        a.or(b);
        System.out.println("aAfterDirectOr=" + a);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BitSetAlgebraDemo.java
java BitSetAlgebraDemo
```

Stdout:

```text
intersection={3, 9}
union={1, 3, 4, 5, 9}
symmetricDifference={1, 4, 5}
difference={1, 5}
intersects=true
originalA={1, 3, 5, 9}
originalB={3, 4, 9}
aAfterDirectOr={1, 3, 4, 5, 9}
```

### 7.1. Đối chiếu từng kết quả

Với A={1,3,5,9}, B={3,4,9}, giao là `{3, 9}`, hợp là `{1, 3, 4, 5, 9}`, XOR là `{1, 4, 5}`, còn A trừ B là `{1, 5}`. Phần tử 4 giúp thấy rõ khác biệt giữa XOR và hiệu.

Vì các phép trước được thực hiện trên clone, originalA và originalB vẫn nguyên. Lần `a.or(b)` cuối cùng tác động trực tiếp vào a, nên a trở thành hợp. Đây là bằng chứng cần theo dõi đối tượng nhận lời gọi khi dùng các phương thức trả void.

Các tập muốn kết hợp phải thống nhất ý nghĩa của chỉ số: bit 5 phải cùng đại diện một đối tượng hoặc một thuộc tính ở cả hai nguồn. Nếu một nguồn dùng số thứ tự trang còn nguồn kia dùng mã người dùng, phép AND vẫn chạy nhưng kết quả không có ý nghĩa nghiệp vụ.

## 8. Thao tác một khoảng chỉ số

### 8.1. Đầu có bao gồm, cuối không bao gồm

Các overload nhận `fromIndex, toIndex` dùng khoảng nửa mở `[fromIndex, toIndex)`:

- `set(2, 8)` bật 2, 3, 4, 5, 6, 7.
- `clear(4, 6)` tắt 4 và 5.
- `flip(6, 9)` đảo 6, 7, 8.

Chỉ số toIndex không nằm trong khoảng. Muốn xử lý các vị trí 0 đến N-1 thì dùng cận cuối N. Việc dùng khoảng nửa mở giúp độ dài khoảng được tính bằng toIndex-fromIndex.

Khoảng có hai cận bằng nhau là khoảng rỗng và không chứa bit cần thay đổi. Cận âm hoặc fromIndex lớn hơn toIndex bị từ chối bằng `IndexOutOfBoundsException`.

Constructor nhận số bit ban đầu âm có hợp đồng lỗi riêng: `NegativeArraySizeException`. Không nhầm nó với lỗi truy cập chỉ số âm của get/set.

### 8.2. get(from, to) trả một bản mới và đổi gốc chỉ số

`get(from, to)` không phải view liên kết với BitSet nguồn. Nó trả một BitSet mới chứa các bit trong khoảng, với vị trí from của nguồn được đặt thành chỉ số 0 của kết quả.

Ví dụ nguồn bật 2, 3, 8; lấy khoảng `[2,9)` thì kết quả bật 0, 1, 6. Công thức đối chiếu là chỉ số mới = chỉ số gốc - fromIndex.

Xóa bit 0 trên kết quả không xóa bit 2 trên nguồn. Nếu cần giữ nguyên hệ đánh số ban đầu, không được dùng get(range) rồi giả định các số in ra vẫn là các số gốc.

## 9. Chương trình 3: khoảng, bản sao và phép bằng nhau

Lưu chương trình đầy đủ vào `BitSetRangeCopyDemo.java`:

```java
import java.util.BitSet;

public class BitSetRangeCopyDemo {
    public static void main(String[] args) {
        BitSet bits = new BitSet();
        bits.set(2, 8);
        System.out.println("setRange=" + bits);
        bits.clear(4, 6);
        System.out.println("clearRange=" + bits);
        bits.flip(6, 9);
        System.out.println("flipRange=" + bits);

        BitSet slice = bits.get(2, 9);
        System.out.println("slice=" + slice);
        slice.clear(0);
        System.out.println("sliceAfterClear=" + slice);
        System.out.println("originalBit2=" + bits.get(2));

        BitSet copy = (BitSet) bits.clone();
        copy.clear(3);
        System.out.println("copyAfterClear=" + copy);
        System.out.println("originalBit3=" + bits.get(3));

        BitSet small = new BitSet(1);
        BitSet large = new BitSet(1024);
        small.set(6);
        large.set(6);
        System.out.println("equalDespiteCapacity=" + small.equals(large));
        System.out.println("equalHashCodes=" + (small.hashCode() == large.hashCode()));
        try {
            bits.get(-1);
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("negativeIndex=IndexOutOfBoundsException");
        }
        try {
            bits.set(9, 3);
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("reversedRange=IndexOutOfBoundsException");
        }
        try {
            new BitSet(-1);
            throw new AssertionError("Expected NegativeArraySizeException");
        } catch (NegativeArraySizeException expected) {
            System.out.println("negativeInitialSize=NegativeArraySizeException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BitSetRangeCopyDemo.java
java BitSetRangeCopyDemo
```

Stdout:

```text
setRange={2, 3, 4, 5, 6, 7}
clearRange={2, 3, 6, 7}
flipRange={2, 3, 8}
slice={0, 1, 6}
sliceAfterClear={1, 6}
originalBit2=true
copyAfterClear={2, 8}
originalBit3=true
equalDespiteCapacity=true
equalHashCodes=true
negativeIndex=IndexOutOfBoundsException
reversedRange=IndexOutOfBoundsException
negativeInitialSize=NegativeArraySizeException
```

### 9.1. Theo dõi ba thao tác khoảng

Sau `set(2,8)`, các bit 2 đến 7 được bật. `clear(4,6)` bỏ 4 và 5, còn `{2, 3, 6, 7}`. `flip(6,9)` tắt 6, 7 và bật 8, nên nguồn thành `{2, 3, 8}`.

`slice={0, 1, 6}` thể hiện việc dịch gốc chỉ số khi lấy đoạn từ 2 đến trước 9. Xóa 0 của slice vẫn để `originalBit2=true`.

### 9.2. Clone giữ nguyên chỉ số nhưng tách trạng thái bit

`clone()` tạo BitSet mới có cùng các bit true, giữ nguyên hệ đánh số. Xóa 3 trên clone để lại `{2, 8}` trong bản sao, trong khi `originalBit3=true` xác nhận nguồn không đổi.

Đây là khác biệt với phép gán một biến tham chiếu thứ hai tới cùng BitSet. Một tham chiếu khác không làm trạng thái bit được nhân bản.

### 9.3. Equals xét bit true, không xét phần không gian dự trữ

small và large được tạo với kích thước ban đầu khác nhau, nhưng cùng chỉ bật bit 6. `equalDespiteCapacity=true` và `equalHashCodes=true` xác nhận nội dung bit quyết định phép bằng nhau và mã băm.

Không có số lượng bit false ở đuôi được ghi thành một độ dài nghiệp vụ riêng trong phép bằng nhau. Hai cấu hình ứng dụng có N khác nhau nhưng cùng mẫu bit true có thể cần được phân biệt bằng một lớp chứa cả N và BitSet, thay vì dùng riêng BitSet.equals.

BitSet có thể thay đổi, và hashCode phụ thuộc các bit true. Không sửa nội dung một BitSet đang được dùng làm khóa trong cấu trúc băm hoặc làm phần tử của một HashSet nếu việc đó làm thay đổi mã băm và quan hệ bằng nhau mà cấu trúc đang dựa vào.

### 9.4. Các lỗi đầu vào có chủ đích

Ba ngoại lệ được bắt trong chương trình kiểm tra ba lỗi: chỉ số âm, khoảng đảo cận và kích thước ban đầu âm. Mỗi trường hợp in đúng loại lỗi đã được đối chiếu.

Việc chỉ số chưa được bật trả false khác với việc chỉ số âm không hợp lệ. Đó là lý do `get500` ở chương trình 1 chạy bình thường, còn `get(-1)` ở đây ném lỗi.

## 10. Duyệt các chỉ số đang được bật

### 10.1. nextSetBit bỏ qua các bit false

`nextSetBit(from)` tìm bit true đầu tiên ở vị trí từ from trở đi, có bao gồm from. Nếu không còn bit true, nó trả -1.

Muốn duyệt tiếp sau chỉ số i, lần tìm sau bắt đầu ở i+1. Nếu vẫn tìm từ i, có thể gặp lại chính bit đang true và không tiến lên được.

Mẫu vòng lặp trong chương trình tiếp theo có chặn i bằng `Integer.MAX_VALUE` trước khi tính i+1, tránh tràn số ở mốc lớn nhất. Đây cũng là điểm được nêu trong ví dụ duyệt của API BitSet. Không cần tạo một BitSet khổng lồ để chạy các dữ liệu nhỏ của bài.

### 10.2. stream trả chỉ số int, không trả các boolean

`bits.stream()` cho một IntStream chứa các chỉ số bit true theo thứ tự tăng dần. Với `{1,7,11}`, mảng từ stream là `[1,7,11]`, không phải một mảng gồm true/false ở từng vị trí.

Khi thu lại vào `Set<Integer>`, các chỉ số int được đóng hộp thành Integer theo cơ chế Java. BitSet không vì có stream mà trở thành một Collection nhận trực tiếp ở mọi API cần Set.

BitSet stream gắn với nguồn khi bắt đầu thao tác kết thúc. Tài liệu quy định kết quả không xác định nếu BitSet bị thay đổi trong thao tác đó. Khi cần một nguồn ổn định, phải bảo đảm điều kiện truy cập hoặc tạo bản sao trong điều kiện phù hợp trước khi duyệt.

## 11. Chương trình 4: chuyển giữa BitSet và Set<Integer>

Lưu vào `BitSetIntegerSetDemo.java`. Chương trình dùng TreeSet khi cần in thứ tự tăng dần xác định; không dựa vào thứ tự của một Set bất kỳ.

```java
import java.util.Arrays;
import java.util.BitSet;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeSet;

public class BitSetIntegerSetDemo {
    public static void main(String[] args) {
        Set<Integer> original = new TreeSet<>(Set.of(1, 7, 11));
        BitSet bits = new BitSet();
        for (int index : original) {
            bits.set(index);
        }
        System.out.println("bits=" + bits);
        System.out.println("streamIndices=" + Arrays.toString(bits.stream().toArray()));
        StringJoiner visited = new StringJoiner(", ");
        for (int index = bits.nextSetBit(0);
                index >= 0;
                index = bits.nextSetBit(index + 1)) {
            visited.add(Integer.toString(index));
            if (index == Integer.MAX_VALUE) {
                break;
            }
        }
        System.out.println("nextSetBitIndices=" + visited);
        Set<Integer> restored = new TreeSet<>();
        bits.stream().forEach(restored::add);
        System.out.println("restored=" + restored);
        System.out.println("sameMembers=" + restored.equals(original));
        System.out.println("bitSetEqualsSet=" + bits.equals(original));
        System.out.println("setEqualsBitSet=" + original.equals(bits));

        Set<Integer> signed = new TreeSet<>(Set.of(-1, 1));
        System.out.println("setHasNegative=" + signed.contains(-1));
        try {
            bits.get(-1);
            throw new AssertionError("Expected IndexOutOfBoundsException");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("negativeBitLookup=IndexOutOfBoundsException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BitSetIntegerSetDemo.java
java BitSetIntegerSetDemo
```

Stdout:

```text
bits={1, 7, 11}
streamIndices=[1, 7, 11]
nextSetBitIndices=1, 7, 11
restored=[1, 7, 11]
sameMembers=true
bitSetEqualsSet=false
setEqualsBitSet=false
setHasNegative=true
negativeBitLookup=IndexOutOfBoundsException
```

### 11.1. Giữ cùng tập phần tử trong miền không âm

Vòng lặp set từng chỉ số tạo BitSet `{1, 7, 11}`. Stream và vòng nextSetBit đều duyệt 1, 7, 11. Khi thu lại thành một TreeSet, `sameMembers=true` xác nhận tập Integer khôi phục có cùng các thành viên với tập nguồn.

Phép chuyển này dựa trên điều kiện đầu vào là các số nguyên không âm. Với một Set tổng quát, cần chọn rõ cách xử lý số âm và null trước khi chuyển: từ chối, ánh xạ lại qua một hệ chỉ số riêng, hoặc chọn cấu trúc khác. Không âm thầm bỏ những phần tử mà BitSet không biểu diễn trực tiếp.

### 11.2. Cùng ý nghĩa tập hợp không đồng nghĩa equals giữa hai kiểu

`bitSetEqualsSet=false` và `setEqualsBitSet=false` là đúng hợp đồng. BitSet.equals yêu cầu đối tượng khác cũng là BitSet với cùng các bit true; Set.equals yêu cầu một Set với cùng phần tử.

Không dùng phép equals trực tiếp giữa hai kiểu để kiểm tra chuyển đổi. Hãy so hai BitSet cùng cách biểu diễn, hoặc chuyển về hai Set rồi so các thành viên như chương trình đã làm.

### 11.3. Set có thể giữ số âm, BitSet không có chỉ số âm

Set trong phần cuối chứa -1 và 1 hợp lệ. BitSet.get(-1) lại ném `IndexOutOfBoundsException`. Điều này thể hiện khác biệt miền dữ liệu, không phải một cách tra cứu tương đương chỉ khác tên phương thức.

Set là interface; từng cách triển khai có thêm chính sách khác nhau về null và thứ tự. Chẳng hạn [HashSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) cho phép phần tử null, còn BitSet không có một vị trí đặc biệt nào để biểu diễn “phần tử null”.

## 12. Khi nào biểu diễn bit có lợi?

### 12.1. Miền chỉ số dày và có chung hệ đánh số

Nếu các định danh đã nằm trong khoảng 0 đến U-1 và nhiều vị trí trong khoảng có thể được dùng, một bit cho mỗi vị trí là biểu diễn tự nhiên. Các phép logic có thể xử lý các khối bit thay vì phải thao tác từng đối tượng Integer.

Trong OpenJDK, BitSet đóng gói các bit trong các khối long 64 bit; có thể đối chiếu [mã nguồn BitSet của OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/BitSet.java). Đây là giải thích triển khai cho khả năng xử lý theo khối, không phải cam kết rằng mọi phương thức đều có thời gian hằng số.

Các phép như đếm bit, duyệt hoặc kết hợp nhiều khối bit vẫn có công việc theo phần dữ liệu cần xét. Không dùng trực giác “chỉ có một lời gọi and” để suy ra phép giao luôn có cùng chi phí dù miền dữ liệu nhỏ hay rất lớn.

### 12.2. Tập thưa với chỉ số rất cao có thể bất lợi

Nếu chỉ có hai phần tử 0 và một tỷ, một biểu diễn bit tuyến tính phải có khả năng đi đến vị trí rất cao đó. Phần bit thuần đã có quy mô khoảng 125 triệu byte, chưa tính các chi tiết cấu trúc và cấp phát. Cardinality bằng hai không phản ánh chi phí này.

Một HashSet chứa hai số không cần dành một bit cho mọi vị trí ở giữa hai số. Vì vậy không nên chọn BitSet chỉ từ câu “chỉ cần lưu số nguyên”. Cần xét cả chỉ số lớn nhất và mật độ dữ liệu.

Không tạo chỉ số cực lớn trong một ví dụ chỉ để xem kết quả true; phân tích miền dữ liệu đã đủ cho quyết định biểu diễn. Nếu định danh thật rất thưa, có thể giữ chúng trong Set hoặc thiết kế bảng ánh xạ sang chỉ số dày, nhưng khi đó mọi BitSet được kết hợp phải dùng cùng bảng ánh xạ.

### 12.3. Tiêu chí lựa chọn

| Nhu cầu | Điều nên ưu tiên xét |
|---|---|
| Nhiều cờ trên một khoảng chỉ số vừa phải | BitSet với miền N được mô tả rõ |
| Giao/hợp nhiều nhóm cùng hệ chỉ số | Các phép bit của BitSet |
| Một vài số nằm rất xa nhau | Chi phí theo chỉ số cao nhất; Set có thể phù hợp hơn |
| Cần số âm hoặc null như phần tử | Chính sách phần tử của Set hoặc một ánh xạ riêng |
| Cần truyền vào API nhận Collection/Set | BitSet không thay thế trực tiếp được interface đó |
| Cần đếm số lần xuất hiện của mỗi số | Một cấu trúc lưu tần suất, không chỉ một bit có/không |

Không có lựa chọn tốt nhất cho mọi dữ liệu. So sánh cần dựa trên miền chỉ số, số phần tử, các phép toán chủ yếu và yêu cầu chia sẻ trạng thái.

## 13. Miền hữu hạn và phần bù của một tập

### 13.1. Phải biết phần bù trong miền nào

Với tập được chọn `{0, 2}`, câu hỏi “những vị trí chưa được chọn là gì?” chưa có một đáp án hữu hạn nếu không biết miền hợp lệ. Trong miền `[0,3)`, phần còn lại là `{1}`. Trong miền `[0,5)`, phần còn lại là `{1,3,4}`.

`flip(0, N)` đảo đúng các bit trong miền nửa mở đó; nó không phải thao tác tạo một phần bù vô hạn. Các bit ngoài khoảng không bị thao tác này đổi. Nếu dùng một bản sao rồi flip để tạo tập vị trí rảnh, phải bảo đảm bản sao không chứa các bit true ngoài miền ứng dụng, hoặc tạo mặt nạ miền rồi thực hiện hiệu tập hợp thích hợp.

Không dùng length thay N: khi vị trí cuối cùng đang rảnh, length có thể nhỏ hơn N. Cũng không dùng size thay N vì không gian biểu diễn có thể lớn hơn miền nghiệp vụ.

### 13.2. nextClearBit không biết giới hạn tài nguyên

`nextClearBit(0)` tìm một vị trí false từ 0 trở đi. Với ba vị trí 0,1,2 đều bận, nó có thể trả 3; điều đó chỉ nói bit 3 đang false, không nói hệ thống có vị trí tài nguyên thứ tư.

Muốn phân bổ trong miền hữu hạn, cần kiểm tra chỉ số tìm thấy nhỏ hơn giới hạn rồi mới đánh dấu bận. Đây là một khác biệt thực tế giữa trạng thái bit có thể mở rộng và một danh sách tài nguyên cố định.

## 14. Chương trình 5: quản lý các vị trí từ 0 đến limit−1

Lưu chương trình đầy đủ vào `BitSetSlotsDemo.java`. Quy ước của lớp Slots là bit true nghĩa vị trí đang bận; phương thức allocate trả -1 khi không còn vị trí hợp lệ. Ví dụ được thiết kế cho một luồng.

```java
import java.util.BitSet;

public class BitSetSlotsDemo {
    static final class Slots {
        private final int limit;
        private final BitSet busy;

        Slots(int limit) {
            if (limit < 0) {
                throw new IllegalArgumentException("negative limit");
            }
            this.limit = limit;
            busy = new BitSet(limit);
        }

        int allocate() {
            int index = busy.nextClearBit(0);
            if (index >= limit) {
                return -1;
            }
            busy.set(index);
            return index;
        }

        void release(int index) {
            if (index < 0 || index >= limit) {
                throw new IndexOutOfBoundsException("slot");
            }
            busy.clear(index);
        }

        BitSet busySnapshot() {
            return (BitSet) busy.clone();
        }

        BitSet freeSnapshot() {
            BitSet free = (BitSet) busy.clone();
            free.flip(0, limit);
            return free;
        }
    }

    public static void main(String[] args) {
        Slots slots = new Slots(3);
        System.out.println("allocate=" + slots.allocate());
        System.out.println("allocate=" + slots.allocate());
        System.out.println("allocate=" + slots.allocate());
        System.out.println("fullAllocate=" + slots.allocate());
        slots.release(1);
        System.out.println("busyAfterRelease=" + slots.busySnapshot());
        System.out.println("freeAfterRelease=" + slots.freeSnapshot());
        System.out.println("allocateAgain=" + slots.allocate());
        BitSet snapshot = slots.busySnapshot();
        snapshot.clear();
        System.out.println("busyAfterSnapshotClear=" + slots.busySnapshot());
        System.out.println("zeroLimitAllocate=" + new Slots(0).allocate());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BitSetSlotsDemo.java
java BitSetSlotsDemo
```

Stdout:

```text
allocate=0
allocate=1
allocate=2
fullAllocate=-1
busyAfterRelease={0, 2}
freeAfterRelease={1}
allocateAgain=1
busyAfterSnapshotClear={0, 1, 2}
zeroLimitAllocate=-1
```

### 14.1. Giới hạn được kiểm tra trước khi bật

Ba lần cấp đầu trả 0,1,2. Lần thứ tư không tự mở rộng tài nguyên bằng cách dùng bit 3: phương thức kiểm tra `index >= limit` và trả -1.

Giải phóng 1 để busy còn `{0,2}`. Bản sao free đảo miền `[0,3)` nên cho `{1}`. Lần cấp tiếp theo lấy lại vị trí 1 và busy trở về `{0,1,2}`.

Giới hạn 0 được định nghĩa là không có vị trí hợp lệ, nên allocate trả -1 ngay cả khi nextClearBit tìm thấy chỉ số 0. Giới hạn âm bị constructor lớp bọc từ chối bằng `IllegalArgumentException` trước khi tạo BitSet.

### 14.2. Bản sao bảo vệ trạng thái nội bộ

`busySnapshot()` trả clone, không trả chính busy. Vì vậy xóa hết các bit trên biến snapshot không làm đối tượng Slots mất dấu các vị trí bận; `busyAfterSnapshotClear` vẫn là `{0,1,2}`.

`freeSnapshot()` hợp lệ vì lớp chỉ bật các bit trong miền `[0,limit)`, nên không có bit true ngoài miền để còn sót lại sau phép flip. Điều kiện đó được giữ bằng trường private và kiểm tra trong các thao tác của lớp.

Phương thức release kiểm tra chỉ số nằm trong miền rồi clear bit. Theo cách viết này, release một vị trí hợp lệ vốn đã rảnh vẫn để nó rảnh; ví dụ không đặt thêm chính sách báo lỗi cho lần giải phóng lặp. Khi dùng vào một bài toán cụ thể, hợp đồng đó phải được chọn rõ ràng.

### 14.3. Đây là quy trình nhiều bước

`allocate` gồm tìm bit rảnh rồi đánh dấu nó bận. BitSet không làm hai bước trở thành một thao tác cấp phát nguyên tử giữa nhiều luồng. Hai luồng cùng dùng mà không phối hợp có thể cùng tìm một chỉ số rảnh.

Nếu cần dùng đồng thời, phải thiết kế cách phối hợp toàn bộ trạng thái và quy trình. Các kết quả của chương trình chỉ xác nhận hành vi một luồng đang được mô tả, không tự cung cấp bảo đảm đồng thời.

## 15. Chuyển sang mảng: danh sách chỉ số khác dữ liệu bit đóng gói

Ba API có tên gần nhau nhưng trả dữ liệu khác:

| Cách lấy dữ liệu | Nội dung kết quả |
|---|---|
| `bits.stream().toArray()` | Mảng int gồm các chỉ số đang true |
| `bits.toByteArray()` | Mảng byte đóng gói các bit |
| `bits.toLongArray()` | Mảng long đóng gói các bit thành các khối |

`BitSet.valueOf(byte[])` hoặc `valueOf(long[])` đọc biểu diễn bit đóng gói, không đọc danh sách các số nguyên được chọn. Nếu muốn biểu diễn các thành viên 1,7,11, hãy set từng chỉ số hoặc chuyển theo cách ở chương trình 4; không đưa một mảng các thành viên vào valueOf rồi coi nó là phép chuyển Set.

Tài liệu BitSet mô tả quy tắc đánh số bit và biểu diễn little-endian của các mảng đóng gói. Khi cần định nghĩa một định dạng lưu/truyền, phải theo đúng hợp đồng đó, không đồng nhất dữ liệu này với một chuỗi ký tự nhị phân hay mã hóa văn bản.

Mẫu bit cũng không tự giữ số bit false ở đuôi như một độ dài miền riêng. Nếu định dạng cần ghi nhớ N vị trí hợp lệ, hãy lưu N cùng dữ liệu theo thiết kế định dạng. Khôi phục cùng các bit true không tự chứng minh đã khôi phục mọi thông tin của bài toán ứng dụng.

## 16. Trạng thái thay đổi, chia sẻ và kiểm tra

### 16.1. Chọn rõ đối tượng nào được phép thay đổi

BitSet là đối tượng có thể thay đổi. Các phương thức set/clear/flip và các phép logic có thể làm dữ liệu mà các biến tham chiếu khác cùng nhìn thấy đổi theo.

Khi một hàm chỉ muốn tính kết quả mà giữ nguồn, hãy sao chép chủ đích như chương trình đại số. Khi trả dữ liệu ra ngoài nhưng muốn bảo vệ nội bộ, dùng một bản sao phù hợp như lớp Slots. Đặt tên biến mới không tự tạo ranh giới dữ liệu.

Không có bảo đảm an toàn nhiều luồng nếu thiếu đồng bộ bên ngoài. Một phép toán logic theo khối bit hoặc một lời gọi set không được tự diễn giải thành một giao dịch đầy đủ cho nhiều thao tác ứng dụng.

### 16.2. Những kiểm tra có giá trị

- Với tập `{2,5,100}`, xác nhận cardinality 3 và length 101; không dùng size để thay một trong hai.
- Set lại cùng bit phải giữ số thành viên, còn flip hai lần cùng bit phải trở lại trạng thái cũ.
- Khoảng có nhận đầu nhưng không nhận cuối; kiểm tra thêm khoảng rỗng và khoảng đảo cận.
- get(range) phải đổi gốc chỉ số và tạo bản riêng; clone tạo bản riêng nhưng giữ chỉ số.
- Giao/hợp/XOR/hiệu phải có kết quả đúng và chỉ sửa đối tượng được chủ đích cho phép sửa.
- Chuyển qua Set rồi về BitSet phải giữ các thành viên trong miền được hỗ trợ.
- Với miền hữu hạn, mọi bit được bật phải nhỏ hơn N và nextClearBit ngoài N phải được xử lý.

Có thể dùng một Set<Integer> không âm làm dữ liệu đối chiếu cho các phép toán: giao tương ứng retainAll trên một bản sao; hợp tương ứng addAll; hiệu tương ứng removeAll. Cần tạo bản sao Set nếu muốn giữ nguồn, tương tự việc clone BitSet.

Kiểm tra cả kết quả lẫn các nguồn còn nguyên khi đó là hợp đồng. Một phép giao trả đúng nhưng vô tình sửa nguồn dùng ở bước sau vẫn là lỗi của cách sử dụng.

### 16.3. Không suy ra tốc độ từ tên cấu trúc

Biểu diễn gọn và phép toán theo khối có thể có lợi lớn khi miền chỉ số phù hợp. Tuy nhiên, việc mở rộng, sao chép, duyệt hay đếm bit đều có chi phí; số phần tử n và miền chỉ số U không phải cùng một đại lượng.

Nếu cần đánh giá hiệu năng, dùng dữ liệu đại diện cho mật độ và chỉ số cao nhất thực tế. Một phép đo trên các số 0 đến 100 không trả lời được chi phí của vài số nằm gần một tỷ.

## 17. Lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách xử lý |
|---|---|---|
| BitSet là một cách triển khai Set<Integer> | Truyền sai kiểu vào API Collection hoặc hiểu sai equals | Chuyển đổi rõ ràng khi cần Set |
| new BitSet(N) đã có N phần tử | Đếm sai ngay sau khởi tạo | Mọi bit ban đầu false; xem cardinality |
| N trong constructor là giới hạn cứng | Đặt bit vượt miền ứng dụng mà không bị chặn | Lưu và kiểm tra giới hạn riêng |
| size là số phần tử được chọn | Nhầm không gian với thành viên | Dùng cardinality |
| length là số phần tử được chọn | Sai khi có khoảng trống giữa các bit | Dùng định nghĩa bit true cao nhất cộng một |
| Clear bit cao nhất làm giảm cardinality bằng cả khoảng dài | Nhầm số vị trí với số bit true | Cardinality chỉ giảm theo bit true bị tắt |
| or/and trả một tập mới | Sửa nguồn ngoài ý định | Clone trước nếu cần kết quả riêng |
| XOR là A trừ B | Giữ thêm các phần tử chỉ thuộc B | Phân biệt xor với andNot |
| Khoảng có nhận cả hai cận | Bật hoặc tắt thừa một bit | Dùng khoảng [from,to) |
| get(from,to) giữ chỉ số gốc hoặc tạo view | Đọc sai vị trí, dự đoán sai thay đổi nguồn | Hiểu bản mới được dịch gốc chỉ số |
| nextClearBit luôn trả tài nguyên hợp lệ | Cấp vượt giới hạn N | Kiểm tra kết quả so với N |
| Hai phần tử thì BitSet chắc chắn rất nhỏ | Bỏ qua chỉ số cao nhất | Xét cả miền U và mật độ |
| valueOf(long[]) nhận danh sách thành viên | Dựng sai mẫu bit | Đó là các khối bit đóng gói |

## 18. Tự kiểm tra

### Câu hỏi

1. Bật 0 và 100 thì cardinality và length bằng bao nhiêu?
2. new BitSet(64) có cấm set(100) không?
3. Get ở một chỉ số không âm chưa được đặt trả false hay null?
4. Vì sao `bits.equals(aSet)` không phải cách kiểm tra hai tập thành viên tương đương?
5. `a.and(b)` sửa a hay trả một BitSet mới?
6. Với A={1,3}, B={3,4}, XOR và A trừ B khác nhau ở đâu?
7. Nguồn bật 5,7; get(5,8) có các bit nào?
8. Vì sao không dùng length làm tổng số ghế trong một hệ thống có N ghế?
9. Ba vị trí 0,1,2 đã bận; nextClearBit(0) tìm thấy 3 có nghĩa đã có thêm một vị trí hợp lệ không?
10. Vì sao một BitSet có cardinality nhỏ vẫn có thể tốn nhiều không gian?

### Đáp án

1. Cardinality là 2, length là 101.
2. Không; kích thước ban đầu không phải giới hạn cố định.
3. False; giá trị boolean không có trạng thái null.
4. Hai kiểu có hợp đồng equals khác nhau; BitSet không phải Set.
5. Sửa a, trả void. Clone a trước nếu cần giữ nguồn.
6. XOR là `{1,4}`, hiệu A trừ B là `{1}`.
7. Các bit 0 và 2, vì chỉ số gốc được trừ đi 5.
8. Bit cuối có thể đang false hoặc mọi bit đều false; length mô tả trạng thái đang bật chứ không giữ N.
9. Không; ứng dụng phải kiểm tra 3 có nhỏ hơn giới hạn không.
10. Biểu diễn bit tuyến tính cần tới vị trí chỉ số cao; cardinality không đo khoảng này.

## 19. Thực hành với kết quả đối chiếu

### Bài 1: ba đại lượng kích thước

Tạo BitSet với không gian ban đầu cho 256 vị trí, chỉ bật 4 và 200. Trước khi chạy, dự đoán cardinality và length, rồi xóa 200 và dự đoán lại.

Kết quả đối chiếu: ban đầu cardinality 2, length 201; sau clear(200), cardinality 1, length 5. Không chốt size bằng cardinality hoặc bằng length.

### Bài 2: phép logic giữ nguyên nguồn

Tạo A={0,2,4}, B={2,3}. Dùng clone để tính giao, hợp, XOR và A trừ B. Sau mỗi phép, xác nhận A và B vẫn là hai tập nguồn ban đầu.

Kết quả đối chiếu: giao `{2}`, hợp `{0,2,3,4}`, XOR `{0,3,4}`, hiệu `{0,4}`. Nếu A đã đổi trong quá trình, xem lại có vô tình dùng cùng tham chiếu làm kết quả hay không.

### Bài 3: lấy đoạn khác với lọc giữ nguyên chỉ số

Nguồn bật 5 và 7. Lấy get(5,8), xóa bit 0 trên kết quả rồi in cả nguồn và đoạn. Tiếp theo tạo clone nguồn, clear bit 5 trên clone rồi đối chiếu lại.

Kết quả đối chiếu: đoạn ban đầu `{0,2}`, sau xóa 0 còn `{2}`; nguồn vẫn `{5,7}`. Clone giữ hệ chỉ số gốc nên sau clear(5) còn `{7}`. Hai kiểu sao chép đều tách trạng thái nhưng có ý nghĩa chỉ số khác nhau.

### Bài 4: phần bù trong miền được chọn

Trong miền `[0,5)`, tập bận là `{0,2}`. Tạo bản sao chỉ có các bit đó rồi flip(0,5). Kiểm tra tập rảnh và tổng cardinality của bận với rảnh.

Kết quả đối chiếu: rảnh `{1,3,4}`, tổng số bit true là 5 và giao hai tập rỗng. Nếu thay miền thành `[0,3)`, kết quả rảnh chỉ còn `{1}`; miền là một phần của đề bài, không tự có trong mẫu bit.

## 20. Môi trường chạy và tài liệu

Năm chương trình trong bài độc lập, dùng cú pháp và API tương thích Java 17. Chúng đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK 24.0.2; stdout được đối chiếu từ các lần chạy đó. Mỗi lớp public được lưu trong tệp trùng tên, không phụ thuộc thư viện ngoài.

- [BitSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html): chỉ số, kích thước, phạm vi, phép logic, stream và mảng đóng gói.
- [Set — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): hợp đồng tập đối tượng và equals.
- [HashSet — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): một cách triển khai Set tổng quát và chính sách phần tử null.
- [BitSet — mã nguồn OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/BitSet.java): đối chiếu biểu diễn đóng gói theo khối long.
