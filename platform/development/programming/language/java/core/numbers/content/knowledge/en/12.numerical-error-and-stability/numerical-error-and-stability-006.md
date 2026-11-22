# Điều kiện bài toán và trường hợp sai số đầu vào bị khuếch đại

Trong tính toán số, **một kết quả sai nhiều không nhất thiết bắt nguồn từ code Java sai**. Có những bài toán vốn rất nhạy: chỉ thay đổi một lượng rất nhỏ trong dữ liệu đầu vào cũng làm **giá trị đầu ra thay đổi lớn theo tỷ lệ tương đối**. Tính chất này gọi là **điều kiện của bài toán** (*conditioning*). Một bài toán có điều kiện xấu (*ill-conditioned*) vẫn có thể được giải bằng thuật toán ổn định; ngược lại, một bài toán có điều kiện tốt vẫn có thể bị tính sai nếu chọn công thức hoặc cách triển khai không ổn định.

Ví dụ đơn giản là lấy hiệu hai số gần nhau:

```text
a = 1 + 2^-40
b = 1

a - b = 2^-40

Nếu a tăng 2^-50:
(a + 2^-50) - b = 2^-40 + 2^-50
```

**Thay đổi tuyệt đối** của đầu vào và đầu ra đều là `2^-50`, nhưng **tỷ lệ thay đổi của đầu ra so với giá trị hiệu ban đầu** là `2^-10 = 0.0009765625` (gần 0,1%). Trong khi đó, tỷ lệ thay đổi của `a` chỉ khoảng `8.88 × 10^-16`. Chênh lệch tương đối được khuếch đại hơn **một nghìn tỷ lần**.

Bài học sẽ giải thích điều kiện tuyệt đối, điều kiện tương đối, số điều kiện, phép trừ gần triệt tiêu, bài toán gần điểm kỳ dị, và cách phân biệt **độ nhạy vốn có của đầu vào** với **lỗi do thuật toán** khi lập trình Java.

## 1. Hai loại sai số cần tách biệt

Cho một bài toán toán học nhận đầu vào `x` và tính đầu ra `f(x)`. Trong thực tế, máy tính có thể nhận `x̃` thay vì `x` do dữ liệu đo đạc, chuyển đổi văn bản sang số thực, hoặc kết quả của các phép tính trước đó. Sau đó máy tính tạo ra một kết quả xấp xỉ `ŷ`.

Ta có thể phân tích hai ảnh hưởng khác nhau:

1. **Ảnh hưởng của nhiễu đầu vào:** so sánh `f(x̃)` với `f(x)`. Nếu chỉ thay đổi một chút đầu vào mà kết quả đúng của bài toán thay đổi mạnh, **bài toán nhạy**. Đây là conditioning.
2. **Ảnh hưởng của thuật toán/số học máy:** so sánh `ŷ` với `f(x̃)`. Nếu thuật toán tạo nhiều sai số bổ sung do làm tròn, overflow, underflow hoặc phép biến đổi bất lợi, đó là vấn đề **ổn định của thuật toán** (*numerical stability*).

Một cách tóm lược:

```text
Đầu vào lý tưởng x
      │ sai số đo/chuyển đổi dữ liệu
      ▼
Đầu vào thực có x̃ ──[bài toán toán học]──► f(x̃)
      │                                         │
      └────────[thuật toán số thực tế]────────► ŷ
```

**Conditioning** liên quan tới chính hàm toán học và điểm đầu vào; **stability** liên quan tới cách tính hàm ấy. Thuật toán tốt có thể giảm sai số tính toán **thêm vào**, nhưng không thể bảo đảm khôi phục thông tin không có trong đầu vào.

## 2. Sai số tuyệt đối và sai số tương đối

Với đại lượng đúng `v` và đại lượng xấp xỉ `ṽ`:

```text
Sai số tuyệt đối:       |ṽ - v|
Sai số tương đối:       |ṽ - v| / |v|    (khi v khác 0)
```

Ví dụ: cùng sai số tuyệt đối `0.001`, nhưng ở giá trị `1000` tỷ lệ chỉ `10^-6`, còn ở giá trị `0.01` tỷ lệ là `0.1`, tức **10%**. Vì vậy, cần nêu rõ đang nói tới **độ lớn tuyệt đối** hay **tỷ lệ tương đối**.

Đối với đầu ra bằng 0 hoặc rất gần 0, sai số tương đối có thể **không xác định hoặc cực lớn** dù sai số tuyệt đối rất nhỏ. Khi đó, một chuẩn sai số tuyệt đối có thang đo nghiệp vụ thường hữu ích hơn. Không nên chia bừa cho một giá trị gần zero rồi diễn giải con số rất lớn như “thuật toán chắc chắn sai”.

Lưu ý Java có `double` hữu hạn, `NaN`, Infinity và `+0.0`/`-0.0`; nếu tự viết công cụ đo sai số, hãy xác định cách xử lý các trường hợp này trước khi chia hoặc so sánh.

## 3. Điều kiện tuyệt đối và điều kiện tương đối của hàm một biến

Với hàm `f(x)` khả vi và nhiễu nhỏ `δx`, xấp xỉ tuyến tính là:

```text
δy = f(x + δx) - f(x) ≈ f'(x) × δx
```

**Độ nhạy tuyệt đối cục bộ** được phản ánh bởi `|f'(x)|`: giá trị lớn cho biết nhiễu tuyệt đối nhỏ ở `x` có thể tạo thay đổi tuyệt đối lớn ở `f(x)`.

Nếu `x ≠ 0` và `f(x) ≠ 0`, **số điều kiện tương đối cục bộ** thường được định nghĩa:

```text
κ_rel(x) = |x × f'(x) / f(x)|
```

Khi `δx` đủ nhỏ để xấp xỉ tuyến tính phù hợp:

```text
|δy| / |f(x)| ≈ κ_rel(x) × (|δx| / |x|)
```

Diễn giải:

- `κ_rel ≈ 1`: sai số tương đối đầu ra cùng bậc với đầu vào (theo mô hình cục bộ).
- `κ_rel ≫ 1`: sai số tương đối của đầu vào có thể được **khuếch đại mạnh** ở đầu ra; đây là điều kiện xấu về mặt tương đối.
- `κ_rel ≪ 1`: một nhiễu tương đối nhỏ ở đầu vào có thể tạo nhiễu tương đối đầu ra còn nhỏ hơn.

Đây là **xấp xỉ cục bộ**, không phải bảo đảm cho mọi nhiễu lớn. Số điều kiện còn phụ thuộc **chuẩn đo đầu vào/đầu ra và cách đặt bài toán**; gần zero, thang đo tuyệt đối và tương đối có thể đưa tới những nhận định khác nhau.

## 4. Phép trừ hai số gần nhau: đầu ra nhỏ, độ nhạy tương đối lớn

Xét `f(a,b) = a - b`. Đây là bài toán hai đầu vào. Nếu cả `a` và `b` đều có nhiễu:

```text
a → a + δa
b → b + δb

(a + δa) - (b + δb) = (a - b) + (δa - δb)
```

Sai số tuyệt đối của hiệu **không vượt** `|δa| + |δb|`, nhưng nếu `|a-b|` rất nhỏ so với `|a|` và `|b|`, sai số tương đối của hiệu có thể lớn. Một thước đo điều kiện tương đối cho phép trừ (với thành phần đầu vào có sai số tương đối cùng cỡ) là:

```text
κ_sub ≈ (|a| + |b|) / |a - b|
```

Khi `a ≈ b`, mẫu số rất nhỏ, khiến `κ_sub` lớn. Điều này không có nghĩa lệnh trừ của CPU nhất định sai. Trái lại, phép trừ hai số floating-point đủ gần nhau đôi khi còn **chính xác hoàn toàn đối với hai giá trị đã được biểu diễn** (liên quan tới định lý Sterbenz). Vấn đề là nếu dữ liệu đầu vào hơi đổi, **đáp án đúng của bài toán cũng đổi nhiều theo tỷ lệ**.

Ví dụ được chọn với các số nhị phân biểu diễn chính xác:

```java
double a = 1.0 + 0x1.0p-40;
double changedA = a + 0x1.0p-50;
double difference = a - 1.0;
double changedDifference = changedA - 1.0;
```

Trong literal hex floating-point của Java, `0x1.0p-40` là `2^-40`, `0x1.0p-50` là `2^-50`. Tất cả các giá trị này được `double` biểu diễn chính xác.

| Chỉ số | Giá trị |
| --- | --- |
| Hiệu ban đầu `a - 1` | `2^-40` |
| Nhiễu thêm vào `a` | `2^-50` ≈ `8.881784197001252E-16` |
| Thay đổi tuyệt đối của hiệu | Cũng là `2^-50` |
| Thay đổi tương đối của hiệu | `2^-10 = 0.0009765625` |
| Thay đổi tương đối của `a` | Khoảng `8.88E-16` |
| Hệ số khuếch đại tương đối tại điểm xét | Gần `2^40`, hơn một nghìn tỷ lần |

Trong ví dụ có đúng một đầu vào biến động, ta xem `f(a)=a-1`; số điều kiện tương đối là `|a/(a-1)| = 2^40+1`. Giá trị của hệ số khuếch đại tính bằng hai sai khác thực tế cũng bằng **1_099_511_627_777** (in dưới dạng số nguyên), trong khi phép trừ ở ví dụ **không mắc lỗi làm tròn đầu ra**. Đó là minh chứng rõ ràng rằng conditioning xấu và thuật toán mất ổn định **không phải một khái niệm**.

## 5. Hàm có mẫu số gần zero: điều kiện xấu gần điểm kỳ dị

Xét:

```text
f(x) = 1 / (x - 1),   x ≠ 1

f'(x) = -1 / (x - 1)^2

κ_rel(x) = |x / (x - 1)|
```

Khi `x` tiến gần `1`, cả đạo hàm tuyệt đối lẫn số điều kiện tương đối có thể rất lớn. Ví dụ, với `x = 1 + 2^-20`:

```text
f(x) = 2^20 = 1_048_576
κ_rel(x) ≈ 2^20
```

Nếu tăng `x` thêm `2^-40` (khoảng `9.09 × 10^-13`), đầu ra đổi thành gần `1_048_575.0000009537`. Đầu vào thay đổi cực nhỏ, nhưng sự thay đổi tương đối của đầu ra có độ lớn gần một phần triệu, tức hệ số khuếch đại vào khoảng một triệu lần so với sai số tương đối đầu vào.

Đây là hệ quả của bài toán **gần cực (pole)**, không phải do lập trình viên viết thiếu dấu ngoặc. Một thuật toán ổn định tính `1/(x-1)` vẫn phải chịu độ nhạy này nếu giá trị thực của `x` không chắc chắn.

Tại **`x = 1.0` chính xác**, phép chia `1.0 / (x - 1.0)` trong Java trả **`+Infinity`** theo ngữ nghĩa floating-point; không ném `ArithmeticException` như phép chia **số nguyên** cho zero. Trong chương trình thực cần kiểm tra miền xác định và khoảng cách tới điểm kỳ dị trước khi dùng kết quả.

## 6. Vì sao “thuật toán ổn định” không xóa được điều kiện xấu?

Một thuật toán được gọi là **ổn định số** khi sai số do tính toán của nó được kiểm soát tốt so với yêu cầu và độ nhạy của bài toán. Phân biệt hai hướng đánh giá phổ biến:

- **Forward error:** `|ŷ - f(x)|`, tức khoảng cách từ đáp án máy tính đến đáp án lý tưởng tại đầu vào gốc.
- **Backward error:** xem `ŷ` có thể được coi là đáp án đúng `f(x+Δx)` của **một đầu vào gần `x`** hay không. Nếu có với `Δx` đủ nhỏ theo chuẩn đã chọn, thuật toán có thể được đánh giá là ổn định ngược (*backward stable*).

Với bài toán điều kiện tốt, một thuật toán có backward error nhỏ thường cho forward error nhỏ. Với bài toán điều kiện xấu, **ngay cả thay đổi đầu vào rất nhỏ** vẫn có thể cho forward error lớn. Một quy tắc phân tích ở mức xấp xỉ cục bộ là:

```text
sai số tương đối đầu ra
    ≈ số điều kiện × sai số tương đối đầu vào
      + ảnh hưởng sai số thuật toán
```

Công thức mang tính trực giác, không phải định luật cộng sai số có thể áp dụng nguyên xi cho mọi hàm hay mọi trường hợp `NaN`/Infinity. Phân tích chính xác cần xác định chuẩn đo, các hạng sai số và phạm vi đầu vào. Tuy vậy, nguyên tắc quan trọng là: **thuật toán tốt không thể làm một bài toán ill-conditioned trở thành well-conditioned chỉ bằng việc thay cách viết code**.

## 7. Trường hợp ngược lại: bài toán không quá nhạy nhưng công thức tính gây mất ổn định

Xét hàm:

```text
g(x) = sqrt(x + 1) - sqrt(x),  với x ≥ 0
```

Khi `x` rất lớn, hai căn bậc hai gần bằng nhau. Phép trừ hai số sau khi làm tròn có thể **triệt tiêu gần hết các chữ số có nghĩa**. Nhưng ta có thể biến đổi đại số (với `x ≥ 0`):

```text
sqrt(x+1) - sqrt(x)
    = ((x+1)-x) / (sqrt(x+1)+sqrt(x))
    = 1 / (sqrt(x+1)+sqrt(x))
```

Trong Java:

```java
double x = 1.0e16;
double direct = Math.sqrt(x + 1.0) - Math.sqrt(x);
double stable = 1.0 / (Math.sqrt(x + 1.0) + Math.sqrt(x));
```

Với `x = 1e16`, `x + 1.0` bị làm tròn về chính `x` ở kiểu `double`; cách viết trực tiếp cho **`0.0`**. Cách viết theo mẫu số cho khoảng **`5.0E-9`**, gần giá trị toán học `1/(2×10^8)`.

Điểm mấu chốt: **bài toán tính `g(x)` không tự nhiên vô vọng ở `x` lớn** (theo độ nhạy tương đối, nó khá tốt ở miền này), nhưng cách tính hiệu của hai căn gần nhau gây mất ổn định. Biến đổi công thức giúp tránh phép trừ gây hủy triệt tiêu. Đây là lỗi **thuật toán**, khác với ví dụ `a-b` có đầu vào không chắc chắn và hiệu rất nhỏ.

Không nên áp dụng công thức biến đổi một cách mù quáng cho mọi miền: cần kiểm tra miền xác định và nguy cơ overflow/underflow của các trung gian trong công thức mới. Với `x ≥ 0` hữu hạn của ví dụ và độ lớn thông dụng, dạng nghịch đảo là lựa chọn tốt để tránh cancellation.

## 8. Một công thức tốt hơn còn có thể tránh overflow trung gian

Tính độ dài vector hai chiều:

```text
h(a,b) = sqrt(a^2 + b^2)
```

Bài toán này thường **không nhạy quá mức** theo sai số tương đối của các thành phần khi độ lớn có ý nghĩa. Nhưng công thức trực tiếp có thể tràn dù kết quả cuối vẫn nằm trong phạm vi `double`:

```java
double a = 1.0e200;
double naive = Math.sqrt(a * a + a * a); // Infinity.
double robust = Math.hypot(a, a);        // Hữu hạn, khoảng 1.414e200.
```

Ở đây `a*a = 1e400` vượt `Double.MAX_VALUE` trước khi gọi `sqrt`. `Math.hypot` dùng phương pháp phù hợp để tránh overflow/underflow trung gian trong những trường hợp như vậy. Ví dụ này không phải “sửa điều kiện bài toán”: nó dùng **thuật toán tốt hơn** để tính một hàm vốn có kết quả hữu hạn.

Thông điệp thực tiễn: trước khi tăng độ chính xác kiểu số, hãy xem có **hàm thư viện hoặc biến đổi ổn định** cho chính phép tính đang thực hiện không.

## 9. Chương trình Java 17+ chạy độc lập

Tạo tệp **`ConditionSensitivityDemo.java`**:

```java
public class ConditionSensitivityDemo {
    public static void main(String[] args) {
        double x = 1.0 + 0x1.0p-40;
        double perturbed = x + 0x1.0p-50;
        double gap = x - 1.0;
        double perturbedGap = perturbed - 1.0;

        double relativeInputChange = (perturbed - x) / x;
        double relativeOutputChange = (perturbedGap - gap) / gap;
        System.out.println("gapHex=" + Double.toHexString(gap));
        System.out.println("changedGapHex=" + Double.toHexString(perturbedGap));
        System.out.println("absoluteInputChange=" + (perturbed - x));
        System.out.println("absoluteOutputChange=" + (perturbedGap - gap));
        System.out.println("relativeOutputChange=" + relativeOutputChange);
        System.out.println("relativeAmplificationRounded="
                + Math.round(relativeOutputChange / relativeInputChange));

        double p = 1.0 + 0x1.0p-20;
        double q = p + 0x1.0p-40;
        double fP = 1.0 / (p - 1.0);
        double fQ = 1.0 / (q - 1.0);
        System.out.println("nearPoleOriginal=" + fP);
        System.out.println("nearPoleChanged=" + fQ);
        System.out.println("nearPoleOutputChanged=" + (fP != fQ));

        double large = 1.0e16;
        double direct = Math.sqrt(large + 1.0) - Math.sqrt(large);
        double reformulated =
                1.0 / (Math.sqrt(large + 1.0) + Math.sqrt(large));
        System.out.println("directCancellation=" + direct);
        System.out.println("stableReformulation=" + reformulated);

        double a = 1.0e200;
        System.out.println("naiveHypotenuseInfinite="
                + Double.isInfinite(Math.sqrt(a * a + a * a)));
        System.out.println("hypotFinite=" + Double.isFinite(Math.hypot(a, a)));

        double threshold = 0x1.0p53;
        System.out.println("inputIncrementLost=" + (threshold + 1.0 == threshold));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ConditionSensitivityDemo.java
java ConditionSensitivityDemo
```

Kết quả stdout chính xác:

```text
gapHex=0x1.0p-40
changedGapHex=0x1.004p-40
absoluteInputChange=8.881784197001252E-16
absoluteOutputChange=8.881784197001252E-16
relativeOutputChange=9.765625E-4
relativeAmplificationRounded=1099511627777
nearPoleOriginal=1048576.0
nearPoleChanged=1048575.0000009537
nearPoleOutputChanged=true
directCancellation=0.0
stableReformulation=5.0E-9
naiveHypotenuseInfinite=true
hypotFinite=true
inputIncrementLost=true
```

Các dòng kiểm chứng ba nhóm kiến thức:

1. **Độ nhạy tương đối của phép trừ:** `absoluteInputChange` và `absoluteOutputChange` bằng nhau, nhưng `relativeOutputChange` gần `0.001`, còn `relativeAmplificationRounded` vượt `10^12`. Đây là bài toán nhạy dù phép trừ trên các giá trị biểu diễn được là chính xác.
2. **Hàm gần điểm kỳ dị:** `nearPoleOriginal` và `nearPoleChanged` khác nhau sau một nhiễu rất nhỏ ở `x`.
3. **Thuật toán có/không ổn định:** `directCancellation=0.0` so với `stableReformulation=5.0E-9`; `naiveHypotenuseInfinite=true` trong khi `hypotFinite=true`.

Dòng `inputIncrementLost=true` thể hiện sự thật bổ sung: ở `2^53`, `double` không còn biểu diễn được mọi số nguyên kế tiếp, nên `2^53 + 1.0` làm tròn về `2^53`. Nếu một chênh lệch **đã mất khi hình thành dữ liệu đầu vào**, thuật toán phía sau không có cách nào suy ra chính xác nó từ giá trị `double` ấy.

## 10. Độ chính xác biểu diễn khác điều kiện bài toán

`float` có khoảng 24 bit significand hiệu dụng, `double` có khoảng 53 bit; mọi phép toán được biểu diễn trên lưới giá trị hữu hạn với khoảng cách phụ thuộc độ lớn. Công cụ `Math.ulp(x)` cho biết bước biểu diễn liên quan tới `x`, còn `Math.nextUp(x)` và `Math.nextDown(x)` giúp xem các giá trị kề nhau.

Ví dụ:

```java
double limit = 0x1.0p53; // 2^53.
boolean lost = (limit + 1.0 == limit); // true.
double step = Math.ulp(limit);        // 2.0.
```

Dữ liệu đo/chuyển đổi có thể bị làm tròn khi tạo ra `double`, khiến `x̃` khác giá trị lý tưởng `x`. **Conditioning** mô tả tác động của sự khác biệt đó lên câu trả lời toán học, còn **ULP và quy tắc floating-point** mô tả một nguồn sai khác phổ biến trong máy tính.

Nếu một bài toán gần điểm kỳ dị có `κ_rel` rất lớn, sai số tương đối của đầu vào cỡ vài ULP vẫn có thể làm đầu ra đổi đáng kể. Nhưng chỉ nhìn ULP không đủ xác định chất lượng dữ liệu: sai số cảm biến, khuyết dữ liệu, mô hình hóa hoặc nhập liệu sai thường lớn hơn sai số làm tròn máy nhiều bậc.

## 11. Chọn thang đo và đơn vị trước khi báo cáo bài toán “nhạy”

Tính điều kiện tương đối có thể thay đổi khi chọn đầu vào hoặc thang đo. Ví dụ `f(x)=x-1` gần `x=1` rất nhạy về **sai số tương đối của đầu ra** vì `f(x)` gần zero. Nhưng độ nhạy **tuyệt đối** `|f'(x)|=1` vẫn không lớn: đầu vào tăng bao nhiêu thì đầu ra tăng bấy nhiêu.

Nếu nghiệp vụ quan tâm **sai số tuyệt đối không quá `10^-9`**, việc đầu ra nhỏ bị sai tỷ lệ 50% không nhất thiết gây hậu quả. Ngược lại, nếu hệ thống dùng **tỷ lệ tăng trưởng**, độ nhạy tương đối lớn có thể là vấn đề nghiêm trọng.

Khi đo nhiễu, xác định:

- Đầu vào nào thay đổi: một tham số, nhiều tham số hay tất cả?
- Dùng chuẩn nào cho vector đầu vào (ví dụ chuẩn vô cùng `L∞` hoặc Euclid `L2`)?
- Nhiễu là tuyệt đối, tương đối, hay được mô tả bằng khoảng tin cậy từ dữ liệu đo?
- Đầu ra yêu cầu **số chữ số có nghĩa**, sai số tuyệt đối, sai số tương đối hay giới hạn nghiệp vụ?
- Có điểm `f(x)=0`, `x=0`, điểm kỳ dị hoặc bất liên tục làm công thức tương đối trở nên vô nghĩa không?

Với bài toán nhiều biến, **Jacobian** là phiên bản tổng quát của đạo hàm; độ nhạy phụ thuộc hướng nhiễu và chuẩn được chọn. Trong hệ tuyến tính `Ax=b`, số điều kiện ma trận `κ(A)` cho biết độ nhạy của nghiệm đối với nhiễu dữ liệu theo một chuẩn cụ thể. Không nên dùng nguyên công thức một biến `|x f'/f|` cho mọi hệ phương trình nhiều chiều.

## 12. Gắn conditioning với bài toán dữ liệu thực tế

**Tình huống A — hiệu giữa hai phép đo lớn.** Ví dụ đo hai khối lượng gần `1000 kg` rồi trừ để tìm phần chênh `0.001 kg`. Nếu mỗi phép đo có độ bất định `±0.01 kg`, thì độ bất định của hiệu có thể lớn hơn chính kết quả cần tìm. Dùng `BigDecimal` để trừ chính xác các số thập phân đã ghi **không thể phục hồi độ chính xác đo đạc ban đầu**. Cần cảm biến/qui trình đo tốt hơn hoặc đo trực tiếp đại lượng chênh lệch.

**Tình huống B — chia cho một độ lệch gần zero.** Ví dụ tính chỉ tiêu `1/(p - p0)` khi `p` gần `p0`. Một sai số rất nhỏ của cảm biến `p` sẽ làm chỉ tiêu thay đổi mạnh. Cần xác định miền hợp lệ, đặt ngưỡng khoảng cách tới `p0`, tính khoảng đầu ra tương ứng với bất định đầu vào hoặc đổi mô hình nếu gần điểm kỳ dị không có ý nghĩa nghiệp vụ.

**Tình huống C — tính toán hình học lớn.** Độ dài hai cạnh `1e200` vẫn có thể cho đường chéo hữu hạn, nhưng công thức dùng `a*a+b*b` ở `double` gây overflow. `Math.hypot(a,b)` xử lý tốt hơn mà không cần giả sử dữ liệu gốc phải bớt chính xác.

**Tình huống D — tính chênh của hai căn lớn.** Trực tiếp `sqrt(x+1)-sqrt(x)` có thể cho 0 dù đáp án dương. Biến đổi thành `1/(sqrt(x+1)+sqrt(x))` là sửa **thuật toán**, không phải giảm độ nhạy vốn có của hàm.

## 13. Cách kiểm thử độ nhạy một cách có hệ thống trong Java

Để đánh giá một hàm số trong ứng dụng, nên kết hợp:

1. **Tìm miền và điểm khó:** mẫu số gần zero, căn của số gần biên, hiệu hai đại lượng gần nhau, dữ liệu khác bậc độ lớn, điều kiện cực trị.
2. **Ước lượng condition number** khi có đạo hàm hoặc mô hình toán học phù hợp; phân biệt tuyệt đối/tương đối và tránh chia cho zero.
3. **Tạo perturbation có kiểm soát** cho đầu vào. Có thể dùng `Math.nextUp(x)`/`Math.nextDown(x)` để thay một bước biểu diễn, hoặc nhiễu theo sai số đo thực tế.
4. **So hai nguồn sai số:** chạy thuật toán trên các đầu vào hơi khác nhau, rồi so với phương pháp tham chiếu có độ chính xác cao hơn hoặc công thức giải tích khi khả thi.
5. **Thử thêm các giá trị biên:** gần zero, Infinity, NaN, subnormal, giá trị rất lớn, `Double.MAX_VALUE`, vùng đầu vào gây cancellation.
6. **Thử tính chất (properties):** đơn điệu nếu mô hình phải đơn điệu, giá trị không âm nếu đại lượng không âm, giới hạn vật lý, khả năng kiểm tra ngược từ nghiệm về dữ liệu.
7. **Ghi rõ thang sai số mong muốn** trong test, thay vì đòi `double` bằng đúng bit với đáp án thập phân lý tưởng trong mọi tình huống.

Một số phép tính có thể dùng `BigDecimal` với `MathContext` đủ chính xác để tạo giá trị tham chiếu, nhưng **`BigDecimal` không hỗ trợ sẵn mọi hàm số học**, và nó không tự giải quyết mô hình ill-conditioned. Với biểu thức cần các hàm siêu việt, tham chiếu có thể cần thư viện số học độ chính xác cao hoặc biến đổi giải tích được kiểm chứng.

## 14. Sai số forward/backward: hiểu đúng một kết quả khác nhau

Giả sử mô hình lý tưởng có `f(x)`, đầu vào lưu trong máy là `x̃`, kết quả máy là `ŷ`. Phân tích nên hỏi từng câu:

| Câu hỏi | Đang nói về |
| --- | --- |
| `x̃` khác `x` bao nhiêu? | Sai số dữ liệu/biểu diễn |
| `f(x̃)` khác `f(x)` bao nhiêu? | Độ nhạy của **bài toán** |
| `ŷ` khác `f(x̃)` bao nhiêu? | Sai số **thuật toán** tại đầu vào đã lưu |
| `ŷ` có bằng `f(x+Δx)` với `Δx` nhỏ không? | Góc nhìn **backward error** |
| Cả hệ thống có đạt yêu cầu độ chính xác không? | Kết hợp mô hình, dữ liệu, thuật toán và điều kiện |

Trong ví dụ `a = 1 + 2^-40`, phép trừ gần nhau **không phải thủ phạm chính**: cả giá trị gốc và giá trị nhiễu đều có thể lưu và trừ chính xác. Sự khuếch đại tương đối là thuộc tính của việc lấy **hiệu rất nhỏ giữa hai giá trị cỡ 1**.

Ngược lại, trong ví dụ `sqrt(x+1)-sqrt(x)`, việc lựa chọn công thức trực tiếp tạo ra mất chữ số có nghĩa khi các trung gian bị làm tròn. Chuyển sang dạng nghịch đảo giúp giảm sai số tính toán; đó là cải thiện thuật toán, không phải tái định nghĩa đáp án toán học.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách tiếp cận đúng |
| --- | --- | --- |
| Có kết quả sai lớn thì chắc chắn do Java `double` triển khai sai | Bài toán có thể có condition number rất lớn | Phân tích độ nhạy toán học trước |
| Thuật toán ổn định sẽ luôn cho đáp án gần `f(x)` | Dữ liệu `x̃` có thể đã khác `x`; bài toán nhạy | Phân biệt sai số dữ liệu với sai số thuật toán |
| Hai số gần nhau thì phép trừ luôn được CPU tính sai | Với các số floating-point đủ gần, phép trừ đôi khi chính xác | Xét nhiễu đầu vào và thuật toán riêng |
| Sai số tương đối lớn thì sai số tuyệt đối cũng lớn | Đầu ra rất nhỏ dễ có sai số tương đối lớn | Nêu chuẩn lỗi phù hợp miền đo |
| Tăng từ `float` lên `double` luôn chữa được điều kiện xấu | Tăng độ chính xác không đổi bản chất hàm toán học | Phân tích condition number và chất lượng dữ liệu |
| `BigDecimal` sửa được nhiễu cảm biến | Nó chỉ tăng kiểm soát biểu diễn/tính toán | Cải thiện đo đạc hoặc mô hình nếu cần |
| `sqrt(a*a+b*b)` an toàn khi kết quả cuối hữu hạn | Trung gian `a*a` có thể overflow | Dùng `Math.hypot(a,b)` |
| `sqrt(x+1)-sqrt(x)` luôn an toàn vì toán học dương | Hai căn được làm tròn gần bằng nhau | Dùng biến đổi đại số ổn định |
| Số điều kiện một biến áp dụng y hệt cho nhiều biến | Độ nhạy nhiều biến phụ thuộc chuẩn và hướng nhiễu | Xem Jacobian và condition number phù hợp |
| So sánh `double` bằng `==` đủ để đánh giá tính đúng | Kết quả bị làm tròn và có thể rất gần nhau | Dùng tiêu chí sai số có thiết kế và test biên |

## 16. Câu hỏi tự kiểm tra

1. **Conditioning là gì?** Là tính nhạy của đáp án toán học đối với thay đổi nhỏ ở đầu vào, tại miền/điểm và chuẩn đo đã xác định.
2. **Numerical stability khác conditioning ở điểm nào?** Stability nói về sai số do **thuật toán tính**, conditioning nói về **bản thân bài toán**.
3. **Với `f(x)=x-1`, tại `x` rất gần 1, tại sao sai số tương đối đầu ra tăng mạnh?** Vì `f(x)` rất nhỏ, trong khi nhiễu tuyệt đối của `x` vẫn truyền vào hiệu; số điều kiện tương đối `|x/(x-1)|` lớn.
4. **Phép trừ hai số gần nhau có nhất thiết làm tròn sai không?** Không. Nó có thể chính xác trên hai số đã lưu, nhưng kết quả rất nhạy theo **sai số tương đối của đầu vào**.
5. **Với `f(x)=1/(x-1)`, chuyện gì xảy ra khi `x` gần 1?** Đạo hàm và số điều kiện tương đối có thể rất lớn; một sai số nhỏ của `x` có thể làm `f(x)` thay đổi mạnh.
6. **Vì sao `sqrt(1e16 + 1) - sqrt(1e16)` trong `double` có thể bằng zero?** Vì các giá trị trung gian bị làm tròn thành hai số như nhau; công thức trực tiếp gây cancellation.
7. **Biến đổi ổn định hơn của `sqrt(x+1)-sqrt(x)` là gì với `x≥0`?** `1/(sqrt(x+1)+sqrt(x))`.
8. **Vì sao `Math.hypot(1e200,1e200)` có thể hữu hạn trong khi `Math.sqrt(a*a+a*a)` là Infinity?** `a*a` đã overflow trước khi lấy căn; `Math.hypot` tránh trung gian không cần thiết đó.
9. **Nếu một số đo có sai số vật lý lớn, đổi `double` sang `BigDecimal` có phục hồi giá trị chính xác không?** Không. Độ chính xác biểu diễn không phục hồi thông tin không tồn tại trong phép đo.
10. **Khi nào dùng sai số tuyệt đối thay vì sai số tương đối?** Khi đầu ra có thể bằng/gần zero hoặc nghiệp vụ quy định dung sai tuyệt đối cụ thể.

**Ghi nhớ:** sai số đầu vào có thể bị **khuếch đại do điều kiện bài toán**, kể cả khi thuật toán hoàn toàn đúng trên các giá trị đã lưu. Hãy đo cả **sai số tuyệt đối và tương đối**, phân tích số điều kiện gần những điểm nhạy, phân biệt lỗi dữ liệu với lỗi thuật toán, rồi lựa chọn công thức số ổn định (`Math.hypot`, biến đổi tránh cancellation, kiểm tra miền) và độ chính xác phù hợp với yêu cầu.
