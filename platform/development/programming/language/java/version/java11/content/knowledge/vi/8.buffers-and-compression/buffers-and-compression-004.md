# Buffer rỗng, prefix và độ dài khác nhau khi so sánh bằng `ByteBuffer.mismatch()` (Java 11)

## 1. Mục tiêu và tình huống

Trong ứng dụng xử lý tệp, gói tin, dữ liệu nhị phân hoặc kết quả nén, đôi khi cần tìm **vị trí đầu tiên hai chuỗi byte khác nhau**. Từ Java 11, `java.nio.ByteBuffer` cung cấp:

```java
int mismatch(ByteBuffer that)
```

Phương thức trả về **chỉ số tương đối của điểm khác nhau đầu tiên**, hoặc **`-1` khi hai chuỗi byte đang được so sánh giống nhau hoàn toàn**. Ba trường hợp dễ nhầm nhất là:

1. **Buffer rỗng**: không còn byte nào để đọc, dù bộ nhớ đã được cấp phát.
2. **Prefix**: tất cả byte của buffer ngắn hơn trùng với phần đầu của buffer dài hơn, nhưng vẫn còn byte thừa.
3. **Độ dài khác nhau**: khác độ dài chưa chắc trả ngay độ dài buffer ngắn hơn; nếu có byte khác sớm hơn thì kết quả là vị trí khác sớm nhất.

Bài này tập trung vào `ByteBuffer.mismatch(ByteBuffer)` và các trạng thái `position`, `limit`, `remaining` quyết định phạm vi so sánh. Quy tắc này vẫn được hỗ trợ trên các JDK hiện đại. Phương thức tương tự có trên các loại buffer nguyên thủy như `CharBuffer`, `IntBuffer` và `LongBuffer`; ở đây ví dụ dùng byte vì phù hợp dữ liệu nhị phân và nén.

Sau bài học, bạn có thể giải thích chính xác kết quả ở mọi trường hợp rỗng/prefix/khác chiều dài, chuyển chỉ số tương đối thành chỉ số tuyệt đối để đọc byte an toàn, sử dụng buffer đang có `position` khác 0, và phân biệt so sánh byte với so sánh nội dung sau giải nén.

## 2. “Rỗng” theo nghĩa `ByteBuffer` là gì?

Một `ByteBuffer` có các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capacity()` | Dung lượng phần tử tối đa của buffer, thường là cố định sau khi tạo |
| `position()` | Vị trí phần tử tiếp theo sẽ được đọc hoặc ghi theo thao tác tương đối |
| `limit()` | Mốc giới hạn trên của các vị trí được phép truy cập |
| `remaining()` | Số phần tử còn lại: `limit() - position()` |
| `hasRemaining()` | `remaining() > 0` |

Trong ngữ cảnh `mismatch()`, **buffer rỗng nghĩa là `remaining() == 0`**. Không cần `capacity()` bằng 0.

Ví dụ:

```java
ByteBuffer zeroCapacity = ByteBuffer.allocate(0);  // remaining = 0
ByteBuffer exhausted = ByteBuffer.wrap(new byte[] {1, 2});
exhausted.position(2);                              // remaining = 0

ByteBuffer fresh = ByteBuffer.allocate(2);          // remaining = 2
ByteBuffer emptyReadView = ByteBuffer.allocate(2);
emptyReadView.flip();                                // remaining = 0
```

Các dòng trên là **trích đoạn** đặt trong một phương thức, cần `import java.nio.ByteBuffer;`.

Điểm khác biệt quan trọng:

- `ByteBuffer.allocate(2)` vừa tạo có `position = 0`, `limit = 2` và `remaining = 2`. Dù chưa ghi byte nào, **nó không rỗng theo `remaining()`**; các phần tử của vùng mới cấp phát được khởi tạo bằng 0.
- Khi bạn ghi dữ liệu bằng `put(...)` rồi muốn đọc lại vùng vừa ghi, thông thường gọi `flip()`: `limit` trở thành `position` cũ và `position` trở về 0. Nếu chưa ghi gì và gọi `flip()`, vùng đọc có `remaining = 0`.
- `clear()` chuẩn bị buffer để ghi lại, **không xóa nội dung byte cũ**. Sau `clear()`, `remaining` có thể lớn hơn 0 dù dữ liệu trong vùng đó không phải dữ liệu hợp lệ để so sánh.
- `rewind()` đặt `position` về 0 nhưng giữ `limit` hiện tại. Cần hiểu trước đó `limit` đang đại diện vùng dữ liệu nào.

**Kết luận:** hãy so sánh **vùng dữ liệu hợp lệ, đã chuẩn bị cho chế độ đọc**. Nếu buffer đang ở chế độ ghi hoặc `limit` đặt sai, `mismatch()` có thể trả kết quả đúng theo trạng thái kỹ thuật nhưng sai với ý định nghiệp vụ.

## 3. Quy tắc chính xác của `mismatch()`

Với hai buffer `a` và `b`:

```java
int index = a.mismatch(b);
```

Phương thức xét lần lượt hai dãy **byte còn lại**:

- `a`: phần tử từ `a.position()` đến trước `a.limit()`.
- `b`: phần tử từ `b.position()` đến trước `b.limit()`.

Trả về:

1. **`i >= 0`** nếu phần tử ở độ lệch `i` đầu tiên khác nhau, với `0 <= i < min(a.remaining(), b.remaining())`.
2. Nếu mọi phần tử của vùng ngắn hơn đều bằng nhau **nhưng độ dài còn lại khác nhau**, trả `min(a.remaining(), b.remaining())`. Đây là trường hợp một vùng là **prefix đúng** của vùng còn lại.
3. Nếu mọi phần tử so sánh được đều bằng nhau **và độ dài còn lại cũng bằng nhau**, trả **`-1`**.

Có thể diễn đạt logic bằng mã giả:

```text
n = min(a.remaining(), b.remaining())
for i from 0 to n - 1:
    if a[positionA + i] != b[positionB + i]:
        return i
if a.remaining() != b.remaining():
    return n
return -1
```

Mã giả minh họa **ngữ nghĩa**, không phải mã triển khai nội bộ của JDK và không cần tự viết lại phương thức trong ứng dụng thông thường.

Đặc biệt, **`0` là kết quả “khác nhau tại vị trí đầu tiên” hoặc “chỉ một bên có dữ liệu”**, tuyệt đối không phải ký hiệu hai buffer bằng nhau. **Chỉ `-1` biểu thị không có khác biệt**.

## 4. Ma trận trường hợp rỗng, prefix và khác độ dài

Các chuỗi `"AB"`, `"ABC"` bên dưới biểu diễn **byte ASCII**, không phải `String` được so sánh trực tiếp. Mỗi chuỗi được đưa vào `ByteBuffer.wrap(bytes)` với `position = 0` và `limit = bytes.length`.

| Byte còn lại trong `a` | Byte còn lại trong `b` | `a.mismatch(b)` | Giải thích |
| --- | --- | --- | --- |
| `""` | `""` | `-1` | Cả hai rỗng, bằng nhau |
| `""` | `"A"` | `0` | Không có byte đầu tiên ở `a` |
| `"A"` | `""` | `0` | Không có byte đầu tiên ở `b` |
| `"ABC"` | `"ABC"` | `-1` | Toàn bộ byte và độ dài bằng nhau |
| `"ABC"` | `"XBC"` | `0` | Khác ở byte đầu |
| `"ABC"` | `"AXC"` | `1` | Khác ở byte thứ hai |
| `"ABC"` | `"ABX"` | `2` | Khác ở byte thứ ba |
| `"AB"` | `"ABC"` | `2` | `"AB"` là prefix của `"ABC"`; thiếu byte ở độ lệch 2 |
| `"ABC"` | `"AB"` | `2` | Prefix theo hướng ngược lại |
| `"ABC"` | `"AXYZ"` | `1` | Khác tại vị trí 1, **trước** khi xét khác độ dài |
| `"AB"` | `"AB"` | `-1` | Prefix chung cũng là toàn bộ nội dung của cả hai |

**Ba điểm cần nhớ từ bảng:**

- Hai buffer rỗng được coi là giống nhau, nên kết quả **`-1`**.
- Một buffer rỗng và một buffer có byte trả về **`0`**, vì độ dài chung lớn nhất có thể so sánh là 0, nhưng tổng độ dài khác nhau.
- Nếu `a` có 2 byte và `b` có 3 byte, cả hai bắt đầu bằng `"AB"`, `mismatch` là **`2`**. `2` là vị trí ngay sau dãy byte chung, **không tồn tại trong buffer ngắn**.

Ví dụ cuối rất quan trọng: khi kết quả là độ dài của prefix ngắn, bạn không thể gọi `get(position + index)` trên **cả hai buffer** mà không kiểm tra điều kiện; một bên sẽ truy cập tại `limit` và phát sinh `IndexOutOfBoundsException`.

## 5. Ví dụ Java 11 hoàn chỉnh, biên dịch và kiểm tra kết quả

Tạo tệp **`BufferMismatchEdgesDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferMismatchEdgesDemo {

    private static ByteBuffer ascii(String s) {
        return ByteBuffer.wrap(
                s.getBytes(StandardCharsets.US_ASCII));
    }

    private static void check(
            String label, ByteBuffer a, ByteBuffer b) {
        int difference = a.mismatch(b);
        System.out.println(label
                + ": remaining=" + a.remaining() + "/" + b.remaining()
                + ", mismatch=" + difference
                + ", equals=" + a.equals(b)
                + ", positions=" + a.position() + "/" + b.position());
    }

    public static void main(String[] args) {
        check("both-empty", ascii(""), ascii(""));
        check("left-empty", ascii(""), ascii("ABC"));
        check("right-empty", ascii("ABC"), ascii(""));
        check("identical", ascii("ABC"), ascii("ABC"));
        check("first-diff", ascii("ABC"), ascii("XBC"));
        check("middle-diff", ascii("ABC"), ascii("AXC"));
        check("short-prefix", ascii("AB"), ascii("ABC"));
        check("long-prefix", ascii("ABC"), ascii("AB"));
        check("diff-before-end", ascii("ABC"), ascii("AXYZ"));

        ByteBuffer window = ascii("!ABC?");
        window.position(1);
        window.limit(4);
        ByteBuffer expected = ascii("ABX");

        check("window", window, expected);
        int relativeIndex = window.mismatch(expected);
        int absoluteA = window.position() + relativeIndex;
        int absoluteB = expected.position() + relativeIndex;

        System.out.println("window first differing bytes: "
                + (char) (window.get(absoluteA) & 0xff)
                + "/"
                + (char) (expected.get(absoluteB) & 0xff));
        System.out.println("window indexes: relative="
                + relativeIndex + ", absolute="
                + absoluteA + "/" + absoluteB);

        ByteBuffer exhausted = ascii("Z");
        exhausted.position(exhausted.limit());
        check("exhausted", exhausted, ascii(""));

        ByteBuffer fresh = ByteBuffer.allocate(2);
        check("allocated", fresh, ascii(""));

        ByteBuffer flippedEmpty = ByteBuffer.allocate(2);
        flippedEmpty.flip();
        check("flipped-empty", flippedEmpty, ascii(""));
    }
}
```

Chạy bằng JDK 11 (hoặc JDK mới hơn có hỗ trợ `--release 11`):

```bash
javac --release 11 -encoding UTF-8 BufferMismatchEdgesDemo.java
java BufferMismatchEdgesDemo
```

**Kết quả chuẩn:**

```text
both-empty: remaining=0/0, mismatch=-1, equals=true, positions=0/0
left-empty: remaining=0/3, mismatch=0, equals=false, positions=0/0
right-empty: remaining=3/0, mismatch=0, equals=false, positions=0/0
identical: remaining=3/3, mismatch=-1, equals=true, positions=0/0
first-diff: remaining=3/3, mismatch=0, equals=false, positions=0/0
middle-diff: remaining=3/3, mismatch=1, equals=false, positions=0/0
short-prefix: remaining=2/3, mismatch=2, equals=false, positions=0/0
long-prefix: remaining=3/2, mismatch=2, equals=false, positions=0/0
diff-before-end: remaining=3/4, mismatch=1, equals=false, positions=0/0
window: remaining=3/3, mismatch=2, equals=false, positions=1/0
window first differing bytes: C/X
window indexes: relative=2, absolute=3/2
exhausted: remaining=0/0, mismatch=-1, equals=true, positions=1/0
allocated: remaining=2/0, mismatch=0, equals=false, positions=0/0
flipped-empty: remaining=0/0, mismatch=-1, equals=true, positions=0/0
```

**Giải thích từng nhóm kết quả:**

1. `both-empty`, `exhausted` và `flipped-empty` đều có hai dãy byte còn lại rỗng, nên `mismatch = -1` và `equals = true` dù `position` hoặc `capacity` không nhất thiết bằng nhau.
2. `left-empty` và `right-empty` trả `0`. Không cố đọc byte số 0 của buffer rỗng; chỉ nên giải thích đây là **khác độ dài tại biên đầu tiên**.
3. `identical` có ba byte và không khác vị trí nào, nên `-1`.
4. `first-diff`, `middle-diff` cho thấy chỉ số bắt đầu từ `0`. `diff-before-end` có độ dài 3 và 4 nhưng byte khác đã xuất hiện ở độ lệch 1, nên kết quả là **1 chứ không phải 3**.
5. `short-prefix` và `long-prefix` trả cùng **2**, chính là số byte còn lại của buffer ngắn hơn, vì hai byte `A`, `B` đều khớp.
6. `window` có capacity 5 nhưng `position = 1`, `limit = 4`; chỉ vùng `"ABC"` được so với `"ABX"`. Byte khác đầu tiên là `C`/`X` ở độ lệch tương đối 2, tương ứng chỉ số tuyệt đối 3/2.
7. `positions=1/0` sau `mismatch` cho thấy lời gọi **không tiêu thụ byte hoặc thay đổi `position`**. Đây là khác biệt với `get()` tương đối, vốn tăng `position`.
8. `allocated` minh họa vừa `allocate(2)` thì `remaining = 2`, không phải buffer rỗng. `flipped-empty` minh họa `flip()` khi chưa ghi gì làm vùng đọc trở thành rỗng.

Dữ liệu ASCII được chọn để mỗi ký tự tương ứng một byte dễ kiểm tra. Nếu chuyển `String` tiếng Việt sang UTF-8, một ký tự có thể chiếm nhiều byte; `mismatch` trên `ByteBuffer` tìm **vị trí byte**, không phải vị trí ký tự Unicode.

## 6. Truy cập byte tại vị trí mismatch một cách an toàn

Với kết quả `index = a.mismatch(b)`, cần phân biệt **ba nhánh**:

```java
static String describe(ByteBuffer a, ByteBuffer b) {
    int index = a.mismatch(b);

    if (index == -1) {
        return "Identical remaining bytes";
    }

    if (index >= a.remaining() || index >= b.remaining()) {
        return "One buffer is a proper prefix of the other";
    }

    int aByte = Byte.toUnsignedInt(
            a.get(a.position() + index));
    int bByte = Byte.toUnsignedInt(
            b.get(b.position() + index));

    return "Different bytes at relative index "
            + index + ": " + aByte + " vs " + bByte;
}
```

Đây là **phương thức minh họa đặt trong một lớp**, cần import `java.nio.ByteBuffer`. Nó không thay đổi `position` vì sử dụng `get(int)` tuyệt đối.

Với `a = "AB"` và `b = "ABC"`, `index = 2` bằng `a.remaining()`, nên phương thức trả thông báo prefix **trước khi gọi `get`**. Nếu cứ làm `a.get(a.position() + 2)` thì truy cập tại giới hạn của `a` và gây `IndexOutOfBoundsException`.

`Byte.toUnsignedInt` chuyển byte về số nguyên 0–255 để in giá trị nhị phân dễ hiểu. `ByteBuffer.get(int)` trả `byte` có dấu; bản thân `mismatch()` so sánh giá trị byte và không cần chuyển đổi này.

Nếu `index >= 0` nhưng nhỏ hơn cả hai `remaining()`, có byte thực sự khác nhau ở vị trí đó. Chỉ số tuyệt đối trong từng buffer là:

```text
absoluteIndexA = a.position() + index
absoluteIndexB = b.position() + index
```

Đừng gán `index` trực tiếp làm chỉ số tuyệt đối khi buffer có `position` khác 0. Đừng dùng `a.array()[index]` như cách chung: direct buffer hoặc read-only buffer có thể không cung cấp backing array truy cập được; buffer dạng slice còn có thể có offset khác 0.

## 7. Prefix không đồng nghĩa hoàn toàn bằng nhau

**Prefix** là quan hệ có hướng. Dãy byte `"AB"` là prefix của `"ABC"`; ngược lại `"ABC"` không phải prefix của `"AB"`. Trong khi đó, chỉ số `mismatch` khi hoán đổi hai buffer vẫn bằng 2 vì vị trí khác biệt đầu tiên là ranh giới sau prefix chung.

Nếu nghiệp vụ cần hỏi “`a` có là prefix của `b` không?”, cần kết hợp `remaining` và `mismatch`:

```java
static boolean isPrefix(ByteBuffer a, ByteBuffer b) {
    int aLength = a.remaining();
    int bLength = b.remaining();
    if (aLength > bLength) {
        return false;
    }
    int difference = a.mismatch(b);
    return difference == -1 || difference == aLength;
}
```

Đây là **phương thức minh họa** dành cho câu hỏi “`a` là prefix của `b`”, **bao gồm trường hợp hai dãy bằng nhau**. Nó trả:

| `a` | `b` | `isPrefix(a,b)` |
| --- | --- | --- |
| `""` | `""` | `true` |
| `""` | `"ABC"` | `true` |
| `"AB"` | `"ABC"` | `true` |
| `"ABC"` | `"AB"` | `false` |
| `"ABC"` | `"ABC"` | `true` |
| `"AX"` | `"ABC"` | `false` |

**Cần chú ý:** công thức trên có một trường hợp dễ nhầm. Nếu `a` và `b` có **cùng độ dài, nhưng byte cuối khác**, `mismatch` là `aLength - 1`, nên trả `false`; không nhầm với chỉ số `aLength` chỉ có thể xảy ra khi `a` là prefix đúng của vùng `b` dài hơn. Khi hai dãy bằng nhau hoàn toàn, `mismatch = -1`.

Nếu yêu cầu **prefix đúng** (ngắn hơn thực sự), thêm điều kiện `aLength < bLength`. Chuỗi rỗng là prefix theo định nghĩa toán học phổ biến, nhưng ứng dụng có thể cấm prefix rỗng tùy hợp đồng. Khi đó thêm kiểm tra `aLength > 0`.

**Không dùng riêng `mismatch == a.remaining()` khi muốn kiểm tra prefix có hướng mà bỏ qua điều kiện kích thước.** Chẳng hạn, nếu `a` dài hơn `b` và `b` là prefix của `a`, `mismatch` bằng `b.remaining()`; đó không chứng minh `a` là prefix của `b`.

## 8. Vị trí, giới hạn và cửa sổ dữ liệu

Một buffer vật lý có thể chứa cả header, payload và trailer. `mismatch()` chỉ dùng vùng đang hoạt động, nên không nhất thiết so sánh toàn bộ vùng lưu trữ.

Ví dụ (trích đoạn Java 11):

```java
ByteBuffer packet = ByteBuffer.wrap(new byte[] {
        9, 10, 11, 12, 99
});
packet.position(1);
packet.limit(4); // Dãy còn lại: [10, 11, 12]

ByteBuffer payload = ByteBuffer.wrap(new byte[] {
        10, 11, 12
});

System.out.println(packet.mismatch(payload)); // -1
System.out.println(packet.remaining());        // 3
```

Ở đây `packet.capacity() == 5`, nhưng đoạn so sánh chỉ có ba byte. Sau khi gọi `mismatch`, `packet.position()` vẫn là 1.

Một vài cách chuẩn bị phạm vi:

- **`duplicate()`** tạo view có trạng thái `position/limit` độc lập ban đầu nhưng chia sẻ nội dung byte. Có thể dùng để điều chỉnh vùng so sánh mà không thay đổi trạng thái đọc của caller.
- **`slice()`** tạo view tương ứng phần còn lại, có `position = 0` và `limit = remaining`, cũng chia sẻ bộ nhớ với buffer gốc. Khi làm việc với chỉ số tương đối của slice, cần hiểu chỉ số đã được tính từ đầu slice.
- **`asReadOnlyBuffer()`** cho view không được ghi qua reference đó, hữu ích khi muốn tránh sửa vô tình; tuy nhiên dữ liệu vẫn có thể bị thay đổi qua các reference khác đang dùng chung backing storage.
- **`flip()`** được dùng khi chuyển từ chế độ ghi sang đọc. `clear()` không phải thao tác làm rỗng dữ liệu; nó đặt trạng thái để ghi từ đầu.

Không cần tạo bản sao dữ liệu chỉ để chạy `mismatch`, nhưng nếu nội dung có thể bị sửa song song hoặc trong quá trình so sánh, kết quả có thể không phản ánh một snapshot nhất quán. Hãy quản lý ownership, tính bất biến hoặc snapshot khi độ chính xác yêu cầu.

## 9. So sánh `mismatch()`, `equals()` và `compareTo()`

Ba phương thức có mục đích khác nhau:

| Phương thức | Trả về | Dùng khi |
| --- | --- | --- |
| `a.mismatch(b)` | `-1` nếu giống nhau; ngược lại vị trí khác đầu tiên | Cần biết **khác tại đâu**, gồm chênh lệch do prefix/độ dài |
| `a.equals(b)` | `true` nếu hai dãy byte còn lại bằng nhau và cùng độ dài | Chỉ cần kiểm tra **có giống nhau không** |
| `a.compareTo(b)` | Số âm / 0 / số dương theo thứ tự từ điển trên các byte còn lại | Cần **thứ tự sắp xếp**, không cần vị trí khác đầu tiên |

Với `ByteBuffer`, hai buffer có `position` hoặc `capacity` khác nhau vẫn có thể `equals == true` nếu hai dãy byte từ `position` tới `limit` giống nhau. Khi không có thay đổi đồng thời, `a.mismatch(b) == -1` tương ứng với `a.equals(b)`.

Đối với `ByteBuffer.compareTo`, giá trị số âm hoặc dương chỉ biểu thị **thứ tự**, không phải vị trí byte khác nhau. Không dùng `compareTo` để tìm offset khác biệt. Ngược lại, không dùng `mismatch()` để suy ra thứ tự lớn/nhỏ, vì giá trị trả về là **index** chứ không phải dấu so sánh.

`Arrays.mismatch(byte[], byte[])` là API khác dùng trực tiếp cho mảng. Khi bạn đã có hai `ByteBuffer` (có `position/limit`), `ByteBuffer.mismatch` thường thuận tiện hơn việc sao chép toàn bộ mảng. Khi có hai `byte[]` độc lập và muốn so sánh từ phần tử đầu, `Arrays.mismatch` có thể là lựa chọn phù hợp.

## 10. Liên hệ với xử lý buffer và dữ liệu nén

`ByteBuffer.mismatch` chỉ đối chiếu **byte đang hiện diện trong hai view**. Nó **không giải nén**, không kiểm tra hợp lệ của dữ liệu nén, không hiểu record framing và không bảo đảm hai dữ liệu có cùng ý nghĩa nghiệp vụ.

Một số trường hợp thực tế:

- **Kiểm tra magic bytes/header:** đọc một đoạn byte đầu của tệp hoặc frame vào `ByteBuffer`, dùng `mismatch` hoặc kiểm tra có hướng để đối chiếu prefix kỳ vọng. Nếu dữ liệu ngắn hơn header, phải xử lý như **thiếu dữ liệu**, không cố đọc byte tại chỉ số `mismatch`.
- **So sánh hai payload:** nếu yêu cầu là **byte-for-byte** trong hai vùng đã chọn, `mismatch == -1` cho biết chúng trùng nhau. Nếu chỉ cần kiểm tra bản ghi có chung prefix, dùng logic kiểm tra prefix có hướng.
- **So sánh hai luồng byte sau nén:** hai luồng nén có thể tạo dữ liệu byte khác nhau vì cấp độ nén, cách đóng gói, metadata hoặc cách triển khai; việc chúng khác byte chưa đủ để kết luận nội dung gốc khác. Nếu cần kiểm tra **nội dung thực**, hãy giải nén bằng quy trình hợp lệ và so sánh nội dung sau giải nén theo yêu cầu.
- **Xử lý nhiều chunk:** một chunk cuối có thể ngắn hơn chunk còn lại. Khi gọi `mismatch` trên từng chunk, kết quả chỉ liên quan đến **vùng hiện tại**; phải giữ offset toàn cục và xử lý ranh giới chunk/EOF trước khi suy ra hai tệp giống nhau.

Không dùng `mismatch` làm cơ chế xác thực mật mã hoặc kiểm tra chữ ký/HMAC. Phương thức tìm vị trí khác đầu tiên có đặc tính thời gian phụ thuộc dữ liệu và không tạo ra bảo đảm bảo mật về việc so sánh token bí mật. Với dữ liệu bảo mật cần dùng quy trình xác thực mật mã và API phù hợp thay vì suy luận từ vị trí sai khác.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi `0` là kết quả bằng nhau | Kết luận sai trường hợp khác byte đầu hoặc chỉ một buffer rỗng | `-1` mới là giá trị “không mismatch” |
| Coi `capacity() == 0` mới là rỗng | Bỏ sót buffer `position == limit` | Dùng `remaining() == 0` |
| Xem `allocate(10)` như buffer chưa có dữ liệu để so sánh | So sánh 10 byte 0 đã cấp phát như thể là payload hợp lệ | Ghi dữ liệu rồi chuẩn bị vùng đọc bằng `flip()` |
| Gặp prefix thì gọi `get(position + mismatch)` trên hai buffer | Truy cập tại `limit` của buffer ngắn, gây `IndexOutOfBoundsException` | So `index` với cả hai `remaining()` trước |
| Luôn trả chiều dài ngắn hơn khi độ dài khác | Bỏ qua khác biệt sớm trong prefix | `mismatch` ưu tiên byte khác đầu tiên |
| Dùng index tương đối như index tuyệt đối | Đọc byte sai khi `position != 0` | Tính `position + index` cho mỗi buffer |
| Dùng `array()[index]` với mọi `ByteBuffer` | Direct/read-only/slice có thể không cho truy cập mảng hay có offset | Dùng `get(int)` trên view hợp lệ |
| Dùng `clear()` để xóa dữ liệu | Nội dung byte cũ vẫn còn; phạm vi `remaining` bị mở rộng | Hiểu `clear` chỉ đặt lại trạng thái để ghi |
| Tưởng `mismatch` thay đổi `position` | Làm sai logic xử lý packet phía sau | `mismatch` chỉ so sánh, không tiêu thụ byte |
| So sánh hai mảnh dữ liệu từ vị trí hoặc giới hạn không đúng | Kết quả không phản ánh payload cần so sánh | Chuẩn bị `position/limit` hoặc `slice` rõ ràng |
| Coi hai luồng nén khác byte là nội dung gốc khác | Kết luận sai về dữ liệu logic | So dữ liệu sau giải nén nếu yêu cầu theo nội dung |
| Dùng `mismatch` để xác thực token mật | Không có bảo đảm so sánh thời gian an toàn | Dùng primitive xác thực mật mã được thiết kế cho mục tiêu này |

## 12. Checklist kiểm thử trường hợp biên

Khi viết test cho chức năng so sánh buffer, tối thiểu nên có:

1. **Rỗng/rỗng:** hai `remaining = 0` nhưng `capacity/position` có thể khác; mong đợi `-1`.
2. **Rỗng/có dữ liệu theo cả hai hướng:** mong đợi `0`.
3. **Bằng nhau và cùng độ dài:** mong đợi `-1`.
4. **Khác ở byte đầu, giữa và cuối:** mong đợi lần lượt chỉ số 0, chỉ số giữa, chỉ số cuối.
5. **Prefix đúng theo cả hai hướng:** mong đợi độ dài phần còn lại của buffer ngắn hơn.
6. **Khác độ dài nhưng byte khác sớm:** mong đợi chỉ số khác sớm, không phải độ dài prefix tối đa.
7. **Có `position` khác 0:** mong đợi chỉ số tương đối chính xác; sau lời gọi `position` vẫn giữ nguyên.
8. **Buffer vừa cấp phát, buffer sau `flip`, buffer đã đọc hết:** xác nhận đúng `remaining`.
9. **Slice/direct/read-only:** kiểm tra trên vùng còn lại thay vì suy luận từ `array()`.
10. **Tác động nghiệp vụ:** nếu so sánh tệp hoặc luồng nén thì kiểm tra cả ranh giới chunk, EOF và nội dung sau giải nén khi cần.

## 13. Bài luyện tập

**Bài 1.** `a` có dãy còn lại `"CAT"`, `b` có `"CATER"`. Kết quả `a.mismatch(b)` là bao nhiêu?

**Đáp án:** **`3`**. Ba byte đầu trùng nhau; ở độ lệch 3, `a` đã hết còn `b` còn byte `E`.

**Bài 2.** `a` có `"CAT"`, `b` có `"CXR"`. Kết quả?

**Đáp án:** **`1`**. Khác tại byte thứ hai `A`/`X`.

**Bài 3.** `a` có `position = limit = 5`, `b` có `position = limit = 0`. Dung lượng hai buffer có thể khác nhau. Kết quả?

**Đáp án:** **`-1`**, vì cả hai đều còn 0 byte; `mismatch` không xét phần dữ liệu ngoài cửa sổ còn lại.

**Bài 4.** `a` còn 0 byte, `b` còn 7 byte. Có được gọi `a.get(a.position() + a.mismatch(b))` không?

**Đáp án:** **Không**. `mismatch` trả 0, nhưng `a.position() == a.limit()` nên không có byte nào tại chỉ số đó.

**Bài 5.** `a` còn `"ABCD"` nhưng `position = 2`; `b` còn `"ABXD"` nhưng `position = 5`. Nếu byte đầu tiên khác tại độ lệch 2 trong hai cửa sổ, chỉ số tuyệt đối để đọc trong từng buffer là bao nhiêu?

**Đáp án:** **4 đối với `a` và 7 đối với `b`**. `mismatch` trả chỉ số tương đối 2; truy cập tuyệt đối phải cộng `position` của từng buffer.

**Bài 6.** Một buffer có `capacity = 100`, `position = 40`, `limit = 40`. Nó có được xem là rỗng trong `mismatch` không?

**Đáp án:** **Có**, vì `remaining = 0`; không xét 100 byte mà buffer có khả năng lưu trữ.

## 14. Ghi nhớ và tài liệu tham khảo

- Trong Java 11, `ByteBuffer.mismatch` so sánh **hai dãy byte còn lại** giữa `position` và `limit`.
- `-1` là **hoàn toàn bằng nhau**, kể cả rỗng/rỗng; `0` là khác ở byte đầu hoặc một bên rỗng.
- Nếu một bên là **prefix đúng**, kết quả bằng `min(remainingA, remainingB)`; chỉ số này **không hợp lệ trên buffer ngắn hơn**.
- Nếu có byte khác sớm hơn, phương thức trả chỉ số khác đầu tiên, **không** tự động trả độ dài của buffer ngắn.
- Chỉ số trả về là **tương đối**; để đọc byte sử dụng `get(position + index)` sau khi chắc rằng `index < remaining` trên cả hai.
- `capacity` không định nghĩa vùng so sánh; `position/limit/remaining` mới là trạng thái quan trọng.
- Kết quả so sánh byte không tự chứng minh nội dung đã giải nén, hợp lệ về cấu trúc hoặc có xác thực mật mã.

Tài liệu API chính thức, vẫn phù hợp:

- [`ByteBuffer` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html): `mismatch` (Since: 11), `equals`, `compareTo`, `slice`, `duplicate` và trạng thái buffer.
- [`Buffer` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/Buffer.html): `position`, `limit`, `remaining`, `clear`, `flip` và `rewind`.
- [`CharBuffer` — Java SE 11](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/CharBuffer.html): ví dụ một loại buffer khác có `mismatch` từ Java 11.
- [`ByteBuffer` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): đối chiếu việc API tiếp tục được hỗ trợ trên JDK hiện đại.
