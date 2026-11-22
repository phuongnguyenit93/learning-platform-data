# StringBuilder: setLength và nội dung được mở rộng

## Hiểu đúng độ dài và vùng nhớ dự trữ

`StringBuilder` giữ một chuỗi có thể sửa đổi. Khi gọi `setLength(n)`, bạn đặt **độ dài nội dung** thành `n`, tính bằng đơn vị mã UTF-16 (`char`). Đây là thao tác sửa nội dung, khác với việc chỉ dự trữ chỗ để nối chuỗi sau này.

Phương thức có dạng `public void setLength(int newLength)` và trả về `void`. Vì vậy, hãy gọi `builder.setLength(0);` rồi mới gọi `builder.append(...)` ở câu lệnh tiếp theo; không viết `builder.setLength(0).append(...)`.

Bài này tập trung vào hành vi vẫn dùng trong Java hiện đại, với ví dụ dùng được trên Java 17+. Hợp đồng `setLength` hiện hành quy định ba trường hợp:

| Giá trị mới so với độ dài cũ | Nội dung sau lệnh |
| --- | --- |
| Nhỏ hơn | Giữ phần đầu và cắt phần đuôi |
| Bằng | Giữ nguyên nội dung |
| Lớn hơn | Giữ nội dung cũ, bổ sung các `char` có giá trị `0` |

Độ dài âm bị từ chối bằng `IndexOutOfBoundsException`. [Java SE 25: setLength](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#setLength(int)).

## Vì sao phần mở rộng dễ gây hiểu nhầm?

Giả sử builder đang chứa `"ABC"` và bạn gọi `setLength(5)`. Hai vị trí mới không chứa dấu cách, chữ số `'0'` hay chuỗi `"null"`. Chúng chứa ký tự NUL, viết trong Java là `'\u0000'`.

Khi in trực tiếp, NUL thường không có hình dạng nhìn thấy được. Bạn có thể tưởng chuỗi vẫn chỉ có ba ký tự. Hãy kiểm tra `length()` hoặc giá trị số của `charAt(i)`. Trong chương trình bên dưới, hàm `visible` đổi NUL thành nhãn `<NUL>` **chỉ để quan sát**; nhãn này không được ghi vào builder gốc.

Phân biệt:

| Giá trị | Bản chất |
| --- | --- |
| `'\u0000'` | Một `char` có giá trị số 0 |
| `'0'` | Một chữ số, giá trị số 48 |
| `' '` | Một dấu cách, giá trị số 32 |
| `null` | Không có tham chiếu đến đối tượng |
| `"null"` | Chuỗi bốn ký tự |

Từ quy tắc mở rộng, ta suy ra: cắt `"ABCDE"` còn `"ABC"` rồi tăng độ dài lên 5 **không khôi phục `D` và `E`**. Hai vị trí xuất hiện lại phải là NUL. Muốn giữ dữ liệu trước khi cắt, hãy lưu riêng dữ liệu đó.

## Chương trình thực hành đầy đủ

Lưu chương trình sau vào `SetLengthDemo.java`. Các dòng stdout dùng chữ không dấu để việc kiểm tra kết quả không phụ thuộc cấu hình hiển thị của terminal.

```java
public class SetLengthDemo {
    private static String visible(CharSequence value) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (ch == 0) {
                out.append("<NUL>");
            } else {
                out.append(ch);
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("ABCDE");
        text.setLength(3);
        System.out.println("shorten: " + text + ", length=" + text.length());

        text.setLength(5);
        System.out.println("expand: " + visible(text));
        System.out.println("charAt(3): " + (int) text.charAt(3));
        System.out.println("length: " + text.length());
        System.out.println("empty: " + (text.length() == 0));

        text.append('X');
        System.out.println("append: " + visible(text));
        text.setCharAt(3, 'D');
        text.setCharAt(4, 'E');
        System.out.println("replace padding: " + text);

        String snapshot = text.toString();
        text.setLength(0);
        text.append("new");
        System.out.println("reused: " + text);
        System.out.println("snapshot: " + snapshot);

        StringBuilder reserved = new StringBuilder(8);
        reserved.ensureCapacity(20);
        System.out.println("reserved length: " + reserved.length());
        System.out.println("reserved capacity >= 20: " + (reserved.capacity() >= 20));

        StringBuilder record = new StringBuilder();
        record.setLength(4);
        record.setCharAt(0, 'J');
        record.setCharAt(1, 'A');
        record.setCharAt(2, 'V');
        record.setCharAt(3, 'A');
        System.out.println("filled: " + record);

        StringBuilder unicode = new StringBuilder("A\uD83D\uDE00B");
        System.out.println("UTF-16 length: " + unicode.length());
        unicode.setLength(2);
        System.out.println("dangling high surrogate: "
                + Character.isHighSurrogate(unicode.charAt(1)));
        StringBuilder safe = new StringBuilder("A\uD83D\uDE00B");
        int boundary = safe.offsetByCodePoints(0, 2);
        safe.setLength(boundary);
        System.out.println("safe UTF-16 length: " + safe.length());
        System.out.println("safe code points: " + safe.codePointCount(0, safe.length()));

        try {
            text.setLength(-1);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("negative length rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 SetLengthDemo.java
java SetLengthDemo
```

Kết quả:

```text
shorten: ABC, length=3
expand: ABC<NUL><NUL>
charAt(3): 0
length: 5
empty: false
append: ABC<NUL><NUL>X
replace padding: ABCDEX
reused: new
snapshot: ABCDEX
reserved length: 0
reserved capacity >= 20: true
filled: JAVA
UTF-16 length: 4
dangling high surrogate: true
safe UTF-16 length: 3
safe code points: 2
negative length rejected
```

### Đọc kết quả theo từng thay đổi

1. `setLength(3)` giữ `ABC`. Sau `setLength(5)`, hai vị trí mới chứa NUL; `charAt(3)` có giá trị số 0.
2. `append('X')` thêm sau toàn bộ nội dung có độ dài 5, nên `X` nằm ở chỉ số 5. Nó không tự tìm và lấp vị trí NUL đầu tiên.
3. Hai lệnh `setCharAt` thay trực tiếp các vị trí 3 và 4 bằng `D` và `E`. Kết quả là `ABCDEX`.
4. `toString()` lưu một chuỗi kết quả trước khi builder được làm rỗng. Sau khi builder chứa `new`, biến `snapshot` vẫn chứa `ABCDEX`.
5. Dự trữ dung lượng không tạo nội dung: `reserved.length()` vẫn là 0.
6. Builder `record` được mở rộng trước rồi ghi đủ bốn vị trí, nên không còn NUL trong kết quả `JAVA`.
7. Các dòng cuối minh họa ranh giới UTF-16 và trường hợp độ dài âm.

## Chọn thao tác phù hợp với mục đích

### Chỉ muốn chuẩn bị chỗ cho nội dung sắp nối

Dùng constructor nhận dung lượng hoặc `ensureCapacity`. Độ dài vẫn bằng 0 cho đến khi có nội dung được thêm. `capacity()` đo khả năng chứa, còn `length()` đo nội dung hiện có. [Java SE 21: capacity và ensureCapacity](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html#ensureCapacity(int)).

Ví dụ minh họa trong một phương thức:

```java
StringBuilder line = new StringBuilder(100);
// line.length() == 0
line.append("name=").append("Lan");
// line.toString().equals("name=Lan")
```

Nếu thay constructor trên bằng `new StringBuilder(); line.setLength(100);`, rồi `append("name=Lan")`, kết quả sẽ có 100 NUL đứng trước phần văn bản. Đó là một dữ liệu khác, dù terminal có thể không hiển thị các ký tự đầu.

### Muốn cắt phần đuôi hoặc bỏ dấu phân cách cuối

Chỉ giảm độ dài khi chắc chắn phần bỏ đi đúng là phần cần loại bỏ:

```java
StringBuilder csv = new StringBuilder();
for (String name : new String[] {"An", "Binh"}) {
    csv.append(name).append(',');
}
if (csv.length() > 0) {
    csv.setLength(csv.length() - 1);
}
// csv.toString().equals("An,Binh")
```

Điều kiện bảo vệ xử lý trường hợp mảng rỗng. Bỏ điều kiện rồi tính `length() - 1` khi độ dài bằng 0 sẽ tạo tham số âm.

Nếu yêu cầu là “tối đa 20 đơn vị UTF-16”, đừng gọi `setLength(20)` vô điều kiện: chuỗi ngắn hơn 20 sẽ bị thêm NUL. Hãy chỉ cắt khi `builder.length() > 20`. Với văn bản Unicode bất kỳ, còn phải xét ranh giới ký tự như phần sau.

### Muốn tái sử dụng builder cho lượt tiếp theo

`setLength(0)` đưa nội dung về rỗng. Trong chương trình mẫu, chính đối tượng `text` được dùng lại để tạo `new`. `String` đã lấy qua `toString()` không bị thay đổi theo builder. [Java SE 21: toString](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html#toString()).

Trong OpenJDK 25, thu ngắn cập nhật độ dài mà không chủ động thu nhỏ mảng chứa. Việc mở rộng phải điền phần mới bằng số 0 và có thể cần cấp phát khi thiếu dung lượng. Vì vậy, tăng độ dài rất lớn có chi phí bộ nhớ; giảm độ dài không đồng nghĩa giải phóng dung lượng ngay. Đây là giải thích từ triển khai cụ thể, không phải lý do để phụ thuộc vào bố trí mảng bên trong. [OpenJDK 25: triển khai setLength](https://github.com/openjdk/jdk/blob/jdk-25%2B36/src/java.base/share/classes/java/lang/AbstractStringBuilder.java).

Từ triển khai đó cũng thấy `setLength(0)` không phải cam kết ghi đè toàn bộ dữ liệu cũ trong bộ nhớ. Khi đánh giá việc tái sử dụng, hãy phân biệt “nội dung không còn đọc được qua chỉ số hợp lệ” với “bộ nhớ đã bị xóa vật lý”.

### Muốn tạo nội dung có độ dài cố định

Có thể mở rộng rồi ghi từng vị trí bằng `setCharAt`, như `record` trong chương trình. Cần bảo đảm mọi vị trí thuộc kết quả đều được gán nội dung mong muốn trước khi dùng `toString()`.

Nếu mục đích là căn lề bằng dấu cách, hãy thêm dấu cách rõ ràng. Đoạn minh họa sau tạo `"ID  "` có hai dấu cách cuối:

```java
StringBuilder label = new StringBuilder("ID");
while (label.length() < 4) {
    label.append(' ');
}
```

`setLength(4)` sẽ tạo `ID` kèm hai NUL, nên không thay thế được cách căn lề này.

## UTF-16: độ dài không luôn bằng số ký tự nhìn thấy

Trong chương trình, `"A\uD83D\uDE00B"` gồm `A`, một emoji và `B`. Emoji được biểu diễn bằng hai `char` tạo thành một cặp surrogate, nên tổng độ dài là 4. Khi cắt còn 2, builder giữ `A` và nửa đầu cặp surrogate. Kết quả `dangling high surrogate: true` cho thấy phép cắt đã chia đôi biểu diễn emoji.

Nếu yêu cầu giữ hai mã điểm Unicode đầu tiên, chương trình dùng `offsetByCodePoints(0, 2)` để tìm chỉ số UTF-16 tương ứng, rồi truyền chỉ số đó vào `setLength`. Kết quả còn 3 đơn vị UTF-16 và 2 mã điểm. Cách dùng này áp dụng khi đã xác nhận chuỗi có đủ số mã điểm cần giữ. [Java SE 25: offsetByCodePoints](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#offsetByCodePoints(int,int)).

**Mã điểm vẫn không luôn bằng một ký tự hiển thị hoàn chỉnh**: dấu kết hợp và một số chuỗi emoji có thể gồm nhiều mã điểm. Vì vậy, nếu bài toán là cắt văn bản theo ký tự mà người dùng nhìn thấy, cần xác định quy tắc phân đoạn văn bản riêng; không coi `setLength` là bộ cắt văn bản theo giao diện.

## Tự kiểm tra

Dự đoán trước rồi chạy từng đoạn trong một phương thức:

- `new StringBuilder("AB").setLength(4)` có tạo hai dấu cách không? Không; nội dung mới có hai NUL.
- Sau khi mở rộng `"AB"` lên độ dài 4 rồi `append("C")`, độ dài là bao nhiêu? 5; `C` nằm ở chỉ số 4.
- Sau `setLength(0)` rồi `setLength(2)`, nội dung cũ có trở lại không? Không; hai vị trí mới là NUL.
- Builder có dung lượng 100 nhưng độ dài 0 có gọi được `setCharAt(50, 'X')` không? Không; vị trí phải nằm trong nội dung hiện tại, tức nhỏ hơn `length()`.
- Vì sao `setLength` không thích hợp để “đặt trước độ dài ước lượng” khi đang xây chuỗi bằng `append`? Vì phần đặt trước trở thành nội dung NUL thực sự, và các lần nối sẽ bắt đầu sau phần đó.

Khi dùng `setLength`, hãy xác định rõ mục tiêu là **cắt nội dung**, **làm rỗng để tái sử dụng**, hay **tạo các vị trí nội dung mới sẽ được ghi đầy đủ**. Nếu chỉ cần dự trữ bộ nhớ, hãy chọn thao tác dung lượng.
