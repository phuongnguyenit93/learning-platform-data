# Math.nextAfter và giá trị biểu diễn liền kề

## 1. Khái niệm: số thực trong chương trình không tạo thành một trục liên tục

Về toán học, giữa hai số thực khác nhau luôn có thêm số thực khác. Nhưng một kiểu hữu hạn như `float` hoặc `double` chỉ biểu diễn được một tập hữu hạn các giá trị.

Do đó, với một giá trị máy cụ thể, có thể hỏi:

> Số biểu diễn được nằm sát nó nhất ở phía lớn hơn hoặc nhỏ hơn là số nào?

`Math.nextAfter` trả lời câu hỏi này bằng cách chọn giá trị liền kề theo hướng được chỉ định.

Mô hình đơn giản:

```text
... → giá trị trước → start → giá trị sau → ...

nextAfter(start, hướng nhỏ hơn) → giá trị trước
nextAfter(start, hướng lớn hơn) → giá trị sau
```

Đây là **một bước trên tập số của kiểu dữ liệu**, không phải cộng một lượng thập phân cố định, không phải làm tròn tới một số chữ số sau dấu phẩy và không phải đi thẳng tới giá trị đích.

Hai overload `nextAfter` có từ Java 6 và vẫn được sử dụng trên Java hiện đại. Bài dùng ví dụ JDK 17+ và đối chiếu hợp đồng hiện hành.

## 2. Hai overload: kiểu của start quyết định tập số kết quả

```java
public static double nextAfter(double start, double direction)
public static float nextAfter(float start, double direction)
```

Điểm dễ bỏ sót là overload thứ hai nhận `start` kiểu float nhưng `direction` vẫn là double.

| Lời gọi | Kiểu kết quả | Giá trị liền kề được xét trong tập nào? |
| --- | --- | --- |
| `Math.nextAfter(1.0, 2.0)` | double | Tập giá trị double |
| `Math.nextAfter(1.0f, 2.0)` | float | Tập giá trị float |

Kết quả float có bước liền kề thường lớn hơn kết quả double quanh cùng giá trị, do độ chính xác của hai định dạng khác nhau.

Không nên đổi kiểu start một cách vô tình:

```java
float x = 1.0f;

float a = Math.nextAfter(x, Double.POSITIVE_INFINITY);
double b = Math.nextAfter((double) x, Double.POSITIVE_INFINITY);
```

Đây là đoạn minh họa, không phải chương trình độc lập. a là float kế tiếp; b là double kế tiếp sau giá trị double được chuyển từ x. Chúng không cùng một số.

## 3. direction chọn phía, không chọn độ dài bước

Với các giá trị hữu hạn thông thường, không phải NaN:

- Nếu direction lớn hơn start, chọn số liền kề về phía lớn hơn.
- Nếu direction nhỏ hơn start, chọn số liền kề về phía nhỏ hơn.
- Nếu hai đối số so sánh bằng nhau, trả direction; với overload float là giá trị float tương ứng.

Ví dụ:

```java
Math.nextAfter(1.0, 2.0)
Math.nextAfter(1.0, 100.0)
```

Hai lời gọi cho cùng kết quả vì cả 2 và 100 đều nằm về phía lớn hơn 1. Nó không trả 2 hoặc 100 chỉ vì các số đó là tham số thứ hai.

Thường dùng vô cực để biểu đạt hướng rõ ràng:

```java
double higher = Math.nextAfter(x, Double.POSITIVE_INFINITY);
double lower = Math.nextAfter(x, Double.NEGATIVE_INFINITY);
```

Còn nếu dùng:

```java
Math.nextAfter(x, 0.0)
```

thì đang đi **về phía 0**, không phải luôn đi xuống theo giá trị số. Với x dương, kết quả nhỏ hơn; với x âm, kết quả lớn hơn, trừ những trường hợp đặc biệt cần xét theo hợp đồng.

Hướng được quyết định bằng tương quan giữa hai giá trị, không chỉ bằng dấu của direction.

## 4. Vì sao không dùng một epsilon cố định?

Một cách thử tạo giá trị “nhỉnh hơn” là:

```java
double y = x + 1.0e-12;
```

Nhưng lượng này không thích ứng với độ lớn của x:

- Ở một vùng, nó có thể đi qua nhiều giá trị biểu diễn được.
- Ở vùng có x lớn, nó có thể quá nhỏ để làm thay đổi kết quả sau làm tròn.
- Ở một vùng khác, nó không đại diện đúng yêu cầu sai số của bài toán.

Ví dụ trong chương trình kiểm chứng:

```text
1.0e20 + 1.0e-12 > 1.0e20 → false
```

Không phải phép cộng bị bỏ qua tùy tiện. Kết quả chính xác của phép cộng quá gần x so với khoảng cách biểu diễn ở vùng đó, nên được làm tròn về cùng giá trị.

`nextAfter` dành cho câu hỏi **giá trị máy liền kề**, còn epsilon dùng trong một quy tắc sai số cần được thiết kế theo bài toán. Hai công cụ không thay thế nhau cho mọi mục tiêu.

## 5. Khoảng cách liền kề không đồng đều

Quanh 1.0 kiểu double:

```text
Số ngay dưới: 1 - 2^-53
Điểm giữa:   1
Số ngay trên:1 + 2^-52
```

Khoảng trên lớn gấp đôi khoảng dưới. Đây là ranh giới giữa các vùng có số mũ khác nhau của định dạng nhị phân.

Vì vậy, không nên viết một quy tắc tổng quát rằng:

```text
nextAfter(x, hướng bất kỳ) luôn bằng x ± cùng một lượng cố định
```

Khoảng cách giữa các số chuẩn hóa thay đổi theo vùng độ lớn; trong vùng subnormal, cấu trúc khoảng cách có đặc điểm khác.

### Liên hệ với ulp

`Math.ulp(x)` mô tả kích thước một đơn vị ở vị trí có trọng số thấp nhất theo hợp đồng của API. Nó hữu ích để hiểu độ phân giải quanh một giá trị.

Nhưng tại ranh giới như 1.0:

```text
Math.ulp(1.0) = 2^-52
Khoảng từ 1.0 tới số ngay dưới = 2^-53
```

Do đó, `x - Math.ulp(x)` không luôn là số liền kề phía dưới x. Nếu mục tiêu là đúng hàng xóm theo hướng, dùng API nextAfter/nextUp/nextDown phù hợp.

Không cần tự sửa bit hoặc tự suy ra quy tắc số mũ để làm công việc mà API đã quy định.

## 6. Các trường hợp đặc biệt phải biết

### 6.1. Hai đối số bằng nhau

`Math.nextAfter(1.0, 1.0)` trả 1.0. Không có quy tắc bắt buộc phải dịch chuyển khi đã ở đúng giá trị direction.

Trường hợp hai số 0 có dấu làm quy tắc này đặc biệt quan trọng.

### 6.2. +0.0 và -0.0

Java có hai số 0 dấu khác nhau. Chúng so sánh bằng nhau với toán tử `==`, nhưng có biểu diễn và một số tác động tính toán khác nhau.

Vì vậy:

| Lời gọi double | Kết quả |
| --- | --- |
| `nextAfter(+0.0, -0.0)` | -0.0 |
| `nextAfter(-0.0, +0.0)` | +0.0 |
| `nextAfter(0.0, 1.0)` | Double.MIN_VALUE |
| `nextAfter(0.0, -1.0)` | -Double.MIN_VALUE |

Hai dòng đầu trả hướng vì các đối số so sánh bằng nhau. Hai dòng sau bước ra khỏi 0 theo phía được chọn.

Một phép kiểm chỉ dùng `result == 0.0` sẽ không xác minh được dấu zero. Có thể kiểm biểu diễn bit hoặc dùng biểu diễn hex như chương trình dưới đây.

### 6.3. MIN_VALUE không phải số âm nhỏ nhất

`Double.MIN_VALUE` là số dương khác 0 nhỏ nhất kiểu double; nó thuộc vùng subnormal. Tương tự với Float.MIN_VALUE.

Khi bước từ giá trị này về phía có độ lớn nhỏ hơn:

```text
nextAfter(+Double.MIN_VALUE, 0.0) → +0.0
nextAfter(-Double.MIN_VALUE, 0.0) → -0.0
```

Dấu zero được giữ theo start trong trường hợp này.

Không nhầm MIN_VALUE với MIN_NORMAL, là số dương chuẩn hóa nhỏ nhất. Tập double vẫn còn các số subnormal dương nhỏ hơn MIN_NORMAL trước khi về 0.

### 6.4. Vô cực và giới hạn hữu hạn

| Tình huống | Kết quả |
| --- | --- |
| Từ +MAX_VALUE ra phía lớn hơn | +Infinity |
| Từ -MAX_VALUE ra phía nhỏ hơn | -Infinity |
| Từ +Infinity về phía hữu hạn | +MAX_VALUE |
| Từ -Infinity về phía hữu hạn | -MAX_VALUE |
| Từ +Infinity hướng +Infinity | +Infinity |
| Từ -Infinity hướng -Infinity | -Infinity |

Những kết quả này được trả như giá trị số thực đặc biệt, không phải một `ArithmeticException` vì “đã bước quá giới hạn”.

### 6.5. NaN

Nếu một trong hai đối số là NaN, kết quả là NaN.

Kiểm bằng:

```java
Double.isNaN(result)
```

không kiểm bằng `result == Double.NaN`, vì NaN không bằng chính nó theo toán tử số học `==`.

Không coi NaN như một điểm nằm trước hoặc sau các số trong quy tắc hướng của nextAfter.

## 7. Điểm riêng của overload float: có thể bước qua direction

Xét:

```java
float start = 1.0f;
double direction = 1.0 + 0x1.0p-40;
float result = Math.nextAfter(start, direction);
```

Direction là một double lớn hơn 1 nhưng rất gần 1. Khi ép direction về float, nó được làm tròn về 1.0f.

Tuy nhiên, overload không yêu cầu ép direction sang float trước khi xét hướng. Nó vẫn nhận ra hướng lớn hơn start và trả số float liền kề phía trên.

Vì không có số float nằm giữa start và direction, kết quả có thể **lớn hơn direction**.

Do đó, câu “mỗi bước tiến về direction và không bao giờ đi quá direction” không đúng một cách tổng quát cho overload float nhận hướng double.

Điều API bảo đảm là chọn hàng xóm của **start trong tập float** theo phía của direction. Nó không bảo đảm mọi direction double đều là đích mà float có thể chạm chính xác.

Nếu direction được tạo bằng một phép tính đã làm tròn về đúng start ngay từ đầu, API không biết “ý định toán học” trước khi làm tròn; nó chỉ thấy hai giá trị đối số thực sự được truyền vào.

## 8. Ví dụ chạy được với biểu diễn hex

Tệp `NextAfterDemo.java`:

```java
public final class NextAfterDemo {
    private static void show(String label, double value) {
        System.out.println(label + "=" + Double.toHexString(value));
    }

    public static void main(String[] args) {
        double up = Math.nextAfter(1.0, Double.POSITIVE_INFINITY);
        double down = Math.nextAfter(1.0, Double.NEGATIVE_INFINITY);
        show("one", 1.0);
        show("up", up);
        show("down", down);
        show("gapUp", up - 1.0);
        show("gapDown", 1.0 - down);
        System.out.println("gapRatio=" + ((up - 1.0) / (1.0 - down)));
        System.out.println("sameDirection="
                + (Math.nextAfter(1.0, 2.0) == Math.nextAfter(1.0, 100.0)));
        System.out.println("fixedEpsilonMoves="
                + (1.0e20 + 1.0e-12 > 1.0e20));

        float floatUp = Math.nextAfter(1.0f, Double.POSITIVE_INFINITY);
        double doubleUp = Math.nextAfter(1.0, Double.POSITIVE_INFINITY);
        System.out.println("floatUp=" + Float.toHexString(floatUp));
        System.out.println("doubleUp=" + Double.toHexString(doubleUp));
        double closeDirection = 1.0 + 0x1.0p-40;
        System.out.println("castDirectionEqualsStart="
                + ((float) closeDirection == 1.0f));
        System.out.println("floatStillMoves="
                + (Math.nextAfter(1.0f, closeDirection) > 1.0f));

        show("zeroTowardPositive", Math.nextAfter(0.0, 1.0));
        show("zeroTowardNegative", Math.nextAfter(0.0, -1.0));
        show("positiveZeroToNegativeZero", Math.nextAfter(+0.0, -0.0));
        show("negativeZeroToPositiveZero", Math.nextAfter(-0.0, +0.0));
        show("positiveMinToZero", Math.nextAfter(Double.MIN_VALUE, 0.0));
        show("negativeMinToZero", Math.nextAfter(-Double.MIN_VALUE, 0.0));
        show("maxToInfinity",
                Math.nextAfter(Double.MAX_VALUE, Double.POSITIVE_INFINITY));
        show("infinityToZero",
                Math.nextAfter(Double.POSITIVE_INFINITY, 0.0));
        System.out.println("nanStart="
                + Double.isNaN(Math.nextAfter(Double.NaN, 0.0)));
        System.out.println("nanDirection="
                + Double.isNaN(Math.nextAfter(1.0, Double.NaN)));

        double limit = 0.3;
        double below = Math.nextAfter(limit, Double.NEGATIVE_INFINITY);
        double above = Math.nextAfter(limit, Double.POSITIVE_INFINITY);
        System.out.println("boundary="
                + (below <= limit) + "," + (limit <= limit)
                + "," + (above <= limit));
    }
}
```

Biên dịch và chạy với JDK 17+:

```powershell
javac --release 17 -d out NextAfterDemo.java
java -cp out NextAfterDemo
```

Chỉ chạy sau khi biên dịch thành công.

Stdout:

```text
one=0x1.0p0
up=0x1.0000000000001p0
down=0x1.fffffffffffffp-1
gapUp=0x1.0p-52
gapDown=0x1.0p-53
gapRatio=2.0
sameDirection=true
fixedEpsilonMoves=false
floatUp=0x1.000002p0
doubleUp=0x1.0000000000001p0
castDirectionEqualsStart=true
floatStillMoves=true
zeroTowardPositive=0x0.0000000000001p-1022
zeroTowardNegative=-0x0.0000000000001p-1022
positiveZeroToNegativeZero=-0x0.0p0
negativeZeroToPositiveZero=0x0.0p0
positiveMinToZero=0x0.0p0
negativeMinToZero=-0x0.0p0
maxToInfinity=Infinity
infinityToZero=0x1.fffffffffffffp1023
nanStart=true
nanDirection=true
boundary=true,true,false
```

Ví dụ đã được biên dịch với `--release 17` và chạy kiểm tra trên JDK 24.0.2.

### Cách đọc dạng hex

Trong chuỗi `0x1.0p-52`:

- `0x` biểu thị phần chữ số ở hệ 16.
- `p-52` biểu thị nhân với 2 mũ -52, không phải 10 mũ -52.

Dạng này giúp nhìn trực tiếp cấu trúc nhị phân và tránh việc định dạng thập phân với quá ít chữ số làm hai giá trị liền kề trông như cùng một số.

Các dòng up/down cho thấy hai hàng xóm của 1.0. Các dòng gap cho thấy độ dài hai bước. Các dòng zero cho thấy dấu 0 và bước subnormal, còn NaN được kiểm bằng isNaN.

## 9. Ứng dụng: tạo dữ liệu kiểm thử sát ngưỡng

Giả sử mã ứng dụng dùng điều kiện:

```java
value <= limit
```

Một bộ ba kiểm thử hữu ích là:

```java
double below = Math.nextAfter(limit, Double.NEGATIVE_INFINITY);
double equal = limit;
double above = Math.nextAfter(limit, Double.POSITIVE_INFINITY);
```

Với limit hữu hạn thông thường, ta kiểm được:

| Đầu vào | Kỳ vọng cho `value <= limit` |
| --- | --- |
| below | true |
| equal | true |
| above | false |

Điều này giúp phát hiện lỗi dùng `<` thay cho `<=`, xử lý sai giá trị ngay bên ngưỡng hoặc làm tròn trung gian ngoài ý muốn.

Trong chương trình, limit là giá trị double được literal `0.3` biểu diễn. Bộ ba kiểm tra ranh giới quanh **giá trị double đó**, không biến nó thành số thập phân 0.3 chính xác theo toán học.

Nếu yêu cầu nghiệp vụ định nghĩa ngưỡng theo một đơn vị thập phân chính xác, cần chọn mô hình biểu diễn và quy tắc tính phù hợp. Di chuyển một bước double không tự giải quyết yêu cầu đó.

### Không tự nới ngưỡng để che lỗi

Có thể tạo một ngưỡng nhỉnh hơn bằng nextAfter, nhưng chỉ làm vậy khi đặc tả thật sự yêu cầu nới đúng một bước biểu diễn.

Không dùng nó như một cách “sửa” chung khi hai phép tính số thực không bằng nhau. Sai số có thể lớn hơn một bước, phụ thuộc thuật toán hoặc xuất phát từ điều kiện không phù hợp. Cần phân tích nguyên nhân và tiêu chí chấp nhận.

### Tạo điểm nằm sát phía trong một miền

Trong một số thử nghiệm số học, muốn tạo giá trị máy ngay bên trong miền có biên hữu hạn. Có thể dùng hướng về phía trong, ví dụ điểm dưới 1.0 nhưng gần nó nhất bằng `nextAfter(1.0, NEGATIVE_INFINITY)`.

Tuy nhiên, “chỉ dịch một bước để nằm trong miền” không tự bảo đảm một thuật toán số học ổn định. Đây là công cụ tạo dữ liệu/cận theo số máy, không phải một chứng minh sai số của toàn bộ phép tính.

## 10. Phân biệt với các API gần giống

| API/cách làm | Mục đích |
| --- | --- |
| `nextAfter(x, direction)` | Chọn hàng xóm theo phía của một giá trị chỉ hướng |
| `nextUp(x)` | Chọn hàng xóm theo phía dương vô cực |
| `nextDown(x)` | Chọn hàng xóm theo phía âm vô cực |
| `ulp(x)` | Tìm kích thước ulp theo định nghĩa của API |
| `floor/ceil/rint` | Làm tròn về những giá trị nguyên theo quy tắc riêng |
| `x + epsilon` | Thực hiện phép cộng với epsilon đã chọn, không bảo đảm hàng xóm |
| Làm tròn thập phân | Áp quy tắc số chữ số/đơn vị thập phân, là nhu cầu khác |

`nextUp` có từ Java 6, còn `nextDown` được bổ sung từ Java 8. Các API này đều dùng được trên JDK 17+; không gán mốc của cả nhóm theo một thành viên.

Nếu chỉ muốn đi một phía cố định, nextUp/nextDown giúp thể hiện ý định ngắn hơn. Nếu phía phụ thuộc một giá trị mục tiêu, nextAfter biểu đạt trực tiếp hơn.

Không suy từ dòng mô tả tổng quan của Math rằng mọi phương thức có sai số xấp xỉ như nhau. nextAfter có hợp đồng chọn giá trị biểu diễn liền kề cụ thể; cần đọc hợp đồng của chính phương thức.

## 11. Cách kiểm thử và những lỗi thường gặp

### Kiểm hàng xóm bằng expected độc lập khi phù hợp

Quanh 1.0, có thể dùng literal nhị phân hoặc biểu diễn hex đã biết làm expected. Nếu chỉ dùng nextAfter để tạo expected rồi lại so với một hàm gọi nextAfter tương tự, test có thể không kiểm được giả định của chính nó.

Khi kiểm một điều kiện nghiệp vụ, dùng nextAfter tạo đầu vào sát biên, còn expected nên đến từ đặc tả điều kiện.

### Chú ý dấu zero và NaN

- Dùng kiểm bit hoặc biểu diễn phù hợp để phân biệt +0.0/-0.0 khi cần.
- Dùng isNaN cho NaN.
- Không dùng một assertion khoảng sai số lớn tới mức nó coi hai hàng xóm là “đủ giống” khi mục tiêu đang là phân biệt chính các hàng xóm.

### Không tự tăng bit một cách ngây thơ

Tăng một bit pattern bằng 1 không đồng nghĩa luôn tăng giá trị số: số âm, zero và NaN có cấu trúc riêng. API nextAfter tồn tại để diễn đạt đúng thao tác theo giá trị mà không bắt người gọi tự làm mọi trường hợp.

### Không biến nextAfter thành bước lặp thông thường

Giữa hai giá trị gần nhau theo đơn vị con người vẫn có thể có rất nhiều số máy. Lặp qua từng hàng xóm có thể cực kỳ chậm.

Ngoài ra:

- Nếu start và direction so sánh bằng nhau, kết quả không tiến thêm.
- Tại vô cực cùng hướng, nó không tiến nữa.
- NaN không thể kiểm kết thúc bằng phép so sánh bằng thông thường.
- Với hướng double không biểu diễn được bằng float, vòng lặp float yêu cầu bằng đích có thể không kết thúc như mong muốn.

Nếu thật sự duyệt một đoạn số biểu diễn, cần giới hạn số bước và điều kiện dừng được thiết kế cho kiểu/miền đang dùng.

### Không nhầm “liền kề” với “khác nhau nhìn thấy khi in”

In bằng vài chữ số thập phân có thể làm hai số khác nhau hiện giống nhau. Khi cần kiểm cấu trúc số máy, dùng đủ chữ số, dạng hex hoặc biểu diễn bit.

## 12. Bài tập tự kiểm chứng

1. Thay start 1.0 bằng 2.0 và tính khoảng về phía trên/dưới bằng nextAfter. Giải thích vai trò ranh giới số mũ, thay vì chỉ ghi hai số thập phân.
2. Với start âm, so sánh hướng về 0 và hướng âm vô cực. Hướng nào làm giá trị lớn hơn? Hướng nào làm độ lớn tăng?
3. Kiểm `nextAfter(+0.0,-0.0)` bằng `==0.0` rồi bằng biểu diễn bit. Phép nào xác minh được dấu zero?
4. Tạo direction double lớn hơn 1.0 nhưng chưa tới float kế tiếp. Chứng minh kết quả float có thể vượt direction.
5. Dùng bộ ba below/equal/above để kiểm một hàm chấp nhận khoảng đóng `[a,b]`, với a và b là các giá trị hữu hạn thông thường. Tách rõ ca NaN/vô cực theo hợp đồng hàm.
6. Giải thích vì sao `x-Math.ulp(x)` tại x=1.0 không phải cách đúng để lấy số double liền kề phía dưới.
7. Nêu một trường hợp cần sai số nghiệp vụ thay vì đúng một bước số máy. Giải thích vì sao nextAfter chưa đủ để xác định sai số đó.

Điều cần nắm là **nextAfter chọn đúng một giá trị biểu diễn kế bên theo hướng, còn độ dài bước phụ thuộc kiểu và vị trí trên tập số**. Nó đặc biệt hữu ích để khám phá biểu diễn nhị phân và tạo kiểm thử sát biên khi dùng đúng hợp đồng.

## Tài liệu đối chiếu

- [Math.nextAfter(double, double)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html#nextAfter(double,double)): quy tắc chọn hàng xóm và các trường hợp đặc biệt.
- [Math.nextAfter(float, double)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html#nextAfter(float,double)): kiểu hướng và tập kết quả float.
- [Double](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Double.html): zero có dấu, NaN, giới hạn và biểu diễn hex.
- [Float](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Float.html): độ chính xác và các giới hạn của float.
