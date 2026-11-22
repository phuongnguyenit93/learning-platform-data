# Dấu gạch dưới trong literal số và vị trí không hợp lệ

> **Java core — language-basics / Literal**  
> **Yêu cầu:** JDK 17+; một chương trình Java chạy độc lập, không dùng thư viện ngoài.  
> **Mục tiêu:** Biết khi nào được viết dấu `_` trong numeric literal, nhận ra các vị trí bị cấm và phân biệt cú pháp literal tại thời điểm biên dịch với chuỗi được parse khi chương trình chạy.

## 1. Dấu `_` dùng để làm gì?

Java cho phép chèn dấu gạch dưới giữa các chữ số trong **literal số** để dễ đọc, chẳng hạn:

~~~java
int population = 1_000_000;
long distance = 9_000_000_000L;
double rate = 12.3_4;
~~~

Dấu `_` ở đây **không thay đổi giá trị hoặc kiểu dữ liệu**. `1_000_000` và `1000000` là cùng một giá trị `int`; `9_000_000_000L` vẫn là literal `long` vì có hậu tố `L`.

| Cách viết | Giá trị | Vì sao hợp lệ? |
| --- | ---: | --- |
| `1_000_000` | 1000000 | Nhóm các chữ số thập phân |
| `0b1111_0000` | 240 | Nhóm các bit sau tiền tố nhị phân `0b` |
| `05_2` | 42 | Nhóm chữ số của literal bát phân (bắt đầu bằng `0`) |
| `0xCA_FE` | 51966 | Nhóm chữ số hệ 16 |
| `1__000` | 1000 | **Nhiều** dấu `_` liên tiếp giữa hai chữ số vẫn hợp lệ |
| `12.3_4` | 12.34 | Nhóm chữ số ở phần thập phân của floating-point literal |
| `1.2e1_0` | 1.2 × 10¹⁰ | Dấu `_` nằm giữa các chữ số phần số mũ |

Quy tắc thực dụng: **chèn `_` ở giữa các chữ số của cùng một phần literal, không đặt nó tại ranh giới tiền tố, dấu chấm, ký hiệu số mũ hay hậu tố kiểu.**

## 2. Các vị trí không hợp lệ

| Viết sai | Nguyên nhân | Viết đúng nếu giữ ý định |
| --- | --- | --- |
| `123_` | Kết thúc literal bằng dấu `_` | `123` hoặc `1_23` |
| `0b_1010` | Ngay sau tiền tố `0b` | `0b1010` hoặc `0b10_10` |
| `0x_FF` | Ngay sau tiền tố `0x` | `0xFF` hoặc `0xF_F` |
| `1_.25` | Ngay trước dấu chấm thập phân | `1.25` |
| `1._25` | Ngay sau dấu chấm thập phân | `1.25` hoặc `1.2_5` |
| `1e_10` | Ngay sau ký hiệu `e` của số mũ | `1e10` hoặc `1e1_0` |
| `1e+_10` | Ngay sau dấu `+` thuộc số mũ | `1e+10` |
| `123_L` | Ngay trước hậu tố kiểu `L` | `123L` hoặc `1_23L` |
| `12_f` | Ngay trước hậu tố `f` | `12f` hoặc `1_2f` |

Ngoài ra, `_123` là một **identifier có thể hợp lệ**, **không phải** literal số 123. Viết `int n = _123;` sẽ tìm **biến tên `_123`**, chứ không đưa số 123 vào `n`. Dấu `_` đứng **một mình** lại không được dùng làm identifier trong Java 17.

**Phân biệt quan trọng:** `1__000` **hợp lệ**, không nên suy diễn rằng cứ có hai dấu gạch dưới liền nhau là sai. Vị trí tương đối với **chữ số, dấu phân cách và hậu tố** mới là điều quyết định.

## 3. Áp dụng cho những loại literal số nào?

Cú pháp dấu `_` dùng được cho **integer literal** và **floating-point literal** ở những vị trí hợp lệ:

- Số nguyên: thập phân `4_200`, nhị phân `0b1010_0101`, bát phân `07_52`, thập lục phân `0xAB_CD`, `long` như `1_000L`.
- Số thực: `3.14_15`, `1_2.5_0f`, hoặc số mũ `6.02e2_3`.
- Số thực hex cũng có quy tắc riêng về chữ số và dấu mũ `p`, ví dụ `0x1.8p1_0` là literal `double` hợp lệ (giá trị 1536.0).

**Không được chèn `_` tùy tiện vào một tiền tố/cú pháp rồi nghĩ rằng compiler sẽ tự bỏ nó.** Ví dụ `0x_FF` và `1_.0` không là cách viết số hợp lệ.

Chú ý rằng `-1_000` có **toán tử dấu trừ** đứng trước literal `1_000`; dấu `_` vẫn chỉ phục vụ nhóm chữ số. Dấu `L`, `f`, `d` xác định loại literal theo quy tắc tương ứng, không phải chữ số để kẹp thêm `_` sát vào.

## 4. Chương trình Java 17+ chạy được

Tạo file **NumericUnderscoreDemo.java** và chép toàn bộ mã:

~~~java
public class NumericUnderscoreDemo {
    public static void main(String[] args) {
        int decimal = 4_2;
        int binary = 0b1111_0000;
        int octal = 05_2;
        int hex = 0xCA_FE;
        int repeated = 1__000;
        long large = 9_000_000_000L;
        double fraction = 12.3_4;

        System.out.println("decimal=" + decimal);
        System.out.println("binary=" + binary);
        System.out.println("octal=" + octal);
        System.out.println("hex=" + hex);
        System.out.println("repeated=" + repeated);
        System.out.println("large=" + large);
        System.out.println("fraction=" + fraction);
        System.out.println("same42=" + (decimal == octal));

        try {
            Integer.parseInt("1_000");
            System.out.println("parse=OK");
        } catch (NumberFormatException exception) {
            System.out.println("parse=ERROR");
        }
    }
}
~~~

Trong terminal (Bash, PowerShell hoặc Command Prompt), từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 NumericUnderscoreDemo.java
java NumericUnderscoreDemo
~~~

**Đầu ra mong đợi:**

~~~text
decimal=42
binary=240
octal=42
hex=51966
repeated=1000
large=9000000000
fraction=12.34
same42=true
parse=ERROR
~~~

Ở đây `05_2` là số **bát phân**: \(5 \times 8 + 2 = 42\). `0xCA_FE` là số hex `CAFE` (51966 thập phân). Cả hai chỉ là **cách ghi giá trị trong mã nguồn**, không phải chuỗi đặc biệt được in nguyên dạng.

## 5. Compiler và chuỗi đầu vào không dùng cùng quy tắc

Đây là điểm phân biệt thiết yếu:

~~~java
int fromSource = 1_000;             // Hợp lệ: compiler hiểu literal Java.
int fromText = Integer.parseInt("1000"); // Hợp lệ: parse chuỗi toàn chữ số.
~~~

Nhưng:

~~~java
Integer.parseInt("1_000"); // Ném NumberFormatException khi chạy.
~~~

`Integer.parseInt` không tự loại `_` như compiler Java xử lý ở numeric literal. Nếu ứng dụng muốn người dùng nhập `1_000`, bạn phải định nghĩa **quy tắc kiểm tra định dạng**, rồi xử lý đầu vào trước khi chuyển kiểu. Đừng chỉ xóa mọi dấu `_` mà không kiểm tra, vì như vậy các chuỗi sai như `_123` hoặc `123_` có thể bị biến thành số hợp lệ ngoài ý định.

Tương tự, literal `1_000L` chứa hậu tố `L` của **source code**, nhưng `Long.parseLong("1_000L")` không chấp nhận chuỗi ấy.

## 6. Các bẫy cần kiểm tra

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Có `_` thì kiểu số thành String.” | Sai. Numeric literal vẫn có kiểu số tương ứng. |
| “`1__000` luôn sai.” | Sai. Dấu `_` liên tiếp giữa chữ số được cho phép. |
| “`0x_FF` tương đương `0xFF`.” | Sai. Không được chèn `_` ngay sau tiền tố. |
| “Xuống dòng hoặc khoảng trắng cạnh `_` cũng được.” | Sai khi làm vỡ một literal: `1_ 000` không còn là numeric literal hợp lệ. |
| “`123_L` là `long` hợp lệ.” | Sai. Hậu tố `L` phải theo sau phần chữ số đúng cú pháp. |
| “`parseInt("1_000")` hoạt động như compiler.” | Sai. `parseInt` không nhận dấu `_` làm nhóm chữ số. |

**Thử nghiệm có chủ đích:** chọn một ví dụ sai ở bảng mục 2, đặt vào một dòng riêng của `NumericUnderscoreDemo.java`, rồi chạy `javac` để quan sát lỗi. Sau đó sửa lại và biên dịch lần nữa. Không thêm toàn bộ các ví dụ sai vào chương trình chính, vì chương trình sẽ không thể biên dịch.

## 7. Bài tập ngắn

**Bài 1 — Đúng hay sai?** Phân loại các literal `1_234`, `1__234`, `1_`, `0b10_01`, `0b_1001`, `0xA_B`, `0x_AB`, `3.1_4` và `3._14`. Nêu *vị trí* quyết định kết quả, không chỉ ghi “sai cú pháp”.

**Bài 2 — Giữ nguyên giá trị.** Viết lại `1000000000L`, `0b11110000` và `0xCAFEBABE` sao cho dễ đọc bằng `_` mà giá trị không đổi. Thử in từng giá trị để tự kiểm tra.

**Bài 3 — Source so với runtime.** Vì sao `Integer.parseInt("1000")` thành công còn `Integer.parseInt("1_000")` thất bại? Nếu làm công cụ đọc cấu hình chấp nhận `_`, bạn sẽ kiểm tra vị trí gạch dưới như thế nào?

**Bài 4 — Debug.** Sửa hai literal sai `1e_10` và `9_000_L`, giải thích vì sao ký hiệu exponent và suffix không phải vị trí được phép đặt dấu `_`.

### Ghi nhớ

**Dấu `_` là ký hiệu giúp con người đọc numeric literal rõ hơn, không mang giá trị và không tự mở rộng cú pháp parser cho chuỗi runtime.** Đặt nó **giữa chữ số hợp lệ**, có thể nhiều dấu liên tiếp; **không** đặt ở đầu/cuối literal hoặc sát tiền tố, dấu chấm, ký hiệu số mũ hay hậu tố kiểu.
