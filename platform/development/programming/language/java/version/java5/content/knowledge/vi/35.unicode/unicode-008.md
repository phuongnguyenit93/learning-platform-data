# String.codePointCount và String.offsetByCodePoints

Một chuỗi Java có thể chứa ký tự cần hai đơn vị mã UTF-16. Vì vậy, “điểm mã thứ ba” không nhất thiết nằm ở chỉ số `char` bằng 2.

`codePointCount` và `offsetByCodePoints` giúp chuyển giữa hai cách nhìn: **đếm điểm mã trong một đoạn** và **tìm vị trí UTF-16 sau khi di chuyển một số điểm mã**. Chúng hữu ích khi giới hạn, chia hoặc trích văn bản theo điểm mã mà không cắt đôi cặp surrogate hợp lệ.

## 1. Phân biệt đầu vào và kết quả

| Phương thức | Tham số | Kết quả |
| --- | --- | --- |
| `codePointCount(beginIndex, endIndex)` | Hai chỉ số UTF-16 của đoạn nửa mở | Số điểm mã trong đoạn |
| `offsetByCodePoints(index, codePointOffset)` | Chỉ số UTF-16 xuất phát và số điểm mã cần dịch | Chỉ số UTF-16 đích |

Cần đọc rõ đơn vị: tham số thứ nhất của `offsetByCodePoints` là **chỉ số UTF-16**, còn tham số thứ hai là **số điểm mã dịch chuyển**.

Hình dung một chuỗi có năm điểm mã:

```text
Nội dung:            A      🚀       é       𝄞      Z
Điểm mã:           U+0041 U+1F680 U+00E9 U+1D11E U+005A
Đơn vị UTF-16:      0041 D83D DE80 00E9 D834 DD1E 005A
Chỉ số đơn vị mã:     0    1    2    3    4    5    6

Các ranh giới điểm mã theo chỉ số UTF-16:
                     0    1         3    4         6    7
```

Chuỗi có `length() = 7` nhưng chỉ có 5 điểm mã. Vị trí ngay sau ba điểm mã đầu tiên là chỉ số UTF-16 bằng 4.

## 2. codePointCount đếm một đoạn nửa mở

Chữ ký:

```java
int codePointCount(int beginIndex, int endIndex)
```

Đoạn được đếm là `[beginIndex, endIndex)`: gồm vị trí đầu, không gồm vị trí cuối. Cặp surrogate nằm trọn trong đoạn được tính là một; surrogate không ghép cặp trong đoạn được tính riêng từng đơn vị. [Hợp đồng codePointCount](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePointCount(int,int))

Với chuỗi trong sơ đồ:

| Lời gọi | Kết quả | Đoạn được xét |
| --- | --- | --- |
| `text.codePointCount(0, 7)` | 5 | Toàn chuỗi |
| `text.codePointCount(1, 3)` | 1 | Cả cặp của tên lửa |
| `text.codePointCount(3, 4)` | 1 | Chữ é |
| `text.codePointCount(4, 4)` | 0 | Đoạn rỗng |

Để đếm toàn bộ chuỗi:

```java
int count = text.codePointCount(0, text.length());
```

Đây là đoạn minh họa bên trong phương thức với biến `text` đã có.

Các giới hạn phải thỏa `0 <= beginIndex <= endIndex <= text.length()`; vi phạm sẽ gây `IndexOutOfBoundsException`. Một đối tượng `String` rỗng vẫn có thể gọi `codePointCount(0, 0)` và nhận 0.

## 3. offsetByCodePoints tìm vị trí mới

Chữ ký:

```java
int offsetByCodePoints(int index, int codePointOffset)
```

Độ dịch dương đi về cuối chuỗi, âm đi về đầu, bằng 0 giữ vị trí. Kết quả vẫn là chỉ số UTF-16 để dùng với các API như `substring`. [Hợp đồng offsetByCodePoints](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#offsetByCodePoints(int,int))

Một số phép dịch trên sơ đồ:

| Lời gọi | Kết quả |
| --- | --- |
| `text.offsetByCodePoints(0, 3)` | 4 |
| `text.offsetByCodePoints(1, 2)` | 4 |
| `text.offsetByCodePoints(7, -2)` | 4 |
| `text.offsetByCodePoints(7, 0)` | 7 |
| `text.offsetByCodePoints(0, 5)` | 7 |

Phương thức không trả điểm mã, không trả chuỗi con và không tự chặn ở biên nếu bạn yêu cầu đi quá xa.

`index` có thể bằng `text.length()`, phù hợp khi bắt đầu từ cuối để đi lùi. Nếu vị trí xuất phát ngoài `0..length()` hoặc không còn đủ điểm mã theo hướng dịch, phương thức ném `IndexOutOfBoundsException`.

## 4. Chương trình quan sát cả hai phương thức

Chương trình dùng các điểm mã số để tạo dữ liệu. Kết quả trích được in bằng đơn vị mã hex nên không phụ thuộc phông chữ terminal.

Lưu thành **CodePointRangesDemo.java**:

```java
public class CodePointRangesDemo {
    private static String sliceByCodePoints(
            String text, int fromPoint, int toPoint) {
        int total = text.codePointCount(0, text.length());
        if (fromPoint < 0 || toPoint < fromPoint || toPoint > total) {
            throw new IndexOutOfBoundsException("Invalid code point range");
        }

        int begin = text.offsetByCodePoints(0, fromPoint);
        int end = text.offsetByCodePoints(begin, toPoint - fromPoint);
        return text.substring(begin, end);
    }

    private static String units(String text) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            if (i > 0) out.append(' ');
            out.append(String.format("%04X", (int) text.charAt(i)));
        }
        return out.toString();
    }

    public static void main(String[] args) {
        int[] points = {0x0041, 0x1F680, 0x00E9, 0x1D11E, 0x005A};
        String text = new String(points, 0, points.length);

        System.out.println("units=" + text.length());
        System.out.println("points=" + text.codePointCount(0, text.length()));
        System.out.println("whole pair count=" + text.codePointCount(1, 3));
        System.out.println("left half count=" + text.codePointCount(1, 2));
        System.out.println("right half count=" + text.codePointCount(2, 3));

        System.out.println("forward 3=" + text.offsetByCodePoints(0, 3));
        System.out.println("backward 2="
                + text.offsetByCodePoints(text.length(), -2));

        String middle = sliceByCodePoints(text, 1, 4);
        System.out.println("slice units=" + units(middle));
        System.out.println("slice points="
                + middle.codePointCount(0, middle.length()));
        System.out.println("empty slice length="
                + sliceByCodePoints(text, 5, 5).length());

        try {
            text.offsetByCodePoints(0, 6);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("too far rejected");
        }

        try {
            text.codePointCount(3, 1);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("reversed range rejected");
        }

        String lone = String.valueOf((char) 0xD83D);
        System.out.println("lone surrogate count="
                + lone.codePointCount(0, lone.length()));
        System.out.println("lone surrogate offset="
                + lone.offsetByCodePoints(0, 1));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 CodePointRangesDemo.java
java CodePointRangesDemo
```

Stdout:

```text
units=7
points=5
whole pair count=1
left half count=1
right half count=1
forward 3=4
backward 2=4
slice units=D83D DE80 00E9 D834 DD1E
slice points=3
empty slice length=0
too far rejected
reversed range rejected
lone surrogate count=1
lone surrogate offset=1
```

Hàm `sliceByCodePoints` nhận đoạn nửa mở tính theo **số thứ tự điểm mã**, rồi đổi hai đầu sang chỉ số UTF-16 trước khi gọi `substring`. Với dữ liệu UTF-16 hợp lệ, các vị trí tìm được từ đầu chuỗi giữ nguyên ranh giới cặp surrogate.

Đoạn `[1, 4)` lấy ba điểm mã: tên lửa, é và khóa Sol. Hai ký tự bổ sung mỗi ký tự dùng hai đơn vị mã nên kết quả có năm đơn vị mã.

## 5. Vì sao đếm hai nửa có thể khác đếm cả cặp?

Ba dòng sau không mâu thuẫn:

```text
whole pair count=1
left half count=1
right half count=1
```

Khi đếm đoạn `[1, 3)`, cả hai đơn vị của cặp đều hiện diện nên Java ghép chúng thành một điểm mã.

Khi đếm riêng `[1, 2)`, phần thấp nằm ngoài đoạn; surrogate cao được tính riêng. Với `[2, 3)`, phần thấp cũng được tính riêng.

Vì thế, không thể tùy ý chia chuỗi giữa cặp surrogate rồi cộng các kết quả đếm để suy ra số điểm mã toàn chuỗi. Nếu muốn cộng số lượng các phần, hãy chia ở ranh giới điểm mã.

Hai phương thức cũng không xác thực chuỗi UTF-16. Những dòng `lone surrogate` trong chương trình cho thấy một đơn vị rời vẫn được đếm và đi qua như một đơn vị. Nếu dữ liệu yêu cầu UTF-16 hợp lệ, cần bước kiểm tra cấu trúc riêng.

## 6. Bắt đầu ở giữa cặp không được tự sửa

Phương thức `offsetByCodePoints` nhận chỉ số UTF-16. Nó không biết bạn đang định trỏ đến “ký tự nào” trong giao diện và không tự dời một chỉ số sai về đầu cặp.

Với sơ đồ, chỉ số 2 nằm giữa cặp `D83D DE80`. Dùng vị trí ấy làm điểm xuất phát có thể khiến phần cặp nằm ở một phía được xử lý riêng trong đoạn đang duyệt.

Cách duy trì ranh giới có thể kiểm soát:

- Tìm vị trí từ đầu chuỗi bằng `offsetByCodePoints(0, n)`.
- Hoặc bắt đầu từ một ranh giới đã biết rồi dịch tiếp bằng số điểm mã.
- Khi nhận chỉ số từ nguồn khác, xác định rõ đó là chỉ số byte, UTF-16, điểm mã hay cụm ký tự trước khi sử dụng.

Đặc biệt, không truyền số thứ tự điểm mã trực tiếp vào tham số `index` rồi cho rằng phương thức sẽ tự chuyển hệ tọa độ.

## 7. Áp dụng để lấy tiền tố hoặc hậu tố

Các đoạn sau minh họa bên trong phương thức; giả sử `text` là UTF-16 hợp lệ và `limit` không âm.

Lấy tối đa `limit` điểm mã đầu tiên:

```java
int total = text.codePointCount(0, text.length());
int taken = Math.min(limit, total);
int end = text.offsetByCodePoints(0, taken);
String prefix = text.substring(0, end);
```

Lấy tối đa `limit` điểm mã cuối cùng:

```java
int total = text.codePointCount(0, text.length());
int taken = Math.min(limit, total);
int begin = text.offsetByCodePoints(text.length(), -taken);
String suffix = text.substring(begin);
```

`Math.min` thể hiện chính sách “lấy tối đa”, khác với chính sách báo lỗi khi số lượng vượt quá. Chọn chính sách theo yêu cầu thay vì vô tình dựa vào ngoại lệ.

Nếu mục tiêu là lấy đúng n điểm mã, có thể gọi `offsetByCodePoints` trực tiếp và để điều kiện không đủ dữ liệu được xử lý rõ ràng.

## 8. Giới hạn và chi phí cần hiểu

**Điểm mã không đồng nghĩa cụm ký tự.** Một chữ có dấu kết hợp hoặc emoji ghép có thể gồm nhiều điểm mã. Cắt đúng điểm mã tránh tách cặp surrogate, nhưng vẫn có thể tách cụm mà người dùng xem là một ký tự. Yêu cầu giao diện theo cụm cần cách phân đoạn riêng.

**Chỉ số không phải số lượng.** `codePointCount` trả một số đếm, còn `offsetByCodePoints` trả vị trí. Trộn hai loại kết quả là nguồn lỗi phổ biến.

**Phép dịch không phải phép cộng số nguyên đơn giản.** Để biết phải vượt qua bao nhiêu đơn vị mã, chương trình có thể cần quét dữ liệu. Khi duyệt toàn chuỗi, đừng liên tục tìm điểm mã thứ k bằng cách quét lại từ 0 cho từng k; hãy giữ vị trí hiện tại hoặc dùng cách duyệt tuần tự phù hợp.

**Không cần đổi nếu hợp đồng vốn dùng UTF-16.** Một chỉ số do API Java trả về có thể đã là chỉ số UTF-16 thích hợp cho `substring`. Chỉ chuyển khi yêu cầu thực sự dùng số lượng hoặc thứ tự điểm mã.

## 9. Tự kiểm tra

1. Vì sao `text.codePointCount(0, text.length())` khác `text.length()` trong ví dụ?
2. `text.offsetByCodePoints(0, 2)` trả về 2 hay 3?
3. Vì sao `offsetByCodePoints(text.length(), -1)` có ý nghĩa nhưng `codePointAt(text.length())` không có vị trí hợp lệ?
4. Hàm `sliceByCodePoints` có tự từ chối surrogate rời không?

Đối chiếu:

1. Hai ký tự bổ sung mỗi ký tự dùng hai đơn vị mã nhưng chỉ là một điểm mã.
2. Trả về 3: đã đi qua A và cả cặp của tên lửa.
3. Một phép dịch có thể bắt đầu ở ranh giới cuối; đọc điểm mã cần trỏ vào dữ liệu còn tồn tại.
4. Không; hàm dùng quy tắc đếm của Java, còn xác thực UTF-16 là trách nhiệm riêng nếu cần.
