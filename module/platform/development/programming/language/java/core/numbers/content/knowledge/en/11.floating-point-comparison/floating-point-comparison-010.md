# Khi nào cần giới hạn theo ULP khi so sánh số thực trong Java?

## 1. Vì sao một sai số tuyệt đối cố định không luôn đủ?

Phép toán **float** và **double** sử dụng số dấu phẩy động nhị phân hữu hạn độ chính xác. Kết quả trung gian và kết quả cuối có thể phải làm tròn. Vì vậy, hai phép tính về mặt toán học có cùng đáp số vẫn có thể trả về hai mẫu bit khác nhau.

Ví dụ:

~~~java
double computed = 0.1 + 0.2;
double expected = 0.3;

System.out.println(computed == expected); // false
~~~

Số **0.1**, **0.2** và **0.3** không có biểu diễn nhị phân hữu hạn chính xác trong kiểu double. Ở đây hai kết quả nằm ở **hai giá trị double liên tiếp**. Điều đó gợi ý một cách đo sai khác theo bước của chính định dạng số: **ULP**.

Tuy nhiên, việc hai giá trị cách nhau ít ULP **không tự chứng minh** kết quả đủ chính xác cho nghiệp vụ. Một ULP phụ thuộc vào độ lớn của giá trị: tại số rất lớn, khoảng cách một ULP có thể rất lớn theo đơn vị vật lý; gần zero, một ULP có thể tương ứng với tỷ lệ sai khác rất lớn.

Mục tiêu của bài là xác định **khi nào giới hạn sai số theo ULP hợp lý**, khi nào nên dùng sai số tuyệt đối/tương đối, và cách viết kiểm tra Java tránh kết luận sai.

## 2. ULP là gì?

**ULP** viết tắt của *unit in the last place*. Với một giá trị floating-point hữu hạn x, **Math.ulp(x)** trong Java trả về kích thước một ULP tại x: khoảng cách dương đến giá trị biểu diễn được kế tiếp theo hướng **tăng độ lớn**. Điều này phụ thuộc vào độ rộng kiểu (**float** hay **double**) và vị trí của x trên trục số.

Các phương thức liên quan:

- **Math.ulp(double)** trả về double; **Math.ulp(float)** trả về float.
- **Math.nextUp(x)** tìm số floating-point sát bên theo hướng dương vô cùng.
- **Math.nextDown(x)** tìm số sát bên theo hướng âm vô cùng.
- **Math.nextAfter(start, direction)** tìm số sát bên theo hướng chỉ định.
- **Double.toHexString(x)** và **Float.toHexString(x)** hiển thị significand và số mũ nhị phân để quan sát ranh giới.

Một số mốc quan trọng:

| Giá trị | ULP trong Java | Ý nghĩa |
| --- | --- | --- |
| **Math.ulp(1.0)** | **2^−52** | Bước phía trên 1 của double |
| **Math.ulp(1.0f)** | **2^−23** | Bước phía trên 1 của float |
| **Math.ulp(0.0)** | **Double.MIN_VALUE = 2^−1074** | Bước subnormal nhỏ nhất của double |
| **Math.ulp(0.0f)** | **Float.MIN_VALUE = 2^−149** | Bước subnormal nhỏ nhất của float |
| **Math.ulp(Double.MAX_VALUE)** | **2^971** | Kích thước ULP tại double hữu hạn lớn nhất |
| **Math.ulp(Double.POSITIVE_INFINITY)** | **Infinity** | Trường hợp đặc biệt; không dùng làm mức dung sai hữu hạn |
| **Math.ulp(Double.NaN)** | **NaN** | Không có khoảng cách số để so sánh |

Trong cùng một đoạn giá trị mà số mũ nhị phân không đổi (*binade*), các giá trị biểu diễn được cách nhau đều; khi chuyển sang đoạn số mũ kế tiếp, bước lưới thay đổi. Các **subnormal** gần zero có khoảng cách tuyệt đối cố định bằng **MIN_VALUE**.

### Bẫy ở đúng lũy thừa của hai

Tại **1.0 = 2^0** của double:

~~~text
Math.nextDown(1.0) = 1.0 - 2^-53
1.0                = 1.0
Math.nextUp(1.0)   = 1.0 + 2^-52

Math.ulp(1.0)      = 2^-52
~~~

Khoảng cách tới giá trị phía dưới **chỉ bằng một nửa** khoảng cách tới giá trị phía trên. Vì vậy, biểu thức **Math.abs(a - b) / Math.ulp(a)** không phải phép đếm số giá trị floating-point nằm giữa a và b trong mọi trường hợp.

Phân biệt hai ý nghĩa thường bị gọi chung là “sai số N ULP”:

1. **Ngưỡng khoảng cách số học:** chấp nhận khi |a − b| không vượt **N × Math.ulp(reference)** hoặc một ULP tại thang đo được chọn. Đây là ngưỡng độ lớn có đơn vị của a/b.
2. **Số bước biểu diễn (representable-value distance):** chấp nhận khi từ một giá trị đến giá trị kia đi qua không quá N lần **nextUp/nextDown** hợp lệ. Đây là số bước nguyên, không luôn bằng tỷ số ở mục 1.

Cần xác định hợp đồng kiểm thử muốn sử dụng nghĩa nào **trước khi chọn thuật toán**.

## 3. Khi nào nên đặt giới hạn ULP?

### Trường hợp phù hợp

Một ngưỡng theo ULP hữu ích khi:

- **Kiểm thử thuật toán số mức thấp:** bạn có giá trị tham chiếu và muốn đo xem kết quả double/float của một triển khai lệch bao nhiêu bước làm tròn so với tham chiếu, đặc biệt khi tiêu chí kiểm thử hoặc tài liệu API mô tả sai số bằng ULP.
- **So sánh kết quả của hai cách tính số học nhị phân:** cả hai tính cùng đại lượng, có cùng đơn vị, cùng độ rộng float/double và dự kiến chỉ sai nhau ít bước biểu diễn.
- **Khảo sát tính chính xác tại một vùng giá trị có độ lớn tương đương:** bạn muốn dung sai co giãn cùng độ phân giải biểu diễn, thay vì gắn cố định một **epsilon = 1e−9** trên mọi thang đo.
- **Đánh giá chất lượng phép làm tròn:** xác định kết quả có cách giá trị tham chiếu đúng hoặc có độ chính xác cao chỉ 0, 1, 2... bước biểu diễn. Phép đếm này có ý nghĩa đặc biệt khi giá trị tham chiếu đã được làm tròn về đúng kiểu đích theo một quy tắc đã biết.

**Điều kiện quan trọng:** trước hết phải biết giới hạn sai số của thuật toán hoặc hợp đồng kiểm thử. Không có giá trị N mặc định đúng cho mọi hàm. “Cho phép 4 ULP” chỉ là một quyết định có cơ sở nếu được chứng minh bởi phân tích sai số, đặc tả API, dữ liệu thực nghiệm hoặc mục tiêu kiểm thử rõ ràng.

### Trường hợp không nên chỉ dựa vào ULP

- **Nghiệp vụ có đơn vị và ngưỡng chấp nhận cụ thể:** ví dụ sai khác nhiệt độ không quá 0.01 °C, vị trí không quá 1 mm, thời gian không quá 1 µs. Ngưỡng tuyệt đối theo đơn vị thực là quan trọng hơn.
- **Sai số tương đối có ý nghĩa:** đo tỷ lệ thay đổi của đại lượng trên nhiều bậc độ lớn. Giới hạn tương đối thường biểu đạt rõ yêu cầu hơn.
- **Miền gần zero:** 0 và **Double.MIN_VALUE** cách đúng một bước biểu diễn nhưng tỷ lệ sai khác so với giá trị khác 0 là 100%. Một ngưỡng “1 ULP” có thể quá dễ dãi nếu nghiệp vụ yêu cầu giá trị phải thực sự khác 0.
- **Thuật toán mất ổn định số hoặc triệt tiêu chữ số (cancellation):** đầu ra có thể cách kết quả chính xác nhiều ULP dù sai số tuyệt đối nhỏ, hoặc ngược lại. ULP không thay cho phân tích độ điều kiện (*conditioning*) của bài toán.
- **So sánh giá trị tiền tệ/định danh/giới hạn pháp lý phải chính xác theo thập phân:** dùng mô hình tiền và quy tắc làm tròn rõ ràng (chẳng hạn BigDecimal đúng cách) thay vì mặc định so sánh double gần nhau.
- **Dùng số thực làm khóa phân vùng, khóa Map, hoặc điều kiện đồng nhất bắt buộc bắc cầu:** quan hệ “gần nhau trong N ULP” không bắc cầu. Nó không nên được nhét tùy tiện vào **equals/hashCode**.

Ví dụ: nếu x và y cách một ULP, y và z cũng cách một ULP, thì x và z có thể cách **hai ULP**. Khi ấy **close(x,y)** và **close(y,z)** có thể cùng true nhưng **close(x,z)** false.

## 4. So sánh tuyệt đối, tương đối và ULP

Ba dạng kiểm tra phục vụ ba kiểu yêu cầu:

| Cách so sánh | Quy tắc thường gặp | Phù hợp với |
| --- | --- | --- |
| **Sai số tuyệt đối** | **abs(a−b) ≤ absTol** | Có ngưỡng thực tế theo đơn vị, nhất là gần zero |
| **Sai số tương đối** | **abs(a−b) ≤ relTol × max(abs(a), abs(b))** | Độ lớn khác nhau, quan tâm tỉ lệ sai số |
| **Kết hợp tuyệt đối/tương đối** | **abs(a−b) ≤ max(absTol, relTol × scale)** | Nhiều bài kiểm thử ứng dụng trên cả giá trị nhỏ và lớn |
| **Ngưỡng ULP theo thang** | **abs(a−b) ≤ N × Math.ulp(scale)** | Dung sai cùng độ phân giải biểu diễn ở vùng scale |
| **Đếm chính xác bước ULP** | **distanceInRepresentableValues(a,b) ≤ N** | Hợp đồng cho phép tối đa N bước float/double |

Dùng **max** thay vì chỉ relative tolerance giúp tránh vấn đề so sánh gần 0 với dung sai tương đối bằng 0. Nhưng **absTol** và **relTol** vẫn phải được chọn theo yêu cầu bài toán; công thức không tự tạo ra hai ngưỡng đúng.

**Lưu ý:** viết phép trừ **a−b** trực tiếp có thể tràn thành **Infinity** với hai số double hữu hạn rất lớn và trái dấu. Với sai số ULP theo số bước, ta có thể tránh phép trừ double bằng cách đếm khoảng cách mẫu bit có thứ tự. Cũng không dùng **Math.ulp(Infinity)** làm dung sai cho các phép so sánh hữu hạn.

### Một epsilon cố định không phải ULP

Trong Java, **Math.ulp(1.0)** bằng **2^−52** (khoảng 2.22 × 10^−16), còn **Math.ulp(1.0f)** bằng **2^−23**. Không có **Double.EPSILON** được định nghĩa như một hằng chuẩn trong **java.lang.Double**. Nếu tự viết **EPSILON = 1e−9**, đó chỉ là dung sai tuyệt đối được lập trình viên lựa chọn.

Ngay cả khi tự đặt **EPSILON = Math.ulp(1.0)**, nó cũng chỉ mô tả độ phân giải gần 1.0, không phải ngưỡng thích hợp cho mọi độ lớn.

## 5. Cách dùng Math.ulp: ngưỡng theo thang đo, có giới hạn

Khi hai số a, b cùng kiểu double, hữu hạn và gần cùng một thang đo, một phép so sánh mức ULP xấp xỉ có thể là:

~~~java
// Hàm minh họa, nằm trong class chứa ứng dụng:
static boolean withinLocalUlps(double a, double b, int maxUlps) {
    if (maxUlps < 0) {
        throw new IllegalArgumentException("maxUlps must be >= 0");
    }
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true; // cũng coi +0.0 và -0.0 bằng nhau
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double scale = Math.max(Math.abs(a), Math.abs(b));
    double tolerance = maxUlps * Math.ulp(scale);
    return Math.abs(a - b) <= tolerance;
}
~~~

**Đây là ngưỡng tuyệt đối có kích thước được lấy từ ULP tại scale**, không phải phép đếm chính xác maxUlps bước biểu diễn. Nó thích hợp khi tiêu chí của bạn thực sự là ngưỡng khoảng cách số học đó.

Những điểm phải kiểm soát:

1. **maxUlps** không được âm. Nếu bạn cho phép N quá lớn, **N × Math.ulp(scale)** có thể tràn thành Infinity; nên dùng ngưỡng nhỏ, hợp lý và có kiểm chứng.
2. Cần quyết định cách xử lý **NaN** và **Infinity**: hàm trên từ chối NaN; hai infinity cùng dấu bằng nhau theo **==**, còn một infinity với số hữu hạn không được coi là gần.
3. **+0.0** và **−0.0** được coi là bằng nhau nếu không phân biệt dấu zero. Trong ứng dụng cần phân biệt biểu diễn bit, dùng quy tắc riêng.
4. Tại ranh giới lũy thừa của 2, hai bước biểu diễn ở phía số nhỏ hơn có thể có khoảng cách bằng một **Math.ulp** ở điểm ranh giới. Không gọi hàm này là “đếm đúng N ULP”.
5. Nếu a và b trái dấu, cách nhau rất xa hoặc có kiểu float nhưng đã chuyển lên double, thang đo ULP này có thể không diễn đạt đúng hợp đồng kiểm thử.

Với **float**, sử dụng overload **Math.ulp(float)** và thao tác trên float khi bạn muốn đo độ phân giải binary32. Chuyển float sang double rồi đếm ULP double sẽ tạo ra thang đo khác hẳn.

## 6. Đếm chính xác số bước biểu diễn được

Trong một chuỗi các **double hữu hạn**, ta có thể chuyển mẫu bit thành một số nguyên có thứ tự tăng theo giá trị số. Từ đó lấy hiệu thứ tự hai giá trị; **BigInteger** cho phép hiệu không tràn khi khoảng cách vượt quá miền long có dấu.

Ý tưởng đối với bit dấu:

- Mẫu **double** dương dùng thứ tự bit nguyên không dấu đồng biến với giá trị.
- Mẫu double âm có thứ tự bit đảo chiều; cần ánh xạ chúng về một chuỗi tăng.
- Cả **−0.0** và **+0.0** được ánh xạ cùng vị trí 0 để phản ánh phép so sánh giá trị; chúng khác nhau về bit nhưng không được coi là một bước khác biệt giá trị.
- Loại **NaN** và không đếm bước đến Infinity trong helper này. Infinity được xử lý theo **==** ở lớp so sánh ngoài.

Hàm minh họa chính xác về **số bước giá trị double hữu hạn**, với quy tắc nêu trên:

~~~java
import java.math.BigInteger;

// Các phương thức sau đặt bên trong cùng một class Java.
static long orderedBits(double x) {
    long bits = Double.doubleToRawLongBits(x);
    return bits < 0 ? Long.MIN_VALUE - bits : bits;
}

static BigInteger ulpSteps(double a, double b) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        throw new IllegalArgumentException("Only finite double values");
    }
    return BigInteger.valueOf(orderedBits(a))
            .subtract(BigInteger.valueOf(orderedBits(b)))
            .abs();
}

static boolean withinSteps(double a, double b, long maxSteps) {
    if (maxSteps < 0) {
        throw new IllegalArgumentException("maxSteps must be >= 0");
    }
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    return ulpSteps(a, b)
            .compareTo(BigInteger.valueOf(maxSteps)) <= 0;
}
~~~

Phép trừ trong **orderedBits** chạy trên **long** theo quy tắc tràn bù hai của Java. Biến đổi này dùng thứ tự số nguyên có dấu sau ánh xạ; hiệu cuối được tính bằng **BigInteger** nên không làm mất trường hợp khoảng cách cực lớn. Với float, cần một phiên bản riêng dựa trên **Float.floatToRawIntBits** và độ rộng 32 bit, không nên ép nguyên xi quy tắc double.

Đây là một cách cài đặt dùng để **kiểm thử kỹ thuật**. Khi dùng trong thư viện production, nên kèm kiểm thử biên với số âm, dương, zero, subnormal, MIN_NORMAL, MAX_VALUE, NaN và vô cực; lựa chọn đếm 0 bước cho cặp zero trái dấu phải phù hợp hợp đồng của bạn.

## 7. Ví dụ Java 17+ có thể biên dịch và chạy độc lập

Tạo tệp **UlpComparisonDemo.java**:

~~~java
import java.math.BigInteger;

public class UlpComparisonDemo {
    static long orderedBits(double x) {
        long bits = Double.doubleToRawLongBits(x);
        return bits < 0 ? Long.MIN_VALUE - bits : bits;
    }

    static BigInteger ulpSteps(double a, double b) {
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            throw new IllegalArgumentException("Only finite values");
        }
        return BigInteger.valueOf(orderedBits(a))
                .subtract(BigInteger.valueOf(orderedBits(b)))
                .abs();
    }

    static boolean withinSteps(double a, double b, long maxSteps) {
        if (maxSteps < 0) {
            throw new IllegalArgumentException("Invalid maxSteps");
        }
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return ulpSteps(a, b).compareTo(BigInteger.valueOf(maxSteps)) <= 0;
    }

    static boolean withinLocalUlps(double a, double b, int count) {
        if (count < 0) {
            throw new IllegalArgumentException("Invalid count");
        }
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return Math.abs(a - b)
                <= count * Math.ulp(Math.max(Math.abs(a), Math.abs(b)));
    }

    public static void main(String[] args) {
        double one = 1.0;
        double up = Math.nextUp(one);
        double down = Math.nextDown(one);
        double down2 = Math.nextDown(down);

        System.out.println("ULP(1): " + Double.toHexString(Math.ulp(one)));
        System.out.println("up gap: " + Double.toHexString(up - one));
        System.out.println("down gap: " + Double.toHexString(one - down));
        System.out.println("nextUp steps: " + ulpSteps(one, up));
        System.out.println("down2 steps: " + ulpSteps(one, down2));
        System.out.println("approx 1 ULP includes down2: "
                + withinLocalUlps(one, down2, 1));
        System.out.println("exact 1 ULP includes down2: "
                + withinSteps(one, down2, 1));

        System.out.println("0 to min sub steps: "
                + ulpSteps(0.0, Double.MIN_VALUE));
        System.out.println("-min to +min steps: "
                + ulpSteps(-Double.MIN_VALUE, Double.MIN_VALUE));
        System.out.println("signed zero steps: " + ulpSteps(-0.0, +0.0));
        System.out.println("0.1 + 0.2 to 0.3 steps: "
                + ulpSteps(0.1 + 0.2, 0.3));

        System.out.println("NaN close: "
                + withinSteps(Double.NaN, Double.NaN, 1));
        System.out.println("Infinity self close: "
                + withinSteps(Double.POSITIVE_INFINITY, Double.POSITIVE_INFINITY, 0));
        System.out.println("Infinity vs max close: "
                + withinSteps(Double.POSITIVE_INFINITY, Double.MAX_VALUE, 1));
        System.out.println("float ULP(1): "
                + Float.toHexString(Math.ulp(1f)));
    }
}
~~~

Lệnh chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 UlpComparisonDemo.java
java UlpComparisonDemo
~~~

Kết quả stdout:

~~~text
ULP(1): 0x1.0p-52
up gap: 0x1.0p-52
down gap: 0x1.0p-53
nextUp steps: 1
down2 steps: 2
approx 1 ULP includes down2: true
exact 1 ULP includes down2: false
0 to min sub steps: 1
-min to +min steps: 2
signed zero steps: 0
0.1 + 0.2 to 0.3 steps: 1
NaN close: false
Infinity self close: true
Infinity vs max close: false
float ULP(1): 0x1.0p-23
~~~

Điểm đáng chú ý:

- Hai bước từ **1.0** sang **down2** có tổng khoảng cách **2^−52**, bằng **Math.ulp(1.0)**. Phép so sánh ngưỡng theo thang trả **true** nhưng phép đếm **một bước** trả **false**.
- **0.0** và **Double.MIN_VALUE** cách nhau một bước; khoảng cách gần zero quá bé về trị tuyệt đối nhưng có thể rất lớn về tỷ lệ.
- **−Double.MIN_VALUE** và **+Double.MIN_VALUE** cách nhau hai bước khi coi **±0.0** là cùng một giá trị.
- **0.1 + 0.2** khác **0.3** đúng một bước double ở môi trường Java 17+; đó là minh họa về biểu diễn, chưa phải giấy phép tự động chấp nhận mọi sai số một ULP.
- **Infinity** không được biến thành giá trị hữu hạn thông qua phép so sánh gần đúng. Hai infinity bằng nhau vẫn trả **true** theo quy tắc của helper; nếu nghiệp vụ cấm mọi infinity, hãy loại chúng trước.

## 8. Chọn ngưỡng bao nhiêu ULP?

Không có con số cố định cho mọi thuật toán. Một quy trình thực tế:

1. **Xác định giá trị tham chiếu:** có thể là kết quả tính bằng độ chính xác cao, công thức chính xác rồi làm tròn theo kiểu đích, bộ dữ liệu kiểm thử được thẩm định, hoặc hợp đồng của hàm thư viện.
2. **Xác định dạng sai số được cam kết:** “không quá N bước representable” khác “không quá N × Math.ulp(reference)”. Viết rõ định nghĩa vào kiểm thử.
3. **Chọn độ rộng đo:** nếu dữ liệu được tính và lưu dưới dạng float, đo theo ULP float; nếu là double, đo theo ULP double. Không để **binary numeric promotion** âm thầm thay đổi thang đo.
4. **Dùng N từ phân tích sai số hoặc hợp đồng:** một phép tính được làm tròn đúng có thể yêu cầu 0 ULP so với kết quả đã làm tròn tham chiếu; một hàm xấp xỉ có thể cần N khác. Số lượng thao tác và độ điều kiện ảnh hưởng tới sai số tích lũy, nên “1 ULP cho mọi phép tính” không phải quy luật.
5. **Kiểm tra ranh giới:** zero, subnormal, lũy thừa của 2, đầu mút miền normal, giá trị âm, NaN, infinity, số gần cực đại, các trường hợp cancellation.
6. **Đặt ngưỡng nghiệp vụ bổ sung nếu cần:** giới hạn ULP và giới hạn tuyệt đối/tương đối có thể **đồng thời** được yêu cầu. Không cho phép một phép đo thay thế yêu cầu còn lại.

Ví dụ, với một thuật toán tính đại lượng đo bằng mét, yêu cầu có thể là: sai lệch **không quá 2 bước double** **và** sai số tuyệt đối **không quá 10^−6 m**. Khi đó cả hai điều kiện phải được kiểm tra; một kết quả vượt ngưỡng mét sẽ bị từ chối dù khoảng cách ULP rất nhỏ.

## 9. Các tình huống thường gặp

### Tình huống A — Kiểm thử hai triển khai hàm số

Một thuật toán được đặc tả sai khác không quá **2 ULP** so với kết quả chuẩn đã làm tròn theo double. Trong trường hợp đó, **đếm bước ULP** là cách diễn đạt trực tiếp của hợp đồng. Các test cần mẫu số âm, dương, giá trị gần 0 và các ranh giới số mũ.

Lưu ý: nếu tài liệu định nghĩa ULP theo **đơn vị khoảng cách tại kết quả chính xác** thay vì số bước biểu diễn, phải triển khai đúng định nghĩa được ghi trong hợp đồng; đừng tự thay bằng phép đếm nguyên.

### Tình huống B — Kiểm thử kết quả có sai số tương đối

Một phép đo dương có độ lớn từ **10^−8** đến **10^8**, yêu cầu sai lệch tối đa **0.01%**. Điều kiện **relative tolerance** diễn đạt đúng yêu cầu hơn một N ULP bất kỳ. Có thể thêm absTol nếu miền gần zero cần ngưỡng vật lý phù hợp.

### Tình huống C — Kiểm tra hội tụ vòng lặp

Điều kiện kiểu **Math.abs(next - current) <= N * Math.ulp(current)** chỉ phát hiện các bước thay đổi nhỏ so với độ phân giải tại current. Nó **không đảm bảo** kết quả đã gần nghiệm đúng: thuật toán có thể đình trệ do làm tròn, đạo hàm nhỏ, vùng bằng phẳng hoặc lỗi số học. Nên kết hợp tiêu chí dựa vào **residual** và giới hạn số vòng lặp khi thích hợp.

### Tình huống D — Tiền và quy tắc làm tròn thập phân

So sánh hai khoản tiền với ngưỡng **0.01** đơn vị tiền tệ là bài toán theo đơn vị và quy tắc thập phân. **BigDecimal** khởi tạo từ chuỗi thập phân rõ ràng, kết hợp **setScale** và **RoundingMode** theo nghiệp vụ, thường biểu đạt chính xác hơn. Đừng dùng ULP double làm quy tắc kế toán.

### Tình huống E — Hai biểu thức tính ra hai số sát nhau

**0.1 + 0.2** và **0.3** cách nhau một double step. Nếu đây là kiểm thử đơn thuần xác nhận một triển khai số cho kết quả trong sai số làm tròn đã dự kiến, giới hạn một bước có thể được biện minh. Nếu giá trị này là điều kiện giao dịch hoặc dữ liệu cần khớp tuyệt đối ở cơ số 10, hãy dùng biểu diễn và hợp đồng phù hợp thay vì mặc nhiên chấp nhận.

## 10. NaN, Infinity, signed zero: phải quyết định trước

Các giá trị đặc biệt không tuân theo mọi quy tắc so sánh hữu hạn.

| Trường hợp | Hành vi ngôn ngữ Java | Chính sách thường dùng trong helper kiểm thử |
| --- | --- | --- |
| **NaN** | **Double.NaN == Double.NaN** là **false** | Trả **false**; nếu test yêu cầu NaN, kiểm tra **Double.isNaN** riêng |
| **+Infinity** so với **+Infinity** | **== true** | Có thể cho **true** nếu kết quả vô cực là hợp lệ |
| **+Infinity** so với số hữu hạn | **== false** | Không tính khoảng cách N ULP đến infinity |
| **+0.0** so với **−0.0** | **== true** | Thường cùng giá trị, song có thể cần kiểm tra bit dấu |
| **0.0** so với **Double.MIN_VALUE** | Giá trị khác nhau | Chỉ cách **một bước**; vẫn phải xem xét yêu cầu near-zero |

Nếu dấu của zero quan trọng, ví dụ **1.0 / +0.0** cho **+Infinity** và **1.0 / −0.0** cho **−Infinity**, hãy dùng:

~~~java
boolean sameBits = Double.doubleToRawLongBits(a)
        == Double.doubleToRawLongBits(b);
~~~

Đoạn trên minh họa đặt trong một method đã định nghĩa biến **a** và **b**; nó **không phải** chương trình Java độc lập. Phép so sánh bit chính xác còn phân biệt payload NaN; khi yêu cầu chỉ cần nhận diện NaN, dùng **Double.isNaN** phù hợp hơn.

Đối với **Double.compare(a,b)**, Java sắp xếp **−0.0** và **+0.0** khác nhau, trong khi toán tử **==** coi chúng bằng nhau. Chọn đúng phép so sánh cho mục đích của bạn.

## 11. Tại sao ULP vẫn không đủ để đánh giá độ đúng?

ULP đo độ khác biệt **theo độ phân giải định dạng đích**. Nó không nói bản thân thuật toán có tính **ổn định số**, cũng không phản ánh toàn bộ ràng buộc của bài toán.

### Gần zero và cancellation

Giả sử hai số gần bằng nhau bị trừ đi. Kết quả có thể rất nhỏ về trị tuyệt đối, nhưng sai lệch tương đối lớn nếu các toán hạng đã mang lỗi làm tròn từ trước. Nếu dùng ULP của **kết quả nhỏ** làm chuẩn, chỉ một sai lệch tuyệt đối nhỏ cũng có thể tương ứng với rất nhiều ULP. Nếu dùng ULP của **toán hạng lớn**, bạn có thể cho phép sai số quá rộng. Cần biết **đầu ra nào** có ý nghĩa và thang nào được phép đo.

### Ở độ lớn rất lớn

Ở gần **Double.MAX_VALUE**, một ULP bằng **2^971** — con số khổng lồ theo đơn vị tuyệt đối. Hai kết quả sát nhau trên lưới double vẫn có thể sai khác quá lớn đối với ứng dụng có giới hạn chặt bằng mét, giây hoặc tiền tệ.

### Sai số thuật toán tích lũy

Phép cộng lặp đi lặp lại, các phép biến đổi kém điều kiện và thay đổi thứ tự phép tính có thể tích lũy sai số. Số ULP của một phép tính đơn không tự trở thành giới hạn ULP cho cả thuật toán dài. Nếu thuật toán chứa các phép toán transcendental, hãy đọc tiêu chuẩn độ chính xác của **API được gọi** thay vì đoán.

**Nguyên tắc:** dùng ULP khi đó là đơn vị sai số được định nghĩa, có thể giải thích và kiểm chứng; dùng đơn vị nghiệp vụ khi điều kiện nghiệm thu nằm ở thế giới thực.

## 12. Các lỗi phổ biến cần tránh

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng **1e−9** cho mọi số | Dung sai quá rộng gần zero hoặc quá chặt ở độ lớn khác | Chọn absTol/relTol theo bài toán, hoặc thang ULP có lý do |
| Coi **N × Math.ulp(x)** là đúng N bước trong mọi trường hợp | Sai ở ranh giới lũy thừa của 2 | Phân biệt ngưỡng số học và đếm bước |
| Dùng ULP double cho kết quả thực chất là float | Ngưỡng so sánh thay đổi theo kiểu | Kiểm tra độ rộng phép tính/lưu trữ |
| Chọn N = 4, 8 hoặc 16 theo thói quen | Che giấu lỗi mà không có căn cứ | Xuất phát từ hợp đồng/phân tích lỗi |
| Dùng **Math.ulp(Infinity)** như epsilon | Infinity không phải dung sai hữu hạn | Phân loại NaN/Infinity trước |
| Thực hiện trừ double cực đại trái dấu rồi coi kết quả là khoảng cách số học hữu hạn | Phép trừ có thể tràn Infinity | Dùng hàm đếm bước chính xác hoặc xử lý miền riêng |
| Cho rằng **0.0** và **MIN_VALUE** gần nhau nên luôn chấp nhận | Sai khác tương đối có thể rất lớn | Thêm ngưỡng near-zero hoặc kiểm tra kết quả phải khác 0 |
| Đổi điều kiện hội tụ thành “khác tối đa 1 ULP” | Có thể chỉ xác nhận thuật toán đình trệ | Kiểm tra residual, mục tiêu nghiệm và ngưỡng nghiệp vụ |
| Dùng so sánh gần đúng làm **equals/hashCode** | Quan hệ gần đúng không bắc cầu | Dùng biểu diễn/khóa chính xác hoặc lượng tử hóa theo hợp đồng |
| Bỏ qua **−0.0**, **NaN**, **Infinity** | Kết quả kiểm thử khó hiểu hoặc sai | Định nghĩa chính sách từng trường hợp |

## 13. Bài tập kiểm tra

**Bài 1.** Tại **1.0**, vì sao **Math.nextUp(1.0) − 1.0** khác **1.0 − Math.nextDown(1.0)**?

*Đáp án:* 1.0 nằm đúng ranh giới hai đoạn số mũ nhị phân; bước phía trên là **2^−52**, phía dưới là **2^−53**. **Math.ulp(1.0)** bằng bước theo hướng tăng độ lớn, tức **2^−52**.

**Bài 2.** Nếu giới hạn cho phép **1 ULP** hiểu là “không quá 1 bước double”, **1.0** và **Math.nextDown(Math.nextDown(1.0))** có gần nhau không?

*Đáp án:* **Không**. Hai số cách nhau **hai** giá trị kế tiếp, dù sai khác tuyệt đối của chúng bằng **Math.ulp(1.0)**.

**Bài 3.** **0.0** và **Double.MIN_VALUE** cách bao nhiêu bước double hữu hạn? Có nên chấp nhận chúng là bằng nhau về nghiệp vụ?

*Đáp án:* **Một bước**. Việc có chấp nhận hay không phải dựa vào yêu cầu gần zero; một bước ULP không chứng minh tỷ lệ sai khác nhỏ.

**Bài 4.** Vì sao không dùng **Math.ulp(1.0)** làm epsilon chung cho mọi kết quả double?

*Đáp án:* Kích thước ULP thay đổi cùng độ lớn số. ULP tại 1.0 không đại diện cho độ phân giải ở 1e−100 hay 1e100.

**Bài 5.** Một thuật toán xử lý khoảng cách địa lý được yêu cầu sai khác tối đa **0.5 m**. Nên lấy tiêu chí nào làm điều kiện nghiệm thu chính?

*Đáp án:* Dùng sai số tuyệt đối theo mét. ULP có thể là công cụ kiểm thử chi tiết thêm khi có căn cứ, nhưng không thay thế yêu cầu 0.5 m.

**Bài 6.** **NaN** xuất hiện trong cả expected và actual. **withinSteps(NaN, NaN, 0)** theo ví dụ trả gì, và làm sao kiểm thử kết quả phải là NaN?

*Đáp án:* **false**. Kiểm tra **Double.isNaN(actual)** riêng khi NaN là kết quả mong đợi.

## 14. Ghi nhớ để lựa chọn đúng

Khi thiết kế phép so sánh số thực, hãy trả lời theo trình tự: **(1) Đại lượng nào đang được so sánh? (2) Có giới hạn bằng đơn vị vật lý/kinh doanh không? (3) Có tiêu chí sai số tương đối không? (4) Nếu muốn giới hạn ULP, đó là ngưỡng khoảng cách số học hay số bước giá trị biểu diễn được? (5) Tham chiếu và N lấy từ đâu? (6) Các giá trị biên sẽ được xử lý thế nào?**

Giới hạn theo ULP phát huy giá trị nhất ở **kiểm thử độ chính xác của phép toán/thuật toán dấu phẩy động cùng kiểu** khi sai số được định nghĩa bằng đơn vị lưới biểu diễn. Nó cần được dùng cùng hiểu biết về rounding, đặc tính thuật toán và các ngưỡng nghiệp vụ.

## 15. Tài liệu tham khảo

- [Java SE 17 Math API — ulp, nextUp, nextDown, nextAfter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html).
- [Java SE 17 Double API — doubleToRawLongBits, compare, isFinite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
- [Java SE 17 Float API — floatToRawIntBits, MIN_VALUE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html).
- [Java Language Specification 17 — §4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3).
- [Java Language Specification 17 — §15.21 Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21).