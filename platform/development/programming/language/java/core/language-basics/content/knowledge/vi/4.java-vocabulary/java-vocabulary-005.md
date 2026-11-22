# Giới hạn của tên `_`, `const` và `goto` trong Java 17+

Ba trường hợp dễ gây nhầm khi đặt tên trong Java là dấu gạch dưới đơn lẻ `_` cùng hai từ `const` và `goto`. Chúng **không được dùng làm identifier** (tên biến, lớp, phương thức, v.v.) trên Java 17, nhưng lý do và lịch sử của chúng không hoàn toàn giống nhau:

- `_` (chỉ một dấu gạch dưới) trở thành từ khóa dành riêng từ **Java 9**. Dấu `_` vẫn được phép **nằm trong tên dài hơn** như `_count`, `value_` hoặc `__`.
- `const` và `goto` được Java **dành riêng**, nhưng Java **không cung cấp cú pháp khai báo hằng bằng `const` hoặc câu lệnh nhảy `goto`**.
- Thay cho `const` khi cần ngăn gán lại, Java sử dụng `final`; hằng số cấp lớp thường khai báo với `static final`. Thay cho ý tưởng nhảy vô điều kiện, Java cung cấp các cấu trúc điều khiển có quy tắc rõ ràng như `if`, `for`, `while`, `break`, `continue` và `return`.

Bài này tập trung vào **Java/JDK 17 trở lên**, chỉ ra tên nào hợp lệ, cách thay bằng cú pháp đúng và cách tự xác minh bằng `javac`.

## 1. Vì sao ba tên này không hợp lệ?

| Cách viết | Trên Java 17 | Giải thích |
| --- | --- | --- |
| `int _ = 1;` | **Lỗi biên dịch** | `_` đơn lẻ là từ khóa dành riêng |
| `int const = 2;` | **Lỗi biên dịch** | `const` là từ khóa dành riêng, dù Java không thực thi một câu lệnh `const` |
| `int goto = 3;` | **Lỗi biên dịch** | `goto` là từ khóa dành riêng, dù Java không có câu lệnh `goto` |
| `int _count = 1;` | **Hợp lệ** | Dấu gạch dưới chỉ là một phần của tên |
| `int count_ = 2;` | **Hợp lệ** | Tên không phải `_` đơn lẻ |
| `int __ = 3;` | **Hợp lệ** | Hai dấu gạch dưới tạo thành một identifier khác `_` |
| `int constValue = 4;` | **Hợp lệ** | Không trùng nguyên token `const` |
| `int gotoCount = 5;` | **Hợp lệ** | Không trùng nguyên token `goto` |
| `String text = "const goto _";` | **Hợp lệ** | Các ký tự nằm trong *string literal*, không phải identifier |

**Điểm cốt lõi:** trình biên dịch xem `const` là một token dành riêng, nhưng `constValue` là **một identifier riêng biệt**, không bị tách thành keyword `const` và phần đuôi `Value`. Tương tự với `gotoCount`.

Trong Java, tên có phân biệt chữ hoa/chữ thường. `GotoCount` không phải token `goto`, nhưng cách đặt tên vẫn nên tuân theo quy ước dễ đọc, ví dụ `gotoCount` cho biến và `GotoCounter` cho lớp.

### Quy tắc về identifier cần nhớ

Một tên Java thông thường có thể bắt đầu bằng chữ cái, dấu `_` hoặc `$` theo quy tắc ký tự Java, nhưng **không bắt đầu bằng chữ số**. Sau ký tự đầu tiên có thể có chữ số. Từ khóa dành riêng và literal như `true`, `false`, `null` cũng không dùng làm tên.

Dấu `$` hợp lệ về ngữ pháp nhưng thường dành cho mã sinh tự động hoặc tình huống đặc biệt; trong mã học tập, ưu tiên tên có nghĩa như `totalCount` hoặc `maxRetries`.

Phân biệt hai trường hợp:

~~~java
int item_2 = 10; // Hợp lệ.
int _item = 20;  // Hợp lệ.
// int 2item = 30; // Sai: bắt đầu bằng chữ số.
// int _ = 40;     // Sai trên Java 17: "_" đơn lẻ.
~~~

## 2. Thử nhìn thấy lỗi từ `javac`

Tạo tệp **`BadNames.java`** sau để **cố ý kiểm tra lỗi**:

~~~java
public class BadNames {
    public static void main(String[] args) {
        int _ = 1;
        int const = 2;
        int goto = 3;
        System.out.println("Khong chay den day");
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 BadNames.java
~~~

**Kết quả:** biên dịch **thất bại**. `javac` sẽ chỉ ra những token không thể dùng làm identifier; số lượng và lời văn chẩn đoán có thể thay đổi theo phiên bản compiler. **Không có đầu ra chương trình**, vì phương thức `main` chưa được thực thi.

Khi thử sửa lỗi, nên bỏ từng dòng sai hoặc đổi chúng thành:

~~~java
int _value = 1;
int constValue = 2;
int gotoCount = 3;
System.out.println(_value + constValue + gotoCount); // 6
~~~

Bốn câu lệnh trên là đoạn **đặt trong một phương thức**, không phải một tệp Java độc lập.

## 3. `const` không thay thế được `final` trong Java

Nếu muốn giá trị không được gán lại sau khi khởi tạo, dùng `final`:

~~~java
final int retryLimit = 3;
// retryLimit = 4; // Sai: không thể gán lại biến final.
~~~

Nếu cần một hằng số dùng chung trong lớp, một cách thông dụng là:

~~~java
static final int MAX_RETRIES = 3;
~~~

| Ý định | Cách làm Java | Lưu ý |
| --- | --- | --- |
| Không cho gán lại biến cục bộ | `final int limit = 3;` | `final` ngăn gán lại, không phải token `const` |
| Hằng số thuộc lớp | `static final int MAX_RETRIES = 3;` | Thường viết tên hằng bằng chữ hoa và `_` |
| Giá trị không đổi của chuỗi | `final String APP_NAME = "Demo";` | `String` vốn không thay đổi nội dung đối tượng |
| Không gán lại tham chiếu | `final StringBuilder b = new StringBuilder();` | **Vẫn có thể** gọi `b.append(...)` để sửa nội dung đối tượng |

Một field `static final` không nhất thiết là *compile-time constant*: điều đó còn phụ thuộc kiểu và **biểu thức khởi tạo**. Ví dụ `static final int X = 3;` là hằng số biểu thức đơn giản; `static final int X = Integer.parseInt("3");` là field chỉ được gán một lần nhưng giá trị tính lúc chạy.

**Đừng nhầm:** `final` không tự khiến mọi đối tượng trở nên bất biến (*immutable*). Nó hạn chế việc gán lại biến/tham chiếu theo quy tắc Java.

## 4. Không có `goto`: dùng điều khiển luồng có cấu trúc

Java không có câu lệnh `goto label;`. Một số cách điều khiển luồng gần với mục đích thực tế:

| Mục đích | Cấu trúc phù hợp |
| --- | --- |
| Chọn nhánh theo điều kiện | `if` / `else`, `switch` |
| Lặp nhiều lần | `for`, `while`, `do-while` |
| Thoát một vòng lặp | `break;` |
| Bỏ phần còn lại của một lượt lặp | `continue;` |
| Thoát nhiều mức lặp có chủ đích | `break label;` tại vòng/khối được gắn nhãn |
| Chuyển ngay sang lượt của vòng lặp ngoài | `continue label;` với **nhãn đặt trên một vòng lặp** |
| Kết thúc phương thức | `return;` hoặc `return value;` |

Nhãn là **identifier theo sau dấu hai chấm**. Bạn có thể viết `scan:` nhưng **không** viết `goto:` vì `goto` là từ khóa dành riêng.

Với `break outer;`, Java kết thúc statement mang nhãn `outer`. Với `continue outer;`, Java chuyển đến lượt tiếp theo của **vòng lặp** được gắn nhãn `outer`; không thể `continue` đến một nhãn đặt trên khối bất kỳ không phải vòng lặp.

Nhãn nên dùng có chừng mực: nhiều nhãn chồng chéo khiến luồng chạy khó theo dõi. Đối với tìm kiếm đơn giản, `return` từ một phương thức nhỏ thường còn rõ ràng hơn.

## 5. Ví dụ Java 17 chạy được: tên hợp lệ và nhãn thay cho `goto`

Tạo tệp **`ReservedNamesDemo.java`**:

~~~java
public class ReservedNamesDemo {
    private static final int MAX_RETRIES = 3;

    static int countProcessed(int[][] rows) {
        int processed = 0;

        scan:
        for (int row = 0; row < rows.length; row++) {
            for (int column = 0; column < rows[row].length; column++) {
                int value = rows[row][column];

                if (value == -1) {
                    continue scan; // Bo qua phan con lai cua hang.
                }

                if (value == 99) {
                    break scan; // Thoat ca hai vong lap.
                }

                processed++;
            }
        }
        return processed;
    }

    public static void main(String[] args) {
        int _count = 2;
        int __ = 3;
        int constValue = 5;
        int gotoCount = 7;

        int[][] rows = {
            {4, 5},
            {7, -1, 8},
            {9, 99, 10}
        };

        System.out.println("maxRetries=" + MAX_RETRIES);
        System.out.println(
                "legalNamesSum=" + (_count + __ + constValue + gotoCount));
        System.out.println("processed=" + countProcessed(rows));
    }
}
~~~

**Biên dịch/chạy trên Windows PowerShell hoặc Linux/Bash** — cùng một bộ lệnh:

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 ReservedNamesDemo.java
java ReservedNamesDemo
~~~

Kết quả dự kiến:

~~~text
maxRetries=3
legalNamesSum=17
processed=4
~~~

### Tại sao kết quả là 4?

Dữ liệu được duyệt lần lượt:

1. Hàng đầu tiên chứa `4`, `5`: cả hai được tính, `processed = 2`.
2. Hàng thứ hai: `7` được tính, `processed = 3`. Gặp `-1` thì `continue scan;` **bỏ qua số 8** và chuyển sang hàng thứ ba.
3. Hàng thứ ba: `9` được tính, `processed = 4`. Gặp `99` thì `break scan;` thoát cả hai vòng lặp, **không xét số 10**.

Lệnh `continue scan` và `break scan` có phạm vi điều khiển xác định, khác với một lệnh nhảy tùy ý kiểu `goto`.

Ở phần tên biến: `_count`, `__`, `constValue` và `gotoCount` đều hợp lệ; tổng `2 + 3 + 5 + 7 = 17`. Tên `__` tuy hợp lệ về cú pháp, nhưng khi viết chương trình thực tế bạn nên đặt tên biểu đạt ý nghĩa hơn.

`MAX_RETRIES` minh họa cách khai báo `static final`, **không phải** một câu lệnh `const`.

## 6. Các lỗi và ngộ nhận thường gặp

| Nhầm lẫn | Sự thật trên Java 17 | Cách xử lý |
| --- | --- | --- |
| “`_` là tên biến ngắn nên chắc hợp lệ” | `_` đứng một mình là keyword từ Java 9 | Đặt `_value` hoặc tên mô tả như `count` |
| “`const` không có tính năng nên được dùng đặt tên” | Vẫn là keyword dành riêng | Dùng tên như `constValue`; dùng `final` để ngăn gán lại |
| “`goto` không chạy nên có thể đặt làm nhãn” | Không; từ khóa dành riêng không làm identifier được | Đặt nhãn `scan:` hoặc `outer:` |
| “Mọi tên chứa `_` đều sai” | Chỉ `_` **đơn lẻ** bị cấm theo quy tắc này | `_count`, `item_2`, `__` hợp lệ |
| “`final` làm đối tượng bất biến hoàn toàn” | Không đúng với mọi đối tượng | Phân biệt gán lại tham chiếu và thay đổi trạng thái đối tượng |
| “`break outer` giống hệt `goto`” | `break` chỉ nhảy đến điểm kết thúc statement gắn nhãn hợp lệ | Dùng điều khiển luồng có cấu trúc |
| “`continue label` có thể nhảy tới mọi nhãn” | Nhãn đích phải đặt trên vòng lặp thích hợp | Chỉ dùng `continue` với nhãn vòng lặp |
| “Mã `const`/`goto` sẽ chạy rồi báo lỗi” | Lỗi bị bắt **khi biên dịch**, trước khi chạy `main` | Sửa identifier/cú pháp trước khi dùng `java` |

Một lưu ý nữa: dấu gạch dưới trong literal số, ví dụ `1_000`, chỉ giúp dễ đọc **chữ số**, không phải một biến tên `_`. Đây là hai ngữ cảnh cú pháp hoàn toàn khác nhau.

## 7. Bài tập tự luyện

**Bài 1 — Phân loại tên.** Các tên nào có thể khai báo thành biến `int` trên Java 17?

~~~text
_    __    _score    score_    const    constValue
goto    gotoCount    2score    score2
~~~

*Đáp án:* Hợp lệ: `__`, `_score`, `score_`, `constValue`, `gotoCount`, `score2`. Không hợp lệ: `_`, `const`, `goto` và `2score` (bắt đầu bằng chữ số).

**Bài 2 — Sửa lỗi.** Đoạn sau sai ở đâu?

~~~java
// Đoạn cố ý SAI, không đặt vào ví dụ đang chạy.
final int const = 3;
goto: for (int i = 0; i < 2; i++) {
    System.out.println(i);
}
~~~

*Gợi ý đáp án:* Cả `const` làm tên biến lẫn `goto` làm nhãn đều không hợp lệ. Đổi thành `final int maxTries = 3;` và nhãn `loop:` hoặc bỏ nhãn nếu không cần.

**Bài 3 — Dự đoán trước khi chạy.** Trong `ReservedNamesDemo`, nếu đổi `99` thành `11` thì `processed` bằng bao nhiêu?

*Đáp án:* `6`. Không còn giá trị chặn 99; vòng lặp vẫn bỏ qua `8` vì `-1`, sau đó đếm `9`, `11` và `10`.

**Bài 4 — Thử `continue`.** Bỏ nhãn trong `continue scan;` để thành `continue;`. Với dữ liệu gốc, kết quả `processed` có thay đổi không?

*Đáp án:* Có: thành `5`. `continue;` chỉ chuyển sang lượt tiếp theo của **vòng lặp trong**, nên sau `-1` còn xử lý `8`, trước khi gặp `99` ở hàng sau.

**Bài 5 — `final` và object.** Cho:

~~~java
final StringBuilder message = new StringBuilder("Java");
message.append(" 17"); // Hợp lệ.
// message = new StringBuilder("Other"); // Sai: gán lại biến final.
~~~

Tại sao câu `append` hợp lệ? *Đáp án:* `final` ngăn đổi tham chiếu được lưu trong biến, không nhất thiết ngăn thay đổi trạng thái đối tượng tham chiếu tới.

## Ghi nhớ

Trên **Java 17+**, `_` đơn lẻ, `const` và `goto` đều **không thể dùng làm tên**. `const` và `goto` là những từ dành riêng dù Java không triển khai câu lệnh mang các tên ấy; `_` đơn lẻ bị dành riêng từ Java 9, nhưng dấu `_` vẫn có thể là một phần trong identifier dài hơn. Hãy dùng `final`/`static final` cho mục đích hạn chế gán lại, và dùng `break`/`continue` có nhãn, `return` hoặc cấu trúc điều khiển phù hợp thay vì tìm cú pháp `goto`.
