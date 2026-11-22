# StringBuilder: charAt, setCharAt, substring và subSequence

## 1. Đọc, sửa tại chỗ và lấy ra một đoạn là ba việc khác nhau

`StringBuilder` là vùng văn bản có thể thay đổi. Khi đang xây dựng một chuỗi, đôi lúc ta cần kiểm tra một vị trí, sửa một dấu phân cách, hoặc lấy riêng một phần để gửi sang bước xử lý tiếp theo. Bốn phương thức trong bài giải quyết các nhu cầu đó:

- `charAt(index)`: đọc một giá trị `char`.
- `setCharAt(index, ch)`: thay giá trị `char` đang có tại một vị trí.
- `substring(start, end)`: lấy một đoạn dưới dạng `String`.
- `subSequence(start, end)`: lấy một đoạn qua kiểu trả về `CharSequence`.

Điểm cần phân biệt trước khi viết mã: chỉ `setCharAt` sửa nội dung của builder. Các phương thức còn lại đọc dữ liệu hoặc tạo kết quả trích xuất; chúng không xóa đoạn vừa lấy khỏi builder.

Bài dùng cú pháp và API chạy được trên Java 17 trở lên. Tên module Java 5 chỉ ngữ cảnh giới thiệu `StringBuilder`; các cách dùng dưới đây vẫn phù hợp với Java hiện nay.

## 2. Hợp đồng phương thức và miền chỉ số

Giả sử `n = sb.length()` tại thời điểm thao tác:

| Phương thức | Kết quả | Chỉ số hợp lệ | Sửa builder? |
| --- | --- | --- | --- |
| `charAt(i)` | `char` | `0 <= i < n` | Không |
| `setCharAt(i, ch)` | `void` | `0 <= i < n` | Có, một đơn vị UTF-16 |
| `substring(start)` | `String` | `0 <= start <= n` | Không |
| `substring(start, end)` | `String` | `0 <= start <= end <= n` | Không |
| `subSequence(start, end)` | `CharSequence` | `0 <= start <= end <= n` | Không |

Với truy cập một phần tử, `n` nằm ngoài phạm vi. Với lấy một đoạn, `n` được phép dùng làm mốc kết thúc hoặc làm điểm bắt đầu của đoạn rỗng.

Nếu vi phạm miền chỉ số, `charAt`, `setCharAt` và `subSequence` quy định `IndexOutOfBoundsException`; các overload `substring` quy định `StringIndexOutOfBoundsException`, vốn là lớp con của `IndexOutOfBoundsException`. Khi kiểm tra lỗi, không phụ thuộc vào nội dung thông báo ngoại lệ hoặc lớp con cụ thể mà một phiên bản JDK tình cờ ném ra.

Các chữ ký và điều kiện biên có thể đối chiếu tại [Java API: StringBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#charAt(int)).

### 2.1. Hiểu khoảng nửa mở [start, end)

Với văn bản `"order=paid"`:

```text
Chỉ số:  0 1 2 3 4 5 6 7 8 9
char:    o r d e r = p a i d
```

`substring(6, 10)` lấy các vị trí 6, 7, 8, 9: kết quả là `"paid"`. Giá trị 10 là ranh giới dừng, không phải vị trí được đọc.

Độ dài đoạn là `end - start`. Muốn lấy `count` đơn vị UTF-16 từ `start`, mốc cuối là `start + count`, sau khi đã kiểm tra phép tính và giới hạn. Tham số thứ hai của `substring` không phải số lượng phần tử.

Quy ước này giúp ghép các khoảng liền nhau: `[0, 6)` và `[6, 10)` không lặp phần tử tại vị trí 6.

## 3. charAt: kiểm tra một vị trí mà không sửa dữ liệu

`charAt` phù hợp khi cần xem dấu phân cách, ký tự chữ số ASCII hoặc dấu kết thúc đã biết vị trí.

Đoạn sau minh họa bên trong một phương thức:

```java
StringBuilder line = new StringBuilder("level=3;");
char last = line.charAt(line.length() - 1);
boolean terminated = last == ';';
```

Biến `last` có giá trị `';'`, còn `terminated` là `true`. Nội dung `line` vẫn là `"level=3;"`.

Nếu builder có thể rỗng, phải xử lý trường hợp đó trước:

```java
StringBuilder line = new StringBuilder();
boolean terminated = line.length() > 0
        && line.charAt(line.length() - 1) == ';';
```

Ở đây phép `&&` đánh giá ngắn mạch: vế phải không chạy khi độ dài bằng 0. Không có lần truy cập `charAt(-1)`.

Không dùng `capacity()` làm giới hạn duyệt. Dung lượng dự trữ chưa trở thành nội dung; một builder rỗng vẫn không có phần tử nào để đọc dù nó có sức chứa lớn.

## 4. setCharAt: thay đúng một đơn vị UTF-16 đang tồn tại

`setCharAt` thay tại chỗ và không thay đổi `length()`. Ví dụ minh họa:

```java
StringBuilder code = new StringBuilder("AB-123");
code.setCharAt(2, ':');
// code có nội dung "AB:123", length() vẫn bằng 6.
```

Đây là thay dấu `'-'` đang có, không chèn dấu mới và không dời các vị trí phía sau.

Những giới hạn cần nhớ:

- `setCharAt(sb.length(), ch)` không có nghĩa là thêm vào cuối; vị trí đó chưa tồn tại. Dùng `append(ch)` khi cần thêm.
- Tham số thứ hai là một `char`, chẳng hạn `':'`, không phải một `String` như `":"`.
- Phương thức trả về `void`. Không viết `sb.setCharAt(0, 'X').append("!")`.
- Nếu cần thay một đoạn bằng văn bản dài hoặc ngắn hơn, dùng thao tác theo khoảng như `replace`; không cố biểu diễn cả chuỗi bằng một `char`.

Biến khác trỏ tới cùng builder sẽ thấy thay đổi. Ngược lại, một `String` đã được lấy ra trước đó giữ nội dung của nó; ví dụ hoàn chỉnh ở phần tiếp theo làm rõ sự khác biệt này.

## 5. substring và subSequence: lấy một phần mà không tạo liên kết cập nhật

`substring(start)` lấy từ `start` đến cuối. `substring(start, end)` lấy đúng khoảng chỉ định. Cả hai trả về `String`.

`subSequence(start, end)` có kiểu trả về được khai báo là `CharSequence`, nhờ đó dùng được trong các API chỉ cần khả năng đọc một chuỗi ký tự. Riêng với `StringBuilder`, hợp đồng của phương thức này tương đương `substring(start, end)`: kết quả không phải một cửa sổ luôn theo dõi builder. Thay builder sau khi trích xuất không cập nhật đoạn đã nhận. Xem [hợp đồng subSequence của StringBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#subSequence(int,int)).

Ví dụ dưới đây là chương trình độc lập, lưu thành `BuilderAccessDemo.java`:

```java
public class BuilderAccessDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("order=paid");

        System.out.println("first=" + sb.charAt(0));
        System.out.println("last=" + sb.charAt(sb.length() - 1));

        String prefix = sb.substring(0, 5);
        String suffix = sb.substring(6);
        CharSequence part = sb.subSequence(6, 10);

        sb.setCharAt(0, 'O');
        sb.setCharAt(6, 'P');

        System.out.println("builder=" + sb);
        System.out.println("prefix=" + prefix);
        System.out.println("suffix=" + suffix);
        System.out.println("part=" + part);
        System.out.println("length=" + sb.length());
        System.out.println("empty=[" + sb.substring(sb.length()) + "]");
        System.out.println("rangeLength=" + sb.substring(2, 5).length());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 BuilderAccessDemo.java
java BuilderAccessDemo
```

Stdout:

```text
first=o
last=d
builder=Order=Paid
prefix=order
suffix=paid
part=paid
length=10
empty=[]
rangeLength=3
```

Ta đã sửa vị trí 0 và 6, nên builder thành `"Order=Paid"`. Ba kết quả đã trích xuất vẫn giữ chữ thường. Đồng thời, lấy đoạn không làm builder ngắn đi: độ dài cuối cùng vẫn là 10.

### 5.1. CharSequence là kiểu giao tiếp, không phải cam kết bất biến chung

Trong đoạn minh họa sau, biến `source` vẫn trỏ tới builder:

```java
StringBuilder sb = new StringBuilder("cat");
CharSequence source = sb;
CharSequence extracted = sb.subSequence(0, 3);
sb.setCharAt(0, 'b');
// source đọc được "bat"; extracted vẫn là "cat".
```

Khai báo kiểu `CharSequence` không tự tạo bản sao và không ngăn đối tượng gốc thay đổi. Kết quả ổn định ở `extracted` là hành vi của `StringBuilder.subSequence`, không phải quy tắc cho mọi lớp triển khai `CharSequence`.

Khi viết hàm nhận một `CharSequence` bất kỳ, hãy dựa vào hợp đồng của nguồn đó. Nếu hàm cần giữ một giá trị văn bản độc lập, cân nhắc chuyển sang `String` tại ranh giới tiếp nhận và làm rõ trách nhiệm đồng bộ nếu dữ liệu được chia sẻ giữa các luồng. Việc chuyển kiểu biến hoặc ép kiểu không thay thế việc tạo kết quả độc lập.

## 6. UTF-16: một char không luôn là một ký tự người dùng nhìn thấy

Các chỉ số trong bốn phương thức là chỉ số đơn vị mã UTF-16. Với chữ ASCII trong các ví dụ trên, một chữ tương ứng một `char`, nên cách đếm trực quan hoạt động.

Một mã Unicode ngoài vùng BMP, chẳng hạn U+1F600, cần hai `char`: cặp thay thế gồm phần cao và phần thấp (surrogate pair). `charAt` chỉ trả về một nửa nếu ta truy cập vào một vị trí thuộc cặp đó. `setCharAt` cũng chỉ thay một nửa. Các phương thức lấy đoạn chấp nhận ranh giới nằm giữa cặp; chúng không tự điều chỉnh ranh giới thành ký tự hoàn chỉnh.

Chương trình độc lập sau không phụ thuộc khả năng hiển thị emoji của terminal. Lưu thành `BuilderUnicodeDemo.java`:

```java
public class BuilderUnicodeDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("A\uD83D\uDE00B");

        System.out.println("units=" + sb.length());
        System.out.println("codePoints="
                + sb.codePointCount(0, sb.length()));
        System.out.println("high="
                + Character.isHighSurrogate(sb.charAt(1)));
        System.out.println("low="
                + Character.isLowSurrogate(sb.charAt(2)));
        System.out.println("codePoint="
                + Integer.toHexString(sb.codePointAt(1)));

        int start = sb.offsetByCodePoints(0, 1);
        int end = sb.offsetByCodePoints(start, 1);
        String whole = sb.substring(start, end);
        System.out.println("wholeUnits=" + whole.length());
        System.out.println("wholeCodePoint="
                + Integer.toHexString(whole.codePointAt(0)));

        String half = sb.substring(1, 2);
        System.out.println("halfUnits=" + half.length());
        System.out.println("halfIsHigh="
                + Character.isHighSurrogate(half.charAt(0)));

        sb.setCharAt(1, 'X');
        System.out.println("afterSetUnits=" + sb.length());
        System.out.println("remainingLow="
                + Character.isLowSurrogate(sb.charAt(2)));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 BuilderUnicodeDemo.java
java BuilderUnicodeDemo
```

Stdout:

```text
units=4
codePoints=3
high=true
low=true
codePoint=1f600
wholeUnits=2
wholeCodePoint=1f600
halfUnits=1
halfIsHigh=true
afterSetUnits=4
remainingLow=true
```

Trong dữ liệu ban đầu, `A` ở vị trí 0, cặp thay thế ở vị trí 1 và 2, `B` ở vị trí 3. Cặp mã ở giữa biểu diễn một mã Unicode nhưng chiếm hai đơn vị UTF-16.

Ví dụ dùng `offsetByCodePoints` chuyển bước đếm theo mã Unicode thành chỉ số UTF-16, rồi mới gọi `substring`. Cách này hữu ích khi yêu cầu tính theo mã Unicode và dữ liệu đầu vào hợp lệ. Nó không biến một cụm ký tự hiển thị thành một phần tử: chữ kèm dấu tổ hợp hoặc một số emoji ghép vẫn có thể gồm nhiều mã Unicode.

Sau `setCharAt(1, 'X')`, phần thấp ở vị trí 2 không còn được ghép với phần cao ban đầu. Java cho phép lưu chuỗi đơn vị UTF-16 như vậy; không nên dựa vào ngoại lệ để phát hiện thao tác làm hỏng cặp. Khi cần thay cả mã Unicode, xác định đúng khoảng và thay toàn bộ khoảng bằng văn bản phù hợp.

## 7. Thử ranh giới thay vì đoán

Đây là chương trình độc lập kiểm tra cả đoạn rỗng và các chỉ số sai. Lưu thành `BuilderBoundsDemo.java`:

```java
public class BuilderBoundsDemo {
    private static void check(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + ": accepted");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println(name + ": rejected");
        }
    }

    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("abc");

        check("charAt(length)", () -> {
            sb.charAt(sb.length());
        });
        check("setCharAt(length)", () -> {
            sb.setCharAt(sb.length(), '!');
        });
        check("substring(length)", () -> {
            sb.substring(sb.length());
        });
        check("subSequence(length,length)", () -> {
            sb.subSequence(sb.length(), sb.length());
        });
        check("substring(2,1)", () -> {
            sb.substring(2, 1);
        });
        check("subSequence(0,4)", () -> {
            sb.subSequence(0, 4);
        });
        check("charAt(-1)", () -> {
            sb.charAt(-1);
        });
        check("substring(0,0) on empty", () -> {
            new StringBuilder().substring(0, 0);
        });

        System.out.println("builder=" + sb);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 BuilderBoundsDemo.java
java BuilderBoundsDemo
```

Stdout:

```text
charAt(length): rejected
setCharAt(length): rejected
substring(length): accepted
subSequence(length,length): accepted
substring(2,1): rejected
subSequence(0,4): rejected
charAt(-1): rejected
substring(0,0) on empty: accepted
builder=abc
```

Hàm `check` chỉ phục vụ thí nghiệm nên cố ý bắt ngoại lệ và in kết luận. Trong mã ứng dụng, nếu chỉ số đến từ dữ liệu bên ngoài, hãy xác minh dữ liệu theo hợp đồng đầu vào; không lặng lẽ nuốt ngoại lệ rồi tiếp tục với kết quả sai.

## 8. Chọn thao tác phù hợp và tránh lỗi thường gặp

| Ý định | Cách làm phù hợp | Sai lầm cần tránh |
| --- | --- | --- |
| Xem phần tử cuối | Kiểm tra không rỗng rồi đọc `charAt(length() - 1)` | Đọc `charAt(length())` |
| Đổi một dấu phân cách ASCII | `setCharAt(index, ':')` | Truyền chuỗi `":"` hoặc mong chèn phần tử |
| Lấy ba đơn vị từ vị trí 2 | `substring(2, 5)` | Viết `substring(2, 3)` và tưởng tham số 3 là số lượng |
| Lấy một đoạn dưới dạng chuỗi | `substring(start, end)` | Tưởng đoạn bị xóa khỏi builder |
| Trả dữ liệu qua giao diện đọc chuỗi | `subSequence(start, end)` khi hợp đồng cần `CharSequence` | Tưởng kết quả tự cập nhật theo nguồn |
| Tách theo mã Unicode | Đổi mốc mã Unicode sang chỉ số UTF-16 trước | Cắt mù vào giữa surrogate pair |
| Thêm vào cuối | `append` | Dùng `setCharAt(length(), ch)` |

Nếu đã có chỉ số rồi thực hiện một thao tác chèn hoặc xóa trước vị trí đó, cần tính lại chỉ số trước khi đọc/sửa tiếp. Một chỉ số đúng ở trạng thái cũ không tự dịch chuyển theo dữ liệu.

Không thêm bước `toString()` chỉ để gọi `substring`: builder đã có phương thức trích xuất trực tiếp. Khi phải lấy nhiều đoạn lớn hoặc giữ nhiều kết quả, hãy cân nhắc lượng dữ liệu trích xuất thực tế thay vì giả định mọi đoạn đều là một cửa sổ dùng chung và miễn phí.

Giữ builder cục bộ trong một luồng là lựa chọn dễ hiểu. Nếu chia sẻ cho nhiều luồng, một lần kiểm tra `length()` rồi một lần truy cập không tự trở thành một thao tác nguyên tử: luồng khác có thể thay đổi nội dung giữa hai lần gọi.

## 9. Tự kiểm tra

Với `StringBuilder sb = new StringBuilder("AB-123");`, hãy dự đoán trước khi chạy:

1. `sb.charAt(2)` cho gì?
2. Sau `sb.setCharAt(2, ':')`, độ dài và nội dung là gì?
3. `sb.substring(3, 6)` và `sb.subSequence(0, 2)` chứa gì?
4. Sau khi lưu `String saved = sb.substring(0, 2);` rồi gọi `sb.setCharAt(0, 'Z');`, `saved` còn là `"AB"` không?
5. `sb.substring(6, 6)` hợp lệ không? Còn `sb.charAt(6)`?
6. Vì sao không thể thay cả U+1F600 bằng một lần `setCharAt` mà vẫn coi đó là thao tác thay trọn mã Unicode?

Đáp án:

1. `'-'`.
2. Độ dài 6, nội dung `"AB:123"`.
3. Lần lượt `"123"` và `"AB"`.
4. Có. Builder thành `"ZB:123"`, kết quả đã lưu vẫn là `"AB"`.
5. Lấy đoạn rỗng hợp lệ; truy cập vị trí 6 không hợp lệ.
6. Mã Unicode đó chiếm hai `char`, còn `setCharAt` chỉ thay một đơn vị UTF-16.

Khi sử dụng bốn phương thức, hãy xác định trước ba điều: đang thao tác trên một vị trí hay một khoảng, chỉ số tính theo đơn vị nào, và cần sửa builder hay cần giữ một kết quả độc lập.
