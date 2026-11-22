# codePointAt và codePointBefore trong Java String

Hai phương thức **String.codePointAt(int index)** và **String.codePointBefore(int index)** cho phép đọc một *Unicode code point* từ chuỗi Java theo hai hướng: bắt đầu tại vị trí chỉ định hoặc ngay trước vị trí chỉ định. Điểm quyết định để sử dụng đúng là: **index của cả hai phương thức đều đo bằng đơn vị mã UTF-16 (vị trí char), không phải số thứ tự code point hay số ký tự mà mắt nhìn thấy**.

Bài học tập trung vào cách lấy code point, nhận biết cặp surrogate, chọn chỉ số hợp lệ và duyệt chuỗi mà không vô tình tách đôi một code point nằm ngoài Basic Multilingual Plane (BMP).

## 1. Vì sao charAt() chưa đủ để đọc mọi ký tự Unicode?

Java String lưu dãy đơn vị mã UTF-16. Một đơn vị mã là một giá trị 16 bit; thao tác **charAt(index)** trả về đúng một đơn vị mã kiểu char.

- Các code point thuộc BMP không nằm trong vùng surrogate (ví dụ U+0041 là "A") thường được biểu diễn bởi **một** đơn vị mã UTF-16.
- Một code point bổ sung ngoài BMP (từ U+10000 đến U+10FFFF, ví dụ U+1F600 là emoji 😀) cần **hai** đơn vị mã: *high surrogate* rồi *low surrogate*.
- Nếu gọi charAt() vào một nửa của cặp surrogate, giá trị nhận được chỉ là một char đại diện cho nửa đó; nó không tương đương code point ban đầu.

Ví dụ với chuỗi **"A😀B"**:

| UTF-16 index | Đơn vị mã tại vị trí | Vai trò |
|---:|---|---|
| 0 | U+0041 | Chữ A |
| 1 | U+D83D | High surrogate của 😀 |
| 2 | U+DE00 | Low surrogate của 😀 |
| 3 | U+0042 | Chữ B |

Vì thế, **length() bằng 4**, dù chuỗi có **3 Unicode code point**: A, 😀 và B. Độ dài UTF-16 không phải số code point và cũng không mặc nhiên là số ký tự hiển thị (*grapheme cluster*).

Hai phương thức codePointAt()/codePointBefore() nhận diện **một cặp surrogate hợp lệ liền kề** và ghép thành code point tương ứng, thay vì chỉ trả về một char như charAt().

## 2. String.codePointAt(int index): đọc từ vị trí bắt đầu

Cú pháp:

~~~java
int codePoint = text.codePointAt(index);
~~~

Quy tắc:

1. index là vị trí đơn vị mã UTF-16 đầu tiên cần đọc.
2. Nếu char tại index là **high surrogate** và ngay sau nó là **low surrogate**, phương thức ghép cả hai và trả về code point bổ sung dạng int.
3. Trong các trường hợp khác, phương thức trả về giá trị đơn vị mã char tại index dưới dạng int. Điều này bao gồm một surrogate đơn lẻ hoặc việc bắt đầu ở **low surrogate**, tức giữa một cặp.
4. Phương thức **không làm thay đổi** String.

Với "A😀B":

| Lời gọi | Kết quả hệ 16 | Giải thích |
|---|---|---|
| codePointAt(0) | U+0041 | Đọc A |
| codePointAt(1) | U+1F600 | Ghép high surrogate index 1 và low surrogate index 2 |
| codePointAt(2) | U+DE00 | Bắt đầu ở low surrogate: chỉ trả về đơn vị mã này |
| codePointAt(3) | U+0042 | Đọc B |

**Sai lầm quan trọng:** codePointAt(2) không có nghĩa là “lấy code point thứ 3”. Nó là đọc code point **bắt đầu ở chỉ số UTF-16 2**. Nếu chỉ số ở giữa cặp surrogate, phương thức không tự quay lại tìm high surrogate.

Giới hạn chỉ số hợp lệ với chuỗi độ dài n:

- **0 <= index < n** cho codePointAt(index).
- Với chuỗi rỗng, không có index hợp lệ.
- index âm hoặc index >= n gây **StringIndexOutOfBoundsException**.

### Khi nào sử dụng?

Dùng codePointAt() khi bạn đã có **UTF-16 offset** và muốn lấy code point bắt đầu tại đó. Ví dụ, duyệt chuỗi từ trái qua phải, phân loại code point bằng Character.isLetter(int), Character.isDigit(int) hoặc xử lý một ký tự Unicode không giới hạn trong 16 bit.

## 3. String.codePointBefore(int index): đọc ngay trước một ranh giới

Cú pháp:

~~~java
int codePoint = text.codePointBefore(index);
~~~

Khác với codePointAt(), tham số index **không** chỉ phần tử cần đọc, mà chỉ **ranh giới ngay sau đơn vị mã cuối cùng cần xét**.

Quy tắc:

1. Phương thức nhìn vào char tại **index - 1**.
2. Nếu đó là **low surrogate** và char tại **index - 2** là **high surrogate**, phương thức ghép cả cặp rồi trả về code point bổ sung.
3. Nếu không có cặp hợp lệ về phía trước, phương thức trả về giá trị char tại index - 1 dưới dạng int.
4. String nguồn không thay đổi.

Với "A😀B":

| Lời gọi | Kết quả hệ 16 | Giải thích |
|---|---|---|
| codePointBefore(1) | U+0041 | Ký tự ngay trước ranh giới 1 là A |
| codePointBefore(2) | U+D83D | Ngay trước ranh giới 2 là high surrogate; chưa có low surrogate ở bên trái để ghép |
| codePointBefore(3) | U+1F600 | Nhìn từ index 3 về trước: low surrogate tại 2 ghép với high tại 1 |
| codePointBefore(4) | U+0042 | Ký tự ngay trước ranh giới 4 là B |

**Khác biệt cần ghi nhớ:** để lấy emoji 😀 đầy đủ, codePointAt(1) bắt đầu tại high surrogate; codePointBefore(3) bắt đầu từ ranh giới **sau** low surrogate.

Giới hạn chỉ số hợp lệ với chuỗi độ dài n:

- **1 <= index <= n** cho codePointBefore(index).
- index bằng n hoàn toàn hợp lệ và giúp đọc code point cuối.
- index bằng 0, âm hoặc lớn hơn n gây **StringIndexOutOfBoundsException**.

### Khi nào sử dụng?

Dùng codePointBefore() khi bạn có offset nằm **sau** vị trí cần đọc: ví dụ duyệt ngược từ cuối chuỗi, đọc code point đứng trước con trỏ hoặc đi lùi theo ranh giới UTF-16.

## 4. So sánh trực tiếp hai phương thức

| Câu hỏi | codePointAt(index) | codePointBefore(index) |
|---|---|---|
| Đọc về hướng nào? | Từ vị trí index sang phải | Từ trước index sang trái |
| Đơn vị của index? | UTF-16 code unit | UTF-16 code unit |
| Bắt đầu xét char nào? | index | index - 1 |
| Cặp surrogate được ghép khi nào? | index là high và index+1 là low | index-1 là low và index-2 là high |
| Chỉ số hợp lệ? | [0, length()-1] | [1, length()] |
| Lấy code point đầu tiên | codePointAt(0) | codePointBefore(độ dài UTF-16 của code point đầu) |
| Lấy code point cuối cùng | codePointAt(offset đầu của code point cuối) | codePointBefore(length()) |
| Kiểu trả về | int | int |
| Chuỗi bị sửa? | Không | Không |

**Mẹo nhớ:** *At* đọc code point **bắt đầu tại** index; *Before* đọc code point **kết thúc ngay trước** index.

Nếu index trỏ tới ranh giới tự nhiên giữa hai code point, cả hai phương thức hữu ích và nhất quán. Nếu index cắt đôi cặp surrogate, kết quả có thể chỉ là một nửa surrogate. Java không tự bảo đảm index do ứng dụng truyền vào nằm tại ranh giới code point.

## 5. Chương trình Java 17+ chạy độc lập

Ví dụ sau in giá trị dạng U+... để tránh phụ thuộc font hiển thị emoji trong console. Nó minh họa cả trường hợp truy cập đúng ranh giới và trường hợp truy cập giữa hai nửa surrogate.

Tạo file **CodePointAccessDemo.java** với nội dung:

~~~java
public class CodePointAccessDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println("length=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("at(%d)=U+%X%n", i, text.codePointAt(i));
        }

        for (int i = 1; i <= text.length(); i++) {
            System.out.printf("before(%d)=U+%X%n", i, text.codePointBefore(i));
        }

        System.out.println("highSurrogate="
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("lowSurrogate="
                + Character.isLowSurrogate(text.charAt(2)));
    }
}
~~~

Lưu mã nguồn bằng UTF-8, rồi biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CodePointAccessDemo.java
java CodePointAccessDemo
~~~

Kết quả chính xác:

~~~text
length=4
codePoints=3
at(0)=U+41
at(1)=U+1F600
at(2)=U+DE00
at(3)=U+42
before(1)=U+41
before(2)=U+D83D
before(3)=U+1F600
before(4)=U+42
highSurrogate=true
lowSurrogate=true
~~~

Giải thích:

- length() đếm **4 đơn vị mã UTF-16**, còn codePointCount(0, length()) đếm **3 code point**.
- codePointAt(1) và codePointBefore(3) cùng nhận ra emoji U+1F600.
- codePointAt(2) chỉ trả về low surrogate U+DE00; codePointBefore(2) chỉ trả về high surrogate U+D83D.
- %X trong printf hiển thị int dưới dạng hệ 16 với chữ A–F viết hoa, nên các dòng trên không phụ thuộc ngôn ngữ hệ thống.

## 6. Duyệt chuỗi mà không tách đôi surrogate pair

### 6.1. Duyệt từ trái sang phải

Sai lầm thường gặp:

~~~java
for (int i = 0; i < text.length(); i++) {
    int codePoint = text.codePointAt(i);
    // Xử lý codePoint...
}
~~~

Đây là **đoạn mã minh họa**, giả định biến text đã được khai báo. Với chuỗi có code point bổ sung, vòng lặp tăng i đúng **1 đơn vị mã**; sau khi đọc đủ emoji tại high surrogate, vòng tiếp theo lại đọc riêng low surrogate. Như vậy có thể xử lý dư một lần.

Cách đúng là tăng i theo **số đơn vị mã của code point vừa đọc**:

~~~java
for (int i = 0; i < text.length(); ) {
    int codePoint = text.codePointAt(i);
    System.out.printf("%d: U+%X%n", i, codePoint);
    i += Character.charCount(codePoint);
}
~~~

Character.charCount(codePoint) trả về 2 cho code point bổ sung hợp lệ và 1 cho các giá trị còn lại. Với text = "A😀B", kết quả:

~~~text
0: U+41
1: U+1F600
3: U+42
~~~

Con trỏ nhảy qua cả hai đơn vị mã của emoji: từ vị trí 1 đến vị trí 3. Nó không đứng ở low surrogate tại vị trí 2.

### 6.2. Duyệt từ phải sang trái

Khởi tạo con trỏ ở **length()** rồi dùng codePointBefore(index); sau mỗi lần đọc, trừ đúng số đơn vị mã của code point:

~~~java
for (int i = text.length(); i > 0; ) {
    int codePoint = text.codePointBefore(i);
    i -= Character.charCount(codePoint);
    System.out.printf("%d: U+%X%n", i, codePoint);
}
~~~

Với text = "A😀B", kết quả:

~~~text
3: U+42
1: U+1F600
0: U+41
~~~

**Cần lưu ý:** hai vòng lặp trên hoạt động trên các ranh giới code point khi xuất phát từ đầu/cuối chuỗi. Nếu tự đặt con trỏ ban đầu ở giữa một cặp surrogate, cả codePointAt() và codePointBefore() có thể trả về một surrogate đơn lẻ. Cần xác định offset hợp lệ từ đầu hoặc cuối chuỗi, hoặc dùng offsetByCodePoints() khi chuyển qua số lượng code point.

### 6.3. Nếu cần vị trí code point thứ n

Các phương thức codePointAt()/codePointBefore() không nhận trực tiếp **thứ tự code point**. Để tìm UTF-16 offset sau khi đi qua n code point, dùng String.offsetByCodePoints(startUtf16Offset, n), rồi mới gọi codePointAt():

~~~java
String text = "A😀B";
int utf16Offset = text.offsetByCodePoints(0, 2);
int codePoint = text.codePointAt(utf16Offset);

System.out.println(utf16Offset); // 3
System.out.printf("U+%X%n", codePoint); // U+42
~~~

Ở ví dụ này, sau hai code point A và 😀, offset UTF-16 là 3 chứ không phải 2. offsetByCodePoints() cũng cần chỉ số và khoảng dịch hợp lệ; nó có thể ném IndexOutOfBoundsException nếu vượt vùng khả dụng.

Nếu chỉ cần duyệt tất cả code point về phía trước và không cần UTF-16 offset, có thể dùng **text.codePoints()**, một IntStream các giá trị int của code point:

~~~java
String text = "A😀B";
text.codePoints().forEach(cp -> System.out.printf("U+%X%n", cp));
~~~

Đầu ra:

~~~text
U+41
U+1F600
U+42
~~~

codePoints() hữu ích khi xử lý từng code point dưới dạng luồng số, còn codePointAt()/codePointBefore() phù hợp khi cần điều khiển vị trí UTF-16 một cách tường minh.

## 7. Xử lý index rỗng, biên và lỗi

Hãy kiểm tra **giới hạn khác nhau** của hai API trước khi gọi.

| Chuỗi | Lời gọi | Kết quả |
|---|---|---|
| "AB" | codePointAt(0) | 65, tức U+0041 |
| "AB" | codePointAt(2) | Lỗi StringIndexOutOfBoundsException |
| "AB" | codePointBefore(2) | 66, tức U+0042 |
| "AB" | codePointBefore(0) | Lỗi StringIndexOutOfBoundsException |
| "" | codePointAt(0) | Lỗi StringIndexOutOfBoundsException |
| "" | codePointBefore(0) | Lỗi StringIndexOutOfBoundsException |

Hai phương thức có kiểu trả về int bởi một code point bổ sung cần hơn 16 bit; không nên ép kết quả thành char khi muốn giữ nguyên code point U+10000 trở lên. Nếu cần chuyển một code point hợp lệ thành dãy char UTF-16, có thể dùng **Character.toChars(codePoint)**.

Ví dụ chương trình độc lập kiểm tra biên:

~~~java
public class CodePointBoundaryDemo {
    public static void main(String[] args) {
        String text = "AB";
        System.out.println(text.codePointAt(0));
        System.out.println(text.codePointBefore(text.length()));

        try {
            text.codePointBefore(0);
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("Invalid before index");
        }

        try {
            text.codePointAt(text.length());
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("Invalid at index");
        }
    }
}
~~~

~~~bash
javac CodePointBoundaryDemo.java
java CodePointBoundaryDemo
~~~

Đầu ra:

~~~text
65
66
Invalid before index
Invalid at index
~~~

Trong mã thực tế, nếu đầu vào là một offset do người dùng hoặc API khác cung cấp, hãy kiểm tra miền chỉ số hoặc xử lý ngoại lệ phù hợp. Tránh tự động trừ/cộng 1 trước khi hiểu offset đó đại diện cho **đơn vị mã UTF-16**, **số thứ tự code point**, hay **vị trí hiển thị**.

## 8. Trường hợp Unicode khó: surrogate đơn lẻ và grapheme cluster

### 8.1. Surrogate không ghép thành cặp hợp lệ

Một String Java có thể chứa **surrogate đơn lẻ** (chuỗi UTF-16 không chuẩn hóa thành cặp đầy đủ). Khi codePointAt()/codePointBefore() không tìm thấy cặp high–low thích hợp, nó trả về giá trị char surrogate dưới dạng int. Phương thức không tự sửa dữ liệu lỗi thành U+FFFD và không tự ném lỗi chỉ vì gặp surrogate đơn lẻ.

Vì vậy, “giá trị int trả về từ codePointAt” không luôn có nghĩa là một *Unicode scalar value* hợp lệ: giá trị trong dải surrogate U+D800–U+DFFF là dấu hiệu của đơn vị mã surrogate chưa ghép. Nếu xử lý dữ liệu ngoài hệ thống, cần xem xét chất lượng chuỗi và quy tắc mã hóa/giải mã đầu vào.

### 8.2. Code point không phải ký tự người dùng nhìn thấy

Ví dụ một ký tự hiển thị giống "é" có thể được biểu diễn bằng chữ e (U+0065) kết hợp dấu sắc (U+0301), tức **hai code point**. Một số emoji kết hợp nhiều code point, variation selector hoặc dấu nối zero-width joiner. codePointAt()/codePointBefore() đọc **code point**, không tự gom toàn bộ *grapheme cluster* thành một ký tự hiển thị.

Vì thế:

- Muốn duyệt giá trị Unicode riêng lẻ: dùng codePointAt()/codePointBefore() hoặc codePoints().
- Muốn đếm/định vị code point: dùng codePointCount() và offsetByCodePoints().
- Muốn tách các cụm ký tự như người dùng nhìn thấy trong giao diện: cần một thuật toán phân đoạn grapheme cluster phù hợp với yêu cầu và phiên bản Unicode; codePointAt() một mình chưa đủ.

## 9. Checklist chọn API và lỗi thường gặp

1. **Đọc một đơn vị mã UTF-16:** charAt(index).
2. **Đọc một code point bắt đầu tại UTF-16 offset:** codePointAt(index).
3. **Đọc một code point trước UTF-16 offset:** codePointBefore(index).
4. **Đi qua code point khi duyệt thuận/ngược:** cộng hoặc trừ Character.charCount(codePoint), không luôn tăng/giảm 1.
5. **Chuyển số lượng code point thành UTF-16 offset:** offsetByCodePoints().
6. **Đếm code point trong một khoảng:** codePointCount(startUtf16, endUtf16).
7. **Duyệt tất cả code point dạng số:** codePoints().

Những lỗi hay gặp cần tránh:

- Xem **index** trong codePointAt()/codePointBefore() là thứ tự code point.
- Gọi codePointBefore(0) với suy nghĩ đó là “code point đầu tiên”; chỉ số 0 là một ranh giới **không có đơn vị mã nào phía trước**.
- Gọi codePointAt(length()) để lấy code point cuối; chỉ số đó đã ở **sau** cuối chuỗi.
- Duyệt bằng i++ và codePointAt(i) rồi đếm trùng một low surrogate sau khi đã ghép cặp.
- Cho rằng codePointAt() có thể ghép cặp khi index đang ở low surrogate.
- Ép code point bổ sung từ int sang char và làm mất thông tin.
- Đồng nhất code point với một “chữ” hiển thị duy nhất, đặc biệt trong tiếng Việt có dấu kết hợp hoặc emoji phức hợp.

**Kết luận:** cả **codePointAt(index)** lẫn **codePointBefore(index)** đều làm việc với offset UTF-16. codePointAt() đọc từ một vị trí về bên phải; codePointBefore() đọc ngay trước vị trí đó về bên trái. Dùng chỉ số đúng ranh giới và dịch con trỏ theo Character.charCount() để xử lý đầy đủ code point bổ sung mà không vô tình tách cặp surrogate.
