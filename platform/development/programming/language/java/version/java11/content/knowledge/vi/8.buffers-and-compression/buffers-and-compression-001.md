# ByteBuffer.mismatch và chỉ số khác biệt đầu tiên trong Java 11+

## 1. Mục tiêu và phạm vi

Khi xử lý các **buffer byte** trong Java NIO, nhất là dữ liệu nhị phân đọc từ file, truyền qua mạng hoặc được tạo ra từ thuật toán nén, ta thường cần biết hai vùng dữ liệu có giống nhau không và nếu không thì **byte đầu tiên khác nhau ở đâu**.

Kể từ **Java 11**, `ByteBuffer` có phương thức:

```java
int index = first.mismatch(second);
```

`ByteBuffer.mismatch(ByteBuffer that)` trả về **chỉ số tương đối** của byte đầu tiên khác nhau giữa **hai dãy byte còn lại (remaining)**. Phương thức này vẫn được hỗ trợ trên các JDK hiện đại; có thể dùng với bộ đệm lưu trên heap, bộ đệm trực tiếp (`direct buffer`) và bộ đệm chỉ đọc.

Ví dụ tối giản:

```java
ByteBuffer a = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
ByteBuffer b = ByteBuffer.wrap(new byte[] {10, 20, 99, 40});

System.out.println(a.mismatch(b)); // 2
```

Hai byte đầu bằng nhau; byte ở chỉ số tương đối `2` khác nhau: `30` so với `99`. Vì vậy phương thức trả **`2`**, không phải số lượng byte khác biệt.

Phạm vi của `mismatch` là **nội dung byte thực tế**, không tự giải mã Unicode, giải nén hoặc tính offset toàn file.

## 2. Hiểu ba khái niệm của ByteBuffer: position, limit và remaining

`ByteBuffer` là một vùng byte có trạng thái:

- **`capacity()`:** tổng sức chứa của buffer.
- **`position()`:** vị trí hiện tại, tức điểm bắt đầu phần dữ liệu cần thao tác.
- **`limit()`:** giới hạn kết thúc (không bao gồm vị trí limit).
- **`remaining()`:** số byte còn lại, bằng `limit() - position()`.

Ví dụ:

```text
ByteBuffer: [A, B, C, D, E, F]
Index:       0  1  2  3  4  5
                   ^           ^
              position=2     limit=6

Remaining: [C, D, E, F]
Chỉ số tương đối: 0, 1, 2, 3
```

Chỉ các byte từ **`position` đến trước `limit`** tham gia so sánh. Những byte ở trước `position` hay nằm sau `limit` không được xét. Hai buffer có capacity khác nhau vẫn có thể so bằng nhau nếu **dãy remaining của chúng giống nhau**.

Phương thức `mismatch` **không di chuyển `position`, không thay `limit` và không tiêu thụ byte**. Nếu bạn thay `position` hoặc `limit` trước lần gọi tiếp theo, chính **vùng dữ liệu được so sánh** sẽ khác đi.

## 3. Hợp đồng trả về của mismatch

Chữ ký API:

```java
public int mismatch(ByteBuffer that)
```

Gọi `n = Math.min(a.remaining(), b.remaining())`. Kết quả có ý nghĩa:

| Kết quả | Ý nghĩa |
| --- | --- |
| `-1` | Hai phần remaining có **cùng độ dài** và mọi byte tương ứng đều bằng nhau |
| `0 <= i < n` | Byte tương ứng ở chỉ số tương đối `i` là cặp byte đầu tiên khác nhau |
| `n` (khi remaining khác độ dài) | Phần chung dài `n` byte giống nhau; một buffer là **tiền tố đúng** của buffer kia |

Lưu ý nếu `n = 0` và một phía có dữ liệu còn phía kia rỗng, kết quả là **`0`**. Nếu cả hai dãy remaining rỗng, kết quả là **`-1`**.

Ví dụ:

| Buffer A còn lại | Buffer B còn lại | `a.mismatch(b)` | Vì sao |
| --- | --- | --- | --- |
| `[1, 2, 3]` | `[1, 2, 9]` | `2` | Byte thứ ba khác |
| `[1, 2, 3]` | `[1, 2, 3]` | `-1` | Bằng nhau cả độ dài |
| `[7, 8]` | `[7, 8, 9]` | `2` | B là dãy dài hơn, A là tiền tố |
| `[]` | `[4]` | `0` | Tiền tố rỗng, khác độ dài |
| `[]` | `[]` | `-1` | Hai dãy rỗng giống nhau |

**Quan trọng:** khi kết quả bằng `n` vì khác độ dài, **không có cặp byte khác nhau tại chỉ số `n` trên cả hai buffer**. Bên ngắn đã hết dữ liệu.

## 4. Cơ chế tìm byte khác đầu tiên

Để hiểu cách kết quả được xác định, có thể hình dung thuật toán sau:

1. Bắt đầu từ `a.position()` và `b.position()`.
2. Xét từng offset tương đối `i = 0, 1, ...` nhỏ hơn số byte remaining của **cả hai**.
3. Nếu `a.get(a.position() + i) != b.get(b.position() + i)`, trả về `i`.
4. Nếu toàn bộ vùng chung giống nhau nhưng một bên dài hơn, trả về số byte chung.
5. Nếu cùng độ dài và mọi byte giống nhau, trả về `-1`.

Đây là **mô hình giải thích hợp đồng kết quả**; JDK có thể dùng triển khai tối ưu thay vì lặp từng byte theo cách diễn giải này.

Dữ liệu chỉ được so **theo byte**, không theo giá trị số nguyên nhiều byte. `ByteOrder.BIG_ENDIAN` hay `LITTLE_ENDIAN` ảnh hưởng cách lấy/đặt giá trị như `getInt()`, nhưng `mismatch` xét các byte đang được lưu; cùng từng byte thì bằng nhau dù byte order khác.

## 5. Chương trình hoàn chỉnh, chạy trên Java 11+

Tạo tệp **`ByteBufferMismatchDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class ByteBufferMismatchDemo {
    private static void show(String label, ByteBuffer left, ByteBuffer right) {
        int lp = left.position();
        int rp = right.position();
        int ll = left.limit();
        int rl = right.limit();

        int index = left.mismatch(right);
        System.out.println(label + " = " + index);

        if (index >= 0) {
            if (index < left.remaining() && index < right.remaining()) {
                int a = Byte.toUnsignedInt(left.get(lp + index));
                int b = Byte.toUnsignedInt(right.get(rp + index));
                System.out.println("  values = " + a + "/" + b
                        + ", absolute = " + (lp + index) + "/" + (rp + index));
            } else {
                System.out.println("  common prefix; lengths differ");
            }
        }
        System.out.println("  position stable = "
                + (left.position() == lp && right.position() == rp)
                + ", limit stable = "
                + (left.limit() == ll && right.limit() == rl));
    }

    public static void main(String[] args) {
        show("first difference",
                ByteBuffer.wrap(new byte[] {10, 20, 30, 40}),
                ByteBuffer.wrap(new byte[] {10, 20, 99, 40}));

        show("equal remaining",
                ByteBuffer.wrap(new byte[] {1, 2, 3}),
                ByteBuffer.wrap(new byte[] {0, 1, 2, 3, 9})
                        .position(1).limit(4));

        show("proper prefix",
                ByteBuffer.wrap(new byte[] {7, 8}),
                ByteBuffer.wrap(new byte[] {7, 8, 9}));

        ByteBuffer a = ByteBuffer.wrap(new byte[] {99, 1, 2, 3, 4});
        ByteBuffer b = ByteBuffer.wrap(new byte[] {77, 55, 1, 2, 8, 4});
        a.position(1).limit(4);
        b.position(2).limit(5);
        show("different positions", a, b);

        ByteBuffer direct = ByteBuffer.allocateDirect(3);
        direct.put(new byte[] {1, 2, 3}).flip();
        ByteBuffer heap = ByteBuffer.wrap(new byte[] {1, 2, 3});
        show("direct vs heap", direct, heap.asReadOnlyBuffer());

        ByteBuffer big = ByteBuffer.wrap(new byte[] {1, 2, 3});
        ByteBuffer little = ByteBuffer.wrap(new byte[] {1, 2, 3});
        big.order(ByteOrder.BIG_ENDIAN);
        little.order(ByteOrder.LITTLE_ENDIAN);
        show("different byte orders", big, little);

        ByteBuffer empty = ByteBuffer.allocate(0);
        show("empty vs nonempty", empty, ByteBuffer.wrap(new byte[] {4}));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp với JDK 11 trở lên:

```bash
javac --release 11 ByteBufferMismatchDemo.java
java ByteBufferMismatchDemo
```

**Đầu ra đã kiểm chứng bằng chương trình thực:**

```text
first difference = 2
  values = 30/99, absolute = 2/2
  position stable = true, limit stable = true
equal remaining = -1
  position stable = true, limit stable = true
proper prefix = 2
  common prefix; lengths differ
  position stable = true, limit stable = true
different positions = 2
  values = 3/8, absolute = 3/4
  position stable = true, limit stable = true
direct vs heap = -1
  position stable = true, limit stable = true
different byte orders = -1
  position stable = true, limit stable = true
empty vs nonempty = 0
  common prefix; lengths differ
  position stable = true, limit stable = true
```

Ý nghĩa từng phần:

- **`first difference`:** điểm khác đầu tiên tại offset `2`, byte lần lượt là `30` và `99`.
- **`equal remaining`:** mặc dù buffer bên phải có mảng gốc dài hơn, `position(1).limit(4)` chỉ để lại `[1,2,3]`, trùng buffer trái, nên trả `-1`.
- **`proper prefix`:** `[7,8]` là tiền tố của `[7,8,9]`, nên trả `2`. Hàm `show` cố ý không gọi `get` ở index `2` trên buffer ngắn.
- **`different positions`:** dãy so là `[1,2,3]` và `[1,2,8]`; offset tương đối `2` chuyển thành vị trí tuyệt đối `3` và `4`.
- **`direct vs heap`:** `mismatch` hoạt động bất kể cách cấp phát bộ nhớ, kể cả khi một view chỉ đọc.
- **`different byte orders`:** hai dãy byte giống nhau nên trả `-1`; byte order khác không thay đổi cách so từng byte.
- **`empty vs nonempty`:** một dãy rỗng và một dãy có byte đầu ⇒ khác độ dài ngay tại offset `0`.
- Những dòng `position stable / limit stable` chứng minh `mismatch` và cách đọc tuyệt đối trong ví dụ không tự làm thay đổi các mốc so sánh.

## 6. Chỉ số tương đối so với chỉ số tuyệt đối

Hãy xem:

```java
ByteBuffer left = ByteBuffer.wrap(new byte[] {99, 1, 2, 3, 4});
ByteBuffer right = ByteBuffer.wrap(new byte[] {77, 55, 1, 2, 8, 4});

left.position(1).limit(4);  // Phần remaining = [1, 2, 3]
right.position(2).limit(5); // Phần remaining = [1, 2, 8]

int index = left.mismatch(right); // 2
```

`index == 2` **không** có nghĩa byte khác nhau đều ở vị trí tuyệt đối `2`. Đúng phải là:

```java
int absoluteLeft = left.position() + index;   // 3
int absoluteRight = right.position() + index; // 4
byte leftByte = left.get(absoluteLeft);       // 3
byte rightByte = right.get(absoluteRight);    // 8
```

Mỗi buffer có thể có `position` khác nhau, nên offset tuyệt đối khác nhau. Khi thao tác với một block thuộc tệp lớn, offset trên toàn tệp còn cần **cộng thêm vị trí bắt đầu block**; `mismatch` không biết offset của file.

Để đọc cặp byte đầu tiên khác nhau an toàn:

```java
int i = left.mismatch(right);
int minRemaining = Math.min(left.remaining(), right.remaining());

if (i == -1) {
    System.out.println("Hai phần remaining giống hệt");
} else if (i == minRemaining) {
    System.out.println("Phần chung giống nhau, khác độ dài");
} else {
    byte x = left.get(left.position() + i);
    byte y = right.get(right.position() + i);
    System.out.println("Byte khác: " + Byte.toUnsignedInt(x)
            + " vs " + Byte.toUnsignedInt(y));
}
```

Đoạn này là **mảnh mã để đặt bên trong phương thức có biến `left`/`right`**, không phải chương trình riêng. `Byte.toUnsignedInt` chỉ chuyển kiểu hiển thị thành `0..255`; nó không làm thay đổi việc xác định byte nào khác nhau.

## 7. flip, slice và duplicate ảnh hưởng phép so sánh ra sao?

### `flip()` sau khi ghi

Khi ghi vào buffer bằng `put`, `position` tăng lên theo dữ liệu mới ghi. Trước khi chuyển sang đọc hoặc so nội dung mới ghi, cần đặt lại ranh giới:

```java
ByteBuffer data = ByteBuffer.allocate(3);
data.put(new byte[] {1, 2, 3});
data.flip(); // position=0, limit=3

ByteBuffer expected = ByteBuffer.wrap(new byte[] {1, 2, 3});
System.out.println(data.mismatch(expected)); // -1
```

Nếu thiếu `flip()`, `position` thường đang nằm ở cuối phần ghi; `remaining` có thể bằng `0`. Kết quả sẽ phản ánh **vùng rỗng**, khiến việc so với expected không đúng ý định.

`flip()` chuyển trạng thái sang đọc, không xóa dữ liệu. `clear()` chỉ khôi phục vị trí/giới hạn để chuẩn bị ghi, **không xóa những byte cũ đang nằm trong bộ nhớ**.

### `duplicate()` để chọn vùng, không đụng trạng thái gốc

```java
ByteBuffer source = ByteBuffer.wrap(new byte[] {9, 1, 2, 3, 9});
ByteBuffer view = source.duplicate();
view.position(1).limit(4); // So vùng [1,2,3]

ByteBuffer expected = ByteBuffer.wrap(new byte[] {1, 2, 3});
System.out.println(view.mismatch(expected)); // -1
System.out.println(source.position());       // 0
```

View có `position`/`limit` độc lập với buffer gốc. Tuy nhiên, **nội dung byte bên dưới được chia sẻ**, vì `duplicate()` không sao chép dữ liệu thực tế.

### `slice()` tạo view có chỉ số tương đối bắt đầu lại từ 0

Sau khi đã đặt `view.position(1).limit(4)`, dùng:

```java
ByteBuffer sub = view.slice(); // position=0, remaining=3
System.out.println(sub.mismatch(expected)); // -1
```

View `sub` mới đại diện đúng phần remaining, có `position=0` và chia sẻ byte với buffer nguồn. Phương thức `mismatch` không đòi hai buffer cùng capacity, cùng cách cấp phát hay cùng mảng backing.

## 8. So sánh với các API khác

| Phương thức | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `a.mismatch(b)` | `int` | Offset tương đối đầu tiên khác, hoặc `-1` |
| `a.equals(b)` | `boolean` | Hai `ByteBuffer` có cùng dãy byte remaining hay không |
| `a.compareTo(b)` | `int` âm/`0`/dương | So **thứ tự từ điển** của hai phần remaining |
| `Arrays.mismatch(byte[], byte[])` | `int` | Offset khác đầu tiên của **hai mảng byte** |

Khi `a` và `b` đều là `ByteBuffer`, `a.mismatch(b) == -1` có nghĩa dãy remaining giống nhau; điều đó nhất quán với `a.equals(b)`. Nhưng `equals` chỉ trả true/false, còn `mismatch` cho biết offset.

`compareTo` không trả offset. Nó so thứ tự từ điển theo các giá trị `byte` (có dấu) và độ dài, do đó trả âm/`0`/dương thay vì vị trí khác.

Ví dụ:

```java
ByteBuffer a = ByteBuffer.wrap(new byte[] {1, 2, 3});
ByteBuffer b = ByteBuffer.wrap(new byte[] {1, 2, 8});

System.out.println(a.mismatch(b));     // 2
System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b) < 0); // true
```

`Arrays.mismatch` áp dụng cho mảng byte, không hiểu `position`/`limit` của một buffer view. Đặc biệt, direct buffer và một số buffer chỉ đọc không cung cấp mảng backing truy cập được bằng `array()`. Nếu đang có `ByteBuffer`, nên dùng `mismatch` trực tiếp để giữ đúng phạm vi và không phụ thuộc cách cấp phát.

## 9. Ứng dụng với dữ liệu nhị phân và dữ liệu nén

**Phát hiện khác biệt sau truyền dữ liệu:** nếu `expected` và `actual` chứa các byte tương ứng đã được căn chỉnh, `mismatch` giúp xác định byte đầu tiên sai:

```java
ByteBuffer expected = ByteBuffer.wrap(new byte[] {5, 10, 15, 20});
ByteBuffer actual   = ByteBuffer.wrap(new byte[] {5, 10, 99, 20});

int offset = expected.mismatch(actual); // 2
```

**So sánh kết quả nén:** `mismatch` có thể kiểm tra hai **dãy byte nén** có đúng bằng nhau. Tuy nhiên, cùng dữ liệu **sau giải nén** có thể có các biểu diễn byte nén khác nhau vì metadata, mức nén hoặc định dạng container. `mismatch` không tự giải nén và không chứng minh hai file nén chứa cùng nội dung logic.

**Luồng dữ liệu lớn:** khi đọc theo block, cần `flip()`, chọn đúng `position/limit` và theo dõi offset đã xử lý. Chỉ số `mismatch` là chỉ số **trong vùng remaining của block hiện tại**; muốn báo offset toàn luồng phải cộng vị trí bắt đầu block. Nếu cách phân khúc dữ liệu khác nhau ở hai phía, cần căn chỉnh block để tránh kết luận sai.

**Tính toàn vẹn và bảo mật:** `mismatch == -1` chỉ chứng minh hai vùng byte đang so bằng nhau; nó không xác thực nguồn gốc hay phát hiện thay đổi có chủ đích nếu không có cơ chế kiểm tra khác. API không cam kết thời gian so sánh không phụ thuộc dữ liệu (constant-time); không sử dụng nó làm giải pháp chống tấn công thời gian khi so sánh giá trị bí mật.

## 10. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Xem `mismatch` như offset tuyệt đối | Đọc nhầm byte khi hai `position` khác nhau | Cộng `position() + index` cho **mỗi buffer** |
| Đọc byte khi kết quả bằng `minRemaining` | Truy cập ra ngoài buffer ngắn ở tình huống tiền tố | Chỉ đọc nếu `index < remaining()` ở **cả hai bên** |
| Cho rằng `-1` nghĩa toàn bộ capacity giống nhau | Bỏ qua việc phần trước position và sau limit không so | Nhớ API chỉ so **remaining** |
| Quên `flip()` sau `put` | Đang so vùng rỗng hoặc vùng không mong muốn | `flip` trước khi chuyển sang đọc/so |
| Nghĩ `mismatch` làm tăng `position` | Dùng trạng thái buffer sai ở thao tác tiếp | Tự điều chỉnh `position` nếu chương trình cần tiêu thụ byte |
| Lấy `compareTo` làm chỉ số khác đầu tiên | `compareTo` chỉ trả dấu thứ tự | Dùng `mismatch` |
| Gọi `array()` trên direct/read-only buffer | Có thể không có backing array truy cập được | Dùng chính `ByteBuffer.mismatch` |
| Cho rằng byte đã nén khác nhau ⇒ nội dung giải nén chắc chắn khác | Nhầm tầng biểu diễn dữ liệu | Giải nén và so dữ liệu logic khi đó là mục tiêu |

## 11. Câu hỏi tự kiểm tra

**1.** Dãy remaining `[10, 20, 30]` và `[10, 20, 99]` có kết quả gì?  
**Đáp án:** `2`, byte thứ ba khác nhau.

**2.** Dãy remaining `[7, 8]` và `[7, 8, 9]` có kết quả gì? Có được đọc byte ở offset `2` của buffer ngắn không?  
**Đáp án:** `2`; **không được**, vì bên ngắn đã hết dữ liệu, chỉ khác độ dài.

**3.** Buffer A bắt đầu ở `position=3`, B ở `position=10`. Nếu `mismatch` trả `2` (và cả hai remaining đều dài hơn `2`), byte khác đầu tiên nằm tại chỉ số tuyệt đối nào?  
**Đáp án:** A ở `3+2=5` và B ở `10+2=12`.

**4.** Hai buffer có dung lượng khác nhau, nhưng phần remaining giống nhau hoàn toàn. `mismatch` trả gì?  
**Đáp án:** `-1`; capacity không quyết định tính bằng nhau của phần remaining.

**5.** Sau khi `put(new byte[]{1,2,3})` vào buffer mới cấp phát, vì sao cần `flip()` trước `mismatch`?  
**Đáp án:** Vì `put` làm tăng position; `flip` đặt lại position về 0 và limit tới cuối phần vừa ghi, để so đúng ba byte đó.

## 12. Ghi nhớ

`ByteBuffer.mismatch(ByteBuffer)` có từ Java 11 và vẫn hữu ích hiện nay:

- **`-1`:** hai vùng remaining bằng nhau cả byte lẫn độ dài.
- **`i < minRemaining`:** offset tương đối của cặp byte khác đầu tiên.
- **`i == minRemaining`:** một vùng là tiền tố của vùng còn lại, khác độ dài.

Giá trị là **chỉ số tương đối so với position** của từng buffer. Muốn lấy offset tuyệt đối, cộng `position()`; muốn đọc byte tại điểm khác, kiểm tra index còn nằm trong `remaining()` ở **cả hai buffer**. Phương thức không sửa trạng thái vị trí/giới hạn và không giải mã, giải nén dữ liệu.

### Tài liệu chính thức

- [Java SE 11 — ByteBuffer.mismatch, Since: 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 26 — ByteBuffer API hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 26 — Buffer.position, limit và remaining](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/Buffer.html)
- [Java SE 26 — Arrays.mismatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
