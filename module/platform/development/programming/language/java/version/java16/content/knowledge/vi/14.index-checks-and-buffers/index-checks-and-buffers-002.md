# Objects.checkFromToIndex với long và khoảng nửa mở

## 1. Khoảng nửa mở là gì?

Khi xử lý một đoạn dữ liệu, Java thường mô tả phạm vi bằng hai mốc: vị trí bắt đầu được lấy và vị trí kết thúc không được lấy. Đây là khoảng nửa mở, viết dưới dạng `[from, to)`.

Ví dụ, khoảng `[3, 7)` chứa các vị trí `3`, `4`, `5` và `6`. Vị trí `7` là cận trên nên không thuộc phạm vi. Số phần tử trong khoảng là `to - from`, trong ví dụ này bằng `4`.

Từ Java 16, `java.util.Objects` có overload `checkFromToIndex(long, long, long)` để xác thực một khoảng có các mốc kiểu `long`:

~~~java
import java.util.Objects;

long length = 5_000_000_000L;
long from = 2_000_000_000L;
long to = 2_000_000_128L;

long checkedFrom = Objects.checkFromToIndex(from, to, length);
long rangeLength = to - checkedFrom;
~~~

Nếu khoảng hợp lệ, phương thức trả về `fromIndex`. Nếu khoảng nằm ngoài độ dài, nó ném `IndexOutOfBoundsException`.

Overload này hữu ích với offset tệp, dữ liệu phân đoạn hoặc abstraction có không gian chỉ số kiểu `long`. Nó không làm mảng Java hoặc `ByteBuffer` hỗ trợ index `long`; giới hạn của cấu trúc được truy cập vẫn do API đó quyết định.

Mục tiêu bài học:

- Hiểu ý nghĩa của khoảng nửa mở `[from, to)`.
- Dùng `Objects.checkFromToIndex(long, long, long)` để xác thực phạm vi.
- Xử lý đúng cận trên, khoảng rỗng và các trường hợp biên.
- Phân biệt `checkFromToIndex` với `checkIndex` và `checkFromIndexSize`.
- Áp dụng kiểm tra khoảng cho offset lớn và dữ liệu kiểu `long`.
- Tránh lỗi off-by-one và phép tính phạm vi không an toàn.

## 2. Cú pháp và điều kiện hợp lệ

Chữ ký overload long:

~~~java
long Objects.checkFromToIndex(
    long fromIndex,
    long toIndex,
    long length
)
~~~

Một khoảng hợp lệ phải thỏa mãn:

\[
0 \le fromIndex \le toIndex \le length
\]

Trong đó:

- `fromIndex` là vị trí bắt đầu, được bao gồm.
- `toIndex` là cận trên, không được bao gồm.
- `length` là số lượng phần tử hoặc độ dài logic của vùng dữ liệu.
- Giá trị trả về là `fromIndex` nếu mọi điều kiện hợp lệ.

Ví dụ, nếu `length = 10`:

- `[0, 10)` bao phủ toàn bộ mười vị trí.
- `[2, 5)` bao gồm vị trí 2, 3 và 4.
- `[9, 10)` chỉ bao gồm vị trí 9.
- `[10, 10)` là khoảng rỗng hợp lệ ở cuối vùng dữ liệu.

Các trường hợp sau không hợp lệ:

- `fromIndex < 0`.
- `toIndex < fromIndex`.
- `toIndex > length`.
- `length < 0`.

Nếu khoảng không hợp lệ, phương thức ném `IndexOutOfBoundsException`. Không nên dựa vào nội dung message cụ thể của exception vì đó không phải hợp đồng ổn định để ứng dụng phân tích.

## 3. Cận trên không được bao gồm

Điểm dễ nhầm nhất của `checkFromToIndex` là `toIndex` không phải vị trí cuối cùng được xử lý.

Với `from = 3` và `to = 7`:

~~~text
Vị trí:   0   1   2   3   4   5   6   7   8   9
                    [--- phạm vi ---)
                    ^               ^
                 from = 3         to = 7
~~~

Các vị trí được lấy là 3, 4, 5, 6. Vị trí 7 nằm ngoài khoảng.

Quy ước này có một số lợi ích:

- Độ dài khoảng tính bằng phép trừ đơn giản: `to - from`.
- Hai khoảng liền kề có thể ghép mà không chồng lặp: `[0, 4)` và `[4, 8)`.
- Khoảng rỗng được biểu diễn tự nhiên bằng `from == to`.
- Cận trên có thể bằng `length`, nên có thể biểu diễn phạm vi đến hết dữ liệu mà không cần tính chỉ số cuối cùng là `length - 1`.

Ví dụ hai khoảng liền nhau:

~~~java
long firstStart = Objects.checkFromToIndex(0L, 4L, 8L);
long secondStart = Objects.checkFromToIndex(4L, 8L, 8L);

long firstLength = 4L - firstStart;   // 4
long secondLength = 8L - secondStart; // 4
~~~

Hai phạm vi `[0, 4)` và `[4, 8)` không có phần tử chung, cũng không bỏ sót vị trí nào trong `[0, 8)`.

## 4. Khoảng rỗng và trường hợp from bằng to

Khoảng nửa mở cho phép `fromIndex == toIndex`. Đây là khoảng rỗng, có độ dài bằng 0.

~~~java
long start = Objects.checkFromToIndex(4L, 4L, 10L);
long count = 4L - start;

System.out.println(start); // 4
System.out.println(count); // 0
~~~

Khoảng rỗng có thể xuất hiện khi:

- Một trang dữ liệu không có phần tử.
- Người dùng chọn vùng không có nội dung.
- Một thao tác xử lý không cần đọc byte nào.
- Một đoạn nằm ngay trước hoặc sau một đoạn khác.

Đặc biệt, khoảng rỗng ở cuối vùng dữ liệu là hợp lệ:

~~~java
long end = Objects.checkFromToIndex(10L, 10L, 10L);
~~~

Kết quả là `10`. Điều này không có nghĩa index 10 là một phần tử hợp lệ. Nó chỉ là vị trí kết thúc của một khoảng rỗng ngay sau phần tử cuối cùng.

So sánh:

~~~java
Objects.checkFromToIndex(10L, 10L, 10L); // Hợp lệ: khoảng rỗng.
Objects.checkIndex(10L, 10L);            // Không hợp lệ: không có phần tử index 10.
~~~

Vì vậy, hãy chọn phương thức theo ý nghĩa thao tác: kiểm tra một phần tử hay kiểm tra một khoảng.

## 5. Ví dụ kiểm tra các trường hợp biên

Bảng sau giả sử `length = 10`:

| fromIndex | toIndex | Kết quả | Giải thích |
| ---: | ---: | --- | --- |
| 0 | 10 | Hợp lệ | Bao phủ toàn bộ vùng. |
| 0 | 0 | Hợp lệ | Khoảng rỗng ở đầu. |
| 3 | 7 | Hợp lệ | Bao gồm 3, 4, 5, 6. |
| 10 | 10 | Hợp lệ | Khoảng rỗng ở cuối. |
| 9 | 10 | Hợp lệ | Chỉ bao gồm phần tử cuối cùng. |
| -1 | 2 | Không hợp lệ | Cận dưới âm. |
| 4 | 3 | Không hợp lệ | Cận trên nhỏ hơn cận dưới. |
| 0 | 11 | Không hợp lệ | Cận trên vượt độ dài. |
| 11 | 11 | Không hợp lệ | Cả hai mốc đều vượt độ dài. |

Có thể kiểm tra trực tiếp:

~~~java
import java.util.Objects;

class BoundaryDemo {
    static void check(long from, long to, long length) {
        try {
            long start = Objects.checkFromToIndex(from, to, length);
            System.out.printf(
                "[%d, %d) hợp lệ, số phần tử = %d%n",
                start,
                to,
                to - start
            );
        } catch (IndexOutOfBoundsException ex) {
            System.out.printf(
                "[%d, %d) không hợp lệ với length = %d%n",
                from,
                to,
                length
            );
        }
    }

    public static void main(String[] args) {
        check(0, 10, 10);
        check(10, 10, 10);
        check(4, 3, 10);
        check(0, 11, 10);
    }
}
~~~

Bắt exception để báo lỗi đầu vào ở ranh giới phù hợp. Nếu khoảng không hợp lệ là lỗi lập trình hoặc vi phạm invariant nội bộ, có thể để exception truyền lên thay vì bắt rồi tiếp tục.

## 6. Dùng overload long từ Java 16

Overload nhận `long` cho phép xác thực mốc lớn hơn miền của `int`:

~~~java
import java.util.Objects;

class LongRangeDemo {
    public static void main(String[] args) {
        long logicalLength = 12_000_000_000L;

        long from = 8_000_000_000L;
        long to = 8_000_001_024L;

        long start = Objects.checkFromToIndex(
            from,
            to,
            logicalLength
        );

        System.out.println(start);        // 8000000000
        System.out.println(to - start);   // 1024
    }
}
~~~

Nếu ép các mốc này về `int` trước khi kiểm tra, các bit cao có thể bị mất và làm thay đổi giá trị. Do đó, hãy giữ mốc ở kiểu `long` trong toàn bộ bước xác thực.

Cần hiểu giới hạn: phương thức chỉ xác nhận mối quan hệ giữa ba số `long`. Nó không tự cung cấp cấu trúc dữ liệu có khả năng đọc/ghi tại mọi vị trí đó.

Ví dụ:

- `FileChannel` hỗ trợ vị trí tệp kiểu `long`.
- Một abstraction lưu trữ phân đoạn có thể định nghĩa offset logic kiểu `long`.
- Mảng Java vẫn dùng index kiểu `int`.
- `ByteBuffer` vẫn dùng position, limit và capacity kiểu `int`.

## 7. So sánh checkFromToIndex với checkIndex và checkFromIndexSize

Ba phương thức giải quyết các dạng kiểm tra khác nhau:

| Phương thức | Đầu vào | Ý nghĩa |
| --- | --- | --- |
| `checkIndex(index, length)` | Một index và length | Xác thực một phần tử: `0 <= index < length`. |
| `checkFromToIndex(from, to, length)` | Hai mốc và length | Xác thực khoảng nửa mở: `0 <= from <= to <= length`. |
| `checkFromIndexSize(from, size, length)` | Mốc bắt đầu, số lượng và length | Xác thực một vùng có kích thước xác định. |

Nếu biết hai đầu mút, dùng `checkFromToIndex`:

~~~java
long start = Objects.checkFromToIndex(from, to, length);
long size = to - start;
~~~

Nếu biết điểm bắt đầu và số lượng, dùng `checkFromIndexSize`:

~~~java
long start = Objects.checkFromIndexSize(from, size, length);
~~~

Với dữ liệu hợp lệ, `checkFromIndexSize(from, size, length)` biểu diễn cùng một vùng với `checkFromToIndex(from, from + size, length)`. Tuy nhiên, đừng tự tính `from + size` trước khi xác thực vì phép cộng có thể overflow. Dùng trực tiếp overload phù hợp với dạng đầu vào đang có.

Nếu chỉ cần truy cập một phần tử, dùng `checkIndex`. Đừng dùng range check cho một index đơn lẻ chỉ vì muốn nhận lại cùng một kiểu trả về.

## 8. Ứng dụng với offset của FileChannel

Một tệp có kích thước kiểu `long`. Khi xử lý một đoạn byte trong tệp, có thể xác thực hai đầu mút trước khi thực hiện thao tác I/O:

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.util.Objects;

class FileRange {
    static long checkedLength(
            FileChannel channel,
            long from,
            long to
    ) throws IOException {

        long fileSize = channel.size();
        long checkedFrom = Objects.checkFromToIndex(from, to, fileSize);

        return to - checkedFrom;
    }
}
~~~

Ở đây:

1. `channel.size()` trả về kích thước tệp dưới dạng `long`.
2. `checkFromToIndex` xác thực khoảng `[from, to)` nằm trong kích thước hiện tại.
3. Giá trị trả về là cận dưới đã xác thực.
4. `to - checkedFrom` là số byte của phạm vi.

Nếu cần đọc dữ liệu, có thể dùng vị trí bắt đầu và độ dài đã xác thực để điều khiển vòng lặp đọc theo từng buffer nhỏ. `FileChannel.read(buffer, position)` nhận offset tệp kiểu `long`, trong khi `ByteBuffer` chỉ chứa một lượng dữ liệu hữu hạn với capacity kiểu `int`.

Kiểm tra phạm vi không đảm bảo lần đọc sẽ trả đủ byte. File có thể bị rút ngắn sau bước kiểm tra, thao tác đọc có thể gặp EOF hoặc chỉ đọc được một phần. Ứng dụng cần xử lý partial read và lỗi I/O theo yêu cầu nghiệp vụ.

## 9. Xử lý range trong một abstraction có index long

Không phải mọi cấu trúc dữ liệu đều là array. Một abstraction có thể công bố độ dài và thao tác đọc theo chỉ số `long`:

~~~java
import java.util.Objects;

interface LongIndexedBytes {
    long length();
    byte get(long index);
}

class RangeProcessor {
    static long sum(
            LongIndexedBytes data,
            long from,
            long to
    ) {
        long start = Objects.checkFromToIndex(
            from,
            to,
            data.length()
        );

        long total = 0;
        for (long index = start; index < to; index++) {
            total += data.get(index);
        }
        return total;
    }
}
~~~

Phương thức kiểm tra khoảng một lần trước khi lặp. Điều kiện vòng lặp `index < to` giữ đúng quy ước cận trên không bao gồm.

Trong một triển khai thực tế, `LongIndexedBytes.get()` phải bảo đảm chính nó truy cập dữ liệu đúng cách, ví dụ ánh xạ index logic sang segment và offset cục bộ. `checkFromToIndex` xác thực khoảng ở lớp abstraction, không thay thế kiểm tra nội bộ của cấu trúc lưu trữ nếu phép ánh xạ có thêm giới hạn riêng.

## 10. Tránh lỗi off-by-one khi chia và ghép khoảng

Khi chia một vùng thành các đoạn nhỏ, hãy giữ thống nhất quy ước nửa mở.

Ví dụ chia `[0, 10)` thành hai đoạn:

~~~java
long firstFrom = 0;
long firstTo = 5;

long secondFrom = 5;
long secondTo = 10;

Objects.checkFromToIndex(firstFrom, firstTo, 10);
Objects.checkFromToIndex(secondFrom, secondTo, 10);
~~~

Hai đoạn là `[0, 5)` và `[5, 10)`. Chúng không trùng phần tử và ghép lại đúng thành `[0, 10)`.

Các lỗi thường gặp:

- Dùng `to - 1` làm cận trên khi gọi `checkFromToIndex`, khiến bỏ sót phần tử cuối.
- Dùng `to` như một index cần đọc, dù nó là cận trên không bao gồm.
- Dùng điều kiện vòng lặp `index <= to` thay vì `index < to`.
- Cộng thêm 1 vào cận trên để “bao gồm” phần tử cuối, gây overflow khi cận trên đã ở giới hạn lớn.
- Tính `length - 1` mà không xử lý trường hợp length bằng 0.

Nếu nguồn dữ liệu biểu diễn phạm vi bằng chỉ số đầu và chỉ số cuối *bao gồm*, hãy chuyển đổi cẩn thận sang khoảng nửa mở. Khi chỉ số cuối là `inclusiveEnd`, cận trên thường là `inclusiveEnd + 1`; phép cộng này phải được bảo vệ nếu có thể đạt `Long.MAX_VALUE`. Trong nhiều API, tốt hơn là lưu và truyền trực tiếp cặp `[from, to)` để không phải chuyển đổi qua lại.

## 11. Những lỗi thường gặp và cách khắc phục

1. **Coi `toIndex` là vị trí cuối được lấy:** đây là cận trên không bao gồm. Dùng vòng lặp `index < toIndex`.
2. **Từ chối khoảng rỗng:** `from == to` là hợp lệ nếu vị trí nằm trong `[0, length]`.
3. **Cho rằng `length` là một index phần tử:** `length` chỉ có thể làm cận trên; nó không hợp lệ cho `checkIndex`.
4. **Dùng `checkIndex` để xác thực đoạn:** chọn `checkFromToIndex` khi đã biết cả hai đầu mút.
5. **Tự tính `from + size` trước khi kiểm tra:** có thể overflow; dùng `checkFromIndexSize`.
6. **Ép mốc `long` về `int` quá sớm:** giữ `long` trong bước kiểm tra và chỉ thu hẹp khi API đích yêu cầu, sau khi đã chứng minh giá trị nằm trong miền `int`.
7. **Nhầm long overload mở rộng giới hạn array:** nó chỉ xác thực số kiểu `long`; array vẫn có giới hạn riêng.
8. **Cho rằng kiểm tra range bảo đảm I/O hoàn tất:** cần xử lý partial read, EOF và lỗi I/O.
9. **Dùng điều kiện vòng lặp đóng ở cận trên:** với khoảng `[from, to)`, điều kiện đúng là `index < to`.
10. **Phụ thuộc vào message của exception:** chỉ dựa vào loại exception và điều kiện hợp lệ được API quy định.

## 12. Bài tập thực hành

1. Viết method nhận `long from`, `long to`, `long length`; trả về độ dài sau khi xác thực bằng `Objects.checkFromToIndex`.
2. Với `length = 12`, xác định khoảng nào hợp lệ: `[0, 12)`, `[12, 12)`, `[11, 12)`, `[12, 13)`, `[5, 4)`.
3. Giải thích vì sao `[length, length)` hợp lệ nhưng `checkIndex(length, length)` không hợp lệ.
4. Chia khoảng `[0, 100)` thành bốn đoạn liên tiếp có độ dài bằng nhau. Xác thực từng đoạn và chứng minh không có phần tử bị trùng hoặc bỏ sót.
5. So sánh `checkFromToIndex(4, 9, 20)` với `checkFromIndexSize(4, 5, 20)`.
6. Viết method xác thực khoảng byte trong một `FileChannel` bằng `channel.size()`.
7. Tìm và sửa lỗi off-by-one trong vòng lặp `for (long i = from; i <= to; i++)`.
8. Giải thích vì sao không nên chuyển một cặp `[from, inclusiveEnd]` sang `[from, inclusiveEnd + 1)` mà không xem xét overflow.

## Ghi nhớ

`Objects.checkFromToIndex(long, long, long)` được bổ sung trong Java 16 để xác thực một khoảng nửa mở bằng các mốc kiểu `long`. Điều kiện hợp lệ là `0 <= fromIndex <= toIndex <= length`; cận dưới được bao gồm, cận trên không được bao gồm. Phương thức trả về `fromIndex` nếu hợp lệ và ném `IndexOutOfBoundsException` nếu không hợp lệ. Khoảng rỗng được phép, kể cả `[length, length)`, nhưng `length` không phải index của một phần tử. Dùng `checkFromToIndex` khi đã có hai đầu mút, `checkFromIndexSize` khi biết điểm bắt đầu và số lượng, còn `checkIndex` khi kiểm tra một phần tử. Giữ quy ước nửa mở xuyên suốt vòng lặp và thao tác chia đoạn để tránh off-by-one. Overload long hữu ích cho offset tệp và abstraction dữ liệu lớn, nhưng không mở rộng giới hạn của array hoặc `ByteBuffer`.

**Tài liệu tham khảo chính thức:**

- [Java 16 API – Objects.checkFromToIndex(long, long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromToIndex(long,long,long))
- [Java 16 API – Objects.checkFromIndexSize(long, long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkFromIndexSize(long,long,long))
- [Java 16 API – Objects.checkIndex(long, long)](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/Objects.html#checkIndex(long,long))
- [Java 16 API – FileChannel](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/nio/channels/FileChannel.html)
