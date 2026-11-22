# Xử lý `null` và dữ liệu không được nhận diện khi dùng `switch` với `String` trong Java

## 1. Mục tiêu của bài học

Khi dùng `switch` để xử lý lệnh, trạng thái hoặc loại thông điệp dưới dạng `String`, dữ liệu nhận được có thể hợp lệ, `null`, rỗng, chỉ chứa khoảng trắng hoặc có giá trị không thuộc danh sách được hỗ trợ. Một chương trình cần **phân biệt những trường hợp đó** trước khi quyết định hành động. Mặc định chạy nhầm một lệnh hoặc phát sinh `NullPointerException` ngoài ý muốn đều là biểu hiện xử lý đầu vào chưa rõ ràng.

Sau bài này, bạn sẽ biết:

- Phân biệt `null`, chuỗi rỗng `""`, chuỗi trắng, chuỗi chữ `"null"` và chuỗi không được nhận diện.
- Hiểu chính xác cách `switch` so khớp `String` và vai trò của `case`, `default`.
- Chọn một trong hai cách xử lý `null`: kiểm tra ở biên đầu vào hoặc sử dụng `case null` từ **Java 21**.
- Quyết định lúc nào nên chuẩn hóa chữ hoa/thường và khoảng trắng, lúc nào phải so khớp nguyên văn.
- Trả về kết quả rõ nghĩa cho dữ liệu không hợp lệ thay vì vô tình thực hiện một hành động khác.

**Phạm vi phiên bản:** `switch` nhận `String` từ **Java 7** và vẫn hữu ích trong Java hiện đại; cú pháp `case null` trở thành tính năng chuẩn từ **Java 21** (JEP 441). Ví dụ chạy được bên dưới sử dụng **JDK hỗ trợ `--release 21`**; không cần Java 7 cũ, thư viện lỗi thời hay chế độ preview.

## 2. Phân loại dữ liệu trước khi chọn nhánh

Hãy hình dung chương trình nhận một lệnh văn bản: `"start"`, `"stop"` hoặc `"status"`. Những đầu vào sau có ý nghĩa khác nhau:

| Đầu vào | Ý nghĩa có thể có | Xử lý đề xuất trong ví dụ |
| --- | --- | --- |
| `"start"` | Lệnh hợp lệ | `START` |
| `"stop"` | Lệnh hợp lệ | `STOP` |
| `"status"` | Lệnh hợp lệ | `STATUS` |
| `null` | Không có đối tượng chuỗi; ví dụ trường đầu vào vắng mặt | `MISSING` |
| `""` | Có chuỗi nhưng không chứa ký tự | `EMPTY` |
| `"   "` | Có chuỗi nhưng chỉ là khoảng trắng | `EMPTY` nếu chính sách cho phép bỏ khoảng trắng |
| `"pause"` | Có dữ liệu, nhưng lệnh chưa được hỗ trợ | `UNKNOWN` |
| `"START"` | Khác chữ hoa/thường so với `"start"` | Hợp lệ chỉ khi quy tắc cho phép chuẩn hóa |
| `"null"` | Bốn chữ cái `n`, `u`, `l`, `l` | Là một chuỗi bình thường; không phải giá trị `null` |

Đó là **quy tắc xử lý đầu vào của ví dụ**, không phải quy tắc tự động do `switch` thiết lập. Ứng dụng thực tế có thể phân biệt thêm “không gửi trường”, “gửi `null`” và “gửi chuỗi rỗng” ở lớp kiểm tra request; thông tin này có thể mất nếu đã ép tất cả về một biến `String`.

Lưu ý: `null` không phải chuỗi rỗng. Đối tượng `String` có thể chứa không ký tự nào, còn biến tham chiếu `null` không trỏ đến đối tượng nào. Không gọi `raw.strip()`, `raw.isEmpty()` hay phương thức khác trước khi đã xử lý `raw == null`.

## 3. `switch` với `String` thực sự so khớp như thế nào?

Với một chuỗi hợp lệ, `case` so khớp **nội dung chuỗi**, phân biệt chữ hoa/thường. Hai đối tượng `String` khác nhau nhưng có nội dung giống nhau vẫn được đưa vào cùng nhánh; không phụ thuộc việc chuỗi có được intern hay không.

~~~java
String command = new String("start");

switch (command) {
    case "start" -> System.out.println("Đã nhận START");
    default -> System.out.println("Lệnh không được hỗ trợ");
}
~~~

Đoạn trên chỉ minh họa cơ chế và có thể đặt trong một phương thức; nó không phải một file chương trình độc lập. Kết quả khi chạy đoạn code là `Đã nhận START`. `switch` không tự bỏ khoảng trắng, không tự đổi `"START"` thành `"start"` và không tự nhận dạng bí danh như `"run"`.

Các nhãn `case` kiểu chuỗi phải là **hằng biên dịch** (`"start"` hoặc một `static final String` được khởi tạo bằng biểu thức hằng hợp lệ). Không thể đặt một biến `String` thay đổi tại runtime sau `case`. Nếu giá trị cấu hình hoặc danh sách lệnh có thể thay đổi lúc chạy, cách ánh xạ bằng `Map` hoặc bộ xử lý riêng có thể phù hợp hơn.

`default` dành cho **giá trị không khớp các `case`**, chẳng hạn `"pause"`. Điểm dễ sai nhất: `default` **không tự bắt `null`**. Nếu không có nhánh `case null` hợp lệ, `switch` trên tham chiếu `null` ném `NullPointerException` trước khi chọn `default`.

Cú pháp mũi tên `case "start" -> ...` giúp từng nhánh không vô ý chạy tiếp sang nhánh sau; khi cần trả về một kết quả thì `switch` **expression** (biểu thức `switch`) rất phù hợp. Với kiểu selector `String`, biểu thức `switch` phải có nhánh bao phủ các giá trị không nhận diện, thường là `default`.

## 4. Hai phương án xử lý `null` còn áp dụng hiện nay

### Phương án A: kiểm tra `null` trước khi `switch`

Đây là cách rõ ràng, dùng được ngay cả khi mức Java đích chưa có `case null`:

~~~java
static String classify(String command) {
    if (command == null) {
        return "MISSING";
    }
    return switch (command) {
        case "start" -> "START";
        case "stop" -> "STOP";
        case "status" -> "STATUS";
        default -> "UNKNOWN";
    };
}
~~~

Đoạn này là **phương thức minh họa**, cần được đặt trong lớp Java thích hợp để chạy. Sau kiểm tra `null`, chương trình bảo đảm selector không null. Nó cố ý so khớp nguyên văn: `"START"`, `" status "`, `""` và `"pause"` đều vào `default`. Nếu cần phân biệt chuỗi rỗng với lệnh không hỗ trợ, hãy kiểm tra chuỗi rỗng trước `switch`.

### Phương án B: khai báo `case null` trực tiếp (Java 21 trở lên)

~~~java
static String classifyExact(String command) {
    return switch (command) {
        case null -> "MISSING";
        case "start" -> "START";
        case "stop" -> "STOP";
        case "status" -> "STATUS";
        default -> "UNKNOWN";
    };
}
~~~

Phương thức minh họa này có thể biên dịch với `javac --release 21` và **không cần `--enable-preview`**. Khi selector `null`, `case null` chạy. Khi chuỗi khác tất cả lệnh hợp lệ, `default` chạy. Đó là hai nhánh có mục đích khác nhau.

**Ranh giới phiên bản:** Có `switch` trên `String` từ Java 7 **không đồng nghĩa** với có `case null` từ Java 7. Nếu dự án chọn mức ngôn ngữ trước Java 21, dùng kiểm tra `null` bên ngoài như phương án A. Không copy `case null` vào code biên dịch với `--release 17` rồi kỳ vọng cú pháp đó được hỗ trợ như tính năng chuẩn của Java 17.

## 5. Ví dụ hoàn chỉnh: chuẩn hóa có kiểm soát, phân biệt đầu vào lỗi

Ví dụ sau minh họa **hai chính sách xử lý khác nhau**. Hàm `normalizeAndRoute` chấp nhận khoảng trắng bao quanh và khác biệt chữ hoa/thường theo quy tắc bài học. Hàm `exactRoute` giữ nguyên nội dung để chứng minh `switch` vốn phân biệt chính xác từng chuỗi.

Tạo file `src/main/java/demo/StringCommandExample.java` trong thư mục ví dụ:

~~~java
package demo;

import java.util.Locale;

public final class StringCommandExample {
    private StringCommandExample() {
    }

    enum Decision {
        START, STOP, STATUS, MISSING, EMPTY, UNKNOWN
    }

    static Decision normalizeAndRoute(String raw) {
        if (raw == null) {
            return Decision.MISSING;
        }
        String command = raw.strip().toLowerCase(Locale.ROOT);
        if (command.isEmpty()) {
            return Decision.EMPTY;
        }
        return switch (command) {
            case "start" -> Decision.START;
            case "stop" -> Decision.STOP;
            case "status" -> Decision.STATUS;
            default -> Decision.UNKNOWN;
        };
    }

    static Decision exactRoute(String raw) {
        return switch (raw) {
            case null -> Decision.MISSING;
            case "start" -> Decision.START;
            case "stop" -> Decision.STOP;
            case "status" -> Decision.STATUS;
            default -> Decision.UNKNOWN;
        };
    }

    public static void main(String[] args) {
        String[] requests = {null, "start", " STATUS ", "stop", "pause", "", "null"};
        for (String request : requests) {
            String display = request == null ? "<null>" : "\"" + request + "\"";
            System.out.println(display + " => " + normalizeAndRoute(request));
        }
        System.out.println("exact null => " + exactRoute(null));
        System.out.println("exact STATUS => " + exactRoute("STATUS"));
        System.out.println("exact start => " + exactRoute("start"));
    }
}
~~~

Từ thư mục chứa `src/`, chạy bằng JDK có trình biên dịch hỗ trợ Java 21:

~~~sh
javac --release 21 -encoding UTF-8 -d out src/main/java/demo/StringCommandExample.java
java -cp out demo.StringCommandExample
~~~

Kết quả stdout chính xác:

~~~text
<null> => MISSING
"start" => START
" STATUS " => STATUS
"stop" => STOP
"pause" => UNKNOWN
"" => EMPTY
"null" => UNKNOWN
exact null => MISSING
exact STATUS => UNKNOWN
exact start => START
~~~

**Phân tích các bước:**

1. `normalizeAndRoute(null)` trả `MISSING` ngay ở đầu. Không gọi phương thức nào trên `null`.
2. `raw.strip()` (API có từ Java 11) loại bỏ ký tự khoảng trắng đầu/cuối theo định nghĩa Java; `toLowerCase(Locale.ROOT)` chuyển chữ theo locale trung lập với dữ liệu lệnh nội bộ. Vì vậy `" STATUS "` thành `"status"` và được nhận.
3. Sau chuẩn hóa, `isEmpty()` giúp phân biệt chuỗi trắng với chuỗi không thuộc danh sách được phép: chuỗi `""` thành `EMPTY`, còn `"pause"` thành `UNKNOWN`.
4. `switch` expression trả trực tiếp một hằng `Decision`; `default` không thực hiện bất kỳ hành động nào, chỉ trả `UNKNOWN`.
5. Trong `exactRoute`, `case null` bảo vệ selector null; `"STATUS"` không bằng `"status"`, nên kết quả là `UNKNOWN`.
6. `"null"` gồm bốn ký tự, khác hoàn toàn tham chiếu `null`. Bài không coi một chuỗi văn bản đặc biệt là tín hiệu thiếu dữ liệu.

**Lưu ý:** `Decision` ở đây là kiểu kết quả minh họa để chương trình chạy độc lập. Trong ứng dụng lớn, có thể dùng kiểu kết quả phân tích riêng (ví dụ kết quả thành công kèm `Command` hoặc lỗi có mã cụ thể) để không trộn lệnh được phép với lỗi đầu vào.

## 6. Lúc nào nên chuẩn hóa, lúc nào phải giữ nguyên?

### 6.1. Chuẩn hóa khi giao diện đầu vào quy định cho phép

Đối với lệnh do người dùng nhập tự do, có thể chấp nhận `" START "` như `"start"` để thuận tiện. Khi đó cần ghi **quy tắc đầu vào** rõ ràng: có bỏ khoảng trắng hai đầu không, có phân biệt hoa/thường không, và có chấp nhận bí danh không.

- Dùng `strip()` nếu chấp nhận bỏ các ký tự khoảng trắng được Java nhận diện ở hai đầu; `strip()` không xóa mọi ký tự vô hình theo mọi định nghĩa Unicode.
- Dùng `toLowerCase(Locale.ROOT)` cho token kỹ thuật không phụ thuộc ngôn ngữ giao diện; tránh để quy tắc của locale máy chủ làm thay đổi cách khớp.
- Không tự động xóa khoảng trắng **ở giữa** hoặc đổi ký tự nếu giao thức không quy định. `"st art"` không phải `"start"`.
- Nếu cần chặn đầu vào quá dài, thực hiện giới hạn độ dài phù hợp trước công việc chuẩn hóa hoặc phân tích tốn kém.

### 6.2. Không chuẩn hóa vô điều kiện

Với mã truy cập, khóa, token bảo mật, chữ ký, định danh phân biệt hoa/thường, giá trị cấu hình có cú pháp xác định hoặc trường dữ liệu giao thức, một phép `strip()` hay `toLowerCase(...)` có thể **thay đổi ý nghĩa**. Giữ nguyên văn bản và so khớp theo đặc tả hệ thống.

Nếu ứng dụng phải chấp nhận nhiều cách viết, nên tạo bảng ánh xạ rõ ràng và kiểm thử từng cách; đừng ngầm suy luận rằng hai dạng trông giống nhau luôn tương đương về Unicode hoặc về ý nghĩa nghiệp vụ.

## 7. Chính sách cho dữ liệu không được nhận diện

`default` chỉ báo rằng không có `case` nào tương ứng; **hành động** cần làm khi gặp một lệnh không nhận diện là quyết định thiết kế.

| Bối cảnh | Phản ứng phù hợp | Lý do |
| --- | --- | --- |
| Dữ liệu đầu vào bắt buộc mà bị `null` | Báo lỗi thiếu dữ liệu | Giúp phân biệt thiếu với sai giá trị |
| Chuỗi rỗng hoặc trắng | Báo lỗi trống theo quy tắc giao diện | Người gửi có thể sửa cụ thể |
| Giá trị lạ, như `"pause"` | Trả `UNKNOWN`/lỗi validation, ghi nhận giá trị an toàn | Tránh chọn một lệnh không liên quan |
| Trường không bắt buộc, có mặc định được quy định rõ | Áp dụng mặc định **chỉ** cho trường hợp được phép | Không tự biến giá trị sai thành giá trị hợp lệ |
| Lệnh ảnh hưởng quyền truy cập, thay đổi dữ liệu hoặc công việc nhạy cảm | Từ chối lệnh không nhận diện | Không mở ra hành vi ngoài danh sách cho phép |

Trong API HTTP, lớp validation có thể ánh xạ đầu vào thiếu hoặc sai sang phản hồi lỗi phía client (thường là nhóm `4xx` theo hợp đồng API), còn bộ phân nhánh chỉ làm việc với lệnh hợp lệ đã được xác nhận. Không nên để `default` gọi nhánh “cho phép”, tạo tài nguyên hoặc thực thi lệnh ngẫu nhiên.

Nếu cần nhật ký, ghi **mã phân loại lỗi** hoặc giá trị đã được kiểm soát; không đưa thông tin nhạy cảm từ đầu vào trực tiếp vào log chỉ để gỡ lỗi. Với danh sách lệnh cố định, `enum` thường phù hợp sau bước parse, vì phần xử lý nghiệp vụ không phải tiếp tục so khớp các chuỗi tùy ý.

## 8. Các lỗi dễ gặp và cách sửa

| Lỗi | Điều xảy ra | Cách khắc phục |
| --- | --- | --- |
| Tưởng `default` bắt mọi trường hợp, kể cả `null` | Có thể nhận `NullPointerException` khi selector null | Kiểm tra `null` trước hoặc dùng `case null` ở mức Java 21+ |
| Gọi `raw.strip()` trước `raw == null` | Ném `NullPointerException` ngay tại bước chuẩn hóa | Kiểm tra tham chiếu trước khi gọi phương thức |
| Dùng `case "start"` và mong khớp `"START"` | Không khớp vì phân biệt chữ hoa/thường | Xác định chính sách phân biệt chữ; chuẩn hóa nếu được phép |
| Gộp `null`, `""` và giá trị lạ vào một mặc định | Không thể báo lỗi chính xác, khó phân tích sự cố | Phân biệt `MISSING`, `EMPTY`, `UNKNOWN` |
| `default` mặc định làm hành động có quyền | Đầu vào lạ có thể gây tác dụng phụ nguy hiểm | Trả lỗi hoặc từ chối; chỉ thực thi lệnh đã được nhận diện |
| Copy `case null` vào `--release 17` | Cú pháp chưa là tính năng chuẩn của Java 17 | Chọn `--release 21` hoặc kiểm tra `null` ở bên ngoài |
| Chuẩn hóa mọi String nhận được | Có thể biến đổi token/định danh phân biệt hoa/thường | Chỉ chuẩn hóa khi đặc tả đầu vào cho phép |
| Dùng `==` để tự so sánh hai `String` | So sánh tham chiếu, không so nội dung | Dùng `equals`/`Objects.equals` khi so sánh thủ công; `switch` với `String` đã so khớp nội dung |
| Bỏ `default` khỏi `switch` expression kiểu `String` | Không bao phủ hết các giá trị có thể gặp | Thêm nhánh `default` và quy định rõ lỗi không nhận diện |

Đối với phương án so sánh thủ công, `"start".equals(raw)` là cách so sánh nội dung an toàn với `null`; `raw.equals("start")` không an toàn nếu `raw` có thể null. Điều này hữu ích khi chỉ có một hoặc hai giá trị; khi có nhiều lệnh, `switch` rõ ràng hơn nếu danh sách trường hợp cố định.

## 9. Tự luyện và kiểm tra hiểu đúng

**Bài 1.** Hàm `exactRoute` ở ví dụ trả gì với `null`, `"start"`, `"START"` và `"pause"`?

**Đáp án:** `MISSING`, `START`, `UNKNOWN`, `UNKNOWN` theo thứ tự. `case null` xử lý thiếu dữ liệu; `default` xử lý chuỗi có nội dung nhưng không khớp.

**Bài 2.** Hàm `normalizeAndRoute` trả gì với `"  stop  "`, `"   "` và `"unknown"`?

**Đáp án:** `STOP`, `EMPTY`, `UNKNOWN`. Kết quả này phụ thuộc vào quy tắc chuẩn hóa đã được khai báo trong hàm.

**Bài 3.** Vì sao chỉ có `default -> "UNKNOWN"` không bảo đảm an toàn với selector `null`?

**Đáp án:** `default` dành cho giá trị không khớp nhãn `case`. Nếu selector null mà không có nhánh cho null, `switch` phát sinh `NullPointerException`.

**Bài 4.** Một giao thức định nghĩa `"Start"` và `"start"` là hai mã khác nhau. Có nên gọi `toLowerCase(Locale.ROOT)` trước `switch`?

**Đáp án:** Không; làm vậy đánh mất sự khác nhau do giao thức quy định. Giữ nguyên dữ liệu và viết các nhánh chính xác.

**Bài 5.** Một chương trình định chạy `START` trong nhánh `default` để người dùng “không cần nhớ lệnh”. Rủi ro là gì?

**Đáp án:** Mọi lỗi gõ, chuỗi lạ hoặc dữ liệu hỏng có thể vô tình kích hoạt `START`. Chỉ áp dụng giá trị mặc định khi hợp đồng đầu vào cho phép rõ ràng, còn lệnh không nhận diện nên bị từ chối hoặc báo lỗi.

## 10. Checklist khi triển khai

- [ ] Xác định `null` có nghĩa “vắng mặt” và chuỗi rỗng có cần phân biệt hay không.
- [ ] Đảm bảo xử lý `null` trước khi gọi phương thức trên chuỗi hoặc đã có `case null` với mức Java phù hợp.
- [ ] Có `default` cho dữ liệu ngoài danh sách, không âm thầm biến đầu vào sai thành hành động có tác dụng phụ.
- [ ] Xác định chính sách khoảng trắng, chữ hoa/thường và alias trước khi chuẩn hóa; không đổi dữ liệu khi đặc tả yêu cầu so khớp nguyên văn.
- [ ] Trả kết quả có nghĩa và giữ phần thực thi nghiệp vụ sau bước nhận diện/validation.
- [ ] Kiểm thử ít nhất: `null`, `""`, chuỗi trắng, giá trị đúng, khác hoa/thường, không nhận diện và chuỗi chữ `"null"`.
- [ ] Chọn mức Java mục tiêu và biên dịch thật; kiểm tra stdout thực tế thay vì chỉ dự đoán.

**Tài liệu chính thức:** [Java SE 21 Language Specification — `switch` statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11), [`switch` expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28) và [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441). Các tài liệu này xác nhận việc dùng `case null` từ Java 21, còn ví dụ trong bài sử dụng các API và cú pháp vẫn được hỗ trợ hiện nay.