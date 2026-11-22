# Java 7 — BitSet: Biểu diễn tập chỉ số và dãy cờ bằng bit

## 1. BitSet là gì và dùng khi nào?

`java.util.BitSet` biểu diễn **một dãy giá trị boolean bằng các bit**. Mỗi vị trí có **chỉ số nguyên không âm**; bit tại vị trí đó là `true` (đã bật/thuộc tập) hoặc `false` (chưa bật/không thuộc tập). Khi cần đánh dấu nhiều chỉ số, thay vì lưu từng đối tượng `Integer` trong một `Set<Integer>`, chương trình có thể dùng một `BitSet` như một **tập chỉ số**:

- Bit số 1 bật nghĩa là chỉ số 1 được chọn.
- Bit số 4 bật nghĩa là chỉ số 4 được chọn.
- Bit số 6 tắt nghĩa là chỉ số 6 không được chọn.

Nếu coi mỗi chỉ số là một **cờ trạng thái**, chương trình có thể quy ước chỉ số 0 là `CAN_READ`, chỉ số 1 là `CAN_WRITE`, chỉ số 2 là `CAN_EXPORT`. Khi đó bật/tắt một bit tương ứng với cấp hoặc bỏ một cờ. Tuy nhiên, `BitSet` tự nó **không lưu tên cờ hoặc ý nghĩa nghiệp vụ**; mapping chỉ số do ứng dụng định nghĩa.

`BitSet` là class lâu đời trong thư viện chuẩn Java, **không phải class mới ra mắt ở Java 7**. Các cách dùng hiện nay vẫn áp dụng tốt trên Java 17+. Một số API đóng gói/khôi phục bit như `toByteArray()`, `toLongArray()` và `valueOf(...)` được bổ sung từ Java 7; `stream()` xuất hiện từ Java 8. Vì thế bài học trong module Java 7 vẫn phù hợp nhưng ví dụ chính dùng JDK 17+ được hỗ trợ rộng rãi.

### 1.1. Mô hình các chỉ số

Xét tập các vị trí đang bật: **{1, 4}**. Trong nhóm tám bit thấp đầu tiên, có thể minh họa:

```text
Chỉ số: 7 6 5 4 3 2 1 0
Giá trị: 0 0 0 1 0 0 1 0
         └───────────────┘
Tương ứng: 0b00010010 = 18 (trong một byte/word thấp)
Bit đang bật: 1 và 4.
```

Đây chỉ là sơ đồ tám bit để học, **không phải giới hạn kích thước của BitSet**. Chỉ số bắt đầu từ **0**, không phải 1. Mặc định mọi bit đều `false`, và `BitSet` có thể tăng dung lượng nội bộ khi sử dụng một chỉ số cao hơn.

### 1.2. Khởi tạo

```java
import java.util.BitSet;

BitSet selected = new BitSet();       // Rỗng: chưa có bit true.
BitSet expected = new BitSet(1_000);  // Dự trù sức chứa cho chỉ số 0..999.
```

Các dòng trên là **snippet đặt trong phương thức hoặc JShell**, không phải tệp Java độc lập. Tham số `1_000` là **dung lượng dự kiến**, không có nghĩa 1.000 bit đang bật; `expected.cardinality()` vẫn bằng 0. `BitSet` không có “kích thước cố định” theo nghĩa phải đặt mọi phép truy cập trong 0..999. Nếu ứng dụng cần một miền chỉ số giới hạn, hãy **tự kiểm tra miền hợp lệ**.

## 2. Các thao tác cơ bản với một bit

| Lệnh | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `bits.set(i)` | Bật bit `i` thành `true` | Nếu đã bật thì không thay đổi trạng thái. |
| `bits.set(i, value)` | Gán bit `i` theo `boolean value` | Tiện khi cờ đến từ một điều kiện. |
| `bits.get(i)` | Đọc giá trị boolean tại `i` | Bit chưa từng bật trả `false`. |
| `bits.clear(i)` | Tắt bit `i` thành `false` | Tắt một bit vốn false không gây lỗi. |
| `bits.flip(i)` | Đảo trạng thái tại `i` | True thành false, false thành true. |
| `bits.clear()` | Tắt tất cả bit | Không cần duyệt thủ công mọi chỉ số. |
| `bits.isEmpty()` | Có phải không còn bit true? | Khác với kích thước buffer nội bộ. |

Ví dụ minh họa:

```java
BitSet flags = new BitSet();
flags.set(1);                 // {1}
flags.set(4);                 // {1, 4}
System.out.println(flags);    // {1, 4}
System.out.println(flags.get(3)); // false
flags.flip(1);                // {4}
flags.clear(4);               // {}
System.out.println(flags.isEmpty()); // true
```

Đây là **đoạn mã trong một phương thức** sau khi import `java.util.BitSet`. Cú pháp `toString()` của `BitSet` hiển thị **chỉ số những bit true** trong ngoặc nhọn, tăng dần; không hiển thị một chuỗi 0/1 dài. Lệnh `System.out.println(flags)` ở trên in ra biểu diễn tập chỉ số, không phải hex hay binary.

### 2.1. Làm việc với một khoảng chỉ số

Các overload trên khoảng dùng **đầu trái bao gồm, đầu phải không bao gồm** (*half-open interval*), giống nhiều API Java:

```java
BitSet flags = new BitSet();
flags.set(2, 6);   // Bật 2, 3, 4, 5. Không bật 6.
flags.clear(3, 5); // Tắt 3, 4. Còn 2, 5.
flags.flip(5, 7);  // Đảo 5, 6. Còn 2, 6.
System.out.println(flags); // {2, 6}
```

Đây là snippet minh họa cần đặt trong phương thức. Các khoảng như `set(from, to)`, `clear(from, to)` và `flip(from, to)` đều dùng chỉ số `from` inclusive, `to` exclusive. Nếu `from == to` thì khoảng rỗng. Nếu chỉ số âm hoặc `from > to`, các API tương ứng ném `IndexOutOfBoundsException`; đừng xem đây là trường hợp “không có gì để làm”.

### 2.2. Không nhầm `flip` với `set`

`set(i)` đưa bit về true, phù hợp để đánh dấu một tác vụ đã xong. `flip(i)` **đảo** trạng thái, phù hợp với thao tác bật/tắt theo nghĩa toggle. Nếu một message có thể bị xử lý lặp, dùng `flip(i)` có thể vô tình **hủy** trạng thái đã đánh dấu. Với lệnh idempotent như “đánh dấu đã hoàn tất”, dùng `set(i)`.

## 3. Ba phép đo: cardinality, length và size không giống nhau

Đây là phần quan trọng khi dùng `BitSet` như tập chỉ số.

| API | Ý nghĩa chính xác | Ví dụ với bit đang bật {1, 4} |
| --- | --- | --- |
| `cardinality()` | **Số lượng bit true** | `2` |
| `length()` | **Chỉ số bit true cao nhất + 1**; 0 nếu không có bit true | `5` |
| `size()` | **Số vị trí bit mà cấu trúc nội bộ đang cấp phát để biểu diễn**, phụ thuộc implementation | Không nên giả định luôn bằng 5 hoặc 2 |
| `isEmpty()` | Có phải không có bit true? | `false` |

Ví dụ:

```java
BitSet b = new BitSet();
b.set(1);
b.set(4);
System.out.println(b.cardinality()); // 2
System.out.println(b.length());      // 5
System.out.println(b.isEmpty());     // false
```

Snippet minh họa. **Không dùng `size()` để đếm số phần tử** trong tập, và không dùng `length()` để đếm số bit đã bật. Mặc dù `size()` thường phản ánh dung lượng đã cấp phát theo đơn vị từ máy, Javadoc lưu ý giá trị này phụ thuộc chi tiết triển khai; không nên đưa nó làm số phần tử cho nghiệp vụ.

Với `new BitSet(100)` mà chưa bật bit nào, `cardinality() == 0`, `length() == 0` và `isEmpty() == true`, dù có thể đã dự trù vùng lưu trữ cho 100 vị trí.

### 3.1. Ví dụ cần bảo toàn miền chỉ số

Giả sử đang lưu trạng thái của 100 câu hỏi, bit cuối cùng được bật là 12. Khi đó `length() == 13`, **không phải 100**. Nếu chỉ lưu `BitSet`, bạn không thể suy ra tổng số câu hỏi từ `length()`. Hãy lưu riêng số lượng câu hỏi 100 hoặc schema của dữ liệu.

## 4. Chương trình Java 17+ hoàn chỉnh: tập chỉ số, cờ bit và phép toán tập hợp

Tạo file **`BitSetIndexDemo.java`**:

```java
import java.util.Arrays;
import java.util.BitSet;

public class BitSetIndexDemo {
    static BitSet fromIndices(int... indices) {
        BitSet bits = new BitSet();
        for (int index : indices) {
            bits.set(index);
        }
        return bits;
    }

    public static void main(String[] args) {
        BitSet active = fromIndices(1, 3, 6);
        System.out.println("active = " + active);
        System.out.println("get(3) = " + active.get(3));
        System.out.println("get(4) = " + active.get(4));
        System.out.println("count = " + active.cardinality());
        System.out.println("length = " + active.length());

        active.flip(3);
        active.set(4);
        active.clear(6);
        System.out.println("updated = " + active);

        BitSet other = fromIndices(0, 4, 5);
        BitSet union = (BitSet) active.clone();
        union.or(other);
        System.out.println("union = " + union);

        BitSet intersection = (BitSet) active.clone();
        intersection.and(other);
        System.out.println("intersection = " + intersection);

        BitSet difference = (BitSet) active.clone();
        difference.andNot(other);
        System.out.println("difference = " + difference);

        BitSet symmetricDifference = (BitSet) active.clone();
        symmetricDifference.xor(other);
        System.out.println("xor = " + symmetricDifference);

        System.out.println("indices = " + Arrays.toString(active.stream().toArray()));
        System.out.println("nextSetBit(2) = " + active.nextSetBit(2));
        System.out.println("nextClearBit(0) = " + active.nextClearBit(0));
        System.out.println("slice [2, 6) = " + active.get(2, 6));
        System.out.println("packed longs = " + Arrays.toString(active.toLongArray()));
        System.out.println("restored = " + BitSet.valueOf(active.toLongArray()));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac --release 17 BitSetIndexDemo.java
java BitSetIndexDemo
```

**Stdout chính xác:**

```text
active = {1, 3, 6}
get(3) = true
get(4) = false
count = 3
length = 7
updated = {1, 4}
union = {0, 1, 4, 5}
intersection = {4}
difference = {1}
xor = {0, 1, 5}
indices = [1, 4]
nextSetBit(2) = 4
nextClearBit(0) = 0
slice [2, 6) = {2}
packed longs = [18]
restored = {1, 4}
```

**Phân tích chương trình:**

1. `fromIndices(1, 3, 6)` tạo tập có ba vị trí bật. `get(3)` là true; `get(4)` false.
2. `cardinality()` bằng 3. `length()` bằng 7 vì bit cao nhất đang bật có chỉ số 6.
3. `flip(3)` tắt bit 3; `set(4)` bật bit 4; `clear(6)` tắt bit 6. Tập còn **{1, 4}**.
4. Trước các phép tập hợp, chương trình gọi `clone()` để **không làm thay đổi `active`**. Nhờ đó mọi phép đều được so sánh trên cùng tập gốc.
5. `union` là hợp {1,4} ∪ {0,4,5} = {0,1,4,5}; `intersection` là {4}; `difference` là {1}; `xor` là {0,1,5}.
6. `stream().toArray()` cho mảng chỉ số đang bật theo thứ tự tăng dần. Dòng `indices` in `[1, 4]`.
7. `get(2, 6)` tạo BitSet mới cho đoạn [2,6). **Chỉ số trong kết quả được dịch xuống**, nên bit gốc ở 4 trở thành bit 2; output là `{2}`.
8. `toLongArray()` đóng gói {1,4} thành một từ 64 bit có giá trị `2 + 16 = 18`; `valueOf(...)` phục hồi đúng tập {1,4}.

Ví dụ này không phụ thuộc cơ sở dữ liệu, file hay mạng, nên output có thể tái hiện nhất quán. Tất cả các API dùng trong chương trình đều khả dụng trên Java 17.

## 5. BitSet như một tập hợp chỉ số: hợp, giao, hiệu và hiệu đối xứng

Nếu xem `BitSet` là tập các số nguyên không âm thì các phép toán logic có ý nghĩa trực tiếp:

| Phép tập hợp | Java API | Điều xảy ra với receiver |
| --- | --- | --- |
| Hợp `A ∪ B` | `A.or(B)` | Bật những bit nằm trong A hoặc B. **Thay đổi A**. |
| Giao `A ∩ B` | `A.and(B)` | Giữ bit đồng thời bật trong A và B. **Thay đổi A**. |
| Hiệu `A \ B` | `A.andNot(B)` | Xóa khỏi A những bit có trong B. **Thay đổi A**. |
| Hiệu đối xứng `A △ B` | `A.xor(B)` | Bật bit xuất hiện ở đúng một trong hai tập. **Thay đổi A**. |
| Có giao nhau? | `A.intersects(B)` | Trả boolean, **không sửa A/B**. |
| So sánh bằng nhau | `A.equals(B)` | So sánh các vị trí true; không yêu cầu capacity bằng nhau. |

Điểm dễ mắc lỗi là các phương thức `and/or/xor/andNot` trả về **`void`**, không trả BitSet mới. Ví dụ:

```java
BitSet a = new BitSet();
a.set(1);
BitSet b = new BitSet();
b.set(2);

// Đúng nếu muốn giữ a:
BitSet combined = (BitSet) a.clone();
combined.or(b);
System.out.println(a);        // {1}
System.out.println(combined); // {1, 2}
```

Đây là snippet trong phương thức đã import `BitSet`. Nếu gọi trực tiếp `a.or(b)`, đối tượng `a` sẽ thay đổi. Việc một đối tượng là mutable cũng đồng nghĩa nhiều biến cùng trỏ tới nó sẽ cùng quan sát thay đổi.

### 5.1. Kiểm tra tập con

Có thể suy luận **A là tập con của B** bằng cách trừ B khỏi một bản sao A rồi kiểm tra rỗng:

```java
static boolean isSubsetOf(BitSet a, BitSet b) {
    BitSet remainder = (BitSet) a.clone();
    remainder.andNot(b);
    return remainder.isEmpty();
}
```

Đây là phương thức minh họa trong một lớp có import `BitSet`. Nó không sửa hai đối số. `a.intersects(b)` chỉ kiểm tra **ít nhất một phần tử chung**, không phải kiểm tra tập con.

Ví dụ A={1,4}, B={1,4,8} thì `isSubsetOf(A,B)` là true. Nếu A={1,7} thì false.

## 6. Duyệt các chỉ số đang bật thay vì quét toàn bộ miền

Với một `BitSet` có nhiều vị trí false, thường muốn duyệt **chỉ những bit true**.

### 6.1. Dùng nextSetBit

```java
for (int i = bits.nextSetBit(0);
     i >= 0;
     i = bits.nextSetBit(i + 1)) {
    System.out.println("selected index = " + i);
    if (i == Integer.MAX_VALUE) {
        break; // Tránh i+1 bị overflow.
    }
}
```

Đây là code minh họa trong phương thức có `BitSet bits`. `nextSetBit(fromIndex)` tìm chỉ số true đầu tiên từ `fromIndex` trở lên và trả `-1` nếu không còn. Thao tác này tiết kiệm việc gọi `get(i)` lần lượt trên mọi vị trí false, đặc biệt khi kết quả chỉ chứa một số bit bật.

Điều kiện tránh overflow ở `Integer.MAX_VALUE` được Javadoc nhắc tới khi mô tả vòng lặp chuẩn. Với dữ liệu có miền chỉ số biết trước nhỏ hơn, bạn có thể dùng ràng buộc miền để đơn giản hóa code. Không sử dụng chỉ số âm; các API truy cập bit thông thường từ chối chỉ số âm.

### 6.2. Dùng IntStream trên Java 17+

```java
int[] selectedIndices = bits.stream().toArray();
long count = bits.stream().count();
```

Đây là snippet trong phương thức đã có `BitSet bits`. `stream()` trả `IntStream` gồm các **chỉ số bit true**, thứ tự tăng dần. Nó không tạo stream boolean cho tất cả bit từ 0 tới `size()`. `stream()` có từ Java 8; dùng trong JDK 17+ hoàn toàn phù hợp.

**Không thay đổi BitSet trong khi terminal operation của stream đang duyệt**: Javadoc không định nghĩa kết quả nếu set bị sửa đồng thời với quá trình duyệt. Nếu cần snapshot độc lập để xử lý lâu dài, sao chép các chỉ số thành `int[]` hoặc clone đối tượng rồi mới làm việc.

### 6.3. Tìm bit false, tìm về phía trước hoặc phía sau

- `nextClearBit(i)`: vị trí `false` đầu tiên từ i trở lên, hữu ích khi cần tìm slot trống.
- `nextSetBit(i)`: vị trí `true` đầu tiên từ i trở lên.
- `previousSetBit(i)`: vị trí `true` gần nhất không lớn hơn i.
- `previousClearBit(i)`: vị trí `false` gần nhất không lớn hơn i.

Với các cờ dùng trong một miền có giới hạn [0, N), hãy kiểm tra kết quả của `nextClearBit` có **nhỏ hơn N** trước khi cấp phát slot. Bởi bên ngoài vùng đã được sử dụng, các bit cũng có giá trị `false`; một BitSet không tự giới hạn “slot có hiệu lực”.

## 7. Cắt một khoảng với get(from, to): chỉ số được dịch về 0

`get(int fromIndex, int toIndex)` trả một **BitSet mới**, không phải một view giữ nguyên chỉ số tuyệt đối. Phần tử tại chỉ số `fromIndex` của tập gốc trở thành bit số **0** của tập kết quả.

Ví dụ:

```java
BitSet original = new BitSet();
original.set(4);
original.set(7);
BitSet window = original.get(3, 8);
System.out.println(window); // {1, 4}
```

Đây là snippet trong phương thức. Bit 4 ban đầu trở thành 4−3=1 và bit 7 thành 7−3=4. Nếu đang lưu **ID toàn cục** và cần giữ nguyên ID, hãy cân nhắc việc copy các vị trí hoặc lưu offset riêng thay vì ngầm hiểu `get(range)` giữ nguyên chỉ số.

Tương tự, các phương thức `set(from,to)` và `clear(from,to)` áp dụng lên khoảng của **đối tượng hiện tại**, không trả một BitSet con mới.

## 8. Dùng BitSet làm dãy cờ có tên: phải có mapping chỉ số ổn định

Một cách thực tế là định nghĩa các vị trí cờ bằng hằng số:

```java
static final int CAN_READ = 0;
static final int CAN_WRITE = 1;
static final int CAN_EXPORT = 2;

static BitSet examplePermissions() {
    BitSet permissions = new BitSet(3);
    permissions.set(CAN_READ);
    permissions.set(CAN_EXPORT);

    if (!permissions.get(CAN_WRITE)) {
        System.out.println("Write permission is disabled");
    }
    return permissions;
}
```

Đây là snippet minh họa trong một class đã import `java.util.BitSet`, không phải file độc lập. Sau khi gọi, `permissions` chứa các bit {0,2}. `BitSet` không tự biết bit 0 tên là CAN_READ; nếu ghi/đọc qua file hoặc giữa các phiên bản hệ thống, bảng quy ước index phải **ổn định**.

### 8.1. Cẩn thận với Enum.ordinal()

Nếu dữ liệu lưu lâu dài, không nên tùy tiện lấy `enum.ordinal()` làm index bền vững. Thứ tự khai báo enum có thể thay đổi khi thêm/sắp xếp hằng số, khiến cùng bit index mang ý nghĩa khác ở phiên bản sau. Khi cần serialization, nên dùng **ID cờ ổn định được quy định rõ** hoặc schema ánh xạ có version.

Nếu toàn bộ đối tượng cần biểu diễn là **một tập giá trị enum**, không có nhu cầu bit index bên ngoài, `EnumSet<Feature>` thường dễ đọc, type-safe và phù hợp hơn. BitSet có lợi khi miền chính là **chỉ số nguyên** hoặc format dữ liệu yêu cầu vị trí bit xác định.

### 8.2. Không dùng BitSet như hệ thống phân quyền hoàn chỉnh

BitSet chỉ lưu trạng thái flag. Việc kiểm tra quyền cần xử lý xác thực, policy, scope, ownership, và cập nhật đồng bộ. Một `BitSet` local trong bộ nhớ **không thay thế** hệ thống authorization hay kiểm tra ở server. Đừng mặc định dữ liệu cờ đến từ client là đáng tin, vì client có thể tự gửi bit được bật.

## 9. Biểu diễn tập chỉ số theo miền dữ liệu

Một tình huống phổ biến là đánh dấu các hàng hoặc tác vụ đã xử lý trong một batch có `N` phần tử:

```java
static void markProcessed(BitSet processed, int rowIndex, int totalRows) {
    if (rowIndex < 0 || rowIndex >= totalRows) {
        throw new IndexOutOfBoundsException("Invalid row index: " + rowIndex);
    }
    processed.set(rowIndex);
}
```

Đây là phương thức minh họa trong lớp đã import `BitSet`. Việc kiểm tra `rowIndex < totalRows` là **ràng buộc nghiệp vụ**, không phải ràng buộc mặc định của `BitSet`. Khi dùng một BitSet cho 200 task, `set(1000)` có thể làm đối tượng tự tăng vùng lưu trữ thay vì từ chối theo N=200.

Sau khi đánh dấu:

- `processed.cardinality()` cho số task được đánh dấu xong.
- `processed.get(i)` cho biết task tại vị trí i đã được đánh dấu hay chưa.
- `processed.nextClearBit(0)` cho vị trí chưa xử lý đầu tiên; **phải so sánh với N** để biết còn task hợp lệ nào chưa.
- Khi `processed.cardinality() == N` và **tất cả bit thuộc [0,N) đã được đặt**, có thể coi batch đầy đủ; lưu ý không được để bit ngoài miền làm sai thống kê. Cách chắc chắn hơn là kiểm tra miền, không chỉ tin tổng số.
- Dùng `processed.get(0,N)` để xem snapshot trạng thái trong miền [0,N), với indices kết quả tương ứng 0..N−1.

Với batch có cấu trúc thưa, ID không liên tục và có giá trị rất lớn, không nên gán thẳng mỗi ID làm chỉ số bit nếu điều đó khiến BitSet mở rộng vô lý. Có thể ánh xạ ID sang index liên tục trước hoặc chọn cấu trúc dữ liệu khác.

## 10. Đóng gói và phục hồi bit: toLongArray, toByteArray, valueOf

`BitSet` có thể chuyển sang mảng primitive để lưu truyền dữ liệu:

- `bits.toLongArray()` → `long[]`; mỗi phần tử chứa tới 64 bit.
- `bits.toByteArray()` → `byte[]`; mỗi phần tử chứa tới 8 bit.
- `BitSet.valueOf(long[])` và `BitSet.valueOf(byte[])` → tạo BitSet mới từ mảng.
- Các overload `valueOf(LongBuffer)` và `valueOf(ByteBuffer)` hỗ trợ dữ liệu trong buffer, với cách diễn giải bit theo tài liệu chính thức.

Ví dụ:

```java
BitSet bits = new BitSet();
bits.set(1);
bits.set(4);
System.out.println(java.util.Arrays.toString(bits.toLongArray())); // [18]
System.out.println(java.util.Arrays.toString(bits.toByteArray())); // [18]
System.out.println(BitSet.valueOf(new long[]{18L})); // {1, 4}
```

Đây là snippet minh họa cần đặt trong một phương thức. Vì 18 = 2¹ + 2⁴, cả byte thấp và long thấp có bit 1,4 bật. Chú ý thứ tự bit theo **little-endian**: ở byte thứ nhất, bit 0 là bit ít trọng số nhất; vị trí n nằm tại `bytes[n / 8]`, bit thứ `n % 8`. Tương tự với `longs[n / 64]` và bit thứ `n % 64`.

### 10.1. Không nhầm thứ tự bit với “String binary”

`BitSet.toString()` trả danh sách vị trí true, ví dụ `{1, 4}`. Nó **không** trả `"00010010"`. Nếu muốn một chuỗi binary có chiều dài cố định, cần tự định nghĩa thứ tự chỉ số và padding theo format của ứng dụng.

Ví dụ muốn hiển thị đúng tám bit với **bit 7 ở bên trái, bit 0 ở bên phải**:

```java
static String formatEightBits(BitSet bits) {
    StringBuilder out = new StringBuilder(8);
    for (int i = 7; i >= 0; i--) {
        out.append(bits.get(i) ? '1' : '0');
    }
    return out.toString();
}
```

Đây là phương thức minh họa. Nếu `bits` có {1,4}, kết quả sẽ là `"00010010"`. Với format khác, phải xác định rõ thứ tự bit để hai hệ thống không giải mã trái ngược.

### 10.2. Khi lưu dữ liệu, chiều dài miền không tự được bảo toàn

`toByteArray()` và `toLongArray()` trả dữ liệu đủ để biểu diễn **các bit true**, không bắt buộc giữ các byte/long chỉ chứa các bit false ở đuôi. Vì vậy nếu dãy cờ có miền logic [0,100) nhưng bit cao nhất true là 12, mảng xuất ra có thể **không đủ để tự suy ra N=100**.

Để có một format bền vững:

1. Lưu thêm **logical length N** hoặc định nghĩa một schema đã biết N.
2. Cố định mapping chỉ số ↔ ý nghĩa của cờ.
3. Nếu trao đổi qua hệ thống khác, quy định bit order, byte order, version và xử lý input sai.
4. Kiểm tra dữ liệu đầu vào không vượt phạm vi/memory budget trước khi xây BitSet từ bytes đến từ nguồn không tin cậy.
5. Kiểm thử round-trip `valueOf(bits.toByteArray())` **về các vị trí bật**, không lấy `size()` làm điều kiện bằng nhau.

`BitSet.equals(...)` kiểm tra vị trí true, không đồng nghĩa nội dung serialized phải lưu cùng một dung lượng nội bộ. Với các loại giao thức bảo đảm khả năng tương thích, đừng phụ thuộc vào Java object serialization mặc định khi cần một format ổn định liên ngôn ngữ; định nghĩa schema cụ thể.

## 11. Hiệu năng và sử dụng bộ nhớ: chọn BitSet đúng miền

Một `BitSet` thường dùng ít bộ nhớ hơn việc lưu mỗi cờ thành một object, vì bit được gom trong các từ lưu trữ. Nhưng **không có quy tắc BitSet luôn tốt nhất**:

- **Miền chỉ số khá dày, nhiều trạng thái boolean hoặc cần phép toán tập hợp nhanh:** BitSet thường phù hợp. Ví dụ 50.000 vị trí liên tục, hay thường xuyên hợp/giao hai tập.
- **Miền chỉ số nhỏ và cố định, cần tên/kiểu rõ ràng:** `EnumSet` hoặc một vài boolean/field có tên có thể dễ hiểu hơn.
- **Một tập ID rất thưa có chỉ số tối đa cực lớn:** `HashSet<Integer>` hoặc một cấu trúc tập thưa chuyên dụng có thể phù hợp hơn. BitSet dự trù theo vị trí bit cao nhất, nên việc chỉ bật một bit ở chỉ số rất lớn có thể gây tốn bộ nhớ đáng kể.
- **Một dãy kích thước cố định và cần đọc trực tiếp từng phần tử:** `boolean[]` đơn giản, rõ ràng, dù thường tiêu tốn nhiều byte hơn BitSet cho cùng số lượng cờ.
- **Chỉ cần tối đa 64 cờ và có một giao thức bitmask rõ ràng:** `long` với phép `& | ^ ~ <<` có thể gọn hơn, nhưng phải quản lý shift và bitmask đúng, dễ nhầm khi mở rộng.
- **Cần giữ thứ tự thêm phần tử hoặc khóa tùy ý:** BitSet không phải danh sách có thứ tự chèn hay Map. Nó chỉ biểu diễn membership theo chỉ số không âm.

### 11.1. Dung lượng có thể tăng theo chỉ số cao nhất

`BitSet` tự mở rộng khi cần. Chỉ bật một bit có chỉ số rất lớn có thể khiến vùng lưu trữ phải phủ qua nhiều vị trí false ở giữa. Điều này khác với `HashSet<Integer>` vốn lưu những phần tử được thêm vào mà không phải dành một bit cho mọi số nguyên nhỏ hơn phần tử lớn nhất.

Vì vậy trước khi dùng ID từ database làm bit index, hãy xem độ lớn và tính liên tục của ID. Nếu ID là số ngẫu nhiên hoặc không liên tục, có thể cần **mapping ID → index** hoặc một tập sparse thích hợp.

### 11.2. Chi phí của các phép logic

Các phép `and/or/xor/andNot` hoạt động trên những nhóm bit, thuận tiện hơn việc lặp qua từng chỉ số trong nhiều tình huống. Tuy nhiên tốc độ thực tế còn phụ thuộc độ lớn miền, số phép thực hiện, cách cấp phát/clone và đặc điểm dữ liệu. Nếu hiệu năng là mục tiêu, **benchmark đúng workload**; đừng giả định mọi phép trên BitSet là O(1) hay BitSet luôn nhanh hơn một Set thông thường.

## 12. Mutable, copy và đồng bộ khi nhiều thread

`BitSet` là **mutable**. Cả `set/clear/flip` và phép tập hợp như `or/and/xor` đều thay đổi đối tượng. Hai biến cùng trỏ một BitSet sẽ cùng nhìn thấy thay đổi:

```java
BitSet original = new BitSet();
original.set(1);
BitSet alias = original;
alias.set(2);
System.out.println(original); // {1, 2}

BitSet copy = (BitSet) original.clone();
copy.clear(1);
System.out.println(original); // {1, 2}
System.out.println(copy);     // {2}
```

Đây là snippet trong phương thức. `clone()` tạo đối tượng BitSet độc lập về trạng thái các bit, dù return type là `Object` nên cần cast `(BitSet)`.

**BitSet không bảo đảm an toàn thread khi nhiều luồng truy cập và sửa đổi đồng thời.** Nếu chia sẻ một đối tượng mutable giữa thread, cần đồng bộ hóa bên ngoài hoặc một thiết kế dữ liệu đồng thời phù hợp. Không mặc định `stream()` an toàn khi một luồng sửa BitSet trong khi luồng khác đang duyệt.

Với API chỉ đọc, có thể truyền snapshot bằng `(BitSet) bits.clone()`, nhưng điều đó **không tự giải quyết** trường hợp nguồn bị sửa đồng thời trong lúc đang lấy snapshot. Cần xác định cách phối hợp truy cập/ownership từ đầu.

### 12.1. Không dùng BitSet làm cơ chế cấp quyền truy cập thread-safe tự động

Một `BitSet` đánh dấu “task đã xong” giữa nhiều worker có thể gặp race condition nếu không có đồng bộ. BitSet không thay thế các primitive `AtomicIntegerArray`, cấu trúc concurrent hay lock khi bài toán yêu cầu cập nhật nguyên tử. Hãy chọn cơ chế synchronization theo thiết kế đa luồng.

## 13. So sánh BitSet với những lựa chọn phổ biến

| Nhu cầu | BitSet | boolean[] | HashSet<Integer> | EnumSet |
| --- | --- | --- | --- | --- |
| Membership theo chỉ số không âm | Rất phù hợp | Phù hợp trong miền cố định | Phù hợp cả chỉ số rời rạc | Không, chỉ nhận enum |
| Tự mở rộng miền bit | Có | Không, phải tạo mảng mới | Không phụ thuộc chỉ số tối đa | Theo kiểu enum |
| Đếm bit true / số phần tử | `cardinality()` | Tự đếm | `size()` | `size()` |
| Hợp/giao/hiệu | `or/and/andNot` | Tự lặp | `addAll/retainAll/removeAll` | Có các thao tác Set |
| Biểu diễn cờ có tên type-safe | Cần mapping riêng | Cần mapping riêng | Cần mapping riêng | Rất phù hợp nếu cờ là enum |
| Dữ liệu thưa với chỉ số rất lớn | Cần cân nhắc memory | Có thể tốn quá nhiều | Thường phù hợp hơn | Không áp dụng |
| Trạng thái mutable | Có | Có | Có | Có |

Bảng chỉ hỗ trợ quyết định cấu trúc dữ liệu; lựa chọn thực tế còn phụ thuộc kích thước, phân bố chỉ số, workload và ràng buộc API. Một `EnumSet` có thể được triển khai hiệu quả bằng bit vector nhưng vẫn cung cấp **kiểu enum rõ ràng**, vì vậy đừng đổi EnumSet sang BitSet chỉ vì suy đoán về vài byte.

## 14. Những lỗi thường gặp khi dùng BitSet

**Lỗi 1 — Nhầm `size()` với số bit true.** Sai; số bit true là `cardinality()`. `size()` là dung lượng biểu diễn nội bộ.

**Lỗi 2 — Nhầm `length()` với tổng số cờ đã định nghĩa.** Sai; `length()` dựa trên bit true cao nhất. Những bit false ở cuối miền không được tính vào length.

**Lỗi 3 — Đếm chỉ số từ 1.** BitSet đánh chỉ số từ 0. Nếu cấu trúc nghiệp vụ dùng ID 1-based, cần mapping rõ ràng để tránh off-by-one.

**Lỗi 4 — Coi khoảng `set(2, 6)` bao gồm cả 6.** Sai; đầu phải exclusive. Nó bật 2,3,4,5.

**Lỗi 5 — Dùng `flip(i)` thay cho `set(i)` khi xử lý lại sự kiện.** Flip có thể làm mất trạng thái bật cũ; set giữ idempotency cho tác vụ đánh dấu.

**Lỗi 6 — Cho rằng `get(from,to)` giữ nguyên chỉ số gốc.** Sai; kết quả là BitSet mới với index dịch về 0 theo from.

**Lỗi 7 — Tưởng `and/or/xor` trả BitSet mới.** Sai; các phương thức trả `void` và sửa receiver. Dùng clone trước nếu muốn giữ bản gốc.

**Lỗi 8 — Duyệt bằng `for (int i=0; i<bits.size(); i++)` rồi gọi là số phần tử.** Sai. Nó duyệt theo dung lượng, không theo bit true. Dùng `nextSetBit` hoặc `stream()` khi mục tiêu là tập chỉ số bật.

**Lỗi 9 — Lấy kết quả `nextClearBit(0)` làm chỉ số hợp lệ mà không kiểm tra giới hạn.** Sai nếu miền có N phần tử; kết quả có thể từ N trở lên.

**Lỗi 10 — Gán ID database lớn trực tiếp thành bit index.** Có thể làm BitSet cấp phát rất nhiều bộ nhớ, dù chỉ vài bit true.

**Lỗi 11 — Cho rằng `toByteArray()` lưu mọi bit false ở đuôi miền.** Sai; hãy lưu N/schema riêng khi format yêu cầu.

**Lỗi 12 — Đọc chuỗi `{1, 4}` như binary.** `toString()` in danh sách chỉ số bật, không phải chuỗi các bit theo thứ tự.

**Lỗi 13 — Chia sẻ một BitSet mutable giữa nhiều thread không đồng bộ.** Không an toàn theo Javadoc; cần cơ chế concurrency riêng.

**Lỗi 14 — Cố thay EnumSet bằng BitSet mà không định nghĩa mapping.** Làm mất type safety/ý nghĩa cờ; EnumSet có thể phù hợp hơn nếu domain là enum.

**Lỗi 15 — Coi dữ liệu BitSet nhận từ client là quyền đã được xác thực.** Không. BitSet chỉ là representation; cần kiểm tra authorization ở tầng tin cậy.

## 15. Checklist áp dụng vào code dự án

Khi review một đoạn code dùng BitSet, kiểm tra:

1. **Ý nghĩa bit:** mỗi chỉ số ứng với đối tượng/cờ nào? Mapping có ổn định qua phiên bản nếu lưu hoặc truyền dữ liệu không?
2. **Miền hợp lệ:** N bao nhiêu? Có kiểm tra index 0..N−1, hay dữ liệu có thể mở rộng không giới hạn?
3. **Cấu trúc dữ liệu:** miền đủ dày để dùng BitSet, hay thưa tới mức HashSet<Integer>/mapping hiệu quả hơn?
4. **Chỉ số và khoảng:** các lời gọi `set/clear/flip/get` dùng chỉ số zero-based và khoảng [from,to) đúng không?
5. **Số lượng:** code dùng `cardinality` để đếm bit true, không dùng nhầm `size` hoặc `length`?
6. **Mutation:** các phép `or/and/xor/andNot` có vô ý sửa đối tượng của caller không? Nếu cần, clone trước.
7. **Traversal:** chọn `nextSetBit` hoặc `stream` khi chỉ cần các bit bật; xử lý đúng sentinel `-1`.
8. **Tìm slot trống:** với `nextClearBit`, có kiểm tra giới hạn miền N hay không?
9. **Serialization:** bit order, byte order, logical length N và mapping cờ có được quy định rõ? Có test round-trip không?
10. **Concurrency:** nếu share mutable BitSet, có đồng bộ hóa hoặc ownership đúng không?
11. **Input không tin cậy:** chỉ số và kích thước mảng đầu vào có được giới hạn để tránh tiêu thụ bộ nhớ quá mức?
12. **API phù hợp:** nếu cờ là enum có tên, EnumSet có thể rõ ràng hơn không? Nếu miền cố định nhỏ, boolean[] hoặc long có đủ không?
13. **Test đường biên:** tập rỗng, bit 0, chỉ số cao nhất hợp lệ, chỉ số âm, khoảng rỗng, phép tập hợp trên hai tập khác độ dài, clone và byte round-trip.
14. **Thông tin cá nhân/bảo mật:** không đưa một bitset về phía client rồi tin rằng client không thể bật các cờ nhạy cảm.

Checklist là cách hệ thống hóa review, không có nghĩa mọi bài toán đều phải dùng tất cả API của BitSet.

## 16. Bài tập tự kiểm tra

**1.** `BitSet b = new BitSet(); b.set(2); b.set(7);`. Hỏi `cardinality()` và `length()`? — **2 và 8**. Chỉ có hai bit true; cao nhất là 7.

**2.** `new BitSet(200)` vừa tạo có 200 bit true không? — **Không**. Tất cả đều false; `cardinality()` là 0.

**3.** `set(3, 6)` bật các chỉ số nào? — **3,4,5**. Không bật 6 vì toIndex exclusive.

**4.** `A={1,4}`, `B={4,5}`. Sau `A.and(B)`, A là gì? — **{4}**. A bị thay đổi, B không bị sửa bởi lệnh đó.

**5.** Cần tạo hợp A∪B nhưng vẫn giữ A ban đầu. Làm sao? — Clone A rồi gọi `or(B)` trên bản sao.

**6.** `BitSet b` có bit true tại 4,7; `b.get(3,8)` chứa chỉ số nào? — **{1,4}**, vì các bit được dịch về đầu khoảng.

**7.** Muốn đếm số vị trí true dùng gì? — **`cardinality()`**. Không phải size/length.

**8.** Muốn duyệt tất cả vị trí true theo thứ tự tăng dần? — Dùng **`nextSetBit`** trong vòng lặp hoặc **`stream()`** trên Java 17+.

**9.** Dùng `nextClearBit(0)` để tìm công việc chưa xong trong 100 phần tử có cần điều kiện phụ? — **Có**. Chỉ số trả về phải **nhỏ hơn 100**.

**10.** `BitSet.valueOf(new byte[]{18})` có các bit nào true? — **1 và 4** (18 = 0b00010010).

**11.** Nếu dãy có 100 cờ nhưng bit cao nhất true là 12, `toByteArray()` có tự lưu lại số 100 không? — **Không**. Cần lưu logical length/schema riêng.

**12.** Vì sao BitSet có thể không phù hợp để lưu vài ID rất lớn, rời rạc? — Vì vùng bit có thể phải mở rộng tới index cao nhất, gây tốn bộ nhớ.

**13.** BitSet có tự cung cấp thread safety cho nhiều worker cùng cập nhật không? — **Không**. Cần bảo vệ truy cập hoặc dùng cấu trúc concurrent phù hợp.

**14.** Tập các quyền định nghĩa bằng enum nên cân nhắc class nào trước? — **`EnumSet<Permission>`**, vì biểu đạt kiểu enum và ngữ nghĩa rõ hơn.

## Tài liệu chính thức còn áp dụng

- [Java SE 17 API — java.util.BitSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/BitSet.html): chữ ký và hợp đồng `set/clear/flip/get`, `cardinality/length/size`, `and/or/xor/andNot`, `stream`, `valueOf`, `toLongArray`, `toByteArray`, giới hạn thread safety.
- [Java SE 17 API — java.util.EnumSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html): lựa chọn phù hợp khi tập là các hằng enum.
- [Java SE 17 API — java.util.HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): lựa chọn để biểu diễn tập giá trị rời rạc không phụ thuộc vị trí bit cao nhất.
- [Java SE 17 API — java.util.stream.IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): xử lý dãy chỉ số nguyên từ `BitSet.stream()`.

**Ghi nhớ:** `BitSet` là **tập các chỉ số nguyên không âm có bit true**, không phải danh sách boolean cố định. Bật/tắt bằng `set/clear/flip`; đếm bằng `cardinality()`; phân biệt `length()` và `size()`; duyệt bằng `nextSetBit/stream`; dùng `or/and/andNot/xor` trên bản sao nếu cần giữ dữ liệu gốc. Với dãy cờ có schema, quản lý mapping và logical length N riêng, đồng thời cân nhắc cấu trúc khác nếu dữ liệu rất thưa hoặc thực chất là một EnumSet.