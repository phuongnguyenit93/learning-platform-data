# Chuẩn hóa chuỗi đầu vào trước khi phân nhánh bằng `switch` với `String`

## 1. Vấn đề: cùng một lệnh nhưng nhiều cách viết

Giả sử ứng dụng nhận một lệnh từ bàn phím, tham số dòng lệnh hoặc HTTP request. Người dùng có thể gửi:

```text
"start"
"START"
" Start "
"  start  "
"run"
```

Nếu quy ước nghiệp vụ cho phép không phân biệt chữ hoa/thường, bỏ khoảng trắng ở hai đầu và chấp nhận `run` như bí danh của `start`, các giá trị trên cần đi vào **cùng một nhánh xử lý**. Tuy nhiên, phép `switch` trên `String` không tự thực hiện bất kỳ bước chuẩn hóa nào.

Từ Java 7, có thể dùng `String` làm biểu thức lựa chọn của `switch`. Cơ chế này **vẫn hợp lệ trong Java hiện đại**. Việc khớp một nhãn `case` dựa trên nội dung chuỗi với tính phân biệt chữ hoa/thường; về ý nghĩa so sánh là `String.equals`, không phải so sánh địa chỉ đối tượng bằng `==`.

```java
String command = " START ";

switch (command) {
    case "start":
        System.out.println("Bắt đầu");
        break;
    default:
        System.out.println("Không nhận diện");
}
```

Ở đây chương trình in `Không nhận diện` vì `" START "` khác `"start"`. **Chuẩn hóa chuỗi đầu vào trước khi phân nhánh** nghĩa là biến đầu vào thô thành một khóa so khớp theo *quy tắc đã được xác định*, sau đó mới đưa khóa đó vào `switch`.

Mục tiêu học tập của bài này là biết **nên chuẩn hóa gì**, **đặt bước chuẩn hóa ở đâu**, **xử lý `null` và Unicode thế nào** và **tránh biến đầu vào không hợp lệ thành một lệnh khác**. Chuẩn hóa không đồng nghĩa với tùy tiện loại bỏ mọi ký tự khác nhau.

## 2. Quy trình chuẩn hóa theo hợp đồng đầu vào

Với tập lệnh điều khiển không phân biệt chữ hoa/thường, một quy trình hợp lý trên Java hiện đại là:

```text
Giá trị đầu vào
     |
     v
Kiểm tra null / giới hạn kích thước
     |
     v
Loại khoảng trắng ở hai đầu (strip)
     |
     v
Chuyển chữ hoa/thường ổn định (Locale.ROOT)
     |
     v
Chuẩn hóa Unicode về NFC nếu cần
     |
     v
Kiểm tra chuỗi rỗng / định dạng hợp lệ
     |
     v
switch theo khóa đã chuẩn hóa
     |
     +--> nhánh hợp lệ / bí danh đã công bố
     |
     +--> default: giá trị không được hỗ trợ
```

Không phải hệ thống nào cũng cần đủ mọi bước. Hãy xác định **quy tắc đầu vào trước**, ví dụ: "chấp nhận `START`, `Start` hoặc ` start ` như `start`; không cho phép khoảng trắng ở giữa từ; không tự xóa dấu tiếng Việt". Sau đó triển khai đúng quy tắc đó.

Với các lệnh ASCII đơn giản như `start`, `stop`, ba thao tác quan trọng thường là kiểm tra `null`, `strip()` và `toLowerCase(Locale.ROOT)`. Nếu tập khóa có chữ Unicode có dấu, chuẩn hóa dạng Unicode `NFC` giúp tránh một số trường hợp chuỗi nhìn giống nhau nhưng được lưu bằng các dãy mã khác nhau.

**Luôn phân biệt** dữ liệu gốc (`raw input`) với khóa so khớp (`normalized key`). Có thể giữ dữ liệu gốc để hiển thị hoặc chẩn đoán lỗi; chỉ dùng khóa đã chuẩn hóa để phân nhánh theo hợp đồng.

## 3. Xử lý `null` trước khi đưa `String` vào `switch`

Với cú pháp `switch` cổ điển nhận `String`, nếu biểu thức lựa chọn là `null`, Java ném `NullPointerException`. Những biểu thức gọi phương thức như `raw.strip()` cũng sẽ ném lỗi nếu `raw == null`.

```java
// raw có thể nhận null
if (raw == null) {
    return "MISSING";
}
String key = raw.strip().toLowerCase(java.util.Locale.ROOT);

switch (key) {
    case "start":
        return "START";
    default:
        return "UNKNOWN";
}
```

Đoạn trên chỉ minh họa **phần thân của một phương thức trả về `String`**, không phải chương trình chạy độc lập. Nó áp dụng một chính sách rõ ràng: `null` là đầu vào bị thiếu. Nếu nghiệp vụ yêu cầu báo lỗi thay vì trả trạng thái, có thể ném `IllegalArgumentException` hoặc trả đối tượng lỗi theo hợp đồng API.

Tránh dùng `String.valueOf(raw)` như một "cách sửa `null`" vô điều kiện: với `raw == null`, phương thức tạo ra chuỗi văn bản `"null"`, có thể vô tình được coi là một lệnh thật. Tương tự, không tự động biến `null` thành chuỗi rỗng nếu hệ thống cần phân biệt **thiếu trường** với **có trường nhưng trống**.

## 4. `strip()`, `trim()` và khoảng trắng: chọn theo yêu cầu

Hai phương thức phổ biến để xử lý khoảng trắng hai đầu là:

- `String.strip()` (Java 11+): loại các ký tự đầu/cuối mà `Character.isWhitespace` công nhận. Phù hợp cho nhiều đầu vào văn bản Unicode trong Java hiện đại.
- `String.trim()`: loại các ký tự đầu/cuối có mã không lớn hơn U+0020, như khoảng trắng ASCII và nhiều ký tự điều khiển. `trim()` vẫn được hỗ trợ, nhưng **không đồng nghĩa** với xử lý mọi khoảng trắng Unicode.

Ví dụ:

```java
String raw = "  START  ";
String stripped = raw.strip(); // "START"
String trimmed = raw.trim();   // "START"
```

Hai phương thức đều trả **chuỗi mới**; `String` là bất biến, nên `raw` không bị sửa. Vì vậy phải gán kết quả:

```java
String raw = "  START  ";
raw.strip();                     // Không sửa biến raw
String key = raw.strip();        // key mới là "START"
```

**Giới hạn quan trọng:** `strip()` không có nghĩa là "xóa mọi ký tự hiển thị như khoảng trắng". Một số dấu cách không ngắt dòng (`non-breaking space`, ví dụ U+00A0), dấu cách đặc biệt và ký tự vô hình không nhất thiết được `Character.isWhitespace` công nhận. Nếu đầu vào giao thức yêu cầu chỉ có ký tự ASCII, cách đúng có thể là **từ chối ký tự khác** thay vì tìm cách xóa hết.

Đặc biệt, `strip()` không loại khoảng trắng **ở giữa** lệnh:

```java
"st art".strip() // vẫn là "st art"
```

Không nên mặc định áp dụng `replace(" ", "")`, vì hai lệnh khác nhau có thể bị nhập làm một. Tương tự, chỉ gộp nhiều khoảng trắng bên trong thành một dấu cách nếu **ngữ pháp đầu vào cho phép** các cách viết đó tương đương.

Trên Java 7, `strip()` chưa tồn tại; `trim()` vẫn có thể dùng trong mã cần biên dịch bằng JDK cũ. Trong Java 17+ hiện nay, ưu tiên quyết định dựa trên **đặc tính dữ liệu đầu vào**, không chọn `trim()` chỉ vì ví dụ lịch sử.

## 5. Chuyển chữ hoa/thường ổn định bằng `Locale.ROOT`

`switch` phân biệt `"start"` và `"START"`. Nếu tập lệnh được định nghĩa **không phân biệt hoa/thường**, có thể chuẩn hóa về chữ thường:

```java
import java.util.Locale;

// Bên trong phương thức:
String key = raw.strip().toLowerCase(Locale.ROOT);
```

`Locale.ROOT` là locale trung tính, thích hợp cho các **khóa điều khiển, định danh giao thức và lệnh máy** cần hành vi nhất quán giữa các máy chủ. Viết `toLowerCase()` không tham số sẽ dùng locale mặc định của môi trường; quy tắc chuyển chữ có thể khác nhau theo ngôn ngữ. Ví dụ tiếng Thổ Nhĩ Kỳ có quy tắc riêng với chữ `I` và `i`, khiến phép so khớp lệnh thay đổi giữa máy.

Ngược lại, nếu bạn xử lý **từ ngữ tự nhiên của một ngôn ngữ cụ thể**, có thể cần locale tương ứng với ngôn ngữ đó. `Locale.ROOT` không phải phép "chuyển toàn bộ Unicode thành cùng một dạng không phân biệt hoa/thường" trong mọi ngữ cảnh; việc chuyển chữ và phép *Unicode case folding* đầy đủ là các khái niệm khác nhau.

Ngoài ra, **không phải mọi chuỗi cần bỏ phân biệt hoa/thường**. Mã truy cập, mật khẩu, token, ID phân biệt hoa/thường, chữ ký và một số tên tài nguyên phải được giữ nguyên hoặc xác minh theo quy tắc riêng. Chuẩn hóa lệnh điều khiển không có nghĩa là được phép chuẩn hóa những giá trị đó.

Để các nhánh dễ hiểu, hãy đặt nhãn `case` theo **cùng dạng chuẩn**:

```java
String key = raw.strip().toLowerCase(Locale.ROOT);

switch (key) {
    case "start":           // Đúng: nhãn ở chữ thường
        return "START";
    case "stop":
        return "STOP";
    default:
        return "UNKNOWN";
}
```

`case "START":` sau khi đã chuyển `key` thành chữ thường thường sẽ không khớp. Nhãn `case` phải là một biểu thức hằng `String` hợp lệ ở thời điểm biên dịch; không thể dùng tùy ý `case someVariable:` hay `case "START".toLowerCase(Locale.ROOT):`.

## 6. Unicode: chuỗi hiển thị giống nhau chưa chắc chứa cùng ký tự

Trong Unicode, một chữ có dấu có thể được biểu diễn theo nhiều chuỗi mã. Ví dụ ký tự `é` có thể là:

- Một mã duy nhất: `U+00E9`.
- Chữ `e` (`U+0065`) theo sau bởi dấu sắc kết hợp `U+0301`.

Hai dạng có thể nhìn gần như giống hệt, nhưng `String.equals` có thể trả `false`. Nếu tập lệnh thực sự chứa ký tự có dấu, có thể chuẩn hóa về dạng chuẩn tắc `NFC` trước khi phân nhánh:

```java
import java.text.Normalizer;
import java.util.Locale;

// Bên trong phương thức, sau khi đã kiểm tra raw != null:
String key = Normalizer.normalize(
        raw.strip().toLowerCase(Locale.ROOT),
        Normalizer.Form.NFC
);
```

**NFC** gộp những biểu diễn Unicode tương đương về một dạng chuẩn tắc, khi có thể. Cách này giúp nhãn `case "café":` khớp với chuỗi đầu vào được viết bằng `"cafe\u0301"` sau chuẩn hóa. Ví dụ này không yêu cầu xóa dấu.

Không nên áp dụng bừa `NFKC` (chuẩn hóa tương thích) hay xóa hết dấu. `NFKC` còn có thể biến các ký tự tương thích như một số dạng chữ fullwidth hoặc ký hiệu trình bày thành dạng khác; việc đó có thể hữu ích trong một số sản phẩm nhưng cũng có thể làm mất phân biệt có ý nghĩa. Việc xóa dấu biến `"má"` và `"ma"` thành cùng khóa, điều mà nghiệp vụ tiếng Việt có thể không mong muốn.

NFC **không bảo đảm** những chuỗi trông giống nhau ở mắt người sẽ được coi là cùng một khóa; ví dụ ký tự hình dạng giống nhau giữa các hệ chữ khác nhau vẫn có thể khác. Nếu chỉ chấp nhận tập lệnh ASCII cố định, hãy cân nhắc **giới hạn cú pháp đầu vào** và so khớp danh sách lệnh được phép, thay vì cố xử lý mọi trường hợp Unicode.

## 7. Ví dụ hoàn chỉnh: chuẩn hóa một lần, phân nhánh một lần

Chương trình Java 17+ sau minh họa một chính sách cụ thể:

1. `null` được trả về trạng thái `MISSING`, không gây lỗi trong `switch`.
2. Bỏ khoảng trắng được nhận diện ở hai đầu bằng `strip()`.
3. Chuyển chữ về chữ thường với `Locale.ROOT` để máy khác nhau vẫn nhất quán.
4. Chuẩn hóa Unicode về `NFC` để lệnh `café` nhận cả hai dạng mã hóa tương đương.
5. Chuỗi rỗng sau chuẩn hóa được trả về `EMPTY`.
6. Lệnh `start` hoặc `run` vào nhánh bắt đầu; `stop` hoặc `quit` vào nhánh dừng.
7. Các chuỗi khác, kể cả khoảng trắng nằm giữa `"st art"`, vào `default`.

Tạo tệp **`InputNormalizationDemo.java`**:

```java
import java.text.Normalizer;
import java.util.Locale;

public class InputNormalizationDemo {

    public static String route(String raw) {
        if (raw == null) {
            return "MISSING";
        }

        String key = Normalizer.normalize(
                raw.strip().toLowerCase(Locale.ROOT),
                Normalizer.Form.NFC
        );

        if (key.isEmpty()) {
            return "EMPTY";
        }

        switch (key) {
            case "start":
            case "run":
                return "START";

            case "stop":
            case "quit":
                return "STOP";

            case "café":
                return "CAFE";

            default:
                return "UNKNOWN";
        }
    }

    public static void main(String[] args) {
        System.out.println(route("  START  "));
        System.out.println(route("Run"));
        System.out.println(route(" STOP "));
        System.out.println(route(" CAFE\u0301 "));
        System.out.println(route("st art"));
        System.out.println(route(""));
        System.out.println(route(" \t "));
        System.out.println(route(null));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 InputNormalizationDemo.java
java InputNormalizationDemo
```

Kết quả chính xác:

```text
START
START
STOP
CAFE
UNKNOWN
EMPTY
EMPTY
MISSING
```

Ở ví dụ thứ tư, `"CAFE\u0301"` chứa chữ `E` và dấu sắc kết hợp. Sau `toLowerCase(Locale.ROOT)` và `Normalizer.Form.NFC`, nó khớp với nhãn `"café"`. Chương trình sử dụng `switch` cổ điển với các nhánh `case` và `return`, nên **không cần `break`**: mỗi nhánh trả kết quả ngay và kết thúc phương thức, không rơi xuống nhánh kế tiếp.

Đây là cách dùng `switch` với `String` đã có từ Java 7, kết hợp những API chuẩn hóa vẫn phù hợp ở Java hiện đại. `strip()` là API xuất hiện từ Java 11; do đó **chương trình đầy đủ ở đây chạy trên Java 17+, không biên dịch nguyên trạng bằng JDK 7**.

## 8. Chuẩn hóa, xác thực và phân nhánh là ba trách nhiệm khác nhau

Chuẩn hóa chỉ giải quyết **những khác biệt được phép coi là tương đương**. Nó không thay thế việc xác thực đầu vào hoặc kiểm tra quyền:

- **Chuẩn hóa:** `" START "` thành `"start"` nếu cho phép bỏ khoảng trắng và không phân biệt hoa/thường.
- **Xác thực:** chỉ cho phép các khóa thuộc tập `start`, `run`, `stop`, `quit`, `café`; có thể kiểm tra chiều dài, ký tự hợp lệ và định dạng trước khi xử lý.
- **Phân nhánh:** `switch` chọn hành vi theo khóa đã được kiểm tra.
- **Phân quyền nếu có:** hệ thống phải kiểm tra riêng người dùng có được thực hiện hành vi đó hay không; việc chọn đúng `case` không cấp quyền thực hiện.

Đặc biệt, **không tự động thay các ký tự lạ bằng chuỗi rỗng** để "cứu" một giá trị đầu vào. Điều đó có thể biến hai lệnh khác nhau thành cùng một khóa. Nếu đầu vào có dấu cách ở giữa không được hợp đồng chấp nhận, trả kết quả `UNKNOWN` hoặc lỗi xác thực là chính xác hơn.

Đối với dữ liệu không đáng tin cậy có thể rất dài, nên giới hạn kích thước trước các phép xử lý đắt hơn như chuyển chữ, chuẩn hóa Unicode hoặc biểu thức chính quy. Giới hạn cần dựa trên đặc điểm giao thức và sản phẩm; không tự giả định mọi lệnh đều được dài vô hạn. Hãy ghi nhận lỗi ở mức thích hợp, tránh lộ dữ liệu nhạy cảm trong log.

Với lệnh được cấu hình bằng các bí danh, có thể tạo **một tập ánh xạ bí danh về lệnh chuẩn** trước khi `switch`. Khi số lượng lệnh ít và cố định, dùng nhiều `case` liên tiếp như ví dụ là dễ hiểu. Khi quy tắc động hoặc nhiều alias, một `Map<String, Command>` hoặc `enum` trung gian có thể dễ bảo trì hơn; vẫn áp dụng cùng chính sách chuẩn hóa cho các khóa tra cứu.

## 9. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `"START"` không vào `case "start"` | `switch` phân biệt chữ hoa/thường | Nếu hợp đồng cho phép, dùng `toLowerCase(Locale.ROOT)` |
| `" start "` rơi vào `default` | Khoảng trắng hai đầu khác ký tự nhãn | Dùng `strip()` trước `switch` |
| Gọi `raw.strip()` khi `raw == null` | Tham chiếu `null` | Xử lý `null` trước mọi thao tác |
| Chuỗi chỉ gồm dấu cách rơi vào nhánh lạ | Không kiểm tra giá trị sau `strip()` | Dùng `key.isEmpty()` hoặc kiểm tra rõ tình huống `EMPTY` |
| `"café"` không khớp chuỗi nhìn giống hệt | Unicode có dạng ghép/tách ký tự | Dùng `Normalizer.Form.NFC` nếu hợp đồng yêu cầu |
| Đầu vào khác nhau giữa hai máy | Dùng `toLowerCase()` phụ thuộc locale mặc định | Chọn `Locale.ROOT` cho khóa kỹ thuật |
| Gọi `strip()` mà `switch` vẫn dùng `raw` | `String` bất biến; kết quả không được lưu lại | Gán vào biến `key` và `switch (key)` |
| Thêm nhiều nhãn `case` sau chuẩn hóa nhưng trùng nghĩa | Nhiều nhánh khó kiểm soát, nhãn trùng là lỗi biên dịch | Chuẩn hóa một lần, tổ chức alias về cùng hành vi |
| Loại bỏ toàn bộ dấu/khoảng trắng mà không có yêu cầu | Hai giá trị khác nghĩa bị coi là một | Chỉ thực hiện biến đổi đã được hợp đồng công nhận |
| Sử dụng `==` để kiểm tra chuỗi bên ngoài `switch` | `==` so sánh tham chiếu | Dùng `equals` hoặc chuyển thành khóa rồi `switch` |
| Tin rằng `strip()` loại được mọi ký tự vô hình | Một số ký tự không thuộc `Character.isWhitespace` | Xác thực ký tự được chấp nhận theo đầu vào |
| Chuẩn hóa mật khẩu, token hay ID phân biệt hoa/thường | Thay đổi dữ liệu có ý nghĩa xác thực | Tách quy tắc riêng; giữ nguyên hoặc so khớp chính xác |

**Độ ưu tiên:** không bắt đầu bằng việc "làm sạch mạnh nhất", mà bằng việc liệt kê đầu vào hợp lệ, các biến thể được phép và phản hồi dành cho đầu vào không hợp lệ. Đây là cách bảo đảm bước chuẩn hóa hỗ trợ `switch` mà không tự đổi nghĩa dữ liệu.

## 10. Bài tập và đáp án

**Bài 1.** Ứng dụng nhận `" YES "` và `"yes"` tương đương nhau. Hãy viết biểu thức tạo khóa ổn định trước `switch` trên Java 17+, giả sử `raw` đã được kiểm tra khác `null`.

**Bài 2.** Với chương trình `InputNormalizationDemo` ở trên, hãy dự đoán kết quả của `route(" St Art ")`, `route("start now")` và `route(null)`.

**Bài 3.** Đặt hai khóa `"café"` (dạng ký tự ghép sẵn) và `"cafe\u0301"` (chữ `e` + dấu sắc kết hợp) vào `String.equals` trước khi chuẩn hóa. Chúng có bắt buộc bằng nhau không? Cách làm nào giúp chúng khớp nếu hợp đồng coi chúng tương đương?

**Bài 4.** Vì sao không nên chuyển `"apiKeyAbC"` sang chữ thường chỉ để so sánh với `"apikeyabc"`? Vì sao `"s t a r t"` không nên tự động trở thành `"start"`?

**Đáp án:**

1. `String key = raw.strip().toLowerCase(Locale.ROOT);`, với `import java.util.Locale;`. Nếu định dạng có Unicode cần xử lý tương đương chuẩn tắc, bổ sung `Normalizer.normalize(key, Normalizer.Form.NFC)`.
2. `" St Art "` → `START`. `"start now"` → `UNKNOWN` vì khoảng trắng ở giữa không bị loại. `null` → `MISSING` trước khi gọi bất kỳ phương thức trên chuỗi nào.
3. Không bắt buộc: hai chuỗi có thể khác nhau về dãy đơn vị mã. Chuẩn hóa cả hai về `Normalizer.Form.NFC` trước khi so sánh hoặc phân nhánh nếu điều đó đúng với hợp đồng.
4. Mã khóa API có thể phân biệt chữ hoa/thường; đổi chữ có thể khiến xác thực sai. Khoảng trắng ở giữa từ có thể là lỗi nhập hoặc là dữ liệu khác nghĩa; tự xóa nó sẽ tạo quy tắc tương đương mà hệ thống chưa cho phép.

**Ghi nhớ:** Quy trình đáng tin cậy là **xác định hợp đồng đầu vào → xử lý `null` → chuẩn hóa đúng mức được phép → xác thực → `switch` theo khóa chuẩn → xử lý `default` rõ ràng**. Java 7 đã hỗ trợ `switch` với `String`; Java hiện đại vẫn sử dụng cơ chế đó và cung cấp thêm các API như `strip()` để viết bước chuẩn hóa rõ ràng hơn.