# Math.scalb và nhân với lũy thừa của hai

`Math.scalb(x, n)` tính giá trị tương ứng với **x nhân 2 mũ n**, với quy tắc làm tròn của kiểu số thực kết quả. Nó phù hợp khi thuật toán cần thay đổi thang đo theo cơ số hai, đặc biệt khi muốn tránh tạo riêng một giá trị lũy thừa có thể bị tràn hoặc về không trước phép nhân.

API có từ Java 6 và vẫn áp dụng trong JDK hiện đại. Hiểu nó cần gắn phép nhân toán học với phạm vi hữu hạn của `float` và `double`.

## 1. Đọc hai tham số theo đúng vai trò

Chữ ký:

```java
public static double scalb(double d, int scaleFactor)
public static float scalb(float f, int scaleFactor)
```

`scaleFactor` là số mũ của hai, không phải hệ số nhân trực tiếp.

| Lời gọi | Phép toán toán học | Kết quả |
| --- | --- | --- |
| `Math.scalb(1.5, 3)` | 1.5 × 2³ | `12.0` |
| `Math.scalb(1.5, -2)` | 1.5 × 2⁻² | `0.375` |
| `Math.scalb(1.5, 0)` | 1.5 × 1 | `1.5` |

Số mũ dương tăng độ lớn; số mũ âm giảm độ lớn, trong phạm vi kết quả biểu diễn được. Vì lũy thừa của hai luôn dương, kết quả không phải NaN giữ dấu của đối số đầu, kể cả signed zero.

Hợp đồng API yêu cầu kết quả như một phép nhân số thực được làm tròn đúng một lần. Xem [Math.scalb(double,int)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#scalb(double,int)) và [overload float](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#scalb(float,int)).

## 2. Vì sao cơ số hai đặc biệt với số thực nhị phân?

Một số chuẩn hóa có thể được hình dung:

```text
dấu × phần định trị × 2^số_mũ
```

Trong miền còn biểu diễn chính xác được, nhân với lũy thừa của hai chủ yếu thay đổi thang mũ thay vì tạo ra một chuỗi chữ số nhị phân mới. Ví dụ, `1.5` là `1.1` trong nhị phân; nhân `2³` cho `1100`, tức `12`.

Tuy nhiên, mô hình này không cho phép kết luận rằng `scalb` luôn chính xác và đảo ngược được ở mọi đầu vào. Khi kết quả đi vào vùng dưới chuẩn hoặc vượt phạm vi, phải xét làm tròn, mất thông tin và tràn.

### Hai mốc khác nhau của double

| Hằng | Ý nghĩa |
| --- | --- |
| `Double.MIN_NORMAL` | Số dương chuẩn hóa nhỏ nhất, 2⁻¹⁰²² |
| `Double.MIN_VALUE` | Số dương khác không nhỏ nhất, 2⁻¹⁰⁷⁴ |

`MIN_VALUE` không phải số âm nhỏ nhất. Các giá trị dương giữa không và `MIN_NORMAL` là số dưới chuẩn (subnormal), có độ chính xác tương đối giảm khi tiến gần về không.

Xem [các hằng của Double](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html#MIN_NORMAL).

## 3. Chương trình hoàn chỉnh: từ phép nhân đơn giản đến biên biểu diễn

Tạo tệp `ScalbDemo.java`:

```java
public class ScalbDemo {
    public static void main(String[] args) {
        show("up", 1.5, 3);
        show("down", 1.5, -2);
        show("normal-to-subnormal", Double.MIN_NORMAL, -1);
        show("overflow", Double.MAX_VALUE, 1);
        show("half-min", Double.MIN_VALUE, -1);
        show("three-min-halved", 3.0 * Double.MIN_VALUE, -1);
        show("negative-half-min", -Double.MIN_VALUE, -1);
        show("negative-zero", -0.0, 100);
        show("infinity", Double.NEGATIVE_INFINITY, -100);
        System.out.println("nan=" + Double.isNaN(Math.scalb(Double.NaN, 10)));
        System.out.println("float=" + Math.scalb(1.5f, 3));
        System.out.println("scalb.tiny-up=" + Math.scalb(Double.MIN_VALUE, 1074));
        System.out.println("pow.tiny-up=" + (Double.MIN_VALUE * Math.pow(2.0, 1074)));
        System.out.println("scalb.large-down=" + Math.scalb(Double.MAX_VALUE, -1075));
        System.out.println("pow.large-down=" + (Double.MAX_VALUE * Math.pow(2.0, -1075)));
    }

    private static void show(String label, double value, int scale) {
        double result = Math.scalb(value, scale);
        System.out.println(label + "=" + result + ", hex=" + Double.toHexString(result));
    }
}
```

`Double.toHexString` giúp nhìn cấu trúc số nhị phân. Chữ `p` trong biểu diễn hex đi cùng số mũ **cơ số hai**; nó không phải số mũ cơ số 16.

### Biên dịch và chạy

Lưu tệp UTF-8 không BOM. Mở terminal tại thư mục chứa tệp, dùng JDK 17 trở lên có `javac` và `java` trong `PATH`:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out ScalbDemo.java
java -cp out ScalbDemo
```

Stdout đã kiểm chứng trên Microsoft OpenJDK 21.0.9:

```text
up=12.0, hex=0x1.8p3
down=0.375, hex=0x1.8p-2
normal-to-subnormal=1.1125369292536007E-308, hex=0x0.8p-1022
overflow=Infinity, hex=Infinity
half-min=0.0, hex=0x0.0p0
three-min-halved=9.9E-324, hex=0x0.0000000000002p-1022
negative-half-min=-0.0, hex=-0x0.0p0
negative-zero=-0.0, hex=-0x0.0p0
infinity=-Infinity, hex=-Infinity
nan=true
float=12.0
scalb.tiny-up=1.0
pow.tiny-up=Infinity
scalb.large-down=4.4408920985006257E-16
pow.large-down=0.0
```

Các số thập phân cực nhỏ khó đọc bằng mắt; dạng hex ở cạnh giúp đối chiếu giá trị nhị phân của kết quả.

## 4. Giải thích các trường hợp biên

### 4.1. Đi vào vùng dưới chuẩn chưa có nghĩa đã về không

`scalb(Double.MIN_NORMAL, -1)` chia mốc chuẩn hóa nhỏ nhất cho hai. Kết quả là số dưới chuẩn dương vẫn khác không và trong trường hợp này biểu diễn chính xác được:

```text
0x0.8p-1022
```

Vùng dưới chuẩn giúp việc giảm độ lớn diễn ra dần thay vì mọi kết quả dưới mốc chuẩn đều lập tức thành không.

### 4.2. Tràn vẫn có thể xảy ra ở kết quả cuối

`scalb(Double.MAX_VALUE, 1)` cần nhân số hữu hạn lớn nhất với hai, vượt phạm vi `double`, nên trả `Infinity`.

`scalb` tránh một số lỗi do giá trị trung gian; nó không mở rộng vô hạn phạm vi của kiểu dữ liệu và không ném ngoại lệ để báo mọi tình huống tràn số thực.

### 4.3. Làm tròn sát không có thể mất thông tin

Gọi `m = Double.MIN_VALUE`. Giá trị toán học `m / 2` nằm đúng giữa `0` và `m`. Với quy tắc làm tròn về gần nhất, hòa thì chọn chẵn, kết quả là `+0.0`.

Giá trị `3m / 2` nằm giữa `m` và `2m`; kết quả được chọn là `2m`, như dòng `three-min-halved`.

“Chẵn” ở đây nói về bit cuối của biểu diễn được làm tròn, không phải kiểm tra số thập phân có chia hết cho hai theo trực giác thông thường hay không.

Với đầu vào âm `-m`, phép chia thang tương tự trả `-0.0`, giữ dấu nguồn. Dấu âm của không xuất hiện trực tiếp ở stdout.

### 4.4. Không luôn khôi phục được sau khi thu nhỏ

Đoạn minh họa:

```java
double x = Double.MIN_VALUE;
double smaller = Math.scalb(x, -1);     // 0.0
double restored = Math.scalb(smaller, 1); // vẫn 0.0
```

Khi bước đầu đã làm mất thông tin, bước sau không thể tự tái tạo giá trị gốc. Tài liệu `scalb` cũng nêu rõ phép thu nhỏ rồi phóng lại có thể không trả về giá trị ban đầu khi kết quả dưới chuẩn.

## 5. Vì sao không luôn viết x * Math.pow(2.0, n)?

Trên giấy, hai biểu thức có cùng công thức. Trong máy, biểu thức dùng `pow` tạo riêng một kết quả trung gian rồi mới nhân.

### Lũy thừa trung gian bị tràn

```java
Math.scalb(Double.MIN_VALUE, 1074)
```

có kết quả toán học `2⁻¹⁰⁷⁴ × 2¹⁰⁷⁴ = 1`, và chương trình nhận `1.0`.

Trong khi đó:

```java
Double.MIN_VALUE * Math.pow(2.0, 1074)
```

tạo `2¹⁰⁷⁴` trước. Giá trị đó không biểu diễn được như một `double` hữu hạn, nên bước trung gian thành `Infinity`, kéo kết quả thành `Infinity`.

### Lũy thừa trung gian bị làm tròn về không

Ở chiều ngược lại:

```java
Math.scalb(Double.MAX_VALUE, -1075)
```

cho một kết quả hữu hạn dương khoảng `4.44 × 10⁻¹⁶`.

Nhưng `Math.pow(2.0, -1075)` được làm tròn về `0.0` trước khi nhân với `MAX_VALUE`, nên cách tính hai bước nhận `0.0`.

Các ví dụ cho thấy khác biệt về **đường tính trong số thực hữu hạn**, không phải khác biệt của công thức số thực toán học. Khi yêu cầu đúng là nhân với lũy thừa nguyên của hai, `scalb` thể hiện trực tiếp mục đích và hợp đồng làm tròn.

## 6. Dấu, NaN và vô cực

| Đầu vào thứ nhất | Kết quả scalb |
| --- | --- |
| NaN | NaN |
| `+Infinity` hoặc `-Infinity` | Vô cực cùng dấu |
| `+0.0` hoặc `-0.0` | Số không cùng dấu |
| Số hữu hạn khác không | Kết quả theo phép đổi thang và quy tắc làm tròn; giữ dấu nếu không phải NaN |

Đổi thang một giá trị vô cực không tự đưa nó về hữu hạn. Đổi thang `-0.0` bằng số mũ dương cũng không biến nó thành một số âm khác không.

Dùng `Double.isNaN` hoặc `Double.isFinite` khi thuật toán cần phân loại kết quả. Quyết định cho phép vô cực/NaN phải đến từ yêu cầu tính toán, không chỉ từ việc lời gọi phương thức không ném lỗi.

## 7. Chọn kiểu và viết biểu thức đúng

### Float và double

```java
float narrow = Math.scalb(1.5f, 3);
double wide = Math.scalb(1.5, 3);
```

Hậu tố `f` chọn giá trị `float`; literal `1.5` là `double`. Đối số số mũ là `int` ở cả hai overload.

Chọn kiểu của giá trị đầu vào có chủ đích. Hai kiểu có phạm vi và độ chính xác khác nhau, nên một phép đổi thang còn hữu hạn ở `double` có thể đã vượt phạm vi `float`.

### Dấu ^ không phải lũy thừa trong Java

Công thức `x × 2^n` trong văn bản toán học dùng ký hiệu mũ. Trong mã Java, `^` là XOR đối với các kiểu toán hạng phù hợp, không phải toán tử lũy thừa.

Tương tự, `1 << n` là dịch bit số nguyên. Nó có quy tắc kiểu, mặt nạ khoảng dịch và tràn số nguyên riêng, nên không phải cách tạo tổng quát lũy thừa hai cho số thực với số mũ âm hoặc lớn.

Dùng:

```java
double factor = Math.scalb(1.0, n);
```

khi thật sự cần một hệ số `double` độc lập có thể biểu diễn được. Nếu mục đích là nhân `x` với thang đó, gọi trực tiếp `Math.scalb(x, n)` để tránh tạo hệ số trung gian không biểu diễn được.

### Giữ kết quả trả về

`scalb` không sửa biến đầu vào:

```java
double x = 1.5;
double scaled = Math.scalb(x, 3);
// x vẫn 1.5; scaled là 12.0
```

## 8. Ứng dụng và giới hạn thực tế

Thao tác này hữu ích trong các thuật toán cần điều chỉnh thang nhị phân, tách phần độ lớn và số mũ, hoặc xử lý dữ liệu số ở nhiều bậc độ lớn.

Tuy nhiên, chọn thang phù hợp chỉ là một phần của thuật toán. Các phép cộng/trừ sau đó vẫn có thể mất chính xác; các bước khác vẫn có thể tràn. Không dùng một lời gọi `scalb` như bằng chứng rằng toàn bộ phép tính đã ổn định số học.

Khi kiểm thử, nên có ít nhất các nhóm:

- Giá trị thường với số mũ dương, âm và bằng không.
- Giá trị sát mốc chuẩn/dưới chuẩn.
- Giá trị có nguy cơ tràn và về không.
- Dấu âm, signed zero, vô cực và NaN.
- Kiểu `float` hoặc `double` đúng với dữ liệu thực tế.

## 9. Tự kiểm tra

1. Dự đoán `Math.scalb(-1.5, -2)` và giải thích dấu.
2. Vì sao `Double.MIN_NORMAL / 2` vẫn có thể khác không?
3. Vì sao thu nhỏ rồi phóng lại `Double.MIN_VALUE` có thể thất bại?
4. Hai ví dụ cuối chương trình thất bại ở bước trung gian nào khi dùng `pow`?
5. Vì sao `1 << n` không thay cho phép đổi thang số thực tổng quát?

Hãy xem `scalb` là phép **đổi thang theo lũy thừa của hai với kết quả được làm tròn đúng**, đồng thời vẫn tôn trọng phạm vi hữu hạn, số dưới chuẩn và các giá trị đặc biệt của kiểu số thực.
