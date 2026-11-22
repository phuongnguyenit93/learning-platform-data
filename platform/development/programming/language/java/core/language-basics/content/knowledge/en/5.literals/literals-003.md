# Literal số thực, ký hiệu số mũ và hậu tố F hoặc D trong Java 17+

**Floating-point literal** là giá trị số thực viết trực tiếp trong mã Java, chẳng hạn `3.14`, `2e3` hoặc `0.5F`. Nó khác literal số nguyên `2` về **kiểu**, cách biểu diễn và phép tính.

Trong Java 17, literal số thực **không có hậu tố** mặc định là `double`. Muốn ghi rõ một literal thuộc kiểu `float`, thêm hậu tố `F` hoặc `f`; hậu tố `D` hoặc `d` xác nhận kiểu `double` nhưng **không bắt buộc**.

## 1. Nhận diện cú pháp

| Literal | Kiểu | Giá trị toán học | Ghi chú |
| --- | --- | --- | --- |
| `3.14` | `double` | 3,14 | Không có hậu tố |
| `3.14D` | `double` | 3,14 | `D` viết tường minh |
| `3.14f` | `float` | 3,14 | `f`/`F` chỉ định kiểu float |
| `2e3` | `double` | 2 × 10³ = 2000 | `e`/`E` là ký hiệu số mũ thập phân |
| `6.02E-3` | `double` | 6,02 × 10⁻³ | Số mũ âm |
| `1.25e+2F` | `float` | 125 | Số mũ có dấu `+`, hậu tố `F` |
| `.5` | `double` | 0,5 | Được phép bỏ chữ số trước dấu chấm |
| `5.` | `double` | 5,0 | Được phép bỏ chữ số sau dấu chấm |
| `1_000.5` | `double` | 1000,5 | `_` giúp nhóm chữ số tại vị trí hợp lệ |
| `5` | `int` | 5 | Literal **số nguyên**, không phải số thực |

Ký hiệu `e`/**`E`** ở đây có nghĩa “nhân với `10` lũy thừa số nguyên”, **không phải hằng số Euler**.

Cấu trúc điển hình:

~~~text
phần định trị [e hoặc E] [dấu + hoặc -] số mũ [F/f/D/d]
      1.25        e          -             3        F
~~~

Ví dụ `1.25e-3F` là literal kiểu `float` có giá trị toán học `0.00125`, được làm tròn tới độ chính xác của `float`. Nếu dùng ký hiệu `e/E` thì phần số mũ phải có chữ số; `1e` và `1e+` **không hợp lệ**.

Java cũng có literal số thực hệ 16 như `0x1.8p1` (bằng `3.0`, kiểu `double`): `p/P` biểu diễn số mũ **cơ số 2**, không phải `e/E`. Đây là cú pháp riêng, không cần dùng để hiểu ví dụ thập phân bên dưới.

## 2. Ví dụ Java 17 chạy được

Tạo tệp **`FloatingLiteralDemo.java`** (tên tệp khớp với `public class`):

~~~java
public class FloatingLiteralDemo {
    public static void main(String[] args) {
        double regular = 12.5;
        double large = 1.25e3;
        double small = 6.02E-3;
        float withF = 2.5F;
        double withD = 2.5D;
        double leadingDot = .5;
        double trailingDot = 5.;
        double hex = 0x1.8p1;

        double fromIntegerDivision = 5 / 2;
        double fromFloatingDivision = 5 / 2.0;

        System.out.println("regular=" + regular);
        System.out.println("large=" + large);
        System.out.println("small=" + small);
        System.out.println("withF=" + withF);
        System.out.println("withD=" + withD);
        System.out.println("leadingDot=" + leadingDot);
        System.out.println("trailingDot=" + trailingDot);
        System.out.println("hex=" + hex);
        System.out.println("integerDivision=" + fromIntegerDivision);
        System.out.println("floatingDivision=" + fromFloatingDivision);
        System.out.println("exactEquality=" + (0.1 + 0.2 == 0.3));
    }
}
~~~

Mở PowerShell (Windows) hoặc terminal Bash (Linux) tại thư mục chứa tệp, rồi dùng **cùng các lệnh**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 FloatingLiteralDemo.java
java FloatingLiteralDemo
~~~

**Kết quả dự kiến:**

~~~text
regular=12.5
large=1250.0
small=0.00602
withF=2.5
withD=2.5
leadingDot=0.5
trailingDot=5.0
hex=3.0
integerDivision=2.0
floatingDivision=2.5
exactEquality=false
~~~

**Tại sao?** `1.25e3` bằng `1250.0` dù lệnh in không nhất thiết giữ nguyên dạng số mũ. `5 / 2` dùng phép chia hai `int`, kết quả nguyên `2` rồi mới đổi thành `double` `2.0`; ngược lại, `5 / 2.0` thực hiện chia số thực, cho `2.5`. Phép so sánh cuối là `false` vì một số phân số thập phân (như `0.1`) **không được biểu diễn chính xác** bằng số thực nhị phân IEEE 754.

## 3. `float` so với `double`: hậu tố quyết định kiểu literal

~~~java
double a = 1.5;  // Đúng: literal mặc định là double.
double b = 1.5D; // Đúng: thêm D tường minh.
float c = 1.5F;  // Đúng: literal kiểu float.
double d = 1.5F; // Đúng: float được mở rộng thành double.

// float e = 1.5; // Sai biên dịch: double không tự thu hẹp thành float.
~~~

| Tiêu chí | `float` | `double` |
| --- | --- | --- |
| Kích thước | 32 bit | 64 bit |
| Độ chính xác xấp xỉ | 6–7 chữ số thập phân có nghĩa | 15–16 chữ số thập phân có nghĩa |
| Hậu tố literal | `f` hoặc `F` | `d`/`D`, hoặc bỏ hậu tố |
| Ví dụ | `0.1F` | `0.1`, `0.1D` |

Chuyển một literal `double` sang `float` bằng cast, ví dụ `(float) 1.5`, có thể hợp lệ nhưng **có nguy cơ mất độ chính xác hoặc vượt miền**. Khi chủ ý ghi literal `float`, dùng `F` thường rõ nghĩa hơn.

Một literal âm như `-2.5F` được phân tích theo toán tử **đổi dấu** `-` áp dụng lên literal `2.5F`; dấu trừ không phải phần độc lập của token literal. Điều này giúp hiểu vì sao biểu thức và literal có thể có quy tắc riêng.

## 4. Giới hạn, quy tắc gạch dưới và sai lầm thường gặp

| Mã hoặc tình huống | Đúng/sai | Giải thích |
| --- | --- | --- |
| `double rate = 1e-3;` | Đúng | `0.001`, kiểu double |
| `float rate = 1e-3F;` | Đúng | Hậu tố `F`, kiểu float |
| `float rate = 1e-3;` | **Lỗi biên dịch** | Vế phải là double; không tự thu hẹp |
| `double n = 1e;` | **Lỗi biên dịch** | Thiếu số mũ |
| `double n = 1_.0;` | **Lỗi biên dịch** | Gạch dưới sát dấu chấm không hợp lệ |
| `double n = 1_000.0;` | Đúng | Nhóm chữ số hợp lệ |
| `double n = 1e400;` | **Lỗi biên dịch** | Literal double hữu hạn vượt miền biểu diễn |
| `float n = 1e40F;` | **Lỗi biên dịch** | Literal float hữu hạn vượt miền biểu diễn |
| `double n = 5 / 2;` | Đúng cú pháp, có thể sai ý định | Kết quả `2.0`, không phải `2.5` |

Một literal số thực **khác 0** mà nhỏ tới mức làm tròn thành 0 trong kiểu đã chọn cũng không hợp lệ khi viết trực tiếp; ví dụ `1e-400` vượt phía dưới độ lớn biểu diễn được của `double`. Nhưng các **phép tính lúc chạy** vẫn có thể tạo `Infinity`, `NaN`, số *subnormal* hoặc giá trị 0 do underflow; đó là vấn đề khác với kiểm tra literal lúc biên dịch.

### Khi nào không nên dùng `float`/`double`?

Các kiểu này biểu diễn số thực **xấp xỉ**, phù hợp tính toán khoa học, đồ họa, thống kê khi chấp nhận sai số số học. Với **tiền và phép tính yêu cầu thập phân chính xác**, nên cân nhắc `BigDecimal` (khởi tạo từ **chuỗi** khi cần giữ chính xác giá trị thập phân), hoặc đơn vị tiền nguyên theo yêu cầu bài toán.

Ví dụ `new java.math.BigDecimal("0.1")` giữ chính xác giá trị thập phân `0.1` theo mô hình `BigDecimal`, khác với `new BigDecimal(0.1)` vốn nhận giá trị `double` đã xấp xỉ.

## 5. Bài tập tự kiểm tra

1. **Xác định kiểu:** `7.5`, `7.5f`, `2e2`, `2e2D`.  
   *Đáp án:* Lần lượt `double`, `float`, `double`, `double`.
2. **Đổi sang thập phân thông thường:** `3.2e2` và `6.5E-2F`.  
   *Đáp án:* Giá trị toán học lần lượt `320` và `0.065`; literal thứ hai có kiểu `float`.
3. **Sửa lỗi:** `float x = 0.25;`.  
   *Đáp án:* `float x = 0.25F;`, hoặc chọn `double x = 0.25;`.
4. **Dự đoán:** `double x = 7 / 2;` và `double y = 7 / 2.0;`.  
   *Đáp án:* `x == 3.0`, `y == 3.5`.
5. **Thử độ chính xác:** chạy `System.out.println(0.1 + 0.2 == 0.3);`.  
   *Đáp án:* `false`; không dùng so sánh `==` một cách máy móc cho các kết quả tính toán số thực xấp xỉ.

**Ghi nhớ:** Trong Java 17, literal số thực mặc định thuộc `double`, hậu tố `F/f` đổi thành `float`, `D/d` chỉ ghi rõ `double`. Ký hiệu `e/E` nhân với lũy thừa của 10; kiểu của **toán hạng ngay tại phép tính** quyết định cách chia và độ chính xác, chứ không chỉ kiểu biến ở vế trái.
