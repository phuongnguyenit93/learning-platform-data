# Vì sao `String.split()` đơn giản không đủ để phân tích CSV có dấu nháy

## 1. Vấn đề cốt lõi

CSV (Comma-Separated Values) thường dùng dấu phẩy để ngăn cách các trường, nhưng **dấu phẩy không phải lúc nào cũng là dấu phân cách**. Một trường được bao bởi dấu nháy kép (`"..."`) có thể chứa dấu phẩy, dấu xuống dòng và dấu nháy kép được mã hóa bằng hai dấu nháy liên tiếp (`""`). Vì vậy, không thể coi mọi dấu phẩy trong chuỗi là ranh giới trường.

Ví dụ, bản ghi:

~~~csv
101,"Nguyễn, An","Nói ""xin chào""",active
~~~

có đúng **4 trường**, lần lượt là:

1. `101`
2. `Nguyễn, An`
3. `Nói "xin chào"`
4. `active`

Nếu dùng `line.split(",")`, Java sẽ tách cả dấu phẩy nằm **bên trong** `"Nguyễn, An"`, khiến số trường và vị trí dữ liệu sai. `split` chỉ tìm vị trí khớp biểu thức chính quy; nó không theo dõi ngữ cảnh “đang ở trong hay ngoài dấu nháy”.

CSV không phải một định dạng có duy nhất một biến thể: RFC 4180 mô tả một quy ước phổ biến, còn dữ liệu thực tế có thể dùng dấu chấm phẩy, quy tắc khoảng trắng hoặc cách escape khác. Khi xử lý CSV cần biết **dialect** (quy ước định dạng) của nguồn dữ liệu.

## 2. Những tình huống `split` dễ xử lý sai

| Dòng CSV đầu vào | Các trường cần thu được | Vấn đề khi tách bằng dấu phẩy |
| --- | --- | --- |
| `a,b,c` | `a`, `b`, `c` | Trường hợp đơn giản: `split` hoạt động |
| `1,"Lan, An",3` | `1`, `Lan, An`, `3` | Dấu phẩy trong trường được nháy bị tách nhầm |
| `1,"a""b",3` | `1`, `a"b`, `3` | `split` không giải mã `""` thành `"` |
| `a,b,` | `a`, `b`, trường rỗng | `split(",")` mặc định bỏ trường rỗng ở cuối |
| `"Dòng 1\nDòng 2",ok` | Trường đầu chứa ký tự xuống dòng thật; trường sau là `ok` | Đọc từng dòng vật lý có thể cắt đôi một bản ghi |

Ở hàng cuối của bảng, `\n` dùng để **biểu diễn** một ký tự xuống dòng nằm trong cặp nháy; một tệp CSV thực có thể chứa dòng vật lý kế tiếp ngay giữa trường này.

### `split(",")` và `split(",", -1)` khác nhau thế nào?

Trong Java, `String.split(regex)` tương đương `String.split(regex, 0)`: các trường rỗng ở **cuối** kết quả bị loại bỏ. Dùng `limit = -1` giúp giữ chúng, nhưng **không** giải quyết dấu phẩy trong nháy hoặc giải mã dấu nháy kép.

~~~java
import java.util.Arrays;

public class SplitLimitDemo {
    public static void main(String[] args) {
        System.out.println(Arrays.toString("a,b,".split(",")));
        System.out.println(Arrays.toString("a,b,".split(",", -1)));

        String csv = "1,\"Lan, An\",3";
        String[] wrong = csv.split(",", -1);
        System.out.println(wrong.length);
        System.out.println(wrong[1]);
        System.out.println(wrong[2]);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SplitLimitDemo.java
java SplitLimitDemo
~~~

Kết quả chính xác:

~~~text
[a, b]
[a, b, ]
4
"Lan
 An"
~~~

Giữ trường rỗng ở cuối là một phần của xử lý CSV, nhưng dùng `-1` vẫn tạo ra **4 mảnh** thay vì **3 trường** đối với `1,"Lan, An",3`. Cũng cần nhớ rằng đối số đầu tiên của `split` là **regex** chứ không phải chuỗi phân cách theo nghĩa đen; kể cả dùng `Pattern.quote(delimiter)` đúng cách cũng không khiến nó hiểu quy tắc nháy CSV.

## 3. Quy tắc nhận diện một trường CSV

Với biến thể phổ biến dùng dấu phẩy và dấu nháy kép:

- **Ngoài cặp nháy:** dấu phẩy kết thúc trường; dấu xuống dòng kết thúc bản ghi.
- **Bên trong cặp nháy:** dấu phẩy và dấu xuống dòng là **dữ liệu** thuộc cùng một trường.
- **Hai dấu nháy liền nhau** `""` ở bên trong trường được nháy biểu thị **một** dấu `"` trong giá trị.
- **Sau dấu nháy đóng:** với parser nghiêm ngặt, ký tự hợp lệ tiếp theo chỉ là dấu phẩy, ký tự kết thúc bản ghi hoặc hết dữ liệu. Dữ liệu như `"abc"x` là không hợp lệ.
- **Trường rỗng:** `a,,b` có trường thứ hai rỗng; `a,b,` có trường cuối rỗng; `""` là một trường được nháy nhưng có giá trị rỗng.
- **Kết thúc bản ghi:** `\r\n` thường dùng trong CSV kiểu RFC 4180; một số nguồn dùng `\n` hoặc `\r`. Parser phải phân biệt dấu xuống dòng bên ngoài nháy và bên trong nháy.

Một bộ phân tích hợp lệ phải **giữ trạng thái** theo từng ký tự hoặc dùng thư viện đã hiện thực các quy tắc đó; không thể quyết định chỉ từ chính ký tự dấu phẩy.

Có thể hình dung bốn trạng thái:

| Trạng thái | Ý nghĩa | Xử lý chính |
| --- | --- | --- |
| `START` | Đầu trường, chưa có nội dung | `"` mở trường có nháy; dấu phẩy tạo trường rỗng |
| `UNQUOTED` | Đang đọc trường không có nháy | Dấu phẩy hoặc hết bản ghi kết thúc trường; dấu `"` giữa trường là lỗi theo quy tắc nghiêm ngặt |
| `QUOTED` | Đang đọc trường trong nháy | Chấp nhận dấu phẩy, `\r` và `\n` như dữ liệu; `""` thêm một dấu `"` |
| `AFTER_QUOTE` | Đã đọc dấu nháy đóng | Chỉ cho phép dấu phẩy, hết bản ghi hoặc EOF |

## 4. Ví dụ Java 17+: phân tích đúng dấu nháy, xuống dòng và trường rỗng

Ví dụ dưới đây là **chương trình đầy đủ**, dùng bộ quét trạng thái cho một biến thể CSV cụ thể: dấu phân cách là `,`, dấu bao trường là `"`, escape dấu nháy bằng `""`, cho phép `CRLF`/`LF`/`CR` làm ranh giới bản ghi, và không bỏ qua khoảng trắng sau dấu nháy đóng. Mục đích là thấy rõ cơ chế; với tệp lớn hoặc dữ liệu không đáng tin cậy, nên dùng thư viện CSV đã được kiểm thử kỹ.

Lưu dưới tên `CsvExample.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class CsvExample {
    private enum State { START, UNQUOTED, QUOTED, AFTER_QUOTE }

    public static List<List<String>> parse(String input) {
        List<List<String>> records = new ArrayList<>();
        List<String> record = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        State state = State.START;
        boolean lastWasRecordSeparator = false;

        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);

            if (state == State.QUOTED) {
                if (ch == '"') {
                    if (i + 1 < input.length()
                            && input.charAt(i + 1) == '"') {
                        field.append('"');
                        i++; // Hai dấu nháy trong CSV tạo một dấu nháy.
                    } else {
                        state = State.AFTER_QUOTE;
                    }
                } else {
                    field.append(ch); // Bao gồm dấu phẩy và xuống dòng.
                }
                lastWasRecordSeparator = false;
                continue;
            }

            if (ch == ',') {
                record.add(field.toString());
                field.setLength(0);
                state = State.START;
                lastWasRecordSeparator = false;
            } else if (ch == '\r' || ch == '\n') {
                record.add(field.toString());
                records.add(record);
                record = new ArrayList<>();
                field.setLength(0);
                state = State.START;
                lastWasRecordSeparator = true;

                // Ngoài nháy, CRLF chỉ kết thúc một bản ghi.
                if (ch == '\r' && i + 1 < input.length()
                        && input.charAt(i + 1) == '\n') {
                    i++;
                }
            } else if (state == State.AFTER_QUOTE) {
                throw new IllegalArgumentException(
                        "Ký tự sau dấu nháy đóng tại vị trí " + i);
            } else if (state == State.START && ch == '"') {
                state = State.QUOTED;
                lastWasRecordSeparator = false;
            } else if (ch == '"') {
                throw new IllegalArgumentException(
                        "Dấu nháy không hợp lệ tại vị trí " + i);
            } else {
                field.append(ch);
                state = State.UNQUOTED;
                lastWasRecordSeparator = false;
            }
        }

        if (state == State.QUOTED) {
            throw new IllegalArgumentException("Thiếu dấu nháy đóng");
        }

        // Không tạo bản ghi giả sau dấu xuống dòng kết thúc tệp.
        // Nhưng vẫn giữ trường rỗng cuối cùng nếu tệp kết thúc bằng ','.
        if (!input.isEmpty() && !lastWasRecordSeparator) {
            record.add(field.toString());
            records.add(record);
        }

        return records;
    }

    public static void main(String[] args) {
        String csv =
                "id,name,quote,note\r\n" +
                "1,\"Nguyễn, An\",\"Nói \"\"xin chào\"\"\","
                        + "\"Dòng 1\nDòng 2\"\r\n" +
                "2,Bình,,\r\n";

        List<List<String>> rows = parse(csv);
        System.out.println(rows.size());
        System.out.println(rows.get(1).get(1));
        System.out.println(rows.get(1).get(2));
        System.out.println(
                rows.get(1).get(3).replace("\n", "\\n"));
        System.out.println(rows.get(2).size());
        System.out.println(rows.get(2).get(3).isEmpty());
    }
}
~~~

Biên dịch và chạy (terminal có JDK 17 trở lên):

~~~bash
javac -encoding UTF-8 CsvExample.java
java CsvExample
~~~

`stdout`:

~~~text
3
Nguyễn, An
Nói "xin chào"
Dòng 1\nDòng 2
4
true
~~~

Giải thích kết quả:

1. Có **3 bản ghi logic**: một header và hai bản ghi dữ liệu. Trường `note` của bản ghi đầu chứa `\n` thật nhưng không tạo thêm bản ghi.
2. Trường `name` giữ nguyên dấu phẩy `Nguyễn, An`.
3. Hai dấu nháy kép `""` của CSV được giải mã thành một dấu nháy trong `Nói "xin chào"`.
4. Bản ghi thứ hai vẫn có **4 trường**, kể cả hai trường rỗng ở cuối.

Parser trên cố ý **nghiêm ngặt**: nó báo lỗi với nháy chưa đóng, nháy xuất hiện giữa trường không có nháy, hoặc ký tự bất hợp lệ ngay sau nháy đóng. Nó đọc toàn bộ `String` vào bộ nhớ, không phát hiện lỗi số cột không đồng nhất, không xử lý BOM, không cho tùy biến delimiter hay cách escape; đó là giới hạn rõ ràng của **ví dụ học cơ chế**, không phải một CSV parser sản xuất tổng quát.

## 5. Vì sao đọc từng dòng rồi `split` cũng sai?

Một **bản ghi CSV logic** có thể chiếm nhiều **dòng vật lý**:

~~~csv
id,comment,status
1,"Bắt đầu ở đây
và tiếp tục ở dòng tiếp theo",done
2,"Một dòng",pending
~~~

Ở đây chỉ có ba bản ghi (gồm header). Nếu gọi `BufferedReader.readLine()` rồi phân tích mỗi dòng như một bản ghi độc lập, giá trị `comment` của id `1` bị chặt đôi. `readLine()` bỏ ký tự xuống dòng, nên còn có nguy cơ làm mất ký tự gốc của trường nhiều dòng.

Để xử lý luồng lớn, parser phải đọc từ `Reader` và theo dõi trạng thái nháy **xuyên qua các lần đọc và các dòng vật lý**. Nếu dùng thư viện, ưu tiên API đọc từng bản ghi CSV logic. Cách “gom dòng cho đến khi đếm được số dấu nháy chẵn” cũng dễ sai nếu không xét quy tắc `""` và đầu vào lỗi.

## 6. Khi nào `split` đủ dùng và khi nào nên dùng thư viện?

`split` phù hợp nếu **đầu vào đã được bảo đảm** là văn bản phân tách đơn giản, không bao giờ chứa dấu phân cách trong giá trị, không dùng cú pháp nháy/escape CSV, không có bản ghi nhiều dòng, và cách xử lý trường rỗng đã được xác định. Đó là giả định về **định dạng đầu vào**, không thể suy ra chỉ vì tệp có đuôi `.csv`.

Với CSV do người dùng tải lên, CSV xuất từ Excel hoặc hệ thống khác, tệp có trường tự do như tên/địa chỉ/mô tả, hoặc dữ liệu cần độ tin cậy cao, hãy dùng thư viện chuyên dụng như **Apache Commons CSV** hoặc **uniVocity Parsers**. Cấu hình rõ delimiter, quote, escape, kiểu kết thúc bản ghi, header và chính sách báo lỗi theo nguồn dữ liệu; không mặc định mọi CSV đều giống nhau.

Khi đưa CSV vào ứng dụng thực tế, còn phải cân nhắc:

- **Encoding và BOM:** giải mã đúng charset (thường UTF-8); nếu có BOM ở đầu tệp, quyết định cách loại bỏ trước khi so khớp tên cột.
- **Header và số cột:** kiểm tra số cột dự kiến, tên header trùng/thiếu, bản ghi có số trường bất thường; parser đúng cú pháp chưa chắc bảo đảm dữ liệu đúng nghiệp vụ.
- **Rỗng và thiếu:** `,,`, `""` và trường vắng mặt do bản ghi thiếu cột có thể mang ý nghĩa khác nhau; phải quy định khi ánh xạ sang đối tượng Java.
- **Khoảng trắng:** `" abc "` giữ khoảng trắng bên trong nháy; tự động `trim()` có thể làm thay đổi dữ liệu. Một số dialect cho phép khoảng trắng sau nháy đóng, nhưng ví dụ Java ở trên không cho phép.
- **Dòng lỗi và kích thước:** chọn chính sách dừng/bỏ qua bản ghi lỗi, giới hạn độ dài trường và kích thước tệp để tránh dùng quá nhiều bộ nhớ.
- **Xuất CSV:** khi tạo CSV để mở bằng ứng dụng bảng tính, dữ liệu bắt đầu bằng `=`, `+`, `-`, `@` có thể bị hiểu là công thức. Đây là vấn đề an toàn ở **khâu xuất/nhập bảng tính**, ngoài việc parse CSV cho đúng.

## 7. Checklist tự kiểm tra

Một parser CSV cần được kiểm thử tối thiểu với các đầu vào:

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| `a,b,c` | Một bản ghi, 3 trường |
| `a,,c` | Trường giữa rỗng |
| `a,b,` | Giữ trường cuối rỗng |
| `"a,b",c` | Trường đầu là `a,b` |
| `"a""b",c` | Trường đầu là `a"b` |
| `"a\nb",c` (xuống dòng thật trong nháy) | Một bản ghi; trường đầu chứa xuống dòng |
| `a,b\r\nc,d` | Hai bản ghi với CRLF |
| `"abc` | Báo lỗi nháy chưa đóng |
| `"abc"x,y` | Báo lỗi ký tự sau nháy đóng |
| `a"b,c` | Báo lỗi nháy giữa trường không nháy |

**Kết luận:** `String.split(",")` nhìn thấy dấu phẩy; CSV parser phải hiểu **ngữ cảnh của dấu phẩy** và **trạng thái nháy**. `split(",", -1)` chỉ sửa việc mất các trường rỗng cuối dòng, không thay thế được phân tích CSV có nháy, escape và bản ghi nhiều dòng.
