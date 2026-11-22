# Nhóm chữ số theo đơn vị có ý nghĩa trong Java

## 1. Vì sao nên nhóm chữ số?

Khi một số chứa nhiều chữ số, việc viết liền dễ dẫn đến đọc nhầm, bỏ sót hoặc thêm một chữ số. Kể từ **Java 7**, Java cho phép đặt dấu gạch dưới (`_`) **giữa các chữ số của numeric literal** (giá trị số viết trực tiếp trong mã nguồn). Đây vẫn là cú pháp Java thông dụng và được hỗ trợ trên các JDK hiện đại.

Ví dụ:

~~~java
int oneMillion = 1_000_000;
long nanosPerSecond = 1_000_000_000L;
~~~

`1_000_000` và `1000000` biểu diễn **cùng một giá trị**. Trình biên dịch dùng dấu `_` để đọc mã nguồn; dấu này **không phải** chữ số, toán tử, ký tự được lưu trong số hay ký hiệu định dạng kết quả. Khi in `oneMillion` thông thường, kết quả là `1000000`.

Chủ đề “nhóm chữ số theo đơn vị có ý nghĩa” gồm hai lựa chọn kết hợp với nhau:

1. **Nhóm ở vị trí giúp người đọc nhận ra cấu trúc**: hàng nghìn trong hệ thập phân, từng nibble (4 bit) trong hệ nhị phân, từng byte (2 chữ số hex) trong hệ thập lục phân.
2. **Đặt tên biến/hằng cho biết đơn vị thực**: `timeoutMillis`, `bytesPerMebibyte`, `nanosPerSecond`. Dấu `_` giúp nhìn rõ chữ số, nhưng không tự biến một số thành mili giây, byte, tiền hoặc màu sắc.

## 2. Chọn cách nhóm phù hợp với ý nghĩa của số

| Tình huống | Cách viết | Vì sao dễ hiểu |
| --- | --- | --- |
| Số lượng theo hàng nghìn | `12_345_678` | Nhóm ba chữ số từ phải sang trái theo cách đọc số thập phân |
| Khoảng thời gian tính bằng mili giây | `30_000L` | Dễ thấy số 30.000 ms = 30 giây; đơn vị thể hiện ở tên biến |
| Số byte tương ứng 1 MiB | `1_048_576` | Giá trị 2²⁰ byte, tách hàng nghìn để tránh đọc sai |
| Số nanô giây trong một giây | `1_000_000_000L` | Chín chữ số 0 dễ kiểm tra hơn khi nhóm ba |
| Mặt nạ bit | `0b1010_0101` | Mỗi nhóm bốn bit tương ứng một nibble |
| Ba kênh màu RGB | `0x12_34_56` | Mỗi cặp hex tương ứng một byte: R=`0x12`, G=`0x34`, B=`0x56` |
| Dãy thập phân | `3.141_592_653` | Nhóm phần lẻ cho dễ đối chiếu; vẫn là literal kiểu `double` mặc định |

Các ví dụ được nhóm theo **mục đích đọc hiểu**, không có quy tắc phải đặt dấu `_` sau đúng ba chữ số trong mọi cơ số. Quy ước nhóm ba chữ số phù hợp số thập phân; nhóm bốn bit phù hợp nhị phân; nhóm hai chữ số hex phù hợp ranh giới byte. Trong một dự án, hãy dùng cách nhóm ổn định để các con số cùng ý nghĩa có thể so sánh nhanh.

**Lưu ý về đơn vị dữ liệu:** 1 MiB = 1.048.576 byte; 1 MB (theo hệ thập phân) = 1.000.000 byte. Dấu `_` không quyết định đây là MB hay MiB; tên hằng và tài liệu phải ghi đúng đơn vị.

## 3. Quy tắc cú pháp cần nhớ

Theo Java Language Specification, dấu gạch dưới có thể xuất hiện trong phần chữ số của literal số nguyên hoặc số thực, với điều kiện đặt **giữa các chữ số hợp lệ** ở vị trí đó.

Các dạng hợp lệ:

~~~java
int total = 1_000_000;                // Thập phân
long timeoutMillis = 30_000L;        // Hậu tố L đứng sau chữ số
int statusBits = 0b1010_0101;        // Nhị phân, 4 bit/nhóm
int rgb = 0x12_34_56;                // Thập lục phân, 2 hex digit/byte
double fraction = 0.123_456;         // Sau dấu thập phân
double measurement = 12_345.678_9;   // Có thể nhóm hai phía dấu chấm
int sameValue = 1__000;              // Hợp lệ, nhưng ít rõ ràng hơn 1_000
~~~

Bảng đối chiếu lỗi cú pháp:

| Cách viết | Vấn đề | Viết lại |
| --- | --- | --- |
| `1_000_` | Dấu `_` sau chữ số cuối cùng | `1_000` |
| `1_.25` | Dấu `_` ngay trước dấu chấm thập phân | `1.25` |
| `1._25` | Dấu `_` ngay sau dấu chấm thập phân | `1.25` |
| `0x_FF` | Dấu `_` ngay sau tiền tố `0x` | `0xFF` |
| `0b_1010` | Dấu `_` ngay sau tiền tố `0b` | `0b1010` |
| `123_L` | Dấu `_` trước hậu tố kiểu `L` | `123L` |
| `3.14_F` | Dấu `_` trước hậu tố kiểu `F` | `3.14F` |
| `1e_3` | Dấu `_` ngay sau ký hiệu số mũ `e` | `1e3` |
| `_1000` | Đây có thể được đọc như **tên định danh**, không phải literal số | `1_000` |

**Diễn giải quan trọng:**

- Trong dạng `0x...`, các chữ `A` đến `F` là **chữ số hex**; vì thế `0xAB_CD` hợp lệ. `0x_ABCD` thì không: dấu `_` không được đứng sát tiền tố `0x`.
- Dấu `_` có thể xuất hiện **nhiều lần liên tiếp** giữa hai chữ số, nhưng `1__000` gây nhiễu khi đọc và thường không đáng dùng.
- Phần nguyên và phần thập phân có thể nhóm độc lập; **không** đặt `_` giáp dấu chấm `.` hoặc ký hiệu số mũ.
- Không viết `1,000,000` với ý định biểu diễn một literal Java duy nhất: dấu phẩy không phải ký tự phân nhóm numeric literal trong mã nguồn.
- Đừng thêm số `0` ở đầu một số nguyên thập phân để “căn hàng”: cách viết số nguyên bắt đầu bằng `0` có thể mang ý nghĩa hệ cơ số khác. Viết thẳng `10_000` hoặc ghi rõ `0b`/`0x` khi cần nhị phân/hex.

Các biểu thức **không hợp lệ** trong bảng là ví dụ để nhận diện lỗi, không phải đoạn mã để biên dịch như một chương trình độc lập.

## 4. Ví dụ Java hoàn chỉnh, chạy trên JDK hiện đại

Dùng JDK 21 hoặc mới hơn có khả năng biên dịch mức `--release 21`. Tạo một file:

~~~text
grouped-numbers/
└── src/
    └── main/
        └── java/
            └── demo/
                └── GroupedNumberExample.java
~~~

Nội dung `src/main/java/demo/GroupedNumberExample.java`:

~~~java
package demo;

public final class GroupedNumberExample {
    private GroupedNumberExample() {
    }

    public static void main(String[] args) {
        long nanosPerSecond = 1_000_000_000L;
        int bytesPerMebibyte = 1_048_576;
        int rgb = 0x12_34_56;
        int statusBits = 0b1010_0101;

        System.out.println("nanosPerSecond=" + nanosPerSecond);
        System.out.println("bytesPerMebibyte=" + bytesPerMebibyte);
        System.out.println("rgb=" + ((rgb >>> 16) & 0xFF)
                + "," + ((rgb >>> 8) & 0xFF)
                + "," + (rgb & 0xFF));
        System.out.println("statusBits=" + statusBits);
        System.out.println("equal=" + (1_000_000 == 1000000));
    }
}
~~~

Đứng trong thư mục `grouped-numbers/` và chạy:

~~~sh
javac --release 21 -encoding UTF-8 -d out src/main/java/demo/GroupedNumberExample.java
java -cp out demo.GroupedNumberExample
~~~

Stdout chính xác:

~~~text
nanosPerSecond=1000000000
bytesPerMebibyte=1048576
rgb=18,52,86
statusBits=165
equal=true
~~~

**Vì sao cho ra những giá trị đó?**

1. `1_000_000_000L` có giá trị 1.000.000.000 nanô giây; `L` xác định literal `long`, còn dấu `_` chỉ tăng khả năng đọc.
2. `1_048_576` là số byte trong 1 MiB. Giá trị vừa trong `int`; cách viết nhóm không làm thay đổi kiểu.
3. `0x12_34_56` chia giá trị thành ba byte trong hệ hex. Toán tử dịch phải không dấu `>>>` và mặt nạ `0xFF` tách R, G, B; `0x12` = 18, `0x34` = 52, `0x56` = 86.
4. `0b1010_0101` chứa tám bit; chuyển sang thập phân bằng `128 + 32 + 4 + 1` = 165. Dấu gạch dưới ngăn hai nibble để dễ quan sát.
5. `1_000_000 == 1000000` là `true` vì hai literal có cùng giá trị. Khi nối số vào chuỗi để in, dấu phân cách không xuất hiện trong kết quả.

Ví dụ tập trung vào cú pháp literal; toán tử dịch bit chỉ được dùng để kiểm chứng ý nghĩa phân nhóm của mã màu, không đòi cấu hình Java 7 hoặc công cụ cũ.

## 5. Ba điều mà dấu gạch dưới **không** làm

### 5.1. Không đổi kiểu dữ liệu hay ngăn tràn số

~~~java
long count = 3_000_000_000L;         // Hợp lệ: literal long
long product = 100_000L * 100_000;   // Hợp lệ: phép nhân thực hiện trên long
~~~

`3_000_000_000` không tự trở thành `long` chỉ vì có dấu `_`. Nếu thiếu `L`, một literal nguyên thập phân vượt miền giá trị `int` có thể gây lỗi biên dịch. Tương tự, `100_000 * 100_000` được nhân dưới kiểu `int` và có thể tràn trước khi gán vào biến `long`. Phải chọn đúng kiểu và kiểu của toán hạng; cách nhóm chữ số không có tác dụng bảo vệ tràn số.

### 5.2. Không phải cú pháp đầu vào văn bản

Dấu `_` bên trong **source code** khác với dấu `_` bên trong một `String`. Ví dụ:

~~~java
int amount = 1_000;                      // Hợp lệ: numeric literal
// Integer.parseInt("1_000");           // Nếu gọi sẽ ném NumberFormatException
int parsed = Integer.parseInt("1000");    // Hợp lệ: văn bản chữ số thập phân
~~~

Đây là đoạn minh họa để so sánh cú pháp, không phải chương trình có `main` độc lập. Khi nhận dữ liệu từ JSON, biểu mẫu, tệp cấu hình hoặc API, phải tuân theo **cú pháp định dạng đầu vào tương ứng**; không mặc nhiên cho rằng mọi bộ đọc số đều chấp nhận dấu `_` như trình biên dịch Java.

Tương tự, nếu muốn **hiển thị** dấu phân cách cho người dùng, hãy dùng bộ định dạng phù hợp với `Locale`/yêu cầu giao diện. Dấu gạch dưới trong mã nguồn không phải quy tắc trình bày số khi in.

### 5.3. Không tự gắn ngữ nghĩa nghiệp vụ

`30_000` không mặc nhiên là 30 giây; nó chỉ là số ba mươi nghìn. Tên `timeoutMillis` mới cho biết đơn vị. `2026_11_04` cũng chỉ là literal số thập phân có giá trị `20261104`, **không phải một kiểu ngày tháng**; khi lưu ngày, hãy dùng kiểu ngày như `LocalDate` hoặc định dạng ngày được định nghĩa rõ ràng.

Nếu nhóm chữ số chỉ mang tính trang trí hoặc tạo ấn tượng sai về đơn vị, nên bỏ nhóm hoặc đổi tên hằng cho rõ nghĩa.

## 6. Quy ước khi dùng trong dự án thật

1. **Decimal:** mặc định nhóm ba chữ số từ phải sang trái cho số dài, trừ khi domain có cách nhóm dễ đọc hơn và cả dự án thống nhất cách viết.
2. **Binary:** ưu tiên nhóm bốn hoặc tám bit nếu đang biểu diễn cờ hoặc bit field; nếu ánh xạ cấu trúc giao thức, nhóm theo ranh giới trường và giải thích trường.
3. **Hex:** ưu tiên nhóm hai chữ số để thể hiện byte; với dữ liệu biểu diễn RGB, địa chỉ, mask hoặc định dạng khác, xác định rõ ý nghĩa từng nhóm.
4. **Đơn vị:** đưa vào tên biến, tên hằng hoặc kiểu dữ liệu, chẳng hạn `timeoutMillis` và `bufferSizeBytes`; đừng để người đọc phải suy luận từ số chữ số 0.
5. **Giới hạn kiểu số:** dùng `L` khi cần `long`; chú ý miền giá trị và tràn khi tính toán. Với số thực, dấu `_` chỉ hỗ trợ đọc mã; không cải thiện độ chính xác của `float`/`double`. Nếu xử lý tiền cần độ chính xác thập phân, chọn cách biểu diễn phù hợp như `BigDecimal` hoặc đơn vị nhỏ nhất ở kiểu nguyên.
6. **Dễ đọc hơn là “đúng cú pháp”:** dù `1__000` biên dịch được, thông thường `1_000` nhất quán và rõ hơn.

## 7. Tự kiểm tra

**Bài 1.** Viết lại các literal để dễ nhìn thấy nhóm có ý nghĩa:

~~~text
5000000           (decimal)
1048576           (byte, tương ứng 1 MiB)
0b11001100        (bit mask)
0x112233          (RGB)
~~~

**Đáp án gợi ý:** `5_000_000`, `1_048_576`, `0b1100_1100`, `0x11_22_33`.

**Bài 2.** Dự đoán kết quả của `1_000 == 1000` và giải thích. **Đáp án:** `true`; dấu `_` không đổi giá trị literal.

**Bài 3.** Vì sao `0x_FF` và `1_000_` không biên dịch như literal số? **Đáp án:** một dấu `_` đứng ngay sau tiền tố cơ số, dấu còn lại đứng sau chữ số cuối; cả hai đều không nằm giữa các chữ số.

**Bài 4.** Có nên dùng `1_000_000` thay cho `1000000` trong `Integer.parseInt(...)` không? **Đáp án:** chỉ thay ở mã nguồn Java khi đó là **literal**; hàm phân tích `String` không nhận dấu `_` trong chuỗi thập phân đó.

## 8. Checklist và tài liệu đối chiếu

- [ ] Dấu `_` chỉ nằm giữa chữ số hợp lệ, không sát tiền tố `0x`/`0b`, dấu chấm, dấu số mũ hoặc hậu tố kiểu.
- [ ] Các nhóm làm rõ hàng nghìn, byte, nibble hoặc ranh giới domain thật; không gây hiểu nhầm.
- [ ] Tên biến/hằng mô tả đơn vị, nhất là thời gian, dung lượng hoặc đại lượng đo.
- [ ] Kiểu `int`/`long`/`float`/`double` và phép tính tương ứng được chọn theo miền giá trị và độ chính xác cần thiết.
- [ ] Mã biên dịch được trên JDK được hỗ trợ; kết quả in và cách đọc đầu vào không bị nhầm với cú pháp source literal.

Tài liệu chính thức: [Java Language Specification — Numeric Literals](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html#jls-3.10) và [Dev.java — Using Underscore Characters in Numeric Literals](https://dev.java/learn/language/constructs/basics/primitive-types/).