# Duyệt chuỗi theo code point mà không cắt cặp surrogate

## Vì sao i++ không luôn là “sang ký tự kế tiếp”?

Một `String` Java được truy cập theo các đơn vị UTF-16. Chỉ số của `charAt` và giá trị `length()` đều đếm đơn vị `char`. Trong khi đó, một **mã điểm Unicode (code point)** ngoài BMP được biểu diễn bằng hai `char` tạo thành cặp surrogate.

Nếu đang xử lý từng đơn vị mã, `i++` là đúng mục tiêu. Nhưng nếu đang lọc, phân loại hoặc cắt chuỗi theo mã điểm, đi từng `char` có thể khiến hai nửa của một mã điểm bị xử lý độc lập.

Cách tiếp cận cần giữ rõ hai điều:

1. Đọc được một mã điểm đầy đủ tại ranh giới hợp lệ.
2. Tăng hoặc giảm chỉ số theo số đơn vị UTF-16 của mã điểm vừa đọc.

Bài dùng API Java hiện hành, với chương trình chạy trên Java 17+. Phần duyệt theo mã điểm bảo toàn cặp surrogate hợp lệ; việc phân đoạn theo ký tự người dùng nhìn thấy là một lớp xử lý khác.

## Mô hình chuỗi dùng để thực hành

Chương trình sẽ tạo chuỗi gồm:

```text
A + U+10400 + U+1F680 + B
```

`U+10400` là một chữ thuộc hệ chữ Deseret, còn `U+1F680` là biểu tượng tên lửa. Cả hai nằm ngoài BMP và cần hai đơn vị UTF-16.

| Chỉ số UTF-16 | Đơn vị mã | Vai trò |
| --- | --- | --- |
| 0 | `0041` | A |
| 1 | `D801` | Nửa đầu của U+10400 |
| 2 | `DC00` | Nửa sau của U+10400 |
| 3 | `D83D` | Nửa đầu của U+1F680 |
| 4 | `DE80` | Nửa sau của U+1F680 |
| 5 | `0042` | B |

Độ dài UTF-16 là 6 nhưng số mã điểm là 4. Các vị trí bắt đầu mã điểm là 0, 1, 3 và 5. Một vị trí như 2 vẫn là chỉ số `char` hợp lệ, nhưng đang nằm giữa cặp surrogate.

## Duyệt xuôi: codePointAt kết hợp charCount

Mẫu cơ bản:

```java
for (int i = 0; i < text.length();) {
    int cp = text.codePointAt(i);
    // Xử lý cp dưới dạng int.
    i += Character.charCount(cp);
}
```

`codePointAt(i)` kết hợp high surrogate tại `i` với low surrogate ngay sau nó khi có cặp hợp lệ. `Character.charCount(cp)` cho biết số đơn vị UTF-16 của mã điểm để dịch chỉ số. Trong mẫu này, dữ liệu từ `codePointAt` quyết định bước 1 hoặc 2. [Java SE 25: codePointAt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePointAt(int)), [Character.charCount](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#charCount(int)).

Điều kiện vòng lặp vẫn là `i < text.length()`, vì `i` là chỉ số UTF-16. Không thay điều kiện bằng số mã điểm rồi tiếp tục dùng `i` như chỉ số `char`.

### Hai lỗi kết hợp sai thường gặp

- Đọc bằng `codePointAt(i)` nhưng luôn tăng `i++`: lần sau có thể đọc lại nửa sau cặp vừa xử lý.
- Đọc bằng `charAt(i)` rồi ép thành `int`: chỉ đổi kiểu số của một đơn vị mã, không tự ghép cặp.

Khi đã nhận `cp` dưới dạng `int`, hãy gọi các API hỗ trợ mã điểm với chính giá trị đó. Nếu ép trở lại `char`, bạn có thể làm mất phần dữ liệu của mã điểm ngoài BMP.

## Duyệt ngược: giữ một điểm kết thúc loại trừ

Mẫu đối xứng:

```java
for (int end = text.length(); end > 0;) {
    int cp = text.codePointBefore(end);
    int start = end - Character.charCount(cp);
    // Mã điểm vừa đọc nằm trong [start, end).
    end = start;
}
```

`end` không phải vị trí ký tự cần đọc; nó là ranh giới **ngay sau** vùng còn chưa xử lý. Ban đầu bằng `length()`, có thể lớn hơn chỉ số `char` cuối cùng một đơn vị.

`codePointBefore(end)` nhìn về trước ranh giới đó để nhận mã điểm. Cách giữ `end` tại ranh giới mã điểm rồi giảm theo `charCount` giúp vòng lặp đi qua toàn bộ cặp. [Java SE 25: codePointBefore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePointBefore(int)).

Đừng đổi thành `codePointAt(end - 1)` rồi mặc định tương đương: nếu `end - 1` là low surrogate, phương thức không tự tìm ngược high surrogate để ghép.

## Chương trình đầy đủ

Lưu thành `CodePointTraversalDemo.java`. Kết quả được in bằng hệ mười sáu để không phụ thuộc terminal có font Deseret hay biểu tượng tên lửa.

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class CodePointTraversalDemo {
    private static String hex(int value) {
        return String.format(Locale.ROOT, "%04X", value);
    }

    private static String units(String value) {
        return value.chars().mapToObj(CodePointTraversalDemo::hex)
                .collect(Collectors.joining(" "));
    }

    private static String takeCodePoints(String value, int max) {
        if (max < 0) {
            throw new IllegalArgumentException("Negative limit");
        }
        int count = value.codePointCount(0, value.length());
        int end = value.offsetByCodePoints(0, Math.min(max, count));
        return value.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A\uD801\uDC00\uD83D\uDE80B";
        System.out.println("units: " + units(text));
        System.out.println("UTF-16 length: " + text.length());
        System.out.println("code point count: " + text.codePointCount(0, text.length()));

        System.out.println("forward:");
        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            System.out.println(i + ": " + hex(cp));
            i += Character.charCount(cp);
        }

        System.out.println("backward:");
        for (int end = text.length(); end > 0;) {
            int cp = text.codePointBefore(end);
            int start = end - Character.charCount(cp);
            System.out.println(start + ": " + hex(cp));
            end = start;
        }

        System.out.println("stream: " + text.codePoints()
                .mapToObj(CodePointTraversalDemo::hex)
                .collect(Collectors.joining(" ")));

        StringBuilder letters = new StringBuilder();
        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            if (Character.isLetter(cp)) {
                letters.appendCodePoint(cp);
            }
            i += Character.charCount(cp);
        }
        System.out.println("letter units: " + units(letters.toString()));

        StringBuilder wrong = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (Character.isLetter(ch)) {
                wrong.append(ch);
            }
        }
        System.out.println("char filter result: " + wrong);

        System.out.println("unsafe prefix units: " + units(text.substring(0, 2)));
        System.out.println("safe prefix units: " + units(takeCodePoints(text, 2)));
        System.out.println("empty prefix length: " + takeCodePoints(text, 0).length());
        System.out.println("large limit keeps all: " + text.equals(takeCodePoints(text, 99)));

        String malformed = "\uD800Z\uDC00";
        System.out.println("unpaired values: " + malformed.codePoints()
                .mapToObj(CodePointTraversalDemo::hex)
                .collect(Collectors.joining(" ")));
        String combining = "a\u0301";
        System.out.println("combining code points: "
                + combining.codePointCount(0, combining.length()));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CodePointTraversalDemo.java
java CodePointTraversalDemo
```

Stdout:

```text
units: 0041 D801 DC00 D83D DE80 0042
UTF-16 length: 6
code point count: 4
forward:
0: 0041
1: 10400
3: 1F680
5: 0042
backward:
5: 0042
3: 1F680
1: 10400
0: 0041
stream: 0041 10400 1F680 0042
letter units: 0041 D801 DC00 0042
char filter result: AB
unsafe prefix units: 0041 D801
safe prefix units: 0041 D801 DC00
empty prefix length: 0
large limit keeps all: true
unpaired values: D800 005A DC00
combining code points: 2
```

## Đọc kết quả để biết phần nào được bảo toàn

### Duyệt xuôi và ngược đi qua cùng bốn mã điểm

Các chỉ số in ra ở hai chiều là các ranh giới UTF-16 của cùng một tập mã điểm. Vòng xuôi đi 0 → 1 → 3 → 5; vòng ngược đi 5 → 3 → 1 → 0.

Vì mỗi bước đi trọn số đơn vị mã của phần tử vừa đọc, hai vòng không biến `D801 DC00` thành hai ký tự độc lập. Việc in chỉ số vẫn có ích khi bạn cần lấy lát chuỗi, đánh dấu vị trí hoặc báo lỗi tại vị trí UTF-16.

### Lọc chữ phải xét mã điểm đầy đủ

`Character.isLetter(cp)` trong vòng duyệt mã điểm nhận được `U+10400` đầy đủ nên giữ chữ Deseret. Builder nối lại bằng `appendCodePoint(cp)` để tạo đúng hai đơn vị UTF-16 của chữ này.

Vòng `charAt` dùng để đối chiếu chỉ thấy riêng `D801` và `DC00`; cả hai không phải chữ độc lập, nên bỏ mất ký tự Deseret. Kết quả chỉ còn `AB`.

Đây là ví dụ cụ thể của lỗi **chọn sai đơn vị xử lý**. Không nên suy ra rằng mọi vòng lặp `char` đều làm hỏng dữ liệu: sao chép toàn bộ `char` theo đúng thứ tự có thể giữ nguyên biểu diễn. Lỗi xuất hiện khi điều kiện lọc hoặc thao tác biến đổi coi mỗi đơn vị mã là một ký tự hoàn chỉnh.

Khi dựng lại văn bản từ mã điểm, dùng `appendCodePoint(cp)`. `append(cp)` sẽ nối dạng số thập phân, còn `append((char) cp)` có thể cắt mất phần cao.

## Khi nào dùng String.codePoints()?

Nếu không cần theo dõi chỉ số UTF-16, `codePoints()` cho một `IntStream` tiện để duyệt hoặc lọc mã điểm. Trong chương trình, nó tạo cùng dãy số như vòng duyệt xuôi.

Phân biệt:

| API | Đơn vị cung cấp |
| --- | --- |
| `charAt(i)` | Một đơn vị UTF-16 tại chỉ số i |
| `chars()` | Từng đơn vị UTF-16, mở rộng thành int |
| `codePointAt(i)` | Mã điểm bắt đầu tại chỉ số UTF-16 i, nếu ghép được cặp |
| `codePoints()` | Dãy mã điểm sau khi kết hợp các cặp surrogate hợp lệ |

Dù phần tử của `chars()` cũng là `int`, điều đó không làm nó trở thành luồng mã điểm: hai nửa của một cặp vẫn là hai phần tử. [Java SE 25: chars](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#chars()), [codePoints](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePoints()).

Không cần tạo `toArray()` chỉ để xử lý tuần tự một lần; mảng mã điểm sẽ tạo thêm vùng nhớ theo số phần tử. Nếu dùng stream để ghi vào một builder chung, giữ xử lý tuần tự; không đổi sang luồng song song rồi cùng sửa builder đó.

## Cắt tiền tố theo số mã điểm

`substring` vẫn nhận chỉ số UTF-16. Trong chương trình, `substring(0, 2)` chỉ giữ `A` và high surrogate `D801`; nó đã chia đôi biểu diễn chữ Deseret.

`takeCodePoints` thực hiện ba việc:

1. Từ chối giới hạn âm.
2. Chọn số mã điểm thực sự lấy, không vượt số đang có.
3. Dùng `offsetByCodePoints(0, count)` để tìm chỉ số UTF-16 kết thúc, rồi gọi `substring`.

Vì điểm xuất phát là 0 và việc dịch đi qua từng mã điểm, ranh giới cuối không nằm giữa cặp surrogate hợp lệ. Các trường hợp giới hạn 0 và giới hạn lớn hơn nội dung cũng được kiểm chứng trong stdout. [Java SE 21: offsetByCodePoints](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#offsetByCodePoints(int,int)).

Cần xác định đầu vào của một hàm cắt là **số mã điểm** hay **chỉ số UTF-16**. Hai con số đó không hoán đổi được. Nếu hàm nhận sẵn một chỉ số UTF-16 tùy ý, phải bảo đảm nó không nằm giữa high và low surrogate trước khi coi đó là ranh giới bắt đầu.

`codePointAt` không tự sửa một vị trí bắt đầu sai. Trong ví dụ, gọi nó tại chỉ số 2 vẫn đang bắt đầu từ low surrogate. Tương tự, đừng dùng một chỉ số nằm giữa cặp làm điểm gốc cho `offsetByCodePoints` rồi mong API tự tìm lại ranh giới mong muốn.

### Tránh tính lại vị trí từ đầu cho mọi phần tử

Nếu muốn duyệt toàn chuỗi, hãy giữ chỉ số và tăng tuần tự như vòng `for`. Liên tục gọi `offsetByCodePoints(0, k)` với `k = 0, 1, 2, ...` có thể phải đi lại các tiền tố nhiều lần. Đó là công việc thừa mà vòng duyệt một lần tránh được.

Hàm `takeCodePoints` trong ví dụ đếm toàn chuỗi để xử lý giới hạn vượt nội dung rồi tìm điểm kết thúc. Nếu chỉ cần tiền tố ngắn của một chuỗi rất lớn, có thể triển khai một vòng tiến tối đa `max` mã điểm và dừng sớm, vẫn giữ nguyên quy tắc bước nhảy.

## Surrogate đứng riêng: duyệt không có nghĩa là xác thực

Một `String` có thể chứa high hoặc low surrogate không ghép cặp. Các API duyệt trong bài không tự bảo đảm toàn bộ chuỗi là UTF-16 hợp lệ.

Chương trình tạo `"\uD800Z\uDC00"`. `codePoints()` trả ra `D800`, `005A` và `DC00`, thay vì tự ném lỗi hay sửa thành một chuỗi khác. Hai surrogate không đứng sát nhau để tạo cặp.

Vì vậy, lời bảo đảm đúng là: cách duyệt này **không chia đôi cặp surrogate hợp lệ đang có khi xuất phát từ ranh giới phù hợp**. Nó không chứng minh dữ liệu nguồn không có lỗi.

Nếu ứng dụng yêu cầu văn bản hợp lệ, cần chính sách đầu vào rõ ràng: từ chối surrogate đơn, thay thế theo quy tắc đã chọn hoặc xử lý ở bước giải mã nguồn. Không dùng `codePointCount` hay `codePoints` như một phép xác thực chỉ vì chúng có từ “code point”.

Khi nguồn được chia thành các khối `char` riêng, ranh giới khối có thể nằm giữa một cặp. Nếu xử lý như dữ liệu liên tục, phải giữ lại high surrogate cuối khối để xét cùng đầu khối sau; mẫu vòng lặp trên một `String` hoàn chỉnh không tự quản lý trạng thái giữa các khối.

## Bảo toàn mã điểm chưa chắc bảo toàn ký tự hiển thị

`"a\u0301"` trong chương trình gồm chữ `a` và dấu sắc kết hợp. Số mã điểm bằng 2, nhưng chúng có thể tạo một cụm ký tự mà người đọc cảm nhận như một chữ có dấu.

Cắt sau mã điểm đầu không chia cặp surrogate nào, nhưng làm mất dấu kết hợp khỏi cụm ban đầu. Một số chuỗi emoji cũng gồm nhiều mã điểm. Bài toán di chuyển con trỏ, xóa một ký tự trên giao diện hoặc giới hạn tên hiển thị thường cần ranh giới **cụm tự vị (grapheme cluster)**. [Unicode UAX #29: phân đoạn văn bản](https://www.unicode.org/reports/tr29/).

Hãy chọn đúng lớp xử lý: đơn vị UTF-16 cho chỉ số API, mã điểm cho phân loại Unicode, và cụm tự vị cho nhiều thao tác gắn với cách người dùng nhìn ký tự.

## Thực hành

1. Thay `U+10400` trong ví dụ bằng một chữ BMP và giải thích các chỉ số vòng duyệt thay đổi thế nào.
2. Sửa vòng duyệt xuôi thành `i++`, in mã điểm từng lượt và xác định phần dữ liệu bị đọc thêm.
3. Viết hàm lấy phần đuôi có tối đa hai mã điểm bằng `offsetByCodePoints` với độ lệch âm từ `length()`; xử lý riêng trường hợp chuỗi có ít hơn hai mã điểm.
4. Kiểm tra hàm tiền tố với chuỗi rỗng, chỉ một mã điểm ngoài BMP và giới hạn âm.
5. Nêu lý do một tiền tố không chia cặp surrogate vẫn có thể cắt mất dấu kết hợp hoặc một phần của chuỗi emoji.

Mẫu cần nhớ là **đọc mã điểm đầy đủ, xử lý dưới dạng int, rồi dịch chỉ số bằng số đơn vị UTF-16 tương ứng**. Khi tạo kết quả mới, nối lại bằng API nhận mã điểm và chỉ cắt ở ranh giới đã xác định.
