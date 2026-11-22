# String.codePointAt và String.codePointBefore

## 1. Đọc một mã Unicode theo hai hướng

Khi đọc văn bản Java, `charAt` cho một đơn vị UTF-16. Một mã Unicode ngoài BMP cần hai đơn vị, nên đôi khi ta cần đọc cả mã thay vì từng nửa của nó.

`String` cung cấp hai phương thức:

```java
int codePointAt(int index)
int codePointBefore(int index)
```

- `codePointAt(index)` đọc mã bắt đầu tại vị trí UTF-16 được chỉ định, ghép với đơn vị tiếp theo nếu tạo thành cặp surrogate.
- `codePointBefore(index)` đọc mã ngay trước ranh giới UTF-16 được chỉ định, ghép với đơn vị đứng trước nữa nếu tạo thành cặp surrogate.

Cả hai trả về `int` để chứa được mã ngoài miền của `char`. Cả hai đều không sửa chuỗi.

Một nguyên tắc phải giữ xuyên suốt bài:

> Tên phương thức nói về mã Unicode ở kết quả, nhưng tham số index vẫn tính theo đơn vị UTF-16.

Không truyền “thứ tự mã Unicode” vào tham số này nếu chưa đổi nó thành chỉ số UTF-16. Ví dụ, mã Unicode thứ ba không nhất thiết bắt đầu ở chỉ số 2.

Các ví dụ bên dưới chạy được trên Java 17 trở lên và dùng các API vẫn phù hợp trong Java hiện nay.

## 2. Hiểu chỉ số phần tử và ranh giới

Xét chuỗi gồm chữ `a`, emoji tên lửa U+1F680 và chữ `z`:

```text
Đơn vị UTF-16:       0061       D83D       DE80       007A
Chỉ số đơn vị:         0          1          2          3
Ranh giới:         0       1          2          3          4
Mã Unicode:        [a]       [ U+1F680 ]          [z]
```

Chuỗi có bốn đơn vị UTF-16 nhưng ba mã Unicode.

- Để đọc tên lửa theo hướng tiến, bắt đầu ở chỉ số 1: `codePointAt(1)`.
- Để đọc tên lửa theo hướng lùi, đặt ranh giới ngay sau nó, tức 3: `codePointBefore(3)`.
- Để đọc mã cuối, dùng `codePointBefore(text.length())`.
- Không dùng `codePointAt(text.length())`, vì không có đơn vị nào bắt đầu ở ranh giới cuối.

Khác biệt này đặc biệt hữu ích khi viết bộ quét văn bản: một biến vị trí có thể biểu diễn “đơn vị sắp đọc” khi đi tiến hoặc “ranh giới sau phần đã đi qua” khi đi lùi.

## 3. Cơ chế ghép surrogate của từng phương thức

### 3.1. codePointAt nhìn tại index và tối đa một đơn vị phía sau

Với một `index` hợp lệ:

1. Đọc đơn vị UTF-16 tại `index`.
2. Nếu đó là high surrogate, phía sau còn dữ liệu và đơn vị kế là low surrogate, ghép hai đơn vị thành mã ngoài BMP.
3. Nếu không thỏa điều kiện ghép, trả giá trị số của đơn vị tại `index`.

Phương thức không tự đi lùi để tìm đầu cặp. Nếu `index` đang trỏ tới low surrogate, nó trả giá trị low surrogate đó.

### 3.2. codePointBefore nhìn tại index - 1 và tối đa một đơn vị phía trước

Với một `index` hợp lệ:

1. Đọc đơn vị UTF-16 tại `index - 1`.
2. Nếu đó là low surrogate và đơn vị ngay trước nó là high surrogate, ghép thành mã ngoài BMP.
3. Nếu không ghép được, trả giá trị số của đơn vị tại `index - 1`.

Phương thức không tự đi tiến qua ranh giới đã cho. Nếu ranh giới nằm giữa high surrogate và low surrogate, đơn vị ngay trước ranh giới chỉ là high surrogate.

Các quy tắc này được nêu trong [hợp đồng codePointAt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePointAt(int)) và [hợp đồng codePointBefore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePointBefore(int)).

### 3.3. Đọc giữa cặp không đồng nghĩa với đọc cả mã

Với chuỗi `a + U+1F680 + z`:

| Lời gọi | Giá trị trả về | Giải thích |
| --- | --- | --- |
| `codePointAt(1)` | `0x1F680` | Bắt đầu tại high surrogate, ghép được cặp |
| `codePointAt(2)` | `0xDE80` | Bắt đầu tại low surrogate, không lùi lại |
| `codePointBefore(3)` | `0x1F680` | Ranh giới nằm sau cả cặp |
| `codePointBefore(2)` | `0xD83D` | Ranh giới nằm giữa cặp, không đọc vượt sang phải |

Vì thế, không coi `codePointBefore(i + 1)` luôn tương đương `codePointAt(i)`. Với `i = 1`, hai lời gọi đó cho hai giá trị khác nhau.

## 4. Chương trình quan sát mọi vị trí hợp lệ

Lưu thành `CodePointPositionsDemo.java`:

```java
public class CodePointPositionsDemo {
    public static void main(String[] args) {
        String text = "a\uD83D\uDE80z";
        System.out.println("length=" + text.length());

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("at(%d)=U+%04X%n",
                    i, text.codePointAt(i));
        }

        for (int i = 1; i <= text.length(); i++) {
            System.out.printf("before(%d)=U+%04X%n",
                    i, text.codePointBefore(i));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 CodePointPositionsDemo.java
java CodePointPositionsDemo
```

Stdout:

```text
length=4
at(0)=U+0061
at(1)=U+1F680
at(2)=U+DE80
at(3)=U+007A
before(1)=U+0061
before(2)=U+D83D
before(3)=U+1F680
before(4)=U+007A
```

Chương trình cố ý thử từng vị trí UTF-16, kể cả vị trí ở giữa cặp. Đây là thí nghiệm về hợp đồng phương thức; không phải mẫu duyệt một lần cho mỗi mã Unicode.

`U+DE80` và `U+D83D` trong đầu ra là các giá trị surrogate. Chúng không phải các giá trị vô hướng Unicode biểu diễn độc lập một ký tự hoàn chỉnh. Cách in số hexadecimal giúp quan sát chính xác, không phụ thuộc phông chữ hoặc việc terminal thay surrogate lẻ bằng ký hiệu nào.

## 5. Duyệt tiến và lùi đúng theo mã Unicode

Nếu muốn đi qua từng mã một lần, sau khi đọc phải di chuyển theo số đơn vị của mã vừa đọc.

`Character.charCount(point)` trả 1 hoặc 2 theo giá trị mã. Khi dùng với kết quả đọc từ chuỗi, nó cho bước di chuyển cần thiết trong các vòng lặp dưới đây. Có thể đối chiếu tại [Character.charCount](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#charCount(int)).

### 5.1. Đi tiến

Mẫu minh họa bên trong một phương thức, với biến `text` đã khai báo:

```java
for (int offset = 0; offset < text.length();) {
    int point = text.codePointAt(offset);
    // Xử lý point.
    offset += Character.charCount(point);
}
```

Không tăng cố định `offset++`: khi mã vừa đọc dùng hai đơn vị, tăng một sẽ đưa vòng lặp vào phần thấp của cặp.

### 5.2. Đi lùi

```java
for (int cursor = text.length(); cursor > 0;) {
    int point = text.codePointBefore(cursor);
    // Xử lý point.
    cursor -= Character.charCount(point);
}
```

Khởi đầu ở `length()` là đúng cho `codePointBefore`. Đọc xong mới lùi ranh giới về đầu mã vừa đọc.

Hai vòng lặp này tự bỏ qua phần thân nếu chuỗi rỗng. Không cần gọi một phương thức đọc với chỉ số không tồn tại rồi bắt ngoại lệ để kết thúc vòng lặp.

### 5.3. Ví dụ độc lập có cả mã một và hai đơn vị

Lưu thành `CodePointWalkDemo.java`:

```java
public class CodePointWalkDemo {
    public static void main(String[] args) {
        String text = "L\uD83D\uDE80\uD801\uDC00R";
        System.out.println("units=" + text.length());

        int offset = 0;
        while (offset < text.length()) {
            int point = text.codePointAt(offset);
            int next = offset + Character.charCount(point);
            System.out.printf("forward[%d,%d)=U+%04X%n",
                    offset, next, point);
            offset = next;
        }

        int cursor = text.length();
        while (cursor > 0) {
            int point = text.codePointBefore(cursor);
            int previous = cursor - Character.charCount(point);
            System.out.printf("backward[%d,%d)=U+%04X%n",
                    previous, cursor, point);
            cursor = previous;
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 CodePointWalkDemo.java
java CodePointWalkDemo
```

Stdout:

```text
units=6
forward[0,1)=U+004C
forward[1,3)=U+1F680
forward[3,5)=U+10400
forward[5,6)=U+0052
backward[5,6)=U+0052
backward[3,5)=U+10400
backward[1,3)=U+1F680
backward[0,1)=U+004C
```

Hai hướng đi qua cùng bốn mã, theo thứ tự ngược nhau. Các khoảng `[start, end)` trong đầu ra cho thấy rõ mã nào chiếm một hay hai đơn vị UTF-16.

Đây là thứ tự lưu trữ logic của chuỗi. Không dùng nó như một thuật toán di chuyển con trỏ theo thứ tự hình ảnh trên màn hình đối với văn bản có quy tắc dựng hoặc hướng viết phức tạp.

## 6. Miền chỉ số, chuỗi rỗng và ngoại lệ

Giả sử `n = text.length()`:

| Phương thức | Miền index hợp lệ |
| --- | --- |
| `codePointAt(index)` | `0 <= index < n` |
| `codePointBefore(index)` | `1 <= index <= n` |

Cả hai quy định ném `IndexOutOfBoundsException` khi chỉ số ngoài miền. JDK có thể ném một lớp con; mã kiểm thử không nên phụ thuộc nội dung thông báo lỗi.

Với chuỗi rỗng, không có chỉ số đọc hợp lệ cho cả hai. Với biến `String` là `null`, lời gọi phương thức gây `NullPointerException`; đó là trường hợp không có đối tượng chuỗi, khác với đối tượng chuỗi rỗng.

Lưu chương trình sau thành `CodePointEdgesDemo.java`:

```java
public class CodePointEdgesDemo {
    private static void check(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": accepted");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println(label + ": rejected");
        }
    }

    public static void main(String[] args) {
        String text = "ok";
        check("at(-1)", () -> {
            text.codePointAt(-1);
        });
        check("at(length)", () -> {
            text.codePointAt(text.length());
        });
        check("before(0)", () -> {
            text.codePointBefore(0);
        });
        check("before(length)", () -> {
            text.codePointBefore(text.length());
        });
        check("before(length+1)", () -> {
            text.codePointBefore(text.length() + 1);
        });
        check("empty.at(0)", () -> {
            "".codePointAt(0);
        });
        check("empty.before(0)", () -> {
            "".codePointBefore(0);
        });

        String highOnly = "\uD83D";
        String lowOnly = "\uDE80";
        System.out.printf("high.at=U+%04X%n",
                highOnly.codePointAt(0));
        System.out.printf("high.before=U+%04X%n",
                highOnly.codePointBefore(1));
        System.out.printf("low.at=U+%04X%n",
                lowOnly.codePointAt(0));
        System.out.printf("low.before=U+%04X%n",
                lowOnly.codePointBefore(1));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 CodePointEdgesDemo.java
java CodePointEdgesDemo
```

Stdout:

```text
at(-1): rejected
at(length): rejected
before(0): rejected
before(length): accepted
before(length+1): rejected
empty.at(0): rejected
empty.before(0): rejected
high.at=U+D83D
high.before=U+D83D
low.at=U+DE80
low.before=U+DE80
```

Hàm `check` phục vụ thí nghiệm nên chủ động bắt lỗi chỉ số và in kết luận. Trong mã ứng dụng, xử lý điều kiện biên theo hợp đồng của hàm thay vì coi ngoại lệ là kết quả đọc thông thường.

Các dòng cuối chứng minh hai phương thức không xác minh toàn bộ tính hợp lệ UTF-16. Surrogate không ghép cặp được trả lại dưới dạng số; không có ngoại lệ chỉ vì dữ liệu chứa một surrogate lẻ.

## 7. Khi nào áp dụng và cần giữ giả định gì?

### 7.1. Kiểm tra một mã ở trước hoặc sau vị trí quét

Một bộ phân tích có thể kiểm tra mã sắp đọc bằng `codePointAt(offset)`, hoặc mã đứng trước con trỏ bằng `codePointBefore(cursor)`. Trước khi gọi, kiểm tra miền chỉ số và bảo đảm vị trí quét đang ở ranh giới mã mong muốn.

Để phân loại chữ ngoài BMP, giữ giá trị ở kiểu `int` rồi gọi overload thích hợp:

```java
int point = text.codePointAt(offset);
boolean letter = Character.isLetter(point);
```

Đây là đoạn minh họa với `text` khác `null` và `offset` hợp lệ. Không ép kết quả sang `char` trước khi phân loại: thao tác đó làm mất thông tin của mã ngoài BMP.

### 7.2. Đọc mã thứ k cần bước đổi chỉ số

Nếu yêu cầu nói đến mã ở thứ tự `k` tính từ 0, `k` không tự trở thành `index`. Với `0 <= k < text.codePointCount(0, text.length())`, có thể viết:

```java
int offset = text.offsetByCodePoints(0, k);
int point = text.codePointAt(offset);
```

Đoạn minh họa này tách rõ hai trách nhiệm: tìm vị trí UTF-16 rồi đọc mã tại vị trí đó. Khi duyệt toàn chuỗi, dùng bước tiến ở phần 5 giúp tránh tìm lại từ đầu cho từng `k`.

### 7.3. Mã Unicode không phải cụm ký tự

Một chữ có dấu tổ hợp hoặc một chuỗi emoji có thể gồm nhiều mã Unicode. Đi tiến/lùi một mã chưa chắc đi qua trọn một ký tự mà người dùng cảm nhận.

Vì vậy, dùng hai phương thức này khi bài toán cần đọc mã Unicode. Nếu yêu cầu là xóa một ký tự hiển thị, chọn đoạn theo cụm ký tự hoặc di chuyển con trỏ trong trình biên tập, cần thêm quy tắc phân đoạn và dựng văn bản thích hợp.

## 8. Lỗi thường gặp

| Lỗi | Hệ quả | Cách tránh |
| --- | --- | --- |
| Dùng index như thứ tự code point | Có thể đọc nhầm hoặc rơi vào giữa cặp | Giữ chỉ số UTF-16 hoặc đổi bằng `offsetByCodePoints` |
| Gọi `codePointAt(length())` | Lỗi chỉ số | Dùng `codePointBefore(length())` để đọc mã cuối khi không rỗng |
| Gọi `codePointBefore(0)` | Lỗi chỉ số | Kiểm tra còn dữ liệu phía trước |
| Tăng/giảm cố định một đơn vị | Có thể đọc lại nửa surrogate | Dùng `Character.charCount(point)` |
| Cho rằng phương thức tự chỉnh vị trí giữa cặp | Nhận surrogate thay vì mã hoàn chỉnh | Quản lý ranh giới tại bên gọi |
| Ép kết quả về char | Mất phần thông tin của mã ngoài BMP | Giữ `int` cho mã Unicode |
| Coi kết quả đọc được là bằng chứng UTF-16 hợp lệ | Bỏ sót surrogate lẻ | Kiểm tra dữ liệu riêng nếu hợp đồng yêu cầu |
| Coi mỗi mã là một ký tự hiển thị | Có thể tách dấu hoặc emoji ghép | Phân biệt mã và cụm ký tự |

## 9. Tự kiểm tra

Với `String s = "a\uD83D\uDE80z";`:

1. `s.length()` bằng bao nhiêu?
2. `s.codePointAt(1)` và `s.codePointBefore(3)` có cùng kết quả không?
3. Vì sao `s.codePointAt(2)` không trả mã tên lửa?
4. Vì sao `s.codePointBefore(2)` chỉ trả high surrogate?
5. Lời gọi nào đọc đúng mã cuối?
6. Sau khi đọc tên lửa bằng `codePointAt(1)`, vị trí tiếp theo phải là bao nhiêu?
7. Hai phương thức có bảo đảm kết quả luôn là giá trị vô hướng Unicode hợp lệ không?
8. Một vòng lặp lùi qua mã Unicode có đồng thời là thuật toán đảo ký tự hiển thị không?

Đáp án:

1. Bốn đơn vị UTF-16.
2. Có; đều trả `0x1F680`.
3. Chỉ số 2 trỏ vào low surrogate; phương thức không lùi để ghép với phần cao.
4. Ranh giới 2 nằm giữa cặp; phương thức không đọc vượt qua ranh giới sang phải.
5. `s.codePointBefore(s.length())`, kết quả U+007A.
6. Chỉ số 3, vì tên lửa chiếm hai đơn vị.
7. Không; surrogate lẻ có thể được trả lại.
8. Không; một cụm ký tự có thể gồm nhiều mã và cách dựng văn bản còn có quy tắc khác.

Để đọc đúng, hãy thống nhất ba điều: chỉ số đang đo bằng UTF-16, ranh giới nằm ở đâu và sau lần đọc cần dịch bao nhiêu đơn vị. `codePointAt` và `codePointBefore` cung cấp hai hướng đọc; bên gọi chịu trách nhiệm chọn vị trí phù hợp.
